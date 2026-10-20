"""Statistics for the corrected L1-L5 physical-model round (R9, 2026-10-20).

The corrected model (see ``four_side_1024/l3d/SCHEMA_L3D.md``) is:

* **L1 is the interface routing layer and contains BOTH port rows**:
  physical ``z=0.0 mm`` (z1 row) and ``z=0.5 mm`` (z2 row), both logical
  ``layer_id = 1``;
* **L2..L5 are four additional routing layers** whose physical heights are
  *not confirmed* - they are configurable simulation inputs with provenance
  ``unconfirmed_simulation``; formal process acceptance must therefore be
  refused while they are unconfirmed;
* multi-transition routes are allowed (``L1 -> L2 -> L3 -> L1`` etc.);
* the old 2.5D model (``z1 = layer 0 / z2 = layer 4``) is WRONG and its counts
  (A 985 / B 723) are historical-only and never mixed into the corrected numbers.

Usage::

    python -m four_side_1024.l3d.stats_l3d
    python -m four_side_1024.l3d.stats_l3d --root outputs/four_side_1024_v2_l1l5_v01

Reads (all optional; missing/partial data -> null + warning, never crash)::

    <root>/baseline/scheme{A,B}/routes_l3d.json + run_summary.json
    <root>/l3d/scheme{A,B}/layers5_<stack>/routes_l3d.json + run_summary.json
    <root>/layer_stacks/<stack>.json
    <root>/validation/**/*.json        (independent validator output)

Writes ONLY ``<root>/summary/``::

    l3d_statistics.json          full machine-readable statistics
    l3d_statistics.md            human-readable report
    l3d_comparison.md            corrected vs historical / R15-2D / sensitivity
    l3d_per_route.csv            one row per route record (all stages)
    l3d_layer_usage.csv          physical-plane and logical-layer usage
    l3d_transition_pairs.csv     transition (from_layer,to_layer,dz) histogram
    l3d_loss_parameters.json     calibrated / uncalibrated loss parameters only

No loss coefficients are invented: propagation 0.05 dB/cm is the experiment
convention (not measured), bend / crossing / interlayer losses are
``unknown_uncalibrated`` and no total-loss conclusion is produced.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import time
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = PROJECT_ROOT / 'outputs' / 'four_side_1024_v2_l1l5_v01'

SCHEMA_STATISTICS = 'four_side_1024_v2_l3d_statistics_v1'
SCHEMA_LOSS = 'four_side_1024_v2_l3d_loss_parameters_v1'

SCHEMES = ('A', 'B')
PLANES = ('z1', 'z2')
INTERFACE_LAYER_ID = 1
ROUTING_LAYER_IDS = (2, 3, 4, 5)
ALL_LAYER_IDS = (1, 2, 3, 4, 5)
INTERFACE_ROWS = {'z1': 0.0, 'z2': 0.5}
PRIMARY_STACK = 'medium_050'
SENSITIVITY_STACKS = ('compact_025', 'wide_100')
STACK_ORDER = (PRIMARY_STACK, 'compact_025', 'wide_100')
PROVENANCE_UNCONFIRMED = 'unconfirmed_simulation'
PROVENANCE_CONFIRMED = 'confirmed'
CLEARANCE_MM = 0.08
EXPECTED_RADIUS_MM = 15.0
RADIUS_TOL_MM = 1e-6
DASH = '—'

#: documented exploratory presets from SCHEMA_L3D.md sec.1 (fallback only)
STACK_PRESETS = {
    'medium_050': dict(heights={2: 1.0, 3: 1.5, 4: 2.0, 5: 2.5},
                       note='0.5 mm spacing above the top interface row; exploratory'),
    'compact_025': dict(heights={2: 0.75, 3: 1.0, 4: 1.25, 5: 1.5},
                        note='0.25 mm spacing; minimum-clearance exploratory stack'),
    'wide_100': dict(heights={2: 1.5, 3: 2.5, 4: 3.5, 5: 4.5},
                     note='1.0 mm spacing; exploratory'),
}

#: corrected-model reference numbers (task-provided, not derived from old 2.5D)
R15_2D_BASELINE = {
    'A': dict(total=943, z1=498, z2=445),
    'B': dict(total=515, z1=184, z2=331),
}
OLD_5L_HISTORICAL = dict(
    A=985, B=723,
    note=('historical old-5L numbers from the WRONG model (z1=L1 / z2=L5); '
          'they are NOT comparable with corrected L1-L5 results and must never '
          'be mixed into the corrected numbers'),
)
PROPAGATION_LOSS_DB_PER_CM = 0.05


# ---------------------------------------------------------------------------
# generic helpers
# ---------------------------------------------------------------------------
def _now_utc():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def _display_path(path):
    path = Path(path)
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve())).replace('\\', '/')
    except (ValueError, OSError):
        return str(path).replace('\\', '/')


def _load_json(path, warnings, what, required=False):
    path = Path(path)
    if not path.exists():
        if required:
            warnings.append(f'{what}: missing ({_display_path(path)})')
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        warnings.append(f'{what}: cannot read/parse ({_display_path(path)}): {exc}')
        return None


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False),
                    encoding='utf-8')
    return path


def _write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def _pick(*values):
    for value in values:
        if value is not None:
            return value
    return None


def _num(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _round(value, digits=6):
    if value is None:
        return None
    return round(float(value), digits)


def _mean(values):
    values = [value for value in values if value is not None]
    return (sum(values) / len(values)) if values else None


def _sum(values):
    values = [value for value in values if value is not None]
    return sum(values) if values else 0.0


def _pct(part, whole):
    if part is None or not whole:
        return None
    return round(100.0 * part / whole, 4)


def _same_number(first, second, rel=1e-6, abs_tol=1e-9):
    if first is None or second is None:
        return True
    return abs(float(first) - float(second)) <= max(abs_tol,
                                                   rel * max(1.0, abs(float(second))))


def _fmt_int(value):
    return DASH if value is None else f'{int(value):,}'


def _fmt_num(value, digits=3):
    return DASH if value is None else f'{float(value):,.{digits}f}'


def _fmt_delta(value):
    if value is None:
        return DASH
    if int(value) == 0:
        return '0'
    return f'{int(value):+d}'


def _md_table(headers, rows, aligns=None):
    aligns = list(aligns or ['---'] * len(headers))
    lines = ['| ' + ' | '.join(str(item) for item in headers) + ' |',
             '|' + '|'.join(aligns) + '|']
    for row in rows:
        lines.append('| ' + ' | '.join(str(item) for item in row) + ' |')
    return lines


def _pass_fail(value):
    if value is True:
        return 'PASS'
    if value is False:
        return 'FAIL'
    return DASH


def _yes_no(value):
    if value is True:
        return '是'
    if value is False:
        return '否'
    return DASH


def _console(value, digits=None):
    if value is None:
        return 'n/a'
    if isinstance(value, bool):
        return 'yes' if value else 'no'
    if isinstance(value, float) and digits is not None:
        return f'{value:.{digits}f}'
    return str(value)


# ---------------------------------------------------------------------------
# flat / transition geometry (recomputed from JSON parameters)
# ---------------------------------------------------------------------------
def _primitive_metrics(primitive):
    kind = primitive.get('kind')
    if kind == 'line':
        p0 = primitive.get('p0') or [0.0, 0.0]
        p1 = primitive.get('p1') or [0.0, 0.0]
        return dict(kind='line',
                    length_mm=math.hypot(float(p1[0]) - float(p0[0]),
                                         float(p1[1]) - float(p0[1])),
                    radius_mm=None, sweep_deg=None)
    if kind == 'arc':
        radius = abs(float(primitive.get('radius') or 0.0))
        sweep = float(primitive.get('sweep') or 0.0)
        return dict(kind='arc', length_mm=abs(sweep) * radius,
                    radius_mm=radius, sweep_deg=math.degrees(sweep))
    return dict(kind=str(kind), length_mm=0.0, radius_mm=None, sweep_deg=None)


def _flat_geometry(primitives):
    pieces = [_primitive_metrics(primitive) for primitive in (primitives or [])]
    lines = [piece for piece in pieces if piece['kind'] == 'line']
    arcs = [piece for piece in pieces if piece['kind'] == 'arc']
    straight = _sum(piece['length_mm'] for piece in lines)
    arc_length = _sum(piece['length_mm'] for piece in arcs)
    radii = Counter()
    for piece in arcs:
        radii[f'{piece["radius_mm"]:.6f}'] += 1
    return dict(
        length_mm=straight + arc_length,
        straight_length_mm=straight,
        arc_length_mm=arc_length,
        line_count=len(lines),
        arc_count=len(arcs),
        radius_distribution=dict(sorted(radii.items(),
                                        key=lambda item: float(item[0]))),
        unexpected_radius_arc_count=sum(
            count for key, count in radii.items()
            if abs(float(key) - EXPECTED_RADIUS_MM) > RADIUS_TOL_MM),
    )


def _transition_geometry(part):
    radius = abs(float(part.get('radius_mm') or 0.0))
    z0 = _num(part.get('z0'))
    z1 = _num(part.get('z1'))
    dz_saved = _num(part.get('dz_mm'))
    dz = abs((z1 - z0)) if (z0 is not None and z1 is not None) else dz_saved
    theta = footprint = length = None
    if radius > 0 and dz is not None and dz < 2.0 * radius:
        theta = math.acos(max(-1.0, min(1.0, 1.0 - dz / (2.0 * radius))))
        footprint = 2.0 * radius * math.sin(theta)
        length = 2.0 * radius * theta
    return dict(
        from_layer=_int(part.get('from_layer')),
        to_layer=_int(part.get('to_layer')),
        radius_mm=radius,
        z0=_num(z0),
        z1=_num(z1),
        dz_mm=dz,
        dz_signed_mm=(z1 - z0) if (z0 is not None and z1 is not None) else None,
        theta_rad=theta,
        theta_deg=(math.degrees(theta) if theta is not None else None),
        footprint_mm=footprint,
        length_mm=length,
        saved_theta_rad=_num(part.get('theta_rad')),
        saved_footprint_mm=_num(part.get('footprint_mm')),
        saved_length_mm=_num(part.get('length_mm')),
        saved_dz_mm=dz_saved,
        theta_matches=(_same_number(_num(part.get('theta_rad')), theta)
                       if theta is not None else None),
        footprint_matches=(_same_number(_num(part.get('footprint_mm')),
                                        footprint) if footprint is not None else None),
        length_matches=(_same_number(_num(part.get('length_mm')), length)
                        if length is not None else None),
        dz_matches=(_same_number(abs(dz_saved) if dz_saved is not None else None,
                                 dz) if dz is not None else None),
        radius_expected=bool(abs(radius - EXPECTED_RADIUS_MM) <= RADIUS_TOL_MM),
    )


# ---------------------------------------------------------------------------
# layer-stack handling
# ---------------------------------------------------------------------------
def _preset_stack(name):
    preset = STACK_PRESETS.get(name)
    if preset is None:
        return None
    return dict(
        name=name,
        provenance=PROVENANCE_UNCONFIRMED,
        formal_acceptance_allowed=False,
        interface_rows=dict(INTERFACE_ROWS),
        routing_heights_mm={str(layer_id): float(height)
                            for layer_id, height in preset['heights'].items()},
        note=preset['note'],
        source='SCHEMA_L3D.md preset fallback',
    )


def _stack_from_payload(stack_payload, name=None):
    """Normalise a layer_stack dict (from routes/run_summary/layer_stacks json)."""
    if not isinstance(stack_payload, dict):
        return None
    heights = {}
    raw_heights = stack_payload.get('routing_heights_mm')
    if isinstance(raw_heights, dict):
        for key, value in raw_heights.items():
            layer_id = _int(key)
            height = _num(value)
            if layer_id is not None and height is not None:
                heights[layer_id] = height
    layers = stack_payload.get('layers')
    interface_rows = dict(INTERFACE_ROWS)
    if isinstance(layers, dict):
        interface = layers.get(str(INTERFACE_LAYER_ID)) or layers.get(INTERFACE_LAYER_ID)
        if isinstance(interface, dict) and isinstance(
                interface.get('interface_rows'), dict):
            interface_rows = {row: float(value) for row, value in
                              interface['interface_rows'].items()}
        for layer_id in ROUTING_LAYER_IDS:
            if layer_id in heights:
                continue  # routing_heights_mm is the explicit authority
            layer = layers.get(str(layer_id)) or layers.get(layer_id)
            if isinstance(layer, dict) and _num(layer.get('physical_z_mm')) is not None:
                heights[layer_id] = _num(layer.get('physical_z_mm'))
    return dict(
        name=name,
        provenance=stack_payload.get('provenance', PROVENANCE_UNCONFIRMED),
        formal_acceptance_allowed=bool(
            stack_payload.get('formal_acceptance_allowed', False)),
        interface_rows=interface_rows,
        routing_heights_mm={str(layer_id): float(height)
                            for layer_id, height in sorted(heights.items())},
        note=stack_payload.get('note', ''),
        source='embedded layer_stack payload',
        payload=stack_payload,
    )


def _stack_validation(stack):
    """Independently validate the corrected-model stack invariants."""
    errors = []
    if stack is None:
        return dict(valid=False, errors=['layer stack unavailable'],
                    min_plane_gap_mm=None, physical_planes=[])
    provenance = stack.get('provenance')
    if provenance not in (PROVENANCE_UNCONFIRMED, PROVENANCE_CONFIRMED):
        errors.append(f'invalid provenance {provenance!r}')
    interface_rows = stack.get('interface_rows') or {}
    if {row: float(value) for row, value in interface_rows.items()} != INTERFACE_ROWS:
        errors.append(f'L1 interface rows must be {INTERFACE_ROWS}, got {interface_rows}')
    heights = {}
    for layer_id in ROUTING_LAYER_IDS:
        height = _num((stack.get('routing_heights_mm') or {}).get(str(layer_id)))
        if height is None:
            errors.append(f'L{layer_id} has no physical height')
        elif not math.isfinite(height):
            errors.append(f'L{layer_id} height is not finite')
        else:
            heights[layer_id] = height
    ordered = sorted(heights.items(), key=lambda item: item[1])
    min_gap = None
    for (layer_a, z_a), (layer_b, z_b) in zip(ordered, ordered[1:]):
        gap = z_b - z_a
        min_gap = gap if min_gap is None else min(min_gap, gap)
        if gap <= CLEARANCE_MM:
            errors.append(f'L{layer_a}={z_a:g} and L{layer_b}={z_b:g} are closer '
                          f'than the {CLEARANCE_MM:g} mm clearance')
    for row, z_row in INTERFACE_ROWS.items():
        for layer_id, height in heights.items():
            gap = abs(height - z_row)
            min_gap = gap if min_gap is None else min(min_gap, gap)
            if gap <= CLEARANCE_MM:
                errors.append(f'L{layer_id}={height:g} is closer than clearance to '
                              f'interface row {row}={z_row:g}')
    if set(stack.get('routing_heights_mm') or {}) != {str(i) for i in ROUTING_LAYER_IDS}:
        errors.append('routing heights must cover exactly L2..L5')
    physical_planes = _physical_planes_from_stack(stack, heights)
    return dict(valid=not errors, errors=errors,
                min_plane_gap_mm=_round(min_gap, 9),
                physical_planes=physical_planes,
                formal_acceptance_allowed=bool(
                    provenance == PROVENANCE_CONFIRMED
                    and stack.get('formal_acceptance_allowed')))


def _physical_planes_from_stack(stack, heights):
    """Physical planes of the stack: L1 appears TWICE (two rows)."""
    planes = []
    for row in PLANES:
        planes.append(dict(
            key=f'L1:{row}',
            label=f'L1 {row} row',
            z_mm=float(INTERFACE_ROWS[row]),
            logical_layer_id=INTERFACE_LAYER_ID,
            layer_type='interface',
            row=row,
        ))
    for layer_id, height in sorted(heights.items(), key=lambda item: item[1]):
        planes.append(dict(
            key=f'L{layer_id}',
            label=f'L{layer_id}',
            z_mm=float(height),
            logical_layer_id=int(layer_id),
            layer_type='routing',
            row=None,
        ))
    planes.sort(key=lambda plane: (plane['z_mm'], plane['key']))
    return planes


def _stack_lookup(stack):
    """Return helper maps for a normalised stack."""
    heights = {int(layer_id): float(height)
               for layer_id, height in (stack.get('routing_heights_mm') or {}).items()
               if _int(layer_id) is not None and _num(height) is not None}
    interface_rows = {row: float(value) for row, value in
                      (stack.get('interface_rows') or INTERFACE_ROWS).items()}
    planes = _physical_planes_from_stack(stack, heights)
    z_to_plane = {}
    for plane in planes:
        z_to_plane[_plane_key(plane['z_mm'])] = plane
    return dict(heights=heights, interface_rows=interface_rows,
                planes=planes, z_to_plane=z_to_plane)


def _plane_key(z_mm):
    return f'{float(z_mm):.6f}'


def _plane_label_for_z(z_mm, lookup):
    plane = lookup['z_to_plane'].get(_plane_key(z_mm))
    if plane is None:
        return f'z={float(z_mm):g} mm (unmapped)'
    return f'{plane["label"]} (z={float(z_mm):g} mm)'


# ---------------------------------------------------------------------------
# route-record analysis
# ---------------------------------------------------------------------------
def _analyse_route(record, lookup, warnings, tag):
    """Analyse one route record; returns (metrics dict, per-route csv row)."""
    parts = record.get('parts') or []
    flat_parts = [part for part in parts if part.get('kind') == 'flat']
    transitions = [part for part in parts if part.get('kind') == 'transition']
    flat_length = 0.0
    flat_length_saved = 0.0
    flat_straight_length = 0.0
    flat_arc_length = 0.0
    flat_arc_count = 0
    flat_radius_counter = Counter()
    flat_length_by_z = Counter()
    flat_parts_by_z = Counter()
    flat_layer_ids_by_z = {}
    flat_length_by_layer = Counter()
    flat_parts_by_layer = Counter()
    plane_touch = {}
    flat_radius_counter = Counter()
    transition_metrics = []
    for part in flat_parts:
        geometry = _flat_geometry(part.get('primitives') or [])
        z_mm = _num(part.get('z_mm'))
        layer_id = _int(part.get('layer_id'))
        flat_length += geometry['length_mm']
        flat_straight_length += geometry['straight_length_mm']
        flat_arc_length += geometry['arc_length_mm']
        flat_arc_count += geometry['arc_count']
        flat_length_saved += float(part.get('length_mm') or 0.0)
        if z_mm is not None:
            flat_length_by_z[_plane_key(z_mm)] += geometry['length_mm']
            flat_parts_by_z[_plane_key(z_mm)] += 1
            plane_touch[_plane_key(z_mm)] = True
        if z_mm is not None and layer_id is not None:
            flat_layer_ids_by_z.setdefault(_plane_key(z_mm), set()).add(int(layer_id))
        if layer_id is not None:
            flat_length_by_layer[layer_id] += geometry['length_mm']
            flat_parts_by_layer[layer_id] += 1
        for radius, count in geometry['radius_distribution'].items():
            flat_radius_counter[radius] += count
        if geometry['unexpected_radius_arc_count']:
            warnings.append(f'{tag}: route {record.get("route_id")} flat part has '
                            f'non-R15 flat arc radii'
                            f' {geometry["radius_distribution"]}')
    for part in transitions:
        metrics = _transition_geometry(part)
        transition_metrics.append(metrics)
        if metrics['theta_matches'] is False or metrics['footprint_matches'] is False \
                or metrics['length_matches'] is False or metrics['dz_matches'] is False:
            warnings.append(f'{tag}: route {record.get("route_id")} transition '
                            f'L{metrics["from_layer"]}->L{metrics["to_layer"]} has '
                            f'inconsistent saved theta/footprint/length/dz')
        if not metrics['radius_expected']:
            warnings.append(f'{tag}: route {record.get("route_id")} transition '
                            f'radius {metrics["radius_mm"]:g} != R15')
    flat_length = round(flat_length, 9)
    transition_length = _sum(metrics['length_mm'] for metrics in transition_metrics)
    z0s = [metrics['z0'] for metrics in transition_metrics if metrics['z0'] is not None]
    z1s = [metrics['z1'] for metrics in transition_metrics if metrics['z1'] is not None]
    z_span = (_max_minus_min(z0s + z1s) if (z0s or z1s) else 0.0)
    layer_sequence = [_int(value) for value in (record.get('layer_sequence') or [])
                      if _int(value) is not None]
    layer_z_sequence = [_num(value) for value in (record.get('layer_z_sequence') or [])]
    n_transitions_saved = _int(record.get('n_transitions'))
    total_length = flat_length + transition_length
    metrics = dict(
        flat_length_mm=flat_length,
        flat_length_saved_mm=round(flat_length_saved, 9),
        transition_length_mm=transition_length,
        total_length_mm=total_length,
        total_length_saved_mm=_num(record.get('length_mm')),
        xy_length_mm=_num(record.get('xy_length_mm')),
        flat_parts_count=len(flat_parts),
        transition_parts_count=len(transitions),
        n_transitions_saved=n_transitions_saved,
        transitions=transition_metrics,
        flat_parts_by_z={key: count for key, count in flat_parts_by_z.items()},
        flat_layer_ids_by_z={key: sorted(values)
                             for key, values in flat_layer_ids_by_z.items()},
        flat_straight_length_mm=flat_straight_length,
        flat_arc_length_mm=flat_arc_length,
        flat_arc_count=flat_arc_count,
        flat_length_by_z={key: round(value, 9)
                          for key, value in flat_length_by_z.items()},
        flat_parts_by_layer={layer: count
                             for layer, count in flat_parts_by_layer.items()},
        flat_length_by_layer={layer: round(value, 9)
                              for layer, value in flat_length_by_layer.items()},
        flat_radius_distribution=dict(sorted(flat_radius_counter.items(),
                                             key=lambda item: float(item[0]))),
        layer_sequence=layer_sequence,
        layer_z_sequence=layer_z_sequence,
        z_span_mm=(_num(record.get('z_span_mm')) if _num(record.get('z_span_mm'))
                   is not None else round(z_span, 9)),
        planes_touched=sorted(plane_touch),
        sequence_z_consistent=_sequence_z_consistent(layer_sequence,
                                                     layer_z_sequence, lookup),
        start_end_l1=(bool(layer_sequence) and layer_sequence[0] == INTERFACE_LAYER_ID
                      and layer_sequence[-1] == INTERFACE_LAYER_ID),
        n_transitions_consistent=(n_transitions_saved is None
                                  or n_transitions_saved == len(transitions)),
    )
    row = dict(
        scheme=record.get('scheme'),
        route_id=_int(record.get('route_id')),
        plane=record.get('plane'),
        status=record.get('status'),
        reason=record.get('reason'),
        baseline_2d=bool(record.get('baseline_2d')),
        mode=record.get('mode'),
        lifted=bool(record.get('lifted')),
        n_transitions=(n_transitions_saved if n_transitions_saved is not None
                       else len(transitions)),
        layer_sequence='->'.join(str(value) for value in layer_sequence),
        layer_z_sequence=';'.join(f'{value:g}' for value in layer_z_sequence
                                  if value is not None),
        layers_used=';'.join(str(value) for value in
                             (record.get('layers_used') or [])),
        xy_length_mm=_num(record.get('xy_length_mm')),
        length_mm=_num(record.get('length_mm')),
        flat_length_mm=round(flat_length, 6),
        transition_length_mm=round(transition_length, 6),
        z_span_mm=metrics['z_span_mm'],
        start_z_mm=_num(record.get('start_z_mm')),
        end_z_mm=_num(record.get('end_z_mm')),
        source_row=_int(record.get('source_row')),
        target_row=_int(record.get('target_row')),
        flat_parts_count=len(flat_parts),
        transition_parts_count=len(transitions),
        flat_radius_distribution=metrics['flat_radius_distribution'],
        transition_radii=sorted({f'{metrics["radius_mm"]:.6f}'
                                 for metrics in transition_metrics}),
    )
    return metrics, row


def _max_minus_min(values):
    values = [value for value in values if value is not None]
    if not values:
        return 0.0
    return max(values) - min(values)


def _sequence_z_consistent(layer_sequence, layer_z_sequence, lookup):
    if not layer_sequence or not layer_z_sequence:
        return None
    if len(layer_sequence) != len(layer_z_sequence):
        return False
    heights = lookup['heights']
    rows = lookup['interface_rows']
    for layer_id, z_mm in zip(layer_sequence, layer_z_sequence):
        if z_mm is None:
            return False
        if layer_id == INTERFACE_LAYER_ID:
            if not any(abs(float(z_mm) - float(row_z)) <= 1e-6
                       for row_z in rows.values()):
                return False
        else:
            expected = heights.get(layer_id)
            if expected is None or abs(float(z_mm) - expected) > 1e-6:
                return False
    return True


# ---------------------------------------------------------------------------
# run / baseline analysis
# ---------------------------------------------------------------------------
def _empty_run_entry(scheme, stack_name, stage):
    return dict(
        present=False, scheme=scheme, stack=stack_name, stage=stage,
        source_routes=None, source_summary=None, run_summary_seconds=None,
        run_summary_config=None, layer_stack=None, stack_provenance=None,
        stack_formal_acceptance_allowed=None, stack_valid=None,
        stack_validation_errors=[], min_plane_gap_mm=None,
        router_stats=None, stats_saved=None, process=None,
        routed=None, total=None, failed=None, baseline_routed=None,
        new_routed=None, added=None, flat_l1_routed=None,
        lifted=None, transitions=None, transitions_histogram=None,
        transitions_grouped=None, transition_pairs=None,
        transition_geometry=None, layers_used_histogram=None,
        layer_sequence_histogram=None, physical_planes=None,
        logical_layers=None, length=None, z_span_distribution=None,
        per_plane=None, failure_reasons=None, failure_by_plane=None,
        validation=None, formal_acceptance_granted=False,
        formal_acceptance_status='NOT_GRANTED', warnings=[],
    )


def _find_run_dir(root, scheme, stack_name):
    candidates = [
        Path(root) / 'l3d' / f'scheme{scheme}' / f'layers5_{stack_name}',
        Path(root) / f'scheme{scheme}' / f'layers5_{stack_name}',
        Path(root) / 'runs' / f'scheme{scheme}' / f'layers5_{stack_name}',
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


def _load_stack_definition(root, stack_name, run_payload, run_summary, warnings):
    stack = None
    for payload in (run_payload or {}, run_summary or {}):
        if isinstance(payload, dict) and isinstance(payload.get('layer_stack'), dict):
            stack = _stack_from_payload(payload['layer_stack'], stack_name)
            if stack and stack.get('routing_heights_mm'):
                return stack
    stack_path = Path(root) / 'layer_stacks' / f'{stack_name}.json'
    payload = _load_json(stack_path, warnings,
                         f'layer_stacks/{stack_name}.json')
    if isinstance(payload, dict):
        stack = _stack_from_payload(payload, stack_name)
        if stack:
            return stack
    preset = _preset_stack(stack_name)
    if preset is not None:
        return preset
    return None


def _analyse_run(root, scheme, stack_name, stage, validation, warnings):
    tag = f'l3d/scheme{scheme}/layers5_{stack_name}'
    run_dir = _find_run_dir(root, scheme, stack_name)
    routes_path = run_dir / 'routes_l3d.json'
    summary_path = run_dir / 'run_summary.json'
    entry = _empty_run_entry(scheme, stack_name, stage)
    entry['warnings'] = []
    if not routes_path.exists() and not summary_path.exists():
        warnings.append(f'{tag}: no routes_l3d.json/run_summary.json yet '
                        f'(null fields)')
        return entry
    payload = _load_json(routes_path, warnings, f'{tag}/routes_l3d.json')
    summary = _load_json(summary_path, warnings, f'{tag}/run_summary.json')
    payload = payload if isinstance(payload, dict) else {}
    summary = summary if isinstance(summary, dict) else {}
    records = payload.get('routes') if isinstance(payload.get('routes'), list) else None
    if records is None and payload:
        warnings.append(f'{tag}: routes_l3d.json has no routes list')
    stack = _load_stack_definition(root, stack_name, payload, summary, warnings)
    stack_validation = _stack_validation(stack) if stack else dict(
        valid=False, errors=['layer stack unavailable'], min_plane_gap_mm=None,
        physical_planes=[])
    if stack is None:
        warnings.append(f'{tag}: layer stack definition unavailable; physical '
                        f'plane statistics null')
    lookup = _stack_lookup(stack) if stack else _stack_lookup(_preset_stack(
        PRIMARY_STACK) or {})
    entry.update(
        present=True,
        stage=(payload.get('stage') or summary.get('stage') or stage),
        source_routes=_display_path(routes_path) if routes_path.exists() else None,
        source_summary=_display_path(summary_path) if summary_path.exists() else None,
        run_summary_seconds=_num(summary.get('seconds')),
        run_summary_config=summary.get('config') if isinstance(
            summary.get('config'), dict) else None,
        layer_stack=(stack.get('payload') if stack and stack.get('payload')
                     else stack),
        stack_provenance=(stack.get('provenance') if stack else None),
        stack_formal_acceptance_allowed=(
            stack.get('formal_acceptance_allowed') if stack else None),
        stack_valid=stack_validation['valid'],
        stack_validation_errors=stack_validation['errors'],
        min_plane_gap_mm=stack_validation['min_plane_gap_mm'],
        router_stats=payload.get('router') if isinstance(payload.get('router'), dict)
        else summary.get('router'),
        stats_saved=payload.get('statistics') if isinstance(
            payload.get('statistics'), dict) else summary.get('statistics'),
        process=payload.get('process') if isinstance(payload.get('process'), dict)
        else None,
    )
    if stack is not None and stack.get('provenance') == PROVENANCE_UNCONFIRMED:
        entry['warnings'].append(
            'layer stack provenance is unconfirmed_simulation: formal process '
            'acceptance is NOT granted (heights are simulation inputs)')
    if records is None:
        validation_view = validation
        entry['validation'] = validation_view
        return entry
    stats_saved = entry.get('stats_saved') or {}
    routed = [record for record in records if record.get('status') == 'routed']
    failed = [record for record in records if record.get('status') != 'routed']
    plane_index = lookup['planes']
    plane_by_key = lookup['z_to_plane']
    physical_planes = {}
    for plane in plane_index:
        physical_planes[plane['key']] = dict(
            key=plane['key'], label=plane['label'], z_mm=plane['z_mm'],
            logical_layer_ids=sorted({plane['logical_layer_id']}),
            layer_type=plane['layer_type'], row=plane['row'],
            routes_touching=set(), flat_parts=0, flat_length_mm=0.0)
    logical_layers = {layer_id: dict(
        layer_id=layer_id, layer_type=('interface' if layer_id == INTERFACE_LAYER_ID
                                       else 'routing'),
        physical_z_mm=(None if layer_id == INTERFACE_LAYER_ID
                       else lookup['heights'].get(layer_id)),
        interface_rows=(dict(INTERFACE_ROWS) if layer_id == INTERFACE_LAYER_ID
                        else {}),
        routes_touching=set(), flat_parts=0, flat_length_mm=0.0,
        transition_endpoints=0) for layer_id in ALL_LAYER_IDS}
    transitions_histogram = Counter()
    layers_used_histogram = Counter()
    layer_sequence_histogram = Counter()
    transition_pairs = {}
    transition_count = 0
    flat_length_total = 0.0
    transition_length_total = 0.0
    total_length = 0.0
    total_xy_length = 0.0
    theta_total = 0.0
    footprint_total = 0.0
    radius_counter = Counter()
    z_span_values = []
    per_plane = {plane: dict(routed=0, baseline=0, lifted=0) for plane in PLANES}
    failure_reasons = Counter()
    failure_by_plane = {plane: Counter() for plane in PLANES}
    baseline_count = 0
    lifted_count = 0
    per_route_rows = []
    transition_mismatch_count = 0
    flat_radius_counter = Counter()
    flat_arc_count = 0
    flat_straight_length = 0.0
    flat_arc_length = 0.0
    for record in routed:
        metrics, row = _analyse_route(record, lookup, warnings, tag)
        row.update(scheme=scheme, stack=stack_name, stage=stage)
        per_route_rows.append(row)
        for radius, count in (metrics.get('flat_radius_distribution') or {}).items():
            flat_radius_counter[radius] += count
        flat_arc_count += int(metrics.get('flat_arc_count') or 0)
        flat_straight_length += float(metrics.get('flat_straight_length_mm') or 0.0)
        flat_arc_length += float(metrics.get('flat_arc_length_mm') or 0.0)
        baseline_count += 1 if record.get('baseline_2d') else 0
        plane = record.get('plane')
        if plane in per_plane:
            per_plane[plane]['routed'] += 1
            per_plane[plane]['baseline'] += 1 if record.get('baseline_2d') else 0
            per_plane[plane]['lifted'] += 1 if record.get('lifted') else 0
        if record.get('lifted'):
            lifted_count += 1
        transitions_histogram[int(metrics['n_transitions_saved']
                                  if metrics['n_transitions_saved'] is not None
                                  else metrics['transition_parts_count'])] += 1
        sequence = metrics['layer_sequence'] or [INTERFACE_LAYER_ID]
        layer_sequence_histogram['->'.join(str(value) for value in sequence)] += 1
        used = record.get('layers_used')
        if not used:
            used = sorted({value for value in sequence})
        layers_used_histogram[','.join(str(int(value)) for value in used)] += 1
        if not metrics['start_end_l1']:
            warnings.append(f'{tag}: route {record.get("route_id")} does not start/end '
                            f'on L1: layer_sequence={sequence}')
        if metrics['sequence_z_consistent'] is False:
            warnings.append(f'{tag}: route {record.get("route_id")} layer_z_sequence '
                            f'does not match the layer stack mapping')
        if metrics['n_transitions_consistent'] is False:
            warnings.append(f'{tag}: route {record.get("route_id")} n_transitions != '
                            f'number of transition parts')
        for key, count in metrics['flat_parts_by_z'].items():
            stack_plane = plane_by_key.get(key)
            if stack_plane is not None:
                plane_entry = physical_planes.get(stack_plane['key'])
                if plane_entry is None:
                    plane_entry = dict(
                        key=stack_plane['key'], label=stack_plane.get('label'),
                        z_mm=stack_plane.get('z_mm'),
                        logical_layer_ids=[stack_plane.get('logical_layer_id')],
                        layer_type=stack_plane.get('layer_type'),
                        row=stack_plane.get('row'), routes_touching=set(),
                        flat_parts=0, flat_length_mm=0.0)
                    physical_planes[plane_entry['key']] = plane_entry
            else:
                # unmapped physical z: still report it as a physical plane group
                plane_entry = physical_planes.get(f'z={key}') or dict(
                    key=f'z={key}', label=f'z={key} mm (unmapped)',
                    z_mm=float(key), logical_layer_ids=[], layer_type='unknown',
                    row=None, routes_touching=set(), flat_parts=0,
                    flat_length_mm=0.0)
                physical_planes[plane_entry['key']] = plane_entry
            plane_entry['routes_touching'].add(record.get('route_id'))
            plane_entry['flat_parts'] += count
            plane_entry['flat_length_mm'] += metrics['flat_length_by_z'].get(key, 0.0)
            layer_ids = set(plane_entry.get('logical_layer_ids') or [])
            for layer_id in metrics['flat_layer_ids_by_z'].get(key, ()):
                layer_ids.add(int(layer_id))
            plane_entry['logical_layer_ids'] = sorted(layer_ids)
        for layer_id, count in metrics['flat_parts_by_layer'].items():
            layer_entry = logical_layers.setdefault(int(layer_id), dict(
                layer_id=int(layer_id), layer_type='unknown', physical_z_mm=None,
                interface_rows={}, routes_touching=set(), flat_parts=0,
                flat_length_mm=0.0, transition_endpoints=0))
            layer_entry['routes_touching'].add(record.get('route_id'))
            layer_entry['flat_parts'] += count
            layer_entry['flat_length_mm'] += metrics['flat_length_by_layer'].get(
                int(layer_id), 0.0)
        for layer_id in metrics['layer_sequence']:
            layer_entry = logical_layers.setdefault(int(layer_id), dict(
                layer_id=int(layer_id), layer_type='unknown', physical_z_mm=None,
                interface_rows={}, routes_touching=set(), flat_parts=0,
                flat_length_mm=0.0, transition_endpoints=0))
            layer_entry['routes_touching'].add(record.get('route_id'))
        for transition in metrics['transitions']:
            transition_count += 1
            if transition['theta_deg'] is not None:
                theta_total += transition['theta_deg']
            if transition['footprint_mm'] is not None:
                footprint_total += transition['footprint_mm']
            radius_counter[f'{transition["radius_mm"]:.6f}'] += 1
            for layer_id in (transition['from_layer'], transition['to_layer']):
                if layer_id in logical_layers:
                    logical_layers[layer_id]['transition_endpoints'] += 1
            pair_key = (transition['from_layer'], transition['to_layer'],
                        _round(transition['dz_signed_mm'], 6))
            pair = transition_pairs.setdefault(pair_key, dict(
                from_layer=transition['from_layer'],
                to_layer=transition['to_layer'],
                dz_signed_mm=_round(transition['dz_signed_mm'], 6),
                dz_abs_mm=_round(transition['dz_mm'], 6),
                count=0, theta_deg_total=0.0, footprint_mm_total=0.0,
                length_mm_total=0.0, radius_values=set()))
            pair['count'] += 1
            pair['theta_deg_total'] += transition['theta_deg'] or 0.0
            pair['footprint_mm_total'] += transition['footprint_mm'] or 0.0
            pair['length_mm_total'] += transition['length_mm'] or 0.0
            pair['radius_values'].add(round(transition['radius_mm'], 6))
        flat_length_total += metrics['flat_length_mm']
        transition_length_total += metrics['transition_length_mm']
        total_length += metrics['total_length_mm']
        total_xy_length += metrics['xy_length_mm'] or 0.0
        if metrics['z_span_mm'] is not None:
            z_span_values.append(metrics['z_span_mm'])
        if not _same_number(metrics['total_length_saved_mm'],
                            metrics['total_length_mm']):
            transition_mismatch_count += 1
    for record in failed:
        reason = str(record.get('reason') or 'unknown')
        failure_reasons[reason] += 1
        plane = record.get('plane')
        if plane in failure_by_plane:
            failure_by_plane[plane][reason] += 1
        per_route_rows.append(dict(
            scheme=scheme, stack=stack_name, stage=stage,
            route_id=_int(record.get('route_id')), plane=record.get('plane'),
            status=record.get('status'), reason=reason,
            baseline_2d=bool(record.get('baseline_2d')), mode=None,
            lifted=False, n_transitions=None, layer_sequence=None,
            layer_z_sequence=None, layers_used=None, xy_length_mm=None,
            length_mm=None, flat_length_mm=None, transition_length_mm=None,
            z_span_mm=None, start_z_mm=_num(record.get('start_z_mm')),
            end_z_mm=_num(record.get('end_z_mm')),
            source_row=_int(record.get('source_row')),
            target_row=_int(record.get('target_row')),
            flat_parts_count=None, transition_parts_count=None,
            flat_radius_distribution=None, transition_radii=None))
    router_stats = entry.get('router_stats') or {}
    passes = router_stats.get('passes') if isinstance(
        router_stats.get('passes'), list) else []
    attempted = sum(int(item.get('attempted') or 0) for item in passes
                    if isinstance(item, dict))
    attemptable = _int(router_stats.get('attemptable'))
    unattempted = (attemptable - attempted
                   if attemptable is not None and attempted is not None else None)
    rejected = router_stats.get('rejected') if isinstance(
        router_stats.get('rejected'), dict) else {}
    failure_analysis = dict(
        from_records=dict(
            failed_total=len(failed),
            no_2d_candidate=int(failure_reasons.get('no_2d_candidate', 0)),
            unplaceable_in_3d=int(failure_reasons.get('unplaceable_in_3d', 0)),
            other={key: value for key, value in failure_reasons.items()
                   if key not in ('no_2d_candidate', 'unplaceable_in_3d')},
        ),
        from_run_summary=dict(
            attemptable=attemptable,
            attempted=attempted,
            unattempted=unattempted,
            no_candidate=_int(router_stats.get('no_candidate')),
            failed_no_candidate=_int((stats_saved or {}).get('failed_no_candidate')),
            failed_unplaceable=_int(router_stats.get('failed_unplaceable')),
            flat_added=_int(router_stats.get('flat_added')),
            rejected=dict(rejected),
            passes=passes if passes else None,
        ),
        transition_placement_infeasible=_int(
            rejected.get('transition_placement_infeasible')),
        blocked_in_3d=_int(router_stats.get('failed_unplaceable')),
        no_2d_candidate=_int(router_stats.get('no_candidate')),
        note=('no_2d_candidate = the accepted R15 2D layout had no candidate for '
              'this route; blocked_in_3d = attempted but no legal 3D placement; '
              'transition_placement_infeasible = the router rejected a candidate '
              'because the elevation S-curve could not be placed on the 2D path; '
              'unattempted = attemptable routes not yet tried in this run'),
    )
    if transition_mismatch_count:
        warnings.append(f'{tag}: {transition_mismatch_count} routed records disagree '
                        f'between saved length_mm and recomputed flat+transition length')
    if flat_radius_counter and any(
            abs(float(key) - EXPECTED_RADIUS_MM) > RADIUS_TOL_MM
            for key in flat_radius_counter):
        warnings.append(f'{tag}: flat 2D geometry inherited from the R15 layouts '
                        f'contains non-R15 arc radii '
                        f'{dict(flat_radius_counter)}')
    z_span_distribution = Counter()
    for value in z_span_values:
        z_span_distribution[f'{value:.6f}'] += 1
    physical_planes_view = {}
    for key, plane in sorted(physical_planes.items(),
                             key=lambda item: (item[1].get('z_mm') or 0.0,
                                               item[0])):
        physical_planes_view[key] = dict(
            key=key, label=plane.get('label'), z_mm=plane.get('z_mm'),
            logical_layer_ids=sorted(plane.get('logical_layer_ids') or []),
            layer_type=plane.get('layer_type'), row=plane.get('row'),
            routes_touching=len(plane.get('routes_touching') or ()),
            flat_parts=int(plane.get('flat_parts') or 0),
            flat_length_mm=_round(plane.get('flat_length_mm')),
        )
    logical_layers_view = {}
    for layer_id in sorted(logical_layers):
        layer = logical_layers[layer_id]
        logical_layers_view[str(layer_id)] = dict(
            layer_id=int(layer_id), layer_type=layer.get('layer_type'),
            physical_z_mm=_round(layer.get('physical_z_mm')),
            interface_rows=layer.get('interface_rows') or {},
            routes_touching=len(layer.get('routes_touching') or ()),
            flat_parts=int(layer.get('flat_parts') or 0),
            flat_length_mm=_round(layer.get('flat_length_mm')),
            transition_endpoints=int(layer.get('transition_endpoints') or 0),
        )
    transition_pairs_view = []
    for pair in sorted(transition_pairs.values(),
                       key=lambda item: (item['from_layer'] is None,
                                         item['from_layer'] or 0,
                                         item['to_layer'] or 0,
                                         item['dz_signed_mm'] or 0.0)):
        transition_pairs_view.append(dict(
            from_layer=pair['from_layer'], to_layer=pair['to_layer'],
            dz_signed_mm=pair['dz_signed_mm'], dz_abs_mm=pair['dz_abs_mm'],
            count=pair['count'],
            theta_deg_total=_round(pair['theta_deg_total'], 6),
            footprint_mm_total=_round(pair['footprint_mm_total'], 6),
            length_mm_total=_round(pair['length_mm_total'], 6),
            radius_values_mm=sorted(pair['radius_values'])))
    transitions_grouped = _group_transition_histogram(transitions_histogram)
    saved_stats = entry.get('stats_saved') or {}
    routed_count = len(routed)
    added = routed_count - baseline_count
    entry.update(
        routed=routed_count,
        total=len(records),
        failed=len(failed),
        baseline_routed=baseline_count,
        new_routed=(_int(saved_stats.get('new_routed'))
                    if saved_stats.get('new_routed') is not None else added),
        added=added,
        flat_l1_routed=baseline_count,
        lifted=lifted_count,
        transitions=transition_count,
        transitions_histogram=dict(sorted(transitions_histogram.items())),
        transitions_grouped=transitions_grouped,
        transition_pairs=transition_pairs_view,
        transition_geometry=dict(
            count=transition_count,
            radius_distribution=dict(sorted(radius_counter.items(),
                                            key=lambda item: float(item[0]))),
            radius_expected_mm=EXPECTED_RADIUS_MM,
            all_transition_radii_r15=bool(radius_counter) and all(
                abs(float(key) - EXPECTED_RADIUS_MM) <= RADIUS_TOL_MM
                for key in radius_counter),
            theta_deg_total=_round(theta_total, 6),
            footprint_mm_total=_round(footprint_total, 6),
            length_mm_total=_round(transition_length_total, 6),
        ),
        layers_used_histogram=dict(sorted(layers_used_histogram.items())),
        layer_sequence_histogram=dict(sorted(layer_sequence_histogram.items())),
        physical_planes=physical_planes_view,
        flat_geometry=dict(
            arc_count=int(flat_arc_count),
            straight_length_mm=_round(flat_straight_length),
            arc_length_mm=_round(flat_arc_length),
            radius_distribution=dict(sorted(
                flat_radius_counter.items(), key=lambda item: float(item[0]))),
            expected_radius_mm=EXPECTED_RADIUS_MM,
            all_flat_arcs_r15=(bool(flat_radius_counter) and all(
                abs(float(key) - EXPECTED_RADIUS_MM) <= RADIUS_TOL_MM
                for key in flat_radius_counter)
                if flat_radius_counter else None),
            unexpected_flat_arc_count=sum(
                count for key, count in flat_radius_counter.items()
                if abs(float(key) - EXPECTED_RADIUS_MM) > RADIUS_TOL_MM),
        ),
        l1_two_rows_check=dict(
            logical_layer_id=INTERFACE_LAYER_ID,
            physical_plane_count=sum(
                1 for plane in physical_planes_view.values()
                if plane.get('layer_type') == 'interface'),
            z_values_mm=sorted(
                plane.get('z_mm') for plane in physical_planes_view.values()
                if plane.get('layer_type') == 'interface'),
            rows=sorted(
                str(plane.get('row')) for plane in physical_planes_view.values()
                if plane.get('layer_type') == 'interface'),
            note=('L1 is ONE logical routing layer with TWO physical planes: '
                  'z1 row z=0.0 mm and z2 row z=0.5 mm; physical-plane statistics '
                  'therefore list L1 twice, both with logical layer_id=1'),
        ),
        logical_layers=logical_layers_view,
        length=dict(
            xy_total_mm=_round(total_xy_length),
            three_d_total_mm=_round(total_length),
            flat_total_mm=_round(flat_length_total),
            transition_total_mm=_round(transition_length_total),
            mean_3d_length_mm=_round(_safe_divide(total_length, routed_count)),
            mean_xy_length_mm=_round(_safe_divide(total_xy_length, routed_count)),
            mean_transition_length_per_lifted_mm=_round(
                _safe_divide(transition_length_total, lifted_count)),
        ),
        z_span_distribution=dict(sorted(z_span_distribution.items(),
                                        key=lambda item: float(item[0]))),
        per_plane=per_plane,
        failure_reasons=dict(failure_reasons),
        failure_analysis=failure_analysis,
        failure_by_plane={plane: dict(counter)
                          for plane, counter in failure_by_plane.items() if counter},
        validation=validation,
        formal_acceptance_granted=False,
        formal_acceptance_status='NOT_GRANTED',
        formal_acceptance_refusal_reason=(
            'L2-L5 physical heights are unconfirmed_simulation; formal process '
            'acceptance cannot be granted'),
        per_route_rows=per_route_rows,
    )
    entry['warnings'] = list(entry.get('warnings') or [])
    if validation and validation.get('formal_acceptance') is True:
        if stack is None or stack.get('provenance') != PROVENANCE_CONFIRMED:
            warnings.append(f'{tag}: validator reports formal_acceptance=true but the '
                            f'layer stack is unconfirmed; formal acceptance is still '
                            f'refused by the statistics rule')
    return entry


def _safe_divide(numerator, denominator):
    if numerator is None or not denominator:
        return None
    return numerator / denominator


def _group_transition_histogram(histogram):
    return {
        '0': int(histogram.get(0, 0)),
        '2': int(histogram.get(2, 0)),
        '3': int(histogram.get(3, 0)),
        '4+': int(sum(count for key, count in histogram.items() if key >= 4)),
    }


def _analyse_baseline(root, scheme, warnings):
    tag = f'baseline/scheme{scheme}'
    base_dir = Path(root) / 'baseline' / f'scheme{scheme}'
    routes_path = base_dir / 'routes_l3d.json'
    summary_path = base_dir / 'run_summary.json'
    entry = dict(present=False, scheme=scheme, stage='baseline_l1',
                 source_routes=None, source_summary=None,
                 routed=None, failed=None, total=None, per_plane=None,
                 failure_reasons=None, layer_stack=None, provenance=None,
                 two_rows_note=None, expected=R15_2D_BASELINE.get(scheme),
                 matches_expected=None)
    if not routes_path.exists():
        warnings.append(f'{tag}/routes_l3d.json missing (baseline block null)')
        return entry
    payload = _load_json(routes_path, warnings, f'{tag}/routes_l3d.json')
    summary = _load_json(summary_path, warnings, f'{tag}/run_summary.json')
    if not isinstance(payload, dict):
        return entry
    records = payload.get('routes') if isinstance(payload.get('routes'), list) else []
    routed = [record for record in records if record.get('status') == 'routed']
    failed = [record for record in records if record.get('status') != 'routed']
    per_plane = {}
    for plane in PLANES:
        plane_routed = [record for record in routed
                        if record.get('plane') == plane]
        per_plane[plane] = dict(
            routed=len(plane_routed),
            failed=sum(1 for record in failed if record.get('plane') == plane),
            z_mm=float(INTERFACE_ROWS[plane]),
            physical_plane=f'L1 {plane} row',
        )
    expected = R15_2D_BASELINE.get(scheme) or {}
    matches = (expected.get('total') == len(routed)
               and expected.get('z1') == per_plane['z1']['routed']
               and expected.get('z2') == per_plane['z2']['routed'])
    if expected and not matches:
        warnings.append(f'{tag}: routed={len(routed)} '
                        f'(z1={per_plane["z1"]["routed"]}, '
                        f'z2={per_plane["z2"]["routed"]}) differs from the '
                        f'corrected R15-2D reference {expected}')
    entry.update(
        present=True,
        source_routes=_display_path(routes_path),
        source_summary=_display_path(summary_path) if summary_path.exists() else None,
        routed=len(routed), failed=len(failed), total=len(records),
        per_plane=per_plane,
        failure_reasons=dict(Counter(str(record.get('reason') or 'unknown')
                                     for record in failed)),
        per_plane_failure_reasons={
            plane: dict(Counter(str(record.get('reason') or 'unknown')
                                for record in failed
                                if record.get('plane') == plane))
            for plane in PLANES},
        layer_stack=payload.get('layer_stack'),
        provenance=(payload.get('layer_stack') or {}).get('provenance')
        if isinstance(payload.get('layer_stack'), dict) else None,
        statistics=payload.get('statistics') if isinstance(
            payload.get('statistics'), dict) else None,
        two_rows_note=('both port rows belong to L1: z1 row at z=0.0 mm, z2 row at '
                       'z=0.5 mm; the baseline is a flat-L1 layout on two physical '
                       'planes of the SAME logical layer'),
        expected=expected,
        matches_expected=matches,
    )
    return entry


# ---------------------------------------------------------------------------
# independent validation discovery
# ---------------------------------------------------------------------------
def _looks_like_l3d_validation(payload):
    keys = set(payload)
    markers = ('formal_acceptance', 'exploratory_pass', 'validation_passed',
               'passed', 'min_3d_clearance_mm', 'min_3d_distance_mm',
               'min_curvature_radius_mm', 'counts', 'crossings')
    score = sum(1 for marker in markers if marker in keys)
    return score >= 2 and any(marker in keys for marker in
                              ('passed', 'formal_acceptance', 'exploratory_pass',
                               'counts', 'crossings', 'min_3d_clearance_mm'))


def _extract_validation_reports(payload, depth=0):
    reports = []
    if depth > 4 or not isinstance(payload, (dict, list)):
        return reports
    if isinstance(payload, dict):
        if _looks_like_l3d_validation(payload):
            return [payload]
        for value in payload.values():
            reports.extend(_extract_validation_reports(value, depth + 1))
    else:
        for item in payload:
            reports.extend(_extract_validation_reports(item, depth + 1))
    return reports


def _validation_identity(report, path):
    scheme = None
    stack = None
    raw_scheme = report.get('scheme')
    if isinstance(raw_scheme, str) and raw_scheme.strip().upper() in SCHEMES:
        scheme = raw_scheme.strip().upper()
    for key in ('stack', 'stack_name'):
        value = report.get(key)
        if isinstance(value, str) and value:
            stack = value
    if isinstance(report.get('layer_stack'), dict):
        note = report['layer_stack'].get('note')
        if isinstance(note, str):
            match = re.match(r'\s*([A-Za-z0-9_]+):', note)
            if match:
                stack = match.group(1)
    text = (f'{report.get("input") or ""} {report.get("output") or ""} '
            f'{report.get("routes_file") or ""} '
            f'{report.get("layer_stack_source") or ""} {path}')
    if isinstance(report.get('layer_stack'), dict):
        note = report['layer_stack'].get('note')
        if isinstance(note, str):
            text += ' ' + note
    if scheme is None:
        match = re.search(r'scheme\s*[_-]?\s*([AB])\b', text, re.IGNORECASE)
        if match:
            scheme = match.group(1).upper()
    if stack is None:
        match = re.search(r'layers5_([A-Za-z0-9_]+)', text)
        if match:
            stack = match.group(1)
    return scheme, stack


def _validation_view(report, path):
    counts = report.get('counts') if isinstance(report.get('counts'), dict) else None
    stats = report.get('stats') if isinstance(report.get('stats'), dict) else {}
    checks = report.get('checks') if isinstance(report.get('checks'), dict) else {}
    same_plane = checks.get('same_plane') if isinstance(
        checks.get('same_plane'), dict) else {}
    clearance_checks = checks.get('clearance') if isinstance(
        checks.get('clearance'), dict) else {}
    acceptance = checks.get('acceptance') if isinstance(
        checks.get('acceptance'), dict) else {}
    curvature_check = checks.get('curvature') if isinstance(
        checks.get('curvature'), dict) else {}
    crossings = report.get('crossings')
    if isinstance(crossings, dict):
        crossings_view = dict(crossings)
    elif isinstance(crossings, (int, float)):
        crossings_view = dict(total=int(crossings))
    else:
        crossings_view = None
    crossings_total = None
    crossings_by_physical_plane = None
    if isinstance(same_plane, dict) and same_plane:
        crossings_total = _int(same_plane.get('crossings'))
        planes = same_plane.get('planes')
        if isinstance(planes, list):
            by_plane = {}
            for plane_block in planes:
                if not isinstance(plane_block, dict):
                    continue
                key = _pick(plane_block.get('key'),
                            f'z={_fmt_num(plane_block.get("z_mm"), 6)}')
                by_plane[str(key)] = _int(plane_block.get('crossings')) or 0
            if by_plane:
                crossings_by_physical_plane = by_plane
    if crossings_total is None and isinstance(stats, dict):
        crossings_total = _int(stats.get('same_plane_crossings'))
    if crossings_total is None and isinstance(crossings_view, dict):
        crossings_total = _int(crossings_view.get('total'))
        for value in crossings_view.values():
            if crossings_total is None and isinstance(value, int):
                crossings_total = value
                break
    if crossings_by_physical_plane is None and isinstance(crossings_view, dict) \
            and isinstance(crossings_view.get('by_physical_plane'), dict):
        crossings_by_physical_plane = dict(crossings_view['by_physical_plane'])
    if crossings_by_physical_plane is None and isinstance(
            report.get('crossings_by_physical_plane'), dict):
        crossings_by_physical_plane = dict(report['crossings_by_physical_plane'])
    formal = report.get('formal_acceptance')
    if formal is None:
        formal = _pick(report.get('formal_acceptance_granted'),
                       acceptance.get('formal_acceptance'))
    exploratory = _pick(report.get('exploratory_pass'),
                        acceptance.get('exploratory_pass'))
    passed = _pick(report.get('passed'), report.get('validation_passed'),
                   report.get('geometry_pass'))
    min_clearance = _pick(stats.get('min_3d_clearance_mm')
                          if isinstance(stats, dict) else None,
                          report.get('min_3d_clearance_mm'),
                          report.get('min_3d_distance_mm'),
                          clearance_checks.get('min_3d_clearance_mm'))
    min_curvature = _pick(stats.get('min_curvature_radius_mm')
                          if isinstance(stats, dict) else None,
                          report.get('min_curvature_radius_mm'),
                          curvature_check.get('min_curvature_radius_mm'),
                          report.get('min_curvature_mm'))
    violations = report.get('violations')
    violations_count = (len(violations) if isinstance(violations, list)
                        else _int(report.get('violations_count')))
    violations_detail = None
    if isinstance(violations, list) and violations:
        violations_detail = [dict(item) for item in violations[:50]
                             if isinstance(item, dict)]
    return dict(
        present=True,
        source=_display_path(path),
        schema=report.get('schema'),
        scheme=report.get('scheme'),
        stack=_pick(report.get('stack'), report.get('stack_name')),
        passed=passed,
        status=report.get('status'),
        exit_code=_int(report.get('exit_code')),
        geometry_pass=report.get('geometry_pass'),
        geometry_executed=report.get('geometry_executed'),
        allow_exploratory=report.get('allow_exploratory'),
        formal_acceptance=(formal if isinstance(formal, bool) else None),
        exploratory_pass=(exploratory if isinstance(exploratory, bool) else None),
        refusal_reason=_pick(report.get('refusal_reason'),
                             report.get('formal_acceptance_refusal_reason'),
                             acceptance.get('note')),
        counts=dict(counts) if counts else None,
        violations_count=violations_count,
        violation_kinds=(report.get('violation_kinds')
                         if isinstance(report.get('violation_kinds'), dict)
                         else None),
        violations_detail=violations_detail,
        crossings=crossings_view,
        crossings_total=crossings_total,
        crossings_by_physical_plane=crossings_by_physical_plane,
        min_3d_clearance_mm=_num(min_clearance),
        min_curvature_radius_mm=_num(min_curvature),
        min_self_clearance_mm=_num((stats or {}).get('min_self_clearance_mm')),
        multi_transition_routes=_int((stats or {}).get('multi_transition_routes')),
        transition_count=_int((stats or {}).get('transition_count')),
        transition_pairs=(stats or {}).get('transition_pairs'),
        layers_used_histogram=(stats or {}).get('layers_used_histogram'),
        transitions_histogram=(stats or {}).get('transitions_histogram'),
        flat_arcs=_int((stats or {}).get('flat_arcs')),
        flat_arc_radius_values=(stats or {}).get('flat_arc_radius_values'),
        transition_radius_values=(stats or {}).get('transition_radius_values'),
        declared_statistics=(stats or {}).get('declared_statistics'),
        stack_provenance=(report.get('layer_stack') or {}).get('provenance')
        if isinstance(report.get('layer_stack'), dict) else None,
        stack_formal_acceptance_allowed=(report.get('layer_stack') or {}).get(
            'formal_acceptance_allowed')
        if isinstance(report.get('layer_stack'), dict) else None,
        runtime_seconds=_num(report.get('runtime_seconds')),
        errors=report.get('errors') if isinstance(report.get('errors'), list)
        else None,
        warnings=report.get('warnings') if isinstance(report.get('warnings'), list)
        else None,
        raw_keys=sorted(report.keys())[:60],
    )


def _discover_validation(root, warnings):
    directories = [Path(root) / 'validation', Path(root) / 'l3d' / 'validation',
                   Path(root) / 'formal_validation']
    reports = []
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob('*.json')):
            if not path.is_file():
                continue
            payload = _load_json(path, warnings, f'validation file {path.name}')
            if payload is None:
                continue
            for report in _extract_validation_reports(payload):
                reports.append((path, report))
    if not reports:
        warnings.append('L3D validation reports not found under '
                        f'{_display_path(Path(root) / "validation")} '
                        '(validation block null)')
    result = {}
    for path, report in reports:
        scheme, stack = _validation_identity(report, path)
        if scheme not in SCHEMES:
            continue
        stack = stack or PRIMARY_STACK
        key = f'{scheme}/{stack}'
        previous = result.get(key)
        score = (4 if report.get('scheme') == scheme else 0)
        score += 2 if report.get('stack') == stack else 0
        score += 1 if 'layers5_' in path.name else 0
        if previous is None or score > previous[0]:
            result[key] = (score, _validation_view(report, path))
    return {key: value[1] for key, value in result.items()}


# ---------------------------------------------------------------------------
# loss parameters
# ---------------------------------------------------------------------------
def _loss_parameters(runs):
    process = None
    for entry in runs.values():
        if entry.get('present') and isinstance(entry.get('process'), dict):
            process = entry['process']
            break
    radius = None
    propagation = None
    if isinstance(process, dict):
        radius = _num(process.get('radius_mm'))
        propagation = _num(process.get('propagation_loss_db_per_cm'))
    return dict(
        schema=SCHEMA_LOSS,
        generated_utc=_now_utc(),
        round='R9_corrected_L1_L5',
        radius_mm=_pick(radius, EXPECTED_RADIUS_MM),
        guidance=('No loss coefficients are invented in this round. Only the '
                  'propagation-loss experiment convention is listed as a known '
                  'parameter; bend / crossing / interlayer losses are unknown and '
                  'uncalibrated, and no total-loss conclusion is produced.'),
        parameters=dict(
            propagation_loss=dict(
                parameter='propagation_loss',
                value_db_per_cm=_pick(propagation, PROPAGATION_LOSS_DB_PER_CM),
                status='experimental_convention_not_measured',
                measured=False,
                source='fslw.config experiment convention (not a measured value)',
                note='length-only experiment convention; not a measured glass value'),
            bend_loss=dict(parameter='bend_loss', value_db=None,
                           status='unknown_uncalibrated', measured=False,
                           source='not available in this round',
                           note=('no calibrated glass bend-loss function; R=15 mm is '
                                 'a geometry constraint only')),
            crossing_loss=dict(parameter='crossing_loss', value_db=None,
                               status='unknown_uncalibrated', measured=False,
                               source='not available in this round',
                               note=('single-layer crossing optical feasibility not '
                                     'confirmed; crossing counts are geometric only')),
            interlayer_loss=dict(parameter='interlayer_loss', value_db=None,
                                 status='unknown_uncalibrated', measured=False,
                                 source='not available in this round',
                                 note=('multi-layer transitions and interlayer '
                                       'propagation effects are not calibrated')),
        ),
        total_loss_conclusion=dict(
            produced=False,
            reason=('bend, crossing and interlayer coefficients are all '
                    'unknown_uncalibrated; a total-loss number would require '
                    'invented coefficients, so none is reported')),
        layer_heights_unconfirmed=dict(
            status=PROVENANCE_UNCONFIRMED,
            note=('L2-L5 heights are exploratory simulation inputs, not confirmed '
                  'process values; this also blocks formal process acceptance')),
        geometric_inputs_only=dict(
            note=('lengths / arc counts / transition counts / crossing counts are '
                  'reported as geometric inputs only and are deliberately NOT '
                  'converted into total loss'),
            runs={key: dict(routed=entry.get('routed'),
                            total_3d_length_mm=(entry.get('length') or {}).get(
                                'three_d_total_mm'),
                            transitions=entry.get('transitions'),
                            crossings=(entry.get('validation') or {}).get(
                                'crossings'))
                  for key, entry in runs.items() if entry.get('present')},
        ),
    )


# ---------------------------------------------------------------------------
# comparison
# ---------------------------------------------------------------------------
def _comparison(runs, baseline, stacks_info, validation):
    primary_rows = []
    for scheme in SCHEMES:
        entry = runs.get(f'{scheme}/{PRIMARY_STACK}') or {}
        base = baseline.get(scheme) or {}
        r15_2d = R15_2D_BASELINE.get(scheme, {})
        old = OLD_5L_HISTORICAL.get(scheme)
        routed = entry.get('routed')
        primary_rows.append(dict(
            scheme=scheme,
            stack=PRIMARY_STACK,
            corrected_routed=routed,
            corrected_added=(entry.get('added') if entry.get('present') else None),
            corrected_lifted=entry.get('lifted'),
            corrected_transitions=entry.get('transitions'),
            corrected_total_length_mm=(entry.get('length') or {}).get(
                'three_d_total_mm'),
            r15_2d_baseline=r15_2d.get('total'),
            delta_vs_r15_2d=((routed - r15_2d['total'])
                             if routed is not None and r15_2d.get('total') is not None
                             else None),
            baseline_payload_routed=base.get('routed'),
            historical_old_5l=old,
            delta_vs_old_5l=((routed - old)
                             if routed is not None and old is not None else None),
            old_5l_comparable=False,
            exploratory_validation=(validation.get(f'{scheme}/{PRIMARY_STACK}')
                                    or {}).get('exploratory_pass'),
            formal_acceptance_granted=False,
        ))
    sensitivity_rows = []
    for stack_name in [PRIMARY_STACK, *SENSITIVITY_STACKS]:
        info = stacks_info.get(stack_name) or {}
        row = dict(
            stack=stack_name,
            heights_mm=info.get('routing_heights_mm'),
            provenance=info.get('provenance'),
            stack_valid=info.get('valid'),
            min_plane_gap_mm=info.get('min_plane_gap_mm'),
            formal_acceptance_allowed=info.get('formal_acceptance_allowed'),
            present_schemes={},
        )
        for scheme in SCHEMES:
            entry = runs.get(f'{scheme}/{stack_name}') or {}
            row['present_schemes'][scheme] = dict(
                present=bool(entry.get('present')),
                routed=entry.get('routed'),
                added=entry.get('added'),
                lifted=entry.get('lifted'),
                transitions=entry.get('transitions'),
                validation=(validation.get(f'{scheme}/{stack_name}') or {}).get(
                    'exploratory_pass'),
            )
        sensitivity_rows.append(row)
    return dict(
        primary=[f'{PRIMARY_STACK} corrected L1-L5'],
        r15_2d_baseline=R15_2D_BASELINE,
        historical_old_5l=OLD_5L_HISTORICAL,
        old_model_note=OLD_5L_HISTORICAL['note'],
        primary_rows=primary_rows,
        sensitivity_rows=sensitivity_rows,
        formal_acceptance=dict(
            granted=False,
            reason=('L2-L5 physical heights are unconfirmed_simulation simulation '
                    'inputs; formal process acceptance is refused for every stack'),
        ),
    )


# ---------------------------------------------------------------------------
# markdown renderers
# ---------------------------------------------------------------------------
def _render_statistics_md(statistics):
    runs = statistics['runs']
    baseline = statistics['baseline']
    comparison = statistics['comparison']
    losses = statistics['loss_parameters']
    lines = [
        '# 修正 L1–L5 物理模型统计报告（R9，自动生成）',
        '',
        f'- 生成时间（UTC）：{statistics["generated_utc"]}',
        f'- 数据根目录：`{statistics["root"]}`',
        '- 生成脚本：`four_side_1024/l3d/stats_l3d.py`（只读输入，仅写 summary/）',
        '',
        '## 0. 模型修正与正式验收状态',
        '',
        '- **正确模型**：L1 是接口布线层，同时包含两个端口行：z1 行物理高度 '
        '**0.0 mm**、z2 行 **0.5 mm**（两者 logical layer_id 均 = 1）；'
        'L2–L5 是四个额外布线层。多段 transition 合法。',
        '- **旧模型（错误）**：`z1 = layer 0 / z2 = layer 4`，把 0.5 mm 端口行高差当作'
        '整个五层堆栈；旧 5L 结果 A=985 / B=723 **不可比**，仅作历史记录。',
        '- **正式验收状态**：**NOT GRANTED**。L2–L5 物理高度目前为 '
        '`unconfirmed_simulation`（仿真输入），在导师确认前不能给出正式工艺验收结论；'
        '几何检查结果只能标为 exploratory。',
        '',
        '## 1. 运行总览（primary = medium_050）',
        '',
        '| 方案 | 层堆栈 | 阶段 | 布通/总数 | 失败 | flat-L1 基线 | 新增 | 抬升 | '
        'transitions | 3D 总长 mm | 几何验收 | 正式验收 |',
        '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|',
    ]
    for scheme in SCHEMES:
        for stack_name in [PRIMARY_STACK, *SENSITIVITY_STACKS]:
            entry = runs.get(f'{scheme}/{stack_name}') or {}
            if not entry.get('present'):
                if stack_name == PRIMARY_STACK:
                    lines.append(f'| {scheme} | {stack_name} | {DASH} | '
                                 + ' | '.join([DASH] * 9) + ' |')
                continue
            validation = entry.get('validation') or {}
            lines.append(
                f'| {scheme} | {stack_name} | {entry.get("stage") or DASH} | '
                f'{_fmt_int(entry.get("routed"))}/{_fmt_int(entry.get("total"))} | '
                f'{_fmt_int(entry.get("failed"))} | '
                f'{_fmt_int(entry.get("baseline_routed"))} | '
                f'{_fmt_int(entry.get("added"))} | {_fmt_int(entry.get("lifted"))} | '
                f'{_fmt_int(entry.get("transitions"))} | '
                f'{_fmt_num((entry.get("length") or {}).get("three_d_total_mm"), 3)} | '
                f'{_pass_fail(validation.get("exploratory_pass"))} | '
                f'{_pass_fail(validation.get("formal_acceptance"))} |')
    lines.append('')
    lines.extend([
        '### 1.1 flat-L1 基线（修正模型）',
        '',
        '| 方案 | 布通 | 失败 | z1 行布通/失败 | z2 行布通/失败 | 与 R15-2D 参考一致 |',
        '|---|---:|---:|---|---|---|',
    ])
    for scheme in SCHEMES:
        base = baseline.get(scheme) or {}
        planes = base.get('per_plane') or {}
        lines.append(
            f'| {scheme} | {_fmt_int(base.get("routed"))} | '
            f'{_fmt_int(base.get("failed"))} | '
            f'{_fmt_int((planes.get("z1") or {}).get("routed"))}/'
            f'{_fmt_int((planes.get("z1") or {}).get("failed"))} | '
            f'{_fmt_int((planes.get("z2") or {}).get("routed"))}/'
            f'{_fmt_int((planes.get("z2") or {}).get("failed"))} | '
            f'{_yes_no(base.get("matches_expected"))} |')
    lines.append('')
    lines.append('> 两个端口行都属于 L1：z1 row z=0.0 mm、z2 row z=0.5 mm，是**同一'
                 '逻辑层 L1 的两个物理平面**；基线不继承任何旧 2.5D 结果。')
    lines.append('')

    lines.extend([
        '## 2. 物理平面统计（按真实 z 分组，不按 logical layer id）',
        '',
        '| 方案/栈 | 物理平面 | 真实 z mm | logical layer_id | 触及路由数 | '
        'flat 段数 | flat 总长 mm | 备注 |',
        '|---|---|---:|---|---:|---:|---:|---|',
    ])
    rendered_any_plane = False
    for scheme in SCHEMES:
        for stack_name in [PRIMARY_STACK, *SENSITIVITY_STACKS]:
            entry = runs.get(f'{scheme}/{stack_name}') or {}
            planes = entry.get('physical_planes') or {}
            for plane in planes.values():
                rendered_any_plane = True
                note = ''
                if plane.get('layer_type') == 'interface':
                    note = (f'L1 {plane.get("row")} row — L1 has TWO physical planes, '
                            f'both logical layer_id=1')
                lines.append(
                    f'| {scheme}/{stack_name} | {plane.get("label")} | '
                    f'{_fmt_num(plane.get("z_mm"), 6)} | '
                    f'{", ".join(str(value) for value in plane.get("logical_layer_ids") or []) or DASH} | '
                    f'{_fmt_int(plane.get("routes_touching"))} | '
                    f'{_fmt_int(plane.get("flat_parts"))} | '
                    f'{_fmt_num(plane.get("flat_length_mm"), 3)} | {note or DASH} |')
    if not rendered_any_plane:
        lines.append('| ' + ' | '.join([DASH] * 8) + ' |')
    lines.append('')
    for scheme in SCHEMES:
        entry = runs.get(f'{scheme}/{PRIMARY_STACK}') or {}
        check = entry.get('l1_two_rows_check') or {}
        if check:
            lines.append(
                f'- **L1 双物理平面检查（{scheme}）**：L1 在物理平面表中出现 '
                f'{_fmt_int(check.get("physical_plane_count"))} 次，'
                f'z = {check.get("z_values_mm")} mm，行 = {check.get("rows")}，'
                f'两者 logical layer_id 均为 {check.get("logical_layer_id")}'
                f'（同一逻辑接口层的两个真实高度）。')
    lines.append('')

    lines.extend([
        '## 3. 逻辑层与层序列统计',
        '',
        '| 方案/栈 | 逻辑层 | 物理 z mm / 行 | 触及路由数 | flat 段数 | '
        'flat 总长 mm | transition 端点 |',
        '|---|---|---|---:|---:|---:|---:|',
    ])
    rendered_any_layer = False
    for scheme in SCHEMES:
        entry = runs.get(f'{scheme}/{PRIMARY_STACK}') or {}
        layers = entry.get('logical_layers') or {}
        for layer_id, layer in layers.items():
            rendered_any_layer = True
            if layer.get('layer_type') == 'interface':
                z_text = 'rows z1=0.0 / z2=0.5'
            else:
                z_text = _fmt_num(layer.get('physical_z_mm'), 6)
            lines.append(
                f'| {scheme}/{PRIMARY_STACK} | L{layer_id} | {z_text} | '
                f'{_fmt_int(layer.get("routes_touching"))} | '
                f'{_fmt_int(layer.get("flat_parts"))} | '
                f'{_fmt_num(layer.get("flat_length_mm"), 3)} | '
                f'{_fmt_int(layer.get("transition_endpoints"))} |')
    if not rendered_any_layer:
        lines.append('| ' + ' | '.join([DASH] * 7) + ' |')
    lines.append('')
    lines.extend([
        '### 3.1 直方图（primary）',
        '',
        '| 方案 | layers-used 直方图 | layer sequence 直方图 | transition 数直方图 |',
        '|---|---|---|---|',
    ])
    for scheme in SCHEMES:
        entry = runs.get(f'{scheme}/{PRIMARY_STACK}') or {}
        if not entry.get('present'):
            lines.append(f'| {scheme} | {DASH} | {DASH} | {DASH} |')
            continue
        lines.append(
            f'| {scheme} | {entry.get("layers_used_histogram") or DASH} | '
            f'{_short_histogram(entry.get("layer_sequence_histogram"))} | '
            f'{entry.get("transitions_grouped") or DASH} |')
    lines.append('')
    lines.extend([
        '### 3.2 transition 层对 / dz 直方图（primary）',
        '',
        '| 方案 | from→to | dz mm | 次数 | θ 总计° | footprint 总计 mm | '
        '弧长总计 mm | 半径 mm |',
        '|---|---|---:|---:|---:|---:|---:|---|',
    ])
    rendered_pair = False
    for scheme in SCHEMES:
        entry = runs.get(f'{scheme}/{PRIMARY_STACK}') or {}
        for pair in entry.get('transition_pairs') or []:
            rendered_pair = True
            lines.append(
                f'| {scheme} | L{pair.get("from_layer")}→L{pair.get("to_layer")} | '
                f'{_fmt_num(pair.get("dz_signed_mm"), 6)} | '
                f'{_fmt_int(pair.get("count"))} | '
                f'{_fmt_num(pair.get("theta_deg_total"), 3)} | '
                f'{_fmt_num(pair.get("footprint_mm_total"), 3)} | '
                f'{_fmt_num(pair.get("length_mm_total"), 3)} | '
                f'{pair.get("radius_values_mm") or DASH} |')
    if not rendered_pair:
        lines.append('| ' + ' | '.join([DASH] * 8) + ' |')
    lines.append('')

    lines.extend([
        '## 4. 长度与 z_span',
        '',
        '| 方案/栈 | XY 总长 mm | 3D 总长 mm | flat 总长 mm | transition 总长 mm | '
        '平均 3D 长 mm | z_span 分布 |',
        '|---|---:|---:|---:|---:|---:|---|',
    ])
    for scheme in SCHEMES:
        for stack_name in [PRIMARY_STACK, *SENSITIVITY_STACKS]:
            entry = runs.get(f'{scheme}/{stack_name}') or {}
            if not entry.get('present'):
                continue
            length = entry.get('length') or {}
            lines.append(
                f'| {scheme}/{stack_name} | {_fmt_num(length.get("xy_total_mm"), 3)} | '
                f'{_fmt_num(length.get("three_d_total_mm"), 3)} | '
                f'{_fmt_num(length.get("flat_total_mm"), 3)} | '
                f'{_fmt_num(length.get("transition_total_mm"), 3)} | '
                f'{_fmt_num(length.get("mean_3d_length_mm"), 3)} | '
                f'{entry.get("z_span_distribution") or DASH} |')
    lines.append('')
    for scheme in SCHEMES:
        for stack_name in [PRIMARY_STACK, *SENSITIVITY_STACKS]:
            entry = runs.get(f'{scheme}/{stack_name}') or {}
            flat = entry.get('flat_geometry') or {}
            if not flat:
                continue
            lines.append(
                f'- flat 2D 几何（{scheme}/{stack_name}）：弧数 '
                f'{_fmt_int(flat.get("arc_count"))}，半径分布 '
                f'{flat.get("radius_distribution") or DASH}，全部 R15='
                f'{_yes_no(flat.get("all_flat_arcs_r15"))}。')
    lines.append('')

    lines.extend([
        '## 5. 独立 3D 验收摘要（exploratory only）',
        '',
        '| 方案/栈 | 报告 | 几何通过 | exploratory | formal acceptance | '
        '最小 3D 间距 mm | 最小曲率半径 mm | 违规计数 |',
        '|---|---|---|---|---|---:|---:|---|',
    ])
    for scheme in SCHEMES:
        for stack_name in [PRIMARY_STACK, *SENSITIVITY_STACKS]:
            entry = runs.get(f'{scheme}/{stack_name}') or {}
            validation = entry.get('validation') or {}
            if not entry.get('present') and not validation.get('present'):
                continue
            counts = validation.get('counts') or {}
            counts_nonzero = {key: value for key, value in counts.items()
                              if value not in (0, None)}
            lines.append(
                f'| {scheme}/{stack_name} | '
                f'{_short_path(validation.get("source"))} | '
                f'{_pass_fail(validation.get("passed"))} | '
                f'{_pass_fail(validation.get("exploratory_pass"))} | '
                f'{_pass_fail(validation.get("formal_acceptance"))} | '
                f'{_fmt_num(validation.get("min_3d_clearance_mm"), 6)} | '
                f'{_fmt_num(validation.get("min_curvature_radius_mm"), 6)} | '
                f'{counts_nonzero if counts_nonzero else "全部 0"} |')
    lines.append('')
    if comparison.get('formal_acceptance'):
        lines.append(f'> **正式验收：NOT GRANTED。** '
                     f'{comparison["formal_acceptance"]["reason"]}')
        lines.append('')

    lines.extend([
        '## 6. 失败分析',
        '',
        '| 方案/栈 | 记录失败 | 无 2D 候选(记录) | 3D 无法放置(记录) | '
        'transition 放置不可行(rejected) | router: 无2D候选 / 3D阻塞 / 未尝试 | '
        '其他记录原因 | 分平面 |',
        '|---|---:|---:|---:|---:|---|---|---|',
    ])
    for scheme in SCHEMES:
        for stack_name in [PRIMARY_STACK, *SENSITIVITY_STACKS]:
            entry = runs.get(f'{scheme}/{stack_name}') or {}
            if not entry.get('present'):
                continue
            reasons = entry.get('failure_reasons') or {}
            analysis = entry.get('failure_analysis') or {}
            router = analysis.get('from_run_summary') or {}
            other = {key: value for key, value in reasons.items()
                     if key not in ('no_2d_candidate', 'unplaceable_in_3d')}
            lines.append(
                f'| {scheme}/{stack_name} | {_fmt_int(entry.get("failed"))} | '
                f'{_fmt_int(reasons.get("no_2d_candidate"))} | '
                f'{_fmt_int(reasons.get("unplaceable_in_3d"))} | '
                f'{_fmt_int(analysis.get("transition_placement_infeasible"))} | '
                f'{_fmt_int(router.get("no_candidate"))} / '
                f'{_fmt_int(router.get("failed_unplaceable"))} / '
                f'{_fmt_int(router.get("unattempted"))} | '
                f'{other or DASH} | {entry.get("failure_by_plane") or DASH} |')
    lines.append('')
    lines.append('> 口径：记录中的 `unplaceable_in_3d` 包含“尚未尝试”的路线；router 统计'
                 '区分 attempted / unattempted，并记录 '
                 '`transition_placement_infeasible`（S 曲线无法放到 2D 路径上）。')
    lines.append('')

    lines.extend([
        '## 7. 损耗参数口径（不输出总损耗结论）',
        '',
        '| 参数 | 值 | 状态 | 已标定 | 说明 |',
        '|---|---|---|---|---|',
    ])
    for parameter in losses['parameters'].values():
        value = parameter.get('value_db_per_cm')
        value_text = f'{value} dB/cm' if value is not None else DASH
        lines.append(
            f'| {parameter.get("parameter")} | {value_text} | '
            f'{parameter.get("status")} | {parameter.get("measured")} | '
            f'{parameter.get("note")} |')
    lines.append('')
    lines.append('> **本轮不输出总损耗结论。** 传播损耗 0.05 dB/cm 为实验约定'
                 '（非实测）；弯曲 / 交叉 / 层间损耗均 `unknown_uncalibrated`。')
    lines.append('')

    if statistics.get('warnings'):
        lines.extend(['## 8. 警告', ''])
        for warning in statistics['warnings'][:30]:
            lines.append(f'- {warning}')
        if len(statistics['warnings']) > 30:
            lines.append(f'- ... 其余 {len(statistics["warnings"]) - 30} 条')
        lines.append('')
    return '\n'.join(lines) + '\n'


def _short_histogram(histogram):
    if not histogram:
        return DASH
    items = list(histogram.items())
    if len(items) <= 6:
        return '; '.join(f'{key}:{value}' for key, value in items)
    return '; '.join(f'{key}:{value}' for key, value in items[:6]) + f'; ...({len(items)} keys)'


def _short_path(path):
    if not path:
        return DASH
    return f'`{path}`'


def _render_comparison_md(statistics):
    comparison = statistics['comparison']
    losses = statistics['loss_parameters']
    lines = [
        '# 修正 L1–L5 模型 vs 历史 / R15-2D 对照表（自动生成）',
        '',
        f'- 生成时间（UTC）：{statistics["generated_utc"]}',
        '',
        '## 0. 重要警告：旧 5L 数字不可比',
        '',
        f'- {comparison["old_model_note"]}。',
        '- 旧数字只出现在本对照表的“历史”列，**不进入**任何 corrected 统计。',
        '- 修正模型：L1 接口层同时包含 z1（0.0 mm）与 z2（0.5 mm）两个端口行；'
        'L2–L5 额外布线层高度未确认（`unconfirmed_simulation`）→ 正式验收 '
        '**NOT GRANTED**。',
        '',
        '## 1. 主对照（primary stack = medium_050）',
        '',
        '| 方案 | corrected L1-L5 布通 | 相对 flat-L1 基线新增 | 抬升 | '
        'transitions | corrected 3D 总长 mm | R15-2D 基线 | Δ vs R15-2D | '
        '历史旧 5L（不可比） | Δ vs 旧（不可比） |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for row in comparison['primary_rows']:
        lines.append(
            f'| {row["scheme"]} | '
            f'{_fmt_int(row.get("corrected_routed"))} | '
            f'{_fmt_delta(row.get("corrected_added"))} | '
            f'{_fmt_int(row.get("corrected_lifted"))} | '
            f'{_fmt_int(row.get("corrected_transitions"))} | '
            f'{_fmt_num(row.get("corrected_total_length_mm"), 3)} | '
            f'{_fmt_int(row.get("r15_2d_baseline"))} | '
            f'{_fmt_delta(row.get("delta_vs_r15_2d"))} | '
            f'{_fmt_int(row.get("historical_old_5l"))} | '
            f'{_fmt_delta(row.get("delta_vs_old_5l"))}（不可比） |')
    lines.append('')
    lines.extend([
        '## 2. 层堆栈参数敏感性（exploratory）',
        '',
        '| 堆栈 | L2..L5 高度 mm | provenance | 堆栈有效 | 最小平面间距 mm | '
        'A 布通/新增/抬升/transitions | B 布通/新增/抬升/transitions | '
        'A 几何验收 | B 几何验收 |',
        '|---|---|---|---|---:|---|---|---|---|',
    ])
    for row in comparison['sensitivity_rows']:
        schemes = row.get('present_schemes') or {}
        a = schemes.get('A') or {}
        b = schemes.get('B') or {}
        lines.append(
            f'| {row["stack"]} | {row.get("heights_mm") or DASH} | '
            f'{row.get("provenance") or DASH} | {_yes_no(row.get("stack_valid"))} | '
            f'{_fmt_num(row.get("min_plane_gap_mm"), 6)} | '
            f'{_format_run_cell(a)} | {_format_run_cell(b)} | '
            f'{_pass_fail(a.get("validation"))} | {_pass_fail(b.get("validation"))} |')
    lines.append('')
    lines.extend([
        '## 3. flat-L1 基线（修正模型）',
        '',
        '| 方案 | flat-L1 布通 | z1 行 | z2 行 | 失败 | 与 R15-2D 参考一致 |',
        '|---|---:|---:|---:|---:|---|',
    ])
    for scheme in SCHEMES:
        base = statistics['baseline'].get(scheme) or {}
        planes = base.get('per_plane') or {}
        lines.append(
            f'| {scheme} | {_fmt_int(base.get("routed"))} | '
            f'{_fmt_int((planes.get("z1") or {}).get("routed"))} | '
            f'{_fmt_int((planes.get("z2") or {}).get("routed"))} | '
            f'{_fmt_int(base.get("failed"))} | '
            f'{_yes_no(base.get("matches_expected"))} |')
    lines.append('')
    lines.extend([
        '## 4. 正式验收状态',
        '',
        f'- granted: **{_yes_no(comparison["formal_acceptance"]["granted"])}**',
        f'- 原因：{comparison["formal_acceptance"]["reason"]}',
        '',
        '## 5. 损耗口径',
        '',
        f'- {losses["total_loss_conclusion"]["reason"]}',
        '- 唯一已知参数为传播损耗实验约定 0.05 dB/cm（非实测）；弯曲/交叉/层间均为 '
        '`unknown_uncalibrated`。',
        '',
    ])
    return '\n'.join(lines) + '\n'


def _format_run_cell(entry):
    if not entry or not entry.get('present'):
        return DASH
    return (f'{_fmt_int(entry.get("routed"))}/'
            f'{_fmt_delta(entry.get("added"))}/'
            f'{_fmt_int(entry.get("lifted"))}/'
            f'{_fmt_int(entry.get("transitions"))}')


# ---------------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------------
CSV_PER_ROUTE_FIELDS = [
    'stage', 'scheme', 'stack', 'route_id', 'plane', 'status', 'reason',
    'baseline_2d', 'mode', 'lifted', 'n_transitions', 'layer_sequence',
    'layer_z_sequence', 'layers_used', 'xy_length_mm', 'length_mm',
    'flat_length_mm', 'transition_length_mm', 'z_span_mm', 'start_z_mm',
    'end_z_mm', 'source_row', 'target_row', 'flat_parts_count',
    'transition_parts_count', 'flat_radius_distribution', 'transition_radii',
]
CSV_LAYER_USAGE_FIELDS = [
    'scope', 'category', 'key', 'layer_type', 'logical_layer_ids', 'z_mm',
    'row', 'routes_touching', 'flat_parts', 'flat_length_mm',
    'transition_endpoints', 'note',
]
CSV_TRANSITION_PAIR_FIELDS = [
    'scheme', 'stack', 'from_layer', 'to_layer', 'dz_signed_mm', 'dz_abs_mm',
    'count', 'theta_deg_total', 'footprint_mm_total', 'length_mm_total',
    'radius_values_mm',
]


def _csv_scalar(value):
    if isinstance(value, (list, tuple)):
        return ';'.join(str(item) for item in value)
    if isinstance(value, dict):
        return ';'.join(f'{key}={item}' for key, item in sorted(value.items()))
    return value


def _write_csv(path, fieldnames, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames,
                                extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_scalar(row.get(field))
                             for field in fieldnames})
    return path


# ---------------------------------------------------------------------------
# stack discovery
# ---------------------------------------------------------------------------
def _discover_stacks(root, runs, warnings):
    stacks_info = {}
    stack_dir = Path(root) / 'layer_stacks'
    if stack_dir.is_dir():
        for path in sorted(stack_dir.glob('*.json')):
            payload = _load_json(path, warnings, f'layer_stacks/{path.name}')
            stack = _stack_from_payload(payload, path.stem)
            if stack:
                validation = _stack_validation(stack)
                stack['valid'] = validation['valid']
                stack['validation_errors'] = validation['errors']
                stack['min_plane_gap_mm'] = validation['min_plane_gap_mm']
                stack['physical_planes'] = validation['physical_planes']
                stacks_info[path.stem] = stack
    for key, entry in runs.items():
        stack_name = entry.get('stack')
        if not stack_name or stack_name in stacks_info:
            continue
        stack = _normalise_stack_from_run(entry, stack_name, warnings)
        if stack:
            stacks_info[stack_name] = stack
    for stack_name in [PRIMARY_STACK, *SENSITIVITY_STACKS]:
        if stack_name not in stacks_info:
            preset = _preset_stack(stack_name)
            if preset is not None:
                validation = _stack_validation(preset)
                preset['valid'] = validation['valid']
                preset['validation_errors'] = validation['errors']
                preset['min_plane_gap_mm'] = validation['min_plane_gap_mm']
                preset['physical_planes'] = validation['physical_planes']
                stacks_info[stack_name] = preset
                warnings.append(f'layer stack {stack_name}: definition file '
                                f'missing; documented preset used as fallback')
    return stacks_info


def _normalise_stack_from_run(entry, stack_name, warnings):
    payload_stack = entry.get('layer_stack')
    if not isinstance(payload_stack, dict):
        return None
    stack = _stack_from_payload(payload_stack, stack_name)
    if stack is None or not stack.get('routing_heights_mm'):
        return None
    validation = _stack_validation(stack)
    stack['valid'] = validation['valid']
    stack['validation_errors'] = validation['errors']
    stack['min_plane_gap_mm'] = validation['min_plane_gap_mm']
    stack['physical_planes'] = validation['physical_planes']
    return stack


# ---------------------------------------------------------------------------
# analysis entry point
# ---------------------------------------------------------------------------
def collect(root, log=print):
    root = Path(root)
    warnings = []
    runs = {}
    run_keys = []
    for scheme in SCHEMES:
        scheme_dir = Path(root) / 'l3d' / f'scheme{scheme}'
        stack_names = []
        if scheme_dir.is_dir():
            for child in sorted(scheme_dir.iterdir()):
                if child.is_dir() and child.name.startswith('layers5_'):
                    stack_names.append(child.name[len('layers5_'):])
        for stack_name in [PRIMARY_STACK, *SENSITIVITY_STACKS]:
            if stack_name in stack_names or not stack_names:
                if stack_name not in stack_names:
                    stack_names.append(stack_name)
        if not stack_names:
            stack_names = [PRIMARY_STACK]
        run_dirs = {}
        for stack_name in stack_names:
            run_dir = _find_run_dir(root, scheme, stack_name)
            run_dirs[stack_name] = run_dir
        if not any((run_dirs[stack_name] / 'routes_l3d.json').exists()
                   for stack_name in stack_names):
            warnings.append(f'l3d/scheme{scheme}: no routes_l3d.json yet for any '
                            f'stack ({", ".join(stack_names)})')
        run_keys.extend(f'{scheme}/{stack_name}' for stack_name in stack_names)
    validations = _discover_validation(root, warnings)
    for scheme in SCHEMES:
        scheme_dir = Path(root) / 'l3d' / f'scheme{scheme}'
        stack_names = []
        if scheme_dir.is_dir():
            for child in sorted(scheme_dir.iterdir()):
                if child.is_dir() and child.name.startswith('layers5_'):
                    stack_names.append(child.name[len('layers5_'):])
        for stack_name in [PRIMARY_STACK, *SENSITIVITY_STACKS]:
            if stack_name not in stack_names:
                stack_names.append(stack_name)
        for stack_name in stack_names:
            key = f'{scheme}/{stack_name}'
            validation = validations.get(key)
            stage = 'full'
            if validation is None:
                warnings.append(f'{key}: independent L3D validation report not '
                                f'found (validation block null)')
            entry = _analyse_run(root, scheme, stack_name, stage, validation,
                                 warnings)
            runs[key] = entry
            warnings.extend(entry.get('warnings') or [])
    baseline = {}
    for scheme in SCHEMES:
        baseline[scheme] = _analyse_baseline(root, scheme, warnings)
    stacks_info = _discover_stacks(root, runs, warnings)
    losses = _loss_parameters(runs)
    comparison = _comparison(runs, baseline, stacks_info, validations)
    per_route_rows = []
    for key in run_keys:
        entry = runs.get(key) or {}
        for row in entry.get('per_route_rows') or []:
            per_route_rows.append(row)
    layer_usage_rows = _layer_usage_rows(runs)
    transition_pair_rows = _transition_pair_rows(runs)
    statistics = dict(
        schema=SCHEMA_STATISTICS,
        generated_utc=_now_utc(),
        generator='four_side_1024.l3d.stats_l3d',
        python_version=sys.version.split()[0],
        root=_display_path(root),
        root_abs=str(root),
        round='R9_corrected_L1_L5',
        model_correction=dict(
            old_model=('WRONG: z1 plane = layer index 0 (z=0), z2 plane = layer index '
                       '4 (z=0.5); old 5L results A=985/B=723 are historical only '
                       'and NOT comparable'),
            new_model=('L1 is the interface routing layer and contains BOTH port rows '
                       '(z1 row = 0.0 mm, z2 row = 0.5 mm, both logical layer_id=1); '
                       'L2-L5 are four additional routing layers with unconfirmed '
                       'configurable heights; multi-transition routes are allowed'),
            formal_acceptance=dict(
                granted=False,
                reason=('L2-L5 physical heights are unconfirmed_simulation; formal '
                        'process acceptance is refused while they are unconfirmed')),
        ),
        references=dict(
            r15_2d_corrected_l1_baseline=R15_2D_BASELINE,
            historical_old_5l=OLD_5L_HISTORICAL,
        ),
        layer_stacks={name: dict(
            name=name,
            provenance=stack.get('provenance'),
            formal_acceptance_allowed=stack.get('formal_acceptance_allowed'),
            routing_heights_mm=stack.get('routing_heights_mm'),
            interface_rows=stack.get('interface_rows'),
            valid=stack.get('valid'),
            validation_errors=stack.get('validation_errors'),
            min_plane_gap_mm=stack.get('min_plane_gap_mm'),
            physical_planes=stack.get('physical_planes'),
            note=stack.get('note'),
            source=stack.get('source'),
        ) for name, stack in stacks_info.items()},
        baseline=baseline,
        runs={key: {field: value for field, value in entry.items()
                    if field != 'per_route_rows'}
              for key, entry in runs.items()},
        validation={key: value for key, value in validations.items()},
        comparison=comparison,
        loss_parameters=losses,
        per_route_counts=dict(per_route_rows=len(per_route_rows),
                              layer_usage_rows=len(layer_usage_rows),
                              transition_pair_rows=len(transition_pair_rows)),
        failure_summary=_failure_summary(runs),
        warnings=warnings,
    )
    return dict(statistics=statistics, comparison=comparison, losses=losses,
                per_route_rows=per_route_rows,
                layer_usage_rows=layer_usage_rows,
                transition_pair_rows=transition_pair_rows)


def _layer_usage_rows(runs):
    rows = []
    for key, entry in runs.items():
        if not entry.get('present'):
            continue
        scheme = entry.get('scheme')
        stack = entry.get('stack')
        for plane in (entry.get('physical_planes') or {}).values():
            rows.append(dict(
                scope=f'{scheme}/{stack}', category='physical_plane',
                key=plane.get('key'), layer_type=plane.get('layer_type'),
                logical_layer_ids=plane.get('logical_layer_ids'),
                z_mm=plane.get('z_mm'), row=plane.get('row'),
                routes_touching=plane.get('routes_touching'),
                flat_parts=plane.get('flat_parts'),
                flat_length_mm=plane.get('flat_length_mm'),
                transition_endpoints=None,
                note=('L1 interface row plane (same logical layer_id=1 as the other '
                      'L1 row)' if plane.get('layer_type') == 'interface' else None)))
        for layer_id, layer in (entry.get('logical_layers') or {}).items():
            rows.append(dict(
                scope=f'{scheme}/{stack}', category='logical_layer',
                key=f'L{layer_id}', layer_type=layer.get('layer_type'),
                logical_layer_ids=[int(layer_id)],
                z_mm=layer.get('physical_z_mm'),
                row=','.join(sorted(layer.get('interface_rows') or {})) or None,
                routes_touching=layer.get('routes_touching'),
                flat_parts=layer.get('flat_parts'),
                flat_length_mm=layer.get('flat_length_mm'),
                transition_endpoints=layer.get('transition_endpoints'),
                note=('interface layer L1 has TWO physical planes (z=0.0 and 0.5 mm)'
                      if int(layer_id) == INTERFACE_LAYER_ID else None)))
    return rows


def _transition_pair_rows(runs):
    rows = []
    for key, entry in runs.items():
        if not entry.get('present'):
            continue
        for pair in entry.get('transition_pairs') or []:
            rows.append(dict(scheme=entry.get('scheme'), stack=entry.get('stack'),
                             **pair))
    return rows


def _failure_summary(runs):
    totals = Counter()
    per_run = {}
    for key, entry in runs.items():
        reasons = entry.get('failure_reasons') or {}
        per_run[key] = dict(failed=entry.get('failed'), reasons=reasons)
        totals.update(reasons)
    return dict(total_by_reason=dict(totals), per_run=per_run)


def run(root, log=print):
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f'L3D root not found: {root}')
    started = time.perf_counter()
    result = collect(root, log=log)
    summary_dir = root / 'summary'
    summary_dir.mkdir(parents=True, exist_ok=True)
    statistics = result['statistics']
    comparison = result['comparison']
    losses = result['losses']
    written = []
    written.append(_write_json(summary_dir / 'l3d_statistics.json', statistics))
    written.append(_write_text(summary_dir / 'l3d_statistics.md',
                               _render_statistics_md(statistics)))
    written.append(_write_text(summary_dir / 'l3d_comparison.md',
                               _render_comparison_md(statistics)))
    written.append(_write_csv(summary_dir / 'l3d_per_route.csv',
                              CSV_PER_ROUTE_FIELDS, result['per_route_rows']))
    written.append(_write_csv(summary_dir / 'l3d_layer_usage.csv',
                              CSV_LAYER_USAGE_FIELDS, result['layer_usage_rows']))
    written.append(_write_csv(summary_dir / 'l3d_transition_pairs.csv',
                              CSV_TRANSITION_PAIR_FIELDS,
                              result['transition_pair_rows']))
    written.append(_write_json(summary_dir / 'l3d_loss_parameters.json', losses))
    return dict(statistics=statistics, comparison=comparison, losses=losses,
                written=[str(path) for path in written],
                seconds=round(time.perf_counter() - started, 3))


def _resolve_root(value):
    if value is None:
        return DEFAULT_ROOT
    path = Path(value)
    if path.is_absolute():
        return path
    candidate = PROJECT_ROOT / path
    if candidate.exists():
        return candidate
    return Path.cwd() / path


def _print_summary(result):
    statistics = result['statistics']
    comparison = result['comparison']
    print(f'[stats_l3d] root={statistics["root"]} '
          f'warnings={len(statistics["warnings"])}')
    for scheme in SCHEMES:
        base = statistics['baseline'].get(scheme) or {}
        print(f'[stats_l3d] baseline L1 {scheme}: routed={_console(base.get("routed"))} '
              f'(expected {_console((base.get("expected") or {}).get("total"))}, '
              f'match={_console(base.get("matches_expected"))})')
    for key, entry in statistics['runs'].items():
        if not entry.get('present'):
            print(f'[stats_l3d] run {key}: n/a')
            continue
        print(f'[stats_l3d] run {key}: routed={_console(entry.get("routed"))} '
              f'added={_console(entry.get("added"))} lifted='
              f'{_console(entry.get("lifted"))} transitions='
              f'{_console(entry.get("transitions"))} '
              f'exploratory={_console((entry.get("validation") or {}).get("exploratory_pass"))} '
              f'formal={_console((entry.get("validation") or {}).get("formal_acceptance"))}')
    print('[stats_l3d] formal acceptance: NOT GRANTED '
          '(L2-L5 heights unconfirmed_simulation)')
    for warning in statistics['warnings'][:20]:
        print(f'[stats_l3d] WARNING: {warning}')
    if len(statistics['warnings']) > 20:
        print(f'[stats_l3d] ... {len(statistics["warnings"]) - 20} more warnings')
    for path in result['written']:
        print(f'[stats_l3d] written {_display_path(path)}')
    for row in comparison.get('primary_rows', []):
        if row.get('corrected_routed') is not None:
            print(f'[stats_l3d] compare {row["scheme"]}: corrected='
                  f'{_console(row.get("corrected_routed"))} vs R15-2D='
                  f'{_console(row.get("r15_2d_baseline"))} (Δ'
                  f'{_console(row.get("delta_vs_r15_2d"))}) vs old-5L='
                  f'{_console(row.get("historical_old_5l"))} (NOT comparable)')
    print(f'[stats_l3d] done in {result["seconds"]}s')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=None,
                        help='L3D 实验输出根目录（默认 '
                             'outputs/four_side_1024_v2_l1l5_v01）')
    parser.add_argument('--quiet', action='store_true',
                        help='只输出写文件信息')
    args = parser.parse_args(argv)
    root = _resolve_root(args.root)
    if not Path(root).is_dir():
        print(f'[stats_l3d] ERROR: root directory not found: {root}')
        return 1
    result = run(root)
    if args.quiet:
        for path in result['written']:
            print(f'[stats_l3d] written {_display_path(path)}')
    else:
        _print_summary(result)
    return 0


if __name__ == '__main__':
    sys.exit(main())
