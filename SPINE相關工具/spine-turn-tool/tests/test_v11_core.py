"""Behavior checks for orientation, anchored bounce/scales, and opaque face shading."""
from pathlib import Path
import math
import sys
import tempfile
import unittest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spine_turn_core import TurnOptions, prepare_images, pose_at, motion_at


class V11BehaviorTests(unittest.TestCase):
    def test_horizontal_vertical_and_auto_edge_inputs_are_equivalent(self):
        source = ROOT / 'assets' / 'demo-edge.png'
        front = ROOT / 'assets' / 'demo-front.png'
        with tempfile.TemporaryDirectory() as temporary:
            vertical = Path(temporary) / 'vertical.png'
            with Image.open(source) as im:
                im.transpose(Image.Transpose.ROTATE_270).save(vertical)
            horizontal_result = prepare_images(front, None, source, TurnOptions(edge_orientation='horizontal'))
            vertical_result = prepare_images(front, None, vertical, TurnOptions(edge_orientation='vertical'))
            auto_h = prepare_images(front, None, source, TurnOptions(edge_orientation='auto'))
            auto_v = prepare_images(front, None, vertical, TurnOptions(edge_orientation='auto'))
            for candidate in [vertical_result, auto_h, auto_v]:
                self.assertEqual(horizontal_result['edge'].size, candidate['edge'].size)
                self.assertEqual(horizontal_result['edge'].tobytes(), candidate['edge'].tobytes())
            self.assertEqual(auto_h['edge_resolved_orientation'], 'horizontal')
            self.assertEqual(auto_v['edge_resolved_orientation'], 'vertical')
            self.assertEqual(auto_h['edge_source_size'], [512, 32])
            self.assertEqual(auto_v['edge_source_size'], [32, 512])

    def test_disabled_bounce_retains_base_scale_and_stationary_center(self):
        for progress in [0, .037, .08, .4, .86, 1]:
            value = motion_at(progress, TurnOptions(base_scale=1.25), height=300)
            self.assertAlmostEqual(value['x'], 0)
            self.assertAlmostEqual(value['y'], 0)
            self.assertAlmostEqual(value['scale_x'], 1.25)
            self.assertAlmostEqual(value['scale_y'], 1.25)

    def test_bounce_preserves_ground_contact_at_landing_and_recovers_endpoints(self):
        opts = TurnOptions(base_scale=1.25, bounce_enabled=True, bounce_height=120,
            peak_scale=1.2, landing_squash=.16)
        height = 300
        ground = -height * opts.base_scale / 2
        for progress in [0, .08, .8, .86, .93, 1]:
            value = motion_at(progress, opts, height=height)
            self.assertAlmostEqual(value['y'] - height * value['scale_y'] / 2, ground, places=4,
                msg=f'Ground slides during contact at progress {progress}.')
        apex = motion_at(.4, opts, height=height)
        self.assertAlmostEqual(apex['y'] - height * apex['scale_y'] / 2, ground + 120, places=4)
        self.assertAlmostEqual(apex['scale_x'], opts.base_scale * opts.peak_scale, places=4)
        self.assertAlmostEqual(apex['scale_y'], opts.base_scale * opts.peak_scale, places=4)
        landing = motion_at(.86, opts, height=height)
        self.assertGreater(landing['scale_x'], opts.base_scale)
        self.assertLess(landing['scale_y'], opts.base_scale)
        for progress in [0, 1]:
            resting = motion_at(progress, opts, height=height)
            self.assertAlmostEqual(resting['x'], 0)
            self.assertAlmostEqual(resting['y'], 0)
            self.assertAlmostEqual(resting['scale_x'], opts.base_scale)
            self.assertAlmostEqual(resting['scale_y'], opts.base_scale)
        for index in range(1001):
            value = motion_at(index / 1000, opts, height=height)
            self.assertTrue(all(math.isfinite(v) for v in value.values()))
            self.assertGreater(value['scale_x'], 0)
            self.assertGreater(value['scale_y'], 0)

    def test_face_shading_is_grayscale_opaque_and_respects_light_direction(self):
        opts = TurnOptions(shade_faces=True, min_brightness=.4, shade_curve=1, light_angle=45)
        for angle in [0, 15, 45, 89.99, 90, 135, 180, 225, 270, 315, 360]:
            for face in [m for m in pose_at(angle, opts) if m['kind'] in ['front', 'back']]:
                rgba = tuple(int(face['color'][i:i + 2], 16) for i in range(0, 8, 2))
                self.assertEqual(rgba[0], rgba[1])
                self.assertEqual(rgba[1], rgba[2])
                self.assertEqual(rgba[3], 255, 'Brightness must never turn into transparency.')
                self.assertGreaterEqual(rgba[0], round(255 * .4))
                self.assertLessEqual(rgba[0], 255)
        front_at_45 = next(m for m in pose_at(45, opts) if m['kind'] == 'front')
        self.assertEqual(front_at_45['color'].lower(), 'ffffffff')
        off = TurnOptions(shade_faces=False, min_brightness=.1, light_angle=45)
        self.assertTrue(all(m['color'].lower() == 'ffffffff' for m in pose_at(90, off)
            if m['kind'] in ['front', 'back']))
        standard = next(m for m in pose_at(45, TurnOptions(shade_faces=True, shade_curve=1)) if m['kind'] == 'front')
        stronger = next(m for m in pose_at(45, TurnOptions(shade_faces=True, shade_curve=2)) if m['kind'] == 'front')
        self.assertLess(int(stronger['color'][:2], 16), int(standard['color'][:2], 16))


if __name__ == '__main__':
    unittest.main(verbosity=2)
