# FSLW 双高度真实 2×16 MPO 端口模型校验（connectivity / Phase 1）

> **重要声明（本文所有坐标为“双高度接口假设”下的仿真坐标，不是可制造性结论）**
>
> - 本模块与产物中的坐标是 **仿真坐标**（two-height interface assumption）：`z1 = 0.0 mm`、`z2 = 0.5 mm` 为模型值；
> - **本轮未实现任何 z 方向过渡**（无 via / taper / fanout）；
> - **玻璃厚度与接头安装方向尚未确认**；
> - **9 mm 接头间距下的机械干涉尚未解决**：暂定 MPO 外壳包络 12.59 mm > 间距 9.0 mm，相邻外壳重叠 3.59 mm（光纤跨距仅 3.75 mm 本身不重叠）；
> - **跨平面的 XY 投影重叠不是同层冲突**：z1 / z2 相距 0.5 mm，冲突判定只在同一平面内进行。

生成脚本：`four_side_1024/fslw/ports_audit.py`（`python -m four_side_1024.fslw.ports_audit`）；本 README 及全部 JSON/CSV/PNG 由该脚本一次运行生成，所有数字均为实测，无手工填写。

## 1. 模型（独立重新推导，不复用 `fslw/ports.py`）

| 项 | 值 |
|---|---|
| 接口标准 | IEC 61754-7-3:2019 2×16 MPO |
| 同排纤芯列距 | 0.25 mm |
| 两排中心距（z1→z2） | 0.5 mm |
| 每接头光纤 | 2 排 × 16 列 = 32 根 |
| 板面 / 接头数 | 150 × 150 mm，4 边 × 16 = 64 个接头 |
| 接头中心 | `connector_center = (150 − 15×9)/2 + (c−1)×9 = 7.5 + (c−1)×9` mm（c = 1..16） |
| 端口沿边坐标 | `along = connector_center + (column − 8.5) × 0.25` mm |
| 平面规则 | CSV `row=1` → `z1=0.0 mm`（512 对边：NS 256 + EW 256）；`row=2` → `z2=0.5 mm`（512 邻边：EN/ES/SW/NW 各 128） |
| 每平面端口 | 4 边 × 16 接头 × 16 列 = 1024，恰好各用一次 |
| 2D 布线坐标 | 端口的板边投影（丢弃 z）；层 `layer=0`，平面内独立二维寻路 |

## 2. 校验结果

### V1（SHA256 `0ecce47109f9223e8407928c423ad5d9272186938cc267877a6158936e0e428b`）

- 总体：**PASS**；failed_checks = []
- 连接：1024 条；relation = {'opposite': 512, 'adjacent': 512, 'pairs': {'NS': 256, 'EW': 256, 'EN': 128, 'ES': 128, 'SW': 128, 'NW': 128}}
- 端点：2048 个物理端口（64 接头 × 32 纤芯）各用一次；每个接头覆盖全部 32 通道 = 64/64
- 平面 z1（row 1, z = 0.0 mm）：512 条连接、1024 个端点、1024/1024 个端口恰好各一次、relation = {'opposite': 512, 'adjacent': 0}、along 公式最大误差 0.0e+00 mm、routing_xy 最大误差 0.0e+00 mm
- 平面 z2（row 2, z = 0.5 mm）：512 条连接、1024 个端点、1024/1024 个端口恰好各一次、relation = {'opposite': 0, 'adjacent': 512}、along 公式最大误差 0.0e+00 mm、routing_xy 最大误差 0.0e+00 mm
- 列距 0.25 mm：实测 [0.25]；两排 z 间隔 0.5 mm
- CSV→端点编号一致性：channel/row/column 违规 0；同边连接 0；重复连接 0
- 与上一轮历史记录的 `physical_projected_xy` 交叉核对：2048 个端点，最大偏差 0.0 mm（该历史文件只读，仅作旁证）
- 与 Lead `fslw/config.py` 常量核对：mismatches = []
- 机械包络告警：包络 12.59 mm / 间距 9.0 mm，重叠 3.59 mm（保留告警，非端口模型失败）

### V2（SHA256 `49dd9e89c4ea506d04638ae34eb06a0d8163d479de80869804c881ee1c43915e`）

- 总体：**PASS**；failed_checks = []
- 连接：1024 条；relation = {'opposite': 512, 'adjacent': 512, 'pairs': {'NS': 256, 'EW': 256, 'EN': 128, 'ES': 128, 'SW': 128, 'NW': 128}}
- 端点：2048 个物理端口（64 接头 × 32 纤芯）各用一次；每个接头覆盖全部 32 通道 = 64/64
- 平面 z1（row 1, z = 0.0 mm）：512 条连接、1024 个端点、1024/1024 个端口恰好各一次、relation = {'opposite': 512, 'adjacent': 0}、along 公式最大误差 0.0e+00 mm、routing_xy 最大误差 0.0e+00 mm
- 平面 z2（row 2, z = 0.5 mm）：512 条连接、1024 个端点、1024/1024 个端口恰好各一次、relation = {'opposite': 0, 'adjacent': 512}、along 公式最大误差 0.0e+00 mm、routing_xy 最大误差 0.0e+00 mm
- 列距 0.25 mm：实测 [0.25]；两排 z 间隔 0.5 mm
- CSV→端点编号一致性：channel/row/column 违规 0；同边连接 0；重复连接 0
- 与上一轮历史记录的 `physical_projected_xy` 交叉核对：2048 个端点，最大偏差 0.0 mm（该历史文件只读，仅作旁证）
- 与 Lead `fslw/config.py` 常量核对：mismatches = []
- 机械包络告警：包络 12.59 mm / 间距 9.0 mm，重叠 3.59 mm（保留告警，非端口模型失败）

## 3. 物理 3D 端口坐标（独立于二维布线坐标保存）

- `physical_ports_v1.csv` / `physical_ports_v2.csv`：各 2048 行 = 64 接头 × 32 根光纤；列：`topology, side, connector, row, column, channel, plane, x_mm, y_mm, z_mm, along_mm, plane_row, connector_center_mm, inward_x, inward_y, port_model`。
- 3D 坐标唯一：2048/2048；z1 平面 1024 个、z2 平面 1024 个；
- (x, y) 投影只有 1024 个不同位置，1024 个端口在 XY 投影上“重合”——这是两个高度平面在同一 XY 上的投影，**不是同层冲突**。
- 两个拓扑共用同一套 2048 个物理端口（端口几何与拓扑无关），V1/V2 CSV 仅在 `topology` 列不同。

## 4. 与 Lead `fslw/ports.py` 的独立对比

- 对比方式：在独立子进程中运行 `fslw/ports.py`，与本文推导逐字段对比（`ports_audit.py` 不在导入期依赖 `ports.py`）。
- 被对比的 `ports.py`：SHA256 `1bc96f1f04a2ab4bd185c1305c32ce6259ee3008dfdbb1eaf97f11e6a62d5249`，11648 bytes，mtime 2026-10-19 18:22:38。
- 2048 个 `(connector,row,column)` 身份集合是否相同：**True**；routing_xy 最大偏差 **0.0 mm**；physical_along 最大偏差 0.0 mm；z 最大偏差 0.0 mm。
- 端点 row→plane 不一致数：0；每个拓扑 route 字段不一致数：{'V1': 0, 'V2': 0}；row→plane 不一致 route：{'V1': 0, 'V2': 0}；物理端口表坐标最大偏差：{'V1': 0.0, 'V2': 0.0}。
- 对比结论：**PASS — 完全一致**（详见 `lead_ports_comparison.json`）。
- 顺带发现（不阻塞，供 Lead 参考）：
  - ports.load_plane / ports.all_routes do NOT set route["row"] although SPEC §9 asks for it; this comparison falls back to route["source_row"].
  - ports.validate_plane duplicate route_id check compares a list to itself (sorted(...) != sorted(...)) -> always False; harmless because load_plane already guarantees 512 unique CSV route ids, but the guard is a no-op.
  - ports.validate_plane non-finite coordinate check is abs(x - x) > 0 -> always False; invalid/NaN routing_xy would not be caught by ports.py (our audit checks coordinates directly).
  - ports.load_plane skips row-mixing detection for routes whose source row does not match the plane (continue before the target_row check); our audit checks both roles.

## 5. 文件清单

| 文件 | 内容 |
|---|---|
| `ports_validation_v1.json` / `ports_validation_v2.json` | 双高度端口模型逐项校验（本文件第 2 节数字的完整结构化版本） |
| `physical_ports_v1.csv` / `physical_ports_v2.csv` | 2048 个真实 3D 物理端口坐标 (x, y, z1/z2, along, side/connector/row/column/channel) |
| `plane_connectivity_v1_z1.png` `plane_connectivity_v1_z2.png` `plane_connectivity_v2_z1.png` `plane_connectivity_v2_z2.png` | V1/V2 × z1/z2 四个平面的连接关系图（每平面 512 条） |
| `dual_height_schematic.png` | 双高度 2×16 接口剖面示意（0.25 mm 列距、0.5 mm 两排间距、z1/z2、无 z 过渡） |
| `lead_ports_comparison.json` | 与 Lead `fslw/ports.py` 的逐字段对比结果 |
| `README.md` | 本文件 |

## 6. 重现

```powershell
cd "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D"
.\\.venv\\Scripts\\python.exe -m four_side_1024.fslw.ports_audit
.\\.venv\\Scripts\\python.exe -m pytest four_side_1024\\fslw\\tests_fslw\\test_ports_fslw.py -q
```

## 7. 已知限制 / 风险

1. **仿真假设**：z1=0.0 mm、z2=0.5 mm 是模型值；玻璃厚度、接头安装方向未确认。
2. **无 z 过渡**：没有 via/taper/fanout，两个平面在物理上如何连接到同一接头的两排光纤仍是一个假设；组合布局中的跨平面连线在真实器件中需要额外结构。
3. **机械干涉**：9 mm 接头间距与暂定 MPO 外壳包络 12.59 mm 不兼容（相邻重叠 3.59 mm），本轮端口模型不解决该问题。
4. **跨平面投影不是冲突**：z1/z2 的 XY 投影在同一点重合是设计使然，不得把跨平面的投影交叉计为同层违规；组合统计必须分开 `same_plane_crossings` 与 `cross_plane_projected_overlaps`。
5. **不可与上一轮数字直接比较**：上一轮为 0.175 mm 单层虚拟展开（R=5 mm / 125 µm 间距），端口模型不同，数据不可直接比。

