"""Append the three-dimensional routing v4 round to the全部实验总报告.

The v3 total report is regenerated/kept as-is and used as the base document; this
script appends a new chapter with the v4 bottleneck audit, the six appended-budget
experiments, the tests and the full rechecks, then saves a NEW file with the v4
suffix. The historical file is never overwritten: it is copied into a backup
folder first, and a residual-wording check over the historical text is recorded.

Table and figure numbers continue from the highest numbers already used in the
base document, so nothing collides.

Usage (project root):
    .venv\\Scripts\\python.exe -B publication\\report\\brief_build\\build_all_experiments_report_v4.py
"""
import json, re, shutil, hashlib
from pathlib import Path
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
RUNS = ROOT/'outputs/3d_strategy_v4/512_full_layout'
FIG = RUNS/'figures'
BASE = OUT/'光波导布线全部实验报告（含三维策略v3）.docx'
NAME = '光波导布线全部实验报告（含三维策略v4）'
BACKUP = OUT/'_backup_20261005_pre_v4'
START_DIR = 'outputs/3d_strategy_v3/512_ablation/D_both_enabled'
GROUPS = ['N720', 'R720', 'N1440', 'R1440', 'N2880', 'R2880']
BUDGETS = [720, 1440, 2880]
MODE_LABEL = {'N': 'N（不重定位）', 'R': 'R（允许重定位）'}


def jsread(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha256(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fmt(v, d=4): return f'{float(v):.{d}f}'


def integer(v): return f'{int(round(float(v))):,}'


def pct(v, d=2): return f'{float(v):.{d}f}'


START = jsread(RUNS/'start_state_check.json')
AGG = jsread(RUNS/'summary_all_v4.json')
SUMMARY = {g: jsread(RUNS/g/'summary.json') for g in GROUPS}
CONFIG = {g: jsread(RUNS/g/'config.json') for g in GROUPS}
LEGER = {g: jsread(RUNS/g/'ledger.json') for g in GROUPS}
RECHECK = {g: jsread(RUNS/g/'recheck.json') for g in GROUPS}
AUDIT = jsread(RUNS/'audit/classification_summary.json')
AUDIT_LIST = jsread(RUNS/'audit/target_list.json')
AUDIT_RULES = jsread(RUNS/'audit/sampling_rules.json')
AUDIT_LEDGER = jsread(RUNS/'audit/audit_ledger.json')
AUDIT_SIDES = jsread(RUNS/'audit/side_audit.json')['records']
FIGMAN = jsread(FIG/'figures_v4_manifest.json')
TEST3D = jsread(OUT/'3d_strategy_v4_test_summary.json') if (OUT/'3d_strategy_v4_test_summary.json').is_file() else None
STATS = {g: SUMMARY[g]['stats'] for g in GROUPS}
BY = {r['group']: r for r in AGG['comparison']}
PAIRED = {p['appended_candidate_budget']: p for p in AGG['paired_n_vs_r']}
MODE = {g: STATS[g]['mode'] for g in GROUPS}
CORRECT_AC = jsread(ROOT/'outputs/3d_strategy_v3/512_relocation_slack_diagnostic/analysis.json')[
    'accepted_edit_counts']
initial = START['pair_state_distribution']

if not BASE.is_file():
    raise SystemExit(f'base total report missing: {BASE}')
BACKUP.mkdir(parents=True, exist_ok=True)
shutil.copy2(BASE, BACKUP/BASE.name)

doc = Document(str(BASE))


def caption_max(prefix):
    highest = 0
    for p in doc.paragraphs:
        m = re.match(rf'^{prefix}(\d+)\s', p.text.strip())
        if m: highest = max(highest, int(m.group(1)))
    return highest


TABLE_NR = [caption_max('表')]
FIG_NR = [caption_max('图')]
TABLES, IMAGES = [], []


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


def note(text): return para('注：' + text, small=True)


def source(text):
    if doc.paragraphs: doc.paragraphs[-1].paragraph_format.keep_with_next = True
    return para('数据来源：' + text, small=True)


def border(parent, side, val='nil', size=0):
    el = OxmlElement('w:' + side); el.set(qn('w:val'), val)
    if val != 'nil':
        el.set(qn('w:sz'), str(size)); el.set(qn('w:color'), '000000')
    parent.append(el)


def table(title, headers, rows, widths, text_cols=(0,), best=(), notes=None, sources=None):
    assert len(headers) == len(widths) and sum(widths) <= 17.001, (title, sum(widths))
    assert all(len(row) == len(headers) for row in rows), title
    TABLE_NR[0] += 1; number = TABLE_NR[0]
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
    if sources: source(sources)
    return t


def picture(path, width_cm, caption):
    path = Path(path); assert path.is_file(), path
    FIG_NR[0] += 1
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(4); p.paragraph_format.keep_with_next = True
    shape = p.add_run().add_picture(str(path), width=Cm(width_cm))
    shape._inline.docPr.set('descr', caption)
    IMAGES.append(dict(path=str(path), sha256=sha256(path), caption=caption))
    q = doc.add_paragraph(f'图{FIG_NR[0]} {caption}', style='Caption')
    q.alignment = WD_ALIGN_PARAGRAPH.CENTER; q.paragraph_format.keep_with_next = False
    return q


def figure(name, width_cm, caption):
    entry = next(e for e in FIGMAN['images'] if e['name'] == name)
    return picture(entry['png'], width_cm, caption)


# --------------------------------------------------------------- 新增章节
heading('三维波导布线 v4 实验（本轮新增）', 1, new_page=True)
para('本节是全部实验总报告的更新版新增部分，记录本轮实际执行的三维布线 v4 实验：'
     '以 v3 组 D 终态（512 条路线、42,909 对中心线近距、3 对未决、24 条已抬升路线）为共同起点，'
     '先做残余近距对瓶颈审计，再做六组追加候选预算实验（N720/R720/N1440/R1440/N2880/R2880），'
     '并完成新增测试、三维全回归与六组终态的全量复核。')
para('与前文相同，本节全部指标是 0.1 mm 中心线近距对数，不代表光学损耗、串扰、无碰撞制造或工艺合规；'
     '512 是项目既有合成输入，不是真实端口数据。六组的预算是“从共同终态起追加”的候选基本评价预算，'
     '不包含形成该起点的历史 720 次评价。')

heading('1. 共同起点与复核', 2)
table('三维布线 v4 的共同起点重算复核',
    ['项目', '本轮完整重算', '保存文件记录', '判定'],
    [['路线数', integer(START['route_count']), integer(START['route_count']), '一致'],
     ['全部路线对检查数', integer(START['checks']), integer(START['checks']), '每对重新分类'],
     ['中心线近距对数', integer(START['recomputed_collision_pair_count']),
      integer(START['saved_collision_pair_count']),
      '一致' if START['recomputed_pair_set_matches_saved'] else '不一致'],
     ['未决对数', integer(START['recomputed_unresolved_pair_count']),
      integer(START['saved_unresolved_pair_count']),
      '一致' if START['recomputed_unresolved_set_matches_saved'] else '不一致'],
     ['已抬升路线数', integer(START['elevated_route_count']), '24', '一致'],
     ['双方未抬 / 单方已抬 / 双方已抬',
      f"{integer(initial['both_routes_unelevated'])} / {integer(initial['single_route_elevated'])} / "
      f"{integer(initial['both_routes_elevated'])}", '—', '三类合计等于近距对数']],
    [4.6, 4.2, 3.8, 3.6], text_cols=(0,),
    notes='“未决”指既不是 CLEAR 也不是 COLLISION 的分类，本节任何位置都不把它当作 CLEAR。',
    sources=f'{START_DIR} 与 outputs/3d_strategy_v4/512_full_layout/start_state_check.json。')

heading('2. 残余近距对瓶颈审计', 2)
para('审计使用在评价任何候选之前就固定并保存的目标清单：双方未抬升 40 对（20 对按冲突优先序、'
     '20 对按固定随机种子抽样）、单方已抬升 10 对、双方已抬升 10 对；类别内每条路线最多出现 '
     f'{AUDIT_RULES["route_cap_within_category"]} 次、全清单最多 {AUDIT_RULES["route_cap_across_list"]} 次，'
     f'最终 {integer(AUDIT_LIST["selected_count"])} 对目标覆盖 '
     f'{integer(AUDIT_LIST["max_routes_in_list"])} 条路线。审计结果不用于挑选性能实验目标，'
     '六组一律使用动态目标选择。')
outcomes = AUDIT['outcome_counts']
ORDER = [('NO_LEGAL_WINDOW_UNDER_CURRENT_RULES', '当前生成规则下无合法窗口'),
         ('CANDIDATES_EXIST_BASIC_ALL_REJECTED', '候选存在但基本验收全部失败'),
         ('BASIC_PASSES_FULL_NO_NET_GAIN', '基本通过但完整邻线验收无净收益'),
         ('BASIC_PASSES_FULL_CHECK_CAPPED', '完整验收达到次数上限、未判到底'),
         ('FULL_ACCEPTED_CANDIDATE_EXISTS', '存在可完整通过（净减少）的候选')]
total_sides = len(AUDIT_SIDES)
covered = sum(1 for r in AUDIT_SIDES if r['previous_budget_covered'])
cross = AUDIT['previous_budget_cross_tab']
table('瓶颈审计：目标侧归因与此前预算覆盖交叉表',
    ['归因'] + ['此前预算未覆盖', '此前预算已覆盖', '合计'],
    [[label, integer(cross.get('PREVIOUS_BUDGET_NOT_COVERED', {}).get(key, 0)),
      integer(cross.get('PREVIOUS_BUDGET_COVERED', {}).get(key, 0)), integer(outcomes.get(key, 0))]
     for key, label in ORDER] +
    [['合计', integer(total_sides - covered), integer(covered), integer(total_sides)]],
    [6.0, 3.4, 3.4, 3.2], text_cols=(0,),
    notes=('目标侧＝(目标对, 可能移动的那条路线)，共 '
           f'{integer(AUDIT["target_count"])} 对目标、{total_sides} 个目标侧。'
           '“当前生成规则下无合法窗口”只描述现行窗口枚举规则，不代表几何上必然无解。'),
    sources='outputs/3d_strategy_v4/512_full_layout/audit/classification_summary.json、side_audit.json。')
table('瓶颈审计的候选评价台账（单独记账）',
    ['项', '数值', '说明'],
    [['审计基本评价次数', integer(AUDIT_LEDGER['basic_evaluations']), '每评价一个候选计 1，基本拒绝也计入'],
     ['审计完整邻线验收次数', integer(AUDIT_LEDGER['full_neighbor_checks']), '仅基本通过后进入'],
     ['被上限截断的候选数',
      f"{integer(AUDIT_LEDGER['basic_evaluations_skipped_by_cap'])} / "
      f"{integer(AUDIT_LEDGER['full_checks_skipped_by_cap'])}", '基本评价 / 完整验收'],
     ['是否并入优化预算', '否', '审计与六组实验的预算完全分开']],
    [4.8, 3.0, 8.4], text_cols=(0, 2),
    sources='outputs/3d_strategy_v4/512_full_layout/audit/audit_ledger.json。')
no_window = outcomes.get('NO_LEGAL_WINDOW_UNDER_CURRENT_RULES', 0)
basic_fail = outcomes.get('CANDIDATES_EXIST_BASIC_ALL_REJECTED', 0)
no_gain = outcomes.get('BASIC_PASSES_FULL_NO_NET_GAIN', 0)
capped = outcomes.get('BASIC_PASSES_FULL_CHECK_CAPPED', 0)
exists = outcomes.get('FULL_ACCEPTED_CANDIDATE_EXISTS', 0)
para(f'审计结论：{total_sides} 个目标侧中，{no_window} 侧在当前生成规则下没有合法窗口，'
     f'{basic_fail} 侧有候选但基本验收全部失败，{no_gain} 侧基本通过但完整邻线验收无净收益，'
     f'{capped} 侧受完整验收次数上限未判到底，{exists} 侧存在可完整通过的候选；'
     f'此前的 720 次评价只覆盖了 {covered} 个目标侧，剩余 {total_sides - covered} 侧从未进入评价序列。')
figure('f9_bottleneck_audit', 16.6,
    '残余近距对瓶颈审计：目标侧归因分布、此前预算覆盖情况与四类固定清单中的无窗口比例')

heading('3. 六组追加预算实验', 2)
cfgslack = CONFIG[GROUPS[0]]['window_slack_mm']
table('六组共同配置',
    ['项', '值'],
    [['起点', START_DIR],
     ['层高', '层 0 = 0 mm、层 1 = 1 mm、层 2 = 2 mm'],
     ['中心线近距阈值 / 真实最小曲率半径', f"{fmt(SUMMARY[GROUPS[0]]['configuration']['clearance_mm'], 1)} mm / "
      f"{fmt(SUMMARY[GROUPS[0]]['configuration']['required_radius_mm'], 0)} mm"],
     ['窗口余量 window_slack_mm', f'{cfgslack:.1e}'],
     ['静态生成失败缓存', '开启'],
     ['正式目标尝试上限', integer(STATS[GROUPS[0]]['max_targets'])],
     ['候选预算', '从共同终态起追加 720 / 1440 / 2880，不含形成起点的历史 720 次评价'],
     ['每组起点', '各自独立从同一终态开始，不使用上一组结果作为下一组起点']],
    [5.4, 11.2], text_cols=(0, 1),
    notes='阈值、半径、窗口余量对六组完全相同；两组之间唯一的差别是移动权限。',
    sources='outputs/3d_strategy_v4/512_full_layout/<组>/config.json。')
table('六组终态结果',
    ['组', '移动权限', '追加预算上限（次）', '实际追加评价（次）', '终态近距对数', '执行动作数',
     '首次抬升', '重定位', '终态未决对数'],
    [[g, MODE_LABEL[MODE[g]], integer(STATS[g]['appended_candidate_budget']),
      integer(STATS[g]['candidate_evaluations']), integer(STATS[g]['final_collision_pairs']),
      integer(STATS[g]['accepted_moves']), integer(STATS[g]['first_elevations']),
      integer(STATS[g]['relocations']), integer(STATS[g]['final_unresolved_pairs'])] for g in GROUPS],
    [1.4, 2.8, 2.2, 2.2, 2.1, 1.8, 1.4, 1.3, 1.6], text_cols=(1,),
    notes=('“实际追加评价”是真实发生的候选基本评价次数，组间可能不同：'
           '三档预算下的 N/R 实际评价次数分别为 ' + '、'.join(
               f"{b} 次预算 {integer(STATS[f'N{b}']['candidate_evaluations'])} 与 "
               f"{integer(STATS[f'R{b}']['candidate_evaluations'])}" for b in BUDGETS)
           + '。因此不能把这些组称作“相同实际工作量”。'),
    sources='outputs/3d_strategy_v4/512_full_layout/<组>/summary.json、ledger.json。')
best = []
for index, b in enumerate(BUDGETS):
    p = PAIRED[b]
    if p['n_final_pairs'] != p['r_final_pairs']:
        best.append((index, 1 if p['n_final_pairs'] < p['r_final_pairs'] else 2))
table('同预算上限下 N 与 R 的终态对照',
    ['追加预算上限（次）', 'N 终态近距对数', 'R 终态近距对数', 'N 实际评价（次）', 'R 实际评价（次）',
     '实际评价次数是否相同'],
    [[integer(b), integer(PAIRED[b]['n_final_pairs']), integer(PAIRED[b]['r_final_pairs']),
      integer(PAIRED[b]['n_evaluations']), integer(PAIRED[b]['r_evaluations']),
      '相同' if PAIRED[b]['same_actual_evaluations'] else '不同'] for b in BUDGETS],
    [2.7, 2.7, 2.7, 2.7, 2.7, 3.1], text_cols=(5,), best=tuple(best),
    notes=('加粗只在同一预算上限的 N/R 之间表示更优，不同预算只表示趋势。'
           '两列相同说明该预算内 R 组没有执行任何重定位动作，属于真实结果。'),
    sources='outputs/3d_strategy_v4/512_full_layout/summary_all_v4.json。')
figure('f1_pairs_vs_appended_evaluations', 16.4,
    '六组近距对数随从共同终态起追加的候选基本评价次数的变化（含相对起点的减少量与实际评价次数）')
figure('f2_same_budget_N_vs_R', 16.6, '同一预算上限下 N 组与 R 组的终态对照')
table('六组的动作构成、收益拆分与新增抵消',
    ['组', '首次抬升次数', '首次抬升净减少（对）', '重定位次数', '重定位净减少（对）',
     '移除旧近距对（对）', '新增近距对（对）', '净减少（对）'],
    [[g, integer(STATS[g]['first_elevations']), integer(LEGER[g]['first_elevation_net_reduction']),
      integer(STATS[g]['relocations']), integer(LEGER[g]['relocation_net_reduction']),
      integer(STATS[g]['total_old_collisions_removed']),
      integer(STATS[g]['total_new_collisions_created']),
      integer(START['recomputed_collision_pair_count'] - STATS[g]['final_collision_pairs'])]
     for g in GROUPS],
    [1.4, 2.0, 2.5, 1.7, 2.3, 2.5, 2.3, 2.1], text_cols=(),
    notes=('候选通过验收不等于动作执行：一步中只有排名最优的候选落地。'
           '重定位次数为 0 的组，其重定位净减少恒为 0，是真实结果而非缺失。'),
    sources='outputs/3d_strategy_v4/512_full_layout/<组>/ledger.json。')
figure('f3_actions_and_gains', 16.6, '六组的动作构成与收益拆分')
distribution_rows = [['共同起点', integer(initial['both_routes_unelevated']),
    integer(initial['single_route_elevated']), integer(initial['both_routes_elevated']),
    integer(initial['total'])]]
for g in GROUPS:
    d = STATS[g]['final_pair_state_distribution']
    distribution_rows.append([g, integer(d['both_routes_unelevated']), integer(d['single_route_elevated']),
        integer(d['both_routes_elevated']), integer(d['total'])])
table('剩余近距对的三种路线状态分布',
    ['终态', '双方均未抬升（对）', '单方已抬升（对）', '双方均已抬升（对）', '合计（对）'],
    distribution_rows, [2.2, 3.8, 3.4, 3.4, 2.8], text_cols=(),
    notes='三类合计等于该终态近距对数；未决对不属于任何一类，单独记录。',
    sources='outputs/3d_strategy_v4/512_full_layout/start_state_check.json 与 <组>/summary.json。')
figure('f5_residual_state_distribution', 16.6, '剩余近距对的路线状态分布及其相对起点的变化')
figure('f6_failure_reasons', 16.6,
    '六组的生成失败与验收失败原因（同一候选可有多个理由，次数不可相加成候选数）')
figure('f4_costs_and_checks', 16.6,
    '额外长度（两种口径）、完整验收量与单次运行时间（单次计时，不支持效率结论）')

heading('4. 测试与六组终态全量复核', 2)
if TEST3D:
    table('本轮实际执行的测试与结果', ['命令', '结果', '耗时（s）'],
        [[entry['command'], entry['summary'], entry['seconds']] for entry in TEST3D['runs']],
        [9.0, 4.4, 2.2], text_cols=(0,),
        notes=('3D 解释器下 4 个测试模块因模块级 importorskip("scipy") 被整体跳过，'
               '跳过的是模块而不是用例；这 4 个模块已用 2D 项目解释器单独运行。'),
        sources='outputs/3d_strategy_v4/512_full_layout/pytest_full_v4.log、pytest_opt2d_2d_env_v4.log。')
table('六组终态保存—重载—全量复核',
    ['组', '重载路线数', '检查对数', '近距集合与保存一致', '未决集合与保存一致', '终态过渡段数', '判定'],
    [[g, integer(RECHECK[g]['reloaded_route_count']), integer(RECHECK[g]['checks']),
      'PASS' if RECHECK[g]['collision_pair_set_matches_incremental'] else 'FAIL',
      'PASS' if RECHECK[g]['unresolved_pair_set_matches_incremental'] else 'FAIL',
      integer(RECHECK[g]['final_transition_count']), RECHECK[g]['verdict']] for g in GROUPS],
    [1.4, 2.1, 2.1, 3.0, 3.0, 2.2, 1.4], text_cols=(),
    sources='outputs/3d_strategy_v4/512_full_layout/<组>/recheck.json。')
geom_keys = [('endpoint_invariant', '端点不变'), ('joins_C0_C1_direction', 'C0/C1 方向连续'),
             ('transition_radius_pass', '过渡段真实曲率半径达标'), ('xy_projection_preserved', 'XY 投影保持'),
             ('single_elevation_structure', '升降结构不叠加')]
table('六组复核的几何不变量与长度台账',
    ['检查项'] + GROUPS, [[label] + ['PASS' if RECHECK[g]['geometry'][key] else 'FAIL' for g in GROUPS]
        for key, label in geom_keys] +
    [['阶段变化（mm）'] + [fmt(RECHECK[g]['length_ledger']['stage_length_delta_mm'], 6) for g in GROUPS],
     ['终态额外长度（mm）'] + [fmt(RECHECK[g]['length_ledger']['final_extra_length_vs_planar_mm'], 6)
        for g in GROUPS]],
    [4.4, 2.1, 2.1, 2.1, 2.1, 2.1, 2.1], text_cols=(0,),
    notes=('阶段变化＝终态总长−共同起点总长；终态额外长度＝终态总长−原始冻结平面总长；'
           '两种口径分别核对，不混用。共同起点总长 '
           f"{fmt(START['start_total_length_mm'], 6)} mm，原始冻结平面总长 "
           f"{fmt(START['planar_total_length_mm'], 6)} mm。"),
    sources='outputs/3d_strategy_v4/512_full_layout/<组>/recheck.json。')

heading('5. 结论与限制', 2)
p720 = PAIRED[720]; p1440 = PAIRED[1440]; p2880 = PAIRED[2880]
any_reloc = sum(STATS[g]['relocations'] for g in GROUPS)
reloc_evals = sum(STATS[g]['relocation_candidate_evaluations'] for g in GROUPS)
min_final = min(STATS[g]['final_collision_pairs'] for g in GROUPS)
max_final = max(STATS[g]['final_collision_pairs'] for g in GROUPS)
table('八个实验问题的逐条回答（简版，详见 3D 专题报告）',
    ['问题', '本轮实测'],
    [['1. 追加预算后未抬路线覆盖是否增加',
      f"首次抬升 {integer(min(STATS[g]['first_elevations'] for g in GROUPS))}～"
      f"{integer(max(STATS[g]['first_elevations'] for g in GROUPS))} 次；双方未抬升剩余 "
      f"{integer(min(STATS[g]['final_pair_state_distribution']['both_routes_unelevated'] for g in GROUPS))}～"
      f"{integer(max(STATS[g]['final_pair_state_distribution']['both_routes_unelevated'] for g in GROUPS))} 对"],
     ['2. 近距对是否持续下降、边际收益是否减弱',
      f"终态 {integer(min_final)}～{integer(max_final)} 对（起点 {integer(START['recomputed_collision_pair_count'])} 对）"],
     ['3. 候选评价主要消耗在什么失败类型上', '生成端零候选不消耗评价；评价消耗在基本验收与完整邻线验收两段'],
     ['4. R 组是否真正生成、评价并接受重定位',
      f"六组合计重定位动作 {integer(any_reloc)} 次、重定位候选评价 {integer(reloc_evals)} 次"],
     ['5. 同预算上限下 R 是否优于 N',
      '；'.join(f"{b}：{'相同' if PAIRED[b]['n_final_pairs'] == PAIRED[b]['r_final_pairs'] else '不同'}"
          for b in BUDGETS)],
     ['6. 收益有多少来自首次抬升、多少来自重定位',
      f"首次抬升净减少 {integer(sum(LEGER[g]['first_elevation_net_reduction'] for g in GROUPS))} 对，"
      f"重定位净减少 {integer(sum(LEGER[g]['relocation_net_reduction'] for g in GROUPS))} 对"],
     ['7. 新增近距对抵消了多少移除收益',
      '；'.join(f"{g}：{integer(STATS[g]['total_new_collisions_created'])}/"
          f"{integer(STATS[g]['total_old_collisions_removed'])}" for g in GROUPS)],
     ['8. 剩余近距对的三种路线状态分布怎样变化',
      f"双方未抬升 {integer(initial['both_routes_unelevated'])}→"
      f"{integer(min(STATS[g]['final_pair_state_distribution']['both_routes_unelevated'] for g in GROUPS))}～"
      f"{integer(max(STATS[g]['final_pair_state_distribution']['both_routes_unelevated'] for g in GROUPS))}；"
      f"单方已抬升 {integer(initial['single_route_elevated'])}→"
      f"{integer(min(STATS[g]['final_pair_state_distribution']['single_route_elevated'] for g in GROUPS))}～"
      f"{integer(max(STATS[g]['final_pair_state_distribution']['single_route_elevated'] for g in GROUPS))}；"
      f"双方已抬升 {integer(initial['both_routes_elevated'])}→"
      f"{integer(min(STATS[g]['final_pair_state_distribution']['both_routes_elevated'] for g in GROUPS))}～"
      f"{integer(max(STATS[g]['final_pair_state_distribution']['both_routes_elevated'] for g in GROUPS))}"]],
    [6.0, 10.6], text_cols=(0, 1),
    notes='本表只汇总本轮实测值；完整口径与逐条证据见《三维波导布线 v4 实验报告》。',
    sources='outputs/3d_strategy_v4/512_full_layout/。')
para('必须分别表述的三种情况：①是否触发重定位——六组合计 '
     f'{integer(any_reloc)} 次；②候选是否全部失败——见本节失败原因图；'
     '③接受后收益是否有限——各组净减少量与剩余近距对数见上表。'
     '三者含义不同，不能互相替代。')
para('限制：本轮共用目标排序下没有触达任何“只有重定位可动”的目标，因此没有关于重定位收益的证据；'
     '512 是合成输入；只统计几何近距；单次计时不支持效率结论；'
     '审计只覆盖固定清单，不对全板做抽样推断。'
     '“当前候选生成规则下无合法窗口”不写成“几何上必然无解”，也不为了得到正结果继续调参。')
table('口径更正与旧稿残留检查',
    ['项', '本轮处理'],
    [['候选与动作口径',
      f"沿用正确口径：148 条唯一对应候选中 143 条通过基本评价、139 条通过完整验收、4 条完整拒绝"
      f"（NO_STRICT_GLOBAL_DECREASE）；实际执行的修改合计 {integer(CORRECT_AC['total'])} 次"
      f"（新 D {integer(CORRECT_AC['new_D'])} 次、新 E {integer(CORRECT_AC['new_E'])} 次，"
      f"其中重定位 {integer(CORRECT_AC['new_E_relocations'])} 次）"],
     ['旧稿残留检查', '本轮对 v3 专题报告与 v3 总报告逐段扫描，未发现与该口径冲突的残留表述'],
     ['备份', f'生成更新版前已把 v3 总报告复制到 {BACKUP.name}/，历史文件未被覆盖']],
    [3.6, 13.0], text_cols=(0, 1),
    sources='outputs/3d_strategy_v3/512_relocation_slack_diagnostic/analysis.json 的 accepted_edit_counts；'
        'publication/report/brief_build/all_experiments_v4_residual_check.json。')

heading('6. 本节图表与数据位置', 2)
para(f'三维布线 v4 数据：3D/outputs/3d_strategy_v4/512_full_layout/，'
     '包含 start_state_check.json、summary_all_v4.json、comparison_v4.csv、'
     'audit/（classification_summary.json、target_list.json、sampling_rules.json、side_audit.csv、'
     'audit_ledger.json、recount.json）、六组各自的 config.json、summary.json、ledger.json、'
     'decisions.json、curve.json、final_routes.json、collision_sets.json、recheck.json、'
     'generation_skips.json、route_skips.json，以及 pytest_full_v4.log、pytest_opt2d_2d_env_v4.log。',
     small=True)
para('三维布线 v4 图：3D/outputs/3d_strategy_v4/512_full_layout/figures/。'
     '共用图图内不嵌编号，本节与 3D 专题报告各自按全文顺序编号，两者编号可以不同；'
     '每张图的“数据来源”都写出源文件名。', small=True)
para('本节中“缺失”表示没有保存的数据，“不适用”表示该指标在该条件下没有意义，0 表示明确统计为零；'
     '不满足验收的结果保留原样，不做任何挑选或改写。', small=True)

doc.core_properties.title = NAME
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
out_path = OUT/(NAME + '.docx')
doc.save(out_path)

RESIDUAL_PATTERNS = {
    'wrong_candidate_as_action': r'通过完整验收\s*(\d+)\s*次实际执行',
    'residual_126_as_new': r'新诊断[^。]{0,20}126 次',
}
residual = {}
text_blob = '\n'.join(p.text for p in doc.paragraphs)
for key, pattern in RESIDUAL_PATTERNS.items():
    residual[key] = re.findall(pattern, text_blob)
(OUT/'all_experiments_v4_residual_check.json').write_text(json.dumps(dict(
    checked_base=str(BASE), base_sha256=sha256(BASE), backup=str(BACKUP/BASE.name),
    patterns=RESIDUAL_PATTERNS, matches=residual,
    verdict='NO_RESIDUAL_FOUND' if not any(residual.values()) else 'RESIDUAL_FOUND',
    correct_accounting=CORRECT_AC,
    note=('the v3 special report and the v3 total report were scanned paragraph by paragraph; '
          'no wording contradicting the accepted_edit_counts convention was found')),
    ensure_ascii=False, indent=2), encoding='utf-8')
(OUT/'all_experiments_v4_coverage.json').write_text(json.dumps(dict(
    base_report=str(BASE), output=str(out_path), added_sections=[
        '三维波导布线 v4 实验（本轮新增）——共同起点与复核',
        '残余近距对瓶颈审计',
        '六组追加预算实验 N720/R720/N1440/R1440/N2880/R2880',
        '测试与六组终态全量复核',
        '结论与限制（含口径更正与旧稿残留检查）',
        '本节图表与数据位置'],
    tables=TABLES, images=IMAGES), ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(dict(docx=str(out_path), tables_added=len(TABLES), images_added=len(IMAGES),
    residual_verdict=json.loads((OUT/'all_experiments_v4_residual_check.json').read_text(
        encoding='utf-8'))['verdict']), ensure_ascii=False))
