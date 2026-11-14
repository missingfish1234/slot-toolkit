"""Artwork-aligned reflection regions on the closed Diamond surface.

The partitions change material normals, not the physical silhouette. Vertices
are clipped in the exact affine texture coordinates used by each source mesh.
"""
from __future__ import annotations

from functools import lru_cache
import math


def _cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _signed_area(points):
    return sum(a[0] * b[1] - a[1] * b[0]
               for a, b in zip(points, points[1:] + points[:1])) / 2


def _clip(points, a, b, inside=True):
    if not points:
        return []
    result = []
    before = points[-1]
    previous = _cross(a, b, before) * (1 if inside else -1)
    for after in points:
        current = _cross(a, b, after) * (1 if inside else -1)
        if (previous >= 0) != (current >= 0):
            ratio = previous / (previous - current)
            result.append(tuple(x + ratio * (y - x) for x, y in zip(before, after)))
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


def _intersection(first, second):
    result = list(first)
    for a, b in zip(second, second[1:] + second[:1]):
        result = _clip(result, a, b)
    return result


def validate_cut_regions(regions):
    """Return bounded, nonoverlapping convex regions in image-centred XY."""
    try:
        if len(regions) > 24:
            raise ValueError('最多可設定 24 個反光切面。')
        result = []
        for entry in regions:
            if len(entry) != 3:
                raise ValueError('每個切面需要範圍、左右朝向及上下朝向。')
            raw, yaw, pitch = entry
            points = tuple(tuple(float(v) for v in p) for p in raw)
            yaw, pitch = float(yaw), float(pitch)
            if len(points) > 1 and points[0] == points[-1]:
                points = points[:-1]
            if not 3 <= len(points) <= 12 or any(len(p) != 2 for p in points):
                raise ValueError('每個切面需由 3 到 12 個頂點組成。')
            if any(not math.isfinite(v) or abs(v) > .500001 for p in points for v in p):
                raise ValueError('切面頂點需位於圖片範圍內。')
            if not all(math.isfinite(v) and -60 <= v <= 60 for v in (yaw, pitch)):
                raise ValueError('反光朝向需介於 −60° 到 60°。')
            if _signed_area(points) < 0:
                points = tuple(reversed(points))
            if _signed_area(points) < 1e-7 or any(
                _cross(points[i - 1], points[i], points[(i + 1) % len(points)]) <= 1e-10
                for i in range(len(points))):
                raise ValueError('切面需為沒有交叉、沒有凹角的封閉區域。')
            # Every other vertex must lie on the interior side of every edge.
            if any(_cross(a, b, p) < -1e-10 for a, b in zip(points, points[1:] + points[:1])
                   for p in points):
                raise ValueError('切面線條不可交叉。')
            for previous, _, _ in result:
                overlap = _intersection(list(points), previous)
                if len(overlap) >= 3 and abs(_signed_area(overlap)) > 1e-9:
                    raise ValueError('反光切面不可重疊；相鄰切面可以共用邊線。')
            result.append((points, yaw, pitch))
        return tuple(result)
    except (TypeError, OverflowError, IndexError):
        raise ValueError('切面資料格式無效。') from None


def _partition(polygon, regions):
    remaining = [polygon]
    finished = []
    for number, (boundary, yaw, pitch) in enumerate(regions):
        rest = []
        for piece in remaining:
            overlap = _intersection(piece, boundary)
            if len(overlap) < 3 or abs(_signed_area(overlap)) < 1e-12:
                rest.append(piece)
                continue
            current = piece
            for a, b in zip(boundary, boundary[1:] + boundary[:1]):
                outside = _clip(current, a, b, False)
                if len(outside) >= 3 and abs(_signed_area(outside)) > 1e-12:
                    rest.append(outside)
                current = _clip(current, a, b)
            if len(current) >= 3 and abs(_signed_area(current)) > 1e-12:
                finished.append((current, number, yaw, pitch))
        remaining = rest
    return finished + [(piece, -1, 0., 0.) for piece in remaining]


def split_diamond_geometry(geometry, regions, width, height, tilt, static_z_scale=1,
                           front_boundary=(), back_boundary=(), allow_hidden_reuse=False,
                           material_center_x=None):
    if not regions:
        return geometry
    key = tuple((s['name'], s['zone'], tuple(s['model']), tuple(s['triangles']),
                 s['hull'], tuple(s['normal_coefficients'])) for s in geometry)
    return _split_cached(key, validate_cut_regions(regions), float(width), float(height),
                         float(tilt), float(static_z_scale), tuple(front_boundary), tuple(back_boundary),
                         bool(allow_hidden_reuse), None if material_center_x is None else float(material_center_x))


@lru_cache(maxsize=48)
def _split_cached(geometry, regions, width, height, tilt, scale, front, back, allow_hidden_reuse=False,
                  material_center_x=None):
    from spine_turn_diamond import _source_material_uvs
    patches = []
    xs = [p[0] for _, _, model, _, _, _ in geometry for p in model]
    center_x = (min(xs) + max(xs)) / 2 if material_center_x is None else material_center_x
    surfaces = tuple(dict(name=name, zone=zone, model=model, triangles=triangles,
                          hull=hull, normal_coefficients=normal)
                     for name, zone, model, triangles, hull, normal in geometry)
    for name, zone, model, triangles, hull, normal in geometry:
        surface = dict(name=name, zone=zone, model=model, normal_coefficients=normal)
        path, material_uvs = _source_material_uvs(surface, surfaces, width, height, tilt,
                                                 scale, center_x, front, back, allow_hidden_reuse=allow_hidden_reuse)
        uv = [(u - .5, .5 - v) for u, v in material_uvs]
        for start in range(0, len(triangles), 3):
            ids = triangles[start:start + 3]
            polygon = [(*uv[i], *model[i]) for i in ids]
            area = _signed_area(polygon)
            if abs(area) < 1e-12:
                # Degenerate source projection still carries physical volume.
                pieces = [(polygon, -1, 0., 0.)]
            else:
                if area < 0:
                    polygon.reverse()
                pieces = _partition(polygon, regions)
                if area < 0:
                    pieces = [(list(reversed(p)), number, yaw, pitch) for p, number, yaw, pitch in pieces]
            for polygon, number, yaw, pitch in pieces:
                patches.append({'source': name, 'zone': zone, 'polygon': polygon,
                    'normal_coefficients': normal, 'material_path': path,
                    'cut_region': number, 'cut_yaw': yaw, 'cut_pitch': pitch})
    # Insert intersection points along neighbouring edges too, so the shell
    # remains a conforming closed mesh even at a cut ending on a shared edge.
    vertices = {tuple(round(v, 8) for v in p[2:]): p[2:]
                for patch in patches for p in patch['polygon']}
    tolerance = max(width, height) * 2e-8
    result = []
    counters = {}
    for patch in patches:
        polygon = patch.pop('polygon')
        conformed = []
        for a, b in zip(polygon, polygon[1:] + polygon[:1]):
            delta = tuple(b[i] - a[i] for i in range(2, 5))
            square = sum(v * v for v in delta)
            values = [(0., a)]
            if square > tolerance * tolerance:
                for point in vertices.values():
                    t = sum((point[i] - a[i + 2]) * delta[i] for i in range(3)) / square
                    if 1e-8 < t < 1 - 1e-8 and math.dist(point, tuple(a[i + 2] + t * delta[i] for i in range(3))) < tolerance:
                        values.append((t, tuple(x + t * (y - x) for x, y in zip(a, b))))
            values.sort(key=lambda entry: entry[0])
            for _, point in values:
                if not conformed or math.dist(conformed[-1][2:], point[2:]) > tolerance:
                    conformed.append(point)
        if len(conformed) < 3:
            continue
        number = counters.get(patch['source'], 0)
        counters[patch['source']] = number + 1
        points = tuple(tuple(p[2:]) for p in conformed)
        # A centroid fan retains all collinear boundary subdivisions.
        center = tuple(sum(p[i] for p in conformed) / len(conformed) for i in range(5))
        count = len(points)
        result.append({**patch, 'name': f"{patch['source']}_cut_{number:03d}",
            'model': points + (tuple(center[2:]),), 'hull': count,
            'triangles': tuple(v for i in range(count) for v in (i, (i + 1) % count, count)),
            'material_uvs': tuple((p[0] + .5, .5 - p[1]) for p in conformed + [center])})
    return tuple(result)


def reflection_normal(normal, yaw, pitch, path='front'):
    """Facet-local normal offsets; both controls also work on the top table.

    The local horizontal tangent mirrors naturally on the rear hemisphere;
    the vertical tangent points towards the top of the source projection.
    Physical normals remain unchanged and continue to control culling.
    """
    x, y, z = normal
    length = math.hypot(x, z)
    horizontal = (z / length, 0., -x / length) if length > 1e-10 else (1., 0., 0.)
    a, b, c = horizontal
    vertical = (y*c-z*b, z*a-x*c, x*b-y*a)
    u, v = math.tan(math.radians(yaw)), math.tan(math.radians(pitch))
    vector = tuple(normal[i] + u * horizontal[i] + v * vertical[i] for i in range(3))
    magnitude = math.sqrt(sum(value*value for value in vector))
    return tuple(value / magnitude for value in vector)
