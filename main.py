"""Routing workflow: input workbook in, PNG/PDF/XLSX/GDS out.

Python 3.10 port of the legacy ``main.py``.  The
``Router`` class keeps its original name, constructor signature, ``logger``
and ``finish`` signals so that later work can compare it function by function
with the legacy program.

Additions:

* ``error`` signal and a ``try`` around the pipeline in ``run()``; the legacy
  version let an exception kill the worker thread silently.
* a command line interface (``python main.py --help``) that resolves the input
  workbook from ``data/`` instead of the hard-coded ``./fiberBoard512.xlsx``.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

import pandas as pd
from PyQt5.QtCore import QThread, pyqtSignal

from problem_graph import create_sim_space
from waveguide_calculator import calc_index, draw_chart
from wiring_bend_826 import plotter_bend, svg2gds_bend
from wiring_rect_826 import plotter_rect, svg2dwgscr_rect

BASE_DIR = Path(__file__).resolve().parent

Delta_Arc = 0.001

__all__ = ["Router", "run_routing", "resolve_input", "default_pitch", "main"]


class Router(QThread):
    logger = pyqtSignal(str, str)
    finish = pyqtSignal(str, int)
    error = pyqtSignal(str)

    def __init__(
        self,
        N=256,
        SaveFolder="./results",
        Src="./fiberBoard256.xlsx",
        Line_Width=0.05,
        Dist=0.25,
        Bend_Radius=5,
        height=150,
        width=150,
    ):
        super(Router, self).__init__()
        self.N = N
        self.SaveFolder = SaveFolder
        self.Src = Src
        self.Line_Width = Line_Width
        self.Dist = Dist
        self.Bend_Radius = Bend_Radius
        self.height = height
        self.width = width

    def run(self):
        try:
            self.router(
                self.N,
                self.SaveFolder,
                self.Src,
                self.Line_Width,
                self.Dist,
                self.Bend_Radius,
                self.height,
                self.width,
            )
        except Exception:
            self.error.emit(traceback.format_exc())

    def router(
        self, N, SaveFolder, Src, Line_Width, Dist, Bend_Radius, height, width
    ) -> pd.DataFrame:
        save_folder = Path(SaveFolder)
        save_folder.mkdir(parents=True, exist_ok=True)
        print("******* Start! ********")
        self.logger.emit("正在进行直波导布线......", "Routing the straight waveguides......")
        print("******* Routing the waveguides without bend... ********")
        df = create_sim_space(
            Src, str(save_folder), Line_Width, Dist, height=height, N=N
        )
        df_rect = plotter_rect(
            df,
            Line_Width,
            (Dist + Line_Width),
            str(save_folder),
            height=height,
            N=N,
            r=Bend_Radius,
        )
        self.logger.emit("正在为波导添加弯曲......", "Adding the waveguide bends......")
        print("******* Adding bend to the routed plain... ********")
        df_bend = plotter_bend(
            df_rect,
            Line_Width,
            Dist + Line_Width,
            Bend_Radius,
            Delta_Arc,
            str(save_folder),
            "fiberBoard" + str(N) + "bend",
        )
        svg2gds_bend(
            df_bend,
            Line_Width,
            Bend_Radius,
            "fiberBoard" + str(N) + "bend.gds",
            str(save_folder),
        )
        # Additive over the legacy version: the intermediate frames stay
        # reachable from the router instance for verification.
        self.df = df
        self.df_rect = df_rect
        self.df_bend = df_bend
        self.logger.emit("波导布线完成", "Complete!")
        print("******* All done! ********")
        self.finish.emit(str(save_folder), N)
        return df_bend


def default_pitch(N: int) -> float:
    """Nominal edge-to-edge waveguide gap for a channel count, in mm.

    Values come from the verified 2D routing parameter table: 250 um for the
    256-channel board and 125 um for the 512-channel board, both with a 50 um
    waveguide.
    """
    return {256: 0.25, 512: 0.125}.get(N, 0.25)


def resolve_input(Src: str | None, N: int) -> Path:
    """Find the input workbook, defaulting to ``data/fiberBoard<N>.xlsx``."""
    if Src:
        path = Path(Src)
        if not path.is_file():
            raise FileNotFoundError(f"input workbook not found: {path}")
        return path
    candidate = BASE_DIR / "data" / f"fiberBoard{N}.xlsx"
    if not candidate.is_file():
        raise FileNotFoundError(
            f"no workbook given and {candidate} does not exist; "
            f"pass --input or add the workbook to data/"
        )
    return candidate


def run_routing(
    Src: str | None = None,
    SaveFolder: str = "./results",
    N: int = 512,
    Line_Width: float = 0.05,
    Dist: float | None = None,
    Bend_Radius: float = 5,
    height: int = 150,
    width: int = 150,
) -> pd.DataFrame:
    """Run the full pipeline synchronously and return the routed dataframe."""
    source = resolve_input(Src, N)
    if Dist is None:
        Dist = default_pitch(N)
    router = Router(
        N, SaveFolder, str(source), Line_Width, Dist, Bend_Radius, height, width
    )
    return router.router(
        N, SaveFolder, str(source), Line_Width, Dist, Bend_Radius, height, width
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description=(
            "Legacy AutoRouter 2D waveguide routing (Python 3.10 port). "
            "Runs create_sim_space -> plotter_rect -> plotter_bend -> svg2gds_bend."
        ),
    )
    parser.add_argument(
        "--input",
        default=None,
        help="input workbook with Port1/Port2 columns (default: data/fiberBoard<N>.xlsx)",
    )
    parser.add_argument("--output", default="results", help="output folder (default: results)")
    parser.add_argument(
        "--channels", type=int, default=512, help="channel count, 256 or 512 (default: 512)"
    )
    parser.add_argument(
        "--line-width", type=float, default=0.05, help="waveguide width in mm (default: 0.05)"
    )
    parser.add_argument(
        "--pitch",
        type=float,
        default=None,
        help="edge-to-edge waveguide gap in mm (default: 0.25 for 256, 0.125 for 512)",
    )
    parser.add_argument(
        "--bend-radius", type=float, default=5, help="bend radius in mm (default: 5)"
    )
    parser.add_argument("--width", type=int, default=150, help="routing area width in mm (default: 150)")
    parser.add_argument("--height", type=int, default=150, help="routing area height in mm (default: 150)")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.channels not in (256, 512):
        print(
            "error: --channels must be 256 or 512; the legacy port table defines "
            "no other fiber board",
            file=sys.stderr,
        )
        return 2
    pitch = args.pitch if args.pitch is not None else default_pitch(args.channels)
    if args.line_width <= 0 or pitch <= 0 or args.bend_radius <= 0:
        print("error: --line-width, --pitch and --bend-radius must be positive", file=sys.stderr)
        return 2
    try:
        source = resolve_input(args.input, args.channels)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        "routing %d channels from %s (line_width=%s mm, pitch=%s mm, bend_radius=%s mm, "
        "area=%sx%s mm) into %s"
        % (
            args.channels,
            source,
            args.line_width,
            pitch,
            args.bend_radius,
            args.width,
            args.height,
            args.output,
        )
    )
    router = Router(
        args.channels,
        args.output,
        str(source),
        args.line_width,
        pitch,
        args.bend_radius,
        args.height,
        args.width,
    )
    router.router(
        args.channels,
        args.output,
        str(source),
        args.line_width,
        pitch,
        args.bend_radius,
        args.height,
        args.width,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
