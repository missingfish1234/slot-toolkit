"""Portable package checks for generated art, mesh references, and timeline integrity."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spine_turn_core import TurnOptions, build_package


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class PackageTests(unittest.TestCase):
    def test_export_is_portable_and_preserves_source_art(self):
        source = {name: ROOT / 'assets' / f'demo-{name}.png' for name in ['front', 'back', 'edge']}
        before = {name: digest(p) for name, p in source.items()}
        with tempfile.TemporaryDirectory() as folder:
            result = build_package(source['front'], source['back'], source['edge'], folder,
                TurnOptions(name='qa_coin', width=294, height=294, thickness=24, segments=24, duration=2))
            json_path = Path(result['json_path'])
            self.assertTrue(json_path.is_file())
            data = json.loads(json_path.read_text(encoding='utf-8'))
            self.assertEqual(data['skeleton']['spine'], '4.0.56')
            images = data['skeleton'].get('images', './images/')
            self.assertFalse(Path(images).is_absolute(), 'Image path must survive package relocation.')
            self.assertTrue((json_path.parent / images).is_dir())
            self.assertNotIn(str(ROOT), json_path.read_text(encoding='utf-8'), 'Export leaks an absolute workspace path.')
            self.check_skeleton(data, json_path.parent / images)
            atlases = list(json_path.parent.glob('*.atlas'))
            self.assertEqual(len(atlases), 1)
            atlas_pages = list(json_path.parent.glob('*.png'))
            self.assertGreaterEqual(len(atlas_pages), 1)
            for page in atlas_pages:
                with Image.open(page) as im:
                    self.assertEqual(im.mode, 'RGBA')
                    self.assertGreater(im.width, 0)
                    self.assertGreater(im.height, 0)
        self.assertEqual(before, {name: digest(p) for name, p in source.items()})

    def check_skeleton(self, data, images):
        bone_names = [b['name'] for b in data['bones']]
        self.assertEqual(len(bone_names), len(set(bone_names)))
        slot_names = [s['name'] for s in data['slots']]
        self.assertEqual(len(slot_names), len(set(slot_names)))
        for slot in data['slots']:
            self.assertIn(slot['bone'], bone_names)
        skins = data['skins']
        self.assertIsInstance(skins, list, 'Spine 4.0 skins use list format.')
        attachment_count = 0
        for skin in skins:
            for slot, attachments in skin['attachments'].items():
                self.assertIn(slot, slot_names)
                for name, mesh in attachments.items():
                    attachment_count += 1
                    self.assertEqual(mesh['type'], 'mesh')
                    self.assertTrue((images / (mesh.get('path', name) + '.png')).is_file())
                    uvs = mesh['uvs']
                    self.assertEqual(len(uvs), len(mesh['vertices']))
                    self.assertEqual(len(uvs) % 2, 0)
                    self.assertTrue(all(-1e-6 <= value <= 1.000001 for value in uvs))
                    triangles = mesh['triangles']
                    self.assertEqual(len(triangles) % 3, 0)
                    self.assertTrue(all(isinstance(i, int) and 0 <= i < len(uvs) // 2 for i in triangles))
        self.assertGreaterEqual(attachment_count, 3)
        self.assertLess(attachment_count, 100, 'Rotation should remain mesh animation, not raster frame attachments.')
        self.assertIn('animations', data)
        for animation in data['animations'].values():
            self.assertTrue(animation.get('deform'), 'Rotation must contain editable deform keys.')
            self.check_timelines(animation)

    def check_timelines(self, value):
        if isinstance(value, dict):
            for child in value.values():
                self.check_timelines(child)
        elif isinstance(value, list):
            if value and isinstance(value[0], dict) and 'time' in value[0]:
                times = [frame.get('time', 0) for frame in value]
                self.assertEqual(times, sorted(set(times)), 'Timeline keys need unique increasing times.')
            for child in value:
                self.check_timelines(child)

    def test_single_image_and_other_axis_export(self):
        with tempfile.TemporaryDirectory() as folder:
            result = build_package(ROOT / 'assets' / 'demo-front.png', None, None, folder,
                TurnOptions(name='one_face', width=200, height=180, axis='x', thickness=12, duration=1.5))
            data = json.loads(Path(result['json_path']).read_text(encoding='utf-8'))
            self.check_skeleton(data, Path(result['json_path']).parent / data['skeleton'].get('images', './images/'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
