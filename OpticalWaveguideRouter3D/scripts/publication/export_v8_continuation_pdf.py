"""Export the continuation report DOCX to PDF with Word and count the pages.

Usage: python -B scripts/publication/export_v8_continuation_pdf.py PROJECT
"""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
DOCX = ROOT / "publication/report/brief_build/三维布线v8路径弧长窗口续跑报告.docx"
PDF = ROOT / "publication/report/三维布线v8路径弧长窗口续跑报告.pdf"
WD_EXPORT_FORMAT_PDF = 17


def main():
    import win32com.client
    if not DOCX.is_file():
        raise SystemExit("missing " + str(DOCX))
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    document = None
    try:
        document = word.Documents.Open(str(DOCX), ReadOnly=False)
        document.Fields.Update()
        document.Repaginate()
        pages = document.ComputeStatistics(2)
        document.Save()
        document.ExportAsFixedFormat(OutputFileName=str(PDF), ExportFormat=WD_EXPORT_FORMAT_PDF,
                                     CreateBookmarks=1)
        print("pages", pages)
    finally:
        if document is not None:
            document.Close(SaveChanges=0)
        word.Quit()
    print("pdf", PDF, PDF.stat().st_size)


if __name__ == "__main__":
    main()
