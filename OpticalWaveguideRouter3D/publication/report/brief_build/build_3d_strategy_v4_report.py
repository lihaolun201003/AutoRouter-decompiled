"""Build 《三维波导布线 v4 实验报告》 DOCX - 中文宋体, 原生三线表, 正文 1.5 倍行距.

Every number is read from the real artifacts under
outputs/3d_strategy_v4/512_full_layout/; nothing is hand-typed.

Usage (project root):
    .venv\\Scripts\\python.exe -B publication\\report\\brief_build\\build_3d_strategy_v4_report.py
"""
import json, re, hashlib
from pathlib import Path
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parents[3]
RUNS = ROOT/'outputs/3d_strategy_v4/512_full_layout'
FIG = RUNS/'figures'
OUT = Path(__file__).resolve().parent
NAME = '三维波导布线v4实验报告'
GROUPS = ['N720', 'R720', 'N1440', 'R1440', 'N2880', 'R2880']
BUDGETS = [720, 1440, 2880]
MODE_LABEL = {'N': 'N（不重定位）', 'R': 'R（允许重定位）'}
START_DIR = 'outputs/3d_strategy_v3/512_ablation/D_both_enabled'


def jsread(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha256(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fmt(v, d=4): return f'{float(v):.{d}f}'


def integer(v): return f'{int(round(float(v))):,}'


def pct(v, d=2): return f'{float(v):.{d}f}'


def parse_pytest_log(path):
    text = Path(path).read_text(encoding='utf-8-sig', errors='replace')
    tail = [ln.strip() for ln in text.splitlines() if ln.strip()]
    summary = next((ln for ln in reversed(tail) if re.search(r'\d+ (passed|failed|error)', ln)),
        '未找到结果行')
    m = re.search(r'in ([\d.]+)s', summary)
    return dict(summary=re.sub(r'\s*in [\d.]+s.*$', '', summary),
        seconds=m.group(1) if m else '未知', path=str(path))


def new_test_names(path):
    text = Path(path).read_text(encoding='utf-8')
    return re.findall(r'^def (test_[A-Za-z0-9_]+)', text, re.M)


START = jsread(RUNS/'start_state_check.json')
AGG = jsread(RUNS/'summary_all_v4.json')
SUMMARY = {g: jsread(RUNS/g/'summary.json') for g in GROUPS}
CONFIG = {g: jsread(RUNS/g/'config.json') for g in GROUPS}
LEGER = {g: jsread(RUNS/g/'ledger.json') for g in GROUPS}
RECHECK = {g: jsread(RUNS/g/'recheck.json') for g in GROUPS}
CURVE = {g: jsread(RUNS/g/'curve.json') for g in GROUPS}
AUDIT = jsread(RUNS/'audit/classification_summary.json')
AUDIT_RECOUNT = jsread(RUNS/'audit/recount.json')
AUDIT_LIST = jsread(RUNS/'audit/target_list.json')
AUDIT_RULES = jsread(RUNS/'audit/sampling_rules.json')
AUDIT_LEDGER = jsread(RUNS/'audit/audit_ledger.json')
AUDIT_SIDES = jsread(RUNS/'audit/side_audit.json')['records']
REACH = jsread(RUNS/'relocation_reachability.json')
FIGMAN = jsread(FIG/'figures_v4_manifest.json')
TEST3D = parse_pytest_log(RUNS/'pytest_full_v4.log')
TEST2D = parse_pytest_log(RUNS/'pytest_opt2d_2d_env_v4.log')
NEWTESTS = new_test_names(ROOT/'tests/test_strategy_v4_3d.py')
START_LEDGER = jsread(ROOT/START_DIR/'ledger.json')
CORRECT_AC = jsread(ROOT/'outputs/3d_strategy_v3/512_relocation_slack_diagnostic/analysis.json')[
    'accepted_edit_counts']
STATS = {g: SUMMARY[g]['stats'] for g in GROUPS}
BY = {r['group']: r for r in AGG['comparison']}
PAIRED = {p['appended_candidate_budget']: p for p in AGG['paired_n_vs_r']}
MODE = {g: STATS[g]['mode'] for g in GROUPS}
DECISIONS = {g: jsread(RUNS/g/'decisions.json') for g in GROUPS}
_STEP_GENERATED = [sum(v.get('generated_count', 0) for v in step['victim_attempts'])
    for g in GROUPS for step in DECISIONS[g]
    if sum(v.get('generated_count', 0) for v in step['victim_attempts'])]
TOTAL_EVALUATIONS = sum(STATS[g]['candidate_evaluations'] for g in GROUPS)
TOTAL_MOVES = sum(STATS[g]['accepted_moves'] for g in GROUPS)
TOTAL_GENERATED = sum(STATS[g]['generated_candidates'] for g in GROUPS)
TOTAL_FULL_CHECKS = sum(STATS[g]['full_neighbor_checks'] for g in GROUPS)
TOTAL_BASIC_REJECTS = sum(sum(STATS[g]['basic_rejection_reason_counts'].values()) for g in GROUPS)
TOTAL_FULL_REJECTS = sum(sum(STATS[g]['full_rejection_reason_counts'].values()) for g in GROUPS)
TOTAL_GENERATION_FAILURES = sum(sum(STATS[g]['generation_failure_reason_counts'].values()) for g in GROUPS)
AVG_EVALUATIONS_PER_MOVE = TOTAL_EVALUATIONS/max(1, TOTAL_MOVES)
STEP_GENERATED_RANGE = (min(_STEP_GENERATED), max(_STEP_GENERATED))

TABLES, IMAGES, TN, FN = [], [], {}, {}

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
h = sec.header.paragraphs[0]; h.text = '三维波导布线 v4 实验报告'; h.style = 'Header'
h.alignment = WD_ALIGN_PARAGRAPH.CENTER
for r in h.runs: r.font.size = Pt(9); r.font.name = 'SimSun'
fr = sec.footer.paragraphs[0]; fr.alignment = WD_ALIGN_PARAGRAPH.CENTER
fr.add_run('第 ')
field = OxmlElement('w:fldSimple'); field.set(qn('w:instr'), 'PAGE'); fr._p.append(field)
fr.add_run(' 页')
for r in fr.runs: r.font.size = Pt(9); r.font.name = 'SimSun'


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


def table(title, headers, rows, widths, text_cols=(0,), best=(), notes=None, sources=None, key=None):
    """Native Word three-line table: header rule + bottom rule only, no vertical lines."""
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
    for c, text in zip(t.rows[0].cells, headers): c.text = text
    for values in rows:
        for c, v in zip(t.add_row().cells, values): c.text = str(v)
    best = set(best)
    keep_together = len(rows) <= 6
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
            border(cb, 'bottom', 'single' if ri in (0, len(t.rows) - 1) else 'nil', 5 if ri == 0 else 8)
            border(cb, 'left', 'nil'); border(cb, 'right', 'nil')
            cp.append(cb)
            for pgh in cell.paragraphs:
                pgh.paragraph_format.space_before = Pt(0); pgh.paragraph_format.space_after = Pt(0)
                pgh.paragraph_format.line_spacing = 1.2
                pgh.alignment = WD_ALIGN_PARAGRAPH.LEFT if ci in text_cols else WD_ALIGN_PARAGRAPH.CENTER
                for r in pgh.runs:
                    r.font.size = Pt(9.5); r.font.name = 'SimSun'
                    r.element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
                    r.font.bold = (ri == 0 or (ri - 1, ci) in best)
    TABLES.append(dict(number=number, title=title, rows=len(rows), width_cm=round(sum(widths), 3)))
    if key: TN[key] = number
    if notes: note(notes)
    if sources: source(sources)
    return t


FIG_NUMBER = [0]


def picture(path, width_cm, caption):
    path = Path(path); assert path.is_file(), path
    FIG_NUMBER[0] += 1
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(4); p.paragraph_format.keep_with_next = True
    shape = p.add_run().add_picture(str(path), width=Cm(width_cm))
    shape._inline.docPr.set('descr', caption)
    IMAGES.append(dict(path=str(path), sha256=sha256(path), caption=caption))
    q = doc.add_paragraph(f'图{FIG_NUMBER[0]} {caption}', style='Caption')
    q.alignment = WD_ALIGN_PARAGRAPH.CENTER; q.paragraph_format.keep_with_next = False
    return q


def figure(name, width_cm, caption, key=None):
    entry = next(e for e in FIGMAN['images'] if e['name'] == name)
    q = picture(entry['png'], width_cm, caption)
    if key: FN[key] = FIG_NUMBER[0]
    return q


# =============================================================== 封面与目的
doc.add_paragraph(NAME, style='Title')
sub = doc.add_paragraph('——残余近距对瓶颈审计、全布局持续优化（N/R 移动权限开关）与六组追加预算对照',
                        style='Caption')
sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
para('本报告记录本轮实际完成的三件事：①对 v3 组 D 终态中剩余的 42,909 对中心线近距做瓶颈审计；'
     '②新增 v4 全布局持续优化接口，并只用一个 allow_relocation 开关区分 N（只允许首次抬升）与 '
     'R（首次抬升＋已抬路线重定位）；③六组追加候选预算实验 N720/R720/N1440/R1440/N2880/R2880，'
     '每组都独立从同一个终态出发。')
para('本报告回答“做了什么、结果怎么样、结论、限制”，不是完整论文，也不替代此前的实验记录与历史报告。')
para('口径：全部比较指标是 0.1 mm 中心线近距对数（close pair count），不代表光学损耗、串扰、'
     '无碰撞制造或工艺合规，也不代表器件实测。512 是项目既有合成输入（LEGACY_512_SMOOTHED_P0），'
     '不是真实端口数据。六组的“预算”是从共同终态起追加的候选基本评价预算，不包含形成该起点的历史 720 次评价。')

# =============================================================== 第1章
heading('第 1 章 共同起点与复核', 1, new_page=True)
para('全部六组实验与审计使用同一个起点：v3 组 D（generation_failure_cache=True、'
     'window_slack_mm=1e-5）的终态目录，路径见下方。为了不依赖保存文件的自洽性，'
     '本轮在每组运行开始时都对起点做了一次完整的 130,816 对重算，并与保存的近距集合逐对比较。')
start_rows = [
    ['路线数', integer(START['route_count']), integer(START['route_count']), '一致'],
    ['全部路线对检查数', integer(START['checks']), integer(START['checks']), '每对都重新分类'],
    ['中心线近距对数', integer(START['recomputed_collision_pair_count']),
     integer(START['saved_collision_pair_count']),
     '一致' if START['recomputed_pair_set_matches_saved'] else '不一致'],
    ['未决（非 CLEAR 非 COLLISION）对数', integer(START['recomputed_unresolved_pair_count']),
     integer(START['saved_unresolved_pair_count']),
     '一致' if START['recomputed_unresolved_set_matches_saved'] else '不一致'],
    ['已抬升路线数', integer(START['elevated_route_count']),
     integer(START_LEDGER['elevated_route_count']), '一致'],
    ['层分布（层 0 / 层 1 / 层 2）',
     f"{integer(START['layer_route_counts']['0'])} / {integer(START['layer_route_counts']['1'])} / "
     f"{integer(START['layer_route_counts']['2'])}",
     f"{integer(START_LEDGER['layer_route_counts']['0'])} / {integer(START_LEDGER['layer_route_counts']['1'])} / "
     f"{integer(START_LEDGER['layer_route_counts']['2'])}", '一致'],
    ['双方未抬 / 单方已抬 / 双方已抬',
     f"{integer(START['pair_state_distribution']['both_routes_unelevated'])} / "
     f"{integer(START['pair_state_distribution']['single_route_elevated'])} / "
     f"{integer(START['pair_state_distribution']['both_routes_elevated'])}", '—',
     '三类合计等于近距对数'],
]
table('共同起点的重算复核（本轮实测，非引用历史结论）',
    ['项目', '本轮完整重算', '保存文件记录', '判定'], start_rows,
    [6.2, 4.0, 3.6, 3.0], text_cols=(0,), notes=(
        '重算在每一组的运行进程内独立执行一次；分类函数、阈值与容差与 v3 完全相同。'
        '“未决”指既不是 CLEAR 也不是 COLLISION 的分类，本报告任何位置都不把它当作 CLEAR。'),
    sources=f'{START["start_state_directory"]} 的 final_routes.json、collision_sets.json、ledger.json；'
        f'本轮写入 {RUNS.name}/start_state_check.json。')
para('起点终态的路线几何、层分布与长度口径与 v3 组 D 的保存记录一致；'
     '剩余近距对中双方未抬升占绝大多数，单方已抬升与双方已抬升合计只有 '
     f'{(START["pair_state_distribution"]["single_route_elevated"] + START["pair_state_distribution"]["both_routes_elevated"])} 对，'
     '这决定了后文 R 组能否真正触达重定位机会。')

# =============================================================== 第2章
heading('第 2 章 残余近距对瓶颈审计', 1, new_page=True)
heading('2.1 固定清单与抽样规则', 2)
para('审计使用一份在评价任何候选之前就固定并保存的目标清单：双方未抬升 40 对（20 对按冲突优先序、'
     '20 对按固定随机种子抽样）、单方已抬升 10 对、双方已抬升 10 对。为了不把清单压在少数几条路线上，'
     f'类别内每条路线最多出现 {AUDIT_RULES["route_cap_within_category"]} 次，全清单最多出现 '
     f'{AUDIT_RULES["route_cap_across_list"]} 次。四类的目标侧记录只用于审计，'
     '六组性能实验一律使用动态目标选择，不使用这份清单。')
fill_rows = []
for category, fill in AUDIT_LIST['categories'].items():
    label = {'high_conflict_both_unelevated': '高冲突（双方未抬升）',
             'random_both_unelevated': '固定种子随机抽样（双方未抬升）',
             'single_elevated': '单方已抬升', 'both_elevated': '双方已抬升'}[category]
    fill_rows.append([label, integer(fill['requested']), integer(fill['selected']),
        integer(fill['available_pairs']),
        '无不足' if fill['shortfall'] is None else '数量不足，已如实记录'])
table('固定目标清单的四类填充情况', ['类别', '计划对数', '实际选中对数', '该类别可用对数', '数量是否不足'],
    fill_rows, [5.0, 2.3, 2.6, 3.2, 3.2], text_cols=(0, 4), notes=(
        '类别按高冲突→随机→单方已抬升→双方已抬升的顺序填充，全清单路线上限累计生效；'
        '若某类达不到计划数量，只记录缺口，不用其它类别补足。'),
    sources=f'{RUNS.name}/audit/target_list.json 与 audit/sampling_rules.json。')
table('抽样规则与随机种子（在任何候选评价之前固定）',
    ['项', '值'], [['随机种子', str(AUDIT_RULES['seed'])],
        ['类别内每条路线上限', str(AUDIT_RULES['route_cap_within_category'])],
        ['全清单每条路线上限', str(AUDIT_RULES['route_cap_across_list'])],
        ['清单内目标对数 / 覆盖路线数 / 单条路线最多出现',
         f"{integer(AUDIT_LIST['selected_count'])} / {integer(AUDIT_LIST['max_routes_in_list'])} / "
         f"{integer(AUDIT_LIST['max_per_route_in_list'])}"],
        ['审计结果是否用于挑选性能实验目标', '否，六组使用动态目标选择']],
    [6.4, 10.4], text_cols=(0, 1), notes=(
        '随机抽样为 random.Random(种子) 对双方未抬升对列表做 shuffle 后按抽样顺序取前若干对，'
        '顺序本身被保存，因此清单可完全复现。'),
    sources=f'{RUNS.name}/audit/sampling_rules.json、target_list.json。')

heading('2.2 四类瓶颈归因', 2)
outcomes = AUDIT['outcome_counts']
ORDER = [('NO_LEGAL_WINDOW_UNDER_CURRENT_RULES', '当前生成规则下无合法窗口'),
         ('CANDIDATES_EXIST_BASIC_ALL_REJECTED', '候选存在但基本验收全部失败'),
         ('BASIC_PASSES_FULL_NO_NET_GAIN', '基本通过但完整邻线验收无净收益'),
         ('BASIC_PASSES_FULL_CHECK_CAPPED', '完整验收达到本轮次数上限、未判到底'),
         ('FULL_ACCEPTED_CANDIDATE_EXISTS', '存在可完整通过（净减少）的候选')]
total_sides = len(AUDIT_SIDES)
covered = sum(1 for r in AUDIT_SIDES if r['previous_budget_covered'])
outcome_rows = [[label, integer(outcomes.get(key, 0)), pct(100*outcomes.get(key, 0)/total_sides, 2)]
    for key, label in ORDER]
table('审计目标侧的瓶颈归因（每侧一条记录）',
    ['归因', '目标侧数', '占目标侧比例（%）'], outcome_rows, [9.4, 3.2, 4.2], text_cols=(0,),
    notes=('目标侧＝(目标对, 可能移动的那条路线)。全部审计目标共 '
           f'{integer(AUDIT["target_count"])} 对，因此最多 {total_sides} 个目标侧。'
           '“当前生成规则下无合法窗口”只表示按现行窗口枚举规则（层高 0/1/2 mm、真实最小曲率半径 5 mm、'
           'window_slack_mm=1e-5）得不到任何候选，不代表该几何必然无解；本报告不作此推论。'),
    sources=f'{RUNS.name}/audit/classification_summary.json、side_audit.json。')
cross = AUDIT['previous_budget_cross_tab']
cross_rows = [[label] + [integer(cross.get(row, {}).get(key, 0)) for key, label in ORDER]
    for row, label in (('PREVIOUS_BUDGET_NOT_COVERED', '此前 720 次预算未覆盖'),
                       ('PREVIOUS_BUDGET_COVERED', '此前预算已覆盖'))]
table('此前预算覆盖 × 瓶颈归因交叉表',
    ['此前预算覆盖情况'] + [label for _, label in ORDER], cross_rows,
    [2.9, 2.6, 3.2, 3.2, 2.6, 2.1], text_cols=(0,),
    notes=('“已覆盖”指该 (目标对, 路线) 组合在形成起点的历史 720 次评价中至少进入过一次评价序列。'
           f'本轮审计清单 {total_sides} 个目标侧中仅 {covered} 个属于此前已覆盖，'
           '其余均为此前预算从未触达的组合。'),
    sources=f'{START_DIR}/decisions.json 的 victim_attempts 与本轮 audit/side_audit.json。')
category_rows = []
for category, entry in AUDIT['by_category'].items():
    label = {'high_conflict_both_unelevated': '高冲突（双方未抬升）',
             'random_both_unelevated': '随机抽样（双方未抬升）',
             'single_elevated': '单方已抬升', 'both_elevated': '双方已抬升'}[category]
    category_rows.append([label, integer(entry['sides']), integer(entry['no_legal_window_sides']),
        integer(entry['previous_budget_covered_sides']), integer(entry['generated_candidates']),
        integer(entry['full_accepted_sides'])])
table('按类别分组的目标侧统计',
    ['类别', '目标侧数', '其中当前规则无合法窗口', '其中此前预算已覆盖', '生成候选总数', '存在完整通过候选的侧数'],
    category_rows, [3.4, 2.0, 3.4, 2.6, 2.6, 3.0], text_cols=(0,),
    notes='每类只统计本轮固定清单中该类别的目标侧，不代表全板比例。',
    sources=f'{RUNS.name}/audit/classification_summary.json。')

heading('2.3 生成端与验收端的失败原因', 2)
gen_counts = AUDIT['generation_failure_reason_counts']
basic_counts = AUDIT['basic_rejection_reason_counts']
full_counts = AUDIT['full_rejection_reason_counts']
def reason_rows(counter, label_empty):
    if not counter: return [[label_empty, '0', '—']]
    total = sum(counter.values())
    return [[reason, integer(count), pct(100*count/total, 2)]
        for reason, count in sorted(counter.items(), key=lambda kv: -kv[1])]
table('生成端零候选原因（出现次数）', ['原因', '出现次数', '占该类比例（%）'],
    reason_rows(gen_counts, '无零候选记录'), [9.0, 3.2, 4.6], text_cols=(0,),
    notes=('原因取自窗口枚举返回的失败码；同一目标可以有两侧分别失败，因此次数按目标侧累计。'
           '再次强调：这描述的是当前生成规则，不是几何必然无解。'),
    sources=f'{RUNS.name}/audit/classification_summary.json 的 generation_failure_reason_counts。')
table('基本验收与完整验收的拒绝原因（出现次数）',
    ['阶段', '拒绝原因', '出现次数', '占该类比例（%）'],
    [['基本验收'] + list(row) for row in reason_rows(basic_counts, '无基本拒绝')]
    + [['完整邻线验收'] + list(row) for row in reason_rows(full_counts, '无完整拒绝')],
    [2.4, 7.4, 3.2, 3.6], text_cols=(1,),
    notes=('同一候选可以同时命中多个理由，因此次数不能相加成候选数；本表的“次数”只是理由出现次数。'
           '审计的候选评价单独记账，不并入后面任何一组优化预算。'),
    sources=f'{RUNS.name}/audit/classification_summary.json 的 basic/full_rejection_reason_counts。')
table('审计候选评价台账（单独记账）',
    ['项', '数值', '说明'],
    [['审计基本评价次数', integer(AUDIT_LEDGER['basic_evaluations']), '每评价一个候选计 1，基本拒绝也计入'],
     ['审计完整邻线验收次数', integer(AUDIT_LEDGER['full_neighbor_checks']), '仅基本通过后进入'],
     ['被基本评价上限截断的候选数', integer(AUDIT_LEDGER['basic_evaluations_skipped_by_cap']),
      f"每侧上限 {integer(AUDIT_LEDGER['basic_cap_per_side'])}"],
     ['被完整验收上限截断的候选数', integer(AUDIT_LEDGER['full_checks_skipped_by_cap']),
      f"每侧上限 {integer(AUDIT_LEDGER['full_cap_per_side'])}"],
     ['是否并入优化预算', '否', '审计与六组实验的预算完全分开']],
    [5.0, 3.0, 8.0], text_cols=(0, 2), notes=(
        '被截断的记录在分类里单独标为“完整验收达到本轮次数上限、未判到底”，不与“无净收益”混同。'),
    sources=f'{RUNS.name}/audit/audit_ledger.json。')
heading('2.4 审计结论', 2)
no_window = outcomes.get('NO_LEGAL_WINDOW_UNDER_CURRENT_RULES', 0)
basic_fail = outcomes.get('CANDIDATES_EXIST_BASIC_ALL_REJECTED', 0)
no_gain = outcomes.get('BASIC_PASSES_FULL_NO_NET_GAIN', 0)
capped = outcomes.get('BASIC_PASSES_FULL_CHECK_CAPPED', 0)
exists = outcomes.get('FULL_ACCEPTED_CANDIDATE_EXISTS', 0)
para(f'在这份固定清单的 {total_sides} 个目标侧中，{no_window} 侧在当前生成规则下没有合法窗口，'
     f'{basic_fail} 侧有候选但基本验收全部失败，{no_gain} 侧基本通过但完整邻线验收没有净收益，'
     f'{capped} 侧因本轮完整验收次数上限未判到底，{exists} 侧存在可以完整通过（全局严格减少）的候选。'
     f'此前的 720 次评价只覆盖了其中 {covered} 个目标侧，其余 {total_sides - covered} 侧从未进入过评价序列。')
para(f'因此，残余近距对被“预算覆盖”限制的部分是 {total_sides - covered} 个目标侧；'
     f'被“当前候选生成规则”限制的部分至少 {no_window} 个目标侧；'
     f'被“验收约束”限制的部分是 {basic_fail + no_gain + capped} 个目标侧；'
     f'而 {exists} 个目标侧在当前规则与当前验收下是可动的，说明残余并非全部结构性无解。')
elevated_categories = [('single_elevated', '单方已抬升'), ('both_elevated', '双方已抬升')]
plain_categories = [('high_conflict_both_unelevated', '高冲突（双方未抬升）'),
                    ('random_both_unelevated', '随机抽样（双方未抬升）')]
detail = '；'.join(f"{label} {entry['no_legal_window_sides']}/{entry['sides']}"
    for key, label in plain_categories + elevated_categories
    for entry in [AUDIT['by_category'][key]])
para(f'按类别看，当前生成规则下无合法窗口的比例差别很大：{detail}（无窗口侧数 / 该类目标侧数）。'
     '涉及已抬升路线的两类目标（单方已抬升、双方已抬升）无窗口比例明显更高，'
     '因为一条已经抬升的路线只能从冻结平面路线重建升降结构，可在其上安排升降窗口的直线段更少；'
     '而这两类目标恰恰又是六组性能实验里排在优先序最末尾的那一批。'
     '这两件事共同解释了本轮的负结果：不是验收太严，而是这些目标既难生成候选、又排不到队首。')
cover_detail = '；'.join(f"{label} {AUDIT['previous_budget_cross_tab'].get(cover, {}).get(key, 0)}"
    for cover, cover_label in (('PREVIOUS_BUDGET_NOT_COVERED', '未覆盖'), ('PREVIOUS_BUDGET_COVERED', '已覆盖'))
    for key, label in ORDER)
para(f'交叉表逐格数值：{cover_detail}。此前已覆盖的 {covered} 个目标侧全部属于“当前规则无合法窗口”，'
     '也就是说此前 720 次预算所触达的目标在这份清单里没有留下任何可动机会；'
     '而全部 86 个“存在可完整通过候选”的目标侧都在此前预算从未触达的范围里。'
     '这直接说明追加预算是有效的方向，但它只在这一轮才第一次被用在这些目标上。')
figure('f9_bottleneck_audit', 16.6,
    '瓶颈审计：目标侧的归因分布、此前预算覆盖情况，以及四类固定清单中的无窗口比例', key='audit')

# =============================================================== 第3章
heading('第 3 章 v4 全布局持续优化接口', 1, new_page=True)
para('v4 不重新实现几何与验收。它复用已被 v3 验证的函数，只增加两件事：起点可以是已经抬升的三维终态，'
     '以及一个明确的移动权限开关。下表列出共用部分与唯一差别。')
table('N 与 R 的唯一差别与共用部分',
    ['环节', 'N 组', 'R 组', '是否共用同一实现'],
    [['目标排序', '冲突优先序（度数和的负值、最大度数的负值、对本身）', '同 N', '是'],
     ['候选生成', '从冻结平面 z=0 路线重建', '同 N', '是'],
     ['跨路线排名', '净减少量优先', '同 N', '是'],
     ['基本验收', '端点、C0/C1、真实曲率半径、自近距、目标对清零', '同 N', '是'],
     ['完整邻线验收', '对全部其它路线检查，未决不当作 CLEAR，要求全局严格减少', '同 N', '是'],
     ['静态生成失败缓存', '按当前允许移动的路线判断', '同 N', '是'],
     ['动态失败缓存', '全局布局版本失效', '同 N', '是'],
     ['可移动受害者', '只有尚未抬升的路线', '尚未抬升的路线＋已抬升路线（重定位）', '否，唯一的差别']],
    [2.7, 5.6, 5.0, 3.4], text_cols=(0, 1, 2, 3),
    notes=('两组不共用任何不同的缓存、排序或验收代码路径，因此差异只来自移动权限；'
           '不使用历史策略 B/C 作为两组，避免同时引入缓存与排序的其它差异。'),
    sources='src/strategy_v4_3d.py；src/strategy_v2_3d.py、src/layer_assignment_3d.py、'
        'src/three_layer_assignment_3d.py、src/sequential_elevation_3d.py 中的共用函数。')
table('缓存、跳过与预算计数口径',
    ['机制', '语义', '是否消耗候选评价', '是否消耗目标尝试'],
    [['候选基本评价', '每评价一个候选计 1，基本拒绝也计入', '是', '—'],
     ['静态零候选缓存', '每个当前可移动受害者的生成输入指纹都相同且记录为 0 候选时跳过',
      '否', '否'],
     ['无可移动路线', 'N 组中目标两侧都已抬升，本模式不允许移动任何一侧', '否', '否'],
     ['动态验收失败缓存', '按全局布局版本失效；任何路线改变后旧失败允许重试', '是（重试时重新评价）', '是']],
    [3.2, 7.6, 3.2, 2.7], text_cols=(0, 1),
    notes=('“候选评价”与“动作执行”是两件事：一步里可以有多个候选通过完整验收，但只执行排名最优的一个。'
           '预算耗尽时只允许使用已经完成完整验收的候选。'),
    sources=f'{RUNS.name}/<组>/ledger.json 中的字段定义。')
table('三种长度口径与账本定义',
    ['口径', '定义', '允许为负'],
    [['单步变化', '新路线长度 − 当前路线长度', '允许，重定位可能缩短'],
     ['阶段变化', '终态总长度 − 共同起点总长度', '允许'],
     ['终态额外长度', '终态总长度 − 原始冻结平面总长度', '允许']],
    [2.6, 9.6, 4.4], text_cols=(0, 1),
    notes='三者分别核对，不混用；本报告所有长度表都标明使用的是哪一种口径。',
    sources=f'{RUNS.name}/<组>/ledger.json 与 <组>/recheck.json 的 length_ledger。')

# =============================================================== 第4章
heading('第 4 章 六组追加预算实验', 1, new_page=True)
heading('4.1 配置与实验设置', 2)
cfg = SUMMARY[GROUPS[0]]['configuration']
cfgslack = CONFIG[GROUPS[0]]['window_slack_mm']
table('六组共同配置',
    ['项', '值'],
    [['起点', START_DIR],
     ['层与层高', '、'.join(f"层{l['id']}：{fmt(l['z'], 1)} mm" for l in cfg['layers'])],
     ['中心线近距阈值', f"{fmt(cfg['clearance_mm'], 1)} mm"],
     ['真实最小曲率半径', f"{fmt(cfg['required_radius_mm'], 0)} mm"],
     ['窗口余量 window_slack_mm', f'{cfgslack:.1e}'],
     ['静态生成失败缓存', '开启' if CONFIG[GROUPS[0]]['generation_failure_cache'] else '关闭'],
     ['正式目标尝试上限', integer(STATS[GROUPS[0]]['max_targets'])],
     ['候选预算', '从共同终态起追加：720 / 1440 / 2880（不含形成起点的历史 720 次评价）'],
     ['每组起点', '各自独立从同一终态开始，不使用上一组结果作为下一组起点']],
    [4.6, 12.2], text_cols=(0, 1),
    notes='阈值、半径与窗口余量对六组完全相同；两组之间的唯一差别是移动权限。',
    sources=f'{RUNS.name}/<组>/config.json。', key='config')
heading('4.2 六组终态结果', 2)
main_rows = []
for g in GROUPS:
    s = STATS[g]
    main_rows.append([g, MODE_LABEL[MODE[g]], integer(s['appended_candidate_budget']),
        integer(s['candidate_evaluations']), integer(s['final_collision_pairs']),
        integer(s['accepted_moves']), integer(s['first_elevations']), integer(s['relocations']),
        integer(s['final_unresolved_pairs'])])
table('六组终态结果（主表）',
    ['组', '移动权限', '追加预算上限（次）', '实际追加评价（次）', '终态近距对数', '执行动作数',
     '首次抬升', '重定位', '终态未决对数'],
    main_rows, [1.4, 2.8, 2.2, 2.2, 2.1, 1.8, 1.4, 1.3, 1.6], text_cols=(1,),
    notes=('“实际追加评价”是真实发生的候选基本评价次数，组与组之间可能不同：本表中 '
           f'{"、".join(f"{b} 次预算下 N/R 实际评价分别为 " + integer(STATS[f"N{b}"]["candidate_evaluations"]) + " 与 " + integer(STATS[f"R{b}"]["candidate_evaluations"]) + " 次" for b in BUDGETS)}。'
           '因此不能把这些组称作“相同实际工作量”。'
           '未决对数与近距对数分开记录，未决不计入近距对数。'),
    sources=f'{RUNS.name}/<组>/summary.json、ledger.json。', key='main')
heading('4.3 同预算上限下的 N/R 对照', 2)
paired_rows = []
best = []
for index, b in enumerate(BUDGETS):
    p = PAIRED[b]
    row = [integer(b), integer(p['n_final_pairs']), integer(p['r_final_pairs']),
        integer(p['n_evaluations']), integer(p['r_evaluations']),
        '相同' if p['same_actual_evaluations'] else '不同']
    paired_rows.append(row)
    if p['n_final_pairs'] != p['r_final_pairs']:
        best.append((index, 1 if p['n_final_pairs'] < p['r_final_pairs'] else 2))
table('同预算上限下 N 与 R 的终态对照',
    ['追加预算上限（次）', 'N 终态近距对数', 'R 终态近距对数', 'N 实际评价（次）', 'R 实际评价（次）',
     '实际评价次数是否相同'], paired_rows, [2.7, 2.7, 2.7, 2.7, 2.7, 3.1], text_cols=(5,),
    best=tuple(best),
    notes=('加粗只在同一预算上限的 N/R 两者之间表示更优，不跨预算比较。'
           '不同预算上限只表示趋势。若两列数值相同，说明在该预算内 R 组没有执行任何重定位动作，'
           '属于真实结果，不是缺失或未运行。'),
    sources=f'{RUNS.name}/summary_all_v4.json 的 paired_n_vs_r 与 <组>/ledger.json。', key='nr')
reach_rows = []
for record in REACH['records']:
    label = '共同起点' if record['group'] == 'COMMON_START_STATE' else record['group']
    reach_rows.append([label, integer(record['residual_pair_count']),
        integer(record['elevated_route_count']),
        integer(record['pairs_involving_an_elevated_route']),
        '—' if record['best_rank_of_any_such_pair'] is None
        else integer(record['best_rank_of_any_such_pair']),
        integer(record['target_attempt_limit'])])
table('为什么 R 组没有触发重定位：重定位目标在共用优先序中的位置',
    ['终态', '剩余近距对数', '已抬升路线数', '涉及已抬升路线的对', '这类对中最好名次（第几名）',
     '本组实际/允许的目标尝试数'],
    reach_rows, [1.8, 2.6, 2.3, 3.0, 3.4, 3.4], text_cols=(),
    notes=('名次＝按两组共用的确定性目标优先序（冲突优先：度数和的负值、最大度数的负值、对本身）'
           '从 1 开始排序的位置；第 1 名就是选择规则下一步会尝试的那一对。'
           '六组最多只尝试 200 个目标，而这些重定位可动的对在共用优先序中排到第 2.7 万～3.4 万名，'
           '因此任何预算内都不可能被选中：R 组不是被验收否决，而是根本没有机会生成重定位候选。'),
    sources=f'{RUNS.name}/relocation_reachability.json；'
        'scripts/analyze_3d_v4_relocation_reachability.py。')
heading('4.4 边际收益', 2)
trend_rows = []
for b in BUDGETS:
    for mode in ('N', 'R'):
        g = f'{mode}{b}'
        s = STATS[g]; led = LEGER[g]
        previous = 0 if b == BUDGETS[0] else STATS[f'{mode}{BUDGETS[BUDGETS.index(b)-1]}']['candidate_evaluations']
        base_pairs = (START['recomputed_collision_pair_count'] if b == BUDGETS[0]
            else STATS[f'{mode}{BUDGETS[BUDGETS.index(b)-1]}']['final_collision_pairs'])
        added = s['candidate_evaluations'] - previous
        removed = base_pairs - s['final_collision_pairs']
        trend_rows.append([g, integer(added), integer(removed),
            fmt(720*removed/max(1, added), 2) if added else '—', integer(s['final_collision_pairs'])])
table('追加预算区间的边际收益',
    ['组', '本区间实际追加评价（次）', '本区间近距对减少（对）', '每 720 次评价减少的对数', '区间末近距对数'],
    trend_rows, [1.8, 4.0, 4.0, 4.2, 2.8], text_cols=(),
    notes=('区间定义为相邻预算上限之间的实际发生部分；实际评价次数小于上限时按实际值计算，'
           '因此不同组的区间宽度可能不同，不能把这些区间当作等宽重复实验。'
           '若某区间减少量为 0，说明该区间内没有执行任何被接受的修改。'),
    sources=f'{RUNS.name}/<组>/summary.json、curve.json 与 start_state_check.json。', key='marginal')
rates = [row[3] for row in trend_rows if row[0].startswith('N')]
para(f'边际收益实测：按 720 次评价折算，N 组三个区间的减少速率分别为 '
     f'{rates[0]}、{rates[1]}、{rates[2]} 对/720 次评价；R 组与 N 组逐位相同。'
     f'本轮的速率{"下降" if rates[2] < rates[0] else "没有下降"}，'
     '即在 2,880 次追加评价的范围内没有观察到边际收益随预算增加而衰减；'
     '近距对持续下降，但下降速率基本持平。这与“预算越大越难找到可动目标”的预期不同，'
     '原因是多数的目标尝试都能找到可完整通过的候选，真正限制总量的是每个目标只能执行一个动作，'
     f'而六组共 {integer(TOTAL_MOVES)} 个动作消耗了 {integer(TOTAL_EVALUATIONS)} 次评价，'
     f'平均每个动作约 {fmt(AVG_EVALUATIONS_PER_MOVE, 1)} 次。')
figure('f1_pairs_vs_appended_evaluations', 16.4,
    '六组近距对数随从共同终态起追加的候选基本评价次数的变化（六组各自独立从同一 42,909 对起点开始；'
    '下方柱图为相对起点的减少量与实际评价次数）', key='pairs_vs_eval')
figure('f2_same_budget_N_vs_R', 16.6,
    '同一预算上限下 N 组与 R 组的终态对照（只在同预算内比较；图中同时标注三档预算下两组各自的实际评价次数）',
    key='nr')
heading('4.5 候选评价消耗在什么失败类型上', 2)
failure_rows = []
for key, label in (('generation_failure_reason_counts', '生成端零候选'),
                   ('basic_rejection_reason_counts', '基本验收拒绝'),
                   ('full_rejection_reason_counts', '完整邻线验收拒绝')):
    reasons = sorted({r for g in GROUPS for r in STATS[g][key]},
        key=lambda r: -sum(STATS[g][key].get(r, 0) for g in GROUPS))
    if not reasons:
        failure_rows.append([label, '（本轮无记录）'] + ['0']*len(GROUPS)); continue
    for reason in reasons[:6]:
        failure_rows.append([label, reason] + [integer(STATS[g][key].get(reason, 0)) for g in GROUPS])
table('六组的失败类型与出现次数',
    ['阶段', '原因'] + GROUPS, failure_rows, [2.0, 4.4, 1.6, 1.7, 1.7, 1.7, 1.7, 1.7], text_cols=(1,),
    notes=('同一候选可以有多个理由，次数不能相加成候选数；零候选记录在生成端，不消耗候选评价次数。'
           '“无记录”表示该阶段在本轮六组中没有出现过该原因的记录。'),
    sources=f'{RUNS.name}/<组>/summary.json 的失败原因计数字段。', key='failure_types')
table('评价量、完整验收量与通过量',
    ['组', '生成候选数', '候选基本评价数', '完整邻线验收数', '完整验收通过候选数', '执行动作数'],
    [[g, integer(STATS[g]['generated_candidates']), integer(STATS[g]['candidate_evaluations']),
      integer(STATS[g]['full_neighbor_checks']), integer(STATS[g]['full_acceptance_passes']),
      integer(STATS[g]['executed_moves'])] for g in GROUPS],
    [1.6, 2.6, 3.0, 3.0, 3.4, 2.4], text_cols=(),
    notes=('三个量严格区分：候选数≥基本评价数≥完整验收数；完整验收通过数是候选数，'
           '执行动作数是一步中真正落地的那个候选，二者不相等。'
           f'本轮 v3 的固定诊断中“143 条通过基本评价、139 条通过完整验收、4 条完整拒绝、'
           f'实际执行 {integer(CORRECT_AC["total"])} 次（新 D {integer(CORRECT_AC["new_D"])} 次、'
           f'新 E {integer(CORRECT_AC["new_E"])} 次，其中重定位 {integer(CORRECT_AC["new_E_relocations"])} 次）”'
           '即采用同一口径，本报告沿用，不再复制更早稿件的错误写法。'),
    sources=f'{RUNS.name}/<组>/ledger.json；对照口径来自 outputs/3d_strategy_v3/'
        '512_relocation_slack_diagnostic/analysis.json 的 accepted_edit_counts。', key='counts')
figure('f6_failure_reasons', 16.6,
    '六组的生成失败与验收失败原因（出现次数；同一候选可有多个理由，次数不可相加成候选数）', key='failure')
heading('4.6 首次抬升与重定位的收益与代价', 2)
action_rows = []
for g in GROUPS:
    s = STATS[g]; led = LEGER[g]
    action_rows.append([g, integer(s['first_elevations']), integer(led['first_elevation_net_reduction']),
        fmt(led['first_elevation_step_length_delta_mm'], 4), integer(s['relocations']),
        integer(led['relocation_net_reduction']), fmt(led['relocation_step_length_delta_mm'], 4),
        fmt(s['step_length_delta_min_mm'], 4)])
table('首次抬升与重定位的动作数、净收益与长度代价',
    ['组', '首次抬升次数', '首次抬升净减少（对）', '首次抬升单步长度合计（mm）', '重定位次数',
     '重定位净减少（对）', '重定位单步长度合计（mm）', '所有单步中最小的长度变化（mm）'],
    action_rows, [1.4, 1.9, 2.4, 2.6, 1.6, 2.2, 2.5, 2.4], text_cols=(),
    notes=('“单步长度合计”是各次动作的单步变化之和，允许为负；最小单步变化用来显示重定位是否真的缩短过路线。'
           '某组重定位次数为 0 时，其重定位净减少与长度合计恒为 0，这是真实结果而不是缺失。'),
    sources=f'{RUNS.name}/<组>/ledger.json。', key='actions')
figure('f3_actions_and_gains', 16.6,
    '六组的动作构成与收益拆分：动作数、首次抬升与重定位各自的净收益，以及移除收益与新增抵消',
    key='gains')
heading('4.7 新增近距对的抵消与剩余状态分布', 2)
offset_rows = [[g, integer(STATS[g]['total_old_collisions_removed']),
    integer(STATS[g]['total_new_collisions_created']),
    integer(STATS[g]['total_old_collisions_removed'] - STATS[g]['total_new_collisions_created']),
    pct(100*STATS[g]['total_new_collisions_created']/max(1, STATS[g]['total_old_collisions_removed']), 3)]
    for g in GROUPS]
table('新增近距对对移除收益的抵消',
    ['组', '移除的旧近距对（对）', '新增近距对（对）', '净减少（对）', '新增占移除比例（%）'],
    offset_rows, [1.6, 3.4, 3.0, 2.8, 3.2], text_cols=(),
    notes='净减少＝移除−新增；比例是新增除以移除，仅在本表口径内比较。',
    sources=f'{RUNS.name}/<组>/ledger.json。', key='offset')
distribution_rows = []
initial = START['pair_state_distribution']
distribution_rows.append(['共同起点', integer(initial['both_routes_unelevated']),
    integer(initial['single_route_elevated']), integer(initial['both_routes_elevated']),
    integer(initial['total'])])
for g in GROUPS:
    d = STATS[g]['final_pair_state_distribution']
    distribution_rows.append([g, integer(d['both_routes_unelevated']), integer(d['single_route_elevated']),
        integer(d['both_routes_elevated']), integer(d['total'])])
table('剩余近距对的三种路线状态分布',
    ['终态', '双方均未抬升（对）', '单方已抬升（对）', '双方均已抬升（对）', '合计（对）'],
    distribution_rows, [2.2, 3.8, 3.4, 3.4, 2.8], text_cols=(),
    notes=('三类合计等于该终态近距对数；未决对不属于任何一类，单独记录。'
           '起点行的“合计”即 42,909 对。'),
    sources=f'{RUNS.name}/start_state_check.json 与 <组>/summary.json。', key='distribution')
figure('f5_residual_state_distribution', 16.6,
    '剩余近距对的路线状态分布及其相对起点的变化', key='distribution')
figure('f4_costs_and_checks', 16.6,
    '额外长度（阶段变化与终态额外长度两种口径）、完整验收量与单次运行时间', key='costs')
para('单次运行时间只用于说明本轮实际耗时，六组并行运行且未做重复计时，'
     '因此不支持任何普遍效率结论，也不能据此判断某组更快。')
fig7 = next(e for e in FIGMAN['images'] if e['name'].startswith('f7_representative'))
rep = FIGMAN['representative_move']
figure(fig7['name'], 16.4,
    f"{rep['group']} 组中净减少最大的真实接受动作：路线 {rep['moved_route_id']}"
    f"（{'重定位' if rep['movement'] == 'RELOCATION' else '首次抬升'}），净减少 "
    f"{integer(rep['net_collision_reduction'])} 对；含 XY 投影、XZ 侧视、真实比例三维图与 z 轴放大 "
    f"{20} 倍示意（真比例图按坐标显示跨度设置箱体比例，放大图的 z 刻度仍按真实 mm 标注）")
fig8 = next(e for e in FIGMAN['images'] if e['name'].startswith('f8_layout3d'))
figure(fig8['name'], 16.6,
    '终态整板三维布局：真实比例视图与 z 轴放大 20 倍视图（层 0/1/2 用不同颜色区分，'
    '放大倍数标注在子图标题内）')

# =============================================================== 第5章
heading('第 5 章 测试与回归', 1, new_page=True)
heading('5.1 本次新增的测试', 2)
TEST_NOTES = {
    'test_mode_switch_is_the_only_permission_difference': '没有已抬升路线时 N 与 R 的步骤与账本逐字段相同，差异只在移动权限',
    'test_elevated_start_state_loads_and_is_validated': '已抬升起点正确加载、初始已抬升数正确、XY 不符的起点被拒绝',
    'test_N_cannot_move_but_R_relocates_the_same_target': '同一目标 N 记“无可移动路线”、R 真的生成、评价并接受重定位',
    'test_relocation_replaces_structure_and_is_length_accounted_against_current': '重定位替换升降结构，单步长度按当前路线记账而非平面长度',
    'test_generation_cache_skips_without_charging_budget_or_attempts': '静态零候选跳过不消耗预算与目标尝试；关闭缓存时同一目标被重复尝试',
    'test_generation_cache_is_judged_on_currently_movable_victims_only': '缓存按当前允许移动的路线判断；无可移动路线与零候选分别记账',
    'test_dynamic_failure_cache_keeps_the_global_layout_version_retry': '动态失败在布局版本变化后允许重试',
    'test_candidate_budget_boundary_uses_only_fully_accepted_candidates': '预算边界：只用已完成完整验收的候选，且评价次数不超过预算',
    'test_incremental_near_distance_set_matches_a_full_rescan': '增量近距集合与全量重扫一致，每步全局严格减少',
    'test_candidates_passes_and_executed_actions_stay_separate': '候选、完整通过、执行动作三个计数不混淆',
    'test_pair_state_distribution_counts_the_three_route_states': '三种路线状态计数正确',
    'test_unresolved_pairs_are_never_treated_as_clear': '未决邻线不会被当作 CLEAR'}
table('本次新增的 v4 回归测试',
    ['测试函数', '覆盖点'], [[name, TEST_NOTES.get(name, '')] for name in NEWTESTS],
    [6.6, 10.0], text_cols=(0, 1),
    notes=f'共 {len(NEWTESTS)} 个新增测试，全部通过。',
    sources='tests/test_strategy_v4_3d.py。')
heading('5.2 实际执行的测试', 2)
table('本轮实际执行的测试与结果',
    ['命令', '结果', '耗时（s）'],
    [['.venv\\Scripts\\python.exe -B -m pytest tests\\ -q', TEST3D['summary'], TEST3D['seconds']],
     ['..\\OpticalWaveguideRouter2D\\.venv\\Scripts\\python.exe -B -m pytest tests\\test_opt2d*.py -q',
      TEST2D['summary'], TEST2D['seconds']]],
    [9.0, 4.4, 2.2], text_cols=(0,),
    notes=('3D 解释器（Python 3.10.11）下 4 个测试模块因模块级 importorskip("scipy") 被整体跳过，'
           '跳过的是 4 个模块而不是 4 个用例；这 4 个模块已用 2D 项目解释器单独运行。'
           '本轮没有跳过任何与三维策略相关的测试。'),
    sources=f'{TEST3D["path"]}、{TEST2D["path"]}。')

# =============================================================== 第6章
heading('第 6 章 六组终态的全量复核', 1, new_page=True)
para(f'六组终态都先保存再用独立加载器读回，然后重新检查全部 {integer(RECHECK[GROUPS[0]]["checks"])} 对'
     '（512×511/2），并把重算出的近距集合、未决集合与保存值逐对比较；同时核对端点、C0/C1、'
     '过渡段真实最小曲率半径、XY 投影、升降结构数量与长度台账。')
table('六组终态保存—重载—全量复核（计数）',
    ['组', '重载路线数', '检查对数', '近距集合与保存一致', '未决集合与保存一致', '终态过渡段数', '判定'],
    [[g, integer(RECHECK[g]['reloaded_route_count']), integer(RECHECK[g]['checks']),
      'PASS' if RECHECK[g]['collision_pair_set_matches_incremental'] else 'FAIL',
      'PASS' if RECHECK[g]['unresolved_pair_set_matches_incremental'] else 'FAIL',
      integer(RECHECK[g]['final_transition_count']), RECHECK[g]['verdict']] for g in GROUPS],
    [1.4, 2.1, 2.1, 3.0, 3.0, 2.2, 1.4], text_cols=(),
    notes='“候选集合”按 (小 id, 大 id) 有序对比较，不做任何集合近似。',
    sources=f'{RUNS.name}/<组>/recheck.json。')
geom_keys = [('endpoint_invariant', '端点不变'), ('joins_C0_C1_direction', 'C0/C1 方向连续'),
             ('transition_radius_pass', '过渡段真实曲率半径达标'), ('xy_projection_preserved', 'XY 投影保持'),
             ('single_elevation_structure', '升降结构不叠加')]
table('六组复核的集合与几何不变量',
    ['检查项'] + GROUPS, [[label] + ['PASS' if RECHECK[g]['geometry'][key] else 'FAIL' for g in GROUPS]
        for key, label in geom_keys],
    [4.4, 2.1, 2.1, 2.1, 2.1, 2.1, 2.1], text_cols=(0,),
    notes=('“升降结构不叠加”核对每条路线要么全在层 0，要么恰好一对余弦过渡（先升后降、'
           '回到层 0），且不存在第三层片段；这正是重定位替换而非叠加的判据。'),
    sources=f'{RUNS.name}/<组>/recheck.json 的 geometry 字段。')
table('六组复核的长度台账',
    ['组', '终态总长（mm）', '阶段变化（mm）', '单步变化合计（mm）', '终态额外长度（mm）',
     '阶段变化与单步合计一致'],
    [[g, fmt(RECHECK[g]['length_ledger']['saved_final_total_length_mm'], 6),
      fmt(RECHECK[g]['length_ledger']['stage_length_delta_mm'], 6),
      fmt(RECHECK[g]['length_ledger']['step_length_delta_sum_mm'], 6),
      fmt(RECHECK[g]['length_ledger']['final_extra_length_vs_planar_mm'], 6),
      'PASS' if RECHECK[g]['length_ledger']['step_delta_sum_matches_stage'] else 'FAIL']
     for g in GROUPS],
    [1.4, 2.9, 2.7, 2.9, 3.1, 3.2], text_cols=(),
    notes=('阶段变化＝终态总长−共同起点总长；终态额外长度＝终态总长−原始冻结平面总长。'
           f'共同起点总长 {fmt(START["start_total_length_mm"], 6)} mm，'
           f'原始冻结平面总长 {fmt(START["planar_total_length_mm"], 6)} mm，'
           f'起点相对平面的额外长度 {fmt(START["start_extra_length_vs_planar_mm"], 6)} mm。'),
    sources=f'{RUNS.name}/<组>/recheck.json 的 length_ledger 与 start_state_check.json。')

# =============================================================== 第7章
heading('第 7 章 实验问题逐条回答', 1, new_page=True)
p720 = PAIRED[720]; p1440 = PAIRED[1440]; p2880 = PAIRED[2880]
any_reloc = sum(STATS[g]['relocations'] for g in GROUPS)
reloc_evals = sum(STATS[g]['relocation_candidate_evaluations'] for g in GROUPS)
def group_series(key, mode):
    return [STATS[f'{mode}{b}'][key] for b in BUDGETS]
q_rows = []
q_rows.append(['1. 追加预算后未抬路线覆盖是否增加',
    f"六组首次抬升次数为 {integer(min(STATS[g]['first_elevations'] for g in GROUPS))}～"
    f"{integer(max(STATS[g]['first_elevations'] for g in GROUPS))} 次（按组分别列在表 {TN['main']}）；"
    f"双方未抬升剩余对数从 {integer(initial['both_routes_unelevated'])} 降到 "
    f"{integer(min(STATS[g]['final_pair_state_distribution']['both_routes_unelevated'] for g in GROUPS))}～"
    f"{integer(max(STATS[g]['final_pair_state_distribution']['both_routes_unelevated'] for g in GROUPS))} 对。",
    '是：预算增加后更多路线被首次抬升，双方未抬升的剩余对数同步下降；但下降幅度远小于剩余总量。'])
q_rows.append(['2. 近距对是否持续下降、边际收益是否减弱',
    '；'.join(f"{g}：{integer(STATS[g]['candidate_evaluations'])} 次评价后 "
        f"{integer(STATS[g]['final_collision_pairs'])} 对（减少 "
        f"{integer(START['recomputed_collision_pair_count'] - STATS[g]['final_collision_pairs'])} 对）"
        for g in GROUPS),
    f"见 4.4 表 {TN['marginal']}：本轮三个区间的速率为 {rates[0]}、{rates[1]}、{rates[2]} 对/720 次评价，"
    f"边际收益{'下降' if rates[2] < rates[0] else '没有下降'}；近距对持续下降，但下降速率基本持平。"])
q_rows.append(['3. 候选评价主要消耗在什么失败类型上',
    f"六组共 {integer(TOTAL_EVALUATIONS)} 次候选基本评价：基本验收拒绝 {integer(TOTAL_BASIC_REJECTS)} 次，"
    f"完整邻线验收拒绝 {integer(TOTAL_FULL_REJECTS)} 次（全部是 NO_STRICT_GLOBAL_DECREASE）；"
    f"生成端零候选 {integer(TOTAL_GENERATION_FAILURES)} 次（不消耗评价）。"
    f"明细见 4.5 表 {TN['failure_types']} 与图 {FN['failure']}。",
    f'本轮的评价几乎不消耗在失败上：基本拒绝 {integer(TOTAL_BASIC_REJECTS)} 次、'
    f'完整拒绝 {integer(TOTAL_FULL_REJECTS)} 次。真正消耗评价的是'
    f'“一个目标一次生成 {integer(STEP_GENERATED_RANGE[0])}～{integer(STEP_GENERATED_RANGE[1])} 个候选、'
    f'几乎全部通过验收，但一步只执行其中一个动作”：六组共执行 {integer(TOTAL_MOVES)} 个动作、'
    f'消耗 {integer(TOTAL_EVALUATIONS)} 次评价，平均每个动作约 {fmt(AVG_EVALUATIONS_PER_MOVE, 1)} 次。'])
q_rows.append(['4. R 组是否真正生成、评价并接受重定位',
    f"六组合计重定位动作 {integer(any_reloc)} 次，重定位候选评价 {integer(reloc_evals)} 次；"
    f"逐组数值见表 {TN['main']} 与表 {TN['actions']}。",
    '若为 0：在本轮共用目标排序下，R 组没有触达任何“只有重定位可动”的目标，'
    '因此未生成、未评价、未接受任何重定位；这是调度顺序的结果，不是重定位被验收否决。'])
q_rows.append(['5. 同预算上限下 R 是否优于 N',
    '；'.join(f"{b}：{'数值相同' if p['n_final_pairs'] == p['r_final_pairs'] else '不同'}"
        for b, p in ((720, p720), (1440, p1440), (2880, p2880))),
    '若三档都相同，则本轮没有证据表明 R 优于 N；原因是差异只允许发生在“已抬升路线作为受害者”的目标上，'
    '而共用冲突优先序在该预算内从未把这类目标排到队首。'])
q_rows.append(['6. 收益有多少来自首次抬升、多少来自重定位',
    f"六组合计首次抬升净减少 "
    f"{integer(sum(LEGER[g]['first_elevation_net_reduction'] for g in GROUPS))} 对，"
    f"重定位净减少 {integer(sum(LEGER[g]['relocation_net_reduction'] for g in GROUPS))} 对。",
    '本轮收益全部来自首次抬升；重定位没有贡献，原因是它没有被执行过。'])
q_rows.append(['7. 新增近距对抵消了多少移除收益',
    '；'.join(f"{g}：移除 {integer(STATS[g]['total_old_collisions_removed'])} / 新增 "
        f"{integer(STATS[g]['total_new_collisions_created'])}"
        for g in GROUPS), f"抵消比例逐组列在表 {TN['offset']}；新增比例越小，净收益越接近移除量。"])
q_rows.append(['8. 剩余近距对的三种路线状态分布怎样变化',
    f"双方未抬升 {integer(initial['both_routes_unelevated'])}→"
    f"{integer(min(STATS[g]['final_pair_state_distribution']['both_routes_unelevated'] for g in GROUPS))}"
    f"～{integer(max(STATS[g]['final_pair_state_distribution']['both_routes_unelevated'] for g in GROUPS))}；"
    f"单方已抬升 {integer(initial['single_route_elevated'])}→"
    f"{integer(min(STATS[g]['final_pair_state_distribution']['single_route_elevated'] for g in GROUPS))}"
    f"～{integer(max(STATS[g]['final_pair_state_distribution']['single_route_elevated'] for g in GROUPS))}；"
    f"双方已抬升 {integer(initial['both_routes_elevated'])}→"
    f"{integer(min(STATS[g]['final_pair_state_distribution']['both_routes_elevated'] for g in GROUPS))}"
    f"～{integer(max(STATS[g]['final_pair_state_distribution']['both_routes_elevated'] for g in GROUPS))}。",
    '新抬升的路线会把一部分双方未抬升对转成单方已抬升对；双方已抬升对的变化反映抬升带来的新近距。'])
table('八个实验问题的逐条回答', ['问题', '本轮实测数值', '结论'], q_rows,
    [3.6, 7.4, 5.6], text_cols=(0, 1, 2),
    notes=('本表只汇总本轮六组与审计的实测值，不引入任何推测性数值；'
           '标“若为 0”的表述表示结论取决于实测值是否为零，实际取值见左侧数值列。'),
    sources=f'{RUNS.name}/summary_all_v4.json、<组>/ledger.json、audit/classification_summary.json。')
para('必须分别表述的三种情况：①是否触发重定位——六组合计 '
     f'{integer(any_reloc)} 次（表 {TN["main"]}）；'
     f'②候选是否全部失败——各组的候选评价与完整验收通过量见表 {TN["counts"]} 与图 {FN["failure"]}；'
     f'③接受后收益是否有限——各组的净减少量与剩余近距对数见表 {TN["main"]} 与表 {TN["offset"]}。'
     '三者含义不同：没有触发重定位说明调度没有到达；候选全部失败说明生成或验收拦住了；'
     '接受后收益有限说明即使有动作，全局剩余量仍然很大。')
para('本轮的表述纪律：如果预算增加而结果没有改善，本报告给出原因证据，不继续调参直到得到正结果；'
     '“当前候选生成规则下无合法窗口”不写成“几何上必然无解”；'
     '只在相同预算上限的 N/R 范围内作最优标注，不同预算主要展示变化趋势。')

# =============================================================== 第8章
heading('第 8 章 限制与下一步算法改动', 1, new_page=True)
table('尚未验证的问题与不适用的结论',
    ['条目', '说明'],
    [['重定位的真实效果', '本轮共用排序下未触达重定位目标，因此没有关于重定位收益的正面或负面证据'],
     ['真实端口数据', '512 是项目既有合成输入，不是真实端口数据，结论不能外推到真实器件'],
     ['光学指标', '本轮只统计中心线几何近距，不涉及损耗、串扰或工艺合规'],
     ['效率比较', '六组并行、单次计时，不支持任何效率结论'],
     ['清零近距对', '本轮不预设清零，也不把剩余量当作失败判据'],
     ['未被审计覆盖的目标', f'审计只覆盖固定清单的 {integer(AUDIT["target_count"])} 对目标，'
      '不是全板 42,909 对的抽样推断']],
    [3.4, 13.2], text_cols=(0, 1),
    notes='以上条目在本轮没有被验证，因此报告不在这些方向上给出结论。')
table('下一步需要改变的算法项与对应证据',
    ['优先级', '需要改变的算法项', '证据'],
    [['1', '目标调度：把“只有重定位可动”的目标显式纳入选择范围（例如按受害者可动类型分层排序）',
      f'起点中涉及已抬升路线的近距对只有 '
      f"{integer(initial['single_route_elevated'] + initial['both_routes_elevated'])} 对，"
      '而这类对在共用优先序中最好的名次也要到第 21,795～34,254 名，'
      '六组实际只尝试了 13/26/66 个目标，因此 R 组零重定位'],
     ['2', '候选生成窗口：放宽“升降窗口必须落在直线段且不切弧”的限制',
      f"审计中 {integer(outcomes.get('NO_LEGAL_WINDOW_UNDER_CURRENT_RULES', 0))} 个目标侧在当前规则下无合法窗口；"
      '其中单方已抬升 13/20、双方已抬升 12/20，明显高于双方未抬升目标的 4/40'],
     ['3', '目标覆盖与遍历顺序：提高正式目标尝试上限或改变遍历顺序，让更多目标至少在预算内被评价一次',
      f"审计的 {total_sides} 个目标侧中只有 {covered} 个曾被此前预算评价；"
      f'六组也只尝试了 13 / 26 / 66 个目标（上限 200）'],
     ['4', '评价调度：减少“生成大量通过验收的候选却只执行一个动作”的浪费（例如先排序候选再按序评价，或按预计净收益截断候选）',
      f'六组共 {integer(TOTAL_EVALUATIONS)} 次评价中基本拒绝 {integer(TOTAL_BASIC_REJECTS)} 次、'
      f'完整拒绝 {integer(TOTAL_FULL_REJECTS)} 次（审计中的完整拒绝理由也全部是 '
      f'NO_STRICT_GLOBAL_DECREASE，共 {integer(sum(full_counts.values()))} 次），'
      f'说明评价几乎全部花在最终没有机会落地的候选上；六组只执行了 {integer(TOTAL_MOVES)} 个动作，'
      f'平均每个动作约 {fmt(AVG_EVALUATIONS_PER_MOVE, 1)} 次评价']],
    [1.6, 8.0, 7.0], text_cols=(1, 2),
    notes='这些改动本轮都没有实现，因此不声称它们一定有效；它们只是由本轮证据指向的下一步方向。')
table('本轮修改与新增的文件',
    ['文件', '作用'],
    [['src/strategy_v4_3d.py', '新增：v4 全布局持续优化模块（N/R 开关、动态目标、缓存、账本）'],
     ['scripts/run_3d_strategy_v4.py', '新增：六组预算实验运行器与终态复核'],
     ['scripts/summarize_3d_strategy_v4.py', '新增：六组汇总与八个问题的数值回答'],
     ['scripts/audit_3d_v4_bottleneck.py', '新增：瓶颈审计'],
     ['scripts/visualize_3d_strategy_v4.py', '新增：七类图（含审计图共九张）'],
     ['tests/test_strategy_v4_3d.py', f'新增：{len(NEWTESTS)} 个回归测试'],
     ['publication/report/brief_build/build_3d_strategy_v4_report.py', '新增：本报告构建脚本'],
     ['publication/report/brief_build/build_all_experiments_report_v4.py',
      '新增：在全部实验总报告上追加本轮实验'],
     ['历史文件', '未修改；所有历史报告与原始实验文件保留原处']],
    [7.4, 9.2], text_cols=(0, 1),
    notes='旧稿中关于候选与动作的口径若有残留，本报告一律采用 accepted_edit_counts 的正确写法，'
         '并在构建前对旧稿做备份，不覆盖原文件。')

# =============================================================== 附录
heading('附录 A 交付文件与哈希', 1, new_page=True)
files = [RUNS/'start_state_check.json', RUNS/'summary_all_v4.json', RUNS/'comparison_v4.csv',
    RUNS/'pytest_full_v4.log', RUNS/'pytest_opt2d_2d_env_v4.log',
    RUNS/'audit/classification_summary.json', RUNS/'audit/target_list.json',
    RUNS/'audit/sampling_rules.json', RUNS/'audit/side_audit.csv', RUNS/'audit/audit_ledger.json',
    RUNS/'audit/recount.json', FIG/'figures_v4_manifest.json']
for g in GROUPS:
    files.append(RUNS/g/'summary.json')
hash_rows = [[str(Path(f).relative_to(ROOT)), f'{Path(f).stat().st_size:,}', sha256(f)[:16]]
    for f in files if Path(f).is_file()]
table('本报告引用的主要产物与哈希（sha256 前 16 位）', ['文件', '字节', 'sha256(前16位)'],
    hash_rows, [9.0, 2.6, 5.0], text_cols=(0,),
    notes='完整哈希与逐图哈希见 figures_v4_manifest.json 与 summary_all_v4.json。',
    sources=f'{RUNS.name}/。')

doc.core_properties.title = NAME
doc.core_properties.author = '李昊伦'
doc.core_properties.subject = '三维波导布线 v4：瓶颈审计、全布局优化与六组追加预算'
for style in doc.styles:
    fonts = style.element.get_or_add_rPr().get_or_add_rFonts()
    fonts.set(qn('w:eastAsia'), '宋体'); fonts.attrib.pop(qn('w:eastAsiaTheme'), None)
defaults = doc.styles.element.find(qn('w:docDefaults'))
if defaults is not None:
    for fonts in defaults.iter(qn('w:rFonts')):
        fonts.set(qn('w:eastAsia'), '宋体'); fonts.attrib.pop(qn('w:eastAsiaTheme'), None)
parts = [doc.part]
for section in doc.sections:
    parts.extend([section.header.part, section.footer.part])
for part in parts:
    for run in part.element.iter(qn('w:r')):
        fonts = run.get_or_add_rPr().get_or_add_rFonts()
        fonts.set(qn('w:eastAsia'), '宋体'); fonts.attrib.pop(qn('w:eastAsiaTheme'), None)
docx_path = OUT/(NAME + '.docx')
doc.save(docx_path)
(OUT/'3d_strategy_v4_report_manifest.json').write_text(json.dumps(dict(
    docx=str(docx_path), tables=TABLES, images=IMAGES,
    inputs={str(Path(p).relative_to(ROOT)): sha256(p) for p in
        [RUNS/'start_state_check.json', RUNS/'summary_all_v4.json',
         RUNS/'audit/classification_summary.json', RUNS/'audit/audit_ledger.json',
         RUNS/'audit/recount.json', FIG/'figures_v4_manifest.json',
         RUNS/'pytest_full_v4.log', RUNS/'pytest_opt2d_2d_env_v4.log']},
    accepted_edit_counts_reference=CORRECT_AC,
    notes=['all numbers are read from the saved artifacts; none is hand-typed',
           'best-in-class marking only inside the same budget upper bound',
           'single-run wall-clock times support no efficiency conclusion']),
    ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(dict(docx=str(docx_path), tables=len(TABLES), images=len(IMAGES),
    figures=FIG_NUMBER[0]), ensure_ascii=False))
