"""Actual projected Diamond cage alignment; edits remain local until Apply."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
import math
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk
from spine_turn_ui_style import PALETTE, StudioButton

from spine_turn_diamond_editor import GUIDE_DEFAULTS
from spine_turn_region_editor import CanvasTransform

ALIGNMENT_DEFAULTS = {**GUIDE_DEFAULTS, 'diamond_table_depth': 0., 'diamond_waist_depth': 0.,
                      'diamond_ring_phase': 0., 'diamond_view_tilt': 12.}
BG, PANEL, TEXT, MUTED = (PALETTE[key] for key in ('BG', 'PANEL', 'TEXT', 'MUTED'))
TABLE, WAIST, TIP, ERROR = '#ffca70', '#71e2ed', '#db9cff', '#ff8585'
FIELD_LABELS = {
    'diamond_center_x': '中心左右位置（%）', 'diamond_table_y': '頂台中心高度（%）',
    'diamond_waist_y': '腰環中心高度（%）', 'diamond_tip_y': '底尖高度（%）',
    'diamond_table_width': '頂台寬度（%）', 'diamond_waist_width': '腰環寬度（%）',
    'diamond_table_depth': '頂台前後深度（% 圖寬）', 'diamond_waist_depth': '腰環前後深度（% 圖寬）',
    'diamond_ring_phase': '切面朝向（°）', 'diamond_view_tilt': '俯視角度（°）',
}


def _number(value, label):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{label}請輸入有效數值。') from None
    if not math.isfinite(result):
        raise ValueError(f'{label}請輸入有限數值。')
    return result


def _display_number(value, precision='g'):
    return format(0. if abs(value) < 1e-10 else value, precision)


class DiamondAlignmentModel:
    """Core owns projection/inverse projection; this class owns local history."""

    def __init__(self, options, image_size, *, alignment_fn=None, adjust_fn=None):
        self.context = asdict(options) if is_dataclass(options) else dict(options)
        self.image_size = tuple(image_size)
        self.alignment_fn, self.adjust_fn = alignment_fn, adjust_fn
        self.values = {name: _number(self.context.get(name, default), FIELD_LABELS[name])
                       for name, default in ALIGNMENT_DEFAULTS.items()}
        self._refresh(self.values)
        self.initial = dict(self.values)
        self._history = [self._state()]
        self._cursor = 0

    def _helpers(self):
        if self.alignment_fn is None or self.adjust_fn is None:
            from spine_turn_diamond import get_diamond_alignment, adjust_diamond_alignment
            return self.alignment_fn or get_diamond_alignment, self.adjust_fn or adjust_diamond_alignment
        return self.alignment_fn, self.adjust_fn

    def _refresh(self, values):
        values = {name: _number(values.get(name, default), FIELD_LABELS[name])
                  for name, default in ALIGNMENT_DEFAULTS.items()}
        if not 0 <= values['diamond_view_tilt'] <= 35:
            raise ValueError('俯視角度需介於 0° 到 35°。')
        get_alignment, _ = self._helpers()
        alignment = get_alignment({**self.context, **values}, *self.image_size)
        self.values = {name: _number(alignment['options'].get(name, values[name]), FIELD_LABELS[name])
                       for name in ALIGNMENT_DEFAULTS}
        self.alignment = alignment

    def _state(self):
        return tuple(self.values[name] for name in ALIGNMENT_DEFAULTS)

    @property
    def can_undo(self):
        return self._cursor > 0 or self._state() != self._history[self._cursor]

    @property
    def can_redo(self):
        return self._state() == self._history[self._cursor] and self._cursor + 1 < len(self._history)

    def commit(self):
        state = self._state()
        if state != self._history[self._cursor]:
            self._history = self._history[:self._cursor + 1] + [state]
            self._cursor += 1

    def set_values(self, changes, *, record=True):
        self._refresh({**self.values, **changes})
        if record:
            self.commit()

    def drag(self, handle, point, *, record=False):
        point = tuple(_number(value, '節點座標') for value in point)
        if len(point) != 2:
            raise ValueError('節點需要左右及上下兩個座標。')
        _, adjust = self._helpers()
        result = adjust({**self.context, **self.values}, handle, point, *self.image_size)
        self.set_values(result, record=record)

    def preset(self, mode):
        facets = int(self.context.get('diamond_facets', 8))
        if mode not in ('facet', 'ridge'):
            raise ValueError('請選擇正面切面或正面稜線。')
        self.set_values({'diamond_ring_phase': 180 / facets if mode == 'facet' else 0.})

    def reset(self):
        self.set_values(self.initial)

    def undo(self):
        self.commit()
        if self._cursor:
            self._cursor -= 1
            self._refresh(dict(zip(ALIGNMENT_DEFAULTS, self._history[self._cursor])))

    def redo(self):
        if self.can_redo:
            self._cursor += 1
            self._refresh(dict(zip(ALIGNMENT_DEFAULTS, self._history[self._cursor])))

    def validate(self):
        self._refresh(self.values)
        return dict(self.values)

    def handles(self):
        return self.alignment['handles']


class _AlignmentEditor:
    def __init__(self, parent, image, options, callback):
        self.image = image.convert('RGBA').copy()
        self.model = DiamondAlignmentModel(options, self.image.size)
        self.callback = callback
        self.selected = next(iter(self.model.handles()), None)
        self.dragging = self.pan_start = None
        self.zoom, self.pan_x, self.pan_y = 1., 0., 0.
        self.photo = None
        self._syncing = False
        self.field_error = self.drag_error = ''
        self.window = tk.Toplevel(parent)
        self.window.title('對齊鑽石實體切線 · Spine Turn Studio')
        self.window.configure(bg=BG)
        parent.update_idletasks()
        x = max(0, parent.winfo_rootx() + (parent.winfo_width() - 1080) // 2)
        y = max(0, parent.winfo_rooty() + (parent.winfo_height() - 760) // 2)
        self.window.geometry(f'1080x760+{x}+{y}')
        self.window.minsize(880, 650)
        self.window.transient(parent)
        self.window.result = None
        self.window.protocol('WM_DELETE_WINDOW', self.cancel)
        self.show_rear = tk.BooleanVar(self.window, value=False)
        self.show_cuts = tk.BooleanVar(self.window, value=False)
        self.fields = {name: tk.StringVar(self.window) for name in ALIGNMENT_DEFAULTS}
        self.point_x, self.point_y = tk.StringVar(self.window), tk.StringVar(self.window)
        self.selected_label, self.status = tk.StringVar(self.window), tk.StringVar(self.window)
        self.error_text = tk.StringVar(self.window)
        self._build()
        self.window.bind('<Control-z>', lambda event: self.action(self.model.undo))
        self.window.bind('<Control-y>', lambda event: self.action(self.model.redo))
        self.window.bind('<Escape>', lambda event: self.cancel())
        self.window.after_idle(self.refresh)
        self.window.grab_set()

    def label(self, parent, text='', **kwargs):
        settings = dict(text=text, bg=parent.cget('bg'), fg=TEXT, font=('Microsoft JhengHei UI', 10))
        settings.update(kwargs)
        return tk.Label(parent, **settings)

    def button(self, parent, text, command, primary=False):
        return StudioButton(parent, text=text, command=command, primary=primary,
            padx=12, pady=8, font=('Microsoft JhengHei UI', 10))

    def _build(self):
        header = tk.Frame(self.window, bg=BG, padx=18, pady=11)
        header.pack(fill='x')
        self.label(header, '把真正的立體切線，對齊原圖', font=('Microsoft JhengHei UI', 16, 'bold')).pack(anchor='w')
        self.label(header, '固定 0° 正面，使用目前俯視角度。拖前／後台緣、腰緣或寬度節點，調整實體輪廓。', fg=MUTED).pack(anchor='w', pady=(3, 0))
        toolbar = tk.Frame(self.window, bg=BG, padx=18)
        toolbar.pack(fill='x', pady=(0, 8))
        self.undo_button = self.button(toolbar, '復原', lambda: self.action(self.model.undo))
        self.undo_button.pack(side='left', padx=(0, 6))
        self.redo_button = self.button(toolbar, '重做', lambda: self.action(self.model.redo))
        self.redo_button.pack(side='left', padx=(0, 6))
        self.button(toolbar, '恢復開啟時', lambda: self.action(self.model.reset)).pack(side='left', padx=(0, 12))
        for text, variable in (('顯示背面線', self.show_rear), ('顯示原反光分區', self.show_cuts)):
            tk.Checkbutton(toolbar, text=text, variable=variable, command=self.redraw, bg=BG, fg=MUTED,
                selectcolor=PANEL, activebackground=BG, activeforeground=TEXT, font=('Microsoft JhengHei UI', 10)).pack(side='left', padx=(0, 9))
        body = tk.Frame(self.window, bg=BG, padx=18)
        body.pack(fill='both', expand=True)
        side_box = tk.Frame(body, bg=PANEL, width=280)
        side_box.pack(side='right', fill='y', padx=(12, 0))
        side_box.pack_propagate(False)
        side_scroll = ttk.Scrollbar(side_box, orient='vertical')
        side_scroll.pack(side='right', fill='y')
        self.side_canvas = tk.Canvas(side_box, bg=PANEL, highlightthickness=0, yscrollcommand=side_scroll.set)
        self.side_canvas.pack(fill='both', expand=True)
        side_scroll.configure(command=self.side_canvas.yview)
        side = tk.Frame(self.side_canvas, bg=PANEL, padx=12, pady=12)
        self.side_window = self.side_canvas.create_window(0, 0, window=side, anchor='nw')
        side.bind('<Configure>', lambda event: self.side_canvas.configure(scrollregion=self.side_canvas.bbox('all')))
        self.side_canvas.bind('<Configure>', lambda event: self.side_canvas.itemconfigure(self.side_window, width=event.width))
        self.label(side, '選取的實體控制點', fg=TABLE).pack(anchor='w')
        self.label(side, textvariable=self.selected_label, wraplength=240, justify='left').pack(anchor='w', pady=(7, 6))
        xy = tk.Frame(side, bg=PANEL)
        xy.pack(fill='x')
        self.point_entries = []
        for label, variable in (('左右 %', self.point_x), ('上下 %', self.point_y)):
            column = tk.Frame(xy, bg=PANEL)
            column.pack(side='left', fill='x', expand=True, padx=(0, 7))
            self.label(column, label, fg=MUTED, font=('Microsoft JhengHei UI', 9)).pack(anchor='w')
            entry = ttk.Entry(column, textvariable=variable, width=9)
            entry.pack(fill='x')
            entry.bind('<Return>', lambda event: self.move_selected())
            self.point_entries.append(entry)
        self.button(side, '移動選取點', self.move_selected).pack(fill='x', pady=(7, 10))
        self.label(side, '正面切線排列', fg=TABLE).pack(anchor='w')
        self.button(side, '正面為切面', lambda: self.action(lambda: self.model.preset('facet'))).pack(fill='x', pady=(6, 4))
        self.button(side, '正面為稜線', lambda: self.action(lambda: self.model.preset('ridge'))).pack(fill='x')
        self.label(side, f'目前環形分段：{int(self.model.context.get("diamond_facets", 8))}', fg=MUTED,
            font=('Microsoft JhengHei UI', 9)).pack(anchor='w', pady=(5, 9))
        for name in ('diamond_view_tilt', 'diamond_table_depth', 'diamond_waist_depth', 'diamond_ring_phase'):
            self._field(side, name)
        self.label(side, '深度是整圈前後厚度；0 使用原本自動值。\n前／後控制點上下拖動時，另一側保持原位。',
            fg=MUTED, justify='left', wraplength=240, font=('Microsoft JhengHei UI', 9)).pack(anchor='w', pady=(7, 13))
        self.label(side, '環中心與寬度（進階）', fg=TABLE).pack(anchor='w')
        for name in GUIDE_DEFAULTS:
            self._field(side, name)
        self.label(side, '中心高度不是前側切線位置。\n實線是可見實體切邊，虛線是背面切邊。\n原反光分區只供對照，不會自動改變輪廓。',
            fg=MUTED, justify='left', wraplength=240, font=('Microsoft JhengHei UI', 9)).pack(anchor='w', pady=(10, 5))
        # Scroll only while the cursor is over the sidebar, never the image.
        def bind_scroll(widget):
            widget.bind('<MouseWheel>', self.scroll_sidebar)
            for child in widget.winfo_children():
                bind_scroll(child)
        bind_scroll(side)
        self.side_canvas.bind('<MouseWheel>', self.scroll_sidebar)
        canvas_box = tk.Frame(body, bg=BG)
        canvas_box.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(canvas_box, bg='#151e2c', highlightthickness=1, highlightbackground='#334155', cursor='crosshair')
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda event: self.redraw())
        self.canvas.bind('<Button-1>', self.press)
        self.canvas.bind('<B1-Motion>', self.move)
        self.canvas.bind('<ButtonRelease-1>', self.release)
        self.canvas.bind('<MouseWheel>', self.wheel)
        self.canvas.bind('<Button-2>', self.pan_press)
        self.canvas.bind('<B2-Motion>', self.pan_move)
        self.canvas.bind('<ButtonRelease-2>', lambda event: setattr(self, 'pan_start', None))
        legend = tk.Frame(canvas_box, bg=BG)
        legend.pack(fill='x', pady=(5, 0))
        self.label(legend, '頂台 / 上切面', fg=TABLE, font=('Microsoft JhengHei UI', 9)).pack(side='left', padx=(0, 12))
        self.label(legend, '腰環 / 下切面', fg=WAIST, font=('Microsoft JhengHei UI', 9)).pack(side='left')
        self.button(legend, '符合視窗', self.fit).pack(side='right')
        footer = tk.Frame(self.window, bg=BG, padx=18, pady=9)
        footer.pack(fill='x')
        self.label(footer, textvariable=self.status, fg=MUTED, anchor='w', wraplength=1040).pack(fill='x')
        self.label(footer, textvariable=self.error_text, fg=ERROR, anchor='w', height=2, wraplength=1040).pack(fill='x')
        buttons = tk.Frame(footer, bg=BG)
        buttons.pack(fill='x')
        self.label(buttons, '滾輪縮放 · 中鍵平移 · 取消不會修改目前設定', fg=MUTED,
            font=('Microsoft JhengHei UI', 9)).pack(side='left')
        self.button(buttons, '取消', self.cancel).pack(side='right', padx=(8, 0))
        self.apply_button = self.button(buttons, '套用輪廓與深度', self.apply, True)
        self.apply_button.pack(side='right')

    def scroll_sidebar(self, event):
        self.side_canvas.yview_scroll(-int(event.delta / 120), 'units')
        # Stop TSpinbox's class binding from also changing a geometric value.
        return 'break'

    def _field(self, parent, name):
        self.label(parent, FIELD_LABELS[name], font=('Microsoft JhengHei UI', 9)).pack(anchor='w', pady=(7, 2))
        degrees = name in ('diamond_view_tilt', 'diamond_ring_phase')
        lower, upper = (0, 35) if name == 'diamond_view_tilt' else (-180, 180) if degrees else (0, 200) if name.endswith('_depth') else (-50, 50) if name.endswith(('_x', '_y')) else (1, 100)
        spin = ttk.Spinbox(parent, from_=lower, to=upper, increment=.5 if degrees else 1,
            textvariable=self.fields[name], command=self.commit_fields, width=12)
        spin.pack(fill='x')
        spin.bind('<FocusOut>', lambda event: self.commit_fields())
        spin.bind('<Return>', lambda event: self.commit_fields())
        self.fields[name].trace_add('write', lambda *_: self.fields_changed())

    def refresh(self):
        self._syncing = True
        try:
            for name, value in self.model.values.items():
                multiplier = 1 if name in ('diamond_view_tilt', 'diamond_ring_phase') else 100
                self.fields[name].set(_display_number(value * multiplier))
            handles = self.model.handles()
            if self.selected not in handles:
                self.selected = next(iter(handles), None)
            if self.selected is not None:
                handle = handles[self.selected]
                vertical = handle.get('kind') in ('front', 'back', 'tip')
                self.selected_label.set(handle.get('label', self.selected) + (' · 上下移動' if vertical else ' · 左右移動'))
                self.point_x.set(_display_number(handle['point'][0] * 100, '.5g'))
                self.point_y.set(_display_number(handle['point'][1] * 100, '.5g'))
                self.point_entries[0].configure(state='readonly' if vertical else 'normal')
                self.point_entries[1].configure(state='normal' if vertical else 'readonly')
        finally:
            self._syncing = False
        self.undo_button.configure(state='normal' if self.model.can_undo else 'disabled')
        self.redo_button.configure(state='normal' if self.model.can_redo else 'disabled')
        self.apply_button.configure(state='disabled' if self.field_error else 'normal')
        self.error_text.set(self.field_error or self.drag_error)
        self.status.set('0° 正面校準 · 拖前／後環邊改變實體深度，對側保持固定；底尖與寬度也可直接拖曳。')
        if self.model.values['diamond_view_tilt'] < 2:
            self.status.set('目前俯視角小於 2°，前後邊幾乎重疊；需要拖前後邊時，請先提高俯視角。開啟不會改動原值。')
        self.redraw()

    def fields_changed(self):
        if self._syncing:
            return
        try:
            values = {name: _number(variable.get(), FIELD_LABELS[name]) /
                (1 if name in ('diamond_view_tilt', 'diamond_ring_phase') else 100)
                for name, variable in self.fields.items()}
            self.model.set_values(values, record=False)
            self.field_error = ''
        except ValueError as exc:
            self.field_error = str(exc)
        self.error_text.set(self.field_error)
        self.apply_button.configure(state='disabled' if self.field_error else 'normal')
        self.redraw()

    def commit_fields(self):
        if not self.field_error:
            self.model.commit()
            self.refresh()

    def action(self, callback):
        try:
            callback()
            self.field_error = self.drag_error = ''
        except ValueError as exc:
            self.drag_error = str(exc)
        self.refresh()
        return 'break'

    def transform(self):
        return CanvasTransform(*self.image.size, max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height()),
            padding=36, zoom=self.zoom, pan_x=self.pan_x, pan_y=self.pan_y)

    def redraw(self):
        if not hasattr(self, 'canvas') or not self.window.winfo_exists():
            return
        transform = self.transform()
        width, height = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        image = Image.new('RGBA', (width, height), '#151e2c')
        draw = ImageDraw.Draw(image)
        for y in range(0, height, 16):
            for x in range(0, width, 16):
                if (x // 16 + y // 16) % 2:
                    draw.rectangle((x, y, x + 15, y + 15), fill='#202e40')
        size = tuple(max(1, round(value * transform.scale)) for value in self.image.size)
        origin_x, origin_y = transform.origin
        image.alpha_composite(self.image.resize(size, Image.Resampling.LANCZOS),
            (round(origin_x - size[0] / 2), round(origin_y - size[1] / 2)))
        self.photo = ImageTk.PhotoImage(image, master=self.window)
        self.canvas.delete('all')
        self.canvas.create_image(0, 0, image=self.photo, anchor='nw')
        if self.show_cuts.get():
            for points, _, _ in self.model.context.get('diamond_cut_regions', ()):
                self.canvas.create_polygon(*(value for point in points for value in transform.to_canvas(point)),
                    fill='', outline='#737b98', width=1, dash=(2, 5))
        alignment = self.model.alignment
        nodes = alignment['nodes']
        for edge in sorted(alignment['edges'], key=lambda edge: edge.get('visible', True)):
            if edge.get('internal', False):
                continue
            visible = edge.get('visible', True)
            if not visible and not self.show_rear.get():
                continue
            first, second = nodes[edge['a']]['point'], nodes[edge['b']]['point']
            color = TABLE if edge.get('zone') in ('table', 'crown') else WAIST
            self.canvas.create_line(*transform.to_canvas(first), *transform.to_canvas(second),
                fill=color if visible else '#66758d', width=1.8 if visible else 1,
                dash=() if visible else (5, 4))
        for name, handle in self.model.handles().items():
            x, y = transform.to_canvas(handle['point'])
            selected = name == self.selected
            color = TIP if name == 'tip' else TABLE if name.startswith('table') else WAIST
            radius = 7 if selected else 5
            self.canvas.create_oval(x - radius, y - radius, x + radius, y + radius,
                fill=color if selected else BG, outline=color, width=2)
            if selected or 'front' in name or 'back' in name or name == 'tip':
                text_id = self.canvas.create_text(x + 10, y - 8, text=handle.get('label', name), fill=color,
                    anchor='sw', font=('Microsoft JhengHei UI', 9, 'bold'))
                box = self.canvas.bbox(text_id)
                if box:
                    backdrop = self.canvas.create_rectangle(box[0] - 3, box[1] - 1, box[2] + 3, box[3] + 1,
                        fill=BG, outline='')
                    self.canvas.tag_lower(backdrop, text_id)

    def press(self, event):
        self.canvas.focus_set()
        transform = self.transform()
        handles = self.model.handles()
        distance, handle = min((math.dist((event.x, event.y), transform.to_canvas(value['point'])), name)
                               for name, value in handles.items())
        if distance <= 13:
            self.model.commit()
            self.selected = self.dragging = handle
            self.field_error = self.drag_error = ''
            self.refresh()

    def move(self, event):
        if self.dragging:
            try:
                self.model.drag(self.dragging, self.transform().to_normalized((event.x, event.y)))
                self.drag_error = ''
            except ValueError as exc:
                self.drag_error = str(exc)
            self.refresh()

    def release(self, event=None):
        if self.dragging:
            self.model.commit()
        self.dragging = None
        self.refresh()

    def move_selected(self):
        if self.selected is not None:
            try:
                point = _number(self.point_x.get(), '左右位置') / 100, _number(self.point_y.get(), '上下位置') / 100
                self.model.drag(self.selected, point, record=True)
                self.field_error = self.drag_error = ''
            except ValueError as exc:
                self.drag_error = str(exc)
            self.refresh()

    def wheel(self, event):
        point = self.transform().to_normalized((event.x, event.y))
        self.zoom = max(.35, min(5., self.zoom * (1.15 if event.delta > 0 else 1 / 1.15)))
        after = self.transform().to_canvas(point)
        self.pan_x += event.x - after[0]
        self.pan_y += event.y - after[1]
        self.redraw()

    def pan_press(self, event):
        self.pan_start = event.x, event.y, self.pan_x, self.pan_y

    def pan_move(self, event):
        if self.pan_start:
            x, y, origin_x, origin_y = self.pan_start
            self.pan_x, self.pan_y = origin_x + event.x - x, origin_y + event.y - y
            self.redraw()

    def fit(self):
        self.zoom, self.pan_x, self.pan_y = 1., 0., 0.
        self.redraw()

    def apply(self):
        if self.field_error:
            return
        try:
            self.model.commit()
            result = self.model.validate()
            if self.callback is not None:
                self.callback(dict(result))
            self.window.result = dict(result)
        except (ValueError, RuntimeError) as exc:
            self.field_error = str(exc)
            self.refresh()
            return
        self._destroy()

    def cancel(self):
        self.window.result = None
        self._destroy()

    def _destroy(self):
        try:
            self.window.grab_release()
        except tk.TclError:
            pass
        self.window.destroy()


def open_diamond_alignment_editor(parent, image_rgba, options, on_apply):
    """Open actual front-zero wire alignment; Apply calls ``on_apply(dict)`` only."""
    editor = _AlignmentEditor(parent, image_rgba, options, on_apply)
    editor.window.diamond_alignment_editor = editor
    return editor.window
