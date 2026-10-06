

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
