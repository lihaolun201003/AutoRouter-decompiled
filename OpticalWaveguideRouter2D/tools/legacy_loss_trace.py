"""Run the ORIGINAL ``waveguide_calculator.calc_index`` bytecode.

The original module takes a ``loss`` DataFrame holding the per-crossing-angle
insertion loss (``angle`` / ``loss_db`` columns, the latter for 30 crossings).
That workbook was never shipped with the EXE, so this runner substitutes a
placeholder table to reach the geometry and crossing-angle code paths and to
record what the original implementation actually produces.

Everything else is the untouched original bytecode executed under the original
Python 3.8.10 / NumPy 1.18.5 / pandas 1.0.4 runtime.

Run with the 3.8 interpreter::

    _legacy_runtime\\py38\\python.exe tools\\legacy_loss_trace.py \
        --bend scratch_legacy_runtime/fiberBoard512bend.xlsx --out scratch/legacy_loss_512.json
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
RUNTIME = os.path.join(PROJECT, "_legacy_runtime")
PYZ = os.path.join(RUNTIME, "pyz")
BUNDLE = os.path.join(os.path.dirname(PROJECT), "自动排布", "AutoRouter")

sys.path.insert(0, PYZ)
sys.path.append(BUNDLE)
if hasattr(os, "add_dll_directory") and os.path.isdir(BUNDLE):
    try:
        os.add_dll_directory(BUNDLE)
    except OSError:
        pass
for _extra in (RUNTIME, os.path.join(RUNTIME, "py38")):
    if os.path.isdir(_extra) and hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(_extra)
        except OSError:
            pass

os.environ.setdefault("MPLBACKEND", "Agg")

import pandas as pd  # noqa: E402


def _as_list(value):
    """Accept a real list or the literal text Excel round-tripped it into."""
    if isinstance(value, list):
        return value
    return ast.literal_eval(value)


def _as_float(value):
    return float(value)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bend", required=True, help="plotter_bend output workbook")
    ap.add_argument("--out", required=True, help="JSON dump path")
    ap.add_argument("--bend-radius", type=float, default=5.0)
    ap.add_argument("--line-width", type=float, default=0.05)
    ap.add_argument("--height", type=int, default=150)
    ap.add_argument("--width", type=int, default=150)
    ap.add_argument(
        "--loss-db-per-30",
        type=float,
        default=0.0,
        help="placeholder loss_db column value (per 30 crossings)",
    )
    args = ap.parse_args()

    import waveguide_calculator as wc

    data = pd.read_excel(args.bend)
    # The original reads the placeholder table only through
    # loss.loc[loss["angle"] == int(a)]["loss_db"].  Angle 0 does occur for
    # crossings that the geometry routines classify as "not an angle", so the
    # placeholder spans 0..180.
    loss = pd.DataFrame(
        {
            "angle": list(range(0, 181)),
            "loss_db": [args.loss_db_per_30] * 181,
        }
    )

    out_xlsx = os.path.join(
        os.path.dirname(os.path.abspath(args.out)),
        "legacy_calc_index_output_%d.xlsx" % int(args.bend_radius),
    )
    result = wc.calc_index(
        data,
        loss,
        args.line_width,
        args.bend_radius,
        height=args.height,
        width=args.width,
        file_name=out_xlsx,
    )

    records = []
    for _, row in result.iterrows():
        records.append(
            {
                "name": int(row.name) if row.name == row.name else None,
                "Port1": int(row["Port1"]),
                "Port2": int(row["Port2"]),
                "dx": float(row["dx"]),
                "sy": float(row["sy"]),
                "ly": float(row["ly"]),
                "inflection": float(row["inflection"]),
                "length": float(row["length"]),
                "angles": [int(a) for a in row["angles"]],
                "crossing": int(row["crossing"]),
                "loss": float(row["loss"]),
                "theta": [[float(t[0]), float(t[1])] for t in row["theta"]],
                "center": [[float(c[0]), float(c[1])] for c in row["center"]],
                # calc_index parses inflection_*/center/theta itself, so those
                # arrive as lists; bend_x/bend_y keep whatever the workbook held.
                "bend_x": [_as_float(v) for v in _as_list(row["bend_x"])],
                "bend_y": [_as_float(v) for v in _as_list(row["bend_y"])],
                "inflection_x": [_as_float(v) for v in _as_list(row["inflection_x"])],
                "inflection_y": [_as_float(v) for v in _as_list(row["inflection_y"])],
            }
        )

    payload = {
        "bend_radius": args.bend_radius,
        "line_width": args.line_width,
        "height": args.height,
        "width": args.width,
        "loss_db_per_30_placeholder": args.loss_db_per_30,
        "routes": records,
        "min_angle": int(wc.min_angle),
        "count_ge20": int(wc.count),
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1)
    print("wrote", args.out, "routes:", len(records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
