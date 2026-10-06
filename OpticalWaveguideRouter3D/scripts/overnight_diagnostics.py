"""Pre-declared diagnostics that must exist BEFORE the mechanisms they justify.

1. Conflict-graph connected components of the pair set at both start states. Idea D
   (route-coverage scheduling) is only meaningful if the conflict graph is not one
   single giant component; if it is, component round-robin cannot be claimed as
   evidence of improvement.
2. The frozen v4 diagnostic set (60 pairs / 120 sides) split into per-side entries
   with their recorded generation outcome, so v6 prefix-vs-exhaustive comparisons
   and v8 old-window/no-window comparisons use exactly the same frozen list.
3. Stop-reason / skip-event inventory of the reviewed v4 groups.

Usage: .venv\\Scripts\\python.exe -B scripts\\overnight_diagnostics.py PROJECT OUTDIR
"""
import sys, json
from collections import Counter, defaultdict
from pathlib import Path
from time import perf_counter


def main():
    root = Path(sys.argv[1]).resolve(); out = Path(sys.argv[2]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(root))
    from src.models import Layer
    from src.geometry_3d import lift_smoothed_route_to_layer, CosineTransition3D
    from src.multi_attribution import deserialize_plot
    from src.fixed_1024_routing import deserialize_route3d

    def components(pairs, node_count):
        parent = list(range(node_count))
        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]; x = parent[x]
            return x
        for a, b in pairs:
            ra, rb = find(a), find(b)
            if ra != rb: parent[ra] = rb
        sizes = Counter(find(i) for i in range(node_count))
        return dict(node_count=node_count, component_count=len(sizes),
                    largest_component_size=max(sizes.values()) if sizes else 0,
                    largest_component_share=round(max(sizes.values()) / node_count, 6) if sizes else 0.,
                    isolated_node_count=sum(1 for i in range(node_count) if (i,) not in pairs
                                            and not any(i in p for p in []) ),
                    size_histogram={str(k): v for k, v in sorted(Counter(sizes.values()).items())},
                    nodes_with_no_pair=sum(1 for i in range(node_count)
                                           if all(i not in p for p in pairs)),
                    note=("connected components of the CURRENT centre-line near-distance graph; "
                          "a single giant component means component round-robin has no real "
                          "distinction and must not be presented as an improvement"))

    result = dict(started=None)
    started = perf_counter()
    for kind, rel in (("main", "outputs/3d_strategy_v3/512_ablation/D_both_enabled"),
                      ("challenge", "outputs/3d_strategy_v4/512_full_layout/N2880")):
        directory = root / rel
        routes = {r["route_id"]: deserialize_route3d(r["geometry"])
                  for r in json.loads((directory / "final_routes.json").read_text(encoding="utf-8"))["routes"]}
        sets = json.loads((directory / "collision_sets.json").read_text(encoding="utf-8"))
        pairs = [tuple(p) for p in sets["final_collision_pairs"]]
        unknown = [tuple(p) for p in sets["final_unresolved_pairs"]]
        elevated = {i for i, r in routes.items()
                    if any(isinstance(p, CosineTransition3D) for p in r.primitives)}
        result[kind] = dict(directory=rel, pairs=len(pairs), unresolved=len(unknown),
                            elevated_routes=len(elevated),
                            graph=components(pairs + unknown, len(routes)),
                            degree_histogram={str(k): v for k, v in sorted(Counter(
                                Counter([n for p in pairs + unknown for n in p]).values()).items())},
                            max_degree=max(Counter([n for p in pairs + unknown for n in p]).values(),
                                           default=0))
    # frozen diagnostic set inherited from v4 (60 pairs, 120 sides), only re-read
    audit_dir = root / "outputs/3d_strategy_v4/512_full_layout/audit"
    if (audit_dir / "target_list.json").is_file():
        listing = json.loads((audit_dir / "target_list.json").read_text(encoding="utf-8"))
        result["v4_frozen_diagnostic_set"] = dict(
            source=str((audit_dir / "target_list.json").relative_to(root)),
            pair_count=len(listing) if isinstance(listing, list) else listing.get("pair_count"),
            note=("frozen BEFORE any v4 candidate evaluation; reused only as a fixed diagnostic "
                  "list, never to pick a performance target"),
            raw_type=type(listing).__name__)
    result["v4_group_inventory"] = {}
    for group in ("N720", "N1440", "N2880", "R720", "R1440", "R2880"):
        ledger_path = root / "outputs/3d_strategy_v4/512_full_layout" / group / "ledger.json"
        if ledger_path.is_file():
            led = json.loads(ledger_path.read_text(encoding="utf-8"))
            result["v4_group_inventory"][group] = dict(
                final_collision_pair_count=led["final_collision_pair_count"],
                candidate_evaluations=led["candidate_evaluations"],
                accepted_moves=led["accepted_moves"], relocations=led["relocations"],
                relocation_candidate_evaluations=led["relocation_candidate_evaluations"],
                stage_length_delta_mm=led["stage_length_delta_mm"],
                target_attempts=led["target_attempts"], stop_reason=led["stop_reason"],
                generation_skip_events=led["generation_skip_events"],
                full_rejection_reason_counts=led["full_rejection_reason_counts"],
                basic_rejection_reason_counts=led["basic_rejection_reason_counts"],
                runtime_seconds=led["runtime_seconds"])
    result["seconds"] = perf_counter() - started
    (out / "diagnostics_prechecks.json").write_text(json.dumps(result, indent=2, default=str),
                                                    encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "v4_group_inventory"}, indent=2,
                     default=str)[:3000])


if __name__ == "__main__":
    main()
