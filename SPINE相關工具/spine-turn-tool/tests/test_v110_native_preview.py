"""Native-data previews use sampled world coordinates and actual painter order."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from native_data_preview import render_native_pose,native_delivery_preview


def mesh(path,color=(1,1,1,1)):
    return dict(path=path,vertices=[0,0,12,0,0,12],uvs=[0,0,1,0,0,1],triangles=[0,1,2],color=color)


class NativePreviewTests(unittest.TestCase):
    def test_world_vertices_are_drawn_in_runtime_insertion_order(self):
        textures={'red':Image.new('RGBA',(2,2),(255,0,0,255)),
                  'blue':Image.new('RGBA',(2,2),(0,0,255,255))}
        camera=dict(scale=2,origin_x=10,origin_y=40)
        first={'geometry':{'red':mesh('red',(1,1,1,.5)),'blue':mesh('blue',(1,1,1,.5))}}
        second={'geometry':dict(reversed(list(first['geometry'].items())))}
        on_top_blue=render_native_pose(first,textures,camera,size=(64,64))
        on_top_red=render_native_pose(second,textures,camera,size=(64,64))
        self.assertGreater(on_top_blue.getpixel((15,35))[2],on_top_blue.getpixel((15,35))[0])
        self.assertGreater(on_top_red.getpixel((15,35))[0],on_top_red.getpixel((15,35))[2])
        self.assertEqual(on_top_blue.getchannel('A').getbbox(),(10,17,33,40))

    def test_sixty_frame_delivery_records_binary_and_runtime_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            case=folder/'case'
            (case/'spine-4.0/images').mkdir(parents=True)
            (case/'spine-4.0/native-binary').mkdir()
            (case/'spine-4.0/native-binary/fixture.skel').write_bytes(b'unit fixture identity; not executable')
            Image.new('RGBA',(2,2),(40,150,230,255)).save(case/'spine-4.0/images/front.png')
            progresses=sorted(set([i/60 for i in range(60)]+[i/8 for i in range(8)]))
            samples=dict(data_version='4.0.56',animations={'rotate_loop':{'poses':[
                dict(progress=progress,geometry={'front':mesh('front')}) for progress in progresses]}})
            (case/'4.0-native-binary-poses.json').write_text(json.dumps(samples),encoding='utf-8')
            delivery=folder/'delivery'
            (delivery/'png-sequence').mkdir(parents=True)
            (delivery/'delivery.json').write_text('{}',encoding='utf-8')
            (delivery/'png-sequence/sequence.json').write_text(json.dumps(dict(frame_count=60,status='complete',
                camera=dict(scale=20,origin_x=120,origin_y=400))),encoding='utf-8')
            from types import SimpleNamespace
            result=native_delivery_preview(case,delivery,SimpleNamespace(name='fixture',duration=2))
            self.assertEqual(result['native_binary_rendered_frames'],60)
            self.assertEqual(len(list((delivery/'png-sequence').glob('frame_*.png'))),60)
            metadata=json.loads((delivery/'png-sequence/sequence.json').read_text(encoding='utf-8'))
            self.assertEqual(metadata['render_source']['kind'],'official-runtime-native-binary')
            self.assertTrue(metadata['render_source']['world_vertices_include_bone_motion'])
            self.assertEqual(len(metadata['render_source']['frame_pixel_sha256']),60)
            self.assertTrue((delivery/'preview.gif').is_file())


if __name__=='__main__':unittest.main(verbosity=2)
