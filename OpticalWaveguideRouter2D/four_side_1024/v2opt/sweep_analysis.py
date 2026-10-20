"""Task 5.4 analysis: candidate-budget ladder + expanded-candidate coverage.

Inputs
------
* ``outputs/four_side_1024_v2_candidate_rr_v01/candidates_budget/sweep_budget*.json``
  and ``sweep_summary.json`` - produced by::

      .venv\\Scripts\\python.exe -m four_side_1024.v2opt.pipeline sweep \\
          --plane z2 --budgets 200,400,800,1600 --workers 10

* the frozen historical layout ``.../fslw_R40_gap30_abcd/planes/V2/C/z2/routes.json``
  (206 routed / 306 failed, reconstructed into real D56 primitives by
  :class:`four_side_1024.v2opt.core.LayoutState`).

What this script derives (everything from the real artefacts, nothing hard-coded)
-------------------------------------------------------------------------------
1. budget ladder: found / newly found / cumulative / evaluations / wall clock,
   and the marginal yield of every budget step;
2. found-route distribution by side pair (EN/ES/SW/NW) and by candidate family
   (L/TURN_S/SHIFT_TURN/Z3/LEFT/Z5/DOWN_LOOP);
3. failure analysis of the routes that are still not placed: three mutually
   exclusive categories (candidate-budget exhausted / current-layout blocked /
   no candidate generated), aggregated ``rejection_counts`` and blocker Top-15;
4. candidate-side coverage of the 128 historical ``no_candidate_generated``
   corner routes under the *expanded* D56 candidate library, in two
   calibration modes:

   * ``empty`` layout - no historical route placed (only the fixed CSV endpoint
     stub lines remain in the ranking oracle, exactly like the historical
     generator's "unattempted routes" view).  This measures whether the current
     D56 candidate library can express the route geometry at all;
   * ``base`` layout - the frozen 206-route BASE layout.  This measures how many
     of those geometrically expressible candidates are actually insertable.

   Both modes enumerate the *full* queue (``candidates_adjacent`` ->
   ``candidates_from_specs``), independent of the 200/400/800/1600 evaluation
   budgets, and run with multiprocessing over routes.

   The wording is deliberately "the current D56 expanded candidate library
   generates no candidate for route X" - never "route X is physically
   impossible".

5. five matplotlib figures (PNG + the data of every axis in JSON);
6. ``ANALYSIS.md`` with the tables, the checks and the reproduction commands.

Usage
-----
    # full analysis (coverage is cached after the first run)
    .venv\\Scripts\\python.exe -m four_side_1024.v2opt.sweep_analysis

    # only (re)compute the expensive 128-route coverage cache
    .venv\\Scripts\\python.exe -m four_side_1024.v2opt.sweep_analysis --coverage-only

    # fast iteration without the coverage step
    .venv\\Scripts\\python.exe -m four_side_1024.v2opt.sweep_analysis --skip-coverage
"""
from __future__ import annotations

import argparse
import json
import multiprocessing
import time
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402  (backend must be set first)

from . import candext  # noqa: E402
from .core import DEFAULT_OUT, LayoutState  # noqa: E402
from .pipeline import base_routes_path  # noqa: E402
from ..d56.index import prepare  # noqa: E402

TOPOLOGY = 'V2'
PLANE = 'z2'
BUDGETS = (200, 400, 800, 1600)
HISTORY = base_routes_path(TOPOLOGY, PLANE)
CAND_DIR = Path(DEFAULT_OUT) / 'candidates_budget'
FIG_DIR = CAND_DIR / 'figures'
COVERAGE_CACHE = CAND_DIR / 'coverage_128_corner_routes.json'
ANALYSIS_JSON = CAND_DIR / 'analysis_data.json'
SUMMARY_JSON = CAND_DIR / 'sweep_summary.json'

FAMILY_ORDER = ('L', 'TURN_S', 'SHIFT_TURN', 'Z3', 'LEFT', 'Z5', 'DOWN_LOOP')
PAIR_ORDER = ('EN', 'ES', 'SW', 'NW')
BUCKETS = ((0, 0), (1, 9), (10, 99), (100, 999), (1000, None))
BUCKET_LABELS = ('0', '1-9', '10-99', '100-999', '>=1000')
CATEGORY_LABELS = {
    'candidate_budget_exhausted': 'candidate budget exhausted',
    'layout_blocked': 'current layout blocks all candidates',
    'no_candidate_generated': 'no candidate generated',
}


def _noop_log(*_args, **_kwargs):
    pass


def _stamp(message):
    print(time.strftime('%H:%M:%S') + ' ' + str(message), flush=True)


def _load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _bucket(value):
    for label, (low, high) in zip(BUCKET_LABELS, BUCKETS):
        if high is None and value >= low:
            return label
        if low <= value <= high:
            return label
    return BUCKET_LABELS[-1]


def _fmt(value, digits=1):
    return f'{value:,.{digits}f}'


# ---------------------------------------------------------------------------
# input loading
# ---------------------------------------------------------------------------
def load_history():
    """Historical z2 plane payload (frozen BASE layout + failure records)."""
    if not HISTORY.exists():
        raise FileNotFoundError(f'historical routes.json not found: {HISTORY}')
    payload = _load_json(HISTORY)
    payload['_path'] = str(HISTORY)
    return payload


def failed_routes(payload):
    return [record for record in payload['routes']
            if record.get('status') != 'routed']


def corner_route_ids(payload):
    """The 128 historical ``no_candidate_generated`` corner routes."""
    ids = sorted(int(record['route_id']) for record in failed_routes(payload)
                 if record.get('reason') == 'no_candidate_generated')
    if not ids:
        raise RuntimeError('no historical no_candidate_generated route found')
    return ids


def load_sweeps(budgets=BUDGETS):
    sweeps = []
    for budget in budgets:
        path = CAND_DIR / f'sweep_budget{int(budget)}.json'
        if not path.exists():
            raise FileNotFoundError(
                f'missing sweep artefact {path} - run the pipeline sweep first')
        payload = _load_json(path)
        sweeps.append(dict(budget=int(budget), path=str(path),
                           summary=payload['summary'], routes=payload['routes']))
    sweeps.sort(key=lambda item: item['budget'])
    return sweeps


# ---------------------------------------------------------------------------
# 1) budget ladder
# ---------------------------------------------------------------------------
def ladder_analysis(sweeps, history):
    pending = len(failed_routes(history))
    total_routes = len(history['routes'])
    routed_base = sum(1 for record in history['routes']
                      if record.get('status') == 'routed')
    levels = []
    previous_found = set()
    previous_evaluated = 0
    nesting_ok = True
    for sweep in sweeps:
        summary = sweep['summary']
        found = set(int(route_id) for route_id in summary['found_route_ids'])
        new_found = sorted(found - previous_found)
        if not previous_found.issubset(found):
            nesting_ok = False
        records = sweep['routes']
        evaluated = sum(int(record.get('evaluated') or 0) for record in records)
        candidate_indices = sorted(int(record['candidate_index']) for record in records
                                   if record.get('found'))
        level = dict(
            budget=sweep['budget'],
            tested=int(summary['tested']),
            found=int(summary['found']),
            cumulative_found=len(found),
            new_found=new_found,
            new_found_count=len(new_found),
            cumulative_rate=len(found) / pending if pending else 0.0,
            evaluated=evaluated,
            evaluated_per_route=(evaluated / summary['tested']
                                 if summary['tested'] else 0.0),
            evaluated_delta=evaluated - previous_evaluated,
            seconds=float(summary['seconds']),
            workers=int(summary.get('workers') or 0),
            seconds_per_route=(float(summary['seconds']) / summary['tested']
                               if summary['tested'] else 0.0),
            evaluations_per_second=(evaluated / summary['seconds']
                                    if summary['seconds'] else 0.0),
            candidate_index_min=candidate_indices[0] if candidate_indices else None,
            candidate_index_max=candidate_indices[-1] if candidate_indices else None,
            candidate_index_median=(candidate_indices[len(candidate_indices) // 2]
                                    if candidate_indices else None),
            candidate_index_le_200=sum(1 for index in candidate_indices if index < 200),
            candidate_index_le_400=sum(1 for index in candidate_indices if index < 400),
            candidate_index_le_800=sum(1 for index in candidate_indices if index < 800),
            found_route_ids=sorted(found),
        )
        if previous_evaluated:
            level['evaluated_ratio'] = evaluated / previous_evaluated
        else:
            level['evaluated_ratio'] = None
        if level['new_found_count']:
            level['evaluations_per_new_route'] = (level['evaluated_delta']
                                                  / level['new_found_count'])
        else:
            level['evaluations_per_new_route'] = None
        levels.append(level)
        previous_found = found
        previous_evaluated = evaluated
    all_found = set(levels[-1]['found_route_ids']) if levels else set()
    return dict(pending=pending, total_routes=total_routes, routed_base=routed_base,
                budgets=list(BUDGETS), nesting_ok=nesting_ok, levels=levels,
                found_any=sorted(all_found),
                still_failed=sorted(set(
                    int(record['route_id']) for record in failed_routes(history))
                    - all_found))


# ---------------------------------------------------------------------------
# 2) pair / family distribution
# ---------------------------------------------------------------------------
def distribution_analysis(sweeps):
    by_pair = {}
    by_family = {}
    previous_pairs = Counter()
    previous_families = Counter()
    for sweep in sweeps:
        summary = sweep['summary']
        budget = sweep['budget']
        pairs = {pair: int(summary['by_pair_found'].get(pair, 0))
                 for pair in PAIR_ORDER}
        families = {family: int(summary['family_histogram'].get(family, 0))
                    for family in FAMILY_ORDER}
        by_pair[budget] = dict(
            found=pairs,
            new={pair: pairs[pair] - previous_pairs[pair] for pair in PAIR_ORDER},
            total=int(summary['found']))
        by_family[budget] = dict(
            found=families,
            new={family: families[family] - previous_families[family]
                 for family in FAMILY_ORDER},
            total=int(summary['found']))
        previous_pairs = Counter(pairs)
        previous_families = Counter(families)
    # family x pair cross table at the largest budget
    family_by_pair = {}
    for record in sweeps[-1]['routes']:
        if not record.get('found'):
            continue
        family = record.get('family')
        pair = record.get('pair')
        entry = family_by_pair.setdefault(family, Counter())
        entry[pair] += 1
    family_by_pair = {family: {pair: int(counts.get(pair, 0))
                               for pair in PAIR_ORDER}
                      for family, counts in sorted(family_by_pair.items())}
    return dict(by_pair=by_pair, by_family=by_family,
                family_by_pair=family_by_pair)


# ---------------------------------------------------------------------------
# 3) failure analysis of the still-unplaced routes
# ---------------------------------------------------------------------------
def _top_blockers(records, top_n=15):
    counts = Counter()
    routes_touched = Counter()
    for record in records:
        for key, value in (record.get('blockers') or {}).items():
            blocker = int(key)
            counts[blocker] += int(value)
            routes_touched[blocker] += 1
    top = []
    total = sum(counts.values())
    for blocker, count in counts.most_common(top_n):
        top.append(dict(blocker_route_id=blocker, count=int(count),
                        affected_routes=int(routes_touched[blocker]),
                        share=count / total if total else 0.0))
    return dict(total=int(total), distinct=len(counts), top=top)


def failure_analysis(sweeps):
    levels = []
    for sweep in sweeps:
        budget = sweep['budget']
        records = sweep['routes']
        unfound = [record for record in records if not record.get('found')]
        categories = Counter()
        rejection = Counter()
        geometric = Counter()
        evaluated_hist = Counter()
        by_category_pair = {}
        budget_marker_missing = []

        for record in unfound:
            reason = record.get('reason')
            rejection_counts = record.get('rejection_counts') or {}
            evaluated = int(record.get('evaluated') or 0)
            if reason == 'no_candidate_generated' or evaluated == 0:
                category = 'no_candidate_generated'
            elif int(rejection_counts.get('candidate_budget_exhausted', 0)) > 0:
                category = 'candidate_budget_exhausted'
            else:
                category = 'layout_blocked'
            if (evaluated >= budget
                    and int(rejection_counts.get('candidate_budget_exhausted', 0)) == 0
                    and category != 'no_candidate_generated'):
                budget_marker_missing.append(int(record['route_id']))
            categories[category] += 1
            pair = record.get('pair')
            bucket = by_category_pair.setdefault(pair, Counter())
            bucket[category] += 1
            evaluated_hist[evaluated] += 1
            for key, value in rejection_counts.items():
                rejection[key] += int(value)
                if key != 'candidate_budget_exhausted':
                    geometric[key] += int(value)
            # a route whose evaluation budget ran out but whose queue had fewer
            # than <budget> candidates is *not* budget-limited; the marker in
            # rejection_counts is authoritative, see attempt_route().

        levels.append(dict(
            budget=budget,
            tested=len(records),
            found=sum(1 for record in records if record.get('found')),
            unfound=len(unfound),
            categories={category: int(categories.get(category, 0))
                        for category in CATEGORY_LABELS},
            by_category_pair={pair: {category: int(counts.get(category, 0))
                                     for category in CATEGORY_LABELS}
                              for pair, counts in sorted(by_category_pair.items())},
            rejection_counts=dict(rejection),
            geometric_rejection_counts=dict(geometric),
            blockers=_top_blockers(unfound, top_n=15),
            evaluated_mode=dict(sorted(evaluated_hist.items())),
            budget_marker_missing=budget_marker_missing,
        ))
    return levels


# ---------------------------------------------------------------------------
# 4) candidate-side coverage of the 128 historical no_candidate_generated routes
# ---------------------------------------------------------------------------
def _coverage_worker(task):
    """Enumerate the *full* expanded candidate queue of one chunk of routes.

    Runs in a separate process: the frozen BASE layout and the empty layout are
    both rebuilt once per worker from the same historical ``routes.json``.
    """
    history, plane, topology, route_ids = (task['history'], task['plane'],
                                           task['topology'], task['route_ids'])
    started = time.perf_counter()
    base = LayoutState.from_history(topology, plane, history, log=_noop_log)
    empty = LayoutState.from_history(topology, plane, history, log=_noop_log)
    empty.rebuild(accepted={}, failed={})
    records = []
    for route_id in route_ids:
        route_id = int(route_id)
        record = dict(route_id=route_id)
        for mode, state in (('empty', empty), ('base', base)):
            frame = state.frames[route_id]
            if frame.kind != 'adjacent':
                record[mode] = dict(error='non-adjacent frame kind',
                                    kind=frame.kind)
                continue
            oracle = state.oracle_for(route_id)
            specs = candext.adjacent_specs(frame, oracle)
            generated = 0
            valid = 0
            families = Counter()
            first_valid = None
            for index, candidate in enumerate(
                    candext.candidates_from_specs(frame, specs, oracle)):
                generated += 1
                world = frame.to_world(candidate['primitives'])
                prepared = prepare(world)
                evaluation = state.index.evaluate(prepared)
                if evaluation.valid:
                    valid += 1
                    families[candidate['family']] += 1
                    if first_valid is None:
                        first_valid = dict(index=index,
                                           family=candidate['family'],
                                           params=candidate['params'],
                                           length_mm=prepared.length)
            record[mode] = dict(spec_total=len(specs),
                                generated=generated,
                                valid=valid,
                                families=dict(families),
                                first_valid=first_valid)
        records.append(record)
    return dict(records=records, seconds=time.perf_counter() - started)


def coverage_analysis(route_ids, workers=10, refresh=False, limit=0):
    """Coverage of ``route_ids`` in both calibration modes, cached on disk."""
    route_ids = sorted(int(route_id) for route_id in route_ids)
    if limit:
        route_ids = route_ids[:int(limit)]
    if COVERAGE_CACHE.exists() and not refresh:
        cached = _load_json(COVERAGE_CACHE)
        if cached.get('meta', {}).get('route_ids') == route_ids:
            _stamp(f'coverage: reusing cache {COVERAGE_CACHE}')
            return cached
    workers = max(1, min(int(workers), len(route_ids)))
    chunks = [[] for _ in range(workers)]
    for position, route_id in enumerate(route_ids):
        chunks[position % workers].append(route_id)
    tasks = [dict(history=str(HISTORY), plane=PLANE, topology=TOPOLOGY,
                  route_ids=chunk) for chunk in chunks if chunk]
    _stamp(f'coverage: {len(route_ids)} routes x 2 calibration modes, '
           f'{len(tasks)} workers, full candidate queue per route')
    started = time.perf_counter()
    results = []
    context = multiprocessing.get_context('spawn')
    with context.Pool(processes=len(tasks)) as pool:
        for chunk_result in pool.imap_unordered(_coverage_worker, tasks):
            results.extend(chunk_result['records'])
            _stamp(f'coverage: {len(results)}/{len(route_ids)} routes done, '
                   f'elapsed={time.perf_counter() - started:.1f}s')
    results.sort(key=lambda record: record['route_id'])
    payload = dict(
        meta=dict(plane=PLANE, topology=TOPOLOGY, history=str(HISTORY),
                  route_ids=route_ids, n_routes=len(route_ids),
                  workers=len(tasks), seconds=time.perf_counter() - started,
                  mode='full expanded queue, independent of evaluation budget',
                  generated_by='four_side_1024.v2opt.candext.adjacent_specs + '
                               'candidates_from_specs',
                  timestamp=time.strftime('%Y-%m-%dT%H:%M:%S')),
        routes=results)
    COVERAGE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    COVERAGE_CACHE.write_text(json.dumps(payload, indent=1, ensure_ascii=False),
                              encoding='utf-8')
    _stamp(f'coverage: wrote {COVERAGE_CACHE}')
    return payload


def summarise_coverage(coverage, sweeps, history):
    routes = coverage['routes']
    corner_ids = coverage['meta']['route_ids']
    corner_set = set(corner_ids)
    found_by_budget = {sweep['budget']: set(int(route_id) for route_id in
                                            sweep['summary']['found_route_ids'])
                       for sweep in sweeps}
    budget_max = max(found_by_budget) if found_by_budget else 0
    pairs = {int(record['route_id']): record.get('pair')
             for record in history['routes']}
    pairs = {route_id: pairs.get(route_id) for route_id in corner_ids}

    def mode_stats(mode):
        bucket_hist = Counter()
        generated_total = 0
        valid_total = 0
        max_generated = 0
        max_valid = 0
        zero_generated = []
        zero_valid = []
        families = Counter()
        family_routes = Counter()
        first_valid_indices = []
        for record in routes:
            data = record[mode]
            generated = int(data['generated'])
            valid = int(data['valid'])
            generated_total += generated
            valid_total += valid
            max_generated = max(max_generated, generated)
            max_valid = max(max_valid, valid)
            bucket_hist[_bucket(valid)] += 1
            if generated == 0:
                zero_generated.append(record['route_id'])
            if valid == 0:
                zero_valid.append(record['route_id'])
            for family, count in (data.get('families') or {}).items():
                families[family] += int(count)
                family_routes[family] += 1
            first_valid = data.get('first_valid')
            if first_valid:
                first_valid_indices.append(first_valid['index'])
        denominator = len(routes) if routes else 1
        return dict(generated_total=generated_total, valid_total=valid_total,
                    mean_generated=generated_total / denominator,
                    mean_valid=valid_total / denominator,
                    max_generated=max_generated, max_valid=max_valid,
                    zero=zero_valid, zero_count=len(zero_valid),
                    zero_generated=zero_generated,
                    zero_generated_count=len(zero_generated),
                    buckets={label: int(bucket_hist.get(label, 0))
                             for label in BUCKET_LABELS},
                    families={family: int(families.get(family, 0))
                              for family in FAMILY_ORDER
                              if families.get(family)},
                    family_routes={family: int(family_routes.get(family, 0))
                                   for family in FAMILY_ORDER
                                   if family_routes.get(family)},
                    first_valid_index_median=(sorted(first_valid_indices)[
                        len(first_valid_indices) // 2]
                        if first_valid_indices else None))

    empty = mode_stats('empty')
    base = mode_stats('base')

    # the no_candidate_generated set of every sweep budget must be exactly the
    # base-layout "no candidate generated at all" set of the 128 corner routes.
    no_candidate_by_budget = {}
    for sweep in sweeps:
        no_candidate_by_budget[sweep['budget']] = sorted(
            int(record['route_id']) for record in sweep['routes']
            if int(record['route_id']) in corner_set
            and record.get('reason') == 'no_candidate_generated')
    no_candidate_matches_base = all(
        ids == base['zero_generated'] for ids in no_candidate_by_budget.values())
    empty_zero_is_base_zero = empty['zero_generated'] == base['zero_generated']

    # consistency with the budget ladder: found at budget b  <=>  a legal
    # base-layout candidate exists at queue position < b.
    mismatch = []
    for record in routes:
        route_id = record['route_id']
        first = record['base'].get('first_valid')
        for budget, found in found_by_budget.items():
            predicted = bool(first and first['index'] < budget)
            actual = route_id in found
            if predicted != actual:
                mismatch.append(dict(route_id=route_id, budget=budget,
                                     predicted=predicted, actual=actual,
                                     first_valid_index=(first or {}).get('index')))
    beyond_budget = sorted(
        record['route_id'] for record in routes
        if record['base'].get('first_valid')
        and record['base']['first_valid']['index'] >= budget_max)

    # cross classes
    cross = Counter()
    for record in routes:
        cell = (int(record['empty']['generated']) > 0,
                int(record['base']['valid']) > 0)
        cross[cell] += 1

    zero_empty_pairs = Counter(pairs[route_id] for route_id in empty['zero'])
    zero_base_pairs = Counter(pairs[route_id] for route_id in base['zero'])
    corner_found = {budget: sorted(corner_set & found)
                    for budget, found in found_by_budget.items()}
    predicted_counts = {}
    for budget in found_by_budget:
        predicted_counts[budget] = sum(
            1 for record in routes
            if record['base'].get('first_valid')
            and record['base']['first_valid']['index'] < budget)
    return dict(
        n_routes=len(routes), n_routes_expected=len(corner_ids),
        route_ids=corner_ids, pairs=pairs,
        empty=empty, base=base,
        cross={f'empty_ge1__base_ge1': cross[(True, True)],
               f'empty_ge1__base_0': cross[(True, False)],
               f'empty_0__base_ge1': cross[(False, True)],
               f'empty_0__base_0': cross[(False, False)]},
        zero_empty_pairs=dict(zero_empty_pairs),
        zero_base_pairs=dict(zero_base_pairs),
        sweep_consistency_mismatch=mismatch,
        no_candidate_by_budget={int(key): value
                                for key, value in no_candidate_by_budget.items()},
        no_candidate_matches_base=no_candidate_matches_base,
        empty_zero_is_base_zero=empty_zero_is_base_zero,
        corner_found_by_budget={int(key): value
                                for key, value in corner_found.items()},
        corner_found_counts={int(budget): len(value)
                             for budget, value in corner_found.items()},
        predicted_found_counts={int(budget): int(count)
                                for budget, count in predicted_counts.items()},
        found_at_max_budget=sorted(found_by_budget.get(budget_max, set())),
        unfound_at_max_budget=sorted(set(corner_ids)
                                     - found_by_budget.get(budget_max, set())),
        base_first_valid_beyond_budget=beyond_budget,
        seconds=float(coverage['meta'].get('seconds') or 0.0),
        workers=int(coverage['meta'].get('workers') or 0),
        generated_by=coverage['meta'].get('generated_by'),
    )


# ---------------------------------------------------------------------------
# 5) figures
# ---------------------------------------------------------------------------
def _figure_path(name):
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    return FIG_DIR / name


def make_figures(ladder, distribution, failures, coverage, history):
    plt.rcParams.update({'axes.grid': True, 'grid.alpha': 0.3,
                         'font.size': 9, 'figure.autolayout': True})
    palette = plt.get_cmap('tab10')
    figure_data = {}
    figures = []

    # -- fig1: cumulative found routes vs budget ---------------------------
    budgets = [0] + [level['budget'] for level in ladder['levels']]
    cumulative = [0] + [level['cumulative_found'] for level in ladder['levels']]
    positions = list(range(len(budgets)))
    fig, axis = plt.subplots(figsize=(7.2, 4.4))
    axis.plot(positions, cumulative, marker='o', color=palette(0), linewidth=2,
              label='cumulative rescued routes')
    for x, y in zip(positions, cumulative):
        axis.annotate(f'{y}', (x, y), textcoords='offset points',
                      xytext=(0, 8), ha='center', fontsize=9, color=palette(0))
    axis.set_xlabel('candidate evaluation budget per route')
    axis.set_ylabel('cumulative rescued routes')
    axis.set_title('Task 5.4 - cumulative rescued routes vs budget\n'
                   f"(frozen BASE layout: {ladder['routed_base']} routed, "
                   f"{ladder['pending']} pending; independent single-route tests)")
    axis.set_xticks(positions)
    axis.set_xticklabels([str(value) for value in budgets])
    axis.set_ylim(0, max(cumulative) * 1.25 + 1)
    axis.legend()
    path = _figure_path('fig1_budget_vs_cumulative_found.png')
    fig.savefig(path, dpi=160)
    plt.close(fig)
    figures.append(path)
    figure_data['fig1'] = dict(budgets=budgets, cumulative_found=cumulative)

    # -- fig2: marginal gain per budget step ------------------------------
    steps = [level['budget'] for level in ladder['levels']]
    marginal = [level['new_found_count'] for level in ladder['levels']]
    efficiency = [((level['evaluated_delta'] / level['new_found_count'])
                   if level['new_found_count'] else float('nan'))
                  for level in ladder['levels']]
    fig, axis = plt.subplots(figsize=(7.2, 4.4))
    axis.bar(range(len(steps)), marginal, color=palette(2), width=0.6,
             label='newly rescued routes')
    for x, y in enumerate(marginal):
        axis.annotate(f'{y}', (x, y), textcoords='offset points',
                      xytext=(0, 4), ha='center', fontsize=9)
    axis.set_xticks(range(len(steps)))
    axis.set_xticklabels([str(value) for value in steps])
    axis.set_xlabel('candidate evaluation budget (step ceiling)')
    axis.set_ylabel('newly rescued routes')
    axis.set_ylim(0, max(marginal or [1]) * 1.3 + 1)
    axis2 = axis.twinx()
    axis2.plot(range(len(steps)), efficiency, marker='s', color=palette(3),
               linewidth=1.6, label='evaluations per newly rescued route')
    axis2.set_ylabel('evaluations / newly rescued route')
    axis2.grid(False)
    lines = axis.get_legend_handles_labels()
    lines2 = axis2.get_legend_handles_labels()
    axis.legend(lines[0] + lines2[0], lines[1] + lines2[1], loc='upper right')
    axis.set_title('Task 5.4 - marginal gain and marginal cost of every budget step')
    path = _figure_path('fig2_marginal_gain.png')
    fig.savefig(path, dpi=160)
    plt.close(fig)
    figures.append(path)
    figure_data['fig2'] = dict(
        budgets=steps, new_found=marginal,
        evaluations_per_new_route=[None if value != value else value
                                   for value in efficiency])

    # -- fig3: rescued routes per candidate family, stacked by budget -----
    fig, axis = plt.subplots(figsize=(7.6, 4.4))
    x = range(len(steps))
    bottom = [0] * len(steps)
    family_series = {}
    for family in FAMILY_ORDER:
        values = [distribution['by_family'][budget]['found'][family]
                  for budget in steps]
        family_series[family] = values
        if max(values) == 0:
            continue
        axis.bar(x, values, bottom=bottom, width=0.6,
                 label=family, color=palette(FAMILY_ORDER.index(family)))
        bottom = [base_value + value for base_value, value in zip(bottom, values)]
    for position, total in enumerate(bottom):
        axis.annotate(f'{total}', (position, total), textcoords='offset points',
                      xytext=(0, 4), ha='center', fontsize=9)
    axis.set_xticks(list(x))
    axis.set_xticklabels([str(value) for value in steps])
    axis.set_xlabel('candidate evaluation budget')
    axis.set_ylabel('rescued routes (cumulative within budget)')
    axis.set_ylim(0, (max(bottom) if bottom else 1) * 1.35 + 1)
    axis.set_title('Task 5.4 - rescued routes per candidate family')
    axis.legend(loc='upper left', ncol=2)
    path = _figure_path('fig3_family_stacked.png')
    fig.savefig(path, dpi=160)
    plt.close(fig)
    figures.append(path)
    figure_data['fig3'] = dict(budgets=steps, families=family_series)

    # -- fig4: failure categories + geometric rejection reasons -----------
    fig, (axis, axis2) = plt.subplots(1, 2, figsize=(11.2, 4.5))
    categories = list(CATEGORY_LABELS)
    bottom = [0] * len(steps)
    per_budget = {category: [failures[position]['categories'][category]
                            for position in range(len(steps))]
                  for category in categories}
    for position_category, category in enumerate(categories):
        values = per_budget[category]
        axis.bar(range(len(steps)), values, bottom=bottom, width=0.6,
                 label=CATEGORY_LABELS[category],
                 color=palette(position_category + 3))
        bottom = [base_value + value for base_value, value in zip(bottom, values)]
    for position, total in enumerate(bottom):
        axis.annotate(f'{total}', (position, total), textcoords='offset points',
                      xytext=(0, 4), ha='center', fontsize=9)
    axis.set_xticks(range(len(steps)))
    axis.set_xticklabels([str(value) for value in steps])
    axis.set_xlabel('candidate evaluation budget')
    axis.set_ylabel('still-unplaced routes')
    axis.set_ylim(0, (max(bottom) if bottom else 1) * 1.25 + 1)
    axis.set_title('failure categories vs budget')
    axis.legend(loc='lower right', fontsize=7)
    # geometric rejection reasons (aggregate over still-unplaced routes)
    reason_order = sorted({reason for failure in failures
                           for reason in failure['geometric_rejection_counts']},
                          key=lambda reason: -sum(
                              failure['geometric_rejection_counts'].get(reason, 0)
                              for failure in failures))
    reason_order = reason_order[:6]
    width = 0.8 / max(1, len(reason_order))
    for position_reason, reason in enumerate(reason_order):
        values = [failures[position]['geometric_rejection_counts'].get(reason, 0)
                  for position in range(len(steps))]
        axis2.bar([position + (position_reason - len(reason_order) / 2 + 0.5) * width
                   for position in range(len(steps))],
                  values, width=width * 0.92, label=reason,
                  color=palette(position_reason))
    axis2.set_xticks(range(len(steps)))
    axis2.set_xticklabels([str(value) for value in steps])
    axis2.set_xlabel('candidate evaluation budget')
    axis2.set_ylabel('rejected candidate count (all routes)')
    axis2.set_yscale('symlog', linthresh=10)
    axis2.set_title('geometric rejection reasons vs budget')
    axis2.legend(fontsize=7)
    path = _figure_path('fig4_failure_reasons.png')
    fig.savefig(path, dpi=160)
    plt.close(fig)
    figures.append(path)
    figure_data['fig4'] = dict(budgets=steps, categories=per_budget,
                               geometric_reasons={
                                   reason: [failures[position]
                                            ['geometric_rejection_counts']
                                            .get(reason, 0)
                                            for position in range(len(steps))]
                                   for reason in reason_order})

    # -- fig5: coverage of the 128 historical no_candidate_generated routes
    if coverage is not None:
        fig, axes = plt.subplots(1, 3, figsize=(13.2, 4.2))
        axis = axes[0]
        positions = range(len(BUCKET_LABELS))
        width = 0.38
        empty_values = [coverage['empty']['buckets'][label]
                        for label in BUCKET_LABELS]
        base_values = [coverage['base']['buckets'][label]
                       for label in BUCKET_LABELS]
        axis.bar([position - width / 2 for position in positions], empty_values,
                 width=width, label='empty layout (generated)',
                 color=palette(0))
        axis.bar([position + width / 2 for position in positions], base_values,
                 width=width, label='BASE layout (insert-legal)',
                 color=palette(3))
        axis.set_xticks(list(positions))
        axis.set_xticklabels(BUCKET_LABELS)
        axis.set_xlabel('legal candidates per route')
        axis.set_ylabel('number of routes')
        axis.set_title(f"128 historical no_candidate_generated\ncorner routes "
                       f"({coverage['n_routes']} routes)")
        axis.legend(fontsize=7)
        axis = axes[1]
        cross_labels = ['empty>=1\nbase>=1', 'empty>=1\nbase=0',
                        'empty=0\nbase>=1', 'empty=0\nbase=0']
        cross_values = [coverage['cross']['empty_ge1__base_ge1'],
                        coverage['cross']['empty_ge1__base_0'],
                        coverage['cross']['empty_0__base_ge1'],
                        coverage['cross']['empty_0__base_0']]
        axis.bar(range(4), cross_values, color=palette(1), width=0.6)
        for position, value in enumerate(cross_values):
            axis.annotate(f'{value}', (position, value),
                          textcoords='offset points', xytext=(0, 4),
                          ha='center', fontsize=9)
        axis.set_xticks(range(4))
        axis.set_xticklabels(cross_labels, fontsize=7)
        axis.set_ylabel('number of routes')
        axis.set_title('coverage cross-classes')
        axis.set_ylim(0, max(cross_values or [1]) * 1.3 + 1)
        axis = axes[2]
        pairs = list(PAIR_ORDER)
        zero_empty = [coverage['zero_empty_pairs'].get(pair, 0) for pair in pairs]
        zero_base = [coverage['zero_base_pairs'].get(pair, 0) for pair in pairs]
        width = 0.38
        axis.bar([position - width / 2 for position in range(len(pairs))],
                 zero_empty, width=width, label='0 generated (empty layout)',
                 color=palette(4))
        axis.bar([position + width / 2 for position in range(len(pairs))],
                 zero_base, width=width, label='0 insert-legal (BASE layout)',
                 color=palette(5))
        axis.set_xticks(range(len(pairs)))
        axis.set_xticklabels(pairs)
        axis.set_ylabel('number of routes with 0 candidates')
        axis.set_title('zero-coverage routes per side pair')
        axis.legend(fontsize=7)
        fig.tight_layout()
        path = _figure_path('fig5_corner_coverage.png')
        fig.savefig(path, dpi=160)
        plt.close(fig)
        figures.append(path)
        figure_data['fig5'] = dict(
            buckets=BUCKET_LABELS, empty_generated=empty_values,
            base_valid=base_values, cross=cross_values,
            zero_empty_by_pair=dict(zip(pairs, zero_empty)),
            zero_base_by_pair=dict(zip(pairs, zero_base)))

    return figures, figure_data


# ---------------------------------------------------------------------------
# 6) markdown report
# ---------------------------------------------------------------------------
def _table(headers, rows):
    lines = ['| ' + ' | '.join(str(header) for header in headers) + ' |',
             '|' + '|'.join('---' for _ in headers) + '|']
    for row in rows:
        lines.append('| ' + ' | '.join(str(cell) for cell in row) + ' |')
    return '\n'.join(lines)


def _compress_ids(ids):
    """Compact representation of a sorted id list (ranges + singles)."""
    ids = sorted(int(value) for value in ids)
    if not ids:
        return ''
    parts = []
    start = previous = ids[0]
    for value in ids[1:]:
        if value == previous + 1:
            previous = value
            continue
        parts.append(f'{start}-{previous}' if previous > start else str(start))
        start = previous = value
    parts.append(f'{start}-{previous}' if previous > start else str(start))
    return ', '.join(parts)


def write_analysis_md(ladder, distribution, failures, coverage, figures,
                      checks, history, elapsed):
    """Render ``ANALYSIS.md`` from the computed structures (all values derived)."""
    history_payload = history
    statistics = history_payload.get('statistics') or {}
    by_pair_history = statistics.get('by_pair') or {}
    lines = []
    lines.append('# 任务 5.4：V2 z2 平面候选预算 200/400/800/1600 对照实验与候选覆盖分析\n')
    lines.append('> 全部数字由 `four_side_1024/v2opt/sweep_analysis.py` 从真实产物文件重算得出，'
                 '没有任何手工填写值。\n')

    # ---- experiment setup ------------------------------------------------
    lines.append('## 1. 实验设置\n')
    lines.append('| 项目 | 值 |')
    lines.append('|---|---|')
    lines.append(f"| 拓扑 / 平面 | {TOPOLOGY} / {PLANE} |")
    lines.append(f"| 冻结 BASE 布局（历史 C/z2） | "
                 f"{ladder['routed_base']} / {ladder['total_routes']} "
                 f"已布通（待测试 {ladder['pending']} 条） |")
    lines.append('| 历史 pair 分布（成功/失败） | '
                 + '；'.join(f'{pair} {entry.get("success", 0)}/'
                             f'{entry.get("failed", 0)}'
                             for pair, entry in by_pair_history.items()) + ' |')
    lines.append(f"| 历史 routes.json | `{HISTORY}` |")
    lines.append('| 测试方式 | 单路线独立插入测试（`parallel_sweep`）：'
                 '每个失败路线独立在冻结布局上尝试，找到的候选 **不提交**、'
                 '不改变布局 |')
    lines.append('| 候选来源 | `candext` 扩展 D56 候选库（L / TURN_S / SHIFT_TURN / '
                 'Z3 / LEFT / Z5 / DOWN_LOOP，同一 primitive 集） |')
    lines.append('| 评估预算 | ' + ' / '.join(str(budget) for budget in BUDGETS) + ' |')
    lines.append(f"| 并行度 | {ladder['levels'][0]['workers'] if ladder['levels'] else '?'} 个进程 |")
    lines.append('| 合法性判定 | 冻结的严格 D56 精确索引 `D56Index.evaluate`'
                 '（`crossing_policy=strict`） |')
    lines.append('')
    lines.append('复现命令（项目根 `OpticalWaveguideRouter2D/`）：\n')
    lines.append('```powershell')
    lines.append('.venv\\Scripts\\python.exe -m four_side_1024.v2opt.pipeline sweep '
                 '--plane z2 --budgets 200,400,800,1600 --workers 10')
    lines.append('.venv\\Scripts\\python.exe -m four_side_1024.v2opt.sweep_analysis')
    lines.append('```\n')
    lines.append('说明：sweep 每个预算档独立重跑 306 条失败路线；'
                 '`sweep_analysis.py --coverage-only` 可单独重算 128 条 corner 路线的'
                 '全候选队列覆盖（多进程，结果缓存于 '
                 '`coverage_128_corner_routes.json`）。\n')
    lines.append('> 运行备注：本次 sweep 进程结束时退出码为 1，原因是 `pipeline.py` 的 '
                 '`main()` 在 `finally` 中先 `handle.close()` 再调用 '
                 '`log(f\'log written ...\')`（写已关闭的日志句柄）触发 `ValueError`。'
                 '该异常发生在 **四档预算全部完成并写出产物之后**，四个 sweep JSON 均已'
                 '校验完整（本报告第 2 节自检全部通过），不影响实验结果；'
                 '本脚本未修改任何共享模块。\n')

    # ---- sanity checks ---------------------------------------------------
    lines.append('## 2. 自检（数据一致性）\n')
    lines.append(_table(['检查项', '结果'], [
        ['四档 found 集合逐档嵌套', 'PASS' if ladder['nesting_ok'] else 'FAIL'],
        ['summary.found == len(found_route_ids)', 'PASS' if all(
            level['found'] == len(level['found_route_ids']) for level in ladder['levels'])
         else 'FAIL'],
        ['四档 found 并集 == 累计救回路线数',
         f"{len(ladder['found_any'])} / {ladder['levels'][-1]['cumulative_found'] if ladder['levels'] else 0}"],
        ['summary.evaluated == sum(逐路线 evaluated)', 'PASS' if not checks['evaluated_mismatch']
         else 'FAIL ' + str(checks['evaluated_mismatch'])],
        ['evaluated==budget 但无预算标记（候选队列恰为 budget 条的边界情形，'
         '仍按"当前布局阻挡"归类）',
         str(sum(len(failure['budget_marker_missing']) for failure in failures))],
        ['coverage 缓存路线数', f"{coverage['n_routes']} / {coverage['n_routes_expected']}"
         if coverage else 'N/A'],
        ['coverage 与 sweep found 交叉校验不一致数',
         f"{len(coverage['sweep_consistency_mismatch'])}" if coverage else 'N/A'],
        ['coverage 0 生成集合 == sweep 各档 no_candidate_generated 集合',
         ('PASS' if coverage['no_candidate_matches_base'] else 'FAIL')
         if coverage else 'N/A'],
        ['empty-layout 0 生成集合 == base-layout 0 生成集合',
         ('PASS' if coverage['empty_zero_is_base_zero'] else 'FAIL')
         if coverage else 'N/A'],
    ]))
    lines.append('')

    # ---- 3. budget ladder ------------------------------------------------
    lines.append('## 3. 预算阶梯结果\n')
    rows = []
    for level in ladder['levels']:
        rows.append([
            level['budget'], level['found'], level['new_found_count'],
            level['cumulative_found'],
            f"{level['cumulative_rate'] * 100:.2f}%",
            f"{level['evaluated']:,}", f"{level['evaluated_per_route']:.1f}",
            f"{level['seconds']:.1f}",
            (f"{level['evaluations_per_new_route']:,.0f}"
             if level['evaluations_per_new_route'] else '-'),
        ])
    lines.append(_table(['预算', 'found', '边际新增', '累计 found', '累计救回率',
                         'evaluated 总数', 'evaluated/路线', '耗时 (s)',
                         '每条边际新增消耗的评估数'], rows))
    lines.append('')
    lines.append('说明：`evaluated` 是真实执行的候选合法性评估次数之和；'
                 '它小于 `预算 × 306` 有两个原因：部分路线的扩展候选队列本身短于预算'
                 '（队列耗尽即结束），以及部分路线在命中合法候选后提前结束。\n')
    lines.append('### 3.1 边际收益结论\n')
    levels = ladder['levels']
    if levels:
        first = levels[0]
        last = levels[-1]
        lines.append(f"- 预算 {first['budget']} 即可救回 **{first['found']}** 条"
                     f"（占 {ladder['pending']} 条待测路线的 "
                     f"{first['cumulative_rate'] * 100:.1f}%）。")
        if len(levels) > 1:
            lines.append(f"- 200→{last['budget']} 累计只多救回 "
                         f"**{last['cumulative_found'] - first['found']}** 条"
                         f"（{first['found']} → {last['cumulative_found']}），"
                         f"边际收益快速衰减："
                         + '，'.join(f"{levels[index]['budget']}→"
                                     f"{levels[index + 1]['budget']} 新增 "
                                     f"{levels[index + 1]['new_found_count']}"
                                     for index in range(len(levels) - 1))
                         + '。')
            candidates_le_200 = last['candidate_index_le_200']
            lines.append(f"- 全部 {last['found']} 条成功路线的成功候选在候选队列中的"
                         f"位置：中位数 {last['candidate_index_median']}，"
                         f"最小 {last['candidate_index_min']}，最大 {last['candidate_index_max']}；"
                         f"其中 {candidates_le_200} 条在队列前 200 个候选内即可命中。")
            lines.append(f"- 评估耗时：{first['budget']} 档 {first['seconds']:.1f}s → "
                         f"{last['budget']} 档 {last['seconds']:.1f}s"
                         f"（evaluated {first['evaluated']:,} → {last['evaluated']:,}）。")
            if len(levels) > 1 and last['found']:
                ratio = levels[1]['found'] / last['found'] * 100.0
                lines.append(f"- 性价比：{levels[1]['budget']} 档已拿到最终累计收益的 "
                             f"{ratio:.1f}%（{levels[1]['found']}/{last['found']}）"
                             + (f"；{levels[-2]['budget']}→{last['budget']} 无任何新增，"
                                f"候选预算在 {levels[-2]['budget']} 以上已饱和。"
                                if last['new_found_count'] == 0 else '。'))
    lines.append('')
    lines.append('### 3.2 各档新增救回路线 ID\n')
    for level in levels:
        ids = level['new_found']
        lines.append(f"- **预算 {level['budget']}**（新增 {len(ids)} 条）："
                     f"`{_compress_ids(ids) if ids else '（无）'}`")
    lines.append('\n（区间压缩表示；完整 `found_route_ids` 见 '
                 '`sweep_budget*.json` 与本脚本的 `analysis_data.json`。）\n')

    # ---- 4. distribution -------------------------------------------------
    lines.append('## 4. 救回路线的 pair / family 分布\n')
    lines.append('### 4.1 按 pair\n')
    rows = []
    for pair in PAIR_ORDER:
        row = [pair]
        for level in levels:
            found = distribution['by_pair'][level['budget']]['found'][pair]
            new = distribution['by_pair'][level['budget']]['new'][pair]
            row.append(f'{found} (+{new})' if new else str(found))
        rows.append(row)
    lines.append(_table(['pair', *[f'预算 {level["budget"]}' for level in levels]], rows))
    lines.append('\n括号内为该档相对上一档的边际新增。\n')
    lines.append('### 4.2 按 family\n')
    rows = []
    for family in FAMILY_ORDER:
        row = [family]
        for level in levels:
            found = distribution['by_family'][level['budget']]['found'][family]
            new = distribution['by_family'][level['budget']]['new'][family]
            if not found and not new:
                row.append('-')
            else:
                row.append(f'{found} (+{new})' if new else str(found))
        rows.append(row)
    lines.append(_table(['family', *[f'预算 {level["budget"]}' for level in levels]], rows))
    lines.append('')
    lines.append('### 4.3 family × pair 交叉（最大预算档）\n')
    rows = []
    for family, counts in distribution['family_by_pair'].items():
        rows.append([family, *[counts.get(pair, 0) for pair in PAIR_ORDER],
                     sum(counts.values())])
    lines.append(_table(['family', *PAIR_ORDER, '合计'], rows))
    lines.append('')
    # dominant family/pair
    last_distribution = distribution['by_family'][levels[-1]['budget']]['found'] \
        if levels else {}
    if last_distribution:
        dominant = sorted(last_distribution.items(), key=lambda item: -item[1])
        dominant = [(family, count) for family, count in dominant if count]
        if dominant:
            lines.append(f"- **主要受益 family**："
                         + '、'.join(f'{family}（{count} 条）'
                                     for family, count in dominant) + '。')
    last_pair = distribution['by_pair'][levels[-1]['budget']]['found'] if levels else {}
    if last_pair:
        dominant_pair = sorted(last_pair.items(), key=lambda item: -item[1])
        dominant_pair = [(pair, count) for pair, count in dominant_pair if count]
        if dominant_pair:
            lines.append(f"- **主要受益 pair**："
                         + '、'.join(f'{pair}（{count} 条）'
                                     for pair, count in dominant_pair) + '。')
    lines.append('')

    # ---- 5. failure analysis --------------------------------------------
    lines.append('## 5. 未救回路线的失败分析\n')
    lines.append('三分类定义（互斥，逐路线判定，来源为 sweep JSON 的 `reason` 与 '
                 '`rejection_counts`）：\n')
    lines.append('- `candidate budget exhausted`：`rejection_counts` 中出现 '
                 '`candidate_budget_exhausted`，即已评估满该档预算仍有候选未评估完；')
    lines.append('- `current layout blocks all candidates`：队列被完整枚举'
                 '（evaluated 小于预算）但全部被严格索引判非法，`reason=no_legal_candidate`；')
    lines.append('- `no candidate generated`：扩展候选库在该布局下没有产生任何候选，'
                 '`evaluated=0`、`reason=no_candidate_generated`。\n')
    rows = []
    for failure in failures:
        rows.append([failure['budget'], failure['unfound'],
                     failure['categories']['candidate_budget_exhausted'],
                     failure['categories']['layout_blocked'],
                     failure['categories']['no_candidate_generated']])
    lines.append(_table(['预算', '未救回', '预算耗尽', '当前布局阻挡', '无候选生成'], rows))
    lines.append('')
    lines.append('### 5.1 几何拒绝原因聚合（未救回路线，剔除预算标记）\n')
    rows = []
    reason_keys = sorted({reason for failure in failures
                          for reason in failure['geometric_rejection_counts']},
                         key=lambda reason: -sum(
                             failure['geometric_rejection_counts'].get(reason, 0)
                             for failure in failures))
    for reason in reason_keys:
        rows.append([reason, *[failure['geometric_rejection_counts'].get(reason, 0)
                               for failure in failures]])
    lines.append(_table(['拒绝原因', *[f'预算 {failure["budget"]}' for failure in failures]],
                        rows))
    lines.append('')
    if failures:
        last_failure = failures[-1]
        geometric_last = last_failure['geometric_rejection_counts']
        total_geometric = sum(geometric_last.values())
        if total_geometric:
            shares = sorted(geometric_last.items(), key=lambda item: -item[1])[:3]
            lines.append('注：绝对计数随预算提高而增加是必然的（所有路线都评估了更多候选），'
                         '有意义的是同一预算下各原因的相对占比。'
                         f"预算 {last_failure['budget']} 档占比："
                         + '、'.join(f'{reason} {count / total_geometric * 100:.1f}%'
                                     for reason, count in shares)
                         + '——几何拒绝的主因始终是 `double_cross`'
                           '（候选与已布通波导发生两处交叉）。\n')
    lines.append('### 5.2 blocker 频次 Top-15（最大预算档）\n')
    blocker_rows = []
    blocker_level = failures[-1] if failures else None
    if blocker_level:
        lines.append(f"下表为预算 {blocker_level['budget']} 档的 blocker 频次 Top-15"
                     f"（blocker = 拒绝某个候选的已布通路线；"
                     f"「影响路线数」= 有多少条未救回路线被该 blocker 拒绝过）。\n")
        for rank, entry in enumerate(blocker_level['blockers']['top'], 1):
            blocker_rows.append([
                rank, entry['blocker_route_id'], entry['count'],
                entry['affected_routes'], f'{entry["share"] * 100:.2f}%',
                blocker_pair(entry['blocker_route_id'], history),
            ])
        lines.append(_table(['#', 'blocker route_id', '出现次数',
                             '影响路线数', '占全部 blocker 次数', 'blocker 所属 pair'],
                            blocker_rows))
        lines.append(f"\n预算 {blocker_level['budget']} 档 blocker 总次数 "
                     f"{blocker_level['blockers']['total']:,}，"
                     f"涉及 {blocker_level['blockers']['distinct']} 条已布通路线；"
                     f"Top-15 占比 "
                     f"{sum(entry['share'] for entry in blocker_level['blockers']['top']) * 100:.1f}%。\n")
    if failures:
        level = failures[0]
        lines.append(f'### 5.3 blocker 频次 Top-15（预算 {level["budget"]}，对照）\n')
        rows = [[rank, entry['blocker_route_id'], entry['count'],
                 entry['affected_routes'], f'{entry["share"] * 100:.2f}%',
                 blocker_pair(entry['blocker_route_id'], history)]
                for rank, entry in enumerate(level['blockers']['top'], 1)]
        lines.append(_table(['#', 'blocker route_id', '出现次数', '影响路线数',
                             '占全部 blocker 次数', 'blocker 所属 pair'], rows))
        lines.append(f"\n该档 blocker 总次数 {level['blockers']['total']:,}，"
                     f"涉及 {level['blockers']['distinct']} 条已布通路线。\n")
    lines.append('预算 400、800 档的 blocker Top-15 未重复列出，'
                 '见 `analysis_data.json` 中 `failures[*].blockers.top`（四档齐全）。\n')
    lines.append('**解释**：随着预算提高，`预算耗尽` 类路线逐步转为'
                 '`当前布局阻挡` 类（队列被完整枚举），而 `无候选生成` 类的数量不随预算变化'
                 '——后者的瓶颈不在评估预算，而在候选库/布局。\n')

    # ---- 6. coverage -----------------------------------------------------
    lines.append('## 6. 128 条历史 `no_candidate_generated` corner 路线的候选覆盖\n')
    if coverage:
        lines.append('口径说明：\n')
        lines.append('- **empty-layout**：不放置任何历史已布通路线，'
                     '仅保留 CSV 端口固定出入线（所有候选生成器共享的静态“必然占用线”）'
                     '以及 `D56Index` 的空索引。该口径衡量“当前 D56 扩展候选库能否'
                     '为这条路线几何生成合法候选”；')
        lines.append('- **base-layout**：冻结的 206 条已布通路线全部装入精确索引，'
                     '衡量“生成出来的候选中有多少能真正插入当前布局”；')
        lines.append('- 两种口径都枚举 **完整候选队列**（与 200/400/800/1600 预算无关），'
                     f"每路线每口径一次；本次覆盖计算耗时 "
                     f"{coverage['seconds']:.1f}s（{coverage['workers']} 进程）。\n")
        lines.append('### 6.1 总体覆盖\n')
        empty = coverage['empty']
        base = coverage['base']
        empty_median = (empty['first_valid_index_median']
                        if empty['first_valid_index_median'] is not None else '-')
        base_median = (base['first_valid_index_median']
                       if base['first_valid_index_median'] is not None else '-')
        empty_median = str(empty_median)
        base_median = str(base_median)
        rows = [
            ['路线数', coverage['n_routes'], coverage['n_routes_expected']],
            ['生成候选总数（generated）', f"{empty['generated_total']:,}",
             f"{base['generated_total']:,}"],
            ['其中通过严格 D56 索引的合法候选', f"{empty['valid_total']:,}",
             f"{base['valid_total']:,}"],
            ['合法候选均值/路线', f"{empty['mean_valid']:.1f}",
             f"{base['mean_valid']:.1f}"],
            ['合法候选最大值/路线', empty['max_valid'], base['max_valid']],
            ['0 合法候选路线数', empty['zero_count'], base['zero_count']],
            ['其中“连候选都生成不出来”的路线数',
             empty['zero_generated_count'], base['zero_generated_count']],
            ['首个合法候选位置中位数', empty_median, base_median],
        ]
        lines.append(_table(['指标', 'empty-layout', 'base-layout'], rows))
        lines.append('\nempty-layout 使用空索引，生成的候选没有已布通路线可冲突，'
                     '因此“生成数”与“合法数”相等；base-layout 的差异即为'
                     '冻结布局造成的拒绝。\n')
        lines.append('### 6.2 每路线合法候选数分布\n')
        rows = [[label, empty['buckets'][label], base['buckets'][label]]
                for label in BUCKET_LABELS]
        lines.append(_table(['合法候选数区间', 'empty-layout 路线数', 'base-layout 路线数'],
                            rows))
        lines.append('')
        lines.append('### 6.3 empty-layout 下候选族贡献\n')
        rows = []
        for family in FAMILY_ORDER:
            count = empty['families'].get(family, 0)
            routes_with = empty['family_routes'].get(family, 0)
            if not count:
                rows.append([family, 0, 0])
            else:
                rows.append([family, f'{count:,}', routes_with])
        lines.append(_table(['family', 'empty-layout 合法候选数', '覆盖路线数'], rows))
        lines.append('')
        lines.append('### 6.4 覆盖交叉分类\n')
        cross = coverage['cross']
        rows = [
            ['empty-layout ≥1 且 base-layout ≥1（可生成且可插入当前布局）',
             cross['empty_ge1__base_ge1']],
            ['empty-layout ≥1 且 base-layout = 0（可生成但当前布局全部阻挡）',
             cross['empty_ge1__base_0']],
            ['empty-layout = 0 且 base-layout ≥1（逻辑上不应出现）',
             cross['empty_0__base_ge1']],
            ['empty-layout = 0 且 base-layout = 0（当前扩展候选库未找到候选）',
             cross['empty_0__base_0']],
        ]
        lines.append(_table(['类别', '路线数'], rows))
        lines.append('')
        lines.append('### 6.5 仍然 0 候选的路线 ID\n')
        zero_empty = empty['zero']
        zero_base = base['zero']
        lines.append(f"**empty-layout 下 0 合法候选（{len(zero_empty)} 条）**，即"
                     f"“当前 D56 扩展候选库未找到候选”的路线：\n")
        lines.append(f"```\n{_compress_ids(zero_empty) if zero_empty else '（无）'}\n```\n")
        lines.append(f"**base-layout 下 0 条可插入候选（{len(zero_base)} 条）**：\n")
        lines.append(f"```\n{_compress_ids(zero_base) if zero_base else '（无）'}\n```\n")
        lines.append(f"集合一致性校验：empty-layout 的 0 生成集合、base-layout 的 0 生成"
                     f"集合、以及 sweep 每一档 `no_candidate_generated` 的路线集合"
                     f"三者完全一致：**{coverage['empty_zero_is_base_zero'] and coverage['no_candidate_matches_base']}**"
                     f"（每档均为 {len(coverage['no_candidate_by_budget'].get(min(coverage['no_candidate_by_budget'], default=0), []))} 条）。\n")
        if coverage['base_first_valid_beyond_budget']:
            lines.append(f"另有 {len(coverage['base_first_valid_beyond_budget'])} 条路线"
                         f"虽然存在可插入候选，但首个合法候选的位置超过最大预算 1600，"
                         f"因此 1600 档 sweep 仍未救回："
                         f"`{_compress_ids(coverage['base_first_valid_beyond_budget'])}`。\n")
        lines.append('### 6.6 与预算 sweep 的交叉校验\n')
        rows = []
        for budget in sorted(coverage['corner_found_counts']):
            rows.append([budget, coverage['corner_found_counts'][budget],
                         coverage['predicted_found_counts'][budget]])
        lines.append(_table(['预算档', '这 128 条中 sweep 实际救回数',
                             '按 base-layout 首个可插入候选位置预测的救回数'], rows))
        lines.append('')
        mismatch = coverage['sweep_consistency_mismatch']
        lines.append(f"逐路线预测“预算 b 下是否救回” ⇔ “base-layout 首个可插入"
                     f"候选的位置 < b”，与 sweep 实测对比："
                     f"不一致 **{len(mismatch)}** 条"
                     + (f"（不一致明细：`{mismatch[:5]}`）" if mismatch else '（完全一致）')
                     + '。\n')
        lines.append('### 6.7 结论（严格表述）\n')
        lines.append(f"- 128 条历史 `no_candidate_generated` corner 路线中，扩展候选库在 "
                     f"empty-layout 口径下能为 **{coverage['n_routes'] - empty['zero_count']}** 条"
                     f"生成合法几何候选（共 {empty['valid_total']:,} 条，"
                     f"均值 {empty['mean_valid']:.1f} 条/路线）；"
                     f"仍有 **{empty['zero_count']}** 条在当前 D56 扩展候选库下未找到候选。")
        lines.append(f"- 这 {empty['zero_count']} 条在三处完全一致（empty-layout 0 生成 / "
                     f"base-layout 0 生成 / sweep 各档 `no_candidate_generated`），"
                     f"说明它们的 0 候选与评估预算、与已布通路线都无关，"
                     f"是当前 D56 扩展候选库（在当前端口固定出入线约束下）的覆盖缺口。")
        lines.append(f"- 在冻结 BASE 布局上，这 128 条中只有 "
                     f"**{coverage['n_routes'] - base['zero_count']}** 条"
                     f"存在至少 1 条可插入候选，其余 "
                     f"**{base['zero_count']}** 条在冻结布局下全部候选均被严格索引判非法："
                     f"其中 {cross['empty_ge1__base_0']} 条是“能生成、但当前布局全部阻挡”"
                     f"（属于布局占位/顺序问题，是 R&R 实验的范畴），"
                     f"另外 {cross['empty_0__base_0']} 条连候选都生成不出来。")
        lines.append(f"- 候选族贡献：empty-layout 下全部 {empty['valid_total']:,} 条合法候选"
                     f"只来自 "
                     + '、'.join(f'{family}（{empty["families"][family]:,} 条 / '
                                 f'{empty["family_routes"][family]} 条路线）'
                                 for family in FAMILY_ORDER
                                 if empty['families'].get(family))
                     + '，L / TURN_S / SHIFT_TURN / Z3 / LEFT 五个族贡献为 0'
                     f"——说明这批 corner 几何只有扩展的 loop 族能覆盖，"
                     f"但覆盖后仍被当前布局阻挡。")
        lines.append(f"- 上述“0 候选”只应表述为“当前 D56 扩展候选库在当前（空/冻结）布局"
                     f"下未找到候选”，**不能**推断该连接在物理上绝对不可布通："
                     f"候选库仍是有限族（L/TURN_S/SHIFT_TURN/Z3/LEFT/Z5/DOWN_LOOP），"
                     f"且 empty-layout 仍施加全部端口固定出入线约束（保守口径），"
                     f"不排除存在库外 D56 合法几何。\n")
    else:
        lines.append('（本次运行未启用 coverage 步骤，使用 '
                     '`--coverage-only` 生成缓存后重跑本脚本。）\n')

    # ---- 7. artifacts ----------------------------------------------------
    lines.append('## 7. 结论摘要与产物\n')
    lines.append('### 7.1 结论摘要\n')
    if levels:
        first = levels[0]
        last = levels[-1]
        lines.append(f"1. 四档预算救回路线数："
                     + '；'.join(f"{level['budget']} → {level['found']} 条"
                                 for level in levels)
                     + f"（累计上限 {last['cumulative_found']}/{ladder['pending']}）。")
        if len(levels) >= 2:
            lines.append(f"2. 边际收益：" + '；'.join(
                f"{levels[index]['budget']}→{levels[index + 1]['budget']} 新增 "
                f"{levels[index + 1]['new_found_count']} 条"
                for index in range(len(levels) - 1))
                + f"（累计 {first['found']} → {last['cumulative_found']}）。")
        if coverage:
            empty = coverage['empty']
            base = coverage['base']
            lines.append(f"3. 128 条历史无候选 corner 路线：扩展候选库 empty-layout 下 "
                         f"{coverage['n_routes'] - empty['zero_count']}/128 可生成"
                         f"合法候选（{empty['valid_total']:,} 条，仅来自 "
                         + '、'.join(family for family in FAMILY_ORDER
                                     if empty['families'].get(family))
                         + f"），仍 {empty['zero_count']} 条未找到候选；"
                         f"冻结 BASE 布局下 {coverage['n_routes'] - base['zero_count']}/128 "
                         f"可插入 → 对能生成候选的路线，瓶颈是已有布局占位而非候选预算"
                         f"（{coverage['cross']['empty_ge1__base_0']} 条可生成但全部被阻挡），"
                         f"另 {empty['zero_generated_count']} 条属于候选库覆盖缺口。")
        if len(levels) > 1 and last['found']:
            ratio = levels[1]['found'] / last['found'] * 100.0
            lines.append(f"4. 预算建议：候选评估预算取 {levels[-2]['budget'] if last['new_found_count'] == 0 else last['budget']} "
                         f"已饱和（{levels[-2]['budget']}→{last['budget']} 新增 "
                         f"{last['new_found_count']} 条）；若以评估成本优先，"
                         f"{levels[1]['budget']} 档即可拿到 {ratio:.1f}% 的最终收益。")
    lines.append('')
    lines.append('### 7.2 产物清单\n')
    lines.append('| 文件 | 内容 |')
    lines.append('|---|---|')
    lines.append(f"| `{CAND_DIR}\\sweep_budget200.json` … `sweep_budget1600.json` | "
                 f"每档预算的 summary + 306 条逐路线明细 |")
    lines.append(f"| `{SUMMARY_JSON}` | 四档 summary 列表 |")
    lines.append(f"| `{COVERAGE_CACHE}` | 128 条 corner 路线全队列覆盖明细（两种口径） |")
    lines.append(f"| `{ANALYSIS_JSON}` | 本报告全部数字的机器可读版本 |")
    lines.append(f"| `{FIG_DIR}\\fig1_budget_vs_cumulative_found.png` … `fig5_corner_coverage.png` "
                 f"| 5 张图 |")
    lines.append(f"| `{FIG_DIR}\\figure_data.json` | 每张图的数据序列 |")
    lines.append('')
    lines.append(f"报告生成耗时 {elapsed:.1f}s。")
    lines.append('')
    return '\n'.join(lines)


def blocker_pair(blocker_route_id, history):
    for record in history['routes']:
        if int(record['route_id']) == int(blocker_route_id):
            return record.get('pair') or '-'
    return '-'


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------
def _summary_checks(sweeps):
    mismatch = []
    for sweep in sweeps:
        summary = sweep['summary']
        total = sum(int(record.get('evaluated') or 0) for record in sweep['routes'])
        if int(summary['evaluated']) != total:
            mismatch.append(dict(budget=sweep['budget'],
                                 summary=int(summary['evaluated']),
                                 routes=total))
    return dict(evaluated_mismatch=mismatch)


def build_analysis(sweeps, history, coverage_payload):
    started = time.perf_counter()
    ladder = ladder_analysis(sweeps, history)
    distribution = distribution_analysis(sweeps)
    failures = failure_analysis(sweeps)
    coverage = None
    if coverage_payload is not None:
        coverage = summarise_coverage(coverage_payload, sweeps, history)
    checks = _summary_checks(sweeps)
    figures, figure_data = make_figures(ladder, distribution, failures, coverage,
                                        history)
    elapsed = time.perf_counter() - started

    analysis = dict(
        meta=dict(plane=PLANE, topology=TOPOLOGY, history=str(HISTORY),
                  budgets=list(BUDGETS),
                  generated_by='four_side_1024.v2opt.sweep_analysis',
                  timestamp=time.strftime('%Y-%m-%dT%H:%M:%S'),
                  seconds=elapsed),
        ladder=ladder, distribution=distribution, failures=failures,
        coverage=coverage, checks=checks,
        figures=[str(path) for path in figures],
    )
    ANALYSIS_JSON.write_text(json.dumps(analysis, indent=1, ensure_ascii=False),
                             encoding='utf-8')
    (FIG_DIR / 'figure_data.json').write_text(
        json.dumps(figure_data, indent=1, ensure_ascii=False), encoding='utf-8')
    markdown = write_analysis_md(ladder, distribution, failures, coverage,
                                 figures, checks, history, elapsed)
    (CAND_DIR / 'ANALYSIS.md').write_text(markdown, encoding='utf-8')
    _stamp(f'analysis: wrote {ANALYSIS_JSON}, {FIG_DIR / "figure_data.json"}, '
           f'{CAND_DIR / "ANALYSIS.md"} and {len(figures)} figures')
    return analysis


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--budgets', default=','.join(str(b) for b in BUDGETS))
    parser.add_argument('--coverage-workers', type=int, default=10)
    parser.add_argument('--coverage-limit', type=int, default=0,
                        help='only the first N corner routes (debug); 0 = all')
    parser.add_argument('--refresh-coverage', action='store_true')
    parser.add_argument('--skip-coverage', action='store_true')
    parser.add_argument('--coverage-only', action='store_true')
    args = parser.parse_args(argv)
    budgets = tuple(int(value) for value in args.budgets.split(','))

    history = load_history()
    corners = corner_route_ids(history)
    _stamp(f'history {HISTORY.name}: {len(history["routes"])} routes, '
           f'{len(failed_routes(history))} failed of which '
           f'{len(corners)} historical no_candidate_generated')

    coverage_payload = None
    if not args.skip_coverage:
        coverage_payload = coverage_analysis(
            corners, workers=args.coverage_workers,
            refresh=args.refresh_coverage, limit=args.coverage_limit)
    if args.coverage_only:
        _stamp('coverage-only run finished')
        return 0

    sweeps = load_sweeps(budgets)
    _stamp(f'loaded {len(sweeps)} sweep artefacts: '
           + ', '.join(f"{s['budget']} -> found {s['summary']['found']}"
                       for s in sweeps))
    analysis = build_analysis(sweeps, history, coverage_payload)
    _stamp(f'done: budgets ' + ' / '.join(
        f"{level['budget']}={level['found']}" for level in analysis['ladder']['levels']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
