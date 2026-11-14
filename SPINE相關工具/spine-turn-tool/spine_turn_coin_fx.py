"""Shader-free, alpha-preserving light sweeps on flat front/back surfaces.

Each stripe is a fixed convex combination of its parent face vertices. Only
its opacity changes. This remains inside the parent during Spine's linear
deform interpolation, including edge-on turns and independent Y/Z motion.
"""
from __future__ import annotations

from functools import lru_cache
import math
from PIL import Image, ImageFilter, ImageOps


def _get(options, name, default):
    return options.get(name, default) if isinstance(options, dict) else getattr(options, name, default)


def coin_shine_active(options):
    return (_get(options, 'model', 'extrusion') == 'extrusion' and
            bool(_get(options, 'coin_shine_enabled', False)) and
            _get(options, 'coin_shine_strength', .4) > 0)


def make_effect_textures(prepared, options):
    """White masks are nonzero only within the source's opaque interior.

    One opaque-pixel guard protects bilinear filtering: wherever this mask
    contributes, all source samples are fully opaque. Normal blending cannot
    increase the original semi-transparent edge or fill transparent holes.
    """
    if not coin_shine_active(options):
        return {}
    result = {}
    for role in ('front', 'back'):
        source = prepared[role]
        mask = source.getchannel('A').point(lambda value: 255 if value == 255 else 0)
        # The image boundary is transparent too, including opaque cards whose
        # artwork touches every canvas edge. Padding prevents filter clamping
        # from accidentally leaving an unguarded bright border there.
        mask = ImageOps.expand(mask, border=1, fill=0).filter(ImageFilter.MinFilter(3))
        mask = mask.crop((1, 1, source.width+1, source.height+1))
        white = Image.new('RGBA', source.size, (255, 255, 255, 0))
        white.putalpha(mask)
        result[f'coin-shine-{role}'] = white
    return result


def _direction(angle):
    radians = math.radians(angle)
    # Positive angle tilts the vertical light band clockwise in image space.
    return math.cos(radians), -math.sin(radians)


def _dot(u, v, width, height, direction):
    return direction[0] * (u-.5) * width + direction[1] * (.5-v) * height


def _clip(polygon, limit, greater, width, height, direction):
    if not polygon:
        return []
    result, before = [], polygon[-1]
    previous = (_dot(before[0], before[1], width, height, direction) - limit) * (1 if greater else -1)
    for after in polygon:
        current = (_dot(after[0], after[1], width, height, direction) - limit) * (1 if greater else -1)
        if (previous >= 0) != (current >= 0):
            fraction = previous / (previous-current)
            result.append(tuple(a + (b-a)*fraction for a, b in zip(before, after)))
        if current >= 0:
            result.append(after)
        before, previous = after, current
    clean = []
    for point in result:
        if not clean or math.dist(point[:2], clean[-1][:2]) > 1e-11:
            clean.append(point)
    if len(clean) > 1 and math.dist(clean[0][:2], clean[-1][:2]) < 1e-11:
        clean.pop()
    return clean


@lru_cache(maxsize=128)
def _stripe_cells(uvs, hull, width, height, angle):
    count = len(uvs)//2
    hull = min(hull, count)
    polygon = [tuple(uvs[index*2:index*2+2]) + tuple(float(index == other) for other in range(count))
               for index in range(hull)]
    direction = _direction(angle)
    span = abs(direction[0])*width + abs(direction[1])*height
    result = []
    for index in range(32):
        lower, upper = -span/2 + span*index/32, -span/2 + span*(index+1)/32
        points = _clip(_clip(polygon, lower, True, width, height, direction), upper, False, width, height, direction)
        area = sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points, points[1:]+points[:1])) if points else 0
        if len(points) < 3 or abs(area) < 1e-12:
            continue
        center = tuple(sum(point[coordinate] for point in points)/len(points) for coordinate in range(2+count))
        vertices = points + [center]
        weights = tuple(tuple((i, value) for i, value in enumerate(point[2:]) if abs(value) > 1e-14) for point in vertices)
        cell_uvs = tuple(value for point in vertices for value in point[:2])
        triangles = tuple(value for i in range(len(points)) for value in (i, (i+1)%len(points), len(points)))
        q = _dot(center[0], center[1], width, height, direction)
        result.append((index, weights, cell_uvs, triangles, len(points), q))
    return tuple(result)


def sweep_alpha(progress, coordinate, options, width, height):
    start, end = _get(options, 'coin_shine_start', 0), _get(options, 'coin_shine_end', .25)
    if progress <= start or progress >= end:
        return 0.
    repeats = _get(options, 'coin_shine_repeat', 1)
    local = (progress-start)/(end-start)*repeats
    phase = local-math.floor(local)
    direction = _direction(_get(options, 'coin_shine_angle', -25))
    span = abs(direction[0])*width + abs(direction[1])*height
    half_width = _get(options, 'coin_shine_width', .5)*width/2
    center = -span/2-half_width + (span+2*half_width)*phase
    distance = abs(coordinate-center)/half_width
    if distance >= 1:
        return 0.
    return _get(options, 'coin_shine_strength', .4) * .5 * (1+math.cos(math.pi*distance))


def shine_key_progress(options, width, height):
    """Sparse opacity samples inside the scheduled sweep window only."""
    if not coin_shine_active(options):
        return ()
    direction = _direction(_get(options, 'coin_shine_angle', -25))
    span = abs(direction[0])*width + abs(direction[1])*height
    samples = min(64, max(12, math.ceil(4*(span+_get(options, 'coin_shine_width', .5)*width)/
                                         (_get(options, 'coin_shine_width', .5)*width))))
    samples += samples % 2
    start, end = _get(options, 'coin_shine_start', 0), _get(options, 'coin_shine_end', .25)
    repeat = _get(options, 'coin_shine_repeat', 1)
    return tuple(start+(end-start)*(cycle+index/samples)/repeat
                 for cycle in range(repeat) for index in range(samples+1))


def coin_effect_surfaces(base_surfaces, options, progress, width, height, keep=None):
    """Return at most 32 fixed-UV cells per flat cap, never side/bevel walls.

    `keep(source_coordinate)` is an optional rasterizer-only filter: cells of
    a hidden parent, or cells it rejects, are skipped before being built.
    """
    if not coin_shine_active(options):
        return []
    if _get(options, 'shape', 'ellipse') == 'irregular':
        from spine_turn_irregular import irregular_effect_surfaces
        return irregular_effect_surfaces(base_surfaces, options, progress, width, height, keep)
    result = []
    for surface in base_surfaces:
        if surface.get('kind') not in ('front', 'back'):
            continue
        source = surface['name']
        parent = list(zip(surface['vertices'][::2], surface['vertices'][1::2]))
        cells = _stripe_cells(tuple(surface['uvs']), surface.get('hull', 4), width, height,
                              _get(options, 'coin_shine_angle', -25))
        for index, weights, uvs, triangles, hull, coordinate in cells:
            if keep is not None and not (surface.get('visible', True) and keep(coordinate)):
                continue
            vertices = [sum(parent[i][axis]*weight for i,weight in vertex) for vertex in weights for axis in range(2)]
            alpha = sweep_alpha(progress, coordinate, options, width, height)
            result.append({'name':f'{source}_coin_shine_{index:02d}', 'kind':'coin_fx',
                'path':f'coin-shine-{surface["path"]}', 'vertices':vertices, 'uvs':list(uvs),
                'triangles':list(triangles), 'hull':hull, 'color':f'ffffff{round(alpha*255):02x}',
                'visible':surface.get('visible', True), 'source_face':source, 'effect':'light_sweep',
                'cell_weights':weights, 'source_coordinate':coordinate})
    return result
