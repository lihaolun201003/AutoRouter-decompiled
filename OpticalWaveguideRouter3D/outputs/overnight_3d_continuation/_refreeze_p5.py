
import hashlib, json, subprocess, sys
from datetime import datetime
from pathlib import Path
root = Path(sys.argv[1]).resolve(); out = root / "outputs/overnight_3d_continuation"
manifest = out / "manifest" / "round_p5.json"
old_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
old_groups = json.loads(manifest.read_text(encoding="utf-8"))["groups"]
result = subprocess.run([str(root / ".venv/Scripts/python.exe"), "-B",
                         str(root / "scripts/freeze_overnight_manifest.py"), str(root), str(out),
                         "--round", "p5", "--force"], capture_output=True, text=True)
print(result.stdout.strip() or result.stderr.strip())
new = json.loads(manifest.read_text(encoding="utf-8"))
record = dict(round="p5",
              reason=("the timing comparison is declared at the main start and R1440 only; the other "
                      "pre-registered cells were never run, and a frozen manifest must not contain "
                      "groups that are silently not run"),
              old_sha256=old_sha, new_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
              old_groups=old_groups, new_groups=new["groups"],
              recorded_at=datetime.now().isoformat(timespec="seconds"))
(out / "manifest" / "round_p5_override_record.json").write_text(
    json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
print("p5 groups now:", new["groups"])
