"""Per-route loss analysis for one routed board.

Runs the reconstructed ``waveguide_calculator.calc_index`` on a ``plotter_bend``
workbook, converts the result into the thesis loss model (see :mod:`loss_model`)
and writes the per-route workbook, the summary JSON and the comparison figures.

Usage::

    .venv\\Scripts\\python.exe tools/analyze_loss.py --channels 512 --radius 5
    .venv\\Scripts\\python.exe tools/analyze_loss.py --sweep --channels 512

Crossing-loss provenance and its accuracy are documented in
``loss_model.load_crossing_table`` and in
``docs/loss_model_reconstruction_report.md``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import waveguide_calculator as wc  # noqa: E402
from loss_model import (  # noqa: E402
    THESIS_BEND_LOSS_90_DB,
    bend_loss_density_db_per_mm,
    load_crossing_table,
    route_loss_from_geometry,
    summarise,
)

DEFAULT_BEND = {
    (256, 5.0): PROJECT_ROOT / "results" / "fiberBoard256bend.xlsx",
    (512, 5.0): PROJECT_ROOT / "results" / "fiberBoard512bend.xlsx",
}

#: Thesis section 4.2/4.3/4.1 reported values, for the error table.
THESIS_VALUES = {
    (256, 5.0): {"mean": 5.3, "max": 6.4},
    (512, 5.0): {"mean": 5.5, "max": 6.6},
    (512, 4.0): {"mean": 9.8, "max": 11.0},
}


def bend_workbook(channels: int, radius: float, sweep_dir: Path) -> Path:
    known = DEFAULT_BEND.get((channels, float(radius)))
    if known is not None:
        return known
    return sweep_dir / f"R{radius:g}" / f"fiberBoard{channels}bend.xlsx"


def analyse(
    channels: int, radius: float, bend_path: Path, table: dict[int, float]
) -> list:
    data = pd.read_excel(bend_path)
    result = wc.calc_index(
        data, table, 0.05, radius, height=150, width=150, file_name=None
    )
    losses = []
    for _, row in result.iterrows():
        losses.append(
            route_loss_from_geometry(
                route_id=int(row.name),
                port1=int(row["Port1"]),
                port2=int(row["Port2"]),
                bend_radius_mm=float(radius),
                total_length_mm=float(row["length"]),
                theta_intervals=row["theta"],
                crossing_angles=row["angles"],
                table=table,
            )
        )
    return losses


def to_frame(losses) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "route_id": r.route_id,
                "Port1": r.port1,
                "Port2": r.port2,
                "straight_length_mm": float(r.straight_length_mm),
                "bend_arc_length_mm": float(r.bend_arc_length_mm),
                "total_length_mm": float(r.total_length_mm),
                "bend_radius_mm": float(r.bend_radius_mm),
                "bend_count": int(r.bend_count),
                "bend_angles_deg": [round(float(a), 6) for a in r.bend_angles_deg],
                "crossing_count": int(r.crossing_count),
                "crossing_angles_deg": [
                    int(a) for a in r.crossing_angles_deg
                ],
                "straight_loss_db": float(r.straight_loss_db),
                "bend_loss_db": float(r.bend_loss_db),
                "crossing_loss_db": float(r.crossing_loss_db),
                "total_loss_db": float(r.total_loss_db),
            }
            for r in losses
        ]
    )


def summary_payload(
    channels: int, radius: float, losses, table_source: str
) -> dict:
    stats = summarise(losses)
    total = stats["loss_db_mean"]
    payload = {
        "channels": channels,
        "bend_radius_mm": float(radius),
        "route_count": len(losses),
        "crossing_loss_source": table_source,
        "mean_loss_db": stats["loss_db_mean"],
        "max_loss_db": stats["loss_db_max"],
        "min_loss_db": stats["loss_db_min"],
        "std_loss_db": stats["loss_db_std"],
        "mean_straight_loss_db": stats["straight_loss_db_mean"],
        "mean_bend_loss_db": stats["bend_loss_db_mean"],
        "mean_crossing_loss_db": stats["crossing_loss_db_mean"],
        "max_straight_loss_db": stats["straight_loss_db_max"],
        "max_bend_loss_db": stats["bend_loss_db_max"],
        "max_crossing_loss_db": stats["crossing_loss_db_max"],
        "mean_straight_length_mm": stats["straight_length_mm_mean"],
        "mean_total_length_mm": stats["total_length_mm_mean"],
        "max_total_length_mm": stats["total_length_mm_max"],
        "mean_crossing_count": stats["crossing_count_mean"],
        "max_crossing_count": stats["crossing_count_max"],
        "loss_contribution": {
            "straight": stats["straight_loss_db_mean"] / total,
            "bend": stats["bend_loss_db_mean"] / total,
            "crossing": stats["crossing_loss_db_mean"] / total,
        },
        "bend_loss_90_db": {
            str(r): THESIS_BEND_LOSS_90_DB[r] for r in sorted(THESIS_BEND_LOSS_90_DB)
        },
    }
    thesis = THESIS_VALUES.get((channels, float(radius)))
    if thesis:
        payload["thesis_mean_loss_db"] = thesis["mean"]
        payload["thesis_max_loss_db"] = thesis["max"]
        payload["mean_abs_error_db"] = payload["mean_loss_db"] - thesis["mean"]
        payload["mean_rel_error"] = (
            payload["mean_loss_db"] - thesis["mean"]
        ) / thesis["mean"]
        payload["max_abs_error_db"] = payload["max_loss_db"] - thesis["max"]
        payload["max_rel_error"] = (
            payload["max_loss_db"] - thesis["max"]
        ) / thesis["max"]
    return payload


def plot_case(
    frame: pd.DataFrame, channels: int, radius: float, out_dir: Path, prefix: str = ""
) -> None:
    """Figures for one board.

    ``prefix`` keeps a 256-channel run from overwriting the 512-channel figures;
    the 512 case uses the bare ``loss_*_R<radius>.png`` names.
    """
    tag = "%sR%g" % (prefix, radius)
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.hist(frame["total_loss_db"], bins=40, color="#4472c4", edgecolor="white")
    ax.set_xlabel("Loss (dB)")
    ax.set_ylabel("Waveguides")
    ax.set_title(
        "%d channels, bend radius %g mm: loss distribution" % (channels, radius)
    )
    fig.tight_layout()
    fig.savefig(out_dir / f"loss_distribution_{tag}.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.scatter(frame["total_length_mm"], frame["total_loss_db"], s=8, color="#c00000")
    ax.set_xlabel("Waveguide length (mm)")
    ax.set_ylabel("Loss (dB)")
    ax.set_title("%d channels: loss vs length (%s)" % (channels, tag))
    fig.tight_layout()
    fig.savefig(out_dir / f"loss_vs_length_{tag}.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.scatter(
        frame["crossing_count"], frame["total_loss_db"], s=8, color="#c00000"
    )
    ax.set_xlabel("Number of crossings (as counted by the legacy sum)")
    ax.set_ylabel("Loss (dB)")
    ax.set_title("%d channels: loss vs crossings (%s)" % (channels, tag))
    fig.tight_layout()
    fig.savefig(out_dir / f"loss_vs_crossings_{tag}.png", dpi=140)
    plt.close(fig)


def plot_radius_sweep(
    per_radius: dict[float, pd.DataFrame],
    out_dir: Path,
    channels: int,
    prefix: str = "",
) -> None:
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))
    radii = sorted(per_radius)
    means = [per_radius[r]["total_loss_db"].mean() for r in radii]
    maxes = [per_radius[r]["total_loss_db"].max() for r in radii]
    ax.plot(radii, means, "o-", label="mean")
    ax.plot(radii, maxes, "s--", label="max")
    thesis_r = [r for r in radii if (512, r) in THESIS_VALUES]
    if thesis_r:
        ax.plot(
            thesis_r,
            [THESIS_VALUES[(512, r)]["mean"] for r in thesis_r],
            "x",
            color="green",
            label="thesis mean",
        )
        ax.plot(
            thesis_r,
            [THESIS_VALUES[(512, r)]["max"] for r in thesis_r],
            "+",
            color="green",
            label="thesis max",
        )
    ax.set_xlabel("Bend radius (mm)")
    ax.set_ylabel("Loss (dB)")
    ax.set_title("512 channels: loss vs bend radius")
    ax.legend()
    for r in radii:
        ax2.scatter(
            [r] * len(per_radius[r]),
            per_radius[r]["total_loss_db"],
            s=4,
            alpha=0.35,
        )
    ax2.set_xlabel("Bend radius (mm)")
    ax2.set_ylabel("Loss (dB)")
    ax2.set_title("Per-waveguide spread")
    fig.tight_layout()
    fig.savefig(out_dir / ("%sloss_vs_radius.png" % prefix), dpi=140)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channels", type=int, default=512, choices=(256, 512))
    ap.add_argument("--radius", type=float, default=5.0)
    ap.add_argument("--radii", type=float, nargs="+", default=[2, 3, 4, 5])
    ap.add_argument("--sweep", action="store_true", help="also analyse --radii")
    ap.add_argument("--bend", type=Path, default=None)
    ap.add_argument("--sweep-dir", type=Path, default=PROJECT_ROOT / "scratch" / "radius_sweep")
    ap.add_argument("--out", type=Path, default=PROJECT_ROOT / "results")
    ap.add_argument(
        "--crossing-table",
        type=Path,
        default=None,
        help="override the reconstructed crossing-loss table",
    )
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    table = load_crossing_table(args.crossing_table)
    source = str(args.crossing_table or "data/crossing_loss_from_thesis_fig3_12.csv")

    per_radius: dict[float, pd.DataFrame] = {}

    def run(radius: float):
        path = args.bend or bend_workbook(args.channels, radius, args.sweep_dir)
        losses = analyse(args.channels, radius, path, table)
        frame = to_frame(losses)
        payload = summary_payload(args.channels, radius, losses, source)
        stem = "fiberBoard%d_loss" % args.channels
        suffix = "" if radius == 5.0 else "_R%g" % radius
        frame.to_excel(args.out / f"{stem}{suffix}.xlsx", index=False)
        with (args.out / f"{stem}{suffix}_summary.json").open(
            "w", encoding="utf-8"
        ) as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        per_radius[radius] = frame
        print(
            "R=%g  n=%d  mean %.4f dB  max %.4f dB  min %.4f dB  std %.4f"
            % (
                radius,
                len(frame),
                payload["mean_loss_db"],
                payload["max_loss_db"],
                payload["min_loss_db"],
                payload["std_loss_db"],
            )
        )
        print(
            "     straight %.4f (%.1f%%)  bend %.4f (%.1f%%)  crossing %.4f (%.1f%%)"
            % (
                payload["mean_straight_loss_db"],
                100 * payload["loss_contribution"]["straight"],
                payload["mean_bend_loss_db"],
                100 * payload["loss_contribution"]["bend"],
                payload["mean_crossing_loss_db"],
                100 * payload["loss_contribution"]["crossing"],
            )
        )
        if "thesis_mean_loss_db" in payload:
            print(
                "     thesis mean %.1f -> abs err %+0.4f (rel %+0.2f%%)   "
                "thesis max %.1f -> abs err %+0.4f (rel %+0.2f%%)"
                % (
                    payload["thesis_mean_loss_db"],
                    payload["mean_abs_error_db"],
                    100 * payload["mean_rel_error"],
                    payload["thesis_max_loss_db"],
                    payload["max_abs_error_db"],
                    100 * payload["max_rel_error"],
                )
            )
        return frame

    # The 512-channel board is the reference case, so it owns the bare
    # ``loss_*_R<radius>.png`` names; other channel counts are prefixed.
    prefix = "" if args.channels == 512 else "%d_" % args.channels

    run(args.radius)
    if args.sweep:
        for radius in args.radii:
            if radius != args.radius:
                run(radius)
        plot_radius_sweep(per_radius, args.out, args.channels, prefix)

    for radius, frame in sorted(per_radius.items()):
        plot_case(frame, args.channels, radius, args.out, prefix)
    print("\nwrote to", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
