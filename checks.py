"""Meaningful regression checks for telemetry, incidents and the real UI."""
from pathlib import Path
from datetime import datetime, timedelta
import unittest
import joblib
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest
from engine import make_day, features, new_simulation, advance, set_mode, update_event, new_live, sync_live, LOCAL_TZ, APARTMENTS, ensure_apartments

ROOT = Path(__file__).resolve().parent
BUNDLE = joblib.load(ROOT/'artifacts/water_model.joblib')


class EngineTests(unittest.TestCase):
    def test_fifteen_apartments_and_existing_session_upgrade(self):
        sim = new_simulation()
        self.assertEqual(APARTMENTS, [f'{i:02d}' for i in range(1,16)])
        self.assertEqual(len(sim['frames']),15)
        set_mode(sim,'15','leak')
        advance(sim,BUNDLE,60)
        self.assertIn(('15','water'),sim['open_events'])
        self.assertEqual(len(sim['last_snapshot']),15)
        saved_event = sim['events'][0].copy()
        del sim['frames']['14']
        del sim['modes']['14']
        ensure_apartments(sim,BUNDLE)
        self.assertIn('14',sim['last_snapshot'])
        self.assertEqual(sim['events'][0],saved_event)

    def test_live_clock_real_minutes_and_midnight(self):
        now = datetime(2026,11,16,23,59,20,tzinfo=LOCAL_TZ)
        sim = new_live(now)
        sync_live(sim,BUNDLE,now)
        self.assertEqual(sim['minute'],1439)
        self.assertTrue(sim['running'])
        sync_live(sim,BUNDLE,now+timedelta(seconds=20))
        self.assertEqual(sim['minute'],1439)
        sync_live(sim,BUNDLE,now+timedelta(seconds=60))
        self.assertEqual(sim['minute'],1440)
        self.assertEqual(len(sim['frames']['01']),2880)
        self.assertTrue(sim['running'])

    def test_default_ui_live_clock(self):
        app = AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.radio[0].value,'live')
        self.assertTrue(next(b for b in app.button if b.label=='+15 minutes').disabled)
        sim = app.session_state['simulation']
        now = datetime.now(LOCAL_TZ)
        self.assertEqual(sim['minute'],now.hour*60+now.minute)

    def test_features_do_not_see_future(self):
        day = make_day(456,True)
        full = features(day)
        prefix = features(day.iloc[:200])
        pd.testing.assert_frame_equal(full.iloc[:200],prefix)

    def test_missing_reading_breaks_continuity(self):
        day = pd.DataFrame({'minute':range(5),'flow':[1,1,np.nan,1,1]})
        self.assertEqual(features(day).continuous.tolist(),[1,2,0,1,2])

    def test_incident_lifecycle_no_duplicate_until_flow_stops(self):
        sim = new_simulation()
        set_mode(sim,'03','leak')
        advance(sim,BUNDLE,120)
        events = [e for e in sim['events'] if e['apartment']=='03' and e['kind']=='water']
        self.assertEqual(len(events),1)
        event_id = events[0]['id']
        update_event(sim,event_id,'ack')
        update_event(sim,event_id,'resolve','Sizish tasdiqlandi','Demo tekshiruv')
        self.assertFalse(events[0]['active'])
        self.assertNotIn(('03','water'),sim['open_events'])
        self.assertEqual(sim['modes']['03'],'normal')
        self.assertEqual(sim['last_snapshot']['03']['flow'],0)
        self.assertEqual(sim['last_snapshot']['03']['duration'],0)
        self.assertFalse(sim['last_snapshot']['03']['anomaly'])
        self.assertEqual(sim['frames']['03'].loc[sim['minute'],'flow'],0)
        advance(sim,BUNDLE,30)
        self.assertEqual(len([e for e in sim['events'] if e['apartment']=='03']),1)
        set_mode(sim,'03','normal')
        advance(sim,BUNDLE,10)
        self.assertNotIn(('03','water'),sim['open_events'])
        set_mode(sim,'03','leak')
        advance(sim,BUNDLE,120)
        self.assertEqual(len([e for e in sim['events'] if e['apartment']=='03']),2)

    def test_short_shower_does_not_alert(self):
        sim = new_simulation()
        set_mode(sim,'01','shower')
        advance(sim,BUNDLE,30)
        self.assertEqual(sim['modes']['01'],'normal')
        self.assertFalse([e for e in sim['events'] if e['apartment']=='01'])

    def test_offline_and_recovery(self):
        sim = new_simulation()
        set_mode(sim,'02','offline'); advance(sim,BUNDLE,15)
        self.assertTrue(sim['last_snapshot']['02']['offline'])
        self.assertEqual(sim['events'][0]['kind'],'offline')
        advance(sim,BUNDLE,15)
        self.assertEqual(len(sim['events']),1)
        set_mode(sim,'02','normal'); advance(sim,BUNDLE,1)
        self.assertFalse(sim['events'][0]['active'])
        self.assertFalse(sim['last_snapshot']['02']['offline'])

    def test_end_of_day_is_bounded(self):
        sim = new_simulation(); sim['minute']=1438; sim['running']=True
        advance(sim,BUNDLE,15)
        self.assertEqual(sim['minute'],1439)
        self.assertFalse(sim['running'])
        advance(sim,BUNDLE,15)
        self.assertEqual(sim['minute'],1439)

    def test_ui_startup_step_and_reset(self):
        app = AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
        app.radio[0].set_value('demo').run()
        self.assertFalse(app.exception)
        step = next(b for b in app.button if b.label=='+15 minutes')
        step.click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['simulation']['minute'],136)
        next(b for b in app.button if b.label=='Reset demo').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['simulation']['minute'],121)

    def test_ui_scenario_acknowledge_and_resolve(self):
        app = AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
        app.radio[0].set_value('demo').run()
        next(b for b in app.button if b.label=='💧 Start leak').click().run()
        self.assertFalse(app.exception)
        # Drive the same simulation path used by the timer without waiting.
        advance(app.session_state['simulation'],BUNDLE,60)
        app.run()
        self.assertFalse(app.exception)
        next(b for b in app.button if b.label=='Acknowledge').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['simulation']['events'][0]['status'],'ack')
        next(b for b in app.button if b.label=='Resolve').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['simulation']['events'][0]['status'],'resolved')
        self.assertFalse(app.session_state['simulation']['events'][0]['active'])
        self.assertEqual(app.session_state['simulation']['modes']['03'],'normal')

    def test_language_switch_preserves_incident_and_mode(self):
        app = AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
        self.assertEqual(app.selectbox(key='language').value,'en')
        self.assertEqual(app.title[0].value,'💧 Water Monitor')
        app.radio[0].set_value('demo').run()
        app.button(key='scenario_leak').click().run()
        advance(app.session_state['simulation'],BUNDLE,60)
        app.run()
        app.button(key='ack_1').click().run()
        minute = app.session_state['simulation']['minute']
        app.selectbox(key='language').set_value('ko').run()
        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value,'💧 수도 모니터링')
        self.assertEqual(app.radio[0].value,'demo')
        self.assertEqual(app.session_state['simulation']['minute'],minute)
        self.assertEqual(app.session_state['simulation']['events'][0]['status'],'ack')
        self.assertEqual(app.button(key='scenario_leak').label,'💧 누수 시작')
        app.selectbox(key='out_1').set_value('normal_usage').run()
        app.text_input(key='note_1').input('Test staff note').run()
        app.selectbox(key='language').set_value('en').run()
        self.assertEqual(app.selectbox(key='out_1').value,'normal_usage')
        self.assertEqual(app.text_input(key='note_1').value,'Test staff note')
        app.selectbox(key='language').set_value('uz').run()
        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value,'💧 Suv nazorati')
        self.assertEqual(app.button(key='scenario_leak').label,'💧 Sizishni boshlash')
        self.assertEqual(app.radio[0].value,'demo')
        self.assertEqual(app.session_state['simulation']['minute'],minute)
        self.assertEqual(app.selectbox(key='out_1').value,'normal_usage')
        self.assertEqual(app.text_input(key='note_1').value,'Test staff note')
        app.selectbox(key='language').set_value('ko').run()
        app.button(key='done_1').click().run()
        self.assertFalse(app.exception)
        event = app.session_state['simulation']['events'][0]
        self.assertEqual(event['status'],'resolved')
        self.assertEqual(event['outcome'],'normal_usage')
        self.assertEqual(event['note'],'Test staff note')


if __name__=='__main__':
    unittest.main()
