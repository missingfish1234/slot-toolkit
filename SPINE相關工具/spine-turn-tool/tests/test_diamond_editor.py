"""Diamond guide geometry/history and Apply/Cancel semantics without a display."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spine_turn_diamond_editor import GUIDE_DEFAULTS, DiamondGuideModel, _DiamondEditor, guide_values
from spine_turn_region_editor import CanvasTransform


class DiamondGuideEditorTests(unittest.TestCase):
    def test_handles_use_full_width_fractions_and_world_up_on_non_square_image(self):
        options = {**GUIDE_DEFAULTS, 'diamond_center_x': .1,
            'diamond_table_width': .3, 'diamond_waist_width': .7}
        model = DiamondGuideModel(options, (300, 180))
        points = model.handle_points()
        self.assertAlmostEqual(points['table_left'][0], -.05)
        self.assertAlmostEqual(points['table_right'][0], .25)
        self.assertAlmostEqual(points['waist_left'][0], -.25)
        self.assertAlmostEqual(points['waist_right'][0], .45)
        self.assertEqual(points['tip'], (.1, -.48))
        transform = CanvasTransform(300, 180, 800, 500)
        left, right = (transform.to_canvas(points[name]) for name in ('table_left', 'table_right'))
        self.assertAlmostEqual(right[0] - left[0], .3 * 300 * transform.scale)
        self.assertLess(transform.to_canvas(points['table_y'])[1], transform.to_canvas(points['waist_y'])[1])

    def test_dragging_width_is_symmetric_and_center_keeps_profile_in_image(self):
        model = DiamondGuideModel({**GUIDE_DEFAULTS, 'diamond_center_x': .05,
            'diamond_table_width': .4, 'diamond_waist_width': .8}, (300, 180))
        model.drag('table_left', (-.1, -.4))
        self.assertAlmostEqual(model.guides['diamond_table_width'], .3)
        points = model.handle_points()
        self.assertAlmostEqual(points['table_left'][0], -.1)
        self.assertAlmostEqual(points['table_right'][0], .2)
        self.assertEqual(points['table_y'][1], .35)
        model.drag('waist_right', (.49, 0))
        self.assertAlmostEqual(model.guides['diamond_waist_width'], .88)
        model.drag('center', (.4, 0))
        self.assertAlmostEqual(model.guides['diamond_center_x'], .06)
        self.assertLessEqual(model.handle_points()['waist_right'][0], .5 + 1e-12)
        model.validate()

    def test_vertical_drags_cannot_swap_table_waist_and_tip(self):
        model = DiamondGuideModel(GUIDE_DEFAULTS, (300, 180))
        model.drag('table_y', (0, -.49))
        self.assertGreater(model.guides['diamond_table_y'], model.guides['diamond_waist_y'])
        model.drag('waist_y', (0, .49))
        self.assertLess(model.guides['diamond_waist_y'], model.guides['diamond_table_y'])
        model.drag('tip', (.3, .49))
        self.assertLess(model.guides['diamond_tip_y'], model.guides['diamond_waist_y'])
        self.assertEqual(model.handle_points()['tip'][0], model.guides['diamond_center_x'])
        model.validate()

    def test_guides_respect_existing_girdle_height_without_exposing_extra_controls(self):
        model = DiamondGuideModel({**GUIDE_DEFAULTS, 'diamond_girdle_height': .12}, (300, 180))
        model.drag('table_y', (0, -.49))
        self.assertGreater(model.guides['diamond_table_y'] - model.guides['diamond_waist_y'], .06)
        model.validate()
        with self.assertRaisesRegex(ValueError, '腰'):
            DiamondGuideModel({**GUIDE_DEFAULTS, 'diamond_girdle_height': .12,
                'diamond_table_y': .14}, (300, 180))

    def test_drag_coalesces_into_one_undo_and_new_edit_discards_redo(self):
        source = dict(GUIDE_DEFAULTS)
        model = DiamondGuideModel(source, (300, 180))
        for x in (.4, .42, .43, .44):
            model.drag('waist_right', (x, 0))
        self.assertTrue(model.can_undo)
        model.commit()
        final = dict(model.guides)
        model.undo()
        self.assertEqual(model.guides, GUIDE_DEFAULTS)
        self.assertFalse(model.can_undo)
        model.redo()
        self.assertEqual(model.guides, final)
        model.undo()
        model.set_values({**model.guides, 'diamond_tip_y': -.4})
        self.assertFalse(model.can_redo)
        self.assertEqual(source, GUIDE_DEFAULTS)

    def test_reset_is_undoable_and_invalid_numeric_geometry_remains_repairable(self):
        initial = {**GUIDE_DEFAULTS, 'diamond_table_y': .4, 'diamond_tip_y': -.4}
        model = DiamondGuideModel(initial, (300, 180))
        model.reset()
        self.assertEqual(model.guides, GUIDE_DEFAULTS)
        model.undo()
        self.assertEqual(model.guides, initial)
        model.set_values({**initial, 'diamond_table_y': -.2})
        with self.assertRaises(ValueError):
            model.validate()
        model.undo()
        self.assertEqual(model.guides, initial)
        self.assertEqual(model.initial, initial)

    def test_out_of_bounds_ordering_width_and_nonfinite_input_are_rejected(self):
        for change in [{'diamond_center_x': .3}, {'diamond_tip_y': -.5},
            {'diamond_table_y': .05}, {'diamond_table_width': 1},
            {'diamond_waist_width': .4}, {'diamond_table_y': float('nan')}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                DiamondGuideModel({**GUIDE_DEFAULTS, **change}, (300, 180))

    def test_cancel_has_no_callback_and_apply_returns_independent_six_field_snapshot(self):
        editor = _DiamondEditor.__new__(_DiamondEditor)
        source = dict(GUIDE_DEFAULTS)
        editor.model = DiamondGuideModel(source, (300, 180))
        editor.callback = Mock()
        editor.window = SimpleNamespace(result=None)
        editor._destroy = Mock()
        editor.cancel()
        editor.callback.assert_not_called()
        self.assertIsNone(editor.window.result)
        self.assertEqual(source, GUIDE_DEFAULTS)
        editor.commit_fields = Mock()
        editor._field_error = ''
        editor.redraw = Mock()
        editor.apply()
        editor.callback.assert_called_once()
        payload = editor.callback.call_args.args[0]
        self.assertEqual(payload, GUIDE_DEFAULTS)
        self.assertEqual(editor.window.result, GUIDE_DEFAULTS)
        payload['diamond_tip_y'] = -.2
        self.assertEqual(editor.model.guides['diamond_tip_y'], -.48)
        self.assertEqual(editor.window.result['diamond_tip_y'], -.48)

    def test_invalid_numeric_field_keeps_last_valid_overlay_and_blocks_apply(self):
        editor = _DiamondEditor.__new__(_DiamondEditor)
        editor.model = DiamondGuideModel(GUIDE_DEFAULTS, (300, 180))
        editor._syncing = False
        editor.fields = {name: SimpleNamespace(get=lambda value=value: str(value * 100))
            for name, value in GUIDE_DEFAULTS.items()}
        editor.fields['diamond_center_x'] = SimpleNamespace(get=lambda: '1e308')
        editor.redraw = Mock()
        editor.fields_changed()
        self.assertTrue(editor._field_error)
        self.assertIn('中心', editor._field_error)
        self.assertEqual(editor.model.guides, GUIDE_DEFAULTS)
        editor.redraw.assert_called_once()


if __name__ == '__main__':
    unittest.main(verbosity=2)
