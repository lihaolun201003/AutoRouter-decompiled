"""R9 corrected L1-L5 physical-model figures (L3D round).

The corrected model (``four_side_1024/l3d/SCHEMA_L3D.md``):

* **L1 is the interface routing layer and contains BOTH port rows** - z1 row at
  physical z = 0.0 mm, z2 row at physical z = 0.5 mm (0.5 mm real height
  difference).  The old 2.5D model wrongly put z1 on L1 and z2 on L5.
* **L2-L5 are four additional routing layers** whose physical heights are
  exploratory / ``unconfirmed_simulation`` parameters (never a process claim).
  Formal process acceptance is refused while they are unconfirmed.
* Routes may perform multiple transitions between layers; every route starts
  and ends on L1 at its own row height.  All bends and elevation S-curves use
  the R15 profile (fixed radius R = 15 mm).

This module is read-only: it never modifies route data and writes only under
``outputs/four_side_1024_v2_l1l5_v01/figures/`` and ``.../comparison/``.  The
R15 and R40 output roots are frozen and write-protected here.

CLI
---
    .venv\\Scripts\\python.exe -m four_side_1024.l3d.plots_l3d
    .venv\\Scripts\\python.exe -m four_side_1024.l3d.plots_l3d --include-smoke

Missing or partial data is tolerated: every independent figure is rendered when
its inputs exist, otherwise it is skipped with a printed warning and a manifest
caveat (the module never crashes on absent ``routes_l3d.json``).
"""
from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter
from pathlib import Path

from ..r15 import profile_r15

# Radius must be R=15 in this round, and the profile has to be applied before
# any routing module binds the radius at import time.
profile_r15.apply()

import numpy as np  # noqa: E402  (import order is intentional)

from ..d56.plots_d56 import DPI, _board_frame, draw_connectors, pyplot  # noqa: E402
from ..geometry import sample  # noqa: E402
from ..fslw import metrics as fslw_metrics  # noqa: E402

SCHEMA = 'four_side_1024_v2_l1l5_plots_v1'
TOOL = 'four_side_1024.l3d.plots_l3d'
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = PROJECT_ROOT / 'outputs/four_side_1024_v2_l1l5_v01'
R15_ROOT = PROJECT_ROOT / 'outputs/four_side_1024_v2_r15_v01'
R40_ROOTS = (
    PROJECT_ROOT / 'outputs/four_side_1024_v2_candidate_rr_v01',
    PROJECT_ROOT / 'outputs/four_side_1024_v2_ortho90_v01',
    PROJECT_ROOT / 'outputs/four_side_1024_v2_25d_v01',
)
FROZEN_WRITE_ROOTS = (R15_ROOT,) + R40_ROOTS

BOARD_MM = 150.0
PLANE_TOTAL = 512
TOTAL_CONNECTIONS = 1024
RADIUS_MM = 15.0
LAYER_IDS = (1, 2, 3, 4, 5)
ROUTING_LAYER_IDS = (2, 3, 4, 5)
PLANE_ORDER = ('z1', 'z2')
SCHEME_ORDER = ('A', 'B')
PLANE_COLORS = {'z1': '#1565c0', 'z2': '#c62828'}
SCHEME_COLORS = {'A': '#1565c0', 'B': '#c62828'}
STACK_NOTE = ('L2-L5 physical heights are exploratory / unconfirmed_simulation '
              'parameters, not supervisor-confirmed process values; formal '
              'process acceptance is refused until they are confirmed.')
OLD_MODEL_NOTE = ('The old 2.5D model put z1 on L1 and z2 on L5 and treated the '
                  '0.5 mm interface-row spacing as the whole five-layer stack. '
                  'Old counts are NOT comparable as process results.')
OLD_25D_CONST = {'A': 985, 'B': 723}
DISPLAY_SAGITTA_MM = 0.005
DISPLAY_SAGITTA_3D_MM = 0.02
TRANSITION_DISPLAY_STEP_MM = 0.05
TRANSITION_3D_STEP_MM = 0.10

# Exploratory stacks of SCHEMA_L3D.md §1 (all unconfirmed_simulation).
DEFAULT_STACKS = {
    'medium_050': dict(routing={2: 1.0, 3: 1.5, 4: 2.0, 5: 2.5},
                       note='0.5 mm spacing above the top interface row'),
    'compact_025': dict(routing={2: 0.75, 3: 1.0, 4: 1.25, 5: 1.5},
                        note='0.25 mm spacing (minimum above clearance)'),
    'wide_100': dict(routing={2: 1.5, 3: 2.5, 4: 3.5, 5: 4.5},
                     note='1.0 mm spacing'),
}
DEFAULT_STACK_NAME = 'medium_050'
DEFAULT_ROWS = {'z1': 0.0, 'z2': 0.5}

_ACTIVE_ROOT = {'path': DEFAULT_ROOT}
_WRITE_ALLOWED = []


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
    for frozen in FROZEN_WRITE_ROOTS:
        try:
            path.relative_to(Path(frozen).resolve())
        except ValueError:
            continue
        raise RuntimeError(f'refusing to write into frozen R15/R40 root: {path}')
    for allowed in _WRITE_ALLOWED:
        try:
            path.relative_to(Path(allowed).resolve())
        except ValueError:
            continue
        return
    raise RuntimeError(f'refusing to write outside the L1-L5 figures/ dirs: '
                       f'{path}')


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


def _sha256(path):
    import hashlib
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# layer stack
# --------------------------------------------------------------------------- #
def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_stack_mapping(raw):
    """Turn the many possible stack encodings into {layer_id: spec}."""
    mapping = {}
    if isinstance(raw, dict):
        layers = raw.get('layers') or raw.get('layer_geometries')
        if isinstance(layers, (dict, list)):
            raw = layers
        elif ('physical_z_mm' in raw or 'interface_rows' in raw) and \
                'layer_id' in raw:
            raw = [raw]
        else:
            # flat mapping such as {"1": {...}, "2": 1.0} / {"L2": 1.0}
            raw = {key: value for key, value in raw.items()
                   if str(key).upper().lstrip('L').isdigit()}
    if isinstance(raw, dict):
        items = list(raw.items())
    elif isinstance(raw, list):
        items = [(entry.get('layer_id') if isinstance(entry, dict) else None,
                  entry) for entry in raw]
    else:
        items = []
    for key, spec in items:
        layer_id = None
        if isinstance(spec, dict):
            layer_id = spec.get('layer_id', spec.get('id'))
        if layer_id is None:
            try:
                layer_id = int(str(key).upper().lstrip('L'))
            except (TypeError, ValueError):
                continue
        try:
            layer_id = int(layer_id)
        except (TypeError, ValueError):
            continue
        if layer_id in mapping:
            continue
        mapping[layer_id] = spec
    return mapping


def _stack_name_hint(payload, run_dir):
    """Stack name declared by the run (payload / run_summary / config)."""
    hint = None
    if isinstance(payload, dict):
        for key in ('stack', 'stack_name', 'layer_stack_name'):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                hint = value.strip()
                break
    for name in ('run_summary.json', 'config.json'):
        path = Path(run_dir) / name
        if not path.exists():
            continue
        try:
            data = _json_load(path)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        for key in ('stack', 'stack_name'):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                hint = hint or value.strip()
        config = data.get('config')
        if isinstance(config, dict):
            for key in ('stack', 'stack_name'):
                value = config.get(key)
                if isinstance(value, str) and value.strip():
                    hint = hint or value.strip()
    return hint


def _official_stack_candidate(hint, run_dir):
    """Load ``<root>/layer_stacks/<hint>.json`` when the run names a stack."""
    if not hint:
        return None
    roots = [Path(_ACTIVE_ROOT['path']) / 'layer_stacks']
    parent = Path(run_dir).resolve()
    for ancestor in list(parent.parents)[:4]:
        roots.append(ancestor / 'layer_stacks')
    for stack_root in roots:
        path = stack_root / f'{hint}.json'
        if not path.exists():
            continue
        try:
            data = _json_load(path)
        except (OSError, json.JSONDecodeError):
            continue
        return (f'layer_stacks/{hint}.json', data)
    return None


def normalise_stack(payload, run_dir, caveats):
    """Resolve the physical layer stack from a run payload / run directory."""
    run_dir = Path(run_dir)
    hint = _stack_name_hint(payload, run_dir)
    candidates = []
    official = _official_stack_candidate(hint, run_dir)
    if official is not None:
        candidates.append(official)
    if isinstance(payload, dict):
        for key in ('layer_stack', 'stack', 'layers', 'layer_geometries',
                    'layer_heights_mm', 'routing_layer_heights_mm'):
            if key in payload and payload[key] is not None:
                candidates.append((f'payload.{key}', payload[key]))
    for name in ('layer_stack.json', 'stack.json', 'config.json',
                 'run_summary.json'):
        path = run_dir / name
        if not path.exists():
            continue
        try:
            data = _json_load(path)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            for key in ('layer_stack', 'stack', 'layers', 'layer_geometries'):
                if key in data and data[key] is not None:
                    candidates.append((f'{name}:{key}', data[key]))
    stack_name = hint
    rows = dict(DEFAULT_ROWS)
    routing = {}
    provenance = 'unconfirmed_simulation'
    note = None
    source = None
    for label, raw in candidates:
        mapping = _extract_stack_mapping(raw)
        if not mapping:
            continue
        source = label
        if isinstance(raw, dict):
            stack_name = (raw.get('name') or raw.get('stack_name')
                          or stack_name)
            provenance = raw.get('provenance') or provenance
            note = raw.get('provenance_note') or raw.get('note') or note
        for layer_id, spec in mapping.items():
            if layer_id == 1:
                if isinstance(spec, dict):
                    interface_rows = spec.get('interface_rows')
                    if isinstance(interface_rows, dict):
                        z1 = _as_float(interface_rows.get('z1'))
                        z2 = _as_float(interface_rows.get('z2'))
                        if z1 is not None and z2 is not None:
                            rows = {'z1': z1, 'z2': z2}
            elif layer_id in ROUTING_LAYER_IDS:
                value = None
                if isinstance(spec, dict):
                    for key in ('physical_z_mm', 'z_mm', 'height_mm', 'z'):
                        value = _as_float(spec.get(key))
                        if value is not None:
                            break
                else:
                    value = _as_float(spec)
                if value is not None:
                    routing[layer_id] = value
        if routing:
            break
    defaulted = False
    if len(routing) < len(ROUTING_LAYER_IDS):
        chosen = DEFAULT_STACKS[DEFAULT_STACK_NAME]
        for layer_id in ROUTING_LAYER_IDS:
            if layer_id not in routing:
                routing[layer_id] = chosen['routing'][layer_id]
                defaulted = True
        if defaulted:
            caveats.append(
                f'{run_dir}: routing-layer heights incomplete in the data; '
                f'defaulted missing L2-L5 heights to the exploratory '
                f'{DEFAULT_STACK_NAME} stack (unconfirmed_simulation)')
        stack_name = stack_name or DEFAULT_STACK_NAME
        source = source or 'fallback:medium_050'
    # infer the stack name from the known exploratory stacks when unnamed
    if not stack_name:
        for candidate_name, info in DEFAULT_STACKS.items():
            if all(layer_id in routing
                   and abs(routing[layer_id] - height) <= 1e-9
                   for layer_id, height in info['routing'].items()):
                stack_name = candidate_name
                break
    # an official layer_stacks/<name>.json overrides provenance / notes
    if stack_name:
        official = _official_stack_candidate(stack_name, run_dir)
        if official is not None and isinstance(official[1], dict):
            data = official[1]
            note = data.get('note') or note
            provenance = data.get('provenance') or provenance
            source = source or official[0]
    heights = sorted(routing.values())
    if len(heights) != len(set(heights)):
        caveats.append(f'{run_dir}: duplicate routing-layer heights {heights}')
    all_heights = sorted(set(heights) | {rows['z1'], rows['z2']})
    ordered = [all_heights[index] < all_heights[index + 1]
               for index in range(len(all_heights) - 1)]
    if not all(ordered):
        caveats.append(f'{run_dir}: layer heights are not strictly ordered '
                       f'{all_heights}')
    return {
        'name': stack_name or f'stack_from_{source or "data"}',
        'rows': rows,
        'routing': dict(sorted(routing.items())),
        'provenance': provenance,
        'provenance_note': note or STACK_NOTE,
        'source': source,
        'defaulted': defaulted,
    }


def layer_height_label(stack, layer_id):
    if layer_id == 1:
        return (f'L1 interface rows z1={stack["rows"]["z1"]:.3f} mm / '
                f'z2={stack["rows"]["z2"]:.3f} mm')
    return f'L{layer_id} z={stack["routing"].get(layer_id, float("nan")):.3f} mm'


def layer_z(stack, layer_id, plane=None):
    if layer_id == 1:
        if plane in stack['rows']:
            return stack['rows'][plane]
        return stack['rows']['z1']
    return stack['routing'].get(layer_id)


def stack_height_ticks(stack):
    ticks = [(stack['rows']['z1'], 'L1 z1 row'), (stack['rows']['z2'],
                                                  'L1 z2 row')]
    for layer_id, height in stack['routing'].items():
        ticks.append((height, f'L{layer_id}'))
    return ticks


# --------------------------------------------------------------------------- #
# route data loading
# --------------------------------------------------------------------------- #
def _derive_scheme(payload, run_dir):
    value = payload.get('scheme') if isinstance(payload, dict) else None
    if isinstance(value, str) and value.strip().upper() in ('A', 'B'):
        return value.strip().upper()
    for part in reversed(Path(run_dir).parts):
        text = part.strip()
        if text.lower().startswith('scheme') and text[-1:].upper() in ('A', 'B'):
            return text[-1].upper()
        if text.upper() in ('A', 'B'):
            return text.upper()
    return None


def _route_plane(route):
    plane = route.get('plane')
    if isinstance(plane, str) and plane.strip().lower() in PLANE_ORDER:
        return plane.strip().lower()
    start_z = _as_float(route.get('start_z_mm'))
    source_port = route.get('source_port') or {}
    if start_z is None:
        start_z = _as_float(source_port.get('z_mm'))
    return 'z1' if start_z is not None and abs(start_z) < 1e-9 else 'z2'


def load_run(run_dir, caveats, is_smoke=False):
    run_dir = Path(run_dir)
    routes_path = run_dir / 'routes_l3d.json'
    payload = _json_load(routes_path)
    if isinstance(payload, dict):
        routes = payload.get('routes') or []
        meta = payload
    elif isinstance(payload, list):
        routes = payload
        meta = {}
    else:
        raise ValueError(f'{routes_path}: unexpected payload')
    routes = [route for route in routes if isinstance(route, dict)]
    statistics = meta.get('statistics') or {}
    routed = meta.get('routed')
    if routed is None:
        routed = statistics.get('routed')
    routes = [route for route in routes if route.get('parts')]
    routed = len(routes)
    failed = meta.get('failed')
    if failed is None:
        failed = statistics.get('failed')
    total = meta.get('total') or statistics.get('total') or TOTAL_CONNECTIONS
    stage = meta.get('stage')
    stack = normalise_stack(meta, run_dir, caveats)
    scheme = _derive_scheme(meta, run_dir)
    label = meta.get('label')
    if not label:
        label = (f'{stage}_{scheme}' if stage
                 else f'{run_dir.parent.name}_{scheme or run_dir.name}')
    radius_values = set()
    max_transitions = 0
    for route in routes:
        max_transitions = max(max_transitions, route_transition_count(route))
        for part in route.get('parts') or []:
            radius = _as_float(part.get('radius_mm'))
            if part.get('kind') == 'transition' and radius is not None:
                radius_values.add(round(radius, 6))
    return {
        'run_dir': run_dir,
        'routes_path': routes_path,
        'payload': meta,
        'routes': routes,
        'routed': int(routed),
        'failed': int(failed) if failed is not None else None,
        'total': int(total),
        'scheme': scheme,
        'label': str(label),
        'stage': str(stage) if stage else None,
        'max_transitions': int(max_transitions),
        'stack': stack,
        'is_smoke': bool(is_smoke or '_smoke' in run_dir.parts),
        'transition_radii': sorted(radius_values),
        'schema': meta.get('schema'),
        '_segments3d': None,
    }


def _stage_rank(run):
    """Higher = more advanced: multi-layer stages outrank single-layer ones."""
    stage = (run.get('stage') or '').lower()
    if any(token in stage for token in ('multilayer', 'multi_layer',
                                        'lifted', 'full', 'final')):
        rank = 3
    elif 'single' in stage:
        rank = 1
    elif not stage or stage.startswith('baseline') or stage == 'l1_baseline':
        rank = 0
    else:
        rank = 2
    if int(run.get('max_transitions') or 0) >= 2 and rank < 2:
        rank = 2
    return rank


def discover_runs(root, include_smoke, caveats):
    """All ``routes_l3d.json`` files under root (non-smoke preferred)."""
    root = Path(root)
    runs = []
    smoke_runs = []
    for routes_path in sorted(root.rglob('routes_l3d.json')):
        run_dir = routes_path.parent
        is_smoke = '_smoke' in run_dir.parts
        try:
            run = load_run(run_dir, caveats, is_smoke=is_smoke)
        except Exception as exc:  # noqa: BLE001
            caveats.append(f'{routes_path}: skipped '
                           f'({type(exc).__name__}: {exc})')
            continue
        if run['scheme'] not in SCHEME_ORDER:
            caveats.append(f'{routes_path}: skipped (cannot determine scheme)')
            continue
        if is_smoke:
            smoke_runs.append(run)
        else:
            runs.append(run)
    if include_smoke:
        runs.extend(smoke_runs)
        smoke_runs = []
    if not runs and smoke_runs:
        caveats.append('no formal L3D run found under the root; rendering the '
                       '_smoke fixture data only (not a process result)')
        runs = smoke_runs
    for run in runs:
        radii = run['transition_radii']
        if radii and any(abs(radius - RADIUS_MM) > 1e-6 for radius in radii):
            caveats.append(f'{run["run_dir"]}: transition radii {radii} differ '
                           f'from the required R=15 mm')
    return runs


def select_primary_runs(runs, caveats):
    """One primary run per scheme: most advanced stage, primary stack first."""
    table = {}
    for scheme in SCHEME_ORDER:
        candidates = [run for run in runs if run['scheme'] == scheme
                      and not run['is_smoke']]
        if not candidates:
            candidates = [run for run in runs if run['scheme'] == scheme]
        if not candidates:
            continue
        candidates.sort(key=lambda run: (
            -_stage_rank(run),
            0 if run['stack'].get('name') == DEFAULT_STACK_NAME else 1,
            -int(run['routed']),
            -int(run.get('max_transitions') or 0),
            str(run['run_dir'])))
        table[scheme] = candidates[0]
        if len(candidates) > 1:
            caveats.append(
                f'scheme {scheme}: {len(candidates)} runs found; using '
                f'{candidates[0]["label"]} ({candidates[0]["routed"]} routed, '
                f'stage {candidates[0]["stage"] or "n/a"}) for the main '
                f'figures; all runs are listed in the manifest')
    return table


# --------------------------------------------------------------------------- #
# geometry sampling
# --------------------------------------------------------------------------- #
def _part_z_bounds(part):
    z0 = _as_float(part.get('z0', part.get('z0_mm')))
    z1 = _as_float(part.get('z1', part.get('z1_mm')))
    if z0 is None or z1 is None:
        raise KeyError('transition part without z0/z1')
    return z0, z1


def transition_polyline(part, step_mm=TRANSITION_DISPLAY_STEP_MM):
    """3D samples of one stored transition (schema S-curve, R=15 mm)."""
    radius = _as_float(part.get('radius_mm')) or RADIUS_MM
    z0, z1 = _part_z_bounds(part)
    dz = z1 - z0
    sign = 1.0 if dz >= 0.0 else -1.0
    theta = _as_float(part.get('theta_rad'))
    if theta is None or theta <= 0.0:
        ratio = 1.0 - abs(dz) / (2.0 * radius)
        theta = math.acos(max(-1.0, min(1.0, ratio)))
    start = np.asarray(part['start'], dtype=float)
    direction = np.asarray(part['direction'], dtype=float)
    norm = float(np.hypot(direction[0], direction[1])) or 1.0
    direction = direction / norm
    if theta <= 0.0:
        end = np.asarray(part.get('end', start), dtype=float)
        return np.asarray([[start[0], start[1], z0], [end[0], end[1], z1]])
    footprint = 2.0 * radius * math.sin(theta)
    arc_length = 2.0 * radius * theta
    count = max(2, int(math.ceil(arc_length / max(step_mm, 1e-9))))
    phase = np.linspace(0.0, 2.0 * theta, count + 1)
    first = phase <= theta
    u = np.where(first, radius * np.sin(phase),
                 footprint - radius * np.sin(2.0 * theta - phase))
    w = np.where(first, z0 + sign * radius * (1.0 - np.cos(phase)),
                 z1 - sign * radius * (1.0 - np.cos(2.0 * theta - phase)))
    xy = start[None, :] + u[:, None] * direction[None, :]
    return np.column_stack([xy, w])


def flat_polyline(part, sagitta_mm=DISPLAY_SAGITTA_MM):
    primitives = part.get('primitives') or []
    if not primitives:
        return None
    points = sample(primitives, sagitta_mm)
    if points is None or len(points) < 2:
        return None
    return np.asarray(points, dtype=float)


def route_segments_3d(route, sagitta_mm=DISPLAY_SAGITTA_3D_MM,
                      transition_step_mm=TRANSITION_3D_STEP_MM):
    """``(m, 2, 3)`` segments of one route, in part order."""
    chunks = []
    for part in route.get('parts') or []:
        kind = part.get('kind')
        if kind == 'flat':
            points = flat_polyline(part, sagitta_mm)
            if points is None:
                continue
            z = _as_float(part.get('z_mm'))
            if z is None:
                z = 0.0
            polyline = np.column_stack([points, np.full(len(points), z)])
        elif kind == 'transition':
            try:
                polyline = transition_polyline(part, transition_step_mm)
            except (KeyError, TypeError, ValueError):
                continue
        else:
            continue
        if polyline is None or len(polyline) < 2:
            continue
        chunks.append(np.stack([polyline[:-1], polyline[1:]], axis=1))
    if not chunks:
        return None
    return np.concatenate(chunks, axis=0)


def run_segments_3d(run):
    if run.get('_segments3d') is not None:
        return run['_segments3d']
    per_plane = {plane: [] for plane in PLANE_ORDER}
    for route in run['routes']:
        segments = route_segments_3d(route)
        if segments is None or not len(segments):
            continue
        per_plane[_route_plane(route)].append(segments)
    result = {plane: (np.concatenate(chunks, axis=0) if chunks else None)
              for plane, chunks in per_plane.items()}
    run['_segments3d'] = result
    return result


def route_layer_sequence(route):
    sequence = route.get('layer_sequence')
    if isinstance(sequence, list) and sequence:
        try:
            return [int(value) for value in sequence]
        except (TypeError, ValueError):
            pass
    sequence = [1]
    for part in route.get('parts') or []:
        layer_id = _as_float(part.get('layer_id', part.get('from_layer')))
        if layer_id is None:
            continue
        layer_id = int(layer_id)
        if layer_id != sequence[-1]:
            sequence.append(layer_id)
    return sequence


def route_transition_count(route):
    value = route.get('n_transitions')
    if value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            pass
    return sum(1 for part in route.get('parts') or []
               if part.get('kind') == 'transition')


def route_layers_used(route):
    sequence = route_layer_sequence(route)
    return sorted(set(sequence))


def route_plane_counts(run):
    counts = {'z1': 0, 'z2': 0}
    for route in run['routes']:
        counts[_route_plane(route)] += 1
    return counts


def layer_flat_parts(run, layer_id):
    entries = []
    for route in run['routes']:
        for part in route.get('parts') or []:
            if part.get('kind') != 'flat':
                continue
            try:
                part_layer = int(part.get('layer_id'))
            except (TypeError, ValueError):
                continue
            if part_layer != layer_id:
                continue
            points = flat_polyline(part)
            if points is None:
                continue
            entries.append({'route': route, 'part': part, 'points': points,
                            'plane': _route_plane(route)})
    return entries


def layer_route_count(run, layer_id):
    count = 0
    for route in run['routes']:
        if layer_id in route_layers_used(route):
            count += 1
    return count


# --------------------------------------------------------------------------- #
# ports / connectors (frozen V2 interface, always available)
# --------------------------------------------------------------------------- #
def load_port_data(caveats):
    try:
        from ..fslw import ports
        routes_z1, endpoints_z1, connectors, validation = \
            ports.load_plane('V2', 'z1')
        routes_z2, endpoints_z2, _connectors, _validation = \
            ports.load_plane('V2', 'z2')
    except Exception as exc:  # noqa: BLE001
        caveats.append(f'frozen V2 port table unavailable '
                       f'({type(exc).__name__}: {exc})')
        return None
    endpoints = {}
    for entry in list(endpoints_z1.values()) + list(endpoints_z2.values()):
        endpoints[entry['endpoint_id']] = entry
    return {'connectors': connectors, 'endpoints': endpoints,
            'routes_z1': routes_z1, 'routes_z2': routes_z2}


# --------------------------------------------------------------------------- #
# 1) L1 interface 2x16 dual-row zoom
# --------------------------------------------------------------------------- #
def _pick_connector(port_data, name=None):
    connectors = port_data.get('connectors') or []
    if not connectors:
        return None
    for connector in connectors:
        if connector['connector'] == name:
            return connector
    return connectors[0]


def render_l1_interface_zoom(output_path, port_data, caveats):
    plt = pyplot()
    connector = _pick_connector(port_data, 'N01')
    if connector is None:
        raise RuntimeError('no connector available for the L1 zoom')
    endpoints = port_data['endpoints'] or {}
    row1 = sorted([entry for entry in endpoints.values()
                   if entry.get('connector') == connector['connector']
                   and int(entry.get('row', 0)) == 1],
                  key=lambda entry: int(entry.get('column', 0)))
    row2 = sorted([entry for entry in endpoints.values()
                   if entry.get('connector') == connector['connector']
                   and int(entry.get('row', 0)) == 2],
                  key=lambda entry: int(entry.get('column', 0)))
    if not row1 or not row2:
        raise RuntimeError('connector rows 1/2 have no endpoint records')
    column_pitch = float(connector.get('fiber_column_pitch_mm', 0.25))
    row_pitch = abs(float(row1[0].get('z_mm', 0.0))
                    - float(row2[0].get('z_mm', 0.5)))

    fig = plt.figure(figsize=(13.6, 7.8))
    ax = fig.add_subplot(111, projection='3d')
    ax.set_position([-0.03, -0.10, 1.06, 1.14])
    x_row1 = [float(entry['routing_xy'][0]) for entry in row1]
    x_row2 = [float(entry['routing_xy'][0]) for entry in row2]
    y_edge = float(connector['center_xy'][1])
    z1_row = float(row1[0].get('z_mm', 0.0))
    z2_row = float(row2[0].get('z_mm', 0.5))
    ax.scatter(x_row1, [y_edge] * len(x_row1), [z1_row] * len(x_row1),
               s=46, c='#1565c0', depthshade=False, label='L1 z1 row (row 1)')
    ax.scatter(x_row2, [y_edge] * len(x_row2), [z2_row] * len(x_row2),
               s=46, c='#c62828', marker='s', depthshade=False,
               label='L1 z2 row (row 2)')
    for x_value in x_row1:
        ax.plot([x_value, x_value], [y_edge, y_edge], [z1_row, z2_row],
                color='#666666', linewidth=0.8, linestyle=':')
    # matrix / connector envelope blocks for the two rows.
    width = float(connector.get('envelope_width_mm', 12.59))
    center_x = float(connector['center_xy'][0])
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    for z_value, color in ((z1_row, '#1565c0'), (z2_row, '#c62828')):
        y0, y1 = y_edge, y_edge + 3.0
        z0, z1 = z_value - 0.035, z_value + 0.035
        vertices = [[(center_x - width / 2.0, y0, z0),
                     (center_x + width / 2.0, y0, z0),
                     (center_x + width / 2.0, y1, z0),
                     (center_x - width / 2.0, y1, z0)],
                    [(center_x - width / 2.0, y0, z1),
                     (center_x + width / 2.0, y0, z1),
                     (center_x + width / 2.0, y1, z1),
                     (center_x - width / 2.0, y1, z1)]]
        ax.add_collection3d(Poly3DCollection(
            vertices, facecolor=color, alpha=0.16, edgecolor=color,
            linewidth=0.6))
    # 0.25 mm column-pitch dimension marker between the two middle columns.
    if len(x_row1) >= 9:
        x_a, x_b = x_row1[7], x_row1[8]
        y_dim = y_edge - 0.9
        ax.plot([x_a, x_a], [y_dim, y_edge], [z1_row, z1_row],
                color='#444444', linewidth=0.7)
        ax.plot([x_b, x_b], [y_dim, y_edge], [z1_row, z1_row],
                color='#444444', linewidth=0.7)
        ax.plot([x_a, x_b], [y_dim, y_dim], [z1_row, z1_row],
                color='#444444', linewidth=0.9)
        ax.text((x_a + x_b) / 2.0, y_dim - 0.5, z1_row,
                f'column pitch {column_pitch:g} mm', fontsize=7.5,
                color='#333333', ha='center')
    # 0.5 mm row-pitch dimension marker at the left edge.
    x_dim = x_row1[0] - 0.9
    ax.plot([x_dim, x_row1[0]], [y_edge, y_edge], [z1_row, z1_row],
            color='#444444', linewidth=0.9)
    ax.plot([x_dim, x_row1[0]], [y_edge, y_edge], [z2_row, z2_row],
            color='#444444', linewidth=0.9)
    ax.plot([x_dim, x_dim], [y_edge, y_edge], [z1_row, z2_row],
            color='#444444', linewidth=0.9)
    ax.text(x_dim - 0.4, y_edge, (z1_row + z2_row) / 2.0,
            f'row pitch {row_pitch:g} mm', fontsize=7.5, color='#333333',
            ha='right')
    ax.set_xlim(center_x - width / 2.0 - 1.5, center_x + width / 2.0 + 1.5)
    ax.set_ylim(y_edge - 1.8, y_edge + 3.6)
    ax.set_zlim(-0.25, 0.85)
    ax.set_box_aspect((2.4, 1.0, 0.75))
    ax.set_xticks([center_x + offset for offset in (-2.0, -1.0, 0.0, 1.0, 2.0)])
    ax.set_yticks([y_edge - 1.0, y_edge, y_edge + 1.5, y_edge + 3.0])
    ax.set_zticks([0.0, 0.25, 0.5])
    ax.set_zticklabels(['0.000', '0.250', '0.500'], fontsize=7.5)
    ax.set_xlabel('x (mm, along connector)')
    ax.set_ylabel('y (mm, board normal / depth)')
    ax.set_zlabel('physical z (mm)')
    ax.view_init(elev=18.0, azim=-60.0)
    from matplotlib.lines import Line2D
    legend_handles = [
        Line2D([0], [0], marker='o', color='none', markerfacecolor='#1565c0',
               markeredgecolor='#0d47a1', markersize=7,
               label='L1 z1 row (row 1, z = 0.000 mm)'),
        Line2D([0], [0], marker='s', color='none', markerfacecolor='#c62828',
               markeredgecolor='#8e0000', markersize=7,
               label='L1 z2 row (row 2, z = 0.500 mm)'),
        Line2D([0], [0], color='#666666', linewidth=0.9, linestyle=':',
               label='same column on both rows (0.5 mm apart)'),
    ]
    fig.legend(handles=legend_handles, loc='upper right',
               bbox_to_anchor=(0.985, 0.925), fontsize=8.0, framealpha=0.92)
    fig.text(
        0.5, 0.012,
        "L1 interface layer = BOTH port rows of this 2 x 16 MPO connector\n"
        "  L1 z1 row = 0.0 mm (row 1, channels 1-16, blue)   |   "
        "L1 z2 row = 0.5 mm (row 2, channels 17-32, red)\n"
        "L5 is a ROUTING layer, not an interface layer (old-model mistake "
        "corrected)",
        ha='center', va='bottom', fontsize=8.6,
        bbox=dict(boxstyle='round,pad=0.35', facecolor='white', alpha=0.94,
                  edgecolor='#888888'))
    fig.suptitle(
        f'Corrected L1 interface: one logical interface layer L1 with two '
        f'physical port rows (z = 0.0 and 0.5 mm)\n'
        f'connector {connector["connector"]} | 2 x 16 MPO = 32 channels | '
        f'column pitch {column_pitch:g} mm | row pitch (physical z) '
        f'{row_pitch:g} mm | local 3D zoom, z exaggerated for display',
        fontsize=10.5, y=0.998)
    _save(fig, output_path, tight=False)
    return {
        'file': _rel(output_path),
        'kind': 'l1_interface_two_rows_zoom',
        'run': None,
        'description': ('3D local zoom of a 2x16 MPO connector showing L1 with '
                        'both port rows (z1=0.0 mm, z2=0.5 mm) and the '
                        'corrected interface-layer definition'),
        'connector': connector['connector'],
        'column_pitch_mm': column_pitch,
        'row_pitch_mm': row_pitch,
        'row1_z_mm': z1_row,
        'row2_z_mm': z2_row,
    }


# --------------------------------------------------------------------------- #
# 2) physical layer-stack schematic
# --------------------------------------------------------------------------- #
def render_layer_stack(stack, output_path):
    plt = pyplot()
    from matplotlib.patches import ConnectionPatch, FancyBboxPatch
    fig, (ax_left, ax_right) = plt.subplots(
        1, 2, figsize=(14.6, 7.6),
        gridspec_kw={'width_ratios': [1.0, 1.45], 'wspace': 0.10})
    # left: logical layer identity axis
    ax_left.set_xlim(0.0, 1.0)
    ax_left.set_ylim(0.4, 5.8)
    ax_left.set_yticks(list(LAYER_IDS))
    ax_left.set_yticklabels([f'L{layer}' for layer in LAYER_IDS])
    ax_left.set_ylabel('logical layer id (L1..L5)', fontsize=9.5)
    ax_left.set_xticks([])
    ax_left.set_title('logical layer identity (data model)', fontsize=9.5)
    ax_left.grid(True, axis='y', alpha=0.25, linewidth=0.5)
    for spine in ax_left.spines.values():
        spine.set_visible(False)
    for layer_id in LAYER_IDS:
        y = layer_id
        if layer_id == 1:
            label = ('L1  interface\nboth port rows\n(z1=0.0, z2=0.5 mm)')
            face = '#e3f2fd'
            edge = '#1565c0'
        else:
            height = stack['routing'].get(layer_id)
            label = (f'L{layer_id}  routing\nz = {height:.3f} mm\n'
                     f'(unconfirmed_simulation)')
            face = '#f3e5f5'
            edge = '#6a1b9a'
        ax_left.add_patch(FancyBboxPatch(
            (0.16, y - 0.36), 0.68, 0.72,
            boxstyle='round,pad=0.02', facecolor=face, edgecolor=edge,
            linewidth=1.0, mutation_aspect=3.0))
        ax_left.text(0.5, y, label, ha='center', va='center', fontsize=7.6)
    # right: physical z axis
    heights = [stack['rows']['z1'], stack['rows']['z2']]
    heights += [stack['routing'][layer_id] for layer_id in ROUTING_LAYER_IDS
                if layer_id in stack['routing']]
    z_min = min(heights) - 0.35
    z_max = max(heights) + 0.45
    ax_right.set_xlim(0.0, 1.0)
    ax_right.set_ylim(z_min, z_max)
    ax_right.yaxis.set_label_position('right')
    ax_right.yaxis.tick_right()
    ax_right.set_ylabel('physical z (mm) - real height axis', fontsize=9.5,
                        labelpad=8)
    ax_right.set_xticks([])
    ax_right.set_title('physical height (simulation parameter space)',
                       fontsize=9.5)
    ax_right.grid(True, axis='y', alpha=0.25, linewidth=0.5)
    ax_right.tick_params(axis='y', labelsize=8.0)
    for spine in ax_right.spines.values():
        spine.set_visible(False)
    planes = [
        (stack['rows']['z1'], 'L1 z1 row = 0.000 mm  (interface row 1)',
         '#1565c0', 'solid'),
        (stack['rows']['z2'], 'L1 z2 row = 0.500 mm  (interface row 2)',
         '#c62828', 'solid'),
    ]
    for layer_id in ROUTING_LAYER_IDS:
        if layer_id not in stack['routing']:
            continue
        planes.append((stack['routing'][layer_id],
                       f'L{layer_id} = {stack["routing"][layer_id]:.3f} mm '
                       f'(exploratory, unconfirmed)', '#6a1b9a', 'dashed'))
    for z_value, label, color, style in planes:
        ax_right.plot([0.02, 0.98], [z_value, z_value], color=color,
                      linewidth=1.8 if style == 'solid' else 1.2,
                      linestyle=style)
        ax_right.text(0.52, z_value, label, ha='left', va='bottom',
                      fontsize=7.6, color=color,
                      bbox=dict(boxstyle='round,pad=0.12', facecolor='white',
                                alpha=0.85, edgecolor='none'))
    # arrows logical -> physical (L1 forks into its two rows)
    for layer_id in LAYER_IDS:
        y_left = layer_id
        if layer_id == 1:
            targets = [stack['rows']['z1'], stack['rows']['z2']]
        elif layer_id in stack['routing']:
            targets = [stack['routing'][layer_id]]
        else:
            continue
        for z_value in targets:
            arrow = ConnectionPatch(
                xyA=(0.86, y_left), coordsA=ax_left.transData,
                xyB=(0.05, z_value), coordsB=ax_right.transData,
                axesA=ax_left, axesB=ax_right, arrowstyle='-|>',
                mutation_scale=9, color='#555555', linewidth=0.9,
                linestyle='-' if layer_id == 1 else '--', alpha=0.85)
            fig.add_artist(arrow)
    note = (
        'CORRECTED L1-L5 PHYSICAL MODEL (R9)\n'
        'L1 = interface routing layer containing BOTH port rows: z1 row at '
        'physical z = 0.0 mm, z2 row at z = 0.5 mm.\n'
        'L2-L5 = four additional routing layers with explorative physical '
        'heights (exploratory / unconfirmed_simulation parameters).\n'
        'They are simulation inputs, NOT supervisor-confirmed process values; '
        'formal process acceptance is refused until they are confirmed.\n'
        'OLD (WRONG) model: z1 = layer 0 (L1) and z2 = layer 4 (L5) with the '
        '0.5 mm row spacing treated as the whole stack - kept only as history.')
    fig.text(0.5, 0.015, note, ha='center', va='bottom', fontsize=8.6,
             bbox=dict(boxstyle='round,pad=0.45', facecolor='#fffde7',
                       edgecolor='#f9a825', linewidth=1.1))
    fig.suptitle(
        f'Physical layer stack used this round - stack "{stack["name"]}" | '
        f'provenance: {stack["provenance"]} | '
        f'left axis = logical layer id, right axis = physical z (mm)',
        fontsize=11.5)
    fig.subplots_adjust(top=0.90, bottom=0.21, left=0.06, right=0.925)
    _save(fig, output_path, tight=False)
    return {
        'file': _rel(output_path),
        'kind': 'layer_stack_physical_heights',
        'run': None,
        'description': ('logical layer id axis vs physical z axis; L1 has both '
                        'port rows, L2-L5 are exploratory routing heights '
                        '(unconfirmed_simulation)'),
        'stack_name': stack['name'],
        'stack': {'rows': dict(stack['rows']),
                  'routing': {str(key): value
                              for key, value in stack['routing'].items()}},
        'provenance': stack['provenance'],
    }


# --------------------------------------------------------------------------- #
# 3) per-layer XY routing maps
# --------------------------------------------------------------------------- #
def _layer_colour_map(stack):
    from matplotlib import colormaps
    from matplotlib.colors import Normalize
    heights = [stack['rows']['z1'], stack['rows']['z2']]
    heights += [stack['routing'][layer_id] for layer_id in ROUTING_LAYER_IDS
                if layer_id in stack['routing']]
    norm = Normalize(vmin=min(heights), vmax=max(heights))
    return colormaps['plasma'], norm, heights


def render_layer_routing_map(run, layer_id, output_path, connectors):
    plt = pyplot()
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D
    from matplotlib.cm import ScalarMappable
    stack = run['stack']
    entries = layer_flat_parts(run, layer_id)
    route_count = layer_route_count(run, layer_id)
    plane_counts = Counter(entry['plane'] for entry in entries)
    fig, ax = plt.subplots(figsize=(11.0, 10.2))
    cmap, norm, heights = _layer_colour_map(stack)
    if layer_id == 1:
        for plane in PLANE_ORDER:
            segments = [entry['points'] for entry in entries
                        if entry['plane'] == plane]
            if not segments:
                continue
            ax.add_collection(LineCollection(
                segments, colors=[PLANE_COLORS[plane]], linewidths=0.45,
                alpha=0.85, zorder=3))
        handles = [
            Line2D([0], [0], color=PLANE_COLORS['z1'], linewidth=1.6,
                   label=f"z1 row routes (z = {stack['rows']['z1']:.3f} mm): "
                         f"{plane_counts.get('z1', 0)} flat parts"),
            Line2D([0], [0], color=PLANE_COLORS['z2'], linewidth=1.6,
                   label=f"z2 row routes (z = {stack['rows']['z2']:.3f} mm): "
                         f"{plane_counts.get('z2', 0)} flat parts"),
        ]
        ax.legend(handles=handles, loc='upper left', fontsize=7.5,
                  framealpha=0.9)
        radius_text = ('L1 interface layer: BOTH port rows belong to L1 '
                       '(z1 row = 0.0 mm, z2 row = 0.5 mm)')
    else:
        z_values = [float(entry['part'].get('z_mm', stack['routing'][layer_id]))
                    for entry in entries]
        if not z_values:
            z_values = [stack['routing'][layer_id]]
        colour = cmap(norm(float(np.mean(z_values))))
        segments = [entry['points'] for entry in entries]
        if segments:
            ax.add_collection(LineCollection(
                segments, colors=[colour], linewidths=0.55, alpha=0.88,
                zorder=3))
        handles = [Line2D([0], [0], color=colour, linewidth=1.6,
                          label=f'L{layer_id} flat parts: {len(entries)}')]
        ax.legend(handles=handles, loc='upper left', fontsize=7.5,
                  framealpha=0.9)
        radius_text = (f'L{layer_id} routing layer: physical z = '
                       f'{stack["routing"][layer_id]:.3f} mm '
                       f'(exploratory / unconfirmed_simulation)')
        scalar = ScalarMappable(norm=norm, cmap=cmap)
        colorbar = fig.colorbar(scalar, ax=ax, fraction=0.035, pad=0.02)
        colorbar.set_label('physical z (mm) of the layer stack', fontsize=8.5)
        colorbar.set_ticks([height for height, _label
                            in stack_height_ticks(stack)])
        colorbar.ax.set_yticklabels(
            [f'{height:.3f}  {label}' for height, label
             in stack_height_ticks(stack)], fontsize=6.8)
    _board_frame(ax)
    draw_connectors(ax, connectors or [], depth_mm=3.0, label_fontsize=4.0)
    if not entries:
        ax.text(0.5, 0.5,
                f'no routed routes use L{layer_id} in this data yet\n'
                f'current data stage: {run.get("stage") or "unknown"}\n'
                f'(empty layer expected before multi-layer routing data)',
                transform=ax.transAxes, ha='center', va='center',
                fontsize=10.0, color='#666666',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='white',
                          alpha=0.9, edgecolor='#bbbbbb'))
    ax.set_title(
        f'L{layer_id} routing map | {radius_text}\n'
        f'{route_count}/{run["routed"]} routed routes use L{layer_id} | '
        f'{len(entries)} flat parts on L{layer_id} | total '
        f'{run["routed"]}/{TOTAL_CONNECTIONS} routed (R={RADIUS_MM:g} mm) | '
        f'stack "{stack["name"]}" | stage "{run.get("stage") or "n/a"}"',
        fontsize=9.0)
    _save(fig, output_path)
    return {
        'file': _rel(output_path),
        'kind': 'layer_routing_map',
        'run': run['label'],
        'layer_id': int(layer_id),
        'description': (f'XY routing map of all flat parts on logical layer '
                        f'L{layer_id} ({route_count} routes use it)'),
        'routes_using_layer': int(route_count),
        'flat_parts': len(entries),
        'physical_z': (stack['rows'] if layer_id == 1
                       else stack['routing'].get(layer_id)),
    }


# --------------------------------------------------------------------------- #
# 4) full 1024-channel 3D layout
# --------------------------------------------------------------------------- #
def _collection_3d(segments, colors, linewidth, alpha=0.65):
    from mpl_toolkits.mplot3d.art3d import Line3DCollection
    return Line3DCollection(segments, colors=colors, linewidths=linewidth,
                            alpha=alpha)


def _setup_3d_axes(ax, stack, run):
    heights = [stack['rows']['z1'], stack['rows']['z2']]
    heights += [stack['routing'][layer_id] for layer_id in ROUTING_LAYER_IDS
                if layer_id in stack['routing']]
    z_lo, z_hi = min(heights), max(heights)
    pad = 6.0
    ax.set_xlim(-pad, BOARD_MM + pad)
    ax.set_ylim(-pad, BOARD_MM + pad)
    z_pad = 0.12 * (z_hi - z_lo) if z_hi > z_lo else 0.1
    ax.set_zlim(z_lo - z_pad, z_hi + z_pad)
    z_aspect = 0.42
    ax.set_box_aspect((1.0, 1.0, z_aspect))
    horizontal = 1.0 / float(BOARD_MM + 2.0 * pad)
    vertical = z_aspect / float((z_hi - z_lo) + 2.0 * z_pad)
    exaggeration = vertical / horizontal
    ax.set_xticks([0.0, 50.0, 100.0, 150.0])
    ax.set_yticks([0.0, 50.0, 100.0, 150.0])
    ticks = stack_height_ticks(stack)
    short_labels = {'L1 z1 row': 'L1 z1', 'L1 z2 row': 'L1 z2'}
    ax.set_zticks([height for height, _label in ticks])
    ax.set_zticklabels([f'{height:.3f} {short_labels.get(label, label)}'
                        for height, label in ticks], fontsize=5.8)
    ax.tick_params(axis='z', pad=1.5)
    ax.set_xlabel('x (mm)')
    ax.set_ylabel('y (mm)')
    ax.set_zlabel('physical z (mm)')
    ax.view_init(elev=30.0, azim=-57.0)
    return exaggeration


def render_full_layout_3d(run, output_path, mode='plane'):
    plt = pyplot()
    from matplotlib.cm import ScalarMappable
    stack = run['stack']
    segments_by_plane = run_segments_3d(run)
    fig = plt.figure(figsize=(16.0, 9.6))
    ax = fig.add_subplot(111, projection='3d')
    ax.set_position([-0.02, -0.17, 1.02, 1.23])
    linewidth = 0.30 if run['routed'] > 128 else 0.45
    if mode == 'height':
        chunks, heights = [], []
        for plane in PLANE_ORDER:
            segments = segments_by_plane.get(plane)
            if segments is None or not len(segments):
                continue
            chunks.append(segments)
            heights.append(segments[:, :, 2].mean(axis=1))
        cmap, norm, _z = _layer_colour_map(stack)
        if chunks:
            segments = np.concatenate(chunks, axis=0)
            values = np.concatenate(heights, axis=0)
            ax.add_collection3d(_collection_3d(
                segments, cmap(norm(values)), linewidth, alpha=0.70))
            scalar = ScalarMappable(norm=norm, cmap=cmap)
            ax.set_position([-0.04, -0.17, 0.98, 1.23])
            cax = fig.add_axes([0.895, 0.20, 0.012, 0.56])
            colorbar = fig.colorbar(scalar, cax=cax)
            colorbar.set_label('physical z (mm)', fontsize=8.5)
            colorbar.set_ticks([height for height, _label
                                in stack_height_ticks(stack)])
            short_labels = {'L1 z1 row': 'L1 z1', 'L1 z2 row': 'L1 z2'}
            colorbar.ax.set_yticklabels(
                [f'{height:.3f} {short_labels.get(label, label)}'
                 for height, label in stack_height_ticks(stack)],
                fontsize=6.4)
        title = (
            f'Corrected L1-L5 model: all {run["routed"]}/{TOTAL_CONNECTIONS} '
            f'routed routes, coloured by PHYSICAL z\n'
            f'L1 interface rows: 0.000 / 0.500 mm | L2-L5 exploratory routing '
            f'heights: ' +
            ', '.join(f'L{layer}={height:.2f} mm' for layer, height
                      in sorted(stack['routing'].items())) +
            f'\nstack "{stack["name"]}" | R={RADIUS_MM:g} mm | colours are the '
            f'stored physical heights, not logical layer ids')
        entry_kind = 'full_1024_layout_height_colored'
    else:
        for plane in PLANE_ORDER:
            segments = segments_by_plane.get(plane)
            if segments is None or not len(segments):
                continue
            ax.add_collection3d(_collection_3d(
                segments, PLANE_COLORS[plane], linewidth))
        from matplotlib.lines import Line2D
        handles = [Line2D([0], [0], color=PLANE_COLORS[plane], linewidth=2.0,
                          label=f'{plane} row routes')
                   for plane in PLANE_ORDER]
        ax.legend(handles=handles, loc='upper left', fontsize=7.5,
                  framealpha=0.85)
        title = (
            f'Corrected L1-L5 model: full {run["routed"]}/{TOTAL_CONNECTIONS} '
            f'channel 3D layout (wireframe)\n'
            f'L1 interface layer contains BOTH port rows (z1 row 0.000 mm '
            f'blue, z2 row 0.500 mm red); L2-L5 are exploratory routing '
            f'layers (heights unconfirmed_simulation)\n'
            f'stack "{stack["name"]}" | R={RADIUS_MM:g} mm | z axis '
            f'exaggerated for display')
        entry_kind = 'full_1024_layout_3d'
    exaggeration = _setup_3d_axes(ax, stack, run)
    fig.suptitle(title + f' | vertical exaggeration ~{exaggeration:.0f}x',
                 fontsize=10.0, y=0.985)
    _save(fig, output_path, tight=False)
    return {
        'file': _rel(output_path),
        'kind': entry_kind,
        'run': run['label'],
        'description': (f'{mode}-coloured 3D layout of {run["routed"]} routed '
                        f'L1-L5 routes'),
        'z_exaggeration': round(exaggeration, 1),
    }


# --------------------------------------------------------------------------- #
# 5) example multilayer route
# --------------------------------------------------------------------------- #
def _pick_example_route(run):
    best = None
    for route in run['routes']:
        transitions = route_transition_count(route)
        try:
            length = float(route.get('length_mm') or 0.0)
        except (TypeError, ValueError):
            length = 0.0
        key = (transitions, length)
        if best is None or key > best[0]:
            best = (key, route)
    return best[1] if best else None


def _route_3d_points(route):
    points = []
    for part in route.get('parts') or []:
        kind = part.get('kind')
        if kind == 'flat':
            xy = flat_polyline(part, DISPLAY_SAGITTA_MM)
            if xy is None:
                continue
            z = _as_float(part.get('z_mm'))
            local = np.column_stack([xy, np.full(len(xy), z if z else 0.0)])
        elif kind == 'transition':
            try:
                local = transition_polyline(part, TRANSITION_DISPLAY_STEP_MM)
            except (KeyError, TypeError, ValueError):
                continue
        else:
            continue
        if local is None or len(local) < 2:
            continue
        if points and float(np.hypot(*(local[0, :2] - points[-1][:2]))) < 1e-6 \
                and abs(local[0, 2] - points[-1][2]) < 1e-6:
            local = local[1:]
        points.extend(local.tolist())
    return np.asarray(points) if points else None


def render_example_route(run, output_path, output_xz):
    plt = pyplot()
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D
    route = _pick_example_route(run)
    if route is None:
        raise RuntimeError('no routed route available')
    stack = run['stack']
    sequence = route_layer_sequence(route)
    points = _route_3d_points(route)
    if points is None:
        raise RuntimeError('example route has no sampled parts')
    transitions = route_transition_count(route)
    plane = _route_plane(route)
    # 3D figure, coloured by path progress, transition mid-points annotated.
    fig = plt.figure(figsize=(15.0, 9.4))
    ax = fig.add_subplot(111, projection='3d')
    ax.set_position([-0.02, -0.12, 1.02, 1.16])
    segments = np.stack([points[:-1], points[1:]], axis=1)
    colours = plt.get_cmap('viridis')(np.linspace(0.05, 0.95, len(segments)))
    ax.add_collection3d(_collection_3d(segments, colours, 1.6, alpha=0.95))
    transition_parts = [part for part in route.get('parts') or []
                        if part.get('kind') == 'transition']
    for index, part in enumerate(transition_parts, start=1):
        start = np.asarray(part.get('start', [0, 0]), dtype=float)
        z0, z1 = _part_z_bounds(part)
        from_layer = part.get('from_layer', '?')
        to_layer = part.get('to_layer', '?')
        ax.scatter([start[0]], [start[1]], [z0], s=34, c='#ff7043',
                   depthshade=False)
        ax.text(start[0], start[1], z1 + 0.05,
                f'{index}: L{from_layer}->L{to_layer}', fontsize=6.8,
                color='#333333')
    exaggeration = _setup_3d_axes(ax, stack, run)
    handles = [Line2D([0], [0], color=plt.get_cmap('viridis')(0.1),
                      linewidth=2.0, label='route start'),
               Line2D([0], [0], color=plt.get_cmap('viridis')(0.9),
                      linewidth=2.0, label='route end'),
               Line2D([0], [0], color='#ff7043', marker='o', linewidth=0,
                      label='transition start points')]
    ax.legend(handles=handles, loc='lower left', fontsize=7.0,
              framealpha=0.85)
    sequence_text = ' -> '.join(f'L{layer}' for layer in sequence)
    fig.suptitle(
        f'Example multilayer route (route_id {route.get("route_id")}, '
        f'{plane} row) | {transitions} transitions | layer sequence '
        f'{sequence_text}\n'
        f'L1 interface rows 0.000/0.500 mm; L2-L5 heights are '
        f'exploratory / unconfirmed_simulation | R={RADIUS_MM:g} mm '
        f'transitions | z exaggerated ~{exaggeration:.0f}x',
        fontsize=10.0, y=0.985)
    _save(fig, output_path, tight=False)
    # XZ side view + elevation profile.
    fig2, (ax_xz, ax_profile) = plt.subplots(2, 1, figsize=(13.5, 9.0),
                                             gridspec_kw={'height_ratios':
                                                          [1.0, 0.85]})
    progress = np.linspace(0.0, 1.0, len(points))
    ax_xz.scatter(points[:, 0], points[:, 2], c=progress, cmap='viridis',
                  s=4, zorder=3)
    ax_xz.plot(points[:, 0], points[:, 2], color='#888888', linewidth=0.5,
               zorder=2)
    for height, label in stack_height_ticks(stack):
        ax_xz.axhline(height, color='#bbbbbb', linewidth=0.7, linestyle='--',
                      zorder=1)
        ax_xz.text(ax_xz.get_xlim()[0] if False else points[:, 0].min(),
                   height, f' {label} = {height:.3f} mm', fontsize=6.8,
                   va='bottom', color='#555555')
    ax_xz.set_xlabel('x (mm)')
    ax_xz.set_ylabel('physical z (mm)')
    ax_xz.set_title('XZ side view (projection of the 3D route)', fontsize=9.5)
    ax_xz.grid(alpha=0.25, linewidth=0.5)
    cumulative = np.concatenate(
        [[0.0], np.cumsum(np.linalg.norm(np.diff(points[:, :2], axis=0),
                                         axis=1))])
    ax_profile.plot(cumulative, points[:, 2], color='#1565c0', linewidth=1.6)
    ax_profile.fill_between(cumulative, points[:, 2], alpha=0.15,
                            color='#1565c0')
    for height, label in stack_height_ticks(stack):
        ax_profile.axhline(height, color='#bbbbbb', linewidth=0.7,
                           linestyle='--')
        ax_profile.text(cumulative.max(), height, f'{label} = {height:.3f}',
                        fontsize=6.6, va='bottom', ha='right',
                        color='#555555')
    ax_profile.set_xlabel('cumulative horizontal path length (mm)')
    ax_profile.set_ylabel('physical z (mm)')
    ax_profile.set_title('elevation profile (z along the route)', fontsize=9.5)
    ax_profile.grid(alpha=0.25, linewidth=0.5)
    fig2.suptitle(
        f'Example multilayer route {route.get("route_id")} ({plane} row) - '
        f'layer sequence {" -> ".join(f"L{layer}" for layer in sequence)} | '
        f'{transitions} R={RADIUS_MM:g} mm transitions', fontsize=10.5)
    _save(fig2, output_xz, tight=False)
    return {
        'file': _rel(output_path),
        'xz_file': _rel(output_xz),
        'kind': 'example_multilayer_route',
        'run': run['label'],
        'description': (f'example route {route.get("route_id")} with '
                        f'{transitions} transitions and layer sequence '
                        f'{"-".join(str(layer) for layer in sequence)}'),
        'route_id': route.get('route_id'),
        'plane': plane,
        'layer_sequence': sequence,
        'n_transitions': int(transitions),
        'length_mm': route.get('length_mm'),
    }


# --------------------------------------------------------------------------- #
# 6) per-layer counts and transitions
# --------------------------------------------------------------------------- #
def render_counts_figure(runs, output_path, stack):
    plt = pyplot()
    from matplotlib import colormaps
    fig, axes = plt.subplots(1, 3, figsize=(17.5, 5.8))
    scheme_text = ', '.join(f'{run["scheme"]}: {run["routed"]}'
                            for run in runs)
    # (a) routes using each logical layer
    layer_counts = []
    for layer_id in LAYER_IDS:
        count = sum(layer_route_count(run, layer_id) for run in runs)
        layer_counts.append(count)
    cmap, norm, _heights = _layer_colour_map(stack)
    colours = []
    for layer_id in LAYER_IDS:
        if layer_id == 1:
            colours.append(PLANE_COLORS['z1'])
        else:
            height = stack['routing'].get(layer_id)
            colours.append(cmap(norm(height)) if height is not None
                           else '#777777')
    bars = axes[0].bar([f'L{layer_id}' for layer_id in LAYER_IDS],
                       layer_counts, color=colours, alpha=0.9,
                       edgecolor='#222222', linewidth=0.4)
    axes[0].bar_label(bars, fmt='%d', fontsize=8.0, padding=2)
    axes[0].set_title('routes using each logical layer\n(layer sequence '
                      'members; L1 = interface, contains all routes)',
                      fontsize=9.0)
    axes[0].set_ylabel('routed routes')
    axes[0].grid(True, axis='y', alpha=0.28, linewidth=0.5)
    # (b) transitions per route histogram
    transition_counter = Counter(route_transition_count(route)
                                 for run in runs for route in run['routes'])
    bins = sorted(transition_counter)
    if bins:
        max_bin = max(max(bins), 2)
        labels = [str(value) for value in range(0, max_bin + 1)]
        values = [transition_counter.get(value, 0)
                  for value in range(0, max_bin + 1)]
        bars = axes[1].bar(labels, values, color='#5e35b1', alpha=0.9,
                           edgecolor='#222222', linewidth=0.4)
        axes[1].bar_label(bars, fmt='%d', fontsize=8.0, padding=2)
        axes[1].set_ylabel('routes')
    axes[1].set_xlabel('transitions per route (0 = stays on L1)')
    axes[1].set_title('transitions-per-route histogram', fontsize=9.0)
    axes[1].grid(True, axis='y', alpha=0.28, linewidth=0.5)
    # (c) layer-sequence histogram (top 8)
    sequence_counter = Counter(
        '-'.join(str(layer) for layer in route_layer_sequence(route))
        for run in runs for route in run['routes'])
    top = sequence_counter.most_common(8)
    if top:
        labels = [f'L {item[0]}'.replace('-', '-L') for item in top]
        values = [item[1] for item in top]
        bars = axes[2].barh(range(len(top)), values, color='#00897b',
                            alpha=0.9, edgecolor='#222222', linewidth=0.4)
        for index, value in enumerate(values):
            axes[2].text(value + max(values) * 0.01, index, str(value),
                         va='center', fontsize=8.0)
        axes[2].set_yticks(range(len(top)))
        axes[2].set_yticklabels(labels, fontsize=7.0)
        axes[2].invert_yaxis()
    axes[2].set_xlabel('routes')
    axes[2].set_title('layer-sequence histogram (top 8 sequences)',
                      fontsize=9.0)
    axes[2].grid(True, axis='x', alpha=0.28, linewidth=0.5)
    total_routes = sum(run['routed'] for run in runs)
    total_transitions = sum(route_transition_count(route)
                            for run in runs for route in run['routes'])
    fig.suptitle(
        f'L1-L5 route statistics across selected runs ({scheme_text}; '
        f'{total_routes} routes, {total_transitions} transitions) | '
        f'stack "{stack["name"]}" (L2-L5 heights unconfirmed_simulation)',
        fontsize=10.5)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.94))
    _save(fig, output_path, tight=False)
    return {
        'file': _rel(output_path),
        'kind': 'per_layer_counts_and_transitions',
        'run': ', '.join(run['label'] for run in runs),
        'description': ('routes per logical layer, transitions-per-route '
                        'histogram and layer-sequence histogram'),
        'layer_route_counts': {f'L{layer_id}': count
                               for layer_id, count in zip(LAYER_IDS,
                                                          layer_counts)},
        'transition_histogram': {str(key): value
                                 for key, value in sorted(
                                     transition_counter.items())},
        'top_layer_sequences': [[label, value] for label, value in top],
    }


# --------------------------------------------------------------------------- #
# 7) comparisons
# --------------------------------------------------------------------------- #
def old_wrong_model_counts(caveats):
    """Live read of the old (wrong-model) 2.5D counts, fallback to constants."""
    counts = {}
    source = {}
    for scheme in SCHEME_ORDER:
        path = (R15_ROOT / '25d' / f'scheme{scheme}' / 'layers5'
                / 'run_summary.json')
        value = None
        if path.exists():
            try:
                payload = _json_load(path)
                value = (payload.get('statistics') or {}).get('routed')
            except (OSError, json.JSONDecodeError):
                value = None
        if value is not None:
            counts[scheme] = int(value)
            source[scheme] = str(path)
        else:
            counts[scheme] = OLD_25D_CONST[scheme]
            source[scheme] = 'constant'
            caveats.append(f'old 2.5D {scheme} count not found in '
                           f'{path}; using historical constant '
                           f'{OLD_25D_CONST[scheme]}')
    return counts, source


def render_old_vs_new(old_counts, old_source, runs_by_scheme, output_path):
    plt = pyplot()
    from matplotlib.patches import Patch
    fig, ax = plt.subplots(figsize=(12.0, 6.8))
    positions = np.arange(len(SCHEME_ORDER), dtype=float)
    width = 0.34
    old_values = [old_counts.get(scheme) for scheme in SCHEME_ORDER]
    new_values = []
    for scheme in SCHEME_ORDER:
        run = runs_by_scheme.get(scheme)
        new_values.append(run['routed'] if run is not None else None)
    bars_old = ax.bar(positions - width / 2.0,
                      [value or 0 for value in old_values], width=width,
                      color='#9e9e9e', hatch='//', edgecolor='#424242',
                      linewidth=0.6, alpha=0.95,
                      label='OLD 2.5D: wrong z1=L1 / z2=L5 model '
                            '(NOT comparable as process results)')
    bars_new = ax.bar(positions + width / 2.0,
                      [value or 0 for value in new_values], width=width,
                      color='#2e7d32', edgecolor='#1b5e20', linewidth=0.6,
                      alpha=0.95,
                      label='NEW corrected L3D: L1 = interface with both rows, '
                            'L2-L5 exploratory (heights unconfirmed)')
    for bar_item, value in zip(bars_old, old_values):
        if value is None:
            continue
        ax.text(bar_item.get_x() + bar_item.get_width() / 2.0, value + 8.0,
                f'{value}/1024\n(old model)', ha='center', va='bottom',
                fontsize=8.0, color='#424242')
    for bar_item, value in zip(bars_new, new_values):
        if value is None:
            ax.text(bar_item.get_x() + bar_item.get_width() / 2.0, 12.0,
                    'pending', ha='center', va='bottom', fontsize=8.0,
                    color='#777777', rotation=90)
            continue
        ax.text(bar_item.get_x() + bar_item.get_width() / 2.0, value + 8.0,
                f'{value}/1024', ha='center', va='bottom', fontsize=8.5,
                color='#1b5e20')
    ax.axhline(TOTAL_CONNECTIONS, color='#333333', linewidth=0.8,
               linestyle='--')
    ax.text(0.0, TOTAL_CONNECTIONS + 42.0,
            f'{TOTAL_CONNECTIONS} connections', ha='left', fontsize=7.5)
    ax.set_xticks(positions)
    ax.set_xticklabels([f'scheme {scheme}' for scheme in SCHEME_ORDER],
                       fontsize=10.0)
    ax.set_ylabel('routed connections (of 1024)', fontsize=9.0)
    ax.set_ylim(0.0, TOTAL_CONNECTIONS * 1.26)
    ax.grid(True, axis='y', alpha=0.28, linewidth=0.5)
    ax.legend(fontsize=7.6, loc='upper left', framealpha=0.95)
    note = (
        f'OLD counts {old_counts.get("A", "?")}/{old_counts.get("B", "?")} '
        f'(A/B) come from the previous 5-layer 2.5D experiment, which used the '
        f'WRONG model: z1 plane = L1 (z=0), z2 plane = L5 (z=0.5), L2-L4 '
        f'squeezed between 0 and 0.5 mm.\n'
        f'That is NOT the corrected L1-L5 physical model, so the old counts are '
        f'NOT comparable as process results (kept as history only).\n'
        f'NEW counts are exploratory: L2-L5 heights are unconfirmed_simulation '
        f'parameters; formal process acceptance is refused until confirmed.')
    ax.text(0.0, -0.14, note, transform=ax.transAxes, ha='left', va='top',
            fontsize=7.4,
            bbox=dict(boxstyle='round,pad=0.4', facecolor='#fff8e1',
                      edgecolor='#f9a825'))
    ax.set_title(
        'Old (wrong-model) 2.5D counts vs new corrected L3D counts - NOT '
        'comparable as process results\n'
        'old values: 5-layer 2.5D with z1=L1 / z2=L5 (history only) | new '
        'values: corrected L1-L5 physical model (exploratory heights)',
        fontsize=10.0)
    fig.subplots_adjust(left=0.09, right=0.98, top=0.86, bottom=0.26)
    _save(fig, output_path, tight=False)
    return {
        'file': _rel(output_path),
        'kind': 'old25d_vs_new_l3d',
        'run': None,
        'description': ('old wrong-model 2.5D counts '
                        f'({old_counts.get("A")}/{old_counts.get("B")}) vs new '
                        'corrected L3D counts - explicitly marked not '
                        'comparable as process results'),
        'old_counts': dict(old_counts),
        'old_source': dict(old_source),
        'new_counts': {scheme: new_values[index]
                       for index, scheme in enumerate(SCHEME_ORDER)},
        'comparable_as_process_results': False,
    }


def render_a_vs_b(runs_by_scheme, output_path):
    plt = pyplot()
    fig, (ax_total, ax_rows) = plt.subplots(1, 2, figsize=(13.5, 6.0))
    schemes = [scheme for scheme in SCHEME_ORDER if scheme in runs_by_scheme]
    positions = np.arange(len(schemes), dtype=float)
    totals = [runs_by_scheme[scheme]['routed'] for scheme in schemes]
    colours = [SCHEME_COLORS.get(scheme, '#555555') for scheme in schemes]
    bars = ax_total.bar(positions, totals, color=colours, alpha=0.9,
                        edgecolor='#222222', linewidth=0.5, width=0.55)
    ax_total.bar_label(bars, fmt='%d/1024', fontsize=9.0, padding=3)
    ax_total.axhline(TOTAL_CONNECTIONS, color='#333333', linewidth=0.8,
                     linestyle='--')
    ax_total.set_xticks(positions)
    ax_total.set_xticklabels([f'scheme {scheme}' for scheme in schemes],
                             fontsize=10.0)
    ax_total.set_ylabel('routed connections', fontsize=9.0)
    ax_total.set_ylim(0.0, TOTAL_CONNECTIONS * 1.16)
    ax_total.grid(True, axis='y', alpha=0.28, linewidth=0.5)
    ax_total.set_title('A vs B: total routed (corrected L1-L5 model; '
                       'exploratory)', fontsize=9.5)
    rows = {'z1': [], 'z2': []}
    for scheme in schemes:
        counts = route_plane_counts(runs_by_scheme[scheme])
        rows['z1'].append(counts['z1'])
        rows['z2'].append(counts['z2'])
    ax_rows.bar(positions, rows['z1'], color=PLANE_COLORS['z1'], alpha=0.9,
                edgecolor='#222222', linewidth=0.4, width=0.55,
                label='z1 row (L1, physical z = 0.0 mm)')
    ax_rows.bar(positions, rows['z2'], bottom=rows['z1'],
                color=PLANE_COLORS['z2'], alpha=0.9, edgecolor='#222222',
                linewidth=0.4, width=0.55,
                label='z2 row (L1, physical z = 0.5 mm)')
    for index, scheme in enumerate(schemes):
        total = rows['z1'][index] + rows['z2'][index]
        ax_rows.text(index, total + 8.0,
                     f'{rows["z1"][index]} / {rows["z2"][index]}',
                     ha='center', va='bottom', fontsize=8.5)
    ax_rows.axhline(PLANE_TOTAL, color='#333333', linewidth=0.8,
                    linestyle='--')
    ax_rows.text(0.02, PLANE_TOTAL + 12.0,
                 f'{PLANE_TOTAL} connections per row', ha='left', fontsize=7.5)
    ax_rows.set_xticks(positions)
    ax_rows.set_xticklabels([f'scheme {scheme}' for scheme in schemes],
                            fontsize=10.0)
    ax_rows.set_ylabel('routed connections', fontsize=9.0)
    max_total = max(totals) if totals else PLANE_TOTAL
    ax_rows.set_ylim(0.0, max(PLANE_TOTAL * 1.15, max_total * 1.15))
    ax_rows.grid(True, axis='y', alpha=0.28, linewidth=0.5)
    ax_rows.legend(fontsize=7.8, loc='upper left', framealpha=0.95)
    ax_rows.set_title('A vs B: routed per L1 interface row (z1 / z2)',
                      fontsize=9.5)
    fig.suptitle(
        'Corrected L1-L5 model: A vs B routed counts | both rows belong to L1 '
        '(z1=0.0 mm, z2=0.5 mm); L2-L5 heights are exploratory '
        'unconfirmed_simulation - not a process result', fontsize=10.5)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.92))
    _save(fig, output_path, tight=False)
    return {
        'file': _rel(output_path),
        'kind': 'a_vs_b_l3d',
        'run': ', '.join(schemes),
        'description': 'A vs B routed counts and per-interface-row split for '
                       'the corrected L1-L5 model',
        'totals': {scheme: runs_by_scheme[scheme]['routed']
                   for scheme in schemes},
        'per_row': {scheme: {'z1': rows['z1'][index],
                             'z2': rows['z2'][index]}
                    for index, scheme in enumerate(schemes)},
    }


# --------------------------------------------------------------------------- #
# manifest
# --------------------------------------------------------------------------- #
def write_manifest(manifest_path, files, runs, stack, caveats):
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
        path = (active_root / name) if not Path(name).is_absolute() \
            else Path(name)
        if path.exists():
            files_by_path[name] = entry
    for entry in files:
        files_by_path[entry['file']] = entry
    runs_table = []
    for run in runs:
        runs_table.append({
            'label': run['label'],
            'scheme': run['scheme'],
            'stage': run.get('stage'),
            'max_transitions': int(run.get('max_transitions') or 0),
            'stack': run['stack']['name'],
            'provenance': run['stack']['provenance'],
            'routed': int(run['routed']),
            'failed': run['failed'],
            'total': int(run['total']),
            'per_row': route_plane_counts(run),
            'n_transitions': sum(route_transition_count(route)
                                 for route in run['routes']),
            'transition_histogram': {
                str(key): value for key, value in sorted(Counter(
                    route_transition_count(route)
                    for route in run['routes']).items())},
            'is_smoke': bool(run['is_smoke']),
            'run_dir': _rel(run['run_dir']),
            'routes_file': _rel(run['routes_path']),
            'routes_sha256': _sha256(run['routes_path']),
            'transition_radii': run['transition_radii'],
        })
    payload = {
        'schema': SCHEMA,
        'tool': TOOL,
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'root': str(active_root),
        'model': {
            'name': 'corrected_L1_L5_physical_model',
            'interface_layer': {'layer_id': 1,
                                'rows': dict(stack['rows']),
                                'note': 'L1 contains BOTH port rows: z1 row '
                                        '0.0 mm, z2 row 0.5 mm'},
            'routing_layers': {f'L{layer_id}': height for layer_id, height
                               in stack['routing'].items()},
            'provenance': stack['provenance'],
            'provenance_note': stack['provenance_note'],
            'old_wrong_model': {
                'description': OLD_MODEL_NOTE,
                'old_25d_counts': dict(OLD_25D_CONST),
                'comparable_as_process_results': False,
            },
        },
        'stack': {
            'name': stack['name'],
            'rows': dict(stack['rows']),
            'routing': {str(key): value for key, value
                        in stack['routing'].items()},
            'provenance': stack['provenance'],
            'source': stack['source'],
            'defaulted': bool(stack.get('defaulted')),
        },
        'style': {
            'board_mm': BOARD_MM,
            'dpi': DPI,
            'radius_mm': RADIUS_MM,
            'plane_colors': dict(PLANE_COLORS),
            'display_sagitta_mm': DISPLAY_SAGITTA_MM,
            'display_sagitta_3d_mm': DISPLAY_SAGITTA_3D_MM,
            'labels': 'English only (no CJK glyphs in figures)',
        },
        'runs': runs_table,
        'files': sorted(files_by_path.values(), key=lambda item: item['file']),
        'caveats': list(caveats),
    }
    manifest_path.write_text(json.dumps(payload, indent=1, ensure_ascii=False),
                             encoding='utf-8')
    return payload


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _build_parser():
    parser = argparse.ArgumentParser(
        description='Render corrected L1-L5 (L3D) figures: L1 dual-row '
                    'interface zoom, physical layer-stack schematic, per-layer '
                    'routing maps, full 3D layouts, multilayer example route, '
                    'statistics and old-vs-new comparisons.')
    parser.add_argument('--root', default=None,
                        help='L1-L5 experiment root (default '
                             'outputs/four_side_1024_v2_l1l5_v01)')
    parser.add_argument('--include-smoke', action='store_true',
                        help='also use routes_l3d.json fixtures under _smoke/')
    parser.add_argument('--verbose', action='store_true')
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    root = Path(args.root) if args.root else Path(DEFAULT_ROOT)
    root = root if root.is_absolute() else PROJECT_ROOT / root
    root = root.resolve()
    _ACTIVE_ROOT['path'] = root
    figures_dir = root / 'figures'
    comparison_dir = root / 'comparison'
    figures_dir.mkdir(parents=True, exist_ok=True)
    comparison_dir.mkdir(parents=True, exist_ok=True)
    _WRITE_ALLOWED.clear()
    _WRITE_ALLOWED.extend([figures_dir, comparison_dir])
    started = time.perf_counter()
    caveats = []
    files = []
    _apply_style()

    # port table + runs -----------------------------------------------------
    port_data = load_port_data(caveats)
    runs = discover_runs(root, args.include_smoke, caveats)
    if not runs:
        caveats.append(f'no routes_l3d.json found under {root} (pending data)')
    runs_by_scheme = select_primary_runs(runs, caveats)
    if runs_by_scheme:
        primary = max(runs_by_scheme.values(),
                      key=lambda run: (run['routed'], run['scheme']))
        stack = primary['stack']
    else:
        stack = normalise_stack({}, root, caveats)

    # 1) L1 dual-row interface zoom ---------------------------------------
    if port_data is not None:
        try:
            entry = render_l1_interface_zoom(
                figures_dir / 'l1_interface_two_rows_zoom.png', port_data,
                caveats)
            files.append(entry)
            print(f"[plots_l3d] {entry['file']}")
        except Exception as exc:  # noqa: BLE001
            message = (f'l1_interface_two_rows_zoom: skipped '
                       f'({type(exc).__name__}: {exc})')
            print(f'[plots_l3d] WARNING {message}')
            caveats.append(message)
    # 2) physical layer-stack schematic -----------------------------------
    try:
        entry = render_layer_stack(
            stack, figures_dir / 'layer_stack_physical_heights.png')
        files.append(entry)
        print(f"[plots_l3d] {entry['file']}")
    except Exception as exc:  # noqa: BLE001
        message = f'layer_stack_physical_heights: skipped ({type(exc).__name__}: {exc})'
        print(f'[plots_l3d] WARNING {message}')
        caveats.append(message)

    # 3) per-layer routing maps -------------------------------------------
    connectors = (port_data or {}).get('connectors') or []
    if runs_by_scheme:
        primary = max(runs_by_scheme.values(),
                      key=lambda run: (run['routed'], run['scheme']))
        for layer_id in LAYER_IDS:
            output_path = figures_dir / f'layer_L{layer_id}_routing.png' \
                if layer_id == 1 else figures_dir / f'layer_L{layer_id}.png'
            try:
                entry = render_layer_routing_map(primary, layer_id,
                                                 output_path, connectors)
            except Exception as exc:  # noqa: BLE001
                message = (f'layer L{layer_id}: skipped '
                           f'({type(exc).__name__}: {exc})')
                print(f'[plots_l3d] WARNING {message}')
                caveats.append(message)
                continue
            files.append(entry)
            print(f"[plots_l3d] {entry['file']}")
    else:
        caveats.append('layer_L*.png routing maps skipped (no L3D run '
                       'available)')

    # 4) full layout 3D + height-coloured --------------------------------
    if runs_by_scheme:
        primary = max(runs_by_scheme.values(),
                      key=lambda run: (run['routed'], run['scheme']))
        for mode, filename in (('plane', 'full_1024_layout_3d.png'),
                               ('height',
                                'full_1024_layout_height_colored.png')):
            try:
                entry = render_full_layout_3d(
                    primary, figures_dir / filename, mode=mode)
            except Exception as exc:  # noqa: BLE001
                message = f'{filename}: skipped ({type(exc).__name__}: {exc})'
                print(f'[plots_l3d] WARNING {message}')
                caveats.append(message)
                continue
            files.append(entry)
            print(f"[plots_l3d] {entry['file']}")

    # 5) example multilayer route ----------------------------------------
    if runs_by_scheme:
        # pick the run that actually contains the richest multi-transition data
        example_run = max(runs_by_scheme.values(),
                          key=lambda run: (int(run.get('max_transitions') or 0),
                                           run['routed']))
        try:
            entry = render_example_route(
                example_run, figures_dir / 'example_multilayer_route.png',
                figures_dir / 'example_multilayer_route_xz.png')
            files.append(entry)
            files.append({
                'file': entry['xz_file'],
                'kind': 'example_multilayer_route_xz',
                'run': example_run['label'],
                'description': (f'XZ side view + elevation profile of the '
                                f'example multilayer route '
                                f'{entry["route_id"]}'),
                'route_id': entry['route_id'],
            })
            print(f"[plots_l3d] {entry['file']}")
            print(f"[plots_l3d] {entry['xz_file']}")
            if int(entry['n_transitions']) < 2:
                caveats.append(
                    f'example route {entry["route_id"]} '
                    f'(run {example_run["label"]}) has '
                    f'{entry["n_transitions"]} transitions (no >=2-transition '
                    f'route in the available data)')
        except Exception as exc:  # noqa: BLE001
            message = f'example_multilayer_route: skipped ({type(exc).__name__}: {exc})'
            print(f'[plots_l3d] WARNING {message}')
            caveats.append(message)

    # 6) per-layer counts and transitions --------------------------------
    selected = [runs_by_scheme[scheme] for scheme in SCHEME_ORDER
                if scheme in runs_by_scheme]
    if selected:
        try:
            entry = render_counts_figure(
                selected, figures_dir / 'per_layer_counts_and_transitions.png',
                stack)
            files.append(entry)
            print(f"[plots_l3d] {entry['file']}")
        except Exception as exc:  # noqa: BLE001
            message = (f'per_layer_counts_and_transitions: skipped '
                       f'({type(exc).__name__}: {exc})')
            print(f'[plots_l3d] WARNING {message}')
            caveats.append(message)

    # 7) comparisons ------------------------------------------------------
    if runs_by_scheme:
        old_counts, old_source = old_wrong_model_counts(caveats)
        try:
            entry = render_old_vs_new(
                old_counts, old_source, runs_by_scheme,
                comparison_dir / 'old25d_vs_new_l3d.png')
            files.append(entry)
            print(f"[plots_l3d] {entry['file']}")
        except Exception as exc:  # noqa: BLE001
            message = f'old25d_vs_new_l3d: skipped ({type(exc).__name__}: {exc})'
            print(f'[plots_l3d] WARNING {message}')
            caveats.append(message)
        try:
            entry = render_a_vs_b(
                runs_by_scheme, comparison_dir / 'a_vs_b_l3d.png')
            files.append(entry)
            print(f"[plots_l3d] {entry['file']}")
        except Exception as exc:  # noqa: BLE001
            message = f'a_vs_b_l3d: skipped ({type(exc).__name__}: {exc})'
            print(f'[plots_l3d] WARNING {message}')
            caveats.append(message)
    else:
        caveats.append('old25d_vs_new_l3d / a_vs_b_l3d: skipped '
                       '(no L3D run available)')

    # manifest ------------------------------------------------------------
    manifest_path = comparison_dir / 'plots_manifest.json'
    files.append({
        'file': _rel(manifest_path),
        'kind': 'plots_manifest',
        'run': None,
        'description': 'inventory of every figure generated by plots_l3d',
    })
    manifest = write_manifest(manifest_path, files, runs, stack, caveats)
    print(json.dumps({
        'tool': TOOL,
        'root': str(root),
        'files': len(manifest['files']),
        'runs': {run['label']: run['routed'] for run in runs},
        'stack': manifest['stack'],
        'caveats': caveats,
        'wall_seconds': round(time.perf_counter() - started, 2),
    }, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
