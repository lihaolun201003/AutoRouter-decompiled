# 公开仓库说明：V3-Huang 1024 通道双高度二维布线轮（2026-10-19）

本目录对应 `docs/reports/four_side_1024_v3_huang_R40_gap30_abcd.md`。

## 本轮模型

- 输入：用户提供的 V3-Huang 连接关系。`data/v3_huang/` 中冻结了字节原样副本
  （CSV SHA256 `76d91316…6cf23`、XLSX `4d285f56…b32de`，`PROVENANCE.json` 记录原路径）。
  1024 条光纤级固定连接：same 448（NN/SS/EE/WW 各 112）+ opposite 384（NS/EW 192）
  + adjacent 192（NE/NW/ES/SW 各 48）；CSV row1→z1（同边 222/对边 196/邻边 94）、
  row2→z2（226/188/98）；2048 个物理端点各用一次。
- 工艺/几何与上一轮 FSLW 完全相同且未放宽：R = 40 mm 固定（所有弧 40.0）、波导宽 0.05 mm、
  边缘间距 0.030 mm、中心线净空 0.080 mm、D56 正交直线 + 四分之一圆弧 + 历史短 S 对，
  并为本轮同边连接新增 `SAME_U` / `SAME_HAIRPIN_A/B`（短 S + 相邻两段四分之一弧的 180° 回折）。
- strict 验收口径不变：0.080 mm 净空、禁止二次交叉/重叠/相切/窗互叠/过宽窗，仅对布通几何审计；
  `no_candidate_generated` / `no_legal_candidate` 是失败身份而非违规。
- 双高度：row1→z1、row2→z2，两高度独立二维布线；跨高度 XY 投影交叉不计冲突；
  **未实现 z 过渡**，不添加其他波导层。

## 已上传

| 内容 | 说明 |
|---|---|
| `inputs/` | 冻结输入的 SHA256 清单（原始文件在 `OpticalWaveguideRouter2D/data/v3_huang/`） |
| `topology/` | 独立输入审计（26/26 PASS、与 Lead 模块 0 mismatch）、2048 个真实 3D 物理端口、每平面 1024 端点、64×64 矩阵 CSV、类组成图与矩阵热图、README |
| `feasibility/` | Phase-2/3：16 项真实几何小规模测试（全部 PASS）、同边可行域网格、类别隔离容量实验（same/opposite/adjacent 与 NN/SS/EE/WW 单独布线容量） |
| `planes/<A-D>/<z1|z2>/` | 8 个平面实验的 `routes.json`（512 条身份，含失败记录）、`statistics.json`、`config.json`、独立 `audit_strict.json`、`run.log` |
| `combined/<A-D>/` | 4 套 1024 通道组合：`routes_1024.json`、`statistics.json`、`planes_summary.json`；最佳组 B 另含 `layer_2d.png/svg`、`overlay_3d.png`、双高度 GDS（layer0=z1/layer1=z2），组 C 另含 `layer_2d.png` |
| `shapes/` | 同边 U/回折专项统计 JSON（形态构成、U 深度/轨道/嵌套、相邻 U 间距、成组拱形、失败分类） |
| `comparison/` | 10 项必需 Phase-7 图（需求图、64×64 矩阵、z1/z2 四算法布局、四套组合图、3D 叠加、仅 U 专项、嵌套放大、类别对比、算法对比）、`all_metrics.csv/json`、`key_numbers.json`、严格审计汇总、交叉验证 JSON、README |
| `report/report_data.json` | 报告使用的原始数据快照 |

## 因体积未上传（可完整重建）

- 各平面的 `routing_all.png/svg/gds`、`routing_detail.png`、`crossing_heatmap.png`、
  `radius_check.png`、`congestion_zoom.png`、`CHECKPOINT.json`、`failed_routes.json`
  （失败记录已含在 `routes.json` 中）。
- 组合布局 A/D 的 `layer_2d.png/svg`、`overlay_3d.png`、双高度 GDS（B/C 已保留；
  四套组合的整体图见 `comparison/combined_layouts_abcd.png`、`comparison/overlay_3d_abcd.png`）。
- `topology/` 中三张大图的副本（`demand_1024_connectors.png`、`plane_demand_z1/z2.png`），
  需求图见 `comparison/demand_1024_connector.png`。
- `shapes/` 中与 `comparison/` 重复的图片（`u_routes_only.png`、`nested_u_zoom.png`、
  `shape_mix.png`、`u_depth_histogram.png`、`u_track_occupancy.png`），见 `comparison/`。
- 重新生成命令（在 `OpticalWaveguideRouter2D/` 下，需 `.venv`）：

```shell
python -m four_side_1024.v3.metrics --run-dir outputs/four_side_1024_v3_huang_R40_gap30_abcd/planes/B/z1
python -m four_side_1024.v3.plots   --root outputs/four_side_1024_v3_huang_R40_gap30_abcd --all
python -m four_side_1024.v3.combine --root outputs/four_side_1024_v3_huang_R40_gap30_abcd --all
python -m four_side_1024.v3.compare --root outputs/four_side_1024_v3_huang_R40_gap30_abcd
python -m four_side_1024.v3.validate_v3  --scan-root outputs/four_side_1024_v3_huang_R40_gap30_abcd/planes
python -m four_side_1024.v3.crosscheck_v3 --scan-root outputs/four_side_1024_v3_huang_R40_gap30_abcd/planes
```

`routes.json` 是自包含的权威几何记录；`audit_strict.json` 由独立校验器生成
（8/8 平面 PASS、0 违规、路由器与校验器 160 367 对路线 mismatch=0）。
