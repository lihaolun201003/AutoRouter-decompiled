"""Regression tests for window_slack_mm on the fixed-target D/E diagnostic.

The 512 fixed-relocation diagnostic reuses the Step 15 start state, target list
and order, adding only window_slack_mm. These tests pin the interface contract:

* default window_slack_mm=0.0 reproduces the historical generation and the
  historical decision sequence exactly;
* a positive slack really reaches candidate generation (recorded windows equal
  the generator output at that slack) and moves each placement by exactly
  (1-2f)*delta with delta = slack/straight length: the start-anchored placement
  (f=0) moves by +delta, the middle placement (f=0.5) stays, the end-anchored
  placement (f=1) moves by -delta, and the transition run is unchanged;
* the 0.1 mm clearance criterion, the endpoint/XY/C0-C1/radius rules and the
  strict global-decrease rule stay in force (no verdict is relaxed by the slack);
* invalid slack values are rejected;
* one read-only 512 check confirms the passthrough on the real frozen input.
"""
import json
from pathlib import Path
from src.models import Layer,Point3D
from src.geometry_3d import LineSegment3D,CosineTransition3D,Route3D
from src.strategy_v2_3d import (BudgetConfig,run_fixed_target_diagnostic,xy_projection_preserved)
from src.three_layer_assignment_3d import LayerConfiguration,candidate_families


def config(n=3):
    return LayerConfiguration([Layer(i,float(i)) for i in range(n)],.1,5.,
        'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC')


def L(a,b):return LineSegment3D(Point3D(*a),Point3D(*b))


def crossing_scenario():
    """Two 60 mm straight routes crossing at (0,0). Raising route 0 clears the
    single close pair, so mode D accepts exactly one first elevation."""
    routes={0:Route3D(0,[L((-30,0,0),(30,0,0))]),1:Route3D(1,[L((0,-30,0),(0,30,0))])}
    return routes,{(0,1):[Point3D(0,0,0)]}


def run_diag(routes,planar,crossings,*,targets=((0,1),),mode='D',slack=None,budget=None):
    kwargs={} if slack is None else dict(window_slack_mm=slack)
    return run_fixed_target_diagnostic(routes,planar,config(),targets=targets,mode=mode,
        scale=len(routes),saved_crossings=crossings,
        budget=budget or BudgetConfig(len(routes),len(targets),50,True,'TEST'),**kwargs)


def strip_timings(ledger):
    return {k:v for k,v in ledger.items() if k not in
        ('runtime_seconds','initial_pair_scan_seconds','assignment_seconds')}


def victim_rows(result,step_index=0,victim_index=0):
    """Candidate rows of one victim attempt: a target attempts both routes, so a
    step holds two independent generations."""
    return result['steps'][step_index]['victim_attempts'][victim_index]['candidates']


def ordered_windows(result,layer,step_index=0,victim_index=0):
    """Distinct rise windows then distinct fall windows of one elevated layer, in
    enumeration order."""
    rises=[];falls=[]
    for row in victim_rows(result,step_index,victim_index):
        if row['target_layer_id']!=layer: continue
        for collection,key in ((rises,'rise_window'),(falls,'fall_window')):
            value=tuple(row[key])
            if value not in collection: collection.append(value)
    return rises,falls


def test_default_slack_matches_explicit_zero_and_historical_generation():
    routes,crossings=crossing_scenario()
    default=run_diag(routes,routes,crossings)
    explicit=run_diag(routes,routes,crossings,slack=0.0)
    assert default['steps']==explicit['steps']
    assert strip_timings(default['ledger'])==strip_timings(explicit['ledger'])
    assert default['final_collision_pairs']==explicit['final_collision_pairs']==[]
    # The recorded windows are exactly the slack-free enumeration of the frozen
    # planar route: the default path did not change generation.
    candidates,failures=candidate_families(routes[0],(0,1),crossings[(0,1)],config())
    assert set(failures.values())=={None}
    recorded=[(tuple(r['rise_window']),tuple(r['fall_window']),r['target_layer_id'])
        for r in victim_rows(default)]
    assert recorded==[(c.rise_window,c.fall_window,c.layer_to) for c in candidates]
    assert default['ledger']['window_slack_mm']==0.0


def test_window_shift_is_one_minus_two_f_delta_and_run_is_unchanged():
    routes,crossings=crossing_scenario()
    slack=1e-5
    base=run_diag(routes,routes,crossings,slack=0.0)
    shifted=run_diag(routes,routes,crossings,slack=slack)
    delta=slack/routes[0].primitives[0].length()
    base_rises,base_falls=ordered_windows(base,1)
    new_rises,new_falls=ordered_windows(shifted,1)
    assert len(base_rises)==len(new_rises)==3 and len(base_falls)==len(new_falls)==3
    for collection_base,collection_new in ((base_rises,new_rises),(base_falls,new_falls)):
        for index,(fraction,(bi,bu,bv),(ni,nu,nv)) in enumerate(
                zip((0.,.5,1.),collection_base,collection_new)):
            assert bi==ni
            assert abs((bv-bu)-(nv-nu))<=1e-15           # transition run unchanged
            assert abs((nu-bu)-(1-2*fraction)*delta)<=1e-15, (fraction,nu-bu)
    assert len(victim_rows(shifted))==18                   # 3 placements x 3 windows x 2 elevated layers
    layer2_rises,layer2_falls=ordered_windows(shifted,2)    # the same rule holds on layer 2
    assert len(layer2_rises)==len(layer2_falls)==3


def test_positive_slack_reaches_generation_and_is_recorded():
    routes,crossings=crossing_scenario()
    slack=1e-5
    shifted=run_diag(routes,routes,crossings,slack=slack)
    candidates,failures=candidate_families(routes[0],(0,1),crossings[(0,1)],config(),window_slack_mm=slack)
    assert set(failures.values())=={None}
    recorded=[(tuple(r['rise_window']),tuple(r['fall_window']),r['target_layer_id'])
        for r in victim_rows(shifted)]
    assert recorded[:len(candidates)]==[(c.rise_window,c.fall_window,c.layer_to) for c in candidates]
    plain,_=candidate_families(routes[0],(0,1),crossings[(0,1)],config())
    assert recorded!=[(c.rise_window,c.fall_window,c.layer_to) for c in plain]
    assert len(recorded)==len(plain)                      # no window lost in this scenario
    assert shifted['ledger']['window_slack_mm']==slack
    assert shifted['ledger']['generation_failure_cache_enabled'] is False


def test_invalid_slack_is_rejected():
    routes,crossings=crossing_scenario()
    for bad in (-1e-5,-1.0,float('inf'),float('nan'),'1e-5',None):
        try:
            run_fixed_target_diagnostic(routes,routes,config(),targets=((0,1),),mode='D',scale=2,
                saved_crossings=crossings,budget=BudgetConfig(2,1,50,True,'TEST'),window_slack_mm=bad)
        except ValueError as ex:
            assert str(ex)=='WINDOW_SLACK_MUST_BE_FINITE_AND_NONNEGATIVE',(bad,ex)
        else:
            raise AssertionError(('accepted invalid slack',bad))


def test_slack_does_not_change_acceptance_rules_or_geometry_invariants():
    routes,crossings=crossing_scenario();slack=1e-5
    base=run_diag(routes,routes,crossings,slack=0.0)
    shifted=run_diag(routes,routes,crossings,slack=slack)
    def verdicts(result):
        return [(r['basic_status'],tuple(r.get('basic_reasons') or []),r['status'],
                 tuple(r.get('full_reasons') or [])) for r in victim_rows(result)]
    assert verdicts(base)==verdicts(shifted)
    assert base['steps'][0]['status']==shifted['steps'][0]['status']=='ELEVATED'
    assert base['ledger']['accepted_moves']==shifted['ledger']['accepted_moves']==1
    assert base['ledger']['final_collision_pair_count']==shifted['ledger']['final_collision_pair_count']==0
    moved=shifted['steps'][0]['moved_route_id']
    route=shifted['routes'][moved]
    assert sum(isinstance(p,CosineTransition3D) for p in route.primitives)==2   # replaced, not stacked
    assert route.start_point==routes[moved].start_point and route.end_point==routes[moved].end_point
    ok,reason=xy_projection_preserved(route,routes[moved])
    assert ok,reason
    for p in route.primitives:
        if isinstance(p,CosineTransition3D):
            assert p.minimum_curvature_radius()>=config().required_radius_mm


def test_mode_d_skips_elevated_victims_and_mode_e_relocates_from_planar_route():
    routes,crossings=crossing_scenario()
    family,_=candidate_families(routes[0],(0,1),crossings[(0,1)],config())
    family1,_=candidate_families(routes[1],(0,1),crossings[(0,1)],config())
    # Both routes already elevated to the same layer, so they still collide at
    # z=1: mode D has no movable route, mode E may rebuild a replacement.
    start={0:family[0].route,1:family1[0].route}
    budget=BudgetConfig(2,1,50,True,'TEST')
    result_d=run_diag(start,routes,crossings,mode='D',slack=1e-5,budget=budget)
    assert result_d['steps'][0]['status']=='NO_MOVABLE_ROUTE'
    assert all(va['status']=='ROUTE_ALREADY_ELEVATED_NOT_ALLOWED_IN_D'
        for va in result_d['steps'][0]['victim_attempts'])
    assert result_d['ledger']['relocation_victim_attempts']==0
    assert result_d['ledger']['candidate_evaluations']==0
    result_e=run_diag(start,routes,crossings,mode='E',slack=1e-5,budget=budget)
    attempts=result_e['steps'][0]['victim_attempts']
    assert result_e['ledger']['relocation_victim_attempts']==2
    assert all(va['generated_count']==len(family) for va in attempts)
    assert all(va['generator_route_source']=='FROZEN_PLANAR_LAYER_ZERO' for va in attempts)
    # The rebuilt candidate comes from the frozen planar route, never from the
    # current elevated route: 2 transitions, not 4.
    for route in result_e['routes'].values():
        assert sum(isinstance(p,CosineTransition3D) for p in route.primitives)==2
    assert all(p.start.z==p.end.z for route in result_e['routes'].values()
        for p in route.primitives if not isinstance(p,CosineTransition3D))


def test_real_512_passthrough_is_read_only_and_matches_generator():
    """Read-only 512 check on the real frozen input: three fixed targets from the
    Step 15 re-run list, run with the same slack as the extended diagnostic."""
    root=Path(__file__).parents[1]
    from src.multi_attribution import deserialize_plot
    from src.geometry_3d import lift_smoothed_route_to_layer
    from src.fixed_1024_routing import deserialize_route3d
    plot=json.loads((root/'outputs/step_8_5_legacy_512_plot_geometry.json').read_text())
    planar={r['id']:lift_smoothed_route_to_layer(deserialize_plot(r),Layer(0,0)) for r in plot['routes']}
    crossings={}
    for text in (root/'outputs/step_8_5_legacy_512_physical_events.jsonl').read_text().splitlines():
        e=json.loads(text)
        if e['kind']=='cross':
            crossings.setdefault(tuple(sorted((e['route_a_id'],e['route_b_id']))),[]).append(
                Point3D(e['point']['x'],e['point']['y'],0))
    start={row['route_id']:deserialize_route3d(row['geometry']) for row in json.loads(
        (root/'outputs/3d_strategy_v2/512_three_layer_abc/final_routes_B.json').read_text())['routes']}
    targets=[tuple(t) for t in json.loads((root/'outputs/3d_strategy_v2_rev2/512_de_diagnostic'
        /'target_list.json').read_text())['one_elevated'][:3]]
    slack=1e-5
    result=run_fixed_target_diagnostic(start,planar,config(),targets=targets,mode='D',scale=512,
        saved_crossings=crossings,budget=BudgetConfig(512,3,720,True,'TEST'),window_slack_mm=slack)
    assert result['ledger']['window_slack_mm']==slack
    checked=0
    for step in result['steps']:
        target=tuple(step['target_pair'])
        for va in step['victim_attempts']:
            if va.get('generated_count',0)<=0: continue
            moved=va['route_id']
            generated,_failures=candidate_families(planar[moved],target,crossings[target],config(),
                window_slack_mm=slack)
            assert generated,'generator produced no row although the run recorded candidates'
            recorded=[(tuple(r['rise_window']),tuple(r['fall_window']),r['target_layer_id'])
                for r in va['candidates']]
            assert recorded==[(c.rise_window,c.fall_window,c.layer_to) for c in generated]
            plain,_=candidate_families(planar[moved],target,crossings[target],config())
            assert recorded!=[(c.rise_window,c.fall_window,c.layer_to) for c in plain]
            assert len(plain)>=len(recorded)   # the larger pad can only remove windows, never add
            checked+=1
    assert checked>=1,'no victim generated candidates on the three fixed targets'
    # Read-only on the input: every start route object is untouched and every
    # terminal route keeps its endpoints and XY projection.
    for i,r in start.items():
        assert result['routes'][i].route_id==i
        assert result['routes'][i].start_point==r.start_point
        assert result['routes'][i].end_point==r.end_point
        ok,reason=xy_projection_preserved(result['routes'][i],planar[i])
        assert ok,reason


# ---------------------------------------------------------------------------
# Derived-statistics consistency (read-only on the saved diagnostic artifacts)
# ---------------------------------------------------------------------------
DIAG = Path(__file__).parents[1]/'outputs/3d_strategy_v3/512_relocation_slack_diagnostic'


def derived():
    return (json.loads((DIAG/'analysis.json').read_text(encoding='utf-8')),
            json.loads((DIAG/'candidate_correspondence.json').read_text(encoding='utf-8')),
            {m: json.loads((DIAG/f'ledger_{m}.json').read_text(encoding='utf-8')) for m in ('D', 'E')})


def test_derived_movement_scopes_are_explicit_and_disjoint():
    analysis, correspondence, _ = derived()
    all_scope = correspondence['scopes']['ALL_MOVEMENT_CLASSES']
    relocation_scope = correspondence['scopes']['RELOCATION_ONLY']
    # 208 rows cover both movement classes; the 70 relocation rows are a subset.
    assert all_scope['old_self_ambiguous_rows'] == 208
    assert relocation_scope['old_self_ambiguous_rows'] == 70
    assert all_scope['movement_classes_included'] == ['FIRST_ELEVATION', 'RELOCATION']
    assert relocation_scope['movement_classes_included'] == ['RELOCATION']
    assert sum(1 for e in all_scope['records'] if e['movement'] == 'RELOCATION') == 70
    assert all(e['movement'] == 'RELOCATION' for e in relocation_scope['records'])
    assert 'ALL movement classes' in all_scope['scope']
    assert 'RELOCATION candidates only' in relocation_scope['scope']
    assert correspondence['scope_summary'] == {'all_movement_classes_rows': 208,
                                              'relocation_only_rows': 70}
    # the analysis record keeps the same two scopes under stable key names
    assert analysis['correspondence_all_movement_classes']['old_self_ambiguous_rows'] == 208
    assert analysis['correspondence_relocation_candidates']['old_self_ambiguous_rows'] == 70


def test_derived_window_shift_units_are_consistent():
    _, correspondence, _ = derived()
    checked = 0; moved = 0
    for scope in correspondence['scopes'].values():
        for entry in scope['records']:
            if entry.get('match') != 'MATCHED': continue
            lengths = (entry['shift_conversion']['rise_primitive_length_mm'],
                       entry['shift_conversion']['fall_primitive_length_mm'])
            for mm, param, length in zip(entry['start_shift_mm'], entry['start_shift_param'], lengths):
                assert abs(mm - param*length) <= 1e-15
                assert 0.0 <= abs(mm) <= 2*correspondence['window_slack_mm'] + 1e-12
                if abs(mm) > 0: moved += 1
            checked += 1
    assert checked == 148 + 10          # all-scope matches + relocation-scope matches
    # f=0.5 (middle) placements do not move; the anchored placements move by +-delta
    assert moved > 0
    validations = derived()[0]['validations']
    assert validations['unit_conversion_all']['violations'] == 0
    assert validations['unit_conversion_all']['within_bound'] is True
    assert validations['unit_conversion_relocation']['violations'] == 0
    assert validations['verdict'] == 'PASS'


def test_derived_target_level_evaluations_are_deltas_not_cumulative():
    analysis, _, ledgers = derived()
    for label, mode in (('new_D', 'D'), ('new_E', 'E')):
        check = analysis['per_target_evaluations'][label]
        assert check['verdict'] == 'PASS'
        assert check['sum_of_per_target_evaluations'] == check['sum_of_recorded_candidate_rows']
        assert check['sum_of_per_target_evaluations'] == check['ledger_candidate_evaluations']
        assert check['sum_of_per_target_evaluations'] == ledgers[mode]['candidate_evaluations']
        assert check['every_target_matches_its_rows'] is True
        assert check['sum_of_per_target_evaluations'] == check['expected_total']
    assert analysis['per_target_evaluations']['new_D']['expected_total'] == 324
    assert analysis['per_target_evaluations']['new_E']['expected_total'] == 342
    # the CSV records the per-target delta, never the cumulative counter
    rows = (DIAG/'target_outcomes.csv').read_text(encoding='utf-8-sig').splitlines()
    assert 'new_D_evaluations' in rows[0] and 'new_D_evaluations_after_cumulative' not in rows[0]
    per_target = {tuple(r['target']): r for r in analysis['target_outcomes']}
    assert sum(r['new_E_evaluations'] for r in per_target.values()) == 342
    assert max(r['new_D_evaluations'] for r in per_target.values()) < 324


def test_derived_match_uniqueness_is_checked_not_assumed():
    analysis, correspondence, _ = derived()
    for scope in correspondence['scopes'].values():
        for entry in scope['records']:
            if entry.get('match') == 'MATCHED':
                assert entry['match_count'] == 1
            if entry.get('match') == 'AMBIGUOUS_MULTIPLE_MATCHES':
                assert entry['match_count'] > 1
        counted = (scope['matched'] + sum(scope['unmatched'].values()))
        assert counted == scope['old_self_ambiguous_rows']
    assert analysis['validations']['match_uniqueness']['every_matched_has_exactly_one_match'] is True


def test_derived_benefit_decomposition_and_length_consistency():
    analysis, _, ledgers = derived()
    benefit = analysis['benefit_decomposition']
    assert benefit['relocation_removed_pairs_directly'] == 26
    assert [x['route_id'] for x in benefit['first_elevations_with_one_fewer_new_pair']] == [0, 1, 13]
    assert benefit['pairs_saved_by_those_first_elevations'] == 3
    assert benefit['final_pair_difference_D_minus_E'] == 29
    assert benefit['decomposition_holds'] is True
    assert (benefit['relocation_removed_pairs_directly']
            + benefit['pairs_saved_by_those_first_elevations']) == benefit['final_pair_difference_D_minus_E']
    length = analysis['length_consistency']
    assert length['agree_within_1e_9'] is True
    assert abs(length['relocation_step_delta_mm'] - length['final_extra_length_difference_mm']) < 1e-9
    assert abs(length['relocation_step_delta_mm'] - 0.43422826896971856) < 1e-12
    assert abs((ledgers['E']['final_extra_length_vs_planar_mm']
                - ledgers['D']['final_extra_length_vs_planar_mm'])
               - length['relocation_step_delta_mm']) < 1e-9


def test_derived_acceptance_counts_are_candidates_not_executed_edits():
    """148 matched rows -> 143 pass basic -> 139 pass full acceptance, 4 rejected there.
    Passing acceptance is not execution: the two diagnostics executed 17 edits (D 8, E 9)."""
    analysis, correspondence, ledgers = derived()
    all_scope = correspondence['scopes']['ALL_MOVEMENT_CLASSES']
    reloc_scope = correspondence['scopes']['RELOCATION_ONLY']
    assert all_scope['matched'] == 148
    assert all_scope['matched_to_basic_pass'] == 143
    assert all_scope['matched_to_full_acceptance'] == 139
    assert all_scope['matched_full_rejected'] == 4
    assert all_scope['matched_full_reject_reasons'] == {'NO_STRICT_GLOBAL_DECREASE': 4}
    assert reloc_scope['matched'] == 10
    assert reloc_scope['matched_to_basic_pass'] == 5
    assert reloc_scope['matched_to_full_acceptance'] == 1
    assert reloc_scope['matched_full_rejected'] == 4
    # consistent with the per-row records
    matched_rows = [e for e in all_scope['records'] if e.get('match') == 'MATCHED']
    assert sum(1 for e in matched_rows if e['new_basic_status'] == 'ACCEPTED_TARGET_PAIR_ONLY') == 143
    assert sum(1 for e in matched_rows if e.get('new_full_status') == 'ACCEPTED_FULL') == 139
    assert sum(1 for e in matched_rows if e.get('new_full_status') == 'REJECTED_FULL') == 4
    # executed edits come from the ledgers, not from the acceptance counts
    counts = analysis['accepted_edit_counts']
    assert (counts['new_D'], counts['new_E'], counts['total']) == (8, 9, 17)
    assert counts['new_E_relocations'] == 1
    assert counts['new_E_first_elevations'] == 8
    assert counts['matched_basic_pass'] == 143
    assert counts['matched_full_pass'] == 139
    assert counts['matched_full_rejected'] == 4
    assert ledgers['D']['accepted_moves'] == 8 and ledgers['E']['accepted_moves'] == 9
    assert counts['total'] == ledgers['D']['accepted_moves'] + ledgers['E']['accepted_moves']
    assert counts['total'] != counts['matched_full_pass']
