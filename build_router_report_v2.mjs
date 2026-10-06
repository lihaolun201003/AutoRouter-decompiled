import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {FileBlob,PresentationFile} from '@oai/artifact-tool';

const base='C:/Users/lihao/Desktop/Graduation Project';
const repo=path.join(base,'OpticalWaveguideRouter2D');
const template=path.join(base,'Linsgroup_PPT.pptx');
const out=path.join(base,'汇报材料');
const build=path.join(base,'.router_ppt_build');
const skill='C:/Users/lihao/.codex/plugins/cache/openai-primary-runtime/presentations/26.921.10847/skills/presentations';
await fs.mkdir(out,{recursive:true});await fs.mkdir(build,{recursive:true});
const p=await PresentationFile.importPptx(await FileBlob.load(template));
const coverLayout=p.slides.getItem(0).useLayoutId;
const bodyLayout=p.slides.getItem(8).useLayoutId;
for(const old of [...p.slides.items])old.delete();
const blue='#0B4DA2',ink='#1F2933',gray='#536170',red='#AD4040',green='#286B5A',light='#E8F0F8',font='Microsoft YaHei';
function addText(s,t,x,y,w,h,size=26,color=ink,bold=false,align='left'){
 const sh=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 sh.text=String(t);sh.text.style={typeface:font,fontSize:size,color,bold,alignment:align,verticalAlignment:'middle',wrap:true,autoFit:'shrinkText'};return sh;
}
function shape(s,x,y,w,h,fill){s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill,line:{fill:'none',width:0}})}
function body(title,stage){const s=p.slides.add({layoutId:bodyLayout});addText(s,title,150,16,1030,51,30,'#FFFFFF',true);addText(s,stage,63,105,560,36,18,blue,true);return s}
function bullets(s,a,x=92,y=185,w=1080,size=27,gap=94){a.forEach((t,i)=>{addText(s,'•',x,y+i*gap,28,42,size,blue,true);addText(s,t,x+38,y+i*gap,w-38,62,size,ink)})}
function table(s,values,x,y,w,h,widths){const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,values,columnWidths:widths});t.borders.assign({style:'solid',fill:'#9BB4CB',width:1});for(let r=0;r<values.length;r++)for(let c=0;c<values[0].length;c++){let z=t.getCell(r,c);z.fill=r===0?light:'#FFFFFF';z.text.style={typeface:font,fontSize:r===0?22:21,color:r===0?blue:ink,bold:r===0,autoFit:'shrinkText'}}return t}
async function image(s,file,x,y,w,h,root=repo,crop){s.images.add({blob:new Uint8Array(await fs.readFile(path.join(root,file))),contentType:'image/png',alt:path.basename(file),fit:'contain',position:{left:x,top:y,width:w,height:h},...(crop?{crop}:{})})}
function note(s,t,sources){s.speakerNotes.textFrame.setText(t+'\n\n资料来源：'+sources.join('；'))}
const speech=[];function rec(n,t,body,sources){speech.push(`## 第 ${n} 页：${t}\n\n${body}\n\n**资料来源：** ${sources.join('；')}\n`)}

// 1 封面
{
 const s=p.slides.add({layoutId:coverLayout});
 addText(s,'OpticalWaveguideRouter2D',144,202,992,70,46,blue,true,'center');
 addText(s,'旧版 AutoRouter 解码、精确复现与论文损耗对比',138,293,1004,96,36,blue,true,'center');
 addText(s,'李昊伦    导师：Prof. Lin Ma',255,461,770,56,25,blue,false,'center');
 const b='这次汇报只讲三步。第一步，从旧 AutoRouter.exe 解出程序。第二步，在 Python 3.10 中复现并证明路由结果与原版一致。第三步，展示生成的波导图，把估计损耗与黄志杰论文中的数字对比。';note(s,b,['README.md','docs/migration_report.md']);rec(1,'封面',b,['README.md','migration_report.md']);
}
// 2 总览
{
 const s=body('这次汇报的三步','汇报路线');
 const steps=[['01','解码','从 AutoRouter.exe 找回程序'],['02','复现','让 Python 3.10 跑出同样的路由'],['03','对比','展示波导图与论文损耗数据']];
 steps.forEach((v,i)=>{const x=95+i*380;addText(s,v[0],x,205,100,65,48,blue,true);addText(s,v[1],x,292,260,57,35,blue,true);addText(s,v[2],x,367,300,112,25,ink);if(i<2)addText(s,'›',x+310,280,60,86,53,blue,true,'center')});
 const b='整项工作按三步展开：先从可执行程序找回代码，再把它迁移到 Python 3.10，并和旧程序逐条比较，最后展示真实生成的波导图，以及论文级损耗模型复现结果。';note(s,b,['README.md','docs/exact_legacy_fidelity_report.md','docs/loss_model_reconstruction_report.md']);rec(2,'三步总览',b,['README.md','exact_legacy_fidelity_report.md','loss_model_reconstruction_report.md']);
}
// 3 解码原因
{
 const s=body('为什么需要解码旧程序','第一步：解码');
 bullets(s,['论文给出了算法思路，旧 AutoRouter.exe 保存着实际实现','原来的反编译代码只能通过语法检查，运行行为未验证','要做 3D Router，需要先有可信的 2D 对照程序'],95,181,1090,28,112);
 const b='黄志杰论文解释了二维光波导排布的思路，但真正执行的细节在旧 AutoRouter 程序里。原 GitHub 的反编译源码说明仅通过语法检查，尚未验证运行行为。为了建立可靠的二维基线，需要回到 EXE 中确认程序实际怎么运行。';note(s,b,['GitHub 原始 README','docs/migration_report.md §1']);rec(3,'为什么解码',b,['原始 GitHub README','migration_report.md']);
}
// 4 screenshot
{
 const s=body('用 PyInstaller Extractor 解出程序文件','第一步：解码');
 await image(s,'codex-clipboard-b173ba03-80ec-41f2-bac9-10e089bd3b97.png',62,157,790,460,'C:/Users/lihao/AppData/Local/Temp');
 addText(s,'AutoRouter.exe',875,216,305,53,29,blue,true);
 addText(s,'提取打包内容',875,301,305,54,27,ink);
 addText(s,'得到 Python 字节码',875,376,305,70,27,ink);
 addText(s,'再反编译、核对控制流',875,477,305,88,24,ink);
 const b='这里展示的是 PyInstaller Extractor 的项目页面截图。我们用它从 AutoRouter.exe 提取打包内容，得到 Python 字节码，再把字节码还原为可读代码。反编译结果不能直接当作正确源码，所以后面还要用原程序运行行为核对。';note(s,b,['用户提供的 PyInstaller Extractor 截图','docs/migration_report.md §1、§4']);rec(4,'解码工具',b,['用户提供截图','migration_report.md']);
}
//5 decoded files
{
 const s=body('解码后找回了什么','第一步：解码');
 table(s,[['程序部分','作用'],['problem_graph','读取 Excel，安排端口位置'],['wiring_rect_826','选择布线轨道'],['wiring_bend_826','把直角转为圆弧并输出 GDS'],['waveguide_calculator','计算长度、交叉与损耗']],89,165,1085,368,[400,685]);
 addText(s,'修复的是反编译造成的错误，算法决策仍以原版为准',91,560,1080,58,25,blue,true);
 const b='解码后可以看到四块主要逻辑：端口放置、直角布线、圆弧生成与损耗计算。反编译有时会把缩进和判断还原错，我们对照字节码与原版运行结果修正这些错误。目标是恢复旧程序本来的算法，而不是重新发明一个算法。';note(s,b,['docs/migration_report.md §1、§4']);rec(5,'解码结果',b,['migration_report.md']);
}
//6 pipeline
{
 const s=body('在 Python 3.10 中重新跑通完整流程','第二步：复现');
 const a=[['Excel 输入','256 / 512 通道'],['端口放置','起点与终点'],['波导布线','直线与弯曲'],['结果输出','GDS、图片、表格']];
 a.forEach((v,i)=>{let x=86+i*296;addText(s,v[0],x,243,260,56,31,blue,true,'center');shape(s,x+25,323,210,3,blue);addText(s,v[1],x,349,260,80,25,ink,false,'center');if(i<3)addText(s,'›',x+257,264,40,60,43,blue,true)});
 addText(s,'使用项目 data/fiberBoard256.xlsx 与 fiberBoard512.xlsx 作为真实输入',90,525,1100,69,23,gray);
 const b='复现版用 Python 3.10.11，直接读取项目中的 256 和 512 通道输入表。流程是端口放置、波导布线、圆弧生成，最后输出 GDS、图片和 Excel。这个流程也保留了 GUI 和命令行入口。';note(s,b,['README.md','docs/migration_report.md','data/fiberBoard256.xlsx','data/fiberBoard512.xlsx']);rec(6,'复现流程',b,['README.md','migration_report.md','两张输入 Excel']);
}
//7 exact
{
 const s=body('怎么证明复现结果一样','第二步：复现');
 table(s,[['比较位置','与原版 Python 3.8 程序对比'],['端口位置','512 / 512 一致'],['直角布线','512 / 512 一致'],['圆弧参数','512 / 512 一致'],['GDS 波导几何','512 / 512 一致']],80,158,1120,367,[390,730]);
 addText(s,'逐条对比数据与几何，不靠肉眼看图',84,560,1110,62,28,blue,true);
 const b='我们把原版字节码放回它原来的 Python 3.8 环境实际运行，再与 Python 3.10 复现版逐条对比。512 根波导的端口、布线轨道、弯曲参数和 GDS 路径全部一致。GDS 文件只有自身记录的时间戳不同。';note(s,b,['docs/exact_legacy_fidelity_report.md','tools/exact_fidelity_gate.py']);rec(7,'精确复现证据',b,['exact_legacy_fidelity_report.md','exact_fidelity_gate.py']);
}
//8 pdf issue
{
 const s=body('为什么曾经只对上 266 根','第二步：复现');
 addText(s,'266 / 512',95,200,420,100,59,red,true);addText(s,'与 2020 年保存的 PDF 图对比',585,212,560,80,28,ink);
 shape(s,93,331,1080,2,'#AFC4D8');
 addText(s,'512 / 512',95,370,420,100,59,green,true);addText(s,'与原版 EXE 实际运行结果对比',585,383,560,80,28,ink);
 addText(s,'结论：历史 PDF 来自另一版程序；以原版 EXE 的实际运行结果为准',94,536,1090,75,25,blue,true);
 const b='一开始用旧文件夹里的 2020 年 PDF 图比较，只对上 266 根。继续追踪后发现，该图来自另一版 AutoRouter。用本次解码的 EXE 在原 Python 3.8 环境实际运行，复现版 512 根全部一致。因此选原 EXE 的运行结果作为基准。';note(s,b,['docs/debug_first_divergence.md','docs/exact_legacy_fidelity_report.md']);rec(8,'历史 PDF 差异',b,['debug_first_divergence.md','exact_legacy_fidelity_report.md']);
}
//9 waveguide 256
{
 const s=body('256 通道波导图','第三步：波导图与论文对比');
 await image(s,'results/fiberBoard256bend.png',202,145,850,490,repo,{left:0.13,top:0.065,right:0.13,bottom:0});
 const b='这是复现版使用 fiberBoard256.xlsx 输入后直接生成的 256 通道弯曲波导图。横纵坐标单位为毫米，红色曲线是实际布线路径。这里展示的是程序输出，不是重新画的示意图。';note(s,b,['results/fiberBoard256bend.png','data/fiberBoard256.xlsx']);rec(9,'256 通道波导图',b,['fiberBoard256bend.png','fiberBoard256.xlsx']);
}
//10 waveguide 512
{
 const s=body('512 通道波导图','第三步：波导图与论文对比');
 await image(s,'results/fiberBoard512bend.png',202,145,850,490,repo,{left:0.13,top:0.065,right:0.13,bottom:0});
 const b='这张是与用户给出的参考图同样样式的项目实际输出。512 根波导在 150 毫米见方的布线区域里完成排布，图中可看出波导密度高于 256 通道。后面损耗对比的 512 R5 场景就基于这组路由结果。';note(s,b,['results/fiberBoard512bend.png','data/fiberBoard512.xlsx','用户提供的波导图参考']);rec(10,'512 通道波导图',b,['fiberBoard512bend.png','fiberBoard512.xlsx']);
}
//11 loss simple
{
 const s=body('损耗怎么算','第三步：波导图与论文对比');
 addText(s,'总损耗 = 弯曲损耗 + 直线损耗 + 交叉损耗',78,165,1110,76,37,blue,true,'center');
 bullets(s,['直线：论文给出 0.05 dB/cm','弯曲：论文表 3-1 给出不同半径的 90° 损耗','交叉：原始数据表缺失，按论文图 3-12 估算'],95,300,1090,27,91);
 addText(s,'交叉损耗因此标记 PARTIAL；这里比较的是估计模型，不是实测',92,596,1080,46,22,red,true);
 const b='论文把总损耗分成弯曲、直线和交叉三项。直线损耗的系数是 0.05 dB/cm。弯曲损耗按论文表 3-1 的半径数据计算。交叉损耗所需的原始表没有找到，所以从论文图 3-12 数字化估算；整个损耗模型状态写 PARTIAL。';note(s,b,['黄志杰论文 §3.3.2、表 2-1、表 3-1、图 3-12','docs/loss_model_reconstruction_report.md']);rec(11,'损耗计算',b,['黄志杰论文','loss_model_reconstruction_report.md']);
}
//12 thesis comparison
{
 const s=body('与论文数值对比','第三步：波导图与论文对比');
 table(s,[['场景','论文 平均 / 最大','复现 平均 / 最大'],['256 通道，R=5 mm','5.3 / 6.4 dB','5.2788 / 6.3330 dB'],['512 通道，R=5 mm','5.5 / 6.6 dB','5.5147 / 6.5761 dB'],['512 通道，R=4 mm','9.8 / 11.0 dB','9.8096 / 10.9815 dB']],70,180,1140,300,[305,400,435]);
 addText(s,'全部落在论文一位小数的印刷精度内',82,528,1090,55,29,blue,true);
 addText(s,'最大相对误差 1.05%；没有针对目标数值调参',82,590,1090,40,21,gray);
 const b='把论文中明确报告的三组场景拿出来，比较平均损耗与最大损耗。256 R5、512 R5、512 R4 的复现值都能四舍五入到论文所印的一位小数。六个比较值中最大相对误差是 1.05%。这支持论文级损耗数值复现，但交叉部分仍是近似。';note(s,b,['results/fiberBoard256_loss_summary.json','results/fiberBoard512_loss_summary.json','results/fiberBoard512_loss_R4_summary.json','docs/loss_model_reconstruction_report.md']);rec(12,'与论文数值对比',b,['三个 loss summary JSON','loss_model_reconstruction_report.md']);
}
//13 contribution
{
 const s=body('损耗主要来自弯曲','第三步：波导图与论文对比');
 addText(s,'512 通道、R=5 mm',73,144,440,48,25,blue,true);
 await image(s,'results/loss_distribution_R5.png',72,210,552,310);
 await image(s,'results/loss_vs_radius.png',650,210,552,310);
 addText(s,'弯曲 82.7%   直线 11.5%   交叉 5.8%',72,556,1120,54,29,blue,true,'center');
 const b='这两张图直接来自 results。以 512 通道、5 毫米半径为例，平均弯曲损耗为 4.5587 dB，占总平均损耗的 82.7%；直线占 11.5%，交叉占 5.8%。半径扫描图也显示更小的弯曲半径会显著增加损耗。这里仍是论文模型估计结果。';note(s,b,['results/fiberBoard512_loss_summary.json','results/loss_distribution_R5.png','results/loss_vs_radius.png']);rec(13,'损耗贡献',b,['fiberBoard512_loss_summary.json','两张 results 损耗图']);
}
//14 next
{
 const s=body('这项工作对 3D 毕设的作用','总结');
 bullets(s,['二维路由：已与原版逐条精确对齐，可作为基线','损耗评价：论文数值已复现，交叉项保留 PARTIAL 标注','下一步在 3D 中加入多层、间距和冲突处理','用相同输入与指标，对比 2D 与 3D 的路线和损耗'],91,177,1095,27,100);
 const b='现在我们有一个可靠的二维路由基线，也有一套来源明确的论文级损耗评价口径。下一步进入三维路由，处理多层、最小间距和冲突后的重布线，再用布通率、长度、损耗和冲突数量与二维结果对比。交叉损耗的原始表缺失会继续清楚标注。';note(s,b,['README.md','docs/exact_legacy_fidelity_report.md','docs/loss_model_reconstruction_report.md']);rec(14,'总结与 3D 下一步',b,['README.md','exact_legacy_fidelity_report.md','loss_model_reconstruction_report.md']);
}

const md='# OpticalWaveguideRouter2D 汇报讲稿（三步版）\n\n按“解码、复现、波导图与论文对比”讲述。损耗数字为论文级估计模型结果，并非物理实验。\n\n'+speech.join('\n');
const mdPath=path.join(out,'OpticalWaveguideRouter2D_三步汇报讲稿.md');await fs.writeFile(mdPath,md,'utf8');
const cand=path.join(build,'candidate_v2.pptx');await (await PresentationFile.exportPptx(p)).save(cand);
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const final=path.join(out,'OpticalWaveguideRouter2D_三步汇报_交大模板_最终版.pptx');
const r=await finalizePresentation({workspaceDir:base,candidatePath:cand,finalPath:final,pythonExecutable:'C:/Users/lihao/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe',integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit','--require-native-table-slide','5','--require-native-table-slide','7','--require-native-table-slide','12'],explicitTotalSlideCount:14,requiredNativeTableOwnerSlides:[5,7,12],fontPolicy:{basis:'design',families:[font]},verifyArtifactToolImport:true,receiptPath:path.join(build,'validation_v2_final2.json')});
console.log(JSON.stringify({pptx:final,md:mdPath,status:r.packageIntegrity?.status,slides:r.packageIntegrity?.slide_count,layout:r.presentationLayout?.finding_count},null,2));
