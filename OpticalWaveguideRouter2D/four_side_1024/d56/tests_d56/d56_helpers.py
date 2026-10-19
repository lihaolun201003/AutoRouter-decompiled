"""Shared builders for the independent D56 validator test suite.

Every geometry helper keeps the D56 contract: lines are exactly horizontal or
vertical, arcs have radius 5.0, and non-quarter arcs use the original AutoRouter
small-displacement short-S formula ``theta = acos(1 - d/(2R))`` with
``h = R*sin(theta)``.  ``build_legacy_route`` uses the accepted legacy
constructors (``four_side_1024.legacy_geometry.opposite/adjacent`` + the four-side
rigid frames), which is exactly the geometry class the router is allowed to emit.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024 import inputs, legacy_geometry

RADIUS = 5.0
CLEARANCE = 0.175

LEGACY_80 = ROOT / "outputs/four_side_1024_legacy_two_branch_v2/routes_geometry.json"
LEGACY_80_STATS = ROOT / "outputs/four_side_1024_legacy_two_branch_v2/statistics.json"
FREE_526 = ROOT / "outputs/four_side_1024_single_layer_v1/routes_geometry.json"
REAL_D56_RUN = ROOT / "outputs/four_side_1024_d56_optimized/routes.json"

# A track in the middle of the board fits both legacy templates for every
# canonical side pair; the direct-L adjacent interface uses the exact target y.
TRACK_CHOICES = (75.0, 70.0, 80.0, 65.0, 85.0, 60.0, 90.0, 55.0, 95.0,
                 45.0, 105.0, 40.0, 110.0)


# ---------------------------------------------------------------------------
# Primitive builders
# ---------------------------------------------------------------------------
def line(p0, p1, layer=0):
    return {"kind": "line", "p0": [float(p0[0]), float(p0[1])],
            "p1": [float(p1[0]), float(p1[1])], "layer": int(layer)}


def arc(center, radius, start_angle, sweep, p0=None, p1=None, layer=0):
    """Build a self-consistent arc primitive from center/radius/angle/sweep."""
    cx, cy = float(center[0]), float(center[1])
    radius = float(radius)
    if p0 is None:
        p0 = (cx + radius * math.cos(start_angle), cy + radius * math.sin(start_angle))
    if p1 is None:
        p1 = (cx + radius * math.cos(start_angle + sweep),
              cy + radius * math.sin(start_angle + sweep))
    return {"kind": "arc", "p0": [float(p0[0]), float(p0[1])],
            "p1": [float(p1[0]), float(p1[1])], "center": [cx, cy],
            "radius": radius, "start_angle": float(start_angle),
            "sweep": float(sweep), "layer": int(layer)}


def arc_chain(start, heading, sweeps, radius=RADIUS):
    """Chain arcs with the given signed sweeps, staying G1-continuous.

    ``heading`` is the travel direction at ``start`` in radians.  A positive
    sweep turns left (centre on the left of travel); a negative sweep turns
    right.  This reproduces the original construction used for the short S.
    """
    primitives = []
    cursor = (float(start[0]), float(start[1]))
    current = float(heading)
    for sweep in sweeps:
        sign = 1.0 if sweep > 0 else -1.0
        center = (cursor[0] - sign * radius * math.sin(current),
                  cursor[1] + sign * radius * math.cos(current))
        start_angle = current - sign * math.pi / 2.0
        end = (center[0] + radius * math.cos(start_angle + sweep),
               center[1] + radius * math.sin(start_angle + sweep))
        primitives.append(arc(center, radius, start_angle, sweep, p0=cursor, p1=end))
        cursor = end
        current += sweep
    return primitives, cursor, current


def short_s_route(displacement, start=(10.0, 10.0), lead=5.0, tail=30.0,
                  radius=RADIUS):
    """Original AutoRouter small-displacement short S for ``0 < d < 2R``.

    The two arcs keep radius R and use ``sweep = +theta / -theta`` with
    ``theta = acos(1 - d/(2R))``, exactly as ``wiring_bend_826`` does; there is
    no straight between the arcs.  Returns ``(primitives, source, target, theta)``.
    """
    if not 0.0 < displacement < 2.0 * radius:
        raise ValueError("short-S displacement must satisfy 0 < d < 2R")
    theta = math.acos(1.0 - displacement / (2.0 * radius))
    x0, y0 = float(start[0]), float(start[1])
    tail_primitives, end, _ = arc_chain((x0, y0), math.pi / 2.0, [theta, -theta], radius)
    primitives = [line((x0, y0 - lead), (x0, y0))] + tail_primitives
    primitives.append(line(end, (end[0], end[1] + tail)))
    source = {"routing_xy": [x0, y0 - lead], "inward": [0.0, 1.0]}
    target = {"routing_xy": [end[0], end[1] + tail], "inward": [0.0, -1.0]}
    return primitives, source, target, theta


# ---------------------------------------------------------------------------
# Four-side dataset helpers
# ---------------------------------------------------------------------------
def load_dataset():
    rows, endpoints, connectors, validation = inputs.load()
    return {"rows": rows, "endpoints": endpoints, "connectors": connectors,
            "validation": validation, "by_id": {row["route_id"]: row for row in rows}}


def first_row_per_side_pair(rows):
    """First CSV connection for each ordered (source_side, target_side) pair."""
    seen = set()
    result = []
    for row in rows:
        key = (row["source_side"], row["target_side"])
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def canonical_row(row, endpoints):
    source = endpoints[row["source_endpoint"]]
    target = endpoints[row["target_endpoint"]]
    p, q, transform, kind = legacy_geometry.canonicalize(
        row["source_side"], row["target_side"],
        source["routing_xy"], target["routing_xy"])
    return p, q, transform, kind, source, target


def build_legacy_route(row, endpoints, track=None):
    """Generate one D56 route with the accepted legacy constructors.

    ``track`` overrides the automatically selected legacy track.  Returns
    ``(primitives, source, target, meta)``; raises ``ValueError`` when the
    requested track cannot host the fixed-radius template.
    """
    p, q, transform, kind, source, target = canonical_row(row, endpoints)
    candidates = []
    if track is not None:
        candidates.append(float(track))
    else:
        if kind == "adjacent":
            candidates.append(float(q[1]))  # direct single-L interface
        candidates.extend(TRACK_CHOICES)
    last_error = None
    for candidate in candidates:
        try:
            if kind == "opposite":
                local = legacy_geometry.opposite(p, q, candidate, radius=RADIUS)
            else:
                local = legacy_geometry.adjacent(p, q, candidate, radius=RADIUS)
        except ValueError as exc:
            last_error = exc
            continue
        primitives = legacy_geometry.transform_primitives(local, transform, inverse=True)
        meta = {"kind": kind, "track_mm": candidate, "row": row}
        return primitives, source, target, meta
    raise ValueError(f"No legacy geometry for route {row['route_id']}: {last_error}")


def build_generated_route_for_row(row, endpoints, track=None):
    """Alias of ``build_legacy_route`` for one explicit CSV row."""
    return build_legacy_route(row, endpoints, track=track)


def build_generated_routes():
    """One generated D56 route per ordered side pair, plus adjacent variants."""
    dataset = load_dataset()
    endpoints = dataset["endpoints"]
    generated = []
    for row in first_row_per_side_pair(dataset["rows"]):
        primitives, source, target, meta = build_legacy_route(row, endpoints)
        generated.append({"label": f"{row['source_side']}->{row['target_side']}",
                          "route_id": row["route_id"], "row": row,
                          "primitives": primitives, "source": source,
                          "target": target, "meta": dict(meta, variant="primary")})
        if meta["kind"] == "adjacent":
            # The adjacent adapter has two legal D56 interfaces: the direct
            # single-L and the three-bend orthogonal terminal template.
            try:
                alternative = build_legacy_route(row, endpoints, track=75.0)
            except ValueError:
                alternatives = []
            else:
                primitives2, source2, target2, meta2 = alternative
                generated.append({"label": f"{row['source_side']}->{row['target_side']}",
                                  "route_id": row["route_id"], "row": row,
                                  "primitives": primitives2, "source": source2,
                                  "target": target2,
                                  "meta": dict(meta2, variant="three_bend")})
    return generated


def load_legacy_80():
    """The 80 accepted D56 routes of the historical legacy baseline."""
    dataset = load_dataset()
    endpoints = dataset["endpoints"]
    payload = json.loads(LEGACY_80.read_text(encoding="utf-8"))
    result = []
    for record in payload["routes"]:
        source = endpoints[record["source_endpoint"]]
        target = endpoints[record["target_endpoint"]]
        result.append({"route_id": record["route_id"], "record": record,
                       "primitives": record["primitives"],
                       "source": source, "target": target})
    return result


def load_free_526():
    """The 526 free-curve (F56/Dubins) routes of the historical experiment.

    ``routes_geometry.json`` does not repeat endpoint identities, so they are
    resolved from the sibling ``routes.json`` by route id (validator helper).
    """
    from four_side_1024.d56 import validate_d56 as V

    dataset = load_dataset()
    records, _ = V.load_routes_file(FREE_526)
    result = []
    for record in records:
        source = dataset["endpoints"].get(record.get("_source_endpoint"))
        target = dataset["endpoints"].get(record.get("_target_endpoint"))
        result.append({"route_id": record["route_id"], "record": record,
                       "primitives": record["primitives"],
                       "source": source, "target": target})
    return result


def spec_routes_payload(route_records):
    """Wrap routed/failed records in the SPEC ``routes.json`` schema."""
    return {
        "schema": "four_side_1024_d56_optimized_routes_v1",
        "units": "mm",
        "layer": 0,
        "endpoint_mode": "virtual_unfolded",
        "config": {"min_radius_mm": RADIUS, "width_mm": 0.05,
                   "edge_gap_mm": 0.125, "sagitta_mm": 0.0005},
        "algorithm": {"name": "test-fixture"},
        "routes": route_records,
    }


def routed_record(route_id, primitives, source_endpoint, target_endpoint,
                  relation=None):
    record = {"route_id": route_id, "status": "routed", "layer": 0,
              "source_endpoint": source_endpoint,
              "target_endpoint": target_endpoint,
              "primitives": primitives}
    if relation is not None:
        record["relation"] = relation
    return record


def failed_record(route_id, source_endpoint, target_endpoint, reason="no_legal_candidate"):
    return {"route_id": route_id, "status": "failed", "layer": 0,
            "source_endpoint": source_endpoint,
            "target_endpoint": target_endpoint,
            "reason": reason}
