# 公开仓库说明：V2 双高度候选扩展 + 强化 R&R（2026-10-20）

本目录对应 `docs/reports/four_side_1024_v2_candidate_rr_v01.md`（仓库根 docs）。

- **模型**：IEC 61754-7-3:2019 真实 2x16 双高度接口（row1 -> z1 对边平面、row2 -> z2 邻边平面；
  z1=0.0 / z2=0.5 mm，两平面独立二维寻路，跨平面投影交叉不计冲突），R = 40 mm 固定、
  波导宽度 0.05 mm、边缘间距 0.030 mm、中心线净空 0.080 mm、strict 局部交叉窗口口径；
  本轮不实现 z 过渡，不宣称可制造。
- **结果**：V2 1024 组合最佳 **752/1024（73.44%）**：z1 508/512 + z2 244/512；
  组合基线 698 的独立验收（`baseline_acceptance.json`）、候选预算 200/400/800/1600 阶梯
  （`candidates_budget/`）、E1/E2/E3/E3X/Z1OPT/BEST 消融与 R&R 轮次统计（`experiments/`）、
  可达性与角部路线覆盖（`reachability/`）、对照图（`comparison/`）。所有平面/消融组均通过
  独立 strict 验收（`audit_strict.json`，0 违规）；`final_validation.json` 为 1024 组合验收汇总。

## 已上传

- `planes/V2/<BASE|E1|E2|E3|E3X|Z1OPT|BEST>/<z1|z2>/`：`routes.json`（自包含几何，含成功与失败记录）、
  `statistics.json`、`config.json`、`audit_strict.json`、`CHECKPOINT.json`、`failed_routes.json`；
  BEST 额外保留 `routing_geomtype.png`（几何类型着色图）。
- `combined/V2/<label>/`：`routes_1024.json`、`statistics.json`、`planes_summary.json`；
  BEST 额外保留 `layer_2d.png/svg`、`overlay_3d.png`、`routing_1024_two_height.gds`。
- 顶层：`METHOD.md`、`REPRODUCE.md`、`baseline_reproduce.md`、`baseline_acceptance.json`、
  `best_selection.json`、`final_validation.json`、报告副本；`checkpoints/`（真实几何快照）、
  `work/`（运行日志）。

## 因体积未上传（可完整重建）

各平面的 `routing_all.png/svg/gds`、`routing_detail.png`、`crossing_heatmap.png`、
`radius_check.png`、`congestion_zoom.png`；非 BEST 组合的 `layer_2d.png/svg`、
`overlay_3d.png`、`routing_1024_two_height.gds`。重建命令见 `REPRODUCE.md`：

```bat
.venv\Scripts\python.exe -m four_side_1024.v2opt.select_best
.venv\Scripts\python.exe -m four_side_1024.v2opt.finalize --root outputs/four_side_1024_v2_candidate_rr_v01 --labels BASE,E1,E2,E3,E3X,Z1OPT,BEST
.venv\Scripts\python.exe -m four_side_1024.v2opt.summarize
```

`routes.json` 是权威几何记录；`audit_strict.json` 由冻结独立校验器 `fslw/validate_fslw.py`
生成（strict 口径），不使用路由器内部判定。
