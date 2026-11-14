"""Check displayed control values reach the exporter in the correct units."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from main import App
from spine_turn_core import TurnOptions


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def app_without_window(**overrides):
    values = dict(name='ui_export', thickness=26, duration=2.4, segments=24,
        axis='左右翻轉 · Y 軸', shape='圓形／橢圓硬幣', edge_orientation='橫向長條',
        base_scale=110, bounce_enabled=True, bounce_height=125, peak_scale=135,
        landing_squash=18, shade_faces=True, min_brightness=35, shade_curve=1.7,
        light_angle=-30, shade_edge=False, z_scale=125, peak_z_scale=160,
        z_bounce_enabled=False, z_bounce_depth=150, z_offset=-50, camera_distance=1200,
        bounce_start=.08, bounce_apex=.4, bounce_land=.8, bounce_end=1,
        z_bounce_start=.08, z_bounce_apex=.4, z_bounce_end=.8,
        bevel_width=0, bevel_depth=25, spine_version='4.0')
    values.update(overrides)
    app = App.__new__(App)
    extras = values.pop('extra_options', None)
    for name, value in values.items():
        setattr(app, name, Value(value))
    if extras is not None:
        app.extra_options = extras
    return app


class UIExportOptionsTests(unittest.TestCase):
    def test_target_family_selection_uses_pinned_schema_revision(self):
        for family, exact in {'3.8': '3.8.99', '4.0': '4.0.56', '4.2': '4.2.43'}.items():
            self.assertEqual(app_without_window(spine_version=family).get_options().spine_version, exact)

    def test_project_settings_without_visible_controls_are_preserved(self):
        extra = TurnOptions(width=256, height=384, trim_transparent=False,
            edge_color='#123456', key_step_degrees=7.5)
        options = app_without_window(extra_options=extra).get_options()
        self.assertEqual(options.width, 256)
        self.assertEqual(options.height, 384)
        self.assertFalse(options.trim_transparent)
        self.assertEqual(options.edge_color, '#123456')
        self.assertEqual(options.key_step_degrees, 7.5)

    def test_percent_controls_and_toggles_reach_exporter_in_correct_units(self):
        options = app_without_window().get_options()
        self.assertAlmostEqual(options.base_scale, 1.1)
        self.assertAlmostEqual(options.peak_scale, 1.35)
        self.assertAlmostEqual(options.landing_squash, .18)
        self.assertAlmostEqual(options.min_brightness, .35)
        self.assertEqual(options.bounce_height, 125)
        self.assertAlmostEqual(options.shade_curve, 1.7)
        self.assertEqual(options.light_angle, -30)
        self.assertEqual(options.thickness, 26)
        self.assertAlmostEqual(options.duration, 2.4)
        self.assertEqual(options.segments, 24)
        self.assertTrue(options.bounce_enabled)
        self.assertTrue(options.shade_faces)
        self.assertFalse(options.shade_edge)
        self.assertAlmostEqual(options.z_scale, 1.25)
        self.assertAlmostEqual(options.peak_z_scale, 1.6)
        self.assertFalse(options.z_bounce_enabled)
        self.assertEqual(options.z_bounce_depth, 150)
        self.assertEqual(options.z_offset, -50)
        self.assertEqual(options.camera_distance, 1200)

    def test_z_motion_can_be_enabled_without_vertical_bounce(self):
        options = app_without_window(bounce_enabled=False, z_bounce_enabled=True).get_options()
        self.assertFalse(options.bounce_enabled)
        self.assertTrue(options.z_bounce_enabled)

    def test_ridge_checkbox_selects_no_sideband_export_without_changing_stored_height(self):
        ridge = app_without_window(ridge_mode=True, bevel_depth=35).get_options()
        strip = app_without_window(ridge_mode=False, bevel_depth=35).get_options()
        self.assertEqual(ridge.side_mode, 'ridge')
        self.assertEqual(strip.side_mode, 'strip')
        self.assertAlmostEqual(ridge.bevel_depth, .35)
        self.assertAlmostEqual(strip.bevel_depth, .35)

    def test_orientation_and_axis_selection_preserve_intended_meaning(self):
        for label, value in [('橫向長條', 'horizontal'), ('直向長條', 'vertical'), ('自動依長寬判斷', 'auto')]:
            with self.subTest(label=label):
                self.assertEqual(app_without_window(edge_orientation=label).get_options().edge_orientation, value)
        self.assertEqual(app_without_window().get_options().axis, 'y')
        self.assertEqual(app_without_window(axis='上下翻轉 · X 軸').get_options().axis, 'x')
        self.assertEqual(app_without_window(shape='矩形／卡片').get_options().shape, 'rectangle')
        self.assertEqual(app_without_window(shape='依透明外框／凸多邊形').get_options().shape, 'polygon')

    def test_bevel_percentage_controls_reach_exporter_as_fractions(self):
        options = app_without_window(bevel_width=7, bevel_depth=25).get_options()
        self.assertAlmostEqual(options.bevel_width, .07)
        self.assertAlmostEqual(options.bevel_depth, .25)

    def test_independent_normalized_y_and_z_timings_reach_exporter(self):
        options = app_without_window(bounce_start=.3, bounce_apex=.5,
            bounce_land=.7, bounce_end=.85, z_bounce_start=.1,
            z_bounce_apex=.2, z_bounce_end=.45).get_options()
        for name, expected in {'bounce_start': .3, 'bounce_apex': .5,
            'bounce_land': .7, 'bounce_end': .85, 'z_bounce_start': .1,
            'z_bounce_apex': .2, 'z_bounce_end': .45}.items():
            self.assertAlmostEqual(getattr(options, name), expected)

    def test_nonfinite_numeric_values_report_named_chinese_control(self):
        for value in ['nan', float('inf'), 'not a number']:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, '最暗亮度'):
                    app_without_window(min_brightness=value).get_options()


if __name__ == '__main__':
    unittest.main(verbosity=2)
