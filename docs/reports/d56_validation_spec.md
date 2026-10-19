# D56 独立几何校验器说明与实测结果（Phase 7a）

本文档描述 `OpticalWaveguideRouter2D/four_side_1024/d56/validate_d56.py`（独立校验器）
与 `four_side_1024/d56/tests_d56/`（pytest 套件）的校验项、容差、判定口径、命令行和实测数字。
契约见 `four_side_1024/d56/SPEC.md`。校验器**不调用**寻路器自己的 `validate` / `ConflictIndex`
作为判据；仅把 `four_side_1024/geometry.py` 的 `intersections`/`bounds` 当纯解析原语使用，
`four_side_1024/conflicts.py` 全程未 import。

## 1. 命令行

```powershell
# 最终验收：对 Lead 的 d56 优化运行目录做全量独立审计
.venv\Scripts\python.exe -m four_side_1024.d56.validate_d56 `
    --run-dir outputs\four_side_1024_d56_optimized --output scratch\validate_audit.json

# 兼容历史产物：SPEC routes.json、legacy routes.json、legacy routes_geometry.json 均可
.venv\Scripts\python.exe -m four_side_1024.d56.validate_d56 `
    --routes outputs\four_side_1024_legacy_two_branch_v2\routes_geometry.json

# 仅单路线检查
.venv\Scripts\python.exe -m four_side_1024.d56.validate_d56 --routes <json> --no-pair-audit

# 逐交叉点 CSV（可选）
.venv\Scripts\python.exe -m four_side_1024.d56.validate_d56 --run-dir <dir> `
    --write-crossings scratch\validate_crossings.csv

# 口径敏感性分析（可选）：legacy 为权威口径；--compare-exact 额外给出 exact 口径违规清单
.venv\Scripts\python.exe -m four_side_1024.d56.validate_d56 --run-dir <dir> --compare-exact
```

退出码：`passed==true` 为 0，否则 1。`--run-dir` 默认要求 `routes.json` 含 1024 条记录
（`--expect-route-count` 可覆盖）。端点身份由 `four_side_1024.inputs.load()` 重建；
若给定的是不含端口身份的 `routes_geometry.json`，会自动从同目录 `routes.json` 按 `route_id` 补齐。
`status:"routed"/"failed"` 混排的 routes.json 可直接审计：failed 路线跳过几何审计但计数
（`failed_status_count`、`failed_status_route_ids`），routed 路线逐条检查 D56 与路线间间距。

**口径选择**：`--policy legacy`（默认，权威，与 `conflicts.py` 一致）与
`--policy exact`（旧快速索引的“整对 primitive 交叉即整对豁免”语义，仅用于报告敏感性分析，
不作为验收口径）。`--compare-exact` 在 legacy 权威结果之外附带 `exact_policy_violations`。
`--routes` 还直接接受引擎 checkpoint（`{"accepted":[...], "failed":[...]}` 这种分区格式），
因此 `routes_checkpoint.json` 一出现即可先做预检，无需等最终 `routes.json`。

## 2. 单路线 D56 检查（9 项，均独立实现）

| # | 检查项 | 口径/容差 | 失败错误码前缀 |
|---|---|---|---|
| 1 | 只正交直线 | 每条 line `min(|dx|,|dy|) <= 1e-9` | `diagonal_line:` |
| 2 | 圆弧半径固定 | `|radius-5.0| <= 1e-9` | `arc_radius:` |
| 3 | 无 F56 自由弯角 | 每弧 `|abs(sweep)-pi/2| <= 1e-9`，或原公式短 S 成对（见 §3） | `short_s_unpaired_arc:` / `short_s_pair_invalid:` |
| 4 | 弧参数与端点解析一致 | `center+R*(cos a,sin a)` 与 p0/p1 差 `<1e-7` | `arc_endpoint_inconsistent:` |
| 5 | 位置连续 | 相邻图元连接点距 `<1e-7` | `position_discontinuity:` |
| 6 | 切向连续（G1） | 相邻图元端点切向向量差 `<1e-7` | `tangent_discontinuity:` |
| 7 | 起终点固定 | `prims[0].p0==source.routing_xy`、`prims[-1].p1==target.routing_xy`（`<1e-7`） | `start_endpoint_mismatch` / `end_endpoint_mismatch` |
| 8 | 出入射方向 | 首段切向==source inward、末段切向==-target inward（`<1e-7`） | `start_direction_mismatch` / `end_direction_mismatch` |
| 9 | layer=0 / 板界 / 自交自重叠自间距 | 每个图元 `layer==0,z==0`；宽 0.05 描边后落在 `[0,150]^2`（容差 1e-8）；自交/自重叠（相邻仅允许共享端点）；非相邻段（沿线弧长间隔 > 2*clearance）中心距 `<0.175` 拒绝 | `nonzero_layer:` / `board_out_of_bounds:` / `self_intersection:` / `self_overlap:` / `self_spacing:` |

任何一条路线不合法都会写入 `route_errors`（含 `route_id` 与逐项错误码），不会静默跳过。
`status=failed` 的路线不参与几何审计，仅统计数量（`failed_status_count`、`failed_status_route_ids`）。

## 3. 短 S 公式口径（SPEC 歧义记录）

- `wiring_bend_826.py` / `wiring_rect_826.py` 的原始小位移公式实际为：
  `theta = acos(1 - d/(2R))`，每弧纵向行程 `h = R*sin(theta)`，横向行程 `d/2= R*(1-cos theta)`；
  两弧 sweep 为 `+theta` / `-theta`，弧间无直线（原公式 `d<2R` 分支，半径仍为 R=5）。
- SPEC §1 第 3 条写作 "`d = 2*R*sin(theta)`（`0<d<2R`）" 与 "`theta=acos(1-d/(2R))`" 两式互相矛盾
  （联立只在 `d=2R` 成立）。**实现以 `wiring_bend_826.py` 与 `legacy_geometry.py` 的实际语义为准**：
  短 S 对总横向位移 `d = 2R(1-cos(theta)) < 2R`、纵向位移 `2R*sin(theta) = 2h`，
  且 `0 < theta < pi/2`；校验时在配对起点切向坐标系内直接核验这两个位移与 `theta=acos(1-d/(2R))`。
- 接受：两段 R=5、等 `|sweep|`、反向、弧间直线长度 `<1e-7` 且位移关系成立的短 S 对。
- 拒绝：单段非 90° 弧、3 段及以上非 90° 弧链、正负不等角/同号对、弧间存在可见直线、
  半径缩为 `d/2`、任意角度（不满足原公式位移）的两段弧。

## 4. 路线间精确审计（口径与 `conflicts.py` 一致，独立实现）

- 中心线最小距离 `clearance = width+edge_gap = 0.05+0.125 = 0.175 mm`（数值容差 1e-8）。
- 交叉只豁免**交点局部**：沿两条曲线各取弧长区间
  `half = clearance/sin(crossing_angle) + 2*sagitta`，`sagitta=0.0005 mm`。
  窗口外仍需与对方**完整**路径保持 0.175 mm（先"切 A 后对全 B"，再"切 B 后对全 A"，与
  `conflicts.py` 相同，避免把 outside/inside 近失错误豁免）。
- 拒绝：重叠（正长度共线/共圆）、切触（`sin<1e-7` 或交点落在任一路线端点 `1e-7` 内）、
  交叉窗口彼此重叠（保守拒绝）、自交/自重叠/自间距、非相邻段间距违规。
- 允许并记录交叉：交点坐标、锐角角度的 `asin(|cross(t1,t2)|)`。
- 空间粗选：路线精确包围盒距离 `<= clearance+2*sagitta` 的候选对；原始图元对再用精确包围盒剪枝。
- 交叉角直方图分组：`0-1,1-5,5-10,10-20,20-30,30-45,45-60,60-75,75-90`（度，左闭右开，
  最后一组含 90）；`<10°` 计数为 `small_angle_crossing_count`。
- `min_non_crossing_centerline_mm`：候选对中**无交叉且合法**路线对的最小精确中心线距离。

### 违规清单字段（`violations`）

逐条给出（不是只给总数）：

```json
{"route_a": 7, "route_b": 9, "kind": "spacing", "kinds": ["spacing"],
 "distance_mm": 0.1, "x": 0.0, "y": 0.05}
```

- `kind` ∈ `spacing | overlap | touch | crossing_window_overlap`；
- `kinds` 为该违规对同时命中的全部类别（兼容旧字段）；
- `distance_mm` 为最近中心线距离（`spacing` 才有意义；其他类别为 null 或 0）；
- `x, y` 为违规最近点的代表位置（mm），可直接用于报告/热图定位。

对应聚合计数：`spacing_violation_pairs`、`overlap_pairs`、`touch_pairs`、
`crossing_zone_overlap_pairs`、`crossing_window_overlap_pairs`（后两者同值，前者为历史命名）、
`violation_pair_count`（去重后的违规路线对数）。

### 口径敏感性（可选 `--policy exact` / `--compare-exact`）

`exact` 口径 = 旧快速索引语义：**一对 primitive 只要精确相交就整对豁免间距检查**，
不相交的 primitive 对按完整几何距离检查（不切交叉窗口）。它与 legacy 口径的差异是双向的：
弧/浅角交叉处 legacy 的局部窗口可能欠豁免（exact 更宽松），而交叉窗口内相邻图形
（非交叉 primitive 对）legacy 会豁免、exact 会报出。因此 exact 结果只作报告敏感性分析：
本机实测 80 条历史 D56 基线在 legacy 下 0 违规，在 exact 下会报出 20 对 `spacing`
（均为窗口内相邻图形的近失）；真实 1024 条运行可用 `--compare-exact` 量化引擎
若采用旧索引口径会漏掉多少 legacy 违规。

### 与 `conflicts.py` 的等价性证据（不是只信寻路器）

`outputs/four_side_1024_single_layer_v1/routes_geometry.json` 的 526 条自由曲线（F56/Dubins）
不经过 D56 单路线过滤、直接跑本审计器，与参考 `statistics.json` 逐项一致：

| 指标 | 参考 statistics.json | 本独立审计 |
|---|---|---|
| crossing_count | 98197 | **98197** |
| [1,5) / [5,10) / [10,20) / ... / [75,90] | 76 / 951 / 4981 / 7986 / 16930 / 20543 / 21287 / 25443 | **完全一致** |
| small_angle(<10°) | 1027 | **1027** |
| spacing/overlap/touch/zone 违规 | 0 | **0** |

## 5. 输出 JSON 字段

必需字段：`passed, route_count, errors, violations, crossing_count, crossing_angle_histogram,
min_non_crossing_centerline_mm, checks`。此外还输出
`policy_used, routed_count, failed_status_count, failed_status_route_ids, d56_checked_count,
d56_passed_count, d56_failed_count, checks_total, route_errors,
self_intersections, self_overlaps, self_spacing_violations,
radius_violations, boundary_violations, diagonal_line_violations, free_or_short_s_arc_violations,
crossing_pair_count, small_angle_threshold_deg, small_angle_crossing_count,
spacing_violation_pairs, overlap_pairs, touch_pairs, crossing_zone_overlap_pairs,
crossing_window_overlap_pairs, violation_pair_count, candidate_pair_count,
pair_audit_runtime_seconds, runtime_seconds, policy, methods`；
使用 `--compare-exact` 时追加 `exact_policy_violations, exact_policy_violation_count,
exact_policy_spacing_violation_pairs, exact_policy_note`。
`checks` 为每项检查通过路线数（`checks_total` 为实际执行该项检查的路线数）。

## 6. 测试套件与实测结果（2026-10-19 本机实测）

套件：`four_side_1024/d56/tests_d56/`（`conftest.py` + `d56_helpers.py` + 8 个测试文件）。

```powershell
.venv\Scripts\python.exe -m pytest four_side_1024\d56\tests_d56 -v
```

实测：**84 passed, 1 skipped in 18.10s**
（skip 的是真实 `outputs/four_side_1024_d56_optimized/routes.json` 验收用例——该产物尚未生成；
生成后自动启用，一次跑完 1024 条全量独立审计并断言 `passed` 与 <120 s。）
另有 3 个 `scratch/outputs_dryrun/` 集成用例（outputs-builder 的 SPEC schema 干跑产物），
当前该产物存在，实测通过。

| 回归对象 | 结果 |
|---|---|
| `outputs/four_side_1024_legacy_two_branch_v2/routes_geometry.json`（80 条 D56 基线） | **80/80 通过**单路线检查；独立 pair 审计 **crossing_count=1141**、直方图与参考 `statistics.json` **完全一致**、0 违规、最小非交叉中心距 0.175 mm |
| `outputs/four_side_1024_single_layer_v1/routes_geometry.json`（526 条自由曲线） | **494/526 判为不合规**（`diagonal_line`/`short_s_unpaired_arc` 等 F56 特征）；其余 32 条本身是**单段正交直线**，属于 D56 合法退化情形，故通过。检查器确实能识别 F56 几何 |
| outputs-builder 干跑产物 `scratch/outputs_dryrun/out80/routes.json`（SPEC schema，1024 身份：80 routed + 944 failed） | `--run-dir` 模式 **passed=true**：80/80 routed 通过 D56；944 条 failed 仅计数；crossing_count=1141 与同目录 `statistics.json` 一致；0 违规 |
| 现有 legacy 回归 `python -m pytest tests -q`（只读，未改任何现有代码） | **62 passed**（108.94 s） |
| 短 S 反向用例 | 半径缩为 d/2、角不等/同号对、3 弧链、弧间可见直线、非原公式位移均被逐项拒绝 |
| 反向用例 | 斜线、R=4.9/5.1、任意角单弧、切向断裂、位置断裂、端点偏移、方向反向、layer=1、越界、自交、自重叠、自间距、0.1 mm 间距对全部逐项报错 |
| 正向用例 | `legacy_geometry.opposite/adjacent` + 四边刚体变换生成的全部 6 个有序边对（含邻边单 L 与三弯接口）均通过 |

性能实测（本机）：

| 场景 | 实测 |
|---|---|
| 1024 条合成正交路线的全量独立审计（512 竖 × 512 横 = 262144 个 90° 交叉，即每个候选对都要端到端审计） | **8.31 s**（预算 120 s；测试内断言） |
| 1024 条单路线 D56 检查 | **0.03 s** |
| 526 条/98197 交叉的完整 pair 审计（等价性验证用，绕过 D56 过滤） | **8.89 s**（crossing_count=98197 与参考一致） |
| 80 条历史 D56 基线完整 CLI（单路线 + pair 审计） | **0.21 s**（内部计时 0.08 s） |
| 80 条历史 D56 基线 exact 口径敏感性（`--compare-exact`） | 20 对 `spacing`（均为窗口内相邻图形近失；legacy 权威口径为 0） |

> 注：Lead 只需在收到优化运行的 `routes.json`（或 checkpoint `routes_checkpoint.json`）后运行 §1
> 第一条命令；若中途只有 checkpoint，可先用 `--routes <checkpoint>`（需含 `source_endpoint/
> target_endpoint/primitives`，或用同目录 routes.json 补齐身份）做预检。

## 7. 已知边界

- 本校验器验证**平面几何合法性**，不认证光学交叉/弯曲的插入损耗、串扰或可制造性。
- 交叉窗口豁免与 `conflicts.py` 相同，是几何验收口径，不是光学交叉单元设计。
- 真实 1024 条优化运行验收需等 Lead 产出 `routes.json` 后执行 §1 第一条命令；
  坏路线会逐条给出 `route_id` 与具体错误码，失败路线只计数不审计。
