"""Exact clearance tests for the independent four-side single-layer index."""
import math
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from four_side_1024.conflicts import ConflictIndex, _make_primitive, _exact_distance, _intersections


def line(a,b):
    return dict(kind='line',p0=a,p1=b)


def arc(c,r,a,s):
    return dict(kind='arc',center=c,radius=r,start_angle=a,sweep=s,
        p0=(c[0]+r*math.cos(a),c[1]+r*math.sin(a)),
        p1=(c[0]+r*math.cos(a+s),c[1]+r*math.sin(a+s)))


def test_crossing_is_allowed_and_measured_acute():
    idx=ConflictIndex()
    idx.add(1,[line((-5,0),(5,0))])
    result=idx.evaluate([line((-4,-4),(4,4))],stop_on_invalid=False)
    assert result['valid']
    assert result['crossings'][0]['angle_deg']==pytest.approx(45)
    assert result['crossings'][0]['x']==pytest.approx(0)


def test_crossing_does_not_excuse_remote_parallel_violation():
    idx=ConflictIndex()
    idx.add(1,[line((-10,0),(10,0))])
    # One orthogonal crossing followed by a distant close parallel segment.
    candidate=[line((0,-5),(0,5)),line((0,5),(8,5)),
               line((8,5),(8,.1)),line((8,.1),(12,.1))]
    result=idx.evaluate(candidate,stop_on_invalid=False)
    assert not result['valid']
    assert result['spacing_pairs']==[1]
    assert len(result['crossings'])==1


def test_parallel_exact_clearance_not_rejected_by_chord_tolerance():
    idx=ConflictIndex()
    idx.add(1,[line((0,0),(10,0))])
    assert idx.evaluate([line((0,.175),(10,.175))])['valid']
    assert not idx.evaluate([line((0,.17499),(10,.17499))])['valid']


def test_overlap_and_tangent_not_allowed():
    idx=ConflictIndex()
    idx.add(1,[line((-10,0),(10,0))])
    assert idx.evaluate([line((-5,0),(5,0))])['overlap_pairs']==[1]
    result=idx.evaluate([arc((0,5),5,math.pi,math.pi)])
    assert not result['valid']
    assert result['touch_pairs']==[1]


def test_self_crossing_and_backtracking_rejected():
    idx=ConflictIndex()
    result=idx.evaluate([line((-1,-1),(1,1)),line((1,1),(-1,1)),line((-1,1),(1,-1))])
    assert not result['valid']
    assert result['self_intersections']==1
    result=idx.evaluate([line((0,0),(10,0)),line((10,0),(5,0))])
    assert result['self_overlaps']==1


def test_arc_crossing_exact_angle_and_distance():
    idx=ConflictIndex()
    idx.add(1,[line((-10,2),(10,2))])
    result=idx.evaluate([arc((0,0),5,0,math.pi)],stop_on_invalid=False)
    assert len(result['crossings'])==2
    expected=math.degrees(math.acos(2/5))
    assert all(c['angle_deg']==pytest.approx(expected) for c in result['crossings'])
    # Curvature can make a straight-tangent clearance/sin(angle) window too
    # short. The exact outside-window check must reject it conservatively.
    assert not result['valid']
    assert result['spacing_pairs']==[1]
    # A concentric outer arc is near along its entire length, even if neither
    # pair of endpoint chords happen to be nearest.
    a=_make_primitive(arc((0,0),5,.1,1.5))
    b=_make_primitive(arc((0,0),5.1,.4,.5))
    assert _exact_distance(a,b)==pytest.approx(.1)


def test_near_orthogonal_arc_crossings_pass_local_clearance_check():
    idx=ConflictIndex()
    idx.add(1,[line((-10,0),(10,0))])
    result=idx.evaluate([arc((0,0),5,-math.pi/4,1.5*math.pi)],stop_on_invalid=False)
    assert result['valid']
    assert len(result['crossings'])==2
    assert all(c['angle_deg']==pytest.approx(90) for c in result['crossings'])


def test_two_near_circular_crossings_cannot_excuse_whole_pair():
    idx=ConflictIndex()
    idx.add(1,[line((-10,4.999),(10,4.999))])
    result=idx.evaluate([arc((0,0),5,0,math.pi)],stop_on_invalid=False)
    assert not result['valid']
    assert result['crossing_zone_overlap_pairs']==[1]


def test_remove_replace_exclude_and_pending_tree_updates():
    idx=ConflictIndex()
    idx.add(1,[line((0,0),(10,0))])
    assert idx.evaluate([line((0,0),(10,0))],exclude=1)['valid']
    idx.add(2,[line((0,1),(10,1))])
    assert not idx.evaluate([line((0,1.1),(10,1.1))])['valid']
    idx.remove(2)
    assert idx.evaluate([line((0,1.1),(10,1.1))])['valid']
    idx.add(1,[line((0,2),(10,2))])
    assert idx.evaluate([line((0,.1),(10,.1))])['valid']
    assert not idx.evaluate([line((0,2.1),(10,2.1))])['valid']


def test_wrong_layer_or_arc_endpoints_fail_loudly():
    idx=ConflictIndex()
    with pytest.raises(ValueError):
        idx.prepare([dict(line((0,0),(1,1)),layer=1)])
    bad=arc((0,0),5,0,1)
    bad['p1']=(1,1)
    with pytest.raises(ValueError):
        idx.prepare([bad])


def test_smooth_joins_are_not_illegal_self_intersections():
    idx=ConflictIndex()
    path=[line((0,0),(10,0)),arc((10,5),5,-math.pi/2,math.pi/2),line((15,5),(15,20))]
    assert idx.evaluate(path)['valid']


@pytest.mark.parametrize('angle',[0.,.1,.7,math.pi/2,2.8,4.3,6.1])
def test_long_line_arc_tangent_join_numerically_stable(angle):
    direction=(math.cos(angle),math.sin(angle))
    joint=(70.,75.)
    center=(joint[0]-5*direction[1],joint[1]+5*direction[0])
    path=[line((joint[0]-10000*direction[0],joint[1]-10000*direction[1]),joint),
          arc(center,5,angle-math.pi/2,math.pi/2)]
    result=ConflictIndex().evaluate(path)
    assert result['self_intersections']==0
    assert result['self_overlaps']==0
    assert result['valid']


def test_long_line_near_tangent_is_not_false_intersection():
    a=_make_primitive(line((-100000,0),(100000,0)))
    b=_make_primitive(arc((0,5.0000001),5,math.pi,math.pi))
    points,overlap=_intersections(a,b)
    assert points==[] and not overlap
    assert _exact_distance(a,b)==pytest.approx(.0000001,abs=1e-10)
