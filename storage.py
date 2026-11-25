"""Persistent incident archive (SQLite or PostgreSQL). No model binaries or telemetry frames are serialized."""
from datetime import datetime, timezone, timedelta
import json
import uuid


from database import connection, database_path, DATABASE_ERRORS


def utc_now():
    return datetime.now(timezone.utc).isoformat()


WORKFLOW_FIELDS = ('status','outcome','note')


def workflow(event):
    return {key:event[key] for key in WORKFLOW_FIELDS}


def save_simulation(sim,path=None):
    """Merge telemetry with version-checked workflow under a write lock.

    Compare each workflow against the last value this window saved/read. If
    another window changed it, that saved version wins over a stale snapshot.
    Reconcile the local view after commit, even if there were no local changes.
    """
    run_id = sim.setdefault('_run_id',uuid.uuid4().hex)
    created = sim.setdefault('_created_at',utc_now())
    baseline = sim.get('_saved_workflows',{})
    reconciled,conflicts = {},[]
    rejected = set(sim.get('_rejected_history',[]))
    with connection(path) as db:
        db.begin_write()
        db.execute('INSERT INTO runs VALUES(?,?,?) ON CONFLICT DO NOTHING',
                   (run_id,'live' if sim.get('live') else 'demo',created))
        for event in sim['events']:
            if 'started_at' not in event:
                # Demo timestamps use the same virtual date as its chart.
                origin = sim.get('origin') if sim.get('live') else datetime(2026,1,1)
                if origin is not None:
                    event['started_at'] = (origin+timedelta(minutes=event['start'])).isoformat()
            row = db.execute('SELECT payload FROM incidents WHERE run_id=? AND local_id=?',
                             (run_id,event['id'])).fetchone()
            merged = dict(event)
            if row:
                remote = workflow(json.loads(row['payload']))
                local = workflow(event)
                previous = baseline.get(event['id'])
                if remote != previous:
                    merged.update(remote)
                    if previous is not None and local != previous and local != remote:
                        conflicts.append(event['id'])
            reconciled[event['id']] = workflow(merged)
            encoded = json.dumps(merged,ensure_ascii=False)
            if row is None:
                db.execute('INSERT INTO incidents VALUES(?,?,?,?)',
                           (run_id,event['id'],encoded,utc_now()))
            elif encoded != row['payload']:
                db.execute('UPDATE incidents SET payload=?,updated_at=? WHERE run_id=? AND local_id=?',
                           (encoded,utc_now(),run_id,event['id']))
        for seq,entry in enumerate(sim['history']):
            # A losing workflow action must not be recorded as successful.
            if entry.get('type')=='event' and entry.get('event_id') in conflicts:
                recorded = db.execute("SELECT 1 FROM activity_stream WHERE run_id=? AND source='simulation' AND source_sequence=?",
                                      (run_id,seq)).fetchone()
                if not recorded:
                    rejected.add(seq)
            if seq in rejected:
                continue
            db.execute("""INSERT INTO activity_stream
                (run_id,source,source_sequence,payload) VALUES(?,?,?,?) ON CONFLICT DO NOTHING""",
                (run_id,'simulation',seq,json.dumps(entry,ensure_ascii=False)))
    for event in sim['events']:
        event.update(reconciled[event['id']])
    sim['_saved_workflows'] = reconciled
    sim['_workflow_conflicts'] = conflicts
    sim['_rejected_history'] = sorted(rejected)
    return run_id


def load_incidents(path=None,exclude_run=None):
    with connection(path) as db:
        rows = db.execute('''SELECT i.*,r.mode,r.created_at FROM incidents i
            JOIN runs r ON r.id=i.run_id
            WHERE (CAST(? AS TEXT) IS NULL OR i.run_id != ?)
            ORDER BY r.created_at DESC,i.local_id DESC''',(exclude_run,exclude_run)).fetchall()
    records = []
    for row in rows:
        records.append({**json.loads(row['payload']),'run_id':row['run_id'],
                        'run_mode':row['mode'],'created_at':row['created_at'],
                        'updated_at':row['updated_at']})
    return records


def load_activity(path=None):
    with connection(path) as db:
        rows = db.execute('SELECT run_id,payload FROM activity_stream ORDER BY id').fetchall()
    return [{'run_id':row['run_id'],**json.loads(row['payload'])} for row in rows]


def update_saved_incident(run_id,local_id,action,outcome='',note='',path=None):
    """Update archived workflow without inventing telemetry for a closed session."""
    with connection(path) as db:
        db.begin_write()
        row = db.execute('SELECT payload FROM incidents WHERE run_id=? AND local_id=?',
                         (run_id,local_id)).fetchone()
        if row is None:
            raise ValueError('Incident not found')
        event = json.loads(row['payload'])
        if action=='ack' and event['status']=='new':
            event['status'] = 'ack'
        elif action=='resolve' and event['status'] in ('new','ack') and outcome:
            event.update(status='ack' if event['kind']=='water' and outcome=='unknown' else 'resolved',outcome=outcome,note=note[:1000])
        else:
            raise ValueError('Invalid incident transition')
        # active is the last known signal state, not a live measurement.
        db.execute('UPDATE incidents SET payload=?,updated_at=? WHERE run_id=? AND local_id=?',
                   (json.dumps(event,ensure_ascii=False),utc_now(),run_id,local_id))
        seq = db.execute("SELECT COALESCE(MAX(source_sequence),-1)+1 AS next_sequence FROM activity_stream WHERE run_id=? AND source='archive'",
                         (run_id,)).fetchone()['next_sequence']
        db.execute('INSERT INTO activity_stream (run_id,source,source_sequence,payload) VALUES(?,?,?,?)',(run_id,'archive',seq,json.dumps({
            'type':'event','time':utc_now(),'apartment':event['apartment'],
            'event_id':local_id,'action':action,'outcome':outcome,'note':note[:1000],
            'source':'archive'},ensure_ascii=False)))
