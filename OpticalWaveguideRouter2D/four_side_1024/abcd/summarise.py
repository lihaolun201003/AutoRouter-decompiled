"""Cross-experiment summaries that the viz comparison builder consumes.

Produces (all under ``outputs/four_side_1024_v1_v2_abcd/comparison/``):

* ``c_sweep.csv`` / ``c_sweep.json`` - the 8-design C ablation on V1, plus the
  frozen design used for V1_C / V2_C;
* ``d_budget_compare.json`` / ``.md`` - D equal-budget vs extended-budget versus
  the A/B/C costs on the same topology;
* ``run_summary.json`` - one row per experiment straight from ``routes.json``
  (engine self-report; ``metrics.py`` recomputes the authoritative statistics).
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = ROOT / 'outputs/four_side_1024_v1_v2_abcd'
EXPERIMENTS = [f'{topology}_{algorithm}' for topology in ('V1', 'V2')
               for algorithm in ('A', 'B', 'C', 'D')]
C_FROZEN = dict(start_side='E', direction='ccw', batch=32)


def _load(path):
    with Path(path).open(encoding='utf-8') as handle:
        return json.load(handle)


def _row(run_dir):
    routes_path = Path(run_dir) / 'routes.json'
    if not routes_path.exists():
        return None
    payload = _load(routes_path)
    stats = payload.get('statistics') or {}
    config_path = Path(run_dir) / 'config.json'
    config = _load(config_path) if config_path.exists() else {}
    return dict(
        experiment=payload.get('experiment') or Path(run_dir).name,
        routed=stats.get('success_count'),
        opposite=(stats.get('by_relation') or {}).get('opposite', {}).get('success'),
        adjacent=(stats.get('by_relation') or {}).get('adjacent', {}).get('success'),
        by_pair={key: value.get('success') for key, value in
                 (stats.get('by_pair') or {}).items()},
        mean_length_mm=stats.get('mean_length_mm'),
        total_length_mm=stats.get('total_length_mm'),
        crossing_count=stats.get('crossing_count'),
        evaluations=stats.get('candidate_evaluations'),
        runtime_seconds=stats.get('total_runtime_seconds'),
        policy=((payload.get('algorithm_detail') or {}).get('crossing_policy')
                or config.get('policy')),
        strategy=config.get('strategy'),
        budget=dict(eval_budget=config.get('eval_budget'),
                    time_budget_seconds=config.get('time_budget_seconds')),
    )


def c_sweep(root=DEFAULT_ROOT):
    sweeps = {}
    sweep_dir = Path(root) / 'sweeps'
    if sweep_dir.exists():
        for path in sorted(sweep_dir.iterdir()):
            row = _row(path)
            if row is None:
                continue
            design = (row.get('strategy') or {}).get('design') or {}
            sweeps[path.name] = dict(
                design=design, routed=row['routed'],
                opposite=row['opposite'], adjacent=row['adjacent'],
                mean_length_mm=row['mean_length_mm'],
                evaluations=row['evaluations'],
                runtime_seconds=row['runtime_seconds'])
    rows = []
    for name, record in sweeps.items():
        design = record['design']
        rows.append(dict(
            design_name=name,
            direction=design.get('direction'),
            start_side=design.get('start_side'),
            batch=design.get('batch'),
            routed=record['routed'],
            opposite=record['opposite'],
            adjacent=record['adjacent'],
            mean_length_mm=record['mean_length_mm'],
            evaluations=record['evaluations'],
            runtime_seconds=record['runtime_seconds'],
        ))
    rows.sort(key=lambda item: (-(item['routed'] or 0),
                                item['mean_length_mm'] or 1e9))
    comparison = Path(root) / 'comparison'
    comparison.mkdir(parents=True, exist_ok=True)
    with (comparison / 'c_sweep.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else
                                ['design_name', 'routed'])
        writer.writeheader()
        writer.writerows(rows)
    payload = dict(policy='strict', topology='V1',
                   note='C design ablation; each variant is a full 1024-identity run '
                        'under the identical geometry/candidate/policy budget. The '
                        'frozen design is used unchanged for both V1_C and V2_C.',
                   frozen_design=dict(C_FROZEN), designs=rows,
                   selected=[row for row in rows if row['routed'] == max(
                       (item['routed'] or 0) for item in rows)][:3] if rows else [])
    (comparison / 'c_sweep.json').write_text(
        json.dumps(payload, indent=1, ensure_ascii=False), encoding='utf-8')
    return payload


def d_budget_compare(root=DEFAULT_ROOT):
    comparison = Path(root) / 'comparison'
    comparison.mkdir(parents=True, exist_ok=True)
    record = dict(policy='strict',
                  note='D is compared at (a) the same candidate-evaluation budget as '
                       'the best A/B/C experiment on that topology and (b) an extended '
                       'budget; both runs use the same geometry, candidate pool rules '
                       'and strict acceptance policy.',
                  topologies={})
    for topology in ('V1', 'V2'):
        base = {algorithm: _row(Path(root) / f'{topology}_{algorithm}')
                for algorithm in ('A', 'B', 'C')}
        sequential_evals = [row['evaluations'] for row in base.values()
                            if row and row['evaluations']]
        equal_budget = max(sequential_evals) if sequential_evals else None
        primary = _row(Path(root) / f'{topology}_D')
        equal_arm = _row(Path(root) / 'equal_budget' / f'{topology}_D')
        extended = _row(Path(root) / 'extended' / f'{topology}_D')
        record['topologies'][topology] = dict(
            sequential=dict(
                equal_budget_evaluations=equal_budget,
                runs={algorithm: (None if base[algorithm] is None else dict(
                    routed=base[algorithm]['routed'],
                    opposite=base[algorithm]['opposite'],
                    adjacent=base[algorithm]['adjacent'],
                    evaluations=base[algorithm]['evaluations'],
                    runtime_seconds=base[algorithm]['runtime_seconds']))
                    for algorithm in base}),
            d_equal_budget=None if equal_arm is None else dict(
                routed=equal_arm['routed'], opposite=equal_arm['opposite'],
                adjacent=equal_arm['adjacent'], evaluations=equal_arm['evaluations'],
                runtime_seconds=equal_arm['runtime_seconds'],
                eval_budget=equal_arm['budget']['eval_budget']),
            d_primary=None if primary is None else dict(
                routed=primary['routed'], opposite=primary['opposite'],
                adjacent=primary['adjacent'], evaluations=primary['evaluations'],
                runtime_seconds=primary['runtime_seconds'],
                eval_budget=primary['budget']['eval_budget']),
            d_extended=None if extended is None else dict(
                routed=extended['routed'], opposite=extended['opposite'],
                adjacent=extended['adjacent'], evaluations=extended['evaluations'],
                runtime_seconds=extended['runtime_seconds'],
                eval_budget=extended['budget']['eval_budget']),
        )
    (comparison / 'd_budget_compare.json').write_text(
        json.dumps(record, indent=1, ensure_ascii=False), encoding='utf-8')
    return record


def run_summary(root=DEFAULT_ROOT):
    table = {}
    for experiment in EXPERIMENTS:
        row = _row(Path(root) / experiment)
        if row:
            table[experiment] = row
    comparison = Path(root) / 'comparison'
    comparison.mkdir(parents=True, exist_ok=True)
    (comparison / 'run_summary.json').write_text(
        json.dumps(dict(generated_from='routes.json engine self-report',
                        experiments=table), indent=1, ensure_ascii=False),
        encoding='utf-8')
    return table


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args(argv)
    c = c_sweep(args.root)
    d = d_budget_compare(args.root)
    s = run_summary(args.root)
    print(json.dumps(dict(c_sweep_variants=len(c['designs']),
                          frozen_design=c['frozen_design'],
                          run_summary=sorted(s),
                          d_topologies=list(d['topologies'])), indent=1))


if __name__ == '__main__':
    main()
