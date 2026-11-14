"""Irregular-shape controls and project round trips without creating a window."""
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
import main
from main import App,SHAPES
from test_v11_ui_options import app_without_window
from test_v16_ui_project import app_without_display,Value
from spine_turn_core import TurnOptions,normalize_options,prepare_images,resolve_options
from spine_turn_project import save_project,load_project


class IrregularUIIntegrationTests(unittest.TestCase):
    def test_explicit_shape_mapping_preserves_legacy_labels_without_substring_fallback(self):
        for label,expected in SHAPES.items():
            self.assertEqual(app_without_window(shape=label).get_options().shape,expected)
        self.assertEqual(app_without_window(shape='矩形／卡片').get_options().shape,'rectangle')
        for label in ('未知多邊形','其他矩形','不存在的外形'):
            with self.subTest(label=label),self.assertRaisesRegex(ValueError,'物件外形'):
                app_without_window(shape=label).get_options()

    def test_irregular_effective_options_keep_motion_material_and_shine_but_disable_convex_profiles(self):
        app=app_without_window(shape='不規則透明輪廓',outline_alpha_threshold=72,outline_tolerance=.75,
            ridge_mode=True,bevel_width=12,bevel_depth=35,coin_shine_enabled=True,
            bounce_enabled=True,z_bounce_enabled=True)
        app.raised_contour_points=((-0.2,-0.2),(.2,-.2),(0,.2))
        options=app.get_options()
        self.assertEqual((options.shape,options.outline_alpha_threshold,options.outline_tolerance),
                         ('irregular',72,.75))
        self.assertEqual((options.bevel_width,options.side_mode,options.raised_contour_points),(0,'strip',()))
        self.assertEqual(options.thickness,26)
        self.assertEqual(options.edge_orientation,'horizontal')
        self.assertTrue(options.coin_shine_enabled and options.bounce_enabled and options.z_bounce_enabled)
        self.assertEqual(app.bevel_width.get(),12)
        self.assertTrue(app.ridge_mode.get())

    def test_threshold_and_tolerance_reject_invalid_values_before_project_commit(self):
        for changes,word in (({'outline_alpha_threshold':0},'透明度門檻'),
                ({'outline_alpha_threshold':256},'透明度門檻'),
                ({'outline_alpha_threshold':16.5},'整數'),
                ({'outline_tolerance':-.1},'輪廓誤差'),
                ({'outline_tolerance':4.1},'輪廓誤差'),
                ({'outline_tolerance':float('nan')},'輪廓誤差')):
            with self.subTest(changes=changes),self.assertRaisesRegex(ValueError,word):
                app_without_window(shape='不規則透明輪廓',**changes).get_options()

    def test_controls_keep_thickness_and_material_enabled_while_hiding_convex_only_features(self):
        app=app_without_window(shape='不規則透明輪廓',model_choice='一般物件')
        names=('ridge_control','raised_region_button','reset_region_button','bevel_width_control',
               'bevel_depth_control','thickness_control','shape_control','edge_direction_control',
               'segments_control','outline_threshold_control','outline_tolerance_control','outline_settings')
        for name in names:setattr(app,name,Mock())
        app.update_model_controls()
        for name in names[:5]:getattr(app,name).configure.assert_called_with(state='disabled')
        app.thickness_control.configure.assert_called_with(state='normal')
        app.edge_direction_control.configure.assert_called_with(state='readonly')
        app.outline_threshold_control.configure.assert_called_with(state='normal')
        app.outline_settings.pack.assert_called_once()
        app.shape=Value('依透明外框／凸多邊形')
        app.update_model_controls()
        app.raised_region_button.configure.assert_called_with(state='normal')
        app.outline_settings.pack_forget.assert_called_once()
        app.model_choice=Value('鑽石')
        app.update_model_controls()
        app.thickness_control.configure.assert_called_with(state='disabled')
        app.shape_control.configure.assert_called_with(state='disabled')

    def test_direct_raised_editor_and_ridge_actions_cannot_coerce_irregular_to_convex(self):
        app=app_without_window(shape='不規則透明輪廓')
        app.root=object()
        with patch('main.messagebox.showinfo') as info:
            app.edit_raised_region()
        info.assert_called_once()
        self.assertEqual(app.selected_shape(),'irregular')
        app.ridge_mode=Value(True)
        app.update_profile_controls=Mock()
        app.toggle_ridge_mode()
        self.assertFalse(app.ridge_mode.get())
        self.assertEqual(app.selected_shape(),'irregular')

    def test_irregular_project_open_and_ctrl_s_keep_controls_contours_and_original_bytes(self):
        sources={'front':ROOT/'assets/demo-irregular-front.png',
                 'back':ROOT/'assets/demo-irregular-back.png','edge':ROOT/'assets/demo-edge.png'}
        options=TurnOptions(name='irregular-ui',shape='irregular',outline_alpha_threshold=72,
            outline_tolerance=.75,spine_version='4.2.43',coin_shine_enabled=True,
            bounce_enabled=True,z_bounce_enabled=True,z_bounce_depth=-100)
        options=resolve_options(prepare_images(**{f'{role}_path':path for role,path in sources.items()},options=options),options)
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'irregular.spturn'
            save_project(path,sources,options,{'animation':'flip_to_back','progress':.31,'playing':False})
            with load_project(path) as loaded:
                app=app_without_display()
                app.apply_loaded_project(loaded,path)
                current=app.get_options()
                self.assertEqual(app.shape.get(),'不規則透明輪廓')
                self.assertEqual(current.irregular_contours,normalize_options(options).irregular_contours)
                self.assertEqual((current.outline_alpha_threshold,current.outline_tolerance),(72,.75))
                app.outline_alpha_threshold.set(220)
                app.outline_tolerance.set(3.5)
                changed=app.get_options()
                expected=resolve_options(prepare_images(app.paths['front'],app.paths['back'],app.paths['edge'],changed),changed)
                self.assertNotEqual(expected.irregular_contours,current.irregular_contours,
                                    'Fixture must expose stale-loop saves after changing outline controls.')
                with patch('main.messagebox.showerror') as errors:app.save_project()
                errors.assert_not_called()
                with load_project(path) as saved:
                    self.assertEqual(saved.options.irregular_contours,expected.irregular_contours)
                    self.assertEqual(saved.options.spine_version,'4.2.43')
                    self.assertEqual(saved.options.outline_alpha_threshold,220)
                    self.assertEqual(saved.options.outline_tolerance,3.5)
                    for role,source in sources.items():
                        self.assertEqual(Path(saved.paths[role]).read_bytes(),source.read_bytes())

    def test_demo_selects_original_irregular_art_and_shine_demo_still_resets_to_ellipse(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'initial.spturn'
            save_project(path,{'front':ROOT/'assets/demo-front.png','back':None,'edge':None},TurnOptions())
            with load_project(path) as loaded:
                app=app_without_display()
                app.apply_loaded_project(loaded,path)
                app.load_demo('irregular')
                options=app.get_options()
                self.assertEqual((options.shape,options.outline_alpha_threshold,options.outline_tolerance),
                                 ('irregular',16,1))
                self.assertFalse(options.coin_shine_enabled)
                self.assertEqual(Path(app.paths['front']).name,'demo-irregular-front.png')
                self.assertEqual(Path(app.paths['back']).name,'demo-irregular-back.png')
                app.load_demo('shine')
                self.assertEqual(app.get_options().shape,'ellipse')
                self.assertTrue(app.get_options().coin_shine_enabled)

    def test_replacing_front_art_discards_stale_irregular_contours(self):
        app=app_without_display()
        app.paths={'front':'previous.png','back':None,'edge':None}
        app.extra_options=replace(TurnOptions(),irregular_contours=(((0,0),(.1,0),(0,.1)),))
        app.thumbs={}
        app.cards={'front':(Mock(),Mock())}
        app.set_image=App.set_image.__get__(app)
        with patch('main.ImageTk.PhotoImage',return_value=object()):
            self.assertTrue(app.set_image('front',ROOT/'assets/demo-irregular-front.png'))
        self.assertEqual(app.extra_options.irregular_contours,())


if __name__=='__main__':unittest.main(verbosity=2)
