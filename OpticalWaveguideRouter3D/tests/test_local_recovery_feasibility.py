"""Sandbox invariants and independent exact differential fixtures."""
from copy import deepcopy
from itertools import combinations
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from local_recovery_feasibility import *
from src.models import Point2D,Port,Waveguide,SmoothedRoute2D,LineSegment2D
from src.router_2d import prepare_waveguide_2d
from src.multi_crossing import detect_multi_waveguide_crossings

def fixture():
    w=Waveguide(1,Port(2,1,None,Point2D(0,150)),Port(3,2,None,Point2D(20,150)))
    return w,prepare_waveguide_2d(w,150,0)

def line(r,a,b):return SmoothedRoute2D(r,[LineSegment2D(Point2D(*a),Point2D(*b))])

def test_unique_victim_score():
    assert victim_scores([(1,2,3),(3,2,1),(1,3,4)])=={1:2,2:1,3:2,4:1}

def test_score_primary_before_id():
    assert victim_order((1,2,3),{1:9,2:2,3:5},set(),{1:100,2:1,3:30})==[2,3,1]

def test_alternate_then_final_id():
    assert victim_order((3,2,1),{1:2,2:2,3:2},set(),{1:8,2:9,3:9})==[2,3,1]

def test_tie_preserved_in_scores():
    s={1:2,2:2,3:4};before=deepcopy(s)
    victim_order((1,2,3),s,set(),{1:3,2:3,3:3})
    assert s==before and s[1]==s[2]

def test_special_excluded_even_lower():
    assert victim_order((1,2,3),{1:1,2:2,3:3},{1},{2:1,3:1})==[2,3]

def test_all_special():
    assert victim_order((1,2,3),{}, {1,2,3},{})==[]

def test_temporary_release():
    o=[None,3,1,2];t=released_occupancy(o,1)
    assert t==[None,3,None,2] and o==[None,3,1,2]

def test_release_failure_no_mutation():
    for o in ([None,2],[1,1,2]):
        before=deepcopy(o)
        try:released_occupancy(o,1)
        except ValueError:pass
        else:assert False
        assert o==before

def test_geometry_endpoint_isolation():
    w,p=fixture();before=deepcopy((w,p));c=candidate_geometry(w,p,0,[50.],set())
    c.segments[0].start.x=888
    assert (w,p)==before

def test_special_geometry_rejection():
    w,p=fixture()
    try:candidate_geometry(w,p,0,[50.],{1})
    except ValueError:pass
    else:assert False

def test_local_delta_differential():
    old={1:line(1,(-2,0),(2,0)),2:line(2,(0,-2),(0,2)),
         3:line(3,(-2,-1.95),(2,2.05)),4:line(4,(-2,1),(2,1))}
    fixed={k:find_physical_route_intersections_2d(old[k[0]],old[k[1]]) for k in combinations(old,2)}
    before=deepcopy((old,fixed))
    for y in (0.,.1,1.5):
        c=line(1,(-2,y),(2,y));d=local_pairs(c,old)
        assert set(d)=={(1,2),(1,3),(1,4)}
        got=local_multis(1,d,fixed)
        allroutes={**old,1:c}
        ev=[e for a,b in combinations(allroutes.values(),2) for e in find_physical_route_intersections_2d(a,b)]
        expected={m.route_ids for m in detect_multi_waveguide_crossings(ev) if m.classification=='multi_waveguide_crossing' and 1 in m.route_ids}
        assert got==expected
    assert before==(old,fixed)

def test_multiplicity_transition():
    from src.physical_intersections import PhysicalRouteIntersection as E
    e=lambda a,b,x,y:E(a,b,Point2D(x,y),'cross')
    fixed={(2,3):[e(2,3,0,.05)]};d={(1,2):[e(1,2,0,0)],(1,3):[e(1,3,.05,0)]}
    assert local_multis(1,d,fixed)=={(1,2,3)}
    d[(1,2)].append(e(1,2,2,2));assert not local_multis(1,d,fixed)
    d[(1,2)].pop();d[(1,2)].append(E(1,2,Point2D(3,3),'touch'))
    assert local_multis(1,d,fixed)=={(1,2,3)}

def test_multi_delta_formula():
    base={(1,2,3),(1,4,5),(2,4,6)}
    s=score_delta((1,2,3),1,base,{(1,4,5),(1,6,7)})
    assert s['M_after']==3 and s['old_multi_removed']==1 and s['new_multi_created']==1
    assert not acceptable(s)

def test_strict_improvement():
    s=score_delta((1,2,3),1,{(1,2,3),(2,4,6)},set())
    assert acceptable(s) and s['M_after']==1
    assert not acceptable(s,False)

def test_target_must_disappear():
    s=score_delta((1,2,3),1,{(1,2,3),(1,4,5)},{(1,2,3)})
    assert s['M_after']==1 and not acceptable(s)

def test_increase_rejected():
    s=score_delta((1,2,3),1,{(1,2,3)},{(1,4,5),(1,6,7)})
    assert not acceptable(s)

def test_deterministic_candidate_rank():
    rows=[dict(M_after=3,new_multi_created=1,track_displacement=4,track_index=i) for i in (9,7)]
    assert min(rows,key=candidate_rank)['track_index']==7
    assert min(rows[::-1],key=candidate_rank)==min(rows,key=candidate_rank)

def test_evaluation_rollback_and_occupied_rejection():
    w,p=fixture();grid=[50.,60.,70.];o=[1,2,None]
    routes={1:candidate_geometry(w,p,0,grid,set()),2:line(2,(40,0),(40,150))}
    args=((1,2,3),1,2,grid,o,{1:w},{1:p},routes,{},set(),set())
    before=deepcopy(args)
    s,c,d=evaluate(*args)
    assert args==before and not s['accepted']
    c.segments[0].start.x=1000
    assert args==before
    bad=list(args);bad[2]=1
    try:evaluate(*bad)
    except ValueError:pass
    else:assert False
    assert args==before


def test_invalid_track_index_rejected():
    w,p=fixture()
    for i in (-1,1,True):
        try:candidate_geometry(w,p,i,[50.],set())
        except ValueError:pass
        else:assert False
