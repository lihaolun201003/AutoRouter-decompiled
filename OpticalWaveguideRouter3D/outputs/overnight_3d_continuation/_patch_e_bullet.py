
import re, sys
from pathlib import Path
path = Path(sys.argv[1]) / "scripts/publication/build_v8_continuation_report.py"
text = path.read_text(encoding="utf-8")
pattern = re.compile(r'(\r?\n)(    lines\.append\(""\)\r?\n    return "\\\\n"\.join\(lines\) \+ "\\\\n"\r?\n\r?\n\r?\ndef artifacts_section\(\):)')
m = pattern.search(text)
print("found:", bool(m))
if m:
    bullet = ('\r\n    lines.append("- 额外队列（E 多锚点 x 目标上限）：E 在 max_targets=200 下无论预算多大都只'
              '\r\n                 "花 668 次评价就停止（终态 32565）；上限提到 2000 后同一预算用满，主起点 '
              'R2880"\r\n                 "为 15935 对，优于 BASE_E2（18444）与 A_FAMILY（18042）。此前把 E 记为'
              '"\r\n                 "“退化”来自目标尝试上限，不是多锚点机制本身。")')
    text = text[:m.start(2)] + bullet.lstrip("\r\n") + text[m.start(2):]
    path.write_text(text, encoding="utf-8")
    print("bullet inserted")
