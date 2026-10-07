import copy
import json
import math
from collections import defaultdict

import topojson
from shapely.geometry import shape
from shapely.ops import unary_union


def round_arc(points, strength):
    closed = points[0] == points[-1]
    vertices = points[:-1] if closed else points
    result = []
    for i, point in enumerate(vertices):
        if not closed and i in (0, len(vertices) - 1):
            result.append(point)
            continue
        previous, following = vertices[i - 1], vertices[(i + 1) % len(vertices)]
        longitude_scale = max(.1, math.cos(math.radians(point[1])))
        a = ((previous[0] - point[0]) * longitude_scale, previous[1] - point[1])
        b = ((following[0] - point[0]) * longitude_scale, following[1] - point[1])
        la, lb = math.hypot(*a), math.hypot(*b)
        if not la or not lb or abs(a[0] * b[1] - a[1] * b[0]) < .05 * la * lb:
            result.append(point)
            continue
        # Round only a short part of each edge; keep long straight stretches intact.
        distance = min(la * .25, lb * .25, .075) * strength
        start = [point[j] + (previous[j] - point[j]) * distance / la for j in (0, 1)]
        end = [point[j] + (following[j] - point[j]) * distance / lb for j in (0, 1)]
        result.append(start)
        for t in (1 / 3, 2 / 3):
            result.append([(1 - t) ** 2 * start[j] + 2 * t * (1 - t) * point[j] + t ** 2 * end[j] for j in (0, 1)])
        result.append(end)
    rounded = []
    for point in result:
        point = [round(v, 5) for v in point]
        if not rounded or point != rounded[-1]:
            rounded.append(point)
    if closed:
        rounded.append(rounded[0])
    return rounded


def smooth_overview(value):
    topology = copy.deepcopy(value)
    transform = topology.pop('transform', None)
    if transform:
        for index, arc in enumerate(topology['arcs']):
            x = y = 0
            points = []
            for dx, dy in arc:
                x += dx
                y += dy
                points.append([round(x * transform['scale'][0] + transform['translate'][0], 5), round(y * transform['scale'][1] + transform['translate'][1], 5)])
            topology['arcs'][index] = points
    uses = defaultdict(set)

    def collect(arcs, risk):
        if isinstance(arcs, int):
            uses[arcs if arcs >= 0 else ~arcs].add(risk)
        else:
            for arc in arcs:
                collect(arc, risk)

    for obj in topology['objects'].values():
        for feature in obj['geometries']:
            collect(feature['arcs'], feature['properties']['risk'])
    shared = [i for i, risks in uses.items() if len(risks) > 1 and len(topology['arcs'][i]) > 2]

    def decode(t):
        return json.loads(topojson.Topology(t).to_geojson(decimals=5))

    original = decode(topology)
    before = [shape(f['geometry']) for f in original['features']]
    footprint = unary_union(before)

    def pieces(g):
        return list(g.geoms) if g.geom_type == 'MultiPolygon' else [g]

    def signature(g):
        return len(pieces(g)), sum(len(p.interiors) for p in pieces(g))

    def acceptable(after):
        if any(not b.is_valid or signature(a) != signature(b) for a, b in zip(before, after)):
            return False
        if any(b.area < .9 * a.area or b.area > 1.1 * a.area for a, b in zip(before, after)):
            return False
        if any(a.intersection(b).area > 1e-8 for i, a in enumerate(after) for b in after[i + 1:]):
            return False
        return footprint.symmetric_difference(unary_union(after)).area < 1e-7

    for strength in (1, .5, .25):
        candidate = copy.deepcopy(topology)
        for index in shared:
            candidate['arcs'][index] = round_arc(topology['arcs'][index], strength)
        result = decode(candidate)
        if acceptable([shape(f['geometry']) for f in result['features']]):
            return result, {'shared_arcs_rounded': sum(candidate['arcs'][i] != topology['arcs'][i] for i in shared), 'strength': strength}
    return original, {'shared_arcs_rounded': 0, 'strength': 0}
