"""Editable projects preserve original inputs/settings and fail without data loss."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import spine_turn_project as project
from spine_turn_core import TurnOptions, prepare_images, resolve_options
from spine_turn_preview import render_pose


def bytes_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rewrite(source, destination, change=None, extra=None, remove=None):
    with zipfile.ZipFile(source) as archive:
        members = {info.filename: archive.read(info.filename) for info in archive.infolist()}
    manifest = json.loads(members['manifest.json'])
    if change:
        change(manifest)
    members['manifest.json'] = json.dumps(manifest, ensure_ascii=False).encode('utf-8')
    if extra:
        members.update(extra)
    if remove:
        members.pop(remove)
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)


class EditableProjectTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.front = self.folder / '原始_正面.png'
        self.back = self.folder / '原始_背面.png'
        self.edge = self.folder / '直向材質.png'
        shutil.copy2(ROOT / 'assets' / 'demo-octagon.png', self.front)
        with Image.open(self.front) as image:
            image.transpose(Image.Transpose.FLIP_LEFT_RIGHT).save(self.back)
        with Image.open(ROOT / 'assets' / 'demo-edge.png') as image:
            image.transpose(Image.Transpose.ROTATE_270).save(self.edge)
        self.paths = {'front': str(self.front), 'back': str(self.back), 'edge': str(self.edge)}
        self.ui = {'animation': 'flip_to_back', 'background': 'light', 'preview_zoom': 135,
            'show_ground': False, 'native_export': True, 'progress': .37, 'playing': False,
            'future_display_note': '保持未顯示的畫面資料'}

    def options(self):
        return TurnOptions(name='保存所有設定', width=384, height=0, thickness=37, segments=40,
            duration=3.4, axis='x', shape='polygon', key_step_degrees=12,
            trim_transparent=True, edge_color='#7a228c', shade_edge=False,
            edge_orientation='vertical', base_scale=1.2, bounce_enabled=True,
            bounce_height=87, peak_scale=1.3, landing_squash=.16,
            shade_faces=True, min_brightness=.32, shade_curve=1.8, light_angle=-25,
            z_scale=1.1, peak_z_scale=1.4, z_bounce_enabled=True, z_bounce_depth=180,
            z_offset=-60, camera_distance=1300, bounce_start=.15, bounce_apex=.42,
            bounce_land=.75, bounce_end=.9, z_bounce_start=.2, z_bounce_apex=.5,
            z_bounce_end=.85, bevel_width=0, bevel_depth=.3,
            raised_contour_points=((-0.2, -0.25), (.24, -.23), (.31, .06), (.05, .3), (-.27, .14)),
            side_mode='ridge', spine_version='4.2.43')

    def save_simple(self):
        filename = self.folder / 'valid.spturn'
        project.save_project(filename, self.paths, TurnOptions(name='valid'), self.ui)
        return filename

    def test_roundtrip_all_settings_raw_images_and_resave_without_original_files(self):
        filename = self.folder / '完整編輯檔.spturn'
        options = self.options()
        hashes = {name: bytes_hash(path) for name, path in self.paths.items()}
        # Raw image is320x320 with transparent margins, not prepared384x384.
        prepared = prepare_images(**{f'{name}_path': value for name, value in self.paths.items()}, options=options)
        before = render_pose(prepared, resolve_options(prepared, options), 66.6, size=(160, 160), background='transparent', progress=.37, show_ground=False)
        metadata = project.save_project(filename, self.paths, options, self.ui)
        self.assertEqual(metadata['asset_count'], 3)
        for path in self.paths.values():
            Path(path).unlink()
        with project.load_project(filename) as loaded:
            self.assertEqual(asdict(loaded.options), asdict(options))
            self.assertEqual(loaded.ui_state, self.ui)
            self.assertEqual({name: bytes_hash(path) for name, path in loaded.paths.items()}, hashes)
            with Image.open(loaded.paths['front']) as image:
                self.assertEqual(image.size, (320, 320))
            restored = prepare_images(loaded.paths['front'], loaded.paths['back'], loaded.paths['edge'], loaded.options)
            after = render_pose(restored, resolve_options(restored, loaded.options), 66.6, size=(160, 160), background='transparent', progress=.37, show_ground=False)
            self.assertEqual(before.tobytes(), after.tobytes())
            second = self.folder / '另存新檔.spturn'
            project.save_project(second, loaded.paths, loaded.options, loaded.ui_state)
            workspace = Path(loaded.workspace_dir)
            self.assertTrue(workspace.is_dir())
        self.assertFalse(workspace.exists())
        with project.load_project(second) as loaded:
            self.assertEqual({name: bytes_hash(path) for name, path in loaded.paths.items()}, hashes)

    def test_optional_sources_stay_none_and_owned_workspace_cleanup_preserves_parent(self):
        filename = self.folder / 'one-image.spturn'
        project.save_project(filename, {'front': self.front, 'back': None, 'edge': None}, TurnOptions())
        workspace_parent = self.folder / 'workspaces'
        workspace_parent.mkdir()
        sentinel = workspace_parent / 'retain.txt'
        sentinel.write_text('retain', encoding='utf-8')
        loaded = project.load_project(filename, workspace_dir=workspace_parent)
        self.assertIsNone(loaded.paths['back'])
        self.assertIsNone(loaded.paths['edge'])
        self.assertEqual(loaded.ui_state, {})
        loaded.close()
        loaded.close()
        self.assertTrue(sentinel.exists())
        self.assertEqual(list(workspace_parent.iterdir()), [sentinel])

    def test_missing_source_or_atomic_replace_failure_preserves_existing_project(self):
        filename = self.save_simple()
        previous = filename.read_bytes()
        with self.assertRaisesRegex(ValueError, '找不到正面'):
            project.save_project(filename, {'front': self.folder / 'missing.png'}, TurnOptions())
        self.assertEqual(filename.read_bytes(), previous)
        with patch('spine_turn_project.os.replace', side_effect=PermissionError('injected')):
            with self.assertRaisesRegex(ValueError, '原有檔案已保留'):
                project.save_project(filename, self.paths, TurnOptions())
        self.assertEqual(filename.read_bytes(), previous)
        self.assertFalse(list(self.folder.glob('.valid.spturn.*.tmp')))

    def test_future_schema_options_and_malformed_ui_fail_before_workspace_creation(self):
        valid = self.save_simple()
        workspaces = self.folder / 'workspaces'
        workspaces.mkdir()
        changes = [lambda m: m.update(schema_version=99),
            lambda m: m['options'].update(future_unknown_field=1),
            lambda m: m['ui_state'].update(progress=2),
            lambda m: m['ui_state'].update(preview_zoom='large'),
            lambda m: m['ui_state'].update(native_export='False'),
            lambda m: m['ui_state'].update(animation='execute_this')]
        for index, change in enumerate(changes):
            filename = self.folder / f'invalid-{index}.spturn'
            rewrite(valid, filename, change)
            with self.subTest(index=index), self.assertRaises(ValueError):
                project.load_project(filename, workspace_dir=workspaces)
            self.assertFalse(list(workspaces.iterdir()))

    def test_archive_traversal_unlisted_code_and_checksum_damage_are_rejected(self):
        valid = self.save_simple()
        workspaces = self.folder / 'workspaces'
        workspaces.mkdir()
        for name in ['../outside.png', 'assets/../../outside.png', 'C:/outside.png', 'assets\\outside.png', 'code.py']:
            filename = self.folder / ('unsafe-' + str(len(name)) + '.spturn')
            rewrite(valid, filename, extra={name: b'not executed'})
            with self.subTest(member=name), self.assertRaises(ValueError):
                project.load_project(filename, workspace_dir=workspaces)
        filename = self.folder / 'damaged.spturn'
        rewrite(valid, filename, extra={'assets/front.png': b'damaged image'})
        with self.assertRaisesRegex(ValueError, '素材'):
            project.load_project(filename)
        self.assertFalse((workspaces / 'outside.png').exists())
        self.assertFalse(list(workspaces.iterdir()))

    def test_asset_size_and_image_pixel_limits_are_checked_without_large_allocations(self):
        valid = self.save_simple()
        with patch('spine_turn_project.MAX_ASSET_BYTES', 10):
            with self.assertRaisesRegex(ValueError, '大小|上限'):
                project.load_project(valid)
        with patch('spine_turn_project.MAX_IMAGE_PIXELS', 4):
            with self.assertRaisesRegex(ValueError, '像素'):
                project.save_project(self.folder / 'large.spturn', self.paths, TurnOptions())
        invalid = self.folder / 'not-image.png'
        invalid.write_bytes(b'print("this is data, never executable")')
        with self.assertRaisesRegex(ValueError, '圖片'):
            project.save_project(self.folder / 'invalid-image.spturn', {'front': invalid}, TurnOptions())

    def test_old_missing_option_and_ui_fields_use_defaults_without_losing_known_values(self):
        valid = self.save_simple()
        old = self.folder / 'older-fields.spturn'
        rewrite(valid, old, lambda manifest: manifest.update(options={'name': 'older'}, ui_state={'background': 'dark'}))
        with project.load_project(old) as loaded:
            self.assertEqual(loaded.options.name, 'older')
            self.assertEqual(loaded.options.spine_version, '4.0.56')
            self.assertEqual(loaded.options.side_mode, 'strip')
            self.assertEqual(loaded.ui_state, {'background': 'dark'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
