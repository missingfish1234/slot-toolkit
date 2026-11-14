"""Generated, shader-free diamond highlights shared by preview and Spine export."""
from __future__ import annotations

from functools import lru_cache
import math

from PIL import Image


@lru_cache(maxsize=1)
def _sparkle_texture():
    size = 96
    image = Image.new("RGBA", (size, size))
    pixels = image.load()
    for y in range(size):
        dy = (y + .5 - size / 2) / (size / 2)
        for x in range(size):
            dx = (x + .5 - size / 2) / (size / 2)
            core = math.exp(-(dx * dx + dy * dy) * 95)
            cross = (math.exp(-abs(dx) * 85 - abs(dy) * 3.5) +
                     math.exp(-abs(dy) * 85 - abs(dx) * 3.5)) * .8
            diagonal = (math.exp(-abs(dx - dy) * 80 - abs(dx + dy) * 8) +
                        math.exp(-abs(dx + dy) * 80 - abs(dx - dy) * 8)) * .28
            edge = max(0., 1. - max(abs(dx), abs(dy)))
            alpha = round(255 * min(1., core + cross + diagonal) * min(1., edge * 6))
            pixels[x, y] = (255, 255, 255, alpha)
    return image


def make_effect_textures(options):
    if getattr(options, "model", "extrusion") != "diamond":
        return {}
    result = {}
    if getattr(options, "diamond_shine_enabled", False):
        result["diamond-shine"] = Image.new("RGBA", (2, 2), (255, 255, 255, 255))
    if getattr(options, "diamond_sparkles_enabled", False):
        result["diamond-sparkle"] = _sparkle_texture().copy()
    return result


def _pairs(values, width):
    return [tuple(values[index:index + width]) for index in range(0, len(values), width)]


def _color(alpha):
    return f"ffffff{max(0, min(255, round(alpha * 255))):02x}"


def _shine_facing(surface):
    facing = min(1.,max(0.,float(surface.get('facing',1.)))*3)
    if surface.get('cut_region',-1)>=0:
        normal=surface.get('view_shading_normal',surface.get('view_normal',(0.,0.,1.)))
        lambert=max(0.,(-.35*normal[0]+.45*normal[1]+.82*normal[2])/
                    math.sqrt(.35**2+.45**2+.82**2))
        facing*=.2+.8*lambert
    return facing


def _facet_cells(surface, sweep_center, width, strength):
    """Fixed barycentric cells stay inside a linearly interpolated parent face.

    Moving clipped polygon corners can change correspondence at an edge and
    leave their facet between keys. These cells keep their vertex identities
    and weights for the entire turn; only the soft sweep opacity changes.
    Convex parent faces are supplied by the Diamond geometry/cut partition.
    """
    points = _pairs(surface["vertices"], 2)
    models = _pairs(surface["model_vertices"], 3)
    count = min(len(points), int(surface.get("hull", len(points))))
    # Image-space cut patches already use a centroid fan. One light cell per
    # patch preserves those artist-drawn divisions and bounds the slot count.
    if len(points)>count:
        x,y = (sum(point[axis] for point in points[:count])/count for axis in range(2))
        distance = (x+.24*y-sweep_center)/max(width*.15,1.)
        facing = _shine_facing(surface)
        alpha = strength*.75*math.exp(-.5*distance*distance)*facing
        return [{"name":f"{surface['name']}_shine_0","kind":"diamond_fx","path":"diamond-shine",
            "vertices":list(surface['vertices']),"uvs":[.5,.5]*len(points),
            "triangles":list(surface['triangles']),"hull":count,"color":_color(alpha),
            "visible":surface.get('visible',True),"model_vertices":list(surface['model_vertices']),
            "source_face":surface['name'],"effect":"light_sweep","cell_weights":{"identity":True}}]
    points, models = points[:count], models[:count]
    if count < 3:
        return []
    center = tuple(sum(point[axis] for point in points)/count for axis in range(2))
    model_center = tuple(sum(point[axis] for point in models)/count for axis in range(3))
    sigma = max(width*.15, 1.)
    facing = _shine_facing(surface)
    result = []
    for index in range(count):
        following = (index+1) % count
        polygon = (points[index], points[following], center)
        model = (models[index], models[following], model_center)
        x, y = (sum(point[axis] for point in polygon)/3 for axis in range(2))
        distance = (x+.24*y-sweep_center)/sigma
        alpha = strength*.75*math.exp(-.5*distance*distance)*facing
        result.append({"name":f"{surface['name']}_shine_{index}", "kind":"diamond_fx",
            "path":"diamond-shine", "vertices":[value for point in polygon for value in point],
            "uvs":[.5,.5]*3, "triangles":[0,1,2], "hull":3,
            "color":_color(alpha), "visible":surface.get("visible",True),
            "model_vertices":[value for point in model for value in point],
            "source_face":surface["name"], "effect":"light_sweep",
            "cell_weights":{"edge":(index,following),"centroid_count":count}})
    return result


def _sparkles(faces, options, angle, width, height):
    candidates = {}
    waist = options.diamond_waist_y * height
    for surface in faces:
        for projected, model in zip(_pairs(surface["vertices"], 2), _pairs(surface["model_vertices"], 3)):
            key = tuple(round(value, 7) for value in model)
            item = candidates.setdefault(key, {"model": model, "point": projected, "facing": 0.})
            if surface.get("visible", True):
                facing = surface.get("facing", 1.)
                item["facing"] = max(item["facing"], max(0., float(facing)))
    if not candidates:
        return []
    nearest_waist = min(abs(item["model"][1] - waist) for item in candidates.values())
    ring = [item for item in candidates.values() if abs(item["model"][1] - waist) <= nearest_waist + 1e-6]
    anchors = (min(ring, key=lambda item: item["model"]),
               max(ring, key=lambda item: (item["model"][0], -item["model"][2])))
    all_points = [item["point"] for item in candidates.values()]
    lo, hi = min(point[0] for point in all_points), max(point[0] for point in all_points)
    middle, radius = (lo + hi) / 2, max((hi - lo) / 2, 1.)
    result = []
    for index, anchor in enumerate(anchors):
        x, y = anchor["point"]
        edge = min(1., max(0., (abs(x - middle) / radius - .62) / .38)) ** 2
        pulse = max(0., math.sin(angle * 2 + index * 1.9 + .45)) ** 8
        intensity = options.diamond_sparkle_strength * edge * pulse * min(1., anchor["facing"] * 2)
        half = min(width, height) * .075 * (.45 + .55 * pulse)
        vertices = [x - half, y + half, x + half, y + half,
                    x + half, y - half, x - half, y - half]
        result.append({"name": f"diamond_sparkle_{index}", "kind": "diamond_fx", "path": "diamond-sparkle",
                       "vertices": vertices, "uvs": [0., 0., 1., 0., 1., 1., 0., 1.],
                       "triangles": [0, 1, 2, 2, 3, 0], "hull": 4, "visible": True,
                       "color": _color(intensity), "model_vertices": list(anchor["model"]) * 4,
                       "effect": "sparkle"})
    return result


def diamond_effect_surfaces(base_surfaces, options, angle_degrees, width, height):
    """Return stable-topology normal-blend light meshes; no clipping attachments."""
    if getattr(options, "model", "extrusion") != "diamond":
        return []
    faces = [surface for surface in base_surfaces if surface.get("kind") == "diamond_face"]
    if not faces:
        return []
    angle = math.radians(angle_degrees % 360)
    result = []
    if options.diamond_shine_enabled:
        points = [point for face in faces for point in _pairs(face["vertices"], 2)]
        cx = (min(point[0] for point in points) + max(point[0] for point in points)) / 2
        cy = (min(point[1] for point in points) + max(point[1] for point in points)) / 2
        center = cx + .24 * cy - math.cos(angle) * (width * .8 + height * .25)
        for surface in faces:
            result.extend(_facet_cells(surface,center,width,options.diamond_shine_strength))
    if options.diamond_sparkles_enabled:
        result.extend(_sparkles(faces, options, angle, width, height))
    return result
