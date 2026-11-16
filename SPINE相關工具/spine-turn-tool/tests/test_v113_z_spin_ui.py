"""UI/project contracts for an independent full in-plane revolution."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
import main
from spine_turn_core import TurnOptions
from spine_turn_project import save_project, load_project
from test_v16_ui_project import app_without_display, Value


class InPlaneSpinUIContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'spin.spturn'
        self.sources = {'front': ROOT / 'assets/demo-octagon.png', 'back': None, 'edge': None}

    def opened_app(self, path):
        app = app_without_display()
        with patch.object(main.filedialog, 'askopenfilename', return_value=str(path)), \
                patch.object(main.messagebox, 'showerror') as error:
            app.open_project()
        error.assert_not_called()
        self.addCleanup(lambda: app._loaded_project.close() if app._loaded_project else None)
        return app

    def test_spin_options_open_edit_save_and_reopen_without_changing_primary_motion(self):
        options = TurnOptions(name='spin', axis='x', duration=2.4, z_spin_enabled=True,
                              z_spin_direction='counterclockwise', z_spin_start=.2, z_spin_end=.85,
                              bounce_enabled=True, z_bounce_enabled=True, z_bounce_depth=120)
        save_project(self.path, self.sources, options, {'playing': False, 'progress': .35})
        app = self.opened_app(self.path)
        self.assertEqual(app.z_spin_direction.get(), '逆時針')
        self.assertEqual(app.axis.get(), '上下翻轉 · X 軸')
        self.assertTrue(app.z_spin_enabled.get())
        self.assertEqual((app.z_spin_start.get(), app.z_spin_end.get()), (.2, .85))
        app.z_spin_direction.set('順時針')
        with patch.object(main.messagebox, 'showerror') as error:
            app.save_project()
        error.assert_not_called()
        saved = load_project(self.path)
        self.addCleanup(saved.close)
        self.assertTrue(saved.options.z_spin_enabled)
        self.assertEqual(saved.options.z_spin_direction, 'clockwise')
        self.assertEqual((saved.options.z_spin_start, saved.options.z_spin_end), (.2, .85))
        self.assertEqual((saved.options.axis, saved.options.bounce_enabled, saved.options.z_bounce_enabled),
                         ('x', True, True))
        self.assertEqual(saved.ui_state['progress'], .35)

    def test_existing_public_project_uses_disabled_spin_defaults(self):
        app = self.opened_app(ROOT / 'examples/irregular-v1.10/irregular.spturn')
        self.assertFalse(app.z_spin_enabled.get())
        self.assertEqual(app.z_spin_direction.get(), '順時針')
        self.assertEqual((app.z_spin_start.get(), app.z_spin_end.get()), (0, 1))
        self.assertFalse(app.get_options().z_spin_enabled)

    def test_seconds_convert_to_clip_fractions_and_failure_does_not_partially_change_them(self):
        app = main.App.__new__(main.App)
        app.z_spin_start, app.z_spin_end = Value(.1), Value(.9)
        app.update_z_spin_display = lambda: None
        app.set_z_spin_times(.6, 1.8, 2.4)
        self.assertAlmostEqual(app.z_spin_start.get(), .25)
        self.assertAlmostEqual(app.z_spin_end.get(), .75)
        before = app.z_spin_start.get(), app.z_spin_end.get()
        for start, end, duration in ((1, 1, 2), (2, 1, 2), (-1, 1, 2), (0, 3, 2), (0, 1, 0), (0, float('nan'), 2)):
            with self.subTest(start=start, end=end, duration=duration), self.assertRaises(ValueError):
                app.set_z_spin_times(start, end, duration)
            self.assertEqual((app.z_spin_start.get(), app.z_spin_end.get()), before)

    def test_summary_uses_half_clip_seconds_without_rewriting_timing(self):
        save_project(self.path, self.sources, TurnOptions(z_spin_enabled=True, z_spin_start=.25, z_spin_end=.75))
        app = self.opened_app(self.path)
        app.update_z_spin_display()
        self.assertIn('0.50–1.50 秒', app.z_spin_summary.get())
        app.animation.set('正面 → 背面')
        app.update_z_spin_display()
        self.assertIn('0.25–0.75 秒', app.z_spin_summary.get())
        self.assertEqual((app.z_spin_start.get(), app.z_spin_end.get()), (.25, .75))
        app.z_spin_direction.set('沒有這個方向')
        with self.assertRaisesRegex(ValueError, '順時針或逆時針'):
            app.get_options()


if __name__ == '__main__':
    unittest.main()
