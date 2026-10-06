"""Opt-in short-circuit guard; final diagnostics belong to independent validation."""
from collections import Counter
from dataclasses import dataclass, asdict
from math import isfinite
from time import perf_counter
from .models import Point2D, SmoothedRoute2D
from .physical_intersections import find_physical_route_intersections_2d, PhysicalRouteIntersection
from .multi_crossing import classify_multi_crossing, MultiWaveguideCrossing


def get_single_cross_or_none(a: SmoothedRoute2D, b: SmoothedRoute2D,
                             tol: float = 1e-9) -> Point2D | None:
    """Reuse exact consolidation, retaining only one CROSS point or NOT_SINGLE.

    Touch/overlap alone do not qualify. If accompanied by exactly one CROSS,
    retain that CROSS, matching the existing detector's cross-only semantics.
    Full transient kernel events are discarded; no alternative geometry math.
    """
    point = None
    for event in find_physical_route_intersections_2d(a, b, tol):
        if event.kind == 'cross':
            if point is not None:
                return None
            point = event.point
    return point


@dataclass
class CandidateEvaluation:
    """Temporary pair->single point/None; rejected evaluations may be incomplete."""
    route: SmoothedRoute2D
    generation: int
    events: dict[tuple[int, int], Point2D | None]
    witness: MultiWaveguideCrossing | None


class ExactMultiCrossingGuard:
    """Incremental single-cross adjacency and first-witness rejection only."""

    def __init__(self, spacing_mm: float = 0.125, tol: float = 1e-9):
        if not all(isfinite(v) for v in (spacing_mm,tol)) or not 0 <= tol < spacing_mm:
            raise ValueError('Require positive finite spacing and smaller tolerance.')
        self.spacing_mm, self.tol = spacing_mm, tol
        self.routes: dict[int, SmoothedRoute2D] = {}
        self.pair_cache: dict[tuple[int,int], Point2D | None] = {}
        self.single_cross_graph: dict[int,set[int]] = {}
        self.stats = Counter()
        self.timings = Counter()
        self.rejections: list[dict] = []
        self.rejected_ids: set[int] = set()
        self.later_assigned: set[int] = set()
        self.exhausted: list[int] = []
        self.max_evaluation_seconds = 0.0

    def evaluate(self, route: SmoothedRoute2D) -> CandidateEvaluation:
        """Reject at first witness, including before unneeded remaining pair tests."""
        if route.waveguide_id in self.routes:
            raise ValueError('Route already committed.')
        started=perf_counter()
        self.stats['guard_evaluation_count'] += 1
        events={}; singles={}; identifier=route.waveguide_id
        try:
            for a, existing in sorted(self.routes.items()):
                t=perf_counter()
                point=get_single_cross_or_none(route,existing,self.tol)
                self.timings['candidate_pair_kernel'] += perf_counter()-t
                self.stats['candidate_existing_pair_checks'] += 1
                events[tuple(sorted((identifier,a)))]=point
                if point is None:
                    continue
                self.stats['candidate_single_cross_neighbors'] += 1
                t=perf_counter()
                # Only cached single edges to already discovered single neighbors.
                for b in sorted(self.single_cross_graph[a].intersection(singles)):
                    self.stats['triangle_cache_checks'] += 1
                    ab=tuple(sorted((a,b)))
                    points={ab:self.pair_cache[ab], tuple(sorted((identifier,a))):point,
                            tuple(sorted((identifier,b))):singles[b]}
                    pairs={key:[PhysicalRouteIntersection(*key,p,'cross')] for key,p in points.items()}
                    result=classify_multi_crossing(tuple(sorted((identifier,a,b))),pairs,self.spacing_mm,self.tol)
                    self.stats['candidate_triplet_evaluations'] += 1
                    if result.classification=='multi_waveguide_crossing':
                        self.timings['triplet_guard_evaluation'] += perf_counter()-t
                        return CandidateEvaluation(route,len(self.routes),events,result)
                self.timings['triplet_guard_evaluation'] += perf_counter()-t
                singles[a]=point
            return CandidateEvaluation(route,len(self.routes),events,None)
        finally:
            elapsed=perf_counter()-started
            self.timings['candidate_evaluation'] += elapsed
            self.max_evaluation_seconds=max(self.max_evaluation_seconds,elapsed)

    def reject(self, evaluation: CandidateEvaluation, track_index: int, track_y: float) -> None:
        """Record only the first explicit witness; never publish temporary state."""
        if evaluation.witness is None:
            raise ValueError('Cannot reject without a definite multi witness.')
        t=perf_counter()
        self.stats['guard_multi_rejections'] += 1
        self.rejected_ids.add(evaluation.route.waveguide_id)
        self.rejections.append(dict(waveguide_id=evaluation.route.waveguide_id,
            track_index=track_index,track_y=track_y,witness=asdict(evaluation.witness)))
        self.timings['candidate_reject_commit'] += perf_counter()-t

    def commit(self, evaluation: CandidateEvaluation) -> None:
        """Only accepted, complete evaluations update the cache and adjacency."""
        if evaluation.witness is not None or evaluation.generation!=len(self.routes):
            raise ValueError('Rejected or stale candidate cannot commit.')
        identifier=evaluation.route.waveguide_id
        if identifier in self.routes:
            raise ValueError('Route already committed.')
        if set(evaluation.events)!={tuple(sorted((identifier,i))) for i in self.routes}:
            raise ValueError('Incomplete accepted evaluation.')
        t=perf_counter()
        self.routes[identifier]=evaluation.route
        self.pair_cache.update(evaluation.events)
        self.single_cross_graph[identifier]=set()
        for (a,b),point in evaluation.events.items():
            if point is not None:
                self.single_cross_graph[a].add(b)
                self.single_cross_graph[b].add(a)
        if identifier in self.rejected_ids:self.later_assigned.add(identifier)
        self.timings['candidate_reject_commit'] += perf_counter()-t

    def summary(self) -> dict:
        """Cheap operation counts; no boundary/outside report diagnostics."""
        keys=('candidate_attempt_count','guard_evaluation_count','candidate_existing_pair_checks',
              'candidate_single_cross_neighbors','triangle_cache_checks','candidate_triplet_evaluations',
              'guard_multi_rejections','allocator_base_checks')
        n=self.stats['guard_evaluation_count']
        return dict(**{k:self.stats[k] for k in keys}, unique_waveguides_rejected=len(self.rejected_ids),
            rejected_then_later_assigned=len(self.later_assigned),guard_exhausted_waveguides=list(self.exhausted),
            mean_candidate_evaluation_seconds=self.timings['candidate_evaluation']/n if n else 0,
            max_candidate_evaluation_seconds=self.max_evaluation_seconds,timings=dict(self.timings))