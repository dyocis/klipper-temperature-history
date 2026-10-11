import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen

from server import Recorder, Store, handler_for


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'db.sqlite3')
        self.store.record(100, [('heater_bed', 50, 100)], [('heater_bed', 'Bed', 'heater')], ('printing', '<test>.gcode'))
        config = {'sample_seconds': 10, 'retention_days': 30}
        self.recorder = Recorder(config, self.store)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.recorder, self.store))
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def test_history_and_raw_export(self):
        with urlopen(self.base + '/api/history?start=90&end=120') as response:
            data = json.load(response)
        self.assertEqual(data['series']['heater_bed'][0]['value'], 50)
        self.assertEqual(data['events'][0]['state'], 'printing')
        with urlopen(self.base + '/api/export?start=90&end=120&sensor=heater_bed') as response:
            text = response.read().decode()
        self.assertIn('unix_seconds,sensor,temperature_c,target_c', text)
        self.assertIn('heater_bed,50.0,100.0', text)

    def test_invalid_ranges_and_path_rejected(self):
        for route, code in [('/api/history?start=nan&end=120', 400),
                            ('/api/history?start=120&end=90', 400),
                            ('/api/history?sensor=missing', 400),
                            ('/../config.local.json', 404),
                            ('/printer/gcode/script', 404)]:
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base + route)
            self.assertEqual(error.exception.code, code)
            error.exception.close()

    def test_assets_and_status(self):
        for route in ('/', '/styles.css', '/app.js', '/favicon.svg', '/favicon.ico', '/favicon.png'):
            with urlopen(self.base + route) as response:
                self.assertGreater(len(response.read()), 100)
        with urlopen(self.base + '/api/status') as response:
            status = json.load(response)
        self.assertEqual(status['sensors'][0]['name'], 'heater_bed')
        self.assertNotIn('moonraker_url', status)
