"""Independent whole-volume Diamond geometry, material and regression checks."""
from dataclasses import replace
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from fixture_availability import require_historical_packages

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from spine_turn_core import (TurnOptions,prepare_images,resolve_options,pose_at,
    animation_pose_at,build_skeleton,build_package,validate_diamond_guides,get_diamond_guides)
from spine_turn_preview import render_pose
from test_v14_raised_region import closed_mesh_edge_counts,chunks


def shell(surfaces):
    return [mesh for mesh in surfaces if mesh['kind']=='diamond_face']


def triangle_area(mesh):
    points = chunks(mesh['vertices'],2)
    return sum(abs((points[b][0]-points[a][0])*(points[c][1]-points[a][1])-
                   (points[b][1]-points[a][1])*(points[c][0]-points[a][0]))/2
               for a,b,c in chunks(mesh['triangles'],3))


def volume(surfaces):
    total = 0.
    for mesh in surfaces:
        points = chunks(mesh['model_vertices'],3)
        for indices in chunks(mesh['triangles'],3):
            a,b,c = [points[index] for index in indices]
            total += (a[0]*(b[1]*c[2]-b[2]*c[1])+a[1]*(b[2]*c[0]-b[0]*c[2])+
                      a[2]*(b[0]*c[1]-b[1]*c[0]))/6
    return total


class DiamondModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.asset = ROOT/'assets/demo-diamond.png'
        cls.base = TurnOptions(model='diamond',trim_transparent=False,
            diamond_shine_enabled=False,diamond_sparkles_enabled=False)
        cls.prepared = prepare_images(cls.asset,options=cls.base)
        cls.options = resolve_options(cls.prepared,cls.base)

    def test_profile_validation_rejects_crossed_levels_impossible_widths_and_nonfinite_values(self):
        valid = get_diamond_guides(self.prepared,self.options)
        for change in ({'diamond_table_y':.1},{'diamond_tip_y':.2},
            {'diamond_waist_y':-.49},{'diamond_tip_y':-.5},
            {'diamond_table_width':.98},{'diamond_waist_width':1.01},
            {'diamond_center_x':.1},{'diamond_table_width':0},
            {'diamond_tip_y':math.nan}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                validate_diamond_guides({**valid,**change},384,384)
        for width,height in ((0,384),(384,-1),(math.inf,384)):
            with self.assertRaises(ValueError):
                validate_diamond_guides(valid,width,height)
        for change in ({'diamond_facets':3},{'diamond_facets':17},{'diamond_facets':8.5},
            {'diamond_view_tilt':36},{'diamond_girdle_height':.13},{'diamond_shading':1.01},
            {'diamond_shine_strength':-.1},{'diamond_sparkle_strength':math.inf},
            {'diamond_table_y':.105,'diamond_girdle_height':.015}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                pose_at(0,replace(self.base,**change),384,384)

    def test_whole_shell_has_exactly_two_uses_of_every_edge_and_positive_volume(self):
        for facets in (4,8,13,16):
            for girdle in (0,.015,.06):
                options = replace(self.options,diamond_facets=facets,diamond_girdle_height=girdle)
                surfaces = shell(pose_at(37,options,384,384))
                self.assertEqual(set(closed_mesh_edge_counts(surfaces).values()),{2},(facets,girdle))
                self.assertGreater(volume(surfaces),1e5)
                zones = {mesh['zone'] for mesh in surfaces}
                self.assertTrue({'table','crown','pavilion'}.issubset(zones))
                self.assertEqual('girdle' in zones,girdle>0)
                self.assertFalse(any(mesh['path']=='edge' for mesh in surfaces))

    def test_ninety_degree_views_retain_volume_for_both_axes_and_depth_scales(self):
        for axis in ('x','y'):
            for depth_scale in (.7,1,1.8):
                options = replace(self.options,axis=axis,z_scale=depth_scale)
                initial = shell(pose_at(0,options,384,384))
                turned = shell(pose_at(90,options,384,384))
                self.assertAlmostEqual(volume(initial),volume(turned),places=5)
                initial_area = sum(triangle_area(m) for m in initial if m['visible'])
                turned_area = sum(triangle_area(m) for m in turned if m['visible'])
                self.assertGreater(turned_area,initial_area*.4,(axis,depth_scale))
                self.assertGreater(turned_area,20000)

    def test_normals_are_outward_and_projected_visible_faces_have_consistent_winding(self):
        for axis in ('x','y'):
            for scale in (.65,1.7):
                options = replace(self.options,axis=axis,z_scale=scale)
                for angle in range(0,360,3):
                    for mesh in shell(pose_at(angle,options,384,384)):
                        points = chunks(mesh['model_vertices'],3)
                        center = tuple(sum(p[i] for p in points)/len(points) for i in range(3))
                        self.assertGreater(sum(a*b for a,b in zip(center,mesh['normal'])),0)
                        self.assertAlmostEqual(sum(n*n for n in mesh['normal']),1,places=10)
                        if mesh['visible'] and abs(mesh['facing'])>1e-7:
                            for a,b,c in chunks(mesh['triangles'],3):
                                p,q,r = [chunks(mesh['vertices'],2)[i] for i in (a,b,c)]
                                signed = (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
                                self.assertGreaterEqual(signed,-1e-7,(axis,angle,mesh['name']))

    def test_one_front_source_and_edge_texture_changes_do_not_change_diamond_pixels(self):
        self.assertEqual(self.prepared['front'].tobytes(),Image.open(self.asset).convert('RGBA').tobytes())
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            red,blue = folder/'red.png',folder/'blue.png'
            Image.new('RGBA',(24,12),'#ff0000').save(red)
            Image.new('RGBA',(24,12),'#0000ff').save(blue)
            a = prepare_images(self.asset,None,red,self.options)
            b = prepare_images(self.asset,None,blue,self.options)
            document = build_skeleton(a,self.options)
            paths = {mesh['path'] for entries in document['skins'][0]['attachments'].values()
                     for mesh in entries.values()}
            self.assertTrue(paths.issubset({'front','back'}))
            for angle in (0,47,90,181,269):
                first = render_pose(a,self.options,angle,size=(240,240),background='transparent',show_ground=False)
                second = render_pose(b,self.options,angle,size=(240,240),background='transparent',show_ground=False)
                self.assertEqual(first.tobytes(),second.tobytes())

    def test_effect_toggles_preserve_physical_shell_and_use_generated_normal_blend_materials(self):
        on = replace(self.options,diamond_shine_enabled=True,diamond_sparkles_enabled=True)
        prepared = prepare_images(self.asset,options=on)
        options = resolve_options(prepared,on)
        for angle in (0,33,90,179,270):
            self.assertEqual(shell(pose_at(angle,self.options,384,384)),shell(pose_at(angle,options,384,384)))
        document = build_skeleton(prepared,options)
        paths = {mesh['path'] for entries in document['skins'][0]['attachments'].values()
                 for mesh in entries.values()}
        self.assertEqual(paths,{'front','back','diamond-shine','diamond-sparkle'})
        self.assertTrue(all(slot.get('blend','normal')=='normal' for slot in document['slots']))
        self.assertTrue(all(mesh.get('type')=='mesh' for entries in document['skins'][0]['attachments'].values()
                            for mesh in entries.values()))

    def test_dynamic_culling_changes_only_when_shell_face_projected_area_is_zero(self):
        for axis in ('x','y'):
            options = replace(self.options,axis=axis,z_bounce_enabled=True,peak_z_scale=1.35,
                z_bounce_start=.1,z_bounce_apex=.2,z_bounce_end=.45)
            document = build_skeleton(self.prepared,options)
            for name,animation in document['animations'].items():
                duration = options.duration if name=='rotate_loop' else options.duration/2
                for slot,tracks in animation['slots'].items():
                    for frame in tracks['attachment'][1:]:
                        meshes = {m['name']:m for m in animation_pose_at(frame['time']/duration,
                            options,384,384,name)}
                        self.assertLess(triangle_area(meshes[slot]),.02,(axis,name,slot,frame['time']))

    def test_empty_diamond_mode_preserves_v16_strip_and_ridge_meshes_and_animations(self):
        require_historical_packages(self, [ROOT / 'qa/v1.7' / f'baseline-v1.6-{label}'
                                          for label in ('default-strip', 'ridge')])
        for label in ('default-strip','ridge'):
            folder = ROOT/'qa/v1.7'/f'baseline-v1.6-{label}'
            manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
            options = TurnOptions(**manifest['options'])
            self.assertEqual(options.model,'extrusion')
            previous = next(p for p in folder.glob('*.json') if p.name!='manifest.json')
            old = json.loads(previous.read_text(encoding='utf-8'))
            with tempfile.TemporaryDirectory() as temporary:
                current_path = build_package(folder/'images/front.png',folder/'images/back.png',
                    folder/'images/edge.png',temporary,options)['json_path']
                current = json.loads(Path(current_path).read_text(encoding='utf-8'))
            for section in ('skins','animations','slots','bones'):
                self.assertEqual(old[section],current[section],(label,section))


if __name__=='__main__':
    unittest.main(verbosity=2)
