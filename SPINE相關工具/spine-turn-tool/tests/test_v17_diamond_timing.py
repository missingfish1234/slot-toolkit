import sys
import copy
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import spine_turn_core as core


class DiamondExportTimingTests(unittest.TestCase):
    def options(self, duration=2.0):
        return core.TurnOptions(model="diamond", duration=duration,
                                diamond_shine_enabled=False, diamond_sparkles_enabled=False)

    def test_measured_nearby_fx_root_uses_exported_float32_time_not_raw_angle(self):
        # Values measured from the official runtime failure, not computed by
        # the helper. The sample is just BEFORE the Float32 culling event.
        root = 122.99700038370615
        event_time = 0.683316707611084
        sample_time = 0.6833167
        anchors = {0: 0.0, root: 100.0, 123: 300.0, 360: 300.0}

        def pose(angle, *_):
            value = anchors[angle]
            return [{"name": "fx", "vertices": [value, 0], "color": "ffffffff" if angle == 0 else "ffffff00",
                     "visible": angle == 0}]

        with patch.object(core, "_animation_angles", return_value=[0, root, 123, 360]), \
                patch.object(core, "_animation_projection", side_effect=pose):
            surface = core.animation_pose_at(sample_time / 2, self.options())[0]
            self.assertAlmostEqual(surface["vertices"][0], 100 * sample_time / event_time, places=10)
            self.assertTrue(surface["visible"])
            self.assertAlmostEqual(surface["tint"][3], 1 - sample_time / event_time, places=14)
            at_event = core.animation_pose_at(event_time / 2, self.options())[0]
            self.assertEqual(at_event["vertices"][0], 100)
            self.assertFalse(at_event["visible"])

    def test_same_export_time_uses_last_key_at_exact_event(self):
        angles = [0, 10.000000001, 10.000000002, 360]
        # Both small-angle keys export to this same Float32 time.
        event_time = 0.05555560067296028
        anchors = dict(zip(angles, [0, 100, 200, 300]))
        with patch.object(core, "_animation_angles", return_value=angles), \
                patch.object(core, "_animation_projection", side_effect=lambda angle, *_: [
                    {"vertices": [anchors[angle], 0], "color": "ffffffff", "visible": True}]):
            surface = core.animation_pose_at(event_time / 2, self.options())[0]
            self.assertEqual(surface["vertices"][0], 200)

    def test_native40_power_of_two_fps_is_diamond_only_and_preserves_events(self):
        # This measured key suffered a one-ULP native4.0 frame/time round trip
        # at30FPS;32FPS preserves Float32 time through an exponent-only shift.
        source = {"skeleton": {"spine": "4.0.56", "fps": 30}, "animations": {"a": {
            "slots": {"fx": {"attachment": [{"time": 0}, {"time": 1.5666833}, {"time": 2}]}}}}}
        with patch.object(core, "_build_canonical_skeleton", side_effect=lambda *_: copy.deepcopy(source)):
            diamond = core.build_skeleton({}, self.options())
            badge = core.build_skeleton({}, core.TurnOptions())
        self.assertEqual(diamond["skeleton"]["fps"], 32)
        self.assertEqual(diamond["animations"], source["animations"])
        self.assertEqual(badge, source)


if __name__ == "__main__":
    unittest.main()
