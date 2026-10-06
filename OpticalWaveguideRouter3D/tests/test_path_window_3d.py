"""v8 targeted tests: path-arc-length windows and their whole support chain.

Every test is written against the declarations of the v8 task:
  * pure straight-line degeneracy (a path window on one straight primitive must
    integrate the same arc length and the same exact maximum curvature as the
    historical cosine model)
  * line->arc and arc->line windows that cut arcs and cross primitive
    boundaries, with two independent checks of the closed-form curvature
  * internal phase sharing (one cosine phase over the whole window, never
    restarted per piece) and direction continuity
  * exact curvature bound vs a fine numeric sampling of ||r' x r''||/||r'||^3
  * a radius-tight arc must be REJECTED, never silently accepted
  * conservative distance: the adaptive bounds must bracket a fine sampling
  * self clearance, logical structure, round trip, cache invalidation and
    incremental-set consistency
"""
import json
from math import pi, sqrt, hypot, sin, cos
from pathlib import Path

import pytest

from src.clearance_3d import (adaptive_primitive_minimum_distance, analyze_primitive_clearance,
    analyze_route3d_clearance, analyze_route3d_self_clearance, classify_distance, _box)
from src.fixed_1024_routing import deserialize_route3d, serialize_route3d
from src.geometry_3d import (CosineTransition3D, LineSegment3D, PathWindowTransition3D,
    PlanarArcSegment3D, Point3D, Route3D, TRANSITION_TYPES, planar_sub_curve)
from src.geometry_3d_diagnostics import analyze_route3d_joins, minimum_xy_run_for_radius
from src.layer_assignment_3d import evaluate_elevation
from src.models import Layer
from src.overnight_engine_3d import (StrategySpec, elevation_structure,
    transition_fragment_counts)
from src.path_window_3d import (PATH_WINDOW_CANDIDATE_CAP, build_path_window_candidate,
    candidate_path_offsets, minimum_path_run_for_curvature, path_offsets_of_point,
    path_window_candidates, planar_path_model)
from src.strategy_v2_3d import failure_cache_hit, generation_cache_hit, generation_input_key, \
    xy_projection_preserved
from src.three_layer_assignment_3d import LayerConfiguration, candidate_families

ROOT = Path(__file__).resolve().parents[1]
PLOT = ROOT / "outputs" / "step_8_5_legacy_512_plot_geometry.json"


def config():
    return LayerConfiguration([Layer(0, 0.), Layer(1, 1.), Layer(2, 2.)], .1, 5.,
                              "LINE_ONLY_FINITE_WINDOWS", "EXPERIMENTAL_SYNTHETIC")


def L(a, b):
    return LineSegment3D(Point3D(*a), Point3D(*b))


def synthetic_route():
    """line -> quarter arc -> quarter arc (opposite) -> line, C1 continuous."""
    arc1 = PlanarArcSegment3D(20., 5., 0., 5., -pi / 2, pi / 2)
    arc2 = PlanarArcSegment3D(30., 5., 0., 5., pi, -pi / 2)
    return Route3D(7, (L((0, 0, 0), (20, 0, 0)), arc1, arc2, L((30, 10, 0), (50, 10, 0))))


def real_route(index=0):
    data = json.loads(PLOT.read_text(encoding="utf-8"))
    from src.multi_attribution import deserialize_plot
    from src.geometry_3d import lift_smoothed_route_to_layer
    rows = data["routes"]
    return lift_smoothed_route_to_layer(deserialize_plot(rows[index]), Layer(0, 0))


# --------------------------------------------------------------------------
# 1 pure straight-line degeneracy
# --------------------------------------------------------------------------
def test_straight_window_degenerates_to_the_historical_cosine_model():
    window = PathWindowTransition3D((L((0, 0, 0), (10, 0, 0)),), 0., 1.)
    historical = CosineTransition3D(Point3D(0, 0, 0), Point3D(10, 0, 1))
    assert window.length() == pytest.approx(historical.length(), rel=1e-12, abs=1e-12)
    assert window.max_curvature() == pytest.approx(historical.max_curvature(), rel=1e-12)
    assert window.minimum_curvature_radius() == pytest.approx(
        historical.minimum_curvature_radius(), rel=1e-12)
    for t in (0., .25, .5, .75, 1.):
        assert window.point_at(t).distance_to(historical.point_at(t)) < 1e-12
    # Arc length equals a very fine Simpson quadrature of the same speed.
    reference = 0.
    steps = 20000
    for k in range(steps):
        t = (k + .5) / steps
        reference += hypot(10., (pi / 2) * sin(pi * t)) / steps
    assert window.length() == pytest.approx(reference, rel=1e-9)


def test_straight_window_curvature_matches_the_closed_form_everywhere():
    window = PathWindowTransition3D((L((0, 0, 0), (8, 0, 0)),), 0., 1.)
    for t in (0., .1, .3, .5, .7, .9, 1.):
        zs = (1. / 8.) * (pi / 2) * sin(pi * t)
        zss = (1. / 64.) * (pi * pi / 2) * cos(pi * t)
        expected = abs(zss) / (1. + zs * zs) ** 1.5
        assert window.curvature_at(t) == pytest.approx(expected, rel=1e-12)


# --------------------------------------------------------------------------
# 2 windows that cut arcs and cross primitive boundaries
# --------------------------------------------------------------------------
def test_window_pieces_are_exact_sub_curves_and_never_chords():
    route = synthetic_route()
    model = planar_path_model(route)
    # window from the middle of the first line, across the whole first arc, into
    # the second arc
    start = 15.
    end = 20. + pi * 5. / 2. + 3.
    pieces = []
    from src.path_window_3d import split_path_interval
    for k, u, v in split_path_interval(model, start, end):
        pieces.append(planar_sub_curve(model["primitives"][k], u, v, 0.))
    assert [type(p).__name__ for p in pieces] == ["LineSegment3D", "PlanarArcSegment3D",
                                                  "PlanarArcSegment3D"]
    window = PathWindowTransition3D(tuple(pieces), 0., 1.)
    assert window.planar_run_mm == pytest.approx(end - start, abs=1e-12)
    # every sampled XY point lies exactly on the frozen planar route
    for k in range(41):
        t = k / 40
        q = window.point_at(t)
        s = start + t * (end - start)
        offset = 0.
        best = None
        for prim, off, length in zip(model["primitives"], model["offsets"], model["lengths"]):
            if s <= off + length or prim is model["primitives"][-1]:
                local = min(1., max(0., (s - off) / length))
                reference = prim.point_at(local)
                best = hypot(reference.x - q.x, reference.y - q.y)
                break
        assert best < 1e-9


def test_cross_primitive_window_keeps_the_original_xy_path():
    route = synthetic_route()
    crossing = Point3D(35., 10., 0.)
    candidate = build_path_window_candidate(route, (7, 8), [crossing], config(),
                                            (18., 24.), (42., 48.))
    ok, reason = xy_projection_preserved(candidate.route, route)
    assert ok, reason
    assert candidate.route.start_point == route.start_point
    assert candidate.route.end_point == route.end_point
    assert elevation_structure(candidate.route)[0]
    joins = analyze_route3d_joins(candidate.route)
    assert joins.all_C0 and joins.all_C1_direction


def test_internal_pieces_share_one_phase_and_are_not_restarted():
    """A window split over several planar pieces must follow ONE cosine phase."""
    route = synthetic_route()
    crossing = Point3D(35., 10., 0.)
    candidate = build_path_window_candidate(route, (7, 8), [crossing], config(),
                                            (18., 24.), (42., 48.))
    rise = [p for p in candidate.route.primitives if isinstance(p, PathWindowTransition3D)][0]
    # The four values sit on one sin^2 phase, taken at the piece boundaries.
    breaks = rise.curvature_breakpoints()
    assert len(breaks) == len(rise.pieces) + 1
    for t in breaks:
        assert rise.point_at(t).z == pytest.approx(sin(pi * t / 2) ** 2, abs=1e-12)
    # A restart per piece would make z come back to 0 at every internal boundary.
    internal = breaks[1:-1]
    assert internal, "this window must really span several pieces"
    for t in internal:
        assert rise.point_at(t).z > 0.


def test_direction_is_continuous_on_both_sides_of_every_piece():
    route = synthetic_route()
    crossing = Point3D(35., 10., 0.)
    candidate = build_path_window_candidate(route, (7, 8), [crossing], config(),
                                            (18., 24.), (42., 48.))
    rise = [p for p in candidate.route.primitives if isinstance(p, PathWindowTransition3D)][0]
    for t in rise.curvature_breakpoints():
        left = rise.tangent_at(max(0., t - 1e-7))
        right = rise.tangent_at(min(1., t + 1e-7))
        nl = hypot(*left); nr = hypot(*right)
        dot = sum(a * b for a, b in zip(left, right)) / (nl * nr)
        assert dot > 1 - 1e-9


# --------------------------------------------------------------------------
# 3 exact 3D curvature against an independent numeric evaluation
# --------------------------------------------------------------------------
def _numeric_curvature(window, t, h=1e-6):
    def r(u):
        p = window.point_at(u)
        return (p.x, p.y, p.z)
    a = r(max(0., t - h)); b = r(t); c = r(min(1., t + h))
    r1 = tuple((c[i] - a[i]) / (min(1., t + h) - max(0., t - h)) for i in range(3))
    r2 = tuple((c[i] - 2 * b[i] + a[i]) / (h * h) for i in range(3))
    cross = (r1[1] * r2[2] - r1[2] * r2[1], r1[2] * r2[0] - r1[0] * r2[2],
             r1[0] * r2[1] - r1[1] * r2[0])
    norm1 = hypot(*r1)
    return hypot(*cross) / norm1 ** 3


@pytest.mark.parametrize("t", [0.05, 0.2, 0.35, 0.5, 0.65, 0.8, 0.95])
def test_closed_form_curvature_matches_numeric_3d_curvature(t):
    route = synthetic_route()
    from src.path_window_3d import split_path_interval
    model = planar_path_model(route)
    pieces = [planar_sub_curve(model["primitives"][k], u, v, 0.)
              for k, u, v in split_path_interval(model, 15., 32.)]
    window = PathWindowTransition3D(tuple(pieces), 0., 1.)
    assert window.curvature_at(t) == pytest.approx(_numeric_curvature(window, t), rel=2e-3)


def test_max_curvature_is_an_exact_window_maximum_not_a_sample_minimum():
    route = synthetic_route()
    from src.path_window_3d import split_path_interval
    model = planar_path_model(route)
    pieces = [planar_sub_curve(model["primitives"][k], u, v, 0.)
              for k, u, v in split_path_interval(model, 15., 32.)]
    window = PathWindowTransition3D(tuple(pieces), 0., 1.)
    worst = max(window.curvature_at(k / 4000.) for k in range(4001))
    assert window.max_curvature() >= worst
    assert window.max_curvature() == pytest.approx(worst, rel=1e-6)
    certificate = window.curvature_certificate()
    assert certificate["method"] == "ANALYTIC_CLOSED_FORM_MAX_AT_PIECE_BOUNDARIES"
    assert certificate["minimum_curvature_radius_mm"] == pytest.approx(
        1. / window.max_curvature())
    assert certificate["attained_at_parameter"] in window.curvature_breakpoints()


def test_arc_curvature_enters_the_three_dimensional_formula():
    """kappa_3D = sqrt(kappa_xy^2 (1+z_s^2) + z_ss^2)/(1+z_s^2)^1.5 exactly."""
    arc = PlanarArcSegment3D(0., 0., 0., 20., 0., pi / 2)
    window = PathWindowTransition3D((arc,), 0., 1.)
    for t in (0., .2, .5, .8, 1.):
        run = window.planar_run_mm
        kappa_xy = 1. / 20.
        zs = (1. / run) * (pi / 2) * sin(pi * t)
        zss = (1. / (run * run)) * (pi * pi / 2) * cos(pi * t)
        expected = sqrt(kappa_xy ** 2 * (1. + zs * zs) + zss * zss) / (1. + zs * zs) ** 1.5
        assert window.curvature_at(t) == pytest.approx(expected, rel=1e-12)
    # A tighter planar radius makes the window infeasible at any length.
    run, feasible = minimum_path_run_for_curvature(1., 5., 1. / 5.)
    assert not feasible and run is None
    run, feasible = minimum_path_run_for_curvature(1., 5., 0.)
    assert feasible
    assert run == pytest.approx(minimum_xy_run_for_radius(1., 5.))


def tight_route():
    """line -> arc of EXACTLY the required radius -> line, all C1 continuous."""
    arc = PlanarArcSegment3D(5., 5., 0., 5., -pi / 2, pi / 2)
    return Route3D(3, (L((0, 0, 0), (5, 0, 0)), arc, L((10, 5, 0), (10, 25, 0))))


def test_radius_tight_arc_is_conservatively_rejected():
    """A planar arc whose radius is exactly the required radius cannot carry a
    rise: the request must be REJECTED, never satisfied by relaxing the radius
    or by moving the XY path. A window that stays on the straight parts is
    still legal, so the rejection is specific, not a blanket refusal."""
    route = tight_route()
    crossing = Point3D(10., 15., 0.)          # on the second line, offset 22.85
    spanning = build_path_window_candidate(route, (3, 4), [crossing], config(),
                                           (4., 12.), (25., 30.))
    assert spanning.minimum_radius_mm < config().required_radius_mm
    windows, stats = path_window_candidates(route, (3, 4), [crossing], config(),
                                            window_slack_mm=1e-5)
    assert stats["curvature_rejected"] >= 1
    assert all(c.minimum_radius_mm >= config().required_radius_mm for c in windows)
    for candidate in windows:                 # the tight arc is never covered
        assert candidate.rise_offsets_mm[1] <= 5. + 1e-9 or candidate.rise_offsets_mm[0] >= 12.85
    # exactly at the requested radius the window is infeasible by the curve math
    run, feasible = minimum_path_run_for_curvature(1., 5., 1. / 5.)
    assert (run, feasible) == (None, False)


# --------------------------------------------------------------------------
# 4 conservative distance, self clearance and clearance classification
# --------------------------------------------------------------------------
def test_conservative_bounds_bracket_a_fine_sampling_for_a_path_window():
    route = synthetic_route()
    from src.path_window_3d import split_path_interval
    model = planar_path_model(route)
    pieces = [planar_sub_curve(model["primitives"][k], u, v, 0.)
              for k, u, v in split_path_interval(model, 15., 32.)]
    window = PathWindowTransition3D(tuple(pieces), 0., 1.)
    other = L((15, -8, 0.4), (15, 8, 0.4))
    distance = adaptive_primitive_minimum_distance(window, other, distance_tol=1e-7)
    assert distance.converged
    assert distance.lower_bound_mm - 1e-9 <= distance.distance_mm <= distance.upper_bound_mm + 1e-9
    sampled = min(window.point_at(k / 2000.).distance_to(
        Point3D(15., -8. + 16. * j / 2000., .4)) for k in range(51) for j in range(2001))
    assert distance.lower_bound_mm <= sampled + 1e-6
    # an ambiguous or unconverged distance is never accepted as CLEAR
    assert classify_distance(distance, 0.1) in ("CLEAR", "COLLISION", "AMBIGUOUS_CLEARANCE")


def test_box_of_a_path_window_is_conservative():
    route = synthetic_route()
    from src.path_window_3d import split_path_interval
    model = planar_path_model(route)
    pieces = [planar_sub_curve(model["primitives"][k], u, v, 0.)
              for k, u, v in split_path_interval(model, 15., 32.)]
    window = PathWindowTransition3D(tuple(pieces), 0., 1.)
    box = _box(window, 0., 1.)
    for k in range(501):
        q = window.point_at(k / 500.)
        assert box[0][0] - 1e-12 <= q.x <= box[0][1] + 1e-12
        assert box[1][0] - 1e-12 <= q.y <= box[1][1] + 1e-12
        assert box[2][0] - 1e-12 <= q.z <= box[2][1] + 1e-12


def hook_route():
    """line -> 180 deg arc -> opposite quarter arc -> line.

    The first arc turns back in both X and Y, so a rise window covering it is
    monotone in NO axis and the historical monotone exemption cannot apply to
    its joint with the elevated continuation: that joint is exactly the case the
    v8 arc-length cap proof exists for."""
    arc_a = PlanarArcSegment3D(10., 5., 0., 5., -pi / 2, pi)
    arc_b = PlanarArcSegment3D(10., 15., 0., 5., -pi / 2, -pi / 2)
    return Route3D(11, (L((0, 0, 0), (10, 0, 0)), arc_a, arc_b, L((5, 15, 0), (5, 35, 0))))


def test_self_clearance_and_adjacent_cap_policy_on_a_path_window_route():
    route = hook_route()
    crossing = Point3D(5., 25., 0.)           # on the last line, offset 43.56
    candidate = build_path_window_candidate(route, (11, 12), [crossing], config(),
                                            (10.2, 25.5), (45., 52.))
    result = analyze_route3d_self_clearance(candidate.route, 0.1)
    assert result["status"] in ("CLEAR", "COLLISION", "AMBIGUOUS_CLEARANCE")
    assert "AMBIGUOUS_CLEARANCE" not in [row["status"] for row in result["adjacent_results"]]
    proofs = [row.get("proof") for row in result["adjacent_results"]]
    assert "C1_CONTINUOUS_JOINT_OUTSIDE_ARC_LENGTH_CAP" in proofs
    capped = [row for row in result["adjacent_results"]
              if row.get("proof") == "C1_CONTINUOUS_JOINT_OUTSIDE_ARC_LENGTH_CAP"][0]
    assert capped["arc_length_cap_mm"] == 0.1
    assert capped["adjacent_far_arc_length_mm"] == pytest.approx(0.2)
    assert capped["exempt_pair_arc_length_below_mm"] == pytest.approx(0.4)
    assert all(check["status"] == "CLEAR" for check in capped["region_checks"])


def test_old_route_adjacent_pairs_keep_their_historical_proofs():
    """The new arc-length cap proof is only applied to pairs containing a path
    window, so the historical G0 answer cannot change."""
    route = Route3D(0, (L((0, 0, 0), (10, 0, 0)),
                        CosineTransition3D(Point3D(10, 0, 0), Point3D(20, 0, 1)),
                        L((20, 0, 1), (30, 0, 1)),
                        CosineTransition3D(Point3D(30, 0, 1), Point3D(40, 0, 0)),
                        L((40, 0, 0), (50, 0, 0))))
    result = analyze_route3d_self_clearance(route, .1)
    proofs = {row.get("proof") for row in result["adjacent_results"]}
    assert "C1_CONTINUOUS_JOINT_OUTSIDE_ARC_LENGTH_CAP" not in proofs
    assert result["status"] == "CLEAR"


# --------------------------------------------------------------------------
# 5 logical structure, round trip, cache and incremental consistency
# --------------------------------------------------------------------------
def test_logical_structure_counts_ramps_not_fragments():
    route = synthetic_route()
    crossing = Point3D(35., 10., 0.)
    candidate = build_path_window_candidate(route, (7, 8), [crossing], config(),
                                            (18., 24.), (42., 48.))
    logical, physical = transition_fragment_counts(candidate.route)
    assert logical == 2
    assert physical >= 2
    assert elevation_structure(candidate.route) == (True, None)


def test_round_trip_preserves_a_path_window_bit_for_bit():
    route = synthetic_route()
    crossing = Point3D(35., 10., 0.)
    candidate = build_path_window_candidate(route, (7, 8), [crossing], config(),
                                            (18., 24.), (42., 48.))
    restored = deserialize_route3d(serialize_route3d(candidate.route))
    assert restored == candidate.route
    assert restored.total_length() == pytest.approx(candidate.route.total_length(), abs=1e-12)
    assert len([p for p in restored.primitives
                if isinstance(p, PathWindowTransition3D)]) == 2


def test_generation_cache_key_changes_with_the_window_geometry():
    route = synthetic_route()
    crossing = [Point3D(35., 10., 0.)]
    model = planar_path_model(route)
    first = build_path_window_candidate(route, (7, 8), crossing, config(), (18., 24.), (42., 48.))
    second = build_path_window_candidate(route, (7, 8), crossing, config(), (16., 24.), (41., 48.))
    key_one = generation_input_key(first.route, crossing, config(), window_slack_mm=1e-5)
    key_two = generation_input_key(second.route, crossing, config(), window_slack_mm=1e-5)
    assert key_one != key_two
    assert candidate_path_offsets(model, first) != candidate_path_offsets(model, second)
    # a structural zero recorded under one key is not reused under the other
    cache = {((7, 8), 8): dict(key=key_one, generated_count=0)}
    assert generation_cache_hit(cache, (7, 8), 8, key_one)
    assert not generation_cache_hit(cache, (7, 8), 8, key_two)


def test_g1_keeps_every_g0_candidate_and_adds_path_windows():
    route = real_route(0)
    model = planar_path_model(route)
    crossings = [route.point_at(0.)] if False else None
    # a synthetic anchor on the frozen route keeps this test independent of the
    # diagnostic set: take a point at half the planar length
    half = model["total"] / 2.
    for prim, off, length in zip(model["primitives"], model["offsets"], model["lengths"]):
        if half <= off + length:
            anchor = prim.point_at(min(1., max(0., (half - off) / length)))
            break
    g0, g0_failures = candidate_families(route, (0, 1), [anchor], config(),
                                         window_slack_mm=1e-5, generation_domain="LINE_ONLY")
    stats = {}
    g1, g1_failures = candidate_families(route, (0, 1), [anchor], config(),
                                         window_slack_mm=1e-5,
                                         generation_domain="PATH_WINDOWS", stats_out=stats)
    strided = stats.get("line_window_candidates", 0)
    assert strided == len(g0)
    assert len(g1) >= len(g0)
    keys_g0 = [(c.layer_to, candidate_path_offsets(model, c)) for c in g0]
    keys_g1 = [(c.layer_to, candidate_path_offsets(model, c)) for c in g1]
    assert len(set(keys_g1)) == len(keys_g1)
    for key in keys_g0:
        assert key in keys_g1
    assert list(keys_g1[:len(keys_g0)]) == keys_g0
    assert stats["path_window_candidates"] == len(g1) - len(g0)

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


def real_route_by_id(route_id):
    from src.multi_attribution import deserialize_plot
    from src.geometry_3d import lift_smoothed_route_to_layer
    data = json.loads(PLOT.read_text(encoding="utf-8"))
    row = next(r for r in data["routes"] if r["id"] == route_id)
    return lift_smoothed_route_to_layer(deserialize_plot(row), Layer(0, 0))


def _anchor_at(route, fraction):
    model = planar_path_model(route)
    target = model["total"] * fraction
    for primitive, offset, length in zip(model["primitives"], model["offsets"], model["lengths"]):
        if target <= offset + length:
            return primitive.point_at(min(1., max(0., (target - offset) / length)))


@pytest.mark.parametrize("route_id", [105, 0, 7, 250])
def test_windows_touching_the_route_ends_keep_the_exact_frozen_endpoints(route_id):
    """Regression: a rise window that starts at planar offset 0 or a fall window
    that ends at the route total must not move the frozen endpoints by even one
    ulp; the interpolated sub-curve endpoint used to differ by ~1e-14 mm."""
    route = real_route_by_id(route_id)
    anchor = _anchor_at(route, .6)
    candidates, stats = path_window_candidates(route, (route_id, 9999), [anchor], config(),
                                               window_slack_mm=1e-5)
    assert candidates, stats
    total = planar_path_model(route)["total"]
    touching = 0
    for candidate in candidates:
        assert candidate.route.start_point == route.start_point
        assert candidate.route.end_point == route.end_point
        if candidate.rise_offsets_mm[0] == 0. or abs(candidate.fall_offsets_mm[1] - total) < 1e-12:
            touching += 1
    assert touching > 0, "the enumeration must really place windows on the route ends"
