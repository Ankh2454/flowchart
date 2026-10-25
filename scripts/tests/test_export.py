"""Exercise the real browser + ffmpeg exporter and decode its output."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[2]
NODE = os.environ.get('NODE_PATH') or shutil.which('node') or 'node'
BASE = '''<!doctype html><style>:root{--loop:LOOP}body{margin:41px}.canvas{width:50px}svg{width:100%}.dot{animation:move DURATION linear ITERATIONS;animation-delay:DELAY}@keyframes move{0%,100%{transform:translateX(0)}50%{transform:translateX(50px)}}</style><div data-preview-controls style="background:red;height:80px">Do not record this</div><div class="canvas"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 100"><title>Export fixture</title><desc>A moving paper square</desc><rect width="160" height="100" fill="#edf0e8"/><rect class="dot" x="20" y="20" width="20" height="20" fill="#e95b38"/></svg></div>'''


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.source = self.folder / 'input.html'
        self.output = self.folder / 'output.gif'
        self.poster = self.folder / 'poster.png'

    def tearDown(self):
        self.temp.cleanup()

    def run_export(self, *, loop='1000ms', duration='1000ms', delay='0ms', iterations='infinite', extra=()):
        self.output.unlink(missing_ok=True)
        self.poster.unlink(missing_ok=True)
        html = BASE.replace('LOOP', loop).replace('DURATION', duration).replace('DELAY', delay).replace('ITERATIONS', iterations)
        self.source.write_text(html)
        return subprocess.run([NODE, str(ROOT / 'scripts/render-gif.mjs'), str(self.source),
                               str(self.output), '--poster', str(self.poster), '--fps', '10', *extra],
                              capture_output=True, text=True, timeout=60)

    def test_real_gif_frames_dimensions_motion_and_cropping(self):
        result = self.run_export()
        self.assertEqual(result.returncode, 0, result.stderr)
        with Image.open(self.output) as gif, Image.open(self.poster) as poster:
            self.assertEqual(gif.size, (320, 200))
            self.assertEqual(gif.n_frames, 10)
            self.assertEqual(gif.info['loop'], 0)
            start = gif.convert('RGB')
            total = 0
            frames = []
            for i in range(gif.n_frames):
                gif.seek(i)
                total += gif.info['duration']
                frames.append(gif.convert('RGB'))
            self.assertEqual(total, 1000)
            self.assertTrue(ImageChops.difference(frames[0], frames[5]).getbbox())
            self.assertTrue(ImageChops.difference(frames[5], frames[9]).getbbox())
            self.assertEqual(poster.size, (320, 200))
            self.assertEqual(poster.convert('RGB').getpixel((0, 0)), (237, 240, 232))
            self.assertTrue(ImageChops.difference(start, poster.convert('RGB')).getbbox())

    def test_invalid_animation_contracts(self):
        for kwargs, message in [({'duration': '300ms'}, 'period'), ({'delay': '100ms'}, 'delay'),
                                ({'iterations': '1'}, 'infinite'), ({'loop': 'oops'}, 'CSS'),
                                ({'extra': ('--loop', '2000')}, 'does not match')]:
            with self.subTest(kwargs=kwargs):
                result = self.run_export(**kwargs)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                self.assertFalse(self.output.exists())

    def test_invalid_numeric_and_colliding_paths(self):
        for args in [('--fps', '0'), ('--scale', 'NaN'), ('--loop', '-1'),
                     ('--poster', str(self.source)), ('--unknown', '1')]:
            with self.subTest(args=args):
                result = self.run_export(extra=args)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.output.exists())
                self.assertTrue(self.source.read_text().startswith('<!doctype html>'))


if __name__ == '__main__':
    unittest.main()
