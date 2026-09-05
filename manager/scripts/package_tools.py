"""Build per-tool, checksum-addressed release assets from an immutable Git commit.

Run after the implementation commit is complete. This script never publishes or
changes tool metadata: generated index/ZIPs are placed only in --output.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from toolkit_manager.models import ToolIndex
from toolkit_manager.indexer import format_size
from toolkit_manager.services import file_digest, validate_tool_payload, extract_tool_from_archive
from toolkit_manager.storage import atomic_json
import tempfile


def include_file(relative: str, tool, registered_children: list[str]) -> bool:
    parts = PurePosixPath(relative).parts
    if any(part.casefold() in {".git", ".venv", "__pycache__", "build", "backups", "old", "舊版", "舊版本"} for part in parts):
        return False
    if any(relative.startswith(child + "/") for child in registered_children):
        return False
    if re.search(r"(?:^|/)spine-director-cocos38-v[^/]+/", relative):
        return False
    # Old distributable bundles remain in Git history, not the current install.
    if parts[-1].lower().endswith((".zip", ".ccx")) and re.search(r"(?:v|_)(\d+\.\d+\.\d+)", parts[-1]):
        match = re.search(r"(?:v|_)(\d+\.\d+\.\d+)", parts[-1])
        if relative == tool.entry:
            return True
        if match.group(1) != tool.version:
            return False
    if tool.category.startswith("PS內插件") and relative == "PSDExportManager.exe" and tool.entry != relative:
        return False  # Legacy bootstrapper embeds the obsolete CCX.
    if tool.category.startswith("PS內插件") and re.fullmatch(r"Install_PSDExportPipeline_\d+\.\d+\.\d+\.cmd", relative) and relative != tool.entry:
        return False
    return True


def package(root: Path, revision: str, output: Path, tag: str, repository: str) -> dict:
    revision = subprocess.check_output(["git", "rev-parse", "--verify", revision + "^{commit}"], cwd=root, text=True).strip()
    source_index = subprocess.check_output(["git", "show", f"{revision}:tools-index.json"], cwd=root)
    index = ToolIndex.from_dict(json.loads(source_index))
    index.source_revision = revision
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for tool in index.tools:
        archive_bytes = subprocess.check_output(["git", "archive", "--format=zip", revision, "--", tool.path], cwd=root)
        children = [other.path[len(tool.path) + 1:] for other in index.tools if other.path.startswith(tool.path + "/")]
        filename = f"tool-{tool.id}-{tool.version}.zip"
        target = output / filename
        count = 0
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as source, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as destination:
            prefix = tool.path.rstrip("/") + "/"
            for info in source.infolist():
                if info.is_dir() or not info.filename.startswith(prefix):
                    continue
                relative = info.filename[len(prefix):]
                if not include_file(relative, tool, children):
                    continue
                result = zipfile.ZipInfo(relative, date_time=info.date_time)
                result.compress_type = zipfile.ZIP_DEFLATED
                result.external_attr = 0o100644 << 16
                destination.writestr(result, source.read(info))
                count += 1
        with tempfile.TemporaryDirectory(prefix="toolkit-package-verify-") as temporary:
            extract_tool_from_archive(target, "", Path(temporary))
            validate_tool_payload(tool, Path(temporary))
        tool.download_url = f"https://github.com/{repository}/releases/download/{tag}/{filename}"
        tool.sha256 = file_digest(target)
        tool.size = format_size(target.stat().st_size) + "（下載）"
        results.append({"id": tool.id, "name": tool.name, "asset": filename, "files": count, "bytes": target.stat().st_size, "sha256": tool.sha256})
        print(f"OK {tool.id}: {count} files, {target.stat().st_size} bytes", flush=True)
    atomic_json(output / "tools-index.json", index.to_dict(), backup=False)
    manifest = {"sourceRevision": revision, "tag": tag, "tools": results}
    atomic_json(output / "packages-manifest.json", manifest, backup=False)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--repository", default="missingfish1234/slot-toolkit")
    args = parser.parse_args()
    package(Path(__file__).resolve().parents[2], args.revision, args.output.resolve(), args.tag, args.repository)
