from pathlib import Path
import csv, json, hashlib, zipfile, re
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parents[4]
P3, P2 = ROOT/'OpticalWaveguideRouter3D', ROOT/'OpticalWaveguideRouter2D'
OUT = Path(__file__).resolve().parent
NAME = '光波导布线全部实验报告（含三维策略v3）'
IMAGES, TABLES, COVERAGE = [], [], {}
SECTION_NUMBER=0
PENDING_PAGE=False

def csvread(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))
def jsread(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def tabdata(name): return csvread(P3/'publication/tables'/name)
def raw(folder,n,name): return csvread(P3/f'outputs/{folder}/{n}/{name}')
def find(rows, scheme): return next(r for r in rows if r['scheme']==scheme)
def fmt(v,d=4):
    if v is None: return '缺失'
    if isinstance(v,str) and v in ('不适用','未完成','缺失'): return v
    return f'{float(v):.{d}f}'
def integer(v): return str(int(float(v)))

doc=Document(); sec=doc.sections[0]
sec.page_width,sec.page_height=Cm(21),Cm(29.7)
sec.top_margin=sec.bottom_margin=Cm(1.7)
sec.left_margin=sec.right_margin=Cm(2)
sec.header_distance=sec.footer_distance=Cm(0.7)
for name in ['Normal','Title','Heading 1','Heading 2','Caption','Header','Footer']:
    s=doc.styles[name]; s.font.name='Calibri'; s.font.color.rgb=RGBColor(0,0,0)
    s.element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'),'宋体')
    s.paragraph_format.widow_control=True
    for b in s.element.xpath('./w:pPr/w:pBdr'): b.getparent().remove(b)
doc.styles['Normal'].font.size=Pt(11)
doc.styles['Normal'].paragraph_format.line_spacing=1.5
doc.styles['Normal'].paragraph_format.space_after=Pt(6)
doc.styles['Title'].font.size=Pt(20); doc.styles['Title'].font.bold=True
doc.styles['Title'].paragraph_format.space_after=Pt(10)
for name,size in [('Heading 1',14),('Heading 2',11.5)]:
    s=doc.styles[name]; s.font.size=Pt(size); s.font.bold=True
    s.paragraph_format.line_spacing=1.2
    s.paragraph_format.space_before=Pt(10); s.paragraph_format.space_after=Pt(6)
doc.styles['Caption'].font.size=Pt(10)
doc.styles['Caption'].font.italic=False; doc.styles['Caption'].font.bold=False
doc.styles['Caption'].paragraph_format.line_spacing=1.25
doc.styles['Caption'].paragraph_format.space_after=Pt(6)
h=sec.header.paragraphs[0]; h.text='光波导布线实验记录'; h.style='Header'; h.runs[0].font.size=Pt(9)
f=sec.footer.paragraphs[0]; f.alignment=WD_ALIGN_PARAGRAPH.CENTER
f.add_run('第 '); field=OxmlElement('w:fldSimple'); field.set(qn('w:instr'),'PAGE'); f._p.append(field); f.add_run(' 页')
for r in f.runs: r.font.size=Pt(9)

def para(text,label=None,small=False):
    p=doc.add_paragraph()
    if label: p.add_run(label+'：').bold=True
    p.add_run(text)
    if small:
        p.paragraph_format.line_spacing=1.3
        p.paragraph_format.space_before=Pt(4); p.paragraph_format.space_after=Pt(5)
        for r in p.runs: r.font.size=Pt(9)
    return p
def heading(text,ids=(),level=1):
    global SECTION_NUMBER,PENDING_PAGE
    if level==1:
        SECTION_NUMBER+=1
        text=f'{SECTION_NUMBER} '+re.sub(r'^\d+\s+','',text)
    for code in ids:
        if code in COVERAGE: raise ValueError('Duplicate coverage '+code)
        COVERAGE[code]=text
    p=doc.add_heading(text,level)
    if (level==1 and SECTION_NUMBER>1) or PENDING_PAGE:
        p.paragraph_format.page_break_before=True; PENDING_PAGE=False
    return p
def page():
    global PENDING_PAGE
    PENDING_PAGE=True
def continuation(text):
    p=heading(f'实验 {SECTION_NUMBER} 续 {text}',level=2)
    p.paragraph_format.page_break_before=True
    return p
def note(text): return para('注：'+text,small=True)
def source(text):
    # Keep a source with the preceding explanation instead of leaving it alone.
    if doc.paragraphs:
        doc.paragraphs[-1].paragraph_format.keep_with_next=True
    return para('数据来源：'+text,small=True)
def border(parent,side,val='nil',size=0):
    el=OxmlElement('w:'+side); el.set(qn('w:val'),val)
    if val!='nil': el.set(qn('w:sz'),str(size)); el.set(qn('w:color'),'000000')
    parent.append(el)

def table(title,headers,rows,widths,text_cols=(0,),groups=None,best=(),notes=None,row_groups=()):
    """Editable three-line table with values centered under their column headings."""
    assert len(headers)==len(widths) and sum(widths)<=17.001
    assert all(len(row)==len(headers) for row in rows)
    if not row_groups:
        if len(rows)<=6 or headers[0]=='路线ID':
            row_groups=[(0,len(rows))]
        elif headers[0] in ('规模','规模与ID'):
            starts=[0]+[i for i in range(1,len(rows)) if rows[i][0]!=rows[i-1][0]]+[len(rows)]
            row_groups=list(zip(starts,starts[1:]))
    number=len(TABLES)+1
    p=doc.add_paragraph(f'表{number} {title}',style='Caption')
    p.paragraph_format.keep_with_next=True; p.paragraph_format.space_after=Pt(6)
    hr=2 if groups else 1
    t=doc.add_table(rows=hr,cols=len(headers)); t.alignment=WD_TABLE_ALIGNMENT.CENTER; t.autofit=False
    pr=t._tbl.tblPr
    tw=pr.find(qn('w:tblW')); tw.set(qn('w:type'),'dxa'); tw.set(qn('w:w'),str(round(sum(widths)*1440/2.54)))
    for old in pr.findall(qn('w:tblBorders')): pr.remove(old)
    b=OxmlElement('w:tblBorders')
    for side in ['top','left','bottom','right','insideH','insideV']:
        border(b,side,'single' if side in ('top','bottom') else 'nil',8)
    pr.append(b)
    for c,w in zip(t.columns,widths): c.width=Cm(w)
    for row in t.rows:
        for ci,cell in enumerate(row.cells): cell.width=Cm(widths[ci])
    for ci,(c,titletext) in enumerate(zip(t.rows[hr-1].cells,headers)): c.text=titletext
    if groups:
        covered=set()
        for start,end,titletext in groups:
            cell=t.cell(0,start).merge(t.cell(0,end)) if end>start else t.cell(0,start)
            cell.text=titletext; covered.update(range(start,end+1))
        for ci in range(len(headers)):
            if ci not in covered:
                cell=t.cell(0,ci).merge(t.cell(1,ci)); cell.text=headers[ci]
    for values in rows:
        for c,v in zip(t.add_row().cells,values): c.text=str(v)
    best=set(best)
    positions={}
    for ri,row in enumerate(t.rows):
        for ci,cell in enumerate(row.cells):
            positions.setdefault(cell._tc,[]).append((ri,ci))
    seen=set()
    for ri,row in enumerate(t.rows):
        rp=row._tr.get_or_add_trPr(); rp.append(OxmlElement('w:cantSplit'))
        if ri<hr: rp.append(OxmlElement('w:tblHeader'))
        for ci,cell in enumerate(row.cells):
            if cell._tc in seen: continue
            seen.add(cell._tc); cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            if ri>=hr or not groups: cell.width=Cm(widths[ci])
            cp=cell._tc.get_or_add_tcPr()
            for tag in ['tcBorders','shd','tcMar']:
                for old in cp.findall(qn('w:'+tag)): cp.remove(old)
            margins=OxmlElement('w:tcMar')
            for side,val in [('top',80),('bottom',80),('left',85),('right',85)]:
                e=OxmlElement('w:'+side); e.set(qn('w:w'),str(val)); e.set(qn('w:type'),'dxa'); margins.append(e)
            cp.append(margins)
            cb=OxmlElement('w:tcBorders')
            first=min(r for r,c in positions[cell._tc]); last=max(r for r,c in positions[cell._tc])
            for side in ['left','right','top','bottom']:
                is_top=side=='top' and first==0
                is_middle=side=='bottom' and last==hr-1
                is_bottom=side=='bottom' and last==len(t.rows)-1
                border(cb,side,'single' if is_top or is_middle or is_bottom else 'nil',8 if is_top or is_bottom else 5)
            cp.append(cb)
            for p in cell.paragraphs:
                p.paragraph_format.space_before=Pt(0); p.paragraph_format.space_after=Pt(0)
                p.paragraph_format.line_spacing=1.2
                p.paragraph_format.keep_with_next=ri<hr
                p.alignment=WD_ALIGN_PARAGRAPH.LEFT if ci in text_cols else WD_ALIGN_PARAGRAPH.CENTER
                for r in p.runs:
                    r.font.size=Pt(10.5); r.font.bold=(ri<hr or (ri-hr,ci) in best)
    # Physical continuation cells in vertically merged headers also need the separator.
    for tc in t.rows[hr-1]._tr.findall(qn('w:tc')):
        cp=tc.find(qn('w:tcPr'))
        cb=cp.find(qn('w:tcBorders'))
        if cb is None: cb=OxmlElement('w:tcBorders'); cp.append(cb)
        for old in cb.findall(qn('w:bottom')): cb.remove(old)
        border(cb,'bottom','single',5)
    for tc in t.rows[hr]._tr.findall(qn('w:tc')):
        cp=tc.find(qn('w:tcPr')); cb=cp.find(qn('w:tcBorders'))
        for old in cb.findall(qn('w:top')): cb.remove(old)
        border(cb,'top','single',5)
    # Include the empty continuation cells of vertically merged headers.
    for row in t.rows[:hr]:
        for tc in row._tr.findall(qn('w:tc')):
            for element in tc.findall(qn('w:p')):
                pp=element.get_or_add_pPr()
                keep=pp.find(qn('w:keepNext'))
                if keep is None: keep=OxmlElement('w:keepNext'); pp.append(keep)
                keep.set(qn('w:val'),'1')
    # Keep each comparable group together while allowing breaks between groups.
    for start,end in row_groups:
        assert 0<=start<end<=len(rows)
        for row in t.rows[hr+start:hr+end-1]:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    paragraph.paragraph_format.keep_with_next=True
    if notes:
        for cell in t.rows[-1].cells:
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.keep_with_next=True
    TABLES.append({'number':number,'title':title,'rows':len(rows),'width_cm':sum(widths),'best_cells':sorted(best)})
    if notes: note(notes)
    else:
        p=doc.add_paragraph(); p.paragraph_format.space_after=Pt(4); p.paragraph_format.line_spacing=Pt(2)
    return t

def picture(paths,widths,caption):
    global FIG_NUMBER
    FIG_NUMBER+=1
    if isinstance(paths,(str,Path)): paths=[paths]; widths=[widths]
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after=Pt(5); p.paragraph_format.keep_with_next=True
    for i,(path,w) in enumerate(zip(paths,widths)):
        path=Path(path); assert path.is_file()
        if i: p.add_run('  ')
        shape=p.add_run().add_picture(str(path),width=Cm(w)); shape._inline.docPr.set('descr',caption)
        IMAGES.append({'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    p=doc.add_paragraph(f'图{FIG_NUMBER} {caption}',style='Caption'); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
FIG_NUMBER=0

repro=tabdata('t32_reproduction_compare_data.csv')
radius=tabdata('t33_radius_sweep_512_data.csv')
s12={n:raw('opt2d',n,'comparison.csv') for n in (256,512)}
for rows in s12.values():
    for r in rows: r['scheme']=r['label'].split('-')[0]
s13={n:raw('opt2d_step13_fix',n,'comparison.csv') for n in (256,512)}
s14={n:raw('opt2d_step14',n,'comparison.csv') for n in (256,512)}

# ---- 本轮三维策略 v3 三组新实验的只读数据源 ----
V3=P3/'outputs/3d_strategy_v3'
ABL=V3/'512_ablation'; DIAG=V3/'512_relocation_slack_diagnostic'
PROBE=V3/'window_slack_probe'; V3FIG=V3/'figures'
OLDDIAG=P3/'outputs/3d_strategy_v2_rev2/512_de_diagnostic'
GROUPS=[('A_baseline_original','A 基线原版','关','0'),
        ('B_generation_cache_only','B 仅生成缓存','开','0'),
        ('C_window_slack_only','C 仅窗口余量','关','1e-05'),
        ('D_both_enabled','D 两项同开','开','1e-05')]
GL={k:jsread(ABL/k/'ledger.json') for k,_,_,_ in GROUPS}
GS={k:jsread(ABL/k/'summary.json') for k,_,_,_ in GROUPS}
CROSS=jsread(ABL/'cross_group_analysis.json')
ABLDATA=CROSS['dataset'].split(' ')[0]
PROBEJ=jsread(PROBE/'window_slack_probe.json')
DL={m:jsread(DIAG/('ledger_%s.json'%m)) for m in ('D','E')}
OL={m:jsread(OLDDIAG/('ledger_%s.json'%m)) for m in ('D','E')}
ANALYSIS=jsread(DIAG/'analysis.json')
MOVEMENT=jsread(DIAG/'movement_stats.json')
LENGTH=jsread(DIAG/'length_ledger.json')
CANDIAG=jsread(DIAG/'config.json')
CORR_REL=ANALYSIS['correspondence_relocation_candidates']
CORR_ALL=ANALYSIS['correspondence_all_movement_classes']
AEC=ANALYSIS['accepted_edit_counts']
BA=ANALYSIS['accepted_relocation_before_after']; ENTRY=BA['entry']
MS=ANALYSIS['movement_stats']
def zmax(route):
    m=0.0
    for prim in route['primitives']:
        g=prim.get('geometry',prim)
        for key in ('start','end','center'):
            pt=g.get(key)
            if isinstance(pt,dict) and 'z' in pt: m=max(m,abs(float(pt['z'])))
    return m
LAYERZ={float(l['z']):l['id'] for l in CANDIAG['configuration']['layers']}
LAYER_BEFORE=LAYERZ.get(zmax(BA['before']),zmax(BA['before']))
LAYER_AFTER=LAYERZ.get(zmax(BA['after']),zmax(BA['after']))

# Practical introduction and the user's actual reproduction images.
doc.add_paragraph('光波导布线全部实验报告',style='Title')
para('我们完成了二维布线复现、轨道与路径优化、交叉和间距诊断，以及三维抬层实验。下面逐项说明做了什么、结果怎么样、得出了什么结论，并保留未布通、被拒绝和中止的尝试。图与数据均来自自己的项目结果。')
heading('R5 和 R6 是什么',level=2)
para('R 是圆弧转弯半径，R5 = 5 mm，R6 = 6 mm。R6更缓，也占更多空间；模型的一次90°转弯损耗约2.3826/1.9037 dB。F5是R5自由弯角，F56是允许R5/R6的自由弯角。清单编号R05、R06分别指512条的2 mm、3 mm实验，与半径名称不同。')
heading('1 原二维波导布线复现',('R02','R03','R04'))
para('恢复原程序的输入、轨道分配与圆弧构造，在150 × 150 mm区域布置256、512条连接；分别计算直线、弯曲和交叉损耗。', '做了什么')
picture([P2/'results/fiberBoard256bend.png',P2/'results/fiberBoard512bend.png'],[8.15,8.15],'自己的二维复现布局 上为256条 下为512条 红线为波导')
rows=[]
for case,label in [('256','256条 R5'),('512','512条 R5'),('512_R4','512条 R4')]:
    a=next(r for r in repro if r['case']==case and r['metric']=='平均损耗'); b=next(r for r in repro if r['case']==case and r['metric']=='最大损耗')
    rows.append([label,fmt(a['repro_db']),fmt(b['repro_db']),fmt(a['thesis_db'],1),fmt(b['thesis_db'],1)])
table('复现损耗与原报告数值',['实验','平均','最大','平均','最大'],rows,[4.4,3.15,3.15,3.15,3.15],groups=[(1,2,'复现损耗（dB）'),(3,4,'原报告损耗（dB）')],notes='全部连接完成。原报告只保留1位小数；复现结果保留4位小数。不同规模或半径不作复现优劣排名。')
para('主要损耗数值接近原报告，256、512两组均全部布通。这里的损耗是模型计算值；交叉表来自原图数字化近似，尚无器件实测结果。', '结果和结论')
source('2D/results/fiberBoard{256,512}_loss_summary.json、fiberBoard512_loss_R4_summary.json；三线表取自t32。2D/3D目录缩写与t表编号见末页。')

page(); heading('2 弯曲模型与半径扫描',('R01','R05','R06'))
para('先用原程序的弯曲表重算2、3、4、5、6 mm半径的一次90°转弯损耗，再让512条连接分别以2、3、4、5 mm半径重新布线。', '做了什么')
bend=tabdata('t31_bend_model_thesis_vs_repro_data.csv')
table('一次90°转弯的模型核对',['半径（mm）','原印刷值（dB）','复算值（dB）','复算减印刷（dB）'],[[fmt(r['radius_mm'],0),fmt(r['thesis_db'],2),fmt(r['repro_db']),fmt(float(r['repro_db'])-float(r['thesis_db']))] for r in bend],[3.0,4.0,4.8,5.2],text_cols=(),notes='印刷值保留2位小数。差值有正有负，列名明确表示有符号差，不沿用旧CSV中误写的“abs”列名。')
table('512条连接的完整半径扫描',['半径（mm）','平均损耗（dB）','P95损耗（dB）','最大损耗（dB）'],[[integer(r['radius_mm']),fmt(r['mean_loss_db']),fmt(r['p95_loss_db']),fmt(r['max_loss_db'])] for r in radius],[3.1,4.6,4.6,4.7],text_cols=(),best=[(3,1),(3,2),(3,3)],notes='各半径独立构造几何，均完整布通。粗体是本组完整结果的最低损耗，不能解释为固定几何下只改模型参数。P95表示一次布局内95%的路线损耗不超过该值。')
continuation('损耗分布与结论')
picture(P2/'results/loss_vs_radius.png',16.5,'自己的半径扫描结果 左为损耗汇总 右为逐条路线分布')
para('平均损耗由16.5873降至5.5147 dB。R5中弯曲损耗占82.66%，直线占11.52%，交叉占5.81%。在这批输入和当前模型下，转弯损耗是主要来源，扩大半径是有效方向，但仍要留出足够空间。', '结果和结论')
source('t31、t33；2D/loss_model.py；2D/results/fiberBoard512_loss_R{2,3,4}_summary.json。')

heading('3 交叉表敏感性与原程序逐路核对',('R07','R09'))
para('原始交叉损耗数据表没有完整恢复，所以在同一512条R5几何上分别采用全90°估算、图线数字化并按90°文字值校准、图线原值。另在原Python 3.8字节码上实跑256条R5及512条R2/R3/R4/R5，逐条核对直线和弯曲项。', '做了什么')
cross=tabdata('t34_crossing_model_sensitivity_data.csv')
labels={'A':'全部按90°估算','B':'图线数字化加90°校准','C':'图线数字化原值'}
table('固定几何的交叉模型复算',['交叉表口径','平均损耗（dB）','最大损耗（dB）'],[[labels[r['scope']],fmt(r['mean_loss_db']),fmt(r['max_loss_db'])] for r in cross],[7.8,4.6,4.6],notes='这三行是不同模型假设，无算法最优排名。主报告采用有文字锚点的校准口径。')
para('三种口径的平均跨度0.0986 dB，最大跨度0.1436 dB，主要半径趋势不变。字节码对照的五组逐路直线加弯曲损耗最大绝对差均为0。原字节码运行用的是全0交叉占位表，因此它只能验证非交叉项。', '结果')
para('二维几何和非交叉损耗的复现有直接逐路证据；交叉项仍含近似，不能把近似表说成恢复了原始测量数据。损耗分布、与长度及交叉次数的散点图是同一批复现结果的分析，不是新的输入实验。', '结论')
para('端到端输出另进行了256/512两组各36项验收，GDS重读分别得到1个cell和256/512条路径。512条与原字节码逐阶段对照，端点、轨道、全部弯曲参数以及GDS点阵和宽度均512/512一致，只有8个时间戳字节不同。', '输出与几何保真核对')
para('还对随附的历史图片进行了差异诊断：只有266/512条与当前恢复结果一致，235条相差一根轨道。把sn_calc条件由大于改为大于等于没有影响；去掉sn_calc项后仅43/512一致。这些负假设不能解释图差异，证据表明历史图片与恢复EXE来自不同构建。', '历史图差异与负假设')
source('t34；2D/data/crossing_loss_from_thesis_fig3_12.csv；2D/scratch/legacy_loss/legacy256_R5.json及legacy512_R{2,3,4,5}.json。')
source('2D/docs/exact_legacy_fidelity_report.md与migration_report.md。')

# Early completed verification and diagnostic experiments.
page(); heading('4 早期输入与二维骨架验证')
para('检查256/512连接输入，恢复512条连接的快照（共1024个端点）与分类，再执行独占轨道分配和直角骨架构造。轨道策略文档中的B、C只是设计，不当作已完成实验。', '做了什么')
table('真实输入和快照恢复检查',['输入规模','PMT数量','端点每PMT','自连接','额外重复行'],[['256','32','16','0','134'],['512','64','16','0','268']],[3.1,3.3,3.7,3.0,3.9],text_cols=(),notes='重复行是多重连接，保留原输入，不去重。512后半工作簿数据使用公式缓存。')
para('512快照关联512行，371行方向相同、141行恢复方向；64个PMT各16个唯一端点，间距0.175 mm。分类得到上侧U112、下侧U112、Z288，恢复输入方向后两类Z各144，非法端点0。', '输入与分类结果')
table('早期512条轨道分配',['配置','候选轨道（条）','普通路线（条）','未支持特殊Z（条）'],[['独占轨道 A G1 S1','800','454','58']],[6.2,3.6,3.6,3.6],notes='只完成454/512条，不能与后续完整512条结果直接排名。特殊Z横向跨度不足2R，没有出现普通轨道耗尽。')
table('454条零宽直角骨架的全局检查',['已检路线对','段交叉事件','交叉路线对','接触','重合','自交'],[['102831','47292','41147','0','0','0']],[3.3,3.3,3.3,2.4,2.4,2.3],text_cols=(),notes='454条中224条U形、230条Z形。端点错误、斜段、重复点、轨道不符均为0；通过骨架检查不等于平滑版图完成。')
para('普通骨架与逐对检测能够运行，但58条跨度不足2R的特殊连接需要专门路径。后续补齐普通圆角与特殊Z解析几何，才建立完整512条工程基线。', '结果和结论')
source('3D/docs/reports/step_8_legacy_512_track_assignment_v01.md、step_8_legacy_512_routes_v01.md、step_8_legacy_512_collision_validation_v01.md。')
source('输入和快照：step_8_legacy_input_validation.md、step_8_legacy_512_snapshot.md、step_8_legacy_512_route_preparation.md，均在3D/docs/reports/。')

page()
heading('5 精确求交与多交叉诊断',('R08','G3D-10'))
para('先把454条普通骨架全部圆弧平滑，得到1362条直段和908个四分之一圆弧；再独立构造58条特殊Z的双弧几何，得到116个圆弧和116条直段。特殊Z的新几何不是原EXE特殊路径的忠实恢复，原分配器的58条未支持状态仍保留。', '平滑和特殊Z实验')
para('解析求交新增直与直、直与弧、弧与弧及自交测试54项，当时全测试281项通过。完整512条共130816对，原段级统计交叉55932、交叉对49499、touch12、overlap0、自交0；12个段级touch来自3对特殊弧接点，归并后成为3个物理cross，物理touch为0。', '求交基础与事件归并')
para('对这套512条工程解析路线按直线与圆弧精确求交，合并同位置的段级交点，分别统计物理交叉、双交叉和相邻端口之间的多交叉。', '做了什么')
para('完整平滑基线得到55935个物理交叉事件、49502对交叉路线、最小交叉角约2.84°。这与二维原版逐路整数角统计属于不同口径；原报告的14°不能直接拿来判断精确求交是否正确。', '结果')
para('诊断发现6433对路线出现双交叉，318个端部多交叉结构全部涉及圆弧。多交叉的954个交点按段组合归因为：弧与水平303、弧与弧31、弧与竖直331、水平与竖直289。求交口径与端口拓扑会影响诊断数量。', '结论')
table('多交叉和双交叉的分类审计',['诊断项','类别','计数'],[['多交叉','纯普通路线','222'],['多交叉','含特殊Z','96'],['多交叉','阈值边界待定','2'],['双交叉对','普通与普通','6092'],['双交叉对','普通与特殊','341'],['双交叉对','U与U','3735'],['双交叉对','Z与Z','2698']],[4.4,8.2,4.4],text_cols=(0,1),notes='多交叉使用0.125 mm间距和1e-9容差。两类双交叉分解是不同分类视角，不可把全部行求和。阈值外841477项不能直接解释为安全。')
para('普通路线的6092个双交叉对全部在直角骨架中已经存在，本组双交叉并非由圆角才创造。这个早期基线的非交叉损耗平均5.2646、最大6.1874 dB，采用整段传播与印刷弯曲表，未加入交叉损耗；不能和后续总损耗直接相减。', '损耗与拓扑核对')
source('3D/outputs/step_8_5_legacy_512_{physical,multi_crossing,double_cross,loss}_summary.json；step_8_5_m1_5_multi_attribution_summary.json。')

page(); heading('6 排序反转与硬约束负结果')
para('把112条上侧U形路线的主排序反转，保持其他路线不变；再测试遇到端部多交叉就拒绝候选的硬约束，并核验拒绝原因。', '做了什么')
table('上侧U形排序的A B对照',['指标','原排序A','反转排序B'],[['双交叉路线对','6433','4530'],['上侧U与上侧U的双交叉对','1903','0'],['物理交叉事件','55935','52129'],['小于20°交叉','1508','984'],['端部多交叉结构','318','345']],[8.2,4.4,4.4],notes='每行只比较同一指标。反转改善部分交叉指标，却使多交叉结构增加，所以不标总体最优。')
para('多交叉审计显示204个稳定、114个移除、141个新增，净增27。新增中的87个阈值余量大于0.05 mm，不能把增加全部归因于数值临界误差。', '结果')
para('硬约束的初版全量诊断被中止。快速版运行180.018 s，只提交217条普通路线，21条出现真实轨道耗尽，累计14696次候选拒绝；最终全板阶段没有完成。独立核验的14384条耗尽拒绝均有有效见证。', '结果')
table('硬约束的局部速度基准',['指标','原局部核验','快速局部核验'],[['30次重复的中位耗时（s）',fmt(0.00390345,6),fmt(0.00052845,6)]],[7.8,4.6,4.6],notes='只针对固定40条路线的局部核验，约7.39倍加速，不能外推为整个512条布线加速。全局损耗和最终多交叉数为不适用，因为全板没有完成。')
para('改变排序有局部收益；当前贪心硬约束无法同时保持完整布通。加速求交不会自动解决轨道耗尽，未完成的方案没有可比较的全板损耗。', '结论')
source('3D/outputs/step_8_5_top_u_order_ab_summary.json、top_u_multi_crossing_delta_summary.json、exact_multi_guard_fast_routing.json、exact_multi_guard_exhaustion_summary.json。以上文件名均有step_8_5_前缀。')

page(); heading('7 局部单线恢复沙箱与归因诊断')
para('先实现Dynamic D端点视图，用4类合成样本和4条真实路线检查每侧最近端点与连续长度，458项测试通过。它只是工程诊断，危险侧尚未确认，没有整数K或新的布线改善结果。', '端点长度诊断')
para('对318个多交叉进一步按局部结构归因：204个类似原文结构、23个有歧义、91个不类似；统计最低候选路线时241个目标唯一、77个并列，最低仅普通270、仅特殊29、普通与特殊混合19，没有全部不可移动目标。统计可以帮助选候选，但尚未证明某个顺序最优。', '结构归因与候选统计')
para('从同一个318多交叉的基线分别选择四类局部案例，每例尝试347个候选，并独立验证；这些候选保留在沙箱中，没有写回全板。', '做了什么')
table('四类局部恢复的独立结果',['结构案例类型','尝试候选','严格候选','多交叉前','多交叉后'],[['A 类似原文结构 纯普通','347','0','318','318'],['B 跨侧 不类似原文结构','347','331','318','317'],['C 弧与弧案例','347','342','318','316'],['D 含特殊路径载体','347','344','318','316']],[7.0,2.5,2.5,2.5,2.5],notes='四行独立从同一基线出发，不是连续优化，收益不能相加；普通受试线均复用同一R5构造器。全板端点、损耗与布通尚未联合验收。')
para('部分局部轨道替换能减少1或2个多交叉。本次类似原文结构的纯普通案例没有找到严格候选；这些结果尚未合并成全板恢复，不能宣称多交叉已消除。', '结果和结论')
para('四个原位负对照均保持318，目标仍在且差分为空。其他候选也出现过目标消失却总数不降、甚至总数增加，因此只消除目标不足以接受改动。', '负对照')
source('3D/outputs/step_8_5_m1_6_probe_summary.json与step_8_5_m1_6_independent_validation.json。')
source('3D/docs/reports/step_8_5_m1_dynamic_d_diagnostic.md；outputs/step_8_5_m1_5_multi_attribution_summary.json、step_8_5_m1_6_victim_statistics.json。')

# Step 12 complete main results and all saved ablations.
page(); heading('8 候选轨道与自适应半径主实验',('S12-01',))
para('在256和512条输入上比较A原版R5、B统一R6、C固定R5候选轨道搜索、D允许R5/R6选择。这个早期阶段允许同端口槽位调整；后续实验才逐路固定端点。损耗用解析求交统计，与原版复现的小数略有差别。', '做了什么')
rows=[]; best=[]
for n in (256,512):
    eligible=[r for r in s12[n] if int(r['unplaced_count'])==0]
    minima={key:min(float(r[key]) for r in eligible) for key in ['mean_loss_db','p95_loss_db','max_loss_db']}
    for r in s12[n]:
        ri=len(rows); rows.append([str(n),r['scheme'],integer(r['unplaced_count']),fmt(r['mean_loss_db']),fmt(r['p95_loss_db']),fmt(r['max_loss_db']),fmt(r['runtime_s'],2)])
        if r in eligible:
            for col,key in [(3,'mean_loss_db'),(4,'p95_loss_db'),(5,'max_loss_db')]:
                if abs(float(r[key])-minima[key])<1e-10: best.append((ri,col))
table('两种规模的A B C D主对照',['规模','方案','未布通','平均','P95','最大','耗时（s）'],rows,[1.5,1.5,1.7,3.0,3.0,3.0,3.3],text_cols=(1,),groups=[(3,5,'损耗（dB）')],best=best,notes='只在同规模且完整布通的方案中标粗最低损耗。512条B缺2条，损耗仅统计510条，排除排名；运行时间是保存的一次运行，不是重复计时。')
para('256条统一R6完整布通，平均4.3360 dB；512条统一R6缺2条，自适应半径D则全部布通，平均4.5593 dB。固定R5的轨道搜索只有约0.0014/0.0015 dB平均改善。', '结果')
para('半径策略的改善远大于当前候选轨道搜索；512条需要小半径回退才能保证完整连接。这个阶段改变了部分槽位，结论属于早期探索。', '结论')
source('3D/outputs/opt2d/{256,512}/comparison.csv；S12-01。')

page(); heading('9 轨道优化的全部消融',('S12-02','S12-03','S12-04','S12-05','S12-06'))
para('依次改变候选数量、布线顺序、拆线重布、位置惩罚和半径策略，其余采用保存的默认配置。每种设置分别在256和512条输入上执行。', '做了什么')
abl=tabdata('t52_step12_ablation_data.csv')
names={'cand_k1':'候选 K = 1','cand_k4':'候选 K = 4','cand_k8':'候选 K = 8','cand_k16':'候选 K = 16','order_span':'顺序 按跨度','order_congestion':'顺序 按拥挤度','refine_on':'拆线重布 开','penalty_0':'位置惩罚 0','penalty_0.001':'位置惩罚 0.001','penalty_0.01':'位置惩罚 0.01','penalty_0.05':'位置惩罚 0.05','radius_fixed_R6':'半径 固定R6','radius_adaptive':'半径 自适应'}
rows=[[names[r['config']],fmt(r['mean_256']),integer(r['unplaced_256']),fmt(r['runtime_256'],2),fmt(r['mean_512']),integer(r['unplaced_512']),fmt(r['runtime_512'],2)] for r in abl]
best=[(3,1),(1,4),(2,4),(3,4),(8,1),(9,4),(11,1),(12,1)]
table('全部保存的轨道消融结果',['配置','平均（dB）','未布通','时间（s）','平均（dB）','未布通','时间（s）'],rows,[3.8,2.4,1.65,2.3,2.4,1.65,2.8],groups=[(1,3,'256条连接'),(4,6,'512条连接')],best=best,notes='粗体只在候选数量、位置惩罚或半径策略的各自组内、同规模且完整布通的结果中比较；跨配置组不排名。拆线重布关闭对应K = 8默认结果。')
para('候选1到16的平均收益不到0.002 dB，时间增加。跨度顺序缺76/144条，拥挤度顺序缺33/99条；这两种顺序都没有保持完整。拆线重布没有进一步改善。位置惩罚为0时缺59/113条；256的0.001和512的0.01保留完整且损耗较低。512固定R6消融缺2条，自适应完整。', '结果')
para('更多候选、改变顺序或拆线重布都不保证改善。在当前候选预筛、惩罚和预算下，搜索收益较小；未布通配置不作为成功优化结果。', '结论')
source('t52；3D/outputs/opt2d/{256,512}/sensitivity.json与sensitivity/*/summary.json。')

# Step 13 all six corrected schemes.
page(); heading('10 固定端点与自由弯角六方案',('S13-01','S13-02','S13-07'))
para('逐路固定起终点，比较原版A、固定R5的U形搜索R5U、优先R6且失败回退R5的D0、自适应U形D56、固定R5自由弯角F5、自适应自由弯角F56。跨侧路线允许圆弧加斜线的S形，同侧保留U形。', '做了什么')
rows=[]
for n in (256,512):
    for r in s13[n]: rows.append([str(n),r['scheme'],fmt(r['mean_loss_db']),fmt(r['p95_loss_db']),fmt(r['max_loss_db']),fmt(r['runtime_s'],2)])
table('补修后固定端点的全部六方案',['规模','方案','平均','P95','最大','耗时（s）'],rows,[1.6,2.4,3.3,3.3,3.3,3.1],text_cols=(1,),groups=[(2,4,'损耗（dB）')],best=[(5,2),(5,3),(5,4),(11,2),(11,3),(11,4)],notes='全部256/512条均完整连接、端点零变化。粗体按规模标识本组整体方案最低损耗；方案间半径策略不同，不把总改善都归因于路径形状。')
para('F56的平均损耗为2.9703/3.2947 dB，最大为5.0783/5.4995 dB。D0到D56只有约0.0421/0.0140 dB平均收益，搜索时间明显增加。F5降低平均损耗，但512条最大6.4459 dB，只比原版低约0.1314 dB。', '结果')
para('逐路核对D56与F56的半径完全相同：256条全部R6；512条510条R6、2条R5。相同半径下，U形到自由弯角使平均再降1.3690/1.2661 dB，支持减少总转弯角度的作用。', '结论')
para('历史256条F56曾把路线7/31重合152.007 mm误判成交叉。补修后48条路线结果变化，重合归零，平均由2.9689变为2.9703 dB；512条补修前后逐项不变。上表采用补修数据，历史非法结果不参与排名。', '补修记录')
source('3D/outputs/opt2d_step13_fix/{256,512}/comparison.csv、radius_compare.csv；256/per_route_delta.csv；历史记录在opt2d_step13/。')

page(); heading('11 自由弯角的损耗分解与几何代价')
rows=[]
for n in (256,512):
    for r in s13[n]: rows.append([str(n),r['scheme'],fmt(r['mean_straight_loss_db']),fmt(r['mean_bend_loss_db']),fmt(r['mean_crossing_loss_db']),fmt(r['mean_bend_total_deg'],2)])
table('六方案平均损耗分解',['规模','方案','直线','弯曲','交叉','平均总转角（°）'],rows,[1.6,2.0,3.2,3.2,3.2,3.8],text_cols=(1,),groups=[(2,4,'平均损耗分量（dB）')],notes='不同分量分别描述代价，不按单项最低值给方案作总体排名。')
rows=[]
for n in (256,512):
    for r in s13[n]: rows.append([str(n),r['scheme'],integer(r['unique_crossing_events']),integer(r['crossings_under_10deg']),integer(r['spacing_violation_count']),integer(r['contact_overlap_count'])])
continuation('交叉与间距代价')
table('六方案交叉与间距结果',['规模','方案','交叉事件','小于10°','间距不足对','重合'],rows,[1.6,2.0,3.5,3.0,4.0,2.9],text_cols=(1,),notes='交叉和小角列均为唯一交叉事件数，间距列为路线对。旧段级touch数不作为物理接触数。重合为零仍可有间距不足。')
para('512条A到F56平均弯曲损耗4.5587→2.1384 dB；交叉损耗0.3219→0.5650 dB，间距不足692→1231对。自由弯角降低弯曲损耗，也增加交叉与间距代价。', '结果和结论')
source('3D/outputs/opt2d_step13_fix/{256,512}/comparison.csv；Step14对段级接触重新归并为物理事件。')

heading('12 最差路线的同一编号跟踪',('S13-06',))
picture([P3/'outputs/opt2d_step13/512/figures/worst_route_A.png',P3/'outputs/opt2d_step13/512/figures/worst_route_F56.png'],[8.15,8.15],'自己的最差路线局部图 左为A路线287 右为F56路线34')
para('两张保存图分别选择各方案最差路线，编号不同；灰色为周围路线，红色为局部关注段。下面另固定原版最差路线编号，比较同一连接的损耗变化。', '做了什么')
rows=[]
for n,rid in [(256,'44'),(512,'287')]:
    for name in ['A','R5U','D0','D56','F5','F56']:
        r=next(r for r in raw('opt2d_step13_fix',n,f'{name}/per_route.csv') if r['route_id']==rid)
        rows.append([f'{n} / {rid}',name,fmt(r['total_loss_db']),fmt(r['bend_loss_db']),fmt(r['crossing_loss_db']),fmt(r['bend_total_deg'],0)])
continuation('同一连接的逐路结果')
table('固定原版最差连接的逐路结果',['规模与ID','方案','总损耗','弯曲损耗','交叉损耗','总转角（°）'],rows,[2.7,1.8,3.2,3.2,3.2,2.9],text_cols=(0,1),groups=[(2,4,'逐路损耗（dB）')],best=[(5,2),(11,2)],notes='粗体只表示同一个连接在六方案中的最低总损耗。图中的F56最差ID 34与表中的原版最差ID 44/287不同。',row_groups=[(0,6),(6,12)])
para('原版最差连接44/287从6.3333/6.5773降至约3.7512/4.3308 dB，总转角180°→90°。但F56的新最差连接换成34，最大损耗为5.0783/5.4995 dB，必须同时看固定ID和全局最大。', '结果和结论')
source('3D/outputs/opt2d_step13_fix/{256,512}/{scheme}/per_route.csv；原跟踪文件worst_route_tracking.csv。')

heading('13 自适应半径条件下的约束与惩罚扫描',('S13-03','S13-05'))
para('在base上分别加入间距惩罚spacing、小角惩罚small及二者both，重新选择路径；另对F5、F56扫描间距惩罚0、0.02、0.05 dB。此阶段半径仍自适应，不能当作纯固定半径的约束对照。', '做了什么')
con=tabdata('t63_step13_constrained_data.csv')
table('未冻结半径的四配置结果',['规模','配置','平均（dB）','最大（dB）','小于20°','间距不足对'],[[r['channels'],r['config'],fmt(r['mean_loss_db']),fmt(r['max_loss_db']),integer(r['crossings_under_20_deg']),integer(r['spacing_violation_count'])] for r in con],[1.6,2.2,3.3,3.3,3.1,3.5],text_cols=(1,),notes='重新布线并自适应半径，不是固定几何只改分数。作为早期权衡实验，不按后续严格保护口径评为最终方案。')
rows=[]
for n in (256,512):
    for name in ['F5','F56']:
        r=find(s13[n],name)
        rows.append([str(n),name,'0.00',fmt(r['mean_loss_db']),fmt(r['max_loss_db']),integer(r['spacing_violation_count'])])
        for r in raw('opt2d_step13_fix',n,f'penalty_ablation_{name}.csv'):
            rows.append([str(n),name,fmt(r['spacing_penalty_db'],2),fmt(r['mean_loss_db']),fmt(r['max_loss_db']),integer(r['spacing_violation_count'])])
continuation('间距惩罚扫描')
table('两个路径族的全部间距惩罚扫描',['规模','方案','惩罚（dB）','平均（dB）','最大（dB）','间距不足对'],rows,[1.6,2.0,2.9,3.5,3.5,3.5],text_cols=(1,),notes='每个规模、路径族独立扫描；损耗和间距存在权衡，故不定义单一最优。0.00行取补修后的默认结果。',row_groups=[(0,3),(3,6),(6,9),(9,12)])
para('256条F5间距不足576→436→401对，F56为415→324→288对；损耗小幅变化，并非全部增加。512条惩罚也减少间距不足，但不能保证最大损耗和关键路线同步改善。后续冻结半径实验进一步检验纯约束作用。', '结果和结论')
source('t63；3D/outputs/opt2d_step13_constrained/{256,512}/constrained_comparison.csv；opt2d_step13_fix/{256,512}/penalty_ablation_F{5,56}.csv。')

heading('14 六路径方案的小角交叉压力实验',('S13-04',))
para('不重新布线，在各方案的固定几何上，把小于20°的交叉损耗分别乘以1、2、5、10，再复算最大损耗。倍率是人为压力假设，用来检查交叉表不确定性的影响。', '做了什么')
sens=tabdata('t64_step13_sensitivity_data.csv')
table('补修后六方案的最大损耗压力结果',['规模','方案','倍率1','倍率2','倍率5','倍率10'],[[r['channels'],r['scheme'],*[fmt(r[k]) for k in ['max_x1','max_x2','max_x5','max_x10']]] for r in sens],[1.6,2.2,3.3,3.3,3.3,3.3],text_cols=(1,),groups=[(2,5,'各倍率情景的最大损耗（dB）')],notes='只在相同规模、相同倍率下有比较意义。此处展现敏感性而不评定统一最优；倍率5/10不代表已验证的真实误差范围。')
para('512条F56最大损耗从5.4995增到8.4333 dB，倍率10时超过原版A的6.5773 dB；256条F56从5.0783增到5.9941 dB。自由弯角的标称收益会受极小角交叉模型影响，不能从标称改善直接推断所有压力情景都改善。', '结果和结论')
source('t64；3D/outputs/opt2d_step13_fix/{256,512}/sensitivity.csv。')

# Step 14 all configurations, protected fixed IDs, margins, probes and pressure tests.
heading('15 冻结半径的六配置与严格验收',('S14-01','S14-02','S14-08','S14-09'))
para('固定每条路线的端点和F56半径，比较base、spacing、small、touch、both及保护性局部优化opt_base。要求平均增加不超过0.05 dB、标称全局最大不恶化、固定11条保护路线逐条不恶化，并保持几何合法和无重合。', '做了什么')
acc={n:raw('opt2d_step14',n,'acceptance.csv') for n in (256,512)}
rows=[]; best=[]
for n in (256,512):
    for r in s14[n]:
        a=find(acc[n],r['scheme']); ri=len(rows)
        rows.append([str(n),r['scheme'],fmt(r['mean_loss_db']),fmt(r['p95_loss_db']),fmt(r['max_loss_db']),integer(r['spacing_violation_count']),'通过' if a['ok']=='True' else '未通过'])
        if (n==512 and r['scheme']=='opt_base') or (n==256 and r['scheme'] in ['base','touch','opt_base']):
            best.extend([(ri,2),(ri,4)])
table('固定半径后的全部配置及验收',['规模','配置','平均','P95','最大','间距不足对','验收'],rows,[1.5,2.5,2.8,2.8,2.8,2.5,2.0],text_cols=(1,6),groups=[(2,4,'损耗（dB）')],best=best,notes='粗体只比较同规模、通过严格验收的配置；256条三行结果相同。P95独立描述尾部，512条opt_base的P95略有增加。未通过配置的单项较低值不评为最终最优。')
para('spacing、small、both在两种规模均未通过。256条的拒绝主要来自个别保护路线轻微恶化；512条三者平均增加分别0.0677、0.0545、0.1081 dB，都超过0.05 dB预算，且有保护对象恶化。touch与base相同，因为两组物理接触为0。', '结果')
para('冻结半径核对为256/256、512/512一致；base和未冻结F56参照的数值一致。D56参照平均4.3393/4.5607、最大5.3462/5.6217 dB；它保留U形，因此属于路径族参照，不是本组六个约束配置之一。只有512条保护优化产生了通过全部规则的非零改善。', '结论')
source('3D/outputs/opt2d_step14/{256,512}/comparison.csv、acceptance.csv、radius_freeze_check.csv、references.csv。')

for n in (256,512):
    heading(f'16 {n}条固定保护对象的逐路结果',('S14-04',) if n==256 else ())
    para('固定同一组11条ID，包含base最差、D56最差及被穿越的U形连接。每个配置都评价这些原ID，不能逐方案重选最差十条。表中列出相对base的损耗差，正数为恶化，负数为改善。', '做了什么')
    by={name:raw('opt2d_step14',n,f'{name}/protection_routes.csv') for name in ['base','spacing','small','both','opt_base']}
    rows=[]
    for base in by['base']:
        rid=base['route_id']; values=[]
        for name in ['spacing','small','both','opt_base']:
            r=next(r for r in by[name] if r['route_id']==rid); values.append(fmt(r['delta_vs_base_db']))
        rows.append([rid,fmt(base['total_loss_db']),*values])
    table(f'{n}条实验固定11条连接的损耗变化',['路线ID','base损耗（dB）','spacing','small','both','opt_base'],rows,[2.0,3.0,3.0,3.0,3.0,3.0],text_cols=(),groups=[(2,5,'相对base的差值（dB）')],notes='差值保留4位小数；显示0.0000可能是小于舍入精度的数值，不表示用0替代缺失。touch差值全部为0，与base一致，省去重复列。不对不同路线ID作损耗排名。')
    if n==256:
        para('spacing让185恶化约0.0072 dB，small让186、185、177恶化，both让52恶化约0.0021 dB。虽然多数保护对象改善，每种约束仍有至少一条恶化，所以零余量验收拒绝。opt_base没有接受候选，全部保持原值。', '结果和结论')
    else:
        para('spacing和both对311分别恶化约0.3885、0.3376 dB；small对152恶化约0.0238 dB。opt_base改善7条、其余不恶化，满足逐路保护。集合均值或全局最大改善，不能代替逐路验收。', '结果和结论')
    source(f'3D/outputs/opt2d_step14/{n}/protection_set.json与各配置/protection_routes.csv。')
    if n==256:
        heading('保护余量诊断',('S14-03',),level=2)
        para('对固定保护集合扫描允许恶化0、0.001、0.002、0.005、0.01、0.02 dB，不改变已经生成的几何。256条both在0.005 dB时达到逐路余量要求，spacing和small在0.01 dB时达到；512条small、both、spacing的最大恶化分别0.0238、0.3376、0.3885 dB，在本次扫描的全部余量下仍未通过逐路保护。')
        para('这是对保护条件的诊断，任务仍采用0 dB余量；“通过余量”只描述保护集合，并不自动满足平均预算等其他条件。', '结论')
        source('3D/outputs/opt2d_step14/{256,512}/protection_margins.csv。')

heading('17 保护优化过程与放宽条件探针',('S14-05','S14-06'))
para('每个目标路线最多试4个候选，目标包含固定保护集合和压力情景的高损耗路线。逐候选评价平均预算、全局最大、11条保护路线和倍率5情景最大；失败则完整回滚。另改变候选排序强度及保护余量，检查拒绝限制。', '做了什么')
rows=[]
for n in (256,512):
    rec=jsread(P3/f'outputs/opt2d_step14/{n}/optimize_record.json')
    # Main counts and runtime are recorded by the actual optimizer, not comparison runtime.
    attempts=raw('opt2d_step14',n,'optimize_attempts_base.csv')
    runtime=233.1024483999936 if n==256 else 762.2401490000193
    accepted=sum(r.get('accepted')=='True' for r in attempts)
    rows.append([str(n),'严格主实验','0.00',str(len(attempts)),str(accepted),fmt(runtime,2),fmt(find(s14[n],'opt_base')['scenario5_max_loss_db'])])
    for r in raw('opt2d_step14',n,'probe/probe_summary.csv'):
        label=f"排序{fmt(r['rank_small_penalty_db'],1)} 余量{fmt(r['protected_slack_db'],2)}"
        rows.append([str(n),label,fmt(r['protected_slack_db'],2),integer(r['candidates_tried']),integer(r['accepted']),fmt(r['runtime_s'],2),fmt(r['scenario5_max_loss_db'])])
table('实际优化和全部保存的诊断探针',['规模','变体','余量（dB）','尝试','接受','耗时（s）','倍率5最大（dB）'],rows,[1.5,4.2,2.0,1.2,1.2,2.9,4.0],text_cols=(1,),notes='诊断预算与候选排序有差别，不按接受数或耗时跨行排优。256的strict_slack005实际参数是0.05 dB，名称不等于0.005。全部回滚指纹不一致次数均为0。')
para('严格主实验256条接受0/68，512条接受6/74，512平均3.2947→3.2936、最大5.4995→5.4654、倍率5最大5.7264→5.6340 dB。256条主要拒绝原因包括情景无改善62次、最大恶化32次及保护对象恶化；一个候选可同时触发多条拒绝，计数不能相加成总候选数。', '结果')
para('256条把排序强度调到0.5或2.0仍0接受；保护余量0.01/0.05时各接受2个候选，属于放宽条件诊断。512条严格排序0.5和余量0.01探针均接受5/33和5/28，情景最大同为约5.6392 dB，不能把“严格排序0接受”的256结论推广到512。', '结论')
source('3D/outputs/opt2d_step14/{256,512}/optimize_attempts_base.csv、optimize_record.json、probe/probe_summary.csv。')

heading('18 冻结半径后全部压力情景',('S14-07',))
para('保留六配置已经生成的几何，分别把小于20°交叉损耗乘以1、2、5、10，重新计算最大损耗；不重新优化各情景。', '做了什么')
sens=tabdata('t74_step14_sensitivity_data.csv')
table('六配置的全倍率最大损耗',['规模','配置','倍率1','倍率2','倍率5','倍率10'],[[r['channels'],r['scheme'],*[fmt(r[k]) for k in ['max_x1','max_x2','max_x5','max_x10']]] for r in sens],[1.6,2.2,3.3,3.3,3.3,3.3],text_cols=(1,),groups=[(2,5,'各倍率情景最大损耗（dB）')],best=[(11,2),(11,3),(11,4),(6,5),(9,5)],notes='仅在同规模、同倍率且已通过严格验收的base/touch/opt_base之间标粗有改善或更低的结果；256条三者相同，不标重复最优。spacing/small/both仍保留未验收状态。')
para('512条opt_base在倍率1、2、5时改善，但倍率10最大从8.4333变为8.4996 dB，略有恶化。small在倍率10的最大较低，但仍违反平均预算和固定保护条件。256条opt_base没有改动，全部压力结果与base一致。', '结果和结论')
heading('小角计数与间距权衡',level=2)
para('冻结半径后，256条small把小于20°交叉657→315，both降至371；512条small从2939→1125，both降至1209。spacing在512条虽然把间距不足1231→821，却使小于20°交叉增到3263。不能用一项改善代表所有风险改善。')
source('t74；3D/outputs/opt2d_step14/{256,512}/sensitivity.csv、comparison.csv。')

# Three-dimensional work, including all foundation steps and all executed scale experiments.
heading('19 三维几何与距离检测验证',('G3D-01','G3D-02','G3D-03'))
para('建立三维路线容器和局部抬层几何；用余弦过渡连接不同层，检查端点与切向连续；对直线、圆弧和过渡段的最小距离进行样本验证。', '做了什么')
table('三维基础验证记录',['验证项','真实样本路线（条）','独立差分点（个）','全测试通过（项）'],[['9A 路线容器与抬层','6','不适用','545'],['9B 曲率解析与数值','不适用','7','579'],['9C clearance分类','不适用','不适用','623']],[6.0,3.8,3.6,3.6],notes='9C使用6对路线和150对几何段。基础验证支持几何实现，不是全板路由结果。不同阶段测试数包含当时已有测试，不相加。')
para('9A将普通0/1/2、特殊13/14/15抬到2.75 mm，XY误差0、平面段长度不变。9B的Lxy = 10 mm、高度差1 mm过渡，真实最小半径20.2642 mm、有效参数25.25 mm；7点差分最大曲率误差6.356 × 10⁻¹² mm⁻¹，579项测试通过。')
para('9C在0.01 mm阈值下，同层0/24、0/25、0/26为碰撞；0/1、0/2、0/3间距0.175、0.350、0.525 mm为分离，另覆盖异层、阈值和过渡内部最近点，623项测试通过。未决不当作分离。', '距离验证')
para('几何容器、切向连接和距离检测能用于后续抬层；有效半径不等于真实最小半径，切向连续也不保证曲率连续。此验证没有计算三维器件传播损耗。', '结论')
source('3D/outputs/step_9_a_tests.json、step_9_b_curvature_join_validation.json、step_9_c_clearance_validation.json。')
heading('20 单路线抬层探针',('G3D-04',))
para('选3组真实相交路线对，逐次抬高其中一条；每次再检查该路线与其余511条邻居，测试能否消除目标近距对且不引入新对。阈值0.1 mm。', '做了什么')
table('三个真实路线对的独立抬层结果',['目标路线对','移动ID','碰撞邻线前','碰撞邻线后','新增邻线','增长（mm）'],[['0 / 24','24','230','217','0','0.243892'],['0 / 25','0','95','52','0','0.243892'],['0 / 26','26','230','217','0','0.243892']],[3.0,2.0,3.2,3.2,2.8,2.8],text_cols=(0,),notes='每组各45候选，20个通过目标检查、25个因自身判定有歧义拒绝。三个案例从各自原状态出发，不能同时叠加。')
para('3组均校验511个邻居，零新增碰撞，总耗时约68.6 s。合成十字探针从0→1→0 mm后，目标间距1 mm、额外长度0.243892 mm；端点和过渡连接均检查。', '结果')
para('单路线抬层具有局部可行性；它没有证明多路线同时抬层后全板无碰撞，因此继续执行顺序分配和1024条压力实例。', '结论')
source('3D/outputs/step_9_d_probe_summary.json、step_9_d_local_validation.json、step_9_d_synthetic.json。')

heading('21 两层与三层顺序分配',('G3D-05','G3D-06','G3D-07'))
para('在同一512条二维布局上执行两层30次探针，再以各50次尝试比较两层和三层。每次抬层后检查整个受影响集合，记录移除、新增与净变化，以总体近距对减少为收益。', '做了什么')
layers=tabdata('t81_3d_experiments_data.csv')
rows=[]
for r in layers[:3]:
    reduce=(int(r['initial_pairs'])-int(r['final_pairs']))/int(r['initial_pairs'])*100
    rows.append([f"{r['layers']}层 / {r['attempts']}次",integer(r['successful_elevations']),integer(r['initial_pairs']),integer(r['final_pairs']),fmt(reduce,2),fmt(r['extra_length_mm'],2),fmt(r['runtime_s'],2)])
table('512条连接的三组抬层结果',['配置','成功抬层','初始近距对','最终近距对','减少（%）','增长（mm）','耗时（s）'],rows,[3.0,1.9,2.6,2.6,2.1,2.4,2.4],text_cols=(0,),best=[(2,1),(2,3),(2,4),(1,5),(1,6)],notes='粗体只比较同为50次尝试的两层与三层：三层几何收益更好，两层成本更低。30次是先期探针。近距对用0.1 mm中心线阈值，与二维cross事件不同。')
para('两层30次成功12次，近距对减少4.06%；50次两层成功16次、减少5.84%，三层成功22次、减少8.32%。三层比两层多减少1224对，代价是额外长度与运行时间增加。', '结果')
para('新增近距对累计分别19、35、38；50次两层移除2929对、三层移除4156对，因此有新增但净数下降。三组均保留3对未决。30次的18次失败因双方已经抬过，本轮不重复抬层。', '碰撞账目与失败')
para('第三层没有“只有它才可行”的独有成功路线，额外收益来自更好的替代选择。层数增加在本次条件下有几何收益，但50次后仍有45400对近距路线，没有得到无碰撞版图。', '结论')
source('t81；3D/outputs/step_9_e_sequential_elevation_summary.json、step_9_f_{two_layer_control,three_layer}_summary.json、step_9_f_comparison.json。')

heading('22 固定1024条三层实验',('G3D-08',))
para('1024条输入在150 mm板高时，800条普通分配成功、160条轨道耗尽、64条特殊待解析；200 mm高提供1086根轨道，960条普通和64条特殊全部生成、耗尽0。最终使用300 × 200 mm区域。', '板容量负对照')
para('将固定输入确定性扩展成1024条合成连接，使用300 × 200 mm区域，层高0、1、2 mm，最多1024次尝试；局部抬高后回到底层，端点不变。中心线近距阈值0.1 mm。', '做了什么')
picture(P3/'outputs/figures/step_11_1024_3d_overview_z20.png',11.0,'自己的1024条三维总览 真实高度0 1 2 mm 显示高度放大20倍')
r=layers[3]; reduce=(int(r['initial_pairs'])-int(r['final_pairs']))/int(r['initial_pairs'])*100
continuation('终态结果与核对')
table('1024条合成输入的终态指标',['尝试','成功抬层','初始近距对','最终近距对','减少（%）','增长（mm）','耗时（s）'],[[r['attempts'],r['successful_elevations'],r['initial_pairs'],r['final_pairs'],fmt(reduce,2),fmt(r['extra_length_mm'],2),fmt(r['runtime_s'],2)]],[1.5,2.0,2.9,2.9,2.1,2.4,3.2],text_cols=(),notes='不同于512条的规模、板尺寸和尝试预算，独立报告，不跨规模评最优。所有指标是中心线几何统计。')
para('成功抬层175次，产生350个过渡；近距对204291→138113，减少32.39%。总长度增加87.41 mm，耗时1172.66 s，约19.5分钟；另有4对未决。终态849条在底层、72条主体在1 mm层、103条在2 mm层。', '结果')
para('累计移除68782对、新增2604对，净减少66178对；845次因双方已抬、4次无改善。独立重载1024条终态后全查523776路线对，与局部更新账目一致，696项测试通过。', '失败与终态独立复核')
para('局部抬层能减少约三分之一的近距对，但仍有大量剩余和未决对。这是合成压力实例的几何改善，没有计算三维光学损耗，也没有制作器件验证。', '结论')
source('3D/outputs/step_10_fixed_1024_{summary,initial_stats,validation,final_route_state,board_capacity_check}.json。')

heading('23 自己的三维结果图怎么读',('G3D-09',))
picture(P3/'outputs/figures/step_11_1024_xz_side.png',15.8,'自己的XZ侧视图 紫色是升层与降层过渡')
para('灰、蓝、橙分别表示0、1、2 mm层的主体段；紫色表示过渡。端点留在底层，被选中的路线在中段升高，末段降回底层。高度信息要结合近距检测判断。')
picture([P3/'outputs/figures/step_11_layer1_elevation_side.png',P3/'outputs/figures/step_11_layer2_elevation_side.png'],[8.15,8.15],'自己的局部抬层示例 左为1 mm层 右为2 mm层')
para('可视化阶段保存了13张原图，包括俯视、侧视、总览、分层和局部示例。图来自已保存的终态几何，不增加一次路由实验。俯视相交不能单独代表三维碰撞，也不能仅凭总览图声称碰撞已全部消除。', '结果和结论')
source('3D/outputs/step_11_visualization_summary.json；原图均位于3D/outputs/figures/。')

# =============================================================== 三维策略 v3 三组新实验（本轮新增）
page(); heading('三维策略v3 实验A：缓存与候选窗口余量的 512 四组功能消融',('V3-01',))
para('在同一份 512 条合成输入（'+ABLDATA+'）、同一初态（冻结的二维 z=0 平面路线）和同一几何阈值'
     '（0.1 mm 中心线近距、5 mm 过渡半径）下，只切换两个开关组合出四组：静态生成失败缓存与候选窗口余量 '
     'window_slack_mm。四组都使用策略 C、候选基本评价预算上限 720 次、目标尝试上限 50 次，验收规则不变。','做了什么')
para('本节的组字母 A/B/C/D 是本轮两项功能的消融分组，与历史策略字母 A/B/C 无关，不能按字母对应，目录名都带区分后缀。'
     '静态生成失败缓存只跳过“目标双方在完全相同的生成输入下都生成零候选”的目标，不占用 50 次正式目标尝试上限；'
     '候选窗口余量只把候选窗口的位置移离 0.1 mm 阈值边界。两者都不是加工公差，也不是光学安全裕量。','不混淆')
STOP={'TARGET_LIMIT':'目标上限','CANDIDATE_BUDGET_EXHAUSTED':'预算耗尽'}
ABLNOTE={'A_baseline_original':'两项新功能都关闭，复现历史行为',
         'B_generation_cache_only':'只开静态生成失败缓存（改的是调度）',
         'C_window_slack_only':'只开候选窗口余量（改的是生成）',
         'D_both_enabled':'两项同时开启'}
rows=[[label,cache,slack,ABLNOTE[key]] for key,label,cache,slack in GROUPS]
table('512 四组功能消融的分组定义',['分组','生成失败缓存','窗口余量（mm）','说明'],rows,[2.3,2.7,2.9,9.1],text_cols=(0,3),
      notes='“关/开”指该组是否启用对应功能。“窗口余量 1e-05 mm”是候选窗口的数值与几何余量，不是加工公差；'
            '初态（49,518 对近距、3 对未决）、输入、阈值、预算上限和验收规则四组完全相同。')
source('outputs/3d_strategy_v3/512_ablation/{A_baseline_original,B_generation_cache_only,C_window_slack_only,D_both_enabled}/config.json、'
       'ledger.json 与 cross_group_analysis.json。')
rows=[]
for key,label,cache,slack in GROUPS:
    g=GL[key]
    rows.append([label,integer(g['final_collision_pair_count']),fmt(g['reduction_percent'],2),integer(g['accepted_moves']),
                 integer(g['relocations']),fmt(g['final_extra_length_mm'],6),integer(g['candidate_evaluations']),
                 fmt(GS[key]['stats']['budget_used_percent'],1),STOP.get(g['stop_reason'],g['stop_reason'])])
table('512 四组功能消融的终态结果与代价',['分组','终态近距对','减少（%）','接受修改','重定位','额外长度（mm）',
      '实际评价（次）','预算使用（%）','停止原因'],rows,[2.6,1.75,1.65,1.5,1.3,2.0,1.6,1.6,3.0],text_cols=(0,8),
      best=[(3,1),(2,5)],
      notes='“减少（%）”是相对同一初态 49,518 对的减少比例，四组初态相同因此可比。粗体只标注严格可比范围内的最优：'
            '终态近距对最低为 D（四项功能组合中最低），额外长度最小为 C（6.912199 mm）；不对“单次运行时间”排名。'
            '四组预算上限都是 720 次，但实际评价次数 666/720/711/720 不同，相同预算上限不等于相同实际工作量。'
            '0 表示明确统计为零（四组重定位均为 0，不是缺失）。“停止原因”列把枚举值 TARGET_LIMIT 写为“目标上限”、'
            'CANDIDATE_BUDGET_EXHAUSTED 写为“预算耗尽”，原始枚举名见各组 ledger.json 的 stop_reason 字段，正文也照原样给出。')
source('outputs/3d_strategy_v3/512_ablation/各分组 ledger.json 的 final_collision_pair_count、reduction_percent、'
       'accepted_moves、relocations、final_extra_length_mm、candidate_evaluations、budget_used_percent、stop_reason。')
rows=[]
for key,label,cache,slack in GROUPS:
    g=CROSS['groups'][key]
    amb=sum(g['self_rejection_reasons'].values()) if g['self_rejection_reasons'] else 0
    rows.append([label,integer(g['target_attempts']),integer(g['unique_targets']),integer(g['repeat_attempts']),
                 integer(g['generation_skip_events']),integer(g['generated_candidates']),
                 integer(g['candidate_evaluations']),integer(g['full_neighbor_checks']),integer(amb)])
table('512 四组的调度、实际工作量与自检歧义记录',['分组','目标尝试（次）','不同目标（个）','重复尝试（次）','缓存跳过（次）',
      '生成候选（个）','实际评价（次）','完整邻线验收（次）','自检歧义（条）'],rows,
      [2.7,1.7,1.7,1.7,1.7,1.7,1.7,2.0,2.1],text_cols=(0,),
      notes='“自检歧义”是被评价候选在基本评价阶段因 SELF_AMBIGUOUS_CLEARANCE 被拒的条数：只有开窗口余量的 C、D 两组把它降到 0。'
            'B、D 的缓存跳过只涉及两个结构性零候选目标，作用是让它们不再反复占用 50 次正式目标尝试上限；'
            '零候选本身原本就不消耗候选评价预算，因此不能写成“节省候选调用”或“运行更快”。')
source('同上 cross_group_analysis.json、各组 summary.json 与 generation_skips.json。')
picture(V3FIG/'f1_group_pairs.png',16.4,'自己的结果：四组功能消融的终态中心线近距对与相对初态的减少量')
source('源图 outputs/3d_strategy_v3/figures/f1_group_pairs.png；共用图图内不带编号。'
       '本报告的图号由全文顺序自增，以本报告图注为准。图由已保存产物直接绘制，不新增实验。')
rows=[]
for key,label,cache,slack in GROUPS:
    g=GL[key]
    rows.append([label,integer(g['target_attempts']),integer(g['candidate_evaluations']),integer(g['candidate_budget']),
                 fmt(GS[key]['stats']['budget_used_percent'],1),fmt(g['runtime_seconds'],1),g['stop_reason']])
para('四组的实际评价次数并不相同：A 666、B 720、C 711、D 720，预算使用率分别是 92.50%、100.00%、98.75%、100.00%。'
     '相同预算上限不等于相同实际工作量。', '预算口径')
picture(V3FIG/'f2_pairs_vs_evaluations.png',16.4,'自己的结果：中心线近距对数随累计候选基本评价次数的变化（共同上限 720 次）')
source('源图 outputs/3d_strategy_v3/figures/f2_pairs_vs_evaluations.png，数据取自各组 curve.json 与 ledger.json；'
       '共用图图内不带编号，图号以本报告图注为准。')
picture(V3FIG/'f3_costs.png',16.4,'自己的结果：四组功能消融的额外长度、单次运行时间与候选评价预算使用率')
source('源图 outputs/3d_strategy_v3/figures/f3_costs.png；共用图图内不带编号，图号以本报告图注为准。'
       '运行时间是同机单次实测，没有重复测量与置信区间。')
a=GL['A_baseline_original']; b=GL['B_generation_cache_only']; c=GL['C_window_slack_only']; d=GL['D_both_enabled']
unres='、'.join(str(x) for x in sorted({g['final_unresolved_pair_count'] for g in (a,b,c,d)}))
para('（1）终态中心线近距对最低的是两项功能同开的 D 组 %s 对，比 A 组（%s 对）少 %d 对；C 组 %s 对、B 组 %s 对。'
     '四组相对同一初态的减少比例分别是 %s%%、%s%%、%s%%、%s%%。'
     % (integer(d['final_collision_pair_count']),integer(a['final_collision_pair_count']),
        a['final_collision_pair_count']-d['final_collision_pair_count'],integer(c['final_collision_pair_count']),
        integer(b['final_collision_pair_count']),fmt(a['reduction_percent'],2),fmt(b['reduction_percent'],2),
        fmt(c['reduction_percent'],2),fmt(d['reduction_percent'],2)),'结果')
para('（2）终态额外长度最小的是只开窗口余量的 C 组 %s mm；A、B、D 分别是 %s、%s、%s mm。'
     % (fmt(c['final_extra_length_mm'],6),fmt(a['final_extra_length_mm'],6),fmt(b['final_extra_length_mm'],6),
        fmt(d['final_extra_length_mm'],6)),'结果')
para('（3）四组预算上限相同（各 %s 次候选基本评价），但实际评价次数、预算使用率与停止原因都不同（见上表与图）。'
     'A、C 在目标上限处停止（%s），B、D 在预算耗尽处停止（%s），因此 B、D 的终态是预算口径下的结果，不能声称已经收敛。'
     % (integer(a['candidate_budget']),a['stop_reason'],b['stop_reason']),'结果')
para('（4）四组终态未决对都是 %s 对（TOUCHING_THRESHOLD）；阈值没有放宽，未决对没有当作 CLEAR 消除。' % unres,'结果')
para('（5）单次运行时间（同机、每组只跑一次）：A %s s、B %s s、C %s s、D %s s；'
     '总耗时约 %s 分钟。运行时间没有重复测量、没有置信区间，单次耗时不能支持普遍效率结论；'
     'B 组比 A 组耗时更长且预算耗尽，因此本轮的缓存与余量都不能用“更快”来表述。'
     % (fmt(a['runtime_seconds'],1),fmt(b['runtime_seconds'],1),fmt(c['runtime_seconds'],1),fmt(d['runtime_seconds'],1),
        fmt((a['runtime_seconds']+b['runtime_seconds']+c['runtime_seconds']+d['runtime_seconds'])/60,1)),'结果')
para('在本次 512 合成输入、同一预算上限与同一验收规则下，两项新功能的作用位置不同：生成缓存改的是调度'
     '（结构性零候选目标不再被反复尝试，目标尝试 50→27、重复尝试 25→0），窗口余量改的是生成'
     '（把落在阈值边界上的窗口位置移开，被评价候选的自检歧义从 A 的 331 条、B 的 356 条降到 0 条）。'
     '两项同开的 D 组终态最低，只开余量的 C 组额外长度最小；本轮每组只运行一次、只有一个 512 输入，'
     '不能外推为普遍结论，也没有做目标级归因。','结论')
para('口径限制：全部比较指标是 0.1 mm 中心线近距对数，不代表光学损耗、串扰、无碰撞制造或工艺合规；'
     '512 是项目既有合成输入 '+ABLDATA+'，不是真实端口数据；本轮没有器件实测。','限制')
source('outputs/3d_strategy_v3/512_ablation/summary_all.json、各分组 summary.json 与 recheck.json'
       '（四组落盘重载后 130,816 对全查、重载一致、终态几何四项检查均为真）。')

page(); heading('三维策略v3 实验B：窗口余量对 331 条自检歧义候选的探针',('V3-02',))
para('从冻结平面几何与保存的 CROSS 锚点重建修正版 C 在 512 主实验中保存的全部自检歧义候选'
     '（基本评价阶段因 SELF_AMBIGUOUS_CLEARANCE 被拒），再用 window_slack_mm=%s 重新枚举候选窗口，'
     '在每个已记录候选的 ±2δ 内寻找唯一对应窗口并重建候选，只对候选自身的净距做判定。'
     '不重新布线、不改 0.1 mm 阈值、不放宽任何验收规则。'
     % ('%g' % PROBEJ['window_slack_mm']),'做了什么')
para('数学关系：设 δ = window_slack_mm / 直线长度。端点内缩量由 clearance/length 变为 (clearance+slack)/length，'
     '可用区间 [lo, hi] 的两端各内缩 δ、宽度缩小 2δ；三个位置参数 f = 0、0.5、1 的位移为 (1−2f)δ，'
     '即锚定左端的位置平移 +δ、中间位置不动、贴近右端的位置平移 −δ；过渡长度 run/length 与过渡数量不变；'
     '本来就勉强可行的窗口可能因这 2δ 的收缩而消失（hi−lo < width 时该窗口不再被枚举）。','必须写清的数学')
para('本节按上面这组 δ 收缩关系叙述，不使用此前文档中已被判定为错误的等价性说法，也不做超出本次实测范围的一般性保证；'
     '只保留“0.1 mm 中心线近距阈值与全部验收规则保持不变”这一事实。','口径更正')
st=PROBEJ['status_after_shift']; tw=PROBEJ['task_window_counts']
rows=[['已记录的自检歧义候选（条）',integer(PROBEJ['recorded_rows'])],
      ['涉及生成任务（个）',integer(PROBEJ['unique_tasks'])],
      ['加余量后判为 CLEAR（条）',integer(st['CLEAR'])],
      ['加余量后仍为 AMBIGUOUS_CLEARANCE / 判为 COLLISION / 判为 TOUCHING_THRESHOLD / 其它非 CLEAR 歧义（条）',
       '%s / %s / %s / %s' % (integer(st['still_ambiguous']),integer(st['collision']),
                             integer(st['touching_threshold']),integer(st['other_ambiguous_status']))],
      ['无法匹配到窗口（条）',integer(st['window_not_available'])],
      ['生成阶段被拒（条）',integer(st['build_rejected'])],
      ['这 %s 个任务的候选总数（余量 0 → 余量 1e-5，个）' % integer(PROBEJ['unique_tasks']),
       '%s → %s' % (integer(tw['total_candidates_at_slack_zero']),integer(tw['total_candidates_at_probe_slack']))],
      ['加余量后候选变少的任务数（个）',integer(tw['tasks_with_fewer_candidates_after_shift'])],
      ['这些任务中层失败原因发生变化的记录数',integer(len(PROBEJ['failure_shifts_on_recorded_tasks']))]]
table('窗口余量探针：已记录自检歧义候选的复核结果',['项目','数值'],rows,[10.2,4.8],text_cols=(0,),
      notes='“无法匹配到窗口”为 0 表示已记录候选都在 ±2δ 内找到了唯一对应窗口。'
            '候选总数 666 → 666 表示这些任务没有因为余量而失去或获得候选；'
            '层失败原因变化记录数为 0 表示这些任务的失败原因没有改变。未决状态没有被当作 CLEAR。')
source('outputs/3d_strategy_v3/window_slack_probe/window_slack_probe.json（含 limitation 字段）。')
smp=PROBEJ['samples'][0]
para('%s 条候选的自身净距全部由 AMBIGUOUS_CLEARANCE 变为 CLEAR（仍为歧义 0 条、判为碰撞 0 条、判为临界 0 条）。'
     '样本（第 %d 步、目标 (%d,%d)、移动路线 %d、层 %d、候选 %d）在加余量后的最小距离为 %s mm，'
     '阈值仍是 %s mm，状态 CLEAR。'
     % (integer(st['CLEAR']),smp['step_index'],smp['target'][0],smp['target'][1],smp['moved'],smp['layer'],
        smp['candidate_index'],fmt(smp['minimum_distance_mm'],6),fmt(PROBEJ['clearance_mm'],1)),'结果')
gA=CROSS['groups']['A_baseline_original']['generation_failure_reasons']
gC=CROSS['groups']['C_window_slack_only']['generation_failure_reasons']
def failcount(d,key): return sum(v for k,v in d.items() if key in k)
para('余量也带来生成端的细微变化：A 组（余量 0）的生成失败记录为 INSUFFICIENT_TRANSITION_SPACE %d 次、'
     'NO_VALID_TRANSITION_WINDOW %d 次；C 组（余量 1e-5）为 %d 次与 %d 次，'
     '说明余量在至少一个目标上把失败原因从“过渡空间不足”改成了“没有可用过渡窗口”，'
     '即加余量确实可能让本来就勉强可行的窗口从枚举中消失。'
     % (failcount(gA,'INSUFFICIENT_TRANSITION_SPACE'),failcount(gA,'NO_VALID_TRANSITION_WINDOW'),
        failcount(gC,'INSUFFICIENT_TRANSITION_SPACE'),failcount(gC,'NO_VALID_TRANSITION_WINDOW')),'负效应证据')
para('（1）自检歧义消除不等于目标近距对与完整邻线验收通过。本轮探针只判定候选自身的净距；'
     '候选是否被接受还要看目标对是否被清除、与全部邻线的逐一关系以及全局近距对是否严格下降。','结论')
para('（2）探针不等于全局未决对清零。四组主实验的终态未决对仍是 %s 对，本轮没有任何阈值放宽，'
     '未决状态没有被当作 CLEAR 消除。' % unres)
para('（3）范围只有这一份 512 合成输入与这 %s 个已记录生成任务；1024 与其他输入没有做同样的逐候选复核，'
     '不能把 331/331 当作普遍结论。' % integer(PROBEJ['unique_tasks']))
para('（4）探针只覆盖“已记录”的那些候选；它不说明没有被记录为歧义的候选会怎样，也不说明其它规模或其它余量取值会怎样。')
source('outputs/3d_strategy_v3/window_slack_probe/window_slack_probe.json、wording_fix_check.json 与 '
       'outputs/3d_strategy_v3/512_ablation/cross_group_analysis.json。')

page(); heading('三维策略v3 实验C：加余量的固定重定位诊断（新 D / 新 E）',('V3-03',))
para('历史诊断在 512 条 B 终态（%s 对近距、%s 条已抬升路线）上预先固定 %s 个目标（%s 对双方均已抬升、%s 对仅一方已抬升），'
     'D 组只允许首次抬升，E 组还允许把已经抬升的路线重定位到另一层；当时 E 实际生成并完整评价了 %s 个重定位候选，'
     '其中 %s 个在基本评价阶段因自检歧义被拒，没有任何候选通过全部验收，D 与 E 的终态相同（%s 对）。'
     '本轮把 window_slack_mm=%s 加进同一诊断：起点、目标清单、处理顺序、预算上限、几何阈值和验收规则全部不变，'
     '静态生成失败缓存保持关闭。'
     % (integer(CANDIAG['start_pair_scan_collisions']),integer(CANDIAG['start_elevated_route_count']),
        integer(len(CANDIAG['targets'])),integer(len(CANDIAG['both_elevated_targets'])),
        integer(len(CANDIAG['one_elevated_targets'])),
        integer(MS['old_E']['RELOCATION']['basic_evaluations']),
        integer((MS['old_E']['RELOCATION']['basic_rejection_reason_occurrences'] or {}).get('SELF_AMBIGUOUS_CLEARANCE',0)),
        integer(OL['D']['final_collision_pair_count']),'%g' % CANDIAG['window_slack_mm']),'做了什么')
para('重定位必须满足：从原始冻结平面路线重建替代候选；保留端点与 XY 投影；替换当前路线而不是叠加升降结构；'
     '保持切向连接、过渡半径与原有保守验收规则；与当前全部邻线逐一验收；未决状态不得当作 CLEAR；'
     '每次接受修改后全局近距对必须严格下降。','重定位规则')
rows=[]
for era,tag,led in (('旧诊断','D',OL['D']),('新诊断','D',DL['D']),('旧诊断','E',OL['E']),('新诊断','E',DL['E'])):
    rows.append(['%s %s' % (era,tag),integer(led['final_collision_pair_count']),
                 integer(CANDIAG['start_pair_scan_collisions']-led['final_collision_pair_count']),
                 integer(led['accepted_moves']),integer(led['first_elevations']),integer(led['relocations']),
                 integer(led['relocation_candidate_evaluations']),integer(led['candidate_evaluations']),
                 fmt(led['final_extra_length_vs_planar_mm'],4),fmt(led['runtime_seconds'],1)])
table('加余量前后的固定重定位诊断对照（同一起点 %s 对、同一 %s 目标清单）'
      % (integer(CANDIAG['start_pair_scan_collisions']),integer(len(CANDIAG['targets']))),
      ['组','终态近距对','净减少（对）','接受修改','首次抬升','接受重定位','重定位候选评价（次）','候选评价合计（次）',
       '终态额外长度（mm）','单次运行时间（s）'],rows,[2.1,1.65,1.5,1.4,1.4,1.5,1.9,1.85,2.0,1.7],text_cols=(0,),
      best=[(3,1)],
      notes='四行共用同一起点、同一目标清单、同一顺序、同一几何阈值与同一验收规则。粗体只标注四行中终态近距对最低者（新 E）。'
            '“预算上限同为 %s 次”只表示上限相同：实际候选评价次数 %s/%s/%s/%s 两两不同，不能称相同实际工作量；'
            '运行时间是单次实测，不能据此得出普遍效率结论。0 表示明确统计为零（旧诊断两组的重定位接受为 0）。'
      % (integer(CANDIAG['candidate_budget_ceiling']),integer(OL['D']['candidate_evaluations']),integer(DL['D']['candidate_evaluations']),
         integer(OL['E']['candidate_evaluations']),integer(DL['E']['candidate_evaluations'])))
source('outputs/3d_strategy_v2_rev2/512_de_diagnostic/ledger_{D,E}.json（旧诊断对照）与 '
       'outputs/3d_strategy_v3/512_relocation_slack_diagnostic/ledger_{D,E}.json、comparison_DE.csv（本轮）。')
para('新 D 与旧 D 的决策序列、终态近距集合、未决集合和统计指标保持一致：终态近距对 %s 对、接受修改 %s 次、'
     '首次抬升 %s 次、候选评价 %s 次、额外长度 %s mm；但 8 条路线的窗口几何发生了微小变化'
     '（平移约 1e-5 mm），本轮不声称几何或原始 decisions 逐字节相同。'
     % (integer(DL['D']['final_collision_pair_count']),integer(DL['D']['accepted_moves']),
        integer(DL['D']['first_elevations']),integer(DL['D']['candidate_evaluations']),
        fmt(DL['D']['final_extra_length_vs_planar_mm'],4)),'新 D')
para('新 E 第一次接受了重定位：终态从 %s 对降到 %s 对（少 %d 对），接受修改 %s 次（其中首次抬升 %s 次、重定位 %s 次），'
     '重定位候选评价从 %s 次降到 %s 次，候选评价合计从 %s 次降到 %s 次。'
     '原因是第 %d 步的重定位被接受后，剩下 6 个“双方均已抬升”的目标不再处于近距状态'
     '（目标状态变为 TARGET_NO_LONGER_COLLIDING），因此不再需要逐候选评价；'
     '本轮目标状态为“不再近距”的目标数为 D 组 %s 个、E 组 %s 个（旧诊断 E 为 %s 个）。'
     % (integer(OL['E']['final_collision_pair_count']),integer(DL['E']['final_collision_pair_count']),
        OL['E']['final_collision_pair_count']-DL['E']['final_collision_pair_count'],
        integer(DL['E']['accepted_moves']),integer(DL['E']['first_elevations']),integer(DL['E']['relocations']),
        integer(OL['E']['relocation_candidate_evaluations']),integer(DL['E']['relocation_candidate_evaluations']),
        integer(OL['E']['candidate_evaluations']),integer(DL['E']['candidate_evaluations']),ENTRY['step_index'],
        integer(DL['D']['targets_no_longer_colliding']),integer(DL['E']['targets_no_longer_colliding']),
        integer(OL['E']['targets_no_longer_colliding'])),'新 E')
para('长度代价：新 E 相对诊断起点的总长度变化为 +%s mm，终态额外长度相对原始平面为 %s mm；'
     '新 D 相对起点 +%s mm、相对平面 %s mm。即新 E 用多 %s mm 的终态额外长度换到少 %d 对近距对。'
     % (fmt(LENGTH['modes']['E']['delta_vs_diagnostic_start_mm'],4),fmt(LENGTH['modes']['E']['final_extra_length_vs_planar_mm'],4),
        fmt(LENGTH['modes']['D']['delta_vs_diagnostic_start_mm'],4),fmt(LENGTH['modes']['D']['final_extra_length_vs_planar_mm'],4),
        fmt(LENGTH['modes']['E']['final_extra_length_vs_planar_mm']-LENGTH['modes']['D']['final_extra_length_vs_planar_mm'],4),
        OL['E']['final_collision_pair_count']-DL['E']['final_collision_pair_count']),'长度')
picture(V3FIG/'f4_diagnostic_comparison.png',16.4,'自己的结果：旧诊断（余量 0）与加余量诊断（1e-5 mm）的终态、实际评价次数、额外长度与单次运行时间对照')
source('源图 outputs/3d_strategy_v3/figures/f4_diagnostic_comparison.png；'
       '数据来自两组 ledger_{D,E}.json。图由已保存产物直接绘制，不新增实验。')
heading('逐候选对应：不是“%s 条全部解决”' % integer(CORR_REL['old_self_ambiguous_rows']),level=2)
para('只看歧义总数下降不能说明具体候选被解决，因此本轮把旧诊断 E 与新诊断 E 的重定位候选逐条建立对应：'
     '生成始终使用冻结平面路线与冻结锚点，同一（目标、victim、层）任务的候选集合可以逐窗口匹配，'
     '匹配规则是“层、起升直线编号、下降直线编号、窗口宽度完全一致，窗口起点位移不超过 2δ”。'
     '只有找到唯一对应候选的那些条目才能给出逐候选结论。','方法')
rows=[['有唯一对应候选的旧候选（条）',integer(CORR_REL['matched'])],
      ['　其中：加余量后通过基本评价（条）',integer((CORR_REL['old_to_new_basic_status'] or {}).get('REJECTED -> ACCEPTED_TARGET_PAIR_ONLY',0))],
      ['　其中：加余量后仍被拒（条）',integer((CORR_REL['old_to_new_basic_status'] or {}).get('REJECTED -> REJECTED',0))],
      ['　其中：加余量后通过完整验收（条）',integer(CORR_REL['matched_to_full_acceptance'])],
      ['　其中：加余量后在完整验收被拒（条）',integer(CORR_REL['matched_full_rejected'])],
      ['本轮未再出现的旧候选（条）',integer(sum(CORR_REL['unmatched'].values()))],
      ['　原因：该生成任务本轮没有执行（条）',integer(CORR_REL['unmatched'].get('TASK_NOT_REACHED_IN_NEW_RUN',0))],
      ['找不到对应窗口（条）',integer(CORR_REL['unmatched'].get('NO_CORRESPONDING_WINDOW_IN_NEW_RUN',0))]]
table('旧诊断 E 的 %s 条重定位自检歧义候选：逐候选对应结果' % integer(CORR_REL['old_self_ambiguous_rows']),
      ['项目','条数'],rows,[10.6,4.4],text_cols=(0,),
      notes='“本轮未再出现的旧候选”不能算作被解决：它们所在的生成任务在本轮没有执行'
            '（被接受的重定位先把这些目标清除了），因此本轮对它们既没有正面证据也没有负面证据；'
            '只有“有唯一对应候选”的 %s 条才能给出逐候选结论，不能写成“%s 条全部解决”。'
      % (integer(CORR_REL['matched']),integer(CORR_REL['old_self_ambiguous_rows'])))
source('outputs/3d_strategy_v3/512_relocation_slack_diagnostic/analysis.json 的 correspondence_relocation_candidates；'
       '逐条原始记录见同目录 candidate_correspondence.json。')
rows=[]
for name,src_ in (('重定位候选',CORR_REL),('全部移动类别（含首次抬升）',CORR_ALL)):
    rows.append([name,integer(src_['old_self_ambiguous_rows']),integer(src_['matched']),
                 integer(src_['matched_to_basic_pass']),integer(src_['matched_still_rejected']),
                 integer(src_['matched_to_full_acceptance']),integer(src_['matched_full_rejected']),
                 integer(src_['unmatched'].get('TASK_NOT_REACHED_IN_NEW_RUN',0))])
table('旧诊断 E 全部自检歧义候选的对应统计（两个口径分开列出）',
      ['范围','旧候选（条）','有唯一对应（条）','通过基本评价（条）','基本评价被拒（条）',
       '通过完整验收（条）','完整验收被拒（条）','本轮任务未执行（条）'],
      rows,[3.0,1.9,2.0,2.0,2.0,2.0,2.0,2.1],text_cols=(0,),
      notes='“通过基本评价”与“通过完整验收”都是候选条数，不是被接受的修改次数：'
            '全部 %s 条有唯一对应的候选中 %s 条通过基本评价，其中 %s 条通过完整验收、%s 条在完整验收被拒（%s）。'
            '通过验收不等于实际执行：一个步骤只执行它选中的那一个候选，本轮两条诊断实际执行的修改合计 %s 次'
            '（新 D %s 次、新 E %s 次，其中重定位 %s 次）。'
            '旧诊断 E 的全部自检歧义候选共 %s 条，其中 %s 条属于重定位候选（上一张表的口径）。'
            '两行的“有唯一对应”都只覆盖各自范围的一部分：%s = %s + %s，%s = %s + %s；'
            '未执行的 %s 条不参与任何通过率计算。'
      % (integer(CORR_ALL['matched']),integer(CORR_ALL['matched_to_basic_pass']),
         integer(CORR_ALL['matched_to_full_acceptance']),integer(CORR_ALL['matched_full_rejected']),
         '、'.join(CORR_ALL['matched_full_reject_reasons']),
         integer(AEC['total']),integer(AEC['new_D']),integer(AEC['new_E']),integer(AEC['new_E_relocations']),
         integer(CORR_ALL['old_self_ambiguous_rows']),integer(CORR_REL['old_self_ambiguous_rows']),
         integer(CORR_REL['matched']),integer(CORR_REL['matched_to_basic_pass']),
         integer(CORR_REL['matched_still_rejected']),
         integer(CORR_ALL['matched']),integer(CORR_ALL['matched_to_basic_pass']),
         integer(CORR_ALL['matched_still_rejected']),
         integer(CORR_ALL['unmatched'].get('TASK_NOT_REACHED_IN_NEW_RUN',0))))
source('同上 analysis.json 的 correspondence_all_movement_classes。')
relrecs=CORR_REL['records']
lay_ok=sum(1 for r in relrecs if r.get('match')=='MATCHED' and r.get('new_basic_status')=='ACCEPTED_TARGET_PAIR_ONLY' and r.get('layer')==2)
lay_no=sum(1 for r in relrecs if r.get('match')=='MATCHED' and r.get('new_basic_status')=='REJECTED' and r.get('layer')==1)
para('在有唯一对应的 %s 条中，%s 条（层 2 的窗口布置）加余量后通过基本评价，另 %s 条（层 1）仍因 TARGET_NOT_CLEARED 被拒：'
     '余量只解决候选自身的自检歧义，不解决“目标近距对没有被清除”。通过基本评价的 %s 条里，%s 条通过完整验收、'
     '%s 条在完整验收被拒（均为 %s）；通过验收不等于实际执行，实际执行的修改是新 D %s 次、新 E %s 次（含重定位 %s 次），合计 %s 次。'
     % (integer(CORR_REL['matched']),integer(lay_ok),integer(lay_no),
        integer(CORR_REL['matched_to_basic_pass']),integer(CORR_REL['matched_to_full_acceptance']),
        integer(CORR_REL['matched_full_rejected']),'、'.join(CORR_REL['matched_full_reject_reasons']),
        integer(AEC['new_D']),integer(AEC['new_E']),integer(AEC['new_E_relocations']),integer(AEC['total'])),'读数')
para('新 E 第 %d 步、目标 (%d,%d)，移动路线 %d，运动类型 %s：路线由层 %d 改到层 %d（目标层 id %d），'
     '移除 %d 对近距、新增 %d 对，全局近距对 %s → %s（严格下降），单步长度变化 +%s mm。'
     % (ENTRY['step_index'],ENTRY['target_pair'][0],ENTRY['target_pair'][1],ENTRY['route_id'],ENTRY['movement'],
        LAYER_BEFORE,LAYER_AFTER,ENTRY['target_layer_id'],len(ENTRY['old_collisions_removed']),
        len(ENTRY['new_collisions_created']),integer(ENTRY['global_pairs_before']),integer(ENTRY['global_pairs_after']),
        fmt(ENTRY['step_length_delta_mm'],4)),'被接受的修改')
para('该路线重定位前长度 %s mm、过渡段 %d 段；重定位后长度 %s mm、过渡段 %d 段；原始平面路线长度 %s mm。'
     '过渡段数保持不变，说明是把当前路线整体替换掉，而不是在已有升降结构上再叠加一层；'
     '端点与 XY 投影、切向连接与过渡半径都保持通过。'
     % (fmt(BA['before_length_mm'],4),BA['before_transition_count'],fmt(BA['after_length_mm'],4),
        BA['after_transition_count'],fmt(BA['planar_length_mm'],4)),'替换而非叠加')
rows=[]
for movement,mlabel in (('FIRST_ELEVATION','首次抬升'),('RELOCATION','重定位')):
    for mode in ('D','E'):
        m=MOVEMENT['modes'][mode][movement]
        rows.append(['%s（新 %s）' % (mlabel,mode),integer(m['victim_attempts_total']),
                     integer(m['victim_attempts_with_generation']),integer(m['generated_candidates']),
                     integer(m['basic_evaluations']),integer(m['basic_passed']),integer(m['full_acceptance_checks']),
                     integer(m['full_acceptance_passed']),integer(m['accepted_edits'])])
table('按运动类别分别记录的尝试、生成、评价与接受（新诊断）',
      ['类别','路线尝试（次）','实际生成（次）','生成候选（个）','基本评价（次）','基本通过（个）','完整验收（次）',
       '完整通过（个）','接受（次）'],rows,[2.0,1.7,1.7,1.7,1.7,1.6,1.7,1.7,1.7],text_cols=(0,),
      notes='“路线尝试”包含因 D 组规则被跳过、没有发生生成的尝试（新 D 的 %s 次重定位尝试全部属于此类，'
            '状态为 ROUTE_ALREADY_ELEVATED_NOT_ALLOWED_IN_D）；“实际生成”只统计真正调用生成器的尝试。'
            '两列同时给出，避免把“没有触发重定位”与“重定位候选全部失败”混为一谈。'
      % integer(MOVEMENT['modes']['D']['RELOCATION']['victim_attempts_total']))
source('outputs/3d_strategy_v3/512_relocation_slack_diagnostic/movement_stats.json。')
oldEm=MS['old_E']['RELOCATION']; newEm=MS['new_E']['RELOCATION']
rows=[['自检歧义 SELF_AMBIGUOUS_CLEARANCE','基本评价',
       integer((newEm['basic_rejection_reason_occurrences'] or {}).get('SELF_AMBIGUOUS_CLEARANCE',0)),
       integer((oldEm['basic_rejection_reason_occurrences'] or {}).get('SELF_AMBIGUOUS_CLEARANCE',0))],
      ['目标近距对未清除 TARGET_NOT_CLEARED','基本评价',
       integer((newEm['basic_rejection_reason_occurrences'] or {}).get('TARGET_NOT_CLEARED',0)),
       integer((oldEm['basic_rejection_reason_occurrences'] or {}).get('TARGET_NOT_CLEARED',0))],
      ['全局近距对未严格下降 NO_STRICT_GLOBAL_DECREASE','完整邻线验收',
       integer((newEm['full_rejection_reason_occurrences'] or {}).get('NO_STRICT_GLOBAL_DECREASE',0)),
       integer((oldEm['full_rejection_reason_occurrences'] or {}).get('NO_STRICT_GLOBAL_DECREASE',0))]]
table('重定位候选的拒绝理由出现次数',['拒绝理由','发生在','新诊断 E（次）','旧诊断 E（次）'],rows,[7.4,2.8,3.4,3.4],text_cols=(0,1),
      notes='统计口径：一个候选可能同时带多个拒绝理由，因此这里统计的是“理由出现次数”，不同理由的次数不能相加成候选数。'
            '按候选去重的计数保存在 movement_stats.json 的 candidates_with_reason 字段中。'
            '旧诊断 E 的 %s 个重定位候选中，自检歧义理由出现 %s 次、目标未清除理由出现 %s 次，两者之和大于候选数，'
            '正是这个口径的直接例子；新诊断 E 的 %s 个候选中 %s 个因目标未清除在基本评价阶段被拒，'
            '另外 %s 个进入完整验收、其中 %s 个因全局近距对未严格下降被拒、%s 个被接受。'
      % (integer(oldEm['basic_evaluations']),
         integer((oldEm['basic_rejection_reason_occurrences'] or {}).get('SELF_AMBIGUOUS_CLEARANCE',0)),
         integer((oldEm['basic_rejection_reason_occurrences'] or {}).get('TARGET_NOT_CLEARED',0)),
         integer(newEm['basic_evaluations']),integer(newEm['basic_rejected']),integer(newEm['full_acceptance_checks']),
         integer((newEm['full_rejection_reason_occurrences'] or {}).get('NO_STRICT_GLOBAL_DECREASE',0)),
         integer(newEm['accepted_edits'])))
source('outputs/3d_strategy_v3/512_relocation_slack_diagnostic/movement_stats.json 与 analysis.json 的 movement_stats 段。')
picture(V3FIG/'f5_relocation_rejections.png',16.4,'自己的结果：重定位候选的失败原因（旧诊断 0 次接受、%s 个候选；新诊断 1 次接受、%s 个候选）'
        % (integer(oldEm['basic_evaluations']),integer(newEm['basic_evaluations'])))
source('源图 outputs/3d_strategy_v3/figures/f5_relocation_rejections.png。'
       '同一候选可有多个拒绝理由，出现次数不能相加成候选数。')
picture(V3FIG/'f7_route34_relocation_before_after.png',16.0,
        '自己的结果：路线 %d 被接受的这一次重定位前后（XY 投影、XZ 侧视、真实高度比例三维图、Z 轴放大 20 倍示意图；真实层高 0/1/2 mm）'
        % ENTRY['route_id'])
source('源图 outputs/3d_strategy_v3/figures/f7_route34_relocation_before_after.png；'
       'before/after 几何取自 analysis.json 的 accepted_relocation_before_after。')
rows=[]
for mode in ('D','E'):
    L=LENGTH['modes'][mode]
    neg=('不适用' if L['accepted_move_count']-DL[mode]['first_elevations']==0
         else fmt(L['relocation_step_delta_mm'],4))
    rows.append(['新诊断 %s' % mode,fmt(L['delta_vs_diagnostic_start_mm'],4),fmt(L['first_elevation_step_delta_mm'],4),neg,
                 fmt(L['start_extra_length_vs_planar_mm'],4),fmt(L['final_extra_length_vs_planar_mm'],4),
                 integer(L['accepted_move_count']),integer(L['negative_step_count']),
                 '一致' if L['delta_vs_diagnostic_start_consistent'] else '不一致'])
table('长度记账（相对诊断起点与相对原始平面）',['组','相对起点总变化（mm）','首次抬升长度（mm）','重定位长度（mm）',
      '起点额外长度（mm）','终态额外长度（mm）','接受修改（次）','单步负增长（次）','前后核对'],rows,
      [1.9,2.1,2.0,2.1,2.0,2.0,1.5,1.6,1.5],text_cols=(0,8),
      notes='“不适用”表示该组没有接受任何重定位，重定位的长度代价没有意义；这与“0”不同。'
            '“单步负增长”是单步长度变化小于 0 的次数，本轮两组都是 0。')
source('outputs/3d_strategy_v3/512_relocation_slack_diagnostic/length_ledger.json 与 ledger_{D,E}.json。')
para('把 10 nm 的窗口余量加进历史固定重定位诊断后，E 组第一次接受了重定位：路线 %d 从层 %s 改到层 %s，'
     '全局近距对 %s → %s，终态从 %s 降到 %s（少 %d 对）；代价是终态额外长度相对原始平面从 %s mm 增加到 %s mm，'
     '而重定位候选评价次数反而从 %s 次降到 %s 次。这次接受不是“放宽规则”的结果：'
     '0.1 mm 阈值、半径规则、端点与 XY 投影、切向连接、完整邻线验收以及“全局近距对必须严格下降”全部照旧。'
     % (ENTRY['route_id'],integer(LAYER_BEFORE),integer(LAYER_AFTER),
        integer(ENTRY['global_pairs_before']),integer(ENTRY['global_pairs_after']),
        integer(OL['E']['final_collision_pair_count']),integer(DL['E']['final_collision_pair_count']),
        OL['E']['final_collision_pair_count']-DL['E']['final_collision_pair_count'],
        fmt(OL['E']['final_extra_length_vs_planar_mm'],4),fmt(DL['E']['final_extra_length_vs_planar_mm'],4),
        integer(OL['E']['relocation_candidate_evaluations']),integer(DL['E']['relocation_candidate_evaluations'])),'结论')
para('本轮只有 1 个起点、1 份 %s 目标清单、1 个余量取值和 1 次被接受的重定位，结论只覆盖这一份诊断；'
     'D 组（只允许首次抬升）在加余量前后决策序列、终态集合与统计指标保持一致，只有 8 条路线的窗口几何有'
     '1e-5 mm 量级的平移。' % integer(len(CANDIAG['targets'])),'限制')
para('旧诊断 E 的 %s 条重定位歧义候选中有 %s 条所在的生成任务本轮没有执行，'
     '因此它们既没有被证明解决，也没有被证明仍未解决；只有有唯一对应的 %s 条能给出逐候选结论。'
     % (integer(CORR_REL['old_self_ambiguous_rows']),
        integer(CORR_REL['unmatched'].get('TASK_NOT_REACHED_IN_NEW_RUN',0)),integer(CORR_REL['matched'])))
para('运行时间是单次实测（新 D %s s、新 E %s s；旧 D %s s、旧 E %s s），不能据此得出普遍效率结论。'
     '全部指标仍是 0.1 mm 中心线近距对数，不代表损耗、串扰、无碰撞制造或工艺合规；'
     '本轮没有器件实测，也没有计算三维光学损耗。'
     % (fmt(DL['D']['runtime_seconds'],1),fmt(DL['E']['runtime_seconds'],1),
        fmt(OL['D']['runtime_seconds'],1),fmt(OL['E']['runtime_seconds'],1)),'限制')
source('outputs/3d_strategy_v3/512_relocation_slack_diagnostic/recheck_{D,E}.json（两组落盘重载后 130,816 对全查、'
       '重载一致、终态几何四项检查均为真、终态未决对仍为 %s 对）。' % integer(DL['E']['final_unresolved_pair_count']))

page(); heading('24 全部实验可以得出的结论')
para('二维复现方面，原版几何和直线加弯曲损耗有逐路一致性证据，主要损耗数值接近原报告。交叉表含数字化近似，精确求交与整数角统计必须分开使用。')
para('优化方面，扩大半径和减少总转弯角度带来的收益明显大于当前轨道候选搜索。固定端点、逐路半径一致的对照进一步支持自由弯角的作用，同时它会增加小角交叉和间距不足。')
para('约束方面，降低间距违规或压力情景最大值并不等于全部保护路线都改善。严格保护下256条没有找到可接受改进；512条找到6个接受候选，带来小幅损耗改善。倍率10的结果仍略恶化。')
para('早期交叉诊断方面，反转排序能改善部分双交叉，但会新增多交叉；硬约束会耗尽轨道，未完成全板。局部单线恢复沙箱有1到2个多交叉改善，尚未合并为完整全板结果。')
para('三维方面，增加高度层和局部抬升可以减少中心线近距对。1024条合成实例减少32.39%，仍剩138113对和4对未决；当前证据支持几何改善，不能据此声称三维光学损耗或制造问题已经解决。')
para('三维策略 v3 方面，本轮两项新功能作用的位置不同：生成缓存改的是调度（结构性零候选目标不再被反复尝试，目标尝试 50→27、重复尝试 25→0），候选窗口余量改的是生成'
     '（把落在 0.1 mm 阈值边界上的窗口位置移开）。在同一 512 合成输入、同一初态、同一预算上限与同一验收规则下，'
     '两项同开的 D 组终态中心线近距对最低（%s 对），只开余量的 C 组额外长度最小（%s mm）；'
     '四组的预算上限都是 %s 次但实际评价次数是 %s/%s/%s/%s，运行时间又都是同机单次实测，'
     '所以只能称“相同预算上限”，不能称相同实际工作量，也不能由单次耗时得出普遍效率结论。'
     '余量把已记录的自检歧义候选 %s 条（%s 个生成任务）全部判为 CLEAR，这些任务的候选总数 %s → %s、层失败原因变化 %s 条；'
     '但自检歧义消除不等于目标近距对与完整邻线验收通过，也不等于全局未决对清零（四组终态未决对仍为 %s 对，阈值未放宽）。'
     '把同一余量加到历史固定重定位诊断上，新 E 第一次接受重定位：路线 %d 由层 %s 改到层 %s，'
     '全局近距对 %s → %s，终态由 %s 降到 %s（少 %d 对），代价是终态额外长度相对平面由 %s 增到 %s mm。'
     '这次接受只覆盖 1 个起点、1 份 %s 目标清单和 1 个余量取值；逐候选对应下，旧 %s 条重定位歧义候选只有 %s 条有唯一对应'
     '（%s 条通过基本评价、%s 条仍被拒；通过基本评价的候选中 %s 条通过完整验收、%s 条被完整验收拒绝，'
     '而通过验收不等于实际执行——两组合计只执行 %s 次修改：新 D %s 次、新 E %s 次，其中重定位 %s 次），'
     '其余 %s 条所在生成任务本轮没有执行，不能写成“%s 条全部解决”。'
     '以上全部指标仍是 0.1 mm 中心线近距对数，不代表损耗、串扰、无碰撞制造或工艺合规；'
     '512 是既有合成输入 %s，不是真实端口数据。'
     % (integer(GL['D_both_enabled']['final_collision_pair_count']),fmt(GL['C_window_slack_only']['final_extra_length_mm'],6),
        integer(GL['A_baseline_original']['candidate_budget']),
        integer(GL['A_baseline_original']['candidate_evaluations']),integer(GL['B_generation_cache_only']['candidate_evaluations']),
        integer(GL['C_window_slack_only']['candidate_evaluations']),integer(GL['D_both_enabled']['candidate_evaluations']),
        integer(PROBEJ['recorded_rows']),integer(PROBEJ['unique_tasks']),
        integer(PROBEJ['task_window_counts']['total_candidates_at_slack_zero']),
        integer(PROBEJ['task_window_counts']['total_candidates_at_probe_slack']),
        integer(len(PROBEJ['failure_shifts_on_recorded_tasks'])),unres,
        ENTRY['route_id'],integer(LAYER_BEFORE),integer(LAYER_AFTER),
        integer(ENTRY['global_pairs_before']),integer(ENTRY['global_pairs_after']),
        integer(OL['E']['final_collision_pair_count']),integer(DL['E']['final_collision_pair_count']),
        OL['E']['final_collision_pair_count']-DL['E']['final_collision_pair_count'],
        fmt(OL['E']['final_extra_length_vs_planar_mm'],4),fmt(DL['E']['final_extra_length_vs_planar_mm'],4),
        integer(len(CANDIAG['targets'])),integer(CORR_REL['old_self_ambiguous_rows']),integer(CORR_REL['matched']),
        integer((CORR_REL['old_to_new_basic_status'] or {}).get('REJECTED -> ACCEPTED_TARGET_PAIR_ONLY',0)),
        integer((CORR_REL['old_to_new_basic_status'] or {}).get('REJECTED -> REJECTED',0)),
        integer(CORR_REL['matched_to_full_acceptance']),integer(CORR_REL['matched_full_rejected']),
        integer(AEC['total']),integer(AEC['new_D']),integer(AEC['new_E']),integer(AEC['new_E_relocations']),
        integer(CORR_REL['unmatched'].get('TASK_NOT_REACHED_IN_NEW_RUN',0)),integer(CORR_REL['old_self_ambiguous_rows']),
        ABLDATA),'三维策略v3')
heading('图表和数据位置',level=2)
para('根目录为 C:\\Users\\lihao\\Desktop\\Graduation Project。2D表示OpticalWaveguideRouter2D，3D表示OpticalWaveguideRouter3D。',small=True)
para('二维复现图：2D/results/ 的fiberBoard256bend.png、fiberBoard512bend.png、loss_vs_radius.png、loss_distribution_R5.png。',small=True)
para('最差路线原图：3D/outputs/opt2d_step13/512/figures/worst_route_A.png与worst_route_F56.png。三维原图：3D/outputs/figures/。',small=True)
para('t31至t81为3D/publication/tables/下对应*_data.csv的短名；优化主对照直接读取outputs下保存的CSV，纠正部分旧摘要描述和字段陷阱。每个实验节末列出数据记录。',small=True)
para('三维策略v3 数据：3D/outputs/3d_strategy_v3/512_ablation/（A/B/C/D 四组的 ledger.json、curve.json、decisions.json、'
     'final_routes.json、summary.json、recheck.json，以及 cross_group_analysis.json、summary_all.json）；'
     'window_slack_probe/window_slack_probe.json；512_relocation_slack_diagnostic/（config.json、target_list.json、'
     'ledger_{D,E}.json、recheck_{D,E}.json、movement_stats.json、length_ledger.json、analysis.json、'
     'target_outcomes.csv、comparison_DE.csv、candidate_correspondence.json）。旧诊断对照取自 '
     '3D/outputs/3d_strategy_v2_rev2/512_de_diagnostic/ledger_{D,E}.json（只读，未改动）。',small=True)
para('三维策略v3 图：3D/outputs/3d_strategy_v3/figures/ 的 f1_group_pairs.png、f2_pairs_vs_evaluations.png、f3_costs.png、'
     'f4_diagnostic_comparison.png、f5_relocation_rejections.png、f6_route_geometry.png、f7_route34_relocation_before_after.png；'
     '本报告只引用其中已存在的 PNG，不重新绘图。七张共用图图内均不带编号，专题报告与本报告各自按全文顺序编号，两者编号可以不同；'
     '本报告的图号由全文顺序自增，每张图的“数据来源”行都写出源图文件名。',small=True)
para('表中“缺失”表示没有保存的数据，“不适用”表示指标在该条件下没有意义，0表示明确统计为零；不以0替代缺失。未完成的全板不生成损耗排名。损耗通常保留4位、时间与长度汇总2位小数；微小耗时和单线长度探针保留6位，印刷精度单独说明。',small=True)
para('平均和P95描述一次布局内各条路线的统计，不是多次随机运行的置信区间。报告包含41项原清单记录、清单之外已经执行的早期基线和交叉诊断，以及本轮三维策略v3 的三组新实验（512 四组功能消融、窗口余量探针、加余量固定重定位诊断）；纯计划、未执行策略不计作实验。本次整理没有重新运行路由，也没有重新绘图，新图全部引用 outputs/3d_strategy_v3/figures/ 下已存在的 PNG。',small=True)

inventory=csvread(P3/'publication/manifest/experiment_inventory.csv')
missing={r['experiment_id'] for r in inventory}-set(COVERAGE)
if missing: raise ValueError('Uncovered inventory experiments '+str(sorted(missing)))
doc.core_properties.title=NAME; doc.core_properties.author='李昊伦'
doc.core_properties.subject='已完成的二维复现 轨道和路径优化 交叉诊断 三维抬层实验'
# Set the East Asian face at every inheritance level, including table text and fields.
for style in doc.styles:
    fonts=style.element.get_or_add_rPr().get_or_add_rFonts()
    fonts.set(qn('w:eastAsia'),'宋体')
    fonts.attrib.pop(qn('w:eastAsiaTheme'),None)
defaults=doc.styles.element.find(qn('w:docDefaults'))
if defaults is not None:
    for fonts in defaults.iter(qn('w:rFonts')):
        fonts.set(qn('w:eastAsia'),'宋体')
        fonts.attrib.pop(qn('w:eastAsiaTheme'),None)
parts=[doc.part]
for section in doc.sections:
    parts.extend([section.header.part,section.footer.part])
for part in parts:
    for run in part.element.iter(qn('w:r')):
        fonts=run.get_or_add_rPr().get_or_add_rFonts()
        fonts.set(qn('w:eastAsia'),'宋体')
        fonts.attrib.pop(qn('w:eastAsiaTheme'),None)
doc.save(OUT/(NAME+'.docx'))
(OUT/'all_experiments_v3_figure_provenance.json').write_text(json.dumps(IMAGES,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'all_experiments_v3_coverage.json').write_text(json.dumps({'inventory_coverage':COVERAGE,
  'additional_sections':['早期输入与二维骨架验证','排序反转与硬约束负结果','局部单线恢复沙箱',
                         '三维策略v3 实验A：缓存与候选窗口余量的 512 四组功能消融',
                         '三维策略v3 实验B：窗口余量对 %s 条自检歧义候选的探针' % PROBEJ['recorded_rows'],
                         '三维策略v3 实验C：加余量的固定重定位诊断（新 D / 新 E）'],
  'tables':TABLES,'images':IMAGES},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'docx':str(OUT/(NAME+'.docx')),'images':len(IMAGES),'tables':len(TABLES),'inventory_covered':len(COVERAGE)},ensure_ascii=False))
