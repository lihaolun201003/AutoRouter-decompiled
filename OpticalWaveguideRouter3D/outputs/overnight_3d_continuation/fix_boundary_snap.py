"""Fix the boundary-snap defect found by the frozen diagnostic and the G1 arms.

Root cause: split_path_interval() computed v=(t-lo)/length with t=min(b, off+length).
When the requested interval end equals the model total, off+length can be 1 ulp
BELOW the total, so v came out 0.9999999999999999 instead of 1.0. The sub-curve
then interpolated its endpoint and moved the route's frozen terminal point by
~1.2e-14 mm, so evaluate_elevation rejected the candidate with ENDPOINT_CHANGED.

Evidence: V8_G1_N2880 basic_rejection_reason_counts = {ENDPOINT_CHANGED: 1866},
114 of 185 steps were PREFIX_EVALUATED_NO_WINNER_DEFERRED, and the route 105
terminal point became (3.75, 1.1815548539573228e-14, 0) instead of (3.75, 0, 0).

Fix: snap a sub-interval parameter to an exact 0/1 primitive boundary when the
interval end is within BOUNDARY_SNAP_MM = 1e-9 mm of it (100x below the XY
preservation tolerance 1e-7 mm, equal to the route continuity tolerance).

Usage: python -B outputs/overnight_3d_continuation/fix_boundary_snap.py
"""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

EDITS = [
    ("src/path_window_3d.py",
     "PATH_WINDOW_CANDIDATE_CAP=4096",
     "PATH_WINDOW_CANDIDATE_CAP=4096\n"
     "# A sub-interval end this close to a primitive boundary is snapped to the\n"
     "# boundary itself: one ulp away the interpolated endpoint differs from the\n"
     "# frozen endpoint by ~1e-14 mm and the exact endpoint invariant would fail.\n"
     "BOUNDARY_SNAP_MM=1e-9"),
    ("src/path_window_3d.py",
     "        s=max(a,lo);t=min(b,hi)\n"
     "        if t>s:\n"
     "            u=(s-lo)/length;v=(t-lo)/length\n",
     "        s=max(a,lo);t=min(b,hi)\n"
     "        if t>s:\n"
     "            u=(s-lo)/length;v=(t-lo)/length\n"
     "            if (s-lo)<=BOUNDARY_SNAP_MM:u=0.\n"
     "            if (hi-t)<=BOUNDARY_SNAP_MM:v=1.\n"),
]

TEST = open(Path(__file__).with_name("boundary_snap_test.py"), encoding="utf-8").read()


def main():
    for relative, old, new in EDITS:
        path = ROOT / relative
        text = path.read_text(encoding="utf-8")
        if text.count(old) != 1:
            raise SystemExit("occurrence count %d for %s" % (text.count(old), relative))
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        path.write_text(text.replace(old, new), encoding="utf-8")
        print(relative, before[:12], "->", hashlib.sha256(path.read_bytes()).hexdigest()[:12])
    tests = ROOT / "tests/test_path_window_3d.py"
    text = tests.read_text(encoding="utf-8")
    if "test_windows_touching_the_route_ends" not in text:
        tests.write_text(text + TEST, encoding="utf-8")
        print("regression test appended")
    print("BOUNDARY SNAP FIX APPLIED")


if __name__ == "__main__":
    main()
