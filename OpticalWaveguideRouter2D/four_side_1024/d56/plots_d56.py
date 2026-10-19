"""Figures, SVG export and ablation bars for the D56 optimized-run pipeline.

Conventions:
- English-only labels (the host lacks CJK fonts), matplotlib Agg, dpi = 200.
- Coordinates are millimetres on the 150 x 150 mm board, origin lower-left.
- Board-wide figures use ``aspect='equal'`` with axis limits slightly outside the
  board so the out-of-board connector envelopes remain visible.
- Nothing in this module decides geometric legality; legality is recomputed from
  the exact primitives in ``outputs_d56.py`` and independently re-checked by
  ``four_side_1024/d56/validate_d56.py`` when that validator exists.
"""
from __future__ import annotations

import math
from collections import Counter

import numpy as np

from ..geometry import sample
from ..outputs import COLORS

BOARD_MM = 150.0
DPI = 200
PAIR_ORDER = ('NS', 'EW', 'EN', 'ES', 'SW', 'NW')
RELATION_PAIRS = {'opposite': ('NS', 'EW'), 'adjacent': ('EN', 'ES', 'SW', 'NW')}
DEFAULT_PAD_MM = 9.0


# --------------------------------------------------------------------------- #
# small shared helpers
# --------------------------------------------------------------------------- #
def pyplot():
    """Import matplotlib lazily and force the headless Agg backend."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    return plt


def sample_curves(routed, sagitta_mm):
    """Chordal display polylines for every exportable routed record."""
    curves = {}
    for record in routed:
        primitives = record.get('primitives') or []
        if not primitives:
            continue
        curves[record['route_id']] = sample(primitives, sagitta_mm)
    return curves


def curve_bboxes(curves):
    boxes = {}
    for route_id, points in curves.items():
        if len(points) == 0:
            continue
        boxes[route_id] = (float(points[:, 0].min()), float(points[:, 1].min()),
                           float(points[:, 0].max()), float(points[:, 1].max()))
    return boxes


def crossing_cell_counts(crossings, grid_mm=5.0):
    """5 x 5 mm crossing counts keyed by (lower-left x, lower-left y)."""
    cells = max(1, int(math.ceil(BOARD_MM / grid_mm)))
    counts = Counter()
    for crossing in crossings:
        ix = int(math.floor(float(crossing['x_mm']) / grid_mm))
        iy = int(math.floor(float(crossing['y_mm']) / grid_mm))
        counts[(min(cells - 1, max(0, ix)) * int(grid_mm),
                min(cells - 1, max(0, iy)) * int(grid_mm))] += 1
    return counts


def densest_crossing_cells(crossings, grid_mm=5.0, limit=20):
    counts = crossing_cell_counts(crossings, grid_mm)
    return [dict(x_min_mm=int(x), y_min_mm=int(y), count=int(count))
            for (x, y), count in counts.most_common(limit)]


def _board_frame(ax, pad_mm=DEFAULT_PAD_MM):
    from matplotlib.patches import Rectangle
    ax.add_patch(Rectangle((0.0, 0.0), BOARD_MM, BOARD_MM, fill=False,
                           edgecolor='#111111', linewidth=1.2, zorder=6))
    ax.set_xlim(-pad_mm, BOARD_MM + pad_mm)
    ax.set_ylim(-pad_mm, BOARD_MM + pad_mm)
    ax.set_aspect('equal')
    ax.set_xlabel('x (mm)')
    ax.set_ylabel('y (mm)')


def draw_connectors(ax, connectors, depth_mm=3.0, label_fontsize=5.0):
    """Draw the provisional MPO connector envelope blocks outside the board."""
    from matplotlib.patches import Rectangle
    for connector in connectors:
        x, y = (float(v) for v in connector['center_xy'])
        side = connector['side']
        width = float(connector.get('envelope_width_mm', 12.59))
        if side in ('N', 'S'):
            base = y if side == 'N' else -depth_mm
            ax.add_patch(Rectangle((x - width / 2.0, base), width, depth_mm,
                                   facecolor='#bbbbbb', edgecolor='#333333',
                                   linewidth=0.3, zorder=5))
            ax.text(x, y + (4.2 if side == 'N' else -4.2), connector['connector'],
                    ha='center', va='bottom' if side == 'N' else 'top',
                    fontsize=label_fontsize, zorder=7)
        else:
            base = x if side == 'E' else -depth_mm
            ax.add_patch(Rectangle((base, y - width / 2.0), depth_mm, width,
                                   facecolor='#bbbbbb', edgecolor='#333333',
                                   linewidth=0.3, zorder=5))
            ax.text(x + (4.2 if side == 'E' else -4.2), y, connector['connector'],
                    ha='left' if side == 'E' else 'right', va='center',
                    fontsize=label_fontsize, zorder=7)


def _pair_legend(ax, pairs, fontsize=7.0):
    from matplotlib.lines import Line2D
    handles = [Line2D([0], [0], color=COLORS[pair], linewidth=1.4, label=pair)
               for pair in PAIR_ORDER if pair in pairs]
    if handles:
        ax.legend(handles=handles, loc='upper left', ncol=len(handles),
                  fontsize=fontsize, framealpha=0.85)


def _save(fig, output_path):
    fig.tight_layout()
    fig.savefig(output_path, dpi=DPI)
    pyplot().close(fig)


# --------------------------------------------------------------------------- #
# 01 - raw connectivity
# --------------------------------------------------------------------------- #
def plot_connectivity(rows, endpoints, connectors, output_path):
    """Straight-line picture of all original CSV connections (inputs.phase1 style)."""
    plt = pyplot()
    from matplotlib.collections import LineCollection
    segments = [[endpoints[row['source_endpoint']]['routing_xy'],
                 endpoints[row['target_endpoint']]['routing_xy']] for row in rows]
    colors = [COLORS[row['pair']] for row in rows]
    fig, ax = plt.subplots(figsize=(11.0, 11.0))
    if segments:
        ax.add_collection(LineCollection(segments, colors=colors, linewidths=0.35,
                                         alpha=0.45, zorder=2))
    _board_frame(ax)
    draw_connectors(ax, connectors)
    ax.set_title(f'{len(rows)} original CSV connections | 64 connectors | '
                 f'2048 port identities\nvirtual_unfolded endpoints | 150 x 150 mm '
                 f'board | D56 routing layer = 0', fontsize=10)
    _save(fig, output_path)
    return dict(file=str(output_path), connections=len(rows))


# --------------------------------------------------------------------------- #
# 02/03/04 - routed geometry subsets
# --------------------------------------------------------------------------- #
def plot_routes(curves, meta, route_ids, connectors, output_path, title, subtitle,
                show_legend=True):
    plt = pyplot()
    from matplotlib.collections import LineCollection
    ids = [route_id for route_id in route_ids if route_id in curves]
    fig, ax = plt.subplots(figsize=(11.0, 10.0))
    if ids:
        segments = [curves[route_id] for route_id in ids]
        colors = [COLORS[meta[route_id]['pair']] for route_id in ids]
        ax.add_collection(LineCollection(segments, colors=colors,
                                         linewidths=0.55 if len(ids) <= 128 else 0.4,
                                         alpha=0.85, zorder=3))
    _board_frame(ax)
    draw_connectors(ax, connectors)
    if show_legend:
        _pair_legend(ax, {meta[route_id]['pair'] for route_id in ids})
    ax.set_title(title + '\n' + subtitle, fontsize=10)
    _save(fig, output_path)
    return dict(file=str(output_path), routes=len(ids))


# --------------------------------------------------------------------------- #
# 05 - crossing heatmap
# --------------------------------------------------------------------------- #
def plot_heatmap(crossings, routed_count, total_count, output_path, grid_mm=5.0):
    plt = pyplot()
    from matplotlib.patches import Rectangle
    cells = int(round(BOARD_MM / grid_mm))
    counts = np.zeros((cells, cells), dtype=int)
    for crossing in crossings:
        ix = int(math.floor(float(crossing['x_mm']) / grid_mm))
        iy = int(math.floor(float(crossing['y_mm']) / grid_mm))
        counts[min(cells - 1, max(0, iy)), min(cells - 1, max(0, ix))] += 1
    fig, ax = plt.subplots(figsize=(10.0, 9.0))
    image = ax.imshow(counts, origin='lower', extent=(0.0, BOARD_MM, 0.0, BOARD_MM),
                      cmap='magma', interpolation='nearest')
    bar = fig.colorbar(image, ax=ax)
    bar.set_label(f'Exact centerline crossings per {grid_mm:g} x {grid_mm:g} mm cell')
    top = densest_crossing_cells(crossings, grid_mm, limit=3)
    for rank, cell in enumerate(top, start=1):
        x0, y0 = cell['x_min_mm'], cell['y_min_mm']
        ax.add_patch(Rectangle((x0, y0), grid_mm, grid_mm, fill=False,
                               edgecolor='#7CFC00', linewidth=1.4, zorder=4))
        ax.annotate(f"{cell['count']} ({x0},{y0})",
                    xy=(x0 + grid_mm / 2.0, y0 + grid_mm / 2.0),
                    ha='center', va='center', fontsize=7, color='white',
                    bbox=dict(boxstyle='round,pad=0.2', facecolor='#111111', alpha=0.75),
                    zorder=5)
    ax.set(xlabel='x (mm)', ylabel='y (mm)',
           title=f'D56 crossing density: {len(crossings)} exact intersections | '
                 f'{routed_count}/{total_count} routed\nlayer = 0 single plane | '
                 f'crossings are recorded 2D crossings, not certified optical crossings')
    _save(fig, output_path)
    return dict(file=str(output_path), cells=cells, densest_cells=top)


# --------------------------------------------------------------------------- #
# 06 - hotspot detail panels
# --------------------------------------------------------------------------- #
def _detail_windows(crossings, densest_cells, count, half_mm):
    windows = []
    for cell in densest_cells:
        cx = cell['x_min_mm'] + 2.5
        cy = cell['y_min_mm'] + 2.5
        windows.append((cx, cy, cell['count']))
        if len(windows) >= count:
            break
    if len(windows) < count:
        fallbacks = [(37.5, 37.5, 0), (112.5, 37.5, 0), (37.5, 112.5, 0), (112.5, 112.5, 0)]
        for cx, cy, count_value in fallbacks:
            if len(windows) >= count:
                break
            if all(math.hypot(cx - x, cy - y) > 2 * half_mm for x, y, _ in windows):
                windows.append((cx, cy, count_value))
    return windows[:count]


def plot_detail(curves, meta, crossings, output_path, routed_count, total_count,
                densest_cells, count=4, half_mm=12.5):
    plt = pyplot()
    from matplotlib.collections import LineCollection
    from matplotlib.patches import Rectangle
    boxes = curve_bboxes(curves)
    windows = _detail_windows(crossings, densest_cells, count, half_mm)
    columns = 2
    rows = max(1, int(math.ceil(len(windows) / columns)))
    fig, axes = plt.subplots(rows, columns, figsize=(13.0, 6.2 * rows), squeeze=False)
    for index, (cx, cy, count_value) in enumerate(windows):
        ax = axes[index // columns][index % columns]
        x_lo = max(-4.0, cx - half_mm)
        x_hi = min(BOARD_MM + 4.0, cx + half_mm)
        y_lo = max(-4.0, cy - half_mm)
        y_hi = min(BOARD_MM + 4.0, cy + half_mm)
        ids = [route_id for route_id, box in boxes.items()
               if box[2] >= x_lo and box[0] <= x_hi and box[3] >= y_lo and box[1] <= y_hi]
        segments = [curves[route_id] for route_id in ids]
        colors = [COLORS[meta[route_id]['pair']] for route_id in ids]
        if segments:
            ax.add_collection(LineCollection(segments, colors=colors, linewidths=0.6,
                                             alpha=0.85, zorder=3))
        ax.add_patch(Rectangle((0.0, 0.0), BOARD_MM, BOARD_MM, fill=False,
                               edgecolor='#111111', linewidth=0.8, zorder=6))
        local = [c for c in crossings
                 if x_lo <= c['x_mm'] <= x_hi and y_lo <= c['y_mm'] <= y_hi]
        if local:
            ax.plot([c['x_mm'] for c in local], [c['y_mm'] for c in local],
                    'o', ms=3.5, color='#e02020', alpha=0.9, zorder=4,
                    label=f'{len(local)} crossings')
            ax.legend(loc='lower right', fontsize=6.5, framealpha=0.85)
        ax.set_xlim(x_lo, x_hi)
        ax.set_ylim(y_lo, y_hi)
        ax.set_aspect('equal')
        ax.grid(alpha=0.25, linewidth=0.4)
        ax.set_xlabel('x (mm)')
        ax.set_ylabel('y (mm)')
        ax.set_title(f'Hotspot {index + 1}: densest 5 x 5 mm cell has {count_value} crossings\n'
                     f'window x in [{x_lo:.1f}, {x_hi:.1f}] mm, '
                     f'y in [{y_lo:.1f}, {y_hi:.1f}] mm | {len(ids)} routes shown',
                     fontsize=8.5)
    for empty in range(len(windows), rows * columns):
        axes[empty // columns][empty % columns].axis('off')
    fig.suptitle(f'Routing detail: {len(windows)} densest crossing hotspots | '
                 f'{routed_count}/{total_count} routed | {len(crossings)} crossings | '
                 f'layer = 0', fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return dict(file=str(output_path), hotspots=len(windows),
                windows=[[round(w[0], 3), round(w[1], 3), int(w[2])] for w in windows])


# --------------------------------------------------------------------------- #
# 07 - strategy / ablation comparison
# --------------------------------------------------------------------------- #
def _first(record, keys, default=None):
    for key in keys:
        if key in record and record[key] is not None:
            return record[key]
    return default


def plot_strategy(ablations, statistics, output_path):
    plt = pyplot()
    total = int(statistics.get('total_connections', 1024))
    if ablations:
        labels, success, crossings, runtimes = [], [], [], []
        relations = []
        for index, item in enumerate(ablations):
            labels.append(str(_first(item, ('label', 'name', 'strategy', 'id'),
                                     default=f'ablation {index + 1}')))
            good = int(_first(item, ('success_count', 'success', 'routed',
                                     'routed_count', 'routed_total'), default=0) or 0)
            success.append(good)
            crossings.append(int(_first(item, ('crossing_count', 'crossings',
                                               'crossing_total', 'crossing'),
                                      default=0) or 0))
            runtime = _first(item, ('runtime_seconds', 'runtime', 'seconds'))
            runtimes.append(float(runtime) if runtime is not None else None)
            by_relation = item.get('by_relation') or {}
            opposite = 0
            adjacent = 0
            if isinstance(by_relation, dict):
                for key, target in (('opposite', 'opposite'), ('adjacent', 'adjacent')):
                    entry = by_relation.get(key)
                    if isinstance(entry, dict):
                        value = int(entry.get('success', 0) or 0)
                    elif isinstance(entry, (int, float)):
                        value = int(entry)
                    else:
                        value = 0
                    if target == 'opposite':
                        opposite = value
                    else:
                        adjacent = value
            relations.append((opposite, adjacent, max(0, good - opposite - adjacent)))
        positions = np.arange(len(labels))
        fig, axes = plt.subplots(1, 3, figsize=(15.0, 5.0))
        # Left: routed count of the total.
        bars = axes[0].bar(positions, success, color='#3366bb', alpha=0.88)
        axes[0].bar_label(bars, fmt='%d', fontsize=7.5)
        axes[0].set_title(f'Routed count (of {total})', fontsize=9)
        # Middle: opposite / adjacent relation split.
        opposite = [relation[0] for relation in relations]
        adjacent = [relation[1] for relation in relations]
        other = [relation[2] for relation in relations]
        axes[1].bar(positions, opposite, color='#3366bb', alpha=0.9, label='opposite')
        axes[1].bar(positions, adjacent, bottom=opposite, color='#00a0a0', alpha=0.9,
                    label='adjacent')
        if any(value > 0 for value in other):
            base = [left + right for left, right in zip(opposite, adjacent)]
            axes[1].bar(positions, other, bottom=base, color='#777777', alpha=0.7,
                        label='other/unclassified')
        for position, opposite_value, adjacent_value in zip(positions, opposite, adjacent):
            axes[1].text(position, opposite_value + adjacent_value + 4,
                         f'{opposite_value}/{adjacent_value}', ha='center', fontsize=7)
        axes[1].set_title('Routed count by relation (opposite/adjacent)', fontsize=9)
        axes[1].legend(fontsize=7.5)
        # Right: exact crossing count, falling back to runtime when unavailable.
        if any(crossings):
            bars = axes[2].bar(positions, crossings, color='#e3a323', alpha=0.9)
            axes[2].bar_label(bars, fmt='%d', fontsize=7.5)
            axes[2].set_title('Exact 2D crossings', fontsize=9)
        else:
            values = [runtime if runtime is not None else 0.0 for runtime in runtimes]
            bars = axes[2].bar(positions, values, color='#a545b0', alpha=0.9)
            axes[2].bar_label(bars, fmt='%.1f', fontsize=7.5)
            axes[2].set_title('Runtime (s)', fontsize=9)
        for axis in axes:
            axis.set_xticks(positions)
            axis.set_xticklabels(labels, rotation=20, ha='right', fontsize=7)
            axis.grid(axis='y', alpha=0.25, linewidth=0.4)
        fig.suptitle(f'D56 strategy / ablation comparison | {len(ablations)} configurations | '
                     f'all bars from ablation table (total {total} connections)', fontsize=11)
        fig.tight_layout(rect=(0, 0, 1, 0.94))
        fig.savefig(output_path, dpi=DPI)
        plt.close(fig)
        return dict(file=str(output_path), mode='ablations', configurations=len(ablations))

    # No ablation table in this run: still show the current-run key metrics so the
    # required deliverable is complete and the interface is explicit.
    by_pair = statistics.get('by_pair') or {}
    by_relation = statistics.get('by_relation') or {}
    pairs = [pair for pair in PAIR_ORDER if pair in by_pair]
    fig, axes = plt.subplots(1, 2, figsize=(13.0, 5.0))
    positions = np.arange(len(pairs))
    success = [int(by_pair[pair].get('success', 0)) for pair in pairs]
    failed = [int(by_pair[pair].get('failed', 0)) for pair in pairs]
    axes[0].bar(positions, success, color='#3366bb', alpha=0.9, label='routed')
    axes[0].bar(positions, failed, bottom=success, color='#b84040', alpha=0.55, label='failed')
    for position, good, bad in zip(positions, success, failed):
        axes[0].text(position, good + bad + 4, f'{good}', ha='center', fontsize=7.5)
    axes[0].set_xticks(positions)
    axes[0].set_xticklabels(pairs)
    axes[0].set_ylabel('connections')
    axes[0].set_title('Connections per side pair', fontsize=9)
    axes[0].legend(fontsize=7.5)
    axes[0].grid(axis='y', alpha=0.25, linewidth=0.4)
    relations = [relation for relation in ('opposite', 'adjacent') if relation in by_relation]
    relation_positions = np.arange(len(relations))
    good = [int(by_relation[relation].get('success', 0)) for relation in relations]
    bad = [int(by_relation[relation].get('failed', 0)) for relation in relations]
    axes[1].bar(relation_positions, good, color='#3366bb', alpha=0.9, label='routed')
    axes[1].bar(relation_positions, bad, bottom=good, color='#b84040', alpha=0.55,
                label='failed')
    for position, value, other in zip(relation_positions, good, bad):
        axes[1].text(position, value + other + 4, f'{value}/{value + other}',
                     ha='center', fontsize=8)
    axes[1].set_xticks(relation_positions)
    axes[1].set_xticklabels(relations)
    axes[1].set_title('Opposite vs adjacent relation', fontsize=9)
    axes[1].legend(fontsize=7.5)
    axes[1].grid(axis='y', alpha=0.25, linewidth=0.4)
    fig.suptitle(f'Current-run key metrics | {statistics.get("success_count", 0)}/'
                 f'{total} routed | {statistics.get("crossing_count", 0)} crossings\n'
                 'No ablation table was supplied (algorithm.ablations / ablations.json absent); '
                 'this figure shows current-run metrics only', fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return dict(file=str(output_path), mode='current_run_metrics', configurations=0)


# --------------------------------------------------------------------------- #
# SVG - routes only, board frame, sampled arcs
# --------------------------------------------------------------------------- #
def _svg_path(points):
    flipped = np.column_stack((points[:, 0], BOARD_MM - points[:, 1]))
    return 'M' + 'L'.join(f'{x:.2f} {y:.2f}' for x, y in flipped)


def write_svg(routed, output_path, sagitta_mm=0.01, max_bytes=5 * 1024 * 1024):
    """Write a compact hand-built SVG (polylines sampled from exact primitives).

    ``routed`` records need ``route_id``, ``pair`` and ``primitives``.  The SVG
    is pure presentation: arcs are chordal polylines and no legality claim is
    encoded here.  If the first sampling exceeds ``max_bytes`` the sampling is
    refined coarser once, keeping the file well under the 5 MB requirement.
    """
    selected = {}
    used_sagitta = float(sagitta_mm)
    payload = ''
    for attempt in range(2):
        used_sagitta = float(sagitta_mm) * (5.0 ** attempt)
        groups = {pair: [] for pair in PAIR_ORDER}
        for record in sorted(routed, key=lambda r: r['route_id']):
            primitives = record.get('primitives') or []
            if not primitives:
                continue
            points = np.asarray(sample(primitives, used_sagitta), dtype=float)
            if len(points) < 2:
                continue
            groups.setdefault(record['pair'], []).append(_svg_path(points))
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
            'width="900" height="900" viewBox="-6 -6 162 162">',
            f'<title>D56 single-layer routing: {len(routed)} routes on a 150 x 150 mm board</title>',
            '<desc>Research geometry, layer = 0, virtual_unfolded endpoints. '
            f'Arc polylines sampled with sagitta &lt;= {used_sagitta:g} mm; '
            'not a fabrication release.</desc>',
            '<rect x="0" y="0" width="150" height="150" fill="none" '
            'stroke="#111111" stroke-width="0.2"/>',
            '<g fill="none" stroke-linecap="butt" stroke-linejoin="round" opacity="0.9">',
        ]
        for pair in PAIR_ORDER:
            bodies = groups.get(pair) or []
            if not bodies:
                continue
            lines.append(f'<g stroke="{COLORS[pair]}" stroke-width="0.05">')
            lines.extend(f'<path d="{body}"/>' for body in bodies)
            lines.append('</g>')
        extra = [pair for pair in groups if pair not in PAIR_ORDER and groups[pair]]
        for pair in extra:
            lines.append('<g stroke="#555555" stroke-width="0.05">')
            lines.extend(f'<path d="{body}"/>' for body in groups[pair])
            lines.append('</g>')
        lines.extend(['</g>', '</svg>', ''])
        payload = '\n'.join(lines)
        if len(payload.encode('utf-8')) <= max_bytes:
            break
    output_path.write_text(payload, encoding='utf-8')
    selected = dict(file=str(output_path), bytes=len(payload.encode('utf-8')),
                    routes=len(routed), sagitta_mm=used_sagitta,
                    board_mm=BOARD_MM, layer=0)
    return selected
