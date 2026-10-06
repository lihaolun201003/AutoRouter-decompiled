"""Prepare a publishable copy; never modify the original project files."""
from pathlib import Path
import os, json, hashlib, shutil, subprocess, collections, re, stat

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / '_repo_stage' / 'upload_20261006'
PRIVATE = {'fiberboard256.xlsx','fiberboard512.xlsx','fiberboard0data.xlsx',
           'fixed_1024_legacy_seed.json','step_10_fixed_1024_input.json',
           'step_10_legacy_512_input_audit.json'}
SKIP_DIRS = {'.git','.venv','venv','env','node_modules','__pycache__','.pytest_cache',
             '.mypy_cache','.ruff_cache','.vscode','.idea','.codex-build','.codex-finalizer',
             '.router_ppt_build','_repo_stage','_legacy_runtime','tmp','temp','native_temp',
             'scratch','scratch_legacy_runtime','scratch_reconstruction'}
LEGACY_VENDOR = {'AutoRouter','base_library','gdspy','Include','lib2to3','matplotlib',
                 'mpl-data','numpy','pandas','PyQt5','pytz','scipy','tcl','test','tk','win32com'}
SKIP_EXT = {'.dll','.pyd','.pyo','.ttf','.otf','.woff','.woff2','.swp'}
INPUT_HASHES = set()
for p in [ROOT/'OpticalWaveguideRouter2D/data'/n for n in ('fiberBoard256.xlsx','fiberBoard512.xlsx','fiberBoard0data.xlsx')]:
    INPUT_HASHES.add(hashlib.sha256(p.read_bytes()).hexdigest())
INPUT_HASHES.add(hashlib.sha256((ROOT/'OpticalWaveguideRouter3D/data/fixed_1024_legacy_seed.json').read_bytes()).hexdigest())

def reason(p, relative):
    if p.name.lower() in PRIVATE: return 'private PMT input or seed'
    if p.name.startswith('tmp') and p.suffix=='':return 'test temporary file'
    if p.name.startswith('~$') or p.name in {'.DS_Store','Thumbs.db'}:return 'local temporary file'
    if p.suffix.lower() in SKIP_EXT:return 'bundled runtime or generated font'
    if p.suffix.lower()=='.pyc' and '/bytecode/' not in relative:return 'Python cache'
    if p.suffix.lower()=='.zip':return 'original archive may contain private inputs; extracted project material published instead'
    if p.suffix.lower()=='.xlsx' and hashlib.sha256(p.read_bytes()).hexdigest() in INPUT_HASHES:return 'renamed private PMT workbook copy'
    return None

assert DEST.resolve().is_relative_to((ROOT/'_repo_stage').resolve())
assert (DEST/'.git').exists(), 'clone repository first'
# Delete only tracked files in this isolated clone; the original workspace stays intact.
old = subprocess.check_output(['git','ls-files','-z'],cwd=DEST).decode('utf-8').split('\0')
for name in old:
    if not name:continue
    target=(DEST/name).resolve()
    assert target.is_relative_to(DEST.resolve()) and '.git' not in Path(name).parts
    if target.is_file():target.unlink()

included=[];excluded=[]
for base, dirs, names in os.walk(ROOT,followlinks=False):
    relbase=Path(base).relative_to(ROOT)
    kept=[]
    for d in dirs:
        dr=relbase/d
        if d in SKIP_DIRS or d.startswith(('_backup_','pytest-of-')) or d=='AutoRouter.exe_extracted' or Path(base,d).is_symlink():
            excluded.append({'path':dr.as_posix()+'/','reason':'local environment, dependency, cache or duplicate staging'})
        elif relbase.as_posix()=='自动排布/AutoRouter' and d in LEGACY_VENDOR:
            excluded.append({'path':dr.as_posix()+'/','reason':'legacy bundled dependency runtime'})
        elif (d=='render' or d.startswith('render_') or d in {'rendered','qa_render','render_v3','render_v4'}) and 'publication' in dr.parts:
            excluded.append({'path':dr.as_posix()+'/','reason':'generated page render cache; source documents preserved'})
        else:kept.append(d)
    dirs[:]=kept
    for name in names:
        p=Path(base,name);relative=p.relative_to(ROOT).as_posix()
        why=reason(p,relative)
        if why:
            excluded.append({'path':relative,'reason':why});continue
        dest=DEST/relative;dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists():dest.chmod(stat.S_IWRITE|stat.S_IREAD)
        shutil.copy2(p,dest)
        with p.open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()
        included.append({'path':relative,'size':p.stat().st_size,'sha256':digest})

# Keep the complete presentation/video assets with Git LFS.
(DEST/'.gitattributes').write_text('*.avi filter=lfs diff=lfs merge=lfs -text\n*.mp4 filter=lfs diff=lfs merge=lfs -text\n*.pptx filter=lfs diff=lfs merge=lfs -text\n',encoding='utf-8')
(DEST/'.gitignore').write_text('''# Local environments and private PMT input files
**/.venv/
**/node_modules/
**/__pycache__/
**/.pytest_cache/
**/.git/
**/tmp/
**/.vscode/
_repo_stage/
**/fiberBoard256.xlsx
**/fiberBoard512.xlsx
**/fiberBoard0data.xlsx
**/fixed_1024_legacy_seed.json
**/step_10_fixed_1024_input.json
**/step_10_legacy_512_input_audit.json
*.pyc
!**/bytecode/*.pyc
''',encoding='utf-8')
manifest={'date':'2026-10-06','scope':'Research results retained per user authorization; only original PMT tables and seeds excluded',
          'included_count':len(included),'included_bytes':sum(x['size'] for x in included),
          'included':included,'excluded':excluded}
(DEST/'UPLOAD_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
totals=collections.defaultdict(lambda:[0,0])
for r in included:
    totals[r['path'].split('/')[0]][0]+=1;totals[r['path'].split('/')[0]][1]+=r['size']
print(json.dumps({'files':len(included),'bytes':manifest['included_bytes'],'groups':totals,
                  'large_files':[r for r in included if r['size']>100_000_000],
                  'private_excluded':[r['path'] for r in excluded if 'private PMT' in r['reason']]},ensure_ascii=False,indent=2))
