
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
files = sorted((root / "src").glob("*.py")) + [root / "scripts/overnight_registry.py",
    root / "scripts/run_overnight_3d.py", root / "scripts/overnight_pool.py",
    root / "scripts/v8_diagnostics.py", root / "scripts/v8_compare.py",
    root / "scripts/v8_figures.py", root / "scripts/v8_visualize_example.py",
    root / "scripts/overnight_final_verification.py"]
rows = {}
for path in files:
    if path.is_file():
        rows[str(path.relative_to(root)).replace("\\", "/")] = hashlib.sha256(path.read_bytes()).hexdigest()
tests = {}
for path in sorted((root / "tests").glob("*.py")):
    tests[str(path.relative_to(root)).replace("\\", "/")] = hashlib.sha256(path.read_bytes()).hexdigest()
target = root / "outputs/overnight_3d_continuation/code_snapshot.json"
target.write_text(json.dumps(dict(
    note="SHA256 of every source file loaded by the formal v8-continuation runs, frozen before the batch",
    files=rows, tests=tests), indent=2), encoding="utf-8")
print("snapshot", target, len(rows), "source files,", len(tests), "test files")
