"""Candidate transactions, exact criterion and unchanged allocator policies."""
from copy import deepcopy
from dataclasses import replace
from unittest import TestCase
from unittest.mock import patch
from src.models import Point2D, LineSegment2D, SmoothedRoute2D
from src.multi_crossing_guard import ExactMultiCrossingGuard
from src.physical_intersections import PhysicalRouteIntersection
from src.router_2d import assign_tracks_2d, prepare_waveguides_2d, TrackPolicyConfig
from pathlib import Path
from runpy import run_path
_helpers=run_path(str(Path(__file__).with_name('test_top_u_order.py')))
fixture,wg=_helpers['fixture'],_helpers['wg']


def line(i,a,b):
    return SmoothedRoute2D(i,[LineSegment2D(Point2D(*a),Point2D(*b))])

def existing():
    g=ExactMultiCrossingGuard()
    for r in (line(1,(-2,0),(2,0)),line(2,(0,-2),(0,2))):g.commit(g.evaluate(r))
    return g

def diagonal(x=.1,y=.1):
    return line(3,(-x,2*y),(2*x,-y))

def test_guard_real_multi_rejected():
    e=existing().evaluate(diagonal())
    assert e.witness.classification=='multi_waveguide_crossing'
    assert e.witness.short_side_count==2

def test_guard_single_cross_allowed():
    g=ExactMultiCrossingGuard();g.commit(g.evaluate(line(1,(-2,0),(2,0))))
    assert g.evaluate(line(2,(0,-2),(0,2))).witness is None

def test_guard_only_one_short_allowed():
    assert existing().evaluate(diagonal(.05,.3)).witness is None

def test_guard_boundary_allowed_diagnostic():
    g=existing();assert g.evaluate(diagonal(.125,.125)).witness is None
    assert 'guard_boundary_observations' not in g.stats

def test_guard_outside_allowed_diagnostic():
    g=existing()
    key=(1,2);g.pair_cache[key]=None;g.single_cross_graph[1].remove(2);g.single_cross_graph[2].remove(1)
    assert g.evaluate(diagonal()).witness is None
    assert 'guard_outside_observations' not in g.stats

def test_guard_no_cross_allowed():
    assert existing().evaluate(line(3,(5,5),(6,5))).witness is None

def test_guard_one_neighbor_no_triangle():
    g=existing();assert g.evaluate(line(3,(1,-1),(1,1))).witness is None
    assert g.stats['candidate_triplet_evaluations']==0

def test_guard_reject_geometry_unchanged():
    g=existing();saved=deepcopy(g.routes);e=g.evaluate(diagonal());g.reject(e,10,2)
    assert g.routes==saved

def test_guard_reject_pair_cache_unchanged():
    g=existing();saved=deepcopy(g.pair_cache);e=g.evaluate(diagonal());g.reject(e,10,2)
    assert g.pair_cache==saved

def test_guard_reject_cross_cache_unchanged():
    g=existing();saved=deepcopy(g.single_cross_graph);e=g.evaluate(diagonal());g.reject(e,10,2)
    assert g.single_cross_graph==saved

def test_guard_only_commit_publishes():
    g=existing();e=g.evaluate(line(3,(1,-1),(1,1)))
    assert 3 not in g.routes and (1,3) not in g.pair_cache
    g.commit(e);assert 3 in g.routes and (1,3) in g.pair_cache

def test_guard_cannot_commit_rejected():
    g=existing()
    with TestCase().assertRaises(ValueError):g.commit(g.evaluate(diagonal()))

def test_guard_stale_evaluation_refused():
    g=existing();e=g.evaluate(line(3,(5,5),(6,5)))
    g.commit(g.evaluate(line(4,(8,8),(9,8))))
    with TestCase().assertRaises(ValueError):g.commit(e)

def test_guard_witness_deterministic():
    g=existing();a=g.evaluate(diagonal());b=g.evaluate(diagonal())
    assert a.witness==b.witness and a.witness.route_ids==(1,2,3)

def test_guard_diagnostics_do_not_commit():
    g=existing();g.evaluate(diagonal(.125,.125));assert set(g.routes)=={1,2}

def config():return TrackPolicyConfig(150,.05,.125,5,top_u_primary_order='descending')

def run(ws,g=None):return assign_tracks_2d(ws,prepare_waveguides_2d(ws,150,0),config(),guard=g)

def test_guard_off_matches_old_default():
    ws=fixture();p=prepare_waveguides_2d(ws,150,0);c=TrackPolicyConfig(150,.05,.125,5)
    assert assign_tracks_2d(ws,p,c)==assign_tracks_2d(ws,p,c,guard=None)

def test_guard_off_descending_fixture():
    a=run(fixture());assert a[0].track_index==798 and a[1].track_index==799


def scan_fixture(y1,y2,expected):
    # Synthetic rejection isolates allocator lifecycle; criterion has real-geometry tests above.
    ws=[wg(7,0,y1,40,y2)];g=ExactMultiCrossingGuard();calls=[]
    original=g.evaluate
    def evaluate(route):
        calls.append(deepcopy(route));e=original(route)
        if len(calls)==1:e.witness=existing().evaluate(diagonal()).witness
        return e
    with patch.object(g,'evaluate',side_effect=evaluate):a=run(ws,g)
    assert a[0].status=='assigned' and a[0].track_index==expected
    assert len(calls)==2 and list(g.routes)==[7]
    assert g.stats['guard_multi_rejections']==1
    assert g.later_assigned=={7}
    return a,g

def test_guard_top_u_next_scan():scan_fixture(150,150,798)
def test_guard_bottom_u_next_scan():scan_fixture(0,0,1)
def test_guard_top_bottom_z_next_scan():scan_fixture(150,0,798)
def test_guard_bottom_top_z_next_scan():scan_fixture(0,150,798)

def test_guard_special_not_evaluated():
    g=ExactMultiCrossingGuard();a=run([wg(1,0,150,4,0)],g)
    assert a[0].status=='unsupported_geometry' and not g.routes and not g.stats

def test_guard_exclusive_and_deterministic():
    ws=fixture();g=ExactMultiCrossingGuard();a=run(ws,g);b=run(ws,ExactMultiCrossingGuard())
    assert a==b
    tracks=[x.track_index for x in a if x.status=='assigned'];assert len(tracks)==len(set(tracks))

def test_guard_rejected_track_remains_available():
    ws=[wg(1,0,150,40,150),wg(2,-10,150,50,150)];g=ExactMultiCrossingGuard();original=g.evaluate
    def evaluate(route):
        e=original(route)
        if route.waveguide_id==1 and not g.rejections:e.witness=existing().evaluate(diagonal()).witness
        return e
    with patch.object(g,'evaluate',side_effect=evaluate):a=run(ws,g)
    assert [x.track_index for x in a]==[798,799]

def test_guard_reject_does_not_publish_assignment():
    ws=[wg(1,0,150,40,150)];saved=deepcopy(ws);g=ExactMultiCrossingGuard();original=g.evaluate
    def evaluate(route):
        e=original(route);e.witness=existing().evaluate(diagonal()).witness;return e
    # A small two-track grid verifies exhaustion without fallback.
    cfg=TrackPolicyConfig(10.225,.05,.125,5)
    ws=[wg(1,0,10.225,40,10.225)];saved=deepcopy(ws)
    with patch.object(g,'evaluate',side_effect=evaluate):
        a=assign_tracks_2d(ws,prepare_waveguides_2d(ws,10.225,0),cfg,guard=g)
    assert a[0].status=='no_available_track' and a[0].track_index is None
    assert not g.routes and not g.pair_cache and ws==saved and g.exhausted==[1]

def test_guard_real_committed_triangle_invariant():
    g=existing();bad=g.evaluate(diagonal());assert bad.witness is not None
    good=g.evaluate(diagonal(.3,.3));assert good.witness is None;g.commit(good)
    from src.multi_crossing import classify_multi_crossing
    pairs={k:[PhysicalRouteIntersection(*k,p,'cross')] for k,p in g.pair_cache.items() if p is not None}
    assert classify_multi_crossing((1,2,3),pairs).classification!='multi_waveguide_crossing'

def test_guard_grid_unchanged():
    from src.router_2d import build_track_grid_2d
    grid=build_track_grid_2d(config());run(fixture(),ExactMultiCrossingGuard())
    assert grid==build_track_grid_2d(config()) and len(grid)==800
    assert abs(grid[1]-grid[0]-.175)<1e-12

def test_guard_real_arc_double_is_not_rejected():
    from math import sqrt, pi
    from src.models import ArcSegment2D
    g=ExactMultiCrossingGuard();g.commit(g.evaluate(line(1,(-2,0),(2,0))))
    q=sqrt(.5)
    arc=SmoothedRoute2D(2,[ArcSegment2D(Point2D(q,-q),Point2D(0,1),Point2D(0,0),.75*pi), ArcSegment2D(Point2D(0,1),Point2D(-q,-q),Point2D(0,0),.75*pi)])
    e=g.evaluate(arc);assert e.witness is None;g.commit(e)
    assert g.pair_cache[(1,2)] is None
    e=g.evaluate(line(3,(0,-2),(0,2)))
    assert e.witness is None and 'guard_outside_observations' not in g.stats


def test_guard_witness_independent_of_committed_insertion_order():
    g=ExactMultiCrossingGuard()
    for r in (line(2,(0,-2),(0,2)),line(1,(-2,0),(2,0))):g.commit(g.evaluate(r))
    assert g.evaluate(diagonal()).witness==existing().evaluate(diagonal()).witness

def test_fast_first_witness_stops_pair_and_triangle_work():
    g=existing();g.commit(g.evaluate(line(4,(10,10),(11,10))))
    from src import multi_crossing_guard as module
    original=module.get_single_cross_or_none
    with patch.object(module,'get_single_cross_or_none',wraps=original) as pair_test, \
         patch.object(module,'classify_multi_crossing',wraps=module.classify_multi_crossing) as classify:
        assert g.evaluate(diagonal()).witness is not None
    assert pair_test.call_count==2 and classify.call_count==1


def test_fast_no_neighbors_skips_detector():
    with patch('src.multi_crossing_guard.classify_multi_crossing',side_effect=AssertionError('unneeded')):
        assert existing().evaluate(line(3,(10,10),(11,10))).witness is None


def test_fast_one_neighbor_skips_detector():
    g=existing()
    with patch('src.multi_crossing_guard.classify_multi_crossing',side_effect=AssertionError('unneeded')):
        assert g.evaluate(line(3,(1,-1),(1,1))).witness is None


def test_fast_disconnected_neighbors_skip_detector():
    g=ExactMultiCrossingGuard()
    for i,y in ((1,0),(2,1)):g.commit(g.evaluate(line(i,(-2,y),(2,y))))
    with patch('src.multi_crossing_guard.classify_multi_crossing',side_effect=AssertionError('no cached edge')):
        assert g.evaluate(line(3,(0,-2),(0,2))).witness is None
    assert g.stats['triangle_cache_checks']==0


def test_fast_rejection_preserves_adjacency():
    g=existing();saved=deepcopy(g.single_cross_graph);e=g.evaluate(diagonal());g.reject(e,1,2)
    assert saved==g.single_cross_graph


def test_fast_adjacency_updates_only_on_commit():
    g=existing();e=g.evaluate(line(3,(1,-1),(1,1)))
    assert 3 not in g.single_cross_graph and 3 not in g.single_cross_graph[1]
    g.commit(e);assert g.single_cross_graph[3]=={1} and 3 in g.single_cross_graph[1]


def test_fast_minimal_cache_has_no_full_events():
    g=existing()
    assert all(value is None or isinstance(value,Point2D) for value in g.pair_cache.values())


def test_fast_incomplete_accept_cannot_commit():
    g=existing();e=g.evaluate(line(3,(10,10),(11,10)));e.events.clear()
    with TestCase().assertRaises(ValueError):g.commit(e)
    assert set(g.routes)=={1,2}


def test_independent_validation_accepted_set_zero():
    from scripts.validate_exact_multi_guard_fast import independent_validation
    g=existing();g.commit(g.evaluate(diagonal(.3,.3)))
    with patch.object(g,'evaluate',side_effect=AssertionError('guard must not run')):
        result=independent_validation(list(g.routes.values()))
    assert result['counts']['multi_waveguide_crossing']==0 and result['checked_pairs']==3


def test_independent_validation_detects_corrupted_safe_metadata():
    from scripts.validate_exact_multi_guard_fast import independent_validation
    g=existing();g.commit(g.evaluate(diagonal(.3,.3)))
    frozen=deepcopy(list(g.routes.values()));frozen[-1]=diagonal()
    with patch('src.multi_crossing_guard.ExactMultiCrossingGuard.evaluate',side_effect=AssertionError('metadata forbidden')):
        result=independent_validation(frozen)
    assert result['counts']['multi_waveguide_crossing']==1
    assert g.routes[3]!=frozen[-1]


def test_fast_wrapper_matches_cross_only_semantics():
    from src.multi_crossing_guard import get_single_cross_or_none
    events=[PhysicalRouteIntersection(1,2,Point2D(0,0),'cross'),
            PhysicalRouteIntersection(1,2,Point2D(1,1),'touch')]
    with patch('src.multi_crossing_guard.find_physical_route_intersections_2d',return_value=events):
        assert get_single_cross_or_none(line(1,(0,0),(1,0)),line(2,(0,1),(1,1)))==Point2D(0,0)


def test_fast_repeated_witness_deterministic_after_short_circuit():
    g=existing();g.commit(g.evaluate(line(4,(10,10),(11,10))))
    assert g.evaluate(diagonal()).witness==g.evaluate(diagonal()).witness

def test_exhaustion_covers_entire_available_grid():
    from src.router_2d import build_track_grid_2d
    cfg=TrackPolicyConfig(11.0,.05,.125,5)
    ws=[wg(1,0,11.0,40,11.0)]
    guard=ExactMultiCrossingGuard();original=guard.evaluate
    witness=existing().evaluate(diagonal()).witness
    def reject(route):
        result=original(route);result.witness=witness;return result
    with patch.object(guard,'evaluate',side_effect=reject):
        assignments=assign_tracks_2d(ws,prepare_waveguides_2d(ws,11.0,0),cfg,guard=guard)
    expected=list(reversed(range(len(build_track_grid_2d(cfg)))))
    assert [r['track_index'] for r in guard.rejections]==expected
    assert assignments[0].status=='no_available_track' and guard.exhausted==[1]
    assert not guard.routes and not guard.pair_cache and not guard.single_cross_graph


def test_timeout_during_scan_is_not_exhaustion():
    cfg=TrackPolicyConfig(11.0,.05,.125,5)
    ws=[wg(1,0,11.0,40,11.0)]
    guard=ExactMultiCrossingGuard();original=guard.evaluate
    witness=existing().evaluate(diagonal()).witness
    def interrupted(route):
        if guard.rejections:raise TimeoutError('Simulated performance limit')
        result=original(route);result.witness=witness;return result
    with patch.object(guard,'evaluate',side_effect=interrupted):
        with TestCase().assertRaises(TimeoutError):
            assign_tracks_2d(ws,prepare_waveguides_2d(ws,11.0,0),cfg,guard=guard)
    assert len(guard.rejections)==1 and not guard.exhausted
    assert not guard.routes and not guard.pair_cache and not guard.single_cross_graph