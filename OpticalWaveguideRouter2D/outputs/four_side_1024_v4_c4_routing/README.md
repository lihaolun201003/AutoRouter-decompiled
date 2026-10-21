# V4-C4 同边重配对与 1024 通道布线实验 — 数据清单

本轮在 V3-C4 的 964/1024（512 对边 + 456 成功邻边）基础上，把 V3 中失败的 **14 个邻边四元组（56 条连接）**
重新配对为 **同边内部互连**：每边角部两个端口互连，其余三边由 90° 旋转生成，保持严格端口级 C4 对称。

## 最终结果

| 项目 | 数值 |
|---|---:|
| V4 成功通道数 | **1020 / 1024** |
| 相对 V3（964）增加 | **+56 条** |
| 对边连接 | 508 / 512（V3 已布通的 508 条全部保留） |
| 邻边连接 | 456 / 456（V3 成功邻边全部保留） |
| 同边 U 形连接 | **56 / 56（14 个四元组 × 4 边旋转，全部布通）** |
| row1 (z=0 mm) / row2 (z=0.5 mm) | 508 / 512 |
| C4 对称 | **PASS**（255/256 个四元组完整，端口级 90° 旋转逐组比对 0 误差） |
| 2D 自动验收 | **PASS**（冻结 `fslw.validate_fslw` strict：z1 508 条、z2 512 条，geometry 0 错、strict 0 违规） |
| 端口/身份 | 2048 个物理端口各用一次；1024 条记录与 V4 CSV 逐条一致 |
| 未布通 | 仅 V3 原有对边组 53（4 条），本轮未救回；其余 1020 条全部布通 |
| 三维抬升 | 0 组（本轮按要求只做二维） |

V4 连接分布：对边 **512**、邻边 **456**、同边 **56**，合计 **1024**；同边连接每边 14 条（N/E/S/W 各 14）。

## 文件

| 文件 | 说明 |
|---|---|
| `optical_1024_multitomulti_connectivity_v4_c4_symmetric.csv` | V4 连接表（1024 行，V3 route_id 不变；`relation` = opposite / adjacent / same） |
| `optical_1024_multitomulti_connectivity_v4_c4_symmetric.xlsx` | V4 Excel：1024 连接总表 / 四边接口表(2048) / 旋转对称组(256×4) / 统计与验证 / 来源与重配对 / 被重配对行(56) |
| `v4_connectivity_data.json` | V4 连接、四元组、56 条被重配对映射（V3 邻边 → V4 同边） |
| `validation_connectivity.json` | 连接表自动验收：端口唯一、关系计数、旋转闭包、组结构（PASS） |
| `routes_1024.json` | **1024 条完整路线几何**（primitives/line+arc、长度、family/params、C4 组号与相位、状态） |
| `routes_z1.json` / `routes_z2.json` | 分平面路线数据（各 512 条） |
| `failed_routes.json` | 失败线路与失败四元组（仅对边组 53 的 4 条） |
| `run_summary.json` | 成功数、分排/分关系统计、参数、耗时、同边逐组插入参数、组 53 救回尝试记录 |
| `checkpoint.json` | 最优结果可恢复 checkpoint（含 V4 CSV SHA256、逐组插入参数） |
| `validation.json` | 路线层自动验收：逐平面 strict 审计 + C4 旋转审计 + 2048 端口覆盖 + V4 身份核对（PASS） |
| `plots/` | 5 类实际布线图（PNG + SVG），均标注实际成功通道数 |

## 图（plots/，PNG+SVG 同名）

1. `01_overview_1024` 整板 1024 通道二维俯视图
2. `02_row1_opposite` row1 对边布线图
3. `03_row2_adjacent_same` row2 邻边与同边布线图
4. `04_same_side_u_zoom` 同边 U 形连接局部放大图（4 边 × 14 条 + 单边叠放放大；R15 quarter-pair）
5. `05_3d_two_rows` 两排物理高度（row1 z=0 / row2 z=0.5 mm）三维布线图

## 复现

```powershell
$env:PYTHONPATH = "...\OpticalWaveguideRouter2D"

# 1) 生成 V4 连接表 + Excel + 连接级验收（需要 openpyxl 的 Python）
& $py -m four_side_1024.v3c4.v4_connectivity

# 2) 布线实验：保留 V3 964 条路线，插入 56 条同边 U（四条联合检测、原子提交），
#    可选地对对边组 53 做有限时长救回尝试；输出路线/验收/图（需要 matplotlib 的 .venv Python）
& $py -m four_side_1024.v3c4.v4_run --z1-recovery-seconds 420
```

关键实现（均在 `four_side_1024/v3c4/`，未修改 V3 CSV / V3 结果 / V1-V2 历史）：
- `v4_connectivity.py`：V4 连接重配对、C4 四元组与 2048 端口校验、CSV/Excel 输出；
- `v4_route.py`：同边 U 候选（直接复用 `r15/u_geometry.py` 的 R15 quarter-pair / half-circle / stadium 几何，
  半径不缩）、四条 90° 旋转联合检测与原子提交；
- `v4_run.py`：路线 payload、冻结校验器审计、C4 旋转审计、身份/覆盖检查、5 类图输出。

## 物理约束（全部继承，未放宽）

板 150×150 mm；R ≥ 15 mm（含同边 U 两段 90° 圆弧）；波导宽 0.05 mm；最小边缘间距 0.03 mm；
非豁免中心线净空 ≥ 0.08 mm；row1 z=0 mm / row2 z=0.5 mm；端口位置与切向固定；严格 C4 四重旋转对称。

## 输入与来源

- V3 连接表（未修改）：`outputs/four_side_1024_v3_c4_connectivity/optical_1024_multitomulti_connectivity_v3_c4_symmetric.csv`
  SHA256 `de7e382d3fbf94033eb323ccc64914739e14bde5793191389341896b717f0430`
- V3 布线结果（未修改）：`outputs/four_side_1024_v3_c4_routing/`（964/1024 基线）
- V4 连接表 SHA256：见 `run_summary.json` / `checkpoint.json`（CSV SHA 记录在 `validation_connectivity.json`）
