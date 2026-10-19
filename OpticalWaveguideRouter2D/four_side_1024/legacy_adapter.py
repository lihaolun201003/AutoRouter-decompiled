"""Original AutoRouter first-free/noCross algorithm with explicit four-side adapters.

Run ``python -m four_side_1024.legacy_adapter`` to prepare the 1024 input only.
Routing requires the explicit ``--route`` flag. No Dubins, optimized candidate
selection, alternative schedules, or rip-up/reroute are used by this entrypoint.
"""
import argparse
from collections import Counter
import datetime
import json
import time
from pathlib import Path

import numpy as np

from .inputs import DEFAULT_INPUT, config, phase1, save_json
from .legacy_rules import LegacyRules, WGyset, nodesMTset, source_provenance
from .legacy_geometry import canonicalize, transform_primitives, opposite, adjacent
from .geometry import length, validate
from .conflicts import ConflictIndex

OUTPUT=Path(__file__).resolve().parents[1]/'outputs/four_side_1024_legacy_single_layer_v1'
GROUP_ORDER=('SW','ES','NW','EN','NS','EW')


def branch_for_source(side):
    """Use a fixed board orientation rather than forcing every source below.

    NS has N above/S below; in the EW frame W is above/E below. Adjacent
    interfaces use the same source-side polarity, with explicit 90-degree geometry.
    """
    if side not in 'NSEW':
        raise ValueError('Unknown source side')
    return 'above2below' if side in 'NW' else 'below2above'


def track_schedule(kind,qy,track_y,branch):
    """All available tracks, no per-route evaluation or track-count cutoff.

    Geometry is constructed in the canonical S->N/E frame. For above2below
    the rule frame is reflected in y, so its ascending scan maps back correctly.
    """
    above=branch=='above2below'
    if kind=='adjacent':
        rule_y=150.-qy if above else qy
        i=min(range(len(track_y)),key=lambda j:abs(track_y[j]-rule_y))
        yield i,rule_y,qy,'direct_L_interface'
    indices=range(len(track_y)) if above else reversed(range(len(track_y)))
    for i in indices:
        rule_y=track_y[i]
        yield i,rule_y,150.-rule_y if above else rule_y,'legacy_track'


def legacy_order_ok(branch,rule_y,i1,i2,track):
    """Keep the distinct original outer endpoint-order predicates."""
    if branch=='above2below':
        return rule_y>=5. and i2>track.rEnd[-1]
    if branch=='below2above':
        return rule_y<145. and i2>=track.rEnd[-1] and i1!=track.rEnd[-1]
    raise ValueError('Unknown cross-side branch')


def route_original(routes,endpoints,cfg,log):
    start=time.perf_counter(); deadline=start+cfg['search_seconds']
    pitch=cfg['width_mm']+cfg['edge_gap_mm']
    base_track_y=[round(y/1000,3) for y in range(5000,145000,int(round(pitch*1000)))]
    shared=ConflictIndex(width=cfg['width_mm'],gap=cfg['edge_gap_mm'],sagitta=cfg['sagitta_mm'])
    accepted={};failed={};evaluations=0;scans=0;group_stats=[];provenance=source_provenance();branch_calls=Counter()
    for pair in GROUP_ORDER:
        group=[r for r in routes if r['pair']==pair]
        example=group[0]; ss,ts=example['source_side'],example['target_side']
        branch=branch_for_source(ss);source_above=branch=='above2below'
        _,_,transform,kind=canonicalize(ss,ts,
            endpoints[example['source_endpoint']]['routing_xy'],endpoints[example['target_endpoint']]['routing_xy'])
        matrix=np.array(transform['matrix']); offset=np.array(transform['offset'])
        def canonical(e): return matrix@np.array(e['routing_xy'])+offset
        # Physical connector identities stay fixed. Only local ordering is adapted.
        src_names=sorted({e['connector'] for e in endpoints.values() if e['side']==ss},
            key=lambda name:np.mean([canonical(e)[0] for e in endpoints.values() if e['connector']==name]))
        target_axis=0 if kind=='opposite' else 1
        dst_names=sorted({e['connector'] for e in endpoints.values() if e['side']==ts},
            key=lambda name:np.mean([canonical(e)[target_axis] for e in endpoints.values() if e['connector']==name]))
        src_x=[[float(canonical(e)[0]) for e in endpoints.values() if e['connector']==name] for name in src_names]
        dst_x=[[float(canonical(e)[target_axis]) for e in endpoints.values() if e['connector']==name] for name in dst_names]
        nodes=nodesMTset(src_x,dst_x,height=150.) if source_above else nodesMTset(dst_x,src_x,height=150.)
        source_nodes=nodes.MTabove if source_above else nodes.MTbelow
        target_nodes=nodes.MTbelow if source_above else nodes.MTabove
        active={'channel':1}
        # Same original ln arithmetic; explicit local pin ordinal replaces board-specific modulo constants.
        rules=LegacyRules(nodes,lambda lx,ly:max(active['channel']-1-6,4),r=cfg['min_radius_mm'],height=150.)
        track_y=base_track_y
        if kind=='adjacent':
            direct_y=[float(canonical(endpoints[r['target_endpoint']])[1]) for r in group]
            direct_y=[150.-y for y in direct_y] if source_above else direct_y
            # The fixed L interface is checked at its actual coordinate, not
            # at a nearby grid coordinate. This only adds its exact state slot.
            track_y=sorted(set(base_track_y+direct_y))
        tracks=[WGyset(y=y,rEnd=[-1],lEnd=[100]) for y in track_y]
        ordered=sorted(group,key=lambda r:-canonical(endpoints[r['source_endpoint']])[0])
        group_start=time.perf_counter(); group_success=0
        for rownum,r in enumerate(ordered):
            rid=r['route_id']; src=endpoints[r['source_endpoint']]; dst=endpoints[r['target_endpoint']]
            p=canonical(src);q=canonical(dst); i1=src_names.index(src['connector']);i2=dst_names.index(dst['connector'])
            si=source_nodes[i1].x.index(float(p[0]));ti=target_nodes[i2].x.index(float(q[target_axis]))
            active['channel']=(ti if source_above else si)+1
            reasons=Counter(); blockers=Counter(); n=0; nscan=0; chosen=None
            for i,rule_y,y,mode in track_schedule(kind,float(q[1]),track_y,branch):
                if time.perf_counter()>=deadline or evaluations>=cfg['candidate_evaluation_budget']:
                    reasons['search_budget_exhausted']+=1;break
                scans+=1;nscan+=1;w=tracks[i]
                # Original branch-specific outer predicates; interface margins
                # replace unavailable same-edge-pass bounds in this all-cross-edge CSV.
                if not legacy_order_ok(branch,rule_y,i1,i2,w):
                    reasons['original_track_endpoint_order']+=1;continue
                branch_calls[branch]+=1
                ln_x=float(q[target_axis]) if source_above else float(p[0])
                if not rules.noCross(i2,i1,i,tracks,_type=branch,lx=ln_x,ly=0.):
                    reasons['original_noCross']+=1;continue
                try:
                    local=(opposite if kind=='opposite' else adjacent)(p,q,y,radius=cfg['min_radius_mm'],width=cfg['width_mm'])
                    primitives=transform_primitives(local,transform,inverse=True)
                except ValueError as exc:
                    reasons['legacy_bend_does_not_fit']+=1;continue
                errors=validate(primitives,src['routing_xy'],dst['routing_xy'],src['inward'],
                    -np.array(dst['inward']),board=150.,width=cfg['width_mm'],min_radius=cfg['min_radius_mm'])
                if errors:
                    reasons.update(errors);continue
                evaluations+=1;n+=1
                result=shared.evaluate(primitives)
                if not result['valid']:
                    found=False
                    for key in ('spacing_pairs','overlap_pairs','touch_pairs','crossing_zone_overlap_pairs'):
                        if result.get(key):
                            reasons[key]+=1;blockers.update(result[key]);found=True
                    for key in ('self_intersections','self_overlaps','self_spacing_violations','discontinuities'):
                        if result.get(key):reasons[key]+=1;found=True
                    if not found:reasons['other_geometry_conflict']+=1
                    continue
                chosen=dict(route_id=rid,layer=0,primitives=primitives,length_mm=length(primitives),
                    track_mm=y,rule_track_mm=rule_y,track_index=i,legacy_pass=branch,interface_mode=mode,
                    local_frame=transform,source_endpoint=r['source_endpoint'],target_endpoint=r['target_endpoint'])
                shared.add(rid,primitives)
                w.WGs.append(rid);w.rEnd.append(i1);w.lEnd.append(i2)
                source_nodes[i1].y[si]=rule_y;target_nodes[i2].y[ti]=rule_y
                break
            if chosen:accepted[rid]=chosen;group_success+=1
            else:
                reason='search_budget_exhausted' if reasons['search_budget_exhausted'] else 'original_first_free_no_legal_track'
                failed[rid]=dict(route_id=rid,reason=reason,evaluated=n,scanned_tracks=nscan,
                    rejection_counts=dict(reasons),blockers=dict(blockers),generation_rejections={})
            if (rownum+1)%64==0:
                log(f'{pair}: {rownum+1}/{len(group)} attempted; group success={group_success}; total={len(accepted)}; elapsed={time.perf_counter()-start:.1f}s')
        group_stats.append(dict(pair=pair,legacy_pass=branch,attempted=len(group),success=group_success,failed=len(group)-group_success,
                                duration_seconds=time.perf_counter()-group_start))
    assert len(accepted)+len(failed)==1024
    return accepted,failed,dict(algorithm='legacy_AutoRouter_first_free_noCross_four_side_adapter',
        groups=group_stats,group_order=list(GROUP_ORDER),search_runtime_seconds=time.perf_counter()-start,
        scanned_tracks=scans,candidate_evaluations=evaluations,source_provenance=provenance,
        branch_calls=dict(branch_calls),per_route_evaluation_limit=None,
        branch_assignment_counts=dict(Counter(branch_for_source(r['source_side']) for r in routes)),
        strategy_count=1,dubins=False,ripup=False,optimized_candidate_scoring=False,
        endpoint_reassignment=False,legacy_fixed_track_pitch_mm=pitch,
        adaptations=['four-side rigid frames','adjacent 90-degree interface',
            '32-channel explicit ln_calc and MT state','fixed pins: order routes instead of permuting coordinates',
            'all orientations share exact geometric audit and one routing layer',
            'full precision legacy bend formulas instead of four-decimal storage'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=DEFAULT_INPUT)
    parser.add_argument('--output',type=Path,default=None)
    parser.add_argument('--route',action='store_true',help='Explicitly run routing; default only connects and validates 1024 inputs')
    parser.add_argument('--seconds',type=float,default=600.)
    parser.add_argument('--evaluations',type=int,default=900000,help='Global geometric evaluation budget; no per-route cutoff')
    args=parser.parse_args()
    if not np.isfinite(args.seconds) or args.seconds<=0 or args.evaluations<=0:
        parser.error('Global seconds and evaluations must be positive')
    if args.output is None:
        args.output=OUTPUT if args.route else OUTPUT.with_name('four_side_1024_legacy_input_v1')
    cfg=config();cfg.update(search_seconds=args.seconds,
        strategies=['legacy_fixed_pass_order'],candidate_evaluation_budget=args.evaluations,
        enabled_cross_branches=['below2above','above2below'],per_route_evaluation_limit=None,
        ripup_routes=0,algorithm='legacy_AutoRouter_four_side_adapter',group_order=list(GROUP_ORDER))
    cfg.pop('candidates_per_route',None)
    args.output.mkdir(parents=True,exist_ok=True);start=time.perf_counter()
    with (args.output/'run.log').open('w',encoding='utf-8',buffering=1) as file:
        def log(message):
            line=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()+' '+message
            print(line,flush=True);file.write(line+'\n')
        routes,endpoints,connectors,validation=phase1(args.input,args.output,cfg)
        log('Phase1 complete before original-algorithm routing: 1024 original identities, layer=0')
        if not args.route:
            save_json(args.output/'legacy_adapter_input.json',dict(
                schema='four_side_1024_legacy_adapter_input_v1',layer=0,
                routes=routes,endpoints=endpoints,connectors=connectors,
                csv_sha256=validation['csv_sha256'],endpoint_mode=cfg['endpoint_mode']))
            save_json(args.output/'integration_status.json',dict(
                status='input_connected',connections=1024,endpoints=2048,connectors=64,
                endpoint_validation_passed=validation['passed'],routing_executed=False,
                enabled_cross_branches=['below2above','above2below'],per_route_evaluation_limit=None,
                algorithm='reverse_engineered_AutoRouter_with_required_four_side_adapters',
                source_provenance=source_provenance()))
            log('1024 input integration complete. Routing was not executed.')
            return
        old_output=Path(__file__).resolve().parents[1]/'outputs/four_side_1024_single_layer_v1'
        for name in ('mechanical_reference.md','mechanical_reference.json','legacy_tests.log'):
            if (old_output/name).exists():(args.output/name).write_bytes((old_output/name).read_bytes())
        accepted,failed,search=route_original(routes,endpoints,cfg,log)
        save_json(args.output/'search_checkpoint.json',dict(accepted=list(accepted.values()),failed=list(failed.values()),search=search))
        from .legacy_outputs import finalize
        finalize(routes,endpoints,connectors,validation,accepted,failed,search,cfg,args.output,start,log)
        log(f'finished original-algorithm adaptation in {time.perf_counter()-start:.3f}s')


if __name__=='__main__':main()
