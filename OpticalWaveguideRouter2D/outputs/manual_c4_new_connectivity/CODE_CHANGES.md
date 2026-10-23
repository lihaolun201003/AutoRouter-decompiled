# 代码修改记录（新连接表实验轮，2026-10-22）

原则：**不重写布线算法、不放宽任何物理约束、不覆盖历史实验目录**。既有算法引擎
（`four_side_1024.v2opt` / `d56` / `fslw` / `r15` / `l3d` / `v3c4` 的几何与验收逻辑）
全部原样复用；只做了两件事：

1. **新增** `four_side_1024/manual_c4/` 适配包（新连接表 → 既有数据结构）：
   - `connectivity.py`：读取两份人工 CSV，用权威端口模型 `fslw.ports.build_plane_endpoints()`
     校验（端口身份/XY/row/column/channel/side/relation、1024 端口各用一次、C4 闭合），
     复制原始 CSV 到 `outputs/manual_c4_new_connectivity/inputs/`，合成既有 12 列
     1024 行拓扑 CSV（route_id 1..512 = z1，513..1024 = z2）与 256 个 C4 旋转四元组；
   - `state.py`：`ManualLayoutState`，复用 `v2opt.core.LayoutState` 的 D56 精确索引 /
     oracle / 端口帧；仅替换路由来源；同边连接（旧 `canonicalize` 只接受两条不同边）
     不进入 canonical frame，只注入其端点固定线，并交给 R15 同边 U 族布线；
   - `router.py`：`ManualGroupRouter`，复用 `v3c4.c4.GroupRouter` 的四元组联合搜索/
     检查/原子提交逻辑；新增同边 U 组入口（`r15.u_geometry` 的 quarter-pair 几何，
     R=15 不缩；bulge 梯沿用 V4-C4 已验证的 0..120 mm/2 mm 档 + 1/3/5 档，
     否则每边只能嵌套 4 条 U，16/48 组同边连接必然放不下）；
   - `audit2d.py` / `run2d.py` / `plots2d.py`：新连接表的二维运行器、独立验收包装与图。

2. **既有文件的可选参数化**（默认值 = 历史行为，旧命令/旧输出不受影响）：
   - `four_side_1024/v3c4/ablation.py`：`run_smoke/run_full/build_comparison/main`
     增加可选 `v4_root`（默认 None → 历史 V4 路由根）与 `label`（默认 `V4-C4`）；
     `run_full` 在子进程命令中按需追加 `--v4-root`；图表/表格标题使用 `label`；
   - `four_side_1024/v3c4/dynamic_opt.py`：`DynamicOptimizer.__init__` 增加可选
     `v4_root`（默认 None → 历史 V4 路由根），透传给 `CrossingLifter`，并在
     `input_hashes` 记录 `routing_root`；输出 `experiment` 名可用 `topology_label` 配置；
     **必要缺陷修复**：`build_payload()` 对每条被重调度路线先从路由 manifest
     (`lifter.records`) 回填连接身份字段（source/target endpoint、relation、pair、
     sides、row）再覆盖几何/层字段——旧实现只写精简 route dict，导致被接受动作的
     52 条记录丢失身份元数据（几何本身正确，独立 l3d 因注入 identity 未暴露）；
     `summary()` 的 `routed_before` 由硬编码 1020 改为实际 `len(lifter.routed)`（1024）。
   - `four_side_1024/v3c4/dynamic_run.py`：`run/main` 增加可选 `--v4-root`、`--label`，
     透传 `v4_root` 给优化器，图题与 `summary` 使用 `label`。
   - `lift_cross.py / lift_cross_run.py`：**未修改**——其 `--v4-root` 参数本来就存在，
     只需指向本轮 `phase2_2d` 目录即可（该目录的 `routes_1024.json` 提供同一 schema 的
     路由与 256 个 C4 四元组）；3D 验收的 identity 由 `validate_payload_v4` 从该目录注入。

约束核对：R=15 mm（所有圆弧）、波导宽 0.05 mm、非豁免中心线净空 0.08 mm、板面
150×150 mm、row1 z=0 / row2 z=0.5 mm、端口位置与切向固定、升降只在直线段、每条最多
一次上升/下降、C4 四元组原子提交、交叉按唯一 (route_id_a, route_id_b) 跨全部高度去重
——均未改动；层高仍为探索性参数，3D 验收为 exploratory PASS，不代表制造工艺正式验收。

---

# 追加：空间分组式 U 形线束三维布线实验（2026-10-23）

新增（不影响任何既有输出）：

- `four_side_1024/manual_c4/spatial_u_bundle.py`：U 线束几何构造器（端口→延长入口直线→
  S 上升→目标层 90° 圆弧+中间直线+90° 圆弧→S 下降→延长出口直线→端口；复用
  `r15.u_geometry._quarter_pair` 与 `v3c4.lift_cross.lift_route`）、逐四元组可行性扫描 /
  嵌套深度链分配、与固定 768 条路线的增量 3D 检查（`l3d.world.World`）、payload 组装、
  指标计算；
- `four_side_1024/manual_c4/run_spatial_u_bundle.py`：实验 runner（搜索缓存、分层分配、
  "仅修改 U"与"含局部重路由"两个变体、权威 `validate_payload_v4` 验收、对照表、图）；
- `four_side_1024/manual_c4/spatial_u_bundle_plots.py`：前后 3D 总图、6 张逐层图、4 张
  U 线束局部放大图；
- `four_side_1024/tests_manual_c4/test_spatial_u_bundle.py`：构造/C4/分配/未改动路线/
  验收产物的快速测试。

明确记录的局部重路由（仅 final 变体，与"仅修改 U"分开比较）：

- 非 U C4 四元组 **group 11**（z1 对边，route_id 12 / 231 / 232 / 29）原本被 V2 抬到
  L3（z=1.5 mm）；其 L3 长直线与 z2 第二组四角 U（group 167，目标 L3）的端口/直线在
  同一物理平面共线，任何参数都无法避免冲突。final 变体把该四元组整体重新抬升到
  L5（z=2.5 mm，`a_in=64, a_out=48`，2D 拓扑/端口/连接不变），并在
  `u_layer_assignment.json` 的 `modified_non_u_routes` 与 `validation.json` 中逐条记录。
  仅修改 U 的变体（`routes_1024_u_only.json`）不移动任何非 U 路线，因此 group 167
  保留 V2 原始几何、目标 L3 未完成（63/64），失败原因记为"被其他非 U 路线阻挡
  （L3 同层共线冲突）"。

约束核对：仍为 R=15、宽 0.05、净空 0.08、板面 150×150、接口高度 0/0.5、C4 四元组
原子旋转、升降仅在 2D 直线段、每条 ≤1 升 1 降、目标层分配固定 L2/L2/L3/L4；未修改
任何端口配对。层高 L2–L5 仍为探索性参数，3D 验收 exploratory PASS。

---

# 追加：结构化分层布线 A/B 实验（2026-10-23）

新增（不影响既有输出）：

- `four_side_1024/manual_c4/structured_layer_routing.py`：结构化分层框架——连接/2D
  底图加载（可选 z1↔z2 行交换）、全平铺基底、对边 L2 直通构造（延长 base + S 升降 +
  C4 四元组）、U 目标层重构（90°圆弧/中间直线/延长直线）、组内成员互检、逐组 3D
  可行性扫描、例外优先/困难组优先装配、payload 组装、权威验收与指标；
- `four_side_1024/manual_c4/structured_layer_plots.py`：A/B 图件（整体前后 3D、
  L1-z1…L5 逐层、仅对边 3D/L2、对边升降局部放大、仅 U 3D 与 U L3/L4/L5）；
- `four_side_1024/manual_c4/structured_comparison.py`：A/B/旧 Spatial/前置 V2 对照表；
- `four_side_1024/tests_manual_c4/test_structured_layer_routing.py`：A/B 身份/端口/
  规则分层/C4/验收/交付物测试。

方法要点：先把 1024 条已验收的 Manual-C4 2D 走线全部平铺在接口层（合法三维初始
布局），再在对边/U 的目标层上逐组抬升；完整 XYZ 检查（含组内成员互检与跨层升降
段），失败组保留接口层平铺并逐组记录原因（不伪造成功）。

A（原 z1/z2 分配）：1024/1024；邻边 496 接口层；对边 **54/68 组（216 条）集中 L2**，
14 组（56 条，5.5%）例外保留接口层（同列影子路线导致升降过渡与 0.08 净空冲突）；
U **64/64**（L3=128、L4=64、L5=64）；唯一交叉对 19584、升降 944、总长 98033.77 mm、
min3D 0.0917；权威 3D PASS（counts 全 0）；独立验收 PASS（25/25）。

B（z1/z2 连接表整体交换）：1024/1024；邻边 496；对边 **66/68 组（264 条）集中 L2**，
2 组例外；U 仅 **16/64** 达标（48 组失败：行交换后原 z2 的 U 落到 z1 基排，其端口列
在 z2 行被对边连接占用，接口平面同列升降过渡与 0.08 净空结构性冲突；含角部
144–175 全部 32 组 + 中部 16 组；全部保留接口层并逐组记录）；唯一交叉对 26152、
升降 656、总长 99554.33 mm、min3D 0.0849；权威 3D PASS（counts 全 0）。

产物：`outputs/manual_c4_new_connectivity/structured_layer_routing/{A,B}/`（routes、
u/opposite assignment、validation、summary、15 图组、READY/ARTEFACTS_READY）、
`_work/`（可行性扫描、参数、基世界、checkpoints）、顶层 `comparison_table.*`、
`verification/`（独立验收脚本与报告）。A 为最优可行方案；B 如实报告规则分层不可行。

---

# 追加：Hybrid C2/C4 Directional Layer Routing（2026-10-23）

新增（不影响既有输出）：

- `four_side_1024/manual_c4/hybrid_c2_c4.py`：混合对称性方向分层框架——z1 对边按
  端口方向拆成 66 横向 + 66 纵向 C2 二元组；C2 二元组共享升降参数、严格 180°旋转；
  目标方向抬升 L2 的构造（base + S 升降 + L2 直线）；z2 严格 C4（U/对边/邻边与
  Structured A 逐字段相同）；完整 XYZ 验收与交叉类型分解；
- `four_side_1024/manual_c4/run_hybrid_c2_c4.py`：H/V 装配 + 权威验收 + 交叉削减分析
  + C2 分配文档；
- `four_side_1024/manual_c4/hybrid_c2_c4_plots.py`、`hybrid_comparison.py`：每组 13
  组图件（整体前后 3D、逐层、横/纵独立、方向分屏、仅对边 3D、密集区放大）与
  H/V/旧 A/旧 Spatial 对照；
- `four_side_1024/tests_manual_c4/test_hybrid_c2_c4.py`：混合 C2/C4 身份、方向分层、
  U/z2 固定保持、C2/C4 旋转、C2/C4 混合验收与交叉削减测试。

H/V 结果：1024/1024 布通；64/66 个 C2 二元组抬升（2 对失败保留 L1-z1 并记录）；
z1 横纵同层交叉 10928→7032（−3896）、z=0 交叉 17576→11952（−5624）、全局唯一交叉
19584→12960（−6624）、升降 944→784、min3D 0.0917；权威 3D exploratory PASS。
主要瓶颈：z2 接口层相邻路线与目标方向 line 同排并行（parallel shadow），R15+dz=1.0
的 S 升降足印 7.68mm 使 34 个 C2 二元组只能用深窗口，base 直线段留在 z=0 造成剩余
横纵交叉；2 对（group 2/3 方向对）无可行升降参数。详见
`outputs/manual_c4_new_connectivity/hybrid_c2_c4_directional/` 的 README、
crossing_analysis 与 verification。
