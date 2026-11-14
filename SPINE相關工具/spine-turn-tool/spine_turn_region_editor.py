"""Modal convex raised-region drawing, with a testable coordinate/history model."""
from __future__ import annotations

from dataclasses import dataclass
import math
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk

BG, PANEL, TEXT, MUTED = '#101722', '#1c2738', '#edf3fc', '#9cacc2'
AMBER, CYAN, ERROR = '#ffc05a', '#69d8e8', '#ff8585'


@dataclass(frozen=True)
class CanvasTransform:
    image_width: float
    image_height: float
    canvas_width: float
    canvas_height: float
    padding: float = 28
    zoom: float = 1
    pan_x: float = 0
    pan_y: float = 0

    def __post_init__(self):
        values = (self.image_width, self.image_height, self.canvas_width, self.canvas_height,
                  self.padding, self.zoom, self.pan_x, self.pan_y)
        if not all(math.isfinite(float(value)) for value in values) or min(values[:4]) <= 0 or self.zoom <= 0:
            raise ValueError('圖片與畫布尺寸必須是正的有限數值。')

    @property
    def scale(self):
        return min(max(1, self.canvas_width - 2 * self.padding) / self.image_width,
                   max(1, self.canvas_height - 2 * self.padding) / self.image_height) * self.zoom

    @property
    def origin(self):
        return self.canvas_width / 2 + self.pan_x, self.canvas_height / 2 + self.pan_y

    def to_canvas(self, point):
        x, y = self.origin
        return x + point[0] * self.image_width * self.scale, y - point[1] * self.image_height * self.scale

    def to_normalized(self, point, *, clamp=False):
        x, y = self.origin
        result = ((point[0] - x) / (self.image_width * self.scale),
                  (y - point[1]) / (self.image_height * self.scale))
        return tuple(max(-.5, min(.5, value)) for value in result) if clamp else result


def validate_height_percent(value):
    try:
        height = float(value)
    except (TypeError, ValueError):
        raise ValueError('凸起高度請輸入 0 到 45 的數值。') from None
    if not math.isfinite(height) or not 0 <= height <= 45:
        raise ValueError('凸起高度需介於 0% 到 45%。')
    return height


def _points(values):
    try:
        result = tuple(tuple(float(value) for value in point) for point in values)
    except (TypeError, ValueError):
        raise ValueError('頂點座標必須是有效數值。') from None
    if len(result) > 32 or any(len(point) != 2 or not all(math.isfinite(value) and abs(value) <= .500001
            for value in point) for point in result):
        raise ValueError('請在圖片內設定最多 32 個頂點。')
    return result


class RaisedRegionModel:
    """Local edit state only: the caller receives data exclusively on Apply."""

    def __init__(self, outer_points, initial_points, image_size, *, auto_points=None, validator=None):
        self.outer = _points(outer_points)
        self.image_size = tuple(image_size)
        self.validator = validator
        self.initial = _points(initial_points)
        self.auto = _points(auto_points) if auto_points is not None else self.initial
        self.points = self.initial
        self.closed = len(self.points) >= 3
        self.selected_vertex = self.selected_edge = None
        self._history = [(self.points, self.closed)]
        self._cursor = 0
        self._drag_start = None

    @property
    def can_undo(self):
        return self._cursor > 0

    @property
    def can_redo(self):
        return self._cursor + 1 < len(self._history)

    def _record(self):
        state = (self.points, self.closed)
        if state != self._history[self._cursor]:
            self._history = self._history[:self._cursor + 1] + [state]
            self._cursor += 1

    def _replace(self, points, closed, *, record=True):
        self.points, self.closed = _points(points), bool(closed)
        if record:
            self._record()

    def validate(self):
        if len(self.points) < 3:
            raise ValueError('至少需要 3 個頂點，才能完成凸起範圍。')
        validator = self.validator
        if validator is None:
            from spine_turn_core import validate_raised_region
            validator = validate_raised_region
        return tuple(tuple(point) for point in validator(self.outer, self.points, *self.image_size))

    def add_point(self, point):
        if self.closed:
            raise ValueError('請先按「清除重畫」，或選取一條邊後加入頂點。')
        if len(self.points) >= 32:
            raise ValueError('最多可設定 32 個頂點。')
        point = _points([point])[0]
        if any(math.dist(point, other) < 1e-8 for other in self.points):
            raise ValueError('頂點不可重疊。')
        self._replace(self.points + (point,), False)

    def close(self):
        valid = self.validate()
        self._replace(valid, True)
        self.selected_vertex = self.selected_edge = None
        return valid

    def clear(self):
        self._replace((), False)
        self.selected_vertex = self.selected_edge = None

    def reset_auto(self):
        self._replace(self.auto, len(self.auto) >= 3)
        self.selected_vertex = self.selected_edge = None

    def insert_on_edge(self, index):
        if not self.closed or len(self.points) >= 32:
            raise ValueError('請選取封閉輪廓的邊；最多可設定 32 個頂點。')
        index %= len(self.points)
        a, b = self.points[index], self.points[(index + 1) % len(self.points)]
        midpoint = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        self._replace(self.points[:index + 1] + (midpoint,) + self.points[index + 1:], True)
        self.selected_vertex, self.selected_edge = index + 1, None

    def delete_point(self, index):
        if self.closed and len(self.points) <= 3:
            raise ValueError('封閉範圍至少需要 3 個頂點；需要重畫時請按「清除重畫」。')
        if not 0 <= index < len(self.points):
            raise ValueError('請先選取要刪除的頂點。')
        self._replace(self.points[:index] + self.points[index + 1:], self.closed)
        self.selected_vertex = self.selected_edge = None

    def begin_drag(self, index):
        if not 0 <= index < len(self.points):
            raise ValueError('找不到要移動的頂點。')
        self._drag_start = (self.points, self.closed)
        self.selected_vertex, self.selected_edge = index, None

    def move_point(self, index, point, *, record=True):
        point = _points([point])[0]
        values = list(self.points)
        values[index] = point
        self._replace(values, self.closed, record=record)

    def end_drag(self):
        if self._drag_start is not None:
            self._record()
            self._drag_start = None

    def undo(self):
        self.end_drag()
        if self.can_undo:
            self._cursor -= 1
            self.points, self.closed = self._history[self._cursor]
        self.selected_vertex = self.selected_edge = None

    def redo(self):
        if self.can_redo:
            self._cursor += 1
            self.points, self.closed = self._history[self._cursor]
        self.selected_vertex = self.selected_edge = None


def _segment_distance(point, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    fraction = 0 if length == 0 else max(0, min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length))
    return math.dist(point, (a[0] + fraction * dx, a[1] + fraction * dy))


class _RegionEditor:
    def __init__(self, parent, image, outer, initial, height, callback, auto_points,
                 height_enabled=True, height_note=None):
        self.image = image.convert('RGBA').copy()
        self.model = RaisedRegionModel(outer, initial, image.size, auto_points=auto_points)
        self.callback = callback
        self.height_enabled = bool(height_enabled)
        self.height_note = height_note or ''
        self.original_height = validate_height_percent(height)
        self.zoom, self.pan_x, self.pan_y = 1., 0., 0.
        self.drag_vertex = None
        self.pan_start = None
        self.space_down = False
        self.photo = None
        self.error = ''
        self.window = tk.Toplevel(parent)
        self.window.title('繪製凸起範圍 · Spine Turn Studio')
        self.window.configure(bg=BG)
        parent.update_idletasks()
        x = max(0, parent.winfo_rootx() + (parent.winfo_width() - 850) // 2)
        y = max(0, parent.winfo_rooty() + (parent.winfo_height() - 720) // 2)
        self.window.geometry(f'850x720+{x}+{y}')
        self.window.minsize(720, 600)
        self.window.transient(parent)
        self.window.result = None
        self.window.protocol('WM_DELETE_WINDOW', self.cancel)
        self.height = tk.StringVar(self.window, value=f'{self.original_height:g}')
        self.status = tk.StringVar(self.window)
        self.error_text = tk.StringVar(self.window)
        self.zoom_text = tk.StringVar(self.window, value='100%')
        self._build()
        self.window.bind('<Control-z>', lambda event: self._action(self.model.undo))
        self.window.bind('<Control-y>', lambda event: self._action(self.model.redo))
        self.window.bind('<Delete>', lambda event: self.delete_selected())
        self.window.bind('<Escape>', lambda event: self.cancel())
        self.window.bind('<Return>', lambda event: self._action(self.model.close) if not self.model.closed else self.apply())
        self.window.after_idle(self.redraw)
        self.window.grab_set()

    def label(self, parent, text=None, **kwargs):
        settings = dict(text=text, bg=parent.cget('bg'), fg=TEXT,
            font=('Microsoft JhengHei UI', 10))
        settings.update(kwargs)
        return tk.Label(parent, **settings)

    def button(self, parent, text, command, *, primary=False):
        return tk.Button(parent, text=text, command=command, bg=AMBER if primary else PANEL,
            fg=BG if primary else TEXT, activebackground='#b7c8e0', bd=0, padx=10, pady=8,
            cursor='hand2', font=('Microsoft JhengHei UI', 9), disabledforeground='#64748b')

    def _build(self):
        header = tk.Frame(self.window, bg=BG, padx=18, pady=12)
        header.pack(fill='x')
        self.label(header, '繪製凸起範圍', font=('Microsoft JhengHei UI', 16, 'bold')).pack(anchor='w')
        self.label(header, '依序畫出要抬高的區塊。第一版支援凸多邊形，最多 32 點。', fg=MUTED).pack(anchor='w', pady=(4, 0))
        toolbar = tk.Frame(self.window, bg=BG, padx=18)
        toolbar.pack(fill='x', pady=(0, 8))
        self.buttons = {}
        commands = [('clear', '清除重畫', self.model.clear), ('close', '完成輪廓', self.model.close),
            ('insert', '選取邊加點', self.insert_selected), ('delete', '刪除頂點', self._delete_selected),
            ('undo', '復原', self.model.undo), ('redo', '重做', self.model.redo),
            ('reset', '恢復自動', self.model.reset_auto)]
        for name, title, command in commands:
            button = self.button(toolbar, title, lambda action=command: self._action(action))
            button.pack(side='left', padx=(0, 6))
            self.buttons[name] = button
        area = tk.Frame(self.window, bg=BG, padx=18)
        area.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(area, bg='#151e2c', highlightthickness=1, highlightbackground='#334155', cursor='crosshair')
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda event: self.redraw())
        self.canvas.bind('<Button-1>', self.on_press)
        self.canvas.bind('<B1-Motion>', self.on_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_release)
        self.canvas.bind('<Button-3>', self.on_right_click)
        self.canvas.bind('<MouseWheel>', self.on_wheel)
        self.canvas.bind('<Button-2>', self.on_pan_press)
        self.canvas.bind('<B2-Motion>', self.on_drag)
        self.canvas.bind('<ButtonRelease-2>', self.on_release)
        self.canvas.bind('<KeyPress-space>', lambda event: self.set_space(True))
        self.canvas.bind('<KeyRelease-space>', lambda event: self.set_space(False))
        strip = tk.Frame(area, bg=BG)
        strip.pack(fill='x', pady=(6, 0))
        self.label(strip, textvariable=self.status, fg=MUTED, anchor='w').pack(side='left', fill='x', expand=True)
        self.button(strip, '−', lambda: self.set_zoom(self.zoom / 1.2)).pack(side='left')
        self.label(strip, textvariable=self.zoom_text, width=5, fg=MUTED).pack(side='left')
        self.button(strip, '＋', lambda: self.set_zoom(self.zoom * 1.2)).pack(side='left')
        self.button(strip, '適合畫面', self.fit).pack(side='left', padx=(6, 0))
        footer = tk.Frame(self.window, bg=BG, padx=18, pady=10)
        footer.pack(fill='x')
        self.label(footer, textvariable=self.error_text, fg=ERROR, justify='left', anchor='w',
            wraplength=790, height=2).pack(fill='x')
        row = tk.Frame(footer, bg=BG)
        row.pack(fill='x')
        self.label(row, '凸起高度（占厚度%）').pack(side='left')
        if self.height_enabled:
            self.height_control = ttk.Spinbox(row, from_=0, to=45, increment=1, width=6, textvariable=self.height)
        else:
            self.height_control = self.label(row, '50%（固定）', fg=CYAN)
        self.height_control.pack(side='left', padx=8)
        self.height.trace_add('write', lambda *_: self.update_status())
        self.button(row, '取消', self.cancel).pack(side='right', padx=(8, 0))
        self.apply_button = self.button(row, '套用凸起範圍', self.apply, primary=True)
        self.apply_button.pack(side='right')
        if self.height_note:
            self.label(footer, self.height_note, fg=CYAN, justify='left', wraplength=790).pack(anchor='w', pady=(7, 0))
        self.label(footer, '琥珀色範圍是平整凸起面，與青色外框之間會形成斜邊。\n拖曳頂點；點選邊後可加點；右鍵刪點；滾輪縮放，空白鍵拖曳平移。',
            fg=MUTED, justify='left', wraplength=790).pack(anchor='w', pady=(8, 0))

    def transform(self):
        return CanvasTransform(*self.image.size, max(1, self.canvas.winfo_width()),
            max(1, self.canvas.winfo_height()), zoom=self.zoom, pan_x=self.pan_x, pan_y=self.pan_y)

    def _action(self, callback):
        try:
            callback()
            self.error = ''
        except (ValueError, IndexError) as error:
            self.error = str(error)
        self.redraw()
        return 'break'

    def redraw(self):
        if not self.window.winfo_exists():
            return
        transform = self.transform()
        width, height = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        view = Image.new('RGBA', (width, height), '#151e2c')
        draw = ImageDraw.Draw(view)
        left, top = transform.to_canvas((-.5, .5))
        target = (max(1, round(self.image.width * transform.scale)), max(1, round(self.image.height * transform.scale)))
        right, bottom = left + target[0], top + target[1]
        for y in range(max(0, math.floor(top / 16) * 16), min(height, math.ceil(bottom / 16) * 16), 16):
            for x in range(max(0, math.floor(left / 16) * 16), min(width, math.ceil(right / 16) * 16), 16):
                draw.rectangle((max(left, x), max(top, y), min(right, x + 15), min(bottom, y + 15)),
                    fill='#303b4c' if (x // 16 + y // 16) % 2 else '#253042')
        resized = self.image.resize(target, Image.Resampling.LANCZOS)
        image_left, image_top = round(left), round(top)
        crop = (max(0, -image_left), max(0, -image_top),
            min(resized.width, width - image_left), min(resized.height, height - image_top))
        if crop[2] > crop[0] and crop[3] > crop[1]:
            view.alpha_composite(resized.crop(crop), (max(0, image_left), max(0, image_top)))
        self.photo = ImageTk.PhotoImage(view, master=self.window)
        self.canvas.delete('all')
        self.canvas.create_image(0, 0, image=self.photo, anchor='nw')
        outer = [coordinate for point in self.model.outer for coordinate in transform.to_canvas(point)]
        if len(outer) >= 6:
            self.canvas.create_polygon(outer, fill='', outline=CYAN, width=2, dash=(6, 4))
        points = [transform.to_canvas(point) for point in self.model.points]
        geometry_error = self.geometry_error()
        line_color = ERROR if geometry_error else AMBER
        if self.model.closed and len(points) >= 3:
            self.canvas.create_polygon([coordinate for point in points for coordinate in point],
                fill=AMBER, stipple='gray25', outline=line_color, width=2)
        elif len(points) >= 2:
            self.canvas.create_line([coordinate for point in points for coordinate in point], fill=line_color, width=2)
        if self.model.selected_edge is not None and self.model.closed:
            index = self.model.selected_edge
            self.canvas.create_line(*points[index], *points[(index + 1) % len(points)], fill='white', width=4)
        for index, (x, y) in enumerate(points):
            selected = index == self.model.selected_vertex
            self.canvas.create_oval(x - 6, y - 6, x + 6, y + 6, fill='white' if selected else AMBER,
                outline=BG, width=2)
            self.canvas.create_text(x + 11, y - 10, text=str(index + 1), fill='white',
                font=('Segoe UI', 9, 'bold'), anchor='sw')
        self.update_status()

    def geometry_error(self):
        if self.model.closed:
            try:
                self.model.validate()
            except ValueError as error:
                return str(error)
        return ''

    def update_status(self):
        if not hasattr(self, 'apply_button'):
            return
        height_error = ''
        if self.height_enabled:
            try:
                validate_height_percent(self.height.get())
            except ValueError as error:
                height_error = str(error)
        geometry_error = self.geometry_error()
        self.error_text.set(height_error or geometry_error or self.error)
        count = len(self.model.points)
        self.status.set(f'{"已封閉，拖曳頂點調整" if self.model.closed else "繪製中，依序點選頂點"}  ·  {count} / 32 點')
        self.zoom_text.set(f'{self.zoom * 100:.0f}%')
        self.apply_button.configure(state='normal' if self.model.closed and count >= 3 and not height_error and not geometry_error else 'disabled')
        self.buttons['close'].configure(state='normal' if not self.model.closed and count >= 3 else 'disabled')
        self.buttons['insert'].configure(state='normal' if self.model.closed and self.model.selected_edge is not None and count < 32 else 'disabled')
        self.buttons['delete'].configure(state='normal' if self.model.selected_vertex is not None else 'disabled')
        self.buttons['undo'].configure(state='normal' if self.model.can_undo else 'disabled')
        self.buttons['redo'].configure(state='normal' if self.model.can_redo else 'disabled')

    def hit_vertex(self, position):
        transform = self.transform()
        choices = [(math.dist(position, transform.to_canvas(point)), index) for index, point in enumerate(self.model.points)]
        distance, index = min(choices, default=(math.inf, None))
        return index if distance <= 11 else None

    def hit_edge(self, position):
        points = [self.transform().to_canvas(point) for point in self.model.points]
        choices = [(_segment_distance(position, a, b), index)
            for index, (a, b) in enumerate(zip(points, points[1:] + points[:1]))]
        distance, index = min(choices, default=(math.inf, None))
        return index if distance <= 10 else None

    def on_press(self, event):
        self.canvas.focus_set()
        if self.space_down:
            return self.on_pan_press(event)
        position = (event.x, event.y)
        vertex = self.hit_vertex(position)
        if not self.model.closed and vertex == 0 and len(self.model.points) >= 3:
            return self._action(self.model.close)
        if vertex is not None:
            self.model.begin_drag(vertex)
            self.drag_vertex = vertex
            self.error = ''
        elif self.model.closed:
            self.model.selected_vertex = None
            self.model.selected_edge = self.hit_edge(position)
            self.error = '' if self.model.selected_edge is not None else '要重新畫線，請按「清除重畫」。'
        else:
            point = self.transform().to_normalized(position)
            return self._action(lambda: self.model.add_point(point))
        self.redraw()

    def on_drag(self, event):
        if self.pan_start is not None:
            x, y, px, py = self.pan_start
            self.pan_x, self.pan_y = px + event.x - x, py + event.y - y
            self.redraw()
        elif self.drag_vertex is not None:
            point = self.transform().to_normalized((event.x, event.y), clamp=True)
            self.model.move_point(self.drag_vertex, point, record=False)
            self.redraw()

    def on_release(self, event=None):
        self.model.end_drag()
        self.drag_vertex, self.pan_start = None, None
        self.redraw()

    def on_right_click(self, event):
        vertex = self.hit_vertex((event.x, event.y))
        if vertex is not None:
            self.model.selected_vertex = vertex
            self.delete_selected()

    def insert_selected(self):
        if self.model.selected_edge is None:
            raise ValueError('請先點選要加入頂點的邊。')
        self.model.insert_on_edge(self.model.selected_edge)

    def delete_selected(self):
        return self._action(self._delete_selected)

    def _delete_selected(self):
        if self.model.selected_vertex is None:
            raise ValueError('請先選取要刪除的頂點。')
        self.model.delete_point(self.model.selected_vertex)

    def set_space(self, down):
        self.space_down = down
        self.canvas.configure(cursor='fleur' if down else 'crosshair')
        return 'break'

    def on_pan_press(self, event):
        self.pan_start = event.x, event.y, self.pan_x, self.pan_y

    def set_zoom(self, zoom, anchor=None):
        old = self.transform()
        self.zoom = max(.5, min(4., zoom))
        if anchor is not None:
            point = old.to_normalized(anchor)
            updated = self.transform()
            self.pan_x = anchor[0] - updated.canvas_width / 2 - point[0] * updated.image_width * updated.scale
            self.pan_y = anchor[1] - updated.canvas_height / 2 + point[1] * updated.image_height * updated.scale
        self.redraw()

    def on_wheel(self, event):
        self.set_zoom(self.zoom * (1.15 if event.delta > 0 else 1 / 1.15), (event.x, event.y))
        return 'break'

    def fit(self):
        self.zoom, self.pan_x, self.pan_y = 1., 0., 0.
        self.redraw()

    def apply(self):
        try:
            if not self.model.closed:
                raise ValueError('請先完成封閉輪廓。')
            points = self.model.validate()
            height = validate_height_percent(self.height.get()) if self.height_enabled else self.original_height
            if self.callback is not None:
                self.callback(points, height)
            self.window.result = points, height
        except (ValueError, RuntimeError) as error:
            self.error = str(error)
            self.redraw()
            return
        self._destroy()

    def _destroy(self):
        try:
            if self.window.grab_current() == self.window:
                self.window.grab_release()
        except tk.TclError:
            pass
        self.window.destroy()

    def cancel(self):
        self.window.result = None
        self._destroy()


def open_raised_region_editor(parent, image_rgba, outer_points, initial_points,
                              height_percent=25, on_apply=None, *, auto_points=None,
                              height_enabled=True, height_note=None):
    """Open a modal local editor; only Apply calls ``on_apply(points, percent)``.

    Points are normalized centered world-up tuples. The returned Toplevel has
    ``result=None`` on Cancel, or ``(points,height_percent)`` after Apply.
    ``auto_points`` supplies the independent automatic boundary for Reset.
    A disabled height field preserves the supplied stored height on Apply;
    ``height_note`` can explain a mode with an independently fixed physical height.
    """
    editor = _RegionEditor(parent, image_rgba, outer_points, initial_points,
        height_percent, on_apply, auto_points, height_enabled, height_note)
    editor.window.region_editor = editor
    return editor.window
