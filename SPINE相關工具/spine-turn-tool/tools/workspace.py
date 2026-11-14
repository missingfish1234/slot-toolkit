"""Local launch, environment and development builds; no fallback to other copies."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
import uuid
import venv
from build_release import read_app_version, source_hashes, copy_licenses

ROOT = Path(__file__).resolve().parents[1]
LOCAL_ENV = ROOT / '.build/venv'

def clean_env(project=ROOT):
    result = os.environ.copy()
    for key in ('PYTHONPATH', 'PYTHONHOME'):
        result.pop(key, None)
    result.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONNOUSERSITE='1')
    result['PYINSTALLER_CONFIG_DIR'] = str(child(project, '.build/pyinstaller-cache'))
    return result

def child(project, relative):
    project = Path(project).resolve()
    result = (project / relative).resolve()
    if not result.is_relative_to(project):
        raise ValueError(f'Path resolves outside this project: {result}')
    return result

def launch_plan(project=ROOT):
    project = Path(project).resolve()
    main = child(project, 'main.py')
    python = child(project, '.build/venv/Scripts/python.exe')
    pythonw = child(project, '.build/venv/Scripts/pythonw.exe')
    if not main.is_file():
        raise ValueError(f'Application source is missing: {main}')
    if not python.is_file() or not pythonw.is_file():
        raise ValueError('Local environment is missing; run environment setup first.')
    return dict(project=str(project), version=read_app_version(project), cwd=str(project),
                python=str(python), command=[str(pythonw), str(main)],
                development_output=str(child(project, 'dist/dev')),
                formal_output=str(child(project, 'dist')), build_cache=str(child(project, '.build')),
                launch_log=str(child(project, '.build/launch.log')))

def require_local(project=ROOT):
    target = child(project, '.build/venv')
    if Path(sys.prefix).resolve() != target or not Path(sys.executable).resolve().is_relative_to(target):
        raise ValueError(f'Use local Python: {target / "Scripts/python.exe"}')

def environment_status(project=ROOT):
    packages, problems = {}, []
    for line in child(project, 'tools/build-requirements.txt').read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        name, expected = line.strip().split('==', 1)
        try:
            distribution = metadata.distribution(name)
            packages[name] = dict(version=distribution.version, location=str(distribution.locate_file('')))
            if distribution.version != expected:
                problems.append(f'{name}: expected {expected}, got {distribution.version}')
        except metadata.PackageNotFoundError:
            problems.append(f'Missing {name}=={expected}')
    return dict(ok=not problems, packages=packages, problems=problems,
                python=str(Path(sys.executable).resolve()), prefix=str(Path(sys.prefix).resolve()))

def setup(project=ROOT):
    project = Path(project).resolve()
    target = child(project, '.build/venv')
    # Generate fresh launchers/config; do not copy a non-relocatable venv.
    venv.EnvBuilder(with_pip=True, system_site_packages=True).create(target)
    python = target / 'Scripts/python.exe'
    log = child(project, '.build/setup.log')
    with log.open('wb') as stream:
        result = subprocess.run([str(python), '-m', 'pip', 'install', '--no-input',
            '--disable-pip-version-check', '-r', str(child(project, 'tools/build-requirements.txt'))],
            cwd=project, env=clean_env(project), stdout=stream, stderr=subprocess.STDOUT, shell=False)
    if result.returncode:
        raise RuntimeError(f'Environment setup failed; see {log}')
    result = subprocess.run([str(python), '-B', str(child(project, 'tools/workspace.py')), 'check'],
        cwd=project, env=clean_env(project), capture_output=True, text=True, encoding='utf-8', shell=False)
    if result.returncode:
        raise RuntimeError(f'Environment verification failed: {result.stdout}\n{result.stderr}')
    record = json.loads(result.stdout)
    child(project, '.build/environment.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return record

def launch(*, check=False, project=ROOT):
    plan = launch_plan(project)
    if check:
        return plan
    require_local(project)
    log = Path(plan['launch_log'])
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('ab') as stream:
        process = subprocess.Popen(plan['command'], cwd=plan['cwd'], env=clean_env(project),
            stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT, shell=False)
        try:
            code = process.wait(timeout=1.5)
        except subprocess.TimeoutExpired:
            code = None
    if code not in (None, 0):
        raise RuntimeError(f'Application startup failed (exit {code}); see {log}')
    return dict(plan, pid=process.pid, startup_status='running' if code is None else 'closed')

def run_tests(work, project=ROOT):
    project, work = Path(project).resolve(), Path(work).resolve()
    before = source_hashes(project)
    sys.path.insert(0, str(project))
    suite = unittest.defaultTestLoader.discover(str(project / 'tests'), pattern='test_*.py')
    with (work / 'unit-tests.log').open('w', encoding='utf-8') as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    after = source_hashes(project)
    modules = {name: str(Path(sys.modules[name].__file__).resolve())
               for name in (Path(filename).stem for filename in before)
               if name in sys.modules and getattr(sys.modules[name], '__file__', None)}
    local = all(Path(value).is_relative_to(project) for value in modules.values())
    report = dict(ok=result.wasSuccessful() and before == after and local,
        tests=result.testsRun, skipped=len(result.skipped), application_source=str(project),
        source_sha256=before, source_hashes_after=after, application_module_files=modules,
        all_application_imports_local=local, failures=len(result.failures), errors=len(result.errors))
    (work / 'unit-tests.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report

def dev_build(project=ROOT):
    project = Path(project).resolve()
    require_local(project)
    plan = launch_plan(project)
    before = source_hashes(project)
    token = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6]
    work, output = child(project, '.build/dev/' + token), child(project, 'dist/dev/' + token)
    if work.exists() or output.exists():
        raise ValueError('Build directory exists; no files were overwritten.')
    work.mkdir(parents=True)
    tests = run_tests(work, project)
    if not tests['ok']:
        raise RuntimeError(f'Unit tests failed; packaging stopped. See {work / "unit-tests.log"}')
    command = [plan['python'], '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed', '--onedir',
        '--name', 'SpineTurnStudio', '--distpath', str(output), '--workpath', str(work / 'work'),
        '--specpath', str(work), '--add-data', f'{project / "assets"};assets',
        '--collect-all', 'tkinterdnd2', str(child(project, 'main.py'))]
    with (work / 'build.log').open('wb') as stream:
        result = subprocess.run(command, cwd=project, env=clean_env(project), stdout=stream,
                                stderr=subprocess.STDOUT, shell=False, timeout=600)
    if result.returncode:
        raise RuntimeError(f'Packaging failed; see {work / "build.log"}')
    bundle, executable = output / 'SpineTurnStudio', output / 'SpineTurnStudio/SpineTurnStudio.exe'
    if not executable.is_file() or source_hashes(project) != before:
        raise RuntimeError('Build incomplete or source changed; do not distribute this output.')
    shutil.copy2(project / 'README_zh-TW.md', bundle / 'README_zh-TW.md')
    copy_licenses(bundle)
    record = dict(version=plan['version'], application_source=str(project), python=plan['python'],
        source_sha256=before, source_hashes_after=source_hashes(project), executable=str(executable),
        executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(), output=str(output),
        work=str(work), tests=tests['tests'], development_build=True, native_release_checks_run=False)
    text = json.dumps(record, ensure_ascii=False, indent=2)
    (bundle / 'DEV-BUILD.json').write_text(text, encoding='utf-8')
    (work / 'build-report.json').write_text(text, encoding='utf-8')
    return record

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('setup', 'check', 'launch', 'dev-build'))
    parser.add_argument('--check', action='store_true', help='Show launch plan without opening the app')
    args = parser.parse_args(argv)
    try:
        if args.action == 'setup':
            record = setup()
        elif args.action == 'check':
            require_local()
            record = dict(launch_plan(), environment=environment_status())
            if not record['environment']['ok']:
                raise ValueError('; '.join(record['environment']['problems']))
        elif args.action == 'launch':
            record = launch(check=args.check)
        else:
            record = dev_build()
        print(json.dumps(record, ensure_ascii=True, indent=2))
        return 0
    except Exception as error:
        print(f'Failed: {error}', file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
