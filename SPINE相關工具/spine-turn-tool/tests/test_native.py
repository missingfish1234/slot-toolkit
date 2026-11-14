"""Safety and error-path checks for the optional native editor bridge."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import spine_native


class NativeAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.source = self.directory / "輸入 coin.json"
        self.source.write_text(json.dumps({"skeleton": {"spine": "4.0.56"}}), encoding="utf-8")
        self.launcher = self.directory / "Spine.com"
        self.launcher.write_bytes(b"placeholder")
        self.output = self.directory / "硬幣.spine"

    def tearDown(self):
        self.temporary.cleanup()

    def test_success_imports_into_nonexistent_sibling_then_replaces(self):
        def run(command, timeout):
            staging = Path(command[command.index("-o") + 1])
            self.assertEqual(staging.parent, self.output.parent)
            self.assertFalse(staging.exists())
            self.assertIn(str(self.source), command)
            self.assertEqual(command[command.index("--update") + 1], "4.0.56")
            staging.write_bytes(b"native-spine-project")
            return {"ok": True, "returncode": 0}
        with patch.object(spine_native, "_run", side_effect=run):
            result = spine_native.convert_project(self.source, self.output, self.launcher)
        self.assertTrue(result["ok"])
        self.assertEqual(self.output.read_bytes(), b"native-spine-project")
        self.assertEqual(list(self.directory.glob(".spine-import-*")), [])

    def test_existing_project_is_protected(self):
        self.output.write_bytes(b"artist-edited-project")
        with patch.object(spine_native, "_run") as run:
            result = spine_native.convert_project(self.source, self.output, self.launcher)
        run.assert_not_called()
        self.assertEqual(result["reason"], "output_exists")
        self.assertEqual(self.output.read_bytes(), b"artist-edited-project")

    def test_failed_overwrite_preserves_existing_project(self):
        self.output.write_bytes(b"artist-edited-project")
        with patch.object(spine_native, "_run", return_value={"ok": False, "reason": "test", "message": "failed"}):
            result = spine_native.convert_project(self.source, self.output, self.launcher, overwrite=True)
        self.assertFalse(result["ok"])
        self.assertEqual(self.output.read_bytes(), b"artist-edited-project")
        self.assertEqual(list(self.directory.glob(".spine-import-*")), [])

    def test_claimed_success_without_native_file_is_failure(self):
        with patch.object(spine_native, "_run", return_value={"ok": True, "returncode": 0}):
            result = spine_native.convert_project(self.source, self.output, self.launcher)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "missing_project")
        self.assertFalse(self.output.exists())

    def test_wrong_json_version_is_rejected_before_launch(self):
        self.source.write_text('{"skeleton":{"spine":"4.2.18"}}', encoding="utf-8")
        with patch.object(spine_native, "_run") as run:
            result = spine_native.convert_project(self.source, self.output, self.launcher)
        run.assert_not_called()
        self.assertEqual(result["reason"], "version_mismatch")

    def test_missing_installation_returns_importable_fallback(self):
        with patch.object(spine_native, "discover_spine", return_value=None):
            result = spine_native.convert_project(self.source, self.output)
        self.assertEqual(result["status"], "unavailable")
        self.assertTrue(self.source.exists())
        self.assertFalse(self.output.exists())

    def test_cli_output_never_leaks_license_identity(self):
        completed = subprocess.CompletedProcess([], 1, stdout=b"Licensed to PRIVATE PERSON private@example.com", stderr=b"bad input")
        with patch.object(spine_native.subprocess, "run", return_value=completed) as run:
            result = spine_native._run([str(self.launcher), "argument with spaces"], 5)
        rendered = json.dumps(result)
        self.assertNotIn("PRIVATE", rendered)
        self.assertNotIn("private@example.com", rendered)
        self.assertIs(run.call_args.kwargs["shell"], False)

    def test_timeout_is_reported_without_partial_project(self):
        with patch.object(spine_native.subprocess, "run", side_effect=subprocess.TimeoutExpired([], 1)):
            result = spine_native.convert_project(self.source, self.output, self.launcher, timeout=1)
        self.assertEqual(result["reason"], "timeout")
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
