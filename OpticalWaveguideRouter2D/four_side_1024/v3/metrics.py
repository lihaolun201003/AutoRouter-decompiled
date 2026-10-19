"""V3-Huang 1024-channel dual-height metrics: class/shape/U/refold statistics.

Round-3 deliverable for ``four_side_1024/v3/SPEC.md`` (§7 artifacts, §2 topology,
§4 geometry families, §8 honesty rules).  Reuses the proven FSLW measurement
helpers (``four_side_1024.fslw.metrics``) for primitive geometry, strict crossing
re-computation, nearest-gap quality, propagation loss and audit merging; the V3
specific layer added here is:

* **class statistics** -- same / opposite / adjacent routed counts and rates,
  plus NN/SS/EE/WW/NS/EW/NE/NW/ES/SW pair counts, checked against the frozen
  ``v3/ports.py`` identity metadata (never inferred from the row number);
* **path-shape classification from saved primitives only** (SPEC §4) --
  ``straight / short_S / L / U / multi_bend_refold / other``; the relation label
  is never used for the shape;
* **U/refold statistics** -- U depth distribution, track counts, U nesting
  (ordered nested groups per side), adjacent-U spacing, bundle/arch grouping and
  refold-region congestion, all computed from the saved world-mm primitives;
* **failure taxonomy** -- ``no_candidate_generated`` vs ``no_legal_candidate``
  vs budget/other, with the SPEC §8 (A)/(B)/(C) honesty interpretation;
* standard quality metrics (lengths, bends, detours, crossings, violations from
  the authoritative ``audit_strict.json`` with a stale-file guard, propagation
  loss only; bend/crossing loss stay ``unknown_uncalibrated``).

Combined (two physical heights) statistics are produced for
``combined/<A>/statistics.json``; same-plane crossings are kept strictly
separate from the informational ``cross_plane_projected_overlap``.

CLI
---
    .venv\\Scripts\\python.exe -m four_side_1024.v3.metrics --run-dir \\
        outputs/four_side_1024_v3_huang_R40_gap30_abcd/planes/B/z1
    .venv\\Scripts\\python.exe -m four_side_1024.v3.metrics --combined-dir \\
        outputs/four_side_1024_v3_huang_R40_gap30_abcd/combined/B --root <root>
    .venv\\Scripts\\python.exe -m four_side_1024.v3.metrics --shapes --root <root>
"""
from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter, OrderedDict
from pathlib import Path

import numpy as np

from .. import geometry as geom
from ..d56 import validate_d56 as d56_validator
from ..fslw import config as fslw_config
from ..fslw import metrics as fm
from . import config as v3_config

try:  # frozen Lead-authored V3 port model
    from . import ports as v3_ports
except Exception:  # pragma: no cover - reported instead of guessed
    v3_ports = None

SCHEMA_PLANE = "four_side_1024_v3_plane_statistics_v1"
SCHEMA_COMBINED = "four_side_1024_v3_combined_statistics_v1"
SCHEMA_SHAPES = "four_side_1024_v3_shapes_statistics_v1"
TOOL = "four_side_1024.v3.metrics"

PLANES = tuple(getattr(v3_config, "PLANES", ("z1", "z2")))
ALGORITHMS = tuple(getattr(v3_config, "ALGORITHMS", ("A", "B", "C", "D")))
CLASSES = ("same", "opposite", "adjacent")
PAIR_ORDER = ("NN", "SS", "EE", "WW", "NS", "EW", "NE", "NW", "ES", "SW")
CLASS_PAIRS = OrderedDict((
    ("same", ("NN", "SS", "EE", "WW")),
    ("opposite", ("NS", "EW")),
    ("adjacent", ("NE", "NW", "ES", "SW")),
))
PAIR_CLASS = {pair: relation for relation, pairs in CLASS_PAIRS.items()
              for pair in pairs}
REQUIRED_SHAPES = ("straight", "short_S", "L", "U", "multi_bend_refold", "other")
CLASS_EXPECTED = dict(v3_config.EXPECTED["relation_counts"])
PAIR_EXPECTED = dict(v3_config.EXPECTED["pair_counts"])
PLANE_EXPECTED = {plane: dict(values)
                  for plane, values in v3_config.EXPECTED["planes"].items()}
CONNECTIONS_PER_PLANE = 512
TOTAL_CONNECTIONS = 1024
CLEARANCE_MM = float(getattr(v3_config, "CLEARANCE_MM",
                             fslw_config.CLEARANCE_MM))
RADIUS_MM = float(getattr(v3_config, "RADIUS_MM", fslw_config.RADIUS_MM))
GRID_MM = 5.0
TRACK_MIN_LENGTH_MM = 0.5
BUNDLE_DEPTH_TOL_MM = 0.16          # 2 x clearance: same bundle/arch track band
NESTING_TOL_MM = 1e-6
SHAPE_DEFINITIONS = {
    "straight": "no arcs; all straight primitives collinear (single straight run)",
    "short_S": "exactly one historical short-S pair (two reverse theta arcs, "
               "theta=acos(1-d/(2R))) and no quarter arcs",
    "L": "exactly one quarter arc (90 deg) plus straight primitives",
    "U": "one net 180-degree turn inside the board: 'wide_U' (two quarter arcs "
         "with straight primitives between), 'hairpin' (two consecutive quarter "
         "arcs, no straight between), or 'hairpin_short_S' (SAME_HAIRPIN_A/B: "
         "one hairpin plus one historical short-S lateral shift, still a single "
         "180-degree same-side U path)",
    "multi_bend_refold": "more than two effective bends: three or more quarter "
                         "arcs, two or more hairpins, or a short-S combined with "
                         "additional quarter arcs (folded/refold path)",
    "other": "anything that does not match the families above; in V3 this is "
             "the two-quarter step transfer (two quarter arcs with opposite "
             "sweeps, net turn 0 deg, the FSLW opposite-side 'U' transfer "
             "family), kept as 'other' because the required taxonomy has no "
             "step class and 'U' is reserved for net-180-degree U/hairpin paths",
}
SIDE_GEOM = {
    "N": dict(edge_value=150.0, inward=(0.0, -1.0), along=0, normal=1,
              depth_value=150.0),
    "S": dict(edge_value=0.0, inward=(0.0, 1.0), along=0, normal=1,
              depth_value=0.0),
    "E": dict(edge_value=150.0, inward=(-1.0, 0.0), along=1, normal=0,
              depth_value=150.0),
    "W": dict(edge_value=0.0, inward=(1.0, 0.0), along=1, normal=0,
              depth_value=0.0),
}


# ---------------------------------------------------------------------------
# generic helpers (reused from the FSLW measurement layer)
# ---------------------------------------------------------------------------
def _json_safe(value):
    return fm._json_safe(value)


def _load_json(path):
    return fm._load_json(path)


def _sha256(path):
    return fm._sha256(path)


def _number(value):
    return fm._number(value)


def _first(mapping, keys, default=None):
    return fm._first(mapping, keys, default)


def _round(value, digits=6):
    return fm._round(value, digits)


def _mean(values):
    values = [value for value in values if value is not None]
    return (sum(values) / len(values)) if values else None


def _median(values):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    middle = len(values) // 2
    return (values[middle] if len(values) % 2
            else 0.5 * (values[middle - 1] + values[middle]))


def _percentiles(values, points=(25, 50, 75, 90, 99)):
    values = [float(value) for value in values if value is not None]
    if not values:
        return {f"p{point}": None for point in points}
    return {f"p{point}": float(np.percentile(values, point)) for point in points}


def _std(values):
    values = [float(value) for value in values if value is not None]
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def _plane_run_dir(root, algorithm, plane):
    return Path(root) / "planes" / algorithm / plane


def _combined_run_dir(root, algorithm):
    return Path(root) / "combined" / algorithm


def iter_plane_runs(root):
    root = Path(root)
    for algorithm in ALGORITHMS:
        for plane in PLANES:
            run_dir = _plane_run_dir(root, algorithm, plane)
            if (run_dir / "routes.json").exists():
                yield algorithm, plane, run_dir


def iter_combined_runs(root):
    root = Path(root)
    for algorithm in ALGORITHMS:
        combined_dir = _combined_run_dir(root, algorithm)
        if (combined_dir / "routes_1024.json").exists() or \
                (combined_dir / "statistics.json").exists():
            yield algorithm, combined_dir


# ---------------------------------------------------------------------------
# ports / process / route metadata
# ---------------------------------------------------------------------------
def load_plane_ports(plane):
    """Frozen V3 port model: endpoints + connectors + identity metadata."""
    if v3_ports is not None:
        try:
            routes, endpoints, connectors, validation = v3_ports.load_plane(plane)
            return {"routes": routes, "endpoints": endpoints,
                    "connectors": connectors, "validation": validation,
                    "source": "four_side_1024.v3.ports.load_plane"}
        except Exception as exc:  # noqa: BLE001 - reported, never guessed
            error = f"{type(exc).__name__}: {exc}"
    else:
        error = "v3/ports.py unavailable"
    return {"routes": None, "endpoints": None, "connectors": None,
            "validation": None, "error": error}


def load_process(routes_meta=None, config_payload=None, run_dir=None):
    """V3 process convention (identical to FSLW R=40 / gap 30 um)."""
    process = fm.load_process(routes_meta or {}, config_payload, run_dir)
    process["source"] = ("four_side_1024.v3.config (process imported from "
                         "fslw.config by the frozen V3 config module)")
    return process


def _relation_of(record):
    relation = record.get("relation")
    if relation in CLASSES:
        return relation
    source = str(record.get("source_side") or "")
    target = str(record.get("target_side") or "")
    try:
        from . import inputs as v3_inputs
        return v3_inputs.relation_of(source, target)
    except Exception:  # noqa: BLE001
        if source == target:
            return "same"
        if {source, target} == {"N", "S"} or {source, target} == {"E", "W"}:
            return "opposite"
        return "adjacent"


def _pair_of(record):
    pair = record.get("pair")
    if pair in PAIR_CLASS:
        return pair
    source = str(record.get("source_side") or "")
    target = str(record.get("target_side") or "")
    try:
        from . import inputs as v3_inputs
        return v3_inputs.pair_of(source, target)
    except Exception:  # noqa: BLE001
        if source == target:
            return source + target
        if {source, target} == {"N", "S"}:
            return "NS"
        if {source, target} == {"E", "W"}:
            return "EW"
        order = {"N": 0, "E": 1, "S": 2, "W": 3}
        return source + target if order.get(source, 9) < order.get(target, 9) \
            else target + source


def _plane_signature(records):
    return dict(records=len(records),
                route_ids=sorted(record.get("route_id") for record in records))


# ---------------------------------------------------------------------------
# path-shape classification FROM PRIMITIVES ONLY (SPEC section 4)
# ---------------------------------------------------------------------------
def _line_length(primitive):
    try:
        return float(math.hypot(
            float(primitive["p1"][0]) - float(primitive["p0"][0]),
            float(primitive["p1"][1]) - float(primitive["p0"][1])))
    except (KeyError, TypeError, ValueError):
        return 0.0


def _is_quarter(sweep):
    return abs(abs(float(sweep)) - math.pi / 2.0) <= 1e-9


def _arc_entries(primitives):
    entries = []
    for index, primitive in enumerate(primitives):
        if primitive.get("kind") != "arc":
            continue
        sweep = _number(primitive.get("sweep")) or 0.0
        entries.append({
            "index": index,
            "sweep": sweep,
            "abs_sweep": abs(sweep),
            "sign": 1 if sweep > 0 else (-1 if sweep < 0 else 0),
            "radius": _number(primitive.get("radius")),
            "quarter": _is_quarter(sweep),
        })
    return entries


def _hairpin_pairs(primitives, quarter_entries):
    """Disjoint pairs of consecutive same-sign quarter arcs (180 deg hairpin)."""
    pairs = []
    index = 0
    entries = list(quarter_entries)
    while index + 1 < len(entries):
        first, second = entries[index], entries[index + 1]
        if (_arcs_adjacent(primitives, first["index"], second["index"])
                and first["sign"] == second["sign"]
                and first["sign"] != 0):
            pairs.append((first, second))
            index += 2
        else:
            index += 1
    return pairs


def _short_s_groups(primitives, radius=RADIUS_MM):
    """Adjacent reverse-theta arc pairs (historical short-S family)."""
    groups = []
    index = 0
    count = len(primitives)
    while index < count:
        primitive = primitives[index]
        if primitive.get("kind") != "arc" or _is_quarter(
                primitive.get("sweep") or 0.0):
            index += 1
            continue
        following = index + 1
        gap = 0.0
        while following < count and primitives[following].get("kind") == "line":
            gap += _line_length(primitives[following])
            following += 1
        if (following < count
                and primitives[following].get("kind") == "arc"
                and gap <= fm.POSE_TOL):
            try:
                valid, _reason = fm._short_s_pair_valid(  # noqa: SLF001
                    primitive, primitives[following], radius)
            except Exception:  # noqa: BLE001
                valid = False
            if valid:
                groups.append((index, following))
                index = following + 1
                continue
        index += 1
    return groups


def _straight_lines_only(primitives):
    """True when every primitive is a line and the whole path is collinear."""
    if not primitives:
        return False
    if any(primitive.get("kind") != "line" for primitive in primitives):
        return False
    try:
        p0 = np.asarray(primitives[0]["p0"], dtype=float)
        p1 = np.asarray(primitives[0]["p1"], dtype=float)
    except (KeyError, TypeError, ValueError):
        return False
    direction = p1 - p0
    norm = float(np.linalg.norm(direction))
    if norm <= 1e-12:
        return False
    unit = direction / norm
    for primitive in primitives[1:]:
        try:
            q0 = np.asarray(primitive["p0"], dtype=float)
            q1 = np.asarray(primitive["p1"], dtype=float)
        except (KeyError, TypeError, ValueError):
            return False
        if abs(float(np.cross(unit, q1 - q0))) > 1e-7:
            return False
        if abs(float(np.cross(unit, q0 - p0))) > 1e-7:
            return False
    return True


def _arcs_adjacent(primitives, first_index, second_index):
    if second_index == first_index + 1:
        return True
    for index in range(first_index + 1, second_index):
        if primitives[index].get("kind") != "line":
            return False
        if _line_length(primitives[index]) > fm.POSE_TOL:
            return False
    return True


def classify_route(primitives, radius=RADIUS_MM):
    """Classify one route's shape strictly from its saved primitives.

    Never consults ``relation``/``pair`` -- this is the SPEC §4 requirement that
    shape must be derived from geometry, not from the CSV label.  The same-side
    ``SAME_HAIRPIN_A/B`` families (short-S lateral shift + one 180-degree hairpin
    of two consecutive quarter arcs) are U-shaped routes and are classified as
    ``U`` with subtype ``hairpin_short_S``: they still turn the path through
    180 degrees inside one side.  ``multi_bend_refold`` is reserved for paths
    with more than two effective bends (three or more quarter arcs, two or more
    hairpins, or a short-S combined with additional quarter arcs).
    """
    primitives = list(primitives or [])
    arcs = _arc_entries(primitives)
    quarter = [entry for entry in arcs if entry["quarter"]]
    non_quarter = [entry for entry in arcs if not entry["quarter"]]
    short_s = _short_s_groups(primitives, radius) if non_quarter else []
    hairpins = _hairpin_pairs(primitives, quarter) if quarter else []
    arc_count = len(arcs)
    line_count = sum(1 for primitive in primitives
                     if primitive.get("kind") == "line")
    net_turn = sum(entry["sweep"] for entry in arcs)
    hairpin = bool(hairpins)
    shape = "other"
    subtype = "unclassified"
    if not primitives:
        subtype = "empty"
    elif arc_count == 0:
        orthogonal = True
        for primitive in primitives:
            if primitive.get("kind") != "line":
                orthogonal = False
                continue
            dx = abs(float(primitive["p1"][0]) - float(primitive["p0"][0]))
            dy = abs(float(primitive["p1"][1]) - float(primitive["p0"][1]))
            if min(dx, dy) > 1e-9:
                orthogonal = False
        if not orthogonal:
            shape = "other"
            subtype = "non_orthogonal_line"
        elif _straight_lines_only(primitives):
            shape = "straight"
            subtype = "single_straight_run"
        else:
            shape = "other"
            subtype = "polyline_without_arc"
    elif non_quarter:
        if arc_count == 2 and len(short_s) == 1 and not quarter:
            shape = "short_S"
            subtype = "short_S_pair"
        elif (arc_count == 4 and len(short_s) == 1 and len(hairpins) == 1
              and len(non_quarter) == 2 and len(quarter) == 2):
            shape = "U"
            subtype = "hairpin_short_S"
        elif arc_count >= 3 or len(short_s) >= 2:
            shape = "multi_bend_refold"
            subtype = ("multi_short_S_refold" if len(short_s) >= 2
                       else "mixed_arc_family_refold")
        else:
            shape = "other"
            subtype = "short_S_with_other_arcs"
    elif arc_count == 1:
        shape = "L"
        subtype = "single_quarter"
    elif arc_count == 2:
        if (quarter[0]["sign"] == quarter[1]["sign"]
                and quarter[0]["sign"] != 0):
            shape = "U"
            subtype = "hairpin" if hairpins else "wide_U"
        else:
            shape = "other"
            subtype = "two_quarter_step_transfer"
    else:
        shape = "multi_bend_refold"
        subtype = ("multi_hairpin_refold" if len(hairpins) >= 2
                   else ("quarter_chain_hairpin" if hairpins
                         else "quarter_chain"))
    return {
        "shape": shape,
        "subtype": subtype,
        "arc_count": arc_count,
        "quarter_arc_count": len(quarter),
        "nonquarter_arc_count": len(non_quarter),
        "short_s_pair_count": len(short_s),
        "hairpin_pair_count": len(hairpins),
        "line_count": line_count,
        "hairpin": hairpin,
        "net_turn_deg": math.degrees(net_turn),
        "turn_signs": [entry["sign"] for entry in arcs],
        "classification_source": "saved_primitives",
        "definition": SHAPE_DEFINITIONS.get(shape),
    }


# ---------------------------------------------------------------------------
# U / nesting / spacing / bundle statistics
# ---------------------------------------------------------------------------
def _curve_points(primitives, sagitta=0.01):
    try:
        return np.asarray(geom.sample(primitives, sagitta), dtype=float)
    except Exception:  # noqa: BLE001 - unusable geometry reported elsewhere
        return np.empty((0, 2))


def _u_features(record, classification, endpoints):
    primitives = record.get("primitives") or []
    source = (endpoints or {}).get(record.get("source_endpoint")) or {}
    target = (endpoints or {}).get(record.get("target_endpoint")) or {}
    side = source.get("side") or target.get("side")
    if side not in SIDE_GEOM:
        side = str(record.get("source_side") or "")
    geometry = SIDE_GEOM.get(side)
    if geometry is None:
        return None
    points = _curve_points(primitives)
    if len(points) == 0:
        return None
    along_index = geometry["along"]
    normal_index = geometry["normal"]
    edge_value = geometry["edge_value"]
    if normal_index == 1:          # N/S: depth is distance from the y edge
        depths = (edge_value - points[:, 1]) if geometry["inward"][1] < 0 \
            else (points[:, 1] - edge_value)
    else:                          # E/W: depth is distance from the x edge
        depths = (edge_value - points[:, 0]) if geometry["inward"][0] < 0 \
            else (points[:, 0] - edge_value)
    depth_max = float(np.max(depths))
    # tracks: straight primitives parallel to the shared edge
    tracks = []
    for primitive in primitives:
        if primitive.get("kind") != "line":
            continue
        length = _line_length(primitive)
        if length < TRACK_MIN_LENGTH_MM:
            continue
        dx = abs(float(primitive["p1"][0]) - float(primitive["p0"][0]))
        dy = abs(float(primitive["p1"][1]) - float(primitive["p0"][1]))
        if normal_index == 1 and dy <= fm.ORTHO_TOL:
            track_depth = (150.0 - float(primitive["p0"][1])
                           if geometry["inward"][1] < 0
                           else float(primitive["p0"][1]))
            tracks.append((float(primitive["p0"][1]), length, track_depth))
        elif normal_index == 0 and dx <= fm.ORTHO_TOL:
            track_depth = (150.0 - float(primitive["p0"][0])
                           if geometry["inward"][0] < 0
                           else float(primitive["p0"][0]))
            tracks.append((float(primitive["p0"][0]), length, track_depth))
    track_depths = sorted({round(depth, 6) for _coord, _len, depth in tracks})
    track_depth = track_depths[-1] if track_depths else depth_max
    start_along = None
    end_along = None
    start_point = primitives[0].get("p0") if primitives else None
    end_point = primitives[-1].get("p1") if primitives else None
    if start_point is not None:
        start_along = float(start_point[along_index])
    if end_point is not None:
        end_along = float(end_point[along_index])
    along_values = points[:, along_index]
    interval = [float(np.min(along_values)), float(np.max(along_values))]
    return {
        "side": side,
        "depth_mm": track_depth,
        "depth_max_mm": depth_max,
        "track_depth_mm": track_depth,
        "track_count": len(track_depths),
        "track_depths_mm": track_depths,
        "width_mm": abs(float(end_along - start_along))
        if None not in (start_along, end_along) else None,
        "interval_along_mm": interval,
        "start_along_mm": start_along,
        "end_along_mm": end_along,
        "arc_count": classification["arc_count"],
        "line_count": classification["line_count"],
        "hairpin": classification["hairpin"],
        "subtype": classification["subtype"],
        "hairpin_pair_count": classification["hairpin_pair_count"],
        "short_s_pair_count": classification["short_s_pair_count"],
        "router_family": (record.get("candidate") or {}).get("family"),
        "length_mm": _number(record.get("length_mm")),
        "route_id": record.get("route_id"),
    }


def _depth_histogram(depths, bin_width=5.0, max_depth=150.0):
    if not depths:
        return {}
    bins = max(1, int(math.ceil(max_depth / bin_width)))
    histogram = OrderedDict()
    for index in range(bins):
        low = index * bin_width
        high = min(max_depth, low + bin_width)
        label = f"{low:.0f}-{high:.0f}"
        histogram[label] = sum(1 for value in depths
                               if low <= value < high
                               or (index == bins - 1 and value == high))
    return dict(histogram)


def _route_prepared(primitives):
    try:
        return d56_validator.prepare_route(primitives)
    except Exception:  # noqa: BLE001
        return None


def _route_pair_gap(first_prepared, second_prepared):
    if first_prepared is None or second_prepared is None:
        return None
    try:
        return fm._route_min_gap(first_prepared, second_prepared, 10.0)  # noqa: SLF001
    except Exception:  # noqa: BLE001
        return None


def compute_u_statistics(routed, classification_by_route, endpoints, process):
    """U depth/track/nesting/adjacent-spacing/bundle statistics (same-side U only)."""
    clearance = float(process.get("clearance_mm") or CLEARANCE_MM)
    members = []
    for record in routed:
        route_id = record.get("route_id")
        classification = classification_by_route.get(route_id) or {}
        if classification.get("shape") != "U":
            continue
        if _relation_of(record) != "same":
            # a U-shaped route whose endpoints are not on one edge is reported
            # in the shape mix but not in the same-side U geometry statistics
            continue
        features = _u_features(record, classification, endpoints)
        if features is not None:
            features["prepared"] = _route_prepared(record.get("primitives") or [])
            members.append(features)
    per_side = OrderedDict()
    for side in "NESW":
        side_members = [item for item in members if item["side"] == side]
        depths = [item["depth_mm"] for item in side_members]
        widths = [item["width_mm"] for item in side_members
                  if item["width_mm"] is not None]
        track_counts = [item["track_count"] for item in side_members]
        per_side[side] = {
            "count": len(side_members),
            "depth_mm": {
                "mean": _mean(depths), "median": _median(depths),
                "min": min(depths) if depths else None,
                "max": max(depths) if depths else None,
                "std": _std(depths),
                "percentiles": _percentiles(depths),
                "histogram_5mm": _depth_histogram(depths),
            },
            "width_mm": {
                "mean": _mean(widths), "median": _median(widths),
                "min": min(widths) if widths else None,
                "max": max(widths) if widths else None,
            },
            "track_count_distribution": dict(sorted(Counter(
                track_counts).items())),
            "hairpin_count": sum(1 for item in side_members
                                 if item["hairpin"]),
            "routes": [{key: value for key, value in item.items()
                        if key != "prepared"} for item in side_members],
        }
    # nesting: containment of (interval, depth) within a deeper/larger U
    nesting_pairs = []
    for side in "NESW":
        side_members = [item for item in members if item["side"] == side]
        for outer in side_members:
            outer_lo, outer_hi = outer["interval_along_mm"]
            for inner in side_members:
                if outer is inner:
                    continue
                inner_lo, inner_hi = inner["interval_along_mm"]
                if (inner_lo >= outer_lo - NESTING_TOL_MM
                        and inner_hi <= outer_hi + NESTING_TOL_MM
                        and inner["depth_mm"] > outer["depth_mm"] + 1e-9):
                    nesting_pairs.append((outer, inner))
    # longest nesting chain (DAG on containment + increasing depth)
    children = {id(item): [] for item in members}
    for outer, inner in nesting_pairs:
        children[id(outer)].append(inner)
    memo = {}

    def _chain(item):
        key = id(item)
        if key in memo:
            return memo[key]
        best = 1
        for child in children.get(key, []):
            best = max(best, 1 + _chain(child))
        memo[key] = best
        return best

    chain_lengths = {id(item): _chain(item) for item in members}
    max_chain = max(chain_lengths.values()) if chain_lengths else 0
    # nested groups (connected components of containment pairs)
    parent = {id(item): id(item) for item in members}

    def _find(value):
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    for outer, inner in nesting_pairs:
        root_a, root_b = _find(id(outer)), _find(id(inner))
        if root_a != root_b:
            parent[root_b] = root_a
    groups = OrderedDict()
    by_id = {id(item): item for item in members}
    for item in members:
        root = _find(id(item))
        groups.setdefault(root, []).append(item)
    nested_groups = []
    for group_members in groups.values():
        if len(group_members) < 2:
            continue
        ordered = sorted(group_members, key=lambda item: item["depth_mm"])
        nested_groups.append({
            "side": ordered[0]["side"],
            "size": len(ordered),
            "route_ids_ordered_by_depth": [item["route_id"]
                                           for item in ordered],
            "depths_mm": [round(item["depth_mm"], 6) for item in ordered],
            "intervals_along_mm": [[round(v, 6) for v in
                                    item["interval_along_mm"]]
                                   for item in ordered],
            "chain_length": max(chain_lengths.get(id(item), 1)
                                for item in ordered),
        })
    nested_groups.sort(key=lambda item: (-item["size"], item["side"]))
    # adjacent-U spacing: consecutive tracks per side with overlapping intervals
    adjacent = []
    for side in "NESW":
        side_members = sorted([item for item in members if item["side"] == side],
                              key=lambda item: item["depth_mm"])
        for first, second in zip(side_members[:-1], side_members[1:]):
            lo = max(first["interval_along_mm"][0], second["interval_along_mm"][0])
            hi = min(first["interval_along_mm"][1], second["interval_along_mm"][1])
            if hi - lo <= 0.0:
                continue
            gap = _route_pair_gap(first["prepared"], second["prepared"])
            if gap is None:
                gap = abs(second["depth_mm"] - first["depth_mm"])
            adjacent.append({
                "side": side,
                "route_a": first["route_id"],
                "route_b": second["route_id"],
                "track_depth_a_mm": round(first["depth_mm"], 6),
                "track_depth_b_mm": round(second["depth_mm"], 6),
                "centreline_gap_mm": round(gap, 6),
                "interval_overlap_mm": round(hi - lo, 6),
            })
    gaps = [item["centreline_gap_mm"] for item in adjacent]
    spacing_violations = [item for item in adjacent
                          if item["centreline_gap_mm"] < clearance - 1e-7]
    # bundle / arch grouping: overlapping intervals with depth within tolerance
    bundles = []
    for side in "NESW":
        side_members = sorted([item for item in members if item["side"] == side],
                              key=lambda item: item["depth_mm"])
        used = set()
        for index, first in enumerate(side_members):
            if id(first) in used:
                continue
            group = [first]
            used.add(id(first))
            for second in side_members[index + 1:]:
                if id(second) in used:
                    continue
                overlap = min(first["interval_along_mm"][1],
                              second["interval_along_mm"][1]) - \
                    max(first["interval_along_mm"][0],
                        second["interval_along_mm"][0])
                if (overlap > 0.0
                        and abs(second["depth_mm"] - first["depth_mm"])
                        <= BUNDLE_DEPTH_TOL_MM):
                    group.append(second)
                    used.add(id(second))
            if len(group) >= 2:
                bundles.append({
                    "side": side,
                    "size": len(group),
                    "route_ids": [item["route_id"] for item in group],
                    "depths_mm": [round(item["depth_mm"], 6) for item in group],
                })
    bundles.sort(key=lambda item: -item["size"])
    track_counts = [item["track_count"] for item in members]
    subtype_counts = Counter(item["subtype"] for item in members)
    family_counts = Counter(item["router_family"] or "unknown"
                            for item in members)
    return {
        "definition": "same-side 180-degree U/hairpin routes only "
                      "(relation=='same' AND shape=='U' from saved primitives: "
                      "wide_U, hairpin, and hairpin_short_S families); depth = "
                      "inward distance from the shared board edge to the deepest "
                      "point/track; track_count = number of straight segments "
                      "parallel to the shared edge with length >= "
                      f"{TRACK_MIN_LENGTH_MM} mm (0 for pure hairpin-family paths "
                      "that contain no straight track)",
        "count": len(members),
        "subtype_counts": dict(sorted(subtype_counts.items())),
        "router_family_counts": dict(sorted(family_counts.items())),
        "per_side": per_side,
        "depth_mm": {
            "mean": _mean([item["depth_mm"] for item in members]),
            "median": _median([item["depth_mm"] for item in members]),
            "min": min([item["depth_mm"] for item in members], default=None),
            "max": max([item["depth_mm"] for item in members], default=None),
            "percentiles": _percentiles([item["depth_mm"] for item in members]),
            "histogram_5mm": _depth_histogram(
                [item["depth_mm"] for item in members]),
        },
        "track_count_distribution": dict(sorted(Counter(track_counts).items())),
        "hairpin_count": sum(1 for item in members if item["hairpin"]),
        "nesting": {
            "containment_pair_count": len(nesting_pairs),
            "max_chain_length": max_chain,
            "groups": nested_groups[:50],
            "group_count": len(nested_groups),
            "definition": "an inner U nests in an outer U when its along-edge "
                          "interval is contained in the outer interval and its "
                          "track is deeper (larger depth from the shared edge)",
        },
        "adjacent_spacing": {
            "pairs_considered": len(adjacent),
            "min_gap_mm": min(gaps) if gaps else None,
            "mean_gap_mm": _mean(gaps),
            "max_gap_mm": max(gaps) if gaps else None,
            "violation_count": len(spacing_violations),
            "violations": spacing_violations[:20],
            "pairs": adjacent[:200],
            "definition": "consecutive U tracks per side with overlapping "
                          "along-edge intervals; gap = exact minimum centreline "
                          "distance between the two routes",
        },
        "bundles": {
            "count": len(bundles),
            "max_size": max([item["size"] for item in bundles], default=0),
            "mean_size": _mean([item["size"] for item in bundles]),
            "depth_tolerance_mm": BUNDLE_DEPTH_TOL_MM,
            "groups": bundles[:50],
            "definition": "overlapping U intervals within one depth tolerance "
                          "band (2 x clearance) form one bundle/arch track group",
        },
    }


def compute_refold_statistics(routed, classification_by_route, process):
    """Refold (multi-bend) route statistics and refold-region congestion."""
    board = process.get("board_mm") or [fslw_config.BOARD_MM] * 2
    board_x, board_y = float(board[0]), float(board[1])
    refold = [record for record in routed
              if (classification_by_route.get(record.get("route_id")) or {})
              .get("shape") == "multi_bend_refold"]
    cells = GRID_MM
    grid_x = max(1, int(math.ceil(board_x / cells)))
    grid_y = max(1, int(math.ceil(board_y / cells)))
    density = np.zeros((grid_x, grid_y), dtype=float)
    total_length = 0.0
    for record in refold:
        primitives = record.get("primitives") or []
        points = _curve_points(primitives, 0.01)
        if len(points) < 2:
            continue
        for first, second in zip(points[:-1], points[1:]):
            segment = second - first
            length = float(np.linalg.norm(segment))
            if length <= 0.0:
                continue
            total_length += length
            steps = max(1, int(math.ceil(length / 0.5)))
            share = length / steps
            for step in range(steps):
                t = (step + 0.5) / steps
                px = first[0] + t * segment[0]
                py = first[1] + t * segment[1]
                ix = min(grid_x - 1, max(0, int(math.floor(px / cells))))
                iy = min(grid_y - 1, max(0, int(math.floor(py / cells))))
                density[ix, iy] += share
    flat = [(float(density[ix, iy]), ix, iy)
            for ix in range(grid_x) for iy in range(grid_y)
            if density[ix, iy] > 0]
    flat.sort(reverse=True)
    top_cells = [{"x_min_mm": ix * cells, "y_min_mm": iy * cells,
                  "length_mm": _round(value, 3)}
                 for value, ix, iy in flat[:10]]
    return {
        "count": len(refold),
        "routing_rate": (len(refold) / len(routed)) if routed else None,
        "total_length_mm": total_length,
        "mean_length_mm": _mean([_number(record.get("length_mm"))
                                 for record in refold]),
        "mean_bend_count": _mean([_number(record.get("bend_count"))
                                  for record in refold]),
        "region_grid_mm": GRID_MM,
        "region_grid_peak_mm": flat[0][0] if flat else 0.0,
        "region_grid_peak_cell": ([flat[0][1] * cells, flat[0][2] * cells]
                                  if flat else None),
        "top_congestion_cells": top_cells,
        "definition": "refold = path shapes classified multi_bend_refold from "
                      "primitives; congestion = refold-only centreline length per "
                      "5 x 5 mm cell (mm per cell)",
    }


# ---------------------------------------------------------------------------
# failure taxonomy (SPEC section 8 honesty rules)
# ---------------------------------------------------------------------------
def _failure_category(reason):
    text = str(reason or "").lower()
    if "no_candidate_generated" in text or "no_candidate" in text:
        return "no_candidate_generated"
    if "no_legal_candidate" in text:
        return "no_legal_candidate"
    if "budget" in text or "timeout" in text or "deadline" in text:
        return "budget_or_timeout"
    if "not_attempted" in text or "skipped" in text:
        return "not_attempted"
    return "other"


def compute_failure_taxonomy(failed):
    categories = ("no_candidate_generated", "no_legal_candidate",
                  "budget_or_timeout", "not_attempted", "other")
    counts = Counter()
    by_class = {relation: Counter() for relation in CLASSES}
    by_pair = Counter()
    examples = []
    for record in failed:
        category = _failure_category(record.get("reason"))
        counts[category] += 1
        relation = _relation_of(record)
        if relation in by_class:
            by_class[relation][category] += 1
        by_pair[_pair_of(record)] += 1
        if len(examples) < 20:
            examples.append({
                "route_id": record.get("route_id"),
                "relation": relation,
                "pair": _pair_of(record),
                "reason": record.get("reason"),
                "category": category,
                "evaluated": record.get("evaluated"),
                "blockers": record.get("blockers"),
                "rejection_counts": record.get("rejection_counts"),
            })
    total = len(failed)
    return {
        "total_failed": total,
        "counts": {category: counts.get(category, 0)
                   for category in categories},
        "fractions": {category: (counts.get(category, 0) / total)
                      for category in categories} if total else {},
        "by_class": {relation: dict(by_class[relation])
                     for relation in CLASSES},
        "by_pair": dict(sorted(by_pair.items())),
        "examples": examples,
        "honesty_interpretation": {
            "A_template_or_family_infeasible": {
                "count": counts.get("no_candidate_generated", 0),
                "meaning": "no candidate from the implemented D56 families was "
                           "generated at all (SPEC §8 category A/B without "
                           "family-level proof of mathematical impossibility)",
            },
            "C_candidate_blocked_by_other_routes": {
                "count": counts.get("no_legal_candidate", 0),
                "meaning": "candidates were generated but rejected by the strict "
                           "same-plane acceptance policy (blocked by other routes "
                           "and/or the geometry rules; not hidden)",
            },
            "budget_or_timeout": {
                "count": counts.get("budget_or_timeout", 0),
                "meaning": "stopped by the evaluation/time budget",
            },
            "note": "no mathematical impossibility is claimed; A/B/C cannot be "
                    "fully separated from the saved artefacts, so the raw "
                    "no_candidate_generated / no_legal_candidate split is the "
                    "authoritative taxonomy",
        },
    }


# ---------------------------------------------------------------------------
# plane statistics assembly
# ---------------------------------------------------------------------------
def _resolve_paths(run_dir):
    run_dir = Path(run_dir)
    routes_path = run_dir / "routes.json"
    if not routes_path.exists():
        raise FileNotFoundError(f"no routes.json under {run_dir}")
    config_path = run_dir / "config.json"
    return routes_path, config_path


def load_plane_context(run_dir, statistics=None):
    """Load one plane run (records, endpoints, connectors, process, stats)."""
    run_dir = Path(run_dir)
    routes_path, default_config = _resolve_paths(run_dir)
    config_path = default_config if default_config.exists() else None
    payload, meta, records, routed, failed = fm.load_routes(routes_path)
    config_payload = _load_json(config_path) if config_path else None
    process = load_process(meta, config_payload, run_dir)
    plane = fm._normalise_plane(process.get("plane"))  # noqa: SLF001
    if plane is None:
        for record in records:
            plane = fm._normalise_plane(record.get("plane"))  # noqa: SLF001
            if plane:
                break
    process["plane"] = plane
    if process.get("z_mm") is None:
        process["z_mm"] = fm.PLANE_Z.get(plane)
    algorithm = process.get("algorithm") or _first(meta, ("algorithm",))
    ports = load_plane_ports(plane) if plane else {}
    endpoints = ports.get("endpoints")
    if not endpoints:
        endpoints = fm._derive_endpoints(routed, process)  # noqa: SLF001
    if statistics is None:
        stats_path = run_dir / "statistics.json"
        if stats_path.exists():
            try:
                statistics = _load_json(stats_path)
            except (OSError, json.JSONDecodeError):
                statistics = None
    return {
        "run_dir": run_dir,
        "routes_path": routes_path,
        "config_path": config_path if config_path else None,
        "payload": payload,
        "meta": meta,
        "records": records,
        "routed": routed,
        "failed": failed,
        "process": process,
        "plane": plane,
        "algorithm": algorithm,
        "experiment": process.get("experiment") or run_dir.parent.name + "_" + str(plane),
        "endpoints": endpoints,
        "connectors": ports.get("connectors") or [],
        "ports_validation": ports.get("validation"),
        "ports_source": ports.get("source"),
        "statistics": statistics,
    }


def build_plane_statistics(run_dir, out_path=None, audit_path=None,
                           config_path=None, skip_pair_audit=False,
                           skip_min_gaps=False, quiet=False):
    """Recompute the complete V3 plane statistics set and write statistics.json."""
    started = time.perf_counter()
    run_dir = Path(run_dir)
    context = load_plane_context(run_dir)
    routes_path = context["routes_path"]
    payload = context["payload"]
    meta = context["meta"]
    records = context["records"]
    routed = context["routed"]
    failed = context["failed"]
    process = context["process"]
    plane = context["plane"]
    algorithm = context["algorithm"]
    endpoints = context["endpoints"]
    ports_routes = None
    if v3_ports is not None and plane:
        try:
            ports_routes = v3_ports.load_plane(plane)[0]
        except Exception:  # noqa: BLE001
            ports_routes = None
    if config_path is None:
        config_path = context["config_path"]
    else:
        config_path = Path(config_path)
    if out_path is None:
        out_path = run_dir / "statistics.json"
    else:
        out_path = Path(out_path)
    if audit_path is None:
        candidate = run_dir / "audit_strict.json"
        audit_path = candidate if candidate.exists() else None

    # ---------------- class / pair counts ---------------------------------
    class_total = Counter()
    class_routed = Counter()
    pair_total = Counter()
    pair_routed = Counter()
    for record in records:
        relation = _relation_of(record)
        pair = _pair_of(record)
        if relation in CLASSES:
            class_total[relation] += 1
        if pair in PAIR_CLASS:
            pair_total[pair] += 1
        if record.get("status") == "routed" or record.get("primitives"):
            if relation in CLASSES:
                class_routed[relation] += 1
            if pair in PAIR_CLASS:
                pair_routed[pair] += 1
    routed_count = len(routed)
    unrouted_count = len(failed)
    by_class = OrderedDict()
    for relation in CLASSES:
        total = class_total.get(relation, 0)
        success = class_routed.get(relation, 0)
        expected = CLASS_EXPECTED.get(relation)
        by_class[relation] = {
            "success": success, "routed": success,
            "failed": total - success, "total": total,
            "routing_rate": (success / total) if total else None,
            "expected_total": expected,
            "matches_expected": (total == expected) if expected else None,
            "pairs": list(CLASS_PAIRS[relation]),
        }
    by_pair = OrderedDict()
    for pair in PAIR_ORDER:
        total = pair_total.get(pair, 0)
        success = pair_routed.get(pair, 0)
        expected = PAIR_EXPECTED.get(pair)
        by_pair[pair] = {
            "class": PAIR_CLASS[pair],
            "success": success, "routed": success,
            "failed": total - success, "total": total,
            "routing_rate": (success / total) if total else None,
            "expected_total": expected,
            "matches_expected": (total == expected) if expected else None,
        }

    # ---------------- topology / identity validation vs frozen ports ------
    validation = {"plane": plane, "connections": len(records),
                  "unique_route_ids": len({record.get("route_id")
                                           for record in records}),
                  "expected_connections": CONNECTIONS_PER_PLANE,
                  "class_counts": dict(class_total),
                  "class_expected": dict(CLASS_EXPECTED),
                  "pair_counts": dict(pair_total),
                  "pair_expected": dict(PAIR_EXPECTED),
                  "issues": []}
    if len(records) != CONNECTIONS_PER_PLANE:
        validation["issues"].append(
            f"connection_count {len(records)} != {CONNECTIONS_PER_PLANE}")
    if validation["unique_route_ids"] != len(records):
        validation["issues"].append("duplicate route_id")
    plane_row = fslw_config.PLANE_ROW.get(plane)
    if ports_routes is not None:
        ports_by_id = {record.get("route_id"): record for record in ports_routes}
        mismatches = []
        for record in records:
            reference = ports_by_id.get(record.get("route_id"))
            if reference is None:
                mismatches.append({"route_id": record.get("route_id"),
                                   "issue": "route_id not in frozen port model"})
                continue
            for key in ("relation", "pair", "source_endpoint",
                        "target_endpoint", "plane"):
                if record.get(key) != reference.get(key):
                    mismatches.append({
                        "route_id": record.get("route_id"), "field": key,
                        "routes_json": record.get(key),
                        "ports_model": reference.get(key)})
            row = record.get("source_row")
            if row is not None and plane_row is not None and int(row) != plane_row:
                mismatches.append({"route_id": record.get("route_id"),
                                   "field": "source_row", "routes_json": row,
                                   "expected": plane_row})
            if len(mismatches) >= 30:
                break
        validation["ports_model_mismatch_count"] = len(mismatches)
        validation["ports_model_mismatches"] = mismatches[:30]
        if mismatches:
            validation["issues"].append(
                f"{len(mismatches)} record(s) disagree with the frozen ports model")
    plane_expected = PLANE_EXPECTED.get(plane) or {}
    if plane_expected:
        for relation in CLASSES:
            expected = plane_expected.get(relation)
            actual = class_total.get(relation, 0)
            if expected is not None and actual != expected:
                validation["issues"].append(
                    f"plane {plane} {relation} count {actual} != {expected}")
    validation["passed"] = not validation["issues"]

    # ---------------- standard geometry / crossing / loss / quality -------
    geometry = fm.compute_route_geometry(routed, process, endpoints)
    classification_by_route = {}
    shape_counts = Counter()
    subtype_counts = Counter()
    router_family_counts = Counter()
    router_family_by_shape = {}
    shape_by_class = {relation: Counter() for relation in CLASSES}
    shape_by_pair = {pair: Counter() for pair in PAIR_ORDER}
    shape_routes = {}
    for record in routed:
        route_id = record.get("route_id")
        classification = classify_route(record.get("primitives") or [],
                                        float(process.get("radius_mm")
                                              or RADIUS_MM))
        classification_by_route[route_id] = classification
        shape = classification["shape"]
        shape_counts[shape] += 1
        subtype_counts[classification["subtype"]] += 1
        router_family = (record.get("candidate") or {}).get("family") or "unknown"
        router_family_counts[router_family] += 1
        router_family_by_shape.setdefault(router_family, Counter())[shape] += 1
        relation = _relation_of(record)
        if relation in shape_by_class:
            shape_by_class[relation][shape] += 1
        pair = _pair_of(record)
        if pair in shape_by_pair:
            shape_by_pair[pair][shape] += 1
        shape_routes[str(route_id)] = {
            "shape": shape,
            "subtype": classification["subtype"],
            "arc_count": classification["arc_count"],
            "quarter_arc_count": classification["quarter_arc_count"],
            "short_s_pair_count": classification["short_s_pair_count"],
            "hairpin_pair_count": classification["hairpin_pair_count"],
            "hairpin": classification["hairpin"],
            "net_turn_deg": _round(classification["net_turn_deg"], 3),
            "relation": relation,
            "pair": pair,
            "router_family": router_family,
            "length_mm": _round(record.get("length_mm"), 6),
        }
    total_shaped = sum(shape_counts.values())
    u_subtype_counts = Counter({
        subtype: count for subtype, count in subtype_counts.items()
        if subtype in ("wide_U", "hairpin", "hairpin_short_S")})
    path_shapes = {
        "counts": {shape: shape_counts.get(shape, 0)
                   for shape in REQUIRED_SHAPES},
        "fractions": {shape: (shape_counts.get(shape, 0) / total_shaped)
                      for shape in REQUIRED_SHAPES} if total_shaped else {},
        "routed_total": total_shaped,
        "subtypes": dict(sorted(subtype_counts.items())),
        "u_subtype_counts": dict(sorted(u_subtype_counts.items())),
        "router_family_counts": dict(sorted(router_family_counts.items())),
        "router_family_by_shape": {
            family: dict(sorted(counts.items()))
            for family, counts in sorted(router_family_by_shape.items())},
        "by_class": {relation: {shape: shape_by_class[relation].get(shape, 0)
                                for shape in REQUIRED_SHAPES}
                     for relation in CLASSES},
        "by_pair": {pair: {shape: shape_by_pair[pair].get(shape, 0)
                           for shape in REQUIRED_SHAPES}
                    for pair in PAIR_ORDER},
        "per_route": shape_routes,
        "classified_from": "saved world-mm primitives (relation/pair labels are "
                           "not used for the shape; router_family is recorded "
                           "for provenance only and is not the classifier)",
        "definitions": SHAPE_DEFINITIONS,
    }
    pair_audit = None if skip_pair_audit else fm.compute_pair_audit(routed,
                                                                    process)
    audit_report, audit_meta = fm.load_audit(routes_path, audit_path)
    audit_values = (audit_report or {}).get("values", {}) if audit_report else {}
    recomputed = {
        "crossing_count": pair_audit["crossing_count"] if pair_audit else None,
        "crossing_angle_histogram": (pair_audit["crossing_angle_histogram"]
                                     if pair_audit else None),
        "small_angle_crossing_count": (pair_audit["small_angle_crossing_count"]
                                       if pair_audit else None),
        "spacing_violation_pairs": (pair_audit["spacing_violation_pairs"]
                                    if pair_audit else None),
        "overlap_pairs": pair_audit["overlap_pairs"] if pair_audit else None,
        "touch_pairs": pair_audit["touch_pairs"] if pair_audit else None,
        "crossing_window_overlap_pairs": (
            pair_audit["crossing_window_overlap_pairs"] if pair_audit else None),
        "double_cross_pairs": (pair_audit["double_cross_pairs"]
                               if pair_audit else None),
        "crossing_window_excessive_pairs": (
            pair_audit["crossing_window_excessive_pairs"] if pair_audit else None),
        "violation_pair_count": (pair_audit["violation_pair_count"]
                                 if pair_audit else None),
        "self_intersections": geometry["self_intersections"],
        "self_overlaps": geometry["self_overlaps"],
        "self_spacing_violations": geometry["self_spacing_violations"],
        "radius_violations": geometry["radius_violations"],
        "boundary_violations": geometry["boundary_violations"],
        "diagonal_line_violations": geometry["diagonal_line_violations"],
        "free_arc_violations": geometry["free_arc_violations"],
    }
    violation_fields = ("spacing_violation_pairs", "overlap_pairs", "touch_pairs",
                        "crossing_window_overlap_pairs", "double_cross_pairs",
                        "crossing_window_excessive_pairs", "violation_pair_count",
                        "crossing_count", "crossing_angle_histogram",
                        "small_angle_crossing_count", "self_intersections",
                        "self_overlaps", "self_spacing_violations",
                        "radius_violations", "boundary_violations",
                        "diagonal_line_violations", "free_arc_violations")
    merged = OrderedDict()
    sources = OrderedDict()
    for field in violation_fields:
        if field in audit_values and audit_values[field] is not None:
            merged[field] = audit_values[field]
            sources[field] = f"{audit_report['label']}:{audit_report['file']}"
        else:
            merged[field] = recomputed.get(field)
            sources[field] = ("recomputed_from_primitives"
                              if recomputed.get(field) is not None else None)
    crossing_count = merged.get("crossing_count")
    if crossing_count is None:
        crossing_count = recomputed.get("crossing_count")
        sources["crossing_count"] = "recomputed_from_primitives"
    gaps = None if skip_min_gaps else fm.compute_min_gaps(routed, process)
    quality = fm.compute_quality(routed, process, endpoints,
                                 (pair_audit or {}).get("crossings") or [])
    quality.pop("sampled_curves", None)
    lengths = [entry["length_mm"] for entry in geometry["per_route"].values()]
    loss_breakdown = fm.compute_loss_breakdown(lengths, process)
    propagation_detail = fm.compute_propagation_loss(lengths, process)
    propagation_block = dict(propagation_detail)
    propagation_block["value_db"] = propagation_detail.get("total_db")
    propagation_block["db_per_cm"] = propagation_detail.get(
        "propagation_loss_db_per_cm")
    propagation_block["optical_loss_scope"] = (
        "propagation-only; bend loss and crossing loss are unknown_uncalibrated")
    u_statistics = compute_u_statistics(routed, classification_by_route,
                                        endpoints, process)
    refold_statistics = compute_refold_statistics(routed, classification_by_route,
                                                  process)
    failure_taxonomy = compute_failure_taxonomy(failed)
    run_metadata = fm._extract_run_metadata(meta, None, run_dir)  # noqa: SLF001
    crossing_pair_count = (audit_report or {}).get("crossing_pair_count")
    if crossing_pair_count is None and pair_audit is not None:
        crossing_pair_count = pair_audit["crossing_pair_count"]
    violations_total = 0
    violations_complete = True
    for field in ("spacing_violation_pairs", "overlap_pairs", "touch_pairs",
                  "crossing_window_overlap_pairs", "double_cross_pairs",
                  "crossing_window_excessive_pairs", "self_intersections",
                  "self_overlaps", "self_spacing_violations",
                  "radius_violations", "boundary_violations",
                  "diagonal_line_violations", "free_arc_violations"):
        value = merged.get(field)
        if value is None:
            violations_complete = False
        else:
            violations_total += int(value)
    board_x, board_y = [float(v) for v in (process.get("board_mm")
                                           or [v3_config.BOARD_MM] * 2)]

    statistics = OrderedDict()
    statistics["schema"] = SCHEMA_PLANE
    statistics["scope"] = "plane"
    statistics["tool"] = TOOL
    statistics["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    statistics["experiment"] = context["experiment"]
    statistics["topology"] = getattr(v3_config, "TOPOLOGY", "V3_Huang")
    statistics["algorithm"] = algorithm
    statistics["plane"] = plane
    statistics["plane_row"] = fslw_config.PLANE_ROW.get(plane)
    statistics["z_mm"] = process.get("z_mm")
    statistics["port_model"] = process.get("port_model")
    statistics["process"] = _json_safe(process)
    statistics["board_mm"] = [board_x, board_y]
    statistics["layer"] = 0
    statistics["source"] = {
        "routes_json": str(routes_path),
        "routes_sha256": _sha256(routes_path),
        "routes_schema": meta.get("schema"),
        "config_json": str(config_path) if config_path else None,
        "ports_source": context["ports_source"],
        "ports_validation_passed": (context["ports_validation"] or {}).get(
            "passed"),
        "connector_count": len(context["connectors"]),
        "audit": audit_meta,
        "audit_sha256": (audit_report or {}).get("sha256"),
    }
    statistics["connections_total"] = CONNECTIONS_PER_PLANE
    statistics["connections_in_file"] = len(records)
    statistics["routed"] = routed_count
    statistics["unrouted"] = unrouted_count
    statistics["routing_rate"] = routed_count / CONNECTIONS_PER_PLANE
    statistics["success_count"] = routed_count
    statistics["failed_count"] = unrouted_count
    statistics["by_class"] = by_class
    statistics["by_pair"] = by_pair
    statistics["topology_validation"] = validation
    statistics["same_side"] = {
        "routed": class_routed.get("same", 0),
        "total": class_total.get("same", 0),
        "routing_rate": (class_routed.get("same", 0)
                         / class_total.get("same", 0))
        if class_total.get("same") else None,
        "by_pair": {pair: {"routed": pair_routed.get(pair, 0),
                           "total": pair_total.get(pair, 0),
                           "routing_rate": (pair_routed.get(pair, 0)
                                            / pair_total.get(pair, 0))
                           if pair_total.get(pair) else None}
                    for pair in CLASS_PAIRS["same"]},
        "definition": "NN/SS/EE/WW same-edge connections (the V3 U/refold core)",
    }
    statistics["failure_reason_counts"] = dict(sorted(Counter(
        str(record.get("reason") or "unknown_failure")
        for record in failed).items()))
    statistics["failure_taxonomy"] = failure_taxonomy
    statistics["failed_route_ids"] = sorted(record.get("route_id")
                                            for record in failed)
    statistics["length"] = {
        "mean_length_mm": geometry["mean_length_mm"],
        "max_length_mm": geometry["max_length_mm"],
        "min_length_mm": geometry["min_length_mm"],
        "total_length_mm": geometry["total_length_mm"],
        "total_horizontal_line_length_mm": geometry[
            "total_horizontal_line_length_mm"],
        "total_vertical_line_length_mm": geometry[
            "total_vertical_line_length_mm"],
        "total_arc_length_mm": geometry["total_arc_length_mm"],
    }
    for key in ("mean_length_mm", "max_length_mm", "min_length_mm",
                "total_length_mm", "mean_bend_count", "max_bend_count",
                "total_bends", "mean_turns", "mean_straight_fraction",
                "mean_horizontal_straight_fraction",
                "mean_vertical_straight_fraction", "mean_arc_fraction",
                "mean_unnecessary_detour_mm", "max_unnecessary_detour_mm",
                "total_unnecessary_detour_mm", "mean_unnecessary_detour_ratio",
                "mean_unnecessary_detour_vs_euclidean_mm",
                "total_unnecessary_detour_vs_euclidean_mm",
                "routes_below_manhattan_bound_count"):
        statistics[key] = geometry.get(key)
    statistics["horizontal_straight_fraction"] = (
        geometry["total_horizontal_line_length_mm"]
        / geometry["total_length_mm"]) if geometry["total_length_mm"] else None
    statistics["vertical_straight_fraction"] = (
        geometry["total_vertical_line_length_mm"]
        / geometry["total_length_mm"]) if geometry["total_length_mm"] else None
    statistics["detour_definition"] = geometry.get("detour_note")
    statistics["crossing_count"] = crossing_count
    statistics["crossing_count_source"] = sources.get("crossing_count")
    statistics["crossing_count_recomputed"] = recomputed.get("crossing_count")
    statistics["crossing_pair_count"] = crossing_pair_count
    statistics["crossing_count_density_per_mm2"] = (
        (crossing_count / (board_x * board_y))
        if crossing_count is not None and board_x and board_y else None)
    statistics["crossing_angle_histogram"] = merged.get(
        "crossing_angle_histogram") or recomputed.get("crossing_angle_histogram")
    statistics["crossing_histogram_bins_deg"] = [label for label, _, _ in
                                                 fm._HIST_BINS]  # noqa: SLF001
    statistics["small_angle_threshold_deg"] = 10.0
    statistics["small_angle_crossing_count"] = merged.get(
        "small_angle_crossing_count")
    statistics["small_angle_5deg_threshold_deg"] = 5.0
    statistics["small_angle_5deg_crossing_count"] = (pair_audit or {}).get(
        "small_angle_5deg_crossing_count")
    statistics["crossing_grid_mm"] = GRID_MM
    statistics["crossing_grid_peak"] = (pair_audit or {}).get("crossing_grid_peak")
    statistics["crossing_grid_peak_cell"] = (pair_audit or {}).get(
        "crossing_grid_peak_cell")
    statistics["densest_crossing_cells"] = (pair_audit or {}).get(
        "densest_crossing_cells")
    statistics["crossing_points_count"] = len((pair_audit or {}).get(
        "crossings") or [])
    sample_crossings = []
    for item in ((pair_audit or {}).get("crossings") or [])[:500]:
        sample_crossings.append({"x_mm": float(item["x"]),
                                 "y_mm": float(item["y"]),
                                 "angle_deg": item.get("angle_deg"),
                                 "route_a": item.get("route_a"),
                                 "route_b": item.get("route_b")})
    statistics["crossing_points_sample"] = sample_crossings
    statistics["crossing_points_note"] = (
        "full crossing list is not embedded (size); recompute with "
        "four_side_1024.v3.metrics for figures")
    for field in violation_fields:
        if field in ("crossing_count", "crossing_angle_histogram",
                     "small_angle_crossing_count"):
            continue
        statistics[field] = merged.get(field)
        statistics[f"{field}_source"] = sources.get(field)
        statistics[f"{field}_recomputed"] = recomputed.get(field)
    statistics["total_violation_count"] = (violations_total
                                           if violations_complete else None)
    statistics["audit_passed"] = (audit_report or {}).get("passed")
    statistics["audit_policy"] = (audit_report or {}).get("policy")
    statistics["audit_routed_count"] = (audit_report or {}).get("routed_count")
    statistics["audit_checked_count"] = (audit_report or {}).get("checked_count")
    statistics["audit_failed_count"] = (audit_report or {}).get("failed_count")
    statistics["audit_error_count"] = (audit_report or {}).get("error_count")
    statistics["audit_violation_count"] = (audit_report or {}).get(
        "violation_count")
    statistics["audit_candidate_pair_count"] = (audit_report or {}).get(
        "candidate_pair_count")
    statistics["audit_runtime_seconds"] = (audit_report or {}).get(
        "runtime_seconds")
    statistics["audit_crossing_window_count"] = (audit_report or {}).get(
        "crossing_window_count")
    statistics["audit_crossing_window_max_mm"] = (audit_report or {}).get(
        "crossing_window_max_mm")
    statistics["min_non_crossing_centerline_mm"] = (
        (audit_report or {}).get("values", {}).get(
            "min_non_crossing_centerline_mm")
        or (pair_audit or {}).get("min_non_crossing_centerline_mm"))
    statistics["mean_min_gap_mm"] = (gaps or {}).get("mean_min_gap_mm")
    statistics["median_min_gap_mm"] = (gaps or {}).get("median_min_gap_mm")
    statistics["min_min_gap_mm"] = (gaps or {}).get("min_min_gap_mm")
    statistics["max_min_gap_mm"] = (gaps or {}).get("max_min_gap_mm")
    statistics["routes_with_min_gap"] = (gaps or {}).get("routes_with_min_gap")
    statistics["quality"] = quality
    statistics["route_length_grid_peak_mm"] = quality.get(
        "route_length_grid_peak_mm")
    statistics["route_length_grid_peak_cell"] = quality.get(
        "route_length_grid_peak_cell")
    statistics["port_region"] = quality.get("port_region")
    statistics["port_region_length_mm"] = quality.get("port_region_length_mm")
    statistics["path_shapes"] = path_shapes
    statistics["u_statistics"] = u_statistics
    statistics["refold_statistics"] = refold_statistics
    statistics["propagation_loss"] = propagation_block
    statistics["propagation_loss_detail"] = propagation_detail
    statistics["optical_loss_breakdown"] = {
        key: value for key, value in loss_breakdown.items()
        if key != "propagation_loss"}
    statistics["optical_loss_breakdown"]["propagation_loss"] = (
        loss_breakdown["propagation_loss"])
    statistics["candidate_evaluations"] = run_metadata["candidate_evaluations"]
    statistics["candidate_evaluations_source"] = run_metadata[
        "candidate_evaluations_source"]
    statistics["runtime_seconds"] = run_metadata["runtime_seconds"]
    statistics["runtime_seconds_source"] = run_metadata["runtime_seconds_source"]
    statistics["evals_per_second"] = run_metadata["evals_per_second"]
    statistics["peak_memory_mb"] = run_metadata["peak_memory_mb"]
    statistics["peak_memory_mb_source"] = run_metadata["peak_memory_mb_source"]
    statistics["pair_checks"] = run_metadata["pair_checks"]
    statistics["eval_budget"] = run_metadata["eval_budget"]
    statistics["time_budget_seconds"] = run_metadata["time_budget_seconds"]
    statistics["budget_exhausted"] = run_metadata["budget_exhausted"]
    statistics["seed"] = None
    statistics["strategy"] = None
    if config_path:
        try:
            config_payload = _load_json(config_path)
        except (OSError, json.JSONDecodeError):
            config_payload = None
        if isinstance(config_payload, dict):
            statistics["seed"] = config_payload.get("seed")
            statistics["strategy"] = config_payload.get("strategy")
            statistics["config_budget"] = config_payload.get("budget")
    statistics["pareto"] = {
        "routed": routed_count,
        "same_side_routed": class_routed.get("same", 0),
        "total_length_mm": geometry["total_length_mm"],
        "crossing_count": crossing_count,
        "propagation_loss_total_db": propagation_block.get("value_db"),
        "mean_length_mm": geometry["mean_length_mm"],
        "small_angle_crossing_count": statistics["small_angle_crossing_count"],
        "strict_violation_count": (violations_total
                                   if violations_complete else None),
        "u_route_count": u_statistics["count"],
        "refold_route_count": refold_statistics["count"],
        "lexicographic_objective": [
            "routed (descending)", "strict_violation_count (ascending)",
            "same_side_routed (descending)",
            "small_angle_crossing_count (ascending)",
            "crossing_count (ascending)", "total_length_mm (ascending)"],
    }
    statistics["geometry_checks"] = {key: value for key, value in geometry.items()
                                     if key not in ("per_route", "route_errors")}
    statistics["route_geometry"] = geometry["per_route"]
    statistics["metric_sources"] = {
        "class/pair counts": "recomputed from routes.json and cross-checked "
                             "against v3/ports.py frozen identity metadata",
        "path shapes": "SAVED PRIMITIVES ONLY (relation/pair label is not used)",
        "U/refold/nesting/spacing/bundles": "saved primitives + frozen port "
                                            "endpoints",
        "crossings/violations": "authoritative audit_strict.json merged when "
                                "fresh (stale mtime ignored), otherwise "
                                "recomputed with the independent geometry kernel",
        "losses": "propagation computed; bend/crossing unknown_uncalibrated",
        "quality": "recomputed from sampled centrelines",
        "audited_fields": sources,
    }
    statistics["notes"] = []
    if audit_meta.get("status") != "merged":
        statistics["notes"].append(
            f"audit_strict.json not merged ({audit_meta.get('status')}); "
            "violation counters recomputed with source="
            "'recomputed_from_primitives'")
    if audit_meta.get("status") == "stale_ignored":
        statistics["notes"].append(
            "ignored audit file older than routes.json (stale solution)")
    statistics["notes"].append(
        "shape classes are derived from saved primitives, never from the "
        "CSV relation label")
    statistics["notes"].append(
        "bend loss and crossing loss are unknown_uncalibrated; only propagation "
        "loss is a physical loss number")
    statistics["notes"].append(
        "plane is metadata only: every primitive is layer=0 2D; z is 0.0 for z1 "
        "and 0.5 for z2 and is never used inside a plane")
    statistics["notes"].append(
        "same-side routed count is reported separately for NN/SS/EE/WW; failure "
        "reasons are reported as-is with the SPEC §8 (A)/(B)/(C) interpretation")
    statistics["recomputation_runtime_seconds"] = time.perf_counter() - started
    statistics = _json_safe(statistics)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(statistics, handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    if not quiet:
        print(json.dumps({
            "out": str(out_path),
            "experiment": statistics["experiment"],
            "plane": plane,
            "routed": routed_count,
            "routing_rate": round(statistics["routing_rate"], 6),
            "same_routed": class_routed.get("same", 0),
            "opposite_routed": class_routed.get("opposite", 0),
            "adjacent_routed": class_routed.get("adjacent", 0),
            "shapes": dict(shape_counts),
            "u_routes": u_statistics["count"],
            "nesting_max_chain": u_statistics["nesting"]["max_chain_length"],
            "crossing_count": crossing_count,
            "audit_passed": statistics["audit_passed"],
            "recompute_seconds": round(
                statistics["recomputation_runtime_seconds"], 3),
        }, ensure_ascii=False))
    return statistics


# ---------------------------------------------------------------------------
# combined dual-height statistics
# ---------------------------------------------------------------------------
def build_combined_statistics(combined_dir, root=None, out_path=None,
                              plane_statistics=None, skip_projection=False,
                              quiet=False):
    """Merge z1+z2 into the 1024-channel combined statistics."""
    started = time.perf_counter()
    combined_dir = Path(combined_dir)
    if root is None:
        root = combined_dir.parent.parent
    root = Path(root)
    algorithm = combined_dir.name
    planes = {}
    plane_routes = {}
    plane_stats = plane_statistics or {}
    for plane in PLANES:
        plane_dir = _plane_run_dir(root, algorithm, plane)
        routes_path = plane_dir / "routes.json"
        if not routes_path.exists():
            planes[plane] = {"available": False,
                             "run_dir": str(plane_dir),
                             "error": "routes.json missing"}
            continue
        payload, meta, records, routed, failed = fm.load_routes(routes_path)
        plane_routes[plane] = {"payload": payload, "meta": meta,
                               "records": records, "routed": routed,
                               "failed": failed}
        statistics = plane_stats.get(plane)
        if statistics is None:
            stats_path = plane_dir / "statistics.json"
            if stats_path.exists():
                try:
                    statistics = _load_json(stats_path)
                except (OSError, json.JSONDecodeError):
                    statistics = None
            if statistics is None:
                statistics = build_plane_statistics(plane_dir, quiet=True)
            plane_stats[plane] = statistics
        planes[plane] = {"available": True, "run_dir": str(plane_dir),
                         "routes_json": str(routes_path),
                         "statistics": statistics,
                         "routed": len(routed), "unrouted": len(failed)}
    routed_total = sum(len(plane_routes[plane]["routed"]) for plane in PLANES
                       if plane in plane_routes)
    combined = OrderedDict()
    combined["schema"] = SCHEMA_COMBINED
    combined["scope"] = "combined"
    combined["tool"] = TOOL
    combined["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    combined["topology"] = getattr(v3_config, "TOPOLOGY", "V3_Huang")
    combined["algorithm"] = algorithm
    combined["experiment"] = f"{algorithm}_combined"
    combined["process"] = _json_safe(
        (plane_stats.get("z1") or {}).get("process")
        or fm.load_process({}, None, None))
    combined["port_model"] = getattr(v3_config, "PORT_MODEL",
                                     fslw_config.PORT_MODEL)
    combined["z_model"] = {"z1": 0.0, "z2": 0.5, "z2_minus_z1_mm": 0.5,
                           "note": "model heights; no z transition implemented"}
    combined["planes"] = {}
    for plane in PLANES:
        entry = planes.get(plane) or {}
        statistics = entry.get("statistics") or {}
        combined["planes"][plane] = {
            "available": entry.get("available", False),
            "run_dir": entry.get("run_dir"),
            "routed": statistics.get("routed"),
            "unrouted": statistics.get("unrouted"),
            "connections_total": statistics.get("connections_total",
                                                CONNECTIONS_PER_PLANE),
            "routing_rate": statistics.get("routing_rate"),
            "by_class": statistics.get("by_class"),
            "by_pair": statistics.get("by_pair"),
            "mean_length_mm": statistics.get("mean_length_mm"),
            "total_length_mm": statistics.get("total_length_mm"),
            "crossing_count": statistics.get("crossing_count"),
            "same_side_routed": statistics.get("same_side", {}).get("routed"),
            "u_route_count": (statistics.get("u_statistics") or {}).get("count"),
            "path_shapes": (statistics.get("path_shapes") or {}).get("counts"),
            "propagation_loss": statistics.get("propagation_loss"),
            "audit_passed": statistics.get("audit_passed"),
            "total_violation_count": statistics.get("total_violation_count"),
        }
    combined["connections_total"] = TOTAL_CONNECTIONS
    combined["connections_per_plane"] = CONNECTIONS_PER_PLANE
    combined["routed"] = routed_total
    combined["unrouted"] = TOTAL_CONNECTIONS - routed_total
    combined["routing_rate"] = routed_total / TOTAL_CONNECTIONS
    # merged class/pair table
    by_class = OrderedDict()
    for relation in CLASSES:
        total = 0
        success = 0
        for plane in PLANES:
            entry = ((planes.get(plane) or {}).get("statistics") or {}).get(
                "by_class", {}).get(relation) or {}
            total += int(entry.get("total") or 0)
            success += int(entry.get("success") or 0)
        by_class[relation] = {"success": success, "routed": success,
                              "failed": total - success, "total": total,
                              "routing_rate": (success / total) if total else None}
    combined["by_class"] = by_class
    combined["same_side"] = {
        "routed": by_class["same"]["success"],
        "total": by_class["same"]["total"],
        "routing_rate": by_class["same"]["routing_rate"],
        "by_pair": {},
    }
    for pair in CLASS_PAIRS["same"]:
        total = 0
        success = 0
        for plane in PLANES:
            entry = ((planes.get(plane) or {}).get("statistics") or {}).get(
                "by_pair", {}).get(pair) or {}
            total += int(entry.get("total") or 0)
            success += int(entry.get("success") or 0)
        combined["same_side"]["by_pair"][pair] = {
            "routed": success, "total": total,
            "routing_rate": (success / total) if total else None}
    by_pair = OrderedDict()
    for pair in PAIR_ORDER:
        total = 0
        success = 0
        for plane in PLANES:
            entry = ((planes.get(plane) or {}).get("statistics") or {}).get(
                "by_pair", {}).get(pair) or {}
            total += int(entry.get("total") or 0)
            success += int(entry.get("success") or 0)
        by_pair[pair] = {"class": PAIR_CLASS[pair], "routed": success,
                         "success": success, "failed": total - success,
                         "total": total,
                         "routing_rate": (success / total) if total else None}
    combined["by_pair"] = by_pair
    # merged shape / U / refold statistics
    shape_counts = Counter()
    shape_subtypes = Counter()
    u_subtype_counts = Counter()
    router_family_counts = Counter()
    shape_by_class = {relation: Counter() for relation in CLASSES}
    shape_by_pair = {pair: Counter() for pair in PAIR_ORDER}
    u_merged = Counter()
    refold_count = 0
    for plane in PLANES:
        statistics = ((planes.get(plane) or {}).get("statistics") or {})
        shapes = statistics.get("path_shapes") or {}
        for shape, count in (shapes.get("counts") or {}).items():
            shape_counts[shape] += int(count or 0)
        for subtype, count in (shapes.get("subtypes") or {}).items():
            shape_subtypes[subtype] += int(count or 0)
        for subtype, count in (shapes.get("u_subtype_counts") or {}).items():
            u_subtype_counts[subtype] += int(count or 0)
        for family, count in (shapes.get("router_family_counts") or {}).items():
            router_family_counts[family] += int(count or 0)
        for relation, counts in (shapes.get("by_class") or {}).items():
            for shape, count in (counts or {}).items():
                shape_by_class.setdefault(relation, Counter())[shape] += int(
                    count or 0)
        for pair, counts in (shapes.get("by_pair") or {}).items():
            for shape, count in (counts or {}).items():
                shape_by_pair.setdefault(pair, Counter())[shape] += int(
                    count or 0)
        u_statistics = statistics.get("u_statistics") or {}
        u_merged["count"] += int(u_statistics.get("count") or 0)
        u_merged["nesting_groups"] += int(
            (u_statistics.get("nesting") or {}).get("group_count") or 0)
        u_merged["max_chain"] = max(
            u_merged["max_chain"],
            int((u_statistics.get("nesting") or {}).get("max_chain_length") or 0))
        refold_count += int((statistics.get("refold_statistics") or {}).get(
            "count") or 0)
    total_shaped = sum(shape_counts.values())
    combined["path_shapes"] = {
        "counts": {shape: shape_counts.get(shape, 0)
                   for shape in REQUIRED_SHAPES},
        "fractions": {shape: (shape_counts.get(shape, 0) / total_shaped)
                      for shape in REQUIRED_SHAPES} if total_shaped else {},
        "routed_total": total_shaped,
        "subtypes": dict(sorted(shape_subtypes.items())),
        "u_subtype_counts": dict(sorted(u_subtype_counts.items())),
        "router_family_counts": dict(sorted(router_family_counts.items())),
        "by_class": {relation: {shape: shape_by_class[relation].get(shape, 0)
                                for shape in REQUIRED_SHAPES}
                     for relation in CLASSES},
        "by_pair": {pair: {shape: shape_by_pair[pair].get(shape, 0)
                           for shape in REQUIRED_SHAPES}
                    for pair in PAIR_ORDER},
        "classified_from": "saved world-mm primitives (two heights merged)",
    }
    combined["u_statistics"] = {
        "count": u_merged["count"],
        "nesting_group_count": u_merged["nesting_groups"],
        "nesting_max_chain_length": u_merged["max_chain"],
        "per_plane": {plane: ((planes.get(plane) or {}).get("statistics") or {})
                      .get("u_statistics") for plane in PLANES},
        "note": "U/refold geometry statistics are per plane; the two heights are "
                "independent 2D problems, so nesting is reported per plane",
    }
    combined["refold_statistics"] = {
        "count": refold_count,
        "per_plane": {plane: ((planes.get(plane) or {}).get("statistics") or {})
                      .get("refold_statistics") for plane in PLANES},
    }
    # lengths / bends / detours / crossings / losses / violations
    total_length = 0.0
    length_weighted = 0.0
    route_count_length = 0
    straight_weighted = 0.0
    straight_routes = 0
    detour_total = 0.0
    detour_weighted = 0.0
    total_bends = 0
    same_plane_crossings = 0
    crossing_histogram = {label: 0 for label, _, _ in fm._HIST_BINS}  # noqa: SLF001
    small_angle = 0
    violations_total = 0
    violations_complete = True
    for plane in PLANES:
        statistics = ((planes.get(plane) or {}).get("statistics") or {})
        length = _number((statistics.get("length") or {}).get("total_length_mm"))
        if length is not None:
            total_length += length
        routed_count = int(statistics.get("routed") or 0)
        mean_length = _number(statistics.get("mean_length_mm"))
        if mean_length is not None and routed_count:
            length_weighted += mean_length * routed_count
            route_count_length += routed_count
        straight = _number(statistics.get("mean_straight_fraction"))
        if straight is not None and routed_count:
            straight_weighted += straight * routed_count
            straight_routes += routed_count
        detour = _number(statistics.get("total_unnecessary_detour_mm"))
        if detour is not None:
            detour_total += detour
        mean_detour = _number(statistics.get("mean_unnecessary_detour_mm"))
        if mean_detour is not None and routed_count:
            detour_weighted += mean_detour * routed_count
        total_bends += int(statistics.get("total_bends") or 0)
        crossing = _number(statistics.get("crossing_count"))
        if crossing is not None:
            same_plane_crossings += int(crossing)
        for label, value in (statistics.get("crossing_angle_histogram") or {}).items():
            if label in crossing_histogram:
                crossing_histogram[label] += int(value or 0)
        small = _number(statistics.get("small_angle_crossing_count"))
        if small is not None:
            small_angle += int(small)
        for field in ("spacing_violation_pairs", "overlap_pairs", "touch_pairs",
                      "crossing_window_overlap_pairs", "double_cross_pairs",
                      "crossing_window_excessive_pairs", "self_intersections",
                      "self_overlaps", "self_spacing_violations",
                      "radius_violations", "boundary_violations",
                      "diagonal_line_violations", "free_arc_violations"):
            value = statistics.get(field)
            if value is None:
                violations_complete = False
            else:
                violations_total += int(value)
    combined["length"] = {
        "mean_length_mm": (length_weighted / route_count_length)
        if route_count_length else None,
        "total_length_mm": total_length,
        "mean_straight_fraction": (straight_weighted / straight_routes)
        if straight_routes else None,
        "total_unnecessary_detour_mm": detour_total,
        "mean_unnecessary_detour_mm": (detour_weighted / route_count_length)
        if route_count_length else None,
        "total_bends": total_bends,
    }
    combined["mean_length_mm"] = combined["length"]["mean_length_mm"]
    combined["total_length_mm"] = total_length
    combined["total_bends"] = total_bends
    combined["same_plane_crossings"] = same_plane_crossings
    combined["same_plane_crossing_angle_histogram"] = crossing_histogram
    combined["small_angle_crossing_count"] = small_angle
    combined["same_plane_crossing_by_plane"] = {
        plane: ((planes.get(plane) or {}).get("statistics") or {}).get(
            "crossing_count") for plane in PLANES}
    combined["violations"] = {
        "same_plane_total": violations_total if violations_complete else None,
        "complete": violations_complete,
        "by_plane": {plane: {
            field: ((planes.get(plane) or {}).get("statistics") or {}).get(field)
            for field in ("spacing_violation_pairs", "overlap_pairs",
                          "touch_pairs", "crossing_window_overlap_pairs",
                          "self_intersections", "radius_violations",
                          "boundary_violations")} for plane in PLANES},
        "cross_plane": {"status": "not_a_violation_by_design",
                        "note": "SPEC §2/§5: two different glass heights; no "
                                "cross-plane same-layer conflict test exists",
                        "value": 0},
    }
    # loss
    propagation_total = 0.0
    propagation_weighted = 0.0
    propagation_routes = 0
    propagation_by_plane = {}
    for plane in PLANES:
        statistics = ((planes.get(plane) or {}).get("statistics") or {})
        block = statistics.get("propagation_loss") or {}
        propagation_by_plane[plane] = block
        total = _number(block.get("value_db"))
        if total is not None:
            propagation_total += total
        mean = _number(block.get("mean_db"))
        routed_count = int(statistics.get("routed") or 0)
        if mean is not None and routed_count:
            propagation_weighted += mean * routed_count
            propagation_routes += routed_count
    combined["propagation_loss"] = {
        "status": "computed",
        "value_db": propagation_total,
        "total_db": propagation_total,
        "mean_db": (propagation_weighted / propagation_routes)
        if propagation_routes else None,
        "total_length_cm": total_length / 10.0,
        "formula": "Lprop_dB = 0.05 dB/cm * length_cm",
        "db_per_cm": float(getattr(v3_config,
                                   "PROPAGATION_LOSS_DB_PER_CM", 0.05)),
        "by_plane": propagation_by_plane,
        "optical_loss_scope": "propagation-only; bend/crossing unknown_uncalibrated",
    }
    combined["optical_loss_breakdown"] = {
        "bend_loss": dict(getattr(v3_config, "BEND_LOSS", {})),
        "crossing_loss": dict(getattr(v3_config, "CROSSING_LOSS", {})),
        "propagation_loss": combined["propagation_loss"],
        "total_optical_loss": {
            "status": "not_computable_missing_calibration", "value_db": None,
            "components_known": ["propagation"],
            "components_unknown": ["bend", "crossing"]},
        "legacy_arm": {"included": False,
                       "legacy_polymer_estimate": dict(getattr(
                           v3_config, "LEGACY_POLYMER_ESTIMATE", {})),
                       "status": "legacy_estimate_omitted"},
    }
    if not skip_projection and all(plane in plane_routes for plane in PLANES):
        process = fm.load_process({}, None, None)
        combined["cross_plane_projected_overlap"] = (
            fm.compute_cross_plane_projection(plane_routes["z1"]["routed"],
                                              plane_routes["z2"]["routed"],
                                              process))
    else:
        combined["cross_plane_projected_overlap"] = {
            "status": "unavailable",
            "note": "both plane runs must exist to compute the XY projection"}
    combined["mean_min_gap_mm"] = _mean([
        _number(((planes.get(plane) or {}).get("statistics") or {}).get(
            "mean_min_gap_mm")) for plane in PLANES])
    combined["failure_taxonomy"] = _merge_failure_taxonomies(
        ((planes.get(plane) or {}).get("statistics") or {}).get(
            "failure_taxonomy") for plane in PLANES)
    combined["path_shapes"]["definitions"] = SHAPE_DEFINITIONS
    combined["candidate_evaluations"] = sum(
        int(((planes.get(plane) or {}).get("statistics") or {}).get(
            "candidate_evaluations") or 0) for plane in PLANES)
    combined["runtime_seconds"] = sum(
        (_number(((planes.get(plane) or {}).get("statistics") or {}).get(
            "runtime_seconds")) or 0.0) for plane in PLANES)
    combined["audit_passed_all_planes"] = all(
        ((planes.get(plane) or {}).get("statistics") or {}).get("audit_passed")
        is True for plane in PLANES if (planes.get(plane) or {}).get("available"))
    combined["pareto"] = {
        "routed": routed_total,
        "same_side_routed": by_class["same"]["success"],
        "total_length_mm": total_length,
        "same_plane_crossings": same_plane_crossings,
        "propagation_loss_total_db": propagation_total,
        "strict_violation_count": violations_total if violations_complete else None,
        "lexicographic_objective": [
            "routed (descending)", "strict_violation_count (ascending)",
            "same_side_routed (descending)", "same_plane_crossings (ascending)",
            "total_length_mm (ascending)"],
    }
    combined["metric_sources"] = {
        "per_plane": "planes/<A>/<z>/statistics.json (recomputed from primitives; "
                     "audit_strict.json merged when fresh)",
        "combined": "merged from the two plane statistics; same-plane crossings "
                    "summed; cross-plane projection is informational only",
        "path_shapes": "SAVED PRIMITIVES ONLY per plane, merged by class/pair",
        "losses": "propagation computed; bend/crossing unknown_uncalibrated",
    }
    combined["notes"] = [
        "combined layout = plane z1 (row 1) + plane z2 (row 2) at model heights "
        "0.0/0.5; each plane mixes same/opposite/adjacent classes",
        "each plane is an independent 2D problem at layer=0; the two heights are "
        "NOT a waveguide layer stack and no z-transition is implemented",
        "cross-plane XY-projected overlaps are informational only and never "
        "violations (SPEC §2)",
        "bend loss and crossing loss remain unknown_uncalibrated",
        "U/nesting statistics are per-plane (2D problems); the combined block "
        "merges them without pretending they interact across heights",
    ]
    combined["recomputation_runtime_seconds"] = time.perf_counter() - started
    combined = _json_safe(combined)
    if out_path is None:
        out_path = combined_dir / "statistics.json"
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(combined, handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    if not quiet:
        projection = combined.get("cross_plane_projected_overlap") or {}
        print(json.dumps({
            "out": str(out_path),
            "experiment": combined["experiment"],
            "routed": routed_total,
            "total": TOTAL_CONNECTIONS,
            "routing_rate": round(combined["routing_rate"], 6),
            "same_side_routed": by_class["same"]["success"],
            "by_plane": {plane: ((planes.get(plane) or {}).get("statistics")
                                 or {}).get("routed") for plane in PLANES},
            "same_plane_crossings": same_plane_crossings,
            "cross_plane_projected_internal": projection.get(
                "cross_plane_projected_internal_crossings"),
            "u_routes_total": combined["u_statistics"]["count"],
            "recompute_seconds": round(
                combined["recomputation_runtime_seconds"], 3),
        }, ensure_ascii=False))
    return combined


def _merge_failure_taxonomies(taxonomies):
    counts = Counter()
    by_class = {relation: Counter() for relation in CLASSES}
    by_pair = Counter()
    total = 0
    for taxonomy in taxonomies:
        if not taxonomy:
            continue
        total += int(taxonomy.get("total_failed") or 0)
        for category, value in (taxonomy.get("counts") or {}).items():
            counts[category] += int(value or 0)
        for relation, values in (taxonomy.get("by_class") or {}).items():
            for category, value in (values or {}).items():
                by_class.setdefault(relation, Counter())[category] += int(
                    value or 0)
        for pair, value in (taxonomy.get("by_pair") or {}).items():
            by_pair[pair] += int(value or 0)
    return {"total_failed": total,
            "counts": dict(counts),
            "by_class": {relation: dict(by_class[relation])
                         for relation in CLASSES},
            "by_pair": dict(sorted(by_pair.items())),
            "note": "merged over both planes; raw no_candidate_generated vs "
                    "no_legal_candidate taxonomy is authoritative (SPEC §8)"}


# ---------------------------------------------------------------------------
# shapes/ aggregate artifact
# ---------------------------------------------------------------------------
def build_shapes_statistics(root, out_path=None, quiet=False):
    """Aggregate same-side U / refold / shape statistics into shapes/."""
    root = Path(root)
    output_dir = root / "shapes"
    output_dir.mkdir(parents=True, exist_ok=True)
    if out_path is None:
        out_path = output_dir / "same_side_statistics.json"
    per_plane = {}
    aggregate = {"connections_total": 0, "routed": 0,
                 "same_routed": 0, "same_total": 0,
                 "shape_counts": Counter(), "refold_count": 0,
                 "u_count": 0, "nesting_groups": 0, "max_chain": 0}
    failures = []
    for algorithm, plane, run_dir in iter_plane_runs(root):
        context = load_plane_context(run_dir)
        statistics = context["statistics"]
        if statistics is None:
            statistics = build_plane_statistics(run_dir, quiet=True)
        per_plane[f"{algorithm}_{plane}"] = {
            "experiment": statistics.get("experiment"),
            "plane": plane,
            "z_mm": statistics.get("z_mm"),
            "routed": statistics.get("routed"),
            "routing_rate": statistics.get("routing_rate"),
            "by_class": statistics.get("by_class"),
            "same_side": statistics.get("same_side"),
            "path_shapes": statistics.get("path_shapes"),
            "u_statistics": statistics.get("u_statistics"),
            "refold_statistics": statistics.get("refold_statistics"),
            "failure_taxonomy": statistics.get("failure_taxonomy"),
            "audit_passed": statistics.get("audit_passed"),
        }
        aggregate["connections_total"] += int(
            statistics.get("connections_total") or 0)
        aggregate["routed"] += int(statistics.get("routed") or 0)
        same_block = statistics.get("same_side") or {}
        aggregate["same_routed"] += int(same_block.get("routed") or 0)
        aggregate["same_total"] += int(same_block.get("total") or 0)
        for shape, count in ((statistics.get("path_shapes") or {}).get(
                "counts") or {}).items():
            aggregate["shape_counts"][shape] += int(count or 0)
        aggregate["refold_count"] += int((statistics.get("refold_statistics")
                                          or {}).get("count") or 0)
        aggregate["u_count"] += int((statistics.get("u_statistics") or {}).get(
            "count") or 0)
        nesting = (statistics.get("u_statistics") or {}).get("nesting") or {}
        aggregate["nesting_groups"] += int(nesting.get("group_count") or 0)
        aggregate["max_chain"] = max(aggregate["max_chain"],
                                     int(nesting.get("max_chain_length") or 0))
        if statistics.get("audit_passed") is False:
            failures.append(f"{algorithm}_{plane}")
    total_routed = aggregate["routed"]
    payload = {
        "schema": SCHEMA_SHAPES,
        "tool": TOOL,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "root": str(root),
        "planes_measured": len(per_plane),
        "aggregate": {
            "connections_total": aggregate["connections_total"],
            "routed": total_routed,
            "routing_rate": (total_routed / aggregate["connections_total"])
            if aggregate["connections_total"] else None,
            "same_side": {
                "routed": aggregate["same_routed"],
                "total": aggregate["same_total"],
                "routing_rate": (aggregate["same_routed"]
                                 / aggregate["same_total"])
                if aggregate["same_total"] else None,
            },
            "path_shapes": {
                "counts": {shape: aggregate["shape_counts"].get(shape, 0)
                           for shape in REQUIRED_SHAPES},
                "fractions": {
                    shape: (aggregate["shape_counts"].get(shape, 0) / total_routed)
                    for shape in REQUIRED_SHAPES} if total_routed else {},
            },
            "u_route_count": aggregate["u_count"],
            "refold_route_count": aggregate["refold_count"],
            "nesting_group_count": aggregate["nesting_groups"],
            "nesting_max_chain_length": aggregate["max_chain"],
        },
        "per_plane": per_plane,
        "planes_with_failed_audit": failures,
        "definitions": {
            "path_shapes": SHAPE_DEFINITIONS,
            "u_statistics": "same-side U routes only; depth from shared edge; "
                            "tracks = straight segments parallel to the edge >= "
                            f"{TRACK_MIN_LENGTH_MM} mm",
            "nesting": "inner U nests in outer U when its along-edge interval is "
                       "contained and its track is deeper",
            "bundle": "overlapping U intervals within a depth band of "
                      f"{BUNDLE_DEPTH_TOL_MM} mm",
        },
        "notes": [
            "all shape classification is derived from saved world-mm primitives; "
            "relation/pair labels are never used for the shape",
            "U/nesting/spacing/bundle statistics are per plane (independent 2D "
            "problems at two heights)",
        ],
    }
    out_path = Path(out_path)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(_json_safe(payload), handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    if not quiet:
        print(json.dumps({
            "out": str(out_path),
            "planes_measured": len(per_plane),
            "routed": total_routed,
            "same_routed": aggregate["same_routed"],
            "shapes": dict(aggregate["shape_counts"]),
            "u_route_count": aggregate["u_count"],
            "nesting_max_chain_length": aggregate["max_chain"],
        }, ensure_ascii=False))
    return payload


# ---------------------------------------------------------------------------
# u_track_statistics.json (machine-readable Phase-6 U numbers)
# ---------------------------------------------------------------------------
def build_u_track_statistics(root, out_path=None, quiet=False):
    """Write ``shapes/u_track_statistics.json``: depth/track/nesting/spacing."""
    root = Path(root)
    shapes_dir = root / "shapes"
    shapes_dir.mkdir(parents=True, exist_ok=True)
    if out_path is None:
        out_path = shapes_dir / "u_track_statistics.json"
    per_plane = {}
    aggregate = {
        "u_count": 0,
        "side_counts": Counter(),
        "depth_values": [],
        "track_counts": Counter(),
        "nesting_group_count": 0,
        "max_chain_length": 0,
        "adjacent_pairs": 0,
        "adjacent_min_gap_mm": None,
        "adjacent_mean_gaps": [],
        "adjacent_violations": 0,
        "bundles": 0,
        "bundle_max_size": 0,
        "bundle_sizes": [],
    }
    for algorithm, plane, run_dir in iter_plane_runs(root):
        context = load_plane_context(run_dir)
        statistics = context["statistics"]
        if statistics is None:
            statistics = build_plane_statistics(run_dir, quiet=True)
        u_statistics = statistics.get("u_statistics") or {}
        entry = {
            "experiment": statistics.get("experiment"),
            "plane": plane,
            "z_mm": statistics.get("z_mm"),
            "routed": statistics.get("routed"),
            "u_count": u_statistics.get("count"),
            "same_side": statistics.get("same_side"),
            "depth_mm": u_statistics.get("depth_mm"),
            "track_count_distribution": u_statistics.get(
                "track_count_distribution"),
            "per_side": {},
            "nesting": {
                "group_count": (u_statistics.get("nesting") or {}).get(
                    "group_count", 0),
                "max_chain_length": (u_statistics.get("nesting") or {}).get(
                    "max_chain_length", 0),
                "containment_pair_count": (u_statistics.get("nesting") or {}).get(
                    "containment_pair_count", 0),
                "groups": (u_statistics.get("nesting") or {}).get("groups", []),
            },
            "adjacent_spacing": {
                key: (u_statistics.get("adjacent_spacing") or {}).get(key)
                for key in ("pairs_considered", "min_gap_mm", "mean_gap_mm",
                            "max_gap_mm", "violation_count", "violations")},
            "bundles": {
                "count": (u_statistics.get("bundles") or {}).get("count", 0),
                "max_size": (u_statistics.get("bundles") or {}).get(
                    "max_size", 0),
                "mean_size": (u_statistics.get("bundles") or {}).get("mean_size"),
                "depth_tolerance_mm": u_statistics.get("bundles", {}).get(
                    "depth_tolerance_mm") if u_statistics.get("bundles") else None,
            },
        }
        for side in "NESW":
            side_block = (u_statistics.get("per_side") or {}).get(side) or {}
            depths = [route.get("depth_mm") for route in
                      (side_block.get("routes") or [])
                      if route.get("depth_mm") is not None]
            track_depths = sorted({round(value, 6) for value in depths})
            entry["per_side"][side] = {
                "count": side_block.get("count", 0),
                "depth_mm": side_block.get("depth_mm"),
                "width_mm": side_block.get("width_mm"),
                "track_count_distribution": side_block.get(
                    "track_count_distribution"),
                "hairpin_count": side_block.get("hairpin_count"),
                "distinct_track_count": len(track_depths),
                "track_depths_mm": track_depths,
                "track_intervals_along_mm": [
                    [round(route.get("start_along_mm") or 0.0, 6),
                     round(route.get("end_along_mm") or 0.0, 6)]
                    for route in (side_block.get("routes") or [])],
            }
            if depths:
                aggregate["side_counts"][side] += len(depths)
                aggregate["depth_values"].extend(depths)
                aggregate["track_counts"][len(track_depths)] += 1
        aggregate["u_count"] += int(u_statistics.get("count") or 0)
        nesting = u_statistics.get("nesting") or {}
        aggregate["nesting_group_count"] += int(nesting.get("group_count") or 0)
        aggregate["max_chain_length"] = max(
            aggregate["max_chain_length"],
            int(nesting.get("max_chain_length") or 0))
        adjacent = u_statistics.get("adjacent_spacing") or {}
        aggregate["adjacent_pairs"] += int(adjacent.get("pairs_considered") or 0)
        minimum = _number(adjacent.get("min_gap_mm"))
        if minimum is not None and (aggregate["adjacent_min_gap_mm"] is None
                                    or minimum < aggregate["adjacent_min_gap_mm"]):
            aggregate["adjacent_min_gap_mm"] = minimum
        mean_gap = _number(adjacent.get("mean_gap_mm"))
        if mean_gap is not None:
            aggregate["adjacent_mean_gaps"].append(mean_gap)
        aggregate["adjacent_violations"] += int(
            adjacent.get("violation_count") or 0)
        bundles = u_statistics.get("bundles") or {}
        aggregate["bundles"] += int(bundles.get("count") or 0)
        aggregate["bundle_max_size"] = max(aggregate["bundle_max_size"],
                                           int(bundles.get("max_size") or 0))
        if bundles.get("groups"):
            aggregate["bundle_sizes"].extend(
                [group.get("size") for group in bundles["groups"]
                 if group.get("size")])
        per_plane[f"{algorithm}_{plane}"] = entry
    depth_values = aggregate["depth_values"]
    payload = {
        "schema": "four_side_1024_v3_u_track_statistics_v1",
        "tool": TOOL,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "root": str(root),
        "planes_measured": len(per_plane),
        "aggregate": {
            "u_route_count": aggregate["u_count"],
            "u_count_per_side": dict(aggregate["side_counts"]),
            "depth_mm": {
                "mean": _mean(depth_values),
                "median": _median(depth_values),
                "min": min(depth_values) if depth_values else None,
                "max": max(depth_values) if depth_values else None,
                "std": _std(depth_values),
                "percentiles": _percentiles(depth_values),
                "histogram_5mm": _depth_histogram(depth_values),
            },
            "distinct_track_count_distribution": dict(sorted(
                aggregate["track_counts"].items())),
            "nesting_group_count": aggregate["nesting_group_count"],
            "nesting_max_chain_length": aggregate["max_chain_length"],
            "adjacent_u_spacing": {
                "pairs_considered": aggregate["adjacent_pairs"],
                "min_gap_mm": aggregate["adjacent_min_gap_mm"],
                "mean_gap_mm": _mean(aggregate["adjacent_mean_gaps"]),
                "violation_count": aggregate["adjacent_violations"],
            },
            "bundles": {
                "count": aggregate["bundles"],
                "max_size": aggregate["bundle_max_size"],
                "mean_size": _mean(aggregate["bundle_sizes"]),
            },
        },
        "per_plane": per_plane,
        "definitions": {
            "depth_mm": "inward distance from the shared board edge to the "
                        "deepest U track",
            "track_count": "number of straight segments parallel to the shared "
                           f"edge with length >= {TRACK_MIN_LENGTH_MM} mm",
            "nesting": "inner U nests in outer U when its along-edge interval is "
                       "contained in the outer interval and its track is deeper",
            "adjacent_u_spacing": "consecutive U tracks per side with overlapping "
                                  "along-edge intervals; exact minimum centreline "
                                  "distance between the two routes",
            "bundle": "overlapping U intervals within a depth band of "
                      f"{BUNDLE_DEPTH_TOL_MM} mm",
        },
        "notes": [
            "all values are per plane (the two heights are independent 2D "
            "problems); no cross-height U interaction is claimed",
            "shape/U features come from saved primitives only",
        ],
    }
    out_path = Path(out_path)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(_json_safe(payload), handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    if not quiet:
        print(json.dumps({"out": str(out_path),
                          "u_route_count": aggregate["u_count"],
                          "nesting_group_count": aggregate["nesting_group_count"],
                          "nesting_max_chain_length": aggregate["max_chain_length"]},
                         ensure_ascii=False))
    return str(out_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _build_parser():
    parser = argparse.ArgumentParser(
        description="Recompute V3-Huang plane/combined/shape statistics.")
    parser.add_argument("--run-dir", help="plane run dir (planes/<A>/<z1|z2>)")
    parser.add_argument("--combined-dir", help="combined/<A> dir")
    parser.add_argument("--root", help="V3 output root")
    parser.add_argument("--shapes", action="store_true",
                        help="aggregate shapes/ same-side statistics")
    parser.add_argument("--routes", help="explicit plane routes.json")
    parser.add_argument("--config", help="explicit plane config.json")
    parser.add_argument("--audit", help="explicit audit_strict.json")
    parser.add_argument("--out", help="output json path")
    parser.add_argument("--skip-pair-audit", action="store_true")
    parser.add_argument("--skip-min-gaps", action="store_true")
    parser.add_argument("--skip-projection", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    root = Path(args.root) if args.root else Path(
        getattr(v3_config, "OUTPUT_ROOT",
                "outputs/four_side_1024_v3_huang_R40_gap30_abcd"))
    if args.shapes:
        build_shapes_statistics(root, out_path=args.out, quiet=args.quiet)
        return 0
    if args.combined_dir:
        build_combined_statistics(args.combined_dir, root=root,
                                  out_path=args.out,
                                  skip_projection=args.skip_projection,
                                  quiet=args.quiet)
        return 0
    run_dir = args.run_dir
    routes_path = args.routes
    config_path = args.config
    audit_path = args.audit
    if run_dir and not routes_path:
        routes_path = str(Path(run_dir) / "routes.json")
        if config_path is None:
            candidate = Path(run_dir) / "config.json"
            config_path = str(candidate) if candidate.exists() else None
        if audit_path is None:
            candidate = Path(run_dir) / "audit_strict.json"
            audit_path = str(candidate) if candidate.exists() else None
        if args.out is None:
            args.out = str(Path(run_dir) / "statistics.json")
    if not routes_path:
        raise SystemExit("v3.metrics: --run-dir/--routes or --combined-dir or "
                         "--shapes required")
    build_plane_statistics(
        Path(routes_path).parent if run_dir is None else run_dir,
        out_path=args.out, audit_path=audit_path, config_path=config_path,
        skip_pair_audit=args.skip_pair_audit, skip_min_gaps=args.skip_min_gaps,
        quiet=args.quiet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
