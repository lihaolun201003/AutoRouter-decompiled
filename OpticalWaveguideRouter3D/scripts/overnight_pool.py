"""Run pre-registered overnight groups with bounded parallelism, one process each.

Every group is started as its own process (its own fresh interpreter, empty
in-process caches and empty logical caches), which is what the frozen manifest
and the runner require. The pool never starts a group that is not in the frozen
manifest, and it never lets two workers write the same group folder.

Usage:
  python -B scripts/overnight_pool.py PROJECT OUTDIR --plan PLAN.json [--workers N]

PLAN.json = [{"round": "...", "group": "...", "tag": "..."}, ...]
"""
import json
import subprocess
import sys
import time
from pathlib import Path


def parse(argv):
    args = {"workers": 1, "plan": None, "project": None, "outdir": None}
    rest = argv[1:]
    args["project"] = rest[0]
    args["outdir"] = rest[1]
    i = 2
    while i < len(rest):
        if rest[i] == "--plan":
            args["plan"] = rest[i + 1]; i += 2
        elif rest[i] == "--workers":
            args["workers"] = int(rest[i + 1]); i += 2
        else:
            raise SystemExit("unknown argument " + rest[i])
    return args


def main():
    args = parse(sys.argv)
    root = Path(args["project"]).resolve()
    out = Path(args["outdir"]).resolve()
    plan = json.loads(Path(args["plan"]).read_text(encoding="utf-8"))
    log_dir = out / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    python = str(root / ".venv" / "Scripts" / "python.exe")
    runner = str(root / "scripts" / "run_overnight_3d.py")
    pending = list(plan)
    running = []
    finished = []
    started = time.time()
    while pending or running:
        while pending and len(running) < args["workers"]:
            job = pending.pop(0)
            name = job["group"] + (("_" + job["tag"]) if job.get("tag") else "")
            log_path = log_dir / (job["round"] + "__" + name + ".log")
            handle = log_path.open("w", encoding="utf-8")
            command = [python, "-B", runner, str(root), str(out), "--round", job["round"],
                       "--group", job["group"]]
            if job.get("tag"):
                command += ["--tag", job["tag"]]
            process = subprocess.Popen(command, cwd=str(root), stdout=handle,
                                       stderr=subprocess.STDOUT)
            running.append(dict(job=job, name=name, process=process, handle=handle,
                                log=str(log_path), started=time.time()))
            print("START " + name + " pid=" + str(process.pid) + " log=" + str(log_path),
                  flush=True)
        time.sleep(2)
        for row in list(running):
            code = row["process"].poll()
            if code is None:
                continue
            row["handle"].close()
            running.remove(row)
            row["exit"] = code
            row["seconds"] = round(time.time() - row["started"], 1)
            finished.append(row)
            print("DONE  " + row["name"] + " exit=" + str(code) + " " + str(row["seconds"])
                  + "s", flush=True)
    summary = dict(workers=args["workers"], total=len(plan),
                   seconds=round(time.time() - started, 1),
                   results=[dict(round=r["job"]["round"], group=r["job"]["group"],
                                 tag=r["job"].get("tag"), exit=r["exit"],
                                 seconds=r["seconds"], log=r["log"]) for r in finished])
    (out / "pool_last_run.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    failures = [r for r in finished if r["exit"] != 0]
    print("POOL DONE total=" + str(len(finished)) + " failures=" + str(len(failures)))
    for r in failures:
        print("FAILED " + r["name"] + " exit=" + str(r["exit"]))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
