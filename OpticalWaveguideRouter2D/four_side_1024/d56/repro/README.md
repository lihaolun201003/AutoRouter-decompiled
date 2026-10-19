# D56 优化的可复现脚本与诊断证据

本目录保存两份报告引用的可复现脚本与关键证据：

- `docs/reports/four_side_1024_d56_optimized.md`（完整实验与消融报告）
- `docs/reports/d56_1024_failure_diagnosis.md`（Phase 1 失败诊断）

工作副本中的 `OpticalWaveguideRouter2D/scratch/` 是项目的本地临时目录（被
`OpticalWaveguideRouter2D/.gitignore` 的 `scratch/` 规则忽略），公开仓库里改为放在
本目录，映射如下：

| 报告中的路径 | 公开仓库路径 |
|---|---|
| `scratch/diagnosis/*.py`、`summary.json`、`data/*` | `four_side_1024/d56/repro/diagnosis/` |
| `scratch/*.py`（消融/定稿/复算脚本） | `four_side_1024/d56/repro/ablation/` |
| `scratch/audit_*.json`、`final_exact.json`、`legacy_full.json` | `four_side_1024/d56/repro/ablation/` |

**因体积未上传**（结论已固化在 `diagnosis/summary.json` 与报告中，脚本可重新生成）：
`scratch/diagnosis/data/replay/`（约 44 MB 逐轨回放明细）、
`scratch/diagnosis/data/calib/`（约 2.8 MB 标定中间件）、`scratch/validate_final.json` 等
可重算的运行快照。

权威的逐条违规清单与独立审计结果见
`outputs/four_side_1024_d56_optimized/independent_audit*.json`。

## 重新生成的顺序

```shell
# 1) 复现诊断 8 问（详见诊断报告每节的命令）
python four_side_1024/d56/repro/diagnosis/probe_transforms.py
python four_side_1024/d56/repro/diagnosis/probe_replay.py
python four_side_1024/d56/repro/diagnosis/probe_direct_l.py
python four_side_1024/d56/repro/diagnosis/probe_capacity.py

# 2) 复现消融表（需要各策略 checkpoint）
python four_side_1024/d56/repro/ablation/collect_ablations.py
python four_side_1024/d56/repro/ablation/recompute_ablation_stats.py

# 3) 定稿与产物
python four_side_1024/d56/repro/ablation/finalize_delivery.py <best_checkpoint.json>
python -m four_side_1024.d56.run --strategy A --groups NW,EN,SW,ES,NS,EW --within x_desc --out outputs/four_side_1024_d56_optimized
python -m four_side_1024.d56.validate_d56 --routes outputs/four_side_1024_d56_optimized/routes.json --compare-exact
python -m four_side_1024.d56.outputs_d56 --run-dir outputs/four_side_1024_d56_optimized --run-status complete
```
