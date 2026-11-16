"""The additional object-local Z turn composes with existing editable motion."""
from dataclasses import replace
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import spine_turn_core as core


class ZSpinCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.images = core.prepare_images(ROOT / "assets/demo-front.png", ROOT / "assets/demo-back.png",
                                        ROOT / "assets/demo-edge.png", core.TurnOptions())

    def test_new_settings_reject_ambiguous_flags_invalid_direction_and_timing(self):
        for changes in (
                {"z_spin_enabled": 1}, {"z_spin_enabled": "false"},
                {"z_spin_direction": "left"}, {"z_spin_direction": None},
                {"z_spin_start": True}, {"z_spin_end": False},
                {"z_spin_start": math.nan}, {"z_spin_end": math.inf},
                {"z_spin_start": -.01}, {"z_spin_end": 1.01},
                {"z_spin_start": .8, "z_spin_end": .8},
                {"z_spin_start": .9, "z_spin_end": .8}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                core.normalize_options(replace(core.TurnOptions(), **changes))

    def test_clockwise_and_counterclockwise_make_one_turn_with_window_holds(self):
        for direction, sign in (("clockwise", -1), ("counterclockwise", 1)):
            options = core.TurnOptions(z_spin_enabled=True, z_spin_direction=direction,
                                       z_spin_start=.2, z_spin_end=.8)
            for progress, turns in ((-.1, 0), (0, 0), (.2, 0), (.35, .25),
                                    (.5, .5), (.65, .75), (.8, 1), (1, 1), (2, 1)):
                self.assertAlmostEqual(core.z_spin_angle(progress, options), sign * 360 * turns)
        self.assertEqual(core.z_spin_key_progress(core.TurnOptions()), ())
        self.assertEqual(core.z_spin_angle(.5, core.TurnOptions()), 0)
        with self.assertRaises(ValueError):
            core.z_spin_angle(math.nan)

    def test_rotation_is_local_before_squash_and_does_not_rotate_bounce_translation(self):
        options = core.TurnOptions(z_spin_enabled=True, z_spin_direction="counterclockwise")
        movement = {"scale_x": 2, "scale_y": 3, "x": 7, "y": 13}
        actual = core.transform_vertices_for_motion([2, 1, 0, 0], movement, .25, options)
        for value, expected in zip(actual, (5, 19, 7, 13)):
            self.assertAlmostEqual(value, expected)
        for progress in (0, .13, .25, .51, .75, 1):
            self.assertEqual(core.transform_vertices_for_motion([0, 0], movement, progress, options), [7, 13])

    def test_disabled_and_complete_turn_have_identical_transform_arithmetic(self):
        vertices = [.1, 12.345, -3.25, -.2]
        movement = {"scale_x": 1.1234567, "scale_y": .9876543, "x": 0, "y": 31.274}
        expected = [value for index in range(0, len(vertices), 2)
                    for value in (vertices[index] * movement["scale_x"] + movement["x"],
                                  vertices[index + 1] * movement["scale_y"] + movement["y"])]
        self.assertEqual(core.transform_vertices_for_motion(vertices, movement, .35, core.TurnOptions()), expected)
        for direction in ("clockwise", "counterclockwise"):
            options = core.TurnOptions(z_spin_enabled=True, z_spin_direction=direction)
            self.assertEqual(core.transform_vertices_for_motion(vertices, movement, 0, options), expected)
            self.assertEqual(core.transform_vertices_for_motion(vertices, movement, 1, options), expected)

    def test_disabled_settings_do_not_add_bones_or_change_any_existing_track(self):
        base = core.TurnOptions()
        expected = core.build_skeleton(self.images, base)
        actual = core.build_skeleton(self.images, replace(base, z_spin_direction="counterclockwise",
                                                         z_spin_start=.2, z_spin_end=.8))
        self.assertEqual(actual, expected)
        self.assertNotIn("spin", {bone["name"] for bone in actual["bones"]})

    def test_all_three_families_export_one_turn_in_every_clip_with_quarter_keys(self):
        for version in ("3.8.99", "4.0.56", "4.2.43"):
            options = core.TurnOptions(spine_version=version, z_spin_enabled=True,
                                       z_spin_start=.2, z_spin_end=.8)
            skeleton = core.build_skeleton(self.images, options)
            self.assertEqual(skeleton["bones"], [{"name": "root"}, {"name": "turn", "parent": "root"},
                                                {"name": "spin", "parent": "turn"}])
            self.assertTrue(all(slot["bone"] == "spin" for slot in skeleton["slots"]))
            field = "angle" if version.startswith("3.8") else "value"
            for name, animation in skeleton["animations"].items():
                duration = options.duration if name == "rotate_loop" else options.duration / 2
                frames = animation["bones"]["spin"]["rotate"]
                self.assertEqual(len(frames), 7)
                self.assertEqual([frame[field] for frame in frames], [0, 0, -90, -180, -270, -360, -360])
                self.assertEqual(frames[0]["time"], 0)
                self.assertEqual(frames[-1]["time"], duration)
                self.assertTrue(all(a["time"] < b["time"] for a, b in zip(frames, frames[1:])))

    def test_spin_child_keeps_existing_parent_motion_and_deforms_unchanged(self):
        base = core.TurnOptions(bounce_enabled=True, z_bounce_enabled=True, z_offset=75,
                                coin_shine_enabled=True)
        images = core.prepare_images(ROOT / "assets/demo-front.png", ROOT / "assets/demo-back.png",
                                     ROOT / "assets/demo-edge.png", base)
        plain = core.build_skeleton(images, base)
        spun = core.build_skeleton(images, replace(base, z_spin_enabled=True))
        self.assertEqual(spun["bones"][-1], {"name": "spin", "parent": "depth"})
        self.assertEqual(spun["skins"], plain["skins"])
        for name, animation in plain["animations"].items():
            copy = dict(spun["animations"][name])
            bones = dict(copy["bones"])
            self.assertIn("spin", bones)
            bones.pop("spin")
            copy["bones"] = bones
            self.assertEqual(copy, animation)

    def test_metadata_bounds_cover_long_object_rotated_with_independent_motion(self):
        options = core.TurnOptions(z_spin_enabled=True, width=1200, height=90,
            thickness=44, bounce_enabled=True, bounce_height=130, peak_scale=1.4,
            z_bounce_enabled=True, z_bounce_depth=250, peak_z_scale=2, z_offset=50)
        images = core.prepare_images(ROOT / "assets/demo-front.png", None, None, options)
        skeleton = core.build_skeleton(images, options)
        box = skeleton["skeleton"]
        right, top = box["x"] + box["width"], box["y"] + box["height"]
        for name in skeleton["animations"]:
            for progress in (index / 80 for index in range(81)):
                movement = core.motion_at(progress, options, images["height"])
                for surface in core.animation_pose_at(progress, options, images["width"], images["height"], name):
                    vertices = core.transform_vertices_for_motion(surface["vertices"], movement, progress, options)
                    for x, y in zip(vertices[::2], vertices[1::2]):
                        self.assertLessEqual(box["x"] - 1e-5, x)
                        self.assertLessEqual(x, right + 1e-5)
                        self.assertLessEqual(box["y"] - 1e-5, y)
                        self.assertLessEqual(y, top + 1e-5)

    def test_too_short_export_window_stops_instead_of_dropping_rotation_keys(self):
        options = core.TurnOptions(z_spin_enabled=True, z_spin_start=.5, z_spin_end=.5000000001)
        with self.assertRaisesRegex(ValueError, "旋轉時間過短"):
            core.build_skeleton(self.images, options)


if __name__ == "__main__":
    unittest.main()
