import sqlite3
from contextlib import closing
import unittest
from unittest.mock import patch

from server import Recorder, Store
import test_server


class GroupCleanupTests(unittest.TestCase):
    setUp = test_server.HistoryTests.setUp
    tearDown = test_server.HistoryTests.tearDown

    def test_saved_groups_persist_and_edit_without_duplicates(self):
        self.store.record(100, [('s', 20, None), ('t', 30, None)], [('s', 'One', 'sensor'), ('t', 'Two', 'sensor')])
        identifier = self.store.save_group({'name': 'Chamber', 'sensors': ['s', 's']})
        reopened = Store(self.path)
        self.assertEqual(reopened.groups(), [{'id': identifier, 'name': 'Chamber', 'sensors': ['s']}])
        reopened.save_group({'id': identifier, 'name': 'Chamber & motors', 'sensors': ['s', 't']})
        self.assertEqual(len(reopened.groups()), 1)
        self.assertEqual(reopened.groups()[0]['sensors'], ['s', 't'])
        reopened.delete_group(identifier)
        self.assertEqual(reopened.groups(), [])

    def test_group_validation_and_duplicate_names(self):
        self.store.record(100, [('s', 20, None)], [('s', 'One', 'sensor')])
        self.store.save_group({'name': 'Chamber', 'sensors': ['s']})
        for payload in ({'name': 'chamber', 'sensors': ['s']}, {'name': ' ', 'sensors': ['s']},
                        {'name': 'New', 'sensors': ['missing']}, {'name': 'New', 'sensors': []},
                        {'name': 'New', 'sensors': [['s']]}, {'id': 'gone', 'name': 'New', 'sensors': ['s']}):
            with self.assertRaises(ValueError):
                self.store.save_group(payload)
        self.assertEqual(len(self.store.groups()), 1)

    def test_cleanup_uses_last_valid_reading_and_prunes_group_members(self):
        self.store.record(100, [('old', 20, None), ('live', 30, None)], [('old', 'Old', 'sensor'), ('live', 'Live', 'sensor')])
        self.store.save_group({'name': 'Pair', 'sensors': ['old', 'live']})
        # Repeated metadata and null samples must not make an old channel fresh.
        self.store.record(200, [('old', None, None), ('live', 0, None)], [('old', 'Old', 'sensor'), ('live', 'Live', 'sensor')])
        self.assertEqual(self.store.expire_stale(150), ['old'])
        self.assertEqual(list(self.store.export(0, 300, ['old'])), [])
        self.assertEqual([s['name'] for s in self.store.sensors()], ['live'])
        self.assertEqual(self.store.groups()[0]['sensors'], ['live'])
        self.assertEqual(self.store.history(0, 300, ['live'])['series']['live'][-1]['value'], 0)

    def test_never_reporting_channel_stays_removed_until_valid_data_returns(self):
        self.store.record(100, [('s', None, None)], [('s', 'One', 'sensor')])
        self.assertEqual(self.store.expire_stale(100), [])
        self.assertEqual(self.store.expire_stale(101), ['s'])
        reopened = Store(self.path)
        reopened.record(200, [('s', None, None)], [('s', 'One', 'sensor')])
        self.assertEqual(reopened.sensors(), [])
        self.assertEqual(list(reopened.export(0, 300, ['s'])), [])
        reopened.record(210, [('s', 0, None)], [('s', 'One', 'sensor')])
        self.assertEqual(len(reopened.sensors()), 1)
        self.assertEqual(list(reopened.export(0, 300, ['s']))[0][2], 0)

    def test_old_schema_migrates_timestamps_from_history(self):
        old_path = self.path.parent / 'old.sqlite3'
        with closing(sqlite3.connect(old_path)) as db:
            db.executescript('''CREATE TABLE sensors(name TEXT PRIMARY KEY, label TEXT, kind TEXT);
                CREATE TABLE samples(ts REAL,sensor TEXT,value REAL,target REAL,PRIMARY KEY(ts,sensor));
                INSERT INTO sensors VALUES('s','One','sensor');
                INSERT INTO samples VALUES(100,'s',20,NULL);
                INSERT INTO samples VALUES(200,'s',NULL,NULL);''')
        migrated = Store(old_path)
        self.assertEqual(migrated.expire_stale(150), ['s'])

    def test_successful_poll_cleanup_and_disabled_option(self):
        self.store.record(1, [('old', 20, None)], [('old', 'Old', 'sensor')])
        discovery = {'status': {'heaters': {'available_sensors': ['live']}}}
        readings = {'status': {'live': {'temperature': 25}}}
        recorder = Recorder({**self.config, 'stale_channel_hours': 0}, self.store)
        with patch.object(recorder, 'get', side_effect=[discovery, readings]), patch('server.time.time', return_value=30000):
            recorder.sample()
        self.assertEqual(len(self.store.sensors()), 2)
        recorder.config['stale_channel_hours'] = 6
        with patch.object(recorder, 'get', side_effect=[discovery, readings]), patch('server.time.time', return_value=30001):
            recorder.sample()
        self.assertEqual([s['name'] for s in self.store.sensors()], ['live'])
        self.assertNotIn('old', recorder.status['readings'])

    def test_printer_unavailable_does_not_run_cleanup(self):
        self.store.record(1, [('old', 20, None)], [('old', 'Old', 'sensor')])
        recorder = Recorder(self.config, self.store)
        with patch.object(recorder, 'get', side_effect=RuntimeError('offline')), patch.object(recorder.stop, 'wait', side_effect=lambda _: recorder.stop.set()), patch.object(self.store, 'expire_stale') as cleanup:
            recorder.run()
        cleanup.assert_not_called()
