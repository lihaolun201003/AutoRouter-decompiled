"""Figures for the V2 five-layer (2.5D) experiment.

Read-only plotting: every route is drawn exactly as stored in
``routes_25d.json`` (flat parts use their stored 2D primitives, transitions use
the S-curve definition of ``SCHEMA_25D.md`` §3).  Nothing in this module changes
geometry, connectors, axes or data; the two frozen 2D output roots are opened
read-only.

What is written (all under ``outputs/four_side_1024_v2_25d_v01/``)::

    figures/<scheme>/layers<n>/layer_<k>.png    one 2D diagram per layer
    figures/<scheme>/layers<n>/layers_2d.png    all layers in one panel grid
    figures/<scheme>/layers<n>/view3d.png       matplotlib 3D centerline view
    figures/<scheme>/layers<n>/top_view_by_height.png
                                                XY top view coloured by height
    comparison/baseline_vs_25d_scheme{A,B}.png  frozen 2D baseline vs 2.5D final
    comparison/layers_effect.png                routed: baseline / 3 / 5 layers
    comparison/lift_statistics.png              lifted routes and transitions
    comparison/plots_manifest.json              inventory of every figure

Style conventions are inherited from the frozen 2D figures: 150 x 150 mm board,
``d56.plots_d56._board_frame`` + ``draw_connectors``, 200 dpi, English labels
(the host has no CJK font), z1 plane blue ``#1565c0`` and z2 plane red
``#c62828``.

CLI
---
    .venv\\Scripts\\python.exe -m four_side_1024.fsd25d.plots25d
    .venv\\Scripts\\python.exe -m four_side_1024.fsd25d.plots25d --root \\
        outputs/four_side_1024_v2_25d_v01 --include-smoke
    .venv\\Scripts\\python.exe -m four_side_1024.fsd25d.plots25d --runs \\
        schemeA/layers5,schemeB/layers5
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np

from ..d56.plots_d56 import DPI, _board_frame, draw_connectors, pyplot
from ..geometry import sample
from . import config25d as CFG

SCHEMA_ROUTES = 'four_side_1024_v2_25d_routes_v1'
SCHEMA_RUN = 'four_side_1024_v2_25d_run_v1'
SCHEMA_PLOTS = 'four_side_1024_v2_25d_plots_v1'
TOOL = 'four_side_1024.fsd25d.plots25d'
BOARD_MM = 150.0

PLANE_COLORS = {'z1': '#1565c0', 'z2': '#c62828'}
LINE_COLOR = '#1565c0'          # geometry-type colouring of the frozen comparison
ARC_COLOR = '#c62828'
BASELINE_COLOR = '#9e9e9e'
FINAL_COLOR = '#2e7d32'
SCHEME_COLORS = {'A': '#5e35b1', 'B': '#ef6c00'}
TRAVEL_LIGHTEN = 0.45           # travel-layer plane colours blended to white
DISPLAY_SAGITTA_MM = 0.005      # flat-part display sampling (frozen convention)
TRANSITION_DISPLAY_STEP_MM = 0.05
DISPLAY_SAGITTA_3D_MM = 0.02
TRANSITION_3D_STEP_MM = 0.10
PLANE_TOTAL = 512
TOTAL_CONNECTIONS = 1024
DEFAULT_ROOT = CFG.V25D_ROOT
FROZEN_ROOTS = (CFG.OUTPUTS / 'four_side_1024_v2_candidate_rr_v01',
                CFG.OUTPUTS / 'four_side_1024_v2_ortho90_v01')

_PLANE_ORDER = ('z1', 'z2')


# --------------------------------------------------------------------------- #
# generic helpers
# --------------------------------------------------------------------------- #
def _apply_style():
    """Consistent, readable font sizes for every figure of this module."""
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


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _rel(root, path):
    path = Path(path).resolve()
    try:
        return path.relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _guard_write(path):
    """Refuse to write anything below the two frozen 2D output roots."""
    resolved = Path(path).resolve()
    for frozen in FROZEN_ROOTS:
        try:
            resolved.relative_to(Path(frozen).resolve())
        except ValueError:
            continue
        raise RuntimeError(f'refusing to write into frozen output root: {resolved}')


def _save(fig, output_path, tight=True):
    plt = pyplot()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _guard_write(output_path)
    if tight:
        fig.tight_layout()
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return output_path


def _blend_hex(colour, other='#ffffff', fraction=0.45):
    first, second = colour.lstrip('#'), other.lstrip('#')
    channels = []
    for start in (0, 2, 4):
        a = int(first[start:start + 2], 16)
        b = int(second[start:start + 2], 16)
        channels.append(int(round(a * (1.0 - fraction) + b * fraction)))
    return '#%02x%02x%02x' % tuple(channels)


def _plane_colour(plane, layer, interface_layer):
    """Interface layer keeps the saturated plane colour, travel layers lighten."""
    colour = PLANE_COLORS.get(plane, '#555555')
    if int(interface_layer.get(plane, -1)) != int(layer):
        colour = _blend_hex(colour, '#ffffff', TRAVEL_LIGHTEN)
    return colour


def _linewidth(count):
    if count <= 32:
        return 0.80
    if count <= 128:
        return 0.55
    return 0.40


# --------------------------------------------------------------------------- #
# transition geometry (SCHEMA_25D.md §3, rebuilt here for display only)
# --------------------------------------------------------------------------- #
def transition_theta(radius_mm, dz_mm):
    dz = abs(float(dz_mm))
    if dz <= 0.0:
        return 0.0
    ratio = 1.0 - dz / (2.0 * float(radius_mm))
    return math.acos(max(-1.0, min(1.0, ratio)))


def _transition_z_bounds(part):
    """Stored transition heights (schema uses ``z0_mm``/``z1_mm``)."""
    z0 = part.get('z0_mm', part.get('z0'))
    z1 = part.get('z1_mm', part.get('z1'))
    if z0 is None or z1 is None:
        raise KeyError('transition part has no z0/z1 height')
    return float(z0), float(z1)


def transition_polyline(part, step_mm=TRANSITION_DISPLAY_STEP_MM):
    """3D samples ``(x, y, z)`` of one stored transition part.

    Uses the unique S-curve definition of the schema: ``theta =
    acos(1-|dz|/(2R))``, first arc ``u = R sin(phi)``, ``w = z0 + sign*R(1-cos
    phi)``, second arc = point reflection of the first one about the midpoint.
    """
    radius = float(part['radius_mm'])
    z0, z1 = _transition_z_bounds(part)
    dz = z1 - z0
    sign = 1.0 if dz >= 0.0 else -1.0
    theta = transition_theta(radius, dz)
    start = np.asarray(part['start'], dtype=float)
    end = np.asarray(part['end'], dtype=float)
    direction = np.asarray(part['direction'], dtype=float)
    norm = float(np.hypot(direction[0], direction[1]))
    if norm <= 0.0:
        raise ValueError('transition direction is zero')
    direction = direction / norm
    if theta <= 0.0:
        # degenerate (no height change): a straight XY segment at z0
        return np.asarray([[start[0], start[1], z0], [end[0], end[1], z1]])
    footprint = 2.0 * radius * math.sin(theta)
    arc_length = 2.0 * radius * theta
    count = max(2, int(math.ceil(arc_length / max(step_mm, 1e-9))))
    phase = np.linspace(0.0, 2.0 * theta, count + 1)
    first_half = phase <= theta
    u = np.where(first_half,
                 radius * np.sin(phase),
                 footprint - radius * np.sin(2.0 * theta - phase))
    w = np.where(first_half,
                 z0 + sign * radius * (1.0 - np.cos(phase)),
                 z1 - sign * radius * (1.0 - np.cos(2.0 * theta - phase)))
    xy = start[None, :] + u[:, None] * direction[None, :]
    return np.column_stack([xy, w])


def transition_consistency(part):
    """Max deviation (mm) of the stored footprint/end/theta from the schema formula."""
    radius = float(part['radius_mm'])
    z0, z1 = _transition_z_bounds(part)
    dz = z1 - z0
    theta = transition_theta(radius, dz)
    footprint = 2.0 * radius * math.sin(theta)
    length = 2.0 * radius * theta
    start = np.asarray(part['start'], dtype=float)
    end = np.asarray(part['end'], dtype=float)
    direction = np.asarray(part['direction'], dtype=float)
    norm = float(np.hypot(direction[0], direction[1])) or 1.0
    direction = direction / norm
    expected_end = start + direction * footprint
    errors = [
        abs(footprint - float(part.get('footprint_mm') or footprint)),
        abs(length - float(part.get('length_mm') or length)),
        float(np.hypot(*(end - expected_end))),
    ]
    return max(errors)


# --------------------------------------------------------------------------- #
# route sampling
# --------------------------------------------------------------------------- #
def flat_polyline(part, sagitta_mm=DISPLAY_SAGITTA_MM):
    """2D display polyline of one stored flat part (no geometry change)."""
    primitives = part.get('primitives') or []
    if not primitives:
        return None
    points = sample(primitives, sagitta_mm)
    if points is None or len(points) < 2:
        return None
    return np.asarray(points, dtype=float)


def route_segments_3d(record, sagitta_mm=DISPLAY_SAGITTA_3D_MM,
                      transition_step_mm=TRANSITION_3D_STEP_MM):
    """``(m, 2, 3)`` segment array of one routed record, in 2D part order."""
    chunks = []
    for part in record.get('parts') or []:
        kind = part.get('kind')
        if kind == 'flat':
            points = flat_polyline(part, sagitta_mm)
            if points is None:
                continue
            z = float(part['z_mm'])
            polyline = np.column_stack([points, np.full(len(points), z)])
        elif kind == 'transition':
            polyline = transition_polyline(part, transition_step_mm)
        else:
            continue
        if polyline is None or len(polyline) < 2:
            continue
        chunks.append(np.stack([polyline[:-1], polyline[1:]], axis=1))
    if not chunks:
        return None
    return np.concatenate(chunks, axis=0)


def route_segments_xy_z(record, **kwargs):
    """XY projection segments plus the mean height of every segment."""
    segments = route_segments_3d(record, **kwargs)
    if segments is None or not len(segments):
        return None, None
    return segments[:, :, :2], segments[:, :, 2].mean(axis=1)


# --------------------------------------------------------------------------- #
# run loading / discovery
# --------------------------------------------------------------------------- #
def _route_plane(record, run):
    plane = record.get('plane')
    if isinstance(plane, str) and plane.strip().lower() in _PLANE_ORDER:
        return plane.strip().lower()
    layer = record.get('interface_layer')
    try:
        layer = int(layer)
    except (TypeError, ValueError):
        return None
    for name in _PLANE_ORDER:
        if int((run.get('interface_layer') or {}).get(name, -9)) == layer:
            return name
    return None


def load_run(run_dir, require_summary=False):
    """Load one run directory (read-only) into the plotting view model."""
    run_dir = Path(run_dir)
    routes_path = run_dir / 'routes_25d.json'
    if not routes_path.exists():
        raise FileNotFoundError(f'no routes_25d.json under {run_dir}')
    summary_path = run_dir / 'run_summary.json'
    if require_summary and not summary_path.exists():
        raise FileNotFoundError(f'no run_summary.json under {run_dir}')
    payload = _json_load(routes_path)
    if not isinstance(payload, dict) or not isinstance(payload.get('routes'), list):
        raise ValueError(f'{routes_path}: unexpected 2.5D routes payload')
    records = payload['routes']
    routed = [record for record in records if record.get('status') == 'routed']
    n_layers = int(payload.get('n_layers') or 0)
    layers_z = [float(z) for z in (payload.get('layers_z_mm') or [])]
    if n_layers <= 0 and layers_z:
        n_layers = len(layers_z)
    scheme = payload.get('scheme')
    if scheme not in ('A', 'B'):
        name = run_dir.parent.name
        scheme = name[-1].upper() if name.startswith('scheme') else '?'
    if not layers_z:
        layers_z = list(CFG.stack(n_layers))
    interface_layer = payload.get('interface_layer')
    if not isinstance(interface_layer, dict):
        interface_layer = dict(CFG.INTERFACE_LAYER.get(n_layers, {}))
    interface_layer = {str(key).lower(): int(value)
                       for key, value in interface_layer.items()}
    summary = None
    if summary_path.exists():
        try:
            summary = _json_load(summary_path)
        except (OSError, json.JSONDecodeError):
            summary = None
    statistics = {}
    if isinstance(summary, dict) and isinstance(summary.get('statistics'), dict):
        statistics.update(summary['statistics'])
    if isinstance(payload.get('statistics'), dict):
        for key, value in payload['statistics'].items():
            statistics.setdefault(key, value)
    return {
        'run_dir': run_dir,
        'routes_path': routes_path,
        'summary_path': summary_path if summary_path.exists() else None,
        'payload': payload,
        'records': records,
        'routed': routed,
        'n_routed': len(routed),
        'failed': len(records) - len(routed),
        'scheme': scheme,
        'n_layers': n_layers,
        'layers_z_mm': layers_z,
        'interface_layer': interface_layer,
        'topology': payload.get('topology') or 'V2',
        'scheme_label': payload.get('scheme_label') or f'scheme {scheme}',
        'summary': summary,
        'statistics': statistics,
        'is_smoke': run_dir.name.startswith('_'),
        'schema': payload.get('schema'),
    }


def run_label(run):
    if run.get('is_smoke'):
        return '_smoke'
    return f"scheme{run['scheme']}/layers{run['n_layers']}"


def run_title(run):
    return f"scheme {run['scheme']} ({run.get('scheme_label') or '2.5D'}) | {run['n_layers']} layers"


def discover_run_dirs(root):
    """Completed 2.5D runs: scheme{A,B}/layers{3,5} with routes + run_summary."""
    root = Path(root)
    found = []
    for scheme in ('A', 'B'):
        for n_layers in (3, 5):
            run_dir = root / f'scheme{scheme}' / f'layers{n_layers}'
            if ((run_dir / 'routes_25d.json').exists()
                    and (run_dir / 'run_summary.json').exists()):
                found.append(run_dir)
    return found


def _resolve_run_spec(root, spec):
    text = str(spec).strip()
    if not text:
        return None
    if text.lower() in ('smoke', '_smoke'):
        return Path(root) / '_smoke'
    path = Path(text)
    return path if path.is_absolute() else Path(root) / text


def load_connectors(topology, caveats):
    """The 64 frozen MPO connector envelopes (same blocks as the 2D figures)."""
    try:
        from ..fslw import metrics as fslw_metrics
        bundle = fslw_metrics.load_plane_ports(topology or 'V2', 'z1')
    except Exception as exc:  # noqa: BLE001 - a missing port table is a caveat
        caveats.append(f'connectors unavailable: {type(exc).__name__}: {exc}')
        return []
    connectors = (bundle or {}).get('connectors') or []
    if not connectors:
        caveats.append('connectors unavailable: frozen port table returned none')
    return connectors


# --------------------------------------------------------------------------- #
# geometry prepared once per run
# --------------------------------------------------------------------------- #
def prepare_layer_geometry(run):
    """``layer -> [entry]``; entry = route id/plane/part + display polyline."""
    by_layer = {layer: [] for layer in range(run['n_layers'])}
    for record in run['routed']:
        plane = _route_plane(record, run)
        for part in record.get('parts') or []:
            if part.get('kind') != 'flat':
                continue
            layer = int(part.get('layer', -1))
            if layer not in by_layer:
                continue
            points = flat_polyline(part)
            if points is None:
                continue
            by_layer[layer].append({'route_id': record.get('route_id'),
                                    'plane': plane, 'part': part,
                                    'points': points})
    return by_layer


def layer_counts(by_layer, layer):
    entries = by_layer.get(layer) or []
    planes = {'z1': 0, 'z2': 0}
    for entry in entries:
        if entry['plane'] in planes:
            planes[entry['plane']] += 1
    return {
        'layer': int(layer),
        'flat_parts': len(entries),
        'routes_touching': len({entry['route_id'] for entry in entries}),
        'z1_routes': len({entry['route_id'] for entry in entries
                          if entry['plane'] == 'z1'}),
        'z2_routes': len({entry['route_id'] for entry in entries
                          if entry['plane'] == 'z2'}),
        'z1_parts': planes['z1'],
        'z2_parts': planes['z2'],
    }


def _layer_groups(entry_list):
    groups = {plane: [] for plane in _PLANE_ORDER}
    for entry in entry_list:
        if entry['plane'] in groups:
            groups[entry['plane']].append(entry['points'])
    return groups


# --------------------------------------------------------------------------- #
# per-layer 2D diagrams
# --------------------------------------------------------------------------- #
def _draw_layer_panel(ax, run, by_layer, layer, connectors, compact=False):
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D
    entries = by_layer.get(layer) or []
    groups = _layer_groups(entries)
    interface = run['interface_layer']
    linewidth = _linewidth(len(entries))
    handles = []
    for plane in _PLANE_ORDER:
        segments = groups.get(plane) or []
        if not segments:
            continue
        colour = _plane_colour(plane, layer, interface)
        is_interface = int(interface.get(plane, -1)) == layer
        ax.add_collection(LineCollection(
            segments, colors=[colour], linewidths=linewidth, alpha=0.88,
            zorder=3 if is_interface else 4))
        route_count = len({entry['route_id'] for entry in entries
                           if entry['plane'] == plane})
        label = f'{plane}: {route_count} routes, {len(segments)} flat parts'
        if not is_interface:
            label += ' (travel layer)'
        handles.append(Line2D([0], [0], color=colour, linewidth=1.6,
                              label=label))
    _board_frame(ax)
    draw_connectors(ax, connectors, depth_mm=3.0,
                    label_fontsize=3.0 if compact else 4.2)
    if handles:
        ax.legend(handles=handles, loc='upper left',
                  fontsize=6.2 if compact else 7.0, framealpha=0.85)
    ax.tick_params(labelsize=6.5 if compact else 7.0)
    return layer_counts(by_layer, layer)


def _layer_title(run, counts):
    layer = counts['layer']
    z = float(run['layers_z_mm'][layer])
    lines = [
        f"layer {layer} | z = {z:.3f} mm | {counts['flat_parts']} flat parts | "
        f"{counts['routes_touching']} routed routes touch this layer",
        f"scheme {run['scheme']} ({run.get('scheme_label') or '2.5D'}) | "
        f"{run['n_layers']} layers | {run['n_routed']}/{TOTAL_CONNECTIONS} routed",
        f"z1-plane {counts['z1_routes']} routes, z2-plane {counts['z2_routes']} "
        f"routes | z1 blue #1565c0, z2 red #c62828",
        'interface layers full saturation, intermediate travel layers lightened '
        '| flat parts plotted as stored (transitions in view3d.png)',
    ]
    return '\n'.join(lines)


def render_layer(run, by_layer, layer, output_path, connectors):
    plt = pyplot()
    fig, ax = plt.subplots(figsize=(11.0, 10.2))
    counts = _draw_layer_panel(ax, run, by_layer, layer, connectors,
                               compact=False)
    ax.set_title(_layer_title(run, counts), fontsize=9.0)
    _save(fig, output_path)
    return {
        'file': str(output_path),
        'kind': 'layer_2d',
        'run': run_label(run),
        'layer': int(layer),
        'z_mm': float(run['layers_z_mm'][layer]),
        'description': (f"2D diagram of layer {layer} (z="
                        f"{float(run['layers_z_mm'][layer]):.3f} mm): "
                        f"{counts['flat_parts']} flat parts, "
                        f"{counts['routes_touching']} routes touching the layer"),
        'counts': counts,
    }


def _layer_table_lines(run, by_layer):
    interface = run['interface_layer']
    lines = [
        f"scheme {run['scheme']} ({run.get('scheme_label') or '2.5D'})",
        f"{run['n_layers']} layers = " + ', '.join(
            f"{float(z):g}" for z in run['layers_z_mm']) + ' mm',
        f"interface: z1 -> layer {interface.get('z1')}, "
        f"z2 -> layer {interface.get('z2')}",
        f"{run['n_routed']}/{TOTAL_CONNECTIONS} routed",
        '',
        'layer   z (mm)   flat parts   routes',
        '-----   ------   ----------   ------',
    ]
    for layer in range(run['n_layers']):
        counts = layer_counts(by_layer, layer)
        interface_note = ''
        for plane in _PLANE_ORDER:
            if int(interface.get(plane, -1)) == layer:
                interface_note = f'  <- {plane} interface'
        lines.append(f"{layer:>5}   {float(run['layers_z_mm'][layer]):>6.3f}   "
                     f"{counts['flat_parts']:>10}   "
                     f"{counts['routes_touching']:>6}{interface_note}")
    lines.extend(['', 'colour: z1 plane blue #1565c0,',
                  '        z2 plane red #c62828',
                  'interface layers full saturation,',
                  'travel layers lightened 45 %'])
    return lines


def render_layers_2d(run, by_layer, output_path, connectors):
    """One panel per layer in a single figure (+ a small layer table panel)."""
    plt = pyplot()
    count = run['n_layers']
    columns = 3 if count > 1 else 1
    rows = max(1, int(math.ceil(count / columns)))
    fig, axes = plt.subplots(rows, columns,
                             figsize=(6.6 * columns, 6.5 * rows + 0.9),
                             squeeze=False)
    panel_counts = []
    for index in range(rows * columns):
        ax = axes[index // columns][index % columns]
        if index < count:
            counts = _draw_layer_panel(ax, run, by_layer, index, connectors,
                                       compact=True)
            panel_counts.append(counts)
            z = float(run['layers_z_mm'][index])
            interface_note = ''
            for plane in _PLANE_ORDER:
                if int(run['interface_layer'].get(plane, -1)) == index:
                    interface_note = f' | {plane} interface'
            ax.set_title(f"layer {index} | z = {z:.3f} mm | "
                         f"{counts['flat_parts']} flat parts | "
                         f"{counts['routes_touching']} routes{interface_note}",
                         fontsize=8.5)
        elif index == count:
            ax.axis('off')
            ax.text(0.0, 1.0, '\n'.join(_layer_table_lines(run, by_layer)),
                    ha='left', va='top', fontsize=7.4, family='monospace')
            ax.set_title('layer stack summary', fontsize=8.5)
        else:
            ax.axis('off')
    fig.suptitle(
        f"scheme {run['scheme']} ({run.get('scheme_label') or '2.5D'}) | "
        f"{run['n_layers']} layers | flat parts per layer on the 150 x 150 mm "
        f"board | {run['n_routed']}/{TOTAL_CONNECTIONS} routed\n"
        f"all flat parts plotted exactly as stored | colour = plane "
        f"(z1 blue #1565c0 / z2 red #c62828) | interface layers saturated, "
        f"travel layers lightened | transitions shown in view3d.png",
        fontsize=10.0)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    _save(fig, output_path, tight=False)
    return {
        'file': str(output_path),
        'kind': 'layers_2d',
        'run': run_label(run),
        'description': (f"all {run['n_layers']} layers as 2D panels "
                        f"(flat parts, plane colouring)"),
        'layers': panel_counts,
    }


# --------------------------------------------------------------------------- #
# full 3D visualisation
# --------------------------------------------------------------------------- #
def _board_3d(ax, layers_z):
    z_lo, z_hi = float(min(layers_z)), float(max(layers_z))
    for z, colour in ((z_lo, PLANE_COLORS['z1']), (z_hi, PLANE_COLORS['z2'])):
        xs = [0.0, BOARD_MM, BOARD_MM, 0.0, 0.0]
        ys = [0.0, 0.0, BOARD_MM, BOARD_MM, 0.0]
        ax.plot(xs, ys, [z] * 5, color=colour, linewidth=1.1,
                linestyle='--', alpha=0.9)
    for x, y in ((0.0, 0.0), (BOARD_MM, 0.0), (BOARD_MM, BOARD_MM),
                 (0.0, BOARD_MM)):
        ax.plot([x, x], [y, y], [z_lo, z_hi], color='#666666', linewidth=0.7,
                linestyle=':', alpha=0.9)
    return z_lo, z_hi


def render_view3d(run, output_path):
    plt = pyplot()
    from mpl_toolkits.mplot3d.art3d import Line3DCollection
    from matplotlib.lines import Line2D
    fig = plt.figure(figsize=(16.0, 9.6))
    ax = fig.add_subplot(111, projection='3d')
    ax.set_position([-0.02, -0.17, 1.02, 1.23])
    per_plane = {}
    for plane in _PLANE_ORDER:
        chunks = []
        for record in run['routed']:
            if _route_plane(record, run) != plane:
                continue
            segments = route_segments_3d(record)
            if segments is not None and len(segments):
                chunks.append(segments)
        if chunks:
            segments = np.concatenate(chunks, axis=0)
            per_plane[plane] = int(len(segments))
            ax.add_collection3d(Line3DCollection(
                segments, colors=PLANE_COLORS[plane], linewidths=0.30,
                alpha=0.65, zorder=3))
        else:
            per_plane[plane] = 0
    z_lo, z_hi = _board_3d(ax, run['layers_z_mm'])
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
    stats = run['statistics']
    lifted = int(stats.get('lifted') or 0)
    transitions = int(stats.get('transitions') or 0)
    handles = [Line2D([0], [0], color=PLANE_COLORS[plane], linewidth=2.0,
                      label=f'{plane} plane routes')
               for plane in _PLANE_ORDER]
    ax.legend(handles=handles, loc='upper left', fontsize=8.0, framealpha=0.85)
    fig.suptitle(
        f"scheme {run['scheme']} ({run.get('scheme_label') or '2.5D'}) | "
        f"{run['n_layers']} layers | {run['n_routed']}/{TOTAL_CONNECTIONS} routed "
        f"| 3D centerline view\n"
        f"z1 plane at {float(run['layers_z_mm'][int(run['interface_layer'].get('z1', 0))]):.3f} mm "
        f"(blue), z2 plane at "
        f"{float(run['layers_z_mm'][int(run['interface_layer'].get('z2', run['n_layers'] - 1))]):.3f} mm "
        f"(red) | {lifted} lifted routes, {transitions} vertical S-transitions\n"
        f"flat parts + two-arc R=40 mm transitions plotted as stored | "
        f"vertical scale exaggerated ~{exaggeration:.0f}x for display",
        fontsize=10.0, y=0.985)
    _save(fig, output_path, tight=False)
    return {
        'file': str(output_path),
        'kind': 'view3d',
        'run': run_label(run),
        'description': (f"3D centerline view of {run['n_routed']} routed routes "
                        f"(plane colouring, z exaggerated ~{exaggeration:.0f}x)"),
        'segments': per_plane,
        'z_exaggeration': round(exaggeration, 1),
    }


def render_top_view_by_height(run, output_path, connectors):
    plt = pyplot()
    from matplotlib import colormaps
    from matplotlib.cm import ScalarMappable
    from matplotlib.collections import LineCollection
    from matplotlib.colors import Normalize
    fig, ax = plt.subplots(figsize=(11.0, 10.4))
    chunks = []
    height_chunks = []
    for record in run['routed']:
        segments, heights = route_segments_xy_z(record)
        if segments is None or not len(segments):
            continue
        chunks.append(segments)
        height_chunks.append(heights)
    z_top = float(max(run['layers_z_mm']))
    norm = Normalize(vmin=0.0, vmax=max(z_top, 1e-9))
    cmap = colormaps['plasma']
    if chunks:
        segments = np.concatenate(chunks, axis=0)
        heights = np.concatenate(height_chunks, axis=0)
        ax.add_collection(LineCollection(
            segments, colors=cmap(norm(heights)),
            linewidths=_linewidth(len(run['routed'])), alpha=0.90, zorder=3))
    _board_frame(ax)
    draw_connectors(ax, connectors, depth_mm=3.0, label_fontsize=4.2)
    scalar = ScalarMappable(norm=norm, cmap=cmap)
    bar = fig.colorbar(scalar, ax=ax)
    bar.set_label('3D path height z (mm)')
    bar.set_ticks([float(z) for z in run['layers_z_mm']])
    bar.ax.set_yticklabels([f'{float(z):.3f}' for z in run['layers_z_mm']])
    stats = run['statistics']
    lifted = int(stats.get('lifted') or 0)
    transitions = int(stats.get('transitions') or 0)
    ax.set_title(
        f"scheme {run['scheme']} ({run.get('scheme_label') or '2.5D'}) | "
        f"XY top view coloured by 3D height z | {run['n_routed']}/{TOTAL_CONNECTIONS} "
        f"routed\n"
        f"{run['n_layers']} layers, z = 0.000-{z_top:.3f} mm | z1 plane blue-low, "
        f"z2 plane yellow-high | {lifted} lifted routes ({transitions} transitions) "
        f"run at intermediate heights\n"
        f"colours come from the stored 3D path (flat parts + S-transitions) | "
        f"height scale in mm, board axes unchanged",
        fontsize=9.5)
    _save(fig, output_path)
    return {
        'file': str(output_path),
        'kind': 'top_view_by_height',
        'run': run_label(run),
        'description': (f"XY top view of {run['n_routed']} routed routes coloured "
                        f"by height z (plasma colorbar)"),
    }


# --------------------------------------------------------------------------- #
# frozen 2D baseline vs 2.5D final comparison
# --------------------------------------------------------------------------- #
def baseline_plane_dir(scheme, plane):
    spec = CFG.SCHEMES[scheme]
    return (Path(spec['baseline_root']) / 'planes' / 'V2'
            / spec['baseline_algorithm'] / plane)


def _load_baseline_panel(run_dir):
    from ..v2opt import plots_ortho90 as v2_compare
    return v2_compare._load_panel(Path(run_dir))


def _baseline_panel_titles(scheme, plane, routed):
    if scheme == 'A':
        return (f'V2-BEST plane {plane} | {routed}/512 routed',
                'original D56 layout (contains non-90 short-S arcs)')
    return (f'ORTHO90 plane {plane} | {routed}/512 routed',
            'pure orthogonal: only exact 90-deg quarter arcs')


def _height_panel(ax, run, plane, norm, cmap, connectors):
    from matplotlib.collections import LineCollection
    chunks, height_chunks = [], []
    count = 0
    for record in run['routed']:
        if _route_plane(record, run) != plane:
            continue
        count += 1
        segments, heights = route_segments_xy_z(record)
        if segments is None or not len(segments):
            continue
        chunks.append(segments)
        height_chunks.append(heights)
    if chunks:
        segments = np.concatenate(chunks, axis=0)
        heights = np.concatenate(height_chunks, axis=0)
        ax.add_collection(LineCollection(
            segments, colors=cmap(norm(heights)),
            linewidths=_linewidth(count), alpha=0.90, zorder=3))
    _board_frame(ax)
    draw_connectors(ax, connectors, depth_mm=3.0, label_fontsize=4.2)
    ax.tick_params(labelsize=7.0)
    return count


def render_baseline_vs_25d(run, output_path, connectors, caveats):
    """2 x 2 comparison (top: frozen 2D per plane, bottom: 2.5D top view) + bars."""
    plt = pyplot()
    from matplotlib import colormaps
    from matplotlib.cm import ScalarMappable
    from matplotlib.colors import Normalize
    from ..v2opt import plots_ortho90 as v2_compare

    scheme = run['scheme']
    old_panels, old_counts = {}, {}
    for plane in _PLANE_ORDER:
        panel_dir = baseline_plane_dir(scheme, plane)
        if not (panel_dir / 'routes.json').exists():
            raise FileNotFoundError(f'frozen 2D baseline missing: {panel_dir}')
        panel = _load_baseline_panel(panel_dir)
        old_panels[plane] = panel
        old_counts[plane] = len(panel['routed'])
    baseline_total = sum(old_counts.values())
    expected = int(CFG.SCHEMES[scheme]['baseline_routed'])
    if baseline_total != expected:
        caveats.append(
            f'scheme {scheme}: frozen baseline routed {baseline_total} != '
            f'expected {expected}')
    final_counts = {}
    for plane in _PLANE_ORDER:
        final_counts[plane] = sum(1 for record in run['routed']
                                  if _route_plane(record, run) == plane)
    final_total = sum(final_counts.values())
    stats = run['statistics']
    lifted = int(stats.get('lifted') or 0)
    transitions = int(stats.get('transitions') or 0)
    z_top = float(max(run['layers_z_mm']))
    norm = Normalize(vmin=0.0, vmax=max(z_top, 1e-9))
    cmap = colormaps['plasma']

    fig = plt.figure(figsize=(20.0, 23.0))
    grid = fig.add_gridspec(4, 2, height_ratios=[1.0, 1.0, 0.10, 0.30],
                            hspace=0.22, wspace=0.085, left=0.07,
                            right=0.945, top=0.93, bottom=0.05)
    for column, plane in enumerate(_PLANE_ORDER):
        ax = fig.add_subplot(grid[0, column])
        title, subtitle = _baseline_panel_titles(scheme, plane,
                                                 old_counts[plane])
        v2_compare._draw_panel(ax, old_panels[plane], title, subtitle,
                               linewidth=0.40, show_legend=True)
    for column, plane in enumerate(_PLANE_ORDER):
        ax = fig.add_subplot(grid[1, column])
        count = _height_panel(ax, run, plane, norm, cmap, connectors)
        ax.set_title(
            f"2.5D final plane {plane} | {count}/512 routed "
            f"({count / PLANE_TOTAL:.1%}) | top view, colour = height\n"
            f"scheme {run['scheme']}, {run['n_layers']} layers | XY projection "
            f"of flat parts + S-transitions | shape stored, not altered",
            fontsize=9.5)
    cax = fig.add_subplot(grid[2, :])
    bar = fig.colorbar(ScalarMappable(norm=norm, cmap=cmap), cax=cax,
                       orientation='horizontal')
    bar.set_label('height z (mm)', fontsize=8.5)
    bar.set_ticks([float(z) for z in run['layers_z_mm']])
    bar.ax.set_xticklabels([f'{float(z):.3f}' for z in run['layers_z_mm']])

    ax_bar = fig.add_subplot(grid[3, :])
    labels = ['2D baseline', '2.5D final']
    values = [baseline_total, final_total]
    bars = ax_bar.barh([0, 1], values, height=0.55,
                       color=[BASELINE_COLOR, FINAL_COLOR], alpha=0.92,
                       edgecolor='#222222', linewidth=0.5)
    for bar_item, value in zip(bars, values):
        ax_bar.text(value + 12.0, bar_item.get_y() + bar_item.get_height() / 2.0,
                    f'{value}/{TOTAL_CONNECTIONS} ({value / TOTAL_CONNECTIONS:.1%})',
                    va='center', fontsize=10.0)
    ax_bar.axvline(TOTAL_CONNECTIONS, color='#333333', linewidth=0.8,
                   linestyle='--')
    ax_bar.set_xlim(0.0, TOTAL_CONNECTIONS * 1.16)
    ax_bar.set_yticks([0, 1])
    ax_bar.set_yticklabels(labels, fontsize=9.5)
    ax_bar.set_xlabel('routed connections (of 1024)', fontsize=8.5)
    ax_bar.grid(True, axis='x', alpha=0.28, linewidth=0.5)
    ax_bar.set_title(
        f"Routed totals, scheme {run['scheme']} "
        f"({CFG.SCHEMES[scheme]['baseline_algorithm']} baseline): "
        f"{baseline_total}/1024 original 2D -> {final_total}/1024 2.5D final "
        f"(+{final_total - baseline_total})\n"
        f"top row: frozen 2D per plane (geometry-type colour: line=blue, "
        f"arc=red) | bottom row: 2.5D final per plane top view (colour = height)",
        fontsize=9.5)

    fig.suptitle(
        f"V2 dual-height 1024 layout: original 2D routing vs 2.5D final "
        f"(scheme {run['scheme']}, {run['n_layers']} layers)\n"
        f"route shapes plotted exactly as stored | baseline z1/z2 = "
        f"{old_counts['z1']}/{old_counts['z2']}, final z1/z2 = "
        f"{final_counts['z1']}/{final_counts['z2']} | lifted routes {lifted}, "
        f"vertical transitions {transitions}\n"
        f"frozen 2D baseline: "
        f"{CFG.SCHEMES[scheme]['baseline_root'].name} / "
        f"V2 / {CFG.SCHEMES[scheme]['baseline_algorithm']}",
        fontsize=13.0)
    _save(fig, output_path, tight=False)
    return {
        'file': str(output_path),
        'kind': 'baseline_vs_25d',
        'run': run_label(run),
        'description': (f"frozen 2D baseline {baseline_total}/1024 vs 2.5D final "
                        f"{final_total}/1024 (2x2 per-plane panels + routed bars)"),
        'baseline_total': baseline_total,
        'final_total': final_total,
        'baseline_per_plane': old_counts,
        'final_per_plane': final_counts,
    }


# --------------------------------------------------------------------------- #
# cross-run statistics
# --------------------------------------------------------------------------- #
def _runs_by_scheme(runs):
    table = {}
    for run in runs:
        table.setdefault(run['scheme'], {})[run['n_layers']] = run
    return table


def render_layers_effect(runs, output_path):
    plt = pyplot()
    table = _runs_by_scheme(runs)
    schemes = [scheme for scheme in ('A', 'B') if scheme in table]
    schemes += [scheme for scheme in sorted(table) if scheme not in schemes]
    fig, ax = plt.subplots(figsize=(10.5, 6.4))
    positions = np.arange(len(schemes), dtype=float)
    width = 0.26
    short = {'A': 'D56 short-S', 'B': 'pure ortho 90'}

    def routed_of(run):
        return None if run is None else int(run['statistics'].get('routed')
                                            or run['n_routed'])

    columns = [
        ('2D baseline (frozen)',
         lambda scheme: int(CFG.SCHEMES.get(scheme, {}).get('baseline_routed', 0)),
         BASELINE_COLOR),
        ('3-layer 2.5D',
         lambda scheme: routed_of(table[scheme].get(3)),
         None),
        ('5-layer 2.5D',
         lambda scheme: routed_of(table[scheme].get(5)),
         None),
    ]
    shade = {'2D baseline (frozen)': 0.0, '3-layer 2.5D': 0.45,
             '5-layer 2.5D': 0.0}
    labelled = set()
    for offset, (label, getter, colour) in zip((-width, 0.0, width), columns):
        for index, scheme in enumerate(schemes):
            value = getter(scheme)
            if value is None:
                ax.text(positions[index] + offset, 14.0, 'n/a', ha='center',
                        va='bottom', fontsize=7.0, color='#777777',
                        rotation=90)
                continue
            bar_colour = colour or _blend_hex(
                SCHEME_COLORS.get(scheme, '#555555'), '#ffffff',
                shade[label])
            bars = ax.bar(positions[index] + offset, value, width=width,
                          color=bar_colour, edgecolor='#222222',
                          linewidth=0.4,
                          label=label if label not in labelled else None)
            labelled.add(label)
            ax.bar_label(bars, fmt='%d', fontsize=7.5, padding=2)
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(handles, labels, fontsize=8.0, loc='upper left',
                  framealpha=0.9)
    ax.axhline(TOTAL_CONNECTIONS, color='#333333', linewidth=0.8,
               linestyle='--')
    ax.text(len(schemes) - 0.55, TOTAL_CONNECTIONS + 8.0,
            f'{TOTAL_CONNECTIONS} connections', fontsize=7.5, ha='right')
    ax.set_xticks(positions)
    ax.set_xticklabels([f"scheme {scheme}\n({short.get(scheme, '2.5D')})"
                        for scheme in schemes], fontsize=9.0)
    ax.set_ylabel('routed connections', fontsize=9.0)
    ax.set_ylim(0.0, TOTAL_CONNECTIONS * 1.12)
    ax.grid(True, axis='y', alpha=0.28, linewidth=0.5)
    ordered = sorted(runs, key=lambda item: (item['scheme'], item['n_layers']))
    run_totals = ', '.join(f"{run['scheme']}{run['n_layers']} {run['n_routed']}"
                           for run in ordered)
    if any(run.get('is_smoke') for run in runs):
        run_totals += ' (includes debug sample)'
    ax.set_title(
        'Routed connections: 2D baseline vs 3-layer vs 5-layer 2.5D\n'
        'per scheme | strict 2D rules on every layer + true 3D clearance '
        '>= 0.08 mm\n'
        f'run totals: {run_totals} | maximum {TOTAL_CONNECTIONS} connections',
        fontsize=9.5)
    _save(fig, output_path)
    return {
        'file': str(output_path),
        'kind': 'layers_effect',
        'run': None,
        'description': ('routed counts: frozen 2D baseline vs 3-layer vs '
                        '5-layer 2.5D, per scheme'),
        'values': {
            scheme: {
                'baseline': int(CFG.SCHEMES.get(scheme, {}).get(
                    'baseline_routed', 0)),
                'layers3': routed_of(table[scheme].get(3)),
                'layers5': routed_of(table[scheme].get(5)),
            }
            for scheme in schemes
        },
    }


def _runs_sorted(runs):
    order = {'A': 0, 'B': 1}
    return sorted(runs, key=lambda run: (order.get(run['scheme'], 9),
                                         run['n_layers']))


def render_lift_statistics(runs, output_path):
    plt = pyplot()
    ordered = _runs_sorted(runs)
    fig, axes = plt.subplots(1, 2, figsize=(13.0, 5.6))
    for ax, key, title, colour in (
            (axes[0], 'lifted', 'Lifted routes (raised to a travel layer)', '#5e35b1'),
            (axes[1], 'transitions', 'Vertical S-transitions (two per lifted route)', '#00897b')):
        values = [int(run['statistics'].get(key) or 0) for run in ordered]
        labels = [f"{run['scheme']}/{run['n_layers']}L"
                  + (' (smoke)' if run.get('is_smoke') else '')
                  for run in ordered]
        colours = []
        for run in ordered:
            base = SCHEME_COLORS.get(run['scheme'], '#555555')
            colours.append(_blend_hex(base, '#ffffff', 0.30)
                           if run['n_layers'] == 3 else base)
        bars = ax.bar(np.arange(len(ordered)), values, color=colours,
                      edgecolor='#222222', linewidth=0.5, width=0.62)
        ax.bar_label(bars, fmt='%d', fontsize=8.0, padding=2)
        ax.set_xticks(np.arange(len(ordered)))
        ax.set_xticklabels(labels, rotation=0 if len(labels) <= 6 else 25,
                           ha='center' if len(labels) <= 6 else 'right',
                           fontsize=8.0)
        ax.set_ylabel('count', fontsize=8.5)
        ax.grid(True, axis='y', alpha=0.28, linewidth=0.5)
        if values and max(values) > 0:
            ax.set_ylim(0.0, max(values) * 1.22)
        ax.set_title(f'{title} | total {sum(values)}', fontsize=9.5)
        ax.text(0.02, 0.97, '\n'.join(
            f"{run['scheme']}/{run['n_layers']}L: lifted="
            f"{int(run['statistics'].get('lifted') or 0)}, "
            f"new={int(run['statistics'].get('new_routed') or 0)}, "
            f"flat_added={int(run['statistics'].get('flat_added') or 0)}"
            for run in ordered),
            transform=ax.transAxes, ha='left', va='top', fontsize=6.8,
            family='monospace',
            bbox=dict(boxstyle='round,pad=0.25', facecolor='white',
                      alpha=0.80, edgecolor='#cccccc'))
    total_lifted = sum(int(run['statistics'].get('lifted') or 0) for run in ordered)
    total_transitions = sum(int(run['statistics'].get('transitions') or 0)
                            for run in ordered)
    fig.suptitle(
        '2.5D lift statistics: routes raised to an intermediate travel layer '
        'and their vertical S-transitions\n'
        f'{len(ordered)} run(s) | total lifted {total_lifted}, total transitions '
        f'{total_transitions} | flat baseline routes keep their 2D height '
        f'(no vertical transition)', fontsize=10.5)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.91))
    _save(fig, output_path, tight=False)
    return {
        'file': str(output_path),
        'kind': 'lift_statistics',
        'run': None,
        'description': ('lifted routes and vertical transition counts per run '
                        '(2 panels)'),
        'total_lifted': total_lifted,
        'total_transitions': total_transitions,
    }


# --------------------------------------------------------------------------- #
# manifest
# --------------------------------------------------------------------------- #
def run_manifest_entry(root, run):
    statistics = run['statistics']
    entry = {
        'run': run_label(run),
        'scheme': run['scheme'],
        'n_layers': run['n_layers'],
        'layers_z_mm': [float(z) for z in run['layers_z_mm']],
        'interface_layer': {key: int(value)
                            for key, value in run['interface_layer'].items()},
        'is_smoke': bool(run.get('is_smoke')),
        'run_dir': _rel(root, run['run_dir']),
        'routes_file': _rel(root, run['routes_path']),
        'routes_sha256': _sha256(run['routes_path']),
        'summary_file': (_rel(root, run['summary_path'])
                         if run.get('summary_path') else None),
        'routed': int(run['n_routed']),
        'failed': int(run['failed']),
        'baseline_routed': int(statistics.get('baseline_routed') or 0),
        'new_routed': int(statistics.get('new_routed') or 0),
        'lifted': int(statistics.get('lifted') or 0),
        'flat_added': int(statistics.get('flat_added') or 0),
        'transitions': int(statistics.get('transitions') or 0),
        'per_plane': statistics.get('per_plane'),
        'per_layer_flat_parts': statistics.get('per_layer_flat_parts'),
    }
    return entry


def write_manifest(root, manifest_path, runs, new_files, caveats):
    root = Path(root)
    manifest_path = Path(manifest_path)
    existing = {}
    if manifest_path.exists():
        try:
            existing = _json_load(manifest_path)
        except (OSError, json.JSONDecodeError):
            existing = {}
    files_by_path = {}
    for entry in existing.get('files') or []:
        rel = entry.get('file')
        if rel and (root / rel).exists():
            files_by_path[rel] = entry
    for entry in new_files:
        rel = entry['file']
        entry = dict(entry)
        entry['file'] = rel
        files_by_path[rel] = entry
    runs_by_label = {}
    for entry in existing.get('runs') or []:
        label = entry.get('run')
        if label:
            runs_by_label[label] = entry
    for run in runs:
        runs_by_label[run_label(run)] = run_manifest_entry(root, run)
    merged_caveats = []
    for text in list(existing.get('caveats') or []) + list(caveats or []):
        if text not in merged_caveats:
            merged_caveats.append(text)
    payload = {
        'schema': SCHEMA_PLOTS,
        'tool': TOOL,
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'root': str(root),
        'style': {
            'board_mm': BOARD_MM,
            'dpi': DPI,
            'plane_colors': dict(PLANE_COLORS),
            'geometry_type_colors': {'line': LINE_COLOR, 'arc': ARC_COLOR},
            'display_sagitta_mm': DISPLAY_SAGITTA_MM,
            'display_sagitta_3d_mm': DISPLAY_SAGITTA_3D_MM,
            'transition_display_step_mm': TRANSITION_DISPLAY_STEP_MM,
            'transition_3d_step_mm': TRANSITION_3D_STEP_MM,
            'connectors': '64 frozen MPO envelopes (fslw.ports.load_plane V2)',
            'labels': 'English only (no CJK glyphs in figures)',
        },
        'runs': sorted(runs_by_label.values(), key=lambda entry: entry['run']),
        'files': sorted(files_by_path.values(), key=lambda entry: entry['file']),
        'caveats': merged_caveats,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    _guard_write(manifest_path)
    manifest_path.write_text(json.dumps(payload, indent=1, ensure_ascii=False),
                             encoding='utf-8')
    return payload


# --------------------------------------------------------------------------- #
# per-run rendering
# --------------------------------------------------------------------------- #
def figure_dir_for(root, run, in_run_dir=False):
    if in_run_dir:
        return Path(run['run_dir'])
    root = Path(root)
    if run.get('is_smoke'):
        return root / 'figures' / '_smoke'
    return root / 'figures' / f"scheme{run['scheme']}" / f"layers{run['n_layers']}"


def render_run_figures(root, run, connectors, in_run_dir, caveats):
    """All per-run figures; returns the manifest entries."""
    figures_dir = figure_dir_for(root, run, in_run_dir=in_run_dir)
    figures_dir.mkdir(parents=True, exist_ok=True)
    by_layer = prepare_layer_geometry(run)
    # transition formula cross-check (display rebuild vs stored fields)
    worst = 0.0
    for record in run['routed']:
        for part in record.get('parts') or []:
            if part.get('kind') == 'transition':
                worst = max(worst, transition_consistency(part))
    if worst > 1e-6:
        caveats.append(f"{run_label(run)}: transition schema deviation "
                       f"{worst:.3g} mm (display rebuild vs stored fields)")

    entries = []
    for layer in range(run['n_layers']):
        output_path = figures_dir / f'layer_{layer}.png'
        info = render_layer(run, by_layer, layer, output_path, connectors)
        info['file'] = _rel(root, output_path)
        entries.append(info)
        print(f"[plots25d] {info['file']}")
    output_path = figures_dir / 'layers_2d.png'
    info = render_layers_2d(run, by_layer, output_path, connectors)
    info['file'] = _rel(root, output_path)
    entries.append(info)
    print(f"[plots25d] {info['file']}")
    output_path = figures_dir / 'view3d.png'
    info = render_view3d(run, output_path)
    info['file'] = _rel(root, output_path)
    entries.append(info)
    print(f"[plots25d] {info['file']}")
    output_path = figures_dir / 'top_view_by_height.png'
    info = render_top_view_by_height(run, output_path, connectors)
    info['file'] = _rel(root, output_path)
    entries.append(info)
    print(f"[plots25d] {info['file']}")
    return entries


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _build_parser():
    parser = argparse.ArgumentParser(
        description='Render V2 five-layer (2.5D) figures (read-only inputs).')
    parser.add_argument('--root', default=None,
                        help='2.5D output root (default: '
                             'outputs/four_side_1024_v2_25d_v01)')
    parser.add_argument('--runs', default=None,
                        help='comma separated run dirs, e.g. '
                             'schemeA/layers3,schemeB/layers5 or smoke')
    parser.add_argument('--include-smoke', action='store_true',
                        help='also render the _smoke debug sample')
    parser.add_argument('--in-run-dir', action='store_true',
                        help='write per-run figures into the run dir instead of '
                             'figures/<scheme>/layers<n>/ (default: off, the '
                             'figures/ tree only)')
    parser.add_argument('--skip-comparison', action='store_true',
                        help='skip baseline_vs_25d_scheme*.png')
    parser.add_argument('--skip-stats', action='store_true',
                        help='skip layers_effect.png / lift_statistics.png')
    parser.add_argument('--verbose', action='store_true')
    return parser


def _select_runs(root, args, caveats):
    root = Path(root)
    if args.runs:
        specs = [item.strip() for item in str(args.runs).split(',')
                 if item.strip()]
    else:
        specs = [str(path) for path in discover_run_dirs(root)]
        if not specs:
            smoke = root / '_smoke'
            if (smoke / 'routes_25d.json').exists():
                specs = [str(smoke)]
                print('[plots25d] no completed full run found, falling back to '
                      'the _smoke sample')
            else:
                raise SystemExit(f'no 2.5D runs found under {root}')
        elif args.include_smoke:
            smoke = root / '_smoke'
            if (smoke / 'routes_25d.json').exists():
                specs.append(str(smoke))
    runs = []
    for spec in specs:
        run_dir = _resolve_run_spec(root, spec)
        if run_dir is None:
            continue
        try:
            runs.append(load_run(run_dir))
        except (OSError, ValueError, KeyError) as exc:
            message = f'{spec}: skipped ({type(exc).__name__}: {exc})'
            print(f'[plots25d] WARNING {message}')
            caveats.append(message)
    if not runs:
        raise SystemExit(f'no loadable 2.5D run under {root}')
    return runs


def main(argv=None):
    args = _build_parser().parse_args(argv)
    root = Path(args.root) if args.root else Path(DEFAULT_ROOT)
    root = root.resolve()
    started = time.perf_counter()
    caveats = []
    _apply_style()
    runs = _select_runs(root, args, caveats)
    topology = runs[0].get('topology') or 'V2'
    connectors = load_connectors(topology, caveats)
    manifest_files = []
    for run in runs:
        print(f"[plots25d] run {run_label(run)}: {run['n_routed']} routed, "
              f"{run['n_layers']} layers <- {run['run_dir']}")
        try:
            manifest_files.extend(render_run_figures(
                root, run, connectors, args.in_run_dir, caveats))
        except Exception as exc:  # noqa: BLE001 - report, keep other runs
            message = (f"{run_label(run)}: per-run figures failed "
                       f"({type(exc).__name__}: {exc})")
            print(f'[plots25d] ERROR {message}')
            caveats.append(message)
            if args.verbose:
                raise
    comparison_dir = root / 'comparison'
    comparison_dir.mkdir(parents=True, exist_ok=True)
    if not args.skip_comparison:
        schemes = []
        for run in runs:
            if run['scheme'] not in schemes:
                schemes.append(run['scheme'])
        for scheme in schemes:
            candidates = [run for run in runs if run['scheme'] == scheme]
            full_runs = [run for run in candidates if not run.get('is_smoke')]
            pool = full_runs or candidates
            final = max(pool, key=lambda run: run['n_layers'])
            output_path = comparison_dir / f'baseline_vs_25d_scheme{scheme}.png'
            try:
                info = render_baseline_vs_25d(final, output_path, connectors,
                                              caveats)
            except Exception as exc:  # noqa: BLE001 - baseline may be absent
                message = (f'baseline_vs_25d_scheme{scheme}: skipped '
                           f'({type(exc).__name__}: {exc})')
                print(f'[plots25d] WARNING {message}')
                caveats.append(message)
                continue
            info['file'] = _rel(root, output_path)
            manifest_files.append(info)
            print(f"[plots25d] {info['file']}")
    if not args.skip_stats and runs:
        for renderer, name in ((render_layers_effect, 'layers_effect.png'),
                               (render_lift_statistics, 'lift_statistics.png')):
            output_path = comparison_dir / name
            try:
                info = renderer(runs, output_path)
            except Exception as exc:  # noqa: BLE001
                message = (f'{name}: skipped ({type(exc).__name__}: {exc})')
                print(f'[plots25d] WARNING {message}')
                caveats.append(message)
                continue
            info['file'] = _rel(root, output_path)
            manifest_files.append(info)
            print(f"[plots25d] {info['file']}")
    manifest_path = comparison_dir / 'plots_manifest.json'
    manifest_files.append({
        'file': _rel(root, manifest_path),
        'kind': 'plots_manifest',
        'run': None,
        'description': 'inventory of every figure generated by plots25d',
    })
    manifest = write_manifest(root, manifest_path, runs, manifest_files, caveats)
    print(json.dumps({
        'tool': TOOL,
        'root': str(root),
        'runs': [run_label(run) for run in runs],
        'files': len(manifest_files),
        'caveats': caveats,
        'wall_seconds': round(time.perf_counter() - started, 2),
    }, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
