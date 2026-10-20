# 五层 2.5D 实验复现说明（REPRODUCE_25D.md）

> 本文件由 `four_side_1024/fsd25d/summarize25d.py` 自动生成，重新运行该脚本会覆盖。
> 输入（冻结 2D 输出、`routes_25d.json`、validation 输出）一律只读；本脚本只写 `summary/` 与本文件，不修改任何路线数据。

- 生成时间（UTC）：2026-10-20T05:26:31Z
- 数据根目录：`outputs/four_side_1024_v2_25d_v01`
- 项目根目录：`C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D`

## 1. 环境

| 项 | 值 |
|---|---|
| 操作系统 | Windows（PowerShell） |
| Python 解释器 | `C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\.venv\Scripts\python.exe` |
| Python 版本 | 3.10.11 |
| 项目根目录 | `C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D` |
| 拓扑/连接 CSV SHA256 | `A: 49dd9e89c4ea506d04638ae34eb06a0d8163d479de80869804c881ee1c43915e`, `B: 49dd9e89c4ea506d04638ae34eb06a0d8163d479de80869804c881ee1c43915e` |

## 2. 冻结输入（只读，不得修改）

### 2.1 2D 基线（方案 A / B）

| 方案 | 平面 | 文件路径 | 布通 | 文件 SHA256 | CSV SHA256 |
|---|---|---|---:|---|---|
| A | z1 | `outputs/four_side_1024_v2_candidate_rr_v01/planes/V2/BEST/z1/routes.json` | 508 | `1e16caba9deb44dd98a80b3fbd0f79ec55a83d37a040f1ed9a58db11edd931b4` | `49dd9e89c4ea506d04638ae34eb06a0d8163d479de80869804c881ee1c43915e` |
| A | z2 | `outputs/four_side_1024_v2_candidate_rr_v01/planes/V2/BEST/z2/routes.json` | 244 | `8398401a34c03b533a5941f76d7bdc01cff9ac744bb0983f95c39b9d870b1f2a` | `49dd9e89c4ea506d04638ae34eb06a0d8163d479de80869804c881ee1c43915e` |
| B | z1 | `outputs/four_side_1024_v2_ortho90_v01/planes/V2/ORTHO90/z1/routes.json` | 128 | `343fa1431a0fc3e32f5079777bdff73aefe99a2a3c0837c3f812e77185dde44c` | `49dd9e89c4ea506d04638ae34eb06a0d8163d479de80869804c881ee1c43915e` |
| B | z2 | `outputs/four_side_1024_v2_ortho90_v01/planes/V2/ORTHO90/z2/routes.json` | 134 | `4f6b050024c5b4a656c37de8526fd8879c0b3c9a51db0b07f866966f39424fcd` | `49dd9e89c4ea506d04638ae34eb06a0d8163d479de80869804c881ee1c43915e` |

- 方案 A：A_shortS，算法 `BEST`，预期布通 752/1024，根目录 `outputs/four_side_1024_v2_candidate_rr_v01`
- 方案 B：B_ortho90，算法 `ORTHO90`，预期布通 262/1024，根目录 `outputs/four_side_1024_v2_ortho90_v01`

> 基线目录与文件均为冻结产物；本实验只读取，不写回。`_smoke/` 仅为调试样本（B/5、10 条新增），不参与正式统计。

### 2.2 2.5D 数据根目录

| 子目录/文件 | 生成者 | 说明 |
|---|---|---|
| `scheme{A,B}/layers{3,5}/routes_25d.json` | run25d | 完整 3D 路线数据（schema v1） |
| `scheme{A,B}/layers{3,5}/run_summary.json` | run25d | 运行配置与统计 |
| `scheme{A,B}/layers{3,5}/run.log` | run25d | 运行日志 |
| `validation/<scheme>/layers<N>.json` | validate25d | 每个 run 的独立 3D 验收结果 |
| `validation/all_validation.json` | validate25d | 验收汇总（按 run label 跨调用合并） |
| `validation/_smoke/B_layers5.json` | validate25d | smoke 调试样本验收（不参与正式统计） |
| `figures/<scheme>/layers<N>/*.png` | plots25d | 分层平面图、2D 对比图、3D 视图 |
| `comparison/*.png` + `plots_manifest.json` | plots25d | 基线对照、层数效应、抬升统计 |
| `summary/crossing_metrics.json` | extra_metrics25d | 2D 平铺交叉数 vs 实际 3D 交叉数 |
| `summary/` | summarize25d | overview/comparison/layers_effect/failed_analysis |
| `REPRODUCE_25D.md` | summarize25d | 本文件 |

## 3. 几何模型

### 3.1 层高、接口与升降高度

| 层数 | `layers_z_mm` | 接口层 (`z1`/`z2`) | z1 接口 z (mm) | z2 接口 z (mm) | 可能的 `|dz|` (mm) | transition footprint (mm) |
|---:|---|---|---:|---:|---|---|
| 3 | `[0.0, 0.25, 0.5]` | 0 / 2 | 0.0 | 0.5 | 0.250000 | 0.250000 → 6.319612 mm |
| 5 | `[0.0, 0.125, 0.25, 0.375, 0.5]` | 0 / 4 | 0.0 | 0.5 | 0.125000, 0.250000, 0.375000 | 0.125000 → 4.470389 mm; 0.250000 → 6.319612 mm; 0.375000 → 7.736884 mm |

### 3.2 工艺与几何常数

| 常数 | 值 |
|---|---|
| 板面 BOARD_MM | [150.0, 150.0] (mm × mm) |
| 波导宽度 WIDTH_MM | 0.05 mm |
| 边缘间距 EDGE_GAP_MM | 0.03 mm |
| 三维净空 CLEARANCE_MM | 0.08 mm |
| 弯曲半径 RADIUS_MM | 40.0 mm |
| 最小交叉角 MIN_CROSS_ANGLE_DEG | 5.0 ° |
| 同层 2D 交叉策略 | strict |
| 交叉 3D 净空豁免窗口 | ±2.5 mm （仅同层 strict 2D 合法交叉点附近） |

### 3.3 升降 transition（垂直平面内 S 曲线）

- 每条 lifted 路线在 2D 路径的直线段上放置 **两段** transition：接口层 → 旅行层（`travel_layer`）→ 目标接口层；
- 每段 transition 为垂直平面内两段 R=40 mm 圆弧组成的 S 曲线，关于中点中心对称、G1 连续；起终点切向水平且与所在直线段方向一致（方向轴对齐）；
- `theta = acos(1 - |dz| / (2R))`，水平投影 `footprint = 2R sin(theta)`，弧长 `length = 2R theta`，其中 `dz = z1 - z0`；
- 完整三维路径最小曲率半径 = 40 mm（验收要求 ≥ 39.96 mm）；
- flat 段：方案 A（D56）允许轴对齐直线 + R=40 的 90° 弧 + 短 S 弧；方案 B（ortho90）只允许轴对齐直线 + 精确 90°、R=40 的弧；
- 每条 lifted 路线 `n_transitions = 2`；flat 路线 `n_transitions = 0`。

## 4. 复现命令（PowerShell，按顺序执行）

### 4.0 准备

```powershell
cd "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D"
$py = ".\.venv\Scripts\python.exe"
& $py --version   # 需要 Python 3.10.x
```

### 4.1 四个 2.5D 布线运行（run25d，每个约数分钟到数十分钟，取决于机器负载）

```powershell
& $py -m four_side_1024.fsd25d.run25d --scheme A --layers 3 --passes 3 --rr-rounds 2 --budget 400 --flat-probe 12 --rr-targets 64 --rr-rip 2
& $py -m four_side_1024.fsd25d.run25d --scheme A --layers 5 --passes 3 --rr-rounds 2 --budget 400 --flat-probe 12 --rr-targets 64 --rr-rip 2
& $py -m four_side_1024.fsd25d.run25d --scheme B --layers 3 --passes 3 --rr-rounds 2 --budget 400 --flat-probe 12 --rr-targets 64 --rr-rip 2
& $py -m four_side_1024.fsd25d.run25d --scheme B --layers 5 --passes 3 --rr-rounds 2 --budget 400 --flat-probe 12 --rr-targets 64 --rr-rip 2
```

四个 run 相互独立（各写 `scheme{X}/layers{Y}/`，互不覆盖），可按任意顺序串行执行。

- 上面的参数取自**实际交付 run 的 `run_summary.json`**（四个 run 配置一致；任务约定的 canonical 配置为 `--passes 3 --rr-rounds 2 --budget 300`）。

### 4.2 独立三维验收（validate25d）

```powershell
& $py -m four_side_1024.fsd25d.validate25d --root outputs/four_side_1024_v2_25d_v01
# 可选用法：只验部分 run / 指定输出目录 / 关闭端口 CSV 校验 / 单独验 smoke 样本
& $py -m four_side_1024.fsd25d.validate25d --root outputs/four_side_1024_v2_25d_v01 --only schemeA/layers5
& $py -m four_side_1024.fsd25d.validate25d --root outputs/four_side_1024_v2_25d_v01 --out outputs/four_side_1024_v2_25d_v01/validation
& $py -m four_side_1024.fsd25d.validate25d --root outputs/four_side_1024_v2_25d_v01 --no-port-csv --max-violations 500
& $py -m four_side_1024.fsd25d.validate25d --root outputs/four_side_1024_v2_25d_v01 --input outputs/four_side_1024_v2_25d_v01/_smoke/routes_25d.json
```

- 必须在全部 run 完成后执行；缺省 `--root` 即本数据根目录，自动发现存在的 `scheme{A,B}/layers{3,5}/routes_25d.json`；`--only` 过滤单个 run，`--input` 指定单个 routes 文件或目录。
- 输出：`outputs/four_side_1024_v2_25d_v01/validation/<scheme>/layers<N>.json`（每个 run 一个）与 `outputs/four_side_1024_v2_25d_v01/validation/all_validation.json`（按 run label 跨调用合并，smoke 与 4 个正式 run 可共存）。
- 退出码：0 = 所有处理的 run 均 PASS；1 = 有 run 未通过；2 = 没有任何输入/过滤匹配。
- per-run JSON 顶层字段：`passed`、`routed/failed/total`、`failure_reasons`、`crossings{total,by_layer}`、`violations[]`、`violation_kinds`、`counts{9 项}`、`stats{transitions,lifted,flat_parts,total_length_mm,...}`、`min_3d_distance_mm`、`min_3d_distance_excluding_crossings_mm`、`min_3d_distance_including_crossings_mm`、`min_curvature_radius_mm`、`layer_2d`、`runtime_seconds`；summarize25d 消费这些字段生成对照表与验收列。
- summarize25d 会递归扫描 `validation/**/*.json` 并按 scheme/layers 自动匹配，不依赖具体文件名；`all_validation.json` 若只有部分 run 也能被逐条识别。

### 4.3 对照图（plots25d）

```powershell
& $py -m four_side_1024.fsd25d.plots25d --root outputs/four_side_1024_v2_25d_v01
```

- 输出到 `outputs/four_side_1024_v2_25d_v01/figures/<scheme>/layers<N>/`：`layer_<k>.png`（k=0..N-1）、`layers_2d.png`、`view3d.png`、`top_view_by_height.png`；
- 输出到 `outputs/four_side_1024_v2_25d_v01/comparison/`：`baseline_vs_25d_schemeA.png`、`baseline_vs_25d_schemeB.png`、`layers_effect.png`、`lift_statistics.png`、`plots_manifest.json`（图件清单/runs 表/caveats）；
- 缺省不往 run 目录写图；需要与 `routes_25d.json` 放在一起时加 `--in-run-dir`；
- 可选：`--runs schemeA/layers3,schemeA/layers5` 只画指定 run；`--include-smoke` 追加 `_smoke` 调试样本。

### 4.4 额外交叉指标（extra_metrics25d，可选但推荐）

```powershell
& $py -m four_side_1024.fsd25d.extra_metrics25d
```

- 需在四个 run 的 `routes_25d.json` 与 `validation/<scheme>/layers<N>.json` 都存在后运行；读取它们并写 `summary/crossing_metrics.json`。
- 含义：把每个 run 的全部路线“平铺回接口高度”得到一个假设性 2D 布局，用冻结 `fslw` strict 2D pair kernel 统计其交叉总数（`flattened_total`），再与 `validate25d` 的实际 3D 同层交叉数（`actual_3d_crossings`）比较；二者之差 `crossings_avoided` 即抬升/分层消除的交叉数。
- `summarize25d` 会自动读取该文件，把“2D 平铺交叉数 / 消除的交叉数”写入 `overview.json` 与 `comparison_table.md`；文件缺失时这两列为 “—”。
- 注意该指标是**描述性对照**，不作为验收 PASS 判据（PASS 仍只看 validate25d 的 counts 与 min 距离/曲率）。

### 4.5 汇总统计（本脚本）

```powershell
& $py -m four_side_1024.fsd25d.summarize25d --root outputs/four_side_1024_v2_25d_v01
```

### 4.6 一次性顺序执行（可选）

```powershell
$py = ".\.venv\Scripts\python.exe"
foreach ($scheme in @("A", "B")) {
  foreach ($layers in @(3, 5)) {
    & $py -m four_side_1024.fsd25d.run25d --scheme $scheme --layers $layers --passes 3 --rr-rounds 2 --budget 400 --flat-probe 12 --rr-targets 64 --rr-rip 2
    if ($LASTEXITCODE -ne 0) { throw "run25d failed: $scheme/$layers" }
  }
}
& $py -m four_side_1024.fsd25d.validate25d --root outputs/four_side_1024_v2_25d_v01
& $py -m four_side_1024.fsd25d.plots25d --root outputs/four_side_1024_v2_25d_v01
& $py -m four_side_1024.fsd25d.extra_metrics25d
& $py -m four_side_1024.fsd25d.summarize25d --root outputs/four_side_1024_v2_25d_v01
```

### 4.7 调试样本 smoke（可选，不参与正式统计）

```powershell
& $py -m four_side_1024.fsd25d.run25d --scheme B --layers 5 --passes 1 --rr-rounds 0 --budget 300 --limit 10 --out outputs/four_side_1024_v2_25d_v01/_smoke
& $py -m four_side_1024.fsd25d.validate25d --root outputs/four_side_1024_v2_25d_v01 --input outputs/four_side_1024_v2_25d_v01/_smoke/routes_25d.json
```

> `summarize25d` 只汇总 `scheme{A,B}/layers{3,5}` 四个正式目录，`_smoke` 不参与统计；`_smoke` 的验收结果保存在 `validation/_smoke/B_layers5.json`。

## 5. 预期输出目录树

```text
outputs/four_side_1024_v2_25d_v01/
├─ schemeA/
│  ├─ layers3/  routes_25d.json  run_summary.json  run.log
│  └─ layers5/  routes_25d.json  run_summary.json  run.log
├─ schemeB/
│  ├─ layers3/  routes_25d.json  run_summary.json  run.log
│  └─ layers5/  routes_25d.json  run_summary.json  run.log
├─ _smoke/                        # 调试样本（B/5，10 条新增），不参与正式统计
├─ validation/                    # validate25d
│  ├─ A/layers3.json  A/layers5.json  B/layers3.json  B/layers5.json
│  ├─ _smoke/B_layers5.json       # 可选
│  └─ all_validation.json         # 按 run label 跨调用合并
├─ figures/                       # plots25d
│  └─ scheme{A,B}/layers{3,5}/  layer_<k>.png  layers_2d.png  view3d.png top_view_by_height.png
├─ comparison/                    # plots25d
│  ├─ baseline_vs_25d_schemeA.png  baseline_vs_25d_schemeB.png
│  ├─ layers_effect.png  lift_statistics.png
│  └─ plots_manifest.json
├─ summary/                       # extra_metrics25d + summarize25d
│  ├─ crossing_metrics.json        # extra_metrics25d：2D 平铺 vs 实际 3D 交叉
│  ├─ overview.json
│  ├─ comparison_table.md
│  ├─ layers_effect.json
│  ├─ layers_effect.md
│  └─ failed_analysis.json
└─ REPRODUCE_25D.md               # summarize25d（本文件）
```

## 6. 预期结果与验收口径

### 6.1 本次汇总时的实际数据

| 方案 | 层数 | 数据 | 2D 基线布通 | 2.5D 布通 | 新增 | 抬升 | 升降次数 | 实际 3D 交叉数 | 2D 平铺交叉数 | 消除交叉数 | 总长 (mm) | 验收 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A | 3 | 已生成 | 752 | 788 | 36 | 36 | 72 | 87,240 | 93,753 | 6,513 | 119,805.766 | PASS |
| A | 5 | 已生成 | 752 | 820 | 68 | 68 | 136 | 87,279 | 104,076 | 16,797 | 128,895.611 | PASS |
| B | 3 | 已生成 | 262 | 342 | 80 | 80 | 160 | 10,822 | 21,575 | 10,753 | 57,663.260 | PASS |
| B | 5 | 已生成 | 262 | 383 | 121 | 121 | 242 | 11,138 | 34,091 | 22,953 | 68,703.398 | PASS |

### 6.2 独立验收判据（validate25d / SCHEMA_25D.md §4）

- `counts` 中全部计数为 0：structure / port / xy_model / curvature / clearance / layer_2d / self_clearance / board；
- 不同路线之间真实三维中心线最小距离 ≥ 0.08 mm（仅同层 strict 2D 合法交叉点 ±2.5 mm 窗口内豁免）；
- 完整三维路径最小曲率半径 ≥ 39.96 mm（R=40 mm，容差 0.1%）；
- 每层 flat 段作为独立 prepared route 重跑冻结 strict 2D 审计：violations 必须为空；
- `passed = true` 才可写入报告；**不得把 2D PASS 当作 3D PASS**。

### 6.2.1 交叉指标口径（描述性，不参与 PASS 判定）

- **实际 3D 交叉数**：`validate25d` 按层重跑冻结 strict 2D 审计得到的同层合法交叉数之和（真实三维布局）；
- **2D 平铺交叉数**：`extra_metrics25d` 把该 run 全部路线平铺回接口高度后，用冻结 strict 2D pair kernel 统计的假设性 2D 交叉总数；
- **消除的交叉数** = 2D 平铺 − 实际 3D，表示抬升/分层实际消除的交叉量；
- 三者都不改变验收结论；正式 PASS/FAIL 只看 `counts` 全 0 与 min 距离/曲率条件。

### 6.3 复现自检清单

- [ ] 4 个 run 目录均含 `routes_25d.json` + `run_summary.json`；
- [ ] 各 `routes_25d.json` 的 `csv_sha256` 一致（见 §2.1）；
- [ ] `validation/all_validation.json` 中 4 个 run 全部 `passed = true`；
- [ ] `summary/overview.json` 中 `selfcheck.all_runs_present = true`、`selfcheck.all_validations_passed = true`；
- [ ] `summary/comparison_table.md` 四行 A/B × 3/5 完整（无 “缺失”）；
- [ ] `summary/layers_effect.md` 给出“5 层相对 3 层”的净增益结论；
- [ ] `summary/crossing_metrics.json` 存在且 4 个 run 都有 `flattened_total` / `crossings_avoided`；
- [ ] `summary/failed_analysis.json` 单独列出 `no_2d_candidate_at_all` 路线。

### 6.4 调试样本 smoke 的独立验收基线（validate25d，可选）

- 样本：`_smoke/B_layers5`，报告文件：`outputs/four_side_1024_v2_25d_v01/validation/_smoke/B_layers5.json`

| 项 | 值 |
|---|---|
| 验收结论 | PASS |
| routed / failed | 272 / 752 |
| 实际 3D 交叉数（各层求和） | 8,624 |
| 最小真实 3D 距离（排除合法交叉） | 0.105137 |
| 最小真实 3D 距离（含交叉，参考） | 0.000000 |
| 最小曲率半径 mm | 39.9999997 |
| 违规计数 counts | 全部为 0 |
| transitions / lifted / flat_parts | 20 / 10 / 292 |
| 总波导长度 mm | 44,901.880609 |
| 验收耗时 s | 1.52 |

> 该 smoke 基线只用于验证“数据格式 + 独立验收器”链路本身，不参与正式统计。

## 7. 本次汇总时的运行状态

| 方案/层数 | 数据状态 | 布通 | 耗时 s | passes | rr_rounds | budget | flat_probe | limit | min 3D 距离 mm | min R mm | 验收 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A/3 | 已生成 | 788 | 2,295.0 | 3 | 2 | 400 | 12 | 0 | 0.080390 | 39.9999997 | PASS |
| A/5 | 已生成 | 820 | 3,688.8 | 3 | 2 | 400 | 12 | 0 | 0.080390 | 39.9999997 | PASS |
| B/3 | 已生成 | 342 | 649.9 | 3 | 2 | 400 | 12 | 0 | 0.092446 | 39.9999997 | PASS |
| B/5 | 已生成 | 383 | 776.3 | 3 | 2 | 400 | 12 | 0 | 0.091117 | 39.9999997 | PASS |

## 8. 产出文件说明

| 文件 | 生成者 | 内容 |
|---|---|---|
| `summary/overview.json` | summarize25d | 每个 run 的统计 + 对照表字段 + 自检 |
| `summary/comparison_table.md` | summarize25d | A/B × 3/5（+2D 基线）对照表 |
| `summary/layers_effect.json` | summarize25d | 3 层 vs 5 层对比（机器可读） |
| `summary/layers_effect.md` | summarize25d | 3 层 vs 5 层对比（报告可用） |
| `summary/failed_analysis.json` | summarize25d | 失败按原因/方案/平面/层数拆分 |
| `summary/crossing_metrics.json` | extra_metrics25d | 2D 平铺 vs 实际 3D 交叉数（被 summarize25d 读取） |
| `figures/`, `comparison/` | plots25d | 分层平面图、3D 视图、基线对照图 |
| `REPRODUCE_25D.md` | summarize25d | 本文件 |

> 缺失数据策略：任何 run / validation 文件缺失时，相关字段写 `null` 并在 `summary/overview.json` 的 `warnings` 中记录；脚本不 crash、不修改输入。

