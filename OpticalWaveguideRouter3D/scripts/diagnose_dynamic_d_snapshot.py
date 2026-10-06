"""Read-only four-route snapshot diagnostics in a declared hypothetical state.

Run as a module with connection and snapshot paths. This never replays history.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from src.hierarchy_diagnostic import diagnose_dynamic_d, RADIUS_MM
from src.io import load_legacy_512_snapshot
from src.models import PMT
from src.router_2d import prepare_waveguide_2d, _algorithmic_endpoints


def sample_snapshot(connections: Path, snapshot: Path) -> dict:
    """Use an explicitly empty commit prefix; do not infer historical states."""
    before_hashes = [sha256(p.read_bytes()).hexdigest() for p in (connections, snapshot)]
    routes = load_legacy_512_snapshot(connections, snapshot)
    grouped = {}
    special = set()
    representatives = {}
    prepared = {}
    for w in routes:
        for port in (w.start_port, w.end_port):
            grouped.setdefault(port.pmt_id, []).append(port)
        prep = prepare_waveguide_2d(w, 150.0, 0.0)
        ends = _algorithmic_endpoints(w, prep, 1e-9)
        prepared[w.id] = (prep, ends)
        if prep.route_type == "z" and abs(ends[0].position.x - ends[1].position.x) < 2*RADIUS_MM - 1e-9:
            special.add(w.id)
            continue
        start_side = "top" if ends[0].position.y == 150.0 else "bottom"
        end_side = "top" if ends[1].position.y == 150.0 else "bottom"
        category = start_side + "-U" if prep.route_type == "u" else start_side + "->" + end_side + " Z"
        representatives.setdefault(category, w)
    expected = ("top-U", "bottom-U", "top->bottom Z", "bottom->top Z")
    if set(representatives) != set(expected):
        raise ValueError("Four ordinary categories are required.")
    states = {w.id: "unsupported" if w.id in special else "pending_for_horizontal_routing" for w in routes}
    prefix = []
    pmts = [PMT(pid, ports) for pid, ports in grouped.items()]
    frozen = deepcopy((routes, pmts, states, prefix, special))
    samples = []
    for category in expected:
        w = representatives[category]
        prep, endpoints = prepared[w.id]
        result = diagnose_dynamic_d(w, prep, endpoints, pmts, routes, states, prefix, frozenset(special))
        if result["status"] != "OK":
            raise ValueError(f"Sample {w.id}: {result}")
        samples.append(result)
    if (routes, pmts, states, prefix, special) != frozen:
        raise AssertionError("Diagnostic modified input.")
    after_hashes = [sha256(p.read_bytes()).hexdigest() for p in (connections, snapshot)]
    if before_hashes != after_hashes:
        raise AssertionError("Source files changed.")
    return {
        "scenario": "PROJECT-SPECIFIC hypothetical state: all ordinary pending; special unsupported; commit prefix empty",
        "historical_reconstruction": False,
        "route_451": "NOT RECONSTRUCTABLE FROM SAVED STATE",
        "route_451_note": "Saved commit evidence alone does not supply an explicit complete pending_for_horizontal_routing state; no history inferred.",
        "route_count": len(routes), "pmt_count": len(pmts), "special_count": len(special),
        "source_sha256": before_hashes, "source_files_unchanged": True,
        "input_objects_unchanged": True, "samples": samples,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("connections", type=Path)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    print(json.dumps(sample_snapshot(args.connections, args.snapshot), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
