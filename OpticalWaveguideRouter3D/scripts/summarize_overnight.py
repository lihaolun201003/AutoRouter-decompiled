"""Aggregate ONE overnight round of scripts/run_overnight_3d.py into one row per group.

Usage (project root):
    .venv\Scripts\python.exe -B scripts\summarize_overnight.py PROJECT OUTDIR \
        --round v5 [--adopt]

A group is only considered when it is listed in the FROZEN manifest
OUTDIR/manifest/round_<round>.json; the manifest is never bypassed by listing the
round folder. Every directory under the round folder is still inspected and any
directory that cannot be matched to a manifest group is reported in
skipped_unknown_directories (and, if it holds a complete run, in excluded_rows)
instead of being silently included.

Outputs (OUTDIR/<round>/):
    comparison.csv        one row per completed, manifest-matched group; the frozen
                          identity columns (group, strategy, mode, budget,
                          start_kind, control) come from the manifest cell and the
                          row carries manifest_sha256 of the round it came from
    summary_<round>.json  the same rows plus missing_fields, column_sources,
                          recheck_geometry, coverage, the legacy-equivalence verdict
                          of scripts/overnight_equiv_check.py and the skip/exclusion
                          accounting
    adoption.json         only with --adopt and only when the pre-declared rule in
                          scripts/overnight_registry.py ADOPTION_RULE can be applied

Nothing is invented: a value absent from every declared source becomes null in
JSON, an empty field in CSV, and is listed in a 'missing_fields' list.
Not-yet-finished groups are skipped and counted, never guessed.
"""
import argparse
import ast
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

GENERATOR = "scripts/summarize_overnight.py"

# The 34 pre-declared columns, in order; manifest_sha256 is appended by the lead's
# requirement that every row carries the frozen manifest it came from.
IDENTITY_COLUMNS = ["group", "strategy", "mode", "budget", "start_kind", "control"]
COLUMNS = [
    "group", "strategy", "mode", "budget", "start_kind", "control",
    "initial_collision_pairs", "final_collision_pairs", "net_collision_reduction",
    "accepted_moves", "first_elevations", "relocations", "returns",
    "first_elevation_net_reduction", "relocation_net_reduction", "return_net_reduction",
    "total_old_collisions_removed", "total_new_collisions_created",
    "generated_candidates", "candidate_evaluations", "full_neighbor_checks",
    "full_acceptance_passes", "executed_moves", "stop_reason", "target_attempts",
    "evaluations_per_action", "net_reduction_per_evaluation",
    "relocation_candidate_evaluations", "not_evaluated_candidates",
    "stage_length_delta_mm", "final_extra_length_vs_planar_mm",
    "final_transition_count", "final_elevated_route_count", "recheck_verdict",
    "manifest_sha256",
]

# Every column is read from the FIRST source that actually carries the key.
# "manifest" = the frozen cell of OUTDIR/manifest/round_<round>.json (identity only),
# "stats"    = summary.json["stats"] as written by run_overnight_3d.py,
# "ledger"/"recheck"/"config" = the group's own saved artifacts (declared fallbacks,
# never recomputations).
SOURCES = {
    "group": [("manifest", "group"), ("stats", "group"), ("config", "group")],
    "strategy": [("manifest", "strategy"), ("stats", "strategy"), ("config", "strategy")],
    "mode": [("manifest", "mode"), ("stats", "mode"), ("config", "mode")],
    "budget": [("manifest", "budget"), ("stats", "appended_candidate_budget"),
               ("config", "appended_candidate_budget")],
    "start_kind": [("manifest", "start_kind"), ("stats", "start_kind"),
                   ("config", "start_kind")],
    "control": [("manifest", "control"), ("stats", "control"), ("config", "control")],
    "initial_collision_pairs": [("stats", "initial_collision_pairs"),
                                ("ledger", "initial_collision_pair_count")],
    "final_collision_pairs": [("stats", "final_collision_pairs"),
                              ("ledger", "final_collision_pair_count")],
    "net_collision_reduction": [("stats", "net_collision_reduction"),
                                ("ledger", "net_collision_reduction")],
    "accepted_moves": [("stats", "accepted_moves"), ("ledger", "accepted_moves")],
    "first_elevations": [("stats", "first_elevations"), ("ledger", "first_elevations")],
    "relocations": [("stats", "relocations"), ("ledger", "relocations")],
    "returns": [("stats", "returns"), ("ledger", "returns")],
    "first_elevation_net_reduction": [("stats", "first_elevation_net_reduction"),
                                      ("ledger", "first_elevation_net_reduction")],
    "relocation_net_reduction": [("stats", "relocation_net_reduction"),
                                 ("ledger", "relocation_net_reduction")],
    "return_net_reduction": [("stats", "return_net_reduction"),
                             ("ledger", "return_net_reduction")],
    "total_old_collisions_removed": [("stats", "total_old_collisions_removed"),
                                     ("ledger", "total_old_collisions_removed")],
    "total_new_collisions_created": [("stats", "total_new_collisions_created"),
                                     ("ledger", "total_new_collisions_created")],
    "generated_candidates": [("stats", "generated_candidates"),
                             ("ledger", "generated_candidates")],
    "candidate_evaluations": [("stats", "candidate_evaluations"),
                              ("ledger", "candidate_evaluations")],
    "full_neighbor_checks": [("stats", "full_neighbor_checks"),
                             ("ledger", "full_neighbor_checks")],
    "full_acceptance_passes": [("stats", "full_acceptance_passes"),
                               ("ledger", "full_acceptance_passes")],
    "executed_moves": [("stats", "executed_moves"), ("ledger", "executed_moves")],
    "stop_reason": [("stats", "stop_reason"), ("ledger", "stop_reason")],
    "target_attempts": [("stats", "target_attempts"), ("ledger", "target_attempts")],
    "evaluations_per_action": [("stats", "evaluations_per_action"),
                               ("ledger", "evaluations_per_action")],
    "net_reduction_per_evaluation": [("stats", "net_reduction_per_evaluation"),
                                     ("ledger", "net_reduction_per_evaluation")],
    "relocation_candidate_evaluations": [("stats", "relocation_candidate_evaluations"),
                                         ("ledger", "relocation_candidate_evaluations")],
    "not_evaluated_candidates": [("stats", "not_evaluated_candidates"),
                                 ("ledger", "not_evaluated_candidates")],
    "stage_length_delta_mm": [("stats", "stage_length_delta_mm"),
                              ("ledger", "stage_length_delta_mm")],
    "final_extra_length_vs_planar_mm": [("stats", "final_extra_length_vs_planar_mm"),
                                        ("ledger", "final_extra_length_vs_planar_mm")],
    "final_transition_count": [("stats", "final_transition_count"),
                               ("ledger", "final_transition_count")],
    "final_elevated_route_count": [("stats", "final_elevated_route_count"),
                                   ("ledger", "final_elevated_route_count")],
    "recheck_verdict": [("stats", "recheck.verdict"), ("recheck", "verdict")],
    "manifest_sha256": [("config", "manifest_sha256")],
}

JSON_ONLY = ["missing_fields", "column_sources", "strategy_spec", "recheck_geometry",
             "coverage", "manifest_group", "frozen_identity_source",
             "frozen_identity_mismatch", "run_reported_identity", "warnings"]
REQUIRED_FILES = ("summary.json", "ledger.json", "recheck.json")
OPTIONAL_FILES = ("config.json", "collision_sets.json", "curve.json", "decisions.json")
GEOMETRY_FLAGS = ("endpoint_invariant", "joins_C0_C1_direction", "transition_radius_pass",
                  "xy_projection_preserved", "single_elevation_structure")
EQUIV_FILE = "equiv/%s_legacy_vs_v4.json"
_MISSING = object()


def parse_args(argv):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("project", help="project root (contains src/ and scripts/)")
    ap.add_argument("outdir", help="outputs/overnight_3d_ideas")
    ap.add_argument("--round", required=True, help="round directory name, e.g. v5")
    ap.add_argument("--adopt", action="store_true",
                    help="also apply scripts/overnight_registry.py ADOPTION_RULE")
    return ap.parse_args(argv[1:])


ARGS = parse_args(sys.argv)
ROOT = Path(ARGS.project).resolve()
OUT = Path(ARGS.outdir).resolve()
ROUND = ARGS.round
ROUND_DIR = OUT / ROUND

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
try:
    import overnight_registry as REG  # noqa: E402
except Exception as exc:  # pragma: no cover - a missing registry is fatal by design
    raise SystemExit("cannot import scripts/overnight_registry.py: %r" % (exc,))


def jsread(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def dig(obj, dotted):
    current = obj
    for part in dotted.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return _MISSING
    return current


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def manifest_path():
    return OUT / "manifest" / ("round_" + ROUND + ".json")


def load_manifest():
    """The frozen round manifest is a hard precondition, exactly as for the runner."""
    path = manifest_path()
    if not path.is_file():
        raise SystemExit("frozen manifest missing: %s\n"
                         "the summarizer only reports pre-registered groups; run "
                         "scripts/freeze_overnight_manifest.py first" % path)
    manifest = jsread(path)
    if not manifest.get("cells"):
        raise SystemExit("frozen manifest has no cells: %s\n"
                         "cannot attach the frozen identity of any row" % path)
    groups = list(manifest.get("groups") or [c["group"] for c in manifest["cells"]])
    missing_cells = [g for g in groups if g not in {c["group"] for c in manifest["cells"]}]
    if missing_cells:
        raise SystemExit("frozen manifest lists groups without a cell: %s"
                         % ", ".join(missing_cells))
    return manifest, str(path)


def discover_group_dirs():
    """Directories under the round folder that look like a run directory."""
    if not ROUND_DIR.is_dir():
        return []
    names = []
    for entry in sorted(ROUND_DIR.iterdir()):
        if not entry.is_dir():
            continue
        if any((entry / f).is_file() for f in ("config.json", "summary.json", "ledger.json")):
            names.append(entry.name)
    return names


def load_group(folder):
    """Return (data, None) for a completed group, else (None, skip_reason)."""
    missing = [f for f in REQUIRED_FILES if not (folder / f).is_file()]
    if missing:
        return None, "not finished: missing " + ", ".join(missing)
    data = {}
    for name in REQUIRED_FILES + OPTIONAL_FILES:
        path = folder / name
        if not path.is_file():
            continue
        try:
            data[name.split(".")[0]] = jsread(path)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            return None, "unreadable %s (%s)" % (name, type(exc).__name__)
    stats = data.get("summary", {}).get("stats")
    if not isinstance(stats, dict):
        return None, "summary.json has no stats object"
    data["stats"] = stats
    return data, None


def row_from_group(name, manifest_group, cell, data, current_manifest_sha):
    warnings = []
    sources = {"manifest": cell, "stats": data["stats"], "ledger": data.get("ledger", {}),
               "recheck": data.get("recheck", {}), "config": data.get("config", {})}
    row = {}
    origin = {}
    missing_fields = []
    for column in COLUMNS:
        value = _MISSING
        used = None
        for source, dotted in SOURCES[column]:
            found = dig(sources.get(source, {}), dotted)
            if found is not _MISSING:
                value, used = found, "%s.%s" % (source, dotted)
                break
        if value is _MISSING:
            row[column] = None
            origin[column] = None
            missing_fields.append(column)
        else:
            row[column] = value
            origin[column] = used
    # The directory name identifies the artifact; a tagged run keeps its own name.
    if row["group"] is None or name != manifest_group:
        row["group"] = name
        origin["group"] = "directory name" + ("" if name == manifest_group else " (tagged run)")
        if name != manifest_group:
            warnings.append("tagged run of %s" % manifest_group)
    # manifest_sha256: prefer the hash the run itself recorded, else the hash of the
    # manifest that is on disk now (recorded as such, never silently substituted).
    if row["manifest_sha256"] is None:
        row["manifest_sha256"] = current_manifest_sha
        origin["manifest_sha256"] = "sha256 of the current %s" % manifest_path().name
        warnings.append("config.json does not record manifest_sha256; the hash of the "
                        "manifest on disk was recorded instead")
    elif current_manifest_sha and row["manifest_sha256"] != current_manifest_sha:
        warnings.append("recorded manifest_sha256 differs from the manifest on disk "
                        "(the manifest may have been re-frozen after this run started)")
    for key, fallback in (("recheck_geometry", ("stats", "recheck_geometry", "recheck", "geometry")),
                          ("coverage", ("stats", "coverage", "ledger", "coverage"))):
        value = dig(sources[fallback[0]], fallback[1])
        if value is _MISSING and len(fallback) == 4:
            value = dig(sources[fallback[2]], fallback[3])
        row[key] = None if value is _MISSING else value
    spec = dig(sources["stats"], "strategy_spec")
    if spec is _MISSING:
        spec = dig(sources["config"], "strategy_spec")
    row["strategy_spec"] = None if spec is _MISSING else spec
    # Cross-check the frozen identity against what the run itself reported.
    run_identity = {column: (None if dig(sources["stats"], dotted) is _MISSING
                             else dig(sources["stats"], dotted))
                    for column, dotted in (("group", "group"), ("strategy", "strategy"),
                                           ("mode", "mode"),
                                           ("budget", "appended_candidate_budget"),
                                           ("start_kind", "start_kind"),
                                           ("control", "control"))}
    mismatch = ["%s: manifest=%r run=%r" % (column, row[column], run_identity[column])
                for column in IDENTITY_COLUMNS
                if column != "group" and run_identity[column] is not None
                and run_identity[column] != row[column]]
    if run_identity["group"] is not None and run_identity["group"] != manifest_group:
        mismatch.append("group: manifest=%r run=%r" % (manifest_group, run_identity["group"]))
    row["missing_fields"] = missing_fields
    row["column_sources"] = origin
    row["manifest_group"] = manifest_group
    row["frozen_identity_source"] = "manifest.cell (frozen %s)" % manifest_path().name
    row["frozen_identity_mismatch"] = mismatch
    row["run_reported_identity"] = run_identity
    row["warnings"] = warnings + (["frozen identity differs from the run's own report: "
                                   + "; ".join(mismatch)] if mismatch else [])
    return row


def geometry_state(geometry):
    """(ok, list_of_failed_flags) for a recheck_geometry sub-object."""
    if not isinstance(geometry, dict):
        return False, ["recheck_geometry absent"]
    failed = [flag for flag in GEOMETRY_FLAGS if geometry.get(flag) is not True]
    for key in ("failures", "xy_failures"):
        value = geometry.get(key)
        if isinstance(value, list) and value:
            failed.append("%s=%d" % (key, len(value)))
    return (not failed), failed


def correctness(row):
    """The pre-declared first gate: correctness and recheck PASS."""
    reasons = []
    verdict = row.get("recheck_verdict")
    if verdict != "PASS":
        reasons.append("recheck_verdict=%r" % (verdict,))
    ok, failed = geometry_state(row.get("recheck_geometry"))
    if not ok:
        reasons.append("geometry:" + ",".join(failed))
    return (not reasons), reasons


def sort_key(row):
    rank = {"main": 0, "challenge": 1}
    return (rank.get(row.get("start_kind"), 2), str(row.get("strategy")),
            str(row.get("mode")), row.get("budget") if row.get("budget") is not None else -1,
            str(row.get("group")))


def legacy_equivalence():
    """Surface (never re-derive) the verdict of scripts/overnight_equiv_check.py."""
    path = OUT / (EQUIV_FILE % ROUND)
    doc = dict(source=str(path), present=False, all_reusable=None,
               note=("read verbatim from scripts/overnight_equiv_check.py output; the "
                     "summarizer never re-derives this verdict"))
    if not path.is_file():
        doc["note"] = ("%s is absent, so no LEGACY-vs-v4 reuse verdict exists yet; "
                       "nothing is assumed here" % path)
        return doc
    record = jsread(path)
    doc.update(present=True, all_reusable=record.get("all_reusable"),
               criterion=record.get("criterion"),
               source_v4=record.get("source_v4"), source_new=record.get("source_new"),
               groups=[dict(group=r.get("group"), mode=r.get("mode"), budget=r.get("budget"),
                            status=r.get("status"),
                            reusable_as_baseline=r.get("reusable_as_baseline"),
                            failing_checks=[k for k, v in (r.get("checks") or {}).items() if not v])
                       for r in record.get("rows", [])])
    return doc


def summarise():
    manifest, manifest_file = load_manifest()
    cells = {c["group"]: c for c in manifest["cells"]}
    expected = list(manifest.get("groups") or cells)
    current_manifest_sha = sha256_file(manifest_path())

    found = discover_group_dirs()
    wanted, unknown = [], []
    for name in found:
        if name in cells:
            wanted.append((name, name))
            continue
        tagged = [g for g in expected if name.startswith(g + "_")]
        if tagged:
            wanted.append((name, max(tagged, key=len)))
        else:
            unknown.append(dict(directory=name,
                                reason="not listed in the frozen manifest %s"
                                       % Path(manifest_file).name))
    wanted.sort(key=lambda item: (expected.index(item[1]) if item[1] in expected else 10 ** 6,
                                  item[0]))

    rows, skipped, excluded_rows = [], [], []
    for name, manifest_group in wanted:
        data, reason = load_group(ROUND_DIR / name)
        if data is None:
            skipped.append(dict(group=name, manifest_group=manifest_group, reason=reason))
            continue
        rows.append(row_from_group(name, manifest_group, cells[manifest_group], data,
                                   current_manifest_sha))
    rows.sort(key=sort_key)

    # A stray directory that also holds a complete run is excluded, never included.
    for entry in unknown:
        data, _reason = load_group(ROUND_DIR / entry["directory"])
        if data is not None:
            excluded_rows.append(dict(group=entry["directory"],
                                      reason="no frozen manifest cell matches this directory "
                                             "(%s); the completed run is excluded from "
                                             "comparison.csv" % entry["reason"]))
    for name in expected:
        if name not in cells:
            excluded_rows.append(dict(group=name,
                                      reason="listed in the frozen manifest but without a cell"))

    aggregate_missing = sorted({"%s:%s" % (r["group"], c) for r in rows
                                for c in r["missing_fields"]})
    equivalence = legacy_equivalence()
    summary = {
        "round": ROUND,
        "generator": GENERATOR,
        "generated_utc": utcnow(),
        "round_manifest": manifest_file,
        "round_manifest_sha256": current_manifest_sha,
        "round_manifest_frozen_at": manifest.get("frozen_at"),
        "round_manifest_adoption": manifest.get("adoption"),
        "round_manifest_adoption_rule": manifest.get("adoption_rule"),
        "group_source": "frozen manifest only; the round folder is never globbed for rows",
        "groups_expected": len(expected),
        "groups_completed": len(rows),
        "groups_not_finished": len(skipped),
        "skipped_groups": skipped,
        "skipped_unknown_directories": unknown,
        "excluded_rows": excluded_rows,
        "excluded_row_count": len(excluded_rows),
        "column_order": COLUMNS,
        "identity_columns": IDENTITY_COLUMNS,
        "identity_source": "frozen manifest cells of %s" % Path(manifest_file).name,
        "column_sources": {c: ["%s.%s" % (s, p) for s, p in SOURCES[c]] for c in COLUMNS},
        "json_only_fields": JSON_ONLY,
        "row_schema_note": ("each row carries the comparison.csv columns plus missing_fields, "
                            "column_sources, strategy_spec, recheck_geometry, coverage, the "
                            "frozen identity and the run's own reported identity; a value "
                            "absent from every declared source is null and named in "
                            "missing_fields"),
        "missing_fields": aggregate_missing,
        "legacy_equivalence": equivalence,
        "adoption_rule": REG.ADOPTION_RULE,
        "adoption_rule_source": "scripts/overnight_registry.py ADOPTION_RULE",
        "rows": rows,
    }
    summary_file = ROUND_DIR / ("summary_%s.json" % ROUND)
    summary_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False),
                            encoding="utf-8")

    csv_file = ROUND_DIR / "comparison.csv"
    with csv_file.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: ("" if row[c] is None else row[c]) for c in COLUMNS})
    return rows, skipped, unknown, excluded_rows, summary, summary_file, csv_file


# ------------------------------------------------------------------- adoption
def registry_default_old_config():
    """The configuration the registry uses when no adoption.json is supplied.

    Read from scripts/overnight_registry.py itself (round_groups() ADOPTION
    defaults) so the old config is never restated from memory."""
    path = Path(REG.__file__)
    text = path.read_text(encoding="utf-8")
    found = dict(re.findall(r'adoption\.get\(\s*"(\w+)"\s*,\s*([^)]+?)\s*\)', text))
    config = {}
    for key in ("target_policy", "evaluation_policy", "k_per_target"):
        if key not in found:
            return None, "registry default for %s not found in %s" % (key, path)
        try:
            config[key] = ast.literal_eval(found[key])
        except (ValueError, SyntaxError) as exc:
            return None, "cannot read registry default %s (%s)" % (key, exc)
    return config, "%s: round_groups() adoption defaults (adoption absent)" % path


def old_config(round_dir):
    path = round_dir / "adoption.json"
    if path.is_file():
        try:
            previous = jsread(path)
        except (json.JSONDecodeError, OSError):
            previous = {}
        triple = {k: previous.get(k) for k in ("target_policy", "evaluation_policy",
                                              "k_per_target")}
        if all(v is not None for v in triple.values()):
            return triple, "%s (previously written adoption decision)" % path
    return registry_default_old_config()


def spec_triple(row):
    """The three registry-level policy keys of one row's frozen StrategySpec."""
    spec = row.get("strategy_spec") or {}
    triple = {k: spec.get(k) for k in ("target_policy", "evaluation_policy", "k_per_target")}
    return triple if all(v is not None for v in triple.values()) else None


def same_triple(left, right):
    if not left or not right:
        return False
    return all(left.get(k) == right.get(k) for k in ("target_policy", "evaluation_policy",
                                                     "k_per_target"))


def brief(row):
    """Serialisable one-line record of a candidate; never used for comparisons."""
    return dict(group=row["group"], strategy=row.get("strategy"),
                recheck_verdict=row.get("recheck_verdict"),
                final_collision_pairs=row.get("final_collision_pairs"),
                stage_length_delta_mm=row.get("stage_length_delta_mm"),
                candidate_evaluations=row.get("candidate_evaluations"))


def rule_clauses():
    return [clause.strip() for clause in REG.ADOPTION_RULE.split(";")]


def adoption_decision(rows, round_dir, manifest):
    clauses = rule_clauses()
    old, old_source = old_config(round_dir)

    def cell_of(row):
        return (row.get("start_kind"), row.get("mode"), row.get("budget"))

    main_r2880 = [r for r in rows
                  if r.get("start_kind") == "main" and r.get("mode") == "R"
                  and r.get("budget") == 2880]
    candidate_names = {r["group"] for r in main_r2880}
    eligible, excluded = [], []
    for row in main_r2880:
        ok, reasons = correctness(row)
        (eligible if ok else excluded).append(
            row if ok else dict(group=row["group"], strategy=row.get("strategy"),
                                recheck_verdict=row.get("recheck_verdict"),
                                final_collision_pairs=row.get("final_collision_pairs"),
                                excluded_reasons=reasons))
    for row in rows:
        if row["group"] in candidate_names:
            continue
        ok, reasons = correctness(row)
        if not ok:
            excluded.append(dict(group=row["group"], strategy=row.get("strategy"),
                                 recheck_verdict=row.get("recheck_verdict"),
                                 final_collision_pairs=row.get("final_collision_pairs"),
                                 excluded_reasons=reasons,
                                 note="not a MAIN R2880 candidate; failed recheck"))

    decision_path = []
    if not eligible:
        return None, dict(status="DEFERRED", clauses=clauses, old_config=old,
                          old_config_source=old_source, eligible=[], excluded=excluded,
                          reason=("no completed MAIN R2880 R-mode group passes correctness/"
                                  "recheck yet"))

    survivors = sorted(eligible, key=lambda r: r["group"])
    decision_path.append(dict(
        step=1, criterion=clauses[0], applied=True, field="recheck_verdict + recheck_geometry",
        kept=[r["group"] for r in survivors],
        dropped=[dict(group=e["group"], reasons=e["excluded_reasons"]) for e in excluded],
        detail="MAIN R2880 R-mode groups only; the rule's first gate"))

    criteria = [(2, clauses[1], "final_collision_pairs", "min"),
                (3, clauses[2], "stage_length_delta_mm", "min"),
                (4, clauses[3], "candidate_evaluations", "min")]
    for step, criterion, field, direction in criteria:
        values = {r["group"]: r.get(field) for r in survivors}
        unknown = [g for g, v in values.items() if v is None]
        measured = [r for r in survivors if r.get(field) is not None]
        if len(survivors) <= 1:
            decision_path.append(dict(step=step, criterion=criterion, applied=False,
                                      field=field, values=values,
                                      reason="a single candidate already remained"))
            continue
        if len(measured) <= 1:
            decision_path.append(dict(step=step, criterion=criterion, applied=False,
                                      field=field, values=values,
                                      reason=("cannot be applied: %d of %d candidates lack the "
                                              "value" % (len(unknown), len(survivors)))))
            if len(measured) == 1:
                survivors = measured
            continue
        best = min(v for v in values.values() if v is not None)
        kept = [r for r in measured if r[field] == best]
        dropped = [r["group"] for r in survivors if r not in kept]
        survivors = kept
        decision_path.append(dict(step=step, criterion=criterion, applied=True, field=field,
                                  direction=direction, values=values,
                                  kept=[r["group"] for r in survivors], dropped=dropped,
                                  unknown_values=unknown))

    if len(survivors) > 1:
        matches = [r for r in survivors if same_triple(spec_triple(r), old)]
        decision_path.append(dict(
            step=5, criterion=clauses[4], applied=True,
            field="strategy_spec.target_policy + evaluation_policy + k_per_target",
            old_config=old, old_config_source=old_source,
            candidates=[r["group"] for r in survivors],
            kept=[r["group"] for r in matches],
            detail=("all measured criteria tied; the old configuration is retained")))
        if matches:
            survivors = [sorted(matches, key=lambda r: r["group"])[0]]
        elif old is None:
            return None, dict(status="DEFERRED", clauses=clauses, old_config=old,
                              old_config_source=old_source,
                              eligible=[brief(row) for row in eligible], excluded=excluded,
                              reason=("every measured criterion tied and the old configuration "
                                      "could not be determined, so no policy value can be "
                                      "declared"))
        else:
            survivors = []

    if survivors:
        winner = survivors[0]
        adopted = dict(target_policy=None, evaluation_policy=None, k_per_target=None,
                       adopted_group=winner["group"], retained_old_config=False)
        adopted.update(spec_triple(winner) or {})
        adopted["adopted_cell"] = dict(start_kind=winner.get("start_kind"),
                                       mode=winner.get("mode"), budget=winner.get("budget"))
        adopted["adopted_manifest_sha256"] = winner.get("manifest_sha256")
        adopted["adopted_metrics"] = {k: winner.get(k) for k in
                                      ("initial_collision_pairs", "final_collision_pairs",
                                       "net_collision_reduction", "stage_length_delta_mm",
                                       "candidate_evaluations", "accepted_moves",
                                       "recheck_verdict")}
    else:
        adopted = dict(target_policy=None, evaluation_policy=None, k_per_target=None,
                       adopted_group=None, retained_old_config=True)
        adopted.update(old or {})
        adopted["adopted_cell"] = None
        adopted["adopted_metrics"] = None
        adopted["note"] = ("every measured criterion tied and no completed group realises the "
                           "old configuration in this round; the old configuration itself is "
                           "kept, so no group is adopted")

    winner_triple = spec_triple(survivors[0]) if survivors else old
    winner_groups = {}
    for row in rows:
        if same_triple(spec_triple(row), winner_triple):
            winner_groups.setdefault(cell_of(row), row["group"])
    old_groups = {}
    for row in rows:
        if same_triple(spec_triple(row), old):
            old_groups.setdefault(cell_of(row), row["group"])

    by_cell = []
    planned = [(c.get("start_kind"), c.get("mode"), c.get("budget"))
               for c in (manifest or {}).get("cells", [])]
    seen = set()
    for key in planned + [cell_of(r) for r in rows]:
        if key in seen:
            continue
        seen.add(key)
        start_kind, mode, budget = key
        adopted_group = winner_groups.get(key)
        old_group = old_groups.get(key)
        new_row = next((r for r in rows if r["group"] == adopted_group), None)
        old_row = next((r for r in rows if r["group"] == old_group), None)
        cell = dict(start_kind=start_kind, mode=mode, budget=budget,
                    adopted_group=adopted_group, old_config_group=old_group,
                    adopted_final_collision_pairs=(new_row or {}).get("final_collision_pairs"),
                    old_config_final_collision_pairs=(old_row or {}).get("final_collision_pairs"),
                    verdict="NOT_COMPARABLE")
        if new_row is not None and old_row is not None:
            delta = new_row["final_collision_pairs"] - old_row["final_collision_pairs"]
            cell.update(
                delta_final_collision_pairs=delta,
                regression=bool(delta > 0),
                delta_stage_length_delta_mm=(new_row["stage_length_delta_mm"]
                                             - old_row["stage_length_delta_mm"]),
                delta_candidate_evaluations=(new_row["candidate_evaluations"]
                                             - old_row["candidate_evaluations"]),
                adopted_recheck_verdict=new_row.get("recheck_verdict"),
                old_config_recheck_verdict=old_row.get("recheck_verdict"),
                verdict="REGRESSION" if delta > 0 else ("IMPROVEMENT" if delta < 0 else "IDENTICAL"))
            if new_row.get("recheck_verdict") != "PASS":
                cell["correctness_note"] = ("adopted configuration's recheck verdict is %r at "
                                            "this cell" % (new_row.get("recheck_verdict"),))
        elif new_row is None and old_row is None:
            cell["verdict"] = "NEITHER_GROUP_COMPLETED"
        elif old_row is None:
            cell["verdict"] = "OLD_CONFIG_GROUP_NOT_COMPLETED"
        else:
            cell["verdict"] = "ADOPTED_GROUP_NOT_COMPLETED"
        by_cell.append(cell)

    regressions = [c for c in by_cell if c.get("regression") is True]
    disclosure = dict(
        by_cell=by_cell,
        regression_count=len(regressions),
        regression_cells=[dict(start_kind=c["start_kind"], mode=c["mode"], budget=c["budget"],
                               adopted_group=c["adopted_group"],
                               old_config_group=c["old_config_group"],
                               delta_final_collision_pairs=c["delta_final_collision_pairs"])
                          for c in regressions],
        criterion=("regression = the adopted configuration terminates with MORE near-distance "
                   "pairs than the old configuration at the same start state, mode and budget; "
                   "the rule itself ranks only the MAIN R2880 R-mode cells, so every other "
                   "budget and mode is disclosed here, never used to rank"),
        not_comparable=[dict(cell=c, verdict=c["verdict"]) for c in by_cell
                        if c["verdict"] not in ("REGRESSION", "IMPROVEMENT", "IDENTICAL")])
    return adopted, dict(status="DECIDED", clauses=clauses, old_config=old,
                         old_config_source=old_source,
                         eligible=[brief(row) for row in eligible],
                         excluded=[e for e in excluded],
                         decision_path=decision_path, disclosures=disclosure)


def write_adoption(adopted, detail, summary):
    payload = dict(round=ROUND, generator=GENERATOR, generated_utc=utcnow(),
                   status=detail["status"], adoption_rule=REG.ADOPTION_RULE,
                   rule_source="scripts/overnight_registry.py ADOPTION_RULE",
                   target_policy=adopted["target_policy"],
                   evaluation_policy=adopted["evaluation_policy"],
                   k_per_target=adopted["k_per_target"],
                   adopted_group=adopted["adopted_group"],
                   adopted_cell=adopted.get("adopted_cell"),
                   adopted_manifest_sha256=adopted.get("adopted_manifest_sha256"),
                   adopted_metrics=adopted.get("adopted_metrics"),
                   retained_old_config=adopted.get("retained_old_config"),
                   old_config=detail["old_config"], old_config_source=detail["old_config_source"],
                   eligible_candidates=detail["eligible"],
                   excluded_candidates=detail["excluded"],
                   decision_path=detail.get("decision_path", []),
                   disclosures=detail.get("disclosures"),
                   round_manifest=summary.get("round_manifest"),
                   round_manifest_sha256=summary.get("round_manifest_sha256"),
                   legacy_equivalence=summary.get("legacy_equivalence"),
                   notes=[detail.get("reason")] if detail.get("reason") else [])
    path = ROUND_DIR / "adoption.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False),
                    encoding="utf-8")
    return path, payload


def main():
    if not ROUND_DIR.is_dir():
        print("round directory does not exist yet: %s" % ROUND_DIR, flush=True)
        print("SUMMARIZE DONE (nothing to do)")
        return 0
    rows, skipped, unknown, excluded_rows, summary, summary_file, csv_file = summarise()
    print("round=%s manifest=%s sha256=%s"
          % (ROUND, summary["round_manifest"], summary["round_manifest_sha256"][:16]), flush=True)
    print("groups_expected=%d completed=%d not_finished=%d unknown_dirs=%d excluded_rows=%d"
          % (summary["groups_expected"], len(rows), len(skipped), len(unknown),
             summary["excluded_row_count"]), flush=True)
    for entry in skipped:
        print("  skip %s: %s" % (entry["group"], entry["reason"]), flush=True)
    for entry in unknown:
        print("  unknown directory %s: %s" % (entry["directory"], entry["reason"]), flush=True)
    for entry in excluded_rows:
        print("  excluded row %s: %s" % (entry["group"], entry["reason"]), flush=True)
    for row in rows:
        print("  %-28s strategy=%-13s mode=%s budget=%s start=%s final_pairs=%s moves=%s "
              "evals=%s stop=%s recheck=%s manifest=%s"
              % (row["group"], row["strategy"], row["mode"], row["budget"], row["start_kind"],
                 row["final_collision_pairs"], row["accepted_moves"],
                 row["candidate_evaluations"], row["stop_reason"], row["recheck_verdict"],
                 (row["manifest_sha256"] or "")[:16]), flush=True)
        if row["missing_fields"]:
            print("    missing_fields: %s" % ",".join(row["missing_fields"]), flush=True)
        for warning in row["warnings"]:
            print("    warning: %s" % warning, flush=True)
    if summary["missing_fields"]:
        print("aggregate missing fields: %s" % ", ".join(summary["missing_fields"]), flush=True)
    else:
        print("aggregate missing fields: none", flush=True)
    equivalence = summary["legacy_equivalence"]
    print("legacy_equivalence: present=%s all_reusable=%s source=%s"
          % (equivalence["present"], equivalence["all_reusable"], equivalence["source"]),
          flush=True)
    print("wrote %s" % csv_file, flush=True)
    print("wrote %s" % summary_file, flush=True)

    if not ARGS.adopt:
        print("SUMMARIZE DONE (adoption not requested)")
        return 0
    adopted, detail = adoption_decision(rows, ROUND_DIR, load_manifest()[0])
    if detail["status"] != "DECIDED":
        print("ADOPTION DEFERRED: %s" % detail["reason"], flush=True)
        print("  adoption.json not written: a deferred round must not change the live config",
              flush=True)
        print("SUMMARIZE DONE")
        return 0
    print("adoption: eligible MAIN R2880 R-mode candidates=%d (of %d completed rows)"
          % (len(detail["eligible"]), len(rows)), flush=True)
    for step in detail["decision_path"]:
        print("  step %d [%s] applied=%s kept=%s"
              % (step["step"], step["criterion"], step["applied"],
                 step.get("kept", step.get("candidates"))), flush=True)
    path, payload = write_adoption(adopted, detail, summary)
    print("adopted_group=%s target_policy=%s evaluation_policy=%s k_per_target=%s"
          % (payload["adopted_group"], payload["target_policy"], payload["evaluation_policy"],
             payload["k_per_target"]), flush=True)
    print("regressions disclosed=%d" % payload["disclosures"]["regression_count"], flush=True)
    print("wrote %s" % path, flush=True)
    print("SUMMARIZE DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
