"""Image guides for a symmetric diamond profile; local edits commit only on Apply."""
from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageDraw, ImageTk
from spine_turn_ui_style import PALETTE, StudioButton

from spine_turn_region_editor import CanvasTransform

GUIDE_DEFAULTS = {
    'diamond_center_x': 0., 'diamond_table_y': .35, 'diamond_waist_y': .10,
    'diamond_tip_y': -.48, 'diamond_table_width': .50, 'diamond_waist_width': .96,
}
GUIDE_LABELS = {
    'diamond_center_x': '中心位置（左 −／右 ＋）',
    'diamond_table_y': '頂台位置（上 ＋／下 −）',
    'diamond_waist_y': '腰線位置（上 ＋／下 −）',
    'diamond_tip_y': '底尖位置（上 ＋／下 −）',
    'diamond_table_width': '頂台寬度', 'diamond_waist_width': '腰部寬度',
}
BG, PANEL, TEXT, MUTED = (PALETTE[key] for key in ('BG', 'PANEL', 'TEXT', 'MUTED'))
TABLE, WAIST, TIP, ERROR = '#ffca70', '#71e2ed', '#db9cff', '#ff8585'


def guide_values(options):
    getter = options.get if isinstance(options, dict) else lambda name, default: getattr(options, name, default)
    result = {}
    for name, default in GUIDE_DEFAULTS.items():
        try:
            value = float(getter(name, default))
        except (TypeError, ValueError):
            raise ValueError(f'{GUIDE_LABELS[name]}請輸入有效數值。') from None
        if not math.isfinite(value):
            raise ValueError(f'{GUIDE_LABELS[name]}必須是有限數值。')
        result[name] = value
    return result


class DiamondGuideModel:
    def __init__(self, options, image_size, *, validator=None):
        self.image_size = tuple(image_size)
        self.validator = validator
        self.girdle_height = float(options.get('diamond_girdle_height', .015)
            if isinstance(options, dict) else getattr(options, 'diamond_girdle_height', .015))
        if not math.isfinite(self.girdle_height) or not 0 <= self.girdle_height <= .12:
            raise ValueError('鑽石腰帶高度需介於 0% 到 12%。')
        self.guides = self._validate(guide_values(options))
        self.initial = dict(self.guides)
        self._history = [self._state()]
        self._cursor = 0

    def _validate(self, values):
        validator = self.validator
        if validator is None:
            from spine_turn_core import validate_diamond_guides
            validator = validate_diamond_guides
        result = guide_values(validator(values, *self.image_size))
        if self.girdle_height / 2 >= min(result['diamond_table_y'] - result['diamond_waist_y'],
                                          result['diamond_waist_y'] - result['diamond_tip_y']):
            raise ValueError('頂台或底尖距離腰線太近，請拉開輪廓，或回主畫面降低腰帶高度。')
        return result

    def validate(self):
        return self._validate(dict(self.guides))

    def _state(self):
        return tuple(self.guides[name] for name in GUIDE_DEFAULTS)

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

    def set_values(self, values, *, record=True):
        self.guides = guide_values(values)
        if record:
            self.commit()

    def undo(self):
        self.commit()
        if self._cursor:
            self._cursor -= 1
            self.guides = dict(zip(GUIDE_DEFAULTS, self._history[self._cursor]))

    def redo(self):
        if self.can_redo:
            self._cursor += 1
            self.guides = dict(zip(GUIDE_DEFAULTS, self._history[self._cursor]))

    def reset(self):
        self.commit()
        self.guides = self._validate(dict(GUIDE_DEFAULTS))
        self.commit()

    def handle_points(self):
        g = self.guides
        center = g['diamond_center_x']
        table, waist, tip = (g[name] for name in ('diamond_table_y', 'diamond_waist_y', 'diamond_tip_y'))
        tw, ww = g['diamond_table_width'] / 2, g['diamond_waist_width'] / 2
        return {'center': (center, .485), 'table_y': (center, table), 'waist_y': (center, waist),
            'tip': (center, tip), 'table_left': (center - tw, table), 'table_right': (center + tw, table),
            'waist_left': (center - ww, waist), 'waist_right': (center + ww, waist)}

    def drag(self, handle, point, *, record=False):
        x, y = (float(value) for value in point)
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError('拖曳座標必須是有限數值。')
        g = dict(self.guides)
        ex, ey = max(1e-5, 1 / self.image_size[0]), max(1e-5, 1 / self.image_size[1])
        level_gap = self.girdle_height / 2 + ey
        clamp = lambda value, low, high: max(low, min(high, value))
        if handle == 'center':
            available = max(0, .5 - g['diamond_waist_width'] / 2)
            g['diamond_center_x'] = clamp(x, -available, available)
        elif handle == 'table_y':
            g['diamond_table_y'] = clamp(y, g['diamond_waist_y'] + level_gap, .5 - ey)
        elif handle == 'waist_y':
            g['diamond_waist_y'] = clamp(y, g['diamond_tip_y'] + level_gap, g['diamond_table_y'] - level_gap)
        elif handle == 'tip':
            g['diamond_tip_y'] = clamp(y, -.5 + ey, g['diamond_waist_y'] - level_gap)
        elif handle in ('table_left', 'table_right'):
            g['diamond_table_width'] = clamp(2 * abs(x - g['diamond_center_x']), ex, g['diamond_waist_width'] - ex)
        elif handle in ('waist_left', 'waist_right'):
            available = 2 * max(0, .5 - abs(g['diamond_center_x']))
            g['diamond_waist_width'] = clamp(2 * abs(x - g['diamond_center_x']), g['diamond_table_width'] + ex, available)
        else:
            raise ValueError('找不到要調整的輪廓線。')
        self.guides = g
        if record:
            self.commit()


class _DiamondEditor:
    def __init__(self, parent, image, options, callback):
        self.image = image.convert('RGBA').copy()
        self.model = DiamondGuideModel(options, self.image.size)
        self.callback = callback
        self.dragging = None
        self.photo = None
        self._syncing = False
        self._fields_dirty = False
        self._field_error = ''
        self.window = tk.Toplevel(parent)
        self.window.title('調整鑽石輪廓 · Spine Turn Studio')
        self.window.configure(bg=BG)
        parent.update_idletasks()
        x = max(0, parent.winfo_rootx() + (parent.winfo_width() - 900) // 2)
        y = max(0, parent.winfo_rooty() + (parent.winfo_height() - 730) // 2)
        self.window.geometry(f'900x730+{x}+{y}')
        self.window.minsize(760, 620)
        self.window.transient(parent)
        self.window.result = None
        self.window.protocol('WM_DELETE_WINDOW', self.cancel)
        self.error_text = tk.StringVar(self.window)
        self.status = tk.StringVar(self.window, value='拖曳頂台、腰線、寬度或底尖，對齊圖片。')
        self.fields = {name: tk.StringVar(self.window) for name in GUIDE_DEFAULTS}
        self._build()
        self._sync_fields()
        self.window.bind('<Control-z>', lambda event: self.action(self.model.undo))
        self.window.bind('<Control-y>', lambda event: self.action(self.model.redo))
        self.window.bind('<Return>', lambda event: self.apply())
        self.window.bind('<Escape>', lambda event: self.cancel())
        self.window.after_idle(self.redraw)
        self.window.grab_set()

    def label(self, parent, text=None, **kwargs):
        settings = dict(text=text, bg=parent.cget('bg'), fg=TEXT, font=('Microsoft JhengHei UI', 10))
        settings.update(kwargs)
        return tk.Label(parent, **settings)

    def button(self, parent, text, command, primary=False):
        return StudioButton(parent, text=text, command=command, primary=primary,
            padx=15, pady=9, font=('Microsoft JhengHei UI', 10))

    def _build(self):
        header = tk.Frame(self.window, bg=BG, padx=18, pady=12)
        header.pack(fill='x')
        self.label(header, '調整鑽石輪廓', font=('Microsoft JhengHei UI', 16, 'bold')).pack(anchor='w')
        self.label(header, '沿著圖片設定頂台、腰部與底尖。左右對稱，立體切面由模型產生。', fg=MUTED).pack(anchor='w', pady=(4, 0))
        toolbar = tk.Frame(self.window, bg=BG, padx=18)
        toolbar.pack(fill='x', pady=(0, 8))
        self.undo_button = self.button(toolbar, '復原', lambda: self.action(self.model.undo))
        self.undo_button.pack(side='left', padx=(0, 7))
        self.redo_button = self.button(toolbar, '重做', lambda: self.action(self.model.redo))
        self.redo_button.pack(side='left', padx=(0, 7))
        self.button(toolbar, '恢復預設', lambda: self.action(self.model.reset)).pack(side='left')
        body = tk.Frame(self.window, bg=BG, padx=18)
        body.pack(fill='both', expand=True)
        side = tk.Frame(body, bg=PANEL, padx=12, pady=12, width=220)
        side.pack(side='right', fill='y', padx=(12, 0))
        side.pack_propagate(False)
        self.label(side, '輪廓比例（%）', fg=TABLE).pack(anchor='w', pady=(0, 8))
        for name in GUIDE_DEFAULTS:
            self.label(side, GUIDE_LABELS[name], font=('Microsoft JhengHei UI', 9), wraplength=190).pack(anchor='w', pady=(6, 2))
            control = ttk.Spinbox(side, from_=-50 if name.endswith(('_x', '_y')) else 1,
                to=50 if name.endswith(('_x', '_y')) else 100, increment=1,
                textvariable=self.fields[name], width=11, command=self.commit_fields)
            control.pack(fill='x')
            control.bind('<FocusOut>', lambda event: self.commit_fields())
            self.fields[name].trace_add('write', lambda *_: self.fields_changed())
        self.label(side, '位置以圖片中心為 0。\n寬度是整張圖片寬度的比例。\n先縮小腰寬，可移動更多中心位置。',
            fg=MUTED, justify='left', wraplength=190, font=('Microsoft JhengHei UI', 9)).pack(anchor='w', pady=(12, 0))
        self.canvas = tk.Canvas(body, bg='#151e2c', highlightthickness=1, highlightbackground='#334155', cursor='crosshair')
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda event: self.redraw())
        self.canvas.bind('<Button-1>', self.press)
        self.canvas.bind('<B1-Motion>', self.move)
        self.canvas.bind('<ButtonRelease-1>', self.release)
        footer = tk.Frame(self.window, bg=BG, padx=18, pady=10)
        footer.pack(fill='x')
        self.label(footer, textvariable=self.status, fg=MUTED, anchor='w', wraplength=850).pack(fill='x')
        self.label(footer, textvariable=self.error_text, fg=ERROR, anchor='w', wraplength=850, height=2).pack(fill='x', pady=(3, 3))
        buttons = tk.Frame(footer, bg=BG)
        buttons.pack(fill='x')
        self.label(buttons, '頂台在腰線上方，底尖在下方；頂台比腰部窄。', fg=MUTED, font=('Microsoft JhengHei UI', 9)).pack(side='left')
        self.button(buttons, '取消', self.cancel).pack(side='right', padx=(8, 0))
        self.apply_button = self.button(buttons, '套用鑽石輪廓', self.apply, True)
        self.apply_button.pack(side='right')

    def _sync_fields(self):
        self._syncing = True
        try:
            for name, value in self.model.guides.items():
                self.fields[name].set(f'{value * 100:g}')
        finally:
            self._syncing = False
        self._fields_dirty = False
        self._field_error = ''

    def fields_changed(self):
        if self._syncing:
            return
        self._fields_dirty = True
        try:
            values = {name: float(variable.get()) / 100 for name, variable in self.fields.items()}
        except (TypeError, ValueError):
            self._field_error = '輪廓比例請輸入有效的數值。'
            self.redraw()
            return
        try:
            # Keep the last valid overlay while the user edits several related
            # numeric fields, rather than sending huge/invalid coordinates to Tk.
            self.model._validate(values)
            self.model.set_values(values, record=False)
            self._field_error = ''
        except ValueError as error:
            self._field_error = str(error)
        self.redraw()

    def commit_fields(self):
        if self._fields_dirty:
            self.model.commit()
        self.update_status()

    def action(self, callback):
        try:
            callback()
            self._sync_fields()
        except ValueError as error:
            self._field_error = str(error)
        self.redraw()
        return 'break'

    def transform(self):
        return CanvasTransform(*self.image.size, max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height()))

    def redraw(self):
        if not self.window.winfo_exists():
            return
        transform = self.transform()
        width, height = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        view = Image.new('RGBA', (width, height), '#151e2c')
        draw = ImageDraw.Draw(view)
        left, top = transform.to_canvas((-.5, .5))
        target = max(1, round(self.image.width * transform.scale)), max(1, round(self.image.height * transform.scale))
        for y in range(max(0, math.floor(top / 16) * 16), min(height, math.ceil((top + target[1]) / 16) * 16), 16):
            for x in range(max(0, math.floor(left / 16) * 16), min(width, math.ceil((left + target[0]) / 16) * 16), 16):
                draw.rectangle((max(left, x), max(top, y), min(left + target[0], x + 15), min(top + target[1], y + 15)),
                    fill='#303b4c' if (x // 16 + y // 16) % 2 else '#253042')
        view.alpha_composite(self.image.resize(target, Image.Resampling.LANCZOS), (round(left), round(top)))
        self.photo = ImageTk.PhotoImage(view, master=self.window)
        self.canvas.delete('all')
        self.canvas.create_image(0, 0, image=self.photo, anchor='nw')
        positions = {name: transform.to_canvas(point) for name, point in self.model.handle_points().items()}
        center = self.model.guides['diamond_center_x']
        self.canvas.create_line(*transform.to_canvas((center, .5)), *transform.to_canvas((center, -.5)),
            fill='#b0bfd5', width=1, dash=(6, 4))
        self.canvas.create_line(*positions['table_left'], *positions['waist_left'], *positions['tip'],
            *positions['waist_right'], *positions['table_right'], fill='#eef3ff', width=1)
        for level, color, title in [('table', TABLE, '頂台'), ('waist', WAIST, '腰線')]:
            a, b = positions[level + '_left'], positions[level + '_right']
            self.canvas.create_line(*a, *b, fill=color, width=2)
            self.canvas.create_text(a[0] - 7, a[1] - 9, text=title, fill=color, anchor='se', font=('Microsoft JhengHei UI', 10, 'bold'))
        for name, (x, y) in positions.items():
            color = TABLE if name.startswith('table') else WAIST if name.startswith('waist') else TIP if name == 'tip' else '#b0bfd5'
            radius = 7 if name == self.dragging else 5
            self.canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill=color, outline=BG, width=2)
        x, y = positions['tip']
        self.canvas.create_text(x + 10, y - 3, text='底尖', fill=TIP, anchor='sw', font=('Microsoft JhengHei UI', 10, 'bold'))
        x, y = positions['center']
        self.canvas.create_text(x + 10, y + 1, text='中心', fill='#c2cfe1', anchor='nw', font=('Microsoft JhengHei UI', 9))
        self.update_status()

    def update_status(self):
        if not hasattr(self, 'apply_button'):
            return
        error = self._field_error
        if not error:
            try:
                self.model.validate()
            except ValueError as exception:
                error = str(exception)
        self.error_text.set(error)
        self.apply_button.configure(state='disabled' if error else 'normal')
        self.undo_button.configure(state='normal' if self.model.can_undo else 'disabled')
        self.redo_button.configure(state='normal' if self.model.can_redo else 'disabled')

    def press(self, event):
        self.canvas.focus_set()
        transform = self.transform()
        distance, handle = min((math.dist((event.x, event.y), transform.to_canvas(point)), name)
            for name, point in self.model.handle_points().items())
        self.dragging = handle if distance <= 12 else None
        if self.dragging:
            self.commit_fields()
            self._sync_fields()
            descriptions = {'center': '拖曳中心線；腰寬會限制可移動範圍。', 'table_y': '上下移動頂台。',
                'waist_y': '上下移動腰線。', 'tip': '上下移動底尖；底尖會保持在中心線上。'}
            self.status.set(descriptions.get(handle, '左右拖曳調整寬度；另一側會對稱移動。'))
        self.redraw()

    def move(self, event):
        if self.dragging:
            self.model.drag(self.dragging, self.transform().to_normalized((event.x, event.y)))
            self._sync_fields()
            self.redraw()

    def release(self, event=None):
        if self.dragging:
            self.model.commit()
        self.dragging = None
        self.status.set('拖曳頂台、腰線、寬度或底尖，對齊圖片。')
        self.redraw()

    def apply(self):
        self.commit_fields()
        try:
            if self._field_error:
                raise ValueError(self._field_error)
            guides = self.model.validate()
            if self.callback is not None:
                self.callback(dict(guides))
            self.window.result = dict(guides)
        except (ValueError, RuntimeError) as error:
            self._field_error = str(error)
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


def open_diamond_editor(parent, image_rgba, options, on_apply):
    """Open modal six-guide editor; Apply calls ``on_apply(guide_dict)`` only.

    Positions are centered world-up image fractions; widths are full-image
    fractions. Returned Toplevel.result is None on Cancel or the applied dict.
    """
    editor = _DiamondEditor(parent, image_rgba, options, on_apply)
    editor.window.diamond_editor = editor
    return editor.window
