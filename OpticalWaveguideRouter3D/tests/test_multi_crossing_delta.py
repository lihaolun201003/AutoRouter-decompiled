"""Differential audit helpers; no routing changes."""
from copy import deepcopy
from unittest import TestCase
from src.multi_crossing_delta import *
from src.multi_crossing import triplet_composition
raises=TestCase().assertRaises
def record(sides):
 return dict(side_lengths_mm=sides,short_side_count=2,crossing_angles_deg=[10,40,80])
def test_delta_canonical():
 assert canonical_triplet((3,1,2))==(1,2,3)
def test_delta_sets():
 d=triplet_set_diff([(1,2,3),(2,3,4)],[(3,2,1),(3,4,5)])
 assert d==dict(stable=[(1,2,3)],removed=[(2,3,4)],added=[(3,4,5)])
def test_delta_identities():
 d=triplet_set_diff([(1,2,3)],[(1,2,3),(2,3,4)])
 assert len(d["stable"])+len(d["removed"])==1
 assert len(d["stable"])+len(d["added"])==2
def test_delta_second_side():
 assert severity(record([.3,.1,.2]))["s2"]==.2
def test_delta_margin():
 assert abs(severity(record([.01,.1,.2]))["second_shortest_margin_mm"]-.025)<1e-12
def test_delta_severity_order():
 rs=[record([.01,.12,.2]),record([.01,.03,.2])]
 assert max(rs,key=lambda r:severity(r)["second_shortest_margin_mm"])==rs[1]
def test_delta_stable_change():
 assert margin_delta(record([.01,.1,.2]),record([.01,.05,.2]))["change"]=="worsened"
 assert margin_delta(record([.01,.05,.2]),record([.01,.1,.2]))["change"]=="improved"
 assert margin_delta(record([.01,.05,.2]),record([.01,.05+1e-10,.2]))["change"]=="unchanged"
def test_delta_no_top_invariant():
 assert check_top_u_invariant(dict(added=[(1,2,3)],removed=[]),{1})
 with raises(ValueError):check_top_u_invariant(dict(added=[(1,2,3)],removed=[]),{4})
def test_delta_composition():
 assert triplet_composition((1,2,3),{3})=="ordinary/ordinary/special"
def test_delta_graph_set_difference():
 d=triplet_set_diff([(0,1,2),(0,1,3)],[(0,1,3)])
 assert d["removed"]==[(0,1,2)]
def test_delta_eligible_equal_count_not_equal_set():
 d=triplet_set_diff([(0,1,2)],[(0,1,3)])
 assert len(d["removed"])==len(d["added"])==1 and not d["stable"]
def test_delta_angles():
 s=summarize_records([record([.01,.02,.03])])
 assert s["contains_angle_below_20"]==1 and s["minimum_angle_per_triplet"]["mean"]==10
def test_delta_no_mutation_determinism():
 rs=[record([.01,.02,.03])];saved=deepcopy(rs)
 assert summarize_records(rs)==summarize_records(rs)
 assert rs==saved
