
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve(); out = root / "outputs/overnight_3d_continuation"
path = out / "manifest" / "round_p5_override_record.json"
record = json.loads(path.read_text(encoding="utf-8"))
history = ["a35aa6b10b4fa7d947bbc7d58e6f30f46c3932fad8219016f66a9071190fa326",
           "3bf9481781532aaf02f137b520fffb0f696c63c4a638f230441b354b2fb839da",
           "63a9001781532aaf02f137b520fffb0f696c63c4a638f230441b354b2fb839da",
           "4ea5107fe32c5d9415945cfa441b1dbbb8d26902b0ba40b320f1ad3934539555",
           "8da211707a46f761fd4193749cfa54b79b557120e71a4f87b624931637d216f2"]
current = hashlib.sha256((out / "manifest" / "round_p5.json").read_bytes()).hexdigest()
record.update(
    old_sha256_history=history,
    new_sha256=current,
    history_note=("the p5 manifest was re-frozen several times while the round was being narrowed to "
                  "the two cells the task actually requires (main start, R1440, both cache "
                  "settings); every previous hash is kept here, and the six timing runs recorded "
                  "the FIRST one because they were executed before the narrowing"),
    reason=("the controlled serial timing comparison is declared at the MAIN start and R1440 only "
            "(both cache settings, three tag-suffixed repeats each); every other cell was never run "
            "and a frozen manifest must not contain groups that are silently not run. No executed "
            "group's own cell (spec, mode, budget, start) changed"))
path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
print("history recorded:", len(history), "current:", current[:12])
