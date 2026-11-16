"""Transparent PNG sequences from the same editable geometry as the Spine export.

Frames are streamed to disk with a single camera fitted to their union bounds.
Rendering uses the shared Pillow CPU renderer, not the native Spine/GPU renderer.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
import math
from pathlib import Path
from typing import Any

import spine_turn_core as core
from spine_turn_preview import render_pose


ANIMATION_ARCS = {
    'rotate_loop': (0., 360., True),
    'flip_to_back': (0., 180., False),
    'flip_to_front': (180., 360., False),
}


def _finite_number(value, label):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{label}必須是有效數值。') from None
    if not math.isfinite(result):
        raise ValueError(f'{label}必須是有限數值。')
    return result


def _cancelled(event):
    return event is not None and event.is_set()


def _frame_plan(options, animation_name, fps):
    if animation_name not in ANIMATION_ARCS:
        raise ValueError('找不到指定的動畫。')
    requested = _finite_number(fps, '每秒張數')
    if not 1 <= requested <= 120:
        raise ValueError('每秒張數需介於 1 到 120。')
    duration = _finite_number(options.duration, '動畫時間')
    if duration <= 0:
        raise ValueError('動畫時間必須大於 0。')
    loop = ANIMATION_ARCS[animation_name][2]
    duration = duration if loop else duration / 2
    intervals = max(1, round(duration * requested))
    count = intervals if loop else intervals + 1
    denominator = intervals
    return {
        'duration': duration, 'loop': loop, 'requested_fps': requested,
        'effective_fps': intervals / duration, 'frame_count': count,
        'progresses': (index / denominator for index in range(count)),
        'intervals': intervals,
    }


def _union_progresses(plan, options, animation_name):
    samples = {index / plan['intervals'] for index in range(plan['frame_count'])}
    samples.update((0., 1.))
    for name in ('MOTION_KEY_PROGRESS', 'MOTION_Z_KEY_PROGRESS'):
        samples.update(getattr(core, name, ()))
    samples.update(core.motion_key_progress(options))
    samples.update(core.z_spin_key_progress(options))
    start, end, _ = ANIMATION_ARCS[animation_name]
    step = _finite_number(options.key_step_degrees, '旋轉關鍵格間隔')
    if step <= 0:
        raise ValueError('旋轉關鍵格間隔必須大於 0。')
    keys = max(1, math.ceil((end - start) / step))
    samples.update(index / keys for index in range(keys + 1))
    samples.update((angle - start) / (end - start)
        for angle in (0., 90., 180., 270., 360.) if start <= angle <= end)
    return sorted(samples)


def _fit_camera(prepared, options, size, padding, plan, animation_name, cancel_event):
    min_x = min_y = math.inf
    max_x = max_y = -math.inf
    for progress in _union_progresses(plan, options, animation_name):
        if _cancelled(cancel_event):
            return None, None
        movement = core.motion_at(progress, options, prepared['height'])
        surfaces = core.animation_pose_at(progress, options, prepared['width'],
            prepared['height'], animation_name)
        for surface in surfaces:
            if not surface.get('visible', True):
                continue
            vertices = core.transform_vertices_for_motion(surface['vertices'], movement, progress, options)
            for index in range(0, len(vertices), 2):
                x, y = vertices[index], vertices[index + 1]
                if not math.isfinite(x) or not math.isfinite(y):
                    raise ValueError('動畫包含無效的網格座標。')
                min_x, max_x = min(min_x, x), max(max_x, x)
                min_y, max_y = min(min_y, y), max(max_y, y)
    if not all(math.isfinite(value) for value in (min_x, min_y, max_x, max_y)):
        raise ValueError('動畫沒有可輸出的可見網格。')
    width, height = size
    scale = min(width * (1 - 2 * padding) / max(1e-6, max_x - min_x),
        height * (1 - 2 * padding) / max(1e-6, max_y - min_y))
    camera = {
        'scale': scale,
        'origin_x': width / 2 - (min_x + max_x) / 2 * scale,
        'origin_y': height / 2 + (min_y + max_y) / 2 * scale,
    }
    return camera, [min_x, min_y, max_x, max_y]


def export_sequence(prepared, options, output_dir, animation_name='rotate_loop', fps=30,
                    size=(512, 512), *, padding=.08, cancel_event=None,
                    progress_callback=None) -> dict[str, Any]:
    """Write frame_0000.png… plus sequence.json; return paths and completion status.

    ``progress_callback(completed, total)`` runs on the caller's thread. An event
    with ``is_set()`` can cancel fitting or rendering. Partial output is retained
    with an explicit cancelled/error manifest. Existing nonempty directories are
    refused so earlier exports and unrelated files are preserved.
    """
    import json

    if isinstance(options, dict):
        options = core.TurnOptions(**options)
    options = core.resolve_options(prepared, options)
    if not isinstance(size, (tuple, list)) or len(size) != 2:
        raise ValueError('畫布尺寸需提供寬度與高度。')
    dimensions = []
    for value in size:
        number = _finite_number(value, '畫布尺寸')
        if isinstance(value, bool) or not number.is_integer() or not 64 <= number <= 4096:
            raise ValueError('畫布寬高需為 64 到 4096 的整數。')
        dimensions.append(int(number))
    size = tuple(dimensions)
    padding = _finite_number(padding, '邊界比例')
    if not 0 <= padding <= .45:
        raise ValueError('邊界比例需介於 0 到 0.45。')
    for key in ('width', 'height'):
        if _finite_number(prepared[key], '素材尺寸') <= 0:
            raise ValueError('素材尺寸必須大於 0。')
    plan = _frame_plan(options, animation_name, fps)
    destination = Path(output_dir).resolve()
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise FileExistsError('序列圖輸出資料夾已有檔案，請選擇新的空資料夾。')
    destination.mkdir(parents=True, exist_ok=True)
    manifest_path = destination / 'sequence.json'
    files = []
    camera = bounds = None
    status = 'cancelled'
    failure = None

    def record_manifest():
        manifest = {
            'format': 'spine-turn-transparent-sequence-v1', 'status': status,
            'complete': status == 'complete',
            'renderer': 'Pillow CPU software rasterization of shared Spine mesh/color/motion helpers',
            'animation': animation_name, 'duration': plan['duration'], 'loop': plan['loop'],
            'requested_fps': plan['requested_fps'], 'effective_fps': plan['effective_fps'],
            'canvas': list(size), 'padding': padding, 'world_bounds': bounds,
            'camera': camera, 'world_pivot': [0, 0],
            'canvas_pivot': [camera['origin_x'], camera['origin_y']] if camera else None,
            'frame_count': len(files), 'expected_frame_count': plan['frame_count'],
            'alpha': 'straight', 'transparent_background': True, 'ground_line': False,
            'loop_endpoint_duplicated': False,
            'endpoint_included': not plan['loop'] and status == 'complete',
            'sample_time_formula': 'i * duration / intervals', 'intervals': plan['intervals'],
            'options': asdict(options) if is_dataclass(options) else {},
            'files': files,
        }
        if failure is not None:
            manifest['error'] = str(failure)
        with manifest_path.open('x', encoding='utf-8') as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2)

    try:
        camera, bounds = _fit_camera(prepared, options, size, padding, plan, animation_name, cancel_event)
        if camera is not None:
            if progress_callback:
                progress_callback(0, plan['frame_count'])
            for index, progress in enumerate(plan['progresses']):
                if _cancelled(cancel_event):
                    break
                start, end, _ = ANIMATION_ARCS[animation_name]
                image = render_pose(prepared, options, start + (end - start) * progress,
                    size=size, background='transparent', progress=progress,
                    animation_name=animation_name, show_ground=False, camera=camera)
                if image.mode != 'RGBA' or image.size != size:
                    raise ValueError('序列圖繪製器必須回傳指定尺寸的 RGBA 圖片。')
                filename = f'frame_{index:04d}.png'
                frame_path = destination / filename
                created = False
                try:
                    with frame_path.open('xb') as stream:
                        created = True
                        image.save(stream, format='PNG')
                except BaseException:
                    if created:
                        frame_path.unlink(missing_ok=True)
                    raise
                finally:
                    image.close()
                files.append(filename)
                if progress_callback:
                    progress_callback(len(files), plan['frame_count'])
            if len(files) == plan['frame_count']:
                status = 'complete'
    except BaseException as error:
        status, failure = 'error', error
        try:
            record_manifest()
        except OSError:
            pass
        raise
    record_manifest()
    return {
        'ok': status == 'complete', 'status': status, 'output_dir': str(destination),
        'frame_count': len(files), 'expected_frame_count': plan['frame_count'],
        'frame_paths': [str(destination / filename) for filename in files],
        'manifest_path': str(manifest_path), 'effective_fps': plan['effective_fps'],
        'camera': camera, 'world_bounds': bounds,
    }
