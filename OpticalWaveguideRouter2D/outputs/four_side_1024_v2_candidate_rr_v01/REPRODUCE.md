# V2 双高度二维布线优化轮（v2_candidate_rr_v01）复现说明

工程根目录：`C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D`
Python：`.venv\Scripts\python.exe`（Python 3.10.11，numpy / matplotlib / pytest 已安装）

本轮所有实验的**物理参数、V2 连接 CSV、D56 几何 primitive 与 strict 验收口径完全沿用上一轮**，
只在搜索/调度层面扩展。随机种子统一为 `20261019`（`four_side_1024/v2opt/config.py:SEED`）。

## 0. 输入（只读历史，不修改）

| 内容 | 路径 |
|---|---|
| V2 连接 CSV | `C:\Users\lihao\Desktop\optical_1024_multitomulti_connectivity_v2_symmetric.csv`（SHA256 `49dd9e89...3915e`） |
| 历史 z1（V2-D，492/512） | `outputs/four_side_1024_fslw_R40_gap30_abcd/planes/V2/D/z1/routes.json` |
| 历史 z2（V2-C，206/512） | `outputs/four_side_1024_fslw_R40_gap30_abcd/planes/V2/C/z2/routes.json` |

## 1. 组合基线 698 的独立验收

```bat
cd "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D"
.venv\Scripts\python.exe four_side_1024\v2opt\audit_baseline.py
.venv\Scripts\python.exe -m pytest four_side_1024\v2opt\tests -q
```

产物：`outputs/four_side_1024_v2_candidate_rr_v01/planes/V2/BASE/{z1,z2}/`、
`combined/V2/BASE/`、`baseline_acceptance.json`（7 项逐条证据）。

## 2. 候选预算对照（任务 5.1/5.4，约 20 分钟）

```bat
.venv\Scripts\python.exe -m four_side_1024.v2opt.pipeline sweep --plane z2 --budgets 200,400,800,1600 --workers 10
```

产物：`candidates_budget/sweep_budget{200,400,800,1600}.json`、`sweep_summary.json`、
`candidates_budget/figures/*.png`、`candidates_budget/ANALYSIS.md`。

## 3. E1（扩大候选、无强化 R&R，约 25 分钟）

```bat
.venv\Scripts\python.exe -m four_side_1024.v2opt.pipeline e1 --budget 1600
```

## 4. E2（原预算 200 + 强化 R&R，约 40 分钟）

```bat
.venv\Scripts\python.exe -m four_side_1024.v2opt.pipeline e2 --workers 6 --rounds 6 --transactions 64 --sizes 1,2,4,8,12 --analysis-budget 400 --reinsert-budget 400 --rr-time-limit 2400
```

## 5. E3（扩大候选 1600 + 强化 R&R，约 1~2 小时）

```bat
.venv\Scripts\python.exe -m four_side_1024.v2opt.pipeline e3 --budget 1600 --workers 8 --rounds 6 --transactions 64 --sizes 1,2,4,8,12 --analysis-budget 800 --reinsert-budget 800 --rr-time-limit 3600
```

## 6. z1 平面同样处理（Z1OPT，约 5 分钟）

```bat
.venv\Scripts\python.exe -m four_side_1024.v2opt.pipeline z1opt --budget 1600 --workers 5 --rounds 4 --transactions 24 --sizes 1,2,4 --analysis-budget 1600 --reinsert-budget 1600 --rr-time-limit 900
```

## 7. E3 续跑（E3X，可选延伸实验）

```bat
.venv\Scripts\python.exe -m four_side_1024.v2opt.pipeline rrcontinue --label E3X --from-checkpoint outputs/four_side_1024_v2_candidate_rr_v01/checkpoints/E3_z2.json --plane z2 --budget 800 --workers 10 --rounds 6 --min-rounds 5 --zero-rounds 2 --transactions 128 --targets-per-round 64 --analysis-targets 96 --sizes 1,2,4,8,12 --analysis-budget 800 --reinsert-budget 600 --rr-time-limit 1800 --seed-offset 777
```

结果：244 → 244（0 增益，4 轮 k=1→8，见 `experiments/E3X_z2_summary.json`）。

## 8. 选择 BEST 布局

```bat
.venv\Scripts\python.exe -m four_side_1024.v2opt.select_best
```

选择规则：z2 取 E1/E2/E3 中独立验收 routed 最大者（并列优先 E3）；z1 若 Z1OPT 严格优于 492 则取 Z1OPT。
产物：`planes/V2/BEST/{z1,z2}/`、`best_selection.json`。

## 9. 独立验收 + 统计 + 1024 组合产物

```bat
.venv\Scripts\python.exe -m four_side_1024.v2opt.finalize --root outputs/four_side_1024_v2_candidate_rr_v01 --labels BASE,E1,E2,E3,Z1OPT,BEST
```

对每个平面运行冻结的 `four_side_1024.fslw.validate_fslw`（strict）写 `audit_strict.json`，
再用 `fslw.metrics` 生成 `statistics.json`，最后用 `fslw.combine` 生成双高度 1024 组合
（`routes_1024.json`、`layer_2d.png/.svg`、`overlay_3d.png`、`routing_1024_two_height.gds`）。

## 10. 汇总对比与报告数据

```bat
.venv\Scripts\python.exe -m four_side_1024.v2opt.summarize
```

产物：`comparison/experiment_comparison.{json,md}`、`comparison/figure_*.png`。

## 11. 验收回归测试

```bat
.venv\Scripts\python.exe -m pytest four_side_1024\v2opt\tests -q
```

覆盖任务九 9 条回归项（历史布局加载、索引拆线/重加、候选去重、R&R 回滚、重复布入、
总数不下降、checkpoint 恢复、预算不改变物理约束、最终布局独立重审计）。

## 目录说明

```
outputs/four_side_1024_v2_candidate_rr_v01/
├─ planes/V2/{BASE,E1,E2,E3,Z1OPT,BEST}/{z1,z2}/   # 每平面 routes.json + audit_strict + statistics
├─ combined/V2/{BASE,E1,E2,E3,Z1OPT,BEST}/         # 1024 组合产物（双高度图/GDS/统计）
├─ candidates_budget/                              # 候选预算对照实验
├─ experiments/                                    # E1/E2/E3/Z1OPT 摘要、R&R 分析、图
├─ reachability/                                   # 128 条角部路线覆盖/可达性探针
├─ checkpoints/                                    # 真实几何 checkpoint（可恢复）
├─ work/                                           # 完整运行日志（命令 + seed + 每轮进度）
├─ baseline_acceptance.json / final_validation.json / best_selection.json
└─ REPRODUCE.md
```

