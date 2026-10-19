"""Pin AST identity and behavior of original noCross/sn_calc bindings."""
import ast
import hashlib
from pathlib import Path
import random
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from four_side_1024.legacy_rules import (
    LEGACY_SOURCE, LegacyRules, WGyset, channel_ln_calc,
    extracted_rule_ast, nodesMTset, source_provenance,
)
import wiring_rect_826


def _nodes():
    return nodesMTset([[10*j+.175*i for i in range(32)] for j in range(3)],
                      [[10*j+.175*i for i in range(32)] for j in range(3)])


def _independent_original_namespace(nodes, callback):
    # Parse the legacy source independently of the extraction implementation.
    tree=ast.parse(LEGACY_SOURCE.read_text(encoding='utf-8'))
    parent=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='plotter_rect')
    functions=[n for n in parent.body if isinstance(n,ast.FunctionDef) and n.name in ('sn_calc','noCross')]
    namespace=dict(nodes=nodes,ln_calc=callback,r=5.,height=150.)
    exec(compile(ast.Module(body=functions,type_ignores=[]),str(LEGACY_SOURCE),'exec'),namespace)
    return functions,namespace


def test_original_source_ast_is_used_without_rewriting():
    functions,original=_independent_original_namespace(_nodes(),lambda lx,ly:16)
    rules=LegacyRules(_nodes(),lambda lx,ly:16)
    for f in functions:
        assert ast.dump(f,include_attributes=False)==ast.dump(extracted_rule_ast(f.name),include_attributes=False)
        assert rules.namespace[f.name].__code__.co_code==original[f.name].__code__.co_code
        assert rules.namespace[f.name].__code__.co_consts==original[f.name].__code__.co_consts
    assert WGyset is wiring_rect_826.WGyset
    p=source_provenance()
    assert p['source_file_sha256']==hashlib.sha256(LEGACY_SOURCE.read_bytes()).hexdigest()
    assert p['unchanged_legacy_constants']['sn_calc_fallback']==8


def test_nodes_use_all_32_channels_and_original_initial_values():
    nodes=_nodes()
    for mt in nodes.MTabove:
        assert len(mt.x)==len(mt.y)==32 and mt.x==sorted(mt.x)
        assert mt.y==[0.]*32
    for mt in nodes.MTbelow:
        assert len(mt.x)==len(mt.y)==32 and mt.y==[150.]*32
    nodes.MTabove[0].y[0]=15.
    assert nodes.MTabove[1].y[0]==0.  # no aliased mutable y lists


def test_channel_adapter_has_no_original_N_limit_or_modulo_aliasing():
    mapping={(float(i),150.):i+1 for i in range(32)}
    callback=channel_ln_calc(mapping)
    assert [callback(float(i),150.) for i in range(32)]==[max(i-6,4) for i in range(32)]
    assert callback(31.,150.)==25
    with pytest.raises(KeyError):
        callback(99.,150.)


def test_sn_calc_observes_real_32_channel_state_and_unchanged_fallback():
    nodes=_nodes(); rules=LegacyRules(nodes,lambda lx,ly:16)
    nodes.MTbelow[0].y=[float(i) for i in range(32)]
    nodes.MTabove[0].y=[150.-i for i in range(32)]
    assert rules.sn_calc(0,20.)==-20
    assert rules.sn_calc(0,130.,False)==-20
    assert rules.sn_calc(3,20.)==8
    assert rules.sn_calc(0,140.)==8


@pytest.mark.parametrize('direction',['below','above','above2below','below2above'])
def test_every_original_noCross_branch_matches_independent_source(direction):
    rng=random.Random(871)
    nodes=_nodes()
    for mt in nodes.MTbelow+nodes.MTabove:
        mt.y[:]=sorted([rng.uniform(0,150) for _ in range(32)])
    callback=lambda lx,ly:max(int(lx),4)
    rules=LegacyRules(nodes,callback)
    _,original=_independent_original_namespace(nodes,callback)
    for trial in range(100):
        tracks=[]
        for i in range(50):
            occupied=rng.random()<.6
            tracks.append(WGyset(y=5+i*.175,WGs=[i] if occupied else [],
                lEnd=[100]+([rng.randrange(3)] if occupied else []),
                rEnd=[-1]+([rng.randrange(3),rng.randrange(3)] if occupied else [])))
        args=(rng.randrange(3),rng.randrange(3),rng.randrange(50),tracks)
        kwargs=dict(_type=direction,lx=rng.randrange(4,26),ly=150.)
        assert rules.noCross(*args,**kwargs)==original['noCross'](*args,**kwargs)


def test_nodes_and_callbacks_fail_loudly_on_incomplete_channel_data():
    with pytest.raises(ValueError):
        nodesMTset([[1,2]],[[1,2]])
    with pytest.raises(ValueError):
        channel_ln_calc({(1,2):33})
    with pytest.raises(TypeError):
        LegacyRules(_nodes(),None)
