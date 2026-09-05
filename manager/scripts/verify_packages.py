"""Exercise real release archives with the manager installer, in disposable folders."""
import argparse
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from toolkit_manager.models import AppConfig, ToolIndex
from toolkit_manager.services import GitHubClient, file_digest
from toolkit_manager.storage import atomic_json


def verify(directory: Path):
    index = ToolIndex.from_dict(json.loads((directory / "tools-index.json").read_text(encoding="utf-8")))
    results = []
    for tool in index.tools:
        package = directory / tool.download_url.rsplit("/", 1)[-1]
        if file_digest(package) != tool.sha256:
            raise RuntimeError("Checksum mismatch: " + tool.name)
        with tempfile.TemporaryDirectory(prefix="tkverify-") as temporary:
            root = Path(temporary)
            client = GitHubClient(AppConfig(install_root=str(root / "i")), cache_dir=root / "c")
            destination = client.config.install_path / tool.id
            with patch.object(client, "cached_package", return_value=package):
                client.download_tool(tool, destination)
                user_file = destination / "user-data" / "設定.txt"
                user_file.parent.mkdir(exist_ok=True)
                user_file.write_text("preserve-this-user-file", encoding="utf-8")
                client.download_tool(tool, destination)
            if user_file.read_text(encoding="utf-8") != "preserve-this-user-file":
                raise RuntimeError("User data missing: " + tool.name)
            backup = list(destination.parent.glob(tool.id + ".backup-*"))
            if len(backup) != 1:
                raise RuntimeError("Expected retained backup: " + tool.name)
            if tool.entry and not (destination / tool.entry).is_file():
                raise RuntimeError("Missing installed entry: " + tool.name)
        results.append({"id": tool.id, "version": tool.version, "checksum": True, "freshInstall": True, "updateRetainsUserData": True, "fullBackup": True})
        print("PASS " + tool.name, flush=True)
    report = {"count": len(results), "sourceRevision": index.source_revision, "results": results}
    atomic_json(directory / "install-verification.json", report, backup=False)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    verify(args.directory.resolve())
