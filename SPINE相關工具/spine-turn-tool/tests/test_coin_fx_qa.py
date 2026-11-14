"""Independent coin-light transparency, interpolation and renderer checks."""
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spine_turn_core import TurnOptions, animation_pose_at, motion_at, prepare_images, resolve_options
from spine_turn_preview import render_pose


def translucent_coin(back=False):
    image = Image.new('RGBA', (64, 64))
    draw = ImageDraw.Draw(image)
    color = (70, 120, 210) if back else (170, 95, 35)
    draw.ellipse((3, 3, 61, 61), fill=(*color, 96))
    draw.ellipse((6, 6, 58, 58), fill=(*color, 255))
    hole = (35, 26) if back else (27, 34)
    x, y = hole
    draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=(*color, 128))
    draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=(200, 0, 200, 0))
    return image


def no_light_color(surfaces):
    result = []
    for surface in surfaces:
        value = surface.copy()
        if surface.get('kind') == 'coin_fx':
            value['color'] = 'ffffff00'
            value['tint'] = (1., 1., 1., 0.)
        result.append(value)
    return result


def inside_convex(point, polygon, tolerance=2e-5):
    crosses = [(b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0])
               for a, b in zip(polygon, polygon[1:] + polygon[:1])]
    return min(crosses) >= -tolerance or max(crosses) <= tolerance


class CoinLightIndependentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.front, self.back = self.folder / 'front.png', self.folder / 'back.png'
        translucent_coin().save(self.front)
        translucent_coin(True).save(self.back)

    def prepared(self, options):
        images = prepare_images(self.front, self.back, None, options)
        return images, resolve_options(images, options)

    def test_white_light_masks_leave_translucent_edges_and_holes_dark(self):
        from spine_turn_coin_fx import make_effect_textures
        options = TurnOptions(coin_shine_enabled=True, trim_transparent=False)
        images, options = self.prepared(options)
        textures = make_effect_textures(images, options)
        self.assertEqual(set(textures), {'coin-shine-front', 'coin-shine-back'})
        for source_name in ('front', 'back'):
            source_alpha = np.asarray(images[source_name])[:, :, 3]
            texture = np.asarray(textures[f'coin-shine-{source_name}'])
            self.assertEqual(texture.shape, np.asarray(images[source_name]).shape)
            self.assertTrue(np.all(texture[:, :, :3] == 255))
            self.assertTrue(np.all(texture[:, :, 3][source_alpha < 255] == 0))
            self.assertGreater(np.count_nonzero(texture[:, :, 3]), 0)
        self.assertFalse(np.array_equal(np.asarray(textures['coin-shine-front'])[:, :, 3],
                                       np.asarray(textures['coin-shine-back'])[:, :, 3]))

    def test_bilinear_white_overlay_never_increases_source_alpha_or_fills_holes(self):
        options = TurnOptions(coin_shine_enabled=True, coin_shine_strength=.9,
            coin_shine_width=.4, trim_transparent=False, thickness=6)
        changed_pixels = 0
        for axis in ('x', 'y'):
            images, current = self.prepared(replace(options, axis=axis))
            for progress in (.13, .31, .47, .63, .81):
                with self.subTest(axis=axis, progress=progress):
                    surfaces = animation_pose_at(progress, current, images['width'], images['height'])
                    camera = {'scale': 1.5, 'origin_x': 64, 'origin_y': 64}
                    actual = render_pose(images, current, 360 * progress, (128, 128), 'transparent',
                        progress=progress, camera=camera, show_ground=False)
                    with patch('spine_turn_preview.animation_pose_at', return_value=no_light_color(surfaces)):
                        baseline = render_pose(images, current, 360 * progress, (128, 128), 'transparent',
                            progress=progress, camera=camera, show_ground=False)
                    actual, baseline = np.asarray(actual), np.asarray(baseline)
                    self.assertTrue(np.array_equal(actual[:, :, 3], baseline[:, :, 3]))
                    self.assertTrue(np.all(actual[:, :, 3][baseline[:, :, 3] == 0] == 0))
                    changed_pixels += np.count_nonzero(np.any(actual[:, :, :3] != baseline[:, :, :3], axis=2))
        self.assertGreater(changed_pixels, 0, 'Containment must not be achieved by an invisible light.')

    def test_strength_zero_is_exactly_disabled_in_textures_geometry_and_pixels(self):
        from spine_turn_coin_fx import make_effect_textures
        disabled = TurnOptions(trim_transparent=False, thickness=6)
        zero = replace(disabled, coin_shine_enabled=True, coin_shine_strength=0.)
        images_off, disabled = self.prepared(disabled)
        images_zero, zero = self.prepared(zero)
        self.assertEqual(make_effect_textures(images_off, disabled), {})
        self.assertEqual(make_effect_textures(images_zero, zero), {})
        for progress in (0., .137, .429, .763, 1.):
            with self.subTest(progress=progress):
                off_pose = animation_pose_at(progress, disabled, images_off['width'], images_off['height'])
                zero_pose = animation_pose_at(progress, zero, images_zero['width'], images_zero['height'])
                self.assertEqual(zero_pose, off_pose)
                kwargs = dict(size=(128, 128), background='transparent', progress=progress, show_ground=False,
                              camera={'scale': 1.5, 'origin_x': 64, 'origin_y': 64})
                self.assertEqual(render_pose(images_off, disabled, 360 * progress, **kwargs).tobytes(),
                                 render_pose(images_zero, zero, 360 * progress, **kwargs).tobytes())

    def test_light_cells_stay_inside_their_real_cap_between_keys_with_yz_motion(self):
        tested = 0
        for axis in ('x', 'y'):
            for profile in ('ellipse', 'polygon', 'bevel', 'ridge'):
                options = TurnOptions(coin_shine_enabled=True, coin_shine_strength=.8,
                    shape='ellipse' if profile == 'ellipse' else 'polygon', axis=axis,
                    bevel_width=.08 if profile in ('bevel', 'ridge') else 0,
                    side_mode='ridge' if profile == 'ridge' else 'strip',
                    bounce_enabled=True, bounce_height=12, peak_scale=1.2,
                    z_bounce_enabled=True, z_bounce_depth=80, peak_z_scale=1.35,
                    camera_distance=800, thickness=12)
                # The public fixture is a convex octagon with genuine corners.
                images = prepare_images(ROOT / 'assets' / 'demo-octagon.png', None, None, options)
                options = resolve_options(images, options)
                for progress in (.003, .079, .213, .251, .437, .661, .813, .997):
                    surfaces = animation_pose_at(progress, options, images['width'], images['height'])
                    parents = {surface['name']: surface for surface in surfaces if surface.get('kind') != 'coin_fx'}
                    movement = motion_at(progress, options, images['height'])
                    def transformed(surface):
                        return [(surface['vertices'][i] * movement['scale_x'] + movement['x'],
                                 surface['vertices'][i + 1] * movement['scale_y'] + movement['y'])
                                for i in range(0, len(surface['vertices']), 2)]
                    for child in surfaces:
                        if child.get('kind') != 'coin_fx':
                            continue
                        with self.subTest(axis=axis, profile=profile, progress=progress, child=child['name']):
                            parent = parents[child['source_face']]
                            self.assertIn(parent['kind'], ('front', 'back'))
                            self.assertEqual(child['visible'], parent['visible'])
                            polygon = transformed(parent)[:parent.get('hull', len(parent['vertices']) // 2)]
                            for point in transformed(child):
                                self.assertTrue(inside_convex(point, polygon), (point, polygon))
                            tested += 1
        self.assertGreater(tested, 100)

    def test_coin_light_does_not_change_diamond_mode(self):
        from spine_turn_coin_fx import make_effect_textures
        options = TurnOptions(model='diamond', coin_shine_enabled=True)
        images, options = self.prepared(options)
        self.assertEqual(make_effect_textures(images, options), {})
        self.assertFalse(any(surface.get('kind') == 'coin_fx'
                             for surface in animation_pose_at(.37, options, images['width'], images['height'])))


if __name__ == '__main__':
    unittest.main(verbosity=2)
