"""Preview shortcuts distinguish Tk Windows NumLock from Alt modifiers."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from test_v111_ui_actions import Harness, Widget, Window


class WindowsShortcutTests(unittest.TestCase):
    def app(self, backend='win32'):
        app = Harness()
        app.root.tk = SimpleNamespace(call=Mock(return_value=backend))
        return app

    @staticmethod
    def event(app, key, state, widget=None):
        return SimpleNamespace(keysym=key, widget=widget or app.preview, state=state)

    def test_windows_numlock_and_other_lock_states_do_not_block_transport(self):
        for state in (0x8, 0x8 | 0x2, 0x8 | 0x20, 0x8 | 0x2 | 0x20):
            with self.subTest(state=state):
                app = self.app()
                options = app.options
                self.assertEqual(app.handle_preview_key(self.event(app, 'space', state)), 'break')
                self.assertFalse(app.playing)
                self.assertEqual(app.handle_preview_key(self.event(app, 'Right', state)), 'break')
                self.assertAlmostEqual(app.progress, .25 + 1 / 60)
                self.assertEqual(app.handle_preview_key(self.event(app, 'Home', state)), 'break')
                self.assertEqual(app.progress, 0)
                self.assertEqual(app.handle_preview_key(self.event(app, 'End', state)), 'break')
                self.assertEqual(app.progress, 1)
                self.assertIs(app.options, options)

    def test_windows_numlock_does_not_block_f8_from_input_or_buttons(self):
        for kind in ('Canvas', 'TEntry', 'TButton', 'TCombobox'):
            with self.subTest(kind=kind):
                app = self.app()
                app.root.focus = control = Widget(app.root, kind)
                result = app.handle_preview_key(self.event(app, 'F8', 0x8, control))
                self.assertEqual(result, 'break')
                app._workspace.toggle_focus.assert_called_once_with()

    def test_windows_ctrl_alt_and_existing_meta_guard_remain_blocked(self):
        for state in (0x4, 0x4 | 0x8, 0x20000, 0x20000 | 0x8, 0x80 | 0x8):
            for key in ('space', 'Right', 'F8'):
                with self.subTest(state=state, key=key):
                    app = self.app()
                    self.assertIsNone(app.handle_preview_key(self.event(app, key, state)))
                    self.assertEqual((app.progress, app.playing), (.25, True))
                    app._workspace.toggle_focus.assert_not_called()

    def test_numlock_does_not_bypass_text_input_or_modal_guards(self):
        app = self.app()
        app.root.focus = entry = Widget(app.root, 'TEntry')
        self.assertIsNone(app.handle_preview_key(self.event(app, 'space', 0x8, entry)))
        self.assertIsNone(app.handle_preview_key(self.event(app, 'Right', 0x8, entry)))
        app.root.grab = Widget(app.root, 'Frame')
        self.assertIsNone(app.handle_preview_key(self.event(app, 'F8', 0x8)))
        app.root.grab = None
        app.root.focus = Widget(Window(), 'Canvas')
        self.assertIsNone(app.handle_preview_key(self.event(app, 'F8', 0x8)))
        self.assertEqual((app.progress, app.playing), (.25, True))
        app._workspace.toggle_focus.assert_not_called()

    def test_other_tk_backends_keep_mod1_alt_guard(self):
        for backend in ('x11', 'aqua'):
            app = self.app(backend)
            self.assertIsNone(app.handle_preview_key(self.event(app, 'F8', 0x8)))
            app._workspace.toggle_focus.assert_not_called()
            self.assertEqual(app.handle_preview_key(self.event(app, 'F8', 0)), 'break')
            app._workspace.toggle_focus.assert_called_once_with()


if __name__ == '__main__':
    unittest.main(verbosity=2)
