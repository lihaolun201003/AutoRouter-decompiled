"""Audit saved exhaustion traces; no full G1 or final layout validation."""
from pathlib import Path
from collections import Counter, defaultdict
from dataclasses import asdict
from hashlib import sha256
from itertools import combinations
from time import perf_counter
import csv,json,sys,inspect
from src.io import load_legacy_512_snapshot
from src.models import Point2D
from src.router_2d import (TrackPolicyConfig,TrackAssignment,prepare_waveguides_2d,
    _algorithmic_endpoints,build_track_grid_2d,generate_assigned_routes_2d,assign_tracks_2d)
from src.geometry import smooth_orthogonal_route_2d,distance
from src.physical_intersections import find_physical_route_intersections_2d
from src.multi_crossing import build_crossing_pair_map,classify_multi_crossing,MultiWaveguideCrossing
from src.multi_crossing_guard import ExactMultiCrossingGuard,CandidateEvaluation
from scripts.validate_exact_multi_guard_fast import deserialize

PREFIX='step_8_5_exact_multi_guard_exhaustion'
EXPECTED=[451,427,428,430,431,432,506,444,445,441,442,433,457,265,226,227,228,165,216,217,218]


def digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def main():
    started=perf_counter();root=Path(__file__).resolve().parents[1];out=root/'outputs'
    source=next(root.parent.glob('*/AutoRouter/fiberBoard0data.xlsx')).parent
    inputs=[source/'fiberBoard512.xlsx',source/'fiberBoard0data.xlsx']
    files=list((root/'src').glob('*.py'))+[p for p in out.iterdir() if p.is_file() and not p.name.startswith(PREFIX)]+inputs
    hashes={str(p):sha256(p.read_bytes()).hexdigest() for p in files}
    saved=json.loads((out/'step_8_5_exact_multi_guard_fast_routing.json').read_text())
    assert saved['guard']['guard_exhausted_waveguides']==EXPECTED
    frozen={r.waveguide_id:r for r in deserialize(json.loads((out/'step_8_5_exact_multi_guard_fast_partial_geometry.json').read_text()))}
    trace=[json.loads(s) for s in (out/'step_8_5_exact_multi_guard_fast_rejections.jsonl').read_text().splitlines()]
    logs=defaultdict(list)
    for record in trace:logs[record['waveguide_id']].append(record)
    ws=load_legacy_512_snapshot(*inputs);ww={w.id:w for w in ws}
    preps=prepare_waveguides_2d(ws,150,0);pp={p.waveguide_id:p for p in preps}
    cfg=TrackPolicyConfig(**saved['config']);grid=build_track_grid_2d(cfg)
    assert len(grid)==800
    def ordering(w):
        p=pp[w.id];a,b=_algorithmic_endpoints(w,p,cfg.tol)
        group=(0 if p.side=='top' else 1) if p.route_type=='u' else (2 if abs(a.position.y-150)<=cfg.tol else 3)
        primary=-a.position.x if group==0 else a.position.x
        return group,primary,b.position.x,a.pmt_id,b.pmt_id,w.id
    ordered=sorted(ws,key=ordering);rank={w.id:i for i,w in enumerate(ordered)}
    assert [i for i in sorted(EXPECTED,key=rank.get)]==EXPECTED
    log_groups=[]
    for record in trace:
        if not log_groups or log_groups[-1]!=record['waveguide_id']:log_groups.append(record['waveguide_id'])
    assert len(log_groups)==len(set(log_groups)) and log_groups==sorted(log_groups,key=rank.get)
    def curve(identifier,index):
        sk=generate_assigned_routes_2d([ww[identifier]],[pp[identifier]],
            [TrackAssignment(identifier,'assigned',index,grid[index],None)],top_y=150,bottom_y=0)[0]
        return smooth_orthogonal_route_2d(sk,5)
    def index_of(route):
        ys={s.start.y for s in route.segments if abs(s.start.y-s.end.y)<1e-9 and abs(s.start.x-s.end.x)>1e-9}
        candidates=range(800) if len(ys)!=1 else [round((next(iter(ys))-grid[0])/.175)]
        matches=[i for i in candidates if 0<=i<800 and curve(route.waveguide_id,i)==route]
        assert len(matches)==1,(route.waveguide_id,matches)
        return matches[0]
    committed_indices={i:index_of(r) for i,r in frozen.items()}
    assert len(set(committed_indices.values()))==217
    occupancy={};accepted=[];snapshots={};summary=[];all_rows=[];partial_id=None
    for w in ordered:
        i=w.id;group=ordering(w)[0]
        if abs(w.start_port.position.x-w.end_port.position.x)<10-1e-9:continue
        available=[k for k in (range(800) if group==1 else range(799,-1,-1)) if k not in occupancy]
        rejected=[r['track_index'] for r in logs[i]]
        assert len(rejected)==len(set(rejected)),i
        assert rejected==available[:len(rejected)],('missing/invalid candidate',i)
        assert all(abs(r['track_y']-grid[r['track_index']])<1e-9 for r in logs[i])
        if i in frozen:
            assert len(rejected)<len(available) and committed_indices[i]==available[len(rejected)]
            occupancy[committed_indices[i]]=i;accepted.append(i)
        elif i in EXPECTED:
            assert rejected==available and len(available)>0
            snapshots[i]=dict(prior_ids=list(accepted),occupancy=dict(occupancy))
            summary.append(dict(route_id=i,category=('top-U','bottom-U','top->bottom Z','bottom->top Z')[group],
                pmt_ids=[w.start_port.pmt_id,w.end_port.pmt_id],prior_committed=len(accepted),
                base_available=len(available),explicit_rejections=len(rejected),base_occupied=len(occupancy),
                first_candidate=rejected[0],last_candidate=rejected[-1],scan_complete=True,
                timeout_excluded=True,independent_verified=0))
        else:
            partial_id=i
            assert i in logs and len(rejected)<len(available)
            break
    assert len(accepted)==217 and len(summary)==21 and partial_id is not None
    print('TRACE RECONSTRUCTION',json.dumps(summary), 'interrupted_route',partial_id,flush=True)
    # Recompute EVERY logged witness on the 21 failed routes: no guard cache used.
    for item in summary:
        i=item['route_id'];prior=set(snapshots[i]['prior_ids'])
        for record in logs[i]:
            k=record['track_index'];old=record['witness'];ids=tuple(old['route_ids'])
            assert i in ids and len(set(ids))==3 and (set(ids)-{i})<=prior
            routes={j:(curve(i,k) if j==i else frozen[j]) for j in ids}
            events=[];cross_counts={}
            for a,b in combinations(ids,2):
                found=find_physical_route_intersections_2d(routes[a],routes[b])
                cross_counts[f'{a}-{b}']=sum(e.kind=='cross' for e in found);events.extend(found)
            assert set(cross_counts.values())=={1}
            result=classify_multi_crossing(ids,build_crossing_pair_map(events),.125,1e-9)
            assert result.classification=='multi_waveguide_crossing'
            point_error=max(distance(getattr(result,key),Point2D(**old[key])) for key in ('point_ab','point_ac','point_bc'))
            length_error=max(abs(a-b) for a,b in zip(result.side_lengths_mm,old['side_lengths_mm']))
            assert point_error<=1e-9 and length_error<=1e-9 and result.short_side_count==old['short_side_count']
            short=[name for name,v in zip(('Pab-Pac','Pab-Pbc','Pac-Pbc'),result.side_lengths_mm) if v<.125-1e-9]
            assert len(short)>=2
            row=dict(route_id=i,track_index=k,track_y=grid[k],verdict='REJECT_BY_EXPLICIT_MULTI',
                witness_other_ids=sorted(set(ids)-{i}),independent=asdict(result),cross_counts=cross_counts,
                short_edges=short,max_point_error=point_error,max_length_error=length_error)
            all_rows.append(row);item['independent_verified']+=1
        print('WITNESSES VERIFIED',i,item['independent_verified'],flush=True)
    with (out/(PREFIX+'_witness_audit.jsonl')).open('w',encoding='utf-8') as f:
        for row in all_rows:f.write(json.dumps(row)+'\n')
    with (out/(PREFIX+'_route_451_candidates.csv')).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['track_index','track_y','verdict','witness_A','witness_B',
            'canonical_route_ids','Pab','Pac','Pbc','side_lengths','short_edges','cross_counts','independent_pass'])
        writer.writeheader()
        for row in all_rows:
            if row['route_id']!=451:continue
            r=row['independent'];writer.writerow(dict(track_index=row['track_index'],track_y=row['track_y'],
                verdict=row['verdict'],witness_A=row['witness_other_ids'][0],witness_B=row['witness_other_ids'][1],
                canonical_route_ids=r['route_ids'],Pab=r['point_ab'],Pac=r['point_ac'],Pbc=r['point_bc'],
                side_lengths=r['side_lengths_mm'],short_edges=row['short_edges'],cross_counts=row['cross_counts'],independent_pass=True))
    # Local replay ends at fourth exhausted route, using saved traces for preceding routes.
    # Actual guard/kernel runs on the four targets. Accepted-prefix pair cache is rebuilt independently.
    targets=set(EXPECTED[:4]);end=rank[EXPECTED[3]];batch=ordered[:end+1]
    log_lookup={(r['waveguide_id'],r['track_index']):r for r in trace}
    cache_checks=0
    class ReplayGuard(ExactMultiCrossingGuard):
        def evaluate(self,route):
            nonlocal cache_checks
            i=route.waveguide_id
            if i in targets:return super().evaluate(route)
            k=index_of(route)
            if (i,k) in log_lookup:
                d=dict(log_lookup[i,k]['witness'])
                for name in ('point_ab','point_ac','point_bc'):d[name]=Point2D(**d[name])
                d['route_ids']=tuple(d['route_ids']);d['side_lengths_mm']=tuple(d['side_lengths_mm'])
                return CandidateEvaluation(route,len(self.routes),{},MultiWaveguideCrossing(**d))
            assert i in frozen and k==committed_indices[i] and route==frozen[i]
            events={}
            for a,existing in self.routes.items():
                found=[e for e in find_physical_route_intersections_2d(route,existing) if e.kind=='cross']
                events[tuple(sorted((i,a)))]=found[0].point if len(found)==1 else None;cache_checks+=1
            return CandidateEvaluation(route,len(self.routes),events,None)
    guard=ReplayGuard();transactions={};previous=None
    source_lines,source_start=inspect.getsourcelines(assign_tracks_2d)
    loop_line=source_start+next(n for n,line in enumerate(source_lines) if line.strip().startswith('dx = abs('))
    def snapshot(frame):
        loc=frame.f_locals
        values=dict(occupancy=loc['occupancy'],
            committed_assignments={i:asdict(a) for i,a in loc['results'].items() if a.status=='assigned'},
            geometry={i:asdict(r) for i,r in guard.routes.items()},
            pair_cache=[(list(k),asdict(p) if p is not None else None) for k,p in sorted(guard.pair_cache.items())],
            adjacency={i:sorted(v) for i,v in guard.single_cross_graph.items()})
        return {key:digest(value) for key,value in values.items()}
    def finish(i,frame):
        after=snapshot(frame);before=transactions[i]['before']
        assert before==after,(i,'transaction mutation')
        result=frame.f_locals['results'][i]
        assert result.status=='no_available_track' and result.track_index is None and i in guard.exhausted
        transactions[i].update(after=after,unchanged=True,failure_result=asdict(result))
    def local_trace(frame,event,arg):
        nonlocal previous
        if event=='return':
            if previous in targets:finish(previous,frame)
            return local_trace
        if event!='line' or frame.f_lineno!=loop_line:return local_trace
        i=frame.f_locals['waveguide'].id
        if i!=previous:
            if previous in targets:finish(previous,frame)
            previous=i
            if i in targets:
                expected=snapshots[i]
                assert set(guard.routes)==set(expected['prior_ids'])
                assert {k:v for k,v in enumerate(frame.f_locals['occupancy']) if v is not None}==expected['occupancy']
                # Validate graph directly against independently rebuilt pair points.
                for a in guard.routes:
                    assert guard.single_cross_graph[a]=={b for b in guard.routes if a!=b and guard.pair_cache[tuple(sorted((a,b)))] is not None}
                transactions[i]=dict(before=snapshot(frame),prior_cache_entries=len(guard.pair_cache))
        return local_trace
    def trace_function(frame,event,arg):
        return local_trace if event=='call' and frame.f_code is assign_tracks_2d.__code__ else None
    replay_start=perf_counter();sys.settrace(trace_function)
    try:replayed=assign_tracks_2d(batch,[pp[w.id] for w in batch],cfg,guard=guard)
    finally:sys.settrace(None)
    assert set(transactions)==targets and all(v['unchanged'] for v in transactions.values())
    for i in targets:
        replay_logs=[r for r in guard.rejections if r['waveguide_id']==i]
        assert [r['track_index'] for r in replay_logs]==[r['track_index'] for r in logs[i]]
        assert all(digest(r['witness'])==digest(old['witness']) for r,old in zip(replay_logs,logs[i]))
    assert all(sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
    result=dict(audit='PASS',conclusion='G1 FAILS ROUTABILITY REQUIREMENT',exhausted_routes=summary,
        category_counts=dict(Counter(r['category'] for r in summary)),interrupted_route=partial_id,
        witness_verifications=len(all_rows),witness_route_pair_recomputations=3*len(all_rows),
        first_route=summary[0],transactions=transactions,independently_rebuilt_prior_pairs=cache_checks,
        replay_scope='First four exhausted routes only; saved accepted-prefix geometry and rejection traces; not full G1',
        replay_seconds=perf_counter()-replay_start,total_seconds=perf_counter()-started,
        input_hashes_unchanged=True,historical_checksums_available=False,
        checksum_evidence='Reconstructed-state local replay; original run did not persist entry/exit cache checksums',
        final_global_metrics='N/A - incomplete routing',protected_hashes=hashes)
    (out/(PREFIX+'_summary.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('AUDIT COMPLETE',json.dumps({k:v for k,v in result.items() if k!='protected_hashes'}),flush=True)

if __name__=='__main__':main()