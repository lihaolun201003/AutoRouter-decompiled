"""Cross-check the strict crossing policy: router index vs independent validator.

SPEC ``four_side_1024/abcd/SPEC.md`` §2.2 requires the router-side decision
(``four_side_1024.d56.index.D56Index(crossing_policy='strict')``) and the
independent authoritative validator (``four_side_1024.d56.validate_d56`` with
``policy='strict'``) to agree on the legality of **every route pair** of a
saved routes file.  This harness checks exactly that:

* both implementations parse the same routed ``primitives``;
* for every broad-phase candidate route pair (route bounding boxes within
  ``clearance + 2*sagitta``) it isolates the pair in both implementations
  (a one-route router index and ``validate_d56.evaluate_pair``) and compares the
  boolean verdict;
* per-route-pair mismatches are listed with both reasons and metrics;
* the router window counters and the validator window statistics are compared
  as a secondary consistency signal (number of crossing windows).

Expected result on the historical deliverable
``outputs/four_side_1024_d56_optimized/routes.json`` (467 routed routes):

    465 / 467 routes pass strict, exactly one route pair (460, 989) fails as
    ``crossing_window_overlap`` in both implementations, ``mismatch=0``.

Usage::

    .venv\\Scripts\\python.exe -m four_side_1024.abcd.crosscheck_strict
    .venv\\Scripts\\python.exe -m four_side_1024.abcd.crosscheck_strict \\
        --routes outputs/four_side_1024_v1_v2_abcd/V1_B/routes.json \\
        --output outputs/four_side_1024_v1_v2_abcd/comparison/crosscheck_strict.json

Exit code 0 = PASS (mismatch == 0), 1 = FAIL (mismatch > 0), 2 = interface
problem (e.g. the installed router index has no strict policy yet).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from four_side_1024.d56 import validate_d56 as V

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROUTES = (PROJECT_ROOT / "outputs" / "four_side_1024_d56_optimized"
                  / "routes.json")

ROUTED_STATUS = {"routed", "success", "succeeded", "ok", "routed_ok"}


def _status_of(record):
    status = record.get("_status")
    if status is not None:
        return status
    status = record.get("status")
    if status is None:
        return "routed"
    return str(status).strip().lower()


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_routed_primitives(routes_path):
    """Return ``[(route_id, primitives)]`` for every routed record in the file."""
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


def _router_index_module():
    from four_side_1024.d56 import index as router_index
    return router_index


def crosscheck(routes_path, max_pairs=None, progress=None):
    """Compare strict verdicts pair by pair; returns a JSON-serialisable dict."""
    started = time.perf_counter()
    routes_path = Path(routes_path)
    if not routes_path.exists():
        raise FileNotFoundError(f"routes file not found: {routes_path}")
    routed, info = load_routed_primitives(routes_path)
    if not routed:
        raise ValueError(f"no routed primitives in {routes_path}")
    router = _router_index_module()
    try:
        router.D56Index(crossing_policy="strict")
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            "four_side_1024.d56.index.D56Index has no crossing_policy='strict' "
            f"support yet ({exc}); coordinate with the index owner") from exc

    validator_prepared = [V.prepare_route(primitives, route_id)
                          for route_id, primitives in routed]
    router_prepared = [router.prepare(primitives)
                       for _route_id, primitives in routed]
    route_ids = [route_id for route_id, _primitives in routed]

    pairs = V._candidate_pairs(validator_prepared, V.CLEARANCE + 2.0 * V.SAGITTA)
    if max_pairs is not None:
        pairs = pairs[:max_pairs]
    # Group the candidate pairs by their first route so one router index (with
    # a single route) can isolate every pair of that route.
    by_first = {}
    for index_a, index_b in pairs:
        by_first.setdefault(index_a, []).append(index_b)

    mismatches = []
    compared = 0
    invalid_validator = 0
    invalid_router = 0
    invalid_both = 0
    validator_window_count = 0
    router_window_count = 0
    router_window_total_mm = 0.0
    router_window_max_mm = 0.0
    validator_max_half_mm = 0.0
    validator_total_length_sum = 0.0
    validator_sides = 0
    invalid_pairs = []
    # Crossing-count consistency (valid pairs only, matching the audit counter).
    validator_crossing_count = 0
    router_crossing_count = 0
    crossing_count_mismatch_pairs = []
    validator_failed_route_ids = set()
    router_failed_route_ids = set()
    for index_a in sorted(by_first):
        index = router.D56Index(crossing_policy="strict")
        index.add(route_ids[index_a], router_prepared[index_a])
        first_validator = validator_prepared[index_a]
        for index_b in by_first[index_a]:
            compared += 1
            result = index.evaluate(router_prepared[index_b], stop_on_invalid=True)
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
                validator_crossing_count_pair = len(validator_result["crossings"])
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
        if progress is not None and len(by_first) > 1:
            progress(len(by_first), len(validator_prepared))
    elapsed = time.perf_counter() - started
    invalid_route_ids = sorted({
        item["route_a"] for item in invalid_pairs
        if not item["validator_valid"] or not item["router_valid"]}
        | {item["route_b"] for item in invalid_pairs
           if not item["validator_valid"] or not item["router_valid"]})
    summary = {
        "schema": "four_side_1024_abcd_strict_crosscheck_v1",
        "roles": {
            "router": "four_side_1024.d56.index.D56Index(crossing_policy='strict')",
            "validator": "four_side_1024.d56.validate_d56 policy='strict' (authoritative)",
        },
        "routes_file": str(routes_path),
        "routes_sha256": _sha256(routes_path),
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
    print("=" * 78)
    print("STRICT POLICY CROSSCHECK  (router index vs independent validator)")
    print("=" * 78)
    print(f"routes file            : {summary['routes_file']}")
    print(f"routed routes          : {summary['routed_route_count']}")
    print(f"compared route pairs   : {summary['compared_pair_count']}")
    print(f"validator invalid pairs: {summary['validator_invalid_pairs']}")
    print(f"router invalid pairs   : {summary['router_invalid_pairs']}")
    print(f"invalid in both        : {summary['invalid_both_pairs']}")
    print(f"strict routes passing  : validator={summary['validator_passed_route_count']}"
          f" router={summary['router_passed_route_count']}"
          f"  (invalid pair count={len(summary['strict_invalid_pairs'])})")
    print(f"crossings (valid pairs): validator={summary['crossing_count']['validator']}"
          f" router={summary['crossing_count']['router']}"
          f" (match={summary['crossing_count']['matches']},"
          f" per-pair mismatches={summary['crossing_count']['per_pair_mismatch_count']})")
    print(f"crossing windows       : validator={window['validator_window_count']}"
          f" router={window['router_window_count']}"
          f" (match={window['count_matches']})")
    print(f"window half max        : validator={window['validator_max_half_mm']}"
          f" mm  router={window['router_max_half_mm']} mm")
    print(f"runtime                : {summary['runtime_seconds']:.2f} s")
    for item in summary["strict_invalid_pairs"]:
        print(f"  strict-invalid pair  {item['route_a']} <-> {item['route_b']}: "
              f"validator={item['validator_kinds'] or 'valid'} "
              f"router={item['router_reason'] or 'valid'}"
              f" (validator d={item['validator_first_distance_mm']}, "
              f"router d={item['router_min_spacing_mm']})")
    if verbose:
        for item in summary["mismatches"]:
            print(f"  MISMATCH  {item['route_a']} <-> {item['route_b']}: "
                  f"validator_valid={item['validator_valid']} "
                  f"({item['validator_kinds']}) "
                  f"router_valid={item['router_valid']} "
                  f"({item['router_reason']})")
    elif summary["mismatches"]:
        for item in summary["mismatches"][:20]:
            print(f"  MISMATCH  {item['route_a']} <-> {item['route_b']}: "
                  f"validator_valid={item['validator_valid']} "
                  f"({item['validator_kinds']}) "
                  f"router_valid={item['router_valid']} "
                  f"({item['router_reason']})")
    verdict = "PASS" if summary["passed"] else "FAIL"
    print(f"{verdict}: mismatch={summary['mismatch_count']} "
          f"crossing-count-mismatches="
          f"{summary['crossing_count']['per_pair_mismatch_count']} "
          f"(expected 0; router and validator must agree on every route pair)")
    return summary["passed"]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Cross-check strict crossing-policy verdicts between the "
                    "router index and the independent validator.")
    parser.add_argument("--routes", type=Path, default=DEFAULT_ROUTES,
                        help="routes JSON to cross-check "
                             "(default: historical optimized D56 deliverable)")
    parser.add_argument("--output", type=Path, default=None,
                        help="optional path for the full JSON report")
    parser.add_argument("--max-pairs", type=int, default=None,
                        help="limit the number of compared route pairs (debug)")
    parser.add_argument("--verbose", action="store_true",
                        help="print every mismatch instead of the first 20")
    parser.add_argument("--quiet", action="store_true",
                        help="only print the final PASS/FAIL line")
    args = parser.parse_args(argv)
    try:
        summary = crosscheck(args.routes, max_pairs=args.max_pairs)
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
        output.write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                          encoding="utf-8")
        if not args.quiet:
            print(f"report written: {output}")
    return 0 if passed else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
