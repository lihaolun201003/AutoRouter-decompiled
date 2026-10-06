"""Radius sweep: route 512 channels at several bend radii.

Routing geometry depends on the bend radius (``plotter_rect`` reserves space
with ``r=Bend_Radius``), so the thesis radius study (section 4.3) needs an
independent routing run per radius.  Results go to a scratch folder: the
``results/`` workbooks are the frozen fidelity references and are never
touched here.

Usage::

    .venv\\Scripts\\python.exe tools/radius_sweep.py --channels 512 --radii 2 3 4 5
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from main import default_pitch, run_routing  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channels", type=int, default=512)
    ap.add_argument("--radii", type=float, nargs="+", default=[2, 3, 4, 5])
    ap.add_argument("--out", default="scratch/radius_sweep")
    args = ap.parse_args()

    out_root = PROJECT_ROOT / args.out
    out_root.mkdir(parents=True, exist_ok=True)
    pitch = default_pitch(args.channels)

    for radius in args.radii:
        folder = out_root / f"R{radius:g}"
        folder.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        df_bend = run_routing(
            Src=str(PROJECT_ROOT / "data" / f"fiberBoard{args.channels}.xlsx"),
            SaveFolder=str(folder),
            N=args.channels,
            Line_Width=0.05,
            Dist=pitch,
            Bend_Radius=radius,
            height=150,
            width=150,
        )
        print(
            "R=%g: %d routes in %.1fs -> %s"
            % (radius, len(df_bend), time.time() - t0, folder)
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
