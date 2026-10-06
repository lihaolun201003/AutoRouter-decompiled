# -*- coding: utf-8 -*-
"""生成「TOA-cos 论文精读」16 页讲解型 PPT。

套用 Linsgroup_PPT.pptx 的上海交大蓝白模板：add_slide 到模板版式，
因此母版、页眉蓝色标题栏、校徽、页脚校门线稿、配色与字体规范全部继承。
"""
import os
import sys

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deck_lib import (BAND, BAND2, BLUE, BORDER, GBLUE, GREEN, MAUVE, MUTED,
                      NAVY, RED, TEAL, TEXT, WHITE, arrow, badge, blank_slide,
                      bullets, caption, card, chip, est_h, fig, note, rect,
                      rich_at, set_font, set_title, text_at)

ROOT = r'C:\Users\lihao\Desktop\Graduation Project'
TPL = os.path.join(ROOT, 'Linsgroup_PPT.pptx')
OUT = os.path.join(ROOT, 'TOA-cos论文精读_讲解型汇报.pptx')
FIG = os.path.join(ROOT, 'work', 'crop')

L_COVER, L_TITLE = 0, 7
X0, XR = 0.55, 12.88
CW = XR - X0
SRC_LONG = 'Fengrui Yu et al., Adv. Photonics Res. 2026'
RED_BG = RGBColor(0xFD, 0xF2, 0xF2)
GREEN_BG = RGBColor(0xEE, 0xF8, 0xF2)

prs = Presentation(TPL)
for sid in list(prs.slides._sldIdLst):
    prs.part.drop_rel(sid.get(
        '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'))
    prs.slides._sldIdLst.remove(sid)


def new(title, layout=L_TITLE):
    s = blank_slide(prs, layout)
    set_title(s, title)
    return s


def srcnote(slide, l, t, w, num):
    txt = (f'图源：{SRC_LONG}, Fig. {num}' if w >= 4.6
           else f'图源：Adv. Photonics Res. 2026, Fig. {num}')
    return caption(slide, l, t, w, txt, size=11, color=GBLUE)


def kv_card(slide, l, t, w, h, head, sym, val, desc):
    card(slide, l, t, w, h)
    text_at(slide, l + 0.20, t + 0.48, w - 0.40, 0.34, head, size=18, bold=True, color=BLUE)
    rich_at(slide, l + 0.20, t + 0.85, w - 0.40, 0.30, [(sym, True, GBLUE)], size=15)
    text_at(slide, l + 0.20, t + 1.15, w - 0.40, 0.34, val, size=15, bold=True, color=RED)
    text_at(slide, l + 0.20, t + 1.50, w - 0.40, 0.60, desc, size=13, color=MUTED, line=1.30)


def card_title(slide, l, t, w, text, size=18, color=BLUE):
    """卡片内标题：放在左上角平行四边形角标之下，避免压住角标。"""
    return text_at(slide, l + 0.30, t + 0.48, w - 0.60, 0.36, text,
                   size=size, bold=True, color=color)


# ================================================================ P1 封面
s = prs.slides.add_slide(prs.slide_layouts[L_COVER])
for sh in list(s.shapes):
    if not sh.is_placeholder:
        continue
    if abs(sh.top - Inches(2.20)) < Inches(0.25):
        tf = sh.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        for r in list(p.runs):
            r._r.getparent().remove(r._r)
        r = p.add_run()
        r.text = '超紧凑低损耗 3D 玻璃光波导芯片'
        set_font(r, 40, True, BLUE)
    elif abs(sh.top - Inches(4.82)) < Inches(0.30):
        tf = sh.text_frame
        p = tf.paragraphs[0]
        for r in list(p.runs):
            r._r.getparent().remove(r._r)
        r = p.add_run()
        r.text = '文献精读汇报'
        set_font(r, 18, False, BLUE)
    else:
        sh._element.getparent().remove(sh._element)

text_at(s, 1.17, 4.02, 10.99, 0.45,
        '飞秒激光直写（FLDW）+ TOA-cos 弯曲波导：给多芯光纤与 1.6T 光模块之间做一块“翻译器”',
        size=16, color=NAVY, align=PP_ALIGN.CENTER)
text_at(s, 1.17, 6.36, 10.99, 0.35,
        f'{SRC_LONG}  |  DOI: 10.1002/adpr.70241',
        size=11, color=GBLUE, align=PP_ALIGN.CENTER)

note(s, [
    '开场（约 30 秒）：',
    '今天讲的这篇论文来自上海交大区域光纤通信网与新型光通信系统国家重点实验室，通讯作者是马麟老师，第一作者于丰瑞，发表在 Advanced Photonics Research 2026。',
    '题目是《Ultra-Compact Low-Loss 3D Glass Waveguide Chip Using Femtosecond Laser Writing Technique》——超紧凑、低损耗、3D 玻璃光波导芯片。',
    '我先说结论：这块芯片只有 2.5 乘 2.0 平方毫米，插损 0.54 dB，是目前用飞秒激光直写在玻璃里做出来的、面积最小的多芯光纤扇入扇出器件。',
    '但今天我更想讲清楚的，不是这个数字，而是“这个数字是怎么被逼出来的”——它的创新逻辑，对我后面做 3D 波导路由非常有参考价值。',
])

# ================================================================ P2 一句话贡献
s = new('一句话讲清：这篇文章到底做了什么')
rect(s, X0, 1.08, CW, 1.62, fill=BAND, line=None)
text_at(s, X0 + 0.40, 1.20, CW - 0.80, 1.38,
        '在玻璃里用飞秒激光“刻”出弯曲波导，靠 cosine 曲线 + lateral offset + trench 三招合一，'
        '把 4 芯光纤的扇入/扇出（FI/FO）器件做到 0.54 dB 插损、2.5 × 2.0 mm² 面积。',
        size=20, bold=True, color=NAVY, line=1.34, anchor=MSO_ANCHOR.MIDDLE)

for x, v, u, lab, vs in [(0.55, '0.54', 'dB', '四通道最大插入损耗 @1310 nm', 34),
                         (3.68, '83', '%', '较圆弧 S 弯，TE 插损降幅', 34),
                         (6.81, '0.13', 'dB/cm', '直波导传播损耗', 34),
                         (9.94, '2.5×2.0', 'mm²', '芯片面积，FLDW 玻璃基最小', 26)]:
    chip(s, x, 2.88, 2.94, 1.42, v, u, lab, vsize=vs, fill=BAND2)

card(s, X0, 4.36, CW, 2.54)
card_title(s, X0, 4.36, CW, '为什么这篇文章值得讲')
bullets(s, X0 + 0.35, 5.32, CW - 0.70, [
    '它不是把工艺参数调得更好，而是提出新结构 TOA-cos：把 mode mismatch loss 当成可设计的对象。',
    '它面对的是 AI 数据中心最现实的接口问题：多芯光纤（MCF）与 1.6T 光模块之间原本没有“翻译器”。',
    '它的结论可核对：把总插损拆成四项后逐项核算，理论 0.37 dB、实测 0.50 dB，仿真与实验互相印证。',
], size=15, gap=0.22)

note(s, [
    '这一页是整场的“电梯陈述”。如果听众只能记住一页，就记这一页。',
    '一句话版本：给 4 芯光纤做一块 2.5×2.0 平方毫米的“扇入扇出”芯片，插损 0.54 dB，靠的是 cosine 曲线、横向偏移、辅助槽三招合一，论文里把它叫 TOA-cos。',
    '四个数字分别是什么：0.54 dB 是四个通道里最差那个的插损，1310 纳米；83% 是同样尺寸下，把传统圆弧 S 弯的 3.0 dB 降到 0.50 dB 的降幅；0.13 dB/cm 和 0.06 dB/facet 是直波导的传播损耗和单端面耦合损耗，这是“打好地基”。',
    '注意第三点——理论 0.37 dB、实测 0.50 dB。论文用这个差值反推算出残余的 mode mismatch loss 只有 0.13 dB。这说明作者不是“碰巧做出一个好器件”，而是有一个能算得清楚的模型。',
])

# ================================================================ P3 背景
s = new('AI 数据中心要 1.6T，可“多加几根光纤”已经走不通了')

rows = [
    ('老办法 ①：增加光纤根数',
     '通道数上去了，但系统复杂度同步上升，可靠性下降，机柜里的布线也支撑不住。',
     '复杂度 ↑  可靠性 ↓', RED),
    ('老办法 ②：提高单纤速率（CWDM 加波道）',
     '单纤 400 Gbit/s 时色散变得严重，传输距离被压缩，长距离 AI 集群用不了。',
     '色散 ↑  距离 ↓', RED),
    ('新答案：多芯光纤 MCF（space division multiplexing）',
     '同样的包层直径里塞进多根纤芯，用“空间”这个新维度换带宽，同时保住光纤数量不变。',
     '同包层直径 · 多芯 · 单波长长距离', GREEN),
]
y = 1.12
for head, desc, tag, col in rows:
    card(s, X0, y, 7.30, 1.80)
    text_at(s, X0 + 0.30, y + 0.46, 6.70, 0.35, head, size=17, bold=True, color=col)
    text_at(s, X0 + 0.30, y + 0.86, 6.70, 0.60, desc, size=14, color=TEXT, line=1.32)
    text_at(s, X0 + 0.30, y + 1.48, 6.70, 0.28, tag, size=13, bold=True, color=GBLUE)
    y += 1.95

rect(s, 8.10, 1.12, 4.78, 5.71, fill=BAND2, line=BORDER)
text_at(s, 8.35, 1.32, 4.30, 0.35, '新的麻烦：两边的“间距”不一样', size=15, bold=True, color=BLUE)
text_at(s, 8.35, 1.80, 4.30, 0.30, 'MCF 多芯光纤：芯距 40 μm', size=13, bold=True, color=NAVY)
for k in range(4):
    rect(s, 8.55 + k * 0.62, 2.16, 0.44, 0.44, fill=BLUE, shape=MSO_SHAPE.OVAL)
text_at(s, 8.35, 2.68, 4.30, 0.28, '4 根纤芯挤在微小间距里', size=11.5, color=MUTED)

arrow(s, 10.42, 3.02, 0, 0.42, color=RED, lw=2.0)
text_at(s, 8.35, 3.08, 2.0, 0.32, '必须换间距', size=13, bold=True, color=RED)
text_at(s, 10.58, 3.08, 2.30, 0.32, '→  FI/FO 扇入/扇出', size=13, bold=True, color=BLUE)

text_at(s, 8.35, 3.64, 4.30, 0.30, '光模块内波导阵列：间距 127 μm', size=13, bold=True, color=NAVY)
for k in range(4):
    rect(s, 8.48 + k * 1.06, 4.00, 0.40, 0.40, fill=TEAL, shape=MSO_SHAPE.OVAL)
text_at(s, 8.35, 4.50, 4.30, 0.28, '要对接标准单模光纤与硅光波导', size=11.5, color=MUTED)

rect(s, 8.35, 4.94, 4.30, 1.66, fill=BAND, line=None)
text_at(s, 8.58, 5.10, 3.85, 1.40,
        'FI/FO 的活，就是把这 4 根芯从 40 μm 间距“摊开”到 127 μm，'
        '并且在这个过程中不能把光损耗掉。',
        size=14, color=NAVY, line=1.34, anchor=MSO_ANCHOR.MIDDLE)

note(s, [
    '先讲“为什么需要这个东西”。',
    'AI 集群的带宽需求把光模块推到了 1.6T。传统有两条路：一是堆光纤根数，二是加波道做 CWDM。第一条路让系统复杂度和可靠性变差；第二条路在单纤 400 Gbit/s 时色散严重，传输距离被压得很短。',
    '所以工业界转向多芯光纤 MCF——包层直径不变，里面做成多根纤芯，用空间维度换带宽。这是这一轮光互连里很重要的方向。',
    '但 MCF 引出一个新麻烦：MCF 的芯距只有 40 微米左右；而光模块内部，无论是对接单模光纤还是硅光波导阵列，间距是 127 微米量级。',
    '两边对不上，中间就必须有一个器件把间距“摊开”，这个器件就是 FI/FO——fan-in / fan-out，扇入扇出。它是 MCF 落到实处的咽喉。',
])

# ================================================================ P4 问题
s = new('难在哪：空间预算以毫米计，损耗预算只有零点几 dB')

card(s, X0, 1.06, 6.05, 2.52)
card_title(s, X0, 1.06, 6.05, '约束一 · 空间')
rich_at(s, X0 + 0.30, 1.96, 5.45, 0.55,
        [('2.5 × 2.0', True, BLUE), ('  mm²', True, GBLUE)], size=28)
text_at(s, X0 + 0.30, 2.53, 5.45, 0.30, '本文最终做到的面积', size=12.5, color=MUTED)
bullets(s, X0 + 0.30, 2.88, 5.45, [
    '模块内部要和驱动器、TIA、封装抢空间',
    '所以 FI/FO 必须做到 mm² 量级，并能贴装进模块',
], size=12.5, gap=0.12, mcolor=BLUE)

card(s, 6.83, 1.06, 6.05, 2.52)
card_title(s, 6.83, 1.06, 6.05, '约束二 · 损耗')
rich_at(s, 7.13, 1.96, 5.45, 0.55,
        [('< 1', True, BLUE), ('  dB', True, GBLUE)], size=28)
text_at(s, 7.13, 2.53, 5.45, 0.30, '这是 FI/FO 能分到的损耗额度', size=12.5, color=MUTED)
bullets(s, 7.13, 2.88, 5.45, [
    '整条链路功率预算有限，而 FI/FO 是无源器件，自己不发光',
    '超了额度就要牺牲链路裕量，或额外加放大器',
], size=12.5, gap=0.12, mcolor=BLUE)

rect(s, X0, 3.74, CW, 1.34, fill=RED_BG, line=None)
text_at(s, X0 + 0.35, 3.88, 11.63, 0.34,
        '两条约束在这里正面冲突', size=17, bold=True, color=RED)
rich_at(s, X0 + 0.35, 4.28, 11.63, 0.64,
        [('想省空间', True, NAVY), ('  →  ', False, MUTED),
         ('弯曲半径 R 必须做小', True, NAVY), ('  →  ', False, MUTED),
         ('但 R 越小，弯曲损耗越大', True, RED),
         ('。这是一道“小半径 × 低损耗”的联立方程。', False, TEXT)], size=16, line=1.30)

for x, v, u, lab in [(0.55, '190.5', 'μm', '本文 S 弯的输入/输出中心距 Δx'),
                     (4.74, '1400', 'μm', '本文 S 弯的水平路由长度 Δy'),
                     (8.93, '2.62', 'mm', '典型 S 弯的有效弯曲半径 Reff')]:
    chip(s, x, 5.28, 3.95, 1.34, v, u, lab, vsize=32, fill=BAND2)

note(s, [
    '这一页讲“为什么难”。难点不是单点的，是两条硬约束打架。',
    '空间这边：光模块里留给光学的空间非常小，FI/FO 必须做到毫米见方，还要能封装进去。',
    '损耗这边：整条链路有功率预算，FI/FO 是无源器件，自己不分光也不放大，它能占的额度就是零点几 dB。',
    '冲突在哪儿？想省空间，弯曲半径 R 就得做小。而在波导里，弯得越急，光越容易从弯道“漏”出去，损耗越大。所以这本质上是一道“小半径 × 低损耗”的联立方程。',
    '底下三个数字是论文实际用的设计点：Δx 190.5 微米、Δy 1400 微米、有效弯曲半径 2.62 毫米。记住 2.62 毫米这个量级——后面所有关于弯曲损耗的讨论，都是在这个半径下展开的。',
])

# ================================================================ P5 FLDW
s = new('为什么用飞秒激光直写（FLDW），而不是光刻')

fx, fy, fw, fh = fig(s, os.path.join(FIG, 'fig3a.png'), X0, 1.10, 5.55, 2.55,
                     center_in_box=False)
caption(s, X0, fy + fh + 0.06, 5.55,
        '▲ 多次扫描 + 覆写：先在起点覆写 m 次，焦点平移 s 后继续覆写 m 次，共 n 个循环 → m × n × 1 μm')
srcnote(s, X0, fy + fh + 0.62, 5.55, '3(a)')

bullets(s, 6.90, 1.16, 5.98, [
    '原理：飞秒脉冲被物镜聚焦进玻璃内部，焦点处发生非线性吸收，局部折射率被永久改写。',
    '真正的 3D 自由度：焦点可以在玻璃体内任意深度扫描，所以能在同一块玻璃里叠多层波导——这是光刻做不到的。',
    '免掩模、快速原型：改一个弯曲形状，只要改控制程序，不用重做光罩，迭代以小时计。',
    '结构埋在玻璃体内，物理化学稳定性与可靠性高，适合复杂的通信环境。',
], size=14.5, gap=0.22)

card(s, X0, 4.62, CW, 2.26)
card_title(s, X0, 4.62, CW, '有了好工具，还要把“路”修平：本文的工艺优化')
for x, v, u, lab in [(0.95, '4×7×1', 'μm', '最优波导：覆写 4 次 × 7 轨道'),
                     (4.75, '210 mW', '· 200 μm/s', '最优激光功率与扫描速度'),
                     (8.55, '0.25', 'dB', '该配置下直波导插损（PDL < 0.1 dB）')]:
    chip(s, x, 5.48, 3.65, 1.34, v, u, lab, vsize=25, fill=BAND2)

note(s, [
    '工具这一页，回答“为什么是 FLDW”。',
    '飞秒激光直写的原理：把飞秒脉冲用物镜聚焦到玻璃内部，焦点处功率密度极高，发生非线性吸收，材料局部结构被改写，折射率发生变化，于是就形成了一条波导。',
    '它的三个不可替代之处：第一，真正的三维自由度——焦点可以扫描到玻璃内部任意深度，所以可以在同一块玻璃里叠很多层光路，这是平面光刻给不了的；第二，免掩模、迭代快；第三，波导埋在玻璃体内部，不接触空气，稳定性好。',
    '但工具好不等于器件好。波导本身的损耗要压下去。本文用“多次扫描 + 覆写”：在同一点先覆写 m 次，然后把焦点平移 1 微米，再覆写 m 次，一共 n 个循环，总共 m 乘 n 次扫描。',
    '扫参数扫出来的最优配置是 4×7×1 微米：覆写 4 次、7 条平行轨道。条件是 300 kHz 重频、210 毫瓦、200 微米每秒。这样直波导的插损做到 0.25 dB，偏振相关损耗小于 0.1 dB。',
    '注意：这一步是“打地基”，不是本文的创新点。真正的创新在后面弯曲结构上。',
])

# ================================================================ P6 损耗分解
s = new('弯曲损耗不是一个东西，而是几种损耗叠加')

card(s, X0, 1.06, CW, 1.56)
text_at(s, X0 + 0.30, 1.50, 11.6, 0.32,
        '先把总插入损耗写清楚：', size=15, bold=True, color=NAVY)
rich_at(s, X0 + 0.35, 1.90, 11.6, 0.42,
        [('IL = Lp × (ls + lb) + 2Lc + Lb', True, BLUE), ('      (1)', False, MUTED)],
        size=21)
rich_at(s, X0 + 0.35, 2.32, 11.6, 0.36,
        [('Lb ≈ Lr × lb + Lmismatch + Ls × lb', True, BLUE),
         ('      (2)   —— Ls 是侧壁粗糙度带来的散射损耗，仿真中忽略', False, MUTED)], size=16)

for x, head, sym, val, desc in [
        (0.55, '传播损耗', 'Lp', '0.13 dB/cm', '由材料与写入质量决定，靠工艺参数优化，本文已压得很低。'),
        (3.66, '耦合损耗', 'Lc', '0.06 dB/facet', '与标准单模光纤的模场匹配程度决定，说明截面写得好。'),
        (6.77, '辐射损耗', 'Lr', '∝ 弯曲半径 R', '光从弯道“漏”出去，靠提高芯-包折射率对比来压制。'),
        (9.88, '模式失配损耗', 'Lmismatch', '∝ 曲率变化', '曲率突变处两侧模场不匹配；论文认为这一项没被系统解决。')]:
    kv_card(s, x, 2.76, 2.92, 2.16, head, sym, val, desc)

rect(s, X0, 5.02, CW, 1.86, fill=BAND, line=None)
text_at(s, X0 + 0.35, 5.20, 11.6, 0.34, '关键判断', size=17, bold=True, color=BLUE)
rich_at(s, X0 + 0.35, 5.62, 11.6, 0.68,
        [('Lp 和 Lc 已经被工艺优化压到很低', True, NAVY),
         ('（0.13 dB/cm、0.06 dB/facet）。于是', False, TEXT),
         ('弯曲损耗 Lb 成了主要矛盾', True, RED),
         ('，而 Lb 里只剩两项还能打——', False, TEXT),
         ('辐射损耗 Lr 和模式失配损耗 Lmismatch', True, RED),
         ('。把总问题拆到这一步，“该往哪儿使劲”就清楚了。', False, TEXT)], size=15.5, line=1.32)
rich_at(s, X0 + 0.35, 6.38, 11.6, 0.36,
        [('这就是全文的方法论：不对“损耗”这个笼统的数发力，而是对每一项分别设计结构。', False, BLUE)],
        size=14.5)

note(s, [
    '这页是全场的转折点，也是我认为这篇论文最值得学的一页。',
    '论文把弯曲波导的总插入损耗写成两项：IL 等于传播损耗乘总长度，加两端耦合损耗，加弯曲损耗 Lb。而弯曲损耗再拆：Lb 约等于辐射损耗乘弯曲段长度，加模式失配损耗，加散射损耗乘长度。散射损耗来自侧壁粗糙度，仿真里忽略。',
    '拆完你看到四项：传播损耗 0.13 dB/cm，耦合损耗 0.06 dB/facet，这两项靠工艺参数优化，本文已经压得很低了。剩下辐射损耗和模式失配损耗，这两项才是弯曲结构要负责的。',
    '辐射损耗是光在弯道上“漏”出去，半径越小越严重，常规做法是提高芯和包的折射率对比，把光约束得更紧。',
    '模式失配损耗发生在曲率突变的地方——两段曲率不同的波导接在一起，各自的模场不一样，overlap 不好，就产生损耗。',
    '关键判断：前三项论文已经解决得不错，所以 Lb 成为主要矛盾；而 Lb 里，辐射损耗前人做得很多，模式失配损耗没被系统解决。这就是本文的切口。',
    '请大家记住这个“拆解”的动作，最后一页我会把它和 ResNet 类比。',
])

# ================================================================ P7 已有方法
s = new('前人把“提高折射率对比”这条路走透了，却漏了一半')

rows = [
    ['已有方法', '主要压制', '局限'],
    ['提高芯-包折射率对比 [37–39]', '辐射损耗 Lr', '对模式失配损耗无解'],
    ['绝热曲率曲线（Euler / Bézier）[40–42]', '模式失配 Lmismatch', '曲率连续与低曲率变化率难以兼得'],
    ['结点引入横向偏移 offset [43–45]', '模式失配 Lmismatch', '单点使用，未与曲线形状协同'],
    ['抑制壁 / 微裂纹 / 复合波导 [30–36]', '主要降 Lr', '核心仍是提高折射率对比'],
    ['混合热-无热波导 [33]：4.0 mm 处 1.0 dB/cm 记录', '辐射损耗 Lr', '热-无热界面引入很高插损'],
]
tbl = s.shapes.add_table(len(rows), 3, Inches(X0), Inches(1.12),
                         Inches(7.75), Inches(4.15)).table
for i, wdt in enumerate([3.15, 1.55, 3.05]):
    tbl.columns[i].width = Inches(wdt)
for r, row in enumerate(rows):
    tbl.rows[r].height = Inches(0.40 if r == 0 else 0.75)
    for c, val in enumerate(row):
        cell = tbl.cell(r, c)
        cell.margin_left = cell.margin_right = Inches(0.10)
        cell.margin_top = cell.margin_bottom = Inches(0.04)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        cell.fill.solid()
        cell.fill.fore_color.rgb = BLUE if r == 0 else (BAND if r % 2 else WHITE)
        tf = cell.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        for run in list(p.runs):
            run._r.getparent().remove(run._r)
        run = p.add_run()
        run.text = val
        if r == 0:
            set_font(run, 14, True, WHITE)
        elif c == 2:
            set_font(run, 12, False, RED if r in (1, 5) else MUTED)
        elif c == 1:
            set_font(run, 12.5, True, GBLUE)
        else:
            set_font(run, 12.5, False, TEXT)

fx, fy, fw, fh = fig(s, os.path.join(FIG, 'fig11.png'), 8.55, 1.12, 4.33, 3.30,
                     center_in_box=False)
caption(s, 8.55, fy + fh + 0.08, 4.33,
        '▲ 仿真插损地图：白色虚线是 1.0 dB 阈值线。相同 Δx、Δy 下，'
        'TOA-cos 的可工作区域明显比 arc 大。', size=11.5, color=TEXT)
caption(s, 8.55, fy + fh + 0.64, 4.33,
        f'图源：{SRC_LONG}, Fig. 11', size=11, color=GBLUE)

rect(s, X0, 5.52, CW, 1.36, fill=RED_BG, line=None)
text_at(s, X0 + 0.35, 5.66, 11.6, 0.34, '所以真正没被解决的是这一项', size=16, bold=True, color=RED)
rich_at(s, X0 + 0.35, 6.06, 11.6, 0.66,
        [('Mode mismatch loss 至今没有被系统性地最小化', True, RED),
         ('——前人的工作几乎都集中在“提高折射率对比、压制辐射损耗”这一条路上，'
          '而模式失配往往只在单点、单个结构上被顺手处理。这正是本文要补上的那一半。', False, TEXT)],
        size=14.5, line=1.32)

note(s, [
    '这一页是文献综述的“定位”，回答“别人做了什么、没做什么”。',
    '表里五行，前四行是前人方法：提高折射率对比、用绝热曲率曲线、结点加横向偏移、抑制壁/微裂纹/复合波导。最后一行的 Ross-Adams 工作把弯曲半径记录做到 4.0 毫米处 1.0 dB/cm，指标很好，但热-无热波导界面引入了很高的插损。',
    '请看第二列和第三列：所有方法的“主要压制”要么是辐射损耗，要么是单独处理模式失配；而局限那一列，四项里有三项都指向同一个问题——只做了一半。',
    '右边的图是论文的仿真插损地图，横轴 Δx、纵轴 Δy，颜色代表插损。白色虚线是 1.0 dB 阈值线。TOA-cos 那条虚线明显在 arc 之上——意思是同样尺寸下，TOA-cos 需要更小的 Δy 就能做到 1 dB 以内。',
    '结论：模式失配损耗没有被系统性地最小化。注意“系统性”三个字——不是说前人没提过 offset，而是说没人把它和曲线形状、约束增强放在一起做协同设计。这就给本文留出了空间。',
])

# ================================================================ P8 mode mismatch 物理来源
s = new('模式失配从哪来：曲率突变处，模场“错位”了一下')

fx, fy, fw, fh = fig(s, os.path.join(FIG, 'fig2b.png'), 0.62, 1.20, 6.30, 3.70,
                     center_in_box=False)
for rx, ry in [(0.1483, 0.5897), (0.5510, 0.4521), (0.8895, 0.4644)]:
    cx, cy = fx + rx * fw, fy + ry * fh
    rect(s, cx - 0.24, cy - 0.24, 0.48, 0.48, fill=None, line=RED, lw=2.25,
         shape=MSO_SHAPE.OVAL)
caption(s, 0.62, fy + fh + 0.08, 6.30,
        '红圈标出三个曲率不连续点 a、b、c（对应曲率曲线的三处跳变）', size=12, color=RED)
srcnote(s, 0.62, fy + fh + 0.38, 5.55, '2(b)')

bullets(s, 7.25, 1.24, 5.63, [
    '直波导曲率是 0，圆弧段曲率是常数 κ。两者相接的 a、c 点，曲率是“台阶式”跳变。',
    '两段反向圆弧相接的 b 点更极端：曲率从 +κ 直接跳到 −κ，模场被整体“翻转”。',
    '曲率一突跳，两侧的模场分布就不再匹配，能量在接缝处被反射/散射掉——这就是 Lmismatch。',
    '还有第二重错位：弯曲波导里，模场中心会整体向弯曲外侧偏移，所以即使曲率连续，两侧模场中心也已经错开了。',
], size=14.5, gap=0.24)

rect(s, X0, 5.46, CW, 1.42, fill=BAND, line=None)
text_at(s, X0 + 0.35, 5.62, 11.6, 0.32, '于是有两条路可以走', size=16, bold=True, color=BLUE)
rich_at(s, X0 + 0.35, 6.02, 11.6, 0.60,
        [('① 让曲率不要突变', True, NAVY), ('（改曲线形状）；', False, TEXT),
         ('② 把已经错开的模场中心重新对准', True, NAVY), ('（加横向偏移）。', False, TEXT),
         ('本文两个都做了，再加上第三步把光约束得更紧。', False, TEXT)], size=15, line=1.34)

note(s, [
    '这页讲模式失配的物理来源，是理解后面三步设计的前提。',
    '看左边的图，这是三种 S 弯的曲率随路径长度的变化。绿虚线是圆弧 arc，它就是“台阶”：在 a 点从 0 直接跳到常数曲率，在 b 点从正曲率直接跳到负曲率，在 c 点又跳回 0。红圈就是我标出来的这三处。',
    'b 点是最恶劣的，因为曲率符号都反了，等于模场被整体翻了个方向。',
    '曲率一突变，接缝两侧的模场分布就不一样了。两束光要耦合，模场要 overlap 得好；overlap 差，能量就在接缝处被散射或反射掉。这就是模式失配损耗。',
    '还有第二重错位，这一点容易被忽略：在弯曲波导里，模场中心不是待在芯的正中间，而是整体向弯曲的外侧偏移。所以哪怕你把曲率做成连续的，两侧模场中心仍然错开了。',
    '于是本文的思路就很自然：第一条路，让曲率别突变，改曲线形状；第二条路，把已经错开的模场中心重新对准，加横向偏移。第三步再补一个约束增强。',
])

# ================================================================ P9 cosine
s = new('第一步｜把“曲率台阶”换成连续变化的 cosine 曲线')

fx, fy, fw, fh = fig(s, os.path.join(FIG, 'fig2a.png'), 0.62, 1.18, 5.64, 2.90,
                     center_in_box=False)
caption(s, X0, fy + fh + 0.08, 5.70,
        '▲ (a) arc / cosine / raised-sine 三种 S 弯的几何形状', size=12)
srcnote(s, X0, fy + fh + 0.38, 5.55, '2(a)')

bullets(s, 7.20, 1.24, 5.68, [
    'arc 圆弧：曲率是台阶，a、c 点突变 → 模式失配最大，实测插损 3.0 dB。',
    'raised-sine 升余弦：端点曲率为 0，但曲率变化率更大 → 损耗反而更高，所以被排除。',
    'cosine 余弦：曲率连续变化，且变化率更小 → 本文选择它。',
    '代价也要说清楚：cosine 在 a、c 点的曲率不为零，残余的模式失配依然存在，所以还需要第二步。',
], size=14.5, gap=0.22)

rect(s, X0, 4.96, CW, 1.92, fill=BAND, line=None)
text_at(s, X0 + 0.35, 5.12, 5.6, 0.32, 'cosine 曲线的表达式', size=14, bold=True, color=BLUE)
rich_at(s, X0 + 0.35, 5.48, 5.6, 0.36,
        [('f(y) = (Δx/2) · [1 − cos(π·y/Δy)]', True, NAVY), ('   (3)', False, MUTED)], size=15)
text_at(s, 6.60, 5.12, 5.6, 0.32, '有效弯曲半径的定义', size=14, bold=True, color=BLUE)
rich_at(s, 6.60, 5.48, 5.6, 0.36,
        [('Reff = (Δy² + Δx²) / (4Δx)', True, NAVY), ('   (5)', False, MUTED)], size=15)
text_at(s, X0 + 0.35, 6.02, 11.6, 0.72,
        'Δx 是输入与输出波导的中心距，Δy 是 S 弯的水平路由长度。'
        'Reff 的定义是：一个与之有相同 Δx、Δy 的圆弧弯的半径——有了它，不同形状的 S 弯才能放在同一把尺子上比较。',
        size=13, color=TEXT, line=1.32)

note(s, [
    '第一步，改曲线形状。',
    '论文比较了三种：圆弧 arc、余弦 cosine、升余弦 raised-sine。',
    'arc 就是前面说的“台阶”，曲率在两个端点突变，模式失配最大，实测插损 3.0 dB。',
    'raised-sine 有意思——它的曲率在端点正好回到 0，看起来更平滑；但它的曲率变化率更大，中间那段曲率变化太剧烈，最后损耗反而更高。所以被排除了。',
    'cosine 是折中最好的：曲率连续变化，而且变化率更小。所以本文选它。',
    '但作者很诚实：cosine 在 a、c 两点的曲率不为零——你从直波导进到 cosine，曲率还是从一个非零值开始，所以模式失配依然存在。这就逼出了第二步。',
    '下面两个公式要记住：第一个是 cosine 的形状函数；第二个是有效弯曲半径 Reff。Reff 是关键——它把任意形状的 S 弯折算成一个等效圆弧的半径，这样不同曲线才能公平比较。',
])

# ================================================================ P10 offset
s = new('第二步｜曲率归不了零，那就把模场“横向挪回来”')

fx, fy, fw, fh = fig(s, os.path.join(FIG, 'fig1_offset.png'), 0.62, 1.26, 4.30, 3.05,
                     center_in_box=False)
text_at(s, 0.62, fy + fh + 0.08, 4.30, 0.30,
        '▲ 显微放大：接缝处两条白虚线框出错开的波导中心',
        size=11.5, color=TEXT, line=1.30)

bullets(s, 5.35, 1.26, 7.53, [
    '弯曲波导里模场中心向弯曲外侧偏移。相邻两段曲率不同的波导相接，两个模场中心不重合，overlap 下降 → Lmismatch。',
    '做法：在接缝处引入一个精确的横向偏移（lateral offset），把两侧模场中心重新对齐。',
    '关键前提是工艺精度：FLDW 系统的定位精度是 0.1 μm，所以这种亚微米级的偏移可以被稳定复现出来。',
    '偏移的最优值随弯曲半径变化，需要按 R 分别优化；仿真显示 ±0.2 μm 的制造偏差引起的插损波动可以忽略 → 设计对工艺容差鲁棒。',
], size=14.5, gap=0.24)

rect(s, X0, 4.80, CW, 2.08, fill=BAND2, line=None)
text_at(s, X0 + 0.35, 4.96, 11.6, 0.34, '为什么这一招成立', size=17, bold=True, color=BLUE)
rich_at(s, X0 + 0.35, 5.38, 11.6, 0.68,
        [('它管的是“结果”而不是“原因”', True, NAVY),
         ('——前面 cosine 已经让曲率变连续了，但 cosine 端点的残余曲率、以及弯曲引起的模场外移，'
          '这两件事都让模场中心对不上。offset 不去纠结曲率，直接把对不准的模场中心搬回来，所以它能和任何曲线形状叠加使用。',
          False, TEXT)], size=14.5, line=1.32)
chip(s, 0.95, 6.02, 5.45, 0.86, '0.1', 'μm', 'FLDW 系统定位精度', vsize=21, fill=WHITE)
chip(s, 6.85, 6.02, 5.45, 0.86, '±0.2', 'μm', '制造偏差下的插损波动可忽略', vsize=21, fill=WHITE)

note(s, [
    '第二步，横向偏移。这一招解决的是“原因之外的那部分”问题。',
    '前面 cosine 让曲率连续了，但还有两件事让模场中心对不上：一是 cosine 在端点的曲率不为零；二是弯曲波导本身会让模场中心向外侧偏移。',
    'offset 的思路是：不去纠结曲率了，直接把对不准的模场中心搬回来。在直波导和弯曲波导的接缝处，给一个精确的横向偏移量，让两侧模场中心重新重合，overlap 就上去了。',
    '左边这张显微照片就是证据：上下两条白虚线框出的两段波导中心，它们明显错开了一段——这个错位就是设计好的 offset。',
    '这一招能用的前提是工艺精度。飞秒激光直写系统的定位精度是 0.1 微米，所以亚微米级的偏移可以稳定复现。反过来，如果工艺精度不够，这个设计就只是纸面上的。',
    '还有一个工程上很重要的点：最优偏移量随弯曲半径变化，要按半径分别优化；但仿真显示，±0.2 微米的制造偏差引起的插损波动可以忽略，说明设计对工艺容差是鲁棒的。',
])

# ================================================================ P11 trench
s = new('第三步｜在芯两侧挖槽，把光“按”回芯里')

fx, fy, fw, fh = fig(s, os.path.join(FIG, 'fig5.png'), 0.62, 1.22, 3.80, 3.62,
                     center_in_box=False)
text_at(s, 0.62, fy + fh + 0.10, 3.80, 0.34,
        '▲ 实测折射率分布：芯 +0.0065，槽 −0.0059', size=11.5, color=TEXT, line=1.28)
srcnote(s, 0.62, fy + fh + 0.42, 3.80, '5')

bullets(s, 4.85, 1.26, 8.03, [
    '思路：在芯的两侧写入折射率降低区（trench），把正折射率的芯“夹”在两条负折射率的槽中间，等效提高横向折射率对比。',
    '对比更强 → 模式约束更强 → 光更难从弯道泄漏到辐射模 → 辐射损耗 Lr 下降。',
    '与已有的 bend-loss-suppression wall 不同：本文靠的是槽内的负折射率对比，而不是应力引起的折射率改变。',
    '槽间距固定 20 μm，尽量不影响导波特性；槽本身按 1×7×1 μm 波导写入，不额外增加太多加工时间。',
], size=14.5, gap=0.22)

fx2, fy2, fw2, fh2 = fig(s, os.path.join(FIG, 'fig6.png'), 4.85, 4.42, 4.55, 2.10,
                         center_in_box=False)
text_at(s, 4.85, fy2 + fh2 + 0.06, 4.55, 0.28,
        '▲ 标准波导 (a) 与加槽波导 (b) 的模场对比', size=11.5, color=TEXT)

card(s, 9.68, 4.42, 3.20, 2.36)
text_at(s, 9.98, 4.88, 2.62, 0.30, '加槽改变了模场吗？', size=15, bold=True, color=BLUE)
rich_at(s, 9.98, 5.22, 2.62, 0.62,
        [('99.9', True, BLUE), (' %', True, GBLUE)], size=32)
text_at(s, 9.98, 5.88, 2.62, 0.80,
        '标准波导与加槽波导的模场重叠积分高达 99.9%：加槽几乎不改变模场分布，只增强约束。',
        size=12, color=TEXT, line=1.30)

note(s, [
    '第三步，辅助槽。这一招管的是辐射损耗。',
    '做法是在波导芯的两侧，用同样的飞秒激光写入两条折射率降低的区域，也就是负折射率的槽。这样正折射率的芯就被夹在两条负折射率的槽中间。',
    '效果等价于提高了横向的折射率对比。对比度一高，模式约束就强，光更难从弯道泄漏到辐射模里去，辐射损耗就下来了。',
    '这里要强调一个区别：前人有一种做法叫 bend-loss-suppression wall，也是挖结构，但它靠的是应力引起的折射率改变；本文的槽靠的是槽本身写入后的负折射率对比，机理不一样。',
    '左边这张图是实测的折射率分布，用原位三维折射率成像系统测的：芯是正 0.0065，槽是负 0.0059。这个数据后面直接喂给仿真。',
    '右下角是“怎么证明加槽没有帮倒忙”。它对比了标准波导和加槽波导的模场，两者的重叠积分是 99.9%。意思是加槽几乎没有改变模场分布，只是把约束加强了——所以它可以自由地和别的设计叠加。',
])

# ================================================================ P12 TOA-cos 总结构
s = new('三种机制合体：Trench + Offset + Assisted-cosine = TOA-cos')

fx, fy, fw, fh = fig(s, os.path.join(FIG, 'fig1_full.png'), 0.62, 1.18, 7.25, 4.54,
                     center_in_box=False)
for txt, rx, ry, tw in [('lateral offset', 0.055, 0.10, 1.32),
                        ('cosine curve', 0.185, 0.655, 1.26),
                        ('auxiliary trench', 0.735, 0.815, 1.62)]:
    tx, ty = fx + rx * fw, fy + ry * fh
    box = rect(s, min(tx, 7.62 - tw), ty, tw, 0.28, fill=RED)
    tf = box.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = txt
    set_font(r, 11, True, WHITE)
srcnote(s, 0.62, fy + fh + 0.08, 5.55, '1')

for letter, sub, desc, ty in [
        ('T', 'Trench-assisted', '两侧负折射率槽，提高横向折射率对比 → 压制辐射损耗 Lr。', 1.18),
        ('O', 'Offset-assisted', '接缝处精确横向偏移，对准偏移后的模场中心 → 压制模式失配 Lmismatch。', 2.70),
        ('A-cos', 'assisted cosine', 'cosine 曲线让曲率连续、变化率低 → 从源头上减少模式失配的产生。', 4.22)]:
    card(s, 8.05, ty, 4.83, 1.46)
    rich_at(s, 8.30, ty + 0.44, 4.35, 0.46,
            [(letter, True, BLUE), ('  =  ', True, GBLUE), (sub, True, NAVY)], size=19)
    text_at(s, 8.30, ty + 0.94, 4.35, 0.48, desc, size=13, color=TEXT, line=1.28)

rect(s, 8.05, 5.80, 4.83, 1.08, fill=GREEN_BG, line=None)
text_at(s, 8.30, 5.92, 4.35, 0.30, '而且是可叠加的', size=13.5, bold=True, color=GREEN)
text_at(s, 8.30, 6.22, 4.35, 0.60,
        'TOA-cos 与已有的 FLDW 降损耗方法（微裂纹、复合波导、应力工程）兼容，可以叠在一起用。',
        size=12, color=TEXT, line=1.26)

note(s, [
    '这一页把三个机制合起来，解释名字的来历。',
    '图上三个红标：lateral offset 在接缝处，cosine curve 是弯曲的形状，auxiliary trench 是芯两侧的槽。',
    'TOA-cos 就是这三个词的首字母：T 是 Trench-assisted，辅助槽；O 是 Offset-assisted，辅助偏移；A-cos 是 assisted cosine，辅助余弦曲线。',
    '三者的分工要讲清楚：cosine 是从源头减少模式失配的产生——它让曲率连续；offset 是收拾残局——对已经错开的模场中心做补偿；trench 管的是另一类损耗——它压辐射损耗。',
    '所以这不是三个技巧的随意堆叠，而是分别对应前面拆出来的那两项损耗：cosine 和 offset 打 Lmismatch，trench 打 Lr。这就是“把总问题拆开、再逐项设计”的完整落地。',
    '右下角还有一点很重要：它是可叠加的。和已有的微裂纹、复合波导、应力工程都兼容，所以这个结构不是替代别人，而是可以和别人一起用。这大大提高了它的实用性。',
])

# ================================================================ P13 仿真
s = new('仿真怎么调参：槽深 10 μm、偏移量随半径配、辐射损耗砍半')

PY = 1.42
for bx in (0.62, 3.33, 8.22):
    badge(s, bx, PY - 0.36, (0.62, 3.33, 8.22).index(bx) + 1)
fig(s, os.path.join(FIG, 'fig7a.png'), 0.62, PY, 2.30, 3.20, center_in_box=False)
fig(s, os.path.join(FIG, 'fig7b.png'), 3.33, PY, 4.20, 3.20, center_in_box=False)
fig(s, os.path.join(FIG, 'fig7c.png'), 8.22, PY, 4.20, 3.20, center_in_box=False)
srcnote(s, 0.62, PY + 3.26, 5.55, '7')

for i, (head, desc) in enumerate([
        ('① 槽深 h 怎么定',
         '插损在 h = 10.0 μm 时最小，且与弯曲半径无关；h < 10 μm 时导模会与槽的亮区发生倏逝耦合，'
         '插损反而升高。Reff > 3.8 mm 后出现平台 —— 槽主要对小半径有效。'),
        ('② 横向偏移 offset 怎么定',
         '加了最优 offset 后插损明显更低，且最优值随 Reff 变化。误差棒对应 ±0.2 μm 的制造偏差，'
         '引起的波动很小 → 设计鲁棒。'),
        ('③ 辐射损耗降了多少',
         '加槽（TA）波导的辐射损耗明显低于不加槽的波导。1.0 dB/cm 的截止半径做到 '
         '2.5 mm @1310 nm、4.0 mm @1550 nm。')]):
    x = 0.62 + i * 4.13
    card(s, x, 5.02, 3.95, 1.90)
    text_at(s, x + 0.24, 5.48, 3.50, 0.30, head, size=14.5, bold=True, color=BLUE)
    text_at(s, x + 0.24, 5.86, 3.50, 0.95, desc, size=12, color=TEXT, line=1.30)

note(s, [
    '这一页讲仿真，回答“这三个参数是怎么定下来的”。',
    '论文用的仿真方法是 BPM，光束传播法，输入是前面实测的折射率分布——芯正 0.0065、槽负 0.0059。',
    '第一张图，槽深 h 的优化。横轴是槽深，纵轴是插损，每条曲线对应一个不同的有效弯曲半径。结论：h 等于 10 微米时插损最小，而且这个最优值跟半径无关。另外两个细节：槽深不足 10 微米时，导模会和槽的亮区发生倏逝耦合，插损反而升高；而 Reff 大于 3.8 毫米以后曲线出现平台，说明槽主要对小半径有效。',
    '第二张图，横向偏移的优化。绿色是不加 offset，蓝色是加最优 offset。加了以后插损明显下降，而且最优偏移量随半径变化，所以要按半径配。误差棒对应正负 0.2 微米的制造偏差，波动很小。',
    '第三张图，辐射损耗。加槽的 TA 波导明显低于不加槽的波导。1.0 dB/cm 这个截止半径做到了 2.5 毫米，1310 纳米；1550 纳米是 4.0 毫米。这是量化 Lr 被压下去的直接证据。',
])

# ================================================================ P14 实验对比
s = new('实测对比：同样尺寸，插损从 3.0 dB 降到 0.50 dB')

text_at(s, X0, 1.04, 12.3, 0.28,
        '测试条件：Δx = 190.5 μm，Δy = 1400 μm，总长 10 mm，波长 1310 nm，Reff = 2.62 mm',
        size=12.5, bold=True, color=NAVY)
for i, ((fn, name, cn), (v, u, col)) in enumerate(zip(
        [('fig8a.png', 'arc', '传统圆弧 S 弯'),
         ('fig8b.png', 'cosine', '余弦 S 弯'),
         ('fig8c.png', 'TOA-cos', '本文结构')],
        [('3.0', 'dB', RED), ('1.0', 'dB', MAUVE), ('0.50', 'dB', GREEN)])):
    x = 0.62 + i * 4.30
    fig(s, os.path.join(FIG, fn), x, 1.40, 3.48, 3.30, center_in_box=False)
    text_at(s, x, 4.80, 3.48, 0.34, name, size=17, bold=True, color=col, align=PP_ALIGN.CENTER)
    rect(s, x + 0.44, 5.18, 2.60, 0.72, fill=BAND2, line=BORDER)
    rich_at(s, x + 0.44, 5.18, 2.60, 0.72, [(v, True, col), (' ' + u, True, GBLUE)],
            size=27, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    text_at(s, x, 5.96, 3.48, 0.28, cn + ' · TE 模式插入损耗', size=12, color=MUTED,
            align=PP_ALIGN.CENTER)
srcnote(s, X0, 6.24, 5.55, '8')

rect(s, X0, 6.46, CW, 0.52, fill=GREEN_BG, line=None)
text_at(s, X0 + 0.25, 6.50, 11.9, 0.44,
        '损耗核算：耦合 0.06×2 = 0.12 dB ＋ 传播 0.13 dB/cm×1.0 cm = 0.13 dB ＋ '
        '辐射 0.85 dB/cm×1.4 cm = 0.12 dB ＝ 0.37 dB 理想值 → 与实测 0.50 dB 的差值即残余 '
        'Lmismatch ≈ 0.13 dB',
        size=11.5, bold=True, color=GREEN, line=1.28)

note(s, [
    '这一页是实验对比，也是全文最有说服力的一页。',
    '测试条件统一：Δx 190.5 微米，Δy 1400 微米，总长 10 毫米，波长 1310 纳米，有效弯曲半径 2.62 毫米。三个器件尺寸完全一样，只改结构。',
    '结果是：传统圆弧 S 弯 TE 模式插损 3.0 dB；换成 cosine 降到 1.0 dB；换成 TOA-cos 降到 0.50 dB。相对传统圆弧降低 83%。',
    '注意这个阶梯：从 3.0 到 1.0 是“改曲线形状”的功劳，也就是 cosine；从 1.0 到 0.50 是“offset 加 trench”的功劳。两步各自贡献了一半左右的改善。',
    '最下面这条绿色带子是损耗核算，非常漂亮：耦合损耗两端共 0.12 dB，传播损耗 0.13 dB，辐射损耗 0.12 dB，加起来 0.37 dB，这是理想值。实测 0.50 dB，差值 0.13 dB，论文把它算作残余的模式失配损耗。',
    '这说明这个模型是能算的、可信的，不是碰运气。而且残余的 Lmismatch 已经被压到 0.13 dB。',
    '另外论文还提到：TM 模式的插损随着半径减小会变得更明显，因为 TM 模的约束更弱、更容易泄漏，所以 PDL 会随半径减小而增大。这是这个方案的一个已知特性。',
])

# ================================================================ P15 器件指标
s = new('做出来的器件：0.54 dB、2.5 × 2.0 mm²，FLDW 玻璃基最小')

fig(s, os.path.join(FIG, 'fig9a.png'), 0.62, 1.16, 6.35, 2.58, center_in_box=False)
text_at(s, 0.62, 3.82, 6.35, 0.28,
        '▲ (a) 四通道 FI/FO 显微图：1.5 mm 弯曲段 + 两端各 0.5 mm 直波导',
        size=11.5, color=TEXT)
srcnote(s, 0.62, 4.12, 5.00, '9')
fig(s, os.path.join(FIG, 'fig9b.png'), 0.62, 4.44, 2.98, 2.08, center_in_box=False)
fig(s, os.path.join(FIG, 'fig9c.png'), 3.80, 4.44, 3.17, 2.08, center_in_box=False)
text_at(s, 0.62, 6.60, 6.35, 0.24,
        '▲ (b) 实物照片：2.5 × 2.0 mm²　(c) 四通道光谱', size=11, color=TEXT)

rich_at(s, 7.28, 1.14, 5.60, 0.85,
        [('0.54', True, BLUE), ('  dB', True, GBLUE)], size=46)
text_at(s, 7.28, 2.04, 5.60, 0.30, '四通道最大插入损耗（@1310 nm，全通道 < 0.54 dB）',
        size=12.5, color=MUTED)
rich_at(s, 7.28, 2.44, 5.60, 0.78,
        [('2.5 × 2.0', True, BLUE), ('  mm²', True, GBLUE)], size=36)
text_at(s, 7.28, 3.28, 5.60, 0.30, '芯片面积（迄今 FLDW 玻璃基 FI/FO 最小）', size=12.5, color=MUTED)

card(s, 7.28, 3.78, 5.60, 3.12)
text_at(s, 7.96, 4.02, 4.60, 0.32, '器件参数与扩展验证', size=15, bold=True, color=BLUE)
bullets(s, 7.58, 4.44, 5.00, [
    '结构：4 通道；MCF 侧芯距 40 μm，光模块侧波导间距 127 μm；最小有效弯曲半径 Reff = 3.34 mm。',
    '带宽：四个通道的光谱覆盖整个通信波段，可全波段使用。',
    '大角度扩展验证：Δx = 8.0 mm、Δy = 4.0 mm 时 TE 插损 0.60 dB、PDL 0.15 dB。',
    '作者自述的局限：尚未与 MCF 和光子芯片实际集成（此前工作表明装配损耗可接受）；纵向尺寸仍可优化，如改用高 NA 物镜。',
], size=12.5, gap=0.16, mcolor=BLUE)

note(s, [
    '这一页是最终器件指标。',
    '左边是器件的显微图和实物照片。图 (a) 上能看到四条弯曲波导，每一条通道由 1.5 毫米的弯曲段加上两端各 0.5 毫米的直波导组成。图 (b) 是实物照片——芯片只有 2.5 乘 2.0 平方毫米，放在指尖上。图 (c) 是四个通道的光谱。',
    '核心指标两个：第一，四个通道的插损全部小于 0.54 dB，1310 纳米；第二，面积 2.5 乘 2.0 平方毫米，这是目前用飞秒激光直写在玻璃基上做出来的 FI/FO 里面积最小的。',
    '结构参数：MCF 侧芯距 40 微米，光模块侧波导间距 127 微米，最小有效弯曲半径 3.34 毫米。注意论文这里做了一个工程上的取舍：只有在小半径处（Reff = 3.34 毫米）才用 TOA-cos，半径大的地方还用普通 cosine S 弯——因为前面仿真说了，槽只对小半径有效。',
    '带宽上覆盖了整个通信波段。另外还验证了大角度扩展能力：Δx 8 毫米、Δy 4 毫米时 TE 插损 0.60 dB，说明这个方法可以做多通道、高密度的三维光路。',
    '最后是作者自己说的局限，讲的时候要提，答辩时也常被问：一是器件还没有和 MCF、光子芯片实际集成，不过作者引用自己此前的工作说明装配损耗是可接受的；二是纵向尺寸还有优化空间，比如换用高数值孔径的物镜。',
])

# ================================================================ P16 总结
s = new('它的创新方式，和 ResNet 是同一套逻辑')

half = [('深层网络难优化',
         [('不是“网络深”本身的问题，\n而是梯度难以传回浅层', 0),
          ('于是引入 residual connection，\n让恒等映射有一条直通路', 1)], BLUE, 'ResNet'),
        ('小半径弯曲损耗高',
         [('不是“损耗”一个笼统的数，\n而是 Lp / Lc / Lr / Lmismatch 的叠加', 0),
          ('拆开后发现 mode mismatch\n没被系统解决 → TOA-cos', 1)], RED, '本文')]
for i, (head, steps, col, who) in enumerate(half):
    x = 0.62 + i * 6.05
    card(s, x, 1.12, 5.85, 2.98)
    text_at(s, x + 0.30, 1.58, 5.25, 0.34, head, size=17, bold=True, color=col)
    yy = 1.96
    for txt, kind in steps:
        h = est_h(txt, 4.55, 13.5) + 0.20
        rect(s, x + 0.32, yy, 4.95, h, fill=BAND if kind == 0 else GREEN_BG, line=None)
        text_at(s, x + 0.52, yy + 0.10, 4.55, h - 0.20, txt, size=13.5, color=TEXT, line=1.28)
        yy += h + 0.14
        if kind == 0:
            text_at(s, x + 2.85, yy - 0.16, 1.2, 0.24, '↓ 拆解', size=11.5, bold=True, color=col)
            yy += 0.14
    rich_at(s, x + 0.32, 3.72, 5.25, 0.30,
            [(who + '：', True, col), ('对“没被解决的那一项”下手。', False, TEXT)], size=12.5)

text_at(s, X0, 4.24, CW, 0.32,
        '真正的创新往往不是“把整体做得更好”，而是先把总问题拆成可解释的子问题，再对其中没被解决的那一项下手。',
        size=15, bold=True, color=NAVY)

for i, (head, desc) in enumerate([
        ('创新来自把总问题\n拆成可解释的子损耗',
         'IL 拆到 Lp / Lc / Lr / Lmismatch 之后，才知道 Lb 是主战场、Lmismatch 是空白。拆解本身就是创新的一部分。'),
        ('TOA-cos 是结构组合，\n不是工艺参数优化',
         'cosine 管曲率连续、offset 补模场错位、trench 压辐射损耗 —— 三种经典手段第一次被组合进同一个弯曲波导，且可与既有方法叠加。'),
        ('对 3D 波导布线 /\n光互连的启发',
         '结构自由度是 FLDW 相对光刻的最大优势。把损耗拆成设计变量，曲线形状、横向偏移、周边辅助结构就都成了可优化的“旋钮”。')]):
    x = 0.62 + i * 4.13
    card(s, x, 4.62, 3.95, 2.30)
    badge(s, x + 0.22, 5.06, i + 1, color=BLUE, size=0.30)
    text_at(s, x + 0.68, 4.86, 3.05, 0.60, head, size=13.5, bold=True, color=BLUE, line=1.24)
    text_at(s, x + 0.28, 5.62, 3.45, 1.20, desc, size=11.5, color=TEXT, line=1.30)

text_at(s, X0, 7.02, CW, 0.26,
        '谢谢，欢迎提问 —— 完整出处：Fengrui Yu, Lin Ma, Mingjing Xu, Xiaoke Chen, Jinhua Wu, Zeyuan He, '
        'Advanced Photonics Research, 2026',
        size=10.5, color=NAVY, align=PP_ALIGN.CENTER)

note(s, [
    '最后一页，我想讲的是这篇文章的“创新方式”，它和 ResNet 是同一套逻辑。',
    '左边是 ResNet 的故事：深层网络难优化，大家一开始以为是“深度”本身的问题。后来发现真正的症结是梯度传不回浅层，于是引入残差连接，给恒等映射一条直通路。它没有把网络改小，而是先诊断出真正的病因。',
    '右边是这篇论文：小半径弯曲损耗高，作者没有去笼统地“降损耗”，而是先把总插损拆成传播、耦合、辐射、模式失配四项。拆完发现前三项已经被前人解决得不错，唯独模式失配没有被系统解决。于是针对它设计 TOA-cos。',
    '两者共同的模式是：真正的创新往往不是“把整体做得更好”，而是先把总问题拆成可解释的子问题，再对其中没被解决的那一项下手。',
    '三条 takeaway。',
    '第一，创新来自把总问题拆成可解释的子损耗。这篇论文最重要的一页不是结果页，而是那个损耗分解公式——它决定了后面所有设计的方向。',
    '第二，TOA-cos 是结构组合，不是工艺参数优化。cosine 管曲率连续，offset 补模场错位，trench 压辐射损耗。这三种手段单独看都是经典方法，但第一次被组合进同一个弯曲波导，而且可以和已有方法叠加。这是它的器件结构创新属性。',
    '第三，对我自己后面做 3D 波导布线和光互连的启发：结构自由度是 FLDW 相对光刻的最大优势。如果我们能把损耗拆成设计变量，那么曲线形状、横向偏移、周边辅助结构就都变成了可以优化的“旋钮”。反过来，这也是我后面做自动排布和路由优化时可以直接借用的思路。',
    '谢谢，欢迎提问。',
])

prs.save(OUT)
print('saved ->', OUT)
