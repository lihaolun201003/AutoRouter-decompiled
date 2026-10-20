"""T1: recombine the historical two-plane V2 solution into the 698-channel BASE baseline
and audit it independently (authoritative FSLW strict validator + independent D56 index).

What this script produces (all new, nothing existing is modified)
-----------------------------------------------------------------
``outputs/four_side_1024_v2_candidate_rr_v01/``

* ``planes/V2/BASE/z1/{routes.json,config.json,audit_strict.json,statistics.json}``
  512 records recombined from the historical V2_D_z1 run (492 routed).
* ``planes/V2/BASE/z2/{...}``
  512 records recombined from the historical V2_C_z2 run (206 routed).
* ``combined/V2/BASE/``
  ``four_side_1024.fslw.combine.build_combined`` output: ``routes_1024.json``
  (698/1024 routed), ``statistics.json``, ``planes_summary.json``, the two-height
  GDS (layer 0 = z1, layer 1 = z2) and the dual-height figures.
* ``baseline_acceptance.json``
  every one of the seven T1 acceptance criteria with its real numbers, paths and
  PASS/FAIL verdict.
* ``baseline_reproduce.md``
  short reproduction notes.

Provenance
----------
The 698 baseline is a pure recombination of two *already validated* historical
plane solutions (no routing search is run here, no geometry is edited):

* plane z1 primitives <- ``outputs/four_side_1024_fslw_R40_gap30_abcd/planes/V2/D/z1/routes.json``
* plane z2 primitives <- ``outputs/four_side_1024_fslw_R40_gap30_abcd/planes/V2/C/z2/routes.json``

Every routed record's ``primitives``, ``length_mm``, ``bend_count`` and candidate
metadata are copied verbatim (a JSON deep equality is asserted against the
historical files).  Every record's connection identity (route_id / endpoints /
pair / relation / sides / rows) is rebuilt from the frozen V2 CSV through
``four_side_1024.fslw.ports.load_plane('V2', plane)`` so the pairing is a
zero-change projection of the CSV; the result is re-checked against the CSV in
acceptance criterion 1.

Acceptance criteria (task T1)
-----------------------------
1. 512 records per plane, identity fields identical to the frozen CSV pairing,
   V2 CSV sha256 = 49dd9e89c4ea506d04638ae34eb06a0d8163d479de80869804c881ee1c43915e.
2. routed primitives byte-equal (JSON deep equality) to the historical files, 492/206.
3. ``validate_fslw`` strict audit per plane passed=True (audit_strict.json written
   exactly like ``scan_and_audit`` does, including the routes sha256).
4. ``metrics.build_plane_statistics`` -> statistics.json with audit_passed=True.
5. ``combine.build_combined(root,'V2','BASE')`` -> 698 routed, routing_rate 698/1024,
   two-height GDS + figures, combined audit declares 0 same-plane violations.
6. Independent recomputation: rebuild both plane layouts with
   ``four_side_1024.d56.index.D56Index`` (width=0.05, gap=0.03,
   crossing_policy='strict'; no fslw routing-search import) and run a per-route
   leave-one-out ``exclude`` self-check -> zero violations; plus
   ``fslw.crosscheck_fslw.crosscheck`` router-vs-validator pair-verdict agreement.
7. Comparison table of the eight historical V1/V2 x A/B/C/D groups and the 698
   recombination.

Usage
-----
    cd "C:\\Users\\lihao\\Desktop\\Graduation Project\\OpticalWaveguideRouter2D"
    .venv\\Scripts\\python.exe four_side_1024\\v2opt\\audit_baseline.py

This script is idempotent: re-running it rewrites all of the artefacts above from
the read-only historical inputs.  It never writes outside the ``v01`` output root.
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

from four_side_1024.d56 import index as d56_index  # noqa: E402
from four_side_1024.fslw import combine as fslw_combine  # noqa: E402
from four_side_1024.fslw import config as fslw_config  # noqa: E402
from four_side_1024.fslw import crosscheck_fslw  # noqa: E402
from four_side_1024.fslw import metrics as fslw_metrics  # noqa: E402
from four_side_1024.fslw import ports as fslw_ports  # noqa: E402
from four_side_1024.fslw import validate_fslw  # noqa: E402

# ---------------------------------------------------------------------------
# frozen configuration of this deliverable
# ---------------------------------------------------------------------------
TOPOLOGY = 'V2'
ALGORITHM = 'BASE'
PLANES = ('z1', 'z2')

PROJECT = Path(__file__).resolve().parents[2]
HIST_ROOT = PROJECT / 'outputs' / 'four_side_1024_fslw_R40_gap30_abcd'
OUT_ROOT = PROJECT / 'outputs' / 'four_side_1024_v2_candidate_rr_v01'

#: historical (read-only) source of each plane's routed geometry
SOURCE_ROUTES = {
    'z1': HIST_ROOT / 'planes' / 'V2' / 'D' / 'z1' / 'routes.json',
    'z2': HIST_ROOT / 'planes' / 'V2' / 'C' / 'z2' / 'routes.json',
}
SOURCE_ALGORITHM = {'z1': 'D', 'z2': 'C'}
EXPECTED_ROUTED = {'z1': 492, 'z2': 206}
EXPECTED_TOTAL_ROUTED = 698
ROUTES_PER_PLANE = 512
CONNECTIONS_TOTAL = 1024
V2_CSV_SHA256 = ('49dd9e89c4ea506d04638ae34eb06a0d8163d479de80869804c881ee1c43915e')
IDENTITY_FIELDS = ('route_id', 'source_endpoint', 'target_endpoint', 'pair',
                   'relation', 'source_side', 'target_side', 'source_row',
                   'target_row')

#: expected V2 ABCD totals quoted by the task (V2_C, V2_B, V2_A, V2_D)
EXPECTED_V2_ABCD_TOTALS = {'A': 681, 'B': 677, 'C': 694, 'D': 638}


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def iso_now():
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
    text = json.dumps(payload, ensure_ascii=False, indent=indent)
    path.write_text(text, encoding='utf-8')
    return path


def canonical_json(value):
    """Canonical JSON text used for the stronger byte-level equality check."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'))


def relative(path):
    path = Path(path)
    try:
        return str(path.resolve().relative_to(PROJECT.resolve()))
    except ValueError:
        return str(path)


def plane_run_dir(plane):
    return OUT_ROOT / 'planes' / TOPOLOGY / ALGORITHM / plane


def combined_run_dir():
    return OUT_ROOT / 'combined' / TOPOLOGY / ALGORITHM


def file_record(path):
    path = Path(path)
    return {'path': str(path), 'relative': relative(path),
            'exists': path.exists(),
            'bytes': path.stat().st_size if path.exists() else None,
            'sha256': sha256_file(path) if path.exists() else None}


def print_criterion(number, title, passed, details):
    print(f"[{'PASS' if passed else 'FAIL'}] C{number}: {title}")
    for key, value in details.items():
        print(f"      {key} = {value}")


def png_info(path):
    """PNG signature + IHDR dimensions (independent figure sanity check)."""
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
    return {'exists': True, 'valid_png': True, 'width': width,
            'height': height, 'bytes': path.stat().st_size}


def svg_info(path):
    """SVG root-element sanity check (independent figure sanity check)."""
    path = Path(path)
    if not path.exists():
        return {'exists': False, 'valid_svg': False}
    text = path.read_text(encoding='utf-8', errors='replace')
    stripped = text.lstrip()
    valid = (stripped.startswith('<?xml') or stripped.startswith('<svg')) \
        and '<svg' in text and '</svg>' in text
    return {'exists': True, 'valid_svg': valid,
            'bytes': path.stat().st_size}


def gds_reread(path, expected_layer_counts):
    """Re-open the two-height GDS and verify layer ownership independently."""
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
    expected = {'0': expected_layer_counts['z1'],
                '1': expected_layer_counts['z2']}
    verified = (layers == [0, 1] and datatypes == [0]
                and {str(key): value for key, value in layer_counts.items()}
                == expected)
    return {'exists': True, 'verified': bool(verified),
            'layers': layers, 'datatypes': datatypes,
            'paths_per_layer': {str(key): value
                                for key, value in layer_counts.items()},
            'path_count': len(paths),
            'top_cells': [cell.name for cell in tops],
            'bytes': path.stat().st_size}


# ---------------------------------------------------------------------------
# STEP 1-3: recombine the plane payload, write routes.json + config.json, then
#           write the authoritative strict audit exactly like scan_and_audit does
# ---------------------------------------------------------------------------
def build_plane_payload(plane):
    """Recombine one plane's payload: CSV identities + verbatim historical geometry."""
    source_path = SOURCE_ROUTES[plane]
    if not source_path.exists():
        raise FileNotFoundError(f'historical source routes.json missing: {source_path}')
    hist = load_json(source_path)
    source_sha = sha256_file(source_path)
    csv_routes, _endpoints, _connectors, validation = fslw_ports.load_plane(
        TOPOLOGY, plane)
    by_id = {route['route_id']: route for route in csv_routes}
    z_mm = fslw_config.PLANE_Z_MM[fslw_config.PLANE_ROW[plane]]

    records = []
    routed = 0
    for raw in hist['routes']:
        route_id = raw['route_id']
        if route_id not in by_id:
            raise ValueError(f'{plane}: historical route_id {route_id} not in the '
                             'frozen CSV plane')
        identity = by_id[route_id]
        record = dict(
            route_id=route_id, plane=plane, z_mm=z_mm,
            relation=identity['relation'], pair=identity['pair'],
            source_side=identity['source_side'],
            target_side=identity['target_side'],
            source_row=identity['source_row'],
            target_row=identity['target_row'],
            source_endpoint=identity['source_endpoint'],
            target_endpoint=identity['target_endpoint'],
        )
        status = str(raw.get('status') or '').strip().lower()
        if status == 'routed':
            primitives = raw.get('primitives')
            if not primitives:
                raise ValueError(f'{plane}: routed source route {route_id} has no '
                                 'primitives')
            length_mm = float(raw['length_mm'])
            record.update(
                status='routed', layer=0, length_mm=length_mm,
                length_cm=length_mm / 10.0,
                propagation_loss_db=(fslw_config.PROPAGATION_LOSS_DB_PER_CM
                                     * length_mm / 10.0),
                bend_count=raw['bend_count'], primitives=primitives,
                candidate=raw.get('candidate'))
            routed += 1
        else:
            record.update(
                status='failed',
                reason=raw.get('reason', 'not_attempted'),
                evaluated=raw.get('evaluated', 0),
                rejection_counts=raw.get('rejection_counts', {}),
                blockers=raw.get('blockers', {}))
        records.append(record)

    if len(records) != ROUTES_PER_PLANE:
        raise ValueError(f'{plane}: recombined {len(records)} records, expected '
                         f'{ROUTES_PER_PLANE}')
    if routed != EXPECTED_ROUTED[plane]:
        raise ValueError(f'{plane}: recombined {routed} routed records, expected '
                         f'{EXPECTED_ROUTED[plane]}')

    hist_statistics = hist.get('statistics') or {}
    payload = dict(
        schema='four_side_1024_fslw_plane_routes_v1',
        units='mm', layer=0,
        experiment=f'{TOPOLOGY}_{ALGORITHM}_{plane}',
        topology=TOPOLOGY, algorithm=ALGORITHM, plane=plane, z_mm=z_mm,
        port_model=fslw_config.PORT_MODEL,
        endpoint_mode='real_2x16_dual_height',
        csv_sha256=validation['csv_sha256'], csv_path=validation['csv_path'],
        process=fslw_config.process_record(),
        algorithm_detail=dict(
            name='BASE_recombined', algorithm=ALGORITHM,
            strategy=dict(
                name='history_recombine',
                source_plane=plane,
                source_algorithm=SOURCE_ALGORITHM[plane],
                source_experiment=hist.get('experiment'),
                source_routes_json=relative(source_path),
                source_routes_sha256=source_sha,
                search_performed=False,
                note=('routed primitives/candidate metadata are copied verbatim from '
                      'the historical plane solution; no routing search is run')),
            crossing_policy='strict',
            candidate_budget_per_route=None, eval_budget=None,
            time_budget_seconds=None, seed=None, ripup_rounds=0,
            search_performed=False),
        plane_validation=validation,
        provenance=dict(
            task='T1: V2 dual-height 698 combined baseline',
            kind='history_recombine',
            recombination_script='four_side_1024/v2opt/audit_baseline.py',
            source_plane=plane,
            source_algorithm=SOURCE_ALGORITHM[plane],
            source_routes_json=relative(source_path),
            source_routes_sha256=source_sha,
            source_experiment=hist.get('experiment'),
            frozen_csv=relative(validation['csv_path']),
            frozen_csv_sha256=validation['csv_sha256'],
            note=('connection identity is a zero-change projection of the frozen V2 '
                  'CSV through four_side_1024.fslw.ports.load_plane; only the routed '
                  'geometry of the two historical plane solutions is reused and it is '
                  'kept byte-identical')),
        statistics=dict(
            success_count=routed,
            failed_count=len(records) - routed,
            routed=routed,
            unrouted=len(records) - routed,
            total_connections=len(records),
            routing_rate=routed / len(records),
            source_run=dict(
                experiment=hist.get('experiment'),
                algorithm=SOURCE_ALGORITHM[plane],
                routes_json=relative(source_path),
                routes_sha256=source_sha,
                candidate_evaluations=hist_statistics.get('candidate_evaluations'),
                runtime_seconds=hist_statistics.get('runtime_seconds')),
            note=('recombined baseline; candidate_evaluations/runtime_seconds are '
                  'inherited from the historical source run, no search is executed '
                  'by this recombination')),
        routes=records)
    return payload


def build_config_record(plane, payload):
    """config.json in the same shape as fslw/run.py (plus recombination provenance)."""
    source_path = SOURCE_ROUTES[plane]
    return dict(
        experiment=payload['experiment'], topology=TOPOLOGY, algorithm=ALGORITHM,
        plane=plane, z_mm=payload['z_mm'],
        port_model=fslw_config.PORT_MODEL,
        process=fslw_config.process_record(),
        strategy=dict(name='history_recombine', algorithm=ALGORITHM,
                      search_performed=False,
                      source_plane=plane,
                      source_algorithm=SOURCE_ALGORITHM[plane],
                      source_routes_json=relative(source_path),
                      source_routes_sha256=sha256_file(source_path)),
        budget=dict(candidate_budget_per_route=None, eval_budget=None,
                    time_budget_seconds=None, ripup_rounds=0, seed=None,
                    note='no search: the plane geometry is recombined verbatim from '
                         'the historical solution'),
        main_pass=None,
        final_audit_removed=0,
        recombination=payload['provenance'],
    )


def write_strict_audit(plane):
    """Authoritative strict audit -> audit_strict.json (scan_and_audit file schema)."""
    run_dir = plane_run_dir(plane)
    routes_path = run_dir / 'routes.json'
    started = time.perf_counter()
    report = validate_fslw.build_report(
        routes_path=routes_path, policy='strict',
        expected_route_count=ROUTES_PER_PLANE)
    wall = time.perf_counter() - started
    audit = validate_fslw._compact_audit(report, 'strict')  # same file schema
    audit['wall_seconds'] = wall
    audit['routes_sha256'] = sha256_file(routes_path)
    audit['routes_size_bytes'] = routes_path.stat().st_size
    audit['routes_mtime_utc'] = time.strftime(
        '%Y-%m-%dT%H:%M:%SZ', time.gmtime(routes_path.stat().st_mtime))
    write_json(run_dir / 'audit_strict.json', audit)
    return report, audit, wall


def build_plane_artifacts(plane):
    """Write routes.json -> config.json -> audit_strict.json -> statistics.json."""
    run_dir = plane_run_dir(plane)
    run_dir.mkdir(parents=True, exist_ok=True)
    timings = {}
    started = time.perf_counter()
    payload = build_plane_payload(plane)
    write_json(run_dir / 'routes.json', payload)
    write_json(run_dir / 'config.json', build_config_record(plane, payload))
    timings['routes_and_config_seconds'] = time.perf_counter() - started
    print(f"      [{plane}] routes.json + config.json written "
          f"({len(payload['routes'])} records, {payload['statistics']['routed']} "
          f"routed) in {timings['routes_and_config_seconds']:.2f}s")

    report, audit, wall = write_strict_audit(plane)
    timings['strict_audit_seconds'] = wall
    print(f"      [{plane}] strict audit passed={report['passed']} "
          f"routed={report['routed_count']} crossings={report['crossing_count']} "
          f"({wall:.1f}s)")

    started = time.perf_counter()
    statistics = fslw_metrics.build_plane_statistics(run_dir, quiet=True)
    timings['statistics_seconds'] = time.perf_counter() - started
    print(f"      [{plane}] statistics.json audit_passed="
          f"{statistics.get('audit_passed')} "
          f"({timings['statistics_seconds']:.1f}s)")
    return dict(payload=payload, report=report, audit=audit,
                statistics=statistics, timings=timings)


# ---------------------------------------------------------------------------
# criterion 1: 512 records / frozen CSV identity / CSV sha256
# ---------------------------------------------------------------------------
def check_identity(plane):
    run_dir = plane_run_dir(plane)
    payload = load_json(run_dir / 'routes.json')
    csv_routes, _endpoints, _connectors, validation = fslw_ports.load_plane(
        TOPOLOGY, plane)
    by_id = {route['route_id']: route for route in csv_routes}
    records = payload['routes']
    mismatches = []
    checked = 0
    usage = Counter()
    for record in records:
        route_id = record['route_id']
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
        if record.get('z_mm') != payload['z_mm']:
            mismatches.append({'route_id': route_id, 'field': 'z_mm',
                               'payload': record.get('z_mm'),
                               'csv': payload['z_mm']})
        for role in ('source_endpoint', 'target_endpoint'):
            usage[record.get(role)] += 1
        checked += 1
    ids_payload = [record['route_id'] for record in records]
    ids_csv = [route['route_id'] for route in csv_routes]
    statuses = Counter(record.get('status') for record in records)
    csv_path = Path(validation['csv_path'])
    csv_sha = sha256_file(csv_path)
    result = dict(
        plane=plane,
        record_count=len(records),
        expected_record_count=ROUTES_PER_PLANE,
        records_identity_checked=checked,
        identity_field_mismatch_count=len(mismatches),
        identity_field_mismatches=mismatches[:10],
        route_id_order_matches_csv=(ids_payload == ids_csv),
        csv_path=str(csv_path),
        csv_sha256=csv_sha,
        csv_sha256_expected=V2_CSV_SHA256,
        csv_sha256_matches_expected=(csv_sha.lower() == V2_CSV_SHA256),
        payload_csv_sha256=payload.get('csv_sha256'),
        payload_csv_sha256_matches_expected=(
            str(payload.get('csv_sha256', '')).lower() == V2_CSV_SHA256),
        plane_validation_passed=validation['passed'],
        plane_validation_issues=validation['issues'],
        status_counts=dict(statuses),
        routed=statuses.get('routed', 0),
        expected_routed=EXPECTED_ROUTED[plane],
        ports_used_unique=len(usage),
        ports_used_once=(len(usage) == 1024 and set(usage.values()) == {1}),
    )
    result['passed'] = (
        result['record_count'] == ROUTES_PER_PLANE
        and result['identity_field_mismatch_count'] == 0
        and result['route_id_order_matches_csv']
        and result['csv_sha256_matches_expected']
        and result['payload_csv_sha256_matches_expected']
        and result['plane_validation_passed']
        and result['routed'] == EXPECTED_ROUTED[plane]
        and result['ports_used_once'])
    return result


# ---------------------------------------------------------------------------
# criterion 2: routed primitives deep/byte equal to the historical files
# ---------------------------------------------------------------------------
def check_primitives(plane):
    payload = load_json(plane_run_dir(plane) / 'routes.json')
    source_path = SOURCE_ROUTES[plane]
    hist = load_json(source_path)
    hist_by_id = {record['route_id']: record for record in hist['routes']}
    routed = [record for record in payload['routes']
              if record.get('status') == 'routed']
    hist_routed = [record for record in hist['routes']
                   if str(record.get('status', 'routed')).lower() == 'routed']
    mismatches = []
    deep_equal = 0
    canonical_equal = 0
    for record in routed:
        route_id = record['route_id']
        source = hist_by_id.get(route_id)
        if source is None or source.get('status') != 'routed':
            mismatches.append({'route_id': route_id,
                               'kind': 'missing_in_history'})
            continue
        left = record.get('primitives')
        right = source.get('primitives')
        if left == right:
            deep_equal += 1
        else:
            mismatches.append({'route_id': route_id,
                               'kind': 'primitives_not_deep_equal'})
        if canonical_json(left) == canonical_json(right):
            canonical_equal += 1
        else:
            mismatches.append({'route_id': route_id,
                               'kind': 'primitives_not_byte_equal'})
        if record.get('length_mm') != source.get('length_mm'):
            mismatches.append({'route_id': route_id,
                               'kind': 'length_mm_mismatch',
                               'payload': record.get('length_mm'),
                               'history': source.get('length_mm')})
        if record.get('bend_count') != source.get('bend_count'):
            mismatches.append({'route_id': route_id,
                               'kind': 'bend_count_mismatch',
                               'payload': record.get('bend_count'),
                               'history': source.get('bend_count')})
    routed_ids = {record['route_id'] for record in routed}
    hist_routed_ids = {record['route_id'] for record in hist_routed}
    statuses_payload = Counter(record.get('status') for record in payload['routes'])
    statuses_hist = Counter(str(record.get('status', 'routed')).lower()
                            for record in hist['routes'])
    result = dict(
        plane=plane,
        source_routes_json=relative(source_path),
        source_routes_sha256=sha256_file(source_path),
        source_experiment=hist.get('experiment'),
        routed_count=len(routed),
        expected_routed_count=EXPECTED_ROUTED[plane],
        historical_routed_count=len(hist_routed),
        primitives_deep_equal_count=deep_equal,
        primitives_byte_equal_count=canonical_equal,
        primitive_mismatch_count=len(mismatches),
        primitive_mismatches=mismatches[:10],
        routed_id_sets_equal=(routed_ids == hist_routed_ids),
        status_counts_payload=dict(statuses_payload),
        status_counts_history=dict(statuses_hist),
        status_counts_equal=(statuses_payload == statuses_hist),
    )
    result['passed'] = (
        result['routed_count'] == EXPECTED_ROUTED[plane]
        and result['historical_routed_count'] == EXPECTED_ROUTED[plane]
        and result['primitives_deep_equal_count'] == result['routed_count']
        and result['primitives_byte_equal_count'] == result['routed_count']
        and result['primitive_mismatch_count'] == 0
        and result['routed_id_sets_equal']
        and result['status_counts_equal'])
    return result


# ---------------------------------------------------------------------------
# criterion 3: strict authoritative audit per plane
# ---------------------------------------------------------------------------
def check_audit(plane, report, audit, wall):
    run_dir = plane_run_dir(plane)
    routes_path = run_dir / 'routes.json'
    audit_path = run_dir / 'audit_strict.json'
    routes_sha = sha256_file(routes_path)
    audit_payload = load_json(audit_path)
    structure = report.get('structure') or {}
    result = dict(
        plane=plane,
        audit_file=str(audit_path),
        validator=report.get('validator'),
        policy_used=report.get('policy_used'),
        passed=report.get('passed'),
        route_count=report.get('route_count'),
        routed_count=report.get('routed_count'),
        expected_routed=EXPECTED_ROUTED[plane],
        failed_status_count=report.get('failed_status_count'),
        d56_checked_count=report.get('d56_checked_count'),
        d56_passed_count=report.get('d56_passed_count'),
        d56_failed_count=report.get('d56_failed_count'),
        crossing_count=report.get('crossing_count'),
        crossing_pair_count=report.get('crossing_pair_count'),
        violation_pair_count=report.get('violation_pair_count'),
        spacing_violation_pairs=report.get('spacing_violation_pairs'),
        overlap_pairs=report.get('overlap_pairs'),
        touch_pairs=report.get('touch_pairs'),
        crossing_window_overlap_pairs=report.get(
            'crossing_window_overlap_pairs'),
        double_cross_pairs=report.get('double_cross_pairs'),
        crossing_window_excessive_pairs=report.get(
            'crossing_window_excessive_pairs'),
        self_intersections=report.get('self_intersections'),
        self_overlaps=report.get('self_overlaps'),
        self_spacing_violations=report.get('self_spacing_violations'),
        radius_violations=report.get('radius_violations'),
        boundary_violations=report.get('boundary_violations'),
        diagonal_line_violations=report.get('diagonal_line_violations'),
        free_or_short_s_arc_violations=report.get(
            'free_or_short_s_arc_violations'),
        small_angle_crossing_count=report.get('small_angle_crossing_count'),
        min_non_crossing_centerline_mm=report.get(
            'min_non_crossing_centerline_mm'),
        process_radius_mm=(report.get('process') or {}).get('radius_mm'),
        process_clearance_mm=(report.get('process') or {}).get(
            'centerline_clearance_mm'),
        parameters_source=(report.get('process') or {}).get(
            'parameters_source'),
        structure_checked=structure.get('checked'),
        structure=structure,
        errors=report.get('errors'),
        warnings=report.get('warnings'),
        wall_seconds=wall,
        routes_path=str(routes_path),
        routes_sha256=routes_sha,
        audit_routes_sha256=audit_payload.get('routes_sha256'),
        audit_routes_sha256_matches=(audit_payload.get('routes_sha256')
                                     == routes_sha),
        compact_audit_matches_runtime_report=(
            audit_payload.get('passed') == report.get('passed')),
    )
    result['passed'] = (
        report.get('passed') is True
        and not report.get('errors')
        and result['d56_failed_count'] == 0
        and result['routed_count'] == EXPECTED_ROUTED[plane]
        and result['route_count'] == ROUTES_PER_PLANE
        and result['structure_checked'] is True
        and result['violation_pair_count'] == 0
        and result['audit_routes_sha256_matches']
        and result['process_radius_mm'] == 40.0
        and abs(float(result['process_clearance_mm']) - 0.08) < 1e-12)
    return result


# ---------------------------------------------------------------------------
# criterion 4: statistics.json from metrics.build_plane_statistics
# ---------------------------------------------------------------------------
def check_statistics(plane, statistics):
    run_dir = plane_run_dir(plane)
    statistics_path = run_dir / 'statistics.json'
    audit_path = run_dir / 'audit_strict.json'
    payload_statistics = load_json(statistics_path)
    source_block = payload_statistics.get('source') or {}
    audit_meta = source_block.get('audit') or {}
    audit_payload = load_json(audit_path)
    result = dict(
        plane=plane,
        statistics_file=str(statistics_path),
        schema=payload_statistics.get('schema'),
        experiment=payload_statistics.get('experiment'),
        routed=payload_statistics.get('routed'),
        expected_routed=EXPECTED_ROUTED[plane],
        unrouted=payload_statistics.get('unrouted'),
        connections_total=payload_statistics.get('connections_total'),
        routing_rate=payload_statistics.get('routing_rate'),
        expected_routing_rate=EXPECTED_ROUTED[plane] / ROUTES_PER_PLANE,
        audit_passed=payload_statistics.get('audit_passed'),
        audit_policy=payload_statistics.get('audit_policy'),
        audit_routed_count=payload_statistics.get('audit_routed_count'),
        audit_checked_count=payload_statistics.get('audit_checked_count'),
        audit_passed_count=payload_statistics.get('audit_passed_count'),
        audit_failed_count=payload_statistics.get('audit_failed_count'),
        audit_error_count=payload_statistics.get('audit_error_count'),
        audit_violation_count=payload_statistics.get('audit_violation_count'),
        total_violation_count=payload_statistics.get('total_violation_count'),
        crossing_count=payload_statistics.get('crossing_count'),
        audit_crossing_window_count=payload_statistics.get(
            'audit_crossing_window_count'),
        audit_source_status=audit_meta.get('status'),
        audit_source_file=audit_meta.get('file'),
        audit_sha256=source_block.get('audit_sha256'),
        audit_file_sha256=sha256_file(audit_path),
        routes_sha256=source_block.get('routes_sha256'),
        routes_file_sha256=sha256_file(run_dir / 'routes.json'),
        audit_merged_from_file=(
            audit_meta.get('status') == 'merged'
            and str(audit_meta.get('file')).endswith('audit_strict.json')),
        audit_values_from_file=(
            audit_payload.get('passed') is True
            and payload_statistics.get('audit_passed') is True),
        notes=payload_statistics.get('notes'),
    )
    result['passed'] = (
        payload_statistics.get('audit_passed') is True
        and result['audit_merged_from_file']
        and result['audit_sha256'] == result['audit_file_sha256']
        and result['routes_sha256'] == result['routes_file_sha256']
        and result['routed'] == EXPECTED_ROUTED[plane]
        and result['audit_violation_count'] == 0
        and result['total_violation_count'] == 0
        and result['crossing_count'] == payload_statistics.get(
            'crossing_count_recomputed'))
    return result


# ---------------------------------------------------------------------------
# criterion 5: combined 1024-channel build
# ---------------------------------------------------------------------------
def check_combine(plane_artifacts):
    combined_dir = combined_run_dir()
    routes_path = combined_dir / 'routes_1024.json'
    statistics_path = combined_dir / 'statistics.json'
    summary_path = combined_dir / 'planes_summary.json'
    files = {
        'routes_1024.json': routes_path,
        'statistics.json': statistics_path,
        'planes_summary.json': summary_path,
        'layer_2d.png': combined_dir / 'layer_2d.png',
        'layer_2d.svg': combined_dir / 'layer_2d.svg',
        'overlay_3d.png': combined_dir / 'overlay_3d.png',
        'routing_1024_two_height.gds': (
            combined_dir / 'routing_1024_two_height.gds'),
    }
    payload = load_json(routes_path)
    statistics = load_json(statistics_path)
    summary = load_json(summary_path)
    records = payload['routes']
    statuses = Counter(record.get('status') for record in records)
    routed_records = [record for record in records
                      if str(record.get('status', 'routed')).lower() == 'routed']
    by_plane = Counter(record.get('plane') for record in routed_records)
    ids = [record.get('route_id') for record in records]
    violations = statistics.get('violations') or {}
    gds = ((summary.get('gds') or {}).get('combined') or {})
    figure_block = summary.get('figures') or {}
    layer_2d = figure_block.get('layer_2d_png') or {}
    overlay_3d = figure_block.get('overlay_3d_png') or {}
    plane_blocks = payload.get('plane_summaries') or {}
    plane_crossings = {
        plane: (plane_artifacts[plane]['statistics'].get('crossing_count'))
        for plane in PLANES}
    expected_crossings = sum(value for value in plane_crossings.values()
                             if value is not None)
    per_plane_violation_fields = {}
    for plane in PLANES:
        stats = plane_artifacts[plane]['statistics']
        per_plane_violation_fields[plane] = {
            field: stats.get(field) for field in (
                'spacing_violation_pairs', 'overlap_pairs', 'touch_pairs',
                'crossing_window_overlap_pairs', 'double_cross_pairs',
                'crossing_window_excessive_pairs', 'self_intersections',
                'self_overlaps', 'self_spacing_violations', 'radius_violations',
                'boundary_violations', 'diagonal_line_violations',
                'free_arc_violations', 'total_violation_count')}
    plane_vectors = {}
    for plane in PLANES:
        plane_dir = plane_run_dir(plane)
        plane_vectors[plane] = {
            'routing_all.gds': file_record(plane_dir / 'routing_all.gds'),
            'routing_all.svg': file_record(plane_dir / 'routing_all.svg'),
        }
    gds_path = files['routing_1024_two_height.gds']
    independent_gds = gds_reread(
        gds_path, expected_layer_counts=EXPECTED_ROUTED) if gds_path.exists() \
        else {'exists': False, 'verified': False}
    figure_integrity = {
        'layer_2d_png': png_info(files['layer_2d.png']),
        'overlay_3d_png': png_info(files['overlay_3d.png']),
        'layer_2d_svg': svg_info(files['layer_2d.svg']),
    }
    csv_union_ids = set()
    for plane in PLANES:
        csv_routes, _endpoints, _connectors, _validation = \
            fslw_ports.load_plane(TOPOLOGY, plane)
        csv_union_ids.update(route['route_id'] for route in csv_routes)
    result = dict(
        combined_dir=str(combined_dir),
        files={name: file_record(path) for name, path in files.items()},
        plane_vectors=plane_vectors,
        routes_1024_records=len(records),
        routes_1024_unique_route_ids=len(set(ids)),
        routed_total=statuses.get('routed', 0),
        failed_total=statuses.get('failed', 0),
        routed_by_plane=dict(by_plane),
        expected_routed_total=EXPECTED_TOTAL_ROUTED,
        expected_routed_by_plane=dict(EXPECTED_ROUTED),
        statistics_routed=statistics.get('routed'),
        statistics_unrouted=statistics.get('unrouted'),
        connections_total=statistics.get('connections_total'),
        routing_rate=statistics.get('routing_rate'),
        expected_routing_rate=EXPECTED_TOTAL_ROUTED / CONNECTIONS_TOTAL,
        audit_passed_all_planes=statistics.get('audit_passed_all_planes'),
        same_plane_crossings=statistics.get('same_plane_crossings'),
        plane_crossing_counts=plane_crossings,
        same_plane_crossings_expected=expected_crossings,
        violations=violations,
        same_plane_violation_total=violations.get('same_plane_total'),
        violations_complete=violations.get('complete'),
        per_plane_violation_fields=per_plane_violation_fields,
        same_plane_legacy_violations=violations.get('same_plane_total'),
        same_plane_legacy_note=(
            'combined audit statement: `violations.same_plane_total` merges the '
            'authoritative strict audit counters of both planes (legacy-compatible '
            'field schema); value 0 = no same-plane violation in either height plane'),
        gds_verified=gds.get('verified'),
        gds_layers=gds.get('layers'),
        gds_datatypes=gds.get('datatypes'),
        gds_paths_per_layer=gds.get('paths_per_layer'),
        gds_layer_documentation=gds.get('layer_documentation'),
        gds_file_exists=files['routing_1024_two_height.gds'].exists(),
        independent_gds_reread=independent_gds,
        figure_integrity=figure_integrity,
        routes_1024_route_ids_cover_csv=(set(ids) == csv_union_ids),
        figures={
            'layer_2d_png': layer_2d,
            'overlay_3d_png': overlay_3d,
            'layer_2d_png_exists': files['layer_2d.png'].exists(),
            'layer_2d_svg_exists': files['layer_2d.svg'].exists(),
            'overlay_3d_png_exists': files['overlay_3d.png'].exists(),
        },
        plane_summaries={
            plane: {
                'routes_json': (plane_blocks.get(plane) or {}).get('routes_json'),
                'routed': (plane_blocks.get(plane) or {}).get('routed'),
                'z_mm': (plane_blocks.get(plane) or {}).get('z_mm'),
            } for plane in PLANES},
        combined_summary=(summary.get('combined') or {}),
    )
    expected_paths = {
        'z1': EXPECTED_ROUTED['z1'],
        'z2': EXPECTED_ROUTED['z2'],
    }
    result['passed'] = (
        result['routes_1024_records'] == CONNECTIONS_TOTAL
        and result['routes_1024_unique_route_ids'] == CONNECTIONS_TOTAL
        and result['routed_total'] == EXPECTED_TOTAL_ROUTED
        and result['routed_by_plane'] == expected_paths
        and result['statistics_routed'] == EXPECTED_TOTAL_ROUTED
        and result['statistics_unrouted'] == (CONNECTIONS_TOTAL
                                              - EXPECTED_TOTAL_ROUTED)
        and result['connections_total'] == CONNECTIONS_TOTAL
        and result['routing_rate'] == EXPECTED_TOTAL_ROUTED / CONNECTIONS_TOTAL
        and result['audit_passed_all_planes'] is True
        and result['violations_complete'] is True
        and result['same_plane_violation_total'] == 0
        and result['same_plane_crossings'] == expected_crossings
        and result['gds_verified'] is True
        and result['gds_layers'] == [0, 1]
        and result['gds_datatypes'] == [0]
        and result['gds_paths_per_layer'] == {'0': EXPECTED_ROUTED['z1'],
                                              '1': EXPECTED_ROUTED['z2']}
        and result['gds_file_exists']
        and result['independent_gds_reread'].get('verified') is True
        and result['independent_gds_reread'].get('layers') == [0, 1]
        and result['routes_1024_route_ids_cover_csv']
        and all(item.get('valid_png') is True for key, item
                in figure_integrity.items() if key.endswith('_png'))
        and figure_integrity['layer_2d_svg'].get('valid_svg') is True
        and result['figures']['layer_2d_png_exists']
        and result['figures']['layer_2d_svg_exists']
        and result['figures']['overlay_3d_png_exists']
        and all(record['exists'] and record['bytes'] for plane in PLANES
                for record in plane_vectors[plane].values())
        and all((plane_blocks.get(plane) or {}).get('routed')
                == EXPECTED_ROUTED[plane] for plane in PLANES))
    return result


# ---------------------------------------------------------------------------
# criterion 6a: independent D56 index rebuild + per-route leave-one-out exclude
# ---------------------------------------------------------------------------
def d56_leave_one_out_selfcheck(plane):
    payload = load_json(plane_run_dir(plane) / 'routes.json')
    routed = [record for record in payload['routes']
              if record.get('status') == 'routed']
    index = d56_index.D56Index(width=fslw_config.WIDTH_MM,
                               gap=fslw_config.EDGE_GAP_MM,
                               crossing_policy='strict')
    prepared = {}
    started = time.perf_counter()
    for record in routed:
        route_id = record['route_id']
        prepared[route_id] = d56_index.prepare(record['primitives'])
        index.add(route_id, prepared[route_id])
    index_seconds = time.perf_counter() - started
    route_ids = list(prepared)
    violations = []
    reasons = Counter()
    crossing_events = 0
    started = time.perf_counter()
    for route_id in route_ids:
        index.remove(route_id)
        evaluation = index.evaluate(prepared[route_id])
        if evaluation.valid:
            reasons['valid'] += 1
            crossing_events += len(evaluation.crossings)
        else:
            reasons[str(evaluation.reason)] += 1
            violations.append({
                'route_id': route_id,
                'reason': evaluation.reason,
                'blockers': list(evaluation.blockers)[:5],
                'min_spacing_mm': evaluation.min_spacing_mm,
            })
        index.add(route_id, prepared[route_id])
    evaluate_seconds = time.perf_counter() - started
    total_crossings = crossing_events // 2 if crossing_events % 2 == 0 else None
    report = None
    report_path = plane_run_dir(plane) / 'audit_strict.json'
    if report_path.exists():
        report = load_json(report_path)
    result = dict(
        plane=plane,
        engine='four_side_1024.d56.index.D56Index',
        configuration=dict(width_mm=fslw_config.WIDTH_MM,
                           gap_mm=fslw_config.EDGE_GAP_MM,
                           centerline_clearance_mm=fslw_config.CLEARANCE_MM,
                           crossing_policy='strict',
                           sagitta_mm=fslw_config.SAGITTA_MM),
        routed_route_count=len(routed),
        indexed_route_count=len(index.routes),
        leave_one_out_checked=sum(reasons.values()),
        valid_route_count=reasons.get('valid', 0),
        violation_count=len(violations),
        reasons=dict(reasons),
        violations=violations[:10],
        crossing_events_sum=crossing_events,
        crossing_count_round_trip=total_crossings,
        validator_crossing_count=(report or {}).get('crossing_count'),
        crossing_count_matches_validator=(
            total_crossings is not None
            and (report or {}).get('crossing_count') == total_crossings),
        crossed_direction_count_even=(crossing_events % 2 == 0),
        index_seconds=index_seconds,
        evaluate_seconds=evaluate_seconds,
    )
    result['passed'] = (
        result['routed_route_count'] == EXPECTED_ROUTED[plane]
        and result['indexed_route_count'] == EXPECTED_ROUTED[plane]
        and result['leave_one_out_checked'] == EXPECTED_ROUTED[plane]
        and result['violation_count'] == 0
        and result['valid_route_count'] == EXPECTED_ROUTED[plane])
    return result


# ---------------------------------------------------------------------------
# criterion 6b: router-index vs authoritative-validator pair verdict crosscheck
# ---------------------------------------------------------------------------
def crosscheck_plane(plane):
    routes_path = plane_run_dir(plane) / 'routes.json'
    started = time.perf_counter()
    summary = crosscheck_fslw.crosscheck(routes_path, plane=plane)
    wall = time.perf_counter() - started
    result = dict(
        plane=plane,
        tool='four_side_1024.fslw.crosscheck_fslw.crosscheck',
        routes_file=str(routes_path),
        routes_sha256=summary.get('routes_sha256'),
        compared_pair_count=summary.get('compared_pair_count'),
        mismatch_count=summary.get('mismatch_count'),
        validator_invalid_pairs=summary.get('validator_invalid_pairs'),
        router_invalid_pairs=summary.get('router_invalid_pairs'),
        strict_failed_route_count=summary.get('strict_failed_route_count'),
        validator_passed_route_count=summary.get(
            'validator_passed_route_count'),
        router_passed_route_count=summary.get('router_passed_route_count'),
        crossing_count=summary.get('crossing_count'),
        window_consistency=summary.get('window_consistency'),
        roles=summary.get('roles'),
        process=summary.get('process'),
        passed=summary.get('passed'),
        wall_seconds=wall,
    )
    result['agrees_with_authoritative_validator'] = (
        result['passed'] is True
        and result['mismatch_count'] == 0
        and result['strict_failed_route_count'] == 0
        and (result['crossing_count'] or {}).get('matches') is True
        and (result['window_consistency'] or {}).get('count_matches') is True)
    result['passed'] = bool(result['agrees_with_authoritative_validator'])
    return result


# ---------------------------------------------------------------------------
# criterion 7: eight historical ABCD groups vs the 698 baseline
# ---------------------------------------------------------------------------
def build_abcd_comparison():
    rows = []
    problems = []
    for topology in ('V1', 'V2'):
        for algorithm in ('A', 'B', 'C', 'D'):
            combined_statistics = (
                HIST_ROOT / 'combined' / topology / algorithm / 'statistics.json')
            if not combined_statistics.exists():
                problems.append(f'missing {relative(combined_statistics)}')
                continue
            statistics = load_json(combined_statistics)
            by_plane = {plane: (statistics.get('by_plane') or {}).get(
                plane, {}).get('routed') for plane in PLANES}
            plane_files = {}
            for plane in PLANES:
                plane_stats = (HIST_ROOT / 'planes' / topology / algorithm
                               / plane / 'statistics.json')
                plane_files[plane] = relative(plane_stats)
                if plane_stats.exists():
                    plane_payload = load_json(plane_stats)
                    if plane_payload.get('routed') != by_plane[plane]:
                        problems.append(
                            f'{topology}_{algorithm}_{plane}: plane statistics '
                            f'routed {plane_payload.get("routed")} != combined '
                            f'by_plane {by_plane[plane]}')
            routed_total = statistics.get('routed')
            if routed_total != (by_plane['z1'] or 0) + (by_plane['z2'] or 0):
                problems.append(f'{topology}_{algorithm}: total mismatch')
            violations = statistics.get('violations') or {}
            rows.append(dict(
                group=f'{topology}_{algorithm}',
                topology=topology, algorithm=algorithm,
                z1_routed=by_plane['z1'], z2_routed=by_plane['z2'],
                routed_total=routed_total,
                routing_rate=statistics.get('routing_rate'),
                routing_rate_text=f'{routed_total}/1024',
                same_plane_crossings=statistics.get('same_plane_crossings'),
                same_plane_violations=violations.get('same_plane_total'),
                audit_passed_all_planes=statistics.get(
                    'audit_passed_all_planes'),
                combined_statistics_json=relative(combined_statistics),
                plane_statistics_json=plane_files,
            ))
    v2_totals = {row['algorithm']: row['routed_total'] for row in rows
                 if row['topology'] == 'V2'}
    reference_ok = v2_totals == EXPECTED_V2_ABCD_TOTALS
    best = max(rows, key=lambda row: row['routed_total']) if rows else None
    baseline_row = next((row for row in rows if row['group'] == 'V2_B'), None)
    comparison = []
    for row in rows:
        comparison.append(dict(
            group=row['group'],
            z1_routed=row['z1_routed'], z2_routed=row['z2_routed'],
            routed_total=row['routed_total'],
            routing_rate=round(row['routed_total'] / CONNECTIONS_TOTAL, 12),
            delta_vs_698=routed_total_delta(row['routed_total']),
            audit_passed_all_planes=row['audit_passed_all_planes'],
            combined_statistics_json=row['combined_statistics_json'],
        ))
    result = dict(
        rows=rows,
        comparison_table=comparison,
        eight_group_count=len(rows),
        v2_abcd_totals=v2_totals,
        expected_v2_abcd_totals=EXPECTED_V2_ABCD_TOTALS,
        v2_reference_numbers_match=reference_ok,
        best_historical_group=(best or {}).get('group'),
        best_historical_routed=(best or {}).get('routed_total'),
        baseline_group='V2_BASE (z1=492 from V2_D, z2=206 from V2_C)',
        baseline_698=EXPECTED_TOTAL_ROUTED,
        baseline_routing_rate=EXPECTED_TOTAL_ROUTED / CONNECTIONS_TOTAL,
        delta_vs_best_historical=(
            EXPECTED_TOTAL_ROUTED - best['routed_total'] if best else None),
        delta_vs_v2_default_B=(
            EXPECTED_TOTAL_ROUTED - baseline_row['routed_total']
            if baseline_row else None),
        problems=problems,
    )
    result['passed'] = (
        len(rows) == 8
        and not problems
        and reference_ok
        and EXPECTED_TOTAL_ROUTED > best['routed_total'])
    return result


def routed_total_delta(historical_total):
    return EXPECTED_TOTAL_ROUTED - historical_total


# ---------------------------------------------------------------------------
# README / reproduction notes
# ---------------------------------------------------------------------------
README_TEXT = """# V2 dual-height 698-channel BASE baseline (T1) - reproduction

Recombined 1024-channel baseline for the FSLW R=40 mm / edge-gap 0.030 mm
process: plane z1 = 492 opposite connections, plane z2 = 206 adjacent
connections, 698/1024 routed (68.1640625%).

## Provenance (read-only historical inputs, nothing modified)

| plane | source routes.json | original algorithm | routed |
|---|---|---|---|
| z1 | `outputs/four_side_1024_fslw_R40_gap30_abcd/planes/V2/D/z1/routes.json` | D | 492 |
| z2 | `outputs/four_side_1024_fslw_R40_gap30_abcd/planes/V2/C/z2/routes.json` | C | 206 |

The routed primitives/lengths/bends/candidate metadata are copied verbatim (a
JSON deep-equality check against the historical files is part of the
acceptance).  Connection identities are rebuilt as a zero-change projection of
the frozen V2 CSV through `four_side_1024.fslw.ports.load_plane('V2', plane)`.
No routing search is run and no geometry of the historical solutions is edited.

## Reproduce

Run from `OpticalWaveguideRouter2D`:

```bat
cd "C:\\Users\\lihao\\Desktop\\Graduation Project\\OpticalWaveguideRouter2D"
.venv\\Scripts\\python.exe four_side_1024\\v2opt\\audit_baseline.py
.venv\\Scripts\\python.exe -m pytest four_side_1024\\v2opt\\tests -q
```

The script rebuilds, idempotently:

* `planes/V2/BASE/z1/{routes.json, config.json, audit_strict.json, statistics.json}`
* `planes/V2/BASE/z2/{routes.json, config.json, audit_strict.json, statistics.json}`
* `combined/V2/BASE/` via `four_side_1024.fslw.combine.build_combined(root,'V2','BASE')`
  (`routes_1024.json`, `statistics.json`, `planes_summary.json`,
  `routing_1024_two_height.gds`, `layer_2d.png/.svg`, `overlay_3d.png`, plus the
  per-plane `routing_all.gds/.svg`)
* `baseline_acceptance.json` - all seven T1 criteria with real numbers and PASS/FAIL
* this `baseline_reproduce.md`

## Acceptance gates (all must be true)

1. 512 records per plane, identity fields identical to the frozen V2 CSV,
   CSV sha256 = 49dd9e89c4ea506d04638ae34eb06a0d8163d479de80869804c881ee1c43915e.
2. routed primitives byte-equal (JSON deep equality) to the historical files, 492/206.
3. `four_side_1024.fslw.validate_fslw` strict policy passed=True per plane
   (`audit_strict.json` includes the routes sha256).
4. `four_side_1024.fslw.metrics.build_plane_statistics` -> statistics.json with
   `audit_passed=True` merged from `audit_strict.json`.
5. `four_side_1024.fslw.combine.build_combined` -> 698 routed, routing_rate
   698/1024, dual-height GDS (layer 0 = z1, layer 1 = z2) and figures generated,
   combined audit declares 0 same-plane violations.
6. Independent recomputation: `four_side_1024.d56.index.D56Index`
   (width=0.05 mm, gap=0.03 mm, crossing_policy='strict') rebuild + per-route
   leave-one-out exclude self-check -> zero violations; `fslw.crosscheck_fslw`
   router-vs-validator pair-verdict agreement (0 mismatches).
7. Comparison of the eight historical V1/V2 x A/B/C/D groups (694/677/681/638
   for V2) against the 698 recombination.

`baseline_acceptance.json` is the machine-readable verdict; the script exits 0
only when every criterion passes.
"""


def write_readme():
    path = OUT_ROOT / 'baseline_reproduce.md'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(README_TEXT, encoding='utf-8')
    return path


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(
        description='T1: recombine the historical two-plane V2 solution into the '
                    '698-channel BASE baseline and audit it independently.')
    parser.add_argument('--quiet-combine', action='store_true',
                        help='suppress the combine module progress printing')
    parser.add_argument('--skip-independent', action='store_true',
                        help='debug only: skip criterion 6 (independent '
                             'recomputation); the acceptance then fails')
    parser.add_argument('--output-root', type=Path, default=None,
                        help='override the v01 output root (debug only)')
    args = parser.parse_args(argv)

    global OUT_ROOT
    if args.output_root is not None:
        OUT_ROOT = Path(args.output_root)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    total_started = time.perf_counter()
    print('=' * 78)
    print('T1: V2 dual-height recombined BASE baseline + independent audit')
    print(f'project      : {PROJECT_ROOT}')
    print(f'output root  : {OUT_ROOT}')
    print(f'historical   : {HIST_ROOT}')
    print('=' * 78)

    # ---------------------------------------------------------------- step 1-4
    print('[build] recombine plane payloads, strict audits and plane statistics')
    plane_artifacts = {}
    for plane in PLANES:
        print(f'  plane {plane}: source {relative(SOURCE_ROUTES[plane])} '
              f'(algorithm {SOURCE_ALGORITHM[plane]})')
        plane_artifacts[plane] = build_plane_artifacts(plane)

    # ----------------------------------------------------------------- step 5
    print('[build] combined 1024-channel layout via combine.build_combined')
    for plane in PLANES:
        plane_dir = plane_run_dir(plane)
        for name in ('routing_all.gds', 'routing_all.svg'):
            stale = plane_dir / name
            if stale.exists():
                stale.unlink()
    combine_started = time.perf_counter()
    combined_path = fslw_combine.build_combined(
        OUT_ROOT, TOPOLOGY, ALGORITHM, quiet=args.quiet_combine)
    combine_seconds = time.perf_counter() - combine_started
    print(f'      combined dir: {combined_path} ({combine_seconds:.1f}s)')

    # ----------------------------------------------------------- acceptance run
    criteria = []

    checks = {plane: check_identity(plane) for plane in PLANES}
    c1_passed = all(checks[plane]['passed'] for plane in PLANES)
    criteria.append(dict(
        criterion_id=1,
        name='512 records/plane, connection identity identical to frozen V2 CSV, '
             'V2 CSV sha256',
        passed=c1_passed,
        evidence={plane: checks[plane] for plane in PLANES}))

    primitives = {plane: check_primitives(plane) for plane in PLANES}
    c2_passed = all(primitives[plane]['passed'] for plane in PLANES)
    criteria.append(dict(
        criterion_id=2,
        name='routed primitives JSON-deep-equal (canonical byte-equal) to the '
             'historical files, 492/206',
        passed=c2_passed,
        evidence={plane: primitives[plane] for plane in PLANES}))

    audits = {plane: check_audit(
        plane, plane_artifacts[plane]['report'], plane_artifacts[plane]['audit'],
        plane_artifacts[plane]['timings']['strict_audit_seconds'])
        for plane in PLANES}
    c3_passed = all(audits[plane]['passed'] for plane in PLANES)
    criteria.append(dict(
        criterion_id=3,
        name='validate_fslw strict authoritative audit passed=True per plane '
             '(audit_strict.json with routes sha256)',
        passed=c3_passed,
        evidence={plane: audits[plane] for plane in PLANES}))

    statistics_checks = {plane: check_statistics(
        plane, plane_artifacts[plane]['statistics']) for plane in PLANES}
    c4_passed = all(statistics_checks[plane]['passed'] for plane in PLANES)
    criteria.append(dict(
        criterion_id=4,
        name='metrics.build_plane_statistics statistics.json with '
             'audit_passed=True merged from audit_strict.json',
        passed=c4_passed,
        evidence={plane: statistics_checks[plane] for plane in PLANES}))

    combined = check_combine(plane_artifacts)
    combined['build_seconds'] = combine_seconds
    combined['builder'] = 'four_side_1024.fslw.combine.build_combined(root, '
    combined['builder'] += f"'{TOPOLOGY}', '{ALGORITHM}')"
    criteria.append(dict(
        criterion_id=5,
        name='combine.build_combined -> 698 routed (z1=492,z2=206), routing_rate '
             '698/1024, dual-height GDS/figures, combined audit same-plane '
             'violations=0',
        passed=combined['passed'],
        evidence=combined))

    independent = {}
    c6_passed = False
    if args.skip_independent:
        independent['skipped'] = True
        independent['note'] = '--skip-independent (debug): criterion not executed'
    else:
        selfchecks = {plane: d56_leave_one_out_selfcheck(plane)
                      for plane in PLANES}
        crosschecks = {plane: crosscheck_plane(plane) for plane in PLANES}
        c6_passed = (all(selfchecks[plane]['passed'] for plane in PLANES)
                     and all(crosschecks[plane]['passed'] for plane in PLANES))
        independent = {
            'd56_index_selfcheck': selfchecks,
            'crosscheck_fslw': crosschecks,
            'd56_configuration': dict(width_mm=fslw_config.WIDTH_MM,
                                      gap_mm=fslw_config.EDGE_GAP_MM,
                                      clearance_mm=fslw_config.CLEARANCE_MM,
                                      crossing_policy='strict'),
            'note': ('D56Index rebuild + per-route leave-one-out exclude check of '
                     'both recombined plane layouts; crosscheck_fslw compares the '
                     'router index pair verdicts with the authoritative validate_fslw '
                     'verdicts on every candidate route pair'),
        }
    criteria.append(dict(
        criterion_id=6,
        name='independent recomputation: D56Index rebuild + leave-one-out exclude '
             'zero violations; crosscheck_fslw agrees with validate_fslw',
        passed=c6_passed,
        evidence=independent))

    abcd = build_abcd_comparison()
    criteria.append(dict(
        criterion_id=7,
        name='eight historical V1/V2 x A/B/C/D groups vs the 698 recombination',
        passed=abcd['passed'],
        evidence=abcd))

    # ------------------------------------------------------------------ verdict
    write_readme()  # written before the acceptance record so its hash is recorded
    all_passed = all(criterion['passed'] for criterion in criteria)
    combined_routed = combined['statistics_routed']
    acceptance = dict(
        schema='four_side_1024_v2_candidate_rr_v01_baseline_acceptance_v1',
        task='T1: 698 combined baseline independent acceptance and audit assets',
        generated_at=iso_now(),
        project_root=str(PROJECT_ROOT),
        output_root=str(OUT_ROOT),
        historical_root=str(HIST_ROOT),
        topology=TOPOLOGY, algorithm=ALGORITHM,
        baseline=dict(
            description='V2 dual-height 698/1024 combined baseline',
            z1=dict(plane='z1', source_algorithm=SOURCE_ALGORITHM['z1'],
                    source_routes_json=relative(SOURCE_ROUTES['z1']),
                    routed=EXPECTED_ROUTED['z1']),
            z2=dict(plane='z2', source_algorithm=SOURCE_ALGORITHM['z2'],
                    source_routes_json=relative(SOURCE_ROUTES['z2']),
                    routed=EXPECTED_ROUTED['z2']),
            routed=EXPECTED_TOTAL_ROUTED,
            connections_total=CONNECTIONS_TOTAL,
            routing_rate=EXPECTED_TOTAL_ROUTED / CONNECTIONS_TOTAL,
            routing_rate_text=f'{EXPECTED_TOTAL_ROUTED}/{CONNECTIONS_TOTAL}',
            combine_builder='four_side_1024.fslw.combine.build_combined',
            authoritative_validator='four_side_1024.fslw.validate_fslw '
                                    "(policy='strict', clearance 0.080 mm, R=40 mm)",
            independent_recomputation=('four_side_1024.d56.index.D56Index '
                                       "(width=0.05, gap=0.03, "
                                       "crossing_policy='strict')"),
            frozen_csv_sha256=V2_CSV_SHA256),
        criteria=criteria,
        summary=dict(
            all_criteria_passed=all_passed,
            baseline_698_established=bool(
                all_passed and combined_routed == EXPECTED_TOTAL_ROUTED),
            combined_routed=combined_routed,
            routing_rate=combined['routing_rate'],
            routing_rate_text=f'{combined_routed}/{CONNECTIONS_TOTAL}',
            z1_routed=checks['z1']['routed'],
            z2_routed=checks['z2']['routed'],
            plane_audit_passed={plane: audits[plane]['passed']
                                for plane in PLANES},
            plane_crossing_counts={plane: audits[plane]['crossing_count']
                                   for plane in PLANES},
            combined_same_plane_crossings=combined['same_plane_crossings'],
            combined_same_plane_violations=combined['same_plane_violation_total'],
            d56_leave_one_out_violations=(
                {plane: independent['d56_index_selfcheck'][plane]['violation_count']
                 for plane in PLANES} if not args.skip_independent else 'skipped'),
            crosscheck_mismatches=(
                {plane: independent['crosscheck_fslw'][plane]['mismatch_count']
                 for plane in PLANES} if not args.skip_independent else 'skipped'),
            best_historical_group=abcd['best_historical_group'],
            best_historical_routed=abcd['best_historical_routed'],
            delta_vs_best_historical=abcd['delta_vs_best_historical'],
            delta_vs_v2_default_B=abcd['delta_vs_v2_default_B'],
        ),
        outputs=dict(
            plane_dirs={plane: str(plane_run_dir(plane)) for plane in PLANES},
            combined_dir=str(combined_run_dir()),
            files={
                'z1_routes.json': file_record(plane_run_dir('z1') / 'routes.json'),
                'z1_config.json': file_record(plane_run_dir('z1') / 'config.json'),
                'z1_audit_strict.json': file_record(
                    plane_run_dir('z1') / 'audit_strict.json'),
                'z1_statistics.json': file_record(
                    plane_run_dir('z1') / 'statistics.json'),
                'z2_routes.json': file_record(plane_run_dir('z2') / 'routes.json'),
                'z2_config.json': file_record(plane_run_dir('z2') / 'config.json'),
                'z2_audit_strict.json': file_record(
                    plane_run_dir('z2') / 'audit_strict.json'),
                'z2_statistics.json': file_record(
                    plane_run_dir('z2') / 'statistics.json'),
                'z1_routing_all.gds': file_record(
                    plane_run_dir('z1') / 'routing_all.gds'),
                'z1_routing_all.svg': file_record(
                    plane_run_dir('z1') / 'routing_all.svg'),
                'z2_routing_all.gds': file_record(
                    plane_run_dir('z2') / 'routing_all.gds'),
                'z2_routing_all.svg': file_record(
                    plane_run_dir('z2') / 'routing_all.svg'),
                'combined_routes_1024.json': file_record(
                    combined_run_dir() / 'routes_1024.json'),
                'combined_statistics.json': file_record(
                    combined_run_dir() / 'statistics.json'),
                'combined_planes_summary.json': file_record(
                    combined_run_dir() / 'planes_summary.json'),
                'two_height_gds': file_record(
                    combined_run_dir() / 'routing_1024_two_height.gds'),
                'layer_2d_png': file_record(combined_run_dir() / 'layer_2d.png'),
                'layer_2d_svg': file_record(combined_run_dir() / 'layer_2d.svg'),
                'overlay_3d_png': file_record(
                    combined_run_dir() / 'overlay_3d.png'),
                'reproduce_readme': file_record(
                    OUT_ROOT / 'baseline_reproduce.md'),
            },
            acceptance_json=str(OUT_ROOT / 'baseline_acceptance.json')),
        environment=dict(
            python=sys.version.split()[0],
            implementation=platform.python_implementation(),
            platform=platform.platform(),
            numpy=_package_version('numpy'),
            gdspy=_package_version('gdspy'),
            matplotlib=_package_version('matplotlib'),
            script=relative(Path(__file__).resolve()),
        ),
        timings=dict(
            plane_routes_and_config_seconds={
                plane: plane_artifacts[plane]['timings'][
                    'routes_and_config_seconds'] for plane in PLANES},
            plane_strict_audit_seconds={
                plane: plane_artifacts[plane]['timings'][
                    'strict_audit_seconds'] for plane in PLANES},
            plane_statistics_seconds={
                plane: plane_artifacts[plane]['timings'][
                    'statistics_seconds'] for plane in PLANES},
            combine_seconds=combine_seconds,
            total_seconds=time.perf_counter() - total_started,
        ),
        reproduce=dict(
            readme=relative(OUT_ROOT / 'baseline_reproduce.md'),
            commands=[
                '.venv\\Scripts\\python.exe four_side_1024\\v2opt\\audit_baseline.py',
                '.venv\\Scripts\\python.exe -m pytest '
                'four_side_1024\\v2opt\\tests -q',
            ],
            note='read-only historical inputs; the script rewrites every v01 '
                 'artefact from them'),
        notes=[
            'no routing search is executed here: the 698 baseline recombines two '
            'already validated historical plane solutions verbatim',
            'plane z1 and plane z2 are two independent 2D problems at model heights '
            '0.0 and 0.5 mm; XY-projected cross-plane overlaps are not violations '
            '(fslw/SPEC.md section 2)',
            'bend loss and crossing loss remain unknown_uncalibrated; only the '
            'propagation loss is reported as a physical number',
            'the authoritative acceptance policy is validate_fslw strict '
            '(clearance 0.080 mm); d56 D56Index and crosscheck_fslw are used as '
            'independent cross-checks',
        ])

    acceptance_path = OUT_ROOT / 'baseline_acceptance.json'
    write_json(acceptance_path, acceptance)
    # ------------------------------------------------------------------ report
    print()
    print('=' * 78)
    print('ACCEPTANCE (T1)')
    print('=' * 78)
    for criterion in criteria:
        print_criterion(criterion['criterion_id'], criterion['name'],
                        criterion['passed'],
                        _criterion_print_details(criterion))
    print()
    print(f'baseline_acceptance.json : {acceptance_path}')
    print(f'baseline_reproduce.md    : {OUT_ROOT / "baseline_reproduce.md"}')
    print(f'698 established          : '
          f'{acceptance["summary"]["baseline_698_established"]}')
    print(f'all criteria passed      : {all_passed}')
    print(f'total wall               : '
          f'{acceptance["timings"]["total_seconds"]:.1f}s')
    print('=' * 78)
    return 0 if all_passed else 1


def _criterion_print_details(criterion):
    evidence = criterion.get('evidence') or {}
    number = criterion['criterion_id']
    if number in (1, 2, 3, 4):
        details = {}
        for plane, result in evidence.items():
            if number == 1:
                details[plane] = (
                    f'records={result["record_count"]}, '
                    f'mismatches={result["identity_field_mismatch_count"]}, '
                    f'csv_sha_ok={result["csv_sha256_matches_expected"]}, '
                    f'routed={result["routed"]}')
            elif number == 2:
                details[plane] = (
                    f'routed={result["routed_count"]}, '
                    f'primitives_deep_equal={result["primitives_deep_equal_count"]}, '
                    f'byte_equal={result["primitives_byte_equal_count"]}, '
                    f'mismatches={result["primitive_mismatch_count"]}')
            elif number == 3:
                details[plane] = (
                    f'passed={result["passed"]}, '
                    f'routed={result["routed_count"]}, '
                    f'crossings={result["crossing_count"]}, '
                    f'violations={result["violation_pair_count"]}, '
                    f'sha_ok={result["audit_routes_sha256_matches"]}')
            else:
                details[plane] = (
                    f'audit_passed={result["audit_passed"]}, '
                    f'audit_merged={result["audit_merged_from_file"]}, '
                    f'violations={result["total_violation_count"]}, '
                    f'routed={result["routed"]}')
        return details
    if number == 5:
        return {
            'combined_routed': evidence.get('routed_total'),
            'by_plane': evidence.get('routed_by_plane'),
            'routing_rate': evidence.get('routing_rate'),
            'same_plane_violations': evidence.get('same_plane_violation_total'),
            'gds_layers': evidence.get('gds_layers'),
            'gds_verified': evidence.get('gds_verified'),
            'gds_reread_verified': (
                evidence.get('independent_gds_reread') or {}).get('verified'),
            'gds_reread_paths': (
                evidence.get('independent_gds_reread') or {}).get(
                    'paths_per_layer'),
            'figures': {key: value for key, value in
                        (evidence.get('figures') or {}).items()
                        if key.endswith('_exists')},
            'figure_integrity': {
                key: (value.get('valid_png') if key.endswith('_png')
                      else value.get('valid_svg'))
                for key, value in
                (evidence.get('figure_integrity') or {}).items()},
        }
    if number == 6:
        if evidence.get('skipped'):
            return {'status': 'skipped'}
        details = {}
        for plane, result in (evidence.get('d56_index_selfcheck') or {}).items():
            details[f'd56_leave_one_out_{plane}'] = (
                f'violations={result["violation_count"]}, '
                f'valid={result["valid_route_count"]}/'
                f'{result["leave_one_out_checked"]}, '
                f'crossings={result["crossing_count_round_trip"]}, '
                f'validator_crossings={result["validator_crossing_count"]}')
        for plane, result in (evidence.get('crosscheck_fslw') or {}).items():
            details[f'crosscheck_{plane}'] = (
                f'mismatch={result["mismatch_count"]}, '
                f'pairs={result["compared_pair_count"]}, '
                f'crossings_router={result["crossing_count"].get("router")}, '
                f'crossings_validator={result["crossing_count"].get("validator")}')
        return details
    if number == 7:
        rows = evidence.get('comparison_table') or []
        return {'groups': len(rows),
                'table': [f'{row["group"]}: {row["routed_total"]}/1024 '
                          f'(z1={row["z1_routed"]},z2={row["z2_routed"]})'
                          for row in rows],
                'best': (evidence.get('best_historical_group'),
                         evidence.get('best_historical_routed')),
                'delta_vs_best': evidence.get('delta_vs_best_historical')}
    return {}


def _package_version(name):
    try:
        module = __import__(name)
        return getattr(module, '__version__', 'unknown')
    except Exception:  # noqa: BLE001 - environment record only
        return 'not-available'


if __name__ == '__main__':
    raise SystemExit(main())
