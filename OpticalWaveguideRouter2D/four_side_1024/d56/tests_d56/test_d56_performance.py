"""Performance guard: a full 1024-route independent audit must fit the budget.

The SPEC requires the full independent audit of 1024 routes to finish in about
two minutes.  This test uses a synthetic 1024-route orthogonal dataset whose
worst-case interaction pattern is extreme: 512 vertical and 512 horizontal
full-board lines produce 262 144 legal 90-degree crossings, i.e. every one of
the 262 144 broad-phase candidate pairs must be exactly audited end to end.
"""
from __future__ import annotations

import time

import pytest

from d56_helpers import line
from four_side_1024.d56 import validate_d56 as V

BUDGET_SECONDS = 120.0
ROUTE_COUNT = 1024


def _synthetic_orthogonal_routes():
    prepared = []
    route_id = 1
    for index in range(512):
        x = 0.15 + 0.29 * index
        prepared.append(V.prepare_route(
            [line((x, 0.0), (x, 150.0))], route_id))
        route_id += 1
    for index in range(512):
        y = 0.15 + 0.29 * index
        prepared.append(V.prepare_route(
            [line((0.0, y), (150.0, y))], route_id))
        route_id += 1
    return prepared


def test_full_1024_route_audit_under_two_minutes():
    prepared = _synthetic_orthogonal_routes()
    assert len(prepared) == ROUTE_COUNT
    started = time.perf_counter()
    audit = V.audit_route_pairs(prepared)
    elapsed = time.perf_counter() - started
    assert audit["candidate_pair_count"] == 512 * 512
    assert audit["crossing_count"] == 512 * 512
    assert audit["crossing_pair_count"] == 512 * 512
    assert audit["crossing_angle_histogram"]["75-90"] == 512 * 512
    assert audit["violations"] == []
    assert elapsed < BUDGET_SECONDS, (
        f"full 1024-route audit took {elapsed:.1f}s > {BUDGET_SECONDS:.0f}s")
    print(f"\n1024-route audit: {elapsed:.2f}s, "
          f"{audit['crossing_count']} crossings")


def test_1024_single_route_checks_are_fast():
    """1024 single-route D56 checks stay far below the pair-audit budget."""
    routes = []
    for index in range(512):
        x = 0.15 + 0.29 * index
        routes.append([line((x, 0.15), (x, 149.85))])
    for index in range(512):
        y = 0.15 + 0.29 * index
        routes.append([line((0.15, y), (149.85, y))])
    started = time.perf_counter()
    passed = 0
    for primitives in routes:
        result = V.check_route_primitives(primitives)
        if result["passed"]:
            passed += 1
    elapsed = time.perf_counter() - started
    assert passed == 1024
    assert elapsed < 30.0
    print(f"\n1024 single-route checks: {elapsed:.2f}s")
