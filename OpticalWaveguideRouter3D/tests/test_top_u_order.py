"""Single-variable top-U ordering experiment tests."""
from copy import deepcopy
from dataclasses import replace
from unittest import TestCase
from src.models import Point2D,Port,Waveguide
from src.router_2d import TrackPolicyConfig,prepare_waveguides_2d,assign_tracks_2d,generate_assigned_routes_2d
from src.collision import find_route_intersections
raises=TestCase().assertRaises

def wg(i,x1,y1,x2,y2,pmt=1):
 return Waveguide(i,Port(i*2,pmt,None,Point2D(x1,y1)),Port(i*2+1,pmt+100,None,Point2D(x2,y2)))
def fixture():
 return [wg(1,0,150,40,150),wg(2,10,150,30,150),wg(3,0,0,40,0),
         wg(4,0,150,40,0),wg(5,0,0,40,150),wg(6,0,150,4,0)]
def run(ws=None,option=None):
 ws=fixture() if ws is None else ws
 config=TrackPolicyConfig(150,.05,.125,5)
 if option is not None:config=replace(config,top_u_primary_order=option)
 p=prepare_waveguides_2d(ws,150,0)
 return assign_tracks_2d(ws,p,config)
def test_order_default_baseline():
 a=run()
 assert a==run(option="ascending")
 assert a[0].track_index==799 and a[1].track_index==798
def test_order_variant_primary_only():
 a=run(option="descending")
 assert a[0].track_index==798 and a[1].track_index==799
def test_order_ties_unchanged():
 ws=[wg(9,0,150,30,150,2),wg(8,0,150,20,150,3),
     wg(7,0,150,20,150,2),wg(6,0,150,20,150,2)]
 a=run(ws);b=run(ws,"descending")
 assert a==b
 assert [r.waveguide_id for r in sorted(a,key=lambda r:-r.track_index)]==[6,7,8,9]
def test_order_bottom_unchanged():
 assert run()[2]==run(option="descending")[2]
def test_order_z_unchanged():
 assert run()[3:5]==run(option="descending")[3:5]
def test_order_special_unchanged():
 assert run()[-1]==run(option="descending")[-1]
 assert run()[-1].status=="unsupported_geometry"
def test_order_top_assigned_set():
 assert {a.waveguide_id for a in run()[:2]}=={a.waveguide_id for a in run(option="descending")[:2]}
def test_order_top_track_set():
 assert {a.track_index for a in run()[:2]}=={a.track_index for a in run(option="descending")[:2]}
def test_order_nested_comparison():
 ws=fixture()[:2];p=prepare_waveguides_2d(ws,150,0)
 counts=[]
 for option in ("ascending","descending"):
  a=run(ws,option)
  routes=generate_assigned_routes_2d(ws,p,a,top_y=150,bottom_y=0)
  counts.append(sum(e.kind=="cross" for e in find_route_intersections(*routes)))
 assert counts==[2,0]
def test_order_no_mutation():
 ws=fixture();before=deepcopy(ws);control=run(ws);saved=deepcopy(control)
 run(ws,"descending")
 assert ws==before and control==saved
def test_order_invalid():
 with raises(ValueError):run(option="reverse_everything")
def test_order_deterministic():
 ws=fixture()
 assert run(ws,"descending")==run(ws,"descending")
 assert {a.waveguide_id:a for a in run(ws,"descending")}=={a.waveguide_id:a for a in run(list(reversed(ws)),"descending")}
