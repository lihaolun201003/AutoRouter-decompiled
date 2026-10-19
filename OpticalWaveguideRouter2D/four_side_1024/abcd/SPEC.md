# ABCD 实验共享契约（SPEC v1）

本文件是 `four_side_1024/abcd/` 包的公共契约。所有写入者必须遵守；任何变更必须记录在 §9 变更记录。

代码目录：`OpticalWaveguideRouter2D/four_side_1024/abcd/`
交付目录：`OpticalWaveguideRouter2D/outputs/four_side_1024_v1_v2_abcd/`
总报告：`<project root>/docs/reports/four_side_1024_v1_v2_abcd.md`

## 0. 绝对不变项（不得修改）

| 项 | 值 |
|---|---|
| 基板 | 150 x 150 mm，原点左下，x/y 单位 mm |
| 接头 | 四边各 16 个，共 64 个，每个 2 行 x 16 列 = 32 通道 |
| 端点坐标 | `four_side_1024.inputs.load(path)` 的 `routing_xy`（`virtual_unfolded`）；每个 CSV 固定后不得重分配端点 |
| 连接数 | 1024（2048 个端点各用一次） |
| 层 | 全部图元 `layer=0`，单层 |
| 最小弯曲半径 | R = 5.0 mm（圆弧半径必须恰为 5.0） |
| 波导宽度 | 0.05 mm |
| 非交叉边缘间距 | 0.125 mm → 中心线最小距离 clearance = 0.175 mm |
| 弯曲模型 | D56：正交水平/竖直直线 + 固定 R=5 的 90° 圆弧 + 原 AutoRouter 小位移短 S（两段 R 弧，`theta=acos(1-d/(2R))`） |
| 禁止 | F56 自由弯角、斜线、Dubins、三维、移动端点、缩小半径、放宽间距 |

旧包 `four_side_1024/d56/`（历史 467 结果与校验器）、旧 256/512、`legacy_adapter` **不得修改**（唯一例外：`d56/index.py` 与 `d56/validate_d56.py` 按 §2 追加 `strict` 口径，历史 `exact`/`legacy` 行为必须逐位保持）。
历史交付 `outputs/four_side_1024_d56_optimized/` **不得覆盖**。

拓扑说明：V1 与 V2 是两个不同连接拓扑，比较二者属于**拓扑实验**；在同一拓扑下比较 ABCD 才是**算法实验**。V2 是实验拓扑，不是导师确认的最终需求。

## 1. 两种连接拓扑（输入，只读）

| 名称 | 路径 | SHA256 |
|---|---|---|
| V1 | `C:\Users\lihao\Desktop\optical_1024_multitomulti_connectivity_v1.csv` | `0ecce47109f9223e8407928c423ad5d9272186938cc267877a6158936e0e428b` |
| V2 | `C:\Users\lihao\Desktop\optical_1024_multitomulti_connectivity_v2_symmetric.csv` | 由 `abcd/connectivity.py` 计算并写入 `connectivity/validation.json` |

## 2. 严格几何验收口径 `crossing_policy='strict'`（Phase 2 核心，两处实现必须一致）

历史三种口径：

- `legacy`：交叉窗 `half = clearance/sin(angle) + 2*sagitta`（仅对直线精确；弧参与时**欠豁免**），窗外做精确距离复检。
- `exact`：相交的整对 primitive **整体豁免**（历史 467 的交付口径，过于宽松）。
- **`strict`（本次新主口径）**：只豁免"真正横向交叉的局部必要区域"，定义如下。

### 2.1 单对路线 (A,B) 判定（与 `d56/index.py` 和 `d56/validate_d56.py` 一致）

记 clearance c = 0.175，sagitta = 0.0005，**violation limit `lim = c − 1e-7`**（数值判定门限，两处实现必须相同），sine 门限 `sin(5°)`（D56 最小交叉角），max_half_window = 4.0 mm，窗长容差 `|h−h*| <= 1e-5`。

对每对 primitive (a,b)（先 bbox 距离粗筛）：

1. **重叠**（共线/共圆正长度重合）→ 违规 `overlap`。
2. **无交点**：若精确最小中心线距离 < lim → 违规 `spacing`。
3. **交点 > 1** → 违规 `double_cross`。
4. **交点 = 1**（参数 sA 沿 A、sB 沿 B 的弧长）：若 sine < sin(5°)（相切/近平行）或交点落在任一路线端点 1e-7 内 → 违规 `tangent_touch` / `endpoint_touch`。
5. **交叉点分组**：几何坐标相差 < 1e-6 的交叉点视为同一交叉点（D56 中常见于"一路线的 line/arc 连接点恰好落在另一路线的 primitive 上"），合并为一组。每组产生一个窗口。
6. **精确局部交叉窗（每组）**：对该组内每个 primitive-pair 记录，对交点两侧各求
   `h* = 满足 dist(a(sA±h), b) == lim 的最小 h >= 0`（对**该记录的 partner primitive** 度量；沿整条路线弧长度量，允许跨 primitive 连接处延伸），
   求解要求 |h − h*| <= 1e-5。组窗口半宽取组内记录的最大值（并集）。
   实际豁免半宽 `h = h* + 2*sagitta`（1 µm 数值容差，保证窗外边界距离 >= lim + 约 1 µm·sinθ > lim，使两处实现稳定一致）。
   - 若某侧在 h 达到 max_half_window=4.0 mm 时仍未达到 lim → 违规 `crossing_window_excessive`（两曲线在 lim 带内长距离伴行，不构成真正横向交叉）。
   - 若窗口搜索先到达**路线端点**（路线在带内结束），窗口截断在路线端点，不算违规。
   - 两条正交直线（axis-aligned line × axis-aligned line）的交叉：sine = 1，窗半宽解析等于 `c + 2*sagitta`（精确解，无需数值搜索）；且其窗外区域可证明 >= c（沿一条直线到另一条直线的距离恰为 |Δs|），**免做窗外复检**。
7. **窗互叠**：同一对路线上，**不同交叉点组**的窗口弧长区间两两不得重叠（A 侧、B 侧分别检查）→ 违规 `crossing_window_overlap`。同一组的窗口不参与互叠检查（它们本来就是同一交叉点）。
8. **窗外严格间距（双向）**：对每组的窗口，在 A 侧把路线 A 在该窗口内的一段剪掉（跨多个 primitive 时逐段剪），剩余每一段与**本组的 partner primitive** 求精确距离；任何 < lim → 违规 `spacing`。B 侧同理。
   说明：不相交的 primitive 对已在第 2 步完整检查；相交的 primitive 对必然属于某个组并已按本步骤复检，因此无需再对非 partner primitive 重复检查。
9. 允许并记录：交叉点、交叉角（`angle_deg = asin(sine)`）、窗口长度（A 侧、B 侧）。

**说明**：`strict` 比 `exact` 严格（整对豁免被替换成最小必要局部窗），比 `legacy` 精确（窗按真实弧几何求解，不再 `clearance/sin` 直线近似）。所有半径/宽度/间距/层/端点约束不变。

### 2.2 两处实现（必须独立，不得互相 import）

| 位置 | 角色 | 要求 |
|---|---|---|
| `four_side_1024/d56/index.py` | 路由器判定（增量空间哈希索引） | 新增 `crossing_policy='strict'`；`exact`/`legacy` 行为不变 |
| `four_side_1024/d56/validate_d56.py` | **authoritative 独立校验器** | 新增 `policy='strict'`；不 import `conflicts.py`/`index.py` |

交叉验证：对同一批路线文件，两者对**每一对路线**的合法性判定必须完全一致（`abcd/crosscheck_strict.py` 输出 `mismatch=0`）。若不一致，以 `validate_d56.py` 的几何为准并修正 `index.py`。

### 2.3 三口径对照

- 主口径：`strict`（本文交付）。
- 敏感性：`exact`（历史 467 口径）、`legacy`（历史近似），用于说明口径影响，不作为交付验收。

## 3. 实验矩阵（8 组，全部全量 1024 条）

| 实验 | 拓扑 | 算法 |
|---|---|---|
| V1_A | V1 | A 对边优先 |
| V1_B | V1 | B 邻边优先 |
| V1_C | V1 | C 四边轮流混合 |
| V1_D | V1 | D 全局联合候选优化 |
| V2_A | V2 | A 对边优先 |
| V2_B | V2 | B 邻边优先 |
| V2_C | V2 | C 四边轮流混合 |
| V2_D | V2 | D 全局联合候选优化 |

算法定义固定（不得在拓扑间偷换）：

- **A 对边优先**：先 NS、EW，再 NE、ES、SW、WN。基本顺序 `NS→EW→NE→ES→SW→NW`；组内顺序可优化但必须对 V1/V2 用同一设定。
- **B 邻边优先**：`NW→EN→SW→ES→NS→EW`（历史 D56 最优顺序，完整保留 D56 候选族与冲突约束）。
- **C 四边轮流**：按 N、E、S、W 轮流。每条连接唯一归属一个"当前边"（取 source side），据此入队，**绝不重复布线**。每边队列同时含指向对边与两个相邻边的连接。每轮从当前边取 batch 条，然后轮换。必须试验：顺时针/逆时针、4 个起始边、至少 2 种 batch。选择规则：以 V1 上的 C 消融结果按（布通数, 总长度, 交叉数）选出一套 C 设计，**该设计同时用于 V1 与 V2**（不得按拓扑调参）。
- **D 全局联合**：不得只重排队列。必须：(1) 为全部 1024 条连接生成多条 D56 候选路径；(2) 用精确 `strict` 判定建立候选间冲突关系（可惰性/分块建立，须说明）；(3) 整体选择最大兼容子集（贪心 + 多起点）；(4) **LNS/成组 rip-up**：把已布通的多条路线与失败路线成组释放，联合重选一组候选（真正的多路线联合替换），接受准则为分层目标（布通数 → 几何风险 → 交叉/小角 → 总长 → 弯曲 → 规整/对称）。预算内保存当前最好解。

公平性：所有 8 组使用同一几何、同一 `strict` 口径、同一 D56 候选族与生成原则、同一候选评价预算上限（`--eval-budget`）、同一墙钟上限、固定随机种子（`--seed`）、同一 checkpoint 策略。D 额外报告"等预算"（预算 = A/B/C 中最高的实际评价次数）与"扩展预算"（全额上限）两次结果。

## 4. 目录与文件契约

```text
outputs/four_side_1024_v1_v2_abcd/
  connectivity/                     # Phase 1
    validation_v1.json validation_v2.json
    symmetry_v2.json                # 接头级旋转/镜像对称性分析
    diff_v1_v2.csv diff_v1_v2.md    # 差异表
    connectivity_v1.png connectivity_v2.png
    diff_heatmap.png
  V1_A/ V1_B/ V1_C/ V1_D/ V2_A/ V2_B/ V2_C/ V2_D/
    config.json            # 完整配置（拓扑、算法、种子、预算、口径）
    routes.json            # SPEC 路由文件（§5，1024 条身份全在，成功含解析几何）
    failed_routes.json     # 失败路线及分类/阻挡统计
    statistics.json        # 全部指标（§6）
    audit_strict.json      # 独立校验器 strict 口径结果（authoritative）
    audit_exact.json       # 敏感性
    audit_legacy.json      # 敏感性
    routing_all.png routing_all.svg routing_all.gds
    by_pair_NS.png ... (可选) routing_detail.png
    run.log                # 带时间戳真实日志
    CHECKPOINT.json        # 增量 checkpoint（算法内部状态摘要，可 resume）
  comparison/
    all_metrics.csv all_metrics.json
    abcd_layout_compare.png      # ABCD 四联通图并排（同坐标/线宽/配色）
    abcd_layout_compare_v2.png
    v1_v2_same_algo_compare.png  # V1/V2 同算法并排（4 对）
    metric_bars_*.png
    c_sweep.csv / c_sweep.json   # C 消融
    d_budget_compare.json        # D 等预算 vs 扩展预算
    strict_audit_summary.json
```

`routes.json` 必须与 `d56/SPEC.md` §3.1 兼容（`schema: four_side_1024_d56_optimized_routes_v1`），这样 `validate_d56.py` 可直接审计。必含字段：
`route_id, status('routed'|'failed'), relation, pair, source_side, target_side, source_endpoint, target_endpoint, layer=0, length_mm, bend_count, primitives[]`；
失败记录含 `reason, evaluated, rejection_counts, blockers`。
`statistics.json` 由 `abcd/metrics.py` 从 primitives 重算，禁止直接抄路由引擎自报数。

## 5. 指标定义（`abcd/metrics.py` 输出，命名固定）

- `routed, unrouted, routing_rate = routed/1024`
- `opposite_routing_rate, adjacent_routing_rate`；`by_pair.{NS,EW,EN,ES,SW,NW}.routing_rate`
- `mean_length_mm, max_length_mm, total_length_mm`
- `mean_bend_count, total_bends`
- `crossing_count, crossing_count_density_per_mm2, crossing_angle_histogram, small_angle_crossing_count`（<10°，同时报 <5°）
- `spacing_violation_pairs, overlap_pairs, touch_pairs, crossing_window_overlap_pairs, self_intersections, radius_violations, boundary_violations, diagonal_line_violations, free_arc_violations`（后三类必须为 0）
- `candidate_evaluations, runtime_seconds, evals_per_second, peak_memory_mb`
- 规整度：`mean_straight_fraction`（直线长度/总长）、`mean_turns`、`mean_min_gap_mm`（与其他路线的最近中心距均值）、`crossing_grid_peak`（5mm 网格最大交叉密度）、`track_band_score`（平行段落在 0.175 整数倍邻接带的条带规整度）
- 对称性（按拓扑）：`symmetry.{rot90,rot180,mirror_x,mirror_y,diag}.routed_pair_fraction` 与 `shape_match_fraction`（拓扑置换下双方都已布通、且一方路径经变换与另一方 Hausdorff ≤ 0.05 mm 的比例）
- `pareto`: 布通数-总长-交叉的分层目标值（不得为美观牺牲布通率）

## 6. 可视化契约

- 所有整板图：同一坐标范围 [0,150]^2（含接头标注区 pad），同一 figsize/dpi，线宽一致，配色按边对固定（沿用 `d56/plots_d56.py` 的 palette），标题必须标注**实际布通数量/1024**与实验名。
- 必须输出 PNG（200 dpi）+ SVG（矢量，sagitta ≤ 0.01 mm 离散）+ GDS（单层 layer 0）。
- `comparison/` 图必须用相同坐标比例、线宽、着色方式，便于直接肉眼比较。

## 7. 代码所有权（避免写冲突）

| 路径 | 所有者 |
|---|---|
| `abcd/SPEC.md`, `abcd/strategies.py`, `abcd/d_lns.py`, `abcd/run.py` | Lead |
| `d56/index.py`（strict 追加） | Lead |
| `abcd/connectivity.py`, `abcd/tests_abcd/test_connectivity.py`, `outputs/.../connectivity/` | connectivity |
| `d56/validate_d56.py`（strict 追加）, `abcd/crosscheck_strict.py`, `abcd/tests_abcd/test_strict_policy.py` | validator |
| `abcd/metrics.py`, `abcd/plots.py`, `abcd/export.py`, `abcd/tests_abcd/test_metrics.py`, 各实验 `*.png/svg/gds/statistics.json`, `outputs/.../comparison/` | viz |
| 总报告 | Lead（可邀请各 owner 提交小节） |

**任何人不得修改他人所有权文件**；需要改动时通过消息请求 owner。旧包（`d56/` 除上述两个文件、`tests/`、`legacy_*`、256/512 输出）一律不改。

## 8. 预算与可复现

固定随机种子（默认 `seed=20261019`）；每实验 `--eval-budget`（候选 vs 已布解判定次数）与 `--time-budget` 秒上限；checkpoint 每 `--checkpoint-every` 次评价落盘一次；预算耗尽时保存当前最好解并标记 `budget_exhausted=true`。禁止无限运行。

## 9. 变更记录

- v1（Lead，2026-10-19）：初始契约；确立 `strict` 口径数学定义、8 组实验矩阵、checkpoint 兼容 d56 SPEC、指标与目录契约、代码所有权。
