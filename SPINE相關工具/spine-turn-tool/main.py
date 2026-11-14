"""Spine Turn Studio — a local image-to-editable-Spine desktop tool."""
from __future__ import annotations

import ctypes
from dataclasses import replace
import json
import math
import os
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
sys.path.insert(0, str(APP_DIR / "vendor"))
from PIL import Image, ImageTk
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    Root = TkinterDnD.Tk
except ImportError:
    Root = tk.Tk
    DND_FILES = None
from spine_turn_core import TurnOptions, SPINE_TARGETS, normalize_options, prepare_images, build_package, resolve_options
from spine_turn_preview import render_pose
from spine_turn_preview_worker import LatestPreviewWorker
from spine_turn_ui import StudioWorkspace
from spine_turn_ui_actions import StudioActions
from spine_turn_ui_style import PALETTE, StudioButton, FeedbackToast, attach_tooltip, configure_theme
from spine_native import discover_spine, convert_project
from spine_turn_sequence import export_sequence
from spine_turn_project import save_project as save_editable_project, load_project as load_editable_project

BG, PANEL, CARD, TEXT, MUTED, ACCENT, LINE = (
    PALETTE[key] for key in ("BG", "PANEL", "CARD", "TEXT", "MUTED", "ACCENT", "LINE"))
APP_VERSION = "1.12.0"
ANIMATIONS = {"整圈旋轉": "rotate_loop", "正面 → 背面": "flip_to_back", "背面 → 正面": "flip_to_front"}
EDGE_DIRECTIONS = {"橫向長條": "horizontal", "直向長條": "vertical", "自動依長寬判斷": "auto"}
MODELS = {"一般物件": "extrusion", "鑽石": "diamond"}
SHAPES = {"圓形／橢圓硬幣": "ellipse", "矩形卡片": "rectangle",
          "依透明外框／凸多邊形": "polygon", "不規則透明輪廓": "irregular"}
SHAPE_ALIASES = {"矩形／卡片": "rectangle"}
DIAMOND_GUIDE_FIELDS = ("diamond_center_x", "diamond_table_y", "diamond_waist_y",
                        "diamond_tip_y", "diamond_table_width", "diamond_waist_width")


class App(StudioActions):
    def __init__(self, root):
        self.root = root
        root.title(f"Spine Turn Studio {APP_VERSION} · 圖片翻轉製作器")
        width = min(1440, max(1000, root.winfo_screenwidth() - 80))
        height = min(880, max(660, root.winfo_screenheight() - 140))
        left = max(0, (root.winfo_screenwidth() - width) // 2)
        top = max(0, (root.winfo_screenheight() - height - 50) // 2)
        root.geometry(f"{width}x{height}+{left}+{top}")
        root.minsize(1000, 660)
        root.configure(bg=BG)
        self.paths = {"front": None, "back": None, "edge": None}
        self.extra_options = TurnOptions()
        self.project_path = None
        self._loaded_project = None
        self._loading_project = False
        self._closed = False
        self._preview_worker = None
        self._preview_view_key = None
        self._preview_request_id = 0
        self._preview_presented_id = 0
        self._preview_revision = 0
        self._preview_poll_job = None
        self.thumbs = {}
        self.prepared = None
        self.angle = 0.0
        self.progress = 0.0
        self.playing = True
        self.busy = False
        self.last_tick = time.perf_counter()
        self.native = discover_spine()
        self.output_base = Path.home() / "Documents" / "SpineTurnExports"
        self.name = tk.StringVar(value="coin")
        self.spine_version = tk.StringVar(value="4.0")
        self.spine_revision = tk.StringVar(value="目標版本：4.0.56")
        self.model_choice = tk.StringVar(value="一般物件")
        self.diamond_facets = tk.IntVar(value=8)
        self.diamond_view_tilt = tk.DoubleVar(value=12)
        self.diamond_girdle_height = tk.DoubleVar(value=1.5)
        self.diamond_shading = tk.DoubleVar(value=65)
        self.diamond_shine_enabled = tk.BooleanVar(value=True)
        self.diamond_shine_strength = tk.DoubleVar(value=35)
        self.diamond_sparkles_enabled = tk.BooleanVar(value=True)
        self.diamond_sparkle_strength = tk.DoubleVar(value=65)
        self.coin_shine_enabled = tk.BooleanVar(value=False)
        self.coin_shine_strength = tk.DoubleVar(value=40)
        self.coin_shine_width = tk.DoubleVar(value=50)
        self.coin_shine_angle = tk.DoubleVar(value=-25)
        self.coin_shine_start = tk.DoubleVar(value=0)
        self.coin_shine_end = tk.DoubleVar(value=.25)
        self.coin_shine_repeat = tk.IntVar(value=1)
        self.coin_shine_timing_summary = tk.StringVar(value="")
        self.diamond_guides = {}
        self.diamond_summary = tk.StringVar(value="對齊實際切面與前後緣。")
        self.thickness = tk.DoubleVar(value=24)
        self.duration = tk.DoubleVar(value=2)
        self.segments = tk.IntVar(value=32)
        self.axis = tk.StringVar(value="左右翻轉 · Y 軸")
        self.shape = tk.StringVar(value="圓形／橢圓硬幣")
        self.outline_alpha_threshold = tk.StringVar(value="16")
        self.outline_tolerance = tk.DoubleVar(value=1)
        self.edge_orientation = tk.StringVar(value="橫向長條")
        self.base_scale = tk.DoubleVar(value=100)
        self.bounce_enabled = tk.BooleanVar(value=False)
        self.bounce_height = tk.DoubleVar(value=100)
        self.peak_scale = tk.DoubleVar(value=115)
        self.landing_squash = tk.DoubleVar(value=12)
        self.z_scale = tk.DoubleVar(value=100)
        self.peak_z_scale = tk.DoubleVar(value=100)
        self.z_bounce_enabled = tk.BooleanVar(value=False)
        self.z_bounce_depth = tk.DoubleVar(value=150)
        self.z_offset = tk.DoubleVar(value=0)
        self.camera_distance = tk.DoubleVar(value=1000)
        self.bevel_width = tk.DoubleVar(value=0)
        self.bevel_width_title = tk.StringVar(value="自動斜面寬度（%，0＝平面）")
        self.bevel_depth = tk.DoubleVar(value=25)
        self.ridge_mode = tk.BooleanVar(value=False)
        self.profile_hint = tk.StringVar(value="圈內是凸起正面，圈線到外框形成斜面。高度由下方的整體厚度計算。")
        self.raised_contour_points = ()
        self.region_summary = tk.StringVar(value="自動範圍 · 依斜面寬度決定")
        self.bounce_start = tk.DoubleVar(value=.08)
        self.bounce_apex = tk.DoubleVar(value=.4)
        self.bounce_land = tk.DoubleVar(value=.8)
        self.bounce_end = tk.DoubleVar(value=1)
        self.z_bounce_start = tk.DoubleVar(value=.08)
        self.z_bounce_apex = tk.DoubleVar(value=.4)
        self.z_bounce_end = tk.DoubleVar(value=.8)
        self.shade_faces = tk.BooleanVar(value=False)
        self.min_brightness = tk.DoubleVar(value=40)
        self.shade_curve = tk.DoubleVar(value=1)
        self.light_angle = tk.DoubleVar(value=0)
        self.shade_edge = tk.BooleanVar(value=True)
        self.animation = tk.StringVar(value="整圈旋轉")
        self.preview_zoom = tk.DoubleVar(value=100)
        self.show_ground = tk.BooleanVar(value=True)
        self.native_export = tk.BooleanVar(value=bool(self.native))
        self.background = tk.StringVar(value="checker")
        self.status = tk.StringVar(value="載入你的圖片，或先試試範例硬幣。")
        self.summary = tk.StringVar(value="Spine 4.0.56  ·  可編輯網格")
        self.timing_summary = tk.StringVar(value="")
        self.angle_input = tk.StringVar(value="0.0")
        self.time_readout = tk.StringVar(value="0.00 / 2.00 秒")
        self.profile_expanded = tk.BooleanVar(value=False)
        self._settings_scrollareas = []
        self._build()
        self._feedback_toast = FeedbackToast(self._workspace.feedback_host)
        self._feedback_last_text = ""
        self.status.trace_add("write", self._update_status_feedback)
        self._update_status_feedback()
        self.update_model_controls()
        self._rebuild_job = None
        self._render_job = None
        for variable in (self.thickness, self.duration, self.segments, self.axis, self.shape, self.spine_version,
                         self.model_choice, self.diamond_facets, self.diamond_view_tilt, self.diamond_girdle_height,
                         self.diamond_shading, self.diamond_shine_enabled, self.diamond_shine_strength,
                         self.diamond_sparkles_enabled, self.diamond_sparkle_strength,
                         self.coin_shine_enabled, self.coin_shine_strength, self.coin_shine_width,
                         self.coin_shine_angle, self.coin_shine_start, self.coin_shine_end,
                         self.coin_shine_repeat, self.outline_alpha_threshold, self.outline_tolerance,
                         self.edge_orientation, self.base_scale, self.bounce_enabled,
                         self.bounce_height, self.peak_scale, self.landing_squash,
                         self.z_scale, self.peak_z_scale, self.z_bounce_enabled,
                         self.z_bounce_depth, self.z_offset, self.camera_distance,
                         self.bevel_width, self.bevel_depth, self.ridge_mode,
                         self.bounce_start, self.bounce_apex, self.bounce_land, self.bounce_end,
                         self.z_bounce_start, self.z_bounce_apex, self.z_bounce_end,
                         self.shade_faces, self.min_brightness, self.shade_curve,
                         self.light_angle, self.shade_edge):
            variable.trace_add("write", lambda *_: self.schedule_rebuild())
        self.animation.trace_add("write", lambda *_: self.change_animation())
        self.shape.trace_add("write", lambda *_: self.on_shape_change())
        self.spine_version.trace_add("write", lambda *_: self.update_target_display())
        self.model_choice.trace_add("write", lambda *_: self.change_model())
        self.preview_zoom.trace_add("write", lambda *_: self.draw())
        self.show_ground.trace_add("write", lambda *_: self.draw())
        root.bind("<Control-s>", lambda _: self.save_project())
        root.bind("<Control-Shift-S>", lambda _: self.save_project(as_new=True))
        root.bind("<Control-o>", lambda _: self.open_project())
        for key in ("<space>", "<Left>", "<Right>", "<Home>", "<End>", "<F8>"):
            root.bind(key, self.handle_preview_key, add="+")
        root.protocol("WM_DELETE_WINDOW", self.close_app)
        root.after(100, self.load_startup_demo)
        self._preview_poll_job = root.after(10, self._poll_preview)
        root.after(33, self.tick)

    def label(self, parent, text=None, **kwargs):
        options = dict(bg=parent.cget("bg"), fg=TEXT, font=("Microsoft JhengHei UI", 10))
        options.update(kwargs)
        return tk.Label(parent, text=text, **options)

    def button(self, parent, text, command, primary=False, **kwargs):
        return StudioButton(parent, text=text, command=command, primary=primary, **kwargs)

    def _update_status_feedback(self, *_):
        """Show status changes once; preview frames never schedule extra effects."""
        text = self.status.get()
        if text == self._feedback_last_text:
            return
        self._feedback_last_text = text
        if self.busy:
            kind = "busy"
        elif any(word in text for word in ("失敗", "無法", "發生問題", "請檢查", "需為有效")):
            kind = "error"
        elif text.startswith(("編輯檔已", "已交換", "已移除", "已選擇")) or "已建立" in text or "已完成" in text:
            kind = "success"
        else:
            kind = "ready"
        self._workspace.set_status_kind(kind)
        self._workspace.refresh_asset_states()
        if kind == "success":
            if text.startswith("編輯檔已儲存"):
                message = "編輯檔已儲存"
            elif text.startswith("編輯檔已開啟"):
                message = "編輯檔已開啟，已還原素材與設定"
            else:
                message = text.split("：", 1)[0]
            self._feedback_toast.show(message, kind="success")
        elif kind == "error":
            self._feedback_toast.show(text[:130], kind="error", duration=4200)

    def _build(self):
        configure_theme(self.root)
        self._workspace = StudioWorkspace(self, APP_VERSION, PALETTE,
            MODELS, SPINE_TARGETS, ANIMATIONS, DND_FILES)
        common = self._workspace.common
        numbers = tk.Frame(common, bg=PANEL)
        numbers.pack(fill="x", pady=(2, 7))
        for column, (title, variable, lower, upper, step) in enumerate((
                ("厚度 px", self.thickness, 0, 2048, 2),
                ("一圈 秒", self.duration, .2, 30, .1),
                ("輸出大小 %", self.base_scale, 10, 400, 5))):
            group = tk.Frame(numbers, bg=PANEL)
            group.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 4, 0))
            numbers.grid_columnconfigure(column, weight=1, uniform="common")
            self.label(group, title).pack(anchor="w", pady=(0, 3))
            control = ttk.Spinbox(group, from_=lower, to=upper, increment=step,
                                  textvariable=variable, width=6)
            control.pack(fill="x")
            if column == 0:
                self.thickness_control = control
            attach_tooltip(control, (
                "正面與背面之間的厚度；設為 0 可製作平面翻轉。",
                "完成一整圈旋轉的秒數；半圈動畫使用一半時間。",
                "輸出動畫的基礎大小，不影響預覽視窗的檢視縮放。",
            )[column])
        ttk.Combobox(common, textvariable=self.axis,
            values=["左右翻轉 · Y 軸", "上下翻轉 · X 軸"], state="readonly").pack(fill="x", pady=(0, 10))
        basic = self.settings_page("外形")
        diamond = self.settings_page("鑽石")
        self.diamond_page = self.settings_tabs.tabs()[-1]
        self.basic_page = self.settings_tabs.tabs()[0]
        motion = self.settings_page("彈跳")
        self.motion_page = self.settings_tabs.tabs()[-1]
        depth = self.settings_page("Z 軸")
        self.depth_page = self.settings_tabs.tabs()[-1]
        lighting = self.settings_page("光效")
        self.lighting_page = self.settings_tabs.tabs()[-1]
        self.shape_control = ttk.Combobox(basic, textvariable=self.shape,
                   values=list(SHAPES), state="readonly")
        self.field(basic, "物件外形", self.shape_control)
        self.outline_settings = tk.Frame(basic, bg=PANEL)
        self.outline_threshold_control = ttk.Spinbox(self.outline_settings, from_=1, to=255, increment=1,
                                                    textvariable=self.outline_alpha_threshold)
        self.field(self.outline_settings, "透明度門檻（1–255）", self.outline_threshold_control)
        self.outline_tolerance_control = ttk.Spinbox(self.outline_settings, from_=0, to=4, increment=.25,
                                                    textvariable=self.outline_tolerance)
        self.field(self.outline_settings, "輪廓誤差（像素）", self.outline_tolerance_control)
        self.hint(self.outline_settings, "依透明範圍保留凹口；圖片內已上色區域不會自動挖孔。背面留空或與正面為同一張圖時，會自動鏡像背面，讓側壁沿同一實體輪廓接合。不同背面圖須對齊鏡像後的實體外框。")
        self.edge_direction_control = ttk.Combobox(basic, textvariable=self.edge_orientation,
                   values=list(EDGE_DIRECTIONS), state="readonly")
        self.field(basic, "側邊貼圖方向", self.edge_direction_control)
        self.segments_control = ttk.Combobox(basic, textvariable=self.segments,
                   values=[16, 24, 32, 48, 64], state="readonly")
        self.segments_label = self.field(basic, "側邊分段", self.segments_control)
        self.profile_toggle = self.button(basic, "▸ 凸起與斜面設定", self.toggle_profile_settings)
        self.profile_toggle.pack(fill="x", pady=(10, 4))
        self.profile_settings = tk.Frame(basic, bg=PANEL)
        profile = self.profile_settings
        self.ridge_control = tk.Checkbutton(profile, text="石塊模式（前後斜面相接）", variable=self.ridge_mode,
                       command=self.toggle_ridge_mode, bg=PANEL, fg=TEXT, selectcolor=CARD,
                       activebackground=PANEL, activeforeground=TEXT, anchor="w",
                       font=("Microsoft JhengHei UI", 10))
        self.ridge_control.pack(fill="x", pady=(3, 6))
        self.raised_region_button = self.button(profile, "畫凸起範圍…", self.edit_raised_region, primary=True)
        self.raised_region_button.pack(fill="x", pady=(2, 5))
        tk.Label(profile, textvariable=self.region_summary, bg=PANEL, fg=MUTED,
                 anchor="w", wraplength=229, justify="left",
                 font=("Microsoft JhengHei UI", 9)).pack(fill="x", pady=(0, 4))
        self.reset_region_button = self.button(profile, "恢復自動範圍", self.reset_raised_region,
                  variant="ghost", pady=5, font=("Microsoft JhengHei UI", 9))
        self.reset_region_button.pack(fill="x", pady=(0, 8))
        self.label(profile, textvariable=self.bevel_width_title).pack(anchor="w", pady=(0, 3))
        self.bevel_width_control = ttk.Spinbox(profile, from_=0, to=20, increment=1, textvariable=self.bevel_width)
        self.bevel_width_control.pack(fill="x", ipady=1, pady=(0, 5))
        depth_control = tk.Frame(profile, bg=PANEL)
        self.bevel_depth_control = ttk.Spinbox(depth_control, from_=0, to=45, increment=5,
                                               textvariable=self.bevel_depth)
        self.bevel_depth_control.pack(fill="x")
        self.ridge_height_label = tk.Label(depth_control, text="50%（固定 · 前後斜面相接）",
                                           bg=CARD, fg=TEXT, anchor="w", padx=6, pady=6,
                                           font=("Microsoft JhengHei UI", 10))
        self.field(profile, "凸起高度（占厚度 %）", depth_control)
        tk.Label(profile, textvariable=self.profile_hint,
                 bg=PANEL, fg=MUTED, wraplength=229, justify="left",
                 font=("Microsoft JhengHei UI", 9)).pack(fill="x", pady=(0, 8))
        self.button(diamond, "調整鑽石輪廓…", self.edit_diamond, primary=True).pack(fill="x", pady=(0, 6))
        self.button(diamond, "畫切面與反光方向…", self.edit_diamond_cuts).pack(fill="x", pady=(0, 6))
        tk.Label(diamond, textvariable=self.diamond_summary, bg=PANEL, fg=MUTED, justify="left",
                 wraplength=229, font=("Microsoft JhengHei UI", 9)).pack(fill="x", pady=(0, 8))
        self.field(diamond, "切面數", ttk.Combobox(diamond, textvariable=self.diamond_facets,
                   values=[4, 6, 8, 10, 12, 16], state="readonly"))
        self.field(diamond, "俯視角度（°）", ttk.Spinbox(diamond, from_=0, to=35, increment=2,
                                                      textvariable=self.diamond_view_tilt))
        self.field(diamond, "腰圍厚度（占圖片高度 %）", ttk.Spinbox(diamond, from_=0, to=12, increment=.5,
                                                             textvariable=self.diamond_girdle_height))
        self.field(diamond, "切面明暗強度（%）", ttk.Spinbox(diamond, from_=0, to=100, increment=5,
                                                           textvariable=self.diamond_shading))
        self.check(diamond, "啟用掃光", self.diamond_shine_enabled)
        self.field(diamond, "掃光強度（%）", ttk.Spinbox(diamond, from_=0, to=100, increment=5,
                                                      textvariable=self.diamond_shine_strength))
        self.check(diamond, "啟用星芒", self.diamond_sparkles_enabled)
        self.field(diamond, "星芒強度（%）", ttk.Spinbox(diamond, from_=0, to=100, increment=5,
                                                      textvariable=self.diamond_sparkle_strength))
        self.hint(diamond, "輪廓編輯會顯示真正的旋轉切面，可分別對齊台面與腰部的前後緣。套用後先停在正面比對；反光分區另控制各面明暗。")
        self.check(motion, "啟用 Y 軸彈跳與落地", self.bounce_enabled)
        self.field(motion, "Y 軸彈跳高度（像素）", ttk.Spinbox(motion, from_=0, to=4096, increment=10,
                                                       textvariable=self.bounce_height))
        self.field(motion, "空中放大（相對基礎，%）", ttk.Spinbox(motion, from_=50, to=300, increment=5,
                                                             textvariable=self.peak_scale))
        self.field(motion, "落地壓縮（%，0＝不壓縮）", ttk.Spinbox(motion, from_=0, to=45, increment=2,
                                                              textvariable=self.landing_squash))
        self.button(motion, "設定 Y／Z 彈跳時間…", self.timing_dialog).pack(fill="x", pady=(4, 4))
        self.hint(motion, "Y 軸控制上下彈跳與落地，和 Z 軸各自獨立。可關閉此項，只使用 Z 軸靠近／遠離。")
        self.field(depth, "前後厚度縮放（%）", ttk.Spinbox(depth, from_=10, to=400, increment=5,
                                                       textvariable=self.z_scale))
        self.field(depth, "鏡頭距離（像素）", ttk.Spinbox(depth, from_=100, to=20000, increment=100,
                                                      textvariable=self.camera_distance))
        self.field(depth, "基礎 Z 位置（正＝靠近）", ttk.Spinbox(depth, from_=-10000, to=18000, increment=50,
                                                            textvariable=self.z_offset))
        self.check(depth, "啟用 Z 軸靠近／遠離彈跳", self.z_bounce_enabled)
        self.button(depth, "設定 Y／Z 彈跳時間…", self.timing_dialog).pack(fill="x", pady=(2, 7))
        self.field(depth, "Z 彈跳幅度（正＝靠近）", ttk.Spinbox(depth, from_=-10000, to=18000, increment=50,
                                                           textvariable=self.z_bounce_depth))
        self.field(depth, "Z 彈跳頂點厚度（相對基礎，%）", ttk.Spinbox(depth, from_=25, to=400, increment=5,
                                                                  textvariable=self.peak_z_scale))
        self.hint(depth, "Z 軸以近大遠小呈現深度移動，正面大小與厚度縮放分開控制。靠近位置需小於鏡頭距離的 90%。")
        self.label(lighting, "硬幣掃光").pack(anchor="w", pady=(0, 8))
        self.button(lighting, "試用硬幣掃光", lambda: self.load_demo("shine"), primary=True).pack(fill="x", pady=(0, 8))
        self.check(lighting, "啟用正反面掃光", self.coin_shine_enabled)
        self.field(lighting, "掃光強度（%）", ttk.Spinbox(lighting, from_=0, to=100, increment=5,
                                                        textvariable=self.coin_shine_strength))
        self.field(lighting, "光帶寬度（占圖寬 %）", ttk.Spinbox(lighting, from_=5, to=100, increment=5,
                                                              textvariable=self.coin_shine_width))
        self.field(lighting, "光帶傾斜角度（°）", ttk.Spinbox(lighting, from_=-180, to=180, increment=5,
                                                          textvariable=self.coin_shine_angle))
        self.button(lighting, "掃光時間…", self.coin_shine_timing_dialog).pack(fill="x", pady=(3, 5))
        tk.Label(lighting, textvariable=self.coin_shine_timing_summary, bg=PANEL, fg=MUTED,
                 justify="left", wraplength=229, font=("Microsoft JhengHei UI", 9)).pack(anchor="w")
        self.hint(lighting, "亮帶沿正背面旋轉，並保留透明輪廓。適用一般物件；鑽石掃光仍在鑽石分頁調整。")
        self.label(lighting, "轉向明暗").pack(anchor="w", pady=(18, 8))
        self.check(lighting, "啟用正反面轉向明暗", self.shade_faces)
        self.field(lighting, "最暗亮度（%）", ttk.Spinbox(lighting, from_=0, to=100, increment=5,
                                                     textvariable=self.min_brightness))
        self.field(lighting, "變化曲線（1＝標準）", ttk.Spinbox(lighting, from_=0.2, to=4, increment=.1,
                                                           textvariable=self.shade_curve))
        self.field(lighting, "光源角度（°）", ttk.Spinbox(lighting, from_=-180, to=180, increment=15,
                                                      textvariable=self.light_angle))
        self.check(lighting, "啟用側邊陰影", self.shade_edge)
        self.hint(lighting, "0° 光源：正面朝向觀眾時最亮，轉進側面時漸暗，從側面轉出時恢復明亮。最暗亮度 100% 可保持原圖。")
        self._install_settings_wheel()
        self.slider.bind("<ButtonPress-1>", self.begin_angle_edit, add="+")
        self.slider.bind("<KeyPress>", self.begin_angle_edit, add="+")
        self.preview.bind("<Button-1>", lambda _: self.preview.focus_set(), add="+")
        self.preview.bind("<MouseWheel>", self.zoom_preview)

    def zoom_preview(self, event):
        if self.busy:
            return 'break'
        try:
            current = float(self.preview_zoom.get())
        except (tk.TclError, ValueError):
            current = 100.
        if event.delta:
            self.preview_zoom.set(min(250., max(25., current + (10. if event.delta > 0 else -10.))))
        return 'break'

    def _install_settings_wheel(self):
        """Scroll the inspector before Spinbox/Combobox class bindings run."""
        for index, (inner, canvas) in enumerate(self._settings_scrollareas):
            tag = f"StudioInspectorWheel{id(self)}_{index}"

            def scroll(event, target=canvas):
                if event.delta:
                    units = max(1, round(abs(event.delta) / 120)) * (1 if event.delta < 0 else -1)
                    target.yview_scroll(units * 3, "units")
                return "break"

            self.root.bind_class(tag, "<MouseWheel>", scroll)

            def install(widget):
                widget.bindtags((tag,) + tuple(widget.bindtags()))
                for child in widget.winfo_children():
                    install(child)

            install(inner)
            canvas.bind("<MouseWheel>", scroll)

        def tag_children(widget, tag):
            widget.bindtags((tag,) + tuple(widget.bindtags()))
            for child in widget.winfo_children():
                tag_children(child, tag)

        def scroll_current(event):
            current = self.settings_tabs.select()
            for inner, target in self._settings_scrollareas:
                if str(target.master) == current:
                    if event.delta:
                        units = max(1, round(abs(event.delta) / 120)) * (1 if event.delta < 0 else -1)
                        target.yview_scroll(units * 3, 'units')
                    break
            return 'break'

        common_tag = f"StudioCommonWheel{id(self)}"
        self.root.bind_class(common_tag, '<MouseWheel>', scroll_current)
        tag_children(self._workspace.common, common_tag)
        output_tag = f"StudioOutputWheel{id(self)}"
        self.root.bind_class(output_tag, '<MouseWheel>', lambda _: 'break')
        tag_children(self._workspace.export_bar, output_tag)

    def load_startup_demo(self):
        if self._closed or self.paths['front']:
            return
        self.load_demo('shine')
        self.settings_tabs.select(self.basic_page)

    def toggle_profile_settings(self):
        self.profile_expanded.set(not self.profile_expanded.get())
        self._update_profile_visibility()

    def _update_profile_visibility(self):
        if not hasattr(self, "profile_toggle"):
            return
        available = self.model_choice.get() != "鑽石" and self.selected_shape() != "irregular"
        if not available:
            self.profile_toggle.pack_forget()
            self.profile_settings.pack_forget()
            return
        self.profile_toggle.pack(after=self.segments_control, fill="x", pady=(10, 4))
        expanded = self.profile_expanded.get()
        self.profile_toggle.configure(text=("▾" if expanded else "▸") + " 凸起與斜面設定")
        if expanded:
            self.profile_settings.pack(after=self.profile_toggle, fill="x")
        else:
            self.profile_settings.pack_forget()

    def field(self, parent, label, widget):
        title = self.label(parent, label, fg=MUTED, font=("Microsoft JhengHei UI", 9))
        title.pack(anchor="w", pady=(3, 4))
        widget.pack(fill="x", ipady=1, pady=(0, 7))
        return title

    def settings_page(self, title):
        outer = tk.Frame(self.settings_tabs, bg=PANEL)
        self.settings_tabs.add(outer, text=title)
        canvas = tk.Canvas(outer, bg=PANEL, bd=0, highlightthickness=0, height=1, width=1)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        inner = tk.Frame(canvas, bg=PANEL, pady=10, padx=2)
        item = canvas.create_window(0, 0, anchor="nw", window=inner)
        inner.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        self._settings_scrollareas.append((inner, canvas))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(item, width=e.width))
        return inner

    def check(self, parent, text, variable):
        tk.Checkbutton(parent, text=text, variable=variable, bg=PANEL, fg=TEXT,
                       selectcolor=CARD, activebackground=CARD, activeforeground=ACCENT,
                       highlightcolor=ACCENT, highlightbackground=PANEL, highlightthickness=1,
                       cursor="hand2", font=("Microsoft JhengHei UI", 10), anchor="w").pack(fill="x", pady=(0, 10))

    def hint(self, parent, text):
        label = tk.Label(parent, text=text, bg=PANEL, fg=MUTED, justify="left", wraplength=280,
                         font=("Microsoft JhengHei UI", 9))
        label.pack(fill="x", pady=(6, 4))
        label.bind("<Configure>", lambda event: label.configure(wraplength=max(160, event.width - 2)))

    def number(self, variable, label, minimum, maximum):
        try:
            value = float(variable.get())
        except (tk.TclError, ValueError):
            raise ValueError(f"{label}請輸入有效的數值。") from None
        if not math.isfinite(value) or not minimum <= value <= maximum:
            raise ValueError(f"{label}需介於 {minimum:g} 到 {maximum:g}。")
        return value

    def selected_shape(self):
        label = self.shape.get()
        shape = SHAPES.get(label, SHAPE_ALIASES.get(label))
        if shape is None:
            raise ValueError("請選擇有效的物件外形。")
        return shape

    def get_options(self):
        name = self.name.get().strip()
        if not name or len(name) > 80 or any(c in name for c in '<>:"/\\|?*') or name in (".", ".."):
            raise ValueError("專案名稱請使用 1–80 個字，避免路徑或特殊符號。")
        thickness = self.number(self.thickness, "厚度（像素）", 0, 2048)
        duration = self.number(self.duration, "一圈時間（秒）", .2, 30)
        segments = int(self.number(self.segments, "側邊分段", 8, 128))
        camera_distance = self.number(self.camera_distance, "鏡頭距離", 100, 20000)
        z_offset = self.number(self.z_offset, "基礎 Z 位置", -10000, 18000)
        z_depth = self.number(self.z_bounce_depth, "Z 彈跳幅度", -10000, 18000)
        nearest_z = z_offset + (max(0, z_depth) if self.z_bounce_enabled.get() else 0)
        if nearest_z > .9 * camera_distance:
            raise ValueError("Z 位置與彈跳後的最近位置，需小於鏡頭距離的 90%。請減少 Z 位置或增加鏡頭距離。")
        family = self.spine_version.get() if hasattr(self, "spine_version") else "4.0"
        if family not in SPINE_TARGETS:
            raise ValueError("請選擇 Spine 3.8、4.0 或 4.2。")
        diamond_values = dict(getattr(self, "diamond_guides", {}))
        for field, title, minimum, maximum, divisor in (
                ("diamond_facets", "鑽石切面數", 4, 16, 1),
                ("diamond_view_tilt", "俯視角度", 0, 35, 1),
                ("diamond_girdle_height", "腰圍厚度（%）", 0, 12, 100),
                ("diamond_shading", "切面明暗強度（%）", 0, 100, 100),
                ("diamond_shine_strength", "掃光強度（%）", 0, 100, 100),
                ("diamond_sparkle_strength", "星芒強度（%）", 0, 100, 100)):
            if hasattr(self, field):
                value = self.number(getattr(self, field), title, minimum, maximum) / divisor
                diamond_values[field] = int(value) if field == "diamond_facets" else value
        for field in ("diamond_shine_enabled", "diamond_sparkles_enabled"):
            if hasattr(self, field):
                diamond_values[field] = bool(getattr(self, field).get())
        base_options = getattr(self, "extra_options", TurnOptions())
        coin_values = {}
        for field, title, minimum, maximum, divisor in (
                ("coin_shine_strength", "掃光強度（%）", 0, 100, 100),
                ("coin_shine_width", "光帶寬度（%）", 5, 100, 100),
                ("coin_shine_angle", "光帶傾斜角度", -180, 180, 1),
                ("coin_shine_start", "掃光開始時間比例", 0, 1, 1),
                ("coin_shine_end", "掃光結束時間比例", 0, 1, 1),
                ("coin_shine_repeat", "掃光次數", 1, 4, 1)):
            if hasattr(self, field):
                value = self.number(getattr(self, field), title, minimum, maximum) / divisor
                if field == "coin_shine_repeat" and int(value) != value:
                    raise ValueError("掃光次數請使用 1 到 4 的整數。")
                coin_values[field] = int(value) if field == "coin_shine_repeat" else value
        if hasattr(self, "coin_shine_enabled"):
            coin_values["coin_shine_enabled"] = bool(self.coin_shine_enabled.get())
        if coin_values.get("coin_shine_start", base_options.coin_shine_start) >= coin_values.get("coin_shine_end", base_options.coin_shine_end):
            raise ValueError("掃光時間需為：開始 < 結束。")
        model = MODELS[self.model_choice.get()] if hasattr(self, "model_choice") else base_options.model
        shape = self.selected_shape()
        irregular = model == "extrusion" and shape == "irregular"
        outline_threshold = (self.number(self.outline_alpha_threshold, "透明度門檻", 1, 255)
                             if hasattr(self, "outline_alpha_threshold") else base_options.outline_alpha_threshold)
        if int(outline_threshold) != outline_threshold:
            raise ValueError("透明度門檻請使用 1 到 255 的整數。")
        outline_tolerance = (self.number(self.outline_tolerance, "輪廓誤差（像素）", 0, 4)
                             if hasattr(self, "outline_tolerance") else base_options.outline_tolerance)
        return replace(getattr(self, "extra_options", TurnOptions()),
                           name=name, thickness=thickness, duration=duration, segments=segments,
                           model=model, **diamond_values, **coin_values,
                           spine_version=self.selected_target_version(),
                           axis="x" if "X" in self.axis.get() else "y",
                           shape=shape, outline_alpha_threshold=int(outline_threshold),
                           outline_tolerance=outline_tolerance,
                           irregular_contours=(base_options.irregular_contours
                               if outline_threshold == base_options.outline_alpha_threshold
                               and outline_tolerance == base_options.outline_tolerance else ()),
                           edge_orientation=EDGE_DIRECTIONS[self.edge_orientation.get()],
                           base_scale=self.number(self.base_scale, "基礎縮放（%）", 10, 400)/100,
                           bounce_enabled=self.bounce_enabled.get(),
                           bounce_height=self.number(self.bounce_height, "彈跳高度（像素）", 0, 4096),
                           peak_scale=self.number(self.peak_scale, "空中放大（%）", 50, 300)/100,
                           landing_squash=self.number(self.landing_squash, "落地壓縮（%）", 0, 45)/100,
                           z_scale=self.number(self.z_scale, "前後厚度縮放（%）", 10, 400)/100,
                           peak_z_scale=self.number(self.peak_z_scale, "Z 彈跳頂點厚度（%）", 25, 400)/100,
                           z_bounce_enabled=self.z_bounce_enabled.get(),
                           z_bounce_depth=z_depth, z_offset=z_offset, camera_distance=camera_distance,
                           bevel_width=(0 if irregular else self.number(self.bevel_width, "斜面寬度（%）", 0, 20)/100),
                           bevel_depth=self.number(self.bevel_depth, "凸起高度（%）", 0, 45)/100,
                           side_mode=("ridge" if not irregular and getattr(self, "ridge_mode", None)
                                      and self.ridge_mode.get() else "strip"),
                           raised_contour_points=(getattr(self, "raised_contour_points", ())
                                                  if shape == "polygon" else ()),
                           bounce_start=self.number(self.bounce_start, "Y 起跳時間比例", 0, 1),
                           bounce_apex=self.number(self.bounce_apex, "Y 高點時間比例", 0, 1),
                           bounce_land=self.number(self.bounce_land, "Y 落地時間比例", 0, 1),
                           bounce_end=self.number(self.bounce_end, "Y 恢復時間比例", 0, 1),
                           z_bounce_start=self.number(self.z_bounce_start, "Z 開始時間比例", 0, 1),
                           z_bounce_apex=self.number(self.z_bounce_apex, "Z 高點時間比例", 0, 1),
                           z_bounce_end=self.number(self.z_bounce_end, "Z 返回時間比例", 0, 1),
                           shade_faces=self.shade_faces.get(),
                           min_brightness=self.number(self.min_brightness, "最暗亮度（%）", 0, 100)/100,
                           shade_curve=self.number(self.shade_curve, "變化曲線", .2, 4),
                           light_angle=self.number(self.light_angle, "光源角度（°）", -180, 180),
                           shade_edge=self.shade_edge.get())

    def selected_target_version(self):
        family = self.spine_version.get() if hasattr(self, "spine_version") else "4.0"
        previous = getattr(self, "extra_options", TurnOptions()).spine_version
        if ".".join(previous.split(".")[:2]) == family:
            return normalize_options({"spine_version": previous}).spine_version
        return SPINE_TARGETS[family]

    def update_target_display(self):
        self.spine_revision.set(f"請用 Spine {self.selected_target_version()} 開啟")

    def project_ui_state(self):
        state = dict(self._loaded_project.ui_state) if self._loaded_project is not None else {}
        state.update({"animation": ANIMATIONS[self.animation.get()], "background": self.background.get(),
                "preview_zoom": self.number(self.preview_zoom, "預覽縮放", 25, 250),
                "show_ground": bool(self.show_ground.get()), "native_export": bool(self.native_export.get()),
                "progress": self.progress, "playing": bool(self.playing)})
        return state

    def update_project_title(self):
        suffix = Path(self.project_path).name if self.project_path else "圖片翻轉製作器"
        self.root.title(f"Spine Turn Studio {APP_VERSION} · {suffix}")

    def save_project(self, as_new=False):
        try:
            if not self.paths["front"]:
                raise ValueError("請先放入正面圖片。")
            options = self.get_options()
            prepared = prepare_images(self.paths["front"], self.paths["back"], self.paths["edge"], options)
            resolved = resolve_options(prepared, options)
            if options.shape == "irregular" and options.model != "diamond":
                options = resolved
            ui_state = self.project_ui_state()
            path = None if as_new else self.project_path
            if not path:
                previous = Path(self.project_path) if self.project_path else None
                path = filedialog.asksaveasfilename(parent=self.root, title="儲存編輯檔（包含素材與設定）",
                    defaultextension=".spturn", filetypes=[("Spine Turn 編輯檔", "*.spturn")],
                    initialdir=str(previous.parent if previous else Path.home() / "Documents"),
                    initialfile=previous.name if previous else f"{options.name}.spturn")
            if not path:
                return
            save_editable_project(path, self.paths, options, ui_state)
            self.project_path = str(Path(path).resolve())
            self.update_project_title()
            self.status.set(f"編輯檔已儲存（包含素材、範圍與動畫設定）：{self.project_path}")
        except Exception as exc:
            self.status.set(f"無法儲存編輯檔：{exc}")
            messagebox.showerror("無法儲存編輯檔", str(exc), parent=self.root)

    def open_project(self):
        if self.busy:
            self.status.set("正在匯出，完成後即可開啟其他編輯檔。")
            return
        path = filedialog.askopenfilename(parent=self.root, title="開啟 Spine Turn 編輯檔",
            filetypes=[("Spine Turn 編輯檔", "*.spturn"), ("所有檔案", "*.*")],
            initialdir=str(Path(self.project_path).parent if self.project_path else Path.home() / "Documents"))
        if not path:
            return
        loaded = None
        try:
            loaded = load_editable_project(path)
            # Validate all embedded assets and geometry before changing the current workspace.
            prepared = prepare_images(loaded.paths["front"], loaded.paths["back"], loaded.paths["edge"], loaded.options)
            resolve_options(prepared, loaded.options)
            self.apply_loaded_project(loaded, path)
        except Exception as exc:
            if loaded is not None and loaded is not self._loaded_project:
                loaded.close()
            messagebox.showerror("無法開啟編輯檔", str(exc), parent=self.root)

    def apply_loaded_project(self, loaded, path):
        options, ui = normalize_options(loaded.options), loaded.ui_state
        values = {
            "model_choice": next(key for key, value in MODELS.items() if value == options.model),
            "diamond_facets": options.diamond_facets, "diamond_view_tilt": options.diamond_view_tilt,
            "diamond_girdle_height": options.diamond_girdle_height * 100,
            "diamond_shading": options.diamond_shading * 100,
            "diamond_shine_enabled": options.diamond_shine_enabled,
            "diamond_shine_strength": options.diamond_shine_strength * 100,
            "diamond_sparkles_enabled": options.diamond_sparkles_enabled,
            "diamond_sparkle_strength": options.diamond_sparkle_strength * 100,
            "coin_shine_enabled": options.coin_shine_enabled,
            "coin_shine_strength": options.coin_shine_strength * 100,
            "coin_shine_width": options.coin_shine_width * 100,
            "coin_shine_angle": options.coin_shine_angle,
            "coin_shine_start": options.coin_shine_start,
            "coin_shine_end": options.coin_shine_end,
            "coin_shine_repeat": options.coin_shine_repeat,
            "name": options.name, "thickness": options.thickness, "duration": options.duration,
            "segments": options.segments, "spine_version": ".".join(options.spine_version.split(".")[:2]),
            "axis": "上下翻轉 · X 軸" if options.axis == "x" else "左右翻轉 · Y 軸",
            "shape": next(label for label, value in SHAPES.items() if value == options.shape),
            "outline_alpha_threshold": options.outline_alpha_threshold,
            "outline_tolerance": options.outline_tolerance,
            "edge_orientation": next(key for key, value in EDGE_DIRECTIONS.items() if value == options.edge_orientation),
            "base_scale": options.base_scale * 100, "bounce_enabled": options.bounce_enabled,
            "bounce_height": options.bounce_height, "peak_scale": options.peak_scale * 100,
            "landing_squash": options.landing_squash * 100, "z_scale": options.z_scale * 100,
            "peak_z_scale": options.peak_z_scale * 100, "z_bounce_enabled": options.z_bounce_enabled,
            "z_bounce_depth": options.z_bounce_depth, "z_offset": options.z_offset,
            "camera_distance": options.camera_distance, "bevel_width": options.bevel_width * 100,
            "bevel_depth": options.bevel_depth * 100, "ridge_mode": options.side_mode == "ridge",
            "bounce_start": options.bounce_start, "bounce_apex": options.bounce_apex,
            "bounce_land": options.bounce_land, "bounce_end": options.bounce_end,
            "z_bounce_start": options.z_bounce_start, "z_bounce_apex": options.z_bounce_apex,
            "z_bounce_end": options.z_bounce_end, "shade_faces": options.shade_faces,
            "min_brightness": options.min_brightness * 100, "shade_curve": options.shade_curve,
            "light_angle": options.light_angle, "shade_edge": options.shade_edge,
            "animation": next(key for key, value in ANIMATIONS.items() if value == ui.get("animation", "rotate_loop")),
            "background": ui.get("background", "checker"), "preview_zoom": ui.get("preview_zoom", 100),
            "show_ground": ui.get("show_ground", True), "native_export": ui.get("native_export", bool(self.native))}
        self.validate_project_controls(values, options)
        previous = self._loaded_project
        self._loading_project = True
        if self._rebuild_job:
            self.root.after_cancel(self._rebuild_job)
            self._rebuild_job = None
        try:
            for kind, image_path in loaded.paths.items():
                if image_path:
                    if not self.set_image(kind, image_path):
                        raise ValueError("編輯檔素材無法顯示。")
                else:
                    self.clear_image(kind)
            self.extra_options = options
            self.diamond_guides = {key: getattr(options, key) for key in DIAMOND_GUIDE_FIELDS}
            for name, value in values.items():
                getattr(self, name).set(value)
            self.raised_contour_points = tuple(tuple(point) for point in options.raised_contour_points)
            self.region_summary.set(f"手動畫線 · {len(self.raised_contour_points)} 點 · 自動寬度暫停使用"
                                    if self.raised_contour_points else "自動範圍 · 依斜面寬度決定")
            self._loaded_project = loaded
            self.project_path = str(Path(path).resolve())
        finally:
            self._loading_project = False
        self.update_profile_controls()
        self.update_model_controls(select=True)
        self.update_diamond_summary()
        self.update_target_display()
        self.rebuild()
        self.progress = float(ui.get("progress", 0))
        self.playing = bool(ui.get("playing", False))
        self.play_button.configure(text="暫停" if self.playing else "播放")
        self.angle = self.angle_at_progress()
        self.slider.set(self.progress * 360)
        self.last_tick = time.perf_counter()
        self.update_project_title()
        self.draw()
        self.status.set(f"編輯檔已開啟，可繼續修改並重新匯出：{Path(path).name}")
        if previous is not None:
            previous.close()

    @staticmethod
    def validate_project_controls(values, options):
        # Reuse the form validator on plain values before touching any widgets.
        snapshot = App.__new__(App)
        snapshot.extra_options = options
        snapshot.raised_contour_points = options.raised_contour_points
        for name, value in values.items():
            setattr(snapshot, name, SimpleNamespace(get=lambda value=value: value))
        try:
            snapshot.get_options()
        except ValueError as exc:
            raise ValueError(f"編輯檔的設定超出目前介面範圍：{exc}") from None

    def close_app(self):
        self._closed = True
        if worker := getattr(self, '_preview_worker', None):
            worker.close()
        if job := getattr(self, '_preview_poll_job', None):
            self.root.after_cancel(job)
        if self._loaded_project is not None:
            self._loaded_project.close()
        self.root.destroy()

    def choose_image(self, kind):
        path = filedialog.askopenfilename(title="選擇圖片", filetypes=[("圖片", "*.png *.webp *.jpg *.jpeg *.bmp"), ("所有檔案", "*.*")])
        if path:
            self.set_image(kind, path)
            self.rebuild()

    def drop_image(self, event, kind):
        paths = self.root.tk.splitlist(event.data)
        if paths:
            self.set_image(kind, paths[0])
            self.rebuild()

    def set_image(self, kind, path):
        try:
            with Image.open(path) as source:
                thumbnail = source.convert("RGBA")
                width, height = getattr(self, 'asset_preview_size', (210, 78))
                thumbnail.thumbnail((width - 8, height - 8), Image.Resampling.LANCZOS)
                bg = Image.new("RGBA", (width, height), CARD)
                bg.alpha_composite(thumbnail, ((width-thumbnail.width)//2, (height-thumbnail.height)//2))
                photo = ImageTk.PhotoImage(bg)
            resolved_path = str(Path(path).resolve())
            if kind == "front" and self.paths["front"] != resolved_path:
                self.raised_contour_points = ()
                self.region_summary.set("自動範圍 · 依斜面寬度決定")
                self.extra_options = replace(self.extra_options, diamond_cut_regions=(), irregular_contours=())
                if hasattr(self, "diamond_summary"):
                    self.update_diamond_summary()
            self.paths[kind] = resolved_path
            self.thumbs[kind] = photo
            preview, filename = self.cards[kind]
            preview.configure(image=photo, text="", height=height, width=width)
            filename.configure(text=Path(path).name)
            if workspace := getattr(self, "_workspace", None):
                workspace.refresh_asset_states()
            return True
        except Exception as exc:
            self.status.set(f"無法讀取圖片：{exc}")
            return False

    def clear_image(self, kind):
        self.paths[kind] = None
        self.thumbs.pop(kind, None)
        preview, filename = self.cards[kind]
        preview.configure(image="", text="＋", height=3, width=7)
        filename.configure(text={"front": "拖入正面圖片開始", "back": "空白時沿用正面", "edge": "空白時使用金色側邊"}[kind])
        if workspace := getattr(self, "_workspace", None):
            workspace.refresh_asset_states()

    def clear_optional(self):
        for kind in ("back", "edge"):
            self.clear_image(kind)
        self.rebuild()

    def load_demo(self, mode="y"):
        if self.busy:
            return
        self.raised_contour_points = ()
        self.region_summary.set("自動範圍 · 依斜面寬度決定")
        for kind in self.paths:
            if mode == "diamond" and kind != "front":
                self.clear_image(kind)
                continue
            asset_name = ("demo-diamond-aligned.png" if mode == "diamond" else
                          f"demo-irregular-{kind}.png" if mode == "irregular" and kind in ("front", "back") else
                          f"demo-{kind}.png")
            path = APP_DIR / "assets" / asset_name
            if path.exists():
                self.set_image(kind, str(path))
        self.extra_options = (replace(TurnOptions(), trim_transparent=False,
            diamond_ring_phase=22.5, diamond_view_tilt=24) if mode == "diamond" else
            replace(TurnOptions(), coin_shine_enabled=True, coin_shine_start=0,
                    coin_shine_end=.25) if mode == "shine" else
            replace(TurnOptions(), shape="irregular", outline_alpha_threshold=16,
                    outline_tolerance=1) if mode == "irregular" else TurnOptions())
        self.shape.set(next(label for label, value in SHAPES.items() if value == self.extra_options.shape))
        self.outline_alpha_threshold.set(self.extra_options.outline_alpha_threshold)
        self.outline_tolerance.set(self.extra_options.outline_tolerance)
        for name in ("coin_shine_enabled", "coin_shine_angle", "coin_shine_start", "coin_shine_end", "coin_shine_repeat"):
            if hasattr(self, name):
                getattr(self, name).set(getattr(self.extra_options, name))
        for name in ("coin_shine_strength", "coin_shine_width"):
            if hasattr(self, name):
                getattr(self, name).set(getattr(self.extra_options, name) * 100)
        self.diamond_guides = {}
        if hasattr(self, "model_choice"):
            self.model_choice.set("鑽石" if mode == "diamond" else "一般物件")
            defaults = self.extra_options
            for name in ("diamond_facets", "diamond_view_tilt", "diamond_shine_enabled", "diamond_sparkles_enabled"):
                getattr(self, name).set(getattr(defaults, name))
            for name in ("diamond_girdle_height", "diamond_shading", "diamond_shine_strength", "diamond_sparkle_strength"):
                getattr(self, name).set(getattr(defaults, name) * 100)
            self.update_diamond_summary()
            self.update_model_controls(select=True)
            self.name.set("diamond" if mode == "diamond" else "coin_shine" if mode == "shine" else
                          "irregular" if mode == "irregular" else "coin")
        self.update_target_display()
        self.project_path = None
        self.update_project_title()
        if self._loaded_project is not None:
            self._loaded_project.close()
            self._loaded_project = None
        self.edge_orientation.set("橫向長條")
        self.bounce_enabled.set(mode == "y")
        self.bounce_height.set(100)
        self.base_scale.set(100)
        self.peak_scale.set(115)
        self.landing_squash.set(12)
        self.z_scale.set(100)
        self.peak_z_scale.set(100)
        self.z_bounce_enabled.set(mode == "z")
        self.z_bounce_depth.set(150)
        self.z_offset.set(0)
        self.camera_distance.set(1000)
        self.bevel_width.set(0)
        self.bevel_depth.set(25)
        self.ridge_mode.set(False)
        self.update_profile_controls()
        self.bounce_start.set(.08)
        self.bounce_apex.set(.4)
        self.bounce_land.set(.8)
        self.bounce_end.set(1)
        self.z_bounce_start.set(.08)
        self.z_bounce_apex.set(.4)
        self.z_bounce_end.set(.8)
        self.shade_faces.set(True)
        self.min_brightness.set(40)
        self.shade_curve.set(1)
        self.light_angle.set(0)
        self.animation.set("整圈旋轉")
        self.change_animation()
        self.rebuild()
        if mode == "shine" and hasattr(self, "lighting_page"):
            self.settings_tabs.select(self.lighting_page)

    def reset_raised_region(self):
        self.raised_contour_points = ()
        self.region_summary.set("自動範圍 · 依斜面寬度決定")
        self.rebuild()

    def update_profile_controls(self):
        if self.selected_shape() == "irregular" and self.model_choice.get() != "鑽石":
            self.bevel_width_title.set("自動斜面寬度（不規則模式停用）")
            self.ridge_height_label.pack_forget()
            self.bevel_depth_control.pack(fill="x")
            self.profile_hint.set("依透明輪廓建立厚度側壁；斜面、石塊模式與凸起範圍暫不混用。")
        elif self.ridge_mode.get():
            self.bevel_width_title.set("自動斜面寬度（%，0＝自動）")
            self.bevel_depth_control.pack_forget()
            self.ridge_height_label.pack(fill="x")
            self.profile_hint.set("不顯示中間側壁，前後斜面直接相接。凸起高度固定為厚度的 50%；沒有圈選時先使用自動範圍。")
        else:
            self.bevel_width_title.set("自動斜面寬度（%，0＝平面）")
            self.ridge_height_label.pack_forget()
            self.bevel_depth_control.pack(fill="x")
            self.profile_hint.set("圈內是凸起正面，圈線到外框形成斜面。高度由下方的整體厚度計算。")

    def toggle_ridge_mode(self):
        if self.selected_shape() == "irregular":
            self.ridge_mode.set(False)
            self.update_profile_controls()
            return
        if self.ridge_mode.get():
            self.shape.set(next(label for label, value in SHAPES.items() if value == "polygon"))
        self.update_profile_controls()
        self.schedule_rebuild()

    def on_shape_change(self):
        if self._loading_project:
            return
        if self.ridge_mode.get() and self.selected_shape() != "polygon":
            self.ridge_mode.set(False)
        self.update_profile_controls()
        self.update_model_controls()

    def change_model(self):
        if self._loading_project:
            return
        self.update_profile_controls()
        self.update_model_controls(select=True)
        self.schedule_rebuild()

    def update_model_controls(self, select=False):
        diamond = self.model_choice.get() == "鑽石"
        irregular = not diamond and self.selected_shape() == "irregular"
        for widget in (self.ridge_control, self.raised_region_button, self.reset_region_button,
                       self.bevel_width_control, self.bevel_depth_control):
            widget.configure(state="disabled" if diamond or irregular else "normal")
        self.thickness_control.configure(state="disabled" if diamond else "normal")
        for widget in (self.shape_control, self.edge_direction_control, self.segments_control):
            widget.configure(state="disabled" if diamond else "readonly")
        for name in ("outline_threshold_control", "outline_tolerance_control"):
            if hasattr(self, name):
                getattr(self, name).configure(state="normal" if irregular else "disabled")
        if hasattr(self, "outline_settings"):
            if irregular:
                self.outline_settings.pack(after=self.shape_control, fill="x", pady=(0, 6))
            else:
                self.outline_settings.pack_forget()
        if hasattr(self, '_workspace'):
            wanted = self.diamond_page if diamond else self.basic_page
            self.settings_tabs.add(wanted)
            self.settings_tabs.insert(0, wanted)
            self.settings_tabs.hide(self.basic_page if diamond else self.diamond_page)
            if diamond:
                self.settings_tabs.hide(self.lighting_page)
            else:
                self.settings_tabs.add(self.lighting_page)
            if irregular:
                self.segments_label.pack_forget()
                self.segments_control.pack_forget()
            else:
                self.segments_label.pack(after=self.edge_direction_control, anchor='w', pady=(0, 3))
                self.segments_control.pack(after=self.segments_label, fill='x', ipady=1, pady=(0, 7))
            self._update_profile_visibility()
        if select:
            self.settings_tabs.select(self.diamond_page if diamond else self.basic_page)

    def update_diamond_summary(self):
        defaults = self.extra_options
        phase = getattr(defaults, "diamond_ring_phase", 0)
        calibrated = phase != 0 or any(getattr(defaults, name, 0) > 0 for name in
                                     ("diamond_table_depth", "diamond_waist_depth"))
        self.diamond_summary.set(("已設定實際切面與前後深度" if calibrated else "可對齊實際切面與前後緣") +
            "\n反光分區：{} 個".format(len(defaults.diamond_cut_regions)))

    def edit_diamond_cuts(self):
        if not self.paths["front"]:
            messagebox.showinfo("畫鑽石切面", "請先放入正面圖片，或載入鑽石範例。", parent=self.root)
            return
        try:
            from spine_turn_diamond_cut_editor import open_diamond_cut_editor
            options = replace(self.get_options(), model="diamond")
            prepared = prepare_images(self.paths["front"], self.paths["back"], self.paths["edge"], options)

            def apply_cuts(regions):
                self.extra_options = replace(self.extra_options, diamond_cut_regions=regions)
                self.model_choice.set("鑽石")
                self.update_diamond_summary()
                self.rebuild()

            was_playing = self.playing
            self.playing = False
            self.play_button.configure(text="播放")
            try:
                dialog = open_diamond_cut_editor(self.root, prepared["front"], options, apply_cuts)
                self.root.wait_window(dialog)
            finally:
                self.playing = was_playing
                self.play_button.configure(text="暫停" if was_playing else "播放")
                self.last_tick = time.perf_counter()
        except Exception as exc:
            messagebox.showerror("無法調整鑽石切面", str(exc), parent=self.root)

    def edit_diamond(self):
        if not self.paths["front"]:
            messagebox.showinfo("調整鑽石輪廓", "請先放入正面圖片，或載入鑽石範例。", parent=self.root)
            return
        try:
            from spine_turn_diamond_alignment_editor import open_diamond_alignment_editor
            options = replace(self.get_options(), model="diamond")
            prepared = prepare_images(self.paths["front"], self.paths["back"], self.paths["edge"], options)
            options = resolve_options(prepared, options)

            applied = False

            def apply_guides(guides):
                nonlocal applied
                self.extra_options = replace(self.extra_options, **guides)
                self.diamond_guides = {key: guides.get(key, getattr(options, key)) for key in DIAMOND_GUIDE_FIELDS}
                self.diamond_view_tilt.set(guides.get("diamond_view_tilt", options.diamond_view_tilt))
                self.diamond_facets.set(guides.get("diamond_facets", options.diamond_facets))
                self.model_choice.set("鑽石")
                self.update_diamond_summary()
                self.progress = 0.
                self.angle = 0.
                self.animation.set("整圈旋轉")
                self.slider.set(0)
                self.rebuild()
                applied = True

            previous_view = (self.playing, self.progress, self.angle, self.animation.get())
            self.playing = False
            self.animation.set("整圈旋轉")
            self.progress = self.angle = 0.
            self.slider.set(0)
            self.play_button.configure(text="播放")
            self.draw()
            try:
                dialog = open_diamond_alignment_editor(self.root, prepared["front"], options, apply_guides)
                self.root.wait_window(dialog)
            finally:
                if not applied:
                    self.animation.set(previous_view[3])
                    self.playing, self.progress, self.angle = previous_view[:3]
                    self.slider.set(self.progress * 360)
                else:
                    self.playing = False
                self.play_button.configure(text="暫停" if self.playing else "播放")
                self.last_tick = time.perf_counter()
                self.draw()
        except Exception as exc:
            messagebox.showerror("無法調整鑽石輪廓", str(exc), parent=self.root)

    def edit_raised_region(self):
        if self.selected_shape() == "irregular":
            messagebox.showinfo("凸起範圍", "不規則透明輪廓保留凹口，暫時不與凸起範圍或斜面混用。", parent=self.root)
            return
        if not self.paths["front"]:
            messagebox.showinfo("畫凸起範圍", "請先放入正面透明 PNG 圖片。", parent=self.root)
            return
        try:
            from spine_turn_core import get_raised_region
            from spine_turn_region_editor import open_raised_region_editor
            options = replace(self.get_options(), shape="polygon", contour_points=(),
                              raised_contour_points=(), bevel_width=0)
            prepared = prepare_images(self.paths["front"], self.paths["back"], self.paths["edge"], options)
            options = resolve_options(prepared, options)
            try:
                automatic = get_raised_region(prepared, replace(options,
                    bevel_width=self.number(self.bevel_width, "斜面寬度（%）", 0, 20)/100))
            except ValueError:
                automatic = get_raised_region(prepared, options)
            initial = self.raised_contour_points or automatic

            def apply_region(points, height_percent):
                self.raised_contour_points = tuple(tuple(point) for point in points)
                self.shape.set(next(label for label, value in SHAPES.items() if value == "polygon"))
                self.bevel_depth.set(height_percent)
                self.region_summary.set(f"手動畫線 · {len(points)} 點 · 自動寬度暫停使用")
                self.rebuild()

            was_playing = self.playing
            self.playing = False
            self.play_button.configure(text="播放")
            try:
                dialog = open_raised_region_editor(self.root, prepared["front"], options.contour_points,
                                          initial, height_percent=self.number(self.bevel_depth, "凸起高度", 0, 45),
                                          on_apply=apply_region, auto_points=automatic,
                                          height_enabled=not self.ridge_mode.get(),
                                          height_note=("石塊模式：前後斜面直接相接，凸起高度固定為厚度的50%。"
                                                       if self.ridge_mode.get() else None))
                self.root.wait_window(dialog)
            finally:
                self.playing = was_playing
                self.play_button.configure(text="暫停" if was_playing else "播放")
                self.last_tick = time.perf_counter()
        except Exception as exc:
            messagebox.showerror("無法編輯凸起範圍", str(exc), parent=self.root)

    def schedule_rebuild(self):
        if self._loading_project:
            return
        if self._rebuild_job:
            self.root.after_cancel(self._rebuild_job)
        self._rebuild_job = self.root.after(180, self.rebuild)

    def rebuild(self):
        self._rebuild_job = None
        self._preview_revision = getattr(self, '_preview_revision', 0) + 1
        if not self.paths["front"]:
            self.prepared = None
            self.draw()
            return
        try:
            options = self.get_options()
            prepared = prepare_images(self.paths["front"], self.paths["back"], self.paths["edge"], options)
            options = resolve_options(prepared, options)
            self.options, self.prepared = options, prepared
            direction = self.prepared.get("edge_resolved_orientation", "horizontal")
            direction_label = "直向" if direction == "vertical" else "橫向"
            shape_note = (f"鑽石 {options.diamond_facets} 切面 · 俯視 {options.diamond_view_tilt:g}°"
                          if options.model == "diamond" else
                          ("不規則透明輪廓" if options.shape == "irregular" else
                           f"多邊形 {len(options.contour_points)} 角" if options.shape == "polygon" else f"Spine {options.spine_version}"))
            if options.shape == "polygon" and self.raised_contour_points:
                shape_note += f" · 凸起範圍 {len(self.raised_contour_points)} 點"
            material_note = ("獨立鑽石模式" if options.model == "diamond" else
                             ("石塊模式 · 無側壁" if options.side_mode == "ridge" else f"側邊 {direction_label}"))
            self.summary.set(f"{int(prepared['width'])} × {int(prepared['height'])} px  ·  {material_note}  ·  {shape_note}")
            self.update_timing_summary()
            self.status.set("掃光、Y／Z 彈跳、輸出縮放與明暗會寫入動畫；預覽縮放與地面參考線只用於檢視。")
            if options.shape == "irregular" and options.model != "diamond":
                self.status.set("依透明範圍保留凹口；圖片內已上色區域不會自動挖孔。彈跳與掃光會一併輸出。")
            elif options.shape == "polygon" and (prepared.get("contour_analysis") or {}).get("concavity_warning"):
                self.status.set("這張圖含有凹陷；多邊形側邊會以凸外輪廓近似。彈跳與明暗仍會寫入動畫。")
            self.draw()
        except Exception as exc:
            self.status.set(f"請檢查設定：{exc}")

    def set_background(self, value):
        self.background.set(value)
        self.draw()

    def toggle_play(self):
        if self.busy:
            return
        self.playing = not self.playing
        self.play_button.configure(text="暫停" if self.playing else "播放")
        self.last_tick = time.perf_counter()
        self.draw()

    def scrub(self, value):
        next_progress = float(value)/360
        # Tk schedules the scale callback after programmatic .set() calls too.
        # Ignore its rounding-only echo so each preview frame is drawn once.
        if abs(next_progress-self.progress) <= .051/360:
            return
        self.progress = next_progress
        self._preview_revision = getattr(self, '_preview_revision', 0) + 1
        self.angle = self.angle_at_progress()
        self.sync_transport()
        self.draw()

    def angle_at_progress(self):
        action = ANIMATIONS[self.animation.get()]
        if action == "flip_to_back":
            return self.progress * 180
        if action == "flip_to_front":
            return 180 + self.progress * 180
        return self.progress * 360

    def change_animation(self):
        if self._loading_project:
            return
        self.progress = 0.0
        self._preview_revision = getattr(self, '_preview_revision', 0) + 1
        self.angle = self.angle_at_progress()
        self.slider.set(0)
        self.last_tick = time.perf_counter()
        self.update_timing_summary()
        self.draw()

    def clip_duration(self):
        duration = self.number(self.duration, "動畫時間", .2, 30)
        return duration if ANIMATIONS[self.animation.get()] == "rotate_loop" else duration/2

    def update_timing_summary(self):
        try:
            duration = self.clip_duration()
            y = [self.bounce_start.get()*duration, self.bounce_apex.get()*duration,
                 self.bounce_land.get()*duration]
            z = [self.z_bounce_start.get()*duration, self.z_bounce_apex.get()*duration,
                 self.z_bounce_end.get()*duration]
            self.timing_summary.set(f"Y 起跳／高點／落地：{y[0]:.2f}／{y[1]:.2f}／{y[2]:.2f}s   ·   Z：{z[0]:.2f}／{z[1]:.2f}／{z[2]:.2f}s")
            if hasattr(self, "coin_shine_timing_summary"):
                start = self.coin_shine_start.get() * duration
                end = self.coin_shine_end.get() * duration
                self.coin_shine_timing_summary.set(f"掃光：{start:.2f} → {end:.2f} 秒 · {self.coin_shine_repeat.get()} 次")
        except (tk.TclError, ValueError):
            pass

    def set_coin_shine_times(self, start, end, repeats, duration):
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("請先設定有效的動畫時間。")
        if not all(math.isfinite(value) for value in (start, end, repeats)):
            raise ValueError("掃光時間與次數請輸入有效的數值。")
        if not 0 <= start < end <= duration:
            raise ValueError("掃光時間需為：0 ≤ 開始 < 結束 ≤ 動畫長度。")
        if int(repeats) != repeats or not 1 <= repeats <= 4:
            raise ValueError("掃光次數請使用 1 到 4 的整數。")
        self.coin_shine_start.set(start / duration)
        self.coin_shine_end.set(end / duration)
        self.coin_shine_repeat.set(int(repeats))

    def coin_shine_timing_dialog(self):
        if self.busy:
            return
        try:
            duration = self.clip_duration()
        except ValueError as exc:
            messagebox.showerror("請先設定動畫時間", str(exc), parent=self.root)
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("硬幣掃光時間")
        dialog.configure(bg=PANEL, padx=20, pady=18)
        dialog.transient(self.root)
        dialog.resizable(False, False)
        self.place_dialog(dialog, 500, 420)
        dialog.grab_set()
        self.label(dialog, f"{self.animation.get()} · 動畫長度 {duration:g} 秒").pack(anchor="w", pady=(0, 14))
        starts = tk.DoubleVar(dialog, value=round(self.coin_shine_start.get() * duration, 5))
        ends = tk.DoubleVar(dialog, value=round(self.coin_shine_end.get() * duration, 5))
        repeats = tk.DoubleVar(dialog, value=self.coin_shine_repeat.get())
        for title, variable, lower, upper, step in (
                ("開始掃光（秒）", starts, 0, duration, .05),
                ("結束掃光（秒）", ends, 0, duration, .05),
                ("掃過次數", repeats, 1, 4, 1)):
            self.field(dialog, title, ttk.Spinbox(dialog, from_=lower, to=upper, increment=step, textvariable=variable))
        self.hint(dialog, "光帶在指定時間內掃過，可與旋轉和 Y／Z 彈跳分開安排。切換半圈或修改動畫長度時，時間會依比例調整。")
        def apply():
            try:
                self.set_coin_shine_times(self.number(starts, "開始掃光", 0, duration),
                    self.number(ends, "結束掃光", 0, duration), self.number(repeats, "掃光次數", 1, 4), duration)
                self.change_animation()
                self.rebuild()
                dialog.destroy()
            except (tk.TclError, ValueError) as exc:
                messagebox.showerror("請檢查掃光時間", str(exc), parent=dialog)
        buttons = tk.Frame(dialog, bg=PANEL)
        buttons.pack(fill="x", pady=(16, 0))
        self.button(buttons, "套用時間", apply, primary=True).pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.button(buttons, "取消", dialog.destroy).pack(side="left", fill="x", expand=True)

    def timing_dialog(self):
        if self.busy:
            return
        try:
            duration = self.clip_duration()
        except ValueError as exc:
            messagebox.showerror("請先設定動畫時間", str(exc))
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("自訂 Y／Z 彈跳時間")
        dialog.configure(bg=PANEL, padx=20, pady=18)
        dialog.resizable(False, False)
        dialog.transient(self.root)
        self.place_dialog(dialog, 650, 590)
        dialog.grab_set()
        self.label(dialog, f"{self.animation.get()} · 動畫長度 {duration:g} 秒").pack(anchor="w", pady=(0, 12))
        columns = tk.Frame(dialog, bg=PANEL)
        columns.pack(fill="both", expand=True)
        y_panel = tk.Frame(columns, bg=PANEL, padx=4)
        z_panel = tk.Frame(columns, bg=PANEL, padx=4)
        y_panel.pack(side="left", fill="both", expand=True, padx=(0, 14))
        z_panel.pack(side="left", fill="both", expand=True)
        self.label(y_panel, "Y 上下彈跳").pack(anchor="w", pady=(0, 12))
        self.label(z_panel, "Z 靠近／遠離").pack(anchor="w", pady=(0, 12))
        fields = [
            (y_panel, "起跳時間（秒）", self.bounce_start),
            (y_panel, "到達高點（秒）", self.bounce_apex),
            (y_panel, "落地時間（秒）", self.bounce_land),
            (y_panel, "落地後恢復完成（秒）", self.bounce_end),
            (z_panel, "開始靠近／遠離（秒）", self.z_bounce_start),
            (z_panel, "到達深度高點（秒）", self.z_bounce_apex),
            (z_panel, "返回原位（秒）", self.z_bounce_end),
        ]
        local_values = []
        for parent, label, target in fields:
            value = tk.DoubleVar(value=round(target.get()*duration, 4))
            local_values.append(value)
            self.field(parent, label, ttk.Spinbox(parent, from_=0, to=duration, increment=.05,
                                                 textvariable=value))
        tk.Label(dialog, text="起跳前會有短暫預備壓縮；落地後仍能繼續旋轉。\n落地與恢復時間相同時，會省略落地壓縮。\nY、Z 開關與幅度仍分別由各分頁控制。\n調整動畫總長或切換半圈時，時間會依比例套用。",
                 bg=PANEL, fg=MUTED, justify="left", wraplength=605,
                 font=("Microsoft JhengHei UI", 9)).pack(anchor="w", pady=14)

        def apply():
            try:
                values = [self.number(value, label, 0, duration) for value, (_, label, _) in zip(local_values, fields)]
                y_start, y_apex, y_land, y_end, z_start, z_apex, z_end = values
                if not y_start < y_apex < y_land <= y_end:
                    raise ValueError("Y 時間需依序為：起跳 < 高點 < 落地 ≤ 恢復完成。")
                if not z_start < z_apex < z_end:
                    raise ValueError("Z 時間需依序為：開始 < 高點 < 返回原位。")
                for (_, _, target), value in zip(fields, values):
                    target.set(value/duration)
                self.change_animation()
                self.rebuild()
                dialog.destroy()
            except Exception as exc:
                messagebox.showerror("請檢查彈跳時間", str(exc), parent=dialog)
        buttons = tk.Frame(dialog, bg=PANEL)
        buttons.pack(fill="x")
        self.button(buttons, "套用時間", apply, primary=True).pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.button(buttons, "返回", dialog.destroy).pack(side="left", fill="x", expand=True)

    def tick(self):
        if getattr(self, '_closed', False):
            return
        now = time.perf_counter()
        elapsed = max(0., now - self.last_tick)
        self.last_tick = now
        if self.playing and self.prepared and not self.busy:
            clip_duration = self.options.duration if ANIMATIONS[self.animation.get()] == "rotate_loop" else self.options.duration/2
            self.progress = (self.progress + elapsed / clip_duration) % 1
            self.angle = self.angle_at_progress()
            self.slider.set(self.progress * 360)
            self.draw()
        self.sync_transport()
        self.root.after(max(1, round(33-(time.perf_counter()-now)*1000)), self.tick)

    def draw(self):
        if self._loading_project:
            return
        if not hasattr(self, "preview"):
            return
        width, height = max(20, self.preview.winfo_width()), max(20, self.preview.winfo_height())
        if not self.prepared:
            self._preview_view_key = None
            self.preview.delete("all")
            self.preview_image_id = None
            center_x, center_y = width / 2, height / 2
            if height >= 180:
                self.preview.create_rectangle(center_x - 26, center_y - 66, center_x + 26, center_y - 20,
                    outline=LINE, width=2, fill=CARD)
                self.preview.create_line(center_x - 10, center_y - 43, center_x + 10, center_y - 43,
                    fill=ACCENT, width=2)
                self.preview.create_line(center_x, center_y - 53, center_x, center_y - 33,
                    fill=ACCENT, width=2)
            self.preview.create_text(center_x, center_y + 3, text="從一張圖片，開始製作動態", fill=TEXT,
                                     font=("Microsoft JhengHei UI", 14, "bold"))
            self.preview.create_text(center_x, center_y + 34, text="將透明 PNG 拖到正面素材卡，或點選「替換」",
                                     fill=MUTED, font=("Microsoft JhengHei UI", 9), width=max(220, width - 40))
            return
        try:
            zoom = self.preview_zoom.get()/100
            if not .25 <= zoom <= 2.5:
                return
            background, action = self.background.get(), ANIMATIONS[self.animation.get()]
            ground = self.show_ground.get()
            key = (getattr(self, '_preview_revision', 0), id(self.prepared), id(self.options),
                   width, height, background, action, zoom, ground)
            self._preview_view_key = key
            if not getattr(self, '_preview_worker', None):
                self._preview_worker = LatestPreviewWorker(render_pose)
            self._preview_request_id = self._preview_worker.submit(key, self.angle,
                (self.prepared, self.options, self.angle, (width, height), background),
                dict(progress=self.progress, animation_name=action, zoom=zoom, show_ground=ground))
        except Exception as exc:
            self.status.set(f"預覽發生問題：{exc}")

    def _poll_preview(self):
        if getattr(self, '_closed', False):
            return
        worker = getattr(self, '_preview_worker', None)
        result = worker.take_result() if worker else None
        if (result is not None and not self._loading_project and
                result.view_key == self._preview_view_key and
                result.serial > getattr(self, '_preview_presented_id', 0) and
                (self.playing or result.serial == self._preview_request_id)):
            if result.error:
                self.status.set(f"預覽發生問題：{result.error}")
            else:
                self.frame_photo = ImageTk.PhotoImage(result.image)
                if not getattr(self, 'preview_image_id', None):
                    self.preview_image_id = self.preview.create_image(0, 0, anchor='nw', image=self.frame_photo)
                else:
                    self.preview.itemconfigure(self.preview_image_id, image=self.frame_photo)
                self.angle_text.configure(text=f"{result.angle:05.1f}°")
                self._preview_presented_id = result.serial
        self.sync_transport()
        self._preview_poll_job = self.root.after(10, self._poll_preview)

    def choose_spine(self):
        path = filedialog.askopenfilename(title="選擇 Spine.com 或 Spine.exe", filetypes=[("Spine", "*.com *.exe")])
        if path:
            self.native = path
            self.native_export.set(True)
            self.native_status.configure(text="已選擇本機 Spine")
            self.status.set(f"已選擇 Spine，匯出時會依目標 {self.spine_version.get()} 版本建立專案。")

    def export(self):
        if self.busy:
            return
        try:
            options = self.get_options()
            if not self.paths["front"]:
                raise ValueError("請先放入正面圖片。")
        except Exception as exc:
            messagebox.showerror("請檢查素材或設定", str(exc))
            return
        destination = filedialog.askdirectory(title="選擇輸出位置（會建立獨立專案資料夾）", initialdir=str(self.output_base if self.output_base.exists() else Path.home()))
        if not destination:
            return
        folder = Path(destination) / options.name
        serial = 2
        while folder.exists():
            folder = Path(destination) / f"{options.name}_{serial}"
            serial += 1
        self.busy = True
        self.export_button.configure(state="disabled", text="正在建立專案…")
        self.sequence_button.configure(state="disabled")
        self.status.set("正在建立網格、翻轉動畫與圖片；原生專案建立可能需要一點時間。")
        paths = dict(self.paths)
        make_native = self.native_export.get()
        native = self.native

        def worker():
            try:
                result = build_package(paths["front"], paths["back"], paths["edge"], folder, options)
                native_result = None
                if make_native:
                    native_result = convert_project(result["json_path"], folder / f"{options.name}.spine", executable=native, version=options.spine_version)
                    manifest_path = Path(result["manifest_path"])
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    manifest["native_project_created"] = bool(native_result.get("ok"))
                    manifest["native_conversion"] = {key: native_result.get(key) for key in ("ok", "status", "reason", "version", "message") if key in native_result}
                    if native_result.get("ok"):
                        manifest["files"]["project"] = f"{options.name}.spine"
                    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                self.root.after(0, lambda: self.export_done(folder, result, native_result, options.spine_version))
            except Exception as exc:
                error = str(exc)
                self.root.after(0, lambda: self.export_failed(error))
        threading.Thread(target=worker, daemon=True).start()

    def export_done(self, folder, result, native_result, target_version=None):
        self.busy = False
        self.export_button.configure(state="normal", text="匯出 Spine 專案…")
        self.sequence_button.configure(state="normal")
        native_exists = list(folder.glob("*.spine"))
        version = target_version or self.selected_target_version()
        if native_exists:
            title = f"Spine {version} 專案已建立"
            text = f"已匯出至：\n{folder}\n\n請用 Spine {version} 開啟 {native_exists[0].name}，在 Animate 模式選擇 rotate_loop。\n其他動畫：flip_to_back、flip_to_front。"
        else:
            title = "Spine 匯入資料已建立"
            text = f"已匯出至：\n{folder}\n\n在 Spine {version} 使用「Import Data／匯入資料」選擇 JSON，之後另存為 .spine。"
            if make_message := (native_result or {}).get("message"):
                text += f"\n\n原生轉檔：{make_message}"
        text += "\n\n請與編輯器版本一致；跨版本匯入 JSON 可能遺失翻轉動畫。版本不同時，請在工具選擇對應版本後重新匯出。"
        (folder / '開啟前請看.txt').write_text(text + '\n', encoding='utf-8')
        self.status.set(f"{title}：{folder}")
        self.last_export = folder
        messagebox.showinfo(title, text)
        if os.name == "nt":
            os.startfile(folder)

    def export_failed(self, error):
        self.busy = False
        self.export_button.configure(state="normal", text="匯出 Spine 專案…")
        self.sequence_button.configure(state="normal")
        self.status.set(f"匯出失敗：{error}")
        messagebox.showerror("匯出失敗", error)

    @staticmethod
    def unique_output(destination, name):
        folder = Path(destination) / name
        serial = 2
        while folder.exists():
            folder = Path(destination) / f"{name}_{serial}"
            serial += 1
        return folder

    def place_dialog(self, dialog, width, height):
        self.root.update_idletasks()
        x = max(0, self.root.winfo_rootx() + (self.root.winfo_width()-width)//2)
        y = max(0, self.root.winfo_rooty() + (self.root.winfo_height()-height)//2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")

    def sequence_dialog(self):
        if self.busy:
            return
        if not self.paths["front"]:
            messagebox.showerror("請先放入圖片", "請先放入正面圖片，再匯出序列圖。")
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("匯出透明 PNG 序列")
        dialog.configure(bg=PANEL, padx=22, pady=18)
        dialog.resizable(False, False)
        dialog.transient(self.root)
        self.place_dialog(dialog, 440, 650)
        dialog.grab_set()
        action_var = tk.StringVar(value=self.animation.get())
        fps_var = tk.IntVar(value=30)
        width_var, height_var = tk.IntVar(value=512), tk.IntVar(value=512)
        count_var = tk.StringVar()
        self.label(dialog, "輸出目前的素材與動畫設定").pack(anchor="w", pady=(0, 14))
        self.field(dialog, "動畫", ttk.Combobox(dialog, textvariable=action_var,
                   values=list(ANIMATIONS), state="readonly"))
        self.field(dialog, "影格率（FPS）", ttk.Spinbox(dialog, from_=1, to=120, increment=1,
                                                   textvariable=fps_var))
        self.field(dialog, "畫布寬度（像素）", ttk.Spinbox(dialog, from_=64, to=4096, increment=64,
                                                      textvariable=width_var))
        self.field(dialog, "畫布高度（像素）", ttk.Spinbox(dialog, from_=64, to=4096, increment=64,
                                                      textvariable=height_var))
        tk.Label(dialog, textvariable=count_var, bg=PANEL, fg=TEXT, justify="left",
                 wraplength=390, font=("Microsoft JhengHei UI", 10)).pack(anchor="w", pady=12)
        tk.Label(dialog, text="透明背景、固定畫布，會自動保留完整動作範圍。\n輸出包含 Y／Z 彈跳、縮放與明暗。\n預覽地面參考線不會輸出。",
                 bg=PANEL, fg=MUTED, justify="left", wraplength=390,
                 font=("Microsoft JhengHei UI", 9)).pack(anchor="w", pady=(0, 15))

        def update_count(*_):
            try:
                duration = self.duration.get() if ANIMATIONS[action_var.get()] == "rotate_loop" else self.duration.get()/2
                fps = int(fps_var.get())
                count = max(1, round(duration*fps))
                if ANIMATIONS[action_var.get()] != "rotate_loop":
                    count += 1
                count_var.set(f"約 {duration:g} 秒 · {count} 張 PNG\n整圈循環不重複最後一張；半圈會保留結束姿勢。")
            except (tk.TclError, ValueError):
                count_var.set("請輸入有效的影格率。")
        action_var.trace_add("write", update_count)
        fps_var.trace_add("write", update_count)
        update_count()

        def begin():
            try:
                options = self.get_options()
                fps = int(self.number(fps_var, "影格率", 1, 120))
                size = (int(self.number(width_var, "畫布寬度", 64, 4096)),
                        int(self.number(height_var, "畫布高度", 64, 4096)))
                prepared = prepare_images(self.paths["front"], self.paths["back"], self.paths["edge"], options)
                options = resolve_options(prepared, options)
            except Exception as exc:
                messagebox.showerror("請檢查輸出設定", str(exc), parent=dialog)
                return
            destination = filedialog.askdirectory(parent=dialog, title="選擇 PNG 序列輸出位置")
            if not destination:
                return
            action = ANIMATIONS[action_var.get()]
            folder = self.unique_output(destination, f"{options.name}_{action}_png")
            dialog.destroy()
            self.start_sequence(prepared, options, folder, action, fps, size)
        self.button(dialog, "選擇位置並匯出", begin, primary=True).pack(fill="x", pady=(4, 6))
        self.button(dialog, "返回", dialog.destroy).pack(fill="x")

    def start_sequence(self, prepared, options, folder, action, fps, size):
        self.busy = True
        self.export_button.configure(state="disabled")
        self.sequence_button.configure(state="disabled", text="正在輸出 PNG…")
        self.status.set("正在準備透明 PNG 序列，完成後會顯示輸出位置。")
        self.sequence_cancel = threading.Event()
        progress_window = tk.Toplevel(self.root)
        progress_window.title("正在匯出透明 PNG 序列")
        progress_window.configure(bg=PANEL, padx=22, pady=20)
        progress_window.resizable(False, False)
        progress_window.transient(self.root)
        self.place_dialog(progress_window, 420, 210)
        progress_label = tk.StringVar(value="正在計算完整動作範圍…")
        self.label(progress_window, textvariable=progress_label).pack(anchor="w", pady=(0, 16))
        progress_bar = ttk.Progressbar(progress_window, mode="determinate", maximum=100)
        progress_bar.pack(fill="x", pady=(0, 18))

        def cancel():
            self.sequence_cancel.set()
            progress_label.set("正在停止，已輸出的影格會保留並標示為未完成。")
        self.button(progress_window, "取消輸出", cancel).pack(fill="x")
        progress_window.protocol("WM_DELETE_WINDOW", cancel)

        def update(completed, total):
            if progress_window.winfo_exists() and not self.sequence_cancel.is_set():
                progress_label.set(f"正在輸出 {completed} / {total} 張 PNG")
                progress_bar.configure(value=100 * completed / max(1, total))
                self.status.set(f"透明 PNG 序列：{completed} / {total} 張")

        def finish(result=None, error=None):
            progress_window.destroy()
            self.busy = False
            self.export_button.configure(state="normal", text="匯出 Spine 專案…")
            self.sequence_button.configure(state="normal", text="透明 PNG 序列…")
            if error:
                self.status.set(f"序列圖輸出失敗：{error}")
                messagebox.showerror("序列圖輸出失敗", error)
            elif result["status"] == "cancelled":
                self.status.set(f"已取消；已輸出 {result['frame_count']} 張，資料夾已標示為未完成：{folder}")
            else:
                self.status.set(f"透明 PNG 序列已完成：{folder}")
                messagebox.showinfo("透明 PNG 序列已完成", f"已輸出 {result['frame_count']} 張透明 PNG。\n尺寸：{size[0]} × {size[1]}\n\n{folder}")
                if os.name == "nt":
                    os.startfile(folder)

        def worker():
            try:
                result = export_sequence(prepared, options, folder, animation_name=action, fps=fps,
                                         size=size, cancel_event=self.sequence_cancel,
                                         progress_callback=lambda done, total: self.root.after(0, update, done, total))
                self.root.after(0, finish, result)
            except Exception as exc:
                self.root.after(0, finish, None, str(exc))
        threading.Thread(target=worker, daemon=True).start()


def main():
    if os.name == "nt":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = Root()
    app = App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
