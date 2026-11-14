"""Guard the actual-order cache and native mesh renderability checks without a CLI."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from verify_v110_pipeline import validate_irregular,QUARTERS


class NativeValidationTests(unittest.TestCase):
    def fixture(self):
        vertices=[0,0,2,0,0,2]
        uvs=[0,0,1,0,0,1]
        triangles=[0,1,2]
        attachment=dict(path='front',vertices=vertices,uvs=uvs,triangles=triangles,hull=3)
        document=dict(skins=[{'attachments':{name:{name:deepcopy(attachment)} for name in ('a','b')}}],
            slots=[{'name':name} for name in ('a','b')],animations={'rotate_loop':{'deform':{'default':{
                name:{name:[{'time':0,'vertices':[0]*6}]} for name in ('a','b')}}}})
        poses=[]
        for progress in sorted(set(QUARTERS)|{i/100 for i in range(101)}):
            geometry={name:dict(name=name,path='front',vertices=vertices,uvs=uvs,triangles=triangles,
                color=[1,1,1,1],blend_mode=0) for name in (('b','a') if progress>.5 else ('a','b'))}
            poses.append(dict(progress=progress,geometry=geometry,bones={
                'root':dict(world_x=0,world_y=0),'turn':dict(world_x=0,world_y=0,a=1,d=1)}))
        sampled=dict(animations={'rotate_loop':dict(duration=1,poses=poses)})

        def source_pose(progress,*args):
            return [dict(name=name,vertices=vertices,uvs=uvs,triangles=triangles,
                         tint=[1,1,1,1],visible=True,kind='front',
                         draw_order=(1 if name=='a' else 0) if progress>.5 else (0 if name=='a' else 1))
                    for name in ('a','b')]
        return document,sampled,source_pose

    def validate(self,document,sampled,source_pose):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'reference.json'
            path.write_text(json.dumps(document),encoding='utf-8')
            cache={}
            with patch('verify_v17_pipeline.animation_pose_at',side_effect=source_pose), \
                 patch('verify_v17_pipeline.motion_at',return_value=dict(x=0,y=0,scale_x=1,scale_y=1)):
                result=validate_irregular(path,sampled,None,{'width':2,'height':2},cache)
            self.assertTrue(all('draw_order' in mesh for _,preview in cache.values() for mesh in preview.values()))
            return result

    def test_actual_reverse_order_after_halfturn_uses_preserved_cached_rank(self):
        result=self.validate(*self.fixture())
        self.assertGreater(result['draw_order_poses'],100)
        self.assertGreater(result['quarter_epsilon_draw_order_poses'],20)
        self.assertTrue(result['authored_triangle_index_sets_exact'])

    def test_empty_native_triangles_are_rejected_even_when_vertices_uv_and_colors_match(self):
        document,sampled,source=self.fixture()
        sampled['animations']['rotate_loop']['poses'][75]['geometry']['a']['triangles']=[]
        with self.assertRaisesRegex(AssertionError,'empty/invalid native triangles'):
            self.validate(document,sampled,source)

    def test_truncated_native_vertices_cannot_pass_zip_comparisons(self):
        document,sampled,source=self.fixture()
        sampled['animations']['rotate_loop']['poses'][75]['geometry']['a']['vertices']=[0,0,2,0]
        with self.assertRaisesRegex(AssertionError,'native vertex count changed'):
            self.validate(document,sampled,source)


if __name__=='__main__':unittest.main(verbosity=2)
