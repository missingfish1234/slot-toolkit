"""Concave alpha boundaries, holes/islands, winding and protected topology."""
from io import BytesIO
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spine_turn_contour import analyze_irregular_outline, signed_area


def canvas(size=(64, 64)):
    return Image.new('RGBA', size)


def contains(point, polygon):
    x, y = point
    crossings = 0
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if (a[1] > y) != (b[1] > y) and a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1]) > x:
            crossings += 1
    return bool(crossings % 2)


def selected_at(info, x, y):
    width, height = info['source_size']
    point = (x + .5) / width - .5, .5 - (y + .5) / height
    return bool(sum(contains(point, loop) for loop in info['loops']) % 2)


def pixel_loops(info):
    width, height = info['source_size']
    return [[((x + .5) * width, (.5 - y) * height) for x, y in loop] for loop in info['loops']]


class IrregularContourTests(unittest.TestCase):
    def assert_exact_mask(self, image, info, threshold=16):
        expected = np.asarray(image.convert('RGBA'))[:, :, 3] >= threshold
        actual = np.asarray([[selected_at(info, x, y) for x in range(image.width)] for y in range(image.height)])
        self.assertTrue(np.array_equal(expected, actual))
        self.assertAlmostEqual(info['simplified_area_px'], info['pixel_area'])

    def assert_simple(self, loop):
        self.assertGreaterEqual(len(loop), 3)
        self.assertEqual(len(set(loop)), len(loop))
        def cross(a, b, c):
            return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        def on(point, a, b):
            return abs(cross(a, b, point)) < 1e-10 and min(a[0], b[0]) - 1e-10 <= point[0] <= max(a[0], b[0]) + 1e-10 and min(a[1], b[1]) - 1e-10 <= point[1] <= max(a[1], b[1]) + 1e-10
        edges = list(zip(loop, loop[1:] + loop[:1]))
        for i, (a, b) in enumerate(edges):
            for j, (c, d) in enumerate(edges[i + 1:], i + 1):
                if j == i + 1 or (i == 0 and j == len(edges) - 1):
                    continue
                proper = cross(a, b, c) * cross(a, b, d) < -1e-12 and cross(c, d, a) * cross(c, d, b) < -1e-12
                self.assertFalse(proper or on(a, c, d) or on(b, c, d) or on(c, a, b) or on(d, a, b))

    def test_offcenter_l_shape_uses_pixel_cell_bounds_and_original_canvas_center(self):
        image = canvas((80, 48))
        ImageDraw.Draw(image).polygon([(8, 5), (31, 5), (31, 15), (19, 15), (19, 36), (8, 36)], fill='white')
        info = analyze_irregular_outline(image, simplify_tolerance=0)
        self.assertEqual(info['loop_roles'], ['outer'])
        self.assertEqual(info['source_alpha_bounds'], [8, 5, 32, 37])
        self.assertEqual(info['loop_vertex_counts'], [6])
        self.assertGreater(signed_area(info['loops'][0]), 0)
        self.assertAlmostEqual(min(p[0] for p in info['loops'][0]), 8 / 80 - .5)
        self.assertAlmostEqual(max(p[1] for p in info['loops'][0]), .5 - 5 / 48)
        self.assertFalse(selected_at(info, 27, 29))
        self.assert_exact_mask(image, info)

    def test_u_notch_is_not_replaced_by_convex_hull_even_at_large_requested_tolerance(self):
        image = canvas()
        draw = ImageDraw.Draw(image)
        draw.rectangle((6, 6, 57, 57), fill='white')
        draw.rectangle((18, 6, 45, 43), fill=(0, 0, 0, 0))
        info = analyze_irregular_outline(image, simplify_tolerance=20)
        self.assertEqual((info['components'], info['holes']), (1, 0))
        self.assertFalse(selected_at(info, 32, 30))
        self.assertTrue(selected_at(info, 32, 50))
        self.assertGreaterEqual(info['protected_notch_count'], 2)
        self.assert_simple(info['loops'][0])

    def test_star_preserves_reflex_corners_and_has_no_self_intersection(self):
        image = canvas()
        points = [(round(32 + (26 if i % 2 == 0 else 11) * math.sin(i * math.pi / 5)),
                   round(32 - (26 if i % 2 == 0 else 11) * math.cos(i * math.pi / 5))) for i in range(10)]
        ImageDraw.Draw(image).polygon(points, fill='white')
        info = analyze_irregular_outline(image, simplify_tolerance=6)
        self.assertEqual(info['components'], 1)
        self.assertGreaterEqual(info['protected_notch_count'], 5)
        self.assert_simple(info['loops'][0])
        self.assertTrue(selected_at(info, 32, 32))

    def test_donut_keeps_cw_hole_and_exact_zero_tolerance_pixel_area(self):
        image = canvas()
        draw = ImageDraw.Draw(image)
        draw.ellipse((4, 4, 59, 59), fill='white')
        draw.ellipse((21, 21, 42, 42), fill=(0, 0, 0, 0))
        info = analyze_irregular_outline(image, simplify_tolerance=0)
        self.assertEqual(info['loop_roles'], ['outer', 'hole'])
        self.assertEqual(info['loop_parents'], [None, 0])
        self.assertGreater(signed_area(info['loops'][0]), 0)
        self.assertLess(signed_area(info['loops'][1]), 0)
        self.assert_exact_mask(image, info)

    def test_multiple_holes_and_foreground_island_inside_a_hole_keep_hierarchy(self):
        image = canvas((100, 64))
        draw = ImageDraw.Draw(image)
        draw.rectangle((2, 2, 97, 61), fill='white')
        draw.rectangle((10, 10, 44, 53), fill=(0, 0, 0, 0))
        draw.rectangle((58, 14, 86, 48), fill=(0, 0, 0, 0))
        draw.rectangle((20, 20, 31, 37), fill='white')
        info = analyze_irregular_outline(image, simplify_tolerance=0)
        self.assertEqual((info['components'], info['holes']), (2, 2))
        self.assertEqual(info['loop_roles'], ['outer', 'hole', 'outer', 'hole'])
        self.assertEqual(info['loop_parents'], [None, 0, 1, 0])
        self.assert_exact_mask(image, info)

    def test_multiple_components_are_preserved_not_just_the_largest(self):
        image = canvas()
        draw = ImageDraw.Draw(image)
        draw.rectangle((4, 4, 27, 31), fill='white')
        draw.rectangle((41, 35, 54, 47), fill='white')
        draw.point((60, 60), fill='white')
        info = analyze_irregular_outline(image)
        self.assertEqual(info['components'], 3)
        self.assertEqual(info['loop_roles'], ['outer'] * 3)
        self.assertTrue(selected_at(info, 60, 60))
        self.assertTrue(selected_at(info, 46, 41))
        self.assertFalse(selected_at(info, 34, 34))

    def test_diagonal_pixel_contacts_split_into_simple_touching_loops(self):
        image = canvas((10, 10))
        for point in ((2, 2), (3, 3), (4, 4)):
            image.putpixel(point, (255, 255, 255, 255))
        info = analyze_irregular_outline(image)
        self.assertEqual((info['components'], info['holes']), (3, 0))
        self.assertEqual(info['loop_vertex_counts'], [4, 4, 4])
        self.assertEqual(info['shared_grid_corner_count'], 2)
        for loop in info['loops']:
            self.assert_simple(loop)
        self.assert_exact_mask(image, info)

    def test_hole_touching_exterior_at_one_grid_corner_does_not_make_bow_tie(self):
        image = canvas((8, 8))
        draw = ImageDraw.Draw(image)
        draw.rectangle((1, 1, 5, 5), fill='white')
        image.putpixel((1, 1), (0, 0, 0, 0))
        image.putpixel((2, 2), (0, 0, 0, 0))
        info = analyze_irregular_outline(image, simplify_tolerance=0)
        self.assertEqual(info['loop_roles'], ['outer', 'hole'])
        self.assertEqual(info['loop_parents'], [None, 0])
        for loop in info['loops']:
            self.assert_simple(loop)
        self.assert_exact_mask(image, info)

    def test_one_pixel_open_channel_stays_open_under_simplification(self):
        image = canvas((36, 36))
        draw = ImageDraw.Draw(image)
        draw.rectangle((2, 2, 33, 33), fill='white')
        draw.rectangle((10, 10, 24, 24), fill=(0, 0, 0, 0))
        draw.rectangle((24, 16, 33, 16), fill=(0, 0, 0, 0))
        info = analyze_irregular_outline(image, simplify_tolerance=8)
        self.assertEqual(info['holes'], 0)
        self.assertFalse(selected_at(info, 16, 16))
        self.assertFalse(selected_at(info, 29, 16))
        self.assert_simple(info['loops'][0])

    def test_threshold_ignores_faint_island_but_never_discards_selected_small_component(self):
        image = canvas((32, 32))
        draw = ImageDraw.Draw(image)
        draw.rectangle((3, 3, 15, 15), fill='white')
        draw.rectangle((23, 23, 25, 25), fill=(255, 0, 0, 8))
        image.putpixel((20, 10), (0, 255, 0, 16))
        self.assertEqual(analyze_irregular_outline(image, alpha_threshold=17)['components'], 1)
        self.assertEqual(analyze_irregular_outline(image, alpha_threshold=16)['components'], 2)
        self.assertEqual(analyze_irregular_outline(image, alpha_threshold=1)['components'], 3)

    def test_tolerance_is_bounded_and_preserves_pixel_cell_extrema(self):
        image = canvas((40, 40))
        ImageDraw.Draw(image).ellipse((3, 3, 36, 36), fill='white')
        exact = analyze_irregular_outline(image, simplify_tolerance=0)
        simple = analyze_irregular_outline(image, simplify_tolerance=1.5)
        self.assertLessEqual(simple['vertex_count'], exact['vertex_count'])
        self.assertEqual(simple['source_alpha_bounds'], exact['source_alpha_bounds'])
        original, simplified = pixel_loops(exact)[0], pixel_loops(simple)[0]
        def distance(p, a, b):
            dx, dy = b[0] - a[0], b[1] - a[1]
            t = max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
            return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)
        self.assertLessEqual(max(min(distance(point, a, b) for a, b in zip(simplified, simplified[1:] + simplified[:1]))
                                 for point in original), 1.5 + 1e-8)
        for coordinate in (0, 1):
            self.assertAlmostEqual(min(p[coordinate] for p in simplified), min(p[coordinate] for p in original))
            self.assertAlmostEqual(max(p[coordinate] for p in simplified), max(p[coordinate] for p in original))

    def test_per_loop_and_total_vertex_limits_fail_explicitly_without_convex_fallback(self):
        image = canvas((20, 20))
        ImageDraw.Draw(image).rectangle((3, 3, 16, 16), fill='white')
        with self.assertRaisesRegex(ValueError, '上限'):
            analyze_irregular_outline(image, max_vertices=3)
        many = canvas((60, 45))
        for index in range(130):
            many.putpixel((2 + index % 15 * 3, 2 + index // 15 * 3), (255, 255, 255, 255))
        with self.assertRaisesRegex(ValueError, '512'):
            analyze_irregular_outline(many)

    def test_no_alpha_empty_and_full_canvas_are_rejected(self):
        for image in (Image.new('RGB', (8, 8), 'white'), canvas((8, 8)), Image.new('RGBA', (8, 8), 'white')):
            with self.subTest(mode=image.mode), self.assertRaises(ValueError):
                analyze_irregular_outline(image)

    def test_impossible_component_budget_is_rejected_before_quadratic_hierarchy_work(self):
        image = canvas((60, 45))
        for index in range(171):
            image.putpixel((2 + index % 15 * 3, 2 + index // 15 * 3), (255, 255, 255, 255))
        with patch('spine_turn_contour._irregular_parents', side_effect=AssertionError('Hierarchy must not run.')):
            with self.assertRaisesRegex(ValueError, '512'):
                analyze_irregular_outline(image)

    def test_palette_transparency_is_supported_without_changing_source(self):
        image = Image.new('P', (16, 16))
        image.putpalette([0, 0, 0, 255, 255, 255] + [0] * (768 - 6))
        image.info['transparency'] = 0
        ImageDraw.Draw(image).rectangle((3, 4, 11, 12), fill=1)
        before, metadata = image.tobytes(), dict(image.info)
        info = analyze_irregular_outline(image)
        self.assertEqual(info['components'], 1)
        self.assertEqual(image.tobytes(), before)
        self.assertEqual(image.info, metadata)

    def test_deterministic_output_and_source_rgba_bytes_remain_unchanged(self):
        image = canvas()
        draw = ImageDraw.Draw(image)
        draw.polygon([(7, 8), (51, 8), (51, 19), (35, 19), (35, 51), (7, 51)], fill=(20, 180, 90, 255))
        draw.rectangle((14, 25, 22, 39), fill=(190, 0, 90, 0))
        before = BytesIO(); image.save(before, format='PNG')
        first = analyze_irregular_outline(image)
        self.assertEqual(first, analyze_irregular_outline(image))
        after = BytesIO(); image.save(after, format='PNG')
        self.assertEqual(before.getvalue(), after.getvalue())

    def test_invalid_parameters_do_not_silently_coerce(self):
        image = canvas((12, 12)); ImageDraw.Draw(image).rectangle((2, 2, 9, 9), fill='white')
        for parameters in ({'alpha_threshold': 0}, {'alpha_threshold': True}, {'alpha_threshold': 256},
                           {'simplify_tolerance': -1}, {'simplify_tolerance': float('nan')},
                           {'simplify_tolerance': float('inf')}, {'max_vertices': 2},
                           {'max_vertices': 257}, {'max_vertices': True}):
            with self.subTest(parameters=parameters), self.assertRaises(ValueError):
                analyze_irregular_outline(image, **parameters)


if __name__ == '__main__':
    unittest.main(verbosity=2)
