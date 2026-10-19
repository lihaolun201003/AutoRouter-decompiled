"""Authoritative independent audit of the eight ABCD experiments.

For every run directory this writes

* ``audit_strict.json``  - the acceptance policy of this study (authoritative),
* ``audit_exact.json``   - historical whole-primitive-pair exemption (sensitivity),
* ``audit_legacy.json``  - historical ``clearance/sin(angle)`` window (sensitivity),

using :mod:`four_side_1024.d56.validate_d56` (which never imports the router's own
checker).  A summary table is written to ``comparison/strict_audit_summary.json``.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = ROOT / 'outputs/four_side_1024_v1_v2_abcd'

POLICIES = ('strict', 'exact', 'legacy')

KEEP_FIELDS = (
    'passed', 'policy_used', 'route_count', 'routed_count', 'failed_status_count',
    'd56_checked_count', 'd56_passed_count', 'd56_failed_count',
    'pair_audit', 'pair_audited_route_count', 'candidate_pair_count',
    'crossing_count', 'crossing_pair_count', 'crossing_angle_histogram',
    'small_angle_threshold_deg', 'small_angle_crossing_count',
    'min_non_crossing_centerline_mm', 'spacing_violation_pairs', 'overlap_pairs',
    'touch_pairs', 'crossing_zone_overlap_pairs', 'crossing_window_overlap_pairs',
    'double_cross_pairs', 'crossing_window_excessive_pairs',
    'crossing_window_count', 'crossing_window_max_mm',
    'crossing_window_mean_mm', 'crossing_window_total_length_mean_mm',
    'crossing_window_stats', 'violation_pair_count', 'runtime_seconds',
    'self_intersections', 'self_overlaps', 'self_spacing_violations',
    'radius_violations', 'boundary_violations', 'diagonal_line_violations',
    'free_or_short_s_arc_violations', 'errors', 'warnings',
)


def audit_experiment(experiment_dir, policies=POLICIES, verbose=True):
    from four_side_1024.d56 import validate_d56
    routes_path = Path(experiment_dir) / 'routes.json'
    if not routes_path.exists():
        raise FileNotFoundError(routes_path)
    results = {}
    for policy in policies:
        started = time.perf_counter()
        report = validate_d56.build_report(routes_path=routes_path, policy=policy)
        record = {field: report.get(field) for field in KEEP_FIELDS
                  if field in report}
        record['policy'] = policy
        record['violations'] = (report.get('violations') or [])[:400]
        record['violation_total'] = len(report.get('violations') or [])
        record['route_errors'] = (report.get('route_errors') or [])[:50]
        record['wall_seconds'] = time.perf_counter() - started
        (Path(experiment_dir) / f'audit_{policy}.json').write_text(
            json.dumps(record, indent=1, ensure_ascii=False), encoding='utf-8')
        results[policy] = record
        if verbose:
            print(f'{Path(experiment_dir).name} [{policy}]: passed={record.get("passed")} '
                  f'routed={record.get("routed_count")} '
                  f'crossings={record.get("crossing_count")} '
                  f'spacing={record.get("spacing_violation_pairs")} '
                  f'window_overlap={record.get("crossing_window_overlap_pairs")} '
                  f'{record["wall_seconds"]:.1f}s', flush=True)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--experiments', default='V1_A,V1_B,V1_C,V1_D,V2_A,V2_B,V2_C,V2_D')
    parser.add_argument('--policies', default=','.join(POLICIES))
    args = parser.parse_args(argv)
    experiments = [item.strip() for item in args.experiments.split(',') if item.strip()]
    policies = tuple(item.strip() for item in args.policies.split(',') if item.strip())
    summary = {}
    for experiment in experiments:
        run_dir = args.root / experiment
        if not (run_dir / 'routes.json').exists():
            print(f'[skip] {experiment}: no routes.json yet', flush=True)
            continue
        results = audit_experiment(run_dir, policies=policies)
        strict = results['strict']
        summary[experiment] = dict(
            routed=strict.get('routed_count'),
            d56_passed=strict.get('d56_passed_count'),
            passed=strict.get('passed'),
            crossings=strict.get('crossing_count'),
            small_angle=strict.get('small_angle_crossing_count'),
            min_non_crossing_mm=strict.get('min_non_crossing_centerline_mm'),
            spacing=strict.get('spacing_violation_pairs'),
            overlap=strict.get('overlap_pairs'),
            touch=strict.get('touch_pairs'),
            window_overlap=strict.get('crossing_window_overlap_pairs'),
            double_cross=strict.get('double_cross_pairs'),
            excessive=strict.get('crossing_window_excessive_pairs'),
            window_count=strict.get('crossing_window_count'),
            window_max_mm=strict.get('crossing_window_max_mm'),
            window_mean_mm=strict.get('crossing_window_mean_mm'),
            exact_passed=results.get('exact', {}).get('passed'),
            legacy_passed=results.get('legacy', {}).get('passed'),
            legacy_spacing=results.get('legacy', {}).get('spacing_violation_pairs'),
        )
    comparison = args.root / 'comparison'
    comparison.mkdir(parents=True, exist_ok=True)
    (comparison / 'strict_audit_summary.json').write_text(
        json.dumps(dict(generated_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
                        policy='strict (authoritative), exact/legacy sensitivities',
                        experiments=summary), indent=1, ensure_ascii=False),
        encoding='utf-8')
    payload = json.dumps(summary, indent=1, ensure_ascii=False)
    (comparison / 'strict_audit_summary.md').write_text(
        '# Strict (`abcd/SPEC.md` §2.1) audit summary\n\n```json\n' + payload + '\n```\n',
        encoding='utf-8')
    print(payload)


if __name__ == '__main__':
    main()
