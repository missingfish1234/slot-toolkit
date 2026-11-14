"""Physical ring calibration, shared triangles and camera containment."""
from dataclasses import replace
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spine_turn_core import TurnOptions, pose_at
from spine_turn_diamond import (adjust_diamond_alignment, diamond_geometry,
    diamond_rotation_bounds, get_diamond_alignment, project_vertex)
from test_v14_raised_region import closed_mesh_edge_counts


class DiamondAlignmentGeometryTests(unittest.TestCase):
    def setUp(self):
        self.width, self.height = 466, 368
        self.options = TurnOptions(model='diamond', diamond_table_y=.346685,
            diamond_table_width=.59109, diamond_table_depth=.639791,
            diamond_waist_y=.128, diamond_waist_width=.966, diamond_waist_depth=.83,
            diamond_girdle_height=.005, diamond_tip_y=-.498,
            diamond_view_tilt=23.6492, diamond_ring_phase=22.5,
            diamond_shine_enabled=False, diamond_sparkles_enabled=False)

    def test_elliptical_rings_form_a_closed_convex_shell_with_true_triangle_normals(self):
        specs = diamond_geometry(self.options, self.width, self.height)
        self.assertGreater(sum(spec['zone'] == 'crown' for spec in specs), self.options.diamond_facets)
        points = [point for spec in specs for point in spec['model']]
        for spec in specs:
            normal, origin = spec['normal_coefficients'], spec['model'][0]
            length = math.sqrt(sum(value * value for value in normal))
            for point in points:
                self.assertLessEqual(sum(normal[j] * (point[j] - origin[j]) for j in range(3)) / length, 1e-5)
        meshes = pose_at(41, self.options, self.width, self.height)
        self.assertEqual(set(closed_mesh_edge_counts(meshes).values()), {2})
        wire = get_diamond_alignment(self.options, self.width, self.height)
        self.assertEqual(sum(face['zone'] == 'crown' for face in wire['faces']), self.options.diamond_facets)
        self.assertTrue(any(edge['internal'] and edge['zone'] == 'crown' for edge in wire['edges']))

    def test_wireframe_matches_production_at_nonunit_static_z_for_both_axes(self):
        for axis in ('x', 'y'):
            options = replace(self.options, axis=axis, z_scale=1.3)
            meshes = pose_at(0, options, self.width, self.height)
            positions = [tuple(mesh['vertices'][i:i+2]) for mesh in meshes for i in range(0, len(mesh['vertices']), 2)]
            wire = get_diamond_alignment(options, self.width, self.height)
            for node in wire['nodes'].values():
                x, y = node['point'][0] * self.width, node['point'][1] * self.height
                self.assertLess(min(math.hypot(x - px, y - py) for px, py in positions), 1e-8)

    def test_inverse_depth_drag_keeps_opposite_real_upper_rim_at_nonunit_z(self):
        for ring in ('table', 'waist'):
            for direction in ('front', 'back'):
                options = replace(self.options, z_scale=1.3)
                before = get_diamond_alignment(options, self.width, self.height)
                handle, opposite = f'{ring}_{direction}', f'{ring}_{"back" if direction == "front" else "front"}'
                target = before['handles'][handle]['point']
                target = (target[0], target[1] + (-.005 if direction == 'front' else .005))
                result = adjust_diamond_alignment(options, handle, target, self.width, self.height)
                after = get_diamond_alignment(replace(options, **result), self.width, self.height)
                self.assertAlmostEqual(after['handles'][handle]['point'][1], target[1], places=12)
                self.assertAlmostEqual(after['handles'][opposite]['point'][1], before['handles'][opposite]['point'][1], places=12)
                self.assertEqual(after['handles']['waist_left']['xyz'][1], after['nodes']['waist_top:3']['xyz'][1])

    def test_rotation_bounds_contain_deep_models_for_all_angles_and_both_axes(self):
        for axis in ('x', 'y'):
            options = replace(self.options, axis=axis, diamond_table_depth=.85,
                diamond_waist_depth=1.7, z_scale=1.4, z_bounce_enabled=True, peak_z_scale=1.8)
            bounds = diamond_rotation_bounds(options, self.width, self.height)
            center = options.diamond_center_x * self.width
            for angle in range(0, 361, 7):
                for spec in diamond_geometry(options, self.width, self.height):
                    for x, y, z in spec['model']:
                        px, py, _ = project_vertex((x, y, z * options.z_scale * options.peak_z_scale), angle,
                                                   axis, options.diamond_view_tilt, center)
                        self.assertLessEqual(bounds['left'] - 1e-7, px)
                        self.assertGreaterEqual(bounds['right'] + 1e-7, px)
                        self.assertLessEqual(bounds['bottom'] - 1e-7, py)
                        self.assertGreaterEqual(bounds['top'] + 1e-7, py)


if __name__ == '__main__':
    unittest.main()
