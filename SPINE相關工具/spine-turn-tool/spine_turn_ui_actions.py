"""Asset and preview actions shared by the studio's workspace layouts."""
from __future__ import annotations

import copy
import math
from pathlib import Path
import time

from PIL import Image


_ANGLE_RANGES = {
    '整圈旋轉': (0., 360.), 'rotate_loop': (0., 360.),
    '正面 → 背面': (0., 180.), 'flip_to_back': (0., 180.),
    '背面 → 正面': (180., 360.), 'flip_to_front': (180., 360.),
}
_ASSET_LABELS = {'front': '正面', 'back': '背面', 'edge': '側邊'}
_MISSING = object()


def _status(app, text):
    variable = getattr(app, 'status', None)
    if callable(getattr(variable, 'set', None)):
        variable.set(text)


def _value(variable, default=None):
    return variable.get() if callable(getattr(variable, 'get', None)) else default


def _focus(app):
    method = getattr(getattr(app, 'root', None), 'focus_get', None)
    try:
        return method() if callable(method) else None
    except Exception:
        return None


def _shortcut_modifier_mask(root):
    # Tk on Windows uses Mod1 (0x8) for NumLock, rather than Alt.
    mask = 0x4 | 0x80 | 0x20000
    try:
        windows = root.tk.call('tk', 'windowingsystem') == 'win32'
    except Exception:
        windows = False
    return mask if windows else mask | 0x8


def _verify_artwork(path):
    if not path or not Path(path).is_file():
        raise ValueError('請先放入有效的正面與背面圖片。')
    with Image.open(path) as image:
        if image.width * image.height > 40_000_000:
            raise ValueError('圖片超過 4,000 萬像素，請先縮小。')
        image.verify()
    with Image.open(path) as image:
        decoded = image.convert('RGBA')
        decoded.load()
        if decoded.getchannel('A').getbbox() is None:
            raise ValueError('圖片完全透明，無法作為旋轉素材。')


def _asset_snapshot(app):
    snapshot = {
        'paths_object': app.paths, 'paths': dict(app.paths),
        'attributes': {}, 'variables': {}, 'cards': {},
    }
    for name in ('extra_options', 'options', 'prepared', 'raised_contour_points',
                 'diamond_guides', '_preview_revision', '_preview_view_key'):
        value = getattr(app, name, _MISSING)
        if name in ('raised_contour_points', 'diamond_guides') and value is not _MISSING:
            value = copy.deepcopy(value)
        snapshot['attributes'][name] = value
    thumbs = getattr(app, 'thumbs', None)
    if isinstance(thumbs, dict):
        snapshot['thumbs_object'], snapshot['thumbs'] = thumbs, dict(thumbs)
    for name in ('region_summary', 'diamond_summary'):
        variable = getattr(app, name, None)
        if callable(getattr(variable, 'get', None)) and callable(getattr(variable, 'set', None)):
            snapshot['variables'][name] = variable.get()
    for kind in ('front', 'back'):
        pair = getattr(app, 'cards', {}).get(kind)
        if not pair:
            continue
        for widget, keys in ((pair[0], ('image', 'text', 'height')), (pair[1], ('text',))):
            try:
                snapshot['cards'][widget] = {key: widget.cget(key) for key in keys}
            except Exception:
                pass
    return snapshot


def _restore_assets(app, snapshot):
    app.paths = snapshot['paths_object']
    app.paths.clear()
    app.paths.update(snapshot['paths'])
    for name, value in snapshot['attributes'].items():
        if value is _MISSING:
            if hasattr(app, name):
                delattr(app, name)
        else:
            setattr(app, name, value)
    if 'thumbs' in snapshot:
        app.thumbs = snapshot['thumbs_object']
        app.thumbs.clear()
        app.thumbs.update(snapshot['thumbs'])
    for name, value in snapshot['variables'].items():
        getattr(app, name).set(value)
    for widget, values in snapshot['cards'].items():
        try:
            widget.configure(**values)
        except Exception:
            pass


class StudioActions:
    """Mixin; state, artwork widgets and rendering are owned by ``App``."""

    def remove_asset(self, kind):
        if getattr(self, 'busy', False):
            return False
        if kind not in _ASSET_LABELS:
            _status(self, '無法移除未知的素材欄位。')
            return False
        self.clear_image(kind)
        self.rebuild()
        _status(self, f'已移除{_ASSET_LABELS[kind]}圖片。')
        return True

    def swap_faces(self):
        if getattr(self, 'busy', False):
            return False
        front, back = self.paths.get('front'), self.paths.get('back')
        try:
            _verify_artwork(front)
            _verify_artwork(back)
        except Exception as error:
            _status(self, f'無法交換正反面：{error}')
            return False
        snapshot = _asset_snapshot(self)
        try:
            if not self.set_image('front', back) or not self.set_image('back', front):
                raise ValueError('圖片載入失敗，已保留原本的素材與設定。')
            self.rebuild()
            _status(self, '已交換正面與背面圖片。')
        except Exception as error:
            _restore_assets(self, snapshot)
            _status(self, f'無法交換正反面：{error}')
            return False
        return True

    def begin_angle_edit(self, event=None):
        if getattr(self, 'busy', False):
            return False
        self.playing = False
        self.last_tick = time.perf_counter()
        button = getattr(self, 'play_button', None)
        if callable(getattr(button, 'configure', None)):
            button.configure(text='播放')

    def seek_progress(self, progress):
        if getattr(self, 'busy', False):
            return False
        try:
            value = float(progress)
            if not math.isfinite(value):
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            _status(self, '播放位置需為有效數值。')
            return False
        self.begin_angle_edit()
        self.progress = min(1., max(0., value))
        self.angle = self.angle_at_progress()
        self._preview_revision = getattr(self, '_preview_revision', 0) + 1
        slider = getattr(self, 'slider', None)
        if callable(getattr(slider, 'set', None)):
            slider.set(self.progress * 360)
        self.sync_transport()
        self.draw()
        return True

    def step_preview(self, delta):
        if getattr(self, 'busy', False):
            return False
        try:
            fps = float(getattr(getattr(self, 'options', None), 'fps', 30))
            duration, frames = float(self.clip_duration()), float(delta)
            if not all(math.isfinite(value) for value in (fps, duration, frames)) or fps <= 0 or duration <= 0:
                raise ValueError
            progress = float(self.progress) + frames / (fps * duration)
        except (TypeError, ValueError, AttributeError, OverflowError):
            _status(self, '請先設定有效的動畫長度與影格率。')
            return False
        return self.seek_progress(progress)

    def apply_angle(self):
        if getattr(self, 'busy', False):
            return False
        selected = _value(getattr(self, 'animation', None))
        bounds = _ANGLE_RANGES.get(selected)
        if bounds is None:
            _status(self, '請先選擇有效的旋轉動畫。')
            return False
        start, end = bounds
        try:
            angle = float(_value(getattr(self, 'angle_input', None)))
            if not math.isfinite(angle) or not start <= angle <= end:
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            _status(self, f'目前動畫的角度需介於 {start:g}° 與 {end:g}°。')
            return False
        return self.seek_progress((angle - start) / (end - start))

    def sync_transport(self):
        readout, angle_input = getattr(self, 'time_readout', None), getattr(self, 'angle_input', None)
        if readout is None and angle_input is None:
            return
        try:
            duration = float(self.clip_duration())
            progress = min(1., max(0., float(getattr(self, 'progress', 0))))
            if not math.isfinite(duration) or duration < 0:
                return
        except (AttributeError, TypeError, ValueError, OverflowError):
            return
        if callable(getattr(readout, 'set', None)):
            text = f'{progress * duration:.2f} / {duration:.2f} 秒'
            if _value(readout) != text:
                readout.set(text)
        entry = getattr(self, 'angle_entry', None)
        if entry is not None and _focus(self) is entry:
            return
        if callable(getattr(angle_input, 'set', None)):
            try:
                angle = float(self.angle_at_progress())
                if math.isfinite(angle):
                    text = f'{0. if abs(angle) < 1e-10 else angle:.1f}'
                    if _value(angle_input) != text:
                        angle_input.set(text)
            except (AttributeError, TypeError, ValueError, OverflowError):
                pass

    def handle_preview_key(self, event):
        root = getattr(self, 'root', None)
        if root is None or getattr(self, '_closed', False):
            return None
        key = getattr(event, 'keysym', '')
        try:
            grab = root.grab_current() if callable(getattr(root, 'grab_current', None)) else None
            if grab is not None:
                return None
            focus = _focus(self)
            origin = getattr(event, 'widget', None) or focus or root
            for widget in (origin, focus):
                if widget is None:
                    continue
                top = widget.winfo_toplevel() if callable(getattr(widget, 'winfo_toplevel', None)) else widget
                if top is not root:
                    return None
                kind = str(widget.winfo_class()).lower() if callable(getattr(widget, 'winfo_class', None)) else ''
                if key != 'F8' and (kind in {'entry', 'tentry', 'spinbox', 'tspinbox', 'combobox', 'tcombobox',
                             'text', 'listbox', 'treeview', 'ttreeview', 'tnotebook'}
                        or kind.endswith(('button', 'scale'))):
                    return None
            if int(getattr(event, 'state', 0)) & _shortcut_modifier_mask(root):
                return None
        except Exception:
            return None
        if key in ('space', ' '):
            self.toggle_play()
        elif key == 'Left':
            self.step_preview(-1)
        elif key == 'Right':
            self.step_preview(1)
        elif key == 'Home':
            self.seek_progress(0)
        elif key == 'End':
            self.seek_progress(1)
        elif key == 'F8':
            toggle = getattr(getattr(self, '_workspace', None), 'toggle_focus', None)
            if not callable(toggle):
                return None
            toggle()
        else:
            return None
        return 'break'
