from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from toolkit_manager.git_ops import commit_tool_paths, git_output, git_run, git_tool_update_paths, parse_status
from toolkit_manager.indexer import scan_tools
from toolkit_manager.models import AppConfig, ToolInfo, ToolIndex
from toolkit_manager.services import GitHubClient, StateStore, ToolLibrary, download_file, extract_tool_from_archive, file_digest, select_manager_asset
from toolkit_manager.storage import atomic_json, recover_json


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="toolkit-regression-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write(self, name, content="data"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def tool(self, **kwargs):
        return ToolInfo(id="sample", name="範例", category="測試工具", version="1.2.0", entry="run.html", **kwargs)

    def package(self, tool, extra=None):
        path = self.root / f"payload-{tool.version}.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("tool.json", json.dumps(tool.to_dict()))
            archive.writestr("run.html", "new runtime")
            for name, content in (extra or {}).items():
                archive.writestr(name, content)
        return path


class StorageTests(Fixture):
    def test_recover_corrupt_primary_from_backup(self):
        path = self.root / "state.json"
        atomic_json(path, {"a": 1})
        atomic_json(path, {"a": 2})
        path.write_text("{broken", encoding="utf-8")
        with self.assertWarns(RuntimeWarning):
            self.assertEqual(recover_json(path, {}), {"a": 1})
        self.assertTrue(list(self.root.glob("*.corrupt-*")))
        self.assertEqual(json.loads(path.read_text()), {"a": 1})

    def test_wrong_structure_does_not_crash_state(self):
        self.write("state.json", '{"installed": "bad"}')
        with self.assertWarns(RuntimeWarning):
            self.assertEqual(StateStore(self.root).load_installed(), {})

    def test_missing_primary_still_recovers_backup(self):
        self.write("state.json.bak", '{"installed":[{"id":"saved", "version":"1.0.0", "path":"somewhere"}]}')
        with self.assertWarns(RuntimeWarning):
            installed = StateStore(self.root).load_installed()
        self.assertIn("saved", installed)
        self.assertTrue((self.root / "state.json").is_file())

    def test_failed_atomic_replace_preserves_original(self):
        path = self.write("config.json", '{"a":1}')
        with patch("toolkit_manager.storage.os.replace", side_effect=OSError("locked")):
            with self.assertRaises(OSError):
                atomic_json(path, {"a": 2})
        self.assertEqual(json.loads(path.read_text()), {"a": 1})
        self.assertFalse(list(self.root.glob("*.tmp")))

    def test_invalid_interval_is_bounded(self):
        self.assertEqual(AppConfig.from_dict({"auto_check_minutes": "broken"}).auto_check_minutes, 30)
        self.assertEqual(AppConfig.from_dict({"auto_check_minutes": -3}).auto_check_minutes, 1)

    def test_invalid_index_is_rejected(self):
        for value in ([], {}, {"tools": [None]}, {"tools": [{"id": "a"}, {"id": "a"}]}):
            with self.assertRaises(ValueError):
                ToolIndex.from_dict(value)


class DownloadTests(Fixture):
    def client(self):
        config = AppConfig(install_root=str(self.root / "installed"))
        client = GitHubClient(config, cache_dir=self.root / "cache")
        client._auth_token = ""
        return client

    def test_update_preserves_custom_files_and_complete_backup(self):
        tool = self.tool(download_url="https://example.test/tool.zip")
        package = self.package(tool, {"config.json": "new default"})
        client = self.client()
        self.write("installed/sample/run.html", "old program")
        self.write("installed/sample/config.json", "my config")
        self.write("installed/sample/outputs/我的圖.png", "my image")
        destination = client.config.install_path / tool.id
        with patch.object(client, "cached_package", return_value=package):
            client.download_tool(tool, destination)
        self.assertEqual((destination / "run.html").read_text(), "new runtime")
        self.assertEqual((destination / "config.json").read_text(), "my config")
        self.assertEqual((destination / "outputs/我的圖.png").read_text(), "my image")
        backups = list(destination.parent.glob("sample.backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "run.html").read_text(), "old program")

    def test_obsolete_distribution_removed_but_edited_copy_preserved(self):
        tool = self.tool(download_url="https://example.test/tool.zip")
        client = self.client()
        old = self.write("installed/sample/obsolete.js", "old")
        edited = self.write("installed/sample/custom.js", "changed")
        atomic_json(old.parent / ".toolkit-managed.json", {"id": tool.id, "files": {"obsolete.js": file_digest(old), "custom.js": "not-current-hash"}})
        with patch.object(client, "cached_package", return_value=self.package(tool)):
            client.download_tool(tool, old.parent)
        self.assertFalse(old.exists())
        self.assertEqual(edited.read_text(), "changed")

    def test_invalid_payload_keeps_old_install(self):
        tool = self.tool(download_url="https://example.test/tool.zip")
        package = self.package(self.tool())
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("run.html", "broken missing metadata")
        client = self.client()
        old = self.write("installed/sample/run.html", "old")
        with patch.object(client, "cached_package", return_value=package):
            with self.assertRaises(RuntimeError):
                client.download_tool(tool, old.parent)
        self.assertEqual(old.read_text(), "old")

    def test_promotion_failure_restores_old_install(self):
        tool = self.tool(download_url="https://example.test/tool.zip")
        client = self.client()
        old = self.write("installed/sample/run.html", "old")
        original_rename = Path.rename
        def rename(path, target):
            if path.name.startswith(".sample.download-"):
                raise OSError("simulate locked destination")
            return original_rename(path, target)
        with patch.object(client, "cached_package", return_value=self.package(tool)), patch.object(Path, "rename", rename):
            with self.assertRaises(OSError):
                client.download_tool(tool, old.parent)
        self.assertEqual(old.read_text(), "old")
        self.assertFalse(list(old.parent.parent.glob("sample.backup-*")))

    def test_extract_rejects_traversal_and_absolute_paths(self):
        for malicious in ("../escape", "nested/../../escape", "C:/escape", "/escape"):
            package = self.root / "unsafe.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr(malicious, "bad")
            with self.assertRaises(RuntimeError):
                extract_tool_from_archive(package, "", self.root / "safe")

    def test_cache_avoids_repeated_archive_download(self):
        client = self.client()
        client.index_fingerprint = "same-index"
        source = self.package(self.tool())
        def fake_download(url, target, *args, **kwargs):
            target.write_bytes(source.read_bytes())
        with patch("toolkit_manager.services.download_file", side_effect=fake_download) as mocked:
            first = client.cached_package(self.tool())
            second = client.cached_package(ToolInfo("second", "另一個", "測試工具"))
        self.assertEqual(first, second)
        self.assertEqual(mocked.call_count, 1)

    def test_checksum_failure_does_not_keep_cache(self):
        client = self.client()
        tool = self.tool(download_url="https://example.test/tool.zip", sha256="0" * 64)
        with patch("toolkit_manager.services.download_file", side_effect=lambda url, target, *a, **kw: target.write_bytes(b"broken")):
            with self.assertRaisesRegex(RuntimeError, "SHA-256"):
                client.cached_package(tool)
        self.assertFalse(list(client.cache_dir.glob("*.zip")))

    def test_bad_tool_id_rejected(self):
        client = self.client()
        library = ToolLibrary(client.config, StateStore(self.root / "state"))
        for tool_id in ("../escape", "C:/escape", "", "a/b", "."):
            with self.assertRaises(RuntimeError):
                library.install_path_for(ToolInfo(tool_id, "bad", "test"))

    def test_manager_asset_does_not_pick_unrelated_zip(self):
        self.assertIsNone(select_manager_asset([{"name": "other.zip", "browser_download_url": "https://example.test"}]))

    def test_interrupted_download_preserves_existing_zip(self):
        target = self.write("download.zip", "previous")
        class Response:
            headers = {"Content-Length": "100"}
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, size): return b""
        with patch("urllib.request.urlopen", return_value=Response()):
            with self.assertRaises(RuntimeError):
                download_file("https://example.test", target)
        self.assertEqual(target.read_text(), "previous")
        self.assertFalse(list(self.root.glob("*.part")))


class IndexTests(Fixture):
    def meta(self, folder, tool_id):
        self.write(folder + "/tool.json", json.dumps(ToolInfo(tool_id, tool_id, "test").to_dict()))

    def test_readme_category_and_nested_registered_tool(self):
        self.write("分類/README.md", "category description")
        self.meta("分類/工具", "parent")
        self.write("分類/工具/run.html")
        self.meta("分類/工具/Extension", "extension")
        self.write("分類/工具/Extension/run.html")
        self.write("分類/工具/vendor/unwanted.html")
        self.assertEqual({t.id for t in scan_tools(self.root).tools}, {"parent", "extension"})

    def test_invalid_metadata_is_not_silently_replaced(self):
        original = self.write("分類/工具/tool.json", "broken json")
        with self.assertRaises(ValueError):
            scan_tools(self.root)
        self.assertEqual(original.read_text(), "broken json")

    def test_duplicate_ids_rejected(self):
        self.meta("分類/A", "same")
        self.meta("分類/B", "same")
        with self.assertRaises(ValueError): scan_tools(self.root)

    def test_nonlaunchable_resource_stays_without_entry(self):
        self.meta("分類/Shader", "shader")
        self.write("分類/Shader/Editor/example.cs")
        self.write("分類/Shader/tests/test_x.py")
        self.assertEqual(scan_tools(self.root).tools[0].entry, "")


class GitTests(Fixture):
    def test_scoped_commit_preserves_unrelated_staging_and_unicode_rename(self):
        git_run(self.root, ["init"])
        git_run(self.root, ["config", "user.name", "Regression Test"])
        git_run(self.root, ["config", "user.email", "test@example.invalid"])
        old = self.write("分類/工具/old.txt", "old")
        unrelated = self.write("manager/config.txt", "old")
        git_run(self.root, ["add", "."])
        git_run(self.root, ["commit", "-m", "baseline"])
        unrelated.write_text("staged unrelated", encoding="utf-8")
        git_run(self.root, ["add", "manager/config.txt"])
        git_run(self.root, ["mv", old.relative_to(self.root).as_posix(), "分類/工具/new → 中文 ! [x].txt"])
        self.write("分類/工具/空 白.txt", "new")
        status = git_output(self.root, ["status", "--porcelain=v1", "-z", "--untracked-files=all"])
        paths = git_tool_update_paths(self.root, status)
        self.assertIn("分類/工具/old.txt", paths)
        self.assertIn("分類/工具/new → 中文 ! [x].txt", paths)
        self.assertNotIn("manager/config.txt", paths)
        commit_tool_paths(self.root, paths, "tool-only")
        self.assertEqual(git_output(self.root, ["diff", "--cached", "--name-only"]).strip(), "manager/config.txt")
        self.assertNotIn("manager/config.txt", git_output(self.root, ["show", "--format=", "--name-only", "HEAD"]))

    def test_non_z_status_rejected(self):
        with self.assertRaises(ValueError): parse_status("not porcelain")


@unittest.skipUnless(os.name == "nt", "Windows updater")
class UpdaterTests(Fixture):
    def prepare(self):
        source = self.write("source ! % & 中文/ToolkitManager.exe", "new exe").parent
        target = self.write("installed ! % & 中文/ToolkitManager.exe", "old exe").parent
        self.write(target.relative_to(self.root).as_posix() + "/config.json", "my config")
        self.write(source.relative_to(self.root).as_posix() + "/config.json", "default config")
        atomic_json(source / "release-manifest.json", {"files": {p.name: file_digest(p) for p in source.iterdir() if p.is_file()}})
        request = self.root / "request.json"
        atomic_json(request, {"source_dir": str(source), "target_dir": str(target), "parent_pid": 0, "no_launch": True})
        return source, target, request

    def run_updater(self, request):
        script = Path(__file__).resolve().parents[1] / "apply_update.ps1"
        return subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-RequestPath", str(request)], capture_output=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def test_transactional_update_with_special_character_paths(self):
        source, target, request = self.prepare()
        result = self.run_updater(request)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        self.assertEqual((target / "ToolkitManager.exe").read_text(), "new exe")
        self.assertEqual((target / "config.json").read_text(), "my config")
        backups = list(self.root.glob("*.backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "ToolkitManager.exe").read_text(), "old exe")

    def test_checksum_failure_leaves_install_unchanged(self):
        source, target, request = self.prepare()
        (source / "ToolkitManager.exe").write_text("corrupt")
        self.assertNotEqual(self.run_updater(request).returncode, 0)
        self.assertEqual((target / "ToolkitManager.exe").read_text(), "old exe")
        self.assertFalse(list(self.root.glob("*.backup-*")))


if __name__ == "__main__":
    unittest.main()
