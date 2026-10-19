"""Real-CSV acceptance of the original-rule four-side adapter (bounded smoke).

The bounded route smoke evaluates at most four geometries; the full 1024-route
experiment is run by legacy_adapter itself and audited from its saved files.
"""
import ast
from collections import Counter
import copy
import csv
import hashlib
import inspect
import math
from pathlib import Path
import time

import numpy as np
import pytest

from . import legacy_adapter as adapter
from .conflicts import ConflictIndex
from .geometry import length, validate
from .inputs import DEFAULT_INPUT, config, load
from .legacy_geometry import adjacent, canonicalize, opposite, transform_primitives
from .legacy_rules import LegacyRules, WGyset, nodesMTset, source_provenance
import wiring_rect_826


@pytest.fixture(scope='module')
def real_data():
    return load(DEFAULT_INPUT,config())


def test_all_real_csv_identities_and_2048_ports_are_preserved(real_data):
    routes,endpoints,connectors,validation=real_data
    raw=Path(DEFAULT_INPUT).read_bytes()
    original=list(csv.DictReader(raw.decode('utf-8-sig').splitlines()))
    assert len(original)==len(routes)==1024
    assert len(endpoints)==2048 and len(connectors)==64
    assert validation['csv_sha256']==hashlib.sha256(raw).hexdigest()
    assert validation['passed'] and validation['endpoints_used_once']
    usage=Counter()
    for source,route in zip(original,routes):
        for key,value in source.items():
            assert str(route[key])==value
        for role in ('source','target'):
            endpoint=endpoints[route[role+'_endpoint']]
            usage[endpoint['endpoint_id']]+=1
            assert endpoint['connector']==route[role+'_connector']
            assert endpoint['row']==route[role+'_row']
            assert endpoint['column']==route[role+'_column']
            assert endpoint['channel']==route[role+'_channel']
            assert endpoint['side']==route[role+'_side']
            assert endpoint['layer']==0
        assert route['source_side']!=route['target_side']
    assert set(usage)==set(endpoints) and set(usage.values())=={1}
    assert set(Counter(e['connector'] for e in endpoints.values()).values())=={32}
    assert Counter(r['relation'] for r in routes)=={'opposite':512,'adjacent':512}


def test_every_real_endpoint_survives_all_ordered_side_transforms(real_data):
    _,endpoints,_,_=real_data
    inward={'S':np.array([0.,1.]),'N':np.array([0.,-1.]),
            'E':np.array([-1.,0.]),'W':np.array([1.,0.])}
    sample_targets={side:next(e for e in endpoints.values() if e['side']==side)
                    for side in inward}
    seen=set()
    for endpoint in endpoints.values():
        ss=endpoint['side']; p=np.array(endpoint['routing_xy'])
        for ts,target in sample_targets.items():
            if ss==ts:
                continue
            pc,qc,transform,kind=canonicalize(ss,ts,p,target['routing_xy'])
            matrix=np.array(transform['matrix']);offset=np.array(transform['offset'])
            np.testing.assert_allclose(matrix.T@(pc-offset),p,atol=1e-12,rtol=0)
            np.testing.assert_allclose(matrix.T@(qc-offset),target['routing_xy'],atol=1e-12,rtol=0)
            np.testing.assert_allclose(matrix@inward[ss],[0,1],atol=1e-12,rtol=0)
            np.testing.assert_allclose(matrix@inward[ts],[0,-1] if kind=='opposite' else [-1,0],atol=1e-12,rtol=0)
            assert abs(pc[1])<1e-12
            assert abs(qc[1]-150)<1e-12 if kind=='opposite' else abs(qc[0]-150)<1e-12
            seen.add((ss,ts))
    assert len(seen)==12


@pytest.mark.parametrize('pair',adapter.GROUP_ORDER)
def test_six_side_pair_geometries_use_real_fixed_ports(real_data,pair):
    routes,endpoints,_,_=real_data
    checked=None
    for route in (r for r in routes if r['pair']==pair):
        src=endpoints[route['source_endpoint']]; dst=endpoints[route['target_endpoint']]
        p,q,transform,kind=canonicalize(src['side'],dst['side'],src['routing_xy'],dst['routing_xy'])
        track=75. if kind=='opposite' else q[1]
        try:
            local=(opposite if kind=='opposite' else adjacent)(p,q,track,radius=5.,width=.05)
        except ValueError:
            continue
        world=transform_primitives(local,transform,inverse=True)
        assert validate(world,src['routing_xy'],dst['routing_xy'],src['inward'],
                        -np.array(dst['inward']),board=150.,width=.05,min_radius=5.)==[]
        assert math.dist(world[0]['p0'],src['routing_xy'])<1e-12
        assert math.dist(world[-1]['p1'],dst['routing_xy'])<1e-12
        assert all(p['layer']==0 for p in world)
        assert all(p['radius']>=5. for p in world if p['kind']=='arc')
        assert length(world)==pytest.approx(length(local),abs=1e-10)
        checked=route['route_id']; break
    assert checked is not None,f'No genuine CSV fixture fits the necessary adapter for {pair}'


def test_entrypoint_calls_only_legacy_track_rules_and_one_shared_collision_index():
    tree=ast.parse(inspect.getsource(adapter))
    forbidden={'router','dubins','candidates','route_all','ripup','reroute','score','scoring'}
    calls=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.ImportFrom):
            assert (node.module or '').split('.')[-1] not in forbidden
            assert not any(alias.name.lower() in forbidden for alias in node.names)
        if isinstance(node,ast.Import):
            assert not any(alias.name.split('.')[-1].lower() in forbidden for alias in node.names)
        if isinstance(node,ast.Call):
            name=node.func.id if isinstance(node.func,ast.Name) else node.func.attr if isinstance(node.func,ast.Attribute) else ''
            assert name.lower() not in forbidden
            calls.append(node)
    route_func=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='route_original')
    group_loop=next(node for node in route_func.body if isinstance(node,ast.For))
    constructors=[node for node in ast.walk(route_func) if isinstance(node,ast.Call)
                  and isinstance(node.func,ast.Name) and node.func.id=='ConflictIndex']
    assert len(constructors)==1 and constructors[0].lineno<group_loop.lineno
    no_cross=[node for node in calls if isinstance(node.func,ast.Attribute) and node.func.attr=='noCross']
    assert len(no_cross)==1 and isinstance(no_cross[0].func.value,ast.Name) and no_cross[0].func.value.id=='rules'
    collision_calls=[node for node in calls if isinstance(node.func,ast.Attribute) and node.func.attr in ('evaluate','add')]
    assert {node.func.attr for node in collision_calls}=={'evaluate','add'}
    assert all(isinstance(node.func.value,ast.Name) and node.func.value.id=='shared' for node in collision_calls)
    assert adapter.ConflictIndex is ConflictIndex
    assert adapter.WGyset is WGyset is wiring_rect_826.WGyset
    assert adapter.LegacyRules is LegacyRules


def test_bound_rules_retain_original_source_ast_at_runtime():
    nodes=nodesMTset([[i*.175 for i in range(32)]],[[i*.175 for i in range(32)]])
    rules=LegacyRules(nodes,lambda x,y:4)
    source=source_provenance()
    assert rules.noCross.__code__.co_filename==source['source_file']
    assert rules.noCross.__code__.co_firstlineno==source['rules']['noCross']['lineno']
    assert rules.noCross.__globals__['sn_calc'] is rules.sn_calc
    assert rules.noCross.__globals__['nodes'] is nodes
    assert rules.provenance['source_file_sha256']==hashlib.sha256(Path(source['source_file']).read_bytes()).hexdigest()


def test_row_groups_share_real_layer_zero_clearance_check():
    shared=ConflictIndex(width=.05,gap=.125)
    shared.add('row1:opposite',[dict(kind='line',p0=[10.,20.],p1=[100.,20.],layer=0)])
    result=shared.evaluate([dict(kind='line',p0=[20.,20.1],p1=[90.,20.1],layer=0)])
    assert not result['valid'] and result['spacing_pairs']==['row1:opposite']
    crossing=shared.evaluate([dict(kind='line',p0=[50.,10.],p1=[50.,30.],layer=0)])
    assert crossing['valid'] and len(crossing['crossings'])==1
    assert crossing['crossings'][0]['angle_deg']==pytest.approx(90.)


def test_bounded_original_route_smoke_preserves_every_identity(real_data):
    routes,endpoints,_,_=real_data
    before_routes=copy.deepcopy(routes); before_endpoints=copy.deepcopy(endpoints)
    cfg=config(); cfg.update(search_seconds=1.,candidate_evaluation_budget=4)
    start=time.perf_counter()
    accepted,failed,search=adapter.route_original(routes,endpoints,cfg,lambda message:None)
    assert time.perf_counter()-start<10.
    assert set(accepted).isdisjoint(failed)
    assert set(accepted)|set(failed)==set(range(1,1025))
    assert search['candidate_evaluations']<=4
    assert search['strategy_count']==1 and search['algorithm']=='legacy_AutoRouter_first_free_noCross_four_side_adapter'
    assert len(search['groups'])==6
    assert sum(v['attempted'] for v in search['groups'])==1024
    assert routes==before_routes and endpoints==before_endpoints
    lookup={r['route_id']:r for r in routes}
    audit=ConflictIndex(width=.05,gap=.125,sagitta=.0005)
    for rid,record in accepted.items():
        route=lookup[rid]; src=endpoints[route['source_endpoint']]; dst=endpoints[route['target_endpoint']]
        assert record['layer']==0
        assert record['source_endpoint']==route['source_endpoint'] and record['target_endpoint']==route['target_endpoint']
        assert validate(record['primitives'],src['routing_xy'],dst['routing_xy'],src['inward'],
                        -np.array(dst['inward']),board=150.,width=.05,min_radius=5.)==[]
        assert audit.evaluate(record['primitives'],stop_on_invalid=False)['valid']
        audit.add(rid,record['primitives'])
