"""Editable orthographic turns for Spine 3.8, 4.0 and 4.2.

The stable 4.0.56 authoring model emits native mesh/deform animation, never image sequences.
The native editor/CLI must import the JSON to create a real .spine project.
"""
from __future__ import annotations

import json
import math
import re
import struct
import threading
from bisect import bisect_right
from dataclasses import asdict, dataclass, fields, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageColor, ImageDraw, ImageOps
from spine_turn_formats import (FORMAT_SOURCES, SPINE_TARGETS, convert_skeleton,
                                normalize_spine_version, spine_family,
                                animation_key_times, select_native_safe_fps)
from spine_turn_diamond import (get_diamond_guides, validate_diamond_guides,
                                get_diamond_alignment, adjust_diamond_alignment)
from spine_turn_coin_fx import coin_shine_active

SPINE_VERSION = SPINE_TARGETS["4.0"]
TRIANGLES = [0, 1, 2, 2, 3, 0]
FACE_UVS = [0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0]


@dataclass
class TurnOptions:
    name: str = "coin"
    width: float = 0
    height: float = 0
    thickness: float = 24
    segments: int = 32
    duration: float = 2.0
    axis: str = "y"
    shape: str = "ellipse"
    key_step_degrees: float = 15
    trim_transparent: bool = True
    edge_color: str = "#c99535"
    shade_edge: bool = True
    edge_orientation: str = "horizontal"
    base_scale: float = 1.0
    bounce_enabled: bool = False
    bounce_height: float = 100
    peak_scale: float = 1.15
    landing_squash: float = 0.12
    shade_faces: bool = False
    min_brightness: float = 0.4
    shade_curve: float = 1.0
    light_angle: float = 0.0
    z_scale: float = 1.0
    peak_z_scale: float = 1.0
    z_bounce_enabled: bool = False
    z_bounce_depth: float = 150.0
    z_offset: float = 0.0
    camera_distance: float = 1000.0
    bounce_start: float = 0.08
    bounce_apex: float = 0.4
    bounce_land: float = 0.8
    bounce_end: float = 1.0
    z_bounce_start: float = 0.08
    z_bounce_apex: float = 0.4
    z_bounce_end: float = 0.8
    contour_points: tuple = ()
    bevel_width: float = 0.0
    bevel_depth: float = 0.25
    raised_contour_points: tuple = ()
    side_mode: str = "strip"
    spine_version: str = SPINE_VERSION
    model: str = "extrusion"
    diamond_facets: int = 8
    diamond_center_x: float = 0.0
    diamond_table_y: float = 0.35
    diamond_waist_y: float = 0.10
    diamond_tip_y: float = -0.48
    diamond_table_width: float = 0.50
    diamond_waist_width: float = 0.96
    diamond_girdle_height: float = 0.015
    diamond_view_tilt: float = 12.0
    diamond_shading: float = 0.65
    diamond_shine_enabled: bool = True
    diamond_shine_strength: float = 0.35
    diamond_sparkles_enabled: bool = True
    diamond_sparkle_strength: float = 0.65
    diamond_front_uv_points: tuple = ()
    diamond_back_uv_points: tuple = ()
    diamond_cut_regions: tuple = ()
    diamond_table_depth: float = 0.0
    diamond_waist_depth: float = 0.0
    diamond_ring_phase: float = 0.0
    coin_shine_enabled: bool = False
    coin_shine_strength: float = 0.4
    coin_shine_width: float = 0.5
    coin_shine_angle: float = -25.0
    coin_shine_start: float = 0.0
    coin_shine_end: float = 0.25
    coin_shine_repeat: int = 1
    irregular_contours: tuple = ()
    outline_alpha_threshold: int = 16
    outline_tolerance: float = 1.0
    z_spin_enabled: bool = False
    z_spin_direction: str = "clockwise"
    z_spin_start: float = 0.0
    z_spin_end: float = 1.0


def _options(options: TurnOptions | dict | None) -> TurnOptions:
    opts = TurnOptions(**options) if isinstance(options, dict) else (options or TurnOptions())
    if not isinstance(opts, TurnOptions):
        raise TypeError("options must be TurnOptions or dict")
    target_version = normalize_spine_version(opts.spine_version)
    if not isinstance(opts.z_spin_enabled, bool):
        raise ValueError("畫面內旋轉的啟用設定必須是開關值。")
    spin_direction = str(opts.z_spin_direction).lower()
    if spin_direction not in ("clockwise", "counterclockwise"):
        raise ValueError("畫面內旋轉方向需為 clockwise 或 counterclockwise。")
    if any(isinstance(getattr(opts, name), bool) for name in ("z_spin_start", "z_spin_end")):
        raise ValueError("畫面內旋轉時間需為有效數值。")
    try:
        spin_start, spin_end = float(opts.z_spin_start), float(opts.z_spin_end)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("畫面內旋轉時間需為有效數值。") from None
    if not (math.isfinite(spin_start) and math.isfinite(spin_end) and
            0 <= spin_start < spin_end <= 1):
        raise ValueError("畫面內旋轉開始時間需早於結束時間，並位於動畫範圍內。")
    model = str(opts.model).lower()
    if model not in ("extrusion", "diamond"):
        raise ValueError("模型需為厚片或鑽石模式。")
    for field in ("width", "height", "thickness", "duration", "key_step_degrees",
                  "base_scale", "bounce_height", "peak_scale", "landing_squash",
                  "min_brightness", "shade_curve", "light_angle", "z_scale",
                  "peak_z_scale", "z_bounce_depth", "z_offset", "camera_distance",
                  "bounce_start", "bounce_apex", "bounce_land", "bounce_end",
                  "z_bounce_start", "z_bounce_apex", "z_bounce_end", "bevel_width", "bevel_depth",
                  "diamond_center_x", "diamond_table_y", "diamond_waist_y", "diamond_tip_y",
                  "diamond_table_width", "diamond_waist_width", "diamond_girdle_height", "diamond_view_tilt",
                  "diamond_shading", "diamond_shine_strength", "diamond_sparkle_strength",
                  "diamond_table_depth", "diamond_waist_depth", "diamond_ring_phase",
                  "coin_shine_strength", "coin_shine_width", "coin_shine_angle",
                  "coin_shine_start", "coin_shine_end", "coin_shine_repeat",
                  "outline_alpha_threshold", "outline_tolerance"):
        if not math.isfinite(float(getattr(opts, field))):
            raise ValueError(f"{field} must be finite")
    if opts.width < 0 or opts.height < 0 or opts.width > 4096 or opts.height > 4096:
        raise ValueError("width and height must be between 0 and 4096")
    if not 0 <= opts.thickness <= 2048:
        raise ValueError("thickness must be between 0 and 2048")
    if not 0.1 <= opts.duration <= 60:
        raise ValueError("duration must be between 0.1 and 60 seconds")
    if not 8 <= int(opts.segments) <= 128:
        raise ValueError("segments must be between 8 and 128")
    if not 2 <= opts.key_step_degrees <= 45:
        raise ValueError("key_step_degrees must be between 2 and 45")
    if not 0.05 <= opts.base_scale <= 10:
        raise ValueError("base_scale must be between 0.05 and 10")
    if not 0 <= opts.bounce_height <= 4096:
        raise ValueError("bounce_height must be between 0 and 4096")
    if not 0.1 <= opts.peak_scale <= 5:
        raise ValueError("peak_scale must be between 0.1 and 5")
    if not 0 <= opts.landing_squash <= 0.65:
        raise ValueError("landing_squash must be between 0 and 0.65")
    if not 0 <= opts.min_brightness <= 1:
        raise ValueError("min_brightness must be between 0 and 1")
    if not 0.05 <= opts.shade_curve <= 8:
        raise ValueError("shade_curve must be between 0.05 and 8")
    if not 0.05 <= opts.z_scale <= 10 or not 0.05 <= opts.peak_z_scale <= 10:
        raise ValueError("z_scale and peak_z_scale must be between 0.05 and 10")
    if not 1 <= opts.camera_distance <= 1_000_000:
        raise ValueError("camera_distance must be between 1 and 1000000")
    if not -20000 <= opts.z_bounce_depth <= 20000:
        raise ValueError("z_bounce_depth must be between -20000 and 20000")
    maximum_z = opts.z_offset + (max(0, opts.z_bounce_depth) if opts.z_bounce_enabled else 0)
    if maximum_z > opts.camera_distance * 0.9:
        raise ValueError("Z position must stay at least 10% of camera_distance behind the virtual camera")
    if not 0 <= opts.bounce_start < opts.bounce_apex < opts.bounce_land <= opts.bounce_end <= 1:
        raise ValueError("Y timing must satisfy 0 <= start < apex < land <= end <= 1")
    if not 0 <= opts.z_bounce_start < opts.z_bounce_apex < opts.z_bounce_end <= 1:
        raise ValueError("Z timing must satisfy 0 <= start < apex < end <= 1")
    if not 0 <= opts.bevel_width <= 0.2:
        raise ValueError("bevel_width must be between 0 and 0.2")
    if not 0 <= opts.bevel_depth <= 0.45:
        raise ValueError("bevel_depth must be between 0 and 0.45")
    side_mode = str(opts.side_mode).lower()
    if side_mode not in ("strip", "ridge"):
        raise ValueError("side_mode must be strip or ridge")
    edge_orientation = str(opts.edge_orientation).lower()
    if edge_orientation not in ("horizontal", "vertical", "auto"):
        raise ValueError("edge_orientation must be horizontal, vertical, or auto")
    axis = str(opts.axis).lower()
    if axis not in ("x", "y"):
        raise ValueError("axis must be x or y")
    shape = str(opts.shape).lower()
    if shape in ("round", "circle", "coin"):
        shape = "ellipse"
    if shape in ("rectangle", "card", "rectangular"):
        shape = "rectangle"
    if shape in ("outline", "contour", "alpha"):
        shape = "polygon"
    if shape == "irregular" and model == "extrusion" and (side_mode == "ridge" or opts.bevel_width > 0 or opts.raised_contour_points):
        raise ValueError("不規則外框目前不支援斜面、凸起或石塊模式；請先關閉這些設定。")
    if side_mode == "ridge" and model == "extrusion":
        shape = "polygon"
    if shape not in ("ellipse", "rectangle", "polygon", "irregular"):
        raise ValueError("shape must be ellipse, rectangle, polygon, or irregular")
    if (isinstance(opts.outline_alpha_threshold, bool) or int(opts.outline_alpha_threshold) != opts.outline_alpha_threshold
            or not 1 <= opts.outline_alpha_threshold <= 255):
        raise ValueError("外框透明度門檻需為 1 到 255 的整數。")
    if not 0 <= opts.outline_tolerance <= 4:
        raise ValueError("外框簡化誤差需為 0 到 4 像素。")
    try:
        irregular = tuple(tuple(tuple(float(value) for value in point) for point in loop) for loop in opts.irregular_contours)
    except (ValueError, TypeError):
        raise ValueError("不規則輪廓需由有效的封閉頂點環組成。") from None
    if irregular and (sum(map(len, irregular)) > 512 or any(not 3 <= len(loop) <= 256 or
        any(len(point) != 2 or any(not math.isfinite(value) or abs(value) > .50001 for value in point) for point in loop)
        for loop in irregular)):
        raise ValueError("不規則輪廓每環需 3 到 256 點、合計最多 512 點，且位於圖片範圍內。")
    points = tuple(tuple(float(coordinate) for coordinate in point) for point in opts.contour_points)
    if points:
        if not 3 <= len(points) <= 128 or any(len(point) != 2 for point in points):
            raise ValueError("contour_points must contain between 3 and 128 XY pairs")
        if any(not math.isfinite(value) or abs(value) > 0.50001 for point in points for value in point):
            raise ValueError("contour_points must be finite normalized coordinates between -0.5 and 0.5")
        area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:] + points[:1]))
        if abs(area) < 1e-10:
            raise ValueError("contour_points must enclose a nonzero area")
        if area < 0:
            points = tuple(reversed(points))
    try:
        raised = tuple(tuple(float(coordinate) for coordinate in point) for point in opts.raised_contour_points)
    except (TypeError, ValueError):
        raise ValueError("凸起區域需由有效的頂點座標組成。") from None
    if raised:
        if len(raised) > 1 and raised[0] == raised[-1]:
            raised = raised[:-1]
        if not 3 <= len(raised) <= 32 or any(len(point) != 2 for point in raised):
            raise ValueError("凸起區域需要 3 到 32 個頂點。")
        if any(not math.isfinite(value) or abs(value) > 0.50001 for point in raised for value in point):
            raise ValueError("凸起區域的頂點必須位於圖片範圍內。")
    if isinstance(opts.diamond_facets, bool) or int(opts.diamond_facets) != opts.diamond_facets or not 4 <= opts.diamond_facets <= 16:
        raise ValueError("鑽石切面數需為 4 到 16 的整數。")
    if not 0 <= opts.diamond_girdle_height <= 0.12:
        raise ValueError("鑽石腰帶高度需為圖片高度的 0 到 12%。")
    if not 0 <= opts.diamond_view_tilt <= 35:
        raise ValueError("鑽石俯視角度需為 0 到 35 度。")
    if any(not 0 <= value <= 2 for value in (opts.diamond_table_depth, opts.diamond_waist_depth)):
        raise ValueError("台面與腰部前後直徑需為圖片寬度的 0 到 200%；0 代表自動。")
    if not 0 <= opts.coin_shine_strength <= 1 or not .05 <= opts.coin_shine_width <= 1:
        raise ValueError("掃光強度需為 0 到 100%，光帶寬度需為圖片寬度的 5 到 100%。")
    if not 0 <= opts.coin_shine_start < opts.coin_shine_end <= 1:
        raise ValueError("掃光開始時間需早於結束時間，並位於動畫範圍內。")
    if isinstance(opts.coin_shine_repeat, bool) or int(opts.coin_shine_repeat) != opts.coin_shine_repeat or not 1 <= opts.coin_shine_repeat <= 4:
        raise ValueError("掃光次數需為 1 到 4 的整數。")
    if any(not 0 <= value <= 1 for value in (opts.diamond_shading, opts.diamond_shine_strength, opts.diamond_sparkle_strength)):
        raise ValueError("鑽石明暗、光帶與星芒強度需為 0 到 100%。")
    if model == "diamond":
        validate_diamond_guides({name: getattr(opts, name) for name in (
            "diamond_center_x", "diamond_table_y", "diamond_waist_y", "diamond_tip_y",
            "diamond_table_width", "diamond_waist_width")})
        if opts.diamond_girdle_height / 2 >= min(opts.diamond_table_y - opts.diamond_waist_y,
                                               opts.diamond_waist_y - opts.diamond_tip_y):
            raise ValueError("鑽石腰帶高度過大，已碰到台面或底尖。")
    uv_points = {}
    for role in ("front", "back"):
        values = tuple(tuple(float(coordinate) for coordinate in point)
                       for point in getattr(opts, f"diamond_{role}_uv_points"))
        if values and (len(values) < 3 or any(len(point) != 2 or any(not math.isfinite(value) or abs(value) > .50001
                                                                 for value in point) for point in values)):
            raise ValueError("鑽石貼圖範圍含有無效座標。")
        uv_points[f"diamond_{role}_uv_points"] = values
    cut_regions = ()
    if opts.diamond_cut_regions:
        from spine_turn_diamond_cuts import validate_cut_regions
        cut_regions = validate_cut_regions(opts.diamond_cut_regions)
    ImageColor.getrgb(opts.edge_color)
    # Four equal subdivisions preserve the exact rectangle corners.
    segments = int(opts.segments)
    if shape == "rectangle":
        segments = max(8, round(segments / 4) * 4)
    return replace(opts, axis=axis, shape=shape, segments=segments,
                   edge_orientation=edge_orientation, contour_points=points,
                   raised_contour_points=raised, side_mode=side_mode,
                   spine_version=target_version, model=model, diamond_facets=int(opts.diamond_facets),
                   diamond_cut_regions=cut_regions,
                   diamond_ring_phase=((opts.diamond_ring_phase + 180) % 360 - 180),
                   coin_shine_angle=((opts.coin_shine_angle + 180) % 360 - 180),
                   coin_shine_repeat=int(opts.coin_shine_repeat), irregular_contours=irregular,
                   outline_alpha_threshold=int(opts.outline_alpha_threshold),
                   z_spin_direction=spin_direction, z_spin_start=spin_start, z_spin_end=spin_end,
                   **uv_points)


def normalize_options(options: TurnOptions | dict | None = None) -> TurnOptions:
    """Public settings validation for editable-project save/load workflows."""
    try:
        return _options(options)
    except TypeError as error:
        raise ValueError("專案設定含有不支援的欄位或資料格式。") from error


def _load_image(path: str | Path) -> Image.Image:
    with Image.open(path) as source:
        if source.width * source.height > 40_000_000:
            raise ValueError("Image is too large; use an image smaller than 40 megapixels")
        result = ImageOps.exif_transpose(source).convert("RGBA")
    if result.getchannel("A").getbbox() is None:
        raise ValueError("Image is completely transparent")
    return result


def _trim(image: Image.Image, enabled: bool) -> tuple[Image.Image, tuple]:
    bounds = image.getchannel("A").getbbox() if enabled else (0, 0, *image.size)
    return image.crop(bounds), bounds


def _contain(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    image = ImageOps.contain(image, size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", size)
    canvas.alpha_composite(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2))
    return canvas


def prepare_images(front_path: str | Path, back_path: str | Path | None = None,
                   edge_path: str | Path | None = None,
                   options: TurnOptions | dict | None = None) -> dict[str, Any]:
    """Load artwork; return PIL RGBA front/back/edge plus resolved dimensions.

    Side-strip U follows the perimeter and V follows front-to-back thickness.
    Independent back artwork is supplied upright for the 180-degree pose.
    In irregular extrusion mode, a missing back or an explicit back with the
    same decoded RGBA uses the processed front mirrored for Y turns or flipped
    for X turns, so both sides share one physical outline. Other missing backs
    reuse the front unchanged. A missing edge gets a neutral colored rim.
    """
    opts = _options(options)
    front_original = _load_image(front_path)
    front, front_bounds = _trim(front_original, opts.trim_transparent)
    width = opts.width or (opts.height * front.width / front.height if opts.height else front.width)
    height = opts.height or (opts.width * front.height / front.width if opts.width else front.height)
    width, height = max(1, round(width)), max(1, round(height))
    if width > 4096 or height > 4096:
        raise ValueError("Resolved image dimensions must not exceed 4096 pixels")
    front = front.resize((width, height), Image.Resampling.LANCZOS)
    back_bounds = None
    duplicate_irregular_back = False
    if back_path:
        back_original = _load_image(back_path)
        duplicate_irregular_back = (opts.shape == 'irregular' and opts.model == 'extrusion'
            and front_original.size == back_original.size
            and front_original.tobytes() == back_original.tobytes())
        if duplicate_irregular_back:
            # A second copy of the same asymmetric picture is still one
            # physical cutout. Its reverse must share the reflected outline.
            back = ImageOps.mirror(front) if opts.axis == 'y' else ImageOps.flip(front)
            back_bounds = front_bounds
        else:
            back, back_bounds = _trim(back_original, opts.trim_transparent)
            back = _contain(back, (width, height))
    else:
        back = front.copy()
        if opts.shape == 'irregular' and opts.model == 'extrusion':
            back = ImageOps.mirror(back) if opts.axis == 'y' else ImageOps.flip(back)
    edge_source_size = None
    edge_original_orientation = "generated"
    edge_resolved_orientation = "horizontal"
    if edge_path:
        edge = _load_image(edge_path)
        edge_source_size = list(edge.size)
        edge_original_orientation = "vertical" if edge.height > edge.width else "horizontal"
        edge_resolved_orientation = (edge_original_orientation if opts.edge_orientation == "auto"
                                     else opts.edge_orientation)
        if edge_resolved_orientation == "vertical":
            # ROTATE_90 is counterclockwise: original top-to-bottom becomes
            # canonical left-to-right, and original right-to-left becomes V.
            edge = edge.transpose(Image.Transpose.ROTATE_90)
        if edge.width > 4096 or edge.height > 2048:
            edge.thumbnail((4096, 2048), Image.Resampling.LANCZOS)
    else:
        # This is a generated neutral material, not a reconstruction of hidden art.
        edge = Image.new("RGBA", (512, 64), ImageColor.getrgb(opts.edge_color) + (255,))
        draw = ImageDraw.Draw(edge)
        base = ImageColor.getrgb(opts.edge_color)
        for x in range(0, edge.width, 8):
            draw.line((x, 3, x, 60), fill=tuple(round(c * 0.75) for c in base) + (255,), width=1)
        highlight = tuple(min(255, round(c * 1.22)) for c in base) + (255,)
        draw.line((0, 2, 511, 2), fill=highlight, width=2)
        draw.line((0, 61, 511, 61), fill=highlight, width=2)
    contour_analysis = None
    contour_points = []
    if opts.shape == "polygon" and opts.model != "diamond":
        from spine_turn_contour import analyze_convex_outline
        contour_analysis = analyze_convex_outline(front)
        contour_points = contour_analysis["points"]
    prepared = {
        "front": front, "back": back, "edge": edge,
        "width": float(width), "height": float(height),
        "front_bounds": list(front_bounds),
        "back_bounds": list(back_bounds) if back_bounds else None,
        "back_reuses_front": not bool(back_path), "edge_is_placeholder": not bool(edge_path),
        "edge_source_size": edge_source_size,
        "edge_original_orientation": edge_original_orientation,
        "edge_resolved_orientation": edge_resolved_orientation,
        "edge_canonical_orientation": "horizontal",
        "contour_points": contour_points,
        "contour_analysis": contour_analysis,
    }
    if opts.shape == 'irregular' and opts.model == 'extrusion':
        from spine_turn_contour import analyze_irregular_outline
        analysis = analyze_irregular_outline(front, alpha_threshold=opts.outline_alpha_threshold,
                                             simplify_tolerance=opts.outline_tolerance)
        prepared['irregular_analysis'] = analysis
        prepared['irregular_contours'] = analysis['loops']
        prepared['irregular_outline_parameters'] = (opts.outline_alpha_threshold, opts.outline_tolerance)
        prepared['back_mode'] = ('mirrored_duplicate_front_for_irregular' if duplicate_irregular_back else
                                 'supplied' if back_path else 'mirrored_front_for_irregular')
        prepared['back_auto_aligned'] = duplicate_irregular_back
    if opts.model == "diamond" and (opts.diamond_shine_enabled or opts.diamond_sparkles_enabled):
        from spine_turn_diamond_fx import make_effect_textures
        extra_textures = make_effect_textures(opts)
        prepared.update(extra_textures)
        prepared["generated_texture_names"] = list(extra_textures)
    elif coin_shine_active(opts):
        from spine_turn_coin_fx import make_effect_textures
        extra_textures = make_effect_textures(prepared, opts)
        prepared.update(extra_textures)
        prepared["generated_texture_names"] = list(extra_textures)
    return prepared


def validate_raised_region(outer, inner, width: float, height: float) -> tuple:
    """Return a CCW convex inner outline with at least one image-pixel gap."""
    if not all(math.isfinite(float(value)) and float(value) > 0 for value in (width, height)):
        raise ValueError("圖片尺寸無效，無法檢查凸起區域。")
    width, height = float(width), float(height)
    try:
        outer = [tuple(map(float, point)) for point in outer]
        inner = [tuple(map(float, point)) for point in inner]
    except (TypeError, ValueError):
        raise ValueError("凸起區域需由有效的頂點座標組成。") from None
    if len(inner) > 1 and inner[0] == inner[-1]:
        inner.pop()
    if not 3 <= len(inner) <= 32 or any(len(point) != 2 for point in inner):
        raise ValueError("凸起區域需要 3 到 32 個頂點。")
    if len(outer) < 3 or any(len(point) != 2 for point in outer):
        raise ValueError("圖片尚未取得有效的多邊形外框。")
    if any(not math.isfinite(value) for point in outer + inner for value in point):
        raise ValueError("凸起區域含有無效座標。")
    if any(abs(value) > 0.50001 for point in inner for value in point):
        raise ValueError("凸起區域的頂點必須位於圖片範圍內。")
    physical_outer = [(x * width, y * height) for x, y in outer]
    physical_inner = [(x * width, y * height) for x, y in inner]
    area_tolerance = max(width, height) ** 2 * 1e-10
    length_tolerance = max(width, height) * 1e-8

    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def area(points):
        return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:] + points[:1])) / 2

    for index, a in enumerate(physical_inner):
        if any(math.dist(a, b) <= length_tolerance for b in physical_inner[index + 1:]):
            raise ValueError("凸起區域含有重複或過於接近的頂點。")

    def on_segment(a, b, p):
        return (min(a[0], b[0]) - length_tolerance <= p[0] <= max(a[0], b[0]) + length_tolerance and
                min(a[1], b[1]) - length_tolerance <= p[1] <= max(a[1], b[1]) + length_tolerance)

    for index, (a, b) in enumerate(zip(physical_inner, physical_inner[1:] + physical_inner[:1])):
        for other in range(index + 1, len(physical_inner)):
            if other == index + 1 or (index == 0 and other == len(physical_inner) - 1):
                continue
            c, d = physical_inner[other], physical_inner[(other + 1) % len(physical_inner)]
            values = (cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b))
            intersects = values[0] * values[1] < 0 and values[2] * values[3] < 0
            intersects = intersects or any(abs(value) <= area_tolerance and on_segment(s, t, p)
                                          for value, s, t, p in ((values[0], a, b, c), (values[1], a, b, d),
                                                                 (values[2], c, d, a), (values[3], c, d, b)))
            if intersects:
                raise ValueError("凸起區域的邊線不可交叉或互相接觸。")
    if abs(area(physical_inner)) <= area_tolerance:
        raise ValueError("凸起區域太小，請畫出具有面積的區域。")
    if area(physical_inner) < 0:
        physical_inner.reverse()
    if area(physical_outer) < 0:
        physical_outer.reverse()
    for index, point in enumerate(physical_inner):
        if cross(physical_inner[index - 1], point, physical_inner[(index + 1) % len(physical_inner)]) < -area_tolerance:
            raise ValueError("凸起區域目前需為凸多邊形，請移除向內凹的轉角。")
    # Redundant straight-line points add no shape information and can create
    # tiny native mesh triangles, so return the equivalent corner polygon.
    changed = True
    while changed and len(physical_inner) > 3:
        changed = False
        for index, point in enumerate(physical_inner):
            if abs(cross(physical_inner[index - 1], point,
                         physical_inner[(index + 1) % len(physical_inner)])) <= area_tolerance:
                physical_inner.pop(index)
                changed = True
                break
    for a, b in zip(physical_outer, physical_outer[1:] + physical_outer[:1]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length <= length_tolerance:
            raise ValueError("圖片外框含有無效的短邊。")
        nx, ny = dy / length, -dx / length
        constant = nx * a[0] + ny * a[1]
        if any(constant - nx * x - ny * y < 1.0 - 1e-6 for x, y in physical_inner):
            raise ValueError("凸起區域需完全位於圖片外框內，並與外框保留至少 1 像素間距。")
    return tuple((x / width, y / height) for x, y in physical_inner)


def raised_region_points(images: dict[str, Any], options: TurnOptions | dict | None = None) -> tuple:
    """Return the editable explicit region, or a useful automatic initial one."""
    opts = _options(options)
    base = resolve_options(images, replace(opts, shape="polygon", bevel_width=0, raised_contour_points=()))
    if opts.raised_contour_points:
        return validate_raised_region(base.contour_points, opts.raised_contour_points,
                                      images["width"], images["height"])
    width, height = images["width"], images["height"]
    outer = [(x * width, y * height) for x, y in base.contour_points]
    distance = max(1.0, (opts.bevel_width or 0.07) * min(width, height))
    while distance >= 1.0:
        try:
            inner = _inset_convex_polygon(outer, distance)
            return validate_raised_region(base.contour_points, [(x / width, y / height) for x, y in inner], width, height)
        except ValueError:
            if distance == 1.0:
                break
            distance = max(1.0, distance * 0.7)
    raise ValueError("圖片外框過窄，無法建立保留 1 像素間距的凸起區域。")


def get_raised_region(images: dict[str, Any], options: TurnOptions | dict | None = None) -> tuple:
    return raised_region_points(images, options)


def resolve_options(images: dict[str, Any], options: TurnOptions | dict | None = None) -> TurnOptions:
    """Resolve alpha-derived polygon geometry after artwork normalization."""
    opts = _options(options)
    if opts.model == "diamond":
        from spine_turn_contour import analyze_convex_outline
        uv_boundaries = images.get("diamond_uv_boundaries")
        if uv_boundaries is None:
            uv_boundaries = {}
            for role in ("front", "back"):
                try:
                    uv_boundaries[role] = analyze_convex_outline(images[role])["points"]
                except ValueError:
                    uv_boundaries[role] = []
            images["diamond_uv_boundaries"] = uv_boundaries
        guides = get_diamond_guides(images, opts)
        images["diamond_guides"] = guides
        get_diamond_alignment(opts, images["width"], images["height"])
        return replace(opts, **guides,
                       diamond_front_uv_points=tuple(tuple(point) for point in uv_boundaries["front"]),
                       diamond_back_uv_points=tuple(tuple(point) for point in uv_boundaries["back"]))
    if opts.shape == 'irregular':
        parameters = (opts.outline_alpha_threshold, opts.outline_tolerance)
        if images.get('irregular_outline_parameters') != parameters or not images.get('irregular_analysis'):
            from spine_turn_contour import analyze_irregular_outline
            images['irregular_analysis'] = analyze_irregular_outline(images['front'],
                alpha_threshold=opts.outline_alpha_threshold, simplify_tolerance=opts.outline_tolerance)
            images['irregular_outline_parameters'] = parameters
        loops = images['irregular_analysis']['loops']
        images['irregular_contours'] = loops
        resolved = _options(replace(opts, irregular_contours=tuple(tuple(tuple(point) for point in loop) for loop in loops)))
        from spine_turn_irregular import irregular_statistics
        images['irregular_statistics'] = irregular_statistics(resolved, images['width'], images['height'])
        return resolved
    if opts.shape != "polygon":
        return opts
    points = images.get("contour_points") or opts.contour_points
    if not points:
        from spine_turn_contour import analyze_convex_outline
        analysis = analyze_convex_outline(images["front"])
        images["contour_analysis"] = analysis
        images["contour_points"] = points = analysis["points"]
    resolved = _options(replace(opts, contour_points=tuple(tuple(point) for point in points)))
    if resolved.raised_contour_points:
        inner = validate_raised_region(resolved.contour_points, resolved.raised_contour_points,
                                       images["width"], images["height"])
        resolved = replace(resolved, raised_contour_points=inner)
    if (resolved.bevel_width > 0 or resolved.raised_contour_points or resolved.side_mode == "ridge") and resolved.thickness > 0:
        _bevel_profile(resolved, images["width"], images["height"], resolved.thickness * resolved.z_scale)
    return resolved


MOTION_KEY_PROGRESS = (0.0, 0.08, 0.16, 0.4, 0.8, 0.86, 0.93, 1.0)
MOTION_Z_KEY_PROGRESS = tuple(sorted(set(MOTION_KEY_PROGRESS) | {
    (first + second) / 2 for first, second in zip(MOTION_KEY_PROGRESS, MOTION_KEY_PROGRESS[1:])
}))


def _y_phase_data(opts: TurnOptions) -> list[tuple]:
    start, apex, land, end = opts.bounce_start, opts.bounce_apex, opts.bounce_land, opts.bounce_end
    prep = max(0.0, start - (apex - start) / 4)
    aux = start + (apex - start) / 4
    anticipation = min(0.06, opts.landing_squash * 0.5) if prep < start else 0.0
    squash = opts.landing_squash
    # time, scaleX factor, scaleY factor, elevation, incoming/outgoing slopes.
    records = [(0.0, 1, 1, 0, 0, 0), (prep, 1, 1, 0, 0, 0),
               (start, 1 + anticipation, 1 - anticipation, 0, 0, 2 / (apex - start)),
               (aux, 1 - anticipation, 1 + anticipation, 0.4375,
                1.5 / (apex - start), 1.5 / (apex - start)),
               (apex, opts.peak_scale, opts.peak_scale, 1, 0, 0),
               (land, 1, 1, 0, -2 / (land - apex), 0)]
    if land < end:
        records.extend([(land + 0.3 * (end - land), 1 + squash, 1 - squash, 0, 0, 0),
                        (land + 0.65 * (end - land), 1 - squash * 0.3, 1 + squash * 0.3, 0, 0, 0)])
    records.extend([(end, 1, 1, 0, 0, 0), (1.0, 1, 1, 0, 0, 0)])
    deduplicated = {}
    for record in records:
        time = round(record[0], 12)
        # A coincident recovery-end key must retain the landing's incoming
        # slope; otherwise a land=end clip would brake before touching down.
        if time in deduplicated and time == round(land, 12):
            previous = deduplicated[time]
            record = (*record[:4], previous[4], record[5])
        deduplicated[time] = (time, *record[1:])
    return [deduplicated[time] for time in sorted(deduplicated)]


def _z_key_progress(opts: TurnOptions) -> tuple[float, ...]:
    if (opts.z_bounce_start, opts.z_bounce_apex, opts.z_bounce_end) == (0.08, 0.4, 0.8):
        return MOTION_Z_KEY_PROGRESS
    old = (0.0, 0.08, 0.4, 0.8, 1.0)
    new = (0.0, opts.z_bounce_start, opts.z_bounce_apex, opts.z_bounce_end, 1.0)
    mapped = set()
    for progress in MOTION_Z_KEY_PROGRESS:
        for index in range(len(old) - 1):
            if progress <= old[index + 1]:
                fraction = (progress - old[index]) / (old[index + 1] - old[index])
                mapped.add(round(new[index] + fraction * (new[index + 1] - new[index]), 12))
                break
    return tuple(sorted(mapped))


def motion_key_progress(options: TurnOptions | dict | None = None) -> tuple[float, ...]:
    """Actual normalized timing events for preview/sequence union bounds."""
    opts = _options(options)
    keys = {0.0, 1.0}
    if opts.bounce_enabled:
        keys.update(record[0] for record in _y_phase_data(opts))
    if opts.z_bounce_enabled:
        keys.update(_z_key_progress(opts))
    return tuple(sorted(keys))


def _y_motion_tracks(opts: TurnOptions, height: float = 0) -> dict[str, list[dict]]:
    """Sparse Spine 4.0 one-value timelines in normalized clip time.

    Bezier controls are absolute time/value coordinates, as required by 4.0.
    All three channels share linear Bezier time handles, so vertical ground
    compensation remains a linear combination of the same scale curve.
    """
    if not opts.bounce_enabled:
        return {
            "translatey": [{"time": 0.0, "value": 0.0}, {"time": 1.0, "value": 0.0}],
            "scalex": [{"time": 0.0, "value": opts.base_scale}, {"time": 1.0, "value": opts.base_scale}],
            "scaley": [{"time": 0.0, "value": opts.base_scale}, {"time": 1.0, "value": opts.base_scale}],
        }
    phase_data = _y_phase_data(opts)
    progress_keys = [record[0] for record in phase_data]
    scale_x = [opts.base_scale * record[1] for record in phase_data]
    scale_y = [opts.base_scale * record[2] for record in phase_data]
    elevations = [record[3] * opts.bounce_height for record in phase_data]
    translation_y = [elevation + height * (sy - opts.base_scale) / 2
                     for elevation, sy in zip(elevations, scale_y)]
    # Slopes of the two quadratic flight arcs at each segment boundary. The
    # launch and landing intentionally change velocity at their contact keys.
    elevation_slopes = [(first[5], second[4]) for first, second in zip(phase_data, phase_data[1:])]
    tracks = {}
    for channel, values in (("translatey", translation_y), ("scalex", scale_x), ("scaley", scale_y)):
        frames = []
        for index, (progress, value) in enumerate(zip(progress_keys, values)):
            frame = {"time": progress, "value": value}
            if index + 1 < len(values):
                next_progress = progress_keys[index + 1]
                delta = (next_progress - progress) / 3
                slope_out, slope_in = (elevation_slopes[index] if channel == "translatey" else (0, 0))
                frame["curve"] = [progress + delta, value + delta * slope_out * opts.bounce_height,
                                  next_progress - delta,
                                  values[index + 1] - delta * slope_in * opts.bounce_height]
            frames.append(frame)
        tracks[channel] = frames
    return tracks


def _spine_curve_value(progress: float, first: dict, second: dict) -> float:
    """Evaluate the same nine interior Bezier samples used by Spine 4.0.

    This keeps the preview and exported timeline aligned between the keys;
    solving the ideal cubic directly would differ from runtime interpolation.
    """
    t0, v0 = first["time"], first["value"]
    t1, v1 = second["time"], second["value"]
    curve = first.get("curve")
    if not curve:
        return v0 + (v1 - v0) * (progress - t0) / (t1 - t0)
    cx1, cy1, cx2, cy2 = curve
    previous_t, previous_v = t0, v0
    for index in range(1, 11):
        u = index / 10
        inv = 1 - u
        t = inv ** 3 * t0 + 3 * inv ** 2 * u * cx1 + 3 * inv * u ** 2 * cx2 + u ** 3 * t1
        value = inv ** 3 * v0 + 3 * inv ** 2 * u * cy1 + 3 * inv * u ** 2 * cy2 + u ** 3 * v1
        if t >= progress:
            return previous_v + (value - previous_v) * (progress - previous_t) / (t - previous_t)
        previous_t, previous_v = t, value
    return v1


def _sample_track(frames: list[dict], progress: float) -> float:
    if progress <= frames[0]["time"]:
        return frames[0]["value"]
    for first, second in zip(frames, frames[1:]):
        if progress <= second["time"]:
            return _spine_curve_value(progress, first, second)
    return frames[-1]["value"]


def _z_envelope_frames(opts: TurnOptions) -> list[dict]:
    neutral = replace(opts, bounce_enabled=True, bounce_height=1,
                      base_scale=1, peak_scale=1, landing_squash=0,
                      bounce_start=opts.z_bounce_start, bounce_apex=opts.z_bounce_apex,
                      bounce_land=opts.z_bounce_end, bounce_end=1.0)
    return _y_motion_tracks(neutral, 0)["translatey"]


def _depth_at_resolved(progress: float, opts: TurnOptions,
                       envelope_frames: list[dict] | None = None) -> dict[str, float]:
    factor = (_sample_track(envelope_frames or _z_envelope_frames(opts), progress)
              if opts.z_bounce_enabled else 0.0)
    z = opts.z_offset + opts.z_bounce_depth * factor
    return {"z_offset": z, "z": z, "static_z_offset": opts.z_offset,
            "z_scale": opts.z_scale * (1 + (opts.peak_z_scale - 1) * factor),
            "projection_scale": opts.camera_distance / (opts.camera_distance - z),
            "progress_factor": factor}


def depth_at(progress: float, options: TurnOptions | dict | None = None) -> dict[str, float]:
    """Virtual center Z and thickness, independent of the vertical jump switch.

    Positive Z moves toward the camera. Center-distance perspective is baked
    as uniform XY magnification; this is a 2.5D approximation, not per-vertex
    perspective or a third native Spine coordinate. z_scale affects thickness.
    """
    opts = _options(options)
    if not math.isfinite(float(progress)):
        raise ValueError("progress must be finite")
    progress = max(0.0, min(1.0, float(progress)))
    result = _depth_at_resolved(progress, opts)
    result["ideal_projection_scale"] = result["projection_scale"]
    result["projection_scale"] = _sample_track(_projection_track(opts), progress)
    return result


def _motion_tracks(opts: TurnOptions, height: float = 0) -> dict[str, list[dict]]:
    """The independent physical Y layer on the turn bone."""
    initial_projection = opts.camera_distance / (opts.camera_distance - opts.z_offset)
    return _y_motion_tracks(opts, height * initial_projection)


def _projection_track(opts: TurnOptions) -> list[dict]:
    """A separate, uniform Z magnification layer on the depth child bone."""
    if not opts.z_bounce_enabled or opts.z_bounce_depth == 0:
        projection = opts.camera_distance / (opts.camera_distance - opts.z_offset)
        return [{"time": 0.0, "value": projection}, {"time": 1.0, "value": projection}]
    envelope_frames = _z_envelope_frames(opts)

    def value_at(progress: float) -> float:
        return _depth_at_resolved(progress, opts, envelope_frames)["projection_scale"]

    progress_keys = _z_key_progress(opts)
    key_values = [value_at(progress) for progress in progress_keys]
    frames = []
    for index, progress in enumerate(progress_keys):
        frame = {"time": progress, "value": key_values[index]}
        if index + 1 < len(progress_keys):
            next_progress = progress_keys[index + 1]
            interval = next_progress - progress
            epsilon = interval * 0.0001
            slope_out = (value_at(progress + epsilon) - frame["value"]) / epsilon
            slope_in = (key_values[index + 1] - value_at(next_progress - epsilon)) / epsilon
            frame["curve"] = [progress + interval / 3,
                              frame["value"] + slope_out * interval / 3,
                              next_progress - interval / 3,
                              key_values[index + 1] - slope_in * interval / 3]
        frames.append(frame)
    return frames


def motion_at(progress: float, options: TurnOptions | dict | None = None,
              height: float = 0) -> dict[str, float]:
    """Return composed world translation and scale at normalized clip progress.

    Each animation clip receives its own enabled Y and/or Z motion. Root is
    fixed. Y off/Z on keeps center y=0. Uniform center-distance magnification
    is already included in scale_x/scale_y; do not apply it again in previews.
    """
    opts = _options(options)
    progress = float(progress)
    if not math.isfinite(progress):
        raise ValueError("progress must be finite")
    height = float(height or opts.height or 0)
    if not math.isfinite(height) or height < 0:
        raise ValueError("height must be finite and nonnegative")
    progress = min(1, max(0, progress))
    values = {channel: _sample_track(frames, progress)
              for channel, frames in _motion_tracks(opts, height).items()}
    projection = _sample_track(_projection_track(opts), progress)
    return {"x": 0.0, "y": values["translatey"],
            "scale_x": values["scalex"] * projection,
            "scale_y": values["scaley"] * projection}


def timeline_motion_at(progress: float, options: TurnOptions | dict | None = None,
                       height: float = 0) -> dict[str, float]:
    """Alias for previews that explicitly evaluate exported motion interpolation."""
    return motion_at(progress, options, height)


def _z_spin_angle_resolved(progress: float, opts: TurnOptions) -> float:
    progress = float(progress)
    if not math.isfinite(progress):
        raise ValueError("progress must be finite")
    if not opts.z_spin_enabled:
        return 0.0
    fraction = min(1.0, max(0.0, (progress - opts.z_spin_start) /
                                  (opts.z_spin_end - opts.z_spin_start)))
    return fraction * (-360.0 if opts.z_spin_direction == "clockwise" else 360.0)


def z_spin_angle(progress: float, options: TurnOptions | dict | None = None) -> float:
    """Additional local screen-plane turn in Spine's counterclockwise degrees."""
    return _z_spin_angle_resolved(progress, _options(options))


def z_spin_key_progress(options: TurnOptions | dict | None = None) -> tuple[float, ...]:
    """Quarter turns plus clip/window boundaries; an empty tuple when disabled."""
    opts = _options(options)
    if not opts.z_spin_enabled:
        return ()
    span = opts.z_spin_end - opts.z_spin_start
    return tuple(sorted({0.0, 1.0, *(opts.z_spin_start + span * index / 4 for index in range(5))}))


def transform_vertices_for_motion(vertices: list[float], movement: dict[str, float],
                                  progress: float, options: TurnOptions | dict | None = None) -> list[float]:
    """Apply object-local Z rotation before the existing parent scale/translation.

    Repeated surface callers pass already-resolved TurnOptions, avoiding a full
    contour/settings validation for every mesh. The disabled arithmetic is the
    same order used by the original preview and PNG camera fitter.
    """
    opts = options if isinstance(options, TurnOptions) else _options(options)
    if len(vertices) % 2:
        raise ValueError("Mesh positions must contain matching XY pairs.")
    sx, sy, tx, ty = (movement[name] for name in ("scale_x", "scale_y", "x", "y"))
    if not opts.z_spin_enabled:
        return [value for index in range(0, len(vertices), 2)
                for value in (vertices[index] * sx + tx, vertices[index + 1] * sy + ty)]
    # The endpoint is physically the initial orientation. Reducing before trig
    # avoids a tiny sine residue changing coverage on a loop's boundary pixels.
    angle = math.radians(_z_spin_angle_resolved(progress, opts) % 360.0)
    sine, cosine = math.sin(angle), math.cos(angle)
    return [value for index in range(0, len(vertices), 2)
            for value in ((vertices[index] * cosine - vertices[index + 1] * sine) * sx + tx,
                          (vertices[index] * sine + vertices[index + 1] * cosine) * sy + ty)]


def z_spin_bounds(options: TurnOptions | dict | None, width: float, height: float) -> dict[str, float]:
    """Conservative all-angle world bounds, including sparse motion-curve handles.

    Orthographic turn/tilt cannot exceed a model's 3D radius. Rotation preserves
    that radius, and linear deform interpolation lies inside endpoint bounds.
    Bezier values stay in their control-point hull, so this also covers motion
    between authored keys without sampling or rotating the bounce trajectory.
    """
    opts = _options(options)
    depth = opts.thickness * opts.z_scale * (max(1.0, opts.peak_z_scale) if opts.z_bounce_enabled else 1.0)
    if opts.model == "diamond":
        from spine_turn_diamond import diamond_geometry
        center = opts.diamond_center_x * width
        scale = opts.z_scale * (max(1.0, opts.peak_z_scale) if opts.z_bounce_enabled else 1.0)
        radius = abs(center) + max(math.sqrt((x - center) ** 2 + y ** 2 + (z * scale) ** 2)
            for spec in diamond_geometry(opts, width, height) for x, y, z in spec["model"])
        if opts.diamond_sparkles_enabled:
            radius += math.sqrt(2.0) * min(width, height) * .075
    else:
        radius = math.sqrt(width ** 2 + height ** 2 + depth ** 2) / 2

    def interval(frames):
        values = [frame["value"] for frame in frames]
        values.extend(value for frame in frames if "curve" in frame
                      for value in (frame["curve"][1], frame["curve"][3]))
        return min(values), max(values)

    tracks = _motion_tracks(opts, height)
    projection = max(abs(value) for value in interval(_projection_track(opts)))
    rx = radius * max(abs(value) for value in interval(tracks["scalex"])) * projection
    ry = radius * max(abs(value) for value in interval(tracks["scaley"])) * projection
    lower, upper = interval(tracks["translatey"])
    return {"left": -rx, "right": rx, "bottom": lower - ry, "top": upper + ry,
            "local_radius": radius}


def _export_z_spin(duration: float, opts: TurnOptions) -> dict:
    keys = z_spin_key_progress(opts)
    if not keys:
        return {}
    frames = [{"time": round(progress * duration, 7),
               "value": round(_z_spin_angle_resolved(progress, opts), 7)} for progress in keys]
    if any(first["time"] >= second["time"] for first, second in zip(frames, frames[1:])):
        raise ValueError("畫面內旋轉時間過短，無法在目前動畫長度內保留完整旋轉關鍵格。")
    return {"spin": {"rotate": frames}}


def _export_motion(duration: float, opts: TurnOptions, height: float) -> dict:
    if (not opts.bounce_enabled and opts.base_scale == 1 and
            not opts.z_bounce_enabled and opts.z_offset == 0):
        return _export_z_spin(duration, opts) if opts.z_spin_enabled else {}
    bone_tracks = {"turn": _motion_tracks(opts, height)}
    if opts.z_bounce_enabled or opts.z_offset != 0:
        projection = _projection_track(opts)
        bone_tracks["depth"] = {
            channel: [{key: value.copy() if isinstance(value, list) else value
                       for key, value in frame.items()} for frame in projection]
            for channel in ("scalex", "scaley")
        }
    for tracks in bone_tracks.values():
        for frames in tracks.values():
            for frame in frames:
                frame["time"] = round(frame["time"] * duration, 7)
                frame["value"] = round(frame["value"], 7)
                if "curve" in frame:
                    cx1, cy1, cx2, cy2 = frame["curve"]
                    frame["curve"] = [round(cx1 * duration, 7), round(cy1, 7),
                                      round(cx2 * duration, 7), round(cy2, 7)]
    if opts.z_spin_enabled:
        bone_tracks.update(_export_z_spin(duration, opts))
    return bone_tracks


def _project(x: float, y: float, z: float, angle: float, axis: str) -> tuple[float, float]:
    sine, cosine = math.sin(angle), math.cos(angle)
    if axis == "y":
        return x * cosine + z * sine, y
    return x, y * cosine - z * sine


def _perimeter(t: float, width: float, height: float, shape: str) -> tuple[float, float, float, float]:
    """Position and outward normal on a counterclockwise perimeter."""
    if shape == "ellipse":
        phi = 2 * math.pi * t
        x, y = width / 2 * math.cos(phi), height / 2 * math.sin(phi)
        nx, ny = math.cos(phi) / width, math.sin(phi) / height
        length = math.hypot(nx, ny)
        return x, y, nx / length, ny / length
    t = (t % 1) * 4
    if t < 1:
        return width / 2, -height / 2 + t * height, 1, 0
    if t < 2:
        return width / 2 - (t - 1) * width, height / 2, 0, 1
    if t < 3:
        return -width / 2, height / 2 - (t - 2) * height, -1, 0
    return -width / 2 + (t - 3) * width, -height / 2, 0, -1


def _rim_samples(opts: TurnOptions, width: float, height: float, profile: dict | None = None) -> list[tuple]:
    """XY boundaries, physical outward normal and U endpoints for every rim."""
    if opts.shape != "polygon":
        result = []
        for index in range(opts.segments):
            u0, u1 = index / opts.segments, (index + 1) / opts.segments
            x0, y0, _, _ = _perimeter(u0, width, height, opts.shape)
            x1, y1, _, _ = _perimeter(u1, width, height, opts.shape)
            _, _, nx, ny = _perimeter((u0 + u1) / 2, width, height, opts.shape)
            result.append((x0, y0, x1, y1, nx, ny, u0, u1))
        return result
    if not opts.contour_points:
        raise ValueError("Polygon contour is unresolved; call resolve_options after prepare_images")
    from spine_turn_contour import build_polygon_perimeter
    corners = [(point[0] * width, point[1] * height) for point in opts.contour_points]
    if profile and profile.get("mode") == "manual":
        # Radial joins on the outer boundary are real shared vertices. Keep
        # them even when they are collinear with an original polygon edge.
        corners = profile["outer"]
        lengths = [math.dist(a, b) for a, b in zip(corners, corners[1:] + corners[:1])]
        extra_count = max(0, opts.segments - len(corners))
        weighted = [extra_count * length / sum(lengths) for length in lengths]
        counts = [1 + math.floor(value) for value in weighted]
        remainder = max(len(corners), opts.segments) - sum(counts)
        ranking = sorted(range(len(corners)), key=lambda index: (weighted[index] % 1, lengths[index], -index), reverse=True)
        for index in ranking[:remainder]:
            counts[index] += 1
        perimeter = []
        for index, a in enumerate(corners):
            b = corners[(index + 1) % len(corners)]
            for subdivision in range(counts[index]):
                fraction = subdivision / counts[index]
                perimeter.append((a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction))
    else:
        perimeter = build_polygon_perimeter(corners, opts.segments)
    lengths = [math.dist(a, b) for a, b in zip(perimeter, perimeter[1:] + perimeter[:1])]
    total_length = sum(lengths)
    coordinates, distance = [], 0.0
    for length in lengths:
        coordinates.append(distance / total_length)
        distance += length
    coordinates.append(1.0)
    result = []
    for index, (a, b) in enumerate(zip(perimeter, perimeter[1:] + perimeter[:1])):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        result.append((*a, *b, dy / length, -dx / length, coordinates[index], coordinates[index + 1]))
    return result


def _inset_convex_polygon(points: list[tuple], distance: float) -> list[tuple]:
    """Intersect inward-offset supporting lines of a convex CCW polygon."""
    lines = []
    for a, b in zip(points, points[1:] + points[:1]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length <= 1e-10:
            raise ValueError("Polygon contains a zero-length edge")
        nx, ny = dy / length, -dx / length
        lines.append((nx, ny, nx * a[0] + ny * a[1] - distance))
    inner = []
    for index, (nx, ny, constant) in enumerate(lines):
        px, py, previous_constant = lines[index - 1]
        determinant = px * ny - py * nx
        if abs(determinant) <= 1e-10:
            x, y = points[index]
            vertex = (x - nx * distance, y - ny * distance)
        else:
            vertex = ((previous_constant * ny - py * constant) / determinant,
                      (px * constant - previous_constant * nx) / determinant)
        inner.append(vertex)
    extent = max(max(abs(value) for point in points for value in point), 1)
    tolerance = extent * 1e-7
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(inner, inner[1:] + inner[:1])) / 2
    valid = area > extent * extent * 1e-8
    for vertex in inner:
        valid = valid and all(nx * vertex[0] + ny * vertex[1] <= constant + tolerance
                              for nx, ny, constant in lines)
    for index, (a, b) in enumerate(zip(inner, inner[1:] + inner[:1])):
        outer_a, outer_b = points[index], points[(index + 1) % len(points)]
        valid = valid and ((b[0] - a[0]) * (outer_b[0] - outer_a[0]) +
                           (b[1] - a[1]) * (outer_b[1] - outer_a[1]) > tolerance ** 2)
    if not valid:
        raise ValueError("倒角寬度過大，會壓垮內側面；請降低倒角寬度。")
    return inner


def _rise_fraction(opts: TurnOptions) -> float:
    return 0.5 if opts.side_mode == "ridge" else opts.bevel_depth


def _bevel_profile(opts: TurnOptions, width: float, height: float, thickness: float) -> dict | None:
    if (opts.shape != "polygon" or
            (opts.bevel_width <= 0 and not opts.raised_contour_points and opts.side_mode != "ridge") or thickness <= 0):
        return None
    if opts.raised_contour_points:
        geometry = _manual_region_geometry(opts.contour_points, opts.raised_contour_points, float(width), float(height))
        depth = thickness * _rise_fraction(opts)
        return {**geometry, "cap_z": thickness / 2, "body_z": thickness / 2 - depth,
                "bevel_depth": depth, "mode": "manual"}
    outer = [(point[0] * width, point[1] * height) for point in opts.contour_points]
    if len(outer) < 3:
        raise ValueError("Polygon contour is unresolved; call resolve_options after prepare_images")
    if opts.side_mode == "ridge" and opts.bevel_width <= 0:
        distance = max(1.0, 0.07 * min(width, height))
        while True:
            try:
                inner = _inset_convex_polygon(outer, distance)
                break
            except ValueError:
                if distance <= 1.0:
                    raise ValueError("圖片外框過窄，無法建立封閉的石塊斜面。") from None
                distance = max(1.0, distance * 0.7)
    else:
        distance = opts.bevel_width * min(width, height)
        inner = _inset_convex_polygon(outer, distance)
    # Sample the bevel's outer edge from solid artwork just inside the alpha
    # fringe. Geometry stays on the original shared polygon edge. For a very
    # narrow bevel, avoid crossing the inner UV contour and reversing the UVs.
    uv_outer_inset = min(1.0, distance * 0.5)
    outer_uv_points = _inset_convex_polygon(outer, uv_outer_inset)
    bevel_depth = thickness * _rise_fraction(opts)
    return {"outer": outer, "inner": inner, "distance": distance,
            "cap_z": thickness / 2, "body_z": thickness / 2 - bevel_depth,
            "bevel_depth": bevel_depth, "outer_uv_points": outer_uv_points,
            "uv_outer_inset_px": uv_outer_inset}


def _polygon_centroid(points: list[tuple]) -> tuple:
    twice_area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:] + points[:1]))
    x = y = 0.0
    for a, b in zip(points, points[1:] + points[:1]):
        weight = a[0] * b[1] - b[0] * a[1]
        x += (a[0] + b[0]) * weight
        y += (a[1] + b[1]) * weight
    return x / (3 * twice_area), y / (3 * twice_area)


def _ray_boundary(points: list[tuple], center: tuple, angle: float) -> tuple:
    for point in points:
        point_angle = math.atan2(point[1] - center[1], point[0] - center[0]) % (2 * math.pi)
        delta = abs(point_angle - angle)
        if min(delta, 2 * math.pi - delta) <= 1e-10:
            return point
    direction = (math.cos(angle), math.sin(angle))
    maximum = math.inf
    for a, b in zip(points, points[1:] + points[:1]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        nx, ny = dy / length, -dx / length
        denominator = nx * direction[0] + ny * direction[1]
        if denominator > 1e-12:
            distance = (nx * (a[0] - center[0]) + ny * (a[1] - center[1])) / denominator
            maximum = min(maximum, distance)
    if not math.isfinite(maximum) or maximum <= 0:
        raise ValueError("凸起區域無法與圖片外框連接，請調整頂點位置。")
    return center[0] + maximum * direction[0], center[1] + maximum * direction[1]


def _normal_coefficients(xy: list[tuple], roles: tuple, sign: int) -> tuple:
    model = [(x, y, sign * (1 if role == "inner" else 0)) for (x, y), role in zip(xy, roles)]
    a, b, c = model
    first = tuple(b[index] - a[index] for index in range(3))
    second = tuple(c[index] - a[index] for index in range(3))
    normal = (first[1] * second[2] - first[2] * second[1],
              first[2] * second[0] - first[0] * second[2],
              first[0] * second[1] - first[1] * second[0])
    return tuple(sign * value for value in normal)


@lru_cache(maxsize=128)
def _manual_region_geometry(outer_points: tuple, inner_points: tuple,
                             width: float, height: float) -> dict:
    canonical_inner = validate_raised_region(outer_points, inner_points, width, height)
    original_outer = [(x * width, y * height) for x, y in outer_points]
    original_inner = [(x * width, y * height) for x, y in canonical_inner]
    center = _polygon_centroid(original_inner)
    angles = sorted(math.atan2(y - center[1], x - center[0]) % (2 * math.pi)
                    for x, y in original_outer + original_inner)
    unique_angles = []
    for angle in angles:
        if not unique_angles or angle - unique_angles[-1] > 1e-10:
            unique_angles.append(angle)
    if len(unique_angles) > 1 and 2 * math.pi - unique_angles[-1] + unique_angles[0] <= 1e-10:
        unique_angles.pop()
    # Keep the existing edge-texture seam anchored at the original first
    # outer corner instead of moving it when the raised region is edited.
    first_angle = math.atan2(original_outer[0][1] - center[1], original_outer[0][0] - center[0]) % (2 * math.pi)
    first_index = min(range(len(unique_angles)), key=lambda index: abs(math.atan2(
        math.sin(unique_angles[index] - first_angle), math.cos(unique_angles[index] - first_angle))))
    unique_angles = unique_angles[first_index:] + unique_angles[:first_index]
    outer = [_ray_boundary(original_outer, center, angle) for angle in unique_angles]
    inner = [_ray_boundary(original_inner, center, angle) for angle in unique_angles]
    minimum_gap = math.inf
    for a, b in zip(original_outer, original_outer[1:] + original_outer[:1]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        nx, ny = dy / length, -dx / length
        constant = nx * a[0] + ny * a[1]
        minimum_gap = min(minimum_gap, *(constant - nx * x - ny * y for x, y in original_inner))
    uv_inset = min(1.0, minimum_gap * 0.5)
    offset_polygon = _inset_convex_polygon(original_outer, uv_inset)
    outer_uv = [_ray_boundary(offset_polygon, center, angle) for angle in unique_angles]
    specs = []
    for path, sign in (("back", -1), ("front", 1)):
        for index in range(len(outer)):
            following = (index + 1) % len(outer)
            quad = [outer[index], outer[following], inner[following], inner[index]]
            quad_uv = [outer_uv[index], outer_uv[following], inner[following], inner[index]]
            for suffix, indices in (("a", (0, 1, 2)), ("b", (2, 3, 0))):
                xy = [quad[vertex] for vertex in indices]
                uv_xy = [quad_uv[vertex] for vertex in indices]
                roles = tuple("outer" if vertex < 2 else "inner" for vertex in indices)
                specs.append({"name": f"{path}_bevel_{index:03d}_{suffix}", "path": path,
                              "sign": sign, "xy": xy, "uv_xy": uv_xy, "roles": roles,
                              "normal_coefficients": _normal_coefficients(xy, roles, sign)})
    return {"outer": outer, "inner": inner, "center": center, "angles": unique_angles,
            "outer_original": original_outer, "inner_original": original_inner,
            "outer_uv_points": outer_uv, "uv_outer_inset_px": uv_inset,
            "minimum_region_gap_px": minimum_gap, "distance": minimum_gap,
            "surface_specs": specs}


def _normal_facing(normal: tuple, angle: float, axis: str) -> float:
    nx, ny, nz = normal
    return ((-nx if axis == "y" else ny) * math.sin(angle) + nz * math.cos(angle))


def _art_uv(x: float, y: float, width: float, height: float,
            opts: TurnOptions, sign: int) -> tuple:
    if sign < 0:
        if opts.axis == "y":
            x = -x
        else:
            y = -y
    return x / width + 0.5, 0.5 - y / height


def _bevel_surfaces(profile: dict, angle: float, visibility_angle: float,
                     opts: TurnOptions, width: float, height: float,
                     visibility_bevel_depth: float | None = None) -> list[dict]:
    if profile.get("mode") == "manual":
        return _manual_bevel_surfaces(profile, angle, visibility_angle, opts, width, height,
                                       visibility_bevel_depth)
    outer, inner = profile["outer"], profile["inner"]
    result = []
    for path, sign in (("back", -1), ("front", 1)):
        for index, (outer0, outer1, inner0, inner1) in enumerate(zip(
                outer, outer[1:] + outer[:1], inner, inner[1:] + inner[:1])):
            dx, dy = outer1[0] - outer0[0], outer1[1] - outer0[1]
            length = math.hypot(dx, dy)
            normal = (dy / length * profile["bevel_depth"],
                      -dx / length * profile["bevel_depth"], sign * profile["distance"])
            normal_length = math.sqrt(sum(value * value for value in normal))
            normal = tuple(value / normal_length for value in normal)
            visible_depth = profile["bevel_depth"] if visibility_bevel_depth is None else visibility_bevel_depth
            visibility_normal = (dy / length * visible_depth, -dx / length * visible_depth,
                                 sign * profile["distance"])
            model = [(outer0[0], outer0[1], sign * profile["body_z"]),
                     (outer1[0], outer1[1], sign * profile["body_z"]),
                     (inner1[0], inner1[1], sign * profile["cap_z"]),
                     (inner0[0], inner0[1], sign * profile["cap_z"])]
            vertices, uvs = [], []
            uv_outer = profile["outer_uv_points"]
            uv_points = [uv_outer[index], uv_outer[(index + 1) % len(uv_outer)], inner1, inner0]
            for (x, y, z), (uv_x, uv_y) in zip(model, uv_points):
                vertices.extend(_project(x, y, z, angle, opts.axis))
                uvs.extend(_art_uv(uv_x, uv_y, width, height, opts, sign))
            if opts.shade_edge or opts.shade_faces:
                facing_light = max(0, _normal_facing(normal, angle - math.radians(opts.light_angle), opts.axis))
                factor = opts.min_brightness + (1 - opts.min_brightness) * facing_light ** opts.shade_curve
                channel = max(0, min(255, round(255 * factor)))
                color = f"{channel:02x}" * 3 + "ff"
            else:
                color = "ffffffff"
            result.append({"name": f"{path}_bevel_{index:03d}", "kind": "bevel", "path": path,
                           "vertices": vertices, "uvs": uvs, "triangles": TRIANGLES.copy(),
                           "hull": 4, "visible": _normal_facing(visibility_normal, visibility_angle, opts.axis) > 0,
                           "normal": normal, "model_vertices": [value for vertex in model for value in vertex],
                           "color": color})
    for path, sign in (("back", -1), ("front", 1)):
        center = (sum(point[0] for point in inner) / len(inner),
                  sum(point[1] for point in inner) / len(inner))
        points = inner + [center]
        vertices, uvs = [], []
        for x, y in points:
            vertices.extend(_project(x, y, sign * profile["cap_z"], angle, opts.axis))
            uvs.extend(_art_uv(x, y, width, height, opts, sign))
        triangles = [value for index in range(len(inner))
                     for value in (index, (index + 1) % len(inner), len(inner))]
        if opts.shade_faces:
            light = max(0.0, math.cos(angle - math.radians(opts.light_angle)) * sign)
            factor = opts.min_brightness + (1 - opts.min_brightness) * light ** opts.shade_curve
            channel = max(0, min(255, round(255 * factor)))
            color = f"{channel:02x}" * 3 + "ff"
        else:
            color = "ffffffff"
        result.append({"name": path, "kind": path, "path": path,
                       "vertices": vertices, "uvs": uvs, "triangles": triangles,
                       "hull": len(inner), "visible": sign * math.cos(visibility_angle) > 0,
                       "normal": (0, 0, sign),
                       "model_vertices": [value for x, y in points for value in (x, y, sign * profile["cap_z"])],
                       "color": color})
    return result


def _manual_bevel_surfaces(profile: dict, angle: float, visibility_angle: float,
                            opts: TurnOptions, width: float, height: float,
                            visibility_bevel_depth: float | None = None) -> list[dict]:
    result = []
    visible_depth = profile["bevel_depth"] if visibility_bevel_depth is None else visibility_bevel_depth
    for spec in profile["surface_specs"]:
        cx, cy, cz = spec["normal_coefficients"]
        vector = (cx * profile["bevel_depth"], cy * profile["bevel_depth"], cz)
        length = math.sqrt(sum(value * value for value in vector))
        normal = tuple(value / length for value in vector)
        visibility_normal = (cx * visible_depth, cy * visible_depth, cz)
        model = [(x, y, spec["sign"] * (profile["cap_z"] if role == "inner" else profile["body_z"]))
                 for (x, y), role in zip(spec["xy"], spec["roles"])]
        vertices, uvs = [], []
        for (x, y, z), (uv_x, uv_y) in zip(model, spec["uv_xy"]):
            vertices.extend(_project(x, y, z, angle, opts.axis))
            uvs.extend(_art_uv(uv_x, uv_y, width, height, opts, spec["sign"]))
        if opts.shade_edge or opts.shade_faces:
            light = max(0, _normal_facing(normal, angle - math.radians(opts.light_angle), opts.axis))
            factor = opts.min_brightness + (1 - opts.min_brightness) * light ** opts.shade_curve
            channel = max(0, min(255, round(255 * factor)))
            color = f"{channel:02x}" * 3 + "ff"
        else:
            color = "ffffffff"
        result.append({"name": spec["name"], "kind": "bevel", "path": spec["path"],
                       "vertices": vertices, "uvs": uvs, "triangles": [0, 1, 2], "hull": 3,
                       "visible": _normal_facing(visibility_normal, visibility_angle, opts.axis) > 0,
                       "normal": normal, "model_vertices": [value for point in model for value in point],
                       "vertex_roles": spec["roles"], "region_mode": "manual", "color": color})
    inner, center = profile["inner"], profile["center"]
    for path, sign in (("back", -1), ("front", 1)):
        points = inner + [center]
        vertices, uvs = [], []
        for x, y in points:
            vertices.extend(_project(x, y, sign * profile["cap_z"], angle, opts.axis))
            uvs.extend(_art_uv(x, y, width, height, opts, sign))
        triangles = [value for index in range(len(inner))
                     for value in (index, (index + 1) % len(inner), len(inner))]
        if opts.shade_faces:
            light = max(0, math.cos(angle - math.radians(opts.light_angle)) * sign)
            factor = opts.min_brightness + (1 - opts.min_brightness) * light ** opts.shade_curve
            channel = max(0, min(255, round(255 * factor)))
            color = f"{channel:02x}" * 3 + "ff"
        else:
            color = "ffffffff"
        result.append({"name": path, "kind": path, "path": path,
                       "vertices": vertices, "uvs": uvs, "triangles": triangles,
                       "hull": len(inner), "visible": sign * math.cos(visibility_angle) > 0,
                       "normal": (0, 0, sign), "region_mode": "manual",
                       "model_vertices": [value for x, y in points for value in (x, y, sign * profile["cap_z"])],
                       "color": color})
    return result


def pose_at(angle_degrees: float, options: TurnOptions | dict | None = None,
            width: float | None = None, height: float | None = None,
            *, _depth_scale: float | None = None,
            _visibility_depth_scale: float | None = None,
            _effect_progress: float | None = None) -> list[dict[str, Any]]:
    """Return meshes in draw order, with world-up XY vertices and top-left UVs.

    Each mesh carries its own `triangles`. `visible` controls backface culling and `color`
    is a Spine RGBA hex string. The first/last pose at 0/360 is identical.
    """
    opts = _options(options)
    width, height = float(width or opts.width or 512), float(height or opts.height or 512)
    if opts.model == "diamond":
        from spine_turn_diamond import diamond_pose
        depth_scale = opts.z_scale if _depth_scale is None else _depth_scale
        meshes = diamond_pose(angle_degrees, opts, width, height, depth_scale, _visibility_depth_scale)
        if opts.diamond_shine_enabled or opts.diamond_sparkles_enabled:
            from spine_turn_diamond_fx import diamond_effect_surfaces
            meshes.extend(diamond_effect_surfaces(meshes, opts, angle_degrees, width, height))
        return meshes
    if opts.shape == 'irregular':
        from spine_turn_irregular import irregular_pose
        meshes = irregular_pose(angle_degrees, opts, width, height,
                                opts.z_scale if _depth_scale is None else _depth_scale)
        if coin_shine_active(opts):
            from spine_turn_coin_fx import coin_effect_surfaces
            meshes.extend(coin_effect_surfaces(meshes, opts,
                angle_degrees / 360 if _effect_progress is None else _effect_progress, width, height))
        return meshes
    angle = math.radians(angle_degrees % 360)
    # A microscopic lookahead makes attachment switches occur exactly at each
    # quarter turn, without a frame where both image faces are absent.
    visibility_angle = angle + 1e-9
    meshes: list[dict[str, Any]] = []
    half_depth = opts.thickness * (opts.z_scale if _depth_scale is None else _depth_scale) / 2
    profile = _bevel_profile(opts, width, height, half_depth * 2)
    body_half_depth = profile["body_z"] if profile else half_depth
    rim_samples = [] if opts.side_mode == "ridge" else _rim_samples(opts, width, height, profile)
    for index, (x0, y0, x1, y1, nx, ny, u0, u1) in enumerate(rim_samples):
        facing = (-nx if opts.axis == "y" else ny) * math.sin(visibility_angle)
        visible = facing > 0 and opts.thickness > 0
        vertices = []
        model = ((x0, y0, body_half_depth), (x1, y1, body_half_depth),
                 (x1, y1, -body_half_depth), (x0, y0, -body_half_depth))
        for x, y, z in model:
            vertices.extend(_project(x, y, z, angle, opts.axis))
        shade = 0.62 + 0.38 * max(0, facing) if opts.shade_edge else 1
        channel = min(255, round(255 * shade))
        meshes.append({"name": f"rim_{index:03d}", "kind": "edge", "path": "edge",
                       "vertices": vertices, "uvs": [u0, 0, u1, 0, u1, 1, u0, 1],
                       "visible": visible, "color": f"{channel:02x}" * 3 + "ff",
                       "triangles": TRIANGLES.copy(), "hull": 4,
                       "model_vertices": [value for vertex in model for value in vertex]})
    if profile:
        visibility_bevel_depth = (opts.thickness * _visibility_depth_scale * _rise_fraction(opts)
                                  if _visibility_depth_scale is not None else None)
        meshes.extend(_bevel_surfaces(profile, angle, visibility_angle, opts, width, height,
                                      visibility_bevel_depth))
        if coin_shine_active(opts):
            from spine_turn_coin_fx import coin_effect_surfaces
            meshes.extend(coin_effect_surfaces(meshes, opts, angle_degrees / 360 if _effect_progress is None else _effect_progress,
                                               width, height))
        return meshes
    for path, sign in (("back", -1), ("front", 1)):
        vertices = []
        for x, y in ((-width / 2, height / 2), (width / 2, height / 2),
                      (width / 2, -height / 2), (-width / 2, -height / 2)):
            if sign < 0:
                if opts.axis == "y":
                    x = -x
                else:
                    y = -y
            vertices.extend(_project(x, y, sign * half_depth, angle, opts.axis))
        if opts.shade_faces:
            facing_light = max(0.0, math.cos(angle - math.radians(opts.light_angle)) * sign)
            factor = opts.min_brightness + (1 - opts.min_brightness) * facing_light ** opts.shade_curve
            channel = max(0, min(255, round(255 * factor)))
            color = f"{channel:02x}" * 3 + "ff"
        else:
            color = "ffffffff"
        meshes.append({"name": path, "kind": path, "path": path,
                       "vertices": vertices, "uvs": FACE_UVS.copy(),
                       "visible": sign * math.cos(visibility_angle) > 0,
                       "color": color, "triangles": TRIANGLES.copy(), "hull": 4})
    if coin_shine_active(opts):
        from spine_turn_coin_fx import coin_effect_surfaces
        meshes.extend(coin_effect_surfaces(meshes, opts, angle_degrees / 360 if _effect_progress is None else _effect_progress,
                                           width, height))
    return meshes


def ordered_surfaces(surfaces):
    """Painter order for irregular geometry; legacy order is returned intact."""
    if any('draw_order' in surface for surface in surfaces):
        return sorted(surfaces, key=lambda surface: surface.get('draw_order', 0))
    return surfaces


def _rounded(values: list[float]) -> list[float]:
    return [round(value, 6) if abs(value) >= 0.0000005 else 0.0 for value in values]


def _canonical_vertices(mesh: dict[str, Any], width: float, height: float,
                        opts: TurnOptions) -> list[float]:
    if opts.model == "diamond" or mesh.get("kind") == "coin_fx" or mesh.get('irregular'):
        return mesh["vertices"].copy()
    if len(mesh["vertices"]) != 8:
        return mesh["vertices"].copy()
    if mesh["kind"] != "edge":
        return [-width / 2, height / 2, width / 2, height / 2,
                width / 2, -height / 2, -width / 2, -height / 2]
    # A nondegenerate setup mesh keeps the editor's UV tools usable. Runtime
    # deform keys then project the physical edge segment into its true pose.
    length = max(width, height) * math.pi / opts.segments
    depth = max(opts.thickness * opts.z_scale, 1)
    return [-length / 2, depth / 2, length / 2, depth / 2,
            length / 2, -depth / 2, -length / 2, -depth / 2]


def _angles(start: float, end: float, step: float) -> list[float]:
    count = math.ceil((end - start) / step)
    keys = {start + (end - start) * i / count for i in range(count + 1)}
    keys.update(float(a) for a in range(0, 361, 90) if start <= a <= end)
    return sorted(keys)


def _legacy_animation_angles(start: float, end: float, opts: TurnOptions) -> list[float]:
    keys = set(_angles(start, end, opts.key_step_degrees))
    if opts.z_bounce_enabled and opts.peak_z_scale != 1:
        keys.update(start + progress * (end - start) for progress in _z_key_progress(opts))
    return sorted(keys)


@lru_cache(maxsize=128)
def _cached_diamond_animation_angles(start: float, end: float, width: float, height: float,
                                     option_values: tuple) -> tuple[float, ...]:
    from spine_turn_diamond import diamond_geometry, view_normal
    opts = TurnOptions(**dict(option_values))
    effects_on = opts.diamond_shine_enabled or opts.diamond_sparkles_enabled
    step = min(opts.key_step_degrees, 3.0 if effects_on else 7.5)
    keys = set(_angles(start, end, step))
    if opts.z_bounce_enabled and opts.peak_z_scale != 1:
        keys.update(start + progress * (end - start) for progress in _z_key_progress(opts))
    scan = sorted(keys)
    envelope = _z_envelope_frames(opts) if opts.z_bounce_enabled else None
    coefficients = set()
    for spec in diamond_geometry(opts, width, height):
        normal = spec["normal_coefficients"]
        magnitude = math.sqrt(sum(value * value for value in normal))
        coefficients.add(tuple(value / magnitude for value in normal))
    for nx, ny, nz in coefficients:
        def facing(angle: float) -> float:
            progress = (angle - start) / (end - start)
            scale = _depth_at_resolved(progress, opts, envelope)["z_scale"]
            return view_normal((nx * scale, ny * scale, nz), angle, opts.axis, opts.diamond_view_tilt)[2]

        for first, second in zip(scan, scan[1:]):
            left_value, right_value = facing(first), facing(second)
            if abs(left_value) < 1e-11:
                keys.add(first)
            if abs(right_value) < 1e-11:
                keys.add(second)
            if left_value * right_value >= 0:
                continue
            left, right = first, second
            for _ in range(45):
                midpoint = (left + right) / 2
                value = facing(midpoint)
                if left_value * value <= 0:
                    right = midpoint
                else:
                    left, left_value = midpoint, value
            root = (left + right) / 2
            if all(abs(root - existing) > 1e-8 for existing in keys):
                keys.add(root)
    return tuple(sorted(keys))


@lru_cache(maxsize=128)
def _cached_bevel_animation_angles(start: float, end: float, width: float, height: float,
                                   option_values: tuple) -> tuple[float, ...]:
    opts = TurnOptions(**dict(option_values))
    profile = _bevel_profile(opts, width, height, opts.thickness * opts.z_scale)
    if not profile:
        return tuple(_legacy_animation_angles(start, end, opts))
    keys = set(_angles(start, end, min(7.5, opts.key_step_degrees / 2)))
    if opts.z_bounce_enabled and opts.peak_z_scale != 1:
        keys.update(start + progress * (end - start) for progress in _z_key_progress(opts))
    scan = sorted(keys)
    envelope_frames = _z_envelope_frames(opts) if opts.z_bounce_enabled else None
    if profile.get("mode") == "manual":
        coefficients = set()
        for spec in profile["surface_specs"]:
            normal = spec["normal_coefficients"]
            magnitude = math.sqrt(sum(value * value for value in normal))
            coefficients.add(tuple(value / magnitude for value in normal))
        for nx, ny, nz in coefficients:
            component = -nx if opts.axis == "y" else ny

            def facing(angle: float) -> float:
                progress = (angle - start) / (end - start)
                depth_scale = _depth_at_resolved(progress, opts, envelope_frames)["z_scale"]
                depth = opts.thickness * depth_scale * _rise_fraction(opts)
                radians = math.radians(angle)
                return component * depth * math.sin(radians) + nz * math.cos(radians)

            for first, second in zip(scan, scan[1:]):
                left_value, right_value = facing(first), facing(second)
                if abs(left_value) < 1e-11:
                    keys.add(first)
                if abs(right_value) < 1e-11:
                    keys.add(second)
                if left_value * right_value >= 0:
                    continue
                left, right = first, second
                for _ in range(45):
                    midpoint = (left + right) / 2
                    value = facing(midpoint)
                    if left_value * value <= 0:
                        right = midpoint
                    else:
                        left, left_value = midpoint, value
                root = (left + right) / 2
                if all(abs(root - existing) > 1e-8 for existing in keys):
                    keys.add(root)
        return tuple(sorted(keys))
    directions = set()
    outer = profile["outer"]
    for a, b in zip(outer, outer[1:] + outer[:1]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        component = -dy / length if opts.axis == "y" else -dx / length
        directions.add(round(component, 12))
    for component in directions:
        for sign in (-1, 1):
            def facing(angle: float) -> float:
                progress = (angle - start) / (end - start)
                depth_scale = _depth_at_resolved(progress, opts, envelope_frames)["z_scale"]
                depth = opts.thickness * depth_scale * _rise_fraction(opts)
                radians = math.radians(angle)
                return component * depth * math.sin(radians) + sign * profile["distance"] * math.cos(radians)

            for first, second in zip(scan, scan[1:]):
                left_value, right_value = facing(first), facing(second)
                if abs(left_value) < 1e-11:
                    keys.add(first)
                if abs(right_value) < 1e-11:
                    keys.add(second)
                if left_value * right_value >= 0:
                    continue
                left, right = first, second
                for _ in range(45):
                    midpoint = (left + right) / 2
                    value = facing(midpoint)
                    if left_value * value <= 0:
                        right = midpoint
                    else:
                        left, left_value = midpoint, value
                root = (left + right) / 2
                if all(abs(root - existing) > 1e-8 for existing in keys):
                    keys.add(root)
    return tuple(sorted(keys))


def _animation_angles(start: float, end: float, opts: TurnOptions,
                       width: float | None = None, height: float | None = None) -> list[float]:
    if opts.model == "diamond":
        width, height = float(width or opts.width or 512), float(height or opts.height or 512)
        option_values = tuple((field.name, getattr(opts, field.name)) for field in fields(TurnOptions))
        return list(_cached_diamond_animation_angles(start, end, width, height, option_values))
    if (opts.shape != "polygon" or
            (opts.bevel_width <= 0 and not opts.raised_contour_points and opts.side_mode != "ridge") or opts.thickness <= 0):
        keys = _legacy_animation_angles(start, end, opts)
    else:
        width, height = float(width or opts.width or 512), float(height or opts.height or 512)
        option_values = tuple((field.name, getattr(opts, field.name)) for field in fields(TurnOptions))
        keys = list(_cached_bevel_animation_angles(start, end, width, height, option_values))
    if coin_shine_active(opts):
        from spine_turn_coin_fx import shine_key_progress
        width, height = float(width or opts.width or 512), float(height or opts.height or 512)
        keys = sorted(set(keys) | {start + progress * (end-start) for progress in shine_key_progress(opts, width, height)})
    return keys


def _animation_projection(angle: float, start: float, end: float, opts: TurnOptions,
                          width: float | None, height: float | None) -> list[dict]:
    progress = (angle - start) / (end - start)
    if coin_shine_active(opts):
        # Opacity samples must not resample the original turn's cosine curve.
        # New keys lie on the existing authored parent segments exactly.
        plain = replace(opts, coin_shine_enabled=False)
        clip = {(0, 360): "rotate_loop", (0, 180): "flip_to_back", (180, 360): "flip_to_front"}[(start, end)]
        if angle in _animation_angles(start, end, plain, width, height):
            # Preserve original critical-edge visibility and byte colors at
            # authored keys; progress round-trips can fall just before a key.
            thickness_scale = _depth_at_resolved(progress, plain)["z_scale"]
            lookahead = min(1.0, progress + math.degrees(1e-9) / (end-start))
            visibility_scale = _depth_at_resolved(lookahead, plain)["z_scale"]
            meshes = pose_at(angle, plain, width, height, _depth_scale=thickness_scale,
                             _visibility_depth_scale=visibility_scale)
        else:
            meshes = _animation_pose_plain(progress, plain, width, height, clip)
        from spine_turn_coin_fx import coin_effect_surfaces
        meshes.extend(coin_effect_surfaces(meshes, opts, progress,
                      float(width or opts.width or 512), float(height or opts.height or 512)))
        return meshes
    thickness_scale = _depth_at_resolved(progress, opts)["z_scale"]
    lookahead_progress = min(1.0, progress + math.degrees(1e-9) / (end - start))
    visibility_depth_scale = _depth_at_resolved(lookahead_progress, opts)["z_scale"]
    return pose_at(angle, opts, width, height, _depth_scale=thickness_scale,
                   _visibility_depth_scale=visibility_depth_scale, _effect_progress=progress)


_KEY_POSE_LOCK = threading.Lock()
_KEY_POSE_CACHE: list = []


def _key_pose(angle: float, start: float, end: float, opts: TurnOptions,
              width: float | None, height: float | None) -> list[dict]:
    """Authored key pose, remembered for irregular outlines.

    Neighbouring preview frames interpolate between the same two authored
    keys, and an irregular outline rebuilds hundreds of meshes per key. The
    cached lists are read-only for `_animation_pose_plain`; values are the
    unmodified `_animation_projection` results, so nothing changes numerically.
    """
    if opts.shape != "irregular" or opts.model == "diamond" or coin_shine_active(opts):
        return _animation_projection(angle, start, end, opts, width, height)
    key = (angle, start, end, width, height)
    with _KEY_POSE_LOCK:
        for entry in _KEY_POSE_CACHE:
            if entry[0] == key and (entry[1] is opts or entry[1] == opts):
                return entry[2]
    pose = _animation_projection(angle, start, end, opts, width, height)
    with _KEY_POSE_LOCK:
        _KEY_POSE_CACHE.insert(0, (key, replace(opts), pose))
        del _KEY_POSE_CACHE[6:]
    return pose


def _animation_pose_plain(progress: float, options: TurnOptions | dict | None = None,
                          width: float | None = None, height: float | None = None,
                          animation_name: str = "rotate_loop") -> list[dict[str, Any]]:
    """Evaluate the authored mesh/color interpolation, excluding bone motion.

    `pose_at` is the exact mathematical projection at any angle. This helper
    instead follows the sparse exported timeline between those projection
    keys, so playback and preview have the same geometry, culling and tint.
    `tint` preserves interpolated float color; `color` is its 8-bit equivalent.
    """
    opts = _options(options)
    if not math.isfinite(float(progress)):
        raise ValueError("progress must be finite")
    starts_ends = {"rotate_loop": (0, 360), "flip_to_back": (0, 180),
                   "flip_to_front": (180, 360)}
    if animation_name not in starts_ends:
        raise ValueError(f"Unknown animation: {animation_name}")
    start, end = starts_ends[animation_name]
    progress = max(0.0, min(1.0, float(progress)))
    angle = start + progress * (end - start)
    angles = _animation_angles(start, end, opts, width, height)
    if opts.model == "diamond":
        # Deform/attachment/color frame times are read into Float32 by all
        # supported runtimes. Match those exported times, not raw angles:
        # tiny culling/grid intervals can otherwise amplify hidden FX anchor
        # differences even though their opacity is essentially zero.
        duration = opts.duration if animation_name == "rotate_loop" else opts.duration / 2
        float32 = lambda value: struct.unpack("f", struct.pack("f", value))[0]
        times = [float32(round((value - start) / (end - start) * duration, 7)) for value in angles]
        time = progress * float32(round(duration, 7))
        index = max(0, min(len(times) - 1, bisect_right(times, time) - 1))
        following = min(index + 1, len(times) - 1)
        lower, upper = angles[index], angles[following]
        fraction = ((time - times[index]) / (times[following] - times[index])
                    if times[following] > times[index] else 0.0)
    else:
        lower, upper = angles[-1], angles[-1]
        for first, second in zip(angles, angles[1:]):
            if angle < second:
                lower, upper = first, second
                break
        fraction = (angle - lower) / (upper - lower) if upper > lower else 0.0
    first_pose = _key_pose(lower, start, end, opts, width, height)
    second_pose = first_pose if upper == lower else _key_pose(upper, start, end, opts, width, height)
    result = []
    for first, second in zip(first_pose, second_pose):
        surface = first.copy()
        surface["vertices"] = [a + (b - a) * fraction
                               for a, b in zip(first["vertices"], second["vertices"])]
        if surface.get('irregular'):
            depths = [a + (b-a)*fraction for a,b in zip(first['view_depths'],second['view_depths'])]
            radians = math.radians(angle)
            sine, cosine = math.sin(radians), math.cos(radians)
            model = []
            for x,y,z in zip(surface['vertices'][::2],surface['vertices'][1::2],depths):
                model.extend((x*cosine-z*sine,y,x*sine+z*cosine) if opts.axis=='y' else
                             (x,y*cosine+z*sine,-y*sine+z*cosine))
            surface['model_vertices'] = model
            surface['view_depths'] = depths
        colors = []
        for offset in (0, 2, 4, 6):
            a = int(first["color"][offset:offset + 2], 16)
            b = int(second["color"][offset:offset + 2], 16)
            colors.append(a + (b - a) * fraction)
        surface["tint"] = [channel / 255 for channel in colors]
        surface["color"] = "".join(f"{round(channel):02x}" for channel in colors)
        result.append(surface)
    return result


def animation_pose_at(progress: float, options: TurnOptions | dict | None = None,
                      width: float | None = None, height: float | None = None,
                      animation_name: str = "rotate_loop", *,
                      cull_hidden_effects: bool = False) -> list[dict[str, Any]]:
    """Evaluate exported light opacity while preserving the original turn.

    Enabling a light adds no change to parent geometry or source alpha. The
    opacity follows exported Float32 keys; each cell uses fixed weights on
    the unmodified authored parent at the requested progress.

    `cull_hidden_effects` is for rasterizers only: light cells that cannot
    contribute a pixel (hidden parent, or zero opacity at this time) are left
    out instead of being built. Every remaining surface is unchanged.
    """
    opts = _options(options)
    if not coin_shine_active(opts):
        return _animation_pose_plain(progress, opts, width, height, animation_name)
    plain = replace(opts, coin_shine_enabled=False)
    meshes = _animation_pose_plain(progress, plain, width, height, animation_name)
    progress = max(0.0, min(1.0, float(progress)))
    width, height = float(width or opts.width or 512), float(height or opts.height or 512)
    start, end = {"rotate_loop": (0, 360), "flip_to_back": (0, 180), "flip_to_front": (180, 360)}[animation_name]
    angles = _animation_angles(start, end, opts, width, height)
    duration = opts.duration if animation_name == "rotate_loop" else opts.duration / 2
    float32 = lambda value: struct.unpack("f", struct.pack("f", value))[0]
    times = [float32(round((angle-start)/(end-start)*duration, 7)) for angle in angles]
    time = progress * float32(round(duration, 7))
    index = max(0, min(len(times)-1, bisect_right(times, time)-1))
    following = min(index+1, len(times)-1)
    fraction = (time-times[index])/(times[following]-times[index]) if times[following] > times[index] else 0.
    first_progress, second_progress = ((angles[i]-start)/(end-start) for i in (index, following))
    from spine_turn_coin_fx import coin_effect_surfaces, sweep_alpha
    def key_alpha(coordinate):
        first = round(255*sweep_alpha(first_progress, coordinate, opts, width, height))
        second = round(255*sweep_alpha(second_progress, coordinate, opts, width, height))
        return first + (second-first)*fraction
    keep = (lambda coordinate: key_alpha(coordinate) > 0) if cull_hidden_effects else None
    effects = coin_effect_surfaces(meshes, opts, progress, width, height, keep)
    for surface in effects:
        alpha = key_alpha(surface["source_coordinate"])
        surface["tint"] = [1., 1., 1., alpha/255]
        surface["color"] = f"ffffff{round(alpha):02x}"
    meshes.extend(effects)
    return meshes


def _animation(start: float, end: float, duration: float, opts: TurnOptions,
               width: float, height: float, bases: dict[str, list]) -> dict:
    angles = _animation_angles(start, end, opts, width, height)
    geometry_angles = (set(_animation_angles(start, end, replace(opts, coin_shine_enabled=False), width, height))
                       if coin_shine_active(opts) else set(angles))
    meshes = [_animation_projection(angle, start, end, opts, width, height) for angle in angles]
    deform, slots = {}, {}
    for mesh_index, first_mesh in enumerate(meshes[0]):
        name = first_mesh["name"]
        timeline, attachment_keys, color_keys = [], [], []
        previous_visibility = None
        for angle, pose in zip(angles, meshes):
            mesh = pose[mesh_index]
            time = round((angle - start) / (end - start) * duration, 7)
            if angle in geometry_angles:
                timeline.append({"time": time,
                                 "vertices": _rounded([v - b for v, b in zip(mesh["vertices"], bases[name])])})
            if angle in geometry_angles and mesh["visible"] != previous_visibility:
                attachment_keys.append({"time": time, "name": name if mesh["visible"] else None})
                previous_visibility = mesh["visible"]
            if ((mesh["kind"] == "coin_fx" or angle in geometry_angles) and
                    (mesh["kind"] in ("edge", "bevel", "coin_fx") or opts.shade_faces or opts.model == "diamond")):
                color_keys.append({"time": time, "color": mesh["color"]})
        deform[name] = {name: timeline}
        slots[name] = {"attachment": attachment_keys}
        if color_keys:
            slots[name]["rgba"] = color_keys
    # The geometry track at the exact endpoint defines the animation duration
    # even when the last attachment change happened earlier in the loop.
    animation = {"deform": {"default": deform}, "slots": slots}
    if opts.shape == 'irregular' and opts.model == 'extrusion':
        base_order = list(bases)
        offsets, previous_order = [], None
        for angle, pose in zip(angles, meshes):
            order = [mesh['name'] for mesh in ordered_surfaces(pose)]
            if order != previous_order:
                positions = {name:index for index,name in enumerate(order)}
                offsets.append({'time':round((angle-start)/(end-start)*duration,7),
                                'offsets':[{'slot':name,'offset':positions[name]-index} for index,name in enumerate(base_order)]})
                previous_order = order
        animation['drawOrder'] = offsets
    bone_motion = _export_motion(duration, opts, height)
    if bone_motion:
        animation["bones"] = bone_motion
    return animation


def _build_canonical_skeleton(images: dict[str, Any], options: TurnOptions | dict | None = None) -> dict:
    opts = resolve_options(images, options)
    width, height = images["width"], images["height"]
    z_active = opts.z_bounce_enabled or opts.z_offset != 0
    setup_pose = pose_at(0, opts, width, height)
    bases = {mesh["name"]: _canonical_vertices(mesh, width, height, opts) for mesh in setup_pose}
    slots, attachments = [], {}
    for mesh in setup_pose:
        name = mesh["name"]
        slot = {"name": name, "bone": ("spin" if opts.z_spin_enabled else "depth" if z_active else "turn"),
                "color": mesh["color"]}
        if mesh["visible"] and mesh["kind"] != "edge":
            slot["attachment"] = name
        slots.append(slot)
        image = images[mesh["path"]]
        hull = mesh.get("hull", 4)
        edges = [value for index in range(hull) for value in (index * 2, ((index + 1) % hull) * 2)]
        attachments[name] = {name: {"type": "mesh", "path": mesh["path"],
                                   "uvs": mesh["uvs"], "triangles": mesh.get("triangles", TRIANGLES).copy(),
                                   "vertices": bases[name], "hull": hull,
                                   "edges": edges,
                                   "width": image.width, "height": image.height}}
    # Set up faces at their true initial projection; the hidden side pieces are
    # canonical, editable rectangles until an animation is applied.
    for mesh in setup_pose:
        if mesh["kind"] != "edge":
            bases[mesh["name"]] = _rounded(mesh["vertices"])
            attachments[mesh["name"]][mesh["name"]]["vertices"] = bases[mesh["name"]]
    if opts.bounce_enabled:
        anticipation = min(0.06, opts.landing_squash * 0.5)
        max_scale_x = opts.base_scale * max(1 + opts.landing_squash, opts.peak_scale)
        max_scale_y = opts.base_scale * max(1 + anticipation, 1 + opts.landing_squash * 0.3,
                                          opts.peak_scale)
        jump_height = opts.bounce_height
    else:
        max_scale_x = max_scale_y = opts.base_scale
        jump_height = 0
    maximum_thickness = opts.thickness * opts.z_scale * (
        max(1, opts.peak_z_scale) if opts.z_bounce_enabled else 1)
    # Conservative bounds include every turn angle and the full jump. Root
    # remains at the artwork's initial center, with the ground below it.
    minimum_x = -(width + maximum_thickness) * max_scale_x / 2
    minimum_y = -height * opts.base_scale / 2 - maximum_thickness * max_scale_y / 2
    maximum_y = (jump_height + height * (max_scale_y - opts.base_scale) / 2
                 + (height + maximum_thickness) * max_scale_y / 2)
    if z_active:
        # A cubic lies in the convex hull of its values/handles. These ranges
        # therefore include perspective magnification without relying on an
        # idealized depth formula between the sparse exported motion keys.
        ranges = {}
        for channel, frames in _motion_tracks(opts, height).items():
            values = [frame["value"] for frame in frames]
            values.extend(value for frame in frames if "curve" in frame
                          for value in (frame["curve"][1], frame["curve"][3]))
            ranges[channel] = (min(values), max(values))
        projection_frames = _projection_track(opts)
        projection_values = [frame["value"] for frame in projection_frames]
        projection_values.extend(value for frame in projection_frames if "curve" in frame
                                 for value in (frame["curve"][1], frame["curve"][3]))
        maximum_projection = max(projection_values)
        maximum_scale_x = ranges["scalex"][1] * maximum_projection
        maximum_scale_y = ranges["scaley"][1] * maximum_projection
        minimum_x = -(width + maximum_thickness) * maximum_scale_x / 2
        minimum_y = ranges["translatey"][0] - (height + maximum_thickness) * maximum_scale_y / 2
        maximum_y = ranges["translatey"][1] + (height + maximum_thickness) * maximum_scale_y / 2
    bones = [{"name": "root"}, {"name": "turn", "parent": "root"}]
    if z_active:
        bones.append({"name": "depth", "parent": "turn"})
    if opts.z_spin_enabled:
        bones.append({"name": "spin", "parent": "depth" if z_active else "turn"})
    if opts.model == "diamond":
        from spine_turn_diamond import diamond_geometry
        center = opts.diamond_center_x * width
        maximum_depth_scale = opts.z_scale * (max(1, opts.peak_z_scale) if opts.z_bounce_enabled else 1)
        radius = max(math.sqrt((x - center) ** 2 + y ** 2 + (z * maximum_depth_scale) ** 2)
                     for spec in diamond_geometry(opts, width, height) for x, y, z in spec["model"])
        ranges = {}
        for channel, frames in _motion_tracks(opts, height).items():
            values = [frame["value"] for frame in frames]
            values.extend(value for frame in frames if "curve" in frame for value in (frame["curve"][1], frame["curve"][3]))
            ranges[channel] = (min(values), max(values))
        projection_frames = _projection_track(opts)
        projection_values = [frame["value"] for frame in projection_frames]
        projection_values.extend(value for frame in projection_frames if "curve" in frame for value in (frame["curve"][1], frame["curve"][3]))
        projection = max(projection_values)
        margin = max(width, height) * .08 if opts.diamond_sparkles_enabled else 0
        minimum_x = -(abs(center) + radius + margin) * ranges["scalex"][1] * projection
        minimum_y = ranges["translatey"][0] - (radius + margin) * ranges["scaley"][1] * projection
        maximum_y = ranges["translatey"][1] + (radius + margin) * ranges["scaley"][1] * projection
    if opts.z_spin_enabled:
        bounds = z_spin_bounds(opts, width, height)
        minimum_x, minimum_y, maximum_y = bounds["left"], bounds["bottom"], bounds["top"]
    return {
        "skeleton": {"spine": SPINE_VERSION, "x": minimum_x,
                     "y": minimum_y,
                     "width": -2 * minimum_x, "height": maximum_y - minimum_y,
                     "images": "./images/", "audio": "", "fps": 30},
        "bones": bones,
        "slots": slots,
        "skins": [{"name": "default", "attachments": attachments}],
        "animations": {
            "rotate_loop": _animation(0, 360, opts.duration, opts, width, height, bases),
            "flip_to_back": _animation(0, 180, opts.duration / 2, opts, width, height, bases),
            "flip_to_front": _animation(180, 360, opts.duration / 2, opts, width, height, bases),
        },
    }


def build_skeleton(images: dict[str, Any], options: TurnOptions | dict | None = None) -> dict:
    """Build the real selected-family schema from the stable 4.0 authoring model."""
    opts = _options(options)
    canonical = _build_canonical_skeleton(images, opts)
    if (opts.model == "diamond" or coin_shine_active(opts) or opts.z_spin_enabled) and spine_family(opts.spine_version) == "4.0":
        # Tightly sampled effect timelines can amplify even a single Float32
        # frame/time ULP. Power-of-two FPS avoids that rounding
        # round-trip while still rejecting the editor's near-frame snap zone.
        times = animation_key_times(canonical)
        chosen = None
        for fps in (32, 64, 128):
            if all(abs(time * fps - round(time * fps)) <= 1e-5 or
                   abs(time * fps - round(time * fps)) >= .011 for time in times):
                chosen = fps
                break
        canonical["skeleton"]["fps"] = chosen or select_native_safe_fps(canonical, opts.spine_version)
    return convert_skeleton(canonical, opts.spine_version)


def _pack_atlas(images: dict[str, Any], output: Path, name: str,
                 spine_version: str = SPINE_VERSION) -> tuple[Path, Path]:
    padding = 4
    roles = ["front", "back", "edge", *images.get("generated_texture_names", [])]
    # Three regions in a shelf avoids texture-packer dependencies and rotation.
    max_width = max(images[key].width for key in roles) + padding * 2
    height = sum(images[key].height + padding * 2 for key in roles)
    page = Image.new("RGBA", (max_width, height))
    text = [f"{name}.png", f"size: {page.width},{page.height}", "format: RGBA8888",
            "filter: Linear,Linear", "repeat: none"]
    if spine_family(spine_version) != "3.8":
        text.append("pma: false")
    y = padding
    for key in roles:
        image = images[key]
        x = padding
        page.paste(image, (x, y))
        # Extrude the boundary to keep atlas filtering off neighboring regions.
        for distance in range(1, padding + 1):
            page.paste(image.crop((0, 0, 1, image.height)), (x - distance, y))
            page.paste(image.crop((image.width - 1, 0, image.width, image.height)), (x + image.width - 1 + distance, y))
            page.paste(image.crop((0, 0, image.width, 1)), (x, y - distance))
            page.paste(image.crop((0, image.height - 1, image.width, image.height)), (x, y + image.height - 1 + distance))
        text.extend([key, "  rotate: false", f"  xy: {x}, {y}",
                     f"  size: {image.width}, {image.height}",
                     f"  orig: {image.width}, {image.height}", "  offset: 0, 0", "  index: -1"])
        y += image.height + padding * 2
    atlas_path, page_path = output / f"{name}.atlas", output / f"{name}.png"
    atlas_path.write_text("\n".join(text) + "\n", encoding="utf-8")
    page.save(page_path)
    return atlas_path, page_path


def build_package(front_path: str | Path, back_path: str | Path | None,
                  edge_path: str | Path | None, output_dir: str | Path,
                  options: TurnOptions | dict | None = None) -> dict[str, Any]:
    """Write JSON, relative-path artwork, an atlas, and an honest manifest."""
    opts = _options(options)
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^\w\-]+", "_", opts.name, flags=re.UNICODE).strip("._") or "coin"
    if len(name) > 80:
        name = name[:80]
    images = prepare_images(front_path, back_path, edge_path, opts)
    opts = resolve_options(images, opts)
    images_dir = output / "images"
    images_dir.mkdir(exist_ok=True)
    for key in ("front", "back", "edge", *images.get("generated_texture_names", [])):
        images[key].save(images_dir / f"{key}.png")
    skeleton = build_skeleton(images, opts)
    json_path = output / f"{name}.json"
    json_path.write_text(json.dumps(skeleton, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    atlas_path, page_path = _pack_atlas(images, output, name, opts.spine_version)
    bevel_profile = (None if opts.model == "diamond" else
                     _bevel_profile(opts, images["width"], images["height"], opts.thickness * opts.z_scale))
    diamond_base_count = 0
    if opts.model == "diamond":
        from spine_turn_diamond import diamond_geometry
        diamond_base_count = len(diamond_geometry(opts, images["width"], images["height"]))
    manifest = {
        "format": "spine-turn-tool-package-v1.10", "spine_version": opts.spine_version,
        "model": opts.model,
        "spine_family": spine_family(opts.spine_version),
        "canonical_authoring_version": SPINE_VERSION,
        "authoring_fps": skeleton["skeleton"].get("fps", 30),
        "authoring_fps_policy": (f"Native-safe {spine_family(opts.spine_version)} frame labels selected without changing any key time, duration, curve or geometry"
                                 if opts.model == "diamond" or coin_shine_active(opts) or opts.z_spin_enabled or spine_family(opts.spine_version) in ("3.8", "4.2")
                                 else "Canonical authoring FPS retained"),
        "format_conversion": {"3.8": "Combined XY timelines, color timelines and normalized numeric Bezier controls; legacy-compatible atlas header",
                              "4.0": "Canonical native schema; no conversion",
                              "4.2": "Per-attachment deform timeline nesting; native 4.x bone/color curves retained"}[spine_family(opts.spine_version)],
        "native_project_created": False,
        "generator": "native unweighted mesh + deform and attachment timelines",
        "options": asdict(opts), "width": images["width"], "height": images["height"],
        "animations": {key: {"duration": opts.duration if key == "rotate_loop" else opts.duration / 2,
                             "loop": key == "rotate_loop",
                             "timing_seconds": {
                                 field: getattr(opts, field) * (opts.duration if key == "rotate_loop" else opts.duration / 2)
                                 for field in ("bounce_start", "bounce_apex", "bounce_land", "bounce_end",
                                               "z_bounce_start", "z_bounce_apex", "z_bounce_end")}}
                       for key in skeleton["animations"]},
        "pivot": [0, 0], "projection": "orthographic with optional uniform virtual-Z magnification", "axis": opts.axis,
        "side_mode": opts.side_mode,
        "side_geometry": {"mode": opts.side_mode,
                          "active": opts.model != "diamond",
                          "body_wall_enabled": opts.side_mode == "strip",
                          "edge_texture_used": any(slot["name"].startswith("rim_") for slot in skeleton["slots"]),
                          "effective_height_fraction_per_end": _rise_fraction(opts),
                          "stored_height_fraction_per_end": opts.bevel_depth,
                          "total_thickness_pixels": opts.thickness * opts.z_scale,
                          "outer_meeting_z": 0.0 if opts.side_mode == "ridge" else None,
                          "automatic_region_fallback": opts.side_mode == "ridge" and opts.bevel_width <= 0 and not opts.raised_contour_points,
                          "material_guide": ("Front and back artwork meet at a shared outer ridge; no side-strip material is drawn. Missing back artwork reuses the front."
                                             if opts.side_mode == "ridge" else "Side-strip artwork forms the central wall between front and back bevels.")},
        "edge_uv_convention": "U: counterclockwise circumference, V: front to back thickness",
        "irregular": {"active": opts.model == 'extrusion' and opts.shape == 'irregular',
                      "alpha_threshold": opts.outline_alpha_threshold, "simplification_tolerance_pixels": opts.outline_tolerance,
                      "analysis": images.get('irregular_analysis'), "statistics": images.get('irregular_statistics'),
                      "back_mode": images.get('back_mode', 'supplied' if back_path else 'reused_front'),
                      "back_auto_aligned": images.get('back_auto_aligned', False),
                      "geometry": "Axis-invariant slabs and noncrossing material intervals; welded connected rank components with true boundary-first topology",
                      "ordering": "Fixed slot names; per-cell lateral painter rank; standard Spine draw-order keys at half-turn boundaries",
                      "cap_alpha": "Original RGBA spans material and air intervals; air caps keep AA fringes without adding physical walls",
                      "physical_boundary_limit": "Walls follow the selected alpha threshold and simplified loops; soft fringes remain a visual approximation",
                      "back_input_requirement": "Missing backs and explicit decoded-RGBA duplicates mirror the processed front for Y turns or flip it for X turns; independent back artwork remains upright and should match the mirrored physical outline",
                      "unsupported": ["bevel", "raised region", "ridge stone"]},
        "coin_shine": {"active": coin_shine_active(opts), "strength": opts.coin_shine_strength,
                       "width_fraction_of_image_width": opts.coin_shine_width,
                       "width_definition": "Full finite support width of a raised-cosine band",
                       "angle_degrees_clockwise_from_vertical": opts.coin_shine_angle,
                       "start_progress_per_clip": opts.coin_shine_start, "end_progress_per_clip": opts.coin_shine_end,
                       "repeat_per_clip": opts.coin_shine_repeat,
                       "surfaces": "Flat front/back caps only; side walls, bevel slopes and Diamond are excluded",
                       "geometry": "32 fixed UV stripe positions per cap; irregular caps clip to actual connected triangle pieces; fixed parent weights preserve containment",
                       "alpha_guard": "White texture uses source A==255 eroded by one pixel; semitransparent edges and holes remain untouched",
                       "textures": [name for name in images.get("generated_texture_names", []) if name.startswith("coin-shine-")],
                       "blend": "normal", "shader_or_clipping_attachment": False},
        "edge_orientation": {
            "requested": opts.edge_orientation,
            "original": images["edge_original_orientation"],
            "resolved": images["edge_resolved_orientation"],
            "canonical": images["edge_canonical_orientation"],
            "source_size": images["edge_source_size"],
            "vertical_normalization": "counterclockwise 90 degrees; original top to bottom maps left to right",
        },
        "motion": {"bone": "turn", "root_fixed": True,
                   "base_scale": opts.base_scale,
                   "bounce_enabled": opts.bounce_enabled,
                   "peak_scale_semantics": "multiplier relative to base_scale",
                   "key_progress": [record[0] for record in _y_phase_data(opts)] if opts.bounce_enabled else [0, 1],
                   "depth_bone": "depth" if opts.z_bounce_enabled or opts.z_offset != 0 else None,
                   "depth_key_progress": (list(_z_key_progress(opts)) if opts.z_bounce_enabled and opts.z_bounce_depth != 0
                                          else [0, 1]),
                   "timeline_key_progress": list(motion_key_progress(opts)),
                   "anticipation_start": max(0, opts.bounce_start - (opts.bounce_apex - opts.bounce_start) / 4),
                   "airborne_start": opts.bounce_start,
                   "apex_progress": opts.bounce_apex, "landing_progress": opts.bounce_land,
                   "recovery_end": opts.bounce_end,
                   "squash_progress": (opts.bounce_land + 0.3 * (opts.bounce_end - opts.bounce_land)
                                       if opts.bounce_land < opts.bounce_end else None),
                   "ground_y": -images["height"] * opts.base_scale / 2 * depth_at(0, opts)["projection_scale"],
                   "ground_compensation": "Y y += height * (physical_scale_y-base_scale) / 2 * initial_projection",
                   "interpolation": ("Spine 3.8 normalized shared-XY Bezier timelines, nine interior samples"
                                     if spine_family(opts.spine_version) == "3.8"
                                     else "Spine 4.x absolute-control Bezier timelines, nine interior samples")},
        "virtual_z": {"z_scale": opts.z_scale, "peak_z_scale": opts.peak_z_scale,
                      "z_bounce_enabled": opts.z_bounce_enabled,
                      "z_bounce_depth": opts.z_bounce_depth, "z_offset": opts.z_offset,
                      "camera_distance": opts.camera_distance,
                      "independent_from_y": True,
                      "projection_formula": "camera_distance / (camera_distance-current_z)",
                      "projection_interpolation": "15 sparse Bezier keys approximate the ideal camera formula; a separate uniform child bone preserves independent Y proportions exactly",
                      "timing": {"start": opts.z_bounce_start, "apex": opts.z_bounce_apex, "end": opts.z_bounce_end},
                      "initial": depth_at(0, opts), "apex": depth_at(opts.z_bounce_apex, opts),
                      "representation": "Independent uniform depth child-bone scale; Y motion on parent turn bone; virtual thickness on mesh deform",
                      "perspective_limit": "This is a 2.5D approximation, not per-vertex perspective or native 3D Spine coordinates"},
        "lighting": {"shade_faces": opts.shade_faces, "shade_edge": opts.shade_edge,
                     "min_brightness": opts.min_brightness, "curve": opts.shade_curve,
                     "light_angle_degrees": opts.light_angle,
                     "face_formula": "min+(1-min)*max(0,cos(theta-light_angle)*face_sign)^curve",
                     "hue_preserved": True, "slot_alpha": 1},
        "animation_bounds": {key: skeleton["skeleton"][key]
                             for key in ("x", "y", "width", "height")},
        "contour": {"shape": opts.shape, "points": list(opts.contour_points),
                    "actual_rim_segments": sum(slot["name"].startswith("rim_") for slot in skeleton["slots"]),
                    "analysis": images.get("contour_analysis"),
                    "representation": "Convex CCW alpha outline with preserved polygon corners" if opts.shape == "polygon" else opts.shape},
        "bevel": {"enabled": bool(bevel_profile), "width_fraction": opts.bevel_width,
                  "region_mode": ("manual" if opts.raised_contour_points else "automatic") if bevel_profile else "off",
                  "width_pixels": opts.bevel_width * min(images["width"], images["height"]),
                  "effective_width_pixels": bevel_profile["distance"] if bevel_profile else 0.0,
                  "depth_fraction_per_end": _rise_fraction(opts),
                  "stored_depth_fraction_per_end": opts.bevel_depth,
                  "uv_outer_inset_px": bevel_profile["uv_outer_inset_px"] if bevel_profile else 0.0,
                  "uv_outer_inset_scope": "Only outer-boundary bevel UV vertices; cap UVs and physical geometry unchanged",
                  "body_thickness_fraction": 1 - 2 * _rise_fraction(opts),
                  "inner_points": ([[x / images["width"], y / images["height"]]
                                     for x, y in bevel_profile["inner"]] if bevel_profile else []),
                  "bevel_facets": sum("_bevel_" in slot["name"] for slot in skeleton["slots"]),
                  "texture_source": "Original front/back artwork; cap/inner UVs use physical XY, outer bevel UVs sample up to one pixel inward",
                  "visibility": "Rotated 3D facet normals; dynamic zero-crossing events are bisected and cached",
                  "cap_topology": "Inset convex hull vertices first; center last; triangle fan",
                  "geometry_keys": {key: len(_animation_angles(180 if key == "flip_to_front" else 0,
                                                               180 if key == "flip_to_back" else 360,
                                                               opts, images["width"], images["height"]))
                                    for key in skeleton["animations"]}},
        "raised_region": {"mode": "manual" if opts.raised_contour_points else "automatic",
                          "active": opts.model != "diamond",
                          "manual_points": list(opts.raised_contour_points),
                          "height_fraction_per_end": _rise_fraction(opts),
                          "height_pixels_per_end": opts.thickness * opts.z_scale * _rise_fraction(opts),
                          "outer_vertex_count": len(opts.contour_points),
                          "inner_input_vertex_count": len(opts.raised_contour_points),
                          "paired_sector_count": (len(bevel_profile["outer"]) if bevel_profile and bevel_profile.get("mode") == "manual" else None),
                          "center": ([bevel_profile["center"][0] / images["width"],
                                      bevel_profile["center"][1] / images["height"]]
                                     if bevel_profile and bevel_profile.get("mode") == "manual" else None),
                          "minimum_outer_gap_pixels": (bevel_profile["minimum_region_gap_px"]
                                                       if bevel_profile and bevel_profile.get("mode") == "manual" else None),
                          "paired_outer_points": ([[x / images["width"], y / images["height"]]
                                                    for x, y in bevel_profile["outer"]]
                                                   if bevel_profile and bevel_profile.get("mode") == "manual" else []),
                          "paired_inner_points": ([[x / images["width"], y / images["height"]]
                                                    for x, y in bevel_profile["inner"]]
                                                   if bevel_profile and bevel_profile.get("mode") == "manual" else []),
                          "representation": "Radial sector union retaining both outlines; independent planar triangle facets with true 3D normals",
                          "manual_overrides_automatic_width": bool(opts.raised_contour_points)},
        "diamond": {"active": opts.model == "diamond", "facets": opts.diamond_facets,
                    "guides": get_diamond_guides(images, opts) if opts.model == "diamond" else None,
                    "ring_alignment": ({"table_depth_fraction_of_width": opts.diamond_table_depth,
                                        "waist_depth_fraction_of_width": opts.diamond_waist_depth,
                                        "ring_phase_degrees": opts.diamond_ring_phase,
                                        "effective": get_diamond_alignment(opts, images["width"], images["height"])["effective"],
                                        "physical_crown": "Planar quads or independently culled true-normal triangles for nonplanar ring pairs",
                                        "editor_reference": "Actual 0-degree camera projection, including static Z thickness scale; waist handles use the upper waist rim"}
                                       if opts.model == "diamond" else None),
                    "girdle_height_fraction": opts.diamond_girdle_height,
                    "camera_tilt_degrees": opts.diamond_view_tilt,
                    "facet_shading_strength": opts.diamond_shading,
                    "geometry": "Closed parametric table/crown/girdle/pavilion lathe with one lower tip",
                    "view_order": "Rotate model around selected axis, then apply fixed camera-X tilt",
                    "source_projection": "Initial visible projection; unseen faces reuse a mirrored back/front source projection",
                    "uv_safety": "UV-only sampling inside source-alpha hull by one pixel; geometry remains parametric",
                    "base_surface_count": diamond_base_count,
                    "fx_surface_count": len(skeleton["slots"]) - diamond_base_count if opts.model == "diamond" else 0,
                    "generated_textures": list(images.get("generated_texture_names", [])),
                    "shine_enabled": opts.diamond_shine_enabled, "shine_strength": opts.diamond_shine_strength,
                    "cut_region_count": len(opts.diamond_cut_regions),
                    "cut_regions": [{"points": list(points), "reflection_yaw": yaw, "reflection_pitch": pitch}
                                    for points, yaw, pitch in opts.diamond_cut_regions],
                    "cut_region_model": "Artwork-aligned material patches; optical normal offsets change shading, physical normals and closed volume stay unchanged",
                    "sparkles_enabled": opts.diamond_sparkles_enabled, "sparkle_strength": opts.diamond_sparkle_strength},
        "back_reuses_front": images["back_reuses_front"],
        "edge_is_placeholder": images["edge_is_placeholder"],
        "crop_bounds": {"front": images["front_bounds"], "back": images["back_bounds"]},
        "limits": ["Supports flat elliptical, rectangular, convex polygonal, or opt-in concave alpha-extruded objects; not arbitrary 3D reconstruction.",
                   "Irregular mode supports concave loops, holes and islands using axis-specific painter order, without bevel or ridge geometry.",
                   "Alpha polygon mode uses a convex silhouette; concave outlines are approximated by their convex hull.",
                   "A manual raised region must be convex, contain 3 to 32 corners, and keep at least one image pixel from the outer boundary.",
                   "Virtual Z uses uniform center-distance magnification, not per-vertex perspective.",
                   "Front and back artwork should use matching silhouette and centering.",
                   "Mesh editing requires a Spine edition that supports meshes.",
                   "JSON is import data; a true .spine file must be saved by the native Spine editor/CLI."],
        "source_documentation": [
            "https://esotericsoftware.com/spine-import",
            "https://esotericsoftware.com/spine-command-line-interface",
            *FORMAT_SOURCES[spine_family(opts.spine_version)]],
        "files": {"skeleton": json_path.name, "atlas": atlas_path.name,
                  "atlas_page": page_path.name, "images": "images/"},
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"json_path": str(json_path), "atlas_path": str(atlas_path),
            "atlas_image_path": str(page_path), "images_dir": str(images_dir),
            "manifest_path": str(manifest_path), "animation_names": list(skeleton["animations"]),
            "width": images["width"], "height": images["height"],
            "output_dir": str(output)}
