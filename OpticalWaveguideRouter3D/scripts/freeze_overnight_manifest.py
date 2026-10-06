"""Freeze one round configuration list BEFORE its first formal run.

Writes outputs/overnight_3d_ideas/manifest/round_<name>.json with the exact group
list, every StrategySpec, the start state and the SHA256 of this file, plus the
cell definitions of the matrix. Refuses to overwrite an existing manifest unless
--force is given, and records any override explicitly.

Usage: .venv\\Scripts\\python.exe -B scripts\\freeze_overnight_manifest.py PROJECT OUTDIR \\
           --round v5 [--adoption path] [--force]
"""
import sys, json, hashlib, argparse
from pathlib import Path
from datetime import datetime


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project"); ap.add_argument("outdir")
    ap.add_argument("--round", required=True)
    ap.add_argument("--adoption", default=None)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(sys.argv[1:])
    root = Path(args.project).resolve(); out = Path(args.outdir).resolve()
    sys.path.insert(0, str(root)); sys.path.insert(0, str(root / "scripts"))
    import overnight_registry as REG
    adoption = {}
    if args.adoption:
        adoption = json.loads(Path(args.adoption).read_text(encoding="utf-8"))
    groups = REG.round_groups(args.round, adoption)
    manifest_dir = out / "manifest"; manifest_dir.mkdir(parents=True, exist_ok=True)
    target = manifest_dir / ("round_" + args.round + ".json")
    if target.is_file() and not args.force:
        raise SystemExit("manifest already frozen: " + str(target))
    cells = []
    for name, spec, mode, budget, start, control in groups:
        cells.append(dict(group=name, strategy=spec.name, spec=spec.as_dict(), mode=mode,
                          budget=budget, start_kind=start, control=control))
    doc = dict(round=args.round, frozen_at=datetime.now().isoformat(timespec="seconds"),
               adoption=adoption, adoption_rule=REG.ADOPTION_RULE,
               main_start=REG.MAIN_START, challenge_start=REG.CHALLENGE_START,
               main_budgets=list(REG.MAIN_BUDGETS), challenge_budget=REG.CHALLENGE_BUDGET,
               clearance_mm=REG.CLEARANCE_MM, required_radius_mm=REG.REQUIRED_RADIUS_MM,
               window_slack_mm=REG.WINDOW_SLACK_MM,
               idea_titles=REG.IDEA_TITLES, group_count=len(cells),
               groups=[c["group"] for c in cells], cells=cells,
               note=("frozen before the first formal evaluation of this round; the runner refuses "
                     "any group that is not listed here"))
    text = json.dumps(doc, indent=2)
    target.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    (manifest_dir / ("round_" + args.round + ".sha256")).write_text(digest, encoding="utf-8")
    print(json.dumps(dict(round=args.round, groups=len(cells), sha256=digest, path=str(target)),
                     indent=2))


if __name__ == "__main__":
    main()
