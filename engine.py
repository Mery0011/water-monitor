"""Synthetic water telemetry and streaming detection for a portfolio prototype."""
import numpy as np
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo('Asia/Seoul')

FEATURES = ['flow', 'mean15', 'mean60', 'std15', 'continuous', 'hour_sin', 'hour_cos']
APARTMENTS = [f'{number:02d}' for number in range(1, 16)]


def make_day(seed, leak=False):
    """One independent household-day. Litres per minute, sampled once/minute.

    These are illustrative assumptions, NOT measured household distributions.
    """
    rng = np.random.default_rng(seed)
    flow = np.zeros(1440)
    profile = rng.uniform(0.7, 1.3)
    for _ in range(int(rng.integers(14, 32))):
        start = int(rng.integers(360, 1410))
        length = int(rng.integers(1, 5))
        flow[start:start + length] += rng.uniform(0.5, 4) * profile
    # Showers, washing, and an occasional long legitimate use.
    for start in [int(rng.integers(390, 600)), int(rng.integers(1080, 1320))]:
        length = int(rng.integers(6, 24))
        flow[start:start + length] += rng.uniform(4, 10) * profile
    for _ in range(int(rng.integers(1, 4))):
        start = int(rng.integers(480, 1350))
        for offset in range(0, 50, 10):
            flow[start + offset:start + offset + 3] += rng.uniform(2, 5)
    if rng.random() < 0.35:
        start = int(rng.integers(600, 1100))
        length = int(rng.integers(25, 81))
        flow[start:start + length] += rng.uniform(1.5, 7)
    flow = np.maximum(0, flow * rng.normal(1, 0.04, 1440))
    truth = np.zeros(1440, dtype=int)
    if leak:
        start = int(rng.integers(30, 1180))
        length = int(rng.integers(90, 241))
        # The test contains varied small leaks and overlap with normal use.
        flow[start:start + length] += rng.uniform(0.15, 1.6)
        truth[start:start + length] = 1
    return pd.DataFrame({'minute':np.arange(1440), 'flow':flow, 'truth':truth})


def features(frame):
    flow = frame.flow.fillna(0).clip(lower=0)
    active = flow > 0.05
    duration = active.groupby((~active).cumsum()).cumsum()
    angle = frame.minute.to_numpy() / 1440 * 2 * np.pi
    return pd.DataFrame({
        'flow':flow, 'mean15':flow.rolling(15, min_periods=1).mean(),
        'mean60':flow.rolling(60, min_periods=1).mean(),
        'std15':flow.rolling(15, min_periods=1).std().fillna(0),
        'continuous':duration, 'hour_sin':np.sin(angle), 'hour_cos':np.cos(angle),
    })[FEATURES]


def predict(frame, bundle):
    x = features(frame)
    scores = -bundle['model'].score_samples(x)
    # A hybrid: learned anomaly score + a documented persistence rule.
    ai = (scores >= bundle['threshold']) & (x.continuous.to_numpy() >= 20)
    baseline = x.continuous.to_numpy() >= 60
    return x, scores, ai, baseline


def clock_label(minute):
    return f'{(minute // 60) % 24:02d}:{minute % 60:02d}'


def local_now():
    return datetime.now(LOCAL_TZ)


def new_live(now=None):
    now = now or local_now()
    sim = new_simulation()
    sim.update(live=True, minute=now.hour*60+now.minute-1, running=True,
               origin=now.replace(hour=0,minute=0,second=0,microsecond=0),
               last_live=now.replace(second=0,microsecond=0))
    return sim


def sync_live(sim, bundle, now=None, force=False):
    now = now or local_now()
    target = int((now.replace(second=0,microsecond=0)-sim['origin']).total_seconds()//60)
    if not sim['last_snapshot'] or ((sim['running'] or force) and target > sim['minute']):
        advance(sim,bundle,max(0,target-sim['minute']))
        sim['last_live'] = now.replace(second=0,microsecond=0)


def change_scenario(sim, bundle, apt, mode, now=None):
    """Finish elapsed readings under the OLD scenario before applying a new one."""
    if sim.get('live'):
        sync_live(sim,bundle,now=now,force=True)
    set_mode(sim,apt,mode)


def set_monitoring_state(sim, bundle, running, now=None):
    """Resume at the wall clock without backdating subsequent scenario changes."""
    if sim.get('live'):
        sync_live(sim,bundle,now=now,force=True)
    sim['running'] = running


def new_simulation():
    # Independent of all training, validation, and test seeds.
    frames = {apt:make_day(90000 + i) for i, apt in enumerate(APARTMENTS)}
    return {'minute':120, 'frames':frames, 'modes':{apt:'normal' for apt in APARTMENTS},
            'events':[], 'open_events':{}, 'serial':0, 'history':[], 'running':False,
            'mode_until':{}, 'last_snapshot':{}}


def set_mode(sim, apt, mode):
    sim['modes'][apt] = mode
    sim['mode_until'][apt] = sim['minute'] + 15 if mode == 'shower' else 1440
    sim['history'].append({'type':'scenario','time':clock_label(sim['minute']),
                          'apartment':apt,'mode':mode})


def advance(sim, bundle, steps=15):
    """Sequential one-minute readings; manual/auto stepping share this path."""
    end = sim['minute'] + steps if sim.get('live') else min(1439, sim['minute'] + steps)
    # Live monitoring continues through midnight rather than ending the demo day.
    for i,apt in enumerate(APARTMENTS):
        while len(sim['frames'][apt]) <= end:
            offset = len(sim['frames'][apt])
            extra = make_day(90000+i+100*(offset//1440))
            extra['minute'] += offset
            sim['frames'][apt] = pd.concat([sim['frames'][apt],extra],ignore_index=True)
    start = sim['minute'] + 1
    snapshots = {}
    for apt in APARTMENTS:
        frame = sim['frames'][apt]
        mode = sim['modes'][apt]
        indices = np.arange(start, end + 1)
        if mode == 'leak':
            frame.loc[indices, 'flow'] = frame.loc[indices, 'flow'] + 0.7
            frame.loc[indices, 'truth'] = 1
        elif mode == 'shower':
            shower_indices = indices[indices <= sim['mode_until'][apt]]
            frame.loc[shower_indices, 'flow'] = 7.0
            frame.loc[shower_indices, 'truth'] = 0
            if end >= sim['mode_until'][apt]:
                sim['modes'][apt] = 'normal'
        elif mode == 'offline':
            frame.loc[indices, 'flow'] = np.nan
            frame.loc[indices, 'truth'] = 0
        # Normal telemetry comes from an independent generated day.
        partial = frame.iloc[:end + 1]
        x, scores, ai, baseline = predict(partial, bundle)
        for minute in indices:
            offline = pd.isna(frame.loc[minute, 'flow'])
            # Keep one incident open until flow stops, even if score fluctuates.
            ongoing = (apt, 'water') in sim['open_events'] and x.loc[minute, 'continuous'] > 0
            kind = 'offline' if offline else ('water' if ai[minute] or ongoing else None)
            for existing_kind in ('water', 'offline'):
                key = (apt, existing_kind)
                event_id = sim['open_events'].get(key)
                if existing_kind != kind and event_id:
                    event = next(e for e in sim['events'] if e['id'] == event_id)
                    event['active'] = False
                    event['end'] = int(minute)
                    del sim['open_events'][key]
            if kind:
                key = (apt, kind)
                if key not in sim['open_events']:
                    sim['serial'] += 1
                    event = {'id':sim['serial'], 'apartment':apt, 'kind':kind,
                        'start':int(minute), 'end':None, 'active':True,
                        'status':'new', 'outcome':'', 'note':'',
                        'duration':int(x.loc[minute, 'continuous']),
                        'flow':0 if offline else float(frame.loc[minute, 'flow'])}
                    sim['events'].append(event)
                    sim['open_events'][key] = event['id']
        snapshots[apt] = {
            'offline':pd.isna(frame.loc[end, 'flow']), 'flow':float(frame.loc[end, 'flow']),
            'duration':int(x.loc[end, 'continuous']), 'anomaly':bool(ai[end]),
            'baseline':bool(baseline[end]), 'score':float(scores[end]),
        }
    sim['minute'] = end
    sim['last_snapshot'] = snapshots
    if end == 1439 and not sim.get('live'):
        sim['running'] = False


def update_event(sim, event_id, action, outcome='', note=''):
    event = next(e for e in sim['events'] if e['id'] == event_id)
    if action == 'ack' and event['status'] == 'new':
        event['status'] = 'ack'
    elif action == 'resolve' and event['status'] in ('new', 'ack') and outcome:
        event.update(status='resolved', outcome=outcome, note=note[:1000])
        stop_demo_water(sim,event)
        restore_demo_connection(sim,event)
    else:
        raise ValueError('Invalid event transition')
    sim['history'].append({'type':'event','time':clock_label(sim['minute']),
        'apartment':event['apartment'],'event_id':event_id,'action':action,
        'outcome':outcome,'note':note[:1000]})


def stop_demo_water(sim, event):
    """Simulate repair without changing earlier readings or the wall clock."""
    if event['kind'] != 'water' or not event['active']:
        return
    apt = event['apartment']
    set_mode(sim,apt,'normal')
    sim['frames'][apt].loc[sim['minute'],['flow','truth']] = [0.0,0]
    sim['open_events'].pop((apt,'water'),None)
    event.update(active=False,end=sim['minute'])
    if apt in sim['last_snapshot']:
        sim['last_snapshot'][apt].update(flow=0.0,duration=0,anomaly=False,baseline=False)


def restore_demo_connection(sim, event):
    """Apply a confirmed demo reconnection to its matching active incident."""
    if event['kind'] != 'offline' or not event['active'] or event['outcome'] not in ('connection_restored','Aloqa tiklandi'):
        return
    apt = event['apartment']
    if sim['open_events'].get((apt,'offline')) != event['id']:
        return
    set_mode(sim,apt,'normal')
    # Restore only the current sample, preserving earlier missing readings.
    minute = sim['minute']
    day,within_day = divmod(minute,1440)
    original = make_day(90000+APARTMENTS.index(apt)+100*day)
    flow = float(original.loc[within_day,'flow'])
    sim['frames'][apt].loc[minute,['flow','truth']] = [flow,0]
    sim['open_events'].pop((apt,'offline'))
    event.update(active=False,end=minute)
    if apt in sim['last_snapshot']:
        duration = int(features(sim['frames'][apt].iloc[:minute+1]).continuous.iloc[-1])
        sim['last_snapshot'][apt].update(offline=False,flow=flow,duration=duration,
                                         anomaly=False,baseline=False)


def ensure_apartments(sim, bundle):
    """Add new apartments to an existing session without discarding incidents."""
    added = False
    for index, apt in enumerate(APARTMENTS):
        if apt not in sim['frames']:
            sim['frames'][apt] = make_day(90000 + index)
            sim['modes'][apt] = 'normal'
            sim['mode_until'][apt] = 1440
            added = True
    if added:
        advance(sim, bundle, 0)
