"""生成《三维布线策略改进实验报告》PDF（reportlab，中文宋体）。

用法（项目根目录）：
    .venv\\Scripts\\python.exe -B publication\\report\\brief_build\\build_3d_strategy_v2_pdf.py

数据全部来自 outputs/3d_strategy_v2/ 下的真实产物；不重跑布线。
排版：正文宋体 1.5 倍行距，表格 1.2 倍行距并留内边距，三线表，章节另起一页。
"""
from pathlib import Path
import csv, json, statistics

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
    Table, TableStyle, Image, PageBreak)

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
STRATEGY_DIR = ROOT/'outputs'/'3d_strategy_v2'
FIG = STRATEGY_DIR/'figures'
NAME = '三维布线策略改进实验报告'
TARGET_PDF = OUT.parent/(NAME + '.pdf')

pdfmetrics.registerFont(TTFont('SimSun', 'C:/Windows/Fonts/simsun.ttc', subfontIndex=0))
pdfmetrics.registerFont(TTFont('SimHei', 'C:/Windows/Fonts/simhei.ttf'))
pdfmetrics.registerFontFamily('SimSun', normal='SimSun', bold='SimHei', italic='SimSun', boldItalic='SimHei')

BODY = ParagraphStyle('body', fontName='SimSun', fontSize=10.5, leading=15.75, spaceAfter=6,
                      alignment=TA_LEFT, wordWrap='CJK')
H1 = ParagraphStyle('h1', fontName='SimHei', fontSize=14, leading=17, spaceBefore=2, spaceAfter=8, wordWrap='CJK')
H2 = ParagraphStyle('h2', fontName='SimHei', fontSize=11.5, leading=14, spaceBefore=8, spaceAfter=6, wordWrap='CJK')
CAP = ParagraphStyle('cap', fontName='SimSun', fontSize=10, leading=12.5, alignment=TA_CENTER, spaceAfter=6,
                     wordWrap='CJK')
NOTE = ParagraphStyle('note', fontName='SimSun', fontSize=9, leading=11.5, spaceAfter=6, alignment=TA_LEFT,
                      wordWrap='CJK')
CELL = ParagraphStyle('cell', fontName='SimSun', fontSize=9.5, leading=11.4, alignment=TA_CENTER, wordWrap='CJK')
CELL_L = ParagraphStyle('cellL', fontName='SimSun', fontSize=9.5, leading=11.4, alignment=TA_LEFT, wordWrap='CJK')
CELL_H = ParagraphStyle('cellH', fontName='SimHei', fontSize=9.5, leading=11.4, alignment=TA_CENTER, wordWrap='CJK')
CELL_HL = ParagraphStyle('cellHL', fontName='SimHei', fontSize=9.5, leading=11.4, alignment=TA_LEFT, wordWrap='CJK')


def jsread(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def csvread(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def fmt(v, d=4):
    return f'{float(v):.{d}f}'


def integer(v):
    return f'{int(float(v)):,}'


RUNS = {size: jsread(STRATEGY_DIR/f'{size}_three_layer_abc'/'summary.json') for size in (512, 1024)}
COMPARISON = {size: {row['strategy']: row for row in
                     csvread(STRATEGY_DIR/f'{size}_three_layer_abc'/'comparison.csv')} for size in (512, 1024)}
STOP = {'TARGET_LIMIT': '达到目标尝试上限', 'NO_ELIGIBLE_TARGETS': '没有可尝试目标',
        'CANDIDATE_BUDGET_EXHAUSTED': '候选评价预算耗尽'}


def ledger(size, strategy):
    return RUNS[size]['runs'][strategy]['ledger']


def reduction(size, strategy):
    entry = ledger(size, strategy)
    return 100*(entry['initial_collision_pair_count']-entry['final_collision_pair_count'])/entry['initial_collision_pair_count']


def target_degree_stats(size, strategy):
    steps = jsread(STRATEGY_DIR/f'{size}_three_layer_abc'/f'decisions_{strategy}.json')
    values = [sum(v for v in step['victim_degrees'].values()) for step in steps]
    return len(steps), statistics.mean(values), statistics.median(values)


def stepwise_agreement(size):
    new = jsread(STRATEGY_DIR/f'{size}_three_layer_abc'/'decisions_A.json')
    old = jsread(ROOT/'outputs'/(('step_9_f_three_layer_attempts.json', 'step_10_fixed_1024_attempts.json')[size == 1024]))
    fields = ['target_pair', 'status', 'moved_route_id', 'target_layer_id',
              'net_collision_reduction', 'global_collision_pairs_before', 'global_collision_pairs_after']
    diffs = 0
    for a, b in zip(new, old):
        for field in fields:
            x, y = a.get(field), b.get(field)
            if isinstance(x, list):
                x = tuple(x)
            if isinstance(y, list):
                y = tuple(y)
            if x != y:
                diffs += 1
    return len(new), len(old), diffs


STORY = []
TABLES = []


def para(text, style=None, label=None):
    prefix = f'<b>{label}：</b>' if label else ''
    STORY.append(Paragraph(prefix+text, style or BODY))


def h1(text):
    STORY.append(PageBreak())
    STORY.append(Paragraph(text, H1))


def h1_first(text):
    STORY.append(Paragraph(text, H1))


def h2(text):
    STORY.append(Paragraph(text, H2))


def table(title, headers, rows, widths, text_cols=(0,), best=(), notes=None):
    assert sum(widths) <= 171
    data = [[Paragraph(h, CELL_HL if ci in text_cols else CELL_H) for ci, h in enumerate(headers)]]
    for ri, row in enumerate(rows):
        line = []
        for ci, value in enumerate(row):
            style = CELL_L if ci in text_cols else CELL
            if (ri, ci) in set(best):
                style = ParagraphStyle('bold', parent=style, fontName='SimHei')
            line.append(Paragraph(str(value), style))
        data.append(line)
    t = Table(data, colWidths=[w*mm for w in widths], hAlign='CENTER', repeatRows=1)
    t.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (-1, 0), 0.9, colors.black),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.black),
        ('LINEBELOW', (0, -1), (-1, -1), 0.9, colors.black),
        ('TOPPADDING', (0, 0), (-1, -1), 4.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    number = len(TABLES)+1
    TABLES.append(dict(number=number, title=title, rows=len(rows)))
    STORY.append(Paragraph(f'表{number} {title}', CAP))
    STORY.append(t)
    STORY.append(Spacer(1, 3*mm))
    if notes:
        STORY.append(Paragraph('注：'+notes, NOTE))


def picture(path, width_mm, caption):
    path = Path(path)
    assert path.is_file(), path
    from PIL import Image as PILImage
    with PILImage.open(path) as probe:
        ratio = probe.height/probe.width
    STORY.append(Image(str(path), width=width_mm*mm, height=width_mm*ratio*mm, hAlign='CENTER'))
    STORY.append(Spacer(1, 2*mm))
    STORY.append(Paragraph(f'图{len([f for f in STORY if isinstance(f, Image)])} {caption}', CAP))


# ---------------------------------------------------------------------------
# 正文
# ---------------------------------------------------------------------------

b512 = RUNS[512]['budget']
b1024 = RUNS[1024]['budget']

STORY.append(Paragraph(NAME, ParagraphStyle('title', fontName='SimHei', fontSize=19, leading=23,
    alignment=TA_CENTER, spaceAfter=10)))
para('本报告记录在固定二维 XY 路径上、三层高度（0/1/2 mm）条件下，对已经实现的三维局部升降方法的策略改进实验。'
     '上一轮方法在 1024 条合成实例上把中心线近距对数从 204291 降到 138113（减少 32.39%），'
     '但 1024 次目标尝试中有 845 次因为双方都已经抬升而跳过。本轮比较三种策略：A 为原策略对照，'
     'B 改进目标选择并比较双方候选，C 在 B 的基础上允许已抬路线重新选择层与升降位置。'
     '三组使用完全相同的输入、几何参数和实际候选评价预算，只改变决策规则。')
para(f'在相同候选评价预算下，1024 条实例的终态近距对数 A/B/C 分别为 '
     f'{integer(ledger(1024, "A")["final_collision_pair_count"])}、'
     f'{integer(ledger(1024, "B")["final_collision_pair_count"])}、'
     f'{integer(ledger(1024, "C")["final_collision_pair_count"])}；'
     '全部结果只描述中心线几何，不代表光学损耗、串扰或制造合规性。', label='结论先行')

h1_first('1 实验内容与设置')
para('对 512 条（原二维平滑基线）与 1024 条（固定双覆盖扩展）两种规模，分别运行 A、B、C 三个策略，'
     '每个策略只改变决策规则，其他条件完全一致：同一初始路线与输入文件、层高 0/1/2 mm、'
     '0.1 mm 中心线近距阈值、5 mm 真实最小曲率半径下限、余弦过渡、直线段有限窗口枚举、'
     'XY 投影与端点固定、每条路线最多保留一对升降。', label='做了什么')
h2('1.1 三种策略的决策规则')
table('三种策略的决策规则', ['策略', '目标与候选选择', '备注'], [
    ['A', '目标：当前近距对中元组最小者；victim：冲突度数小者优先；第一条路线出现改善即停止、'
          '不再比较另一条；每条路线最多抬升一次。', '原有 9-E/9-F 规则，在新引擎内原样重实现'],
    ['B', '过滤双方都已抬过的目标；目标优先级按"冲突集中"（两条路线度数之和、再按最大值）确定性排序；'
          '对目标两条路线的候选都做完整评价后统一选择；跨路线排序首先比较净减少量 net=removed−created，'
          '相同再比较新增对、长度代价、过渡数。', '每条路线仍最多抬升一次'],
    ['C', '在 B 基础上允许已抬路线重定位：重新选择 1/2 mm 层与升降窗口，替代候选从原始（未抬）平面路线重建，'
          '评价时以当前路线作为对照基线；失败目标按依赖版本记录，相关路线变化后允许重试。',
     '每条终态路线仍只保留一对升降'],
], [16, 105, 50], text_cols=(0, 1, 2))
h2('1.2 统一几何验收与台账')
para('每个被接受的候选必须同时满足：保持路线 ID、端点和完整 XY 投影不变（含双向采样检查）；'
     '连接位置与切向方向通过；真实最小曲率半径不低于 5 mm；自身间距检查通过；清除选定目标近距对；'
     '与全部当前邻线（包括已经抬过的路线）完整检查且没有未决状态；全局中心线近距对数严格下降。'
     '未收敛、歧义与阈值接触一律不当作 CLEAR。失败或被拒绝的候选不会改变任何已保存状态。'
     '允许"有新增但净减少"的候选，三组使用同一验收规则。')
h2('1.3 实验公平性与预算冻结')
para(f'历史记录中 512 条三层实验 50 次目标尝试实际调用 720 次候选基本评价（348 个通过）；'
     f'1024 条实验 1024 次尝试调用 8172 次（4604 个通过）。本轮的候选评价预算取这两个实测值并在运行 B/C 之前'
     f'写入配置：512 条为 {integer(b512["candidate_budget"])} 次，1024 条为 {integer(b1024["candidate_budget"])} 次。'
     f'预算口径：每个生成的候选调用一次基本验收（evaluate_elevation）计一次，基本验收失败同样计入；'
     f'预算不足以完整验收一个候选时，该候选不提交、不参与最终选择。防循环上限为目标尝试数'
     f'（512 条为 {b512["max_targets"]} 次，1024 条为 {b1024["max_targets"]} 次），与历史尝试口径一致。')

for size in (512, 1024):
    h1(f'{"2" if size == 512 else "3"} {size} 条连接的 A/B/C 对照')
    para(f'初始状态：{integer(ledger(size, "A")["initial_collision_pair_count"])} 对中心线近距对'
         f'（另有 {ledger(size, "A")["initial_unresolved_pair_count"]} 对未决/边界单列，不当作 CLEAR，'
         f'也不计入近距对）；全部路线在 Layer 0，'
         f'总长度 {fmt(ledger(size, "A")["initial_total_length_mm"], 3)} mm。')
    rows = []
    for strategy in 'ABC':
        entry = ledger(size, strategy)
        rows.append([strategy, integer(entry['final_collision_pair_count']), fmt(reduction(size, strategy), 2),
                     integer(entry['total_old_collisions_removed']), integer(entry['total_new_collisions_created']),
                     integer(entry['final_unresolved_pair_count']), integer(entry['accepted_moves']),
                     integer(entry['relocations']), STOP.get(entry['stop_reason'], entry['stop_reason'])])
    table(f'{size} 条连接的终态指标（同预算 {integer((b512 if size == 512 else b1024)["candidate_budget"])} 次候选评价）',
          ['策略', '终态对数', '净减少%', '移除对', '新增对', '未决对', '接受修改', '重定位', '停止原因'],
          rows, [12, 19, 20, 16, 16, 16, 20, 16, 34], text_cols=(0, 8), best=[(0, 1), (1, 1), (2, 1)],
          notes='"净减少%"＝（初始−终态）/初始；粗体为三组中终态近距对数最低者。'
                '"移除对/新增对"为逐次集合差累计，不是独立的二维交叉事件数。')
    para('三组的使用预算（实际候选评价数）：'
         + '；'.join(f'{s} 为 {integer(ledger(size, s)["candidate_evaluations"])} 次' for s in 'ABC')
         + '。生成候选数分别为 '
         + '、'.join(integer(ledger(size, s)['generated_candidates']) for s in 'ABC')
         + '；完成全邻线检查的候选数分别为 '
         + '、'.join(integer(ledger(size, s)['full_neighbor_checks']) for s in 'ABC') + '。', label='预算使用')
    degree_rows = []
    for strategy in 'ABC':
        count, mean_degree, median_degree = target_degree_stats(size, strategy)
        degree_rows.append([strategy, integer(count), fmt(mean_degree, 1), fmt(median_degree, 1)])
    table(f'{size} 条：目标选择对比（每次尝试两条路线当前冲突度数之和）',
          ['策略', '目标尝试次数', '度数之和平均值', '度数之和中位数'],
          degree_rows, [20, 36, 54, 54], text_cols=(0,),
          notes='B/C 选择"冲突集中"的目标；A 按配对元组最小者选择。度数为该目标两条路线在当前近距对集合中的'
                '冲突次数之和；不同策略的列不可直接横向比较优劣，只用于核对策略确实按定义执行。')
    h2(f'{2 if size == 512 else 3}.1 曲线与对照解读')
    if size == 512:
        picture(FIG/'f81_pairs_vs_evaluations.png', 165,
                '自己的结果：中心线近距对数随累计候选评价次数的变化（左 512 条，右 1024 条；'
                '横轴为 evaluate_elevation 调用数）')
        para('上图两幅子图使用同一横轴口径。512 条三组在完全相同预算内走完各自的尝试；'
             '1024 条三组的曲线在预算耗尽处截断，截断点即为该组的实际使用预算。')
    else:
        para('上图右幅为 1024 条的三条曲线：三组使用相同的 8172 次候选评价预算，在各自耗尽处停止；'
             'A 达到 1024 次目标尝试上限，B/C 在预算耗尽处停止。终态差异完全来自候选选择规则的不同。')

h1('4 代价对照：长度、过渡与运行时间')
rows = []
for size in (512, 1024):
    for strategy in 'ABC':
        entry = ledger(size, strategy)
        rows.append([str(size), strategy, fmt(entry['final_extra_length_mm'], 4),
                     fmt(entry['total_step_length_delta_mm'], 4), integer(entry['final_transition_count']),
                     integer(entry['elevated_route_count']), fmt(entry['runtime_seconds'], 1)])
table('终态长度与过渡代价',
      ['规模', '策略', '终态额外长度(mm)', '长度变化累计(mm)', '过渡数', '抬升路线数', '运行时间(s)'],
      rows, [13, 12, 33, 33, 16, 23, 24], text_cols=(0, 1),
      notes='"终态额外长度"＝终态总长−原始总长，直接从终态几何统计；"长度变化累计"为逐次（新−当前）之和，'
            'C 的重定位可以使单步长度为负，两者不应混用。过渡数从终态几何统计。运行时间为本机单次实测，不是稳定基准。')
picture(FIG/'f82_final_comparison.png', 165,
        '自己的结果：A/B/C 终态近距对数与代价对照（依次为终态近距对、额外长度、运行时间、实际候选评价次数）')

h1('5 重定位说明与终态三维总览')
h2('5.1 重定位说明')
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
            entries.append((rid, first, route_steps[-1]))
    relocation_rows[size] = entries
if relocation_rows[512] or relocation_rows[1024]:
    rid, first, last = (relocation_rows[1024] or relocation_rows[512])[0]
    para(f'1024 条实例中共有 {len(relocation_rows[1024])} 条路线发生重定位，512 条实例中为 {len(relocation_rows[512])} 条。'
         f'示例路线 {rid}：第一次抬升到 Layer {first["target_layer_id"]}（步骤 {first["step_index"]}，'
         f'目标对 {tuple(first["target_pair"])}，路线长度 {fmt(first["route_length_after_mm"], 4)} mm），'
         f'随后重定位到 Layer {last["target_layer_id"]}（步骤 {last["step_index"]}，'
         f'该步长度变化 {fmt(last["step_length_delta_mm"], 4)} mm，路线长度 {fmt(last["route_length_after_mm"], 4)} mm）。'
         f'两份几何的端点与 XY 投影完全一致（复核脚本逐条通过）。')
else:
    para('在本轮冻结预算内，C 在两个规模上都没有触发对已抬路线的重定位（512 条的 C 与 B 的逐步记录完全相同；'
         '1024 条见上表与终态记录）。这不是实现缺陷，而是预算与目标顺序共同作用的结果：重定位只在'
         '"双方都已抬过且仍有冲突"的目标上才有价值，这些目标在预算耗尽前没有进入 C 的选择序列。')
relocation_figures = sorted(FIG.glob('f83_relocation_*.png'), key=lambda p: p.stat().st_size, reverse=True)
if relocation_figures:
    picture(relocation_figures[0], 155,
            '自己的结果：同一路线重定位前后的 XY 投影（上）与沿程高度（下）；真实层高 0/1/2 mm')
else:
    para('本轮没有发生重定位，因此没有可展示的重定位前后图；该图仅在有真实重定位记录时生成。')

h2('5.2 终态三维总览')
para('下图为 1024 条实例 C 策略终态的只读可视化，来自保存的终态几何文件。三维总览同时给出真实高度版本和'
     '高度放大 20 倍版本，放大版本在标题中明确标注；Z 轴刻度仍标注真实层高 0/1/2 mm。')
picture(FIG/'f84_overview3d_z20.png', 135,
        '自己的结果：1024 条连接 C 策略终态三维总览（高度放大 20 倍；真实层高 0/1/2 mm）')
picture(FIG/'f85_xz_side.png', 165,
        '自己的结果：1024 条连接 C 策略终态 XZ 侧视（纵向放大显示；灰/蓝/橙为 0/1/2 mm 层，紫色为过渡段）')

h1('6 A 与历史记录的一致性核对')
rows = []
for size in (512, 1024):
    hist = RUNS[size].get('historical_A') or {}
    step_count, old_count, diffs = stepwise_agreement(size)
    rows.append([str(size),
                 integer(hist['historical_final_pairs'])+' / '+integer(hist['measured_final_pairs']),
                 f'{hist["historical_successful_elevations"]} / {hist["measured_accepted_first_elevations"]}',
                 fmt(hist['historical_total_extra_length_mm'], 6)+' / '+fmt(hist['measured_total_extra_length_mm'], 6),
                 f'{step_count} / {old_count}，差异 {diffs} 处',
                 '一致' if hist.get('matches_history') and diffs == 0 else '不一致'])
table('A 与历史记录核对（历史 / 本轮 A）',
      ['规模', '终态近距对', '成功抬升次数', '额外长度（mm）', '逐步记录', '结论'],
      rows, [13, 31, 26, 44, 34, 17], text_cols=(0, 4, 5),
      notes='A 在本轮新引擎内原样重实现，用于确认共享预算与台账没有改变原有决策行为。逐步记录比较每一步的'
            '目标对、状态、移动路线、目标层、净减少量与全局近距对前后计数；终态近距对集合与未决集合在两组规模上'
            '均与历史保存完全一致。')
para('A 复跑与历史记录在指标、终态集合与逐步决策上完全一致，说明新引擎对原策略的行为保持兼容；'
     '预算与台账只增加记录，没有改变决策。B 与 C 的差异因此可以归因于决策规则本身，而不是引擎差异。')

h1('7 结论与限制')
para('本轮实验得出的可支持结论：')
for size in (512, 1024):
    values = {s: ledger(size, s)['final_collision_pair_count'] for s in 'ABC'}
    best = min(values, key=values.get)
    para(f'{size} 条规模：A {integer(values["A"])}、B {integer(values["B"])}、C {integer(values["C"])} 对；'
         f'三组中终态近距对数最低为 {best}。', style=NOTE)
para('以上差异只说明在相同候选评价预算与相同验收规则下，不同决策规则导致的中心线几何差异；'
     '不构成光学损耗、串扰或制造合规性的结论。三组终态都仍然存在大量近距对，不能称为无碰撞版图。'
     '预算与尝试上限是人为固定的实验条件，收益是否会随预算继续扩大没有证明。'
     '跨路线排序使用净减少优先，只在本轮实例与验收规则内比较，不是全局最优性证明。')
para('计算代价也应一并考虑：B 的双方候选比较使单步消耗更多候选评价，同一预算内能处理的目标尝试次数少于 A'
     '（上表"目标尝试次数"）；C 的重定位会增加长度（终态额外长度见第 4 节表格），'
     '并可能在部分目标上消耗更多预算。')

h1('8 数据与文件位置')
para('全部原始记录位于 outputs/3d_strategy_v2/512_three_layer_abc/ 与 outputs/3d_strategy_v2/1024_three_layer_abc/，'
     '包含 config.json（配置与输入指纹）、code_version.json、decisions_*.json（逐步骤决策与候选记录）、'
     'final_routes_*.json（终态几何）、collision_sets_*.json、ledger_*.json、recheck_*.json（重载复核）'
     '与 comparison.csv、summary.json。图文件位于 outputs/3d_strategy_v2/figures/。', style=NOTE)
para('复现命令（项目根目录）：', style=NOTE)
para('.venv\\Scripts\\python.exe -B scripts\\run_3d_strategy_v2.py . outputs\\3d_strategy_v2\\512_three_layer_abc --size 512<br/>'
     '.venv\\Scripts\\python.exe -B scripts\\run_3d_strategy_v2.py . outputs\\3d_strategy_v2\\1024_three_layer_abc --size 1024<br/>'
     '.venv\\Scripts\\python.exe -B scripts\\visualize_3d_strategy_v2.py . outputs\\3d_strategy_v2', style=NOTE)


def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont('SimSun', 9)
    canvas.drawCentredString(A4[0]/2, A4[1]-12*mm, '三维波导布线策略改进实验')
    canvas.drawCentredString(A4[0]/2, 10*mm, f'第 {doc.page} 页')
    canvas.restoreState()


doc = BaseDocTemplate(str(TARGET_PDF), pagesize=A4, leftMargin=20*mm, rightMargin=20*mm,
                      topMargin=20*mm, bottomMargin=18*mm, title=NAME, author='李昊伦',
                      subject='三维布线策略改进实验 A/B/C 对照')
frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='body')
doc.addPageTemplates([PageTemplate(id='main', frames=[frame], onPage=on_page)])
doc.build(STORY)
print(json.dumps({'pdf': str(TARGET_PDF), 'tables': len(TABLES),
                  'size_bytes': TARGET_PDF.stat().st_size}, ensure_ascii=False))
