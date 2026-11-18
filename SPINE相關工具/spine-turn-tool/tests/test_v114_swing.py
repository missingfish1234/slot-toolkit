"""Back-and-forth swing clip: geometry, export, PNG sequence, project and UI contracts."""
from dataclasses import replace
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
import main
import spine_turn_core as core
from spine_turn_core import (TurnOptions, animation_pose_at, build_package, build_skeleton, pose_at,
                             prepare_images, resolve_options, swing_angle_at)
from spine_turn_preview import render_pose
from spine_turn_project import load_project, save_project
from spine_turn_sequence import export_sequence
from spine_turn_ui_actions import StudioActions
from test_v16_ui_project import app_without_display, Value

ASSETS = ROOT / 'assets'
START, END = core.SWING_ARC


def scene(front='demo-front.png', back='demo-back.png', edge='demo-edge.png', **changes):
    options = replace(TurnOptions(), **{'swing_enabled': True, **changes})
    prepared = prepare_images(ASSETS / front, ASSETS / back if back else None,
                              ASSETS / edge if edge else None, options)
    return prepared, resolve_options(prepared, options)


def exact_pose(progress, options, width, height):
    """The mathematical pose at the swing's angle, facing the way it is travelling."""
    return pose_at(core._clip_pose_angle(START + progress * (END - START), START, END, options),
                   replace(options, coin_shine_enabled=False), width, height, _effect_progress=progress)


class SwingMotionTests(unittest.TestCase):
    def test_angle_leans_both_ways_and_returns_to_rest(self):
        options = TurnOptions(swing_angle=40)
        self.assertEqual([swing_angle_at(progress, options) for progress in (0, .25, .5, .75, 1)],
                         [0, 40, 0, -40, 0])
        self.assertAlmostEqual(swing_angle_at(1 / 12, options), 20)
        self.assertAlmostEqual(swing_angle_at(7 / 12, options), -20)
        self.assertEqual(core.clip_duration(replace(options, duration=3), 'swing_loop'), 3)
        self.assertEqual(core.clip_duration(replace(options, duration=3), 'flip_to_back'), 1.5)

    def test_invalid_swing_settings_are_rejected(self):
        for changes in ({'swing_angle': 0}, {'swing_angle': 181}, {'swing_angle': math.nan},
                        {'swing_angle': True}, {'swing_angle': 'wide'}, {'swing_enabled': 1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                core.normalize_options(replace(TurnOptions(), **changes))

    def test_small_swing_keeps_front_face_and_shows_thickness_on_alternating_sides(self):
        prepared, options = scene(swing_angle=30, thickness=40)
        width, height = prepared['width'], prepared['height']
        visible_rims = {}
        for progress in (.25, .75):
            pose = {surface['name']: surface for surface in animation_pose_at(progress, options, width, height, 'swing_loop')}
            self.assertTrue(pose['front']['visible'])
            self.assertFalse(pose['back']['visible'])
            rims = [surface for surface in pose.values() if surface['kind'] == 'edge' and surface['visible']]
            self.assertTrue(rims)
            visible_rims[progress] = {surface['name'] for surface in rims}
            xs = pose['front']['vertices'][::2]
            # The face is foreshortened by cos(30 deg) while the edge adds visible depth.
            self.assertAlmostEqual(max(xs) - min(xs), width * math.cos(math.radians(30)), delta=1e-6)
            rim_xs = [x for surface in rims for x in surface['vertices'][::2]]
            self.assertGreater(max(xs + rim_xs) - min(xs + rim_xs), max(xs) - min(xs) + 5)
        self.assertFalse(visible_rims[.25] & visible_rims[.75])

    def test_timeline_follows_exact_geometry_and_visibility_for_every_model(self):
        cases = {
            'coin': scene(),
            'coin-x-wide': scene(axis='x', swing_angle=120),
            'quarter-turn': scene(swing_angle=90),
            'bevel': scene('demo-octagon.png', None, None, shape='polygon', bevel_width=.1, swing_angle=150),
            'ridge': scene('demo-octagon.png', None, None, shape='polygon', side_mode='ridge', swing_angle=180),
            'irregular-light': scene('demo-irregular-front.png', 'demo-irregular-back.png', 'demo-edge.png',
                                     shape='irregular', swing_angle=35, coin_shine_enabled=True),
            'diamond': scene('demo-diamond-aligned.png', None, None, model='diamond',
                             trim_transparent=False, swing_angle=40),
        }
        for name, (prepared, options) in cases.items():
            with self.subTest(case=name):
                width, height = prepared['width'], prepared['height']
                worst = 0
                for index in range(121):
                    progress = (index + .5) / 121
                    got = {surface['name']: surface
                           for surface in animation_pose_at(progress, options, width, height, 'swing_loop')}
                    for surface in exact_pose(progress, options, width, height):
                        if surface['kind'] in ('coin_fx', 'diamond_fx'):
                            continue
                        self.assertEqual(got[surface['name']]['visible'], surface['visible'],
                                         (progress, surface['name']))
                        if surface['visible']:
                            worst = max(worst, max(abs(a - b) for a, b in
                                                   zip(surface['vertices'], got[surface['name']]['vertices'])))
                self.assertLess(worst, 1.5)
                first = animation_pose_at(0, options, width, height, 'swing_loop')
                last = animation_pose_at(1, options, width, height, 'swing_loop')
                self.assertEqual([(s['vertices'], s['visible'], s['color']) for s in first],
                                 [(s['vertices'], s['visible'], s['color']) for s in last])

    def test_keys_include_turning_points_and_never_step_further_than_a_turn_would(self):
        for amplitude in (1, 30, 90, 137, 180):
            options = TurnOptions(swing_enabled=True, swing_angle=amplitude)
            keys = core._animation_angles(START, END, options, 200, 200)
            self.assertEqual(keys, sorted(set(keys)))
            for quarter in range(5):
                self.assertIn(START + 90. * quarter, keys)
            angles = [core._clip_angle(key, START, END, options) for key in keys]
            self.assertLessEqual(max(abs(b - a) for a, b in zip(angles, angles[1:])),
                                 options.key_step_degrees + 1e-9)
            for critical in (-90, 90):
                if amplitude >= 90:
                    self.assertGreaterEqual(sum(abs(angle - critical) < 1e-9 for angle in angles), 1)


class SwingExportTests(unittest.TestCase):
    def test_disabled_export_is_unchanged_and_enabled_export_adds_one_looping_clip(self):
        prepared, options = scene(swing_enabled=False, shade_faces=True)
        disabled = build_skeleton(prepared, options)
        self.assertEqual(list(disabled['animations']), ['rotate_loop', 'flip_to_back', 'flip_to_front'])
        enabled = build_skeleton(prepared, replace(options, swing_enabled=True, swing_angle=25))
        self.assertEqual(list(enabled['animations']),
                         ['rotate_loop', 'flip_to_back', 'flip_to_front', 'swing_loop'])
        for clip in ('rotate_loop', 'flip_to_back', 'flip_to_front'):
            self.assertEqual(enabled['animations'][clip], disabled['animations'][clip])
        self.assertEqual(enabled['slots'], disabled['slots'])
        self.assertEqual(enabled['skins'], disabled['skins'])
        self.assertEqual(enabled['bones'], disabled['bones'])

    def test_swing_clip_lasts_one_full_duration_and_closes_its_loop(self):
        for family in ('3.8', '4.0', '4.2'):
            with self.subTest(family=family):
                prepared, options = scene(swing_angle=45, duration=1.6, bounce_enabled=True,
                                          spine_version=core.SPINE_TARGETS[family])
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
                swing = build_skeleton(prepared, options)['animations']['swing_loop']
                visit(swing)
                self.assertAlmostEqual(max(times), 1.6, places=5)
                self.assertGreaterEqual(min(times, default=0), 0)

    def test_package_manifest_describes_the_swing_clip(self):
        with tempfile.TemporaryDirectory() as folder:
            result = build_package(ASSETS / 'demo-front.png', ASSETS / 'demo-back.png', ASSETS / 'demo-edge.png',
                                   folder, TurnOptions(name='swing', swing_enabled=True, swing_angle=20, duration=2))
            manifest = json.loads(Path(result['manifest_path']).read_text(encoding='utf-8'))
            self.assertEqual(result['animation_names'][-1], 'swing_loop')
            clip = manifest['animations']['swing_loop']
            self.assertEqual((clip['duration'], clip['loop']), (2, True))
            self.assertEqual((manifest['options']['swing_enabled'], manifest['options']['swing_angle']), (True, 20))
            skeleton = json.loads(Path(result['json_path']).read_text(encoding='utf-8'))
            self.assertIn('swing_loop', skeleton['animations'])


class SwingRenderTests(unittest.TestCase):
    def test_preview_frames_mirror_each_other_about_the_axis_for_symmetric_art(self):
        prepared, options = scene('demo-octagon.png', None, None, shape='rectangle', swing_angle=35,
                                  thickness=30, shade_edge=False)
        rest = render_pose(prepared, options, 0, (240, 200), 'transparent', progress=0,
                           animation_name='swing_loop', show_ground=False)
        right = render_pose(prepared, options, 0, (240, 200), 'transparent', progress=.25,
                            animation_name='swing_loop', show_ground=False)
        left = render_pose(prepared, options, 0, (240, 200), 'transparent', progress=.75,
                           animation_name='swing_loop', show_ground=False)
        again = render_pose(prepared, options, 0, (240, 200), 'transparent', progress=.5,
                            animation_name='swing_loop', show_ground=False)
        self.assertEqual(rest.tobytes(), again.tobytes())
        self.assertNotEqual(rest.tobytes(), right.tobytes())
        self.assertNotEqual(left.tobytes(), right.tobytes())
        box_rest, box_right, box_left = (image.getchannel('A').getbbox() for image in (rest, right, left))
        for leaned, resting in zip(box_right[1::2], box_rest[1::2]):
            self.assertAlmostEqual(leaned, resting, delta=1)
        self.assertAlmostEqual(box_right[2] - box_right[0], box_left[2] - box_left[0], delta=1)
        self.assertAlmostEqual(box_right[0] + box_right[2], 480 - (box_left[0] + box_left[2]), delta=2)

    def test_png_sequence_exports_a_seamless_swing_inside_one_canvas(self):
        prepared, options = scene(swing_angle=60, duration=1)
        with tempfile.TemporaryDirectory() as folder:
            result = export_sequence(prepared, options, Path(folder) / 'frames', animation_name='swing_loop',
                                     fps=12, size=(160, 160))
            self.assertEqual(result['frame_count'], 12)
            manifest = json.loads((Path(folder) / 'frames' / 'sequence.json').read_text(encoding='utf-8'))
            self.assertEqual((manifest['animation'], manifest['loop']), ('swing_loop', True))
            from PIL import Image
            boxes = []
            for index in range(12):
                with Image.open(Path(folder) / 'frames' / f'frame_{index:04d}.png') as frame:
                    boxes.append(frame.getchannel('A').getbbox())
            self.assertTrue(all(box and box[0] >= 0 and box[2] <= 160 for box in boxes))
            self.assertEqual(boxes[0], boxes[6])            # rest pose twice per loop
            self.assertLess(boxes[3][2] - boxes[3][0], boxes[0][2] - boxes[0][0])


class SwingUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'swing.spturn'
        self.sources = {'front': ROOT / 'assets/demo-octagon.png', 'back': None, 'edge': None}

    def opened_app(self, path):
        app = app_without_display()
        with patch.object(main.filedialog, 'askopenfilename', return_value=str(path)), \
                patch.object(main.messagebox, 'showerror') as error:
            app.open_project()
        error.assert_not_called()
        self.addCleanup(lambda: app._loaded_project.close() if app._loaded_project else None)
        return app

    def test_swing_animation_opens_edits_saves_and_reopens(self):
        options = TurnOptions(name='swing', swing_angle=42)
        save_project(self.path, self.sources, options, {'playing': False, 'progress': .25, 'animation': 'swing_loop'},
                     [{'name': 'sway', 'action': 'swing_loop', 'options': core.animation_overrides(options)}])
        app = self.opened_app(self.path)
        self.assertEqual(app.swing_angle.get(), 42)
        self.assertEqual(main.ANIMATIONS[app.animation.get()], 'swing_loop')
        self.assertAlmostEqual(app.angle, 42)
        app.swing_angle.set(18)
        with patch.object(main.messagebox, 'showerror') as error:
            app.save_project()
        error.assert_not_called()
        saved = load_project(self.path)
        self.addCleanup(saved.close)
        self.assertEqual([(r['name'], r['action'], r['options']['swing_angle']) for r in saved.animations],
                         [('sway', 'swing_loop', 18)])
        self.assertEqual(saved.ui_state['animation'], 'swing_loop')

    def test_out_of_range_amplitude_is_reported_by_the_form(self):
        app = self.opened_app(ROOT / 'examples/irregular-v1.10/irregular.spturn')
        app.swing_angle.set(200)
        with self.assertRaises(ValueError):
            app.get_options()

    def test_swing_uses_the_full_duration_and_reports_signed_angles(self):
        app = main.App.__new__(main.App)
        app.animation, app.duration = Value('來回搖擺'), Value(2.4)
        app.number = lambda variable, *_: variable.get()
        app.options = TurnOptions(swing_angle=50)
        self.assertEqual(app.clip_duration(), 2.4)
        for progress, expected in ((0, 0), (.25, 50), (.5, 0), (.75, -50)):
            app.progress = progress
            self.assertAlmostEqual(app.angle_at_progress(), expected)
        app.animation.set('正面 → 背面')
        self.assertEqual(app.clip_duration(), 1.2)

    def test_typed_lean_angle_seeks_within_the_amplitude(self):
        class Probe(StudioActions):
            def __init__(self):
                self.busy = False
                self.animation, self.angle_input, self.status = Value('來回搖擺'), Value('25'), Value('')
                self.sought = []
            def swing_amplitude(self):
                return 50.
            def seek_progress(self, progress):
                self.sought.append(progress)
                return True
        probe = Probe()
        self.assertTrue(probe.apply_angle())
        self.assertAlmostEqual(probe.sought[-1], 1 / 12)
        probe.angle_input.set('-50')
        self.assertTrue(probe.apply_angle())
        self.assertAlmostEqual(probe.sought[-1], .75)
        probe.angle_input.set('51')
        self.assertFalse(probe.apply_angle())
        self.assertIn('擺幅', probe.status.get())
        self.assertEqual(len(probe.sought), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
