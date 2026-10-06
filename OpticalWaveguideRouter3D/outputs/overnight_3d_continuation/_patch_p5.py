
import sys
from pathlib import Path
path = Path(sys.argv[1]) / "scripts/overnight_registry.py"
lines = path.read_text(encoding="utf-8").splitlines()
start = next(i for i, l in enumerate(lines) if l.startswith("def v8_round_groups"))
end = next(i for i in range(start, len(lines)) if lines[i].strip() == "return groups")
print("function lines", start + 1, "..", end + 1)
insert = [
    '    if round_name == "p5":',
    "        # The controlled serial timing comparison is declared at the MAIN start",
    "        # and R1440 only (both cache settings, three tag-suffixed repeats each);",
    "        # any other cell would be an unrun pre-registration in a frozen manifest.",
    '        return [row for row in groups if row[2] == "R" and row[3] == 1440]',
]
lines[end:end] = insert
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("patched")
