"""T4 / task 9: independent final acceptance of the V2 optimisation round.

This is the *acceptance* module of ``outputs/four_side_1024_v2_candidate_rr_v01``.
It never routes, never edits geometry and never trusts the optimisation code: the
only authority is the frozen ``four_side_1024.fslw.validate_fslw`` strict audit of
the written ``routes.json`` files, exactly the same validator the historical
round-2 deliverable was accepted with.

For every experiment label under ``planes/V2/<LABEL>/{z1,z2}/`` it

1. runs ``validate_fslw.build_report(policy='strict', expected_route_count=512)``
   (independent of the V2 search/candidate modules) and writes
   ``audit_strict.json`` in the ``fslw.scan_and_audit`` file schema
   (``_compact_audit`` + ``routes_sha256`` + ``wall_seconds``); a plane must have
   no audit error, ``violations == 0`` and ``d56_failed == 0``;
2. re-checks the connection identity of all 512 records of the plane against the
   frozen V2 CSV (``fslw.ports.load_plane``) - ``route_id`` / ``source_endpoint``
   / ``target_endpoint`` / ``pair`` / ``relation`` (+ sides/rows), route order,
   CSV sha256 and port usage;
3. generates ``statistics.json`` with ``fslw.metrics.build_plane_statistics``
   *after* the audit file exists (so the authoritative audit is merged);
4. for a label that only changed one plane (e.g. the E1/E2/E3 experiments only
   write z2, Z1OPT only writes z1) copies the missing plane's geometry from the
   frozen BASE plane via ``v2opt.core.LayoutState.from_history`` +
   ``write_plane`` (identity and primitives unchanged) so that the combined
   artefact can be built - BASE itself is never rebuilt, only gap-filled;
5. for every label whose two planes exist, builds the 1024-channel combined
   artefact with ``fslw.combine.build_combined(root, 'V2', LABEL)`` and verifies
   ``routes_1024.json`` (1024 identities, routed == z1 + z2), the combined
   statistics (same-plane violations == 0), the two-height GDS (layer 0 = z1,
   layer 1 = z2) and the figures;
6. writes ``final_validation.json`` with the per-plane verdicts, the per-combined
   verdicts, all audit-file sha256 values and a round label ranking.

Usage (from ``OpticalWaveguideRouter2D``)::

    .venv\\Scripts\\python.exe -m four_side_1024.v2opt.finalize \\
        --root outputs/four_side_1024_v2_candidate_rr_v01

    # explicit subset / order
    ... --labels BASE,E1,E2,E3,Z1OPT,BEST --skip-combine

The module is idempotent: existing fresh BASE audit/statistics/combined artefacts
are read, never rewritten (they are recorded in ``baseline_acceptance.json``);
only missing artefacts are gap-filled.  Non-BASE labels are rebuilt from their
current ``routes.json`` (use ``--force`` to rebuild fresh derived artefacts too).

Exit code: 0 only when every processed plane and every built combined layout
passes every acceptance gate.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import platform
import sys
import time
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from four_side_1024.fslw import combine as fslw_combine  # noqa: E402
from four_side_1024.fslw import config as fslw_config  # noqa: E402
from four_side_1024.fslw import metrics as fslw_metrics  # noqa: E402
from four_side_1024.fslw import ports as fslw_ports  # noqa: E402
from four_side_1024.fslw import validate_fslw  # noqa: E402

# ---------------------------------------------------------------------------
# frozen acceptance configuration
# ---------------------------------------------------------------------------
TOPOLOGY = 'V2'
PLANES = ('z1', 'z2')
LABEL_ORDER = ('BASE', 'E1', 'E2', 'E3', 'Z1OPT', 'BEST')
ROUTES_PER_PLANE = 512
CONNECTIONS_TOTAL = 1024
V2_CSV_SHA256 = (
    '49dd9e89c4ea506d04638ae34eb06a0d8163d479de80869804c881ee1c43915e')
DEFAULT_ROOT = PROJECT_ROOT / 'outputs' / 'four_side_1024_v2_candidate_rr_v01'

#: connection-identity fields compared against the frozen V2 CSV pairing
IDENTITY_FIELDS = ('route_id', 'source_endpoint', 'target_endpoint', 'pair',
                   'relation', 'source_side', 'target_side', 'source_row',
                   'target_row')
#: counters that must be exactly zero on every accepted plane
VIOLATION_FIELDS = ('spacing_violation_pairs', 'overlap_pairs', 'touch_pairs',
                    'crossing_window_overlap_pairs', 'double_cross_pairs',
                    'crossing_window_excessive_pairs', 'self_intersections',
                    'self_overlaps', 'self_spacing_violations',
                    'radius_violations', 'boundary_violations',
                    'diagonal_line_violations',
                    'free_or_short_s_arc_violations', 'violation_pair_count')
#: audit-file fields that a cached ``audit_strict.json`` must agree with the
#: fresh in-memory strict audit on (independent re-audit every run)
AUDIT_COMPARE_FIELDS = ('passed', 'policy_used', 'route_count', 'routed_count',
                        'd56_checked_count', 'd56_passed_count',
                        'd56_failed_count', 'violation_pair_count',
                        'crossing_count', 'spacing_violation_pairs',
                        'overlap_pairs', 'crossing_window_overlap_pairs')
COMBINED_REQUIRED_FILES = ('routes_1024.json', 'statistics.json',
                           'planes_summary.json', 'layer_2d.png',
                           'layer_2d.svg', 'overlay_3d.png',
                           'routing_1024_two_height.gds')


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def iso_now():
    """Local (+08:00) ISO timestamp used by every artefact of this round."""
    tz = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(tz).isoformat(timespec='seconds')


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, payload, indent=1):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=indent),
                    encoding='utf-8')
    return path


def relative(path):
    path = Path(path)
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return str(path)


def file_record(path):
    path = Path(path)
    return {'path': str(path), 'relative': relative(path),
            'exists': path.exists(),
            'bytes': path.stat().st_size if path.exists() else None,
            'sha256': sha256_file(path) if path.exists() else None}


def planes_root(root):
    return Path(root) / 'planes' / TOPOLOGY


def plane_dir(root, label, plane):
    return planes_root(root) / label / plane


def combined_dir(root, label):
    return Path(root) / 'combined' / TOPOLOGY / label


def png_info(path):
    """PNG signature + IHDR dimensions (figure integrity, independent check)."""
    import struct
    path = Path(path)
    if not path.exists():
        return {'exists': False, 'valid_png': False}
    head = path.read_bytes()[:33]
    okay = (len(head) >= 33 and head[:8] == b'\x89PNG\r\n\x1a\n'
            and head[12:16] == b'IHDR')
    if not okay:
        return {'exists': True, 'valid_png': False,
                'bytes': path.stat().st_size}
    width, height = struct.unpack('>II', head[16:24])
    return {'exists': True, 'valid_png': True, 'width': width, 'height': height,
            'bytes': path.stat().st_size}


def svg_info(path):
    path = Path(path)
    if not path.exists():
        return {'exists': False, 'valid_svg': False}
    text = path.read_text(encoding='utf-8', errors='replace')
    stripped = text.lstrip()
    valid = (stripped.startswith('<?xml') or stripped.startswith('<svg')) \
        and '<svg' in text and '</svg>' in text
    return {'exists': True, 'valid_svg': valid, 'bytes': path.stat().st_size}


def gds_reread(path):
    """Re-open a two-height GDS and verify layer ownership independently."""
    import gdspy
    path = Path(path)
    if not path.exists():
        return {'exists': False, 'verified': False}
    library = gdspy.GdsLibrary(infile=str(path))
    tops = library.top_level()
    paths = list(tops[0].paths) if tops else []
    layers = sorted({int(layer) for item in paths for layer in item.layers})
    datatypes = sorted({int(datatype) for item in paths
                        for datatype in item.datatypes})
    layer_counts = {
        layer: sum(1 for item in paths
                   if any(int(value) == layer for value in item.layers))
        for layer in layers}
    return {'exists': True, 'verified': bool(layers == [0, 1]
                                            and datatypes == [0]),
            'layers': layers, 'datatypes': datatypes,
            'paths_per_layer': {str(key): value
                                for key, value in layer_counts.items()},
            'path_count': len(paths),
            'bytes': path.stat().st_size}


# ---------------------------------------------------------------------------
# label discovery
# ---------------------------------------------------------------------------
def _planes_present(root, label):
    return [plane for plane in PLANES
            if (plane_dir(root, label, plane) / 'routes.json').exists()]


def discover_labels(root, requested=None):
    """Ordered labels to process plus the requested-but-missing ones.

    Without ``requested`` the canonical order BASE,E1,E2,E3,Z1OPT,BEST comes
    first and any other label found under ``planes/V2`` is appended (sorted).
    With ``requested`` the requested order is used exclusively (case
    insensitive), and requested labels that do not exist are reported.
    """
    base = planes_root(root)
    existing = []
    if base.exists():
        for child in sorted(base.iterdir()):
            if child.is_dir() and _planes_present(root, child.name):
                existing.append(child.name)
    by_lower = {name.lower(): name for name in existing}
    if requested:
        ordered = []
        missing = []
        for token in requested:
            name = by_lower.get(token.lower())
            if name is None:
                missing.append(token)
            elif name not in ordered:
                ordered.append(name)
        return ordered, missing
    ordered = [name for name in LABEL_ORDER if name in existing]
    extra = sorted(name for name in existing if name not in LABEL_ORDER)
    return ordered + extra, []


# ---------------------------------------------------------------------------
# strict audit (the only acceptance authority)
# ---------------------------------------------------------------------------
def run_strict_audit(routes_path):
    """Fresh frozen strict audit of one plane + the compact on-disk payload."""
    routes_path = Path(routes_path)
    started = time.perf_counter()
    report = validate_fslw.build_report(
        routes_path=routes_path, policy='strict',
        expected_route_count=ROUTES_PER_PLANE,
        radius=float(fslw_config.RADIUS_MM))
    wall = time.perf_counter() - started
    audit = validate_fslw._compact_audit(report, 'strict')  # noqa: SLF001
    audit['wall_seconds'] = wall
    audit['routes_sha256'] = sha256_file(routes_path)
    audit['routes_size_bytes'] = routes_path.stat().st_size
    audit['routes_mtime_utc'] = time.strftime(
        '%Y-%m-%dT%H:%M:%SZ', time.gmtime(routes_path.stat().st_mtime))
    return report, audit, wall


def ensure_audit_file(root, label, plane, report, audit, wall, force, log):
    """Write ``audit_strict.json`` (scan_and_audit schema) unless already fresh.

    The BASE artefacts are frozen by the T1 acceptance record: an existing BASE
    audit file is never overwritten.  A missing one is written (gap fill); a
    stale/inconsistent one is reported as an acceptance failure instead.
    """
    run_dir = plane_dir(root, label, plane)
    path = run_dir / 'audit_strict.json'
    existing = None
    if path.exists():
        try:
            existing = load_json(path)
        except (OSError, ValueError):
            existing = None
    consistency = {}
    status = None
    written = False
    if existing is not None:
        for field in AUDIT_COMPARE_FIELDS:
            consistency[field] = existing.get(field) == audit.get(field)
        stale = existing.get('routes_sha256') != audit.get('routes_sha256')
        inconsistent = stale or not all(consistency.values())
        if not inconsistent and not (force and label != 'BASE'):
            status = 'fresh'
        elif label == 'BASE':
            # never mutate the frozen, already-accepted BASE audit artefacts
            status = 'base_frozen_inconsistent'
        else:
            write_json(path, audit)
            status = 'rewritten'
            written = True
    else:
        write_json(path, audit)
        status = 'written'
        written = True
    if written:
        current = sha256_file(path)
    elif path.exists():
        current = sha256_file(path)
    else:
        current = None
    return {
        'file': str(path),
        'relative': relative(path),
        'sha256': current,
        'routes_sha256': audit['routes_sha256'],
        'status': status,
        'written': written,
        'wall_seconds': wall,
        'compact_report_sha256': hashlib.sha256(
            json.dumps(audit, sort_keys=True).encode('utf-8')).hexdigest(),
        'fresh_fields_equal_fresh_audit': (all(consistency.values())
                                           if consistency else True),
        'field_comparison': consistency,
    }


def _violation_counters(report):
    return {field: report.get(field) for field in VIOLATION_FIELDS}


# ---------------------------------------------------------------------------
# identity vs the frozen V2 CSV
# ---------------------------------------------------------------------------
def check_plane_identity(routes_path, plane):
    """All 512 connection identities of one plane against the frozen V2 CSV."""
    routes_path = Path(routes_path)
    payload = load_json(routes_path)
    records = payload['routes'] if isinstance(payload, dict) else payload
    csv_routes, _endpoints, _connectors, validation = fslw_ports.load_plane(
        TOPOLOGY, plane)
    by_id = {route['route_id']: route for route in csv_routes}
    mismatches = []
    usage = Counter()
    for record in records:
        route_id = record.get('route_id')
        source = by_id.get(route_id)
        if source is None:
            mismatches.append({'route_id': route_id, 'field': 'route_id',
                               'payload': route_id, 'csv': None})
            continue
        for field in IDENTITY_FIELDS:
            if record.get(field) != source.get(field):
                mismatches.append({'route_id': route_id, 'field': field,
                                   'payload': record.get(field),
                                   'csv': source.get(field)})
        if record.get('plane') != plane:
            mismatches.append({'route_id': route_id, 'field': 'plane',
                               'payload': record.get('plane'), 'csv': plane})
        if record.get('z_mm') != payload.get('z_mm'):
            mismatches.append({'route_id': route_id, 'field': 'z_mm',
                               'payload': record.get('z_mm'),
                               'csv': payload.get('z_mm')})
        for role in ('source_endpoint', 'target_endpoint'):
            usage[record.get(role)] += 1
    ids_payload = [record.get('route_id') for record in records]
    ids_csv = [route['route_id'] for route in csv_routes]
    statuses = Counter(str(record.get('status') or '').strip().lower()
                       for record in records)
    csv_path = Path(validation['csv_path'])
    csv_sha = sha256_file(csv_path)
    result = {
        'routes_path': str(routes_path),
        'record_count': len(records),
        'expected_record_count': ROUTES_PER_PLANE,
        'identity_mismatch_count': len(mismatches),
        'identity_mismatches': mismatches[:10],
        'route_id_order_matches_csv': ids_payload == ids_csv,
        'status_counts': dict(statuses),
        'routed': statuses.get('routed', 0),
        'failed': statuses.get('failed', 0),
        'unknown_status_count': (len(records) - statuses.get('routed', 0)
                                 - statuses.get('failed', 0)),
        'ports_used_unique': len(usage),
        'ports_used_once': (len(usage) == 1024
                            and set(usage.values()) == {1}),
        'csv_path': str(csv_path),
        'csv_sha256': csv_sha,
        'csv_sha256_expected': V2_CSV_SHA256,
        'csv_sha256_matches_expected': csv_sha.lower() == V2_CSV_SHA256,
        'payload_csv_sha256': payload.get('csv_sha256'),
        'payload_csv_sha256_matches_expected':
            str(payload.get('csv_sha256', '')).lower() == V2_CSV_SHA256,
        'plane_validation_passed': validation.get('passed') is True,
        'plane_validation_issues': validation.get('issues'),
        'fields_checked': list(IDENTITY_FIELDS),
    }
    result['passed'] = bool(
        result['record_count'] == ROUTES_PER_PLANE
        and result['identity_mismatch_count'] == 0
        and result['route_id_order_matches_csv']
        and result['unknown_status_count'] == 0
        and result['ports_used_once']
        and result['csv_sha256_matches_expected']
        and result['payload_csv_sha256_matches_expected']
        and result['plane_validation_passed'])
    return result


# ---------------------------------------------------------------------------
# statistics.json (fslw.metrics) - after the audit file exists
# ---------------------------------------------------------------------------
def ensure_statistics(root, label, plane, report, force, log):
    """Gap-fill/refresh ``statistics.json`` from the authoritative audit.

    For BASE an existing statistics file is frozen: it is only rebuilt when it
    is missing (the T1 record pins its sha256).
    """
    run_dir = plane_dir(root, label, plane)
    routes_path = run_dir / 'routes.json'
    audit_path = run_dir / 'audit_strict.json'
    statistics_path = run_dir / 'statistics.json'
    problems = []
    written = False
    statistics = None
    if statistics_path.exists() and not (force and label != 'BASE'):
        try:
            statistics = load_json(statistics_path)
        except (OSError, ValueError) as exc:
            problems.append(f'statistics_unreadable:{exc}')
            statistics = None
        if statistics is not None:
            source = statistics.get('source') or {}
            audit_meta = source.get('audit') or {}
            if statistics.get('audit_passed') is not True:
                problems.append('audit_passed_not_true')
            if source.get('routes_sha256') != sha256_file(routes_path):
                problems.append('routes_sha256_mismatch')
            if audit_path.exists() and source.get('audit_sha256') != sha256_file(
                    audit_path):
                problems.append('audit_sha256_mismatch')
            if audit_meta.get('status') != 'merged':
                problems.append(
                    f'audit_not_merged:{audit_meta.get("status")}')
            if statistics.get('routed') != report.get('routed_count'):
                problems.append('routed_mismatch')
            if problems and label == 'BASE':
                return statistics, False, list(problems)
    if statistics is None or problems or (force and label != 'BASE'):
        started = time.perf_counter()
        statistics = fslw_metrics.build_plane_statistics(run_dir, quiet=True)
        written = True
        wall = time.perf_counter() - started
        problems = []
    else:
        wall = None
    return statistics, written, {
        'wall_seconds': wall,
        'file': str(statistics_path),
        'relative': relative(statistics_path),
        'sha256': sha256_file(statistics_path),
        'problems_with_cached_file': problems,
    }


# ---------------------------------------------------------------------------
# copy a missing plane from the frozen BASE plane
# ---------------------------------------------------------------------------
def materialize_plane_from_base(root, label, plane, log):
    """Copy the frozen BASE geometry of ``plane`` into ``planes/V2/<label>/<plane>``.

    The E1/E2/E3 ablation arms only write z2 and Z1OPT only writes z1; the other
    plane is unchanged from BASE and must still exist for the 1024-channel
    combined artefact.  ``v2opt.core.LayoutState.from_history`` reparses the real
    BASE primitive chains (never route ids), and ``write_plane`` writes the
    frozen fslw payload schema; identity comes from the frozen V2 CSV and the
    primitives are copied verbatim.  This is a *materialisation* step only: the
    acceptance path below re-audits the result with the frozen validator.
    """
    from four_side_1024.v2opt.core import LayoutState  # local: not on audit path
    if abs(float(fslw_config.RADIUS_MM) - 40.0) > 1e-12:
        raise RuntimeError(
            'refusing to materialise a missing plane from the frozen R40 BASE '
            f'during a non-R40 round (radius={fslw_config.RADIUS_MM:g} mm); '
            'produce both planes of this label with the R15 runner instead')
    base_routes = plane_dir(root, 'BASE', plane) / 'routes.json'
    if not base_routes.exists():
        raise FileNotFoundError(
            f'cannot materialise {label}/{plane}: BASE plane missing ({base_routes})')
    target_dir = plane_dir(root, label, plane)
    if (target_dir / 'routes.json').exists():
        return {'status': 'already_present', 'plane': plane,
                'target_dir': str(target_dir)}
    started = time.perf_counter()
    state = LayoutState.from_history(TOPOLOGY, plane, base_routes,
                                     log=lambda *_a, **_k: None)
    detail = {
        'name': label, 'algorithm': label, 'crossing_policy': 'strict',
        'generator': 'frozen_base_plane', 'strategy': 'copy_base_plane',
        'search_performed': False,
        'source_routes_json': relative(base_routes),
        'source_routes_sha256': sha256_file(base_routes),
        'note': ('this experiment only wrote the other height plane; the missing '
                 'plane is materialised from the frozen BASE plane with identical '
                 'connection identity and identical primitives (no search, no '
                 'geometry edit)'),
    }
    state.write_plane(target_dir, label, detail, 'BASE_geometry_copy')
    # independent copy-verification: routed primitives must be byte-identical
    base_payload = load_json(base_routes)
    target_payload = load_json(target_dir / 'routes.json')
    base_by_id = {record['route_id']: record
                  for record in base_payload['routes']}
    geometry_mismatches = []
    copied_routed = 0
    for record in target_payload['routes']:
        route_id = record.get('route_id')
        source = base_by_id.get(route_id)
        if record.get('status') == 'routed':
            copied_routed += 1
            if source is None or source.get('status') != 'routed':
                geometry_mismatches.append(
                    {'route_id': route_id, 'kind': 'missing_in_base'})
            elif record.get('primitives') != source.get('primitives'):
                geometry_mismatches.append(
                    {'route_id': route_id, 'kind': 'primitives_changed'})
    seconds = time.perf_counter() - started
    log(f'  materialised {label}/{plane} from frozen BASE '
        f'({copied_routed} routed, {seconds:.1f}s)')
    return {'status': 'copied', 'plane': plane,
            'source_routes_json': relative(base_routes),
            'source_routes_sha256': sha256_file(base_routes),
            'target_dir': str(target_dir),
            'target_routes_sha256': sha256_file(target_dir / 'routes.json'),
            'routed': copied_routed,
            'geometry_mismatch_count': len(geometry_mismatches),
            'geometry_mismatches': geometry_mismatches[:10],
            'seconds': round(seconds, 3)}


# ---------------------------------------------------------------------------
# combined 1024-channel artefact
# ---------------------------------------------------------------------------
def combined_is_fresh(root, label, plane_routed):
    """Cheap freshness test of an existing combined layout."""
    cdir = combined_dir(root, label)
    missing = [name for name in COMBINED_REQUIRED_FILES
               if not (cdir / name).exists()]
    if missing:
        return False, {'reason': 'missing_files', 'missing': missing}
    try:
        payload = load_json(cdir / 'routes_1024.json')
        statistics = load_json(cdir / 'statistics.json')
    except (OSError, ValueError) as exc:
        return False, {'reason': 'unreadable', 'error': str(exc)}
    records = payload.get('routes') or []
    if len(records) != CONNECTIONS_TOTAL:
        return False, {'reason': 'record_count',
                       'records': len(records)}
    routed_by_plane = Counter(
        record.get('plane') for record in records
        if str(record.get('status') or 'routed').strip().lower() == 'routed')
    if dict(routed_by_plane) != dict(plane_routed):
        return False, {'reason': 'routed_by_plane',
                       'payload': dict(routed_by_plane),
                       'expected': dict(plane_routed)}
    if statistics.get('routed') != sum(plane_routed.values()):
        return False, {'reason': 'statistics_routed',
                       'statistics': statistics.get('routed')}
    return True, {'reason': 'fresh'}


def build_combined_artefact(root, label, force, log):
    cdir = combined_dir(root, label)
    started = time.perf_counter()
    fslw_combine.build_combined(root, TOPOLOGY, label, quiet=True)
    seconds = time.perf_counter() - started
    log(f'  combined {label}: built in {seconds:.1f}s -> {relative(cdir)}')
    return {'built': True, 'seconds': round(seconds, 3), 'dir': str(cdir)}


def check_combined(root, label, plane_report_routed, plane_report_crossings,
                   plane_routed):
    """Independent verification of ``combined/V2/<LABEL>/``."""
    cdir = combined_dir(root, label)
    payload = load_json(cdir / 'routes_1024.json')
    statistics = load_json(cdir / 'statistics.json')
    summary = load_json(cdir / 'planes_summary.json')
    records = payload['routes']
    statuses = Counter(str(record.get('status') or '').strip().lower()
                       for record in records)
    routed_records = [record for record in records
                      if str(record.get('status') or '').strip().lower()
                      == 'routed']
    by_plane = Counter(record.get('plane') for record in routed_records)
    ids = [record.get('route_id') for record in records]
    csv_union_ids = set()
    for plane in PLANES:
        csv_routes, _e, _c, _v = fslw_ports.load_plane(TOPOLOGY, plane)
        csv_union_ids.update(route['route_id'] for route in csv_routes)
    expected_total = sum(plane_report_routed.values())
    expected_crossings = sum(plane_report_crossings.values())
    violations = statistics.get('violations') or {}
    gds = ((summary.get('gds') or {}).get('combined') or {})
    figures = summary.get('figures') or {}
    files = {name: file_record(cdir / name) for name in COMBINED_REQUIRED_FILES}
    expected_layer_counts = {str(index): plane_report_routed[plane]
                             for index, plane in enumerate(PLANES)}
    independent_gds = gds_reread(cdir / 'routing_1024_two_height.gds')
    figure_integrity = {
        'layer_2d.png': png_info(cdir / 'layer_2d.png'),
        'overlay_3d.png': png_info(cdir / 'overlay_3d.png'),
        'layer_2d.svg': svg_info(cdir / 'layer_2d.svg'),
    }
    result = {
        'combined_dir': str(cdir),
        'files': files,
        'routes_1024_records': len(records),
        'routes_1024_unique_route_ids': len(set(ids)),
        'routed_total': statuses.get('routed', 0),
        'failed_total': statuses.get('failed', 0),
        'routed_by_plane': dict(by_plane),
        'z1_routed': plane_report_routed['z1'],
        'z2_routed': plane_report_routed['z2'],
        'expected_routed_total': expected_total,
        'statistics_routed': statistics.get('routed'),
        'statistics_unrouted': statistics.get('unrouted'),
        'connections_total': statistics.get('connections_total'),
        'routing_rate': statistics.get('routing_rate'),
        'expected_routing_rate': expected_total / CONNECTIONS_TOTAL,
        'audit_passed_all_planes': statistics.get('audit_passed_all_planes'),
        'same_plane_crossings': statistics.get('same_plane_crossings'),
        'expected_same_plane_crossings': expected_crossings,
        'violations': violations,
        'same_plane_violation_total': violations.get('same_plane_total'),
        'violations_complete': violations.get('complete'),
        'gds_summary_verified': gds.get('verified'),
        'gds_summary_layers': gds.get('layers'),
        'gds_summary_paths_per_layer': gds.get('paths_per_layer'),
        'independent_gds_reread': independent_gds,
        'figure_integrity': figure_integrity,
        'routes_1024_route_ids_cover_csv': set(ids) == csv_union_ids,
        'planes_summary_figures': {
            'layer_2d_png': (figures.get('layer_2d_png') or {}).get('file'),
            'overlay_3d_png': (figures.get('overlay_3d_png') or {}).get('file'),
        },
    }
    checks = {
        'all_files_exist': all(record['exists'] and record['bytes']
                               for record in files.values()),
        'records_1024': result['routes_1024_records'] == CONNECTIONS_TOTAL,
        'unique_route_ids_1024': result['routes_1024_unique_route_ids']
        == CONNECTIONS_TOTAL,
        'ids_cover_csv': result['routes_1024_route_ids_cover_csv'],
        'routed_equals_z1_plus_z2': result['routed_total'] == expected_total,
        'routed_by_plane': result['routed_by_plane'] == dict(plane_routed),
        'statistics_routed': result['statistics_routed'] == expected_total,
        'statistics_unrouted': result['statistics_unrouted']
        == CONNECTIONS_TOTAL - expected_total,
        'connections_total_1024': result['connections_total']
        == CONNECTIONS_TOTAL,
        'routing_rate': result['routing_rate'] == expected_total
        / CONNECTIONS_TOTAL,
        'audit_passed_all_planes': result['audit_passed_all_planes'] is True,
        'violations_complete': result['violations_complete'] is True,
        'same_plane_violations_zero': result['same_plane_violation_total'] == 0,
        'same_plane_crossings': result['same_plane_crossings']
        == expected_crossings,
        'gds_summary_verified': result['gds_summary_verified'] is True,
        'gds_summary_layers_0_1': result['gds_summary_layers'] == [0, 1],
        'gds_paths_per_layer': result['gds_summary_paths_per_layer']
        == expected_layer_counts,
        'independent_gds_layers_0_1': independent_gds.get('layers') == [0, 1],
        'independent_gds_datatypes_0': independent_gds.get('datatypes') == [0],
        'independent_gds_paths_per_layer':
            independent_gds.get('paths_per_layer') == expected_layer_counts,
        'figures_valid': (figure_integrity['layer_2d.png'].get('valid_png')
                          is True
                          and figure_integrity['overlay_3d.png'].get(
                              'valid_png') is True
                          and figure_integrity['layer_2d.svg'].get(
                              'valid_svg') is True),
    }
    result['checks'] = checks
    result['passed'] = bool(all(checks.values()))
    return result


# ---------------------------------------------------------------------------
# per-plane acceptance
# ---------------------------------------------------------------------------
def accept_plane(root, label, plane, force, log):
    """Full independent acceptance of one height plane; returns its record."""
    run_dir = plane_dir(root, label, plane)
    routes_path = run_dir / 'routes.json'
    started = time.perf_counter()
    report, audit, audit_wall = run_strict_audit(routes_path)
    log(f'  {label}/{plane}: strict audit passed={report.get("passed")} '
        f'routed={report.get("routed_count")} '
        f'crossings={report.get("crossing_count")} '
        f'violations={report.get("violation_pair_count")} '
        f'({audit_wall:.1f}s, {report.get("runtime_seconds", 0):.1f}s report)')
    audit_record = ensure_audit_file(root, label, plane, report, audit,
                                     audit_wall, force, log)
    identity = check_plane_identity(routes_path, plane)
    statistics, statistics_written, statistics_meta = ensure_statistics(
        root, label, plane, report, force, log)
    statistics_meta['written'] = statistics_written
    statistics_meta['routed'] = statistics.get('routed')
    statistics_meta['unrouted'] = statistics.get('unrouted')
    statistics_meta['audit_passed'] = statistics.get('audit_passed')
    statistics_meta['crossing_count'] = statistics.get('crossing_count')
    statistics_meta['total_violation_count'] = statistics.get(
        'total_violation_count')
    statistics_meta['audit_source_status'] = (
        (statistics.get('source') or {}).get('audit') or {}).get('status')
    statistics_meta['audit_sha256_recorded'] = (
        (statistics.get('source') or {}).get('audit_sha256'))

    process = report.get('process') or {}
    violations = _violation_counters(report)
    statistics_source = statistics.get('source') or {}
    statistics_audit = statistics_source.get('audit') or {}
    audit_file_sha = (audit_record['sha256']
                      if audit_record['sha256'] is not None
                      else sha256_file(run_dir / 'audit_strict.json'))
    baseline_statistics_ok = (
        statistics.get('audit_passed') is True
        and statistics_audit.get('status') == 'merged'
        and statistics_source.get('audit_sha256') == audit_file_sha
        and statistics_source.get('routes_sha256')
        == sha256_file(routes_path)
        and statistics.get('routed') == report.get('routed_count')
    )
    checks = {
        'validator_passed': report.get('passed') is True,
        'validator_errors_empty': not (report.get('errors') or []),
        'policy_strict': report.get('policy_used') == 'strict',
        'route_count_512': report.get('route_count') == ROUTES_PER_PLANE,
        'd56_failed_zero': report.get('d56_failed_count') == 0,
        'd56_checked_equals_routed':
            report.get('d56_checked_count') == report.get('routed_count'),
        'd56_passed_equals_routed':
            report.get('d56_passed_count') == report.get('routed_count'),
        'violation_pair_count_zero':
            report.get('violation_pair_count') == 0,
        'all_violation_fields_zero': all(value == 0
                                         for value in violations.values()),
        'endpoint_unchecked_zero':
            (report.get('endpoint_unchecked_count') or 0) == 0,
        'structure_checked':
            (report.get('structure') or {}).get('checked') is True,
        'radius_matches_process':
            abs(float(process.get('radius_mm') or -1.0)
                - float(fslw_config.RADIUS_MM)) < 1e-12,
        'radius_documented': process.get('radius_mm') is not None,
        'clearance_008mm': abs(float(process.get(
            'centerline_clearance_mm') or 0.0) - 0.08) < 1e-12,
        'width_005mm': process.get('waveguide_width_mm') == 0.05,
        'identity_passed': identity['passed'],
        'routed_counts_consistent':
            identity['routed'] == report.get('routed_count'),
        'statistics_present': statistics_meta.get('sha256') is not None,
        'statistics_audit_passed':
            statistics.get('audit_passed') is True,
        'statistics_merged_from_audit_file': baseline_statistics_ok,
        'audit_file_frozen_or_fresh': audit_record['status'] in (
            'fresh', 'written', 'rewritten', 'base_frozen_inconsistent'),
        'audit_file_consistent': (audit_record['status'] !=
                                  'base_frozen_inconsistent'),
    }
    passed = bool(all(checks.values()))
    record = {
        'label': label,
        'plane': plane,
        'run_dir': str(run_dir),
        'routes_path': str(routes_path),
        'routes_sha256': sha256_file(routes_path),
        'routes_size_bytes': routes_path.stat().st_size,
        'report_wall_seconds': audit_wall,
        'audit': audit_record,
        'validator_report': {
            'passed': report.get('passed'),
            'policy_used': report.get('policy_used'),
            'plane': report.get('plane'),
            'route_count': report.get('route_count'),
            'routed_count': report.get('routed_count'),
            'failed_status_count': report.get('failed_status_count'),
            'd56_checked_count': report.get('d56_checked_count'),
            'd56_passed_count': report.get('d56_passed_count'),
            'd56_failed_count': report.get('d56_failed_count'),
            'endpoint_unchecked_count': report.get('endpoint_unchecked_count'),
            'pair_audit': report.get('pair_audit'),
            'pair_audited_route_count': report.get('pair_audited_route_count'),
            'candidate_pair_count': report.get('candidate_pair_count'),
            'crossing_count': report.get('crossing_count'),
            'crossing_pair_count': report.get('crossing_pair_count'),
            'crossing_angle_histogram': report.get(
                'crossing_angle_histogram'),
            'small_angle_crossing_count': report.get(
                'small_angle_crossing_count'),
            'min_non_crossing_centerline_mm': report.get(
                'min_non_crossing_centerline_mm'),
            'crossing_window_count': report.get('crossing_window_count'),
            'crossing_window_max_mm': report.get('crossing_window_max_mm'),
            'violation_pair_count': report.get('violation_pair_count'),
            'violations': violations,
            'self_checks': {
                field: report.get(field) for field in (
                    'self_intersections', 'self_overlaps',
                    'self_spacing_violations', 'radius_violations',
                    'boundary_violations', 'diagonal_line_violations',
                    'free_or_short_s_arc_violations')},
            'errors': report.get('errors'),
            'warnings': report.get('warnings'),
            'structure': report.get('structure'),
            'process': {
                'board_mm': process.get('board_mm'),
                'radius_mm': process.get('radius_mm'),
                'waveguide_width_mm': process.get('waveguide_width_mm'),
                'min_edge_gap_mm': process.get('min_edge_gap_mm'),
                'centerline_clearance_mm': process.get(
                    'centerline_clearance_mm'),
                'centerline_clearance_limit_mm': process.get(
                    'centerline_clearance_limit_mm'),
                'sagitta_mm': process.get('sagitta_mm'),
                'parameters_source': process.get('parameters_source'),
            },
            'runtime_seconds': report.get('runtime_seconds'),
        },
        'identity': identity,
        'statistics': statistics_meta,
        'checks': checks,
        'passed': passed,
        'seconds': round(time.perf_counter() - started, 3),
    }
    return record


# ---------------------------------------------------------------------------
# top level
# ---------------------------------------------------------------------------
def _label_verdict(label_records, combined_record, require_combined=True):
    planes_passed = {plane: record['passed']
                     for plane, record in label_records.items()}
    planes_all = all(planes_passed.values()) and len(planes_passed) == 2
    combined_passed = (combined_record or {}).get('passed') is True
    return {
        'planes': planes_passed,
        'planes_passed': planes_all,
        'combined_passed': combined_passed,
        'combined_required': bool(require_combined),
        'all_passed': bool(planes_all
                           and (combined_passed if require_combined else True)),
    }


def finalize(args, log=print):
    root = Path(args.root).resolve()
    if not root.exists():
        raise SystemExit(f'finalize: output root does not exist: {root}')
    summary_output = (Path(args.summary_output).resolve()
                      if args.summary_output
                      else root / 'final_validation.json')
    requested = None
    if args.labels:
        requested = [item.strip() for item in args.labels.split(',')
                     if item.strip()]
    labels, missing_labels = discover_labels(root, requested)
    if not labels:
        raise SystemExit(f'finalize: no experiment planes found under '
                         f'{planes_root(root)}')
    total_started = time.perf_counter()
    log('=' * 78)
    log('T4 / task 9: independent final acceptance of the V2 optimisation round')
    log(f'project root : {PROJECT_ROOT}')
    log(f'output root  : {root}')
    log(f'labels       : {labels}')
    if missing_labels:
        log(f'missing      : {missing_labels}')
    log(f'authority    : four_side_1024.fslw.validate_fslw policy=strict '
        f'(route_count=512, R={fslw_config.RADIUS_MM:g} mm, clearance 0.080 mm)')
    log('=' * 78)

    plane_records = {}
    materialized = {}
    combined_records = {}
    label_timings = {}
    for label in labels:
        label_started = time.perf_counter()
        log(f'[{label}]')
        present = _planes_present(root, label)
        log(f'  planes present: {present}')
        if label == 'BASE':
            if len(present) != 2:
                log(f'  ERROR: BASE must contain both planes, found {present}')
        else:
            materialized[label] = []
            for plane in PLANES:
                if plane in present:
                    continue
                try:
                    record = materialize_plane_from_base(root, label, plane, log)
                except Exception as exc:  # noqa: BLE001 - reported, not hidden
                    log(f'  ERROR materialising {label}/{plane}: '
                        f'{type(exc).__name__}: {exc}')
                    materialized[label].append(
                        {'plane': plane, 'status': 'failed',
                         'error': f'{type(exc).__name__}: {exc}'})
                    continue
                materialized[label].append(record)
                present = _planes_present(root, label)
        label_records = {}
        for plane in PLANES:
            if not (plane_dir(root, label, plane) / 'routes.json').exists():
                log(f'  WARNING: {label}/{plane} missing -> plane not accepted')
                continue
            try:
                record = accept_plane(root, label, plane, args.force, log)
            except Exception as exc:  # noqa: BLE001 - reported, not hidden
                log(f'  ERROR auditing {label}/{plane}: '
                    f'{type(exc).__name__}: {exc}')
                record = {'label': label, 'plane': plane, 'passed': False,
                          'error': f'{type(exc).__name__}: {exc}'}
            plane_records[f'{label}/{plane}'] = record
            label_records[plane] = record
        combined_record = None
        if args.skip_combine:
            combined_record = {'label': label, 'status': 'skipped',
                               'passed': False,
                               'note': '--skip-combine'}
        elif len(label_records) != 2:
            combined_record = {
                'label': label, 'status': 'not_built', 'passed': False,
                'note': 'both height planes must be accepted before the combined '
                        'layout is built'}
        elif not all(record['passed'] for record in label_records.values()):
            combined_record = {
                'label': label, 'status': 'not_built', 'passed': False,
                'note': 'a height plane failed its independent acceptance; the '
                        'combined artefact is not built for an invalid layout'}
        else:
            try:
                plane_report_routed = {
                    plane: record['validator_report']['routed_count']
                    for plane, record in label_records.items()}
                plane_routed = {
                    plane: record['identity']['routed']
                    for plane, record in label_records.items()}
                plane_crossings = {
                    plane: record['validator_report']['crossing_count']
                    for plane, record in label_records.items()}
                fresh, freshness = combined_is_fresh(
                    root, label, plane_report_routed)
                build_info = {'built': False,
                              'reason': freshness.get('reason')}
                if args.force and label != 'BASE':
                    fresh = False
                if not fresh:
                    build_info = build_combined_artefact(
                        root, label, args.force, log)
                cdir = combined_dir(root, label)
                combined_record = check_combined(
                    root, label, plane_report_routed, plane_crossings,
                    plane_routed)
                combined_record['label'] = label
                combined_record['status'] = ('built' if build_info.get('built')
                                             else 'reused')
                combined_record['build'] = build_info
                combined_record['combined_dir'] = str(cdir)
                log(f'  combined {label}: routed={combined_record["routed_total"]}'
                    f'/{CONNECTIONS_TOTAL} passed={combined_record["passed"]} '
                    f'({combined_record["status"]})')
            except Exception as exc:  # noqa: BLE001 - reported, not hidden
                log(f'  ERROR combined {label}: '
                    f'{type(exc).__name__}: {exc}')
                combined_record = {
                    'label': label, 'status': 'failed', 'passed': False,
                    'error': f'{type(exc).__name__}: {exc}'}
        combined_records[label] = combined_record
        label_timings[label] = round(time.perf_counter() - label_started, 3)

    # ---------------------------------------------------------------- summary
    audit_files = {}
    for key, record in plane_records.items():
        audit = record.get('audit') or {}
        if audit.get('file') and audit.get('sha256'):
            audit_files[audit['file']] = {
                'sha256': audit['sha256'],
                'status': audit.get('status'),
                'routes_sha256': audit.get('routes_sha256'),
            }
    for label, record in combined_records.items():
        for name, item in (record.get('files') or {}).items():
            if item.get('exists') and item.get('sha256'):
                audit_files[item['path']] = {
                    'sha256': item['sha256'], 'status': 'combined',
                    'routes_sha256': None}
    label_verdicts = {}
    routed_totals = {}
    for label in labels:
        records = {plane: plane_records[f'{label}/{plane}']
                   for plane in PLANES if f'{label}/{plane}' in plane_records}
        verdict = _label_verdict(records, combined_records.get(label),
                                 require_combined=not args.skip_combine)
        label_verdicts[label] = verdict
        routed_totals[label] = sum(
            record.get('validator_report', {}).get('routed_count') or 0
            for record in records.values())
    ranked = sorted(labels, key=lambda name: (-routed_totals.get(name, 0),
                                              name))
    all_passed = bool(labels) and all(verdict['all_passed']
                                      for verdict in label_verdicts.values())
    all_requested_present = not missing_labels
    environment = {
        'python': sys.version.split()[0],
        'implementation': platform.python_implementation(),
        'platform': platform.platform(),
        'script': relative(Path(__file__).resolve()),
        'authoritative_validator': 'four_side_1024.fslw.validate_fslw',
        'statistics_tool': 'four_side_1024.fslw.metrics.build_plane_statistics',
        'combined_tool': 'four_side_1024.fslw.combine.build_combined',
        'frozen_csv_sha256': V2_CSV_SHA256,
        'frozen_process': {
            'board_mm': fslw_config.BOARD_MM,
            'waveguide_width_mm': fslw_config.WIDTH_MM,
            'min_edge_gap_mm': fslw_config.EDGE_GAP_MM,
            'centerline_clearance_mm': fslw_config.CLEARANCE_MM,
            'min_bend_radius_mm': fslw_config.RADIUS_MM,
            'sagitta_mm': fslw_config.SAGITTA_MM,
            'policy': 'strict',
        },
    }
    payload = {
        'schema': 'four_side_1024_v2_candidate_rr_v01_final_validation_v1',
        'task': 'T4 / task 9: independent authoritative acceptance of the V2 '
                'optimisation round',
        'generated_at': iso_now(),
        'project_root': str(PROJECT_ROOT),
        'output_root': str(root),
        'topology': TOPOLOGY,
        'authority': {
            'validator': 'four_side_1024.fslw.validate_fslw',
            'policy': 'strict',
            'expected_route_count_per_plane': ROUTES_PER_PLANE,
            'clearance_mm': fslw_config.CLEARANCE_MM,
            'radius_mm': fslw_config.RADIUS_MM,
            'note': ('each plane is re-audited from its routes.json primitives '
                     'with the frozen strict validator; the V2 search/candidate '
                     'modules are never used on the acceptance path'),
        },
        'labels_processed': labels,
        'labels_missing': missing_labels,
        'all_requested_labels_present': all_requested_present,
        'label_order': list(LABEL_ORDER),
        'planes': plane_records,
        'combined': combined_records,
        'materialized_planes': materialized,
        'audit_files': audit_files,
        'summary': {
            'all_passed': all_passed,
            'labels': label_verdicts,
            'plane_count': len(plane_records),
            'planes_passed': sum(1 for record in plane_records.values()
                                 if record.get('passed')),
            'combined_count': sum(1 for record in combined_records.values()
                                  if record.get('status') in ('built', 'reused')),
            'combined_passed': sum(1 for record in combined_records.values()
                                   if record.get('passed')),
            'routed_totals': routed_totals,
            'ranking_by_routed': ranked,
            'best_label': ranked[0] if ranked else None,
            'base_routed': routed_totals.get('BASE'),
            'delta_vs_base': {
                label: (routed_totals.get(label, 0)
                        - (routed_totals.get('BASE') or 0))
                for label in labels},
        },
        'environment': environment,
        'timings': {
            'label_seconds': label_timings,
            'total_seconds': round(time.perf_counter() - total_started, 3),
        },
        'reproduce': {
            'command': ('.venv\\Scripts\\python.exe -m '
                        'four_side_1024.v2opt.finalize --root '
                        f'"{relative(root)}"'),
            'skip_combine_command': ('.venv\\Scripts\\python.exe -m '
                                     'four_side_1024.v2opt.finalize --root '
                                     f'"{relative(root)}" --skip-combine'),
            'note': 'BASE audit/statistics/combined artefacts are gap-filled '
                    'only (frozen T1 acceptance record); non-BASE labels are '
                    're-derived from their current routes.json',
        },
        'notes': [
            'the authoritative acceptance criterion is validate_fslw strict '
            '(clearance 0.080 mm, R={radius:g} mm, 512 route records per height '
            'plane); no optimisation module takes part in the verdict'.format(
                radius=fslw_config.RADIUS_MM),
            'planes z1 and z2 are independent 2D problems at model heights 0.0 '
            'and 0.5 mm; XY-projected cross-plane overlaps are informational '
            'only (fslw/SPEC.md section 2)',
            'a label that only wrote one height plane has the other plane '
            'materialised from the frozen BASE plane with identical identity '
            'and identical primitives (see materialized_planes)',
            'BASE artefacts recorded in baseline_acceptance.json are never '
            'rewritten; only missing BASE artefacts are gap-filled',
            'bend loss and crossing loss remain unknown_uncalibrated; the '
            'combined statistics report only propagation loss',
        ],
    }
    write_json(summary_output, payload)
    # ---------------------------------------------------------------- report
    log('')
    log('=' * 78)
    log('FINAL ACCEPTANCE (T4)')
    log('=' * 78)
    for label in labels:
        verdict = label_verdicts[label]
        records = {plane: plane_records.get(f'{label}/{plane}')
                   for plane in PLANES}
        routed_text = ' + '.join(
            f'{plane}={records[plane].get("validator_report", {}).get("routed_count")}'
            for plane in PLANES if records[plane])
        combined = combined_records.get(label) or {}
        combined_text = f'combined={combined.get("status")}'
        if verdict.get('combined_required'):
            combined_text += f' passed={combined.get("passed")}'
        else:
            combined_text += ' (not required: --skip-combine)'
        log(f"[{'PASS' if verdict['all_passed'] else 'FAIL'}] {label}: "
            f'{routed_text} = {routed_totals.get(label)}/1024, '
            f'{combined_text}')
    log('')
    log(f'all passed            : {all_passed}')
    log(f'all labels present    : {all_requested_present} '
        f'(missing={missing_labels})')
    log(f'final_validation.json : {summary_output}')
    log(f'total wall            : '
        f'{payload["timings"]["total_seconds"]:.1f}s')
    log('=' * 78)
    return 0 if all_passed else 1


def build_parser():
    parser = argparse.ArgumentParser(
        description='Independent final acceptance of the V2 optimisation round: '
                    'frozen strict audit + statistics + combined artefact + '
                    'final_validation.json.')
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT,
                        help='output root of the round '
                             '(default: outputs/four_side_1024_v2_candidate_rr_v01)')
    parser.add_argument('--labels', default=None,
                        help='comma separated label order to process, e.g. '
                             'BASE,E1,E2,E3,Z1OPT,BEST (default: canonical order '
                             'plus every other label found)')
    parser.add_argument('--skip-combine', action='store_true',
                        help='only audit planes and statistics; do not build '
                             'combined layouts')
    parser.add_argument('--force', action='store_true',
                        help='rebuild fresh non-BASE derived artefacts '
                             '(audit/statistics/combined); BASE artefacts are '
                             'still only gap-filled')
    parser.add_argument('--summary-output', type=Path, default=None,
                        help='path of final_validation.json '
                             '(default: <root>/final_validation.json)')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return finalize(args, log=lambda message: print(message, flush=True))


if __name__ == '__main__':
    raise SystemExit(main())
