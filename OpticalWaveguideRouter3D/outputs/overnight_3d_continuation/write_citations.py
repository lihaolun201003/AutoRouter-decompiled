"""Write citation records for every pre-registered cell that reuses a baseline.

The v8-continuation rounds deliberately do not re-run configurations that were
already verified in an earlier round. Such a cell must not look like an
unfinished run: it gets a REUSED_BASELINE.json that names its source group, the
source directory (relative to the project root) and the SHA256 of the source
artifacts, so the verification can check the citation itself instead of a copy.

Usage: python -B outputs/overnight_3d_continuation/write_citations.py PROJECT OUTDIR
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
ARTS = ("summary.json", "collision_sets.json", "final_routes.json", "ledger.json",
        "recheck.json")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def citation(round_name, group, source_round_dir, source_group, reason):
    source = ROOT / "outputs/overnight_3d_ideas" / source_round_dir / source_group
    if not source.is_dir():
        raise SystemExit("missing source " + str(source))
    record = dict(
        status="REUSED_BASELINE_NOT_A_NEW_RUN",
        source_group=source_group,
        source_directory=str(source.relative_to(ROOT)).replace("\\", "/"),
        source_sha256={name: sha256(source / name) for name in ARTS if (source / name).is_file()},
        reason=reason,
        round=round_name, group=group)
    folder = OUT / round_name / group
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "REUSED_BASELINE.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return record


def main():
    written = []
    for mode in ("N", "R"):
        for budget in (720, 1440, 2880):
            for suffix in ("", "C2880"):
                if suffix and budget != 2880:
                    continue
                name = "%s%s" % (mode, suffix if suffix else budget)
                written.append(citation(
                    "v8", "V8_G0_" + name, "v7", "V7_T0_" + name,
                    "G0 is the historical LINE_ONLY generation domain; the v8 neutrality re-runs "
                    "prove the frozen v8 code reproduces this group bit for bit"))
                written.append(citation(
                    "p3", "P3_BASE_E2_T200_" + name, "v7", "V7_T0_" + name,
                    "BASE_E2 at max_targets 200 is exactly the adopted v7 T0 configuration"))
                written.append(citation(
                    "p3", "P3_BASE_E2_T2000_" + name, "v7", "V7_T1_" + name,
                    "BASE_E2 at max_targets 2000 is exactly the v7 T1 configuration"))
                if not suffix:
                    written.append(citation(
                        "p3", "P3_A_FAMILY_T200_" + name, "ideas", "IDEA_A_FAMILY_" + name,
                        "A_FAMILY at max_targets 200 is exactly the verified ideas-round A arm"))
    print("citation records written:", len(written))
    print(json.dumps(written[0], ensure_ascii=False, indent=1)[:600])


if __name__ == "__main__":
    main()
