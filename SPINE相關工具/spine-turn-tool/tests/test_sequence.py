"""Image-level checks for transparent, fixed-camera sequence delivery."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spine_turn_core import TurnOptions, prepare_images
from spine_turn_preview import render_pose
from spine_turn_sequence import export_sequence


class SequenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.options = TurnOptions(duration=.8)
        cls.prepared = prepare_images(ROOT / 'assets' / 'demo-front.png',
            ROOT / 'assets' / 'demo-back.png', ROOT / 'assets' / 'demo-edge.png', cls.options)

    def test_loop_has_transparent_rgba_fixed_canvas_and_no_duplicate_endpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            result = export_sequence(self.prepared, self.options, directory, fps=10, size=(160, 192))
            self.assertTrue(result['ok'])
            self.assertEqual(result['frame_count'], 8)
            manifest = json.loads(Path(result['manifest_path']).read_text(encoding='utf-8'))
            self.assertEqual(manifest['alpha'], 'straight')
            self.assertTrue(manifest['transparent_background'])
            self.assertFalse(manifest['endpoint_included'])
            self.assertFalse(manifest['loop_endpoint_duplicated'])
            self.assertEqual(manifest['effective_fps'], 10)
            self.assertEqual(manifest['world_pivot'], [0, 0])
            pixels = []
            for filename in result['frame_paths']:
                with Image.open(filename) as frame:
                    self.assertEqual(frame.mode, 'RGBA')
                    self.assertEqual(frame.size, (160, 192))
                    self.assertEqual(frame.getpixel((0, 0))[3], 0)
                    self.assertEqual(frame.getpixel((159, 191))[3], 0)
                    alpha = frame.getchannel('A')
                    box = alpha.getbbox()
                    self.assertIsNotNone(box)
                    self.assertGreater(box[0], 0)
                    self.assertGreater(box[1], 0)
                    self.assertLess(box[2], 160)
                    self.assertLess(box[3], 192)
                    self.assertEqual(alpha.getextrema()[1], 255)
                    pixels.append(frame.tobytes())
            self.assertNotEqual(pixels[0], pixels[-1], 'The terminal loop pose was duplicated.')
            expected = render_pose(self.prepared, self.options, 315, size=(160, 192),
                background='transparent', progress=7 / 8, show_ground=False, camera=result['camera'])
            self.assertEqual(pixels[-1], expected.tobytes())

    def test_nonloop_includes_back_endpoint_and_reports_effective_timing(self):
        options = replace(self.options, duration=1.1)
        with tempfile.TemporaryDirectory() as directory:
            result = export_sequence(self.prepared, options, directory, animation_name='flip_to_back', fps=7,
                size=(160, 160))
            # Half-turn duration=.55; round(.55*7)=4 intervals plus the final endpoint.
            self.assertEqual(result['frame_count'], 5)
            self.assertAlmostEqual(result['effective_fps'], 4 / .55)
            manifest = json.loads(Path(result['manifest_path']).read_text(encoding='utf-8'))
            self.assertTrue(manifest['endpoint_included'])
            expected = render_pose(self.prepared, options, 180, size=(160, 160),
                background='transparent', progress=1, animation_name='flip_to_back',
                show_ground=False, camera=result['camera'])
            with Image.open(result['frame_paths'][-1]) as final:
                self.assertEqual(final.tobytes(), expected.tobytes())

    def test_bounce_uses_one_camera_and_retains_visible_travel(self):
        options = replace(self.options, duration=1, bounce_enabled=True, bounce_height=100, peak_scale=1.2)
        with tempfile.TemporaryDirectory() as directory:
            result = export_sequence(self.prepared, options, directory, fps=10, size=(192, 224))
            boxes = []
            for filename in result['frame_paths']:
                with Image.open(filename) as frame:
                    box = frame.getchannel('A').getbbox()
                    self.assertIsNotNone(box)
                    self.assertGreater(box[0], 0)
                    self.assertGreater(box[1], 0)
                    self.assertLess(box[2], 192)
                    self.assertLess(box[3], 224)
                    boxes.append(box)
            resting_y = (boxes[0][1] + boxes[0][3]) / 2
            apex_y = (boxes[4][1] + boxes[4][3]) / 2
            self.assertLess(apex_y, resting_y - 20, 'Per-frame fitting erased the jump travel.')

    def test_cancel_keeps_only_partial_frames_and_honest_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            stop = threading.Event()
            progress = []
            def on_progress(completed, total):
                progress.append((completed, total))
                if completed == 2:
                    stop.set()
            result = export_sequence(self.prepared, self.options, directory, fps=10, size=(96, 96),
                cancel_event=stop, progress_callback=on_progress)
            self.assertFalse(result['ok'])
            self.assertEqual(result['status'], 'cancelled')
            self.assertEqual(result['frame_count'], 2)
            self.assertEqual(len(list(Path(directory).glob('*.png'))), 2)
            manifest = json.loads(Path(result['manifest_path']).read_text(encoding='utf-8'))
            self.assertFalse(manifest['complete'])
            self.assertEqual(manifest['status'], 'cancelled')
            self.assertEqual(progress, [(0, 8), (1, 8), (2, 8)])

    def test_existing_output_is_preserved_and_invalid_settings_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            sentinel = Path(directory) / 'existing.txt'
            sentinel.write_text('retain', encoding='utf-8')
            with self.assertRaises(FileExistsError):
                export_sequence(self.prepared, self.options, directory, size=(96, 96))
            self.assertEqual(sentinel.read_text(encoding='utf-8'), 'retain')
            self.assertEqual(len(list(Path(directory).iterdir())), 1)
        for kwargs in [{'fps': 0}, {'fps': 121}, {'fps': float('nan')}, {'size': (63, 100)},
            {'size': (100, 4097)}, {'padding': .5}, {'animation_name': 'missing'}]:
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    export_sequence(self.prepared, self.options, directory, **kwargs)
                self.assertFalse(list(Path(directory).iterdir()))

    def test_renderer_failure_is_not_reported_as_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('spine_turn_sequence.render_pose', side_effect=RuntimeError('injected render failure')):
                with self.assertRaisesRegex(RuntimeError, 'injected'):
                    export_sequence(self.prepared, self.options, directory, size=(96, 96))
            manifest = json.loads((Path(directory) / 'sequence.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['status'], 'error')
            self.assertFalse(manifest['complete'])
            self.assertEqual(manifest['frame_count'], 0)

    def test_straight_alpha_keeps_semitransparent_color_without_double_multiplication(self):
        prepared = dict(self.prepared)
        prepared['front'] = Image.new('RGBA', prepared['front'].size, (80, 160, 240, 128))
        options = replace(self.options, duration=.1)
        with tempfile.TemporaryDirectory() as directory:
            result = export_sequence(prepared, options, directory, fps=1, size=(96, 96))
            self.assertEqual(result['frame_count'], 1)
            with Image.open(result['frame_paths'][0]) as frame:
                pixel = frame.getpixel((48, 48))
                self.assertEqual(pixel[3], 128)
                # Pillow's premultiplied bilinear sampling can round RGB by one.
                self.assertTrue(all(abs(a - b) <= 1 for a, b in zip(pixel[:3], (80, 160, 240))))

    def test_z_only_bounce_changes_size_without_vertical_travel(self):
        options = replace(self.options, duration=1, bounce_enabled=False, z_bounce_enabled=True,
            z_bounce_depth=300, camera_distance=1000, peak_z_scale=1.5)
        with tempfile.TemporaryDirectory() as directory:
            result = export_sequence(self.prepared, options, directory, fps=10, size=(192, 192))
            boxes = []
            for filename in result['frame_paths']:
                with Image.open(filename) as frame:
                    boxes.append(frame.getchannel('A').getbbox())
            center0 = (boxes[0][1] + boxes[0][3]) / 2
            center4 = (boxes[4][1] + boxes[4][3]) / 2
            self.assertAlmostEqual(center0, center4, delta=1)
            self.assertGreater(boxes[4][3] - boxes[4][1], (boxes[0][3] - boxes[0][1]) * 1.2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
