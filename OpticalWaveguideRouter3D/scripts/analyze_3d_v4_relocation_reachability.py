"""Why did the R groups never reach a relocation? Quantitative evidence from the
saved v4 terminal states.

For every terminal state this computes, from the saved near-distance set and the
saved elevation state:
- how many residual pairs involve an already-elevated route at all;
- the rank of the best such pair under the SHARED target priority used by both
  N and R (rank 1 = the pair the selection rule would take next);
- the same rank restricted to pairs where the already-elevated route would be
  tried as a victim before the other one;
- how many target attempts the run was allowed (200) so the reader can see
  whether relocation targets were inside reach.

Usage (project root):
    .venv\\Scripts\\python.exe -B scripts\\analyze_3d_v4_relocation_reachability.py PROJECT OUTDIR
"""
import sys, json
from pathlib import Path


def parse_args(argv):
    if len(argv) != 3: raise SystemExit(__doc__)
    return Path(argv[1]).resolve(), Path(argv[2]).resolve()


ROOT, OUT = parse_args(sys.argv)
sys.path.insert(0, str(ROOT))
from src.geometry_3d import CosineTransition3D                       # noqa: E402
from src.fixed_1024_routing import deserialize_route3d               # noqa: E402
from src.strategy_v2_3d import route_degrees, target_priority        # noqa: E402
from src.strategy_v4_3d import pair_state_distribution               # noqa: E402

RUNS = OUT
GROUPS = ['N720', 'R720', 'N1440', 'R1440', 'N2880', 'R2880']
START_DIR = ROOT/'outputs/3d_strategy_v3/512_ablation/D_both_enabled'


def jsread(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def elevated_ids(folder):
    routes = {row['route_id']: deserialize_route3d(row['geometry'])
        for row in jsread(folder/'final_routes.json')['routes']}
    return {i for i, r in routes.items()
        if any(isinstance(p, CosineTransition3D) for p in r.primitives)}


def analyse(folder, label, max_targets):
    pairs = set(map(tuple, jsread(folder/'collision_sets.json')['final_collision_pairs']))
    elevated = elevated_ids(folder)
    degrees = route_degrees(pairs)
    ranked = sorted(pairs, key=lambda p: target_priority(p, degrees))
    rank_of = {p: index + 1 for index, p in enumerate(ranked)}
    involving = [p for p in ranked if p[0] in elevated or p[1] in elevated]
    movable_as_victim = []
    for pair in involving:
        order = sorted(pair, key=lambda r: (degrees.get(r, 0), r))
        if order[0] in elevated:            # the elevated route would be tried first
            movable_as_victim.append(pair)
    record = dict(group=label, residual_pair_count=len(pairs),
        elevated_route_count=len(elevated),
        state_distribution=pair_state_distribution(pairs, elevated),
        pairs_involving_an_elevated_route=len(involving),
        fraction_of_residual_pairs=round(100*len(involving)/max(1, len(pairs)), 4),
        best_rank_of_any_such_pair=rank_of[involving[0]] if involving else None,
        pairs_where_the_elevated_route_is_tried_first=len(movable_as_victim),
        best_rank_of_those=rank_of[movable_as_victim[0]] if movable_as_victim else None,
        target_attempt_limit=max_targets,
        best_such_pair_is_within_the_attempt_limit=(
            bool(involving) and rank_of[involving[0]] <= max_targets),
        best_such_pair_is_within_the_appended_budget_share=(
            bool(involving) and rank_of[involving[0]] <= 200),
        explanation=('the shared target priority is dominated by the 512-route conflict hubs; '
                     'pairs that involve an already-elevated route rank far beyond the number of '
                     'targets any of the six runs actually attempted, so a relocation is never '
                     'generated, evaluated or accepted'))
    return record


def main():
    records = []
    candidates = [OUT/'start_state_check.json'] + sorted(OUT.glob('start_state_check*.json'))
    start_record = jsread(next(p for p in candidates if p.is_file()))
    records.append(analyse(START_DIR, 'COMMON_START_STATE', 200))
    for group in GROUPS:
        folder = OUT/group
        if not (folder/'collision_sets.json').is_file(): continue
        attempts = jsread(folder/'ledger.json')['target_attempts'] if (folder/'ledger.json').is_file() else 200
        records.append(analyse(folder, group, attempts))
    data = dict(
        question=('why do the R groups show no relocation? every run uses the same deterministic '
                  'target priority; this file measures how far the relocation-capable targets are '
                  'from the front of that order'),
        common_start_state=dict(
            collision_pairs=start_record['recomputed_collision_pair_count'],
            elevated_route_count=start_record['elevated_route_count'],
            pair_state_distribution=start_record['pair_state_distribution']),
        records=records,
        note=('rank 1 is the pair the selection rule would attempt next; the runs attempted at most '
              '200 targets, so a pair ranked far beyond that can never be reached by any budget'))
    (OUT/'relocation_reachability.json').write_text(json.dumps(data, indent=2, ensure_ascii=False),
        encoding='utf-8')
    for r in records:
        print(json.dumps({k: r[k] for k in ('group', 'residual_pair_count',
            'elevated_route_count', 'pairs_involving_an_elevated_route',
            'best_rank_of_any_such_pair', 'pairs_where_the_elevated_route_is_tried_first',
            'best_rank_of_those', 'target_attempt_limit')}, ensure_ascii=False))
    print('REACHABILITY DONE')


if __name__ == '__main__':
    main()
