"""R15 round statistics (read-only JSON analysis, no router imports).

The 2026-10-20 process requirement fixes the minimum curvature radius at
**R = 15 mm** for every planar bend and every 3D elevation S-curve (R40 results
are kept separately and only ever appear in the explicit R40-vs-R15 comparison
table / block).

Usage::

    python -m four_side_1024.r15.stats_r15
    python -m four_side_1024.r15.stats_r15 --root outputs/four_side_1024_v2_r15_v01

Inputs (all optional; missing/partial data -> null fields + warnings)::

    <root>/planes/V2/{A,B}/{z1,z2}/routes.json       2D plane routes (FSLW schema)
    <root>/planes/V2/{A,B}/{z1,z2}/audit_strict.json 2D strict audit (if present)
    <root>/planes/V2/{A,B}/{z1,z2}/statistics.json   fslw statistics (fallback source)
    <root>/combined/V2/{A,B}/routes_1024.json        1024-channel combined layout
    <root>/25d/scheme{A,B}/layers5/routes_25d.json   R15 five-layer 2.5D routes
    <root>/25d/scheme{A,B}/layers5/run_summary.json  R15 2.5D run summary
    <root>/25d/validation/**/*.json                  independent 3D validation

Outputs (only written under ``<root>/summary/``)::

    r15_statistics.json        full machine-readable statistics
    r15_statistics.md          human-readable summary (2D, 3D, loss, warnings)
    r15_comparison_table.md    explicit R40-vs-R15 comparison table
    r15_per_waveguide_2d.csv   one row per 2D plane route
    r15_per_waveguide_3d.csv   one row per R15 2.5D route
    r15_loss_parameters.json   calibrated / uncalibrated loss parameters only

Design rules honoured here:

* every geometric quantity is recomputed from the stored primitives (lengths,
  arc radii, sweep angles, transition theta/footprint/arc length), the saved
  summary fields are only used as cross-checks;
* no new loss coefficients are invented - only the experiment convention
  propagation loss 0.05 dB/cm is classified (not measured), bend / crossing /
  interlayer losses are ``unknown_uncalibrated`` and no total-loss conclusion is
  produced;
* nothing outside ``<root>/summary/`` is ever written.
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
DEFAULT_ROOT = PROJECT_ROOT / 'outputs' / 'four_side_1024_v2_r15_v01'

SCHEMA_STATISTICS = 'four_side_1024_v2_r15_statistics_v1'
SCHEMA_COMPARISON = 'four_side_1024_v2_r15_comparison_v1'
SCHEMA_LOSS = 'four_side_1024_v2_r15_loss_parameters_v1'

SCHEMES = ('A', 'B')
PLANES = ('z1', 'z2')
N_LAYERS_25D = 5
TOTAL_ROUTES_1024 = 1024
EXPECTED_RADIUS_MM = 15.0
RADIUS_TOL_MM = 1e-6
QUARTER_TOL_DEG = 1e-6
DASH = '—'

# Frozen historical R40 routed counts - ONLY used in the explicit comparison.
R40_COMPARISON = {
    '2d_A': 752,    # R40 2D D56 (Short-S) baseline
    '2d_B': 262,    # R40 2D pure orthogonal 90 deg baseline
    '25d_A': 820,   # R40 5-layer 2.5D + Short-S
    '25d_B': 383,   # R40 5-layer 2.5D + pure orthogonal
}
R40_NOTE = ('R40 numbers are the frozen historical routed counts only; every '
            'length/geometry/loss column in this R15 report is computed from R15 '
            'artefacts. The two rounds are never mixed outside this comparison.')

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
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value):
    if value is None:
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


def _safe_div(numerator, denominator):
    if numerator is None or not denominator:
        return None
    return numerator / denominator


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


def _fmt_pct(value):
    return DASH if value is None else f'{float(value):.2f}%'


def _md_table(headers, rows, aligns=None):
    aligns = list(aligns or ['---'] * len(headers))
    lines = ['| ' + ' | '.join(str(item) for item in headers) + ' |',
             '|' + '|'.join(aligns) + '|']
    for row in rows:
        lines.append('| ' + ' | '.join(str(item) for item in row) + ' |')
    return lines


def _radius_key(radius):
    return f'{float(radius):.6f}'


# ---------------------------------------------------------------------------
# primitive geometry (2D)
# ---------------------------------------------------------------------------
def _primitive_geometry(primitive):
    kind = primitive.get('kind')
    if kind == 'line':
        p0 = primitive.get('p0') or [0.0, 0.0]
        p1 = primitive.get('p1') or [0.0, 0.0]
        length = math.hypot(float(p1[0]) - float(p0[0]),
                            float(p1[1]) - float(p0[1]))
        return dict(kind='line', length_mm=length, radius_mm=None,
                    sweep_deg=None, sweep_rad=None)
    if kind == 'arc':
        radius = abs(float(primitive.get('radius') or 0.0))
        sweep_rad = float(primitive.get('sweep') or 0.0)
        return dict(kind='arc', length_mm=abs(sweep_rad) * radius,
                    radius_mm=radius, sweep_deg=math.degrees(sweep_rad),
                    sweep_rad=sweep_rad)
    return dict(kind=str(kind), length_mm=0.0, radius_mm=None,
                sweep_deg=None, sweep_rad=None)


def _is_quarter(sweep_deg):
    return abs(abs(sweep_deg) - 90.0) <= QUARTER_TOL_DEG


def _sweep_bucket(sweep_deg):
    value = abs(float(sweep_deg))
    if _is_quarter(value):
        return '90deg'
    if value < 5.0:
        return 'shortS_0-5deg'
    if value < 10.0:
        return 'shortS_5-10deg'
    if value < 30.0:
        return 'shortS_10-30deg'
    if value < 60.0:
        return 'shortS_30-60deg'
    return 'shortS_60-90deg'


def _merge_geometry_views(views):
    """Merge per-plane geometry views into one label-level view (fallback when
    the combined routes_1024.json is missing)."""
    views = [view for view in views if isinstance(view, dict)]
    if not views:
        return None

    def _add(key):
        return _sum(view.get(key) for view in views)

    radius_counts = Counter()
    for view in views:
        for radius, count in (view.get('radius_distribution') or {}).items():
            radius_counts[str(radius)] += int(count)
    sweep_buckets = Counter()
    for view in views:
        sweep_buckets.update(view.get('sweep_buckets') or {})
    quarters = [(view.get('quarter_mean_sweep_deg'),
                 view.get('quarter_arc_count') or 0) for view in views]
    short_s = [(view.get('short_s_mean_sweep_deg'),
                view.get('short_s_arc_count') or 0) for view in views]

    def _weighted_mean(pairs):
        total_count = sum(count for _mean_value, count in pairs)
        if not total_count:
            return None
        return sum(mean_value * count for mean_value, count in pairs
                   if mean_value is not None) / total_count

    total = _add('total_length_mm') or 0.0
    straight = _add('straight_length_mm') or 0.0
    arc = _add('arc_length_mm') or 0.0
    min_radii = [view.get('min_radius_mm') for view in views
                 if view.get('min_radius_mm') is not None]
    max_radii = [view.get('max_radius_mm') for view in views
                 if view.get('max_radius_mm') is not None]
    min_short = [view.get('short_s_min_sweep_deg') for view in views
                 if view.get('short_s_min_sweep_deg') is not None]
    max_short = [view.get('short_s_max_sweep_deg') for view in views
                 if view.get('short_s_max_sweep_deg') is not None]
    return dict(
        total_length_mm=_round(total),
        straight_length_mm=_round(straight),
        arc_length_mm=_round(arc),
        mean_length_mm=None,
        straight_fraction_pct=_pct(straight, total),
        arc_fraction_pct=_pct(arc, total),
        line_count=_sum(view.get('line_count') for view in views),
        arc_count=_sum(view.get('arc_count') for view in views),
        radius_distribution=dict(sorted(radius_counts.items(),
                                        key=lambda item: float(item[0]))),
        min_radius_mm=_round(min(min_radii)) if min_radii else None,
        max_radius_mm=_round(max(max_radii)) if max_radii else None,
        expected_radius_mm=EXPECTED_RADIUS_MM,
        all_arcs_expected_radius=(
            all(abs(float(key) - EXPECTED_RADIUS_MM) <= RADIUS_TOL_MM
                for key in radius_counts) if radius_counts else None),
        quarter_arc_count=_sum(view.get('quarter_arc_count') for view in views),
        short_s_arc_count=_sum(view.get('short_s_arc_count') for view in views),
        routes_with_short_s=_sum(view.get('routes_with_short_s') for view in views),
        quarter_arc_length_mm=_round(_add('quarter_arc_length_mm')),
        short_s_arc_length_mm=_round(_add('short_s_arc_length_mm')),
        quarter_mean_sweep_deg=_round(_weighted_mean(quarters), 6),
        short_s_mean_sweep_deg=_round(_weighted_mean(short_s), 6),
        short_s_min_sweep_deg=_round(min(min_short), 6) if min_short else None,
        short_s_max_sweep_deg=_round(max(max_short), 6) if max_short else None,
        sweep_buckets=dict(sorted(sweep_buckets.items())),
    )


def _route_2d_geometry(primitives):
    """Recompute length / arc / sweep statistics from 2D primitives."""
    pieces = [_primitive_geometry(primitive) for primitive in (primitives or [])]
    lines = [piece for piece in pieces if piece['kind'] == 'line']
    arcs = [piece for piece in pieces if piece['kind'] == 'arc']
    other = [piece for piece in pieces
             if piece['kind'] not in ('line', 'arc')]
    straight = _sum(piece['length_mm'] for piece in lines)
    arc_length = _sum(piece['length_mm'] for piece in arcs)
    total = straight + arc_length
    radii = [_radius_key(piece['radius_mm']) for piece in arcs]
    sweeps = [piece['sweep_deg'] for piece in arcs]
    quarters = [value for value in sweeps if _is_quarter(value)]
    short_s = [value for value in sweeps if not _is_quarter(value)]
    quarter_abs = [abs(value) for value in quarters]
    short_abs = [abs(value) for value in short_s]
    buckets = Counter(_sweep_bucket(value) for value in sweeps)
    return dict(
        length_mm=total,
        straight_length_mm=straight,
        arc_length_mm=arc_length,
        line_count=len(lines),
        arc_count=len(arcs),
        other_kind_count=len(other),
        radius_values=radii,
        radii_mm=sorted({piece['radius_mm'] for piece in arcs}),
        min_radius_mm=(min((piece['radius_mm'] for piece in arcs), default=None)),
        max_radius_mm=(max((piece['radius_mm'] for piece in arcs), default=None)),
        sweeps_deg=[round(value, 9) for value in sweeps],
        quarter_count=len(quarters),
        short_s_count=len(short_s),
        quarter_mean_sweep_deg=_mean(quarter_abs),
        short_s_mean_sweep_deg=_mean(short_abs),
        short_s_min_sweep_deg=(min(short_abs) if short_abs else None),
        short_s_max_sweep_deg=(max(short_abs) if short_abs else None),
        quarter_arc_length_mm=_sum(
            piece['length_mm'] for piece in arcs
            if _is_quarter(piece['sweep_deg'])),
        short_s_arc_length_mm=_sum(
            piece['length_mm'] for piece in arcs
            if not _is_quarter(piece['sweep_deg'])),
        sweep_buckets=dict(buckets),
    )


# ---------------------------------------------------------------------------
# primitive geometry (2.5D transitions)
# ---------------------------------------------------------------------------
def _transition_metrics(part):
    radius = abs(float(part.get('radius_mm') or 0.0))
    z0 = float(part.get('z0_mm') or 0.0)
    z1 = float(part.get('z1_mm') or 0.0)
    dz = abs(z1 - z0)
    theta = None
    footprint = None
    length = None
    if radius > 0 and dz < 2.0 * radius:
        theta = math.acos(max(-1.0, min(1.0, 1.0 - dz / (2.0 * radius))))
        footprint = 2.0 * radius * math.sin(theta)
        length = 2.0 * radius * theta
    return dict(
        radius_mm=radius,
        dz_mm=dz,
        theta_rad=theta,
        theta_deg=(math.degrees(theta) if theta is not None else None),
        footprint_mm=footprint,
        length_mm=length,
        saved_radius_mm=_num(part.get('radius_mm')),
        saved_footprint_mm=_num(part.get('footprint_mm')),
        saved_length_mm=_num(part.get('length_mm')),
        saved_dz_mm=_num(part.get('dz_mm')),
    )


def _route_3d_geometry(record):
    """Recompute per-route 3D lengths and transition metrics from parts."""
    parts = record.get('parts') or []
    flat_parts = [part for part in parts if part.get('kind') == 'flat']
    transitions = [part for part in parts if part.get('kind') == 'transition']
    flat_length = 0.0
    flat_length_saved = 0.0
    flat_parts_per_layer = Counter()
    flat_arc_count = 0
    flat_line_count = 0
    for part in flat_parts:
        geometry = _route_2d_geometry(part.get('primitives') or [])
        flat_length += geometry['length_mm']
        flat_arc_count += geometry['arc_count']
        flat_line_count += geometry['line_count']
        flat_length_saved += float(part.get('length_mm') or 0.0)
        layer = part.get('layer')
        flat_parts_per_layer[str(int(layer)) if layer is not None else 'unknown'] += 1
    transition_metrics = [_transition_metrics(part) for part in transitions]
    transition_length = _sum(item['length_mm'] for item in transition_metrics)
    transition_length_saved = _sum(item['saved_length_mm']
                                   for item in transition_metrics)
    total_length = flat_length + transition_length
    return dict(
        flat_length_mm=flat_length,
        flat_length_saved_mm=flat_length_saved,
        transition_length_mm=transition_length,
        transition_length_saved_mm=transition_length_saved,
        total_length_mm=total_length,
        total_length_saved_mm=_num(record.get('length_mm')),
        xy_length_mm=_num(record.get('xy_length_mm')),
        flat_parts_count=len(flat_parts),
        transition_parts_count=len(transitions),
        flat_parts_per_layer=dict(flat_parts_per_layer),
        flat_arc_count=flat_arc_count,
        flat_line_count=flat_line_count,
        transitions=transition_metrics,
        transition_radius_values=[item['radius_mm'] for item in transition_metrics],
        transition_theta_deg_sum=_sum(item['theta_deg'] for item in transition_metrics),
        transition_footprint_sum_mm=_sum(item['footprint_mm']
                                         for item in transition_metrics),
        transition_arc_length_sum_mm=_sum(item['length_mm']
                                          for item in transition_metrics),
        transition_radii_mm=sorted({item['radius_mm'] for item in transition_metrics}),
        transition_dz_mm=[round(item['dz_mm'], 9) for item in transition_metrics],
    )


# ---------------------------------------------------------------------------
# aggregate geometry helpers
# ---------------------------------------------------------------------------
def _empty_geometry_aggregate():
    return dict(
        straight_length_mm=0.0,
        arc_length_mm=0.0,
        total_length_mm=0.0,
        arc_count=0,
        line_count=0,
        quarter_count=0,
        short_s_count=0,
        quarter_arc_length_mm=0.0,
        short_s_arc_length_mm=0.0,
        sweep_buckets=Counter(),
        radius_counter=Counter(),
        sweeps_90=[],
        sweeps_short_s=[],
        routes_with_short_s=0,
        min_radius_mm=None,
        max_radius_mm=None,
    )


def _accumulate_geometry(aggregate, geometry):
    aggregate['straight_length_mm'] += geometry['straight_length_mm']
    aggregate['arc_length_mm'] += geometry['arc_length_mm']
    aggregate['total_length_mm'] += geometry['length_mm']
    aggregate['arc_count'] += geometry['arc_count']
    aggregate['line_count'] += geometry['line_count']
    aggregate['quarter_count'] += geometry['quarter_count']
    aggregate['short_s_count'] += geometry['short_s_count']
    aggregate['quarter_arc_length_mm'] += geometry['quarter_arc_length_mm']
    aggregate['short_s_arc_length_mm'] += geometry['short_s_arc_length_mm']
    aggregate['sweep_buckets'].update(geometry['sweep_buckets'])
    for radius in geometry['radius_values']:
        aggregate['radius_counter'][radius] += 1
    aggregate['sweeps_90'].extend([abs(value) for value in geometry['sweeps_deg']
                                   if _is_quarter(value)])
    aggregate['sweeps_short_s'].extend(
        [abs(value) for value in geometry['sweeps_deg']
         if not _is_quarter(value)])
    if geometry['short_s_count']:
        aggregate['routes_with_short_s'] += 1
    for value in (geometry['min_radius_mm'], geometry['max_radius_mm']):
        if value is not None:
            if aggregate['min_radius_mm'] is None or value < aggregate['min_radius_mm']:
                aggregate['min_radius_mm'] = value
            if aggregate['max_radius_mm'] is None or value > aggregate['max_radius_mm']:
                aggregate['max_radius_mm'] = value


def _geometry_aggregate_view(aggregate, routed_count, expected_radius=EXPECTED_RADIUS_MM):
    radius_counts = dict(sorted(aggregate['radius_counter'].items(),
                                key=lambda item: float(item[0])))
    if radius_counts:
        all_expected = all(abs(float(key) - expected_radius) <= RADIUS_TOL_MM
                           for key in radius_counts)
    else:
        all_expected = None
    view = dict(
        straight_length_mm=_round(aggregate['straight_length_mm']),
        arc_length_mm=_round(aggregate['arc_length_mm']),
        total_length_mm=_round(aggregate['total_length_mm']),
        mean_length_mm=_round(_safe_div(aggregate['total_length_mm'], routed_count)),
        straight_fraction_pct=_pct(aggregate['straight_length_mm'],
                                   aggregate['total_length_mm']),
        arc_fraction_pct=_pct(aggregate['arc_length_mm'],
                              aggregate['total_length_mm']),
        line_count=aggregate['line_count'],
        arc_count=aggregate['arc_count'],
        arcs_per_route=_round(_safe_div(aggregate['arc_count'], routed_count), 4),
        radius_distribution=radius_counts,
        min_radius_mm=_round(aggregate['min_radius_mm']),
        max_radius_mm=_round(aggregate['max_radius_mm']),
        expected_radius_mm=expected_radius,
        all_arcs_expected_radius=all_expected,
        quarter_arc_count=aggregate['quarter_count'],
        short_s_arc_count=aggregate['short_s_count'],
        short_s_arc_fraction_pct=_pct(aggregate['short_s_count'],
                                      aggregate['arc_count']),
        routes_with_short_s=aggregate['routes_with_short_s'],
        quarter_arc_length_mm=_round(aggregate['quarter_arc_length_mm']),
        short_s_arc_length_mm=_round(aggregate['short_s_arc_length_mm']),
        quarter_mean_sweep_deg=_round(_mean(aggregate['sweeps_90']), 6),
        short_s_mean_sweep_deg=_round(_mean(aggregate['sweeps_short_s']), 6),
        short_s_min_sweep_deg=_round(min(aggregate['sweeps_short_s']), 6)
        if aggregate['sweeps_short_s'] else None,
        short_s_max_sweep_deg=_round(max(aggregate['sweeps_short_s']), 6)
        if aggregate['sweeps_short_s'] else None,
        sweep_buckets=dict(sorted(aggregate['sweep_buckets'].items())),
    )
    return view


# ---------------------------------------------------------------------------
# 2D analysis
# ---------------------------------------------------------------------------
def _plane_dir(root, label, plane):
    return Path(root) / 'planes' / 'V2' / label / plane


def _combined_path(root, label):
    return Path(root) / 'combined' / 'V2' / label / 'routes_1024.json'


def _failure_reasons(records):
    return dict(Counter(str(record.get('reason') or 'unknown')
                        for record in records
                        if record.get('status') != 'routed'))


def _load_r15_2d_validation(root, label, plane, warnings):
    """validate_r15 per-plane report (``validation/2d/<label>/<plane>.json``)."""
    path = Path(root) / 'validation' / '2d' / label / f'{plane}.json'
    if not path.exists():
        return None
    payload = _load_json(path, warnings,
                         f'validation/2d/{label}/{plane}.json')
    if not isinstance(payload, dict):
        return None
    counts = payload.get('counts') if isinstance(payload.get('counts'), dict) else {}
    strict_2d = payload.get('strict_2d') if isinstance(
        payload.get('strict_2d'), dict) else {}
    violations = payload.get('violations')
    violation_kinds = Counter(
        str(violation.get('kind') or 'unknown') for violation in violations
    ) if isinstance(violations, list) else Counter()
    return dict(
        present=True,
        source=_display_path(path),
        schema=payload.get('schema'),
        kind=payload.get('kind'),
        label=payload.get('label', label),
        plane=payload.get('plane', plane),
        passed=payload.get('passed'),
        routed=_int(payload.get('routed')),
        failed=_int(payload.get('failed')),
        total=_int(payload.get('total')),
        counts=dict(counts) if counts else None,
        violations_count=(len(violations) if isinstance(violations, list)
                          else None),
        violation_kinds=dict(violation_kinds) if violation_kinds else None,
        geometry=payload.get('geometry'),
        process=payload.get('process'),
        strict_2d_passed=strict_2d.get('passed'),
        crossing_count=_int(strict_2d.get('crossing_count')),
        crossing_pair_count=_int(strict_2d.get('crossing_pair_count')),
        min_non_crossing_centerline_mm=_num(
            strict_2d.get('min_non_crossing_centerline_mm')),
        radius_violations=(_int(counts.get('geometry_errors'))
                           if counts else None),
        runtime_seconds=_num(payload.get('runtime_seconds')),
    )


def _load_r15_validation_summary(root, warnings):
    path = Path(root) / 'validation' / 'r15_validation_summary.json'
    if not path.exists():
        return None
    payload = _load_json(path, warnings, 'validation/r15_validation_summary.json')
    if not isinstance(payload, dict):
        return None
    items = payload.get('items') if isinstance(payload.get('items'), dict) else {}
    compact_items = {}
    for key, item in items.items():
        if not isinstance(item, dict):
            continue
        compact_items[key] = dict(
            kind=item.get('kind'),
            passed=item.get('passed'),
            routed=item.get('routed'),
            failed=item.get('failed'),
            total=item.get('total'),
            counts=item.get('counts'),
        )
    return dict(
        present=True,
        source=_display_path(path),
        schema=payload.get('schema'),
        passed=payload.get('passed'),
        counts=payload.get('counts'),
        geometry=payload.get('geometry'),
        items=compact_items,
        items_expected=payload.get('items_expected'),
        pending=payload.get('pending'),
        skipped=payload.get('skipped'),
        profile=payload.get('profile'),
        runtime_seconds=_num(payload.get('runtime_seconds')),
    )


def _load_audit(plane_dir, warnings, tag):
    path = Path(plane_dir) / 'audit_strict.json'
    if not path.exists():
        return None
    payload = _load_json(path, warnings, f'{tag}/audit_strict.json')
    if not isinstance(payload, dict):
        return None
    return dict(
        present=True,
        source=_display_path(path),
        passed=payload.get('passed'),
        policy=payload.get('policy_used'),
        crossing_count=_int(payload.get('crossing_count')),
        crossing_pair_count=_int(payload.get('crossing_pair_count')),
        min_non_crossing_centerline_mm=_num(
            payload.get('min_non_crossing_centerline_mm')),
        violation_pair_count=_int(payload.get('violation_pair_count')),
        radius_violations=_int(payload.get('radius_violations')),
        self_intersections=_int(payload.get('self_intersections')),
        process=payload.get('process'),
        warnings=payload.get('warnings'),
    )


def _load_plane_statistics(plane_dir, warnings, tag):
    path = Path(plane_dir) / 'statistics.json'
    if not path.exists():
        return None
    payload = _load_json(path, warnings, f'{tag}/statistics.json')
    if not isinstance(payload, dict):
        return None
    return dict(
        present=True,
        source=_display_path(path),
        crossing_count=_int(payload.get('crossing_count')),
        min_non_crossing_centerline_mm=_num(
            payload.get('min_non_crossing_centerline_mm')),
        routed=_int(payload.get('routed')),
        audit_passed=payload.get('audit_passed'),
        total_length_mm=_num(payload.get('total_length_mm')),
    )


def _analyse_2d_payload(payload, warnings, tag, expected_records=None,
                        compute_per_route=False):
    """Analyse a routes.json payload (plane or combined) from primitives."""
    if not isinstance(payload, dict):
        return dict(present=False)
    records = payload.get('routes')
    if not isinstance(records, list):
        warnings.append(f'{tag}: payload has no "routes" list')
        return dict(present=False)
    if expected_records is not None and len(records) != expected_records:
        warnings.append(f'{tag}: expected {expected_records} route records, '
                        f'found {len(records)}')
    routed = [record for record in records if record.get('status') == 'routed']
    failed = [record for record in records if record.get('status') != 'routed']
    reasons = _failure_reasons(records)
    by_pair = Counter(str(record.get('pair') or 'unknown') for record in routed)
    by_relation = Counter(str(record.get('relation') or 'unknown')
                          for record in routed)

    aggregate = _empty_geometry_aggregate()
    mismatch_length = []
    mismatch_bend = []
    radius_mismatch = 0
    unexpected_radius_counter = Counter()
    unexpected_radius_routes = []
    per_route = []
    for record in routed:
        primitives = record.get('primitives')
        if not isinstance(primitives, list):
            warnings.append(f'{tag}: route {record.get("route_id")} has no primitives')
            continue
        geometry = _route_2d_geometry(primitives)
        _accumulate_geometry(aggregate, geometry)
        saved_length = _num(record.get('length_mm'))
        if saved_length is not None and not _same_number(saved_length,
                                                         geometry['length_mm']):
            mismatch_length.append(record.get('route_id'))
        saved_bends = _int(record.get('bend_count'))
        if saved_bends is not None and saved_bends != geometry['arc_count']:
            mismatch_bend.append(record.get('route_id'))
        bad_radii = [key for key in geometry['radius_values']
                     if abs(float(key) - EXPECTED_RADIUS_MM) > RADIUS_TOL_MM]
        if bad_radii:
            radius_mismatch += 1
            for key in bad_radii:
                unexpected_radius_counter[key] += 1
            unexpected_radius_routes.append(_int(record.get('route_id')))
        if compute_per_route:
            per_route.append(dict(
                route_id=_int(record.get('route_id')),
                plane=record.get('plane'),
                pair=record.get('pair'),
                relation=record.get('relation'),
                status=record.get('status'),
                length_mm=_round(geometry['length_mm']),
                straight_mm=_round(geometry['straight_length_mm']),
                arc_mm=_round(geometry['arc_length_mm']),
                arc_count=geometry['arc_count'],
                bend_count_saved=saved_bends,
                min_radius_mm=_round(geometry['min_radius_mm']),
                radii_mm=sorted({_round(value) for value in geometry['radius_values']}),
                sweeps_deg=[_round(value) for value in geometry['sweeps_deg']],
                short_s=bool(geometry['short_s_count']),
                short_s_arc_count=geometry['short_s_count'],
                short_s_total_sweep_deg=_round(
                    _sum(abs(value) for value in geometry['sweeps_deg']
                         if not _is_quarter(value))),
                short_s_arc_length_mm=_round(geometry['short_s_arc_length_mm']),
                length_check_mm=_round(saved_length),
                family=(record.get('candidate') or {}).get('family')
                if isinstance(record.get('candidate'), dict) else None,
            ))

    if mismatch_length:
        warnings.append(f'{tag}: {len(mismatch_length)} routed records disagree '
                        f'between saved length_mm and recomputed primitive length '
                        f'(first ids: {mismatch_length[:10]})')
    if mismatch_bend:
        warnings.append(f'{tag}: {len(mismatch_bend)} routed records disagree '
                        f'between saved bend_count and recomputed arc count '
                        f'(first ids: {mismatch_bend[:10]})')
    if radius_mismatch:
        warnings.append(f'{tag}: {radius_mismatch} routed records contain arc '
                        f'radii different from the expected R=15 mm')

    if compute_per_route:
        for record in failed:
            per_route.append(dict(
                route_id=_int(record.get('route_id')),
                plane=record.get('plane'),
                pair=record.get('pair'),
                relation=record.get('relation'),
                status=record.get('status'),
                reason=record.get('reason'),
                length_mm=None,
                straight_mm=None,
                arc_mm=None,
                arc_count=None,
                bend_count_saved=None,
                min_radius_mm=None,
                radii_mm=None,
                sweeps_deg=None,
                short_s=False,
                short_s_arc_count=None,
                short_s_total_sweep_deg=None,
                short_s_arc_length_mm=None,
                length_check_mm=None,
                family=None,
            ))

    geometry_view = _geometry_aggregate_view(aggregate, len(routed))
    total_length = geometry_view['total_length_mm'] or 0.0
    propagation_length_cm = total_length / 10.0
    result = dict(
        present=True,
        source=_display_path(payload.get('__source_path__')
                             if payload.get('__source_path__') else tag),
        schema=payload.get('schema'),
        process=payload.get('process'),
        total=len(records),
        routed=len(routed),
        failed=len(failed),
        routing_rate_pct=_pct(len(routed), len(records)),
        failure_reasons=reasons,
        failed_route_ids=sorted(_int(record.get('route_id')) for record in failed
                                if record.get('route_id') is not None),
        by_pair=dict(by_pair),
        by_relation=dict(by_relation),
        geometry=geometry_view,
        propagation_length_cm=_round(propagation_length_cm, 6),
        propagation_loss_convention_db=_round(
            propagation_length_cm * PROPAGATION_LOSS_DB_PER_CM, 6),
        propagation_loss_status='experimental_convention_not_measured',
        saved_fields_checked=dict(
            length_mismatch_count=len(mismatch_length),
            bend_count_mismatch_count=len(mismatch_bend),
            radius_mismatch_count=radius_mismatch,
        ),
        radius_expectation=dict(
            expected_radius_mm=EXPECTED_RADIUS_MM,
            all_arcs_expected=geometry_view.get('all_arcs_expected_radius'),
            unexpected_arc_count=sum(unexpected_radius_counter.values()),
            unexpected_radius_distribution=dict(sorted(
                unexpected_radius_counter.items(),
                key=lambda item: float(item[0]))),
            routes_with_unexpected_radius=sorted(unexpected_radius_routes),
        ),
        per_route=per_route,
    )
    return result


def _analyse_plane(root, label, plane, warnings, per_route_rows):
    tag = f'planes/V2/{label}/{plane}'
    path = _plane_dir(root, label, plane) / 'routes.json'
    if not path.exists():
        warnings.append(f'{tag}/routes.json missing (null fields)')
        return dict(present=False, source=None, routed=None, failed=None,
                    total=None)
    payload = _load_json(path, warnings, f'{tag}/routes.json')
    if isinstance(payload, dict):
        payload = dict(payload)
        payload['__source_path__'] = path
    result = _analyse_2d_payload(payload, warnings, tag, expected_records=512,
                                 compute_per_route=True)
    if not result.get('present'):
        return dict(present=False, source=_display_path(path))
    result['label'] = label
    result['plane'] = plane
    result['z_mm'] = (payload or {}).get('z_mm')
    result['audit'] = _load_audit(_plane_dir(root, label, plane), warnings, tag)
    statistics = _load_plane_statistics(_plane_dir(root, label, plane),
                                        warnings, tag)
    result['statistics_fallback'] = statistics
    r15_validation = _load_r15_2d_validation(root, label, plane, warnings)
    result['r15_validation'] = r15_validation
    r15_view = r15_validation or {}
    if result['audit'] is None and statistics is not None:
        result['crossing_count'] = statistics.get('crossing_count')
        result['crossing_source'] = 'statistics.json fallback'
        result['min_non_crossing_centerline_mm'] = statistics.get(
            'min_non_crossing_centerline_mm')
    elif result['audit'] is not None:
        result['crossing_count'] = result['audit'].get('crossing_count')
        result['crossing_source'] = 'audit_strict.json'
        result['min_non_crossing_centerline_mm'] = result['audit'].get(
            'min_non_crossing_centerline_mm')
    elif r15_view.get('present'):
        result['crossing_count'] = r15_view.get('crossing_count')
        result['crossing_source'] = 'validation/2d (validate_r15 fallback)'
        result['min_non_crossing_centerline_mm'] = r15_view.get(
            'min_non_crossing_centerline_mm')
    else:
        result['crossing_count'] = None
        result['crossing_source'] = None
        result['min_non_crossing_centerline_mm'] = None
    result['validation_passed'] = r15_view.get('passed')
    if result.get('audit') is not None and result['audit'].get('passed') is False:
        warnings.append(f'{tag}: 2D strict audit did not pass')
    if r15_view.get('present') and r15_view.get('passed') is False:
        warnings.append(
            f'{tag}: validate_r15 2D validation FAILED '
            f'(violations={r15_view.get("violations_count")}, '
            f'counts={r15_view.get("counts")})')
    for row in result.get('per_route') or []:
        row = dict(row)
        row['label'] = label
        row['plane'] = plane
        per_route_rows.append(row)
    result.pop('per_route', None)
    return result


def _analyse_combined(root, label, warnings):
    tag = f'combined/V2/{label}'
    path = _combined_path(root, label)
    if not path.exists():
        warnings.append(f'{tag}/routes_1024.json missing (null fields)')
        return dict(present=False, source=None)
    payload = _load_json(path, warnings, f'{tag}/routes_1024.json')
    if isinstance(payload, dict):
        payload = dict(payload)
        payload['__source_path__'] = path
    result = _analyse_2d_payload(payload, warnings, tag,
                                 expected_records=TOTAL_ROUTES_1024)
    if not result.get('present'):
        return dict(present=False, source=_display_path(path))
    result['label'] = label
    result['crossing_count'] = None
    result.pop('per_route', None)
    return result


def _analyse_two_d(root, warnings, per_route_rows):
    labels = {}
    for label in SCHEMES:
        planes = {}
        for plane in PLANES:
            planes[plane] = _analyse_plane(root, label, plane, warnings,
                                           per_route_rows)
        combined = _analyse_combined(root, label, warnings)
        routed_sum = sum(planes[plane].get('routed') or 0 for plane in PLANES)
        length_sum = sum(planes[plane].get('geometry', {}).get('total_length_mm') or 0.0
                         for plane in PLANES)
        crossings_sum = sum(planes[plane].get('crossing_count') or 0
                            for plane in PLANES)
        crossing_present = any(planes[plane].get('crossing_count') is not None
                               for plane in PLANES)
        checks = dict(
            plane_routed_sum=routed_sum,
            plane_length_sum_mm=_round(length_sum),
            plane_crossing_sum=crossings_sum if crossing_present else None,
            combined_routed=combined.get('routed'),
            combined_routed_matches=(combined.get('routed') == routed_sum
                                     if combined.get('present') else None),
            combined_length_matches=(
                _same_number(combined.get('geometry', {}).get('total_length_mm'),
                             length_sum)
                if combined.get('present') else None),
        )
        if combined.get('present') and combined.get('routed') is not None \
                and routed_sum and combined['routed'] != routed_sum:
            warnings.append(f'2D {label}: combined routed={combined["routed"]} != '
                            f'sum of planes={routed_sum}')
        labels[label] = dict(
            planes=planes,
            combined=combined,
            totals=dict(
                routed=(combined.get('routed') if combined.get('present')
                        else routed_sum),
                failed=(combined.get('failed') if combined.get('present')
                        else sum(planes[plane].get('failed') or 0
                                 for plane in PLANES)),
                total=(combined.get('total') if combined.get('present')
                       else sum(planes[plane].get('total') or 0
                                for plane in PLANES)),
                total_length_mm=(combined.get('geometry', {}).get('total_length_mm')
                                 if combined.get('present') else _round(length_sum)),
                arc_count=(combined.get('geometry', {}).get('arc_count')
                           if combined.get('present')
                           else sum(planes[plane].get('geometry', {}).get('arc_count') or 0
                                    for plane in PLANES)),
                quarter_arc_count=(combined.get('geometry', {}).get(
                    'quarter_arc_count') if combined.get('present')
                    else sum(planes[plane].get('geometry', {}).get('quarter_arc_count') or 0
                             for plane in PLANES)),
                short_s_arc_count=(combined.get('geometry', {}).get(
                    'short_s_arc_count') if combined.get('present')
                    else sum(planes[plane].get('geometry', {}).get(
                        'short_s_arc_count') or 0 for plane in PLANES)),
                crossing_count=(crossings_sum if crossing_present else None),
                source=('combined routes_1024.json' if combined.get('present')
                        else 'sum of plane routes.json (combined missing)'),
                geometry=(combined.get('geometry') if combined.get('present')
                          else _merge_geometry_views(
                              [planes[plane].get('geometry') for plane in PLANES])),
                geometry_source=('combined routes_1024.json'
                                 if combined.get('present')
                                 else 'merged plane geometry (combined missing)'),
            ),
            checks=checks,
        )
    validation_dir = Path(root) / 'validation'
    final_validation = None
    for candidate in (Path(root) / 'final_validation.json',
                      validation_dir / 'final_validation.json',
                      Path(root) / 'validation_2d' / 'final_validation.json'):
        if candidate.exists():
            payload = _load_json(candidate, warnings, 'final_validation.json')
            if isinstance(payload, dict):
                final_validation = dict(
                    present=True,
                    source=_display_path(candidate),
                    passed=payload.get('passed'),
                    keys=sorted(payload.keys())[:40],
                    warnings=payload.get('warnings') if isinstance(
                        payload.get('warnings'), list) else None,
                )
            break
    if final_validation is None:
        final_validation = _load_r15_validation_summary(root, warnings)
    if final_validation is None:
        warnings.append('2D validation outputs missing (final_validation.json / '
                        'validation/r15_validation_summary.json); 2D validation '
                        'block null')
    for label in SCHEMES:
        combined_validation_path = (validation_dir / '2d' / label
                                    / 'combined.json')
        combined_validation = None
        if combined_validation_path.exists():
            payload = _load_json(combined_validation_path, warnings,
                                 f'validation/2d/{label}/combined.json')
            if isinstance(payload, dict):
                counts = payload.get('counts') if isinstance(
                    payload.get('counts'), dict) else {}
                strict_2d = payload.get('strict_2d') if isinstance(
                    payload.get('strict_2d'), dict) else {}
                violations = payload.get('violations')
                combined_validation = dict(
                    present=True,
                    source=_display_path(combined_validation_path),
                    passed=payload.get('passed'),
                    routed=_int(payload.get('routed')),
                    failed=_int(payload.get('failed')),
                    total=_int(payload.get('total')),
                    counts=dict(counts) if counts else None,
                    violations_count=(len(violations)
                                      if isinstance(violations, list) else None),
                    crossing_count=_int(strict_2d.get('crossing_count')),
                    radius_values=(payload.get('geometry') or {}).get(
                        'arc_radius_values')
                    if isinstance(payload.get('geometry'), dict) else None,
                )
        labels[label]['r15_validation_combined'] = combined_validation

    process = None
    process_source = None
    for label in SCHEMES:
        for plane in PLANES:
            candidate = labels[label]['planes'][plane].get('process')
            if isinstance(candidate, dict):
                process = candidate
                process_source = f'planes/V2/{label}/{plane}/routes.json:process'
                break
        if process:
            break
    detected_radius = _num((process or {}).get('radius_mm',
                                               (process or {}).get(
                                                   'min_bend_radius_mm')))
    propagation = _num((process or {}).get('propagation_loss_db_per_cm'))
    process_info = dict(
        source=process_source,
        radius_mm=detected_radius,
        expected_radius_mm=EXPECTED_RADIUS_MM,
        radius_ok=(abs(detected_radius - EXPECTED_RADIUS_MM) <= RADIUS_TOL_MM
                   if detected_radius is not None else None),
        fixed_radius_40mm=(process or {}).get('fixed_radius_40mm'),
        process_profile=(process or {}).get('process_profile'),
        propagation_loss_db_per_cm=_pick(propagation,
                                         PROPAGATION_LOSS_DB_PER_CM),
    )
    if detected_radius is not None and process_info['radius_ok'] is False:
        warnings.append(f'2D process radius_mm={detected_radius} differs from the '
                        f'R15 requirement R={EXPECTED_RADIUS_MM} mm')
    return dict(labels=labels, validation_2d=final_validation,
                process=process_info)


# ---------------------------------------------------------------------------
# 3D validation discovery
# ---------------------------------------------------------------------------
def _looks_like_validation_report(payload):
    keys = set(payload)
    has_identity = 'scheme' in keys and 'n_layers' in keys
    has_input = 'input' in keys
    has_verdict = 'passed' in keys
    has_counts = isinstance(payload.get('counts'), dict)
    return bool((has_identity and (has_verdict or has_counts))
                or (has_input and (has_verdict or has_counts)))


def _extract_validation_reports(payload, depth=0):
    reports = []
    if depth > 4:
        return reports
    if isinstance(payload, dict):
        if _looks_like_validation_report(payload):
            return [payload]
        for value in payload.values():
            reports.extend(_extract_validation_reports(value, depth + 1))
    elif isinstance(payload, list):
        for item in payload:
            reports.extend(_extract_validation_reports(item, depth + 1))
    return reports


def _report_identity(report, source):
    scheme = None
    n_layers = None
    raw_scheme = report.get('scheme')
    if isinstance(raw_scheme, str) and raw_scheme.strip().upper() in SCHEMES:
        scheme = raw_scheme.strip().upper()
    try:
        raw_layers = report.get('n_layers')
        if raw_layers is not None:
            n_layers = int(raw_layers)
    except (TypeError, ValueError):
        n_layers = None
    text = f'{report.get("input") or ""} {source}'
    if scheme is None:
        match = re.search(r'scheme\s*[_-]?\s*([AB])\b', text, re.IGNORECASE)
        if match:
            scheme = match.group(1).upper()
    if n_layers is None:
        match = re.search(r'layers?\s*[_-]?\s*([35])\b', text, re.IGNORECASE)
        if match:
            n_layers = int(match.group(1))
    return scheme, n_layers


def _validation_view(report, source):
    counts = report.get('counts') if isinstance(report.get('counts'), dict) else {}
    crossings = report.get('crossings')
    crossings_total = None
    crossings_by_layer = None
    if isinstance(crossings, dict):
        raw_total = crossings.get('total')
        if isinstance(raw_total, (int, float)):
            crossings_total = int(raw_total)
        raw_layers = crossings.get('by_layer')
        if isinstance(raw_layers, dict):
            layers = {}
            for key, value in raw_layers.items():
                try:
                    layers[str(int(key))] = int(value)
                except (TypeError, ValueError):
                    continue
            crossings_by_layer = dict(sorted(layers.items(),
                                             key=lambda item: int(item[0])))
            if crossings_total is None and crossings_by_layer:
                crossings_total = sum(crossings_by_layer.values())
    passed = report.get('passed')
    if not isinstance(passed, bool):
        text = str(passed).strip().upper()
        passed = True if text in ('PASS', 'PASSED', 'TRUE', 'OK') else (
            False if text in ('FAIL', 'FAILED', 'FALSE') else None)
    return dict(
        present=True,
        source=_display_path(source),
        schema=report.get('schema'),
        label=report.get('label'),
        passed=passed,
        routed=_int(report.get('routed')),
        failed=_int(report.get('failed')),
        total=_int(report.get('total')),
        failure_reasons=report.get('failure_reasons'),
        crossings_total=crossings_total,
        crossings_by_layer=crossings_by_layer,
        violations_count=_int(report.get('violations_count')),
        counts=dict(counts) if counts else None,
        min_3d_distance_mm=_num(report.get('min_3d_distance_mm')),
        min_3d_distance_excluding_crossings_mm=_num(
            report.get('min_3d_distance_excluding_crossings_mm')),
        min_3d_distance_including_crossings_mm=_num(
            report.get('min_3d_distance_including_crossings_mm')),
        min_curvature_radius_mm=_num(report.get('min_curvature_radius_mm')),
        stats=dict(report.get('stats')) if isinstance(report.get('stats'), dict)
        else None,
        runtime_seconds=_num(report.get('runtime_seconds')),
        port_csv_checked=report.get('port_csv_checked'),
        warnings=report.get('warnings') if isinstance(report.get('warnings'), list)
        else None,
    )


def _discover_3d_validations(root, warnings):
    base = Path(root) / '25d'
    validation_dirs = [base / 'validation', Path(root) / 'validation']
    reports = []
    for directory in validation_dirs:
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob('*.json')):
            if not path.is_file():
                continue
            payload = _load_json(path, warnings,
                                 f'3D validation file {path.name}')
            if payload is None:
                continue
            for report in _extract_validation_reports(payload):
                if isinstance(report, dict):
                    reports.append((path, report))
    if not reports:
        warnings.append('3D validation reports not found under '
                        f'{_display_path(base / "validation")} or '
                        f'{_display_path(Path(root) / "validation")} '
                        '(3D validation block null)')
    result = {}
    for scheme in SCHEMES:
        matches = []
        for path, report in reports:
            report_scheme, report_layers = _report_identity(report, path)
            if report_scheme == scheme and report_layers == N_LAYERS_25D:
                matches.append((path, report))
        if matches:
            matches.sort(key=lambda item: (
                -4 if item[1].get('scheme') == scheme else 0,
                -4 if item[1].get('n_layers') is not None else 0,
                1 if 'all_validation' in item[0].name.lower() else 0,
                str(item[0])))
            path, report = matches[0]
            result[scheme] = _validation_view(report, path)
            if len(matches) > 1:
                warnings.append(f'3D {scheme}: {len(matches)} validation reports '
                                f'matched; using {_display_path(path)}')
    return result


# ---------------------------------------------------------------------------
# 3D (2.5D five-layer) analysis
# ---------------------------------------------------------------------------
def _run_25d_dir(root, scheme):
    return Path(root) / '25d' / f'scheme{scheme}' / f'layers{N_LAYERS_25D}'


def _analyse_25d_scheme(root, scheme, validation, warnings, per_route_rows):
    tag = f'25d/scheme{scheme}/layers{N_LAYERS_25D}'
    run_dir = _run_25d_dir(root, scheme)
    routes_path = run_dir / 'routes_25d.json'
    summary_path = run_dir / 'run_summary.json'
    if not routes_path.exists() and not summary_path.exists():
        warnings.append(f'{tag}: routes_25d.json and run_summary.json missing '
                        f'(null fields)')
        return dict(present=False, source=None, validation=validation)
    payload = _load_json(routes_path, warnings, f'{tag}/routes_25d.json')
    summary = _load_json(summary_path, warnings, f'{tag}/run_summary.json')
    payload = payload if isinstance(payload, dict) else {}
    summary = summary if isinstance(summary, dict) else {}
    records = payload.get('routes') if isinstance(payload.get('routes'), list) \
        else None
    if records is None:
        warnings.append(f'{tag}: routes_25d.json has no routes list')
    stats = payload.get('statistics') if isinstance(payload.get('statistics'), dict) \
        else (summary.get('statistics') if isinstance(summary.get('statistics'), dict)
              else {})

    routed = [record for record in (records or [])
              if record.get('status') == 'routed']
    failed = [record for record in (records or [])
              if record.get('status') != 'routed']
    lifted = [record for record in routed if record.get('lifted')]
    transitions_per_route = Counter()
    travel_layers = Counter()
    flat_parts_per_layer = Counter()
    flat_length = 0.0
    transition_length = 0.0
    total_length = 0.0
    transition_radius_counter = Counter()
    transition_dz_counter = Counter()
    theta_sum = footprint_sum = arc_length_sum = 0.0
    mismatch_radius = 0
    mismatch_footprint = 0
    mismatch_length = 0
    mismatch_theta = 0
    unexpected_transition_radius_counter = Counter()
    unexpected_transition_routes = set()
    for record in routed:
        geometry = _route_3d_geometry(record)
        flat_length += geometry['flat_length_mm']
        transition_length += geometry['transition_length_mm']
        total_length += geometry['total_length_mm']
        transitions_per_route[int(record.get('n_transitions') or 0)] += 1
        if record.get('lifted'):
            travel_layers[str(record.get('travel_layer'))] += 1
        for layer, count in geometry['flat_parts_per_layer'].items():
            flat_parts_per_layer[layer] += count
        for transition in geometry['transitions']:
            transition_radius_counter[_radius_key(transition['radius_mm'])] += 1
            transition_dz_counter[f'{transition["dz_mm"]:.6f}'] += 1
            theta_sum += transition['theta_deg'] or 0.0
            footprint_sum += transition['footprint_mm'] or 0.0
            arc_length_sum += transition['length_mm'] or 0.0
            if abs((transition['saved_radius_mm'] or 0.0)
                   - transition['radius_mm']) > RADIUS_TOL_MM:
                mismatch_radius += 1
            if abs(transition['radius_mm'] - EXPECTED_RADIUS_MM) > RADIUS_TOL_MM:
                unexpected_transition_radius_counter[
                    _radius_key(transition['radius_mm'])] += 1
                unexpected_transition_routes.add(_int(record.get('route_id')))
            if not _same_number(transition['saved_footprint_mm'],
                                transition['footprint_mm'], rel=1e-6):
                mismatch_footprint += 1
            if not _same_number(transition['saved_length_mm'],
                                transition['length_mm'], rel=1e-6):
                mismatch_length += 1
            saved_dz = transition['saved_dz_mm']
            if saved_dz is None or not _same_number(abs(saved_dz),
                                                    transition['dz_mm'], rel=1e-6):
                mismatch_theta += 1
        if record.get('n_transitions') is not None \
                and int(record.get('n_transitions')) != geometry['transition_parts_count']:
            warnings.append(f'{tag}: route {record.get("route_id")} '
                            f'n_transitions={record.get("n_transitions")} but '
                            f'{geometry["transition_parts_count"]} transition parts')
        row = dict(
            scheme=scheme,
            n_layers=N_LAYERS_25D,
            route_id=_int(record.get('route_id')),
            plane=record.get('plane'),
            pair=record.get('pair'),
            relation=record.get('relation'),
            status=record.get('status'),
            mode=record.get('mode'),
            lifted=bool(record.get('lifted')),
            travel_layer=record.get('travel_layer'),
            travel_z_mm=_num(record.get('travel_z_mm')),
            n_transitions=_int(record.get('n_transitions')),
            n_transition_parts=geometry['transition_parts_count'],
            flat_length_mm=_round(geometry['flat_length_mm']),
            transition_length_mm=_round(geometry['transition_length_mm']),
            total_length_mm=_round(geometry['total_length_mm']),
            xy_length_mm=_round(geometry['xy_length_mm']),
            z_span_mm=_num(record.get('z_span_mm')),
            flat_parts_count=geometry['flat_parts_count'],
            flat_arc_count=geometry['flat_arc_count'],
            transition_radii_mm=sorted({_round(value)
                                        for value in geometry['transition_radius_values']}),
            transition_theta_deg_total=_round(
                geometry['transition_theta_deg_sum']),
            transition_footprint_mm_total=_round(geometry['transition_footprint_sum_mm']),
            transition_arc_length_mm_total=_round(
                geometry['transition_arc_length_sum_mm']),
            transition_dz_mm=geometry['transition_dz_mm'],
            total_length_check_mm=_round(record.get('length_mm')),
        )
        per_route_rows.append(row)
    for record in failed:
        per_route_rows.append(dict(
            scheme=scheme,
            n_layers=N_LAYERS_25D,
            route_id=_int(record.get('route_id')),
            plane=record.get('plane'),
            pair=record.get('pair'),
            relation=record.get('relation'),
            status=record.get('status'),
            reason=record.get('reason'),
            mode=None,
            lifted=False,
            travel_layer=None,
            travel_z_mm=None,
            n_transitions=None,
            n_transition_parts=None,
            flat_length_mm=None,
            transition_length_mm=None,
            total_length_mm=None,
            xy_length_mm=None,
            z_span_mm=None,
            flat_parts_count=None,
            flat_arc_count=None,
            transition_radii_mm=None,
            transition_theta_deg_total=None,
            transition_footprint_mm_total=None,
            transition_arc_length_mm_total=None,
            transition_dz_mm=None,
            total_length_check_mm=None,
        ))
    if mismatch_radius:
        warnings.append(f'{tag}: {mismatch_radius} transitions have saved radius '
                        f'different from recomputed radius')
    if mismatch_footprint:
        warnings.append(f'{tag}: {mismatch_footprint} transitions disagree between '
                        f'saved footprint_mm and recomputed 2R*sin(theta)')
    if mismatch_length:
        warnings.append(f'{tag}: {mismatch_length} transitions disagree between '
                        f'saved length_mm and recomputed 2R*theta')
    if mismatch_theta:
        warnings.append(f'{tag}: {mismatch_theta} transitions have missing/'
                        f'inconsistent saved dz_mm')

    validation = validation or dict(present=False)
    crossings_by_layer = validation.get('crossings_by_layer')
    crossings_total = validation.get('crossings_total')
    if crossings_total is None and crossings_by_layer:
        crossings_total = sum(crossings_by_layer.values())
    min_curvature = validation.get('min_curvature_radius_mm')
    expected_min_curvature = EXPECTED_RADIUS_MM * (1.0 - 1e-3)
    records_available = records is not None
    transitions_computed = (sum(count * key for key, count
                                in transitions_per_route.items())
                            if records_available else None)
    stats_view = dict(
        present=bool(records) or bool(stats),
        records_available=records_available,
        routed=len(routed) if records_available else _int(stats.get('routed')),
        failed=(len(failed) if records_available
                else _int(stats.get('failed'))),
        total=len(records) if records_available else _int(stats.get('total')),
        baseline_routed=_int(_pick(stats.get('baseline_routed'),
                                   summary.get('baseline_routed'))),
        new_routed=_int(stats.get('new_routed')),
        lifted=len(lifted) if records_available else _int(stats.get('lifted')),
        flat_added=_int(stats.get('flat_added')),
        transitions=_int(stats.get('transitions')),
        transitions_computed=transitions_computed,
        transitions_per_route=(dict(sorted(transitions_per_route.items()))
                               if records_available else None),
        flat_length_mm=(_round(flat_length) if records_available else None),
        transition_length_mm=(_round(transition_length)
                              if records_available else None),
        total_length_mm=(_round(total_length) if records_available
                         else _num(stats.get('total_length_mm'))),
        total_length_recomputed_from_parts_mm=(_round(total_length)
                                               if records_available else None),
        total_length_saved_mm=_num(stats.get('total_length_mm')),
        mean_length_mm=(_round(_safe_div(total_length, len(routed)))
                        if records_available
                        else _num(stats.get('mean_length_mm'))),
        total_xy_length_mm=_num(stats.get('total_xy_length_mm')),
        transition_radius_distribution=(dict(sorted(
            transition_radius_counter.items(), key=lambda item: float(item[0])))
            if records_available else None),
        transition_dz_distribution_mm=(dict(sorted(transition_dz_counter.items()))
                                       if records_available else None),
        transition_theta_deg_total=(_round(theta_sum)
                                    if records_available else None),
        transition_footprint_mm_total=(_round(footprint_sum)
                                       if records_available else None),
        transition_arc_length_mm_total=(_round(arc_length_sum)
                                        if records_available else None),
        travel_layer_distribution=(dict(sorted(travel_layers.items()))
                                   if records_available else None),
        per_layer_flat_parts=(dict(sorted(flat_parts_per_layer.items(),
                                          key=lambda item: int(item[0])
                                          if item[0].isdigit() else 99))
                              if records_available else None),
        per_layer_flat_parts_saved=stats.get('per_layer_flat_parts'),
        per_plane=_int_per_plane(routed, stats),
        validation=validation,
        crossings_total=crossings_total,
        crossings_by_layer=crossings_by_layer,
        min_3d_distance_mm=validation.get('min_3d_distance_mm'),
        min_3d_distance_excluding_crossings_mm=validation.get(
            'min_3d_distance_excluding_crossings_mm'),
        min_curvature_radius_mm=min_curvature,
        min_curvature_expected_min_mm=round(expected_min_curvature, 9),
        min_curvature_ok=(min_curvature is not None
                          and min_curvature >= expected_min_curvature),
        validation_passed=validation.get('passed'),
        counts=validation.get('counts'),
        radius_expected_mm=EXPECTED_RADIUS_MM,
        all_transitions_expected_radius=(
            bool(transition_radius_counter) and all(
                abs(float(key) - EXPECTED_RADIUS_MM) <= RADIUS_TOL_MM
                for key in transition_radius_counter)
            if records_available else None),
        transition_radius_expectation=dict(
            expected_radius_mm=EXPECTED_RADIUS_MM,
            unexpected_transition_count=sum(
                unexpected_transition_radius_counter.values()),
            unexpected_radius_distribution=dict(sorted(
                unexpected_transition_radius_counter.items(),
                key=lambda item: float(item[0]))),
            routes_with_unexpected_radius=sorted(
                route for route in unexpected_transition_routes
                if route is not None),
        ),
        run_summary_seconds=_num(summary.get('seconds')),
        run_summary_config=summary.get('config') if isinstance(
            summary.get('config'), dict) else None,
        source_routes=_display_path(routes_path) if routes_path.exists() else None,
        source_summary=_display_path(summary_path) if summary_path.exists() else None,
    )
    return stats_view


def _int_per_plane(routed, stats):
    saved = stats.get('per_plane') if isinstance(stats.get('per_plane'), dict) else {}
    result = {}
    for plane in PLANES:
        plane_routed = [record for record in routed if record.get('plane') == plane]
        saved_plane = saved.get(plane) if isinstance(saved.get(plane), dict) else {}
        result[plane] = dict(
            routed=len(plane_routed) if routed else _int(saved_plane.get('routed')),
            baseline=_int(saved_plane.get('baseline')),
            lifted=_int(saved_plane.get('lifted')),
            new=sum(1 for record in plane_routed if not record.get('baseline_2d'))
            if routed else None,
        )
    return result


def _analyse_three_d(root, two_d, warnings, per_route_rows):
    validations = _discover_3d_validations(root, warnings)
    schemes = {}
    for scheme in SCHEMES:
        schemes[scheme] = _analyse_25d_scheme(root, scheme, validations.get(scheme),
                                              warnings, per_route_rows)
    aggregate = dict(
        routed=sum(schemes[scheme].get('routed') or 0 for scheme in SCHEMES),
        lifted=sum(schemes[scheme].get('lifted') or 0 for scheme in SCHEMES),
        transitions=sum(schemes[scheme].get('transitions_computed') or 0
                        for scheme in SCHEMES),
        total_length_mm=_round(sum(
            schemes[scheme].get('total_length_mm') or 0.0 for scheme in SCHEMES)),
        validations_passed=[scheme for scheme in SCHEMES
                            if schemes[scheme].get('validation_passed') is True],
        validations_present=[scheme for scheme in SCHEMES
                             if (schemes[scheme].get('validation') or {}).get(
                                 'present')],
    )
    return dict(schemes=schemes, aggregate=aggregate)


# ---------------------------------------------------------------------------
# loss parameters
# ---------------------------------------------------------------------------
def _loss_parameters(two_d, three_d):
    process = two_d.get('process') if isinstance(two_d.get('process'), dict) else {}
    radius = _num(process.get('radius_mm'))
    propagation = _num(process.get('propagation_loss_db_per_cm'))
    parameters = dict(
        propagation_loss=dict(
            parameter='propagation_loss',
            value_db_per_cm=_pick(propagation, PROPAGATION_LOSS_DB_PER_CM),
            status='experimental_convention_not_measured',
            measured=False,
            source=('fslw.config experiment convention (PROPAGATION_LOSS_DB_PER_CM) '
                    'as documented in README_R15 §5'),
            note='length-only experiment convention; not a measured glass value',
        ),
        bend_loss=dict(
            parameter='bend_loss',
            value=None,
            status='unknown_uncalibrated',
            measured=False,
            source='not available in this round',
            note=('no calibrated femtosecond-laser-written glass bend-loss function; '
                  'R=15 mm is a geometry constraint only, not a measured loss value'),
        ),
        crossing_loss=dict(
            parameter='crossing_loss',
            value=None,
            status='unknown_uncalibrated',
            measured=False,
            source='not available in this round',
            note=('single-layer crossing optical feasibility not confirmed; '
                  'crossing counts are geometric metrics only'),
        ),
        interlayer_effect=dict(
            parameter='interlayer_effect',
            value=None,
            status='unknown_uncalibrated',
            measured=False,
            source='not available in this round',
            note=('effect of the two 3D elevation S-curves / interlayer travel on '
                  'loss is not calibrated'),
        ),
    )
    scope_inputs = {}
    for label in SCHEMES:
        totals = two_d['labels'][label]['totals']
        geometry = totals.get('geometry') or {}
        scope_inputs[f'2d_{label}'] = dict(
            routed=totals.get('routed'),
            failed=totals.get('failed'),
            total_length_mm=totals.get('total_length_mm'),
            total_length_cm=_round(_safe_div(totals.get('total_length_mm'), 10.0)),
            arc_count=totals.get('arc_count'),
            short_s_arc_count=totals.get('short_s_arc_count'),
            crossing_count=totals.get('crossing_count'),
            min_radius_mm=geometry.get('min_radius_mm'),
        )
    for scheme in SCHEMES:
        entry = three_d['schemes'][scheme]
        scope_inputs[f'25d_{scheme}'] = dict(
            routed=entry.get('routed'),
            failed=entry.get('failed'),
            lifted=entry.get('lifted'),
            transitions=entry.get('transitions_computed'),
            flat_length_mm=entry.get('flat_length_mm'),
            transition_length_mm=entry.get('transition_length_mm'),
            total_length_mm=entry.get('total_length_mm'),
            total_length_cm=_round(_safe_div(entry.get('total_length_mm'), 10.0)),
            transition_radius_distribution=entry.get(
                'transition_radius_distribution'),
            crossing_count=entry.get('crossings_total'),
            min_curvature_radius_mm=entry.get('min_curvature_radius_mm'),
        )
    payload = dict(
        schema=SCHEMA_LOSS,
        generated_utc=_now_utc(),
        round='R15',
        radius_requirement=dict(
            required_radius_mm=EXPECTED_RADIUS_MM,
            detected_process_radius_mm=radius,
            radius_ok=(abs(radius - EXPECTED_RADIUS_MM) <= RADIUS_TOL_MM
                       if radius is not None else None),
            fixed_radius_40mm=process.get('fixed_radius_40mm'),
            process_profile=process.get('process_profile'),
            source=process.get('source') if isinstance(process.get('source'), str)
            else None,
            note=('the R15 process requirement is a fixed minimum curvature radius '
                  f'R = {EXPECTED_RADIUS_MM} mm for every planar bend and every 3D '
                  'elevation S-curve'),
        ),
        guidance=('No new loss coefficients are introduced in this round. Only the '
                  'propagation-loss experiment convention is listed as a known '
                  'parameter; bend / crossing / interlayer losses are unknown and '
                  'uncalibrated. No total-loss conclusion is produced.'),
        parameters=parameters,
        total_loss_conclusion=dict(
            produced=False,
            reason=('bend loss, crossing loss and interlayer effects are all '
                    'unknown_uncalibrated; a total-loss number would require invented '
                    'coefficients, therefore none is reported this round'),
        ),
        legacy_r40_polymer_model=dict(
            used=False,
            note=('the historical polymer bend-loss estimate belongs to the R40 '
                  'round and is not carried into R15 numbers'),
        ),
        length_and_count_inputs_only=scope_inputs,
        note=('lengths, arc counts and crossing counts are reported here only as '
              'geometric inputs. They are deliberately NOT converted into a total '
              'loss: that would require the unknown bend/crossing/interlayer '
              'coefficients. The single known parameter is the propagation-loss '
              'experiment convention 0.05 dB/cm (not measured).'),
    )
    return payload


# ---------------------------------------------------------------------------
# R40 vs R15 comparison
# ---------------------------------------------------------------------------
def _comparison(two_d, three_d):
    rows = []
    definitions = (
        ('2d_d56_short_s', '2D D56 (Short-S), A', '2d_A', '2d', 'A'),
        ('2d_ortho90', '2D pure orthogonal 90°, B', '2d_B', '2d', 'B'),
        ('25d_short_s', '5L 2.5D + Short-S, A', '25d_A', '25d', 'A'),
        ('25d_ortho90', '5L 2.5D + pure orthogonal, B', '25d_B', '25d', 'B'),
    )
    for key, label, r40_key, kind, scheme in definitions:
        r40 = R40_COMPARISON[r40_key]
        if kind == '2d':
            totals = two_d['labels'][scheme]['totals']
            geometry = totals.get('geometry') or {}
            r15 = totals.get('routed')
            extra = dict(
                r15_failed=totals.get('failed'),
                r15_total_length_mm=totals.get('total_length_mm'),
                r15_arc_count=totals.get('arc_count'),
                r15_quarter_arc_count=totals.get('quarter_arc_count'),
                r15_short_s_arc_count=totals.get('short_s_arc_count'),
                r15_crossing_count=totals.get('crossing_count'),
                r15_min_curvature_radius_mm=geometry.get('min_radius_mm'),
            )
        else:
            entry = three_d['schemes'][scheme]
            r15 = entry.get('routed')
            extra = dict(
                r15_failed=entry.get('failed'),
                r15_total_length_mm=entry.get('total_length_mm'),
                r15_arc_count=None,
                r15_quarter_arc_count=None,
                r15_short_s_arc_count=None,
                r15_crossing_count=entry.get('crossings_total'),
                r15_min_curvature_radius_mm=entry.get('min_curvature_radius_mm'),
                r15_lifted=entry.get('lifted'),
                r15_transitions=entry.get('transitions_computed'),
            )
        rows.append(dict(
            key=key,
            label=label,
            scheme=scheme,
            kind=kind,
            r40_routed=r40,
            r15_routed=r15,
            delta=(r15 - r40) if (r15 is not None and r40 is not None) else None,
            r15_present=r15 is not None,
            **extra,
        ))
    return dict(
        schema=SCHEMA_COMPARISON,
        generated_utc=_now_utc(),
        round='R15',
        r40_constants=dict(R40_COMPARISON),
        note=R40_NOTE,
        rows=rows,
    )


# ---------------------------------------------------------------------------
# markdown renderers
# ---------------------------------------------------------------------------
def _render_statistics_md(statistics):
    two_d = statistics['two_d']
    three_d = statistics['three_d']
    losses = statistics['loss_parameters']
    lines = [
        '# R15 轮统计报告（自动生成）',
        '',
        f'- 生成时间（UTC）：{statistics["generated_utc"]}',
        f'- 数据根目录：`{statistics["root"]}`',
        f'- 生成脚本：`four_side_1024/r15/stats_r15.py`（只读输入，不修改任何路由数据）',
        f'- 工艺要求：所有平面弯曲与 3D 升降弯曲 **R = {statistics["radius_mm"]} mm**'
        '（R15 本轮要求；R40 结果不在本文件混合）',
        '',
        '## 1. 数据状态',
        '',
    ]
    present_rows = []
    for label in SCHEMES:
        for plane in PLANES:
            entry = two_d['labels'][label]['planes'][plane]
            present_rows.append([f'planes/V2/{label}/{plane}', 
                                 '已生成' if entry.get('present') else '缺失'])
        combined = two_d['labels'][label]['combined']
        present_rows.append([f'combined/V2/{label}', 
                             '已生成' if combined.get('present') else '缺失'])
    for scheme in SCHEMES:
        entry = three_d['schemes'][scheme]
        present_rows.append([f'25d/scheme{scheme}/layers5',
                             '已生成' if entry.get('present') else '缺失'])
        present_rows.append([f'25d validation {scheme}',
                             '已生成' if (entry.get('validation') or {}).get('present')
                             else '缺失'])
    lines.extend(_md_table(['输入', '状态'], 
                           present_rows, ['---', '---']))
    lines.append('')
    if statistics.get('warnings'):
        lines.append(f'> 警告 {len(statistics["warnings"])} 条（详见 '
                     '`r15_statistics.json` 的 `warnings` 字段）：')
        for warning in statistics['warnings'][:12]:
            lines.append(f'> - {warning}')
        if len(statistics['warnings']) > 12:
            lines.append(f'> - ... 其余 {len(statistics["warnings"]) - 12} 条')
        lines.append('')

    lines.extend([
        '## 2. 二维（R15）统计',
        '',
        '### 2.1 平面汇总（由图元重算）',
        '',
    ])
    headers = ['方案', '平面', '布通/总数', '失败', '总长 mm', '平均长 mm',
               '直线长 mm', '弧长 mm', '弧数', '90°弧', '短S弧', '最小半径 mm',
               '同层交叉', '非R15弧数', 'R15 验收']
    aligns = ['---', '---', '---:', '---:', '---:', '---:', '---:', '---:',
              '---:', '---:', '---:', '---:', '---:', '---:', '---']
    rows = []
    for label in SCHEMES:
        for plane in PLANES:
            entry = two_d['labels'][label]['planes'][plane]
            if not entry.get('present'):
                rows.append([label, plane] + [DASH] * (len(headers) - 2))
                continue
            geometry = entry.get('geometry') or {}
            audit = entry.get('audit') or {}
            expectation = entry.get('radius_expectation') or {}
            rows.append([
                label, plane,
                f'{_fmt_int(entry.get("routed"))}/'
                f'{_fmt_int(entry.get("total"))}',
                _fmt_int(entry.get('failed')),
                _fmt_num(geometry.get('total_length_mm'), 3),
                _fmt_num(geometry.get('mean_length_mm'), 3),
                _fmt_num(geometry.get('straight_length_mm'), 3),
                _fmt_num(geometry.get('arc_length_mm'), 3),
                _fmt_int(geometry.get('arc_count')),
                _fmt_int(geometry.get('quarter_arc_count')),
                _fmt_int(geometry.get('short_s_arc_count')),
                _fmt_num(geometry.get('min_radius_mm'), 6),
                _fmt_int(entry.get('crossing_count')),
                _fmt_int(expectation.get('unexpected_arc_count')),
                _pass_fail(entry.get('validation_passed')),
            ])
    lines.extend(_md_table(headers, rows, aligns))
    lines.append('')
    validation_2d = two_d.get('validation_2d') or {}
    validation_2d_text = (_pass_fail(validation_2d.get('passed'))
                          if validation_2d.get('present') else DASH)
    lines.append(f'- 2D 独立 strict 验收：{validation_2d_text}'
                 f'（{validation_2d.get("source") or DASH}）')
    lines.append('- 逐波导 2D 明细见 `r15_per_waveguide_2d.csv`（按 4 个平面各 512 条'
                 '列出，含失败记录；组合 1024 = 两平面并集，不重复输出）。')
    lines.append('')

    lines.extend([
        '### 2.2 组合 1024 通道（A/B 标签）',
        '',
        '| 方案 | 布通/总数 | 失败 | 总长 mm | 总弧数 | 90°弧 | 短S弧 | '
        '同层交叉(两平面和) | combined 验收 | 说明 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---|---|',
    ])
    for label in SCHEMES:
        totals = two_d['labels'][label]['totals']
        combined_validation = two_d['labels'][label].get(
            'r15_validation_combined') or {}
        lines.append(
            f'| {label} | {_fmt_int(totals.get("routed"))}/'
            f'{_fmt_int(totals.get("total"))} | {_fmt_int(totals.get("failed"))} | '
            f'{_fmt_num(totals.get("total_length_mm"), 3)} | '
            f'{_fmt_int(totals.get("arc_count"))} | '
            f'{_fmt_int(totals.get("quarter_arc_count"))} | '
            f'{_fmt_int(totals.get("short_s_arc_count"))} | '
            f'{_fmt_int(totals.get("crossing_count"))} | '
            f'{_pass_fail(combined_validation.get("passed"))} | '
            f'{totals.get("source") or DASH} |')
    lines.append('')
    lines.extend([
        '### 2.3 弧半径 / 转角分布',
        '',
        '| 方案 | 标签范围 | 半径分布 | 90° 弧 | 短S弧 | 短S 平均转角° | '
        '短S 弧长 mm | 90° 弧长 mm |',
        '|---|---|---|---:|---:|---:|---:|---:|',
    ])
    for label in SCHEMES:
        totals = two_d['labels'][label]['totals']
        geometry = totals.get('geometry') or None
        if not geometry:
            lines.append(f'| {label} | {DASH} | {DASH} | {DASH} | {DASH} | {DASH} | '
                         f'{DASH} | {DASH} |')
            continue
        lines.append(
            f'| {label} | {_fmt_num(geometry.get("min_radius_mm"), 6)} – '
            f'{_fmt_num(geometry.get("max_radius_mm"), 6)} | '
            f'{geometry.get("radius_distribution") or DASH} | '
            f'{_fmt_int(geometry.get("quarter_arc_count"))} | '
            f'{_fmt_int(geometry.get("short_s_arc_count"))} | '
            f'{_fmt_num(geometry.get("short_s_mean_sweep_deg"), 3)} | '
            f'{_fmt_num(geometry.get("short_s_arc_length_mm"), 3)} | '
            f'{_fmt_num(geometry.get("quarter_arc_length_mm"), 3)} |')
    lines.append('')
    lines.append('> 2.3 的几何来源：' + '；'.join(
        f'方案 {label}: {two_d["labels"][label]["totals"].get("geometry_source") or DASH}'
        for label in SCHEMES))
    lines.append('')
    radius_anomalies = []
    for label in SCHEMES:
        for plane in PLANES:
            entry = two_d['labels'][label]['planes'][plane]
            expectation = entry.get('radius_expectation') or {}
            if expectation.get('unexpected_arc_count'):
                radius_anomalies.append(
                    f'- **半径异常 {label}/{plane}**：'
                    f'{_fmt_int(expectation.get("unexpected_arc_count"))} 条弧的半径不是 '
                    f'R={EXPECTED_RADIUS_MM} mm（分布 '
                    f'{expectation.get("unexpected_radius_distribution")}，涉及 '
                    f'{len(expectation.get("routes_with_unexpected_radius") or [])} 条路由，'
                    f'前 10 个 id：'
                    f'{(expectation.get("routes_with_unexpected_radius") or [])[:10]}）')
    if radius_anomalies:
        lines.extend(radius_anomalies)
        lines.append('')

    lines.extend([
        '## 3. 三维（R15 五层 2.5D）统计',
        '',
        '| 方案 | 布通 | 失败 | 抬升 | 升降次数 | flat 长 mm | transition 长 mm | '
        '总长 mm | theta 总计° | footprint 总计 mm | transition 弧长总计 mm | '
        '半径分布 | 验收 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|',
    ])
    for scheme in SCHEMES:
        entry = three_d['schemes'][scheme]
        if not entry.get('present'):
            lines.append(f'| {scheme} | ' + ' | '.join([DASH] * 12) + ' |')
            continue
        lines.append(
            f'| {scheme} | {_fmt_int(entry.get("routed"))} | '
            f'{_fmt_int(entry.get("failed"))} | {_fmt_int(entry.get("lifted"))} | '
            f'{_fmt_int(entry.get("transitions_computed"))} | '
            f'{_fmt_num(entry.get("flat_length_mm"), 3)} | '
            f'{_fmt_num(entry.get("transition_length_mm"), 3)} | '
            f'{_fmt_num(entry.get("total_length_mm"), 3)} | '
            f'{_fmt_num(entry.get("transition_theta_deg_total"), 3)} | '
            f'{_fmt_num(entry.get("transition_footprint_mm_total"), 3)} | '
            f'{_fmt_num(entry.get("transition_arc_length_mm_total"), 3)} | '
            f'{entry.get("transition_radius_distribution") or DASH} | '
            f'{_pass_fail(entry.get("validation_passed"))} |')
    lines.append('')
    lines.extend([
        '### 3.1 逐层 flat 段与旅行层分布',
        '',
        '| 方案 | 每层 flat 段 | travel layer 分布 | 每路线 transition 数分布 |',
        '|---|---|---|---|',
    ])
    for scheme in SCHEMES:
        entry = three_d['schemes'][scheme]
        if not entry.get('present'):
            lines.append(f'| {scheme} | {DASH} | {DASH} | {DASH} |')
            continue
        lines.append(
            f'| {scheme} | {entry.get("per_layer_flat_parts") or DASH} | '
            f'{entry.get("travel_layer_distribution") or DASH} | '
            f'{entry.get("transitions_per_route") or DASH} |')
    lines.append('')
    lines.extend([
        '### 3.2 三维独立验收（validate_r15 / fsd25d.validate25d，R15 概况）',
        '',
        '| 方案 | 验收 | 同层交叉(各层和) | 各层交叉 | 最小 3D 距离 mm | '
        '最小曲率半径 mm | 曲率达标(≥14.985) | 违规计数 |',
        '|---|---|---:|---|---:|---:|---|---|',
    ])
    for scheme in SCHEMES:
        entry = three_d['schemes'][scheme]
        validation = entry.get('validation') or {}
        if not validation.get('present'):
            lines.append(f'| {scheme} | ' + ' | '.join([DASH] * 7) + ' |')
            continue
        counts = validation.get('counts') or {}
        counts_nonzero = {key: value for key, value in counts.items()
                          if value not in (0, None)}
        lines.append(
            f'| {scheme} | {_pass_fail(validation.get("passed"))} | '
            f'{_fmt_int(entry.get("crossings_total"))} | '
            f'{entry.get("crossings_by_layer") or DASH} | '
            f'{_fmt_num(entry.get("min_3d_distance_excluding_crossings_mm"), 9)} | '
            f'{_fmt_num(entry.get("min_curvature_radius_mm"), 9)} | '
            f'{_yes_no(entry.get("min_curvature_ok"))} | '
            f'{counts_nonzero if counts_nonzero else "全部 0"} |')
    lines.append('')
    transition_anomalies = []
    for scheme in SCHEMES:
        entry = three_d['schemes'][scheme]
        expectation = entry.get('transition_radius_expectation') or {}
        if expectation.get('unexpected_transition_count'):
            transition_anomalies.append(
                f'- **升降半径异常 {scheme}**：'
                f'{_fmt_int(expectation.get("unexpected_transition_count"))} 段 '
                f'transition 半径不是 R={EXPECTED_RADIUS_MM} mm（分布 '
                f'{expectation.get("unexpected_radius_distribution")}，涉及 '
                f'{len(expectation.get("routes_with_unexpected_radius") or [])} 条路由）')
    if transition_anomalies:
        lines.extend(transition_anomalies)
        lines.append('')
    lines.append('## 4. 损耗参数口径（不输出总损耗结论）')
    lines.append('')
    radius_requirement = losses.get('radius_requirement') or {}
    lines.append(
        f'- 半径要求：R = {radius_requirement.get("required_radius_mm") or DASH} mm；'
        f'检测到 process radius = '
        f'{_fmt_num(radius_requirement.get("detected_process_radius_mm"), 6)} mm；'
        f'达标 = {_yes_no(radius_requirement.get("radius_ok"))}')
    lines.append('')
    lines.extend([
        '| 参数 | 值 | 状态 | 已标定 | 说明 |',
        '|---|---|---|---|---|',
    ])
    for key, parameter in losses['parameters'].items():
        value_db = parameter.get('value_db_per_cm')
        value_text = (f'{value_db} dB/cm' if value_db is not None else DASH)
        lines.append(
            f'| {parameter.get("parameter")} | {value_text} '
            f'| {parameter.get("status")} | {parameter.get("measured")} | '
            f'{parameter.get("note")} |')
    lines.append('')
    lines.append('> **本轮不输出总损耗结论。** 弯曲损耗、交叉损耗、层间影响均为 '
                 '`unknown_uncalibrated`；质量上唯一的已知参数是传播损耗实验约定 '
                 '`0.05 dB/cm`（非实测标定）。若需要损耗预算，必须先由实验标定 '
                 '弯曲/交叉/层间系数。')
    lines.append('')
    return '\n'.join(lines) + '\n'


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


def _render_comparison_md(comparison):
    lines = [
        '# R40 vs R15 对照表（自动生成）',
        '',
        f'- 生成时间（UTC）：{comparison["generated_utc"]}',
        f'- 说明：{comparison["note"]}',
        '',
        '## 1. 布通数对照',
        '',
        '| 配置 | R40 布通 | R15 布通 | Δ (R15−R40) | R15 失败 | '
        'R15 总长 mm | R15 同层交叉 | R15 最小半径/曲率 mm |',
        '|---|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for row in comparison['rows']:
        lines.append(
            f'| {row["label"]} | {_fmt_int(row.get("r40_routed"))} | '
            f'{_fmt_int(row.get("r15_routed"))} | {_fmt_delta(row.get("delta"))} | '
            f'{_fmt_int(row.get("r15_failed"))} | '
            f'{_fmt_num(row.get("r15_total_length_mm"), 3)} | '
            f'{_fmt_int(row.get("r15_crossing_count"))} | '
            f'{_fmt_num(row.get("r15_min_curvature_radius_mm"), 9)} |')
    lines.append('')
    lines.extend([
        '## 2. 说明',
        '',
        '- R40 列只有冻结的历史布通数（2D D56 = 752、2D 纯正交 = 262、'
        '5L 2.5D+Short-S = 820、5L 2.5D+纯正交 = 383），不包含任何 R40 几何/长度/'
        '损耗数值；R15 列全部由本轮 R15 产物重算。',
        '- R15 工艺要求：所有平面弯曲与 3D 升降曲线固定 R = 15 mm；'
        '2D 行“最小半径/曲率”来自图元半径，5L 行来自独立 3D 验收的最小曲率半径。',
        '- 2D R15 布通取自 `combined/V2/{A,B}/routes_1024.json`（若缺失则回退为两平面之和）。',
        '- 5L 2.5D R15 布通取自 `25d/scheme{A,B}/layers5/routes_25d.json`；'
        '其升降曲线半径为 R = 15 mm。',
        '- 因此本表只用于回答“在 R15 工艺约束下布通数相对 R40 基线变化多少”，'
        '不能把两轮的长度/损耗/交叉数直接相除。',
        '',
    ])
    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------------
CSV_2D_FIELDS = [
    'label', 'plane', 'route_id', 'status', 'reason', 'pair', 'relation',
    'length_mm', 'straight_mm', 'arc_mm', 'arc_count', 'bend_count_saved',
    'min_radius_mm', 'radii_mm', 'sweeps_deg', 'short_s', 'short_s_arc_count',
    'short_s_total_sweep_deg', 'short_s_arc_length_mm', 'length_check_mm',
    'family',
]

CSV_3D_FIELDS = [
    'scheme', 'n_layers', 'route_id', 'plane', 'pair', 'relation', 'status',
    'reason', 'mode', 'lifted', 'travel_layer', 'travel_z_mm', 'n_transitions',
    'n_transition_parts', 'flat_length_mm', 'transition_length_mm',
    'total_length_mm', 'xy_length_mm', 'z_span_mm', 'flat_parts_count',
    'flat_arc_count', 'transition_radii_mm', 'transition_theta_deg_total',
    'transition_footprint_mm_total', 'transition_arc_length_mm_total',
    'transition_dz_mm', 'total_length_check_mm',
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
# analysis entry point
# ---------------------------------------------------------------------------
def collect(root, log=print):
    root = Path(root)
    warnings = []
    per_route_2d = []
    per_route_3d = []
    two_d = _analyse_two_d(root, warnings, per_route_2d)
    three_d = _analyse_three_d(root, two_d, warnings, per_route_3d)
    losses = _loss_parameters(two_d, three_d)
    comparison = _comparison(two_d, three_d)
    statistics = dict(
        schema=SCHEMA_STATISTICS,
        generated_utc=_now_utc(),
        generator='four_side_1024.r15.stats_r15',
        python_version=sys.version.split()[0],
        root=_display_path(root),
        root_abs=str(root),
        round='R15',
        radius_mm=EXPECTED_RADIUS_MM,
        process_requirement=('every planar bend and every 3D elevation S-curve uses '
                             'the fixed radius R = 15 mm; supersedes the historical '
                             'R40 convention and the PDF example radii '
                             '(R = 6000/6137.33 um, shape reference only)'),
        r40_policy=('R40 results are kept separately; the only place they appear in '
                    'this R15 module is the explicit comparison table '
                    '(r15_comparison_table.md / comparison_r40_vs_r15).'),
        two_d=two_d,
        three_d=three_d,
        process=two_d.get('process'),
        loss_parameters=losses,
        comparison_r40_vs_r15=comparison,
        per_route_counts=dict(two_d_rows=len(per_route_2d),
                              three_d_rows=len(per_route_3d)),
        warnings=warnings,
    )
    return dict(statistics=statistics, comparison=comparison, losses=losses,
                per_route_2d=per_route_2d, per_route_3d=per_route_3d)


def run(root, log=print):
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f'R15 root not found: {root}')
    started = time.perf_counter()
    result = collect(root, log=log)
    summary_dir = root / 'summary'
    summary_dir.mkdir(parents=True, exist_ok=True)
    statistics = result['statistics']
    comparison = result['comparison']
    losses = result['losses']
    written = []
    written.append(_write_json(summary_dir / 'r15_statistics.json', statistics))
    written.append(_write_text(summary_dir / 'r15_statistics.md',
                               _render_statistics_md(statistics)))
    written.append(_write_text(summary_dir / 'r15_comparison_table.md',
                               _render_comparison_md(comparison)))
    written.append(_write_csv(summary_dir / 'r15_per_waveguide_2d.csv',
                              CSV_2D_FIELDS, result['per_route_2d']))
    written.append(_write_csv(summary_dir / 'r15_per_waveguide_3d.csv',
                              CSV_3D_FIELDS, result['per_route_3d']))
    written.append(_write_json(summary_dir / 'r15_loss_parameters.json', losses))
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


def _console(value, digits=None):
    """ASCII-safe console formatting (avoid CJK dash on GBK consoles)."""
    if value is None:
        return 'n/a'
    if isinstance(value, bool):
        return 'yes' if value else 'no'
    if isinstance(value, float) and digits is not None:
        return f'{value:.{digits}f}'
    return str(value)


def _print_summary(result):
    statistics = result['statistics']
    print(f'[stats_r15] root={statistics["root"]} '
          f'warnings={len(statistics["warnings"])}')
    for label in SCHEMES:
        totals = statistics['two_d']['labels'][label]['totals']
        print(f'[stats_r15] 2D {label}: routed={_console(totals.get("routed"))}/'
              f'{_console(totals.get("total"))} total_length_mm='
              f'{_console(totals.get("total_length_mm"), 3)} arcs='
              f'{_console(totals.get("arc_count"))}')
    for scheme in SCHEMES:
        entry = statistics['three_d']['schemes'][scheme]
        print(f'[stats_r15] 25D {scheme}: routed={_console(entry.get("routed"))} '
              f'lifted={_console(entry.get("lifted"))} transitions='
              f'{_console(entry.get("transitions_computed"))} total_length_mm='
              f'{_console(entry.get("total_length_mm"), 3)} validation='
              f'{_console(_pass_fail(entry.get("validation_passed")))}')
    for warning in statistics['warnings'][:20]:
        print(f'[stats_r15] WARNING: {warning}')
    if len(statistics['warnings']) > 20:
        print(f'[stats_r15] ... {len(statistics["warnings"]) - 20} more warnings')
    for path in result['written']:
        print(f'[stats_r15] written {_display_path(path)}')
    print(f'[stats_r15] done in {result["seconds"]}s')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=None,
                        help='R15 实验输出根目录（默认 '
                             'outputs/four_side_1024_v2_r15_v01）')
    parser.add_argument('--quiet', action='store_true',
                        help='只输出写文件信息')
    args = parser.parse_args(argv)
    root = _resolve_root(args.root)
    if not Path(root).is_dir():
        print(f'[stats_r15] ERROR: root directory not found: {root}')
        return 1
    result = run(root)
    if not args.quiet:
        _print_summary(result)
    else:
        for path in result['written']:
            print(f'[stats_r15] written {_display_path(path)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
