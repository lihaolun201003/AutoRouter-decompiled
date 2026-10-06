# -*- coding: utf-8 -*-
"""构建 PPT 的公共库：字体、卡片、要点行、图片等比放置、演讲者备注。

配色与字体全部取自 Linsgroup_PPT.pptx 的主题（名为「交大蓝」）与第 20 页字体规范：
  中文标题/正文 = 微软雅黑，英文标题/正文 = Arial。
"""
import math
import os

from PIL import Image
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml import parse_xml
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

A = 'http://schemas.openxmlformats.org/drawingml/2006/main'

# ---------------------------------------------------------------- 调色板（交大蓝主题）
BLUE = RGBColor(0x0B, 0x4D, 0xA2)      # accent1  交大蓝
BLUE_D = RGBColor(0x08, 0x39, 0x79)    # 交大蓝加深
NAVY = RGBColor(0x24, 0x28, 0x52)      # dk2
LBLUE = RGBColor(0xAC, 0xCB, 0xF9)     # lt2
BAND = RGBColor(0xEC, 0xF3, 0xFC)      # 极浅蓝底带
BAND2 = RGBColor(0xF4, 0xF7, 0xFB)     # 极浅灰蓝
GBLUE = RGBColor(0x7F, 0x8F, 0xA9)     # accent4
TEAL = RGBColor(0x5A, 0xA2, 0xAE)      # accent5
MAUVE = RGBColor(0x9D, 0x90, 0xA0)     # accent6
RED = RGBColor(0xC8, 0x16, 0x1E)       # 模板「丨」强调色
TEXT = RGBColor(0x33, 0x33, 0x33)
MUTED = RGBColor(0x6B, 0x72, 0x80)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
BORDER = RGBColor(0xD5, 0xE1, 0xF2)
GREEN = RGBColor(0x2E, 0x7D, 0x5B)

EA = '微软雅黑'
LAT = 'Arial'

SRC = 'Fengrui Yu, Lin Ma, et al., Adv. Photonics Res. 2026, DOI: 10.1002/adpr.70241'


# ---------------------------------------------------------------- 字体
def set_font(run, size=18, bold=False, color=TEXT, latin=LAT, ea=EA, italic=False, spc=None):
    """显式设置字体：latin=Arial，ea=微软雅黑（对应模板第 20 页字体规范）。"""
    f = run.font
    f.name = latin
    f.size = Pt(size)
    f.bold = bold
    f.italic = italic
    f.color.rgb = color
    rPr = run._r.get_or_add_rPr()
    for tag in ('a:ea', 'a:cs'):
        for el in rPr.findall(qn(tag)):
            rPr.remove(el)
    ea_el = parse_xml(f'<a:ea xmlns:a="{A}" typeface="{ea}"/>')
    rPr.insert_element_before(ea_el, 'a:cs', 'a:sym', 'a:hlinkClick',
                              'a:hlinkMouseOver', 'a:rtl', 'a:extLst')
    if spc is not None:
        rPr.set('spc', str(int(spc * 100)))
    return run


def _textbox(slide, l, t, w, h, anchor=MSO_ANCHOR.TOP, align=PP_ALIGN.LEFT):
    tb = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.paragraphs[0].alignment = align
    return tb, tf


def put(tf, text, size, bold=False, color=TEXT, align=None, first=False,
        space_before=0, space_after=0, line=None, ea=EA, latin=LAT, italic=False):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    if align is not None:
        p.alignment = align
    if space_before:
        p.space_before = Pt(space_before)
    if space_after:
        p.space_after = Pt(space_after)
    if line:
        p.line_spacing = line
    r = p.add_run()
    r.text = text
    set_font(r, size, bold, color, latin=latin, ea=ea, italic=italic)
    return p


def text_at(slide, l, t, w, h, text, size=18, bold=False, color=TEXT,
            align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, line=None, ea=EA, latin=LAT,
            grow=True):
    """文本框。grow=True 时把框高提到估算所需高度，避免文字溢出框外的隐患。"""
    if grow:
        h = max(h, est_h(text, w, size, line or 1.32) + 0.08)
    tb, tf = _textbox(slide, l, t, w, h, anchor, align)
    put(tf, text, size, bold, color, first=True, line=line, ea=ea, latin=latin)
    return tb


def rich_at(slide, l, t, w, h, parts, size=18, color=TEXT,
            align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, line=None, grow=True):
    """一段内混排多段样式：parts = [(文本, bold, 颜色或None), ...]"""
    if grow:
        joined = ''.join(p[0] for p in parts)
        h = max(h, est_h(joined, w, size, line or 1.32) + 0.08)
    tb, tf = _textbox(slide, l, t, w, h, anchor, align)
    p = tf.paragraphs[0]
    p.alignment = align
    if line:
        p.line_spacing = line
    for txt, bold, col in parts:
        r = p.add_run()
        r.text = txt
        set_font(r, size, bold, col or color)
    return tb


# ---------------------------------------------------------------- 形状
def set_shadow(shape, color='0B4DA2', alpha=12, blur=76200, dist=22860, direction=5400000):
    spPr = shape._element.spPr
    for old in spPr.findall(qn('a:effectLst')):
        spPr.remove(old)
    spPr.append(parse_xml(
        f'<a:effectLst xmlns:a="{A}">'
        f'<a:outerShdw blurRad="{blur}" dist="{dist}" dir="{direction}" rotWithShape="0">'
        f'<a:srgbClr val="{color}"><a:alpha val="{int(alpha * 1000)}"/></a:srgbClr>'
        f'</a:outerShdw></a:effectLst>'))


def no_shadow(shape):
    shape.shadow.inherit = False


def rect(slide, l, t, w, h, fill=WHITE, line=None, lw=0.75, shadow=False,
         shape=MSO_SHAPE.RECTANGLE, radius=None):
    sh = slide.shapes.add_shape(shape, Inches(l), Inches(t), Inches(w), Inches(h))
    if fill is None:
        sh.fill.background()
    else:
        sh.fill.solid()
        sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
        sh.line.width = Pt(lw)
    no_shadow(sh)
    if shadow:
        set_shadow(sh)
    if radius is not None and shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        sh.adjustments[0] = radius
    sh.text_frame.word_wrap = True
    return sh


def card(slide, l, t, w, h, fill=WHITE, accent=True, shadow=True, line=BORDER):
    """模板签名式卡片：白底 + 细蓝边 + 左上角蓝色平行四边形角标 + 淡阴影。"""
    sh = rect(slide, l, t, w, h, fill=fill, line=line, shadow=shadow)
    if accent:
        ph = rect(slide, l + 0.17, t + 0.14, 0.40, 0.19, fill=BLUE,
                  shape=MSO_SHAPE.PARALLELOGRAM)
        _skew_para(ph)
    return sh


def _skew_para(shape):
    """把平行四边形的斜切量调到模板观感（默认 25000 太斜）。"""
    prst = shape._element.spPr.find(qn('a:prstGeom'))
    if prst is None:
        return
    av = prst.find(qn('a:avLst'))
    if av is None:
        av = parse_xml(f'<a:avLst xmlns:a="{A}"/>')
        prst.append(av)
    av.append(parse_xml(f'<a:gd xmlns:a="{A}" name="adj" fmla="val 30000"/>'))


def arrow(slide, l, t, w, h, color=BLUE, lw=1.6):
    conn = slide.shapes.add_connector(1, Inches(l), Inches(t), Inches(l + w), Inches(t + h))
    conn.line.color.rgb = color
    conn.line.width = Pt(lw)
    ln = conn.line._get_or_add_ln()
    ln.append(parse_xml(
        f'<a:tailEnd xmlns:a="{A}" type="triangle" w="med" len="med"/>'))
    return conn


def chip(slide, l, t, w, h, value, unit, label, vcolor=BLUE, vsize=40, fill=BAND):
    """大数字指标块。"""
    rect(slide, l, t, w, h, fill=fill, line=None)
    vh = h - 0.54
    if unit:
        rich_at(slide, l, t + 0.06, w, vh,
                [(value, True, vcolor), (' ' + unit, True, GBLUE)], size=vsize,
                align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, grow=False)
    else:
        text_at(slide, l, t + 0.06, w, vh, value, size=vsize, bold=True, color=vcolor,
                align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, grow=False)
    text_at(slide, l, t + h - 0.42, w, 0.36, label, size=13, color=MUTED,
            align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.TOP, grow=False)


# ---------------------------------------------------------------- 要点行
def units_of(text):
    """按字宽估算：CJK 计 1.0，ASCII 计 0.55。"""
    return sum(1.0 if ord(c) > 0x2E80 else 0.55 for c in text)


def est_lines(text, w_in, size):
    per_line = max(1.0, (w_in * 72.0) / size)
    return max(1, math.ceil(units_of(text) / per_line))


def est_h(text, w_in, size, line=1.32):
    total = 0.0
    for seg in str(text).split('\n'):
        total += est_lines(seg, w_in, size) * size * line / 72.0
    return max(total, size * line / 72.0)


def bullets(slide, l, t, w, rows, size=17, gap=0.20, mark=0.105,
            mcolor=BLUE, tcolor=TEXT, bolds=()):
    """自绘要点行：蓝色小方块 + 文本（不用 unicode 圆点，避免双重点号）。"""
    y = t
    for i, txt in enumerate(rows):
        rect(slide, l, y + size * 0.0085, mark, mark, fill=mcolor)
        tw = w - mark - 0.16
        text_at(slide, l + mark + 0.16, y, tw, est_h(txt, tw, size) + 0.05,
                txt, size=size, color=tcolor, bold=(i in bolds), line=1.32)
        y += est_h(txt, tw, size) + gap
    return y


def caption(slide, l, t, w, text, size=12, color=MUTED, align=PP_ALIGN.LEFT):
    return text_at(slide, l, t, w, 0.28, text, size=size, color=color, align=align)


# ---------------------------------------------------------------- 图片
def fig(slide, path, l, t, maxw, maxh, center_in_box=True):
    """等比缩放置入图片，绝不拉伸；返回实际 (l, t, w, h) 英寸。"""
    with Image.open(path) as im:
        iw, ih = im.size
    ar = iw / ih
    w, h = maxw, maxw / ar
    if h > maxh:
        h, w = maxh, maxh * ar
    x, y = l, t
    if center_in_box:
        x = l + (maxw - w) / 2.0
        y = t + (maxh - h) / 2.0
    slide.shapes.add_picture(path, Inches(x), Inches(y), Inches(w), Inches(h))
    return x, y, w, h


def badge(slide, l, t, num, color=RED, size=0.32):
    """圈号标记 ①②③：用带圆形的数字块。"""
    sh = rect(slide, l, t, size, size, fill=color, shape=MSO_SHAPE.OVAL)
    tf = sh.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = str(num)
    set_font(r, 14, True, WHITE)
    return sh


def note(slide, parts):
    """把讲稿写入演讲者备注。"""
    tf = slide.notes_slide.notes_text_frame
    tf.text = ''
    for i, seg in enumerate(parts):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        if seg == '':
            r = p.add_run()
            r.text = ' '
            set_font(r, 8, color=RGBColor(0x22, 0x22, 0x22))
            continue
        r = p.add_run()
        r.text = seg
        set_font(r, 14, color=RGBColor(0x22, 0x22, 0x22))


def pic_line(slide, l, t, w, text):
    return caption(slide, l, t, w, text, size=11, color=GBLUE)


# ---------------------------------------------------------------- 版式装配
def blank_slide(prs, layout_idx):
    """新建一页；清掉用不到的空占位符，保留顶部标题占位符。"""
    s = prs.slides.add_slide(prs.slide_layouts[layout_idx])
    for sh in list(s.shapes):
        if sh.is_placeholder:
            if not (abs(sh.left - Inches(1.176)) < Inches(0.2)
                    and abs(sh.top - Inches(0.05)) < Inches(0.2)):
                sh._element.getparent().remove(sh._element)
    return s


def set_title(slide, title, size=None):
    ph = None
    for sh in slide.shapes:
        if sh.is_placeholder and abs(sh.left - Inches(1.176)) < Inches(0.2) \
                and abs(sh.top - Inches(0.05)) < Inches(0.2):
            ph = sh
            break
    if ph is None:
        return
    # 必须同时显式设置四个量：python-pptx 新建占位符不带 xfrm，
    # 只设 width 会让继承来的 cy 变成 0，标题会塌成一条线。
    ph.left = Inches(1.176)
    ph.top = Inches(0.048)
    ph.width = Inches(11.35)
    ph.height = Inches(0.655)
    tf = ph.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    for r in list(p.runs):
        r._r.getparent().remove(r._r)
    u = units_of(title)
    if size is None:
        size = 28 if u <= 24 else (26 if u <= 30 else 24)
    r = p.add_run()
    r.text = title
    set_font(r, size, True, WHITE)
