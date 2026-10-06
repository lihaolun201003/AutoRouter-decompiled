"""Apply the pre-launch patches that were staged while a formal run was in flight.

Every edit is applied by exact string replacement and verified (the replacement
must occur exactly once); the script prints the SHA256 before and after each
file so the post-run source delta is auditable.

Usage: python -B outputs/overnight_3d_continuation/apply_pre_launch_patches.py
"""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

EDITS = [
    ("scripts/run_overnight_3d.py",
     "from src.geometry_3d import lift_smoothed_route_to_layer, CosineTransition3D",
     "from src.geometry_3d import (lift_smoothed_route_to_layer, CosineTransition3D,\n"
     "    PathWindowTransition3D, TRANSITION_TYPES)"),
    ("scripts/run_overnight_3d.py",
     "        transitions = [p for p in r.primitives if isinstance(p, CosineTransition3D)]",
     "        transitions = [p for p in r.primitives if isinstance(p, TRANSITION_TYPES)]"),
    ("scripts/run_overnight_3d.py",
     "    moved = {i for i, r in stored.items() if any(isinstance(p, CosineTransition3D) for p in r.primitives)}",
     "    moved = {i for i, r in stored.items() if any(isinstance(p, TRANSITION_TYPES) for p in r.primitives)}"),
    ("scripts/run_overnight_3d.py",
     "                  final_transition_count=sum(isinstance(p, CosineTransition3D)\n"
     "                                             for r in stored.values() for p in r.primitives),",
     "                  final_transition_count=sum(isinstance(p, TRANSITION_TYPES)\n"
     "                                             for r in stored.values() for p in r.primitives),\n"
     "                  final_path_window_count=sum(type(p) is PathWindowTransition3D\n"
     "                                              for r in stored.values() for p in r.primitives),\n"
     "                  minimum_path_window_radius_mm=min(\n"
     "                      (p.minimum_curvature_radius() for r in stored.values()\n"
     "                       for p in r.primitives if type(p) is PathWindowTransition3D),\n"
     "                      default=None),"),
    ("src/path_window_3d.py",
     "    before_length=route.total_length()\n    after_length=elevated.total_length()",
     "    try:\n        before_length=route.total_length()\n        after_length=elevated.total_length()\n"
     "    except RuntimeError as ex:\n"
     "        # A non-converged arc-length integral is a REJECTION, never an unchecked\n"
     "        # estimate and never a crash inside the search loop.\n"
     "        raise ValueError('PATH_WINDOW_LENGTH_NOT_CONVERGED:'+str(ex))"),
    ("src/visualize_3d.py",
     "from .geometry_3d import LineSegment3D, PlanarArcSegment3D, CosineTransition3D",
     "from .geometry_3d import (LineSegment3D, PlanarArcSegment3D, CosineTransition3D,\n"
     "    PathWindowTransition3D)"),
    ("src/visualize_3d.py",
     "    elif isinstance(p,CosineTransition3D):n=49\n    else:raise TypeError(type(p))",
     "    elif isinstance(p,CosineTransition3D):n=49\n"
     "    elif type(p) is PathWindowTransition3D:n=max(49,8*len(p.pieces))\n"
     "    else:raise TypeError(type(p))"),
    ("src/visualize_3d.py",
     "    if isinstance(p,CosineTransition3D):return 'transition'",
     "    if isinstance(p,(CosineTransition3D,PathWindowTransition3D)):return 'transition'"),
    ("scripts/visualize_3d_strategy_v4.py",
     "LineSegment3D, PlanarArcSegment3D, CosineTransition3D)",
     "LineSegment3D, PlanarArcSegment3D, CosineTransition3D, PathWindowTransition3D)"),
    ("scripts/visualize_3d_strategy_v4.py",
     "        elif isinstance(p, CosineTransition3D):\n            ts = np.linspace(0, 1, max(3, samples))",
     "        elif isinstance(p, CosineTransition3D):\n            ts = np.linspace(0, 1, max(3, samples))\n"
     "        elif type(p) is PathWindowTransition3D:\n"
     "            # never a chord: sample every planar piece of the window\n"
     "            ts = np.linspace(0, 1, max(9, 4 * samples))"),
]

TESTS = '''

# --------------------------------------------------------------------------
# 6 non-convergence is a rejection, never an unchecked estimate
# --------------------------------------------------------------------------
def test_length_non_convergence_raises_and_is_reported_as_a_rejection():
    window = PathWindowTransition3D((L((0, 0, 0), (10, 0, 0)),), 0., 1.)
    with pytest.raises(RuntimeError):
        window.length(max_depth=0, abs_tol=1e-30, rel_tol=0.)
    route = synthetic_route()
    crossing = Point3D(35., 10., 0.)
    original = build_path_window_candidate(route, (7, 8), [crossing], config(),
                                           (18., 24.), (42., 48.))
    assert original.route.total_length() > 0
    # a window whose integral cannot converge is rejected by the builder
    import src.path_window_3d as module
    saved = module.PathWindowTransition3D.length
    def never_converges(self, *args, **kwargs):
        raise RuntimeError('TRANSITION_LENGTH_NOT_CONVERGED')
    module.PathWindowTransition3D.length = never_converges
    try:
        with pytest.raises(ValueError) as error:
            module.build_path_window_candidate(route, (7, 8), [crossing], config(),
                                               (18., 24.), (42., 48.))
        assert 'PATH_WINDOW_LENGTH_NOT_CONVERGED' in str(error.value)
    finally:
        module.PathWindowTransition3D.length = saved
'''


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply(relative, old, new):
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit("expected exactly one occurrence in %s, found %d" % (relative, count))
    path.write_text(text.replace(old, new), encoding="utf-8")
    return path


def main():
    for relative, old, new in EDITS:
        path = ROOT / relative
        before = sha256(path)
        apply(relative, old, new)
        print("%-42s %s -> %s" % (relative, before[:12], sha256(path)[:12]))
    tests_path = ROOT / "tests/test_path_window_3d.py"
    before = sha256(tests_path)
    text = tests_path.read_text(encoding="utf-8")
    if "test_length_non_convergence_raises" not in text:
        tests_path.write_text(text + TESTS, encoding="utf-8")
    print("%-42s %s -> %s" % ("tests/test_path_window_3d.py", before[:12],
                              sha256(tests_path)[:12]))
    print("PATCHES APPLIED")


if __name__ == "__main__":
    main()
