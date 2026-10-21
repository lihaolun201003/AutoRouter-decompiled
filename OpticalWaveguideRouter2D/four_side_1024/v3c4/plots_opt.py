"""Plotting utilities for the V3-C4 optimization round (PNG + SVG).

All figures are generated from *saved* route geometry; no fictitious layer is ever
drawn: a layer panel with zero routes is annotated as empty instead.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

BOARD = 150.0
CONNECTOR_PITCH = 9.0
FIRST_CENTER = 7.5
COLUMNS = 16
COL_PITCH = 0.25

PLANE_COLORS = {'z1': '#1f6fd6', 'z2': '#e07b1a'}
LAYER_COLORS = {1: '#333333', 2: '#2f9e44', 3: '#7048e8', 4: '#e03131', 5: '#0c8599'}
FAILED_COLOR = '#c00000'


# ---------------------------------------------------------------------------
# primitive sampling
# ---------------------------------------------------------------------------
def sample_primitive(primitive, step_deg=6.0):
    if primitive['kind'] == 'line':
        return np.array([primitive['p0'], primitive['p1']], dtype=float)
    center = np.asarray(primitive['center'], dtype=float)
    radius = float(primitive['radius'])
    start = float(primitive['start_angle'])
    sweep = float(primitive['sweep'])
    count = max(6, int(abs(math.degrees(sweep)) / step_deg) + 1)
    angles = start + np.linspace(0.0, sweep, count)
    return np.stack([center[0] + radius * np.cos(angles),
                     center[1] + radius * np.sin(angles)], axis=1)


def sample_flat_primitives(primitives):
    chunks = [sample_primitive(primitive) for primitive in primitives]
    if not chunks:
        return np.zeros((0, 2))
    return np.concatenate(chunks, axis=0)


def transition_points(part, samples=24):
    """Sample one S-shaped vertical transition in true XYZ (SCHEMA_L3D formula)."""
    dz = float(part['z1']) - float(part['z0'])
    radius = float(part['radius_mm'])
    theta = math.acos(max(-1.0, min(1.0, 1.0 - abs(dz) / (2.0 * radius))))
    footprint = 2.0 * radius * math.sin(theta)
    start = np.asarray(part['start'], dtype=float)
    direction = np.asarray(part['direction'], dtype=float)
    direction = direction / np.linalg.norm(direction)
    sign = 1.0 if dz >= 0 else -1.0
    points = []
    half = samples // 2
    us = np.linspace(0.0, footprint / 2.0, half)
    for u in us:
        phi = math.asin(min(1.0, max(-1.0, u / radius)))
        w = float(part['z0']) + sign * radius * (1.0 - math.cos(phi))
        points.append((start + direction * u, w))
    inverse = []
    for u, w in reversed(points):
        xy = start + direction * footprint - direction * u
        inverse.append((xy, float(part['z1']) + float(part['z0']) - w))
    all_points = points + inverse
    xy = np.stack([p[0] for p in all_points])
    z = np.array([p[1] for p in all_points])
    return xy, z


# ---------------------------------------------------------------------------
# board decorations
# ---------------------------------------------------------------------------
def draw_board(ax, connector_labels=True, grid=True):
    ax.add_patch(Rectangle((0, 0), BOARD, BOARD, fill=False, linewidth=1.2,
                           edgecolor='black'))
    if grid:
        for value in range(0, 151, 10):
            ax.plot([value, value], [0, BOARD], color='#dddddd', linewidth=0.4,
                    zorder=0)
            ax.plot([0, BOARD], [value, value], color='#dddddd', linewidth=0.4,
                    zorder=0)
    if connector_labels:
        for side in 'NSEW':
            for index in range(1, 17):
                center = FIRST_CENTER + (index - 1) * CONNECTOR_PITCH
                if side in 'NS':
                    x = center
                    y = BOARD if side == 'N' else 0.0
                    ax.add_patch(Rectangle((x - 6.295, y), 12.59, 2.2,
                                           facecolor='#c8c8c8',
                                           edgecolor='#555555',
                                           linewidth=0.3, zorder=1))
                    ax.text(x, y + (2.8 if side == 'N' else -2.8), f'{side}{index:02d}',
                            ha='center', va='center', fontsize=3.2)
                else:
                    x = BOARD if side == 'E' else 0.0
                    y = center
                    ax.add_patch(Rectangle((x, y - 6.295), 2.2, 12.59,
                                           facecolor='#c8c8c8',
                                           edgecolor='#555555',
                                           linewidth=0.3, zorder=1))
                    ax.text(x + (3.2 if side == 'E' else -3.2), y, f'{side}{index:02d}',
                            ha='center', va='center', fontsize=3.2)
    ax.set_xlim(-9, BOARD + 9)
    ax.set_ylim(-9, BOARD + 9)
    ax.set_aspect('equal')
    ax.set_xlabel('x (mm)')
    ax.set_ylabel('y (mm)')


def draw_port_ticks(ax, endpoints, color='#555555'):
    for _eid, ep in endpoints.items():
        x, y = ep['routing_xy']
        ax.plot([x], [y], marker='.', markersize=0.8, color=color, zorder=2)


def draw_route_2d(ax, record, color, linewidth=0.7, alpha=0.85, zorder=3,
                  primitives_key='primitives'):
    primitives = record.get(primitives_key)
    if not primitives:
        return
    for primitive in primitives:
        points = sample_primitive(primitive)
        ax.plot(points[:, 0], points[:, 1], color=color, linewidth=linewidth,
                alpha=alpha, zorder=zorder, solid_capstyle='round')


def draw_route_3d(ax, record, linewidth=0.6, alpha=0.8):
    for part in record.get('parts') or []:
        if part['kind'] == 'flat':
            points = sample_flat_primitives(part['primitives'])
            if len(points) == 0:
                continue
            z = np.full(len(points), float(part['z_mm']))
            ax.plot(points[:, 0], points[:, 1], z,
                    color=LAYER_COLORS.get(int(part['layer_id']), '#333333'),
                    linewidth=linewidth, alpha=alpha, solid_capstyle='round')
        else:
            xy, z = transition_points(part)
            ax.plot(xy[:, 0], xy[:, 1], z, color=LAYER_COLORS.get(
                int(part.get('from_layer', 1)), '#888888'), linewidth=linewidth,
                alpha=alpha)


# ---------------------------------------------------------------------------
# figures
# ---------------------------------------------------------------------------
def _save(fig, path_png):
    path_png = Path(path_png)
    path_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path_png, dpi=220, bbox_inches='tight')
    fig.savefig(path_png.with_suffix('.svg'), bbox_inches='tight')
    plt.close(fig)


def plot_overview(records, endpoints_by_plane, routed_count, title, path_png,
                  failed_groups=None, show_failed=True):
    fig, ax = plt.subplots(figsize=(11, 11))
    draw_board(ax)
    for plane in ('z1', 'z2'):
        for record in records:
            if record.get('status') != 'routed' or record.get('plane') != plane:
                continue
            draw_route_2d(ax, record, PLANE_COLORS[plane], linewidth=0.55,
                          alpha=0.75)
    if show_failed and failed_groups:
        for entry in failed_groups:
            x1, y1 = entry['source_xy']
            x2, y2 = entry['target_xy']
            ax.plot([x1, x2], [y1, y2], color=FAILED_COLOR, linewidth=0.6,
                    linestyle=(0, (2, 2)), alpha=0.9, zorder=4)
            ax.text((x1 + x2) / 2, (y1 + y2) / 2, f"G{entry['group_id']}",
                    fontsize=4.0, color=FAILED_COLOR, ha='center', va='center',
                    zorder=5)
    ax.plot([], [], color=PLANE_COLORS['z1'], linewidth=1.5,
            label=f"row1 / z1 (routed {sum(1 for r in records if r.get('status') == 'routed' and r.get('plane') == 'z1')})")
    ax.plot([], [], color=PLANE_COLORS['z2'], linewidth=1.5,
            label=f"row2 / z2 (routed {sum(1 for r in records if r.get('status') == 'routed' and r.get('plane') == 'z2')})")
    if show_failed and failed_groups:
        ax.plot([], [], color=FAILED_COLOR, linestyle=(0, (2, 2)), linewidth=1.2,
                label=f'failed C4 groups ({len(failed_groups)})')
    ax.legend(loc='upper right', fontsize=7, framealpha=0.9)
    ax.set_title(f'{title}\n成功通道数 routed = {routed_count} / 1024  |  '
                 f'strict C4  |  150 x 150 mm', fontsize=12)
    _save(fig, path_png)


def plot_by_row(records, routed_z1, routed_z2, title, path_png):
    fig, axes = plt.subplots(1, 2, figsize=(20, 10.5))
    for ax, plane in zip(axes, ('z1', 'z2')):
        draw_board(ax)
        for record in records:
            if record.get('status') != 'routed' or record.get('plane') != plane:
                continue
            draw_route_2d(ax, record, PLANE_COLORS[plane], linewidth=0.6,
                          alpha=0.8)
        counted = routed_z1 if plane == 'z1' else routed_z2
        ax.set_title(f'{plane} ({"row1 对边" if plane == "z1" else "row2 邻边"})'
                     f'  routed = {counted} / 512', fontsize=11)
    fig.suptitle(title, fontsize=13)
    _save(fig, path_png)


def plot_layers(records_3d, routed_count, title, path_png):
    fig, axes = plt.subplots(2, 3, figsize=(19, 12.6))
    axes = axes.ravel()
    for layer_id in range(1, 6):
        ax = axes[layer_id - 1]
        draw_board(ax, connector_labels=False, grid=True)
        layer_total = 0
        for record in records_3d:
            if record.get('status') != 'routed':
                continue
            for part in record.get('parts') or []:
                if part['kind'] != 'flat' or int(part['layer_id']) != layer_id:
                    continue
                points = sample_flat_primitives(part['primitives'])
                if len(points) == 0:
                    continue
                layer_total += 1
                if layer_id == 1:
                    color = PLANE_COLORS.get(record.get('plane'), '#333333')
                else:
                    color = LAYER_COLORS[layer_id]
                ax.plot(points[:, 0], points[:, 1], color=color, linewidth=0.5,
                        alpha=0.75, solid_capstyle='round')
        label = 'L1 (interface, row1 z=0 + row2 z=0.5)' if layer_id == 1 else \
            f'L{layer_id} (routing layer)'
        if layer_total == 0:
            ax.text(BOARD / 2, BOARD / 2, '本层无已布线路\n(no routed geometry on this layer)',
                    ha='center', va='center', fontsize=11, color='#888888')
        ax.set_title(f'{label}\nflat parts = {layer_total}', fontsize=10)
    axes[5].axis('off')
    axes[5].text(0.02, 0.95, '说明 / note:\n\n'
                 f'- 总成功通道数 routed = {routed_count} / 1024\n'
                 '- L2–L5 只在真实抬升路线使用后才会出现几何；\n'
                 '  没有使用则明确标注“本层无已布线路”，不画虚构路线。\n'
                 '- 层高：L1 row1 z=0.0, row2 z=0.5；\n'
                 '  L2–L5 = 1.0/1.5/2.0/2.5 mm (exploratory, unconfirmed).',
                 fontsize=9, va='top')
    fig.suptitle(title, fontsize=13)
    _save(fig, path_png)


def plot_3d(records_3d, routed_count, title, path_png):
    fig = plt.figure(figsize=(13, 12))
    ax = fig.add_subplot(111, projection='3d')
    for record in records_3d:
        if record.get('status') != 'routed':
            continue
        draw_route_3d(ax, record)
    ax.set_xlim(0, BOARD)
    ax.set_ylim(0, BOARD)
    ax.set_zlim(-0.1, 2.7)
    ax.set_xlabel('x (mm)')
    ax.set_ylabel('y (mm)')
    ax.set_zlabel('z (mm)')
    ax.view_init(elev=32, azim=-58)
    for layer_id, color in LAYER_COLORS.items():
        ax.plot([], [], [], color=color, linewidth=2,
                label=('L1 (rows z=0 / 0.5)' if layer_id == 1
                       else f'L{layer_id} (z={ {2: 1.0, 3: 1.5, 4: 2.0, 5: 2.5}[layer_id] } mm)'))
    ax.legend(loc='upper left', fontsize=7)
    ax.set_title(f'{title}\n真实 XYZ 布线 | 成功通道数 = {routed_count} / 1024', fontsize=11)
    _save(fig, path_png)


def plot_failed(records, failed_groups, routed_count, title, path_png):
    fig, ax = plt.subplots(figsize=(11, 11))
    draw_board(ax)
    for record in records:
        if record.get('status') != 'routed':
            continue
        draw_route_2d(ax, record, '#9a9a9a', linewidth=0.35, alpha=0.45)
    for entry in failed_groups:
        x1, y1 = entry['source_xy']
        x2, y2 = entry['target_xy']
        plane = entry.get('plane', 'z2')
        ax.plot([x1, x2], [y1, y2], color=FAILED_COLOR if plane == 'z2' else '#7048e8',
                linewidth=0.9, linestyle=(0, (3, 2)), zorder=5)
        ax.plot([x1, x2], [y1, y2], marker='x', markersize=3,
                color=FAILED_COLOR if plane == 'z2' else '#7048e8', zorder=5)
        ax.text((x1 + x2) / 2, (y1 + y2) / 2,
                f"G{entry['group_id']}({plane})", fontsize=4.5,
                color=FAILED_COLOR if plane == 'z2' else '#7048e8',
                ha='center', va='center', zorder=6,
                bbox=dict(boxstyle='round,pad=0.1', fc='white', ec='none', alpha=0.6))
    ax.set_title(f'{title}\n失败四元组 = {len(failed_groups)} 组 / {4 * len(failed_groups)} 条 '
                 f'（routed = {routed_count} / 1024；灰色 = 已布线路）', fontsize=11)
    _save(fig, path_png)


# ---------------------------------------------------------------------------
# data helpers
# ---------------------------------------------------------------------------
def load_plane_records(root, plane):
    payload = json.loads((Path(root) / 'c4_2d' / plane / 'routes.json')
                         .read_text(encoding='utf-8'))
    return payload


def load_3d_records(root, default_plane_payloads):
    """Use routes_l3d.json when it exists (it contains both planes), else build
    a flat-L1 3D record set from the 2D payloads."""
    path = Path(root) / 'c4_l3d' / 'routes_l3d.json'
    if path.exists():
        payload = json.loads(path.read_text(encoding='utf-8'))
        return payload['routes']
    records = []
    for plane, payload in default_plane_payloads.items():
        for record in payload['routes']:
            if record.get('status') != 'routed':
                continue
            parts = [dict(kind='flat', layer_id=1,
                          z_mm=0.0 if plane == 'z1' else 0.5,
                          length_mm=record.get('length_mm'),
                          primitives=record['primitives'])]
            records.append(dict(route_id=int(record['route_id']), plane=plane,
                                status='routed', parts=parts,
                                layer_sequence=[1], n_transitions=0,
                                lifted=False))
    return records


def failed_group_entries(payloads, groups_all):
    """World-space failed group descriptors for the failure map."""
    entries = []
    for plane, payload in payloads.items():
        routed = {int(r['route_id']): r for r in payload['routes']
                  if r.get('status') == 'routed'}
        for group in groups_all:
            if group['plane'] != plane:
                continue
            if all(rid in routed for rid in group['route_ids']):
                continue
            rep = group['route_ids'][0]
            # endpoints are needed: take them from the V3 connectivity identity
            from four_side_1024.v3c4 import inputs as V3
            route = V3.load_all_routes()[0][rep - 1]
            if int(route['route_id']) != rep:
                route = next(r for r in V3.load_all_routes()[0]
                             if int(r['route_id']) == rep)
            sx, sy = V3.port_xy(route['source_endpoint'])
            tx, ty = V3.port_xy(route['target_endpoint'])
            entries.append(dict(group_id=group['group_id'], plane=plane,
                                kind=group['kind'],
                                source_xy=(sx, sy), target_xy=(tx, ty),
                                route_ids=group['route_ids']))
    return entries
