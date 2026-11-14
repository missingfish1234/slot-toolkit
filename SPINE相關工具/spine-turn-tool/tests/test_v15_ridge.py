"""Independent closed-ridge, no-side-material, and legacy-strip checks."""
from dataclasses import replace
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from fixture_availability import require_historical_packages

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spine_turn_core import (TurnOptions, prepare_images, resolve_options, pose_at,
    animation_pose_at, build_skeleton, build_package)
from spine_turn_preview import render_pose
from test_v14_raised_region import TRIANGLE, PENTAGON, closed_mesh_edge_counts, chunks


class RidgeModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prepared = prepare_images(ROOT / 'assets/demo-octagon.png',
            options=TurnOptions(shape='polygon'))
        cls.base = resolve_options(cls.prepared, TurnOptions(shape='polygon',
            side_mode='ridge', thickness=32, bevel_width=0, bevel_depth=.25,
            shade_edge=False, shade_faces=False))

    def test_automatic_and_manual_ridges_are_closed_without_sideband(self):
        for points in ((), TRIANGLE, PENTAGON):
            options = resolve_options(self.prepared, replace(self.base, raised_contour_points=points))
            surfaces = pose_at(38, options, self.prepared['width'], self.prepared['height'])
            self.assertTrue(any(m['kind'] == 'bevel' for m in surfaces))
            self.assertFalse(any(m['kind'] == 'edge' or m['path'] == 'edge' for m in surfaces))
            self.assertEqual(set(closed_mesh_edge_counts(surfaces).values()), {2})
            front_outer, back_outer = set(), set()
            all_z = []
            for mesh in surfaces:
                model = chunks(mesh['model_vertices'], 3)
                all_z.extend(p[2] for p in model)
                if mesh['kind'] == 'bevel':
                    for x, y, z in model:
                        if abs(z) < 1e-8:
                            (front_outer if mesh['path'] == 'front' else back_outer).add((round(x, 7), round(y, 7)))
            self.assertTrue(front_outer)
            self.assertEqual(front_outer, back_outer)
            self.assertAlmostEqual(max(all_z) - min(all_z), options.thickness * options.z_scale, places=7)

    def test_auto_width_zero_creates_valid_fallback_inset(self):
        self.assertFalse(self.base.raised_contour_points)
        self.assertEqual(self.base.bevel_width, 0)
        surfaces = pose_at(0, self.base, self.prepared['width'], self.prepared['height'])
        cap = next(surface for surface in surfaces if surface['name'] == 'front')
        self.assertGreater(cap['hull'], 2)
        self.assertTrue(any(surface['kind'] == 'bevel' for surface in surfaces))

    def test_bevel_height_changes_do_not_change_ridge_mesh_or_animation(self):
        for points in ((), PENTAGON):
            low = resolve_options(self.prepared, replace(self.base,
                bevel_depth=0, raised_contour_points=points, z_bounce_enabled=True, peak_z_scale=1.3))
            high = replace(low, bevel_depth=.45)
            a, b = build_skeleton(self.prepared, low), build_skeleton(self.prepared, high)
            for section in ('animations', 'skins', 'bones', 'slots'):
                self.assertEqual(a[section], b[section], section)

    def test_edge_texture_is_not_referenced_and_cannot_change_ridge_pixels(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            red, blue = folder / 'red.png', folder / 'blue.png'
            Image.new('RGBA', (32, 16), '#ff0000').save(red)
            Image.new('RGBA', (32, 16), '#0000ff').save(blue)
            images_a = prepare_images(ROOT / 'assets/demo-octagon.png', None, red, self.base)
            images_b = prepare_images(ROOT / 'assets/demo-octagon.png', None, blue, self.base)
            document = build_skeleton(images_a, self.base)
            for attachments in document['skins'][0]['attachments'].values():
                for mesh in attachments.values():
                    self.assertIn(mesh['path'], ('front', 'back'))
            for angle in range(0, 360, 30):
                a = render_pose(images_a, self.base, angle, size=(240, 240),
                    background='transparent', show_ground=False)
                b = render_pose(images_b, self.base, angle, size=(240, 240),
                    background='transparent', show_ground=False)
                self.assertEqual(a.tobytes(), b.tobytes())

    def test_projected_total_thickness_is_preserved_for_both_rotation_axes(self):
        for axis in ('x', 'y'):
            for z_scale in (.7, 1, 1.8):
                options = replace(self.base, axis=axis, z_scale=z_scale)
                surfaces = pose_at(90, options, self.prepared['width'], self.prepared['height'])
                parity = 0 if axis == 'y' else 1
                values = [v for surface in surfaces for index, v in enumerate(surface['vertices']) if index % 2 == parity]
                self.assertAlmostEqual(max(values) - min(values), options.thickness * z_scale, places=6)

    def test_ridge_culling_switches_only_at_negligible_projected_area(self):
        for axis in ('x', 'y'):
            options = resolve_options(self.prepared, replace(self.base, axis=axis,
                raised_contour_points=PENTAGON, z_bounce_enabled=True, peak_z_scale=1.4))
            document = build_skeleton(self.prepared, options)
            for name, animation in document['animations'].items():
                duration = options.duration if name == 'rotate_loop' else options.duration / 2
                for slot, tracks in animation['slots'].items():
                    if '_bevel_' not in slot:
                        continue
                    for frame in tracks['attachment'][1:]:
                        lookup = {m['name']: m for m in animation_pose_at(frame['time'] / duration,
                            options, self.prepared['width'], self.prepared['height'], name)}
                        mesh = lookup[slot]
                        points = chunks(mesh['vertices'], 2)
                        area = 0.
                        for index in range(0, len(mesh['triangles']), 3):
                            a, b, c = [points[mesh['triangles'][index + offset]] for offset in range(3)]
                            area += abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])) / 2
                        self.assertLess(area, .02, (axis, name, slot, area))

    def test_default_strip_mode_preserves_saved_v14_meshes_and_animations(self):
        require_historical_packages(self, [ROOT / 'qa/v1.5' / f'baseline-v1.4-{label}'
                                          for label in ('default', 'auto-bevel', 'manual')])
        for label in ('default', 'auto-bevel', 'manual'):
            folder = ROOT / 'qa/v1.5' / f'baseline-v1.4-{label}'
            manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
            options = TurnOptions(**manifest['options'])
            self.assertEqual(options.side_mode, 'strip')
            previous_file = next(p for p in folder.glob('*.json') if p.name != 'manifest.json')
            previous = json.loads(previous_file.read_text(encoding='utf-8'))
            with tempfile.TemporaryDirectory() as temporary:
                result = build_package(folder / 'images/front.png', folder / 'images/back.png',
                    folder / 'images/edge.png', temporary, options)
                current = json.loads(Path(result['json_path']).read_text(encoding='utf-8'))
            for section in ('animations', 'skins', 'bones', 'slots'):
                self.assertEqual(previous[section], current[section], (label, section))


if __name__ == '__main__':
    unittest.main(verbosity=2)
