"""Shared instrumentation for the D56 1024-channel baseline failure diagnosis.

The functions here re-run the *legacy adapter* search (``four_side_1024.legacy_adapter``)
with the same modules/functions and the same deterministic order, but
(a) instrument every candidate, (b) allow an unlimited time/evaluation budget,
and (c) allow controlled group-order experiments and template extensions.

Nothing in ``four_side_1024`` is modified.  All geometry construction and every
accept/reject decision uses the unmodified legacy modules:
``legacy_rules.LegacyRules`` (AST-extracted ``sn_calc``/``noCross``),
``legacy_geometry.opposite/adjacent/canonicalize/transform_primitives``,
``geometry.validate`` and ``conflicts.ConflictIndex``.

All paths are relative to the OpticalWaveguideRouter2D project root.
"""
from __future__ import annotations

import json
import math
import random
import sys
import time
from collections import Counter, OrderedDict
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from four_side_1024.inputs import DEFAULT_INPUT, config, load  # noqa: E402
from four_side_1024.legacy_adapter import GROUP_ORDER, branch_for_source, track_schedule  # noqa: E402
from four_side_1024.legacy_rules import LegacyRules, nodesMTset  # noqa: E402
from four_side_1024.legacy_geometry import (  # noqa: E402
    BOARD, TOL, _check, _orthogonal_quarters, _point,
    adjacent, canonicalize, opposite, transform_primitives,
)
from four_side_1024.geometry import length, validate  # noqa: E402
from four_side_1024.conflicts import ConflictIndex  # noqa: E402
from four_side_1024.legacy_rules import WGyset  # noqa: E402

BASELINE = PROJECT / 'outputs/four_side_1024_legacy_two_branch_v2'
DATA = Path(__file__).resolve().parent / 'data'
DATA.mkdir(parents=True, exist_ok=True)

# Rejection categories the legacy adapter records, in its own priority order.
CONFLICT_KEYS = ('spacing_pairs', 'overlap_pairs', 'touch_pairs',
                 'crossing_zone_overlap_pairs', 'self_intersections',
                 'self_overlaps', 'self_spacing_violations', 'discontinuities')


def base_track_y(pitch=0.175):
    return [round(y / 1000, 3) for y in range(5000, 145000, int(round(pitch * 1000)))]


def load_inputs(path=DEFAULT_INPUT):
    routes, endpoints, connectors, validation = load(path)
    return routes, endpoints, connectors, validation


class GroupContext:
    """Everything ``route_original`` builds per pair group (verbatim)."""

    def __init__(self, pair, group, endpoints, cfg):
        self.pair = pair
        self.group = list(group)
        example = self.group[0]
        self.source_side = example['source_side']
        self.target_side = example['target_side']
        self.branch = branch_for_source(self.source_side)
        self.source_above = self.branch == 'above2below'
        p0 = endpoints[example['source_endpoint']]['routing_xy']
        q0 = endpoints[example['target_endpoint']]['routing_xy']
        _, _, self.transform, self.kind = canonicalize(self.source_side, self.target_side, p0, q0)
        self.matrix = np.array(self.transform['matrix'])
        self.offset = np.array(self.transform['offset'])
        src_names = sorted({e['connector'] for e in endpoints.values() if e['side'] == self.source_side},
                           key=lambda name: np.mean([self.canonical(e)[0] for e in endpoints.values()
                                                     if e['connector'] == name]))
        target_axis = 0 if self.kind == 'opposite' else 1
        dst_names = sorted({e['connector'] for e in endpoints.values() if e['side'] == self.target_side},
                           key=lambda name: np.mean([self.canonical(e)[target_axis] for e in endpoints.values()
                                                     if e['connector'] == name]))
        src_x = [[float(self.canonical(e)[0]) for e in endpoints.values() if e['connector'] == name]
                 for name in src_names]
        dst_x = [[float(self.canonical(e)[target_axis]) for e in endpoints.values() if e['connector'] == name]
                 for name in dst_names]
        self.src_names, self.dst_names = src_names, dst_names
        self.target_axis = target_axis
        nodes = nodesMTset(src_x, dst_x, height=BOARD) if self.source_above else nodesMTset(dst_x, src_x, height=BOARD)
        self.nodes = nodes
        self.source_nodes = nodes.MTabove if self.source_above else nodes.MTbelow
        self.target_nodes = nodes.MTbelow if self.source_above else nodes.MTabove
        self.active = {'channel': 1}
        self.rules = LegacyRules(nodes, lambda lx, ly: max(self.active['channel'] - 1 - 6, 4),
                                 r=cfg['min_radius_mm'], height=BOARD)
        pitch = cfg['width_mm'] + cfg['edge_gap_mm']
        self.track_y = base_track_y(pitch)
        if self.kind == 'adjacent':
            direct_y = [float(self.canonical(endpoints[r['target_endpoint']])[1]) for r in self.group]
            direct_y = [BOARD - y for y in direct_y] if self.source_above else direct_y
            self.track_y = sorted(set(self.track_y + direct_y))
        self.tracks = [WGyset(y=y, rEnd=[-1], lEnd=[100]) for y in self.track_y]
        self.ordered = sorted(self.group, key=lambda r: -self.canonical(endpoints[r['source_endpoint']])[0])

    def canonical(self, endpoint):
        return self.matrix @ np.array(endpoint['routing_xy']) + self.offset


def build_contexts(routes, endpoints, cfg, pairs=None):
    pairs = list(GROUP_ORDER) if pairs is None else list(pairs)
    contexts = {}
    for pair in pairs:
        group = [r for r in routes if r['pair'] == pair]
        contexts[pair] = GroupContext(pair, group, endpoints, cfg)
    return contexts


# ---------------------------------------------------------------------------
# Template extension for adjacent routes (question 6): variable terminal turn.
# ---------------------------------------------------------------------------
def adjacent_flexible(p, q, t1, t2, radius=5.0, width=0.05):
    """Canonical S->E adjacent path with *variable* intermediate track and
    terminal turn abscissa.

    ``t1`` is the y of the intermediate horizontal run and ``t2`` the x of the
    terminal vertical run, i.e. vertex list
    ``[p, (p.x, t1), (t2, t1), (t2, q.y), q]``.  All corners use the unchanged
    legacy fixed-radius quarter-circle construction (``_orthogonal_quarters``).
    ``t2 == BOARD - radius`` reproduces ``legacy_geometry.adjacent`` and
    ``t1 == -1`` (sentinel) reproduces its direct-L branch, so this is a strict
    superset of the deployed template and adds no new geometry primitive type.
    """
    p, q = _point(p), _point(q)
    if abs(p[1]) > TOL or abs(q[0] - BOARD) > TOL:
        raise ValueError('adjacent_flexible requires canonical S -> E boundary endpoints')
    if t1 is None:  # direct L
        points = [p, (p[0], q[1]), q]
    else:
        points = [p, (p[0], t1), (t2, t1), (t2, q[1]), q]
    result = _orthogonal_quarters(points, radius)
    return _check(result, p, q, (0., 1.), (1., 0.), radius, width)


def adjacent_flexible_candidates(qy, sx):
    """Candidate stream for the flexible adjacent template.

    Ordered cheapest-first: direct L, original t2=145 three-bend track scan
    (identical order to the deployed algorithm), then a deterministic grid of
    the two new degrees of freedom.  ``t1`` grid is every 0.175 track; ``t2``
    grid is every 2.5 mm plus the original 145, which is enough to show the
    rescue potential without a full 2-D sweep.
    """
    yield ('direct_L', None, None)
    for y in base_track_y():
        yield ('legacy_track', y, 145.)
    t2_grid = [round(5. + 2.5 * k, 6) for k in range(57) if round(5. + 2.5 * k, 6) <= 145.]
    for t1 in base_track_y():
        for t2 in t2_grid:
            yield ('flex', t1, t2)


# ---------------------------------------------------------------------------
# Instrumented search
# ---------------------------------------------------------------------------
class SearchRecorder:
    """Collects per-route and per-evaluation records for one search variant."""

    def __init__(self, record_exact=True, record_scans=False):
        self.record_exact = record_exact
        self.record_scans = record_scans
        self.route_rows = []          # one dict per attempted route
        self.exact = []               # (rid, track_index, y, primary, blocker, dist, nblocks)
        self.scans = []               # (rid, candidate_id, phase, y, extra)
        self.samples = []             # post-hoc geometry legality of rule-rejected candidates
        self.accepted = OrderedDict()  # rid -> accepted record (legacy schema + primitives)
        self.times = Counter()
        self.rejections = Counter()
        self.evaluations = 0

    def add_time(self, key, dt):
        self.times[key] += dt


def _classify_conflict(result):
    """Legacy priority order used by route_original; return first reason."""
    for key in ('spacing_pairs', 'overlap_pairs', 'touch_pairs', 'crossing_zone_overlap_pairs'):
        if result.get(key):
            return key, result[key][0], result.get('minimum_non_crossing_centerline_mm')
    for key in ('self_intersections', 'self_overlaps', 'self_spacing_violations', 'discontinuities'):
        if result.get(key):
            return key, None, None
    return 'other_geometry_conflict', None, None


def _geometry_legality(p, q, kind, y, transform, src_xy, dst_xy, src_inward, dst_inward,
                       index, cfg):
    """Build the deployed template for a rule-rejected candidate and test it."""
    t = time.perf_counter()
    try:
        local = opposite(p, q, y, radius=cfg['min_radius_mm'], width=cfg['width_mm']) if kind == 'opposite' \
            else adjacent(p, q, y, radius=cfg['min_radius_mm'], width=cfg['width_mm'])
    except ValueError:
        return dict(bend_fit=False, validate_ok=False, exact_valid=False, reason='legacy_bend_does_not_fit',
                    blocker=None, distance=None, n_checked=0, elapsed=time.perf_counter() - t)
    try:
        primitives = transform_primitives(local, transform, inverse=True)
    except (ValueError, KeyError):
        return dict(bend_fit=False, validate_ok=False, exact_valid=False, reason='transform_error',
                    blocker=None, distance=None, n_checked=0, elapsed=time.perf_counter() - t)
    errors = validate(primitives, src_xy, dst_xy, src_inward, -np.array(dst_inward),
                      board=BOARD, width=cfg['width_mm'], min_radius=cfg['min_radius_mm'])
    if errors:
        return dict(bend_fit=True, validate_ok=False, exact_valid=False,
                    reason='validate:' + ','.join(sorted(set(errors))), blocker=None,
                    distance=None, n_checked=0, elapsed=time.perf_counter() - t)
    result = index.evaluate(primitives)
    dt = time.perf_counter() - t
    if result['valid']:
        return dict(bend_fit=True, validate_ok=True, exact_valid=True, reason='legal',
                    blocker=None, distance=None, n_checked=result['checked_pairs'], elapsed=dt)
    reason, blocker, dist = _classify_conflict(result)
    return dict(bend_fit=True, validate_ok=True, exact_valid=False, reason=reason, blocker=blocker,
                distance=dist, n_checked=result['checked_pairs'], elapsed=dt)


class Searcher:
    """Budget-free replica of ``legacy_adapter.route_original`` with hooks.

    Parameters
    ----------
    contexts : dict pair -> GroupContext (already created, fresh group state)
    routes, endpoints : legacy input tables
    cfg : legacy config dict
    index : empty ConflictIndex that receives accepted routes (fresh per run)
    recorder : SearchRecorder
    sample_stride : int or None, keep roughly this many rule-rejected samples/route
    stop_after : int or None, stop after this many route attempts (baseline replay)
    template : 'legacy' | 'flex' adjacent template mode
    flex_cache : dict rid -> list of world primitives (precomputed flexible paths)
    """

    def __init__(self, contexts, routes, endpoints, cfg, index, recorder,
                 sample_stride=6, stop_after=None, template='legacy',
                 flex_candidates=None, evaluator=None, register=None,
                 sample_geometry_legality=True):
        self.contexts = contexts
        self.routes = routes
        self.endpoints = endpoints
        self.cfg = cfg
        self.index = index
        self.rec = recorder
        self.sample_stride = sample_stride
        self.stop_after = stop_after
        self.template = template
        self.flex_candidates = flex_candidates
        self.attempted = 0
        self.pitch = cfg['width_mm'] + cfg['edge_gap_mm']
        # Optional custom exact-conflict engine (crossing-policy experiments).
        # ``evaluator(primitives)`` must return the same result-dict keys as
        # ConflictIndex.evaluate; ``register(rid, primitives)`` adds an accepted
        # route to then-current state.
        self.evaluator = evaluator
        self.register = register
        self.sample_geometry_legality = sample_geometry_legality
        self.by_id = {r['route_id']: r for r in routes}
        self._groups_started = set()

    def run_custom(self, route_order):
        """Attempt an arbitrary global route order, one route at a time.

        Group state (legacy MT/WGyset/tracks) is shared through a shallow copy,
        so this reproduces ``route_original``'s state transitions exactly while
        allowing interleaved / rescued / reordered executions.
        """
        import copy as _copy
        for rid in route_order:
            if self.stop_after is not None and self.attempted >= self.stop_after:
                return
            route = self.by_id[rid]
            ctx = self.contexts[route['pair']]
            sub = _copy.copy(ctx)
            sub.ordered = [route]
            self._run_group(sub)

    # -- candidate generation -------------------------------------------------
    def _candidates(self, ctx, rid, qy):
        """Yield the deployed candidate stream; with template='flex' append the
        new variable-terminal-turn candidates after the deployed stream."""
        for i, rule_y, y, mode in track_schedule(ctx.kind, qy, ctx.track_y, ctx.branch):
            yield dict(candidate_id=None, i=i, rule_y=rule_y, y=y, mode=mode,
                       t1=None, t2=None)
        if ctx.kind == 'adjacent' and self.template == 'flex':
            for idx, (t1, t2) in enumerate(self.flex_candidates[rid]):
                yield dict(candidate_id=idx, i=None, rule_y=None, y=t1, mode='flex',
                           t1=t1, t2=t2)

    def _build_flex(self, p, q, cand):
        return adjacent_flexible(p, q, cand['t1'], cand['t2'],
                                 radius=self.cfg['min_radius_mm'],
                                 width=self.cfg['width_mm'])

    # -- main loop ------------------------------------------------------------
    def run(self, pairs=None):
        pairs = list(GROUP_ORDER) if pairs is None else list(pairs)
        for pair in pairs:
            if self.stop_after is not None and self.attempted >= self.stop_after:
                return
            ctx = self.contexts[pair]
            self._run_group(ctx)

    def _run_group(self, ctx):
        cfg = self.cfg
        rec = self.rec
        group_start = time.perf_counter()
        group_success = 0
        for rownum, r in enumerate(ctx.ordered):
            if self.stop_after is not None and self.attempted >= self.stop_after:
                return
            rid = r['route_id']
            src = self.endpoints[r['source_endpoint']]
            dst = self.endpoints[r['target_endpoint']]
            p = ctx.canonical(src)
            q = ctx.canonical(dst)
            i1 = ctx.src_names.index(src['connector'])
            i2 = ctx.dst_names.index(dst['connector'])
            si = ctx.source_nodes[i1].x.index(float(p[0]))
            ti = ctx.target_nodes[i2].x.index(float(q[ctx.target_axis]))
            ctx.active['channel'] = (ti if ctx.source_above else si) + 1
            reasons = Counter()
            blockers = Counter()
            first_blocker = None
            first_blocker_appearances = Counter()
            nearest_blocked_distance = None
            n = 0
            nscan = 0
            chosen = None
            chosen_meta = None
            phase_counts = Counter()
            samples = []
            sample_count = Counter()
            t_route = time.perf_counter()
            qy = float(q[1])
            for cand in self._candidates(ctx, rid, qy):
                scan_start = time.perf_counter()
                nscan += 1
                y, rule_y, i = cand['y'], cand['rule_y'], cand['i']
                legacy_ordinal = i is not None
                phase_counts['scan'] += 1
                # 1) original branch-specific outer predicates
                if legacy_ordinal:
                    order_ok = self._order_ok(ctx, rule_y, i1, i2, ctx.tracks[i])
                else:
                    order_ok = True
                rec.add_time('order', time.perf_counter() - scan_start)
                if not order_ok:
                    reasons['original_track_endpoint_order'] += 1
                    phase_counts['order_fail'] += 1
                    rec.rejections['original_track_endpoint_order'] += 1
                    if self._want_sample(sample_count, 'order'):
                        samples.append(self._sample(ctx, rid, phase='order_reject', cand=cand,
                                                    p=p, q=q, src=src, dst=dst))
                    continue
                # 2) unchanged legacy noCross
                t = time.perf_counter()
                ln_x = float(q[ctx.target_axis]) if ctx.source_above else float(p[0])
                no_cross = ctx.rules.noCross(i2, i1, i, ctx.tracks, _type=ctx.branch, lx=ln_x, ly=0.) \
                    if legacy_ordinal else True
                rec.add_time('nocross', time.perf_counter() - t)
                if not no_cross:
                    reasons['original_noCross'] += 1
                    phase_counts['nocross_fail'] += 1
                    rec.rejections['original_noCross'] += 1
                    if self._want_sample(sample_count, 'nocross'):
                        samples.append(self._sample(ctx, rid, phase='nocross_reject', cand=cand,
                                                    p=p, q=q, src=src, dst=dst))
                    continue
                # 3) legacy template construction
                t = time.perf_counter()
                try:
                    if cand['mode'] == 'flex':
                        local = self._build_flex(p, q, cand)
                    elif ctx.kind == 'opposite':
                        local = opposite(p, q, y, radius=cfg['min_radius_mm'], width=cfg['width_mm'])
                    else:
                        local = adjacent(p, q, y, radius=cfg['min_radius_mm'], width=cfg['width_mm'])
                    primitives = transform_primitives(local, ctx.transform, inverse=True)
                except ValueError:
                    rec.add_time('bend', time.perf_counter() - t)
                    reasons['legacy_bend_does_not_fit'] += 1
                    phase_counts['bend_fail'] += 1
                    rec.rejections['legacy_bend_does_not_fit'] += 1
                    continue
                rec.add_time('bend', time.perf_counter() - t)
                # 4) per-route validation
                t = time.perf_counter()
                errors = validate(primitives, src['routing_xy'], dst['routing_xy'], src['inward'],
                                  -np.array(dst['inward']), board=BOARD,
                                  width=cfg['width_mm'], min_radius=cfg['min_radius_mm'])
                rec.add_time('validate', time.perf_counter() - t)
                if errors:
                    reasons.update(errors)
                    phase_counts['validate_fail'] += 1
                    continue
                n += 1
                phase_counts['exact'] += 1
                # 5) exact global conflict index (unchanged module by default)
                t = time.perf_counter()
                result = (self.evaluator(primitives) if self.evaluator is not None
                          else self.index.evaluate(primitives))
                rec.add_time('exact', time.perf_counter() - t)
                rec.evaluations += 1
                if not result['valid']:
                    # Replicate route_original's accounting verbatim: every
                    # present conflict category is counted independently.
                    found = False
                    primary = None
                    blocker = None
                    distance = None
                    for key in ('spacing_pairs', 'overlap_pairs', 'touch_pairs',
                                'crossing_zone_overlap_pairs'):
                        if result.get(key):
                            reasons[key] += 1
                            blockers.update(result[key])
                            if primary is None:
                                primary = key
                                blocker = result[key][0]
                                distance = result.get('minimum_non_crossing_centerline_mm')
                            found = True
                    for key in ('self_intersections', 'self_overlaps',
                                'self_spacing_violations', 'discontinuities'):
                        if result.get(key):
                            reasons[key] += 1
                            found = True
                    if not found:
                        reasons['other_geometry_conflict'] += 1
                        primary = 'other_geometry_conflict'
                    if blocker is not None:
                        first_blocker_appearances[blocker] += 1
                        if first_blocker is None:
                            first_blocker = blocker
                        if distance is not None:
                            nearest_blocked_distance = distance if nearest_blocked_distance is None \
                                else min(nearest_blocked_distance, distance)
                    if rec.record_exact:
                        rec.exact.append((rid, cand['i'] if cand['i'] is not None else cand['candidate_id'],
                                          y, primary, blocker, distance, len(blockers)))
                    phase_counts['exact_reject'] += 1
                    continue
                chosen = dict(route_id=rid, layer=0, primitives=primitives,
                              length_mm=length(primitives), track_mm=y, rule_track_mm=rule_y,
                              track_index=cand['i'], legacy_pass=ctx.branch, interface_mode=cand['mode'],
                              local_frame=ctx.transform, source_endpoint=r['source_endpoint'],
                              target_endpoint=r['target_endpoint'])
                chosen_meta = dict(candidate_id=cand['candidate_id'])
                if self.register is not None:
                    self.register(rid, primitives)
                else:
                    self.index.add(rid, primitives)
                if cand['i'] is not None:
                    w = ctx.tracks[cand['i']]
                    w.WGs.append(rid)
                    w.rEnd.append(i1)
                    w.lEnd.append(i2)
                # Legacy track-state write-back.  For the new flexible template
                # there is no legacy track ordinal; the intermediate-track y is
                # written in the branch's rule frame so later group-local rule
                # checks still see a consistent state.
                if rule_y is not None:
                    state_y = rule_y
                elif ctx.source_above:
                    state_y = BOARD - float(cand['t1'])
                else:
                    state_y = float(cand['t1'])
                ctx.source_nodes[i1].y[si] = state_y
                ctx.target_nodes[i2].y[ti] = state_y
                break
            route_elapsed = time.perf_counter() - t_route
            self.attempted += 1
            if chosen:
                rec.accepted[rid] = chosen
                group_success += 1
            elif ctx.kind == 'opposite' or True:
                pass
            row = dict(route_id=rid, pair=ctx.pair, kind=ctx.kind, rank_in_group=rownum,
                       group_size=len(ctx.ordered), scanned=nscan,
                       order_fail=phase_counts['order_fail'], nocross_fail=phase_counts['nocross_fail'],
                       bend_fail=phase_counts['bend_fail'], validate_fail=phase_counts['validate_fail'],
                       exact=n, exact_reject=phase_counts['exact_reject'],
                       accepted=bool(chosen), track_index=(chosen or {}).get('track_index'),
                       track_mm=(chosen or {}).get('track_mm'),
                       first_blocker=first_blocker,
                       nearest_blocked_distance=nearest_blocked_distance,
                       rejection_counts=dict(reasons), blockers=dict(blockers),
                       seconds=route_elapsed)
            rec.route_rows.append(row)
            if samples:
                rec.samples.extend(samples)


    def _want_sample(self, counter, phase):
        """Deterministic per-route reservoir-ish sampling: keep every k-th."""
        counter[phase] += 1
        s = self.sample_stride
        if s is None or s <= 0:
            return False
        return counter[phase] % s == 1

    def _sample(self, ctx, rid, phase, cand, p, q, src, dst):
        y = cand['y']
        if y is None:  # flexible candidate: no deployed template equivalent
            return dict(route_id=rid, pair=ctx.pair, kind=ctx.kind, phase=phase,
                        track_index=cand['candidate_id'], y=None, bend_fit=None, validate_ok=None,
                        exact_valid=None, reason='flex_candidate_not_applicable', blocker=None,
                        distance=None, n_checked=0, elapsed=0.)
        leg = _geometry_legality(p, q, ctx.kind, y, ctx.transform, src['routing_xy'], dst['routing_xy'],
                                 src['inward'], dst['inward'], self.index, self.cfg)
        leg.update(route_id=rid, pair=ctx.pair, kind=ctx.kind, phase=phase,
                   track_index=cand['i'], y=float(y))
        return leg

    @staticmethod
    def _order_ok(ctx, rule_y, i1, i2, track):
        from four_side_1024.legacy_adapter import legacy_order_ok
        return legacy_order_ok(ctx.branch, rule_y, i1, i2, track)


# ---------------------------------------------------------------------------
# Baseline output helpers
# ---------------------------------------------------------------------------
def load_baseline():
    sc = json.loads((BASELINE / 'search_checkpoint.json').read_text(encoding='utf-8'))
    rg = json.loads((BASELINE / 'routes_geometry.json').read_text(encoding='utf-8'))
    stats = json.loads((BASELINE / 'statistics.json').read_text(encoding='utf-8'))
    return sc, rg, stats


def accepted_from_baseline():
    sc, rg, stats = load_baseline()
    accepted = OrderedDict()
    for rec in rg['routes']:
        accepted[rec['route_id']] = rec
    return accepted, sc, rg, stats


def fresh_index(cfg):
    return ConflictIndex(width=cfg['width_mm'], gap=cfg['edge_gap_mm'], sagitta=cfg['sagitta_mm'])


def seed_index(index, accepted_records):
    for rid, rec in accepted_records.items():
        index.add(rid, rec['primitives'])


def save_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding='utf-8')


def route_table(routes):
    return {r['route_id']: r for r in routes}
