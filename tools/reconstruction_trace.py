"""Record the same state the legacy tracer records, from the reconstruction.

``tools/legacy_runtime_trace.py`` runs the original bytecode under its own
Python 3.8 / NumPy 1.18.5 / pandas 1.0.4 stack and dumps one JSON record per
accepted ``below -> below`` route.  This script produces the identical record
shape from the Python 3.10 reconstruction so the two can be diffed route by
route — keyed on the dataframe label, which is identical in both because
``create_sim_space`` matches the legacy snapshot exactly.

Run with the project interpreter::

    .venv\\Scripts\\python.exe tools\\reconstruction_trace.py --out scratch/mine.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT)

TARGET_LINE = "list_inflection[layer] += [w.y]"
FUNCTION = "wiring_rect_below"


def find_accept_line() -> int:
    """Line number of ``list_inflection[layer] += [w.y]`` inside the below pass.

    The pass contains nested ``def`` statements, so the end of the function is
    detected by indentation rather than by the next ``def`` keyword.
    """
    path = os.path.join(PROJECT, "wiring_rect_826.py")
    with open(path, encoding="utf-8") as handle:
        lines = handle.readlines()
    start = None
    indent = None
    for number, text in enumerate(lines, start=1):
        if start is None:
            match = re.match(r"(\s*)def %s\(" % FUNCTION, text)
            if match:
                start = number
                indent = len(match.group(1))
            continue
        match = re.match(r"(\s*)def ", text)
        if match and len(match.group(1)) <= indent:
            break
        if TARGET_LINE in text:
            return number
    raise SystemExit("could not locate the accept line in %s" % path)


records: dict = {"routes": [], "no_cross": [], "mtbelow": [], "meta": {}}


def route_tracer(accept_line: int):
    def tracer(frame, event, arg):
        if event == "call":
            return tracer if frame.f_code.co_filename == os.path.join(
                PROJECT, "wiring_rect_826.py"
            ) else None
        if event != "line":
            return tracer
        if frame.f_code.co_name != FUNCTION:
            return tracer
        if frame.f_lineno != accept_line:
            return tracer
        loc = frame.f_locals
        row = loc.get("row")
        w = loc.get("w")
        nodes = loc.get("nodes")
        label = int(row[0])
        records["routes"].append(
            {
                "label": label,
                "ports": [int(row[1]["Port1"]), int(row[1]["Port2"])],
                "idx1": int(loc.get("idx1")),
                "idx2": int(loc.get("idx2")),
                "sx": float(row[1]["sx"]),
                "lx": float(row[1]["lx"]),
                "track": float(w.y),
                "i": int(loc.get("i")),
                "rEnd": [int(v) for v in w.rEnd],
                "lEnd": [int(v) for v in w.lEnd],
                "WGs": [int(v) for v in w.WGs],
            }
        )
        if nodes is not None:
            records["mtbelow"].append(
                {
                    "label": label,
                    "y": [[float(v) for v in mt.y] for mt in nodes.MTbelow],
                }
            )
        return tracer

    return tracer


def no_cross_tracer(frame, event, arg):
    if event == "return" and frame.f_code.co_name == "noCross":
        loc = frame.f_locals
        if loc.get("_type") != "below":
            return None
        records["no_cross"].append(
            [
                repr(loc.get("_type")),
                float(loc.get("lEnd")),
                float(loc.get("rEnd")),
                float(loc.get("i")),
                float(loc.get("lx")),
                float(loc.get("ly")),
                1 if arg else 0,
            ]
        )
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--channels", type=int, default=512)
    parser.add_argument("--workdir", default=os.path.join(PROJECT, "scratch_reconstruction"))
    parser.add_argument("--no-trace", action="store_true")
    args = parser.parse_args()

    os.environ.setdefault("MPLBACKEND", "Agg")
    accept_line = find_accept_line()
    print("accept line in wiring_rect_826.py = %d" % accept_line)

    os.makedirs(args.workdir, exist_ok=True)
    source = os.path.join(PROJECT, "data", "fiberBoard%d.xlsx" % args.channels)

    import numpy
    import pandas

    records["meta"] = {
        "python": sys.version,
        "numpy": numpy.__version__,
        "pandas": pandas.__version__,
        "source": source,
        "accept_line": accept_line,
    }

    import problem_graph
    import wiring_rect_826

    print("python   %s" % sys.version.split()[0])
    print("numpy    %s" % numpy.__version__)
    print("pandas   %s" % pandas.__version__)

    df = problem_graph.create_sim_space(source, args.workdir, 0.05, 0.125, height=150, N=args.channels)
    print("create_sim_space -> %d rows, sx range %.3f..%.3f" % (len(df), df["sx"].min(), df["sx"].max()))

    if not args.no_trace:
        sys.settrace(route_tracer(accept_line))
        sys.setprofile(no_cross_tracer)
    try:
        result = wiring_rect_826.plotter_rect(df, 0.05, 0.175, args.workdir, height=150, N=args.channels, r=5)
    except Exception:
        traceback.print_exc()
        result = None
    finally:
        sys.settrace(None)
        sys.setprofile(None)

    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(records, handle)
    print("records: %d routes, %d mtbelow snapshots" % (len(records["routes"]), len(records["mtbelow"])))
    if result is not None:
        print("plotter_rect -> %d rows" % len(result))
    print("wrote %s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
