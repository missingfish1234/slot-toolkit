"""Exportable highlight meshes keep stable topology and stay on their facets."""
from dataclasses import replace
import math
from pathlib import Path
import sys
import unittest

from PIL import ImageChops

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spine_turn_core import TurnOptions, prepare_images, resolve_options, pose_at, animation_pose_at
from spine_turn_diamond_fx import make_effect_textures
from spine_turn_preview import render_pose


def points(values):
    return list(zip(values[::2], values[1::2]))


class DiamondFXTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.options = TurnOptions(model="diamond", trim_transparent=False)
        cls.prepared = prepare_images(ROOT / "assets/demo-diamond.png", options=cls.options)
        cls.options = resolve_options(cls.prepared, cls.options)
        cls.width, cls.height = cls.prepared["width"], cls.prepared["height"]

    def test_effect_mesh_topology_uvs_and_names_are_constant_through_a_turn(self):
        baseline = None
        maximum_sparkle = 0
        for angle in range(0, 361, 3):
            effects = [surface for surface in pose_at(angle, self.options, self.width, self.height)
                       if surface.get("kind") == "diamond_fx"]
            signature = [(surface["name"], surface["path"], surface["uvs"], surface["triangles"],
                          len(surface["vertices"])) for surface in effects]
            if baseline is None:
                baseline = signature
            self.assertEqual(signature, baseline)
            self.assertTrue(all(math.isfinite(value) for surface in effects for value in surface["vertices"]))
            maximum_sparkle = max([maximum_sparkle] + [int(surface["color"][-2:], 16)
                for surface in effects if surface.get("effect") == "sparkle"])
        self.assertGreater(maximum_sparkle, 80)

    def test_light_sweep_vertices_remain_inside_their_visible_source_face(self):
        for angle in range(0, 360, 7):
            surfaces = pose_at(angle, self.options, self.width, self.height)
            lookup = {surface["name"]: surface for surface in surfaces}
            for effect in surfaces:
                if effect.get("effect") != "light_sweep" or not effect["visible"]:
                    continue
                face = lookup[effect["source_face"]]
                hull = points(face["vertices"])[:face["hull"]]
                for point in points(effect["vertices"]):
                    crosses = [(b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0])
                               for a, b in zip(hull, hull[1:] + hull[:1])]
                    self.assertTrue(min(crosses) >= -1e-5 or max(crosses) <= 1e-5)

    def test_zero_strength_matches_disabled_effects_without_changing_the_art(self):
        zero = replace(self.options, diamond_shine_strength=0, diamond_sparkle_strength=0)
        disabled = replace(zero, diamond_shine_enabled=False, diamond_sparkles_enabled=False)
        for angle in (0, 45, 90, 180):
            first = render_pose(self.prepared, zero, angle, size=(256, 256), progress=angle / 360,
                                background="transparent", show_ground=False)
            second = render_pose(self.prepared, disabled, angle, size=(256, 256), progress=angle / 360,
                                 background="transparent", show_ground=False)
            self.assertIsNone(ImageChops.difference(first, second).getbbox())

    def test_generated_textures_need_no_external_images_and_do_not_affect_ordinary_mode(self):
        self.assertFalse(make_effect_textures(TurnOptions()))
        images = make_effect_textures(self.options)
        self.assertEqual(set(images), {"diamond-shine", "diamond-sparkle"})
        alpha = images["diamond-sparkle"].getchannel("A")
        self.assertEqual(alpha.getextrema(), (0, 255))
        self.assertIsNotNone(alpha.getbbox())

    def test_fixed_cells_follow_parent_barycentric_positions_between_keys_in_all_clips(self):
        checked = 0
        for axis in ('x','y'):
            options = replace(self.options,axis=axis,z_bounce_enabled=True,peak_z_scale=1.35,
                z_bounce_start=.1,z_bounce_apex=.2,z_bounce_end=.45)
            for name in ('rotate_loop','flip_to_back','flip_to_front'):
                for index in range(201):
                    surfaces = animation_pose_at(index/200,options,self.width,self.height,name)
                    lookup = {surface['name']:surface for surface in surfaces}
                    for effect in surfaces:
                        if effect.get('effect')!='light_sweep':
                            continue
                        face = lookup[effect['source_face']]
                        if effect['cell_weights'].get('identity'):
                            self.assertEqual(effect['vertices'],face['vertices'])
                            checked += len(effect['vertices'])//2
                            continue
                        count = effect['cell_weights']['centroid_count']
                        hull = points(face['vertices'])[:count]
                        first,second = effect['cell_weights']['edge']
                        center = tuple(sum(point[axis] for point in hull)/count for axis in (0,1))
                        expected = (hull[first],hull[second],center)
                        for actual,wanted in zip(points(effect['vertices']),expected):
                            self.assertLess(math.dist(actual,wanted),1e-8,(axis,name,index,effect['name']))
                            checked += 1
        self.assertGreater(checked,1000)

    def test_assigned_reflection_directions_also_change_their_sweep_brightness(self):
        region= ((-.4,.2),(.4,.2),(.4,.49),(-.4,.49))
        left=replace(self.options,diamond_cut_regions=((region,-30,10),))
        right=replace(self.options,diamond_cut_regions=((region,30,10),))
        differences=[]
        for angle in (60,90,120,240,270):
            first=pose_at(angle,left,self.width,self.height)
            second=pose_at(angle,right,self.width,self.height)
            self.assertEqual([(m['name'],m['vertices']) for m in first],
                             [(m['name'],m['vertices']) for m in second])
            a={m['name']:m for m in first}
            differences.extend(m['color']!=a[m['name']]['color'] for m in second
                if m.get('effect')=='light_sweep')
        self.assertTrue(any(differences))


if __name__ == "__main__":
    unittest.main()
