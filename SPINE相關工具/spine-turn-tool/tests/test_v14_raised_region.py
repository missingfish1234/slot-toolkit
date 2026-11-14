"""Independent manual raised-region validity and closed-surface checks."""
from collections import Counter, defaultdict
from dataclasses import replace
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from fixture_availability import require_historical_packages

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spine_turn_core import (TurnOptions, prepare_images, resolve_options, validate_raised_region,
    pose_at, animation_pose_at, build_package, build_skeleton)


TRIANGLE = ((-.27, -.24), (.29, -.18), (.11, .30))
PENTAGON = ((-.20, -.25), (.24, -.23), (.31, .06), (.05, .30), (-.27, .14))


def chunks(values, size):
    return [tuple(values[index:index + size]) for index in range(0, len(values), size)]


def vector(a, b):
    return tuple(y - x for x, y in zip(a, b))


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def key(point):
    return tuple(round(value, 7) for value in point)


def closed_mesh_edge_counts(surfaces):
    """Split T-junctions before checking the physical triangulated shell."""
    edges = []
    vertices = {}
    for surface in surfaces:
        model = chunks(surface['model_vertices'], 3)
        vertices.update({key(p): p for p in model})
        triangles = surface['triangles']
        for index in range(0, len(triangles), 3):
            a, b, c = [model[triangles[index + offset]] for offset in range(3)]
            edges.extend(((a, b), (b, c), (c, a)))
    counts = Counter()
    for a, b in edges:
        direction = vector(a, b)
        squared_length = dot(direction, direction)
        if squared_length < 1e-14:
            continue
        splits = {}
        for point in vertices.values():
            t = dot(vector(a, point), direction) / squared_length
            if -.00000001 <= t <= 1.00000001:
                expected = tuple(x + t * d for x, d in zip(a, direction))
                if sum((x - y) ** 2 for x, y in zip(expected, point)) < 1e-12:
                    splits[key(point)] = (max(0, min(1, t)), point)
        points = [point for _, point in sorted(splits.values(), key=lambda row: row[0])]
        for first, second in zip(points, points[1:]):
            if key(first) != key(second):
                counts[tuple(sorted((key(first), key(second))))] += 1
    return counts


class ManualRaisedRegionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prepared = prepare_images(ROOT / 'assets/demo-octagon.png',
            options=TurnOptions(shape='polygon'))
        cls.base = resolve_options(cls.prepared, TurnOptions(shape='polygon',
            bevel_width=0, bevel_depth=.25, thickness=32, shade_edge=False, shade_faces=False))

    def resolve(self, points):
        return resolve_options(self.prepared, replace(self.base, raised_contour_points=points))

    def test_offcenter_three_and_five_vertex_regions_override_zero_auto_width(self):
        for points in (TRIANGLE, PENTAGON):
            with self.subTest(vertices=len(points)):
                options = self.resolve(points)
                self.assertEqual(options.bevel_width, 0)
                self.assertEqual(len(options.raised_contour_points), len(points))
                surfaces = pose_at(35, options, self.prepared['width'], self.prepared['height'])
                self.assertTrue(any(surface['kind'] == 'bevel' for surface in surfaces))
                self.assertTrue(all(len(surface['vertices']) // 2 >= 3 for surface in surfaces))
                counts = closed_mesh_edge_counts(surfaces)
                self.assertTrue(counts)
                self.assertEqual(set(counts.values()), {2}, 'The raised solid has open or nonmanifold physical edges.')

    def test_shared_vertices_stay_connected_at_all_angles_and_dynamic_times(self):
        for points in (TRIANGLE, PENTAGON):
            options = replace(self.resolve(points), z_bounce_enabled=True, peak_z_scale=1.35)
            for axis in ('x', 'y'):
                axis_options = replace(options, axis=axis)
                for angle in range(0, 361, 10):
                    surfaces = pose_at(angle, axis_options, self.prepared['width'], self.prepared['height'])
                    self.assert_shared_vertices(surfaces)
                for index in range(101):
                    surfaces = animation_pose_at(index / 100, axis_options,
                        self.prepared['width'], self.prepared['height'])
                    self.assert_shared_vertices(surfaces)

    def assert_shared_vertices(self, surfaces):
        groups = defaultdict(list)
        for surface in surfaces:
            for model, projected in zip(chunks(surface['model_vertices'], 3), chunks(surface['vertices'], 2)):
                groups[key(model)].append(projected)
        shared_count = 0
        for group in groups.values():
            if len(group) > 1:
                shared_count += 1
                for point in group[1:]:
                    self.assertLess(math.dist(group[0], point), .000001)
        self.assertGreater(shared_count, 12)

    def test_concave_crossed_outside_and_insufficient_gap_are_rejected(self):
        outer = self.base.contour_points
        invalid = [
            ((-.25, -.2), (.25, -.2), (0, 0), (.25, .2), (-.25, .2)),
            ((-.25, -.2), (.25, .2), (-.25, .2), (.25, -.2)),
            ((-.25, -.2), (.8, -.2), (.1, .2)),
            (outer[0], (-.1, -.1), (.1, .1)),
            ((0, 0), (.1, .1)),
            tuple((.2 * math.cos(i * 2 * math.pi / 33), .2 * math.sin(i * 2 * math.pi / 33)) for i in range(33)),
        ]
        for points in invalid:
            with self.subTest(points=points):
                with self.assertRaises(ValueError):
                    validate_raised_region(outer, points, self.prepared['width'], self.prepared['height'])

    def test_zero_height_manual_region_remains_finite_and_closed(self):
        options = replace(self.resolve(PENTAGON), bevel_depth=0)
        surfaces = pose_at(47, options, self.prepared['width'], self.prepared['height'])
        self.assertEqual(set(closed_mesh_edge_counts(surfaces).values()), {2})
        for surface in surfaces:
            self.assertTrue(all(math.isfinite(value) for value in surface['vertices']))
            if surface['kind'] == 'bevel':
                self.assertAlmostEqual(abs(surface['normal'][2]), 1, places=7)

    def test_each_manual_ring_triangle_has_its_own_physical_normal(self):
        for points in (TRIANGLE, PENTAGON):
            options = self.resolve(points)
            for surface in pose_at(37, options, self.prepared['width'], self.prepared['height']):
                if surface['kind'] != 'bevel':
                    continue
                model = chunks(surface['model_vertices'], 3)
                self.assertEqual(len(model), 3)
                a, b = vector(model[0], model[1]), vector(model[0], model[2])
                normal = (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
                length = math.sqrt(dot(normal, normal))
                self.assertGreater(length, 1e-8)
                normal = tuple(value / length for value in normal)
                self.assertAlmostEqual(abs(dot(normal, surface['normal'])), 1, places=7)

    def test_manual_facet_culling_events_have_negligible_projected_area_on_both_axes(self):
        for axis in ('x', 'y'):
            options = replace(self.resolve(PENTAGON), axis=axis,
                z_bounce_enabled=True, peak_z_scale=1.35)
            document = build_skeleton(self.prepared, options)
            for name, animation in document['animations'].items():
                duration = options.duration if name == 'rotate_loop' else options.duration / 2
                for slot, tracks in animation['slots'].items():
                    if '_bevel_' not in slot:
                        continue
                    for frame in tracks['attachment'][1:]:
                        surfaces = {m['name']: m for m in animation_pose_at(frame['time'] / duration,
                            options, self.prepared['width'], self.prepared['height'], name)}
                        surface = surfaces[slot]
                        points = chunks(surface['vertices'], 2)
                        area = 0.
                        for index in range(0, len(surface['triangles']), 3):
                            a, b, c = [points[surface['triangles'][index + offset]] for offset in range(3)]
                            area += abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])) / 2
                        self.assertLess(area, .02, (axis, name, slot, area))

    def test_manual_points_are_retained_in_export_manifest(self):
        options = self.resolve(PENTAGON)
        with tempfile.TemporaryDirectory() as temporary:
            result = build_package(ROOT / 'assets/demo-octagon.png', None, None, temporary, options)
            manifest = json.loads(Path(result['manifest_path']).read_text(encoding='utf-8'))
            self.assertEqual(len(manifest['options']['raised_contour_points']), 5)
            self.assertEqual(manifest['options']['bevel_width'], 0)

    def test_empty_manual_region_preserves_saved_v13_animation_and_mesh_fixtures(self):
        require_historical_packages(self, [ROOT / 'qa/v1.4' / f'baseline-v1.3-{label}'
                                          for label in ('default', 'y-z', 'auto-bevel')])
        for label in ('default', 'y-z', 'auto-bevel'):
            folder = ROOT / 'qa/v1.4' / f'baseline-v1.3-{label}'
            manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
            options = TurnOptions(**manifest['options'])
            self.assertFalse(options.raised_contour_points)
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
