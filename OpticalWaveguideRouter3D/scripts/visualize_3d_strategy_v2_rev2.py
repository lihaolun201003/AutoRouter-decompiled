"""Step 15 revision figures: corrected-C rerun, D/E diagnostic, failure reasons.

Read-only over saved experiment outputs. Usage (project root):
    .venv\\Scripts\\python.exe -B scripts\\visualize_3d_strategy_v2_rev2.py PROJECT OLD_DIR NEW_DIR
"""
import sys, json, csv
from collections import Counter
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.collections import LineCollection

ROOT = Path(sys.argv[1]).resolve()
OLD = Path(sys.argv[2]).resolve()
NEW = Path(sys.argv[3]).resolve()
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT/'scripts/publication'))
import pubstyle
from src.models import Layer, Point3D
from src.geometry_3d import lift_smoothed_route_to_layer, LineSegment3D, PlanarArcSegment3D, CosineTransition3D
from src.multi_attribution import deserialize_plot
from src.fixed_1024_routing import deserialize_route3d

FIG = NEW/'figures'; FIG.mkdir(parents=True, exist_ok=True)
COLORS = {'A': pubstyle.PALETTE['gray'], 'B': pubstyle.PALETTE['blue'],
          'C': pubstyle.PALETTE['vermillion'], 'C_fixed': pubstyle.PALETTE['reddish_purple']}
LAYER_COLORS = {0: '#87929c', 1: '#0072B2', 2: '#D55E00', 'transition': '#713d88'}
files = []


def jsread(path): return json.loads(Path(path).read_text(encoding='utf-8'))


def csvread(path):
    with open(path, encoding='utf-8-sig', newline='') as f: return list(csv.DictReader(f))


def ledgers(size, which):
    folder = (OLD if which == 'old' else NEW)/f'{size}_three_layer_abc'
    tag = 'C' if which == 'old' else 'C_fixed'
    return {s: jsread(folder/f'ledger_{s}.json') for s in
            (('A', 'B', 'C') if which == 'old' else ('C_fixed',))}


def figure_main_results():
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
    for ax, size in zip(axes, (512, 1024)):
        old = jsread(OLD/f'{size}_three_layer_abc'/'summary.json')
        new_c = jsread(NEW/f'{size}_c_fixed'/'summary_C_fixed.json')['ledger']
        labels = ['A\n(原记录)', 'B\n(原记录)', 'C\n(原记录)', 'C 修正\n(本轮重跑)']
        values = [old['runs'][s]['ledger']['final_collision_pair_count'] for s in 'ABC'] + \
                 [new_c['final_collision_pair_count']]
        colors = [COLORS['A'], COLORS['B'], COLORS['C'], COLORS['C_fixed']]
        bars = ax.bar(labels, values, color=colors, width=.62)
        ax.bar_label(bars, fmt='{:,.0f}', fontsize=8, padding=2)
        ax.set_ylim(min(values)*0.97, max(values)*1.02)
        ax.set_title(f'{size} 条连接 · 终态中心线近距对数（预算 {new_c["candidate_budget"]:,} 次候选评价上限）')
        ax.grid(alpha=.2, axis='y')
    fig.tight_layout()
    for ext in ('png', 'pdf'):
        fig.savefig(FIG/f'g1_main_results.{ext}', dpi=300, bbox_inches='tight'); files.append(f'g1_main_results.{ext}')
    plt.close(fig)


def figure_pairs_vs_evaluations():
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.9))
    for ax, size in zip(axes, (512, 1024)):
        for strategy in 'ABC':
            curve = jsread(OLD/f'{size}_three_layer_abc'/f'curve_{strategy}.json')
            ax.plot([p['candidate_evaluations'] for p in curve], [p['collision_pair_count'] for p in curve],
                color=COLORS[strategy], lw=1.3, label=strategy)
        curve = jsread(NEW/f'{size}_c_fixed'/'curve_C_fixed.json')
        ax.plot([p['candidate_evaluations'] for p in curve], [p['collision_pair_count'] for p in curve],
            color=COLORS['C_fixed'], lw=1.5, ls='--', label='C 修正')
        ax.set_xlabel('累计候选评价次数（evaluate_elevation 调用）')
        ax.set_ylabel('中心线近距对数（0.1 mm 阈值）')
        ax.set_title(f'{size} 条连接')
        ax.legend(title='策略', loc='upper right'); ax.grid(alpha=.2)
    fig.tight_layout()
    for ext in ('png', 'pdf'):
        fig.savefig(FIG/f'g2_pairs_vs_evaluations.{ext}', dpi=300, bbox_inches='tight'); files.append(f'g2_pairs_vs_evaluations.{ext}')
    plt.close(fig)


def figure_costs():
    rows = []
    for size in (512, 1024):
        old = jsread(OLD/f'{size}_three_layer_abc'/'summary.json')
        for strategy in 'ABC':
            ledger = old['runs'][strategy]['ledger']
            rows.append((size, strategy, ledger))
        rows.append((size, 'C 修正', jsread(NEW/f'{size}_c_fixed'/'summary_C_fixed.json')['ledger']))
    panels = [('runtime_seconds', '运行时间（s）'), ('final_extra_length_mm', '终态额外长度（mm）'),
              ('accepted_moves', '接受修改次数'), ('candidate_evaluations', '候选评价次数')]
    fig, axes = plt.subplots(1, 4, figsize=(12.5, 3.7))
    color_map = {**COLORS, 'C 修正': COLORS['C_fixed']}
    for ax, (key, label) in zip(axes, panels):
        positions, heights, colors = [], [], []
        for size_index, size in enumerate((512, 1024)):
            for index, (row_size, strategy, ledger) in enumerate(rows):
                if row_size != size: continue
                positions.append(size_index*6 + index)
                heights.append(float(ledger[key]))
                colors.append(color_map[strategy])
        bars = ax.bar(positions, heights, color=colors, width=.85)
        ax.set_xticks([1.5, 7.5]); ax.set_xticklabels(['512', '1024'])
        ax.set_title(label); ax.grid(alpha=.2, axis='y')
        ax.bar_label(bars, fmt=lambda v: f'{v:,.0f}' if abs(v) >= 100 else f'{v:.2f}', fontsize=6.5, padding=1)
        ax.set_ylim(0, max(heights)*1.25)
    handles = [Line2D([0], [0], color=color_map[k], lw=6, label=k) for k in ('A', 'B', 'C', 'C 修正')]
    fig.legend(handles=handles, ncol=4, loc='lower center', frameon=False, bbox_to_anchor=(.5, -.02))
    fig.tight_layout(rect=(0, .04, 1, 1))
    for ext in ('png', 'pdf'):
        fig.savefig(FIG/f'g3_costs.{ext}', dpi=300, bbox_inches='tight'); files.append(f'g3_costs.{ext}')
    plt.close(fig)


def figure_de_comparison():
    summary = jsread(NEW/'512_de_diagnostic'/'summary_DE.json')
    rows = {row['mode']: row for row in summary['comparison']}
    panels = [('final_collision_pairs', '终态近距对数'), ('accepted_moves', '接受修改次数'),
              ('candidate_evaluations', '候选评价次数'), ('relocations', '接受的重定位次数')]
    fig, axes = plt.subplots(1, 4, figsize=(12, 3.6))
    colors = {'D': pubstyle.PALETTE['orange'], 'E': pubstyle.PALETTE['green']}
    for ax, (key, label) in zip(axes, panels):
        values = [float(rows['D'][key]), float(rows['E'][key])]
        bars = ax.bar(['D\n(仅首次抬升)', 'E\n(允许重定位)'], values, color=[colors['D'], colors['E']], width=.55)
        ax.bar_label(bars, fmt='{:,.0f}', fontsize=9, padding=2)
        ax.set_title(label); ax.grid(alpha=.2, axis='y')
        ax.set_ylim(0, max(values)*1.25 if max(values) else 1)
    fig.tight_layout()
    for ext in ('png', 'pdf'):
        fig.savefig(FIG/f'g4_de_comparison.{ext}', dpi=300, bbox_inches='tight'); files.append(f'g4_de_comparison.{ext}')
    plt.close(fig)


def figure_relocation_rejections():
    steps = jsread(NEW/'512_de_diagnostic'/'decisions_E.json')
    reasons = Counter()
    for step in steps:
        for va in step['victim_attempts']:
            if va.get('movement') != 'RELOCATION': continue
            for row in va['candidates']:
                if row['status'] == 'BASIC_REJECTED':
                    for reason in row['basic_reasons']: reasons['基本验收：' + reason] += 1
                else:
                    for reason in (row.get('full_reasons') or []): reasons['完整验收：' + reason] += 1
    labels = {'基本验收：SELF_AMBIGUOUS_CLEARANCE': '基本验收：自检歧义\n(SELF_AMBIGUOUS_CLEARANCE)',
              '基本验收：TARGET_NOT_CLEARED': '基本验收：目标对未清除\n(TARGET_NOT_CLEARED)',
              '完整验收：NO_STRICT_GLOBAL_DECREASE': '完整验收：净减少不严格为正\n(NO_STRICT_GLOBAL_DECREASE)'}
    order = list(labels)
    values = [reasons.get(key, 0) for key in order]
    fig, ax = plt.subplots(figsize=(8.5, 3.6))
    bars = ax.bar([labels[k] for k in order], values, color=pubstyle.PALETTE['vermillion'], width=.5)
    ax.bar_label(bars, fmt='{:,.0f}', padding=3)
    ax.set_ylabel('候选个数')
    ax.set_title('E 诊断组：28 次重定位候选评价的拒绝原因（接受 0 次）')
    ax.grid(alpha=.2, axis='y'); ax.set_ylim(0, max(values)*1.25)
    fig.tight_layout()
    for ext in ('png', 'pdf'):
        fig.savefig(FIG/f'g5_relocation_rejections.{ext}', dpi=300, bbox_inches='tight'); files.append(f'g5_relocation_rejections.{ext}')
    plt.close(fig)


def _sample(primitive, n=None):
    if isinstance(primitive, LineSegment3D): n = n or 2
    elif isinstance(primitive, PlanarArcSegment3D): n = n or max(12, min(65, int(abs(primitive.sweep_angle)/(np.pi/64))+1))
    else: n = n or 49
    return np.array([[q.x, q.y, q.z] for q in (primitive.point_at(float(t)) for t in np.linspace(0, 1, n))])


def _classify(primitive):
    if isinstance(primitive, CosineTransition3D): return 'transition'
    return int(round(primitive.point_at(0).z))


def figure_route_before_after():
    steps = jsread(NEW/'512_de_diagnostic'/'decisions_E.json')
    accepted = [s for s in steps if s['status'] == 'ELEVATED']
    assert accepted, 'no accepted modification in the diagnostic'
    planar = {r['id']: lift_smoothed_route_to_layer(deserialize_plot(r), Layer(0, 0))
        for r in jsread(ROOT/'outputs/step_8_5_legacy_512_plot_geometry.json')['routes']}
    # Pick, from the accepted modifications, the route with the largest XY extent so
    # the before/after geometry is actually readable; the choice is stated in the report.
    def xy_extent(rid):
        pts = np.array([[q.x, q.y] for p in planar[rid].primitives
            for q in (p.point_at(0.), p.point_at(.5), p.point_at(1.))])
        return (pts[:, 0].max()-pts[:, 0].min())*(pts[:, 1].max()-pts[:, 1].min())
    step = max(accepted, key=lambda s: xy_extent(s['moved_route_id']))
    rid = step['moved_route_id']
    final = {row['route_id']: deserialize_route3d(row['geometry'])
        for row in jsread(NEW/'512_de_diagnostic'/'final_routes_E.json')['routes']}
    before = planar[rid]; after = final[rid]
    before_segments = [(_classify(p), _sample(p)) for p in before.primitives]
    after_segments = [(_classify(p), _sample(p)) for p in after.primitives]
    cloud = np.concatenate([p for _, p in after_segments])
    lo, hi = cloud.min(axis=0), cloud.max(axis=0)
    fig = plt.figure(figsize=(12, 4.2))
    ax = fig.add_subplot(1, 3, 1)
    for kind, pts in after_segments:
        ax.plot(pts[:, 0], pts[:, 1], color=LAYER_COLORS[kind],
            ls=':' if kind == 'transition' else '-', lw=1.4)
    ax.set_title(f'路线 {rid} 修改后 XY 投影\n（与修改前完全相同）')
    ax.set_xlabel('x (mm)'); ax.set_ylabel('y (mm)'); ax.grid(alpha=.2); ax.set_aspect('equal')
    ax = fig.add_subplot(1, 3, 2)
    labeled = False
    for kind, pts in before_segments:
        ax.plot(pts[:, 0], pts[:, 2], color='#555555', ls='--', lw=1.4, alpha=.9,
            label=None if labeled else '修改前（Layer 0，虚线）')
        labeled = True
    for kind, pts in after_segments:
        ax.plot(pts[:, 0], pts[:, 2], color=LAYER_COLORS[kind],
            ls=':' if kind == 'transition' else '-', lw=1.8)
    ax.set_xlabel('x (mm)'); ax.set_ylabel('z (mm，真实值 0/1/2)'); ax.set_yticks([0, 1, 2])
    ax.set_ylim(-.08, 2.12)
    ax.set_title('XZ 侧视（沿程高度）'); ax.grid(alpha=.2)
    ax.legend(fontsize=7, loc='center right')
    ax = fig.add_subplot(1, 3, 3, projection='3d')
    for kind, pts in after_segments:
        q = pts.copy(); q[:, 2] *= 20
        ax.plot(q[:, 0], q[:, 1], q[:, 2], color=LAYER_COLORS[kind],
            ls=':' if kind == 'transition' else '-', lw=1.5)
    ax.set(xlabel='x (mm)', ylabel='y (mm)', zlabel='z (mm)')
    ax.set_zticks([0, 20, 40], ['0', '1', '2']); ax.view_init(elev=22, azim=-60)
    ax.set_title('三维（高度放大 20 倍；真实层高 0/1/2 mm）')
    handles = [Line2D([0], [0], color=LAYER_COLORS[k], lw=2,
        label=('Layer 0' if k == 0 else f'Layer {k}' if isinstance(k, int) else '过渡段')) for k in (0, 1, 2, 'transition')]
    fig.legend(handles=handles, ncol=4, loc='lower center', frameon=False, bbox_to_anchor=(.5, -.03))
    fig.tight_layout(rect=(0, .05, 1, 1))
    for ext in ('png', 'pdf'):
        fig.savefig(FIG/f'g6_route{rid}_before_after.{ext}', dpi=300, bbox_inches='tight')
        files.append(f'g6_route{rid}_before_after.{ext}')
    plt.close(fig)
    meta = dict(route_id=rid, target_pair=list(step['target_pair']), target_layer=step['target_layer_id'],
        step_length_delta_mm=step['step_length_delta_mm'],
        route_length_before_mm=step['route_length_before_mm'], route_length_after_mm=step['route_length_after_mm'])
    (NEW/'g6_example.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    return meta


def figure_overview_3d(size=1024, tag='final_routes_C_fixed.json', folder='1024_c_fixed'):
    path = NEW/folder/tag
    if not path.is_file(): return
    routes = {row['route_id']: deserialize_route3d(row['geometry'])
        for row in jsread(path)['routes']}
    segments = [(_classify(p), _sample(p)) for _, r in sorted(routes.items()) for p in r.primitives]
    cloud = np.concatenate([p for _, p in segments])
    x0, x1 = cloud[:, 0].min(), cloud[:, 0].max(); y0, y1 = cloud[:, 1].min(), cloud[:, 1].max()
    for scale, suffix in ((1, 'true'), (20, 'z20')):
        fig = plt.figure(figsize=(10.5, 6.4)); ax = fig.add_subplot(projection='3d')
        for kind in (0, 1, 2, 'transition'):
            arrays = [q for k, pts in segments if k == kind for q in [np.column_stack([pts[:, 0], pts[:, 1], pts[:, 2]*scale])]]
            if arrays:
                from mpl_toolkits.mplot3d.art3d import Line3DCollection
                ax.add_collection3d(Line3DCollection(arrays, colors=LAYER_COLORS[kind],
                    linewidths=1.9 if kind == 'transition' else .55, alpha=.85), autolim=False)
        ax.plot([x0, x1, x1, x0, x0], [y0, y0, y1, y1, y0], [0]*5, color='#333333', lw=.7)
        ax.set(xlabel='x (mm)', ylabel='y (mm)', zlabel='z (mm)', xlim=(x0, x1), ylim=(y0, y1), zlim=(0, 2*scale))
        ax.set_zticks([0, scale, 2*scale], ['0', '1', '2']); ax.view_init(elev=24, azim=-62)
        ax.set_box_aspect((x1-x0, y1-y0, max(2*scale*.6, 8)))
        ax.set_title(f'{size} 条连接 · C 修正终态三维总览' +
            ('\n真实高度（0/1/2 mm）' if scale == 1 else '\n高度放大 20 倍显示；真实层高仍为 0/1/2 mm'))
        handles = [Line2D([0], [0], color=LAYER_COLORS[k], lw=2,
            label=('Layer 0' if k == 0 else f'Layer {k}' if isinstance(k, int) else '过渡段')) for k in (0, 1, 2, 'transition')]
        ax.legend(handles=handles, loc='upper left', fontsize=8)
        for ext in ('png', 'pdf'):
            fig.savefig(FIG/f'g7_overview3d_{suffix}.{ext}', dpi=300, bbox_inches='tight'); files.append(f'g7_overview3d_{suffix}.{ext}')
        plt.close(fig)


def main():
    figure_main_results()
    figure_pairs_vs_evaluations()
    figure_costs()
    figure_de_comparison()
    figure_relocation_rejections()
    meta = figure_route_before_after()
    figure_overview_3d()
    summary = dict(files=files, example=meta)
    (NEW/'visualization_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
