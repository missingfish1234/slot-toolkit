"""Alignment edits remain local until Apply and preserve animation/project settings."""
from dataclasses import asdict, replace
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
import main
from test_v16_ui_project import app_without_display
from spine_turn_core import TurnOptions, normalize_options
from spine_turn_project import save_project, load_project


class AlignmentIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.filename = self.folder / 'alignment.spturn'
        self.original = TurnOptions(name='alignment', model='diamond', trim_transparent=False,
            spine_version='4.2.43', diamond_view_tilt=24, diamond_ring_phase=22.5,
            diamond_table_depth=.5, diamond_waist_depth=.96,
            diamond_cut_regions=((((-.2, .2), (0, .2), (0, .35)), -15., 10.),))
        save_project(self.filename, {'front': ROOT / 'assets' / 'demo-diamond.png',
            'back': None, 'edge': None}, self.original,
            {'animation': 'flip_to_front', 'progress': .37, 'playing': True})
        loaded = load_project(self.filename)
        self.addCleanup(loaded.close)
        self.app = app_without_display()
        self.app.apply_loaded_project(loaded, self.filename)
        self.app.root.wait_window = Mock()
        self.before = (self.app.playing, self.app.progress, self.app.angle)
        self.before_animation = self.app.animation.get()

    def run_editor(self, action):
        def open_editor(parent, image, options, on_apply):
            self.assertFalse(self.app.playing)
            self.assertEqual((self.app.progress, self.app.angle, self.app.slider.get()), (0, 0, 0))
            self.assertEqual(self.app.animation.get(), '整圈旋轉')
            self.assertEqual(options.diamond_ring_phase, self.original.diamond_ring_phase)
            self.assertEqual(image.mode, 'RGBA')
            action(on_apply)
            return 'modal'
        module = SimpleNamespace(open_diamond_alignment_editor=Mock(side_effect=open_editor))
        with patch.dict(sys.modules, {'spine_turn_diamond_alignment_editor': module}), \
             patch('main.messagebox.showerror') as error:
            self.app.edit_diamond()
        error.assert_not_called()
        self.app.root.wait_window.assert_called_once_with('modal')

    def test_cancel_restores_exact_half_turn_progress_and_playback_without_mutating_project(self):
        original_options = asdict(self.app.get_options())
        original_file = self.filename.read_bytes()
        self.run_editor(lambda on_apply: None)
        self.assertEqual((self.app.playing, self.app.progress, self.app.angle), self.before)
        self.assertEqual(self.app.animation.get(), self.before_animation)
        self.assertAlmostEqual(self.app.slider.get(), self.before[1] * 360)
        self.assertEqual(asdict(self.app.get_options()), original_options)
        self.assertEqual(self.filename.read_bytes(), original_file)

    def test_apply_updates_actual_shape_stays_at_front_and_ctrl_s_reopens_same_depth_phase(self):
        changes = {'diamond_table_width': .58, 'diamond_waist_width': .92,
            'diamond_table_depth': .58, 'diamond_waist_depth': .92,
            'diamond_ring_phase': 15., 'diamond_view_tilt': 28., 'diamond_facets': 12}
        self.run_editor(lambda on_apply: on_apply(changes))
        self.assertEqual((self.app.playing, self.app.progress, self.app.angle), (False, 0, 0))
        self.assertEqual(self.app.animation.get(), '整圈旋轉')
        expected = normalize_options(replace(self.original, **changes))
        self.assertEqual(asdict(self.app.get_options()), asdict(expected))
        with patch('main.messagebox.showerror') as error:
            self.app.save_project()
        error.assert_not_called()
        with load_project(self.filename) as saved:
            self.assertEqual(asdict(saved.options), asdict(expected))
            self.assertFalse(saved.ui_state['playing'])
            self.assertEqual(saved.ui_state['progress'], 0)
            self.assertEqual(saved.options.diamond_cut_regions, self.original.diamond_cut_regions)

    def test_editor_failure_restores_view_and_leaves_original_options(self):
        original_options = asdict(self.app.get_options())
        module = SimpleNamespace(open_diamond_alignment_editor=Mock(side_effect=ValueError('示範錯誤')))
        with patch.dict(sys.modules, {'spine_turn_diamond_alignment_editor': module}), \
             patch('main.messagebox.showerror') as error:
            self.app.edit_diamond()
        self.assertEqual((self.app.playing, self.app.progress, self.app.angle), self.before)
        self.assertEqual(self.app.animation.get(), self.before_animation)
        self.assertEqual(asdict(self.app.get_options()), original_options)
        self.assertIn('示範錯誤', error.call_args.args[1])


if __name__ == '__main__':
    unittest.main(verbosity=2)
