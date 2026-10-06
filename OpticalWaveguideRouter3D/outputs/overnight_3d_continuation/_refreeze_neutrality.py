
import hashlib, json, sys
from datetime import datetime
from pathlib import Path
root = Path(sys.argv[1]).resolve()
out = root / "outputs/overnight_3d_continuation"
manifest = out / "manifest" / "round_v8_neutrality.json"
old = manifest.read_text(encoding="utf-8") if manifest.is_file() else ""
old_sha = hashlib.sha256(old.encode()).hexdigest() if old else None
old_groups = json.loads(old)["groups"] if old else []
import subprocess
result = subprocess.run([str(root / ".venv/Scripts/python.exe"), "-B",
                         str(root / "scripts/freeze_overnight_manifest.py"), str(root), str(out),
                         "--round", "v8_neutrality", "--force"], capture_output=True, text=True)
print(result.stdout.strip() or result.stderr.strip())
new = json.loads(manifest.read_text(encoding="utf-8"))
record = dict(round="v8_neutrality",
              reason=("the first freeze omitted the challenge start (with_challenge was False for this "
                      "round), so the pre-registered challenge cell V8_G0_NEUTRALITY_RC2880 could not be "
                      "run; the round now covers BOTH fixed start states exactly like every other round"),
              old_sha256=old_sha, new_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
              old_groups=old_groups, new_groups=new["groups"],
              recorded_at=datetime.now().isoformat(timespec="seconds"))
(out / "manifest" / "round_v8_neutrality_override_record.json").write_text(
    json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
print("override record written; groups:", len(new["groups"]))
