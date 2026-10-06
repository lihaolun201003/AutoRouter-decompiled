"""Step 17 figures: six v4 budget experiments, the bottleneck audit, and real 3D
layout views. Every plotted number is read from the saved artifacts under
outputs/3d_strategy_v4/512_full_layout/ (plus the frozen planar input). No figure
embeds a fixed figure number: the reports number them themselves.

True-scale 3D panels set the axes box aspect from the displayed coordinate spans;
exaggerated panels state the z magnification in the panel title.

Usage (project root):
    .venv\\Scripts\\python.exe -B scripts\\visualize_3d_strategy_v4.py PROJECT OUTDIR
"""
import sys, json, hashlib, math
from collections import Counter
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.lines import Line2D
from mpl_toolkits.mplot3d.art3d import Line3DCollection

SIMSUN_PATH = Path('C:/Windows/Fonts/simsun.ttc')
GROUPS = ['N720', 'R720', 'N1440', 'R1440', 'N2880', 'R2880']
BUDGETS = [720, 1440, 2880]
MODE_COLOR = {'N': '#0072B2', 'R': '#D55E00'}
BUDGET_STYLE = {720: '-', 1440: '--', 2880: '-.'}
LAYER_COLORS = {0: '#9aa5b1', 1: '#0072B2', 2: '#D55E00'}
Z_EXAGGERATION = 20


def parse_args(argv):
    if len(argv) != 3: raise SystemExit(__doc__)
    return Path(argv[1]).resolve(), Path(argv[2]).resolve()


ROOT, OUT = parse_args(sys.argv)
RUNS = ROOT/'outputs/3d_strategy_v4/512_full_layout'
FIGDIR = OUT
FIGDIR.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))
from src.models import Layer                      # noqa: E402
from src.geometry_3d import (lift_smoothed_route_to_layer,  # noqa: E402
    LineSegment3D, PlanarArcSegment3D, CosineTransition3D, PathWindowTransition3D)
from src.multi_attribution import deserialize_plot  # noqa: E402
from src.fixed_1024_routing import deserialize_route3d  # noqa: E402
from src.strategy_v2_3d import route_layer         # noqa: E402

MANIFEST = []


def setup_fonts():
    if not SIMSUN_PATH.exists(): raise SystemExit(f'missing font {SIMSUN_PATH}')
    fm.fontManager.addfont(str(SIMSUN_PATH))
    plt.rcParams.update({'font.family': ['SimSun'],
        'font.sans-serif': ['SimSun', 'Microsoft YaHei', 'DejaVu Sans'],
        'font.serif': ['SimSun', 'Times New Roman', 'DejaVu Serif'],
        'axes.unicode_minus': False, 'mathtext.fontset': 'stix', 'font.size': 10.5,
        'axes.titlesize': 12.0, 'axes.labelsize': 11.0, 'xtick.labelsize': 10.0,
        'ytick.labelsize': 10.0, 'legend.fontsize': 9.5, 'figure.dpi': 120,
        'savefig.dpi': 300, 'savefig.facecolor': 'white', 'figure.facecolor': 'white',
        'axes.facecolor': 'white', 'axes.edgecolor': '#333333', 'axes.linewidth': .8,
        'axes.spines.top': False, 'axes.spines.right': False, 'axes.grid': True,
        'grid.alpha': .22, 'grid.linewidth': .5, 'legend.frameon': False,
        'lines.linewidth': 1.7, 'pdf.fonttype': 42, 'ps.fonttype': 42})
    return fm.findfont(fm.FontProperties(family='SimSun'))


def jsread(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha256(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(fig, name):
    """SimSun has no U+2212: force ASCII-hyphen tick labels everywhere, then
    replace any remaining minus sign in figure text before rasterising."""
    from matplotlib.ticker import FuncFormatter
    ascii_formatter = FuncFormatter(lambda value, position: '%g' % value)
    for ax in fig.axes:
        ax.xaxis.set_major_formatter(ascii_formatter)
        ax.yaxis.set_major_formatter(ascii_formatter)
    fig.canvas.draw()
    for text in fig.findobj(matplotlib.text.Text):
        value = text.get_text()
        if '\u2212' in value: text.set_text(value.replace('\u2212', '-'))
    png = FIGDIR/f'{name}.png'; pdf = FIGDIR/f'{name}.pdf'
    fig.savefig(png, bbox_inches='tight', facecolor='white')
    fig.savefig(pdf, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    MANIFEST.append(dict(name=name, png=str(png), pdf=str(pdf),
        png_sha256=sha256(png), pdf_sha256=sha256(pdf)))
    print(f'  wrote {name}.png / {name}.pdf', flush=True)


def fmt_int(v): return f'{int(round(v)):,}'


def load_all():
    data = {}
    for name in GROUPS:
        folder = RUNS/name
        data[name] = dict(summary=jsread(folder/'summary.json'), ledger=jsread(folder/'ledger.json'),
            curve=jsread(folder/'curve.json'), decisions=jsread(folder/'decisions.json'),
            routes={row['route_id']: deserialize_route3d(row['geometry'])
                for row in jsread(folder/'final_routes.json')['routes']})
    start = None
    for candidate in [RUNS/'start_state_check.json'] + sorted(RUNS.glob('start_state_check*.json')):
        if candidate.is_file() and candidate.name == 'start_state_check.json':
            start = jsread(candidate); break
    if start is None:
        start = jsread(sorted(RUNS.glob('start_state_check*.json'))[0])
    start_routes = {row['route_id']: deserialize_route3d(row['geometry'])
        for row in jsread(ROOT/'outputs/3d_strategy_v3/512_ablation/D_both_enabled/final_routes.json')['routes']}
    plotpath = ROOT/'outputs/step_8_5_legacy_512_plot_geometry.json'
    planar = {r['id']: lift_smoothed_route_to_layer(deserialize_plot(r), Layer(0, 0))
        for r in jsread(plotpath)['routes']}
    return data, start, start_routes, planar


def route_points(route, samples=14):
    """Ordered 3D polyline points of a Route3D (arcs and cosine transitions sampled)."""
    rows = []
    for p in route.primitives:
        if isinstance(p, PlanarArcSegment3D):
            ts = np.linspace(0, 1, max(3, samples))
        elif isinstance(p, CosineTransition3D):
            ts = np.linspace(0, 1, max(3, samples))
        elif type(p) is PathWindowTransition3D:
            # never a chord: sample every planar piece of the window
            ts = np.linspace(0, 1, max(9, 4 * samples))
        else:
            ts = np.array([0., 1.])
        for t in ts:
            q = p.point_at(float(t))
            rows.append((q.x, q.y, q.z))
    return np.array(rows)


def polyline_tuples(points):
    return [(points[i], points[i + 1]) for i in range(len(points) - 1)]


def true_box_aspect(ax, points_list, magnify_z=1.0):
    allp = np.vstack(points_list)
    spans = [max(1e-6, float(np.ptp(allp[:, 0]))), max(1e-6, float(np.ptp(allp[:, 1]))),
        max(1e-6, float(np.ptp(allp[:, 2])))*magnify_z]
    ax.set_box_aspect(tuple(float(v) for v in (np.array(spans)/max(spans))))


def figure1_pairs_vs_evaluations(data, start):
    fig, (ax, axz) = plt.subplots(2, 1, figsize=(10.2, 8.4),
        gridspec_kw=dict(height_ratios=[2.3, 1.0], hspace=.42))
    start_pairs = start['recomputed_collision_pair_count']
    # The six curves coincide exactly this round; draw them thick-to-thin so the
    # overlap is visible instead of hiding five of them behind the last one.
    widths = {720: 5.2, 1440: 3.4, 2880: 1.8}
    for mode in ('R', 'N'):
        for budget in sorted(BUDGETS, reverse=True):
            name = f'{mode}{budget}'
            curve = data[name]['curve']
            x = [0] + [r['candidate_evaluations'] for r in curve[1:]]
            y = [start_pairs] + [r['collision_pair_count'] for r in curve[1:]]
            ax.step(x, y, where='post', color=MODE_COLOR[mode], linestyle=BUDGET_STYLE[budget],
                linewidth=widths[budget], alpha=.85,
                label=f'{name}（{"允许重定位" if mode == "R" else "不重定位"}）')
            ax.plot([x[-1]], [y[-1]], marker='o', ms=4.6, color=MODE_COLOR[mode],
                mec='black', mew=.6, zorder=6)
            ax.annotate(name, xy=(x[-1], y[-1]), xytext=(6, -2 if mode == 'N' else 8),
                textcoords='offset points', fontsize=8.6, color=MODE_COLOR[mode], zorder=7)
    for budget in BUDGETS:
        ax.axvline(budget, color='#999999', lw=.7, ls=':')
        ax.annotate(f'预算上限 {budget}', xy=(budget, 0), xycoords=('data', 'axes fraction'),
            xytext=(3, .02), textcoords='offset points', fontsize=8.4, color='#666666', rotation=90,
            va='bottom')
    ax.axhline(start_pairs, color='#B2182B', lw=.9, ls='--')
    ax.annotate(f'共同起点 {fmt_int(start_pairs)} 对', xy=(0, start_pairs),
        xytext=(30, -6), textcoords='offset points', fontsize=9.4, color='#B2182B', va='top')
    ax.set_xlabel('从共同终态起追加的候选基本评价次数（次）')
    ax.set_ylabel('当前中心线近距对数（对）')
    ax.set_ylim(30200, start_pairs + 260)
    ax.set_xlim(-30, max(data[n]['summary']['stats']['candidate_evaluations'] for n in GROUPS) + 210)
    ax.legend(handles=[Line2D([], [], color=MODE_COLOR['N'], lw=2.4, label='N 组（不重定位）'),
                       Line2D([], [], color=MODE_COLOR['R'], lw=2.4, label='R 组（允许重定位）'),
                       Line2D([], [], color='#555555', lw=5.2, label='预算上限 720'),
                       Line2D([], [], color='#555555', lw=3.4, ls='--', label='预算上限 1440'),
                       Line2D([], [], color='#555555', lw=1.8, ls='-.', label='预算上限 2880')],
        loc='upper right', ncol=2, fontsize=8.4)
    ax.set_title('（a）六组近距对数随追加候选评价次数的变化（同一 42,909 对起点，各自独立）', fontsize=11)
    removed = {}
    for label, mode in (('N', 'N'), ('R', 'R')):
        rows = []
        for budget in BUDGETS:
            stats = data[f'{mode}{budget}']['summary']['stats']
            rows.append((budget, start_pairs - stats['final_collision_pairs'], stats['candidate_evaluations']))
        removed[label] = rows
    width = .27
    for index, budget in enumerate(BUDGETS):
        for offset, mode in ((-.5*width, 'N'), (.5*width, 'R')):
            row = next(r for r in removed[mode] if r[0] == budget)
            axz.bar(index + offset, row[1], width=width, color=MODE_COLOR[mode],
                edgecolor='black', linewidth=.5)
            axz.annotate(f'{fmt_int(row[1])}\n（{fmt_int(row[2])} 次）',
                xy=(index + offset, row[1]), xytext=(0, 3), textcoords='offset points',
                ha='center', fontsize=8.4)
    axz.set_xticks(range(len(BUDGETS)))
    axz.set_xticklabels([f'追加预算上限 {b}' for b in BUDGETS])
    axz.set_ylabel('相对起点减少（对）')
    axz.set_ylim(0, max(r[1] for rows in removed.values() for r in rows)*1.30)
    axz.legend(handles=[Line2D([], [], color=MODE_COLOR['N'], lw=7, label='N：不重定位'),
                        Line2D([], [], color=MODE_COLOR['R'], lw=7, label='R：允许重定位')],
        loc='upper left', ncol=2)
    axz.set_title('（b）终态相对起点的减少量与实际评价次数（括号内为实际追加评价次数）', fontsize=11)
    fig.text(.01, -.015, '数据来源：outputs/3d_strategy_v4/512_full_layout/<组>/curve.json、summary.json；'
        '起点为 outputs/3d_strategy_v3/512_ablation/D_both_enabled/ 的 42,909 对终态。'
        '六组各自独立从同一起点开始，预算为“追加”预算，不含形成起点的历史 720 次评价。'
        '本轮六组曲线完全重合（N 与 R 的终态逐位相同），因此 (a) 中只看到一条最上层曲线；'
        '用粗细与线型区分，并在端点用标记与组名标出各组终点。',
        fontsize=8.6, color='#555555', va='top')
    save(fig, 'f1_pairs_vs_appended_evaluations')


def figure2_nr_comparison(data, start):
    start_pairs = start['recomputed_collision_pair_count']
    fig, axes = plt.subplots(1, 3, figsize=(13.2, 4.5))
    width = .32
    for index, budget in enumerate(BUDGETS):
        for offset, mode in ((-.5*width, 'N'), (.5*width, 'R')):
            stats = data[f'{mode}{budget}']['summary']['stats']
            axes[0].bar(index + offset, stats['final_collision_pairs'], width=width,
                color=MODE_COLOR[mode], edgecolor='black', linewidth=.5)
            axes[0].annotate(fmt_int(stats['final_collision_pairs']), xy=(index + offset,
                stats['final_collision_pairs']), xytext=(0, 3), textcoords='offset points',
                ha='center', fontsize=8.2, rotation=90)
            axes[1].bar(index + offset, start_pairs - stats['final_collision_pairs'], width=width,
                color=MODE_COLOR[mode], edgecolor='black', linewidth=.5)
            axes[1].annotate(fmt_int(start_pairs - stats['final_collision_pairs']),
                xy=(index + offset, start_pairs - stats['final_collision_pairs']),
                xytext=(0, 3), textcoords='offset points', ha='center', fontsize=8.2)
            axes[2].bar(index + offset, stats['candidate_evaluations'], width=width,
                color=MODE_COLOR[mode], edgecolor='black', linewidth=.5)
            axes[2].annotate(fmt_int(stats['candidate_evaluations']), xy=(index + offset,
                stats['candidate_evaluations']), xytext=(0, 3), textcoords='offset points',
                ha='center', fontsize=8.2)
    axes[0].set_ylim(39500, start_pairs + 200)
    axes[0].set_title('（a）终态近距对数', fontsize=11)
    axes[1].set_title('（b）相对起点减少对数', fontsize=11)
    axes[2].set_title('（c）实际追加候选评价次数', fontsize=11)
    for ax in axes:
        ax.set_xticks(range(len(BUDGETS)))
        ax.set_xticklabels([f'{b}' for b in BUDGETS])
        ax.set_xlabel('追加预算上限（次）')
    bars = [Line2D([], [], color=MODE_COLOR['N'], lw=7, label='N：不重定位'),
            Line2D([], [], color=MODE_COLOR['R'], lw=7, label='R：允许重定位')]
    axes[0].legend(handles=bars, loc='upper right')
    fig.suptitle('同一预算上限下 N 组与 R 组终态对照（只在同预算内比较；不同预算只表示趋势）', fontsize=12)
    pairs = []
    for budget in BUDGETS:
        n = data[f'N{budget}']['summary']['stats']; r = data[f'R{budget}']['summary']['stats']
        pairs.append(f'{budget}: N {fmt_int(n["final_collision_pairs"])} / R {fmt_int(r["final_collision_pairs"])}'
            f'，N/R 实际评价 {fmt_int(n["candidate_evaluations"])} / {fmt_int(r["candidate_evaluations"])} 次'
            f'（{"相同" if n["candidate_evaluations"] == r["candidate_evaluations"] else "不同"}）')
    fig.text(.01, -.05, '数据来源：outputs/3d_strategy_v4/512_full_layout/<组>/summary.json。\n'
        + '\n'.join(pairs), fontsize=8.6, color='#555555', va='top')
    save(fig, 'f2_same_budget_N_vs_R')


def figure3_actions_and_gains(data, start):
    start_pairs = start['recomputed_collision_pair_count']
    fig, axes = plt.subplots(1, 3, figsize=(13.2, 4.4))
    xs = np.arange(len(GROUPS)); width = .38
    first_counts = [data[n]['summary']['stats']['first_elevations'] for n in GROUPS]
    reloc_counts = [data[n]['summary']['stats']['relocations'] for n in GROUPS]
    axes[0].bar(xs - width/2, first_counts, width, label='首次抬升次数', color='#0072B2',
        edgecolor='black', linewidth=.5)
    axes[0].bar(xs + width/2, reloc_counts, width, label='重定位次数', color='#D55E00',
        edgecolor='black', linewidth=.5)
    for x, v in zip(xs - width/2, first_counts):
        axes[0].annotate(str(v), xy=(x, v), xytext=(0, 3), textcoords='offset points', ha='center', fontsize=8.6)
    for x, v in zip(xs + width/2, reloc_counts):
        axes[0].annotate(str(v), xy=(x, v), xytext=(0, 3), textcoords='offset points', ha='center', fontsize=8.6)
    axes[0].set_ylabel('动作次数'); axes[0].legend(loc='upper left')
    axes[0].set_title('（a）实际执行动作数（候选通过≠动作执行）', fontsize=11)
    first_gain = [data[n]['ledger']['first_elevation_net_reduction'] for n in GROUPS]
    reloc_gain = [data[n]['ledger']['relocation_net_reduction'] for n in GROUPS]
    axes[1].bar(xs - width/2, first_gain, width, label='首次抬升净减少', color='#0072B2',
        edgecolor='black', linewidth=.5)
    axes[1].bar(xs + width/2, reloc_gain, width, label='重定位净减少', color='#D55E00',
        edgecolor='black', linewidth=.5)
    for x, v in list(zip(xs - width/2, first_gain)) + list(zip(xs + width/2, reloc_gain)):
        axes[1].annotate(fmt_int(v), xy=(x, v), xytext=(0, 3), textcoords='offset points',
            ha='center', fontsize=8.2, rotation=90)
    axes[1].set_ylabel('净减少对数（合计）'); axes[1].legend(loc='upper left')
    axes[1].set_title('（b）首次抬升与重定位各自的净收益', fontsize=11)
    removed = [data[n]['ledger']['total_old_collisions_removed'] for n in GROUPS]
    created = [data[n]['ledger']['total_new_collisions_created'] for n in GROUPS]
    axes[2].bar(xs - width/2, removed, width, label='移除的旧近距对', color='#009E73',
        edgecolor='black', linewidth=.5)
    axes[2].bar(xs + width/2, created, width, label='新增近距对', color='#B2182B',
        edgecolor='black', linewidth=.5)
    for x, v in list(zip(xs - width/2, removed)) + list(zip(xs + width/2, created)):
        axes[2].annotate(fmt_int(v), xy=(x, v), xytext=(0, 3), textcoords='offset points',
            ha='center', fontsize=8.2, rotation=90)
    axes[2].set_ylabel('对数（合计）'); axes[2].legend(loc='upper left')
    axes[2].set_title('（c）移除收益与新增抵消', fontsize=11)
    for ax in axes:
        ax.set_xticks(xs); ax.set_xticklabels(GROUPS, fontsize=9)
    fig.suptitle('六组的动作构成与收益拆分（共同起点 %s 对）' % fmt_int(start_pairs), fontsize=12)
    fig.text(.01, -.045, '数据来源：outputs/3d_strategy_v4/512_full_layout/<组>/ledger.json。'
        '净减少=移除−新增；某组重定位次数为 0 时其重定位净减少恒为 0，属于真实结果而非缺失。',
        fontsize=8.6, color='#555555', va='top')
    save(fig, 'f3_actions_and_gains')


def figure4_costs(data):
    fig, axes = plt.subplots(1, 3, figsize=(13.2, 4.4))
    xs = np.arange(len(GROUPS)); width = .38
    stage = [data[n]['ledger']['stage_length_delta_mm'] for n in GROUPS]
    extra = [data[n]['ledger']['final_extra_length_vs_planar_mm'] for n in GROUPS]
    axes[0].bar(xs - width/2, stage, width, label='阶段变化（终态−共同起点）', color='#0072B2',
        edgecolor='black', linewidth=.5)
    axes[0].bar(xs + width/2, extra, width, label='终态额外长度（终态−原始平面）', color='#E69F00',
        edgecolor='black', linewidth=.5)
    for x, v in list(zip(xs - width/2, stage)) + list(zip(xs + width/2, extra)):
        axes[0].annotate(f'{v:.3f}', xy=(x, v), xytext=(0, 3), textcoords='offset points',
            ha='center', va='bottom', fontsize=8.2, rotation=90)
    axes[0].set_ylim(0, max(stage + extra)*1.28)
    axes[0].set_ylabel('长度（mm）'); axes[0].legend(loc='upper left')
    axes[0].set_title('（a）两种长度口径分开绘制', fontsize=11)
    full = [data[n]['ledger']['full_neighbor_checks'] for n in GROUPS]
    passes = [data[n]['ledger']['full_acceptance_passes'] for n in GROUPS]
    axes[1].bar(xs - width/2, full, width, label='完整邻线验收次数', color='#0072B2',
        edgecolor='black', linewidth=.5)
    axes[1].bar(xs + width/2, passes, width, label='完整验收通过候选数', color='#009E73',
        edgecolor='black', linewidth=.5)
    for x, v in list(zip(xs - width/2, full)) + list(zip(xs + width/2, passes)):
        axes[1].annotate(fmt_int(v), xy=(x, v), xytext=(0, 3), textcoords='offset points',
            ha='center', va='bottom', fontsize=8.2, rotation=90)
    axes[1].set_ylim(0, max(full + passes)*1.34)
    axes[1].set_ylabel('次数 / 候选数'); axes[1].legend(loc='upper left')
    axes[1].set_title('（b）完整验收量与通过量', fontsize=11)
    seconds = [data[n]['summary']['stats']['timings']['runtime_seconds'] for n in GROUPS]
    axes[2].bar(xs, seconds, .55, color='#5B1387', edgecolor='black', linewidth=.5)
    for x, v in zip(xs, seconds):
        axes[2].annotate(f'{v:.0f}', xy=(x, v), xytext=(0, 3), textcoords='offset points',
            ha='center', fontsize=8.6)
    axes[2].set_ylabel('单次运行时间（s）')
    axes[2].set_title('（c）单次运行时间（不支持普遍效率结论）', fontsize=11)
    for ax in axes:
        ax.set_xticks(xs); ax.set_xticklabels(GROUPS, fontsize=9)
    fig.suptitle('额外长度、完整验收量与单次运行时间', fontsize=12)
    fig.text(.01, -.045, '数据来源：outputs/3d_strategy_v4/512_full_layout/<组>/ledger.json 与 summary.json。'
        '单次运行时间为本机单进程墙钟时间，六组并行运行，未做重复计时，不能据此给出效率结论。',
        fontsize=8.6, color='#555555', va='top')
    save(fig, 'f4_costs_and_checks')


def figure5_residual_distribution(data, start):
    labels = ['双方均未抬升', '单方已抬升', '双方均已抬升']
    keys = ['both_routes_unelevated', 'single_route_elevated', 'both_routes_elevated']
    colors = ['#9aa5b1', '#0072B2', '#D55E00']
    columns = ['共同起点'] + GROUPS
    values = [[start['pair_state_distribution'][k] for k in keys]] + \
        [[data[n]['summary']['stats']['final_pair_state_distribution'][k] for k in keys] for n in GROUPS]
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(13.6, 4.8), gridspec_kw=dict(width_ratios=[1.45, 1]))
    bottom = np.zeros(len(columns))
    for index, (label, color) in enumerate(zip(labels, colors)):
        heights = np.array([v[index] for v in values], dtype=float)
        ax.bar(range(len(columns)), heights, .6, bottom=bottom, label=label, color=color,
            edgecolor='black', linewidth=.4)
        for x, (h, b) in enumerate(zip(heights, bottom)):
            if h > 0:
                ax.annotate(fmt_int(h), xy=(x, b + h/2), ha='center', va='center', fontsize=8.0,
                    color='white' if index else '#222222')
        bottom += heights
    ax.set_xticks(range(len(columns))); ax.set_xticklabels(columns, fontsize=9)
    ax.set_ylabel('中心线近距对数')
    ax.legend(loc='upper right')
    ax.set_title('（a）剩余近距对的三种路线状态分布（含共同起点）', fontsize=11)
    changes = [[data[n]['summary']['stats']['final_pair_state_distribution'][k]
        - start['pair_state_distribution'][k] for k in keys] for n in GROUPS]
    width = .26
    for index, (label, color) in enumerate(zip(labels, colors)):
        ax2.bar(np.arange(len(GROUPS)) + (index - 1)*width, [c[index] for c in changes], width,
            label=label, color=color, edgecolor='black', linewidth=.4)
    ax2.axhline(0, color='#333333', lw=.8)
    ax2.set_xticks(range(len(GROUPS))); ax2.set_xticklabels(GROUPS, fontsize=9)
    ax2.set_ylabel('相对起点的变化（对）')
    ax2.legend(loc='lower left'); ax2.set_title('（b）状态分布相对起点的变化', fontsize=11)
    fig.suptitle('剩余近距对的路线状态分布如何变化', fontsize=12)
    fig.text(.01, -.05, '数据来源：outputs/3d_strategy_v4/512_full_layout/start_state_check.json 与 <组>/summary.json。'
        '三方合计等于该组终态近距对数；未决对不计入三类，单独在报告中列出。', fontsize=8.6,
        color='#555555', va='top')
    save(fig, 'f5_residual_state_distribution')


def figure6_failure_reasons(data):
    fig, axes = plt.subplots(1, 3, figsize=(14.0, 4.8))
    panels = [('generation_failure_reason_counts', '（a）生成端：零候选原因'),
        ('basic_rejection_reason_counts', '（b）基本验收拒绝原因'),
        ('full_rejection_reason_counts', '（c）完整邻线验收拒绝原因')]
    for ax, (key, title) in zip(axes, panels):
        names = sorted({reason for n in GROUPS for reason in
            data[n]['summary']['stats'][key]})
        names = sorted(names, key=lambda r: -sum(data[n]['summary']['stats'][key].get(r, 0)
            for n in GROUPS))
        names = names[:7]
        width = .13
        for index, name in enumerate(names):
            values = [data[g]['summary']['stats'][key].get(name, 0) for g in GROUPS]
            ax.bar(np.arange(len(GROUPS)) + (index - (len(names) - 1)/2)*width, values, width,
                label=name, edgecolor='black', linewidth=.3)
        ax.set_xticks(range(len(GROUPS))); ax.set_xticklabels(GROUPS, fontsize=8.5)
        ax.set_title(title, fontsize=10.5)
        ax.set_ylabel('出现次数')
        handles, labels = ax.get_legend_handles_labels()
        if handles: ax.legend(handles, labels, fontsize=7.6, loc='upper right')
        if not names:
            ax.annotate('该组无此类失败记录', xy=(.5, .5), xycoords='axes fraction',
                ha='center', va='center', fontsize=10, color='#666666')
    fig.suptitle('生成失败与验收失败原因（出现次数；同一候选可有多个理由，次数不可相加成候选数）', fontsize=11.5)
    fig.text(.01, -.05, '数据来源：outputs/3d_strategy_v4/512_full_layout/<组>/ledger.json 的 '
        'generation_failure_reason_counts、basic_rejection_reason_counts、full_rejection_reason_counts。'
        '生成端零候选说明“当前生成规则下无合法窗口”，不代表几何上必然无解。', fontsize=8.6,
        color='#555555', va='top')
    save(fig, 'f6_failure_reasons')


def representative_move(data):
    """Largest-net-reduction accepted relocation if any, else the largest first
    elevation, with its group."""
    best = None
    for name in GROUPS:
        step_index = 0
        for step in data[name]['decisions']:
            step_index += 1
            if step['status'] not in ('ELEVATED', 'RELOCATED'): continue
            key = (step['net_collision_reduction'], step['step_length_delta_mm'])
            if best is None or key > best[0]:
                best = (key, name, step)
    return best[1], best[2]


def draw_route_3d(ax, route, color, label=None, z_scale=1.0, lw=2.0, zorder=3):
    points = route_points(route)
    scaled = points.copy(); scaled[:, 2] *= z_scale
    segments = polyline_tuples(scaled)
    ax.add_collection3d(Line3DCollection(segments, colors=color, linewidths=lw, zorder=zorder))
    if label is not None:
        ax.plot([], [], [], color=color, lw=lw, label=label)
    return scaled


def figure7_representative_case(data, start_routes, planar):
    name, step = representative_move(data)
    moved = step['moved_route_id']
    before = start_routes[moved]
    after = data[name]['routes'][moved]
    other_route = None
    for index in step['target_pair']:
        if index != moved: other_route = index
    target_points = [before, after, start_routes[other_route]]
    if planar[other_route] is not before: target_points.append(planar[other_route])
    fig = plt.figure(figsize=(13.6, 11.6))
    grid = fig.add_gridspec(2, 2, hspace=.30, wspace=.16,
        left=.06, right=.97, top=.93, bottom=.05)
    ax_xy = fig.add_subplot(grid[0, 0])
    for route, color, label, lw, ls in [(planar[moved], '#999999', '冻结平面基准（层 0）', 1.3, '--'),
                                        (before, '#0072B2', '修改前（当前）', 1.9, '-'),
                                        (after, '#D55E00', '修改后（接受）', 1.9, '-')]:
        pts = route_points(route)
        ax_xy.plot(pts[:, 0], pts[:, 1], color=color, lw=lw, ls=ls, label=label)
    pts = route_points(start_routes[other_route])
    ax_xy.plot(pts[:, 0], pts[:, 1], color='#009E73', lw=1.5, label=f'目标对侧路线 {other_route}')
    ax_xy.set_aspect('equal'); ax_xy.legend(fontsize=8.6, loc='best')
    ax_xy.set_xlabel('x（mm）'); ax_xy.set_ylabel('y（mm）')
    ax_xy.set_title('（a）XY 投影（等比例）', fontsize=11)
    ax_xz = fig.add_subplot(grid[0, 1])
    for route, color, label, lw, ls in [(planar[moved], '#999999', '冻结平面基准（层 0）', 1.3, '--'),
                                        (before, '#0072B2', '修改前（当前）', 1.9, '-'),
                                        (after, '#D55E00', '修改后（接受）', 1.9, '-')]:
        pts = route_points(route)
        ax_xz.plot(pts[:, 0], pts[:, 2], color=color, lw=lw, ls=ls, label=label)
    pts = route_points(start_routes[other_route])
    ax_xz.plot(pts[:, 0], pts[:, 2], color='#009E73', lw=1.5, label=f'目标对侧路线 {other_route}')
    ax_xz.set_xlabel('x（mm）'); ax_xz.set_ylabel('z（mm）')
    ax_xz.set_yticks([0, 1, 2]); ax_xz.legend(fontsize=8.6, loc='best')
    ax_xz.set_title('（b）XZ 侧视（z 未放大）', fontsize=11)
    ax_true = fig.add_subplot(grid[1, 0], projection='3d')
    pts_list = [route_points(r) for r in (planar[moved], before, after, start_routes[other_route])]
    draw_route_3d(ax_true, planar[moved], '#999999', '冻结平面基准', 1.0, 1.2)
    draw_route_3d(ax_true, before, '#0072B2', '修改前（当前）', 1.0, 2.0)
    draw_route_3d(ax_true, after, '#D55E00', '修改后（接受）', 1.0, 2.0)
    draw_route_3d(ax_true, start_routes[other_route], '#009E73', f'目标对侧路线 {other_route}', 1.0, 1.6)
    lo = np.vstack(pts_list).min(axis=0); hi = np.vstack(pts_list).max(axis=0)
    ax_true.set_xlim(lo[0], hi[0]); ax_true.set_ylim(lo[1], hi[1]); ax_true.set_zlim(-.1, hi[2] + .1)
    true_box_aspect(ax_true, pts_list, 1.0)
    ax_true.set_xlabel('x（mm）', labelpad=-2); ax_true.set_ylabel('y（mm）', labelpad=-2)
    ax_true.set_zlabel('z（mm）', labelpad=-4)
    ax_true.set_title('（c）三维视图：真实比例（z 与 x/y 同尺度，箱体比例按显示跨度设置）', fontsize=10)
    ax_true.legend(fontsize=7.6, loc='upper left')
    ax_zoom = fig.add_subplot(grid[1, 1], projection='3d')
    draw_route_3d(ax_zoom, planar[moved], '#999999', '冻结平面基准', Z_EXAGGERATION, 1.2)
    draw_route_3d(ax_zoom, before, '#0072B2', '修改前（当前）', Z_EXAGGERATION, 2.0)
    draw_route_3d(ax_zoom, after, '#D55E00', '修改后（接受）', Z_EXAGGERATION, 2.0)
    draw_route_3d(ax_zoom, start_routes[other_route], '#009E73', f'目标对侧路线 {other_route}',
        Z_EXAGGERATION, 1.6)
    zoomed = [np.column_stack([p[:, 0], p[:, 1], p[:, 2]*Z_EXAGGERATION]) for p in pts_list]
    loz = np.vstack(zoomed).min(axis=0); hiz = np.vstack(zoomed).max(axis=0)
    ax_zoom.set_xlim(loz[0], hiz[0]); ax_zoom.set_ylim(loz[1], hiz[1]); ax_zoom.set_zlim(0, max(2.3, hiz[2]))
    true_box_aspect(ax_zoom, zoomed, 1.0)
    ax_zoom.set_xlabel('x（mm）', labelpad=-2); ax_zoom.set_ylabel('y（mm）', labelpad=-2)
    ax_zoom.set_zlabel('z（mm）', labelpad=-4)
    ax_zoom.set_zticks([0, 1*Z_EXAGGERATION, 2*Z_EXAGGERATION])
    ax_zoom.set_zticklabels(['0', '1', '2'])
    ax_zoom.set_title(f'（d）三维视图：z 轴放大 {Z_EXAGGERATION} 倍（真实层高 0/1/2 mm，'
        f'刻度按真实 mm 标注）', fontsize=10)
    ax_zoom.legend(fontsize=7.6, loc='upper left')
    fig.suptitle(f'{name} 组中净减少最大的真实接受动作：路线 {moved}（{step["movement"]}），'
        f'目标对 ({step["target_pair"][0]}, {step["target_pair"][1]})，'
        f'净减少 {step["net_collision_reduction"]} 对，单步长度变化 {step["step_length_delta_mm"]:.4f} mm',
        fontsize=11.5)
    fig.text(.01, -.02, '数据来源：outputs/3d_strategy_v4/512_full_layout/%s/decisions.json 与 final_routes.json；'
        '修改前取共同起点 outputs/3d_strategy_v3/512_ablation/D_both_enabled/final_routes.json。'
        '（c）的箱体比例由显示坐标跨度直接设定，未做任何缩放；（d）的 z 轴放大倍数标注在子图标题内，'
        'z 刻度仍按真实 mm 标注。' % name, fontsize=8.6, color='#555555', va='top')
    save(fig, f'f7_representative_accepted_move_{name}_route{moved}')
    return name, step


def figure8_layout_3d(data, planar, group='R2880'):
    """Whole-layout 3D overview: true scale and z-exaggerated."""
    routes = data[group]['routes']
    fig = plt.figure(figsize=(13.0, 6.4))
    all_points = [route_points(r) for r in routes.values()]
    for panel, (column, magnify) in enumerate([(1, 1.0), (2, Z_EXAGGERATION)]):
        ax = fig.add_subplot(1, 2, column, projection='3d')
        scaled_all = []
        by_layer = {0: [], 1: [], 2: []}
        for index, route in routes.items():
            points = route_points(route)
            scaled = points.copy(); scaled[:, 2] *= magnify
            scaled_all.append(scaled)
            by_layer[route_layer(route)].append(scaled)
        for layer, chunks in by_layer.items():
            segments = [seg for chunk in chunks for seg in polyline_tuples(chunk)]
            if segments:
                ax.add_collection3d(Line3DCollection(segments, colors=LAYER_COLORS[layer],
                    linewidths=.5 if layer == 0 else 1.1,
                    alpha=.42 if layer == 0 else .95,
                    zorder=1 if layer == 0 else (3 if layer == 1 else 4)))
        stacked = np.vstack(scaled_all)
        lo, hi = stacked.min(axis=0), stacked.max(axis=0)
        ax.set_xlim(lo[0], hi[0]); ax.set_ylim(lo[1], hi[1])
        ax.set_zlim(0, max(hi[2], 2.3))
        true_box_aspect(ax, [stacked], 1.0)
        ax.set_xlabel('x（mm）', labelpad=-1); ax.set_ylabel('y（mm）', labelpad=-1)
        ax.set_zlabel('z（mm）', labelpad=-3)
        if magnify == 1.0:
            ax.set_zticks([0, 1, 2]); ax.set_title('（a）真实比例三维布局（z 与 x/y 同尺度）', fontsize=11)
        else:
            ax.set_zticks([0, 1*Z_EXAGGERATION, 2*Z_EXAGGERATION])
            ax.set_zticklabels(['0', '1', '2'])
            ax.set_title(f'（b）同一布局，z 轴放大 {Z_EXAGGERATION} 倍（z 刻度按真实 mm 标注）', fontsize=11)
        handles = [Line2D([], [], color='#9aa5b1', lw=2, label='层 0 路线'),
                   Line2D([], [], color=LAYER_COLORS[1], lw=2, label='层 1（z = 1 mm）'),
                   Line2D([], [], color=LAYER_COLORS[2], lw=2, label='层 2（z = 2 mm）')]
        ax.legend(handles=handles, fontsize=8.0, loc='upper left')
    layer_counts = Counter(route_layer(r) for r in routes.values())
    fig.suptitle(f'{group} 组终态 512 条路线三维布局（层 0：{layer_counts[0]} 条，'
        f'层 1：{layer_counts[1]} 条，层 2：{layer_counts[2]} 条；过渡段共 '
        f'{data[group]["summary"]["stats"]["final_transition_count"]} 段）', fontsize=11.5)
    fig.text(.01, -.02, '数据来源：outputs/3d_strategy_v4/512_full_layout/%s/final_routes.json。'
        '（a）按显示坐标跨度设置箱体比例、z 与 x/y 同尺度；（b）仅用于看清 1/2 mm 抬升，'
        '放大倍数标注在子图标题内，z 刻度仍按真实 mm 标注。' % group, fontsize=8.6,
        color='#555555', va='top')
    save(fig, f'f8_layout3d_{group}')


def figure9_audit(audit_dir):
    summary = jsread(audit_dir/'classification_summary.json')
    side = jsread(audit_dir/'side_audit.json')['records']
    recount = jsread(audit_dir/'recount.json')
    outcomes = summary['outcome_counts']
    order = ['NO_LEGAL_WINDOW_UNDER_CURRENT_RULES', 'CANDIDATES_EXIST_BASIC_ALL_REJECTED',
             'BASIC_PASSES_FULL_NO_NET_GAIN', 'BASIC_PASSES_FULL_CHECK_CAPPED',
             'FULL_ACCEPTED_CANDIDATE_EXISTS']
    short = {'NO_LEGAL_WINDOW_UNDER_CURRENT_RULES': '当前规则无合法窗口',
             'CANDIDATES_EXIST_BASIC_ALL_REJECTED': '候选存在但基本验收全失败',
             'BASIC_PASSES_FULL_NO_NET_GAIN': '基本通过但完整验收无净收益',
             'BASIC_PASSES_FULL_CHECK_CAPPED': '完整验收受上限截断',
             'FULL_ACCEPTED_CANDIDATE_EXISTS': '存在可完整通过候选'}
    fig, axes = plt.subplots(1, 3, figsize=(14.0, 4.6))
    counts = [outcomes.get(k, 0) for k in order]
    axes[0].barh(range(len(order)), counts, .6, color=['#B2182B', '#E69F00', '#5B1387', '#999999',
        '#009E73'], edgecolor='black', linewidth=.4)
    for y, v in enumerate(counts):
        axes[0].annotate(str(v), xy=(v, y), xytext=(3, 0), textcoords='offset points',
            va='center', fontsize=9)
    axes[0].set_yticks(range(len(order))); axes[0].set_yticklabels([short[k] for k in order], fontsize=9)
    axes[0].invert_yaxis(); axes[0].set_xlabel('目标侧数（共 %d 侧）' % len(side))
    axes[0].set_title('（a）审计目标侧的瓶颈归因', fontsize=11)
    cross = summary['previous_budget_cross_tab']
    labels = ['PREVIOUS_BUDGET_NOT_COVERED', 'PREVIOUS_BUDGET_COVERED']
    bottom = np.zeros(len(labels)); colors = ['#B2182B', '#E69F00', '#5B1387', '#999999', '#009E73']
    for index, key in enumerate(order):
        heights = np.array([cross.get(row, {}).get(key, 0) for row in labels], dtype=float)
        axes[1].bar(range(len(labels)), heights, .5, bottom=bottom, label=short[key],
            color=colors[index], edgecolor='black', linewidth=.4)
        bottom += heights
    axes[1].set_xticks(range(len(labels)))
    axes[1].set_xticklabels(['此前 720 次预算未覆盖', '此前预算已覆盖'], fontsize=9)
    axes[1].set_ylabel('目标侧数'); axes[1].legend(fontsize=8.0, loc='upper right')
    axes[1].set_title('（b）此前预算覆盖 × 瓶颈归因', fontsize=11)
    categories = list(summary['by_category'].keys())
    names = {'high_conflict_both_unelevated': '高冲突双方未抬升', 'random_both_unelevated': '随机抽样双方未抬升',
             'single_elevated': '单方已抬升', 'both_elevated': '双方已抬升'}
    width = .38
    xs = np.arange(len(categories))
    no_window = [summary['by_category'][c]['no_legal_window_sides'] for c in categories]
    total = [summary['by_category'][c]['sides'] for c in categories]
    axes[2].bar(xs - width/2, total, width, label='该类目标侧数', color='#4D4D4D',
        edgecolor='black', linewidth=.4)
    axes[2].bar(xs + width/2, no_window, width, label='其中当前规则无合法窗口', color='#B2182B',
        edgecolor='black', linewidth=.4)
    for x, v in list(zip(xs - width/2, total)) + list(zip(xs + width/2, no_window)):
        axes[2].annotate(str(v), xy=(x, v), xytext=(0, 3), textcoords='offset points',
            ha='center', fontsize=8.6)
    axes[2].set_xticks(xs); axes[2].set_xticklabels([names[c] for c in categories], fontsize=8.6)
    axes[2].set_ylim(0, max(total)*1.42)
    axes[2].legend(fontsize=8.4, loc='upper center', ncol=2); axes[2].set_ylabel('目标侧数')
    axes[2].set_title('（c）四类固定清单中的无窗口比例', fontsize=11)
    fig.suptitle('残余近距对瓶颈审计（固定清单：%d 对目标 / %d 个目标侧，覆盖 %d 条路线，单条路线最多 %d 对）'
        % (summary['target_count'], len(side), summary['route_diversity']['routes_used'],
           summary['route_diversity']['max_per_route']), fontsize=11.5)
    fig.text(.01, -.06, '数据来源：outputs/3d_strategy_v4/512_full_layout/audit/classification_summary.json、'
        'side_audit.json、recount.json。重算复核：%d 对，近距集合与保存一致=%s，未决 %d 对，已抬升路线 %d 条。'
        '审计候选评价单独记账（基本 %d 次、完整验收 %d 次），不并入任何一组优化预算；'
        '“无合法窗口”仅指当前生成规则，不代表几何上必然无解。'
        % (recount['recomputed_collision_pairs'], recount['collision_set_matches_saved'],
           recount['recomputed_unresolved_pairs'], recount['elevated_route_count'],
           summary['audit_ledger']['basic_evaluations'], summary['audit_ledger']['full_neighbor_checks']),
        fontsize=8.4, color='#555555', va='top')
    save(fig, 'f9_bottleneck_audit')


def main():
    resolved = setup_fonts()
    print(f'font: {resolved}', flush=True)
    data, start, start_routes, planar = load_all()
    audit_dir = RUNS/'audit'
    figure1_pairs_vs_evaluations(data, start)
    figure2_nr_comparison(data, start)
    figure3_actions_and_gains(data, start)
    figure4_costs(data)
    figure5_residual_distribution(data, start)
    figure6_failure_reasons(data)
    name, step = figure7_representative_case(data, start_routes, planar)
    figure8_layout_3d(data, planar, group='R2880' if 'R2880' in data else GROUPS[-1])
    if (audit_dir/'classification_summary.json').is_file():
        figure9_audit(audit_dir)
    else:
        print('  audit summary missing, f9 skipped', flush=True)
    (FIGDIR/'figures_v4_manifest.json').write_text(json.dumps(dict(
        font=resolved, generator=__file__, images=MANIFEST,
        inputs={'start_state_check': str(RUNS/'start_state_check.json'),
            'groups': {n: str(RUNS/n/'summary.json') for n in GROUPS},
            'audit': str(audit_dir/'classification_summary.json')},
        representative_move=dict(group=name, step_index=step['step_index'],
            moved_route_id=step['moved_route_id'], movement=step['movement'],
            net_collision_reduction=step['net_collision_reduction']),
        no_figure_numbers_embedded=True), indent=2, ensure_ascii=False), encoding='utf-8')
    print('FIGURES DONE')


if __name__ == '__main__':
    main()
