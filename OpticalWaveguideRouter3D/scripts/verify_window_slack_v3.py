"""Step 16 (strategy v3) probe: window-slack effect on the saved 512 self-clearance ambiguities.

Read-only on every earlier artifact. Reconstructs the saved
SELF_AMBIGUOUS_CLEARANCE candidate rows of the revised-C 512 run from the frozen
planar geometry and the saved CROSS anchors, then rebuilds each recorded
candidate with the corresponding window of a slack-grown enumeration.

The pad grows from clearance/length to (clearance+slack)/length, so the usable
interval [lo, hi] is inset by delta=slack/length at both ends: the window width
shrinks by 2*delta, and a window start moves by delta*(1-2f) with f in (0,.5,1)
-- start-anchored placements +delta, the centred placement 0, hit-the-boundary
placements -delta. The transition length run/length is unchanged, but a window
whose shrunk width no longer fits (hi-lo < run/length) drops out of the
enumeration. Corresponding windows are matched within 2*delta instead of
assuming a single shift direction.

The 0.1 mm clearance criterion, the radius rule and the conservative rejection
statuses are unchanged by this probe, which reports the measured outcome only:
how many of the recorded ambiguities come out CLEAR in this rebuild, how many
stay unresolved or turn into collisions, and whether the available window count
shrinks on the recorded tasks. It is a measurement on the saved 512 rows, not a
guarantee about other candidates or other inputs.

Usage (project root):
    .venv\\Scripts\\python.exe -B scripts\\verify_window_slack_v3.py PROJECT OUTDIR
"""
import sys, json, hashlib
from pathlib import Path

PROJECT = Path(sys.argv[1]).resolve(); OUT = Path(sys.argv[2]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(PROJECT))

from src.models import Layer, Point3D
from src.geometry_3d import lift_smoothed_route_to_layer
from src.multi_attribution import deserialize_plot
from src.three_layer_assignment_3d import LayerConfiguration, candidate_families
from src.layer_assignment_3d import build_elevation_candidate
from src.clearance_3d import analyze_route3d_self_clearance

CLEARANCE = 0.1
REQUIRED_RADIUS = 5.
SLACK_MM = 1e-5
DECISIONS = PROJECT/'outputs/3d_strategy_v2_rev2/512_c_fixed/decisions_C_fixed.json'
PLOT = PROJECT/'outputs/step_8_5_legacy_512_plot_geometry.json'
EVENTS = PROJECT/'outputs/step_8_5_legacy_512_physical_events.jsonl'
SOURCE = PROJECT/'src'


def sha256(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_inputs():
    planar = {r['id']: lift_smoothed_route_to_layer(deserialize_plot(r), Layer(0, 0))
        for r in json.loads(PLOT.read_text())['routes']}
    crossings = {}
    for text in EVENTS.read_text().splitlines():
        e = json.loads(text)
        if e['kind'] == 'cross':
            crossings.setdefault(tuple(sorted((e['route_a_id'], e['route_b_id']))), []).append(
                Point3D(e['point']['x'], e['point']['y'], 0))
    return planar, crossings


def recorded_ambiguous_rows(decisions):
    rows = []
    for step in decisions:
        target = tuple(step['target_pair'])
        for va in step['victim_attempts']:
            for row in va['candidates']:
                if 'SELF_AMBIGUOUS_CLEARANCE' in (row.get('basic_reasons') or []):
                    rows.append(dict(target=target, moved=va['route_id'],
                        candidate_index=row['candidate_index'], layer=row['target_layer_id'],
                        rise_window=tuple(row['rise_window']), fall_window=tuple(row['fall_window']),
                        step_index=step['step_index']))
    return rows


def find_candidate(candidates, rise, fall, layer):
    for c in candidates:
        if (tuple(c.rise_window), tuple(c.fall_window), c.layer_to) == (rise, fall, layer):
            return c
    return None


def window_groups(candidates):
    """'primitive|width' -> sorted window starts, from the enumeration itself."""
    groups = {}
    for c in candidates:
        for i, u, v in (c.rise_window, c.fall_window):
            groups.setdefault(f'{i}|{round(v-u, 12)}', set()).add(u)
    return {key: sorted(values) for key, values in groups.items()}


def match_window(route, window, shifted_groups, slack):
    """Nearest window of the slack-grown enumeration: |start difference| is
    delta (f=0), 0 (f=.5) or -delta (f=1), never more than 2*delta."""
    i, u, v = window
    delta = 2*slack/route.primitives[i].length() + 1e-15
    starts = shifted_groups.get(f'{i}|{round(v-u, 12)}', [])
    best = None
    for start in starts:
        gap = abs(start-u)
        if gap <= delta and (best is None or gap < best[0]):
            best = (gap, (i, start, start+(v-u)))
    return best[1] if best else None


def main():
    config = LayerConfiguration([Layer(0, 0.), Layer(1, 1.), Layer(2, 2.)], CLEARANCE,
        REQUIRED_RADIUS, 'LINE_ONLY_FINITE_WINDOWS', 'EXPERIMENTAL_SYNTHETIC')
    planar, crossings = load_inputs()
    decisions = json.loads(DECISIONS.read_text())
    rows = recorded_ambiguous_rows(decisions)

    transitions = {'CLEAR': 0, 'still_ambiguous': 0, 'collision': 0,
        'touching_threshold': 0, 'other_ambiguous_status': 0, 'build_rejected': 0,
        'window_not_available': 0}
    other_statuses = {}
    samples = []
    tasks = {}
    for row in rows:
        key = (row['target'], row['moved'])
        if key not in tasks:
            points = crossings.get(row['target']) or []
            task_rows = [r for r in rows if (r['target'], r['moved']) == key]
            base, base_failures = candidate_families(planar[row['moved']], row['target'], points, config)
            shifted, probe_failures = candidate_families(planar[row['moved']], row['target'], points,
                config, window_slack_mm=SLACK_MM)
            tasks[key] = dict(target=list(row['target']), moved=row['moved'],
                layer1_recorded_ambiguous=sum(1 for r in task_rows if r['layer'] == 1),
                layer2_recorded_ambiguous=sum(1 for r in task_rows if r['layer'] == 2),
                candidates_at_slack_zero=len(base), candidates_at_probe_slack=len(shifted),
                base_failures={str(k): v for k, v in base_failures.items()},
                probe_failures={str(k): v for k, v in probe_failures.items()},
                shifted_groups=window_groups(shifted))
        points = crossings.get(row['target']) or []
        rise = row['rise_window']; fall = row['fall_window']
        new_rise = match_window(planar[row['moved']], rise, tasks[key]['shifted_groups'], SLACK_MM)
        new_fall = match_window(planar[row['moved']], fall, tasks[key]['shifted_groups'], SLACK_MM)
        if new_rise is None or new_fall is None:
            transitions['window_not_available'] += 1
            continue
        try:
            candidate = build_elevation_candidate(planar[row['moved']], row['target'], points,
                config, new_rise, new_fall, target_layer_id=row['layer'])
            self_result = analyze_route3d_self_clearance(candidate.route, CLEARANCE)
            status = self_result['status']
        except ValueError as ex:
            transitions['build_rejected'] += 1
            other_statuses[str(ex)] = other_statuses.get(str(ex), 0)+1
            continue
        if status == 'CLEAR': transitions['CLEAR'] += 1
        elif status == 'AMBIGUOUS_CLEARANCE': transitions['still_ambiguous'] += 1
        elif status == 'COLLISION': transitions['collision'] += 1
        elif status == 'TOUCHING_THRESHOLD': transitions['touching_threshold'] += 1
        else:
            transitions['other_ambiguous_status'] += 1
            other_statuses[status] = other_statuses.get(status, 0)+1
        if len(samples) < 5:
            samples.append(dict(step_index=row['step_index'], target=list(row['target']),
                moved=row['moved'], candidate_index=row['candidate_index'], layer=row['layer'],
                recorded_rise_window=list(rise), recorded_fall_window=list(fall),
                matched_rise_window=list(new_rise), matched_fall_window=list(new_fall),
                start_shift_mm=[(new_rise[1]-rise[1])*planar[row['moved']].primitives[rise[0]].length(),
                    (new_fall[1]-fall[1])*planar[row['moved']].primitives[fall[0]].length()],
                self_clearance_status_after_shift=status,
                minimum_distance_mm=self_result['minimum_distance_mm']))

    failure_shifts = {}
    for (target, moved), task in tasks.items():
        for layer, value in task['base_failures'].items():
            if value != task['probe_failures'].get(layer):
                failure_shifts[f'{target}|{moved}|layer{layer}'] = dict(
                    at_slack_zero=value, at_probe_slack=task['probe_failures'].get(layer))

    total_candidates_at_slack_zero = sum(t['candidates_at_slack_zero'] for t in tasks.values())
    total_candidates_at_probe_slack = sum(t['candidates_at_probe_slack'] for t in tasks.values())

    record = dict(review_date='2026-10-05', scale=512, clearance_mm=CLEARANCE,
        window_slack_mm=SLACK_MM,
        slack_basis=('slack = 1e-5 mm is >=10x the worst converged ADAPTIVE_CHORD_BOUNDS error bound '
            '(distance_tol=1e-6 mm) and 1e4x the analytic classification tol (1e-9 mm); in this rebuild it '
            'insets each usable window by delta=slack/length at both ends (width shrinks by 2*delta) and moves '
            'a window start by delta*(1-2f). Measured on the saved 512 rows: '
            f'{transitions["CLEAR"]}/{len(rows)} recorded ambiguities rebuilt as CLEAR, with task candidate '
            f'totals {total_candidates_at_slack_zero} -> {total_candidates_at_probe_slack}. The 0.1 mm clearance '
            'criterion is unchanged, and this is the measured outcome of this probe only, not a guarantee about '
            'other inputs or candidates.'),
        source=dict(decisions=str(DECISIONS), decisions_sha256=sha256(DECISIONS),
            plot_sha256=sha256(PLOT), events_sha256=sha256(EVENTS),
            layer_assignment_3d_sha256=sha256(SOURCE/'layer_assignment_3d.py')),
        method=('Reconstruct every recorded SELF_AMBIGUOUS_CLEARANCE row from frozen planar geometry and saved '
            'CROSS anchors, then rebuild it with the corresponding window of the slack-grown enumeration, matched '
            'within 2*delta of the recorded start (the delta*(1-2f) move elevation_candidates performs when the '
            'pad grows by slack/length). No routing, no clearance-threshold change, no acceptance-rule change; '
            'the reported numbers are the measured outcome of this rebuild on the saved 512 rows.'),
        recorded_rows=len(rows), unique_tasks=len(tasks),
        status_after_shift=transitions, other_statuses=other_statuses,
        task_window_counts=dict(tasks=list(tasks.values()),
            tasks_with_fewer_candidates_after_shift=sum(
                1 for t in tasks.values() if t['candidates_at_probe_slack'] < t['candidates_at_slack_zero']),
            total_candidates_at_slack_zero=total_candidates_at_slack_zero,
            total_candidates_at_probe_slack=total_candidates_at_probe_slack),
        failure_shifts_on_recorded_tasks=failure_shifts,
        samples=samples,
        limitation=('Measured on the saved 512 ambiguous rows only; 1024 and other inputs were not individually '
            'rebuilt here and no claim is made about them. A marginally feasible window can drop out of the '
            'enumeration once its width shrinks by 2*delta, so unchanged candidate totals on these 31 tasks are '
            'an observation about these tasks, not a rule. Self-clearance status alone is reported, not complete '
            'candidate acceptability; centerline proximity is not loss or manufacturability.'))
    (OUT/'window_slack_probe.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps({k: record[k] for k in ('recorded_rows', 'unique_tasks', 'status_after_shift',
        'task_window_counts')}, indent=2))


if __name__ == '__main__':
    main()
