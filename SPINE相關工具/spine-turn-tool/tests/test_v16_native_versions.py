"""Version selection is pinned, schema-checked, and never falls back silently."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import spine_native


class NativeVersionTests(unittest.TestCase):
    def test_families_resolve_to_explicit_verified_revisions_without_latest(self):
        for family, exact in {'3.8': '3.8.99', '4.0': '4.0.56', '4.2': '4.2.43'}.items():
            self.assertEqual(spine_native.resolve_target_version(family), exact)
            self.assertEqual(spine_native.resolve_target_version(exact), exact)
        self.assertEqual(spine_native.resolve_target_version('4.2.99'), '4.2.99')
        for unsupported in ('latest', '4.2.xx', '4.3.1', '3.7.94', ''):
            with self.assertRaises(ValueError):
                spine_native.resolve_target_version(unsupported)

    def test_target_alias_imports_with_exact_matching_editor_revision(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            launcher = folder / 'Spine.com'
            launcher.write_bytes(b'placeholder')
            source = folder / 'coin.json'
            source.write_text('{"skeleton":{"spine":"3.8.99"}}', encoding='utf-8')
            def run(command, timeout):
                self.assertEqual(command[command.index('--update') + 1], '3.8.99')
                Path(command[command.index('-o') + 1]).write_bytes(b'created-by-editor')
                return {'ok': True, 'editor_version': '3.8.99'}
            with patch.object(spine_native, '_run', side_effect=run):
                result = spine_native.convert_project(source, folder / 'coin.spine', launcher, target_version='3.8')
            self.assertTrue(result['ok'])
            self.assertEqual(result['version'], '3.8.99')

    def test_target_family_does_not_accept_different_json_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source = folder / 'coin.json'
            source.write_text('{"skeleton":{"spine":"4.0.56"}}', encoding='utf-8')
            with patch.object(spine_native, '_run') as run:
                result = spine_native.convert_project(source, folder / 'coin.spine', target_version='4.2')
            self.assertEqual(result['reason'], 'version_mismatch')
            run.assert_not_called()

    def test_success_exit_with_wrong_editor_revision_is_rejected_privately(self):
        completed = subprocess.CompletedProcess([], 0,
            stdout=b'Spine 4.0.56 Enterprise\nLicensed to PRIVATE PERSON private@example.com\n', stderr=b'')
        with patch.object(spine_native.subprocess, 'run', return_value=completed):
            result = spine_native._run(['Spine.com', '--update', '4.2.43'], 5)
        self.assertEqual(result['reason'], 'wrong_editor_version')
        self.assertEqual(result['reported_version'], '4.0.56')
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertNotIn('private@example.com', json.dumps(result))

    def test_download_failure_names_requested_revision(self):
        completed = subprocess.CompletedProcess([], 1, stdout=b'Unable to download requested update', stderr=b'')
        with patch.object(spine_native.subprocess, 'run', return_value=completed):
            result = spine_native._run(['Spine.com', '--update', '3.8.99'], 5)
        self.assertEqual(result['reason'], 'version_unavailable')
        self.assertIn('3.8.99', result['message'])
        self.assertNotIn('4.0.56', result['message'])

    def test_binary_export_pins_requested_revision_and_preserves_format(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            launcher, project = folder / 'Spine.com', folder / 'coin.spine'
            launcher.write_bytes(b'placeholder')
            project.write_bytes(b'native-project')
            def run(command, timeout):
                self.assertEqual(command[command.index('--update') + 1], '4.2.43')
                self.assertEqual(command[command.index('-e') + 1], 'binary')
                (Path(command[command.index('-o') + 1]) / 'coin.skel').write_bytes(b'native-binary')
                return {'ok': True, 'editor_version': '4.2.43'}
            with patch.object(spine_native, '_run', side_effect=run):
                result = spine_native.export_binary(project, folder / 'exported', launcher, target_version='4.2')
            self.assertTrue(result['ok'])
            self.assertEqual(result['version'], '4.2.43')
            self.assertTrue(Path(result['binary_paths'][0]).is_file())
            self.assertNotIn('json_paths', result)

    def test_legacy_38_exports_use_private_settings_file_and_never_return_it(self):
        for data_format, extension in (('binary', '.skel'), ('json', '.json')):
            with self.subTest(data_format=data_format), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary)
                launcher, project = folder / 'Spine.com', folder / 'coin.spine'
                launcher.write_bytes(b'placeholder')
                project.write_bytes(b'native-project')
                def run(command, timeout):
                    settings_file = Path(command[command.index('-e') + 1])
                    settings = json.loads(settings_file.read_text(encoding='utf-8'))
                    self.assertEqual(settings['class'], 'export-binary' if data_format == 'binary' else 'export-json')
                    self.assertFalse(settings['open'])
                    self.assertEqual(settings['extension'], extension)
                    (Path(command[command.index('-o') + 1]) / ('coin' + extension)).write_bytes(b'native-data')
                    return {'ok': True, 'editor_version': '3.8.99'}
                with patch.object(spine_native, '_run', side_effect=run):
                    result = spine_native.export_runtime(project, folder / 'exported', launcher,
                        target_version='3.8', data_format=data_format)
                self.assertTrue(result['ok'])
                self.assertEqual(len(result['file_paths']), 1)
                self.assertEqual(Path(result['file_paths'][0]).name, 'coin' + extension)


if __name__ == '__main__':
    unittest.main(verbosity=2)
