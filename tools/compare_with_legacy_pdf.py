"""Compare a reconstruction run against outputs from the original executable.

Two legacy artifacts are available next to ``AutoRouter.exe`` and are used here
as golden files:

``fiberBoard0data.xlsx``
    The port placement ``create_sim_space`` wrote during a real run.  Comparing
    it proves the input parsing, port numbering, sorting and index handling.

``fiberBoard512_rect.pdf``
    The straight-routing figure ``plotter_rect`` wrote during the same run.
    matplotlib stores vector paths, so the polylines can be recovered
    numerically and compared route by route.

The PDF is read in PDF user space: the page is 6.4x4.8 in (460.8x345.6 pt),
``ylim`` is (-7.5, 157.5), and the first 40 ``m``/``l`` operators are the page
frame, the axes frame and the tick marks.

Usage::

    python tools/compare_with_legacy_pdf.py 512
"""

from __future__ import annotations

import argparse
import re
import sys
import zlib
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

LEGACY_DIR = Path(
    r"C:\Users\lihao\Desktop\Graduation Project\自动排布\AutoRouter"
)
LEGACY_RECT_PDF = LEGACY_DIR / "fiberBoard512_rect.pdf"
LEGACY_SNAPSHOT = LEGACY_DIR / "fiberBoard0data.xlsx"

# Transform from PDF points to data millimetres.
Y0, YSCALE = 50.112, 1.6128        # display_y = Y0 + YSCALE * data_y
TICK0, TICK_SCALE = 69.327547, 2.2525901   # x tick at data 0, and pt per mm
FRAME_AND_TICKS = 40               # m/l operators before the first route
TRACK_PITCH_512 = 0.175


def _content_stream(path: Path) -> bytes:
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
    return best


def _points(path: Path) -> list[tuple[float, float]]:
    points = []
    for line in _content_stream(path).split(b"\n"):
        line = line.strip()
        if line.endswith(b" l") or line.endswith(b" m"):
            parts = line.split()
            if len(parts) == 3:
                try:
                    points.append((float(parts[0]), float(parts[1])))
                except ValueError:
                    pass
    return points


def legacy_inflections(path: Path = LEGACY_RECT_PDF, routes: int = 512) -> np.ndarray:
    """Recover the inflection track of every routed polyline from the PDF."""
    points = _points(path)[FRAME_AND_TICKS:FRAME_AND_TICKS + routes * 4]
    y = (np.array([p[1] for p in points]) - Y0) / YSCALE
    return y.reshape(-1, 4)[:, 1]


def legacy_port_table(path: Path = LEGACY_SNAPSHOT) -> pd.DataFrame:
    return pd.read_excel(path)


def compare_snapshot(reference: pd.DataFrame, mine: pd.DataFrame) -> bool:
    columns = ["Port1", "Port2", "index1", "index2", "sy", "ly", "dz", "sx", "lx", "dx"]
    ok = len(reference) == len(mine)
    ok &= reference["Unnamed: 0"].tolist() == mine.index.tolist()
    for column in columns:
        expected = reference[column].to_numpy(dtype=float)
        actual = mine[column].to_numpy(dtype=float)
        same = bool(np.allclose(expected, actual, rtol=0, atol=1e-9))
        ok &= same
        print(f"  snapshot {column:7s} identical={same}  max delta={np.abs(expected - actual).max():.3g}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("channels", type=int, default=512, nargs="?", choices=(512,))
    parser.add_argument("--output", default="results")
    args = parser.parse_args()

    out = Path(args.output)
    print("1) create_sim_space vs the snapshot written by AutoRouter.exe")
    import problem_graph

    mine = problem_graph.create_sim_space(
        str(PROJECT_ROOT / "data" / "fiberBoard512.xlsx"),
        str(out),
        0.05,
        0.125,
        height=150,
        N=512,
    )
    snapshot_ok = compare_snapshot(legacy_port_table(), mine)

    print("\n2) plotter_rect vs the figure written by AutoRouter.exe")
    import ast

    legacy = np.sort(legacy_inflections())
    workbook = pd.read_excel(out / "fiberBoard512rect.xlsx")
    current = np.sort(
        np.array([float(ast.literal_eval(s)[1]) for s in workbook["inflection_y"]])
    )
    delta = np.round((legacy - current) / TRACK_PITCH_512)
    identical = int((np.abs(delta) < 1e-6).sum())
    counts = Counter(delta.tolist())
    print(f"  routes: {len(legacy)}")
    print(f"  identical tracks: {identical}/{len(legacy)}")
    print(f"  offset in whole tracks: "
          f"{ {int(k): counts[k] for k in sorted(counts)} }")
    print(f"  legacy distinct tracks: {len(set(legacy))}, "
          f"reconstruction: {len(set(current))}")
    print(f"  legacy track range: {legacy.min():.3f}..{legacy.max():.3f}")
    print(f"  reconstruction:     {current.min():.3f}..{current.max():.3f}")
    return 0 if snapshot_ok else 1


if __name__ == "__main__":
    sys.exit(main())
