
import re, sys
from pathlib import Path
path = Path(sys.argv[1]) / "scripts/publication/build_v8_continuation_report.py"
text = path.read_text(encoding="utf-8")

pattern1 = re.compile(r'\r?\n            "按上限聚合：", "", FENCE,\r?\n'
                      r'            json\.dumps\(data\.get\("by_limit"\), ensure_ascii=False, indent=1\), FENCE\]')
replacement1 = ('\r\n            "按上限聚合（R 主 2880 单元）：", ""]\r\n'
                '    limit_rows = []\r\n'
                '    for key, row in (data.get("by_limit") or {}).items():\r\n'
                '        limit_rows.append(dict(arm=key, cells=row.get("cells"),\r\n'
                '                               pairs=row.get("main_r2880"),\r\n'
                '                               evals=row.get("actual_evaluations_r2880"),\r\n'
                '                               limit_hits=row.get("target_limit_hits"),\r\n'
                '                               full_uses=row.get("budget_full_uses"),\r\n'
                '                               length=fmt(row.get("stage_length_delta_r2880"))))\r\n'
                '    text.append(table(limit_rows, ["arm", "cells", "pairs", "evals", "limit_hits",\r\n'
                '                                   "full_uses", "length"],\r\n'
                '                      ["配置", "单元数", "R2880终态对", "实际评价", "触发目标上限",\r\n'
                '                       "用满预算", "阶段长度mm"]))')
text, n1 = pattern1.subn(replacement1, text, count=1)

pattern2 = re.compile(r'\r?\n            "中位数与范围：", "", FENCE,\r?\n'
                      r'            json\.dumps\(dict\(engine=data\.get\("median_runtime_seconds"\),.*?'
                      r'FENCE\]', re.DOTALL)
replacement2 = ('\r\n            "中位数与范围（秒）：", ""]\r\n'
                '    med = []\r\n'
                '    for arm in ("OFF", "ON"):\r\n'
                '        row = dict(arm=arm)\r\n'
                '        for label, key in (("engine", "median_runtime_seconds"),\r\n'
                '                           ("total", "median_run_seconds_including_recheck"),\r\n'
                '                           ("scan", "median_scan_seconds"),\r\n'
                '                           ("assign", "median_assignment_seconds")):\r\n'
                '            stats = (data.get(key) or {}).get(arm) or {}\r\n'
                '            row[label] = ("%s (%s-%s)" % (fmt(stats.get("median")),\r\n'
                '                                          fmt(stats.get("min")), fmt(stats.get("max")))\r\n'
                '                          if stats else "-")\r\n'
                '        med.append(row)\r\n'
                '    text.append(table(med, ["arm", "engine", "total", "scan", "assign"],\r\n'
                '                      ["缓存", "内核中位数(范围)", "总进程中位数(范围)",\r\n'
                '                       "预扫中位数(范围)", "分配中位数(范围)"]))\r\n'
                '    text.append("")\r\n'
                '    text.append("一致性（三次运行逐一核对）：终态近距对 %s；阶段长度 mm %s；"\r\n'
                '                "缓存命中 %s。"\r\n'
                '                % (json.dumps((data.get("consistency") or {}).get("final_pairs")),\r\n'
                '                   json.dumps((data.get("consistency") or {}).get("stage_length_delta")),\r\n'
                '                   json.dumps((data.get("consistency") or {}).get("cache_hits"))))\r\n'
                '    text.append("")\r\n'
                '    text.append("预扫（初始 130,816 对全扫）在每个起点状态上只执行一次，且在引擎计时"\r\n'
                '                "窗口之外，因此内核/进程时间里的预扫列为 0.00；该时间记在 "\r\n'
                '                "start_check_main.json 的 scan_seconds 中。")')
text, n2 = pattern2.subn(replacement2, text, count=1)

path.write_text(text, encoding="utf-8")
print("replaced by_limit block:", n1, "p5 block:", n2)
