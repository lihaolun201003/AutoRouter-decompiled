"""Analytic planar line/circular-arc geometry for the independent 1024 router.

Coordinates and radii are in millimetres; all angles are radians.  ``end_dir``
is the direction of travel *into* the destination, not its inward port normal.
No routine changes the requested radius, endpoint, or routing layer.
"""
from __future__ import annotations

import math
from typing import Iterable

import numpy as np

TAU = 2.0 * math.pi
EPS = 1e-9


def _xy(value):
    result = np.asarray(value, dtype=float)
    if result.shape != (2,) or not np.all(np.isfinite(result)):
        raise ValueError("A finite two-dimensional coordinate is required")
    return result


def _cross(a, b):
    return float(a[0] * b[1] - a[1] * b[0])


def _line(p0, p1):
    return {"kind": "line", "p0": list(map(float, p0)), "p1": list(map(float, p1))}


def _arc(p0, p1, center, radius, start_angle, sweep):
    return {"kind": "arc", "p0": list(map(float, p0)), "p1": list(map(float, p1)),
            "center": list(map(float, center)), "radius": float(radius),
            "start_angle": float(start_angle), "sweep": float(sweep)}


def fillet_polyline(points: Iterable, radius: float) -> list[dict]:
    """Replace corners with exact tangent circular arcs of the given radius.

    Repeated points and forward collinear vertices are removed.  Reversals,
    nonfinite input and overlapping adjacent fillets raise ``ValueError``.
    The two supplied endpoints remain exactly fixed.
    """
    if not math.isfinite(radius) or radius <= 0:
        raise ValueError("radius must be positive and finite")
    vertices = []
    for point in points:
        point = _xy(point)
        if vertices and np.linalg.norm(point - vertices[-1]) < EPS:
            continue
        vertices.append(point)
        while len(vertices) >= 3:
            a, b, c = vertices[-3:]
            u, v = b - a, c - b
            lu, lv = np.linalg.norm(u), np.linalg.norm(v)
            if abs(_cross(u, v)) > EPS * lu * lv:
                break
            if np.dot(u, v) <= 0:
                raise ValueError("Polyline reverses direction")
            vertices.pop(-2)
    if len(vertices) < 2:
        raise ValueError("At least two distinct points are required")
    n = len(vertices)
    trims = np.zeros(n)
    turns = np.zeros(n)
    for i in range(1, n - 1):
        u, v = vertices[i] - vertices[i - 1], vertices[i + 1] - vertices[i]
        u, v = u / np.linalg.norm(u), v / np.linalg.norm(v)
        angle = math.atan2(_cross(u, v), float(np.dot(u, v)))
        if abs(math.pi - abs(angle)) < EPS:
            raise ValueError("Polyline reverses direction")
        turns[i] = angle
        trims[i] = radius * math.tan(abs(angle) / 2.0)
    for i in range(n - 1):
        available = np.linalg.norm(vertices[i + 1] - vertices[i])
        if trims[i] + trims[i + 1] > available + 1e-8:
            raise ValueError(f"Insufficient segment length for radius at segment {i}")
    result = []
    cursor = vertices[0]
    for i in range(1, n - 1):
        incoming = vertices[i] - vertices[i - 1]
        outgoing = vertices[i + 1] - vertices[i]
        incoming /= np.linalg.norm(incoming)
        outgoing /= np.linalg.norm(outgoing)
        pin = vertices[i] - trims[i] * incoming
        pout = vertices[i] + trims[i] * outgoing
        if np.linalg.norm(pin - cursor) > EPS:
            result.append(_line(cursor, pin))
        if abs(turns[i]) > EPS:
            sign = math.copysign(1.0, turns[i])
            center = pin + sign * radius * np.array([-incoming[1], incoming[0]])
            start_angle = math.atan2(pin[1] - center[1], pin[0] - center[0])
            result.append(_arc(pin, pout, center, radius, start_angle, turns[i]))
        cursor = pout
    if np.linalg.norm(vertices[-1] - cursor) > EPS:
        result.append(_line(cursor, vertices[-1]))
    return result


def _mod(angle):
    value = angle % TAU
    return 0.0 if min(value, TAU - value) < 1e-11 else value


def dubins(start, end, radius: float) -> list[list[dict]]:
    """Return feasible analytic LSL/RSR/LSR/RSL/RLR/LRL paths by length.

    Poses have the form ``(x, y, heading)``.  Feasibility here refers only to
    the pose/radius equations; callers must reject paths outside the board or
    conflicting with other waveguides.  All six families are considered.
    """
    if radius <= 0 or not math.isfinite(radius):
        raise ValueError("radius must be positive and finite")
    start, end = np.asarray(start, dtype=float), np.asarray(end, dtype=float)
    if start.shape != (3,) or end.shape != (3,) or not np.all(np.isfinite([start, end])):
        raise ValueError("Poses must be finite (x, y, heading) triples")
    delta = end[:2] - start[:2]
    d = float(np.linalg.norm(delta) / radius)
    theta = math.atan2(delta[1], delta[0])
    a, b = _mod(start[2] - theta), _mod(end[2] - theta)
    sa, sb, ca, cb, cab = math.sin(a), math.sin(b), math.cos(a), math.cos(b), math.cos(a-b)
    solutions = []
    p2 = 2 + d*d - 2*cab + 2*d*(sa-sb)
    if p2 >= -EPS:
        tmp = math.atan2(cb-ca, d+sa-sb)
        solutions.append(("LSL", (_mod(-a+tmp), math.sqrt(max(0., p2)), _mod(b-tmp))))
    p2 = 2 + d*d - 2*cab + 2*d*(sb-sa)
    if p2 >= -EPS:
        tmp = math.atan2(ca-cb, d-sa+sb)
        solutions.append(("RSR", (_mod(a-tmp), math.sqrt(max(0., p2)), _mod(-b+tmp))))
    p2 = -2 + d*d + 2*cab + 2*d*(sa+sb)
    if p2 >= -EPS:
        p = math.sqrt(max(0., p2))
        tmp = math.atan2(-ca-cb, d+sa+sb) - math.atan2(-2., p)
        solutions.append(("LSR", (_mod(-a+tmp), p, _mod(-b+tmp))))
    p2 = d*d - 2 + 2*cab - 2*d*(sa+sb)
    if p2 >= -EPS:
        p = math.sqrt(max(0., p2))
        tmp = math.atan2(ca+cb, d-sa-sb) - math.atan2(2., p)
        solutions.append(("RSL", (_mod(a-tmp), p, _mod(b-tmp))))
    tmp = (6-d*d+2*cab+2*d*(sa-sb))/8.
    if abs(tmp) <= 1+EPS:
        p = _mod(TAU-math.acos(max(-1., min(1., tmp))))
        t = _mod(a-math.atan2(ca-cb, d-sa+sb)+p/2.)
        solutions.append(("RLR", (t, p, _mod(a-b-t+p))))
    tmp = (6-d*d+2*cab+2*d*(-sa+sb))/8.
    if abs(tmp) <= 1+EPS:
        p = _mod(TAU-math.acos(max(-1., min(1., tmp))))
        t = _mod(-a-math.atan2(ca-cb, d+sa-sb)+p/2.)
        solutions.append(("LRL", (t, p, _mod(b-a-t+p))))
    result = []
    for family, params in solutions:
        primitives = []
        cursor = start[:2].copy()
        heading = float(start[2])
        for kind, parameter in zip(family, params):
            if parameter < 1e-11:
                continue
            if kind == "S":
                destination = cursor + radius*parameter*np.array([math.cos(heading), math.sin(heading)])
                primitives.append(_line(cursor, destination))
            else:
                sign = 1. if kind == "L" else -1.
                center = cursor + sign*radius*np.array([-math.sin(heading), math.cos(heading)])
                angle = heading-sign*math.pi/2.
                sweep = sign*parameter
                destination = center + radius*np.array([math.cos(angle+sweep), math.sin(angle+sweep)])
                primitives.append(_arc(cursor, destination, center, radius, angle, sweep))
                heading += sweep
            cursor = destination
        # Analytic integration must reproduce the requested pose to roundoff.
        if np.linalg.norm(cursor-end[:2]) > 1e-6 or abs(math.atan2(math.sin(heading-end[2]), math.cos(heading-end[2]))) > 1e-7:
            raise ArithmeticError(f"Dubins family {family} did not reproduce the requested pose")
        if primitives:
            primitives[0]["p0"] = start[:2].tolist()
            primitives[-1]["p1"] = end[:2].tolist()
            result.append(primitives)
    result.sort(key=length)
    return result


def length(primitives) -> float:
    """Exact centerline length in millimetres."""
    return float(sum(np.linalg.norm(np.asarray(p["p1"])-p["p0"]) if p["kind"] == "line"
                     else abs(p["sweep"])*p["radius"] for p in primitives))


def sample(primitives, sagitta: float = .0005) -> np.ndarray:
    """Chordal centerline samples, bounded by the specified arc sagitta.

    Straight primitives contain endpoints only.  Primitive junctions and the
    two exact route endpoints are always represented.
    """
    if sagitta <= 0 or not math.isfinite(sagitta):
        raise ValueError("sagitta must be positive and finite")
    pieces = []
    for primitive in primitives:
        if primitive["kind"] == "line":
            points = np.asarray([primitive["p0"], primitive["p1"]], dtype=float)
        elif primitive["kind"] == "arc":
            r = primitive["radius"]
            step = 2*math.acos(max(-1., min(1., 1-sagitta/r)))
            count = max(1, int(math.ceil(abs(primitive["sweep"])/max(step, 1e-12))))
            angles = primitive["start_angle"] + np.linspace(0, primitive["sweep"], count+1)
            points = np.asarray(primitive["center"])+r*np.column_stack([np.cos(angles), np.sin(angles)])
            points[0], points[-1] = primitive["p0"], primitive["p1"]
        else:
            raise ValueError(f"Unknown primitive: {primitive['kind']}")
        pieces.append(points if not pieces else points[1:])
    return np.vstack(pieces) if pieces else np.empty((0, 2))


def _on_arc(angle, primitive, tol=1e-8, interior=False):
    sweep = primitive["sweep"]
    distance = ((angle-primitive["start_angle"]) if sweep >= 0 else (primitive["start_angle"]-angle)) % TAU
    if distance > TAU-tol:
        distance = 0.
    if interior:
        return tol < distance < abs(sweep)-tol
    return distance <= abs(sweep)+tol


def _tangent(primitive, end=False):
    if primitive["kind"] == "line":
        direction = np.asarray(primitive["p1"])-primitive["p0"]
        norm = np.linalg.norm(direction)
        return direction/norm if norm > EPS else np.array([np.nan, np.nan])
    angle = primitive["start_angle"]+(primitive["sweep"] if end else 0.)
    return math.copysign(1., primitive["sweep"])*np.array([-math.sin(angle), math.cos(angle)])


def _direction(value):
    if np.isscalar(value):
        return np.array([math.cos(float(value)), math.sin(float(value))])
    vector = _xy(value)
    if np.linalg.norm(vector) < EPS:
        raise ValueError("Port direction cannot be zero")
    return vector/np.linalg.norm(vector)


def bounds(primitive, width=0.):
    """Exact axis-aligned extents of an uncapped stroked primitive.

    Flat port faces allow endpoints on the board boundary while preserving
    transverse half-width clearance; no endpoint-coordinate exception is used.
    """
    half = width/2.
    if primitive["kind"] == "line":
        tangent = _tangent(primitive)
        normal = half*np.array([-tangent[1], tangent[0]])
        p0, p1 = np.asarray(primitive["p0"]), np.asarray(primitive["p1"])
        points = np.asarray([p0+normal, p0-normal, p1+normal, p1-normal])
    else:
        angles = [primitive["start_angle"], primitive["start_angle"]+primitive["sweep"]]
        angles += [a for a in (0., math.pi/2, math.pi, 3*math.pi/2) if _on_arc(a, primitive)]
        unit = np.column_stack([np.cos(angles), np.sin(angles)])
        center = np.asarray(primitive["center"])
        points = np.vstack([center+(primitive["radius"]-half)*unit,
                            center+(primitive["radius"]+half)*unit])
    return (float(points[:,0].min()), float(points[:,1].min()),
            float(points[:,0].max()), float(points[:,1].max()))


def intersections(first, second, tol=1e-8):
    """Exact centerline intersections: ``(points, has_positive_length_overlap)``."""
    fline, sline = first["kind"] == "line", second["kind"] == "line"
    if fline and sline:
        p, q = np.asarray(first["p0"]), np.asarray(second["p0"])
        u, v = np.asarray(first["p1"])-p, np.asarray(second["p1"])-q
        cross = _cross(u, v)
        if abs(cross) > tol:
            t, s = _cross(q-p, v)/cross, _cross(q-p, u)/cross
            return ([p+t*u] if -tol <= t <= 1+tol and -tol <= s <= 1+tol else []), False
        if abs(_cross(q-p, u)) > tol or np.dot(u,u) < EPS:
            return [], False
        limits = sorted([float(np.dot(q-p,u)/np.dot(u,u)), float(np.dot(q+v-p,u)/np.dot(u,u))])
        lo, hi = max(0., limits[0]), min(1., limits[1])
        if hi < lo-tol:
            return [], False
        return [p+lo*u], (hi-lo)*np.linalg.norm(u) > tol
    if fline or sline:
        line, arc = (first, second) if fline else (second, first)
        p = np.asarray(line["p0"])
        v = np.asarray(line["p1"])-p
        offset = p-np.asarray(arc["center"])
        aa = float(np.dot(v,v))
        if aa < EPS:
            return [], False
        # Project in distance units to avoid cancellation in the quadratic
        # discriminant at tangent G1 junctions (long lines magnify that error).
        span = math.sqrt(aa)
        unit = v/span
        projection = -float(np.dot(offset,unit))
        nearest = offset+projection*unit
        height2 = arc["radius"]**2-float(np.dot(nearest,nearest))
        roundoff = 64*np.finfo(float).eps*max(1.,float(np.dot(offset,offset)),arc["radius"]**2)
        if height2 < -roundoff:
            return [], False
        if abs(height2) <= roundoff:
            height2 = 0.
        root = math.sqrt(max(0.,height2))
        points = []
        for t in ((projection-root)/span,(projection+root)/span):
            if -tol <= t <= 1+tol:
                point = p+t*v
                angle = math.atan2(point[1]-arc["center"][1], point[0]-arc["center"][0])
                if _on_arc(angle, arc) and not any(np.linalg.norm(point-other)<tol for other in points):
                    points.append(point)
        return points, False
    c0, c1 = np.asarray(first["center"]), np.asarray(second["center"])
    r0, r1 = first["radius"], second["radius"]
    delta = c1-c0
    distance = float(np.linalg.norm(delta))
    if distance < tol and abs(r0-r1) < tol:
        overlap = False
        points = []
        for primitive, other in ((first,second), (second,first)):
            for fraction in (0., .5, 1.):
                angle = primitive["start_angle"]+fraction*primitive["sweep"]
                if _on_arc(angle, other, interior=True):
                    overlap = True
                elif _on_arc(angle, other):
                    point = c0+r0*np.array([math.cos(angle),math.sin(angle)])
                    if not any(np.linalg.norm(point-p)<tol for p in points):
                        points.append(point)
        return points, overlap
    if distance < tol or distance > r0+r1+tol or distance < abs(r0-r1)-tol:
        return [], False
    chord = (r0*r0-r1*r1+distance*distance)/(2*distance)
    height2 = r0*r0-chord*chord
    if abs(height2) <= 64*np.finfo(float).eps*max(1.,r0*r0,r1*r1,distance*distance):
        height2 = 0.
    height = math.sqrt(max(0.,height2))
    unit = delta/distance
    middle = c0+chord*unit
    offset = height*np.array([-unit[1],unit[0]])
    points = []
    for point in (middle+offset,middle-offset):
        angles = [math.atan2(point[1]-c[1],point[0]-c[0]) for c in (c0,c1)]
        if _on_arc(angles[0],first) and _on_arc(angles[1],second) and not any(np.linalg.norm(point-p)<tol for p in points):
            points.append(point)
    return points, False


def validate(primitives, start_xy, end_xy, start_dir, end_dir,
             board=150., width=.05, min_radius=5.) -> list[str]:
    """Check exact poses, G1, radius, stroked board bounds and self-intersections.

    ``board`` may be a side length, ``(width,height)``, or
    ``(xmin,ymin,xmax,ymax)``.  Direction arguments accept an angle or vector.
    Empty output means all these checks passed; inter-route checks are separate.
    """
    errors = []
    if not primitives:
        return ["empty_geometry"]
    if np.isscalar(board):
        board = (0.,0.,float(board),float(board))
    elif len(board) == 2:
        board = (0.,0.,float(board[0]),float(board[1]))
    if np.linalg.norm(np.asarray(primitives[0]["p0"])-_xy(start_xy)) > 1e-7:
        errors.append("start_endpoint_mismatch")
    if np.linalg.norm(np.asarray(primitives[-1]["p1"])-_xy(end_xy)) > 1e-7:
        errors.append("end_endpoint_mismatch")
    if np.linalg.norm(_tangent(primitives[0])-_direction(start_dir)) > 1e-7:
        errors.append("start_tangent_mismatch")
    if np.linalg.norm(_tangent(primitives[-1],True)-_direction(end_dir)) > 1e-7:
        errors.append("end_tangent_mismatch")
    boxes = []
    for i, primitive in enumerate(primitives):
        if primitive.get("layer",0) != 0:
            errors.append(f"nonzero_layer:{i}")
        try:
            for key in ("p0","p1"):
                _xy(primitive[key])
            if primitive["kind"] == "arc":
                center = _xy(primitive["center"])
                r, a, sweep = primitive["radius"], primitive["start_angle"], primitive["sweep"]
                if not all(math.isfinite(v) for v in (r,a,sweep)):
                    raise ValueError("nonfinite arc")
                if r < min_radius-1e-8:
                    errors.append(f"radius_below_minimum:{i}")
                if abs(sweep) < EPS or abs(sweep) > TAU+1e-8:
                    errors.append(f"invalid_arc_sweep:{i}")
                for key, angle in (("p0",a),("p1",a+sweep)):
                    calculated = center+r*np.array([math.cos(angle),math.sin(angle)])
                    if np.linalg.norm(calculated-primitive[key]) > 1e-7:
                        errors.append(f"arc_endpoint_inconsistent:{i}:{key}")
            elif primitive["kind"] == "line":
                if np.linalg.norm(np.asarray(primitive["p1"])-primitive["p0"]) < EPS:
                    errors.append(f"zero_length_line:{i}")
            else:
                raise ValueError("unknown primitive")
            box = bounds(primitive,width)
            boxes.append(bounds(primitive))
            if box[0] < board[0]-1e-8 or box[1] < board[1]-1e-8 or box[2] > board[2]+1e-8 or box[3] > board[3]+1e-8:
                errors.append(f"board_out_of_bounds:{i}")
        except (ValueError, KeyError, TypeError, FloatingPointError):
            errors.append(f"invalid_primitive:{i}")
            return errors
        if i:
            previous = primitives[i-1]
            if np.linalg.norm(np.asarray(previous["p1"])-primitive["p0"]) > 1e-7:
                errors.append(f"discontinuous_position:{i-1}:{i}")
            if np.linalg.norm(_tangent(previous,True)-_tangent(primitive)) > 1e-7:
                errors.append(f"discontinuous_tangent:{i-1}:{i}")
    for i, first in enumerate(primitives):
        for j in range(i+1,len(primitives)):
            b0, b1 = boxes[i], boxes[j]
            if b0[2] < b1[0]-EPS or b1[2] < b0[0]-EPS or b0[3] < b1[1]-EPS or b1[3] < b0[1]-EPS:
                continue
            points, overlap = intersections(first,primitives[j])
            if overlap:
                errors.append(f"self_overlap:{i}:{j}")
            if any(j != i+1 or np.linalg.norm(point-np.asarray(first["p1"])) > 1e-7 for point in points):
                errors.append(f"self_intersection:{i}:{j}")
    return errors
