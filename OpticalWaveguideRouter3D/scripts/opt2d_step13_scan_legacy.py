"""用修复后的评价器扫描 Step 13 旧产物：重合 / 接触 / 间距违规。

目的：回答"旧产物里哪些方案实际上是几何非法的"。做法是把
``outputs/opt2d_step13/<channels>/<scheme>/per_route.csv`` 的逐路参数重建成
解析几何，交给修复后的 :class:`src.opt2d.evaluator.Evaluator` 重新评价 ——
不做任何重新布线，因此旧结论与新结论的差异可以逐项归因。

输出：``outputs/opt2d_step13_fix/legacy_scheme_scan.csv``。

用法：

.. code-block:: text

    ..\\OpticalWaveguideRouter2D\\.venv\\Scripts\\python.exe -B scripts\\opt2d_step13_scan_legacy.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.opt2d.evaluator import Evaluator  # noqa: E402
from src.opt2d.freeform import FreeformParams, build_freeform_geometry  # noqa: E402
from src.opt2d.smoothing import RouteSpec, build_route_geometry  # noqa: E402

LEGACY = PROJECT_ROOT / "outputs" / "opt2d_step13"
OUT = PROJECT_ROOT / "outputs" / "opt2d_step13_fix" / "legacy_scheme_scan.csv"
SCHEMES = ("A", "R5U", "D0", "D56", "F5", "F56")


def rebuild_segments(row):
    if str(row.geometry) == "freeform":
        return build_freeform_geometry(
            FreeformParams(
                route_id=int(row.route_id), sx=float(row.sx_mm), sy=float(row.sy_mm),
                lx=float(row.lx_mm), ly=float(row.ly_mm), radius=float(row.radius_mm),
                alpha_deg=float(row.alpha_deg), t0_fraction=float(row.t0_fraction),
            )
        )
    return build_route_geometry(
        RouteSpec(
            route_id=int(row.route_id), sx=float(row.sx_mm), sy=float(row.sy_mm),
            lx=float(row.lx_mm), ly=float(row.ly_mm), track_y=float(row.track_y_mm),
            radius=float(row.radius_mm),
        )
    )


def spec_of(row) -> RouteSpec:
    return RouteSpec(
        route_id=int(row.route_id), sx=float(row.sx_mm), sy=float(row.sy_mm),
        lx=float(row.lx_mm), ly=float(row.ly_mm), track_y=float(row.track_y_mm),
        radius=float(row.radius_mm), port1=int(row.port1), port2=int(row.port2),
        index1=int(row.index1), index2=int(row.index2), kind=str(row.geometry),
        alpha_deg=float(row.alpha_deg), t0_fraction=float(row.t0_fraction),
    )


def main() -> int:
    rows = []
    for channels in (256, 512):
        for name in SCHEMES:
            folder = LEGACY / str(channels) / name
            if not (folder / "per_route.csv").is_file():
                continue
            frame = pd.read_csv(folder / "per_route.csv")
            specs = [spec_of(row) for row in frame.itertuples()]
            segments = {int(row.route_id): rebuild_segments(row) for row in frame.itertuples()}
            evaluation = Evaluator(channels).evaluate(
                specs, label=name, segments=segments, unplaced=[]
            )
            summary = evaluation.summary()
            overlap_pairs = sorted(
                {(c.route_a, c.route_b) for c in evaluation.contacts if c.kind == "overlap"}
            )
            rows.append(
                {
                    "channels": channels,
                    "scheme": name,
                    "complete_connection": summary["complete_connection"],
                    "geometry_issue_count": summary["geometry_issue_count"],
                    "geometry_issue_kinds": json.dumps(summary["geometry_issue_kinds"], ensure_ascii=False),
                    "overlap_count": summary["contact_overlap_count"],
                    "touch_count": summary["contact_touch_count"],
                    "spacing_violation_count": summary["spacing_violation_count"],
                    "mean_loss_db": summary["mean_loss_db"],
                    "max_loss_db": summary["max_loss_db"],
                    "overlap_pairs": json.dumps(overlap_pairs[:20]),
                    "legally_valid": summary["contact_overlap_count"] == 0
                    and summary["geometry_issue_count"] == 0,
                }
            )
            print(
                "%4d %-4s overlap=%d touch=%d spacing=%d issues=%d valid=%s"
                % (
                    channels, name,
                    summary["contact_overlap_count"], summary["contact_touch_count"],
                    summary["spacing_violation_count"], summary["geometry_issue_count"],
                    rows[-1]["legally_valid"],
                ),
                flush=True,
            )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT, index=False, encoding="utf-8-sig")
    print("已写出 %s" % OUT, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
