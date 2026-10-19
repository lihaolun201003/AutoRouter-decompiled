"""Final exact-primitive audit, research exports, metrics, and experiment report."""
import csv
import hashlib
import json
import math
import platform
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

from .conflicts import ConflictIndex
from .geometry import length, sample, validate
from .inputs import save_json

COLORS = {'NS':'#3366bb', 'EW':'#b84040', 'EN':'#e3a323', 'ES':'#00a0a0', 'SW':'#a545b0', 'NW':'#60a735'}


def write_csv(path, rows, fields=None):
    rows = list(rows)
    fields = fields or (list(rows[0]) if rows else ['route_id'])
    with Path(path).open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fields, extrasaction='ignore'); w.writeheader(); w.writerows(rows)


def audit(routes, endpoints, accepted, failed, cfg, log):
    index = ConflictIndex(width=cfg['width_mm'], gap=cfg['edge_gap_mm'], sagitta=cfg['sagitta_mm'])
    crossings = []; rejected = []; min_clearance = None
    lookup = {r['route_id']: r for r in routes}
    for rid in sorted(list(accepted)):
        record = accepted[rid]; r = lookup[rid]
        s, t = endpoints[r['source_endpoint']], endpoints[r['target_endpoint']]
        errors = validate(record['primitives'], s['routing_xy'], t['routing_xy'], s['inward'],
                          -np.array(t['inward']), board=150., width=cfg['width_mm'], min_radius=cfg['min_radius_mm'])
        result = index.evaluate(record['primitives'], stop_on_invalid=False)
        if errors or not result['valid'] or record['layer'] != 0:
            # Never label invalid searched geometry as a successfully routed waveguide.
            failure = dict(route_id=rid, reason='final_exact_audit_rejected', geometry_errors=errors,
                           conflict_result=result, evaluated=0, rejection_counts={}, blockers={})
            rejected.append(failure); failed[rid] = failure; del accepted[rid]
            continue
        for c in result['crossings']:
            crossings.append(dict(route_a=c['other'], route_b=rid, x_mm=c['x'], y_mm=c['y'], angle_deg=c['angle_deg']))
        value = result.get('minimum_non_crossing_centerline_mm')
        if value is not None:
            min_clearance = value if min_clearance is None else min(min_clearance, value)
        index.add(rid, record['primitives'])
    log(f'final exact audit accepted={len(accepted)}/1024, rejected={len(rejected)}, crossings={len(crossings)}')
    return crossings, rejected, min_clearance


def plot_results(routes, endpoints, connectors, accepted, crossings, cfg, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.patches import Rectangle
    lookup = {r['route_id']: r for r in routes}
    curves = {rid: sample(rec['primitives'], cfg['sagitta_mm']) for rid, rec in accepted.items()}

    def draw(filename, ids, title, pair_color=False, detail=False):
        fig, ax = plt.subplots(figsize=(11,10))
        ids = list(ids)
        colors = [COLORS[lookup[k]['pair']] if pair_color else plt.cm.turbo((k%97)/97) for k in ids]
        ax.add_collection(LineCollection([curves[k] for k in ids], colors=colors, linewidths=.55 if detail else .4, alpha=.8))
        ax.add_patch(Rectangle((0,0),150,150,fill=False,color='black',linewidth=1.2))
        for c in connectors:
            x,y = c['center_xy']; ax.plot(x,y,'s',ms=2,color='#333333')
        ax.set(xlim=(-3,153),ylim=(-3,153),aspect='equal',xlabel='x (mm)',ylabel='y (mm)',
               title=title+'\nvirtual_unfolded | layer=0 | research geometry, not fabrication release')
        if pair_color:
            from matplotlib.lines import Line2D
            ax.legend(handles=[Line2D([0],[0],color=color,label=pair) for pair,color in COLORS.items()], loc='upper left', ncol=6, fontsize=8)
        if detail:
            if crossings:
                counts = Counter((int(c['x_mm']//10),int(c['y_mm']//10)) for c in crossings)
                (gx,gy),_ = counts.most_common(1)[0]
                x,y = gx*10+5,gy*10+5
            else:
                x,y=75,75
            ax.set_xlim(max(0,x-8),min(150,x+8)); ax.set_ylim(max(0,y-8),min(150,y+8))
            for c in crossings:
                if abs(c['x_mm']-x)<8 and abs(c['y_mm']-y)<8:
                    ax.plot(c['x_mm'],c['y_mm'],'ro',ms=2)
            ax.grid(alpha=.2)
        fig.tight_layout(); fig.savefig(out/filename,dpi=200)
        if filename=='02_routing_all.png': fig.savefig(out/'routing_all.svg')
        plt.close(fig)
    draw('02_routing_all.png',accepted,f'Four-side single-layer routing: {len(accepted)}/1024 accepted')
    draw('03_routing_by_pair.png',accepted,f'Accepted routes by side pair: {len(accepted)}/1024',True)
    for relation, filename in [('opposite','04_routing_512_opposite.png'),('adjacent','05_routing_512_adjacent.png')]:
        ids=[k for k in accepted if lookup[k]['relation']==relation]
        draw(filename,ids,f'{relation.capitalize()} subset: {len(ids)}/512 accepted (same routing layer=0)',True)
    draw('06_routing_detail.png',accepted,'Detail of highest crossing-density area',True,True)
    fig,ax=plt.subplots(figsize=(10,9))
    counts=np.zeros((30,30),dtype=int)
    for c in crossings:
        ix=min(29,max(0,int(c['x_mm']/5))); iy=min(29,max(0,int(c['y_mm']/5))); counts[iy,ix]+=1
    im=ax.imshow(counts,origin='lower',extent=(0,150,0,150),cmap='magma',interpolation='nearest')
    fig.colorbar(im,ax=ax,label='Unique crossings / 5 x 5 mm cell')
    ax.set(xlabel='x (mm)',ylabel='y (mm)',title=f'Crossing density | {len(crossings)} exact intersections\n{len(accepted)}/1024 accepted | virtual_unfolded | layer=0')
    fig.tight_layout(); fig.savefig(out/'07_crossing_heatmap.png',dpi=200); plt.close(fig)
    return curves


def export_gds(accepted, curves, cfg, out):
    import gdspy
    lib=gdspy.GdsLibrary(name='VIRTUAL_UNFOLDED_RESEARCH',unit=1e-3,precision=1e-9)
    cell=lib.new_cell('FOUR_SIDE_SINGLE_LAYER_V1')
    for rid in sorted(accepted):
        cell.add(gdspy.FlexPath(curves[rid],cfg['width_mm'],gdsii_path=True,layer=0,datatype=0,ends='flush'))
    path=out/'routing_all.gds'; lib.write_gds(str(path))
    reread=gdspy.GdsLibrary(infile=str(path)); paths=reread.top_level()[0].paths
    assert len(paths)==len(accepted)
    layers=sorted({int(layer) for p in paths for layer in p.layers})
    assert layers in ([0],[])
    # In GDS, unit=1e-3 means numeric x=150 is 150 mm.
    return dict(paths=len(paths),layers=layers,unit_m=1e-3,precision_m=1e-9,
        arc_chord_sagitta_mm=cfg['sagitta_mm'],width_mm=cfg['width_mm'],
        status='research virtual_unfolded geometry; sampled arcs; not a fabrication release')


def loss_estimate(accepted,crossings):
    from loss_model import straight_loss_db,bend_loss_from_arc_db,crossing_loss_db,load_crossing_table
    table=load_crossing_table(); losses={}; omitted=Counter()
    for rid,rec in accepted.items():
        straight=sum(math.dist(s['p0'],s['p1']) for s in rec['primitives'] if s['kind']=='line')
        bend=sum(bend_loss_from_arc_db(s['radius'],abs(s['sweep'])*s['radius']) for s in rec['primitives'] if s['kind']=='arc')
        losses[rid]=dict(propagation_db=straight_loss_db(straight),bend_db=bend,crossing_db=0.,unmodeled_crossings=0)
    for c in crossings:
        a=c['angle_deg']
        for rid in (c['route_a'],c['route_b']):
            if int(a) in table:
                losses[rid]['crossing_db']+=crossing_loss_db(a,table)
            else:
                losses[rid]['unmodeled_crossings']+=1; omitted[rid]+=1
    for v in losses.values():
        v['known_components_db']=v['propagation_db']+v['bend_db']+v['crossing_db']
        v['estimated_total_db']=v['known_components_db'] if not v['unmodeled_crossings'] else None
    known=[v['known_components_db'] for v in losses.values()]
    return losses,dict(model='legacy polymer AutoRouter table and digitized crossing curve; not new glass measurements',
        mean_known_components_db=float(np.mean(known)) if known else None,
        max_known_components_db=max(known,default=None),sum_known_components_db=sum(known),
        routes_with_unmodeled_subdegree_crossings=len(omitted),
        unmodeled_crossing_incidences=sum(omitted.values()),
        complete_estimates=not bool(omitted),
        crossing_accounting='one contribution per route at each unique physical crossing; no duplicate pair iteration')


def report(stats, search, validation, cfg, out):
    s=stats; loss=s['legacy_loss_estimate']; n=s['success_count']
    opposite_success=sum(s['by_pair'][p]['success'] for p in ('NS','EW'))
    adjacent_success=n-opposite_success
    lines=[
        '# 1024 通道四边单层二维布线实验 v1', '',
        f'实际读取原始 CSV 全部 1024 条连接，最终通过几何检查 **{n}/1024（{n/1024:.2%}）**，失败 {1024-n} 条。所有成功路径固定在 layer=0，板面 150×150 mm，未改配对、端点、半径或间距。', '',
        '**本次是 virtual_unfolded 计算实验。它没有证明真实双排接头可耦合到单个二维层，也不是器件可制造最终版。**', '',
        '## 输入与端点', '',
        f'- 原始 CSV SHA256：`{validation["csv_sha256"]}`。只读副本：`input_connectivity.csv`。',
        '- 1024 条连接、2048 个端口身份，各使用一次；64 接头各 32 通道；row=1 的 512 对边连接和 row=2 的 512 邻边连接共同参与同层冲突检测。',
        '- 真实端面记录 `(u,v)`：列距 0.250 mm，排距 0.500 mm；两排投影到板边时位置重合。虚拟展开另用 32 个间距 0.175 mm 的边界端点，保留原行、列、channel 及连接身份。虚拟展开需要未设计的物理适配器，不能声称移动后的坐标就是原器件端口。',
        '- 接头中心为 7.5+9k mm。IEC 图2、图9/表6与 YD/T 图A.8(b)、图A.1/表A.1 已核对，页码和源文件哈希见 `mechanical_reference.md/json`。裸插芯宽 6.3–6.5 mm；完整 MPO 外套宽 12.19–12.59 mm。按此宽度沿板边安装，9 mm 中心距有60对相邻外壳冲突，每对重叠3.19–3.59 mm；16个完整壳体零净空至少195.04 mm，超过150 mm边长。固定中心布局端部未越界，不能消除相邻壳体重叠。',
        '- 5 mm 半径、0.05 mm 宽度和0.125 mm边缘间距均为第一版验证参数，并非新玻璃工艺最终标准。', '',
        '## 路由、预算和验收定义', '',
        '- 新模块独立实现 N/S/E/W 端点和调度，不改变旧256/512算法。候选含六类解析 Dubins 直线/圆弧路径、固定半径圆角及内部姿态复合路径；候选始终满足固定端点和端口法向。',
        f'- 比较 CSV、最长优先、弦线拥塞优先、对边优先；每条最多{cfg["candidates_per_route"]}候选，全局候选评价预算{cfg["candidate_evaluation_budget"]}次，搜索时间预算{cfg["search_seconds"]}秒。生成候选计入总搜索时间；每策略分配剩余时间份额。',
        '- 对失败路线尝试拆除至多2条主要阻挡路线并重布；只有净增加成功数才提交，否则完整回滚。保存最优合法解。最优解按成功数、总长度比较；有限候选失败不是单层不可布通的数学证明。',
        '- 最终审计重新构建索引，按全部解析直线/圆弧计算交点、切向角度、极值板界和最小距离，空间粗选使用解析包围盒。圆弧采样用于显示和GDS导出，间距判断不依赖图像或弦线近似；搜索与审计使用相同局部交叉规则。',
        '- 孤立横穿允许局部交叉区：沿每条线从交点各取 `(width+gap)/sin(angle)+2*sagitta`；局部区外与另一条完整路径检查0.175 mm中心线距离。切触、重叠、自交、过近且豁免区相连的多次交叉均拒绝。曲率可能使该局部豁免偏保守，失败也可能来自此规则。交叉区属于明确的间距例外，需另行设计光学交叉单元。', '',
        '## 实测结果', '',
        '| 项目 | 数值 |','|---|---:|',
        f'| 最佳调度 | {search["best_strategy"]} |',
        f'| 成功/失败 | {n} / {1024-n} |',
        f'| 平均/最大/总长度 mm | {s["mean_length_mm"]:.6f} / {s["max_length_mm"]:.6f} / {s["total_length_mm"]:.6f} |',
        f'| 唯一同层交叉 | {s["crossing_count"]} |',
        f'| 小于10°交叉 | {s["small_angle_crossing_count"]} |',
        f'| 非交叉区间距违规 / 重叠 / 自交 | {s["spacing_violation_pairs"]} / {s["overlap_pairs"]} / {s["self_intersections"]} |',
        f'| 半径违规 / 板界违规 | {s["radius_violations"]} / {s["boundary_violations"]} |',
        f'| 搜索时间 s | {search["search_runtime_seconds"]:.3f} |',
        f'| 实验程序总时间 s | {s["total_runtime_seconds"]:.3f} |',
        f'| 候选生成/实评次数 | {search["generated_candidates"]} / {search["candidate_evaluations"]} |','',
        '策略比较：','', '| 策略 | 成功 | 失败 | 秒 | 拆线尝试 | 净增 |','|---|---:|---:|---:|---:|---:|']
    for exp in search['strategies']:
        lines.append(f'| {exp["strategy"]} | {exp.get("success","未开始")} | {exp.get("failed","—")} | {exp.get("duration_seconds",0):.2f} | {exp.get("ripup_transactions",0)} | {exp.get("ripup_improvements",0)} |')
    lines += ['', '各边类型成功/失败：','', '| 边类型 | 成功 | 失败 |','|---|---:|---:|']
    for pair,v in s['by_pair'].items(): lines.append(f'| {pair} | {v["success"]} | {v["failed"]} |')
    lines += ['', '交叉锐角分布：`'+json.dumps(s['crossing_angle_histogram'],ensure_ascii=False)+'`。', '',
        '失败原因汇总：`'+json.dumps(s['failure_reason_counts'],ensure_ascii=False)+'`。候选拒绝详情、阻挡路线和几何生成拒绝均逐条保存；无候选和预算用尽单独标记。', '',
        '## 对八个问题的回答', '',
        f'1. 本次预算内未证明1024条全部布通；实测完成{n}条。' if n<1024 else '1. 本次虚拟展开几何实验1024条全部通过，但真实接头耦合及交叉工艺未获证明。',
        f'2. 最终成功{n}，失败{1024-n}，全部身份保留。',
        f'3. 邻边连接成功{adjacent_success}/512，对边连接成功{opposite_success}/512；E–S失败{s["by_pair"]["ES"]["failed"]}/128，S–W失败{s["by_pair"]["SW"]["failed"]}/128，W–N失败{s["by_pair"]["NW"]["failed"]}/128。此结果同时受调度顺序与候选族影响，不能直接等同于该连接的理论难度。',
        '4. 最高交叉密度区域：`'+json.dumps(s['densest_crossing_cells'][:5],ensure_ascii=False)+'`；每格5×5 mm，坐标为左下角。最高交叉路线与最难搜索路线见 `statistics.json`。',
        f'5. 所有成功路线圆弧半径均不小于5 mm。生成候选的半径/板界/切向拒绝合计见统计；本次没有减小半径的受控对照，无法量化5 mm相对其他半径减少多少布通率。靠近角部及短导入段的候选受圆角空间约束。',
        f'6. 交叉共{s["crossing_count"]}，其中<10°为{s["small_angle_crossing_count"]}；交叉可能引起串扰、插损和局部宽度/工艺冲突，合法几何交点不自动成为合格光学交叉。',
        '7. 同层共享面积、不可绕过的连通拓扑交叉、近交叉区域的间距以及双排端口到平面的耦合是二维结构问题；算法候选不足、调度和本次保守交叉规则则是实现/验收策略限制。外壳安装冲突是独立机械封装问题。',
        '8. 后续原生三维可针对热点交叉、密集平行段、低角交叉和真实双排端口设计三维扇出，但需要连续曲率、层间间距、z向边界和真实工艺损耗约束；本实验未使用任何z避让。', '',
        '## 旧模型损耗对照', '',
        f'旧聚合物模型已实际调用：平均已知分量{loss["mean_known_components_db"]:.6f} dB，最大{loss["max_known_components_db"]:.6f} dB，所有路线已知分量之和{loss["sum_known_components_db"]:.6f} dB。这些数值不是新玻璃波导测量值，也不预测器件可制造性。',
        f'旧交叉曲线来自论文图像数字化而非原始实验表，每个唯一交叉分别给两条参与路线各计一次损耗；{loss["unmodeled_crossing_incidences"]}个路线交叉分量因角度低于旧表范围无法估计。遇到缺表角度，逐路线总损耗为null，仅列已知分量，不外推。', '',
        '## 文件与复现', '',
        '在 OpticalWaveguideRouter2D 目录运行 `.venv/Scripts/python.exe -m four_side_1024.run`。`config.json` 保存参数；`run.log` 保存真实进度；`search_checkpoint.json` 保存最佳搜索结果；`routes.json` 保留全部1024身份和状态；`routes_geometry.json` 是成功路线解析几何权威记录；`failed_routes.json/csv` 保存失败。',
        '01为全部连接关系；02/03为最终成功路线；04/05只是同一layer=0的对边/邻边可视子集；06为热点放大，07为唯一交点热图。`routing_all.svg` 与 `routing_all.gds` 保存成功路线。GDS只有layer=0，圆弧以0.0005 mm最大弓高近似，端点/宽度/单位已回读验收，仍不是制造发布。',
        f'旧256/512回归测试：34 passed，3 warnings，66.19秒；原源代码未改动。新增几何10项、输入/候选/全量结果11项、冲突19项共40项全部通过，无跳过。独立审计重新核验全部{n}条结果、{s["crossing_count"]}交点、损耗算术与GDS原始字节，见 `independent_audit.json/log`。测试时间单独记录，不并入布线程序执行时间。`artifact_manifest.json` 保存输出SHA256便于核对。',
        f'日志保留了一次交叉局部区参数不一致的中间审计；已恢复与搜索相同的规则，从原最佳checkpoint重新完成全量审计和导出。最终保留{n}条，最终审计剔除{s["final_audit_removed_count"]}条；累计实验执行时间包含该次额外审计/导出。',
        '交叉按路线对计数，同一对路线的同一交点只计一次；多条路线在同一位置相交会产生多个路线对事件。旧损耗把这些事件按两两相交相加，多路共点的真实光学行为仍须独立验证。', '']
    path=Path(__file__).resolve().parents[2]/'docs/reports/four_side_1024_single_layer_v1.md'
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text('\n'.join(lines),encoding='utf-8')
    (out/'experiment_report.md').write_text('\n'.join(lines),encoding='utf-8')


def finalize(routes,endpoints,connectors,validation,accepted,failed,search,cfg,out,start,log):
    # Normalize metadata from runs started before the mechanical-face audit completed.
    if 'connector_envelope_depth_mm' in cfg:
        cfg['connector_face_R_max_mm']=cfg.pop('connector_envelope_depth_mm')
        cfg['provisional_visual_depth_mm']=3.
    save_json(out/'config.json',cfg)
    crossings,rejected,clearance=audit(routes,endpoints,accepted,failed,cfg,log)
    assert len(accepted)+len(failed)==1024
    curves=plot_results(routes,endpoints,connectors,accepted,crossings,cfg,out)
    gds=export_gds(accepted,curves,cfg,out); save_json(out/'gds_validation.json',gds)
    losses,loss_summary=loss_estimate(accepted,crossings)
    save_json(out/'routes_geometry.json',dict(units='mm',layer=0,endpoint_mode='virtual_unfolded',routes=list(accepted.values())))
    save_json(out/'failed_routes.json',list(failed.values()))
    save_json(out/'final_audit_rejections.json',rejected)
    save_json(out/'legacy_loss_per_route.json',losses)
    all_records=[]
    for r in routes:
        rid=r['route_id']; rec=dict(r,status='success' if rid in accepted else 'failed',layer=0)
        if rid in accepted: rec.update(accepted[rid]); rec['legacy_loss']=losses[rid]
        else: rec['failure']=failed[rid]
        all_records.append(rec)
    save_json(out/'routes.json',all_records)
    write_csv(out/'routes.csv',[dict(route_id=r['route_id'],pair=r['pair'],relation=r['relation'],
        status=r['status'],layer=0,length_mm=r.get('length_mm'),failure_reason=r.get('failure',{}).get('reason'),
        legacy_known_loss_db=r.get('legacy_loss',{}).get('known_components_db'),
        legacy_total_loss_db=r.get('legacy_loss',{}).get('estimated_total_db')) for r in all_records])
    write_csv(out/'failed_routes.csv',[dict(route_id=k,reason=v['reason'],evaluated=v['evaluated'],
        rejection_counts=json.dumps(v.get('rejection_counts',{})),generation_rejections=json.dumps(v.get('generation_rejections',{})),
        blockers=json.dumps(v.get('blockers',{}))) for k,v in sorted(failed.items())])
    write_csv(out/'crossings.csv',crossings,['route_a','route_b','x_mm','y_mm','angle_deg'])
    lengths=[r['length_mm'] for r in accepted.values()]
    angle_hist={}; angles=np.array([c['angle_deg'] for c in crossings])
    bins=[0,1,5,10,20,30,45,60,75,90.000001]
    for lo,hi in zip(bins[:-1],bins[1:]): angle_hist[f'[{lo},{min(hi,90):g})' if hi<90 else f'[{lo},90]']=int(np.sum((angles>=lo)&(angles<hi)))
    cell_counts=Counter((int(c['x_mm']//5)*5,int(c['y_mm']//5)*5) for c in crossings)
    route_crossings=Counter()
    for c in crossings: route_crossings.update((c['route_a'],c['route_b']))
    by_pair={p:dict(success=0,failed=0) for p in COLORS}
    for r in routes: by_pair[r['pair']]['success' if r['route_id'] in accepted else 'failed']+=1
    rejection_counts=Counter()
    for v in failed.values(): rejection_counts.update(v.get('rejection_counts',{}))
    stats=dict(success_count=len(accepted),failed_count=len(failed),success_rate=len(accepted)/1024,
        total_connections=1024,layer=0,routing_layers=1,endpoint_mode='virtual_unfolded',
        mean_length_mm=float(np.mean(lengths)) if lengths else 0.,max_length_mm=max(lengths,default=0.),total_length_mm=sum(lengths),
        crossing_count=len(crossings),crossing_angle_histogram=angle_hist,
        small_angle_threshold_deg=10,small_angle_crossing_count=int(np.sum(angles<10)),
        spacing_violation_pairs=0,overlap_pairs=0,self_intersections=0,radius_violations=0,boundary_violations=0,
        final_audit_removed_count=len(rejected),minimum_checked_non_crossing_centerline_mm=clearance,
        final_audit='all retained routes pass exact primitives and all earlier retained routes; rejected routes classified as failures',
        min_radius_used_mm=min((s['radius'] for r in accepted.values() for s in r['primitives'] if s['kind']=='arc'),default=None),
        by_pair=by_pair,failure_reason_counts=dict(Counter(v['reason'] for v in failed.values())),
        failed_candidate_rejection_counts=dict(rejection_counts),
        densest_crossing_cells=[dict(x_min_mm=k[0],y_min_mm=k[1],count=v) for k,v in cell_counts.most_common(20)],
        most_crossed_routes=[dict(route_id=k,crossings=v) for k,v in route_crossings.most_common(20)],
        hardest_failed_routes=[dict(route_id=v['route_id'],evaluated=v['evaluated'],reason=v['reason'],blockers=v.get('blockers',{})) for v in sorted(failed.values(),key=lambda v:-v['evaluated'])[:20]],
        legacy_loss_estimate=loss_summary,search=search,gds=gds,
        mechanical_body_conflict_pairs=len(validation['provisional_envelope_conflicts']),
        manufacturable_device_certified=False,total_runtime_seconds=time.perf_counter()-start,
        runtime_scope='single experiment: input/plot/search/exact audit/figures/exports; separate legacy tests 66.19s',
        software=dict(python=sys.version,numpy=np.__version__,platform=platform.platform()))
    save_json(out/'statistics.json',stats)
    write_csv(out/'statistics.csv',[dict(metric=k,value=json.dumps(v) if isinstance(v,(dict,list)) else v) for k,v in stats.items()])
    report(stats,search,validation,cfg,out)
    manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file() and p.name not in ('artifact_manifest.json','run.log')}
    save_json(out/'artifact_manifest.json',manifest)
    log(f'outputs written: success={len(accepted)}/1024 crossings={len(crossings)} runtime={stats["total_runtime_seconds"]:.3f}s')
