from pathlib import Path
from functools import lru_cache
import hashlib
import os,json
import numpy as np
from src.visualize_3d import load_checkpoint,sample_primitive,classify,display_points,select_examples
from src.geometry_3d import LineSegment3D,PlanarArcSegment3D,CosineTransition3D

PROJECT=Path(os.environ.get('STEP11_PROJECT',str(Path(__file__).resolve().parents[1])))
SOURCE=PROJECT/'outputs/step_10_fixed_1024_final_route_state.json'
@lru_cache(None)
def fixture():return load_checkpoint(SOURCE)
def test_final_state_load_1024():
    data,routes=fixture();assert len(routes)==1024 and len(data['routes'])==1024
def check_kind(kind):
    _,routes=fixture()
    for r in routes.values():
        for p in r.primitives:
            if isinstance(p,kind):
                a=sample_primitive(p)
                assert np.isfinite(a).all()
                for row,t in ((a[0],0),(a[-1],1)):
                    q=p.point_at(t);assert np.array_equal(row,[q.x,q.y,q.z])
                assert len(a)<=65
def test_line_sampling():check_kind(LineSegment3D)
def test_arc_sampling():check_kind(PlanarArcSegment3D)
def test_cosine_sampling():check_kind(CosineTransition3D)
def test_actual_layer_classification():
    _,routes=fixture()
    for r in routes.values():
        for p in r.primitives:
            c=classify(p)
            if isinstance(p,CosineTransition3D):assert c=='transition'
            else:assert c==p.point_at(0).z==p.point_at(1).z
def test_deterministic_examples():
    data,routes=fixture();a=select_examples(data,routes)
    reverse=dict(data,routes=list(reversed(data['routes'])))
    assert a==select_examples(reverse,routes)
    assert set(a)=={1,2}
def test_display_exaggeration_read_only():
    _,routes=fixture();p=next(p for r in routes.values() for p in r.primitives if isinstance(p,CosineTransition3D))
    original=sample_primitive(p);before=original.copy();shown=display_points(original,20)
    assert np.array_equal(original,before) and np.array_equal(shown[:,:2],before[:,:2])
    assert np.array_equal(shown[:,2],before[:,2]*20)
def test_step_10_source_read_only():
    before=hashlib.sha256(SOURCE.read_bytes()).hexdigest();load_checkpoint(SOURCE)
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==before
def test_figure_outputs_exist_nonempty():
    out=Path(os.environ.get('STEP11_OUTPUT',str(PROJECT/'outputs')))
    summary=json.loads((out/'step_11_visualization_summary.json').read_text())
    assert summary['figure_count']==13 and len(summary['files'])==26
    for name in summary['files']:
        path=out/'figures'/name
        assert path.stat().st_size>1000
        assert path.read_bytes().startswith(b'\x89PNG' if path.suffix=='.png' else b'%PDF')
