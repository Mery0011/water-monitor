"""Integration checks against a disposable PostgreSQL database ending in _test.

Set WATER_MONITOR_TEST_DATABASE_URL; these checks clear only its water_monitor schema.
Never point this script at a deployed app database.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import os
import unittest
from unittest.mock import patch
import joblib
import psycopg
from psycopg.conninfo import conninfo_to_dict
from database import connection, database_url, postgres_options
from contacts import get_contact, save_contact
from engine import new_simulation, set_mode, advance, update_event
from storage import save_simulation, load_incidents, load_activity, update_saved_incident

URL = os.environ.get('WATER_MONITOR_TEST_DATABASE_URL','')


class DatabaseConfigurationTests(unittest.TestCase):
    def test_cloud_failure_never_falls_back_to_sqlite(self):
        with patch.dict(os.environ,{'WATER_MONITOR_DATABASE_URL':'postgresql://invalid/db','WATER_MONITOR_DB':''}), \
             patch('database.initialize_postgres',side_effect=psycopg.OperationalError('unavailable')), \
             patch('database.sqlite3.connect') as local:
            with self.assertRaises(psycopg.OperationalError):
                with connection():
                    pass
            local.assert_not_called()

    def test_explicit_path_isolates_local_database_from_cloud(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory, \
             patch.dict(os.environ,{'WATER_MONITOR_DATABASE_URL':'postgresql://invalid/db'}), \
             patch('database.initialize_postgres') as remote:
            with connection(Path(directory)/'test.sqlite3') as db:
                self.assertIsNone(db.execute('SELECT * FROM contacts').fetchone())
            remote.assert_not_called()

    def test_streamlit_secrets_and_tls_default(self):
        with patch.dict(os.environ,{'WATER_MONITOR_DATABASE_URL':''}), \
             patch('streamlit.secrets',{'WATER_MONITOR_DATABASE_URL':'postgresql://user@host/db'}):
            self.assertEqual(database_url(),'postgresql://user@host/db')
        self.assertEqual(postgres_options('postgresql://user@host/db')['sslmode'],'require')


@unittest.skipUnless(URL,'Set WATER_MONITOR_TEST_DATABASE_URL to a disposable database ending in _test')
class PostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not conninfo_to_dict(URL).get('dbname','').endswith('_test'):
            raise RuntimeError('Refusing to clear a database whose name does not end in _test')
        cls.bundle = joblib.load('artifacts/water_model.joblib')

    def setUp(self):
        env = patch.dict(os.environ,{'WATER_MONITOR_DATABASE_URL':URL,'WATER_MONITOR_DB':''})
        env.start(); self.addCleanup(env.stop)
        with connection() as db:
            db.execute('TRUNCATE activity_stream, activity, incidents, runs, contacts RESTART IDENTITY CASCADE')

    def incident(self):
        sim = new_simulation()
        set_mode(sim,'03','leak'); advance(sim,self.bundle,30)
        save_simulation(sim)
        return sim

    def test_persistence_contacts_and_exclusion(self):
        sim = self.incident()
        self.assertEqual(len(load_incidents()),1)
        self.assertEqual(load_incidents(exclude_run=sim['_run_id']),[])
        self.assertIn('started_at',load_incidents()[0])
        self.assertTrue(get_contact('03')['is_demo'])
        save_contact('03','Test Owner','+821012345678','test@example.invalid',False)
        self.assertEqual(get_contact('03')['name'],'Test Owner')
        self.assertTrue(load_activity())
        # A fresh app session reads the same external history.
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_file('app.py',default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertTrue(any('Session' in x.value.columns and len(x.value)==1 for x in app.dataframe))

    def test_rollback_is_atomic(self):
        with self.assertRaises(RuntimeError):
            with connection() as db:
                db.execute("INSERT INTO runs VALUES(?,?,?)",('rollback','demo','test'))
                raise RuntimeError('simulate failure')
        with connection() as db:
            self.assertIsNone(db.execute('SELECT * FROM runs WHERE id=?',('rollback',)).fetchone())

    def test_stale_workflows_and_concurrent_audit_sequences(self):
        sim = self.incident()
        stale = deepcopy(sim)
        update_saved_incident(sim['_run_id'],1,'resolve','leak_fixed','Remote repair')
        update_event(stale,1,'resolve','unknown','Stale note')
        save_simulation(stale)
        self.assertEqual(load_incidents()[0]['note'],'Remote repair')
        self.assertEqual(stale['events'][0]['status'],'resolved')
        sim = self.incident()
        def inspect(index):
            update_saved_incident(sim['_run_id'],1,'resolve','unknown',str(index))
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(inspect,range(4)))
        actions = [a for a in load_activity() if a['run_id']==sim['_run_id'] and a.get('source')=='archive']
        self.assertEqual(len(actions),4)
        self.assertEqual(load_incidents()[0]['status'],'ack')


if __name__ == '__main__':
    unittest.main()
