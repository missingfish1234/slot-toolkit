"""Test the built EXE after a real clean-runtime update, not just a clean launch."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from toolkit_manager.storage import atomic_json
from toolkit_manager.services import file_digest


def verify(source: Path, report: Path):
    with tempfile.TemporaryDirectory(prefix="tk-real-upgrade-") as temporary:
        root = Path(temporary)
        target = root / "installed ! % 中文"
        shutil.copytree(source, target)
        (target / "_internal" / "icuuc.dll").write_bytes(b"obsolete-incompatible-dll")
        (target / "obsolete.dll").write_bytes(b"old-root-dll")
        (target / "Tools/custom").mkdir(parents=True)
        (target / "Tools/custom/run.exe").write_bytes(b"personal-tool-placeholder")
        atomic_json(target / "config.json", {"install_root": str(target / "Tools"), "auto_check_on_start": False}, backup=False)
        request = root / "request.json"
        atomic_json(request, {"source_dir": str(source), "target_dir": str(target), "parent_pid": 0, "no_launch": True}, backup=False)
        command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(source / "_internal/apply_update.ps1"), "-RequestPath", str(request)]
        result = subprocess.run(command, capture_output=True, timeout=45, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise RuntimeError(result.stderr.decode(errors="replace"))
        assert not (target / "_internal/icuuc.dll").exists()
        assert not (target / "obsolete.dll").exists()
        assert (target / "Tools/custom/run.exe").read_bytes() == b"personal-tool-placeholder"
        assert json.loads((target / "config.json").read_text())["install_root"] == str(target / "Tools")
        manifest = json.loads((source / "release-manifest.json").read_text(encoding="utf-8-sig"))
        for name, digest in manifest["files"].items():
            if name != "config.json":
                assert file_digest(target / name) == digest, name
        backups = list(root.glob("*.backup-*"))
        assert len(backups) == 1 and (backups[0] / "_internal/icuuc.dll").exists()
        diagnostic = root / "smoke-error.txt"
        smoke = subprocess.run([str(target / "ToolkitManager.exe"), "--smoke-test"], capture_output=True, timeout=20,
            env={**os.environ, "TOOLKIT_SMOKE_REPORT": str(diagnostic)})
        if smoke.returncode:
            raise RuntimeError(diagnostic.read_text() if diagnostic.exists() else "Updated EXE failed to launch")
        output = {"version": manifest["version"], "updatedExeExit": smoke.returncode, "cleanRuntime": True,
                  "manifestVerified": True, "oldDllRetainedOnlyInBackup": True, "embeddedPersonalToolsPreserved": True, "configPreserved": True}
    atomic_json(report, output, backup=False)
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    verify(args.source.resolve(), args.report.resolve())
