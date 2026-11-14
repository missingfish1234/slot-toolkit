"""Convex alpha silhouettes and corner-preserving extrusion perimeters.

Normalized points use the supplied texture canvas: x/width-.5, .5-y/height.
Call after the artwork's final trim/resize so geometry and UVs share a center.
"""
from __future__ import annotations

import math
from PIL import Image


def _cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def signed_area(points):
    return sum(a[0] * b[1] - b[0] * a[1]
        for a, b in zip(points, points[1:] + points[:1])) / 2


def _hull(points):
    points = sorted(set(points))
    if len(points) < 3:
        raise ValueError('透明輪廓太小，無法建立多邊形。')
    lower, upper = [], []
    for target, sequence in ((lower, points), (upper, reversed(points))):
        for point in sequence:
            while len(target) >= 2 and _cross(target[-2], target[-1], point) <= 0:
                target.pop()
            target.append(point)
    return lower[:-1] + upper[:-1]


def _point_distance(point, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    if length2 == 0:
        return math.hypot(point[0] - a[0], point[1] - a[1])
    t = max(0., min(1., ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length2))
    return math.hypot(point[0] - a[0] - t * dx, point[1] - a[1] - t * dy)


def _rdp(points, tolerance):
    keep = {0, len(points) - 1}
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        if last <= first + 1:
            continue
        index, distance = max(((i, _point_distance(points[i], points[first], points[last]))
            for i in range(first + 1, last)), key=lambda pair: pair[1])
        if distance > tolerance:
            keep.add(index)
            stack.extend(((first, index), (index, last)))
    return [points[index] for index in sorted(keep)]


def _simplify(hull, tolerance, max_vertices):
    min_x, max_x = min(p[0] for p in hull), max(p[0] for p in hull)
    min_y, max_y = min(p[1] for p in hull), max(p[1] for p in hull)
    # Cardinal support edges preserve narrow top/bottom tabs. Strong corners
    # preserve an octagon's actual vertices instead of rounding it to an oval.
    anchors = set()
    for index, point in enumerate(hull):
        if point[0] in (min_x, max_x) or point[1] in (min_y, max_y):
            anchors.add(index)
        before, after = hull[index - 1], hull[(index + 1) % len(hull)]
        a = (point[0] - before[0], point[1] - before[1])
        b = (after[0] - point[0], after[1] - point[1])
        cosine = max(-1., min(1., (a[0] * b[0] + a[1] * b[1]) /
            (math.hypot(*a) * math.hypot(*b))))
        if math.degrees(math.acos(cosine)) >= 30 - 1e-9:
            anchors.add(index)
    if len(anchors) > max_vertices:
        raise ValueError('輪廓的重要轉角超過頂點上限，請提高頂點上限。')
    indices = sorted(anchors)
    used_tolerance = tolerance
    for _ in range(32):
        simplified = []
        for index, first in enumerate(indices):
            last = indices[(index + 1) % len(indices)]
            if last <= first:
                last += len(hull)
            chain = [hull[i % len(hull)] for i in range(first, last + 1)]
            simplified.extend(_rdp(chain, used_tolerance)[:-1])
        if len(simplified) <= max_vertices:
            return simplified, used_tolerance
        used_tolerance = max(.25, used_tolerance * 1.35)
    raise ValueError('無法在頂點上限內保留輪廓，請提高頂點上限。')


def analyze_convex_outline(image, *, alpha_threshold=16, simplify_tolerance=1.5,
                           max_vertices=20):
    """Return normalized convex points and metadata about the approximation.

    Concave gaps/holes are filled by a convex extrusion. `concavity_warning`
    reports a hull-vs-mask area difference of at least three percent.
    """
    if not isinstance(image, Image.Image) or 'A' not in image.getbands():
        raise ValueError('自動輪廓需要含透明背景的 RGBA 圖片；實心圖片請選擇矩形。')
    if isinstance(alpha_threshold, bool) or not isinstance(alpha_threshold, int) or not 1 <= alpha_threshold <= 255:
        raise ValueError('Alpha 門檻需為 1 到 255 的整數。')
    tolerance = float(simplify_tolerance)
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError('輪廓簡化誤差必須是非負有限數值。')
    if isinstance(max_vertices, bool) or not isinstance(max_vertices, int) or not 3 <= max_vertices <= 256:
        raise ValueError('輪廓頂點上限需為 3 到 256 的整數。')
    alpha = image.getchannel('A')
    mask = alpha.point(lambda value: 255 if value >= alpha_threshold else 0)
    bounds = mask.getbbox()
    if bounds is None:
        raise ValueError('圖片在 Alpha 門檻以上沒有可見輪廓。')
    count = mask.histogram()[255]
    if count == image.width * image.height:
        raise ValueError('圖片沒有透明背景可供判斷輪廓；實心圖片請選擇矩形。')
    if bounds[2] - bounds[0] < 2 or bounds[3] - bounds[1] < 2:
        raise ValueError('透明輪廓太小，無法建立多邊形。')
    # Only row extrema can appear on the convex hull. Pixel-cell corners keep
    # the true alpha bounds, avoiding an unintended half-pixel center shift.
    boundary = []
    for y in range(bounds[1], bounds[3]):
        row = mask.crop((bounds[0], y, bounds[2], y + 1)).getbbox()
        if row:
            left, right = bounds[0] + row[0], bounds[0] + row[2]
            boundary.extend(((left, y), (right, y), (right, y + 1), (left, y + 1)))
    hull = _hull(boundary)
    hull_area = abs(signed_area(hull))
    simplified, used_tolerance = _simplify(hull, tolerance, max_vertices)
    # World-up reverses image-space winding. Keep a deterministic first point.
    points = [(x / image.width - .5, .5 - y / image.height) for x, y in simplified]
    if signed_area(points) < 0:
        points.reverse()
    first = min(range(len(points)), key=lambda index: (points[index][0], -points[index][1]))
    points = points[first:] + points[:first]
    concavity_ratio = max(0., (hull_area - count) / hull_area)
    error = max(min(_point_distance(point, a, b)
        for a, b in zip(simplified, simplified[1:] + simplified[:1])) for point in hull)
    return {
        'points': points, 'is_convex': True,
        'concavity_warning': concavity_ratio >= .03,
        'concavity_ratio': concavity_ratio,
        'source_size': [image.width, image.height], 'source_alpha_bounds': list(bounds),
        'alpha_threshold': alpha_threshold, 'pixel_area': count, 'hull_area_px': hull_area,
        'hull_vertex_count': len(hull), 'vertex_count': len(points),
        'requested_tolerance_px': tolerance, 'used_tolerance_px': used_tolerance,
        'simplification_max_error_px': error,
    }


def convex_outline(image, *, alpha_threshold=16, simplify_tolerance=1.5, max_vertices=20):
    return analyze_convex_outline(image, alpha_threshold=alpha_threshold,
        simplify_tolerance=simplify_tolerance, max_vertices=max_vertices)['points']


def _polygon(points):
    polygon = [tuple(map(float, point)) for point in points]
    if len(polygon) > 1 and polygon[0] == polygon[-1]:
        polygon.pop()
    if len(polygon) < 3 or any(len(p) != 2 or not all(math.isfinite(v) for v in p) for p in polygon):
        raise ValueError('多邊形需要至少三個有效頂點。')
    if any(a == b for a, b in zip(polygon, polygon[1:] + polygon[:1])):
        raise ValueError('多邊形不可包含相鄰重複頂點。')
    area = signed_area(polygon)
    if abs(area) < 1e-12:
        raise ValueError('多邊形面積必須大於零。')
    if area < 0:
        polygon.reverse()
    if any(_cross(polygon[index - 1], point, polygon[(index + 1) % len(polygon)]) < -1e-10
        for index, point in enumerate(polygon)):
        raise ValueError('目前僅支援凸多邊形輪廓。')
    hull_area = abs(signed_area(_hull(polygon)))
    if abs(abs(area) - hull_area) > max(1e-10, hull_area * 1e-9):
        raise ValueError('目前僅支援沒有自交的凸多邊形輪廓。')
    return polygon


def build_polygon_perimeter(points, min_segments):
    """Densify convex CCW edges while retaining every original corner exactly."""
    polygon = _polygon(points)
    if isinstance(min_segments, bool) or not isinstance(min_segments, int) or not 3 <= min_segments <= 4096:
        raise ValueError('側邊分段數需為 3 到 4096 的整數。')
    lengths = [math.dist(a, b) for a, b in zip(polygon, polygon[1:] + polygon[:1])]
    total = sum(lengths)
    remaining = max(0, min_segments - len(polygon))
    extra = [remaining * length / total for length in lengths]
    counts = [1 + math.floor(value) for value in extra]
    remainder = max(len(polygon), min_segments) - sum(counts)
    ranking = sorted(range(len(polygon)), key=lambda i: (extra[i] % 1, lengths[i], -i), reverse=True)
    for index in ranking[:remainder]:
        counts[index] += 1
    result = []
    for index, a in enumerate(polygon):
        b = polygon[(index + 1) % len(polygon)]
        for subdivision in range(counts[index]):
            fraction = subdivision / counts[index]
            result.append((a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction))
    return result


def perimeter_uvs(points):
    """Arc-length U for each perimeter vertex; the closing endpoint uses U=1."""
    polygon = _polygon(points)
    lengths = [math.dist(a, b) for a, b in zip(polygon, polygon[1:] + polygon[:1])]
    total = sum(lengths)
    result, distance = [], 0.
    for length in lengths:
        result.append(distance / total)
        distance += length
    return result


# The irregular tracer is separate from the legacy convex path above. It never
# expands a concave silhouette to a hull or silently discards an island/hole.
def _irregular_strip_collinear(points):
    result = list(points)
    while len(result) >= 3:
        reduced = [point for index, point in enumerate(result)
                   if abs(_cross(result[index - 1], point, result[(index + 1) % len(result)])) > 1e-12]
        if len(reduced) == len(result):
            break
        result = reduced
    return result


def _irregular_split_walk(points):
    """Split a grid-corner touch into simple loops without moving any corner."""
    stack, positions, loops = [], {}, []
    for point in points + points[:1]:
        if point in positions:
            first = positions[point]
            cycle = _irregular_strip_collinear(stack[first:])
            if len(cycle) >= 3 and abs(signed_area(cycle)) > 1e-12:
                loops.append(cycle)
            for removed in stack[first + 1:]:
                positions.pop(removed, None)
            stack = stack[:first + 1]
        else:
            positions[point] = len(stack)
            stack.append(point)
    return loops


def _irregular_trace_grid(mask):
    import numpy as np
    padded = np.pad(mask, 1, constant_values=False)
    exposed = (
        mask & ~padded[:-2, 1:-1], mask & ~padded[1:-1, 2:],
        mask & ~padded[2:, 1:-1], mask & ~padded[1:-1, :-2],
    )
    edge_count = sum(int(np.count_nonzero(side)) for side in exposed)
    if edge_count > 1_000_000:
        raise ValueError('原圖邊界過於複雜，請先降低圖片尺寸或簡化細節；不會改用凸輪廓。')
    outgoing = {}
    for side, selected in enumerate(exposed):
        for y, x in zip(*np.nonzero(selected)):
            x, y = int(x), int(y)
            if side == 0:
                first, last = (x, y), (x + 1, y)
            elif side == 1:
                first, last = (x + 1, y), (x + 1, y + 1)
            elif side == 2:
                first, last = (x + 1, y + 1), (x, y + 1)
            else:
                first, last = (x, y + 1), (x, y)
            outgoing.setdefault(first, []).append(last)
    directions = {(1, 0): 0, (0, 1): 1, (-1, 0): 2, (0, -1): 3}
    visited, loops = set(), []
    # Clockwise image edges keep a selected pixel to the right. At diagonal
    # contacts the right turn follows that pixel, instead of making a bow tie.
    priority = {1: 0, 0: 1, 3: 2, 2: 3}
    for first in sorted(outgoing, key=lambda p: (p[1], p[0])):
        for last in sorted(outgoing[first], key=lambda p: (p[1], p[0])):
            start = first, last
            if start in visited:
                continue
            edge, walk = start, []
            while edge not in visited:
                visited.add(edge)
                a, b = edge
                walk.append(a)
                direction = directions[(b[0] - a[0], b[1] - a[1])]
                choices = outgoing.get(b, ())
                if not choices:
                    raise ValueError('輪廓邊界未封閉，無法建立實體外框。')
                target = min(choices, key=lambda point: priority[(directions[(point[0] - b[0], point[1] - b[1])] - direction) % 4])
                edge = b, target
            if edge != start:
                raise ValueError('輪廓邊界連接不一致，無法安全建立外框。')
            loops.extend(_irregular_split_walk(walk))
    return loops, edge_count


def _irregular_location(point, polygon, epsilon=1e-9):
    """Return -1 outside, 0 on boundary, 1 strictly inside a simple polygon."""
    x, y = point
    inside = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if abs(_cross(a, b, point)) <= epsilon and min(a[0], b[0]) - epsilon <= x <= max(a[0], b[0]) + epsilon and min(a[1], b[1]) - epsilon <= y <= max(a[1], b[1]) + epsilon:
            return 0
        if (a[1] > y) != (b[1] > y):
            intersection = a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if intersection > x:
                inside = not inside
    return 1 if inside else -1


def _irregular_probe(polygon):
    """Choose a strict interior point; a vertex average can lie in a U's gap."""
    low, high = min(p[1] for p in polygon), max(p[1] for p in polygon)
    ys = [low + (high - low) * (index + .5) / 17 for index in range(17)]
    ys.append((low + high) / 2)
    best, clearance = None, -1.
    for y in ys:
        xs = sorted(a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
                    for a, b in zip(polygon, polygon[1:] + polygon[:1]) if (a[1] > y) != (b[1] > y))
        for left, right in zip(xs[::2], xs[1::2]):
            point = (left + right) / 2, y
            if _irregular_location(point, polygon) != 1:
                continue
            distance = min(_point_distance(point, a, b) for a, b in zip(polygon, polygon[1:] + polygon[:1]))
            if distance > clearance:
                best, clearance = point, distance
    if best is None:
        raise ValueError('輪廓過薄或面積為零，無法建立封閉區域。')
    return best


def _irregular_parents(loops):
    areas = [abs(signed_area(loop)) for loop in loops]
    parents = []
    for index, loop in enumerate(loops):
        probe = _irregular_probe(loop)
        choices = [other for other, polygon in enumerate(loops)
                   if areas[other] > areas[index] + 1e-9 and _irregular_location(probe, polygon) == 1]
        parents.append(min(choices, key=lambda other: areas[other]) if choices else None)
    return parents


def _irregular_bad_intersection(a, b, c, d, allowed=()):
    epsilon = 1e-9
    if (max(a[0], b[0]) < min(c[0], d[0]) - epsilon or max(c[0], d[0]) < min(a[0], b[0]) - epsilon or
            max(a[1], b[1]) < min(c[1], d[1]) - epsilon or max(c[1], d[1]) < min(a[1], b[1]) - epsilon):
        return False
    first, second, third, fourth = _cross(a, b, c), _cross(a, b, d), _cross(c, d, a), _cross(c, d, b)
    if first * second < -epsilon and third * fourth < -epsilon:
        return True
    touches = []
    for point, start, end in ((a, c, d), (b, c, d), (c, a, b), (d, a, b)):
        if abs(_cross(start, end, point)) <= epsilon and min(start[0], end[0]) - epsilon <= point[0] <= max(start[0], end[0]) + epsilon and min(start[1], end[1]) - epsilon <= point[1] <= max(start[1], end[1]) + epsilon:
            if point not in touches:
                touches.append(point)
    if not touches:
        return False
    # A shared grid corner is permitted between loops; overlapping edges and
    # new contacts are never introduced by simplification.
    return len(touches) > 1 or any(point not in allowed for point in touches)


def _irregular_simplify_loop(points, tolerance, anchor_points):
    indices = sorted(index for index, point in enumerate(points) if point in anchor_points)
    if len(indices) < 2:
        indices = [0, len(points) // 2]
    result = []
    for number, first in enumerate(indices):
        last = indices[(number + 1) % len(indices)]
        if last <= first:
            last += len(points)
        chain = [points[index % len(points)] for index in range(first, last + 1)]
        result.extend(_rdp(chain, tolerance)[:-1])
    return result


def _irregular_valid(loops, signs, parents, shared, reflex):
    for number, polygon in enumerate(loops):
        if len(polygon) < 3 or len(set(polygon)) != len(polygon) or signed_area(polygon) * signs[number] <= 1e-9:
            return False
        lookup = {point: index for index, point in enumerate(polygon)}
        for point in reflex[number]:
            index = lookup.get(point)
            if index is None or _cross(polygon[index - 1], point, polygon[(index + 1) % len(polygon)]) * signs[number] >= -1e-9:
                return False
        edges = list(zip(polygon, polygon[1:] + polygon[:1]))
        for i, (a, b) in enumerate(edges):
            for j in range(i + 1, len(edges)):
                if j == i + 1 or (i == 0 and j == len(edges) - 1):
                    continue
                if _irregular_bad_intersection(a, b, *edges[j]):
                    return False
    for first in range(len(loops)):
        for second in range(first + 1, len(loops)):
            allowed = shared.get((first, second), ())
            for a, b in zip(loops[first], loops[first][1:] + loops[first][:1]):
                if any(_irregular_bad_intersection(a, b, c, d, allowed)
                       for c, d in zip(loops[second], loops[second][1:] + loops[second][:1])):
                    return False
    return _irregular_parents(loops) == parents


def analyze_irregular_outline(image, *, alpha_threshold=16, simplify_tolerance=1.0,
                              max_vertices=256):
    """Trace concave alpha loops, preserving islands, holes and their winding.

    Selected pixel cells are traced exactly before simplification. Output uses
    the original canvas centre: x/width-.5, .5-y/height. Outer loops are CCW and
    holes CW. Distinct loops may retain an original diagonal grid-corner touch;
    individual loops never self-intersect. No component is silently removed.
    """
    import numpy as np
    if not isinstance(image, Image.Image) or ('A' not in image.getbands() and 'transparency' not in image.info):
        raise ValueError('不規則外框需要帶透明度的圖片，請使用透明 PNG。')
    if isinstance(alpha_threshold, bool) or not isinstance(alpha_threshold, int) or not 1 <= alpha_threshold <= 255:
        raise ValueError('透明度門檻需為 1 到 255 的整數。')
    try:
        tolerance = float(simplify_tolerance)
    except (TypeError, ValueError):
        raise ValueError('輪廓簡化距離需為有效的非負數值。') from None
    if isinstance(simplify_tolerance, bool) or not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError('輪廓簡化距離需為有限的非負數值。')
    if isinstance(max_vertices, bool) or not isinstance(max_vertices, int) or not 3 <= max_vertices <= 256:
        raise ValueError('單一輪廓頂點上限需為 3 到 256 的整數。')
    alpha = image.convert('RGBA').getchannel('A')
    mask = np.asarray(alpha) >= alpha_threshold
    pixel_area = int(np.count_nonzero(mask))
    if pixel_area == 0:
        raise ValueError('圖片在目前透明度門檻下沒有可辨識的輪廓。')
    if pixel_area == image.width * image.height:
        raise ValueError('圖片沒有透明外框；全滿圖片請改用矩形模式。')
    loops, raw_edge_count = _irregular_trace_grid(mask)
    if not loops or abs(sum(signed_area(loop) for loop in loops) - pixel_area) > 1e-7:
        raise ValueError('像素輪廓面積不一致，無法安全建立不規則外框。')
    if len(loops) * 3 > 512:
        raise ValueError('輪廓數量超過總頂點上限 512，請減少小島或孔洞；不會忽略任何輪廓。')
    signs = [1 if signed_area(loop) > 0 else -1 for loop in loops]
    parents = _irregular_parents(loops)
    if any((parent is None and signs[index] < 0) or
           (parent is not None and signs[index] == signs[parent]) for index, parent in enumerate(parents)):
        raise ValueError('外框與孔洞層級不一致，無法安全建立不規則外框。')
    owners = {}
    for number, loop in enumerate(loops):
        for point in loop:
            owners.setdefault(point, []).append(number)
    shared, anchors = {}, []
    for point, indices in owners.items():
        for first in indices:
            for second in indices:
                if first < second:
                    shared.setdefault((first, second), set()).add(point)
    for loop in loops:
        xs, ys = [point[0] for point in loop], [point[1] for point in loop]
        anchor = {point for point in loop if point[0] in (min(xs), max(xs)) or point[1] in (min(ys), max(ys))}
        anchor.update(point for point in loop if len(owners[point]) > 1)
        anchors.append(anchor)
    reflex = []
    for number, loop in enumerate(loops):
        coarse = _irregular_simplify_loop(loop, min(tolerance, .75), anchors[number])
        significant = {point for index, point in enumerate(coarse)
                       if _cross(coarse[index - 1], point, coarse[(index + 1) % len(coarse)]) * signs[number] < -1e-9
                       and _point_distance(point, coarse[index - 1], coarse[(index + 1) % len(coarse)]) >= 1 - 1e-9}
        reflex.append(significant)
        anchors[number].update(significant)
    used_tolerance = tolerance
    for attempt in range(14):
        simplified = [_irregular_simplify_loop(loop, used_tolerance, anchors[index]) for index, loop in enumerate(loops)]
        if any(len(loop) > max_vertices for loop in simplified) or sum(map(len, simplified)) > 512:
            raise ValueError(f'輪廓超過頂點上限（單環 {max_vertices}、總共 512）；請降低圖片細節或調整簡化距離，不會改用凸輪廓。')
        if _irregular_valid(simplified, signs, parents, shared, reflex):
            break
        used_tolerance = 0. if attempt >= 11 else used_tolerance * .75
    else:
        raise ValueError('無法在保留凹口、孔洞與小島的前提下簡化輪廓。')
    counts = [len(loop) for loop in simplified]
    if any(count > max_vertices for count in counts) or sum(counts) > 512:
        raise ValueError(f'輪廓超過頂點上限（單環 {max_vertices}、總共 512）；請降低圖片細節或調整簡化距離，不會改用凸輪廓。')
    children = {index: [] for index in range(len(loops))}
    roots = []
    for index, parent in enumerate(parents):
        (roots if parent is None else children[parent]).append(index)
    def ranking(index):
        return -abs(signed_area(loops[index])), min(point[1] for point in loops[index]), min(point[0] for point in loops[index])
    order = []
    def visit(index):
        order.append(index)
        for child in sorted(children[index], key=ranking):
            visit(child)
    for root in sorted(roots, key=ranking):
        visit(root)
    remap = {old: new for new, old in enumerate(order)}
    normalized = []
    for index in order:
        # Reversing image-space winding after Y inversion produces CCW outers.
        polygon = list(reversed(simplified[index]))
        first = min(range(len(polygon)), key=lambda i: (polygon[i][1], polygon[i][0]))
        polygon = polygon[first:] + polygon[:first]
        normalized.append([(x / image.width - .5, .5 - y / image.height) for x, y in polygon])
    ys, xs = np.nonzero(mask)
    bounds = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
    return {
        'loops': normalized, 'loop_roles': ['outer' if signs[index] > 0 else 'hole' for index in order],
        'loop_parents': [remap[parents[index]] if parents[index] is not None else None for index in order],
        'components': signs.count(1), 'holes': signs.count(-1),
        'source_size': [image.width, image.height], 'source_alpha_bounds': bounds,
        'source_nonzero_alpha_bounds': list(alpha.getbbox()) if alpha.getbbox() else None,
        'alpha_threshold': alpha_threshold, 'pixel_area': pixel_area,
        'raw_edge_count': raw_edge_count, 'raw_vertex_count': sum(len(loop) for loop in loops),
        'vertex_count': sum(counts), 'loop_vertex_counts': [counts[index] for index in order],
        'max_vertices_per_loop': max_vertices, 'max_total_vertices': 512,
        'requested_simplify_tolerance': tolerance, 'used_simplify_tolerance': used_tolerance,
        'protected_notch_count': sum(len(points) for points in reflex),
        'simplified_area_px': sum(signed_area(loop) for loop in simplified),
        'shared_grid_corner_count': sum(len(indices) > 1 for indices in owners.values()),
        'winding': 'outer CCW, holes CW; normalized world-up about original canvas centre',
    }
