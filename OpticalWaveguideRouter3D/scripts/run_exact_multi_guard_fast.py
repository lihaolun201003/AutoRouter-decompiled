"""Bounded fast-path routing; separate frozen-geometry validation command."""
from pathlib import Path
from dataclasses import asdict
from collections import Counter
from time import perf_counter
import argparse, json
from src.io import load_legacy_512_snapshot
from src.router_2d import TrackPolicyConfig, prepare_waveguides_2d, assign_tracks_2d
from src.multi_crossing_guard import ExactMultiCrossingGuard
from scripts.experiment_top_u_order_v01 import digest

PREFIX='step_8_5_exact_multi_guard_fast'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=float,default=180)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];out=root/'outputs'
    gate=json.loads((out/'step_8_5_exact_multi_guard_g0_gate.json').read_text())
    assert gate['passed'],'Existing G0 gate required'
    source=next(root.parent.glob('*/AutoRouter/fiberBoard0data.xlsx')).parent
    sources=[source/'fiberBoard512.xlsx',source/'fiberBoard0data.xlsx']
    protected=[p for p in out.iterdir() if p.is_file()]+sources
    hashes={str(p):digest(p) for p in protected}
    ws=load_legacy_512_snapshot(*sources);preps=prepare_waveguides_2d(ws,150,0)
    cfg=TrackPolicyConfig(150,.05,.125,5,top_u_primary_order='descending')
    # Cheap OFF allocator regression only; no G0 geometry/intersection recomputation.
    off=assign_tracks_2d(ws,preps,cfg)
    assert Counter(a.status for a in off)=={'assigned':454,'unsupported_geometry':58}
    started=perf_counter();last_print=started
    class BudgetExpired(Exception):pass
    class BoundedGuard(ExactMultiCrossingGuard):
        def evaluate(self,route):
            nonlocal last_print
            now=perf_counter()
            if now-started>=args.seconds:raise BudgetExpired
            if now-last_print>=15:
                print('ROUTING',round(now-started,2),'seconds; committed',len(self.routes),
                    'evaluations',self.stats['guard_evaluation_count'],
                    'rejections',self.stats['guard_multi_rejections'],flush=True)
                last_print=now
            return super().evaluate(route)
    guard=BoundedGuard();completed=False;assignments=None
    try:
        assignments=assign_tracks_2d(ws,preps,cfg,guard=guard);completed=True
    except BudgetExpired:
        pass
    elapsed=perf_counter()-started
    result=dict(completed=completed,wall_seconds=elapsed,budget_seconds=args.seconds,
        committed_ordinary=len(guard.routes),guard=guard.summary(),config=asdict(cfg),
        G0_gate_reused=True,status=dict(Counter(a.status for a in assignments)) if completed else None,
        assignments=[asdict(a) for a in assignments] if completed else None,
        off_assignments=[asdict(a) for a in off],
        stopped_for_performance=not completed,independent_validation_run=False,
        source_hashes={str(p):digest(p) for p in sources})
    # Serialize only final/partial geometry, never guard verdict/cache for validation.
    frozen=[dict(waveguide_id=r.waveguide_id,segments=[dict(type=type(s).__name__,**asdict(s)) for s in r.segments])
            for r in sorted(guard.routes.values(),key=lambda r:r.waveguide_id)]
    assert all(digest(Path(p))==h for p,h in hashes.items()),'Existing output/source changed'
    (out/(PREFIX+'_routing.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
    (out/(PREFIX+('_geometry.json' if completed else '_partial_geometry.json'))).write_text(json.dumps(frozen),encoding='utf-8')
    with (out/(PREFIX+'_rejections.jsonl')).open('w',encoding='utf-8') as f:
        for r in guard.rejections:f.write(json.dumps(r)+'\n')
    print('ROUTING RESULT',json.dumps(result|{'off_assignments':'stored','assignments':'stored' if completed else None}),flush=True)
    if not completed:print('STOP: performance budget; no final validation.',flush=True)

if __name__=='__main__':main()