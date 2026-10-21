"""Runner + figures for the V4-C4 crossing-avoidance 3D lift experiment."""
from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter, defaultdict
from pathlib import Path

from .profile import apply as apply_profile

OUT_ROOT_NAME = 'outputs/four_side_1024_v4_c4_crossing_lift'
Z_COLORS = {0.0: '#1f6fd6', 0.5: '#e07b1a', 1.0: '#2f9e44',
            1.5: '#7048e8', 2.0: '#e03131', 2.5: '#0c8599'}
Z_LABELS = {0.0: 'L1 row1 z=0.0', 0.5: 'L1 row2 z=0.5', 1.0: 'L2 z=1.0',
            1.5: 'L3 z=1.5', 2.0: 'L4 z=2.0', 2.5: 'L5 z=2.5'}


def _write_json(path, payload, indent=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=indent),
                    encoding='utf-8')
    return path


def _read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


# ---------------------------------------------------------------------------
# geometry sampling for plots
# ---------------------------------------------------------------------------
def _sample_primitive(primitive, step_deg=6.0):
    import numpy as np
    if primitive['kind'] == 'line':
        return np.array([primitive['p0'], primitive['p1']], dtype=float)
    center = primitive['center']
    radius = float(primitive['radius'])
    start = float(primitive['start_angle'])
    sweep = float(primitive['sweep'])
    count = max(6, int(abs(math.degrees(sweep)) / step_deg) + 1)
    angles = start + __import__('numpy').linspace(0.0, sweep, count)
    return np.stack([center[0] + radius * __import__('numpy').cos(angles),
                     center[1] + radius * __import__('numpy').sin(angles)], axis=1)


def _part_samples(part):
    """Return (N,3) samples of one flat/transition part in true XYZ."""
    import numpy as np
    from ..fsd25d import path3d as P
    if part['kind'] == 'flat':
        chunks = [_sample_primitive(primitive) for primitive in part['primitives']]
        if not chunks:
            return np.zeros((0, 3))
        points = np.concatenate(chunks, axis=0)
        z = np.full(len(points), float(part['z_mm']))
        return np.column_stack([points, z])
    samples = P.transition_samples(part)
    return np.array(samples, dtype=float)


# ---------------------------------------------------------------------------
# figures
# ---------------------------------------------------------------------------
def plot_all(lifter, payload, summary, figures_dir, log=print):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    import numpy as np
    from .plots_opt import draw_board

    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    figures_dir = Path(figures_dir)
    figures_dir.mkdir(parents=True, exist_ok=True)
    records = [record for record in payload['routes']
               if record.get('status') == 'routed']
    base_records = [record for record in lifter.records.values()
                    if record.get('status') == 'routed']
    lifted_records = [record for record in records if record.get('lifted')]

    def save(fig, name):
        png = figures_dir / name
        fig.savefig(png, dpi=220, bbox_inches='tight')
        fig.savefig(png.with_suffix('.svg'), bbox_inches='tight')
        plt.close(fig)
        log(f'[lift] figure {png.name}')

    def draw_record_2d(ax, record, color_by_z=True, linewidth=0.55, alpha=0.85):
        for part in record['parts']:
            points = _part_samples(part)
            if len(points) == 0:
                continue
            if part['kind'] == 'flat':
                z = float(part['z_mm'])
                color = Z_COLORS.get(round(z, 6), '#333333') if color_by_z else (
                    Z_COLORS[0.0] if record['plane'] == 'z1' else Z_COLORS[0.5])
            else:
                color = '#7a7a7a' if color_by_z else '#888888'
            ax.plot(points[:, 0], points[:, 1], color=color,
                    linewidth=linewidth, alpha=alpha, solid_capstyle='round')

    # 1. before / after XY comparison
    fig, axes = plt.subplots(1, 2, figsize=(21, 10.8))
    for ax in axes:
        draw_board(ax)
    for record in base_records:
        for primitive in record['primitives']:
            points = _sample_primitive(primitive)
            ax = axes[0]
            ax.plot(points[:, 0], points[:, 1],
                    color=Z_COLORS[0.0] if record['plane'] == 'z1' else Z_COLORS[0.5],
                    linewidth=0.5, alpha=0.7)
    for record in records:
        draw_record_2d(axes[1], record)
    handles = [Line2D([0], [0], color=Z_COLORS[0.0], lw=2,
                      label=f"row1 L1 z=0 ({sum(1 for r in base_records if r['plane'] == 'z1')})"),
               Line2D([0], [0], color=Z_COLORS[0.5], lw=2,
                      label=f"row2 L1 z=0.5 ({sum(1 for r in base_records if r['plane'] == 'z2')})")]
    axes[0].legend(handles=handles, loc='upper right', fontsize=8)
    for z in (1.0, 1.5, 2.0, 2.5):
        count = sum(1 for record in lifted_records
                    if any(part['kind'] == 'flat'
                           and abs(float(part['z_mm']) - z) < 1e-9
                           for part in record['parts']))
        if count:
            handles.append(Line2D([0], [0], color=Z_COLORS[z], lw=2,
                                  label=f"L{ {1.0: 2, 1.5: 3, 2.0: 4, 2.5: 5}[z] } z={z:g} ({count} 条)"))
    handles.append(Line2D([0], [0], color='#7a7a7a', lw=2, label='升降过渡 S 曲线'))
    axes[1].legend(handles=handles, loc='upper right', fontsize=8)
    axes[0].set_title('优化前（全部同高度 L1）', fontsize=12)
    axes[1].set_title(f"优化后（{summary['lifted_groups']} 个四元组抬升，"
                      f"交叉对 {summary['crossing_pairs_before']} -> "
                      f"{summary['crossing_pairs_after']}）", fontsize=12)
    fig.suptitle('V4-C4 交叉规避式三维抬升：优化前后 XY 俯视对比'
                 f"（布通 {summary['routed_before']}/1024 不变）", fontsize=13)
    save(fig, '01_before_after_xy.png')

    # 2. full 3D coloured by actual Z
    fig = plt.figure(figsize=(13, 12))
    ax = fig.add_subplot(111, projection='3d')
    for record in records:
        for part in record['parts']:
            points = _part_samples(part)
            if len(points) == 0:
                continue
            if part['kind'] == 'flat':
                color = Z_COLORS.get(round(float(part['z_mm']), 6), '#333333')
                width = 0.6
            else:
                color = '#7a7a7a'
                width = 0.9
            ax.plot(points[:, 0], points[:, 1], points[:, 2], color=color,
                    linewidth=width, alpha=0.75)
    ax.set_xlim(0, 150)
    ax.set_ylim(0, 150)
    ax.set_zlim(-0.1, 2.7)
    ax.set_xlabel('x (mm)')
    ax.set_ylabel('y (mm)')
    ax.set_zlabel('z (mm)')
    ax.view_init(elev=26, azim=-58)
    for z, color in Z_COLORS.items():
        ax.plot([], [], [], color=color, linewidth=2, label=Z_LABELS.get(z, f'z={z}'))
    ax.plot([], [], [], color='#7a7a7a', linewidth=2, label='升降过渡 S (R15)')
    ax.legend(loc='upper left', fontsize=8)
    ax.set_title('V4-C4 交叉规避式三维抬升：完整三维布线图\n'
                 f"抬升四元组 {summary['lifted_groups']} / 升降次数 "
                 f"{summary['transitions']} / 布通 {summary['routed_before']}/1024",
                 fontsize=11)
    save(fig, '02_3d_full.png')

    # 3. layer-by-layer
    layer_zs = [(1, [0.0, 0.5]), (2, [1.0]), (3, [1.5]), (4, [2.0]), (5, [2.5])]
    fig, axes = plt.subplots(2, 3, figsize=(20, 13))
    axes = axes.ravel()
    for index, (layer_id, zs) in enumerate(layer_zs):
        ax = axes[index]
        draw_board(ax, connector_labels=False)
        count = 0
        for record in records:
            for part in record['parts']:
                if part['kind'] != 'flat':
                    continue
                z = round(float(part['z_mm']), 6)
                if z not in zs:
                    continue
                for primitive in part['primitives']:
                    points = _sample_primitive(primitive)
                    ax.plot(points[:, 0], points[:, 1], color=Z_COLORS.get(z, '#333333'),
                            linewidth=0.5, alpha=0.75)
                    count += 1
        ax.set_title(f'L{layer_id}（z={[f"{z:g}" for z in zs]} mm）flat parts={count}',
                     fontsize=10)
        if count == 0:
            ax.text(75, 75, '本层无抬升线路\n(no lifted geometry on this layer)',
                    ha='center', va='center', fontsize=11, color='#888888')
    axes[5].axis('off')
    axes[5].text(0.02, 0.9, '分层说明\n\n'
                 f"抬升四元组: {summary['lifted_groups']}\n"
                 f"升降次数: {summary['transitions']}\n"
                 f"L2–L5 层高: {summary['layer_heights_mm']}\n"
                 '圆弧内禁止升降：所有升降过渡只在原路径直线段上\n'
                 '（硬约束由 straight_intervals 保证，圆弧整段保持恒定 Z）\n'
                 f"3D 验收: {summary.get('validation_status')}",
                 fontsize=9, va='top')
    fig.suptitle('V4-C4 交叉规避式三维抬升：L1–L5 分层布线图', fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    save(fig, '03_layers.png')

    # 4. early-climb / arc zoom
    def arc_count(route):
        return sum(1 for part in route['parts'] if part['kind'] == 'flat'
                   for primitive in part['primitives']
                   if primitive['kind'] == 'arc')
    candidates = [record for record in lifted_records]
    candidates.sort(key=lambda record: (-arc_count(record),
                                        int([part for part in record['parts']
                                             if part['kind'] == 'flat'
                                             and part['layer_id'] != 1][0]['layer_id'])))
    focus = candidates[0] if candidates else None
    fig, axes = plt.subplots(1, 2, figsize=(19, 9.5))
    for ax in axes:
        draw_board(ax)
    if focus is not None:
        up = next(part for part in focus['parts'] if part['kind'] == 'transition')
        cx, cy = float(up['start'][0]), float(up['start'][1])
        window = 26.0
        base_record = lifter.routed[int(focus['route_id'])]
        for ax in axes:
            ax.set_xlim(cx - window, cx + window)
            ax.set_ylim(cy - window, cy + window)
        # before: all routes in window (flat L1)
        for record in base_records:
            for primitive in record['primitives']:
                points = _sample_primitive(primitive)
                axes[0].plot(points[:, 0], points[:, 1],
                             color='#b0b0b0', linewidth=0.45, alpha=0.6)
        for primitive in base_record['primitives']:
            points = _sample_primitive(primitive)
            axes[0].plot(points[:, 0], points[:, 1], color='#1f6fd6',
                         linewidth=1.4)
        # after: everything colored by Z, focus highlighted
        for record in records:
            for part in record['parts']:
                points = _part_samples(part)
                if len(points) == 0:
                    continue
                if part['kind'] == 'flat':
                    color = Z_COLORS.get(round(float(part['z_mm']), 6), '#333333')
                else:
                    color = '#7a7a7a'
                axes[1].plot(points[:, 0], points[:, 1], color=color,
                             linewidth=1.4 if int(record['route_id']) == int(focus['route_id'])
                             else 0.45,
                             alpha=0.95 if int(record['route_id']) == int(focus['route_id'])
                             else 0.45)
        high_parts = [part for part in focus['parts']
                      if part['kind'] == 'flat' and part['layer_id'] != 1]
        for part in high_parts:
            for primitive in part['primitives']:
                if primitive['kind'] != 'arc':
                    continue
                points = _sample_primitive(primitive)
                axes[1].plot(points[:, 0], points[:, 1], color='#e03131',
                             linewidth=2.2, alpha=0.95, zorder=6)
        for ax, title in zip(axes, ('优化前：交叉点附近全部位于 L1',
                                    '优化后：进入圆弧前提前抬升，圆弧整段保持恒定高层 Z')):
            ax.plot([cx], [cy], marker='o', markersize=6, color='#c92a2a', zorder=8)
            ax.annotate('climb start', (cx, cy), textcoords='offset points',
                        xytext=(6, 6), fontsize=8, color='#c92a2a')
            ax.set_title(title, fontsize=11)
        axes[1].plot([], [], color=Z_COLORS[0.0], lw=2, label='L1 z=0')
        axes[1].plot([], [], color=Z_COLORS[0.5], lw=2, label='L1 row2 z=0.5')
        for z, color in Z_COLORS.items():
            if z not in (0.0, 0.5):
                axes[1].plot([], [], color=color, lw=2, label=f'L{ {1.0: 2, 1.5: 3, 2.0: 4, 2.5: 5}[z] } z={z:g}')
        axes[1].plot([], [], color='#7a7a7a', lw=2, label='S transition R15')
        axes[1].legend(loc='upper right', fontsize=7)
        fig.suptitle('V4-C4 交叉规避式三维抬升：圆弧前提前抬升局部放大图'
                     f"（route {focus['route_id']}，L"
                     f"{[part for part in focus['parts'] if part['kind'] == 'flat' and part['layer_id'] != 1][0]['layer_id']}）",
                     fontsize=12)
    save(fig, '04_early_climb_zoom.png')

    # 5. crossing-dense region before / after
    before_crossings = _read_json(lifter.out_dir / 'crossings_before.json')['crossings']
    grid = defaultdict(int)
    cell = 20.0
    for item in before_crossings:
        grid[(int(item['x'] // cell), int(item['y'] // cell))] += 1
    best = max(grid.items(), key=lambda pair: pair[1])[0] if grid else (3, 3)
    x0 = best[0] * cell - 12
    y0 = best[1] * cell - 12
    x1, y1 = x0 + 44, y0 + 44
    fig, axes = plt.subplots(1, 2, figsize=(19, 9.5))
    for ax in axes:
        draw_board(ax)
        ax.set_xlim(max(-9, x0), min(159, x1))
        ax.set_ylim(max(-9, y0), min(159, y1))
    for record in base_records:
        for primitive in record['primitives']:
            points = _sample_primitive(primitive)
            axes[0].plot(points[:, 0], points[:, 1],
                         color=Z_COLORS[0.0] if record['plane'] == 'z1'
                         else Z_COLORS[0.5], linewidth=0.45, alpha=0.6)
    inside = [item for item in before_crossings
              if x0 <= item['x'] <= x1 and y0 <= item['y'] <= y1]
    for item in inside:
        axes[0].plot([item['x']], [item['y']], marker='x', markersize=3.2,
                     color='#c92a2a', alpha=0.75)
    for record in records:
        for part in record['parts']:
            points = _part_samples(part)
            if len(points) == 0:
                continue
            if part['kind'] == 'flat':
                color = Z_COLORS.get(round(float(part['z_mm']), 6), '#333333')
            else:
                color = '#7a7a7a'
            axes[1].plot(points[:, 0], points[:, 1], color=color,
                         linewidth=0.45, alpha=0.6)
    axes[0].set_title(f'优化前：该区域同高度交叉点 {len(inside)} 个', fontsize=11)
    after_crossings_path = lifter.out_dir / 'crossings_after.json'
    after = _read_json(after_crossings_path)['crossings'] if after_crossings_path.exists() else []
    inside_after = [item for item in after
                    if x0 <= item['x'] <= x1 and y0 <= item['y'] <= y1]
    for item in inside_after:
        axes[1].plot([item['x']], [item['y']], marker='x', markersize=3.2,
                     color='#c92a2a', alpha=0.75)
    axes[1].set_title(f'优化后：该区域同高度交叉点 {len(inside_after)} 个', fontsize=11)
    fig.suptitle(f'V4-C4 交叉规避式三维抬升：交叉密集区域优化前后对比'
                 f'（region x[{x0:.0f},{x1:.0f}] y[{y0:.0f},{y1:.0f}]）', fontsize=12)
    save(fig, '05_crossing_region_before_after.png')
    return dict(figures_dir=str(figures_dir),
                files=sorted(str(path.relative_to(lifter.out_dir))
                             for path in figures_dir.glob('*')))


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def run(out_dir=None, v4_root=None, max_groups=40, time_limit=1800.0,
        smoke_groups=0, plots=True, log=print):
    apply_profile()
    from .lift_cross import (CrossingLifter, analyze_planes,
                             validate_payload_v4)

    started = time.perf_counter()
    lifter = CrossingLifter(v4_root=v4_root, out_dir=out_dir, log=log)
    lifter.analyze()
    if smoke_groups:
        history = lifter.optimize(max_groups=int(smoke_groups),
                                  time_limit=time_limit, log=log)
        _write_json(lifter.out_dir / 'smoke_summary.json',
                    dict(history=history, lifted_groups=len(lifter.lifted),
                         pair_count=len(lifter.pair_set)), indent=1)
        log(f'[lift] smoke done groups={len(lifter.lifted)} '
            f'pairs={len(lifter.pair_set)}')
        return dict(lifter=lifter, history=history)
    history = lifter.optimize(max_groups=int(max_groups),
                              time_limit=time_limit, log=log)
    payload = lifter.build_payload()
    _write_json(lifter.out_dir / 'routes_l3d.json', payload)
    _write_json(lifter.out_dir / 'layer_stack.json', lifter.stack.to_dict())
    validation = validate_payload_v4(payload, lifter.v4_root, log=log)
    repair_rounds = 0
    while (not validation.get('exploratory_pass')
           and repair_rounds < 40):
        violations = validation.get('violations') or []
        offending = set()
        for item in violations:
            if item.get('category') != 'clearance_violations':
                continue
            for key in ('route_id', 'other_route'):
                value = item.get(key)
                if value is None:
                    continue
                entry = lifter.route_group.get(int(value))
                if entry is not None:
                    offending.add(int(entry[0]))
        if not offending:
            log('[lift] validation failed without addressable violations; stop repair')
            break
        lifter.revert_groups(offending, log=log)
        repair_rounds += 1
        payload = lifter.build_payload()
        _write_json(lifter.out_dir / 'routes_l3d.json', payload)
        validation = validate_payload_v4(payload, lifter.v4_root, log=log)
    if repair_rounds:
        log(f'[lift] repair reverted {repair_rounds} round(s) of groups')
    # final exact crossing analysis of the saved 3D layout
    entries = lifter.final_flat_entries()
    after_crossings, after_reports, after_pairs = analyze_planes(
        entries, log=log, compute_positions=False)
    before_crossings = [dict(z=float(z), route_a=a, route_b=b, x=float(x),
                             y=float(y), angle_deg=float(angle))
                        for (z, a, b, x, y, _s_a, _s_b, angle)
                        in lifter.initial_crossings]
    _write_json(lifter.out_dir / 'crossings_before.json',
                dict(count=len(before_crossings),
                     pair_count=lifter.initial_pair_count,
                     crossings=before_crossings), indent=None)
    after_crossing_records = [
        dict(z=float(value[0]), route_a=int(value[1]), route_b=int(value[2]),
             x=float(value[3]), y=float(value[4]), angle_deg=float(value[7]))
        for value in after_crossings]
    _write_json(lifter.out_dir / 'crossings_after.json',
                dict(count=sum(report['crossing_count']
                               for report in after_reports.values()),
                     pair_count=sum(report['crossing_pair_count']
                                    for report in after_reports.values()),
                     remaining_pairs=sorted([list(pair) for plane_pairs
                                             in after_pairs.values()
                                             for pair in plane_pairs]),
                     crossings=after_crossing_records), indent=None)
    summary = lifter.summary(validation=validation,
                             after_reports=after_reports,
                             after_pairs_by_plane=after_pairs)
    _write_json(lifter.out_dir / 'lift_plans.json',
                dict(lifted=[plan for plan in lifter.group_plans.values()
                             if plan.get('status') == 'lifted'],
                     rejected=[plan for plan in lifter.group_plans.values()
                               if plan.get('status') == 'rejected'],
                     history=history), indent=1)
    _write_json(lifter.out_dir / 'validation.json', validation, indent=1)
    _write_json(lifter.out_dir / 'summary.json', summary, indent=1)
    checkpoint = dict(
        schema='four_side_1024_v4_c4_crossing_lift_checkpoint_v1',
        lifted_groups=[plan for plan in lifter.group_plans.values()
                       if plan.get('status') == 'lifted'],
        pair_count_after=summary['crossing_pairs_after'],
        lifted_route_ids=sorted(lifter.lifted),
        v4_csv=None,
        timestamp=time.strftime('%Y-%m-%dT%H:%M:%S'))
    _write_json(lifter.out_dir / 'checkpoint.json', checkpoint, indent=1)
    figure_info = {}
    if plots:
        figure_info = plot_all(lifter, payload, summary,
                               lifter.out_dir / 'plots', log=log)
        summary['figures'] = figure_info
        _write_json(lifter.out_dir / 'summary.json', summary, indent=1)
    log(f"[lift] DONE pairs {summary['crossing_pairs_before']} -> "
        f"{summary['crossing_pairs_after']} "
        f"groups={summary['lifted_groups']} transitions={summary['transitions']} "
        f"length {summary['length_total_before_mm']:.1f} -> "
        f"{summary['length_total_after_mm']:.1f} mm "
        f"validation={summary['validation_status']} "
        f"({time.perf_counter() - started:.1f}s)")
    return dict(lifter=lifter, summary=summary, validation=validation,
                payload=payload)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=None)
    parser.add_argument('--v4-root', type=Path, default=None)
    parser.add_argument('--max-groups', type=int, default=40)
    parser.add_argument('--time-limit', type=float, default=1800.0)
    parser.add_argument('--smoke-groups', type=int, default=0)
    parser.add_argument('--no-plots', action='store_true')
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

    result = run(out_dir=out_dir, v4_root=args.v4_root,
                 max_groups=args.max_groups, time_limit=args.time_limit,
                 smoke_groups=args.smoke_groups, plots=not args.no_plots,
                 log=log)
    log_handle.close()
    if 'summary' in result:
        summary = result['summary']
        print(json.dumps({key: summary[key] for key in
                          ('routed_before', 'crossing_pairs_before',
                           'crossing_pairs_after', 'lifted_groups',
                           'transitions', 'length_total_before_mm',
                           'length_total_after_mm', 'validation_status')},
                         ensure_ascii=False))
    return result


if __name__ == '__main__':
    main()
