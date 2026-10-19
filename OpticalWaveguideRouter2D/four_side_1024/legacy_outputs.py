"""Research artifacts for the original-algorithm four-side adapter only."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from .inputs import save_json
from .outputs import audit,plot_results,export_gds,loss_estimate,write_csv,COLORS


def make_report(stats,cfg,validation,out):
    s=stats;search=s['search'];loss=s['legacy_loss_estimate']
    lines=['# 原逆向 AutoRouter：1024 通道四边单层适配实验','',
        f'本次按用户选择使用原逆向算法做必要四边适配，最终通过几何检查 **{s["success_count"]}/1024（{s["success_rate"]:.2%}）**，未完成 **{s["failed_count"]}** 条。全部1024条连接均读取，实际进入轨道处理{s["actual_routing_attempted_count"]}条，因全局预算未进入轨道处理{s.get("not_attempted_due_global_budget",0)}条。配对和端点固定，layer=0。','',
        '## 算法来源及必要差异','',
        '- `legacy_adapter.py` 是本次唯一入口。没有使用 Dubins、路径候选评分、多个调度策略、拆线重布或三维避让。之前搜索实验的文件保留追溯，不参与本次寻路。',
        '- `WGyset`、`MT`、`MTset` 直接导入原 `wiring_rect_826.py`；`sn_calc/noCross` 从该文件嵌套函数的AST原样提取执行，函数体未改。源文件、函数体AST哈希和原行号保存于 `algorithm_provenance.json`。',
        '- 本次验证轨道步进为width+gap=0.175 mm，从5 mm至145 mm内，取第一个通过原规则和全局几何检查的轨道，不按损耗或长度打分。below2above按规则坐标降序、above2below按规则坐标升序；保留原函数体、各自端口次序条件和sn_calc的fallback=8。',
        '- N/W源边调用above2below，E/S源边调用below2above；镜像规则坐标、上下接头角色及ln_calc端口序号随分支调整。该CSV两分支各分配512条；没有同边连接，不强套below/above同边分支。轨道/nodes按边对重建，跨组使用同一个全局几何索引；未声称恢复原四遍的共享状态。固定直接L接口按其精确位置检查。',
        '- 固定组顺序SW、ES、NW、EN、NS、EW：先处理角部邻边，再处理跨板对边；组内源端口按局部x降序。此顺序是四边适配的固定策略，不能称原双边四遍调度未经改变即可通用。',
        '- 四边通过等距旋转/镜像转到局部坐标。对边直接使用原双弯公式；邻边必须增加90°端口接口：先用唯一单L转弯，否则沿原轨道扫描使用终端x=145 mm的三弯正交接口。后者仍用固定R的90°圆弧。',
        '- 16通道状态数组扩为32通道；`ln_calc` 原 modulo 布局推断替换为显式局部通道序号，保持 `max(channel-1-6,4)` 算术。原算法的端口重排会写回sx/lx，本适配改为只按端口调度，禁止交换任何物理端点或CSV配对。',
        '- 保留小位移原公式 `theta=acos(1-d/(2R))`、`h=R*sin(theta)`：d<2R时使用两个半径仍为5 mm的短S弧；未把半径缩为d/2。d≥2R采用两个90°弧，d=0为直线。计算存储保留浮点精度，省去原Excel四位舍入。',
        '- 几何模块与原 `plotter_bend` 真运行fixture逐项比较，切点/中心的差异只来自原四位小数舍入；原256/512文件保持不变。',
        '- 所有方向共用一个冲突空间；原noCross只是局部轨道规则，不能替代四边全局解析几何检测。交叉区局部豁免、区外0.175 mm中心距、拒绝切触/重叠/自交的规则与之前几何验收一致。','',
        '## 输入、端点和机械限制','',
        f'- CSV SHA256：`{validation["csv_sha256"]}`；1024原始配对、2048端口身份恰好一次、64接头各32通道、全为不同边连接。先生成01连接图，再寻路。',
        '- 真实端面按列距0.25 mm、双排间距0.50 mm保存(u,v)坐标；二维实验使用单独标注的 `virtual_unfolded` 坐标，0.175 mm逐通道展开，不把双排当两层。虚拟展开没有解决真实双排端口到平面的耦合，因此不是实际器件可制造结论。',
        '- 板面固定150×150 mm；半径5 mm、宽0.05 mm、边缘间距0.125 mm是初版验证参数，不是新玻璃工艺最终标准。',
        '- 接头中心距9 mm为暂定值。标准资料确认完整MPO外套H宽12.19–12.59 mm；H沿板边时同边相邻外壳重叠3.19–3.59 mm，共60对冲突。16个完整外壳至少需195.04 mm，无法在150 mm边内无重叠安装。裸插芯6.3–6.5 mm与完整接头外壳须区分。详见机械参考及其页码、哈希。','',
        '## 全量结果','',
        '| 项目 | 实测 |','|---|---:|',
        f'| 成功/失败 | {s["success_count"]} / {s["failed_count"]} |',
        f'| 布通率 | {s["success_rate"]:.2%} |',
        f'| 平均/最大/总长度 mm | {s["mean_length_mm"]:.6f} / {s["max_length_mm"]:.6f} / {s["total_length_mm"]:.6f} |',
        f'| 同层交叉 / 小于10° | {s["crossing_count"]} / {s["small_angle_crossing_count"]} |',
        f'| 最终保留路线：非交叉区间距违规 / 重叠 / 自交 | {s["spacing_violation_pairs"]} / {s["overlap_pairs"]} / {s["self_intersections"]} |',
        f'| 最终保留路线：半径违规 / 板界违规 | {s["radius_violations"]} / {s["boundary_violations"]} |',
        f'| 进入轨道处理 / 进入完整冲突评价的路线 | {s["actual_routing_attempted_count"]} / {s["geometry_evaluated_route_count"]} |',
        f'| 原轨道扫描次数 / 几何冲突评价次数 | {search["scanned_tracks"]} / {search["candidate_evaluations"]} |',
        f'| 路由时间 / 程序总执行时间 s | {search["search_runtime_seconds"]:.3f} / {s["total_runtime_seconds"]:.3f} |',
        f'| 预算 | 全局{cfg["search_seconds"]}秒、{cfg["candidate_evaluation_budget"]}次几何评价；无每条评价上限 |','',
        '| 边类型 | 成功 | 失败 |','|---|---:|---:|']
    for pair,v in s['by_pair'].items():lines.append(f'| {pair} | {v["success"]} | {v["failed"]} |')
    lines+=['','交叉角度分布：`'+json.dumps(s['crossing_angle_histogram'],ensure_ascii=False)+'`。',
        '失败主因：`'+json.dumps(s['failure_reason_counts'],ensure_ascii=False)+'`。',
        '失败路线逐轨拒绝原因汇总：`'+json.dumps(s['failed_track_rejection_counts'],ensure_ascii=False)+'`。','',
        '## 八个验收问题','',
        f'1. 本次原算法适配在预算内完成{s["success_count"]}/1024；有限轨道和固定模板的失败不构成单层理论不可布通证明。',
        f'2. 成功{s["success_count"]}、失败{s["failed_count"]}；全部1024身份保留在routes.json，失败路线有扫描/评价数量、拒绝分类和阻挡路线。',
        '3. 各类型失败见上表。固定先邻边再对边、旧noCross偏保守，以及邻边终端模板均影响分布，不能直接当作拓扑下界。',
        '4. 最拥挤的5×5 mm交叉网格：`'+json.dumps(s['densest_crossing_cells'][:5],ensure_ascii=False)+'`。最多交叉路线与最难扫描路线保存在statistics.json。',
        '5. 5 mm半径从未减小；空间不足明确拒绝。本次没有改变半径的对照实验，不能量化其对布通率的独立影响；短端口引线、角部以及三弯接口受此约束。',
        f'6. 同层交叉{s["crossing_count"]}，小于10°交叉{s["small_angle_crossing_count"]}。几何交叉允许不代表光学交叉可制造；局部交叉单元的宽度、串扰和损耗尚未实测。',
        '7. 同层面积共享、不可绕开的连通交叉、近交叉间距和双排端口平面耦合属于结构问题；旧轨道规则、固定组顺序和邻边模板不足属于算法适配局限。机械外壳冲突须另行解决。',
        '8. 原生三维后续可重点处理交叉热点、低角度交叉、密集平行区与双排真实扇出，但须增加真实z间距、曲率和损耗约束。本次所有路径layer=0。','',
        '## 旧损耗模型及文件','',
        f'调用旧聚合物模型作为对照：平均已知分量{loss["mean_known_components_db"] or 0:.6f} dB、最大{loss["max_known_components_db"] or 0:.6f} dB。{loss["unmodeled_crossing_incidences"]}个交叉分量超出旧表范围时不外推，逐路线总值置null。旧模型不是新玻璃波导测量值。',
        '交叉按路线对去重后，每条参与路线分别计一次损耗；多路共点按多个两两事件计数，其物理效应需单独评价。','',
        '01是全部原连接；02/03是最终成功路线；04/05仅按对边/邻边分别显示同层子集，06为热点放大，07为交叉热图。SVG与GDS只导出成功路线；GDS全部layer=0，弓高≤0.0005 mm的离散圆弧研究几何，不是制造发布。',
        f'复现布线：在OpticalWaveguideRouter2D目录运行 `.venv/Scripts/python.exe -m four_side_1024.legacy_adapter --route --seconds {cfg["search_seconds"]:g} --evaluations {cfg["candidate_evaluation_budget"]} --output "{out}"`。不加--route只准备输入。原版不加适配的512基线保存在 `outputs/legacy_original_baseline_512`。','']
    path=Path(__file__).resolve().parents[2]/'docs/reports'/f'{out.name}.md'
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text('\n'.join(lines),encoding='utf-8')
    (out/'experiment_report.md').write_text('\n'.join(lines),encoding='utf-8')


def finalize(routes,endpoints,connectors,validation,accepted,failed,search,cfg,out,start,log):
    cfg.pop('candidates_per_route',None)
    save_json(out/'config.json',cfg)
    # Capture search participation before final auditing may reclassify routes.
    track_processed=len(accepted)+sum(v.get('scanned_tracks',0)>0 for v in failed.values())
    geometry_evaluated=len(accepted)+sum(v.get('evaluated',0)>0 for v in failed.values())
    not_entered=sum(v.get('scanned_tracks',0)==0 and v['reason']=='search_budget_exhausted' for v in failed.values())
    for group in search['groups']:
        ids=[r['route_id'] for r in routes if r['pair']==group['pair']]
        group['processed']=len(ids)
        group['track_processed']=sum(rid in accepted or failed[rid].get('scanned_tracks',0)>0 for rid in ids)
        group['geometry_evaluated']=sum(rid in accepted or failed[rid].get('evaluated',0)>0 for rid in ids)
        group['not_attempted_budget']=sum(rid in failed and failed[rid].get('scanned_tracks',0)==0 for rid in ids)
    search['attempted_field_definition']='legacy groups.attempted counts identity traversal; track_processed and geometry_evaluated give actual search participation'
    crossings,rejected,clearance=audit(routes,endpoints,accepted,failed,cfg,log)
    curves=plot_results(routes,endpoints,connectors,accepted,crossings,cfg,out)
    gds=export_gds(accepted,curves,cfg,out);save_json(out/'gds_validation.json',gds)
    losses,loss_summary=loss_estimate(accepted,crossings)
    save_json(out/'algorithm_provenance.json',search['source_provenance'])
    save_json(out/'routes_geometry.json',dict(units='mm',layer=0,endpoint_mode='virtual_unfolded',routes=list(accepted.values())))
    save_json(out/'failed_routes.json',list(failed.values()));save_json(out/'final_audit_rejections.json',rejected)
    save_json(out/'legacy_loss_per_route.json',losses)
    records=[]
    for r in routes:
        rid=r['route_id'];record=dict(r,status='success' if rid in accepted else 'failed',layer=0)
        if rid in accepted:record.update(accepted[rid]);record['legacy_loss']=losses[rid]
        else:record['failure']=failed[rid]
        records.append(record)
    assert len(records)==1024
    save_json(out/'routes.json',records)
    write_csv(out/'routes.csv',[dict(route_id=r['route_id'],pair=r['pair'],relation=r['relation'],status=r['status'],
        layer=0,length_mm=r.get('length_mm'),failure_reason=r.get('failure',{}).get('reason'),
        legacy_known_loss_db=r.get('legacy_loss',{}).get('known_components_db')) for r in records])
    write_csv(out/'failed_routes.csv',[dict(route_id=k,reason=v['reason'],evaluated=v['evaluated'],scanned_tracks=v.get('scanned_tracks',0),
        rejection_counts=json.dumps(v.get('rejection_counts',{})),blockers=json.dumps(v.get('blockers',{}))) for k,v in sorted(failed.items())])
    write_csv(out/'crossings.csv',crossings,['route_a','route_b','x_mm','y_mm','angle_deg'])
    lengths=[r['length_mm'] for r in accepted.values()];angles=np.array([c['angle_deg'] for c in crossings])
    bins=[0,1,5,10,20,30,45,60,75,90.000001]
    hist={f'{lo}-{min(hi,90):g}':int(np.sum((angles>=lo)&(angles<hi))) for lo,hi in zip(bins[:-1],bins[1:])}
    by_pair={p:dict(success=0,failed=0) for p in COLORS}
    for r in routes:by_pair[r['pair']]['success' if r['route_id'] in accepted else 'failed']+=1
    rejection=Counter()
    for v in failed.values():rejection.update(v.get('rejection_counts',{}))
    density=Counter((int(c['x_mm']//5)*5,int(c['y_mm']//5)*5) for c in crossings);route_cross=Counter()
    for c in crossings:route_cross.update((c['route_a'],c['route_b']))
    stats=dict(algorithm=cfg['algorithm'],success_count=len(accepted),failed_count=len(failed),success_rate=len(accepted)/1024,
        total_connections=1024,layer=0,routing_layers=1,endpoint_mode='virtual_unfolded',
        mean_length_mm=float(np.mean(lengths)) if lengths else 0.,max_length_mm=max(lengths,default=0.),total_length_mm=sum(lengths),
        crossing_count=len(crossings),crossing_angle_histogram=hist,small_angle_threshold_deg=10,small_angle_crossing_count=int(np.sum(angles<10)),
        spacing_violation_pairs=0,overlap_pairs=0,self_intersections=0,radius_violations=0,boundary_violations=0,
        final_audit_removed_count=len(rejected),minimum_checked_non_crossing_centerline_mm=clearance,by_pair=by_pair,
        actual_routing_attempted_count=track_processed,geometry_evaluated_route_count=geometry_evaluated,
        not_attempted_due_global_budget=not_entered,
        failure_reason_counts=dict(Counter(v['reason'] for v in failed.values())),failed_track_rejection_counts=dict(rejection),
        densest_crossing_cells=[dict(x_min_mm=k[0],y_min_mm=k[1],count=v) for k,v in density.most_common(20)],
        most_crossed_routes=[dict(route_id=k,crossings=v) for k,v in route_cross.most_common(20)],
        hardest_failed_routes=sorted(failed.values(),key=lambda r:-r.get('scanned_tracks',0))[:20],
        legacy_loss_estimate=loss_summary,search=search,gds=gds,mechanical_body_conflict_pairs=60,
        manufacturable_device_certified=False,total_runtime_seconds=time.perf_counter()-start)
    save_json(out/'statistics.json',stats)
    write_csv(out/'statistics.csv',[dict(metric=k,value=json.dumps(v) if isinstance(v,(list,dict)) else v) for k,v in stats.items()])
    make_report(stats,cfg,validation,out)
    save_json(out/'RUN_STATUS.json',dict(status='completed',routing_executed=True,
        total_connections=1024,actual_routing_attempted_count=stats['actual_routing_attempted_count'],
        success_count=len(accepted),failed_count=len(failed),layer=0,
        algorithm=cfg['algorithm'],result_image='02_routing_all.png'))
    source={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).resolve().parent.glob('*.py')}
    save_json(out/'source_manifest.json',source)
    save_json(out/'artifact_manifest.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file() and p.name not in ('artifact_manifest.json','run.log')})
    log(f'original algorithm output: {len(accepted)}/1024, crossings={len(crossings)}, elapsed={stats["total_runtime_seconds"]:.3f}s')
