"""Convex silhouette, winding, centering, and exact-corner extrusion checks."""
import math
from pathlib import Path
import sys
import unittest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spine_turn_contour import (analyze_convex_outline, convex_outline,
    build_polygon_perimeter, perimeter_uvs, signed_area)


def octagon():
    image = Image.new('RGBA', (256, 256))
    ImageDraw.Draw(image).polygon([(76, 16), (180, 16), (240, 76), (240, 180),
        (180, 240), (76, 240), (16, 180), (16, 76)], fill=(130, 60, 220, 255))
    return image


def distance(point, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0, min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.dist(point, (a[0] + t * dx, a[1] + t * dy))


class ContourTests(unittest.TestCase):
    def test_transparent_octagon_is_convex_ccw_and_preserves_alpha_bounds(self):
        image = octagon()
        before = image.tobytes()
        bounds = image.getchannel('A').getbbox()
        trimmed = image.crop(bounds)
        info = analyze_convex_outline(trimmed)
        points = info['points']
        self.assertEqual(len(points), 8)
        self.assertGreater(signed_area(points), 0)
        self.assertEqual(min(p[0] for p in points), -.5)
        self.assertEqual(max(p[0] for p in points), .5)
        self.assertEqual(min(p[1] for p in points), -.5)
        self.assertEqual(max(p[1] for p in points), .5)
        self.assertFalse(info['concavity_warning'])
        self.assertLessEqual(info['simplification_max_error_px'], 1.5)
        self.assertEqual(image.tobytes(), before, 'Source art must remain unchanged.')

    def test_coordinates_use_supplied_canvas_and_do_not_recenter_hidden_margins(self):
        image = Image.new('RGBA', (350, 300))
        image.alpha_composite(octagon(), (70, 5))
        box = image.getchannel('A').getbbox()
        points = convex_outline(image)
        self.assertAlmostEqual(min(p[0] for p in points), box[0] / 350 - .5)
        self.assertAlmostEqual(max(p[1] for p in points), .5 - box[1] / 300)
        trimmed = convex_outline(image.crop(box))
        self.assertAlmostEqual(min(p[0] for p in trimmed), -.5)
        self.assertAlmostEqual(max(p[1] for p in trimmed), .5)

    def test_small_bottom_tab_support_edge_survives_simplification(self):
        image = Image.new('RGBA', (220, 220))
        ImageDraw.Draw(image).polygon([(30, 70), (70, 25), (150, 25), (190, 70), (190, 145),
            (148, 190), (132, 194), (88, 194), (72, 190), (30, 145)], fill='#b056dc')
        image = image.crop(image.getchannel('A').getbbox())
        points = convex_outline(image)
        bottom = [p for p in points if p[1] == -.5]
        self.assertEqual(len(bottom), 2)
        self.assertAlmostEqual(max(p[0] for p in bottom) - min(p[0] for p in bottom), 45 / image.width)

    def test_perimeter_keeps_every_corner_and_never_shortcuts_across_it(self):
        points = [(-2., -1.), (2., -1.), (2., 1.), (-2., 1.)]
        perimeter = build_polygon_perimeter(points, 17)
        self.assertEqual(len(perimeter), 17)
        self.assertNotEqual(perimeter[0], perimeter[-1])
        for corner in points:
            self.assertIn(corner, perimeter)
        edges = list(zip(points, points[1:] + points[:1]))
        for a, b in zip(perimeter, perimeter[1:] + perimeter[:1]):
            self.assertTrue(any(distance(a, u, v) < 1e-10 and distance(b, u, v) < 1e-10 for u, v in edges))
            midpoint = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            outward = (b[1] - a[1], a[0] - b[0])
            self.assertGreater(outward[0] * midpoint[0] + outward[1] * midpoint[1], 0)
        self.assertEqual(len(build_polygon_perimeter(points, 3)), 4)

    def test_uvs_follow_arc_length_instead_of_vertex_index(self):
        points = build_polygon_perimeter([(-2., -1.), (2., -1.), (2., 1.), (-2., 1.)], 7)
        uvs = perimeter_uvs(points)
        self.assertEqual(uvs[0], 0)
        self.assertEqual(uvs, sorted(uvs))
        increments = [b - a for a, b in zip(uvs, uvs[1:] + [1.])]
        self.assertGreater(max(increments) - min(increments), .01)
        for fraction, a, b in zip(increments, points, points[1:] + points[:1]):
            self.assertAlmostEqual(fraction, math.dist(a, b) / 12)

    def test_concavity_is_reported_and_unusable_alpha_is_rejected(self):
        image = Image.new('RGBA', (120, 120))
        draw = ImageDraw.Draw(image)
        draw.rectangle((10, 10, 110, 110), fill='#aaaaff')
        draw.rectangle((40, 10, 80, 90), fill=(0, 0, 0, 0))
        info = analyze_convex_outline(image)
        self.assertTrue(info['is_convex'])
        self.assertTrue(info['concavity_warning'])
        self.assertGreater(info['concavity_ratio'], .2)
        for source in [Image.new('RGBA', (40, 40), 'red'), Image.new('RGBA', (40, 40)),
            Image.new('RGB', (40, 40), 'red')]:
            with self.subTest(mode=source.mode), self.assertRaisesRegex(ValueError, '透明|Alpha'):
                convex_outline(source)

    def test_alpha_threshold_ignores_faint_isolated_noise(self):
        clean = octagon()
        noisy = clean.copy()
        noisy.putpixel((0, 0), (255, 255, 255, 1))
        self.assertEqual(convex_outline(clean), convex_outline(noisy))
        self.assertNotEqual(convex_outline(clean), convex_outline(noisy, alpha_threshold=1))

    def test_self_intersecting_perimeter_is_rejected(self):
        pentagon = [(math.cos(i * 2 * math.pi / 5), math.sin(i * 2 * math.pi / 5)) for i in range(5)]
        star = [pentagon[i] for i in [0, 2, 4, 1, 3]]
        with self.assertRaisesRegex(ValueError, '凸|自交'):
            build_polygon_perimeter(star, 20)


if __name__ == '__main__':
    unittest.main(verbosity=2)
