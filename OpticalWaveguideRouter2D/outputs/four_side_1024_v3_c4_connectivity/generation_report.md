# 光纤板 1024 通道 V3-C4 四重旋转对称连接表 生成报告

- 生成时间（本地）：2026-10-21T00:26:43+08:00
- 生成时间（UTC）：2026-10-20T16:26:43+00:00
- 生成脚本：`generate_v3_c4.py`（version 1.0.0，SHA256 `e18798a92c61c2e0adc5c79d2dcdf8cf7cb62cea6d64fb84e0053ffee3812ca5`）
- 输出目录：`C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\outputs\four_side_1024_v3_c4_connectivity`

## 1. 结论摘要

- CSV 共 **1024** 条连接，2048 个物理端口各使用一次，64 个接头各使用 32 个通道。
- row1（z=0.0 mm）对边 512 条（NS 256 + EW 256）从 V2 **原样保留**；row2（z=0.5 mm）邻边 512 条（NE/ES/SW/WN 各 128）为全新 **V3-C4** 设计。
- 全连接集合在物理端口级严格满足 90°/180°/270° 旋转对称（闭合缺失均为 0），共 256 个四元旋转组。
- 邻边 512 条采用“角部嵌套方角 L”构造（每个角 128 条，边长 5.625–72.375 mm），在 row2 平面内的 L 型交叉代理计数为 **0**。
- 内置校验：**39 PASS / 0 FAIL**（详见第 6 节与 `validation_v3_c4.json`）。

## 2. 输入与来源

| 文件 | 路径 | SHA256 | 用途 |
|---|---|---|---|
| V2 连接表（冻结输入） | `C:\Users\lihao\Desktop\optical_1024_multitomulti_connectivity_v2_symmetric.csv` | `49dd9e89c4ea506d04638ae34eb06a0d8163d479de80869804c881ee1c43915e` | row1 对边 512 条原样继承 |
| V1 连接表（历史输入） | `C:\Users\lihao\Desktop\optical_1024_multitomulti_connectivity_v1.csv` | `0ecce47109f9223e8407928c423ad5d9272186938cc267877a6158936e0e428b` | 仅作历史对照，未修改、未使用 |
| 上传参考 CSV（黄志杰风格光纤配对） | `C:\Users\lihao\Desktop\fiberBoard1024_黄志杰风格_光纤配对.csv.csv` | `76d91316e0933a64b8c822fd541faa2bda571fdef97e49b64f75b55cf4a6cf23` | 仅核对接口/配对组织 |
| 上传参考 XLSX（黄志杰风格四边接口连接） | `C:\Users\lihao\Desktop\fiberBoard1024_黄志杰风格_四边接口连接.xlsx.xlsx` | `4d285f5667fa922849b3371525944e12feca1dae1bc07c0d5cd40be3b38b32de` | 仅核对端口/Excel 组织 |

参考文件与仓库 `data/v3_huang/` 下 V3-Huang 输入文件 SHA256 相同；其拓扑（same 448 / opposite 384 / adjacent 192，含 448 条同边连接，现有 ports.py/inputs 加载器会拒绝同边连接）与本次要求的 V3-C4 方案不同，未被采用。参考 XLSX 实际为 7 个 Sheet（Sheet1、接口映射、连接类别统计、64x64连接矩阵、光纤级连接_参考、接头对重数、生成说明），本任务按需求输出 5 个 Sheet。

## 3. 物理端口模型（four_side_1024/fslw/ports.py）

- 接头中心沿边坐标 `7.5 + 9*(i-1)` mm（i=1..16），同排光纤列距 0.25 mm，第 j 列沿边坐标 `along = 7.5+9*(i-1)+(j-8.5)*0.25`。
- 端口坐标：`N(i,j)=(along,150)`，`S(i,j)=(along,0)`，`E(i,j)=(150,along)`，`W(i,j)=(0,along)`；row1 → z=0.0 mm，row2 → z=0.5 mm（两排同属逻辑接口层 L1）。
- 板中心 (75,75) 的 90° 逆时针旋转：`rot90(x,y)=(150-y,x)`。
- 端口身份上的旋转映射：`T(N(i,j))=W(i,j)`，`T(W(i,j))=S(17-i,17-j)`，`T(S(i,j))=E(i,j)`，`T(E(i,j))=N(17-i,17-j)`；四元轨道 `O(i,j)={N(i,j),W(i,j),S(17-i,17-j),E(17-i,17-j)}`。

## 4. 设计方法

### 4.1 row1 对边 512 条：原样继承 V2

先用真实物理端口坐标验证 V2 对边 512 条：rot90/rot180/rot270 闭合缺失均为 0（严格 C4 对称），因此 route_id 1..512 逐字段原样复制。V2 的配对规律为 N(i,j)→S(f(i,j))、E(i,j)→W(f(i,j))，其中 f 为 4×4 块转置映射：令 i−1=4p+q、j−1=4r+s（p,q,r,s∈0..3），则 f(i,j)=(4p+r+1, 4q+s+1)，且 f 为对合（f∘f=id）。

### 4.2 row2 邻边 512 条：256 个端口轨道 → 128 个连接轨道

row2 的 1024 个端口分为 256 个四元旋转轨道；取 A = `X(i,j) > 75` 的 128 个轨道（connector 9–16），B = 其余 128 个（connector 1–8）。配对规则为镜像配对 `O(i,j) ↔ O(17-i,17-j)`（物理沿边坐标 X ↔ 150-X）。每个轨道对展开为 4 条连接：

| 组内相位 | 连接 | 说明 |
|---|---|---|
| 0° | N(i,j) – E(i,j) | 东北角，边长 150-X |
| 90° | W(i,j) – N(17-i,17-j) | 西北角 |
| 180° | S(17-i,17-j) – W(17-i,17-j) | 西南角 |
| 270° | E(17-i,17-j) – S(i,j) | 东南角 |

即：每个角部有 128 条嵌套的 90° L（边长 d=150-X(i,j)，d∈[5.625, 72.375] mm），四角互为旋转副本；连接集合由旋转闭包构造，因此端口级 90° 对称是构造性的，并已由独立读回校验确认。

### 4.3 配对方法快速比较（L 型代理）

| 方案 | 交叉数 | 重叠数 | 总长度(mm) | 腿长<15mm 条数 | 最短腿(mm) | 旋转缺失(90/180/270) |
|---|---:|---:|---:|---:|---:|---|
| A_nested_mirror_X_150-X (chosen) | 0 | 0 | 39936.0 | 72 | 5.625 | 0/0/0 |
| B_mirror_bottom_perimeter | 131584 | 512 | 113664.0 | 0 | 77.625 | 0/0/0 |
| C_random_matching_seed20261021 | 14700 | 0 | 39936.0 | 128 | 5.625 | 0/0/0 |
| D_v2_original_adjacent | 61824 | 256 | 75776.0 | 64 | 5.625 | 512/512/512 |

A（选用）交叉/重叠均为 0，总长度最短；B 零短腿但周长式长线导致大量交叉；C 为随机对称匹配；D 为原 V2 邻边（不具备 90° 旋转对称）。

## 5. R15 几何难度记录（预估，不代表布通）

- 工艺：R=15 mm，波导宽 0.05 mm，边缘间距 0.03 mm，非豁免中心线净空 0.08 mm。
- 邻边 512 条的单层单弯 L 估计：腿长范围 5.625–72.375 mm；其中 **72** 条（每类 18 条，四类共 72 条）较短腿 < R=15 mm，单层 R15 单弯 L 不可行，需要局部 L3D 过渡或绕行（CSV 只定义连接关系，不固定路径）。

| 较短腿 d (mm) | 连接条数 | 示例 route_id |
|---:|---:|---|
| 5.625 | 4 | 640, 641, 769, 1024 |
| 5.875 | 4 | 639, 642, 770, 1023 |
| 6.125 | 4 | 638, 643, 771, 1022 |
| 6.375 | 4 | 637, 644, 772, 1021 |
| 6.625 | 4 | 636, 645, 773, 1020 |
| 6.875 | 4 | 635, 646, 774, 1019 |
| 7.125 | 4 | 634, 647, 775, 1018 |
| 7.375 | 4 | 633, 648, 776, 1017 |
| 7.625 | 4 | 632, 649, 777, 1016 |
| 7.875 | 4 | 631, 650, 778, 1015 |
| 8.125 | 4 | 630, 651, 779, 1014 |
| 8.375 | 4 | 629, 652, 780, 1013 |
| 8.625 | 4 | 628, 653, 781, 1012 |
| 8.875 | 4 | 627, 654, 782, 1011 |
| 9.125 | 4 | 626, 655, 783, 1010 |
| 9.375 | 4 | 625, 656, 784, 1009 |
| 14.625 | 4 | 624, 657, 785, 1008 |
| 14.875 | 4 | 623, 658, 786, 1007 |

- 对边 512 条（继承 V2）的端点平行偏移统计（两弧 R15 S 过渡几何估计）：

| 沿边偏移 δ (mm) | 连接条数 |
|---:|---:|
| 0.000 | 128 |
| 8.000 | 192 |
| 16.000 | 128 |
| 24.000 | 64 |

  所有对边连接的 δ ≤ 24 mm ≤ 2R=30 mm，几何上可用两段 R15 圆弧 S 过渡；实际布线仍需全局排布。

## 6. 验证结果（对已保存文件重新读取后校验）

| ID | 类别 | 检查项 | 期望 | 实际 | 结果 |
|---|---|---|---|---|---|
| C01 | CSV结构 | CSV 表头与项目现有格式完全一致（固定 12 列，顺序不变） | 固定 12 列表头 | 12 列 | PASS |
| C02 | CSV结构 | CSV 数据行数恰好 1024 | 1024 | 1024 | PASS |
| C03 | CSV结构 | CSV 使用 UTF-8-SIG（含 BOM）编码 | True | True | PASS |
| C04 | CSV结构 | CSV 行尾为 CRLF | True | True | PASS |
| C05 | CSV结构 | 每行 12 个字段、无额外列 | True | True | PASS |
| C06 | CSV结构 | route_id 为 1..1024 连续且唯一 | 1..1024 连续且唯一 | 数量=1024, 最小=1, 最大=1024 | PASS |
| C07 | CSV结构 | source/target 位于不同边 | 1024 | 1024 | PASS |
| C08 | CSV结构 | connector/row/column/channel 符合物理端口编号规则 | [] | [] | PASS |
| C09 | CSV结构 | relation 取值与两端边类别一致 | [] | [] | PASS |
| C10 | 连接分布 | 对边/邻边类别计数：NS 256, EW 256，邻边四类（EN/ES/SW/NW 排序键）各 128 | {'NS': 256, 'EW': 256, 'EN': 128, 'ES': 128, 'SW': 128, 'NW': 128} | {'NS': 256, 'EW': 256, 'EN': 128, 'ES': 128, 'SW': 128, 'NW': 128} | PASS |
| C11 | 连接分布 | relation 计数：opposite 512, adjacent 512 | {'opposite': 512, 'adjacent': 512} | {'opposite': 512, 'adjacent': 512} | PASS |
| C12 | 连接分布 | 有向边对计数 N→S 256, E→W 256, N→E/E→S/S→W/W→N 各 128 | {'N->S': 256, 'E->W': 256, 'N->E': 128, 'E->S': 128, 'S->W': 128, 'W->N': 128} | {'N->S': 256, 'E->W': 256, 'N->E': 128, 'E->S': 128, 'S->W': 128, 'W->N': 128} | PASS |
| C13 | 行/层分配 | 所有连接 source_row==target_row；对边全为 row1、邻边全为 row2 | [] | [] | PASS |
| C14 | 端口占用 | 2048 个物理端口各被使用且仅使用一次 | {'unique_ports': 2048, 'usage_counts': [1]} | {'unique_ports': 2048, 'usage_counts': [1]} | PASS |
| C15 | 端口占用 | 每边 512 个端口（每排 256）全部使用 | {'N': 512, 'E': 512, 'S': 512, 'W': 512} | {'N': 512, 'E': 512, 'S': 512, 'W': 512} | PASS |
| C16 | 端口占用 | 64 个接头各使用 32 个不同通道（16 列 × 2 排） | {64: 32} | {64: 32} | PASS |
| C17 | 端口坐标 | CSV 端口身份与 fslw/ports.py 物理坐标公式一致（全部 2048 次使用） | [] | [] | PASS |
| C18 | 端口坐标 | 与仓库 four_side_1024/fslw/ports.py 的 build_plane_endpoints() 坐标完全一致 | [] | [] | PASS |
| C19 | 行/层分配 | 物理高度：row1 -> z=0.0 mm，row2 -> z=0.5 mm | {'row1_z': 0.0, 'row2_z': 0.5} | {'row1_z': 0.0, 'row2_z': 0.5} | PASS |
| C20 | 旋转对称 | 全连接集合 rot90 后仍为同一无序连接集合（端口级） | 0 | 0 | PASS |
| C21 | 旋转对称 | 全连接集合 rot180 后仍为同一无序连接集合（端口级） | 0 | 0 | PASS |
| C22 | 旋转对称 | 全连接集合 rot270 后仍为同一无序连接集合（端口级） | 0 | 0 | PASS |
| C23 | 旋转对称 | 每条连接在其四元旋转轨道中有另外 3 条连接（共 256 组） | {'groups': 256, 'group_size': 4} | {'groups': 256, 'bad': 0} | PASS |
| C24 | V2继承 | V2 CSV SHA256 与冻结值一致 | 49dd9e89c4ea506d04638ae34eb06a0d8163d479de80869804c881ee1c43915e | 49dd9e89c4ea506d04638ae34eb06a0d8163d479de80869804c881ee1c43915e | PASS |
| C25 | V2继承 | V2 对边 512 条（route_id 1..512）在 V3 CSV 中逐字段完全一致 | 0 | 0 | PASS |
| C26 | V2继承 | V2 原对边 512 条在真实物理坐标下严格 90° 旋转对称（缺失数 0/0/0） | {'rot90': 0, 'rot180': 0, 'rot270': 0} | {'rot90': 0, 'rot180': 0, 'rot270': 0} | PASS |
| C27 | V2继承 | V2 对边 512 条保留、邻边 512 条未被整体继承（重新设计） | {'kept_opposite': 512, 'v2_adjacent_fully_reused': False} | {'kept_opposite': 512, 'same_connections_as_v2_adjacent': 32, 'v2_adjacent_fully_reused': False} | PASS |
| C28 | 格式约定 | route_id 分块沿用 V2 习惯：NS 1-256 / EW 257-512 / NE 513-640 / ES 641-768 / SW 769-896 / WN 897-1024 | True | True | PASS |
| C29 | 几何参数 | 接口与工艺参数与现有配置一致 | {'board_mm': [150.0, 150.0], 'connector_pitch_mm': 9.0, 'first_center_mm': 7.5, 'column_pitch_mm': 0.25, 'row_pitch_mm': 0.5, 'rows': 2, 'columns': 16, 'connectors_per_side': 16, 'z_row1_mm': 0.0, 'z_row2_mm': 0.5, 'min_radius_mm': 15.0, 'waveguide_width_mm': 0.05, 'min_edge_gap_mm': 0.03, 'min_clearance_mm': 0.08} | {'board_mm': [150.0, 150.0], 'connector_pitch_mm': 9.0, 'first_center_mm': 7.5, 'column_pitch_mm': 0.25, 'row_pitch_mm': 0.5, 'rows': 2, 'columns': 16, 'connectors_per_side': 16, 'z_row1_mm': 0.0, 'z_row2_mm': 0.5, 'min_radius_mm': 15.0, 'waveguide_width_mm': 0.05, 'min_edge_gap_mm': 0.03, 'min_clearance_mm': 0.08} | PASS |
| C30 | 文件安全 | 历史 V1/V2 CSV 未被修改（SHA256 不变） | {'V1': '0ecce47109f9223e8407928c423ad5d9272186938cc267877a6158936e0e428b', 'V2': '49dd9e89c4ea506d04638ae34eb06a0d8163d479de80869804c881ee1c43915e'} | {'V1': '0ecce47109f9223e8407928c423ad5d9272186938cc267877a6158936e0e428b', 'V2': '49dd9e89c4ea506d04638ae34eb06a0d8163d479de80869804c881ee1c43915e'} | PASS |
| E01 | Excel结构 | 工作簿可被 openpyxl 正常打开且恰好 5 个 Sheet | ['1024连接总表', '四边接口表', '旋转对称组', '统计与验证', '来源与说明'] | ['1024连接总表', '四边接口表', '旋转对称组', '统计与验证', '来源与说明'] | PASS |
| E02 | Excel总表 | Sheet1 连接总表 1024 行，前 12 列与 CSV 表头一致 | {'rows': 1024, 'csv_fields': ['route_id', 'source_side', 'source_connector', 'source_row', 'source_column', 'source_channel', 'target_side', 'target_connector', 'target_row', 'target_column', 'target_channel', 'relation']} | {'rows': 1024, 'csv_fields': ['route_id', 'source_side', 'source_connector', 'source_row', 'source_column', 'source_channel', 'target_side', 'target_connector', 'target_row', 'target_column', 'target_channel', 'relation']} | PASS |
| E03 | Excel总表 | Excel 1024 条连接的 12 个 CSV 字段与 CSV 完全一致（含坐标/Z 高度） | [] | [] | PASS |
| E04 | Excel接口表 | Sheet2 四边接口表恰好 2048 行 | 2048 | 2048 | PASS |
| E05 | Excel接口表 | 2048 个物理端口各出现一次、坐标/Z/对端端口与 CSV 一致 | {'unique': 2048, 'used_once': True} | {'unique': 2048, 'used_once': True} | PASS |
| E06 | Excel旋转组 | Sheet3 旋转对称组恰好 256 组（每组 4 条路线） | {'groups': 256, 'routes': 1024} | {'groups': 256, 'routes': 1024} | PASS |
| E07 | Excel旋转组 | 每个旋转组的 0°/90°/180°/270° 路线经 rot90 严格依次对应，且覆盖全部 1024 条 | {'unique_routes': 1024, 'phase_errors': 0} | {'unique_routes': 1024, 'phase_errors': 0} | PASS |
| E08 | Excel格式 | 三个数据表均冻结表头并启用自动筛选 | {'1024连接总表': 'freeze+filter', '四边接口表': 'freeze+filter', '旋转对称组': 'freeze+filter'} | {'1024连接总表': 'freeze+filter', '四边接口表': 'freeze+filter', '旋转对称组': 'freeze+filter'} | PASS |
| E09 | Excel说明 | Sheet4 统计与验证、Sheet5 来源与说明均非空 | {'sheet4_rows>0': True, 'sheet5_rows>0': True} | {'sheet4_rows>0': True, 'sheet5_rows>0': True} | PASS |

合计 **39 PASS / 0 FAIL**。

除上述内置读回校验外，另由独立验收员以**不同实现**重写端口模型与旋转映射后复核：86 项独立检查 86 PASS / 0 FAIL（未复用本生成脚本），并额外用 pandas 读回 Excel、随机抽查 20 条连接（seed=20261021）全部一致。

## 7. 与上传参考文件（黄志杰风格 V3-Huang）的区别

| 项目 | 黄志杰参考 | 本 V3-C4 |
|---|---|---|
| 拓扑来源 | 上传光纤配对 CSV | 保留 V2 对边 + C4 邻边重设计 |
| same（同边） | 448（NN/SS/EE/WW 各 112） | 0 |
| opposite（对边） | 384（NS 192 + EW 192） | 512（NS 256 + EW 256） |
| adjacent（邻边） | 192（NE/NW/ES/SW 各 48） | 512（NE/ES/SW/WN 各 128） |
| 旋转对称 | 未要求 | 端口级严格 C4（90/180/270 闭合 0 缺失） |
| 接口编号/物理模型 | 64 接头 × 2 排 × 16 列，row→z1/z2 | 相同（fslw/ports.py 物理模型） |
| Excel 组织 | 7 Sheet：Sheet1/接口映射/连接类别统计/64x64矩阵/光纤级连接_参考/接头对重数/生成说明 | 5 Sheet：总表/四边接口表/旋转对称组/统计与验证/来源与说明（按本任务要求） |

## 8. 输出文件与哈希

| 文件 | SHA256 | 说明 |
|---|---|---|
| `optical_1024_multitomulti_connectivity_v3_c4_symmetric.csv` | `de7e382d3fbf94033eb323ccc64914739e14bde5793191389341896b717f0430` | 1024 条连接，UTF-8-SIG，CRLF |
| `fiberBoard1024_V3_C4_四边旋转对称连接表.xlsx` | `7d68efdfb3ef76676d1877723290af18093417ad8d288f34b17df77bec9fe419` | 5 Sheet 检查工作簿 |
| `validation_v3_c4.json` | 见文件本身 | 全部 PASS/FAIL 校验记录 |
| `generation_report.md` | 见文件本身 | 本报告 |
| `pairing_comparison_v3_c4.json` | 见文件本身 | 配对方法比较 |

## 9. 复现

```powershell
cd "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\outputs\four_side_1024_v3_c4_connectivity"
python generate_v3_c4.py
python validate_v3_c4.py
```

`validate_v3_c4.py` 为独立验收脚本：不 import 生成脚本，重新读取已保存的 CSV/Excel 后重算端口坐标、端口占用、旋转闭合、V2 保留等检查。

## 10. 限制

- CSV 只定义物理连接关系，未预先固定波导路径/过渡层；未运行任何二维/三维布线实验。
- R15 项为端点几何估计，不代表实际布通结论；72 条短腿邻边连接需在布线阶段局部过渡/绕行。
- 邻边 L 型交叉数 0 / 重叠 0 为 axis-aligned 单弯 L 代理估计（由生成脚本计算，未做实际布线）；第三方复核覆盖了腿长/总长/短腿统计，未重算代理交叉，实际交叉数需由后续布线器给出。
- fslw/ports.py 导入交叉核对：未发现问题。
