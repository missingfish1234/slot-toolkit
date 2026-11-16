"""Z spin survives editable projects and both image-rendering paths."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import spine_turn_core as core
from spine_turn_preview import render_pose
from spine_turn_project import load_project, save_project
from spine_turn_sequence import export_sequence


class ZSpinIntegrationTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / "qa/unit-z-spin"
        parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="integration-", dir=parent)
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.front = self.folder / "front.png"
        image = Image.new("RGBA", (160, 48))
        ImageDraw.Draw(image).rectangle((4, 4, 155, 43), fill=(180, 90, 40, 255))
        image.save(self.front)
        image.close()
        self.options = core.TurnOptions(name="z_spin_test", shape="rectangle", duration=.8,
            thickness=10, z_spin_enabled=True, z_spin_direction="clockwise",
            shade_edge=False, shade_faces=False)

    def prepared(self, options=None):
        return core.prepare_images(self.front, None, None, options or self.options)

    def test_saved_project_retains_independent_spin_fields_and_original_art(self):
        path = self.folder / "editable.spturn"
        options = replace(self.options, z_spin_direction="counterclockwise",
                          z_spin_start=.125, z_spin_end=.875,
                          bounce_enabled=True, bounce_height=40,
                          z_bounce_enabled=True, z_bounce_depth=120)
        save_project(path, {"front": str(self.front), "back": None, "edge": None}, options,
                     {"animation": "flip_to_front", "progress": .3125, "playing": False})
        loaded = load_project(path)
        try:
            self.assertTrue(loaded.options.z_spin_enabled)
            self.assertEqual(loaded.options.z_spin_direction, "counterclockwise")
            self.assertEqual((loaded.options.z_spin_start, loaded.options.z_spin_end), (.125, .875))
            self.assertEqual((loaded.options.bounce_height, loaded.options.z_bounce_depth), (40, 120))
            self.assertEqual(loaded.ui_state["animation"], "flip_to_front")
            self.assertEqual(Path(loaded.paths["front"]).read_bytes(), self.front.read_bytes())
            self.assertIsNone(loaded.paths["back"])
            self.assertIsNone(loaded.paths["edge"])
        finally:
            loaded.close()

    def test_existing_editable_project_defaults_to_spin_disabled(self):
        path = ROOT / "examples/irregular-v1.10/irregular.spturn"
        loaded = load_project(path)
        try:
            self.assertFalse(loaded.options.z_spin_enabled)
            self.assertEqual((loaded.options.z_spin_start, loaded.options.z_spin_end), (0, 1))
        finally:
            loaded.close()

    def test_reference_and_fast_rasterizers_apply_the_same_quarter_spin(self):
        prepared = self.prepared()
        camera = {"scale": .5, "origin_x": 64, "origin_y": 64}
        bounds = {}
        for mode in ("reference", "fast"):
            for enabled in (False, True):
                options = replace(self.options, z_spin_enabled=enabled)
                frame = render_pose(prepared, options, 45, (128, 128), "transparent",
                    progress=.25, animation_name="flip_to_back", show_ground=False,
                    camera=camera, raster_mode=mode)
                try:
                    box = frame.getchannel("A").getbbox()
                    self.assertIsNotNone(box)
                    bounds[mode, enabled] = (box[2] - box[0], box[3] - box[1])
                finally:
                    frame.close()
            wide, tall = bounds[mode, False], bounds[mode, True]
            self.assertGreater(wide[0], wide[1] * 1.5, bounds)
            self.assertGreater(tall[1], tall[0] * 1.5, bounds)
        for enabled in (False, True):
            self.assertLessEqual(max(abs(a - b) for a, b in zip(
                bounds["reference", enabled], bounds["fast", enabled])), 2, bounds)

    def test_png_sequence_keeps_non_square_rotating_art_inside_one_fixed_canvas(self):
        options = replace(self.options, z_spin_start=.1, z_spin_end=.9,
                          z_bounce_enabled=True, z_bounce_depth=100)
        destination = self.folder / "frames"
        result = export_sequence(self.prepared(options), options, destination,
                                 animation_name="flip_to_back", fps=10,
                                 size=(128, 128), padding=.12)
        self.assertEqual(result["status"], "complete")
        manifest = json.loads((destination / "sequence.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["canvas"], [128, 128])
        self.assertTrue(manifest["options"]["z_spin_enabled"])
        self.assertEqual(manifest["options"]["z_spin_start"], .1)
        self.assertTrue(manifest["endpoint_included"])
        self.assertEqual(manifest["world_pivot"], [0, 0])
        self.assertEqual(len(manifest["files"]), 5)
        for filename in manifest["files"]:
            with Image.open(destination / filename) as frame:
                self.assertEqual(frame.mode, "RGBA")
                box = frame.getchannel("A").getbbox()
                self.assertIsNotNone(box, filename)
                self.assertGreaterEqual(min(box[:2]), 12, (filename, box))
                self.assertLessEqual(max(box[2:]), 116, (filename, box))


if __name__ == "__main__":
    unittest.main(verbosity=2)
