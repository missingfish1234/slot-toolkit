"""Independent source-visibility and affine UV continuity checks."""
from dataclasses import replace
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spine_turn_core import TurnOptions, prepare_images, resolve_options
from spine_turn_diamond import (_base_geometry, _safe_uv, _source_material_uvs,
                                diamond_geometry, project_vertex, view_normal)
from spine_turn_diamond_cuts import split_diamond_geometry


def facing(spec, angle, tilt, scale):
    x, y, z = spec['normal_coefficients']
    return view_normal((x * scale, y * scale, z), angle, 'y', tilt)[2]


def projected_uv(spec, angle, options, width, height):
    path = 'front' if angle == 0 else 'back'
    boundary = getattr(options, f'diamond_{path}_uv_points')
    return tuple(_safe_uv(*project_vertex((x, y, z * options.z_scale), angle, 'y',
                         options.diamond_view_tilt, options.diamond_center_x * width)[:2],
                         boundary, width, height) for x, y, z in spec['model'])


def barycentric(point, a, b, c):
    first, second, offset = ([b[i]-a[i] for i in range(3)], [c[i]-a[i] for i in range(3)],
                              [point[i]-a[i] for i in range(3)])
    dot = lambda x, y: sum(p*q for p, q in zip(x, y))
    aa, ab, bb, pa, pb = dot(first, first), dot(first, second), dot(second, second), dot(offset, first), dot(offset, second)
    divisor = aa * bb - ab * ab
    v, w = (bb * pa - ab * pb) / divisor, (aa * pb - ab * pa) / divisor
    return (1-v-w, v, w)


class PavilionMaterialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = TurnOptions(model='diamond', trim_transparent=False, diamond_view_tilt=24,
            diamond_ring_phase=22.5, z_scale=1.3,
            diamond_shine_enabled=False, diamond_sparkles_enabled=False)
        prepared = prepare_images(ROOT/'assets/demo-diamond-aligned.png', options=base)
        cls.options = resolve_options(prepared, base)
        cls.width, cls.height = prepared['width'], prepared['height']
        cls.geometry = _base_geometry(cls.options, cls.width, cls.height)

    def material(self, spec):
        o = self.options
        return _source_material_uvs(spec, self.geometry, self.width, self.height,
            o.diamond_view_tilt, o.z_scale, o.diamond_center_x*self.width,
            o.diamond_front_uv_points, o.diamond_back_uv_points, allow_hidden_reuse=True)

    def test_initial_source_visible_faces_retain_exact_original_projection(self):
        o, checked = self.options, 0
        for spec in self.geometry:
            source_angle = 0 if facing(spec, 0, o.diamond_view_tilt, o.z_scale) >= 0 else 180
            if facing(spec, source_angle, o.diamond_view_tilt, o.z_scale) > 1e-9:
                path, uvs = self.material(spec)
                self.assertEqual(path, 'front' if source_angle == 0 else 'back')
                self.assertEqual(uvs, projected_uv(spec, source_angle, o, self.width, self.height))
                checked += 1
        self.assertGreater(checked, 16)

    def test_double_hidden_pavilion_borrows_visible_pavilion_with_rim_rim_tip_roles(self):
        o, checked = self.options, 0
        for spec in self.geometry:
            if spec['zone'] != 'pavilion' or any(facing(spec, angle, o.diamond_view_tilt, o.z_scale) > 1e-9 for angle in (0, 180)):
                continue
            path, uvs = self.material(spec)
            source_angle = 0 if path == 'front' else 180
            candidates = [candidate for candidate in self.geometry if candidate['zone'] == 'pavilion' and
                          facing(candidate, source_angle, o.diamond_view_tilt, o.z_scale) > 1e-9]
            donors = [candidate for candidate in candidates if
                      projected_uv(candidate, source_angle, o, self.width, self.height) == uvs]
            self.assertTrue(donors)
            self.assertNotEqual(uvs, projected_uv(spec, source_angle, o, self.width, self.height))
            for donor in donors:
                self.assertEqual(spec['model'][2], donor['model'][2])
                self.assertGreater(donor['model'][0][1], donor['model'][2][1])
                self.assertEqual(donor['model'][0][1], donor['model'][1][1])
            checked += 1
        self.assertGreaterEqual(checked, 2)

    def test_material_cut_partition_preserves_the_same_affine_uv_at_every_shared_point(self):
        self.assert_affine_partition(self.options)

    def test_odd_facet_rotated_rings_use_true_rotation_center_for_back_material_partitions(self):
        self.assert_affine_partition(replace(self.options, diamond_facets=7, diamond_ring_phase=13,
                                            diamond_center_x=.015, diamond_waist_width=.92))

    def assert_affine_partition(self, options):
        region = (((-.23, -.30), (.23, -.30), (.23, .42), (-.23, .42)), 20., -10.)
        geometry = _base_geometry(options, self.width, self.height)
        split = diamond_geometry(replace(options, diamond_cut_regions=(region,)), self.width, self.height)
        source = {spec['name']: spec for spec in geometry}
        checked = 0
        for patch in split:
            original = source[patch['source']]
            path, uvs = _source_material_uvs(original, geometry, self.width, self.height,
                options.diamond_view_tilt, options.z_scale, options.diamond_center_x*self.width,
                options.diamond_front_uv_points, options.diamond_back_uv_points, allow_hidden_reuse=True)
            self.assertEqual(patch['material_path'], path)
            for point, actual in zip(patch['model'], patch['material_uvs']):
                matches = []
                for i in range(0, len(original['triangles']), 3):
                    ids = original['triangles'][i:i+3]
                    points = [original['model'][j] for j in ids]
                    weights = barycentric(point, *points)
                    if min(weights) < -1e-7:
                        continue
                    reconstructed = tuple(sum(weights[j]*points[j][k] for j in range(3)) for k in range(3))
                    if math.dist(point, reconstructed) > 1e-6:
                        continue
                    matches.append(tuple(sum(weights[j]*uvs[ids[j]][k] for j in range(3)) for k in range(2)))
                self.assertTrue(matches, (patch['name'], point))
                self.assertLess(min(math.dist(actual, expected) for expected in matches), 1e-8)
                checked += 1
        self.assertGreater(checked, 100)

    def test_legacy_high_tilt_keeps_original_uvs_and_explicit_alignment_optin_is_separate(self):
        options = replace(self.options, diamond_ring_phase=0, diamond_table_depth=0,
                          diamond_waist_depth=0, diamond_view_tilt=35, z_scale=1)
        legacy = _base_geometry(options, self.width, self.height)
        reused = 0
        for spec in legacy:
            path, actual = _source_material_uvs(spec, legacy, self.width, self.height, 35, options.z_scale, 0,
                options.diamond_front_uv_points, options.diamond_back_uv_points)
            angle = 0 if path == 'front' else 180
            self.assertEqual(actual, projected_uv(spec, angle, options, self.width, self.height))
            _, enabled = _source_material_uvs(spec, legacy, self.width, self.height, 35, options.z_scale, 0,
                options.diamond_front_uv_points, options.diamond_back_uv_points, allow_hidden_reuse=True)
            reused += enabled != actual
        self.assertGreater(reused, 0)
        explicit = replace(options, diamond_table_depth=options.diamond_table_width,
                           diamond_waist_depth=options.diamond_waist_width)
        self.assertEqual(_base_geometry(explicit, self.width, self.height), legacy)
        old_pose = __import__('spine_turn_core').pose_at(90, options, self.width, self.height)
        new_pose = __import__('spine_turn_core').pose_at(90, explicit, self.width, self.height)
        self.assertEqual([s['model_vertices'] for s in old_pose], [s['model_vertices'] for s in new_pose])
        self.assertNotEqual([s['uvs'] for s in old_pose], [s['uvs'] for s in new_pose])

    def test_cut_cache_separates_material_optin_for_numerically_identical_geometry(self):
        regions = ((((-.23, -.30), (.23, -.30), (.23, .42), (-.23, .42)), 20., -10.),)
        args = (self.geometry, regions, self.width, self.height, 24, 1.3,
                self.options.diamond_front_uv_points, self.options.diamond_back_uv_points)
        legacy = split_diamond_geometry(*args, allow_hidden_reuse=False)
        aligned = split_diamond_geometry(*args, allow_hidden_reuse=True)
        self.assertNotEqual(legacy, aligned)
        self.assertIs(split_diamond_geometry(*args, allow_hidden_reuse=False), legacy)
        self.assertIs(split_diamond_geometry(*args, allow_hidden_reuse=True), aligned)


if __name__ == '__main__':
    unittest.main()
