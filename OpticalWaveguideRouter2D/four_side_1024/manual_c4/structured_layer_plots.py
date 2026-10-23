"""Figures for the structured layer routing experiment (groups A / B).

Reuses the canvas helpers of :mod:`spatial_u_bundle_plots` but draws the layered
structure: adjacent flat at the interface, opposite concentrated on L2 (or kept
flat as documented exceptions), U bundles on L3/L4/L5.

Figure set (per group directory ``figures/``):
* 01_before_3d / 02_after_3d : previous Spatial-U layout vs structured layout;
* 03_L1_z1 .. 08_L5          : one figure per physical height (all routes using it,
                               opposite / U bundles highlighted);
* 09_opposite_3d             : only the opposite connections (parallel L2 bundles);
* 10_opposite_L2             : only opposite connections, L2 horizontal parts;
* 11_opposite_transition_zoom: local zoom of the opposite S-transition bands;
* 12_u_L3 / 13_u_L4 / 14_u_L5: only the U routes on their target layers;
* 15_u_3d                    : only the U routes (whole board).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = ROOT / 'outputs/manual_c4_new_connectivity'
OLD_BASELINE = CAMPAIGN / 'spatial_u_bundle_optimization/routes_1024.json'
OUT_ROOT = CAMPAIGN / 'structured_layer_routing'

from . import spatial_u_bundle_plots as SP  # noqa: E402
from . import structured_layer_routing as S  # noqa: E402

ADJACENT_COLOR = '#8a8f98'
OPPOSITE_COLOR = '#e8590c'
U_COLORS = {'z1_middle': '#1f6fd6', 'corner1': '#2f9e44',
            'corner2': '#7048e8', 'z2_middle': '#e03131'}
U_LABELS = {'z1_middle': 'z1 四边中间 U (L3)',
            'corner1': 'z2 第一组角部 U (L3)',
            'corner2': 'z2 第二组角部 U (L4)',
            'z2_middle': 'z2 四边中间 U (L5)'}


def _read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _kind_of(campaign, rid):
    record = campaign.record(rid)
    return record['relation']


def _u_bundle_of(gid):
    for name, spec in S.U_BUNDLES.items():
        if int(gid) in spec['gids']:
            return name
    return None


def _route_kind_map(campaign):
    kind = {}
    u_bundle = {}
    for rid in campaign.manifest:
        kind[int(rid)] = campaign.record(rid)['relation']
    for name, spec in S.U_BUNDLES.items():
        for gid in spec['gids']:
            for rid in campaign.group_routes(gid):
                u_bundle[int(rid)] = name
    return kind, u_bundle


def draw_route(ax, record, color=None, highlight_z=None, linewidth=0.5, alpha=0.65):
    for part in record['parts']:
        points = SP._part_samples(part)
        if len(points) == 0:
            continue
        if part['kind'] == 'flat':
            z = round(float(part['z_mm']), 6)
            if highlight_z is not None and abs(z - float(highlight_z)) <= 1e-9:
                ax.plot(points[:, 0], points[:, 1], points[:, 2], color=color,
                        linewidth=linewidth * 1.7, alpha=0.95,
                        solid_capstyle='round', zorder=5)
            else:
                ax.plot(points[:, 0], points[:, 1], points[:, 2],
                        color=color or SP.LAYER_COLORS.get(z, '#555555'),
                        linewidth=linewidth, alpha=alpha,
                        solid_capstyle='round', zorder=3)
        else:
            ax.plot(points[:, 0], points[:, 1], points[:, 2], color='#8c8c8c',
                    linewidth=linewidth * 1.05, alpha=0.55,
                    solid_capstyle='round', zorder=4)


def whole_board(ax, records, title):
    from matplotlib.lines import Line2D
    SP._draw_reference(ax, 0.0)
    for record in records:
        draw_route(ax, record, linewidth=0.42, alpha=0.62)
    handles = [Line2D([0], [0], color=SP.LAYER_COLORS[z], lw=2,
                      label=SP.LAYER_NAMES[z]) for z in sorted(SP.LAYER_COLORS)]
    handles.append(Line2D([0], [0], color='#8c8c8c', lw=1.6, label='升降过渡 S 曲线'))
    ax.legend(handles=handles, loc='upper right', fontsize=7.5, framealpha=0.85)
    SP._decorate(ax, title)


def layer_figure(ax, records, kind, u_bundle, z_mm, title):
    from matplotlib.lines import Line2D
    SP._draw_reference(ax, z_mm, color=SP.LAYER_COLORS[z_mm], alpha=0.05)
    total = highlighted = 0
    for record in records:
        if not SP.uses_layer(record, z_mm):
            continue
        total += 1
        rid = int(record['route_id'])
        relation = kind[rid]
        if relation == 'opposite':
            highlighted += 1
            draw_route(ax, record, color=OPPOSITE_COLOR, highlight_z=z_mm)
        elif relation == 'same':
            highlighted += 1
            draw_route(ax, record, color=U_COLORS[u_bundle[rid]], highlight_z=z_mm)
        else:
            draw_route(ax, record, color=ADJACENT_COLOR, linewidth=0.32, alpha=0.32)
    handles = [Line2D([0], [0], color=OPPOSITE_COLOR, lw=2.2,
                      label='对边连接（L2 集中，例外保留接口层）')]
    for name, color in U_COLORS.items():
        handles.append(Line2D([0], [0], color=color, lw=2.2, label=U_LABELS[name]))
    handles.append(Line2D([0], [0], color=ADJACENT_COLOR, lw=1, alpha=0.5,
                          label='邻边连接（接口层平铺）'))
    ax.legend(handles=handles, loc='upper right', fontsize=7.0, framealpha=0.85)
    SP._decorate(ax, f'{title}\n该层水平传播 {total} 条（高亮 {highlighted} 条）')


def category_3d(ax, records, title, color_by_relation=True):
    from matplotlib.lines import Line2D
    SP._draw_reference(ax, 0.0)
    for record in records:
        draw_route(ax, record, linewidth=0.5, alpha=0.6)
    handles = [Line2D([0], [0], color=SP.LAYER_COLORS[z], lw=2,
                      label=SP.LAYER_NAMES[z]) for z in sorted(SP.LAYER_COLORS)]
    handles.append(Line2D([0], [0], color='#8c8c8c', lw=1.6, label='升降过渡 S 曲线'))
    ax.legend(handles=handles, loc='upper right', fontsize=7.5, framealpha=0.85)
    SP._decorate(ax, title)


def category_layer(ax, records, kind=None, u_bundle=None, color=None, z_mm=None,
                   highlight=None, title=''):
    from matplotlib.lines import Line2D
    if z_mm is not None:
        SP._draw_reference(ax, z_mm, color=SP.LAYER_COLORS[z_mm], alpha=0.05)
    else:
        SP._draw_reference(ax, 0.0)
    for record in records:
        rid = int(record['route_id'])
        draw_route(ax, record, color=color, highlight_z=highlight)
    handles = [Line2D([0], [0], color=color or '#555555', lw=2.2,
                      label=title or 'filtered')]
    ax.legend(handles=handles, loc='upper right', fontsize=8, framealpha=0.85)
    SP._decorate(ax, title)


def plot_group(campaign_name, group_dir, log=print):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    group_dir = Path(group_dir)
    figures = group_dir / 'figures'
    figures.mkdir(parents=True, exist_ok=True)
    campaign = S.StructuredCampaign(swap_rows=group_dir.name.startswith('B'))
    payload = _read_json(group_dir / 'routes_1024.json')
    records = [record for record in payload['routes']
               if record.get('status') == 'routed']
    kind, u_bundle = _route_kind_map(campaign)
    old = _read_json(OLD_BASELINE)
    old_records = [record for record in old['routes']
                   if record.get('status') == 'routed']

    # before / after whole board
    for name, data, title in (
            ('01_before_3d', old_records,
             '优化前：Manual-C4 Spatial U-bundle（1024/1024，12824 唯一交叉对）'),
            ('02_after_3d', records,
             f'优化后：结构化分层布线 {campaign.name}（1024/1024，'
             f'规则分层 L2/L3/L4/L5）')):
        fig = plt.figure(figsize=SP.FIGSIZE)
        ax = fig.add_subplot(111, projection='3d')
        fig.subplots_adjust(left=0.01, right=0.99, bottom=0.045, top=0.885)
        whole_board(ax, data, title)
        SP._save(fig, figures / name)
        plt.close(fig)
        log(f'[structured plots] {name}')

    # per physical height
    layer_specs = [('03_L1_z1', 0.0, 'L1-z1（row1 接口层）z = 0.0 mm'),
                   ('04_L1_z2', 0.5, 'L1-z2（row2 接口层）z = 0.5 mm'),
                   ('05_L2', 1.0, 'L2  z = 1.0 mm（对边集中层）'),
                   ('06_L3', 1.5, 'L3  z = 1.5 mm（U: z1 中间 + z2 第一组角部）'),
                   ('07_L4', 2.0, 'L4  z = 2.0 mm（U: z2 第二组角部）'),
                   ('08_L5', 2.5, 'L5  z = 2.5 mm（U: z2 中间）')]
    for name, z, title in layer_specs:
        fig = plt.figure(figsize=SP.FIGSIZE)
        ax = fig.add_subplot(111, projection='3d')
        fig.subplots_adjust(left=0.01, right=0.99, bottom=0.045, top=0.885)
        layer_figure(ax, records, kind, u_bundle, z, title)
        SP._save(fig, figures / name)
        plt.close(fig)
        log(f'[structured plots] {name}')

    # opposite-only views
    opposite = [record for record in records
                if kind[int(record['route_id'])] == 'opposite']
    for name, title in (('09_opposite_3d', '仅对边连接：L2 平行直通线束（整板 3D）'),
                        ('10_opposite_L2', '仅对边连接：L2 水平段')):
        fig = plt.figure(figsize=SP.FIGSIZE)
        ax = fig.add_subplot(111, projection='3d')
        fig.subplots_adjust(left=0.01, right=0.99, bottom=0.045, top=0.885)
        highlight = 1.0 if name == '10_opposite_L2' else None
        category_layer(ax, opposite, color=OPPOSITE_COLOR, z_mm=1.0,
                       highlight=highlight, title=title)
        SP._save(fig, figures / name)
        plt.close(fig)
        log(f'[structured plots] {name}')

    # opposite transition zoom (whole = left, zoom = right)
    transitions = []
    for record in opposite:
        for part in record['parts']:
            if part['kind'] == 'transition':
                transitions.append(part)
    if transitions:
        xs = [part['start'][0] for part in transitions] + \
             [part['end'][0] for part in transitions]
        ys = [part['start'][1] for part in transitions] + \
             [part['end'][1] for part in transitions]
        x_mid = (min(xs) + max(xs)) / 2.0
        y_mid = (min(ys) + max(ys)) / 2.0
        x_span = max(30.0, (max(xs) - min(xs)) / 2.0 + 15.0)
        y_span = max(30.0, (max(ys) - min(ys)) / 2.0 + 15.0)
        x_lo = max(-5.0, x_mid - x_span)
        x_hi = min(155.0, x_mid + x_span)
        y_lo = max(-5.0, y_mid - y_span)
        y_hi = min(155.0, y_mid + y_span)
        fig = plt.figure(figsize=(15.0, 8.4))
        for index, (title, limits) in enumerate(
                (('仅对边连接：整体 3D', None),
                 ('对边线束升降区域局部放大', (x_lo, x_hi, y_lo, y_hi)))):
            ax = fig.add_subplot(1, 2, index + 1, projection='3d')
            SP._draw_reference(ax, 1.0, color=OPPOSITE_COLOR, alpha=0.05)
            for record in opposite:
                draw_route(ax, record, color=OPPOSITE_COLOR, highlight_z=1.0,
                           linewidth=0.55, alpha=0.6)
            if limits is not None:
                ax.set_xlim(limits[0], limits[1])
                ax.set_ylim(limits[2], limits[3])
                ax.set_zlim(-0.05, 1.15)
                ax.set_box_aspect((limits[1] - limits[0], limits[3] - limits[2],
                                   1.2 * 0.62 * (limits[1] - limits[0]) / 1.2))
            else:
                ax.set_xlim(*SP.XLIM)
                ax.set_ylim(*SP.YLIM)
                ax.set_zlim(*SP.ZLIM)
                ax.set_box_aspect(SP.BOX_ASPECT)
            ax.set_xlabel('x (mm)')
            ax.set_ylabel('y (mm)')
            ax.set_zlabel('z (mm)')
            ax.view_init(**SP.VIEW)
            ax.set_title(title, fontsize=10.5, pad=10)
        fig.subplots_adjust(left=0.01, right=0.99, bottom=0.03, top=0.9,
                            wspace=0.05)
        SP._save(fig, figures / '11_opposite_transition_zoom')
        plt.close(fig)
        log('[structured plots] 11_opposite_transition_zoom')

    # U-only views
    u_records = [record for record in records
                 if kind[int(record['route_id'])] == 'same']
    fig = plt.figure(figsize=SP.FIGSIZE)
    ax = fig.add_subplot(111, projection='3d')
    fig.subplots_adjust(left=0.01, right=0.99, bottom=0.045, top=0.885)
    category_3d(ax, u_records, '仅 U 形线束：L3/L4/L5 指定分层')
    SP._save(fig, figures / '15_u_3d')
    plt.close(fig)
    log('[structured plots] 15_u_3d')
    for name, layer, z, label in (('12_u_L3', 3, 1.5, 'U 线束 L3'),
                                  ('13_u_L4', 4, 2.0, 'U 线束 L4'),
                                  ('14_u_L5', 5, 2.5, 'U 线束 L5')):
        selected = [record for record in u_records if SP.uses_layer(record, z)]
        fig = plt.figure(figsize=SP.FIGSIZE)
        ax = fig.add_subplot(111, projection='3d')
        fig.subplots_adjust(left=0.01, right=0.99, bottom=0.045, top=0.885)
        SP._draw_reference(ax, z, color=SP.LAYER_COLORS[z], alpha=0.05)
        for record in selected:
            rid = int(record['route_id'])
            draw_route(ax, record, color=U_COLORS[u_bundle[rid]],
                       highlight_z=z, linewidth=0.6, alpha=0.6)
        from matplotlib.lines import Line2D
        handles = [Line2D([0], [0], color=color, lw=2.2, label=U_LABELS[bundle])
                   for bundle, color in U_COLORS.items()]
        ax.legend(handles=handles, loc='upper right', fontsize=7.5,
                  framealpha=0.85)
        SP._decorate(ax, f'{label}（z = {z:.1f} mm）：{len(selected)} 条')
        SP._save(fig, figures / name)
        plt.close(fig)
        log(f'[structured plots] {name}')
    return figures


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--group', default='A')
    args = parser.parse_args(argv)
    group_dir = OUT_ROOT / args.group
    figures = plot_group(args.group, group_dir)
    print(f'figures written: {figures}')


if __name__ == '__main__':
    main()
