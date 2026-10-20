"""Re-colour an existing plane layout by D56 primitive kind (line=blue, arc=red).

Read-only rendering: the plane ``routes.json`` is only *read*; no geometry, no
routing and no acceptance data is modified.  Everything else in the figure
(connector envelope labels, axis ranges, board frame, figure size, dpi and the
title lines of the frozen ``fslw/plots.py`` stack) is kept identical to the
``routing_all.png`` figure of the same plane.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from ..d56.plots_d56 import DPI, _board_frame, draw_connectors, pyplot
from ..fslw import plots as fslw_plots
from ..geometry import sample

LINE_COLOR = '#1565c0'      # blue  - kind == "line"
ARC_COLOR = '#c62828'       # red   - kind == "arc"
DISPLAY_SAGITTA_MM = 0.005  # same display sampling as fslw/plots.py


def _kind_segments(routed):
    """Split the routed primitive chains into line/arc display polylines."""
    line_segments = []
    arc_segments = []
    line_length = 0.0
    arc_length = 0.0
    for record in routed:
        for primitive in record.get("primitives") or []:
            points = sample([primitive], DISPLAY_SAGITTA_MM)
            if points is None or len(points) < 2:
                continue
            if primitive.get("kind") == "line":
                line_segments.append(points)
                p0 = primitive["p0"]
                p1 = primitive["p1"]
                line_length += math.hypot(float(p1[0]) - float(p0[0]),
                                          float(p1[1]) - float(p0[1]))
            elif primitive.get("kind") == "arc":
                arc_segments.append(points)
                radius = float(primitive["radius"])
                sweep = abs(float(primitive["sweep"]))
                arc_length += radius * sweep
    return line_segments, arc_segments, line_length, arc_length


def render_geomtype_plane(run_dir, output_path, line_color=LINE_COLOR,
                          arc_color=ARC_COLOR, meta_path=None):
    """Render ``<run_dir>/routes.json`` with line/arc colouring only."""
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D

    run_dir = Path(run_dir)
    output_path = Path(output_path)
    data = fslw_plots.load_plane(run_dir)
    title, subtitle = fslw_plots._plane_title_lines(data)  # noqa: SLF001 - frozen style
    routed = data["routed"]
    line_segments, arc_segments, line_length, arc_length = _kind_segments(routed)
    linewidth = 0.55 if len(routed) <= 128 else 0.4

    plt = pyplot()
    fig, ax = plt.subplots(figsize=(11.0, 10.0))
    if line_segments:
        ax.add_collection(LineCollection(
            line_segments, colors=[line_color], linewidths=linewidth,
            alpha=0.85, zorder=3))
    if arc_segments:
        ax.add_collection(LineCollection(
            arc_segments, colors=[arc_color], linewidths=linewidth,
            alpha=0.85, zorder=4))
    _board_frame(ax)
    draw_connectors(ax, data["connectors"])
    handles = [
        Line2D([0], [0], color=line_color, linewidth=1.4,
               label=f"line (straight): {len(line_segments)} primitives, "
                     f"{line_length:.0f} mm"),
        Line2D([0], [0], color=arc_color, linewidth=1.4,
               label=f"arc (R={(data.get('process') or {}).get('min_bend_radius_mm', 40.0):g} mm): "
                     f"{len(arc_segments)} primitives, "
                     f"{arc_length:.0f} mm"),
    ]
    ax.legend(handles=handles, loc="upper left", fontsize=7.0, framealpha=0.85)
    kind_note = ("primitive-kind colouring: line = blue, arc = red "
                 "(not by pair EN/ES/SW/NW)")
    ax.set_title(title + "\n" + subtitle + "\n" + kind_note, fontsize=10)
    fig.tight_layout()
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)

    info = dict(
        file=str(output_path), plane=data["plane"],
        routed_count=len(routed), total=fslw_plots.PLANE_TOTAL,
        line_primitives=len(line_segments), arc_primitives=len(arc_segments),
        line_centerline_mm=line_length, arc_centerline_mm=arc_length,
        line_color=line_color, arc_color=arc_color,
        routes_json=str(run_dir / "routes.json"),
        routes_sha256=_sha256(run_dir / "routes.json"),
        read_only=True,
    )
    if meta_path is not None:
        meta_path = Path(meta_path)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(info, indent=1, ensure_ascii=False),
                             encoding="utf-8")
    return info


def _sha256(path):
    import hashlib
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",
                        default="outputs/four_side_1024_v2_candidate_rr_v01")
    parser.add_argument("--label", default="BEST")
    parser.add_argument("--planes", default="z1,z2")
    parser.add_argument("--name", default="routing_geomtype.png")
    args = parser.parse_args(argv)
    root = Path(args.root)
    results = []
    for plane in [item.strip() for item in args.planes.split(",") if item.strip()]:
        run_dir = root / "planes" / "V2" / args.label / plane
        if not (run_dir / "routes.json").exists():
            raise FileNotFoundError(run_dir / "routes.json")
        info = render_geomtype_plane(
            run_dir, run_dir / args.name,
            meta_path=root / "work" / "plots_geomtype" / f"{args.label}_{plane}_meta.json")
        print(f"{args.label}/{plane}: {info['routed_count']} routed, "
              f"{info['line_primitives']} lines / {info['arc_primitives']} arcs "
              f"-> {info['file']}")
        results.append(info)
    return results


if __name__ == "__main__":
    main()

