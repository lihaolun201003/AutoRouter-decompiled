"""Deliverable inventory with SHA256 for the v8 continuation.

Usage: python -B outputs/overnight_3d_continuation/write_inventory.py PROJECT OUTDIR
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
REPORT = ROOT / "publication/report"
GLOBS = [
    ("code", [ROOT / "src", ROOT / "scripts", ROOT / "tests"]),
    ("manifest", [OUT / "manifest"]),
    ("comparison", [OUT / "comparison"]),
    ("diagnostics", [OUT / "diagnostics"]),
    ("figures", [OUT / "figures"]),
    ("verification", [OUT / "verification"]),
    ("tests_log", [OUT / "tests"]),
    ("state", [OUT]),
    ("report", [REPORT / "三维布线v8路径弧长窗口续跑报告.pdf",
                REPORT / "brief_build/三维布线v8路径弧长窗口续跑报告.docx",
                ROOT / "docs/reports/step_19_v8_continuation.md"]),
    ("report_qa", [OUT / "report_qa"]),
]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    inventory = {}
    for label, entries in GLOBS:
        rows = {}
        for entry in entries:
            paths = []
            if entry.is_dir():
                paths = sorted(p for p in entry.rglob("*") if p.is_file())
            elif entry.is_file():
                paths = [entry]
            for path in paths:
                if "__pycache__" in str(path):
                    continue
                try:
                    key = str(path.relative_to(ROOT)).replace("\\", "/")
                    rows[key] = dict(bytes=path.stat().st_size, sha256=sha256(path))
                except OSError:
                    continue
        inventory[label] = rows
    summary = {label: len(rows) for label, rows in inventory.items()}
    target = OUT / "deliverable_inventory.json"
    target.write_text(json.dumps(dict(summary=summary, files=inventory), indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("total files", sum(summary.values()))


if __name__ == "__main__":
    main()
