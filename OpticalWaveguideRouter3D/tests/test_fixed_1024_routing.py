import json
from pathlib import Path
from copy import deepcopy
from functools import lru_cache
from collections import Counter
from src.fixed_1024_routing import (legacy_waveguides_from_seed,generate_fixed_1024_input,
    validate_fixed_1024_input,build_fixed_1024_geometry,serialize_route3d,deserialize_route3d,
    fixed_three_layer_config,run_fixed_1024_assignment)
from src.layer_assignment_3d import elevation_candidates
from src.models import Point3D
from src.sequential_elevation_3d import _run_sequential_elevation

def legacy():return legacy_waveguides_from_seed(json.loads((Path(__file__).parents[1]/'data/fixed_1024_legacy_seed.json').read_text()))
def data():return generate_fixed_1024_input(legacy())
@lru_cache(maxsize=1)
def geometry():return build_fixed_1024_geometry(data())

def test_exactly_1024_unique_ids():
    rows=data()['routes'];assert len(rows)==1024 and {r['route_id'] for r in rows}==set(range(1024))
def test_2048_endpoint_uniqueness():
    ports=[p for r in data()['routes'] for p in (r['source'],r['destination'])]
    assert len({p['endpoint_id'] for p in ports})==len({tuple(p['xyz']) for p in ports})==2048
def test_deterministic_fixed_fixture():assert data()==data()
def test_fixed_board_bounds():
    d=data();assert d['board']=={'width_mm':300.,'height_mm':200.}
    assert all(0<=p['xyz'][0]<=300 and p['xyz'][1] in (0.,200.) for r in d['routes'] for p in (r['source'],r['destination']))
def test_connection_completeness():
    rows=data()['routes'];ports=[p for r in rows for p in (r['source'],r['destination'])]
    degrees=Counter(p['pmt_id'] for p in ports);assert len(degrees)==128 and set(degrees.values())=={16}
    assert len({r['source']['endpoint_id'] for r in rows})==len({r['destination']['endpoint_id'] for r in rows})==1024
    assert all(r['destination']['copy']==(r['source_copy']^(r['legacy_route_id']%2)) for r in rows)
def test_all_1024_geometry_generated():
    planar,routes,stats=geometry();assert len(planar)==1024 and stats['assignment_status_counts']=={'assigned':960,'unsupported_geometry':64}
def test_all_1024_lifted():
    _,routes,_=geometry();assert len(routes)==1024 and all(p.start.z==p.end.z==0 for r in routes.values() for p in r.primitives)
def test_three_layer_candidate_support():
    _,routes,_=geometry();r=routes[0];point=r.primitives[len(r.primitives)//2].point_at(.5)
    for layer in (1,2):
        cs,_=elevation_candidates(r,(0,1),[Point3D(point.x,point.y,0)],fixed_three_layer_config(),target_layer_id=layer)
        assert cs and all(c.layer_to==layer for c in cs)
def test_all_final_state_serialization_reload():
    _,routes,_=geometry()
    assert all(deserialize_route3d(json.loads(json.dumps(serialize_route3d(r))))==r for r in routes.values())
def test_elevated_state_reload():
    _,routes,_=geometry();r=routes[0];p=r.primitives[len(r.primitives)//2].point_at(.5)
    cs,_=elevation_candidates(r,(0,1),[p],fixed_three_layer_config(),target_layer_id=2)
    c=cs[0];assert deserialize_route3d(json.loads(json.dumps(serialize_route3d(c.route))))==c.route
def test_fixed_1024_stop_cap_validation():
    _,routes,_=geometry()
    try:_run_sequential_elevation(routes,fixed_three_layer_config(),max_targets=1025,expanded_layers=True,fixed_1024=True)
    except ValueError as e:assert 'TARGET_LIMIT' in str(e)
    else:raise AssertionError('Missing stop bound')
def test_baseline_seed_read_only():
    original=legacy();frozen=deepcopy(original);generate_fixed_1024_input(original);assert original==frozen
