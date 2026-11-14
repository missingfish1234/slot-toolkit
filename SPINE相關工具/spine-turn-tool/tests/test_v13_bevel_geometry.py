"""Physical connectivity and painting identity on the asymmetric user octagon."""
from dataclasses import replace
import json
import math
from pathlib import Path
import sys
import unittest

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spine_turn_core import (TurnOptions, prepare_images, resolve_options, pose_at,
    animation_pose_at, build_skeleton)
from spine_turn_preview import render_pose

USER_IMAGE = Path(r'D:\SLOT工作區\727_MoneyGong\圖騰靜態張\Symbol_Multiplier.png')


def chunks(values, size):
    return [tuple(values[index:index + size]) for index in range(0, len(values), size)]


def distance(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def triangle_area(surface):
    points = chunks(surface['vertices'], 2)
    triangles = surface.get('triangles', [0, 1, 2, 2, 3, 0])
    total = 0.
    for index in range(0, len(triangles), 3):
        a, b, c = [points[triangles[index + offset]] for offset in range(3)]
        total += abs((b[0] - a[0]) * (c[1] - a[1]) -
            (b[1] - a[1]) * (c[0] - a[0])) / 2
    return total


@unittest.skipUnless(USER_IMAGE.is_file(), 'Local user artwork is not part of the generic test package.')
class BevelConnectivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prepared = prepare_images(USER_IMAGE, options=TurnOptions(shape='polygon'))
        cls.options = resolve_options(cls.prepared, TurnOptions(shape='polygon',
            bevel_width=.07, bevel_depth=.25, thickness=32, segments=32,
            shade_faces=False, shade_edge=False, z_bounce_enabled=True,
            peak_z_scale=1.3, z_bounce_start=.1, z_bounce_apex=.2, z_bounce_end=.45))

    def assert_cap_ring_seams(self, surfaces):
        lookup = {surface['name']: surface for surface in surfaces}
        count = len(self.options.contour_points)
        for side in ('front', 'back'):
            cap = chunks(lookup[side]['vertices'], 2)
            for index in range(count):
                bevel = chunks(lookup[f'{side}_bevel_{index:03d}']['vertices'], 2)
                self.assertLess(distance(cap[index], bevel[3]), 1e-7)
                self.assertLess(distance(cap[(index + 1) % count], bevel[2]), 1e-7)

    def test_asymmetric_back_mirrors_uv_but_not_physical_contour(self):
        count = len(self.options.contour_points)
        self.assertEqual(count, 8)
        for axis in ('x', 'y'):
            options = replace(self.options, axis=axis)
            lookup = {m['name']: m for m in pose_at(41, options,
                self.prepared['width'], self.prepared['height'])}
            front = chunks(lookup['front']['model_vertices'], 3)
            back = chunks(lookup['back']['model_vertices'], 3)
            front_uv = chunks(lookup['front']['uvs'], 2)
            back_uv = chunks(lookup['back']['uvs'], 2)
            for a, b, uv_a, uv_b in zip(front, back, front_uv, back_uv):
                self.assertAlmostEqual(a[0], b[0], places=9)
                self.assertAlmostEqual(a[1], b[1], places=9)
                self.assertAlmostEqual(a[2], -b[2], places=9)
                self.assertAlmostEqual(uv_a[0] + uv_b[0] if axis == 'y' else uv_a[0] - uv_b[0],
                    1 if axis == 'y' else 0, places=9)
                self.assertAlmostEqual(uv_a[1] - uv_b[1] if axis == 'y' else uv_a[1] + uv_b[1],
                    0 if axis == 'y' else 1, places=9)

    def test_side_bevel_and_cap_share_physical_edges_at_all_angles(self):
        for angle in range(0, 361, 5):
            surfaces = pose_at(angle, self.options, self.prepared['width'], self.prepared['height'])
            self.assert_cap_ring_seams(surfaces)
            lookup = {surface['name']: surface for surface in surfaces}
            rims = [chunks(m['model_vertices'], 3) for m in surfaces if m['kind'] == 'edge']
            front_rim_vertices = [p for quad in rims for p in quad[:2]]
            back_rim_vertices = [p for quad in rims for p in quad[2:]]
            for side, candidates in (('front', front_rim_vertices), ('back', back_rim_vertices)):
                for index in range(len(self.options.contour_points)):
                    outer = chunks(lookup[f'{side}_bevel_{index:03d}']['model_vertices'], 3)[:2]
                    for point in outer:
                        self.assertLess(min(distance(point, rim) for rim in candidates), 1e-7)

    def test_dynamic_interpolated_caps_and_bevels_remain_connected(self):
        for index in range(501):
            self.assert_cap_ring_seams(animation_pose_at(index / 500, self.options,
                self.prepared['width'], self.prepared['height']))

    def test_bevel_attachment_switch_happens_only_when_projected_area_is_zero(self):
        document = build_skeleton(self.prepared, self.options)
        for name, animation in document['animations'].items():
            duration = self.options.duration if name == 'rotate_loop' else self.options.duration / 2
            for slot, timelines in animation['slots'].items():
                if '_bevel_' not in slot:
                    continue
                for frame in timelines['attachment'][1:]:
                    progress = frame.get('time', 0) / duration
                    lookup = {m['name']: m for m in animation_pose_at(progress, self.options,
                        self.prepared['width'], self.prepared['height'], name)}
                    self.assertLess(triangle_area(lookup[slot]), .02,
                        msg=f'Visible-area pop for {name}/{slot} at {progress}: {triangle_area(lookup[slot])}')

    def test_unshaded_front_cap_preserves_original_interior_pixels(self):
        options = replace(self.options, z_bounce_enabled=False, base_scale=1,
            bounce_enabled=False, z_offset=0, shade_faces=False, shade_edge=False)
        width, height = int(self.prepared['width']), int(self.prepared['height'])
        image = render_pose(self.prepared, options, 0, size=(width, height),
            background='transparent', progress=0, show_ground=False,
            camera={'scale': 1, 'origin_x': width / 2, 'origin_y': height / 2})
        expected = np.asarray(self.prepared['front']).astype(np.int16)
        actual = np.asarray(image).astype(np.int16)
        mask = Image.fromarray(np.where(expected[:, :, 3] >= 250, 255, 0).astype(np.uint8))
        mask = np.asarray(mask.filter(ImageFilter.MinFilter(5))) == 255
        # The cap retains exact source UVs. The outer bevel intentionally
        # samples one source pixel inward to hide its existing alpha fringe.
        cap = next(surface for surface in pose_at(0, options, width, height)
            if surface['name'] == 'front')
        inner = chunks(cap['vertices'], 2)[:-1]
        cap_mask = Image.new('L', (width, height), 0)
        ImageDraw.Draw(cap_mask).polygon([(x + width / 2, height / 2 - y) for x, y in inner], fill=255)
        mask &= np.asarray(cap_mask.filter(ImageFilter.MinFilter(3))) == 255
        difference = np.abs(expected[:, :, :3] - actual[:, :, :3])[mask]
        self.assertLess(float(difference.mean()), 1.0)
        self.assertLessEqual(float(np.quantile(difference, .99)), 2.0)
        self.assertLessEqual(int(np.abs(expected[:, :, 3] - actual[:, :, 3])[mask].max()), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
