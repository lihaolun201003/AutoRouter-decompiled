"""Phase-2 2D figures for the new manual C4 connectivity.

Outputs (PNG + SVG) under ``outputs/manual_c4_new_connectivity/phase2_2d/plots``:

* ``01_overview_1024``        both routing planes, routes coloured by relation
* ``02_row1_z1`` / ``03_row2_z2``  one plane per figure
* ``04_same_side_u_zoom``     zoom on the N-edge same-side U turns (both planes)

Rendering only: the primitives are the saved 2D routes, nothing is re-routed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from ..v3c4.profile import apply as apply_profile  # noqa: F401  (radius binder)

COLORS = {'opposite': '#1f6fd6', 'adjacent': '#2ca02c', 'same': '#d62728'}
Z_TITLES = {'z1': 'row 1 / z1 (z = 0.0 mm)', 'z2': 'row 2 / z2 (z = 0.5 mm)'}
BOARD = 150.0
DPI = 200


def sample_primitive(primitive, max_step=0.5, deg_step=6.0):
    """Return an (N, 2) polyline of one line/arc primitive."""
    if primitive['kind'] == 'line':
        p0 = np.asarray(primitive['p0'], dtype=float)
        p1 = np.asarray(primitive['p1'], dtype=float)
        length = float(np.linalg.norm(p1 - p0))
        count = max(2, int(np.ceil(length / max_step)) + 1)
        t = np.linspace(0.0, 1.0, count)[:, None]
        return p0[None, :] * (1.0 - t) + p1[None, :] * t
    center = np.asarray(primitive['center'], dtype=float)
    radius = float(primitive['radius'])
    start = float(primitive['start_angle'])
    sweep = float(primitive['sweep'])
    steps = max(2, int(abs(np.degrees(sweep)) / deg_step) + 1)
    angles = start + sweep * np.linspace(0.0, 1.0, steps)
    return np.stack([center[0] + radius * np.cos(angles),
                     center[1] + radius * np.sin(angles)], axis=1)


def route_polylines(record):
    return [sample_primitive(primitive) for primitive in record['primitives']]


def draw_board(ax, title):
    ax.set_xlim(-2, BOARD + 2)
    ax.set_ylim(-2, BOARD + 2)
    ax.set_aspect('equal')
    ax.set_facecolor('#fbfbfb')
    ax.add_patch(__import__('matplotlib.patches', fromlist=['Rectangle']).Rectangle(
        (0, 0), BOARD, BOARD, fill=False, edgecolor='#222222', linewidth=1.2,
        zorder=10))
    # connector envelopes (16 per side, 12.59 mm wide, 3 mm deep inward)
    from matplotlib.patches import Rectangle
    pitch = 9.0
    width = 12.59
    for index in range(16):
        along = 7.5 + index * pitch
        for side in 'NSEW':
            if side == 'N':
                rect = (along - width / 2, BOARD - 3.0, width, 3.0)
            elif side == 'S':
                rect = (along - width / 2, 0.0, width, 3.0)
            elif side == 'E':
                rect = (BOARD - 3.0, along - width / 2, 3.0, width)
            else:
                rect = (0.0, along - width / 2, 3.0, width)
            ax.add_patch(Rectangle(rect[:2], rect[2], rect[3], facecolor='#ececec',
                                   edgecolor='#bbbbbb', linewidth=0.35, zorder=1))
    ax.set_xlabel('x (mm)')
    ax.set_ylabel('y (mm)')
    ax.set_title(title, fontsize=10)
    ax.set_xticks([0, 25, 50, 75, 100, 125, 150])
    ax.set_yticks([0, 25, 50, 75, 100, 125, 150])


def draw_plane(ax, records, plane, title, only_relation=None, alpha_others=0.28,
               linewidth=0.35):
    draw_board(ax, title)
    for record in records:
        if record.get('status') != 'routed' or record.get('plane') != plane:
            continue
        relation = record['relation']
        if only_relation is not None and relation != only_relation:
            color = '#999999'
            alpha = alpha_others
            width = linewidth * 0.7
        else:
            color = COLORS[relation]
            alpha = 0.85
            width = linewidth
        for points in route_polylines(record):
            ax.plot(points[:, 0], points[:, 1], color=color, linewidth=width,
                    alpha=alpha, solid_capstyle='round', zorder=3)


def legend_handles():
    from matplotlib.lines import Line2D
    return [Line2D([0], [0], color=COLORS[key], lw=2,
                   label=f'{key} ({zh})')
            for key, zh in (('opposite', '对边'), ('adjacent', '邻边'),
                            ('same', '同边 U'))]


def save(fig, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path.with_suffix('.png'), dpi=DPI, bbox_inches='tight')
    fig.savefig(path.with_suffix('.svg'), bbox_inches='tight')
    return path


def plot_all(phase2_dir, log=print):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    phase2_dir = Path(phase2_dir)
    plots_dir = phase2_dir / 'plots'
    plots_dir.mkdir(parents=True, exist_ok=True)
    payload = json.loads((phase2_dir / 'routes_1024.json').read_text(
        encoding='utf-8'))
    records = payload['routes']
    routed = [record for record in records if record.get('status') == 'routed']
    counters = {}
    for plane in ('z1', 'z2'):
        plane_records = [r for r in routed if r['plane'] == plane]
        counters[plane] = {key: sum(1 for r in plane_records
                                    if r['relation'] == key)
                           for key in COLORS}
        counters[plane]['total'] = len(plane_records)

    # 01: both planes side by side, coloured by relation
    fig, axes = plt.subplots(1, 2, figsize=(23, 11.4))
    for ax, plane in zip(axes, ('z1', 'z2')):
        stats = counters[plane]
        draw_plane(ax, records, plane,
                   f'{Z_TITLES[plane]}\n'
                   f'routed {stats["total"]}/512  |  opposite {stats["opposite"]}, '
                   f'adjacent {stats["adjacent"]}, same {stats["same"]}')
    fig.legend(handles=legend_handles(), loc='lower center', ncol=3, fontsize=11)
    fig.suptitle('MANUAL-C4 新连接表：1024 通道二维布线总览'
                 f'（C4 严格对称，routed {len(routed)}/1024）', fontsize=14)
    save(fig, plots_dir / '01_overview_1024')
    plt.close(fig)
    log('[plots2d] 01_overview_1024')

    # 02 / 03: one plane each
    for name, plane in (('02_row1_z1', 'z1'), ('03_row2_z2', 'z2')):
        fig, ax = plt.subplots(figsize=(12.2, 12.2))
        stats = counters[plane]
        draw_plane(ax, records, plane,
                   f'MANUAL-C4 {Z_TITLES[plane]} — routed {stats["total"]}/512\n'
                   f'opposite {stats["opposite"]} / adjacent {stats["adjacent"]} '
                   f'/ same {stats["same"]}')
        fig.legend(handles=legend_handles(), loc='lower right', fontsize=9)
        save(fig, plots_dir / name)
        plt.close(fig)
        log(f'[plots2d] {name}')

    # 04: same-side U turns zoom (N edge), both planes
    fig, axes = plt.subplots(1, 2, figsize=(16, 7.2))
    for ax, plane in zip(axes, ('z1', 'z2')):
        draw_plane(ax, records, plane,
                   f'{Z_TITLES[plane]} — N 边区同边 U 形连接局部放大',
                   only_relation='same')
        ax.set_xlim(38, 96)
        ax.set_ylim(122, 151)
    fig.suptitle('同边 U 形连接局部放大（红色 = 同边；灰色 = 其他连接）', fontsize=13)
    save(fig, plots_dir / '04_same_side_u_zoom')
    plt.close(fig)
    log('[plots2d] 04_same_side_u_zoom')

    manifest = dict(phase2_dir=str(phase2_dir), plots_dir=str(plots_dir),
                    routed=len(routed), total=len(records),
                    counters=counters)
    (plots_dir / 'plots_manifest.json').write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False), encoding='utf-8')
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase2-dir', type=Path, default=None)
    args = parser.parse_args(argv)
    repo = Path(__file__).resolve().parents[2]
    phase2_dir = args.phase2_dir or (repo / 'outputs/manual_c4_new_connectivity/phase2_2d')
    manifest = plot_all(phase2_dir)
    print(json.dumps({key: manifest[key] for key in ('routed', 'total')},
                     ensure_ascii=False))
    return manifest


if __name__ == '__main__':
    main()
