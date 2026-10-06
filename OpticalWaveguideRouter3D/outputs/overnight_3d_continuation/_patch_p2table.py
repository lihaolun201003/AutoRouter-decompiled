
import re, sys
from pathlib import Path
path = Path(sys.argv[1]) / "scripts/publication/build_v8_continuation_report.py"
text = path.read_text(encoding="utf-8")
pattern = re.compile(r'    text\.append\(table\(rows, \["mode", "budget", "start", "g0_pairs".*?\]\)\)\n',
                     re.DOTALL)
matches = pattern.findall(text)
print("matches", len(matches))
replacement = (
    '    text.append(table(rows, ["mode", "budget", "start", "g0_pairs", "g1_pairs",\n'
    '                             "delta_pairs", "g0_len", "g1_len"],\n'
    '                      ["模式", "预算", "起点", "G0对", "G1对", "Δ对", "G0长mm", "G1长mm"]))\n'
    '    text.append("")\n'
    '    text.append(table(rows, ["mode", "budget", "start", "g0_evals", "g1_evals", "g0_moves",\n'
    '                             "g1_moves", "g1_path_windows", "g1_line_windows"],\n'
    '                      ["模式", "预算", "起点", "G0评价", "G1评价", "G0动作", "G1动作",\n'
    '                       "路径窗动作", "直线窗动作"]))\n')
text, count = pattern.subn(replacement, text, count=1)
path.write_text(text, encoding="utf-8")
print("replaced", count)
