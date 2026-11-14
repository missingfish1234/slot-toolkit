"""Build only from this project, with local tools and mandatory release evidence.

Read-only preflight:
  .build/venv/Scripts/python tools/build_release.py --check

For a frozen snapshot use --app-source .build/<snapshot>/app. That snapshot
must contain ../freeze.json and ../proofs/{unit-tests,verification}.json.
No overwrite, skip-gate, development, or failed-test continuation is supported.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
BUILD_ROOT = PROJECT / ".build"
VERSION_RE = re.compile(r"\d+\.\d+\.\d+")
TARGETS = {"3.8": "3.8.99", "4.0": "4.0.56", "4.2": "4.2.43"}
PACKAGES = ("pillow", "numpy", "tkinterdnd2", "pyinstaller", "setuptools")
PRIVATE_NAMES = {
    "diamond3.spine", "blue_diamond.png", "rainbow_diamond.png",
    "yellow_diamond.png", "symbol_multiplier.png",
    "luckybuddha_mg_superscatter.png", "spine.exe", "spine.com",
}
PRIVATE_HASHES = {
    "66f675606d2b61060bf4ca8f4b798613fbdaca755ca973cc54d1d316528f399f",
    "facc5f9118c106a989ce79bd023c543d710ecbb219ef592a89005832fcffcd44",
    "c277598091a40fb0ea2b22579ff033d23deef342d8d5f88a76b0dbdd6ddc8ce7",
    "fdeb461af933d0fe3d7adf3e16c9d920bffb564f558c306803041f50abf0cb22",
    "f86bd4534f98836748b859e7ec416dea08522906d1edd0f9331e6cd88782dab1",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes(source: Path) -> dict[str, str]:
    result = {}
    for path in sorted(source.glob("*.py")):
        if not contained(path, source):
            raise ValueError(f"Application module resolves outside its source folder: {path}")
        result[path.name] = sha256(path)
    return result


def contained(path: Path, root: Path) -> bool:
    return path.resolve().is_relative_to(root.resolve())


def resolve_argument(value: Path | None, default: Path, project: Path) -> Path:
    path = default if value is None else value
    return (path if path.is_absolute() else project / path).resolve()


def read_app_version(source: Path) -> str:
    """Read a literal APP_VERSION without importing or executing the app."""
    tree = ast.parse((source / "main.py").read_text(encoding="utf-8-sig"))
    values = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "APP_VERSION"
            for target in node.targets
        ):
            values.append(ast.literal_eval(node.value))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "APP_VERSION":
            values.append(ast.literal_eval(node.value))
    if len(values) != 1 or not isinstance(values[0], str) or not VERSION_RE.fullmatch(values[0]):
        raise ValueError("main.py must define one literal numeric APP_VERSION, such as '1.11.0'")
    return values[0]


def valid_source(source: Path, project: Path) -> bool:
    """A project working tree or an app folder inside its local .build only."""
    project = project.resolve()
    source = source.resolve()
    return source == project or (
        source.name == "app" and contained(source, project / ".build")
    )


def environment_status(project: Path) -> dict:
    venv = (project / ".build/venv").resolve()
    python = venv / "Scripts/python.exe"
    versions, missing = {}, []
    for name in PACKAGES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            missing.append(name)
    interpreter = Path(sys.executable).resolve()
    local = contained(venv, project) and contained(interpreter, venv)
    return {
        "python": str(interpreter), "required_python": str(python),
        "local_python_exists": python.is_file(), "using_local_environment": local,
        "package_versions": versions, "missing_packages": missing,
        "ok": python.is_file() and local and not missing,
    }


def proof_status(path: Path, hashes: dict, project: Path, count_key: str) -> dict:
    status = {"path": str(path), "exists": path.is_file(), "ok": False}
    if not contained(path, project):
        status["error"] = "Proof path resolves outside this project"
        return status
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError("Proof must be a JSON object")
        bound = document.get("source_sha256", document.get("source_hashes_before"))
        origin = document.get("application_source")
        origin_allowed = bool(origin) and valid_source(Path(origin), project)
        count = document.get(count_key)
        passed = document.get("ok", document.get("success")) is True
        status.update(
            success=passed, source_sha256_matches=bound == hashes,
            source_after_matches=document.get("source_hashes_after", hashes) == hashes,
            application_source=origin, application_source_allowed=origin_allowed,
            cases=count, sha256=sha256(path),
        )
        status["ok"] = bool(
            passed and hashes and bound == hashes and status["source_after_matches"]
            and origin_allowed and isinstance(count, int) and not isinstance(count, bool) and count > 0
        )
        if not status["ok"]:
            status["error"] = "Proof must pass, bind the exact source hashes, record a local application_source, and have a positive case count"
    except (OSError, ValueError, TypeError) as exc:
        status["error"] = str(exc)
    return status


def file_manifest(folder: Path, project: Path) -> dict[str, str]:
    if not contained(folder, project):
        raise ValueError(f"Input resolves outside this project: {folder}")
    result = {}
    for path in sorted(folder.rglob("*")):
        if not contained(path, project):
            raise ValueError(f"Input resolves outside this project: {path}")
        if path.is_file():
            result[str(path.relative_to(folder))] = sha256(path)
    return result


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Read-only JSON preflight; no directories or outputs are created")
    parser.add_argument("--version", help="Default: literal APP_VERSION read from the selected main.py")
    parser.add_argument("--dist-subdir", help="Default: v<version>, dropping only a final .0")
    parser.add_argument("--example", default="irregular-v1.10", help="One public example folder to include")
    parser.add_argument("--app-source", type=Path, help="Default: this project; snapshots must be inside its .build")
    parser.add_argument("--proof-dir", type=Path, help="Local unit/native proof directory")
    return parser.parse_args(argv)


def check_plan(arguments, *, project_root: Path = PROJECT) -> dict:
    """Read-only plan and gates. Returns JSON-compatible details, never writes."""
    project = project_root.resolve()
    build_root = (project / ".build").resolve()
    source = resolve_argument(arguments.app_source, project, project)
    errors = []
    source_allowed = valid_source(source, project) and contained(build_root, project)
    if not source_allowed:
        errors.append("Application source must be this project or a local .build/<snapshot>/app; external/old sources are rejected")
    hashes = {}
    app_version = None
    if source_allowed:
        try:
            if not (source / "assets").is_dir():
                raise ValueError("Application source requires its assets directory")
            hashes = source_hashes(source)
            app_version = read_app_version(source)
        except (OSError, ValueError, SyntaxError) as exc:
            errors.append(str(exc))
    version = arguments.version or app_version
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        errors.append("A numeric full version is required; use --version or a literal APP_VERSION")
        version = "invalid"
    elif app_version is not None and version != app_version:
        errors.append("Requested version differs from main.py APP_VERSION; update and verify the app first")
    dist_name = arguments.dist_subdir or ("v" + (version[:-2] if version.endswith(".0") else version))
    if not re.fullmatch(r"v\d+\.\d+(?:\.\d+)?", dist_name):
        errors.append("dist-subdir must be a direct versioned folder name")
        dist_name = "invalid"
    if not re.fullmatch(r"[A-Za-z0-9._-]+", arguments.example) or arguments.example in {".", ".."}:
        errors.append("Example must be a direct public folder name")
        example_name = "invalid"
    else:
        example_name = arguments.example
    is_snapshot = source_allowed and source != project
    default_proofs = source.parent / "proofs" if is_snapshot else project / "qa" / ("v" + (version[:-2] if version.endswith(".0") else version))
    proofs = resolve_argument(arguments.proof_dir, default_proofs, project)
    frozen_example = source.parent / "examples" / example_name
    example = (frozen_example if is_snapshot and frozen_example.is_dir() else project / "examples" / example_name).resolve()
    readme = source / "README_zh-TW.md"
    if not readme.is_file():
        readme = project / "README_zh-TW.md"
    paths = {
        "project": project, "application_source": source, "build_root": build_root,
        "environment": build_root / "venv", "proof_directory": proofs,
        "unit_proof": proofs / "unit-tests.json", "native_proof": proofs / "verification.json",
        "assets": source / "assets", "example": example, "readme": readme.resolve(),
        "dist_root": (project / "dist" / dist_name).resolve(),
        "archive": project / f"SpineTurnStudio-{version}-win64.zip",
        "work": (build_root / f"release-{version}").resolve(),
        "report": project / "qa" / f"portable-build-{version}.json",
    }
    paths["portable"] = paths["dist_root"] / "SpineTurnStudio"
    paths["executable"] = paths["portable"] / "SpineTurnStudio.exe"
    paths["log"] = paths["work"] / "build.log"
    paths["spec"] = paths["work"] / "SpineTurnStudio.spec"
    for label, path in paths.items():
        if label == "application_source" and not source_allowed:
            continue
        if not contained(path, project):
            errors.append(f"{label} resolves outside this project")
    snapshot_gate = None
    if is_snapshot:
        manifest_path = source.parent / "freeze.json"
        snapshot_gate = {"path": str(manifest_path), "ok": False}
        try:
            if not contained(manifest_path, project):
                raise ValueError("Snapshot freeze evidence resolves outside this project")
            frozen = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(frozen, dict):
                raise ValueError("Snapshot freeze evidence must be a JSON object")
            snapshot_gate["ok"] = frozen.get("source_sha256") == hashes
            if "snapshot" in frozen:
                snapshot_gate["ok"] = snapshot_gate["ok"] and Path(frozen["snapshot"]).resolve() == source.parent
            snapshot_gate["sha256"] = sha256(manifest_path)
        except (OSError, ValueError, TypeError) as exc:
            snapshot_gate["error"] = str(exc)
        if not snapshot_gate["ok"]:
            errors.append("Snapshot requires a matching local ../freeze.json; a relocated historical freeze is not new evidence")
    gates = {
        "unit_tests": proof_status(paths["unit_proof"], hashes, project, "tests"),
        "native_runtime": proof_status(paths["native_proof"], hashes, project, "native_cases"),
    }
    for label, status in gates.items():
        if not status["ok"]:
            errors.append(f"{label}: {status.get('error', 'proof failed')}")
    example_gate = {
        "editable_project": example.is_dir() and bool(list(example.glob("*.spturn"))),
        "native_families": {family: example.is_dir() and bool(list((example / f"spine-{family}").glob("*.spine"))) for family in TARGETS},
    }
    example_gate["ok"] = example_gate["editable_project"] and all(example_gate["native_families"].values())
    if not example_gate["ok"]:
        errors.append("The selected example requires an editable project and native projects for all three Spine families")
    collisions = {name: str(paths[name]) for name in ("dist_root", "archive", "work", "report") if paths[name].exists()}
    if collisions:
        errors.append("Existing release output is protected; choose a newly verified app version instead of overwriting")
    inputs = {}
    if source_allowed and all(contained(paths[name], project) for name in ("assets", "example", "readme")):
        try:
            inputs = {
                "assets": file_manifest(paths["assets"], project),
                "example": file_manifest(example, project),
                "readme_sha256": sha256(paths["readme"]),
            }
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
    environment = environment_status(project)
    if not environment["ok"]:
        errors.append("Use this project's .build/venv Python with the required packaging dependencies")
    return {
        "ok": not errors, "check_only": bool(arguments.check), "version": version,
        "app_version": app_version, "dist_subdir": dist_name, "example_name": example_name,
        "source_allowed": source_allowed, "source_kind": "frozen-snapshot" if is_snapshot else "working-project",
        "paths": {name: str(path) for name, path in paths.items()},
        "environment": environment, "source_sha256": hashes, "inputs": inputs,
        "snapshot_gate": snapshot_gate, "release_gates": gates, "example_gate": example_gate,
        "collisions": collisions, "errors": errors,
    }


def copy_licenses(portable: Path) -> dict[str, str]:
    notices = portable / "LICENSES"
    notices.mkdir()
    versions = {}
    for name in PACKAGES:
        distribution = metadata.distribution(name)
        versions[name] = distribution.version
        for item in distribution.files or []:
            normalized = str(item).replace("\\", "/")
            if ".dist-info/licenses/" not in normalized:
                continue
            source = Path(distribution.locate_file(item))
            target = notices / name / normalized.split(".dist-info/licenses/", 1)[1]
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_file():
                shutil.copy2(source, target)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        shutil.copy2(python_license, notices / "Python-LICENSE.txt")
    (portable / "THIRD-PARTY-NOTICES.txt").write_text(
        "Spine Turn Studio includes CPython, Tcl/Tk, Pillow, NumPy, tkinterdnd2/TkDND, "
        "and the PyInstaller bootloader. License notices are retained in LICENSES "
        "and _internal. Spine itself is not included; native conversion uses the "
        "user's separately installed and licensed editor.\n\n"
        + "\n".join(f"{name}: {version}" for name, version in versions.items()),
        encoding="utf-8",
    )
    return versions


def verify_bundle(portable: Path) -> tuple[list[Path], int]:
    files = [p for p in sorted(portable.rglob("*")) if p.is_file()]
    embedded = 0
    for path in files:
        parts = path.relative_to(portable).parts
        if path.name.casefold() in PRIVATE_NAMES or any(part.casefold() in {"qa", "output"} for part in parts):
            raise ValueError(f"Private reference, editor binary, or QA output is forbidden in a release: {path}")
        if sha256(path) in PRIVATE_HASHES:
            raise ValueError("A private raw asset entered the release under another filename")
        if path.suffix.casefold() == ".spturn":
            with zipfile.ZipFile(path) as project:
                if project.testzip() is not None:
                    raise ValueError(f"Invalid embedded project: {path}")
                for name in project.namelist():
                    if name.endswith("/"):
                        continue
                    embedded += 1
                    if hashlib.sha256(project.read(name)).hexdigest() in PRIVATE_HASHES:
                        raise ValueError("A private raw asset entered an embedded editable project")
    return files, embedded


def execute_build(arguments) -> dict:
    plan = check_plan(arguments)
    if arguments.check:
        return plan
    if not plan["ok"]:
        raise ValueError(json.dumps(plan, ensure_ascii=False, indent=2))
    paths = {name: Path(value) for name, value in plan["paths"].items()}
    # Exclusive directory/file creation is the final collision guard, including
    # a second process starting after the read-only preflight.
    paths["work"].mkdir(parents=True, exist_ok=False)
    paths["dist_root"].mkdir(parents=True, exist_ok=False)
    command = [
        sys.executable, "-m", "PyInstaller", "--clean", "--windowed", "--onedir",
        "--name", "SpineTurnStudio", "--distpath", str(paths["dist_root"]),
        "--workpath", str(paths["work"] / "work"), "--specpath", str(paths["work"]),
        "--add-data", f"{paths['assets']};assets", "--collect-all", "tkinterdnd2",
        str(paths["application_source"] / "main.py"),
    ]
    with paths["log"].open("xb") as log:
        build_env = os.environ.copy()
        for name in ('PYTHONPATH', 'PYTHONHOME'):
            build_env.pop(name, None)
        build_env.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONNOUSERSITE='1',
                         PYINSTALLER_CONFIG_DIR=str(paths['build_root'] / 'pyinstaller-cache'))
        completed = subprocess.run(command, cwd=paths["project"], stdout=log,
            stderr=subprocess.STDOUT, env=build_env, shell=False, timeout=600, check=False)
    if completed.returncode:
        raise ValueError(f"Packaging failed; inspect the local log: {paths['log']}")
    if source_hashes(paths["application_source"]) != plan["source_sha256"]:
        raise ValueError("Application source changed during packaging")
    if file_manifest(paths["assets"], paths["project"]) != plan["inputs"]["assets"]:
        raise ValueError("Public assets changed during packaging")
    if file_manifest(paths["example"], paths["project"]) != plan["inputs"]["example"]:
        raise ValueError("Public example changed during packaging")
    if sha256(paths["readme"]) != plan["inputs"]["readme_sha256"]:
        raise ValueError("The guide changed during packaging")
    for gate in plan["release_gates"].values():
        if sha256(Path(gate["path"])) != gate["sha256"]:
            raise ValueError("Release evidence changed during packaging")
    shutil.copy2(paths["readme"], paths["portable"] / "README_zh-TW.md")
    shutil.copytree(paths["example"], paths["portable"] / "examples" / plan["example_name"])
    dependencies = copy_licenses(paths["portable"])
    files, embedded = verify_bundle(paths["portable"])
    with zipfile.ZipFile(paths["archive"], "x", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in files:
            archive.write(path, path.relative_to(paths["portable"].parent))
    with zipfile.ZipFile(paths["archive"]) as archive:
        if archive.testzip() is not None:
            raise ValueError("Archive CRC validation failed")
    report = {
        "version": plan["version"], "target_spine": TARGETS, "architecture": "Windows x64",
        "executable": str(paths["executable"]), "executable_sha256": sha256(paths["executable"]),
        "archive": str(paths["archive"]), "archive_bytes": paths["archive"].stat().st_size,
        "archive_sha256": sha256(paths["archive"]), "bundled_dependencies": dependencies,
        "bundle_files": len(files), "source_sha256": plan["source_sha256"],
        "required_native_example": plan["example_name"], "application_source": str(paths["application_source"]),
        "archive_crc_validated": True, "release_gates": plan["release_gates"],
        "private_source_hash_exclusion": True, "editable_project_embedded_members_checked": embedded,
        "local_paths": plan["paths"], "builder_sha256": sha256(Path(__file__)),
    }
    paths["report"].parent.mkdir(parents=True, exist_ok=True)
    with paths["report"].open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    return report


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    arguments = parse_arguments(argv)
    plan = check_plan(arguments)
    if arguments.check:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0 if plan["ok"] else 2
    if not plan["ok"]:
        print(json.dumps(plan, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    try:
        report = execute_build(arguments)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
