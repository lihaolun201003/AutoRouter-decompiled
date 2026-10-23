"""Runner: spatial grouped U-bundle 3D routing experiment.

Steps
-----
1. load the Manual-C4 dynamic-V2 result and the feasibility search artefacts
   (``_work/group_scan_results.json``, ``refined_corner1_scan.json``,
   ``g167_scan.json``, ``moved_group11.json``), which were produced by the
   exhaustive per-group 3D feasibility scan against the fixed 768-route world;
2. assign one (entry distance a, high-layer arc depth D) per quartet, keeping the
   16 U turns of a bundle nested (outer deeper) and the L2/L4 middle bundles'
   rise/fall windows staggered on the shared port columns;
3. build the two variants:
   * ``u_only``   : only the 256 target U routes are rebuilt (g167 stays at its
     original V2 geometry because it is blocked by non-U group 11 at L3);
   * ``final``    : additionally re-lift the blocking non-U quartet (C4 group 11)
     to L5 (recorded explicitly), so all 64 target quartets reach their layer;
4. authoritative 3D validation (``lift_cross.validate_payload_v4``), metrics,
   comparison table, figures, JSON artefacts.
"""
from __future__ import annotations

import json
import shutil
import time
from collections import Counter
from pathlib import Path

from ..v3c4.profile import apply as apply_profile

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = ROOT / 'outputs/manual_c4_new_connectivity'
AFTER_DIR = CAMPAIGN / 'phase5_dynamic_optimization/after'
OUT_DIR = CAMPAIGN / 'spatial_u_bundle_optimization'
WORK_DIR = OUT_DIR / '_work'

from . import spatial_u_bundle as SC  # noqa: E402  (module constants only)


def _read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _write_json(path, payload, indent=1):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=indent),
                    encoding='utf-8')
    return path


class _Logger:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lines = []

    def __call__(self, message):
        line = time.strftime('%H:%M:%S') + ' ' + str(message)
        print(line, flush=True)
        self.lines.append(line)
        with self.path.open('a', encoding='utf-8') as handle:
            handle.write(line + '\n')


# ---------------------------------------------------------------------------
# feasibility / plan
# ---------------------------------------------------------------------------
def load_feasibility():
    coarse = _read_json(WORK_DIR / 'group_scan_results.json')
    entries = {}
    for gid, item in coarse.items():
        entries[int(gid)] = [tuple(pair) for pair in item['feasible']]
    refined_path = WORK_DIR / 'refined_corner1_scan.json'
    if refined_path.exists():
        refined = _read_json(refined_path)
        for gid, pairs in refined.items():
            if pairs:
                entries[int(gid)] = [tuple(pair) for pair in pairs]
    g167_path = WORK_DIR / 'g167_scan.json'
    if g167_path.exists():
        entries[167] = [tuple(pair) for pair in _read_json(g167_path)]
    print(f'[u-bundle] feasibility groups={len(entries)} '
          f'g167={len(entries.get(167, []))}')
    return entries


def _pick_entry(entries, d_chosen, a_preference):
    """Pick the (a, D) entry with the chosen D, preferring a near the bundle value."""
    options = [pair for pair in entries if abs(pair[1] - d_chosen) <= 1e-9]
    if not options:
        raise ValueError(f'no feasible entry at D={d_chosen}')
    options.sort(key=lambda pair: (abs(pair[0] - a_preference), pair[0]))
    return options[0]


def choose_plan(campaign, log=print):
    from . import spatial_u_bundle as S
    feasibility = load_feasibility()
    plan = {}
    spec = {
        'z1_middle_U': dict(a=11.2, gap=0.5),
        'z2_corner_U_1': dict(a=None, gap=0.5),
        'z2_corner_U_2': dict(a=None, gap=0.5),
        'z2_middle_U': dict(a=1.2, gap=0.5),
    }
    for bundle, conf in S.BUNDLES.items():
        ranks = S.bundle_rank(campaign, bundle)
        pref = spec[bundle]
        per_group = []
        for gid in ranks:
            entries = feasibility.get(gid, [])
            if pref['a'] is not None:
                entries = [pair for pair in entries
                           if abs(pair[0] - pref['a']) <= 1e-6]
            if not entries:
                raise ValueError(f'{bundle} group {gid}: no feasible parameter')
            values = sorted({pair[1] for pair in entries})
            per_group.append(values)
        chain = S.choose_depth_chain(per_group, gap=pref['gap'])
        if chain is None:
            raise ValueError(f'{bundle}: could not build a nested D chain')
        for gid, d_chosen in zip(ranks, chain):
            entries = feasibility[gid]
            if pref['a'] is not None:
                entries = [pair for pair in entries
                           if abs(pair[0] - pref['a']) <= 1e-6]
            a_chosen, d = _pick_entry(entries, d_chosen, pref['a'] or 6.0)
            plan[gid] = dict(bundle=bundle, a=float(a_chosen), D=float(d),
                             layer=conf['layer'], layer_z=conf['layer_z'],
                             rank=ranks.index(gid))
        log(f'[u-bundle] plan {bundle}: '
            f'D {min(chain):.2f}..{max(chain):.2f} '
            f'a {sorted({plan[gid]["a"] for gid in ranks})}')
    if len(plan) != 64:
        raise ValueError(f'plan must cover 64 quartets, got {len(plan)}')
    return plan


# ---------------------------------------------------------------------------
# variant assembly
# ---------------------------------------------------------------------------
def load_moved_quartet():
    path = WORK_DIR / 'moved_group11.json'
    if not path.exists():
        return None
    payload = _read_json(path)
    return payload


def build_variant(campaign, plan, moved=None, label='final', log=print,
                  max_alternates=30):
    from . import spatial_u_bundle as S
    target_rids = campaign.target_rids
    moved_rids = set()
    moved_routes = []
    if moved is not None:
        moved_routes = moved['routes']
        moved_rids = {int(route['route_id']) for route in moved_routes}
    world = S.fixed_world(campaign, extra_excluded=moved_rids)
    new_routes = {}
    failures = {}
    detail = {}

    def accept(routes):
        for route in routes:
            world.add_route(route)
            new_routes[int(route['route_id'])] = route

    # the documented local re-route (blocking non-U quartet moved to L5)
    if moved is not None:
        violations = S.check_routes(world, moved_routes)
        if violations:
            log(f'[u-bundle] {label}: moved quartet validation failed '
                f'{violations[:2]}')
            return None
        accept(moved_routes)

    for bundle in ('z2_corner_U_1', 'z2_corner_U_2',
                   'z2_middle_U', 'z1_middle_U'):
        ranks = S.bundle_rank(campaign, bundle)
        for gid in ranks:
            chosen = plan[gid]
            candidates = [(chosen['a'], chosen['D'])]
            # alternates: feasible entries ordered by depth distance to the plan
            feas = sorted(plan_entries(plan, gid), key=lambda pair: (
                abs(pair[1] - chosen['D']), abs(pair[0] - chosen['a'])))
            for pair in feas:
                if len(candidates) >= max_alternates:
                    break
                if (abs(pair[0] - chosen['a']) <= 1e-9
                        and abs(pair[1] - chosen['D']) <= 1e-9):
                    continue
                candidates.append(pair)
            accepted = None
            for a_value, d_value in candidates:
                routes, error = S.build_quartet(
                    campaign, gid, chosen['layer'], chosen['layer_z'],
                    d_value, a_value, a_value)
                if routes is None:
                    continue
                violations = S.check_routes(world, routes)
                if violations:
                    continue
                accepted = (routes, a_value, d_value)
                break
            if accepted is None:
                failures[int(gid)] = dict(
                    bundle=bundle, layer=chosen['layer'],
                    reason='no feasible geometry against the final world '
                           '(blocked / same-plane conflict)')
                detail[int(gid)] = dict(gid=int(gid), bundle=bundle,
                                        status='failed', layer=chosen['layer'],
                                        target_z_mm=chosen['layer_z'],
                                        a=None, D=None)
                log(f'[u-bundle] {label}: group {gid} FAILED')
                continue
            routes, a_value, d_value = accepted
            accept(routes)
            parts = routes[0]['parts']
            transitions = [part for part in parts if part['kind'] == 'transition']
            flats = [part for part in parts if part['kind'] == 'flat']
            separation = float(S.group_separation(campaign, gid))
            total_2d = float(routes[0].get('xy_length_mm') or 0.0)
            detail[int(gid)] = dict(
                gid=int(gid), bundle=bundle, status='rebuilt',
                layer=int(chosen['layer']), target_z_mm=float(chosen['layer_z']),
                a_in=float(a_value), a_out=float(a_value),
                entry_straight_mm=float(a_value), exit_straight_mm=float(a_value),
                high_arc_depth_mm=float(d_value),
                separation_mm=separation,
                middle_straight_mm=round(separation - 2.0 * SC.RADIUS, 6),
                high_flat_length_mm=round(float(flats[1]['length_mm']), 6)
                if len(flats) > 1 else None,
                rise_start_mm=round(float(flats[0]['length_mm']), 6),
                fall_start_mm=round(float(sum(part['length_mm']
                                              for part in parts[:3])), 6),
                rise_start_xy=[round(float(v), 6) for v in transitions[0]['start']],
                rise_end_xy=[round(float(v), 6) for v in transitions[0]['end']],
                fall_start_xy=[round(float(v), 6) for v in transitions[1]['start']],
                fall_end_xy=[round(float(v), 6) for v in transitions[1]['end']],
                rise_z_mm=[float(transitions[0]['z0']), float(transitions[0]['z1'])],
                fall_z_mm=[float(transitions[1]['z0']), float(transitions[1]['z1'])],
                xy_path_length_mm=round(total_2d, 6),
                route_ids=[int(route['route_id']) for route in routes])
    payload = S.assemble_payload(campaign, new_routes, experiment=label)
    info = dict(label=label, moved=moved is not None,
                moved_routes=[int(route['route_id']) for route in moved_routes],
                new_routes=len(new_routes), failures=failures, detail=detail)
    return payload, info


_PLAN_ENTRIES = {}


def plan_entries(plan, gid):
    return _PLAN_ENTRIES.get(int(gid), [])


def set_plan_entries(feasibility):
    _PLAN_ENTRIES.clear()
    for gid, entries in feasibility.items():
        _PLAN_ENTRIES[int(gid)] = list(entries)


# ---------------------------------------------------------------------------
# full experiment
# ---------------------------------------------------------------------------
def run(out_dir=None, log=print):
    apply_profile()
    out_dir = Path(out_dir or OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = out_dir / 'figures'
    search_dir = out_dir / 'search'
    search_dir.mkdir(parents=True, exist_ok=True)
    for path in WORK_DIR.glob('*.json'):
        shutil.copy2(path, search_dir / path.name)

    campaign = SC.Campaign()
    feasibility = load_feasibility()
    set_plan_entries(feasibility)
    plan = choose_plan(campaign, log=log)
    moved = load_moved_quartet()

    started = time.perf_counter()
    variants = {}
    for label, moved_payload in (('u_only', None), ('final', moved)):
        payload, info = build_variant(campaign, plan, moved=moved_payload,
                                      label=label, log=log)
        if payload is None:
            continue
        report = SC.validate_payload(payload, log=log)
        metrics = SC.payload_metrics(campaign, payload, report)
        variants[label] = dict(payload=payload, report=report, info=info,
                               metrics=metrics)
        log(f'[u-bundle] {label}: routed={metrics["routed"]} '
            f'pairs={metrics["unique_crossing_pairs"]} '
            f'validation={metrics.get("validation_status")}')

    baseline = campaign.baseline_payload
    baseline_report = SC.validate_payload(baseline, log=log)
    baseline_metrics = SC.payload_metrics(campaign, baseline, baseline_report)

    final_label = 'final' if 'final' in variants else 'u_only'
    final = variants[final_label]
    # success count: quartets whose new geometry has a flat part on the target layer
    target_success = 0
    for gid in SC.TARGET_GIDS:
        conf = SC.BUNDLES[SC.GID_BUNDLE[gid]]
        route_ids = campaign.group_routes(gid)
        if all(rid in final['info']['detail'] and
               final['info']['detail'][rid].get('status') == 'rebuilt'
               for rid in route_ids):
            target_success += 1
    target_success = sum(1 for value in final['info']['detail'].values()
                         if value.get('status') == 'rebuilt')
    # (detail is per quartet, not per route)
    assignment = []
    for gid in SC.TARGET_GIDS:
        conf = SC.BUNDLES[SC.GID_BUNDLE[gid]]
        item = final['info']['detail'].get(gid)
        route_ids = campaign.group_routes(gid)
        status = 'target_layer_reached' if item and item['status'] == 'rebuilt' else 'failed'
        assignment.append(dict(
            group_id=int(gid), bundle=SC.GID_BUNDLE[gid], target_layer=int(conf['layer']),
            target_z_mm=float(conf['layer_z']), route_ids=route_ids,
            status=status,
            entry_straight_mm=item.get('entry_straight_mm') if item else None,
            exit_straight_mm=item.get('exit_straight_mm') if item else None,
            high_arc_depth_mm=item.get('high_arc_depth_mm') if item else None,
            a_in=item.get('a_in') if item else None,
            a_out=item.get('a_out') if item else None,
            separation_mm=item.get('separation_mm') if item else None,
            middle_straight_mm=item.get('middle_straight_mm') if item else None,
            high_flat_length_mm=item.get('high_flat_length_mm') if item else None,
            rise_start_mm=item.get('rise_start_mm') if item else None,
            fall_start_mm=item.get('fall_start_mm') if item else None,
            rise_start_xy=item.get('rise_start_xy') if item else None,
            fall_start_xy=item.get('fall_start_xy') if item else None,
            rise_z_mm=item.get('rise_z_mm') if item else None,
            fall_z_mm=item.get('fall_z_mm') if item else None,
            failure_reason=None if status == 'target_layer_reached' else
                           final['info']['failures'].get(int(gid), {}).get('reason')
                           or ('kept original V2 geometry (blocked by non-U routes)'
                               if final_label == 'u_only' else 'not rebuilt')))
    success = sum(1 for row in assignment if row['status'] == 'target_layer_reached')

    final_metrics = dict(final['metrics'])
    final_metrics.update(
        experiment='MANUAL_C4_SPATIAL_U_BUNDLE',
        target_quartets=64, target_quartets_reached=int(success),
        target_quartets_failed=int(64 - success),
        baseline_pairs=baseline_metrics['unique_crossing_pairs'],
        pair_delta=int(final_metrics['unique_crossing_pairs']
                       - baseline_metrics['unique_crossing_pairs']),
        runtime_seconds=round(time.perf_counter() - started, 2),
        moved_quartets=final['info']['moved'],
        moved_routes=final['info']['moved_routes'],
        failures=final['info']['failures'],
        validation=dict(
            status=final['report'].get('status'),
            exploratory_pass=final['report'].get('exploratory_pass'),
            geometry_pass=final['report'].get('geometry_pass'),
            counts=final['report'].get('counts'),
            stats=final['report'].get('stats'),
            violations=(final['report'].get('violations') or [])[:50]))
    _write_json(out_dir / 'routes_1024.json', final['payload'], indent=None)
    if 'u_only' in variants:
        _write_json(out_dir / 'routes_1024_u_only.json',
                    variants['u_only']['payload'], indent=None)
    _write_json(out_dir / 'u_layer_assignment.json',
                dict(schema='manual_c4_u_bundle_layer_assignment_v1',
                     target_quartets=64,
                     reached=int(success), failed=int(64 - success),
                     assignment=assignment,
                     modified_non_u_routes=(dict(group_id=11, target_layer=5,
                                                  layer_z_mm=2.5,
                                                  route_ids=final['info']['moved_routes'],
                                                  reason='blocking non-U quartet moved '
                                                         'from L3 to L5 to free g167')
                                            if final['info']['moved'] else None)),
                indent=1)
    _write_json(out_dir / 'validation.json',
                dict(schema='manual_c4_spatial_u_bundle_validation_v1',
                     final_label=final_label,
                     payload_validation=final['report'],
                     u_only_payload_validation=variants.get('u_only', {}).get('report'),
                     baseline_payload_validation=baseline_report,
                     world_check_note='every quartet was checked incrementally with '
                                      'l3d.world.World against the fixed layout before '
                                      'being added; final payload re-audited with '
                                      'l3d.validate_payload',), indent=1)
    comparison = _comparison(baseline_metrics, variants, success, log=log)
    _write_json(out_dir / 'comparison_table.json', comparison, indent=1)
    (out_dir / 'comparison_table.md').write_text(
        _comparison_markdown(comparison), encoding='utf-8')
    _write_json(out_dir / 'summary.json', final_metrics, indent=1)

    # figures
    try:
        from . import spatial_u_bundle_plots as P
        font_records = final['payload']
        target_manifest = {gid: dict(route_ids=list(
            SC.Campaign().group_routes(gid)), name=SC.GID_BUNDLE[gid],
            layer_z=SC.BUNDLES[SC.GID_BUNDLE[gid]]['layer_z'])
            for gid in SC.TARGET_GIDS}
        figures = P.plot_all(font_records, target_manifest, out_dir=figures_dir,
                             log=log)
        final_metrics['figures'] = str(figures)
        _write_json(out_dir / 'summary.json', final_metrics, indent=1)
    except Exception as exc:                       # noqa: BLE001
        log(f'[u-bundle] figures failed: {type(exc).__name__}: {exc}')

    log(f'[u-bundle] DONE success={success}/64 moved={final["info"]["moved"]} '
        f'pairs={final_metrics["unique_crossing_pairs"]} '
        f'validation={final_metrics["validation"]["status"]}')
    return dict(metrics=final_metrics, variants=variants, comparison=comparison,
                plan=plan, assignment=assignment)


def _comparison(baseline_metrics, variants, success, log=print):
    rows = []
    columns = [('基线：Manual-C4 动态优化 V2', baseline_metrics)]
    if 'u_only' in variants:
        columns.append(('仅修改 U：' + 'spatial U-bundle (u-only)',
                        variants['u_only']['metrics']))
    if 'final' in variants:
        columns.append(('最终：spatial U-bundle (final)',
                        variants['final']['metrics']))
    keys = [
        ('总布通数', 'routed'),
        ('唯一交叉线路对（全局去重）', 'unique_crossing_pairs'),
        ('同层 U-U 交叉对', 'same_layer_u_u_crossing_pairs'),
        ('升降次数', 'transitions'),
        ('三维总路径长度 (mm)', 'total_length_mm'),
        ('最小三维净空 (mm)', 'min_3d_clearance_mm'),
        ('独立几何验收', 'validation_status'),
    ]
    for label, key in keys:
        row = dict(metric=label, values={})
        for name, metrics in columns:
            row['values'][name] = metrics.get(key)
        rows.append(row)
    table = dict(schema='manual_c4_spatial_u_bundle_comparison_v1',
                 columns=[name for name, _ in columns],
                 rows=rows,
                 target_quartets=64, target_quartets_reached=int(success),
                 target_quartets_failed=int(64 - success),
                 notes=['U-only: 仅重建 256 条目标 U 路线，其他路线（含阻挡组 11）保持 V2 原样',
                        'final: 额外把阻挡的非 U C4 四元组（group 11）从 L3 重抬到 L5，'
                        '已逐条记录，属于分开比较的局部重路由阶段',
                        '交叉数为跨全部物理高度按唯一 (route_id_a, route_id_b) 去重',
                        '层高为探索性参数，几何 PASS 不等于制造工艺正式验收'])
    return table


def _comparison_markdown(table):
    columns = table['columns']
    lines = ['# 空间分组式 U 形线束三维布线：对照表', '',
             '| 指标 | ' + ' | '.join(columns) + ' |',
             '|---|' + '|'.join(['---:'] * len(columns)) + '|']
    for row in table['rows']:
        values = []
        for name in columns:
            value = row['values'].get(name)
            if isinstance(value, float):
                values.append(f'{value:,.3f}')
            elif value is None:
                values.append('—')
            else:
                values.append(str(value))
        lines.append(f"| {row['metric']} | " + ' | '.join(values) + ' |')
    lines += ['', f"- 目标分层四元组：{table['target_quartets_reached']}/64 "
                  f"（失败 {table['target_quartets_failed']}）"]
    lines += [''] + [f'> {note}' for note in table['notes']]
    return '\n'.join(lines) + '\n'


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=None)
    args = parser.parse_args(argv)
    out_dir = Path(args.out or OUT_DIR)
    logger = _Logger(out_dir / 'run.log')
    result = run(out_dir=out_dir, log=logger)
    print(json.dumps({key: result['metrics'][key] for key in
                      ('routed', 'target_quartets_reached',
                       'unique_crossing_pairs', 'transitions')},
                     ensure_ascii=False))
    return result


if __name__ == '__main__':
    main()
