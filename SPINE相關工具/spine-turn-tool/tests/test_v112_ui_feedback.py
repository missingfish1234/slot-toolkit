"""Real Tk interaction regressions; invisible own-process windows, no desktop input."""
from pathlib import Path
import sys
import tkinter as tk
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spine_turn_ui_style import PALETTE, StudioButton, FeedbackToast, attach_tooltip, configure_theme


class FeedbackInteractionTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.attributes('-alpha', 0)
        self.root.geometry('700x360-20000-20000')
        self.root.report_callback_exception = self.callback_error
        self.errors = []
        configure_theme(self.root)
        self.root.deiconify()
        self.calls = []
        self.button = StudioButton(self.root, text='測試動作', command=lambda: self.calls.append('original'))
        self.button.pack(padx=20, pady=20)
        self.flush()
        self.addCleanup(self.root.destroy)

    def callback_error(self, kind, value, tb):
        self.errors.append(f'{kind.__name__}: {value}')

    def flush(self):
        self.root.update_idletasks()
        self.root.update()
        self.assertEqual(self.errors, [])

    def event(self, sequence, **kwargs):
        self.button.event_generate(sequence, **kwargs)
        self.flush()

    def key(self, phase, keysym):
        # Windows suppresses generated key events for an inactive, offscreen
        # window. Exercise the registered handlers without taking desktop focus.
        self.assertTrue(self.button.bind(f'<Key{phase}-{keysym}>'))
        handler = self.button._on_key_press if phase == 'Press' else self.button._on_key_release
        self.assertEqual(handler(SimpleNamespace(keysym=keysym)), 'break')
        self.flush()

    def test_mouse_press_release_invokes_once_without_changing_bounds(self):
        bounds = self.button.winfo_width(), self.button.winfo_height()
        original = self.button.cget('background')
        self.event('<Enter>', x=4, y=4)
        hover = self.button.cget('background')
        self.event('<ButtonPress-1>', x=4, y=4)
        pressed = self.button.cget('background')
        self.assertNotEqual(hover, original)
        self.assertNotEqual(pressed, hover)
        self.assertEqual((self.button.winfo_width(), self.button.winfo_height()), bounds)
        self.event('<ButtonRelease-1>', x=4, y=4)
        self.assertEqual(self.calls, ['original'])
        self.assertEqual((self.button.winfo_width(), self.button.winfo_height()), bounds)

    def test_dragging_outside_before_release_cancels_click(self):
        self.event('<Enter>', x=4, y=4)
        self.event('<ButtonPress-1>', x=4, y=4)
        self.event('<Leave>', x=-2, y=-2)
        self.event('<ButtonRelease-1>', x=-2, y=-2)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.button._pressed)

    def test_disabling_during_press_blocks_release_and_programmatic_invoke(self):
        self.event('<Enter>', x=4, y=4)
        self.event('<ButtonPress-1>', x=4, y=4)
        self.button.configure(state='disabled')
        self.event('<ButtonRelease-1>', x=4, y=4)
        self.button.invoke()
        self.assertEqual(self.calls, [])
        self.assertFalse(self.button._pressed)
        self.button.configure(state='normal')
        self.button.invoke()
        self.assertEqual(self.calls, ['original'])

    def test_keyboard_return_and_space_activate_once_each_and_respect_disabled(self):
        self.key('Press', 'Return')
        self.key('Release', 'Return')
        self.assertEqual(self.calls, ['original'])
        self.key('Press', 'space')
        self.key('Release', 'space')
        self.assertEqual(self.calls, ['original', 'original'])
        self.button.configure(state='disabled')
        for key in ('Return', 'space'):
            self.key('Press', key)
            self.key('Release', key)
        self.assertEqual(self.calls, ['original', 'original'])

    def test_replacing_command_and_selection_keeps_button_contract(self):
        self.button.config(command=lambda: self.calls.append('replacement'), text='替換後')
        self.button.configure(selected=True)
        self.button.invoke()
        self.assertEqual(self.calls, ['replacement'])
        self.assertEqual(self.button.cget('text'), '替換後')
        selected = self.button.cget('background')
        self.button.set_selected(False)
        self.assertNotEqual(self.button.cget('background'), selected)
        self.button.config(state='disabled')
        self.button.invoke()
        self.assertEqual(self.calls, ['replacement'])

    def test_held_keyboard_press_invokes_once_and_focus_loss_cancels_it(self):
        self.key('Press', 'space')
        self.key('Press', 'space')
        self.key('Release', 'space')
        self.assertEqual(self.calls, ['original'])
        self.key('Press', 'Return')
        self.event('<FocusOut>')
        self.key('Release', 'Return')
        self.assertEqual(self.calls, ['original'])

    def test_tooltip_pending_job_is_cancelled_on_leave_and_destroy(self):
        tip = attach_tooltip(self.button, '操作說明', delay=10000)
        self.event('<Enter>', x=4, y=4)
        self.assertIsNotNone(tip._job)
        self.event('<Leave>', x=-2, y=-2)
        self.assertIsNone(tip._job)
        self.event('<Enter>', x=4, y=4)
        self.assertIsNotNone(tip._job)
        self.event('<ButtonPress-1>', x=4, y=4)
        self.assertIsNone(tip._job)
        self.event('<ButtonRelease-1>', x=4, y=4)
        self.event('<Enter>', x=4, y=4)
        self.assertIsNotNone(tip._job)
        self.button.destroy()
        self.flush()
        self.assertIsNone(tip._job)
        self.assertIsNone(tip._window)

    def test_idle_buttons_do_not_schedule_a_continuous_animation_loop(self):
        before = set(self.root.tk.call('after', 'info'))
        buttons = [StudioButton(self.root, text=str(index), command=lambda: None) for index in range(25)]
        for button in buttons:
            button.pack()
        self.flush()
        self.assertEqual(set(self.root.tk.call('after', 'info')), before)

    def test_replaced_and_destroyed_toasts_cancel_their_pending_dismissal(self):
        toast = FeedbackToast(self.root)
        toast.show('已儲存', duration=10000)
        first_job = toast._job
        toast.show('請檢查設定', kind='error', duration=10000)
        self.assertNotEqual(toast._job, first_job)
        self.assertNotIn(first_job, set(self.root.tk.call('after', 'info')))
        self.assertEqual(toast.label.cget('text'), '請檢查設定')
        toast.destroy()
        self.flush()
        self.assertIsNone(toast._job)

    def test_all_drawing_editor_factories_preserve_native_button_commands(self):
        from spine_turn_region_editor import _RegionEditor
        from spine_turn_diamond_editor import _DiamondEditor
        from spine_turn_diamond_cut_editor import _DiamondCutEditor
        from spine_turn_diamond_alignment_editor import _AlignmentEditor
        for editor_type in (_RegionEditor, _DiamondEditor, _DiamondCutEditor, _AlignmentEditor):
            with self.subTest(editor=editor_type.__name__):
                editor = editor_type.__new__(editor_type)
                calls = []
                button = editor.button(self.root, '套用', lambda: calls.append('apply'), primary=True)
                self.assertIsInstance(button, StudioButton)
                button.invoke()
                button.configure(state='disabled')
                button.invoke()
                self.assertEqual(calls, ['apply'])
                button.destroy()


if __name__ == '__main__':
    unittest.main(verbosity=2)
