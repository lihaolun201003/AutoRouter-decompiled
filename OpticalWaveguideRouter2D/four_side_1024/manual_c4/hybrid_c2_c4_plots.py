"""Figures for the hybrid C2/C4 directional layer routing experiment (H / V)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = ROOT / 'outputs/manual_c4_new_connectivity'
A_PAYLOAD = CAMPAIGN / 'structured_layer_routing/A/routes_1024.json'
OUT_ROOT = CAMPAIGN / 'hybrid_c2_c4_directional'

from . import spatial_u_bundle_plots as SP  # noqa: E402
from .hybrid_c2_c4 import HybridData, direction_of  # noqa: E402

SAME_COLORS = {'z1_middle': '#1f6fd6', 'corner1': '#2f9e44',
               'corner2': '#7048e8', 'z2_middle': '#e03131'}
SAME_LABELS = {'z1_middle': 'z1 四边中间 U (L3)', 'corner1': 'z2 第一组角部 U (L3)',
               'corner2': 'z2 第二组角部 U (L4)', 'z2_middle': 'z2 四边中间 U (L5)'}
ADJ_COLOR = '#8a8f98'
Z1_EW_COLOR = '#e8590c'
Z1_NS_COLOR = '#1971c2'
Z2_OPP_COLOR = '#9c36b5'


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _category(data, rid):
    record = data.manifest[int(rid)]
    relation = record['relation']
    if relation == 'opposite':
        return ('opposite', record['plane'], direction_of(data.manifest, rid))
    if relation == 'same':
        return ('same', record['plane'], None)
    return ('adjacent', record['plane'], None)


_ROUTE_GROUP = {}


def _u_bundle(data, rid):
    rid = int(rid)
    if not _ROUTE_GROUP:
        for g, info in data.groups.items():
            for route_id in info['route_ids']:
                _ROUTE_GROUP[int(route_id)] = int(g)
    gid = _ROUTE_GROUP.get(rid)
    if gid is None:
        return None
    if 20 <= gid <= 35:
        return 'z1_middle'
    if 144 <= gid <= 159:
        return 'corner1'
    if 160 <= gid <= 175:
        return 'corner2'
    if 176 <= gid <= 191:
        return 'z2_middle'
    return None


def _draw(ax, record, color, highlight_z=None, linewidth=0.45, alpha=0.6):
    for part in record['parts']:
        points = SP._part_samples(part)
        if len(points) == 0:
            continue
        if part['kind'] == 'flat':
            z = round(float(part['z_mm']), 6)
            if highlight_z is not None and abs(z - float(highlight_z)) <= 1e-9:
                ax.plot(points[:, 0], points[:, 1], points[:, 2], color=color,
                        linewidth=linewidth * 1.8, alpha=0.95,
                        solid_capstyle='round', zorder=5)
            else:
                ax.plot(points[:, 0], points[:, 1], points[:, 2], color=color,
                        linewidth=linewidth, alpha=alpha,
                        solid_capstyle='round', zorder=3)
        else:
            ax.plot(points[:, 0], points[:, 1], points[:, 2], color='#8c8c8c',
                    linewidth=linewidth * 1.05, alpha=0.5,
                    solid_capstyle='round', zorder=4)


def _whole(ax, records, title):
    from matplotlib.lines import Line2D
    SP._draw_reference(ax, 0.0)
    for record in records:
        _draw(ax, record, '#777777', linewidth=0.4, alpha=0.55)
    handles = [Line2D([0], [0], color=SP.LAYER_COLORS[z], lw=2,
                      label=SP.LAYER_NAMES[z]) for z in sorted(SP.LAYER_COLORS)]
    handles.append(Line2D([0], [0], color='#8c8c8c', lw=1.5, label='升降过渡 S 曲线'))
    ax.legend(handles=handles, loc='upper right', fontsize=7.5, framealpha=0.85)
    SP._decorate(ax, title)


def _layer(ax, data, records, z_mm, title):
    from matplotlib.lines import Line2D
    SP._draw_reference(ax, z_mm, color=SP.LAYER_COLORS[z_mm], alpha=0.05)
    total = highlighted = 0
    for record in records:
        if not SP.uses_layer(record, z_mm):
            continue
        total += 1
        rid = int(record['route_id'])
        kind = _category(data, rid)
        if kind[0] == 'opposite' and kind[1] == 'z1':
            color = Z1_EW_COLOR if kind[2] == 'EW' else Z1_NS_COLOR
            highlighted += 1
            _draw(ax, record, color, highlight_z=z_mm)
        elif kind[0] == 'opposite' and kind[1] == 'z2':
            highlighted += 1
            _draw(ax, record, Z2_OPP_COLOR, highlight_z=z_mm)
        elif kind[0] == 'same':
            bundle = _u_bundle(data, rid)
            highlighted += 1
            _draw(ax, record, SAME_COLORS.get(bundle, '#666666'), highlight_z=z_mm)
        else:
            _draw(ax, record, ADJ_COLOR, linewidth=0.3, alpha=0.3)
    handles = [Line2D([0], [0], color=Z1_EW_COLOR, lw=2.2, label='z1 横向 E↔W（C2）'),
               Line2D([0], [0], color=Z1_NS_COLOR, lw=2.2, label='z1 纵向 N↔S（C2）'),
               Line2D([0], [0], color=Z2_OPP_COLOR, lw=2.2, label='z2 对边（C4, L2）')]
    for name, color in SAME_COLORS.items():
        handles.append(Line2D([0], [0], color=color, lw=2.2,
                              label=SAME_LABELS[name]))
    handles.append(Line2D([0], [0], color=ADJ_COLOR, lw=1, alpha=0.5,
                          label='邻边（接口层平铺）'))
    ax.legend(handles=handles, loc='upper right', fontsize=6.8, framealpha=0.85)
    SP._decorate(ax, f'{title}\n该层水平传播 {total} 条（高亮 {highlighted} 条）')


def _direction_figure(ax, data, records, key, color, title, z_highlight=None):
    from matplotlib.lines import Line2D
    SP._draw_reference(ax, 0.0)
    for record in records:
        _draw(ax, record, color, highlight_z=z_highlight)
    handles = [Line2D([0], [0], color=color, lw=2.2, label=title)]
    ax.legend(handles=handles, loc='upper right', fontsize=8, framealpha=0.85)
    SP._decorate(ax, title)


def plot_variant(variant, log=print):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    data = HybridData()
    result_dir = OUT_ROOT / variant
    figures = result_dir / 'figures'
    figures.mkdir(parents=True, exist_ok=True)
    payload = _read(result_dir / 'routes_1024.json')
    records = [r for r in payload['routes'] if r.get('status') == 'routed']
    a_payload = _read(A_PAYLOAD)
    a_records = [r for r in a_payload['routes'] if r.get('status') == 'routed']

    for name, data_records, title in (
            ('01_before_3d', a_records,
             '优化前：Structured A（1024/1024，19584 唯一交叉对，z=0 交叉 17576）'),
            ('02_after_3d', records,
             f'优化后：Hybrid C2/C4 方向分层 {variant}（1024/1024）')):
        fig = plt.figure(figsize=SP.FIGSIZE)
        ax = fig.add_subplot(111, projection='3d')
        fig.subplots_adjust(left=0.01, right=0.99, bottom=0.045, top=0.885)
        _whole(ax, data_records, title)
        SP._save(fig, figures / name)
        plt.close(fig)
        log(f'[hybrid plots {variant}] {name}')

    layer_specs = [('03_L1_z1', 0.0, 'L1-z1（z = 0.0 mm）'),
                   ('04_L1_z2', 0.5, 'L1-z2（z = 0.5 mm）'),
                   ('05_L2', 1.0, 'L2（z = 1.0 mm）：目标方向集中层'),
                   ('06_L3', 1.5, 'L3（z = 1.5 mm）：U 线束'),
                   ('07_L4', 2.0, 'L4（z = 2.0 mm）：U 线束'),
                   ('08_L5', 2.5, 'L5（z = 2.5 mm）：U 线束')]
    for name, z, title in layer_specs:
        fig = plt.figure(figsize=SP.FIGSIZE)
        ax = fig.add_subplot(111, projection='3d')
        fig.subplots_adjust(left=0.01, right=0.99, bottom=0.045, top=0.885)
        _layer(ax, data, records, z, title)
        SP._save(fig, figures / name)
        plt.close(fig)
        log(f'[hybrid plots {variant}] {name}')

    z1_ew = [r for r in records
             if _category(data, int(r['route_id'])) == ('opposite', 'z1', 'EW')]
    z1_ns = [r for r in records
             if _category(data, int(r['route_id'])) == ('opposite', 'z1', 'NS')]
    for name, route_list, color, title in (
            ('09_z1_horizontal', z1_ew, Z1_EW_COLOR,
             'z1 横向 E↔W 连接（132 条，66 个 C2 二元组）'),
            ('10_z1_vertical', z1_ns, Z1_NS_COLOR,
             'z1 纵向 N↔S 连接（132 条，66 个 C2 二元组）')):
        fig = plt.figure(figsize=SP.FIGSIZE)
        ax = fig.add_subplot(111, projection='3d')
        fig.subplots_adjust(left=0.01, right=0.99, bottom=0.045, top=0.885)
        _direction_figure(ax, data, route_list, name, color, title)
        SP._save(fig, figures / name)
        plt.close(fig)
        log(f'[hybrid plots {variant}] {name}')

    # all z1 opposite connections, coloured by direction
    fig = plt.figure(figsize=SP.FIGSIZE)
    ax = fig.add_subplot(111, projection='3d')
    fig.subplots_adjust(left=0.01, right=0.99, bottom=0.045, top=0.885)
    SP._draw_reference(ax, 0.0)
    from matplotlib.lines import Line2D
    for record in z1_ew:
        _draw(ax, record, Z1_EW_COLOR)
    for record in z1_ns:
        _draw(ax, record, Z1_NS_COLOR)
    handles = [Line2D([0], [0], color=Z1_EW_COLOR, lw=2.2, label='横向 E↔W'),
               Line2D([0], [0], color=Z1_NS_COLOR, lw=2.2, label='纵向 N↔S')]
    ax.legend(handles=handles, loc='upper right', fontsize=8, framealpha=0.85)
    SP._decorate(ax, f'z1 对边方向分层（{variant}）：横向与纵向处于不同物理高度')
    SP._save(fig, figures / '11_z1_direction_split')
    plt.close(fig)
    log(f'[hybrid plots {variant}] 11_z1_direction_split')

    # all opposite connections
    opposite = [r for r in records
                if _category(data, int(r['route_id']))[0] == 'opposite']
    z2_opp = [r for r in records
              if _category(data, int(r['route_id']))[0] == 'opposite'
              and _category(data, int(r['route_id']))[1] == 'z2']
    fig = plt.figure(figsize=SP.FIGSIZE)
    ax = fig.add_subplot(111, projection='3d')
    fig.subplots_adjust(left=0.01, right=0.99, bottom=0.045, top=0.885)
    SP._draw_reference(ax, 0.0)
    for record in z1_ew:
        _draw(ax, record, Z1_EW_COLOR)
    for record in z1_ns:
        _draw(ax, record, Z1_NS_COLOR)
    for record in z2_opp:
        _draw(ax, record, Z2_OPP_COLOR)
    handles = [Line2D([0], [0], color=Z1_EW_COLOR, lw=2.2, label='z1 横向 E↔W'),
               Line2D([0], [0], color=Z1_NS_COLOR, lw=2.2, label='z1 纵向 N↔S'),
               Line2D([0], [0], color=Z2_OPP_COLOR, lw=2.2, label='z2 对边（C4, L2）')]
    ax.legend(handles=handles, loc='upper right', fontsize=8, framealpha=0.85)
    SP._decorate(ax, f'仅对边线路三维图（{variant}）')
    SP._save(fig, figures / '12_opposite_only_3d')
    plt.close(fig)
    log(f'[hybrid plots {variant}] 12_opposite_only_3d')

    # dense-crossing-region zoom: before (A) and after (variant)
    fig = plt.figure(figsize=(15.4, 8.6))
    for index, (title, record_list, highlight) in enumerate(
            (('优化前 A：z=0 横纵同层交叉密集区', a_records, None),
             (f'优化后 {variant}：横向 L2 / 纵向 L1 分离', records, None))):
        ax = fig.add_subplot(1, 2, index + 1, projection='3d')
        SP._draw_reference(ax, 0.0)
        for record in record_list:
            if title.startswith('优化前'):
                rid = int(record['route_id'])
                kind = _category(data, rid)
                if kind[0] == 'opposite' and kind[1] == 'z1':
                    color = Z1_EW_COLOR if kind[2] == 'EW' else Z1_NS_COLOR
                else:
                    color = '#cccccc'
            else:
                rid = int(record['route_id'])
                kind = _category(data, rid)
                if kind[0] == 'opposite' and kind[1] == 'z1':
                    color = Z1_EW_COLOR if kind[2] == 'EW' else Z1_NS_COLOR
                else:
                    color = '#cccccc'
            _draw(ax, record, color, linewidth=0.5, alpha=0.65)
        ax.set_xlim(45.0, 105.0)
        ax.set_ylim(45.0, 105.0)
        ax.set_zlim(-0.05, 1.15)
        ax.set_xlabel('x (mm)')
        ax.set_ylabel('y (mm)')
        ax.set_zlabel('z (mm)')
        ax.view_init(**SP.VIEW)
        ax.set_box_aspect((1.0, 1.0, 0.5))
        ax.set_title(title, fontsize=10.5, pad=10)
    fig.subplots_adjust(left=0.01, right=0.99, bottom=0.04, top=0.9, wspace=0.05)
    SP._save(fig, figures / '13_dense_region_zoom')
    plt.close(fig)
    log(f'[hybrid plots {variant}] 13_dense_region_zoom')
    return figures


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant', required=True, choices=['H', 'V'])
    args = parser.parse_args(argv)
    figures = plot_variant(args.variant)
    print(f'figures written: {figures}')


if __name__ == '__main__':
    main()
