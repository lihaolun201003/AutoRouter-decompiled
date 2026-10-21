"""Experiment 2 (V3_C4_2D): strict four-fold symmetric two-dimensional routing.

Every group of four rotation-related connections is committed atomically:

* only the representative connection of the orbit (route id = minimum in the
  group) is searched with the frozen candidate generator;
* the other three geometries are the exact 90 deg / 180 deg / 270 deg rotations
  of the representative path (with traversal reversal when the CSV direction of
  the rotated member is opposite);
* the four paths are evaluated jointly against the placed layout and against
  each other; a group is committed only if all four are legal at the same time.

The per-candidate acceptance still uses the unchanged exact ``D56Index``; the
only new layer is the group-level search/commit policy.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

from .profile import apply as apply_profile


def _jsonable_args(args):
    return {key: (str(value) if isinstance(value, Path) else value)
            for key, value in vars(args).items()}


def route_legs(route):
    from . import inputs as V3
    sx, sy = V3.port_xy(route['source_endpoint'])
    tx, ty = V3.port_xy(route['target_endpoint'])
    return abs(tx - sx), abs(ty - sy)


def group_difficulty_metrics(group, blocks):
    """Canonical difficulty estimate of one rotation group (from its rep frame)."""
    rep = blocks[group['route_ids'][0]]
    frame = None
    dx, dy = route_legs(rep)
    if group['kind'] == 'adjacent':
        # direct L needs both legs >= R; larger(min(dx,dy)) is easier
        return dict(dx=dx, dy=dy, d=max(dx, dy))
    # opposite: a small lateral shift is easier (straight / short-S)
    return dict(dx=dx, dy=dy, d=dx)


def order_groups(groups, blocks, mode='easy'):
    """Order groups for sequential commit (``easy`` = low difficulty first)."""
    metrics = {g['group_id']: group_difficulty_metrics(g, blocks) for g in groups}
    if mode == 'csv':
        return sorted(groups, key=lambda g: g['group_id'])
    if mode == 'easy':
        if groups and groups[0]['kind'] == 'adjacent':
            return sorted(groups, key=lambda g: (-metrics[g['group_id']]['d'],
                                                g['group_id']))
        return sorted(groups, key=lambda g: (metrics[g['group_id']]['d'],
                                            g['group_id']))
    if mode == 'hard':
        if groups and groups[0]['kind'] == 'adjacent':
            return sorted(groups, key=lambda g: (metrics[g['group_id']]['d'],
                                                g['group_id']))
        return sorted(groups, key=lambda g: (-metrics[g['group_id']]['d'],
                                            g['group_id']))
    raise ValueError(f'unknown group order {mode}')


class GroupRouter:
    """Group-level (C4) sequential router over one V3LayoutState plane."""

    def __init__(self, state, groups, all_groups=None, log=print):
        from . import inputs as V3
        self.state = state
        self.log = log
        self.blocks = {r['route_id']: r for r in state.routes}
        self.groups = groups
        self.all_groups = all_groups if all_groups is not None else groups
        self.group_of_route = {}
        for group in self.all_groups:
            for phase, rid in enumerate(group['route_ids']):
                self.group_of_route[rid] = (group['group_id'], phase)
        self.group_results = {}
        self.failed_groups = {}

    # -- geometry ----------------------------------------------------------
    def build_quad(self, group, rep_world_primitives):
        """Rotate the representative path into the four oriented group paths."""
        from . import inputs as V3
        members = [self.blocks[rid] for rid in group['route_ids']]
        oriented = [rep_world_primitives]
        for phase in range(1, 4):
            rotated = V3.rotate_primitives(rep_world_primitives, phase)
            member = members[phase]
            prims, _reversed = V3.orient_primitives(
                rotated, member['source_endpoint'], member['target_endpoint'])
            oriented.append(prims)
        from ..d56.index import prepare
        prepared = [prepare(prims) for prims in oriented]
        return oriented, prepared

    # -- one group ---------------------------------------------------------
    def attempt_group(self, group, budget, candidate_iterator=None,
                      sort_key=None):
        from ..d56.index import prepare
        from ..d56.search import RouteResult
        from ..v2opt.search import candidates_for

        rep_id = group['route_ids'][0]
        frame = self.state.frames[rep_id]
        oracle = self.state.oracle_for(rep_id)
        ids = list(group['route_ids'])
        iterator = candidate_iterator
        if iterator is None:
            iterator = candidates_for(frame, oracle)
        evaluated = 0
        reasons = Counter()
        blockers = Counter()
        families = Counter()
        started = time.perf_counter()
        for candidate in iterator:
            if evaluated >= budget:
                reasons['candidate_budget_exhausted'] += 1
                break
            evaluated += 1
            families[candidate['family']] += 1
            world = frame.to_world(candidate['primitives'])
            try:
                oriented, prepared = self.build_quad(group, world)
            except ValueError:
                reasons['quad_orientation'] += 1
                continue
            # (a) each member against the accepted layout
            ok = True
            for rid, prep in zip(ids, prepared):
                evaluation = self.state.index.evaluate(prep)
                if not evaluation.valid:
                    reasons[evaluation.reason or 'invalid'] += 1
                    blockers.update(evaluation.blockers)
                    ok = False
                    break
            if not ok:
                continue
            # (b) the four new members against each other
            for rid, prep in zip(ids, prepared):
                self.state.index.add(rid, prep)
            quad_ok = True
            for rid, prep in zip(ids, prepared):
                evaluation = self.state.index.evaluate(prep, exclude=[rid])
                if not evaluation.valid:
                    reasons['quad_' + (evaluation.reason or 'invalid')] += 1
                    quad_ok = False
                    break
            for rid in ids:
                self.state.index.remove(rid)
            if not quad_ok:
                continue
            results = []
            for phase, (rid, prep, prims) in enumerate(zip(ids, prepared, oriented)):
                results.append(RouteResult(
                    rid, candidate['family'], dict(candidate['params']), prims,
                    prep, prep.length, 0, evaluated - 1, prep.bend_count))
            stats = dict(evaluated=evaluated, generated=evaluated,
                         families=dict(families), reasons=dict(reasons),
                         seconds=time.perf_counter() - started)
            return results, None, stats
        failure = dict(group_id=group['group_id'],
                       reason='no_legal_quad' if evaluated else 'no_candidate_generated',
                       evaluated=evaluated, candidate_evaluations=evaluated,
                       rejection_counts=dict(reasons), blockers=dict(blockers),
                       families=dict(families),
                       seconds=time.perf_counter() - started)
        return None, failure, dict(evaluated=evaluated, families=dict(families),
                                   reasons=dict(reasons),
                                   seconds=time.perf_counter() - started)

    # -- commit / failure --------------------------------------------------
    def commit_group(self, group, results):
        for result in results:
            self.state.add(result)
        self.group_results[group['group_id']] = [r.route_id for r in results]
        self.failed_groups.pop(group['group_id'], None)

    def fail_group(self, group, failure):
        for rid in group['route_ids']:
            self.state.failed[rid] = dict(
                route_id=rid, group_id=group['group_id'],
                reason=failure['reason'], evaluated=failure['evaluated'],
                rejection_counts=dict(failure['rejection_counts']),
                blockers=dict(failure['blockers']))
        self.failed_groups[group['group_id']] = dict(failure)

    # -- sequential pass ---------------------------------------------------
    def route_all(self, order, budget, deadline=None, checkpoint_fn=None,
                  checkpoint_every=16, iterator_factory=None):
        from ..v2opt import search as S
        started = time.perf_counter()
        details = []
        applied = []
        for position, group in enumerate(order, 1):
            if deadline is not None and time.perf_counter() > deadline:
                self.log(f'C4 sequential: time budget exhausted at '
                         f'{position - 1}/{len(order)}')
                break
            rep_id = group['route_ids'][0]
            iterator = None
            if iterator_factory is not None:
                frame = self.state.frames[rep_id]
                oracle = self.state.oracle_for(rep_id)
                iterator = iterator_factory(frame, oracle)
            results, failure, stats = self.attempt_group(
                group, budget, candidate_iterator=iterator)
            if results is not None:
                self.commit_group(group, results)
                applied.append(group['group_id'])
                details.append(dict(group_id=group['group_id'], found=True,
                                    families=stats['families'],
                                    evaluated=stats['evaluated'],
                                    seconds=round(stats['seconds'], 3)))
            else:
                self.fail_group(group, failure)
                details.append(dict(group_id=group['group_id'], found=False,
                                    reason=failure['reason'],
                                    evaluated=failure['evaluated'],
                                    rejection_counts=failure['rejection_counts'],
                                    blockers=failure['blockers'],
                                    families=failure.get('families'),
                                    seconds=round(failure['seconds'], 3)))
            if checkpoint_fn is not None and position % checkpoint_every == 0:
                checkpoint_fn(self, position)
            if position % 8 == 0:
                self.log(f'C4 sequential: {position}/{len(order)} groups '
                         f'applied={len(applied)} routed_routes='
                         f'{len(self.state.accepted)} '
                         f'elapsed={time.perf_counter() - started:.1f}s')
        summary = dict(budget=int(budget), attempted=len(details),
                       applied_groups=len(applied), applied_group_ids=applied,
                       routed_routes=len(self.state.accepted),
                       seconds=round(time.perf_counter() - started, 2))
        return details, summary

    # -- serial group rip-up & reroute ------------------------------------
    def rr_groups(self, budget, max_rounds=3, max_ripped_groups=6,
                  candidates_per_failed=12, checkpoint_fn=None):
        """Small serial rip-up/reroute: reopen blocking groups for failed groups."""
        from ..v2opt import search as S
        rounds = []
        started = time.perf_counter()
        pending = [g for g in self.groups if g['group_id'] in self.failed_groups]
        for round_index in range(1, max_rounds + 1):
            gain = 0
            pending = [g for g in self.groups if g['group_id'] in self.failed_groups]
            pending.sort(key=lambda g: len(self.failed_groups[g['group_id']]
                                           .get('blockers') or {}))
            for group in pending:
                failure = self.failed_groups[group['group_id']]
                blocker_routes = [int(k) for k, _count in
                                  sorted((failure.get('blockers') or {}).items(),
                                         key=lambda item: -item[1])]
                blocker_groups = []
                for rid in blocker_routes:
                    entry = self.group_of_route.get(rid)
                    if entry is None or entry[0] in blocker_groups:
                        continue
                    blocker_groups.append(entry[0])
                blocker_groups = blocker_groups[:max_ripped_groups]
                if not blocker_groups:
                    continue
                snapshot = self.state.snapshot()
                removed = []
                for gid in blocker_groups:
                    if gid in self.failed_groups:
                        continue
                    for rid in self.blocks_group(gid)['route_ids']:
                        if rid in self.state.accepted:
                            self.state.remove(rid)
                            removed.append((rid, gid))
                    self.group_results.pop(gid, None)
                if not removed:
                    continue
                results, new_failure, _stats = self.attempt_group(
                    group, budget, sort_key=None)
                if results is None:
                    self.state.restore(snapshot)
                    continue
                self.commit_group(group, results)
                # try to reinsert the ripped groups one by one
                gain += 1
                for gid in blocker_groups:
                    if gid in self.group_results or gid in self.failed_groups:
                        continue
                    g2 = self.blocks_group(gid)
                    res2, failure2, _ = self.attempt_group(g2, budget)
                    if res2 is not None:
                        self.commit_group(g2, res2)
                    else:
                        self.fail_group(g2, failure2)
                self.log(f'  group R&R round {round_index}: recovered group '
                         f'{group["group_id"]} (+{gain}) routed_routes='
                         f'{len(self.state.accepted)}')
                if checkpoint_fn is not None:
                    checkpoint_fn(self, round_index)
            rounds.append(dict(round=round_index, recovered=gain,
                               routed_routes=len(self.state.accepted),
                               failed_groups=len(self.failed_groups),
                               seconds=round(time.perf_counter() - started, 2)))
            self.log(f'C4 group R&R round {round_index}: recovered={gain} '
                     f'routed_routes={len(self.state.accepted)} '
                     f'failed_groups={len(self.failed_groups)}')
            if gain == 0:
                break
        return dict(rounds=rounds, recovered=sum(r['recovered'] for r in rounds),
                    seconds=round(time.perf_counter() - started, 2))

    def blocks_group(self, gid):
        return next(g for g in self.all_groups if g['group_id'] == gid)

    def reconcile(self):
        """Rebuild group bookkeeping from the live accepted layout."""
        self.group_results = {}
        self.failed_groups = {}
        for group in self.all_groups:
            gid = group['group_id']
            if all(rid in self.state.accepted for rid in group['route_ids']):
                self.group_results[gid] = list(group['route_ids'])
            else:
                failure = self.state.failed.get(group['route_ids'][0]) or {}
                self.failed_groups[gid] = dict(
                    group_id=gid,
                    reason=failure.get('reason', 'no_legal_quad'),
                    evaluated=failure.get('evaluated', 0),
                    rejection_counts=dict(failure.get('rejection_counts') or {}),
                    blockers=dict(failure.get('blockers') or {}))
        return self.group_results, self.failed_groups

    def prime_failed_groups(self):
        """Populate ``failed_groups`` from the live state failure records."""
        for group in self.groups:
            if group['group_id'] in self.failed_groups:
                continue
            if all(rid in self.state.accepted for rid in group['route_ids']):
                continue
            rep_id = group['route_ids'][0]
            failure = self.state.failed.get(rep_id) or {}
            if not failure:
                continue
            self.failed_groups[group['group_id']] = dict(
                group_id=group['group_id'],
                reason=failure.get('reason', 'no_legal_quad'),
                evaluated=failure.get('evaluated', 0),
                rejection_counts=dict(failure.get('rejection_counts') or {}),
                blockers=dict(failure.get('blockers') or {}))
        return self.failed_groups

    # -- export ------------------------------------------------------------
    def augment_route_records(self, payload):
        for record in payload.get('routes') or []:
            entry = self.group_of_route.get(int(record['route_id']))
            if entry is None:
                continue
            record['rotation_group_id'] = entry[0]
            record['rotation_phase'] = entry[1]
            record['c4_symmetry'] = 'strict_group_commit'
        return payload


def run_plane(plane, order_name, budget, out_dir, limit_groups=0,
              rr_rounds=0, rr_budget=None, time_limit=None, checkpoint_every=16,
              retry_passes=0, log=print):
    apply_profile()
    from ..fslw import config as C
    from . import inputs as V3
    from . import validate2d
    from .layout import state_for

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / 'run.log'

    def logline(message):
        line = time.strftime('%H:%M:%S') + ' ' + str(message)
        print(line, flush=True)
        with open(log_path, 'a', encoding='utf-8') as handle:
            handle.write(line + '\n')

    started = time.perf_counter()
    groups_all, route_group = V3.build_groups()
    plane_groups = [g for g in groups_all if g['plane'] == plane]
    logline(f'V3_C4_2D plane={plane} groups={len(plane_groups)} order={order_name} '
            f'budget={budget} limit_groups={limit_groups}')
    logline(f'radius={C.RADIUS_MM} mm fixed40={C.FIXED_RADIUS_40MM}')

    state = state_for(plane, log=logline)
    router = GroupRouter(state, plane_groups, log=logline)
    order = order_groups(plane_groups, router.blocks, mode=order_name)
    if limit_groups:
        order = order[:limit_groups]

    def checkpoint_callback(group_router, position):
        path = out_dir / 'checkpoint.json'
        _save_group_checkpoint(group_router, path, tag=f'{plane}_{position}')

    details, summary = router.route_all(
        order, budget,
        deadline=(time.perf_counter() + time_limit) if time_limit else None,
        checkpoint_fn=checkpoint_callback, checkpoint_every=checkpoint_every)
    logline(f'C4 sequential done groups={len(router.group_results)}/'
            f'{len(plane_groups)} routed_routes={len(state.accepted)} '
            f'({summary["seconds"]:.1f}s)')

    rr_info = None
    if rr_rounds > 0:
        rr_info = router.rr_groups(
            budget=rr_budget or budget, max_rounds=rr_rounds,
            checkpoint_fn=checkpoint_callback)
        router.reconcile()
        logline(f'C4 R&R done routed_routes={len(state.accepted)} '
                f'groups={len(router.group_results)} '
                f'failed_groups={len(router.failed_groups)}')
    retry_history = []
    for pass_index in range(1, int(retry_passes) + 1):
        router.reconcile()
        pending = [g for g in plane_groups
                   if g['group_id'] in router.failed_groups]
        if not pending:
            break
        pending_order = order_groups(pending, router.blocks, mode=order_name)
        _details, pass_summary = router.route_all(
            pending_order, budget, checkpoint_fn=checkpoint_callback,
            checkpoint_every=checkpoint_every)
        router.reconcile()
        retry_history.append(dict(pass_index=pass_index,
                                  attempted=len(pending_order),
                                  applied_groups=pass_summary['applied_groups'],
                                  routed_routes=len(state.accepted),
                                  failed_groups=len(router.failed_groups),
                                  seconds=pass_summary['seconds']))
        logline(f'C4 retry pass {pass_index}: routed_routes='
                f'{len(state.accepted)} failed_groups='
                f'{len(router.failed_groups)}')
        if rr_rounds > 0 and router.failed_groups:
            router.rr_groups(budget=rr_budget or budget,
                             max_rounds=int(rr_rounds),
                             checkpoint_fn=checkpoint_callback)
            router.reconcile()
            logline(f'C4 retry pass {pass_index} R&R: routed_routes='
                    f'{len(state.accepted)} failed_groups='
                    f'{len(router.failed_groups)}')
    routed_groups_live = len(router.group_results)
    failed_groups_live = len(router.failed_groups)

    checkpoint = out_dir / 'checkpoint.json'
    _save_group_checkpoint(router, checkpoint, tag=f'V3_C4_2D_{plane}_{order_name}')

    algorithm_detail = dict(
        name='V3_C4_2D', algorithm='C4_2D',
        process_profile='R15_min_radius_15mm', radius_mm=float(C.RADIUS_MM),
        fixed_radius_40mm=False, geometry_mode='d56', crossing_policy='exact',
        candidate_generator='v2opt.candext (D56 lines + 90 deg arcs + short-S)',
        candidate_budget_per_group=int(budget),
        strategy=f'{order_name} group order, representative search + rot90 lift, '
                 f'atomic group commit',
        order=order_name, forced_symmetry=True,
        group_count=len(plane_groups), routed_groups=routed_groups_live,
        failed_groups=failed_groups_live)
    extra = dict(experiment='V3_C4_2D', plane=plane, order=order_name,
                 budget=int(budget), groups=len(plane_groups),
                 routed_groups=routed_groups_live,
                 failed_group_ids=sorted(router.failed_groups),
                 sequential=summary, rr=rr_info, retry_history=retry_history,
                 checkpoint=str(checkpoint),
                 forced_symmetry=True, seconds=round(time.perf_counter() - started, 2))
    payload = state.payload('C4_2D', algorithm_detail, 'V3_C4_2D')
    payload['v3c4'] = extra
    payload['rotation_groups'] = [
        dict(group_id=g['group_id'], kind=g['kind'], plane=g['plane'],
             route_ids=g['route_ids'],
             status='routed' if g['group_id'] in router.group_results else 'failed')
        for g in plane_groups]
    payload['failed_groups'] = [
        dict(failure) for _gid, failure in
        sorted(router.failed_groups.items())]
    router.augment_route_records(payload)
    (out_dir / 'routes.json').write_text(
        json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    (out_dir / 'run_summary.json').write_text(
        json.dumps(dict(algorithm_detail, plane=plane, routed=len(state.accepted),
                        total=len(state.routes),
                        failed=len(state.routes) - len(state.accepted),
                        seconds=extra['seconds'],
                        routed_groups=routed_groups_live,
                        failed_groups=failed_groups_live,
                        group_order=order_name, budget=int(budget),
                        rr=rr_info, retry_history=retry_history,
                        checkpoint=str(checkpoint)),
                   indent=1, ensure_ascii=False), encoding='utf-8')

    # integrated validation on the saved payload
    saved = json.loads((out_dir / 'routes.json').read_text(encoding='utf-8'))
    plane_report = validate2d.audit_plane(saved, plane, label=f'V3_C4_2D_{plane}',
                                          log=logline)
    c4_report = validate2d.audit_c4_groups(saved['routes'], groups_all,
                                           route_group, log=logline)
    passed = bool(plane_report['passed'] and c4_report['passed'])
    validation = dict(schema='four_side_1024_v3_c4_2d_experiment_validation_v1',
                      experiment='V3_C4_2D', plane=plane, passed=passed,
                      plane_audit=plane_report, c4_symmetry=c4_report)
    (out_dir / 'validation.json').write_text(
        json.dumps(validation, indent=1, ensure_ascii=False), encoding='utf-8')
    logline(f'written {out_dir} routed_routes={len(state.accepted)} '
            f'routed_groups={routed_groups_live} '
            f'validation={"PASS" if passed else "FAIL"}')
    return dict(plane=plane, routed=len(state.accepted),
                routed_groups=routed_groups_live,
                failed_groups=failed_groups_live,
                seconds=extra['seconds'], validation_passed=passed,
                out_dir=str(out_dir))


def _save_group_checkpoint(router, path, tag=''):
    state = router.state
    data = dict(schema='four_side_1024_v3c4_group_checkpoint_v1',
                plane=state.plane, topology=state.topology, tag=tag,
                timestamp=time.strftime('%Y-%m-%dT%H:%M:%S'),
                routed=[dict(route_id=rid,
                             group_id=router.group_of_route[rid][0],
                             phase=router.group_of_route[rid][1],
                             primitives=result.primitives,
                             family=result.family, params=result.params)
                        for rid, result in sorted(state.accepted.items())],
                failed_groups={str(gid): failure for gid, failure
                               in sorted(router.failed_groups.items())},
                routed_groups=len(router.group_results),
                failed_group_count=len(router.failed_groups))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    tmp.replace(path)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plane', choices=['z1', 'z2'], required=True)
    parser.add_argument('--order', default='easy',
                        choices=['easy', 'hard', 'csv'])
    parser.add_argument('--budget', type=int, default=400)
    parser.add_argument('--limit-groups', type=int, default=0)
    parser.add_argument('--rr-rounds', type=int, default=0)
    parser.add_argument('--rr-budget', type=int, default=0)
    parser.add_argument('--time-limit', type=float, default=0.0)
    parser.add_argument('--checkpoint-every', type=int, default=16)
    parser.add_argument('--retry-passes', type=int, default=0)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    result = run_plane(args.plane, args.order, args.budget, args.out,
                       limit_groups=args.limit_groups,
                       rr_rounds=args.rr_rounds, rr_budget=args.rr_budget,
                       time_limit=args.time_limit or None,
                       checkpoint_every=args.checkpoint_every,
                       retry_passes=args.retry_passes)
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == '__main__':
    main()
