"""Exercise the local HTTP API, including duplicate export requests."""
import base64
import io
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from curvepress import web


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.output = patch.object(web, 'OUTPUT_ROOT', Path(self.temp.name))
        self.output.start()
        with web.LOCK:
            web.JOBS.clear()
            web.EXPORTS.clear()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), web.CurvePressHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.output.stop()
        self.temp.cleanup()

    def request(self, path, payload=None, headers=None):
        body = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(self.url + path, body, headers=headers or {'Content-Type': 'application/json'})
        try:
            response = urllib.request.urlopen(req, timeout=15)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status, response.read()

    def analyze(self):
        image = Image.new('RGB', (100, 80), 'white')
        ImageDraw.Draw(image).rectangle((20, 20, 60, 60), fill='black')
        raw = io.BytesIO()
        image.save(raw, 'PNG')
        status, body = self.request('/api/analyze', {
            'image': 'data:image/png;base64,' + base64.b64encode(raw.getvalue()).decode(),
            'config': {'width_mm': 30, 'height_mm': 24, 'style': 'poster', 'base_height_mm': '1.0'},
        })
        self.assertEqual(status, 200, body)
        return json.loads(body)

    def test_analysis_downloads_and_validation(self):
        result = self.analyze()
        status, archive = self.request(result['bundle'])
        self.assertEqual(status, 200)
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            self.assertIn('analysis.json', bundle.namelist())
            self.assertIn('ink.svg', bundle.namelist())
        self.assertEqual(self.request('/api/analyze', [1, 2])[0], 400)
        self.assertEqual(self.request('/api/analyze', {}, {'Content-Type': 'text/plain'})[0], 400)
        self.assertEqual(self.request('/api/analyze', {}, {'Content-Type': 'application/json', 'Origin': 'https://example.com'})[0], 400)
        self.assertEqual(self.request('/api/artifact/' + result['job_id'] + '/%2e%2e%2fanalysis.json')[0], 404)

    def test_duplicate_export_requests_start_one_worker(self):
        result = self.analyze()
        release = threading.Event()
        calls = []

        def fake_export(analysis, config):
            calls.append(analysis.job_id)
            if not release.wait(10):
                raise RuntimeError('test export timed out')
            (analysis.directory / 'plate.stl').write_bytes(b'validated-test-artifact')
            return [{'files': ['plate.stl']}]

        try:
            with patch.object(web, 'export_analysis', side_effect=fake_export):
                with ThreadPoolExecutor(max_workers=8) as pool:
                    responses = list(pool.map(lambda _: self.request('/api/export', {'job_id': result['job_id']}), range(12)))
                self.assertTrue(all(status == 202 for status, _ in responses))
                release.set()
                for _ in range(100):
                    _, body = self.request('/api/export/' + result['job_id'])
                    state = json.loads(body)
                    if state['state'] in {'done', 'error'}:
                        break
                    time.sleep(.01)
                self.assertEqual(state['state'], 'done', state)
                self.assertEqual(calls, [result['job_id']])
                self.request('/api/export', {'job_id': result['job_id']})
                self.assertEqual(len(calls), 1)
        finally:
            release.set()
