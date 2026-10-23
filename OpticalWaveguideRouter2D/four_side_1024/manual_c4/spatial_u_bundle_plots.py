"""Figures for the spatial grouped U-bundle 3D routing experiment.

Reading only the saved payloads (no re-routing):
* ``01_before_3d`` / ``02_after_3d`` : whole-board 3D before (Manual-C4 dynamic V2)
  and after (spatial U-bundle layout);
* ``03_L1_z1`` .. ``08_L5`` : one figure per physical height, showing every route
  that has horizontal propagation on that height; the 64 target U quartets are
  highlighted by bundle colour and all other routes are drawn muted;
* ``09_bundle_*`` : 3D zoom (4 sides) of each of the four target bundles.

All figures use identical axes limits / view / canvas.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = ROOT / 'outputs/manual_c4_new_connectivity'
AFTER_DIR = CAMPAIGN / 'phase5_dynamic_optimization/after'
OUT_DIR = CAMPAIGN / 'spatial_u_bundle_optimization'

XLIM = (-5.0, 155.0)
YLIM = (-5.0, 155.0)
ZLIM = (-0.1, 2.7)
VIEW = dict(elev=26, azim=-58)
BOX_ASPECT = (1.0, 1.0, 0.62)
FIGSIZE = (13.2, 11.2)
DPI = 220
BOARD = 150.0

LAYER_COLORS = {0.0: '#1f6fd6', 0.5: '#e07b1a', 1.0: '#2f9e44',
                1.5: '#7048e8', 2.0: '#e03131', 2.5: '#0c8599'}
LAYER_NAMES = {0.0: 'L1-z1  z=0.0 mm', 0.5: 'L1-z2  z=0.5 mm',
               1.0: 'L2  z=1.0 mm', 1.5: 'L3  z=1.5 mm',
               2.0: 'L4  z=2.0 mm', 2.5: 'L5  z=2.5 mm'}
BUNDLE_COLORS = {'z1_middle_U': '#1f6fd6', 'z2_corner_U_1': '#2f9e44',
                 'z2_corner_U_2': '#7048e8', 'z2_middle_U': '#e03131'}
BUNDLE_NAMES = {'z1_middle_U': 'z1 四边中间 U（L2）',
                'z2_corner_U_1': 'z2 第一组四角 U（L2）',
                'z2_corner_U_2': 'z2 第二组四角 U（L3）',
                'z2_middle_U': 'z2 四边中间 U（L4）'}
TARGET_Z = {'z1_middle_U': 1.0, 'z2_corner_U_1': 1.0,
            'z2_corner_U_2': 1.5, 'z2_middle_U': 2.0}


def _read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _part_samples(part):
    from ..v3c4.lift_cross_run import _part_samples
    return _part_samples(part)


def _flat_parts(record):
    return [part for part in record.get('parts') or [] if part['kind'] == 'flat']


def uses_layer(record, z_mm):
    for part in _flat_parts(record):
        if abs(float(part['z_mm']) - float(z_mm)) <= 1e-9:
            return True
    return False


def _draw_reference(ax, z_mm, color='#999999', alpha=0.05):
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    corners = [(0, 0), (BOARD, 0), (BOARD, BOARD), (0, BOARD)]
    for height, line_color, linestyle in ((0.0, '#cccccc', ':'),
                                          (0.5, '#d8d8d8', '--')):
        xs = [x for x, _ in corners] + [0]
        ys = [y for _, y in corners] + [0]
        ax.plot(xs, ys, [height] * 5, color=line_color, linewidth=0.55,
                linestyle=linestyle, zorder=1)
    plane = Poly3DCollection([[(0, 0, z_mm), (BOARD, 0, z_mm),
                               (BOARD, BOARD, z_mm), (0, BOARD, z_mm)]],
                             facecolor=color, alpha=alpha,
                             edgecolor='#999999', linewidth=0.3, zorder=0)
    ax.add_collection3d(plane)


def _decorate(ax, title, subtitle=None, fontsize=11.5):
    ax.set_xlim(*XLIM)
    ax.set_ylim(*YLIM)
    ax.set_zlim(*ZLIM)
    ax.set_xlabel('x (mm)', labelpad=8)
    ax.set_ylabel('y (mm)', labelpad=8)
    ax.set_zlabel('z (mm)', labelpad=8)
    ax.set_xticks([0, 25, 50, 75, 100, 125, 150])
    ax.set_yticks([0, 25, 50, 75, 100, 125, 150])
    ax.set_zticks([0.0, 0.5, 1.0, 1.5, 2.0, 2.5])
    ax.view_init(**VIEW)
    ax.set_box_aspect(BOX_ASPECT)
    ax.grid(True)
    text = title if subtitle is None else f'{title}\n{subtitle}'
    ax.set_title(text, fontsize=fontsize, pad=12)


def _save(fig, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path.with_suffix('.png'), dpi=DPI, facecolor='white')
    fig.savefig(path.with_suffix('.svg'), facecolor='white')
    return path


def draw_route(ax, record, highlight_color=None, z_highlight=None,
               linewidth=0.5, alpha=0.7):
    for part in record['parts']:
        points = _part_samples(part)
        if len(points) == 0:
            continue
        if part['kind'] == 'flat':
            z = round(float(part['z_mm']), 6)
            if (highlight_color is not None and z_highlight is not None
                    and abs(z - float(z_highlight)) <= 1e-9):
                ax.plot(points[:, 0], points[:, 1], points[:, 2],
                        color=highlight_color, linewidth=linewidth * 1.7,
                        alpha=0.95, solid_capstyle='round', zorder=5)
            else:
                color = LAYER_COLORS.get(z, '#555555')
                ax.plot(points[:, 0], points[:, 1], points[:, 2],
                        color=color, linewidth=linewidth, alpha=alpha,
                        solid_capstyle='round', zorder=3)
        else:
            ax.plot(points[:, 0], points[:, 1], points[:, 2],
                    color='#8c8c8c', linewidth=linewidth * 1.05,
                    alpha=0.55, solid_capstyle='round', zorder=4)


def whole_board(ax, records, title):
    from matplotlib.lines import Line2D
    _draw_reference(ax, 0.0)
    for record in records:
        draw_route(ax, record, linewidth=0.42, alpha=0.62)
    handles = [Line2D([0], [0], color=LAYER_COLORS[z], lw=2,
                      label=LAYER_NAMES[z]) for z in sorted(LAYER_COLORS)]
    handles.append(Line2D([0], [0], color='#8c8c8c', lw=1.6,
                          label='升降过渡 S 曲线'))
    ax.legend(handles=handles, loc='upper right', fontsize=7.5, framealpha=0.85)
    _decorate(ax, title)


def layer_figure(ax, records, target_groups, z_mm, title):
    from matplotlib.lines import Line2D
    _draw_reference(ax, z_mm, color=LAYER_COLORS[z_mm], alpha=0.05)
    rid_bundle = {rid: conf['name'] for gid, conf in target_groups.items()
                  for rid in conf['route_ids']}
    total_here = 0
    highlighted = 0
    for record in records:
        if not uses_layer(record, z_mm):
            continue
        total_here += 1
        rid = int(record['route_id'])
        if rid in rid_bundle:
            highlighted += 1
            draw_route(ax, record, highlight_color=BUNDLE_COLORS[rid_bundle[rid]],
                       z_highlight=z_mm, linewidth=0.55, alpha=0.5)
        else:
            draw_route(ax, record, linewidth=0.35, alpha=0.35)
    bundle_names = [name for name in BUNDLE_COLORS
                    if abs(TARGET_Z[name] - float(z_mm)) <= 1e-9]
    handles = [Line2D([0], [0], color=BUNDLE_COLORS[name], lw=2.2,
                      label=BUNDLE_NAMES[name]) for name in bundle_names]
    handles.append(Line2D([0], [0], color='#9a9a9a', lw=1, alpha=0.5,
                          label='其他路线（该层水平段）'))
    ax.legend(handles=handles, loc='upper right', fontsize=7.5, framealpha=0.85)
    _decorate(ax, f'{title}\n该层水平传播 {total_here} 条'
                  f'（其中目标 U 线束 {highlighted} 条高亮）')


def bundle_figure(ax, records, bundle_name, title):
    from matplotlib.lines import Line2D
    _draw_reference(ax, TARGET_Z[bundle_name],
                    color=BUNDLE_COLORS[bundle_name], alpha=0.05)
    for record in records:
        draw_route(ax, record, highlight_color=BUNDLE_COLORS[bundle_name],
                   z_highlight=TARGET_Z[bundle_name], linewidth=0.7, alpha=0.6)
    handles = [Line2D([0], [0], color=BUNDLE_COLORS[bundle_name], lw=2.4,
                      label=f'{BUNDLE_NAMES[bundle_name]}：目标层水平段'),
               Line2D([0], [0], color='#9a9a9a', lw=1, alpha=0.6,
                      label='其他高度水平段'),
               Line2D([0], [0], color='#8c8c8c', lw=1.6,
                      label='升降 S 曲线（R=15 mm）')]
    ax.legend(handles=handles, loc='upper right', fontsize=7.5, framealpha=0.85)
    _decorate(ax, title)


def plot_all(final_payload, target_manifest, out_dir=None, log=print):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    out_dir = Path(out_dir or (OUT_DIR / 'figures'))
    out_dir.mkdir(parents=True, exist_ok=True)
    before = _read_json(AFTER_DIR / 'routes_l3d.json')
    before_records = [record for record in before['routes']
                      if record.get('status') == 'routed']
    after_records = [record for record in final_payload['routes']
                     if record.get('status') == 'routed']
    target_groups = {gid: dict(route_ids=list(conf['route_ids']),
                               name=conf['name'], layer_z=conf['layer_z'])
                     for gid, conf in target_manifest.items()}

    for name, records, title in (
            ('01_before_3d', before_records,
             '优化前：Manual-C4 动态优化 V2（1024/1024，23356 唯一交叉对）'),
            ('02_after_3d', after_records,
             '优化后：空间分组式 U 形线束三维布线（指定分层 64/64）')):
        fig = plt.figure(figsize=FIGSIZE)
        ax = fig.add_subplot(111, projection='3d')
        fig.subplots_adjust(left=0.01, right=0.99, bottom=0.045, top=0.885)
        whole_board(ax, records, title)
        fig.text(0.5, 0.015,
                 '数据来源：spatial_u_bundle_optimization/routes_1024.json'
                 '（仅可视化，未重新布线）', ha='center', va='center',
                 fontsize=8, color='#666666')
        _save(fig, out_dir / name)
        plt.close(fig)
        log(f'[u-bundle plots] {name}')

    layer_specs = [('03_L1_z1', 0.0, 'L1-z1（row1 接口层）z = 0.0 mm'),
                   ('04_L1_z2', 0.5, 'L1-z2（row2 接口层）z = 0.5 mm'),
                   ('05_L2', 1.0, 'L2  z = 1.0 mm'),
                   ('06_L3', 1.5, 'L3  z = 1.5 mm'),
                   ('07_L4', 2.0, 'L4  z = 2.0 mm'),
                   ('08_L5', 2.5, 'L5  z = 2.5 mm')]
    for name, z, title in layer_specs:
        fig = plt.figure(figsize=FIGSIZE)
        ax = fig.add_subplot(111, projection='3d')
        fig.subplots_adjust(left=0.01, right=0.99, bottom=0.045, top=0.885)
        layer_figure(ax, after_records, target_groups, z,
                     f'{title}：该层水平传播的波导（目标 U 线束高亮）')
        _save(fig, out_dir / name)
        plt.close(fig)
        log(f'[u-bundle plots] {name}')

    for index, bundle_name in enumerate(BUNDLE_COLORS, 1):
        gids = [gid for gid, conf in target_manifest.items()
                if conf['name'] == bundle_name]
        rids = {rid for gid in gids for rid in target_manifest[gid]['route_ids']}
        records = [record for record in after_records
                   if int(record['route_id']) in rids]
        fig = plt.figure(figsize=(12.0, 10.0))
        ax = fig.add_subplot(111, projection='3d')
        fig.subplots_adjust(left=0.01, right=0.99, bottom=0.045, top=0.87)
        bundle_figure(ax, records, bundle_name,
                      f'{BUNDLE_NAMES[bundle_name]}：三维局部放大'
                      f'（{len(records)} 条路由）')
        _save(fig, out_dir / f'{8 + index:02d}_bundle_{bundle_name}')
        plt.close(fig)
        log(f'[u-bundle plots] bundle {bundle_name}')
    return out_dir
