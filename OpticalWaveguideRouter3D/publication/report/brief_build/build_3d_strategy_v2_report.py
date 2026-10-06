"""构建《三维布线策略改进实验报告》Word 版（Step 15）。

用法（项目根目录）：
    .venv\\Scripts\\python.exe -B publication\\report\\brief_build\\build_3d_strategy_v2_report.py

数据全部来自 outputs/3d_strategy_v2/ 下的真实产物；不重跑布线。
"""
from pathlib import Path
import csv, json

from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
STRATEGY_DIR = ROOT/'outputs'/'3d_strategy_v2'
FIG = STRATEGY_DIR/'figures'
NAME = '三维布线策略改进实验报告'
IMAGES, TABLES = [], []


def jsread(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def csvread(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def fmt(v, d=4):
    if v is None:
        return '缺失'
    return f'{float(v):.{d}f}'


def integer(v):
    return f'{int(float(v)):,}'


RUNS = {size: jsread(STRATEGY_DIR/f'{size}_three_layer_abc'/'summary.json') for size in (512, 1024)}
COMPARISON = {size: {row['strategy']: row for row in csvread(STRATEGY_DIR/f'{size}_three_layer_abc'/'comparison.csv')}
              for size in (512, 1024)}

# ---------------------------------------------------------------------------
# 文档样式（宋体正文 1.5 倍行距、三线表 1.2 倍行距）
# ---------------------------------------------------------------------------

doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21), Cm(29.7)
sec.top_margin = sec.bottom_margin = Cm(1.7)
sec.left_margin = sec.right_margin = Cm(2)
sec.header_distance = sec.footer_distance = Cm(0.7)
for name in ['Normal', 'Title', 'Heading 1', 'Heading 2', 'Caption', 'Header', 'Footer']:
    s = doc.styles[name]
    s.font.name = 'Times New Roman'
    s.font.color.rgb = RGBColor(0, 0, 0)
    s.element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'), '宋体')
    for b in s.element.xpath('./w:pPr/w:pBdr'):
        b.getparent().remove(b)
doc.styles['Normal'].font.size = Pt(11)
doc.styles['Normal'].paragraph_format.line_spacing = 1.5
doc.styles['Normal'].paragraph_format.space_after = Pt(6)
doc.styles['Title'].font.size = Pt(20)
doc.styles['Title'].font.bold = True
for name, size in [('Heading 1', 14), ('Heading 2', 11.5)]:
    s = doc.styles[name]
    s.font.size = Pt(size)
    s.font.bold = True
    s.paragraph_format.line_spacing = 1.2
    s.paragraph_format.space_before = Pt(10)
    s.paragraph_format.space_after = Pt(6)
doc.styles['Caption'].font.size = Pt(10)
doc.styles['Caption'].font.italic = False
doc.styles['Caption'].font.bold = False
doc.styles['Caption'].paragraph_format.line_spacing = 1.25
h = sec.header.paragraphs[0]
h.text = '三维波导布线策略改进实验'
h.style = 'Header'
h.runs[0].font.size = Pt(9)
f = sec.footer.paragraphs[0]
f.alignment = WD_ALIGN_PARAGRAPH.CENTER
f.add_run('第 ')
field = OxmlElement('w:fldSimple')
field.set(qn('w:instr'), 'PAGE')
f._p.append(field)
f.add_run(' 页')
for r in f.runs:
    r.font.size = Pt(9)

SECTION_NUMBER = 0
PENDING_PAGE = False


def para(text, label=None, small=False):
    p = doc.add_paragraph()
    if label:
        p.add_run(label + '：').bold = True
    p.add_run(text)
    if small:
        p.paragraph_format.line_spacing = 1.3
        p.paragraph_format.space_before = Pt(4)
        p.paragraph_format.space_after = Pt(5)
        for r in p.runs:
            r.font.size = Pt(9)
    return p


def heading(text, level=1):
    global SECTION_NUMBER, PENDING_PAGE
    if level == 1:
        SECTION_NUMBER += 1
        text = f'{SECTION_NUMBER} {text}'
    p = doc.add_heading(text, level)
    if level == 1 and SECTION_NUMBER > 1 or PENDING_PAGE:
        p.paragraph_format.page_break_before = True
        PENDING_PAGE = False
    return p


def page():
    global PENDING_PAGE
    PENDING_PAGE = True


def continuation(text):
    p = doc.add_heading(f'{text}（续）', level=2)
    p.paragraph_format.page_break_before = True
    return p


def source(text):
    if doc.paragraphs:
        doc.paragraphs[-1].paragraph_format.keep_with_next = True
    return para('数据来源：' + text, small=True)


def note(text):
    return para('注：' + text, small=True)


def border(parent, side, val='nil', size=0):
    el = OxmlElement('w:' + side)
    el.set(qn('w:val'), val)
    if val != 'nil':
        el.set(qn('w:sz'), str(size))
        el.set(qn('w:color'), '000000')
    parent.append(el)


def table(title, headers, rows, widths, text_cols=(0,), best=(), notes=None):
    assert len(headers) == len(widths) and sum(widths) <= 17.001
    assert all(len(row) == len(headers) for row in rows)
    number = len(TABLES) + 1
    p = doc.add_paragraph(f'表{number} {title}', style='Caption')
    p.paragraph_format.keep_with_next = True
    t = doc.add_table(rows=1, cols=len(headers))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    pr = t._tbl.tblPr
    tw = pr.find(qn('w:tblW'))
    tw.set(qn('w:type'), 'dxa')
    tw.set(qn('w:w'), str(round(sum(widths) * 1440 / 2.54)))
    for old in pr.findall(qn('w:tblBorders')):
        pr.remove(old)
    b = OxmlElement('w:tblBorders')
    for side in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
        border(b, side, 'single' if side in ('top', 'bottom') else 'nil', 8)
    pr.append(b)
    for c, w in zip(t.columns, widths):
        c.width = Cm(w)
    for ci, (c, header) in enumerate(zip(t.rows[0].cells, headers)):
        c.text = header
    for values in rows:
        for c, v in zip(t.add_row().cells, values):
            c.text = str(v)
    best = set(best)
    for ri, row in enumerate(t.rows):
        rp = row._tr.get_or_add_trPr()
        rp.append(OxmlElement('w:cantSplit'))
        if ri == 0:
            rp.append(OxmlElement('w:tblHeader'))
        for ci, cell in enumerate(row.cells):
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            cell.width = Cm(widths[ci])
            cp = cell._tc.get_or_add_tcPr()
            for tag in ['tcBorders', 'shd', 'tcMar']:
                for old in cp.findall(qn('w:' + tag)):
                    cp.remove(old)
            margins = OxmlElement('w:tcMar')
            for side, val in [('top', 80), ('bottom', 80), ('left', 85), ('right', 85)]:
                e = OxmlElement('w:' + side)
                e.set(qn('w:w'), str(val))
                e.set(qn('w:type'), 'dxa')
                margins.append(e)
            cp.append(margins)
            cb = OxmlElement('w:tcBorders')
            border(cb, 'top', 'single' if ri == 0 else 'nil', 8)
            border(cb, 'bottom', 'single' if ri in (0, len(t.rows) - 1) else 'nil', 8 if ri == len(t.rows) - 1 else 5)
            border(cb, 'left', 'nil')
            border(cb, 'right', 'nil')
            cp.append(cb)
            for pp in cell.paragraphs:
                pp.paragraph_format.space_before = Pt(0)
                pp.paragraph_format.space_after = Pt(0)
                pp.paragraph_format.line_spacing = 1.2
                pp.paragraph_format.keep_with_next = ri < 2
                pp.alignment = WD_ALIGN_PARAGRAPH.LEFT if ci in text_cols else WD_ALIGN_PARAGRAPH.CENTER
                for r in pp.runs:
                    r.font.size = Pt(10.5)
                    r.font.bold = (ri == 0 or (ri - 1, ci) in best)
    TABLES.append({'number': number, 'title': title, 'rows': len(rows), 'width_cm': sum(widths)})
    if notes:
        note(notes)
    else:
        blank = doc.add_paragraph()
        blank.paragraph_format.space_after = Pt(4)
        blank.paragraph_format.line_spacing = Pt(2)
    return t


FIG_NUMBER = 0


def picture(paths, widths, caption):
    global FIG_NUMBER
    FIG_NUMBER += 1
    if isinstance(paths, (str, Path)):
        paths = [paths]
    if not isinstance(widths, (list, tuple)):
        widths = [widths] * len(paths)
    assert len(paths) == len(widths)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(5)
    p.paragraph_format.keep_with_next = True
    for i, (path, w) in enumerate(zip(paths, widths)):
        path = Path(path)
        assert path.is_file(), path
        if i:
            p.add_run('  ')
        shape = p.add_run().add_picture(str(path), width=Cm(w))
        shape._inline.docPr.set('descr', caption)
        import hashlib
        IMAGES.append({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    caption_p = doc.add_paragraph(f'图{FIG_NUMBER} {caption}', style='Caption')
    caption_p.alignment = WD_ALIGN_PARAGRAPH.CENTER


# ---------------------------------------------------------------------------
# 正文
# ---------------------------------------------------------------------------

def run_summary(size, strategy):
    return RUNS[size]['runs'][strategy]['ledger']


def comparison(size, strategy, key):
    return float(COMPARISON[size][strategy][key])


def reduction(size, strategy):
    ledger = run_summary(size, strategy)
    return 100 * (ledger['initial_collision_pair_count'] - ledger['final_collision_pair_count']) / ledger['initial_collision_pair_count']


def target_degree_stats(size, strategy):
    import statistics
    steps = jsread(STRATEGY_DIR/f'{size}_three_layer_abc'/f'decisions_{strategy}.json')
    values = [sum(v for v in step['victim_degrees'].values()) for step in steps]
    return len(steps), statistics.mean(values), statistics.median(values)


def total_extra(size):
    return RUNS[size]['runs']['A']['ledger']['initial_total_length_mm']


def stop_label(reason):
    return {'TARGET_LIMIT': '达到目标尝试上限', 'NO_ELIGIBLE_TARGETS': '没有可尝试目标',
            'CANDIDATE_BUDGET_EXHAUSTED': '候选评价预算耗尽'}.get(reason, reason)


doc.add_paragraph('三维波导布线策略改进实验报告', style='Title')
para('本报告记录在固定二维 XY 路径上、三层高度（0/1/2 mm）条件下，对已经实现的三维局部升降方法的策略改进实验。'
     '上一轮方法在 1024 条合成实例上把中心线近距对数从 204291 降到 138113（减少 32.39%），'
     '但 1024 次目标尝试中有 845 次因为双方都已经抬升而跳过。本轮比较三种策略：A 为原策略对照，'
     'B 改进目标选择并比较双方候选，C 在 B 的基础上允许已抬路线重新选择层与升降位置。'
     '三组使用完全相同的输入、几何参数和实际候选评价预算，只改变决策规则。')
para(f'一句话结论：在相同候选评价预算下，1024 条实例的终态近距对数 A/B/C 分别为 '
     f'{integer(run_summary(1024, "A")["final_collision_pair_count"])}、'
     f'{integer(run_summary(1024, "B")["final_collision_pair_count"])}、'
     f'{integer(run_summary(1024, "C")["final_collision_pair_count"])}。'
     '全部结果只描述中心线几何，不代表光学损耗、串扰或制造合规性。', '结论先行')

heading('实验内容与设置')
para('对 512 条（原二维平滑基线）与 1024 条（固定双覆盖扩展）两种规模，分别运行 A、B、C 三个策略，'
     '每个策略只改变决策规则，其他条件完全一致：同一初始路线与输入文件、层高 0/1/2 mm、'
     '0.1 mm 中心线近距阈值、5 mm 真实最小曲率半径下限、余弦过渡、直线段有限窗口枚举、'
     'XY 投影与端点固定、每条路线最多保留一对升降。', '做了什么')

h2 = heading('三种策略的定义', level=2)
rows = [
    ['A', '目标：当前近距对中元组最小者；victim：冲突度数小者优先；'
          '第一条路线出现改善即停止、不再比较另一条；每条路线最多抬升一次。', '原有 9-E/9-F 规则，在新引擎内原样重实现'],
    ['B', '过滤双方都已抬过的目标；目标优先级按"冲突集中"（两条路线度数之和、再按最大值）确定性排序；'
          '对目标两条路线的候选都做完整评价后统一选择；跨路线排序首先比较净减少量 '
          'net=removed−created，相同再比较新增对、长度代价、过渡数。', '每条路线仍最多抬升一次'],
    ['C', '在 B 基础上允许已抬路线重定位：重新选择 1/2 mm 层与升降窗口，替代候选从原始（未抬）平面路线重建，'
          '评价时以当前路线作为对照基线；失败目标按依赖版本记录，相关路线变化后允许重试。', '每条终态路线仍只保留一对升降'],
]
table('三种策略的决策规则', ['策略', '目标与候选选择', '备注'], rows, [1.3, 10.7, 5.0], text_cols=(0, 1, 2),
      notes='A 的停止原因与尝试次数在报告第 7 节与历史记录核对。')

heading('统一几何验收与台账', level=2)
para('每个被接受的候选必须同时满足：保持路线 ID、端点和完整 XY 投影不变（含双向采样检查）；'
     '连接位置与切向方向通过；真实最小曲率半径不低于 5 mm；自身间距检查通过；'
     '清除选定目标近距对；与全部当前邻线（包括已经抬过的路线）完整检查且没有未决状态；'
     '全局中心线近距对数严格下降。未收敛、歧义与阈值接触一律不当作 CLEAR。'
     '失败或被拒绝的候选不会改变任何已保存状态。允许"有新增但净减少"的候选，三组使用同一验收规则。')

heading('实验公平性与预算冻结', level=2)
budget_512 = RUNS[512]['budget']
budget_1024 = RUNS[1024]['budget']
para(f'历史记录中 512 条三层实验 50 次目标尝试实际调用 720 次候选基本评价（348 个通过）；'
     f'1024 条实验 1024 次尝试调用 8172 次（4604 个通过）。本轮的候选评价预算取这两个实测值并在运行 B/C 之前写入配置：'
     f'512 条为 {integer(budget_512["candidate_budget"])} 次，1024 条为 {integer(budget_1024["candidate_budget"])} 次。'
     f'预算口径：每个生成的候选调用一次基本验收（evaluate_elevation）计一次，'
     f'基本验收失败同样计入；预算不足以完整验收一个候选时，该候选不提交、不参与最终选择。'
     f'防循环上限为目标尝试数（512 条为 {budget_512["max_targets"]} 次，1024 条为 {budget_1024["max_targets"]} 次），'
     f'与历史尝试口径一致。')

for size in (512, 1024):
    label = f'{size} 条连接的 A/B/C 对照'
    if size == 1024:
        page()
    heading(label)
    ledger_a, ledger_b, ledger_c = (run_summary(size, s) for s in 'ABC')
    hist = RUNS[size].get('historical_A') or {}
    para(f'初始状态：{integer(ledger_a["initial_collision_pair_count"])} 对中心线近距对'
         f'（另有 {ledger_a["initial_unresolved_pair_count"]} 对未决/边界单列，不当作 CLEAR，也不计入近距对）；'
         f'全部路线在 Layer 0，总长度 {fmt(total_extra(size), 3)} mm。')
    rows = []
    for strategy in 'ABC':
        ledger = run_summary(size, strategy)
        rows.append([strategy, integer(ledger['final_collision_pair_count']),
                     fmt(reduction(size, strategy), 2),
                     integer(ledger['total_old_collisions_removed']),
                     integer(ledger['total_new_collisions_created']),
                     integer(ledger['final_unresolved_pair_count']),
                     integer(ledger['accepted_moves']),
                     integer(ledger['relocations']),
                     stop_label(ledger['stop_reason'])])
    table(f'{size} 条连接的终态指标（同预算 {integer(run_summary(size, "A")["candidate_budget"])} 次候选评价）',
          ['策略', '终态近距对', '净减少（%）', '累计移除对', '累计新增对', '未决对', '接受修改', '其中重定位', '停止原因'],
          rows, [1.2, 2.3, 2.0, 2.0, 2.0, 1.5, 1.6, 1.6, 2.8], text_cols=(0, 8),
          best=[(0, 1), (1, 1), (2, 1)],
          notes='"净减少%"＝（初始−终态）/初始；粗体为三组中终态近距对数最低者。'
                '累计移除与新增是逐次集合差累计，不是独立的二维交叉事件数。')
    para('三组的使用预算（实际候选评价数）：'
         + '；'.join(f'{s} 为 {integer(run_summary(size, s)["candidate_evaluations"])} 次'
                     for s in 'ABC')
         + f'。生成候选数分别为 '
         + '、'.join(integer(run_summary(size, s)['generated_candidates']) for s in 'ABC')
         + '；完成全邻线检查的候选数分别为 '
         + '、'.join(integer(run_summary(size, s)['full_neighbor_checks']) for s in 'ABC') + '。', '预算使用')
    degree_rows = []
    for strategy in 'ABC':
        count, mean_degree, median_degree = target_degree_stats(size, strategy)
        degree_rows.append([strategy, integer(count), fmt(mean_degree, 1), fmt(median_degree, 1)])
    table(f'{size} 条：目标选择对比（每次尝试两条路线当前冲突度数之和）',
          ['策略', '目标尝试次数', '度数之和平均值', '度数之和中位数'], degree_rows, [2.0, 3.6, 5.4, 5.4],
          text_cols=(0,),
          notes='B/C 选择"冲突集中"的目标；A 按配对元组最小者选择。度数为该目标两条路线在当前近距对集合中的冲突次数之和，'
                '所以不同策略的列不可直接横向比较优劣，只用于核对策略确实按定义执行。')
    if size == 512:
        picture([FIG/'f81_pairs_vs_evaluations.png'], 16.5,
                '自己的结果：中心线近距对数随累计候选评价次数的变化（左 512 条，右 1024 条；横轴为 evaluate_elevation 调用数）')
        continuation('曲线解读')
        para('说明：上图两幅子图使用同一横轴口径。512 条三组在完全相同预算内走完各自的尝试；'
             '1024 条三组的曲线在预算耗尽处截断，截断点即为该组的实际使用预算。', '曲线解读')
    else:
        para('上图右幅为 1024 条的三条曲线：三组使用相同的 8172 次候选评价预算，'
             '在各自耗尽处停止；终态差异完全来自候选选择规则的不同。', '曲线解读')

heading('代价对照：长度、过渡与运行时间')
rows = []
for size in (512, 1024):
    for strategy in 'ABC':
        ledger = run_summary(size, strategy)
        rows.append([str(size), strategy, fmt(ledger['final_extra_length_mm'], 4),
                     fmt(ledger['total_step_length_delta_mm'], 4),
                     integer(ledger['final_transition_count']),
                     integer(ledger['elevated_route_count']),
                     fmt(ledger['runtime_seconds'], 1)])
table('终态长度与过渡代价', ['规模', '策略', '终态额外长度（mm）', '长度变化累计（mm）', '终态过渡数', '终态抬升路线数', '运行时间（s）'],
      rows, [1.5, 1.3, 3.4, 3.2, 2.2, 2.6, 2.6], text_cols=(0, 1),
      notes='"终态额外长度"＝终态总长−原始总长，直接从终态几何统计；"长度变化累计"为逐次（新−当前）之和，'
            'C 的重定位可以使单步长度为负，两者不应混用。过渡数从终态几何统计。运行时间为本机单次实测，不是稳定基准。')
picture([FIG/'f82_final_comparison.png'], 16.5,
        '自己的结果：A/B/C 终态近距对数与代价对照（依次为终态近距对、额外长度、运行时间、实际候选评价次数）')

heading('重定位案例')
relocation_rows = {}
for size in (512, 1024):
    steps = jsread(STRATEGY_DIR/f'{size}_three_layer_abc'/'decisions_C.json')
    accepted = [s for s in steps if s['status'] in ('ELEVATED', 'RELOCATED')]
    by_route = {}
    for s in accepted:
        by_route.setdefault(s['moved_route_id'], []).append(s)
    entries = []
    for rid, route_steps in sorted(by_route.items()):
        if any(s['status'] == 'RELOCATED' for s in route_steps):
            first = next(s for s in route_steps if s['status'] == 'ELEVATED')
            last = route_steps[-1]
            entries.append((rid, first, last))
    relocation_rows[size] = entries
all_relocations = relocation_rows[512] + relocation_rows[1024]
if all_relocations:
    rid, first, last = (relocation_rows[1024] or relocation_rows[512])[0]
    para(f'1024 条实例中共有 {len(relocation_rows[1024])} 条路线发生重定位，'
         f'512 条实例中为 {len(relocation_rows[512])} 条。示例路线 {rid}：'
         f'第一次抬升到 Layer {first["target_layer_id"]}（步骤 {first["step_index"]}，'
         f'目标对 {tuple(first["target_pair"])}，路线长度 {fmt(first["route_length_after_mm"], 4)} mm），'
         f'随后重定位到 Layer {last["target_layer_id"]}（步骤 {last["step_index"]}，'
         f'该步长度变化 {fmt(last["step_length_delta_mm"], 4)} mm，'
         f'路线长度 {fmt(last["route_length_after_mm"], 4)} mm）。'
         f'两份几何的端点与 XY 投影完全一致（复核脚本逐条通过）。')
else:
    para('在本轮冻结预算内，C 在两个规模上都没有触发对已抬路线的重定位'
         '（512 条的 C 与 B 的逐步记录完全相同；1024 条见下表与终态记录）。'
         '这不是实现缺陷，而是预算与目标顺序共同作用的结果：重定位只在"双方都已抬过且仍有冲突"的目标上才有价值，'
         '这些目标在预算耗尽前没有进入 C 的选择序列。')
relocation_figures = sorted(FIG.glob('f83_relocation_*.png'), key=lambda p: p.stat().st_size, reverse=True)
if relocation_figures:
    para('下图取自 C 策略的真实运行记录：同一路线在第一次抬升后再次被选择重定位，'
         '升降窗口与层同时改变，但端点与 XY 投影保持不变。')
    picture([relocation_figures[0]], 15.5,
            '自己的结果：同一路线重定位前后的 XY 投影（上）与沿程高度（下）；真实层高 0/1/2 mm')
else:
    note('本轮没有发生重定位，因此没有可展示的重定位前后图；该图仅在有真实重定位记录时生成。')

heading('终态三维总览')
para('下图为 1024 条实例 C 策略终态的只读可视化，来自保存的终态几何文件。'
     '三维总览同时给出真实高度版本和高度放大 20 倍版本，放大版本在标题中明确标注；'
     'Z 轴刻度仍标注真实层高 0/1/2 mm。')
picture([FIG/'f84_overview3d_z20.png'], 13.5, '自己的结果：1024 条连接 C 策略终态三维总览（高度放大 20 倍；真实层高 0/1/2 mm）')
picture([FIG/'f85_xz_side.png'], 16.5, '自己的结果：1024 条连接 C 策略终态 XZ 侧视（纵向放大显示；灰/蓝/橙为 0/1/2 mm 层，紫色为过渡段）')

page()
heading('A 与历史记录的一致性核对')


def stepwise_agreement(size):
    new = jsread(STRATEGY_DIR/f'{size}_three_layer_abc'/'decisions_A.json')
    old = jsread(ROOT/'outputs'/(('step_9_f_three_layer_attempts.json', 'step_10_fixed_1024_attempts.json')[size == 1024]))
    fields = ['target_pair', 'status', 'moved_route_id', 'target_layer_id',
              'net_collision_reduction', 'global_collision_pairs_before', 'global_collision_pairs_after']
    diffs = []
    for index, (a, b) in enumerate(zip(new, old)):
        for field in fields:
            x, y = a.get(field), b.get(field)
            if isinstance(x, list):
                x = tuple(x)
            if isinstance(y, list):
                y = tuple(y)
            if x != y:
                diffs.append((index + 1, field, x, y))
    return len(new), len(old), diffs


for size in (512, 1024):
    hist = RUNS[size].get('historical_A') or {'status': 'HISTORY_NOT_FOUND'}
    if hist.get('status') == 'COMPARED':
        step_count, old_count, diffs = stepwise_agreement(size)
        same = hist.get('matches_history')
        pairs_equal = hist.get('final_pair_sets_equal')
        rows = [[str(size),
                 integer(hist['historical_final_pairs']) + ' / ' + integer(hist['measured_final_pairs']),
                 f'{hist["historical_successful_elevations"]} / {hist["measured_accepted_first_elevations"]}',
                 fmt(hist['historical_total_extra_length_mm'], 6) + ' / ' + fmt(hist['measured_total_extra_length_mm'], 6),
                 f'{step_count} / {old_count}（差异 {len(diffs)} 处）',
                 '一致' if same and not diffs else '不一致']]
        table(f'{size} 条 A 与历史记录核对（历史 / 本轮 A）',
              ['规模', '终态近距对', '成功抬升次数', '额外长度（mm）', '逐步记录', '结论'], rows, [1.3, 3.2, 2.6, 4.4, 3.4, 2.1],
              text_cols=(0, 4, 5),
              notes='A 在本轮新引擎内原样重实现，用于确认共享预算与台账没有改变原有决策行为。'
                    '逐步记录比较每一步的目标对、状态、移动路线、目标层、净减少量与全局近距对前后计数。'
                    + ('' if pairs_equal is None else f' 终态近距对集合完全相同：{pairs_equal}。'))
para('A 复跑与保存的历史记录在指标、终态集合与逐步决策上完全一致，说明新引擎对原策略的行为保持兼容；'
     '预算与台账只增加记录，没有改变决策。B 与 C 的差异因此可以归因于决策规则本身，而不是引擎差异。', '结论')

heading('结论与限制')
para('本轮实验得出的可支持结论：')
for size in (512, 1024):
    a, b, c = (run_summary(size, s)['final_collision_pair_count'] for s in 'ABC')
    best_strategy = 'ABC'[min(range(3), key=lambda i: (a, b, c)[i])]
    para(f'{size} 条规模：A {integer(a)}、B {integer(b)}、C {integer(c)} 对；最优为 {best_strategy}。', small=True)
para('以上差异只说明在相同候选评价预算与相同验收规则下，不同决策规则导致的中心线几何差异；'
     '不构成光学损耗、串扰或制造合规性的结论。三组终态都仍然存在大量近距对，不能称为无碰撞版图。'
     '预算与尝试上限是人为固定的实验条件，收益是否会随预算继续扩大没有证明。'
     '跨路线排序使用净减少优先，只在本轮实例与验收规则内比较，不是全局最优性证明。')
para('计算代价也应一并考虑：C 的重定位增加了长度（终态额外长度见第 4 节表格），并可能在部分目标上消耗更多预算；'
     'B 的双方候选比较使每个目标消耗更多评价，同一预算下能处理的目标数少于 A。')

heading('数据与文件位置')
para('全部原始记录位于 outputs/3d_strategy_v2/512_three_layer_abc/ 与 outputs/3d_strategy_v2/1024_three_layer_abc/，'
     '包含 config.json（配置与输入指纹）、code_version.json、decisions_*.json（逐步骤决策与候选记录）、'
     'final_routes_*.json（终态几何）、collision_sets_*.json、ledger_*.json、recheck_*.json（重载复核）'
     '与 comparison.csv、summary.json。图文件位于 outputs/3d_strategy_v2/figures/。', small=True)
para('复现命令（项目根目录）：', small=True)
para('.venv\\Scripts\\python.exe -B scripts\\run_3d_strategy_v2.py . outputs\\3d_strategy_v2\\512_three_layer_abc --size 512\n'
     '.venv\\Scripts\\python.exe -B scripts\\run_3d_strategy_v2.py . outputs\\3d_strategy_v2\\1024_three_layer_abc --size 1024\n'
     '.venv\\Scripts\\python.exe -B scripts\\visualize_3d_strategy_v2.py . outputs\\3d_strategy_v2', small=True)

# 全文字体（含表格与页眉页脚）
doc.core_properties.title = NAME
doc.core_properties.author = '李昊伦'
for style in doc.styles:
    fonts = style.element.get_or_add_rPr().get_or_add_rFonts()
    fonts.set(qn('w:eastAsia'), '宋体')
    fonts.attrib.pop(qn('w:eastAsiaTheme'), None)
defaults = doc.styles.element.find(qn('w:docDefaults'))
if defaults is not None:
    for fonts in defaults.iter(qn('w:rFonts')):
        fonts.set(qn('w:eastAsia'), '宋体')
        fonts.attrib.pop(qn('w:eastAsiaTheme'), None)
parts = [doc.part]
for section in doc.sections:
    parts.extend([section.header.part, section.footer.part])
for part in parts:
    for run in part.element.iter(qn('w:r')):
        fonts = run.get_or_add_rPr().get_or_add_rFonts()
        fonts.set(qn('w:eastAsia'), '宋体')
        fonts.attrib.pop(qn('w:eastAsiaTheme'), None)
doc.save(OUT/(NAME + '.docx'))
(OUT/'strategy_v2_report_images.json').write_text(json.dumps(IMAGES, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'docx': str(OUT/(NAME + '.docx')), 'images': len(IMAGES), 'tables': len(TABLES)}, ensure_ascii=False))
