# R15 实验复现说明（2026-10-20）

所有命令在项目根目录 `OpticalWaveguideRouter2D` 下用 PowerShell 执行：

```powershell
Set-Location "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D"
```

工艺要求：本轮所有平面弯曲与 3D 升降弯曲统一 **R = 15 mm**；R40 历史结果保留在
`outputs/four_side_1024_v2_candidate_rr_v01/`、`outputs/four_side_1024_v2_ortho90_v01/`、
`outputs/four_side_1024_v2_25d_v01/`，本目录只写 R15 数据。

## 0. 环境

- Python：`<project root>\.venv\Scripts\python.exe`（numpy / matplotlib / pytest 已安装）
- 随机种子：`four_side_1024/v2opt/config.py::SEED = 20261019`
- R15 配置：`four_side_1024/r15/profile_r15.py`（apply 后设置
  `FSLW_PROCESS_RADIUS_MM=15`，父进程与 multiprocessing 子进程一致）

## 1. R15 二维 D56（方案 A）

```powershell
# 1.1 z1：NS→EW、x 降序顺序，候选预算 1600，4 轮 R&R
.\.venv\Scripts\python.exe -m four_side_1024.r15.run2d_r15 --scheme A --plane z1 `
  --order ns_ew_xdesc --budget 1600 --rr-rounds 4 --transactions 24 --sizes 1,2,4 `
  --analysis-budget 1600 --reinsert-budget 1600 --rr-time-limit 1200 --workers 5

# 1.2 z2 顺序扫描（每个顺序一个独立 root；本轮 R15 最佳为 round_robin_N_cw 437）
foreach ($order in 'round_robin_N_cw','group_swesnw','csv','global_congestion') {
  .\.venv\Scripts\python.exe -m four_side_1024.r15.run2d_r15 --scheme A --plane z2 `
    --order $order --budget 1600 --rr-rounds 0 `
    --root "outputs/four_side_1024_v2_r15_v01/sweep2d/A_z2_$order"
}

# 1.3 最好顺序继续 R&R
.\.venv\Scripts\python.exe -m four_side_1024.r15.run2d_r15 --scheme A --plane z2 `
  --continue-from outputs/four_side_1024_v2_r15_v01/sweep2d/A_z2_round_robin_N_cw/checkpoints/A_z2_round_robin_N_cw.json `
  --rr-rounds 4 --transactions 64 --sizes 1,2,4,8 --analysis-budget 800 `
  --reinsert-budget 800 --rr-time-limit 1800 --workers 8 `
  --targets-per-round 64 --analysis-targets 128
```

结果：z1 498/512、z2 445/512 → **943/1024**（`planes/V2/A/`、`combined/V2/A/`）。

## 2. R15 二维纯正交 90°（方案 B）

```powershell
# 2.1 z1：NS→EW、x 降序顺序（预算 400，4 轮 R&R）
.\.venv\Scripts\python.exe -m four_side_1024.r15.run2d_r15 --scheme B --plane z1 `
  --order ns_ew_xdesc --budget 400 --rr-rounds 4 --transactions 24 --sizes 1,2,4 `
  --analysis-budget 400 --reinsert-budget 400 --rr-time-limit 1200 --workers 5

# 2.2 z2 顺序扫描（本轮 R15 最佳 round_robin_N_cw 331）
foreach ($order in 'round_robin_N_cw','group_swesnw','csv','group_ensw') {
  .\.venv\Scripts\python.exe -m four_side_1024.r15.run2d_r15 --scheme B --plane z2 `
    --order $order --budget 1600 --rr-rounds 0 `
    --root "outputs/four_side_1024_v2_r15_v01/sweep2d/B_z2_$order"
}

# 2.3 最好顺序继续 R&R（参数同 A z2）
.\.venv\Scripts\python.exe -m four_side_1024.r15.run2d_r15 --scheme B --plane z2 `
  --continue-from outputs/four_side_1024_v2_r15_v01/sweep2d/B_z2_round_robin_N_cw/checkpoints/B_z2_round_robin_N_cw.json `
  --rr-rounds 4 --transactions 64 --sizes 1,2,4,8 --analysis-budget 800 `
  --reinsert-budget 800 --rr-time-limit 1800 --workers 8 `
  --targets-per-round 64 --analysis-targets 128
```

结果：z1 184/512、z2 331/512 → **515/1024**（`planes/V2/B/`、`combined/V2/B/`）。

## 3. 二维组合、独立 strict 验收与 R15 复核

```powershell
.\.venv\Scripts\python.exe -m four_side_1024.r15.run_r15_pipeline --step finalize2d --labels A
.\.venv\Scripts\python.exe -m four_side_1024.r15.run_r15_pipeline --step finalize2d --labels B
# 独立 R15 复核（primitive 级扫描 + 冻结 strict 验证器 + 3D 复核）
.\.venv\Scripts\python.exe -m four_side_1024.r15.validate_r15 --only 2d
```

预期：A=943 PASS、B=515 PASS，全部弧半径 15.000000，0 违规。

## 4. R15 五层 2.5D（A/B 各一次）

```powershell
.\.venv\Scripts\python.exe -m four_side_1024.r15.run25d_r15 --scheme A --layers 5 `
  --budget 400 --passes 3 --flat-probe 12 --rr-rounds 2
.\.venv\Scripts\python.exe -m four_side_1024.r15.run25d_r15 --scheme B --layers 5 `
  --budget 400 --passes 3 --flat-probe 12 --rr-rounds 2
```

`run25d_r15` 把 fsd25d 的 baseline 指向本轮 R15 的
`planes/V2/{A,B}/{z1,z2}`（不使用 R40 布局），层高仍为
`[0, 0.125, 0.25, 0.375, 0.5] mm`（仿真假设）。

## 5. 五层独立 3D 验收、统计、图件

```powershell
.\.venv\Scripts\python.exe -m four_side_1024.r15.validate_r15 --only 25d
.\.venv\Scripts\python.exe -m four_side_1024.r15.stats_r15
.\.venv\Scripts\python.exe -m four_side_1024.r15.plots_r15
```

验收要点（`fsd25d.validate25d`，R15 profile）：

- 完整 3D 路径最小曲率半径 ≥ 15 mm × (1 − 1e-3) = 14.985 mm；
- 平面弧半径 = 15 mm、纯正交只允许 90° 弧；
- 端口高度/切线、板边距、真实 3D 净空 ≥ 0.08 mm、同层 strict 冲突；
- 所有 transition 的 `radius_mm = 15`，θ/footprint/弧长按 R15 公式复核。

## 6. 关键输出与校验

| 文件 | 说明 |
|---|---|
| `final_validation.json` | 2D 组合 strict 验收（A 943 / B 515） |
| `validation/r15_validation_summary.json` | 独立 R15 复核（2D + 25D） |
| `25d/validation/all_validation.json` | 五层 3D 验收 |
| `summary/r15_statistics.md` | 2D/3D 统计表 |
| `summary/r15_comparison_table.md` | R40 vs R15 对照表 |
| `summary/r15_loss_parameters.json` | 损耗参数分类（不做总损耗结论） |
| `comparison/`、`figures/` | 新旧对照图、R15 平面图、5 层 3D 图 |
| `work/incident_r40_worker_contamination/` | 首轮 R&R worker 混入 R40 弧的隔离证据（后已修复重跑） |

复核哈希：

```powershell
Get-FileHash outputs/four_side_1024_v2_r15_v01/planes/V2/A/z1/routes.json,
             outputs/four_side_1024_v2_r15_v01/planes/V2/A/z2/routes.json,
             outputs/four_side_1024_v2_r15_v01/planes/V2/B/z1/routes.json,
             outputs/four_side_1024_v2_r15_v01/planes/V2/B/z2/routes.json,
             outputs/four_side_1024_v2_r15_v01/25d/schemeA/layers5/routes_25d.json,
             outputs/four_side_1024_v2_r15_v01/25d/schemeB/layers5/routes_25d.json -Algorithm SHA256
```

## 7. 本轮最终结果（摘要）

| 方案 | R40 历史 | R15 本轮 | Δ | 验收 |
|---|---:|---:|---:|---|
| 2D D56（Short-S） | 752 | **943** | +191 | PASS（z1 498 + z2 445） |
| 2D 纯正交 90° | 262 | **515** | +253 | PASS（z1 184 + z2 331） |
| 5L 2.5D + Short-S | 820 | **985** | +165 | PASS（抬升 42，transition 84） |
| 5L 2.5D + 纯正交 | 383 | **723** | +340 | PASS（抬升 208，transition 416） |

全部 8 项独立验收（2D A/B 各平面与组合、25D A/B）通过：10 046 条弧半径全部
15.000000 mm（最大偏差 0.0 mm）、500 条 transition 半径 15 mm、0 违规。
R15 关键数据 SHA256（前 16 位）：

| 文件 | SHA256 前缀 |
|---|---|
| planes/V2/A/z1/routes.json | `78168d092a389f86` |
| planes/V2/A/z2/routes.json | `0338d257941d5be2` |
| planes/V2/B/z1/routes.json | `79ef1dafbdfa9e49` |
| planes/V2/B/z2/routes.json | `92a5febef18fb76d` |
| 25d/schemeA/layers5/routes_25d.json | `7d1e82fb7742818e` |
| 25d/schemeB/layers5/routes_25d.json | `3c4be7a0288e4770` |

## 8. 备注

- 所有 R15 runner 在 import 任何绑定半径的模块之前调用
  `profile_r15.apply()`；multiprocessing worker 通过
  `FSLW_PROCESS_RADIUS_MM` 环境变量 + `worker_boot.ensure_profile()` 保持一致；
- R40 历史轮不设置该变量（默认 40），因此历史数据/复现不受影响；
- 本轮没有修改端口位置、连接关系、CSV、板尺寸、净空/宽度/交叉策略；
- 不开展 Native 3D 联合寻路；不提前确定未标定的损耗系数。
