"""Preview speed-ups must not change a single rendered byte or any exported data."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
import spine_turn_core as core
import spine_turn_preview as preview
from spine_turn_core import TurnOptions, animation_pose_at, prepare_images, resolve_options

ASSETS = ROOT / 'assets'


def scene(**changes):
    options = replace(TurnOptions(), **{**dict(shape='irregular', outline_alpha_threshold=16,
        outline_tolerance=1, coin_shine_enabled=True, coin_shine_start=0, coin_shine_end=.25), **changes})
    prepared = prepare_images(ASSETS / 'demo-irregular-front.png', ASSETS / 'demo-irregular-back.png',
                              ASSETS / 'demo-edge.png', options)
    return prepared, resolve_options(prepared, options)


def legacy_sample_encode(source, uv, factors):
    """The pre-1.10.2 whole-batch sampling and encoding, kept as the reference."""
    samples = preview._bilinear_pma(source, uv[:, 0], uv[:, 1])
    if factors is not None:
        samples *= factors          # identical to the per-channel tint products
    return preview._encode_pma(samples, np.ones((len(uv), 4)))


class SamplingTests(unittest.TestCase):
    def test_blocked_sampler_matches_reference_functions_byte_for_byte(self):
        random = np.random.default_rng(1102)
        texture = random.random((37, 53, 4)).astype(np.float32)
        texture[:, :, 3] = np.where(random.random((37, 53)) < .6, 1, texture[:, :, 3])
        texture[:6] = 0
        texture[:, :, :3] *= texture[:, :, 3:4]
        count = preview._SAMPLE_BLOCK * 3 + 517          # several blocks plus a ragged tail
        uv = random.random((count, 2)) * 1.1 - .05      # includes clamped coordinates
        tints = np.ones((count, 4))
        tints[count // 3:] = (.62, .7, .81, 1)
        tints[-900:] = (1, 1, 1, .37)
        tints[-40:] = (1, 1, 1, 0)
        expected = preview._encode_pma(preview._bilinear_pma(texture, uv[:, 0], uv[:, 1]), tints.copy())
        factors = np.column_stack((tints[:, :3] * tints[:, 3:4], tints[:, 3]))
        self.assertTrue(np.array_equal(preview._sample_encode(texture, uv, factors), expected))
        plain = preview._encode_pma(preview._bilinear_pma(texture, uv[:, 0], uv[:, 1]), np.ones((count, 4)))
        self.assertTrue(np.array_equal(preview._sample_encode(texture, uv, None), plain))

    def test_texture_cache_never_serves_replaced_artwork(self):
        prepared = {'front': Image.new('RGBA', (4, 4), (255, 0, 0, 255))}
        cache = preview._texture_cache(prepared)
        self.assertIs(cache, preview._texture_cache(prepared))
        first = preview._texture_pma(prepared['front'], cache)
        self.assertIs(first, preview._texture_pma(prepared['front'], cache))
        prepared['front'] = Image.new('RGBA', (4, 4), (0, 0, 255, 255))
        second = preview._texture_pma(prepared['front'], cache)
        self.assertEqual(tuple(second[0, 0]), (0., 0., 1., 1.))
        self.assertEqual(tuple(first[0, 0]), (1., 0., 0., 1.))

    def test_oversized_artwork_is_not_kept_in_memory(self):
        with patch.object(preview, '_PERSISTENT_TEXTURE_PIXELS', 8):
            prepared = {'front': Image.new('RGBA', (4, 4))}
            preview._texture_cache(prepared)['probe'] = 1
            self.assertNotIn('_preview_pma_textures', prepared)

    def test_cached_background_is_not_shared_between_frames(self):
        first = preview._canvas((60, 40), 'checker')
        first.putpixel((0, 0), (1, 2, 3, 4))
        second = preview._canvas((60, 40), 'checker')
        self.assertEqual(second.getpixel((0, 0)), (31, 37, 49, 255))
        self.assertEqual(second.getpixel((25, 5)), (37, 44, 57, 255))
        self.assertEqual(preview._canvas((60, 40), 'transparent').getpixel((25, 5)), (0, 0, 0, 0))


class RenderEquivalenceTests(unittest.TestCase):
    def frames(self, prepared, options, size=(300, 260)):
        return [preview.render_pose(prepared, options, progress * 360, size, background,
                                    progress=progress, show_ground=False).tobytes()
                for background in ('checker', 'transparent')
                for progress in (0, .031, .12, .2, .249, .26, .5, .62, .75, .9, .12, .12)]

    def test_irregular_frames_equal_the_unoptimized_pipeline(self):
        for axis in ('y', 'x'):
            with self.subTest(axis=axis):
                prepared, options = scene(axis=axis)
                fast = self.frames(prepared, options)
                original_pose = preview.animation_pose_at
                def full_pose(*args, **kwargs):
                    kwargs.pop('cull_hidden_effects', None)
                    return original_pose(*args, **kwargs)
                slow_prepared, slow_options = scene(axis=axis)
                with patch.object(preview, 'animation_pose_at', full_pose), \
                        patch.object(preview, '_sample_encode', legacy_sample_encode), \
                        patch.object(core, '_key_pose', core._animation_projection):
                    slow = self.frames(slow_prepared, slow_options)
                self.assertEqual(fast, slow)

    def test_culling_only_removes_cells_the_rasterizer_would_skip(self):
        prepared, options = scene()
        width, height = prepared['width'], prepared['height']
        for progress in (.05, .12, .2, .4, .8):
            full = animation_pose_at(progress, options, width, height)
            culled = animation_pose_at(progress, options, width, height, cull_hidden_effects=True)
            drawn = {surface['name']: surface for surface in full
                     if surface.get('visible', True) and preview._surface_tint(surface)[3] > 0}
            kept = {surface['name']: surface for surface in culled
                    if surface.get('visible', True) and preview._surface_tint(surface)[3] > 0}
            self.assertEqual(set(drawn), set(kept))
            for name, surface in drawn.items():
                for field in ('vertices', 'uvs', 'triangles', 'hull', 'path', 'draw_order'):
                    self.assertEqual(surface.get(field), kept[name].get(field), (progress, name, field))
                self.assertEqual(preview._surface_tint(surface), preview._surface_tint(kept[name]))
            self.assertLess(len(culled), len(full))

    def test_default_pose_and_over_limit_guard_are_unchanged(self):
        prepared, options = scene()
        width, height = prepared['width'], prepared['height']
        with patch.object(core, '_key_pose', core._animation_projection):
            reference = animation_pose_at(.12, options, width, height)
        self.assertEqual(animation_pose_at(.12, options, width, height), reference)
        import spine_turn_irregular
        from spine_turn_irregular import irregular_effect_surfaces
        templates = spine_turn_irregular._effect_templates
        with patch('spine_turn_irregular._effect_templates', side_effect=lambda *args: templates(*args) * 80):
            for keep in (None, lambda coordinate: False):
                with self.assertRaises(ValueError):
                    irregular_effect_surfaces(reference, options, .12, width, height, keep)


class KeyPoseCacheTests(unittest.TestCase):
    def test_key_poses_are_reused_and_follow_option_changes(self):
        prepared, options = scene(coin_shine_enabled=False)
        width, height = prepared['width'], prepared['height']
        core._KEY_POSE_CACHE.clear()
        with patch.object(core, '_animation_projection', wraps=core._animation_projection) as projection:
            first = core._animation_pose_plain(.1234, options, width, height)
            built = projection.call_count
            second = core._animation_pose_plain(.1236, replace(options), width, height)
            self.assertEqual(projection.call_count, built)
            thicker = core._animation_pose_plain(.1234, replace(options, thickness=options.thickness + 7), width, height)
            self.assertGreater(projection.call_count, built)
        self.assertNotEqual(first[0]['vertices'], second[0]['vertices'])
        self.assertNotEqual([s['vertices'] for s in first], [s['vertices'] for s in thicker])
        self.assertLessEqual(len(core._KEY_POSE_CACHE), 6)
        with patch.object(core, '_key_pose', core._animation_projection):
            self.assertEqual(core._animation_pose_plain(.1234, options, width, height), first)

    def test_other_shapes_bypass_the_cache(self):
        core._KEY_POSE_CACHE.clear()
        core._animation_pose_plain(.3, TurnOptions(), 120, 120)
        self.assertEqual(core._KEY_POSE_CACHE, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
