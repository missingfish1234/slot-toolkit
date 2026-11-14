"""Editable coin light timing, source UV identity and disabled regressions."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest
from fixture_availability import require_historical_packages

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spine_turn_core import (TurnOptions, animation_pose_at, build_skeleton,
                             pose_at, prepare_images, resolve_options)
from spine_turn_coin_fx import (coin_effect_surfaces, make_effect_textures,
                                shine_key_progress, sweep_alpha)


class CoinShineCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = TurnOptions(coin_shine_enabled=True, coin_shine_start=0, coin_shine_end=.25)
        cls.prepared = prepare_images(ROOT/'assets/demo-front.png', options=cls.base)
        cls.options = resolve_options(cls.prepared, cls.base)

    def test_disabled_and_zero_strength_keep_entire_v18_native_skeleton_exact(self):
        require_historical_packages(self, [ROOT / 'qa/v1.9' / f'baseline-v1.8-{label}'
                                          for label in ('ellipse', 'polygon', 'bevel', 'ridge')])
        for label in ('ellipse', 'polygon', 'bevel', 'ridge'):
            folder = ROOT/'qa/v1.9'/f'baseline-v1.8-{label}'
            manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
            options = TurnOptions(**manifest['options'])
            document = json.loads(next(p for p in folder.glob('*.json') if p.name != 'manifest.json').read_text(encoding='utf-8'))
            for value in (options, replace(options, coin_shine_enabled=True, coin_shine_strength=0)):
                prepared = prepare_images(folder/'images/front.png', folder/'images/back.png', folder/'images/edge.png', value)
                self.assertEqual(build_skeleton(prepared, value), document, label)
                self.assertNotIn('generated_texture_names', prepared)
                self.assertEqual(shine_key_progress(value, prepared['width'], prepared['height']), ())

    def test_original_transparency_and_holes_are_excluded_from_white_mask(self):
        image = Image.new('RGBA', (13,13), (25,60,100,128))
        for y in range(2,11):
            for x in range(2,11):
                image.putpixel((x,y),(25,60,100,255))
        image.putpixel((6,6),(0,0,0,0))
        masks = make_effect_textures({'front':image,'back':image.copy()}, self.options)
        for mask in masks.values():
            for y in range(13):
                for x in range(13):
                    if mask.getpixel((x,y))[3]:
                        self.assertEqual(mask.getpixel((x,y))[:3],(255,255,255))
                        self.assertTrue(all(image.getpixel((a,b))[3] == 255
                            for a in range(max(0,x-1),min(13,x+2)) for b in range(max(0,y-1),min(13,y+2))))
            self.assertEqual(mask.getpixel((6,6))[3],0)
            self.assertEqual(mask.getpixel((5,6))[3],0)

    def test_enabled_effect_keeps_every_original_parent_native_track_exact(self):
        require_historical_packages(self, [ROOT / 'qa/v1.9' / f'baseline-v1.8-{label}'
                                          for label in ('ellipse', 'polygon', 'bevel', 'ridge')])
        for label in ('ellipse', 'polygon', 'bevel', 'ridge'):
            folder = ROOT/'qa/v1.9'/f'baseline-v1.8-{label}'
            manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
            plain = TurnOptions(**manifest['options'])
            options = replace(plain, coin_shine_enabled=True)
            prepared = prepare_images(folder/'images/front.png', folder/'images/back.png', folder/'images/edge.png', options)
            original = build_skeleton(prepared, plain)
            lit = build_skeleton(prepared, options)
            self.assertEqual(original['slots'],lit['slots'][:len(original['slots'])])
            for name, attachments in original['skins'][0]['attachments'].items():
                self.assertEqual(attachments,lit['skins'][0]['attachments'][name])
            for clip, old in original['animations'].items():
                new = lit['animations'][clip]
                for name, timeline in old['deform']['default'].items():
                    self.assertEqual(timeline,new['deform']['default'][name],(label,clip,name))
                    self.assertEqual(old['slots'][name],new['slots'][name],(label,clip,name))
                self.assertEqual(old.get('bones'),new.get('bones'))

    def test_fully_opaque_cards_still_get_a_guard_at_the_image_boundary(self):
        source = Image.new('RGBA',(8,8),(100,120,140,255))
        masks = make_effect_textures({'front':source,'back':source},self.options)
        for texture in masks.values():
            self.assertTrue(all(texture.getpixel((x,y))[3] == 0
                for x in range(8) for y in range(8) if x in (0,7) or y in (0,7)))
            self.assertEqual(texture.getpixel((3,3))[3],255)

    def test_all_clips_schedule_their_own_window_and_export_alpha_without_face_shading(self):
        width, height = self.prepared['width'], self.prepared['height']
        skeleton = build_skeleton(self.prepared,self.options)
        for clip in ('rotate_loop','flip_to_back','flip_to_front'):
            bright = animation_pose_at(.125,self.options,width,height,clip)
            light = [surface for surface in bright if surface['kind']=='coin_fx']
            self.assertGreater(max(surface['tint'][3] for surface in light),self.options.coin_shine_strength*.7)
            for progress in (0,.25,.4,1):
                surfaces = animation_pose_at(progress,self.options,width,height,clip)
                self.assertTrue(all(surface['tint'][3]==0 for surface in surfaces if surface['kind']=='coin_fx'))
            for surface in light:
                keys = skeleton['animations'][clip]['slots'][surface['name']]['rgba']
                self.assertTrue(any(int(key['color'][-2:],16)>0 for key in keys))
                self.assertEqual(keys[0]['color'][-2:],'00')
                self.assertEqual(keys[-1]['color'][-2:],'00')

    def test_cell_uv_and_positions_are_fixed_convex_parent_combinations_between_keys(self):
        options = replace(self.options, bounce_enabled=True, z_bounce_enabled=True,
                          peak_z_scale=1.4, z_bounce_start=.04,z_bounce_apex=.16,z_bounce_end=.6)
        for axis in ('x','y'):
            for progress in (.013,.077,.123,.237,.499,.733,.98):
                meshes = animation_pose_at(progress,replace(options,axis=axis),320,320)
                lookup = {mesh['name']:mesh for mesh in meshes}
                effects = [mesh for mesh in meshes if mesh['kind']=='coin_fx']
                self.assertLessEqual(len(effects),64)
                for effect in effects:
                    parent = lookup[effect['source_face']]
                    self.assertEqual(effect['visible'],parent['visible'])
                    for vertex, weights in enumerate(effect['cell_weights']):
                        self.assertAlmostEqual(sum(weight for _,weight in weights),1,places=10)
                        self.assertTrue(all(weight>=-1e-12 for _,weight in weights))
                        for axis2 in (0,1):
                            expected = sum(parent['vertices'][i*2+axis2]*weight for i,weight in weights)
                            self.assertAlmostEqual(effect['vertices'][vertex*2+axis2],expected,places=7)
                            uv = sum(parent['uvs'][i*2+axis2]*weight for i,weight in weights)
                            self.assertAlmostEqual(effect['uvs'][vertex*2+axis2],uv,places=10)

    def test_repeat_window_has_dark_cycle_seams_and_finite_support_width(self):
        options = replace(self.options,coin_shine_start=.1,coin_shine_end=.9,coin_shine_repeat=4)
        for progress in (0,.1,.3,.5,.7,.9,1):
            self.assertEqual(sweep_alpha(progress,0,options,320,320),0)
        self.assertAlmostEqual(sweep_alpha(.2,0,options,320,320),options.coin_shine_strength)
        self.assertEqual(sweep_alpha(.2,options.coin_shine_width*320/2,options,320,320),0)
        self.assertTrue(all(.1<=value<=.9 for value in shine_key_progress(options,320,320)))

    def test_invalid_controls_are_rejected_and_diamond_ignores_coin_sweep(self):
        for change in ({'coin_shine_width':.01},{'coin_shine_strength':1.01},
                       {'coin_shine_repeat':0},{'coin_shine_repeat':float('inf')},
                       {'coin_shine_start':.9,'coin_shine_end':.1}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                pose_at(0,replace(self.options,**change),320,320)
        diamond = replace(self.options,model='diamond')
        self.assertFalse(any(surface['kind']=='coin_fx' for surface in pose_at(30,diamond,320,320)))
        self.assertEqual(make_effect_textures(self.prepared,diamond),{})


if __name__ == '__main__':
    unittest.main()
