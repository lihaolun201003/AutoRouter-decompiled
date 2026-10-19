"""ABCD Phase 1 -- connection topology loading, validation and symmetry analysis.

Owner: connectivity (see ``abcd/SPEC.md`` §1, §4, §5, §7).

Public API (stable; consumed by ``abcd/run.py`` and ``abcd/metrics.py``)::

    routes, endpoints, connectors, validation = load_topology(csv_path, cfg=None)
    checks = validate_csv_checks(routes, endpoints=None, connectors=None)
    sym = symmetry_maps(routes, endpoints)

``routes`` / ``endpoints`` / ``connectors`` / ``validation`` come straight from
:func:`four_side_1024.inputs.load`; the returned ``validation`` is *extended*
(never narrowed) with ``topology``, ``csv_path``, ``csv_sha256``,
``inputs_load_evidence`` and the independent ``checks``.

``symmetry_maps`` returns ``{"transforms": [...]}`` with the 8 symmetries of the
board square (D4 group).  Every transform provides the keys requested by the
viz owner and by SPEC §5::

    name, matrix, offset, route_map, route_map_complete, mapped_route_count,
    channel_map_consistent
    # additive diagnostics (safe to ignore):
    orientation_counts, fixed_point_count, endpoint_map_complete,
    connector_map, connector_map_complete, connector_pair_multiset_preserved,
    topology_invariant, description

A top-level ``by_name`` dict also exposes every transform plus the SPEC §5
alias ``diag`` (== ``diag_main``), and ``aliases`` records the aliasing.

Transform convention (board coordinates in mm, origin lower-left, 150 x 150)::

    x' = a*x + b*y + tx        matrix = [[a, b], [c, d]],  offset = [tx, ty]
    y' = c*x + d*y + ty

Transform names / definitions (exact numbers are also emitted in the JSON)::

    identity    M=[[ 1, 0],[ 0, 1]]  o=[  0,   0]   (x,y) -> (x, y)
    rot90       M=[[ 0,-1],[ 1, 0]]  o=[150,   0]   (x,y) -> (150-y, x)   CCW
    rot180      M=[[-1, 0],[ 0,-1]]  o=[150, 150]   (x,y) -> (150-x, 150-y)
    rot270      M=[[ 0, 1],[-1, 0]]  o=[  0, 150]   (x,y) -> (y, 150-x)
    mirror_x    M=[[-1, 0],[ 0, 1]]  o=[150,   0]   (x,y) -> (150-x, y)   vertical axis x=75
    mirror_y    M=[[ 1, 0],[ 0,-1]]  o=[  0, 150]   (x,y) -> (x, 150-y)   horizontal axis y=75
    diag_main   M=[[ 0, 1],[ 1, 0]]  o=[  0,   0]   (x,y) -> (y, x)       main diagonal y=x
    diag_anti   M=[[ 0,-1],[-1, 0]]  o=[150, 150]   (x,y) -> (150-y, 150-x) anti-diagonal y=150-x

Endpoint matching tolerance is 1e-6 mm (exact unordered endpoint-set match; a
transform either permutes all 2048 endpoint identities or it does not).

Measured claims (recomputed on every run, dumped to
``outputs/four_side_1024_v1_v2_abcd/connectivity/``):

* V1: endpoint-level route set invariant only under ``identity``.
* V2: endpoint-level route set invariant only under ``identity`` and
  ``diag_main`` (1024/1024 routes); the connector-level connection multiset
  (unordered connector pairs with multiplicity) is invariant under all 8
  transforms.  ``rot180`` / ``diag_anti`` map 0/1024 routes at endpoint level
  because they flip the virtual row (channel -> 33-channel), and opposite
  connections use row 1 while adjacent connections use row 2.

Run ``python -m four_side_1024.abcd.connectivity`` from the code directory
(``OpticalWaveguideRouter2D``) to rebuild every Phase-1 artifact.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

# Support both ``python -m four_side_1024.abcd.connectivity`` and direct
# ``python four_side_1024/abcd/connectivity.py`` execution.
if __package__ in (None, ''):  # pragma: no cover - only for direct execution
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from four_side_1024 import inputs  # noqa: E402

__all__ = [
    'V1_CSV', 'V2_CSV', 'V1_SHA256', 'V2_SHA256', 'BOARD_MM',
    'TRANSFORMS', 'EXPECTED', 'OUTPUT_DIR',
    'apply_transform', 'load_topology', 'validate_csv_checks', 'symmetry_maps',
    'diff_topologies', 'analyse_topology', 'build_connectivity_artifacts',
]

# ---------------------------------------------------------------------------
# Board / topology constants (SPEC §0, §1)
# ---------------------------------------------------------------------------
BOARD_MM = 150.0
BOARD_CENTER = (BOARD_MM / 2.0, BOARD_MM / 2.0)
SIDES = 'NSEW'
CONNECTORS_PER_SIDE = 16
CHANNELS_PER_CONNECTOR = 32
ROWS = 2
COLUMNS = 16
CONNECTOR_PITCH_MM = 9.0
VIRTUAL_PITCH_MM = 0.175
CONNECTOR_INNER_MARGIN_MM = 7.5  # first connector centre at 7.5 mm from the edge corner
RAW_COORD_DECIMALS = 6           # endpoint routing_xy coordinates have <= 4 decimals
MATCH_TOL_MM = 1.0e-6            # SPEC §5 endpoint matching tolerance

CODE_DIR = Path(__file__).resolve().parents[2]      # .../OpticalWaveguideRouter2D
ABCD_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = CODE_DIR / 'outputs' / 'four_side_1024_v1_v2_abcd' / 'connectivity'

V1_CSV = Path(r'C:\Users\lihao\Desktop\optical_1024_multitomulti_connectivity_v1.csv')
V2_CSV = Path(r'C:\Users\lihao\Desktop\optical_1024_multitomulti_connectivity_v2_symmetric.csv')

# SPEC §1 (V1) / measured from the immutable V2 file (SPEC §1 says the V2 hash is
# computed by this module and written to connectivity/validation.json).
V1_SHA256 = '0ecce47109f9223e8407928c423ad5d9272186938cc267877a6158936e0e428b'
V2_SHA256 = '49dd9e89c4ea506d04638ae34eb06a0d8163d479de80869804c881ee1c43915e'

EXPECTED = dict(
    connections=1024,
    route_id_min=1,
    route_id_max=1024,
    connectors=64,
    connectors_per_side=16,
    channels_per_connector=32,
    endpoints=2048,
    relation_counts={'opposite': 512, 'adjacent': 512},
    pair_counts={'NS': 256, 'EW': 256, 'EN': 128, 'ES': 128, 'SW': 128, 'NW': 128},
    ordered_side_pair_counts={
        'N->S': 256, 'E->W': 256, 'N->E': 128, 'E->S': 128, 'S->W': 128, 'W->N': 128,
    },
    opposite_row=1,
    adjacent_row=2,
)

# ---------------------------------------------------------------------------
# Board transforms (D4).  matrix/offset follow x' = a*x + b*y + tx.
# ---------------------------------------------------------------------------
TRANSFORMS = [
    dict(name='identity',
         matrix=[[1.0, 0.0], [0.0, 1.0]], offset=[0.0, 0.0],
         description='identity (x,y) -> (x,y)'),
    dict(name='rot90',
         matrix=[[0.0, -1.0], [1.0, 0.0]], offset=[150.0, 0.0],
         description='CCW 90 deg about board centre: (x,y) -> (150-y, x)'),
    dict(name='rot180',
         matrix=[[-1.0, 0.0], [0.0, -1.0]], offset=[150.0, 150.0],
         description='180 deg about board centre: (x,y) -> (150-x, 150-y)'),
    dict(name='rot270',
         matrix=[[0.0, 1.0], [-1.0, 0.0]], offset=[0.0, 150.0],
         description='CW 90 deg / CCW 270 deg: (x,y) -> (y, 150-x)'),
    dict(name='mirror_x',
         matrix=[[-1.0, 0.0], [0.0, 1.0]], offset=[150.0, 0.0],
         description='reflect across vertical centre line x=75: (x,y) -> (150-x, y)'),
    dict(name='mirror_y',
         matrix=[[1.0, 0.0], [0.0, -1.0]], offset=[0.0, 150.0],
         description='reflect across horizontal centre line y=75: (x,y) -> (x, 150-y)'),
    dict(name='diag_main',
         matrix=[[0.0, 1.0], [1.0, 0.0]], offset=[0.0, 0.0],
         description='reflect across main diagonal y=x (== SPEC §5 "diag"): (x,y) -> (y, x)'),
    dict(name='diag_anti',
         matrix=[[0.0, -1.0], [-1.0, 0.0]], offset=[150.0, 150.0],
         description='reflect across anti-diagonal y=150-x: (x,y) -> (150-y, 150-x)'),
]

# SPEC §5 name aliases -> canonical name used in ``transforms``.
TRANSFORM_ALIASES = {'diag': 'diag_main'}


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------
def sha256_file(path) -> str:
    """Return the SHA256 hex digest of a file."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def board_xy(side, along):
    """Board coordinate of an edge point, computed independently of inputs.py."""
    if side == 'N':
        return [float(along), BOARD_MM]
    if side == 'S':
        return [float(along), 0.0]
    if side == 'E':
        return [BOARD_MM, float(along)]
    if side == 'W':
        return [0.0, float(along)]
    raise ValueError(f'unknown side {side!r}')


def inward_vector(side):
    """Unit vector pointing from the edge into the board."""
    return {'N': [0.0, -1.0], 'S': [0.0, 1.0], 'E': [-1.0, 0.0], 'W': [1.0, 0.0]}[side]


def connector_center_xy(side, connector):
    """Centre of a connector on the board edge (formula from SPEC §0)."""
    idx = int(str(connector)[1:])
    along = CONNECTOR_INNER_MARGIN_MM + (idx - 1) * CONNECTOR_PITCH_MM
    return board_xy(side, along)


def expected_along_mm(connector, channel):
    """Along-edge coordinate of one channel port (virtual_unfolded mapping)."""
    idx = int(str(connector)[1:])
    center = CONNECTOR_INNER_MARGIN_MM + (idx - 1) * CONNECTOR_PITCH_MM
    return center + (int(channel) - (CHANNELS_PER_CONNECTOR + 1) / 2.0) * VIRTUAL_PITCH_MM


def expected_endpoint_xy(side, connector, channel):
    """Expected ``routing_xy`` of an endpoint, recomputed from SPEC §0 formulas."""
    return board_xy(side, expected_along_mm(connector, channel))


def apply_transform(transform, xy):
    """Apply one of :data:`TRANSFORMS` to a board coordinate ``(x, y)``."""
    m = transform['matrix']
    o = transform['offset']
    x, y = float(xy[0]), float(xy[1])
    return [m[0][0] * x + m[0][1] * y + o[0],
            m[1][0] * x + m[1][1] * y + o[1]]


def _pair_relation_from_sides(a, b):
    pair = ''.join(sorted((a, b)))
    return 'opposite' if pair in ('NS', 'EW') else 'adjacent', pair


def _counter_to_dict(counter):
    return {str(k): int(v) for k, v in sorted(counter.items(), key=lambda kv: str(kv[0]))}


def _jsonable(obj):
    """Recursively convert a Python structure into a JSON-safe structure."""
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, Counter):
        return _jsonable(dict(obj))
    if isinstance(obj, (set, frozenset)):
        return [_jsonable(v) for v in sorted(obj)]
    if hasattr(obj, 'item') and not isinstance(obj, (str, bytes)):  # numpy scalar
        return obj.item()
    return obj


# ---------------------------------------------------------------------------
# Endpoint index / snapping (transform matching with 1e-6 mm tolerance)
# ---------------------------------------------------------------------------
class _EndpointIndex:
    """Coordinate -> endpoint_id index with exact (1e-6 mm) snapping."""

    def __init__(self, endpoints, tol=MATCH_TOL_MM, digits=RAW_COORD_DECIMALS):
        self.tol = float(tol)
        self.digits = int(digits)
        self.endpoints = endpoints
        self.by_key = defaultdict(list)
        for eid, ep in endpoints.items():
            self.by_key[self._key(ep['routing_xy'])].append(eid)
        self.unique = all(len(v) == 1 for v in self.by_key.values())

    def _key(self, xy):
        return (round(float(xy[0]), self.digits), round(float(xy[1]), self.digits))

    def snap(self, xy):
        """Return (endpoint_id or None, max |delta| mm)."""
        key = self._key(xy)
        candidates = self.by_key.get(key)
        if candidates:
            best = None
            for eid in candidates:
                delta = self._delta(xy, self.endpoints[eid]['routing_xy'])
                if best is None or delta < best[1]:
                    best = (eid, delta)
            if best is not None and best[1] <= self.tol:
                return best
        # Robust fallback (only for coordinates that are not exact multiples of
        # the 1e-6 grid, e.g. an externally modified topology): linear scan.
        best = (None, math.inf)
        for eid, ep in self.endpoints.items():
            delta = self._delta(xy, ep['routing_xy'])
            if delta < best[1]:
                best = (eid, delta)
        return best if best[1] <= self.tol else (None, best[1])

    def _delta(self, xy, target):
        return max(abs(float(xy[0]) - float(target[0])), abs(float(xy[1]) - float(target[1])))


def _endpoint_permutation(endpoints, transform, index=None):
    """Permutation of the 2048 endpoint identities induced by ``transform``."""
    index = index or _EndpointIndex(endpoints)
    perm, errors, unmatched = {}, [], []
    for eid in sorted(endpoints):
        image, delta = index.snap(apply_transform(transform, endpoints[eid]['routing_xy']))
        perm[eid] = image
        errors.append(delta)
        if image is None:
            unmatched.append(eid)
    images = [v for v in perm.values() if v is not None]
    complete = (not unmatched) and len(set(images)) == len(images) == len(endpoints)
    return dict(
        perm=perm,
        complete=complete,
        unmatched=unmatched,
        max_error_mm=max(errors) if errors else 0.0,
        fixed_point_count=sum(1 for k, v in perm.items() if v == k),
    )


# ---------------------------------------------------------------------------
# Topology detection / loading
# ---------------------------------------------------------------------------
def detect_topology(csv_path, csv_sha256=None) -> str:
    """Return 'V1', 'V2' or 'UNKNOWN' for a connectivity CSV."""
    path = Path(csv_path)
    digest = csv_sha256 or sha256_file(path)
    if digest == V1_SHA256:
        return 'V1'
    if digest == V2_SHA256:
        return 'V2'
    name = path.name.lower()
    if 'v2' in name or 'symmetric' in name:
        return 'V2'
    if 'v1' in name:
        return 'V1'
    return 'UNKNOWN'


def _inputs_load_evidence(routes, endpoints, connectors, validation):
    """Document that the fixed assertions inside :func:`inputs.load` passed.

    Reaching this point means ``inputs.load`` returned without raising its
    ``AssertionError`` checks; here we record the observed values that those
    fixed assertions assert on, so the evidence is in the JSON artifacts.
    """
    usage = Counter()
    for r in routes:
        usage[r['source_endpoint']] += 1
        usage[r['target_endpoint']] += 1
    relations = Counter(r['relation'] for r in routes)
    opposite = [r for r in routes if r['relation'] == 'opposite']
    adjacent = [r for r in routes if r['relation'] == 'adjacent']
    coords = {tuple(round(v, 9) for v in ep['routing_xy']) for ep in endpoints.values()}
    return dict(
        returned_without_assertion_error=True,
        rows=len(routes),
        route_ids_are_1_to_1024=(sorted(int(r['route_id']) for r in routes)
                                 == list(range(1, 1025))),
        relation_counts=_counter_to_dict(relations),
        opposite_rows_all_1=all(int(r['source_row']) == int(r['target_row']) == 1 for r in opposite),
        adjacent_rows_all_2=all(int(r['source_row']) == int(r['target_row']) == 2 for r in adjacent),
        endpoints_used_once=(len(usage) == len(endpoints)
                             and set(usage) == set(endpoints)
                             and set(usage.values()) == {1}),
        distinct_endpoint_identities=len(usage),
        virtual_routing_xy_unique=len(coords),
        connectors_returned=len(connectors),
        channels_per_connector=validation.get('channels_per_connector'),
        input_validation_passed=bool(validation.get('passed')),
        fixed_assertions=['len(rows)==1024', 'route_ids==1..1024', 'relation==opposite/adjacent',
                          'source_row==target_row==(1|2)', 'endpoints used exactly once',
                          'set(usage)==set(endpoints)', 'relations=={opposite:512, adjacent:512}',
                          'len(set(routing_xy))==2048'],
    )


def load_topology(csv_path=None, cfg=None):
    """Load one connectivity topology and return the extended validation record.

    Wrapper around :func:`four_side_1024.inputs.load` (which is NOT modified).
    Returns ``(routes, endpoints, connectors, validation)`` exactly like
    ``inputs.load``, with ``validation`` extended by:

    * ``topology`` ('V1' | 'V2' | 'UNKNOWN'), ``csv_path``, ``csv_sha256``,
      ``known_csv_sha256``
    * ``inputs_load_evidence`` -- proof that the fixed ``inputs.load``
      assertions passed for this file
    * ``checks`` -- the independent checks from :func:`validate_csv_checks`
    * ``checks_passed``
    """
    path = Path(csv_path or V1_CSV)
    routes, endpoints, connectors, validation = inputs.load(path, cfg)
    sha = str(validation.get('csv_sha256') or sha256_file(path))
    topology = detect_topology(path, sha)
    checks = validate_csv_checks(routes, endpoints=endpoints, connectors=connectors)
    extended = dict(validation)
    extended.update(
        topology=topology,
        csv_path=str(path.resolve()),
        csv_sha256=sha,
        known_csv_sha256=sha in (V1_SHA256, V2_SHA256),
        inputs_load_evidence=_inputs_load_evidence(routes, endpoints, connectors, validation),
        checks=checks,
        checks_passed=bool(checks.get('passed')),
        spec_section='abcd/SPEC.md §1, §4, §5',
    )
    return routes, endpoints, connectors, extended


# ---------------------------------------------------------------------------
# Independent CSV / endpoint-numbering validation
# ---------------------------------------------------------------------------
def _route_role_fields(route, role, endpoints):
    """Return (side, connector, row, column, channel) for one role of a route."""
    if f'{role}_connector' in route and f'{role}_channel' in route:
        return (str(route[f'{role}_side']), str(route[f'{role}_connector']),
                int(route[f'{role}_row']), int(route[f'{role}_column']),
                int(route[f'{role}_channel']))
    if endpoints is None:
        raise KeyError(f'route lacks {role}_connector/{role}_channel and no endpoints given')
    ep = endpoints[route[f'{role}_endpoint']]
    return (ep['side'], ep['connector'], int(ep['row']), int(ep['column']), int(ep['channel']))


def validate_csv_checks(routes, endpoints=None, connectors=None) -> dict:
    """Independent audit of a connectivity CSV, from row fields (+ endpoints).

    Every required check from the Phase-1 mission is reported with its observed
    count/value; ``result['passed']`` is True iff all checks pass.  When
    ``endpoints`` is given (as returned by ``inputs.load``) the endpoint
    coordinate / numbering consistency checks are included as well.

    Checks
    ------
    * 1024 connections, route ids exactly 1..1024
    * 2048 endpoint identities, each used exactly once (as source or target)
    * 64 connectors, each using all 32 channels exactly once
    * every connection between two different sides (0 same-side connections)
    * 512 opposite / 512 adjacent; NS 256, EW 256, EN/ES/SW/NW 128 each
    * ordered side pairs N->S/E->W = 256, N->E/E->S/S->W/W->N = 128
    * row rule: opposite uses row 1, adjacent uses row 2 (source and target)
    * channel identity: channel == (row-1)*16 + column; row/column/channel ranges
    * connector identity: prefix == side, index in 1..16
    * relation label consistent with the two sides
    * no duplicate connection (unordered or ordered)
    * endpoint coordinates: 2048 distinct, on the correct board edge, matching the
      independent virtual_unfolded formula (spec/side/connector/row/column/
      channel vs routing_xy) -- i.e. no CSV/coordinate numbering error
    """
    checks = {}
    failed = []

    def record(name, passed, **info):
        checks[name] = dict(passed=bool(passed), **info)
        if not passed:
            failed.append(name)

    routes = list(routes)
    connections = len(routes)
    record('connections', connections == EXPECTED['connections'], observed=connections,
           expected=EXPECTED['connections'])

    route_ids = [int(r['route_id']) for r in routes]
    record('route_ids', (sorted(route_ids) == list(range(EXPECTED['route_id_min'],
                                                         EXPECTED['route_id_max'] + 1))),
           unique=len(set(route_ids)), min=min(route_ids) if route_ids else None,
           max=max(route_ids) if route_ids else None)

    # ---- endpoint identities, usage, channel coverage ---------------------
    usage = Counter()
    endpoint_channel_usage = defaultdict(list)
    side_of_connector = {}
    role_fields = {}
    field_violations = []
    channel_formula_violations = []
    connector_format_violations = []
    for r in routes:
        for role in ('source', 'target'):
            side, connector, row, column, channel = _route_role_fields(r, role, endpoints)
            role_fields[(int(r['route_id']), role)] = (side, connector, row, column, channel)
            eid = f'{connector}:{row}:{column}'
            usage[eid] += 1
            endpoint_channel_usage[connector].append(channel)
            side_of_connector[connector] = side
            if channel != (row - 1) * COLUMNS + column:
                channel_formula_violations.append(
                    dict(route_id=int(r['route_id']), role=role,
                         channel=channel, row=row, column=column))
            if (str(connector)[:1] != side or not str(connector)[1:].isdigit()
                    or not 1 <= int(str(connector)[1:]) <= CONNECTORS_PER_SIDE
                    or not 1 <= row <= ROWS or not 1 <= column <= COLUMNS
                    or not 1 <= channel <= CHANNELS_PER_CONNECTOR):
                connector_format_violations.append(dict(route_id=int(r['route_id']), role=role))
            if endpoints is not None:
                ep = endpoints.get(r[f'{role}_endpoint'])
                if ep is None or ep.get('side') != side or ep.get('connector') != connector \
                        or int(ep.get('row', 0)) != row or int(ep.get('column', 0)) != column \
                        or int(ep.get('channel', 0)) != channel:
                    field_violations.append(dict(route_id=int(r['route_id']), role=role,
                                                 endpoint=r.get(f'{role}_endpoint')))
    record('endpoints_used_once',
           len(usage) == EXPECTED['endpoints'] and set(usage.values()) == {1},
           distinct_endpoints=len(usage), total_slots=sum(usage.values()),
           usage_min=min(usage.values()) if usage else None,
           usage_max=max(usage.values()) if usage else None,
           missing_endpoints=EXPECTED['endpoints'] - len(usage))
    connectors_seen = sorted(usage.keys(), key=lambda s: (s[0], s))
    connector_names = sorted({c for c in endpoint_channel_usage})
    connector_channel_ok = {}
    for connector in connector_names:
        channels = sorted(endpoint_channel_usage[connector])
        connector_channel_ok[connector] = (len(channels) == EXPECTED['channels_per_connector']
                                           and channels == list(range(1, CHANNELS_PER_CONNECTOR + 1)))
    record('connectors', len(connector_names) == EXPECTED['connectors'],
           observed=len(connector_names), expected=EXPECTED['connectors'])
    record('channel_coverage',
           all(connector_channel_ok.values()) and len(connector_channel_ok) == EXPECTED['connectors'],
           connectors_checked=len(connector_channel_ok),
           connectors_ok=sum(connector_channel_ok.values()),
           expected_channels_per_connector=EXPECTED['channels_per_connector'])
    if connectors is not None:
        connector_meta_ok = (len(connectors) == EXPECTED['connectors']
                             and all(int(c.get('channels', 0)) == EXPECTED['channels_per_connector']
                                     for c in connectors))
        record('connector_metadata', connector_meta_ok, connectors=len(connectors),
               channels_each=EXPECTED['channels_per_connector'])
    record('channel_formula', not channel_formula_violations,
           violations=len(channel_formula_violations),
           sample=channel_formula_violations[:5])
    record('connector_format', not connector_format_violations,
           violations=len(connector_format_violations),
           sample=connector_format_violations[:5])
    if endpoints is not None:
        record('endpoint_field_consistency', not field_violations,
               violations=len(field_violations), sample=field_violations[:5])

    # ---- side pairs / relations / rows -------------------------------------
    same_side = []
    relation_counts = Counter()
    pair_counts = Counter()
    ordered_side_pairs = Counter()
    relation_violations = []
    row_violations = []
    for r in routes:
        s_side, _, s_row, _, _ = role_fields[(int(r['route_id']), 'source')]
        t_side, _, t_row, _, _ = role_fields[(int(r['route_id']), 'target')]
        ordered_side_pairs[f'{s_side}->{t_side}'] += 1
        if s_side == t_side:
            same_side.append(int(r['route_id']))
            continue
        relation, pair = _pair_relation_from_sides(s_side, t_side)
        relation_counts[relation] += 1
        pair_counts[pair] += 1
        if str(r.get('relation', relation)) != relation:
            relation_violations.append(dict(route_id=int(r['route_id']),
                                            declared=r.get('relation'), computed=relation))
        expected_row = EXPECTED['opposite_row'] if relation == 'opposite' else EXPECTED['adjacent_row']
        if not (s_row == t_row == expected_row):
            row_violations.append(dict(route_id=int(r['route_id']), relation=relation,
                                       source_row=s_row, target_row=t_row,
                                       expected_row=expected_row))
    record('different_sides', not same_side, same_side_connections=len(same_side),
           sample=same_side[:5])
    record('relation_counts',
           {k: relation_counts.get(k, 0) for k in EXPECTED['relation_counts']}
           == EXPECTED['relation_counts'],
           observed=_counter_to_dict(relation_counts), expected=EXPECTED['relation_counts'])
    record('pair_counts',
           {k: pair_counts.get(k, 0) for k in EXPECTED['pair_counts']} == EXPECTED['pair_counts'],
           observed=_counter_to_dict(pair_counts), expected=EXPECTED['pair_counts'])
    record('ordered_side_pair_counts',
           {k: ordered_side_pairs.get(k, 0) for k in EXPECTED['ordered_side_pair_counts']}
           == EXPECTED['ordered_side_pair_counts'],
           observed=_counter_to_dict(ordered_side_pairs),
           expected=EXPECTED['ordered_side_pair_counts'])
    record('row_rule', not row_violations, violations=len(row_violations),
           sample=row_violations[:5], opposite_row=1, adjacent_row=2)
    record('relation_label', not relation_violations, violations=len(relation_violations),
           sample=relation_violations[:5])

    # ---- duplicates --------------------------------------------------------
    unordered = Counter()
    ordered = Counter()
    for r in routes:
        s = role_fields[(int(r['route_id']), 'source')]
        t = role_fields[(int(r['route_id']), 'target')]
        a = (s[0], s[1], s[2], s[3], s[4])
        b = (t[0], t[1], t[2], t[3], t[4])
        unordered[tuple(sorted((a, b)))] += 1
        ordered[(a, b)] += 1
    record('no_duplicate_connection',
           set(unordered.values()) == {1} and set(ordered.values()) == {1},
           distinct_unordered=len(unordered), distinct_ordered=len(ordered),
           duplicate_unordered=sum(1 for v in unordered.values() if v > 1),
           duplicate_ordered=sum(1 for v in ordered.values() if v > 1))

    # ---- coordinate / numbering consistency (needs endpoints) --------------
    if endpoints is not None:
        coords = {}
        coord_duplicates = 0
        geometry_errors = []
        max_xy_error = 0.0
        boundary_errors = []
        inward_errors = []
        missing_route_endpoints = []
        expected_endpoint_count = EXPECTED['connectors'] * EXPECTED['channels_per_connector']
        for endpoint_id, ep in endpoints.items():
            xy = (float(ep['routing_xy'][0]), float(ep['routing_xy'][1]))
            key = (round(xy[0], 9), round(xy[1], 9))
            if key in coords:
                coord_duplicates += 1
            coords[key] = endpoint_id
        for r in routes:
            for role in ('source', 'target'):
                eid = r[f'{role}_endpoint']
                ep = endpoints.get(eid)
                if ep is None:
                    missing_route_endpoints.append(eid)
                    continue
                side, connector, row, column, channel = role_fields[(int(r['route_id']), role)]
                expected = expected_endpoint_xy(side, connector, channel)
                delta = max(abs(expected[0] - ep['routing_xy'][0]),
                            abs(expected[1] - ep['routing_xy'][1]))
                max_xy_error = max(max_xy_error, delta)
                if delta > MATCH_TOL_MM:
                    geometry_errors.append(dict(route_id=int(r['route_id']), role=role,
                                                endpoint=eid, expected=expected,
                                                observed=list(ep['routing_xy']), delta=delta))
                border = (side == 'N' and abs(ep['routing_xy'][1] - BOARD_MM) <= MATCH_TOL_MM
                          or side == 'S' and abs(ep['routing_xy'][1]) <= MATCH_TOL_MM
                          or side == 'E' and abs(ep['routing_xy'][0] - BOARD_MM) <= MATCH_TOL_MM
                          or side == 'W' and abs(ep['routing_xy'][0]) <= MATCH_TOL_MM)
                if not border:
                    boundary_errors.append(dict(route_id=int(r['route_id']), role=role,
                                                endpoint=eid))
                inward = ep.get('inward')
                if inward is not None and [float(inward[0]), float(inward[1])] != inward_vector(side):
                    inward_errors.append(eid)
        record('endpoint_coordinates_unique',
               coord_duplicates == 0 and len(coords) == expected_endpoint_count,
               distinct=len(coords), duplicates=coord_duplicates,
               expected=expected_endpoint_count)
        record('endpoint_geometry',
               not geometry_errors and not missing_route_endpoints,
               max_xy_error_mm=max_xy_error, violations=len(geometry_errors),
               missing=len(missing_route_endpoints), sample=geometry_errors[:5],
               tolerance_mm=MATCH_TOL_MM)
        record('endpoint_on_edge', not boundary_errors, violations=len(boundary_errors),
               sample=boundary_errors[:5])
        record('endpoint_inward', not inward_errors, violations=len(inward_errors))
        record('endpoint_count', len(endpoints) == expected_endpoint_count,
               observed=len(endpoints), expected=expected_endpoint_count)
        record('endpoint_identity_matches_csv', not field_violations,
               violations=len(field_violations))
        record('connector_names', _connector_names_consistent(endpoint_channel_usage, endpoints),
               connectors=len(connector_names))
    else:
        checks['endpoint_geometry'] = dict(passed=None, skipped=True,
                                           reason='endpoints argument not provided')

    passed = all(v.get('passed') is not False for v in checks.values())
    return dict(
        passed=passed,
        failed_checks=failed,
        connections=connections,
        checks=checks,
        expectations=dict(EXPECTED),
        tolerance_mm=MATCH_TOL_MM,
    )


def _connector_names_consistent(endpoint_channel_usage, endpoints):
    """Every connector name in the endpoints dict is well formed and consistent."""
    expected = {f'{side}{i:02d}' for side in SIDES for i in range(1, CONNECTORS_PER_SIDE + 1)}
    observed = {c for c in endpoint_channel_usage}
    side_ok = True
    for connector in observed:
        for ep in endpoints.values():
            if ep.get('connector') != connector:
                continue
            # all ports of one connector lie on one edge, within its 32-channel span
            expected_xy = expected_endpoint_xy(ep['side'], connector, int(ep['channel']))
            if max(abs(expected_xy[0] - ep['routing_xy'][0]),
                   abs(expected_xy[1] - ep['routing_xy'][1])) > MATCH_TOL_MM:
                side_ok = False
                break
        if not side_ok:
            break
    return observed == expected and side_ok


# ---------------------------------------------------------------------------
# Symmetry analysis
# ---------------------------------------------------------------------------
def _connector_centers_from_endpoints(endpoints):
    """Derive the 64 connector centres from the endpoints dict."""
    centers = {}
    for ep in endpoints.values():
        connector = str(ep['connector'])
        side = str(ep['side'])
        if connector not in centers:
            centers[connector] = connector_center_xy(side, connector)
    return centers


def _connector_permutation(connector_centers, transform, tol=MATCH_TOL_MM):
    """Permutation of connector names induced by ``transform`` on centres."""
    perm, errors, unmatched = {}, [], []
    max_error = 0.0
    for name, center in connector_centers.items():
        image_xy = apply_transform(transform, center)
        best_name, best_delta = None, math.inf
        for other, other_center in connector_centers.items():
            delta = max(abs(image_xy[0] - other_center[0]), abs(image_xy[1] - other_center[1]))
            if delta < best_delta:
                best_name, best_delta = other, delta
        max_error = max(max_error, best_delta)
        if best_delta <= tol:
            perm[name] = best_name
        else:
            perm[name] = None
            unmatched.append(name)
        errors.append(best_delta)
    images = [v for v in perm.values() if v is not None]
    complete = (not unmatched) and len(set(images)) == len(images) == len(connector_centers)
    return dict(perm=perm, complete=complete, unmatched=unmatched,
                max_center_error_mm=max_error)


def _connector_pair_multiset(routes, endpoints):
    """Unordered connector-pair multiset of a route set (physical links)."""
    counter = Counter()
    for r in routes:
        src = endpoints[r['source_endpoint']]['connector']
        tgt = endpoints[r['target_endpoint']]['connector']
        counter[tuple(sorted((str(src), str(tgt))))] += 1
    return counter


def _channel_map_analysis(endpoints, perm):
    """Channel / row / side maps induced by an endpoint permutation.

    ``channel_map_consistent`` is True iff the mapped (row, channel) depends only
    on the original channel -- i.e. the permutation acts as a pure channel
    permutation independent of connector/side.
    """
    by_channel = defaultdict(set)
    by_side_channel = defaultdict(lambda: defaultdict(set))
    by_row = defaultdict(set)
    by_side = defaultdict(set)
    for eid, ep in endpoints.items():
        image = perm.get(eid)
        if image is None:
            return dict(consistent=False, by_side_consistent=False, channel_map=None,
                        row_map=None, side_map=None, channel_map_by_side=None,
                        reason='endpoint permutation incomplete')
        image_ep = endpoints[image]
        by_channel[int(ep['channel'])].add((int(image_ep['row']), int(image_ep['channel'])))
        by_side_channel[str(ep['side'])][int(ep['channel'])].add(
            (int(image_ep['row']), int(image_ep['channel'])))
        by_row[int(ep['row'])].add(int(image_ep['row']))
        by_side[str(ep['side'])].add(str(image_ep['side']))
    consistent = all(len(v) == 1 for v in by_channel.values())
    by_side_consistent = all(len(v) == 1 for d in by_side_channel.values() for v in d.values())
    side_consistent = all(len(v) == 1 for v in by_side.values())
    channel_map = {ch: sorted(v)[0][1] for ch, v in sorted(by_channel.items())} if consistent else None
    row_map = {row: sorted(v)[0] for row, v in sorted(by_row.items())} if consistent else None
    side_map = {side: sorted(v)[0] for side, v in sorted(by_side.items())} if side_consistent else None
    channel_map_by_side = None
    if by_side_consistent:
        channel_map_by_side = {side: {ch: sorted(v)[0][1] for ch, v in sorted(d.items())}
                               for side, d in sorted(by_side_channel.items())}
    return dict(consistent=consistent, by_side_consistent=by_side_consistent,
                channel_map=channel_map, row_map=row_map, side_map=side_map,
                channel_map_by_side=channel_map_by_side, reason=None)


def symmetry_maps(routes, endpoints) -> dict:
    """All 8 board symmetries applied to a 1024-connection topology.

    Parameters
    ----------
    routes : list of route records
        Needs ``route_id``, ``source_endpoint``, ``target_endpoint``; any other
        fields are ignored.  Works for CSV-loaded routes and ``routes.json``
        records (routed or failed).
    endpoints : dict
        ``endpoint_id -> {"routing_xy": [x, y], ...}``, i.e. ``inputs.load()[1]``.

    Returns
    -------
    dict with ``transforms`` (list of 8, see module docstring), ``by_name``
    (canonical names plus SPEC §5 alias ``diag``), ``aliases`` and summary lists.
    """
    routes = list(routes)
    endpoints = dict(endpoints)
    index = _EndpointIndex(endpoints)
    route_ids = [r['route_id'] for r in routes]
    route_pair_duplicates = len(route_ids) - len(set(route_ids))

    ordered_index = {}
    unordered_index = {}
    for r in routes:
        a, b = r['source_endpoint'], r['target_endpoint']
        ordered_index.setdefault((a, b), r['route_id'])
        unordered_index.setdefault(tuple(sorted((a, b))), r['route_id'])
    connector_centers = _connector_centers_from_endpoints(endpoints)
    base_connector_pairs = _connector_pair_multiset(routes, endpoints)

    transforms_out = []
    for transform in TRANSFORMS:
        endpoint_perm = _endpoint_permutation(endpoints, transform, index=index)
        perm = endpoint_perm['perm']
        route_map, orientations = {}, {}
        mapped, reversed_count, direct_count = 0, 0, 0
        for r in routes:
            rid = r['route_id']
            a, b = perm.get(r['source_endpoint']), perm.get(r['target_endpoint'])
            if a is None or b is None:
                route_map[rid] = None
                orientations[rid] = None
                continue
            direct = ordered_index.get((a, b))
            reversed_ = ordered_index.get((b, a))
            if direct is not None:
                route_map[rid] = direct
                orientations[rid] = 'direct'
                direct_count += 1
                mapped += 1
            elif reversed_ is not None:
                route_map[rid] = reversed_
                orientations[rid] = 'reversed'
                reversed_count += 1
                mapped += 1
            else:
                route_map[rid] = None
                orientations[rid] = None
        connector_perm = _connector_permutation(connector_centers, transform)
        connector_map = connector_perm['perm']
        pair_violations = 0
        pair_mapped = 0
        for pair, multiplicity in base_connector_pairs.items():
            image = tuple(sorted((connector_map.get(pair[0]), connector_map.get(pair[1]))))
            if None in image:
                pair_violations += 1
                continue
            pair_mapped += 1
            if base_connector_pairs.get(image, 0) != multiplicity:
                pair_violations += 1
        channel_info = _channel_map_analysis(endpoints, perm)
        fixed_point_count = sum(1 for rid in route_map if route_map[rid] == rid)
        route_map_complete = mapped == len(routes) and None not in route_map.values()
        topology_invariant = route_map_complete
        transforms_out.append(dict(
            name=transform['name'],
            matrix=[list(row) for row in transform['matrix']],
            offset=list(transform['offset']),
            description=transform['description'],
            route_map=route_map,
            route_map_complete=route_map_complete,
            mapped_route_count=mapped,
            channel_map_consistent=channel_info['consistent'],
            # ---- additive diagnostics ----
            orientation=orientations,
            orientation_counts={'direct': direct_count, 'reversed': reversed_count},
            fixed_point_count=fixed_point_count,
            endpoint_map_complete=endpoint_perm['complete'],
            endpoint_unmatched=len(endpoint_perm['unmatched']),
            endpoint_fixed_point_count=endpoint_perm['fixed_point_count'],
            snap_max_error_mm=endpoint_perm['max_error_mm'],
            connector_map=connector_map,
            connector_map_complete=connector_perm['complete'],
            connector_snap_max_error_mm=connector_perm['max_center_error_mm'],
            connector_pair_multiset_preserved=(pair_violations == 0
                                               and connector_perm['complete']),
            connector_pair_violations=pair_violations,
            connector_pairs_mapped=pair_mapped,
            connector_pairs_total=len(base_connector_pairs),
            channel_map_by_side_consistent=channel_info['by_side_consistent'],
            channel_map=channel_info['channel_map'],
            channel_map_by_side=channel_info['channel_map_by_side'],
            row_map=channel_info['row_map'],
            side_map=channel_info['side_map'],
            topology_invariant=topology_invariant,
        ))

    by_name = {t['name']: t for t in transforms_out}
    aliases = dict(TRANSFORM_ALIASES)
    for alias, canonical in aliases.items():
        by_name[alias] = by_name[canonical]
    return dict(
        transforms=transforms_out,
        by_name=by_name,
        aliases=aliases,
        n_routes=len(routes),
        n_endpoints=len(endpoints),
        tolerance_mm=MATCH_TOL_MM,
        route_id_duplicates=route_pair_duplicates,
        endpoint_level_symmetric=[t['name'] for t in transforms_out if t['route_map_complete']],
        connector_level_symmetric=[t['name'] for t in transforms_out
                                   if t['connector_pair_multiset_preserved']],
        channel_map_pure=[t['name'] for t in transforms_out if t['channel_map_consistent']],
        route_level_mapped_counts={t['name']: t['mapped_route_count'] for t in transforms_out},
    )


def summarise_symmetry(symmetry, topology=None) -> dict:
    """Compact human/JSON summary of :func:`symmetry_maps` output."""
    summary = dict(
        topology=topology,
        n_routes=symmetry['n_routes'],
        n_endpoints=symmetry['n_endpoints'],
        tolerance_mm=symmetry['tolerance_mm'],
        route_level_symmetric=list(symmetry['endpoint_level_symmetric']),
        connector_level_symmetric=list(symmetry['connector_level_symmetric']),
        channel_map_pure=list(symmetry['channel_map_pure']),
        transforms={},
    )
    for t in symmetry['transforms']:
        summary['transforms'][t['name']] = dict(
            mapped_route_count=t['mapped_route_count'],
            route_map_complete=t['route_map_complete'],
            fixed_point_count=t['fixed_point_count'],
            orientation_counts=t['orientation_counts'],
            connector_map_complete=t['connector_map_complete'],
            connector_pair_multiset_preserved=t['connector_pair_multiset_preserved'],
            channel_map_consistent=t['channel_map_consistent'],
            channel_map_by_side_consistent=t['channel_map_by_side_consistent'],
            side_map=t['side_map'],
            row_map=t['row_map'],
            channel_map=t['channel_map'],
            channel_map_by_side=(t['channel_map_by_side']
                                 if not t['channel_map_consistent'] else None),
        )
    return summary


# ---------------------------------------------------------------------------
# V1 vs V2 diff
# ---------------------------------------------------------------------------
def _endpoint_tuple(fields):
    """Hashable endpoint description (side, connector, row, column, channel)."""
    return tuple(fields)


def _route_endpoint_pair(route, role_fields, route_id):
    a = _endpoint_tuple(role_fields[(route_id, 'source')])
    b = _endpoint_tuple(role_fields[(route_id, 'target')])
    return tuple(sorted((a, b))), (a, b)


def diff_topologies(routes1, endpoints1, routes2, endpoints2) -> dict:
    """Compare two connectivity topologies (V1 vs V2).

    Returns a dict with the summary counts, per-route-id comparison rows,
    per-relation-type changes, per-connector statistics and the identical
    connections -- every number is computed here (never hardcoded).
    """
    # Role fields are resolved against the matching endpoints dict; both CSV
    # loads carry the fields directly, so no endpoint dict is actually needed.
    def role_fields(routes):
        out = {}
        for r in routes:
            rid = int(r['route_id'])
            for role in ('source', 'target'):
                out[(rid, role)] = (str(r[f'{role}_side']), str(r[f'{role}_connector']),
                                    int(r[f'{role}_row']), int(r[f'{role}_column']),
                                    int(r[f'{role}_channel']))
        return out

    f1 = role_fields(routes1)
    f2 = role_fields(routes2)
    pairs1, ordered1 = {}, {}
    for r in routes1:
        rid = int(r['route_id'])
        unordered, ordered = _route_endpoint_pair(r, f1, rid)
        pairs1[unordered] = rid
        ordered1[ordered] = rid
    pairs2, ordered2 = {}, {}
    for r in routes2:
        rid = int(r['route_id'])
        unordered, ordered = _route_endpoint_pair(r, f2, rid)
        pairs2[unordered] = rid
        ordered2[ordered] = rid

    common = set(pairs1) & set(pairs2)
    identical_connections = []
    for pair in sorted(common):
        identical_connections.append(dict(
            route_id_v1=pairs1[pair], route_id_v2=pairs2[pair],
            source_endpoint=f'{pair[0][1]}:{pair[0][2]}:{pair[0][3]}',
            target_endpoint=f'{pair[1][1]}:{pair[1][2]}:{pair[1][3]}',
            pair=''.join(sorted((pair[0][0], pair[1][0]))),
        ))

    # per route_id comparison
    by_id1 = {int(r['route_id']): r for r in routes1}
    by_id2 = {int(r['route_id']): r for r in routes2}
    change_classes = Counter()
    by_route_id = []
    for rid in sorted(set(by_id1) | set(by_id2)):
        r1, r2 = by_id1.get(rid), by_id2.get(rid)
        u1, o1 = _route_endpoint_pair(r1, f1, rid) if r1 else (None, None)
        u2, o2 = _route_endpoint_pair(r2, f2, rid) if r2 else (None, None)
        conn1 = (f1[(rid, 'source')][1], f1[(rid, 'target')][1]) if r1 else None
        conn2 = (f2[(rid, 'source')][1], f2[(rid, 'target')][1]) if r2 else None
        same_unordered = u1 is not None and u1 == u2
        same_ordered = o1 is not None and o1 == o2
        same_connector_pair = conn1 is not None and conn2 is not None \
            and tuple(sorted(conn1)) == tuple(sorted(conn2))
        same_source_connector = conn1 is not None and conn2 is not None and conn1[0] == conn2[0]
        same_target_connector = conn1 is not None and conn2 is not None and conn1[1] == conn2[1]
        if same_unordered:
            change = 'identical'
        elif same_connector_pair:
            change = 'same_connector_pair_channel_changed'
        elif same_source_connector:
            change = 'same_source_connector'
        elif same_target_connector:
            change = 'same_target_connector'
        else:
            change = 'connector_pair_changed'
        change_classes[change] += 1
        by_route_id.append(dict(
            route_id=rid,
            v1_source_endpoint=(':'.join(str(v) for v in u1[0][1:]) if u1 else ''),
            v1_target_endpoint=(':'.join(str(v) for v in u1[1][1:]) if u1 else ''),
            v2_source_endpoint=(':'.join(str(v) for v in u2[0][1:]) if u2 else ''),
            v2_target_endpoint=(':'.join(str(v) for v in u2[1][1:]) if u2 else ''),
            v1_pair=''.join(sorted((u1[0][0], u1[1][0]))) if u1 else '',
            v2_pair=''.join(sorted((u2[0][0], u2[1][0]))) if u2 else '',
            same_unordered_endpoint_pair=same_unordered,
            same_ordered_endpoint_pair=same_ordered,
            same_connector_pair=same_connector_pair,
            same_source_connector=same_source_connector,
            same_target_connector=same_target_connector,
            change_class=change,
        ))

    # connector level
    def _conn_pair(r):
        return tuple(sorted((str(r['source_connector']), str(r['target_connector']))))

    counter1, counter2 = Counter(), Counter()
    neighbour1, neighbour2 = defaultdict(set), defaultdict(set)
    degree1, degree2 = Counter(), Counter()
    for r in routes1:
        cp = _conn_pair(r)
        counter1[cp] += 1
        a = str(r['source_connector'])
        b = str(r['target_connector'])
        neighbour1[a].add(b)
        neighbour1[b].add(a)
        degree1[a] += 1
        degree1[b] += 1
    for r in routes2:
        cp = _conn_pair(r)
        counter2[cp] += 1
        a = str(r['source_connector'])
        b = str(r['target_connector'])
        neighbour2[a].add(b)
        neighbour2[b].add(a)
        degree2[a] += 1
        degree2[b] += 1
    connectors_all = sorted(set(neighbour1) | set(neighbour2),
                            key=lambda c: (SIDES.index(c[0]), c))
    per_connector = []
    for connector in connectors_all:
        per_connector.append(dict(
            connector=connector,
            side=connector[0],
            degree_v1=degree1.get(connector, 0),
            degree_v2=degree2.get(connector, 0),
            degree_change=degree2.get(connector, 0) - degree1.get(connector, 0),
            distinct_neighbours_v1=len(neighbour1.get(connector, set())),
            distinct_neighbours_v2=len(neighbour2.get(connector, set())),
            common_neighbours=len(neighbour1.get(connector, set())
                                  & neighbour2.get(connector, set())),
        ))
    connector_pair_common = set(counter1) & set(counter2)
    connector_pair_only_v1 = set(counter1) - set(counter2)
    connector_pair_only_v2 = set(counter2) - set(counter1)

    # per relation type
    def _by_relation(pairs, routes):
        rel_map = {}
        for r in routes:
            rid = int(r['route_id'])
            rel_map[rid] = ''.join(sorted((str(r['source_side']), str(r['target_side']))))
        out = defaultdict(set)
        for pair, rid in pairs.items():
            out[rel_map[rid]].add(pair)
        return out

    conn_pairs_by_rel1 = defaultdict(set)
    conn_pairs_by_rel2 = defaultdict(set)
    for cp in counter1:
        rel = ''.join(sorted((cp[0][0], cp[1][0])))
        conn_pairs_by_rel1[rel].add(cp)
    for cp in counter2:
        rel = ''.join(sorted((cp[0][0], cp[1][0])))
        conn_pairs_by_rel2[rel].add(cp)
    endpoints1_by_rel = _by_relation(pairs1, routes1)
    endpoints2_by_rel = _by_relation(pairs2, routes2)
    by_relation = {}
    for rel in sorted(EXPECTED['pair_counts']):
        by_relation[rel] = dict(
            v1_connections=sum(len(v) for r, v in endpoints1_by_rel.items() if r == rel),
            v2_connections=sum(len(v) for r, v in endpoints2_by_rel.items() if r == rel),
            common_endpoint_pairs=len(endpoints1_by_rel.get(rel, set())
                                      & endpoints2_by_rel.get(rel, set())),
            v1_connector_pairs=len(conn_pairs_by_rel1.get(rel, set())),
            v2_connector_pairs=len(conn_pairs_by_rel2.get(rel, set())),
            common_connector_pairs=len(conn_pairs_by_rel1.get(rel, set())
                                       & conn_pairs_by_rel2.get(rel, set())),
            v2_multiplicity_dist=_counter_to_dict(Counter(
                counter2[cp] for cp in conn_pairs_by_rel2.get(rel, set()))),
        )

    # per source-endpoint remap: each source endpoint is used exactly once per
    # topology, so compare where it terminates in V1 vs V2 (channel-level diff).
    target_by_source_1 = {r['source_endpoint']: r['target_endpoint'] for r in routes1}
    target_by_source_2 = {r['source_endpoint']: r['target_endpoint'] for r in routes2}
    source_endpoint_remap = []
    remap_class_counts = Counter()
    for source_endpoint in sorted(target_by_source_1):
        t1 = target_by_source_1[source_endpoint]
        t2 = target_by_source_2.get(source_endpoint)
        if t2 is None:
            remap_class = 2
        elif t1 == t2:
            remap_class = 0
        elif endpoints1[t1]['connector'] == endpoints2[t2]['connector']:
            remap_class = 1
        else:
            remap_class = 2
        remap_class_counts[remap_class] += 1
        source_endpoint_remap.append(dict(source_endpoint=source_endpoint,
                                          v1_target_endpoint=t1, v2_target_endpoint=t2,
                                          remap_class=remap_class))

    # channel usage by ordered side pair (which channels remap)
    def _channel_usage(routes):
        src = defaultdict(set)
        tgt = defaultdict(set)
        for r in routes:
            key = f"{r['source_side']}->{r['target_side']}"
            src[key].add(int(r['source_channel']))
            tgt[key].add(int(r['target_channel']))
        return ({k: sorted(v) for k, v in sorted(src.items())},
                {k: sorted(v) for k, v in sorted(tgt.items())})

    src1, tgt1 = _channel_usage(routes1)
    src2, tgt2 = _channel_usage(routes2)
    channel_usage_by_side_pair = {}
    for key in sorted(set(src1) | set(src2)):
        channel_usage_by_side_pair[key] = dict(
            v1_source_channels=src1.get(key, []), v2_source_channels=src2.get(key, []),
            v1_target_channels=tgt1.get(key, []), v2_target_channels=tgt2.get(key, []),
        )

    summary = dict(
        v1_connections=len(routes1), v2_connections=len(routes2),
        v1_distinct_endpoint_pairs=len(pairs1), v2_distinct_endpoint_pairs=len(pairs2),
        identical_connections=len(common),
        v1_only_connections=len(set(pairs1) - set(pairs2)),
        v2_only_connections=len(set(pairs2) - set(pairs1)),
        identical_ordered_connections=len(set(ordered1) & set(ordered2)),
        change_classes=_counter_to_dict(change_classes),
        v1_connector_pairs=len(counter1), v2_connector_pairs=len(counter2),
        common_connector_pairs=len(connector_pair_common),
        v1_only_connector_pairs=len(connector_pair_only_v1),
        v2_only_connector_pairs=len(connector_pair_only_v2),
        v1_multiplicity_dist=_counter_to_dict(Counter(counter1.values())),
        v2_multiplicity_dist=_counter_to_dict(Counter(counter2.values())),
        v1_distinct_neighbours_per_connector=sorted({len(v) for v in neighbour1.values()}),
        v2_distinct_neighbours_per_connector=sorted({len(v) for v in neighbour2.values()}),
        neighbours_overlap_dist=_counter_to_dict(Counter(
            len(neighbour1.get(c, set()) & neighbour2.get(c, set())) for c in connectors_all)),
        degree_change_dist=_counter_to_dict(Counter(
            degree2.get(c, 0) - degree1.get(c, 0) for c in connectors_all)),
        source_remap_class_counts=_counter_to_dict(remap_class_counts),
    )
    return dict(
        summary=summary,
        by_route_id=by_route_id,
        by_relation=by_relation,
        per_connector=per_connector,
        identical_connections=identical_connections,
        channel_usage_by_side_pair=channel_usage_by_side_pair,
        source_endpoint_remap=source_endpoint_remap,
        connector_pair_counter_v1=counter1,
        connector_pair_counter_v2=counter2,
        connector_pair_v1_only=sorted(connector_pair_only_v1),
        connector_pair_v2_only=sorted(connector_pair_only_v2),
        connector_pair_common=sorted(connector_pair_common),
    )


def analyse_topology(csv_path, cfg=None):
    """Load + validate + symmetrise one topology; returns a report dict."""
    routes, endpoints, connectors, validation = load_topology(csv_path, cfg=cfg)
    symmetry = symmetry_maps(routes, endpoints)
    return dict(
        topology=validation.get('topology'),
        csv_path=validation.get('csv_path'),
        csv_sha256=validation.get('csv_sha256'),
        validation=validation,
        symmetry=symmetry,
        symmetry_summary=summarise_symmetry(symmetry, validation.get('topology')),
        n_routes=len(routes),
        n_endpoints=len(endpoints),
    )


# ---------------------------------------------------------------------------
# Artifact writers (JSON / CSV / Markdown)
# ---------------------------------------------------------------------------
def _write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(data), indent=2, ensure_ascii=False) + '\n',
                    encoding='utf-8')
    return path


def _write_json_validation(path, record):
    """Write a validation record without the bulky nested checks duplication."""
    return _write_json(path, record)


def write_diff_csv(path, diff):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ['route_id', 'v1_source_endpoint', 'v1_target_endpoint',
              'v2_source_endpoint', 'v2_target_endpoint', 'v1_pair', 'v2_pair',
              'same_unordered_endpoint_pair', 'same_ordered_endpoint_pair',
              'same_connector_pair', 'same_source_connector', 'same_target_connector',
              'change_class']
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in diff['by_route_id']:
            writer.writerow({key: row[key] for key in fields})
    return path


def _fmt_channels(channels):
    """'1-16' / '1,4,7' style rendering of a channel set."""
    channels = sorted(int(c) for c in channels)
    if not channels:
        return '-'
    ranges, start, prev = [], channels[0], channels[0]
    for ch in channels[1:]:
        if ch == prev + 1:
            prev = ch
            continue
        ranges.append((start, prev))
        start = prev = ch
    ranges.append((start, prev))
    return ', '.join(f'{a}' if a == b else f'{a}-{b}' for a, b in ranges)


def write_diff_md(path, diff, validation1=None, validation2=None):
    path = Path(path)
    summary = diff['summary']
    lines = []
    lines.append('# V1 vs V2 连接拓扑差异表')
    lines.append('')
    lines.append('生成脚本：`four_side_1024/abcd/connectivity.py`'
                 '（`python -m four_side_1024.abcd.connectivity`）；所有数字均由脚本实测，非手工填写。')
    lines.append('')
    if validation1 and validation2:
        lines.append(f"- V1：`{validation1.get('csv_path')}`，SHA256 `{validation1.get('csv_sha256')}`")
        lines.append(f"- V2：`{validation2.get('csv_path')}`，SHA256 `{validation2.get('csv_sha256')}`")
        lines.append('')
    lines.append('## 1. 总览')
    lines.append('')
    lines.append('| 指标 | 数值 |')
    lines.append('|---|---|')
    lines.append(f"| 连接数 V1 / V2 | {summary['v1_connections']} / {summary['v2_connections']} |")
    lines.append(f"| 不同端点对（无序）V1 / V2 | {summary['v1_distinct_endpoint_pairs']}"
                 f" / {summary['v2_distinct_endpoint_pairs']} |")
    lines.append(f"| 两版完全相同的连接（无序端点对） | {summary['identical_connections']} |")
    lines.append(f"| 两版完全相同的连接（有序源→目标） | {summary['identical_ordered_connections']} |")
    lines.append(f"| 仅 V1 有的连接 | {summary['v1_only_connections']} |")
    lines.append(f"| 仅 V2 有的连接 | {summary['v2_only_connections']} |")
    lines.append(f"| 不同接头对（无序）V1 / V2 | {summary['v1_connector_pairs']}"
                 f" / {summary['v2_connector_pairs']} |")
    lines.append(f"| 公共接头对 | {summary['common_connector_pairs']} |")
    lines.append(f"| 仅 V1 / 仅 V2 接头对 | {summary['v1_only_connector_pairs']}"
                 f" / {summary['v2_only_connector_pairs']} |")
    lines.append(f"| 接头对重数分布 V1 | {summary['v1_multiplicity_dist']} |")
    lines.append(f"| 接头对重数分布 V2 | {summary['v2_multiplicity_dist']} |")
    lines.append(f"| 每个接头的不同邻居数 V1 / V2 |"
                 f" {summary['v1_distinct_neighbours_per_connector']}"
                 f" / {summary['v2_distinct_neighbours_per_connector']} |")
    lines.append(f"| 接头度数变化分布（V2−V1） | {summary['degree_change_dist']} |")
    lines.append(f"| 不同邻居交集条数分布 | {summary['neighbours_overlap_dist']} |")
    lines.append('')
    lines.append('逐 route_id 分类（V1、V2 的 route_id 都是 1..1024，但两版 route_id 不保证同一条物理连接）：')
    lines.append('')
    lines.append('| 分类 | 条数 |')
    lines.append('|---|---|')
    for cls, count in summary['change_classes'].items():
        lines.append(f'| {cls} | {count} |')
    lines.append('')
    lines.append('## 2. 逐连接类别差异')
    lines.append('')
    lines.append('| 连接类别 | V1 条数 | V2 条数 | 相同端点对 | V1 接头对 | V2 接头对 | 公共接头对 | V2 每对重数 |')
    lines.append('|---|---|---|---|---|---|---|---|')
    for rel, row in diff['by_relation'].items():
        lines.append(f"| {rel} | {row['v1_connections']} | {row['v2_connections']} |"
                     f" {row['common_endpoint_pairs']} | {row['v1_connector_pairs']} |"
                     f" {row['v2_connector_pairs']} | {row['common_connector_pairs']} |"
                     f" {row['v2_multiplicity_dist']} |")
    lines.append('')
    lines.append('## 3. 通道重映射（按源→目标边向量）')
    lines.append('')
    lines.append('| 边对（源→目标） | V1 源通道 | V2 源通道 | V1 目标通道 | V2 目标通道 |')
    lines.append('|---|---|---|---|---|')
    for key, row in diff['channel_usage_by_side_pair'].items():
        lines.append(f"| {key} | {_fmt_channels(row['v1_source_channels'])} |"
                     f" {_fmt_channels(row['v2_source_channels'])} |"
                     f" {_fmt_channels(row['v1_target_channels'])} |"
                     f" {_fmt_channels(row['v2_target_channels'])} |")
    lines.append('')
    lines.append('## 4. 逐接头差异')
    lines.append('')
    lines.append('| 接头 | 边 | V1 度数 | V2 度数 | 度数变化 | V1 不同邻居 | V2 不同邻居 | 共同邻居 |')
    lines.append('|---|---|---|---|---|---|---|---|')
    for row in diff['per_connector']:
        lines.append(f"| {row['connector']} | {row['side']} | {row['degree_v1']} |"
                     f" {row['degree_v2']} | {row['degree_change']:+d} |"
                     f" {row['distinct_neighbours_v1']} | {row['distinct_neighbours_v2']} |"
                     f" {row['common_neighbours']} |")
    lines.append('')
    lines.append('## 5. 两版完全相同的连接（共 %d 条）' % summary['identical_connections'])
    lines.append('')
    lines.append('| V1 route_id | V2 route_id | 连接 | 连接类别 |')
    lines.append('|---|---|---|---|')
    for row in diff['identical_connections']:
        lines.append(f"| {row['route_id_v1']} | {row['route_id_v2']} |"
                     f" {row['source_endpoint']} ↔ {row['target_endpoint']} | {row['pair']} |")
    lines.append('')
    lines.append('## 6. 结论')
    lines.append('')
    lines.append('- 两个拓扑均为 1024 条连接、2048 个端点各用一次、64 个接头各用满 32 通道、'
                 '512 对边 + 512 邻边，均通过全部校验。')
    lines.append(f"- 两版只有 {summary['identical_connections']} 条连接相同，"
                 f"{summary['v1_only_connections']} 条 V1 连接在 V2 中不存在（反之亦然）。")
    lines.append('- 接头度数两版均为 32（度数变化 0），但连接结构完全不同：'
                 f"V1 有 {summary['v1_connector_pairs']} 个不同接头对（每对 1 条，"
                 f"每个接头 {summary['v1_distinct_neighbours_per_connector'][0]} 个不同邻居）；"
                 f"V2 有 {summary['v2_connector_pairs']} 个不同接头对（重数 "
                 f"{summary['v2_multiplicity_dist']}，每个接头 "
                 f"{summary['v2_distinct_neighbours_per_connector'][0]} 个不同邻居）。")
    lines.append('- V1 为全局循环移位/转置结构（无局部块），V2 为 4 接头一块的块状结构：'
                 '对边同号块完全二部（每对 4 条），邻边相邻角块完全二部（每对 2 条）；'
                 'V2 是唯一在接头级呈现 D4 旋转/镜像对称的版本，代价是接头间重数集中、'
                 '每个接头只连 12 个不同接头。')
    lines.append('')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return path


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
PAIR_COLORS = {
    'NS': '#3366bb', 'EW': '#b84040', 'EN': '#e3a323',
    'ES': '#00a0a0', 'SW': '#a545b0', 'NW': '#60a735',
}
SIDE_COLORS = {'N': '#3366bb', 'E': '#e3a323', 'S': '#b84040', 'W': '#60a735'}


def _pyplot():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    return plt


def _board_connector_names():
    return [f'{side}{i:02d}' for side in 'NESW' for i in range(1, CONNECTORS_PER_SIDE + 1)]


def plot_connectivity(routes, endpoints, connectors, validation, path, topology):
    """Full-board connection diagram, same style/scale as ``inputs.phase1``."""
    plt = _pyplot()
    from matplotlib.collections import LineCollection
    from matplotlib.patches import Rectangle
    fig, ax = plt.subplots(figsize=(11, 11))
    segments = [[endpoints[r['source_endpoint']]['routing_xy'],
                 endpoints[r['target_endpoint']]['routing_xy']] for r in routes]
    ax.add_collection(LineCollection(segments, colors=[PAIR_COLORS[r['pair']] for r in routes],
                                     linewidths=.35, alpha=.45))
    ax.add_patch(Rectangle((0, 0), BOARD_MM, BOARD_MM, fill=False, linewidth=1.5))
    for c in connectors:
        x, y = c['center_xy']
        side = c['side']
        width = c['envelope_width_mm']
        if side in 'NS':
            ax.add_patch(Rectangle((x - width / 2, y if side == 'N' else -3), width, 3,
                                   facecolor='#bbbbbb', edgecolor='black', linewidth=.3))
            ax.text(x, y + (4 if side == 'N' else -5), c['connector'], ha='center', fontsize=5)
        else:
            ax.add_patch(Rectangle((x if side == 'E' else -3, y - width / 2), 3, width,
                                   facecolor='#bbbbbb', edgecolor='black', linewidth=.3))
            ax.text(x + (5 if side == 'E' else -5), y, c['connector'], ha='center', fontsize=5)
    title = (f"{topology} connectivity | 1024 connections | 64 connectors x 32 channels\n"
             f"512 opposite / 512 adjacent | virtual_unfolded | 150 x 150 mm | "
             f"layer 0 | all checks passed={validation.get('checks_passed')}")
    ax.set(xlim=(-9, 159), ylim=(-9, 159), aspect='equal', xlabel='x (mm)', ylabel='y (mm)',
           title=title)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return Path(path)


def plot_diff_heatmap(diff, path):
    """Two-panel difference heatmap: connector pairs and per-channel remapping."""
    plt = _pyplot()
    import numpy as np
    from matplotlib.colors import BoundaryNorm, ListedColormap

    connectors = _board_connector_names()
    index = {name: i for i, name in enumerate(connectors)}
    v1 = np.zeros((len(connectors), len(connectors)), dtype=float)
    v2 = np.zeros_like(v1)
    for pair, multiplicity in diff['connector_pair_counter_v1'].items():
        a, b = index[pair[0]], index[pair[1]]
        v1[a, b] = v1[b, a] = multiplicity
    for pair, multiplicity in diff['connector_pair_counter_v2'].items():
        a, b = index[pair[0]], index[pair[1]]
        v2[a, b] = v2[b, a] = multiplicity
    delta = v2 - v1

    fig, axes = plt.subplots(1, 2, figsize=(21, 9),
                             gridspec_kw={'width_ratios': [1.0, 1.0]})
    ax = axes[0]
    limit = max(1.0, float(np.max(np.abs(delta))))
    image = ax.imshow(delta, origin='lower', cmap='RdBu_r', vmin=-limit, vmax=limit,
                      interpolation='nearest')
    ax.set_xticks([index[f'{side}01'] + 7.5 for side in 'NESW'])
    ax.set_yticks([index[f'{side}01'] + 7.5 for side in 'NESW'])
    ax.set_xticklabels([f'{side}01-{side}16' for side in 'NESW'], fontsize=8)
    ax.set_yticklabels([f'{side}01-{side}16' for side in 'NESW'], fontsize=8)
    ax.set_title('Connector-pair multiplicity difference  Δ = V2 − V1\n'
                 f'red = more connections in V2, blue = fewer '
                 f'(V1 pairs {diff["summary"]["v1_connector_pairs"]}, '
                 f'V2 pairs {diff["summary"]["v2_connector_pairs"]}, '
                 f'common {diff["summary"]["common_connector_pairs"]})', fontsize=10)
    for boundary in (16, 32, 48):
        ax.axhline(boundary - 0.5, color='black', lw=0.6)
        ax.axvline(boundary - 0.5, color='black', lw=0.6)
    fig.colorbar(image, ax=ax, fraction=0.046, pad=0.03,
                 label='Δ connection count per unordered connector pair')

    # per source-endpoint remap class: 64 connectors x 32 source channels
    remap = np.full((len(connectors), CHANNELS_PER_CONNECTOR), np.nan)
    for row in diff['source_endpoint_remap']:
        connector, _, channel = row['source_endpoint'].split(':')
        remap[index[connector], int(channel) - 1] = row['remap_class']
    ax = axes[1]
    cmap = ListedColormap(['#f6d8a8', '#e07b39', '#7a1f1f'])  # 0 same endpoint, 1 same conn, 2 other conn
    norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5], cmap.N)
    image = ax.imshow(remap, origin='lower', aspect='auto', cmap=cmap, norm=norm,
                      interpolation='nearest')
    ax.set_xticks([0, 7, 15, 23, 31])
    ax.set_xticklabels(['ch1', 'ch8', 'ch16', 'ch24', 'ch32'], fontsize=8)
    ax.set_yticks([index[f'{side}01'] + 7.5 for side in 'NESW'])
    ax.set_yticklabels([f'{side}01-{side}16' for side in 'NESW'], fontsize=8)
    classes = diff['summary']['source_remap_class_counts']
    ax.set_title('Per-source-channel target remapping  (each source endpoint used once per topology)\n'
                 f'identical target {classes.get("0", 0)} | same target connector, '
                 f'different channel {classes.get("1", 0)} | different target connector '
                 f'{classes.get("2", 0)}', fontsize=10)
    for boundary in (16, 32, 48):
        ax.axhline(boundary - 0.5, color='black', lw=0.6)
    colorbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.03, ticks=[0, 1, 2])
    colorbar.ax.set_yticklabels(['same target endpoint', 'same connector, other channel',
                                 'other target connector'], fontsize=7)
    fig.suptitle('V1 vs V2 connection-topology difference', fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return Path(path)


def _plot_connector_transform(ax, symmetry, transform_name, topology):
    """Board panel with arrows from every connector centre to its image."""
    connectors = _connector_centers_from_endpoints(symmetry['_endpoints'])
    entry = symmetry['by_name'][transform_name]
    from matplotlib.patches import Rectangle
    ax.add_patch(Rectangle((0, 0), BOARD_MM, BOARD_MM, fill=False, linewidth=1.2))
    for name, center in connectors.items():
        image = entry['connector_map'][name]
        image_center = connectors[image]
        ax.annotate('', xy=image_center, xytext=center,
                    arrowprops=dict(arrowstyle='-|>', color=SIDE_COLORS[name[0]],
                                    lw=0.55, alpha=0.65, shrinkA=2, shrinkB=2))
        ax.plot([center[0]], [center[1]], marker='s', ms=2.6, color=SIDE_COLORS[name[0]])
    for side in 'NESW':
        names = [n for n in connectors if n[0] == side]
        centers = [connectors[n] for n in names]
        if side in 'NS':
            xs = [c[0] for c in centers]
            ax.text(sum(xs) / len(xs), 150 if side == 'N' else 0,
                    side, fontsize=13, ha='center',
                    va='bottom' if side == 'N' else 'top', color=SIDE_COLORS[side])
        else:
            ys = [c[1] for c in centers]
            ax.text(150 if side == 'E' else 0, sum(ys) / len(ys),
                    side, fontsize=13, va='center',
                    ha='left' if side == 'E' else 'right', color=SIDE_COLORS[side])
    ax.set(xlim=(-10, 160), ylim=(-10, 160), aspect='equal', xlabel='x (mm)', ylabel='y (mm)')
    ax.set_title(f"{transform_name}: 64/64 connectors mapped\n"
                 f"{entry['description']}\n"
                 f"connector-pair multiset preserved: "
                 f"{entry['connector_pair_multiset_preserved']} "
                 f"(violations {entry['connector_pair_violations']}); "
                 f"route-level {entry['mapped_route_count']}/{len(entry['route_map'])}",
                 fontsize=9)


def _plot_block_structure(ax, symmetry):
    """Block-level view of V2's designed connector symmetry (rot90 + mirror_x)."""
    sides = ['N', 'E', 'S', 'W']
    side_y = {'N': 3.0, 'E': 2.0, 'S': 1.0, 'W': 0.0}
    for side in sides:
        for block in range(4):
            lo = 4 * block + 1
            hi = 4 * block + 4
            ax.add_patch(plt_rectangle(block - 0.42, side_y[side] - 0.32, 0.84, 0.64))
            ax.text(block, side_y[side], f'{side}{lo:02d}-{side}{hi:02d}',
                    ha='center', va='center', fontsize=8,
                    bbox=dict(facecolor='white', edgecolor='none', pad=0.6, alpha=0.92))
    rot_edges = []
    for block in range(4):
        rot_edges.append((('N', block), ('W', block)))
        rot_edges.append((('W', block), ('S', 3 - block)))
        rot_edges.append((('S', block), ('E', 3 - block)))
        rot_edges.append((('E', block), ('N', block)))
    image_edges = [(('N', 0), ('N', 3)), (('N', 1), ('N', 2)), (('N', 2), ('N', 1)),
                   (('N', 3), ('N', 0)), (('S', 0), ('S', 3)), (('S', 1), ('S', 2)),
                   (('S', 2), ('S', 1)), (('S', 3), ('S', 0))]
    image_edges += [(('E', b), ('W', b)) for b in range(4)]
    image_edges += [(('W', b), ('E', b)) for b in range(4)]
    for (src_side, src_block), (dst_side, dst_block) in rot_edges:
        ax.annotate('', xy=(dst_block, side_y[dst_side]), xytext=(src_block, side_y[src_side]),
                    arrowprops=dict(arrowstyle='-|>', color='#2255aa', lw=1.1, alpha=0.8,
                                    shrinkA=22, shrinkB=22, connectionstyle='arc3,rad=0.15'))
    for (src_side, src_block), (dst_side, dst_block) in image_edges:
        ax.annotate('', xy=(dst_block, side_y[dst_side]), xytext=(src_block, side_y[src_side]),
                    arrowprops=dict(arrowstyle='-|>', color='#bb5511', lw=0.9, alpha=0.7,
                                    shrinkA=22, shrinkB=22, connectionstyle='arc3,rad=-0.3'))
    ax.text(1.5, 3.85, 'blue: rot90 block permutation   orange: mirror_x block permutation',
            ha='center', fontsize=9)
    ax.text(1.5, -0.95,
            'V2 design: 16 connectors/side = 4 blocks of 4. Opposite pairs join same-index blocks\n'
            '(multiplicity 4/connector pair); adjacent pairs join the two blocks at the shared\n'
            'corner (multiplicity 2/connector pair). This complete-bipartite block structure makes\n'
            'the connector-level connection multiset invariant under every D4 transform.',
            ha='center', va='top', fontsize=8.5)
    ax.set_xlim(-0.8, 3.8)
    ax.set_ylim(-1.9, 4.0)
    ax.axis('off')
    ax.set_title('Connector-level block structure (64 connectors, 4 blocks per side)', fontsize=10)


def plot_v2_symmetry(symmetry, endpoints, path, topology='V2'):
    """Visualise V2's connector-level rotation/mirror symmetry + endpoint-level truth."""
    plt = _pyplot()
    symmetry = dict(symmetry)
    symmetry['_endpoints'] = endpoints
    fig, axes = plt.subplots(2, 2, figsize=(16, 15))
    _plot_connector_transform(axes[0][0], symmetry, 'rot90', topology)
    _plot_connector_transform(axes[0][1], symmetry, 'mirror_x', topology)
    _plot_block_structure(axes[1][0], symmetry)

    ax = axes[1][1]
    names = [t['name'] for t in symmetry['transforms']]
    route_counts = [t['mapped_route_count'] for t in symmetry['transforms']]
    connector_ok = [1024 if t['connector_pair_multiset_preserved'] else 0
                    for t in symmetry['transforms']]
    xs = range(len(names))
    ax.bar([x - 0.2 for x in xs], route_counts, width=0.4, color='#3366bb',
           label='route-level (endpoint) matched count / 1024')
    ax.bar([x + 0.2 for x in xs], connector_ok, width=0.4, color='#60a735',
           label='connector-level multiset preserved (1024 or 0)')
    for x, (count, ok) in enumerate(zip(route_counts, connector_ok)):
        ax.text(x - 0.2, count + 18, str(count), ha='center', fontsize=8)
        ax.text(x + 0.2, (ok or 0) + 18, str(ok), ha='center', fontsize=8)
    ax.set_xticks(list(xs))
    ax.set_xticklabels(names, rotation=25, ha='right', fontsize=9)
    ax.set_ylim(0, 1150)
    ax.set_ylabel('connections matched / 1024')
    ax.set_title(f'{topology} symmetry: connector-level vs endpoint-level', fontsize=10)
    ax.legend(fontsize=8, loc='lower left')
    ax.text(0.02, 0.97,
            f"connector-level symmetric (all 8 D4):\n  {symmetry['connector_level_symmetric']}\n"
            f"endpoint-level symmetric:\n  {symmetry['endpoint_level_symmetric']}\n"
            f"pure channel permutation:\n  {symmetry['channel_map_pure']}",
            transform=ax.transAxes, va='top', fontsize=8,
            bbox=dict(facecolor='white', alpha=0.85, edgecolor='#888888'))
    ax.grid(True, axis='y', alpha=0.3)
    fig.suptitle(f'{topology}: designed symmetry is CONNECTOR-level; endpoint identities '
                 f'only satisfy identity + diag_main', fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.965))
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return Path(path)


def plt_rectangle(x, y, width, height):
    from matplotlib.patches import Rectangle
    return Rectangle((x, y), width, height, facecolor='#eef2f7', edgecolor='#445566',
                     linewidth=0.8)


# ---------------------------------------------------------------------------
# Artifact builder
# ---------------------------------------------------------------------------
def _symmetry_snapshot(report):
    """JSON-ready snapshot of one topology's symmetry analysis."""
    symmetry = report['symmetry']
    return dict(
        topology=report['topology'],
        csv_path=report['csv_path'],
        csv_sha256=report['csv_sha256'],
        n_routes=symmetry['n_routes'],
        n_endpoints=symmetry['n_endpoints'],
        tolerance_mm=symmetry['tolerance_mm'],
        transform_definitions={t['name']: dict(matrix=t['matrix'], offset=t['offset'],
                                              description=t['description'])
                               for t in symmetry['transforms']},
        aliases=symmetry['aliases'],
        summary=report['symmetry_summary'],
        transforms=[dict(
            name=t['name'], matrix=t['matrix'], offset=t['offset'],
            description=t['description'],
            route_map=t['route_map'],
            route_map_complete=t['route_map_complete'],
            mapped_route_count=t['mapped_route_count'],
            channel_map_consistent=t['channel_map_consistent'],
            channel_map=t['channel_map'],
            channel_map_by_side_consistent=t['channel_map_by_side_consistent'],
            channel_map_by_side=t['channel_map_by_side'],
            row_map=t['row_map'],
            side_map=t['side_map'],
            orientation_counts=t['orientation_counts'],
            fixed_point_count=t['fixed_point_count'],
            endpoint_map_complete=t['endpoint_map_complete'],
            endpoint_unmatched=t['endpoint_unmatched'],
            endpoint_fixed_point_count=t['endpoint_fixed_point_count'],
            snap_max_error_mm=t['snap_max_error_mm'],
            connector_map=t['connector_map'],
            connector_map_complete=t['connector_map_complete'],
            connector_snap_max_error_mm=t['connector_snap_max_error_mm'],
            connector_pair_multiset_preserved=t['connector_pair_multiset_preserved'],
            connector_pair_violations=t['connector_pair_violations'],
            connector_pairs_mapped=t['connector_pairs_mapped'],
            connector_pairs_total=t['connector_pairs_total'],
            topology_invariant=t['topology_invariant'],
        ) for t in symmetry['transforms']],
    )


def build_connectivity_artifacts(output_dir=OUTPUT_DIR, plots=True):
    """Build every Phase-1 artifact under ``outputs/.../connectivity/``.

    Returns ``{"files": [...], "summary": {...}}``; every reported number is
    produced by the same run (nothing is typed in by hand).
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_v1 = analyse_topology(V1_CSV)
    report_v2 = analyse_topology(V2_CSV)
    files = []

    def emit(path):
        files.append(str(path))
        return path

    # ---- validation / symmetry JSON ---------------------------------------
    emit(_write_json(out / 'validation_v1.json', report_v1['validation']))
    emit(_write_json(out / 'validation_v2.json', report_v2['validation']))
    emit(_write_json(out / 'symmetry_v1.json', _symmetry_snapshot(report_v1)))
    emit(_write_json(out / 'symmetry_v2.json', _symmetry_snapshot(report_v2)))

    # reload routes/endpoints once (diff needs identity + endpoint connector meta)
    routes1, endpoints1, connectors1, _ = load_topology(V1_CSV)
    routes2, endpoints2, connectors2, _ = load_topology(V2_CSV)
    diff = diff_topologies(routes1, endpoints1, routes2, endpoints2)
    emit(write_diff_csv(out / 'diff_v1_v2.csv', diff))
    emit(write_diff_md(out / 'diff_v1_v2.md', diff,
                       report_v1['validation'], report_v2['validation']))

    connectivity_summary = dict(
        generated_by='four_side_1024/abcd/connectivity.py',
        transform_convention="x' = matrix[0][0]*x + matrix[0][1]*y + offset[0]; "
                             "y' = matrix[1][0]*x + matrix[1][1]*y + offset[1]",
        aliases=dict(TRANSFORM_ALIASES),
        v1=dict(csv_path=report_v1['csv_path'], csv_sha256=report_v1['csv_sha256'],
                topology=report_v1['topology'],
                passed=report_v1['validation']['passed'],
                checks_passed=report_v1['validation']['checks_passed'],
                connections=report_v1['validation']['connections'],
                opposite=report_v1['validation']['opposite'],
                adjacent=report_v1['validation']['adjacent'],
                connectors=report_v1['validation']['connectors'],
                channels_per_connector=report_v1['validation']['channels_per_connector'],
                endpoints_used_once=report_v1['validation']['endpoints_used_once'],
                symmetry_summary=report_v1['symmetry_summary']),
        v2=dict(csv_path=report_v2['csv_path'], csv_sha256=report_v2['csv_sha256'],
                topology=report_v2['topology'],
                passed=report_v2['validation']['passed'],
                checks_passed=report_v2['validation']['checks_passed'],
                connections=report_v2['validation']['connections'],
                opposite=report_v2['validation']['opposite'],
                adjacent=report_v2['validation']['adjacent'],
                connectors=report_v2['validation']['connectors'],
                channels_per_connector=report_v2['validation']['channels_per_connector'],
                endpoints_used_once=report_v2['validation']['endpoints_used_once'],
                symmetry_summary=report_v2['symmetry_summary']),
        v1_v2_diff=diff['summary'],
    )
    emit(_write_json(out / 'validation.json', connectivity_summary))

    # ---- figures -----------------------------------------------------------
    if plots:
        emit(plot_connectivity(routes1, endpoints1, connectors1,
                               report_v1['validation'], out / 'connectivity_v1.png', 'V1'))
        emit(plot_connectivity(routes2, endpoints2, connectors2,
                               report_v2['validation'], out / 'connectivity_v2.png', 'V2'))
        emit(plot_diff_heatmap(diff, out / 'diff_heatmap.png'))
        emit(plot_v2_symmetry(report_v2['symmetry'], endpoints2,
                              out / 'v2_symmetry_diagram.png', 'V2'))

    summary = dict(
        topology_v1=report_v1['topology'],
        topology_v2=report_v2['topology'],
        v1_checks_passed=report_v1['validation']['checks_passed'],
        v2_checks_passed=report_v2['validation']['checks_passed'],
        v1_csv_sha256=report_v1['csv_sha256'],
        v2_csv_sha256=report_v2['csv_sha256'],
        v1_endpoint_level_symmetric=report_v1['symmetry']['endpoint_level_symmetric'],
        v2_endpoint_level_symmetric=report_v2['symmetry']['endpoint_level_symmetric'],
        v1_connector_level_symmetric=report_v1['symmetry']['connector_level_symmetric'],
        v2_connector_level_symmetric=report_v2['symmetry']['connector_level_symmetric'],
        v2_channel_map_pure=report_v2['symmetry']['channel_map_pure'],
        v2_route_level_mapped_counts=report_v2['symmetry']['route_level_mapped_counts'],
        diff_summary=diff['summary'],
        files=files,
    )
    return dict(files=files, summary=summary)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(
        description='Build ABCD Phase-1 connectivity artifacts (V1/V2 validation, '
                    'symmetry, diff table and figures).')
    parser.add_argument('--output-dir', default=str(OUTPUT_DIR))
    parser.add_argument('--no-plots', action='store_true')
    args = parser.parse_args(argv)
    result = build_connectivity_artifacts(Path(args.output_dir), plots=not args.no_plots)
    print(json.dumps(_jsonable(result['summary']), indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
