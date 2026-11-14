"""Workflow checks for asset transactions and preview transport, without Tk."""
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spine_turn_ui_actions import StudioActions


class Value:
    def __init__(self, value=None):
        self.value = value
        self.on_set = None

    def get(self):
        return self.value

    def set(self, value):
        self.value = value
        if self.on_set:
            self.on_set(value)


class Widget:
    def __init__(self, root=None, kind='Canvas', **configuration):
        self.root, self.kind, self.configuration = root, kind, configuration

    def winfo_toplevel(self):
        return self.root or self

    def winfo_class(self):
        return self.kind

    def cget(self, name):
        return self.configuration.get(name)

    def configure(self, **values):
        self.configuration.update(values)


class Window(Widget):
    def __init__(self):
        super().__init__(kind='Tk')
        self.focus, self.grab = None, None

    def focus_get(self):
        return self.focus

    def grab_current(self):
        return self.grab


class Harness(StudioActions):
    def __init__(self):
        self.root = Window()
        self.preview = Widget(self.root)
        self.root.focus = self.preview
        self.status = Value()
        self.options = SimpleNamespace(duration=2.)
        self.animation = Value('rotate_loop')
        self.progress, self.angle, self.playing = .25, 90., True
        self.last_tick, self._preview_revision = 0., 4
        self.slider = Value(90.)
        self.angle_input, self.time_readout = Value('90'), Value()
        self.angle_entry = Widget(self.root, 'TEntry')
        self.play_button = Widget(self.root, 'TButton')
        self.draw = Mock()
        self.rebuild = Mock()
        self._workspace = SimpleNamespace(toggle_focus=Mock())
        self.busy = False
        self.paths = dict(front='old-front', back='old-back', edge='old-edge')
        self.extra_options = object()
        self.prepared = object()
        self.raised_contour_points = ((-.2, -.2), (.2, -.2), (0, .2))
        self.diamond_guides = {'tip': -.4}
        self.region_summary, self.diamond_summary = Value('manual-region'), Value('aligned')
        self.thumbs = dict(front='front-thumbnail', back='back-thumbnail')
        self.cards = {role: (Widget(image=role, text='', height=78), Widget(text=f'{role}.png'))
                      for role in ('front', 'back', 'edge')}
        self.clear_image = Mock(side_effect=lambda role: self.paths.__setitem__(role, None))
        self.set_image = Mock(side_effect=self.put_image)

    def put_image(self, role, path):
        self.paths[role] = str(path)
        self.thumbs[role] = f'new-{role}'
        self.cards[role][0].configure(image=f'new-{role}', height=78)
        self.cards[role][1].configure(text=Path(path).name)
        if role == 'front':
            self.extra_options = object()
            self.raised_contour_points = ()
            self.region_summary.set('automatic')
            self.diamond_summary.set('new-art')
        return True

    def clip_duration(self):
        return self.options.duration if self.animation.get() in ('rotate_loop', '整圈旋轉') else self.options.duration / 2

    def angle_at_progress(self):
        start, end = {'rotate_loop': (0, 360), '整圈旋轉': (0, 360),
                      'flip_to_back': (0, 180), '正面 → 背面': (0, 180),
                      'flip_to_front': (180, 360), '背面 → 正面': (180, 360)}[self.animation.get()]
        return start + (end - start) * self.progress

    def toggle_play(self):
        self.playing = not self.playing


class AssetActionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.front, self.back = self.folder / 'front 前.png', self.folder / 'back 後.png'
        Image.new('RGBA', (12, 10), (200, 60, 20, 255)).save(self.front)
        Image.new('RGBA', (14, 11), (20, 60, 200, 255)).save(self.back)
        self.app = Harness()
        self.app.paths.update(front=str(self.front), back=str(self.back))

    def test_remove_only_the_requested_role_and_rebuild_once(self):
        before = dict(self.app.paths)
        self.assertTrue(self.app.remove_asset('back'))
        self.assertEqual(self.app.paths, {**before, 'back': None})
        self.app.clear_image.assert_called_once_with('back')
        self.app.rebuild.assert_called_once_with()

    def test_busy_asset_actions_do_not_mutate_or_decode_anything(self):
        self.app.busy = True
        before = dict(self.app.paths)
        with patch('spine_turn_ui_actions.Image.open') as decode:
            self.assertFalse(self.app.remove_asset('front'))
            self.assertFalse(self.app.swap_faces())
        decode.assert_not_called()
        self.assertEqual(self.app.paths, before)
        self.app.clear_image.assert_not_called()
        self.app.set_image.assert_not_called()
        self.app.rebuild.assert_not_called()

    def test_swap_validates_both_images_before_touching_first_asset(self):
        invalid = self.folder / 'bad.png'
        invalid.write_bytes(b'not an image')
        self.app.paths['back'] = str(invalid)
        before, options, region = dict(self.app.paths), self.app.extra_options, self.app.raised_contour_points
        self.assertFalse(self.app.swap_faces())
        self.assertEqual(self.app.paths, before)
        self.assertIs(self.app.extra_options, options)
        self.assertEqual(self.app.raised_contour_points, region)
        self.app.set_image.assert_not_called()
        self.app.rebuild.assert_not_called()
        self.assertTrue(self.app.status.get())

    def test_missing_or_completely_transparent_second_asset_cannot_half_swap(self):
        transparent = self.folder / 'empty.png'
        Image.new('RGBA', (12, 10)).save(transparent)
        for path in (None, str(transparent), str(self.folder / 'missing.png')):
            with self.subTest(path=path):
                self.app.paths['back'] = path
                before = dict(self.app.paths)
                self.assertFalse(self.app.swap_faces())
                self.assertEqual(self.app.paths, before)
                self.app.set_image.assert_not_called()

    def test_success_delegates_each_replacement_and_preserves_edge_source(self):
        old_options = self.app.extra_options
        self.assertTrue(self.app.swap_faces())
        self.assertEqual(self.app.paths, dict(front=str(self.back), back=str(self.front), edge='old-edge'))
        self.assertEqual(self.app.set_image.call_args_list[0].args, ('front', str(self.back)))
        self.assertEqual(self.app.set_image.call_args_list[1].args, ('back', str(self.front)))
        self.assertEqual(self.app.raised_contour_points, ())
        self.assertIsNot(self.app.extra_options, old_options)
        self.app.rebuild.assert_called_once_with()

    def test_second_load_failure_rolls_back_paths_derived_state_and_thumbnails(self):
        paths_object, before = self.app.paths, dict(self.app.paths)
        original = (self.app.extra_options, self.app.options, self.app.prepared,
                    self.app.raised_contour_points, dict(self.app.thumbs))
        def put(role, path):
            self.app.put_image(role, path)
            return role == 'front'
        self.app.set_image.side_effect = put
        self.assertFalse(self.app.swap_faces())
        self.assertIs(self.app.paths, paths_object)
        self.assertEqual(self.app.paths, before)
        self.assertIs(self.app.extra_options, original[0])
        self.assertIs(self.app.options, original[1])
        self.assertIs(self.app.prepared, original[2])
        self.assertEqual(self.app.raised_contour_points, original[3])
        self.assertEqual(self.app.thumbs, original[4])
        self.assertEqual(self.app.region_summary.get(), 'manual-region')
        self.assertEqual(self.app.diamond_summary.get(), 'aligned')
        self.assertEqual(self.app.cards['front'][0].cget('image'), 'front')
        self.assertEqual(self.app.cards['back'][1].cget('text'), 'back.png')
        self.app.rebuild.assert_not_called()


class TransportTests(unittest.TestCase):
    def test_busy_transport_does_not_pause_seek_or_inspect_settings(self):
        app = Harness()
        app.busy = True
        app.angle_input.set('270')
        before = (app.playing, app.progress, app.angle, app.last_tick,
                  app._preview_revision, app.slider.get(), app.angle_input.get())
        app.clip_duration = Mock(side_effect=AssertionError('Busy action inspected settings.'))
        for operation in (app.begin_angle_edit, lambda: app.seek_progress(.8),
                          lambda: app.step_preview(1), app.apply_angle):
            self.assertFalse(operation())
            self.assertEqual((app.playing, app.progress, app.angle, app.last_tick,
                              app._preview_revision, app.slider.get(), app.angle_input.get()), before)
        app.clip_duration.assert_not_called()
        app.draw.assert_not_called()

    def test_seek_clamps_pauses_and_publishes_progress_before_slider_echo(self):
        app = Harness()
        observed = []
        app.slider.on_set = lambda value: observed.append(app.progress)
        with patch('spine_turn_ui_actions.time.perf_counter', return_value=123.):
            self.assertTrue(app.seek_progress(4))
        self.assertEqual((app.progress, app.angle, app.playing, app.last_tick), (1, 360, False, 123))
        self.assertEqual(app._preview_revision, 5)
        self.assertEqual(observed, [1])
        self.assertEqual(app.slider.get(), 360)
        app.draw.assert_called_once_with()
        app.seek_progress(-2)
        self.assertEqual((app.progress, app.angle), (0, 0))

    def test_frame_step_uses_real_half_clip_duration_and_configured_fps(self):
        app = Harness()
        app.progress = 0
        app.step_preview(1)
        self.assertAlmostEqual(app.progress, 1 / 60)
        app.animation.set('flip_to_back')
        app.progress = 0
        app.step_preview(1)
        self.assertAlmostEqual(app.progress, 1 / 30)
        self.assertAlmostEqual(app.angle, 6)
        app.options.fps = 12
        app.animation.set('flip_to_front')
        app.progress = .5
        app.step_preview(-1)
        self.assertAlmostEqual(app.progress, .5 - 1 / 12)
        self.assertAlmostEqual(app.angle, 255)

    def test_apply_angle_maps_all_clips_and_rejects_values_outside_clip(self):
        app = Harness()
        for clip, angle, progress in (('整圈旋轉', 270, .75), ('正面 → 背面', 90, .5),
                                      ('背面 → 正面', 270, .5), ('背面 → 正面', 360, 1)):
            app.animation.set(clip)
            app.angle_input.set(str(angle))
            self.assertTrue(app.apply_angle())
            self.assertAlmostEqual(app.progress, progress)
            self.assertAlmostEqual(app.angle, angle)
        before = (app.progress, app.angle, app._preview_revision)
        for value in ('179.9', '361', 'NaN', 'text'):
            app.angle_input.set(value)
            self.assertFalse(app.apply_angle())
            self.assertEqual((app.progress, app.angle, app._preview_revision), before)
        self.assertTrue(app.status.get())

    def test_invalid_seek_or_frame_rate_preserves_current_pose(self):
        app = Harness()
        before = (app.progress, app.angle, app.playing)
        self.assertFalse(app.seek_progress(float('nan')))
        app.options.fps = 0
        self.assertFalse(app.step_preview(1))
        self.assertEqual((app.progress, app.angle, app.playing), before)
        app.draw.assert_not_called()

    def test_angle_focus_pauses_and_does_not_overwrite_unfinished_entry(self):
        app = Harness()
        app.animation.set('flip_to_back')
        app.angle_input.set('12.')
        app.root.focus = app.angle_entry
        app.begin_angle_edit()
        app.sync_transport()
        self.assertFalse(app.playing)
        self.assertEqual(app.angle_input.get(), '12.')
        seconds = [float(value) for value in re.findall(r'\d+\.\d+', app.time_readout.get())]
        self.assertEqual(seconds, [.25, 1.])
        app.root.focus = app.preview
        app.sync_transport()
        self.assertEqual(float(app.angle_input.get()), 45)
        self.assertIsNone(StudioActions.sync_transport(SimpleNamespace()))

    def test_unchanged_transport_sync_does_not_retrigger_variable_traces(self):
        app = Harness()
        app.angle_input.on_set, app.time_readout.on_set = Mock(), Mock()
        app.sync_transport()
        app.angle_input.on_set.reset_mock()
        app.time_readout.on_set.reset_mock()
        for _ in range(100):
            app.sync_transport()
        app.angle_input.on_set.assert_not_called()
        app.time_readout.on_set.assert_not_called()
        app.progress = .5
        app.sync_transport()
        app.angle_input.on_set.assert_called_once()
        app.time_readout.on_set.assert_called_once()
        self.assertEqual(float(app.angle_input.get()), 180)


class KeyboardTests(unittest.TestCase):
    def event(self, app, key, widget=None, state=0):
        return SimpleNamespace(keysym=key, widget=widget or app.preview, state=state)

    def test_canvas_shortcuts_control_time_and_workspace_without_touching_options(self):
        app = Harness()
        options = app.options
        self.assertEqual(app.handle_preview_key(self.event(app, 'space')), 'break')
        self.assertFalse(app.playing)
        self.assertEqual(app.handle_preview_key(self.event(app, 'Home')), 'break')
        self.assertEqual(app.progress, 0)
        app.handle_preview_key(self.event(app, 'Right'))
        self.assertAlmostEqual(app.progress, 1 / 60)
        app.handle_preview_key(self.event(app, 'Left'))
        self.assertAlmostEqual(app.progress, 0)
        app.handle_preview_key(self.event(app, 'End'))
        self.assertEqual(app.progress, 1)
        self.assertEqual(app.handle_preview_key(self.event(app, 'F8')), 'break')
        app._workspace.toggle_focus.assert_called_once_with()
        self.assertIs(app.options, options)

    def test_typing_and_native_control_navigation_are_not_captured(self):
        app = Harness()
        before = (app.progress, app.playing)
        for kind in ('Entry', 'TEntry', 'Spinbox', 'TSpinbox', 'Combobox', 'TCombobox',
                     'Text', 'Button', 'TButton', 'TCheckbutton', 'TRadiobutton', 'Scale', 'TScale', 'TNotebook'):
            app.root.focus = control = Widget(app.root, kind)
            for key in ('space', 'Left', 'Right', 'Home', 'End'):
                with self.subTest(kind=kind, key=key):
                    self.assertIsNone(app.handle_preview_key(self.event(app, key, control)))
                    self.assertEqual((app.progress, app.playing), before)
        app.draw.assert_not_called()
        app._workspace.toggle_focus.assert_not_called()

    def test_f8_exits_focus_mode_even_when_its_button_or_text_field_has_focus(self):
        app = Harness()
        state = {'focused': False}
        app._workspace.toggle_focus.side_effect = lambda: state.update(focused=not state['focused'])
        for kind in ('TButton', 'TEntry', 'TCombobox', 'TScale'):
            app.root.focus = control = Widget(app.root, kind)
            self.assertEqual(app.handle_preview_key(self.event(app, 'F8', control)), 'break')
            self.assertTrue(state['focused'])
            self.assertEqual(app.handle_preview_key(self.event(app, 'F8', control)), 'break')
            self.assertFalse(state['focused'])
        self.assertEqual((app.progress, app.playing), (.25, True))

    def test_modal_grabs_and_other_toplevels_never_seek_background_preview(self):
        app = Harness()
        original = app.progress
        app.root.grab = Widget(app.root, 'Frame')
        for key in ('End', 'F8'):
            self.assertIsNone(app.handle_preview_key(self.event(app, key)))
        app.root.grab = None
        modal = Window()
        app.root.focus = Widget(modal, 'Canvas')
        for key in ('End', 'F8'):
            self.assertIsNone(app.handle_preview_key(self.event(app, key)))
        self.assertEqual(app.progress, original)
        app.draw.assert_not_called()
        app._workspace.toggle_focus.assert_not_called()

    def test_modified_and_unrelated_keys_are_left_for_other_handlers(self):
        app = Harness()
        for key, state in (('Right', 4), ('space', 8), ('F8', 4), ('F8', 8), ('x', 0)):
            self.assertIsNone(app.handle_preview_key(self.event(app, key, state=state)))
        app.draw.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
