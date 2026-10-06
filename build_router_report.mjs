import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { Presentation, PresentationFile } from '@oai/artifact-tool';

const base='C:/Users/lihao/Desktop/Graduation Project';
const repo=path.join(base,'OpticalWaveguideRouter2D');
const skill='C:/Users/lihao/.codex/plugins/cache/openai-primary-runtime/presentations/26.921.10847/skills/presentations';
const out=path.join(base,'汇报材料');
const build=path.join(base,'.router_ppt_build');
await fs.mkdir(out,{recursive:true}); await fs.mkdir(build,{recursive:true});
const ppt=Presentation.create({slideSize:{width:1280,height:720}});
const C={navy:'#15334A',ink:'#1F2933',blue:'#226A91',light:'#EAF2F5',gray:'#667785',line:'#B9C8D0',white:'#FFFFFF',red:'#A3473E',green:'#336F61'};
const F='Microsoft YaHei';
function txt(s,value,x,y,w,h,size=24,color=C.ink,bold=false,align='left'){
  const a=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
  a.text=String(value);
  a.text.style={typeface:F,fontSize:size,color,bold,alignment:align,verticalAlignment:'middle',autoFit:'shrinkText',wrap:true};
  return a;
}
function line(s,x,y,w,color=C.line,h=2){s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill:color,line:{fill:'none',width:0}})}
function slide(title,num,source=''){
  const s=ppt.slides.add(); s.background.fill=C.white;
  txt(s,title,62,38,1150,66,34,C.navy,true); line(s,62,112,1155,C.blue,3);
  txt(s,`OpticalWaveguideRouter2D  ·  阶段汇报`,62,672,780,22,13,C.gray);
  txt(s,String(num).padStart(2,'0'),1160,671,54,22,13,C.gray,false,'right');
  if(source) s.speakerNotes.textFrame.setText(source);
  return s;
}
function bullet(s,items,x=78,y=147,w=1110,size=25,gap=78){items.forEach((v,i)=>{txt(s,'•',x,y+i*gap,24,42,size,C.blue,true);txt(s,v,x+34,y+i*gap,w-34,50,size,C.ink)})}
function table(s,values,x,y,w,h,colW){
 const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,values,columnWidths:colW});
 t.borders.assign({style:'solid',fill:C.line,width:1});
 for(let r=0;r<values.length;r++)for(let c=0;c<values[0].length;c++){
   const cell=t.getCell(r,c);cell.fill=r===0?C.light:C.white;
   cell.text.style={typeface:F,fontSize:r===0?19:18,color:r===0?C.navy:C.ink,bold:r===0,autoFit:'shrinkText'};
 }
 return t;
}
async function img(s,file,x,y,w,h){s.images.add({blob:new Uint8Array(await fs.readFile(path.join(repo,'results',file))),contentType:'image/png',alt:file,fit:'contain',position:{left:x,top:y,width:w,height:h}})}
function notes(s,body,sources){s.speakerNotes.textFrame.setText(body+'\n\n资料：'+sources.join('；'))}
const manuscript=[];
function record(n,title,body,sources){manuscript.push(`## 第${n}页｜${title}\n\n${body}\n\n**资料来源：** ${sources.join('；')}\n`)}

// 1
{
 const s=ppt.slides.add();s.background.fill=C.white;line(s,62,78,1120,C.blue,5);
 txt(s,'OpticalWaveguideRouter2D：\n旧版 AutoRouter 精确复刻与损耗模型复现',65,125,1110,210,45,C.navy,true);
 txt(s,'面向 3D 光波导智能排布毕设的 2D Baseline 构建',68,375,1100,62,27,C.blue);
 line(s,68,489,540,C.line,2);txt(s,'李昊伦   |   导师：Prof. Lin Ma',68,515,950,46,23,C.ink);
 txt(s,'阶段成果汇报  ·  2026 年 9 月',68,612,900,34,17,C.gray);
 const b='本次汇报说明两个成果：旧版 AutoRouter 的 Python 3.10 行为级精确复刻，以及依据黄志杰论文重建的损耗评价模型。复刻版本用于后续 3D Router 的二维基线。';
 notes(s,b,['项目 README.md','黄志杰_毕设论文.pdf']);record(1,'封面',b,['README.md','黄志杰论文']);
}
//2
{
 const s=slide('背景与动机',2);
 txt(s,'黄志杰毕设',78,157,290,40,29,C.blue,true);txt(s,'2D 光波导智能排布算法及 AutoRouter 工程实现',78,215,1110,54,27);
 txt(s,'当前毕设',78,318,290,40,29,C.blue,true);txt(s,'面向 3D、多层与更高通道数的光波导路由',78,376,1110,54,27);
 line(s,78,498,1110,C.line,2);txt(s,'需要可复现、可验证、可对比的 2D baseline',78,526,1110,78,31,C.navy,true);
 const b='旧版 AutoRouter 是论文中的二维路由算法工程实现。为了评价新的三维算法，需要先固定二维参考行为与评价口径。这里的工作重点是复现原始程序真实输出，并能解释每个损耗分量的来历。';notes(s,b,['docs/migration_report.md §1','黄志杰论文']);record(2,'背景与动机',b,['migration_report.md','黄志杰论文']);
}
//3
{
 const s=slide('原始程序的工程问题',3);
 bullet(s,['Python 3.8 的 AutoRouter.exe 与反编译源码','反编译控制流存在缩进、条件链与 return 错位','原仓库 README 仅声明通过语法检查，行为未验证','缺少完整工程、真实数据验证与系统损耗分析','因此无法直接承担 3D Router 的对照基线'],78,153,1100,24,86);
 const b='原始来源是 Python 3.8 可执行文件及反编译代码。旧 README 明确提示仅通过 syntax check，行为未与原程序核验。主要风险不是语言版本本身，而是反编译后的控制流可能改变算法结果。';notes(s,b,['GitHub 原始 README','docs/migration_report.md §1、§4']);record(3,'原始程序的工程问题',b,['原始 GitHub README','migration_report.md']);
}
//4
{
 const s=slide('复刻范围与处理链',4);
 txt(s,'Python 3.10.11  ·  保留旧算法行为',78,149,1100,50,27,C.blue,true);
 const steps=[['Port1 / Port2\nExcel','data/fiberBoard256/512.xlsx'],['端口放置','create_sim_space'],['直角布线','plotter_rect'],['弯曲生成','plotter_bend'],['GDS / PNG / Excel','svg2gds_bend'],['长度 / 交叉 / 损耗','analyze_loss']];
 steps.forEach((v,i)=>{const x=76+i*198;txt(s,v[0],x,278,169,85,22,C.navy,true,'center');line(s,x,379,169,C.blue,3);txt(s,v[1],x,398,169,88,16,C.gray,false,'center');if(i<5)txt(s,'›',x+175,301,22,40,31,C.blue,true,'center')});
 txt(s,'GUI、CLI、测试和 exact fidelity gate 覆盖整条链路',78,552,1110,58,24,C.ink);
 const b='输入是 256 或 512 通道工作簿中的 Port1、Port2。流程依次完成端口放置、直角布线、圆弧弯曲、GDS 与图像及 Excel 输出，最后计算长度、交叉与估计损耗。工程同时保留 GUI 和 CLI，并增加测试与验证工具。';notes(s,b,['README.md','docs/migration_report.md','tools/exact_fidelity_gate.py','tools/analyze_loss.py']);record(4,'复刻范围与处理链',b,['README.md','migration_report.md','exact_fidelity_gate.py','analyze_loss.py']);
}
//5
{
 const s=slide('Exact Legacy Fidelity：三层证据',5);
 const vals=[['证据层','验证对象','结果'],['原始 bytecode','控制流、分支与 return','逐处还原'],['Python 3.8 runtime','原版代码对象真实执行','作为 ground truth'],['Python 3.10 复刻版','逐阶段数据与 GDS 几何','512/512 exact']];table(s,vals,70,151,1135,235,[295,510,330]);
 txt(s,'create_sim_space   512/512',81,425,500,45,24,C.navy,true);txt(s,'plotter_rect   512/512',661,425,500,45,24,C.navy,true);
 txt(s,'plotter_bend   512/512',81,495,500,45,24,C.navy,true);txt(s,'GDS geometry   512/512',661,495,500,45,24,C.navy,true);
 txt(s,'GDS 文件仅 8 字节时间戳不同（BGNLIB / BGNSTR）',81,576,1110,45,20,C.gray);
 const b='验证不依赖肉眼相似。先从原版字节码判定控制流，再用 Python 3.8.10 和当年依赖执行原版代码对象，然后同 Python 3.10 复刻结果逐阶段比较。512 条路由的端口、轨道、弯曲参数及 GDS 点列和线宽一致。GDS 文件本体只有 8 字节时间戳差异。';notes(s,b,['docs/exact_legacy_fidelity_report.md Summary','tools/exact_fidelity_gate.py']);record(5,'Exact Legacy Fidelity：三层证据',b,['exact_legacy_fidelity_report.md','exact_fidelity_gate.py']);
}
//6
{
 const s=slide('关键反编译错误修复',6);
 const vals=[['位置','反编译产物','复原依据'],['find_next / coarse_sort','return 缩进；if/elif 误解','Python 3.8 bytecode'],['四个布线函数','iter / inflection 缩进','跳转目标与 runtime'],['noCross / dir_norm','条件链；return 错位','指令级控制流'],['theta / Excel','过滤条件；NumPy repr 不兼容','字节码与输出解析'],['calc_crossing','DEBUG 缩进吞掉正常路径','bytecode + 交叉统计']];table(s,vals,66,152,1145,400,[260,545,340]);
 txt(s,'修复 decompiler artifact，保持原版算法决策',75,584,1100,50,25,C.blue,true);
 const b='这些修复的原则是恢复原程序的语义，而不是调整路由策略。比如 find_next 的 return 位置和 noCross 的布尔条件链，都由字节码中的跳转与原版 runtime 对照确认。NumPy 2 的 repr 变化属于输出兼容问题，避免 Excel 回读失败。';notes(s,b,['docs/migration_report.md §4','docs/loss_model_reconstruction_report.md §6']);record(6,'关键反编译错误修复',b,['migration_report.md','loss_model_reconstruction_report.md']);
}
//7
{
 const s=slide('2020 PDF 与原 EXE 的版本差异',7);
 txt(s,'266 / 512',92,173,500,105,58,C.red,true);txt(s,'对历史 fiberBoard512_rect.pdf',620,188,530,80,27,C.ink);
 line(s,90,300,1100,C.line,2);
 txt(s,'512 / 512',92,351,500,105,58,C.green,true);txt(s,'对原版 Python 3.8 runtime',620,366,530,80,27,C.ink);
 txt(s,'差异定位：below→below 的 MTbelow / noCross 分支；其后 173 条 above→below 路由整体受影响',90,530,1100,78,22,C.navy);
 const b='最初把 2020 年生成的 PDF 当成基准，只得到 266/512 exact。排查首个分歧后，发现它来自另一个 AutoRouter build。通过运行当前 EXE 中提取的原始代码对象，复刻版达到 512/512 exact。因此本项目以原版可执行程序的运行行为作为 ground truth，历史 PDF 仅用于说明版本差异。';notes(s,b,['docs/debug_first_divergence.md','docs/exact_legacy_fidelity_report.md']);record(7,'2020 PDF 与原 EXE 的版本差异',b,['debug_first_divergence.md','exact_legacy_fidelity_report.md']);
}
//8
{
 const s=slide('仓库发布与可复现工程',8);
 txt(s,'v1.0-legacy-exact',78,158,720,58,34,C.blue,true);
 txt(s,'main commit  c1da72ba334a81eff9a610529fa331335ae044f8',78,233,1110,48,19,C.ink);
 bullet(s,['正式工程包含 data / docs / tools / tests 与 GUI、CLI','提交历史保留旧反编译源码，可追溯修复前状态','发布排除 .venv、_legacy_runtime 与生成的 results 文件','损耗模型 v1.1 的本地结果另行标注'],80,319,1100,23,69);
 const b='GitHub 的 c1da72b 提交把反编译原型替换为 Python 3.10 正式工程，v1.0-legacy-exact 标签可作为路由基线。旧代码仍可从 Git 历史追溯。环境和生成结果没有纳入该提交，数据、报告、验证工具与测试已纳入。损耗模型的本地后续工作应与该发布状态区分。';notes(s,b,['GitHub commit c1da72b','GitHub tag v1.0-legacy-exact','README.md']);record(8,'仓库发布与可复现工程',b,['GitHub commit c1da72b','GitHub tag v1.0-legacy-exact','README.md']);
}
//9
{
 const s=slide('论文 3.3.2 节的损耗模型',9);
 txt(s,'Lₜ = 2Lᵦ + L₀·lₛ + ΣL𝚌',82,175,1090,112,51,C.navy,true,'center');
 table(s,[['分量','含义','来源'],['2Lᵦ','两段弯曲损耗','表 3-1 + 式 3-18'],['L₀·lₛ','直波导传播损耗','L₀ = 0.05 dB/cm'],['ΣL𝚌','逐交叉角度插入损耗','图 3-12 近似表']],82,341,1100,235,[270,440,390]);
 txt(s,'当前是论文级估计损耗复现，不是物理实验验证',82,602,1100,39,20,C.red);
 const b='论文式 3-19 将每根波导损耗分为对称的两段弯曲、直线传播与所有交叉插入损耗。直波导系数 0.05 dB/cm 来自论文表 2-1。弯曲项从论文表 3-1 与原版内部数据恢复，交叉项因原始表缺失只能采用图 3-12 的近似数字化。';notes(s,b,['黄志杰论文 §3.3.2、表 2-1、表 3-1、图 3-12','docs/loss_model_reconstruction_report.md']);record(9,'论文 3.3.2 节的损耗模型',b,['黄志杰论文','loss_model_reconstruction_report.md']);
}
//10
{
 const s=slide('弯曲损耗：由原版 tl / ll 恢复',10);
 table(s,[['半径 R','论文 90° 弯曲损耗'],['2 mm','7.94 dB'],['3 mm','6.81 dB'],['4 mm','4.59 dB'],['5 mm','2.39 dB'],['6 mm','1.90 dB']],80,151,500,435,[240,260]);
 txt(s,'原版内部：弯曲密度 = |tl / ll|',636,196,570,55,26,C.navy,true);
 txt(s,'Lᵦ = Σ(θ₁ − θ₀) · R · density',636,284,570,76,31,C.blue,true);
 txt(s,'= L₉₀ · θ / 90°',636,381,570,61,29,C.blue,true);
 txt(s,'R = 5 mm 时，内部精度对应 2.3826 dB；论文表为 2.39 dB',636,501,570,88,20,C.gray);
 const b='论文表 3-1 的五个半径值可以由原版程序硬编码的 tl 和 ll 两表求出损耗密度，再乘 90 度弧长得到。原版计算使用未四舍五入的密度，故 R=5 时内部值约 2.3826 dB，论文印刷为 2.39 dB。小于 90 度时按照角度线性折算，与原版按弧长累积完全等价。';notes(s,b,['黄志杰论文表 3-1、式 3-18','docs/loss_model_reconstruction_report.md §4']);record(10,'弯曲损耗：由原版 tl / ll 恢复',b,['黄志杰论文','loss_model_reconstruction_report.md']);
}
//11
{
 const s=slide('交叉损耗：近似数据与边界',11);
 bullet(s,['原始 crossing loss 工作簿未在 EXE、PYZ 或本地文件中找到','图 3-12 的 30 次交叉曲线数字化为逐角度表','用论文“90°、30 次交叉约 0.05 dB”作量级锚定','逐次交叉损耗按对应角度表值 / 30 计算'],76,150,1110,23,89);
 line(s,77,540,1110,C.line,2);txt(s,'Legacy Loss Model：PARTIAL',77,572,1110,60,31,C.red,true);
 const b='原版 calc_loss 会读取一张 crossing loss 表，但它没有随 EXE 或 PYZ 发布。本项目把论文图 3-12 的 30 次交叉曲线数字化为角度表，再用论文给出的 90 度、30 次交叉约 0.05 dB 进行锚定。这个表只有趋势与论文级近似的意义，不能称为原始模型完整复原，因此状态明确写 PARTIAL。';notes(s,b,['docs/loss_model_reconstruction_report.md §6、§14','data/crossing_loss_from_thesis_fig3_12.csv','黄志杰论文图 3-12']);record(11,'交叉损耗：近似数据与边界',b,['loss_model_reconstruction_report.md','crossing_loss_from_thesis_fig3_12.csv','黄志杰论文']);
}
//12
{
 const s=slide('论文关键结果复现',12);
 table(s,[['场景','论文 mean / max','复现 mean / max','最大相对误差'],['256 · R5','5.3 / 6.4 dB','5.2788 / 6.3330 dB','1.05%'],['512 · R5','5.5 / 6.6 dB','5.5147 / 6.5761 dB','0.36%'],['512 · R4','9.8 / 11.0 dB','9.8096 / 10.9815 dB','0.17%']],70,155,1138,326,[220,300,390,228]);
 txt(s,'三组 mean / max 均落在论文一位小数的印刷精度内',75,522,1100,53,27,C.blue,true);
 txt(s,'未按目标数值调参；crossing 项使用图 3-12 近似表',75,585,1100,43,20,C.gray);
 const b='对 256 R5、512 R5 和 512 R4 三个论文明确给数值的场景，复现平均值和最大值均在一位小数印刷精度内。六个比较值中的最大相对误差为 1.05%，来自 256 R5 的最大损耗。这里没有针对目标结果调参，但交叉表仍是数字化近似，故只称论文级损耗结果复现。';notes(s,b,['results/fiberBoard256_loss_summary.json','results/fiberBoard512_loss_summary.json','results/fiberBoard512_loss_R4_summary.json','docs/loss_model_reconstruction_report.md §10–12']);record(12,'论文关键结果复现',b,['三个 loss summary JSON','loss_model_reconstruction_report.md']);
}
//13
{
 const s=slide('512 通道 R5：损耗贡献与趋势',13);
 txt(s,'弯曲 4.5587 dB · 82.7%    直线 0.6355 dB · 11.5%    交叉 0.3205 dB · 5.8%',69,135,1140,46,22,C.navy,true);
 await img(s,'loss_distribution_R5.png',62,207,565,200);await img(s,'loss_vs_length_R5.png',651,207,565,200);
 await img(s,'loss_vs_crossings_R5.png',62,422,565,200);await img(s,'loss_vs_radius.png',651,422,565,200);
 const b='这四张图直接来自 results。512 R5 的逐路由平均损耗为 5.5147 dB，其中弯曲占 82.7%，直线占 11.5%，交叉占 5.8%。从损耗分布、与长度和交叉数的关系，以及不同半径扫描可看到弯曲半径是主要因素。这与论文第四章的趋势一致，但图中数值是模型估计而非测量。';notes(s,b,['results/fiberBoard512_loss_summary.json','results/loss_distribution_R5.png','results/loss_vs_length_R5.png','results/loss_vs_crossings_R5.png','results/loss_vs_radius.png']);record(13,'512 通道 R5：损耗贡献与趋势',b,['fiberBoard512_loss_summary.json','results 中四张 loss 图']);
}
//14
{
 const s=slide('当前成果的两个版本',14);
 txt(s,'v1.0-legacy-exact',81,162,520,54,33,C.blue,true);txt(s,'路由 / 弯曲 / GDS 几何 512/512 exact',81,235,1070,51,27,C.ink);
 line(s,80,315,1100,C.line,2);
 txt(s,'v1.1-loss-model',81,355,520,54,33,C.blue,true);txt(s,'论文级损耗评价模型复现；交叉表缺失，状态 PARTIAL',81,428,1090,58,26,C.ink);
 line(s,80,529,1100,C.line,2);txt(s,'当前 2D baseline 已具备 3D Router 对比所需的路由与评价口径',81,556,1100,75,25,C.navy,true);
 const b='两个版本承担不同作用。v1.0 固定原版 2D 算法的路由和 GDS 行为，属于 exact baseline。v1.1 增加论文损耗评价口径，在直线和弯曲部分有明确来源，交叉部分受原表缺失限制，因此标记 PARTIAL。后续 3D 算法可用同一组输入与指标对照。';notes(s,b,['README.md','docs/exact_legacy_fidelity_report.md','docs/loss_model_reconstruction_report.md §14']);record(14,'当前成果的两个版本',b,['README.md','exact_legacy_fidelity_report.md','loss_model_reconstruction_report.md']);
}
//15
{
 const s=slide('下一阶段：OpticalWaveguideRouter3D',15);
 txt(s,'三维路由能力',80,149,500,41,28,C.blue,true);
 bullet(s,['x / y / z 路由与多层波导','最小间距、弯曲半径与冲突检测','rip-up and reroute，目标规模 512 / 1024 通道'],81,207,1100,22,64);
 line(s,80,417,1100,C.line,2);txt(s,'与 2D baseline 的对比指标',80,441,1010,41,27,C.blue,true);
 txt(s,'布通率  ·  总长度  ·  最大/平均损耗  ·  损耗均衡性',80,504,1110,45,23,C.ink);
 txt(s,'交叉/冲突数量  ·  GDS 与可视化输出',80,565,1110,45,23,C.ink);
 const b='下一阶段进入 OpticalWaveguideRouter3D，处理空间坐标、多层、几何约束和冲突后的 rip-up and reroute。先在 512 通道上与二维基线对照，再扩展至 1024 通道。比较指标包括布通率、总长度、平均与最大估计损耗、均衡性、交叉或冲突数量，以及输出几何和可视化。2D 项目保持冻结参考实现。';notes(s,b,['README.md Scope','本阶段 3D 毕设目标']);record(15,'下一阶段：OpticalWaveguideRouter3D',b,['README.md','毕设目标']);
}

const md='# OpticalWaveguideRouter2D 阶段汇报讲稿\n\n> 对应 15 页 PPT。所有损耗均为论文级估计模型结果，不代表物理实验验证。\n\n'+manuscript.join('\n');
await fs.writeFile(path.join(out,'OpticalWaveguideRouter2D_汇报讲稿.md'),md,'utf8');
const candidate=path.join(build,'candidate.pptx');
await (await PresentationFile.exportPptx(ppt)).save(candidate);
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const final=path.join(out,'OpticalWaveguideRouter2D_阶段成果汇报.pptx');
const result=await finalizePresentation({workspaceDir:base,candidatePath:candidate,finalPath:final,pythonExecutable:'C:/Users/lihao/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe',integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit','--require-native-table-slide','5','--require-native-table-slide','6','--require-native-table-slide','9','--require-native-table-slide','10','--require-native-table-slide','12'],explicitTotalSlideCount:15,requiredNativeTableOwnerSlides:[5,6,9,10,12],fontPolicy:{basis:'design',families:[F]},verifyArtifactToolImport:true,receiptPath:path.join(build,'validation.json')});
console.log(JSON.stringify({final,md:path.join(out,'OpticalWaveguideRouter2D_汇报讲稿.md'),result},null,2));
