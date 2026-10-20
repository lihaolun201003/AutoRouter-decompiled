# 五层 2.5D 实验数据格式（routes_25d.json v1）与独立验收规格

本文件是 `four_side_1024/fsd25d/` 五层（2.5D）实验的数据契约。任何读取/校验/绘图代码
都必须以本文件为准；不要 import 路由器内部实现来"自证"几何合法。

## 1. 目录与文件

```
outputs/four_side_1024_v2_25d_v01/
├─ schemeA/layers3/  schemeA/layers5/  schemeB/layers3/  schemeB/layers5/
│   ├─ routes_25d.json    # 本文件 §2 的完整三维路线数据
│   ├─ run_summary.json   # 运行配置与统计
│   └─ run.log
├─ _smoke/                # 小样本调试数据（10 条新增路线），格式与正式一致
├─ validation/            # 独立 3D 验收输出（validate25d.py 写这里）
├─ comparison/            # 对照图（plots25d.py 写这里）
└─ summary/               # 汇总统计（summarize25d.py 写这里）
```

## 2. `routes_25d.json` 顶层字段

| 字段 | 含义 |
|---|---|
| `schema` | 固定 `four_side_1024_v2_25d_routes_v1` |
| `scheme` | `A`（保留 Short-S 的 D56 基线 752）或 `B`（纯正交 90° 基线 262） |
| `n_layers` | 3 或 5 |
| `layers_z_mm` | 层高列表 mm，如 `[0, 0.125, 0.25, 0.375, 0.5]` |
| `interface_layer` | `{"z1": 0, "z2": n_layers-1}`：z1 平面接口在最低层 z=0，z2 在最高层 z=0.5 |
| `process` | 板面/宽度/边缘间距/净空/R/最小交叉角/交叉策略（strict） |
| `csv_sha256` | V2 连接 CSV 的 SHA256（应与已有验收一致） |
| `statistics` | 汇总统计（见 §4） |
| `router` | 运行过程信息（passes / rr / 时间） |
| `routes` | 1024 条记录（见 §3） |

## 3. 单条 route 记录

失败记录：

```json
{"route_id": 513, "plane": "z2", "pair": "EN", "relation": "adjacent",
 "status": "failed", "reason": "no_2d_candidate" | "no_lift_candidate",
 "baseline_2d": false, "interface_layer": 4, "interface_z_mm": 0.5,
 "port": {"p": [x,y], "q": [x,y], "start_tangent": [dx,dy], "end_tangent": [dx,dy]}}
```

成功记录（在失败记录字段基础上增加）：

```json
{"status": "routed", "baseline_2d": true/false,
 "mode": "flat" | "lifted",
 "family": "L" | "TURN_S" | ... , "params": {...},
 "travel_layer": 1..n-2 | null, "travel_z_mm": ... | null,
 "n_transitions": 0 | 2,
 "lifted": true/false, "xy_length_mm": ..., "length_mm": ...,   // 3D 长度
 "flat_length_mm": ..., "transition_length_mm": ..., "z_span_mm": ...,
 "port": {"p": [x,y], "q": [x,y], "start_tangent": [dx,dy], "end_tangent": [dx,dy]},
 "parts": [ ... ]}
```

`parts` 按 2D 路径顺序排列，两种：

**flat 平坦段** —— 在某层 z 上沿 2D 路径的一段子链（世界坐标 mm）：

```json
{"kind": "flat", "layer": 0, "z_mm": 0.0, "length_mm": 12.3,
 "primitives": [
   {"kind": "line", "p0": [x0,y0], "p1": [x1,y1]},
   {"kind": "arc", "p0": [x0,y0], "p1": [x1,y1], "center": [cx,cy],
    "radius": 40.0, "start_angle": rad, "sweep": rad}
 ]}
```

- 方案 A：flat 段内允许 D56 的直线/90° 弧/短 S 弧（`|sweep|` 任意，radius 恒 40）；
- 方案 B：flat 段内只允许轴对齐直线与 **恰好 90°** 的 R=40 弧；
- 公共约束：直线一律轴对齐（A/B 一致）；primitives 首尾相接、且与相邻 part 连续。

**transition 升降段** —— 竖直平面内的 S 曲线（两个 R=40 mm 圆弧）：

```json
{"kind": "transition",
 "start": [x,y], "end": [x,y],          // XY 投影的起止点
 "direction": [dx,dy],                   // XY 单位方向，等于所在直线段的走向
 "z0_mm": 0.0, "z1_mm": 0.125,
 "dz_mm": 0.125, "radius_mm": 40.0,
 "footprint_mm": 4.474,                  // = 2*R*sin(theta)
 "length_mm": 4.474}                     // = 2*R*theta
```

**S 曲线唯一定义（验收方独立重建）**：
`theta = acos(1 - |dz|/(2R))`，`footprint = 2R sin(theta)`，`dz = z1-z0`（可为负）。
水平投影沿 `direction`；用局部坐标 `(u,w)`：第一段圆弧 `u=R sinφ, w=z0+sign*R(1-cosφ)`，
`φ∈[0,theta]`；S 曲线关于中点 `M=(footprint/2, z0+sign*|dz|/2)` 中心对称，第二段为第一段
关于 M 的点反射（反向遍历）。世界坐标 `(x,y) = start + direction*u`，`z=w`。
transition 起点必须等于上一 part 的终点、终点等于下一 part 的起点（三维连续）；
起点/终点切向水平（与 flat 段切向一致）。

## 4. 验收必须检查的项目（独立 3D 验收，输出 JSON）

对每个 `schemeA/layers{3,5}`、`schemeB/layers{3,5}` 目录的 `routes_25d.json`：

1. **结构/连续性**：每条 routed 记录 parts 非空；相邻 part 三维端点重合（≤1e-6）；
   flat 段首尾与 2D 路径连续；`mode=flat` ⇒ n_transitions=0 且全部 part 为 flat；
   `mode=lifted` ⇒ n_transitions=2 且 part 顺序为 flat,transition,flat,transition,flat。
2. **端口**：每条 routed 记录的 3D 起点 z == interface_z_mm(z1 为 0、z2 为 0.5)，
   终点 z == 目标接口高度；XY 起终点与 `port.p/port.q` 一致；起点 XY 切向与
   `start_tangent` 一致、终点切向与 `end_tangent` 一致（≤1e-6），且 z 向切向为 0。
3. **XY 几何模型**：方案 B 的 flat 段只允许轴对齐直线 + R=40、`|sweep|=90°` 的弧；
   方案 A 允许 D56 三种图元；两者 transition 的 `direction` 必须轴对齐。
4. **曲率**：完整三维路径最小曲率半径 ≥ 40 mm（容差 0.1%，即 ≥39.96）。必须从
   **三维采样点**独立估计（例如相邻三点外接圆半径，采样步长 ≤0.02 mm），
   并额外解析检查每个 transition 的 `theta/footprint/length` 满足上面的公式、每个 flat 弧
   radius=40、每个 flat 直线曲率为 0。
5. **三维净空**：任意两条不同路线之间真实三维中心线最小距离 ≥ 0.08 mm；
   例外仅限"同一层、按 strict 2D 规则合法的交叉"，且只在该交叉点附近（±2.5 mm）豁免。
   实现建议：细采样 + 空间网格；flat–flat 同层由 frozen strict 2D pair 审计负责
   （`fslw.validate_fslw.prepare_route` + `audit_route_pairs(policy='strict')`），
   其余（含 transition）必须真正三维计算。同层合法交叉从 2D 审计的 crossings 获得。
6. **多层 2D strict 规则**：按层收集所有 flat 段（作为独立 prepared route，id 唯一），
   每层调用 frozen `fslw.validate_fslw.audit_route_pairs(..., policy='strict')`：
   `violations` 必须为空；输出每层 crossings 数（=实际空间交叉数）与最小非交叉间距。
7. **端口切向与板界**：起终点切向如上；除端口面附近 0.5 mm 外，所有三维采样点 XY 距板边
   ≥0.025 mm（中心线半宽）。
8. **自净空**：同一路线自身非相邻部分的三维距离 ≥0.08 mm（路径参数差 >1 mm 的点对）。

输出（每个输入目录一个 JSON + 汇总 `validation/all_validation.json`）：

```json
{"schema": "four_side_1024_v2_25d_validation_v1",
 "input": ".../routes_25d.json", "scheme": "A", "n_layers": 5,
 "passed": true/false,
 "routed": 1234, "failed": 42,
 "min_3d_distance_mm": 0.0812, "min_3d_distance_excluding_crossings_mm": 0.0812,
 "min_curvature_radius_mm": 40.001,
 "crossings": {"total": 86143, "by_layer": {"0": 71362, "4": 14779, ...}},
 "violations": [ {"kind": "...", "route_id": ..., "other_route": ..., "detail": "..."} ],
 "counts": {"violations": 0, "structure_errors": 0, "port_errors": 0,
            "xy_model_errors": 0, "curvature_violations": 0,
            "clearance_violations": 0, "layer_2d_violations": 0,
            "self_clearance_violations": 0, "board_violations": 0},
 "stats": {"transitions": ..., "lifted": ..., "total_length_mm": ...}}
```

`passed` 仅在全部 counts 为 0 且 min_3d_distance ≥0.08（豁免交叉后）时可为 true。
**不得**把任何二维 PASS 直接当作 3D PASS。

## 5. 允许/需要复用的权威代码

- `four_side_1024.fslw.validate_fslw.prepare_route / audit_route_pairs(policy='strict')`
  —— 同层 2D strict 规则的权威实现（只用于按层的 2D 审计）；
- `four_side_1024.fslw.config`（板面/宽度/净空/R/交叉角）；
- `four_side_1024.fslw.ports.load_plane('V2', plane)` —— V2 端口/连接 CSV（核对端口与 SHA）。

**禁止**在验收实现里 import `fsd25d.router25d` / `fsd25d.world25d` / `fsd25d.path3d`
（避免用路由器自己的几何/净空判断自证合法）。可以 import `fsd25d.config25d` 的常量。

## 6. 调试样本

`outputs/four_side_1024_v2_25d_v01/_smoke/routes_25d.json` 是 B/5 层、仅 10 条新增路线
的合法样本（262 基线 + 10 抬升，共 272 routed）。正式 4 个目录（A3/A5/B3/B5）在
`run25d.py` 完成后出现。
