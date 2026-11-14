"""Independent output, alpha, and interpolated-parent checks for coin light sweeps."""
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from fixture_availability import require_historical_files, require_historical_packages

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spine_turn_core import (TurnOptions, build_package, prepare_images, resolve_options,
                             animation_pose_at)
from spine_turn_coin_fx import make_effect_textures
from spine_turn_preview import render_pose


class CoinShineIndependentTests(unittest.TestCase):
    def test_disabled_and_zero_strength_preserve_frozen_18_authored_files(self):
        require_historical_files(self, [ROOT/'qa/v1.9/baseline-provenance.json'])
        proof = json.loads((ROOT/'qa/v1.9/baseline-provenance.json').read_text(encoding='utf-8'))
        assets = Path(proof['frozen_application_source'])/'assets'
        require_historical_packages(self, [ROOT/f'qa/v1.9/baseline-v1.8-{label}' for label in proof['cases']])
        required = []
        for label, case in proof['cases'].items():
            required.append(assets/('demo-front.png' if label == 'ellipse' else 'demo-octagon.png'))
            if label == 'ellipse':
                required.append(assets/'demo-back.png')
            if label != 'ridge':
                required.append(assets/'demo-edge.png')
            baseline = ROOT/f'qa/v1.9/baseline-v1.8-{label}'
            required.extend(baseline/f"{case['options']['name']}{suffix}" for suffix in ('.json', '.atlas', '.png'))
        require_historical_files(self, required)
        with tempfile.TemporaryDirectory() as work:
            for label, case in proof['cases'].items():
                front = assets/('demo-front.png' if label == 'ellipse' else 'demo-octagon.png')
                back = assets/'demo-back.png' if label == 'ellipse' else None
                edge = None if label == 'ridge' else assets/'demo-edge.png'
                options = TurnOptions(**case['options'])
                baseline = ROOT/f'qa/v1.9/baseline-v1.8-{label}'
                prepared = prepare_images(front,back,edge,options)
                resolved = resolve_options(prepared,options)
                for angle, expected_hash in case['preview_pixel_sha256'].items():
                    rendered = render_pose(prepared,resolved,int(angle),size=(320,320),progress=int(angle)/360,
                                           background='transparent',show_ground=False)
                    self.assertEqual(hashlib.sha256(rendered.tobytes()).hexdigest(),expected_hash,(label,angle))
                for mode, current in [('disabled', options), ('zero', replace(options,
                        coin_shine_enabled=True, coin_shine_strength=0))]:
                    folder = Path(work)/label/mode
                    result = build_package(front, back, edge, folder, current)
                    expected = json.loads((baseline/f'{options.name}.json').read_text(encoding='utf-8'))
                    actual = json.loads(Path(result['json_path']).read_text(encoding='utf-8'))
                    self.assertEqual(actual, expected, (label, mode))
                    for path in baseline.rglob('*'):
                        if path.is_file() and path.suffix in ('.atlas', '.png'):
                            self.assertEqual((folder/path.relative_to(baseline)).read_bytes(), path.read_bytes(),
                                             (label, mode, path.name))

    def test_zero_strength_matches_disabled_pixels_between_authored_keys(self):
        options = TurnOptions(coin_shine_enabled=True, coin_shine_strength=0,
                              coin_shine_start=0, coin_shine_end=.25)
        prepared = prepare_images(ROOT/'assets/demo-front.png', ROOT/'assets/demo-back.png',
                                  ROOT/'assets/demo-edge.png', options)
        disabled = replace(options, coin_shine_enabled=False)
        for progress in (.017, .123, .347, .619, .983):
            first = render_pose(prepared, options, progress*360, size=(240,240), progress=progress,
                                background='transparent', show_ground=False)
            second = render_pose(prepared, disabled, progress*360, size=(240,240), progress=progress,
                                 background='transparent', show_ground=False)
            self.assertEqual(first.tobytes(), second.tobytes(), progress)
        self.assertEqual(make_effect_textures(prepared, options), {})

    def test_sweep_changes_rgb_without_filling_holes_or_increasing_edge_alpha(self):
        with tempfile.TemporaryDirectory() as work:
            source = Image.new('RGBA', (96,96), (35,80,125,0))
            draw = ImageDraw.Draw(source)
            draw.ellipse((3,3,92,92), fill=(35,80,125,128))
            draw.ellipse((8,8,87,87), fill=(35,80,125,255))
            draw.ellipse((34,34,61,61), fill=(35,80,125,0))
            path = Path(work)/'alpha-hole.png'
            source.save(path)
            options = TurnOptions(thickness=0, trim_transparent=False, coin_shine_enabled=True,
                coin_shine_strength=.8,coin_shine_start=0,coin_shine_end=1,coin_shine_width=.45)
            prepared = prepare_images(path, options=options)
            original = path.read_bytes()
            changes = 0
            for progress in (.17,.31,.49,.63,.81):
                on = render_pose(prepared, options, 0, size=(192,192), progress=progress,
                                 background='transparent',show_ground=False)
                off = render_pose(prepared, replace(options,coin_shine_enabled=False),0,
                                  size=(192,192),progress=progress,
                                  background='transparent',show_ground=False)
                self.assertEqual(on.getchannel('A').tobytes(),off.getchannel('A').tobytes(),progress)
                changes += ImageChops.difference(on.convert('RGB'),off.convert('RGB')).getbbox() is not None
            self.assertGreater(changes, 0)
            self.assertEqual(path.read_bytes(), original)

    def test_fixed_cells_follow_parent_at_between_key_times_on_both_axes_and_all_clips(self):
        checked = 0
        for axis in ('x','y'):
            options = TurnOptions(axis=axis,coin_shine_enabled=True,coin_shine_start=.02,
                coin_shine_end=.83,coin_shine_repeat=3,coin_shine_angle=37,
                bounce_enabled=True,z_bounce_enabled=True,peak_z_scale=1.5,
                bounce_start=.3,bounce_apex=.5,bounce_land=.7,bounce_end=.85,
                z_bounce_start=.1,z_bounce_apex=.2,z_bounce_end=.45)
            for action in ('rotate_loop','flip_to_back','flip_to_front'):
                for index in range(101):
                    surfaces = animation_pose_at(index/100,options,128,96,action)
                    lookup = {mesh['name']:mesh for mesh in surfaces}
                    for mesh in surfaces:
                        if mesh.get('kind') != 'coin_fx':
                            continue
                        parent = lookup[mesh['source_face']]
                        self.assertIn(parent['kind'], ('front','back'))
                        self.assertEqual(mesh['visible'], parent['visible'])
                        source_points = list(zip(parent['vertices'][::2],parent['vertices'][1::2]))
                        for position, weights in enumerate(mesh['cell_weights']):
                            self.assertAlmostEqual(sum(weight for _,weight in weights),1,places=11)
                            self.assertGreaterEqual(min(weight for _,weight in weights),-1e-12)
                            for coordinate in (0,1):
                                expected = sum(source_points[i][coordinate]*weight for i,weight in weights)
                                self.assertLess(abs(mesh['vertices'][2*position+coordinate]-expected),1e-7)
                            checked += 1
        self.assertGreater(checked,1000)

    def test_effects_use_only_flat_caps_on_bevel_and_ridge(self):
        for side, bevel in (('strip',.07),('ridge',0)):
            options = TurnOptions(shape='polygon',side_mode=side,bevel_width=bevel,
                                  coin_shine_enabled=True,coin_shine_start=0,coin_shine_end=.25)
            prepared = prepare_images(ROOT/'assets/demo-octagon.png',options=options)
            options = resolve_options(prepared,options)
            meshes = animation_pose_at(.123,options,prepared['width'],prepared['height'])
            lookup = {mesh['name']:mesh for mesh in meshes}
            fx = [mesh for mesh in meshes if mesh.get('kind') == 'coin_fx']
            self.assertTrue(fx)
            for mesh in fx:
                self.assertIn(lookup[mesh['source_face']]['kind'],('front','back'))
                self.assertIn(mesh['path'],('coin-shine-front','coin-shine-back'))


if __name__ == '__main__':
    unittest.main()
