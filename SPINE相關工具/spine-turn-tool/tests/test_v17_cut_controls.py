import math
import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from spine_turn_core import TurnOptions, pose_at
from spine_turn_diamond_cuts import reflection_normal


class TableReflectionControlsTests(unittest.TestCase):
    def test_table_yaw_alone_moves_reflection_left_and_right(self):
        positive = reflection_normal((0, 1, 0), 35, 0)
        negative = reflection_normal((0, 1, 0), -35, 0)
        self.assertGreater(positive[0], .5)
        self.assertLess(negative[0], -.5)
        self.assertAlmostEqual(positive[1], negative[1])
        self.assertAlmostEqual(sum(value * value for value in positive), 1)
        self.assertAlmostEqual(sum(value * value for value in negative), 1)

    def test_top_cut_shading_changes_but_geometry_uvs_and_culling_do_not(self):
        points = ((-.28, .25), (.28, .25), (.28, .47), (-.28, .47))
        options = TurnOptions(model="diamond", diamond_shine_enabled=False, diamond_sparkles_enabled=False,
                              diamond_cut_regions=((points, 35, 0),))
        left = pose_at(0, options, 320, 320)
        right = pose_at(0, replace(options, diamond_cut_regions=((points, -35, 0),)), 320, 320)
        self.assertEqual(len(left), len(right))
        changed = 0
        for a, b in zip(left, right):
            for key in ("name", "vertices", "uvs", "triangles", "model_vertices", "normal", "view_normal", "visible"):
                self.assertEqual(a[key], b[key], key)
            if a["zone"] == "table" and a["cut_region"] == 0:
                changed += a["color"] != b["color"]
        self.assertGreater(changed, 0)


if __name__ == "__main__":
    unittest.main()
