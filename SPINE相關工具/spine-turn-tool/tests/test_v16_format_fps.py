import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from spine_turn_formats import animation_key_times, convert_skeleton, select_native_safe_fps, select_native_safe_fps_38


class LegacyNativeTimingTests(unittest.TestCase):
    def scene(self):
        # Measured real facet-visibility key: importing at30FPS snapped this
        # to1.4s in native3.8/4.2 and displaced geometry by0.121pixels.
        return {
            "skeleton": {"spine": "4.0.56", "fps": 30},
            "animations": {
                "rotate_loop": {
                    "deform": {"default": {"surface": {"surface": [
                        {"time": 0, "vertices": [0, 0]},
                        {"time": 1.3997369, "vertices": [7, 11]},
                        {"time": 2, "vertices": [0, 0]},
                    ]}}},
                    "slots": {"surface": {"attachment": [
                        {"time": 0, "name": None}, {"time": 1.3997369, "name": "surface"},
                    ]}},
                },
            },
        }

    def test_actual_native_collision_selects60_without_moving_geometry_or_events(self):
        source = self.scene()
        untouched = copy.deepcopy(source)
        target = convert_skeleton(source, "3.8.99")
        self.assertEqual(target["skeleton"]["fps"], 60)
        self.assertEqual(target["animations"], source["animations"])
        self.assertEqual(animation_key_times(target), animation_key_times(source))
        self.assertEqual(source, untouched)

    def test_all_clips_and_timeline_types_are_checked(self):
        source = self.scene()
        # This second clip/color key is unsafe at30 and60, but safe at120.
        source["animations"]["flip_to_back"] = {"slots": {"surface": {"rgba": [
            {"time": 0.6001, "color": "808080ff"},
        ]}}}
        target = convert_skeleton(source, "3.8")
        self.assertEqual(target["skeleton"]["fps"], 120)
        self.assertEqual(animation_key_times(target), animation_key_times(source))

    def test_float_noise_on_exact_frames_keeps30(self):
        source = {"animations": {"idle": {"bones": {"root": {"translate": [
            {"time": 0.1666667, "x": 0, "y": 0}, {"time": 0.5, "x": 0, "y": 0},
        ]}}}}}
        self.assertEqual(select_native_safe_fps_38(source), 30)

    def test_default40_retains_original_fps_and_key_times(self):
        source = self.scene()
        target = convert_skeleton(source, "4.0.56")
        self.assertIs(target, source)
        self.assertEqual(target["skeleton"]["fps"], 30)
        self.assertEqual(animation_key_times(target), animation_key_times(source))

    def test_confirmed42_native_collision_changes_only_fps_and_schema_nesting(self):
        source = self.scene()
        untouched = copy.deepcopy(source)
        target = convert_skeleton(source, "4.2.43")
        self.assertEqual(target["skeleton"]["fps"], 60)
        self.assertEqual(animation_key_times(target), animation_key_times(source))
        original = source["animations"]["rotate_loop"]
        converted = target["animations"]["rotate_loop"]
        self.assertEqual(converted["slots"], original["slots"])
        self.assertEqual(converted["attachments"]["default"]["surface"]["surface"]["deform"],
                         original["deform"]["default"]["surface"]["surface"])
        self.assertEqual(source, untouched)

    def test_no_safe_fps_reports_instead_of_silently_snapping(self):
        source = {"animations": {"a": {"slots": {"s": {"attachment": [{"time": 0.00001}]}}}}}
        with self.assertRaisesRegex(ValueError, "3.8"):
            select_native_safe_fps_38(source)
        with self.assertRaisesRegex(ValueError, "4.2"):
            select_native_safe_fps(source, "4.2.43")


if __name__ == "__main__":
    unittest.main()
