import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication
from toolkit_manager.app import AdminDialog, MainWindow, extract_update_zip, find_update_source_dir
from toolkit_manager.models import AppConfig, ToolIndex, ToolInfo
from toolkit_manager.storage import atomic_json


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="toolkit-ui-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = AppConfig(auto_check_on_start=False, install_root=str(self.root / "tools"))
        self.index = ToolIndex("2026-09-05", [ToolInfo("test", "測試工具", "PS內插件", kind="Photoshop 插件")])
        atomic_json(self.root / "tools-index.json", self.index.to_dict())
        for name, value in (("toolkit_manager.app.app_data_dir", self.root), ("toolkit_manager.app.local_index_path", self.root / "tools-index.json"), ("toolkit_manager.app.ConfigStore.load", self.config)):
            mocked = patch(name, return_value=value)
            mocked.start()
            self.addCleanup(mocked.stop)
        self.window = MainWindow()
        self.window.manager_update_checked = True
        self.addCleanup(self.window.close)

    def test_window_and_resource_details_render(self):
        self.assertEqual(len(self.window.tools), 1)
        self.window.select_tool(self.window.tools[0])
        self.assertEqual(self.window.selected_tool.id, "test")

    def test_index_cache_saved_and_corrupt_source_falls_back(self):
        self.window.apply_remote_index(self.index)
        self.assertTrue(self.window.index_cache_path().is_file())
        (self.root / "tools-index.json").write_text("broken", encoding="utf-8")
        self.window.load_local_index()
        self.assertEqual(len(self.window.tools), 1)

    def test_worker_finishes_and_releases_thread(self):
        values = []
        self.window.start_worker(lambda progress: "done", values.append)
        deadline = time.monotonic() + 5
        while self.window.worker_thread is not None and time.monotonic() < deadline:
            self.application.processEvents()
            time.sleep(0.005)
        self.assertIsNone(self.window.worker_thread)
        self.assertEqual(values, ["done"])

    def test_admin_lifecycle(self):
        dialog = AdminDialog(self.window, self.config, self.window.config_store)
        self.assertIsNone(dialog.git_worker_thread)
        dialog.reject()


if __name__ == "__main__": unittest.main()
