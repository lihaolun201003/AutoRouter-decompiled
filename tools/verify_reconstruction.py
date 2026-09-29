"""Verify a routing run against the real 256/512 inputs.

This is the acceptance pass required for the reconstruction: it reopens the
produced GDSII, measures the PNG, and audits the routing dataframe for the
failure modes the legacy program could hide (all waveguides collapsed onto one
track, tracks outside the routing area, ports that do not match the input
workbook, empty plots).

Usage::

    python tools/verify_reconstruction.py 256
    python tools/verify_reconstruction.py 256 --output results --prefix fiberBoard256bend
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

EXPECTED = {
    256: {"line_width": 0.05, "pitch": 0.25, "bend_radius": 5.0},
    512: {"line_width": 0.05, "pitch": 0.125, "bend_radius": 5.0},
}


def _check(condition: bool, label: str, detail: str, results: list) -> bool:
    results.append({"check": label, "ok": bool(condition), "detail": detail})
    print(f"[{'OK  ' if condition else 'FAIL'}] {label}: {detail}")
    return bool(condition)


def verify_gds(path: Path, expected_routes: int, results: list) -> None:
    import gdspy

    _check(path.is_file(), "gds exists", str(path), results)
    size = path.stat().st_size if path.is_file() else 0
    _check(size > 0, "gds non-empty", f"{size} bytes", results)
    lib = gdspy.GdsLibrary(infile=str(path))
    cells = list(lib.cells)
    _check(len(cells) >= 1, "gds cells", str(cells), results)
    cell = lib.cells[cells[0]]
    paths = cell.get_paths()
    polygons = cell.get_polygons()
    total = len(paths) + len(polygons)
    _check(
        len(paths) == expected_routes,
        "gds path count",
        f"{len(paths)} paths (expected {expected_routes})",
        results,
    )
    _check(total > 0, "gds has geometry", f"{len(paths)} paths + {len(polygons)} polygons", results)
    bbox = cell.get_bounding_box()
    _check(
        bbox is not None and np.isfinite(bbox).all(),
        "gds bounding box finite",
        None if bbox is None else bbox.tolist(),
        results,
    )


def verify_image(path: Path, results: list) -> None:
    from PIL import Image

    _check(path.is_file(), "png exists", str(path), results)
    if not path.is_file():
        return
    with Image.open(path) as image:
        image.load()
        width, height = image.size
        _check(width > 100 and height > 100, "png size", f"{width}x{height}", results)
        rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
        non_white = int((rgb < 250).any(axis=2).sum())
        fraction = non_white / float(width * height)
        _check(fraction > 0.001, "png not blank", f"{fraction:.4%} non-white pixels", results)
        colours = len(np.unique(rgb.reshape(-1, 3), axis=0))
        _check(colours > 50, "png has drawing", f"{colours} distinct colours", results)


def verify_pdf(path: Path, results: list) -> None:
    _check(path.is_file(), "pdf exists", str(path), results)
    if not path.is_file():
        return
    data = path.read_bytes()
    _check(data[:5] == b"%PDF-", "pdf header", data[:8].decode("latin-1"), results)
    _check(len(data) > 2000, "pdf size", f"{len(data)} bytes", results)


def verify_workbook(path: Path, expected_rows: int, results: list) -> pd.DataFrame | None:
    _check(path.is_file(), "workbook exists", str(path), results)
    if not path.is_file():
        return None
    df = pd.read_excel(path)
    _check(len(df) == expected_rows, "workbook row count", f"{len(df)} rows", results)
    return df


def verify_geometry(df: pd.DataFrame, N: int, height: int, results: list) -> None:
    """Audit the routed dataframe against the failure modes of the legacy code."""
    # The workbook stores the polylines as text; calc_index reads them back the
    # same way, so a literal_eval failure is itself a defect worth reporting.
    for column in ("inflection_x", "inflection_y", "center", "theta"):
        try:
            df[column] = df[column].apply(ast.literal_eval)
            results.append(
                {"check": f"{column} literal_eval", "ok": True, "detail": "parsed"}
            )
            print(f"[OK  ] {column} literal_eval: parsed")
        except Exception as exc:
            results.append(
                {
                    "check": f"{column} literal_eval",
                    "ok": False,
                    "detail": f"{type(exc).__name__}: {exc}",
                }
            )
            print(f"[FAIL] {column} literal_eval: {type(exc).__name__}: {exc}")
            return

    numeric = ["sx", "lx", "dx", "inflection", "ln"]
    for column in numeric:
        values = df[column].to_numpy(dtype=float)
        finite = np.isfinite(values).all()
        _check(finite, f"{column} finite", f"min={values.min():.4g} max={values.max():.4g}", results)

    finite_all = np.isfinite(df[numeric].to_numpy(dtype=float)).all()
    if not finite_all:
        return

    lengths_x = df["inflection_x"].apply(len)
    lengths_y = df["inflection_y"].apply(len)
    _check(
        bool((lengths_x == lengths_y).all()),
        "inflection_x/y equal length",
        f"x lengths={sorted(set(lengths_x))}",
        results,
    )
    _check(
        bool((lengths_x >= 2).all()),
        "no empty inflection arrays",
        f"min length={int(lengths_x.min())}",
        results,
    )

    # One horizontal run per route, at its inflection track, spanning sx..lx.
    # Two routes may legitimately share a track as long as their runs do not
    # overlap, so check the intervals rather than the raw counts.
    runs: dict[float, list[tuple[float, float]]] = {}
    for _, row in df.iterrows():
        track = float(row["inflection"])
        low, high = sorted((float(row["sx"]), float(row["lx"])))
        runs.setdefault(track, []).append((low, high))

    overlaps = []
    for track, intervals in runs.items():
        intervals.sort()
        for (low_a, high_a), (low_b, high_b) in zip(intervals, intervals[1:]):
            if low_b < high_a - 1e-6:
                overlaps.append((track, (low_a, high_a), (low_b, high_b)))
    _check(
        not overlaps,
        "no two routes overlap on the same track",
        f"{len(overlaps)} overlapping run(s) over {len(runs)} tracks"
        + (f", first: {overlaps[0]}" if overlaps else ""),
        results,
    )

    distinct = len({float(v) for v in df["inflection"]})
    _check(
        distinct > max(50, N // 4),
        "distinct inflection tracks",
        f"{distinct} distinct tracks for {len(df)} routes",
        results,
    )
    shared = sum(1 for intervals in runs.values() if len(intervals) > 1)
    results.append(
        {
            "check": "track reuse",
            "ok": True,
            "detail": f"{shared} of {distinct} tracks carry more than one route",
        }
    )
    print(f"[info] {shared} of {distinct} tracks carry more than one route")

    outside = 0
    for values in df["inflection_y"]:
        outside += sum(1 for v in values if v < -1e-6 or v > height + 1e-6)
    _check(outside == 0, "inflections inside routing area", f"{outside} outside", results)

    source = pd.read_excel(PROJECT_ROOT / "data" / f"fiberBoard{N}.xlsx")
    pairs_input = {tuple(sorted(p)) for p in source[["Port1", "Port2"]].to_numpy()}
    pairs_routed = {tuple(sorted(p)) for p in df[["Port1", "Port2"]].to_numpy()}
    _check(
        pairs_input == pairs_routed,
        "routed port pairs match the input workbook",
        f"input={len(pairs_input)} routed={len(pairs_routed)} "
        f"missing={len(pairs_input - pairs_routed)} extra={len(pairs_routed - pairs_input)}",
        results,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("channels", type=int, choices=(256, 512))
    parser.add_argument("--output", default="results")
    parser.add_argument("--height", type=int, default=150)
    parser.add_argument("--report", default=None, help="write the checks as JSON here")
    args = parser.parse_args()

    N = args.channels
    out = Path(args.output)
    params = EXPECTED[N]
    prefix = f"fiberBoard{N}bend"
    results: list = []

    print(f"=== verifying {N}-channel run in {out} ===")
    verify_image(out / f"{prefix}.png", results)
    verify_pdf(out / f"{prefix}.pdf", results)
    df = verify_workbook(out / f"{prefix}.xlsx", N, results)
    verify_workbook(out / f"fiberBoard{N}rect.xlsx", N, results)
    verify_pdf(out / f"fiberBoard{N}_rect.pdf", results)
    verify_gds(out / f"{prefix}.gds", N, results)
    if df is not None:
        verify_geometry(df, N, args.height, results)

    failed = [r for r in results if not r["ok"]]
    print(f"=== {len(results) - len(failed)}/{len(results)} checks passed ===")
    if args.report:
        Path(args.report).write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
