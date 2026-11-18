"""Animation sets: several named animations with their own settings in one Spine file."""
from dataclasses import replace
from bisect import bisect_right
import json
from pathlib import Path
import sys
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
import main
import spine_turn_core as core
from spine_turn_core import (TurnOptions, animation_overrides, build_animation_set, build_package,
                             build_skeleton, normalize_animation_set, prepare_images, resolve_options)
from spine_turn_project import load_project, save_project
from test_v16_ui_project import app_without_display

ASSETS = ROOT / 'assets'
COIN = (ASSETS / 'demo-front.png', ASSETS / 'demo-back.png', ASSETS / 'demo-edge.png')
IRREGULAR = (ASSETS / 'demo-irregular-front.png', None, None)


def record(name, action, base=TurnOptions(), **changes):
    return {'name': name, 'action': action, 'options': animation_overrides(replace(base, **changes))}


class AnimationSetValidationTests(unittest.TestCase):
    def test_names_actions_and_settings_are_checked(self):
        good = normalize_animation_set([record(' spin ', 'rotate_loop'), ('Sway', 'swing_loop', {'swing_angle': 20})])
        self.assertEqual([(r['name'], r['action']) for r in good], [('spin', 'rotate_loop'), ('Sway', 'swing_loop')])
        for bad in ([], [record('a', 'rotate_loop'), record('A', 'swing_loop')],
                    [record('a/b', 'rotate_loop')], [record('a', 'moonwalk')],
                    [{'name': 'a', 'action': 'rotate_loop', 'options': {'thickness': 40}}],
                    [record(f'a{index}', 'rotate_loop') for index in range(core.MAX_ANIMATIONS + 1)]):
            with self.subTest(bad=str(bad)[:60]), self.assertRaises(ValueError):
                normalize_animation_set(bad)

    def test_old_option_sets_become_their_original_clips(self):
        legacy = core.legacy_animation_set(TurnOptions(swing_enabled=True, duration=3))
        self.assertEqual([(r['name'], r['action']) for r in legacy],
                         [('rotate_loop', 'rotate_loop'), ('flip_to_back', 'flip_to_back'),
                          ('flip_to_front', 'flip_to_front'), ('swing_loop', 'swing_loop')])
        self.assertTrue(all(r['options']['duration'] == 3 for r in legacy))

    def test_names_cannot_alias_png_subfolders_on_windows(self):
        for name in ('turn.', 'CON', 'con.txt', 'NUL', 'nul.png', 'AUX', 'PRN',
                     'COM1', 'LPT9', 'COM¹', 'LPT².txt', 'CON .txt', 'CONIN$', 'CONOUT$'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Windows'):
                normalize_animation_set([record(name, 'rotate_loop')])
        with self.assertRaisesRegex(ValueError, 'Windows'):
            normalize_animation_set([record('turn', 'rotate_loop'), record('turn.', 'swing_loop')])

    def test_portable_existing_animation_names_are_preserved(self):
        names = ('搖擺', '旋轉 1', 'nod_copy', 'turn.v2', 'CONtour', 'COM0', 'COM10', 'LPT0')
        self.assertEqual([entry['name'] for entry in normalize_animation_set(
            [record(name, 'rotate_loop') for name in names])], list(names))


class AnimationSetBuildTests(unittest.TestCase):
    def test_42_native_frame_roundtrip_keeps_exact_draw_order_boundaries(self):
        # Actual 4.2 editor behavior: frames are multiplied by a Float32
        # reciprocal FPS before binary times are written. At 30 FPS an exact
        # .75-second key moves to .7500000596 and selects the preceding order.
        f32 = lambda value: struct.unpack('f', struct.pack('f', value))[0]
        native_time = lambda time, fps: f32(f32(time * fps) * f32(1 / fps))
        self.assertGreater(native_time(.75, 30), f32(.75))
        base = TurnOptions(spine_version='4.2.43', shape='irregular', duration=1.5)
        images = prepare_images(*IRREGULAR, base)
        resolved = resolve_options(images, base)
        single = build_skeleton(images, replace(resolved, swing_enabled=True))
        shared = build_animation_set(*IRREGULAR, base, [record('sway', 'swing_loop', base)])
        mixed = build_animation_set(*IRREGULAR, base, [record('sway', 'swing_loop', base),
            record('reverse', 'rotate_loop_reverse', base, axis='x', duration=2.4)])
        without_swing = build_animation_set(*IRREGULAR, base, [record('turn', 'rotate_loop', base),
            record('reverse', 'rotate_loop_reverse', base, axis='x', duration=2.4)])
        for name, skeleton, animation_name in (
                ('single', single, 'swing_loop'), ('shared', shared['skeleton'], 'sway'),
                ('mixed', mixed['skeleton'], 'sway'), ('mixed-no-swing', without_swing['skeleton'], 'turn')):
            with self.subTest(name=name):
                fps = skeleton['skeleton']['fps']
                keys = skeleton['animations'][animation_name]['drawOrder']
                authored = [f32(key.get('time', 0)) for key in keys]
                native = [native_time(key.get('time', 0), fps) for key in keys]
                self.assertIn(.75, authored)
                for time in authored:
                    self.assertEqual(bisect_right(native, time), bisect_right(authored, time),
                                     'A native draw-order key must be active at its authored key time.')

    def test_42_non_swing_legacy_finalization_stays_exact(self):
        # Before 1.14 the 4.2 finalizer was exactly the format adapter; retain
        # every key/mesh/FPS byte for existing non-swing callers.
        for changes in ({}, {'z_spin_enabled': True}, {'coin_shine_enabled': True},
                        {'bounce_enabled': True, 'z_bounce_enabled': True}):
            with self.subTest(changes=changes):
                options = TurnOptions(spine_version='4.2.43', **changes)
                images = prepare_images(*COIN, options)
                options = resolve_options(images, options)
                expected = core.convert_skeleton(core._build_canonical_skeleton(images, options), options.spine_version)
                self.assertEqual(json.dumps(build_skeleton(images, options), sort_keys=True),
                                 json.dumps(expected, sort_keys=True))

    def test_shared_settings_give_exactly_the_original_skeleton(self):
        options = TurnOptions(shade_faces=True, bounce_enabled=True)
        prepared = prepare_images(*COIN, options)
        original = build_skeleton(prepared, resolve_options(prepared, options))
        result = build_animation_set(*COIN, options, core.legacy_animation_set(options))
        self.assertTrue(result['shared'])
        self.assertEqual(json.dumps(result['skeleton'], sort_keys=True), json.dumps(original, sort_keys=True))

    def test_each_animation_keeps_its_own_settings_and_name(self):
        base = TurnOptions(thickness=30)
        records = [record('hop', 'rotate_loop', base, bounce_enabled=True, duration=2),
                   record('lean', 'swing_loop', base, axis='x', swing_angle=40, duration=1.5),
                   record('back', 'flip_to_back_reverse', base, z_spin_enabled=True, duration=3)]
        result = build_animation_set(*COIN, base, records)
        self.assertFalse(result['shared'])
        skeleton = result['skeleton']
        self.assertEqual(list(skeleton['animations']), ['hop', 'lean', 'back'])
        self.assertEqual([part['options'].axis for part in result['animations']], ['y', 'x', 'y'])
        self.assertEqual([bone['name'] for bone in skeleton['bones']], ['root', 'turn', 'spin'])
        self.assertTrue(all(slot['bone'] == 'spin' for slot in skeleton['slots']))

        def last_time(animation):
            times = []
            def visit(node):
                if isinstance(node, dict):
                    if isinstance(node.get('time'), (int, float)):
                        times.append(node['time'])
                    for value in node.values():
                        visit(value)
                elif isinstance(node, list):
                    for value in node:
                        visit(value)
            visit(animation)
            return max(times)
        self.assertEqual([round(last_time(skeleton['animations'][name]), 5) for name in ('hop', 'lean', 'back')],
                         [2, 1.5, 1.5])
        # Every animation sets the spin bone, so nothing carries over from another animation.
        for name in ('hop', 'lean', 'back'):
            self.assertIn('rotate', skeleton['animations'][name]['bones']['spin'])

    def test_irregular_outline_on_two_axes_keeps_both_meshes_and_hides_the_other(self):
        base = TurnOptions(shape='irregular')
        result = build_animation_set(*IRREGULAR, base, [record('y', 'rotate_loop', base),
                                                         record('x', 'swing_loop', base, axis='x')])
        skeleton = result['skeleton']
        slots = [slot['name'] for slot in skeleton['slots']]
        alternate = [name for name in slots if '_alt' in name]
        self.assertTrue(alternate)
        self.assertIn('back-2', result['images'])
        for name, hidden in (('y', alternate), ('x', [n for n in slots if n not in alternate][:5])):
            keys = skeleton['animations'][name]['slots']
            for slot in hidden:
                self.assertEqual(keys[slot]['attachment'][0], {'time': 0.0, 'name': None})
            self.assertIn('drawOrder', skeleton['animations'][name])

    def test_package_writes_every_animation_and_texture(self):
        base = TurnOptions(name='set', shape='irregular')
        with tempfile.TemporaryDirectory() as folder:
            result = build_package(*IRREGULAR, folder, base,
                                   animations=[record('turn', 'rotate_loop', base, coin_shine_enabled=True),
                                               record('nod', 'swing_loop', base, axis='x', duration=1)])
            self.assertEqual(result['animation_names'], ['turn', 'nod'])
            manifest = json.loads(Path(result['manifest_path']).read_text(encoding='utf-8'))
            self.assertEqual({key: (value['action'], value['duration'], value['options']['axis'])
                              for key, value in manifest['animations'].items()},
                             {'turn': ('rotate_loop', 2.0, 'y'), 'nod': ('swing_loop', 1, 'x')})
            skeleton = json.loads(Path(result['json_path']).read_text(encoding='utf-8'))
            paths = {attachment['path'] for slot in skeleton['skins'][0]['attachments'].values()
                     for attachment in slot.values()}
            atlas = Path(result['atlas_path']).read_text(encoding='utf-8').splitlines()
            images = {path.stem for path in (Path(folder) / 'images').glob('*.png')}
            self.assertLessEqual(paths, images)
            self.assertLessEqual(paths, set(atlas))
            self.assertIn('coin-shine-front', paths)


class AnimationSetProjectTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'set.spturn'
        self.sources = {'front': ASSETS / 'demo-front.png', 'back': None, 'edge': None}

    def test_animation_set_is_saved_and_restored(self):
        records = [record('one', 'rotate_loop', bounce_enabled=True), record('two', 'swing_loop', axis='x')]
        save_project(self.path, self.sources, TurnOptions(name='set'), {}, records)
        loaded = load_project(self.path)
        self.addCleanup(loaded.close)
        self.assertEqual(loaded.animations, normalize_animation_set(records))
        self.assertEqual(loaded.metadata['application_version'], '1.14.0')

    def test_projects_without_a_set_open_as_their_original_clips(self):
        loaded = load_project(ROOT / 'examples/irregular-v1.10/irregular.spturn')
        self.addCleanup(loaded.close)
        self.assertEqual([r['name'] for r in loaded.animations], list(core.DEFAULT_ANIMATIONS))

    def test_invalid_sets_are_refused(self):
        with self.assertRaisesRegex(ValueError, '動畫'):
            save_project(self.path, self.sources, TurnOptions(), {},
                         [record('a', 'rotate_loop'), record('a', 'swing_loop')])
        with self.assertRaisesRegex(ValueError, '動畫'):
            save_project(self.path, self.sources, TurnOptions(), {},
                         [{'name': 'a', 'action': 'rotate_loop', 'options': {'swing_angle': 500}}])


class AnimationSetUITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'set.spturn'
        self.sources = {'front': ASSETS / 'demo-octagon.png', 'back': None, 'edge': None}

    def opened_app(self, path):
        app = app_without_display()
        app.update_timing_summary = Mock()
        app.update_z_spin_display = Mock()
        with patch.object(main.filedialog, 'askopenfilename', return_value=str(path)), \
                patch.object(main.messagebox, 'showerror') as error:
            app.open_project()
        error.assert_not_called()
        self.addCleanup(lambda: app._loaded_project.close() if app._loaded_project else None)
        return app

    def saved(self):
        with patch.object(main.messagebox, 'showerror') as error:
            self.app.save_project()
        error.assert_not_called()
        loaded = load_project(self.path)
        self.addCleanup(loaded.close)
        return loaded

    def make(self):
        base = TurnOptions(name='set', thickness=36)
        save_project(self.path, self.sources, base, {'animation': 'swing_loop', 'current_animation': 'nod'},
                     [record('hop', 'rotate_loop', base, bounce_enabled=True, duration=2.4),
                      record('nod', 'swing_loop', base, axis='x', swing_angle=25, shade_faces=True)])
        self.app = self.opened_app(self.path)

    def test_open_shows_the_saved_current_animation(self):
        self.make()
        app = self.app
        self.assertEqual(app.current_animation.get(), 'nod')
        self.assertEqual(main.ANIMATIONS[app.animation.get()], 'swing_loop')
        self.assertEqual((app.axis.get(), app.swing_angle.get(), app.shade_faces.get()),
                         ('上下翻轉 · X 軸', 25, True))

    def test_switching_shows_each_animation_without_changing_the_other(self):
        self.make()
        app = self.app
        app.swing_angle.set(33)
        app.current_animation.set('hop')
        app.on_animation_choice()
        self.assertEqual(main.ANIMATIONS[app.animation.get()], 'rotate_loop')
        self.assertEqual((app.axis.get(), app.duration.get(), app.bounce_enabled.get(), app.shade_faces.get()),
                         ('左右翻轉 · Y 軸', 2.4, True, False))
        app.thickness.set(50)                   # shared
        app.duration.set(3)                     # this animation only
        saved = self.saved()
        options = {r['name']: r['options'] for r in saved.animations}
        self.assertEqual((options['hop']['duration'], options['nod']['duration']), (3, 2.0))
        self.assertEqual((options['nod']['swing_angle'], options['nod']['axis']), (33, 'x'))
        self.assertEqual(saved.options.thickness, 50)
        self.assertNotIn('current_animation', saved.ui_state)

    def test_add_copy_rename_and_delete(self):
        self.make()
        app = self.app
        with patch.object(main.simpledialog, 'askstring', side_effect=['nod_copy', 'spin', 'twirl']), \
                patch.object(main.messagebox, 'showerror') as error, \
                patch.object(main.messagebox, 'askyesno', return_value=True):
            self.assertTrue(app.add_animation(copy=True))
            self.assertEqual(app.current_animation.get(), 'nod_copy')
            self.assertEqual(app.swing_angle.get(), 25)
            self.assertTrue(app.add_animation())
            self.assertEqual((app.current_animation.get(), main.ANIMATIONS[app.animation.get()]),
                             ('spin', 'rotate_loop'))
            self.assertEqual(app.axis.get(), '左右翻轉 · Y 軸')
            self.assertTrue(app.rename_animation())
            self.assertEqual(app.current_animation.get(), 'twirl')
            self.assertTrue(app.delete_animation())
            error.assert_not_called()
        self.assertEqual([e['name'] for e in app.animation_entries], ['hop', 'nod', 'nod_copy'])
        self.assertEqual(app.current_animation.get(), 'nod_copy')
        self.assertEqual([r['name'] for r in self.saved().animations], ['hop', 'nod', 'nod_copy'])

    def test_duplicate_names_are_refused_and_the_last_animation_stays(self):
        self.make()
        app = self.app
        with patch.object(main.simpledialog, 'askstring', side_effect=['HOP', None]), \
                patch.object(main.messagebox, 'showerror') as error:
            self.assertFalse(app.rename_animation())
        self.assertIn('已經有', error.call_args[0][1])
        with patch.object(main.messagebox, 'askyesno', return_value=True):
            self.assertTrue(app.delete_animation())
            self.assertFalse(app.delete_animation())
        self.assertEqual([e['name'] for e in app.animation_entries], ['hop'])

    def test_old_project_opens_as_three_animations_and_saves_them_unchanged(self):
        app = self.app = self.opened_app(ROOT / 'examples/irregular-v1.10/irregular.spturn')
        self.assertEqual([e['name'] for e in app.animation_entries], list(core.DEFAULT_ANIMATIONS))
        original = load_project(ROOT / 'examples/irregular-v1.10/irregular.spturn')
        self.addCleanup(original.close)
        app.project_path = str(self.path)
        self.assertEqual(self.saved().animations, original.animations)


if __name__ == '__main__':
    unittest.main(verbosity=2)
