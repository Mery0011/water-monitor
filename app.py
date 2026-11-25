from pathlib import Path
import io
import json
import math
import struct
import time
import wave
from datetime import datetime
import joblib
import pandas as pd
import streamlit as st
import altair as alt
from engine import APARTMENTS, new_simulation, new_live, sync_live, local_now, advance, set_mode, update_event, clock_label, stop_demo_water, ensure_apartments, restore_demo_connection, change_scenario, set_monitoring_state
from i18n import translate, OUTCOMES
from storage import save_simulation, load_incidents, update_saved_incident
from database import DATABASE_ERRORS
from engine import LOCAL_TZ
from contacts import get_contact, save_contact, contact_links

ROOT = Path(__file__).resolve().parent
language = st.session_state.get('language', 'en')
def t(text, **values):
    return translate(text, language, **values)

st.set_page_config(page_title=t('Water Monitor'), page_icon='💧', layout='wide', initial_sidebar_state='collapsed')
st.markdown('''<style>
/* Keep the last reading visible while Streamlit refreshes the dashboard. */
[data-testid="stElementContainer"][data-stale="true"]{
opacity:1!important;filter:none!important;transition:none!important}
.stApp{background:#f4f8fb} .block-container{max-width:1450px;padding-top:2rem}
h1,h2,h3{color:#102c42} div[data-testid="stMetric"]{background:white;border:1px solid #dbe7ec;
border-radius:12px;padding:16px} .stButton>button[kind="primary"]{background:#008e91;border:0}
div[class*="st-key-apartment_card_"]{
background:linear-gradient(145deg,#ffffff,#eaf8fb);
border:1px solid #98cbd5!important;border-top:4px solid #008e91!important;
border-radius:16px!important;padding:16px!important;
box-shadow:0 6px 18px rgba(16,70,90,.13);
transition:box-shadow .18s ease,transform .18s ease}
div[class*="st-key-apartment_card_"]:hover{
box-shadow:0 10px 24px rgba(16,70,90,.21);transform:translateY(-2px)}
div[class*="st-key-apartment_card_"] [data-testid="stMarkdownContainer"] strong{
color:#123d51;font-size:1.12rem}
</style>''', unsafe_allow_html=True)
_, language_column = st.columns([3,1])
with language_column:
    language = st.selectbox('Language / 언어 / Til', ['en','ko','uz'], format_func=lambda code: {'en':'English','ko':'한국어','uz':'O‘zbekcha'}[code], key='language')

@st.cache_resource
def load_bundle():
    return joblib.load(ROOT/'artifacts/water_model.joblib')

if not (ROOT/'artifacts/water_model.joblib').exists():
    st.error(t('Train the model with train.py first.')); st.stop()
bundle = load_bundle()
metrics = json.loads((ROOT/'artifacts/metrics.json').read_text())
st.caption(t('PORTFOLIO PROTOTYPE • SYNTHETIC DATA • NO REAL METER CONNECTED'))
st.title('💧 '+t('Water Monitor'))
st.write(t('Water usage and unusual activity, from apartments to the security desk.'))
def persist_current():
    if 'simulation' in st.session_state:
        try:
            save_simulation(st.session_state['simulation'])
            if st.session_state['simulation'].get('_workflow_conflicts'):
                st.session_state['storage_conflict_notice'] = True
        except (OSError,*DATABASE_ERRORS):
            st.error(t('Could not save to the database. Check disk space and folder permissions, then retry.'))
            st.stop()


with st.sidebar:
    st.header(t('About this project'))
    st.write(t('**Model:** Isolation Forest + 20 minutes of continuous flow.'))
    st.write(t('**Baseline:** alert after 60 minutes of continuous flow.'))
    st.info(t('The AI flags unusual usage for inspection; it does not confirm a leak.'))
    st.caption(t('All results use synthetic scenarios. Performance in a real building has not been measured.'))
    if st.button(t('Reset demo'),key='reset',width='stretch'):
        persist_current()
        st.session_state.pop('simulation',None)
        st.session_state['played_events'] = set()
        st.rerun()
    sound = st.toggle(t('Sound on new incident'),value=False,key='sound')
    st.caption(t('Your browser may require autoplay permission.'))

# Stable internal values preserve time mode and incidents when switching language.
if st.session_state.get('time_mode') not in (None,'live','demo'):
    old = st.session_state.pop('time_mode')
    st.session_state['time_mode'] = 'live' if old=='Jonli vaqt' else 'demo'
mode = st.radio(t('Time mode'),['live','demo'],format_func=lambda v:t('Live time' if v=='live' else 'Accelerated demo'),horizontal=True,key='time_mode')
live = mode=='live'
if 'simulation' not in st.session_state or st.session_state['simulation'].get('live',False)!=live:
    persist_current()
    st.session_state['simulation'] = new_live() if live else new_simulation()
    st.session_state['played_events'] = set()

ensure_apartments(st.session_state['simulation'],bundle)

# Also repair already-resolved incidents from sessions opened before this fix.
for old_event in st.session_state['simulation']['events']:
    if old_event['status'] == 'resolved':
        stop_demo_water(st.session_state['simulation'],old_event)
        restore_demo_connection(st.session_state['simulation'],old_event)

SCENARIOS = {'normal':'Normal','leak':'Leak','shower':'15-minute shower','offline':'Offline'}
STATUSES = {'new':'New','ack':'Acknowledged','resolved':'Resolved'}
def outcome_label(value):
    legacy = {'Sizish tasdiqlandi':'Leak confirmed','Oddiy foydalanish':'Normal usage',
              'Sababi aniqlanmadi':'Cause unknown','Aloqa tiklandi':'Connection restored',
              'Qurilma tekshiruvi kerak':'Device inspection required'}
    return t(OUTCOMES.get(value,legacy.get(value,value)))

def alarm():
    data = io.BytesIO()
    with wave.open(data,'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
        wav.writeframes(b''.join(struct.pack('<h',int(7000*math.sin(2*math.pi*700*i/16000))) for i in range(4800)))
    return data.getvalue()

def owner_contact(apartment,key,event=None,editable=False):
    with st.expander(t('Contact owner')):
        try:
            contact = get_contact(apartment)
        except (OSError,*DATABASE_ERRORS):
            st.error(t('Could not load owner contact. Check database permissions.')); return
        name = t('Demo resident {apt}',apt=apartment) if contact['is_demo'] and contact['name'] == f'Demo Resident {apartment}' else contact['name']
        st.text(t('Owner: {name}',name=name))
        st.text(t('Phone: {phone}',phone=contact['phone'] or '—'))
        st.text(t('Email: {email}',email=contact['email'] or '—'))
        subject = t('Water inspection — Apartment {apt}',apt=apartment)
        body = (t('Hello, building security would like to check unusual water usage in Apartment {apt}. Please contact the security desk.',apt=apartment)
                if event is None or event['kind']=='water' else
                t('Hello, the water meter connection in Apartment {apt} needs checking. Please contact the security desk.',apt=apartment))
        if event:
            body += '\n'+t('Incident #{id}, detected at {time}.',id=event['id'],time=clock_label(event['start']))
        call,mail = contact_links(contact,subject,body)
        a,b = st.columns(2)
        a.link_button(t('Call owner'),call or 'tel:',disabled=call is None,width='stretch')
        b.link_button(t('Draft email'),mail or 'mailto:',disabled=mail is None,width='stretch')
        st.caption(t('Opens your phone or email application. Nothing is sent automatically.'))
        st.text(body)
        if editable:
            if st.session_state.pop(key+'_saved',False):
                st.success(t('Contact saved.'))
            with st.form(key+'_edit'):
                st.caption(t('Owner contacts are saved in the configured database and excluded from GitHub.'))
                owner_name = st.text_input(t('Owner name'),value=contact['name'],max_chars=80,key=key+'_name')
                phone = st.text_input(t('Phone number'),value=contact['phone'],max_chars=30,key=key+'_phone')
                email = st.text_input(t('Email address'),value=contact['email'],max_chars=254,key=key+'_email')
                demo = st.checkbox(t('Sample contact (disable calling and email)'),value=bool(contact['is_demo']),key=key+'_demo')
                if st.form_submit_button(t('Save contact')):
                    try:
                        save_contact(apartment,owner_name,phone,email,is_demo=demo)
                    except ValueError:
                        st.error(t('Enter an owner name and valid phone/email, or leave unused contact fields blank.'))
                    except (OSError,*DATABASE_ERRORS):
                        st.error(t('Could not save owner contact. Check database permissions.'))
                    else:
                        st.session_state[key+'_saved'] = True
                        st.rerun()


def incident_start_label(event):
    if event.get('started_at'):
        started = datetime.fromisoformat(event['started_at'])
        if started.tzinfo is not None:
            started = started.astimezone(LOCAL_TZ)
        return started.strftime('%Y-%m-%d %H:%M')
    return t('Date unavailable')+' • '+clock_label(event['start'])


def explain_incident(event):
    st.markdown('**'+t('Why this alert?')+'**')
    if event['kind'] == 'offline':
        st.write(t('The sensor connection was lost. Water usage cannot be assessed without readings.'))
        st.caption(t('Recommended: check the sensor power and network connection.'))
    else:
        st.write(t('At detection, water had flowed continuously for {minutes} minutes at {flow} L/min.',
            minutes=event['duration'],flow=f"{event['flow']:.2f}"))
        st.write(t('The model flagged unusual usage after at least 20 minutes of continuous flow. This does not confirm a leak.'))
        st.caption(t('Recommended: contact the owner to check whether water is being used.'))


def remember_inspection_draft(event_id,field,widget_key):
    sim = st.session_state['simulation']
    draft = sim.setdefault('inspection_drafts',{}).setdefault(event_id,{})
    draft[field] = st.session_state[widget_key]


@st.fragment(run_every='2s')
def monitor():
    sim = st.session_state['simulation']
    if live:
        sync_live(sim,bundle)
    elif not sim['last_snapshot']:
        advance(sim,bundle,steps=1)
    st.subheader(t('Security dashboard — Building A'))
    c1,c2,c3 = st.columns([1,1,2])
    if c1.button(t('⏸ Pause' if sim['running'] else '▶ Start automatically'),key='play',width='stretch'):
        set_monitoring_state(sim,bundle,not sim['running'])
        sim['last_tick'] = time.monotonic()
    step = c2.button(t('+15 minutes'),key='step',width='stretch',disabled=live or sim['minute']>=1439)
    if step:
        advance(sim,bundle,15)
    elif not live and sim['running'] and time.monotonic()-sim.get('last_tick',0)>=1.8:
        advance(sim,bundle,5); sim['last_tick'] = time.monotonic()
    if live:
        st.caption(t('Local time: {now} • Asia/Seoul (UTC+9) • Last reading: {reading} • {status}',
            now=local_now().strftime('%Y-%m-%d %H:%M:%S'),reading=clock_label(sim['minute']),
            status=t('Live: one reading per minute' if sim['running'] else 'Monitoring paused')))
        c3.caption(t('Live time: 1 minute = 1 real minute. Use demo mode for a quick test.'))
    else:
        st.caption(t('Simulation time: {time} • 1 reading = 1 virtual minute • Auto: 2 seconds = 5 virtual minutes',time=clock_label(sim['minute'])))
        if sim['minute']>=1439:
            c3.info(t('The day has ended. Use Reset demo to start again.'))
        else:
            c3.caption(t('Try: Apartment 03 → Start leak → click +15 minutes twice.'))
    persist_current()
    if st.session_state.pop('storage_conflict_notice',False):
        st.warning(t('Another window updated this incident. The saved result and notes were kept; your conflicting update was not applied.'))
    snap = sim['last_snapshot']
    offline = sum(s['offline'] for s in snap.values())
    active_water = {e['apartment'] for e in sim['events']
                    if e['kind']=='water' and e['active'] and e['status']!='resolved'}
    pending = [e for e in sim['events'] if e['status']!='resolved']
    a,b,c,d = st.columns(4)
    a.metric(t('Apartments'),len(APARTMENTS))
    b.metric(t('Normal'),len(APARTMENTS)-offline-len(active_water))
    c.metric(t('Water inspections'),len(active_water))
    d.metric(t('Offline'),offline)
    for row_start in range(0,len(APARTMENTS),5):
        for col,apt in zip(st.columns(5),APARTMENTS[row_start:row_start+5]):
            reading = snap[apt]
            with col:
                with st.container(border=True,key='apartment_card_'+apt):
                    st.markdown('**'+t('Apartment {apt}',apt=apt)+'**')
                    if reading['offline']: st.error(t('No connection'))
                    elif apt in active_water: st.warning(t('Inspection needed'))
                    else: st.success(t('Normal'))
                    st.caption(t('No reading') if reading['offline'] else f"{reading['flow']:.2f} L/min")
    st.divider()
    left,right = st.columns([1.5,1],gap='large')
    with left:
        apt = st.selectbox(t('Select apartment'),APARTMENTS,index=2,key='chosen_apartment')
        st.caption(t('Current scenario: {scenario}',scenario=t(SCENARIOS[sim['modes'][apt]])))
        owner_contact(apt,'owner_'+apt,editable=True)
        chart_slot = st.container()
        controls = st.columns(2)
        for column,label,value in [(0,'💧 Start leak','leak'),(1,'🚿 Shower — 15 minutes','shower'),
                                   (0,'📡 Disconnect sensor','offline'),(1,'✓ Restore normal','normal')]:
            if controls[column].button(t(label),key='scenario_'+value,width='stretch'):
                change_scenario(sim,bundle,apt,value); persist_current(); st.rerun()
        st.caption(t('Changes apply from the next reading. Leak: +0.7 L/min. Shower: 7 L/min for 15 minutes, then ends automatically.'))
        frame = sim['frames'][apt].iloc[:sim['minute']+1].tail(180).copy()
        origin = sim['origin'].replace(tzinfo=None) if live else pd.Timestamp('2026-01-01')
        times = origin+pd.to_timedelta(frame.minute,unit='m')
        frame['time_label'] = times.dt.strftime('%H:%M')
        max_flow = frame.flow.max()
        upper = max(1.0,float(max_flow)*1.15) if pd.notna(max_flow) else 1.0
        chart = alt.Chart(frame).mark_line(color='#008e91',strokeWidth=3,point={'filled':True,'size':12}).encode(
            x=alt.X('time_label:O',title=t('Time'),sort=None,
                axis=alt.Axis(values=frame.time_label.tolist()[::30]+[frame.time_label.iloc[-1]],labelAngle=0)),
            y=alt.Y('flow:Q',title=t('Water flow (L/min)'),scale=alt.Scale(domain=[-0.05,upper])),
            tooltip=[alt.Tooltip('time_label:O',title=t('Time')),alt.Tooltip('flow:Q',title='L/min',format='.2f')]
        ).properties(height=260)
        with chart_slot:
            st.altair_chart(chart,width='stretch')
            if frame.flow.notna().sum()==0:
                st.warning(t('No sensor readings in this period. Restore the connection to see new data.'))
            elif frame.flow.fillna(0).max()==0:
                st.info(t('Water flow is 0 L/min. The flat line is valid data, not a missing chart.'))
            if not live and not sim['running']:
                st.caption(t('Demo paused. Press Start automatically or +15 minutes to update the chart.'))
        st.caption(t('Chart: last 180 minutes, local time (UTC+9).' if live else 'Chart: last 180 virtual minutes.')+' '+
                   t('Usage is synthetic; no real meter is connected. No readings during a connection loss.'))
        reading = snap[apt]
        st.write(t('**Continuous flow:** {minutes} minutes',minutes=reading['duration']))
        st.write(t('**60-minute baseline:** {status}',status=t('Alert' if reading['baseline'] else 'Quiet')))
        st.caption(t('The AI score is not a probability. One incident stays active until flow stops, avoiding duplicate alerts from score fluctuations.'))
    with right:
        st.subheader(t('Alerts'))
        st.caption(t('{count} unresolved incidents',count=len(pending)))
        if not pending: st.success(t('No incidents waiting for inspection.'))
        # Oldest first: new alerts do not move an existing incident to a
        # different page. Every pending incident remains reachable.
        ordered = sorted(pending,key=lambda event:event['id'])
        page_size = 5
        page_count = max(1,(len(ordered)+page_size-1)//page_size)
        page = max(1,min(st.session_state.get('alert_page',1),page_count))
        st.session_state['alert_page'] = page
        if page_count>1:
            page = st.selectbox(t('Alert page'),list(range(1,page_count+1)),key='alert_page',
                format_func=lambda n:t('Page {page} of {total}',page=n,total=page_count))
        start = (page-1)*page_size
        if ordered:
            st.caption(t('Showing {first}–{last} of {total} alerts · oldest first',
                first=start+1,last=min(start+page_size,len(ordered)),total=len(ordered)))
        for event in ordered[start:start+page_size]:
            with st.container(border=True):
                st.markdown(f"**#{event['id']} • "+t('Apartment {apt}',apt=event['apartment'])+'**')
                st.warning(t('Offline' if event['kind']=='offline' else 'Possible water leak'))
                st.caption(t('Started: {time} • {status}',time=incident_start_label(event),
                    status=t('Signal ongoing' if event['active'] else 'Signal ended; inspection pending')))
                explain_incident(event)
                owner_contact(event['apartment'],f"contact_{event['id']}",event=event)
                if event['status']=='new':
                    if st.button(t('Acknowledge'),key=f"ack_{event['id']}",width='stretch'):
                        if live: sync_live(sim,bundle,force=True)
                        update_event(sim,event['id'],'ack'); persist_current(); st.rerun()
                else: st.caption(t('Inspection in progress' if event['outcome']=='unknown' else '✓ Acknowledged by security — inspection needed'))
                with st.expander(t('Complete inspection')):
                    if event['kind']=='water':
                        st.caption(t('Leak fixed stops the simulated leak. Normal usage completes inspection without stopping flow. Cause unknown keeps inspection open.'))
                    else:
                        st.caption(t('Connection restored reconnects this demo sensor immediately. Device inspection required leaves it offline.'))
                    options = ['leak_fixed','normal_usage','unknown'] if event['kind']=='water' else ['connection_restored','device_check']
                    # Discard legacy translated widget values, keeping saved event data.
                    outcome_key = f"out_{event['id']}"
                    if outcome_key in st.session_state and st.session_state[outcome_key] not in options:
                        del st.session_state[outcome_key]
                    draft = sim.setdefault('inspection_drafts',{}).get(event['id'],{})
                    outcome = st.selectbox(t('Outcome'),options,format_func=outcome_label,key=outcome_key,
                        index=options.index(draft.get('outcome')) if draft.get('outcome') in options else 0,
                        on_change=remember_inspection_draft,args=(event['id'],'outcome',outcome_key))
                    note_key = f"note_{event['id']}"
                    note = st.text_input(t('Staff note'),key=note_key,max_chars=1000,value=draft.get('note',''),
                        on_change=remember_inspection_draft,args=(event['id'],'note',note_key))
                    if st.button(t('Save inspection' if outcome=='unknown' else 'Resolve'),key=f"done_{event['id']}"):
                        if live: sync_live(sim,bundle,force=True)
                        update_event(sim,event['id'],'resolve',outcome,note); persist_current(); st.rerun()
        new_ids = {e['id'] for e in pending if e['status']=='new'}
        played = st.session_state.setdefault('played_events',set())
        if sound and new_ids-played: st.audio(alarm(),format='audio/wav',autoplay=True)
        st.session_state['played_events'] = played|new_ids
    with st.expander(t('Incident history')):
        st.caption(t('Saved incidents remain after restarting the app. Previous sessions contain historical signals, not current sensor readings.'))
        try:
            saved = load_incidents()
        except (OSError,*DATABASE_ERRORS):
            st.error(t('Could not load saved history. Check folder permissions and retry.'))
            return
        records = [{t('Session'):e['run_id'][:8],t('ID'):e['id'],t('Apartment'):e['apartment'],
            t('Mode'):t('Live time' if e['run_mode']=='live' else 'Accelerated demo'),
            t('Type'):t('Offline' if e['kind']=='offline' else 'Possible water leak'),
            t('Started'):incident_start_label(e),t('Status'):t(STATUSES[e['status']]),
            t('Outcome'):outcome_label(e['outcome']),t('Note'):e['note'],
            t('Last saved'):datetime.fromisoformat(e['updated_at']).astimezone(LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S')}
            for e in saved]
        if records:
            table = pd.DataFrame(records)
            st.dataframe(table,hide_index=True,width='stretch')
            st.download_button(t('Download saved history as CSV'),table.to_csv(index=False).encode('utf-8-sig'),
                'saved-water-incidents.csv','text/csv',key='download_saved')
        else:
            st.info(t('No saved incidents yet.'))
        previous = [e for e in saved if e['run_id']!=sim['_run_id'] and e['status']!='resolved']
        if previous:
            st.subheader(t('Pending inspections from previous sessions'))
            choices = {f"{e['run_id']}:{e['id']}":e for e in previous}
            chosen = st.selectbox(t('Saved incident'),list(choices),key='saved_incident',
                format_func=lambda k:choices[k]['run_id'][:8]+f" / #{choices[k]['id']} / "+t('Apartment {apt}',apt=choices[k]['apartment']))
            event = choices[chosen]
            st.caption(t('Last known signal only. Completing this inspection does not change the current simulation.'))
            explain_incident(event)
            prefix = f"saved_{event['run_id']}_{event['id']}"
            owner_contact(event['apartment'],prefix+'_contact',event=event)
            if event['status']=='new' and st.button(t('Acknowledge'),key=prefix+'_ack'):
                try:
                    update_saved_incident(event['run_id'],event['id'],'ack')
                except (OSError,*DATABASE_ERRORS,ValueError):
                    st.error(t('Could not update the saved incident. Refresh and retry.')); st.stop()
                st.rerun()
            options = ['leak_fixed','normal_usage','unknown'] if event['kind']=='water' else ['connection_restored','device_check']
            outcome = st.selectbox(t('Outcome'),options,format_func=outcome_label,key=prefix+'_outcome')
            note = st.text_input(t('Staff note'),value=event['note'],max_chars=1000,key=prefix+'_note')
            if st.button(t('Save inspection' if outcome=='unknown' else 'Resolve'),key=prefix+'_resolve'):
                try:
                    update_saved_incident(event['run_id'],event['id'],'resolve',outcome,note)
                except (OSError,*DATABASE_ERRORS,ValueError):
                    st.error(t('Could not update the saved incident. Refresh and retry.')); st.stop()
                st.rerun()

dashboard_tab,results_tab = st.tabs([t('Dashboard'),t('Model results')])
with dashboard_tab:
    monitor()
with results_tab:
    st.header(t('Model results'))
    st.caption(t('Fixed test results — demo actions do not change these numbers.'))
    ai = metrics['hybrid']
    a,b,c,d = st.columns(4)
    a.metric(t('Leak days detected'),f"{ai['leak_days_detected']}/{ai['leak_days']}")
    b.metric(t('Leak days missed'),ai['leak_days']-ai['leak_days_detected'])
    c.metric(t('Normal days with alerts'),f"{ai['normal_days_alerted']}/{ai['normal_days']}")
    d.metric(t('Median delay (min)'),ai['median_delay_minutes'])
    st.info(t('All leak days were detected, but some leak minutes were missed. The 20-minute rule performed slightly better than AI on this test.'))
    st.subheader(t('Minute-level predictions'))
    normal_correct,false_alert,missed,detected = [n for row in ai['confusion_matrix'] for n in row]
    counts = pd.DataFrame({t('Prediction result'):[t('Normal minutes correctly identified'),t('Normal minutes flagged'),t('Leak minutes missed'),t('Leak minutes detected')],t('Minutes'):[normal_correct,false_alert,missed,detected]})
    st.dataframe(counts,hide_index=True,width='stretch')
    st.caption(t('Day-level detection means at least one leak minute was flagged; it does not mean every leak minute was detected.'))
    st.subheader(t('Does the model outperform simple rules?'))
    st.caption(t('Tested on 24 separate synthetic household-days only. This is not evidence of real-building performance.'))
    rows = []
    for label,key in [('AI + 20 minutes','hybrid'),('20-minute rule','rule20'),('60-minute rule','baseline')]:
        result = metrics[key]; report = result['classification']['leak']
        rows.append({t('Method'):t(label),t('Precision'):f"{report['precision']:.1%}",
            t('Recall'):f"{report['recall']:.1%}",t('F1'):f"{report['f1-score']:.1%}",
            t('Leak days detected'):f"{result['leak_days_detected']}/{result['leak_days']}",
            t('Normal days with alerts'):f"{result['normal_days_alerted']}/{result['normal_days']}",
            t('Median delay (min)'):result['median_delay_minutes']})
    st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch')
    with st.expander(t('Training and limitations')):
        for paragraph in [
            'Isolation Forest was trained on 60 independent synthetic days without leaks. The threshold was selected on 24 validation days and evaluated on 24 separate test days. Demo data belongs to none of these sets.',
            'The score threshold is at least the 95th percentile of normal training scores. Comparison with the 20-minute rule tests whether the model adds value; AI need not win every metric.',
            'Precision and recall are measured per minute. A leak day is detected if at least one leak minute is flagged. Delay is calculated only for detected incidents.',
            'Features include current flow, 15/60-minute averages, variability, continuous-flow duration, and time of day. This is a hybrid of a model and rules.']:
            st.write(t(paragraph))
        st.warning(t('Long normal usage can trigger alerts. Small or intermittent leaks may be missed. This prototype does not shut off water, send SMS, or make decisions for security staff. Real-world validation and permissions are future work.'))
