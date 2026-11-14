"""Migration guards using synthetic projects, never real release evidence."""
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import uuid


PROJECT = Path(__file__).resolve().parents[2]


def load_module(path):
    name = 'workspace_path_fixture_' + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def tree_state(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
            for p in sorted(root.rglob('*'))}


class _ProjectFixture:
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='Spine packaging path QA ')
        self.addCleanup(temporary.cleanup)
        self.container = Path(temporary.name)
        self.root = self.container / '中文 工作區 with spaces' / 'spine-turn-tool'
        (self.root / 'tools').mkdir(parents=True)
        shutil.copy2(PROJECT / 'tools/build_release.py', self.root / 'tools/build_release.py')
        self.builder = load_module(self.root / 'tools/build_release.py')
        self.version = '1.12.0'  # A future version must have the same mandatory gates.
        self.write_source(self.root)
        (self.root / 'README_zh-TW.md').write_text('Synthetic test fixture, not release evidence.', encoding='utf-8')
        example = self.root / 'examples/public-fixture'
        example.mkdir(parents=True)
        (example / 'fixture.spturn').write_bytes(b'synthetic editable fixture')
        for family in ('3.8', '4.0', '4.2'):
            directory = example / ('spine-' + family)
            directory.mkdir()
            (directory / 'fixture.spine').write_bytes(b'synthetic native fixture, not validated')
        self.python = self.root / '.build/venv/Scripts/python.exe'
        self.python.parent.mkdir(parents=True)
        self.python.write_bytes(b'not executable: observations are mocked')
        self.proofs = self.root / 'qa/v1.12'
        self.write_proofs(self.root, self.proofs)

    def write_source(self, source):
        (source / 'assets').mkdir(parents=True)
        (source / 'assets/public.bin').write_bytes(b'synthetic public asset')
        (source / 'main.py').write_text(
            "APP_VERSION = '1.12.0'\nraise RuntimeError('Preflight must not execute fixture app')\n", encoding='utf-8')
        (source / 'helper.py').write_text('SYNTHETIC_FIXTURE = True\n', encoding='utf-8')

    def write_proofs(self, source, directory, *, origin=None, passed=True):
        directory.mkdir(parents=True, exist_ok=True)
        hashes = self.builder.source_hashes(source)
        for name, count in (('unit-tests.json', 'tests'), ('verification.json', 'native_cases')):
            (directory / name).write_text(json.dumps({
                'synthetic_test_fixture': True, 'ok': passed, count: 1,
                'source_sha256': hashes, 'source_hashes_after': hashes,
                'application_source': str(origin or source),
            }), encoding='utf-8')

    def args(self, *extra):
        return self.builder.parse_arguments(['--example', 'public-fixture', *extra])

    @contextmanager
    def local_environment(self):
        # Exercise environment_status itself; only its external observations vary.
        with patch.object(self.builder.sys, 'executable', str(self.python)), \
                patch.object(self.builder.metadata, 'version', return_value='synthetic-installed-version'):
            yield

    def plan(self, *extra):
        with self.local_environment():
            return self.builder.check_plan(self.args(*extra))


class BuilderPathTests(_ProjectFixture, unittest.TestCase):
    def test_script_location_not_cwd_selects_chinese_space_root_and_local_build(self):
        previous = Path.cwd()
        try:
            os.chdir(self.container)
            plan = self.plan('--check')
        finally:
            os.chdir(previous)
        self.assertTrue(plan['ok'], plan['errors'])
        self.assertEqual(self.builder.PROJECT, self.root.resolve())
        self.assertEqual(self.builder.BUILD_ROOT, self.root.resolve() / '.build')
        self.assertEqual(Path(plan['paths']['application_source']), self.root.resolve())
        self.assertTrue(all(Path(p).resolve().is_relative_to(self.root.resolve()) for p in plan['paths'].values()))
        self.assertFalse((self.root / 'dist').exists())

    def test_check_cli_and_direct_api_are_read_only_even_when_ready(self):
        before = tree_state(self.root)
        with self.local_environment(), patch.object(self.builder.subprocess, 'run') as process:
            output = io.StringIO()
            with redirect_stdout(output):
                code = self.builder.main(['--check', '--example', 'public-fixture'])
            direct = self.builder.execute_build(self.args('--check'))
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(output.getvalue())['ok'])
        self.assertTrue(direct['ok'])
        process.assert_not_called()
        self.assertEqual(tree_state(self.root), before)

    def test_future_version_missing_or_failed_proof_never_builds_or_writes(self):
        (self.proofs / 'unit-tests.json').unlink()
        for failed in (False, True):
            if failed:
                self.write_proofs(self.root, self.proofs, passed=False)
            before = tree_state(self.root)
            with self.local_environment(), patch.object(self.builder.subprocess, 'run') as process, \
                    redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = self.builder.main(['--check', '--example', 'public-fixture'])
                build_code = self.builder.main(['--example', 'public-fixture'])
            self.assertEqual((code, build_code), (2, 2))
            process.assert_not_called()
            self.assertEqual(tree_state(self.root), before)

    def test_external_and_old_application_sources_are_rejected_before_hashing(self):
        for source in (Path(r'E:\MINIMAX H3\spine-turn-tool'), self.container / 'other/app',
                       self.root / '.build/../../escaped/app'):
            with self.subTest(source=source), self.local_environment(), \
                    patch.object(self.builder, 'source_hashes', wraps=self.builder.source_hashes) as digest:
                plan = self.builder.check_plan(self.args('--check', '--app-source', str(source)))
                self.assertFalse(plan['source_allowed'])
                self.assertFalse(plan['ok'])
                self.assertEqual(plan['source_sha256'], {})
                digest.assert_not_called()

    def test_matching_hashes_do_not_relabel_historical_external_proof_origins(self):
        self.write_proofs(self.root, self.proofs, origin=Path(r'E:\MINIMAX H3\spine-turn-tool'))
        plan = self.plan('--check')
        self.assertFalse(plan['ok'])
        for gate in plan['release_gates'].values():
            self.assertTrue(gate['source_sha256_matches'])
            self.assertFalse(gate['application_source_allowed'])
            self.assertFalse(gate['ok'])

    def test_proofs_outside_current_project_are_not_accepted(self):
        outside = self.container / 'outside proofs'
        self.write_proofs(self.root, outside)
        before = tree_state(self.root)
        plan = self.plan('--check', '--proof-dir', str(outside))
        self.assertFalse(plan['ok'])
        self.assertTrue(all(not gate['ok'] for gate in plan['release_gates'].values()))
        self.assertEqual(tree_state(self.root), before)

    def test_snapshot_requires_its_real_source_manifest_and_local_origin(self):
        snapshot = self.root / '.build/frozen fixture/app'
        self.write_source(snapshot)
        self.write_proofs(snapshot, snapshot.parent / 'proofs')
        args = ('--check', '--app-source', str(snapshot))
        self.assertFalse(self.plan(*args)['snapshot_gate']['ok'])
        freeze = snapshot.parent / 'freeze.json'
        freeze.write_text(json.dumps({'snapshot': str(snapshot.parent),
            'source_sha256': self.builder.source_hashes(snapshot)}), encoding='utf-8')
        self.assertTrue(self.plan(*args)['ok'])
        document = json.loads(freeze.read_text(encoding='utf-8'))
        document['source_sha256']['helper.py'] = '0' * 64
        freeze.write_text(json.dumps(document), encoding='utf-8')
        self.assertFalse(self.plan(*args)['snapshot_gate']['ok'])

    def test_non_object_proof_and_freeze_json_returns_failed_gate_without_traceback(self):
        for value in ([], None):
            (self.proofs / 'unit-tests.json').write_text(json.dumps(value), encoding='utf-8')
            before = tree_state(self.root)
            plan = self.plan('--check')
            self.assertFalse(plan['ok'])
            self.assertFalse(plan['release_gates']['unit_tests']['ok'])
            self.assertEqual(tree_state(self.root), before)
        self.write_proofs(self.root, self.proofs)
        snapshot = self.root / '.build/malformed freeze/app'
        self.write_source(snapshot)
        self.write_proofs(snapshot, snapshot.parent / 'proofs')
        for value in ([], None):
            (snapshot.parent / 'freeze.json').write_text(json.dumps(value), encoding='utf-8')
            before = tree_state(self.root)
            plan = self.plan('--check', '--app-source', str(snapshot))
            self.assertFalse(plan['snapshot_gate']['ok'])
            self.assertEqual(tree_state(self.root), before)

    def test_existing_release_dist_zip_work_or_report_is_never_overwritten(self):
        paths = self.plan('--check')['paths']
        for name in ('dist_root', 'archive', 'work', 'report'):
            path = Path(paths[name])
            if name in ('dist_root', 'work'):
                path.mkdir(parents=True)
                (path / 'artist-sentinel').write_bytes(b'preserve existing directory')
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'preserve existing file')
            before = tree_state(self.root)
            with self.local_environment(), patch.object(self.builder.subprocess, 'run') as process, \
                    redirect_stderr(io.StringIO()):
                plan = self.builder.check_plan(self.args())
                code = self.builder.main(['--example', 'public-fixture'])
            self.assertIn(name, plan['collisions'])
            self.assertEqual(code, 2)
            process.assert_not_called()
            self.assertEqual(tree_state(self.root), before)

    def test_local_environment_and_dependencies_are_real_preflight_gates(self):
        self.assertTrue(self.plan('--check')['environment']['ok'])
        with patch.object(self.builder.metadata, 'version', return_value='synthetic-installed-version'):
            external = self.builder.check_plan(self.args('--check'))
        self.assertFalse(external['environment']['using_local_environment'])
        self.assertFalse(external['ok'])
        with patch.object(self.builder.sys, 'executable', str(self.python)), \
                patch.object(self.builder.metadata, 'version', side_effect=self.builder.metadata.PackageNotFoundError):
            missing = self.builder.check_plan(self.args('--check'))
        self.assertFalse(missing['environment']['ok'])
        self.assertFalse(missing['ok'])

    def test_no_development_skip_overwrite_or_unverified_version_bypass(self):
        before = tree_state(self.root)
        for flag in ('--dev', '--overwrite', '--skip-gates'):
            with self.subTest(flag=flag), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                self.builder.parse_arguments([flag])
            self.assertEqual(error.exception.code, 2)
        plan = self.plan('--check', '--version', '1.11.0')
        self.assertFalse(plan['ok'])
        self.assertEqual(tree_state(self.root), before)

    def test_failed_packager_stops_before_copy_archive_and_release_report(self):
        args = self.args()
        with self.local_environment(), \
                patch.dict(os.environ, PYTHONPATH='old modules', PYTHONHOME='old runtime'), \
                patch.object(self.builder.subprocess, 'run', return_value=SimpleNamespace(returncode=1)) as package, \
                patch.object(self.builder, 'verify_bundle') as audit, \
                self.assertRaises(ValueError):
            self.builder.execute_build(args)
        audit.assert_not_called()
        environment = package.call_args.kwargs['env']
        self.assertNotIn('PYTHONPATH', environment)
        self.assertNotIn('PYTHONHOME', environment)
        self.assertTrue(Path(environment['PYINSTALLER_CONFIG_DIR']).is_relative_to(self.root))
        self.assertFalse((self.root / f'SpineTurnStudio-{self.version}-win64.zip').exists())
        self.assertFalse((self.root / f'qa/portable-build-{self.version}.json').exists())


class LauncherPathTests(_ProjectFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.pythonw = self.python.with_name('pythonw.exe')
        self.pythonw.write_bytes(b'not executable: Popen is mocked')
        shutil.copy2(PROJECT / 'tools/workspace.py', self.root / 'tools/workspace.py')
        with patch.dict(sys.modules, {'build_release': self.builder}):
            self.workspace = load_module(self.root / 'tools/workspace.py')

    @contextmanager
    def local_interpreter(self):
        with patch.object(self.workspace.sys, 'prefix', str(self.root / '.build/venv')), \
                patch.object(self.workspace.sys, 'executable', str(self.python)):
            yield

    def test_launch_check_uses_script_root_and_never_starts_process_or_writes(self):
        previous = Path.cwd()
        before = tree_state(self.root)
        try:
            os.chdir(self.container)
            with patch.object(self.workspace.subprocess, 'Popen') as process:
                plan = self.workspace.launch(check=True)
        finally:
            os.chdir(previous)
        process.assert_not_called()
        self.assertEqual(self.workspace.ROOT, self.root.resolve())
        self.assertEqual(self.workspace.LOCAL_ENV, self.root.resolve() / '.build/venv')
        self.assertEqual(plan['command'], [str(self.pythonw.resolve()), str(self.root / 'main.py')])
        self.assertEqual(Path(plan['cwd']), self.root.resolve())
        self.assertEqual(Path(plan['launch_log']), self.root / '.build/launch.log')
        self.assertFalse(Path(plan['launch_log']).exists())
        self.assertEqual(tree_state(self.root), before)

    def test_launch_has_one_local_pythonw_command_with_clean_environment(self):
        wait = Mock(side_effect=subprocess.TimeoutExpired('synthetic-pythonw', 1.5))
        with self.local_interpreter(), patch.dict(os.environ, PYTHONPATH='old external path', PYTHONHOME='old home'), \
                patch.object(self.workspace.subprocess, 'Popen', return_value=SimpleNamespace(pid=123, wait=wait)) as process:
            result = self.workspace.launch()
        self.assertEqual(result['pid'], 123)
        self.assertEqual(result['startup_status'], 'running')
        wait.assert_called_once_with(timeout=1.5)
        process.assert_called_once()
        self.assertEqual(process.call_args.args[0], [str(self.pythonw), str(self.root / 'main.py')])
        self.assertEqual(Path(process.call_args.kwargs['cwd']), self.root)
        self.assertFalse(process.call_args.kwargs['shell'])
        self.assertEqual(Path(process.call_args.kwargs['stdout'].name), self.root / '.build/launch.log')
        self.assertEqual(process.call_args.kwargs['stderr'], subprocess.STDOUT)
        environment = process.call_args.kwargs['env']
        self.assertNotIn('PYTHONPATH', environment)
        self.assertNotIn('PYTHONHOME', environment)
        self.assertEqual(environment['PYTHONUTF8'], '1')
        self.assertTrue(Path(environment['PYINSTALLER_CONFIG_DIR']).is_relative_to(self.root))

    def test_launch_failure_propagates_and_main_returns_failure_without_fallback(self):
        with self.local_interpreter(), \
                patch.object(self.workspace.subprocess, 'Popen', side_effect=OSError('synthetic launch failure')) as process, \
                patch.object(self.workspace.subprocess, 'run') as other_process:
            with self.assertRaises(OSError):
                self.workspace.launch()
            self.assertEqual(process.call_count, 1)
            process.reset_mock()
            with redirect_stderr(io.StringIO()):
                self.assertEqual(self.workspace.main(['launch']), 1)
            process.assert_called_once()
            other_process.assert_not_called()

    def test_nonzero_child_exit_is_failure_and_never_falls_back(self):
        wait = Mock(return_value=7)
        with self.local_interpreter(), \
                patch.object(self.workspace.subprocess, 'Popen', return_value=SimpleNamespace(pid=456, wait=wait)) as process, \
                patch.object(self.workspace.subprocess, 'run') as other_process:
            with self.assertRaises(RuntimeError) as error:
                self.workspace.launch()
            self.assertIn(str(self.root / '.build/launch.log'), str(error.exception))
            self.assertTrue((self.root / '.build/launch.log').is_file())
            process.assert_called_once()
            wait.assert_called_once_with(timeout=1.5)
            process.reset_mock()
            wait.reset_mock()
            with redirect_stderr(io.StringIO()):
                self.assertEqual(self.workspace.main(['launch']), 1)
            process.assert_called_once()
            wait.assert_called_once_with(timeout=1.5)
            other_process.assert_not_called()

    def test_clean_early_child_exit_is_reported_closed_not_running(self):
        wait = Mock(return_value=0)
        with self.local_interpreter(), \
                patch.object(self.workspace.subprocess, 'Popen', return_value=SimpleNamespace(pid=789, wait=wait)) as process:
            result = self.workspace.launch()
        self.assertEqual(result['startup_status'], 'closed')
        wait.assert_called_once_with(timeout=1.5)
        process.assert_called_once()

    def test_missing_or_nonlocal_environment_stops_before_any_launch(self):
        with patch.object(self.workspace.subprocess, 'Popen') as process:
            with self.assertRaises(ValueError):
                self.workspace.launch()
            self.pythonw.unlink()
            with self.assertRaises(ValueError):
                self.workspace.launch(check=True)
        process.assert_not_called()

    def test_child_rejects_resolved_escape_and_clean_env_does_not_mutate_parent(self):
        with self.assertRaises(ValueError):
            self.workspace.child(self.root, '../outside')
        with patch.dict(os.environ, PYTHONPATH='external modules', PYTHONHOME='external runtime', KEEP_WORKSPACE_TEST='kept'):
            clean = self.workspace.clean_env()
            self.assertEqual(os.environ['PYTHONPATH'], 'external modules')
            self.assertEqual(os.environ['PYTHONHOME'], 'external runtime')
            self.assertNotIn('PYTHONPATH', clean)
            self.assertNotIn('PYTHONHOME', clean)
            self.assertEqual(clean['KEEP_WORKSPACE_TEST'], 'kept')
            self.assertEqual(clean['PYTHONNOUSERSITE'], '1')

    def test_failed_development_tests_stop_before_pyinstaller_or_output(self):
        with self.local_interpreter(), \
                patch.object(self.workspace, 'run_tests', return_value={'ok': False, 'tests': 1}) as tests, \
                patch.object(self.workspace.subprocess, 'run') as package, \
                self.assertRaises(RuntimeError):
            self.workspace.dev_build()
        tests.assert_called_once()
        package.assert_not_called()
        self.assertFalse((self.root / 'dist/dev').exists())
        self.assertFalse(list(self.root.rglob('DEV-BUILD.json')))

    def test_failed_development_packager_does_not_publish_success_report(self):
        with self.local_interpreter(), \
                patch.object(self.workspace, 'run_tests', return_value={'ok': True, 'tests': 1}), \
                patch.object(self.workspace.subprocess, 'run', return_value=SimpleNamespace(returncode=1)) as package, \
                patch.object(self.workspace, 'copy_licenses') as notices, \
                self.assertRaises(RuntimeError):
            self.workspace.dev_build()
        package.assert_called_once()
        self.assertEqual(package.call_args.args[0][:3], [str(self.python), '-m', 'PyInstaller'])
        notices.assert_not_called()
        self.assertFalse(list(self.root.rglob('DEV-BUILD.json')))
        self.assertFalse(list(self.root.rglob('build-report.json')))


if __name__ == '__main__':
    unittest.main(verbosity=2)
