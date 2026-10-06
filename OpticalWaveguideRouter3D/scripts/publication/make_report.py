"""报告一键入口：生成 Word → 更新域并导出 PDF/真 .doc → 渲染检查图。

用法（项目根目录）：
    .venv\\Scripts\\python.exe scripts\\publication\\make_report.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    python = sys.executable
    for script in ("build_report_docx.py", "export_report_pdf.py"):
        print(f"== 运行 {script} ==")
        result = subprocess.run([python, str(HERE / script)], cwd=str(HERE.parents[1]))
        if result.returncode != 0:
            raise SystemExit(f"{script} 失败（返回码 {result.returncode}）")
    print("报告生成完成：publication/report/")


if __name__ == "__main__":
    main()
