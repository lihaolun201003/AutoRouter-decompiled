"""生成《三维布线策略改进实验报告（修正版）》PDF（reportlab，宋体 + 宋体加粗）。

用法（项目根目录）：
    .venv\\Scripts\\python.exe -B publication\\report\\brief_build\\build_3d_strategy_v2_pdf_rev2.py

数据来自 outputs/3d_strategy_v2/（A/B/C 原始记录）与 outputs/3d_strategy_v2_rev2/
（修正后 C、D/E 诊断、统计重算）。中文加粗使用由 SimSun 轮廓加粗生成的
SimSun-Bold.ttf（scripts/build_simsun_bold.py），不使用黑体。
"""
from pathlib import Path
import csv, json, statistics

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
    Table, TableStyle, Image, PageBreak)

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OLD = ROOT/'outputs'/'3d_strategy_v2'
NEW = ROOT/'outputs'/'3d_strategy_v2_rev2'
FIG = NEW/'figures'
NAME = '三维布线策略改进实验报告（修正版）'
TARGET_PDF = HERE.parent/(NAME + '.pdf')

pdfmetrics.registerFont(TTFont('SimSun', 'C:/Windows/Fonts/simsun.ttc', subfontIndex=0))
BOLD_PATH = HERE/'SimSun-Bold.ttf'
assert BOLD_PATH.is_file(), 'run scripts/build_simsun_bold.py first'
pdfmetrics.registerFont(TTFont('SimSun-Bold', str(BOLD_PATH)))
pdfmetrics.registerFontFamily('SimSun', normal='SimSun', bold='SimSun-Bold', italic='SimSun', boldItalic='SimSun-Bold')

BODY = ParagraphStyle('body', fontName='SimSun', fontSize=10.5, leading=15.75, spaceAfter=6,
                      alignment=TA_LEFT, wordWrap='CJK')
H1 = ParagraphStyle('h1', fontName='SimSun-Bold', fontSize=14, leading=17, spaceBefore=2, spaceAfter=8, wordWrap='CJK')
H2 = ParagraphStyle('h2', fontName='SimSun-Bold', fontSize=11.5, leading=14, spaceBefore=8, spaceAfter=6, wordWrap='CJK')
CAP = ParagraphStyle('cap', fontName='SimSun', fontSize=10, leading=12.5, alignment=TA_CENTER, spaceAfter=6, wordWrap='CJK')
NOTE = ParagraphStyle('note', fontName='SimSun', fontSize=9, leading=11.5, spaceAfter=6, alignment=TA_LEFT, wordWrap='CJK')
CELL = ParagraphStyle('cell', fontName='SimSun', fontSize=9.5, leading=11.4, alignment=TA_CENTER, wordWrap='CJK')
CELL_L = ParagraphStyle('cellL', fontName='SimSun', fontSize=9.5, leading=11.4, alignment=TA_LEFT, wordWrap='CJK')
CELL_H = ParagraphStyle('cellH', fontName='SimSun-Bold', fontSize=9.5, leading=11.4, alignment=TA_CENTER, wordWrap='CJK')
CELL_HL = ParagraphStyle('cellHL', fontName='SimSun-Bold', fontSize=9.5, leading=11.4, alignment=TA_LEFT, wordWrap='CJK')


def jsread(path): return json.loads(Path(path).read_text(encoding='utf-8'))


def csvread(path):
    with open(path, encoding='utf-8-sig', newline='') as f: return list(csv.DictReader(f))


def fmt(value, digits=4): return f'{float(value):.{digits}f}'


def integer(value): return f'{int(float(value)):,}'


STORY = []
TABLES = []


def para(text, style=None, label=None):
    prefix = f'<b>{label}：</b>' if label else ''
    STORY.append(Paragraph(prefix+text, style or BODY))


def h1(text):
    STORY.append(PageBreak()); STORY.append(Paragraph(text, H1))


def h1_first(text): STORY.append(Paragraph(text, H1))


def h2(text): STORY.append(Paragraph(text, H2))


def table(title, headers, rows, widths, text_cols=(0,), best=(), notes=None):
    assert len(headers) == len(widths), (len(headers), len(widths), title)
    assert all(len(row) == len(headers) for row in rows), title
    assert sum(widths) <= 171, (sum(widths), title)
    data = [[Paragraph(h, CELL_HL if ci in text_cols else CELL_H) for ci, h in enumerate(headers)]]
    for ri, row in enumerate(rows):
        line = []
        for ci, value in enumerate(row):
            style = CELL_L if ci in text_cols else CELL
            if (ri, ci) in set(best): style = ParagraphStyle('bold-inline', parent=style, fontName='SimSun-Bold')
            line.append(Paragraph(str(value), style))
        data.append(line)
    t = Table(data, colWidths=[w*mm for w in widths], hAlign='CENTER', repeatRows=1)
    t.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (-1, 0), 0.9, colors.black),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.black),
        ('LINEBELOW', (0, -1), (-1, -1), 0.9, colors.black),
        ('TOPPADDING', (0, 0), (-1, -1), 4.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 4.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))
    number = len(TABLES)+1
    TABLES.append(dict(number=number, title=title, rows=len(rows)))
    STORY.append(Paragraph(f'表{number} {title}', CAP))
    STORY.append(t); STORY.append(Spacer(1, 3*mm))
    if notes: STORY.append(Paragraph('注：'+notes, NOTE))


def picture(path, width_mm, caption):
    path = Path(path)
    assert path.is_file(), path
    from PIL import Image as PILImage
    with PILImage.open(path) as probe: ratio = probe.height/probe.width
    STORY.append(Image(str(path), width=width_mm*mm, height=width_mm*ratio*mm, hAlign='CENTER'))
    STORY.append(Spacer(1, 2*mm))
    STORY.append(Paragraph(f'图{len([f for f in STORY if isinstance(f, Image)])} {caption}', CAP))


# ---------------------------------------------------------------------------
# 数据
# ---------------------------------------------------------------------------

SUMMARY_OLD = {size: jsread(OLD/f'{size}_three_layer_abc'/'summary.json') for size in (512, 1024)}
LEDGER_FIX = {size: jsread(NEW/f'{size}_c_fixed'/'summary_C_fixed.json')['ledger'] for size in (512, 1024)}
RECHECK_FIX = {size: jsread(NEW/f'{size}_c_fixed'/'recheck_C_fixed.json') for size in (512, 1024)}
RECOUNT = jsread(NEW/'stats_fix'/'second_victim_recount.json')
DE_SUMMARY = jsread(NEW/'512_de_diagnostic'/'summary_DE.json')
DE_ROWS = {row['mode']: row for row in DE_SUMMARY['comparison']}
DE_LEDGER = {mode: jsread(NEW/'512_de_diagnostic'/f'ledger_{mode}.json') for mode in ('D', 'E')}
G6 = jsread(NEW/'g6_example.json')


def old_ledger(size, strategy): return SUMMARY_OLD[size]['runs'][strategy]['ledger']


def reduction(initial, final): return 100*(initial-final)/initial


STORY.append(Paragraph(NAME, ParagraphStyle('title', fontName='SimSun-Bold', fontSize=19, leading=23,
    alignment=TA_CENTER, spaceAfter=10)))
para('本报告是前一份《三维布线策略改进实验报告》的修正版。修正了两处代码问题（C 的失败缓存依赖范围、'
     'second_victim_success 统计口径），重跑了 C 策略的 512 与 1024 主实验，并补做了一组来自真实终态的'
     'D/E 重定位诊断实验。A 与 B 的实验结果沿用此前已验证的原始记录，没有重跑，来源在文中逐处标注。')
para('本轮所有比较的度量都是 0.1 mm 中心线近距对数，不代表无碰撞版图，也不代表光学损耗、串扰或制造合规性的改善。')
para(f'核心结果：修正缓存后，512 条 C 的终态近距对为 {integer(LEDGER_FIX[512]["final_collision_pair_count"])}'
     f'（原记录 {integer(old_ledger(512, "C")["final_collision_pair_count"])}），'
     f'1024 条为 {integer(LEDGER_FIX[1024]["final_collision_pair_count"])}'
     f'（原记录 {integer(old_ledger(1024, "C")["final_collision_pair_count"])}）。'
     f'D/E 诊断中，允许重定位的 E 组实际生成并评价了 126 个重定位候选（28 次路线尝试），但没有任何一个通过'
     f'全部验收规则，D 与 E 的终态完全相同。')

h1_first('1 修正内容与影响范围')
h2('1.1 失败缓存依赖范围（已修正）')
para('原实现按目标两条路线各自的版本号记录失败缓存，只有这两条路线变化才会重试。但候选的完整验收依赖'
     '全部当前邻线，第三方路线变化也可能使原先失败的候选变为可接受。修正为全局布局版本：任何一次被接受的'
     '路线修改都会递增版本号，旧布局下的失败记录全部失效。')
para('修正的代价是失败目标会被更频繁地重新评价。在 512 条实验中，修正后 C 的目标尝试从 27 步增至 50 步'
     '（用尽目标尝试上限），其中 25 次是对同一批目标的重复尝试；成功接受从 24 次降到 22 次，'
     '终态近距对从 43750 变为 44274。这是如实记录的差异，不调整规则去凑回原数值。', label='影响')
h2('1.2 second_victim_success 统计口径（已修正）')
para('原实现用"该步骤最后一次 victim 尝试的 priority_index 是否为 1"判断第二路线是否成功，这是错的：'
     '最后一个被尝试的 victim 不一定是最终被选中的路线。修正为找到实际获选路线对应的 victim 尝试，'
     '再用它的 priority_index 判断。A 与 B 没有因为这一项重跑；统计从保存的决策记录重新计算。')
rows = []
for record in RECOUNT['records']:
    if record['strategy'] == 'A': continue
    rows.append([str(record['scale']), record['strategy'], integer(record['accepted_moves']),
                 integer(record['old_rule_last_attempt']),
                 integer(record['corrected_rule_selected_attempt'])])
table('second_victim_success 重算（旧口径 / 修正口径）',
      ['规模', '策略', '接受修改次数', '旧口径计数（错）', '修正口径计数'],
      rows, [16, 14, 38, 50, 46], text_cols=(0, 1),
      notes='从保存的 decisions 文件重算，未重跑 A/B；A 的两次第二-victim 成功在两种口径下相同。'
            f'数据来源：{RECOUNT["source_directory"]}。')

h1('2 修正后重新验证 C：512 条')
ledger = LEDGER_FIX[512]; old = old_ledger(512, 'C')
rows = [
    ['C（原记录）', integer(old['final_collision_pair_count']), fmt(reduction(old['initial_collision_pair_count'], old['final_collision_pair_count']), 2),
     integer(old['accepted_moves']), integer(old['relocations']), integer(old['candidate_evaluations']),
     integer(old['generated_candidates']), integer(old['full_neighbor_checks']),
     {'TARGET_LIMIT':'达到目标尝试上限','CANDIDATE_BUDGET_EXHAUSTED':'候选评价预算耗尽','NO_ELIGIBLE_TARGETS':'没有可尝试目标'}.get(old['stop_reason'], old['stop_reason'])],
    ['C（修正后重跑）', integer(ledger['final_collision_pair_count']), fmt(reduction(ledger['initial_collision_pair_count'], ledger['final_collision_pair_count']), 2),
     integer(ledger['accepted_moves']), integer(ledger['relocations']), integer(ledger['candidate_evaluations']),
     integer(ledger['generated_candidates']), integer(ledger['full_neighbor_checks']),
     {'TARGET_LIMIT':'达到目标尝试上限','CANDIDATE_BUDGET_EXHAUSTED':'候选评价预算耗尽','NO_ELIGIBLE_TARGETS':'没有可尝试目标'}.get(ledger['stop_reason'], ledger['stop_reason'])],
]
table('512 条 C 策略：原记录与修正后重跑（预算上限 720 次候选评价）',
      ['实验', '终态近距对', '净减少%', '接受修改', '重定位', '候选评价', '生成候选', '邻线检查', '停止原因'],
          rows, [27, 20, 17, 16, 14, 16, 16, 21, 24], text_cols=(0, 8),
      notes='修正后的缓存使失败目标重试增多，50 次目标尝试上限先于 720 次候选预算用尽，'
            '因此两者停止原因不同、实际评价次数也不同（666 次）。')
para(f'修正后 C 的关键计数：目标尝试 {ledger["target_attempts"]} 次，'
     f'其中含已抬升路线的目标 {ledger["targets_with_any_elevated_route"]} 次，'
     f'双方都已抬升的目标 {ledger["targets_with_both_elevated_route"]} 次；'
     f'重定位路线尝试 {ledger["relocation_victim_attempts"]} 次，'
     f'重定位候选评价 {ledger["relocation_candidate_evaluations"]} 次，'
     f'接受的重定位 {ledger["relocations"]} 次。', label='计数')
para('"含已抬升路线的目标为 0 次"不是统计缺失：在冻结预算内，"冲突集中"优先级总是先选中冲突度数更大的'
     '低层冲突对，含已抬升路线的目标（其残余冲突度数小）始终排在后面，从未被选中，重定位因此没有被触发。'
     '主实验回答的是"在既有优先级下会不会用到重定位"，第 5 节的 D/E 诊断回答的是"强制处理这类目标时会怎样"，'
     '两者互补。')
para(f'重载复核：从保存文件重新加载 512 条终态路线，完整复核 {integer(RECHECK_FIX[512]["checks"])} 路线对，'
     f'近距对集合与未决集合与增量台账一致（{RECHECK_FIX[512]["collision_pair_set_matches_incremental"]} / '
     f'{RECHECK_FIX[512]["unresolved_pair_set_matches_incremental"]}），端点、C0/C1 连接、过渡曲率与 XY 投影全部通过。',
     label='复核')

h1('3 修正后重新验证 C：1024 条')
ledger1024 = LEDGER_FIX[1024]; old1024 = old_ledger(1024, 'C')
rows = [
    ['C（原记录）', integer(old1024['final_collision_pair_count']),
     fmt(reduction(old1024['initial_collision_pair_count'], old1024['final_collision_pair_count']), 2),
     integer(old1024['accepted_moves']), integer(old1024['relocations']), integer(old1024['candidate_evaluations']),
     integer(old1024['generated_candidates']), integer(old1024['full_neighbor_checks'])],
    ['C（修正后重跑）', integer(ledger1024['final_collision_pair_count']),
     fmt(reduction(ledger1024['initial_collision_pair_count'], ledger1024['final_collision_pair_count']), 2),
     integer(ledger1024['accepted_moves']), integer(ledger1024['relocations']), integer(ledger1024['candidate_evaluations']),
     integer(ledger1024['generated_candidates']), integer(ledger1024['full_neighbor_checks'])],
]
table('1024 条 C 策略：原记录与修正后重跑（预算上限 8172 次候选评价）',
      ['实验', '终态近距对', '净减少%', '接受修改', '重定位', '候选评价', '生成候选', '邻线检查'],
      rows, [32, 22, 18, 17, 15, 17, 17, 19], text_cols=(0,),
      notes='1024 条的完整邻线检查数为 1023，单次评价成本高于 512 条；相同评价次数的实验在两规模之间的耗时不可直接比较。')
para(f'1024 条修正后 C 的计数：目标尝试 {ledger1024["target_attempts"]} 次，'
     f'含已抬升路线 {ledger1024["targets_with_any_elevated_route"]} 次，'
     f'双方已抬升 {ledger1024["targets_with_both_elevated_route"]} 次；'
     f'重定位路线尝试 {ledger1024["relocation_victim_attempts"]} 次，'
     f'重定位候选评价 {ledger1024["relocation_candidate_evaluations"]} 次，'
     f'接受重定位 {ledger1024["relocations"]} 次。与 512 条相同，重试与新目标都停留在低层冲突对上，'
     f'含已抬升路线的目标没有被选中。', label='计数')
para(f'重载复核：重新加载 1024 条终态，复核 {integer(RECHECK_FIX[1024]["checks"])} 路线对，'
     f'集合与台账一致，几何检查全部通过。', label='复核')

h1('4 修正后 A/B/C 主结果对照')
for size in (512, 1024):
    rows = []
    for strategy in ('A', 'B'):
        entry = old_ledger(size, strategy)
        rows.append([f'{strategy}（原记录）', integer(entry['final_collision_pair_count']),
                     fmt(reduction(entry['initial_collision_pair_count'], entry['final_collision_pair_count']), 2),
                     integer(entry['accepted_moves']), integer(entry['relocations']),
                     fmt(entry['final_extra_length_mm'], 4), fmt(entry['runtime_seconds'], 1)])
    entry_old = old_ledger(size, 'C')
    rows.append(['C（原记录）', integer(entry_old['final_collision_pair_count']),
                 fmt(reduction(entry_old['initial_collision_pair_count'], entry_old['final_collision_pair_count']), 2),
                 integer(entry_old['accepted_moves']), integer(entry_old['relocations']),
                 fmt(entry_old['final_extra_length_mm'], 4), fmt(entry_old['runtime_seconds'], 1)])
    entry = LEDGER_FIX[size]
    rows.append(['C（修正重跑）', integer(entry['final_collision_pair_count']),
                 fmt(reduction(entry['initial_collision_pair_count'], entry['final_collision_pair_count']), 2),
                 integer(entry['accepted_moves']), integer(entry['relocations']),
                 fmt(entry['final_extra_length_mm'], 4), fmt(entry['runtime_seconds'], 1)])
    table(f'{size} 条连接的终态对照（A/B 沿用原记录，C 为修正后重跑）',
          ['实验', '终态对数', '净减少%', '接受修改', '重定位', '额外长度(mm)', '运行时间(s)'],
          rows, [30, 20, 16, 20, 16, 27, 25], text_cols=(0,),
          notes='运行时间与长度是不同口径的代价指标，必须分别阅读；'
                '本轮没有做运行时间上的效率结论。所有数值只描述中心线几何。')
    if size == 512:
        para('在两套固定输入上，B 的终态近距对数都低于 A（512：43750 对 45400；1024：130098 对 138113），'
             'B 的终态额外长度也更小（1024：71.92 mm 对 87.41 mm）。样本只有两套固定输入，'
             '不能据此写成"普遍稳定优于 A"。C 与 B 在两规模上的终态数值相同，属于并列，不称"最优为 B"。', label='读数')
picture(FIG/'g1_main_results.png', 165,
        '自己的结果：修正后主结果（A/B 来自原记录，C 修正与 C 原记录并列显示）')
picture(FIG/'g2_pairs_vs_evaluations.png', 165,
        '自己的结果：中心线近距对数随累计候选评价次数（含 C 修正曲线）')

h1('5 来自真实终态的 D/E 重定位诊断')
para('起点为 B 的 512 条终态（已保存、已冻结，文件哈希记录在实验目录）。'
     '从该终态的剩余近距对中，按预先声明的确定性规则选取目标：先按路线编号元组升序取"双方均已抬升"的至多 10 对，'
     '再取"仅一方已抬升"的至多 10 对；不按运行后的收益挑选。'
     'D 组只允许首次抬升（B 的规则），E 组允许已抬路线重定位；两组使用相同起点、固定目标清单、同一处理顺序、'
     '相同几何参数与验收规则，候选评价预算上限同为 720 次。')
start = DE_SUMMARY['start_state']
TARGETS = jsread(NEW/'512_de_diagnostic'/'target_list.json')
para(f'起点状态：{integer(start["collisions"])} 对近距对、{integer(start["elevated_routes"])} 条已抬升路线；'
     f'目标清单共 {DE_SUMMARY["target_count"]} 对，其中双方均已抬升 {len(TARGETS["both_elevated"])} 对、'
     f'仅一方已抬升 {len(TARGETS["one_elevated"])} 对，按路线编号元组升序选取。'
     f'清单完整保存在 512_de_diagnostic/target_list.json。', label='起点与目标')
rows = []
for mode in ('D', 'E'):
    row = DE_ROWS[mode]
    rows.append([mode, integer(row['final_collision_pairs']), integer(row['net_reduction']),
                 integer(row['accepted_moves']), integer(row['relocations']),
                 integer(row['relocation_victim_attempts']), integer(row['relocation_candidate_evaluations']),
                 integer(row['candidate_evaluations']), fmt(row['runtime_seconds'], 1)])
table('D/E 诊断对照（相同预算上限 720 次；实际消耗不同）',
      ['组', '终态近距对', '净减少', '接受修改', '接受重定位', '重定位路线尝试', '重定位候选评价', '候选评价合计', '运行时间（s）'],
      rows, [10, 21, 16, 16, 18, 21, 21, 18, 20], text_cols=(0,),
      notes='两组实际候选评价次数不同（D 324、E 450），只能称"相同预算上限"，不能称相同实际计算工作量。'
            'D/E 的终态近距对数完全相同（42112）：E 多出的 126 次候选评价没有带来任何额外收益。')
rows = []
for mode in ('D', 'E'):
    entry = DE_LEDGER[mode]
    rows.append([mode, integer(entry['failed_no_movable_route']), integer(entry['failed_no_candidates']),
                 integer(entry['failed_all_rejected']), integer(entry['first_elevations']),
                 integer(entry['relocations'])])
table('D/E 目标处理结果分类',
      ['组', '无可移动路线', '无可生成候选', '候选全部被拒', '接受的首次抬升', '接受的重定位'],
      rows, [12, 30, 30, 30, 34, 26], text_cols=(0,),
      notes='"无可移动路线"只出现在 D：双方都已抬升的目标在 D 中没有可移动的路线（10 对全部如此）。'
            'E 在同一批目标上生成了重定位候选并逐一完整评价，结论是"候选全部失败"，不是"没有触发重定位"。')
para('10 对"双方均已抬升"的目标全部涉及路线 34（与 177、185、186、273、274、275、334、338、339、340 这十条'
     '已抬路线成对）：在 B 的 512 条终态里，路线 34 是唯一一条与多条已抬路线仍保持近距冲突的路线。'
     'E 组 28 次重定位路线尝试共产出 126 个候选，全部被验收规则拒绝，没有任何一次接受：'
     '70 个候选在基本验收阶段因自检歧义（SELF_AMBIGUOUS_CLEARANCE）被拒，63 个因目标近距对未被清除'
     '（TARGET_NOT_CLEARED）被拒，28 个通过基本验收后在完整验收阶段因全局近距对数没有严格下降'
     '（NO_STRICT_GLOBAL_DECREASE）被拒。数字合计为逐次计数，同一候选只记一次拒绝原因组。', label='失败原因')
picture(FIG/'g5_relocation_rejections.png', 150,
        '自己的结果：E 组 126 个重定位候选的拒绝原因分布（接受 0 次）')
para('因为没有任何一次重定位被接受，本报告不对重定位的长度代价作评价：D 与 E 的步长变化合计与终态额外长度'
     '完全相同（相对起点的步长变化 4.1223 mm；相对原始平面路线的终态额外长度 13.0153 mm）。'
     '重定位是否可行、是否值得，仍是未验证的问题。')
para('下图为 D/E 中一次真实的首次抬升修改（E 组第一条被接受的路线）：修改前后端点与 XY 投影一致，'
     '三维图明确标注高度放大倍数。重定位成功案例本轮不存在，因此不提供。', label='修改案例')
picture(FIG/f'g6_route{G6["route_id"]}_before_after.png', 165,
        f'自己的结果：路线 {G6["route_id"]} 修改前后（XY 投影、XZ 侧视、三维高度放大 20 倍；真实层高 0/1/2 mm）')

h1('6 终态三维总览')
para('下图为 1024 条 C 修正终态的只读可视化，来自保存的终态几何文件。真实比例与高度放大 20 倍的示意图分开给出，'
     '放大版本的标题与 Z 轴刻度都标注了真实层高 0/1/2 mm。')
picture(FIG/'g7_overview3d_true.png', 135, '自己的结果：1024 条 C 修正终态三维总览（真实高度）')
picture(FIG/'g7_overview3d_z20.png', 135, '自己的结果：同一终态（高度放大 20 倍；真实层高 0/1/2 mm）')

h1('7 结论与限制')
para('本轮修正与验证支持的结论：'
     '（1）失败缓存改为全局布局版本后，第三方路线变化确实会使失败目标重新进入评价，回归测试与 512 条重跑都验证了这一行为；'
     '代价是同一批目标被重复尝试，50 次目标尝试上限先于 720 次候选预算用尽，C 的终态从 43750 变为 44274。'
     '（2）second_victim_success 的口径修正使 512 条 B/C 从 23 次降为 4 次、1024 条 B/C 从 156 次降为 13 次，'
     '与独立重算一致。'
     '（3）修正缓存对两个规模的影响不同：512 条的目标尝试上限只有 50 次，25 次重复尝试挤占了新目标的机会，'
     '终态从 43750 变为 44274；1024 条的目标尝试上限 1024 次远大于实际使用的 310 次（其中 145 次为重复尝试），'
     '重试不影响预算内能完成的工作，终态仍是 130098，与原记录完全相同。'
     '（4）主实验中重定位没有被触发：C 的"冲突集中"优先级在两种规模的预算耗尽前都没有选中含已抬升路线的目标；'
     'D/E 诊断表明，一旦强制处理这些目标，重定位候选会被生成并完整评价，但当前验收规则下全部不可接受。')
para('D/E 诊断给出的结论是明确的负结果：在 512 条 B 终态的 20 个预定目标上，允许重定位的 E 组实际生成并完整评价了'
     '126 个重定位候选，没有任何一个通过全部验收规则；D 与 E 的终态完全相同，E 因此多消耗了约 39% 的候选评价与'
     '约 51% 的运行时间而没有收益。这一结果只覆盖这一份起点、这份目标清单和这套验收规则。')
para('仍未得到验证的问题：（1）重定位在别的起点、别的目标或更宽松的预算下是否有收益，本轮没有证据；'
     '（2）B 同时改动了目标选择、双方候选比较与跨路线排序三项规则，当前结果支持"这批规则组合"的收益，'
     '不能证明每一项改动的独立贡献；（3）运行时间只做了单次实测，不同实验之间的耗时差异不能外推为效率结论；'
     '（4）两套固定输入上 B 低于 A，不能写成"普遍稳定优于 A"。')
para('全部指标都是 0.1 mm 中心线近距对，终态仍有大量近距对；不代表无碰撞版图，也不代表损耗、串扰或制造合规。')

h1('8 数据与文件位置')
para('本轮新增与修正的产物：outputs/3d_strategy_v2_rev2/512_c_fixed/ 与 1024_c_fixed/（修正后 C 的配置、'
     '决策、终态、复核、汇总）、512_de_diagnostic/（D/E 的目标清单、决策、终态、复核、对照表）、'
     'stats_fix/second_victim_recount.json（统计重算）、figures/（本轮图）。'
     'A/B 的原始记录与上一版报告保留在 outputs/3d_strategy_v2/ 与 publication/report/ 下的旧 PDF 中，均未覆盖。', style=NOTE)
para('复现命令（项目根目录）：', style=NOTE)
para('.venv\\Scripts\\python.exe -B scripts\\run_3d_strategy_v2_rev2.py . outputs\\3d_strategy_v2_rev2\\512_c_fixed --task c_fixed --size 512<br/>'
     '.venv\\Scripts\\python.exe -B scripts\\run_3d_strategy_v2_rev2.py . outputs\\3d_strategy_v2_rev2\\1024_c_fixed --task c_fixed --size 1024<br/>'
     '.venv\\Scripts\\python.exe -B scripts\\run_3d_strategy_v2_rev2.py . outputs\\3d_strategy_v2_rev2\\512_de_diagnostic --task de --size 512<br/>'
     '.venv\\Scripts\\python.exe -B scripts\\recount_second_victim_v2.py . outputs\\3d_strategy_v2_rev2\\stats_fix<br/>'
     '.venv\\Scripts\\python.exe -B scripts\\visualize_3d_strategy_v2_rev2.py . outputs\\3d_strategy_v2 outputs\\3d_strategy_v2_rev2',
     style=NOTE)


def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont('SimSun', 9)
    canvas.drawCentredString(A4[0]/2, A4[1]-12*mm, '三维波导布线策略改进实验（修正版）')
    canvas.drawCentredString(A4[0]/2, 10*mm, f'第 {doc.page} 页')
    canvas.restoreState()


doc = BaseDocTemplate(str(TARGET_PDF), pagesize=A4, leftMargin=20*mm, rightMargin=20*mm,
                      topMargin=20*mm, bottomMargin=18*mm, title=NAME, author='李昊伦',
                      subject='三维布线策略改进实验修正版：缓存修正、C 重跑、D/E 重定位诊断')
frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='body')
doc.addPageTemplates([PageTemplate(id='main', frames=[frame], onPage=on_page)])
doc.build(STORY)
print(json.dumps({'pdf': str(TARGET_PDF), 'tables': len(TABLES), 'size_bytes': TARGET_PDF.stat().st_size},
    ensure_ascii=False))
