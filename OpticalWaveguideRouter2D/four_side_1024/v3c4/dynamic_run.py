"""Runner + figures for the V4-C4 dynamic layer optimization (V2)."""
from __future__ import annotations

import argparse
import copy
import json
import shutil
import time
from pathlib import Path

from .profile import apply as apply_profile

OUT_ROOT_NAME = 'outputs/v4_c4_dynamic_layer_optimization'
B_ROOT_NAME = 'outputs/v4_c4_layer_height_ablation/B_0.50mm'
CACHE_NAME = 'outputs/v4_c4_layer_height_ablation/baseline_crossings.json'
LAYER_PALETTE = {2: '#2f9e44', 3: '#7048e8', 4: '#e03131', 5: '#0c8599'}
Z_LIMIT = (-0.1, 2.7)


def _read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _write_json(path, payload, indent=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=indent),
                    encoding='utf-8')
    return path


def _sha256(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _part_samples(part):
    from .lift_cross_run import _part_samples as samples
    return samples(part)


def _style_for_z(stack):
    style = {0.0: '#1f6fd6', 0.5: '#e07b1a'}
    for layer in stack.routing_layers:
        style[round(float(layer.physical_z_mm), 6)] = LAYER_PALETTE[int(layer.layer_id)]
    return style


def _decorate(ax, title):
    import matplotlib.pyplot as plt
    ax.set_xlim(0, 150)
    ax.set_ylim(0, 150)
    ax.set_zlim(*Z_LIMIT)
    ax.set_xlabel('x (mm)')
    ax.set_ylabel('y (mm)')
    ax.set_zlabel('z (mm)')
    ax.view_init(elev=26, azim=-58)
    ax.set_box_aspect((1.0, 1.0, 0.62))
    ax.set_title(title, fontsize=11)
    ax.grid(True)


def _draw_routes(ax, routes, style, linewidth=0.55, alpha=0.8):
    for route in routes:
        for part in route['parts']:
            points = _part_samples(part)
            if len(points) == 0:
                continue
            if part['kind'] == 'flat':
                color = style.get(round(float(part['z_mm']), 6), '#444444')
                ax.plot(points[:, 0], points[:, 1], points[:, 2],
                        color=color, linewidth=linewidth, alpha=alpha,
                        solid_capstyle='round')
            else:
                ax.plot(points[:, 0], points[:, 1], points[:, 2],
                        color='#7a7a7a', linewidth=max(linewidth, 0.7),
                        alpha=0.7, solid_capstyle='round')


def _save(fig, png_path):
    png_path = Path(png_path)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png_path, dpi=200, bbox_inches='tight')
    fig.savefig(png_path.with_suffix('.svg'), bbox_inches='tight')
    import matplotlib.pyplot as plt
    plt.close(fig)


def _figures(out_dir, optimizer, before_payload, after_payload,
             label='V4-C4', log=print):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    figures = Path(out_dir) / 'figures'
    figures.mkdir(parents=True, exist_ok=True)
    style = _style_for_z(optimizer.stack)
    before_routes = [record for record in before_payload['routes']
                     if record.get('status') == 'routed']
    after_routes = [record for record in after_payload['routes']
                    if record.get('status') == 'routed']

    fig = plt.figure(figsize=(12, 11))
    ax = fig.add_subplot(111, projection='3d')
    _draw_routes(ax, before_routes, style, linewidth=0.5, alpha=0.75)
    _decorate(ax, f'优化前：{label} 三维抬升结果（B 组 0.50 mm）— '
                  f'{len(before_routes)} routes')
    _save(fig, figures / 'before_3d.png')
    log(f'[dyn] figure before_3d.png')

    fig = plt.figure(figsize=(12, 11))
    ax = fig.add_subplot(111, projection='3d')
    _draw_routes(ax, after_routes, style, linewidth=0.5, alpha=0.75)
    _decorate(ax, f'优化后：动态换层与局部重调度 — {len(after_routes)} routes，'
                  f'唯一交叉对 {optimizer.initial_pair_count} -> '
                  f'{len(optimizer.pair_set)}')
    _save(fig, figures / 'after_3d.png')
    log(f'[dyn] figure after_3d.png')

    # typical two-quartet (or single-quartet fallback) layer-change zoom
    action = None
    for candidate in ('joint_reschedules', 'dynamic_layer_changes',
                      'interval_moves', 'failed_retries'):
        records = optimizer.stage_records.get(candidate) or []
        if records:
            action = dict(records[0], category=candidate)
            break
    if action is not None:
        if 'group_ids' in action:
            group_ids = [int(value) for value in action['group_ids']]
        else:
            group_ids = [int(action['group_id'])]
        involved = set()
        for gid in group_ids:
            involved.update(optimizer._route_of_group(gid))
        # directly related blocking routes from the recorded pair changes
        related = set()
        for key in ('removed_pairs', 'added_pairs'):
            for pair in action.get(key) or []:
                for rid in pair:
                    if len(related) < 30:
                        related.add(int(rid))
        before_by_id = {int(record['route_id']): record for record in before_routes}
        after_by_id = {int(record['route_id']): record for record in after_routes}
        show_before = [before_by_id[rid] for rid in sorted(involved | related)
                       if rid in before_by_id]
        show_after = [after_by_id[rid] for rid in sorted(involved | related)
                      if rid in after_by_id]
        fig = plt.figure(figsize=(18, 9))
        axes = [fig.add_subplot(1, 2, 1, projection='3d'),
                fig.add_subplot(1, 2, 2, projection='3d')]
        _draw_routes(axes[0], show_before, style, linewidth=1.0, alpha=0.95)
        _draw_routes(axes[1], show_after, style, linewidth=1.0, alpha=0.95)
        _decorate(axes[0], '调整前：参与重调度的四元组 + 直接相关阻挡线路')
        _decorate(axes[1], f'调整后：{action["category"]}'
                           f'（组 {group_ids}，层 '
                           f'{action.get("old_layers", action.get("old_layer"))} -> '
                           f'{action.get("new_layers", action.get("new_layer"))}）')
        fig.suptitle(f'{label} 动态换层前后局部三维对比（统一坐标范围与视角）',
                     fontsize=13)
        _save(fig, figures / 'joint_swap_zoom_before_after.png')
        log('[dyn] figure joint_swap_zoom_before_after.png')
    return sorted(path.name for path in figures.iterdir())


def run(out_dir=None, b_root=None, cache_path=None, time_limit=1800.0,
        v4_root=None, label='V4-C4', log=print):
    apply_profile()
    from .dynamic_opt import DynamicOptimizer
    from .lift_cross import validate_payload_v4

    repo = Path(__file__).resolve().parents[2]
    out_dir = Path(out_dir or (repo / OUT_ROOT_NAME))
    b_root = Path(b_root or (repo / B_ROOT_NAME))
    cache = Path(cache_path or (repo / CACHE_NAME))
    out_dir.mkdir(parents=True, exist_ok=True)
    before_dir = out_dir / 'before'
    before_dir.mkdir(parents=True, exist_ok=True)
    for name in ('routes_l3d.json', 'lift_plans.json', 'layer_stack.json',
                 'validation.json', 'summary.json'):
        shutil.copy2(b_root / name, before_dir / name)
    input_hashes = {
        'b_routes_l3d_sha256': _sha256(b_root / 'routes_l3d.json'),
        'b_layer_stack_sha256': _sha256(b_root / 'layer_stack.json'),
        'b_validation_sha256': _sha256(b_root / 'validation.json'),
        'b_summary_sha256': _sha256(b_root / 'summary.json'),
        'crossing_cache_sha256': _sha256(cache) if cache.exists() else None,
        'routing_root': str(v4_root) if v4_root is not None else None,
        'source_note': f'baseline = {label} 0.50 mm layer-spacing ablation group B',
    }
    _write_json(out_dir / 'input_hashes.json', input_hashes, indent=1)
    before_payload = _read_json(b_root / 'routes_l3d.json')

    optimizer = DynamicOptimizer(out_dir=out_dir, b_root=b_root,
                                 cache_path=cache, log=log,
                                 time_limit=time_limit, v4_root=v4_root)
    optimizer.topology_label = label
    optimize_info = optimizer.optimize()
    validation, after_payload = optimizer.validate_routes()
    _write_json(out_dir / 'after' / 'routes_l3d.json', after_payload)
    _write_json(out_dir / 'after' / 'layer_stack.json',
                optimizer.stack.to_dict())
    _write_json(out_dir / 'after' / 'validation.json', validation, indent=1)

    # final per-quartet layer / interval table
    assignments = []
    for group in optimizer.group_by_id.values():
        gid = int(group['group_id'])
        ids = [int(rid) for rid in group['route_ids']]
        if any(rid not in optimizer.current_routes for rid in ids):
            status = 'not_routed'
        elif all(rid in optimizer.lifted for rid in ids):
            status = 'lifted'
        else:
            status = 'flat_l1'
        assignments.append(dict(
            group_id=gid, kind=group['kind'], plane=group['plane'],
            route_ids=ids, status=status,
            layer_id=(optimizer.current_group_layer(gid) if status == 'lifted'
                      else 1),
            interval=(optimizer.current_group_interval(gid)
                      if status == 'lifted' else None)))
    _write_json(out_dir / 'after' / 'layer_assignments.json',
                dict(groups=assignments), indent=1)
    _write_json(out_dir / 'actions.json',
                dict(actions=optimizer.actions,
                     optimize_info=optimize_info,
                     rejected_records=optimizer.rejects[:3000],
                     rejected_total=len(optimizer.rejects)), indent=1)
    _write_json(out_dir / 'stage_records.json', optimizer.stage_records,
                indent=1)
    summary = optimizer.summary(validation=validation)
    summary.update(optimize_info)
    summary['topology_label'] = label
    summary['routing_root'] = str(v4_root) if v4_root is not None else None
    summary['figures'] = _figures(out_dir, optimizer, before_payload,
                                  after_payload, label=label, log=log)
    _write_json(out_dir / 'summary.json', summary, indent=1)
    checkpoint = dict(
        schema='v4_c4_dynamic_layer_optimization_checkpoint_v1',
        layout_version=optimizer.layout_version,
        unique_crossing_pairs=len(optimizer.pair_set),
        routes_file=str(out_dir / 'after' / 'routes_l3d.json'),
        layer_assignments=assignments,
        accepted_actions=optimizer.actions,
        input_hashes=input_hashes,
        note='restore: load after/routes_l3d.json as the current 3D layout and '
             'continue rescheduling from it',
        timestamp=time.strftime('%Y-%m-%dT%H:%M:%S'))
    _write_json(out_dir / 'checkpoint.json', checkpoint, indent=1)
    log(f'[dyn] DONE pairs {summary["unique_crossing_pairs_before"]} -> '
        f'{summary["unique_crossing_pairs_after"]}, '
        f'single={summary["single_group_reschedules"]}, '
        f'joint={summary["joint_reschedules"]}, '
        f'retry={summary["recovered_failed_groups"]}, '
        f'validation={summary["validation_status"]}')
    return dict(optimizer=optimizer, summary=summary, validation=validation,
                before_payload=before_payload, after_payload=after_payload)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=None)
    parser.add_argument('--b-root', type=Path, default=None)
    parser.add_argument('--cache', type=Path, default=None)
    parser.add_argument('--v4-root', type=Path, default=None,
                        help='routing root providing routes_1024.json '
                             '(default: historical V4-C4 routing root)')
    parser.add_argument('--label', default='V4-C4')
    parser.add_argument('--time-limit', type=float, default=1800.0)
    args = parser.parse_args(argv)
    repo = Path(__file__).resolve().parents[2]
    out_dir = Path(args.out or (repo / OUT_ROOT_NAME))
    out_dir.mkdir(parents=True, exist_ok=True)
    log_handle = open(out_dir / 'run.log', 'a', encoding='utf-8')

    def log(message):
        line = time.strftime('%H:%M:%S') + ' ' + str(message)
        print(line, flush=True)
        log_handle.write(line + '\n')
        log_handle.flush()

    result = run(out_dir=out_dir, b_root=args.b_root,
                 cache_path=args.cache, time_limit=args.time_limit,
                 v4_root=args.v4_root, label=args.label, log=log)
    log_handle.close()
    summary = result['summary']
    print(json.dumps({key: summary[key] for key in
                      ('routed_before', 'routed_after',
                       'unique_crossing_pairs_before',
                       'unique_crossing_pairs_after',
                       'single_group_reschedules', 'joint_reschedules',
                       'recovered_failed_groups', 'lifted_groups_after',
                       'transitions_after', 'length_delta_mm',
                       'validation_status')}, ensure_ascii=False))
    return result


if __name__ == '__main__':
    main()
