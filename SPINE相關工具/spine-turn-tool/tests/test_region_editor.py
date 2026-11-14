"""Coordinate correctness and local edit/history behavior, without a display."""
from pathlib import Path
import sys
import math
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spine_turn_region_editor import CanvasTransform, RaisedRegionModel, validate_height_percent

OUTER = ((-.5, -.5), (.5, -.5), (.5, .5), (-.5, .5))
AUTO = ((-.35, -.35), (.35, -.35), (.35, .35), (-.35, .35))
MANUAL = ((-.2, -.2), (.25, -.2), (.25, .3), (-.2, .3))


class RegionEditorModelTests(unittest.TestCase):
    def test_canvas_round_trip_preserves_non_square_world_up_coordinates(self):
        transform = CanvasTransform(300, 150, 800, 500, zoom=1.7, pan_x=32, pan_y=-18)
        for point in [(-.5, .5), (0, 0), (.125, -.3), (.5, -.5)]:
            actual = transform.to_normalized(transform.to_canvas(point))
            self.assertAlmostEqual(point[0], actual[0])
            self.assertAlmostEqual(point[1], actual[1])
        self.assertEqual(transform.to_canvas((0, 0)), (432, 232))
        self.assertLess(transform.to_canvas((0, .2))[1], transform.to_canvas((0, 0))[1])
        self.assertEqual(transform.to_normalized((-1e5, 1e5), clamp=True), (-.5, -.5))

    def test_draw_clockwise_then_close_adopts_valid_ccw_region(self):
        model = RaisedRegionModel(OUTER, (), (300, 150), auto_points=AUTO)
        for point in [(-.2, .2), (.2, .2), (.2, -.2), (-.2, -.2)]:
            model.add_point(point)
        self.assertFalse(model.closed)
        result = model.close()
        self.assertTrue(model.closed)
        self.assertEqual(set(result), {(-.2, .2), (.2, .2), (.2, -.2), (-.2, -.2)})
        area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(result, result[1:] + result[:1]))
        self.assertGreater(area, 0)

    def test_invalid_concave_region_stays_editable_and_does_not_commit_close(self):
        model = RaisedRegionModel(OUTER, (), (300, 150))
        for point in [(-.3, -.3), (.3, -.3), (0, 0), (.3, .3), (-.3, .3)]:
            model.add_point(point)
        before = model.points
        with self.assertRaises(ValueError):
            model.close()
        self.assertFalse(model.closed)
        self.assertEqual(model.points, before)
        with self.assertRaises(ValueError):
            RaisedRegionModel(OUTER, OUTER, (300, 150)).validate()

    def test_drag_is_one_undo_step_and_redo_branch_is_discarded_after_new_edit(self):
        model = RaisedRegionModel(OUTER, MANUAL, (300, 150))
        model.begin_drag(0)
        for point in [(-.21, -.21), (-.22, -.22), (-.24, -.24)]:
            model.move_point(0, point, record=False)
        model.end_drag()
        self.assertEqual(model.points[0], (-.24, -.24))
        model.undo()
        self.assertEqual(model.points, MANUAL)
        self.assertFalse(model.can_undo)
        self.assertTrue(model.can_redo)
        model.redo()
        self.assertEqual(model.points[0], (-.24, -.24))
        model.undo()
        model.move_point(1, (.27, -.2))
        self.assertFalse(model.can_redo)

    def test_insert_delete_clear_and_restore_auto_preserve_distinct_initial_state(self):
        original = [list(point) for point in MANUAL]
        model = RaisedRegionModel(OUTER, original, (300, 150), auto_points=AUTO)
        model.insert_on_edge(0)
        self.assertEqual(len(model.points), 5)
        self.assertAlmostEqual(model.points[1][0], .025)
        self.assertEqual(model.points[1][1], -.2)
        model.delete_point(1)
        self.assertEqual(model.points, MANUAL)
        model.clear()
        self.assertFalse(model.closed)
        self.assertEqual(model.points, ())
        model.undo()
        self.assertEqual(model.points, MANUAL)
        model.reset_auto()
        self.assertEqual(model.points, AUTO)
        self.assertEqual(model.initial, MANUAL)
        self.assertEqual(original, [list(point) for point in MANUAL])

    def test_minimum_maximum_and_duplicate_points_are_rejected_without_mutation(self):
        triangle = ((-.2, -.2), (.2, -.2), (0, .2))
        model = RaisedRegionModel(OUTER, triangle, (300, 150))
        with self.assertRaises(ValueError):
            model.delete_point(0)
        self.assertEqual(model.points, triangle)
        model.clear()
        model.add_point((0, 0))
        with self.assertRaises(ValueError):
            model.add_point((0, 0))
        with self.assertRaises(ValueError):
            model.add_point((.6, 0))
        self.assertEqual(model.points, ((0., 0.),))
        model.clear()
        for index in range(32):
            angle = index * 2 * math.pi / 32
            model.add_point((.3 * math.cos(angle), .3 * math.sin(angle)))
        with self.assertRaises(ValueError):
            model.add_point((.1, .1))
        self.assertEqual(len(model.points), 32)

    def test_height_limits_reject_nonfinite_and_non_numeric_input(self):
        self.assertEqual(validate_height_percent('0'), 0)
        self.assertEqual(validate_height_percent(45), 45)
        self.assertEqual(validate_height_percent('25.5'), 25.5)
        for value in ['nan', float('inf'), -1, 46, 'letters']:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, '凸起高度'):
                validate_height_percent(value)


if __name__ == '__main__':
    unittest.main(verbosity=2)
