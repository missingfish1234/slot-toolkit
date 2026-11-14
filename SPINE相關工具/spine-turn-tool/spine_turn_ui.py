"""Workspace layout for Spine Turn Studio; application state stays in ``App``.

The workspace creates widgets and routes gestures to existing application
callbacks. It does not load images, change options, schedule playback, or bind
application shortcuts.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class StudioWorkspace:
    """Build the stage, inspector, material cards and persistent export bar."""

    def __init__(self, app, version, palette, models, spine_targets, animations,
                 dnd_files=None):
        self.app = app
        self.root = app.root
        self.palette = palette
        self.bg = palette["BG"]
        self.panel = palette["PANEL"]
        self.card = palette["CARD"]
        self.text = palette["TEXT"]
        self.muted = palette["MUTED"]
        self.accent = palette["ACCENT"]
        self.line = palette.get("LINE", self.card)
        self.font = ("Microsoft JhengHei UI", 9)
        self.assets_visible = True
        self.focused = False
        self._assets_before_focus = True
        self._inspector_width = 320
        self._toolbar_wide = None
        self._dnd_files = dnd_files
        self.asset_buttons = {}

        self._build_header(version)
        # Pack the persistent bottom bars before the expanding workspace. This
        # keeps the export actions reachable when the window becomes shorter.
        self._build_export_bar(spine_targets)
        self.panes = tk.PanedWindow(self.root, orient="horizontal", bg=self.bg,
                                   bd=0, sashwidth=6, sashrelief="flat",
                                   opaqueresize=True, showhandle=False)
        self.panes.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        self.stage = tk.Frame(self.panes, bg=self.bg)
        self.inspector = tk.Frame(self.panes, bg=self.panel, padx=12, pady=10)
        self.panes.add(self.stage, minsize=350, stretch="always")
        self.panes.add(self.inspector, minsize=270, width=320, stretch="never")
        self._build_inspector(models)
        self._build_stage(animations)

    def _label(self, parent, text=None, *, muted=False, **kwargs):
        kwargs.setdefault("font", self.font)
        return tk.Label(parent, text=text, bg=parent.cget("bg"),
                        fg=self.muted if muted else self.text,
                        **kwargs)

    def _button(self, parent, text, command, *, primary=False, small=False,
                **kwargs):
        kwargs.setdefault("padx", 7 if small else 11)
        kwargs.setdefault("pady", 3 if small else 6)
        return tk.Button(parent, text=text, command=command,
                         bg=self.accent if primary else self.card,
                         fg=self.bg if primary else self.text,
                         activebackground=self.accent,
                         activeforeground=self.bg, bd=0, relief="flat",
                         cursor="hand2", font=self.font, takefocus=True, **kwargs)

    def _build_header(self, version):
        app = self.app
        self.header = tk.Frame(self.root, bg=self.bg, padx=14, pady=10)
        self.header.pack(fill="x")
        self.header.columnconfigure(2, weight=1)
        brand = tk.Frame(self.header, bg=self.bg)
        brand.grid(row=0, column=0, sticky="w", padx=(0, 20))
        self._label(brand, "Spine Turn", font=("Segoe UI", 13, "bold")).pack(side="left")
        self._label(brand, str(version), muted=True).pack(side="left", padx=(7, 0))
        self._label(self.header, "專案").grid(row=0, column=1, padx=(0, 7))
        self.project_entry = tk.Entry(self.header, textvariable=app.name,
                                      bg=self.card, fg=self.text,
                                      insertbackground=self.text, bd=0,
                                      font=("Microsoft JhengHei UI", 10),
                                      width=18, relief="flat")
        self.project_entry.grid(row=0, column=2, sticky="ew", ipady=6,
                                padx=(0, 14))
        self._button(self.header, "開啟", app.open_project).grid(row=0, column=3, padx=(0, 6))
        self._button(self.header, "儲存", app.save_project).grid(row=0, column=4, padx=(0, 6))
        self.examples_button = tk.Menubutton(self.header, text="範例 ▾",
            bg=self.card, fg=self.text, activebackground=self.accent,
            activeforeground=self.bg, bd=0, font=self.font, padx=11, pady=6,
            cursor="hand2", relief="flat", takefocus=True)
        examples = tk.Menu(self.examples_button, tearoff=False, bg=self.panel,
                           fg=self.text, activebackground=self.accent,
                           activeforeground=self.bg, font=self.font, bd=0)
        for title, mode in (("硬幣掃光", "shine"), ("Y 軸彈跳", "y"),
                            ("Z 軸靠近／遠離", "z"), ("不規則輪廓", "irregular"),
                            ("鑽石", "diamond")):
            examples.add_command(label=title, command=lambda value=mode: app.load_demo(value))
        self.examples_button.configure(menu=examples)
        self.examples_button.grid(row=0, column=5)

    def _build_export_bar(self, spine_targets):
        app = self.app
        self.status_bar = tk.Frame(self.root, bg=self.bg, padx=14, pady=4)
        self.status_bar.pack(side="bottom", fill="x")
        app.status_label = self._label(self.status_bar, textvariable=app.status,
                                       muted=True, anchor="w", height=1)
        app.status_label.pack(fill="x")
        boundary = tk.Frame(self.root, bg=self.line, height=1)
        boundary.pack(side="bottom", fill="x")
        self.export_bar = tk.Frame(self.root, bg=self.panel, padx=14, pady=8)
        self.export_bar.pack(side="bottom", fill="x")
        self.export_bar.columnconfigure(5, weight=1)
        self._label(self.export_bar, "Spine").grid(row=0, column=0, padx=(0, 6))
        self.version_control = ttk.Combobox(self.export_bar,
            textvariable=app.spine_version, values=list(spine_targets),
            state="readonly", width=5)
        self.version_control.grid(row=0, column=1, sticky="w", padx=(0, 12))
        tk.Checkbutton(self.export_bar, text="建立原生 .spine", variable=app.native_export,
                       bg=self.panel, fg=self.text, selectcolor=self.card,
                       activebackground=self.panel, activeforeground=self.text,
                       font=self.font, anchor="w").grid(row=0, column=2, sticky="w")
        self._button(self.export_bar, "選擇 Spine…", app.choose_spine,
                     small=True).grid(row=0, column=3, padx=(10, 6))
        app.native_status = self._label(self.export_bar,
            "已找到本機 Spine" if app.native else "尚未指定 Spine", muted=True,
            anchor="w")
        app.native_status.grid(row=0, column=4, sticky="w", padx=(4, 8))
        app.sequence_button = self._button(self.export_bar, "透明 PNG 序列…",
                                          app.sequence_dialog)
        app.sequence_button.grid(row=0, column=6, sticky="e", padx=(8, 6))
        app.export_button = self._button(self.export_bar, "匯出 Spine 專案…",
                                        app.export, primary=True)
        app.export_button.grid(row=0, column=7, sticky="e")
        self._label(self.export_bar, textvariable=app.spine_revision,
                    muted=True, anchor="w").grid(row=1, column=0, columnspan=6,
                                                 sticky="w", pady=(5, 0))
        self._label(self.export_bar, "素材與設定可用上方「儲存」繼續編輯。",
                    muted=True, anchor="e").grid(row=1, column=6, columnspan=2,
                                                 sticky="e", pady=(5, 0))

    def _build_inspector(self, models):
        app = self.app
        mode_row = tk.Frame(self.inspector, bg=self.panel)
        mode_row.pack(fill="x", pady=(0, 10))
        self._label(mode_row, "製作模式").pack(side="left", padx=(0, 12))
        ttk.Combobox(mode_row, textvariable=app.model_choice, values=list(models),
                     state="readonly", width=13).pack(side="left", fill="x", expand=True)
        self.common = tk.Frame(self.inspector, bg=self.panel)
        self.common.pack(fill="x", pady=(0, 8))
        app.settings_tabs = ttk.Notebook(self.inspector, style="Turn.TNotebook")
        app.settings_tabs.pack(fill="both", expand=True)
        self.settings_tabs = app.settings_tabs

    def _build_stage(self, animations):
        app = self.app
        self.asset_bar = tk.Frame(self.stage, bg=self.bg)
        self.asset_bar.pack(fill="x", pady=(0, 8))
        self._build_assets()
        self.toolbar = tk.Frame(self.stage, bg=self.bg)
        self.toolbar.pack(fill="x", pady=(0, 8))
        self.action_group = tk.Frame(self.toolbar, bg=self.bg)
        ttk.Combobox(self.action_group, textvariable=app.animation,
                     values=list(animations), state="readonly", width=13).pack(side="left")
        self.view_group = tk.Frame(self.toolbar, bg=self.bg)
        for value, title in (("checker", "透明"), ("dark", "深底"), ("light", "淺底")):
            self._button(self.view_group, title, lambda key=value: app.set_background(key),
                         small=True).pack(side="left", padx=(0, 3))
        self._label(self.view_group, "縮放", muted=True).pack(side="left", padx=(6, 4))
        ttk.Spinbox(self.view_group, from_=25, to=250, increment=10, width=4,
                    textvariable=app.preview_zoom).pack(side="left")
        self._label(self.view_group, "%", muted=True).pack(side="left", padx=(3, 0))
        self._button(self.view_group, "適合", lambda: app.preview_zoom.set(100),
                     small=True).pack(side="left", padx=(5, 0))
        self.workspace_group = tk.Frame(self.toolbar, bg=self.bg)
        self.assets_button = self._button(self.workspace_group, "收合素材", self.toggle_assets,
                                          small=True)
        self.assets_button.pack(side="left", padx=(0, 5))
        self.focus_button = self._button(self.workspace_group, "專注預覽 F8", self.toggle_focus,
                                         small=True)
        self.focus_button.pack(side="left")
        self.toolbar.bind("<Configure>", self._layout_toolbar)
        self._layout_toolbar()
        # Bottom controls are packed first so a short stage always keeps the
        # transport visible and gives the remaining height to the canvas.
        self._build_transport()
        app.preview = tk.Canvas(self.stage, bg=self.panel, bd=0,
                                highlightthickness=1, highlightbackground=self.line)
        app.preview.pack(fill="both", expand=True)
        app.preview.bind("<Configure>", lambda _event: app.draw())

    def _build_assets(self):
        app = self.app
        app.cards = {}
        app.asset_preview_size = (70, 58)
        cards_row = tk.Frame(self.asset_bar, bg=self.bg)
        cards_row.pack(fill="x")
        for column, (kind, title, requirement, placeholder) in enumerate((
                ("front", "正面", "必填", "點選縮圖或拖入透明 PNG"),
                ("back", "背面", "選填", "空白時自動沿用正面"),
                ("edge", "側邊", "選填", "空白時自動產生材質"))):
            cards_row.columnconfigure(column, weight=1, uniform="materials")
            card = tk.Frame(cards_row, bg=self.panel, padx=5, pady=4,
                            highlightthickness=1, highlightbackground=self.line)
            card.grid(row=0, column=column, sticky="nsew",
                      padx=(0 if column == 0 else 3, 0 if column == 2 else 3))
            card.columnconfigure(1, weight=1)
            image_box = tk.Frame(card, bg=self.card, width=70, height=58)
            image_box.grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, 7))
            image_box.pack_propagate(False)
            preview = tk.Label(image_box, text="＋", bg=self.card, fg=self.muted,
                               font=("Segoe UI", 18), cursor="hand2", bd=0)
            preview.pack(fill="both", expand=True)
            header = tk.Frame(card, bg=self.panel)
            header.grid(row=0, column=1, sticky="ew")
            header.columnconfigure(0, weight=1)
            title_label = self._label(header, f"{title} {requirement}", anchor="w",
                                      justify="left", width=1)
            title_label.grid(row=0, column=0, sticky="ew", padx=(0, 3))
            filename = self._label(card, placeholder, muted=True, anchor="w",
                                   justify="left", wraplength=110, height=2)
            filename.grid(row=1, column=1, sticky="ew", pady=(1, 0))
            actions = tk.Frame(header, bg=self.panel)
            actions.grid(row=0, column=1, sticky="e")
            replace_button = self._button(actions, "替換", lambda role=kind: app.choose_image(role),
                                           small=True, padx=2, pady=1)
            replace_button.pack(side="left", padx=(0, 2))
            clear_button = self._button(actions, "清除", lambda role=kind: app.remove_asset(role),
                                         small=True, padx=2, pady=1)
            clear_button.pack(side="left")
            if kind == "back":
                self.swap_button = self._button(actions, "互換", app.swap_faces,
                                                small=True, padx=2, pady=1)
                self.swap_button.pack(side="left", padx=(2, 0))
            self.asset_buttons[kind] = (replace_button, clear_button)
            for widget in (preview, title_label, filename):
                widget.bind("<Button-1>", lambda _event, role=kind: app.choose_image(role))
            if self._dnd_files:
                for widget in (card, image_box, preview, header, title_label, filename):
                    widget.drop_target_register(self._dnd_files)
                    widget.dnd_bind("<<Drop>>", lambda event, role=kind: app.drop_image(event, role))
            card.bind("<Configure>", lambda event, image=image_box, head=header,
                      label=filename, title_widget=title_label,
                      title_text=(title, requirement):
                      self._layout_asset_card(event.width, image, head, label,
                                              title_widget, title_text))
            app.cards[kind] = (preview, filename)

    def _build_transport(self):
        app = self.app
        self.transport = tk.Frame(self.stage, bg=self.bg, pady=6)
        self.transport.pack(side="bottom", fill="x")
        self.transport.columnconfigure(5, weight=1)
        app.play_button = self._button(self.transport, "暫停" if app.playing else "播放",
                                       app.toggle_play, small=True, width=4)
        app.play_button.grid(row=0, column=0, padx=(0, 6))
        for column, title, callback in (
                (1, "起點", lambda: app.seek_progress(0.0)),
                (2, "−1 格", lambda: app.step_preview(-1)),
                (3, "+1 格", lambda: app.step_preview(1)),
                (4, "終點", lambda: app.seek_progress(1.0))):
            self._button(self.transport, title, callback, small=True,
                         padx=6).grid(row=0, column=column, padx=(0, 4))
        app.slider = ttk.Scale(self.transport, from_=0, to=360, orient="horizontal",
            style="Studio.Horizontal.TScale", command=app.scrub)
        app.slider.grid(row=0, column=5, sticky="ew", padx=(3, 0))
        details = tk.Frame(self.transport, bg=self.bg)
        details.grid(row=1, column=0, columnspan=6, sticky="ew", pady=(5, 0))
        details.columnconfigure(0, weight=1)
        self._label(details, textvariable=app.time_readout, muted=True,
                    anchor="w", width=1).grid(row=0, column=0, sticky="ew")
        self._label(details, "角度", muted=True).grid(row=0, column=1, padx=(6, 4))
        app.angle_entry = tk.Entry(details, textvariable=app.angle_input, width=6,
            bg=self.card, fg=self.text, insertbackground=self.text, bd=0,
            justify="right", font=self.font)
        app.angle_entry.grid(row=0, column=2, ipady=4)
        app.angle_entry.bind("<FocusIn>", app.begin_angle_edit)
        app.angle_entry.bind("<Return>", lambda _event: self._apply_angle())
        self._label(details, "°", muted=True).grid(row=0, column=3, padx=(3, 5))
        self._button(details, "套用", app.apply_angle, small=True).grid(row=0, column=4)
        app.angle_text = self._label(details, "000.0°", muted=True, width=8, anchor="e")
        self.info_bar = tk.Frame(self.stage, bg=self.bg, pady=4)
        self.info_bar.pack(side="bottom", fill="x")
        summary_row = tk.Frame(self.info_bar, bg=self.bg)
        summary_row.pack(fill="x")
        tk.Checkbutton(summary_row, text="地面線", variable=app.show_ground,
                       bg=self.bg, fg=self.muted, selectcolor=self.card,
                       activebackground=self.bg, activeforeground=self.text,
                       font=self.font, bd=0).pack(side="right", padx=(8, 0))
        self._label(summary_row, textvariable=app.summary, muted=True,
                    anchor="w", width=1).pack(side="left", fill="x", expand=True)
        app.timing_label = self._label(self.info_bar, textvariable=app.timing_summary,
                                       muted=True, anchor="w", justify="left",
                                       wraplength=560)
        app.timing_label.pack(fill="x", pady=(2, 0))
        self.info_bar.bind("<Configure>", lambda event:
                           app.timing_label.configure(wraplength=max(300, event.width)))

    def _apply_angle(self):
        self.app.apply_angle()
        return "break"

    @staticmethod
    def _layout_asset_card(width, image, header, filename, title, title_text):
        compact = width < 230
        if compact:
            image.grid_remove()
        else:
            image.grid()
        for widget in (header, filename):
            widget.grid_configure(column=0 if compact else 1,
                                  columnspan=2 if compact else 1)
        title.configure(text=("\n" if width < 150 else " ").join(title_text))
        filename.configure(wraplength=max(60, width - (12 if compact else 89)))

    def _layout_toolbar(self, event=None):
        width = event.width if event is not None else 650
        required = sum(group.winfo_reqwidth() for group in
                       (self.action_group, self.view_group, self.workspace_group)) + 24
        wide = width >= max(570, required)
        if wide == self._toolbar_wide:
            return
        self._toolbar_wide = wide
        for group in (self.action_group, self.view_group, self.workspace_group):
            group.grid_forget()
        self.toolbar.columnconfigure(0, weight=0)
        self.toolbar.columnconfigure(1, weight=1)
        self.toolbar.columnconfigure(2, weight=0)
        self.action_group.grid(row=0, column=0, sticky="w", padx=(0, 8))
        if wide:
            self.view_group.grid(row=0, column=1, sticky="w")
            self.workspace_group.grid(row=0, column=2, sticky="e", padx=(8, 0))
        else:
            self.workspace_group.grid(row=0, column=1, columnspan=2, sticky="e")
            self.view_group.grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))

    def toggle_assets(self):
        """Collapse only the source cards, leaving their images and paths intact."""
        if self.focused:
            return
        self._set_assets_visible(not self.assets_visible)

    def _set_assets_visible(self, visible):
        self.assets_visible = bool(visible)
        if self.assets_visible:
            self.asset_bar.pack(before=self.toolbar, fill="x", pady=(0, 8))
        else:
            self.asset_bar.pack_forget()
        self.assets_button.configure(text="收合素材" if self.assets_visible else "顯示素材")

    def toggle_focus(self):
        """Temporarily enlarge the preview without touching animation state."""
        if not self.focused:
            self._assets_before_focus = self.assets_visible
            self._inspector_width = max(270, self.inspector.winfo_width())
            self.panes.forget(self.inspector)
            self._set_assets_visible(False)
            self.focused = True
            self.assets_button.configure(state="disabled")
            self.focus_button.configure(text="返回工作區 F8")
        else:
            self.panes.add(self.inspector, minsize=270, width=self._inspector_width,
                           stretch="never")
            self.focused = False
            self._set_assets_visible(self._assets_before_focus)
            self.assets_button.configure(state="normal")
            self.focus_button.configure(text="專注預覽 F8")

