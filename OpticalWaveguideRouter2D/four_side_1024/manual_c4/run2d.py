"""Phase 2 runner: strict C4 two-dimensional routing of the new manual connectivity.

Run one plane (z1 / z2) from scratch with the frozen R15 D56 candidate families and
the unchanged atomic C4 group policy; then combine the two planes into the full
1024-channel XY route table under ``outputs/manual_c4_new_connectivity/phase2_2d``.

Every plane is re-audited by the frozen authoritative checker
(``fslw.validate_fslw``, ``policy='strict'``) plus the C4 rotation audit, the
2048-port coverage audit and the connectivity identity check.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

from ..v3c4.profile import apply as apply_profile  # no heavy imports


def _jsonable_args(args):
    return {key: (str(value) if isinstance(value, Path) else value)
            for key, value in vars(args).items()}


def run_plane(plane, order_mode, budget, out_dir, rr_rounds=0, rr_budget=None,
              retry_passes=0, time_limit=None, checkpoint_every=16,
              limit_groups=0, log=print):
    apply_profile()
    from ..fslw import config as C
    from ..v3c4 import validate2d
    from ..v3c4.c4 import _save_group_checkpoint
    from . import audit2d
    from . import connectivity as CONN
    from .router import ManualGroupRouter, order_groups
    from .state import state_for

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / 'run.log'

    def logline(message):
        line = time.strftime('%H:%M:%S') + ' ' + str(message)
        print(line, flush=True)
        with open(log_path, 'a', encoding='utf-8') as handle:
            handle.write(line + '\n')

    started = time.perf_counter()
    groups_all = CONN.groups_for_plane(plane)
    logline(f'MANUAL_C4_2D plane={plane} groups={len(groups_all)} order={order_mode} '
            f'budget={budget} rr_rounds={rr_rounds} retry_passes={retry_passes}')
    logline(f'radius={C.RADIUS_MM} mm fixed40={C.FIXED_RADIUS_40MM} '
            f'width={C.WIDTH_MM} clearance={C.CLEARANCE_MM}')
    kinds = Counter(g['kind'] for g in groups_all)
    logline(f'plane group kinds: {dict(kinds)}')
    order_stats = dict(kinds=dict(kinds))

    state = state_for(plane, log=logline)
    router = ManualGroupRouter(state, groups_all, log=logline)
    same_cache = router.prime_same_candidates()
    logline(f'same-side U candidate groups: {len(same_cache)} '
            f'(candidate counts: {sorted(Counter(len(v) for v in same_cache.values()).items())})')
    order = order_groups(groups_all, router, mode=order_mode)
    if limit_groups:
        order = order[:limit_groups]

    def checkpoint_callback(group_router, position):
        _save_group_checkpoint(group_router, out_dir / 'checkpoint.json',
                               tag=f'MANUAL_C4_2D_{plane}_{position}')

    details, summary = router.route_all(
        order, budget,
        deadline=(time.perf_counter() + time_limit) if time_limit else None,
        checkpoint_fn=checkpoint_callback, checkpoint_every=checkpoint_every,
        same_candidates_cache=same_cache)
    logline(f'C4 sequential done groups={len(router.group_results)}/'
            f'{len(groups_all)} routed_routes={len(state.accepted)} '
            f'({summary["seconds"]:.1f}s)')

    rr_info = None
    if rr_rounds > 0:
        rr_info = router.rr_groups(
            budget=rr_budget or budget, max_rounds=rr_rounds,
            checkpoint_fn=checkpoint_callback)
        router.reconcile()
    retry_history = []
    for pass_index in range(1, int(retry_passes) + 1):
        router.reconcile()
        pending = [g for g in groups_all if g['group_id'] in router.failed_groups]
        if not pending:
            break
        pending_order = order_groups(pending, router, mode=order_mode)
        _details, pass_summary = router.route_all(
            pending_order, budget, checkpoint_fn=checkpoint_callback,
            checkpoint_every=checkpoint_every, same_candidates_cache=same_cache)
        router.reconcile()
        retry_history.append(dict(pass_index=pass_index,
                                  attempted=len(pending_order),
                                  applied_groups=pass_summary['applied_groups'],
                                  routed_routes=len(state.accepted),
                                  failed_groups=len(router.failed_groups),
                                  seconds=pass_summary['seconds']))
        logline(f'C4 retry pass {pass_index}: routed_routes='
                f'{len(state.accepted)} failed_groups={len(router.failed_groups)}')
        if rr_rounds > 0 and router.failed_groups:
            router.rr_groups(budget=rr_budget or budget, max_rounds=int(rr_rounds),
                             checkpoint_fn=checkpoint_callback)
            router.reconcile()

    routed_groups_live = len(router.group_results)
    failed_groups_live = len(router.failed_groups)
    checkpoint = out_dir / 'checkpoint.json'
    _save_group_checkpoint(router, checkpoint, tag=f'MANUAL_C4_2D_{plane}_{order_mode}')

    algorithm_detail = dict(
        name='MANUAL_C4_2D', algorithm='C4_2D',
        process_profile='R15_min_radius_15mm', radius_mm=float(C.RADIUS_MM),
        fixed_radius_40mm=False, geometry_mode='d56', crossing_policy='exact',
        candidate_generator='v2opt.candext (D56 lines + 90 deg arcs + short-S) and '
                            'r15.u_geometry (same-side U, quarter_pair, R=15)',
        candidate_budget_per_group=int(budget),
        strategy=f'{order_mode} group order, representative search + rot90 lift, '
                 f'atomic group commit (including same-side U groups)',
        order=order_mode, forced_symmetry=True, group_count=len(groups_all),
        routed_groups=routed_groups_live, failed_groups=failed_groups_live,
        same_side_groups=len(same_cache))
    extra = dict(experiment='MANUAL_C4_2D', plane=plane, order=order_mode,
                 budget=int(budget), groups=len(groups_all),
                 group_kinds=dict(kinds), routed_groups=routed_groups_live,
                 failed_group_ids=sorted(router.failed_groups),
                 sequential=summary, rr=rr_info, retry_history=retry_history,
                 checkpoint=str(checkpoint), forced_symmetry=True,
                 same_side_u_groups=len(same_cache),
                 seconds=round(time.perf_counter() - started, 2))
    payload = state.payload('C4_2D', algorithm_detail, 'MANUAL_C4_2D')
    payload['manual_c4'] = extra
    payload['rotation_groups'] = [
        dict(group_id=g['group_id'], kind=g['kind'], plane=g['plane'],
             route_ids=g['route_ids'],
             status='routed' if g['group_id'] in router.group_results else 'failed')
        for g in groups_all]
    payload['failed_groups'] = [dict(failure) for _gid, failure
                                in sorted(router.failed_groups.items())]
    router.augment_route_records(payload)
    (out_dir / 'routes.json').write_text(
        json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    (out_dir / 'run_summary.json').write_text(
        json.dumps(dict(algorithm_detail, plane=plane,
                        routed=len(state.accepted), total=len(state.routes),
                        failed=len(state.routes) - len(state.accepted),
                        seconds=extra['seconds'],
                        routed_groups=routed_groups_live,
                        failed_groups=failed_groups_live,
                        group_order=order_mode, budget=int(budget),
                        rr=rr_info, retry_history=retry_history,
                        checkpoint=str(checkpoint)),
                   indent=1, ensure_ascii=False), encoding='utf-8')

    saved = json.loads((out_dir / 'routes.json').read_text(encoding='utf-8'))
    plane_report = audit2d.audit_plane(saved, plane,
                                       label=f'MANUAL_C4_2D_{plane}', log=logline)
    groups_all_full = CONN.combined_topology()['groups']
    route_group = CONN.route_group_map()
    c4_report = validate2d.audit_c4_groups(saved['routes'], groups_all,
                                           route_group, log=logline)
    passed = bool(plane_report['passed'] and c4_report['passed'])
    validation = dict(schema='manual_c4_2d_plane_validation_v1',
                      experiment='MANUAL_C4_2D', plane=plane, passed=passed,
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


# ---------------------------------------------------------------------------
# combine both planes into the full 1024 XY table + integrated acceptance
# ---------------------------------------------------------------------------
def combine(phase2_dir=None, log=print):
    apply_profile()
    from . import audit2d
    from . import connectivity as CONN
    from ..v3c4.validate2d import audit_c4_groups

    phase2_dir = Path(phase2_dir or (CONN.OUT_ROOT / 'phase2_2d'))
    planes = {}
    records_all = []
    plane_validation = {}
    for plane in CONN.PLANES:
        payload = json.loads((phase2_dir / plane / 'routes.json').read_text(
            encoding='utf-8'))
        planes[plane] = payload
        records_all.extend(payload['routes'])
        validation = json.loads((phase2_dir / plane / 'validation.json').read_text(
            encoding='utf-8'))
        plane_validation[plane] = validation
    records_all.sort(key=lambda record: int(record['route_id']))
    topology = CONN.combined_topology()
    groups = topology['groups']
    route_group = CONN.route_group_map()
    group_status = []
    for group in groups:
        members = [next(r for r in records_all if int(r['route_id']) == rid)
                   for rid in group['route_ids']]
        routed = all(m.get('status') == 'routed' for m in members)
        group_status.append(dict(group_id=group['group_id'], plane=group['plane'],
                                 kind=group['kind'], pair=group['pair'],
                                 route_ids=group['route_ids'],
                                 status='routed' if routed else 'failed'))
    from ..fslw import config as C
    from ..fslw import validate_fslw as V

    routed = [r for r in records_all if r.get('status') == 'routed']
    by_plane = Counter(r['plane'] for r in routed)
    by_relation = Counter(r['relation'] for r in routed)
    total_relation = Counter(r['relation'] for r in records_all)
    total_length = round(sum(float(r.get('length_mm') or 0.0) for r in routed), 4)
    crossing_pairs = {}
    for plane in CONN.PLANES:
        plane_routes = [r for r in routed if r['plane'] == plane]
        prepared = [V.prepare_route(r['primitives'], route_id=int(r['route_id']))
                    for r in plane_routes]
        audit = V.audit_route_pairs(prepared, clearance=C.CLEARANCE_MM,
                                    sagitta=C.SAGITTA_MM, policy='strict')
        crossing_pairs[plane] = dict(crossing_count=audit['crossing_count'],
                                     crossing_pair_count=audit[
                                         'crossing_pair_count'],
                                     violation_count=audit['violation_pair_count'])
    failed_records = [dict(route_id=int(r['route_id']), plane=r['plane'],
                           relation=r['relation'],
                           source_endpoint=r['source_endpoint'],
                           target_endpoint=r['target_endpoint'],
                           reason=r.get('reason') or 'not_attempted',
                           group_id=(route_group[int(r['route_id'])][0]
                                     if int(r['route_id']) in route_group else None))
                      for r in records_all if r.get('status') != 'routed']
    payload = dict(
        schema='manual_c4_routes_v1', topology=CONN.TOPOLOGY,
        forced_symmetry=True,
        connectivity_csv=topology['combined_csv']['path'],
        connectivity_sha256=topology['combined_csv']['sha256'],
        manual_inputs=topology['manual'],
        routed=len(routed), failed=len(records_all) - len(routed),
        total=len(records_all),
        routed_by_plane=dict(by_plane),
        routed_by_relation=dict(by_relation),
        total_by_relation=dict(total_relation),
        routed_groups=sum(1 for g in group_status if g['status'] == 'routed'),
        total_groups=len(group_status),
        total_length_mm=total_length,
        rotation_groups=group_status,
        plane_crossings=crossing_pairs,
        failed_routes=failed_records,
        routes=records_all)
    (phase2_dir / 'routes_1024.json').write_text(
        json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    (phase2_dir / 'routes_z1.json').write_text(
        json.dumps(planes['z1'], ensure_ascii=False), encoding='utf-8')
    (phase2_dir / 'routes_z2.json').write_text(
        json.dumps(planes['z2'], ensure_ascii=False), encoding='utf-8')
    (phase2_dir / 'failed_routes.json').write_text(
        json.dumps(dict(experiment='MANUAL_C4_2D', failed=failed_records),
                   ensure_ascii=False), encoding='utf-8')
    # integrated independent acceptance
    coverage = audit2d.audit_full_coverage(records_all, log=log)
    identity = audit2d.audit_identity(records_all, log=log)
    uniqueness = audit2d.audit_no_duplicate_geometry(records_all, log=log)
    c4 = audit_c4_groups(records_all, groups, route_group, log=log)
    c4['schema'] = 'manual_c4_c4_symmetry_validation_v1'
    errors = []
    if payload['routed'] == 0:
        errors.append('no_routed_route')
    passed = bool(coverage['passed'] and identity['passed'] and
                  uniqueness['passed'] and c4['passed'] and
                  all(v['passed'] for v in plane_validation.values()))
    validation = dict(schema='manual_c4_2d_integrated_validation_v1',
                      stage='phase2_2d', passed=passed,
                      routed=payload['routed'], failed=payload['failed'],
                      routed_by_plane=payload['routed_by_plane'],
                      routed_by_relation=payload['routed_by_relation'],
                      planes={plane: dict(manifest=plane_validation[plane]['plane_audit'],
                                          passed=plane_validation[plane]['passed'])
                              for plane in CONN.PLANES},
                      coverage=coverage, identity=identity,
                      geometry_uniqueness=uniqueness, c4_symmetry=c4,
                      errors=errors,
                      strict_policy='fslw.validate_fslw strict')
    (phase2_dir / 'validation.json').write_text(
        json.dumps(validation, indent=1, ensure_ascii=False), encoding='utf-8')
    summary = dict(
        schema='manual_c4_2d_run_summary_v1', stage='phase2_2d',
        total=payload['total'], routed=payload['routed'],
        failed=payload['failed'],
        routed_by_plane=payload['routed_by_plane'],
        routed_by_relation=payload['routed_by_relation'],
        total_by_relation=payload['total_by_relation'],
        routed_groups=payload['routed_groups'], total_groups=payload['total_groups'],
        total_length_mm=payload['total_length_mm'],
        plane_crossings=payload['plane_crossings'],
        validation_passed=passed,
        output=str(phase2_dir))
    (phase2_dir / 'run_summary.json').write_text(
        json.dumps(summary, indent=1, ensure_ascii=False), encoding='utf-8')
    log(f'[combine] routed={payload["routed"]}/{payload["total"]} '
        f'groups={payload["routed_groups"]}/{payload["total_groups"]} '
        f'validation={"PASS" if passed else "FAIL"}')
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p_plane = sub.add_parser('plane')
    p_plane.add_argument('--plane', choices=['z1', 'z2'], required=True)
    p_plane.add_argument('--order', default='easy')
    p_plane.add_argument('--budget', type=int, default=1600)
    p_plane.add_argument('--rr-rounds', type=int, default=2)
    p_plane.add_argument('--rr-budget', type=int, default=0)
    p_plane.add_argument('--retry-passes', type=int, default=3)
    p_plane.add_argument('--time-limit', type=float, default=0.0)
    p_plane.add_argument('--checkpoint-every', type=int, default=16)
    p_plane.add_argument('--limit-groups', type=int, default=0)
    p_plane.add_argument('--out', type=Path, required=True)
    p_combine = sub.add_parser('combine')
    p_combine.add_argument('--phase2-dir', type=Path, default=None)
    args = parser.parse_args(argv)
    if args.command == 'plane':
        result = run_plane(args.plane, args.order, args.budget, args.out,
                           rr_rounds=args.rr_rounds,
                           rr_budget=args.rr_budget or None,
                           retry_passes=args.retry_passes,
                           time_limit=args.time_limit or None,
                           checkpoint_every=args.checkpoint_every,
                           limit_groups=args.limit_groups)
    else:
        result = combine(phase2_dir=args.phase2_dir)
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == '__main__':
    main()
