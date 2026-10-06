"""Run the ORIGINAL AutoRouter bytecode under the original runtime.

The PyInstaller bundle next to ``AutoRouter.exe`` contains the original Python
3.8 bytecode (in ``PYZ-00.pyz``) together with the exact NumPy 1.18.5 and
pandas 1.0.4 builds the program was compiled against.  ``_legacy_runtime/``
assembles them behind an official Python 3.8 embeddable interpreter, so the
original ``wiring_rect_826`` module can be executed as-is.

``sys.settrace`` then records, without modifying the original code:

* every accepted ``below -> below`` route: dataframe label, ``idx1``/``idx2``,
  ``sx``/``lx``, the chosen track ``y`` and its index;
* every ``noCross`` call and its result;
* the ``nodes.MTbelow`` state after each accepted route.

Run with the 3.8 interpreter::

    _legacy_runtime\\py38\\python.exe tools\\legacy_runtime_trace.py --out scratch\\legacy.json

The results are the ground truth the reconstruction is compared against.
"""

import argparse
import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
RUNTIME = os.path.join(PROJECT, "_legacy_runtime")
PYZ = os.path.join(RUNTIME, "pyz")
BUNDLE = os.path.join(
    os.path.dirname(PROJECT), "自动排布", "AutoRouter"
)

# The extracted tree supplies the pure-Python packages; the bundle supplies the
# compiled extensions that live loose at its top level (kiwisolver, win32*, ...)
# and the shared libraries they load.  The bundle goes last so it can never
# shadow a package that the extracted tree provides in full.
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

# matplotlib must not try to open a window; the routing result is what matters.
os.environ.setdefault("MPLBACKEND", "Agg")

records = {
    "routes": [],
    "no_cross": [],
    "mtbelow": [],
    "meta": {},
}


def _basename(path):
    return os.path.basename(str(path))


def make_tracer(target_file):
    """Line tracer over one original module.

    Original source line numbers come from the bytecode ``co_lnotab`` and are
    the same numbers the decompiled listing shows (+/- a constant), so they are
    named constants here:

    * 114  ``idx1, idx2 = int(row[1]["index1"] - N / 16), ...``
    * 126  ``list_inflection[layer] += [w.y]``   (a route was accepted)
    * 127  ``break``
    """

    def tracer(frame, event, arg):
        if event == "call":
            if _basename(frame.f_code.co_filename) == target_file:
                return tracer
            return None
        if event != "line":
            return tracer
        if _basename(frame.f_code.co_filename) != target_file:
            return tracer
        name = frame.f_code.co_name
        if name == "noCross" and event == "return":
            loc = frame.f_locals
            records["no_cross"].append(
                [
                    repr(loc.get("_type")),
                    _num(loc.get("lEnd")),
                    _num(loc.get("rEnd")),
                    _num(loc.get("i")),
                    _num(loc.get("lx")),
                    _num(loc.get("ly")),
                    1 if arg else 0,
                ]
            )
        return tracer

    return tracer


def _num(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return repr(value)


def route_tracer(frame, event, arg):
    """Record the state of every accepted ``below -> below`` route."""
    if _basename(frame.f_code.co_filename) != "wiring_rect_826.py":
        return None
    if frame.f_code.co_name != "wiring_rect_below":
        return None
    if event == "line" and frame.f_lineno == 126:
        loc = frame.f_locals
        row = loc.get("row")
        w = loc.get("w")
        nodes = loc.get("nodes")
        try:
            label = int(row[0])
            ports = (int(row[1]["Port1"]), int(row[1]["Port2"]))
            sx = float(row[1]["sx"])
            lx = float(row[1]["lx"])
        except Exception:
            return route_tracer
        records["routes"].append(
            {
                "label": label,
                "ports": list(ports),
                "idx1": int(loc.get("idx1")),
                "idx2": int(loc.get("idx2")),
                "sx": sx,
                "lx": lx,
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
    return route_tracer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--channels", type=int, default=512)
    parser.add_argument(
        "--workdir", default=os.path.join(PROJECT, "scratch_legacy_runtime")
    )
    parser.add_argument("--no-trace", action="store_true")
    parser.add_argument(
        "--full",
        action="store_true",
        help="also run plotter_bend and svg2gds_bend, i.e. the whole Router pipeline",
    )
    parser.add_argument("--prefix", default="legacy")
    args = parser.parse_args()

    os.makedirs(args.workdir, exist_ok=True)
    source = os.path.join(PROJECT, "data", "fiberBoard%d.xlsx" % args.channels)
    if not os.path.exists(source):
        raise SystemExit("missing input %s" % source)

    import numpy
    import pandas

    records["meta"] = {
        "python": sys.version,
        "numpy": numpy.__version__,
        "pandas": pandas.__version__,
        "source": source,
    }

    import problem_graph  # noqa: E402
    import wiring_rect_826  # noqa: E402

    print("python   %s" % sys.version.split()[0])
    print("numpy    %s" % numpy.__version__)
    print("pandas   %s" % pandas.__version__)
    print("modules  %s" % problem_graph.__file__)

    df = problem_graph.create_sim_space(
        source, args.workdir, 0.05, 0.125, height=150, N=args.channels
    )
    print(
        "create_sim_space -> %d rows, sx range %.3f..%.3f, index dtype %s"
        % (len(df), df["sx"].min(), df["sx"].max(), df.index.dtype)
    )

    if args.no_trace:
        sys.settrace(None)
    else:
        sys.settrace(route_tracer)
        sys.setprofile(None)
    try:
        result = wiring_rect_826.plotter_rect(
            df, 0.05, 0.175, args.workdir, height=150, N=args.channels, r=5
        )
    except Exception as exc:  # pragma: no cover - diagnostic path
        print("plotter_rect raised %s: %s" % (type(exc).__name__, exc))
        traceback.print_exc()
        result = None
    finally:
        sys.settrace(None)

    with open(args.out, "w") as handle:
        json.dump(records, handle)
    print("records: %d routes, %d mtbelow snapshots"
          % (len(records["routes"]), len(records["mtbelow"])))
    if result is not None:
        print("plotter_rect -> %d rows" % len(result))

        if args.full:
            # Same four steps main.Router performs, with the original modules.
            import wiring_bend_826

            df_bend = wiring_bend_826.plotter_bend(
                result,
                0.05,
                0.175,
                5,
                0.001,
                os.path.join(args.workdir, ""),
                "fiberBoard%d%s" % (args.channels, args.prefix),
            )
            wiring_bend_826.svg2gds_bend(
                df_bend, 0.05, 5, "fiberBoard%dbend.gds" % args.channels, args.workdir
            )
            df_bend.to_excel(
                os.path.join(args.workdir, "vec_fiberBoard%dbend.xlsx" % args.channels)
            )
            result.to_excel(
                os.path.join(args.workdir, "vec_fiberBoard%drect.xlsx" % args.channels)
            )
            print("full pipeline -> %d bend rows" % len(df_bend))

    print("wrote %s" % args.out)


if __name__ == "__main__":
    main()
