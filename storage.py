"""SQLite incident archive. No model binaries or telemetry frames are serialized."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import uuid


def database_path():
    override = os.environ.get('WATER_MONITOR_DB')
    return Path(override) if override else Path(__file__).resolve().parent/'data/water-monitor.sqlite3'


def utc_now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connection(path=None):
    path = Path(path) if path else database_path()
    path.parent.mkdir(parents=True,exist_ok=True)
    db = sqlite3.connect(path,timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                mode TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS incidents (
                run_id TEXT NOT NULL REFERENCES runs(id),
                local_id INTEGER NOT NULL,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(run_id,local_id)
            );
            CREATE TABLE IF NOT EXISTS activity (
                run_id TEXT NOT NULL REFERENCES runs(id),
                sequence INTEGER NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY(run_id,sequence)
            );
        ''')
        with db:
            yield db
    finally:
        db.close()


def save_simulation(sim,path=None):
    """Save a full incident snapshot atomically; repeated calls are idempotent.

    Each demo reset/time-mode change gets a separate run ID, so local incident
    #1 in one run can never overwrite local incident #1 in another run.
    """
    run_id = sim.setdefault('_run_id',uuid.uuid4().hex)
    created = sim.setdefault('_created_at',utc_now())
    payload = json.dumps({'events':sim['events'],'history':sim['history']},ensure_ascii=False,sort_keys=True)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    target = Path(path) if path else database_path()
    if sim.get('_saved_digest') == digest and sim.get('_saved_path') == str(target) and target.exists():
        return run_id
    now = utc_now()
    with connection(target) as db:
        db.execute('INSERT OR IGNORE INTO runs VALUES(?,?,?)',
                   (run_id,'live' if sim.get('live') else 'demo',created))
        for event in sim['events']:
            db.execute('''INSERT INTO incidents VALUES(?,?,?,?)
                ON CONFLICT(run_id,local_id) DO UPDATE SET
                payload=excluded.payload,updated_at=excluded.updated_at''',
                (run_id,event['id'],json.dumps(event,ensure_ascii=False),now))
        for seq,entry in enumerate(sim['history']):
            db.execute('INSERT OR IGNORE INTO activity VALUES(?,?,?)',
                       (run_id,seq,json.dumps(entry,ensure_ascii=False)))
    # Only mark saved after the transaction commits successfully.
    sim['_saved_digest'] = digest
    sim['_saved_path'] = str(target)
    return run_id


def load_incidents(path=None,exclude_run=None):
    with connection(path) as db:
        rows = db.execute('''SELECT i.*,r.mode,r.created_at FROM incidents i
            JOIN runs r ON r.id=i.run_id
            WHERE (? IS NULL OR i.run_id != ?)
            ORDER BY r.created_at DESC,i.local_id DESC''',(exclude_run,exclude_run)).fetchall()
    records = []
    for row in rows:
        records.append({**json.loads(row['payload']),'run_id':row['run_id'],
                        'run_mode':row['mode'],'created_at':row['created_at'],
                        'updated_at':row['updated_at']})
    return records


def load_activity(path=None):
    with connection(path) as db:
        rows = db.execute('SELECT run_id,payload FROM activity ORDER BY rowid').fetchall()
    return [{'run_id':row['run_id'],**json.loads(row['payload'])} for row in rows]


def update_saved_incident(run_id,local_id,action,outcome='',note='',path=None):
    """Update archived workflow without inventing telemetry for a closed session."""
    with connection(path) as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT payload FROM incidents WHERE run_id=? AND local_id=?',
                         (run_id,local_id)).fetchone()
        if row is None:
            raise ValueError('Incident not found')
        event = json.loads(row['payload'])
        if action=='ack' and event['status']=='new':
            event['status'] = 'ack'
        elif action=='resolve' and event['status'] in ('new','ack') and outcome:
            event.update(status='resolved',outcome=outcome,note=note[:1000])
        else:
            raise ValueError('Invalid incident transition')
        # active is the last known signal state, not a live measurement.
        db.execute('UPDATE incidents SET payload=?,updated_at=? WHERE run_id=? AND local_id=?',
                   (json.dumps(event,ensure_ascii=False),utc_now(),run_id,local_id))
        seq = db.execute('SELECT COALESCE(MAX(sequence),-1)+1 FROM activity WHERE run_id=?',
                         (run_id,)).fetchone()[0]
        db.execute('INSERT INTO activity VALUES(?,?,?)',(run_id,seq,json.dumps({
            'type':'event','time':utc_now(),'apartment':event['apartment'],
            'event_id':local_id,'action':action,'outcome':outcome,'note':note[:1000],
            'source':'archive'},ensure_ascii=False)))
