"""Small explicit-state fixtures for read-only Dynamic-D diagnostics."""
from copy import deepcopy
from math import isclose, sqrt

from src.hierarchy_diagnostic import diagnose_dynamic_d, continuous_hierarchy_diagnostic
from src.models import PMT, Point2D, Port, Waveguide
from src.router_2d import prepare_waveguide_2d, _algorithmic_endpoints

PENDING = "pending_for_horizontal_routing"


def fixture(category="top-U"):
    terminal_y = 150.0 if category in ("top-U", "bottom->top Z") else 0.0
    other_y = 150.0 - terminal_y
    start_y = terminal_y if category.endswith("-U") else other_y
    start_pmt = 100 if category.endswith("-U") else 1
    routes = []
    def add(rid, pa, xa, ya, pb, xb, yb):
        w = Waveguide(rid, Port(2*rid, pa, None, Point2D(xa, ya)),
                      Port(2*rid+1, pb, None, Point2D(xb, yb)))
        routes.append(w)
        return w
    current = add(1, start_pmt, 0, start_y, 5, 20, terminal_y)
    add(2, 900, 18, terminal_y, 1000, 60, other_y)
    add(3, 900, 17.5, terminal_y, 1000, 61, other_y)
    add(4, 7, 22, terminal_y, 1000, 62, other_y)
    add(5, 7, 22.5, terminal_y, 1000, 63, other_y)
    groups = {}
    for w in routes:
        for p in (w.start_port, w.end_port):
            groups.setdefault(p.pmt_id, []).append(p)
    preparation = prepare_waveguide_2d(current, 150, 0)
    return dict(waveguide=current, preparation=preparation,
                algorithmic_endpoints=_algorithmic_endpoints(current, preparation, 1e-9),
                pmts=[PMT(pid, ports) for pid, ports in groups.items()],
                waveguides=routes, route_statuses={w.id: PENDING for w in routes},
                commit_prefix=[], special_route_ids=frozenset())


def run(f=None):
    return diagnose_dynamic_d(**(fixture() if f is None else f))


def test_top_middle_both_neighbors():
    d = run()
    assert d["left"]["neighbor_pmt"] == 900
    assert d["right"]["neighbor_pmt"] == 7
    assert d["xt"] == 20 and d["dangerous_side"] == "UNCONFIRMED"


def test_bottom_middle_neighbors():
    d = run(fixture("bottom-U"))
    assert d["terminal_side"] == "bottom"
    assert d["left"]["neighbor_pmt"] == 900 and d["right"]["neighbor_pmt"] == 7
    assert d["current_scan_direction"] == "ascending"


def test_leftmost_no_adjacent():
    f = fixture("top->bottom Z")
    # Move current terminal PMT left of both same-side neighbors.
    f["waveguide"].end_port.position.x = -20
    d = run(f)
    assert d["left"]["status"] == "NO_ADJACENT"
    assert d["left"]["nearest_distance"] is None


def test_rightmost_no_adjacent():
    f = fixture()
    f["waveguide"].end_port.position.x = 40
    d = run(f)
    assert d["right"]["status"] == "NO_ADJACENT"
    assert d["right"]["continuous"] is None


def test_left_no_pending():
    f = fixture()
    f["route_statuses"].update({2: "committed", 3: "committed"})
    f["commit_prefix"] = [2, 3]
    assert run(f)["left"]["status"] == "NO_PENDING"


def test_right_no_pending():
    f = fixture()
    f["route_statuses"].update({4: "failed_uncommitted", 5: "failed_uncommitted"})
    assert run(f)["right"]["status"] == "NO_PENDING"


def test_both_no_pending():
    f = fixture()
    for rid in (2, 3, 4, 5):
        f["route_statuses"][rid] = "failed_uncommitted"
    d = run(f)
    assert d["left"]["status"] == d["right"]["status"] == "NO_PENDING"
    assert d["left"]["nearest_distance"] is d["right"]["nearest_distance"] is None


def test_unique_nearest_hand_computed():
    d = run()
    assert d["left"]["nearest_distance"] == 2.0
    assert [c["route_id"] for c in d["left"]["nearest_candidates"]] == [2]
    assert d["right"]["nearest_distance"] == 2.0


def test_tie_preserves_all_routes():
    f = fixture()
    f["waveguides"][2].start_port.position.x = 18
    d = run(f)["left"]
    assert d["status"] == "TIE_NEAREST"
    assert [c["route_id"] for c in d["nearest_candidates"]] == [2, 3]


def test_noncontiguous_ids_not_numeric_adjacency():
    d = run()
    assert d["end_pmt"] == 5
    assert (d["left"]["neighbor_pmt"], d["right"]["neighbor_pmt"]) == (900, 7)


def test_local_id_none_preserved():
    d = run()
    assert d["algorithmic_end_endpoint"]["local_id"] is None
    assert all(c["local_id"] is None for c in d["left"]["pending_candidates"])


def test_same_pmt_pair_independent_routes():
    d = run()["left"]
    assert [c["route_id"] for c in d["pending_candidates"]] == [3, 2]
    assert len({c["port_id"] for c in d["pending_candidates"]}) == 2


def test_committed_exclusion_and_state_transition():
    f = fixture()
    before = deepcopy(f)
    assert run(f)["left"]["nearest_candidates"][0]["route_id"] == 2
    assert f == before
    f["route_statuses"][2] = "committed"
    f["commit_prefix"] = [2]
    state_b = deepcopy(f)
    d = run(f)["left"]
    assert [c["route_id"] for c in d["pending_candidates"]] == [3]
    assert d["nearest_distance"] == 2.5 and f == state_b
    assert f["waveguides"] == before["waveguides"] and f["pmts"] == before["pmts"]


def test_failed_uncommitted_exclusion():
    f = fixture()
    f["route_statuses"][2] = "failed_uncommitted"
    d = run(f)["left"]
    assert d["pending_count"] == 1
    assert d["excluded_candidates"][0]["exclusion"] == "failed_uncommitted"


def test_special_neighbor_separate_even_if_explicitly_pending():
    f = fixture()
    f["special_route_ids"] = frozenset({2})
    d = run(f)["left"]
    assert [c["route_id"] for c in d["unsupported_related_routes"]] == [2]
    assert [c["route_id"] for c in d["pending_candidates"]] == [3]


def test_unsupported_neighbor_separate():
    f = fixture()
    f["route_statuses"][2] = "unsupported"
    assert run(f)["left"]["unsupported_related_routes"][0]["route_id"] == 2


def test_current_special_not_diagnosed():
    f = fixture("top->bottom Z")
    f["special_route_ids"] = frozenset({1})
    d = run(f)
    assert d["status"] == "UNSUPPORTED_GEOMETRY_FOR_HIERARCHY_DIAGNOSTIC"
    assert d["left"] is d["right"] is None


def test_undeclared_short_z_not_silently_pending():
    f = fixture("top->bottom Z")
    f["waveguide"].end_port.position.x = 5
    assert run(f)["status"] == "UNSUPPORTED_GEOMETRY_FOR_HIERARCHY_DIAGNOSTIC"


def test_formula_hand_computed():
    # D=2.125 -> r+s-D=3 -> sqrt(25-9)=4 -> L=1.
    d = continuous_hierarchy_diagnostic(2.125)
    assert d["status"] == "OK" and d["L_mm"] == 1
    assert d["paper_ratio"] == 8
    assert isclose(d["project_pitch_ratio"], 40 / 7)


def test_formula_invalid_branch_and_nonfinite():
    for distance in (-1, 0, 0.124, 5.126, 10, float("nan"), float("inf")):
        d = continuous_hierarchy_diagnostic(distance)
        assert d["status"] == "OUT_OF_FORMULA_DOMAIN"
        assert d["L_mm"] is d["paper_ratio"] is d["project_pitch_ratio"] is None


def test_formula_boundary_values():
    assert continuous_hierarchy_diagnostic(0.125)["L_mm"] == 5
    assert continuous_hierarchy_diagnostic(5.125)["L_mm"] == 0


def test_neighbor_formula_matches_hand_value():
    d = run()["left"]["continuous"]
    expected = 5 - sqrt(25 - 3.125**2)
    assert isclose(d["L_mm"], expected)
    assert isclose(d["paper_ratio"], expected / 0.125)
    assert isclose(d["project_pitch_ratio"], expected / 0.175)


def test_no_integer_k_or_assignment_output():
    def visit(value):
        if isinstance(value, dict):
            assert not {"K", "k", "track_index", "assignment", "occupancy"} & set(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child)
    visit(run())


def test_four_categories_scans_and_terminal_mapping():
    for category, scan, side in (
        ("top-U", "descending", "top"), ("bottom-U", "ascending", "bottom"),
        ("top->bottom Z", "descending", "bottom"),
        ("bottom->top Z", "descending", "top"),
    ):
        d = run(fixture(category))
        assert d["status"] == "OK" and d["category"] == category
        assert d["current_scan_direction"] == scan and d["terminal_side"] == side
        assert d["terminal_mapping_status"] == "CURRENT_PROJECT_ENDPOINT_VIEW"
        assert d["xt"] == 20 and d["left"]["nearest_distance"] == 2


def test_z_paper_differences_explicit():
    d = run(fixture("top->bottom Z"))
    assert d["paper_scan_differs"] and d["paper_scan_direction"] == "ascending"
    assert d["paper_primary_order"] == "descending" and d["current_primary_order"] == "ascending"


def test_current_route_excluded_from_neighbor():
    f = fixture("top-U")
    # Current start PMT becomes immediate left neighbor of its terminal.
    f["waveguides"][1].start_port.position.x = -10
    f["waveguides"][2].start_port.position.x = -11
    d = run(f)["left"]
    assert d["neighbor_pmt"] == 100 and d["status"] == "NO_PENDING"
    assert d["excluded_candidates"][0]["exclusion"] == "CURRENT_ROUTE"


def test_readonly_all_inputs_and_detached_output():
    f = fixture()
    before = deepcopy(f)
    d = run(f)
    d["algorithmic_end_endpoint"]["x"] = -999
    d["left"]["pending_candidates"][0]["x"] = -999
    assert f == before


def test_determinism_and_catalog_permutation():
    f = fixture()
    first = run(f)
    f["pmts"].reverse()
    f["waveguides"].reverse()
    for pmt in f["pmts"]:
        pmt.ports.reverse()
    assert run(f) == first


def test_incomplete_state_rejected():
    f = fixture()
    del f["route_statuses"][2]
    assert run(f)["status"] == "AMBIGUOUS"


def test_commit_prefix_inconsistent_rejected():
    f = fixture()
    f["commit_prefix"] = [2]
    assert run(f)["status"] == "AMBIGUOUS"


def test_duplicate_prefix_rejected():
    f = fixture()
    f["route_statuses"][2] = "committed"
    f["commit_prefix"] = [2, 2]
    assert run(f)["status"] == "AMBIGUOUS"


def test_missing_endpoint_explicit():
    f = fixture()
    f["waveguides"][1].start_port.position = None
    assert run(f)["status"] == "MISSING_ENDPOINT"


def test_invalid_side_explicit():
    f = fixture()
    f["waveguides"][1].start_port.position.y = 50
    assert run(f)["status"] == "INVALID_SIDE"


def test_overlapping_pmt_ranges_ambiguous():
    f = fixture()
    f["waveguides"][1].start_port.position.x = 21
    assert run(f)["status"] == "AMBIGUOUS"


def test_wrong_algorithmic_view_rejected():
    f = fixture()
    f["algorithmic_endpoints"] = tuple(reversed(f["algorithmic_endpoints"]))
    assert run(f)["status"] == "AMBIGUOUS"


def test_unknown_state_rejected():
    f = fixture()
    f["route_statuses"][2] = "pending"
    assert run(f)["status"] == "AMBIGUOUS"


def test_neighbor_out_of_domain_keeps_actual_distance():
    f = fixture()
    f["waveguides"][3].start_port.position.x = 30
    f["waveguides"][4].start_port.position.x = 31
    d = run(f)["right"]
    assert d["status"] == "OK" and d["nearest_distance"] == 10
    assert d["continuous"]["status"] == "OUT_OF_FORMULA_DOMAIN"


def test_current_failed_is_not_silently_retried():
    f = fixture()
    f["route_statuses"][1] = "failed_uncommitted"
    assert run(f)["status"] == "AMBIGUOUS"
