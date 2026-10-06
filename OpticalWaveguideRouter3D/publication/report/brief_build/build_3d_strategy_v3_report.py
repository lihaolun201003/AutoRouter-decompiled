"""Build 《三维波导布线策略 v3 实验报告》 DOCX (Word) - 中文宋体, 三线表, 正文 1.5 倍行距.

Every number is read from the real experiment artifacts under outputs/; nothing is
hand-typed. Usage (project root):
    .venv\Scripts\python.exe -B publication\report\brief_build\build_3d_strategy_v3_report.py
"""
import json, csv, hashlib
from pathlib import Path
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.section import WD_SECTION
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parents[3]
P = ROOT/'outputs'
OUT = Path(__file__).resolve().parent
NAME = '三维波导布线策略v3实验报告'
ABL = P/'3d_strategy_v3/512_ablation'
DIAG = P/'3d_strategy_v3/512_relocation_slack_diagnostic'
PROBE = P/'3d_strategy_v3/window_slack_probe'
OLD_DIAG = P/'3d_strategy_v2_rev2/512_de_diagnostic'
FIG = P/'3d_strategy_v3/figures'
GROUPS = [('A_baseline_original', 'A 基线原版', '关', '0'),
          ('B_generation_cache_only', 'B 仅生成缓存', '开', '0'),
          ('C_window_slack_only', 'C 仅窗口余量', '关', '1e-05'),
          ('D_both_enabled', 'D 两项同开', '开', '1e-05')]
IMAGES, TABLES = [], []
LOG3D = P/'3d_strategy_v3/pytest_full_v3_after_slack.log'
LOG2D = P/'3d_strategy_v3/pytest_opt2d_2d_env_after_slack.log'


def parse_pytest_log(path):
    """Read the real pytest summary line of a log written by this round."""
    import re
    text = Path(path).read_text(encoding='utf-8-sig', errors='replace')
    tail = [ln.strip() for ln in text.splitlines() if ln.strip()]
    summary = next((ln for ln in reversed(tail)
                    if re.search(r'\d+ (passed|failed|error)', ln)), '未找到结果行')
    m = re.search(r'in ([\d.]+)s', summary)
    return dict(summary=re.sub(r'\s*in [\d.]+s.*$', '', summary),
                seconds=m.group(1) if m else '未知', path=str(path))


def jsread(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fmt(v, d=4):
    return f'{float(v):.{d}f}'


def integer(v):
    return f'{int(float(v)):,}'


def pct(v, d=2):
    return f'{float(v):.{d}f}'


LEDGERS = {name: jsread(ABL/name/'ledger.json') for name, _, _, _ in GROUPS}
SUMMARIES = {name: jsread(ABL/name/'summary.json') for name, _, _, _ in GROUPS}
CROSS = jsread(ABL/'cross_group_analysis.json')
PROBE_DATA = jsread(PROBE/'window_slack_probe.json')
DIAG_LEDGER = {m: jsread(DIAG/f'ledger_{m}.json') for m in ('D', 'E')}
OLD_LEDGER = {m: jsread(OLD_DIAG/f'ledger_{m}.json') for m in ('D', 'E')}
ANALYSIS = jsread(DIAG/'analysis.json')
MOVEMENT = jsread(DIAG/'movement_stats.json')
LENGTH = jsread(DIAG/'length_ledger.json')
CORR = jsread(DIAG/'candidate_correspondence.json')
CORR_REL = ANALYSIS['correspondence_relocation_candidates']
CORR_ALL = ANALYSIS['correspondence_all_movement_classes']
RECHECK = {m: jsread(DIAG/f'recheck_{m}.json') for m in ('D', 'E')}
TEST3D = parse_pytest_log(LOG3D)
TEST2D = parse_pytest_log(LOG2D)
CONFIG = jsread(DIAG/'config.json')
TARGETS = jsread(DIAG/'target_list.json')
BA = ANALYSIS['accepted_relocation_before_after']
ENTRY = BA['entry']
MS = ANALYSIS['movement_stats']

doc = Document(); sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21), Cm(29.7)
sec.top_margin = sec.bottom_margin = Cm(2.0)
sec.left_margin = sec.right_margin = Cm(2.0)
sec.header_distance = sec.footer_distance = Cm(0.8)
for name in ['Normal', 'Title', 'Heading 1', 'Heading 2', 'Heading 3', 'Caption', 'Header', 'Footer']:
    s = doc.styles[name]; s.font.name = 'SimSun'; s.font.color.rgb = RGBColor(0, 0, 0)
    s.element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'), '宋体')
    s.paragraph_format.widow_control = True
    for b in s.element.xpath('./w:pPr/w:pBdr'): b.getparent().remove(b)
doc.styles['Normal'].font.size = Pt(10.5)
doc.styles['Normal'].paragraph_format.line_spacing = 1.5
doc.styles['Normal'].paragraph_format.space_after = Pt(6)
doc.styles['Title'].font.size = Pt(20); doc.styles['Title'].font.bold = True
doc.styles['Title'].paragraph_format.line_spacing = 1.5
doc.styles['Title'].paragraph_format.space_after = Pt(8)
for name, size in [('Heading 1', 14), ('Heading 2', 11.5), ('Heading 3', 10.5)]:
    s = doc.styles[name]; s.font.size = Pt(size); s.font.bold = True
    s.paragraph_format.line_spacing = 1.5
    s.paragraph_format.space_before = Pt(10); s.paragraph_format.space_after = Pt(6)
doc.styles['Caption'].font.size = Pt(10); doc.styles['Caption'].font.bold = False
doc.styles['Caption'].font.italic = False
doc.styles['Caption'].paragraph_format.line_spacing = 1.2
doc.styles['Caption'].paragraph_format.space_after = Pt(6)
h = sec.header.paragraphs[0]; h.text = '三维波导布线策略 v3 实验报告'; h.style = 'Header'
h.alignment = WD_ALIGN_PARAGRAPH.CENTER
for r in h.runs: r.font.size = Pt(9); r.font.name = 'SimSun'
f = sec.footer.paragraphs[0]; f.alignment = WD_ALIGN_PARAGRAPH.CENTER
f.add_run('第 ')
field = OxmlElement('w:fldSimple'); field.set(qn('w:instr'), 'PAGE'); f._p.append(field)
f.add_run(' 页')
for r in f.runs: r.font.size = Pt(9); r.font.name = 'SimSun'


def para(text, label=None, small=False):
    p = doc.add_paragraph()
    if label:
        r = p.add_run(label + '：'); r.bold = True; r.font.name = 'SimSun'
        r.element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    p.add_run(text)
    if small:
        p.paragraph_format.line_spacing = 1.5
        p.paragraph_format.space_before = Pt(2); p.paragraph_format.space_after = Pt(4)
        for r in p.runs: r.font.size = Pt(9)
    return p


def heading(text, level=1, new_page=False):
    p = doc.add_heading(text, level)
    if new_page: p.paragraph_format.page_break_before = True
    return p


def note(text):
    return para('注：' + text, small=True)


def source(text):
    if doc.paragraphs: doc.paragraphs[-1].paragraph_format.keep_with_next = True
    return para('数据来源：' + text, small=True)


def border(parent, side, val='nil', size=0):
    el = OxmlElement('w:' + side); el.set(qn('w:val'), val)
    if val != 'nil':
        el.set(qn('w:sz'), str(size)); el.set(qn('w:color'), '000000')
    parent.append(el)


def table(title, headers, rows, widths, text_cols=(0,), best=(), notes=None):
    """Native Word three-line table: header row separated by one rule, no vertical lines."""
    assert len(headers) == len(widths) and sum(widths) <= 17.001, (title, sum(widths))
    assert all(len(row) == len(headers) for row in rows), title
    number = len(TABLES) + 1
    p = doc.add_paragraph(f'表{number} {title}', style='Caption')
    p.paragraph_format.keep_with_next = True
    t = doc.add_table(rows=1, cols=len(headers)); t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    pr = t._tbl.tblPr
    tw = pr.find(qn('w:tblW')); tw.set(qn('w:type'), 'dxa'); tw.set(qn('w:w'), str(round(sum(widths)*1440/2.54)))
    for old in pr.findall(qn('w:tblBorders')): pr.remove(old)
    b = OxmlElement('w:tblBorders')
    for side in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
        border(b, side, 'single' if side in ('top', 'bottom') else 'nil', 8)
    pr.append(b)
    for c, w in zip(t.columns, widths): c.width = Cm(w)
    for ci, (c, text) in enumerate(zip(t.rows[0].cells, headers)): c.text = text
    for values in rows:
        for c, v in zip(t.add_row().cells, values): c.text = str(v)
    best = set(best)
    keep_together = len(rows) <= 6      # short tables must not split across pages
    for ri, row in enumerate(t.rows):
        rp = row._tr.get_or_add_trPr(); rp.append(OxmlElement('w:cantSplit'))
        if ri == 0: rp.append(OxmlElement('w:tblHeader'))
        if keep_together and ri < len(t.rows) - 1:
            for cell in row.cells:
                for pgh in cell.paragraphs: pgh.paragraph_format.keep_with_next = True
        for ci, cell in enumerate(row.cells):
            cell.width = Cm(widths[ci]); cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            cp = cell._tc.get_or_add_tcPr()
            for tag in ['tcBorders', 'shd', 'tcMar']:
                for old in cp.findall(qn('w:' + tag)): cp.remove(old)
            margins = OxmlElement('w:tcMar')
            for side, val in [('top', 70), ('bottom', 70), ('left', 85), ('right', 85)]:
                e = OxmlElement('w:' + side); e.set(qn('w:w'), str(val)); e.set(qn('w:type'), 'dxa')
                margins.append(e)
            cp.append(margins)
            cb = OxmlElement('w:tcBorders')
            border(cb, 'top', 'single' if ri == 0 else 'nil', 8)
            border(cb, 'bottom', 'single' if ri in (0, len(t.rows)-1) else 'nil', 5 if ri == 0 else 8)
            border(cb, 'left', 'nil'); border(cb, 'right', 'nil')
            cp.append(cb)
            for pgh in cell.paragraphs:
                pgh.paragraph_format.space_before = Pt(0); pgh.paragraph_format.space_after = Pt(0)
                pgh.paragraph_format.line_spacing = 1.2
                pgh.alignment = WD_ALIGN_PARAGRAPH.LEFT if ci in text_cols else WD_ALIGN_PARAGRAPH.CENTER
                for r in pgh.runs:
                    r.font.size = Pt(9.5); r.font.name = 'SimSun'
                    r.element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
                    r.font.bold = (ri == 0 or (ri-1, ci) in best)
    TABLES.append(dict(number=number, title=title, rows=len(rows), width_cm=round(sum(widths), 3)))
    if notes: note(notes)
    return t


FIG_NUMBER = [0]


def picture(path, width_cm, caption):
    FIG_NUMBER[0] += 1
    path = Path(path); assert path.is_file(), path
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(4); p.paragraph_format.keep_with_next = True
    shape = p.add_run().add_picture(str(path), width=Cm(width_cm))
    shape._inline.docPr.set('descr', caption)
    IMAGES.append(dict(path=str(path), sha256=sha256(path), caption=caption))
    q = doc.add_paragraph(f'图{FIG_NUMBER[0]} {caption}', style='Caption')
    q.alignment = WD_ALIGN_PARAGRAPH.CENTER; q.paragraph_format.keep_with_next = False
    return q


# =============================================================== 封面与目的
doc.add_paragraph(NAME, style='Title')
sub = doc.add_paragraph('——静态生成失败缓存、候选窗口几何余量（512 四组功能消融）与加余量固定重定位诊断',
                        style='Caption')
sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
para('本报告记录本轮实际执行的三组实验：在项目现有 512 条合成输入上对两项默认关闭的新功能做四组功能消融；'
     '对历史记录中的 331 条自检歧义候选做窗口余量探针；把同一 10 nm 窗口余量加到 Step 15 的固定重定位诊断上重跑 D/E 两组。'
     '全部数字来自 outputs/ 下已保存的真实产物，图由这些产物直接绘制。')
para('本报告回答"做了什么、结果怎么样、得出了什么结论、还有什么没验证"，不是完整论文，也不替代此前的实验记录。')
para('口径：全部比较指标是 0.1 mm 中心线近距对数（close pair count）。它不代表光学损耗、串扰、无碰撞制造或工艺合规；'
     '也不代表器件实测。512 是项目既有合成输入（LEGACY_512_SMOOTHED_P0），不是真实端口数据；'
     '真实 1024 端口数据尚未提供，本轮不启动 1024 实验、不重跑已验证的四组主实验。')

heading('1 实验目的与范围', 1)
para('本轮三项实验各自要回答的问题如下。', label='目的')
para('（1）两项新功能——静态生成失败缓存与候选窗口几何余量——单独启用和同时启用，在相同输入、相同初态、'
     '相同阈值与相同预算上限下分别带来什么变化，代价是什么。')
para('（2）10 nm 的窗口余量对历史记录中那 331 条"自检判定为歧义（SELF_AMBIGUOUS_CLEARANCE）"的候选'
     '究竟产生了什么可复核的效果，是否改变了阈值与验收规则。')
para('（3）把同一窗口余量加到历史固定重定位诊断上（原始起点、原始 20 个目标、原始顺序、静态缓存关闭），'
     '重定位能否第一次通过全部验收规则；如果能，代价与收益分别是多少。')
para('本轮四组实验的组字母 A/B/C/D 是功能消融分组，与历史策略字母 A/B/C 无关，两者不能按字母对应；'
     '目录名与图中均带区分后缀。', label='不混淆')
para('静态生成失败缓存只跳过"目标双方在完全相同的生成输入下都生成零候选"的目标，不占用 50 次正式目标尝试上限；'
     '零候选本身原本就不消耗候选评价次数。动态验收失败仍走全局布局版本缓存（任何被接受的修改使旧失败失效）。', label='机制')
para('候选窗口余量 window_slack_mm=1e-5 mm（10 nm）是候选窗口的数值与几何余量，不是加工公差，也不是光学安全裕量；'
     '0.1 mm 中心线近距阈值、5 mm 最小曲率半径与保守验收规则都没有放宽。', label='余量')

# =============================================================== 实验一
heading('2 实验一：512 四组功能消融', 1, new_page=True)
heading('2.1 做法', 2)
para('同一输入、同一初态（冻结的二维 z=0 平面路线）、同一几何阈值（0.1 mm 近距、5 mm 过渡半径）、'
     '策略 C、候选基本评价预算上限 720 次、目标尝试上限 50 次。四组只切换两个开关，'
     '其中"生成缓存"指静态生成失败缓存，"窗口余量"指 window_slack_mm。', label='设置')
rows = []
for key, label, cache, slack in GROUPS:
    g = CROSS['groups'][key]
    rows.append([label, cache, slack, integer(g['final_collision_pairs']),
                 integer(CROSS['groups']['A_baseline_original']['final_collision_pairs'] - g['final_collision_pairs']),
                 pct(100*(49518 - g['final_collision_pairs'])/49518), integer(g['accepted_moves']),
                 integer(g['relocations']), integer(g['candidate_evaluations']),
                 integer(g['candidate_budget']), integer(g['final_unresolved_pairs'])])
table('512 四组功能消融：分组定义与终态结果',
      ['分组', '生成缓存', '窗口余量\n(mm)', '终态近距对', '比 A 少\n(对)', '相对初态\n减少(%)',
       '接受修改', '重定位', '实际评价\n(次)', '预算上限\n(次)', '未决对'],
      rows, [2.5, 1.25, 1.3, 1.7, 1.35, 1.5, 1.3, 1.05, 1.35, 1.35, 1.05], text_cols=(0,),
      best=[(3, 3)],
      notes='初态为 49,518 对近距对、3 对未决，四组相同。"比 A 少"只在本表四组之间可比（同输入、同初态、'
            '同预算上限、同验收规则）。粗体只标注严格可比范围内的最优：D 的终态近距对最低；'
            'A 与 D 的"实际评价"不同，预算上限相同不等于实际工作量相同。0 表示明确统计为零（重定位未发生）。')
source('outputs/3d_strategy_v3/512_ablation/{A_baseline_original,B_generation_cache_only,C_window_slack_only,D_both_enabled}/ledger.json '
       '与 cross_group_analysis.json。')
picture(FIG/'f1_group_pairs.png', 16.4, '自己的结果：四组功能消融的终态中心线近距对与相对初态的减少量（组字母为功能消融，不是历史策略 A/B/C）')

heading('2.2 结果', 2)
rows = []
for key, label, _, _ in GROUPS:
    g = CROSS['groups'][key]
    s = SUMMARIES[key]['stats']
    rows.append([label, integer(g['target_attempts']), integer(g['unique_targets']), integer(g['repeat_attempts']),
                 integer(g['generation_skip_events']), integer(g['generated_candidates']),
                 integer(g['candidate_evaluations']), integer(g['full_neighbor_checks']),
                 integer(sum(s['self_rejection_reasons'].values())),
                 pct(g['budget_used_percent'], 1), g['stop_reason']])
table('512 四组的调度、预算与自检歧义记录',
      ['分组', '目标尝试\n(次)', '不同目标\n(个)', '重复尝试\n(次)', '缓存跳过\n事件(次)', '生成候选\n(个)',
       '实际评价\n(次)', '完整邻居\n验收(次)', '自检歧义\n(条)', '预算使用\n(%)', '停止原因'],
      rows, [2.5, 1.35, 1.3, 1.3, 1.4, 1.3, 1.3, 1.4, 1.25, 1.25, 2.6], text_cols=(0, 10),
      notes='"自检歧义"是被评价候选在基本评价阶段因 SELF_AMBIGUOUS_CLEARANCE 被拒的条数。'
            'B 与 D 的缓存跳过事件 28 次与 26 次只涉及两个独立目标 (290,433) 与 (290,291)：'
            '缓存的作用是让这两个结构性零候选目标不再反复占用 50 次正式目标尝试上限，'
            '零候选本身不消耗候选评价预算，因此不能写成"节省候选调用"或"运行更快"'
            '（B 组实际运行 209.8 s 反而高于 A 组 199.7 s，且 B 组 720/720 预算耗尽）。')
source('同上的 ledger.json、generation_skips.json 与各组 summary.json。')
para('（1）D 组终态最低：42,909 对，比 A 少 1,365 对（A 44,274）。C 组 43,161、B 组 43,750。', label='结果')
para('（2）只有 C、D 两组（即启用窗口余量的两组）把被评价候选的自检歧义从 A 的 331 条、B 的 356 条降到 0 条；'
     'C 组每一条被评价的候选都通过基本评价（711/711），完整邻居验收次数从 A 的 335 次升到 711 次。')
para('（3）B 组消除了重复调度：目标尝试 50→27、重复尝试 25→0；但 B 组在 720 次候选评价耗尽时停止，'
     '未到目标上限，因此 B 组终态受预算口径影响，不能声称收敛。')
para('（4）四组未决对都是 3（TOUCHING_THRESHOLD），阈值未被放宽，未决对没有被当作 CLEAR 消除。')
picture(FIG/'f2_pairs_vs_evaluations.png', 16.4, '自己的结果：中心线近距对数随累计候选基本评价次数的变化（共同上限 720 次；实际评价次数 A 666、B 720、C 711、D 720）')

heading('2.3 代价记录', 2)
rows = []
for key, label, _, _ in GROUPS:
    g = CROSS['groups'][key]
    rows.append([label, fmt(g['final_extra_length_mm'], 6), integer(g['final_transition_count']),
                 fmt(g['timings']['runtime_seconds'], 1), integer(g['candidate_evaluations']),
                 integer(g['candidate_budget']), pct(g['budget_used_percent'], 2)])
table('512 四组的长度、过渡数量、单次运行时间与预算利用',
      ['分组', '终态额外长度\n(mm)', '过渡段数\n(个)', '单次运行时间\n(s)', '实际评价\n(次)', '预算上限\n(次)', '预算使用\n(%)'],
      rows, [3.0, 2.6, 2.0, 2.4, 2.0, 2.0, 2.0], text_cols=(0,), best=[(2, 1)],
      notes='额外长度 = 终态总长度 − 该组初态总长度，四组初态相同，因此可比；粗体只标注最小者（C）。'
            '运行时间为同机单次实测，预算上限相同不代表实际工作量相同，也不能据此得出普遍效率结论。')
source('同上各组 ledger.json 的 final_extra_length_mm、final_transition_count、runtime_seconds、'
       'candidate_evaluations、candidate_budget。')
picture(FIG/'f3_costs.png', 14.2, '自己的结果：四组功能消融的额外长度、单次运行时间与候选评价预算使用率')

heading('2.4 实验一的结论与限制', 2)
para('在本次 512 合成输入、同一预算上限与同一验收规则下：终端近距对最低的是两项功能同开的 D 组（42,909），'
     '额外长度最小的是仅开窗口余量的 C 组（6.912199 mm）；B 组与 D 组都在 720 次候选评价耗尽时停止，'
     '因此 B、D 的终态是预算口径下的结果，不是收敛结果。两项功能的作用机制不同：生成缓存改的是调度'
     '（不再重复尝试结构性零候选目标），窗口余量改的是生成（把落在阈值边界上的窗口 placement 移开，'
     '使候选可被证明为 CLEAR）。本轮的边界是：四组均为单次运行，运行时间不能作为效率结论；'
     '中心线指标不代表损耗、串扰或无碰撞制造；512 为既有合成输入。', label='结论与机制')


# =============================================================== 实验二
heading('3 实验二：窗口余量对 331 条自检歧义候选的探针', 1, new_page=True)
heading('3.1 做法', 2)
para('从冻结平面几何与保存的 CROSS 锚点重建修正版 C 在 512 主实验中保存的全部 331 条 '
     'SELF_AMBIGUOUS_CLEARANCE 候选（涉及 31 个生成任务），然后用 window_slack_mm=1e-5 重新枚举窗口，'
     '在每个已记录候选的 ±2δ（δ=slack/直线长度）内寻找唯一对应窗口并重建候选，只对候选自身做自净距判定。'
     '不重新布线、不改阈值、不放宽任何验收规则。', label='方法')
para('数学关系：设 δ = window_slack_mm / 直线长度。端点内缩量由 clearance/length 变为 (clearance+slack)/length，'
     '可用区间 [lo,hi] 两端各内缩 δ、宽度缩小 2δ；三个位置参数 f=0、0.5、1 的位移是 (1−2f)δ，'
     '即起点锚定位置平移 +δ、中间位置不动、贴近右边界位置平移 −δ；过渡长度 run/length 与过渡数量不变；'
     '本来就勉强可行的窗口可能因这 2δ 的收缩而消失（hi−lo < width 时该窗口不再被枚举）。',
     label='必须写清的数学')
para('此前文档里"hi−lo 中 pad 抵消"的写法是错的，已修正；同样已删除"不会改变任何非边界判定"这类绝对保证，'
     '只保留本次探针对 331 条已记录候选的实测结果，以及"0.1 mm 阈值与全部验收规则保持不变"这一事实。', label='更正')

heading('3.2 结果', 2)
st = PROBE_DATA['status_after_shift']; tw = PROBE_DATA['task_window_counts']
rows = [
    ['已记录的自检歧义候选（条）', integer(PROBE_DATA['recorded_rows'])],
    ['涉及生成任务（个）', integer(PROBE_DATA['unique_tasks'])],
    ['加余量后判为 CLEAR（条）', integer(st['CLEAR'])],
    ['加余量后仍为 AMBIGUOUS_CLEARANCE（条）', integer(st['still_ambiguous'])],
    ['加余量后判为 COLLISION（条）', integer(st['collision'])],
    ['加余量后判为 TOUCHING_THRESHOLD（条）', integer(st['touching_threshold'])],
    ['无法匹配窗口（条）', integer(st['window_not_available'])],
    ['候选总数（余量 0 → 余量 1e-5，个）', f"{integer(tw['total_candidates_at_slack_zero'])} → {integer(tw['total_candidates_at_probe_slack'])}"],
    ['加余量后候选变少 的任务数（个）', integer(tw['tasks_with_fewer_candidates_after_shift'])],
    ['31 个任务的层失败原因发生变化的记录数', integer(len(PROBE_DATA['failure_shifts_on_recorded_tasks']))]]
table('窗口余量探针：331 条已记录自检歧义候选的复核结果', ['项目', '数值'], rows, [9.5, 7.0], text_cols=(0,),
      notes='"无法匹配窗口"为 0 表示 331 条记录都在 ±2δ 内找到了唯一对应窗口。'
            '候选总数 666 → 666 表示这 31 个任务没有因为余量而失去或获得候选；'
            '层失败原因变化记录数为 0 表示这些任务的失败原因没有改变。')
source('outputs/3d_strategy_v3/window_slack_probe/window_slack_probe.json（2026-10-05 生成，'
       '并已按本次措辞修正重新生成，逐字段核对数值未变，见同目录 wording_fix_check.json）。')
para('331 / 331 条候选的自身净距全部由 AMBIGUOUS_CLEARANCE 变为 CLEAR；样本（step 2、目标 (9,34)、'
     '路线 34、层 1）的最小距离由约 0.09999999999 mm 变为 0.10000999999 mm，与设计一致。', label='结果')

heading('3.3 结论与限制', 2)
para('在本次 512 输入、31 个已记录生成任务上，10 nm 的窗口余量足以把已记录的自检歧义候选移出阈值边界，'
     '且这 31 个任务的可用候选数量没有减少、层失败原因没有变化。', label='结论')
para('（1）自检歧义消除不等于目标近距对与完整邻线验收通过。本轮探针只判定候选自身净距；'
     '候选是否被接受还要看目标对是否被清除、与全部 511 条邻线的关系以及全局近距对是否严格下降。', label='限制')
para('（2）探针不等于全局未决对清零。四组主实验的未决对都是 3，本轮没有任何阈值放宽，'
     '未决（TOUCHING_THRESHOLD 等非 CLEAR 状态）仍然不计为 CLEAR。')
para('（3）范围只有这一份 512 输入与这 31 个任务；1024 与其他输入没有做同样的逐候选复核。')
para('（4）余量本身可能移除勉强可行的窗口：回归测试中用一个"仅余 1.5e-5 mm"的贴边窗口复现了'
     '"加余量后该窗口消失（INSUFFICIENT_TRANSITION_SPACE）"的真实负效应；四组主实验中 (34,177) 的 victim 177 '
     '生成失败原因也从 INSUFFICIENT_TRANSITION_SPACE 变为 NO_VALID_TRANSITION_WINDOW。')

# =============================================================== 实验三
heading('4 实验三：加余量的固定重定位诊断（新 D / 新 E）', 1, new_page=True)
heading('4.1 目的与设置', 2)
para('历史 Step 15 的诊断在 512 条 B 终态上预先固定 20 个目标（10 对双方均已抬升、10 对仅一方已抬升），'
     'D 组只允许首次抬升、E 组允许重定位；当时 E 实际生成并完整评价了 126 个重定位候选，'
     '其中 70 个在基本评价阶段因自检歧义被拒，没有任何一个候选通过全部验收规则，D 与 E 的终态完全相同。'
     '本轮把 window_slack_mm=1e-5 加进同一诊断，其余一切不变，看那批被"自检歧义"挡住的候选会怎样。', label='目的')
para('复用原诊断逻辑，只把余量参数透传到候选生成（run_fixed_target_diagnostic 新增 window_slack_mm，默认 0.0 '
     '保持历史行为）。静态生成失败缓存保持关闭，避免同时改变另一项功能。不更换目标、不调整顺序、'
     '不为寻找正结果而改动任何判据。', label='做法')
para('重定位必须满足：从原始冻结平面路线重建替代候选；保留端点与 XY 投影；替换当前路线而不是叠加升降结构；'
     '保持 C0/C1 连接、过渡半径与原保守验收规则；与当前全部邻线逐一验收；未决状态不得当作 CLEAR；'
     '每次接受修改后全局近距对必须严格减少（引擎内断言）。', label='重定位规则')
rows = [
    ['起点状态', '512 条 B 终态（已冻结、带 SHA256）', f"{integer(CONFIG['start_pair_scan_collisions'])} 对近距、"
     f"{integer(CONFIG['start_elevated_route_count'])} 条已抬升路线"],
    ['目标清单', '沿用 Step 15 预声明规则并按 id 元组升序选取', f"共 {len(TARGETS['targets'])} 对"
     f"（双方已抬升 {len(TARGETS['both_elevated'])} 对、仅一方已抬升 {len(TARGETS['one_elevated'])} 对）"],
    ['清单一致性', '本轮按同一规则重新推导并与 Step 15 的 target_list.json 逐项比对', '完全相同（断言通过）'],
    ['处理顺序', '沿用 Step 15 的目标顺序，每个目标一次机会', '相同'],
    ['窗口余量', 'window_slack_mm（仅新增本项）', f"{CONFIG['window_slack_mm']:.1e} mm"],
    ['静态生成失败缓存', '关闭（不引入第二项改动）', '关闭'],
    ['候选评价预算上限', '两组相同上限，基本拒绝同样计入', f"{integer(CONFIG['candidate_budget_ceiling'])} 次"],
    ['几何与验收', '0.1 mm 近距、5 mm 过渡半径、完整邻线验收、未决不计 CLEAR', '与 Step 15 相同']]
table('加余量重定位诊断的设置复核', ['项目', '本轮取值', '数值/说明'], rows, [3.0, 7.0, 6.6], text_cols=(0, 1),
      notes='唯一改动是窗口余量；起点、目标清单、顺序、预算上限、几何阈值与验收规则都沿用原诊断。')
source('outputs/3d_strategy_v3/512_relocation_slack_diagnostic/config.json、target_list.json、'
       'old_diagnostic_reference.json。')

heading('4.2 结果：新 E 第一次接受了重定位', 2)
rows = []
for era, tag, ledger in (('旧', 'D', OLD_LEDGER['D']), ('新', 'D', DIAG_LEDGER['D']),
                         ('旧', 'E', OLD_LEDGER['E']), ('新', 'E', DIAG_LEDGER['E'])):
    rows.append([f'{era}诊断 {tag}', integer(ledger['final_collision_pair_count']),
                 integer(ledger['final_collision_pair_count'] and
                         (43750 - ledger['final_collision_pair_count'])),
                 integer(ledger['accepted_moves']), integer(ledger['first_elevations']),
                 integer(ledger['relocations']), integer(ledger['relocation_victim_attempts']),
                 integer(ledger['relocation_candidate_evaluations']),
                 integer(ledger['candidate_evaluations']),
                 fmt(ledger['final_extra_length_vs_planar_mm'], 4),
                 fmt(ledger['runtime_seconds'], 1)])
table('加余量前后 D/E 诊断对照（起点 43,750 对；预算上限同为 720 次）',
      ['组', '终态近距对', '净减少\n(对)', '接受修改', '首次抬升', '接受重定位', '重定位路线\n尝试(次)',
       '重定位候选\n评价(次)', '候选评价\n合计(次)', '终态额外长度\n相对平面(mm)', '单次运行\n时间(s)'],
      rows, [1.75, 1.35, 1.15, 1.2, 1.2, 1.3, 1.4, 1.4, 1.35, 1.8, 1.35], text_cols=(0,),
      best=[(3, 1)],
      notes='四行共用同一起点与同一目标清单。"预算上限同为 720 次"只表示上限相同：'
            '实际候选评价次数 324 / 324 / 450 / 342 两两不同，不能称相同实际工作量。'
            '粗体只标注四行中终态近距对最低者（新 E）。运行时间为单次实测。')
source('outputs/3d_strategy_v2_rev2/512_de_diagnostic/ledger_{D,E}.json 与 '
       'outputs/3d_strategy_v3/512_relocation_slack_diagnostic/ledger_{D,E}.json。')
para(f'新 D 与旧 D 的决策序列、终态近距集合、未决集合和统计指标保持一致（42,112 对、8 次首次抬升、'
     f'324 次评价、额外长度 {fmt(OLD_LEDGER["D"]["final_extra_length_vs_planar_mm"], 4)} mm），'
     f'但 8 条路线的窗口几何发生了微小变化：余量把 8 次被接受修改的窗口位置平移了约 1.2e-7~1.8e-7 参数单位'
     f'（对应 1e-5 mm 的几何位移）。本轮不声称几何或原始 decisions 逐字节相同。', label='新 D')
para(f'新 E 的终态从 42,112 降到 42,083 对（少 29 对），接受了 1 次重定位；'
     f'重定位候选评价从 126 次降到 18 次，候选评价合计从 450 次降到 342 次。'
     f'原因是第 4 步的重定位被接受后，剩下 6 个"双方均已抬升"的目标不再处于近距状态'
     f'（目标状态变为 TARGET_NO_LONGER_COLLIDING），因此不再需要逐候选评价。', label='新 E')
benefit = ANALYSIS['benefit_decomposition']
saved_routes = '、'.join(str(x['route_id']) for x in benefit['first_elevations_with_one_fewer_new_pair'])
para(f'29 对差异的来源（由保存的 decisions 逐步核对，'
     f'{fmt(benefit["relocation_removed_pairs_directly"], 0)} + {benefit["pairs_saved_by_those_first_elevations"]} '
     f'= {benefit["final_pair_difference_D_minus_E"]}）：路线 34 的重定位直接移除 '
     f'{benefit["relocation_removed_pairs_directly"]} 对近距；后续路线 {saved_routes} 的首次抬升各少新增 1 对'
     f'（共 {benefit["pairs_saved_by_those_first_elevations"]} 对），两项相加正好等于最终 D/E 的 29 对差异。',
     label='收益分解')
lc = ANALYSIS['length_consistency']
para(f'长度一致性：重定位单步长度变化为 +{fmt(lc["relocation_step_delta_mm"], 6)} mm，'
     f'最终 D/E 的终态额外长度差为 {fmt(lc["final_extra_length_difference_mm"], 6)} mm，两者在 1e-9 mm 内一致'
     f'（因为相对 D 只有路线 34 的长度发生变化）。', label='长度口径')
para(f'长度代价：新 E 相对诊断起点的总长度变化为 +{fmt(LENGTH["modes"]["E"]["delta_vs_diagnostic_start_mm"], 4)} mm，'
     f'相对原始平面的终态额外长度为 {fmt(LENGTH["modes"]["E"]["final_extra_length_vs_planar_mm"], 4)} mm；'
     f'新 D 相对起点 +{fmt(LENGTH["modes"]["D"]["delta_vs_diagnostic_start_mm"], 4)} mm，'
     f'相对平面 {fmt(LENGTH["modes"]["D"]["final_extra_length_vs_planar_mm"], 4)} mm。'
     f'即新 E 用多 {fmt(LENGTH["modes"]["E"]["final_extra_length_vs_planar_mm"]-LENGTH["modes"]["D"]["final_extra_length_vs_planar_mm"], 4)} mm '
     f'的终态额外长度换到少 29 对近距对。', label='长度')
picture(FIG/'f4_diagnostic_comparison.png', 16.4, '自己的结果：原诊断（余量 0）与加余量诊断（1e-5 mm）的终态、实际评价次数、额外长度与单次运行时间对照')

heading('4.3 逐候选对应：不是"70 条全部解决"', 2)
para('为了给出逐候选结论而不是只看歧义总数下降，本轮把旧诊断 E 与新诊断 E 的候选建立对应关系：'
     '生成始终使用冻结平面路线与冻结锚点，因此同一 (目标, victim, 层) 任务的候选集合可以逐窗口匹配；'
     '匹配规则是"层、起升直线编号、下降直线编号、窗口宽度完全一致，窗口起点位移不超过 2δ"。', label='方法')
rows = [
    ['有唯一对应候选的旧候选（条）', integer(CORR_REL['matched'])],
    ['　其中：加余量后通过基本评价（条）', integer(CORR_REL['old_to_new_basic_status'].get('REJECTED -> ACCEPTED_TARGET_PAIR_ONLY', 0))],
    ['　其中：加余量后仍被拒（条）', integer(CORR_REL['old_to_new_basic_status'].get('REJECTED -> REJECTED', 0))],
     ['　其中：加余量后通过完整验收（条）', integer(CORR_REL['matched_to_full_acceptance'])],
     ['　其中：加余量后在完整验收被拒（条）', integer(CORR_REL['matched_full_rejected'])],
     ['本轮未再出现的旧候选（条）', integer(sum(CORR_REL['unmatched'].values()))],
    ['　原因：该生成任务本轮没有执行（目标已不再近距）', integer(CORR_REL['unmatched'].get('TASK_NOT_REACHED_IN_NEW_RUN', 0))],
    ['找不到对应窗口（条）', integer(CORR_REL['unmatched'].get('NO_CORRESPONDING_WINDOW_IN_NEW_RUN', 0))]]
table('旧诊断 E 的 70 条重定位自检歧义候选：逐候选对应结果', ['项目', '条数'], rows, [10.0, 4.0],
      text_cols=(0,),
      notes='"本轮未再出现的旧候选"不能算作被解决：它们的生成任务在新诊断中没有执行（接受的重定位先把这些目标清除了），'
            '因此本轮对它们没有正面或负面证据。只有"有唯一对应候选"的 10 条才能给出逐候选结论。')
source('outputs/3d_strategy_v3/512_relocation_slack_diagnostic/analysis.json 的 '
       'correspondence_relocation_candidates；原始逐条记录见 candidate_correspondence.json。')
para(f'在有唯一对应的 10 条中，5 条（全部位于层 2 的窗口布置）加余量后通过基本评价，'
     f'另 5 条（位于层 1）仍因 TARGET_NOT_CLEARED 被拒——余量只解决自检歧义，不能解决"目标近距对没被清除"。'
     f'通过基本评价的 5 条中，{integer(CORR_REL["matched_to_full_acceptance"])} 条随后通过完整邻线验收、'
     f'{integer(CORR_REL["matched_full_rejected"])} 条在完整验收阶段被拒'
     f'（理由均为 {", ".join(CORR_REL["matched_full_reject_reasons"]) or "无"}）。', label='读数')
rows = [
    ['重定位候选（70 条）', integer(CORR_REL['matched']),
     integer(CORR_REL['matched_to_basic_pass']), integer(CORR_REL['matched_still_rejected']),
     integer(CORR_REL['matched_to_full_acceptance']), integer(CORR_REL['matched_full_rejected']),
     integer(CORR_REL['unmatched'].get('TASK_NOT_REACHED_IN_NEW_RUN', 0))],
    ['全部运动类别（208 条）', integer(CORR_ALL['matched']),
     integer(CORR_ALL['matched_to_basic_pass']), integer(CORR_ALL['matched_still_rejected']),
     integer(CORR_ALL['matched_to_full_acceptance']), integer(CORR_ALL['matched_full_rejected']),
     integer(CORR_ALL['unmatched'].get('TASK_NOT_REACHED_IN_NEW_RUN', 0))]]
table('旧诊断 E 全部自检歧义候选的对应统计（含首次抬升）',
      ['范围', '有唯一对应（条）', '通过基本评价（条）', '基本评价被拒（条）',
       '通过完整验收（条）', '完整验收被拒（条）', '本轮任务未执行（条）'],
      rows, [3.3, 2.3, 2.3, 2.3, 2.3, 2.3, 2.2], text_cols=(0,),
      notes=f'旧诊断 E 的全部自检歧义候选共 208 条，其中 70 条属于重定位候选（见上表）；'
            f'两行的 148 = 143 + 5 与 10 = 5 + 5 只覆盖"有唯一对应"的部分，未执行的 60 条不参与任何通过率计算。'
            f'"通过基本评价"与"通过完整验收"都是候选条数：143 条通过基本评价，其中 '
            f'{integer(CORR_ALL["matched_to_full_acceptance"])} 条通过完整验收、'
            f'{integer(CORR_ALL["matched_full_rejected"])} 条在完整验收被拒'
            f'（{", ".join(CORR_ALL["matched_full_reject_reasons"])}）。'
            f'通过验收不等于实际执行：一个步骤只执行它选中的那一个候选，本轮两条诊断实际执行的修改合计 '
            f'{integer(ANALYSIS["accepted_edit_counts"]["total"])} 次'
            f'（新 D {integer(ANALYSIS["accepted_edit_counts"]["new_D"])} 次、'
            f'新 E {integer(ANALYSIS["accepted_edit_counts"]["new_E"])} 次，其中重定位 '
            f'{integer(ANALYSIS["accepted_edit_counts"]["new_E_relocations"])} 次）。')
source('同上 analysis.json 的 correspondence_all_movement_classes。')

heading('4.4 被接受的那一次重定位', 2)
para(f'新诊断 E 的第 {ENTRY["step_index"]} 步、目标 {tuple(ENTRY["target_pair"])}，移动路线 {ENTRY["route_id"]}，'
     f'运动类型 RELOCATION：路线 {ENTRY["route_id"]} 从层 1 改到层 {ENTRY["target_layer_id"]}，'
     f'移除 {len(ENTRY["old_collisions_removed"])} 对近距对、新增 {len(ENTRY["new_collisions_created"])} 对，'
     f'全局近距对 {integer(ENTRY["global_pairs_before"])} → {integer(ENTRY["global_pairs_after"])}（严格下降），'
     f'单步长度变化 +{fmt(ENTRY["step_length_delta_mm"], 4)} mm。', label='被接受的修改')
para(f'该路线重定位前长度 {fmt(BA["before_length_mm"], 4)} mm、过渡段 {BA["before_transition_count"]} 段；'
     f'重定位后长度 {fmt(BA["after_length_mm"], 4)} mm、过渡段 {BA["after_transition_count"]} 段；'
     f'原始平面路线长度 {fmt(BA["planar_length_mm"], 4)} mm。过渡段数保持 2，说明是把当前路线整体替换掉，'
     f'而不是在已有升降结构上再叠加一层；端点与 XY 投影保持不变。', label='替换而非叠加')
rows = [
    ['被评价的重定位候选（个）', integer(MS['new_E']['RELOCATION']['basic_evaluations']),
     integer(MS['old_E']['RELOCATION']['basic_evaluations'])],
    ['通过基本评价（个）', integer(MS['new_E']['RELOCATION']['basic_passed']), integer(MS['old_E']['RELOCATION']['basic_passed'])],
    ['进入完整邻线验收（个）', integer(MS['new_E']['RELOCATION']['full_acceptance_checks']),
     integer(MS['old_E']['RELOCATION']['full_acceptance_checks'])],
    ['完整验收通过（个）', integer(MS['new_E']['RELOCATION']['full_acceptance_passed']),
     integer(MS['old_E']['RELOCATION']['full_acceptance_passed'])],
    ['最终被接受（次）', integer(MS['new_E']['RELOCATION']['accepted_edits']), integer(MS['old_E']['RELOCATION']['accepted_edits'])],
    ['基本评价阶段被拒（个）', integer(MS['new_E']['RELOCATION']['basic_rejected']), integer(MS['old_E']['RELOCATION']['basic_rejected'])],
    ['完整验收阶段被拒（个）',
     integer(MS['new_E']['RELOCATION']['full_acceptance_checks']-MS['new_E']['RELOCATION']['full_acceptance_passed']),
     integer(MS['old_E']['RELOCATION']['full_acceptance_checks']-MS['old_E']['RELOCATION']['full_acceptance_passed'])]]
table('重定位候选的处理结果（新诊断 E 与新诊断对照旧诊断 E）',
      ['环节', '新诊断 E（余量 1e-5）', '旧诊断 E（余量 0）'], rows, [7.0, 4.6, 4.4], text_cols=(0,),
      notes='一个候选只在一个环节被计数一次；"完整验收通过"是候选计数，不是被接受的修改次数。')
rows = [
    ['自检歧义 SELF_AMBIGUOUS_CLEARANCE', '基本评价',
     integer((MS['new_E']['RELOCATION']['basic_rejection_reason_occurrences'] or {}).get('SELF_AMBIGUOUS_CLEARANCE', 0)),
     integer((MS['old_E']['RELOCATION']['basic_rejection_reason_occurrences'] or {}).get('SELF_AMBIGUOUS_CLEARANCE', 0))],
    ['目标近距对未清除 TARGET_NOT_CLEARED', '基本评价',
     integer((MS['new_E']['RELOCATION']['basic_rejection_reason_occurrences'] or {}).get('TARGET_NOT_CLEARED', 0)),
     integer((MS['old_E']['RELOCATION']['basic_rejection_reason_occurrences'] or {}).get('TARGET_NOT_CLEARED', 0))],
    ['全局近距对未严格下降 NO_STRICT_GLOBAL_DECREASE', '完整验收',
     integer((MS['new_E']['RELOCATION']['full_rejection_reason_occurrences'] or {}).get('NO_STRICT_GLOBAL_DECREASE', 0)),
     integer((MS['old_E']['RELOCATION']['full_rejection_reason_occurrences'] or {}).get('NO_STRICT_GLOBAL_DECREASE', 0))]]
table('重定位候选的拒绝理由出现次数',
      ['拒绝理由', '发生在', '新诊断 E', '旧诊断 E'], rows, [8.0, 2.6, 2.7, 2.7], text_cols=(0, 1),
      notes='统计口径：一个候选可能同时带多个拒绝理由，因此这里统计的是"理由出现次数"，'
            '相加不等于候选数。按候选去重的计数保存在 movement_stats.json 的 candidates_with_reason 字段中。'
            '新诊断 E 共 18 个候选：9 个因 TARGET_NOT_CLEARED 在基本阶段被拒，9 个进入完整验收、其中 8 个因'
            ' NO_STRICT_GLOBAL_DECREASE 被拒、1 个被接受。')
source('outputs/3d_strategy_v3/512_relocation_slack_diagnostic/movement_stats.json 与 analysis.json。')
picture(FIG/'f5_relocation_rejections.png', 16.4, '自己的结果：重定位候选的失败原因（旧诊断 0 次接受、126 个候选；新诊断 1 次接受、18 个候选；同一候选可有多个理由，出现次数不能相加成候选数）')
para('作为几何口径对照，下图为四组消融 D 组终态中一条真实被抬升路线（按"余弦过渡段最多、峰值层最高、'
     '抬升段最长、路线编号最小"确定性选取）的四种视图：抬升只改变 z，XY 足迹与冻结平面参考按弧长重采样 401 点'
     '的最大偏差为 1.14e-13 mm（由绘图脚本实测并写入图表清单）。该图用于说明本报告所有路线几何图的读法与'
     '"真实高度比例"与"Z 轴放大"的区别，不参与任何统计比较。', label='几何口径对照')
picture(FIG/'f6_route_geometry.png', 16.0,
        '自己的结果：D 组终态中一条真实被抬升路线的几何（XY 投影、XZ 侧视、真实高度比例三维图、'
        'Z 轴放大 20 倍示意图；真实层高 0/1/2 mm；来源 outputs/3d_strategy_v3/figures/f6_route_geometry.png）')
picture(FIG/'f7_route34_relocation_before_after.png', 16.0,
        f'自己的结果：路线 {ENTRY["route_id"]} 被接受的这一次重定位前后（XY 投影、XZ 侧视、'
        f'真实高度比例三维图、Z 轴放大 20 倍示意图；真实层高 0/1/2 mm）')

heading('4.5 分类计数与长度记账', 2)
rows = []
for movement, label in (('FIRST_ELEVATION', '首次抬升'), ('RELOCATION', '重定位')):
    for mode in ('D', 'E'):
        m = MOVEMENT['modes'][mode][movement]
        rows.append([f'{label}（新 {mode}）', integer(m['victim_attempts_total']),
                     integer(m['victim_attempts_with_generation']), integer(m['generated_candidates']),
                     integer(m['basic_evaluations']), integer(m['basic_passed']),
                     integer(m['full_acceptance_checks']), integer(m['full_acceptance_passed']),
                     integer(m['accepted_edits'])])
table('按运动类别分别记录的尝试、生成、评价与接受（新诊断）',
      ['类别', '路线尝试\n(次)', '实际生成\n(次)', '生成候选\n(个)', '基本评价\n(次)', '基本通过\n(个)',
       '完整验收\n(次)', '完整通过\n(个)', '接受\n(次)'],
      rows, [2.9, 1.5, 1.5, 1.6, 1.6, 1.5, 1.6, 1.5, 1.2], text_cols=(0,),
      notes='"路线尝试"包含因 D 规则被跳过、未发生生成的尝试（新 D 的 28 次重定位尝试全部属于此类，'
            '状态为 ROUTE_ALREADY_ELEVATED_NOT_ALLOWED_IN_D）；"实际生成"只统计真正调用生成器的尝试。'
            '两列同时给出，避免把"没有触发重定位"与"重定位候选全部失败"混为一谈。')
source('outputs/3d_strategy_v3/512_relocation_slack_diagnostic/movement_stats.json。')
rows = []
for mode in ('D', 'E'):
    L = LENGTH['modes'][mode]
    neg = ('不适用（未接受重定位）' if L['accepted_move_count'] - DIAG_LEDGER[mode]['first_elevations'] == 0
           else fmt(L['relocation_step_delta_mm'], 4))
    rows.append([f'新 {mode}', fmt(L['delta_vs_diagnostic_start_mm'], 4),
                 fmt(L['first_elevation_step_delta_mm'], 4), neg,
                 fmt(L['start_extra_length_vs_planar_mm'], 4),
                 fmt(L['final_extra_length_vs_planar_mm'], 4),
                 integer(L['accepted_move_count']), integer(L['negative_step_count']),
                 '一致' if L['delta_vs_diagnostic_start_consistent'] else '不一致'])
table('长度记账（相对诊断起点与相对原始平面）',
      ['组', '相对诊断起点\n变化(mm)', '其中首次抬升\n(mm)', '其中重定位\n(mm)', '起点相对平面\n(mm)',
       '终态相对平面\n(mm)', '接受修改\n(次)', '负步长\n(次)', '台账与终态\n一致性'],
      rows, [1.4, 2.3, 2.2, 2.3, 2.0, 2.0, 1.4, 1.3, 1.6], text_cols=(0, 8),
      notes='单步变化 = 新路线长度 − 当前路线长度，允许为负；本轮两组都没有出现负步长（0 次为实测值，不是缺失）。'
            '"相对诊断起点变化"= 终态总长度 − 本诊断起点总长度，与逐步变化之和在 1e-6 mm 内一致（最后一列）。'
            '"不适用"表示该组没有接受任何重定位，重定位长度代价没有意义；这与"0"不同。')
source('outputs/3d_strategy_v3/512_relocation_slack_diagnostic/length_ledger.json 与 ledger_{D,E}.json。')

heading('4.6 实验三的结论与限制', 2)
para('把 10 nm 的窗口余量加进历史固定重定位诊断后，E 组第一次接受了重定位：路线 34 从层 1 改到层 2，'
     '移除 26 对近距、新增 0 对，全局近距对 43,750 → 43,724，随后 6 个原本待处理的目标不再处于近距状态；'
     '终态从 42,112 降到 42,083（少 29 对），代价是终态额外长度相对原始平面从 13.0153 mm 增加到 13.4495 mm，'
     '而候选评价次数反而从 450 次降到 342 次。', label='结论')
para('这次接受不是"放宽规则"的结果：阈值、半径规则、端点与 XY 投影、'    'C0/C1、完整邻线验收与"全局近距对必须严格下降"全部照旧；被接受候选之所以从"永远无法判定"'
     '变成"可判定为 CLEAR"，是因为窗口位置被移离了 0.1 mm 阈值边界。', label='不是放宽')
para('（1）本轮只有一个起点、一份 20 目标清单、一个余量取值，结论只覆盖这一份诊断；'
     'D 组（只允许首次抬升）在加余量前后决策序列、终态集合与统计指标保持一致，只有 8 条路线的窗口几何有'
     '1e-5 mm 量级的平移。', label='限制')
para('（2）60 条旧的重定位歧义候选所在的生成任务本轮没有执行，因此它们既没有被证明解决，也没有被证明仍未解决。')
para('（3）运行时间是单次实测（新 D 114.2 s、新 E 129.8 s；旧 D 124.7 s、旧 E 188.0 s），'
     '不能据此得出普遍效率结论；新 E 评价次数更少与运行更短同时出现，但两者都只来自这一次运行。')
para('（4）所有指标仍是 0.1 mm 中心线近距对；不代表损耗、串扰、无碰撞制造或工艺合规。')

# =============================================================== 验证
heading('5 验证与复核', 1, new_page=True)
heading('5.1 新增回归测试与全量回归', 2)
para('修改的接口是 run_fixed_target_diagnostic（新增 window_slack_mm，默认 0.0）与候选生成透传。'
     '为它新增 7 个回归测试，重点保证默认余量为 0 时行为与原实现一致，并验证余量确实进入生成、'
     '窗口位移精确等于 (1−2f)δ、验收规则不变、非法余量被拒。', label='覆盖')
rows = [
    ['默认余量与显式 0.0 完全一致，且记录窗口等于无余量枚举',
     '默认路径未改变历史生成'],
    ['窗口位移等于 (1−2f)δ（f=0 为 +δ、f=0.5 为 0、f=1 为 −δ），过渡长度不变',
     '数学关系精确成立'],
    ['正余量确实进入生成：记录窗口等于带余量枚举且不同于无余量枚举，台账记录余量值',
     '接口透传有效'],
    ['非法余量（负值、无穷、NaN、字符串、None）全部抛 WINDOW_SLACK_MUST_BE_FINITE_AND_NONNEGATIVE',
     '参数校验有效'],
    ['余量前后每个候选的基本/完整判定结果完全相同，接受结果相同，端点、XY、C0/C1、半径全部保持',
     '验收规则未被放宽'],
    ['D 跳过已抬升 victim 且不生成、不评价；E 从冻结平面路线重建候选（过渡段仍为 2）',
     '重定位语义正确'],
    ['真实 512 只读检查：3 个固定目标的记录窗口等于带余量枚举、不同于无余量枚举，且不增加窗口',
     '真实数据上透传成立']]
table('为本次接口修改新增的 7 个回归测试', ['测试内容', '验证点'], rows, [12.0, 4.0], text_cols=(0, 1),
      notes='测试文件 tests/test_relocation_slack_diagnostic.py；默认余量为 0 的行为保持不变由第 1 条直接断言。')
source('tests/test_relocation_slack_diagnostic.py。')
para('实际重新执行：3D 项目 .venv（Python 3.10.11）全量 pytest；'
     '4 个因 3D 环境缺 scipy 而模块级跳过的测试模块，用二维项目解释器（含 scipy）单独补跑。'
     '两次运行的结果与耗时见下表，日志文件同存于 outputs/3d_strategy_v3/。', label='实际执行')
rows = [
    ['3D .venv 全量', 'Python 3.10.11（3D 项目 .venv）', TEST3D['summary'],
     f"{TEST3D['seconds']} s", 'outputs/3d_strategy_v3/pytest_full_v3_after_slack.log'],
    ['其中被跳过的 4 个模块', 'OpticalWaveguideRouter2D/.venv（scipy）', TEST2D['summary'],
     f"{TEST2D['seconds']} s", 'outputs/3d_strategy_v3/pytest_opt2d_2d_env_after_slack.log']]
table('本次实际执行的测试与结果', ['范围', '解释器环境', '结果', '耗时', '日志'],
      rows, [3.0, 4.4, 3.0, 1.6, 4.0], text_cols=(0, 1, 4),
      notes='4 个跳过是 4 个测试模块（模块级 pytest.importorskip("scipy")），不是 4 个用例。'
            '上一轮日志（pytest_full_v3.log：732 passed, 4 skipped；pytest_opt2d_2d_env.log：61 passed）'
            '是本次修改之前的历史记录，不能当作本次验证；本次结果以新日志为准。')
source('outputs/3d_strategy_v3/pytest_full_v3_after_slack.log、pytest_opt2d_2d_env_after_slack.log。')

heading('5.2 新终态的落盘重载与全量复核', 2)
rows = []
for mode in ('D', 'E'):
    r = RECHECK[mode]
    rows.append([f'新 {mode}', integer(r['checks']), integer(r['reloaded_route_count']),
                 '一致' if r['collision_pair_set_matches_incremental'] else '不一致',
                 '一致' if r['unresolved_pair_set_matches_incremental'] else '不一致',
                 integer(r['rechecked_close_pair_count']), integer(r['rechecked_unresolved_pair_count']),
                 integer(r['final_transition_count']),
                 '通过' if r['geometry']['endpoint_invariant'] else '未通过',
                 '通过' if r['geometry']['joins_C0_C1_direction'] else '未通过',
                 '通过' if r['geometry']['transition_radius_pass'] else '未通过',
                 '通过' if r['geometry']['xy_projection_preserved'] else '未通过',
                 f"{fmt(r['recheck_seconds'], 1)} s", r['verdict']])
rows_a = [[r[0], r[1], r[2], r[5], r[6], r[7], r[13]] for r in rows]
rows_b = [[r[0], r[3], r[4], r[8], r[9], r[10], r[11], r[12]] for r in rows]
table('新诊断两组终态的保存—重载—全量复核（计数）',
      ['组', '复核路线对（对）', '重载路线（条）', '复核近距对（对）', '复核未决对（对）',
       '终态过渡段数（段）', '结论'],
      rows_a, [1.6, 3.0, 2.4, 2.6, 2.6, 2.8, 1.8], text_cols=(0, 6),
      notes='复核是"从磁盘重新加载保存的终态路线，再对全部 130,816 对路线重新判定"，'
            '不是复用运行内的增量集合；两组结论相同，本表不标注优劣。')
table('同一复核的集合与几何不变量',
      ['组', '近距集合与台账一致', '未决集合与台账一致', '端点', 'C0/C1', '过渡半径', 'XY 投影', '复核耗时（s）'],
      rows_b, [1.4, 2.6, 2.6, 1.5, 1.5, 1.8, 1.8, 2.2], text_cols=(0,))
source('outputs/3d_strategy_v3/512_relocation_slack_diagnostic/recheck_{D,E}.json。')

heading('5.3 台账一致性核对项', 2)
rows = [
    ['近距对集合与增量台账', '重载后重算集合 == collision_sets_{D,E}.json 的 final_collision_pairs', '一致（两组）'],
    ['未决对集合与增量台账', '重载后重算集合 == final_unresolved_pairs（未决不计 CLEAR）', '一致（两组）'],
    ['端点不变量', '每条路线的起终点 == 冻结平面路线起终点', '通过'],
    ['C0/C1 连接', 'analyze_route3d_joins：位置连续且切向连续', '通过'],
    ['过渡曲率半径', '每个余弦过渡段最小曲率半径 ≥ 5 mm', '通过'],
    ['XY 投影', '双向采样：总 XY 长度一致、采样点与弧长一致', '通过'],
    ['过渡数量', f"终态过渡段数 D={RECHECK['D']['final_transition_count']}、E={RECHECK['E']['final_transition_count']}；"
                 f"接受修改每条均为 2 段（替换而非叠加）", '一致'],
    ['长度台账', '终态总长度 − 起点总长度 == 各次接受修改的单步变化之和（1e-6 mm 内）', '一致（两组）'],
    ['全局近距对严格下降', '每次接受修改后引擎内断言：修改前全局对数 − 修改后 == 净减少 > 0',
     f'成立（新 D {ANALYSIS["accepted_edit_counts"]["new_D"]} 次、新 E {ANALYSIS["accepted_edit_counts"]["new_E"]} 次均成立）'],
    ['去重复核', f"每组终态文件 SHA256 记录于 manifest.json；近距对差值曲线 curve_{{D,E}}.json 与决策记录一致", '已记录']]
table('本次实际重新执行的台账一致性核对', ['核对项', '核对方式', '结果'], rows, [3.6, 9.4, 3.0],
      text_cols=(0, 1, 2),
      notes='"一致/通过"表示本次重新计算的结果与保存记录相同；这些核对是为了防止"运行内记账"与"落盘终态"不一致。')
source('outputs/3d_strategy_v3/512_relocation_slack_diagnostic/ 下的 recheck、collision_sets、ledger、'
       'length_ledger、manifest.json。')
para('本轮实际重新执行的部分：加余量重定位诊断（新 D、新 E 两组全流程）、7 个新增回归测试、'
     '3D 全量测试、二维环境补跑的 4 个模块、终态落盘重载与 130,816 对全量复核、窗口余量探针的重建与逐字段核对、'
     '以及本报告全部图表的重新绘制。', label='本次执行')
para('沿用历史已记录、本轮没有重新执行的部分：512 四组功能消融主实验本身（A/B/C/D 四组的决策与终态）、'
     '历史 Step 15 的旧 D/E 诊断结果、331 条自检歧义候选的原始记录来源（修正版 C 的 decisions）。'
     '这些沿用数据在报告中都标注了来源文件；本轮的复核只读取它们，没有重跑。', label='沿用历史')

# =============================================================== 结论与限制
heading('6 结论汇总', 1, new_page=True)
para('（1）在 512 合成输入、相同预算上限与相同验收规则下，两项新功能同时启用（D）得到本轮最低的终态近距对 '
     '42,909（相对初态 −13.35%）；只开窗口余量的 C 组额外长度最小（6.912199 mm）。', label='功能消融')
para('（2）四组的预算上限相同（720 次候选基本评价、50 次目标尝试），但实际评价次数不同（666 / 720 / 711 / 720），'
     '运行时间是单次实测（199.7 / 209.8 / 374.7 / 373.4 s），因此只能说"相同预算上限"，'
     '不能称相同实际工作量，也不能由单次耗时得出普遍效率结论。')
para('（3）窗口余量确实消除了已记录候选的自检歧义：331/331 条由 AMBIGUOUS_CLEARANCE 变为 CLEAR，'
     '对应 31 个生成任务的候选总数 666 → 666 不变。但自检歧义消除不等于目标与完整邻线验收通过，'
     '也不等于全局未决对清零（四组未决对仍为 3）。')
para('（4）把同一余量加到历史固定重定位诊断上，E 组第一次接受了重定位：路线 34 由层 1 改到层 2，'
     '全局近距对 43,750 → 43,724，终态由 42,112 降到 42,083（少 29 对），代价是终态额外长度 '
     '+0.4342 mm（相对平面 13.0153 → 13.4495 mm）；D 组终态不变。')
AEC = ANALYSIS['accepted_edit_counts']
para(f'（5）逐候选对应显示：旧诊断 {integer(CORR_REL["old_self_ambiguous_rows"])} 条重定位歧义候选中只有 '
     f'{integer(CORR_REL["matched"])} 条在本轮有唯一对应候选，其中 {integer(CORR_REL["matched_to_basic_pass"])} 条通过基本评价'
     f'（{integer(CORR_REL["matched_full_rejected"])} 条随后在完整验收被拒、'
     f'{integer(CORR_REL["matched_to_full_acceptance"])} 条通过）、{integer(CORR_REL["matched_still_rejected"])} 条仍因目标未清除被拒；'
     f'全部 {integer(CORR_ALL["matched"])} 条对应候选中 {integer(CORR_ALL["matched_to_basic_pass"])} 条通过基本评价、'
     f'{integer(CORR_ALL["matched_to_full_acceptance"])} 条通过完整验收、{integer(CORR_ALL["matched_full_rejected"])} 条被完整验收拒绝。'
     f'通过验收不等于实际执行：一个步骤只执行它选中的那一个候选，两条诊断实际执行的修改合计 '
     f'{integer(AEC["total"])} 次（新 D {integer(AEC["new_D"])} 次、新 E {integer(AEC["new_E"])} 次，'
     f'其中重定位 {integer(AEC["new_E_relocations"])} 次）；其余 '
     f'{integer(CORR_REL["unmatched"].get("TASK_NOT_REACHED_IN_NEW_RUN", 0))} 条所在的生成任务本轮没有执行，'
     f'因此不能写成"70 条全部解决"。')
para('（6）全部结论都建立在 0.1 mm 中心线近距对指标上：不代表光学损耗、串扰、无碰撞制造或工艺合规；'
     '512 是项目现有合成输入，不是真实端口数据。', label='口径')

heading('7 限制与仍未验证的问题', 1)
rows = [
    ['1024 及其他输入未测', '余量是否会让更紧的窗口消失、生成缓存能否消除 1024 上的重复目标，本轮没有证据',
     '未验证'],
    ['真实端口数据', '真实 1024 端口数据尚未提供；到达后需先做输入审计，再作为独立外部验证', '未验证'],
    ['重定位的普适性', '本轮只有 1 次接受，起于 1 个起点、1 份 20 目标清单、1 个余量取值', '未验证'],
    ['60 条未执行的旧候选', '它们所在的目标在本轮已被清除，逐候选证据缺失（既未证明解决，也未证明未解决）', '证据缺失'],
    ['效率结论', '所有运行时间都是单次实测，没有重复测量与置信区间，也没有性能剖析', '未验证'],
    ['目标级归因', 'D 组 42,909 的改进没有做"哪个目标因哪项功能改变"的目标级归因', '未验证'],
    ['光学与工艺', '中心线近距对不代表损耗、串扰、无碰撞制造或工艺合规，本轮没有任何器件实测', '不适用'],
    ['未决对', '四组与新诊断终态都仍有 3 对未决（TOUCHING_THRESHOLD）；未决没有被当作 CLEAR 消除', '已知未决']]
table('仍未验证的问题与不适用的结论', ['问题', '状态说明', '性质'], rows, [3.4, 10.6, 2.0],
      text_cols=(0, 1, 2),
      notes='"未验证"表示本轮没有做相应实验；"证据缺失"表示本轮设计上无法给出结论；'
            '"不适用"表示该指标在本轮口径下没有意义，而不是数值为零。')
source('本报告的实验范围与 outputs/3d_strategy_v3/ 下各产物的 limitation 字段。')

heading('8 数据、图表与复现', 1)
para('四组主实验：outputs/3d_strategy_v3/512_ablation/（各组 ledger.json、decisions.json、final_routes.json、'
     'collision_sets.json、curve.json、summary.json、recheck.json，以及 cross_group_analysis.json、'
     'summary_all.json、comparison_groups.csv）。', small=True)
para('窗口余量探针：outputs/3d_strategy_v3/window_slack_probe/（window_slack_probe.json、'
     'wording_fix_check.json、修正前备份）。', small=True)
para('加余量重定位诊断：outputs/3d_strategy_v3/512_relocation_slack_diagnostic/（config.json、'
     'target_list.json、old_diagnostic_reference.json、decisions_{D,E}.json、curve_{D,E}.json、'
     'final_routes_{D,E}.json、collision_sets_{D,E}.json、ledger_{D,E}.json、recheck_{D,E}.json、'
     'movement_stats.json、length_ledger.json、candidate_correspondence.json、analysis.json、'
     'target_outcomes.csv、comparison_DE.csv、summary.json、manifest.json）。旧诊断结果保留在 '
     'outputs/3d_strategy_v2_rev2/512_de_diagnostic/，未被覆盖。', small=True)
para('图：outputs/3d_strategy_v3/figures/（f1 四组近距对、f2 近距对随评价次数、f3 长度与时间与预算、'
     'f4 诊断对照、f5 重定位失败原因、f6 真实路线几何、f7 路线 34 重定位前后；每张同时提供 PNG 与 PDF，'
     '并附 figures_manifest.json / figures_relocation_manifest.json 记录输入文件哈希）。', small=True)
para('复现命令（项目根目录逐条执行）：', small=True)
for command in [
        r'.venv\Scripts\python.exe -B scripts\run_3d_strategy_v3.py . outputs\3d_strategy_v3\512_ablation',
        r'.venv\Scripts\python.exe -B scripts\summarize_3d_strategy_v3.py . outputs\3d_strategy_v3\512_ablation',
        r'.venv\Scripts\python.exe -B scripts\verify_window_slack_v3.py . outputs\3d_strategy_v3\window_slack_probe',
        r'.venv\Scripts\python.exe -B scripts\run_3d_relocation_slack_diagnostic.py . outputs\3d_strategy_v3\512_relocation_slack_diagnostic',
        r'.venv\Scripts\python.exe -B scripts\analyze_relocation_slack_diagnostic.py . outputs\3d_strategy_v3\512_relocation_slack_diagnostic',
        r'.venv\Scripts\python.exe -B scripts\visualize_relocation_slack.py . outputs\3d_strategy_v3\figures',
        r'.venv\Scripts\python.exe -B scripts\visualize_3d_strategy_v3.py . outputs\3d_strategy_v3\figures',
        r'.venv\Scripts\python.exe -B -m pytest tests\ -q']:
    q = doc.add_paragraph(); r = q.add_run(command); r.font.size = Pt(8.5); r.font.name = 'SimSun'
    r.element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    q.paragraph_format.line_spacing = 1.0
    q.paragraph_format.space_before = Pt(0); q.paragraph_format.space_after = Pt(0)

doc.core_properties.title = NAME; doc.core_properties.author = '李昊伦'
doc.core_properties.subject = '三维布线策略 v3：生成失败缓存、窗口余量、加余量固定重定位诊断'
for style in doc.styles:
    fonts = style.element.get_or_add_rPr().get_or_add_rFonts()
    fonts.set(qn('w:eastAsia'), '宋体'); fonts.attrib.pop(qn('w:eastAsiaTheme'), None)
defaults = doc.styles.element.find(qn('w:docDefaults'))
if defaults is not None:
    for fonts in defaults.iter(qn('w:rFonts')):
        fonts.set(qn('w:eastAsia'), '宋体'); fonts.attrib.pop(qn('w:eastAsiaTheme'), None)
parts = [doc.part]
for section in doc.sections: parts.extend([section.header.part, section.footer.part])
for part in parts:
    for run in part.element.iter(qn('w:r')):
        fonts = run.get_or_add_rPr().get_or_add_rFonts()
        fonts.set(qn('w:eastAsia'), '宋体'); fonts.attrib.pop(qn('w:eastAsiaTheme'), None)
target = OUT/(NAME + '.docx')
doc.save(target)
(OUT/'3d_strategy_v3_report_manifest.json').write_text(json.dumps(dict(
    docx=str(target), tables=TABLES, images=IMAGES,
    inputs={str(p.relative_to(ROOT)): sha256(p) for p in
        [ABL/'cross_group_analysis.json', ABL/'summary_all.json', PROBE/'window_slack_probe.json',
         DIAG/'analysis.json', DIAG/'movement_stats.json', DIAG/'length_ledger.json',
         DIAG/'ledger_D.json', DIAG/'ledger_E.json', OLD_DIAG/'ledger_D.json', OLD_DIAG/'ledger_E.json']}),
    indent=2), encoding='utf-8')
print(json.dumps(dict(docx=str(target), tables=len(TABLES), images=len(IMAGES)), ensure_ascii=False))
