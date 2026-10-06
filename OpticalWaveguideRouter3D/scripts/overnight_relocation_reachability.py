"""Relocation reachability, derived after the fact from saved states only.

For a saved state, rank every current near-distance pair in the SHARED legacy
priority order (degree sum desc, max degree desc, pair) and report the best rank
of a pair for which the R mode may actually move an already-elevated route. This
is the quantity step 17 used to explain why relocation was never evaluated; it is
recomputed here for the v5 start state and for every v5 terminal state so the
STRATIFIED change can be judged against the same yardstick.

Usage: .venv\\Scripts\\python.exe -B scripts\\overnight_relocation_reachability.py PROJECT OUTDIR
"""
import sys, json
from pathlib import Path
sys.path.insert(0, ".")
from src.geometry_3d import CosineTransition3D
from src.fixed_1024_routing import deserialize_route3d
from src.strategy_v2_3d import route_degrees, target_priority


def analyse(root, rel, restricted_to_elevated_movable=True):
    directory = root / rel
    routes = {r["route_id"]: deserialize_route3d(r["geometry"])
              for r in json.loads((directory / "final_routes.json").read_text(encoding="utf-8"))["routes"]}
    sets = json.loads((directory / "collision_sets.json").read_text(encoding="utf-8"))
    pairs = {tuple(p) for p in sets["final_collision_pairs"]}
    elevated = {i for i, r in routes.items() if any(isinstance(p, CosineTransition3D)
                                                     for p in r.primitives)}
    degrees = route_degrees(pairs)
    ordered = sorted(pairs, key=lambda p: target_priority(p, degrees))
    ranks = {}
    first_relocation = None; relocation_capable = 0
    for rank, pair in enumerate(ordered, start=1):
        ranks[pair] = rank
        movable = [r for r in pair if r in elevated]
        if movable:
            relocation_capable += 1
            if first_relocation is None:
                first_relocation = dict(rank=rank, pair=list(pair),
                                        movable_elevated=sorted(movable),
                                        elevated_movable_count=len(movable),
                                        both_sides_movable=len(movable) == 2)
    both = [p for p in ordered if all(r in elevated for r in p)]
    return dict(directory=str(directory), pairs=len(pairs), elevated_route_count=len(elevated),
                pairs_involving_elevated=sum(1 for p in pairs if p[0] in elevated or p[1] in elevated),
                relocation_movable_pairs=relocation_capable,
                best_relocation_rank=first_relocation,
                rank_of_best_pair_touching_elevated=min((ranks[p] for p in pairs
                                                         if p[0] in elevated or p[1] in elevated),
                                                        default=None),
                both_sides_elevated_pair_count=len(both),
                note=("rank is 1-based in the shared legacy order (degree sum desc, max degree "
                      "desc, pair) recomputed on the SAVED state; derived after the fact, it can "
                      "never influence a run"))


def main():
    root = Path(sys.argv[1]).resolve(); out = Path(sys.argv[2]).resolve()
    doc = dict(method="derived from saved states; no run is influenced", states={})
    doc["states"]["v5_main_start"] = analyse(root, "outputs/3d_strategy_v3/512_ablation/D_both_enabled")
    doc["states"]["v5_challenge_start"] = analyse(root, "outputs/3d_strategy_v4/512_full_layout/N2880")
    for shape in ("v5", "v6", "v7", "ideas"):
        base = out / shape
        if not base.is_dir():
            continue
        for folder in sorted(p for p in base.iterdir() if p.is_dir()):
            if not (folder / "final_routes.json").is_file() or folder.name.startswith("_"):
                continue
            key = shape + "/" + folder.name
            doc["states"][key] = analyse(root, str(folder.relative_to(root)))
            print(key, "best_relocation_rank",
                  (doc["states"][key]["best_relocation_rank"] or {}).get("rank"))
    target = out / "relocation_reachability_overnight.json"
    target.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print("wrote", target)


if __name__ == "__main__":
    main()
