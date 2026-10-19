"""Artifact pipeline for the D56 1024-channel four-side single-layer run.

Reads the authoritative analytic routing result from ``--input-dir/routes.json``
(SPEC section 3.1; a plain list of route records is also accepted), falling back
to ``routes_geometry.json`` + ``failed_routes.json`` when ``routes.json`` is
absent, recomputes every reported statistic from the exact primitives, and writes
the 13 files required by ``four_side_1024/d56/SPEC.md`` section 3 into
``--run-dir``.

Contract highlights
-------------------
* Existing ``routes.json`` is preserved (copy when input dir differ); the analytic
  geometry of routed records is additionally written to ``routes_geometry.json``.
* ``length_mm`` and all crossing statistics are recomputed from primitives with
  ``four_side_1024.geometry`` / ``four_side_1024.conflicts``; input fields are
  only cross-checked, never copied into the final statistics.
* The final inter-route spacing verdict belongs to the independent validator
  (``four_side_1024/d56/validate_d56.py``). When that module exists it is called
  and its result is embedded in ``statistics.json -> independent_audit``; when
  it does not exist yet a clearly marked placeholder is written instead.
* Any routed count from 0 to 1024 is supported; failed records keep their full
  identity in ``routes.json`` and ``failed_routes.json``.
* Figure labels are English, matplotlib uses Agg, dpi is fixed to 200, and the
  board figures use ``aspect='equal'`` with limits slightly outside the board.
* Re-running is idempotent for our own files; ``run.log`` is appended to.

Usage
-----
    .venv\\Scripts\\python.exe -m four_side_1024.d56.outputs_d56 \\
        --run-dir outputs\\four_side_1024_d56_optimized
    # checkpoint preview before the final routes.json exists:
    .venv\\Scripts\\python.exe -m four_side_1024.d56.outputs_d56 \\
        --run-dir scratch\\preview \\
        --routes outputs\\four_side_1024_d56_optimized\\routes_checkpoint.json
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import inspect
import json
import math
import platform
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np

from ..conflicts import ConflictIndex
from ..geometry import length as geometry_length
from ..geometry import sample as geometry_sample
from ..geometry import validate as geometry_validate
from ..inputs import config as input_config
from ..inputs import load as load_inputs
from ..inputs import save_json
from ..outputs import COLORS
from . import plots_d56

SCHEMA_ROUTES = 'four_side_1024_d56_optimized_routes_v1'
SCHEMA_GEOMETRY = 'four_side_1024_d56_optimized_routes_geometry_v1'
SCHEMA_FAILED = 'four_side_1024_d56_optimized_failed_routes_v1'
SCHEMA_STATISTICS = 'four_side_1024_d56_optimized_statistics_v1'
BOARD_MM = 150.0
PAIR_ORDER = plots_d56.PAIR_ORDER
RELATIONS = ('opposite', 'adjacent')

REQUIRED_FILES = (
    '01_connectivity.png', '02_routing_all.png', '03_opposite_routes.png',
    '04_adjacent_routes.png', '05_crossing_heatmap.png', '06_routing_detail.png',
    '07_strategy_comparison.png', 'routing_all.svg', 'routing_all.gds',
    'routes.json', 'failed_routes.json', 'statistics.json', 'run.log',
)

ROUTED_STATUSES = {'routed', 'route', 'success', 'succeeded', 'ok', 'valid', 'done'}
FAILED_STATUSES = {'failed', 'failure', 'unrouted', 'rejected', 'fail'}

CANDIDATE_KEYS = ('family', 'track_mm', 'rule_track_mm', 'strategy', 'index',
                  'candidate_index', 'interface_mode', 'legacy_pass', 'evaluated')

FAILURE_CLASSES = (
    ('no_legal_candidate', ('no_legal', 'no legal', 'no_candidate', 'no candidate',
                            'no_legal_track', 'not_found', 'no_route')),
    ('search_budget_exhausted', ('budget', 'timeout', 'time_budget', 'exhausted')),
    ('rip_up_unresolved', ('rip_up', 'ripup', 'rip-up', 'reroute')),
    ('final_audit_rejected', ('audit_rejected', 'final_exact_audit', 'rejected')),
    ('invalid_geometry', ('invalid_geometry', 'geometry_missing', 'invalid_primitives',
                          'geometry_error')),
    ('input_incomplete', ('missing_from_routes_json', 'missing_from_input')),
)


# --------------------------------------------------------------------------- #
# logging / JSON / misc helpers
# --------------------------------------------------------------------------- #
class RunLog:
    """Append-only timestamped logger writing to ``run.log``."""

    def __init__(self, path):
        self.path = Path(path)
        self.entries = []

    def __call__(self, message):
        stamp = datetime.now().astimezone().isoformat(timespec='milliseconds')
        line = f'{stamp} {message}'
        self.entries.append(line)
        with self.path.open('a', encoding='utf-8') as handle:
            handle.write(line + '\n')
        try:
            print(line, flush=True)
        except Exception:
            pass


def _iso_now():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def _read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json_safe(value):
    try:
        return json.loads(json.dumps(value, default=str))
    except Exception:
        return str(value)


def _status_of(value):
    if isinstance(value, bool):
        return 'routed' if value else 'failed'
    if value is None:
        return 'failed'
    text = str(value).strip().lower()
    if text in ROUTED_STATUSES:
        return 'routed'
    return 'failed'


def classify_failure(reason):
    text = str(reason or '').lower()
    for name, needles in FAILURE_CLASSES:
        if any(needle in text for needle in needles):
            return name
    return 'other'


def _entries(value):
    """Accept a list, a ``{'routes': [...]}`` wrapper, or a keyed mapping."""
    if value is None:
        return []
    if isinstance(value, dict):
        for key in ('routes', 'failed_routes', 'records', 'items', 'results'):
            inner = value.get(key)
            if isinstance(inner, list):
                return list(inner)
        if all(isinstance(item, dict) for item in value.values()):
            entries = []
            for key, item in value.items():
                item = dict(item)
                item.setdefault('route_id', key)
                entries.append(item)
            return entries
        return []
    if isinstance(value, list):
        return list(value)
    return []


def normalize_primitives(primitives):
    """Keep only SPEC primitive fields, force layer 0 and plain floats."""
    if not isinstance(primitives, (list, tuple)) or not primitives:
        raise ValueError('empty or non-list primitives')
    cleaned = []
    for index, primitive in enumerate(primitives):
        kind = primitive.get('kind')
        if kind not in ('line', 'arc'):
            raise ValueError(f'primitive {index} has unknown kind {kind!r}')
        item = dict(kind=kind,
                    p0=[float(primitive['p0'][0]), float(primitive['p0'][1])],
                    p1=[float(primitive['p1'][0]), float(primitive['p1'][1])],
                    layer=0)
        if kind == 'arc':
            item.update(center=[float(primitive['center'][0]),
                                float(primitive['center'][1])],
                        radius=float(primitive['radius']),
                        start_angle=float(primitive['start_angle']),
                        sweep=float(primitive['sweep']))
        cleaned.append(item)
    return cleaned


def normalize_ablations(raw):
    """Convert a loose ablation table (list or mapping) into a list of dicts."""
    if raw is None:
        return []
    if isinstance(raw, dict):
        for key in ('ablations', 'results', 'strategies', 'experiments'):
            inner = raw.get(key)
            if isinstance(inner, (list, dict)):
                return normalize_ablations(inner)
        records = []
        for name, value in raw.items():
            if isinstance(value, dict):
                item = dict(value)
                item.setdefault('label', str(name))
            else:
                item = dict(label=str(name), success=value)
            records.append(item)
        return records
    if isinstance(raw, list):
        records = []
        for index, item in enumerate(raw):
            if isinstance(item, dict):
                record = dict(item)
                record.setdefault('label', record.get('name', record.get('strategy',
                                                                     f'ablation {index + 1}')))
                records.append(record)
            elif isinstance(item, (int, float)):
                records.append(dict(label=f'ablation {index + 1}', success=item))
        return records
    return []


def _candidate_metadata(entry):
    candidate = entry.get('candidate')
    if isinstance(candidate, dict) and candidate:
        return _json_safe(candidate)
    extracted = {key: entry[key] for key in CANDIDATE_KEYS if key in entry}
    return _json_safe(extracted) if extracted else None


# --------------------------------------------------------------------------- #
# input loading
# --------------------------------------------------------------------------- #
def _overlay_endpoints(endpoints, input_dir, log):
    path = Path(input_dir) / 'endpoints.json'
    if not path.exists():
        return endpoints
    try:
        payload = _read_json(path)
        items = payload if isinstance(payload, list) else list(payload.values())
        candidate = {item['endpoint_id']: item for item in items
                     if isinstance(item, dict) and 'endpoint_id' in item
                     and 'routing_xy' in item and 'inward' in item}
    except Exception as exc:  # pragma: no cover - defensive
        log(f'WARNING could not read {path.name} ({exc!r}); using inputs.load() endpoints')
        return endpoints
    if len(candidate) < 2:
        log(f'WARNING {path.name} has only {len(candidate)} usable endpoints; '
            'using inputs.load() endpoints')
        return endpoints
    missing = [row for row in endpoints if row not in candidate]
    if missing:
        log(f'WARNING {path.name} misses {len(missing)} endpoint identities; '
            'using inputs.load() endpoints')
        return endpoints
    log(f'loaded {len(candidate)} endpoint records from {path.name}')
    return candidate


def _overlay_connectors(connectors, input_dir, log):
    path = Path(input_dir) / 'connectors.json'
    if not path.exists():
        return connectors
    try:
        payload = _read_json(path)
        items = payload if isinstance(payload, list) else list(payload.values())
        candidate = [item for item in items
                     if isinstance(item, dict) and 'center_xy' in item and 'side' in item]
    except Exception as exc:  # pragma: no cover - defensive
        log(f'WARNING could not read {path.name} ({exc!r}); using inputs.load() connectors')
        return connectors
    if len(candidate) != 64:
        log(f'WARNING {path.name} has {len(candidate)} connectors instead of 64; '
            'using inputs.load() connectors')
        return connectors
    log(f'loaded {len(candidate)} connector records from {path.name}')
    return candidate


def _geometry_entries(value):
    if isinstance(value, dict):
        entries = value.get('routes')
        if isinstance(entries, list):
            return entries
        if all(isinstance(item, dict) for item in value.values()):
            result = []
            for key, item in value.items():
                item = dict(item)
                item.setdefault('route_id', key)
                result.append(item)
            return result
        return []
    return list(value) if isinstance(value, list) else []


def build_routes_payload(rows, geometry_payload, failed_payload, config, algorithm,
                         csv_sha256):
    """Generate a SPEC ``routes.json`` payload when the run dir has none."""
    identities = {row['route_id']: row for row in rows}
    geometry = {}
    for entry in _geometry_entries(geometry_payload):
        try:
            geometry[int(entry['route_id'])] = entry
        except (KeyError, TypeError, ValueError):
            continue
    failed = {}
    for entry in _entries(failed_payload):
        try:
            failed[int(entry['route_id'])] = entry
        except (KeyError, TypeError, ValueError):
            continue
    routes = []
    for route_id in sorted(identities):
        row = identities[route_id]
        record = dict(route_id=route_id, relation=row['relation'], pair=row['pair'],
                      source_side=row['source_side'], target_side=row['target_side'],
                      source_endpoint=row['source_endpoint'],
                      target_endpoint=row['target_endpoint'], layer=0)
        geometry_entry = geometry.get(route_id)
        if geometry_entry is not None and geometry_entry.get('primitives'):
            primitives = geometry_entry['primitives']
            record.update(status='routed', bend_count=sum(
                1 for primitive in primitives if primitive.get('kind') == 'arc'),
                primitives=primitives)
            candidate = _candidate_metadata(geometry_entry)
            if candidate:
                record['candidate'] = candidate
            if geometry_entry.get('length_mm') is not None:
                record['length_mm'] = float(geometry_entry['length_mm'])
        else:
            failure = failed.get(route_id, {})
            record.update(status='failed', reason=failure.get('reason', 'unknown_failure'),
                          evaluated=int(failure.get('evaluated', 0) or 0),
                          blockers=_json_safe(failure.get('blockers', {})),
                          classification=classify_failure(
                              failure.get('reason', 'unknown_failure')))
        routes.append(record)
    return dict(schema=SCHEMA_ROUTES, units='mm', layer=0,
                endpoint_mode=str(config.get('endpoint_mode', 'virtual_unfolded')),
                csv_sha256=csv_sha256, config=config, algorithm=algorithm,
                routes=routes)


def load_bundle(input_dir, run_dir, log, routes_override=None,
                run_status_override=None):
    """Load identities, endpoints, connectors and the authoritative route payload.

    ``routes_override`` allows pointing the pipeline at a checkpoint file such as
    ``outputs/four_side_1024_d56_optimized/routes_checkpoint.json`` before the
    final ``routes.json`` exists.
    """
    input_dir = Path(input_dir)
    run_dir = Path(run_dir)
    rows, endpoints, connectors, validation = load_inputs()
    log(f'four_side_1024.inputs.load(): {len(rows)} connections, '
        f'{len(endpoints)} endpoints, {len(connectors)} connectors, '
        f'csv_sha256={validation["csv_sha256"]}')
    endpoints = _overlay_endpoints(endpoints, input_dir, log)
    connectors = _overlay_connectors(connectors, input_dir, log)

    config = input_config()
    config_path = input_dir / 'config.json'
    if config_path.exists():
        try:
            loaded = _read_json(config_path)
            if isinstance(loaded, dict):
                config.update(loaded)
                log(f'loaded run configuration from {config_path.name} '
                    f'({len(loaded)} keys)')
        except Exception as exc:  # pragma: no cover - defensive
            log(f'WARNING could not read {config_path.name} ({exc!r}); using defaults')

    if routes_override is not None:
        routes_path = Path(routes_override)
        if not routes_path.is_file():
            raise SystemExit(f'--routes file does not exist: {routes_path}')
        log(f'--routes override: reading route payload from {routes_path}')
    else:
        routes_path = input_dir / 'routes.json'
    geometry_path = input_dir / 'routes_geometry.json'
    failed_path = input_dir / 'failed_routes.json'
    payload = None
    preserved = False
    generated = False
    routes_source = routes_path
    geometry_payload = None
    failed_payload = None
    if routes_path.exists():
        payload = _read_json(routes_path)
        preserved = routes_path.resolve() == (run_dir / 'routes.json').resolve()
        log(f'routes file {routes_path.name} exists ({routes_path.stat().st_size} bytes)')
    else:
        if geometry_path.exists():
            geometry_payload = _read_json(geometry_path)
        else:
            raise SystemExit(
                f'No routes.json or routes_geometry.json found in {input_dir}; '
                'run the D56 router first, point --input-dir at the run directory, '
                'or pass --routes <file>.')
        if failed_path.exists():
            failed_payload = _read_json(failed_path)
        payload = build_routes_payload(rows, geometry_payload, failed_payload,
                                       config, {}, validation['csv_sha256'])
        generated = True
        routes_source = None
        log('routes.json missing: generated a SPEC routes.json from '
            'routes_geometry.json + failed_routes.json')

    if isinstance(payload, dict):
        meta = payload
        raw_routes = _entries(payload)
        payload_config = payload.get('config')
        if isinstance(payload_config, dict):
            config.update(payload_config)
        payload_algorithm = payload.get('algorithm')
        if isinstance(payload_algorithm, dict):
            algorithm = dict(payload_algorithm)
        else:
            algorithm = {}
        csv_sha256 = str(payload.get('csv_sha256') or validation['csv_sha256'])
        endpoint_mode = str(payload.get('endpoint_mode')
                            or config.get('endpoint_mode', 'virtual_unfolded'))
        schema = payload.get('schema')
    else:
        meta = {}
        raw_routes = list(payload)
        algorithm = {}
        csv_sha256 = validation['csv_sha256']
        endpoint_mode = str(config.get('endpoint_mode', 'virtual_unfolded'))
        schema = None

    algorithm_path = input_dir / 'algorithm.json'
    if algorithm_path.exists():
        try:
            loaded = _read_json(algorithm_path)
            if isinstance(loaded, dict):
                algorithm = {**algorithm, **loaded}
                log(f'loaded algorithm metadata from {algorithm_path.name}')
        except Exception as exc:  # pragma: no cover - defensive
            log(f'WARNING could not read {algorithm_path.name} ({exc!r})')

    ablations = normalize_ablations(algorithm.get('ablations'))
    ablations_path = input_dir / 'ablations.json'
    if ablations_path.exists():
        try:
            ablations = normalize_ablations(_read_json(ablations_path))
            log(f'loaded {len(ablations)} ablation records from ablations.json')
        except Exception as exc:  # pragma: no cover - defensive
            log(f'WARNING could not read ablations.json ({exc!r})')
    if ablations:
        log(f'ablation table available with {len(ablations)} configurations')

    geometry_lookup = {}
    if geometry_path.exists() and routes_path.exists():
        try:
            for entry in _geometry_entries(_read_json(geometry_path)):
                geometry_lookup[int(entry['route_id'])] = entry
            log(f'loaded fallback geometry for {len(geometry_lookup)} routes from '
                'routes_geometry.json')
        except Exception as exc:  # pragma: no cover - defensive
            log(f'WARNING could not read routes_geometry.json ({exc!r})')
    failed_lookup = {}
    if failed_path.exists():
        try:
            for entry in _entries(_read_json(failed_path)):
                failed_lookup[int(entry['route_id'])] = entry
        except Exception as exc:  # pragma: no cover - defensive
            log(f'WARNING could not read failed_routes.json ({exc!r})')

    run_status = None
    run_status_source = 'default'
    if isinstance(payload, dict) and payload.get('run_status'):
        run_status = str(payload['run_status'])
        run_status_source = 'routes.json'
    if run_status is None and isinstance(algorithm, dict) and algorithm.get('run_status'):
        run_status = str(algorithm['run_status'])
        run_status_source = 'algorithm'
    if run_status is None:
        hint = ''
        if routes_source is not None:
            hint = routes_source.name.lower()
        checkpoint_hint = ('checkpoint' in hint
                           or bool(isinstance(algorithm, dict)
                                   and algorithm.get('checkpoint')))
        run_status = 'partial_checkpoint' if checkpoint_hint else 'complete'
        run_status_source = 'inferred_from_filename' if checkpoint_hint else 'default'
    if run_status_override is not None:
        run_status = str(run_status_override)
        run_status_source = 'cli_override'
    log(f'run_status={run_status} (source={run_status_source})')

    # Acceptance policy (SPEC change record v2): final deliverable uses the
    # 'exact' crossing policy, while 'legacy' (clearance/sin + outside re-check)
    # is the historical sensitivity comparison. The route payload states it;
    # older/legacy baselines without the field keep the historical policy.
    policy = None
    policy_source = 'default'
    if isinstance(payload, dict) and payload.get('crossing_policy'):
        policy = str(payload['crossing_policy'])
        policy_source = 'routes.json'
    if policy is None and isinstance(algorithm, dict) and algorithm.get('crossing_policy'):
        policy = str(algorithm['crossing_policy'])
        policy_source = 'algorithm'
    if policy is None and isinstance(config, dict) and config.get('crossing_policy'):
        policy = str(config['crossing_policy'])
        policy_source = 'config'
    if policy is None:
        policy = 'legacy'
    policy = policy.strip().lower()
    if policy not in ('exact', 'legacy'):
        policy = 'legacy'
    sensitivity_policy = 'legacy' if policy == 'exact' else 'exact'
    log(f'acceptance_policy={policy} (source={policy_source}); '
        f'sensitivity_policy={sensitivity_policy}')

    return dict(rows=rows, endpoints=endpoints, connectors=connectors,
                validation=validation, config=config, algorithm=algorithm,
                ablations=ablations, payload=payload, meta=meta, raw_routes=raw_routes,
                schema=schema, csv_sha256=csv_sha256, endpoint_mode=endpoint_mode,
                preserved=preserved, generated=generated,
                routes_source=routes_source,
                run_status=run_status, run_status_source=run_status_source,
                acceptance_policy=policy, acceptance_policy_source=policy_source,
                sensitivity_policy=sensitivity_policy,
                geometry_lookup=geometry_lookup, failed_lookup=failed_lookup,
                input_dir=input_dir, run_dir=run_dir)


# --------------------------------------------------------------------------- #
# route records
# --------------------------------------------------------------------------- #
def build_records(bundle, log):
    identities = {row['route_id']: row for row in bundle['rows']}
    raw_entries = {}
    for entry in bundle['raw_routes']:
        if not isinstance(entry, dict):
            continue
        try:
            route_id = int(entry.get('route_id', entry.get('id')))
        except (TypeError, ValueError):
            continue
        raw_entries[route_id] = entry
    geometry_lookup = bundle['geometry_lookup']
    failed_lookup = bundle['failed_lookup']
    records = {}
    missing_identity = []
    missing_geometry = []
    for route_id in sorted(identities):
        row = identities[route_id]
        entry = raw_entries.get(route_id) or {}
        status = _status_of(entry.get('status', entry.get('routed')))
        record = dict(route_id=route_id, status=status,
                      relation=str(entry.get('relation') or row['relation']),
                      pair=str(entry.get('pair') or row['pair']),
                      source_side=str(entry.get('source_side') or row['source_side']),
                      target_side=str(entry.get('target_side') or row['target_side']),
                      source_endpoint=str(entry.get('source_endpoint')
                                          or row['source_endpoint']),
                      target_endpoint=str(entry.get('target_endpoint')
                                          or row['target_endpoint']),
                      layer=0)
        if record['source_endpoint'] not in bundle['endpoints']:
            record['source_endpoint'] = row['source_endpoint']
        if record['target_endpoint'] not in bundle['endpoints']:
            record['target_endpoint'] = row['target_endpoint']
        if route_id not in raw_entries:
            missing_identity.append(route_id)
        if status == 'routed':
            primitives = entry.get('primitives')
            if not primitives:
                primitives = (geometry_lookup.get(route_id) or {}).get('primitives')
            if primitives:
                try:
                    record['primitives'] = normalize_primitives(primitives)
                    record['bend_count'] = sum(1 for primitive in record['primitives']
                                               if primitive['kind'] == 'arc')
                except (KeyError, TypeError, ValueError) as exc:
                    record['status'] = 'failed'
                    record['reason'] = 'invalid_primitives'
                    record['classification'] = 'invalid_geometry'
                    record['evaluated'] = 0
                    record['blockers'] = {}
                    record['geometry_errors'] = [f'invalid_primitives:{exc}']
                    missing_geometry.append(route_id)
            else:
                record['geometry_missing'] = True
                missing_geometry.append(route_id)
            if record['status'] == 'routed':
                input_length = entry.get('length_mm')
                if input_length is None:
                    input_length = (geometry_lookup.get(route_id) or {}).get('length_mm')
                if input_length is not None:
                    try:
                        record['input_length_mm'] = float(input_length)
                    except (TypeError, ValueError):
                        pass
                candidate = _candidate_metadata(entry)
                if candidate:
                    record['candidate'] = candidate
        else:
            failure = {}
            if isinstance(entry.get('failure'), dict):
                failure.update(entry['failure'])
            for key in ('reason', 'evaluated', 'blockers', 'scanned_tracks',
                        'rejection_counts', 'generation_rejections', 'classification'):
                if entry.get(key) is not None:
                    failure[key] = entry[key]
            fallback = failed_lookup.get(route_id, {})
            for key in ('reason', 'evaluated', 'blockers', 'scanned_tracks',
                        'rejection_counts', 'generation_rejections'):
                if failure.get(key) is None and fallback.get(key) is not None:
                    failure[key] = fallback[key]
            reason = failure.get('reason') or 'unknown_failure'
            record.update(reason=str(reason), evaluated=int(failure.get('evaluated') or 0),
                          blockers=_json_safe(failure.get('blockers') or {}),
                          classification=str(failure.get('classification')
                                             or classify_failure(reason)))
            for key in ('scanned_tracks', 'rejection_counts', 'generation_rejections'):
                if failure.get(key) is not None:
                    record[key] = _json_safe(failure[key])
            if record['classification'] == 'other':
                record['classification'] = classify_failure(reason)
        records[route_id] = record
    if missing_identity:
        log(f'WARNING {len(missing_identity)} route identities absent from routes.json; '
            f'classified as failed (first: {missing_identity[:5]})')
        for route_id in missing_identity:
            record = records[route_id]
            record.update(status='failed', reason='missing_from_routes_json',
                          classification='input_incomplete', evaluated=0, blockers={})
    routed_count = sum(1 for record in records.values() if record['status'] == 'routed')
    failed_count = len(records) - routed_count
    log(f'records: {routed_count} routed / {failed_count} failed / {len(records)} total')
    if missing_geometry:
        log(f'WARNING {len(missing_geometry)} routed records without usable primitives '
            f'(first: {missing_geometry[:5]}); they stay in routes.json but are excluded '
            'from geometry exports')
    return records


# --------------------------------------------------------------------------- #
# exact geometry recomputation and final pairwise audit
# --------------------------------------------------------------------------- #
def _find_short_s_partner(primitives, index):
    """True when a non-90-degree arc pairs with the opposite short-S arc.

    SPEC 1.3 allows ``sweep = +-theta`` short-S pairs (theta from the legacy
    ``acos(1 - d/(2R))`` formula) with an optional ~zero-length connecting line.
    Only informational: the independent validator owns the authoritative check.
    """
    sweep = abs(float(primitives[index]['sweep']))
    for direction in (-1, 1):
        j = index + direction
        short_line = True
        while 0 <= j < len(primitives):
            primitive = primitives[j]
            if primitive['kind'] == 'line':
                if math.dist(primitive['p0'], primitive['p1']) > 1e-6:
                    break
                j += direction
                continue
            other = abs(float(primitive['sweep']))
            if (short_line and abs(other - sweep) <= 1e-9
                    and primitive['sweep'] * primitives[index]['sweep'] < 0.0):
                return True
            break
    return False


def audit_geometry(records, endpoints, config, log):
    """Recompute lengths, poses, D56 structural checks and all pair conflicts."""
    started = time.perf_counter()
    width = float(config.get('width_mm', 0.05))
    gap = float(config.get('edge_gap_mm', 0.125))
    sagitta = float(config.get('sagitta_mm', 0.0005))
    min_radius = float(config.get('min_radius_mm', 5.0))
    index = ConflictIndex(width=width, gap=gap, sagitta=sagitta)
    routed_ids = [route_id for route_id in sorted(records)
                  if records[route_id]['status'] == 'routed'
                  and records[route_id].get('primitives')]
    log(f'exact geometry audit of {len(routed_ids)} routed records '
        f'(width={width} mm, clearance={width + gap} mm, sagitta={sagitta} mm)')
    crossings = []
    spacing_pairs, overlap_pairs, touch_pairs, zone_overlap_pairs = set(), set(), set(), set()
    minimum_clearance = None
    route_errors = {}
    error_counts = Counter()
    self_intersections = 0
    self_overlaps = 0
    radius_violations = 0
    boundary_violations = 0
    orthogonality_violations = 0
    sweep_violations = 0
    length_mismatches = []
    arc_radius_values = Counter()
    evaluated = 0
    for position, route_id in enumerate(routed_ids, start=1):
        record = records[route_id]
        primitives = record['primitives']
        local_errors = []
        try:
            exact_length = float(geometry_length(primitives))
            record['length_mm'] = exact_length
        except Exception as exc:  # pragma: no cover - defensive
            record['length_mm'] = float('nan')
            exact_length = float('nan')
            local_errors.append('length_calculation_failed:' + type(exc).__name__)
        record['bend_count'] = sum(1 for primitive in primitives
                                   if primitive['kind'] == 'arc')
        if record.get('input_length_mm') is not None and math.isfinite(exact_length):
            if abs(record['input_length_mm'] - exact_length) > 1e-6:
                length_mismatches.append(route_id)
        for primitive_index, primitive in enumerate(primitives):
            if primitive['kind'] == 'line':
                dx = abs(primitive['p1'][0] - primitive['p0'][0])
                dy = abs(primitive['p1'][1] - primitive['p0'][1])
                if dx > 1e-9 and dy > 1e-9:
                    orthogonality_violations += 1
                    local_errors.append(f'non_orthogonal_line:{primitive_index}')
            else:
                radius = float(primitive['radius'])
                arc_radius_values[round(radius, 6)] += 1
                if abs(radius - min_radius) > 1e-9:
                    radius_violations += 1
                    local_errors.append(f'radius_not_minimum:{primitive_index}')
        nonstandard = [i for i, primitive in enumerate(primitives)
                       if primitive['kind'] == 'arc'
                       and abs(abs(float(primitive['sweep'])) - math.pi / 2.0) > 1e-9]
        for i in nonstandard:
            if not _find_short_s_partner(primitives, i):
                sweep_violations += 1
                local_errors.append(f'non_standard_arc_sweep:{i}')
        source = endpoints.get(record['source_endpoint'])
        target = endpoints.get(record['target_endpoint'])
        try:
            if source is None or target is None:
                raise KeyError('endpoint identity not found')
            pose_errors = geometry_validate(
                primitives, source['routing_xy'], target['routing_xy'],
                source['inward'], -np.asarray(target['inward'], dtype=float),
                board=BOARD_MM, width=width, min_radius=min_radius)
        except Exception as exc:  # pragma: no cover - defensive
            pose_errors = ['validation_failed:' + type(exc).__name__]
        if pose_errors:
            local_errors.extend(pose_errors)
            self_intersections += sum(1 for error in pose_errors
                                      if error.startswith('self_intersection'))
            self_overlaps += sum(1 for error in pose_errors
                                 if error.startswith('self_overlap'))
            boundary_violations += sum(1 for error in pose_errors
                                       if error.startswith('board_out_of_bounds'))
            error_counts.update(error.split(':')[0] for error in pose_errors)
        try:
            result = index.evaluate(primitives, stop_on_invalid=False)
        except Exception as exc:  # pragma: no cover - defensive
            local_errors.append('conflict_evaluation_failed:' + type(exc).__name__)
            result = None
        if result is not None:
            evaluated += 1
            for crossing in result['crossings']:
                crossings.append(dict(
                    route_a=int(crossing['other']),
                    route_b=int(route_id),
                    x_mm=float(crossing['x']),
                    y_mm=float(crossing['y']),
                    angle_deg=float(crossing['angle_deg']),
                    local_exemption_half_length_mm=float(
                        crossing.get('local_exemption_half_length_mm') or 0.0)))
            for other in result['spacing_pairs']:
                spacing_pairs.add((min(int(other), route_id), max(int(other), route_id)))
            for other in result['overlap_pairs']:
                overlap_pairs.add((min(int(other), route_id), max(int(other), route_id)))
            for other in result['touch_pairs']:
                touch_pairs.add((min(int(other), route_id), max(int(other), route_id)))
            for other in result['crossing_zone_overlap_pairs']:
                zone_overlap_pairs.add((min(int(other), route_id),
                                        max(int(other), route_id)))
            value = result.get('minimum_non_crossing_centerline_mm')
            if value is not None:
                minimum_clearance = (float(value) if minimum_clearance is None
                                     else min(minimum_clearance, float(value)))
            try:
                index.add(route_id, primitives)
            except Exception as exc:  # pragma: no cover - defensive
                local_errors.append('index_add_failed:' + type(exc).__name__)
        if local_errors:
            route_errors[route_id] = local_errors
            record['geometry_errors'] = local_errors
        else:
            record.pop('geometry_errors', None)
        if position % 128 == 0:
            log(f'geometry audit progress: {position}/{len(routed_ids)} routes, '
                f'{len(crossings)} crossings, {time.perf_counter() - started:.2f}s')
    runtime = time.perf_counter() - started
    log(f'final exact audit: {evaluated} routed records checked, '
        f'{len(crossings)} recorded crossings, '
        f'{len(spacing_pairs)} non-crossing spacing violations, '
        f'{len(overlap_pairs)} overlaps, {len(touch_pairs)} touches, '
        f'{len(zone_overlap_pairs)} crossing-zone overlaps, '
        f'{len(route_errors)} records with geometry errors, {runtime:.2f}s')
    return dict(
        crossings=crossings,
        spacing_pairs=sorted(spacing_pairs),
        overlap_pairs=sorted(overlap_pairs),
        touch_pairs=sorted(touch_pairs),
        crossing_zone_overlap_pairs=sorted(zone_overlap_pairs),
        route_errors=route_errors,
        error_counts=dict(error_counts),
        self_intersections=int(self_intersections),
        self_overlaps=int(self_overlaps),
        radius_violations=int(radius_violations),
        boundary_violations=int(boundary_violations),
        orthogonality_violations=int(orthogonality_violations),
        d56_sweep_violations=int(sweep_violations),
        minimum_non_crossing_centerline_mm=minimum_clearance,
        length_mismatches=sorted(length_mismatches),
        arc_radius_values={str(key): int(value)
                           for key, value in sorted(arc_radius_values.items())},
        evaluated_routes=int(evaluated),
        runtime_seconds=runtime,
        method=('four_side_1024.geometry.validate (exact primitive geometry) + '
                'four_side_1024.conflicts.ConflictIndex (exact centerline '
                'intersections / local crossing exemption)'),
    )


# --------------------------------------------------------------------------- #
# exports
# --------------------------------------------------------------------------- #
def export_gds(routed, curves, config, path, log):
    import gdspy
    library = gdspy.GdsLibrary(name='D56_SINGLE_LAYER_1024', unit=1e-3, precision=1e-9)
    cell = library.new_cell('D56_SINGLE_LAYER')
    exported = 0
    for record in routed:
        points = curves.get(record['route_id'])
        if points is None or len(points) < 2:
            continue
        cell.add(gdspy.FlexPath(points, float(config.get('width_mm', 0.05)),
                                gdsii_path=True, layer=0, datatype=0, ends='flush'))
        exported += 1
    library.write_gds(str(path))
    reread = gdspy.GdsLibrary(infile=str(path))
    tops = reread.top_level()
    paths = list(tops[0].paths) if tops else []
    layers = sorted({int(layer) for path in paths for layer in path.layers})
    datatypes = sorted({int(datatype) for path in paths for datatype in path.datatypes})
    ok = (len(paths) == exported and layers == ([0] if exported else [])
          and datatypes in ([0], []))
    info = dict(file=str(path), bytes=path.stat().st_size,
                paths=len(paths), exported_routes=exported,
                layers=layers, datatypes=datatypes, unit_m=1e-3, precision_m=1e-9,
                arc_chord_sagitta_mm=float(config.get('sagitta_mm', 0.0005)),
                width_mm=float(config.get('width_mm', 0.05)),
                sha256=_sha256(path), gdspy_version=getattr(gdspy, '__version__', None),
                verified=bool(ok),
                status=('research virtual_unfolded single-layer geometry, '
                        'chordal arcs; not a fabrication release'))
    log(f'routing_all.gds: {info["paths"]} paths / layer {layers} / '
        f'{info["bytes"]} bytes / verified={ok}')
    if not ok:
        raise RuntimeError(f'GDS verification failed: {info}')
    return info


def export_routes_geometry(path, routed, config, csv_sha256, endpoint_mode):
    payload = dict(schema=SCHEMA_GEOMETRY, units='mm', layer=0,
                   endpoint_mode=endpoint_mode, csv_sha256=csv_sha256,
                   generated_at=_iso_now(), config=_json_safe(config),
                   routes=[dict(route_id=record['route_id'], pair=record['pair'],
                                relation=record['relation'],
                                source_endpoint=record['source_endpoint'],
                                target_endpoint=record['target_endpoint'],
                                layer=0, length_mm=record.get('length_mm'),
                                bend_count=record.get('bend_count'),
                                candidate=record.get('candidate'),
                                primitives=record['primitives'])
                           for record in routed])
    save_json(path, payload)
    return dict(file=str(path), bytes=Path(path).stat().st_size,
                routes=len(routed), sha256=_sha256(path))


def export_failed_routes(path, failed):
    records = []
    for record in sorted(failed, key=lambda item: item['route_id']):
        item = dict(route_id=record['route_id'], pair=record['pair'],
                    relation=record['relation'],
                    source_side=record['source_side'], target_side=record['target_side'],
                    source_endpoint=record['source_endpoint'],
                    target_endpoint=record['target_endpoint'], layer=0,
                    status='failed', reason=record.get('reason', 'unknown_failure'),
                    classification=record.get('classification', 'other'),
                    evaluated=int(record.get('evaluated', 0) or 0),
                    blockers=_json_safe(record.get('blockers') or {}))
        for key in ('scanned_tracks', 'rejection_counts', 'generation_rejections',
                    'geometry_errors'):
            if record.get(key) is not None:
                item[key] = _json_safe(record[key])
        records.append(item)
    save_json(path, records)
    return dict(file=str(path), bytes=Path(path).stat().st_size,
                routes=len(records), sha256=_sha256(path))


# --------------------------------------------------------------------------- #
# independent validator bridge
# --------------------------------------------------------------------------- #
def _audit_passed(result):
    if not isinstance(result, dict):
        return None
    for key in ('passed', 'ok', 'all_passed', 'valid'):
        value = result.get(key)
        if isinstance(value, bool):
            return value
    status = str(result.get('status', '')).strip().lower()
    if status in ('passed', 'pass', 'ok', 'success', 'valid', 'completed'):
        return True
    if status in ('failed', 'fail', 'error', 'invalid'):
        return False
    return None


def _compact_audit(audit, limit=400000):
    try:
        text = json.dumps(audit)
    except (TypeError, ValueError):
        return _json_safe(audit)
    if len(text) <= limit:
        return audit
    summary = {key: value for key, value in audit.items()
               if key not in ('details', 'result', 'raw', 'errors', 'violations',
                              'violation_list')}
    violations = audit.get('violations') or []
    summary['truncated'] = True
    summary['violation_count'] = len(violations)
    summary['violations_sample'] = violations[:20]
    summary['error_count'] = len(audit.get('errors') or [])
    summary['note'] = ('full report kept in the validator report file next to the '
                       'artifacts; only a sample is embedded in statistics.json')
    return summary


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f'cannot import {path}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_independent_validator(run_dir, log, policy='legacy', label='main'):
    """Call ``d56/validate_d56.py`` under one crossing policy and return its verdict.

    SPEC change record v2: the final deliverable is validated with the ``exact``
    crossing policy while ``legacy`` is kept as the historical sensitivity
    comparison. ``label='main'`` writes ``independent_audit.json``;
    ``label='sensitivity'`` writes ``independent_audit_sensitivity_<policy>.json``.
    """
    run_dir = Path(run_dir)
    started = time.perf_counter()
    validator_path = Path(__file__).resolve().parent / 'validate_d56.py'
    if label == 'main':
        audit_path = run_dir / 'independent_audit.json'
    else:
        audit_path = run_dir / f'independent_audit_sensitivity_{policy}.json'
    base = dict(validator_module=str(validator_path),
                validator_module_exists=validator_path.exists(),
                policy=policy, label=label, audit_file=str(audit_path), attempts=[],
                pending_note=('four_side_1024/d56/validate_d56.py is not available '
                              'yet; the inter-route spacing verdict is pending the '
                              'independent validator'))
    if not validator_path.exists():
        if audit_path.exists():
            try:
                result = _json_safe(_read_json(audit_path))
                log(f'validate_d56.py absent; loaded existing {audit_path.name}')
                return {**base, 'status': ('passed' if _audit_passed(result)
                                           else 'unknown'), 'passed': _audit_passed(result),
                        'source': f'existing {audit_path.name} (validator module absent)',
                        'result': result,
                        'runtime_seconds': time.perf_counter() - started}
            except Exception as exc:  # pragma: no cover - defensive
                log(f'WARNING could not read existing {audit_path.name} ({exc!r})')
        log(f'validate_d56.py absent: {label}/{policy} audit marked pending')
        return {**base, 'status': 'not_available', 'passed': None,
                'source': 'none', 'runtime_seconds': time.perf_counter() - started}

    result = None
    direct_call_used = False
    module = None
    for module_name in ('four_side_1024.d56.validate_d56',):
        try:
            module = importlib.import_module(module_name)
            base['attempts'].append(f'imported {module_name}')
            break
        except Exception as exc:  # pragma: no cover - validator may be mid-edit
            base['attempts'].append(f'import {module_name} failed: {exc!r}')
    if module is None:
        try:
            module = _load_module(f'_d56_validator_{int(time.time() * 1000)}',
                                  validator_path)
            base['attempts'].append('loaded validator by file path')
        except Exception as exc:  # pragma: no cover - validator API may evolve
            base['attempts'].append('file-path import failed: ' + repr(exc))
            log(f'independent validator import failed: {exc!r}')
    if module is not None:
        entry = None
        for candidate in ('build_report', 'validate_run', 'run_validation',
                          'audit_run', 'validate_outputs', 'validate', 'main'):
            function = getattr(module, candidate, None)
            if callable(function):
                entry = (candidate, function)
                break
        if entry is None:
            base['attempts'].append('validator module has no callable entry point')
        else:
            name, function = entry
            try:
                signature = inspect.signature(function)
                kwargs = {}
                for parameter in signature.parameters:
                    if parameter in ('run_dir', 'output_dir', 'output', 'directory',
                                     'root'):
                        kwargs[parameter] = run_dir
                    elif parameter == 'policy':
                        kwargs['policy'] = policy
                result = function(**kwargs) if kwargs else function()
            except SystemExit as exc:  # e.g. a CLI main() parsing our own argv
                base['attempts'].append(f'direct call {name}() raised SystemExit({exc.code})')
                result = None
            except TypeError:
                try:
                    result = function(run_dir)
                except Exception as exc:  # pragma: no cover - validator API
                    base['attempts'].append(f'direct call {name}() fallback failed: {exc!r}')
                    result = None
            except Exception as exc:  # pragma: no cover - validator may be mid-edit
                base['attempts'].append(f'direct call {name}() failed: {exc!r}')
                result = None
            if not isinstance(result, dict):
                if result is not None:
                    base['attempts'].append(f'{name}() returned {type(result).__name__}')
                result = None
            elif 'passed' in result:
                direct_call_used = True
                base['attempts'].append(f'direct call {name}() -> passed='
                                        f'{result.get("passed")}')

    if result is None:
        # The validator CLI is the durable interface; write its full report next
        # to the artefacts so the independent verdict is also a saved file.
        variants = (
            ['--run-dir', str(run_dir), '--policy', policy, '--output',
             str(audit_path)],
            ['--run-dir', str(run_dir), '--policy', policy],
            ['--run-dir', str(run_dir), '--output', str(audit_path)],
            ['--run-dir', str(run_dir)],
        )
        project_root = str(Path(__file__).resolve().parents[2])
        for extra in variants:
            command = [sys.executable, '-m', 'four_side_1024.d56.validate_d56'] + extra
            try:
                completed = subprocess.run(command, cwd=project_root,
                                           capture_output=True, text=True, timeout=1800)
            except Exception as exc:  # pragma: no cover - subprocess may be unavailable
                base['attempts'].append(f'subprocess {extra} failed: {exc!r}')
                continue
            base['attempts'].append(f'subprocess {extra} exit={completed.returncode}')
            if completed.returncode != 0:
                continue
            if audit_path.exists():
                try:
                    result = _json_safe(_read_json(audit_path))
                    break
                except Exception:  # pragma: no cover - defensive
                    result = None
            output = (completed.stdout or '').strip()
            if output:
                try:
                    result = _json_safe(json.loads(output))
                    break
                except ValueError:
                    result = None

    if result is None and audit_path.exists():
        # Last resort: a report left next to the artefacts by a previous call.
        routes_file = run_dir / 'routes.json'
        fresh = (not routes_file.exists()
                 or audit_path.stat().st_mtime >= routes_file.stat().st_mtime - 1.0)
        if fresh:
            try:
                result = _json_safe(_read_json(audit_path))
                base['attempts'].append(f'loaded {audit_path.name} next to artefacts')
            except Exception:  # pragma: no cover - defensive
                pass

    runtime = time.perf_counter() - started
    if result is None:
        log(f'independent validator could not be executed ({label}/{policy}); '
            f'attempts={base["attempts"]}')
        return {**base, 'pending_note': None, 'status': 'error', 'passed': None,
                'source': 'four_side_1024/d56/validate_d56.py (invocation failed)',
                'runtime_seconds': runtime}
    passed = _audit_passed(result)
    status = 'passed' if passed is True else ('failed' if passed is False else 'unknown')
    if direct_call_used:
        try:
            audit_path.write_text(json.dumps(result, indent=2, ensure_ascii=False),
                                  encoding='utf-8')
            base['attempts'].append(f'wrote full validator report to {audit_path.name}')
        except Exception as exc:  # pragma: no cover - defensive
            log(f'WARNING could not write {audit_path.name} ({exc!r})')
    log(f'independent validator [{label}/{policy}]: status={status} passed={passed} '
        f'({runtime:.2f}s)')
    return {**base, 'pending_note': None, 'status': status, 'passed': passed,
            'source': 'four_side_1024/d56/validate_d56.py',
            'report_file': str(audit_path) if audit_path.exists() else None,
            'result': _compact_audit(result), 'runtime_seconds': runtime}


# --------------------------------------------------------------------------- #
# statistics
# --------------------------------------------------------------------------- #
def _load_statistics_seed(input_dir):
    path = Path(input_dir) / 'statistics_seed.json'
    if not path.exists():
        return None
    try:
        return _json_safe(_read_json(path))
    except Exception:  # pragma: no cover - defensive
        return None


def _crossing_angle_histogram(crossings):
    angles = np.asarray([crossing['angle_deg'] for crossing in crossings], dtype=float)
    bins = [0, 1, 5, 10, 20, 30, 45, 60, 75, 90.000001]
    histogram = {}
    for low, high in zip(bins[:-1], bins[1:]):
        histogram[f'{low}-{min(high, 90):g}'] = int(
            np.sum((angles >= low) & (angles < high)))
    return histogram, angles


def _router_reported_statistics(bundle):
    payload = bundle.get('payload')
    if isinstance(payload, dict):
        reported = payload.get('statistics')
        if isinstance(reported, dict):
            return _json_safe(reported)
    return None


def build_statistics(bundle, records, audit, gds_info, svg_info, figures,
                     validator_result, started_at, log, validator_sensitivity=None):
    routed = [records[key] for key in sorted(records) if records[key]['status'] == 'routed']
    failed = [records[key] for key in sorted(records) if records[key]['status'] == 'failed']
    total = len(records)
    lengths = [record['length_mm'] for record in routed
               if record.get('length_mm') is not None
               and math.isfinite(float(record['length_mm']))]
    crossings = audit['crossings']
    angle_histogram, angles = _crossing_angle_histogram(crossings)
    small_angle_threshold = float(bundle['config'].get('crossing_small_angle_deg', 10.0))
    small_angle_count = int(np.sum(angles < small_angle_threshold)) if len(angles) else 0
    acceptance_policy = bundle.get('acceptance_policy', 'legacy')
    sensitivity_policy = bundle.get('sensitivity_policy',
                                    'exact' if acceptance_policy == 'legacy' else 'legacy')
    main_report = ((validator_result or {}).get('result')
                   if isinstance(validator_result, dict) else None)
    if not isinstance(main_report, dict):
        main_report = {}
    legacy_counts = dict(spacing=len(audit['spacing_pairs']),
                         overlap=len(audit['overlap_pairs']),
                         touch=len(audit['touch_pairs']),
                         zone=len(audit['crossing_zone_overlap_pairs']),
                         minimum=audit['minimum_non_crossing_centerline_mm'])

    def _policy_number(key, legacy_value):
        if acceptance_policy == 'legacy':
            return legacy_value
        value = main_report.get(key)
        return value if isinstance(value, (int, float)) else None

    spacing_violation_pairs = _policy_number('spacing_violation_pairs',
                                             legacy_counts['spacing'])
    overlap_pairs = _policy_number('overlap_pairs', legacy_counts['overlap'])
    if acceptance_policy == 'legacy':
        crossing_window_overlap_pairs = legacy_counts['zone']
    else:
        crossing_window_overlap_pairs = main_report.get(
            'crossing_window_overlap_pairs',
            main_report.get('crossing_zone_overlap_pairs'))
    minimum_clearance = _policy_number('min_non_crossing_centerline_mm',
                                       legacy_counts['minimum'])
    main_violation_count = main_report.get('violation_pair_count')
    if main_violation_count is None and acceptance_policy == 'exact':
        main_violation_count = main_report.get('spacing_violation_pairs')
    by_pair = {pair: dict(success=0, failed=0, total=0, success_rate=0.0)
               for pair in PAIR_ORDER}
    by_relation = {relation: dict(success=0, failed=0, total=0, success_rate=0.0)
                   for relation in RELATIONS}
    for record in records.values():
        pair = record['pair'] if record['pair'] in by_pair else None
        relation = record['relation'] if record['relation'] in by_relation else None
        for target in (by_pair.get(pair), by_relation.get(relation)):
            if target is None:
                continue
            target['total'] += 1
            if record['status'] == 'routed':
                target['success'] += 1
            else:
                target['failed'] += 1
    for target in list(by_pair.values()) + list(by_relation.values()):
        target['success_rate'] = (target['success'] / target['total']
                                  if target['total'] else 0.0)
    failure_reason_counts = Counter(record.get('reason', 'unknown_failure')
                                    for record in failed)
    failure_class_counts = Counter(record.get('classification', 'other')
                                   for record in failed)
    failed_by_pair = Counter(record['pair'] for record in failed)
    failed_evaluations = sum(int(record.get('evaluated', 0) or 0) for record in failed)
    algorithm = bundle['algorithm'] if isinstance(bundle['algorithm'], dict) else {}
    reported_evaluations = algorithm.get('candidate_evaluations')
    if reported_evaluations is None:
        reported_evaluations = algorithm.get('evaluations')
    candidate_evaluations = (int(reported_evaluations)
                             if reported_evaluations is not None else failed_evaluations)
    route_crossings = Counter()
    for crossing in crossings:
        route_crossings.update((crossing['route_a'], crossing['route_b']))
    densest = plots_d56.densest_crossing_cells(crossings, 5.0, 20)
    hashes = collect_artifact_hashes(bundle['run_dir'])
    routing_runtime = algorithm.get('total_runtime_seconds')
    if routing_runtime is None:
        routing_runtime = algorithm.get('runtime_seconds')
    artifact_seconds = time.perf_counter() - started_at
    geometries = [record for record in routed if record.get('primitives')]
    routed_without_geometry = len(routed) - len(geometries)
    statistics = dict(
        schema=SCHEMA_STATISTICS,
        generated_at=_iso_now(),
        tool='four_side_1024.d56.outputs_d56',
        algorithm=algorithm,
        router_reported_statistics=_router_reported_statistics(bundle),
        router_reported_note=('statistics block embedded by the routing engine in '
                              'routes.json["statistics"]; kept only for cross-check, '
                              'every metric below is recomputed from primitives'),
        statistics_seed=_load_statistics_seed(bundle['input_dir']),
        statistics_seed_note=('statistics_seed.json written by the routing author is '
                              'embedded verbatim for traceability; computed fields '
                              'below are authoritative'),
        config=_json_safe(bundle['config']),
        total_connections=total,
        success_count=len(routed),
        failed_count=len(failed),
        success_rate=(len(routed) / total if total else 0.0),
        board_mm=[BOARD_MM, BOARD_MM],
        layer=0,
        routing_layers=1,
        endpoint_mode=bundle['endpoint_mode'],
        min_radius_mm=float(bundle['config'].get('min_radius_mm', 5.0)),
        width_mm=float(bundle['config'].get('width_mm', 0.05)),
        edge_gap_mm=float(bundle['config'].get('edge_gap_mm', 0.125)),
        min_centerline_clearance_mm=float(bundle['config'].get('width_mm', 0.05))
        + float(bundle['config'].get('edge_gap_mm', 0.125)),
        sagitta_mm=float(bundle['config'].get('sagitta_mm', 0.0005)),
        mean_length_mm=(float(np.mean(lengths)) if lengths else 0.0),
        max_length_mm=(float(max(lengths)) if lengths else 0.0),
        total_length_mm=float(sum(lengths)),
        min_length_mm=(float(min(lengths)) if lengths else 0.0),
        mean_bend_count=(float(np.mean([record.get('bend_count', 0)
                                        for record in geometries]))
                         if geometries else 0.0),
        max_bend_count=(int(max((record.get('bend_count', 0)
                                 for record in geometries), default=0))),
        acceptance_policy=acceptance_policy,
        acceptance_policy_source=bundle.get('acceptance_policy_source', 'default'),
        sensitivity_policy=sensitivity_policy,
        crossing_count=len(crossings),
        crossing_angle_histogram=angle_histogram,
        small_angle_threshold_deg=small_angle_threshold,
        small_angle_crossing_count=small_angle_count,
        spacing_violation_pairs=spacing_violation_pairs,
        spacing_violation_pairs_legacy=legacy_counts['spacing'],
        spacing_violation_pairs_source=('validator' if acceptance_policy != 'legacy'
                                        and spacing_violation_pairs is not None
                                        else 'conflicts_legacy_recompute'),
        overlap_pairs=overlap_pairs,
        overlap_pairs_legacy=legacy_counts['overlap'],
        touch_pairs=legacy_counts['touch'],
        crossing_window_overlap_pairs=crossing_window_overlap_pairs,
        crossing_zone_overlap_pairs=legacy_counts['zone'],
        violation_pair_count=main_violation_count,
        self_intersections=int(audit['self_intersections']),
        self_overlaps=int(audit['self_overlaps']),
        radius_violations=int(audit['radius_violations']),
        boundary_violations=int(audit['boundary_violations']),
        orthogonality_violations=int(audit['orthogonality_violations']),
        d56_sweep_violations=int(audit['d56_sweep_violations']),
        minimum_checked_non_crossing_centerline_mm=minimum_clearance,
        minimum_checked_non_crossing_centerline_legacy_mm=legacy_counts['minimum'],
        crossing_count_validator_main=main_report.get('crossing_count'),
        arc_radius_values=audit['arc_radius_values'],
        routes_with_geometry_errors=len(audit['route_errors']),
        geometry_error_counts=audit['error_counts'],
        geometry_error_examples=[dict(route_id=route_id, errors=errors[:6])
                                 for route_id, errors in
                                 sorted(audit['route_errors'].items())[:50]],
        routed_without_geometry=routed_without_geometry,
        length_mismatch_routes=audit['length_mismatches'][:50],
        length_mismatch_count=len(audit['length_mismatches']),
        by_pair=by_pair,
        by_relation=by_relation,
        failure_reason_counts=dict(failure_reason_counts),
        failure_class_counts=dict(failure_class_counts),
        failed_by_pair=dict(failed_by_pair),
        candidate_evaluations=candidate_evaluations,
        candidate_evaluation_breakdown=dict(
            failed_route_evaluations=failed_evaluations,
            algorithm_reported=(int(reported_evaluations)
                                if reported_evaluations is not None else None),
            successful_candidate_index_sum=None,
            note=('candidate_evaluations is taken from the router metadata when '
                  'provided, otherwise it is the sum of the evaluated counts '
                  'recorded for failed routes')),
        evaluated_routes=audit['evaluated_routes'],
        densest_crossing_cells=densest,
        most_crossed_routes=[dict(route_id=route_id, crossings=count)
                             for route_id, count in route_crossings.most_common(20)],
        crossing_pairs_unique=len({(crossing['route_a'], crossing['route_b'])
                                   for crossing in crossings}),
        total_runtime_seconds=(float(routing_runtime)
                               if routing_runtime is not None else artifact_seconds),
        routing_runtime_seconds=(float(routing_runtime)
                                 if routing_runtime is not None else None),
        artifact_generation_seconds=float(artifact_seconds),
        runtime_scope=('total_runtime_seconds uses the router-reported runtime when '
                       'available; artifact_generation_seconds is this export pass'),
        failure_reason_scope='one reason per failed route as recorded by the router',
        run_status=bundle.get('run_status', 'unknown'),
        run_status_source=bundle.get('run_status_source', 'default'),
        ablations=bundle['ablations'],
        ablation_count=len(bundle['ablations']),
        independent_audit=validator_result,
        independent_audit_passed=validator_result.get('passed'),
        independent_audit_status=validator_result.get('status'),
        independent_audit_sensitivity=validator_sensitivity,
        independent_audit_sensitivity_status=(
            validator_sensitivity.get('status')
            if isinstance(validator_sensitivity, dict) else None),
        independent_audit_sensitivity_passed=(
            validator_sensitivity.get('passed')
            if isinstance(validator_sensitivity, dict) else None),
        figures=figures,
        gds=gds_info,
        svg=svg_info,
        artifacts=hashes,
        input=dict(run_dir=str(bundle['run_dir']), input_dir=str(bundle['input_dir']),
                   routes_json_preserved=bool(bundle['preserved']),
                   routes_json_generated=bool(bundle['generated']),
                   routes_json_action=bundle.get('routes_json_action'),
                   routes_source=(str(bundle['routes_source'])
                                  if bundle.get('routes_source') is not None else None),
                   routes_json_schema=bundle['schema'],
                   routes_json_sha256=(_sha256(bundle['run_dir'] / 'routes.json')
                                       if (bundle['run_dir'] / 'routes.json').exists()
                                       else None),
                   csv_sha256=bundle['csv_sha256']),
        audit=dict(source='recomputed from analytic primitives',
                   method=audit['method'],
                   runtime_seconds=audit['runtime_seconds'],
                   acceptance_policy=acceptance_policy,
                   sensitivity_policy=sensitivity_policy,
                   spacing_violation_pairs_legacy=legacy_counts['spacing'],
                   overlap_pairs_legacy=legacy_counts['overlap'],
                   note=('lengths and crossings are recomputed here; the main '
                         'inter-route spacing verdict is the independent validator '
                         'under the deliverable crossing policy, with the other '
                         'policy kept as the historical sensitivity comparison')),
        software=dict(python=sys.version, numpy=np.__version__,
                      platform=platform.platform(),
                      matplotlib=_safe_version('matplotlib'),
                      gdspy=_safe_version('gdspy')),
        notes=[
            'virtual_unfolded endpoints: idealized planar adapter, not a '
            'manufactured two-row fanout.',
            'All primitives are layer=0; crossings are recorded 2D centerline '
            'crossings and are not certified optical crossings.',
            'Research geometry with provisional 5 mm / 0.05 mm / 0.125 mm '
            'parameters; not a fabrication release.',
            'Acceptance uses the crossing policy declared by the route payload '
            '(exact is the deliverable policy per SPEC change record v2); the '
            'other policy is embedded as the historical sensitivity comparison.',
        ],
    )
    log(f'statistics: success={len(routed)}/{total} failed={len(failed)} '
        f'crossings={len(crossings)} small-angle<{small_angle_threshold:g} deg='
        f'{small_angle_count} mean_length={statistics["mean_length_mm"]:.6f} mm')
    return statistics


def collect_artifact_hashes(run_dir):
    hashes = {}
    for name in REQUIRED_FILES:
        if name in ('statistics.json', 'run.log'):
            continue
        path = Path(run_dir) / name
        if path.exists():
            hashes[name] = dict(bytes=path.stat().st_size, sha256=_sha256(path))
    return hashes


def _safe_version(module_name):
    try:
        module = __import__(module_name)
        return getattr(module, '__version__', None)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# main pipeline
# --------------------------------------------------------------------------- #
def audit_only(run_dir, input_dir=None, routes_override=None, report_path=None,
               run_status_override=None, replace_routes=False):
    """Preflight: recompute + independently validate without exporting artifacts.

    Used before the final in-place export so a failing acceptance audit never
    overwrites the deliverable files. Appends to ``run.log`` and saves
    ``independent_audit.json``; writes no PNG/SVG/GDS/statistics.
    """
    started_at = time.perf_counter()
    run_dir = Path(run_dir).resolve()
    input_dir = Path(input_dir).resolve() if input_dir is not None else run_dir
    routes_override = (Path(routes_override).resolve()
                       if routes_override is not None else None)
    run_dir.mkdir(parents=True, exist_ok=True)
    log = RunLog(run_dir / 'run.log')
    log('=' * 72)
    log(f'D56 audit-only preflight start | run_dir={run_dir} | '
        f'input_dir={input_dir}'
        + (f' | routes_override={routes_override}' if routes_override else ''))
    bundle = load_bundle(input_dir, run_dir, log, routes_override,
                         run_status_override)
    records = build_records(bundle, log)
    # The validator reads <run-dir>/routes.json; make sure it exists for a
    # preview directory before validating (never mix two different payloads).
    target_routes_path = run_dir / 'routes.json'
    source_routes_path = bundle.get('routes_source')
    if source_routes_path is not None:
        source_routes_path = Path(source_routes_path)
        if source_routes_path.resolve() != target_routes_path.resolve():
            if not target_routes_path.exists():
                shutil.copyfile(source_routes_path, target_routes_path)
                log(f'routes.json copied unchanged from {source_routes_path.name} '
                    'for preflight validation')
            elif target_routes_path.read_bytes() != source_routes_path.read_bytes():
                if replace_routes:
                    shutil.copyfile(source_routes_path, target_routes_path)
                    log('WARNING --replace-routes: preflight dir routes.json replaced')
                else:
                    raise SystemExit(
                        f'{target_routes_path} differs from the --routes source; '
                        'pass --replace-routes or use a fresh --run-dir.')
    else:
        save_json(target_routes_path, bundle['payload'])
        log('generated routes.json written for preflight validation')
    audit = audit_geometry(records, bundle['endpoints'], bundle['config'], log)
    policy = bundle.get('acceptance_policy', 'legacy')
    validator = run_independent_validator(run_dir, log, policy=policy, label='main')
    report = dict(
        mode='audit_only', run_dir=str(run_dir), input_dir=str(input_dir),
        routes_source=(str(bundle['routes_source'])
                       if bundle.get('routes_source') is not None else None),
        acceptance_policy=policy,
        acceptance_policy_source=bundle.get('acceptance_policy_source'),
        sensitivity_policy=bundle.get('sensitivity_policy'),
        total_connections=len(records),
        success_count=sum(1 for record in records.values()
                          if record['status'] == 'routed'),
        failed_count=sum(1 for record in records.values()
                         if record['status'] == 'failed'),
        crossing_count=len(audit['crossings']),
        spacing_violation_pairs_legacy=len(audit['spacing_pairs']),
        overlap_pairs_legacy=len(audit['overlap_pairs']),
        self_intersections=int(audit['self_intersections']),
        radius_violations=int(audit['radius_violations']),
        boundary_violations=int(audit['boundary_violations']),
        independent_audit_status=validator.get('status'),
        independent_audit_passed=validator.get('passed'),
        violation_count=len((validator.get('result') or {}).get('violations') or []),
        violations=((validator.get('result') or {}).get('violations') or [])[:100],
        elapsed_seconds=time.perf_counter() - started_at,
    )
    if report_path is not None:
        report_path = Path(report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        save_json(report_path, report)
        log(f'audit-only report written: {report_path}')
    log(f'D56 audit-only preflight done | success={report["success_count"]}/'
        f'{report["total_connections"]} | policy={policy} | '
        f'validator={validator.get("status")} | '
        f'{report["elapsed_seconds"]:.2f}s')
    print(json.dumps({key: report[key] for key in
                      ('run_dir', 'success_count', 'total_connections',
                       'acceptance_policy', 'crossing_count',
                       'spacing_violation_pairs_legacy',
                       'independent_audit_status', 'independent_audit_passed',
                       'violation_count', 'elapsed_seconds')},
                     ensure_ascii=False, indent=2))
    return 0 if validator.get('passed') is True else 1


def run(run_dir, input_dir=None, svg_sagitta_mm=0.01, routes_override=None,
        replace_routes=False, run_status_override=None, log_echo=True):
    started_at = time.perf_counter()
    run_dir = Path(run_dir).resolve()
    input_dir = Path(input_dir).resolve() if input_dir is not None else run_dir
    routes_override = Path(routes_override).resolve() if routes_override is not None else None
    run_dir.mkdir(parents=True, exist_ok=True)
    log = RunLog(run_dir / 'run.log')
    log('=' * 72)
    log(f'D56 artifact pipeline start | python={sys.version.split()[0]} | '
        f'run_dir={run_dir} | input_dir={input_dir}'
        + (f' | routes_override={routes_override}' if routes_override else ''))
    if not input_dir.exists():
        raise SystemExit(f'input directory does not exist: {input_dir}')
    bundle = load_bundle(input_dir, run_dir, log, routes_override,
                         run_status_override)
    records = build_records(bundle, log)

    # Preserve the authoritative routes.json byte-for-byte. A --routes override
    # may point at a checkpoint; it is only copied when the run dir has no
    # routes.json yet, and a different existing routes.json is never mixed with it.
    target_routes_path = run_dir / 'routes.json'
    source_routes_path = bundle.get('routes_source')
    if source_routes_path is not None:
        source_routes_path = Path(source_routes_path)
        if source_routes_path.resolve() == target_routes_path.resolve():
            bundle['routes_json_action'] = 'preserved_in_place'
            log(f'routes.json preserved in place '
                f'({target_routes_path.stat().st_size} bytes)')
        elif target_routes_path.exists():
            if target_routes_path.read_bytes() == source_routes_path.read_bytes():
                bundle['routes_json_action'] = 'preserved_identical'
                log(f'routes.json already matches --routes source; preserved '
                    f'({target_routes_path.stat().st_size} bytes)')
            elif replace_routes:
                shutil.copyfile(source_routes_path, target_routes_path)
                bundle['routes_json_action'] = 'replaced_from_source'
                log(f'WARNING --replace-routes: overwrote run-dir routes.json with '
                    f'{source_routes_path.name} ({target_routes_path.stat().st_size} '
                    'bytes)')
            else:
                raise SystemExit(
                    f'{target_routes_path} already exists and differs from the '
                    f'--routes source {source_routes_path}; refusing to mix two '
                    'route payloads. Use a fresh --run-dir, remove the file, or '
                    'pass --replace-routes for a checkpoint preview.')
        else:
            shutil.copyfile(source_routes_path, target_routes_path)
            bundle['routes_json_action'] = 'copied_from_source'
            log(f'routes.json copied unchanged from {source_routes_path.name} '
                f'({target_routes_path.stat().st_size} bytes)')
    else:
        payload = bundle['payload']
        save_json(target_routes_path, payload)
        bundle['routes_json_action'] = 'generated'
        log(f'generated routes.json written ({target_routes_path.stat().st_size} bytes)')

    audit = audit_geometry(records, bundle['endpoints'], bundle['config'], log)

    routed = [records[key] for key in sorted(records) if records[key]['status'] == 'routed']
    failed = [records[key] for key in sorted(records) if records[key]['status'] == 'failed']
    exportable = [record for record in routed if record.get('primitives')]

    geometry_info = export_routes_geometry(run_dir / 'routes_geometry.json', exportable,
                                           bundle['config'], bundle['csv_sha256'],
                                           bundle['endpoint_mode'])
    log(f'routes_geometry.json: {geometry_info["routes"]} analytic routes '
        f'({geometry_info["bytes"]} bytes)')
    failed_path = run_dir / 'failed_routes.json'
    author_failed = (failed_path.exists()
                     and run_dir.resolve() == input_dir.resolve())
    if author_failed:
        # The routing author may provide an authoritative failed-route list in
        # the run directory; never overwrite it (only report consistency).
        failed_info = dict(file=str(failed_path), bytes=failed_path.stat().st_size,
                           routes=len(failed), sha256=_sha256(failed_path),
                           source='preserved_author_provided')
        log(f'failed_routes.json preserved in place ({failed_info["bytes"]} bytes, '
            f'{len(failed)} failed records recomputed)')
    else:
        failed_info = export_failed_routes(failed_path, failed)
        log(f'failed_routes.json: {failed_info["routes"]} failed route records')

    sagitta = float(bundle['config'].get('sagitta_mm', 0.0005))
    curves = plots_d56.sample_curves(exportable, sagitta)
    figures = {}
    figures['01_connectivity.png'] = plots_d56.plot_connectivity(
        bundle['rows'], bundle['endpoints'], bundle['connectors'],
        run_dir / '01_connectivity.png')
    log(f'01_connectivity.png: {bundle["rows"].__len__()} original connections')

    routed_meta = {record['route_id']: record for record in routed}
    opposite_ids = [record['route_id'] for record in routed
                    if record['relation'] == 'opposite']
    adjacent_ids = [record['route_id'] for record in routed
                    if record['relation'] == 'adjacent']
    opposite_total = sum(1 for record in records.values()
                         if record['relation'] == 'opposite')
    adjacent_total = sum(1 for record in records.values()
                         if record['relation'] == 'adjacent')
    figures['02_routing_all.png'] = plots_d56.plot_routes(
        curves, routed_meta, list(curves), bundle['connectors'],
        run_dir / '02_routing_all.png',
        f'D56 single-layer routing: {len(exportable)}/{len(records)} connections routed',
        f'orthogonal lines + R = 5 mm arcs | all routed relations | layer = 0 | '
        f'virtual_unfolded | {len(audit["crossings"])} recorded crossings')
    log(f'02_routing_all.png: {len(exportable)} routed routes')
    figures['03_opposite_routes.png'] = plots_d56.plot_routes(
        curves, routed_meta, opposite_ids, bundle['connectors'],
        run_dir / '03_opposite_routes.png',
        f'Opposite-side routes (NS, EW): {len(opposite_ids)}/{opposite_total} routed',
        'relation = opposite | pair colours NS/EW | layer = 0 single plane')
    log(f'03_opposite_routes.png: {len(opposite_ids)}/{opposite_total} opposite routes')
    figures['04_adjacent_routes.png'] = plots_d56.plot_routes(
        curves, routed_meta, adjacent_ids, bundle['connectors'],
        run_dir / '04_adjacent_routes.png',
        f'Adjacent-side routes (EN, ES, SW, NW): {len(adjacent_ids)}/{adjacent_total} '
        f'routed', 'relation = adjacent | pair colours EN/ES/SW/NW | layer = 0 '
        'single plane')
    log(f'04_adjacent_routes.png: {len(adjacent_ids)}/{adjacent_total} adjacent routes')

    figures['05_crossing_heatmap.png'] = plots_d56.plot_heatmap(
        audit['crossings'], len(exportable), len(records),
        run_dir / '05_crossing_heatmap.png')
    log('05_crossing_heatmap.png: '
        f'{len(figures["05_crossing_heatmap.png"]["densest_cells"])} densest cells '
        'annotated')

    densest = plots_d56.densest_crossing_cells(audit['crossings'], 5.0, 24)
    figures['06_routing_detail.png'] = plots_d56.plot_detail(
        curves, routed_meta, audit['crossings'], run_dir / '06_routing_detail.png',
        len(exportable), len(records), densest)
    log(f'06_routing_detail.png: {figures["06_routing_detail.png"]["hotspots"]} '
        'hotspot windows')

    svg_info = plots_d56.write_svg(exportable, run_dir / 'routing_all.svg',
                                   sagitta_mm=float(svg_sagitta_mm))
    log(f'routing_all.svg: {svg_info["routes"]} routes, {svg_info["bytes"]} bytes, '
        f'sagitta={svg_info["sagitta_mm"]:g} mm')

    gds_info = export_gds(exportable, curves, bundle['config'],
                          run_dir / 'routing_all.gds', log)

    # Main acceptance audit under the deliverable's crossing policy, plus the
    # other policy as the historical sensitivity comparison (SPEC change v2).
    main_policy = bundle.get('acceptance_policy', 'legacy')
    sensitivity_policy = bundle.get('sensitivity_policy',
                                    'exact' if main_policy == 'legacy' else 'legacy')
    validator_result = run_independent_validator(run_dir, log, policy=main_policy,
                                                 label='main')
    validator_sensitivity = run_independent_validator(run_dir, log,
                                                      policy=sensitivity_policy,
                                                      label='sensitivity')

    # Build the statistics body first: 07 needs the per-pair / per-relation
    # numbers and the figure is itself listed in the statistics payload.
    statistics = build_statistics(bundle, records, audit, gds_info, svg_info,
                                  figures, validator_result, started_at, log,
                                  validator_sensitivity=validator_sensitivity)
    figures['07_strategy_comparison.png'] = plots_d56.plot_strategy(
        bundle['ablations'], statistics, run_dir / '07_strategy_comparison.png')
    log(f'07_strategy_comparison.png: mode={figures["07_strategy_comparison.png"]["mode"]}')
    statistics['figures'] = figures
    statistics['artifacts'] = collect_artifact_hashes(run_dir)
    save_json(run_dir / 'statistics.json', statistics)
    log(f'statistics.json written '
        f'({run_dir.joinpath("statistics.json").stat().st_size} bytes)')

    # Re-read the independent audit file if the validator produced one after our
    # in-process result; keep statistics.json consistent in either case.
    audit_path = run_dir / 'independent_audit.json'
    if audit_path.exists():
        try:
            file_result = _json_safe(_read_json(audit_path))
            if validator_result.get('status') in ('not_available', 'error'):
                passed = _audit_passed(file_result)
                statistics['independent_audit'] = dict(
                    status=('passed' if passed is True else
                            ('failed' if passed is False else 'unknown')),
                    passed=passed, source='independent_audit.json',
                    result=_compact_audit(file_result))
                statistics['independent_audit_passed'] = passed
                statistics['independent_audit_status'] = statistics[
                    'independent_audit']['status']
                save_json(run_dir / 'statistics.json', statistics)
                log('statistics.json updated with independent_audit.json')
        except Exception as exc:  # pragma: no cover - defensive
            log(f'WARNING could not merge independent_audit.json ({exc!r})')

    missing = [name for name in REQUIRED_FILES if not (run_dir / name).exists()]
    elapsed = time.perf_counter() - started_at
    if missing:
        log(f'ERROR missing required artifacts: {missing}')
        raise RuntimeError(f'missing required artifacts: {missing}')
    for name in REQUIRED_FILES:
        path = run_dir / name
        log(f'artifact ok: {name} ({path.stat().st_size} bytes)')
    log(f'D56 artifact pipeline done | success={len(routed)}/{len(records)} | '
        f'crossings={len(audit["crossings"])} | run_status={bundle.get("run_status")} '
        f'| independent_audit={statistics["independent_audit_status"]} | {elapsed:.2f}s')
    return dict(run_dir=str(run_dir), input_dir=str(input_dir),
                success_count=len(routed), failed_count=len(failed),
                total_connections=len(records),
                crossing_count=len(audit['crossings']),
                run_status=bundle.get('run_status'),
                independent_audit_status=statistics['independent_audit_status'],
                elapsed_seconds=elapsed,
                statistics=statistics)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='D56 optimized-run artifact pipeline (SPEC section 3).')
    parser.add_argument('--run-dir', type=Path, required=True,
                        help='output directory for the 13 required artifacts '
                             '(default input dir; routes.json is read from here)')
    parser.add_argument('--input-dir', type=Path, default=None,
                        help='directory with routes.json / routes_geometry.json / '
                             'failed_routes.json (default: --run-dir)')
    parser.add_argument('--routes', type=Path, default=None,
                        help='explicit route payload file, e.g. a checkpoint '
                             '(routes_checkpoint.json); overrides '
                             '<input-dir>/routes.json')
    parser.add_argument('--replace-routes', action='store_true',
                        help='preview only: allow overwriting an existing '
                             'run-dir routes.json with the --routes file')
    parser.add_argument('--run-status', default=None,
                        choices=('complete', 'partial_checkpoint'),
                        help='override statistics.run_status (default: read from '
                             'routes.json/algorithm, else infer from file name)')
    parser.add_argument('--audit-only', action='store_true',
                        help='preflight mode: recompute + validate but write no '
                             'artifact (except run.log/independent_audit.json)')
    parser.add_argument('--audit-report', type=Path, default=None,
                        help='with --audit-only: write the summary JSON report here')
    parser.add_argument('--svg-sagitta-mm', type=float, default=0.01,
                        help='chordal sagitta for the SVG polylines (default 0.01)')
    args = parser.parse_args(argv)
    if args.audit_only:
        return audit_only(args.run_dir, args.input_dir, args.routes,
                          args.audit_report, args.run_status,
                          replace_routes=args.replace_routes)
    result = run(args.run_dir, args.input_dir, args.svg_sagitta_mm,
                 routes_override=args.routes,
                 replace_routes=args.replace_routes,
                 run_status_override=args.run_status)
    summary = {key: result[key] for key in
               ('run_dir', 'input_dir', 'success_count', 'failed_count',
                'total_connections', 'crossing_count', 'run_status',
                'independent_audit_status', 'elapsed_seconds')}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
