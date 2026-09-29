"""Render a debug map of a routed board for human inspection.

The legacy ``plotter_rect``/``plotter_bend`` figures are optimized for the
thesis plates (line width = waveguide width, no axes annotations), which makes
it hard to see whether routes collapsed onto one track or left the routing
area.  This tool draws the same geometry on a per-layer colour map with the
fiber-board outline, the port fans and a track histogram next to it.

Usage::

    python tools/render_debug_map.py 256 --output results
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

COLORS = ["tab:red", "tab:blue", "tab:purple", "tab:cyan"]


def render(N: int, output: Path, height: int = 150, width: int = 150) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from main import Router, default_pitch

    folder = output
    router = Router(
        N,
        str(folder),
        str(PROJECT_ROOT / "data" / f"fiberBoard{N}.xlsx"),
        0.05,
        default_pitch(N),
        5,
        height,
        width,
    )
    df = router.router(
        N,
        str(folder),
        str(PROJECT_ROOT / "data" / f"fiberBoard{N}.xlsx"),
        0.05,
        default_pitch(N),
        5,
        height,
        width,
    )
    rect = router.df_rect

    figure, axes = plt.subplots(1, 2, figsize=(20, 10), width_ratios=(3, 1))
    ax = axes[0]
    for _, row in rect.iterrows():
        layer = int(row["dz"])
        ax.plot(
            row["inflection_x"],
            row["inflection_y"],
            color=COLORS[layer % len(COLORS)],
            linewidth=0.6,
            alpha=0.75,
        )
    tracks = rect["inflection"].to_numpy(dtype=float)
    ax.scatter(
        rect["sx"], rect["sy"], s=4, c="black", marker=">", label="source ports"
    )
    ax.scatter(rect["lx"], rect["ly"], s=4, c="dimgray", marker="<", label="target ports")
    ax.axhline(0, color="k", linewidth=0.8)
    ax.axhline(height, color="k", linewidth=0.8)
    ax.set_xlim(-5, width + 5)
    ax.set_ylim(-10, height + 10)
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    ax.set_title(
        f"AutoRouter 2D debug map - {len(rect)} routes, {len(np.unique(tracks))} tracks"
    )
    ax.legend(loc="center left", fontsize=8)

    axes[1].hist(tracks, bins=max(20, N // 4), orientation="horizontal", color="steelblue")
    axes[1].axhline(0, color="k", linewidth=0.8)
    axes[1].axhline(height, color="k", linewidth=0.8)
    axes[1].set_ylim(-10, height + 10)
    axes[1].set_xlabel("routes per track")
    axes[1].set_title("inflection track occupancy")

    figure.tight_layout()
    target = folder / f"fiberBoard{N}debug.png"
    figure.savefig(target, dpi=140, format="png")
    plt.close(figure)
    print(f"wrote {target}")
    print(
        "  routes=%d  distinct tracks=%d  dx=[%.3f, %.3f]  inflection=[%.3f, %.3f]"
        % (
            len(rect),
            len(np.unique(tracks)),
            rect["dx"].min(),
            rect["dx"].max(),
            tracks.min(),
            tracks.max(),
        )
    )
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("channels", type=int, choices=(256, 512))
    parser.add_argument("--output", default="results")
    parser.add_argument("--height", type=int, default=150)
    parser.add_argument("--width", type=int, default=150)
    args = parser.parse_args()
    render(args.channels, Path(args.output), args.height, args.width)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
