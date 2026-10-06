"""Usage: python -B scripts/visualize_fixed_1024_3d.py PROJECT OUTPUT"""
import sys,json,hashlib,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.visualize_3d import load_checkpoint,generate_figures

def main():
    project=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]).resolve();out.mkdir(parents=True,exist_ok=True)
    paths=sorted((project/'outputs').glob('step_10*'))+[project/'docs/reports/step_10_fixed_1024_3d_routing.md']
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}
    source=project/'outputs/step_10_fixed_1024_final_route_state.json'
    start=time.perf_counter();data,routes=load_checkpoint(source)
    summary=json.loads((project/'outputs/step_10_fixed_1024_summary.json').read_text())
    assert (summary['initial_collision_pairs'],summary['final_collision_pairs'])==(204291,138113)
    result=generate_figures(data,routes,out/'figures')
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in before.items())
    result.update(status='PASS',route_count=len(routes),step_10_unchanged=True,source_sha256=before[str(source)],protected_sha256=before,runtime_seconds=time.perf_counter()-start)
    (out/'step_11_visualization_summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('files','protected_sha256')}))
if __name__=='__main__':main()
