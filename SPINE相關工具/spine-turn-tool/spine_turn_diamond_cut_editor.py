"""Local, image-space Diamond reflection regions with shared-point editing."""
from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk

from spine_turn_region_editor import CanvasTransform

BG, PANEL, TEXT, MUTED = '#101722', '#1c2738', '#edf3fc', '#9cacc2'
AMBER, ERROR = '#ffca70', '#ff8585'
COLORS = ('#71e2ed', '#ffca70', '#db9cff', '#8de2b0', '#ff9eb8', '#91baff')
DRAWING_MODES = {'upper4': ('上方四點', 4), 'lower3': ('下方三點', 3), 'free': ('自由畫線', None)}


def _point(point):
    try:
        values = tuple(float(value) for value in point)
    except (TypeError, ValueError):
        raise ValueError('切面節點請使用有效座標。') from None
    if len(values) != 2 or not all(math.isfinite(value) and -.5 <= value <= .5 for value in values):
        raise ValueError('請在圖片範圍內放置切面節點。')
    return values


def _freeze(regions):
    try:
        return tuple((tuple(_point(point) for point in points), float(yaw), float(pitch))
                     for points, yaw, pitch in regions)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'切面資料無效：{exc}') from None


def _same(a, b):
    return math.dist(a, b) < 1e-9


def _contains(point, polygon):
    signs = []
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        value = (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0])
        if abs(value) > 1e-10:
            signs.append(value > 0)
    return bool(signs) and all(value == signs[0] for value in signs)


class DiamondCutModel:
    """Immutable snapshots; a shared coordinate denotes a shared editable node."""

    def __init__(self, regions=(), *, validator=None, drawing_mode='upper4'):
        self.validator = validator
        self.regions = self._validate(regions)
        self.initial = self.regions
        self.draft = ()
        self.drawing = False
        if drawing_mode not in DRAWING_MODES:
            raise ValueError('請選擇上方四點、下方三點或自由畫線。')
        self.drawing_mode = drawing_mode
        self.selected = 0 if self.regions else None
        self._history = [self._state()]
        self._cursor = 0

    def _validate(self, regions):
        validator = self.validator
        if validator is None:
            from spine_turn_diamond_cuts import validate_cut_regions
            validator = validate_cut_regions
        return _freeze(validator(_freeze(regions)))

    def validate(self):
        if self.draft:
            raise ValueError('請先封閉目前切面，或按「取消繪製」。')
        return self._validate(self.regions)

    def _state(self):
        return self.regions, self.draft, self.drawing, self.selected, self.drawing_mode

    @property
    def target_count(self):
        return DRAWING_MODES[self.drawing_mode][1]

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

    def undo(self):
        self.commit()
        if self._cursor:
            self._cursor -= 1
            self.regions, self.draft, self.drawing, self.selected, self.drawing_mode = self._history[self._cursor]

    def redo(self):
        if self.can_redo:
            self._cursor += 1
            self.regions, self.draft, self.drawing, self.selected, self.drawing_mode = self._history[self._cursor]

    def set_drawing_mode(self, mode):
        if mode not in DRAWING_MODES:
            raise ValueError('請選擇上方四點、下方三點或自由畫線。')
        if self.draft:
            raise ValueError('請先完成目前切面，或按「取消繪製」，再切換點數模式。')
        self.drawing_mode = mode
        self.commit()

    def start_drawing(self, mode=None):
        if len(self.regions) >= 24:
            raise ValueError('最多可設定 24 個切面。')
        if mode is not None:
            self.set_drawing_mode(mode)
        self.drawing, self.selected = True, None
        self.commit()

    def add_point(self, point):
        if not self.drawing:
            raise ValueError('請先按「新增切面」。')
        point = _point(point)
        if self.target_count is not None and len(self.draft) >= self.target_count:
            raise ValueError(f'「{DRAWING_MODES[self.drawing_mode][0]}」已有 {self.target_count} 點，請拖曳節點修正後按 Enter，或取消重畫。')
        if len(self.draft) >= 12:
            raise ValueError('每個切面最多 12 個節點；請點第一點完成。')
        if any(_same(point, other) for other in self.draft):
            raise ValueError('節點不可重疊；點第一點可封閉切面。')
        self.draft += (point,)
        self.commit()
        if self.target_count is not None and len(self.draft) == self.target_count:
            return self.close_draft()

    def close_draft(self):
        if len(self.draft) < 3:
            raise ValueError('至少需要 3 個節點才能封閉切面。')
        if self.target_count is not None and len(self.draft) != self.target_count:
            raise ValueError(f'「{DRAWING_MODES[self.drawing_mode][0]}」需要 {self.target_count} 個節點，目前只有 {len(self.draft)} 點。')
        x = sum(point[0] for point in self.draft) / len(self.draft)
        y = sum(point[1] for point in self.draft) / len(self.draft)
        candidate = (self.draft, max(-60., min(60., x * 60)), max(-60., min(60., y * 40)))
        self.regions = self._validate(self.regions + (candidate,))
        self.selected, self.draft, self.drawing = len(self.regions) - 1, (), False
        self.commit()
        return self.regions[self.selected]

    def cancel_draft(self):
        self.draft, self.drawing = (), False
        self.commit()

    def delete_selected(self):
        if self.draft:
            self.draft = self.draft[:-1]
        elif self.selected is not None:
            self.regions = self.regions[:self.selected] + self.regions[self.selected + 1:]
            self.selected = min(self.selected, len(self.regions) - 1) if self.regions else None
        self.commit()

    def clear(self):
        self.regions, self.draft, self.drawing, self.selected = (), (), False, None
        self.commit()

    def reset(self):
        self.regions, self.draft, self.drawing = self.initial, (), False
        self.selected = 0 if self.regions else None
        self.commit()

    def set_angles(self, yaw, pitch, *, record=True):
        if self.selected is None:
            raise ValueError('請先選取一個切面。')
        try:
            yaw, pitch = float(yaw), float(pitch)
        except (TypeError, ValueError):
            raise ValueError('反光方向請輸入 −60 到 60 度。') from None
        if not all(math.isfinite(value) and -60 <= value <= 60 for value in (yaw, pitch)):
            raise ValueError('反光方向需介於 −60 到 60 度。')
        values = list(self.regions)
        values[self.selected] = (values[self.selected][0], yaw, pitch)
        self.regions = self._validate(values)
        if record:
            self.commit()

    def move_vertex(self, region_index, vertex_index, point, *, record=True):
        point = _point(point)
        old = self.regions[region_index][0][vertex_index]
        values = []
        for points, yaw, pitch in self.regions:
            values.append((tuple(point if _same(vertex, old) else vertex for vertex in points), yaw, pitch))
        # Validate the entire connected patch before committing any position.
        self.regions = self._validate(values)
        self.selected = region_index
        if record:
            self.commit()

    def move_draft_vertex(self, index, point, *, record=True):
        point = _point(point)
        if any(i != index and _same(point, other) for i, other in enumerate(self.draft)):
            raise ValueError('草稿節點不可重疊。')
        self.draft = self.draft[:index] + (point,) + self.draft[index + 1:]
        if record:
            self.commit()

    def snap_point(self, point, transform, radius=8, *, exclude=None):
        """Snap in screen pixels, independent of image size, aspect or zoom."""
        canvas_point = transform.to_canvas(point)
        best, distance = _point(point), float(radius)
        for points, _, _ in self.regions:
            for vertex in points:
                if exclude is not None and _same(vertex, exclude):
                    continue
                candidate = math.dist(canvas_point, transform.to_canvas(vertex))
                if candidate <= distance:
                    best, distance = vertex, candidate
        return best


class _DiamondCutEditor:
    def __init__(self, parent, image, options, callback):
        self.image = image.convert('RGBA').copy()
        regions = options.get('diamond_cut_regions', ()) if isinstance(options, dict) else getattr(options, 'diamond_cut_regions', ())
        self.model = DiamondCutModel(regions)
        self.callback = callback
        self.zoom, self.pan_x, self.pan_y = 1., 0., 0.
        self.dragging = self.pan_start = None
        self.photo = None
        self.error = self.field_error = ''
        self._syncing = False
        self.window = tk.Toplevel(parent)
        self.window.title('繪製鑽石切面 · Spine Turn Studio')
        self.window.configure(bg=BG)
        parent.update_idletasks()
        x = max(0, parent.winfo_rootx() + (parent.winfo_width() - 980) // 2)
        y = max(0, parent.winfo_rooty() + (parent.winfo_height() - 740) // 2)
        self.window.geometry(f'980x740+{x}+{y}')
        self.window.minsize(820, 620)
        self.window.transient(parent)
        self.window.result = None
        self.window.protocol('WM_DELETE_WINDOW', self.cancel)
        self.yaw = tk.StringVar(self.window)
        self.pitch = tk.StringVar(self.window)
        self.mode_choice = tk.StringVar(self.window, value=DRAWING_MODES[self.model.drawing_mode][0])
        self.slider_values = (tk.DoubleVar(self.window), tk.DoubleVar(self.window))
        self.status = tk.StringVar(self.window)
        self.error_text = tk.StringVar(self.window)
        self._build()
        self.yaw.trace_add('write', lambda *_: self.change_angles())
        self.pitch.trace_add('write', lambda *_: self.change_angles())
        for index, variable in enumerate(self.slider_values):
            variable.trace_add('write', lambda *_, index=index: self.slider_changed(index))
        self.window.bind('<Control-z>', lambda event: self.action(self.model.undo))
        self.window.bind('<Control-y>', lambda event: self.action(self.model.redo))
        self.window.bind('<Return>', lambda event: self.action(self.model.close_draft) if self.model.drawing else self.commit_angles())
        self.window.bind('<Delete>', lambda event: self.action(self.model.delete_selected))
        self.window.bind('<Escape>', lambda event: self.action(self.model.cancel_draft) if self.model.drawing else self.cancel())
        self.window.after_idle(self.refresh)
        self.window.grab_set()

    def label(self, parent, text='', **kwargs):
        settings = dict(text=text, bg=parent.cget('bg'), fg=TEXT, font=('Microsoft JhengHei UI', 10))
        settings.update(kwargs)
        return tk.Label(parent, **settings)

    def button(self, parent, text, command, primary=False):
        return tk.Button(parent, text=text, command=command, bg=AMBER if primary else PANEL,
            fg=BG if primary else TEXT, activebackground='#b7c8e0', bd=0, padx=12, pady=8,
            cursor='hand2', font=('Microsoft JhengHei UI', 10), disabledforeground='#64748b')

    def _build(self):
        header = tk.Frame(self.window, bg=BG, padx=18, pady=10)
        header.pack(fill='x')
        self.label(header, '沿著原圖，畫出每一個切面', font=('Microsoft JhengHei UI', 16, 'bold')).pack(anchor='w')
        self.label(header, '圈出凸多邊形切面，再調整各區反光方向。鑽石的外形與整體立體模型維持原設定。', fg=MUTED).pack(anchor='w', pady=(3, 0))
        toolbar = tk.Frame(self.window, bg=BG, padx=18)
        toolbar.pack(fill='x', pady=(0, 8))
        self.label(toolbar, '畫線模式', fg=MUTED).pack(side='left', padx=(0, 7))
        self.mode_control = ttk.Combobox(toolbar, textvariable=self.mode_choice,
            values=tuple(mode[0] for mode in DRAWING_MODES.values()), state='readonly', width=11)
        self.mode_control.pack(side='left', padx=(0, 8))
        self.mode_control.bind('<<ComboboxSelected>>', self.change_mode)
        self.new_button = self.button(toolbar, '＋ 新增切面', lambda: self.action(self.model.start_drawing), True)
        self.new_button.pack(side='left', padx=(0, 6))
        self.close_button = self.button(toolbar, '封閉切面 ↵', lambda: self.action(self.model.close_draft))
        self.close_button.pack(side='left', padx=(0, 6))
        self.button(toolbar, '取消繪製', lambda: self.action(self.model.cancel_draft)).pack(side='left')
        history_bar = tk.Frame(self.window, bg=BG, padx=18)
        history_bar.pack(fill='x', pady=(0, 7))
        self.undo_button = self.button(history_bar, '復原', lambda: self.action(self.model.undo))
        self.undo_button.pack(side='left', padx=(0, 6))
        self.redo_button = self.button(history_bar, '重做', lambda: self.action(self.model.redo))
        self.redo_button.pack(side='left', padx=(0, 6))
        self.button(history_bar, '恢復開啟時', lambda: self.action(self.model.reset)).pack(side='left')
        self.button(history_bar, '清除全部', lambda: self.action(self.model.clear)).pack(side='left', padx=(6, 0))
        self.label(history_bar, '上方四點、下方三點會自動封閉；自由畫線可用 3–12 點。',
            fg=MUTED, font=('Microsoft JhengHei UI', 9)).pack(side='left', padx=(12, 0))
        body = tk.Frame(self.window, bg=BG, padx=18)
        body.pack(fill='both', expand=True)
        side = tk.Frame(body, bg=PANEL, padx=12, pady=12, width=222)
        side.pack(side='right', fill='y', padx=(12, 0))
        side.pack_propagate(False)
        self.label(side, '切面區域', fg=AMBER).pack(anchor='w')
        self.region_list = tk.Listbox(side, bg='#101b2a', fg=TEXT, selectbackground='#355577',
            selectforeground=TEXT, exportselection=False, height=3, bd=0, highlightthickness=0,
            font=('Microsoft JhengHei UI', 10), activestyle='none')
        self.region_list.pack(fill='both', expand=True, pady=(7, 6))
        self.region_list.bind('<<ListboxSelect>>', self.select_list)
        self.delete_button = self.button(side, '刪除選取切面', lambda: self.action(self.model.delete_selected))
        self.delete_button.pack(fill='x')
        self.angle_controls = []
        for number, (text, variable) in enumerate((('左右反光方向（度）', self.yaw), ('上下反光方向（度）', self.pitch))):
            self.label(side, text, font=('Microsoft JhengHei UI', 9)).pack(anchor='w', pady=(12, 0))
            slider = tk.Scale(side, from_=-60, to=60, orient='horizontal', variable=self.slider_values[number],
                resolution=1, showvalue=False, bg=PANEL, troughcolor='#2b3b50', fg=TEXT,
                highlightthickness=0, activebackground=AMBER, bd=0)
            slider.pack(fill='x')
            slider.bind('<ButtonRelease-1>', lambda event: self.commit_angles())
            spin = ttk.Spinbox(side, from_=-60, to=60, increment=1, textvariable=variable,
                command=self.commit_angles, width=8)
            spin.pack(fill='x')
            spin.bind('<FocusOut>', lambda event: self.commit_angles())
            self.angle_controls.extend((slider, spin))
        self.label(side, '方向依切面位置估算，可再調整。\n這是各區反光設定，不會重建原圖深度。', fg=MUTED,
            justify='left', wraplength=195, font=('Microsoft JhengHei UI', 9)).pack(anchor='w', pady=(12, 0))
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
        zoom_bar = tk.Frame(canvas_box, bg=BG)
        zoom_bar.pack(fill='x', pady=(5, 0))
        self.label(zoom_bar, '滾輪縮放 · 中鍵平移 · 相鄰節點會吸附', fg=MUTED, font=('Microsoft JhengHei UI', 9)).pack(side='left')
        self.button(zoom_bar, '符合視窗', self.fit).pack(side='right')
        footer = tk.Frame(self.window, bg=BG, padx=18, pady=9)
        footer.pack(fill='x')
        self.label(footer, textvariable=self.status, fg=MUTED, anchor='w').pack(fill='x')
        self.label(footer, textvariable=self.error_text, fg=ERROR, anchor='w', height=2, wraplength=930).pack(fill='x')
        buttons = tk.Frame(footer, bg=BG)
        buttons.pack(fill='x')
        self.label(buttons, '每區 3–12 點，最多 24 區；共用邊可接合，區域不可重疊。', fg=MUTED, font=('Microsoft JhengHei UI', 9)).pack(side='left')
        self.button(buttons, '取消', self.cancel).pack(side='right', padx=(8, 0))
        self.apply_button = self.button(buttons, '套用切面', self.apply, True)
        self.apply_button.pack(side='right')

    def transform(self):
        return CanvasTransform(*self.image.size, max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height()),
                               padding=26, zoom=self.zoom, pan_x=self.pan_x, pan_y=self.pan_y)

    def refresh(self):
        self._syncing = True
        try:
            self.region_list.delete(0, 'end')
            for index, (points, yaw, pitch) in enumerate(self.model.regions):
                self.region_list.insert('end', f'{index + 1:02d}  切面 · {len(points)} 點')
                self.region_list.itemconfig(index, fg=COLORS[index % len(COLORS)])
            selected = self.model.selected
            self.mode_choice.set(DRAWING_MODES[self.model.drawing_mode][0])
            self.mode_control.configure(state='disabled' if self.model.draft else 'readonly')
            active = selected is not None
            if active:
                self.region_list.selection_set(selected)
                self.region_list.see(selected)
                self.yaw.set(f'{self.model.regions[selected][1]:g}')
                self.pitch.set(f'{self.model.regions[selected][2]:g}')
            else:
                self.yaw.set('0'); self.pitch.set('0')
            self.slider_values[0].set(float(self.yaw.get()))
            self.slider_values[1].set(float(self.pitch.get()))
            for control in self.angle_controls:
                control.configure(state='normal' if active else 'disabled')
            self.delete_button.configure(state='normal' if active or self.model.draft else 'disabled',
                text='刪除最後一點' if self.model.draft else '刪除選取切面')
            self.new_button.configure(state='normal' if len(self.model.regions) < 24 and not self.model.drawing else 'disabled')
            complete = (len(self.model.draft) == self.model.target_count if self.model.target_count is not None
                        else len(self.model.draft) >= 3)
            self.close_button.configure(state='normal' if complete else 'disabled')
            self.undo_button.configure(state='normal' if self.model.can_undo else 'disabled')
            self.redo_button.configure(state='normal' if self.model.can_redo else 'disabled')
            self.apply_button.configure(state='disabled' if self.model.draft else 'normal')
        finally:
            self._syncing = False
        if self.model.drawing:
            if self.model.target_count is not None:
                label, count = DRAWING_MODES[self.model.drawing_mode]
                hint = '點滿後自動封閉。' if len(self.model.draft) < count else '請拖曳節點修正，再按 Enter 封閉。'
                self.status.set(f'{label} · {len(self.model.draft)}/{count} 點。{hint} Esc 取消這次繪製。')
            else:
                self.status.set(f'自由畫線 · {len(self.model.draft)}/12 點。點第一點或按 Enter 封閉；Esc 取消這次繪製。')
        else:
            self.status.set(f'共 {len(self.model.regions)}/24 個切面。點選區域調整反光；拖曳節點可對齊原圖，共用節點同步移動。')
        self.error_text.set(self.error or self.field_error)
        self.redraw()

    def redraw(self):
        if not hasattr(self, 'canvas'):
            return
        transform = self.transform()
        canvas_w, canvas_h = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        backing = Image.new('RGBA', (canvas_w, canvas_h), '#151e2c')
        draw = ImageDraw.Draw(backing)
        for y in range(0, canvas_h, 14):
            for x in range(0, canvas_w, 14):
                if (x // 14 + y // 14) % 2:
                    draw.rectangle((x, y, x + 13, y + 13), fill='#1b2737')
        image_size = tuple(max(1, round(value * transform.scale)) for value in self.image.size)
        scaled = self.image.resize(image_size, Image.Resampling.LANCZOS)
        origin_x, origin_y = transform.origin
        backing.alpha_composite(scaled, (round(origin_x - image_size[0] / 2), round(origin_y - image_size[1] / 2)))
        self.photo = ImageTk.PhotoImage(backing, master=self.window)
        self.canvas.delete('all')
        self.canvas.create_image(0, 0, image=self.photo, anchor='nw')
        for index, (points, _, _) in enumerate(self.model.regions):
            selected = index == self.model.selected
            color = COLORS[index % len(COLORS)]
            xy = tuple(value for point in points for value in transform.to_canvas(point))
            self.canvas.create_polygon(*xy, fill='', outline=color, width=3 if selected else 1.7)
            center = tuple(sum(point[i] for point in points) / len(points) for i in range(2))
            x, y = transform.to_canvas(center)
            self.canvas.create_oval(x - 11, y - 11, x + 11, y + 11, fill=PANEL, outline=color)
            self.canvas.create_text(x, y, text=str(index + 1), fill=color, font=('Segoe UI', 9, 'bold'))
            for vertex in points:
                x, y = transform.to_canvas(vertex)
                radius = 4.5 if selected else 2.5
                self.canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill=color, outline=BG)
        if self.model.draft:
            xy = tuple(value for point in self.model.draft for value in transform.to_canvas(point))
            if len(self.model.draft) > 1:
                self.canvas.create_line(*xy, fill=AMBER, width=2, dash=(5, 3))
            for index, vertex in enumerate(self.model.draft):
                x, y = transform.to_canvas(vertex)
                radius = 7 if index == 0 else 4
                self.canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill=BG, outline=AMBER, width=2)

    def action(self, action):
        try:
            action()
            self.error = self.field_error = ''
        except (ValueError, IndexError) as exc:
            self.error = str(exc)
        self.refresh()

    def select_list(self, event=None):
        if self._syncing:
            return
        selected = self.region_list.curselection()
        if selected and not self.model.draft:
            self.model.drawing = False
            self.model.selected = int(selected[0])
            self.error = self.field_error = ''
            self.refresh()

    def change_mode(self, event=None):
        if not self._syncing:
            mode = next((name for name, values in DRAWING_MODES.items() if values[0] == self.mode_choice.get()), None)
            self.action(lambda: self.model.set_drawing_mode(mode))

    def change_angles(self):
        if self._syncing or self.model.selected is None:
            return
        try:
            self.model.set_angles(self.yaw.get(), self.pitch.get(), record=False)
            self.field_error = ''
            if hasattr(self, 'slider_values'):
                self._syncing = True
                try:
                    for variable, value in zip(self.slider_values, (self.yaw.get(), self.pitch.get())):
                        if abs(variable.get() - float(value)) > 1e-9:
                            variable.set(float(value))
                finally:
                    self._syncing = False
        except ValueError as exc:
            self.field_error = str(exc)
        self.error_text.set(self.field_error)

    def slider_changed(self, index):
        if not self._syncing:
            (self.yaw, self.pitch)[index].set(f'{self.slider_values[index].get():g}')

    def commit_angles(self):
        if self._syncing:
            return
        self.change_angles()
        if not self.field_error:
            self.model.commit()
        self.error_text.set(self.field_error)
        self.undo_button.configure(state='normal' if self.model.can_undo else 'disabled')
        self.redo_button.configure(state='normal' if self.model.can_redo else 'disabled')

    def press(self, event):
        transform = self.transform()
        screen = (event.x, event.y)
        point = transform.to_normalized(screen)
        if not all(-.5 <= value <= .5 for value in point):
            self.error = '請在圖片內繪製或選取節點。'
            self.refresh()
            return
        if self.model.drawing:
            for index, vertex in enumerate(self.model.draft):
                if math.dist(screen, transform.to_canvas(vertex)) <= 8:
                    if index == 0 and len(self.model.draft) >= 3:
                        self.action(self.model.close_draft)
                    else:
                        self.dragging = ('draft', index)
                    return
            point = self.model.snap_point(point, transform)
            self.action(lambda: self.model.add_point(point))
            return
        order = list(range(len(self.model.regions)))
        if self.model.selected is not None:
            order.remove(self.model.selected); order.insert(0, self.model.selected)
        for region_index in order:
            for vertex_index, vertex in enumerate(self.model.regions[region_index][0]):
                if math.dist(screen, transform.to_canvas(vertex)) <= 8:
                    self.model.commit()
                    self.model.selected = region_index
                    self.dragging = ('region', region_index, vertex_index)
                    self.error = self.field_error = ''
                    self.refresh()
                    return
        for index in reversed(order):
            if _contains(point, self.model.regions[index][0]):
                self.model.selected = index
                self.error = self.field_error = ''
                self.refresh()
                return
        self.model.selected = None
        self.error = self.field_error = ''
        self.refresh()

    def move(self, event):
        if self.dragging is None:
            return
        transform = self.transform()
        point = transform.to_normalized((event.x, event.y), clamp=True)
        try:
            if self.dragging[0] == 'region':
                _, region_index, vertex_index = self.dragging
                old = self.model.regions[region_index][0][vertex_index]
                point = self.model.snap_point(point, transform, exclude=old)
                self.model.move_vertex(region_index, vertex_index, point, record=False)
            else:
                index = self.dragging[1]
                point = self.model.snap_point(point, transform)
                self.model.move_draft_vertex(index, point, record=False)
            self.error = ''
        except ValueError as exc:
            self.error = str(exc)
        self.error_text.set(self.error)
        self.redraw()

    def release(self, event=None):
        if self.dragging is not None:
            self.model.commit()
            self.dragging = None
            self.refresh()

    def wheel(self, event):
        transform = self.transform()
        point = transform.to_normalized((event.x, event.y))
        self.zoom = max(.5, min(5., self.zoom * (1.15 if event.delta > 0 else 1 / 1.15)))
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
        self.commit_angles()
        if self.field_error:
            return
        try:
            result = self.model.validate()
            if self.callback is not None:
                self.callback(result)
            self.window.result = result
        except ValueError as exc:
            self.error = str(exc)
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


def open_diamond_cut_editor(parent, image_rgba, options, on_apply):
    """Return a modal Toplevel; only Apply calls ``on_apply(regions_tuple)``."""
    editor = _DiamondCutEditor(parent, image_rgba, options, on_apply)
    editor.window.diamond_cut_editor = editor
    return editor.window
