"""Cross-check the FSLW strict crossing policy: router index vs independent validator.

fslw/SPEC.md §4 requires the router-side decision
(``four_side_1024.d56.index.D56Index`` with ``width=0.05, gap=0.03`` ->
centreline clearance 0.080 mm and ``crossing_policy='strict'``) and the
independent authoritative validator (``four_side_1024.fslw.validate_fslw`` with
``policy='strict'``) to agree on every route pair of every height-plane
``routes.json`` (per-route-pair ``mismatch = 0``).

The harness isolates each broad-phase route pair in both implementations (a
one-route router index and ``validate_fslw.evaluate_pair``), compares the
boolean verdicts, and additionally compares the per-pair crossing count and the
per-experiment crossing/window totals.  Run-level audit counters live in
``validate_fslw.scan_and_audit`` (``audit_strict.json``); this script is the
independent pair-verdict check.

Usage::

    .venv\\Scripts\\python.exe -m four_side_1024.fslw.crosscheck_fslw \\
        --run-dir outputs/four_side_1024_fslw_R40_gap30_abcd/planes/V1/B/z1 \\
        --output outputs/four_side_1024_fslw_R40_gap30_abcd/comparison/crosscheck_V1_B_z1.json

    # all plane routes.json of the experiment in one pass
    .venv\\Scripts\\python.exe -m four_side_1024.fslw.crosscheck_fslw \\
        --scan-root outputs/four_side_1024_fslw_R40_gap30_abcd \\
        --output-dir outputs/four_side_1024_fslw_R40_gap30_abcd/comparison

Exit code 0 = PASS (mismatch == 0), 1 = FAIL, 2 = interface/input problem.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from four_side_1024.fslw import validate_fslw as V

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = (PROJECT_ROOT / "outputs"
                      / "four_side_1024_fslw_R40_gap30_abcd" / "comparison")
ROUTED_STATUS = {"routed", "success", "succeeded", "ok", "routed_ok"}


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _router_index_module():
    from four_side_1024.d56 import index as router_index
    return router_index


def _status_of(record):
    status = record.get("_status")
    if status is not None:
        return status
    status = record.get("status")
    if status is None:
        return "routed"
    return str(status).strip().lower()


def load_routed_primitives(routes_path):
    """``[(route_id, primitives)]`` for every routed record of a plane file."""
    records, info = V.load_routes_file(routes_path)
    routed = []
    for record in records:
        if _status_of(record) not in ROUTED_STATUS:
            continue
        primitives = record.get("primitives")
        if not primitives:
            continue
        routed.append((record.get("route_id"), primitives))
    return routed, info


def _plane_tag(routes_path, records):
    meta = V._payload_meta(routes_path)
    return V.detect_plane(meta, records, routes_path)


def crosscheck(routes_path, *, width=None, edge_gap=None, clearance=None,
               radius=None, plane=None, max_pairs=None, verbose=False):
    """Compare strict verdicts pair by pair; returns a JSON-serialisable dict."""
    started = time.perf_counter()
    routes_path = Path(routes_path)
    if not routes_path.exists():
        raise FileNotFoundError(f"routes file not found: {routes_path}")
    routed, info = load_routed_primitives(routes_path)
    if not routed:
        raise ValueError(f"no routed primitives in {routes_path}")
    records, _info = V.load_routes_file(routes_path)
    meta = V._payload_meta(routes_path)
    plane_tag = plane if plane is not None else V.detect_plane(meta, records,
                                                               routes_path)
    params = V.resolve_parameters(routes_path, None, radius=radius,
                                  edge_gap=edge_gap, clearance=clearance,
                                  width=width, payload_meta=meta)
    param_width = params["width"]
    param_clearance = params["clearance"]
    param_gap = param_clearance - param_width
    if param_gap <= 0:
        raise ValueError(f"invalid gap {param_gap} from parameters {params}")
    router = _router_index_module()
    try:
        router.D56Index(width=param_width, gap=param_gap,
                        crossing_policy="strict")
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            "d56.index.D56Index has no strict crossing policy with the FSLW "
            f"process parameters ({exc})") from exc

    validator_prepared = [V.prepare_route(primitives, route_id)
                          for route_id, primitives in routed]
    router_prepared = [router.prepare(primitives)
                       for _route_id, primitives in routed]
    route_ids = [route_id for route_id, _primitives in routed]

    pairs = V._candidate_pairs(validator_prepared,
                               param_clearance + 2.0 * V.SAGITTA)
    if max_pairs is not None:
        pairs = pairs[:max_pairs]
    by_first = {}
    for index_a, index_b in pairs:
        by_first.setdefault(index_a, []).append(index_b)

    mismatches = []
    compared = 0
    invalid_validator = 0
    invalid_router = 0
    invalid_both = 0
    validator_crossing_count = 0
    router_crossing_count = 0
    crossing_count_mismatch_pairs = []
    validator_window_count = 0
    router_window_count = 0
    router_window_total_mm = 0.0
    router_window_max_mm = 0.0
    validator_max_half_mm = 0.0
    validator_total_length_sum = 0.0
    validator_sides = 0
    invalid_pairs = []
    validator_failed_route_ids = set()
    router_failed_route_ids = set()
    for index_a in sorted(by_first):
        index = router.D56Index(width=param_width, gap=param_gap,
                                crossing_policy="strict")
        index.add(route_ids[index_a], router_prepared[index_a])
        first_validator = validator_prepared[index_a]
        for index_b in by_first[index_a]:
            compared += 1
            result = index.evaluate(router_prepared[index_b],
                                    stop_on_invalid=True)
            router_valid = bool(result.valid)
            router_reason = None if router_valid else result.reason
            validator_result = V.evaluate_pair(
                first_validator, validator_prepared[index_b], policy="strict")
            validator_valid = True if validator_result is None else \
                bool(validator_result["valid"])
            validator_crossing_count_pair = 0
            router_crossing_count_pair = len(result.crossings)
            validator_kinds = []
            validator_distance = None
            validator_position = None
            if validator_result is not None:
                validator_crossing_count_pair = len(
                    validator_result["crossings"])
                for detail in validator_result["violations"]:
                    kind = detail.get("kind")
                    if kind not in validator_kinds:
                        validator_kinds.append(kind)
                for crossing in validator_result["crossings"]:
                    validator_window_count += 1
                    halves = (crossing.get("half_a_left"),
                              crossing.get("half_a_right"),
                              crossing.get("half_b_left"),
                              crossing.get("half_b_right"))
                    if any(value is None for value in halves):
                        continue
                    validator_max_half_mm = max(validator_max_half_mm,
                                                max(halves))
                    validator_total_length_sum += sum(halves)
                    validator_sides += len(halves)
                if validator_result["violations"]:
                    first_detail = validator_result["violations"][0]
                    validator_distance = first_detail.get("distance_mm")
                    if first_detail.get("x") is not None:
                        validator_position = (first_detail.get("x"),
                                              first_detail.get("y"))
            if validator_valid:
                validator_crossing_count += validator_crossing_count_pair
            else:
                validator_failed_route_ids.add(route_ids[index_a])
                validator_failed_route_ids.add(route_ids[index_b])
            if router_valid:
                router_crossing_count += router_crossing_count_pair
            else:
                router_failed_route_ids.add(route_ids[index_a])
                router_failed_route_ids.add(route_ids[index_b])
            if (validator_valid and router_valid
                    and validator_crossing_count_pair != router_crossing_count_pair):
                crossing_count_mismatch_pairs.append({
                    "route_a": route_ids[index_a],
                    "route_b": route_ids[index_b],
                    "validator_crossings": validator_crossing_count_pair,
                    "router_crossings": router_crossing_count_pair,
                })
            if not validator_valid:
                invalid_validator += 1
            if not router_valid:
                invalid_router += 1
            if not validator_valid and not router_valid:
                invalid_both += 1
            if not validator_valid or not router_valid:
                invalid_pairs.append({
                    "route_a": route_ids[index_a],
                    "route_b": route_ids[index_b],
                    "validator_valid": validator_valid,
                    "validator_kinds": validator_kinds,
                    "validator_first_distance_mm": validator_distance,
                    "validator_first_position": validator_position,
                    "router_valid": router_valid,
                    "router_reason": router_reason,
                    "router_min_spacing_mm": result.min_spacing_mm,
                })
            if validator_valid != router_valid:
                mismatches.append({
                    "route_a": route_ids[index_a],
                    "route_b": route_ids[index_b],
                    "validator_valid": validator_valid,
                    "validator_kinds": validator_kinds,
                    "validator_first_distance_mm": validator_distance,
                    "validator_first_position": validator_position,
                    "router_valid": router_valid,
                    "router_reason": router_reason,
                    "router_min_spacing_mm": result.min_spacing_mm,
                })
        router_window_count += index.window_count
        router_window_total_mm += index.window_total_mm
        router_window_max_mm = max(router_window_max_mm, index.window_max_mm)
        if verbose and len(by_first) > 1:
            print(f"  crosscheck {routes_path.name}: "
                  f"{len(by_first)}/{len(validator_prepared)} first-routes",
                  flush=True)
    elapsed = time.perf_counter() - started
    invalid_route_ids = sorted(validator_failed_route_ids
                               | router_failed_route_ids)
    summary = {
        "schema": "four_side_1024_fslw_strict_crosscheck_v1",
        "roles": {
            "router": "four_side_1024.d56.index.D56Index("
                      f"width={param_width:g}, gap={param_gap:g}, "
                      "crossing_policy='strict')",
            "validator": "four_side_1024.fslw.validate_fslw policy='strict' "
                         "(authoritative)",
        },
        "routes_file": str(routes_path),
        "routes_sha256": _sha256(routes_path),
        "plane": plane_tag,
        "process": {
            "width_mm": param_width,
            "edge_gap_mm": param_gap,
            "centerline_clearance_mm": param_clearance,
            "radius_mm": params.get("radius"),
            "parameters_source": params.get("parameters_source"),
        },
        "routed_route_count": len(routed),
        "compared_pair_count": compared,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "validator_invalid_pairs": invalid_validator,
        "router_invalid_pairs": invalid_router,
        "invalid_both_pairs": invalid_both,
        "strict_invalid_pairs": invalid_pairs,
        "strict_failed_route_count": len(invalid_route_ids),
        "strict_failed_route_ids": invalid_route_ids,
        "strict_passed_route_count": len(routed) - len(invalid_route_ids),
        "validator_failed_route_ids": sorted(validator_failed_route_ids),
        "router_failed_route_ids": sorted(router_failed_route_ids),
        "validator_passed_route_count":
            len(routed) - len(validator_failed_route_ids),
        "router_passed_route_count":
            len(routed) - len(router_failed_route_ids),
        "crossing_count": {
            "validator": validator_crossing_count,
            "router": router_crossing_count,
            "matches": validator_crossing_count == router_crossing_count,
            "per_pair_mismatch_count": len(crossing_count_mismatch_pairs),
            "per_pair_mismatches": crossing_count_mismatch_pairs[:20],
        },
        "window_consistency": {
            "validator_window_count": validator_window_count,
            "router_window_count": router_window_count,
            "count_matches": validator_window_count == router_window_count,
            "validator_max_half_mm": (validator_max_half_mm
                                      if validator_sides else None),
            "validator_mean_half_mm": (validator_total_length_sum
                                       / (4.0 * validator_window_count)
                                       if validator_window_count else None),
            "router_max_half_mm": (router_window_max_mm
                                   if router_window_count else None),
            "router_mean_total_window_mm": (router_window_total_mm
                                            / router_window_count
                                            if router_window_count else None),
        },
        "runtime_seconds": elapsed,
        "passed": not mismatches and not crossing_count_mismatch_pairs,
    }
    return summary


def _print_summary(summary, verbose=False):
    window = summary["window_consistency"]
    crossing = summary["crossing_count"]
    process = summary["process"]
    print("=" * 78)
    print("FSLW STRICT POLICY CROSSCHECK  (router index vs independent validator)")
    print("=" * 78)
    print(f"routes file            : {summary['routes_file']}")
    print(f"plane / process        : {summary['plane']} / R={process['radius_mm']} "
          f"gap={process['edge_gap_mm']} clearance={process['centerline_clearance_mm']}")
    print(f"routed routes          : {summary['routed_route_count']}")
    print(f"compared route pairs   : {summary['compared_pair_count']}")
    print(f"validator invalid pairs: {summary['validator_invalid_pairs']}")
    print(f"router invalid pairs   : {summary['router_invalid_pairs']}")
    print(f"invalid in both        : {summary['invalid_both_pairs']}")
    print(f"strict routes passing  : validator={summary['validator_passed_route_count']}"
          f" router={summary['router_passed_route_count']}")
    print(f"crossings (valid pairs): validator={crossing['validator']}"
          f" router={crossing['router']} (match={crossing['matches']},"
          f" per-pair mismatches={crossing['per_pair_mismatch_count']})")
    print(f"crossing windows       : validator={window['validator_window_count']}"
          f" router={window['router_window_count']}"
          f" (match={window['count_matches']})")
    print(f"window half max        : validator={window['validator_max_half_mm']}"
          f" mm  router={window['router_max_half_mm']} mm")
    print(f"runtime                : {summary['runtime_seconds']:.2f} s")
    for item in summary["strict_invalid_pairs"][:20]:
        print(f"  strict-invalid pair  {item['route_a']} <-> {item['route_b']}: "
              f"validator={item['validator_kinds'] or 'valid'} "
              f"router={item['router_reason'] or 'valid'}"
              f" (validator d={item['validator_first_distance_mm']}, "
              f"router d={item['router_min_spacing_mm']})")
    if summary["mismatches"]:
        for item in summary["mismatches"][:20]:
            print(f"  MISMATCH  {item['route_a']} <-> {item['route_b']}: "
                  f"validator_valid={item['validator_valid']} "
                  f"({item['validator_kinds']}) router_valid={item['router_valid']} "
                  f"({item['router_reason']})")
    verdict = "PASS" if summary["passed"] else "FAIL"
    print(f"{verdict}: mismatch={summary['mismatch_count']} "
          f"crossing-count-mismatches={crossing['per_pair_mismatch_count']} "
          f"(expected 0; router and validator must agree on every route pair)")
    return summary["passed"]


def _relative_name(routes_path, root):
    root = Path(root)
    relative = Path(routes_path).relative_to(root)
    parts = list(relative.parts[:-1])
    if root.name.lower() in ("planes", "sensitivity"):
        parts = [root.name] + parts
    return "__".join(parts)


def scan_and_crosscheck(scan_root, output_dir, *, verbose=False):
    """Cross-check every plane routes.json; writes one JSON per run + summary."""
    root = Path(scan_root)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    all_passed = True
    for routes_path in V.find_plane_routes_files(root):
        name = _relative_name(routes_path, root)
        summary = crosscheck(routes_path, verbose=verbose)
        out_path = output_dir / f"crosscheck_{name}.json"
        out_path.write_text(json.dumps(summary, indent=1, ensure_ascii=False),
                            encoding="utf-8")
        results[name] = {
            "routes_file": str(routes_path),
            "plane": summary["plane"],
            "routed": summary["routed_route_count"],
            "compared_pairs": summary["compared_pair_count"],
            "mismatch": summary["mismatch_count"],
            "validator_invalid_pairs": summary["validator_invalid_pairs"],
            "router_invalid_pairs": summary["router_invalid_pairs"],
            "invalid_pairs": len(summary["strict_invalid_pairs"]),
            "crossings_validator": summary["crossing_count"]["validator"],
            "crossings_router": summary["crossing_count"]["router"],
            "windows_validator": summary["window_consistency"][
                "validator_window_count"],
            "windows_router": summary["window_consistency"]["router_window_count"],
            "max_half_validator_mm": summary["window_consistency"][
                "validator_max_half_mm"],
            "max_half_router_mm": summary["window_consistency"][
                "router_max_half_mm"],
            "radius_mm": summary["process"]["radius_mm"],
            "clearance_mm": summary["process"]["centerline_clearance_mm"],
            "runtime_seconds": summary["runtime_seconds"],
            "passed": summary["passed"],
            "crosscheck_file": str(out_path),
        }
        all_passed = all_passed and summary["passed"]
        print(f"{name:45s} routed={summary['routed_route_count']:4d} "
              f"pairs={summary['compared_pair_count']:6d} "
              f"mismatch={summary['mismatch_count']} "
              f"invalid={summary['validator_invalid_pairs']}/"
              f"{summary['router_invalid_pairs']} "
              f"{'PASS' if summary['passed'] else 'FAIL'} "
              f"{summary['runtime_seconds']:.1f}s", flush=True)
    summary = {
        "schema": "four_side_1024_fslw_strict_crosscheck_summary_v1",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scan_root": str(root),
        "plane_count": len(results),
        "total_mismatch": sum(item["mismatch"] for item in results.values()),
        "all_passed": all_passed if results else None,
        "experiments": results,
    }
    summary_path = output_dir / "crosscheck_summary.json"
    summary_path.write_text(json.dumps(summary, indent=1, ensure_ascii=False),
                            encoding="utf-8")
    print(f"summary written: {summary_path}")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Cross-check the FSLW strict crossing-policy verdicts "
                    "between the router index and the independent validator.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--routes", type=Path, default=None,
                       help="plane routes JSON to cross-check")
    group.add_argument("--run-dir", type=Path, default=None,
                       help="plane run directory containing routes.json")
    group.add_argument("--scan-root", type=Path, default=None,
                       help="cross-check every routes.json below planes/ and "
                            "sensitivity/")
    parser.add_argument("--output", type=Path, default=None,
                        help="full JSON report path (single run)")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="scan mode output directory (default "
                             "<scan-root>/comparison)")
    parser.add_argument("--max-pairs", type=int, default=None,
                        help="limit the number of compared route pairs (debug)")
    parser.add_argument("--width", type=float, default=None,
                        help="override waveguide width (default 0.050 mm)")
    parser.add_argument("--edge-gap", type=float, default=None,
                        help="override edge gap (default 0.030 mm)")
    parser.add_argument("--clearance", type=float, default=None,
                        help="override centreline clearance (default 0.080 mm)")
    parser.add_argument("--radius", type=float, default=None,
                        help="override validator radius (default 40.0 mm)")
    parser.add_argument("--plane", choices=V.PLANE_NAMES, default=None,
                        help="override plane tag")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.scan_root is not None:
            output_dir = args.output_dir or (Path(args.scan_root) / "comparison")
            summary = scan_and_crosscheck(args.scan_root, output_dir,
                                          verbose=args.verbose)
            print(json.dumps({"plane_count": summary["plane_count"],
                              "total_mismatch": summary["total_mismatch"],
                              "all_passed": summary["all_passed"]}, indent=2))
            return 0 if summary["all_passed"] else 1
        routes_path = args.routes
        if routes_path is None:
            if args.run_dir is None:
                parser.error("one of --routes / --run-dir / --scan-root is required")
            routes_path = Path(args.run_dir) / "routes.json"
        summary = crosscheck(
            routes_path, width=args.width, edge_gap=args.edge_gap,
            clearance=args.clearance, radius=args.radius, plane=args.plane,
            max_pairs=args.max_pairs, verbose=args.verbose)
    except RuntimeError as exc:
        print(f"INTERFACE-ERROR: {exc}")
        return 2
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2
    if args.quiet:
        passed = summary["passed"]
        print(f"{'PASS' if passed else 'FAIL'}: "
              f"mismatch={summary['mismatch_count']}")
    else:
        passed = _print_summary(summary, verbose=args.verbose)
    if args.output is not None:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(summary, indent=1, ensure_ascii=False),
                          encoding="utf-8")
        if not args.quiet:
            print(f"report written: {output}")
    return 0 if passed else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
