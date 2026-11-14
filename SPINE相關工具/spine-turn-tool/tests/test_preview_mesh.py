"""Known textured geometry checks for fan caps and trapezoidal bevel facets."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spine_turn_core import TurnOptions, prepare_images, resolve_options
from spine_turn_preview import render_pose


def mesh(screen_points, uv, triangles, tint=(1, 1, 1, 1)):
    return {'path': 'front', 'visible': True,
        'vertices': [value for x, y in screen_points for value in (x - 64, 64 - y)],
        'uvs': [value for point in uv for value in point],
        'triangles': triangles, 'tint': tint}


def draw(surfaces, texture):
    prepared = {'width': 64, 'height': 64, 'front': texture}
    movement = {'x': 0, 'y': 0, 'scale_x': 1, 'scale_y': 1}
    with patch('spine_turn_preview.animation_pose_at', return_value=surfaces), \
         patch('spine_turn_preview.motion_at', return_value=movement):
        return render_pose(prepared, TurnOptions(), 0, size=(128, 128),
            background='transparent', camera={'scale': 1, 'origin_x': 64, 'origin_y': 64}, show_ground=False)


class GeneralMeshRendererTests(unittest.TestCase):
    def fan(self, tint=(1, 1, 1, 1)):
        return mesh([(32, 32), (96, 32), (96, 96), (32, 96), (64, 64)],
            [(0, 0), (1, 0), (1, 1), (0, 1), (.5, .5)],
            [0, 1, 4, 1, 2, 4, 2, 3, 4, 3, 0, 4], tint)

    def test_semitransparent_fan_has_no_internal_holes_or_double_alpha(self):
        image = draw([self.fan()], Image.new('RGBA', (8, 8), (200, 100, 50, 128)))
        pixels = np.asarray(image)
        self.assertTrue(np.all(pixels[32:96, 32:96, 3] == 128))
        self.assertTrue(np.all(pixels[32:96, 32:96, :3] == (200, 100, 50)))
        self.assertEqual(image.getpixel((0, 0)), (0, 0, 0, 0))
        self.assertEqual(image.getchannel('A').getbbox(), (32, 32, 96, 96))

    def test_trapezoid_uses_its_actual_triangles_for_texture_mapping(self):
        texture = Image.new('RGBA', (2, 2))
        texture.putdata([(255, 0, 0, 255), (0, 255, 0, 255),
                         (0, 0, 255, 255), (255, 255, 255, 255)])
        trapezoid = mesh([(40.5, 40.5), (88.5, 40.5), (76.5, 88.5), (52.5, 88.5)],
            [(0, 0), (1, 0), (1, 1), (0, 1)], [0, 1, 2, 2, 3, 0])
        image = draw([trapezoid], texture)
        # Triangle ABC's centroid is exactly pixel center (68.5,56.5).
        # UV=(2/3,1/3), bilinear 2x2 sample=(70.83,212.5,42.5).
        pixel = image.getpixel((68, 56))
        self.assertTrue(all(abs(a - b) <= 1 for a, b in zip(pixel[:3], (71, 213, 43))), pixel)
        self.assertEqual(pixel[3], 255)
        self.assertEqual(image.getpixel((45, 85))[3], 0, 'Trapezoid leaked into its rectangular bounding box.')

    def test_transparent_texel_rgb_cannot_bleed_into_visible_texture(self):
        texture = Image.new('RGBA', (2, 1))
        texture.putdata([(255, 0, 0, 255), (0, 255, 0, 0)])
        trapezoid = mesh([(40.5, 40.5), (88.5, 40.5), (76.5, 88.5), (52.5, 88.5)],
            [(0, 0), (1, 0), (1, 1), (0, 1)], [0, 1, 2, 2, 3, 0])
        pixel = draw([trapezoid], texture).getpixel((68, 56))
        self.assertEqual(pixel[:3], (255, 0, 0))
        self.assertAlmostEqual(pixel[3], 43, delta=1)

    def test_adjacent_triangle_meshes_own_shared_edge_once(self):
        first = mesh([(32.5, 32.5), (96.5, 32.5), (96.5, 96.5)],
            [(0, 0), (1, 0), (1, 1)], [0, 1, 2])
        second = mesh([(32.5, 32.5), (96.5, 96.5), (32.5, 96.5)],
            [(0, 0), (1, 1), (0, 1)], [0, 1, 2])
        image = draw([first, second], Image.new('RGBA', (4, 4), (100, 200, 50, 128)))
        self.assertTrue(np.all(np.asarray(image)[33:96, 33:96, 3] == 128))

    def test_float_tint_keeps_straight_color_and_alpha_independent(self):
        image = draw([self.fan((.5, .25, 1, .5))], Image.new('RGBA', (4, 4), (200, 100, 50, 128)))
        self.assertEqual(image.getpixel((64, 64)), (100, 25, 50, 64))

    def test_beveled_scene_side_quad_and_facet_share_one_coverage_rule(self):
        side = mesh([(32.5, 32.5), (64.5, 32.5), (64.5, 96.5), (32.5, 96.5)],
            [(0, 0), (1, 0), (1, 1), (0, 1)], [0, 1, 2, 2, 3, 0])
        facet = mesh([(64.5, 32.5), (96.5, 32.5), (96.5, 96.5), (64.5, 96.5)],
            [(0, 0), (1, 0), (1, 1), (0, 1)], [0, 1, 2, 2, 3, 0])
        facet['kind'] = 'bevel'
        image = draw([side, facet], Image.new('RGBA', (4, 4), (200, 100, 50, 128)))
        self.assertTrue(np.all(np.asarray(image)[33:96, 33:96, 3] == 128))

    def test_complete_beveled_polygon_has_no_enclosed_alpha_seams(self):
        options = TurnOptions(shape='polygon', thickness=32, bevel_width=.07, bevel_depth=.25)
        prepared = prepare_images(ROOT / 'assets' / 'demo-octagon.png', None, None, options)
        options = resolve_options(prepared, options)
        for angle in (35, 70, 110, 145):
            with self.subTest(angle=angle):
                image = render_pose(prepared, options, angle, size=(256, 256),
                    background='transparent', progress=angle / 360, show_ground=False)
                alpha = image.getchannel('A').point(lambda value: 255 if value >= 16 else 0)
                padded = Image.new('L', (258, 258))
                padded.paste(alpha, (1, 1))
                ImageDraw.floodfill(padded, (0, 0), 128)
                self.assertEqual(padded.histogram()[0], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
