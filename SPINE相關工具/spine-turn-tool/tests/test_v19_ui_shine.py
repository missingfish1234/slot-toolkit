"""Coin-shine controls survive editable saves and timing changes in seconds."""
from dataclasses import asdict, replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from main import App
from test_v16_ui_project import app_without_display, Value
from test_v11_ui_options import app_without_window
from spine_turn_core import TurnOptions, normalize_options
from spine_turn_project import save_project, load_project


class ShineUIIntegrationTests(unittest.TestCase):
    def test_controls_use_percent_units_and_keep_independent_timing(self):
        app = app_without_window(coin_shine_enabled=True, coin_shine_strength=68,
            coin_shine_width=32, coin_shine_angle=-40, coin_shine_repeat=3,
            coin_shine_start=.2, coin_shine_end=.7)
        options = app.get_options()
        self.assertEqual((options.coin_shine_enabled, options.coin_shine_strength,
            options.coin_shine_width, options.coin_shine_angle, options.coin_shine_repeat),
            (True, .68, .32, -40, 3))
        self.assertEqual((options.coin_shine_start, options.coin_shine_end), (.2, .7))
        self.assertEqual((options.bounce_start, options.z_bounce_start), (.08, .08))

    def test_seconds_convert_to_each_clip_ratio_without_changing_motion(self):
        app = App.__new__(App)
        app.coin_shine_start, app.coin_shine_end, app.coin_shine_repeat = Value(.1), Value(.85), Value(1)
        app.set_coin_shine_times(.4, 1.4, 2, 2)
        self.assertEqual((app.coin_shine_start.get(), app.coin_shine_end.get(), app.coin_shine_repeat.get()), (.2, .7, 2))
        app.set_coin_shine_times(.2, .7, 2, 1)
        self.assertEqual((app.coin_shine_start.get(), app.coin_shine_end.get(), app.coin_shine_repeat.get()), (.2, .7, 2))
        before = (app.coin_shine_start.get(), app.coin_shine_end.get(), app.coin_shine_repeat.get())
        for values in ((.7,.2,2,1), (0,2,1,1), (0,1,1.5,1), (float('nan'),1,1,2)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                app.set_coin_shine_times(*values)
            self.assertEqual((app.coin_shine_start.get(), app.coin_shine_end.get(), app.coin_shine_repeat.get()), before)

    def test_incomplete_or_out_of_range_controls_are_rejected(self):
        for changes in ({'coin_shine_width': 0}, {'coin_shine_strength': 101},
                        {'coin_shine_repeat': 2.5}, {'coin_shine_start': .8, 'coin_shine_end': .3}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                app_without_window(**changes).get_options()

    def test_open_save_retains_all_shine_options_and_inactive_diamond_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            filename = Path(temporary)/'coin-shine.spturn'
            options = TurnOptions(name='coin-shine', coin_shine_enabled=True,
                coin_shine_strength=.68, coin_shine_width=.32, coin_shine_angle=-40,
                coin_shine_start=.2, coin_shine_end=.7, coin_shine_repeat=3,
                diamond_ring_phase=22.5, diamond_view_tilt=24,
                bounce_enabled=False, z_bounce_enabled=True, z_bounce_depth=100)
            save_project(filename, {'front': ROOT/'assets/demo-front.png',
                'back': ROOT/'assets/demo-back.png', 'edge': ROOT/'assets/demo-edge.png'}, options,
                {'animation':'flip_to_back','progress':.3,'playing':False})
            with load_project(filename) as loaded:
                app = app_without_display()
                app.apply_loaded_project(loaded, filename)
                self.assertEqual(asdict(app.get_options()), asdict(normalize_options(options)))
                with patch('main.messagebox.showerror') as errors:
                    app.save_project()
                errors.assert_not_called()
                with load_project(filename) as saved:
                    self.assertEqual(asdict(saved.options), asdict(normalize_options(options)))
                    self.assertEqual(saved.options.diamond_ring_phase, 22.5)
                    self.assertFalse(saved.ui_state['playing'])

    def test_demo_enables_front_sweep_and_ordinary_y_demo_resets_it(self):
        app = app_without_display()
        with tempfile.TemporaryDirectory() as temporary:
            filename = Path(temporary)/'initial.spturn'
            save_project(filename, {'front': ROOT/'assets/demo-front.png',
                'back': None, 'edge': None}, TurnOptions())
            with load_project(filename) as loaded:
                app.apply_loaded_project(loaded, filename)
                app.load_demo('shine')
        self.assertTrue(app.get_options().coin_shine_enabled)
        self.assertEqual((app.get_options().coin_shine_start, app.get_options().coin_shine_end), (0,.25))
        self.assertFalse(app.get_options().bounce_enabled)
        self.assertFalse(app.get_options().z_bounce_enabled)
        app.load_demo('y')
        self.assertFalse(app.get_options().coin_shine_enabled)
        self.assertTrue(app.get_options().bounce_enabled)


if __name__ == '__main__':
    unittest.main(verbosity=2)
