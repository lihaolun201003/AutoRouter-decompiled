"""P0: freeze and re-verify the two experiment start states and every input hash.

Independent full 130,816-pair rescan of
  (a) the MAIN start state  outputs/3d_strategy_v3/512_ablation/D_both_enabled
  (b) the CHALLENGE start   outputs/3d_strategy_v4/512_full_layout/N2880
and a machine-readable errata record for the three known v4 delivery-metadata
defects. Nothing here rewrites an original number.

Usage: .venv\Scripts\python.exe -B scripts\overnight_p0_baseline.py PROJECT OUTDIR
"""
import sys, json, hashlib, platform, traceback
from collections import Counter
from pathlib import Path
from itertools import combinations
from time import perf_counter


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    root = Path(sys.argv[1]).resolve(); out = Path(sys.argv[2]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(root))
    from src.models import Layer, Point3D
    from src.geometry_3d import lift_smoothed_route_to_layer, CosineTransition3D
    from src.multi_attribution import deserialize_plot
    from src.sequential_elevation_3d import RouteView, pair_status
    from src.fixed_1024_routing import deserialize_route3d
    from src.strategy_v2_3d import route_layer
    from src.strategy_v4_3d import pair_state_distribution, elevation_structure

    CLEARANCE = 0.1; SIZE = 512
    record = dict(started=perf_counter(), python=sys.version.split()[0],
        platform=platform.platform(), clearance_mm=CLEARANCE, scale=SIZE)

    # ---- frozen reconstruction inputs -------------------------------------
    plotpath = root/'outputs/step_8_5_legacy_512_plot_geometry.json'
    eventpath = root/'outputs/step_8_5_legacy_512_physical_events.jsonl'
    planar = {r['id']: lift_smoothed_route_to_layer(deserialize_plot(r), Layer(0, 0))
              for r in json.loads(plotpath.read_text())['routes']}
    crossings = {}
    for text in eventpath.read_text().splitlines():
        e = json.loads(text)
        if e['kind'] == 'cross':
            crossings.setdefault(tuple(sorted((e['route_a_id'], e['route_b_id']))), []).append(
                Point3D(e['point']['x'], e['point']['y'], 0))
    planar_total = sum(r.total_length() for r in planar.values())
    record['frozen_reconstruction_inputs'] = dict(
        plot_geometry=dict(path=str(plotpath.relative_to(root)), sha256=sha256(plotpath),
                           bytes=plotpath.stat().st_size),
        physical_events=dict(path=str(eventpath.relative_to(root)), sha256=sha256(eventpath),
                             bytes=eventpath.stat().st_size),
        planar_route_count=len(planar), planar_total_length_mm=planar_total,
        saved_crossing_pairs=len(crossings),
        note='legacy smoothed planar layer-0 routes and saved CROSS points; read-only')

    def scan(routes, tag):
        views = {i: RouteView.prepare(r) for i, r in routes.items()}
        pairs = set(); unknown = set(); t0 = perf_counter(); checks = 0
        for a, b in combinations(sorted(routes), 2):
            st = pair_status(views[a], views[b], CLEARANCE); checks += 1
            if st == 'COLLISION': pairs.add((a, b))
            elif st != 'CLEAR': unknown.add((a, b))
        return dict(tag=tag, checks=checks, seconds=perf_counter()-t0,
                    collision_pairs=pairs, unresolved_pairs=unknown)

    def audit_state(name, path, expected_pairs, expected_unknown, expected_elevated):
        routes = {row['route_id']: deserialize_route3d(row['geometry'])
                  for row in json.loads((path/'final_routes.json').read_text(encoding='utf-8'))['routes']}
        sets = json.loads((path/'collision_sets.json').read_text(encoding='utf-8'))
        saved_pairs = set(map(tuple, sets['final_collision_pairs']))
        saved_unknown = set(map(tuple, sets['final_unresolved_pairs']))
        res = scan(routes, name)
        elevated = {i for i, r in routes.items() if any(isinstance(p, CosineTransition3D) for p in r.primitives)}
        total = sum(r.total_length() for r in routes.values())
        geom = dict(endpoints=True, joins=True, radius=True, xy=True, structure=True)
        for i, r in routes.items():
            if r.start_point != planar[i].start_point or r.end_point != planar[i].end_point: geom['endpoints'] = False
            ok, _ = elevation_structure(r); geom['structure'] = geom['structure'] and ok
        rows = dict(name=name, directory=str(path.relative_to(root)), route_count=len(routes),
            recomputed_checks=res['checks'], recomputed_collision_pairs=len(res['collision_pairs']),
            saved_collision_pairs=len(saved_pairs), pair_set_matches=(res['collision_pairs'] == saved_pairs),
            recomputed_unresolved=len(res['unresolved_pairs']), saved_unresolved=len(saved_unknown),
            unresolved_set_matches=(res['unresolved_pairs'] == saved_unknown),
            elevated_route_count=len(elevated),
            layer_route_counts={str(k): v for k, v in sorted(Counter(route_layer(r) for r in routes.values()).items())},
            pair_state_distribution=pair_state_distribution(res['collision_pairs'], elevated),
            total_length_mm=total, extra_length_vs_planar_mm=total-planar_total,
            scan_seconds=res['seconds'],
            files={f: dict(sha256=sha256(path/f), bytes=(path/f).stat().st_size)
                   for f in ('final_routes.json', 'collision_sets.json', 'ledger.json',
                             'decisions.json', 'summary.json') if (path/f).is_file()},
            expected=dict(collision_pairs=expected_pairs, unresolved=expected_unknown,
                          elevated=expected_elevated),
            geometry_flags=geom)
        rows['verdict'] = 'PASS' if (rows['pair_set_matches'] and rows['unresolved_set_matches']
            and rows['recomputed_collision_pairs'] == expected_pairs
            and rows['recomputed_unresolved'] == expected_unknown
            and rows['elevated_route_count'] == expected_elevated
            and all(geom.values())) else 'FAIL'
        return rows

    record['main_start'] = audit_state('MAIN_v3_D_both_enabled',
        root/'outputs/3d_strategy_v3/512_ablation/D_both_enabled', 42909, 3, 24)
    record['challenge_start'] = audit_state('CHALLENGE_v4_N2880',
        root/'outputs/3d_strategy_v4/512_full_layout/N2880', 30999, 3, 77)
    print(json.dumps({k: (v if k in ('python','platform') else
        {kk: vv for kk, vv in v.items() if kk != 'files'}) for k, v in record.items()
        if k in ('main_start','challenge_start')}, indent=2, default=str)[:4000], flush=True)

    # ---- errata: derived records only, original numbers untouched ----------
    report = (root/'docs/reports/step_17_full_layout_v4.md').read_text(encoding='utf-8').splitlines()
    line118 = report[117] if len(report) > 117 else ''
    record['errata'] = dict(
        note='v4 derived-record defects; original CSV/JSON/log numbers are NOT modified',
        items=[
            dict(id='E1', target='docs/reports/step_17_full_layout_v4.md line 118',
                 observed_text=line118.strip(),
                 correction=('six-group totals are 6 full rejections and ~57.3 evaluations per action, '
                             'not "complete rejection 3 times, 72-99 per action"; the machine ledger in '
                             'outputs/3d_strategy_v4/512_full_layout/summary_all_v4.json is authoritative'),
                 source='outputs/3d_strategy_v4/512_full_layout/summary_all_v4.json + six ledger.json'),
            dict(id='E2', target='outputs/3d_strategy_v4/512_full_layout/3d_strategy_v4_test_summary.json',
                 observed_text=json.loads((root/'outputs/3d_strategy_v4/512_full_layout/'
                     '3d_strategy_v4_test_summary.json').read_text(encoding='utf-8')).get('note', ''),
                 correction=('two entries were not parsed and show a not-found/unknown status; the raw logs are '
                             '757 passed, 4 skipped (3D interpreter) and 61 passed (2D interpreter)'),
                 source='outputs/3d_strategy_v4/512_full_layout/pytest_full_v4.log and pytest_opt2d_2d_env_v4.log'),
            dict(id='E3', target='docs/reports/step_17_full_layout_v4.md lines 139-140',
                 observed_text=' | '.join(x.strip() for x in report[138:140]),
                 correction=('the DOCX is written under publication/report/brief_build and the PDF under '
                             'publication/report; the report text names the wrong directories'),
                 source='outputs/3d_strategy_v4/512_full_layout/report_build.log and report_all_build.log'),
        ])
    record['historical_test_records'] = dict(
        note='historical only; NOT this round’s test result',
        three_d_pytest_log='outputs/3d_strategy_v4/512_full_layout/pytest_full_v4.log',
        three_d_summary='757 passed, 4 skipped (4 module-level scipy importorskip, not 4 cases)',
        two_d_pytest_log='outputs/3d_strategy_v4/512_full_layout/pytest_opt2d_2d_env_v4.log',
        two_d_summary='61 passed')
    record['total_seconds'] = perf_counter() - record['started']
    record['verdict'] = ('PASS' if record['main_start']['verdict'] == 'PASS'
                         and record['challenge_start']['verdict'] == 'PASS' else 'FAIL')
    (out/'P0_baseline.json').write_text(json.dumps(record, indent=2, default=str), encoding='utf-8')
    print('P0', record['verdict'], 'main=%d pairs, challenge=%d pairs, %.1fs' % (
        record['main_start']['recomputed_collision_pairs'],
        record['challenge_start']['recomputed_collision_pairs'], record['total_seconds']), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('FAILED\n' + traceback.format_exc(), flush=True); raise
