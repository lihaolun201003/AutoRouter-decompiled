"""Independent validation + statistics of the pure orthogonal 90-degree experiment.

Reads only the delivered ``routes.json`` files (no router/optimiser import), runs the
frozen authoritative validator (``fslw.validate_fslw.build_report(policy='strict')``)
and additionally checks the pure-90 geometry rule on every routed primitive:

* every ``kind=line`` segment must be horizontal or vertical;
* every ``kind=arc`` must have radius exactly 40 mm and |sweep| exactly 90 degrees.

It also quantifies how much short-S (non-90-degree arc) the reference V2-BEST (752)
layout uses, and produces the report's statistics tables.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

from ..fslw import validate_fslw

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / 'outputs/four_side_1024_v2_candidate_rr_v01'
ORTHO90_OUT = ROOT / 'outputs/four_side_1024_v2_ortho90_v01'
RADIUS = 40.0
QUARTER = math.pi / 2.0
TOL_LINE = 1e-6
TOL_ARC = 1e-6
PLANES = ('z1', 'z2')


def _load_routes(path):
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    return payload, payload.get('routes') or []


def geometry_rule_audit(primitive_lists):
    """Check the pure-90 rule on primitive chains; returns counters + violations."""
    counters = dict(routes=0, lines=0, arcs=0, diagonal_lines=0, non90_arcs=0,
                    bad_radius_arcs=0)
    violations = []
    sweeps = []
    for route_id, primitives in primitive_lists:
        counters['routes'] += 1
        for index, primitive in enumerate(primitives or []):
            kind = primitive.get('kind')
            if kind == 'line':
                counters['lines'] += 1
                p0, p1 = primitive['p0'], primitive['p1']
                if abs(float(p0[0]) - float(p1[0])) > TOL_LINE \
                        and abs(float(p0[1]) - float(p1[1])) > TOL_LINE:
                    counters['diagonal_lines'] += 1
                    violations.append(dict(route_id=route_id, primitive=index,
                                           kind='line', reason='diagonal_line',
                                           p0=p0, p1=p1))
            elif kind == 'arc':
                counters['arcs'] += 1
                radius = float(primitive['radius'])
                sweep = float(primitive['sweep'])
                sweeps.append(abs(sweep))
                if abs(radius - RADIUS) > TOL_ARC:
                    counters['bad_radius_arcs'] += 1
                    violations.append(dict(route_id=route_id, primitive=index,
                                           kind='arc', reason='radius',
                                           radius=radius))
                if abs(abs(sweep) - QUARTER) > TOL_ARC:
                    counters['non90_arcs'] += 1
                    violations.append(dict(route_id=route_id, primitive=index,
                                           kind='arc', reason='non_90_sweep',
                                           sweep_deg=math.degrees(sweep),
                                           radius=radius))
            else:
                violations.append(dict(route_id=route_id, primitive=index,
                                       kind=kind, reason='unknown_primitive_kind'))
    counters['min_sweep_deg'] = math.degrees(min(sweeps)) if sweeps else None
    counters['max_sweep_deg'] = math.degrees(max(sweeps)) if sweeps else None
    counters['violation_count'] = len(violations)
    return counters, violations[:100]


def arc_sweep_histogram(primitive_lists):
    """Histogram of |sweep| for all arcs (short-S arcs show up < 90 deg)."""
    buckets = Counter()
    for _route_id, primitives in primitive_lists:
        for primitive in primitives or []:
            if primitive.get('kind') != 'arc':
                continue
            degrees = math.degrees(abs(float(primitive['sweep'])))
            if degrees > 89.999:
                buckets['90'] += 1
            elif degrees >= 60:
                buckets['60-90'] += 1
            elif degrees >= 30:
                buckets['30-60'] += 1
            elif degrees >= 10:
                buckets['10-30'] += 1
            else:
                buckets['<10'] += 1
    return dict(buckets)


def _routed_records(records):
    return [record for record in records if record.get('status') == 'routed']


def _failed_records(records):
    return [record for record in records if record.get('status') != 'routed']


def _by_pair(records):
    result = {}
    for record in records:
        pair = record['pair']
        entry = result.setdefault(pair, dict(total=0, routed=0))
        entry['total'] += 1
        if record.get('status') == 'routed':
            entry['routed'] += 1
    return result


def audit_plane(routes_path, plane):
    routes_path = Path(routes_path)
    payload, records = _load_routes(routes_path)
    routed = _routed_records(records)
    failed = _failed_records(records)
    primitive_lists = [(record['route_id'], record.get('primitives') or [])
                       for record in routed]
    counters, violations = geometry_rule_audit(primitive_lists)
    report = validate_fslw.build_report(routes_path=routes_path, policy='strict',
                                        expected_route_count=512, plane=plane)
    lengths = [float(record.get('length_mm') or 0.0) for record in routed]
    bends = [int(record.get('bend_count') or 0) for record in routed]
    stats = dict(
        plane=plane,
        routed=len(routed), failed=len(failed), total=len(records),
        by_pair=_by_pair(records),
        failure_reasons=dict(Counter(record.get('reason') or 'unknown'
                                     for record in failed)),
        failed_route_ids=[record['route_id'] for record in failed],
        mean_length_mm=(sum(lengths) / len(lengths)) if lengths else None,
        total_length_mm=sum(lengths),
        mean_bends=(sum(bends) / len(bends)) if bends else None,
        total_bends=sum(bends),
        geometry=counters,
        geometry_violations=violations,
        strict_audit=dict(
            passed=report.get('passed'),
            policy=report.get('policy_used'),
            route_count=report.get('route_count'),
            routed_count=report.get('routed_count'),
            d56_checked=report.get('d56_checked_count'),
            d56_passed=report.get('d56_passed_count'),
            d56_failed=report.get('d56_failed_count'),
            violation_pairs=report.get('violation_pair_count'),
            crossings=report.get('crossing_count'),
            crossing_pairs=report.get('crossing_pair_count'),
            small_angle_crossings=report.get('small_angle_crossing_count'),
            min_non_crossing_mm=report.get('min_non_crossing_centerline_mm'),
            crossing_window_max_mm=report.get('crossing_window_max_mm'),
            errors=report.get('errors'),
            warnings=report.get('warnings'),
        ),
        routes_file=str(routes_path),
    )
    return stats


def lost_vs_best(plane, ortho_stats):
    best_dir = DEFAULT_OUT / 'planes' / 'V2' / 'BEST' / plane
    best_path = best_dir / 'routes.json'
    if not best_path.exists():
        return None
    _payload, best_records = _load_routes(best_path)
    best_routed = {record['route_id']: record for record in best_records
                   if record.get('status') == 'routed'}
    ortho_path = ORTHO90_OUT / 'planes' / 'V2' / 'ORTHO90' / plane / 'routes.json'
    _payload, ortho_records = _load_routes(ortho_path)
    ortho_routed = {record['route_id']: record for record in ortho_records
                    if record.get('status') == 'routed'}
    ortho_failed = {record['route_id']: record for record in ortho_records
                    if record.get('status') != 'routed'}
    lost = sorted(set(best_routed) - set(ortho_routed))
    gained = sorted(set(ortho_routed) - set(best_routed))
    lost_reasons = Counter(ortho_failed.get(route_id, {}).get('reason') or 'not_attempted'
                           for route_id in lost)
    # arcs of the reference layout, to quantify short-S usage
    best_prims = [(route_id, record.get('primitives') or [])
                  for route_id, record in best_routed.items()]
    return dict(best_routed=len(best_routed), ortho_routed=len(ortho_routed),
                lost=len(lost), lost_route_ids=lost,
                lost_failure_reasons=dict(lost_reasons),
                gained=len(gained), gained_route_ids=gained,
                best_arc_sweeps=arc_sweep_histogram(best_prims))


def best_reference_stats(plane):
    """Compact statistics of the reference V2-BEST plane (752-round layout)."""
    plane_dir = DEFAULT_OUT / 'planes' / 'V2' / 'BEST' / plane
    routes_path = plane_dir / 'routes.json'
    if not routes_path.exists():
        return None
    _payload, records = _load_routes(routes_path)
    routed = _routed_records(records)
    lengths = [float(record.get('length_mm') or 0.0) for record in routed]
    bends = [int(record.get('bend_count') or 0) for record in routed]
    prims = [(record['route_id'], record.get('primitives') or []) for record in routed]
    stats_path = plane_dir / 'statistics.json'
    crossings = None
    mean_bends_stat = None
    if stats_path.exists():
        try:
            payload = json.loads(stats_path.read_text(encoding='utf-8'))
            crossings = payload.get('crossing_count')
            mean_bends_stat = payload.get('mean_bend_count')
        except (OSError, json.JSONDecodeError):
            pass
    return dict(plane=plane, routed=len(routed), total=len(records),
                mean_length_mm=(sum(lengths) / len(lengths)) if lengths else None,
                mean_bends=(sum(bends) / len(bends)) if bends else mean_bends_stat,
                total_bends=sum(bends),
                crossings=crossings,
                arc_sweeps=arc_sweep_histogram(prims),
                arcs=sum(1 for _rid, prims2 in prims for primitive in prims2
                         if primitive.get('kind') == 'arc'),
                lines=sum(1 for _rid, prims2 in prims for primitive in prims2
                          if primitive.get('kind') == 'line'))


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ORTHO90_OUT)
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    result = dict(schema='four_side_1024_v2_ortho90_validation_v1',
                  geometry_rule=('lines axis-aligned only; arcs radius=40.0 mm and '
                                 '|sweep|=90 deg exactly; short-S theta<90 forbidden'),
                  reference_v2_best={'z1': best_reference_stats('z1'),
                                     'z2': best_reference_stats('z2')},
                  planes={})
    for plane in PLANES:
        routes_path = out / 'planes' / 'V2' / 'ORTHO90' / plane / 'routes.json'
        if not routes_path.exists():
            print(f'{plane}: routes.json missing, skipped')
            continue
        stats = audit_plane(routes_path, plane)
        stats['lost_vs_best'] = lost_vs_best(plane, stats)
        result['planes'][plane] = stats
        print(f"{plane}: routed={stats['routed']} strict={stats['strict_audit']['passed']} "
              f"violations={stats['strict_audit']['violation_pairs']} "
              f"arcs={stats['geometry']['arcs']} "
              f"non90_arcs={stats['geometry']['non90_arcs']} "
              f"diagonal_lines={stats['geometry']['diagonal_lines']} "
              f"lost_vs_best={(stats['lost_vs_best'] or {}).get('lost')}")
    planes = result['planes']
    if len(planes) == 2:
        result['combined'] = dict(
            routed=sum(planes[plane]['routed'] for plane in PLANES),
            total=sum(planes[plane]['total'] for plane in PLANES),
            strict_passed=all(planes[plane]['strict_audit']['passed']
                              for plane in PLANES),
            geometry_rule_passed=all(
                planes[plane]['geometry']['non90_arcs'] == 0
                and planes[plane]['geometry']['diagonal_lines'] == 0
                and planes[plane]['geometry']['violation_count'] == 0
                for plane in PLANES),
            best_752=752,
        )
        result['combined']['gap_vs_best'] = result['combined']['routed'] - 752
        print(f"combined: {result['combined']['routed']}/1024 "
              f"(gap vs 752: {result['combined']['gap_vs_best']:+d}) strict="
              f"{result['combined']['strict_passed']} pure90="
              f"{result['combined']['geometry_rule_passed']}")
    path = out / 'geometry_audit.json'
    path.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding='utf-8')
    print(f'written {path}')
    return result


if __name__ == '__main__':
    main()
