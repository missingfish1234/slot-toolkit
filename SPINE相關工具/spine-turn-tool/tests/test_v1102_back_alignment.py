"""Duplicate decoded artwork must follow one asymmetric physical outline."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw, ImageOps, PngImagePlugin

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spine_turn_core import (TurnOptions, _contain, _trim, prepare_images,
                             resolve_options, pose_at, build_package)
from spine_turn_formats import SPINE_TARGETS


class DuplicateBackAlignmentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.front, self.back = self.folder/'front.png', self.folder/'separate-back.png'
        image = Image.new('RGBA', (72, 56), (90, 20, 150, 0))
        draw = ImageDraw.Draw(image)
        draw.polygon([(7, 5), (32, 5), (32, 33), (64, 33), (64, 49), (7, 49)],
                     fill=(220, 150, 40, 255))
        draw.rectangle((12, 12, 19, 20), fill=(230, 90, 20, 160))
        self.image = image
        image.save(self.front, compress_level=1)
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text('copy-role', 'Same RGBA in a separate file with different metadata')
        image.save(self.back, pnginfo=metadata, compress_level=9)
        self.original_bytes = {path: path.read_bytes() for path in (self.front, self.back)}
        self.base = TurnOptions(shape='irregular', outline_tolerance=0)

    def assert_sources_unchanged(self):
        for path, data in self.original_bytes.items():
            self.assertEqual(path.read_bytes(), data)

    def test_separate_png_files_with_identical_rgba_follow_processed_front_for_both_axes(self):
        self.assertNotEqual(self.front.read_bytes(), self.back.read_bytes())
        for axis in ('x', 'y'):
            options = replace(self.base, axis=axis, width=88, height=60)
            prepared = prepare_images(self.front, self.back, None, options)
            expected = ImageOps.mirror(prepared['front']) if axis == 'y' else ImageOps.flip(prepared['front'])
            self.assertEqual(prepared['back'].tobytes(), expected.tobytes())
            self.assertEqual(prepared['back_mode'], 'mirrored_duplicate_front_for_irregular')
            self.assertTrue(prepared['back_auto_aligned'])
            self.assertFalse(prepared['back_reuses_front'])
            self.assertEqual(prepared['back_bounds'], prepared['front_bounds'])
        self.assert_sources_unchanged()

    def test_missing_back_keeps_its_existing_mode_and_same_physical_result(self):
        for axis in ('x', 'y'):
            options = replace(self.base, axis=axis)
            duplicate = prepare_images(self.front, self.back, None, options)
            missing = prepare_images(self.front, None, None, options)
            self.assertEqual(duplicate['back'].tobytes(), missing['back'].tobytes())
            self.assertEqual(missing['back_mode'], 'mirrored_front_for_irregular')
            self.assertFalse(missing['back_auto_aligned'])
            self.assertTrue(missing['back_reuses_front'])
            first, second = resolve_options(duplicate, options), resolve_options(missing, options)
            self.assertEqual(pose_at(124.8, first, duplicate['width'], duplicate['height']),
                             pose_at(124.8, second, missing['width'], missing['height']))

    def test_distinct_back_artwork_keeps_its_upright_independent_material(self):
        distinct = self.image.copy()
        distinct.putpixel((13, 13), (20, 230, 60, 255))
        path = self.folder/'different-back.png'
        distinct.save(path)
        original = path.read_bytes()
        for axis in ('x', 'y'):
            prepared = prepare_images(self.front, path, None, replace(self.base, axis=axis))
            trimmed, bounds = _trim(distinct, True)
            expected = _contain(trimmed, prepared['front'].size)
            self.assertEqual(prepared['back'].tobytes(), expected.tobytes())
            self.assertEqual(prepared['back_mode'], 'supplied')
            self.assertFalse(prepared['back_auto_aligned'])
            self.assertFalse(prepared['back_reuses_front'])
        self.assertEqual(path.read_bytes(), original)
        self.assert_sources_unchanged()

    def test_equality_checks_all_decoded_rgba_channels_not_only_alpha_or_visible_pixels(self):
        distinct = self.image.copy()
        distinct.putpixel((0, 0), (1, 2, 3, 0))  # Invisible RGB still differs in decoded RGBA.
        path = self.folder/'hidden-channel-difference.png'
        distinct.save(path)
        prepared = prepare_images(self.front, path, None, self.base)
        self.assertEqual(prepared['back_mode'], 'supplied')
        self.assertFalse(prepared['back_auto_aligned'])

    def test_non_irregular_and_diamond_artwork_are_not_auto_reflected(self):
        for model, shape in (('extrusion', 'ellipse'), ('extrusion', 'rectangle'),
                             ('extrusion', 'polygon'), ('diamond', 'ellipse')):
            for axis in ('x', 'y'):
                options = replace(self.base, model=model, shape=shape, axis=axis)
                prepared = prepare_images(self.front, self.back, None, options)
                trimmed, _ = _trim(self.image, True)
                self.assertEqual(prepared['back'].tobytes(), _contain(trimmed, prepared['front'].size).tobytes())
                self.assertNotIn('back_auto_aligned', prepared)
                self.assertFalse(prepared['back_reuses_front'])
        self.assert_sources_unchanged()

    def test_each_target_package_records_explicit_duplicate_alignment(self):
        for family, version in SPINE_TARGETS.items():
            package = build_package(self.front, self.back, None, self.folder/family,
                                    replace(self.base, spine_version=version))
            metadata = json.loads(Path(package['manifest_path']).read_text(encoding='utf-8'))
            self.assertEqual(metadata['irregular']['back_mode'], 'mirrored_duplicate_front_for_irregular')
            self.assertTrue(metadata['irregular']['back_auto_aligned'])
            self.assertFalse(metadata['back_reuses_front'])
            self.assertEqual(metadata['spine_version'], version)
        self.assert_sources_unchanged()


if __name__ == '__main__':
    unittest.main()
