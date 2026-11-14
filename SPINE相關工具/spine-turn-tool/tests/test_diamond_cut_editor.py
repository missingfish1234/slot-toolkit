"""Artwork-aligned cut-region editing without a Tk display or user artwork."""
from pathlib import Path
import math
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spine_turn_diamond_cut_editor import DiamondCutModel, _DiamondCutEditor
from spine_turn_region_editor import CanvasTransform

LEFT = (((-.4, -.25), (0., -.25), (0., .25), (-.4, .25)), -15., 0.)
RIGHT = (((0., -.25), (.4, -.25), (.4, .25), (0., .25)), 15., 0.)


class DiamondCutEditorTests(unittest.TestCase):
    def test_draw_closes_canonical_region_and_estimates_direction_from_centroid(self):
        model = DiamondCutModel(drawing_mode='free')
        model.start_drawing()
        # Clockwise input becomes a canonical counterclockwise region.
        for point in ((.1, .3), (.3, .1), (.1, -.1)):
            model.add_point(point)
        result = model.close_draft()
        self.assertEqual(set(result[0]), {(.1, .3), (.3, .1), (.1, -.1)})
        self.assertAlmostEqual(result[1], 10.)
        self.assertAlmostEqual(result[2], 4.)
        self.assertEqual(model.selected, 0)
        self.assertFalse(model.drawing)
        self.assertEqual(model.draft, ())
        self.assertEqual(model.validate(), model.regions)

    def test_shared_edge_nodes_move_together_without_changing_reflection_angles(self):
        model = DiamondCutModel((LEFT, RIGHT))
        original = model.regions
        index = model.regions[0][0].index((0., -.25))
        model.move_vertex(0, index, (.04, -.2))
        self.assertIn((.04, -.2), model.regions[0][0])
        self.assertIn((.04, -.2), model.regions[1][0])
        self.assertNotIn((0., -.25), model.regions[0][0] + model.regions[1][0])
        self.assertEqual(tuple(region[1:] for region in model.regions), tuple(region[1:] for region in original))
        model.validate()

    def test_invalid_move_or_angle_does_not_partially_change_connected_regions(self):
        model = DiamondCutModel((LEFT, RIGHT))
        original = model.regions
        index = model.regions[0][0].index((0., .25))
        with self.assertRaises(ValueError):
            model.move_vertex(0, index, (.49, -.25))
        self.assertEqual(model.regions, original)
        for yaw, pitch in ((61, 0), (0, -61), (float('nan'), 0), ('bad', 0)):
            with self.subTest(yaw=yaw, pitch=pitch), self.assertRaises(ValueError):
                model.set_angles(yaw, pitch)
            self.assertEqual(model.regions, original)

    def test_overlapping_or_concave_draft_stays_open_and_can_be_repaired(self):
        model = DiamondCutModel((LEFT,), drawing_mode='free')
        model.start_drawing()
        for point in ((-.2, -.1), (.2, -.1), (.2, .1), (-.2, .1)):
            model.add_point(point)
        before = model.draft
        with self.assertRaisesRegex(ValueError, '重疊'):
            model.close_draft()
        self.assertEqual(model.regions, (LEFT,))
        self.assertEqual(model.draft, before)
        self.assertTrue(model.drawing)
        model.cancel_draft()
        model.start_drawing()
        for point in ((0., -.2), (.4, -.2), (.1, 0.), (.4, .2), (0., .2)):
            model.add_point(point)
        with self.assertRaisesRegex(ValueError, '凹|交叉'):
            model.close_draft()
        self.assertEqual(len(model.regions), 1)

    def test_draft_cannot_apply_until_closed_and_delete_removes_last_draft_point(self):
        model = DiamondCutModel((LEFT,))
        model.start_drawing()
        model.add_point((.1, -.1))
        model.add_point((.4, -.1))
        with self.assertRaisesRegex(ValueError, '封閉'):
            model.validate()
        with self.assertRaisesRegex(ValueError, '3'):
            model.close_draft()
        model.delete_selected()
        self.assertEqual(model.draft, ((.1, -.1),))
        model.cancel_draft()
        self.assertEqual(model.validate(), (LEFT,))

    def test_bounds_duplicate_points_and_region_limits_are_enforced(self):
        model = DiamondCutModel(drawing_mode='free')
        model.start_drawing()
        model.add_point((0., 0.))
        for point in ((0., 0.), (.501, 0.), (0., float('inf'))):
            with self.subTest(point=point), self.assertRaises(ValueError):
                model.add_point(point)
        self.assertEqual(len(model.draft), 1)
        model.cancel_draft(); model.start_drawing()
        for i in range(12):
            model.add_point((.3 * math.cos(i * math.tau / 12), .3 * math.sin(i * math.tau / 12)))
        with self.assertRaisesRegex(ValueError, '12'):
            model.add_point((.1, .1))
        model.close_draft()
        regions = []
        for row in range(4):
            for column in range(6):
                x, y = -.48 + column * .16, -.48 + row * .24
                regions.append((((x, y), (x + .12, y), (x + .12, y + .18), (x, y + .18)), 0, 0))
        full = DiamondCutModel(regions)
        with self.assertRaisesRegex(ValueError, '24'):
            full.start_drawing()

    def test_snap_distance_is_measured_in_screen_pixels_at_each_zoom(self):
        model = DiamondCutModel((LEFT, RIGHT))
        vertex = (0., .25)
        for zoom in (.7, 2.4):
            transform = CanvasTransform(466, 368, 680, 450, zoom=zoom, pan_x=12, pan_y=-19)
            x, y = transform.to_canvas(vertex)
            near = transform.to_normalized((x + 7, y))
            far = transform.to_normalized((x + 9, y))
            self.assertEqual(model.snap_point(near, transform), vertex)
            self.assertEqual(model.snap_point(far, transform), far)
            self.assertEqual(model.snap_point(near, transform, exclude=vertex), near)

    def test_drag_coalesces_to_one_undo_and_new_edit_discards_redo(self):
        model = DiamondCutModel((LEFT, RIGHT))
        original = model.regions
        index = model.regions[0][0].index((0., -.25))
        for x in (.01, .02, .03):
            model.move_vertex(0, index, (x, -.24), record=False)
        model.commit()
        final = model.regions
        model.undo()
        self.assertEqual(model.regions, original)
        self.assertFalse(model.can_undo)
        self.assertTrue(model.can_redo)
        model.redo()
        self.assertEqual(model.regions, final)
        model.undo()
        model.set_angles(-30, 20)
        self.assertFalse(model.can_redo)

    def test_clear_delete_and_reset_are_undoable_and_input_is_not_mutated(self):
        mutable = [[list(point) for point in LEFT[0]], LEFT[1], LEFT[2]]
        model = DiamondCutModel((mutable, RIGHT))
        model.selected = 1
        model.delete_selected()
        self.assertEqual(model.regions, (LEFT,))
        model.clear()
        self.assertEqual(model.regions, ())
        model.undo()
        self.assertEqual(model.regions, (LEFT,))
        model.reset()
        self.assertEqual(model.regions, (LEFT, RIGHT))
        self.assertEqual(mutable, [[list(point) for point in LEFT[0]], LEFT[1], LEFT[2]])
        self.assertIsInstance(model.regions[0][0], tuple)

    def test_apply_returns_only_valid_local_regions_and_cancel_never_calls_parent(self):
        editor = _DiamondCutEditor.__new__(_DiamondCutEditor)
        editor.model = DiamondCutModel((LEFT, RIGHT))
        editor.callback = Mock()
        editor.window = SimpleNamespace(result=None)
        editor._destroy = Mock()
        editor.commit_angles = Mock()
        editor.refresh = Mock()
        editor.field_error = ''
        editor.cancel()
        editor.callback.assert_not_called()
        self.assertIsNone(editor.window.result)
        editor.model.start_drawing(); editor.model.add_point((.45, .45))
        editor.apply()
        editor.callback.assert_not_called()
        self.assertIn('封閉', editor.error)
        editor.model.cancel_draft()
        editor.apply()
        editor.callback.assert_called_once_with((LEFT, RIGHT))
        self.assertEqual(editor.window.result, (LEFT, RIGHT))

    def test_invalid_numeric_text_keeps_previous_valid_reflection_and_blocks_apply(self):
        editor = _DiamondCutEditor.__new__(_DiamondCutEditor)
        editor.model = DiamondCutModel((LEFT,))
        editor._syncing = False
        editor.yaw = SimpleNamespace(get=lambda: 'nan')
        editor.pitch = SimpleNamespace(get=lambda: '0')
        editor.error_text = SimpleNamespace(set=Mock())
        editor.change_angles()
        self.assertEqual(editor.model.regions, (LEFT,))
        self.assertIn('60', editor.field_error)
        editor.commit_angles = Mock()
        editor.callback = Mock()
        editor.apply()
        editor.callback.assert_not_called()

    def test_typed_reflection_updates_slider_without_programmatic_values_writing_back(self):
        class Variable:
            def __init__(self, value):
                self.value = value
                self.callback = None
            def get(self):
                return self.value
            def set(self, value):
                self.value = value
                if self.callback:
                    self.callback()
        editor = _DiamondCutEditor.__new__(_DiamondCutEditor)
        editor.model = DiamondCutModel((LEFT,))
        editor._syncing = False
        editor.error_text = SimpleNamespace(set=Mock())
        editor.yaw, editor.pitch = Variable('-35'), Variable('10')
        editor.slider_values = (Variable(-15.), Variable(0.))
        for index, variable in enumerate(editor.slider_values):
            variable.callback = lambda index=index: editor.slider_changed(index)
        editor.yaw.callback = editor.pitch.callback = editor.change_angles
        editor.change_angles()
        self.assertEqual(editor.model.regions[0][1:], (-35., 10.))
        self.assertEqual((editor.yaw.get(), editor.pitch.get()), ('-35', '10'))
        self.assertEqual(tuple(variable.get() for variable in editor.slider_values), (-35., 10.))
        # Refreshing the other controls must not overwrite an in-progress field.
        editor._syncing = True
        editor.slider_values[0].set(-15.)
        editor._syncing = False
        self.assertEqual(editor.yaw.get(), '-35')
        # An actual slider edit travels in the opposite direction immediately.
        editor.slider_values[0].set(-22.)
        self.assertEqual(editor.yaw.get(), '-22')
        self.assertEqual(editor.model.regions[0][1:], (-22., 10.))

    def test_default_upper_mode_requires_exactly_four_points_and_auto_closes(self):
        model = DiamondCutModel()
        self.assertEqual(model.drawing_mode, 'upper4')
        self.assertEqual(model.target_count, 4)
        model.start_drawing()
        for point in ((-.3, .05), (.3, .05), (.2, .35)):
            model.add_point(point)
        self.assertEqual(len(model.regions), 0)
        with self.assertRaisesRegex(ValueError, '需要 4'):
            model.close_draft()
        with self.assertRaisesRegex(ValueError, '封閉'):
            model.validate()
        model.add_point((-.2, .35))
        self.assertEqual(len(model.regions[0][0]), 4)
        self.assertFalse(model.drawing)
        self.assertFalse(model.draft)
        self.assertEqual(model.validate(), model.regions)

    def test_lower_mode_auto_closes_three_points_and_existing_other_polygons_are_unchanged(self):
        pentagon = (((-.45, .2), (-.3, .1), (-.2, .2), (-.25, .4), (-.4, .4)), 10, -5)
        model = DiamondCutModel((pentagon,))
        original = model.regions[0]
        model.start_drawing('lower3')
        for point in ((-.2, -.1), (.2, -.1), (0, -.4)):
            model.add_point(point)
        self.assertEqual(len(model.regions), 2)
        self.assertEqual(model.regions[0], original)
        self.assertEqual(len(model.regions[1][0]), 3)
        self.assertFalse(model.drawing)
        model.undo()
        self.assertTrue(model.drawing)
        self.assertEqual(model.drawing_mode, 'lower3')
        self.assertEqual(len(model.draft), 3)
        self.assertEqual(len(model.regions), 1)
        model.redo()
        self.assertEqual(len(model.regions), 2)

    def test_fixed_count_validation_failure_keeps_draft_editable_without_extra_points(self):
        model = DiamondCutModel((LEFT,))
        model.start_drawing('lower3')
        model.add_point((-.3, -.1)); model.add_point((-.1, -.1))
        with self.assertRaisesRegex(ValueError, '重疊'):
            model.add_point((-.2, .15))
        self.assertEqual(len(model.draft), 3)
        self.assertTrue(model.drawing)
        self.assertEqual(model.regions, (LEFT,))
        with self.assertRaisesRegex(ValueError, '已有 3'):
            model.add_point((.4, .4))
        with self.assertRaisesRegex(ValueError, '切換'):
            model.set_drawing_mode('free')
        for index, point in enumerate(((.1, -.1), (.4, -.1), (.25, .2))):
            model.move_draft_vertex(index, point)
        model.close_draft()
        self.assertEqual(len(model.regions), 2)
        self.assertFalse(model.draft)

    def test_free_mode_preserves_manual_three_to_twelve_point_workflow(self):
        model = DiamondCutModel()
        model.start_drawing('free')
        for i in range(5):
            model.add_point((.3 * math.cos(i * math.tau / 5), .3 * math.sin(i * math.tau / 5)))
        self.assertEqual(model.regions, ())
        self.assertEqual(len(model.draft), 5)
        model.close_draft()
        self.assertEqual(len(model.regions[0][0]), 5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
