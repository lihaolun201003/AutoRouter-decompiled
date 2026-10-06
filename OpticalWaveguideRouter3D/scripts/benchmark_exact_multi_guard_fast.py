"""Small fixed-workload comparison; never run the old 512 experiment."""
from pathlib import Path
from types import ModuleType
from time import perf_counter
from statistics import median
from dataclasses import asdict
import sys,json,cProfile,pstats,io
from src.models import Point2D,LineSegment2D,SmoothedRoute2D
from src.multi_crossing_guard import ExactMultiCrossingGuard


def main():
    root=Path(__file__).resolve().parents[1];out=root/'outputs'
    old=ModuleType('src._full_diagnostic_benchmark_reference');old.__package__='src'
    sys.modules[old.__name__]=old
    exec(compile((out/'step_8_5_exact_multi_guard_full_diagnostic_reference.txt').read_text(),'<archived guard>','exec'),old.__dict__)
    def line(i,a,b):return SmoothedRoute2D(i,[LineSegment2D(Point2D(*a),Point2D(*b))])
    existing=[line(i,(-20,i*.2),(20,i*.2)) for i in range(20)]
    existing += [line(i+20,(i*.2,-20),(i*.2,20)) for i in range(20)]
    candidate=line(1000,(-10,10.1),(10,-9.9))
    results={};witnesses={};repeats=30
    for name,cls in (('old_full_diagnostic',old.ExactMultiCrossingGuard),('fast_rejection',ExactMultiCrossingGuard)):
        g=cls()
        for route in existing:g.commit(g.evaluate(route))
        g.stats.clear();g.timings.clear();times=[]
        for _ in range(repeats):
            t=perf_counter();e=g.evaluate(candidate);times.append(perf_counter()-t)
            assert e.witness is not None
        witnesses[name]=asdict(e.witness)
        results[name]=dict(repeats=repeats,total_seconds=sum(times),median_seconds=median(times),
            pair_tests_per_evaluation=g.stats['candidate_existing_pair_checks']/repeats,
            triplets_per_evaluation=g.stats['candidate_triplet_evaluations']/repeats)
        if name=='fast_rejection':
            profile=cProfile.Profile();profile.enable()
            for _ in range(10):g.evaluate(candidate)
            profile.disable();stream=io.StringIO();pstats.Stats(profile,stream=stream).sort_stats('cumulative').print_stats(20)
            (out/'step_8_5_exact_multi_guard_fast_local_profile.txt').write_text(stream.getvalue())
    assert witnesses['old_full_diagnostic']==witnesses['fast_rejection']
    results['median_speedup_on_this_workload_only']=results['old_full_diagnostic']['median_seconds']/results['fast_rejection']['median_seconds']
    results['workload']='40 committed exact straight routes (20 horizontal +20 vertical), one diagonal candidate, 30 repeats; not a 512 routing speedup'
    results['same_witness']=True
    (out/'step_8_5_exact_multi_guard_fast_benchmark.json').write_text(json.dumps(results,indent=2))
    print(json.dumps(results,indent=2))

if __name__=='__main__':main()