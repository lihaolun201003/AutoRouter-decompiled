# 空间分组式 U 形线束三维布线 — 可执行几何方案（GEOMETRY_PLAN）

基线：`phase5_dynamic_optimization/after/routes_l3d.json`（1024/1024，23356 唯一交叉对，55 提升四元组/440 升降）。
目标：64 个 `kind=same` 四元组（group 20–35 z1、144–159/160–175/176–191 z2，共 256 条）重构造；其余 768 条逐字段原样。
层映射：A(20–35)→L2、B(144–159)→L2、C(160–175)→L3、D(176–191)→L4（即 L2/L2/L3/L4）；R=15、0.08 净空、150 板面、C4 原子。
单条几何：端口 → base 直线(长 E) → S 升(dz) → 目标层 90°arc + 中直(d−2R) + 90°arc → S 降 → base 直线(E) → 端口。
自由变量：E（=入口/出口直线长）、a（入口直线内 S 起点，`a∈[1.2, E−f]`）、出口 S 终点深度 `d_b∈[1.2, E−f]`；
`f=2R·sin(theta)`，`theta=acos(1−dz/2R)`（dz=0.5/1.0/1.5 → f=5.454/7.681/9.367 mm）。高平段长 = total−a−f−…，total=2E+πR+(d−2R)。
硬性：`E>=f+2.4`、S 两端各留 ≥1.2 mm 平段（否则首/尾 part 不是 flat，`World.check_structure` 报 route_must_start_and_end_flat）、E≤150。

## 1 l3d.world.World / ClearanceWorld3D 增量校验（用法与坑）
- `World.check_route(route)`（l3d/world.py:182）**必须在 `add_route`(147) 之前调用**，且 world 中不能已含该 route：
  `ClearanceWorld3D._flat_vs_transitions`(fsd25d/world25d.py:365) 与 `_transition_vs_flats`(:283) **不排除自身 route_id**；
  只有 `_transition_vs_transitions`(:413) 有 `other.route_id != route_id`。自身 flat 与自身 transition 在交界处距离=0 → 假违规。
  正确模式：`base_world = world_without(group_ids)`（仿 v3c4/dynamic_opt.py:224），对 4 条各 `check_route`（先查后加或在只含前 k 条的临时 world 查第 k+1 条），
  然后 `temp=World(stack)` 内 4 条互查（dynamic_opt._candidate_compat:536 的原型）。
- 同层 flat 严格 2D：`PlaneWorld.evaluate`(world.py:51) → D56Index(strict)；`evaluate().valid`/`blockers`，blocker=part_id=rid*1000+index（world.py:24），route_id=blocker//1000（dynamic_opt._violation_routes:480）。
- `World.check_route` 对首个同层 flat 违规**立即 return**，3D 段不执行 → violations 不完整；诊断需再单独调 `clearance_world.check_route`。
- `remove_route`(155) 会 `ClearanceWorld3D` 全量重建（world25d 无增量删除），实测全量 1024 条世界 0.42 s、768 条固定世界 0.31 s → 只按“组”重建，不要进候选内循环。
- 实测单 route `check_route`≈5.9 ms（768 固定 world），单四元组 3D 互查 ~30–200 ms；`add_route` 会把 transition 按 dense 0.02 mm/coarse 0.25 mm 采样约 445 点插格。
- 阈值：router 侧 `accept_point=0.091`、`accept_segment=0.081`（world25d.py:28-40，保守）；validator 侧 `0.08−tol`。**World 过 ≠ 最终过**：phase5 after 的 min_3d=0.0832 < World accept，最终仍需 validator。

## 2 四条 C4 旋转路线：字段 / 方向 / reverse
- 代表条：`frame,_=UG._canonical_frame(p,q,inward,−inward,C.BOARD_MM,C.WIDTH_MM)`（r15/u_geometry.py:169）；
  `canonical=UG._quarter_pair(frame['p_canonical'],frame['q_canonical'],R,E,d−2R)`(:294)；`world=transform_primitives(canonical,frame['transform'],inverse=True)`。
  与 `manual_c4/router.py:same_side_candidates`(95) 的 BULGE_LADDER(38) 同源；D 组 176–191 等可用 E 阶梯 [2..120]+[1,3,5] 的单调子集。
- 3D 组装直接复用 `lift_cross.lift_route(record,row,layer_id,layer_z,rise_start,fall_start,new_prims)`（v3c4/lift_cross.py:174）：
  parts=[flat(L1,row_z,head), transition(make_transition,fsd25d/path3d.py:174), flat(Lk,layer_z,travel), transition(降：z0=layer_z,z1=row_z,direction=前进切线), flat(L1,row_z,tail)]；
  route 字段（:224-239）：`plane/source_row/target_row/source_port{xy,z_mm,layer_id}/target_port/start_z_mm/end_z_mm/layer_sequence=[1,L,1]/layer_z_sequence/n_transitions=2/lifted=True/layers_used=[1,L]/xy_length_mm/length_mm=Σparts/z_span_mm`。
  transition 字段必须齐：`kind,start,direction,z0,z1,dz_mm,radius_mm,footprint_mm,theta_rad,end,length_mm,from_layer,to_layer`（validate_l3d._parse_transition_part:1156 会逐项校验 theta/footprint/length 公式与半径=15）。
- 三条成员：`L3.rotate_to_member(rep_route,phase,SimpleNamespace(src_xy=现 source_port.xy,dst_xy=现 target_port.xy))`（v3c4/l3d.py:145）：
  `rotate_route`(:64) 用 `_rot_xy=[150−y,x]`(:41) 旋转 flat primitives(经 `inputs.rotate_primitives`:163) 与 transition 的 start/direction/end；
  `orient_route_to`(:131) 端点不匹配时 `reverse_route`(:100)：parts 逆序、z0/z1 互换、dz/direction 取负、from/to_layer 互换、primitives 反序（`inputs.reverse_primitives`:171：p0/p1 互换、arc start_angle+=sweep、sweep 取负）、ports 互换。
  之后按 member 记录覆盖 `source_port/target_port` 的 xy/z_mm/layer_id（lift_cross.build_group_routes:740-771），再用 `route_geometry_key`(:178)/`audit_c4_3d`(:183) 校验严格旋转。
  不要每条独立用自己 canonical 重建：1e-6 round 比较会失败。

## 3 全量独立验收最稳调用
- `from four_side_1024.v3c4.lift_cross import validate_payload_v4; rep=validate_payload_v4(payload, v4_root=<campaign>/phase2_2d)`（lift_cross.py:1131）：
  从 `phase2_2d/routes_1024.json` 组装 identity（planes/routes/endpoints），monkeypatch `validate_l3d._PORT_CACHE['identity']`(967) 与 `_port_identity`(970)，再 `V.validate_payload(payload, allow_exploratory=True)`(validate_l3d.py:2463)。
  已实测：v4_root 换成 manual 的 `phase2_2d` 可正常 PASS（5.3 s，exploratory_only，min_3d=0.0832）。
- 判定：`report['exploratory_pass'] and all(report['counts'].values()==0)`；`formal_acceptance` 恒 false（stack provenance=unconfirmed_simulation，l3d/layers.py:203）。
- violations → group：条目 `{category,kind,route_id[,other_route][,detail]}`；**同层违规的 route_id 是字符串 `"rid:partidx"`**（`_audit_same_plane`:1812 的 part_id），需 `int(str(x).split(':')[0])`；3D/端口/几何违规是 int。
  由 `inputs/connectivity_1024.json` 的 groups 建 rid→(group_id,phase)，用 route_id 与 other_route 双向映射到 group，供 repair/revert 定位。
- 交叉对独立重算：`fslw.audit_route_pairs(prepare_route(flat_prims), clearance=0.08, sagitta=0.0005, policy='strict')` 按物理 z（round 1e-9）分组，唯一对跨高度去重（outputs/.../verification/verify_3d.py:crossing_statistics:783）；`crossing_pairs_after` 是逐高度之和，不等于唯一对数。
- 注意 verify_3d.py 的 `verify_route_geometry`(:440) 会把每条 route 的 XY 逐段回放到 phase2 的 2D 链上——**新 U 的 2D 路径变了（直线延长），256 条目标路线必须改用“自身一致性”检查**（p0/p1 接续、line 轴对齐、arc R=15、transition 在直线段且与切线一致、xy_length/parts 长度一致），其余 768 条继续严格回放 + parts 逐字段不变。

## 4 容易漏掉的硬约束 / 边界
1. **端口影线（最关键）**：row1/row2 端口 XY 完全相同、z 差 0.5（已核对 N08:1:16=N08:2:16=(72.375,150)）。
   z1→L2 的 S 在距 S 起点 u=√(2R·0.5−0.5²)=3.84 mm 处穿越 z=0.5，正落在同一端口 z2 路线的 base 直线上（同轴）→ 3D 距离 0。
   必须让 `a+3.84` 超过该 z2 路线 base 直线长度，且再过 ~√(2R·0.08)=1.55 mm 越过其 arc；否则只能把同端口 z2 目标四元组与该 z1 四元组联合规划。
   建议搜索前对每个端口预计算“被 z=0.5 固定 flat 阻塞的深度区间”，A 批 E 相应加大；`World.check_route` 能抓但盲搜浪费预算。
2. 高平面互查：`_flat_vs_transitions` 采样 0.25 mm 粗、0.02 mm 细并带 1-Lipschitz 下界；transition 穿越中间层（z1→L4 跨 0.5/1.0/1.5；z2→L4 跨 1.0/1.5）全部由它覆盖；跨层 flat/flat 由层间距保证。
3. 板边：`UG._validate`(u_geometry.py:332) + `fslw.geom.canonical_validate` 检查 150×150；E≤150（N 侧 y=150−E≥0），且高平段终点不出板。
4. 端口：首/尾 flat 的 p0/p1 必须等于 `source_port/target_port.xy`（validate_l3d._check_route_ports:1505，POS_TOL）；z 必须是 row 行高 0/0.5、`layer_id=1`、唯一 2048 端口。
5. 层序列：恰好 2 个 transition、1 升 1 降、同一高层、`layer_sequence=[1,L,1]`、`n_transitions=2`、`lifted=True`；`_back_to_back_transitions=0`。
6. 段连续性：transition 起点/终点必须在同一条 line primitive 上且方向=路径切线（`make_transition` 保证；自建时用 `P.path_point_at`(path3d.py:93) 取 point/direction，禁止在 arc 上放 S）。
7. 同层 2D strict：候选必须无 `same_plane_violations`；U 之间“零 XY 交叉”优先（见 §5，可做到 0），与既有高层的合法交叉仍计入唯一交叉对。
8. 768 条“原样”：以 after 记录 dict 为 base，只对目标 rid `update()` 几何字段；非目标记录连同字段顺序/键集合逐字节语义保持；最终 1024 条全部 `status=routed`。
9. `layer_stack` 必须内嵌 payload（`stack.to_dict()`，`layers.build_stack('medium_050')`:203），否则 validator 拒绝几何执行。
10. identity monkeypatch 是**进程级全局状态**，validator 不可多线程并发；12 进程扫描时每个 worker 进程各自注入一次（或校验只在父进程做）。
11. 16 个 C 批目标组当前已抬升到 L3/L4/L5（root=`after`），固定世界必须排除**全部 64 个目标组的 256 条**，而不只是 flat 的。
12. `World.check_structure`(world.py:107) 先跑（廉价），可提前发现 parts 顺序/接续/高度问题，避免贵检查。

## 5 数据事实（本轮只读 dry-run 实测，未落盘）
- 64 组在 4 个 side 上：区间关系 1280 disjoint + 736 contains、**0 partial overlap**；A/B/C/D 每批 16 组都是全嵌套链（120 对全 contains）。
  L2=A∪B：240 内嵌（各批 120）+ 256 跨批 disjoint → 只要 **E 沿嵌套由外到内严格递减（外深内浅）**，同层 U-U 交叉可做到 0；建议 E=E_floor+(max_depth−depth(g))·2 mm。
- 目标 256 条目前参与的唯一交叉对 11664（其中 U-U 仅 104）→ 全部离开 L1 行后理论可消减 ~1.1e4 对；新增只可能是同目标层内交叉/合法交叉。
- 实测：全量 World 0.42 s、768 固定世界 0.31 s、`check_route` 5.9 ms/条、交叉统计 2.3 s、`validate_payload_v4` 5.3 s。
- 现 64 组 rep 的 2D primitives 全部精确等于 `_quarter_pair(bulge=phase2 param)`；phase5 已提升组仅 160–175（L3/L4/L5）。

## 6 实现骨架（建议 `four_side_1024/manual_c4/spatial_u_bundle.py` + `_run.py`）
```
load(after, phase2_2d, connectivity)  # records/identity/prims/frames
assign(group) -> layer_id(batch), E(chain depth), a, d_b   # E>=f+2.4, outer-deeper
build(group, E,a,d_b) :
  prims = quarter_pair(canonical)  -> world prims (rep)
  rep = lift_cross.lift_route(record,row,L,zL,a,fall_start,world_prims)
  members = L3.rotate_to_member(rep,phase,frame(member)); patch ports
evaluate(routes, group_ids) -> _candidate_compat 仿写（world_without + 先查后加 + temp 互查）
  + 2D crossing delta（_cheap_delta 仿 dynamic_opt:599）+ 硬约束(§4)
search: E∈阶梯(按 chain rank), a∈{1.2,3,6,10,...}, d_b 同; 目标 = 唯一交叉对不增、min3D 最大、长度最小
commit: 更新 current_routes；下一组 base_world 重新 world_without(组)
final: build_payload -> validate_payload_v4(phase2_2d) -> 独立验收(crossing_statistics + 自写 target XY 自洽检查 + 768 条不变)
```
复用：`lift_cross.transition_geometry`:130 / `lift_route`:174 / `validate_payload_v4`:1131；`l3d.world.World`；`v3c4.l3d.rotate_to_member`:145；`dynamic_opt._candidate_compat`:536/`_world_without`:224；`manual_c4.router.same_side_candidates`:95（BULGE_LADDER）；`verify_3d.crossing_statistics`:783（口径）。
风险：lift_cross 的 repair/revert 循环（phase3 `repair_rounds`、revert_groups:985）不要继承；World 重建成本（按组）；identity 注入；transition 方向/反序；parts 缺字段；板边；四元组参数一致性（必须 rep+rotate 而非各建）。

## 7 关键索引
lift_cross.py: `transition_geometry`130 `lift_route`174 `analyze_planes`299 `plan_candidates`609 `build_group_routes`740 `try_group`803 `revert_groups`985 `build_payload`1023 `validate_payload_v4`1131
world.py: `part_id`24 `PlaneWorld`32 `World`74 `flat_route`86 `check_structure`107 `add_route`147 `remove_route`155 `rebuild`169 `check_route`182
world25d.py: `ClearanceWorld3D`180 `add_route`273 `check_route`471 `self_clearance_violations`503
validate_l3d.py: `_Report`226 `_PORT_CACHE`967 `_parse_transition_part`1156 `_check_route_ports`1505 `_parse_route`1664 `_audit_same_plane`1812 `_audit_true_3d_clearance`1956 `_cross_plane_flat_clearance`2039 `validate_payload`2463
u_geometry.py: `_canonical_frame`169 `_quarter_pair`294 `_validate`332 `u_candidates`468；inputs.py: `rotate_primitives`163 `reverse_primitives`171 `orient_primitives`189；l3d.py: `rotate_route`64 `reverse_route`100 `rotate_to_member`145 `audit_c4_3d`183
path3d.py: `path_point_at`93 `path_split`110 `make_transition`174 `transition_samples`192（输入字段 start/direction/z0/z1/radius_mm/theta_rad）
