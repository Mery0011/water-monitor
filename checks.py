"""Meaningful regression checks for telemetry, incidents and the real UI."""
from pathlib import Path
from datetime import datetime, timedelta
import unittest
from copy import deepcopy
import os
import sqlite3
import tempfile
from unittest.mock import patch
from contextlib import closing
import joblib
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest
from contacts import get_contact, save_contact, contact_links
from urllib.parse import urlparse, parse_qs
from storage import save_simulation, load_incidents, load_activity, update_saved_incident
from engine import make_day, features, new_simulation, advance, set_mode, update_event, new_live, sync_live, LOCAL_TZ, APARTMENTS, ensure_apartments, restore_demo_connection

ROOT = Path(__file__).resolve().parent
BUNDLE = joblib.load(ROOT/'artifacts/water_model.joblib')


class EngineTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='water-db-check-')
        self.addCleanup(directory.cleanup)
        self.db_path = Path(directory.name)/'incidents.sqlite3'
        env = patch.dict(os.environ,{'WATER_MONITOR_DB':str(self.db_path)})
        env.start()
        self.addCleanup(env.stop)

    def test_other_window_resolution_survives_stale_saves_and_audit_appends(self):
        sim = new_simulation()
        set_mode(sim,'03','leak'); advance(sim,BUNDLE,60)
        run_id = save_simulation(sim)
        update_saved_incident(run_id,1,'resolve','leak_fixed','Resolved in window B')
        # Even an unchanged local snapshot must synchronize remote edits.
        save_simulation(sim)
        self.assertEqual(sim['events'][0]['status'],'resolved')
        self.assertEqual(sim['events'][0]['note'],'Resolved in window B')
        set_mode(sim,'04','shower'); save_simulation(sim)
        self.assertEqual(load_incidents()[0]['note'],'Resolved in window B')
        history = load_activity()
        self.assertTrue(any(h.get('source')=='archive' and h.get('action')=='resolve' for h in history))
        self.assertTrue(any(h.get('type')=='scenario' and h.get('apartment')=='04' for h in history))
        before = len(history)
        save_simulation(sim)
        self.assertEqual(len(load_activity()),before)

    def test_conflicting_resolutions_keep_first_saved_note(self):
        sim = new_simulation()
        set_mode(sim,'03','leak'); advance(sim,BUNDLE,60)
        save_simulation(sim)
        other = deepcopy(sim)
        update_event(other,1,'resolve','leak_fixed','First saved note')
        save_simulation(other)
        update_event(sim,1,'resolve','unknown','Stale conflicting note')
        save_simulation(sim)
        self.assertEqual(sim['_workflow_conflicts'],[1])
        self.assertEqual(sim['events'][0]['note'],'First saved note')
        self.assertEqual(load_incidents()[0]['note'],'First saved note')
        # The rejected action must never reappear as a successful audit entry.
        save_simulation(sim)
        self.assertFalse(any(h.get('note')=='Stale conflicting note' for h in load_activity()))

    def test_two_browser_windows_keep_completed_inspection(self):
        first = AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
        first.radio[0].set_value('demo').run()
        first.button(key='scenario_leak').click().run()
        advance(first.session_state['simulation'],BUNDLE,60); first.run()
        run_id = first.session_state['simulation']['_run_id']
        second = AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
        prefix = f'saved_{run_id}_1'
        second.text_input(key=prefix+'_note').input('Completed in the second window').run()
        second.button(key=prefix+'_resolve').click().run()
        self.assertFalse(second.exception)
        first.run()
        self.assertFalse(first.exception)
        event = first.session_state['simulation']['events'][0]
        self.assertEqual(event['status'],'resolved')
        self.assertEqual(event['note'],'Completed in the second window')
        persisted = next(e for e in load_incidents() if e['run_id']==run_id)
        self.assertEqual(persisted['note'],'Completed in the second window')

    def test_legacy_database_activity_is_migrated_once(self):
        with closing(sqlite3.connect(self.db_path)) as db:
            db.executescript("""CREATE TABLE runs(id TEXT PRIMARY KEY,mode TEXT,created_at TEXT);
                CREATE TABLE activity(run_id TEXT,sequence INTEGER,payload TEXT,PRIMARY KEY(run_id,sequence));
                INSERT INTO runs VALUES('legacy','demo','2026-11-16');
                INSERT INTO activity VALUES('legacy',0,'{"type":"scenario","apartment":"03","mode":"leak"}');
                INSERT INTO activity VALUES('legacy',1,'{"type":"event","source":"archive","action":"ack"}');
            """)
            db.commit()
        self.assertEqual(len(load_activity()),2)
        self.assertEqual(len(load_activity()),2)

    def test_database_round_trip_and_separate_runs(self):
        sim = new_simulation()
        set_mode(sim,'03','leak'); advance(sim,BUNDLE,60)
        run_id = save_simulation(sim)
        save_simulation(sim)
        self.assertEqual(len(load_incidents()),1)
        update_event(sim,1,'ack'); save_simulation(sim)
        note = "수리 완료 — ta’mirlandi; '); DROP TABLE incidents; --"
        update_event(sim,1,'resolve','leak_fixed',note); save_simulation(sim)
        loaded = load_incidents()[0]
        self.assertEqual(loaded['status'],'resolved')
        self.assertEqual(loaded['outcome'],'leak_fixed')
        self.assertEqual(loaded['note'],note)
        self.assertFalse(loaded['active'])
        self.assertEqual(load_activity()[-1]['action'],'resolve')
        other = new_simulation()
        set_mode(other,'15','leak'); advance(other,BUNDLE,60)
        other_id = save_simulation(other)
        self.assertNotEqual(run_id,other_id)
        self.assertEqual(len(load_incidents()),2)
        self.assertEqual(len(load_incidents(exclude_run=other_id)),1)
        with closing(sqlite3.connect(self.db_path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM incidents').fetchone()[0],2)

    def test_saved_incident_can_be_completed_after_restart(self):
        sim = new_simulation()
        set_mode(sim,'03','leak'); advance(sim,BUNDLE,60)
        run_id = save_simulation(sim)
        update_saved_incident(run_id,1,'ack')
        self.assertEqual(load_incidents()[0]['status'],'ack')
        update_saved_incident(run_id,1,'resolve','leak_fixed','Saved after restart')
        self.assertEqual(load_incidents()[0]['note'],'Saved after restart')
        with self.assertRaises(ValueError):
            update_saved_incident(run_id,1,'ack')
        self.assertEqual(load_activity()[-1]['source'],'archive')

    def test_failed_save_is_not_marked_successful(self):
        sim = new_simulation()
        with self.assertRaises(sqlite3.Error):
            save_simulation(sim,path=self.db_path.parent)
        self.assertNotIn('_saved_digest',sim)

    def test_ui_saved_pending_incident_survives_reset_and_new_session(self):
        app = AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
        app.radio[0].set_value('demo').run()
        app.button(key='scenario_leak').click().run()
        advance(app.session_state['simulation'],BUNDLE,60); app.run()
        run_id = app.session_state['simulation']['_run_id']
        self.assertEqual(len(load_incidents()),1)
        app.button(key='reset').click().run()
        self.assertEqual(len(load_incidents()),1)
        self.assertNotEqual(app.session_state['simulation']['_run_id'],run_id)
        # New AppTest represents a new browser session, with a fresh simulation.
        reopened = AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
        self.assertFalse(reopened.exception)
        prefix = f'saved_{run_id}_1'
        reopened.button(key=prefix+'_ack').click().run()
        self.assertEqual(load_incidents()[0]['status'],'ack')
        reopened.text_input(key=prefix+'_note').input('Restart inspection').run()
        reopened.button(key=prefix+'_resolve').click().run()
        self.assertFalse(reopened.exception)
        self.assertEqual(load_incidents()[0]['status'],'resolved')
        self.assertEqual(load_incidents()[0]['note'],'Restart inspection')

    def test_owner_contacts_persist_and_demo_actions_are_disabled(self):
        sample = get_contact('15')
        self.assertTrue(sample['is_demo'])
        self.assertEqual(contact_links(sample,'Test','Body'),(None,None))
        save_contact('15','Owner 이름','+1 (202) 555-0199','owner@example.invalid',is_demo=False)
        saved = get_contact('15')
        self.assertEqual(saved['name'],'Owner 이름')
        self.assertEqual(saved['phone'],'+12025550199')
        call,mail = contact_links(saved,'점검 & inspection','Apartment 15\nPlease call security.')
        self.assertEqual(call,'tel:+12025550199')
        parsed = parse_qs(urlparse(mail).query)
        self.assertEqual(parsed['subject'],['점검 & inspection'])
        self.assertEqual(parsed['body'],['Apartment 15\nPlease call security.'])
        self.assertTrue(get_contact('01')['is_demo'])
        with self.assertRaises(ValueError):
            save_contact('15','Owner','bad-number','owner@example.invalid',is_demo=False)
        with self.assertRaises(ValueError):
            save_contact('15','Owner','','owner@example.invalid\r\nBcc: bad@example.invalid',is_demo=False)
        self.assertEqual(get_contact('15')['name'],'Owner 이름')

    def test_ui_owner_contact_form_saves_and_survives_reset(self):
        app = AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
        self.assertFalse(app.exception)
        app.text_input(key='owner_03_name').input('Test Owner')
        app.text_input(key='owner_03_phone').input('+12025550199')
        app.text_input(key='owner_03_email').input('owner@example.invalid')
        app.checkbox(key='owner_03_demo').uncheck()
        next(b for b in app.button if b.label=='Save contact').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(get_contact('03')['name'],'Test Owner')
        self.assertFalse(get_contact('03')['is_demo'])
        app.button(key='reset').click().run()
        self.assertEqual(get_contact('03')['name'],'Test Owner')
        app.selectbox(key='language').set_value('uz').run()
        self.assertFalse(app.exception)
        self.assertEqual(app.text_input(key='owner_03_name').label,'Xonadon egasining ismi')

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

    def test_resolve_connection_restores_current_sample_and_keeps_history(self):
        sim = new_simulation()
        set_mode(sim,'02','offline'); advance(sim,BUNDLE,15)
        event = next(e for e in sim['events'] if e['apartment']=='02')
        minute = sim['minute']
        update_event(sim,event['id'],'resolve','connection_restored','Sensor reconnected')
        self.assertEqual(sim['minute'],minute)
        self.assertEqual(sim['modes']['02'],'normal')
        self.assertFalse(sim['last_snapshot']['02']['offline'])
        self.assertTrue(np.isfinite(sim['last_snapshot']['02']['flow']))
        self.assertFalse(event['active'])
        self.assertEqual(event['end'],minute)
        self.assertNotIn(('02','offline'),sim['open_events'])
        self.assertTrue(pd.isna(sim['frames']['02'].loc[minute-1,'flow']))
        self.assertTrue(pd.notna(sim['frames']['02'].loc[minute,'flow']))
        save_simulation(sim)
        self.assertFalse(load_incidents()[0]['active'])
        set_mode(sim,'02','offline'); advance(sim,BUNDLE,1)
        self.assertEqual(len(sim['events']),2)
        self.assertNotEqual(sim['events'][-1]['id'],event['id'])
        # Reapplying an old resolution must not reconnect a new incident.
        restore_demo_connection(sim,event)
        self.assertTrue(sim['last_snapshot']['02']['offline'])

    def test_device_inspection_does_not_claim_connection_restored(self):
        sim = new_simulation()
        set_mode(sim,'02','offline'); advance(sim,BUNDLE,15)
        event = sim['events'][0]
        update_event(sim,event['id'],'resolve','device_check')
        self.assertTrue(event['active'])
        self.assertTrue(sim['last_snapshot']['02']['offline'])
        self.assertEqual(sim['modes']['02'],'offline')

    def test_ui_resolve_connection_updates_card_without_advancing(self):
        app = AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
        app.radio[0].set_value('demo').run()
        app.button(key='scenario_offline').click().run()
        app.button(key='step').click().run()
        minute = app.session_state['simulation']['minute']
        app.selectbox(key='out_1').set_value('connection_restored').run()
        app.button(key='done_1').click().run()
        self.assertFalse(app.exception)
        sim = app.session_state['simulation']
        self.assertEqual(sim['minute'],minute)
        self.assertFalse(sim['last_snapshot']['03']['offline'])
        self.assertEqual(sim['modes']['03'],'normal')
        self.assertEqual(next(m for m in app.metric if m.label=='Offline').value,'0')

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
