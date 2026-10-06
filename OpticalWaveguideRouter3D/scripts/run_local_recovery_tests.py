import sys,importlib.util,json,traceback
from pathlib import Path
root=Path(sys.argv[1]).resolve();sys.path.insert(0,str(root))
results=[]
paths=sorted((root/'tests').glob('test_*.py'))
if not (root/'tests/test_local_recovery_feasibility.py').exists():
    paths.append(Path(__file__).with_name('test_local_recovery_feasibility.py'))
for p in paths:
    spec=importlib.util.spec_from_file_location(p.stem,p);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    for name,fn in vars(module).items():
        if name.startswith('test_') and callable(fn):
            try:fn();results.append(dict(file=p.name,test=name,status='PASS'))
            except Exception:results.append(dict(file=p.name,test=name,status='FAIL',traceback=traceback.format_exc()))
data=dict(passed=sum(r['status']=='PASS' for r in results),failed=sum(r['status']=='FAIL' for r in results),tests=results)
Path(sys.argv[2]).write_text(json.dumps(data,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in data.items() if k!='tests'}))
for r in results:
    if r['status']=='FAIL':print(r)
