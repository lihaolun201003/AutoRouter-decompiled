# 公开仓库说明：FSLW R>=40 mm / 30 um 双高度真实 2x16 接口 ABCD（2026-10-19）

本目录对应 `docs/reports/four_side_1024_fslw_R40_gap30_abcd.md`。模型要点：

- 接口：IEC 61754-7-3:2019 2x16 MPO，同排 0.25 mm、两排 0.5 mm；两排沿玻璃厚度方向安装在
  两个高度平面（模型值 z1=0.0 / z2=0.5 mm），**每个平面独立二维寻路**（平面内 `layer=0`）。
- 连接：CSV `row=1` 的 512 条对边连接走 z1 平面，`row=2` 的 512 条邻边连接走 z2 平面。
- 工艺：弯曲半径 **R>=40 mm（本轮固定 R=40）**、波导宽度 0.05 mm、边缘间距 **0.030 mm**、
  中心线净空 **0.080 mm**、传播损耗 0.05 dB/cm。
- 跨平面的 XY 投影交叉**不是**同层冲突；本轮**不实现 z 方向过渡**，不添加其他波导层。
- 诚实边界：玻璃厚度与接头安装方向尚未确认，9 mm 接头中心距存在机械干涉问题，
  结果属于"双高度接口假设下的仿真"，**不宣称可制造**；弯曲/交叉损耗未知（未编造数值）。

## 已上传

| 内容 | 说明 |
|---|---|
| `connectivity/` | 双高度 2x16 端口模型独立校验、2048 个真实 3D 物理端口坐标、每平面连接图、双高度剖面示意图、README |
| `feasibility/` | Phase-2 几何可行性：9 类必需路径族检查、邻边可行域网格、逐条"无合法候选"路线清单 |
| `planes/<V1|V2>/<A-D>/<z1|z2>/` | 16 个平级实验的 `routes.json`（512 条身份）、`statistics.json`、`config.json`、`audit_strict.json`、`run.log` |
| `combined/<V1|V2>/<A-D>/` | 8 个 1024 通道组合布局：`routes_1024.json`（含 plane/z 标签）、`statistics.json`、`planes_summary.json`、`layer_2d.png`；最佳组 V2_C 额外含 `layer_2d.svg`、`overlay_3d.png`、`routing_1024_two_height.gds`（layer0=z1/layer1=z2，两个物理高度） |
| `sensitivity/` | 参数敏感性 O/G/R/N 四组 x 两个平面：结果、统计与独立 `audit_strict.json` |
| `c_sweep/` | 算法 C 的两个设计消融 |
| `comparison/` | 全部对比资产：all_metrics.csv/json、八组布通率、平面/分层对比、敏感性对比、交叉热图、半径检查；**24 个运行的权威严格审计汇总**（`strict_audit_summary.json` + `.md`：16 平面 + 8 敏感性，12 288 条身份、7 605 条布通轨迹、867 020 交叉、0 违规）、`crosscheck_*.json` ×24（918 942 对路线 mismatch = 0）、`previous_rounds_untouched.json` |

## 因体积未上传（可完整重建）

- 各平面的 `routing_all.png/svg/gds`、`routing_detail.png`、`crossing_heatmap.png`、
  `radius_check.png`、`congestion_zoom.png`、`CHECKPOINT.json`、`failed_routes.json`
  （失败记录已含在 `routes.json` 中）。
- 非最佳组的 `overlay_3d.png`、`layer_2d.svg`、`routing_1024_two_height.gds`。
- 重新生成命令（在 `OpticalWaveguideRouter2D/` 下，需要 `.venv`）：

```shell
python -m four_side_1024.fslw.plots   --root outputs/four_side_1024_fslw_R40_gap30_abcd --all
python -m four_side_1024.fslw.combine --root outputs/four_side_1024_fslw_R40_gap30_abcd --all
python -m four_side_1024.fslw.compare --root outputs/four_side_1024_fslw_R40_gap30_abcd
```

`routes.json` 是自包含的权威几何记录；`audit_strict.json` 由独立校验器
`fslw/validate_fslw.py` 生成（16/16 平面 PASS、0 违规、路由器与校验器 mismatch=0）。
