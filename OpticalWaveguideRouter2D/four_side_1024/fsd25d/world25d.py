"""2D layer bookkeeping and true 3D clearance world for the 2.5D experiment.

* :class:`LayerWorld` keeps one exact strict 2D index per routing height; every
  flat route part is registered there (same-layer strict rules are enforced by
  the frozen ``d56.index.D56Index`` strict policy).
* :class:`ClearanceWorld3D` tracks the true 3D geometry of the placed routes and
  answers "does this candidate route keep >= 0.08 mm 3D centreline clearance to
  everything already placed?"  Flat-to-flat pairs on the *same* layer are
  covered by the strict 2D index; flat-to-flat pairs on different layers are
  vertically separated by >= 0.125 mm so they are safe by construction.  All
  remaining checks are transition-related and are done explicitly here.

Performance: every clearance check uses a coarse-to-fine scheme.  Coarse samples
are 0.25 mm apart; because the distance function along a curve is 1-Lipschitz,
a coarse minimum minus 0.125 mm is a certified lower bound, so most
(accepted) candidates never need the fine pass.  The router uses a conservative
acceptance threshold (>= 0.09 mm certified) so the independent validator never
sees a violating route.
"""
from __future__ import annotations

import math

from ..d56.index import D56Index, prepare
from . import config25d as CFG
from . import path3d as P

EPS = 1e-9
GRID_CELL_MM = 0.5
TRANSITION_GRID_MM = 0.6
CLEARANCE_MARGIN_MM = 0.004
DENSE_STEP_MM = 0.02
COARSE_STEP_MM = 0.25
SEGMENT_STEP_MM = 0.1
COARSE_SAFETY_MM = COARSE_STEP_MM / 2.0        # 1-Lipschitz safety
PAIR_COARSE_SAFETY_MM = COARSE_STEP_MM          # two curves
FINE_POINT_SAFETY_MM = DENSE_STEP_MM / 2.0      # 1-Lipschitz, point-sampled checks
MARGIN_MM = 0.001
ACCEPT_POINT_MM = CFG.CLEARANCE_MM + FINE_POINT_SAFETY_MM + MARGIN_MM
ACCEPT_SEGMENT_MM = CFG.CLEARANCE_MM + MARGIN_MM


# ---------------------------------------------------------------------------
# 2D point / primitive distance
# ---------------------------------------------------------------------------
def point_segment_distance_2d(point, a, b):
    px, py = point[0], point[1]
    ax, ay = a[0], a[1]
    bx, by = b[0], b[1]
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 <= EPS:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / length2
    t = min(1.0, max(0.0, t))
    qx, qy = ax + t * dx, ay + t * dy
    return math.hypot(px - qx, py - qy)


def _angle_in_arc(angle, start, sweep):
    two_pi = 2.0 * math.pi
    if sweep >= 0.0:
        delta = (angle - start) % two_pi
        return delta <= sweep + 1e-12
    delta = (start - angle) % two_pi
    return delta <= (-sweep) + 1e-12


def point_primitive_distance_2d(point, prim):
    if prim['kind'] == 'line':
        return point_segment_distance_2d(point, prim['p0'], prim['p1'])
    cx, cy = prim['center']
    radius = float(prim['radius'])
    vector = (point[0] - cx, point[1] - cy)
    distance = math.hypot(vector[0], vector[1])
    angle = math.atan2(vector[1], vector[0])
    if _angle_in_arc(angle, float(prim['start_angle']), float(prim['sweep'])):
        return abs(distance - radius)
    return min(math.hypot(point[0] - prim['p0'][0], point[1] - prim['p0'][1]),
               math.hypot(point[0] - prim['p1'][0], point[1] - prim['p1'][1]))


def primitive_bbox(prim):
    if prim['kind'] == 'line':
        x0, y0 = prim['p0']
        x1, y1 = prim['p1']
        return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
    cx, cy = prim['center']
    radius = float(prim['radius'])
    start = float(prim['start_angle'])
    sweep = float(prim['sweep'])
    xs = [prim['p0'][0], prim['p1'][0]]
    ys = [prim['p0'][1], prim['p1'][1]]
    for k in range(-4, 13):
        angle = k * math.pi / 2.0
        if _angle_in_arc(angle, start, sweep):
            xs.append(cx + radius * math.cos(angle))
            ys.append(cy + radius * math.sin(angle))
    return (min(xs), min(ys), max(xs), max(ys))


# ---------------------------------------------------------------------------
# 3D segment-segment distance (used for fine transition-vs-transition checks)
# ---------------------------------------------------------------------------
def segment_segment_distance_3d(p0, p1, q0, q1):
    """Minimum distance between two 3D segments."""
    d1 = [p1[i] - p0[i] for i in range(3)]
    d2 = [q1[i] - q0[i] for i in range(3)]
    r = [p0[i] - q0[i] for i in range(3)]
    a = sum(value * value for value in d1)
    e = sum(value * value for value in d2)
    f = sum(d2[i] * r[i] for i in range(3))
    if a <= EPS and e <= EPS:
        return math.sqrt(sum(value * value for value in r))
    if a <= EPS:
        s = 0.0
        t = min(1.0, max(0.0, f / e))
    else:
        c = sum(d1[i] * r[i] for i in range(3))
        if e <= EPS:
            t = 0.0
            s = min(1.0, max(0.0, -c / a))
        else:
            b = sum(d1[i] * d2[i] for i in range(3))
            denominator = a * e - b * b
            if denominator > EPS:
                s = min(1.0, max(0.0, (b * f - c * e) / denominator))
            else:
                s = 0.0
            t = (b * s + f) / e
            if t < 0.0:
                t = 0.0
                s = min(1.0, max(0.0, -c / a))
            elif t > 1.0:
                t = 1.0
                s = min(1.0, max(0.0, (b - c) / a))
    closest_p = [p0[i] + d1[i] * s for i in range(3)]
    closest_q = [q0[i] + d2[i] * t for i in range(3)]
    return math.sqrt(sum((closest_p[i] - closest_q[i]) ** 2 for i in range(3)))


# ---------------------------------------------------------------------------
# per-layer 2D strict index
# ---------------------------------------------------------------------------
class LayerWorld:
    def __init__(self):
        self.indices = {}
        self.parts = {}

    def index(self, layer):
        index = self.indices.get(layer)
        if index is None:
            index = D56Index(width=CFG.WIDTH_MM, gap=CFG.EDGE_GAP_MM,
                             sagitta=CFG.SAGITTA_MM,
                             min_cross_angle_deg=CFG.MIN_CROSS_ANGLE_DEG,
                             crossing_policy=CFG.CROSSING_POLICY)
            self.indices[layer] = index
            self.parts[layer] = {}
        return index

    def evaluate(self, prims, layer):
        if not prims:
            return None
        return self.index(layer).evaluate(prepare(prims))

    def add(self, part_id, prims, layer):
        if not prims:
            return
        self.index(layer).add(part_id, prepare(prims))
        self.parts[layer][part_id] = list(prims)

    def remove(self, part_id, layer):
        self.index(layer).remove(part_id)
        self.parts.get(layer, {}).pop(part_id, None)


# ---------------------------------------------------------------------------
# true 3D clearance world
# ---------------------------------------------------------------------------
class ClearanceWorld3D:
    def __init__(self, clearance=CFG.CLEARANCE_MM):
        self.clearance = float(clearance)
        self.accept_point = self.clearance + FINE_POINT_SAFETY_MM + MARGIN_MM
        self.accept_segment = self.clearance + MARGIN_MM
        self.coarse_threshold = self.accept_point + COARSE_SAFETY_MM
        self.pair_threshold = self.accept_segment + PAIR_COARSE_SAFETY_MM
        self.cells = {}
        self.transitions = []
        self.transition_cells = {}

    # -- broad phase -------------------------------------------------------
    @staticmethod
    def _cell_key(x, y, size=GRID_CELL_MM):
        return (int(math.floor(x / size)), int(math.floor(y / size)))

    def _insert_flat(self, prim, z, route_id):
        bbox = primitive_bbox(prim)
        entry = dict(prim=prim, z=float(z), route_id=int(route_id), bbox=bbox)
        x0 = int(math.floor((bbox[0] - GRID_CELL_MM) / GRID_CELL_MM))
        x1 = int(math.floor((bbox[2] + GRID_CELL_MM) / GRID_CELL_MM))
        y0 = int(math.floor((bbox[1] - GRID_CELL_MM) / GRID_CELL_MM))
        y1 = int(math.floor((bbox[3] + GRID_CELL_MM) / GRID_CELL_MM))
        for ix in range(x0, x1 + 1):
            for iy in range(y0, y1 + 1):
                self.cells.setdefault((ix, iy), []).append(entry)

    def _query_flats(self, x, y):
        key = self._cell_key(x, y)
        found = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                found.extend(self.cells.get((key[0] + dx, key[1] + dy), ()))
        return found

    def _flat_candidates_in_bbox(self, bbox):
        x0 = int(math.floor((bbox[0] - GRID_CELL_MM) / GRID_CELL_MM))
        x1 = int(math.floor((bbox[2] + GRID_CELL_MM) / GRID_CELL_MM))
        y0 = int(math.floor((bbox[1] - GRID_CELL_MM) / GRID_CELL_MM))
        y1 = int(math.floor((bbox[3] + GRID_CELL_MM) / GRID_CELL_MM))
        entries = []
        seen = set()
        for ix in range(x0, x1 + 1):
            for iy in range(y0, y1 + 1):
                for entry in self.cells.get((ix, iy), ()):
                    identifier = id(entry)
                    if identifier in seen:
                        continue
                    seen.add(identifier)
                    entries.append(entry)
        return entries

    def _insert_transition(self, record):
        bbox = record['bbox']
        x0 = int(math.floor((bbox[0] - TRANSITION_GRID_MM) / TRANSITION_GRID_MM))
        x1 = int(math.floor((bbox[2] + TRANSITION_GRID_MM) / TRANSITION_GRID_MM))
        y0 = int(math.floor((bbox[1] - TRANSITION_GRID_MM) / TRANSITION_GRID_MM))
        y1 = int(math.floor((bbox[3] + TRANSITION_GRID_MM) / TRANSITION_GRID_MM))
        for ix in range(x0, x1 + 1):
            for iy in range(y0, y1 + 1):
                self.transition_cells.setdefault((ix, iy), []).append(record)
        self.transitions.append(record)

    def _query_transitions(self, bbox):
        x0 = int(math.floor((bbox[0] - TRANSITION_GRID_MM) / TRANSITION_GRID_MM))
        x1 = int(math.floor((bbox[2] + TRANSITION_GRID_MM) / TRANSITION_GRID_MM))
        y0 = int(math.floor((bbox[1] - TRANSITION_GRID_MM) / TRANSITION_GRID_MM))
        y1 = int(math.floor((bbox[3] + TRANSITION_GRID_MM) / TRANSITION_GRID_MM))
        found = []
        seen = set()
        for ix in range(x0, x1 + 1):
            for iy in range(y0, y1 + 1):
                for record in self.transition_cells.get((ix, iy), ()):
                    identifier = id(record)
                    if identifier in seen:
                        continue
                    seen.add(identifier)
                    found.append(record)
        return found

    # -- geometry helpers --------------------------------------------------
    @staticmethod
    def _transition_record(route_id, part):
        dense = [tuple(sample) for sample in
                 P.transition_samples(part, step=DENSE_STEP_MM)]
        coarse = [tuple(sample) for sample in
                  P.transition_samples(part, step=COARSE_STEP_MM)]
        xs = [sample[0] for sample in dense]
        ys = [sample[1] for sample in dense]
        return dict(route_id=int(route_id), dense=dense, coarse=coarse,
                    bbox=(min(xs), min(ys), max(xs), max(ys)))

    # -- building ----------------------------------------------------------
    def add_route(self, route):
        for part in route['parts']:
            if part['kind'] == 'flat':
                for prim in part['primitives']:
                    self._insert_flat(prim, part['z_mm'], route['route_id'])
            else:
                self._insert_transition(
                    self._transition_record(route['route_id'], part))

    # -- checks ------------------------------------------------------------
    def _transition_vs_flats(self, part, route_id):
        points = [tuple(sample) for sample in
                  P.transition_samples(part, step=DENSE_STEP_MM)]
        stride = max(1, int(round(COARSE_STEP_MM / DENSE_STEP_MM)))
        coarse = points[::stride]
        if coarse[-1] != points[-1]:
            coarse.append(points[-1])
        xs = [sample[0] for sample in coarse]
        ys = [sample[1] for sample in coarse]
        probe_bbox = (min(xs) - GRID_CELL_MM, min(ys) - GRID_CELL_MM,
                      max(xs) + GRID_CELL_MM, max(ys) + GRID_CELL_MM)
        if not self._flat_candidates_in_bbox(probe_bbox):
            return []
        coarse_min = float('inf')
        coarse_worst = None
        suspects = []
        for index, sample in enumerate(coarse):
            found_near = False
            for entry in self._query_flats(sample[0], sample[1]):
                bbox = entry['bbox']
                if (sample[0] < bbox[0] - GRID_CELL_MM
                        or sample[0] > bbox[2] + GRID_CELL_MM
                        or sample[1] < bbox[1] - GRID_CELL_MM
                        or sample[1] > bbox[3] + GRID_CELL_MM):
                    continue
                distance2 = point_primitive_distance_2d(sample, entry['prim'])
                if distance2 >= GRID_CELL_MM:
                    continue
                distance3 = math.hypot(distance2, sample[2] - entry['z'])
                if distance3 < coarse_min:
                    coarse_min = distance3
                    coarse_worst = (sample, entry)
                if distance3 < self.coarse_threshold:
                    found_near = True
            if found_near:
                suspects.append(index)
            if coarse_min < self.clearance:
                break
        if coarse_min < self.clearance:
            sample, entry = coarse_worst
            return [dict(kind='transition_vs_flat',
                         other_route=int(entry['route_id']),
                         route_id=int(route_id),
                         point=[round(value, 6) for value in sample],
                         distance_mm=round(coarse_min, 6))]
        if coarse_min - COARSE_SAFETY_MM >= self.accept_point:
            return []
        if not suspects:
            return []
        fine_indices = set()
        for index in suspects:
            for offset in range(-2, 3):
                coarse_index = index + offset
                if 0 <= coarse_index < len(coarse):
                    for fine_index in range(max(0, coarse_index * stride - stride),
                                            min(len(points),
                                                coarse_index * stride + stride + 1)):
                        fine_indices.add(fine_index)
        violations = []
        for fine_index in sorted(fine_indices):
            sample = points[fine_index]
            for entry in self._query_flats(sample[0], sample[1]):
                bbox = entry['bbox']
                if (sample[0] < bbox[0] - GRID_CELL_MM
                        or sample[0] > bbox[2] + GRID_CELL_MM
                        or sample[1] < bbox[1] - GRID_CELL_MM
                        or sample[1] > bbox[3] + GRID_CELL_MM):
                    continue
                distance2 = point_primitive_distance_2d(sample, entry['prim'])
                if distance2 >= GRID_CELL_MM:
                    continue
                distance3 = math.hypot(distance2, sample[2] - entry['z'])
                if distance3 < self.accept_point:
                    violations.append(dict(kind='transition_vs_flat',
                                           other_route=int(entry['route_id']),
                                           route_id=int(route_id),
                                           point=[round(value, 6) for value in sample],
                                           distance_mm=round(distance3, 6)))
                    if len(violations) >= 3:
                        return violations
        return violations

    def _flat_vs_transitions(self, prims, z, route_id):
        violations = []
        for prim in prims:
            bbox = primitive_bbox(prim)
            for record in self._query_transitions(bbox):
                coarse_min = float('inf')
                coarse_worst = None
                for sample in record['coarse']:
                    distance2 = point_primitive_distance_2d(sample, prim)
                    if distance2 >= GRID_CELL_MM:
                        continue
                    distance3 = math.hypot(distance2, sample[2] - z)
                    if distance3 < coarse_min:
                        coarse_min = distance3
                        coarse_worst = sample
                    if coarse_min < self.clearance:
                        break
                if coarse_min < self.clearance:
                    violations.append(dict(kind='flat_vs_transition',
                                           other_route=int(record['route_id']),
                                           route_id=int(route_id),
                                           point=[round(value, 6) for value in coarse_worst],
                                           distance_mm=round(coarse_min, 6)))
                    if len(violations) >= 3:
                        return violations
                    continue
                if coarse_min - COARSE_SAFETY_MM >= self.accept_point:
                    continue
                best = float('inf')
                best_point = None
                for sample in record['dense']:
                    distance2 = point_primitive_distance_2d(sample, prim)
                    if distance2 >= GRID_CELL_MM:
                        continue
                    distance3 = math.hypot(distance2, sample[2] - z)
                    if distance3 < best:
                        best = distance3
                        best_point = sample
                if best < self.accept_point:
                    violations.append(dict(kind='flat_vs_transition',
                                           other_route=int(record['route_id']),
                                           route_id=int(route_id),
                                           point=[round(value, 6) for value in best_point],
                                           distance_mm=round(best, 6)))
                    if len(violations) >= 3:
                        return violations
        return violations

    def _transition_vs_transitions(self, part, route_id):
        record = self._transition_record(route_id, part)
        violations = []
        for other in self._query_transitions(record['bbox']):
            if int(other['route_id']) == int(route_id):
                continue
            coarse_min = float('inf')
            coarse_worst = None
            for sample in record['coarse']:
                for other_sample in other['coarse']:
                    distance = math.sqrt(
                        (sample[0] - other_sample[0]) ** 2
                        + (sample[1] - other_sample[1]) ** 2
                        + (sample[2] - other_sample[2]) ** 2)
                    if distance < coarse_min:
                        coarse_min = distance
                        coarse_worst = sample
                if coarse_min < self.clearance:
                    break
            if coarse_min < self.clearance:
                violations.append(dict(kind='transition_vs_transition',
                                       other_route=int(other['route_id']),
                                       route_id=int(route_id),
                                       point=[round(value, 6) for value in coarse_worst],
                                       distance_mm=round(coarse_min, 6)))
                if len(violations) >= 3:
                    return violations
                continue
            if coarse_min - PAIR_COARSE_SAFETY_MM >= self.accept_segment:
                continue
            poly = _polyline(record['dense'], max(1, int(round(
                SEGMENT_STEP_MM / DENSE_STEP_MM))))
            other_poly = _polyline(other['dense'], max(1, int(round(
                SEGMENT_STEP_MM / DENSE_STEP_MM))))
            best = float('inf')
            best_point = None
            for index in range(len(poly) - 1):
                a0, a1 = poly[index], poly[index + 1]
                for jndex in range(len(other_poly) - 1):
                    b0, b1 = other_poly[jndex], other_poly[jndex + 1]
                    distance = segment_segment_distance_3d(a0, a1, b0, b1)
                    if distance < best:
                        best = distance
                        best_point = a0
                        if best < self.accept_segment:
                            break
                if best < self.accept_segment:
                    break
            if best < self.accept_segment:
                violations.append(dict(kind='transition_vs_transition',
                                       other_route=int(other['route_id']),
                                       route_id=int(route_id),
                                       point=[round(value, 6) for value in best_point],
                                       distance_mm=round(best, 6)))
                if len(violations) >= 3:
                    return violations
        return violations

    def check_route(self, route, check_self=True):
        violations = []
        route_id = route['route_id']
        for part in route['parts']:
            if part['kind'] == 'flat':
                violations.extend(self._flat_vs_transitions(
                    part['primitives'], part['z_mm'], route_id))
            else:
                violations.extend(self._transition_vs_flats(part, route_id))
                violations.extend(self._transition_vs_transitions(part, route_id))
            if violations:
                return violations
        if check_self:
            violations.extend(self_clearance_violations(route, self.clearance))
        return violations


def _polyline(points, stride):
    if stride <= 1:
        return points
    poly = [points[index] for index in range(0, len(points), stride)]
    if poly[-1] != points[-1]:
        poly.append(points[-1])
    return poly


# ---------------------------------------------------------------------------
# self clearance of one route (same route must not come back within 0.08 mm)
# ---------------------------------------------------------------------------
SELF_PATH_SEPARATION_MM = 1.0


def self_clearance_violations(route, clearance,
                              path_separation=SELF_PATH_SEPARATION_MM):
    points, lengths = P.sample_parts(route['parts'], step_flat=0.25,
                                     step_transition=0.05)
    violations = []
    cell = 0.3
    grid = {}
    for index, point in enumerate(points):
        key = (int(math.floor(point[0] / cell)),
               int(math.floor(point[1] / cell)),
               int(math.floor(point[2] / 0.05)))
        nearby = grid.get(key)
        if nearby is not None:
            for other_index in nearby:
                if abs(lengths[index] - lengths[other_index]) <= path_separation:
                    continue
                other = points[other_index]
                if abs(point[2] - other[2]) >= clearance:
                    continue
                distance = math.sqrt((point[0] - other[0]) ** 2
                                     + (point[1] - other[1]) ** 2
                                     + (point[2] - other[2]) ** 2)
                if distance < clearance + 0.01:
                    violations.append(dict(kind='self_clearance',
                                           point=[round(value, 6) for value in point],
                                           distance_mm=round(distance, 6)))
                    if len(violations) >= 5:
                        return violations
        grid.setdefault(key, []).append(index)
    return violations
