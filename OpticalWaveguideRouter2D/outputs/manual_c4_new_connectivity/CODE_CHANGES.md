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
