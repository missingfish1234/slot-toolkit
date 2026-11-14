"""Optional, version-pinned bridge to a locally licensed Spine installation.

The exporter remains usable without Spine: no file is presented as a native
project until the real editor has successfully imported it. CLI output is
intentionally kept private because Spine writes license-holder details there.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any
from spine_turn_formats import SPINE_TARGETS, normalize_spine_version


TARGET_VERSION = SPINE_TARGETS['4.0']
TARGET_VERSIONS = dict(SPINE_TARGETS)


def resolve_target_version(version: str = TARGET_VERSION) -> str:
    """Resolve a family to its pinned revision; never select 'latest'."""
    return normalize_spine_version(version)


def cached_spine_versions() -> list[str]:
    """Read revision filenames only, never activation or license information."""
    directory = Path.home() / "Spine" / "updates"
    if not directory.is_dir():
        return []
    versions = [path.name for path in directory.iterdir()
                if re.fullmatch(r"(?:3\.8|4\.0|4\.2)\.\d+", path.name)]
    return sorted(versions, key=lambda value: tuple(map(int, value.split('.'))))


def discover_spine() -> str | None:
    """Return an installed console launcher, without starting it or reading keys."""
    candidates: list[Path] = []
    configured = os.environ.get("SPINE_EXECUTABLE", "").strip().strip('"')
    if configured:
        candidates.append(Path(configured).expanduser())
    for root in (
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.environ.get("LOCALAPPDATA", ""),
        "E:/",
        "D:/",
    ):
        if not root:
            continue
        for relative in ("Spine", "Programs/Spine", "Spine Professional"):
            for filename in ("Spine.com", "Spine.exe"):
                candidates.append(Path(root) / relative / filename)
    for candidate in candidates:
        if candidate.is_file():
            # Prefer the waiting console application over its GUI sibling.
            console = candidate.with_suffix(".com")
            return str(console if console.is_file() else candidate)
    return None


def _run(command: list[str], timeout: float) -> dict[str, Any]:
    """Run the console editor, never forwarding its private startup banner."""
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    version = command[command.index('--update') + 1] if '--update' in command else TARGET_VERSION
    try:
        completed = subprocess.run(
            command,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            creationflags=flags,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "timeout", "message": f"Spine 轉換逾時。請確認本機 Spine {version} 可正常啟動，再重試。"}
    except OSError:
        return {"ok": False, "reason": "launch_failed", "message": "無法啟動 Spine。請重新選擇本機 Spine.com。"}
    if completed.returncode != 0:
        # Recognize useful causes, but never retain or display CLI output.
        combined = (completed.stdout + completed.stderr).decode("utf-8", errors="replace").lower()
        if any(token in combined for token in ("activation", "not activated", "license expired", "licence expired")):
            reason = "activation_required"
            message = "Spine 需要完成授權啟用。請先開啟本機 Spine 完成設定，再重試。"
        elif any(token in combined for token in ("unable to download", "failed to download", "update not found")):
            reason = "version_unavailable"
            message = f"本機尚未備妥 Spine {version}。請先在 Spine 啟動器下載並啟動此版本。"
        else:
            reason = "editor_rejected_data"
            message = f"Spine 匯入未完成（結束代碼 {completed.returncode}）。JSON 與圖片已保留，可在 {version} 使用「匯入資料」檢查。"
        return {"ok": False, "reason": reason, "returncode": completed.returncode, "message": message}
    private_output = (completed.stdout + completed.stderr).decode("utf-8", errors="replace")
    reported = re.search(r"(?im)^Spine\s+(?:Editor\s+)?(\d+\.\d+\.\d+)\b", private_output)
    if reported and reported.group(1) != version:
        return {"ok": False, "reason": "wrong_editor_version", "returncode": 0,
                "requested_version": version, "reported_version": reported.group(1),
                "message": f"Spine 實際啟動版本與指定 {version} 不同，已停止建立原生專案。"}
    result = {"ok": True, "returncode": 0}
    if reported:
        result["editor_version"] = reported.group(1)
    return result


def _launcher(executable: str | Path | None) -> str | None:
    found = str(executable) if executable else discover_spine()
    if not found:
        return None
    path = Path(found).expanduser()
    if not path.is_file():
        return None
    console = path.with_suffix(".com")
    return str(console if console.is_file() else path)


def convert_project(
    json_path: str | Path,
    output_path: str | Path,
    executable: str | Path | None = None,
    version: str = TARGET_VERSION,
    *,
    target_version: str | None = None,
    timeout: float = 120,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Import JSON into a fresh native project, then move it into place.

    Existing projects are protected by default. Set ``overwrite=True`` only
    when replacing a generated destination is intentional; the old project is
    still untouched until the editor has produced a complete new file.
    The staging project is created beside the destination so relative image
    paths have the same meaning before and after the atomic move.
    """
    try:
        version = resolve_target_version(target_version if target_version is not None else version)
    except ValueError as error:
        return {"ok": False, "status": "error", "reason": "invalid_version", "message": str(error)}
    source = Path(json_path).resolve()
    output = Path(output_path).resolve()
    base = {"json_path": str(source), "project_path": str(output), "version": version}
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        return {**base, "ok": False, "status": "error", "reason": "invalid_version", "message": "Spine 版本必須使用完整版本號，例如 4.0.56。"}
    if not source.is_file() or source.suffix.lower() != ".json":
        return {**base, "ok": False, "status": "error", "reason": "invalid_input", "message": "找不到可匯入的 Spine JSON。"}
    if output.suffix.lower() != ".spine":
        return {**base, "ok": False, "status": "error", "reason": "invalid_output", "message": "原生專案輸出名稱必須以 .spine 結尾。"}
    try:
        document = json.loads(source.read_text(encoding="utf-8-sig"))
        declared = document.get("skeleton", {}).get("spine", "")
    except (OSError, ValueError, AttributeError):
        return {**base, "ok": False, "status": "error", "reason": "invalid_json", "message": "Spine JSON 格式無法讀取。"}
    if declared and declared != version:
        return {**base, "ok": False, "status": "error", "reason": "version_mismatch", "message": f"資料版本為 {declared}，與目標 {version} 不同。請使用相符版本重新輸出。"}
    if output.exists() and not overwrite:
        return {**base, "ok": False, "status": "error", "reason": "output_exists", "message": "此 Spine 專案已存在。請選擇新名稱，避免覆蓋已編輯內容。"}
    launcher = _launcher(executable)
    if not launcher:
        return {**base, "ok": False, "status": "unavailable", "reason": "spine_not_found", "message": f"未找到本機 Spine；已保留可匯入 JSON。安裝並啟用 Spine {version} 後即可轉為 .spine。"}
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, staging_name = tempfile.mkstemp(prefix=".spine-import-", suffix=".spine", dir=output.parent)
    os.close(descriptor)
    staging = Path(staging_name)
    # Spine treats an existing output as an append target. It must not exist.
    staging.unlink()
    try:
        result = _run([launcher, "--update", version, "-i", str(source), "-o", str(staging), "-r", source.stem], timeout)
        if not result["ok"]:
            return {**base, **result, "status": "error"}
        if not staging.is_file() or staging.stat().st_size == 0:
            return {**base, "ok": False, "status": "error", "reason": "missing_project", "message": "Spine 未產生原生專案。JSON 與圖片已保留。"}
        if output.exists() and not overwrite:
            return {**base, "ok": False, "status": "error", "reason": "output_exists", "message": "輸出位置已出現同名專案，已保留原檔。請選擇新名稱。"}
        os.replace(staging, output)
        return {**base, "ok": True, "status": "success", "message": f"已透過 Spine {version} 建立原生 .spine 專案。"}
    except OSError:
        return {**base, "ok": False, "status": "error", "reason": "write_failed", "message": "無法寫入原生專案。請檢查目的資料夾權限與磁碟空間。"}
    finally:
        if staging.exists():
            staging.unlink(missing_ok=True)


def export_runtime(
    project_path: str | Path,
    output_dir: str | Path,
    executable: str | Path | None = None,
    version: str = TARGET_VERSION,
    *,
    target_version: str | None = None,
    data_format: str = "json",
    timeout: float = 120,
) -> dict[str, Any]:
    """Export JSON with the real editor for a native round-trip check.

    ``output_dir`` should be a separate review directory. This function does
    not overwrite the engine's authored import JSON or alter the project.
    """
    try:
        version = resolve_target_version(target_version if target_version is not None else version)
    except ValueError as error:
        return {"ok": False, "status": "error", "reason": "invalid_version", "message": str(error)}
    if data_format not in ('json', 'binary'):
        return {"ok": False, "status": "error", "reason": "invalid_format", "message": "原生資料匯出格式必須為 JSON 或 Binary。"}
    source = Path(project_path).resolve()
    destination = Path(output_dir).resolve()
    base = {"project_path": str(source), "output_dir": str(destination), "version": version}
    if not re.fullmatch(r"\d+\.\d+\.\d+", version) or not source.is_file() or source.suffix.lower() != ".spine":
        return {**base, "ok": False, "status": "error", "reason": "invalid_input", "message": "找不到可重新匯出的 Spine 專案，或版本格式不正確。"}
    launcher = _launcher(executable)
    if not launcher:
        return {**base, "ok": False, "status": "unavailable", "reason": "spine_not_found", "message": "未找到本機 Spine。"}
    destination.mkdir(parents=True, exist_ok=True)
    # A fresh staging directory keeps a failed export from looking successful.
    with tempfile.TemporaryDirectory(prefix=".spine-export-", dir=destination) as temporary:
        staging = Path(temporary)
        export_argument = data_format
        settings_path = None
        if version.startswith('3.8.'):
            # The 3.8 legacy launcher accepts a settings file, not 4.x's
            # convenient `-e json` / `-e binary` shorthand.
            settings_path = staging / '.native-export-settings.json'
            settings_path.write_text(json.dumps({
                'class': 'export-binary' if data_format == 'binary' else 'export-json',
                'name': 'Binary' if data_format == 'binary' else 'JSON',
                'project': str(source), 'output': str(staging), 'open': False,
                'extension': '.skel' if data_format == 'binary' else '.json',
                'nonessential': True, 'cleanUp': False, 'warnings': False,
            }), encoding='utf-8')
            export_argument = str(settings_path)
        result = _run([launcher, "--update", version, "-i", str(source), "-o", str(staging), "-e", export_argument], timeout)
        if not result["ok"]:
            return {**base, **result, "status": "error"}
        generated = [path for path in staging.glob("*.json" if data_format == 'json' else '*.skel')
                     if path != settings_path]
        if not generated:
            return {**base, "ok": False, "status": "error", "reason": "missing_export", "message": f"Spine 未產生重新匯出的 {data_format} 資料。"}
        paths: list[str] = []
        for item in generated:
            target = destination / item.name
            os.replace(item, target)
            paths.append(str(target))
        return {**base, "ok": True, "status": "success", "data_format": data_format,
                "json_paths" if data_format == 'json' else "binary_paths": paths,
                "file_paths": paths, "message": f"已完成原生專案的 {data_format} 重新匯出。"}


def export_binary(project_path, output_dir, executable=None, version=TARGET_VERSION,
                  *, target_version=None, timeout=120):
    """Export unrounded native data for version-matched runtime verification."""
    return export_runtime(project_path, output_dir, executable, version,
        target_version=target_version, data_format='binary', timeout=timeout)
