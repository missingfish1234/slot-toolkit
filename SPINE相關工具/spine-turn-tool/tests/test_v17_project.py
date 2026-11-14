"""Diamond mode/settings/FX remain editable in the self-contained project format."""
from dataclasses import asdict
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spine_turn_core import TurnOptions, prepare_images, resolve_options
from spine_turn_project import APPLICATION_VERSION, save_project, load_project


class DiamondProjectTests(unittest.TestCase):
    def test_all_diamond_guides_material_effects_and_raw_source_roundtrip_without_new_asset_roles(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source = folder / '原始鑽石.png'
            shutil.copy2(ROOT / 'assets' / 'demo-diamond.png', source)
            original_bytes = source.read_bytes()
            options = TurnOptions(name='diamond-project', model='diamond', spine_version='3.8.99',
                width=384, side_mode='ridge', bevel_depth=.3,
                raised_contour_points=((-0.45, -.45), (.45, -.45), (0, .45)),
                diamond_facets=12, diamond_center_x=.03, diamond_table_y=.38,
                diamond_waist_y=.08, diamond_tip_y=-.44, diamond_table_width=.42,
                diamond_waist_width=.88, diamond_girdle_height=.025,
                diamond_view_tilt=18, diamond_shading=.77,
                diamond_shine_enabled=False, diamond_shine_strength=.52,
                diamond_sparkles_enabled=True, diamond_sparkle_strength=.84,
                diamond_cut_regions=((
                    ((-.4, .15), (0., .15), (0., .4)), -24., 12.), (
                    ((0., .15), (.4, .15), (0., .4)), 28., -15.)))
            prepared = prepare_images(source, None, None, options)
            options = resolve_options(prepared, options)
            filename = folder / 'diamond.spturn'
            save_project(filename, {'front': source, 'back': None, 'edge': None}, options,
                {'animation': 'rotate_loop', 'progress': .2, 'playing': False})
            source.unlink()
            with load_project(filename) as loaded:
                self.assertEqual(asdict(loaded.options), asdict(options))
                self.assertEqual(Path(loaded.paths['front']).read_bytes(), original_bytes)
                self.assertIsNone(loaded.paths['back'])
                self.assertIsNone(loaded.paths['edge'])
                self.assertEqual(loaded.options.model, 'diamond')
                self.assertEqual(loaded.options.spine_version, '3.8.99')
                self.assertIsInstance(loaded.options.diamond_cut_regions, tuple)
                self.assertIsInstance(loaded.options.diamond_cut_regions[0][0][0], tuple)
                self.assertEqual(loaded.options.diamond_cut_regions, options.diamond_cut_regions)
                second = folder / 'diamond-resaved.spturn'
                save_project(second, loaded.paths, loaded.options, loaded.ui_state)
            with load_project(second) as loaded:
                self.assertEqual(asdict(loaded.options), asdict(options))
                self.assertEqual(Path(loaded.paths['front']).read_bytes(), original_bytes)
            with zipfile.ZipFile(filename) as archive:
                manifest = json.loads(archive.read('manifest.json'))
                self.assertEqual(manifest['schema_version'], 1)
                self.assertEqual(manifest['application_version'], APPLICATION_VERSION)
                self.assertEqual(set(manifest['assets']), {'front', 'back', 'edge'})
                self.assertEqual(len(archive.namelist()), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
