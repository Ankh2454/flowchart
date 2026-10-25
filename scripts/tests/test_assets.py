"""Offline contract tests: run with python3 -m unittest discover -s scripts/tests -v."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'scripts'
spec = importlib.util.spec_from_file_location('normalize_assets', SCRIPTS / 'normalize-assets.py')
normalizer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(normalizer)


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.catalog = {'generation': {'width': 64, 'height': 64, 'steps': 4},
                        'assets': [{'id': 'test-object', 'prompt': 'one flat object', 'seed': 1}]}
        self.catalog_path = self.folder / 'catalog.json'
        self.catalog_path.write_text(json.dumps(self.catalog))
        buffer = BytesIO()
        Image.new('RGB', (64, 64), 'red').save(buffer, format='PNG')
        self.png = buffer.getvalue()
        self.state = {'posts': 0, 'gets': 0, 'statuses': ['succeeded'], 'data': self.png}
        state = self.state

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                state['posts'] += 1
                state['payload'] = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                self.send_response(202)
                self.end_headers()
                self.wfile.write(json.dumps({'id': 'a' * 32}).encode())

            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                if self.path.endswith('/file'):
                    state['gets'] += 1
                    self.wfile.write(state['data'])
                else:
                    status = state['statuses'][0]
                    if len(state['statuses']) > 1:
                        state['statuses'].pop(0)
                    self.wfile.write(json.dumps({'status': status, 'error': 'mock failure'}).encode())

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.raw = self.folder / 'raw/test-object.raw.png'
        self.command = [sys.executable, str(SCRIPTS / 'generate-assets.py'), '--api-base',
                        f'http://127.0.0.1:{self.server.server_port}', '--catalog', str(self.catalog_path),
                        '--out', str(self.folder / 'raw')]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def run_cli(self, *args, success=True):
        result = subprocess.run(self.command + list(args), capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def test_queue_running_success_and_skip(self):
        self.state['statuses'] = ['queued', 'running', 'succeeded']
        self.run_cli()
        self.run_cli()
        self.assertEqual((self.state['posts'], self.state['gets']), (1, 1))
        self.assertEqual(self.raw.read_bytes(), self.png)
        self.assertEqual(self.state['payload']['prompt'], 'one flat object')

    def test_timeout_resume_does_not_resubmit(self):
        self.state['statuses'] = ['running']
        self.assertIn('resume', self.run_cli('--timeout', '0.01', success=False).stderr)
        self.state['statuses'] = ['succeeded']
        self.run_cli()
        self.assertEqual(self.state['posts'], 1)

    def test_failure_preserves_receipt_without_image(self):
        self.state['statuses'] = ['failed']
        self.assertIn('mock failure', self.run_cli(success=False).stderr)
        self.assertFalse(self.raw.exists())
        self.assertTrue(self.raw.with_name('test-object.job.json').exists())

    def test_changed_request_rejected_without_submission(self):
        self.run_cli()
        self.catalog['assets'][0]['prompt'] = 'changed'
        self.catalog_path.write_text(json.dumps(self.catalog))
        self.assertIn('request changed', self.run_cli(success=False).stderr)
        self.assertEqual(self.state['posts'], 1)

    def test_truncated_png_rejected_then_download_resumed(self):
        self.state['data'] = self.png[:24]
        self.run_cli(success=False)
        self.assertFalse(self.raw.exists())
        self.state['data'] = self.png
        self.run_cli()
        self.assertEqual(self.raw.read_bytes(), self.png)
        self.assertEqual(self.state['posts'], 1)

    def test_corrupt_saved_png_is_recovered(self):
        self.run_cli()
        self.raw.write_bytes(self.png[:24])
        self.run_cli()
        self.assertEqual(self.raw.read_bytes(), self.png)
        self.assertEqual((self.state['posts'], self.state['gets']), (1, 2))

    def test_invalid_options_do_not_submit(self):
        for value in ('0', '-1', 'nan', 'inf'):
            with self.subTest(timeout=value):
                self.run_cli('--timeout', value, success=False)
        self.run_cli('--only', 'nonexistent', success=False)
        self.assertEqual(self.state['posts'], 0)


class NormalizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_palette_transparency_and_centering(self):
        source = self.folder / 'source.png'
        target = self.folder / 'out/object.png'
        im = Image.new('RGB', (256, 256), '#edf0e8')
        draw = ImageDraw.Draw(im)
        draw.rectangle((60, 50, 195, 205), fill='#608880')
        draw.rectangle((90, 90, 165, 165), fill='#e56e41')
        im.save(source)
        normalizer.normalize(source, target, [])
        with Image.open(target) as result:
            self.assertEqual((result.mode, result.size), ('RGBA', (512, 512)))
            self.assertEqual(result.getpixel((256, 256)), (233, 91, 56, 255))
            self.assertEqual(result.getpixel((0, 0))[3], 0)
            self.assertEqual(result.getpixel((200, 256)), (99, 158, 149, 255))

    def test_blank_and_clipped_inputs_rejected(self):
        for clipped in (False, True):
            with self.subTest(clipped=clipped):
                source = self.folder / 'source.png'
                target = self.folder / 'out.png'
                im = Image.new('RGB', (256, 256), '#edf0e8')
                if clipped:
                    ImageDraw.Draw(im).rectangle((0, 70, 150, 180), fill='#608880')
                im.save(source)
                with self.assertRaisesRegex(ValueError, 'manual review'):
                    normalizer.normalize(source, target, [])
                self.assertFalse(target.exists())

    def test_shipped_catalog_images(self):
        catalog = json.loads((ROOT / 'assets/raster/catalog.json').read_text())
        ids = [asset['id'] for asset in catalog['assets']]
        self.assertEqual(len(ids), len(set(ids)))
        for asset in catalog['assets']:
            with self.subTest(asset=asset['id']):
                with Image.open(ROOT / 'assets/raster' / asset['file']) as im:
                    im.load()
                    self.assertEqual((im.mode, im.size), ('RGBA', (512, 512)))
                    alpha = im.getchannel('A')
                    self.assertEqual(alpha.getextrema(), (0, 255))
                    bounds = alpha.getbbox()
                    self.assertGreaterEqual(min(bounds[:2]), 48)
                    self.assertLessEqual(max(bounds[2:]), 464)


if __name__ == '__main__':
    unittest.main()
