"""Irregular topology, source-alpha, cache and native timeline contracts."""
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image,ImageDraw,ImageOps

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from spine_turn_core import (TurnOptions,normalize_options,prepare_images,resolve_options,
    pose_at,animation_pose_at,ordered_surfaces,build_skeleton,build_package)
from spine_turn_irregular import irregular_statistics
from spine_turn_formats import SPINE_TARGETS
from spine_turn_preview import render_pose


def fixture():
    image=Image.new('RGBA',(96,96))
    draw=ImageDraw.Draw(image)
    draw.polygon([(5,5),(91,5),(91,91),(65,91),(65,34),(30,34),(30,91),(5,91)],fill=(200,130,40,255))
    draw.rectangle((8,8,22,22),fill=(180,100,30,96))
    draw.rectangle((10,25,20,30),fill=(0,0,0,0))
    return image


class IrregularCoreTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.folder=Path(temporary.name);self.path=self.folder/'shape.png'
        self.image=fixture();self.image.save(self.path)
        self.options=TurnOptions(shape='irregular',trim_transparent=False,outline_tolerance=0)

    def prepared(self,options=None):
        options=options or self.options
        images=prepare_images(self.path,options=options)
        return images,resolve_options(images,options)

    def test_irregular_is_explicit_and_never_normalized_to_convex_ridge(self):
        self.assertEqual(normalize_options(self.options).shape,'irregular')
        for changes in ({'side_mode':'ridge'},{'bevel_width':.07},{'raised_contour_points':((0,0),(.1,0),(0,.1))},
                        {'outline_alpha_threshold':0},{'outline_alpha_threshold':256},{'outline_alpha_threshold':2.5},
                        {'outline_tolerance':-1},{'outline_tolerance':4.1}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):normalize_options(replace(self.options,**changes))

    def test_saved_derived_loops_do_not_hide_new_threshold_or_tolerance(self):
        images,old=self.prepared(replace(self.options,outline_alpha_threshold=16))
        changed=replace(old,outline_alpha_threshold=200)
        updated=resolve_options(images,changed)
        self.assertNotEqual(updated.irregular_contours,old.irregular_contours)
        fresh=prepare_images(self.path,options=changed)
        self.assertEqual(resolve_options(fresh,changed).irregular_contours,updated.irregular_contours)
        self.assertEqual(images['irregular_outline_parameters'],(200,0))

    def test_front_and_natural_back_retain_source_alpha_exact_for_both_axes(self):
        original_bytes=self.path.read_bytes()
        for axis in ('x','y'):
            images,options=self.prepared(replace(self.options,axis=axis))
            self.assertEqual(images['back_mode'],'mirrored_front_for_irregular')
            expected_back=ImageOps.mirror(self.image) if axis=='y' else ImageOps.flip(self.image)
            self.assertEqual(images['back'].tobytes(),expected_back.tobytes())
            for angle,source in ((0,self.image),(180,expected_back)):
                rendered=render_pose(images,options,angle,(128,128),'transparent',progress=angle/360,show_ground=False,
                    camera={'scale':1.,'origin_x':64.,'origin_y':64.})
                reference=Image.new('RGBA',(128,128));reference.alpha_composite(source,(16,16))
                self.assertTrue(np.array_equal(np.asarray(rendered)[:,:,3],np.asarray(reference)[:,:,3]))
                visible=np.asarray(reference)[:,:,3]>0
                self.assertTrue(np.array_equal(np.asarray(rendered)[:,:,:3][visible],np.asarray(reference)[:,:,:3][visible]))
        self.assertEqual(self.path.read_bytes(),original_bytes)

    def test_every_cap_and_effect_component_obeys_native_mesh_euler_count(self):
        images,options=self.prepared(replace(self.options,coin_shine_enabled=True))
        meshes=pose_at(35,options,images['width'],images['height'])
        self.assertLess(len(meshes),500)
        self.assertTrue(any(mesh['kind']=='coin_fx' for mesh in meshes))
        for mesh in meshes:
            count=len(mesh['vertices'])//2
            self.assertEqual(len(mesh['triangles'])//3,2*count-mesh['hull']-2,mesh['name'])
            self.assertTrue(all(0<=index<count for index in mesh['triangles']))
            self.assertEqual(len(mesh['model_vertices']),count*3)
            self.assertIn('draw_order',mesh)

    def test_fixed_mesh_list_has_separate_painter_order_and_correct_interpolated_depth(self):
        images,options=self.prepared()
        width,height=images['width'],images['height']
        first=pose_at(30,options,width,height);back=pose_at(210,options,width,height)
        self.assertEqual([mesh['name'] for mesh in first],[mesh['name'] for mesh in back])
        self.assertNotEqual([mesh['name'] for mesh in ordered_surfaces(first)],[mesh['name'] for mesh in ordered_surfaces(back)])
        for axis in ('x','y'):
            meshes=animation_pose_at(.137,replace(options,axis=axis),width,height)
            angle=.137*2*np.pi;c,s=np.cos(angle),np.sin(angle)
            for mesh in meshes:
                model=np.asarray(mesh['model_vertices']).reshape(-1,3)
                projected=np.column_stack((model[:,0]*c+model[:,2]*s,model[:,1])) if axis=='y' else np.column_stack((model[:,0],model[:,1]*c-model[:,2]*s))
                self.assertLess(np.max(np.abs(projected-np.asarray(mesh['vertices']).reshape(-1,2))),1e-8)

    def test_standard_draw_order_is_exported_in_each_target_schema(self):
        images,options=self.prepared()
        for family,version in SPINE_TARGETS.items():
            document=build_skeleton(images,replace(options,spine_version=version))
            for clip,animation in document['animations'].items():
                keys=animation['draworder' if family=='3.8' else 'drawOrder']
                self.assertEqual(keys[0]['time'],0)
                self.assertLessEqual(len(keys),3)
                for key in keys:
                    self.assertEqual(len(key['offsets']),len(document['slots']))
                    targets=[i+entry['offset'] for i,entry in enumerate(key['offsets'])]
                    self.assertEqual(sorted(targets),list(range(len(document['slots']))))

    def test_legacy_render_order_helper_is_a_noop_and_manifest_records_approximation(self):
        old=pose_at(33,TurnOptions(),96,96)
        self.assertIs(ordered_surfaces(old),old)
        result=build_package(self.path,None,None,self.folder/'package',self.options)
        import json
        metadata=json.loads(Path(result['manifest_path']).read_text(encoding='utf-8'))
        self.assertEqual(metadata['irregular']['back_mode'],'mirrored_front_for_irregular')
        self.assertTrue(metadata['irregular']['active'])
        self.assertIn('soft fringes',metadata['irregular']['physical_boundary_limit'])


if __name__=='__main__':unittest.main()
