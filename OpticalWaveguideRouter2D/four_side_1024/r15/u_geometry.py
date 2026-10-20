"""Same-side (180 degree) U-turn geometry module for the R15 round.

Geometry contract
-----------------
Two ports sit on the **same board side**, both facing *into* the board, and are
separated laterally by ``d`` along that side.  A legal planar U-turn therefore
starts with the inward direction and must arrive with ``-inward`` (the frozen
``fslw.geom.canonical_validate`` pose convention: ``start_dir`` / ``end_dir`` are
the *travel* directions, so the same-side U has ``end_dir = -inward``).

The process requirement of the 2026-10-20 round fixes the curvature radius at
**R = 15 mm for every planar bend**, superseding the historical R = 40 mm
convention and the PDF example radii (R = 6000 um / R = 6137.33 um are shape
references only, see ``PDF_GEOMETRY.md``).  This module never shrinks the radius:
a port separation that cannot be connected with the requested R is *rejected*.

Legal families (monotone U-turn families; every arc radius exactly R)
--------------------------------------------------------------------
``half_circle``
    One 180-degree arc.  A semicircle displaces the path by exactly ``2R``
    between the two ports, so this family exists **only for d == 2R**
    (30 mm at R15).  At R15 the two ports must be exactly 30 mm apart.
``stadium``
    ``straight + half_circle + straight``: the two straights run *inward* and do
    not change the lateral displacement, so the family also requires d == 2R.
    The free ``bulge`` parameter only moves the bend deeper into the board.
``quarter_pair``
    ``straight + 90-degree arc + straight + 90-degree arc + straight``.  The two
    quarter arcs displace the path by ``2R`` and the middle straight by
    ``d - 2R``, therefore the family exists for **d >= 2R**.  With
    ``middle = 0`` it degenerates to the two-quarter-arc semicircle (the D56
    style 90-degree-only construction of the same U).  For d > 2R the middle
    straight is ``d - 2R`` and it must be non-negative: this is exactly the
    "minimum same-side separation is 2R" statement.

Consequently the minimum feasible same-side separation at radius ``R`` is
``min_feasible_separation(R) = 2R`` (30 mm at R15, 80 mm at the historical R40):
below that the ports are rejected instead of shrinking the radius.  A lateral
reversing "hook" built from a short-S pair plus a half circle could in principle
reach d < 2R, but it doubles back over the port bank (and is not a monotone
U-turn), so it is deliberately **not** emitted here.

Canonical frame
---------------
The common board side is mapped to ``y = 0`` with the inward direction ``+y``
(rigid quarter-turn rotations, all proper rotations, so arc sweeps are
preserved).  In that frame the source is ``p_c = (x0, 0)`` travelling ``+y``
and the target ``q_c = (x0 + d, 0)`` travelling ``-y`` (``d`` signed along the
side).  Primitives are built in the canonical frame and mapped back with
``four_side_1024.legacy_geometry.transform_primitives``.

All returned primitives are D56-schema dicts (``kind`` = ``line`` / ``arc``,
axis-aligned lines in the canonical frame, exact radius arcs, ``layer = 0``) and
are validated with the frozen ``fslw.geom.canonical_validate`` against the real
world poses, the 150 x 150 mm board and the 0.05 mm width.  The returned
``family`` strings are stable API values.
"""
from __future__ import annotations

import math

from ..fslw import config as C
from ..fslw import geom
from ..geometry import length as geometry_length
from ..legacy_geometry import transform_primitives
from . import profile_r15

#: The R15 process radius (read from the round profile, not re-declared as 40).
R15_MM = float(profile_r15.RADIUS_MM)
#: Default board side / waveguide width of the four-side 1024 experiment.
BOARD_MM = 150.0
WIDTH_MM = 0.05

TOL = 1e-9
DIR_TOL = 1e-7
SIDE_TOL = 1e-6
SEP_TOL = 1e-9

#: Inward (routing) direction of every board side.
SIDE_INWARD = {
    'S': (0.0, 1.0),
    'N': (0.0, -1.0),
    'E': (-1.0, 0.0),
    'W': (1.0, 0.0),
}
SIDE_ORDER = ('S', 'W', 'N', 'E')
#: Families emitted by :func:`u_candidates`, in deterministic priority order.
FAMILIES = ('half_circle', 'quarter_pair', 'stadium')

__all__ = [
    'R15_MM', 'BOARD_MM', 'WIDTH_MM', 'FAMILIES', 'SIDE_INWARD',
    'resolve_radius', 'min_feasible_separation', 'u_reachability',
    'u_frame', 'u_candidates', 'family_order',
]


# ---------------------------------------------------------------------------
# process / frame resolution
# ---------------------------------------------------------------------------
def resolve_radius(radius=None):
    """Return the requested radius; ``None`` resolves to the R15 profile (15 mm)."""
    if radius is None:
        profile_r15.apply()
        return float(C.RADIUS_MM)
    value = float(radius)
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError('radius must be positive and finite')
    return value


def resolve_board(board=None):
    """Return the board side length (default: the frozen fslw board, 150 mm)."""
    return float(C.BOARD_MM) if board is None else float(board)


def resolve_width(width=None):
    """Return the waveguide width (default: the frozen fslw width, 0.05 mm)."""
    return float(C.WIDTH_MM) if width is None else float(width)


def side_transforms(board=None):
    """World -> canonical frame for each board side (common side becomes ``y=0``).

    Every transform is a proper quarter-turn rotation (determinant +1), so arc
    sweeps are unchanged by the mapping and ``transform_primitives`` can invert
    it.  The canonical inward direction is always ``(0, 1)``.
    """
    side = resolve_board(board)
    return {
        'S': dict(matrix=[[1.0, 0.0], [0.0, 1.0]], offset=[0.0, 0.0],
                  reflected=False),
        'W': dict(matrix=[[0.0, -1.0], [1.0, 0.0]], offset=[side, 0.0],
                  reflected=False),
        'N': dict(matrix=[[-1.0, 0.0], [0.0, -1.0]], offset=[side, side],
                  reflected=False),
        'E': dict(matrix=[[0.0, 1.0], [-1.0, 0.0]], offset=[0.0, side],
                  reflected=False),
    }


def _unit(vector):
    values = (float(vector[0]), float(vector[1]))
    norm = math.hypot(values[0], values[1])
    if norm <= TOL or not math.isfinite(norm):
        raise ValueError('direction must be a finite non-zero vector')
    return (values[0] / norm, values[1] / norm)


def _side_of_direction(direction):
    """Board side whose inward direction equals ``direction`` (or ``None``)."""
    try:
        vector = _unit(direction)
    except (TypeError, ValueError, IndexError):
        return None
    for side in SIDE_ORDER:
        inward = SIDE_INWARD[side]
        if (abs(vector[0] - inward[0]) <= DIR_TOL
                and abs(vector[1] - inward[1]) <= DIR_TOL):
            return side
    return None


def _apply(transform, point):
    matrix, offset = transform['matrix'], transform['offset']
    return (matrix[0][0] * point[0] + matrix[0][1] * point[1] + offset[0],
            matrix[1][0] * point[0] + matrix[1][1] * point[1] + offset[1])


def _canonical_frame(p, q, start_dir, end_dir, board, width):
    """Build the canonical U-turn frame; records every pose/geometry error."""
    errors = []
    try:
        source = (float(p[0]), float(p[1]))
        target = (float(q[0]), float(q[1]))
    except (TypeError, ValueError, IndexError, KeyError):
        return None, ['invalid_port_coordinates']
    if not all(math.isfinite(value) for value in source + target):
        return None, ['nonfinite_port_coordinates']
    side = _side_of_direction(start_dir)
    if side is None:
        return None, ['start_direction_is_not_an_inward_axis']
    inward = SIDE_INWARD[side]
    try:
        end_vector = _unit(end_dir)
    except (TypeError, ValueError, IndexError):
        return None, ['invalid_end_direction']
    if (abs(end_vector[0] + inward[0]) > DIR_TOL
            or abs(end_vector[1] + inward[1]) > DIR_TOL):
        errors.append('end_direction_is_not_minus_inward')
    transform = side_transforms(board)[side]
    p_canonical = _apply(transform, source)
    q_canonical = _apply(transform, target)
    if abs(p_canonical[1]) > SIDE_TOL:
        errors.append('source_port_off_side')
    if abs(q_canonical[1]) > SIDE_TOL:
        errors.append('target_port_off_side')
    for name, point in (('source', p_canonical), ('target', q_canonical)):
        if point[0] < -SIDE_TOL or point[0] > board + SIDE_TOL:
            errors.append(f'{name}_port_outside_side_span')
    signed = q_canonical[0] - p_canonical[0]
    if abs(signed) <= TOL:
        errors.append('coincident_ports')
    if errors:
        return None, errors
    return dict(
        valid=True,
        side=side,
        board_mm=float(board),
        width_mm=float(width),
        transform=transform,
        source=source,
        target=target,
        start_dir=_unit(start_dir),
        end_dir=end_vector,
        p_canonical=p_canonical,
        q_canonical=q_canonical,
        separation_mm=abs(signed),
        signed_separation_mm=signed,
    ), errors


def u_frame(p, q, start_dir, end_dir, board=None):
    """Return the canonical same-side U frame of a port pair (diagnostic API).

    ``valid=False`` with an ``errors`` list means the pair is not a legal
    same-side U-turn input (wrong side, wrong end direction, coincident ports...).
    """
    board = resolve_board(board)
    width = resolve_width(None)
    frame, errors = _canonical_frame(p, q, start_dir, end_dir, board, width)
    if frame is None:
        return dict(valid=False, errors=list(errors))
    frame['errors'] = list(errors)
    return frame


# ---------------------------------------------------------------------------
# primitive builders (canonical frame, start = (x0, 0) travelling +y)
# ---------------------------------------------------------------------------
def _append_line(primitives, p0, p1):
    if math.hypot(p1[0] - p0[0], p1[1] - p0[1]) > TOL:
        primitives.append(geom.line(p0, p1))


def _append_arc(primitives, cursor, center, radius, start_angle, sweep):
    end = (center[0] + radius * math.cos(start_angle + sweep),
           center[1] + radius * math.sin(start_angle + sweep))
    primitives.append(geom.arc(cursor, end, center, radius, start_angle, sweep))
    return end


def _half_circle(p_canonical, q_canonical, radius):
    """Pure 180-degree arc; requires ``|dx| == 2R``."""
    x0 = float(p_canonical[0])
    delta = float(q_canonical[0]) - x0
    turn = 1.0 if delta > 0.0 else -1.0
    center = (x0 + delta / 2.0, 0.0)
    start_angle = math.pi if turn > 0.0 else 0.0
    sweep = -turn * math.pi
    primitives = []
    _append_arc(primitives, (x0, 0.0), center, radius, start_angle, sweep)
    return primitives


def _stadium(p_canonical, q_canonical, radius, bulge):
    """``straight + half_circle + straight``; requires ``|dx| == 2R``."""
    x0 = float(p_canonical[0])
    delta = float(q_canonical[0]) - x0
    turn = 1.0 if delta > 0.0 else -1.0
    primitives = []
    _append_line(primitives, (x0, 0.0), (x0, bulge))
    center = (x0 + delta / 2.0, bulge)
    start_angle = math.pi if turn > 0.0 else 0.0
    sweep = -turn * math.pi
    end = _append_arc(primitives, (x0, bulge), center, radius, start_angle, sweep)
    _append_line(primitives, end, (x0 + delta, 0.0))
    return primitives


def _quarter_arc(primitives, cursor, heading, turn, radius):
    """Append one 90-degree arc; ``turn`` +1 = left, -1 = right."""
    normal = (-heading[1], heading[0])
    center = (cursor[0] + turn * radius * normal[0],
              cursor[1] + turn * radius * normal[1])
    start_angle = math.atan2(cursor[1] - center[1], cursor[0] - center[0])
    sweep = turn * math.pi / 2.0
    end = _append_arc(primitives, cursor, center, radius, start_angle, sweep)
    cos_sweep, sin_sweep = math.cos(sweep), math.sin(sweep)
    new_heading = (heading[0] * cos_sweep - heading[1] * sin_sweep,
                   heading[0] * sin_sweep + heading[1] * cos_sweep)
    return end, new_heading


def _quarter_pair(p_canonical, q_canonical, radius, bulge, middle):
    """Two quarter arcs + middle straight; requires ``|dx| == 2R + middle``."""
    x0 = float(p_canonical[0])
    delta = float(q_canonical[0]) - x0
    turn = -1.0 if delta > 0.0 else 1.0
    primitives = []
    _append_line(primitives, (x0, 0.0), (x0, bulge))
    cursor = (x0, bulge)
    heading = (0.0, 1.0)
    cursor, heading = _quarter_arc(primitives, cursor, heading, turn, radius)
    _append_line(primitives, cursor,
                 (cursor[0] + heading[0] * middle,
                  cursor[1] + heading[1] * middle))
    cursor = (cursor[0] + heading[0] * middle,
              cursor[1] + heading[1] * middle)
    cursor, heading = _quarter_arc(primitives, cursor, heading, turn, radius)
    _append_line(primitives, cursor, (x0 + delta, 0.0))
    return primitives


# ---------------------------------------------------------------------------
# local exactness checks (the frozen validator only rejects radius < minimum)
# ---------------------------------------------------------------------------
def _check_arc_radii(primitives, radius):
    errors = []
    for index, primitive in enumerate(primitives):
        if primitive['kind'] == 'arc':
            if abs(float(primitive['radius']) - radius) > TOL:
                errors.append(f'arc_radius_not_requested:{index}')
        elif primitive['kind'] == 'line':
            p0, p1 = primitive['p0'], primitive['p1']
            if abs(p0[0] - p1[0]) > DIR_TOL and abs(p0[1] - p1[1]) > DIR_TOL:
                errors.append(f'diagonal_line:{index}')
        else:
            errors.append(f'unknown_primitive:{index}')
    return errors


def _validate(primitives, frame, radius, width):
    """Frozen canonical validation in world coordinates + exact-radius audit."""
    errors = _check_arc_radii(primitives, radius)
    if abs(frame['board_mm'] - float(C.BOARD_MM)) <= TOL:
        ok, canonical_errors = geom.canonical_validate(
            primitives, frame['source'], frame['target'],
            frame['start_dir'], frame['end_dir'], radius=radius, width=width)
        errors.extend(canonical_errors)
        return not errors
    from ..geometry import validate
    errors.extend(validate(primitives, frame['source'], frame['target'],
                           frame['start_dir'], frame['end_dir'],
                           board=frame['board_mm'], width=width,
                           min_radius=radius))
    return not errors


# ---------------------------------------------------------------------------
# family / separation feasibility
# ---------------------------------------------------------------------------
def min_feasible_separation(radius=None):
    """Smallest same-side port separation that a legal U-turn can connect.

    A monotone U-turn must displace the path by at least ``2R`` (a single
    180-degree arc displaces exactly ``2R``; two quarter arcs displace ``2R``
    and any straights add no lateral displacement), so this is ``2R``:
    30.0 mm at R15 and 80.0 mm at the historical R40 convention.
    """
    return 2.0 * resolve_radius(radius)


def family_order():
    """Stable family priority list (also the emission order of candidates)."""
    return list(FAMILIES)


def _bulge_values(max_bulge, radius, include_zero):
    """Deterministic representative ``bulge`` values in ``[0, max_bulge]``.

    The ladder is radius-scaled (``0.5R``, ``R``, ``2R``) so that the emitted
    U-turn candidates are comparable across radii; values beyond the locally
    available board depth are dropped and a very shallow board falls back to the
    largest available bulge.
    """
    values = []
    if include_zero:
        values.append(0.0)
    for factor in (0.5, 1.0, 2.0):
        value = radius * factor
        if value <= max_bulge + TOL:
            values.append(float(value))
    if not values:
        values.append(float(max_bulge))
    unique = []
    for value in values:
        if all(abs(value - other) > TOL for other in unique):
            unique.append(float(value))
    return unique


def u_reachability(separation, radius=None, board=None, width=None):
    """Feasibility report for one same-side port separation ``separation`` (mm).

    Returns a JSON-ready dict with the requested radius, the minimum feasible
    separation (``2R``), the legal family names and a reason when infeasible.
    The radius is never reduced; a separation below ``2R`` is rejected.
    """
    radius = resolve_radius(radius)
    board = resolve_board(board)
    width = resolve_width(width)
    distance = abs(float(separation))
    two_r = 2.0 * radius
    max_bulge = board - radius - width / 2.0
    board_fits = max_bulge >= 0.0
    result = dict(
        separation_mm=distance,
        radius_mm=radius,
        minimum_separation_mm=two_r,
        board_mm=board,
        width_mm=width,
        max_bulge_mm=max(max_bulge, 0.0),
        board_fits=board_fits,
        feasible=False,
        families=[],
        reason=None,
    )
    if distance <= TOL:
        result['reason'] = 'coincident_ports'
        return result
    if not board_fits:
        result['reason'] = 'board_too_small_for_radius'
        return result
    if distance < two_r - SEP_TOL:
        result['reason'] = 'below_minimum_separation_no_radius_shrink'
        return result
    if abs(distance - two_r) <= SEP_TOL:
        families = ['half_circle', 'quarter_pair', 'stadium']
    else:
        families = ['quarter_pair']
    result.update(feasible=True, families=families)
    return result


# ---------------------------------------------------------------------------
# public candidate API
# ---------------------------------------------------------------------------
def _specs(separation, radius, board, width):
    """Ordered ``(family, bulge, middle)`` specs for one separation."""
    specs = []
    two_r = 2.0 * radius
    max_bulge = board - radius - width / 2.0
    if max_bulge < 0.0 or separation < two_r - SEP_TOL:
        return specs
    if abs(separation - two_r) <= SEP_TOL:
        specs.append(('half_circle', 0.0, 0.0))
        for bulge in _bulge_values(max_bulge, radius, include_zero=True):
            specs.append(('quarter_pair', bulge, 0.0))
        for bulge in _bulge_values(max_bulge, radius, include_zero=False):
            specs.append(('stadium', bulge, 0.0))
    else:
        middle = separation - two_r
        for bulge in _bulge_values(max_bulge, radius, include_zero=True):
            specs.append(('quarter_pair', bulge, middle))
    return specs


def _build(family, bulge, middle, p_canonical, q_canonical, radius):
    if family == 'half_circle':
        return _half_circle(p_canonical, q_canonical, radius)
    if family == 'stadium':
        return _stadium(p_canonical, q_canonical, radius, bulge)
    if family == 'quarter_pair':
        return _quarter_pair(p_canonical, q_canonical, radius, bulge, middle)
    raise ValueError('unknown U-turn family ' + str(family))


def u_candidates(p, q, start_dir, end_dir, radius=None, board=None, width=None):
    """Legal same-side 180-degree U-turn candidates for the port pair ``p``, ``q``.

    Parameters
    ----------
    p, q :
        world port positions (mm) on the same board side, both facing inward.
    start_dir, end_dir :
        travel directions at the two ports; for a same-side U they must be
        ``inward`` and ``-inward`` respectively (``fslw.geom`` convention).
    radius :
        fixed bend radius; ``None`` resolves to the R15 process radius (15 mm).
        The radius is never shrunk: infeasible separations return ``[]``.
    board, width :
        board side length and waveguide width (defaults 150 mm / 0.05 mm).

    Returns
    -------
    list of dict
        ``{family, primitives, params, radius_mm, separation_mm, length_mm,
        side, side_canonical, start/target poses}``.  Every candidate is a
        D56-schema line/arc chain in world coordinates that passes the frozen
        ``fslw.geom.canonical_validate`` with exact radius ``R`` and consistent
        tangents.  An empty list means the port pair is not connectable at this
        radius (ambiguous / off-side inputs, ``d < 2R``, or a board too small).
    """
    radius = resolve_radius(radius)
    board = resolve_board(board)
    width = resolve_width(width)
    frame, _errors = _canonical_frame(p, q, start_dir, end_dir, board, width)
    if frame is None:
        return []
    separation = frame['separation_mm']
    candidates = []
    for family, bulge, middle in _specs(separation, radius, board, width):
        canonical = _build(family, bulge, middle,
                           frame['p_canonical'], frame['q_canonical'], radius)
        world = transform_primitives(canonical, frame['transform'], inverse=True)
        if not _validate(world, frame, radius, width):
            continue
        candidates.append(dict(
            family=family,
            primitives=world,
            params=dict(bulge_mm=float(bulge),
                        middle_straight_mm=float(middle),
                        radius_mm=float(radius),
                        separation_mm=float(separation),
                        side=frame['side']),
            radius_mm=float(radius),
            separation_mm=float(separation),
            length_mm=geometry_length(world),
            side=frame['side'],
            side_canonical=list(frame['p_canonical']),
            source=tuple(frame['source']),
            target=tuple(frame['target']),
            start_dir=tuple(frame['start_dir']),
            end_dir=tuple(frame['end_dir']),
        ))
    return candidates


def u_candidate_families(p, q, start_dir, end_dir, radius=None, board=None,
                         width=None):
    """Convenience wrapper: the distinct family names of :func:`u_candidates`."""
    families = []
    for candidate in u_candidates(p, q, start_dir, end_dir, radius=radius,
                                  board=board, width=width):
        if candidate['family'] not in families:
            families.append(candidate['family'])
    return families
