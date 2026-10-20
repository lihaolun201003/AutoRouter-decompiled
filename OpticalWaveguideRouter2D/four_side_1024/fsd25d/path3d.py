"""3D path assembly for the five-layer 2.5D experiment.

A route is described by a list of ``parts`` following the 2D path order:

* ``flat``        - a sub-chain of the accepted 2D XY path, constant height;
* ``transition``  - a smooth S-curve that changes height between two layers.

The transition S-curve is exactly two circular arcs of radius R=40 mm in the
vertical plane that contains the (straight, axis-aligned) local XY direction.
It is G1-continuous and has minimum 3D curvature radius 40 mm; its horizontal
footprint is ``2*R*sin(theta)`` with ``theta = acos(1 - dz/(2R))``.

All numeric helpers here are pure geometry: no router state is imported.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from ..fslw import ports
from ..d56.frames import build_frames
from . import config25d as CFG


# ---------------------------------------------------------------------------
# primitive helpers
# ---------------------------------------------------------------------------
def prim_length(prim):
    if prim['kind'] == 'line':
        p0, p1 = prim['p0'], prim['p1']
        return math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    if prim['kind'] == 'arc':
        return abs(float(prim['radius'])) * abs(float(prim['sweep']))
    raise ValueError('unknown primitive kind ' + str(prim.get('kind')))


def path_length(prims):
    return sum(prim_length(prim) for prim in prims)


def prim_point_at(prim, t):
    if prim['kind'] == 'line':
        p0, p1 = prim['p0'], prim['p1']
        return (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)
    cx, cy = prim['center']
    angle = float(prim['start_angle']) + float(prim['sweep']) * t
    radius = float(prim['radius'])
    return (cx + radius * math.cos(angle), cy + radius * math.sin(angle))


def prim_tangent_at(prim, t):
    if prim['kind'] == 'line':
        p0, p1 = prim['p0'], prim['p1']
        length = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        if length == 0.0:
            raise ValueError('zero-length line')
        return ((p1[0] - p0[0]) / length, (p1[1] - p0[1]) / length)
    angle = float(prim['start_angle']) + float(prim['sweep']) * t
    sign = 1.0 if float(prim['sweep']) >= 0.0 else -1.0
    return (-sign * math.sin(angle), sign * math.cos(angle))


def prim_split(prim, t):
    """Split one primitive at fraction ``t`` into ``(first, second)``."""
    if t <= 1e-12:
        return [], [dict(prim)]
    if t >= 1.0 - 1e-12:
        return [dict(prim)], []
    point = prim_point_at(prim, t)
    if prim['kind'] == 'line':
        first = dict(prim, p0=list(prim['p0']), p1=[point[0], point[1]])
        second = dict(prim, p0=[point[0], point[1]], p1=list(prim['p1']))
        return [first], [second]
    start = float(prim['start_angle'])
    sweep = float(prim['sweep'])
    first = dict(prim, p0=list(prim['p0']), p1=[point[0], point[1]],
                 start_angle=start, sweep=sweep * t)
    second = dict(prim, p0=[point[0], point[1]], p1=list(prim['p1']),
                  start_angle=start + sweep * t, sweep=sweep * (1.0 - t))
    return [first], [second]


def clean_primitive(prim):
    out = dict(prim)
    out.pop('layer', None)
    return out


# ---------------------------------------------------------------------------
# polyline path helpers
# ---------------------------------------------------------------------------
def path_point_at(prims, s):
    """Return ``((x, y), (tx, ty))`` at arc length ``s`` along the 2D path."""
    total = path_length(prims)
    if s < 0.0 or s > total + 1e-9:
        raise ValueError(f'path parameter {s} outside [0, {total}]')
    s = min(max(s, 0.0), total)
    remain = s
    for prim in prims:
        length = prim_length(prim)
        if remain <= length + 1e-12:
            t = 1.0 if length == 0.0 else remain / length
            return prim_point_at(prim, t), prim_tangent_at(prim, t)
        remain -= length
    last = prims[-1]
    return prim_point_at(last, 1.0), prim_tangent_at(last, 1.0)


def path_split(prims, s):
    """Split a path at arc length ``s`` into ``(head, tail)``."""
    total = path_length(prims)
    if s <= 1e-12:
        return [], [dict(p) for p in prims]
    if s >= total - 1e-12:
        return [dict(p) for p in prims], []
    head, tail = [], []
    remain = s
    placed = False
    for prim in prims:
        length = prim_length(prim)
        if not placed and remain >= length - 1e-12:
            head.append(dict(prim))
            remain -= length
            continue
        if not placed:
            t = remain / length
            first, second = prim_split(prim, t)
            head.extend(first)
            tail.extend(second)
            placed = True
            continue
        tail.append(dict(prim))
    return head, tail


def path_polyline(prims, step=CFG.ROUTE_STEP_MM):
    """Dense 2D polyline of the path (used for plotting / clearance checks)."""
    total = path_length(prims)
    count = max(2, int(math.ceil(total / step)) + 1)
    points = []
    for index in range(count + 1):
        s = total * index / count
        point, _tangent = path_point_at(prims, s)
        points.append(point)
    return points


def straight_intervals(prims):
    """``[(start_s, end_s, primitive_index)]`` for every line primitive."""
    intervals = []
    offset = 0.0
    for index, prim in enumerate(prims):
        length = prim_length(prim)
        if prim['kind'] == 'line' and length > 1e-9:
            intervals.append((offset, offset + length, index))
        offset += length
    return intervals


# ---------------------------------------------------------------------------
# transitions
# ---------------------------------------------------------------------------
def transition_theta(dz_mm, radius=CFG.RADIUS_MM):
    dz = abs(float(dz_mm))
    if dz <= 0.0:
        return 0.0
    ratio = 1.0 - dz / (2.0 * radius)
    if ratio <= -1.0:
        raise ValueError('height change too large for the given radius')
    return math.acos(max(-1.0, min(1.0, ratio)))


def make_transition(start, direction, z0, z1, radius=CFG.RADIUS_MM):
    dz = float(z1) - float(z0)
    theta = transition_theta(dz, radius)
    footprint = 2.0 * radius * math.sin(theta)
    dx, dy = float(direction[0]), float(direction[1])
    norm = math.hypot(dx, dy)
    if norm <= 0.0:
        raise ValueError('zero transition direction')
    dx, dy = dx / norm, dy / norm
    return dict(kind='transition', start=[float(start[0]), float(start[1])],
                direction=[dx, dy], z0=float(z0), z1=float(z1),
                dz_mm=dz, radius_mm=float(radius), footprint_mm=footprint,
                theta_rad=theta,
                end=[float(start[0]) + dx * footprint,
                     float(start[1]) + dy * footprint],
                length_mm=2.0 * radius * theta)


def transition_samples(transition, step=CFG.TRANSITION_STEP_MM):
    """3D samples of the S-curve, starting at ``start``/``z0`` ending at ``end``/``z1``."""
    radius = float(transition['radius_mm'])
    theta = float(transition['theta_rad'])
    z0, z1 = float(transition['z0']), float(transition['z1'])
    sign = 1.0 if z1 >= z0 else -1.0
    dz = abs(z1 - z0)
    half = 2.0 * radius * theta / 2.0
    count = max(2, int(math.ceil(half / step)))
    arc = []
    for index in range(count + 1):
        phi = theta * index / count
        u = radius * math.sin(phi)
        w = z0 + sign * radius * (1.0 - math.cos(phi))
        arc.append((u, w))
    mid_u = radius * math.sin(theta)
    mid_w = z0 + sign * dz / 2.0
    first_half = [(u, w) for u, w in arc]
    second_half = [(2.0 * mid_u - u, 2.0 * mid_w - w)
                   for u, w in reversed(arc)]
    local = first_half + second_half[1:]
    (sx, sy), (dx, dy) = transition['start'], transition['direction']
    samples = []
    for u, w in local:
        samples.append([sx + dx * u, sy + dy * u, w])
    return samples


# ---------------------------------------------------------------------------
# transition placement on a 2D path
# ---------------------------------------------------------------------------
def place_transitions(prims, base_z, travel_z, radius=CFG.RADIUS_MM,
                      port_margin=CFG.PORT_MARGIN_MM,
                      segment_margin=CFG.SEGMENT_MARGIN_MM,
                      min_travel=CFG.MIN_TRAVEL_MM, variant=0):
    """Choose climb/descent intervals on straight parts of the path.

    Returns ``dict`` with ``climb_start/climb_end/descent_start/descent_end``
    arc-length positions and the transition footprint, or ``None`` when the
    path cannot host two well separated transitions.
    """
    total = path_length(prims)
    footprint = CFG.transition_footprint(abs(float(travel_z) - float(base_z)), radius)
    if footprint <= 0.0 or total <= 2.0 * footprint + min_travel:
        return None
    climbs = []
    descents = []
    for start, end, _index in straight_intervals(prims):
        lo = start + segment_margin
        hi = end - segment_margin - footprint
        if hi < lo - 1e-9:
            continue
        climb_lo = max(lo, port_margin)
        if climb_lo <= hi + 1e-9:
            climbs.append((climb_lo, hi))
        descent_hi = min(hi, total - port_margin - footprint)
        if descent_hi >= lo - 1e-9:
            descents.append((lo, descent_hi))
    if not climbs or not descents:
        return None
    candidates = []
    for climb_lo, climb_hi in climbs:
        for descent_lo, descent_hi in descents:
            climb_start = climb_lo
            descent_start = descent_hi
            travel = descent_start - (climb_start + footprint)
            if travel < min_travel - 1e-9:
                continue
            candidates.append((travel, climb_start, descent_start))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    climb_start, descent_start = candidates[0][1], candidates[0][2]
    if variant == 1 and len(candidates) > 1:
        chosen = next((item for item in candidates
                       if item[1] > climb_start + 1e-9), candidates[-1])
        climb_start, descent_start = chosen[1], chosen[2]
    elif variant == 2 and len(candidates) > 1:
        chosen = next((item for item in candidates
                       if item[2] < descent_start - 1e-9), candidates[-1])
        climb_start, descent_start = chosen[1], chosen[2]
    return dict(footprint=footprint,
                climb_start=climb_start, climb_end=climb_start + footprint,
                descent_start=descent_start, descent_end=descent_start + footprint,
                travel_length_mm=descent_start - climb_start - footprint)


# ---------------------------------------------------------------------------
# full route assembly
# ---------------------------------------------------------------------------
def build_route3d(route_id, plane, prims, base_layer, base_z, travel_layer=None,
                  travel_z=None, radius=CFG.RADIUS_MM, variant=0):
    """Assemble the 3D route description (``parts``) for one 2D path."""
    prims = [clean_primitive(prim) for prim in prims]
    if travel_layer is None:
        parts = [dict(kind='flat', layer=int(base_layer), z_mm=float(base_z),
                      primitives=prims,
                      length_mm=path_length(prims))]
        xyz_length = path_length(prims)
        xy_length = xyz_length
        transitions = 0
    else:
        placement = place_transitions(prims, base_z, travel_z, radius,
                                      variant=variant)
        if placement is None:
            return None
        climb_start = placement['climb_start']
        climb_end = placement['climb_end']
        descent_start = placement['descent_start']
        head, rest = path_split(prims, climb_start)
        _climb_xy, after_climb = path_split(rest, placement['footprint'])
        travel, rest2 = path_split(after_climb, descent_start - climb_end)
        _descent_xy, tail = path_split(rest2, placement['footprint'])
        if (not travel) or path_length(travel) < CFG.MIN_TRAVEL_MM - 1e-6:
            return None
        start_point, start_dir = path_point_at(prims, climb_start)
        descent_point, descent_dir_forward = path_point_at(prims, descent_start)
        # the descent travels along the path direction, height decreases
        up = make_transition(start_point, start_dir, base_z, travel_z, radius)
        down = make_transition(descent_point, descent_dir_forward, travel_z,
                               base_z, radius)
        parts = [
            dict(kind='flat', layer=int(base_layer), z_mm=float(base_z),
                 primitives=head, length_mm=path_length(head)),
            dict(up, kind='transition'),
            dict(kind='flat', layer=int(travel_layer), z_mm=float(travel_z),
                 primitives=travel, length_mm=path_length(travel)),
            dict(down, kind='transition'),
            dict(kind='flat', layer=int(base_layer), z_mm=float(base_z),
                 primitives=tail, length_mm=path_length(tail)),
        ]
        transitions = 2
        xyz_length = sum(part['length_mm'] for part in parts)
        xy_length = path_length(prims)
    return dict(route_id=int(route_id), plane=plane,
                base_layer=int(base_layer), base_z_mm=float(base_z),
                travel_layer=(int(travel_layer) if travel_layer is not None else None),
                travel_z_mm=(float(travel_z) if travel_z is not None else None),
                lifted=travel_layer is not None,
                n_transitions=transitions,
                xy_length_mm=float(xy_length), length_mm=float(xyz_length),
                z_span_mm=(abs(float(travel_z) - float(base_z))
                           if travel_layer is not None else 0.0),
                parts=parts)


def flat_full_route3d(route_id, plane, prims, layer, z):
    """Flat (not lifted) route at its interface layer."""
    return build_route3d(route_id, plane, prims, layer, z, None, None)


# ---------------------------------------------------------------------------
# route samples / part queries
# ---------------------------------------------------------------------------
def part_point_at(part, t):
    """3D point at fraction ``t`` of one part (flat or transition)."""
    if part['kind'] == 'flat':
        point, _tangent = path_point_at(part['primitives'],
                                        path_length(part['primitives']) * t)
        return (point[0], point[1], float(part['z_mm']))
    samples = transition_samples(part, step=CFG.TRANSITION_STEP_MM)
    index = min(len(samples) - 1, max(0, int(round(t * (len(samples) - 1)))))
    return tuple(samples[index])


def sample_parts(parts, step_flat=CFG.ROUTE_STEP_MM,
                 step_transition=CFG.TRANSITION_STEP_MM):
    """Dense 3D polyline of a route plus the cumulative arc length per sample."""
    points = []
    lengths = []
    total = 0.0
    for part in parts:
        if part['kind'] == 'flat':
            prims = part['primitives']
            z = float(part['z_mm'])
            length = path_length(prims)
            count = max(2, int(math.ceil(length / step_flat)) + 1)
            local = []
            for index in range(count + 1):
                point, _tangent = path_point_at(prims, length * index / count)
                local.append((point[0], point[1], z))
        else:
            length = float(part['length_mm'])
            local = [tuple(sample) for sample in
                     transition_samples(part, step=step_transition)]
        for index, point in enumerate(local):
            if index == 0 and points and _distance3(points[-1], point) < 1e-9:
                continue
            if index > 0:
                total += _distance3(local[index - 1], point)
            points.append(point)
            lengths.append(total)
    return points, lengths


def _distance2(first, second):
    return math.hypot(first[0] - second[0], first[1] - second[1])


def _distance3(first, second):
    return math.sqrt((first[0] - second[0]) ** 2
                     + (first[1] - second[1]) ** 2
                     + (first[2] - second[2]) ** 2)


def route_xy_primitives(route):
    """XY projection of a 3D route (flats + transition projections)."""
    prims = []
    for part in route['parts']:
        if part['kind'] == 'flat':
            prims.extend(dict(prim) for prim in part['primitives'])
        else:
            prims.append(dict(kind='line', p0=list(part['start']),
                              p1=list(part['end'])))
    return prims


# ---------------------------------------------------------------------------
# loading the accepted 2D layouts
# ---------------------------------------------------------------------------
def load_2d_plane(scheme, plane):
    """Load one accepted 2D plane: routed primitives, failed ids, frames, ports."""
    spec = CFG.SCHEMES[scheme]
    path = CFG.baseline_plane_routes(scheme, plane)
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    routes, endpoints, _connectors, _validation = ports.load_plane('V2', plane)
    frames = build_frames(routes, endpoints)
    routed = {}
    failed = {}
    for record in payload['routes']:
        route_id = int(record['route_id'])
        if record.get('status') == 'routed':
            routed[route_id] = [clean_primitive(prim) for prim in record['primitives']]
        else:
            failed[route_id] = record
    for route_id in routed:
        frame = frames[route_id]
        prims = routed[route_id]
        start = (frame.src_xy[0], frame.src_xy[1])
        end = (frame.dst_xy[0], frame.dst_xy[1])
        if _distance2(tuple(prims[0]['p0']), start) > 1e-6:
            raise ValueError(f'route {route_id}: path does not start at its port')
        if _distance2(tuple(prims[-1]['p1']), end) > 1e-6:
            raise ValueError(f'route {route_id}: path does not end at its port')
    return dict(plane=plane, scheme=scheme, routes=routes, endpoints=endpoints,
                frames=frames, routed=routed, failed=failed,
                payload=payload, path=str(path))


def port_pose(frame, plane):
    """World port poses of one route: start point/tangent, end point/tangent."""
    start = (float(frame.src_xy[0]), float(frame.src_xy[1]))
    end = (float(frame.dst_xy[0]), float(frame.dst_xy[1]))
    start_dir = (float(frame.src_inward[0]), float(frame.src_inward[1]))
    end_dir = (-float(frame.dst_inward[0]), -float(frame.dst_inward[1]))
    return start, start_dir, end, end_dir


def write_routes_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False),
                    encoding='utf-8')
    return path


def summarize_route(route):
    flat_length = sum(part['length_mm'] for part in route['parts']
                      if part['kind'] == 'flat')
    transition_length = sum(part['length_mm'] for part in route['parts']
                            if part['kind'] == 'transition')
    return dict(lifted=bool(route['lifted']),
                n_transitions=int(route['n_transitions']),
                travel_layer=route['travel_layer'],
                travel_z_mm=route['travel_z_mm'],
                xy_length_mm=round(float(route['xy_length_mm']), 6),
                length_mm=round(float(route['length_mm']), 6),
                flat_length_mm=round(flat_length, 6),
                transition_length_mm=round(transition_length, 6),
                z_span_mm=round(float(route['z_span_mm']), 6))
