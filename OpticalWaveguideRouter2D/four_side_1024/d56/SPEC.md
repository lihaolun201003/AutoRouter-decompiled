# D56 优化算法共享契约（SPEC）

本文件是 `four_side_1024/d56/` 包的公共契约。所有写入者必须遵守本文件；任何变更必须显式记录在本文件末尾的变更记录中。

目录：`OpticalWaveguideRouter2D/four_side_1024/d56/`

## 0. 绝对不变项（不得修改）

| 项 | 值 |
|---|---|
| 板面 | 150 x 150 mm，坐标原点左下，x/y 均为 mm |
| 连接关系 | 原始 CSV `optical_1024_multitomulti_connectivity_v1.csv`（SHA256 `0ecce47109f9223e8407928c423ad5d9272186938cc267877a6158936e0e428b`） |
| 端点 | `four_side_1024.inputs.load()` 给出的 `routing_xy`（`virtual_unfolded` 模式），route 起终点固定 |
| 层 | 所有图元 `layer=0`，无 z |
| 最小弯曲半径 | R = 5.0 mm，所有圆弧半径必须恰为 5.0 mm（不允许缩小半径） |
| 波导宽度 | 0.05 mm |
| 非交叉边缘间距 | 0.125 mm → 中心线最小距离 clearance = width+gap = 0.175 mm |
| 弯曲模型 | D56：仅水平/竖直直线段 + 固定半径 90° 圆弧（或原 AutoRouter 小位移短 S 公式的两段 R 圆弧），不允许 F56 自由弯角、斜线、Dubins |

## 1. D56 几何合法性（每条路线）

一条路线 = `primitives` 列表，按顺序连接。图元仅两种：

```json
{"kind":"line","p0":[x,y],"p1":[x,y],"layer":0}
{"kind":"arc","p0":[x,y],"p1":[x,y],"center":[x,y],"radius":5.0,
 "start_angle":a0,"sweep":s,"layer":0}
```

必须同时满足：

1. **只正交**：每条 `line` 的 `p0→p1` 必须与 x 轴或 y 轴平行（容差 1e-9）。
2. **圆弧半径固定**：每条 `arc.radius == 5.0`（容差 1e-9）。
3. **不允许自由弯角**：每个 `arc` 必须满足下列之一（仅此两类）：
   - 标准直角转弯：`|abs(sweep) - pi/2| <= 1e-9`；
   - 原 AutoRouter 小位移短 S 公式：存在横向位移 `d = 2*R*sin(theta)`（`0 < d < 2R`），`theta=acos(1-d/(2R))`，`sweep=±theta`，且该圆弧与另一反向 `theta` 圆弧成对出现，两弧之间直线段长度≈0。此公式与 `wiring_rect_826.py` 的 D56 构造一致，属于 D56 允许范围。
   - 结论：`sweep` 绝对值只能落在 `{pi/2}` 或短 S 的 `theta` 值上，且短 S 必须成对。
4. **切向连续**：相邻图元在连接点位置连续（<1e-7）且切向连续（<1e-7）；`arc` 端点必须与其 center/radius/start_angle/sweep 解析一致。
5. **起点终点固定**：`primitives[0].p0 == endpoints[source].routing_xy`，`primitives[-1].p1 == endpoints[target].routing_xy`（<1e-7）。
6. **出入射方向**：`primitives[0]` 的出射切向 == source `inward`；`primitives[-1]` 的入射切向 == `-target.inward`（<1e-7），即路线离开源端口时朝板内法向、到达目标端口时朝板内反方向。
7. **板界**：按宽度 0.05 描边后仍在 [0,150]^2 内。
8. **无自交/自重叠**：`four_side_1024.geometry.validate` 的自交检查必须返回空。
9. **单层**：全部 `layer=0`。

## 2. 路线间合法性（精确几何，沿用现有验收口径）

与 `four_side_1024/conflicts.py` 的语义一致：

- 中心线距离必须 ≥ 0.175 mm，**除**允许的二维横穿区域外。
- 横穿（crossing）只豁免交点局部：沿每条曲线各取 `half = 0.175/sin(angle) + 2*sagitta`（sagitta=0.0005 mm）的区间；区间外仍需与对方完整路径保持 0.175 mm。
- 拒绝：重叠（collinear overlap）、切触（sine<1e-7 或交点落在路线端点上）、交叉豁免区彼此重叠、自交、自重叠、非相邻段间距违规。
- 允许并记录交叉：交叉点坐标、角度、所属两条路线。

## 3. 输出文件契约

运行目录：`OpticalWaveguideRouter2D/outputs/four_side_1024_d56_optimized/`

必需文件（文件名固定）：

| 文件 | 内容 |
|---|---|
| `01_connectivity.png` | 1024 原始连接关系图（复用 `inputs.phase1` 风格） |
| `02_routing_all.png` | 全部成功路线整板图，标题标注真实成功数 |
| `03_opposite_routes.png` | 对边路线单独着色 |
| `04_adjacent_routes.png` | 邻边路线单独着色 |
| `05_crossing_heatmap.png` | 交叉点 2D 热图（5x5 mm 网格） |
| `06_routing_detail.png` | 3-4 个热点区域放大图 |
| `07_strategy_comparison.png` | 消融/策略对照条形图（成功数、对边/邻边、交叉数） |
| `routing_all.svg` | 全部成功路线矢量图 |
| `routing_all.gds` | 单层 GDSII（layer 0，圆弧按 sagitta<=0.0005 离散） |
| `routes.json` | 全部 1024 条身份，成功者含解析几何 |
| `failed_routes.json` | 失败路线及失败分类/阻挡统计 |
| `statistics.json` | 全部统计指标 |
| `run.log` | 带时间戳真实运行日志 |

### 3.1 `routes.json`

```json
{"schema":"four_side_1024_d56_optimized_routes_v1",
 "units":"mm","layer":0,"endpoint_mode":"virtual_unfolded",
 "csv_sha256":"...",
 "config":{...},
 "algorithm":{...},
 "routes":[
   {"route_id":1,"status":"routed","relation":"opposite","pair":"NS",
    "source_side":"N","target_side":"S",
    "source_endpoint":"N01:1:1","target_endpoint":"S01:1:1",
    "layer":0,"length_mm":153.2,"bend_count":2,
    "primitives":[ ... ],
    "candidate":{"family":"U","track_mm":75.0,"strategy":"opposite_first","index":3}
   },
   {"route_id":2,"status":"failed","relation":"adjacent","pair":"ES",
    "source_endpoint":"...","target_endpoint":"...",
    "reason":"no_legal_candidate","evaluated":42,"blockers":{...}}
 ]}
```

### 3.2 `statistics.json` 必需字段

见 `docs/reports/four_side_1024_d56_optimized.md` 第十一节要求，至少：

`success_count, failed_count, success_rate, by_pair{6}, by_relation{opposite,adjacent},
mean_length_mm, max_length_mm, total_length_mm, crossing_count,
crossing_angle_histogram, small_angle_threshold_deg, small_angle_crossing_count,
spacing_violation_pairs, overlap_pairs, self_intersections, radius_violations,
boundary_violations, candidate_evaluations, total_runtime_seconds,
failure_reason_counts, ablations[], independent_audit{...}`

## 4. 代码所有权（避免写冲突）

| 路径 | 所有者 |
|---|---|
| `d56/SPEC.md` | Lead |
| `d56/frames.py`, `d56/candidates.py`, `d56/index.py`, `d56/search.py`, `d56/run.py`, `d56/pipeline.py` | Lead |
| `d56/validate_d56.py`, `d56/tests_d56/` | validator（队友） |
| `d56/outputs_d56.py`, `d56/plots_d56.py` | outputs-builder（队友） |
| `scratch/diagnosis/`, `docs/reports/d56_1024_failure_diagnosis.md` | diagnostician（队友） |

## 5. 变更记录

- v1（Lead）：初始契约。
- v2（Lead，2026-10-19）：明确**交叉区口径**。历史实现
  `half = clearance/sin(angle) + 2*sagitta` 对"圆弧参与交叉"是**欠豁免**
  （直线公式，弧的切向在旋转），实测在 CSV 原生直接 L 路径上窗外距离
  0.173936 mm < 0.175 mm（差 1.06 µm），浅角弧-线交叉差 13.5 µm。因此：
  1. `d56/index.py` 默认 `crossing_policy='exact'`：横向交叉豁免**恰好**整对
     相交 primitive（非相交 primitive 对仍严格检查），即"交叉只豁免局部交叉
     区域"的精确实现；半径、宽度、间距、单层约束均未改变。
  2. `crossing_policy='legacy'` 保留历史 `clearance/sin(angle)` 口径（弧参与
     交叉时补窗外精确复检），用于与 80 / 526 基线做**同口径敏感性对比**。
  3. 最终报告须同时给出两种口径的布通数与违规统计；交付主结果用 exact 口径，
     legacy 口径作为严格化对照（Phase 1 诊断结论之一即此欠豁免问题）。
  4. 独立校验器 `validate_d56.py` 默认 legacy 口径（authoritative 对照），
     并提供 `--compare-exact` 输出 exact 口径下的违规清单。
- v3（Lead）：相邻/对边候选族的自由参数改为**由实际占用障碍带推导的车道**
  （`clearance_tracks`），不再使用与 comb 相位不对齐的全局 0.175 栅格；
  `FrameOracleSet` 为 6 个有向边对分别维护 canonical 占用视图，并把 CSV
  端点隐含的"必然占用线"（E/W 端点 y、S/N 端点 x）静态注入，避免在线贪心
  只躲避已布路线而撞上后布路线的固定段。
