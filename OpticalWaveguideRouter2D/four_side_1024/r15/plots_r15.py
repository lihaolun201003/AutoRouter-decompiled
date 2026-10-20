"""R15 round figures: R40-vs-R15 2D comparison, R15 plane geometry-type plots,
R15 summary bars and R15 five-layer 2.5D views.

Process requirement (2026-10-20): every planar bend and every 3D elevation
S-curve uses the fixed minimum radius **R = 15 mm** (``four_side_1024/r15/
profile_r15.py``).  All historical R40 results are kept and are only read here
for old-vs-new comparison figures; nothing in this module writes into the frozen
R40 output roots.

The R15 profile is applied at import time, **before** any module that binds the
radius at import (``v2opt.*``, ``fsd25d.config25d``, ``fsd25d.path3d``).  The
five-layer figures are produced by reusing ``four_side_1024.fsd25d.plots25d``
after that profile application, so its sampling and titles are R15-correct.

What is written (only under ``outputs/four_side_1024_v2_r15_v01/``)::

    figures/r15_scheme{A,B}_{z1,z2}_geomtype.png    R15 2D geometry-type plots
    figures/25d/scheme{A,B}/layers5/*.png           R15 5-layer 2.5D figures
    comparison/r40_vs_r15_scheme{A,B}.png           2x2 R40 (top) vs R15 (bottom)
    comparison/r40_vs_r15_2d.png                    both schemes in one grid
    comparison/r40_vs_r15_summary.png               routed counts R40 vs R15
    comparison/r15_5layer_view3d_{A,B}.png          3D + height-coloured composites
    comparison/plots_manifest.json                  inventory / stats / caveats

Every input is optional: missing planes or missing 25D runs are drawn as
"pending" placeholders (or null bars) with a warning in the manifest, never a
crash, so the module can be re-run while the parallel experiment finishes.

CLI
---
    .venv\\Scripts\\python.exe -m four_side_1024.r15.plots_r15
    .venv\\Scripts\\python.exe -m four_side_1024.r15.plots_r15 --in-run-dir
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

from . import profile_r15

# The profile must be applied before importing any module that binds the radius
# at import time (fslw.config, v2opt.candext/ortho90, fsd25d.config25d/path3d).
profile_r15.apply()

import numpy as np  # noqa: E402  (import order is intentional)

from ..d56.plots_d56 import DPI, _board_frame, draw_connectors, pyplot  # noqa: E402
from ..fslw import plots as fslw_plots  # noqa: E402
from ..v2opt import plots_geomtype  # noqa: E402

SCHEMA = 'four_side_1024_v2_r15_plots_v1'
TOOL = 'four_side_1024.r15.plots_r15'
PROJECT_ROOT = Path(__file__).resolve().parents[2]
R15_ROOT = PROJECT_ROOT / profile_r15.R15_ROOT
R40_ROOT_2D_A = PROJECT_ROOT / 'outputs/four_side_1024_v2_candidate_rr_v01'
R40_ROOT_2D_B = PROJECT_ROOT / 'outputs/four_side_1024_v2_ortho90_v01'
R40_ROOT_25D = PROJECT_ROOT / 'outputs/four_side_1024_v2_25d_v01'
FROZEN_ROOTS = (R40_ROOT_2D_A, R40_ROOT_2D_B, R40_ROOT_25D)

BOARD_MM = 150.0
PLANE_TOTAL = 512
TOTAL_CONNECTIONS = 1024
DISPLAY_SAGITTA_MM = 0.005
LINE_COLOR = '#1565c0'
ARC_COLOR = '#c62828'
R40_BASELINE_COLOR = '#9e9e9e'
R15_COLOR = '#1565c0'
PLANE_ORDER = ('z1', 'z2')
SCHEME_ORDER = ('A', 'B')

R15_SCHEMES = {
    'A': dict(label='A_shortS', long='D56 + Short-S',
              note='D56 primitives: axis lines + R=15 mm arcs + short-S'),
    'B': dict(label='B_ortho90', long='pure orthogonal 90 deg',
              note='pure orthogonal: axis lines + exact 90-deg R=15 mm arcs'),
}
R40_SCHEMES = {
    'A': dict(root=R40_ROOT_2D_A, algorithm='BEST', label='V2-BEST',
              routed=752, long='D56 (short-S arcs allowed)',
              note='frozen R40 D56 layout (short-S arcs allowed)'),
    'B': dict(root=R40_ROOT_2D_B, algorithm='ORTHO90', label='V2-ORTHO90',
              routed=262, long='pure orthogonal 90 deg',
              note='frozen R40 pure orthogonal layout (90-deg arc only)'),
}
R40_25D_ROUTED = {'A': 820, 'B': 383}   # cross-checked from live run_summary

_WRITE_ALLOWED = []
_ACTIVE_ROOT = {'path': R15_ROOT}


# --------------------------------------------------------------------------- #
# generic helpers
# --------------------------------------------------------------------------- #
def _apply_style():
    plt = pyplot()
    plt.rcParams.update({
        'font.size': 9.0,
        'axes.titlesize': 10.0,
        'axes.labelsize': 8.5,
        'xtick.labelsize': 7.0,
        'ytick.labelsize': 7.0,
        'legend.fontsize': 7.5,
    })
    return plt


def _json_load(path):
    with Path(path).open('r', encoding='utf-8') as handle:
        return json.load(handle)


def _rel(path):
    try:
        return Path(path).resolve().relative_to(
            Path(_ACTIVE_ROOT['path']).resolve()).as_posix()
    except ValueError:
        return Path(path).resolve().as_posix()


def _blend_hex(colour, other='#ffffff', fraction=0.45):
    first, second = colour.lstrip('#'), other.lstrip('#')
    channels = []
    for start in (0, 2, 4):
        a = int(first[start:start + 2], 16)
        b = int(second[start:start + 2], 16)
        channels.append(int(round(a * (1.0 - fraction) + b * fraction)))
    return '#%02x%02x%02x' % tuple(channels)


def _check_writable(path):
    path = Path(path).resolve()
    for frozen in FROZEN_ROOTS:
        try:
            path.relative_to(Path(frozen).resolve())
        except ValueError:
            continue
        raise RuntimeError(f'refusing to write into frozen R40 root: {path}')
    for allowed in _WRITE_ALLOWED:
        try:
            path.relative_to(Path(allowed).resolve())
        except ValueError:
            continue
        return
    raise RuntimeError(f'refusing to write outside the R15 figures/ dirs: {path}')


def _save(fig, output_path, tight=True):
    plt = pyplot()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _check_writable(output_path)
    if tight:
        fig.tight_layout()
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return output_path


def _pending_text(ax, connectors, text):
    """Consistent placeholder panel when an input artifact is still missing."""
    _board_frame(ax)
    draw_connectors(ax, connectors or [], depth_mm=3.0, label_fontsize=3.2)
    ax.text(0.5, 0.5, text, transform=ax.transAxes, ha='center', va='center',
            fontsize=10.0, color='#666666',
            bbox=dict(boxstyle='round,pad=0.5', facecolor='white',
                      alpha=0.9, edgecolor='#bbbbbb'))
    ax.tick_params(labelsize=6.5)


# --------------------------------------------------------------------------- #
# 2D panel loading (R40 frozen + R15 current)
# --------------------------------------------------------------------------- #
def _make_panel(run_dir, expected_radius, label):
    """Load one plane layout read-only and split it into line/arc polylines."""
    data = fslw_plots.load_plane(Path(run_dir))
    routed = data['routed']
    line_segments, arc_segments, line_length, arc_length = \
        plots_geomtype._kind_segments(routed)
    radii = set()
    radius_counts = {}
    arcs = 0
    for record in routed:
        for primitive in record.get('primitives') or []:
            if primitive.get('kind') != 'arc':
                continue
            arcs += 1
            radius = round(float(primitive['radius']), 6)
            radii.add(radius)
            radius_counts[radius] = radius_counts.get(radius, 0) + 1
    return {
        'label': label,
        'run_dir': Path(run_dir),
        'data': data,
        'routed': routed,
        'routed_count': len(routed),
        'line_segments': line_segments,
        'arc_segments': arc_segments,
        'line_length_mm': line_length,
        'arc_length_mm': arc_length,
        'arc_count': arcs,
        'arc_radii': sorted(radii),
        'arc_radius_counts': {str(radius): count
                              for radius, count in sorted(radius_counts.items())},
        'process_radius_mm': (data.get('process') or {}).get('radius_mm'),
        'expected_radius_mm': float(expected_radius),
    }


def _radius_mismatch(panel):
    """True when a panel stores arcs at a radius other than the expected one."""
    return any(abs(radius - panel['expected_radius_mm']) > 1e-6
               for radius in panel['arc_radii'])


def _radius_summary(panel):
    """Short fixed-radius statement (never hides a stored-radius mismatch)."""
    expected = panel['expected_radius_mm']
    if not panel['arc_radii']:
        return f'fixed radius R={expected:g} mm (no arcs stored)'
    if not _radius_mismatch(panel):
        return f'fixed radius R={expected:g} mm'
    return f'expected R={expected:g} mm'


def _radius_caveat(panel):
    """Explicit data-caveat line when stored arc radii differ from the target."""
    if not _radius_mismatch(panel):
        return ''
    parts = ', '.join(
        f'R={radius:g} mm x{count}'
        for radius, count in sorted(
            ((float(key), value) for key, value
             in panel['arc_radius_counts'].items())))
    return (f'DATA CAVEAT: stored arcs are {parts} (target R='
            f'{panel["expected_radius_mm"]:g} mm) — primitives drawn as stored')


def _input_is_stale(run_dir, routes_name):
    """True when a rerun is in progress: routes file older than the run log.

    A plane / 25D directory whose ``run.log`` is newer than its routes file is
    being rewritten; the stored routes are a previous (possibly stale) attempt,
    so it is treated as pending instead of being plotted.
    """
    run_dir = Path(run_dir)
    routes = run_dir / routes_name
    log = run_dir / 'run.log'
    if not routes.exists() or not log.exists():
        return False
    return routes.stat().st_mtime < log.stat().st_mtime - 1.0


def load_panels(root, caveats):
    """Load every available R40/R15 2D plane panel once; cache in a dict."""
    cache = {}
    for scheme in SCHEME_ORDER:
        meta = R40_SCHEMES[scheme]
        for plane in PLANE_ORDER:
            key = ('R40', scheme, plane)
            run_dir = Path(meta['root']) / 'planes' / 'V2' / meta['algorithm'] / plane
            if not (run_dir / 'routes.json').exists():
                caveats.append(f'R40 {meta["label"]}/{plane}: frozen routes.json '
                               f'missing ({run_dir})')
                continue
            try:
                cache[key] = _make_panel(run_dir, 40.0,
                                         f'R40 {meta["label"]}/{plane}')
            except Exception as exc:  # noqa: BLE001 - report, never crash
                caveats.append(f'R40 {meta["label"]}/{plane}: load failed '
                               f'({type(exc).__name__}: {exc})')
                continue
            radii = cache[key]['arc_radii']
            if radii and any(abs(radius - 40.0) > 1e-6 for radius in radii):
                caveats.append(f'R40 {meta["label"]}/{plane}: arc radii '
                               f'{cache[key]["arc_radius_counts"]} differ from '
                               f'the expected 40 mm')
    for scheme in SCHEME_ORDER:
        for plane in PLANE_ORDER:
            key = ('R15', scheme, plane)
            run_dir = root / 'planes' / 'V2' / scheme / plane
            if not (run_dir / 'routes.json').exists():
                caveats.append(f'R15 scheme{scheme}/{plane}: routes.json '
                               f'missing (pending)')
                continue
            if _input_is_stale(run_dir, 'routes.json'):
                caveats.append(f'R15 scheme{scheme}/{plane}: routes.json is '
                               f'older than run.log (run in progress) - stale '
                               f'output ignored, shown as pending')
                continue
            try:
                cache[key] = _make_panel(run_dir, 15.0,
                                         f'R15 scheme{scheme}/{plane}')
            except Exception as exc:  # noqa: BLE001
                caveats.append(f'R15 scheme{scheme}/{plane}: load failed '
                               f'({type(exc).__name__}: {exc})')
                continue
            panel = cache[key]
            if _radius_mismatch(panel):
                caveats.append(
                    f'R15 scheme{scheme}/{plane}: stored arc radii '
                    f'{panel["arc_radius_counts"]} differ from the required '
                    f'R=15 mm (mixed R40/R15 geometry; figures draw the stored '
                    f'primitives and mark this in the subtitles)')
    return cache


def _connectors(cache):
    for panel in cache.values():
        connectors = (panel.get('data') or {}).get('connectors') or []
        if connectors:
            return connectors
    return []


# --------------------------------------------------------------------------- #
# geometry-type panel drawing
# --------------------------------------------------------------------------- #
def _draw_geomtype_panel(ax, panel, title, subtitle, compact=False,
                         linewidth=None):
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D
    routed_count = panel['routed_count']
    if linewidth is None:
        linewidth = 0.55 if routed_count <= 128 else 0.40
    if panel['line_segments']:
        ax.add_collection(LineCollection(
            panel['line_segments'], colors=[LINE_COLOR],
            linewidths=linewidth, alpha=0.85, zorder=3))
    if panel['arc_segments']:
        ax.add_collection(LineCollection(
            panel['arc_segments'], colors=[ARC_COLOR],
            linewidths=linewidth, alpha=0.85, zorder=4))
    _board_frame(ax)
    draw_connectors(ax, (panel.get('data') or {}).get('connectors') or [],
                    depth_mm=3.0,
                    label_fontsize=3.0 if compact else 4.2)
    arc_label = f"arc: {len(panel['arc_segments'])}"
    if _radius_mismatch(panel):
        arc_label += ' (mixed stored radii)'
    else:
        arc_label += f" (R={panel['expected_radius_mm']:g} mm)"
    handles = [
        Line2D([0], [0], color=LINE_COLOR, linewidth=1.4,
               label=f"line: {len(panel['line_segments'])}"),
        Line2D([0], [0], color=ARC_COLOR, linewidth=1.4, label=arc_label),
    ]
    ax.legend(handles=handles, loc='upper left',
              fontsize=6.0 if compact else 7.0, framealpha=0.85)
    ax.tick_params(labelsize=6.5 if compact else 7.0)
    ax.set_title(title + '\n' + subtitle,
                 fontsize=8.6 if compact else 9.5)


def _panel_title(panel, prefix):
    subtitle = (f"{_radius_summary(panel)} | line=blue "
                f"({len(panel['line_segments'])}), arc=red "
                f"({len(panel['arc_segments'])} arcs)")
    caveat = _radius_caveat(panel)
    if caveat:
        subtitle += '\n' + caveat
    return (f"{prefix} | {panel['routed_count']}/512 routed", subtitle)


# --------------------------------------------------------------------------- #
# 1) R40 vs R15 2D comparison
# --------------------------------------------------------------------------- #
def render_r40_vs_r15_scheme(scheme, output_path, cache, caveats):
    plt = pyplot()
    meta = R40_SCHEMES[scheme]
    r15_meta = R15_SCHEMES[scheme]
    connectors = _connectors(cache)
    fig, axes = plt.subplots(2, 2, figsize=(20.0, 20.8))
    counts = {'R40': {}, 'R15': {}}
    for column, plane in enumerate(PLANE_ORDER):
        ax = axes[0][column]
        panel = cache.get(('R40', scheme, plane))
        if panel is None:
            _pending_text(ax, connectors,
                          f'R40 {meta["label"]} plane {plane}\n'
                          f'frozen routes.json not available')
        else:
            counts['R40'][plane] = panel['routed_count']
            title, subtitle = _panel_title(
                panel, f'R40 {meta["label"]} plane {plane}')
            _draw_geomtype_panel(ax, panel, title,
                                 subtitle + f' | {meta["note"]}')
        ax = axes[1][column]
        panel = cache.get(('R15', scheme, plane))
        if panel is None:
            _pending_text(ax, connectors,
                          f'R15 scheme {scheme} plane {plane}\n'
                          f'routes.json pending')
        else:
            counts['R15'][plane] = panel['routed_count']
            title, subtitle = _panel_title(
                panel, f'R15 scheme {scheme} plane {plane}')
            _draw_geomtype_panel(ax, panel, title,
                                 subtitle + f' | {r15_meta["note"]}')
    total40 = (sum(counts['R40'].values())
               if len(counts['R40']) == len(PLANE_ORDER) else None)
    total15 = (sum(counts['R15'].values())
               if len(counts['R15']) == len(PLANE_ORDER) else None)
    fig.suptitle(
        f'R40 (top row) vs R15 (bottom row) 2D layout comparison — '
        f'scheme {scheme} ({meta["long"]})\n'
        f'R40 frozen baseline: '
        f'{total40 if total40 is not None else "pending"}/1024 routed at R=40 mm | '
        f'R15 this round: '
        f'{total15 if total15 is not None else "pending"}/1024 routed at R=15 mm\n'
        f'route shapes plotted exactly as stored from routes.json | identical '
        f'150 x 150 mm board, connector positions and geometry-type palette',
        fontsize=13.0)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.94))
    _save(fig, output_path, tight=False)
    return {
        'file': _rel(output_path),
        'kind': 'r40_vs_r15_2d',
        'run': f'scheme{scheme}',
        'description': (f'2x2 R40 frozen vs R15 current plane layouts, scheme '
                        f'{scheme}: R40 '
                        f'{total40 if total40 is not None else "pending"} -> '
                        f'R15 {total15 if total15 is not None else "pending"}'),
        'r40_routed': total40,
        'r15_routed': total15,
        'r40_per_plane': dict(counts['R40']),
        'r15_per_plane': dict(counts['R15']),
    }


def render_r40_vs_r15_2d(output_path, cache, caveats):
    plt = pyplot()
    connectors = _connectors(cache)
    layout = [(scheme, plane) for scheme in SCHEME_ORDER for plane in PLANE_ORDER]
    fig, axes = plt.subplots(2, 4, figsize=(26.0, 13.8))
    totals = {'R40': {}, 'R15': {}}
    for row, kind in ((0, 'R40'), (1, 'R15')):
        for column, (scheme, plane) in enumerate(layout):
            ax = axes[row][column]
            panel = cache.get((kind, scheme, plane))
            if panel is None:
                _pending_text(ax, connectors,
                              f'{kind} scheme {scheme} plane {plane}\npending')
                continue
            totals[kind][scheme] = totals[kind].get(scheme, 0) \
                + panel['routed_count']
            radius_prefix = (f'R40 {R40_SCHEMES[scheme]["label"]} plane {plane}'
                             if kind == 'R40' else
                             f'R15 scheme {scheme} plane {plane}')
            compact_subtitle = (f"{_radius_summary(panel)} | line=blue "
                                f"({len(panel['line_segments'])}), arc=red "
                                f"({len(panel['arc_segments'])})")
            if _radius_mismatch(panel):
                compact_subtitle += ' | MIXED RADII (data caveat)'
            _draw_geomtype_panel(
                ax, panel, f'{radius_prefix} | {panel["routed_count"]}/512',
                compact_subtitle, compact=True)
    suptitle_lines = [
        'R15 round: 2D layout comparison, R40 frozen baseline (top row) vs '
        'R15 current (bottom row) | geometry-type colouring line=blue, arc=red',
        'columns: scheme A z1, scheme A z2, scheme B z1, scheme B z2',
    ]
    parts = []
    for kind, name in (('R40', 'R40 frozen'), ('R15', 'R15 current')):
        values = [f'{scheme}={totals[kind].get(scheme, "pending")}/1024'
                  for scheme in SCHEME_ORDER]
        parts.append(f'{name}: ' + ', '.join(values))
    suptitle_lines.append('routed totals: ' + ' | '.join(parts))
    fig.suptitle('\n'.join(suptitle_lines), fontsize=12.0)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.94))
    _save(fig, output_path, tight=False)
    return {
        'file': _rel(output_path),
        'kind': 'r40_vs_r15_2d_combined',
        'run': None,
        'description': 'combined 2x4 R40-vs-R15 2D comparison for both schemes',
        'r40_totals': dict(totals['R40']),
        'r15_totals': dict(totals['R15']),
    }


# --------------------------------------------------------------------------- #
# 2) R15 plane geometry-type figures
# --------------------------------------------------------------------------- #
def render_r15_plane_geomtype(scheme, plane, panel, figures_dir, caveats,
                              in_run_dir=False):
    plt = pyplot()
    output_path = Path(figures_dir) / f'r15_scheme{scheme}_{plane}_geomtype.png'
    fig, ax = plt.subplots(figsize=(11.0, 10.2))
    r15_meta = R15_SCHEMES[scheme]
    title = (f"R15 scheme {scheme} ({r15_meta['long']}) | plane {plane} | "
             f"{panel['routed_count']}/512 routed")
    subtitle = (f"target fixed radius R=15 mm | geometry-type colour: "
                f"line=blue #1565c0, arc=red #c62828")
    caveat = _radius_caveat(panel)
    if caveat:
        subtitle += '\n' + caveat
    _draw_geomtype_panel(ax, panel, title, subtitle)
    _save(fig, output_path)
    entry = {
        'file': _rel(output_path),
        'kind': 'r15_plane_geomtype',
        'run': f'scheme{scheme}/{plane}',
        'description': (f'R15 scheme {scheme} plane {plane} geometry-type '
                        f'figure, {panel["routed_count"]}/512 routed'),
        'routed_count': panel['routed_count'],
        'arc_count': panel['arc_count'],
        'arc_radii': panel['arc_radii'],
        'arc_radius_counts': panel['arc_radius_counts'],
    }
    if in_run_dir:
        run_dir = Path(panel['run_dir'])
        copy_path = run_dir / 'routing_geomtype_r15.png'
        _check_writable(copy_path)
        fig_source = output_path
        copy_path.write_bytes(fig_source.read_bytes())
        entry['copy'] = str(copy_path)
    return entry


# --------------------------------------------------------------------------- #
# 3) R40 vs R15 summary bars
# --------------------------------------------------------------------------- #
def _r40_25d_routed(scheme):
    path = R40_ROOT_25D / f'scheme{scheme}' / 'layers5' / 'run_summary.json'
    if path.exists():
        try:
            payload = _json_load(path)
            value = (payload.get('statistics') or {}).get('routed')
            if value is not None:
                return int(value)
        except (OSError, json.JSONDecodeError):
            pass
    return R40_25D_ROUTED.get(scheme)


def _r15_2d_total(cache, scheme):
    values = [cache[('R15', scheme, plane)]['routed_count']
              for plane in PLANE_ORDER
              if ('R15', scheme, plane) in cache]
    return sum(values) if len(values) == len(PLANE_ORDER) else None


def _r15_25d_routed(runs25d, scheme):
    run = runs25d.get(scheme)
    if run is None:
        return None
    value = (run.get('statistics') or {}).get('routed')
    return int(value) if value is not None else int(run['n_routed'])


def render_r40_vs_r15_summary(output_path, cache, runs25d, caveats):
    plt = pyplot()
    rows = [
        ('2D D56 + Short-S (A)', _r40_2d_total(cache, 'A'),
         _r15_2d_total(cache, 'A')),
        ('2D pure-orth 90 deg (B)', _r40_2d_total(cache, 'B'),
         _r15_2d_total(cache, 'B')),
        ('5-layer 2.5D + Short-S (A)', _r40_25d_routed('A'),
         _r15_25d_routed(runs25d, 'A')),
        ('5-layer 2.5D + pure-orth (B)', _r40_25d_routed('B'),
         _r15_25d_routed(runs25d, 'B')),
    ]
    fig, ax = plt.subplots(figsize=(12.0, 6.8))
    positions = np.arange(len(rows), dtype=float)
    height = 0.36
    for offset, index, colour, label in (
            (-height / 2.0, 1, R40_BASELINE_COLOR, 'R40 baseline (40 mm)'),
            (height / 2.0, 2, R15_COLOR, 'R15 this round (15 mm)')):
        values = [row[index] for row in rows]
        numeric = [value if value is not None else 0 for value in values]
        bars = ax.barh(positions + offset, numeric, height=height,
                       color=colour, alpha=0.92, edgecolor='#222222',
                       linewidth=0.4, label=label)
        for bar_item, value, row in zip(bars, values, rows):
            y = bar_item.get_y() + bar_item.get_height() / 2.0
            if value is None:
                anchor = (row[1] or 0) + 10.0
                ax.text(anchor, y, 'n/a (pending)', va='center', fontsize=7.5,
                        color='#777777')
            else:
                ax.text(value + 8.0, y, f'{value}/1024', va='center',
                        fontsize=8.5)
    # delta annotations next to each row
    for position, row in zip(positions, rows):
        baseline, current = row[1], row[2]
        if baseline is None or current is None:
            continue
        delta = current - baseline
        ax.text(TOTAL_CONNECTIONS * 1.04, position,
                f'{delta:+d} vs R40', va='center', fontsize=8.5,
                color='#2e7d32' if delta > 0 else '#b71c1c')
    ax.axvline(TOTAL_CONNECTIONS, color='#333333', linewidth=0.8,
               linestyle='--')
    ax.text(TOTAL_CONNECTIONS - 8.0, -0.52, f'{TOTAL_CONNECTIONS} connections',
            ha='right', va='bottom', fontsize=7.5)
    ax.set_yticks(positions)
    ax.set_yticklabels([row[0] for row in rows], fontsize=9.0)
    ax.set_xlim(0.0, TOTAL_CONNECTIONS * 1.24)
    ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.set_xlabel('routed connections (of 1024)', fontsize=9.0)
    ax.grid(True, axis='x', alpha=0.28, linewidth=0.5)
    ax.legend(fontsize=8.5, loc='lower right', framealpha=0.9)
    missing = sum(1 for row in rows if row[2] is None)
    note = ('all four R15 values available'
            if missing == 0 else
            f'{missing} R15 value(s) still pending — shown as n/a')
    ax.set_title(
        'R15 round: routed connections, R40 baseline (40 mm) vs R15 (15 mm)\n'
        f'rows: 2D D56, 2D pure-orth, 5-layer 2.5D + Short-S, 5-layer 2.5D '
        f'pure-orth | {note}', fontsize=10.0)
    _save(fig, output_path)
    return {
        'file': _rel(output_path),
        'kind': 'r40_vs_r15_summary',
        'run': None,
        'description': 'routed counts R40 baseline vs R15 for the four 2D/2.5D rows',
        'rows': [{'row': row[0], 'r40': row[1], 'r15': row[2]}
                 for row in rows],
    }


def _r40_2d_total(cache, scheme):
    values = [cache[('R40', scheme, plane)]['routed_count']
              for plane in PLANE_ORDER
              if ('R40', scheme, plane) in cache]
    return sum(values) if len(values) == len(PLANE_ORDER) else None


# --------------------------------------------------------------------------- #
# 4) R15 five-layer 2.5D figures (reuse fsd25d.plots25d under the R15 profile)
# --------------------------------------------------------------------------- #
def _import_plots25d(caveats):
    from ..fsd25d import plots25d
    bound_radius = float(getattr(plots25d.CFG, 'RADIUS_MM', 0.0) or 0.0)
    if abs(bound_radius - 15.0) > 1e-9:
        caveats.append(
            f'fsd25d config radius is {bound_radius} mm (expected 15): the R15 '
            f'profile was not applied before import; stored R15 geometry is '
            f'still plotted as-is')
    return plots25d


def _segment_radius_counts(run):
    """Radius histogram of every stored arc / transition in a 25D run."""
    counts = {}
    for record in run['routed']:
        for part in record.get('parts') or []:
            if part.get('kind') == 'transition':
                try:
                    radius = round(float(part['radius_mm']), 6)
                except (KeyError, TypeError, ValueError):
                    continue
                counts[radius] = counts.get(radius, 0) + 1
            else:
                for primitive in part.get('primitives') or []:
                    if primitive.get('kind') != 'arc':
                        continue
                    radius = round(float(primitive['radius']), 6)
                    counts[radius] = counts.get(radius, 0) + 1
    return {str(radius): count for radius, count in sorted(counts.items())}


def load_25d_runs(root_25d, plots25d, caveats):
    runs = {}
    for scheme in SCHEME_ORDER:
        run_dir = Path(root_25d) / f'scheme{scheme}' / 'layers5'
        routes = run_dir / 'routes_25d.json'
        if not routes.exists():
            caveats.append(f'R15 25D scheme{scheme}/layers5: '
                           f'routes_25d.json missing (pending)')
            continue
        if _input_is_stale(run_dir, 'routes_25d.json'):
            caveats.append(f'R15 25D scheme{scheme}/layers5: routes_25d.json '
                           f'is older than run.log (run in progress) - stale '
                           f'output ignored, shown as pending')
            continue
        try:
            run = plots25d.load_run(run_dir)
        except Exception as exc:  # noqa: BLE001
            caveats.append(f'R15 25D scheme{scheme}/layers5: load failed '
                           f'({type(exc).__name__}: {exc})')
            continue
        counts = _segment_radius_counts(run)
        run['_radius_counts'] = counts
        run['_radii'] = sorted(float(key) for key in counts)
        if any(abs(radius - 15.0) > 1e-6 for radius in run['_radii']):
            caveats.append(f'R15 25D scheme{scheme}/layers5: stored arc / '
                           f'transition radii {counts} differ from the required '
                           f'R=15 mm (figures draw the stored primitives)')
        runs[scheme] = run
    return runs


def _run_3d_segments(run, plots25d):
    per_plane = {}
    for plane in PLANE_ORDER:
        chunks = []
        for record in run['routed']:
            if plots25d._route_plane(record, run) != plane:
                continue
            segments = plots25d.route_segments_3d(record)
            if segments is not None and len(segments):
                chunks.append(segments)
        per_plane[plane] = (np.concatenate(chunks, axis=0)
                            if chunks else None)
    return per_plane


def _custom_view3d(fig_or_axes, run, per_plane, plots25d, suptitle=None):
    """Draw the R15 3D centerline view (same conventions as plots25d)."""
    from mpl_toolkits.mplot3d.art3d import Line3DCollection
    from matplotlib.lines import Line2D
    ax = fig_or_axes
    for plane in PLANE_ORDER:
        segments = per_plane.get(plane)
        if segments is None or not len(segments):
            continue
        ax.add_collection3d(Line3DCollection(
            segments, colors=plots25d.PLANE_COLORS[plane], linewidths=0.30,
            alpha=0.65, zorder=3))
    z_lo, z_hi = plots25d._board_3d(ax, run['layers_z_mm'])
    pad = 6.0
    ax.set_xlim(-pad, BOARD_MM + pad)
    ax.set_ylim(-pad, BOARD_MM + pad)
    z_pad = 0.10 * (z_hi - z_lo)
    ax.set_zlim(z_lo - z_pad, z_hi + z_pad)
    z_aspect = 0.45
    ax.set_box_aspect((1.0, 1.0, z_aspect))
    horizontal = 1.0 / float(BOARD_MM + 2.0 * pad)
    vertical = z_aspect / float((z_hi - z_lo) + 2.0 * z_pad)
    exaggeration = vertical / horizontal
    ax.set_xticks([0.0, 50.0, 100.0, 150.0])
    ax.set_yticks([0.0, 50.0, 100.0, 150.0])
    ax.set_zticks([float(z) for z in run['layers_z_mm']])
    ax.set_zticklabels([f'{float(z):.3f}' for z in run['layers_z_mm']],
                       fontsize=6.5)
    ax.set_xlabel('x (mm)')
    ax.set_ylabel('y (mm)')
    ax.set_zlabel('z (mm)')
    ax.view_init(elev=30.0, azim=-57.0)
    handles = [Line2D([0], [0], color=plots25d.PLANE_COLORS[plane],
                      linewidth=2.0, label=f'{plane} plane routes')
               for plane in PLANE_ORDER]
    ax.legend(handles=handles, loc='upper left', fontsize=7.5, framealpha=0.85)
    stats = run['statistics']
    lifted = int(stats.get('lifted') or 0)
    transitions = int(stats.get('transitions') or 0)
    z1 = float(run['layers_z_mm'][int(run['interface_layer'].get('z1', 0))])
    z2 = float(run['layers_z_mm'][int(run['interface_layer'].get(
        'z2', run['n_layers'] - 1))])
    title = (
        f"R15 five-layer 2.5D, scheme {run['scheme']} | "
        f"{run['n_layers']} layers | {run['n_routed']}/{TOTAL_CONNECTIONS} routed "
        f"| 3D centerline view with fixed R=15 mm elevation curves\n"
        f"z1 plane at {z1:.3f} mm (blue), z2 plane at {z2:.3f} mm (red) | "
        f"{lifted} lifted routes, {transitions} vertical S-transitions | "
        f"route shapes plotted exactly as stored\n"
        f"flat parts + two-arc R=15 mm transitions | vertical scale "
        f"exaggerated ~{exaggeration:.0f}x for display")
    if suptitle is None:
        ax.set_title(title, fontsize=9.5)
    else:
        suptitle(title)
    return exaggeration


def _draw_height_top_view(ax, run, per_plane, plots25d, compact=False):
    from matplotlib import colormaps
    from matplotlib.cm import ScalarMappable
    from matplotlib.collections import LineCollection
    from matplotlib.colors import Normalize
    chunks, heights = [], []
    for plane in PLANE_ORDER:
        segments = per_plane.get(plane)
        if segments is None or not len(segments):
            continue
        chunks.append(segments[:, :, :2])
        heights.append(segments[:, :, 2].mean(axis=1))
    z_top = float(max(run['layers_z_mm']))
    norm = Normalize(vmin=0.0, vmax=max(z_top, 1e-9))
    cmap = colormaps['plasma']
    if chunks:
        segments = np.concatenate(chunks, axis=0)
        values = np.concatenate(heights, axis=0)
        ax.add_collection(LineCollection(
            segments, colors=cmap(norm(values)),
            linewidths=0.40 if run['n_routed'] > 128 else 0.55,
            alpha=0.90, zorder=3))
    _board_frame(ax)
    draw_connectors(ax, run.get('_connectors') or [], depth_mm=3.0,
                    label_fontsize=4.2)
    stats = run['statistics']
    lifted = int(stats.get('lifted') or 0)
    transitions = int(stats.get('transitions') or 0)
    if compact:
        title = (f"XY top view coloured by height z | "
                 f"{run['n_routed']}/{TOTAL_CONNECTIONS} routed, R=15 mm\n"
                 f"{lifted} lifted routes ({transitions} S-transitions) at "
                 f"intermediate heights | z = 0.000-{z_top:.3f} mm")
    else:
        title = (
            f"R15 five-layer 2.5D, scheme {run['scheme']} | XY top view "
            f"coloured by 3D height z | {run['n_routed']}/{TOTAL_CONNECTIONS} "
            f"routed\n"
            f"z = 0.000-{z_top:.3f} mm | {lifted} lifted routes "
            f"({transitions} S-transitions at R=15 mm) travel at intermediate "
            f"heights\n"
            f"colours come from the stored 3D path | height scale in mm, board "
            f"axes unchanged")
    ax.set_title(title, fontsize=9.0 if compact else 9.5)
    return ScalarMappable(norm=norm, cmap=cmap), z_top


def _render_25d_view3d(run, output_path, per_plane, plots25d):
    plt = pyplot()
    fig = plt.figure(figsize=(16.0, 9.6))
    ax = fig.add_subplot(111, projection='3d')
    ax.set_position([-0.02, -0.17, 1.02, 1.23])
    exaggeration = _custom_view3d(ax, run, per_plane, plots25d)
    fig.suptitle(
        f"R15 five-layer 2.5D, scheme {run['scheme']} | "
        f"{run['n_layers']} layers | {run['n_routed']}/{TOTAL_CONNECTIONS} "
        f"routed | 3D centerline view with fixed R=15 mm elevation curves\n"
        f"z1 plane at 0.000 mm (blue), z2 plane at 0.500 mm (red) | "
        f"{int(run['statistics'].get('lifted') or 0)} lifted routes, "
        f"{int(run['statistics'].get('transitions') or 0)} vertical "
        f"S-transitions | route shapes plotted exactly as stored\n"
        f"flat parts + two-arc R=15 mm transitions | vertical scale "
        f"exaggerated ~{exaggeration:.0f}x for display",
        fontsize=10.0, y=0.985)
    plots25d._save(fig, output_path, tight=False)
    return {'z_exaggeration': round(exaggeration, 1)}


def render_25d_run(scheme, run, figures_25d_dir, plots25d, connectors,
                   in_run_dir, caveats):
    figures_25d_dir = Path(figures_25d_dir)
    figures_25d_dir.mkdir(parents=True, exist_ok=True)
    run['_connectors'] = connectors
    entries = []
    by_layer = plots25d.prepare_layer_geometry(run)
    for layer in range(run['n_layers']):
        output_path = figures_25d_dir / f'layer_{layer}.png'
        info = plots25d.render_layer(run, by_layer, layer, output_path,
                                     connectors)
        entries.append({
            'file': _rel(output_path), 'kind': 'r15_25d_layer_2d',
            'run': f'scheme{scheme}/layers5', 'layer': int(layer),
            'description': f'R15 5-layer 2.5D scheme {scheme} layer {layer} '
                           f'flat parts, plane colouring (R=15 mm round)',
        })
    output_path = figures_25d_dir / 'layers_2d.png'
    plots25d.render_layers_2d(run, by_layer, output_path, connectors)
    entries.append({'file': _rel(output_path), 'kind': 'r15_25d_layers_2d',
                    'run': f'scheme{scheme}/layers5',
                    'description': f'R15 5-layer 2.5D scheme {scheme}: all '
                                   f'layers as panels'})
    per_plane = _run_3d_segments(run, plots25d)
    output_path = figures_25d_dir / 'view3d.png'
    _render_25d_view3d(run, output_path, per_plane, plots25d)
    entries.append({'file': _rel(output_path), 'kind': 'r15_25d_view3d',
                    'run': f'scheme{scheme}/layers5',
                    'description': f'R15 5-layer 2.5D scheme {scheme}: 3D '
                                   f'centerline view, R=15 mm transitions'})
    output_path = figures_25d_dir / 'top_view_by_height.png'
    plt = pyplot()
    fig, ax = plt.subplots(figsize=(11.0, 10.4))
    mappable, z_top = _draw_height_top_view(ax, run, per_plane, plots25d)
    colorbar = fig.colorbar(mappable, ax=ax)
    colorbar.set_label('3D path height z (mm)')
    colorbar.set_ticks([float(z) for z in run['layers_z_mm']])
    colorbar.ax.set_yticklabels(
        [f'{float(z):.3f}' for z in run['layers_z_mm']])
    plots25d._save(fig, output_path)
    entries.append({'file': _rel(output_path),
                    'kind': 'r15_25d_top_view_by_height',
                    'run': f'scheme{scheme}/layers5',
                    'description': f'R15 5-layer 2.5D scheme {scheme}: XY top '
                                   f'view coloured by 3D height (R=15 mm)'})
    if in_run_dir:
        run_dir = Path(run['run_dir'])
        active_root = Path(_ACTIVE_ROOT['path'])
        for entry in list(entries):
            source = (active_root / entry['file']).resolve()
            if not source.exists():
                continue
            copy_path = run_dir / Path(entry['file']).name
            _check_writable(copy_path)
            copy_path.write_bytes(source.read_bytes())
            entries.append({
                'file': _rel(copy_path),
                'kind': entry['kind'] + '_copy',
                'run': f'scheme{scheme}/layers5',
                'description': f'copy of {entry["file"]} next to routes_25d.json',
            })
    return entries, per_plane


def render_25d_composite(scheme, run, per_plane, output_path, plots25d):
    plt = pyplot()
    fig = plt.figure(figsize=(23.0, 10.6))
    grid = fig.add_gridspec(1, 2, width_ratios=[1.22, 1.0], wspace=0.04,
                            left=0.03, right=0.97, top=0.86, bottom=0.06)
    ax3d = fig.add_subplot(grid[0], projection='3d')
    ax2d = fig.add_subplot(grid[1])
    run['_connectors'] = run.get('_connectors') or []
    exaggeration = _custom_view3d(ax3d, run, per_plane, plots25d)
    ax3d.set_title(
        f"3D centerline view | fixed R=15 mm elevation curves | z exaggerated "
        f"~{exaggeration:.0f}x", fontsize=9.0, pad=-2.0)
    mappable, z_top = _draw_height_top_view(ax2d, run, per_plane, plots25d,
                                            compact=True)
    colorbar = fig.colorbar(mappable, ax=ax2d, fraction=0.045, pad=0.02)
    colorbar.set_label('3D path height z (mm)')
    colorbar.set_ticks([float(z) for z in run['layers_z_mm']])
    colorbar.ax.set_yticklabels(
        [f'{float(z):.3f}' for z in run['layers_z_mm']])
    fig.suptitle(
        f"R15 five-layer 2.5D composite, scheme {scheme} | "
        f"{run['n_routed']}/{TOTAL_CONNECTIONS} routed | fixed radius R=15 mm "
        f"for all planar bends and elevation S-curves\n"
        f"left: 3D centerline view (z1 blue, z2 red) | right: XY top view "
        f"coloured by height z (0.000-{z_top:.3f} mm) | route shapes plotted "
        f"exactly as stored", fontsize=11.5, y=0.975)
    plots25d._save(fig, output_path, tight=False)
    return {'z_exaggeration': round(exaggeration, 1)}


# --------------------------------------------------------------------------- #
# manifest
# --------------------------------------------------------------------------- #
def write_manifest(manifest_path, files, runs25d, cache, caveats):
    manifest_path = Path(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    _check_writable(manifest_path)
    existing = {}
    if manifest_path.exists():
        try:
            existing = _json_load(manifest_path)
        except (OSError, json.JSONDecodeError):
            existing = {}
    files_by_path = {}
    active_root = Path(_ACTIVE_ROOT['path'])
    for entry in existing.get('files') or []:
        name = entry.get('file')
        if not name:
            continue
        path = (active_root / name) if not Path(name).is_absolute() else Path(name)
        if path.exists():
            files_by_path[name] = entry
    for entry in files:
        files_by_path[entry['file']] = entry
    runs_table = {}
    for scheme in SCHEME_ORDER:
        run = runs25d.get(scheme)
        entry = {'present': run is not None}
        if run is not None:
            stats = run.get('statistics') or {}
            entry.update({
                'routed': int(stats.get('routed') or run['n_routed']),
                'baseline_routed': int(stats.get('baseline_routed') or 0),
                'new_routed': int(stats.get('new_routed') or 0),
                'lifted': int(stats.get('lifted') or 0),
                'transitions': int(stats.get('transitions') or 0),
                'n_layers': int(run['n_layers']),
                'radii_mm': run.get('_radii'),
                'radius_counts': run.get('_radius_counts'),
                'run_dir': _rel(run['run_dir']),
                'routes_sha256': _sha256(run['routes_path']),
            })
        runs_table[scheme] = entry

    def panel_audit(panel):
        if panel is None:
            return None
        return {
            'routed': panel['routed_count'],
            'arcs': panel['arc_count'],
            'arc_radius_counts': panel['arc_radius_counts'],
        }
    payload = {
        'schema': SCHEMA,
        'tool': TOOL,
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'root': str(_ACTIVE_ROOT['path']),
        'profile': {
            'name': profile_r15.PROFILE_NAME,
            'radius_mm': profile_r15.RADIUS_MM,
            'note': profile_r15.PROFILE_NOTE,
            'applied': True,
        },
        'style': {
            'board_mm': BOARD_MM,
            'dpi': DPI,
            'geometry_type_colors': {'line': LINE_COLOR, 'arc': ARC_COLOR},
            'display_sagitta_mm': DISPLAY_SAGITTA_MM,
            'connectors': '64 frozen MPO envelopes (fslw.ports.load_plane V2)',
            'labels': 'English only (no CJK glyphs in figures)',
        },
        'r40_inputs': {
            'schemeA_2d': str(R40_ROOT_2D_A / 'planes/V2/BEST'),
            'schemeB_2d': str(R40_ROOT_2D_B / 'planes/V2/ORTHO90'),
            '5layer_2.5d': str(R40_ROOT_25D),
        },
        'r15_2d': {
            scheme: {
                plane: panel_audit(cache.get(('R15', scheme, plane)))
                for plane in PLANE_ORDER
            }
            for scheme in SCHEME_ORDER
        },
        'r40_2d': {
            scheme: {
                plane: panel_audit(cache.get(('R40', scheme, plane)))
                for plane in PLANE_ORDER
            }
            for scheme in SCHEME_ORDER
        },
        'r15_25d': runs_table,
        'files': sorted(files_by_path.values(), key=lambda item: item['file']),
        'caveats': list(caveats),
    }
    manifest_path.write_text(json.dumps(payload, indent=1, ensure_ascii=False),
                             encoding='utf-8')
    return payload


def _sha256(path):
    import hashlib
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _build_parser():
    parser = argparse.ArgumentParser(
        description='Render R15 round figures (R40 vs R15 comparison, R15 2D '
                    'geometry-type plots, R15 5-layer 2.5D views).')
    parser.add_argument('--root', default=None,
                        help='R15 experiment root (default '
                             'outputs/four_side_1024_v2_r15_v01)')
    parser.add_argument('--in-run-dir', action='store_true',
                        help='also copy R15 plane / 25D figures next to the '
                             'stored routes.json files')
    parser.add_argument('--verbose', action='store_true')
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    root = Path(args.root) if args.root else Path(R15_ROOT)
    root = root if root.is_absolute() else PROJECT_ROOT / root
    root = root.resolve()
    _ACTIVE_ROOT['path'] = root
    figures_dir = root / 'figures'
    comparison_dir = root / 'comparison'
    figures_dir.mkdir(parents=True, exist_ok=True)
    comparison_dir.mkdir(parents=True, exist_ok=True)
    _WRITE_ALLOWED.clear()
    _WRITE_ALLOWED.extend([figures_dir, comparison_dir])
    if args.in_run_dir:
        _WRITE_ALLOWED.extend([root / 'planes', root / '25d'])
    started = time.perf_counter()
    caveats = []
    _apply_style()
    files = []

    # ---- 2D panels --------------------------------------------------------
    cache = load_panels(root, caveats)
    print(f'[plots_r15] 2D panels loaded: {len(cache)} '
          f'({sum(1 for key in cache if key[0] == "R40")} R40 / '
          f'{sum(1 for key in cache if key[0] == "R15")} R15)')
    connectors = _connectors(cache)
    for scheme in SCHEME_ORDER:
        output_path = comparison_dir / f'r40_vs_r15_scheme{scheme}.png'
        try:
            entry = render_r40_vs_r15_scheme(scheme, output_path, cache, caveats)
        except Exception as exc:  # noqa: BLE001
            message = (f'r40_vs_r15_scheme{scheme}: failed '
                       f'({type(exc).__name__}: {exc})')
            print(f'[plots_r15] WARNING {message}')
            caveats.append(message)
            continue
        files.append(entry)
        print(f"[plots_r15] {entry['file']}")
    output_path = comparison_dir / 'r40_vs_r15_2d.png'
    try:
        entry = render_r40_vs_r15_2d(output_path, cache, caveats)
        files.append(entry)
        print(f"[plots_r15] {entry['file']}")
    except Exception as exc:  # noqa: BLE001
        message = f'r40_vs_r15_2d: failed ({type(exc).__name__}: {exc})'
        print(f'[plots_r15] WARNING {message}')
        caveats.append(message)
    for scheme in SCHEME_ORDER:
        for plane in PLANE_ORDER:
            panel = cache.get(('R15', scheme, plane))
            if panel is None:
                continue
            try:
                entry = render_r15_plane_geomtype(
                    scheme, plane, panel, figures_dir, caveats,
                    in_run_dir=args.in_run_dir)
            except Exception as exc:  # noqa: BLE001
                message = (f'r15 plane {scheme}/{plane} geomtype: failed '
                           f'({type(exc).__name__}: {exc})')
                print(f'[plots_r15] WARNING {message}')
                caveats.append(message)
                continue
            files.append(entry)
            print(f"[plots_r15] {entry['file']}")

    # ---- 5-layer 2.5D (reuse fsd25d.plots25d under the R15 profile) -------
    runs25d = {}
    try:
        plots25d = _import_plots25d(caveats)
        runs25d = load_25d_runs(root / '25d', plots25d, caveats)
    except Exception as exc:  # noqa: BLE001
        message = f'fsd25d.plots25d unavailable ({type(exc).__name__}: {exc})'
        print(f'[plots_r15] WARNING {message}')
        caveats.append(message)
        plots25d = None
    if plots25d is not None:
        if connectors:
            pass
        else:
            connectors = plots25d.load_connectors('V2', caveats)
        for scheme in SCHEME_ORDER:
            run = runs25d.get(scheme)
            if run is None:
                continue
            run_dir_name = f'layers{run["n_layers"]}'
            target_dir = figures_dir / '25d' / f'scheme{scheme}' / run_dir_name
            try:
                entries, per_plane = render_25d_run(
                    scheme, run, target_dir, plots25d, connectors,
                    args.in_run_dir, caveats)
            except Exception as exc:  # noqa: BLE001
                message = (f'R15 25D scheme{scheme}: per-run figures failed '
                           f'({type(exc).__name__}: {exc})')
                print(f'[plots_r15] WARNING {message}')
                caveats.append(message)
                continue
            files.extend(entries)
            for entry in entries:
                print(f"[plots_r15] {entry['file']}")
            output_path = comparison_dir / f'r15_5layer_view3d_{scheme}.png'
            try:
                composite = render_25d_composite(
                    scheme, run, per_plane, output_path, plots25d)
            except Exception as exc:  # noqa: BLE001
                message = (f'r15_5layer_view3d_{scheme}: composite failed '
                           f'({type(exc).__name__}: {exc})')
                print(f'[plots_r15] WARNING {message}')
                caveats.append(message)
                continue
            files.append({
                'file': _rel(output_path),
                'kind': 'r15_5layer_view3d_composite',
                'run': f'scheme{scheme}/layers5',
                'description': (f'R15 5-layer composite scheme {scheme}: 3D '
                                f'centerline view + height-coloured top view'),
                'z_exaggeration': composite['z_exaggeration'],
            })
            print(f"[plots_r15] {_rel(output_path)}")

    # ---- summary bars -----------------------------------------------------
    output_path = comparison_dir / 'r40_vs_r15_summary.png'
    try:
        entry = render_r40_vs_r15_summary(output_path, cache, runs25d, caveats)
        files.append(entry)
        print(f"[plots_r15] {entry['file']}")
    except Exception as exc:  # noqa: BLE001
        message = f'r40_vs_r15_summary: failed ({type(exc).__name__}: {exc})'
        print(f'[plots_r15] WARNING {message}')
        caveats.append(message)

    # ---- manifest ---------------------------------------------------------
    manifest_path = comparison_dir / 'plots_manifest.json'
    manifest_entry = {
        'file': _rel(manifest_path),
        'kind': 'plots_manifest',
        'run': None,
        'description': 'inventory of every figure generated by plots_r15',
    }
    files.append(manifest_entry)
    manifest = write_manifest(manifest_path, files, runs25d, cache, caveats)
    print(json.dumps({
        'tool': TOOL,
        'root': str(root),
        'files': len(manifest['files']),
        'r15_2d': manifest['r15_2d'],
        'r15_25d': {scheme: entry.get('routed')
                    for scheme, entry in manifest['r15_25d'].items()},
        'caveats': caveats,
        'wall_seconds': round(time.perf_counter() - started, 2),
    }, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
