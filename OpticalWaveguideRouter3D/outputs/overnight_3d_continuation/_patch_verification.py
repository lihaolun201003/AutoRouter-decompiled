
import sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
path = root / "scripts/overnight_final_verification.py"
text = path.read_text(encoding="utf-8")

# 1. tag-aware folder discovery: a group may have been run as tag-suffixed re-runs
old = '''        cells = {c["group"]: c for c in manifest["cells"]}
        for name in manifest["groups"]:
            folder = out / round_name / name'''
new = '''        cells = {c["group"]: c for c in manifest["cells"]}
        for name in manifest["groups"]:
            folders = sorted(p for p in (out / round_name).glob(name + "*")
                             if p.is_dir()) if (out / round_name).is_dir() else []
            if not folders:
                folders = [out / round_name / name]
            for folder in folders:
                verify_folder(root, out, round_name, name, folder, cells, manifest_path, manifest,
                              reports)'''
assert text.count(old) == 1
text = text.replace(old, new)
path.write_text(text, encoding="utf-8")
print("verification dispatch patched; now converting the body into a function")
