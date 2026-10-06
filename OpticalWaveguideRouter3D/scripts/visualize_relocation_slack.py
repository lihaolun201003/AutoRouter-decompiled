"""Step 16 figures for the slack relocation diagnostic (report figures 4, 5, 7).

Read-only on every experiment artifact; writes PNG (300 dpi) and PDF into the
given output directory and a manifest with input hashes.

    figure 4  f4_diagnostic_comparison      old vs new D/E terminal pairs, evaluations, length, runtime
    figure 5  f5_relocation_rejections      relocation-candidate funnel and rejection reasons
    figure 7  f7_route34_relocation         route 34 before/after the accepted relocation
                                            (XY, XZ, true-scale 3D, Z x20 magnified 3D)

Usage (project root):
    .venv\Scripts\python.exe -B scripts\visualize_relocation_slack.py PROJECT OUTDIR
"""
import sys, json, hashlib
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib import font_manager, rcParams
import matplotlib.pyplot as plt

PROJECT = Path(sys.argv[1]).resolve(); OUT = Path(sys.argv[2]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(PROJECT))

from src.fixed_1024_routing import deserialize_route3d

font_manager.fontManager.addfont('C:/Windows/Fonts/simsun.ttc')
rcParams['font.family'] = ['SimSun']
rcParams['axes.unicode_minus'] = False
rcParams['figure.dpi'] = 300
rcParams['savefig.bbox'] = 'tight'

OLD = PROJECT/'outputs/3d_strategy_v2_rev2/512_de_diagnostic'
NEW = PROJECT/'outputs/3d_strategy_v3/512_relocation_slack_diagnostic'
FIGDIR = OUT
INPUTS = []


def read(path):
    path = Path(path)
    INPUTS.append(dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    return json.loads(path.read_text(encoding='utf-8'))


def save(fig, name):
    png = FIGDIR/f'{name}.png'; pdf = FIGDIR/f'{name}.pdf'
    fig.savefig(png); fig.savefig(pdf); plt.close(fig)
    print('wrote', png)


def samples(route):
    xs = []; ys = []; zs = []; s = []; acc = 0.
    for p in route.primitives:
        n = 24 if type(p).__name__ == 'LineSegment3D' else 60
        ts = np.linspace(0., 1., n)
        pts = [p.point_at(float(t)) for t in ts]
        for i, q in enumerate(pts):
            if xs:
                acc += float(np.hypot(q.x-xs[-1], q.y-ys[-1]))
            xs.append(q.x); ys.append(q.y); zs.append(q.z); s.append(acc)
    return np.array(xs), np.array(ys), np.array(zs), np.array(s)


LEDGER_OLD = {m: read(OLD/f'ledger_{m}.json') for m in ('D', 'E')}
LEDGER_NEW = {m: read(NEW/f'ledger_{m}.json') for m in ('D', 'E')}
ANALYSIS = read(NEW/'analysis.json')
BEFORE_AFTER = ANALYSIS['accepted_relocation_before_after']
INITIAL_PAIRS = LEDGER_NEW['D']['initial_collision_pair_count']

# ---------------------------------------------------------------- figure 4
labels = ['旧诊断 D\n(余量=0)', '新诊断 D\n(余量=1e-5)', '旧诊断 E\n(余量=0)', '新诊断 E\n(余量=1e-5)']
ledgers = [LEDGER_OLD['D'], LEDGER_NEW['D'], LEDGER_OLD['E'], LEDGER_NEW['E']]
colors = ['#9aa4b0', '#3b6ea5', '#c9a227', '#c0392b']
fig, axes = plt.subplots(2, 2, figsize=(11.6, 8.2), layout='constrained')
ax = axes[0][0]
vals = [l['final_collision_pair_count'] for l in ledgers]
bars = ax.bar(labels, vals, color=colors, width=.6)
ax.axhline(INITIAL_PAIRS, color='#444444', ls='--', lw=1.2)
ax.text(-0.42, INITIAL_PAIRS+30, f'共同起点 {INITIAL_PAIRS:,} 对', ha='left', va='bottom', fontsize=9, color='#444444')
ax.set_ylim(min(vals)-350, INITIAL_PAIRS+450)
ax.set_ylabel('终态中心线近距对数（0.1 mm）')
ax.set_title(f'(a) 终态近距对（新 E 比新 D 少 '
             f'{LEDGER_NEW["D"]["final_collision_pair_count"]-LEDGER_NEW["E"]["final_collision_pair_count"]} 对）',
             fontsize=12)
for b, v in zip(bars, vals):
    ax.text(b.get_x()+b.get_width()/2, v+40, f'{v:,}', ha='center', fontsize=10)
ax.tick_params(axis='x', labelsize=9)

ax = axes[0][1]
vals = [l['candidate_evaluations'] for l in ledgers]
bars = ax.bar(labels, vals, color=colors, width=.6)
ax.axhline(720, color='#444444', ls='--', lw=1.2)
ax.text(-0.42, 726, '共同预算上限 720 次', ha='left', va='bottom', fontsize=9, color='#444444')
ax.set_ylim(0, 830)
ax.set_ylabel('实际候选基本评价次数')
ax.set_title('(b) 实际评价次数（两两不同）', fontsize=12)
for b, v in zip(bars, vals):
    ax.text(b.get_x()+b.get_width()/2, v+12, f'{v}', ha='center', fontsize=10)
ax.tick_params(axis='x', labelsize=9)

ax = axes[1][0]
vals = [l['final_extra_length_vs_planar_mm'] for l in ledgers]
start_extra = LEDGER_NEW['D']['initial_total_length_mm']-LEDGER_NEW['D']['planar_total_length_mm']
bars = ax.bar(labels, vals, color=colors, width=.6)
ax.axhline(start_extra, color='#444444', ls='--', lw=1.2)
ax.text(-0.42, start_extra+0.05, f'共同起点相对平面 +{start_extra:.4f} mm', ha='left', va='bottom',
        fontsize=9, color='#444444')
ax.set_ylim(8.4, 14.3)
ax.set_ylabel('终态额外长度（mm，相对原始平面）')
ax.set_title('(c) 额外长度（新 E 多 +0.4342 mm）', fontsize=12)
for b, v in zip(bars, vals):
    ax.text(b.get_x()+b.get_width()/2, v+0.05, f'{v:.4f}', ha='center', fontsize=10)
ax.tick_params(axis='x', labelsize=9)

ax = axes[1][1]
vals = [l['runtime_seconds'] for l in ledgers]
bars = ax.bar(labels, vals, color=colors, width=.6)
ax.set_ylim(0, 225)
ax.set_ylabel('单次运行时间（s）')
ax.set_title('(d) 单次实测运行时间（不能外推为效率结论）', fontsize=11)
for b, v in zip(bars, vals):
    ax.text(b.get_x()+b.get_width()/2, v+3, f'{v:.1f}', ha='center', fontsize=10)
ax.tick_params(axis='x', labelsize=9)
fig.suptitle('固定重定位诊断：原诊断（余量 0）与本次加余量（1e-5 mm）对照\n'
             '同一起点、同一 20 目标清单、同一顺序、同一验收规则；预算上限 720 次，实际消耗不同',
             fontsize=12.5)
save(fig, 'f4_diagnostic_comparison')

# ---------------------------------------------------------------- figure 5
ms = ANALYSIS['movement_stats']
oldE = ms['old_E']['RELOCATION']; newE = ms['new_E']['RELOCATION']
fig, axes = plt.subplots(1, 2, figsize=(12.6, 4.9), layout='constrained')
ax = axes[0]
groups = ['旧诊断 E\n(余量 0)', '新诊断 E\n(余量 1e-5)']
basic_pass = [oldE['basic_passed'], newE['basic_passed']]
basic_rej = [oldE['basic_rejected'], newE['basic_rejected']]
x = np.arange(2); w = .5
ax.bar(x, basic_pass, w, label='通过基本评价', color='#3b6ea5')
ax.bar(x, basic_rej, w, bottom=basic_pass, label='基本评价被拒', color='#d9d9d9', edgecolor='#666666')
for i, (bp, br) in enumerate(zip(basic_pass, basic_rej)):
    ax.text(i, bp/2, f'{bp}', ha='center', va='center', color='white', fontsize=11)
    ax.text(i, bp+br/2, f'{br}', ha='center', va='center', color='#333333', fontsize=11)
    ax.text(i, bp+br+2, f'合计 {bp+br} 个重定位候选', ha='center', fontsize=10)
ax.set_xticks(x); ax.set_xticklabels(groups, fontsize=10)
ax.set_ylim(0, max(bp+br for bp, br in zip(basic_pass, basic_rej))*1.2)
ax.set_ylabel('重定位候选数（个）')
ax.set_title('(a) 实际生成并评价的重定位候选', fontsize=12)
ax.legend(fontsize=9, loc='upper right')

ax = axes[1]
reason_labels = ['自检歧义\nSELF_AMBIGUOUS', '目标近距对未清除\nTARGET_NOT_CLEARED',
                 '全局近距对未严格下降\nNO_STRICT_GLOBAL_DEC.', '接受\nACCEPTED']
def occurrences(stats, key):
    occ = stats.get(key) or {}
    return [occ.get('SELF_AMBIGUOUS_CLEARANCE', 0), occ.get('TARGET_NOT_CLEARED', 0),
            occ.get('NO_STRICT_GLOBAL_DECREASE', 0)]
oldv = occurrences(oldE, 'basic_rejection_reason_occurrences') + [0]
newv = occurrences(newE, 'basic_rejection_reason_occurrences') + [newE['accepted_edits']]
oldv[2] = (oldE['full_rejection_reason_occurrences'] or {}).get('NO_STRICT_GLOBAL_DECREASE', 0)
x = np.arange(len(reason_labels)); w = .38
ax.bar(x-w/2, oldv, w, label='旧诊断 E（余量 0）', color='#c9a227')
ax.bar(x+w/2, newv, w, label='新诊断 E（余量 1e-5）', color='#c0392b')
for xi, (o, n) in enumerate(zip(oldv, newv)):
    ax.text(xi-w/2, o+1.5, str(o), ha='center', fontsize=10)
    ax.text(xi+w/2, n+1.5, str(n), ha='center', fontsize=10)
ax.set_xticks(x); ax.set_xticklabels(reason_labels, fontsize=8.5)
ax.set_ylim(0, 88)
ax.set_ylabel('拒绝理由出现次数')
ax.set_title('(b) 拒绝理由（同一候选可有多个理由，出现次数不能相加）', fontsize=11)
ax.legend(fontsize=9)
fig.suptitle('重定位候选的失败原因：旧诊断 0 次接受（126 个候选），新诊断 1 次接受（18 个候选）', fontsize=12.5)
save(fig, 'f5_relocation_rejections')

# ---------------------------------------------------------------- figure 7
route_id = BEFORE_AFTER['route_id']
before = deserialize_route3d(BEFORE_AFTER['before'])
after = deserialize_route3d(BEFORE_AFTER['after'])
planar = deserialize_route3d(BEFORE_AFTER['planar'])
bx, by, bz, bs = samples(before)
ax_, ay, az, as_ = samples(after)
px, py, pz, ps = samples(planar)
fig = plt.figure(figsize=(12.4, 9.0), layout='constrained')
ax = fig.add_subplot(2, 2, 1)
ax.plot(px, py, color='#888888', ls='--', lw=1.4, label='原始平面路线 (z=0)')
ax.plot(bx, by, color='#3b6ea5', lw=2.0, label=f'重定位前（层 {int(round(bz.max()))}）')
ax.plot(ax_, ay, color='#c0392b', lw=1.2, ls=':', label=f'重定位后（层 {int(round(az.max()))}）')
ax.set_aspect('equal'); ax.set_xlabel('X (mm)'); ax.set_ylabel('Y (mm)')
ax.set_title('(a) XY 投影：重定位前后完全重合', fontsize=11.5)
# The equal-aspect strip is only a few millimetres tall, so any legend box would
# overlap the curve, the panel title or the tick labels. Panel (a) therefore has
# no legend: the colour key is written in the figure title instead (below).
ax.grid(alpha=.25, lw=.4)

ax = fig.add_subplot(2, 2, 2)
ax.plot(bs, bz, color='#3b6ea5', lw=2.0)
ax.plot(as_, az, color='#c0392b', lw=2.0, ls='--')
ax.set_ylim(-0.35, 2.85); ax.set_yticks([0, 1, 2])
ax.text(3, 1.10, f'重定位前：层 {int(round(bz.max()))}，长度 {BEFORE_AFTER["before_length_mm"]:.4f} mm',
        color='#3b6ea5', fontsize=9)
ax.text(3, 2.16, f'重定位后：层 {int(round(az.max()))}，长度 {BEFORE_AFTER["after_length_mm"]:.4f} mm',
        color='#c0392b', fontsize=9)
ax.set_xlabel('沿 XY 投影的累计弧长 (mm)'); ax.set_ylabel('Z (mm，真实层高)')
ax.set_title('(b) XZ 侧视：真实层高 0/1/2 mm', fontsize=11.5)
ax.grid(alpha=.25, lw=.4)

X_PAD = 2.0
XLIM = (float(px.min())-X_PAD, float(px.max())+X_PAD)
YLIM = (float(py.min())-X_PAD, float(py.max())+X_PAD)
X_SPAN = XLIM[1]-XLIM[0]; Y_SPAN = YLIM[1]-YLIM[0]
TRUE_Z_SPAN = 2.0

def draw_3d(ax, scale):
    """scale=1 -> true proportions; scale=ZOOM -> Z display values multiplied by
    scale AND the box aspect uses the magnified Z span, so the height really is
    scale times the same-unit X/Y extent on screen."""
    ax.plot(px, py, pz*scale, color='#888888', ls='--', lw=1.2, label='原始平面路线')
    ax.plot(bx, by, bz*scale, color='#3b6ea5', lw=1.8, label='重定位前')
    ax.plot(ax_, ay, az*scale, color='#c0392b', lw=1.8, ls='--', label='重定位后')
    zmax = TRUE_Z_SPAN*scale
    ax.set_xlim(*XLIM); ax.set_ylim(*YLIM); ax.set_zlim(0, zmax)
    ax.set_zticks([0, 1*scale, 2*scale])
    ax.set_zticklabels(['0 (层0)', '1 (层1)', '2 (层2)'] if scale != 1 else ['0', '1', '2'],
                       fontsize=8)
    # One data unit must occupy the same physical length on every axis: the box
    # aspect is the ratio of the displayed spans, so (c) keeps the genuinely
    # flat 2 mm-over-140 mm look and (d) is 20x taller for the same X/Y extent.
    ax.set_box_aspect((X_SPAN, Y_SPAN, zmax))
    # the flat true-scale box leaves little room, so pad the axis labels and use
    # few ticks: labels must not collide with the tick text
    ax.set_xticks([0, 50, 100, 140] if X_SPAN > 100 else None)
    # Y spans only ~10 mm against ~140 mm of X, so in an equal-unit box the Y
    # edge is a few pixels: its tick text could only collide with the label
    ax.set_yticks([])
    ax.set_xlabel('X (mm)', fontsize=9, labelpad=10)
    ax.set_ylabel('Y (mm)', fontsize=9, labelpad=10)
    ax.set_zlabel('Z 显示值' if scale != 1 else 'Z (mm，真实)', fontsize=8.5, labelpad=6)
    ax.view_init(elev=22, azim=-58); ax.tick_params(labelsize=7.5, pad=1)
    return (X_SPAN, Y_SPAN, zmax)

ax = fig.add_subplot(2, 2, 3, projection='3d')
BOX_TRUE = draw_3d(ax, 1.0)
ax.set_title('(c) 真实高度比例三维图（Z 轴不放大；X/Y/Z 同单位同比例）', fontsize=11)
ax.legend(fontsize=8, loc='upper left')

ZOOM = 20
ax = fig.add_subplot(2, 2, 4, projection='3d')
BOX_ZOOM = draw_3d(ax, float(ZOOM))
ax.set_title(f'(d) 示意图：Z 轴显示值放大 {ZOOM} 倍，箱体高度按放大后跨度设置（真实层高 0/1/2 mm）',
             fontsize=10.5)
ax.legend(fontsize=8, loc='upper left')
entry = BEFORE_AFTER['entry']
fig.suptitle(f'路线 {route_id} 的第一次被接受的重定位（新诊断 E，第 {entry["step_index"]} 步，目标 {tuple(entry["target_pair"])}）\n'
             f'从层 1 改到层 2：移除 {len(entry["old_collisions_removed"])} 对近距、新增 {len(entry["new_collisions_created"])} 对，'
             f'全局近距对 {entry["global_pairs_before"]:,} → {entry["global_pairs_after"]:,}；'
             f'单步长度 +{entry["step_length_delta_mm"]:.4f} mm；过渡段数 2 → 2（替换而非叠加）\n'
             f'曲线颜色：(a)(c)(d) 灰虚线=原始平面路线，(b)(c)(d) 蓝实线=重定位前（层 1），'
             f'红虚线=重定位后（层 2）', fontsize=11.5)
save(fig, 'f7_route34_relocation_before_after')

manifest = dict(figures=[{'name': f'{n}.png', 'pdf': f'{n}.pdf'} for n in
        ('f4_diagnostic_comparison', 'f5_relocation_rejections', 'f7_route34_relocation_before_after')],
    inputs=INPUTS, route_id=route_id, zoom_factor=ZOOM,
    box_aspect=dict(true_scale=list(BOX_TRUE), z_magnified=list(BOX_ZOOM),
        note='set_box_aspect uses the displayed span of each axis, so one data unit has the same '
             'physical length on X, Y and Z. (c) true scale: z span 2 mm; (d): z span %g mm '
             '(= 2 mm x %d), i.e. the same X/Y extent is %d times taller on screen.' % (2*ZOOM, ZOOM, ZOOM)),
    displayed_spans_mm=dict(x=X_SPAN, y=Y_SPAN, z_true=TRUE_Z_SPAN, z_magnified=TRUE_Z_SPAN*ZOOM),
    embedded_figure_numbers=False,
    note='shared figures carry no embedded figure number; each report numbers them independently. '
         'true-scale 3D and Z-magnified 3D are separate panels; the magnification is written in the title')
(FIGDIR/'figures_relocation_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps(dict(figures=3, route_id=route_id, zoom=ZOOM), ensure_ascii=False))
