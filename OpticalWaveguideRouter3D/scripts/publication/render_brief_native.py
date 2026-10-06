"""Use the skill's PNG renderer with a native Word conversion backend on Windows.
The canonical conversion was diagnosed: no bundled LibreOffice is supplied for
Windows and soffice.exe is unavailable. No desktop LibreOffice is used.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
TMP=(ROOT/"tmp/report_redesign/native_temp").resolve()
assert TMP.is_relative_to(ROOT.resolve())
TMP.mkdir(parents=True,exist_ok=True)
os.environ["TEMP"]=os.environ["TMP"]=str(TMP)
tempfile.tempdir=str(TMP)
runtime=Path("C:/Users/lihao/.cache/codex-runtimes/codex-primary-runtime/dependencies")
poppler=runtime/"native/poppler/Library/bin"
os.environ["PATH"]=str(poppler)+os.pathsep+os.environ.get("PATH","")
renderer=Path("C:/Users/lihao/.codex/plugins/cache/openai-primary-runtime/documents/26.921.10847/skills/documents/render_docx.py")
spec=importlib.util.spec_from_file_location("canonical_docx_renderer",renderer)
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

def native_convert(doc_path,user_profile,convert_tmp_dir,stem,verbose):
    target=Path(convert_tmp_dir)/f"{stem}.pdf"
    command=["powershell.exe","-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass",
             "-File",str(ROOT/"scripts/publication/export_brief_with_word.ps1"),
             "-InputDocx",str(Path(doc_path).resolve()),"-OutputPdf",str(target.resolve())]
    proc=subprocess.run(command,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=180)
    log=proc.stdout+"\n"+proc.stderr
    if verbose: print(log,flush=True)
    if proc.returncode or not target.exists() or not target.stat().st_size:
        raise RuntimeError("Native Word conversion failed:\n"+log)
    return str(target),log

mod.convert_to_pdf=native_convert
mod.main()

