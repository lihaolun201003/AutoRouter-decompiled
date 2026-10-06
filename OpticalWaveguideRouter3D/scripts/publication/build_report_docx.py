"""构建 Word 实验报告：基于毕业论文格式模板。

流程：
1. 复制模板（不覆盖原文件）；
2. 插入封面（独立节，无页眉页码）；替换中文摘要/Abstract/关键词；
3. 目录替换为 TOC 域；填充主要符号表；
4. 以模板样式写入 8 章正文、参考文献、致谢与附录 A/B/C；
5. 图表编号（图 X-Y / 表 X-Y）手工编号 + 书签 + REF 交叉引用域；
6. 公式使用 OMML 原生公式；
7. 正文页眉统一为学校名；正文页码从 1 重启（阿拉伯）。

用法：
    python scripts/publication/build_report_docx.py
输出：
    publication/report/光波导自动布线算法实验报告.docx（交由 export_report_pdf.py 更新域并导出 PDF）
"""

from __future__ import annotations

import copy
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import pandas as pd
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Mm, Pt, RGBColor

import report_content as C
from report_body import CHAPTERS, ACKNOWLEDGEMENT, APPENDIX_INTRO

PROJECT_ROOT = C.PROJECT_ROOT
TEMPLATE = PROJECT_ROOT / "thesis" / "李昊伦_本科毕业论文_格式模板.docx"
OUT_DIR = PROJECT_ROOT / "publication" / "report"
OUT_DOCX = OUT_DIR / "光波导自动布线算法实验报告.docx"

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NSMAP = {"w": W, "r": R}
_BOOKMARK_ID = [100]


def w(tag: str) -> str:
    return f"{{{W}}}{tag}"


# ---------------------------------------------------------------------------
# 低层工具
# ---------------------------------------------------------------------------


def _new_paragraph(doc, style: str):
    return doc.add_paragraph(style=style)


def _set_run_font(run, size_pt: float | None = None, bold: bool | None = None):
    if size_pt is not None:
        run.font.size = Pt(size_pt)
    if bold is not None:
        run.font.bold = bold


def _clean_paragraph(paragraph):
    """删除段落中全部 run，保留段落属性。"""
    for child in list(paragraph._element):
        if child.tag != w("pPr"):
            paragraph._element.remove(child)


def _set_paragraph_text(paragraph, text: str):
    _clean_paragraph(paragraph)
    paragraph.add_run(text)


def add_field(paragraph, instr: str, cached: str = "", font_size: float | None = None):
    """插入 Word 域（begin/instrText/separate/cached/end）。"""
    run_begin = paragraph.add_run()
    fld = OxmlElement("w:fldChar")
    fld.set(qn("w:fldCharType"), "begin")
    run_begin._element.append(fld)
    if font_size:
        run_begin.font.name = "Times New Roman"
        run_begin.font.size = Pt(font_size)

    run_instr = paragraph.add_run()
    instr_el = OxmlElement("w:instrText")
    instr_el.set(qn("xml:space"), "preserve")
    instr_el.text = instr
    run_instr._element.append(instr_el)

    run_sep = paragraph.add_run()
    fld = OxmlElement("w:fldChar")
    fld.set(qn("w:fldCharType"), "separate")
    run_sep._element.append(fld)

    if cached:
        cached_run = paragraph.add_run(cached)
        if font_size:
            cached_run.font.name = "Times New Roman"
            cached_run.font.size = Pt(font_size)

    run_end = paragraph.add_run()
    fld = OxmlElement("w:fldChar")
    fld.set(qn("w:fldCharType"), "end")
    run_end._element.append(fld)


def add_ref(paragraph, bookmark: str, cached: str):
    add_field(paragraph, f" REF {bookmark} \\h ", cached)


def add_bookmark_around_run(paragraph, run, bookmark: str):
    _BOOKMARK_ID[0] += 1
    bm_id = str(_BOOKMARK_ID[0])
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), bm_id)
    start.set(qn("w:name"), bookmark)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), bm_id)
    run._element.addprevious(start)
    run._element.addnext(end)


REF_PATTERN = re.compile(r"\{\{(fig|tab):([a-zA-Z0-9]+)\}\}")


def add_rich_text(paragraph, text: str):
    """写入文本，把 {{fig:f31}} / {{tab:t51}} 替换为交叉引用域。"""
    position = 0
    for match in REF_PATTERN.finditer(text):
        if match.start() > position:
            paragraph.add_run(text[position:match.start()])
        kind, key = match.group(1), match.group(2)
        if kind == "fig":
            number = C.FIGURES[key][0]
            bookmark = f"fig_{number.replace('-', '_')}"
        else:
            number = C.TABLES[key][0]
            bookmark = f"tab_{number.replace('-', '_')}"
        add_ref(paragraph, bookmark, number)
        position = match.end()
    if position < len(text):
        paragraph.add_run(text[position:])


# ---------------------------------------------------------------------------
# 三线表
# ---------------------------------------------------------------------------


def _set_cell_text(cell, text: str, doc=None, bold: bool = False, font_size: float = 9.5):
    cell.text = ""
    paragraph = cell.paragraphs[0]
    document = doc if doc is not None else cell.part.document
    paragraph.style = document.styles["Thesis Table Text"]
    paragraph.paragraph_format.space_before = Pt(1)
    paragraph.paragraph_format.space_after = Pt(1)
    run = paragraph.add_run(text)
    run.font.bold = bold
    run.font.size = Pt(font_size)


def _table_borders(table, header_row_index: int = 0, sep_rows: list[int] = None):
    """三线表：顶线/表头线/底线 0.5pt，无竖线；sep_rows 为需要下细线的行。"""
    tbl = table._element
    tbl_pr = tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge, sz, color in (("top", 6, "000000"), ("bottom", 6, "000000"),
                            ("left", 0, "000000"), ("right", 0, "000000"),
                            ("insideH", 0, "000000"), ("insideV", 0, "000000")):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single" if sz else "none")
        el.set(qn("w:sz"), str(sz))
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), color)
        borders.append(el)
    tbl_pr.append(borders)

    def row_bottom(row, sz=6):
        for cell in row.cells:
            tc_pr = cell._element.get_or_add_tcPr()
            tc_borders = OxmlElement("w:tcBorders")
            bottom = OxmlElement("w:bottom")
            bottom.set(qn("w:val"), "single")
            bottom.set(qn("w:sz"), str(sz))
            bottom.set(qn("w:space"), "0")
            bottom.set(qn("w:color"), "000000")
            tc_borders.append(bottom)
            tc_pr.append(tc_borders)

    row_bottom(table.rows[header_row_index], 6)
    for index in sep_rows or []:
        row_bottom(table.rows[index], 2)


def _repeat_header(row):
    tr_pr = row._element.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    tr_pr.append(header)


def _display_width(text: str) -> int:
    """粗略显示宽度：中文/全角记 2，其余记 1。"""
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in str(text))


def _auto_col_widths(headers, rows, total_mm: float = 150.0, font_size: float = 9.5):
    """列宽分配：先满足各列“不折行”的最小宽度，富余按内容占比分配。

    中文按字号全宽、半角按半宽估算，另加单元格左右边距。
    """
    cjk_mm = font_size * 0.353
    half_mm = cjk_mm * 0.5
    margin_mm = 3.4

    def text_mm(text: str) -> float:
        cjk = sum(1 for ch in str(text) if ord(ch) > 0x2E80)
        half = len(str(text)) - cjk
        return cjk * cjk_mm + half * half_mm

    mins, content = [], []
    for j in range(len(headers)):
        column = [headers[j]] + [r[j] for r in rows]
        widest = max(text_mm(c) for c in column)
        content.append(widest)
        mins.append(widest + margin_mm)
    total_min = sum(mins)
    if total_min <= total_mm:
        extra = total_mm - total_min
        weight_sum = sum(content) or 1.0
        return [mins[i] + extra * content[i] / weight_sum for i in range(len(mins))]
    scale = total_mm / total_min
    return [m * scale for m in mins]


def _fixed_table_layout(table, total_mm: float = 150.0):
    tbl_pr = table._element.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tbl_pr.append(layout)
    width = OxmlElement("w:tblW")
    width.set(qn("w:w"), str(int(total_mm * 56.7)))
    width.set(qn("w:type"), "dxa")
    tbl_pr.append(width)


def add_three_line_table(doc, headers, rows, sep_rows=None, col_widths_mm=None,
                         font_size: float = 9.5):
    """添加三线表。rows 为字符串列表（可能含 *粗体* 标记）。"""
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.autofit = False
    for j, text in enumerate(headers):
        _set_cell_text(table.rows[0].cells[j], text, doc=doc, bold=True, font_size=font_size)
    _repeat_header(table.rows[0])
    for i, row in enumerate(rows, start=1):
        for j, text in enumerate(row):
            bold = text.startswith("*") and text.endswith("*")
            _set_cell_text(table.rows[i].cells[j], text.strip("*"), doc=doc, bold=bold,
                           font_size=font_size)
    _table_borders(table, 0, sep_rows)
    if col_widths_mm is None:
        col_widths_mm = _auto_col_widths(headers, rows, font_size=font_size)
    for j, width in enumerate(col_widths_mm):
        for row in table.rows:
            row.cells[j].width = Mm(width)
    _fixed_table_layout(table)
    return table


# ---------------------------------------------------------------------------
# 图表
# ---------------------------------------------------------------------------


def add_figure(doc, figure_id: str):
    number, stem, caption, width = C.FIGURES[figure_id]
    image_path = C.FIGURE_DIR / f"{stem}.png"
    if not image_path.exists():
        raise FileNotFoundError(image_path)

    para = doc.add_paragraph(style="Thesis Figure")
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    # 图片行必须使用单倍/自动行距，固定行距会裁剪图片
    para.paragraph_format.line_spacing = 1.0
    para.paragraph_format.space_after = Pt(3)
    run = para.add_run()
    run.add_picture(str(image_path), width=Mm(150 if width == "full" else 73))

    cap = doc.add_paragraph(style="Thesis Figure Caption")
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.add_run("图 ")
    number_run = cap.add_run(number)
    bookmark = f"fig_{number.replace('-', '_')}"
    add_bookmark_around_run(cap, number_run, bookmark)
    cap.add_run(f" {caption}")


def parse_tex_table(table_id: str):
    """解析自产 booktabs .tex：返回 (caption, headers, rows, sep_indices, notes)。"""
    filename = C.TABLES[table_id][1]
    text = (C.TABLE_DIR / f"{filename}.tex").read_text(encoding="utf-8")
    caption = re.search(r"\\caption\{(.*?)\}", text).group(1)
    body = text.split(r"\begin{tabular}")[1]
    body = body.split(r"\end{tabular}")[0]
    body = body.split("}", 1)[1]  # 去掉列格式
    rows_raw: list[list[str]] = []
    sep_indices: list[int] = []
    current: list[str] = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        if line == r"\midrule":
            sep_indices.append(len(current) - 1)  # 上一行加分隔线
            continue
        if line in (r"\toprule", r"\bottomrule"):
            continue
        if line.endswith(r"\\"):
            line = line[:-2].strip()
        # 规范化空首格/空尾格（生成的行可能以 "& " 开头或以 " &" 结尾）
        if line.startswith("& "):
            line = " " + line
        if line.endswith(" &"):
            line = line + " "
        cells = [c.strip() for c in line.split(" & ")]
        current.append(cells)
    headers, data_rows = current[0], current[1:]
    notes_match = re.search(r"\\begin\{flushleft\}\\footnotesize(.*?)\\end\{flushleft\}",
                            text, re.S)
    notes = []
    if notes_match:
        notes = [n.strip().rstrip("\\").strip()
                 for n in notes_match.group(1).splitlines() if n.strip()]

    def unescape(cell: str) -> str:
        if cell.startswith(r"\textbf{") and cell.endswith("}"):
            inner = cell[len(r"\textbf{"):-1]
            return "*" + unescape(inner) + "*"
        return (cell.replace(r"\,", " ")
                    .replace(r"\_", "_").replace(r"\%", "%").replace(r"\&", "&")
                    .replace(r"\#", "#").replace(r"\$", "$"))

    headers = [unescape(c) for c in headers]
    data_rows = [[unescape(c) for c in row] for row in data_rows]
    notes = [n.replace(r"\_", "_").replace(r"\%", "%").replace(r"\&", "&")
             for n in notes]
    return caption, headers, data_rows, sep_indices, notes


def add_table_block(doc, table_id: str):
    number, _, _ = C.TABLES[table_id]
    caption, headers, rows, sep_indices, notes = parse_tex_table(table_id)

    cap = doc.add_paragraph(style="Thesis Table Caption")
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.add_run("表 ")
    number_run = cap.add_run(number)
    bookmark = f"tab_{number.replace('-', '_')}"
    add_bookmark_around_run(cap, number_run, bookmark)
    cap.add_run(f" {caption}")

    # 列数多时缩小字号，保证不超版心
    n_cols = len(headers)
    font_size = 10.5 if n_cols <= 6 else (9.5 if n_cols <= 8 else 9.0)
    table = add_three_line_table(doc, headers, rows, sep_rows=sep_indices, font_size=font_size)
    table.alignment = WD_ALIGN_PARAGRAPH.CENTER

    for note in notes:
        note_para = doc.add_paragraph(style="Thesis Table Text")
        run = note_para.add_run("注：" + note if note is notes[0] else note)
        run.font.size = Pt(8.5)
    blank = doc.add_paragraph(style="Thesis Body")
    blank.paragraph_format.space_after = Pt(6)


# ---------------------------------------------------------------------------
# OMML 公式
# ---------------------------------------------------------------------------


def _m_run(text: str, italic: bool = False, size: int | None = None) -> str:
    sty = "i" if italic else "p"
    size_xml = f'<m:rPr><m:sty m:val="{sty}"/></m:rPr>' if italic else f'<m:rPr><m:sty m:val="{sty}"/></m:rPr>'
    return (f"<m:r>{size_xml}<w:rPr><w:rFonts w:ascii=\"Cambria Math\" "
            f"w:hAnsi=\"Cambria Math\"/></w:rPr><m:t xml:space=\"preserve\">{text}</m:t></m:r>")


def _m_s_sub(base: str, sub: str) -> str:
    return f"<m:sSub><m:e>{base}</m:e><m:sub>{sub}</m:sub></m:sSub>"


def _m_s_sup(base: str, sup: str) -> str:
    return f"<m:sSup><m:e>{base}</m:e><m:sup>{sup}</m:sup></m:sSup>"


def _m_s_subsup(base: str, sub: str, sup: str) -> str:
    return (f"<m:sSubSup><m:e>{base}</m:e><m:sub>{sub}</m:sub>"
            f"<m:sup>{sup}</m:sup></m:sSubSup>")


def _m_frac(num: str, den: str) -> str:
    return f"<m:f><m:num>{num}</m:num><m:den>{den}</m:den></m:f>"


EQUATIONS = {
    "loss_total": lambda: (
        _m_s_sub(_m_run("L", True), _m_run("total", False))
        + _m_run(" = ", False)
        + _m_run("Σ", False) + _m_s_sub(_m_run("L", True), _m_run("cross", False))
        + _m_run(" + ", False)
        + _m_run("Σ", False) + _m_run("ρ", False) + _m_run("(", False)
        + _m_run("R", True) + _m_run(")", False) + _m_run("·", False)
        + _m_run("s", True)
        + _m_run(" + ", False)
        + _m_run("0.005", False) + _m_run("·", False)
        + _m_s_sub(_m_run("l", True), _m_run("straight", False))
    ),
    "rmin": lambda: (
        _m_s_sub(_m_run("R", True), _m_run("min", False))
        + _m_run(" = ", False)
        + _m_frac(
            _m_run("2", False) + _m_s_subsup(_m_run("L", True), _m_run("xy", False), _m_run("2", False)),
            _m_s_sup(_m_run("π", False), _m_run("2", False)) + _m_run("|Δz|", False),
        )
    ),
}


def add_equation(doc, key: str, number: str):
    para = doc.add_paragraph(style="Thesis Equation")
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    math_xml = (
        f'<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
        f'xmlns:w="{W}">{EQUATIONS[key]()}</m:oMath>'
    )
    from docx.oxml import parse_xml

    para._element.append(parse_xml(math_xml))
    run = para.add_run(f"\t（{number}）")
    return para


# ---------------------------------------------------------------------------
# 主体构建
# ---------------------------------------------------------------------------


def build_cover(doc):
    """在最前面插入封面（封面为前置节的首页，靠“首页不同”隐藏页眉页码）。"""
    body = doc.element.body

    cover_lines = [
        ("", 12), (C.COVER["school"], 22, True), (C.COVER["doc_type"], 16),
        ("", 14), (C.COVER["title"], 18, True), ("", 16),
        (f"学生姓名：{C.COVER['author']}", 14),
        (f"学生学号：{C.COVER['student_id']}", 14),
        (f"专    业：{C.COVER['major']}", 14),
        (f"指导教师：{C.COVER['advisor']}", 14),
        (f"学院（系）：{C.COVER['college']}", 14),
        ("", 12), (C.COVER["date"], 14),
    ]
    elements = []
    for line in cover_lines:
        text = line[0]
        size = line[1] if len(line) > 1 else 14
        bold = line[2] if len(line) > 2 else False
        para_el = OxmlElement("w:p")
        if text:
            ppr = OxmlElement("w:pPr")
            jc = OxmlElement("w:jc")
            jc.set(qn("w:val"), "center")
            ppr.append(jc)
            para_el.append(ppr)
            run_el = OxmlElement("w:r")
            rpr = OxmlElement("w:rPr")
            fonts = OxmlElement("w:rFonts")
            fonts.set(qn("w:ascii"), "Times New Roman")
            fonts.set(qn("w:eastAsia"), "宋体")
            rpr.append(fonts)
            if bold:
                rpr.append(OxmlElement("w:b"))
            sz = OxmlElement("w:sz")
            sz.set(qn("w:val"), str(size * 2))
            rpr.append(sz)
            run_el.append(rpr)
            t = OxmlElement("w:t")
            t.text = text
            run_el.append(t)
            para_el.append(run_el)
        elements.append(para_el)
    # 封面与前置部分同节（封面为节的首页，通过“首页不同”隐藏页眉页码），
    # 避免额外节断在 Word 中产生空白页。
    for offset, element in enumerate(elements):
        body.insert(offset, element)


def fill_front_matter(doc):
    """替换摘要/Abstract/关键词，替换目录域，填充符号表。"""
    def find_paragraph(marker: str):
        for p in doc.paragraphs:
            if marker in p.text:
                return p
        raise RuntimeError(f"未找到占位段落：{marker}")

    _set_paragraph_text(find_paragraph("【中文摘要正文待填写】"), C.ABSTRACT)
    _set_paragraph_text(find_paragraph("关键词：XXXX"), "关键词：" + C.KEYWORDS)
    _set_paragraph_text(find_paragraph("【English abstract to be written】"), C.ABSTRACT_EN)
    _set_paragraph_text(find_paragraph("Keywords: XXX"), "Keywords: " + C.KEYWORDS_EN)

    # 关键词样式段（ThesisKeywords）的 run 格式由样式控制，此处保留。

    # 目录：删除 toc 占位段（样式名以 toc 开头），在"目 录"标题后插入 TOC 域
    to_delete = [p for p in doc.paragraphs if p.style.name.lower().startswith("toc")]
    anchor = None
    for p in doc.paragraphs:
        if p.text.strip() == "目 录":
            anchor = p
    for p in to_delete:
        p._element.getparent().remove(p._element)

    toc_para = OxmlElement("w:p")
    ppr = OxmlElement("w:pPr")
    spacing = OxmlElement("w:spacing")
    spacing.set(qn("w:after"), "120")
    ppr.append(spacing)
    toc_para.append(ppr)
    anchor._element.addnext(toc_para)

    # 以 python-docx 包装写入域
    from docx.text.paragraph import Paragraph

    toc_wrapper = Paragraph(toc_para, anchor._parent)
    add_field(toc_wrapper, r' TOC \o "1-3" \h \z \u ',
              "（右键“更新域”生成目录；导出 PDF 前由脚本自动更新）")

    # 符号表：删除原表格，按 3 列重建并放回原位置
    symbols = [
        ("R", "弯曲半径", "Bend radius (mm)"),
        ("Lcross / Lbend / lstraight", "交叉/弯曲/直线损耗分量", "Crossing / bend / straight loss components (dB)"),
        ("ρ(R)", "弯曲损耗密度", "Bend loss density (dB/mm)"),
        ("θ", "交叉角或弯曲角", "Crossing or bend angle (degree)"),
        ("α", "自由弯角圆弧转角", "Arc turn angle of freeform S-bend (degree)"),
        ("P95", "逐路总损耗第 95 百分位", "95th percentile of per-route total loss (dB)"),
        ("K", "候选轨道数", "Number of candidate tracks"),
        ("t0", "自由弯角引出段比例", "Lead-in length fraction of freeform bend"),
        ("Δz / Lxy", "层间高差 / 过渡水平投影长", "Layer height difference / transition run (mm)"),
    ]
    old_table = doc.tables[0]
    new_table = doc.add_table(rows=1, cols=3)
    new_table.autofit = False
    for j, text in enumerate(("符号", "含义", "Meaning (English)")):
        _set_cell_text(new_table.rows[0].cells[j], text, doc=doc, bold=True, font_size=10.5)
    _repeat_header(new_table.rows[0])
    for symbol, meaning, english in symbols:
        row = new_table.add_row()
        _set_cell_text(row.cells[0], symbol, doc=doc, font_size=10.5)
        _set_cell_text(row.cells[1], meaning, doc=doc, font_size=10.5)
        _set_cell_text(row.cells[2], english, doc=doc, font_size=10.5)
    _table_borders(new_table, 0)
    old_table._element.addprevious(new_table._element)
    old_table._element.getparent().remove(old_table._element)


def strip_placeholder_body(doc):
    """删除模板正文占位（主要符号表节之后的所有段落与表格）。"""
    body = doc.element.body
    # 找到"主要符号表"节结束的段落（含 sectPr 的最后一个前置段落）
    keep_until = None
    seen_symbols = False
    for child in list(body):
        if child.tag == w("p"):
            text = "".join(child.itertext())
            if "主要符号表" in text:
                seen_symbols = True
            if seen_symbols and child.find(f".//{w('sectPr')}") is not None:
                keep_until = child
                break
    if keep_until is None:
        raise RuntimeError("未找到主要符号表节结束段落")
    # 删除其后所有元素（段落与表格）
    started = False
    for child in list(body):
        if child is keep_until:
            started = True
            continue
        if started and child.tag != w("sectPr"):
            body.remove(child)
    # 正文节页码从 1 重启（阿拉伯）
    last_sect = body.find(w("sectPr"))
    pg = last_sect.find(w("pgNumType"))
    if pg is None:
        pg = OxmlElement("w:pgNumType")
        last_sect.insert(0, pg)
    for attr in ("w:fmt", "w:start"):
        if pg.get(qn(attr)) is not None:
            del pg.attrib[qn(attr)]
    pg.set(qn("w:start"), "1")


def set_body_header(doc, text="电子科技大学学士学位论文"):
    """正文节页眉统一为学校名（奇偶相同）。"""
    last = doc.sections[-1]
    header = last.header
    header.is_linked_to_previous = False
    for para in header.paragraphs:
        _set_paragraph_text(para, text)
        for run in para.runs:
            run.font.size = Pt(10.5)
    even_header = last.even_page_header
    even_header.is_linked_to_previous = False
    for para in even_header.paragraphs:
        _set_paragraph_text(para, text)
        for run in para.runs:
            run.font.size = Pt(10.5)


def render_body(doc):
    first_chapter = True
    for chapter in CHAPTERS:
        heading = doc.add_paragraph(style="Thesis Chapter")
        heading.add_run(chapter["title"])
        if first_chapter:
            # 节分页已保证正文另起页，避免样式 pageBreakBefore 叠加产生空白页
            heading.paragraph_format.page_break_before = False
            first_chapter = False
        for block in chapter["blocks"]:
            kind = block[0]
            if kind == "h1":
                doc.add_paragraph(style="Thesis Heading 1").add_run(block[1])
            elif kind == "h2":
                doc.add_paragraph(style="Thesis Heading 2").add_run(block[1])
            elif kind == "p":
                para = doc.add_paragraph(style="Thesis Body")
                add_rich_text(para, block[1])
            elif kind == "figure":
                add_figure(doc, block[1])
            elif kind == "table":
                add_table_block(doc, block[1])
            elif kind == "equation":
                add_equation(doc, block[1][0], block[1][1])
            else:
                raise ValueError(kind)


def _back_title(doc, text: str):
    """后置标题：另起页。"""
    paragraph = doc.add_paragraph(style="Thesis Back Title")
    paragraph.add_run(text)
    paragraph.paragraph_format.page_break_before = True
    return paragraph


def render_back_matter(doc):
    # 参考文献（Thesis Reference 样式自带 [n] 方括号自动编号）
    _back_title(doc, "参考文献")
    for ref in C.REFERENCES:
        para = doc.add_paragraph(style="Thesis Reference")
        para.add_run(ref)
    note = doc.add_paragraph(style="Thesis Body")
    run = note.add_run(C.REFERENCES_NOTE)
    run.font.size = Pt(10.5)

    # 致谢
    _back_title(doc, "致谢")
    doc.add_paragraph(style="Thesis Body").add_run(ACKNOWLEDGEMENT)

    # 附录 A：补充图
    _back_title(doc, "附录 A　补充图表")
    for block in APPENDIX_INTRO:
        para = doc.add_paragraph(style="Thesis Body")
        add_rich_text(para, block[1])
    appendix_figures = ["f35", "f36", "f38", "f54", "f67", "f73", "f76", "f80", "f82", "f86"]
    for fid in appendix_figures:
        add_figure(doc, fid)

    # 附录 B：实验覆盖清单
    _back_title(doc, "附录 B　实验覆盖清单")
    para = doc.add_paragraph(style="Thesis Body")
    para.add_run("下表列出本项目全部 41 项实验（清单 ID 与 publication/manifest/"
                 "experiment_inventory.csv 一致）及其图表覆盖。全部实验均在正文或附录中"
                 "有明确位置；基础验证步（9-A/9-B/9-C）与两项一致性核对按设计不绘图，"
                 "在上表中以“核对/验证”状态注明。")
    inventory = C.inventory_frame()
    groups = [
        ("论文复现", 0),
        ("Step 12", 0),
        ("Step 13", 0),
        ("Step 14", 0),
        ("三维", 0),
    ]
    # 按出现顺序分组
    ordered_groups = []
    for group, _ in groups:
        sub = inventory[inventory["group"] == group]
        if len(sub):
            ordered_groups.append((group, sub))
    for group, frame in ordered_groups:
        cap = doc.add_paragraph(style="Thesis Table Caption")
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        number = {"论文复现": "B-1", "Step 12": "B-2", "Step 13": "B-3",
                  "Step 14": "B-4", "三维": "B-5"}[group]
        cap.add_run(f"表 {number} {group}实验清单（{len(frame)} 项）")
        rows = []
        for _, row in frame.iterrows():
            figures = str(row["figures"]).replace(";", "、") or "—"
            tables = str(row["tables"]).replace(";", "、")
            if tables in ("", "nan", "--"):
                tables = "—"
            rows.append([str(row["experiment_id"]), str(row["name"]),
                         str(row["scale"]), str(row["status"]), figures, tables])
        add_three_line_table(
            doc, ["ID", "实验名称", "规模", "状态", "覆盖图", "覆盖表"], rows,
            col_widths_mm=[17, 50, 20, 11, 28, 24], font_size=9.5)
        blank = doc.add_paragraph(style="Thesis Body")
        blank.paragraph_format.space_after = Pt(4)

    # 附录 C：来源与复现说明
    _back_title(doc, "附录 C　图表来源与复现说明")
    lines = [
        "本报告全部图表由统一入口脚本从已有实验产物只读生成：",
        "　　python scripts/publication/make_publication.py",
        "“图”与“表”编号与 publication/manifest 中的覆盖表一一对应；每张图的源文件、"
        "字段、筛选条件与单位记录于 figure_sources.csv 与 figure_coverage.csv。",
        "生成前后对 346 个实验数据文件做 SHA-256 核验，结果为完全一致（零变更），"
        "证明原始实验数据未被修改；核验记录见 data_hashes_before.json 与 "
        "data_hashes_after.json。",
        "本报告的 Word 版由报告脚本 build_report_docx.py 生成，PDF 版由最终 Word 文档"
        "经由 Microsoft Word 导出，两者内容一致；.doc 兼容版为同一文档另存，"
        "未改后缀伪装。",
        "数据完整性、数值验证与视觉检查的完整记录见 publication/manifest/"
        "quality_review.md。",
    ]
    for line in lines:
        doc.add_paragraph(style="Thesis Body").add_run(line)


def strip_rendered_page_breaks(doc):
    """删除模板遗留的 lastRenderedPageBreak 渲染缓存，避免导出沿用旧分页。"""
    body = doc.element.body
    for element in body.iter(w("lastRenderedPageBreak")):
        parent = element.getparent()
        if parent is not None:
            parent.remove(element)


def rebuild_front_sections(doc):
    """前置部分结构整理：
    * 封面与前置部分同节（首页=封面，用 titlePg 隐藏页眉页码）；
    * 删除前置内部的模板节断（摘要/Abstract/目录），改用分页符控制换页；
    * 前置节页码：罗马 start=0（封面计 0 不显示，摘要从 i 起）。
    """
    body = doc.element.body
    sect_paras = []
    for child in body:
        if child.tag == w("p") and child.find(f".//{w('sectPr')}") is not None:
            sect_paras.append(child)
    if len(sect_paras) < 4:
        raise RuntimeError(f"预期至少 4 个段落级分节（当前 {len(sect_paras)}）")
    # 删除摘要、Abstract、目录三个节断空段（前置内部），保留符号表节断（前置→正文分界）
    for para in sect_paras[:3]:
        para.getparent().remove(para)
    # 为中文摘要、Abstract、目录、符号表标题设置段前分页（封面独立成页）
    for paragraph in doc.paragraphs:
        if paragraph.text.strip() in ("中文摘要", "Abstract", "目 录", "主要符号表"):
            paragraph.paragraph_format.page_break_before = True
    # 前置节（sections[0]）：titlePg（封面不显示页眉页码）+ 罗马页码从 0 计
    front_sect = doc.sections[0]._sectPr
    if front_sect.find(w("titlePg")) is None:
        front_sect.insert(0, OxmlElement("w:titlePg"))
    pg = front_sect.find(w("pgNumType"))
    if pg is None:
        pg = OxmlElement("w:pgNumType")
        front_sect.insert(0, pg)
    pg.set(qn("w:fmt"), "lowerRoman")
    pg.set(qn("w:start"), "0")


def add_nested_page_minus_one(paragraph, font_size: float | None = None):
    """插入嵌套域 { = { PAGE } - 1 \\* roman }：封面计 1、摘要显示 i。"""
    def run_with(child_builder):
        run = paragraph.add_run()
        child_builder(run._element)
        if font_size:
            run.font.name = "Times New Roman"
            run.font.size = Pt(font_size)
        return run

    def make_fld(run_el):
        fld = OxmlElement("w:fldChar")
        fld.set(qn("w:fldCharType"), "begin")
        run_el.append(fld)

    def make_instr(text):
        def builder(run_el):
            instr = OxmlElement("w:instrText")
            instr.set(qn("xml:space"), "preserve")
            instr.text = text
            run_el.append(instr)
        return builder

    def make_sep(run_el):
        fld = OxmlElement("w:fldChar")
        fld.set(qn("w:fldCharType"), "separate")
        run_el.append(fld)

    def make_end(run_el):
        fld = OxmlElement("w:fldChar")
        fld.set(qn("w:fldCharType"), "end")
        run_el.append(fld)

    def make_text(text):
        def builder(run_el):
            t = OxmlElement("w:t")
            t.text = text
            run_el.append(t)
        return builder

    run_with(make_fld)                      # 外域开始
    run_with(make_instr("= "))
    run_with(make_fld)                      # 内域开始
    run_with(make_instr(" PAGE "))
    run_with(make_sep)
    run_with(make_text("2"))
    run_with(make_end)
    run_with(make_instr(" - 1 \\* roman "))
    run_with(make_sep)
    run_with(make_text("i"))
    run_with(make_end)


def fix_front_layout(doc):
    """前置节（含封面页）：首页无页眉页脚；其余页眉学校名、页脚显示 PAGE-1 罗马页码。"""
    front = doc.sections[0]
    front.first_page_footer.is_linked_to_previous = False
    for para in front.first_page_footer.paragraphs:
        _clean_paragraph(para)
    front.first_page_header.is_linked_to_previous = False
    for para in front.first_page_header.paragraphs:
        _clean_paragraph(para)
    for footer in (front.footer, front.even_page_footer):
        footer.is_linked_to_previous = False
        for para in footer.paragraphs:
            _clean_paragraph(para)
        para = footer.paragraphs[0]
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        add_field(para, " PAGE ", "ii", font_size=9)
    for header in (front.header, front.even_page_header):
        header.is_linked_to_previous = False
        for para in header.paragraphs:
            _set_paragraph_text(para, "电子科技大学学士学位论文")


def normalize_front_page_numbers(doc):
    """前置节页码连续：保留摘要节 start=1，删除其余前置节的 start（避免与
    变长的英文摘要冲突），保持罗马数字格式。"""
    body = doc.element.body
    first = True
    for child in body:
        if child.tag != w("p"):
            continue
        sect = child.find(f".//{w('sectPr')}")
        if sect is None:
            continue
        pg = sect.find(w("pgNumType"))
        if pg is None:
            continue
        fmt = pg.get(qn("w:fmt"))
        if fmt == "lowerRoman" and not first:
            if pg.get(qn("w:start")) is not None:
                del pg.attrib[qn("w:start")]
        if fmt == "lowerRoman":
            first = False
        elif pg.get(qn("w:start")) == "1":
            break  # 到达正文节


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not TEMPLATE.exists():
        raise FileNotFoundError(TEMPLATE)
    shutil.copyfile(TEMPLATE, OUT_DOCX)  # 复制模板，不覆盖原件
    doc = Document(str(OUT_DOCX))

    build_cover(doc)
    strip_placeholder_body(doc)
    fill_front_matter(doc)
    rebuild_front_sections(doc)
    fix_front_layout(doc)
    strip_rendered_page_breaks(doc)
    set_body_header(doc)
    render_body(doc)
    render_back_matter(doc)

    doc.save(str(OUT_DOCX))
    print("已生成：", OUT_DOCX)
    print("下一步运行： python scripts/publication/export_report_pdf.py")


if __name__ == "__main__":
    main()
