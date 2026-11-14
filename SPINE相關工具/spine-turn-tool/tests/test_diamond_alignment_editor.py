"""Actual projected-cage alignment, local history and Apply/Cancel contracts."""
from dataclasses import asdict
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spine_turn_core import TurnOptions
from spine_turn_diamond_alignment_editor import ALIGNMENT_DEFAULTS, DiamondAlignmentModel, _AlignmentEditor
from spine_turn_diamond import project_vertex


class DiamondAlignmentEditorTests(unittest.TestCase):
    def model(self, **values):
        options = asdict(TurnOptions(model='diamond', trim_transparent=False))
        options.update(values)
        return DiamondAlignmentModel(options, (466, 368)), options

    def test_wire_nodes_are_the_same_projected_physical_points_as_core_on_non_square_image(self):
        model, _ = self.model()
        wire = model.alignment
        self.assertGreater(len(wire['nodes']), 16)
        self.assertGreater(len(wire['edges']), 16)
        for node in wire['nodes'].values():
            x, y, z = node['xyz']
            expected = project_vertex((x, y, z), 0, 'y', model.values['diamond_view_tilt'])
            self.assertAlmostEqual(node['point'][0], expected[0] / 466, places=8)
            self.assertAlmostEqual(node['point'][1], expected[1] / 368, places=8)
        self.assertTrue(any(edge['visible'] for edge in wire['edges']))
        self.assertTrue(any(not edge['visible'] for edge in wire['edges']))
        for edge in wire['edges']:
            self.assertIn(edge['a'], wire['nodes'])
            self.assertIn(edge['b'], wire['nodes'])

    def test_front_table_drag_preserves_opposite_projected_edge_and_other_ring(self):
        model, source = self.model()
        before = dict(model.values)
        back = model.handles()['table_back']['point']
        waist = model.handles()['waist_front']['point']
        front = model.handles()['table_front']['point']
        model.drag('table_front', (front[0], front[1] - .025), record=True)
        self.assertAlmostEqual(model.handles()['table_back']['point'][1], back[1], places=8)
        self.assertAlmostEqual(model.handles()['table_front']['point'][1], front[1] - .025, places=8)
        self.assertEqual(model.handles()['waist_front']['point'], waist)
        self.assertNotEqual(model.values['diamond_table_y'], before['diamond_table_y'])
        self.assertGreater(model.values['diamond_table_depth'], 0)
        self.assertEqual(source['diamond_table_depth'], 0)
        self.assertEqual(source['diamond_table_y'], before['diamond_table_y'])

    def test_back_waist_drag_preserves_front_rim_and_width_handles_use_real_extrema(self):
        model, _ = self.model()
        front = model.handles()['waist_front']['point']
        back = model.handles()['waist_back']['point']
        model.drag('waist_back', (back[0], back[1] + .02), record=True)
        self.assertAlmostEqual(model.handles()['waist_front']['point'][1], front[1], places=8)
        self.assertAlmostEqual(model.handles()['waist_back']['point'][1], back[1] + .02, places=8)
        left = model.handles()['table_left']['point']
        old_width = model.values['diamond_table_width']
        model.drag('table_left', (left[0] - .02, left[1]), record=True)
        self.assertGreater(model.values['diamond_table_width'], old_width)
        left = model.handles()['table_left']['point']
        right = model.handles()['table_right']['point']
        self.assertAlmostEqual((right[0] + left[0]) / 2, model.values['diamond_center_x'], places=8)

    def test_tip_is_actual_projected_point_and_drag_is_not_a_material_normal_edit(self):
        model, _ = self.model()
        tip = model.handles()['tip']['point']
        model.drag('tip', (tip[0], -.43), record=True)
        self.assertAlmostEqual(model.handles()['tip']['point'][1], -.43, places=8)
        self.assertAlmostEqual(model.values['diamond_tip_y'], -.43, places=8)
        self.assertNotIn('diamond_cut_regions', model.validate())

    def test_drag_history_coalesces_and_presets_are_explicit_local_changes(self):
        model, source = self.model()
        initial = dict(model.values)
        self.assertEqual(model.values['diamond_ring_phase'], 0)
        front = model.handles()['table_front']['point']
        for amount in (.01, .02, .03):
            model.drag('table_front', (front[0], front[1] - amount))
        model.commit()
        final = dict(model.values)
        model.undo()
        self.assertEqual(model.values, initial)
        self.assertFalse(model.can_undo)
        model.redo()
        self.assertEqual(model.values, final)
        model.undo()
        model.preset('facet')
        self.assertAlmostEqual(model.values['diamond_ring_phase'], 180 / source['diamond_facets'])
        self.assertFalse(model.can_redo)
        self.assertEqual(source['diamond_ring_phase'], 0)
        model.reset()
        self.assertEqual(model.values, initial)

    def test_old_zero_tilt_and_auto_depth_open_validate_apply_and_cancel_without_silent_change(self):
        model, source = self.model(diamond_view_tilt=0.)
        self.assertEqual(model.values['diamond_view_tilt'], 0.)
        self.assertEqual(model.values['diamond_table_depth'], 0.)
        self.assertEqual(model.values['diamond_waist_depth'], 0.)
        self.assertEqual(model.values['diamond_ring_phase'], 0.)
        self.assertEqual(model.validate(), {name: source.get(name, default) for name, default in ALIGNMENT_DEFAULTS.items()})
        before = dict(model.values)
        with self.assertRaises(ValueError):
            model.drag('table_front', (0, .2))
        self.assertEqual(model.values, before)
        editor = _AlignmentEditor.__new__(_AlignmentEditor)
        editor.model, editor.callback = model, Mock()
        editor.window = SimpleNamespace(result=None)
        editor._destroy = Mock()
        editor.field_error = ''
        editor.refresh = Mock()
        editor.cancel()
        editor.callback.assert_not_called()
        self.assertIsNone(editor.window.result)
        editor.apply()
        editor.callback.assert_called_once_with(before)
        self.assertEqual(editor.window.result, before)
        self.assertEqual(source['diamond_view_tilt'], 0.)

    def test_invalid_numbers_and_geometry_leave_previous_actual_wire_unchanged(self):
        model, _ = self.model()
        before, wire = dict(model.values), model.alignment
        for change in ({'diamond_table_depth': 2.01}, {'diamond_view_tilt': 36},
                       {'diamond_table_y': -.4}, {'diamond_ring_phase': float('nan')}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                model.set_values(change)
            self.assertEqual(model.values, before)
            self.assertIs(model.alignment, wire)

    def test_invalid_numeric_field_cannot_apply_and_success_returns_independent_snapshot(self):
        model, _ = self.model()
        editor = _AlignmentEditor.__new__(_AlignmentEditor)
        editor.model, editor.callback = model, Mock()
        editor._syncing = False
        editor.fields = {name: SimpleNamespace(get=lambda value=value, name=name:
            str(value * (1 if name in ('diamond_view_tilt', 'diamond_ring_phase') else 100)))
            for name, value in model.values.items()}
        editor.fields['diamond_waist_depth'] = SimpleNamespace(get=lambda: 'NaN')
        editor.error_text = SimpleNamespace(set=Mock())
        editor.apply_button = Mock()
        editor.redraw = Mock()
        editor.fields_changed()
        self.assertTrue(editor.field_error)
        editor.apply()
        editor.callback.assert_not_called()
        editor.field_error = ''
        editor.window = SimpleNamespace(result=None)
        editor._destroy = Mock()
        editor.apply()
        payload = editor.callback.call_args.args[0]
        payload['diamond_view_tilt'] = 33
        self.assertEqual(model.values['diamond_view_tilt'], 12)
        self.assertEqual(editor.window.result['diamond_view_tilt'], 12)

    def test_nonunit_static_z_scale_is_in_wire_and_inverse_preserves_opposite_rim(self):
        model, _ = self.model(z_scale=1.3, diamond_ring_phase=22.5,
                             diamond_table_depth=.6, diamond_waist_depth=1.1)
        for node in model.alignment['nodes'].values():
            expected = project_vertex(node['xyz'], 0, 'y', model.values['diamond_view_tilt'])
            self.assertAlmostEqual(node['point'][0], expected[0] / 466, places=8)
            self.assertAlmostEqual(node['point'][1], expected[1] / 368, places=8)
        opposite = model.handles()['table_back']['point']
        front = model.handles()['table_front']['point']
        model.drag('table_front', (front[0], front[1] - .03), record=True)
        self.assertAlmostEqual(model.handles()['table_front']['point'][1], front[1] - .03, places=8)
        self.assertAlmostEqual(model.handles()['table_back']['point'][1], opposite[1], places=8)

    def test_waist_handles_lie_on_actual_upper_cut_rim_not_band_center(self):
        model, _ = self.model(diamond_girdle_height=.08, diamond_ring_phase=22.5)
        top_y = (model.values['diamond_waist_y'] + .04) * 368 / math.cos(math.radians(model.values['diamond_view_tilt']))
        for name in ('waist_front', 'waist_back', 'waist_left', 'waist_right'):
            handle = model.handles()[name]
            self.assertAlmostEqual(handle['xyz'][1], top_y, places=8)
            projected = project_vertex(handle['xyz'], 0, 'y', model.values['diamond_view_tilt'])
            self.assertAlmostEqual(handle['point'][1], projected[1] / 368, places=8)
        front = model.handles()['waist_front']['point']
        back = model.handles()['waist_back']['point']
        model.drag('waist_front', (front[0], front[1] - .015), record=True)
        self.assertAlmostEqual(model.handles()['waist_back']['point'][1], back[1], places=8)


if __name__ == '__main__':
    unittest.main(verbosity=2)
