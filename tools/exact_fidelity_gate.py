"""Exact-fidelity gate: reconstruction vs the original AutoRouter behaviour.

There are two reference sources, in order of authority:

1. **The original program itself** — ``_legacy_runtime/`` runs the original
   ``problem_graph.pyc`` / ``wiring_rect_826.pyc`` / ``wiring_bend_826.pyc``
   from ``AutoRouter.exe``'s ``PYZ-00.pyz`` under the very interpreter and
   libraries they were compiled against (Python 3.8.10, NumPy 1.18.5,
   pandas 1.0.4, gdspy with its real C++ clipper).  Its outputs
   (``scratch_legacy_runtime/``) are the ground truth.
2. ``AutoRouter/fiberBoard512_rect.pdf`` — a 2020 figure shipped next to the
   executable.  It turns out to come from a *different build* of AutoRouter;
   see ``docs/exact_legacy_fidelity_report.md``.  It is still reported here so
   the distinction stays visible.

The gate compares, per routing pass, how many routes land on the same
inflection track, and it reports the first mismatch with full detail.  The
frozen groups (``above -> above`` and ``below -> above``) must not regress.

Usage::

    .venv\\Scripts\\python.exe tools\\exact_fidelity_gate.py
    .venv\\Scripts\\python.exe tools\\exact_fidelity_gate.py --pdf-only
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
import zlib
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

LEGACY_DIR = Path(r"C:\Users\lihao\Desktop\Graduation Project\自动排布\AutoRouter")
STALE_PDF = LEGACY_DIR / "fiberBoard512_rect.pdf"
RUNTIME_DIR = PROJECT_ROOT / "scratch_legacy_runtime"
TRACK_PITCH = 0.175
GROUPS = ["below->below", "above->above", "below->above", "above->below"]
FROZEN = {"above->above": 112, "below->above": 115}

# PDF user space calibration (page 6.4x4.8in, ylim (-7.5, 157.5)).
Y0, YSCALE = 50.112, 1.6128
TICK0, TICK_SCALE = 69.327547, 2.2525901
FRAME_AND_TICKS = 40


def classify(df: pd.DataFrame) -> list[str]:
    return [
        "below->below" if sy == 0 and ly == 0
        else "above->above" if sy != 0 and ly != 0
        else "below->above" if sy == 0
        else "above->below"
        for sy, ly in zip(df["sy"], df["ly"])
    ]


def read_rect(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path).reset_index(drop=True)
    df["group"] = classify(df)
    df["track"] = [float(ast.literal_eval(s)[1]) for s in df["inflection_y"]]
    return df


def pdf_tracks(path: Path, routes: int = 512) -> np.ndarray:
    data = path.read_bytes()
    best = b""
    for match in re.finditer(rb"stream\r?\n", data):
        start = match.end()
        end = data.find(b"endstream", start)
        try:
            stream = zlib.decompress(data[start:end])
        except zlib.error:
            continue
        if stream.count(b" l\n") + stream.count(b" m\n") > best.count(b" l\n"):
            best = stream
    ys = []
    for line in best.split(b"\n"):
        line = line.strip()
        if line.endswith(b" l") or line.endswith(b" m"):
            parts = line.split()
            if len(parts) == 3:
                try:
                    ys.append(float(parts[1]))
                except ValueError:
                    pass
    block = ys[FRAME_AND_TICKS:FRAME_AND_TICKS + routes * 4]
    return np.round((np.array(block) - Y0) / YSCALE, 4).reshape(-1, 4)[:, 1]


def report_group(name: str, legacy: np.ndarray, current: np.ndarray) -> dict:
    delta = np.round((legacy - current) / TRACK_PITCH)
    exact = int((np.abs(delta) < 1e-6).sum())
    stats = Counter(delta.tolist())
    result = {
        "total": len(legacy),
        "exact": exact,
        "plus1": int(stats.get(1.0, 0)),
        "minus1": int(stats.get(-1.0, 0)),
        "other": len(legacy) - exact - int(stats.get(1.0, 0)) - int(stats.get(-1.0, 0)),
    }
    print(
        "  %-13s total=%3d  exact=%3d  +1=%3d  -1=%3d  other=%3d"
        % (name, result["total"], result["exact"], result["plus1"], result["minus1"], result["other"])
    )
    return result


def first_mismatch(name, legacy_rows, current_rows, legacy, current):
    for ordinal, (l, c, lr, cr) in enumerate(zip(legacy, current, legacy_rows, current_rows)):
        if abs(l - c) > 1e-6:
            print(
                "    first mismatch @ %s ordinal %d: label=%s Port1=%s Port2=%s "
                "idx1=%s idx2=%s sx=%.3f lx=%.3f  legacy=%.4f current=%.4f  delta=%+.4f mm (%.0f track)"
                % (
                    name, ordinal, lr.get("index"), lr.get("Port1"), lr.get("Port2"),
                    lr.get("index1"), lr.get("index2"), lr.get("sx"), lr.get("lx"),
                    l, c, l - c, (l - c) / TRACK_PITCH,
                )
            )
            return ordinal
    print("    first mismatch @ %s: none" % name)
    return None


def compare_frames(name: str, legacy: pd.DataFrame, current: pd.DataFrame) -> dict:
    print("%s:" % name)
    legacy_rows = legacy.to_dict("records")
    current_rows = current.to_dict("records")
    summary = {}
    for group in GROUPS:
        lm = [i for i, g in enumerate(legacy["group"]) if g == group]
        cm = [i for i, g in enumerate(current["group"]) if g == group]
        if len(lm) != len(cm):
            print("  %-13s group size differs: legacy=%d current=%d" % (group, len(lm), len(cm)))
            continue
        summary[group] = report_group(
            group,
            np.sort(legacy["track"].to_numpy()[lm]),
            np.sort(current["track"].to_numpy()[cm]),
        )
    overall_legacy = np.sort(legacy["track"].to_numpy())
    overall_current = np.sort(current["track"].to_numpy())
    summary["overall"] = report_group("overall", overall_legacy, overall_current)
    first_mismatch(name, legacy_rows, current_rows, overall_legacy, overall_current)
    return summary


def frozen_ok(summary: dict) -> bool:
    for group, minimum in FROZEN.items():
        got = summary.get(group, {}).get("exact", -1)
        if got < minimum:
            print("FROZEN GROUP REGRESSION: %s exact=%d < %d" % (group, got, minimum))
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="results")
    parser.add_argument("--channels", type=int, default=512, choices=(512,))
    parser.add_argument("--pdf-only", action="store_true")
    args = parser.parse_args()

    runtime_rect = RUNTIME_DIR / f"vec_fiberBoard{args.channels}rect.xlsx"
    current = read_rect(Path(args.output) / f"fiberBoard{args.channels}rect.xlsx")

    ok = True

    print("=== create_sim_space vs the snapshot the original wrote ===")
    snapshot = Path(PROJECT_ROOT / "data" / "fiberBoard0data.xlsx")
    runtime_snapshot = RUNTIME_DIR / "fiberBoard0data.xlsx"
    if snapshot.is_file():
        reference = pd.read_excel(snapshot)
        mine = pd.read_excel(Path(args.output) / "fiberBoard0data.xlsx")
        columns = ["Port1", "Port2", "index1", "index2", "sy", "ly", "dz", "sx", "lx", "dx"]
        same_index = reference["Unnamed: 0"].tolist() == mine["Unnamed: 0"].tolist()
        worst = 0.0
        for column in columns:
            worst = max(worst, float(np.abs(
                reference[column].to_numpy(float) - mine[column].to_numpy(float)).max()))
        print("  rows=%d index labels identical=%s  max column delta=%.3g"
              % (len(mine), same_index, worst))
        ok &= same_index and worst < 1e-9
    else:
        print("  snapshot not available")

    print()
    print("reference: " + (str(runtime_rect) if runtime_rect.is_file() else "NOT AVAILABLE"))
    print()

    if not args.pdf_only and not runtime_rect.is_file():
        # Without the original program's output there is nothing to gate on, so
        # this must fail rather than quietly pass.
        print("MISSING REFERENCE: %s" % runtime_rect)
        print("Run tools/setup_legacy_runtime.py, then")
        print(
            "  _legacy_runtime\\py38\\python.exe tools\\legacy_runtime_trace.py "
            "--out scratch\\legacy_full.json --channels 512 --full"
        )
        return 2
    if not args.pdf_only:
        print("=== original bytecode under the original runtime ===")
        legacy = read_rect(runtime_rect)
        summary = compare_frames("plotter_rect", legacy, current)
        ok &= frozen_ok(summary)
        print()

        runtime_bend = RUNTIME_DIR / f"vec_fiberBoard{args.channels}bend.xlsx"
        current_bend = Path(args.output) / f"fiberBoard{args.channels}bend.xlsx"
        if runtime_bend.is_file() and current_bend.is_file():
            print("=== bend stage (plotter_bend columns) ===")
            a = pd.read_excel(runtime_bend)
            b = pd.read_excel(current_bend)
            for column in ("inflection_x", "inflection_y", "dir", "bend_x", "bend_y", "center", "theta"):
                va = [np.ravel(ast.literal_eval(s)).astype(float).tolist() for s in a[column]]
                vb = [np.ravel(ast.literal_eval(s)).astype(float).tolist() for s in b[column]]
                same = sum(1 for x, y in zip(va, vb) if x == y)
                print("  %-13s identical=%d/%d" % (column, same, len(va)))
                ok &= same == len(va)
            for column in ("sx", "lx", "dx", "inflection", "ln"):
                delta = float(np.abs(a[column].to_numpy(float) - b[column].to_numpy(float)).max())
                print("  %-13s max delta=%.3g" % (column, delta))
                ok &= delta == 0.0
            print()

            print("=== GDSII ===")
            import gdspy

            legacy_gds = sorted(
                p for p in PROJECT_ROOT.glob(f"scratch_legacy_runtime*fiberBoard{args.channels}bend.gds")
            )
            if not legacy_gds:
                legacy_gds = sorted(RUNTIME_DIR.glob(f"*fiberBoard{args.channels}bend.gds"))
            current_gds = Path(args.output) / f"fiberBoard{args.channels}bend.gds"
            if legacy_gds and current_gds.is_file():
                la = gdspy.GdsLibrary(infile=str(legacy_gds[0]))
                lb = gdspy.GdsLibrary(infile=str(current_gds))
                ca = la.cells[list(la.cells)[0]]
                cb = lb.cells[list(lb.cells)[0]]
                pa, pb = ca.get_paths(), cb.get_paths()
                same_points = sum(1 for x, y in zip(pa, pb) if np.array_equal(x.points, y.points))
                same_width = sum(
                    1 for x, y in zip(pa, pb)
                    if getattr(x, "width", None) == getattr(y, "width", None)
                    or x.widths.tolist() == y.widths.tolist()
                )
                print("  cells %s vs %s" % (list(la.cells), list(lb.cells)))
                print("  paths %d vs %d, identical point arrays=%d, identical widths=%d"
                      % (len(pa), len(pb), same_points, same_width))
                bytes_a = legacy_gds[0].read_bytes()
                bytes_b = current_gds.read_bytes()
                differing = sum(1 for x, y in zip(bytes_a, bytes_b) if x != y) + abs(
                    len(bytes_a) - len(bytes_b)
                )
                print("  file size %d vs %d, differing bytes=%d (GDSII BGNLIB/BGNSTR timestamps)"
                      % (len(bytes_a), len(bytes_b), differing))
                ok &= same_points == len(pa) == len(pb) and differing <= 16
            else:
                print("  legacy GDS not available")
            print()

    print("=== 2020 figure shipped with the executable (different build) ===")
    if STALE_PDF.is_file():
        legacy_pdf = pdf_tracks(STALE_PDF)
        for group in GROUPS:
            lm = [i for i, g in enumerate(current["group"]) if g == group]
            report_group(group, np.sort(legacy_pdf[lm]), np.sort(current["track"].to_numpy()[lm]))
        report_group("overall", np.sort(legacy_pdf), np.sort(current["track"].to_numpy()))
        print(
            "    (multiset comparison only: that figure's port fan-out order depends on\n"
            "     its own track choices, so a per-route ordinal is not well defined)"
        )
    else:
        print("  not available")

    print()
    print("FROZEN GROUPS:", "OK" if ok else "REGRESSION")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
