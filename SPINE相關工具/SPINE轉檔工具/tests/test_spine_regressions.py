import io
import json
import runpy
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL))
from conversion_safety import ConversionCancelled, normalize_atlas_names, publish_output, run_spine, validate_output, validate_roots


class ConversionTests(unittest.TestCase):
    def test_roots_reject_same_and_nested(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError): validate_roots(d, d)
            with self.assertRaises(ValueError): validate_roots(d, Path(d) / 'output')

    def test_old_atlas_cannot_overwrite_current(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'Hero.atlas').write_text('new')
            (root / 'Old.atlas').write_text('old')
            normalize_atlas_names(root, 'Hero', False)
            self.assertEqual((root / 'Hero.atlas').read_text(), 'new')
            self.assertEqual((root / 'Old.atlas').read_text(), 'old')

    def test_multipage_references_are_kept(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'x.atlas').write_text('a.png\nsize: 1,1\n\nb.png\nsize: 1,1\n')
            for name in ['a.png', 'b.png', 'Hero.skel']: (root / name).write_bytes(b'fixture')
            normalize_atlas_names(root, 'Hero', False)
            validate_output(root)
            (root / 'b.png').unlink()
            with self.assertRaises(ValueError): validate_output(root)

    def test_publish_preserves_user_files_and_backup(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); staged = root / 'staged'; dest = root / 'output'
            staged.mkdir(); dest.mkdir()
            (staged / 'hero.atlas').write_text('new'); (dest / 'hero.atlas').write_text('old')
            (dest / 'notes.txt').write_text('user')
            backup = publish_output(staged, dest, root / 'backups')
            self.assertEqual((dest / 'hero.atlas').read_text(), 'new')
            self.assertEqual((dest / 'notes.txt').read_text(), 'user')
            self.assertEqual((backup / 'hero.atlas').read_text(), 'old')

    def test_png_region_name_is_not_texture_page(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'hero.atlas').write_text('page.png\nsize: 1,1\nicon.png\n  xy: 0,0\n  size: 1,1\n')
            (root / 'page.png').write_bytes(b'page'); (root / 'hero.skel').write_bytes(b'skel')
            validate_output(root)

    def test_publish_rejects_link_before_replacing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); staged = root / 'staged'; dest = root / 'output'
            staged.mkdir(); dest.mkdir(); (dest / 'keep').write_text('old')
            original = Path.is_symlink
            with patch.object(Path, 'is_symlink', lambda p: p == dest or original(p)), self.assertRaises(ValueError):
                publish_output(staged, dest, root / 'backups')
            self.assertEqual((dest / 'keep').read_text(), 'old')

    def test_publish_failure_restores_destination(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); staged = root / 'staged'; dest = root / 'output'
            staged.mkdir(); dest.mkdir(); (dest / 'keep').write_text('old'); (staged / 'keep').write_text('new')
            rename = Path.rename
            def fail_commit(path, target):
                if path.name.startswith('.spine-publish-'): raise OSError('simulated commit failure')
                return rename(path, target)
            with patch.object(Path, 'rename', fail_commit), self.assertRaises(OSError):
                publish_output(staged, dest, root / 'backups')
            self.assertEqual((dest / 'keep').read_text(), 'old')

    def test_cancel_and_timeout_real_child(self):
        event = threading.Event(); event.set()
        with self.assertRaises(ConversionCancelled): run_spine([sys.executable, '-c', 'pass'], event)
        event.clear()
        with self.assertRaises(TimeoutError): run_spine([sys.executable, '-c', 'import time; time.sleep(10)'], event, timeout=0.2)

    def test_python_sources_parse(self):
        import ast
        for file in [TOOL / 'spine_converter_gui.py', TOOL.parent / 'SPINE資訊檢測工具/checkspine_gui.py']:
            ast.parse(file.read_text(encoding='utf-8-sig'))


class QCTests(unittest.TestCase):
    def test_json_mesh_counts(self):
        mod = runpy.run_path(str(TOOL.parent / 'SPINE資訊檢測工具/checkspine_gui.py'))
        weighted = {'type': 'mesh', 'uvs': [0,0,1,0,0,1], 'vertices': [1,0,0,0,1,1,0,1,0,1,1,0,0,1,1]}
        unweighted = {'type':'mesh','uvs':[0,0,1,0,0,1],'vertices':[0,0,1,0,0,1]}
        for skins in [{'default': {'s': {'a': weighted, 'b': unweighted}}}, [{'name':'default','attachments': {'s': {'a': weighted, 'b': unweighted}}}]]:
            fixture = {'skeleton': {'spine':'4.0.56'}, 'skins':skins}
            fn = mod['analyze_spine_json']
            with patch('builtins.open', return_value=io.StringIO(json.dumps(fixture))), patch.dict(fn.__globals__, {'get_texture_dependencies': lambda _: []}):
                result = fn('fixture', 'fixture')
            self.assertEqual((result['meshes'], result['weighted'], result['verts'], result['drawcalls']), (2,1,6,0))


if __name__ == '__main__': unittest.main()
