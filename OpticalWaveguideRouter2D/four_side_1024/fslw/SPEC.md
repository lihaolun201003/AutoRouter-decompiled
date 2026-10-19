# FSLW R≥40 mm / 30 µm：双高度真实 2×16 接口 ABCD 实验契约（SPEC v1）

本文件是 `four_side_1024/fslw/` 包的公共契约。所有写入者必须遵守；变更记录在 §12。

- 代码：`OpticalWaveguideRouter2D/four_side_1024/fslw/`
- 交付：`OpticalWaveguideRouter2D/outputs/four_side_1024_fslw_R40_gap30_abcd/`
- 报告：`<project root>/docs/reports/four_side_1024_fslw_R40_gap30_abcd.md`

## 0. 与上一轮的关系（不得覆盖）

上一轮 `outputs/four_side_1024_v1_v2_abcd/`（R=5 mm、125 µm 边缘间距、`virtual_unfolded`
单层 1024 通道虚拟展开、8 组 ABCD）**原样保留**，仅作为"单层虚拟展开算法压力测试基线"引用。
本轮所有结果写入新目录，不改上一轮任何文件，不改 `four_side_1024/d56/**`、`tests/**`、
256/512 复刻结果。

## 1. 本轮工艺参数（最高优先级，不允许被旧配置覆盖）

| 项 | 值 |
|---|---|
| 板面 | 150 × 150 mm，单层二维（每个布线平面 `layer=0`） |
| 波导宽度 | 0.050 mm（模型沿用，非已确认的飞秒直写芯宽） |
| 最小边缘间距 | **0.030 mm** |
| 最小中心线净空 | **0.080 mm**（= 0.05 + 0.03） |
| 最小弯曲半径 | **R ≥ 40 mm**；本轮采用 **fixed_radius_40mm = true**（所有弧半径恰为 40 mm），不声称搜索了所有 R≥40 路径 |
| 弯曲模型 | D56 传统：正交直线 + 固定半径 90° 圆弧 + 原 AutoRouter 小位移短 S（两段 R 弧，`theta=acos(1-d/(2R))`，R=40） |
| 禁止 | F56 自由弯角、斜线、Dubins、半径 < 40 mm、放宽间距、移动端点、增加其他波导层 |
| 传播损耗 | 0.05 dB/cm（仅传播；弯曲/交叉损耗未知，见 §7） |
| 端点模型 | 双高度真实 2×16（§2），**不再使用 175 µm 虚拟展开** |

## 2. 接口模型：双高度真实 2×16（本轮唯一正式的实验模型）

IEC 61754-7-3:2019 的 2×16 MPO：同排纤芯中心距 **0.25 mm**，两排中心距 **0.5 mm**。
本轮假设两排沿玻璃厚度方向安装，分别位于 **z₁、z₂** 两个高度平面（`z2 - z1 = 0.5 mm`）：

- **z₁ 平面**：CSV 中 `row = 1` 的 512 条连接（全部为对边连接，NS 256 + EW 256）。
- **z₂ 平面**：CSV 中 `row = 2` 的 512 条连接（全部为邻边连接，EN/ES/SW/NW 各 128）。
- 每个平面内，每个接头的本排 16 个纤芯沿边排列：`along = connector_center + (col - 8.5) * 0.25`；
  该平面的 4 边 × 16 接头 × 16 列 = 1024 个端口，被该平面 512 条连接的 1024 个端点**恰好各用一次**。
- **每个平面独立做二维寻路**，平面内所有图元 `layer=0`；`z` 仅作为平面标签保存在元数据与
  组合布局中（`z1=0.0, z2=0.5` 模型值），平面内几何严格二维。
- **跨平面的 XY 投影交叉不是同层冲突**：冲突判定只在同一平面内进行；组合统计中明确区分
  `same_plane_crossings` 与 `cross_plane_projected_overlaps`（后者只作信息展示，不计违规）。
- **本轮不实现 z 方向过渡**（无 via/taper/fanout），不添加其他波导层。
- 真实物理坐标（32 根光纤的 3D 坐标：column→along、row→z）必须**独立保存**，不得与
  "二维布线坐标"混为一谈。本结果是"双高度接口假设下的仿真"，**不宣称最终可制造**。
- 玻璃厚度与接头安装方向尚未确认。

> 与上一轮的关系：上一轮 `virtual_unfolded`（32 个虚拟端口以 0.175 mm 展开在同一平面）是
> "单层虚拟展开压力测试基线"，本轮**不再**使用；两者数字不可直接比较（端口模型不同）。

## 3. 几何合法性（每个平面内的单条路线）

沿用 `d56/SPEC.md` §1，但参数替换为本轮工艺参数：

1. 只正交：每条 line 与 x/y 轴平行（容差 1e-9）。
2. 圆弧半径 == 40.0 mm（容差 1e-9）；不允许更小者。
3. 弧族只允许：标准直角转弯（`|sweep| == pi/2`）或短 S 对。短 S 的**真实几何**为：
   横向位移 `d = 2R(1 - cos theta)`、沿行进方向推进 `h = 2R sin(theta)`，
   其中 `theta = acos(1 - d/(2R))`；两段反向 theta 弧成对、中间直线长度≈0。
   R=40 时 `d` 可接近 `2R = 80 mm`（theta 接近 90°），必须按真实几何构造与验证。**R=40 时短 S 的
   `theta` 可与 90° 很接近（d 接近 80 mm），必须按真实几何构造并验证。**
4. 切向连续、位置连续；起点终点固定；出入射方向 == 端口 inward。
5. 板界：按宽度 0.05 mm 描边后仍在 [0,150]² 内。
6. 无自交/自重叠/自间距（< 0.080 mm）违规。
7. 全部 `layer=0`（平面内）。

## 4. 路线间合法性：严格局部交叉窗口（`crossing_policy='strict'`）

完全沿用 `four_side_1024/abcd/SPEC.md` §2.1 的数学定义，仅替换：
`clearance c = 0.080 mm`，`lim = c - 1e-7 = 0.0799999 mm`，`sagitta = 0.0005`，
`sine 门限 sin(5°)`，`max_half_window = 4.0 mm`。

- 只有真正的横向交叉的**局部最小必要窗口**允许间距例外；窗外双向严格 ≥ lim。
- 重叠、相切、端点接触、二次交叉、窗互叠、过宽窗一律拒绝。
- **跨平面**路线之间**不做**任何同层间距/交叉判定（§2）。
- 路由器判定（`fslw/search.py` 调用 `d56/index.py::D56Index` 的 strict 口径）与独立校验器
  （`fslw/validate_fslw.py`，validator 所有）必须对每对路线判定一致（mismatch=0）。

## 5. 算法与实验矩阵

每个平面是独立的 512 条连接问题（1024 端口）。四条算法只改变"排路线/选候选"：

| 算法 | 定义（沿用上一轮冻结定义，按平面适配） |
|---|---|
| A 对边优先 | 先 NS、EW，再 EN、ES、SW、NW；组内 `x_desc` |
| B 邻边优先 | `NW → EN → SW → ES → NS → EW`；组内 `x_desc` |
| C 四边轮流 | 按边归属（对边对按 route_id 奇偶各半、邻边对各半），每边队列混合对边/邻边需求；顺时针/逆时针 × 起始边 × 批量消融（V1 选一套冻结后用于 V1/V2 两平面） |
| D 全局联合 | 静态候选池（每身份 K 条）× 多起点全局兼容选择 × LNS 成组释放（≤12 条，含已布通者）+ 动态补候选 + 批次内 DFS 联合求解 + 提交前全索引复测；分层目标（布通 → 交叉 → 长度） |

实验矩阵（每个 = 一个平面运行）：

- 2 拓扑（V1/V2）× 2 平面（z1/z2）× 4 算法 = **16 个平级实验**。
- 组合：2 拓扑 × 4 算法 = **8 个 1024 通道组合布局**（z1+z2 合并，跨平面交叉不计冲突）。
- 统一：相同几何、候选族、`strict` 口径、端口模型；候选评价预算与墙钟上限；固定随机种子
  `20261019`（D 使用）；A/B/C 确定性。预算未用尽才算"自然完成"，否则标记 `budget_exhausted`。
- 必须保存全部失败路线与原因；不得隐藏失败。

## 6. 热图/统计口径

- 布通率：平面内 `routed/512`；组合 `routed/1024`（对边 512、邻边 512 分别统计）。
- 长度：`mean/max/min/total`（每条路线解析长度）。
- 交叉：**同平面**横向交叉数（strict 口径下的合法交叉点）+ 交叉角直方图 + <10° 小角交叉；
  另给 `cross_plane_projected_overlap` 仅作展示，不计冲突。
- 传播损耗：`Lprop_dB = 0.05 * length_cm`；输出平均/最大/最小/分布直方图。
  **弯曲损耗与交叉损耗未知**：不得编造数值；旧聚合物模型（若引用）必须标注 `legacy_estimate`。
  报告必须区分"传播损耗"与"总光学损耗"。
- 质量：直线长度占比、平均/总转弯数、不必要绕行长度（相对同端点 Manhattan 下界的超出量）、
  局部交叉密度（5 mm 网格）、对边/邻边成功数、拥塞热点、对称性、端口附近密集度。

## 7. 参数敏感性矩阵（Phase 11）

在代表性拓扑 + 算法（默认 V1 + B，两个平面分别）下对比：

| 配置 | 最小半径 | 最小边缘间距 | 中心线净空 |
|---|---:|---:|---:|
| 旧基线 O | 5 mm | 125 µm | 0.175 mm |
| 只改间距 G | 5 mm | 30 µm | 0.080 mm |
| 只改半径 R | 40 mm | 125 µm | 0.175 mm |
| 新工艺 N | 40 mm | 30 µm | 0.080 mm |

四组都必须在**同一双高度平面模型**中跑（不能拿上一轮单层虚拟展开的 462 当基线直接比）。
若某项无法完成，记录未完成原因。

## 8. 交付目录

```
outputs/four_side_1024_fslw_R40_gap30_abcd/
  config_process.json            # 本轮工艺参数 + fixed_radius_40mm + 端口模型 + 预算 + 种子
  connectivity/                  # 双高度真实 2×16 端口模型校验、物理坐标、V1/V2 连接图
  feasibility/                   # Phase-2 单路线/族可行性 + 网格可行性图
  planes/<TOPOLOGY>/<ALGO>/<PLANE>/    # z1 / z2：routes.json, failed_routes.json,
                                       #   statistics.json, audit_strict.json, run.log,
                                       #   routing_all.png/svg/gds, config.json
  combined/<TOPOLOGY>/<ALGO>/          # routes_1024.json（含 z 标签）、statistics.json、
                                       #   layer_2d.png/svg、overlay_3d.png、planes_summary.json
  sensitivity/<CONFIG>/                # O/G/R/N × 2 平面 × V1+B
  comparison/                    # 八组对比、参数敏感性对比、交叉热图、半径检查图、
                                 #   all_metrics.csv/json、strict_audit_summary.json
  report/                        # 报告副本
```

`routes.json` 沿用 `d56/SPEC.md` §3.1 的 schema（含 `status/primitives/length_mm/bend_count/
candidate`；失败含 `reason/evaluated/blockers`），并增加：`plane`（z1/z2）、`z_mm`（模型值）、
`port_model`（`real_2x16_dual_height`）、`process`（R/gap/clearance/loss）。

## 9. 端点与坐标（每平面）

`ports.py` 生成 `(routes, endpoints, connectors, validation)`，`endpoints[key]` 至少含：
`endpoint_id, connector, side, row, column, channel, routing_xy, inward, layer=0,
plane(z1/z2), z_mm, physical_along_mm, physical_row_z_mm`。
`routes` 增加 `plane, row`；`pair`/`relation` 沿用 CSV。
**CSV 原有配对与 route_id 一律不改。**

## 10. 可视化契约

- 每个平面：整板 PNG（200 dpi，`[-9,159]²`，按边对固定配色，标题含真实布通数/512 与平面名）+
  SVG + GDS（该平面 layer 0）。
- 组合：2D 分层图（z1 与 z2 两联或叠加、用高度区分）、3D 叠加示意图（matplotlib 3D，z1/z2 各一层，
  跨平面投影交叉不作为违规）、八组布通率对比、参数敏感性对比、交叉热图、半径检查图、
  拥塞放大图。
- 所有整板图统一坐标范围/线宽/配色，可直接比较。GDS：每平面单独 layer 0；组合 GDS 用
  layer 0 = z1、layer 1 = z2，并在文件名/说明中标明这是两个物理高度而非同一层。

## 11. 代码所有权（避免写冲突）

| 路径 | 所有者 |
|---|---|
| `fslw/SPEC.md`, `fslw/config.py`, `fslw/ports.py`, `fslw/geom.py`, `fslw/candidates.py`, `fslw/strategies.py`, `fslw/search.py`, `fslw/d_lns.py`, `fslw/run.py`, `fslw/feasibility.py`, `fslw/loss.py`, `docs/reports/...md` | Lead |
| `fslw/validate_fslw.py`, `fslw/crosscheck_fslw.py`, `fslw/tests_fslw/test_validate_fslw.py` | validator |
| `fslw/metrics.py`, `fslw/plots.py`, `fslw/combine.py`, `fslw/compare.py`, `fslw/tests_fslw/test_metrics_fslw.py` | viz |
| `fslw/ports_audit.py`, `fslw/tests_fslw/test_ports_fslw.py`, `outputs/.../connectivity/` | connectivity |

不得修改他人所有权文件；不得修改 `d56/**`、`abcd/**`、上一轮输出。

## 12. 变更记录

- v1（Lead，2026-10-19）：初始契约。明确双高度真实 2×16 端口模型（row1→z1 对边、row2→z2 邻边、
  平面内 layer=0、跨平面投影交叉不算冲突、无 z 过渡、不宣称可制造）、R=40 fixed_radius_40mm、
  0.08 mm 中心线净空、复用 abcd 的 strict 局部交叉窗口定义、16 平级实验 + 8 组合布局 +
  4 配置敏感性、损耗只报传播项、产物与所有权。
