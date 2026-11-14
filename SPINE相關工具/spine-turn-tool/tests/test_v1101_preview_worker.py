"""UI responsiveness, stale-work rejection, real playback time and version guidance."""
import threading
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
import main
from spine_turn_core import TurnOptions
from spine_turn_preview_worker import LatestPreviewWorker, PreviewResult
from test_v16_ui_project import Value


def wait_result(worker):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if result := worker.take_result():
            return result
        threading.Event().wait(.002)
    raise AssertionError('Preview worker did not return its result.')


class PreviewWorkerTests(unittest.TestCase):
    def test_slow_render_does_not_block_and_pending_work_is_bounded_to_latest(self):
        entered, release = threading.Event(), threading.Event()
        rendered = []
        def render(value):
            rendered.append(value)
            if value == 1:
                entered.set()
                release.wait(2)
            return value * 10
        worker = LatestPreviewWorker(render)
        try:
            worker.submit(('old',), 1, (1,), {})
            self.assertTrue(entered.wait(1))
            started = time.monotonic()
            for value in range(2, 31):
                worker.submit(('new',), value, (value,), {})
            self.assertLess(time.monotonic() - started, .1)
            self.assertIsNone(worker.take_result())
            release.set()
            result = wait_result(worker)
            if result.angle == 1:
                result = wait_result(worker)
            self.assertEqual((result.view_key, result.angle, result.image), (('new',), 30, 300))
            self.assertEqual(rendered, [1, 30])
        finally:
            release.set()
            worker.close()
            worker._thread.join(1)

    def test_errors_are_reported_and_next_request_still_renders(self):
        worker = LatestPreviewWorker(lambda value: 10 / value)
        try:
            worker.submit(('a',), 0, (0,), {})
            self.assertIn('zero', wait_result(worker).error)
            worker.submit(('a',), 2, (2,), {})
            self.assertEqual(wait_result(worker).image, 5)
        finally:
            worker.close()
            worker._thread.join(1)

    def test_close_discards_inflight_result_without_waiting_for_renderer(self):
        entered, release = threading.Event(), threading.Event()
        def render():
            entered.set()
            release.wait(2)
            return 'old'
        worker = LatestPreviewWorker(render)
        worker.submit(('a',), 0, (), {})
        self.assertTrue(entered.wait(1))
        started = time.monotonic()
        worker.close()
        self.assertLess(time.monotonic() - started, .1)
        release.set()
        worker._thread.join(1)
        self.assertIsNone(worker.take_result())
        self.assertFalse(worker._thread.is_alive())


class PreviewUIIntegrationTests(unittest.TestCase):
    def app(self):
        app = main.App.__new__(main.App)
        app._loading_project = app._closed = False
        app.prepared, app.options = object(), TurnOptions()
        app.angle, app.progress = 90., .25
        app.playing = False
        app.preview_zoom, app.background = Value(100), Value('checker')
        app.animation, app.show_ground = Value('整圈旋轉'), Value(False)
        app.preview = SimpleNamespace(winfo_width=lambda: 720, winfo_height=lambda: 600,
            create_image=Mock(return_value=4), itemconfigure=Mock(), delete=Mock(), create_text=Mock())
        app._preview_worker = Mock()
        app._preview_worker.submit.return_value = 5
        app._preview_presented_id = 0
        app._preview_revision = 7
        app.angle_text, app.status = Mock(), Value()
        app.root = SimpleNamespace(after=Mock(return_value='next'))
        return app

    def test_draw_only_submits_full_resolution_snapshot_on_ui_thread(self):
        app = self.app()
        with patch('main.render_pose') as render, patch('main.ImageTk.PhotoImage') as photo:
            app.draw()
        render.assert_not_called()
        photo.assert_not_called()
        args = app._preview_worker.submit.call_args.args
        self.assertEqual(args[2][3], (720, 600))
        self.assertEqual(args[3]['progress'], .25)
        self.assertEqual(app._preview_request_id, 5)

    def test_config_changes_and_paused_scrubs_reject_stale_images(self):
        app = self.app()
        app.draw()
        key = app._preview_view_key
        for result in (PreviewResult(4, key, 45, image='old'),
                       PreviewResult(5, ('different-art',), 90, image='wrong')):
            app._preview_worker.take_result.return_value = result
            with patch('main.ImageTk.PhotoImage') as photo:
                app._poll_preview()
                photo.assert_not_called()
        app._preview_worker.take_result.return_value = PreviewResult(5, key, 90, image='final')
        with patch('main.ImageTk.PhotoImage', return_value='tk-final') as photo:
            app._poll_preview()
            photo.assert_called_once_with('final')
        self.assertEqual(app.frame_photo, 'tk-final')
        self.assertEqual(app._preview_presented_id, 5)

    def test_playback_presents_completed_valid_frames_even_when_newer_time_is_pending(self):
        app = self.app()
        app.playing = True
        app.draw()
        app._preview_worker.take_result.return_value = PreviewResult(4, app._preview_view_key, 80, image='frame')
        with patch('main.ImageTk.PhotoImage', return_value='tk') as photo:
            app._poll_preview()
            photo.assert_called_once_with('frame')

    def test_clock_uses_elapsed_time_instead_of_slow_frame_cap(self):
        app = self.app()
        app.playing, app.busy = True, False
        app.progress, app.last_tick = .2, 10
        app.slider, app.draw = Value(), Mock()
        with patch('main.time.perf_counter', side_effect=(10.6, 10.601)):
            app.tick()
        self.assertAlmostEqual(app.progress, .5)
        self.assertAlmostEqual(app.angle, 180)
        app.draw.assert_called_once()

    def test_native_success_names_exact_required_editor_and_writes_guidance(self):
        app = main.App.__new__(main.App)
        app.export_button, app.sequence_button = Mock(), Mock()
        app.status = Value()
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / 'symbol.spine').write_bytes(b'fixture')
            with patch('main.messagebox.showinfo') as message, patch('main.os.startfile', create=True):
                app.export_done(folder, {}, {'ok': True}, '4.2.43')
            title, text = message.call_args.args
            self.assertIn('4.2.43', title)
            self.assertIn('請用 Spine 4.2.43', text)
            self.assertIn('跨版本匯入 JSON', text)
            self.assertEqual((folder / '開啟前請看.txt').read_text(encoding='utf-8'), text + '\n')


if __name__ == '__main__':
    unittest.main(verbosity=2)
