"""Step 14 后处理：保护约束余量分析。

从 ``outputs/opt2d_step14/<channels>/<scheme>/protection_routes.csv`` 提取每个
方案相对 base 的**逐路**保护损耗变化，回答两个问题：

1. 每个方案的**最大保护越界**是多少（不是集合均值）；
2. 若把保护约束的容差设为 ε，哪些方案能通过（用于量化"约束松紧"的折衷）。

输出 ``outputs/opt2d_step14/<channels>/protection_margins.csv``。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_OUTPUT = PROJECT_ROOT / "outputs" / "opt2d_step14"
#: 保护余量档位（dB）：0 = 任务规定的严格口径。
MARGINS = (0.0, 0.001, 0.002, 0.005, 0.01, 0.02)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="保护约束余量分析")
    parser.add_argument("--channels", type=int, nargs="+", default=[256, 512])
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    for channels in args.channels:
        out_dir = Path(args.output) / str(channels)
        if not out_dir.is_dir():
            print("跳过 %d：缺少目录 %s" % (channels, out_dir), flush=True)
            continue
        rows = []
        for folder in sorted(p for p in out_dir.iterdir() if p.is_dir()):
            path = folder / "protection_routes.csv"
            if not path.is_file() or folder.name == "probe":
                continue
            frame = pd.read_csv(path)
            deltas = frame["delta_vs_base_db"].astype(float)
            row = {
                "scheme": folder.name,
                "protected_routes": len(frame),
                "max_violation_db": float(deltas.max()),
                "violating_routes": int((deltas > 1e-9).sum()),
                "improved_routes": int((deltas < -1e-9).sum()),
                "worst_route_id": int(frame.loc[deltas.idxmax(), "route_id"]),
            }
            for margin in MARGINS:
                row["passes_margin_%g" % margin] = bool(deltas.max() <= margin + 1e-9)
            rows.append(row)
        frame = pd.DataFrame(rows)
        frame.to_csv(out_dir / "protection_margins.csv", index=False, encoding="utf-8-sig")
        print("=== %d 通道 ===" % channels, flush=True)
        print(
            frame[
                ["scheme", "max_violation_db", "violating_routes", "improved_routes"]
                + ["passes_margin_%g" % m for m in MARGINS]
            ].to_string(index=False),
            flush=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
