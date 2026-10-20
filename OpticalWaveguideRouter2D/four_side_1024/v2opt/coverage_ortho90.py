"""Layout-independent pure-90 candidate coverage: per route, does the generator
produce at least one validated candidate on an EMPTY board?

Used for the report question "which connections lose their legal candidates when
non-90-degree short-S arcs are forbidden" (this is a generator/geometry statement,
not a routing-conflict statement).
"""
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(r'C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter2D')
sys.path.insert(0, str(ROOT))

PLANE = sys.argv[1] if len(sys.argv) > 1 else 'z2'
OUT = ROOT / 'outputs/four_side_1024_v2_ortho90_v01' / 'experiments'
OUT.mkdir(parents=True, exist_ok=True)


class Empty:
    def h_obstacle_ys(self, *a): return []
    def v_obstacle_xs(self, *a): return []
    def h_parallel(self, *a): return 0
    def v_parallel(self, *a): return 0
    def h_crossings(self, *a): return 0
    def v_crossings(self, *a): return 0


def worker(route_ids):
    from four_side_1024.fslw import ports
    from four_side_1024.d56.frames import build_frames
    from four_side_1024.v2opt import ortho90
    routes, endpoints, _, _ = ports.load_plane('V2', PLANE)
    frames = build_frames(routes, endpoints)
    results = []
    empty = Empty()
    generator = ortho90.Ortho90Generator(seed=20261019)
    for route_id in route_ids:
        frame = frames[route_id]
        started = time.perf_counter()
        count = 0
        families = {}
        try:
            for candidate in generator.candidates(frame, empty):
                count += 1
                families[candidate['family']] = families.get(candidate['family'], 0) + 1
                if count >= 200:
                    break
        except Exception as exc:  # noqa: BLE001
            results.append(dict(route_id=route_id, error=f'{type(exc).__name__}: {exc}'))
            continue
        results.append(dict(
            route_id=route_id, kind=frame.kind,
            p=[float(frame.p[0]), 0.0], q=[float(frame.q[0]), float(frame.q[1])],
            candidate_count=count, families=families,
            seconds=round(time.perf_counter() - started, 3)))
    return results


def main():
    from four_side_1024.fslw import ports
    routes, _e, _c, _v = ports.load_plane('V2', PLANE)
    route_ids = [route['route_id'] for route in routes]
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    chunks = [[] for _ in range(workers)]
    for index, route_id in enumerate(route_ids):
        chunks[index % workers].append(route_id)
    started = time.perf_counter()
    results = []
    with Pool(processes=workers) as pool:
        for chunk in pool.imap_unordered(worker, [c for c in chunks if c]):
            results.extend(chunk)
            print(f'{len(results)}/{len(route_ids)} routes done '
                  f'{time.perf_counter()-started:.1f}s', flush=True)
    results.sort(key=lambda item: item['route_id'])
    zero = [item for item in results if item.get('candidate_count', 0) == 0]
    summary = dict(
        plane=PLANE, routes=len(results), zero_candidate=len(zero),
        zero_candidate_route_ids=[item['route_id'] for item in zero],
        zero_by_kind={},
        family_histogram={},
        seconds=round(time.perf_counter() - started, 2),
    )
    for item in results:
        kind = item.get('kind')
        summary.setdefault('kind_totals', {}).setdefault(kind, dict(total=0, zero=0))
        summary['kind_totals'][kind]['total'] += 1
        if item.get('candidate_count', 0) == 0:
            summary['kind_totals'][kind]['zero'] += 1
        for family, count in (item.get('families') or {}).items():
            summary['family_histogram'][family] = \
                summary['family_histogram'].get(family, 0) + count
    payload = dict(summary=summary, routes=results)
    path = OUT / f'coverage_empty_{PLANE}.json'
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False),
                    encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))
    print('written', path)


if __name__ == '__main__':
    main()
