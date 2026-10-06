
import sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / "outputs/overnight_3d_continuation"))
import importlib.util
spec = importlib.util.spec_from_file_location(
    "wc", str(root / "outputs/overnight_3d_continuation/write_citations.py"))
module = importlib.util.module_from_spec(spec)
sys.argv = ["write_citations.py", str(root), str(root / "outputs/overnight_3d_continuation")]
spec.loader.exec_module(module)
written = []
for mode in ("N", "R"):
    for budget in (720, 1440, 2880):
        name = "%s%d" % (mode, budget)
        written.append(module.citation(
            "pe", "PE_E_T200_" + name, "ideas", "IDEA_E_" + name,
            "the extra queue keeps idea E exactly as verified in the ideas round; only the "
            "target-attempt limit changes in the PE_E_T2000 cell"))
print("extra citations written:", len(written))
