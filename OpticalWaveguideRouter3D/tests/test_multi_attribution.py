"""Hand-computable geometry tests for post-hoc attribution only."""
from copy import deepcopy
from math import pi, sqrt
from unittest import TestCase
from src.models import Point2D as P, Port, Waveguide, LineSegment2D as L, ArcSegment2D as A, SmoothedRoute2D as R
from src.multi_attribution import (
    line_orientation, physical_endpoints, geometric_pmt_order, neighbor_relation,
    chain_ownership, primitive_attribution, primitive_description, topology_signature,
    pair_token, arc_vertical_relations, classify_paper_like, deserialize_plot,
)
from src.physical_intersections import find_physical_route_intersections_2d
from src.multi_crossing import build_crossing_pair_map, classify_multi_crossing


def u(rid=1,x=0,width=4,y=0,r=1):
    return R(rid,[L(P(x,3),P(x,y+r)),A(P(x,y+r),P(x+r,y),P(x+r,y+r),pi/2),
                  L(P(x+r,y),P(x+width-r,y)),
                  A(P(x+width-r,y),P(x+width,y+r),P(x+width-r,y+r),pi/2),
                  L(P(x+width,y+r),P(x+width,3))])


def wg(route,pa=10,pb=30):
    return Waveguide(route.waveguide_id,
        Port(route.waveguide_id*2,pa,None,route.segments[0].start),
        Port(route.waveguide_id*2+1,pb,None,route.segments[-1].end))


def owners(route,pa=10,pb=30):
    ends=physical_endpoints(wg(route,pa,pb),top_y=3,bottom_y=-3)
    return chain_ownership(route,ends)


def crossing(a,b,point,orders=None):
    oa,ob=owners(a),owners(b,20,40)
    ps=point if isinstance(point,P) else P(*point)
    ma=primitive_attribution(a,ps,[],oa)
    mb=primitive_attribution(b,ps,[],ob)
    result=dict(route_a=a.waveguide_id,route_b=b.waveguide_id,
                x=ps.x,y=ps.y,primitive_a=ma,primitive_b=mb)
    result["neighbor_relations"]=arc_vertical_relations(result,orders or {"TOP":[10,20,30,40],"BOTTOM":[]})
    return result


def paper_fixture():
    a=u()
    b=u(2,.4,7.6,-2,.1)
    c=R(3,[L(P(-1,.25),P(3,.25))])
    routes={r.waveguide_id:r for r in (a,b,c)}
    events=[]
    crosses=[]
    for first,second in ((a,b),(a,c),(b,c)):
        found=find_physical_route_intersections_2d(first,second)
        assert len(found)==1 and found[0].kind=="cross"
        events+=found
        crosses.append(crossing(first,second,found[0].point))
    verdict=classify_multi_crossing((1,2,3),build_crossing_pair_map(events))
    assert verdict.classification=="multi_waveguide_crossing"
    return routes,crosses


def test_line_horizontal():
    assert line_orientation(L(P(2,1),P(-3,1)))=="HORIZONTAL"


def test_line_vertical():
    assert line_orientation(L(P(2,1),P(2,-3)))=="VERTICAL"


def test_line_other_and_degenerate():
    assert line_orientation(L(P(0,0),P(1,1)))=="OTHER"
    assert line_orientation(L(P(0,0),P(0,0)))=="OTHER"


def test_physical_left_right_not_input_order():
    route=u()
    w=wg(route)
    reversed_w=Waveguide(w.id,w.end_port,w.start_port)
    ends=physical_endpoints(reversed_w,3,-3)
    assert [p["physical_end"] for p in ends]==["RIGHT","LEFT"]


def test_physical_top_bottom_and_same_x():
    w=Waveguide(1,Port(1,99,None,P(2,150)),Port(2,5,None,P(2,0)))
    ends=physical_endpoints(w)
    assert [p["side"] for p in ends]==["TOP","BOTTOM"]
    assert all(p["physical_end"]=="SAME_X" for p in ends)


def test_arc_owner_by_chain():
    route=u();o=owners(route)
    assert o[1][0]["physical_end"]=="LEFT"
    assert o[3][0]["physical_end"]=="RIGHT"
    assert 2 not in o


def test_arc_chain_storage_permutation():
    route=u(); original=owners(route)
    perm=[3,0,4,2,1]
    changed=R(1,[route.segments[i] for i in perm])
    ends=physical_endpoints(wg(route),3,-3)
    rearranged=chain_ownership(changed,ends)
    for new,old in enumerate(perm):
        assert rearranged.get(new,[])==original.get(old,[])


def test_reversed_chain_and_input_direction():
    route=u()
    reverse=R(1,[L(s.end,s.start) if isinstance(s,L) else A(s.end,s.start,s.center,-s.sweep_rad)
                 for s in reversed(route.segments)])
    ends=physical_endpoints(Waveguide(1,wg(route).end_port,wg(route).start_port),3,-3)
    own=chain_ownership(reverse,ends)
    assert own[1][0]["physical_end"]=="RIGHT" and own[3][0]["physical_end"]=="LEFT"


def test_disconnected_chain_rejected():
    route=u();route.segments[2]=L(P(100,0),P(101,0))
    with TestCase().assertRaises(ValueError): owners(route)


def test_arc_details():
    route=u();p=primitive_description(route,1,owners(route))
    assert p["type"]=="ARC" and p["center"]==dict(x=1,y=1)
    assert p["radius"]==1 and p["sweep_rad"]==pi/2
    assert p["endpoint_owner"]["pmt_id"]==10


def test_primitive_attribution_arc_point():
    route=u()
    result=primitive_attribution(route,P(.4,.2),[1],owners(route))
    assert len(result)==1 and result[0]["segment_index"]==1


def test_primitive_attribution_keeps_join_membership():
    route=u()
    result=primitive_attribution(route,P(1,0),[1],owners(route))
    assert [p["type"] for p in result]==["ARC","LINE"]


def test_primitive_wrong_saved_index_rejected():
    route=u()
    with TestCase().assertRaises(ValueError):
        primitive_attribution(route,P(.4,.2),[3],owners(route))


def test_hv_av_multi_fixture():
    _,crosses=paper_fixture()
    assert sorted(pair_token(c) for c in crosses)==[
        "ARC x HORIZONTAL","ARC x VERTICAL","HORIZONTAL x VERTICAL"]


def test_arc_arc_primitive_attribution():
    a=u()
    b=u(2,3.6)
    record=crossing(a,b,P(3.8,.4))
    assert pair_token(record)=="ARC x ARC"
    assert record["primitive_a"][0]["endpoint_owner"]["physical_end"]=="RIGHT"
    assert record["primitive_b"][0]["endpoint_owner"]["physical_end"]=="LEFT"


def test_multi_with_arc_arc():
    a=u();b=u(2,3.6);carrier=u(3,3.79,8,-2,.1)
    events=[]
    for x,y in ((a,b),(a,carrier),(b,carrier)):
        found=find_physical_route_intersections_2d(x,y)
        assert len(found)==1 and found[0].kind=="cross"
        events+=found
    assert classify_multi_crossing((1,2,3),build_crossing_pair_map(events)).classification=="multi_waveguide_crossing"


def test_pmt_neighbor_uses_geometry_not_ids():
    ws=[Waveguide(1,Port(1,900,None,P(1,150)),Port(2,100,None,P(1,0))),
        Waveguide(2,Port(3,7,None,P(3,150)),Port(4,500,None,P(3,0))),
        Waveguide(3,Port(5,1,None,P(5,150)),Port(6,2,None,P(5,0)))]
    orders=geometric_pmt_order(ws)
    assert orders["TOP"]==[900,7,1]
    assert neighbor_relation(7,900,orders)=="LEFT_GEOMETRIC_NEIGHBOR"
    assert neighbor_relation(7,1,orders)=="RIGHT_GEOMETRIC_NEIGHBOR"
    assert neighbor_relation(900,1,orders)=="NON_ADJACENT"
    assert neighbor_relation(7,7,orders)=="SAME_PMT"


def test_opposite_side_not_geometric_neighbor():
    assert neighbor_relation(1,2,{"TOP":[1],"BOTTOM":[2]})=="NON_ADJACENT"


def test_unknown_pmt_ambiguous():
    assert neighbor_relation(99,2,{"TOP":[1,2]})=="AMBIGUOUS"


def test_paper_like_real_synthetic():
    _,crosses=paper_fixture()
    assert classify_paper_like(crosses)["label"]=="PAPER_LIKE_LOCAL_MULTI"


def test_nonpaper_nonadjacent():
    _,crosses=paper_fixture()
    for c in crosses:
        c["neighbor_relations"]=arc_vertical_relations(c,{"TOP":[10,99,20,30,40]})
    assert classify_paper_like(crosses)["label"]=="NON_PAPER_LIKE"


def test_nonpaper_no_vertical_carrier():
    _,crosses=paper_fixture()
    for c in crosses:
        for key in ("primitive_a","primitive_b"):
            for p in c[key]:
                if p["orientation"]=="VERTICAL": p["orientation"]="HORIZONTAL"
    assert classify_paper_like(crosses)["reason"]=="NO_TWO_CROSS_VERTICAL_CARRIER"


def test_paper_join_ambiguous():
    _,crosses=paper_fixture()
    crosses[0]["primitive_a"].append(deepcopy(crosses[0]["primitive_a"][0]))
    assert classify_paper_like(crosses)["label"]=="PAPER_LIKE_AMBIGUOUS"


def test_signature_deterministic_pair_order_swap():
    _,crosses=paper_fixture()
    first=topology_signature(crosses)
    changed=deepcopy(list(reversed(crosses)))
    for c in changed:
        c["primitive_a"],c["primitive_b"]=c["primitive_b"],c["primitive_a"]
        c["route_a"],c["route_b"]=c["route_b"],c["route_a"]
    assert topology_signature(changed)==first


def test_special_two_arc_chain_ownership():
    from src.geometry import build_special_z_smoothed_route_2d
    route=build_special_z_smoothed_route_2d(1,P(0,0),P(4,150),5)
    w=wg(route)
    o=chain_ownership(route,physical_endpoints(w))
    arcs=[i for i,s in enumerate(route.segments) if isinstance(s,A)]
    assert len(arcs)==2
    assert {o[i][0]["physical_end"] for i in arcs}=={"LEFT","RIGHT"}


def test_readonly_invariant():
    route=u();ends=physical_endpoints(wg(route),3,-3)
    before=deepcopy((route,ends))
    o=chain_ownership(route,ends)
    result=primitive_attribution(route,P(.4,.2),[1],o)
    result[0]["endpoint_owner"]["x"]=999
    assert (route,ends)==before


def test_deserialize_analytic_arc_not_polyline():
    record=dict(id=1,segments=[dict(kind="arc",cx=1,cy=1,r=1,start_deg=180,sweep_deg=90)])
    before=deepcopy(record);r=deserialize_plot(record)
    assert isinstance(r.segments[0],A) and record==before


def test_single_arc_two_endpoint_owners_stay_ambiguous():
    r=R(1,[A(P(0,1),P(1,0),P(1,1),pi/2)])
    o=chain_ownership(r,physical_endpoints(wg(r),top_y=1,bottom_y=0))
    assert primitive_description(r,0,o)["ownership_status"]=="AMBIGUOUS"


def test_outside_eligible_not_paperlike():
    _,c=paper_fixture()
    assert classify_paper_like(c,legacy_eligible=False)["label"]=="NON_PAPER_LIKE"
