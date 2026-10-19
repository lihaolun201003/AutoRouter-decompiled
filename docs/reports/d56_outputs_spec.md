# D56 优化运行输出产物管线（Phase 6b）

本文件说明 `four_side_1024/d56/` 优化运行（1024 通道四边单层 D56）的**输出产物契约实现**：入口、13 个必需文件、`routes.json`/`statistics.json` 字段、独立审计接入、复现命令与 80 条基线 dry-run 实测数字。

## 1. 代码与复现命令

模块（仅新增，未修改任何既有模块）：

| 文件 | 作用 |
|---|---|
| `four_side_1024/d56/outputs_d56.py` | 主管线：读入 `routes.json` → 精确重算几何/统计 → 生成 13 个文件 |
| `four_side_1024/d56/plots_d56.py` | 7 张 PNG、SVG 导出、消融条形图；Agg、dpi=200、英文标签、`aspect='equal'` |
| `scratch/outputs_dryrun/build_dryrun_80.py` | 80 条基线 → SPEC schema 转换 + 真实 CLI dry-run + 产物/统计校验 |
| `scratch/outputs_dryrun/run80/` | dry-run 输入（SPEC schema `routes.json`） |
| `scratch/outputs_dryrun/out80/` | dry-run 输出（13 个文件 + `routes_geometry.json` + `independent_audit.json`） |
| `scratch/outputs_dryrun/dryrun_validation.json` | dry-run 逐项校验报告（56 项检查） |

真实运行（在 `OpticalWaveguideRouter2D` 目录）：

```bat
.venv\Scripts\python.exe -m four_side_1024.d56.outputs_d56 --run-dir outputs\four_side_1024_d56_optimized
```

可分离输入/输出目录（dry-run 使用）：

```bat
.venv\Scripts\python.exe -m four_side_1024.d56.outputs_d56 ^
  --input-dir scratch\outputs_dryrun\run80 --run-dir scratch\outputs_dryrun\out80
```

dry-run 一键复现：

```bat
.venv\Scripts\python.exe scratch\outputs_dryrun\build_dryrun_80.py
```

CLI 参数：`--run-dir`（必需，输出目录，默认也是输入目录）、`--input-dir`（可选，读 `routes.json`/`endpoints.json`/`config.json`/`ablations.json`/`statistics_seed.json` 等输入）、`--routes`（可选，直接指定任意路由载荷文件，如 `routes_checkpoint.json`；仅当 run-dir 尚无 `routes.json` 时逐字节复制过去，已有不同 `routes.json` 时拒绝混用）、`--replace-routes`（仅 checkpoint 预览用：允许覆盖 run-dir 已有的 `routes.json`，便于同一预览目录迭代 checkpoint）、`--run-status {complete,partial_checkpoint}`（覆盖 `statistics.run_status`；缺省从 `routes.json` 顶层 / `algorithm.run_status` 读取，否则按文件名是否含 checkpoint 推断 `partial_checkpoint`/`complete`）、`--audit-only` + `--audit-report <json>`（预检：只做精确重算与独立审计、不写 PNG/SVG/GDS/statistics，`routes.json` 存在则保留，退出码 0/1 表示主口径审计通过/失败；用于最终导出前拦截违规）、`--svg-sagitta-mm`（SVG 折线采样弓高，默认 0.01）。重复运行幂等：覆盖自己的产物，`run.log` 追加不截断。

`--routes` 典型用法（checkpoint 预览，避免污染最终输出目录）：

```bat
.venv\Scripts\python.exe -m four_side_1024.d56.outputs_d56 ^
  --run-dir scratch\preview --routes outputs\four_side_1024_d56_optimized\routes_checkpoint.json
```

同一预览目录换用新 checkpoint 时加 `--replace-routes`。`run_status` 由 `routes.json` 顶层或 `algorithm.run_status` 决定；未显式提供时，源文件名为 `*checkpoint*.json` 推断为 `partial_checkpoint`，否则为 `complete`（最终定稿目录应写入 `run_status=complete`）。

## 2. 13 个必需文件

| 文件 | 内容 |
|---|---|
| `01_connectivity.png` | 1024 条原始 CSV 连接关系（`inputs.phase1` 风格：按 pair 着色 + 64 接头包络） |
| `02_routing_all.png` | 全部成功路线整板图（pair 着色 + 图例，标题含真实成功数 N/1024） |
| `03_opposite_routes.png` | 仅对边路线（NS/EW），标题含 n/512 |
| `04_adjacent_routes.png` | 仅邻边路线（EN/ES/SW/NW），标题含 n/512 |
| `05_crossing_heatmap.png` | 5×5 mm 网格交叉点热图，colorbar + 最密 3 格计数/坐标标注 |
| `06_routing_detail.png` | 2×2 热点放大（自动取最密 4 个 5×5 mm 格），每格标窗口坐标范围与交叉数 |
| `07_strategy_comparison.png` | 有消融表时：左图 success/1024、中图 opposite/adjacent 按 relation 堆叠、右图 `crossing_count`（无交叉数时退化为 runtime）；无消融表时画本次运行关键指标并明确标注 |
| `routing_all.svg` | 手写 SVG 折线（圆弧采样），含板框；1024 条时远小于 5 MB |
| `routing_all.gds` | gdspy 单层（layer=0/datatype=0），宽 0.05 mm，圆弧 sagitta≤0.0005 mm，单位 1e-3 m（1 mm），写后回读校验路径数/层/线宽/UNITS |
| `routes.json` | 全部 1024 条身份（routed/failed）；已存在则**逐字节保留不改**；缺失时按 SPEC 3.1 生成 |
| `failed_routes.json` | 失败路线 + `reason/classification/evaluated/blockers` 等 |
| `statistics.json` | SPEC 3.2 全部字段 + 扩展指标（见 §4） |
| `run.log` | ISO 时间戳真实日志（追加） |

另附（非 13 必需）：`routes_geometry.json`（全部成功路线的解析几何权威副本）、`independent_audit.json`（独立校验器完整报告，可自动调用生成）。

## 3. `routes.json` 输入契约与容错

- 标准输入为 SPEC 3.1 的 `{"schema", "units", "layer", "endpoint_mode", "csv_sha256", "config", "algorithm", "routes":[...]}`；`routes` 为 1024 条记录，成功者含 `primitives`（`line`/`arc`，全部 `layer=0`），失败者含 `reason/evaluated/blockers`。
- 兼容：`routes` 也可直接是 list；`status` 接受 `routed/success/ok/valid` 与 `failed/failure`；geometry 也可来自同目录 `routes_geometry.json`；`endpoints.json`/`connectors.json` 存在时优先读取，否则用 `four_side_1024.inputs.load()` 重建（已验证两条路径）。
- 缺 `routes.json` 但存在 `routes_geometry.json` + `failed_routes.json` 时自动按 SPEC schema 生成 `routes.json`（已实测：生成后 1024 身份、80 routed、交叉 1141 与基线一致）。
- 身份以 `inputs.load()` 的 1024 条 CSV 连接为准；`routes.json` 缺记录会在日志告警并按 failed 身份保留。成功数可 0~1024（0 条成功亦能生成全部 13 个文件，已实测）。

## 4. `statistics.json` 关键字段

SPEC 3.2 必需字段全部输出：`success_count, failed_count, success_rate, by_pair{NS,EW,EN,ES,SW,NW}, by_relation{opposite,adjacent}, mean_length_mm, max_length_mm, total_length_mm, crossing_count, crossing_angle_histogram, small_angle_threshold_deg, small_angle_crossing_count, spacing_violation_pairs, overlap_pairs, self_intersections, radius_violations, boundary_violations, candidate_evaluations, total_runtime_seconds, failure_reason_counts, ablations[], independent_audit{...}`。

扩展字段：`run_status`/`run_status_source`（优先取 `routes.json` 顶层或 `algorithm.run_status`；若来自 `*checkpoint*.json` 文件名则推断 `partial_checkpoint`，否则 `complete`；可用 `--run-status` 覆盖）、`router_reported_statistics`（若 `routes.json` 内嵌 `statistics` 则原样保留，仅作交叉核对，本文件所有指标均从 primitives 重算）；`statistics_seed`（若 run-dir 有 `statistics_seed.json` 则原样嵌入，仅追溯，不参与计算）；`ablations`（原样嵌入消融表：`label/success/success_rate/failed/by_pair/by_relation/mean_length_mm/max_length_mm/total_length_mm/crossing_count/crossing_angle_histogram/small_angle_crossing_count/spacing_violation_pairs/overlap_pairs/radius_violations/boundary_violations/candidate_evaluations/runtime_seconds/note`）；`board_mm/layer/width_mm/edge_gap_mm/min_radius_mm/sagitta_mm`、`min_length_mm/mean_bend_count/max_bend_count/arc_radius_values`、`touch_pairs/crossing_zone_overlap_pairs/self_overlaps`、`orthogonality_violations/d56_sweep_violations`（D56 结构检查，仅供参考，权威判定归独立校验器）、`minimum_checked_non_crossing_centerline_mm`、`routes_with_geometry_errors/geometry_error_counts`、`routed_without_geometry/length_mismatch_count`、`densest_crossing_cells/most_crossed_routes/crossing_pairs_unique`、`candidate_evaluation_breakdown`、`failure_class_counts/failed_by_pair`、`evaluated_routes`、`routing_runtime_seconds/artifact_generation_seconds/runtime_scope`、`gds/svg/figures/artifacts`、`input`（run/input 目录、`routes_json_action`（preserved_in_place / preserved_identical / copied_from_source / replaced_from_source / generated）、`routes_source`、routes.json 与 CSV 的 SHA256）、`audit`（重算来源与局限）、`software`。

**统计不抄输入**：`length_mm` 由 `geometry.length(primitives)` 精确重算（与输入 `length_mm` 差 >1e-6 会记入 `length_mismatch_routes`）；交叉用 `geometry.validate` + `conflicts.ConflictIndex` 精确求交/局部横穿豁免重算，`crossing_angle_histogram` 与历史口径一致（0–1,1–5,…,75–90）。路线间间距的**最终判定**由独立校验器负责。

**双口径**（SPEC 变更记录 v2）：`routes.json.algorithm.crossing_policy`（或顶层/`config` 同名字段）决定 `acceptance_policy`——最终交付用 `exact`，另一口径作为 sensitivity。`independent_audit` 是 acceptance 口径的 validator 结论（`independent_audit.json`），`independent_audit_sensitivity` 是另一口径的结论（`independent_audit_sensitivity_<policy>.json`）。`spacing_violation_pairs`/`overlap_pairs`/`crossing_window_overlap_pairs`/`minimum_checked_non_crossing_centerline_mm` 按 acceptance 口径给出（exact 时取自 validator 数值，`spacing_violation_pairs_source="validator"`），并同时给出 `spacing_violation_pairs_legacy`/`overlap_pairs_legacy`/`minimum_checked_non_crossing_centerline_legacy_mm`（本管线用 `conflicts.ConflictIndex` 重算的 legacy 对照，与 validator `--policy legacy` 数值一致）。`crossing_count` 为本管线从解析几何重算的横向交叉数（在全部合法数据上与 validator acceptance 口径一致），并给出 `crossing_count_validator_main` 供核对。

## 5. 独立审计接入（双口径）

`d56/validate_d56.py` 存在时自动调用两次：**acceptance 口径**（写入 `independent_audit.json`）与 **sensitivity 口径**（写入 `independent_audit_sensitivity_<policy>.json`）。优先 `import four_side_1024.d56.validate_d56` 后调用其 `build_report(run_dir=..., policy=<policy>)`（当前 validator 版本公开入口），失败则回退命令行 `--run-dir <dir> --policy <policy> --output <file>`。结果并入 `statistics.json.independent_audit` / `independent_audit_sensitivity`（`status/passed/attempts/result/…`）。若该模块尚不存在/调用失败，对应 `status` 为 `not_available`/`error` 并注明"待独立审计"，管线不会伪造通过。dry-run（80 条 legacy）时 acceptance=legacy：`passed=true`（validator 独立得到 `route_count=1024, routed=80, crossing_count=1141, violations=0`），sensitivity=exact 亦通过。validator 由队友维护，本管线只调用不修改；其更新后会重新调用最新版本。

## 6. dry-run 实测（80 条 legacy 基线）

输入：`outputs/four_side_1024_legacy_two_branch_v2/`（80 条解析几何 + 944 条失败），转换后 1024 身份写入 `scratch/outputs_dryrun/run80/routes.json`。输出到 `scratch/outputs_dryrun/out80/`。

- 结果：**56/56 项检查通过**，pipeline 约 4.5 s（含双口径 validator 两次调用；Python 3.10.11 / numpy 2.2.6 / scipy 1.15.3 / matplotlib 3.10.9 / gdspy 1.6.13）。- 与基线 `statistics.json` 对照（全部一致）：

| 指标 | 基线（80 条） | 本管线重算 |
|---|---|---|
| success / failed | 80 / 944 | 80 / 944 |
| crossing_count | 1141 | 1141 |
| by_pair success/failed | NS 24/232、EW 0/256、EN 8/120、ES 16/112、SW 32/96、NW 0/128 | 完全一致 |
| by_relation success | opposite 24 / adjacent 56 | 一致 |
| crossing_angle_histogram | 10–20:2、60–75:24、75–90:1115，其余 0 | 完全一致 |
| small_angle(<10°) | 0 | 0 |
| mean/max/total length (mm) | 143.14499504060012 / 281.4539816339745 / 11451.599603248012 | 误差 ≤1e-9（实测 0.0） |
| spacing/overlap/self/radius/boundary 违规 | 0/0/0/0/0 | 0/0/0/0/0 |
| densest_crossing_cells 前 5 | (50,80)=20、(20,140)=18、(40,80)=18、(10,140)=14、(15,140)=12 | 完全一致 |

- 产物校验：7 张 PNG 用 PNG 头解析尺寸 2200×2200 / 2200×2000 / 2000×1800 / 2600×2480 / 2600×1000 等（全部 >0）；SVG 为合法 XML（80 条 path，26.5 KB）；GDS 经 gdspy 回读 80 paths、layer [0]、datatype [0]；并用独立原始字节解析确认 UNITS=1e-3 m（1 mm）、线宽 0.05 mm、图元范围 0–150 mm、无多边形；routes.json 1024 条、其中 routed 80；failed_routes.json 944 条；run.log 带时间戳且追加。
- 分支测试（均通过、已清理临时目录）：0/1024 成功（空图/空 GDS/SVG 仍为合法文件）；输入=输出同目录的 in-place 模式（routes.json 逐字节不变）；缺失 `routes.json` 时自动生成（1024 身份、80 routed、交叉 1141 与基线一致）；`--routes routes_checkpoint.json` checkpoint 预览（routes.json 逐字节复制、`run_status=partial_checkpoint`、二次运行 `preserved_identical` 幂等）；`algorithm.ablations` 或 `ablations.json` 存在时 07 按 success/relation/crossing 三栏出图（3 组配置实测；无消融表时兜底当前运行指标）。
- 额外规模验证（按 526 条自由曲线历史数据，只读输入）：`--input-dir outputs/four_side_1024_single_layer_v1 --run-dir scratch/...` 全管线 28.0 s（精确配对审计约 19.5 s），重算结果与历史 statistics.json 完全一致（success 526/1024、crossing_count=98197、mean/max/total length 159.24492913522238 / 200.68781297946927 / 83762.83272512726、by_pair 全对、违规全 0），SVG 73.7 KB、GDS 143 KB/526 paths、`routes.json` 逐字节保留。该数据集是 F56 自由曲线实验，`independent_audit=passed=false`（494 条 D56 合规失败）属**预期正确**结果——validator 正确区分了 F56 与 D56 几何；D56 优化路线应通过。
- 满规模接入试跑（只读 Lead 的 535/1024 exact-policy 试验 checkpoint）：`--routes scratch/fullE/routes_checkpoint_E_adjacent_first.json --run-dir scratch/...` 全管线 19.4 s、13 文件齐备（02 1.6 MB、05 116 KB、06 910 KB、SVG 152 KB、GDS 371 KB/535 paths）。该 checkpoint 在 legacy 口径下本就有 9518 对间距违规（与本管线重算的 legacy 数完全一致，validator `--policy legacy` 亦为 9518），故 sensitivity=legacy 为 failed 属预期。
- **exact 口径满规模预览**（只读 Lead 的 428/1024 `v2E` checkpoint，本次双口径管线）：全管线 16.0 s，13 文件齐备；`acceptance_policy=exact`（自动取自 `algorithm.crossing_policy`），`success=428`，`crossing_count=48413` 与 validator `--policy exact` 的 48413 **完全一致**；`spacing_violation_pairs=0`（main exact）、`spacing_violation_pairs_legacy=6877`（与 validator legacy 6877 一致）；`independent_audit=passed`、`independent_audit_sensitivity=failed(legacy)`；GDS 428 paths、SVG 140 KB。该形态即最终交付将采用的审计形态。

## 7. 限制与声明

- 全部为 `virtual_unfolded` 二维研究几何：`endpoint_mode` 为理想化平面展开，不代表真实双排 MPO 端口的可制造耦合；`layer=0`、无 z 避让。
- 交叉是"允许并记录"的二维中心线横穿，不是经光学验证的交叉单元；低角度交叉与局部间距仍需工艺评估。
- 数值参数（R=5 mm、宽 0.05 mm、边距 0.125 mm）为初版验证参数，不是最终玻璃工艺规范；产物不是制造发布。
- 管线自身只做产物生成与精确重算；路线合法性/间距的最终结论以 `four_side_1024/d56/validate_d56.py` 独立审计为准。

## 8. 接入探测与口径差异（影响说明）

为在 1024 最终结果出现前暴露集成问题，`scratch/outputs_dryrun/integration_probe.py` 用 Lead 当时在研的 D56 引擎在 24 条子集（NS/EN/SW 各 8 条）上生成 SPEC `routes.json`，并送入真实产物管线。结论与最终口径：

- **集成本身通过**：engine → routes.json → 管线 13 文件 → validator 的链路全部跑通（`d56_*` 单路线检查 23/23 通过，primitive 在 world mm 中往返无损）。
- **发现口径差异**：早期 `d56/index.py::D56Index` 对"横穿图元对"整体豁免，未做 `conflicts.py` 的交叉窗外间距复检；因此 23 条 accepted 路线在 legacy 口径下被本管线精确审计判出 **90 对间距违规**，`validate_d56.py` 也独立判出**恰好 90 对**。几何原因是 R=5 mm 圆弧在 `clearance/sin(angle)` 交叉窗之外的实际间距略小于 0.175 mm（浅角+曲率时短 0.8–13.5 µm），即"历史交叉窗对圆弧欠豁免"的已知近似，而非端点/切向/正交/半径等几何违规。
- **最终口径（Lead, SPEC 变更记录 v2）**：主交付采用 **exact 交叉区口径**（横向交叉精确豁免相交 primitive 对，非相交 primitive 对严格 0.175 mm 复检），legacy 口径作为**同口径敏感性对照**。`validate_d56.py` 以 `--policy exact|legacy` 同时支持两种判定；本管线据 `routes.json.algorithm.crossing_policy` 自动选择 acceptance 口径，并同时输出另一口径的 sensitivity 审计（见 §4、§5）。两口径的布通数/违规数均写入 `statistics.json`，最终报告须同时给出。
- 该探测脚本保留在 `scratch/outputs_dryrun/integration_probe.py`，可随时对新的 checkpoint 重跑，用于尽早暴露 engine/pipeline/validator 三者之间的口径漂移。
- **最终导出流程**：Lead 写入 `outputs/four_side_1024_d56_optimized/routes.json`（唯一权威输入）与 `ablations.json`/`statistics_seed.json` 后，先跑 `--audit-only` 预检（`run.log` 追加、写 `independent_audit.json`，不写其余产物）；仅当 exact 主口径 `independent_audit.passed=true` 且 `violation_count=0` 时才原地跑 `--run-dir outputs/four_side_1024_d56_optimized` 导出其余 12 个文件并重写 `statistics.json`；若预检失败则保留原文件、把违规清单写 `--audit-report` 的 JSON 并报告 Lead。`ablations.json` 由 Lead 生成，本管线只读不覆盖。

## 9. 最终产物实测（1024 通道 D56 优化运行）

输入：Lead 写入的权威 `routes.json`（SPEC schema，1024 身份，**467 routed / 557 failed**，`algorithm.crossing_policy="exact"`，`strategy_label="E_prime_NW_EN_SW_ES_NS_EW"`）＋ 557 行 `failed_routes.json`（保留不改）＋ 10 行 `ablations.json`（只读）。

- **预检**（`--audit-only --run-status complete`）：6.1 s；exact 主口径 `passed=true`、`violations=0`，`crossing_count=57029`，legacy 敏感性 `spacing_violation_pairs_legacy=8919`。
- **正式导出**（原地 `--run-dir outputs/four_side_1024_d56_optimized --run-status complete`）：13.5 s（其中精确配对审计 4.5 s、validator exact 1.5 s、validator legacy 3.4 s）。`routes.json`/`failed_routes.json`/`ablations.json` 逐字节保留（mtime 未变；SHA256 分别 `ce96833a…`、`f4d72ce5…`、`3346ba38…`）。
- **13 个必需文件**（全部生成、可打开）：

| 文件 | 字节 |
|---|---:|
| `01_connectivity.png` | 7,129,468 |
| `02_routing_all.png` | 1,396,954 |
| `03_opposite_routes.png` | 213,096 |
| `04_adjacent_routes.png` | 1,127,460 |
| `05_crossing_heatmap.png` | 111,677 |
| `06_routing_detail.png` | 881,359 |
| `07_strategy_comparison.png` | 160,896 |
| `routing_all.svg` | 153,560 |
| `routing_all.gds` | 373,106 |
| `routes.json` | 1,145,885 |
| `failed_routes.json` | 963,064 |
| `statistics.json` | 77,879 |
| `run.log` | 10,753 |

- **关键统计**（`statistics.json`，全部从 primitives 重算）：`success_count=467`、`failed_count=557`、`success_rate=0.4561`、`crossing_count=57029`（=validator `--policy exact` 独立重算值）、`small_angle_crossing_count=9`（<10°）、`mean/max/total_length_mm=149.561812 / 305.632145 / 69845.366140`、`candidate_evaluations=142058`（引擎上报，见 `router_reported_statistics`）。
  - 边对：NS 28 / EW 25 / EN 128 / ES 43 / SW 115 / NW 128；关系：opposite 53 / adjacent 414。
  - 交叉角直方图：`{"0-1":0,"1-5":0,"5-10":9,"10-20":581,"20-30":1208,"30-45":3129,"45-60":3086,"60-75":1881,"75-90":47135}`。
  - 双口径：`acceptance_policy=exact`、`spacing_violation_pairs=0`、`overlap_pairs=0`、`touch_pairs=0`、`crossing_window_overlap_pairs=0`、`self_intersections/radius_violations/boundary_violations/orthogonality_violations=0`；`sensitivity_policy=legacy`、`spacing_violation_pairs_legacy=8919`（validator `--policy legacy` 同数；Lead 记录的严格历史口径同算法布通数为 72/1024，见 `algorithm.strict_historical_policy_result`）。
  - `independent_audit.passed=true`（exact，467/467 通过 D56 单路线检查）；`independent_audit_sensitivity`（legacy）= failed 且 `violation_count=8919`，属预期敏感性结果；完整 legacy 报告保存于 `independent_audit_sensitivity_legacy.json`（2.1 MB），statistics 内只嵌入计数与 20 条样本。
  - `run_status=complete`（`--run-status` 覆盖）、`run_status_source=cli_override`。
- **产物校验**：7 张 PNG 头解析尺寸 2200×2200 / 2200×2000 / 2000×1800 / 2600×2480 / 3000×1000 等（均 >0）；SVG 合法 XML、467 条 path、153 KB（<5 MB）；GDS gdspy 回读 467 paths、layer [0]/datatype [0]、UNITS=1e-3 m（1 mm）、线宽 0.05 mm、sagitta≤0.0005 mm 离散、无 polygon；`statistics.artifacts` 保存其余 11 个文件的字节数与 SHA256。
- 附注：引擎 `statistics.crossing_count` 上报 59188 与重算/validator 的 57029 差 821，原因是 rip-up 后每条路线放置时刻的 `crossings` 计数未刷新（引擎侧陈旧值）；交付值以精确重算/独立审计的 57029 为准，引擎原值保留在 `router_reported_statistics` 供追溯。

