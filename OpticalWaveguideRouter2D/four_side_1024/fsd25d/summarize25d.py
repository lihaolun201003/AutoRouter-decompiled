"""Aggregate statistics of the V2 five-layer (2.5D) experiment.

Usage::

    python -m four_side_1024.fsd25d.summarize25d
    python -m four_side_1024.fsd25d.summarize25d --root outputs/four_side_1024_v2_25d_v01

Reads only experiment artefacts (never modifies route data):

* ``<root>/scheme{A,B}/layers{3,5}/routes_25d.json`` + ``run_summary.json``
* ``<root>/validation/**/*.json`` (optional; independent 3D validation)

Writes::

    <root>/summary/overview.json            per-run statistics + comparison rows
    <root>/summary/comparison_table.md      A/B x layers 3/5 (+2D baseline) table
    <root>/summary/layers_effect.json       3-layer vs 5-layer comparison
    <root>/summary/layers_effect.md         human readable 3 vs 5 answer
    <root>/summary/failed_analysis.json     failures by reason / scheme / plane / layers
    <root>/REPRODUCE_25D.md                 full reproduction command sequence

The script is deliberately tolerant: missing runs / run summaries / validation
files produce ``null`` fields plus a warning, never a crash.  Route data is only
ever read, never rewritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

from . import config25d as CFG

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------
SCHEMES = ('A', 'B')
LAYER_COUNTS = (3, 5)
PLANES = ('z1', 'z2')
TOTAL_ROUTES_PER_RUN = 1024
RUN_KEYS = tuple(f'{scheme}/{n}' for scheme in SCHEMES for n in LAYER_COUNTS)

SCHEMA_SUMMARY = 'four_side_1024_v2_25d_summary_v1'
SCHEMA_LAYERS_EFFECT = 'four_side_1024_v2_25d_layers_effect_v1'
SCHEMA_FAILED_ANALYSIS = 'four_side_1024_v2_25d_failed_analysis_v1'
VALIDATION_SCHEMA = 'four_side_1024_v2_25d_validation_v1'

# Reproduce-document command templates.  The modules are the sibling CLIs of
# this package; they are referenced by name only (no import), so this summary
# keeps working when they are absent.  Both CLIs default to --root
# outputs/four_side_1024_v2_25d_v01; the flag is passed explicitly here so the
# documented command is unambiguous.
VALIDATE_MODULE = 'four_side_1024.fsd25d.validate25d'
VALIDATE_EXTRA_ARGS = ' --root outputs/four_side_1024_v2_25d_v01'
PLOTS_MODULE = 'four_side_1024.fsd25d.plots25d'
PLOTS_EXTRA_ARGS = ' --root outputs/four_side_1024_v2_25d_v01'

REASON_NO_2D = 'no_2d_candidate'
REASON_NO_LIFT = 'no_lift_candidate'

DASH = '—'
NO_2D_DEFINITION = (
    'no_2d_candidate = the frozen 2D baseline had no legal 2D XY candidate at all '
    '(route was in router.no_candidate); no_lift_candidate = a 2D candidate exists '
    'but no legal 2.5D placement (flat or lifted) was found'
)

GAIN_KEYS = ('routed', 'new_routed', 'lifted', 'flat_added', 'transitions',
             'total_length_mm', 'mean_length_mm', 'failed_total',
             'failed_no_candidate', 'failed_unplaceable',
             'flattened_crossings_2d', 'crossings_avoided')


# ---------------------------------------------------------------------------
# generic helpers
# ---------------------------------------------------------------------------
def _now_utc():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def _display_path(path):
    """Project-relative POSIX-style path when possible."""
    path = Path(path)
    try:
        return str(path.resolve().relative_to(CFG.ROOT.resolve())).replace('\\', '/')
    except (ValueError, OSError):
        return str(path).replace('\\', '/')


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _pick(*values):
    for value in values:
        if value is not None:
            return value
    return None


def _pick_int(*values):
    value = _pick(*values)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _pick_float(*values):
    value = _pick(*values)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _same_number(first, second, rel=1e-6):
    if first is None or second is None:
        return True
    return abs(float(first) - float(second)) <= rel * max(1.0, abs(float(second)))


def _delta_float(new, old):
    if new is None or old is None:
        return None
    return round(float(new) - float(old), 6)


def _delta_int(new, old):
    if new is None or old is None:
        return None
    return int(new) - int(old)


def _load_json(path, warnings, what, required=True):
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


def _fmt_int(value):
    if value is None:
        return DASH
    return f'{int(value):,}'


def _fmt_num(value, digits=2):
    if value is None:
        return DASH
    return f'{float(value):,.{digits}f}'


def _fmt_delta(value):
    if value is None:
        return DASH
    if isinstance(value, float):
        return f'{value:+,.6f}'
    return f'{int(value):+d}'


def _md_table(headers, rows, aligns=None):
    aligns = list(aligns or [])
    if not aligns:
        aligns = ['---'] * len(headers)
    lines = ['| ' + ' | '.join(str(item) for item in headers) + ' |',
             '|' + '|'.join(aligns) + '|']
    for row in rows:
        lines.append('| ' + ' | '.join(str(item) for item in row) + ' |')
    return lines


def _normalise_passed(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().upper()
    if text in ('PASS', 'PASSED', 'TRUE', 'OK'):
        return True
    if text in ('FAIL', 'FAILED', 'FALSE'):
        return False
    return None


def _verdict_text(run):
    validation = (run or {}).get('validation') or {}
    if not validation.get('present'):
        return DASH
    passed = validation.get('passed')
    if passed is True:
        return 'PASS'
    if passed is False:
        return 'FAIL'
    return '未知'


# ---------------------------------------------------------------------------
# route-record level metrics (authoritative data; used as fallback + forensics)
# ---------------------------------------------------------------------------
def _compute_route_metrics(records):
    routed = [record for record in records
              if isinstance(record, dict) and record.get('status') == 'routed']
    failed = [record for record in records
              if isinstance(record, dict) and record.get('status') != 'routed']
    reasons = Counter(str(record.get('reason') or 'unknown') for record in failed)

    transitions = 0
    total_length = 0.0
    total_xy_length = 0.0
    per_layer = Counter()
    for record in routed:
        transitions += int(record.get('n_transitions') or 0)
        total_length += float(record.get('length_mm') or 0.0)
        total_xy_length += float(record.get('xy_length_mm') or 0.0)
        for part in record.get('parts') or []:
            if not isinstance(part, dict) or part.get('kind') != 'flat':
                continue
            layer = part.get('layer')
            layer = int(layer) if layer is not None else 0
            per_layer[layer] += 1

    per_plane = {}
    for plane in PLANES:
        plane_routed = [record for record in routed if record.get('plane') == plane]
        plane_failed = [record for record in failed if record.get('plane') == plane]
        per_plane[plane] = dict(
            routed=len(plane_routed),
            baseline=sum(1 for record in plane_routed if record.get('baseline_2d')),
            lifted=sum(1 for record in plane_routed if record.get('lifted')),
            new=sum(1 for record in plane_routed if not record.get('baseline_2d')),
            failed=len(plane_failed),
            failed_no_candidate=sum(1 for record in plane_failed
                                    if record.get('reason') == REASON_NO_2D),
            failed_no_lift_candidate=sum(1 for record in plane_failed
                                         if record.get('reason') == REASON_NO_LIFT),
        )

    baseline_count = sum(1 for record in routed if record.get('baseline_2d'))
    lifted_count = sum(1 for record in routed if record.get('lifted'))
    return dict(
        total=len(records),
        routed=len(routed),
        failed=len(failed),
        baseline_routed=baseline_count,
        new_routed=len(routed) - baseline_count,
        lifted=lifted_count,
        flat_added=len(routed) - baseline_count - lifted_count,
        transitions=transitions,
        total_length_mm=round(total_length, 6),
        mean_length_mm=(round(total_length / len(routed), 6) if routed else None),
        total_xy_length_mm=round(total_xy_length, 6),
        failed_no_candidate=reasons.get(REASON_NO_2D, 0),
        failed_no_lift_candidate=reasons.get(REASON_NO_LIFT, 0),
        reason_counts=dict(reasons),
        per_plane=per_plane,
        per_layer_flat_parts=dict(per_layer),
    )


def _failure_forensics(records):
    """Failure breakdown + the per-route data needed to list failed routes."""
    failed = [record for record in records
              if isinstance(record, dict) and record.get('status') != 'routed']
    reasons = Counter(str(record.get('reason') or 'unknown') for record in failed)

    no_2d = [record for record in failed if record.get('reason') == REASON_NO_2D]
    no_lift = [record for record in failed if record.get('reason') == REASON_NO_LIFT]
    other = [record for record in failed
             if record.get('reason') not in (REASON_NO_2D, REASON_NO_LIFT)]

    def _ids(records_):
        return sorted(int(record['route_id']) for record in records_
                      if record.get('route_id') is not None)

    by_pair = {}
    by_plane = {}
    for plane in PLANES:
        plane_failed = [record for record in failed if record.get('plane') == plane]
        by_plane[plane] = dict(
            failed_total=len(plane_failed),
            no_2d_candidate=sum(1 for record in plane_failed
                                if record.get('reason') == REASON_NO_2D),
            no_lift_candidate=sum(1 for record in plane_failed
                                  if record.get('reason') == REASON_NO_LIFT),
            other=sum(1 for record in plane_failed
                      if record.get('reason') not in (REASON_NO_2D, REASON_NO_LIFT)),
        )
        pair_map = {}
        for record in plane_failed:
            pair = str(record.get('pair') or 'unknown')
            entry = pair_map.setdefault(pair, dict(failed=0, no_2d_candidate=0,
                                                   no_lift_candidate=0, other=0))
            entry['failed'] += 1
            reason = record.get('reason')
            if reason == REASON_NO_2D:
                entry['no_2d_candidate'] += 1
            elif reason == REASON_NO_LIFT:
                entry['no_lift_candidate'] += 1
            else:
                entry['other'] += 1
        by_pair[plane] = pair_map

    info = []
    for record in failed:
        info.append(dict(
            route_id=record.get('route_id'),
            plane=record.get('plane'),
            pair=record.get('pair'),
            relation=record.get('relation'),
            reason=record.get('reason') or 'unknown',
            baseline_2d=record.get('baseline_2d'),
            interface_layer=record.get('interface_layer'),
        ))
    info.sort(key=lambda item: (str(item.get('plane')), int(item.get('route_id') or 0)))

    return dict(
        failed_total=len(failed),
        reason_counts=dict(reasons),
        no_2d_route_ids=_ids(no_2d),
        no_lift_route_ids=_ids(no_lift),
        other_route_ids_by_reason=dict(Counter(
            str(record.get('reason') or 'unknown') for record in other)),
        other_route_ids=_ids(other),
        by_plane=by_plane,
        by_pair=by_pair,
        failed_route_info=info,
    )


# ---------------------------------------------------------------------------
# run loading
# ---------------------------------------------------------------------------
def _empty_run_entry(scheme, n_layers):
    return dict(
        present=False,
        scheme=scheme,
        scheme_label=(CFG.SCHEMES.get(scheme) or {}).get('label'),
        n_layers=int(n_layers),
        xy_model=None,
        total=None,
        baseline_routed=None,
        original_2d_routed=None,
        routed=None,
        routed_25d=None,
        new_routed=None,
        lifted=None,
        flat_added=None,
        transitions=None,
        total_length_mm=None,
        mean_length_mm=None,
        total_xy_length_mm=None,
        failed_total=None,
        failed_no_candidate=None,
        failed_unplaceable=None,
        failed_attempted_not_placed=None,
        attemptable=None,
        no_candidate=None,
        per_plane=None,
        per_layer_flat_parts=None,
        five_layer_routed=None,
        five_layer_run=None,
        success_rate=None,
        crossings_total=None,
        crossings_by_layer=None,
        flattened_crossings_2d=None,
        crossings_avoided=None,
        flattened_crossings_per_plane=None,
        crossing_metrics_source=None,
        clearance_violations=None,
        curvature_violations=None,
        total_violations=None,
        min_3d_distance_mm=None,
        min_3d_distance_excluding_crossings_mm=None,
        min_3d_distance_including_crossings_mm=None,
        min_curvature_radius_mm=None,
        validation_runtime_seconds=None,
        validation_passed=None,
        validation_present=False,
        validation=None,
        csv_sha256=None,
        process=None,
        layers_z_mm=None,
        interface_layer=None,
        config=None,
        run_command=None,
        seconds=None,
        routes_file=None,
        run_summary_file=None,
        warnings=[],
    )


def _normalise_per_plane(stats_per_plane, computed_per_plane):
    result = {}
    for plane in PLANES:
        stat_pp = (stats_per_plane or {}).get(plane) or {}
        comp_pp = (computed_per_plane or {}).get(plane) or {}
        result[plane] = dict(
            routed=_pick_int(stat_pp.get('routed'), comp_pp.get('routed')),
            baseline=_pick_int(stat_pp.get('baseline'),
                               stat_pp.get('baseline_routed'),
                               comp_pp.get('baseline')),
            lifted=_pick_int(stat_pp.get('lifted'), comp_pp.get('lifted')),
            new=_pick_int(comp_pp.get('new')),
            failed=_pick_int(comp_pp.get('failed')),
            failed_no_candidate=_pick_int(comp_pp.get('failed_no_candidate')),
            failed_no_lift_candidate=_pick_int(
                comp_pp.get('failed_no_lift_candidate')),
        )
    return result


def _normalise_layer_parts(value, n_layers):
    result = {str(layer): 0 for layer in range(int(n_layers))}
    found = False
    if isinstance(value, dict):
        for key, count in value.items():
            try:
                layer = int(key)
            except (TypeError, ValueError):
                continue
            if 0 <= layer < int(n_layers):
                result[str(layer)] = int(count or 0)
                found = True
    return result if found else None


def _check_statistics_against_records(stats, computed, tag, warnings):
    """Warn when the written statistics disagree with the route records."""
    if not isinstance(stats, dict) or not computed:
        return
    for key in ('routed', 'new_routed', 'lifted', 'flat_added', 'transitions',
                'baseline_routed', 'failed_no_candidate'):
        first = stats.get(key)
        second = computed.get(key)
        if first is None or second is None:
            continue
        if int(first) != int(second):
            warnings.append(f'{tag}: statistics.{key}={first} disagrees with '
                            f'routes records ({second})')
    for key in ('total_length_mm', 'mean_length_mm', 'total_xy_length_mm'):
        first = stats.get(key)
        second = computed.get(key)
        if first is None or second is None:
            continue
        if not _same_number(first, second):
            warnings.append(f'{tag}: statistics.{key}={first} disagrees with '
                            f'routes records ({second})')
    stats_per_plane = stats.get('per_plane')
    computed_per_plane = computed.get('per_plane')
    if isinstance(stats_per_plane, dict) and isinstance(computed_per_plane, dict):
        for plane in PLANES:
            for key in ('routed', 'baseline', 'lifted'):
                first = (stats_per_plane.get(plane) or {}).get(key)
                second = (computed_per_plane.get(plane) or {}).get(key)
                if first is not None and second is not None and int(first) != int(second):
                    warnings.append(f'{tag}: per_plane.{plane}.{key}={first} '
                                    f'disagrees with routes records ({second})')


def _load_run(root, scheme, n_layers):
    """Load one run dir; returns (entry, forensics, payload, summary) tuple."""
    warnings = []
    tag = f'scheme{scheme}/layers{n_layers}'
    run_dir = Path(root) / f'scheme{scheme}' / f'layers{n_layers}'
    routes_path = run_dir / 'routes_25d.json'
    summary_path = run_dir / 'run_summary.json'
    payload = _load_json(routes_path, warnings, f'{tag}/routes_25d.json')
    summary = _load_json(summary_path, warnings, f'{tag}/run_summary.json')

    entry = _empty_run_entry(scheme, n_layers)
    if routes_path.exists():
        entry['routes_file'] = _display_path(routes_path)
    if summary_path.exists():
        entry['run_summary_file'] = _display_path(summary_path)

    if payload is None and summary is None:
        warnings.append(f'{tag}: no run data found (routes_25d.json and '
                        f'run_summary.json missing); all fields set to null')
        entry['warnings'] = warnings
        return entry, None, None, None

    payload = payload if isinstance(payload, dict) else {}
    summary = summary if isinstance(summary, dict) else {}
    records = payload.get('routes')
    if not isinstance(records, list):
        if payload:
            warnings.append(f'{tag}: routes_25d.json has no "routes" list')
        records = None
    computed = _compute_route_metrics(records) if records else None
    forensics = _failure_forensics(records) if records else None

    stats_payload = payload.get('statistics')
    stats_summary = summary.get('statistics')
    if isinstance(stats_payload, dict) and isinstance(stats_summary, dict):
        differing = sorted(key for key in set(stats_payload) | set(stats_summary)
                           if stats_payload.get(key) != stats_summary.get(key))
        if differing:
            warnings.append(f'{tag}: payload.statistics differs from '
                            f'run_summary.statistics at keys {differing}')
    stats = stats_payload if isinstance(stats_payload, dict) else (
        stats_summary if isinstance(stats_summary, dict) else {})
    if not stats and computed is None:
        warnings.append(f'{tag}: neither statistics nor route records available; '
                        f'counts set to null')
    if stats and computed is not None:
        _check_statistics_against_records(stats, computed, tag, warnings)
    if computed is None and stats:
        warnings.append(f'{tag}: route records unavailable; per-route/forensic '
                        f'fields are null')

    totals = computed or {}
    baseline_routed = _pick_int(
        stats.get('baseline_routed'), summary.get('baseline_routed'),
        totals.get('baseline_routed'),
        (CFG.SCHEMES.get(scheme) or {}).get('baseline_routed'))
    routed = _pick_int(stats.get('routed'), totals.get('routed'))
    total = _pick_int(totals.get('total'), TOTAL_ROUTES_PER_RUN)
    failed_total = _pick_int(totals.get('failed'),
                             (total - routed) if (total is not None and routed is not None)
                             else None)
    failed_no_candidate = _pick_int(stats.get('failed_no_candidate'),
                                    totals.get('failed_no_candidate'))
    failed_unplaceable = _pick_int(stats.get('failed_unplaceable'))
    failed_attempted = _pick_int(totals.get('failed_no_lift_candidate'))

    router = summary.get('router') if isinstance(summary.get('router'), dict) else (
        payload.get('router') if isinstance(payload.get('router'), dict) else {})
    config = summary.get('config') if isinstance(summary.get('config'), dict) else (
        payload.get('budget') if isinstance(payload.get('budget'), dict) else None)
    run_command = None
    run_info = payload.get('run')
    if isinstance(run_info, dict) and isinstance(run_info.get('command'), dict):
        run_command = run_info['command']
    seconds = _pick_float(summary.get('seconds'),
                          (run_info or {}).get('seconds') if isinstance(run_info, dict) else None,
                          router.get('seconds'))
    process = payload.get('process') if isinstance(payload.get('process'), dict) else None
    layers_z = payload.get('layers_z_mm') or summary.get('layers_z_mm')
    if layers_z is None:
        layers_z = list(CFG.LAYER_STACKS[int(n_layers)])
    interface_layer = payload.get('interface_layer') or summary.get('interface_layer')
    if interface_layer is None:
        interface_layer = dict(CFG.INTERFACE_LAYER[int(n_layers)])
    csv_sha256 = payload.get('csv_sha256') or summary.get('csv_sha256')

    validation_present = False  # filled after validation discovery
    entry.update(
        present=True,
        scheme_label=payload.get('scheme_label') or summary.get('scheme_label')
        or (CFG.SCHEMES.get(scheme) or {}).get('label'),
        xy_model=payload.get('xy_model'),
        total=total,
        baseline_routed=baseline_routed,
        original_2d_routed=baseline_routed,
        routed=routed,
        routed_25d=routed,
        new_routed=_pick_int(stats.get('new_routed'), totals.get('new_routed')),
        lifted=_pick_int(stats.get('lifted'), totals.get('lifted')),
        flat_added=_pick_int(stats.get('flat_added'), totals.get('flat_added')),
        transitions=_pick_int(stats.get('transitions'), totals.get('transitions')),
        total_length_mm=_pick_float(stats.get('total_length_mm'),
                                    totals.get('total_length_mm')),
        mean_length_mm=_pick_float(stats.get('mean_length_mm'),
                                   totals.get('mean_length_mm')),
        total_xy_length_mm=_pick_float(stats.get('total_xy_length_mm'),
                                       totals.get('total_xy_length_mm')),
        failed_total=failed_total,
        failed_no_candidate=failed_no_candidate,
        failed_unplaceable=failed_unplaceable,
        failed_attempted_not_placed=failed_attempted,
        attemptable=_pick_int(router.get('attemptable')),
        no_candidate=_pick_int(router.get('no_candidate')),
        per_plane=_normalise_per_plane(stats.get('per_plane'),
                                       totals.get('per_plane')),
        per_layer_flat_parts=_normalise_layer_parts(
            _pick(stats.get('per_layer_flat_parts'), totals.get('per_layer_flat_parts')),
            n_layers),
        success_rate=(round(routed / total, 6)
                      if routed is not None and total else None),
        csv_sha256=csv_sha256,
        process=process,
        layers_z_mm=list(layers_z) if isinstance(layers_z, (list, tuple)) else layers_z,
        interface_layer=interface_layer,
        config=config,
        run_command=run_command,
        seconds=seconds,
        validation_present=validation_present,
    )
    limit = (config or {}).get('limit') if isinstance(config, dict) else None
    if limit:
        warnings.append(f'{tag}: debug run with --limit {limit}; failure counts are '
                        f'partial and must not be used in the final report')
    if failed_unplaceable is not None and failed_attempted is not None \
            and failed_unplaceable != failed_attempted and not limit:
        warnings.append(f'{tag}: failed_unplaceable={failed_unplaceable} differs from '
                        f'no_lift_candidate records ({failed_attempted}); using '
                        f'run_summary.statistics as authority')
    entry['warnings'] = warnings
    return entry, forensics, payload, summary


# ---------------------------------------------------------------------------
# independent validation discovery
# ---------------------------------------------------------------------------
def _looks_like_validation_report(payload):
    keys = set(payload)
    has_identity = 'scheme' in keys and 'n_layers' in keys
    has_input = 'input' in keys
    has_verdict = 'passed' in keys
    has_counts = isinstance(payload.get('counts'), dict)
    return bool((has_identity and (has_verdict or has_counts))
                or (has_input and (has_verdict or has_counts)))


def _extract_reports(payload, depth=0):
    reports = []
    if depth > 4:
        return reports
    if isinstance(payload, dict):
        if _looks_like_validation_report(payload):
            return [payload]
        for value in payload.values():
            reports.extend(_extract_reports(value, depth + 1))
    elif isinstance(payload, list):
        for item in payload:
            reports.extend(_extract_reports(item, depth + 1))
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


def _discover_validation_reports(validation_dir, warnings):
    validation_dir = Path(validation_dir)
    if not validation_dir.is_dir():
        warnings.append(f'validation directory missing '
                        f'({_display_path(validation_dir)}); all '
                        f'validation-derived fields are null')
        return []
    files = sorted(path for path in validation_dir.rglob('*.json') if path.is_file())
    if not files:
        warnings.append(f'validation directory empty ({_display_path(validation_dir)})')
        return []
    reports = []
    for path in files:
        payload = _load_json(path, warnings, f'validation file {path.name}',
                            required=False)
        if payload is None:
            continue
        for report in _extract_reports(payload):
            if not isinstance(report, dict):
                continue
            reports.append((path, report))
    return reports


def _select_validation(reports, scheme, n_layers):
    best = None
    best_score = None
    ties = []
    for path, report in reports:
        report_scheme, report_layers = _report_identity(report, path)
        if report_scheme != scheme or report_layers != n_layers:
            continue
        score = 0
        if report.get('scheme') in SCHEMES:
            score += 4
        if report.get('n_layers') is not None:
            score += 4
        name = path.name.lower()
        path_text = str(path).replace('\\', '/').lower()
        if 'all_validation' in name or name.startswith('all'):
            score -= 2
        if 'validation' in name:
            score += 1
        if '_smoke' in path_text:
            score -= 1  # debug sample must never win over a formal run file
        if best is None or score > best_score:
            best = (path, report)
            best_score = score
            ties = [path]
        elif score == best_score:
            ties.append(path)
    return best, (len(ties) if best is not None else 0)


def _validation_view(report, source_path):
    counts = report.get('counts') if isinstance(report.get('counts'), dict) else {}
    violations = report.get('violations')
    violation_kinds = Counter()
    if isinstance(violations, list):
        for violation in violations:
            if isinstance(violation, dict):
                kind = str(violation.get('kind') or violation.get('reason') or 'unknown')
                violation_kinds[kind.lower()] += 1

    def _count(key, hint):
        value = counts.get(key)
        if isinstance(value, (int, float)):
            return int(value)
        if violations is not None:
            return sum(number for kind, number in violation_kinds.items()
                       if hint in kind)
        return None

    crossings = report.get('crossings')
    crossings_total = None
    crossings_by_layer = None
    if isinstance(crossings, dict):
        raw_layers = crossings.get('by_layer')
        if isinstance(raw_layers, dict):
            normalised = {}
            for key, value in raw_layers.items():
                try:
                    layer = int(key)
                except (TypeError, ValueError):
                    continue
                try:
                    normalised[str(layer)] = int(value)
                except (TypeError, ValueError):
                    continue
            crossings_by_layer = dict(sorted(normalised.items(),
                                             key=lambda item: int(item[0])))
        raw_total = crossings.get('total')
        if isinstance(raw_total, (int, float)):
            crossings_total = int(raw_total)
        elif crossings_by_layer:
            crossings_total = sum(crossings_by_layer.values())
    elif isinstance(crossings, (int, float)):
        crossings_total = int(crossings)

    stats = report.get('stats') if isinstance(report.get('stats'), dict) else None
    layer_2d = report.get('layer_2d')
    layer_2d_compact = None
    if isinstance(layer_2d, dict):
        layer_2d_compact = {}
        for key, value in layer_2d.items():
            if not isinstance(value, dict):
                continue
            layer_2d_compact[str(key)] = {
                name: value.get(name)
                for name in ('parts', 'crossings', 'violations',
                             'min_non_crossing_centerline_mm')
                if value.get(name) is not None}
    failure_reasons = report.get('failure_reasons')
    csv_sha256 = report.get('csv_sha256')
    csv_expected = report.get('csv_sha256_expected')
    return dict(
        present=True,
        source=_display_path(source_path),
        schema=report.get('schema'),
        label=report.get('label'),
        passed=_normalise_passed(report.get('passed')),
        routed=_pick_int(report.get('routed')),
        failed=_pick_int(report.get('failed')),
        total=_pick_int(report.get('total')),
        failure_reasons=dict(failure_reasons)
        if isinstance(failure_reasons, dict) else failure_reasons,
        crossings_total=crossings_total,
        crossings_by_layer=crossings_by_layer,
        total_violations=(len(violations) if isinstance(violations, list) else None),
        violation_kinds=dict(report.get('violation_kinds') or {})
        if isinstance(report.get('violation_kinds'), dict) else None,
        clearance_violations=_count('clearance_violations', 'clear'),
        curvature_violations=_count('curvature_violations', 'curv'),
        structure_errors=_count('structure_errors', 'structure'),
        port_errors=_count('port_errors', 'port'),
        xy_model_errors=_count('xy_model_errors', 'xy'),
        layer_2d_violations=_count('layer_2d_violations', 'layer_2d'),
        self_clearance_violations=_count('self_clearance_violations', 'self'),
        board_violations=_count('board_violations', 'board'),
        counts=dict(counts) if counts else None,
        min_3d_distance_mm=_pick_float(report.get('min_3d_distance_mm')),
        min_3d_distance_excluding_crossings_mm=_pick_float(
            report.get('min_3d_distance_excluding_crossings_mm'),
            report.get('min_3d_distance_mm')),
        min_3d_distance_including_crossings_mm=_pick_float(
            report.get('min_3d_distance_including_crossings_mm')),
        min_curvature_radius_mm=_pick_float(report.get('min_curvature_radius_mm')),
        runtime_seconds=_pick_float(report.get('runtime_seconds')),
        port_csv_checked=report.get('port_csv_checked'),
        csv_sha256=csv_sha256,
        csv_sha256_ok=(str(csv_sha256) == str(csv_expected)
                       if csv_sha256 and csv_expected else None),
        layer_2d=layer_2d_compact,
        definition=report.get('min_3d_distance_definition'),
        stats=dict(stats) if stats else None,
        warnings=list(report.get('warnings') or [])[:20]
        if isinstance(report.get('warnings'), list) else None,
    )


def _attach_validations(root, runs, warnings):
    reports = _discover_validation_reports(Path(root) / 'validation', warnings)
    # A file counts as "matched" when at least one report it contains maps to a
    # known scheme/layers pair (so a combined all_validation.json that was
    # superseded by per-run files is not reported as orphaned).
    matched_paths = set()
    for path, report in reports:
        report_scheme, report_layers = _report_identity(report, path)
        if report_scheme in SCHEMES and report_layers in LAYER_COUNTS:
            matched_paths.add(path)

    # optional debug-sample validation (validation/_smoke/...) for the doc
    smoke_candidates = []
    for path, report in reports:
        if '_smoke' not in str(path).replace('\\', '/').lower():
            continue
        report_scheme, report_layers = _report_identity(report, path)
        if report_scheme in SCHEMES and report_layers in LAYER_COUNTS:
            smoke_candidates.append((path, report))
    smoke_view = None
    if smoke_candidates:
        smoke_candidates.sort(key=lambda item: str(item[0]))
        smoke_path, smoke_report = smoke_candidates[0]
        smoke_view = _validation_view(smoke_report, smoke_path)
        smoke_view['label'] = (smoke_report.get('label')
                               or smoke_report.get('scheme'))

    for scheme in SCHEMES:
        for n_layers in LAYER_COUNTS:
            key = f'{scheme}/{n_layers}'
            run = runs[key]
            found, ties = _select_validation(reports, scheme, n_layers)
            if found is None:
                if run.get('present'):
                    warnings.append(f'{key}: independent validation report not found '
                                    f'under validation/; validation fields null')
                continue
            path, report = found
            if not run.get('present'):
                if '_smoke' in str(path).replace('\\', '/').lower():
                    continue  # smoke validation is reported separately
                warnings.append(f'{key}: validation report found '
                                f'({_display_path(path)}) but the run data is '
                                f'missing; validation ignored')
                continue
            view = _validation_view(report, path)
            if ties and ties > 1:
                warnings.append(f'{key}: {ties} validation reports matched; using '
                                f'{_display_path(path)} (highest score)')
            run['validation'] = view
            run['validation_present'] = True
            run['validation_passed'] = view.get('passed')
            run['crossings_total'] = view.get('crossings_total')
            run['crossings_by_layer'] = view.get('crossings_by_layer')
            run['clearance_violations'] = view.get('clearance_violations')
            run['curvature_violations'] = view.get('curvature_violations')
            run['total_violations'] = view.get('total_violations')
            run['min_3d_distance_mm'] = view.get('min_3d_distance_mm')
            run['min_3d_distance_excluding_crossings_mm'] = view.get(
                'min_3d_distance_excluding_crossings_mm')
            run['min_3d_distance_including_crossings_mm'] = view.get(
                'min_3d_distance_including_crossings_mm')
            run['min_curvature_radius_mm'] = view.get('min_curvature_radius_mm')
            run['validation_runtime_seconds'] = view.get('runtime_seconds')
            _check_validation_consistency(key, run, view, warnings)
    unmatched = sorted({path for path, _report in reports} - matched_paths)
    for path in unmatched:
        warnings.append(f'validation file {_display_path(path)} does not match any '
                        f'scheme/layers run; ignored')
    return runs, smoke_view


def _check_validation_consistency(key, run, view, warnings):
    routed = run.get('routed')
    val_routed = view.get('routed')
    if routed is not None and val_routed is not None and int(routed) != int(val_routed):
        warnings.append(f'{key}: validation routed={val_routed} but run '
                        f'routed={routed}')
    transitions = run.get('transitions')
    val_stats = view.get('stats') or {}
    if transitions is not None and val_stats.get('transitions') is not None \
            and int(transitions) != int(val_stats.get('transitions')):
        warnings.append(f'{key}: validation stats.transitions='
                        f'{val_stats.get("transitions")} but run transitions='
                        f'{transitions}')
    total_length = run.get('total_length_mm')
    if total_length is not None and val_stats.get('total_length_mm') is not None \
            and not _same_number(total_length, val_stats.get('total_length_mm')):
        warnings.append(f'{key}: validation stats.total_length_mm='
                        f'{val_stats.get("total_length_mm")} but run '
                        f'total_length_mm={total_length}')


# ---------------------------------------------------------------------------
# extra crossing metrics (extra_metrics25d.py -> summary/crossing_metrics.json)
# ---------------------------------------------------------------------------
def _load_crossing_metrics(root, warnings):
    """Flattened-2D vs actual-3D crossing metrics, when the extra script ran."""
    path = Path(root) / 'summary' / 'crossing_metrics.json'
    if not path.exists():
        warnings.append(
            'summary/crossing_metrics.json missing; flattened-2D vs actual-3D '
            'crossing metrics are null (run four_side_1024.fsd25d.extra_metrics25d '
            'after routes_25d.json + validation exist)')
        return {}
    payload = _load_json(path, warnings, 'summary/crossing_metrics.json',
                        required=False)
    if not isinstance(payload, dict):
        return {}
    result = {}
    for key, value in payload.items():
        if not isinstance(value, dict):
            continue
        scheme = str(value.get('scheme') or '').strip().upper()
        n_layers = _pick_int(value.get('n_layers'))
        if scheme not in SCHEMES or n_layers not in LAYER_COUNTS:
            continue
        result[f'{scheme}/{n_layers}'] = dict(
            scheme=scheme,
            n_layers=n_layers,
            routed=_pick_int(value.get('routed')),
            flattened_total=_pick_int(value.get('flattened_total')),
            actual_3d_crossings=_pick_int(value.get('actual_3d_crossings')),
            crossings_avoided=_pick_int(value.get('crossings_avoided')),
            per_plane=value.get('per_plane')
            if isinstance(value.get('per_plane'), dict) else None,
            by_layer=value.get('by_layer')
            if isinstance(value.get('by_layer'), dict) else None,
            source=_display_path(path),
        )
    return result


def _attach_crossing_metrics(runs, metrics, warnings):
    for key in RUN_KEYS:
        info = metrics.get(key)
        run = runs[key]
        if info is None:
            if metrics and run.get('present'):
                warnings.append(
                    f'{key}: no crossing metrics entry in '
                    f'summary/crossing_metrics.json; flattened/avoided crossings '
                    f'are null (rerun four_side_1024.fsd25d.extra_metrics25d)')
            continue
        if not run.get('present'):
            warnings.append(f'{key}: crossing metrics present '
                            f'({info.get("source")}) but run data missing; ignored')
            continue
        run['flattened_crossings_2d'] = info.get('flattened_total')
        run['crossings_avoided'] = info.get('crossings_avoided')
        run['flattened_crossings_per_plane'] = info.get('per_plane')
        run['crossing_metrics_source'] = info.get('source')
        actual = info.get('actual_3d_crossings')
        validation_total = run.get('crossings_total')
        if actual is not None and validation_total is not None \
                and int(actual) != int(validation_total):
            warnings.append(f'{key}: crossing_metrics actual_3d_crossings={actual} '
                            f'differs from validation crossings_total='
                            f'{validation_total}; validation is authoritative')
        routed = info.get('routed')
        if routed is not None and run.get('routed') is not None \
                and int(routed) != int(run['routed']):
            warnings.append(f'{key}: crossing_metrics routed={routed} differs from '
                            f'routes routed={run["routed"]}')
    for key in metrics:
        if key not in RUN_KEYS:
            warnings.append(f'crossing metrics entry {key} does not match a known '
                            f'scheme/layers run; ignored')


# ---------------------------------------------------------------------------
# geometric model + baseline provenance
# ---------------------------------------------------------------------------
def _possible_transition_dz(n_layers):
    stack = list(CFG.LAYER_STACKS[int(n_layers)])
    values = set()
    for interface_layer in set(CFG.INTERFACE_LAYER[int(n_layers)].values()):
        interface_z = stack[interface_layer]
        for layer in range(1, int(n_layers) - 1):
            if layer == interface_layer:
                continue
            values.add(round(abs(stack[layer] - interface_z), 9))
    return sorted(values)


def _build_geometric_model(runs, warnings):
    model = dict(
        description='V2 五层 2.5D：flat（接口层保持）+ lifted（两段 R=40 垂直 S 曲线升降）',
        layer_stacks={str(n): [float(value) for value in CFG.LAYER_STACKS[n]]
                      for n in LAYER_COUNTS},
        interface_layer={str(n): dict(CFG.INTERFACE_LAYER[n]) for n in LAYER_COUNTS},
        interface_z_mm={str(n): {'z1': float(CFG.LAYER_STACKS[n][
            CFG.INTERFACE_LAYER[n]['z1']]),
            'z2': float(CFG.LAYER_STACKS[n][CFG.INTERFACE_LAYER[n]['z2']])}
            for n in LAYER_COUNTS},
        transition_dz_mm={str(n): _possible_transition_dz(n) for n in LAYER_COUNTS},
        board_mm=[float(CFG.BOARD_MM), float(CFG.BOARD_MM)],
        width_mm=float(CFG.WIDTH_MM),
        edge_gap_mm=float(CFG.EDGE_GAP_MM),
        clearance_mm=float(CFG.CLEARANCE_MM),
        radius_mm=float(CFG.RADIUS_MM),
        min_cross_angle_deg=float(CFG.MIN_CROSS_ANGLE_DEG),
        crossing_policy=CFG.CROSSING_POLICY,
        crossing_exemption_window_mm=2.5,
        s_curve=dict(
            type='vertical-plane two-arc S curve',
            radius_mm=float(CFG.RADIUS_MM),
            theta_formula='theta = acos(1 - |dz| / (2R))',
            footprint_formula='footprint = 2R sin(theta)',
            length_formula='length = 2R theta',
            note='G1 continuous; start/end tangents horizontal and equal to the '
                 'hosting straight direction; transition direction axis-aligned',
        ),
    )
    footprint = {}
    for n in LAYER_COUNTS:
        footprint[str(n)] = {
            f'{dz:.6f}': round(float(CFG.transition_footprint(dz)), 6)
            for dz in model['transition_dz_mm'][str(n)]}
    model['transition_footprint_mm'] = footprint

    # Prefer the process block actually recorded in the route files.
    processes = [(key, run['process']) for key, run in runs.items()
                 if isinstance(run.get('process'), dict)]
    for key, process in processes:
        for field, model_field in (('board_mm', 'board_mm'),
                                   ('width_mm', 'width_mm'),
                                   ('edge_gap_mm', 'edge_gap_mm'),
                                   ('clearance_mm', 'clearance_mm'),
                                   ('radius_mm', 'radius_mm'),
                                   ('min_cross_angle_deg', 'min_cross_angle_deg'),
                                   ('crossing_policy', 'crossing_policy')):
            value = process.get(field)
            if value is None:
                continue
            if field == 'board_mm':
                value = [float(item) for item in value]
            elif field == 'crossing_policy':
                value = str(value)
            else:
                value = float(value)
            if model.get(model_field) != value:
                warnings.append(f'geometric model: run {key} process.{field}='
                                f'{value!r} differs from config25d default '
                                f'{model.get(model_field)!r}; using the route-file value')
                model[model_field] = value
    return model


def _build_baseline_info(warnings):
    result = {}
    for scheme in SCHEMES:
        spec = CFG.SCHEMES.get(scheme) or {}
        baseline_root = Path(spec.get('baseline_root') or '.')
        algorithm = str(spec.get('baseline_algorithm') or '')
        entry = dict(
            scheme=scheme,
            label=spec.get('label'),
            description=spec.get('description'),
            algorithm=algorithm,
            root=_display_path(baseline_root),
            root_abs=str(baseline_root),
            expected_baseline_routed=spec.get('baseline_routed'),
            present=baseline_root.is_dir(),
            files={},
            routed_total=0,
            csv_sha256=None,
        )
        for plane in PLANES:
            path = baseline_root / 'planes' / 'V2' / algorithm / plane / 'routes.json'
            info = dict(path=_display_path(path), path_abs=str(path),
                        present=path.exists(), sha256=None, csv_sha256=None,
                        routed=None, failed=None, total=None)
            if path.exists():
                try:
                    info['sha256'] = _sha256_file(path)
                except OSError as exc:  # pragma: no cover - defensive
                    warnings.append(f'baseline {scheme}/{plane}: sha256 failed: {exc}')
                payload = _load_json(path, [], f'baseline {scheme}/{plane}',
                                    required=False)
                if isinstance(payload, dict):
                    info['csv_sha256'] = payload.get('csv_sha256')
                    records = payload.get('routes')
                    if isinstance(records, list):
                        info['total'] = len(records)
                        info['routed'] = sum(1 for record in records
                                             if isinstance(record, dict)
                                             and record.get('status') == 'routed')
                        info['failed'] = (info['total'] - info['routed'])
            entry['files'][plane] = info
        if entry['files']:
            entry['routed_total'] = sum((info.get('routed') or 0)
                                        for info in entry['files'].values())
            hashes = {info.get('csv_sha256') for info in entry['files'].values()
                      if info.get('csv_sha256')}
            if len(hashes) == 1:
                entry['csv_sha256'] = hashes.pop()
        result[scheme] = entry
    return result


# ---------------------------------------------------------------------------
# comparison table / layers effect / failed analysis builders
# ---------------------------------------------------------------------------
def _build_comparison_rows(runs):
    rows = []
    for scheme in SCHEMES:
        baseline = None
        for n_layers in LAYER_COUNTS:
            run = runs[f'{scheme}/{n_layers}']
            if run.get('present') and run.get('baseline_routed') is not None:
                baseline = run['baseline_routed']
                break
        if baseline is None:
            baseline = (CFG.SCHEMES.get(scheme) or {}).get('baseline_routed')
        rows.append(dict(
            label=f'{scheme} 基线',
            kind='baseline',
            scheme=scheme,
            n_layers=None,
            present=True,
            original_2d_routed=baseline,
            routed_25d=None,
            new_routed=None,
            five_layer_routed=None,
            crossings_total=None,
            flattened_crossings_2d=None,
            crossings_avoided=None,
            total_length_mm=None,
            transitions=None,
            clearance_violations=None,
            curvature_violations=None,
            min_3d_distance_mm=None,
            min_3d_distance_excluding_crossings_mm=None,
            min_curvature_radius_mm=None,
            validation_present=False,
            validation_passed=None,
        ))
        for n_layers in LAYER_COUNTS:
            run = runs[f'{scheme}/{n_layers}']
            present = bool(run.get('present'))
            rows.append(dict(
                label=f'{scheme} · {n_layers} 层',
                kind='run' if present else 'missing',
                scheme=scheme,
                n_layers=n_layers,
                present=present,
                original_2d_routed=baseline if present else None,
                routed_25d=run.get('routed_25d') if present else None,
                new_routed=run.get('new_routed') if present else None,
                five_layer_routed=run.get('five_layer_routed') if present else None,
                crossings_total=run.get('crossings_total') if present else None,
                flattened_crossings_2d=(run.get('flattened_crossings_2d')
                                        if present else None),
                crossings_avoided=run.get('crossings_avoided') if present else None,
                total_length_mm=run.get('total_length_mm') if present else None,
                transitions=run.get('transitions') if present else None,
                clearance_violations=run.get('clearance_violations') if present else None,
                curvature_violations=run.get('curvature_violations') if present else None,
                min_3d_distance_mm=run.get('min_3d_distance_mm') if present else None,
                min_3d_distance_excluding_crossings_mm=(
                    run.get('min_3d_distance_excluding_crossings_mm')
                    if present else None),
                min_curvature_radius_mm=(run.get('min_curvature_radius_mm')
                                         if present else None),
                validation_present=bool(run.get('validation_present')),
                validation_passed=run.get('validation_passed'),
            ))
    return rows


def _layer_metrics(run):
    if not run or not run.get('present'):
        return None
    keys = ('routed', 'new_routed', 'lifted', 'flat_added', 'transitions',
            'total_length_mm', 'mean_length_mm', 'failed_total',
            'failed_no_candidate', 'failed_unplaceable', 'per_plane',
            'per_layer_flat_parts', 'validation_passed', 'crossings_total',
            'flattened_crossings_2d', 'crossings_avoided',
            'clearance_violations', 'curvature_violations',
            'min_3d_distance_excluding_crossings_mm', 'min_curvature_radius_mm')
    return {key: run.get(key) for key in keys}


def _effect_conclusion(scheme, metrics3, metrics5, gain):
    if metrics3 is None or metrics5 is None:
        missing = [str(n_layers) for n_layers, metrics in
                   ((3, metrics3), (5, metrics5)) if metrics is None]
        return f'缺少 layers{"/".join(missing)} 数据，无法比较'
    delta = (gain or {}).get('routed')
    routed3 = metrics3.get('routed')
    routed5 = metrics5.get('routed')
    if delta is None:
        return f'3 层 {routed3}/1024，5 层 {routed5}/1024；增益无法计算'
    if delta > 0:
        verdict = '加入高度有正收益'
    elif delta == 0:
        verdict = '加入高度无增益（持平）'
    else:
        verdict = '加入高度反而减少布通'
    return (f'5 层 {routed5}/1024 vs 3 层 {routed3}/1024，布通增益 {delta:+d}'
            f'（新增 {_fmt_delta((gain or {}).get("new_routed"))}，'
            f'抬升 {_fmt_delta((gain or {}).get("lifted"))}），'
            f'升降次数 {_fmt_int(metrics5.get("transitions"))} vs '
            f'{_fmt_int(metrics3.get("transitions"))}；{verdict}')


def _build_layers_effect(runs, root, warnings):
    effect = dict(
        schema=SCHEMA_LAYERS_EFFECT,
        generated_utc=_now_utc(),
        root=_display_path(root),
        description='3 层 vs 5 层对照：回答“增加层数（高度）是否带来布通收益”',
        metric_units=dict(routed='routes / 1024 per run',
                          new_routed='routes gained over 2D baseline',
                          transitions='S-curve transitions (2 per lifted route)',
                          total_length_mm='mm'),
        schemes={},
        totals={},
        warnings=[],
    )
    for scheme in SCHEMES:
        run3 = runs[f'{scheme}/3']
        run5 = runs[f'{scheme}/5']
        metrics3 = _layer_metrics(run3)
        metrics5 = _layer_metrics(run5)
        gain = None
        if metrics3 is not None and metrics5 is not None:
            gain = {}
            for key in GAIN_KEYS:
                if key == 'mean_length_mm':
                    gain[key] = _delta_float(metrics5.get(key), metrics3.get(key))
                elif key in ('total_length_mm',):
                    gain[key] = _delta_float(metrics5.get(key), metrics3.get(key))
                else:
                    gain[key] = _delta_int(metrics5.get(key), metrics3.get(key))
        per_plane = {}
        for plane in PLANES:
            plane3 = ((metrics3 or {}).get('per_plane') or {}).get(plane) or {}
            plane5 = ((metrics5 or {}).get('per_plane') or {}).get(plane) or {}
            per_plane[plane] = dict(
                routed_3=_pick_int(plane3.get('routed')),
                routed_5=_pick_int(plane5.get('routed')),
                gain=_delta_int(plane5.get('routed'), plane3.get('routed')),
                lifted_3=_pick_int(plane3.get('lifted')),
                lifted_5=_pick_int(plane5.get('lifted')),
                new_3=_pick_int(plane3.get('new')),
                new_5=_pick_int(plane5.get('new')),
                failed_3=_pick_int(plane3.get('failed')),
                failed_5=_pick_int(plane5.get('failed')),
            )
        conclusion = _effect_conclusion(scheme, metrics3, metrics5, gain)
        effect['schemes'][scheme] = dict(
            present={'3': metrics3 is not None, '5': metrics5 is not None},
            layers3=metrics3,
            layers5=metrics5,
            gain_5_vs_3=gain,
            per_plane=per_plane,
            per_layer_flat_parts={
                '3': (metrics3 or {}).get('per_layer_flat_parts'),
                '5': (metrics5 or {}).get('per_layer_flat_parts'),
            },
            conclusion=conclusion,
        )

    # combined totals across schemes (only schemes with the layer count present)
    totals = {}
    for n_layers in LAYER_COUNTS:
        present = [scheme for scheme in SCHEMES
                   if effect['schemes'][scheme]['present'][str(n_layers)]]
        if not present:
            totals[str(n_layers)] = dict(present_schemes=[], denominator=None,
                                         routed=None, new_routed=None, lifted=None,
                                         transitions=None, total_length_mm=None)
            continue

        def _sum(field):
            values = [effect['schemes'][scheme][f'layers{n_layers}'].get(field)
                      for scheme in present]
            if any(value is None for value in values):
                return None
            return sum(values)

        totals[str(n_layers)] = dict(
            present_schemes=present,
            denominator=TOTAL_ROUTES_PER_RUN * len(present),
            routed=_sum('routed'),
            new_routed=_sum('new_routed'),
            lifted=_sum('lifted'),
            transitions=_sum('transitions'),
            total_length_mm=_sum('total_length_mm'),
        )
    common = [scheme for scheme in SCHEMES
              if effect['schemes'][scheme]['present']['3']
              and effect['schemes'][scheme]['present']['5']]
    total_gain = None
    if common:
        total_gain = dict(
            schemes=common,
            denominator=TOTAL_ROUTES_PER_RUN * len(common),
            routed=_delta_int(totals['5']['routed'], totals['3']['routed']),
            new_routed=_delta_int(totals['5']['new_routed'], totals['3']['new_routed']),
            lifted=_delta_int(totals['5']['lifted'], totals['3']['lifted']),
            transitions=_delta_int(totals['5']['transitions'], totals['3']['transitions']),
        )
    effect['totals'] = dict(layers3=totals['3'], layers5=totals['5'],
                            gain_5_vs_3=total_gain)
    if total_gain is not None and total_gain.get('routed') is not None:
        gain_value = total_gain['routed']
        denominator = total_gain['denominator']
        routed3_common = sum(
            ((effect['schemes'][scheme]['layers3'] or {}).get('routed') or 0)
            for scheme in common)
        routed5_common = sum(
            ((effect['schemes'][scheme]['layers5'] or {}).get('routed') or 0)
            for scheme in common)
        if gain_value > 0:
            verdict = '加入高度有正收益'
        elif gain_value == 0:
            verdict = '加入高度无增益（持平）'
        else:
            verdict = '加入高度反而减少布通'
        scope = ('两方案合计' if set(common) == set(SCHEMES)
                 else f'{"+".join(common)} 合计（仅含同时具备 3/5 层数据的方案）')
        effect['conclusion'] = (
            f'{scope}：5 层 {routed5_common}/{denominator} vs 3 层 '
            f'{routed3_common}/{denominator}，净增益 {gain_value:+d}；{verdict}')
    else:
        effect['conclusion'] = '数据不完整，无法给出层数效应结论（需要同一方案同时存在 3 层与 5 层 run）'
    return effect


def _build_failed_analysis(runs, forensics, root, warnings):
    analysis = dict(
        schema=SCHEMA_FAILED_ANALYSIS,
        generated_utc=_now_utc(),
        root=_display_path(root),
        definition=NO_2D_DEFINITION,
        source='reason field of status="failed" records in routes_25d.json; '
               'run_summary.statistics is authoritative for failed_no_candidate / '
               'failed_unplaceable',
        runs={},
        by_scheme={},
        no_2d_candidate_at_all={},
        totals={},
        warnings=[],
    )
    for scheme in SCHEMES:
        for n_layers in LAYER_COUNTS:
            key = f'{scheme}/{n_layers}'
            run = runs[key]
            forensic = forensics.get(key)
            entry = dict(
                scheme=scheme,
                n_layers=n_layers,
                present=bool(run.get('present')),
                records_available=forensic is not None,
                total=run.get('total'),
                routed=run.get('routed'),
                failed=run.get('failed_total'),
                by_reason=None,
                no_2d_candidate_count=None,
                no_lift_candidate_count=None,
                other_reason_counts=None,
                failed_no_candidate=run.get('failed_no_candidate'),
                failed_unplaceable=run.get('failed_unplaceable'),
                attemptable=run.get('attemptable'),
                no_candidate=run.get('no_candidate'),
                by_plane=None,
                by_pair=None,
                no_2d_candidate_route_ids=None,
                no_lift_candidate_route_ids=None,
                other_failed_route_ids_by_reason=None,
            )
            if forensic is not None:
                entry.update(
                    by_reason=forensic['reason_counts'],
                    no_2d_candidate_count=len(forensic['no_2d_route_ids']),
                    no_lift_candidate_count=len(forensic['no_lift_route_ids']),
                    other_reason_counts=forensic['other_route_ids_by_reason'],
                    by_plane=forensic['by_plane'],
                    by_pair=forensic['by_pair'],
                    no_2d_candidate_route_ids=forensic['no_2d_route_ids'],
                    no_lift_candidate_route_ids=forensic['no_lift_route_ids'],
                    other_failed_route_ids_by_reason=forensic['other_route_ids_by_reason'],
                )
            limit = None
            if isinstance(run.get('config'), dict):
                limit = run['config'].get('limit')
            entry['debug_limit'] = limit
            if limit:
                entry['note'] = ('debug run with --limit; no_lift_candidate counts '
                                 'include unattempted routes')
                warnings.append(f'{key}: debug run (--limit {limit}); failure '
                                f'breakdown is not final')
            analysis['runs'][key] = entry

    # consolidated per scheme + explicit "no 2D XY candidate at all" list
    registry = {}
    for scheme in SCHEMES:
        scheme_entry = dict(
            layers_present=[], no_2d_candidate={}, no_lift_candidate={})
        by_layer_no_2d = {}
        by_layer_no_lift = {}
        for n_layers in LAYER_COUNTS:
            key = f'{scheme}/{n_layers}'
            forensic = forensics.get(key)
            run = runs[key]
            if not run.get('present'):
                continue
            scheme_entry['layers_present'].append(n_layers)
            if forensic is None:
                continue
            by_layer_no_2d[str(n_layers)] = list(forensic['no_2d_route_ids'])
            by_layer_no_lift[str(n_layers)] = list(forensic['no_lift_route_ids'])
            for info in forensic['failed_route_info']:
                if info.get('reason') != REASON_NO_2D:
                    continue
                route_id = info.get('route_id')
                if route_id is None:
                    continue
                identity = (scheme, int(route_id))
                record = registry.get(identity)
                if record is None:
                    record = dict(scheme=scheme, route_id=int(route_id),
                                  plane=info.get('plane'), pair=info.get('pair'),
                                  relation=info.get('relation'),
                                  interface_layer=info.get('interface_layer'),
                                  reported_by_runs=[])
                    registry[identity] = record
                if n_layers not in record['reported_by_runs']:
                    record['reported_by_runs'].append(n_layers)

        no_2d_union = sorted({route_id for ids in by_layer_no_2d.values()
                              for route_id in ids})
        no_2d_consistent = None
        if len(by_layer_no_2d) > 1:
            first = list(by_layer_no_2d.values())[0]
            no_2d_consistent = all(ids == first for ids in by_layer_no_2d.values())
        no_lift_union = sorted({route_id for ids in by_layer_no_lift.values()
                                for route_id in ids})
        scheme_entry['no_2d_candidate'] = dict(
            count_by_layer={key: len(ids) for key, ids in by_layer_no_2d.items()},
            count_unique=len(no_2d_union),
            route_ids=no_2d_union,
            consistent_across_layers=no_2d_consistent,
        )
        scheme_entry['no_lift_candidate'] = dict(
            count_by_layer={key: len(ids) for key, ids in by_layer_no_lift.items()},
            count_unique=len(no_lift_union),
            route_ids_by_layer=by_layer_no_lift,
            route_ids_unique=no_lift_union,
        )
        analysis['by_scheme'][scheme] = scheme_entry

    routes = sorted(registry.values(), key=lambda item: (item['scheme'], item['route_id']))
    count_by_scheme = {scheme: 0 for scheme in SCHEMES}
    for route in routes:
        count_by_scheme[route['scheme']] += 1
    analysis['no_2d_candidate_at_all'] = dict(
        description='routes for which the frozen 2D baseline had no legal/any 2D XY '
                    'candidate at all (reason=no_2d_candidate); reported separately '
                    'because they cannot be fixed by adding heights',
        count_by_scheme=count_by_scheme,
        count_total=len(routes),
        routes=routes,
    )

    # totals over available run records
    total_failed = 0
    total_no_2d = 0
    total_no_lift = 0
    total_other = 0
    runs_with_records = []
    for scheme in SCHEMES:
        for n_layers in LAYER_COUNTS:
            key = f'{scheme}/{n_layers}'
            forensic = forensics.get(key)
            if forensic is None:
                continue
            runs_with_records.append(key)
            total_failed += forensic['failed_total']
            total_no_2d += len(forensic['no_2d_route_ids'])
            total_no_lift += len(forensic['no_lift_route_ids'])
            total_other += len(forensic['other_route_ids'])
    analysis['totals'] = dict(
        runs_with_records=runs_with_records,
        failed_records=total_failed,
        no_2d_candidate_records=total_no_2d,
        no_lift_candidate_records=total_no_lift,
        other_records=total_other,
        note='summed over the runs that have route records; the same route appears '
             'once per layer-count run, so cross-run sums double count routes',
    )
    analysis['warnings'] = warnings
    return analysis


# ---------------------------------------------------------------------------
# markdown renderers
# ---------------------------------------------------------------------------
def _render_comparison_md(overview):
    baselines = overview.get('baselines') or {}
    baseline_parts = []
    for scheme, info in baselines.items():
        count = info.get('routed_total') or info.get('expected_baseline_routed')
        if count:
            baseline_parts.append(f'{scheme}={count}/1024')
    baseline_text = '，'.join(baseline_parts) or '见 overview.json'
    lines = [
        '# 2.5D 五层实验对照表（自动生成）',
        '',
        f'- 数据根目录：`{overview["root"]}`',
        f'- 生成时间（UTC）：{overview["generated_utc"]}',
        '- 生成脚本：`four_side_1024/fsd25d/summarize25d.py`（只读输入，不修改路线数据）',
        f'- 原始 2D 布通 = 冻结基线（{baseline_text}）。2.5D 布通 / 新增 / 总长 / '
        '升降次数来自 `routes_25d.json`（缺失时由 routes 记录重算）。',
        '- 实际 3D 交叉数 = 各层同层合法交叉之和（validation 的 `crossings.total`）；'
        '3D 净空违规、曲率违规与验收结论来自独立 `validate25d` 输出。',
        '- 2D 平铺交叉数 = 把本 run 全部路线平铺回接口高度后按冻结 strict 2D pair '
        'kernel 统计的假设性交叉总数；消除的交叉数 = 平铺 − 实际 3D（来源 '
        '`extra_metrics25d.py` → `summary/crossing_metrics.json`，缺失记 “' + DASH + '”）。',
        '- 若某 run 或 validation 缺失，对应单元格记 “' + DASH + '”，并在 '
        '`overview.json` 的 warnings 中记录原因。',
        '',
        '## 1. 方案 × 层数对照',
        '',
    ]
    headers = ['方案', '层数', '原始 2D 布通', '2.5D 布通', '新增布通',
               '实际 3D 交叉数', '2D 平铺交叉数', '消除的交叉数',
               '总波导长度 (mm)', '总升降次数', '3D 净空违规',
               '曲率违规', '验收']
    aligns = ['---', '---:', '---:', '---:', '---:', '---:', '---:', '---:',
              '---:', '---:', '---:', '---:', '---']
    rows = []
    for row in overview.get('comparison_rows') or []:
        if row.get('kind') == 'baseline':
            layer_text = '2D 基线'
        elif row.get('kind') == 'missing':
            layer_text = f'{row.get("n_layers")}（缺失）'
        else:
            layer_text = str(row.get('n_layers'))
        rows.append([
            row.get('scheme'),
            layer_text,
            _fmt_int(row.get('original_2d_routed')),
            _fmt_int(row.get('routed_25d')),
            _fmt_int(row.get('new_routed')),
            _fmt_int(row.get('crossings_total')),
            _fmt_int(row.get('flattened_crossings_2d')),
            _fmt_int(row.get('crossings_avoided')),
            _fmt_num(row.get('total_length_mm'), 3),
            _fmt_int(row.get('transitions')),
            _fmt_int(row.get('clearance_violations')),
            _fmt_int(row.get('curvature_violations')),
            _verdict_text({'validation': {'present': row.get('validation_present'),
                                          'passed': row.get('validation_passed')}}),
        ])
    lines.extend(_md_table(headers, rows, aligns))
    lines.append('')

    runs_missing = overview.get('selfcheck', {}).get('runs_missing') or []
    if runs_missing:
        lines.append('> 缺失的 run：' + '、'.join(f'`{key}`' for key in runs_missing))
        lines.append('')
    validation_missing = overview.get('selfcheck', {}).get('validation_missing') or []
    if validation_missing:
        lines.append('> 缺失的独立验收：'
                     + '、'.join(f'`{key}`' for key in validation_missing))
        lines.append('')

    lines.append('## 2. 层数效应速览')
    lines.append('')
    summary = overview.get('layers_effect_summary') or {}
    conclusion = summary.get('conclusion')
    if conclusion:
        lines.append(f'- 总体结论：{conclusion}')
        lines.append('')
    for scheme in SCHEMES:
        text = (summary.get('schemes') or {}).get(scheme)
        if text:
            lines.append(f'- 方案 {scheme}：{text}')
    lines.append('')
    lines.append('## 3. 口径说明')
    lines.append('')
    lines.append('- 每 run 固定 1024 条 route（z1/z2 各 512）。')
    lines.append('- “新增布通”= 2.5D 布通 − 原始 2D 布通；新增路线要么保持 flat（新 2D '
                 '候选），要么抬升到中间层（lifted，两次 S 曲线 transition）。')
    lines.append('- 实际 3D 交叉数来自按层冻结 strict 2D 审计，不等于 2D 路线交叉数之和。')
    lines.append('- 2D 平铺交叉数来自 `extra_metrics25d.py`：把该 run 全部 3D 路线平铺回'
                 '接口高度后，按冻结 strict 2D pair kernel 统计的假设性交叉总数；'
                 '“消除的交叉数 = 平铺 − 实际 3D”量化抬升/分层带来的交叉减少量。')
    lines.append('- 验收 PASS 的条件见 `SCHEMA_25D.md` §4：所有 counts 为 0、'
                 'min_3d_distance_excluding_crossings ≥ 0.08 mm、'
                 'min_curvature_radius ≥ 39.96 mm。')
    return '\n'.join(lines) + '\n'


def _render_layers_effect_md(effect):
    lines = [
        '# 层数效应：3 层 vs 5 层（自动生成）',
        '',
        f'- 数据根目录：`{effect["root"]}`',
        f'- 生成时间（UTC）：{effect["generated_utc"]}',
        '- 目的：回答“增加层数（高度）是否带来布通收益”。所有计数均为 /1024 route。',
        '',
        '## 1. 总览',
        '',
    ]
    headers = ['方案', '3 层布通', '5 层布通', '布通增益', '3 层新增', '5 层新增',
               '3 层抬升', '5 层抬升', '结论']
    aligns = ['---', '---:', '---:', '---:', '---:', '---:', '---:', '---:', '---']
    rows = []
    for scheme in SCHEMES:
        entry = effect['schemes'][scheme]
        metrics3 = entry.get('layers3') or {}
        metrics5 = entry.get('layers5') or {}
        gain = entry.get('gain_5_vs_3') or {}
        rows.append([
            scheme,
            _fmt_int(metrics3.get('routed')),
            _fmt_int(metrics5.get('routed')),
            _fmt_delta(gain.get('routed')),
            _fmt_int(metrics3.get('new_routed')),
            _fmt_int(metrics5.get('new_routed')),
            _fmt_int(metrics3.get('lifted')),
            _fmt_int(metrics5.get('lifted')),
            entry.get('conclusion'),
        ])
    lines.extend(_md_table(headers, rows, aligns))
    lines.append('')
    totals = effect.get('totals') or {}
    lines.append(f'- {effect.get("conclusion")}')
    for n_layers in LAYER_COUNTS:
        total = totals.get(f'layers{n_layers}') or {}
        if total.get('routed') is not None:
            lines.append(f'- {n_layers} 层合计：{total["routed"]}/'
                         f'{total.get("denominator")} 布通（schemes='
                         f'{", ".join(total.get("present_schemes") or [])}）')
    total_gain = totals.get('gain_5_vs_3') or {}
    if total_gain.get('routed') is not None:
        lines.append(f'- 5 层 − 3 层合计：布通 {_fmt_delta(total_gain.get("routed"))}、'
                     f'新增 {_fmt_delta(total_gain.get("new_routed"))}、'
                     f'抬升 {_fmt_delta(total_gain.get("lifted"))}')
    lines.append('')

    for scheme in SCHEMES:
        entry = effect['schemes'][scheme]
        lines.append(f'## 2.{SCHEMES.index(scheme) + 1} 方案 {scheme} 明细')
        lines.append('')
        if not (entry.get('layers3') or entry.get('layers5')):
            lines.append('> 该方案没有可用的 3 层/5 层 run 数据。')
            lines.append('')
            continue
        metrics3 = entry.get('layers3') or {}
        metrics5 = entry.get('layers5') or {}
        gain = entry.get('gain_5_vs_3') or {}
        detail_headers = ['指标', '3 层', '5 层', '差值 (5−3)']
        detail_rows = [
            ['布通 routed', _fmt_int(metrics3.get('routed')),
             _fmt_int(metrics5.get('routed')), _fmt_delta(gain.get('routed'))],
            ['新增布通 new_routed', _fmt_int(metrics3.get('new_routed')),
             _fmt_int(metrics5.get('new_routed')), _fmt_delta(gain.get('new_routed'))],
            ['抬升路线 lifted', _fmt_int(metrics3.get('lifted')),
             _fmt_int(metrics5.get('lifted')), _fmt_delta(gain.get('lifted'))],
            ['新增 flat flat_added', _fmt_int(metrics3.get('flat_added')),
             _fmt_int(metrics5.get('flat_added')), _fmt_delta(gain.get('flat_added'))],
            ['升降次数 transitions', _fmt_int(metrics3.get('transitions')),
             _fmt_int(metrics5.get('transitions')), _fmt_delta(gain.get('transitions'))],
            ['总波导长度 mm', _fmt_num(metrics3.get('total_length_mm'), 3),
             _fmt_num(metrics5.get('total_length_mm'), 3),
             _fmt_num(gain.get('total_length_mm'), 3)],
            ['平均长度 mm', _fmt_num(metrics3.get('mean_length_mm'), 3),
             _fmt_num(metrics5.get('mean_length_mm'), 3),
             _fmt_num(gain.get('mean_length_mm'), 3)],
            ['失败总数', _fmt_int(metrics3.get('failed_total')),
             _fmt_int(metrics5.get('failed_total')), _fmt_delta(gain.get('failed_total'))],
            ['无 2D XY 候选失败', _fmt_int(metrics3.get('failed_no_candidate')),
             _fmt_int(metrics5.get('failed_no_candidate')),
             _fmt_delta(gain.get('failed_no_candidate'))],
            ['无抬升候选失败', _fmt_int(metrics3.get('failed_unplaceable')),
             _fmt_int(metrics5.get('failed_unplaceable')),
             _fmt_delta(gain.get('failed_unplaceable'))],
            ['实际 3D 交叉数', _fmt_int(metrics3.get('crossings_total')),
             _fmt_int(metrics5.get('crossings_total')), DASH],
            ['2D 平铺交叉数（假设）', _fmt_int(metrics3.get('flattened_crossings_2d')),
             _fmt_int(metrics5.get('flattened_crossings_2d')),
             _fmt_delta(gain.get('flattened_crossings_2d'))],
            ['消除的交叉数（平铺−实际3D）', _fmt_int(metrics3.get('crossings_avoided')),
             _fmt_int(metrics5.get('crossings_avoided')),
             _fmt_delta(gain.get('crossings_avoided'))],
            ['3D 净空违规', _fmt_int(metrics3.get('clearance_violations')),
             _fmt_int(metrics5.get('clearance_violations')), DASH],
            ['曲率违规', _fmt_int(metrics3.get('curvature_violations')),
             _fmt_int(metrics5.get('curvature_violations')), DASH],
            ['最小真实 3D 距离 mm',
             _fmt_num(metrics3.get('min_3d_distance_excluding_crossings_mm'), 6),
             _fmt_num(metrics5.get('min_3d_distance_excluding_crossings_mm'), 6), DASH],
            ['最小曲率半径 mm', _fmt_num(metrics3.get('min_curvature_radius_mm'), 7),
             _fmt_num(metrics5.get('min_curvature_radius_mm'), 7), DASH],
            ['验收', _verdict_text({'validation': {'present': entry.get('present', {}).get('3'),
                                                 'passed': metrics3.get('validation_passed')}}),
             _verdict_text({'validation': {'present': entry.get('present', {}).get('5'),
                                          'passed': metrics5.get('validation_passed')}}), DASH],
        ]
        lines.extend(_md_table(detail_headers, detail_rows, ['---', '---:', '---:', '---:']))
        lines.append('')

        lines.append('分平面：')
        lines.append('')
        plane_headers = ['平面', '3 层布通', '5 层布通', '布通增益', '3 层抬升',
                         '5 层抬升', '3 层新增', '5 层新增']
        plane_rows = []
        for plane in PLANES:
            info = (entry.get('per_plane') or {}).get(plane) or {}
            plane_rows.append([plane, _fmt_int(info.get('routed_3')),
                               _fmt_int(info.get('routed_5')),
                               _fmt_delta(info.get('gain')),
                               _fmt_int(info.get('lifted_3')),
                               _fmt_int(info.get('lifted_5')),
                               _fmt_int(info.get('new_3')),
                               _fmt_int(info.get('new_5'))])
        lines.extend(_md_table(plane_headers, plane_rows,
                              ['---', '---:', '---:', '---:', '---:', '---:',
                               '---:', '---:']))
        lines.append('')

        parts = entry.get('per_layer_flat_parts') or {}
        if any(parts.values()):
            lines.append('每层 flat 段数量（含基线 flat 段，不重复计路线数）：')
            lines.append('')
            max_layers = max([len(parts.get('3') or {}), len(parts.get('5') or {})])
            layer_headers = ['层', '3 层 flat 段', '5 层 flat 段']
            layer_rows = []
            for layer in range(max_layers):
                layer_rows.append([
                    layer,
                    _fmt_int((parts.get('3') or {}).get(str(layer))),
                    _fmt_int((parts.get('5') or {}).get(str(layer)))])
            lines.extend(_md_table(layer_headers, layer_rows,
                                  ['---', '---:', '---:']))
            lines.append('')
        lines.append(f'> 结论：{entry.get("conclusion")}')
        lines.append('')

    lines.append('## 3. 解读提示')
    lines.append('')
    lines.append('- 3 层只有 1 个中间层（z=0.25 mm），5 层有 3 个中间层'
                 '（z=0.125/0.25/0.375 mm），可选抬升高度更多。')
    lines.append('- 新增收益来自“原本 2D 无合法候选或无法插入”的失败路线；'
                 '抬升后部分路线可以绕开同层冲突。')
    lines.append('- 抬升代价：每条 lifted 路线多 2 次 S 曲线 transition（长度增加约 '
                 '2×footprint）；实际 3D 交叉数与验收结论以 validate25d 为准。')
    lines.append('- 若 5 层相对 3 层增益为正且验收全部 PASS，则说明“增加高度”是有效手段。')
    return '\n'.join(lines) + '\n'


def _observed_run_flags(runs):
    """Delivered run25d flags, when all present runs agree.

    Returns ``(common_flags, per_run_flags)`` where ``common_flags`` is a dict
    with passes/rr_rounds/budget/flat_probe/rr_targets/rr_rip when every present
    run shares the same configuration, else ``None``.
    """
    keys = ('passes', 'rr_rounds', 'budget', 'flat_probe', 'rr_targets', 'rr_rip')
    per_run = {}
    for key in RUN_KEYS:
        run = runs.get(key) or {}
        if not run.get('present'):
            continue
        config = run.get('config') if isinstance(run.get('config'), dict) else {}
        per_run[key] = dict(
            passes=_pick_int(config.get('passes')),
            rr_rounds=_pick_int(config.get('rr_rounds')),
            budget=_pick_int(config.get('candidate_budget'),
                             config.get('budget')),
            flat_probe=_pick_int(config.get('flat_probe')),
            rr_targets=_pick_int(config.get('rr_targets')),
            rr_rip=_pick_int(config.get('rr_rip')),
        )
    if not per_run:
        return None, per_run
    first = next(iter(per_run.values()))
    if any(values != first for values in per_run.values()):
        return None, per_run
    common = {key: first.get(key) for key in keys if first.get(key) is not None}
    return common, per_run


def _flag_text(flags):
    parts = []
    for flag in ('passes', 'rr-rounds', 'budget', 'flat-probe', 'rr-targets',
                 'rr-rip'):
        value = flags.get(flag.replace('-', '_'))
        if value is not None:
            parts.append(f'--{flag} {value}')
    return ' '.join(parts)


def _run25d_command(scheme, n_layers, flags):
    parts = [f'& $py -m four_side_1024.fsd25d.run25d --scheme {scheme}',
             f'--layers {n_layers}']
    suffix = _flag_text(flags)
    if suffix:
        parts.append(suffix)
    return ' '.join(parts)


def _render_reproduce_md(overview, effect):
    model = overview.get('geometric_model') or {}
    baselines = overview.get('baselines') or {}
    runs = overview.get('runs') or {}
    root_display = overview.get('root')
    python_exe = str(CFG.ROOT / '.venv' / 'Scripts' / 'python.exe')
    if not (CFG.ROOT / '.venv' / 'Scripts' / 'python.exe').exists():
        python_exe = 'python'
    project_display = str(CFG.ROOT)
    layer_stacks = model.get('layer_stacks') or {}
    interface_layers = model.get('interface_layer') or {}
    interface_z = model.get('interface_z_mm') or {}
    dz_map = model.get('transition_dz_mm') or {}
    footprint_map = model.get('transition_footprint_mm') or {}

    lines = [
        '# 五层 2.5D 实验复现说明（REPRODUCE_25D.md）',
        '',
        '> 本文件由 `four_side_1024/fsd25d/summarize25d.py` 自动生成，重新运行该脚本会覆盖。',
        '> 输入（冻结 2D 输出、`routes_25d.json`、validation 输出）一律只读；本脚本只写 '
        '`summary/` 与本文件，不修改任何路线数据。',
        '',
        f'- 生成时间（UTC）：{overview.get("generated_utc")}',
        f'- 数据根目录：`{root_display}`',
        f'- 项目根目录：`{project_display}`',
        '',
        '## 1. 环境',
        '',
        '| 项 | 值 |',
        '|---|---|',
        f'| 操作系统 | Windows（PowerShell） |',
        f'| Python 解释器 | `{python_exe}` |',
        f'| Python 版本 | {overview.get("python_version") or DASH} |',
        f'| 项目根目录 | `{project_display}` |',
        f'| 拓扑/连接 CSV SHA256 | '
        + ('`' + '`, `'.join(f'{scheme}: {info.get("csv_sha256")}'
                             for scheme, info in baselines.items()
                             if info.get('csv_sha256')) + '`'
           if any(info.get('csv_sha256') for info in baselines.values()) else DASH)
        + ' |',
        '',
        '## 2. 冻结输入（只读，不得修改）',
        '',
        '### 2.1 2D 基线（方案 A / B）',
        '',
    ]
    baseline_headers = ['方案', '平面', '文件路径', '布通', '文件 SHA256', 'CSV SHA256']
    baseline_rows = []
    for scheme in SCHEMES:
        info = baselines.get(scheme) or {}
        for plane in PLANES:
            file_info = (info.get('files') or {}).get(plane) or {}
            baseline_rows.append([
                scheme,
                plane,
                f'`{file_info.get("path") or DASH}`',
                _fmt_int(file_info.get('routed')),
                f'`{file_info.get("sha256") or DASH}`',
                f'`{file_info.get("csv_sha256") or DASH}`',
            ])
    lines.extend(_md_table(baseline_headers, baseline_rows,
                           ['---', '---', '---', '---:', '---', '---']))
    lines.append('')
    baselines_note = []
    for scheme in SCHEMES:
        info = baselines.get(scheme) or {}
        baselines_note.append(
            f'- 方案 {scheme}：{info.get("label") or scheme}，算法 '
            f'`{info.get("algorithm") or DASH}`，预期布通 '
            f'{(info.get("expected_baseline_routed")) or DASH}/1024，'
            f'根目录 `{info.get("root") or DASH}`')
    lines.extend(baselines_note)
    lines.append('')
    lines.append('> 基线目录与文件均为冻结产物；本实验只读取，不写回。'
                 '`_smoke/` 仅为调试样本（B/5、10 条新增），不参与正式统计。')
    lines.append('')

    lines.extend([
        '### 2.2 2.5D 数据根目录',
        '',
        '| 子目录/文件 | 生成者 | 说明 |',
        '|---|---|---|',
        '| `scheme{A,B}/layers{3,5}/routes_25d.json` | run25d | 完整 3D 路线数据（schema v1） |',
        '| `scheme{A,B}/layers{3,5}/run_summary.json` | run25d | 运行配置与统计 |',
        '| `scheme{A,B}/layers{3,5}/run.log` | run25d | 运行日志 |',
        '| `validation/<scheme>/layers<N>.json` | validate25d | 每个 run 的独立 3D 验收结果 |',
        '| `validation/all_validation.json` | validate25d | 验收汇总（按 run label 跨调用合并） |',
        '| `validation/_smoke/B_layers5.json` | validate25d | smoke 调试样本验收（不参与正式统计） |',
        '| `figures/<scheme>/layers<N>/*.png` | plots25d | 分层平面图、2D 对比图、3D 视图 |',
        '| `comparison/*.png` + `plots_manifest.json` | plots25d | 基线对照、层数效应、抬升统计 |',
        '| `summary/crossing_metrics.json` | extra_metrics25d | 2D 平铺交叉数 vs 实际 3D 交叉数 |',
        '| `summary/` | summarize25d | overview/comparison/layers_effect/failed_analysis |',
        '| `REPRODUCE_25D.md` | summarize25d | 本文件 |',
        '',
        '## 3. 几何模型',
        '',
        '### 3.1 层高、接口与升降高度',
        '',
        '| 层数 | `layers_z_mm` | 接口层 (`z1`/`z2`) | z1 接口 z (mm) | z2 接口 z (mm) | '
        '可能的 `|dz|` (mm) | transition footprint (mm) |',
        '|---:|---|---|---:|---:|---|---|',
    ])
    for n_layers in LAYER_COUNTS:
        stack = layer_stacks.get(str(n_layers)) or list(CFG.LAYER_STACKS[n_layers])
        ilayers = interface_layers.get(str(n_layers)) or dict(
            CFG.INTERFACE_LAYER[n_layers])
        z_info = interface_z.get(str(n_layers)) or {}
        dz_values = dz_map.get(str(n_layers)) or []
        footprints = footprint_map.get(str(n_layers)) or {}
        footprint_text = '; '.join(
            f'{dz:.6f} → {footprints.get(f"{dz:.6f}", DASH)} mm' for dz in dz_values)
        lines.append(
            f'| {n_layers} | `{stack}` | {ilayers.get("z1")} / {ilayers.get("z2")} | '
            f'{z_info.get("z1")} | {z_info.get("z2")} | '
            f'{", ".join(f"{dz:.6f}" for dz in dz_values) or DASH} | '
            f'{footprint_text or DASH} |')
    lines.extend([
        '',
        '### 3.2 工艺与几何常数',
        '',
        '| 常数 | 值 |',
        '|---|---|',
        f'| 板面 BOARD_MM | {model.get("board_mm")} (mm × mm) |',
        f'| 波导宽度 WIDTH_MM | {model.get("width_mm")} mm |',
        f'| 边缘间距 EDGE_GAP_MM | {model.get("edge_gap_mm")} mm |',
        f'| 三维净空 CLEARANCE_MM | {model.get("clearance_mm")} mm |',
        f'| 弯曲半径 RADIUS_MM | {model.get("radius_mm")} mm |',
        f'| 最小交叉角 MIN_CROSS_ANGLE_DEG | {model.get("min_cross_angle_deg")} ° |',
        f'| 同层 2D 交叉策略 | {model.get("crossing_policy")} |',
        f'| 交叉 3D 净空豁免窗口 | ±{model.get("crossing_exemption_window_mm")} mm '
        f'（仅同层 strict 2D 合法交叉点附近） |',
        '',
        '### 3.3 升降 transition（垂直平面内 S 曲线）',
        '',
        '- 每条 lifted 路线在 2D 路径的直线段上放置 **两段** transition：'
        '接口层 → 旅行层（`travel_layer`）→ 目标接口层；',
        '- 每段 transition 为垂直平面内两段 R=40 mm 圆弧组成的 S 曲线，关于中点中心对称、'
        'G1 连续；起终点切向水平且与所在直线段方向一致（方向轴对齐）；',
        '- `theta = acos(1 - |dz| / (2R))`，水平投影 `footprint = 2R sin(theta)`，'
        '弧长 `length = 2R theta`，其中 `dz = z1 - z0`；',
        '- 完整三维路径最小曲率半径 = 40 mm（验收要求 ≥ 39.96 mm）；',
        '- flat 段：方案 A（D56）允许轴对齐直线 + R=40 的 90° 弧 + 短 S 弧；'
        '方案 B（ortho90）只允许轴对齐直线 + 精确 90°、R=40 的弧；',
        '- 每条 lifted 路线 `n_transitions = 2`；flat 路线 `n_transitions = 0`。',
        '',
        '## 4. 复现命令（PowerShell，按顺序执行）',
        '',
        '### 4.0 准备',
        '',
        '```powershell',
        f'cd "{project_display}"',
        '$py = ".\\.venv\\Scripts\\python.exe"',
        '& $py --version   # 需要 Python 3.10.x',
        '```',
        '',
        '### 4.1 四个 2.5D 布线运行（run25d，每个约数分钟到数十分钟，取决于机器负载）',
        '',
        '```powershell',
    ])
    observed_flags, per_run_flags = _observed_run_flags(runs)
    command_flags = observed_flags or dict(passes=3, rr_rounds=2, budget=300,
                                           flat_probe=40)
    for scheme in SCHEMES:
        for n_layers in LAYER_COUNTS:
            lines.append(_run25d_command(scheme, n_layers, command_flags))
    lines.extend([
        '```',
        '',
        '四个 run 相互独立（各写 `scheme{X}/layers{Y}/`，互不覆盖），可按任意顺序串行执行。',
        '',
    ])
    if observed_flags:
        if len(per_run_flags) == len(RUN_KEYS):
            scope = '四个 run 配置一致'
        else:
            scope = f'现有 {len(per_run_flags)} 个 run 配置一致'
        lines.append(
            '- 上面的参数取自**实际交付 run 的 `run_summary.json`**'
            f'（{scope}；任务约定的 canonical 配置为 '
            '`--passes 3 --rr-rounds 2 --budget 300`）。')
    else:
        lines.append(
            '- 此时尚未读到四个完整 `run_summary.json`，以上为任务约定的 canonical '
            '配置（`--passes 3 --rr-rounds 2 --budget 300`）；'
            '数据生成后本段会自动替换为实际配置。')
    if per_run_flags and not observed_flags:
        lines.append('- 各 run 实际配置不一致（例如不同 `--budget`/`--flat-probe`），'
                     '见 §7 状态表；复现时请对每个 run 使用其对应参数。')
    lines.extend([
        '',
        '### 4.2 独立三维验收（validate25d）',
        '',
        '```powershell',
        f'& $py -m {VALIDATE_MODULE}{VALIDATE_EXTRA_ARGS}',
        '# 可选用法：只验部分 run / 指定输出目录 / 关闭端口 CSV 校验 / 单独验 smoke 样本',
        f'& $py -m {VALIDATE_MODULE}{VALIDATE_EXTRA_ARGS} --only schemeA/layers5',
        f'& $py -m {VALIDATE_MODULE}{VALIDATE_EXTRA_ARGS} --out '
        f'{root_display}/validation',
        f'& $py -m {VALIDATE_MODULE}{VALIDATE_EXTRA_ARGS} --no-port-csv '
        '--max-violations 500',
        f'& $py -m {VALIDATE_MODULE}{VALIDATE_EXTRA_ARGS} --input '
        f'{root_display}/_smoke/routes_25d.json',
        '```',
        '',
        '- 必须在全部 run 完成后执行；缺省 `--root` 即本数据根目录，自动发现存在的 '
        '`scheme{A,B}/layers{3,5}/routes_25d.json`；`--only` 过滤单个 run，'
        '`--input` 指定单个 routes 文件或目录。',
        f'- 输出：`{root_display}/validation/<scheme>/layers<N>.json`（每个 run 一个）与 '
        f'`{root_display}/validation/all_validation.json`（按 run label 跨调用合并，'
        'smoke 与 4 个正式 run 可共存）。',
        '- 退出码：0 = 所有处理的 run 均 PASS；1 = 有 run 未通过；2 = 没有任何输入/过滤匹配。',
        '- per-run JSON 顶层字段：`passed`、`routed/failed/total`、`failure_reasons`、'
        '`crossings{total,by_layer}`、`violations[]`、`violation_kinds`、`counts{9 项}`、'
        '`stats{transitions,lifted,flat_parts,total_length_mm,...}`、'
        '`min_3d_distance_mm`、`min_3d_distance_excluding_crossings_mm`、'
        '`min_3d_distance_including_crossings_mm`、`min_curvature_radius_mm`、`layer_2d`、'
        '`runtime_seconds`；summarize25d 消费这些字段生成对照表与验收列。',
        '- summarize25d 会递归扫描 `validation/**/*.json` 并按 scheme/layers 自动匹配，'
        '不依赖具体文件名；`all_validation.json` 若只有部分 run 也能被逐条识别。',
        '',
        '### 4.3 对照图（plots25d）',
        '',
        '```powershell',
        f'& $py -m {PLOTS_MODULE}{PLOTS_EXTRA_ARGS}',
        '```',
        '',
        f'- 输出到 `{root_display}/figures/<scheme>/layers<N>/`：`layer_<k>.png`（k=0..N-1）、'
        '`layers_2d.png`、`view3d.png`、`top_view_by_height.png`；',
        f'- 输出到 `{root_display}/comparison/`：`baseline_vs_25d_schemeA.png`、'
        '`baseline_vs_25d_schemeB.png`、`layers_effect.png`、`lift_statistics.png`、'
        '`plots_manifest.json`（图件清单/runs 表/caveats）；',
        '- 缺省不往 run 目录写图；需要与 `routes_25d.json` 放在一起时加 `--in-run-dir`；',
        '- 可选：`--runs schemeA/layers3,schemeA/layers5` 只画指定 run；`--include-smoke` '
        '追加 `_smoke` 调试样本。',
        '',
        '### 4.4 额外交叉指标（extra_metrics25d，可选但推荐）',
        '',
        '```powershell',
        '& $py -m four_side_1024.fsd25d.extra_metrics25d',
        '```',
        '',
        '- 需在四个 run 的 `routes_25d.json` 与 `validation/<scheme>/layers<N>.json` '
        '都存在后运行；读取它们并写 `summary/crossing_metrics.json`。',
        '- 含义：把每个 run 的全部路线“平铺回接口高度”得到一个假设性 2D 布局，'
        '用冻结 `fslw` strict 2D pair kernel 统计其交叉总数（`flattened_total`），'
        '再与 `validate25d` 的实际 3D 同层交叉数（`actual_3d_crossings`）比较；'
        '二者之差 `crossings_avoided` 即抬升/分层消除的交叉数。',
        '- `summarize25d` 会自动读取该文件，把“2D 平铺交叉数 / 消除的交叉数”写入 '
        '`overview.json` 与 `comparison_table.md`；文件缺失时这两列为 “' + DASH + '”。',
        '- 注意该指标是**描述性对照**，不作为验收 PASS 判据（PASS 仍只看 validate25d '
        '的 counts 与 min 距离/曲率）。',
        '',
        '### 4.5 汇总统计（本脚本）',
        '',
        '```powershell',
        '& $py -m four_side_1024.fsd25d.summarize25d --root '
        'outputs/four_side_1024_v2_25d_v01',
        '```',
        '',
        '### 4.6 一次性顺序执行（可选）',
        '',
        '```powershell',
        '$py = ".\\.venv\\Scripts\\python.exe"',
        'foreach ($scheme in @("A", "B")) {',
        '  foreach ($layers in @(3, 5)) {',
        f'    & $py -m four_side_1024.fsd25d.run25d --scheme $scheme --layers $layers '
        f'{_flag_text(command_flags)}',
        '    if ($LASTEXITCODE -ne 0) { throw "run25d failed: $scheme/$layers" }',
        '  }',
        '}',
        f'& $py -m {VALIDATE_MODULE}{VALIDATE_EXTRA_ARGS}',
        f'& $py -m {PLOTS_MODULE}{PLOTS_EXTRA_ARGS}',
        '& $py -m four_side_1024.fsd25d.extra_metrics25d',
        '& $py -m four_side_1024.fsd25d.summarize25d --root '
        'outputs/four_side_1024_v2_25d_v01',
        '```',
        '',
        '### 4.7 调试样本 smoke（可选，不参与正式统计）',
        '',
        '```powershell',
        f'& $py -m four_side_1024.fsd25d.run25d --scheme B --layers 5 --passes 1 '
        f'--rr-rounds 0 --budget 300 --limit 10 --out {root_display}/_smoke',
        f'& $py -m {VALIDATE_MODULE}{VALIDATE_EXTRA_ARGS} --input '
        f'{root_display}/_smoke/routes_25d.json',
        '```',
        '',
        '> `summarize25d` 只汇总 `scheme{A,B}/layers{3,5}` 四个正式目录，'
        '`_smoke` 不参与统计；`_smoke` 的验收结果保存在 '
        '`validation/_smoke/B_layers5.json`。',
        '',
        '## 5. 预期输出目录树',
        '',
        '```text',
        f'{root_display}/',
        '├─ schemeA/',
        '│  ├─ layers3/  routes_25d.json  run_summary.json  run.log',
        '│  └─ layers5/  routes_25d.json  run_summary.json  run.log',
        '├─ schemeB/',
        '│  ├─ layers3/  routes_25d.json  run_summary.json  run.log',
        '│  └─ layers5/  routes_25d.json  run_summary.json  run.log',
        '├─ _smoke/                        # 调试样本（B/5，10 条新增），不参与正式统计',
        '├─ validation/                    # validate25d',
        '│  ├─ A/layers3.json  A/layers5.json  B/layers3.json  B/layers5.json',
        '│  ├─ _smoke/B_layers5.json       # 可选',
        '│  └─ all_validation.json         # 按 run label 跨调用合并',
        '├─ figures/                       # plots25d',
        '│  └─ scheme{A,B}/layers{3,5}/  layer_<k>.png  layers_2d.png  view3d.png '
        'top_view_by_height.png',
        '├─ comparison/                    # plots25d',
        '│  ├─ baseline_vs_25d_schemeA.png  baseline_vs_25d_schemeB.png',
        '│  ├─ layers_effect.png  lift_statistics.png',
        '│  └─ plots_manifest.json',
        '├─ summary/                       # extra_metrics25d + summarize25d',
        '│  ├─ crossing_metrics.json        # extra_metrics25d：2D 平铺 vs 实际 3D 交叉',
        '│  ├─ overview.json',
        '│  ├─ comparison_table.md',
        '│  ├─ layers_effect.json',
        '│  ├─ layers_effect.md',
        '│  └─ failed_analysis.json',
        '└─ REPRODUCE_25D.md               # summarize25d（本文件）',
        '```',
        '',
        '## 6. 预期结果与验收口径',
        '',
        '### 6.1 本次汇总时的实际数据',
        '',
    ])
    headers = ['方案', '层数', '数据', '2D 基线布通', '2.5D 布通', '新增', '抬升',
               '升降次数', '实际 3D 交叉数', '2D 平铺交叉数', '消除交叉数',
               '总长 (mm)', '验收']
    aligns = ['---', '---', '---', '---:', '---:', '---:', '---:', '---:', '---:',
              '---:', '---:', '---:', '---']
    rows = []
    for row in overview.get('comparison_rows') or []:
        if row.get('kind') == 'baseline':
            continue
        run = runs.get(f'{row.get("scheme")}/{row.get("n_layers")}') or {}
        rows.append([
            row.get('scheme'),
            row.get('n_layers'),
            '已生成' if row.get('present') else '缺失',
            _fmt_int(row.get('original_2d_routed')),
            _fmt_int(row.get('routed_25d')),
            _fmt_int(row.get('new_routed')),
            _fmt_int(run.get('lifted')),
            _fmt_int(row.get('transitions')),
            _fmt_int(row.get('crossings_total')),
            _fmt_int(row.get('flattened_crossings_2d')),
            _fmt_int(row.get('crossings_avoided')),
            _fmt_num(row.get('total_length_mm'), 3),
            _verdict_text({'validation': {'present': row.get('validation_present'),
                                          'passed': row.get('validation_passed')}}),
        ])
    lines.extend(_md_table(headers, rows, aligns))
    lines.append('')
    lines.extend([
        '### 6.2 独立验收判据（validate25d / SCHEMA_25D.md §4）',
        '',
        '- `counts` 中全部计数为 0：structure / port / xy_model / curvature / clearance / '
        'layer_2d / self_clearance / board；',
        '- 不同路线之间真实三维中心线最小距离 ≥ 0.08 mm（仅同层 strict 2D 合法交叉点 '
        '±2.5 mm 窗口内豁免）；',
        '- 完整三维路径最小曲率半径 ≥ 39.96 mm（R=40 mm，容差 0.1%）；',
        '- 每层 flat 段作为独立 prepared route 重跑冻结 strict 2D 审计：violations 必须为空；',
        '- `passed = true` 才可写入报告；**不得把 2D PASS 当作 3D PASS**。',
        '',
        '### 6.2.1 交叉指标口径（描述性，不参与 PASS 判定）',
        '',
        '- **实际 3D 交叉数**：`validate25d` 按层重跑冻结 strict 2D 审计得到的同层合法交叉'
        '数之和（真实三维布局）；',
        '- **2D 平铺交叉数**：`extra_metrics25d` 把该 run 全部路线平铺回接口高度后，用冻结 '
        'strict 2D pair kernel 统计的假设性 2D 交叉总数；',
        '- **消除的交叉数** = 2D 平铺 − 实际 3D，表示抬升/分层实际消除的交叉量；',
        '- 三者都不改变验收结论；正式 PASS/FAIL 只看 `counts` 全 0 与 min 距离/曲率条件。',
        '',
        '### 6.3 复现自检清单',
        '',
        '- [ ] 4 个 run 目录均含 `routes_25d.json` + `run_summary.json`；',
        '- [ ] 各 `routes_25d.json` 的 `csv_sha256` 一致（见 §2.1）；',
        '- [ ] `validation/all_validation.json` 中 4 个 run 全部 `passed = true`；',
        '- [ ] `summary/overview.json` 中 `selfcheck.all_runs_present = true`、'
        '`selfcheck.all_validations_passed = true`；',
        '- [ ] `summary/comparison_table.md` 四行 A/B × 3/5 完整（无 “缺失”）；',
        '- [ ] `summary/layers_effect.md` 给出“5 层相对 3 层”的净增益结论；',
        '- [ ] `summary/crossing_metrics.json` 存在且 4 个 run 都有 '
        '`flattened_total` / `crossings_avoided`；',
        '- [ ] `summary/failed_analysis.json` 单独列出 `no_2d_candidate_at_all` 路线。',
        '',
    ])

    # 6.4 debug-sample validation baseline (optional, never part of formal stats)
    smoke = overview.get('smoke_validation') or {}
    lines.append('### 6.4 调试样本 smoke 的独立验收基线（validate25d，可选）')
    lines.append('')
    if smoke.get('present'):
        smoke_stats = smoke.get('stats') or {}
        smoke_counts = smoke.get('counts') or {}
        if smoke_counts and all(value == 0 for value in smoke_counts.values()):
            counts_text = '全部为 0'
        elif smoke_counts:
            counts_text = '存在非零计数（见 validation JSON）'
        else:
            counts_text = DASH
        lines.append(f'- 样本：`{smoke.get("label") or "smoke/B_layers5"}`'
                     f'，报告文件：`{smoke.get("source")}`')
        lines.append('')
        smoke_rows = [
            ['验收结论', 'PASS' if smoke.get('passed') is True else
             ('FAIL' if smoke.get('passed') is False else DASH)],
            ['routed / failed', f'{_fmt_int(smoke.get("routed"))} / '
                                f'{_fmt_int(smoke.get("failed"))}'],
            ['实际 3D 交叉数（各层求和）', _fmt_int(smoke.get('crossings_total'))],
            ['最小真实 3D 距离（排除合法交叉）', _fmt_num(
                smoke.get('min_3d_distance_excluding_crossings_mm'), 6)],
            ['最小真实 3D 距离（含交叉，参考）', _fmt_num(
                smoke.get('min_3d_distance_including_crossings_mm'), 6)],
            ['最小曲率半径 mm', _fmt_num(smoke.get('min_curvature_radius_mm'), 7)],
            ['违规计数 counts', counts_text],
            ['transitions / lifted / flat_parts',
             f'{_fmt_int(smoke_stats.get("transitions"))} / '
             f'{_fmt_int(smoke_stats.get("lifted"))} / '
             f'{_fmt_int(smoke_stats.get("flat_parts"))}'],
            ['总波导长度 mm', _fmt_num(smoke_stats.get('total_length_mm'), 6)],
            ['验收耗时 s', _fmt_num(smoke.get('runtime_seconds'), 2)],
        ]
        lines.extend(_md_table(['项', '值'], smoke_rows, ['---', '---']))
        lines.append('')
        lines.append('> 该 smoke 基线只用于验证“数据格式 + 独立验收器”链路本身，'
                     '不参与正式统计。')
    else:
        lines.append('当前未找到 `validation/_smoke/*.json`；可生成后重跑本脚本：')
        lines.append('')
        lines.append('```powershell')
        lines.append(f'& $py -m {VALIDATE_MODULE}{VALIDATE_EXTRA_ARGS} --input '
                     f'{root_display}/_smoke/routes_25d.json')
        lines.append('```')
    lines.append('')
    lines.extend([
        '## 7. 本次汇总时的运行状态',
        '',
    ])
    state_headers = ['方案/层数', '数据状态', '布通', '耗时 s', 'passes',
                     'rr_rounds', 'budget', 'flat_probe', 'limit',
                     'min 3D 距离 mm', 'min R mm', '验收']
    state_rows = []
    for scheme in SCHEMES:
        for n_layers in LAYER_COUNTS:
            key = f'{scheme}/{n_layers}'
            run = runs.get(key) or {}
            config = run.get('config') or {}
            state_rows.append([
                key,
                '已生成' if run.get('present') else '缺失',
                _fmt_int(run.get('routed')),
                _fmt_num(run.get('seconds'), 1),
                _fmt_int(config.get('passes')),
                _fmt_int(config.get('rr_rounds')),
                _fmt_int(config.get('candidate_budget')),
                _fmt_int(config.get('flat_probe')),
                _fmt_int(config.get('limit')),
                _fmt_num(run.get('min_3d_distance_excluding_crossings_mm'), 6),
                _fmt_num(run.get('min_curvature_radius_mm'), 7),
                _verdict_text(run),
            ])
    lines.extend(_md_table(state_headers, state_rows,
                           ['---', '---', '---:', '---:', '---:', '---:', '---:',
                            '---:', '---:', '---:', '---:', '---']))
    lines.append('')
    lines.append('## 8. 产出文件说明')
    lines.append('')
    lines.extend([
        '| 文件 | 生成者 | 内容 |',
        '|---|---|---|',
        '| `summary/overview.json` | summarize25d | 每个 run 的统计 + 对照表字段 + 自检 |',
        '| `summary/comparison_table.md` | summarize25d | A/B × 3/5（+2D 基线）对照表 |',
        '| `summary/layers_effect.json` | summarize25d | 3 层 vs 5 层对比（机器可读） |',
        '| `summary/layers_effect.md` | summarize25d | 3 层 vs 5 层对比（报告可用） |',
        '| `summary/failed_analysis.json` | summarize25d | 失败按原因/方案/平面/层数拆分 |',
        '| `summary/crossing_metrics.json` | extra_metrics25d | 2D 平铺 vs 实际 3D 交叉数（被 '
        'summarize25d 读取） |',
        '| `figures/`, `comparison/` | plots25d | 分层平面图、3D 视图、基线对照图 |',
        '| `REPRODUCE_25D.md` | summarize25d | 本文件 |',
        '',
        '> 缺失数据策略：任何 run / validation 文件缺失时，相关字段写 `null` 并在 '
        '`summary/overview.json` 的 `warnings` 中记录；脚本不 crash、不修改输入。',
        '',
    ])
    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def _resolve_root(value):
    if value is None:
        return Path(CFG.V25D_ROOT)
    path = Path(value)
    if path.is_absolute():
        return path
    candidate = Path(CFG.ROOT) / path
    if candidate.exists():
        return candidate
    return Path.cwd() / path


def collect(root, log=print):
    root = Path(root)
    warnings = []
    runs = {}
    forensics = {}
    for scheme in SCHEMES:
        for n_layers in LAYER_COUNTS:
            key = f'{scheme}/{n_layers}'
            entry, forensic, _payload, _summary = _load_run(root, scheme, n_layers)
            runs[key] = entry
            forensics[key] = forensic
            warnings.extend(entry.get('warnings') or [])

    # cross-run: "5-layer success" for every scheme
    for scheme in SCHEMES:
        run5 = runs[f'{scheme}/5']
        for n_layers in LAYER_COUNTS:
            run = runs[f'{scheme}/{n_layers}']
            if run5.get('present'):
                run['five_layer_routed'] = run5.get('routed_25d')
                run['five_layer_run'] = f'{scheme}/5'
            else:
                run['five_layer_routed'] = None
                run['five_layer_run'] = None

    runs, smoke_validation = _attach_validations(root, runs, warnings)
    crossing_metrics = _load_crossing_metrics(root, warnings)
    _attach_crossing_metrics(runs, crossing_metrics, warnings)
    model = _build_geometric_model(runs, warnings)
    baselines = _build_baseline_info(warnings)
    effect = _build_layers_effect(runs, root, warnings)

    # surface run/validation availability in the per-run warnings
    for scheme in SCHEMES:
        for n_layers in LAYER_COUNTS:
            run = runs[f'{scheme}/{n_layers}']
            validation = run.get('validation') or {}
            if run.get('present') and not validation.get('present'):
                run['warnings'] = list(run.get('warnings') or []) + [
                    'independent validation missing; validation fields are null']
            elif validation.get('passed') is False:
                run['warnings'] = list(run.get('warnings') or []) + [
                    'independent validation FAILED']

    rows = _build_comparison_rows(runs)
    failed = _build_failed_analysis(runs, forensics, root, warnings)

    runs_present = [key for key in RUN_KEYS if runs[key].get('present')]
    runs_missing = [key for key in RUN_KEYS if not runs[key].get('present')]
    validation_present = [key for key in RUN_KEYS
                          if (runs[key].get('validation') or {}).get('present')]
    validation_missing = [key for key in RUN_KEYS if key not in validation_present]
    validation_passed = [key for key in validation_present
                         if (runs[key].get('validation') or {}).get('passed') is True]
    csv_hashes = {key: runs[key].get('csv_sha256') for key in runs_present
                  if runs[key].get('csv_sha256')}
    selfcheck = dict(
        runs_expected=list(RUN_KEYS),
        runs_present=runs_present,
        runs_missing=runs_missing,
        all_runs_present=not runs_missing,
        validation_present=validation_present,
        validation_missing=validation_missing,
        validations_passed=validation_passed,
        all_validations_passed=(bool(validation_present)
                                and len(validation_passed) == len(RUN_KEYS)),
        all_validations_exist=not validation_missing,
        csv_sha256_by_run=csv_hashes,
        csv_sha256_consistent=len(set(csv_hashes.values())) <= 1,
        smoke_validation_present=smoke_validation is not None,
        smoke_validation_passed=(smoke_validation or {}).get('passed'),
        crossing_metrics_present=bool(crossing_metrics),
        crossing_metrics_runs=sorted(crossing_metrics),
        warnings_count=len(warnings) + len(effect.get('warnings') or []),
    )

    overview = dict(
        schema=SCHEMA_SUMMARY,
        generated_utc=_now_utc(),
        generator='four_side_1024.fsd25d.summarize25d',
        python_version=sys.version.split()[0],
        root=_display_path(root),
        root_abs=str(Path(root)),
        experiment='V2 五层 2.5D（2.5D routing: flat / lifted）',
        description='2D 冻结基线 + 3/5 层 2.5D 布线与独立 3D 验收的汇总统计',
        total_routes_per_run=TOTAL_ROUTES_PER_RUN,
        field_notes={
            'original_2d_routed': '2D 冻结基线在该方案的布通数（A=752，B=262）',
            'routed_25d': '本次 2.5D 布线布通数（=五层实验布通数）',
            'five_layer_routed': '同方案 5 层 run 的布通数（用于对照表“5 层布通”列）',
            'new_routed': 'routed_25d - original_2d_routed',
            'lifted': '新增路线中抬升到中间层的条数（每条含 2 次 transition）',
            'flat_added': '新增路线中保持 flat 的条数',
            'crossings_total': 'validation 中各层同层合法交叉数之和（实际空间交叉）',
            'clearance_violations': 'validation counts.clearance_violations',
            'curvature_violations': 'validation counts.curvature_violations',
            'min_3d_distance_mm': 'validation 中排除合法同层交叉后的最小真实三维中心线距离',
            'min_curvature_radius_mm': 'validation 从三维采样点独立估计的最小曲率半径',
            'flattened_crossings_2d': '把该 run 全部路线平铺回接口高度后，按冻结 strict 2D '
                                      'pair kernel 统计的假设性 2D 交叉总数（来源 '
                                      'extra_metrics25d.py）',
            'crossings_avoided': 'flattened_crossings_2d - crossings_total，'
                                 '即抬升/分层实际消除的交叉数（来源 extra_metrics25d.py）',
        },
        geometric_model=model,
        baselines=baselines,
        smoke_validation=smoke_validation,
        crossing_metrics=dict(
            present=bool(crossing_metrics),
            source=('summary/crossing_metrics.json' if crossing_metrics else None),
            runs={key: dict(
                flattened_crossings_2d=runs[key].get('flattened_crossings_2d'),
                actual_3d_crossings=runs[key].get('crossings_total'),
                crossings_avoided=runs[key].get('crossings_avoided'),
            ) for key in RUN_KEYS if runs[key].get('present')},
        ),
        availability={key: dict(routes_json=bool(runs[key].get('routes_file')),
                                run_summary_json=bool(runs[key].get('run_summary_file')),
                                validation=bool(runs[key].get('validation_present')))
                      for key in RUN_KEYS},
        runs=runs,
        comparison_rows=rows,
        layers_effect_summary=dict(
            conclusion=effect.get('conclusion'),
            schemes={scheme: effect['schemes'][scheme]['conclusion']
                     for scheme in SCHEMES},
            totals=effect.get('totals')),
        failed_analysis_summary=dict(
            no_2d_candidate_at_all=failed['no_2d_candidate_at_all'].get('count_total'),
            count_by_scheme=failed['no_2d_candidate_at_all'].get('count_by_scheme'),
            totals=failed.get('totals'),
        ),
        selfcheck=selfcheck,
        warnings=warnings + list(effect.get('warnings') or []),
    )
    return dict(overview=overview, effect=effect, failed=failed, runs=runs)


def _print_progress(overview):
    for key in RUN_KEYS:
        run = overview['runs'][key]
        if not run.get('present'):
            print(f'[summarize25d] {key}: MISSING (all fields null)')
            continue
        validation = run.get('validation') or {}
        if not validation.get('present'):
            verdict = 'n/a'
        elif validation.get('passed') is True:
            verdict = 'PASS'
        elif validation.get('passed') is False:
            verdict = 'FAIL'
        else:
            verdict = '?'
        print(f'[summarize25d] {key}: routed={run.get("routed")} '
              f'baseline={run.get("baseline_routed")} new={run.get("new_routed")} '
              f'lifted={run.get("lifted")} transitions={run.get("transitions")} '
              f'total_length_mm={run.get("total_length_mm")} validation={verdict}')
    warnings = overview.get('warnings') or []
    for warning in warnings:
        print(f'[summarize25d] WARNING: {warning}')
    print(f'[summarize25d] warnings={len(warnings)}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=None,
                        help='实验输出根目录（默认 outputs/four_side_1024_v2_25d_v01）')
    parser.add_argument('--quiet', action='store_true', help='只输出写文件信息')
    args = parser.parse_args(argv)
    root = _resolve_root(args.root)
    if not Path(root).is_dir():
        print(f'[summarize25d] ERROR: root directory not found: {root}')
        return 1
    started = time.perf_counter()
    if not args.quiet:
        print(f'[summarize25d] root={root}')
    result = collect(root, log=print)
    overview = result['overview']
    effect = result['effect']
    failed = result['failed']
    summary_dir = Path(root) / 'summary'
    written = []
    written.append(_write_json(summary_dir / 'overview.json', overview))
    written.append(_write_text(summary_dir / 'comparison_table.md',
                               _render_comparison_md(overview)))
    written.append(_write_json(summary_dir / 'layers_effect.json', effect))
    written.append(_write_text(summary_dir / 'layers_effect.md',
                               _render_layers_effect_md(effect)))
    written.append(_write_json(summary_dir / 'failed_analysis.json', failed))
    written.append(_write_text(Path(root) / 'REPRODUCE_25D.md',
                               _render_reproduce_md(overview, effect)))
    if not args.quiet:
        _print_progress(overview)
    for path in written:
        print(f'[summarize25d] written {_display_path(path)}')
    print(f'[summarize25d] done in {time.perf_counter() - started:.2f}s')
    return 0


if __name__ == '__main__':
    sys.exit(main())
