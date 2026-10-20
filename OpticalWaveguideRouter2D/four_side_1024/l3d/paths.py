"""Corrected L1-L5 3D path assembly (R9 round, 2026-10-20).

Physical model (see ``SCHEMA_L3D.md``)
--------------------------------------
The corrected model puts **both interface rows on L1**: row ``z1`` at physical
height 0.0 mm and row ``z2`` at 0.5 mm.  L2..L5 are four additional routing
layers with *unconfirmed simulation* heights.  A route starts and ends on L1 at
its own row height and may visit any sequence of logical layers in between,
with one two-arc elevation S-curve per height change.  Multiple transitions and
direct non-adjacent-layer transitions are allowed, including back-to-back
transitions.

Elevation S-curve (unchanged geometry, radius R = 15 mm in this round)::

    theta     = acos(1 - |dz| / (2R))
    footprint = 2 R sin(theta)          # horizontal projection along the straight
    length    = 2 R theta               # 3D arc length of the two arcs

This module only *assembles* geometry: it validates that every transition can
be placed on a straight XY portion of the path, splits the (unchanged) 2D
primitive chain at the exact arc-length positions, and emits the schema
``parts`` list.  Collision checking is done by the router / world / independent
validator, not here.

Placement rules
---------------
* transitions may only sit on ``kind == 'line'`` primitives, with the whole
  footprint inside the line interval after ``segment_margin`` is removed from
  both line ends;
* ``port_margin`` of flat path before the first transition start and after the
  last transition end;
* transitions are at strictly increasing arc-length positions and consecutive
  transitions keep at least ``min_flat_gap`` of flat path between them
  (``0.0`` allows back-to-back S-curves on the same straight; tangents then
  agree because both S-curves start/end along the line direction);
* radius is fixed by the caller (default 15.0 mm) and never reduced: a
  geometry that cannot host the requested transitions returns ``None``.

Variant semantics (deterministic candidate diversity, same feasibility):
``0`` "earliest-then-latest" (first transition as early as possible, last as late
as possible, the middle ones spread evenly between them so every visited layer
normally gets a flat run), ``1`` all transitions forward-greedy (earliest,
possibly back-to-back), ``2`` all transitions backward-greedy (latest, possibly
back-to-back).  On a two-transition ascent/descent route variants 1 and 2 are
the extreme "climb immediately / climb late" alternatives.
"""
from __future__ import annotations

import math

from ..fsd25d import path3d as P

#: R15 process radius (explicit default; the R15 profile is applied by the runner).
DEFAULT_RADIUS_MM = 15.0
#: flat path kept at the route ports before/after the transition region (mm).
PORT_MARGIN_MM = 1.2
#: flat path kept inside a straight primitive end (mm).
SEGMENT_MARGIN_MM = 0.25
#: default minimum flat path between consecutive transitions (mm) for
#: ``place_transitions_multi`` (0.0 allows explicitly requested back-to-back S-curves).
DEFAULT_MIN_FLAT_GAP_MM = 0.0
#: flat run kept between two transitions by ``build_route_l3d`` so that the
#: assembled parts always alternate flat/transition/flat (mm).
DEFAULT_BUILD_MIN_FLAT_GAP_MM = 0.5
#: L1 is the interface routing layer (holds both port rows).
INTERFACE_LAYER_ID = 1
#: L1 real row heights: row z1 -> 0.0 mm, row z2 -> 0.5 mm (SCHEMA_L3D.md §1).
INTERFACE_ROW_Z_MM = {'z1': 0.0, 'z2': 0.5}
#: plane -> CSV row number of the interface row.
PLANE_ROW = {'z1': 1, 'z2': 2}

TOL = 1e-9
FLOAT_TOL = 1e-9
LEN_TOL = 1e-12

__all__ = [
    'DEFAULT_RADIUS_MM', 'PORT_MARGIN_MM', 'SEGMENT_MARGIN_MM',
    'DEFAULT_MIN_FLAT_GAP_MM', 'DEFAULT_BUILD_MIN_FLAT_GAP_MM', 'INTERFACE_LAYER_ID', 'INTERFACE_ROW_Z_MM',
    'PLANE_ROW', 'transition_geometry', 'place_transitions_multi',
    'build_route_l3d', 'route_transition_join',
]


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _finite_float(value, name):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f'{name} must be finite, got {value!r}')
    return number


def _xy(value):
    result = (float(value[0]), float(value[1]))
    if not all(math.isfinite(item) for item in result):
        raise ValueError('non-finite XY coordinate')
    return result


def _dist2(first, second):
    return math.hypot(first[0] - second[0], first[1] - second[1])


def _unit(vector):
    length = math.hypot(float(vector[0]), float(vector[1]))
    if length <= TOL or not math.isfinite(length):
        raise ValueError('zero or non-finite direction')
    return (float(vector[0]) / length, float(vector[1]) / length)


def transition_geometry(dz_mm, radius=DEFAULT_RADIUS_MM):
    """Elevation S-curve parameters for one height change (see module docstring)."""
    radius = float(radius)
    if not math.isfinite(radius) or radius <= 0.0:
        raise ValueError('radius must be positive and finite')
    dz = float(dz_mm)
    if not math.isfinite(dz):
        raise ValueError('dz must be finite')
    theta = P.transition_theta(dz, radius)
    return dict(dz_mm=dz, theta_rad=float(theta),
                footprint_mm=2.0 * radius * math.sin(theta),
                length_mm=2.0 * radius * theta)


# ---------------------------------------------------------------------------
# transition placement on the 2D path
# ---------------------------------------------------------------------------
def _straight_windows(prims, footprint, segment_margin, total):
    """Feasible ``(lo, hi)`` start ranges for one footprint on the straights."""
    windows = []
    for start, end, _index in P.straight_intervals(prims):
        lo = start + segment_margin
        hi = end - segment_margin - footprint
        if hi < lo - TOL:
            continue
        lo = max(lo, 0.0)
        hi = max(hi, lo)
        if hi > total - footprint + TOL:
            hi = max(lo, total - footprint)
        windows.append((lo, hi))
    windows.sort(key=lambda item: item[0])
    return windows


def _earliest_start(windows, floor):
    """Earliest start ``>= floor`` inside one of the (lo, hi) start windows."""
    for lo, hi in windows:
        candidate = max(lo, floor)
        if candidate <= hi + TOL:
            return candidate
    return None


def _latest_start(windows, ceil):
    """Latest start ``<= ceil`` inside one of the (lo, hi) start windows."""
    for lo, hi in reversed(windows):
        candidate = min(hi, ceil)
        if candidate >= lo - TOL:
            return candidate
    return None


def _forward_solution(windows_list, footprints, total, port_margin, gap):
    starts = []
    floor = port_margin
    for index, footprint in enumerate(footprints):
        start = _earliest_start(windows_list[index], floor)
        if start is None:
            return None
        starts.append(start)
        floor = start + footprint + gap
    if starts[0] < port_margin - TOL:
        return None
    if starts[-1] + footprints[-1] > total - port_margin + TOL:
        return None
    return starts


def _backward_solution(windows_list, footprints, total, port_margin, gap):
    count = len(footprints)
    starts = [0.0] * count
    ceil = total - port_margin - footprints[-1]
    for index in range(count - 1, -1, -1):
        start = _latest_start(windows_list[index], ceil)
        if start is None:
            return None
        starts[index] = start
        if index:
            # upper bound on the previous transition's start
            ceil = start - gap - footprints[index - 1]
    if starts[0] < port_margin - TOL:
        return None
    return starts


def _earliest_then_latest_solution(windows_list, footprints, total, port_margin,
                                   gap):
    """Variant 0: first transition earliest, last latest, middle ones spread.

    The remaining transitions are spaced as evenly as the straight windows allow
    between the (earliest) first transition and the (latest) last transition, so
    every visited layer normally receives a non-zero flat run.  If the even
    spread does not fit the windows the plain forward-greedy solution is used.
    """
    forward = _forward_solution(windows_list, footprints, total, port_margin, gap)
    if forward is None:
        return None
    count = len(footprints)
    if count == 1:
        return forward
    first_start = forward[0]
    last_start_upper = total - port_margin - footprints[-1]
    span = last_start_upper - (first_start + footprints[0])
    middle_footprints = sum(footprints[1:-1])
    gaps_total = span - middle_footprints
    if span < -TOL or gaps_total < 0.0:
        return forward
    balanced_gap = max(gap, gaps_total / (count - 1.0))
    starts = [first_start]
    floor = first_start + footprints[0] + balanced_gap
    for index in range(1, count):
        start = _earliest_start(windows_list[index], floor)
        if start is None:
            return forward
        starts.append(start)
        floor = start + footprints[index] + balanced_gap
    if starts[-1] > last_start_upper + TOL:
        return forward
    for index, start in enumerate(starts):
        if not any(lo - TOL <= start <= hi + TOL for lo, hi in windows_list[index]):
            return forward
    return starts


def _placement_is_valid(starts, footprints, windows_list, total, port_margin,
                        gap):
    if not starts:
        return True
    previous_end = None
    for index, (start, footprint) in enumerate(zip(starts, footprints)):
        if not any(lo - TOL <= start <= hi + TOL for lo, hi in windows_list[index]):
            return False
        if index == 0 and start < port_margin - TOL:
            return False
        if previous_end is not None and start < previous_end + gap - TOL:
            return False
        previous_end = start + footprint
        if index == len(starts) - 1 and previous_end > total - port_margin + TOL:
            return False
    return True


def place_transitions_multi(prims, z_sequence, radius=DEFAULT_RADIUS_MM,
                            port_margin=PORT_MARGIN_MM,
                            segment_margin=SEGMENT_MARGIN_MM,
                            min_flat_gap=DEFAULT_MIN_FLAT_GAP_MM, variant=0):
    """Place the elevation transitions of ``z_sequence`` on the 2D path ``prims``.

    Parameters
    ----------
    prims:
        ordered 2D primitive chain (``fsd25d``/D56/pure-90 dicts, lines and arcs).
    z_sequence:
        ``[z_start, z_1, ..., z_end]`` real physical heights along the route.
        Number of transitions is ``len(z_sequence) - 1``; each transition
        footprint/length comes from its own ``dz`` at the given radius.
    radius, port_margin, segment_margin, min_flat_gap, variant:
        see the module docstring.

    Returns
    -------
    dict or None
        ``{footprints, starts_s, ends_s, z_sequence, min_flat_gap, variant}``
        or ``None`` when the transitions cannot be placed (no suitable
        straights, path too short, ``|dz| >= 2R``, degenerate ``dz == 0``).
    """
    radius = float(radius)
    if not math.isfinite(radius) or radius <= 0.0:
        raise ValueError('radius must be positive and finite')
    port_margin = _finite_float(port_margin, 'port_margin')
    segment_margin = _finite_float(segment_margin, 'segment_margin')
    min_flat_gap = _finite_float(min_flat_gap, 'min_flat_gap')
    if port_margin < 0.0 or segment_margin < 0.0 or min_flat_gap < 0.0:
        raise ValueError('margins and min_flat_gap must be non-negative')
    if int(variant) not in (0, 1, 2):
        raise ValueError('variant must be 0, 1 or 2')
    variant = int(variant)
    heights = [_finite_float(value, 'z_sequence entry') for value in z_sequence]
    empty = dict(footprints=[], starts_s=[], ends_s=[],
                 z_sequence=list(heights), min_flat_gap=min_flat_gap,
                 variant=variant)
    if len(heights) == 0:
        raise ValueError('z_sequence must contain at least the start height')
    if len(heights) == 1:
        return empty
    prims = [P.clean_primitive(prim) for prim in prims or []]
    if not prims:
        return None
    footprints = []
    for first, second in zip(heights, heights[1:]):
        dz = second - first
        if abs(dz) <= TOL:
            # a "transition" with no height change is not a real elevation curve
            return None
        try:
            geometry = transition_geometry(dz, radius)
        except ValueError:
            return None
        if geometry['footprint_mm'] <= TOL:
            return None
        footprints.append(geometry['footprint_mm'])
    total = P.path_length(prims)
    if total <= LEN_TOL:
        return None
    windows = [_straight_windows(prims, footprint, segment_margin, total)
               for footprint in footprints]
    if any(not window for window in windows):
        return None
    if variant == 0:
        starts = _earliest_then_latest_solution(
            windows, footprints, total, port_margin, min_flat_gap)
    elif variant == 1:
        starts = _forward_solution(windows, footprints, total, port_margin,
                                   min_flat_gap)
    else:
        starts = _backward_solution(windows, footprints, total, port_margin,
                                    min_flat_gap)
    if starts is None:
        return None
    # every transition may use any straight; re-check each transition's own
    # window (a longer footprint has a smaller usable range) defensively.
    for index, start in enumerate(starts):
        if not any(lo - TOL <= start <= hi + TOL
                   for lo, hi in windows[index]):
            return None
    if not _placement_is_valid(starts, footprints, windows, total,
                               port_margin, min_flat_gap):
        return None
    ends = [start + footprint for start, footprint in zip(starts, footprints)]
    return dict(footprints=[float(value) for value in footprints],
                starts_s=[float(value) for value in starts],
                ends_s=[float(value) for value in ends],
                z_sequence=list(heights), min_flat_gap=min_flat_gap,
                variant=variant)


# ---------------------------------------------------------------------------
# route assembly
# ---------------------------------------------------------------------------
def _subchain(prims, start_s, end_s):
    """Sub-chain of ``prims`` between two arc-length positions (XY unchanged)."""
    if end_s - start_s <= LEN_TOL:
        return []
    _head, tail = P.path_split(prims, start_s)
    body, _rest = P.path_split(tail, end_s - start_s)
    return [P.clean_primitive(prim) for prim in body]


def _part_start_pose(part):
    """``(xy, horizontal tangent)`` at the start of a flat/transition part."""
    if part['kind'] == 'flat':
        point, tangent = P.path_point_at(part['primitives'], 0.0)
        return (float(point[0]), float(point[1])), _unit(tangent)
    return _xy(part['start']), _unit(part['direction'])


def _part_end_pose(part):
    """``(xy, horizontal tangent)`` at the end of a flat/transition part."""
    if part['kind'] == 'flat':
        prims = part['primitives']
        point, tangent = P.path_point_at(prims, P.path_length(prims))
        return (float(point[0]), float(point[1])), _unit(tangent)
    return _xy(part['end']), _unit(part['direction'])


def _part_z_range(part):
    if part['kind'] == 'flat':
        return float(part['z_mm']), float(part['z_mm'])
    return float(part['z0']), float(part['z1'])


def build_route_l3d(route_id, plane, prims, layer_sequence, layer_z_sequence,
                    port_meta, radius=DEFAULT_RADIUS_MM, variant=0,
                    family=None, params=None):
    """Assemble one L1-L5 route description per ``SCHEMA_L3D.md`` §2.

    ``layer_sequence`` and ``layer_z_sequence`` must have the same length, start
    and end on L1 (``layer_id == 1``) and carry the L1 row height at both ends.
    Returns ``None`` when the transition placement is infeasible; raises
    ``ValueError`` for structurally invalid input (wrong plane, bad layer
    sequence, mismatched endpoints, inconsistent layer heights).
    """
    if plane not in INTERFACE_ROW_Z_MM:
        raise ValueError(f'plane must be one of {sorted(INTERFACE_ROW_Z_MM)}')
    radius = float(radius)
    if not math.isfinite(radius) or radius <= 0.0:
        raise ValueError('radius must be positive and finite')
    if int(variant) not in (0, 1, 2):
        raise ValueError('variant must be 0, 1 or 2')
    variant = int(variant)
    prims = [P.clean_primitive(prim) for prim in prims or []]
    if not prims:
        raise ValueError('empty 2D primitive chain')
    layers = [int(value) for value in layer_sequence]
    heights = [_finite_float(value, 'layer_z_sequence entry')
               for value in layer_z_sequence]
    if not layers or len(layers) != len(heights):
        raise ValueError('layer_sequence and layer_z_sequence length mismatch')
    if layers[0] != INTERFACE_LAYER_ID or layers[-1] != INTERFACE_LAYER_ID:
        raise ValueError('an L3D route must start and end on L1')
    if any(layer < INTERFACE_LAYER_ID for layer in layers):
        raise ValueError('layer ids are 1..5 (L1 is the interface layer)')
    # one physical height per logical layer within one route
    seen = {}
    for layer, height in zip(layers, heights):
        if layer in seen and abs(seen[layer] - height) > FLOAT_TOL:
            raise ValueError(f'layer {layer} is used with different physical '
                             f'heights in one route')
        seen[layer] = height
    if not isinstance(port_meta, dict):
        raise ValueError('port_meta must be a dict')
    for key in ('source_port', 'target_port'):
        if key not in port_meta:
            raise ValueError(f'port_meta.{key} is required')
    source = port_meta['source_port']
    target = port_meta['target_port']
    source_xy = _xy(source['xy'])
    target_xy = _xy(target['xy'])
    source_z = _finite_float(source['z_mm'], 'source_port.z_mm')
    target_z = _finite_float(target['z_mm'], 'target_port.z_mm')
    expected_z = float(INTERFACE_ROW_Z_MM[plane])
    if abs(source_z - expected_z) > FLOAT_TOL or abs(target_z - expected_z) > FLOAT_TOL:
        raise ValueError(f'plane {plane} requires L1 row height {expected_z:g} mm')
    if abs(source_z - target_z) > FLOAT_TOL:
        raise ValueError('an L3D route must keep its interface row (same z at both ports)')
    if abs(heights[0] - source_z) > FLOAT_TOL or abs(heights[-1] - target_z) > FLOAT_TOL:
        raise ValueError('layer_z_sequence must start/end at the L1 port heights')
    if int(source.get('layer_id', INTERFACE_LAYER_ID)) != INTERFACE_LAYER_ID \
            or int(target.get('layer_id', INTERFACE_LAYER_ID)) != INTERFACE_LAYER_ID:
        raise ValueError('source/target ports must declare layer_id = 1 (L1)')
    start_xy = _xy(prims[0]['p0'])
    end_xy = _xy(prims[-1]['p1'])
    if _dist2(start_xy, source_xy) > 1e-6:
        raise ValueError('2D path start does not match source_port.xy')
    if _dist2(end_xy, target_xy) > 1e-6:
        raise ValueError('2D path end does not match target_port.xy')
    total = P.path_length(prims)
    if total <= LEN_TOL:
        raise ValueError('2D path has zero length')
    # optional pose directions: travel directions are parallel to the path tangents
    if port_meta.get('start_dir') is not None:
        tangent = _unit(P.path_point_at(prims, 0.0)[1])
        direction = _unit(port_meta['start_dir'])
        if abs(tangent[0] * direction[0] + tangent[1] * direction[1]) < 1.0 - 1e-6:
            raise ValueError('port_meta.start_dir is not parallel to the path start')
    if port_meta.get('end_dir') is not None:
        tangent = _unit(P.path_point_at(prims, total)[1])
        direction = _unit(port_meta['end_dir'])
        if abs(tangent[0] * direction[0] + tangent[1] * direction[1]) < 1.0 - 1e-6:
            raise ValueError('port_meta.end_dir is not parallel to the path end')
    placement = place_transitions_multi(
        prims, heights, radius=radius, port_margin=PORT_MARGIN_MM,
        segment_margin=SEGMENT_MARGIN_MM, min_flat_gap=DEFAULT_BUILD_MIN_FLAT_GAP_MM,
        variant=variant)
    if placement is None:
        return None

    parts = []
    previous_end = 0.0
    transition_count = len(placement['footprints'])
    for index in range(transition_count):
        start_s = placement['starts_s'][index]
        end_s = placement['ends_s'][index]
        flat_primitives = _subchain(prims, previous_end, start_s)
        flat_length = P.path_length(flat_primitives)
        if flat_length > LEN_TOL:
            parts.append(dict(
                kind='flat', layer_id=int(layers[index]),
                z_mm=float(heights[index]), length_mm=float(flat_length),
                primitives=flat_primitives))
        point, direction = P.path_point_at(prims, start_s)
        transition = dict(P.make_transition(
            point, direction, heights[index], heights[index + 1], radius))
        transition['from_layer'] = int(layers[index])
        transition['to_layer'] = int(layers[index + 1])
        parts.append(transition)
        previous_end = end_s
    tail_primitives = _subchain(prims, previous_end, total)
    tail_length = P.path_length(tail_primitives)
    if tail_length > LEN_TOL:
        parts.append(dict(
            kind='flat', layer_id=int(layers[-1]), z_mm=float(heights[-1]),
            length_mm=float(tail_length), primitives=tail_primitives))

    source_row = int(port_meta.get('source_row', PLANE_ROW[plane]))
    target_row = int(port_meta.get('target_row', PLANE_ROW[plane]))
    expected_row = PLANE_ROW[plane]
    if source_row != expected_row or target_row != expected_row:
        raise ValueError(f'plane {plane} requires row {expected_row} at both ports')
    length_mm = float(sum(part['length_mm'] for part in parts))
    route = dict(
        route_id=int(route_id),
        plane=plane,
        source_row=source_row,
        target_row=target_row,
        source_port=dict(xy=[source_xy[0], source_xy[1]], z_mm=float(source_z),
                         layer_id=INTERFACE_LAYER_ID),
        target_port=dict(xy=[target_xy[0], target_xy[1]], z_mm=float(target_z),
                         layer_id=INTERFACE_LAYER_ID),
        start_z_mm=float(heights[0]),
        end_z_mm=float(heights[-1]),
        layer_sequence=layers,
        layer_z_sequence=heights,
        n_transitions=int(transition_count),
        lifted=bool(any(abs(height - heights[0]) > FLOAT_TOL
                        for height in heights)),
        layers_used=sorted(set(layers)),
        xy_length_mm=float(total),
        length_mm=length_mm,
        z_span_mm=float(max(heights) - min(heights)),
        parts=parts,
    )
    if family is not None:
        route['family'] = family
    if params is not None:
        route['params'] = params
    return route


# ---------------------------------------------------------------------------
# join continuity audit (helper for tests / the independent validator)
# ---------------------------------------------------------------------------
def route_transition_join(route):
    """Point/tangent continuity metrics at every part join of an L3D route.

    Returns a list with one dict per adjacent part pair::

        {index, from_kind, to_kind, position_gap_mm, z_gap_mm,
         position_gap_3d_mm, tangent_error_deg, position_ok, tangent_ok}
    """
    parts = route.get('parts') or []
    joins = []
    for index in range(len(parts) - 1):
        previous = parts[index]
        following = parts[index + 1]
        previous_xy, previous_tangent = _part_end_pose(previous)
        following_xy, following_tangent = _part_start_pose(following)
        previous_z = _part_z_range(previous)[1]
        following_z = _part_z_range(following)[0]
        position_gap = _dist2(previous_xy, following_xy)
        z_gap = abs(previous_z - following_z)
        dot = max(-1.0, min(1.0, previous_tangent[0] * following_tangent[0]
                            + previous_tangent[1] * following_tangent[1]))
        tangent_error = math.degrees(math.acos(dot))
        position_ok = position_gap <= 1e-7 and z_gap <= 1e-9
        tangent_ok = tangent_error <= 1e-6
        joins.append(dict(
            index=index,
            from_kind=previous['kind'],
            to_kind=following['kind'],
            position_gap_mm=float(position_gap),
            z_gap_mm=float(z_gap),
            position_gap_3d_mm=float(math.hypot(position_gap, z_gap)),
            tangent_error_deg=float(tangent_error),
            position_ok=bool(position_ok),
            tangent_ok=bool(tangent_ok),
        ))
    return joins
