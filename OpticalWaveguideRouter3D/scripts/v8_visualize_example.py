"""Visualize one real G1 path-window route: geometry, XY preservation, curvature.

Reads a frozen v8 group terminal state plus its decisions, picks the executed
move whose selected window is a PATH window, and draws
  (a) the elevated route in 3D together with the frozen planar route,
  (b) the XY projection of both, proving the XY path is unchanged,
  (c) the exact curvature of both path-window transitions against the required
      radius, with the analytic window maximum marked.

Usage: python -B scripts/v8_visualize_example.py PROJECT OUTDIR GROUP_DIR
"""
import json
import sys
from math import hypot
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

ROOT = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
GROUP = Path(sys.argv[3]).resolve()
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "publication"))

from src.fixed_1024_routing import deserialize_route3d
from src.geometry_3d import (CosineTransition3D, LineSegment3D, PathWindowTransition3D,
                             PlanarArcSegment3D, lift_smoothed_route_to_layer, TRANSITION_TYPES)
from src.models import Layer
from src.multi_attribution import deserialize_plot
import overnight_registry as REG

FIG = OUT / "figures"
FIG.mkdir(parents=True, exist_ok=True)


def route_points(route, per_piece=24):
    rows = []
    for p in route.primitives:
        if type(p) is PathWindowTransition3D:
            for index, piece in enumerate(p.pieces):
                for t in np.linspace(0, 1, 8):
                    q = piece.point_at(float(t))
                    u = (p.piece_offsets[index] + t * piece.length()) / p.planar_run_mm
                    z = p.point_at(min(1., max(0., u))).z
                    rows.append((q.x, q.y, z))
            continue
        count = 2
        if isinstance(p, (PlanarArcSegment3D, CosineTransition3D)):
            count = per_piece
        for t in np.linspace(0, 1, count):
            q = p.point_at(float(t))
            rows.append((q.x, q.y, q.z))
    return np.array(rows)


def main():
    decisions = json.loads((GROUP / "decisions.json").read_text(encoding="utf-8"))
    selected = None
    for step in decisions:
        if step.get("selected_window_kind") == "PATH_WINDOW_G1":
            selected = step
    if selected is None:
        raise SystemExit("no path-window move in " + str(GROUP))
    route_id = selected["moved_route_id"]
    terminal = json.loads((GROUP / "final_routes.json").read_text(encoding="utf-8"))
    routes = {row["route_id"]: deserialize_route3d(row["geometry"]) for row in terminal["routes"]}
    route = routes[route_id]
    plot = json.loads((ROOT / "outputs/step_8_5_legacy_512_plot_geometry.json").read_text(encoding="utf-8"))
    planar_row = next(r for r in plot["routes"] if r["id"] == route_id)
    planar = lift_smoothed_route_to_layer(deserialize_plot(planar_row), Layer(0, 0))
    high = route_points(route)
    flat = route_points(planar)
    windows = [p for p in route.primitives if type(p) is PathWindowTransition3D]
    fig = plt.figure(figsize=(13.5, 4.4))
    axis = fig.add_subplot(1, 3, 1, projection="3d")
    axis.plot(flat[:, 0], flat[:, 1], flat[:, 2], color="0.6", linewidth=1.0,
              label="frozen planar route")
    axis.plot(high[:, 0], high[:, 1], high[:, 2], color="#d62728", linewidth=1.4,
              label="terminal route (path windows)")
    axis.set_title("route %d: 3D geometry" % route_id, fontsize=9)
    axis.legend(fontsize=6, loc="upper left")
    axis.tick_params(labelsize=6)
    axis.set_xlabel("x (mm)", fontsize=7); axis.set_ylabel("y (mm)", fontsize=7)
    axis.set_zlabel("z (mm)", fontsize=7)
    axis2 = fig.add_subplot(1, 3, 2)
    axis2.plot(flat[:, 0], flat[:, 1], color="0.6", linewidth=2.2, label="frozen planar XY")
    axis2.plot(high[:, 0], high[:, 1], color="#d62728", linewidth=1.0, linestyle="--",
               label="terminal XY projection")
    axis2.set_aspect("equal", adjustable="box")
    axis2.set_title("XY projection must coincide exactly", fontsize=9)
    axis2.legend(fontsize=6)
    axis2.grid(alpha=.3)
    axis3 = fig.add_subplot(1, 3, 3)
    for index, window in enumerate(windows):
        ts = np.linspace(0, 1, 400)
        curvature = np.array([window.curvature_at(float(t)) for t in ts])
        axis3.plot(ts, 1. / np.maximum(curvature, 1e-12), label="window %d (R of curvature)" % index,
                   linewidth=1.3)
        axis3.axhline(window.minimum_curvature_radius(), linestyle=":", linewidth=1.0,
                      color="black")
        worst = window.curvature_certificate()["attained_at_parameter"]
        axis3.plot([worst], [window.minimum_curvature_radius()], marker="o", color="black",
                   markersize=4)
    axis3.axhline(REG.REQUIRED_RADIUS_MM, color="red", linewidth=1.2,
                  label="required radius 5 mm")
    axis3.set_yscale("log")
    axis3.set_ylim(REG.REQUIRED_RADIUS_MM * 0.6, 120.)
    axis3.set_xlabel("window parameter u", fontsize=8)
    axis3.set_ylabel("radius of curvature (mm)", fontsize=8)
    axis3.set_title("exact analytic curvature of the path windows", fontsize=9)
    axis3.legend(fontsize=6)
    axis3.grid(alpha=.3)
    fig.suptitle("v8 path-arc-length window: real terminal route %d of %s"
                 % (route_id, GROUP.name), fontsize=10)
    for suffix in (".png", ".pdf"):
        fig.savefig(FIG / ("v8_example_path_window_route" + suffix), dpi=170, bbox_inches="tight")
    plt.close(fig)
    record = dict(group=GROUP.name, route_id=route_id, step_index=selected["step_index"],
                  target_pair=selected["target_pair"], action=selected["action"],
                  movement=selected.get("movement"),
                  net_collision_reduction=selected.get("net_collision_reduction"),
                  step_length_delta_mm=selected.get("step_length_delta_mm"),
                  window_phases=[dict(planar_run_mm=p.planar_run_mm, delta_z=p.delta_z,
                                      piece_count=len(p.pieces),
                                      minimum_curvature_radius_mm=p.minimum_curvature_radius(),
                                      certificate=p.curvature_certificate())
                                 for p in windows])
    (OUT / "figures" / "v8_example_path_window_route.json").write_text(
        json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(dict(route_id=route_id, windows=len(windows),
                          radii=[p.minimum_curvature_radius() for p in windows]), indent=1))


if __name__ == "__main__":
    main()
