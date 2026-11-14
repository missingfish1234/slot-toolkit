"""Parametric, closed faceted Diamond geometry and source-projection UVs."""
from __future__ import annotations

import math
from functools import lru_cache

DIAMOND_GUIDE_DEFAULTS = {
    "diamond_center_x": 0.0,
    "diamond_table_y": 0.35,
    "diamond_waist_y": 0.10,
    "diamond_tip_y": -0.48,
    "diamond_table_width": 0.50,
    "diamond_waist_width": 0.96,
}
DIAMOND_ALIGNMENT_DEFAULTS = {**DIAMOND_GUIDE_DEFAULTS, "diamond_table_depth": 0.0,
                              "diamond_waist_depth": 0.0, "diamond_ring_phase": 0.0,
                              "diamond_view_tilt": 12.0}


def _get(options, name, default=None):
    return options.get(name, default) if isinstance(options, dict) else getattr(options, name, default)


def validate_diamond_guides(guides: dict, width: float = 1, height: float = 1) -> dict:
    try:
        result = {name: float(guides.get(name, default)) for name, default in DIAMOND_GUIDE_DEFAULTS.items()}
        dimensions = (float(width), float(height))
    except (TypeError, ValueError, AttributeError):
        raise ValueError("鑽石導線需使用有效的數值。") from None
    if not all(math.isfinite(value) for value in (*result.values(), *dimensions)) or min(dimensions) <= 0:
        raise ValueError("鑽石導線或圖片尺寸含有無效數值。")
    if not -0.5 < result["diamond_tip_y"] < result["diamond_waist_y"] < result["diamond_table_y"] < 0.5:
        raise ValueError("鑽石導線需依序為上方台面、腰線、下方底尖，並位於圖片範圍內。")
    if not 0 < result["diamond_table_width"] < result["diamond_waist_width"] <= 1:
        raise ValueError("台面寬度需大於 0、小於腰部寬度，腰部寬度不可超過圖片。")
    center, half = result["diamond_center_x"], result["diamond_waist_width"] / 2
    if center - half < -0.5000001 or center + half > 0.5000001:
        raise ValueError("鑽石中心與腰部寬度超出圖片左右邊界。")
    return result


def get_diamond_guides(prepared: dict, options=None) -> dict:
    values = {name: _get(options, name, default) for name, default in DIAMOND_GUIDE_DEFAULTS.items()}
    return validate_diamond_guides(values, prepared.get("width", 1), prepared.get("height", 1))


def _cross(a, b, c):
    u, v = tuple(b[i] - a[i] for i in range(3)), tuple(c[i] - a[i] for i in range(3))
    return (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])


def _unit(vector):
    length = math.sqrt(sum(value * value for value in vector))
    return tuple(value / length for value in vector)


def project_vertex(point, angle_degrees, axis, tilt_degrees, center_x=0):
    x, y, z = point
    theta, pitch = math.radians(angle_degrees), math.radians(tilt_degrees)
    sine, cosine = math.sin(theta), math.cos(theta)
    if axis == "y":
        x, z = (x - center_x) * cosine + z * sine + center_x, -(x - center_x) * sine + z * cosine
    else:
        y, z = y * cosine - z * sine, y * sine + z * cosine
    return x, y * math.cos(pitch) - z * math.sin(pitch), y * math.sin(pitch) + z * math.cos(pitch)


def view_normal(normal, angle_degrees, axis, tilt_degrees):
    return project_vertex(normal, angle_degrees, axis, tilt_degrees, 0)


@lru_cache(maxsize=128)
def _geometry(width, height, facets, center_x, table_y, waist_y, tip_y, table_width, waist_width, girdle, tilt,
              table_depth=0.0, waist_depth=0.0, ring_phase=0.0):
    center = center_x * width
    correction = math.cos(math.radians(tilt))
    table_height, waist_height, tip_height = (value * height / correction for value in (table_y, waist_y, tip_y))
    phase = math.pi / 2 + math.radians(ring_phase)
    horizontal_extent = max(abs(math.cos(phase + index * 2 * math.pi / facets)) for index in range(facets))
    table_radius, waist_radius = table_width * width / (2 * horizontal_extent), waist_width * width / (2 * horizontal_extent)
    table_z_radius = table_depth * width / 2 if table_depth > 0 else table_radius
    waist_z_radius = waist_depth * width / 2 if waist_depth > 0 else waist_radius
    if table_z_radius >= waist_z_radius:
        raise ValueError("台面前後深度需小於腰部深度，才能形成正常鑽冠。")
    half_girdle = girdle * height / (2 * correction)
    # This phase is symmetric about the image's vertical axis for odd/even N;
    # normalization makes the guide handles match the actual initial width.
    def ring(radius, z_radius, y):
        return tuple((center + radius * math.cos(phase + index * 2 * math.pi / facets),
                      y, z_radius * math.sin(phase + index * 2 * math.pi / facets))
                     for index in range(facets))
    table = ring(table_radius, table_z_radius, table_height)
    upper = ring(waist_radius, waist_z_radius, waist_height + half_girdle)
    lower = ring(waist_radius, waist_z_radius, waist_height - half_girdle)
    tip = (center, tip_height, 0.0)
    result = []
    all_points = table + upper + lower + (tip,)

    def add_surface(name, zone, model, ids, logical_ids=None, logical_model=None):
        triangles = (0, 1, 2) if len(model) == 3 else (0, 1, 2, 2, 3, 0)
        if zone == "crown" and len(model) == 4:
            normal = _cross(*model[:3])
            magnitude = math.sqrt(sum(value * value for value in normal))
            distance = abs(sum(normal[i] * (model[3][i] - model[0][i]) for i in range(3))) / magnitude
            if distance > max(width, height) * 1e-8:
                tolerance = max(width, height) * 1e-7
                candidates = (((0, 1, 2), (2, 3, 0)), ((0, 1, 3), (1, 2, 3)))
                chosen = None
                for candidate in candidates:
                    valid = True
                    for triangle in candidate:
                        points = tuple(model[i] for i in triangle)
                        vector = _cross(*points)
                        length = math.sqrt(sum(value * value for value in vector))
                        if length <= 1e-12 or any(sum(vector[i] * (point[i] - points[0][i]) for i in range(3)) > tolerance * length
                                                   for point in all_points):
                            valid = False
                            break
                    if valid:
                        chosen = candidate
                        break
                if chosen is None:
                    raise ValueError("台面與腰部比例會讓鑽冠扭曲，請調整前後深度。")
                for suffix, indices in zip(("a", "b"), chosen):
                    add_surface(f"{name}_{suffix}", zone, tuple(model[i] for i in indices),
                                tuple(ids[i] for i in indices), ids, model)
                return
        result.append({"name": name, "zone": zone, "model": model,
                       "triangles": triangles, "hull": len(model), "normal_coefficients": _cross(*model[:3]),
                       "node_ids": tuple(ids), "logical_face": name.rsplit("_", 1)[0] if logical_ids else name,
                       "logical_node_ids": tuple(logical_ids or ids), "logical_model": tuple(logical_model or model)})

    for index in range(facets):
        following = (index + 1) % facets
        for zone, model in (("pavilion", (lower[index], lower[following], tip)),
                            ("crown", (table[index], table[following], upper[following], upper[index]))):
            ids = ((f"waist_bottom:{index}", f"waist_bottom:{following}", "tip") if zone == "pavilion" else
                   (f"table:{index}", f"table:{following}", f"waist_top:{following}", f"waist_top:{index}"))
            add_surface(f"diamond_{zone}_{index:02d}", zone, model, ids)
        if girdle > 0:
            model = (upper[index], upper[following], lower[following], lower[index])
            result.append({"name": f"diamond_girdle_{index:02d}", "zone": "girdle", "model": model,
                           "triangles": (0, 1, 2, 2, 3, 0), "hull": 4,
                           "normal_coefficients": _cross(*model[:3]),
                           "node_ids": (f"waist_top:{index}", f"waist_top:{following}", f"waist_bottom:{following}", f"waist_bottom:{index}"),
                           "logical_face": f"diamond_girdle_{index:02d}",
                           "logical_node_ids": (f"waist_top:{index}", f"waist_top:{following}", f"waist_bottom:{following}", f"waist_bottom:{index}"),
                           "logical_model": model})
    model = table + ((center, table_height, 0.0),)
    triangles = tuple(vertex for index in range(facets) for vertex in ((index + 1) % facets, index, facets))
    result.append({"name": "diamond_table", "zone": "table", "model": model,
                   "triangles": triangles, "hull": facets, "normal_coefficients": (0.0, 1.0, 0.0),
                   "node_ids": tuple(f"table:{i}" for i in range(facets)) + ("table_center",),
                   "logical_face": "diamond_table", "logical_node_ids": tuple(f"table:{i}" for i in range(facets)),
                   "logical_model": table})
    return tuple(result)


def _base_geometry(options, width, height):
    guides = get_diamond_guides({"width": width, "height": height}, options)
    geometry = _geometry(float(width), float(height), int(_get(options, "diamond_facets", 8)),
                         *(guides[name] for name in DIAMOND_GUIDE_DEFAULTS),
                         float(_get(options, "diamond_girdle_height", .015)), float(_get(options, "diamond_view_tilt", 12)),
                         float(_get(options, "diamond_table_depth", 0)), float(_get(options, "diamond_waist_depth", 0)),
                         float(_get(options, "diamond_ring_phase", 0)))
    return geometry


def _alignment_options(options, width, height):
    values = get_diamond_guides({"width": width, "height": height}, options)
    try:
        values.update({name: float(_get(options, name, default))
                       for name, default in DIAMOND_ALIGNMENT_DEFAULTS.items() if name not in values})
        facets = float(_get(options, "diamond_facets", 8))
        girdle = float(_get(options, "diamond_girdle_height", .015))
        z_scale = float(_get(options, "z_scale", 1))
    except (TypeError, ValueError):
        raise ValueError("鑽石對齊設定需使用有效的數值。") from None
    if not all(math.isfinite(value) for value in (*values.values(), facets, girdle, z_scale)):
        raise ValueError("鑽石對齊設定需使用有限數值。")
    if int(facets) != facets or not 4 <= facets <= 16:
        raise ValueError("鑽石切面數需為 4 到 16 的整數。")
    if not 0 <= values["diamond_view_tilt"] <= 35:
        raise ValueError("鑽石俯視角度需為 0 到 35 度。")
    if any(not 0 <= values[name] <= 2 for name in ("diamond_table_depth", "diamond_waist_depth")):
        raise ValueError("台面與腰部前後直徑需為圖片寬度的 0 到 200%；0 代表自動。")
    if not 0 <= girdle <= .12 or girdle / 2 >= min(values["diamond_table_y"] - values["diamond_waist_y"],
                                                  values["diamond_waist_y"] - values["diamond_tip_y"]):
        raise ValueError("鑽石腰帶高度過大，已碰到台面或底尖。")
    if z_scale <= 0:
        raise ValueError("Z 厚度縮放需大於 0。")
    values["diamond_ring_phase"] = (values["diamond_ring_phase"] + 180) % 360 - 180
    return values, int(facets), girdle, z_scale


def get_diamond_alignment(options, width, height):
    """Return the production 0-degree cage, in normalized world-up image coordinates.

    ``xyz`` includes static Z thickness scaling, but no animation or global
    perspective magnification. Logical faces retain crown quads even when a
    warped quad needs two independently culled physical triangles.
    """
    values, facets, girdle, z_scale = _alignment_options(options, width, height)
    context = {**values, "diamond_facets": facets, "diamond_girdle_height": girdle}
    geometry = _base_geometry(context, width, height)
    nodes, faces, physical = {}, {}, []
    tilt, center = values["diamond_view_tilt"], values["diamond_center_x"] * width
    for spec in geometry:
        ids = spec["node_ids"]
        nx, ny, nz = spec["normal_coefficients"]
        visible = view_normal((nx * z_scale, ny * z_scale, nz), 0, "y", tilt)[2] > 1e-9
        for node_id, point in zip(ids, spec["model"]):
            actual = (point[0], point[1], point[2] * z_scale)
            projected = project_vertex(actual, 0, "y", tilt, center)
            nodes[node_id] = {"point": (projected[0] / width, projected[1] / height),
                              "xyz": actual, "ring": node_id.split(":")[0]}
        logical_id = spec["logical_face"]
        face = faces.setdefault(logical_id, {"id": logical_id, "zone": spec["zone"],
                                "nodes": spec["logical_node_ids"], "visible": False,
                                "physical_faces": []})
        face["visible"] |= visible
        face["physical_faces"].append(spec["name"])
        physical.append((spec, visible))
    # A zero-height girdle has coincident upper/lower nodes, retained as named
    # handles so the UI topology remains stable when a band is enabled later.
    for index in range(facets):
        for prefix, alternate in (("waist_top", "waist_bottom"), ("waist_bottom", "waist_top")):
            node_id = f"{prefix}:{index}"
            if node_id not in nodes:
                original = nodes[f"{alternate}:{index}"]
                nodes[node_id] = {**original, "ring": prefix}
    edges = {}
    for face in faces.values():
        ids = face["nodes"]
        for first, second in zip(ids, ids[1:] + ids[:1]):
            key = tuple(sorted((first, second)))
            edge = edges.setdefault(key, {"a": first, "b": second, "visible": False,
                                          "zone": face["zone"], "internal": False})
            edge["visible"] |= face["visible"]
    for spec, visible in physical:
        ids = spec["node_ids"]
        for ia, ib, ic in zip(spec["triangles"][::3], spec["triangles"][1::3], spec["triangles"][2::3]):
            for first, second in ((ids[ia], ids[ib]), (ids[ib], ids[ic]), (ids[ic], ids[ia])):
                key = tuple(sorted((first, second)))
                if key not in edges:
                    edges[key] = {"a": first, "b": second, "visible": visible,
                                  "zone": spec["zone"], "internal": True}
    handles, effective = {}, {}
    labels = {"table": "頂台", "waist": "腰環"}
    for ring_name, prefix in (("table", "table"), ("waist", "waist_top")):
        points = [nodes[f"{prefix}:{i}"]["xyz"] for i in range(facets)]
        for direction, coordinate, high in (("front", 2, True), ("back", 2, False),
                                            ("left", 0, False), ("right", 0, True)):
            extreme = (max if high else min)(point[coordinate] for point in points)
            selected = [point for point in points if abs(point[coordinate] - extreme) <= max(width, height) * 1e-8]
            point = tuple(sum(p[j] for p in selected) / len(selected) for j in range(3))
            projected = project_vertex(point, 0, "y", tilt, center)
            suffix = {"front": "前緣", "back": "後緣", "left": "左寬", "right": "右寬"}[direction]
            handles[f"{ring_name}_{direction}"] = {"point": (projected[0] / width, projected[1] / height),
                 "xyz": point, "label": labels[ring_name] + suffix, "kind": direction, "ring": ring_name}
        # Effective diameter is the generating ellipse diameter, not its sampled
        # extrema; phase and odd facet counts can make those differ.
        phase = math.pi / 2 + math.radians(values["diamond_ring_phase"])
        extent = max(abs(math.cos(phase + i * 2 * math.pi / facets)) for i in range(facets))
        depth = values[f"diamond_{ring_name}_depth"] or values[f"diamond_{ring_name}_width"] / extent
        effective[f"{ring_name}_depth"] = depth
        effective[f"{ring_name}_depth_pixels"] = depth * width * z_scale
    handles["tip"] = {"point": nodes["tip"]["point"], "xyz": nodes["tip"]["xyz"], "label": "底尖", "kind": "tip"}
    handles["center"] = {"point": (values["diamond_center_x"], values["diamond_waist_y"]),
                         "label": "左右中心", "kind": "center"}
    return {"nodes": nodes, "faces": list(faces.values()), "edges": list(edges.values()),
            "handles": handles, "options": values, "effective": {**effective, "z_scale": z_scale}}


def adjust_diamond_alignment(options, handle_id, target, width, height):
    """Solve one physical rim/width handle while preserving its opposite rim."""
    alignment = get_diamond_alignment(options, width, height)
    values = dict(alignment["options"])
    try:
        x, y = (float(value) for value in target)
    except (TypeError, ValueError):
        raise ValueError("對齊節點需要左右及上下兩個有效座標。") from None
    if not all(math.isfinite(value) for value in (x, y)):
        raise ValueError("對齊節點需使用有限座標。")
    if handle_id not in alignment["handles"]:
        raise ValueError("無法辨識選取的鑽石對齊節點。")
    if handle_id == "center":
        values["diamond_center_x"] = x
    elif handle_id == "tip":
        values["diamond_tip_y"] = y
    else:
        ring_name, direction = handle_id.split("_")
        if direction in ("left", "right"):
            old_x = alignment["handles"][handle_id]["point"][0]
            center = values["diamond_center_x"]
            if (x - center) * (old_x - center) <= 0:
                raise ValueError("寬度節點不可跨越鑽石中心。")
            values[f"diamond_{ring_name}_width"] *= abs((x - center) / (old_x - center))
        else:
            tilt = values["diamond_view_tilt"]
            if tilt < 2:
                raise ValueError("請先將俯視角度調整為至少 2°，才能拖曳前後深度。")
            facets = int(_get(options, "diamond_facets", 8))
            phase = math.pi / 2 + math.radians(values["diamond_ring_phase"])
            sines = [math.sin(phase + index * 2 * math.pi / facets) for index in range(facets)]
            coefficient = -.5 * width / height * _get(options, "z_scale", 1) * math.sin(math.radians(tilt))
            front, back = coefficient * max(sines), coefficient * min(sines)
            front_y = alignment["handles"][f"{ring_name}_front"]["point"][1]
            back_y = alignment["handles"][f"{ring_name}_back"]["point"][1]
            depth = ((y - back_y) / (front - back) if direction == "front" else
                     (front_y - y) / (front - back))
            if depth <= 0:
                raise ValueError("前後緣不可交錯；請保留大於 0 的前後深度。")
            values[f"diamond_{ring_name}_depth"] = depth
            ring_y = back_y - back * depth if direction == "front" else front_y - front * depth
            values[f"diamond_{ring_name}_y"] = ring_y - (_get(options, "diamond_girdle_height", .015) / 2
                                                         if ring_name == "waist" else 0)
    context = dict(options) if isinstance(options, dict) else vars(options).copy()
    return get_diamond_alignment({**context, **values}, width, height)["options"]


def diamond_rotation_bounds(options, width, height):
    """Conservative full-turn orthographic bounds of the actual physical cage."""
    tilt = math.radians(_get(options, "diamond_view_tilt", 12))
    center = _get(options, "diamond_center_x", 0) * width
    depth_scale = _get(options, "z_scale", 1)
    if _get(options, "z_bounce_enabled", False):
        depth_scale *= max(1, _get(options, "peak_z_scale", 1))
    left, right, bottom, top = math.inf, -math.inf, math.inf, -math.inf
    for spec in _base_geometry(options, width, height):
        for x, y, z in spec["model"]:
            z *= depth_scale
            if _get(options, "axis", "y") == "y":
                radius = math.hypot(x - center, z)
                x0, x1 = center - radius, center + radius
                y0, y1 = y * math.cos(tilt) - radius * math.sin(tilt), y * math.cos(tilt) + radius * math.sin(tilt)
            else:
                radius = math.hypot(y, z)
                x0 = x1 = x
                y0, y1 = -radius, radius
            left, right = min(left, x0), max(right, x1)
            bottom, top = min(bottom, y0), max(top, y1)
    return {"left": left, "right": right, "bottom": bottom, "top": top}


def diamond_geometry(options, width, height):
    geometry = _base_geometry(options, width, height)
    regions = _get(options, "diamond_cut_regions", ())
    if regions:
        from spine_turn_diamond_cuts import split_diamond_geometry
        return split_diamond_geometry(geometry, regions, width, height,
                                      _get(options, "diamond_view_tilt", 12), _get(options, "z_scale", 1),
                                      _get(options, "diamond_front_uv_points", ()),
                                      _get(options, "diamond_back_uv_points", ()),
                                      allow_hidden_reuse=_aligned_materials(options),
                                      material_center_x=(_get(options, "diamond_center_x", 0) * width
                                                         if _aligned_materials(options) else None))
    return geometry


def _aligned_materials(options):
    return bool(_get(options, "diamond_table_depth", 0) or _get(options, "diamond_waist_depth", 0)
                or _get(options, "diamond_ring_phase", 0))


def diamond_normals(options, width, height, z_scale=1):
    return tuple((spec["normal_coefficients"][0] * z_scale,
                  spec["normal_coefficients"][1] * z_scale,
                  spec["normal_coefficients"][2]) for spec in diamond_geometry(options, width, height))


def _safe_uv(x, y, boundary, width, height):
    if not boundary:
        return min(1, max(0, x / width + .5)), min(1, max(0, .5 - y / height))
    polygon = [(px * width, py * height) for px, py in boundary]
    center = (sum(px for px, _ in polygon) / len(polygon), sum(py for _, py in polygon) / len(polygon))
    factor = 1.0
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        nx, ny = dy / length, -dx / length
        limit = nx * a[0] + ny * a[1] - 1.0
        amount = nx * (x - center[0]) + ny * (y - center[1])
        if amount > 0:
            factor = min(factor, max(0, (limit - nx * center[0] - ny * center[1]) / amount))
    x, y = center[0] + factor * (x - center[0]), center[1] + factor * (y - center[1])
    return x / width + .5, .5 - y / height


def _source_material_uvs(spec, geometry, width, height, tilt, static_scale, center_x,
                         front_boundary=(), back_boundary=(), allow_hidden_reuse=False):
    """Project material once, borrowing only a visible same-zone pavilion.

    A downward-facing side facet can be hidden in BOTH source cameras. Its
    180-degree projection then covers crown/girdle artwork, even though its
    physical triangle is a pavilion. Reuse a visible pavilion triangle from
    the selected source instead; rim/rim/tip vertex roles remain unchanged.
    Source-visible faces keep their original projection exactly.
    """
    def normal(surface):
        nx, ny, nz = surface["normal_coefficients"]
        return _unit((nx * static_scale, ny * static_scale, nz))

    nx, ny, nz = spec["normal_coefficients"]
    raw_normal = (nx * static_scale, ny * static_scale, nz)
    path = "front" if view_normal(raw_normal, 0, "y", tilt)[2] >= 0 else "back"
    source_angle = 0 if path == "front" else 180
    donor = spec
    if (allow_hidden_reuse and spec["zone"] == "pavilion" and len(spec["model"]) == 3
            and view_normal(raw_normal, source_angle, "y", tilt)[2] <= 1e-9):
        source_normal = normal(spec)
        candidates = []
        for candidate in geometry:
            if candidate["zone"] != "pavilion" or len(candidate["model"]) != 3:
                continue
            candidate_normal = normal(candidate)
            facing = view_normal(candidate_normal, source_angle, "y", tilt)[2]
            if facing > 1e-9:
                alignment = sum(a * b for a, b in zip(source_normal, candidate_normal))
                candidates.append((alignment, facing, candidate))
        if candidates:
            donor = max(candidates, key=lambda entry: entry[:2])[2]
    boundary = front_boundary if path == "front" else back_boundary
    uvs = []
    for x, y, z in donor["model"]:
        px, py, _ = project_vertex((x, y, z * static_scale), source_angle, "y", tilt, center_x)
        uvs.append(_safe_uv(px, py, boundary, width, height))
    return path, tuple(uvs)


def diamond_pose(angle_degrees, options, width, height, z_scale=1, visibility_z_scale=None):
    center = _get(options, "diamond_center_x", 0) * width
    tilt, axis = _get(options, "diamond_view_tilt", 12), _get(options, "axis", "y")
    static_scale = _get(options, "z_scale", 1)
    visible_scale = z_scale if visibility_z_scale is None else visibility_z_scale
    result = []
    geometry = diamond_geometry(options, width, height)
    for spec in geometry:
        nx, ny, nz = spec["normal_coefficients"]
        normal = _unit((nx * z_scale, ny * z_scale, nz))
        shown_normal = view_normal(normal, angle_degrees, axis, tilt)
        next_normal = view_normal((nx * visible_scale, ny * visible_scale, nz),
                                  angle_degrees + math.degrees(1e-9), axis, tilt)
        vertices, uvs, model = [], [], []
        material_uvs = spec.get("material_uvs")
        if material_uvs:
            path = spec["material_path"]
        else:
            path, material_uvs = _source_material_uvs(spec, geometry, width, height, tilt,
                static_scale, center, _get(options, "diamond_front_uv_points", ()),
                _get(options, "diamond_back_uv_points", ()), allow_hidden_reuse=_aligned_materials(options))
        for vertex_index, (x, y, z) in enumerate(spec["model"]):
            actual = (x, y, z * z_scale)
            projected = project_vertex(actual, angle_degrees, axis, tilt, center)
            vertices.extend(projected[:2]); model.extend(actual)
            uvs.extend(material_uvs[vertex_index])
        optical_normal = normal
        if spec.get("cut_yaw", 0) or spec.get("cut_pitch", 0):
            from spine_turn_diamond_cuts import reflection_normal
            optical_normal = reflection_normal(normal, spec.get("cut_yaw", 0), spec.get("cut_pitch", 0), path)
        light = view_normal(optical_normal, angle_degrees - _get(options, "light_angle", 0), axis, tilt)
        # A fixed upper-left camera light separates both side and top facets.
        lambert = max(0.0, (-.35 * light[0] + .45 * light[1] + .82 * light[2]) /
                      math.sqrt(.35 ** 2 + .45 ** 2 + .82 ** 2))
        minimum, power = _get(options, "min_brightness", .4), _get(options, "shade_curve", 1)
        strength = _get(options, "diamond_shading", .65)
        factor = 1 - strength + strength * (minimum + (1 - minimum) * lambert ** power)
        channel = max(0, min(255, round(255 * factor)))
        result.append({"name": spec["name"], "kind": "diamond_face", "zone": spec["zone"], "path": path,
                       "vertices": vertices, "uvs": uvs, "triangles": list(spec["triangles"]), "hull": spec["hull"],
                       "normal": normal, "view_normal": shown_normal, "facing": shown_normal[2],
                       "shading_normal": optical_normal, "view_shading_normal": view_normal(optical_normal, angle_degrees, axis, tilt),
                       "cut_region": spec.get("cut_region", -1), "cut_yaw": spec.get("cut_yaw", 0), "cut_pitch": spec.get("cut_pitch", 0),
                       "visible": next_normal[2] > 0, "model_vertices": model,
                       "color": f"{channel:02x}" * 3 + "ff"})
    return result
