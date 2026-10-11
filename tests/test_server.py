import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from server import Recorder, Store, load_config


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'history.sqlite3'
        self.store = Store(self.path)
        self.config = {'moonraker_url': 'http://printer.local:7125', 'api_key_env': 'TEST_KEY',
                       'exclude_sensors': [], 'include_nonstandard_sensors': [],
                       'sample_seconds': 10, 'retention_days': 30}

    def tearDown(self):
        self.tmp.cleanup()

    def test_persistence_peaks_and_retention(self):
        self.store.record(100, [('heater_bed', 25, 100)], [('heater_bed', 'Bed', 'heater')])
        self.store.record(110, [('heater_bed', 120, 100)], [])
        reopened = Store(self.path)
        bucket = reopened.history(100, 200, ['heater_bed'], buckets=1)['series']['heater_bed'][0]
        self.assertEqual((bucket['min'], bucket['max']), (25, 120))
        self.assertEqual(bucket['value'], 72.5)
        reopened.prune(105)
        self.assertEqual(len(list(reopened.export(0, 200, ['heater_bed']))), 1)

    def test_mixed_bucket_keeps_disconnect_gap(self):
        self.store.record(100, [('s', 50, None)], [('s', 'Sensor', 'sensor')])
        self.store.record(110, [('s', None, None)], [])
        bucket = self.store.history(100, 200, ['s'], buckets=1)['series']['s'][0]
        self.assertIsNone(bucket['value'])
        self.assertEqual(bucket['max'], 50)

    def test_discovery_excludes_power_and_voc(self):
        recorder = Recorder(self.config, self.store)
        discovery = {'status': {'heaters': {'available_sensors': ['extruder', 'temperature_sensor Hotend_power', 'temperature_sensor VOC', 'temperature_sensor motor'], 'available_heaters': ['extruder'], 'available_monitors': ['tmc2240 extruder']}, 'configfile': {'settings': {'temperature_sensor Hotend_power': {'sensor_type': 'HOT_P'}, 'temperature_sensor VOC': {'plot_voc': True}}}}}
        readings = {'status': {'extruder': {'temperature': 200, 'target': 210}, 'temperature_sensor motor': {'temperature': 45}, 'tmc2240 extruder': {'temperature': None}, 'print_stats': {'state': 'printing', 'filename': 'cube.gcode'}}}
        discovery['status']['configfile']['settings']['temperature_sensor hotend_power'] = discovery['status']['configfile']['settings'].pop('temperature_sensor Hotend_power')
        with patch.object(recorder, 'get', side_effect=[discovery, readings]):
            recorder.sample()
        self.assertEqual(set(recorder.status['excluded']), {'temperature_sensor Hotend_power', 'temperature_sensor VOC'})
        self.assertEqual(len(self.store.sensors()), 3)
        self.assertIsNone(recorder.status['readings']['tmc2240 extruder']['value'])
        self.assertEqual(recorder.status['print_state'], 'printing')

    def test_removed_sensor_becomes_gap(self):
        self.store.record(1, [('old', 40, None)], [('old', 'Old', 'sensor')])
        recorder = Recorder(self.config, self.store)
        with patch.object(recorder, 'get', side_effect=[{'status': {'heaters': {}}}, {'status': {}}]):
            recorder.sample()
        rows = list(self.store.export(0, 9999999999, ['old']))
        self.assertIsNone(rows[-1][2])

    def test_config_resolves_database_relative_to_file(self):
        config_path = Path(self.tmp.name) / 'config.json'
        config_path.write_text(json.dumps({'moonraker_url': 'http://printer.local:7125', 'database': 'data/test.db'}))
        config = load_config(config_path)
        self.assertEqual(Path(config['database']), Path(self.tmp.name) / 'data/test.db')
        config_path.write_text(json.dumps({'moonraker_url': 'http://printer.local:7125', 'sample_seconds': 0}))
        with self.assertRaises(ValueError):
            load_config(config_path)

    def test_print_markers_distinguish_start_resume_and_finish(self):
        self.store.record(100, [], [], ('standby', ''))
        self.store.record(110, [], [], ('printing', 'cube.gcode'))
        self.store.record(120, [], [], ('paused', 'cube.gcode'))
        self.store.record(130, [], [], ('printing', 'cube.gcode'))
        self.store.record(140, [], [], ('complete', 'cube.gcode'))
        self.store.record(150, [], [], ('printing', 'second.gcode'))
        self.store.record(160, [], [], ('cancelled', 'second.gcode'))
        kinds = [e['kind'] for e in self.store.history(100, 170, [])['events']]
        self.assertEqual(kinds, ['status_observed', 'print_started', 'print_paused', 'print_resumed', 'print_finished', 'print_started', 'print_cancelled'])

    def test_preexisting_completed_print_has_no_finish_marker(self):
        self.store.record(100, [], [], ('complete', 'old.gcode'))
        event = self.store.history(90, 110, [])['events'][0]
        self.assertEqual(event['kind'], 'status_observed')
        self.assertEqual(event['state'], 'complete')

    def test_midprint_startup_is_not_labeled_actual_start(self):
        self.store.record(100, [], [], ('printing', 'cube.gcode'))
        self.store.record(105, [], [], ('printing', 'cube.gcode'))
        self.assertEqual(len(self.store.history(90, 110, [])['events']), 1)
        self.assertEqual(self.store.history(90, 110, [])['events'][0]['kind'], 'printing_detected')


if __name__ == '__main__':
    unittest.main()
