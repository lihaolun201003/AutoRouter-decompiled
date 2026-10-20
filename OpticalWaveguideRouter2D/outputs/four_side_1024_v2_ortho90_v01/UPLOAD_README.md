# 公开仓库说明：纯正交 90° 圆弧布线对照（262/1024，2026-10-20）

本目录对应 `docs/reports/four_side_1024_v2_ortho90_v01.md`（仓库根 docs）。

- **唯一几何改动**：只允许水平/竖直直线段 + 半径恰 40 mm、转角恰 90° 的四分之一圆弧；
  禁止 Short-S 的非 90 度圆弧组合、禁止斜线与自由弯角。V2 连接、双高度接口、R40、0.03 mm
  边缘间距、全部 strict 约束与独立验收沿用上一轮。
- **结果**：**262/1024（25.59%）**：z1 128/512（全部为单根直线；其余 384 条 8/16/24 mm
  小横向偏移连接在纯 90 度几何族下无合法候选）、z2 134/512（全部由轴对齐直线 + 90 度 R40 弧组成，
  非 90 度弧 0、斜线 0）。相对 752 基线 -490 条（-65.2%）。
- **验收**：两平面冻结 `validate_fslw` strict 验收 PASS（0 违规）+ 额外逐 primitive 审计
  （178/178 段弧均为 R=40 且 |sweep|=90°、index 0）；`geometry_audit.json` 同时量化参考
  752 布局的非 90 度弧使用量（z1 768/768 段、z2 234/482 段）。

## 已上传（本目录全部 78 个文件，21 MB）

`planes/V2/ORTHO90/{z1,z2}/`（routes/statistics/config/audit/平面图/几何类型着色图）、
`combined/V2/ORTHO90/`（routes_1024/statistics/planes_summary/layer_2d/overlay_3d/GDS）、
`experiments/`（8 种顺序对照、空板候选覆盖、z1 精确 LP 可达性证据、汇总 JSON）、
`comparison/`（新旧对照图 compare_z1/z2/all）、`checkpoints/`、`work/`（运行日志）、
`geometry_audit.json`、`final_validation.json`、`REPRODUCE.md` 与报告副本。

复现：见 `REPRODUCE.md`（pipeline ortho90 / order_sweep_ortho90 / ortho90rr / finalize /
ortho90_validate / plots_ortho90 / coverage_ortho90 / z1_pure90_infeasibility）。
