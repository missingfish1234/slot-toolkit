"""Reverse turns and multi-clip output: geometry, export, PNG sequences, project and UI."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
import main
import spine_turn_core as core
from spine_turn_core import (TurnOptions, animation_pose_at, build_package, build_skeleton,
                             clip_angle_at, exported_animations, normalize_options, prepare_images,
                             resolve_options)
from spine_turn_project import load_project, save_project
from spine_turn_sequence import export_sequence
from spine_turn_ui_actions import StudioActions
from test_v16_ui_project import app_without_display, Value

ASSETS = ROOT / 'assets'
# A forward clip played backwards is the reverse clip that runs the same angles.
PAIRS = (('rotate_loop', 'rotate_loop_reverse'), ('flip_to_back', 'flip_to_front_reverse'),
         ('flip_to_front', 'flip_to_back_reverse'))


def scene(front='demo-front.png', back='demo-back.png', edge='demo-edge.png', **changes):
    options = replace(TurnOptions(), **changes)
    prepared = prepare_images(ASSETS / front, ASSETS / back if back else None,
                              ASSETS / edge if edge else None, options)
    return prepared, resolve_options(prepared, options)


class ReverseClipTests(unittest.TestCase):
    def test_reverse_clips_run_the_same_angles_backwards(self):
        self.assertEqual([clip_angle_at(p, 'rotate_loop_reverse') for p in (0, .25, .5, 1)], [360, 270, 180, 0])
        self.assertEqual([clip_angle_at(p, 'flip_to_back_reverse') for p in (0, .5, 1)], [360, 270, 180])
        self.assertEqual([clip_angle_at(p, 'flip_to_front_reverse') for p in (0, .5, 1)], [180, 90, 0])
        options = TurnOptions(duration=3)
        self.assertEqual([core.clip_duration(options, name) for name in core.CLIP_ORDER[:6]],
                         [3, 3, 1.5, 1.5, 1.5, 1.5])

    def test_reverse_timeline_follows_exact_geometry_and_visibility_for_every_model(self):
        cases = {
            'coin': scene(shade_faces=True),
            'coin-x': scene(axis='x'),
            'bevel-light': scene('demo-octagon.png', None, None, shape='polygon', bevel_width=.1,
                                 coin_shine_enabled=True),
            'ridge': scene('demo-octagon.png', None, None, shape='polygon', side_mode='ridge'),
            'irregular': scene('demo-irregular-front.png', 'demo-irregular-back.png', 'demo-edge.png',
                               shape='irregular', bounce_enabled=True, z_bounce_enabled=True),
            'diamond': scene('demo-diamond-aligned.png', None, None, model='diamond', trim_transparent=False),
        }
        for name, (prepared, options) in cases.items():
            width, height = prepared['width'], prepared['height']
            for clip in ('rotate_loop_reverse', 'flip_to_back_reverse', 'flip_to_front_reverse'):
                start, end = core.CLIP_ARCS[clip]
                with self.subTest(case=name, clip=clip):
                    worst = 0
                    for index in range(81):
                        progress = (index + .5) / 81
                        got = {s['name']: s for s in animation_pose_at(progress, options, width, height, clip)}
                        depth = core._depth_at_resolved(progress, options)['z_scale']
                        exact = core.pose_at(core._clip_pose_angle(start + progress * (end - start), start, end, options),
                                             replace(options, coin_shine_enabled=False), width, height,
                                             _depth_scale=depth, _effect_progress=progress)
                        for surface in exact:
                            if surface['kind'] in ('coin_fx', 'diamond_fx'):
                                continue
                            self.assertEqual(got[surface['name']]['visible'], surface['visible'], (progress, surface['name']))
                            if surface['visible']:
                                worst = max(worst, max(abs(a - b) for a, b in
                                                       zip(surface['vertices'], got[surface['name']]['vertices'])))
                    self.assertLess(worst, 1.5)
            first = animation_pose_at(0, options, width, height, 'rotate_loop_reverse')
            last = animation_pose_at(1, options, width, height, 'rotate_loop_reverse')
            self.assertEqual([s['vertices'] for s in first], [s['vertices'] for s in last])

    def test_plain_reverse_turn_is_the_forward_turn_played_backwards(self):
        prepared, options = scene(shade_faces=True)
        width, height = prepared['width'], prepared['height']
        for forward, reverse in PAIRS:
            for index in range(1, 24):
                progress = index / 24
                ahead = animation_pose_at(1 - progress, options, width, height, forward)
                back = animation_pose_at(progress, options, width, height, reverse)
                for one, two in zip(ahead, back):
                    self.assertLess(max(abs(a - b) for a, b in zip(one['vertices'], two['vertices'])), 1e-6)
                    # Same shade; 8-bit rounding at a key may land one step (1/255) apart.
                    self.assertLessEqual(max(abs(a - b) for a, b in zip(one['tint'], two['tint'])), 1 / 255 + 1e-9)


class ClipSelectionTests(unittest.TestCase):
    def test_default_and_explicit_default_selection_store_the_same_way(self):
        for chosen, swing in ((('flip_to_front', 'rotate_loop', 'flip_to_back'), False),
                              (('rotate_loop', 'flip_to_back', 'flip_to_front', 'swing_loop'), True)):
            options = normalize_options(TurnOptions(export_animations=chosen))
            self.assertEqual((options.export_animations, options.swing_enabled), ((), swing))
        self.assertEqual(exported_animations(TurnOptions()), core.DEFAULT_ANIMATIONS)
        self.assertEqual(exported_animations(TurnOptions(swing_enabled=True)),
                         core.DEFAULT_ANIMATIONS + ('swing_loop',))

    def test_custom_selection_is_ordered_and_controls_the_swing_switch(self):
        options = normalize_options(TurnOptions(swing_enabled=True,
            export_animations=['flip_to_front_reverse', 'rotate_loop_reverse', 'rotate_loop_reverse']))
        self.assertEqual(options.export_animations, ('rotate_loop_reverse', 'flip_to_front_reverse'))
        self.assertFalse(options.swing_enabled)
        for bad in (('rotate_loop', 'spin_forever'), 'rotate_loop', 7):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                normalize_options(TurnOptions(export_animations=bad))

    def test_skeleton_contains_exactly_the_chosen_clips_and_shared_parts_are_unchanged(self):
        prepared, options = scene(shade_faces=True, bounce_enabled=True)
        legacy = build_skeleton(prepared, options)
        chosen = ('rotate_loop', 'rotate_loop_reverse', 'flip_to_back_reverse', 'swing_loop')
        custom = build_skeleton(prepared, replace(options, export_animations=chosen))
        self.assertEqual(tuple(custom['animations']), chosen)
        self.assertEqual(custom['animations']['rotate_loop'], legacy['animations']['rotate_loop'])
        for part in ('bones', 'slots', 'skins'):
            self.assertEqual(custom[part], legacy[part])
        only = build_skeleton(prepared, replace(options, export_animations=('flip_to_front_reverse',)))
        self.assertEqual(list(only['animations']), ['flip_to_front_reverse'])

    def test_every_supported_spine_family_receives_the_chosen_clips_with_correct_lengths(self):
        chosen = ('rotate_loop_reverse', 'flip_to_back_reverse', 'flip_to_front')
        for family in ('3.8', '4.0', '4.2'):
            with self.subTest(family=family), tempfile.TemporaryDirectory() as folder:
                result = build_package(ASSETS / 'demo-front.png', ASSETS / 'demo-back.png', ASSETS / 'demo-edge.png',
                    folder, TurnOptions(name='multi', duration=1.6, export_animations=chosen,
                                        spine_version=core.SPINE_TARGETS[family]))
                self.assertEqual(tuple(result['animation_names']), chosen)
                manifest = json.loads(Path(result['manifest_path']).read_text(encoding='utf-8'))
                self.assertEqual({name: (clip['duration'], clip['loop']) for name, clip in manifest['animations'].items()},
                                 {'rotate_loop_reverse': (1.6, True), 'flip_to_back_reverse': (.8, False),
                                  'flip_to_front': (.8, False)})
                skeleton = json.loads(Path(result['json_path']).read_text(encoding='utf-8'))
                self.assertEqual(tuple(skeleton['animations']), chosen)


class SequenceTests(unittest.TestCase):
    def test_reverse_sequence_is_the_forward_sequence_played_backwards(self):
        prepared, options = scene(shade_edge=False)
        with tempfile.TemporaryDirectory() as folder:
            forward = Path(folder) / 'forward'
            reverse = Path(folder) / 'reverse'
            export_sequence(prepared, options, forward, animation_name='flip_to_back', fps=8, size=(96, 96))
            result = export_sequence(prepared, options, reverse, animation_name='flip_to_front_reverse',
                                     fps=8, size=(96, 96))
            self.assertEqual(result['frame_count'], 9)
            manifest = json.loads((reverse / 'sequence.json').read_text(encoding='utf-8'))
            self.assertEqual((manifest['animation'], manifest['loop']), ('flip_to_front_reverse', False))
            with Image.open(reverse / 'frame_0000.png') as first, Image.open(forward / 'frame_0008.png') as back:
                self.assertEqual(first.getchannel('A').getbbox(), back.getchannel('A').getbbox())


class ReverseClipUITests(unittest.TestCase):
    def test_reverse_clips_report_and_accept_falling_angles(self):
        app = main.App.__new__(main.App)
        app.animation, app.duration = Value('正面 → 背面（反轉）'), Value(2)
        app.number = lambda variable, *_: variable.get()
        app.progress = .5
        self.assertEqual(app.angle_at_progress(), 270)
        self.assertEqual(app.clip_duration(), 1)
        app.animation.set('整圈旋轉（反轉）')
        self.assertEqual(app.clip_duration(), 2)

        class Probe(StudioActions):
            def __init__(self):
                self.busy = False
                self.animation, self.angle_input, self.status = Value('背面 → 正面（反轉）'), Value('45'), Value('')
                self.sought = []
            def seek_progress(self, progress):
                self.sought.append(progress)
                return True
        probe = Probe()
        self.assertTrue(probe.apply_angle())
        self.assertAlmostEqual(probe.sought[-1], .75)
        probe.angle_input.set('200')
        self.assertFalse(probe.apply_angle())
        self.assertIn('0° 與 180°', probe.status.get())


if __name__ == '__main__':
    unittest.main(verbosity=2)
