"""Independent virtual-depth behavior checks (not just output snapshots)."""
from dataclasses import replace
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spine_turn_core import TurnOptions, depth_at, motion_at, pose_at, animation_pose_at


class VirtualDepthTests(unittest.TestCase):
    def test_static_camera_depth_follows_center_perspective_formula(self):
        for offset in (-500, -100, 0, 200, 850):
            options = TurnOptions(base_scale=1.2, z_offset=offset, camera_distance=1000)
            for progress in (0, .07, .4, .86, 1):
                depth = depth_at(progress, options)
                expected = 1000 / (1000 - offset)
                self.assertAlmostEqual(depth['projection_scale'], expected, places=6)
                self.assertAlmostEqual(depth['z_offset'], offset, places=6)
                value = motion_at(progress, options, height=300)
                self.assertAlmostEqual(value['scale_x'], 1.2 * expected, places=5)
                self.assertAlmostEqual(value['scale_y'], 1.2 * expected, places=5)
                self.assertAlmostEqual(value['y'], 0, places=6)

    def test_z_only_changes_distance_and_size_while_center_stays_fixed(self):
        options = TurnOptions(bounce_enabled=False, z_bounce_enabled=True,
            z_offset=-50, z_bounce_depth=250, camera_distance=1000,
            z_scale=1.3, peak_z_scale=1.6, base_scale=.8)
        first = depth_at(0, options)
        peak = depth_at(.4, options)
        self.assertAlmostEqual(first['z_offset'], -50, places=5)
        self.assertAlmostEqual(peak['z_offset'], 200, places=5)
        self.assertAlmostEqual(first['z_scale'], 1.3, places=5)
        self.assertAlmostEqual(peak['z_scale'], 1.3 * 1.6, places=5)
        self.assertGreater(peak['projection_scale'], first['projection_scale'])
        for index in range(501):
            progress = index / 500
            value = motion_at(progress, options, height=300)
            depth = depth_at(progress, options)
            self.assertEqual(value['x'], 0)
            self.assertEqual(value['y'], 0, 'Z-only motion must not introduce a Y jump.')
            self.assertAlmostEqual(value['scale_x'], value['scale_y'], places=6)
            self.assertGreater(value['scale_x'], 0)
            self.assertTrue(all(math.isfinite(v) for v in (*value.values(), *depth.values())))
        for field in ('z_offset', 'z_scale', 'projection_scale'):
            self.assertAlmostEqual(first[field], depth_at(1, options)[field], places=6)

    def test_y_and_z_toggles_are_independent(self):
        base = TurnOptions(bounce_enabled=True, bounce_height=110,
            peak_scale=1.15, landing_squash=.1, z_bounce_enabled=True,
            z_bounce_depth=150, camera_distance=1000, peak_z_scale=1.4)
        z_only = replace(base, bounce_enabled=False)
        y_only = replace(base, z_bounce_enabled=False)
        neither = replace(base, bounce_enabled=False, z_bounce_enabled=False)
        for progress in (0, .08, .12, .16, .28, .4, .8, .86, .93, 1):
            both = motion_at(progress, base, height=300)
            y = motion_at(progress, y_only, height=300)
            z = motion_at(progress, z_only, height=300)
            off = motion_at(progress, neither, height=300)
            self.assertEqual(z['y'], 0)
            self.assertEqual(off['y'], 0)
            self.assertAlmostEqual(depth_at(progress, base)['z_offset'],
                depth_at(progress, z_only)['z_offset'], places=6)
            self.assertEqual(depth_at(progress, y_only)['z_offset'], 0)
            self.assertAlmostEqual(y['scale_x'] / y['scale_y'],
                both['scale_x'] / both['scale_y'], places=5,
                msg='Distance magnification must not add anisotropic squash.')
        self.assertGreater(motion_at(.4, y_only, height=300)['y'], 0)
        self.assertGreater(motion_at(.4, base, height=300)['y'], 0)

    def test_negative_z_bounce_moves_away_and_shrinks_without_a_y_jump(self):
        options = TurnOptions(bounce_enabled=False, z_bounce_enabled=True,
            z_offset=40, z_bounce_depth=-220, camera_distance=1000)
        beginning = depth_at(0, options)
        peak = depth_at(.4, options)
        self.assertAlmostEqual(peak['z_offset'], -180, places=6)
        self.assertLess(peak['projection_scale'], beginning['projection_scale'])
        first_motion = motion_at(0, options, height=300)
        peak_motion = motion_at(.4, options, height=300)
        self.assertLess(peak_motion['scale_x'], first_motion['scale_x'])
        self.assertEqual(peak_motion['scale_x'], peak_motion['scale_y'])
        self.assertEqual(peak_motion['y'], 0)

    def test_uniform_depth_preserves_y_squash_ratio_between_keys(self):
        # Depth magnification must remain uniform even while the independent
        # physical Y-motion curves are squashing and stretching.
        both = TurnOptions(bounce_enabled=True, bounce_height=110,
            peak_scale=1.15, landing_squash=.1, z_bounce_enabled=True,
            z_bounce_depth=150, camera_distance=1000)
        y_only = replace(both, z_bounce_enabled=False)
        for index in range(501):
            progress = index / 500
            actual = motion_at(progress, both, height=300)
            physical = motion_at(progress, y_only, height=300)
            self.assertAlmostEqual(actual['scale_x'] / actual['scale_y'],
                physical['scale_x'] / physical['scale_y'], places=6)

    def test_thickness_scale_changes_edge_width_without_resizing_face(self):
        normal = TurnOptions(width=300, height=300, thickness=20, z_scale=1)
        thick = replace(normal, z_scale=2.5)
        for options, expected in ((normal, 20), (thick, 50)):
            surfaces = [m for m in pose_at(90, options) if m['visible']]
            xs = [x for mesh in surfaces for i, x in enumerate(mesh['vertices']) if i % 2 == 0]
            self.assertAlmostEqual(max(xs) - min(xs), expected, places=5)
        for name in ('front', 'back'):
            original = next(m for m in pose_at(0, normal) if m['name'] == name)
            thicker = next(m for m in pose_at(0, thick) if m['name'] == name)
            self.assertEqual(original['vertices'], thicker['vertices'])

    def test_camera_near_plane_is_rejected_before_nan_or_infinite_projection(self):
        invalid = [TurnOptions(camera_distance=0), TurnOptions(camera_distance=-1),
            TurnOptions(z_offset=901, camera_distance=1000),
            TurnOptions(z_bounce_enabled=True, z_offset=800, z_bounce_depth=101, camera_distance=1000)]
        for options in invalid:
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    depth_at(.4, options)

    def test_default_depth_keeps_original_projection_and_animation(self):
        options = TurnOptions()
        for progress in (0, .123, .4, .5, .86, 1):
            depth = depth_at(progress, options)
            self.assertEqual(depth['z_offset'], 0)
            self.assertEqual(depth['z_scale'], 1)
            self.assertEqual(depth['projection_scale'], 1)
            value = motion_at(progress, options, height=300)
            self.assertEqual(value, {'x': 0., 'y': 0., 'scale_x': 1., 'scale_y': 1.})
            self.assertTrue(animation_pose_at(progress, options))


if __name__ == '__main__':
    unittest.main(verbosity=2)
