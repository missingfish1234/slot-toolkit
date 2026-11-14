"""Project-open/save integration without creating a Tk window or touching user art."""
from dataclasses import asdict
import inspect
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import main
from spine_turn_core import TurnOptions, normalize_options, prepare_images, resolve_options
from spine_turn_project import save_project, load_project


class Value:
    def __init__(self, value=None):
        self.value = value
        self.set_calls = []

    def get(self):
        return self.value

    def set(self, value):
        self.set_calls.append(value)
        self.value = value


def app_without_display():
    app = main.App.__new__(main.App)
    names = re.findall(r'self\.(\w+) = tk\.(?:StringVar|DoubleVar|IntVar|BooleanVar)',
        inspect.getsource(main.App.__init__))
    for name in names:
        setattr(app, name, Value('previous-value'))
    app.root = SimpleNamespace(after_cancel=Mock(), title=Mock(), destroy=Mock())
    app.paths = {'front': 'previous-front.png', 'back': None, 'edge': None}
    app.project_path = 'previous.spturn'
    app.extra_options = TurnOptions(name='previous')
    app._loaded_project = None
    app._loading_project = False
    app._rebuild_job = None
    app.busy = False
    app.native = None
    app.progress = .2
    app.playing = False
    app.prepared = object()
    app.raised_contour_points = ()
    app.diamond_guides = {}
    app.play_button = Mock()
    app.slider = Value()
    app.set_image = Mock(side_effect=lambda kind, path: app.paths.__setitem__(kind, path) or True)
    app.clear_image = Mock(side_effect=lambda kind: app.paths.__setitem__(kind, None))
    app.update_profile_controls = Mock()
    app.update_model_controls = Mock()
    app.update_diamond_summary = Mock()
    app.update_target_display = Mock()
    app.update_project_title = Mock()
    app.draw = Mock()

    def rebuild():
        options = app.get_options()
        prepared = prepare_images(app.paths['front'], app.paths['back'], app.paths['edge'], options)
        app.options = resolve_options(prepared, options)
        app.prepared = prepared
    app.rebuild = Mock(side_effect=rebuild)
    return app


class UIProjectIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.sources = {'front': ROOT / 'assets' / 'demo-octagon.png', 'back': None, 'edge': None}

    def test_core_valid_but_ui_unsupported_project_is_rejected_before_any_mutation(self):
        filename = self.folder / 'duration40.spturn'
        save_project(filename, self.sources, TurnOptions(duration=40))
        app = app_without_display()
        app._rebuild_job = 'previous-scheduled-rebuild'
        previous = SimpleNamespace(close=Mock(), ui_state={})
        app._loaded_project = previous
        old_paths = dict(app.paths)
        old_prepared = app.prepared
        created = []

        def capture_load(path):
            result = load_project(path)
            created.append(result)
            return result
        with patch('main.filedialog.askopenfilename', return_value=str(filename)), \
             patch('main.load_editable_project', side_effect=capture_load), \
             patch('main.messagebox.showerror') as show_error:
            app.open_project()
        self.assertEqual(len(created), 1)
        self.assertTrue(created[0].closed)
        self.assertFalse(Path(created[0].workspace_dir).exists())
        self.assertIs(app._loaded_project, previous)
        self.assertIs(app.prepared, old_prepared)
        self.assertEqual(app.paths, old_paths)
        self.assertEqual(app.project_path, 'previous.spturn')
        self.assertEqual(app._rebuild_job, 'previous-scheduled-rebuild')
        self.assertFalse(app._loading_project)
        self.assertFalse(any(value.set_calls for value in vars(app).values() if isinstance(value, Value)))
        app.set_image.assert_not_called()
        app.clear_image.assert_not_called()
        app.root.after_cancel.assert_not_called()
        previous.close.assert_not_called()
        app.rebuild.assert_not_called()
        self.assertIn('超出目前介面範圍', show_error.call_args.args[1])

    def full_project(self):
        options = TurnOptions(name='full-handshake', width=256, height=384,
            trim_transparent=False, edge_color='#123456', key_step_degrees=7.5,
            shape='polygon', side_mode='ridge', spine_version='4.2.17',
            raised_contour_points=((-0.2, -.2), (.25, -.2), (.1, .25)),
            bevel_depth=.2, base_scale=1.1, duration=2.4,
            bounce_enabled=True, peak_scale=1.15, z_bounce_enabled=True,
            z_bounce_depth=120, camera_distance=1200,
            bounce_start=.15, bounce_apex=.35, bounce_land=.65, bounce_end=.85,
            z_bounce_start=.2, z_bounce_apex=.4, z_bounce_end=.7)
        ui = {'animation': 'flip_to_front', 'background': 'dark', 'preview_zoom': 125,
            'show_ground': False, 'native_export': True, 'progress': .37, 'playing': False,
            'future_panel_hint': {'panel': 'depth', 'kept': True}}
        filename = self.folder / 'full.spturn'
        save_project(filename, self.sources, options, ui)
        loaded = load_project(filename)
        self.addCleanup(loaded.close)
        return filename, loaded, options, ui

    def test_full_supported_open_and_ctrl_s_preserve_hidden_options_patch_ui_and_asset_lifetime(self):
        filename, loaded, options, ui = self.full_project()
        old_archive = self.folder / 'old.spturn'
        save_project(old_archive, self.sources, TurnOptions())
        previous = load_project(old_archive)
        self.addCleanup(previous.close)
        previous_workspace = Path(previous.workspace_dir)
        app = app_without_display()
        app._loaded_project = previous
        actual_rebuild = app.rebuild.side_effect
        old_workspace_during_rebuild = []
        def rebuilding():
            old_workspace_during_rebuild.append(previous_workspace.exists())
            actual_rebuild()
        app.rebuild.side_effect = rebuilding
        app.apply_loaded_project(loaded, filename)
        self.assertEqual(old_workspace_during_rebuild, [True])
        self.assertFalse(previous_workspace.exists())
        self.assertTrue(Path(loaded.workspace_dir).exists())
        self.assertEqual(asdict(app.get_options()), asdict(normalize_options(options)))
        self.assertEqual(app.selected_target_version(), '4.2.17')
        self.assertEqual(app.project_ui_state(), ui)
        self.assertAlmostEqual(app.angle, 180 + .37 * 180)
        self.assertAlmostEqual(app.slider.get(), .37 * 360)
        with patch('main.filedialog.asksaveasfilename') as picker, \
             patch('main.messagebox.showerror') as show_error:
            app.save_project()
        picker.assert_not_called()
        show_error.assert_not_called()
        with load_project(filename) as saved:
            self.assertEqual(asdict(saved.options), asdict(normalize_options(options)))
            self.assertEqual(saved.options.spine_version, '4.2.17')
            self.assertEqual(saved.ui_state, ui)
        app.spine_version.set('3.8')
        self.assertEqual(app.selected_target_version(), '3.8.99')

    def test_demo_discards_association_and_cancelled_save_does_not_overwrite_original(self):
        filename, loaded, _, _ = self.full_project()
        app = app_without_display()
        app.apply_loaded_project(loaded, filename)
        previous_bytes = filename.read_bytes()
        old_workspace = Path(loaded.workspace_dir)
        app.load_demo('z')
        self.assertIsNone(app._loaded_project)
        self.assertIsNone(app.project_path)
        self.assertFalse(old_workspace.exists())
        self.assertEqual(app.extra_options, TurnOptions())
        self.assertTrue(all(Path(path).is_file() for path in app.paths.values()))
        with patch('main.filedialog.asksaveasfilename', return_value='') as picker, \
             patch('main.messagebox.showerror') as show_error:
            app.save_project()
        picker.assert_called_once()
        show_error.assert_not_called()
        self.assertEqual(filename.read_bytes(), previous_bytes)

    def test_diamond_open_save_roundtrip_preserves_guides_fx_and_inactive_badge_settings(self):
        filename = self.folder / 'diamond.spturn'
        options = TurnOptions(name='diamond-ui', model='diamond', spine_version='4.2.17',
            width=256, height=384, trim_transparent=False, key_step_degrees=7.5,
            edge_color='#123456', shape='polygon', side_mode='ridge',
            raised_contour_points=((-0.45, -.45), (.45, -.45), (0, .45)),
            bevel_width=.1, bevel_depth=.3, thickness=39,
            diamond_facets=12, diamond_center_x=.02, diamond_table_y=.39,
            diamond_waist_y=.04, diamond_tip_y=-.46, diamond_table_width=.4,
            diamond_waist_width=.9, diamond_girdle_height=.025,
            diamond_view_tilt=18, diamond_shading=.76,
            diamond_shine_enabled=False, diamond_shine_strength=.43,
            diamond_sparkles_enabled=True, diamond_sparkle_strength=.81,
            diamond_cut_regions=((((-.4, .15), (0., .15), (0., .4)), -24., 12.),
                (((0., .15), (.4, .15), (0., .4)), 28., -15.)))
        ui = {'animation': 'rotate_loop', 'background': 'dark', 'preview_zoom': 125,
            'show_ground': False, 'native_export': True, 'progress': .23, 'playing': False}
        save_project(filename, {'front': ROOT / 'assets' / 'demo-diamond.png',
            'back': None, 'edge': None}, options, ui)
        loaded = load_project(filename)
        self.addCleanup(loaded.close)
        app = app_without_display()
        app.apply_loaded_project(loaded, filename)
        self.assertEqual(app.model_choice.get(), '鑽石')
        self.assertEqual(asdict(app.get_options()), asdict(normalize_options(options)))
        self.assertEqual(app.project_ui_state(), ui)
        self.assertTrue(app.ridge_mode.get())
        self.assertEqual(app.raised_contour_points, options.raised_contour_points)
        with patch('main.messagebox.showerror') as show_error:
            app.save_project()
        show_error.assert_not_called()
        with load_project(filename) as saved:
            self.assertEqual(asdict(saved.options), asdict(normalize_options(options)))
        app.model_choice.set('一般物件')
        inactive = app.get_options()
        self.assertEqual(inactive.model, 'extrusion')
        self.assertEqual(inactive.side_mode, 'ridge')
        self.assertEqual(inactive.raised_contour_points, options.raised_contour_points)
        self.assertEqual(inactive.diamond_table_y, options.diamond_table_y)
        self.assertEqual(inactive.diamond_cut_regions, options.diamond_cut_regions)


if __name__ == '__main__':
    unittest.main(verbosity=2)
