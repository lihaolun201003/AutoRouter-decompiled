"""用本机 Microsoft Word 更新域并导出最终文档。

流程（全部基于同一份 Word 文档，保证 docx/pdf/doc 内容一致）：
1. Word 打开 report docx；
2. 更新全部域（交叉引用 REF）与目录（TOC）；
3. 保存 docx（域结果固化）；
4. 导出 PDF（由最终 Word 文档转换）；
5. 另存真正 .doc 兼容版（wdFormatDocument97，不是改后缀）；
6. 关闭 Word；可选渲染 PDF 每页 PNG 供人工检查。

用法：
    python scripts/publication/export_report_pdf.py            # 导出 + 渲染检查图
    python scripts/publication/export_report_pdf.py --no-render
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
REPORT_DIR = PROJECT_ROOT / "publication" / "report"
DOCX = REPORT_DIR / "光波导自动布线算法实验报告.docx"
PDF = REPORT_DIR / "光波导自动布线算法实验报告.pdf"
DOC = REPORT_DIR / "光波导自动布线算法实验报告.doc"
RENDER_DIR = REPORT_DIR / "render"

WD_EXPORT_FORMAT_PDF = 17
WD_FORMAT_DOCUMENT_97 = 0


def export_with_word():
    import win32com.client

    if not DOCX.exists():
        raise FileNotFoundError(DOCX)
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    document = None
    try:
        document = word.Documents.Open(str(DOCX), ReadOnly=False)
        # 更新所有域（含 REF 交叉引用）；再更新目录
        document.Fields.Update()
        for index in range(1, document.TablesOfContents.Count + 1):
            document.TablesOfContents(index).Update()
        # 页眉页脚中的域（页码）需要逐节逐 story 更新
        for si in range(1, document.Sections.Count + 1):
            section = document.Sections(si)
            for kind in (1, 2, 3):  # wdHeaderFooterPrimary/FirstPage/EvenPages
                try:
                    section.Headers(kind).Range.Fields.Update()
                except Exception:
                    pass
                try:
                    section.Footers(kind).Range.Fields.Update()
                except Exception:
                    pass
        document.Repaginate()
        # 页码统计
        pages = document.ComputeStatistics(2)  # wdStatisticPages
        words = document.ComputeStatistics(0)  # wdStatisticWords
        document.Save()
        document.ExportAsFixedFormat(
            OutputFileName=str(PDF),
            ExportFormat=WD_EXPORT_FORMAT_PDF,
            CreateBookmarks=1,  # wdExportCreateHeadingBookmarks
        )
        document.SaveAs2(str(DOC), FileFormat=WD_FORMAT_DOCUMENT_97)
        print(f"页数：{pages}，字数：{words}")
    finally:
        try:
            if document is not None:
                document.Close(SaveChanges=0)
        except Exception:
            pass
        try:
            word.Quit()
        except Exception:
            pass
    print("已导出：", PDF)
    print("已另存 .doc：", DOC)


def render_pdf(dpi: int = 130):
    import pymupdf

    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    for old in RENDER_DIR.glob("page_*.png"):
        old.unlink()
    doc = pymupdf.open(PDF)
    for index, page in enumerate(doc, start=1):
        pix = page.get_pixmap(dpi=dpi)
        path = RENDER_DIR / f"page_{index:02d}.png"
        pix.save(path)
    print(f"已渲染 {len(doc)} 页到 {RENDER_DIR}")


def main():
    render = "--no-render" not in sys.argv
    export_with_word()
    if render:
        render_pdf()


if __name__ == "__main__":
    main()
