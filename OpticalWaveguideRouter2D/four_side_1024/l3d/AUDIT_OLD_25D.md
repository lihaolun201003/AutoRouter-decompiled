# 旧 2.5D（五层 / 25D）物理模型错误审计 —— R9 模型修正

- 审计编号：`R9-MODEL-AUDIT-01`
- 审计日期：2026-10-20
- 审计对象：`four_side_1024/fsd25d/`（旧五层 2.5D 模型）与 `four_side_1024/r15/run25d_r15.py` 产出的旧 25D 结果
- 对照基准：`four_side_1024/l3d/SCHEMA_L3D.md`（R9 修正后的 L1–L5 物理模型与 L3D 数据 schema）
- 机器可读证据：`four_side_1024/l3d/OLD_MODEL_FIELDS.json`（本审计的字段/数值/sha256 证据抽取，全部只读生成）
- 范围声明：本审计**只读**。未修改任何源码、未修改/重新生成任何旧输出，也未运行旧路由器或新 L3D 验证器；所有数字来自已交付的 JSON 产物，仅 sha256 为现场重算。

---

## 0. 结论摘要（先读这一段）

1. **旧 25D 模型（`fsd25d`）不是新 L1–L5 模型的近似，而是另一个物理问题。** 它把两个接口行放到两个不同的逻辑层：z1 → layer 0 / z=0.0，z2 → layer 4（最高层）/ z=0.5；并把 L2–L4 塞进 0–0.5 mm 之间（层高 0.125/0.25/0.375）。即：**把 0.5 mm 的 MPO 两排行距当成了整个五层高度域，把 z2 端口层当成了 L5 接口层。**
2. **旧 985（scheme A, layers5）/ 723（scheme B, layers5）是上述错误模型的解，不能作为 R9 的验收结果、基线或上限继承。** 其构成为 2D flat 基线（A 943 / B 515）+ 旧模型下抬升/下降的 lifted 路线（A 42 / B 208）；lifted 路线的中间高度 0.125/0.25/0.375 mm 在新模型中不存在，其逻辑层号 1..3 也不是新模型的 L2..L5。
3. **旧“五层 PASS”不能继承。** 旧 `validate25d.py` 的 PASS 只证明“在旧 stack 的旧规则下 0 violations”；它没有未确认高度/正式验收拒绝（`formal_acceptance`）概念，按逻辑层号做 2D 分组，跳过不同层 flat–flat 的真实 3D 检查，且**在字段层面无法解析新 L3D JSON**（`layer` vs `layer_id`、`z0_mm` vs `z0`、`interface_layer=4` vs `=1`、缺少 `layer_sequence`/`from_layer`/`to_layer` 等）。
4. **可以复用的只有 R15 已验收的二维 flat 几何**：A 943 条（z1 498 + z2 445）/ B 515 条（z1 184 + z2 331）可以作为 **L1 上的 flat 布局**（z1 行 z=0.0、z2 行 z=0.5），但必须放进**同一个真实 XYZ 环境**用新 L3D 验证器重新验收；**不能把两个独立 2D PASS 相加当作新模型的 3D PASS**。
5. **旧 25D 的 lifted 部分不可复用**：旧 A5 的 42 条、B5 的 208 条 lifted 路线（以及其 84/416 条 transition、32/6/4 与 69/66/73 条中间层 flat 段）必须在修正后的 stack 上重新布线。
6. 旧数据→新数据的**字段级迁移结论**见 §5：`layer`、`travel_layer`、`travel_z_mm`、`interface_layer`、`layers_z_mm`、`n_transitions`、`z_span_mm`、parts 的 transition 字段全部**语义改变或作废**；只有连接身份、2D 端口 XY、flat 的物理 z（仅 0/0.5 两排）等少量字段可直接复用。

---

## 1. 审计范围、方法与证据

### 1.1 代码（逐一通读，行号以当前工作区文件为准）

| 文件 | 行数 | 审计重点 |
|---|---:|---|
| `four_side_1024/fsd25d/config25d.py` | 110 | `LAYER_STACKS`/`INTERFACE_LAYER`/`stack()`/`interface_layer()`/`travel_layers()`/`transition_footprint()` |
| `four_side_1024/fsd25d/path3d.py` | 471 | `build_route3d`（base_layer/base_z）、`place_transitions`、`flat_full_route3d`、route/part JSON 字段 |
| `four_side_1024/fsd25d/router25d.py` | 479 | `load()`（base layer/z 取自 interface 层号）、travel 选择、`attempt_route`、`routes_payload` |
| `four_side_1024/fsd25d/world25d.py` | 532 | `LayerWorld`（按逻辑层号 key）、`ClearanceWorld3D`（flat 插入 z 但无 flat–flat cross-z 检查） |
| `four_side_1024/fsd25d/validate25d.py` | 2229 | 哪些检查假设 layer index→z、interface_layer 用在哪、是否把 z1/z2 当不同层 |
| `four_side_1024/fsd25d/run25d.py` | 115 | 旧 25D CLI/输出 |
| `four_side_1024/r15/run25d_r15.py` | 105 | R15 复用旧 25D 的 runner、baseline 覆盖、输出目录 |
| `four_side_1024/r15/profile_r15.py` | 150 | R15 半径 profile（import-time 绑定）对旧 25D 的影响 |
| `four_side_1024/fslw/ports.py` | 270 | 2×16 MPO 双高度接口的真实事实（行高 0/0.5、CSV 身份、端口占用） |
| `four_side_1024/fslw/config.py` | 116 | 接口/工艺常量（行距 0.5、`PLANE_Z_MM`、`Z_TRANSITION`、R 半径 env 绑定） |
| `four_side_1024/fsd25d/SCHEMA_25D.md` | 160 | **旧数据契约本身**（含错误模型：`interface_layer z2 = n_layers-1`） |
| `four_side_1024/l3d/SCHEMA_L3D.md` | 147 | 修正后模型/数据 schema/验收语义（本审计的对照基准） |

### 1.2 旧输出产物（只读；sha256 见附录 6.2）

| 产物 | 物理含义 |
|---|---|
| `outputs/four_side_1024_v2_r15_v01/25d/schemeA/layers5/routes_25d.json`（2 002 144 B） | R15、scheme A（D56/Short-S）、5 层、旧模型 |
| `outputs/four_side_1024_v2_r15_v01/25d/schemeB/layers5/routes_25d.json`（2 109 589 B） | R15、scheme B（纯正交 90°）、5 层、旧模型 |
| 同上目录 `run_summary.json`/`run.log` | 配置、统计、耗时 |
| `outputs/four_side_1024_v2_r15_v01/25d/validation/all_validation.json` 与 `validation/{A,B}/layers5.json` | 旧验证器（旧模型口径）的 PASS 报告 |
| `outputs/four_side_1024_v2_r15_v01/validation/2d/{A,B}/{z1,z2,combined}.json` | R15 二维逐平面/合并验收（新模型可复用的部分） |
| `outputs/four_side_1024_v2_25d_v01/`（旧 R40 轮） | 旧 25D 最初一轮（layers3 与 layers5，scheme A/B） |

### 1.3 方法

1. 逐行通读 `fsd25d` 五个模块 + `r15` runner/profile + `fslw` 接口两模块，记录“层号↔物理 z”的每一处映射。
2. 解析旧 `routes_25d.json`，统计：顶层字段、成功/失败记录字段集、flat 段 `layer→z_mm` 直方图、transition 的 `z0→z1` 直方图、route 级 `travel_layer/travel_z_mm` 分布，并抽取 5 条代表性记录（z1 flat / z2 flat / z1 lifted / z2 lifted / failed）。
3. 读取旧 `run_summary.json` 与旧 `validation/*.json`，提取两轮（R40、R15）布通数、lifted 数、逐层 flat 段数、逐层 crossing 数、min 3D distance、min curvature、PASS 结论。
4. 以 `SCHEMA_L3D.md` 的 5 条 stack invariant、route 规则、碰撞语义、验收语义逐条对照旧实现，定位需要改动的位置。
5. 所有证据固化到 `four_side_1024/l3d/OLD_MODEL_FIELDS.json`（含每个旧产物 sha256 与关键统计），本文件 §A/§C/§D 的每个数字都可在该 JSON 中找到。

---

## 2. A. “旧模型错误假设”表

记号：`文件:行` 均为当前工作区代码；数据证据来自 §1.2 的旧产物。`SCHEMA_L3D.md:行` 指向修正后模型。

### 2.1 错误假设逐条

| 编号 | 错误假设 | 代码位置 | 数据/事实证据 | 后果（新模型视角） | 新模型正确做法 |
|---|---|---|---|---|---|
| **A1** | z2 端口层 = 最高路由层 **L5（layer index 4，z=0.5）**；z1 = L1（index 0，z=0.0） | `fsd25d/config25d.py:47,49`（`LAYER_STACKS[5]=(0,0.125,0.25,0.375,0.5)`，`INTERFACE_LAYER[5]={'z1':0,'z2':4}`）；`fsd25d/router25d.py:69-70,104-105`（`base_layer=self.interface[plane]`，`base_z=self.z_values[base_layer]`）；`fsd25d/router25d.py:415`（记录写 `interface_layer=4, interface_z_mm=0.5`）；旧契约 `fsd25d/SCHEMA_25D.md:28`（`{"z1":0,"z2":n_layers-1}`） | 两轮旧产物 `layers_z_mm=[0,0.125,0.25,0.375,0.5]`、`interface_layer={"z1":0,"z2":4}`；A5 flat 段 `layer=4,z=0.5` 共 501 条、B5 共 451 条；样例 route 513(A)/514(B) 为 `interface_layer=4, interface_z_mm=0.5` | **旧 985/723 把 z2 端口当作 L5 接口层**：z2 的 512 条连接在旧模型中走最高层；新模型 z2 属于 **L1**（`layer_id=1`，物理高度 0.5），而真实 L5 是额外层（高度未确认，示例 2.5 mm）→ 旧结果整体不可映射为新模型解；“旧五层 PASS”是在错误层分配上的 PASS | L1 为接口层：z1 行 z=0.0、z2 行 z=0.5，**两条路由的 `layer_id` 都是 1**（`SCHEMA_L3D.md:6-15,19-26,31`）；行高由 CSV row 决定，不由层号决定 |
| **A2** | 五个层高 = `[0, 0.125, 0.25, 0.375, 0.5]`：**把 0.5 mm 的两排行距当成整个五层高度域**，额外层以 0.125 mm 等距塞在 0–0.5 mm 之间 | `fsd25d/config25d.py:3-14`（docstring：“vertical stack of routing heights between the two real interface heights”）；`fsd25d/config25d.py:47`；`fsd25d/config25d.py:71-78`（`stack()`/`interface_layer()`）；`fsd25d/config25d.py:88-98`（过渡 footprint 依赖该 dz 域）；`fsd25d/path3d.py:223-340` 全部按该 stack 取 z | 旧 `run_summary.json`：`layers_z_mm=[0.0,0.125,0.25,0.375,0.5]`；旧 validation：`stats.min_layer_gap_mm=0.125`；旧 transition dz 直方图 A5 `{0.125:36,0.25:12,0.375:36}`、B5 `{0.125:160,0.25:132,0.375:124}` | **把 0.5 mm 行距当成整个五层高度域**：L2–L4 的 0.125/0.25/0.375 是人为压缩出来的虚构高度，没有任何 supervisor/工艺依据；新模型 L2–L5 是额外层、高度**未确认**（示例：`medium_050` L2..L5 = 1.0/1.5/2.0/2.5；`compact_025`=0.75/1.0/1.25/1.5；`wide_100`=1.5/2.5/3.5/4.5），旧 lifted 路线（A 42 / B 208 条）依赖虚构高度 → 不可复用 | 用 `LayerStack`：L1 的 `interface_rows={'z1':0.0,'z2':0.5}` + L2–L5 的 `physical_z_mm`（未确认，`provenance='unconfirmed_simulation'`），且要求 routing 层高度严格有序、在接口行高之外、任意两物理平面 `abs(dz) > 0.08`（`SCHEMA_L3D.md:19-40,42-53`） |
| **A3** | 逻辑层号 = 物理高度：`layer index → z_mm` 是一一映射，可互相替代 | `fsd25d/path3d.py:287,314,317,320`（flat part 只带 `layer`+`z_mm`，两者由同一 stack 绑定）；`fsd25d/world25d.py:145-175`（`LayerWorld` 以逻辑层号作 key，一层一个 D56Index）；`fsd25d/router25d.py:122-129`（`_accept` 按 `part['layer']` 注册）；`fsd25d/validate25d.py:897-906`（flat 的 `z_mm` 必须等于 `layers_z[layer]`） | 旧数据 flat `layer→z` 是严格的 0→0.0,1→0.125,2→0.25,3→0.375,4→0.5（A5/B5 直方图见证据 JSON）；旧 validator 从未出现同一 layer 对应两个 z 的表示 | 新模型明确 **`layer_id` 不是 z 坐标**：同一 `layer_id=1` 可对应 z=0.0 和 z=0.5 两个物理高度；不同 `layer_id` 仍必须做真实 3D 碰撞检查（`SCHEMA_L3D.md:118-120`）。旧代码的“层号=高度”绑定既无法表达 L1 两排，也会把“不同层”当成“必然不相交” | 逻辑层与物理 z 彻底解耦：flat part 同时带 `layer_id` 与 `z_mm`，由 stack/行高独立校验；索引/2D 审计按 **`(layer_id, physical z)`** 分组（同物理平面才用 frozen strict 2D 规则） |
| **A4** | 不同逻辑层的 flat–flat 对不需要真实 3D 检查：“必被竖直间隔 ≥0.125 mm 保证安全” | `fsd25d/world25d.py:1-11`（docstring：“flat-to-flat pairs on different layers are vertically separated by >= 0.125 mm so they are safe by construction”）；`fsd25d/world25d.py:471-485`（`check_route` 只检查 transition 相关对 + self）；`fsd25d/validate25d.py:1580-1588`（`_audit_3d_pairs` docstring 同样假设）；`fsd25d/validate25d.py:1713-1721`（`_check_layer_gaps`） | 旧 validation `stats` 只有 `min_flat_flat_same_layer_mm`、`min_flat_transition_mm`、`min_transition_transition_mm`，**没有 flat–flat 不同物理 z 的实测距离**；旧跨平面规则只在 2D 合并验收里以“不同 plane 非冲突”一句话豁免 | 新模型要求：**任意两个不同物理 z 的 part 对**（包括 L1 两排彼此、L1 vs L2–L5、transition vs 任意 flat/transition）都必须真实 3D 中心线距离 ≥0.08，且无交叉豁免（`SCHEMA_L3D.md:107-122`）。旧实现既没有 flat–flat cross-z 检查，也没有按 `(layer_id,z)` 区分同层不同排 | 碰撞世界按物理 z 建索引/空间网格；flat–flat 同物理平面 → frozen strict 2D；flat–flat 不同物理 z、含 transition 的任意对 → 真实 3D 距离；同层不同排（L1 两排）按“不同物理 z”处理 |
| **A5** | 一条路线只允许 0 或 **恰好 2 次** transition，且只能有**一个** travel layer（升-降往返） | `fsd25d/path3d.py:282-335`（`build_route3d` 只生成 flat/transition/flat/transition/flat 五段）；`fsd25d/router25d.py:161-214`（`attempt_route` 对每个候选只尝试 flat 或“单个 travel_layer”）；`fsd25d/validate25d.py:1073-1112`（`lifted` 必须 `["flat","transition","flat","transition","flat"]`；`n_transitions` 只允许 `None/2`；`travel_layer==interface_layer` 报错） | A5：42 条 lifted、84 条 transition、`travel_layer {1:32,2:6,3:4}`；B5：208 条 lifted、416 条 transition、`travel_layer {1:69,2:66,3:73}`；所有 lifted 记录的 `n_transitions=2`（如 A5 route 300/539、B5 route 17/513） | 新模型允许多次换层、任意层对（L1↔Lk、Li↔Lj）、back-to-back transition，例如 `layer_sequence=[1,2,3,1]`、`n_transitions=3`（`SCHEMA_L3D.md:97-105,133`）。旧数据格式与旧 validator **结构性拒绝**新模型路线 → 旧搜索空间远小于新模型空间，**985/723 既不是新模型的上限也不是基线** | route 记录携带 `layer_sequence` + `layer_z_sequence`（长度 = `n_transitions+1`），parts 顺序 `flat,transition,...,flat`，首尾 flat 必须在 L1 的对应行高；transition 用 `from_layer`/`to_layer` 描述任意层对 |
| **A6** | 接口高度从层号/stack 推出：`interface_z = layers_z[interface_layer]` | `fsd25d/router25d.py:104-105`；`fsd25d/validate25d.py:1009-1026`（`interface_layer=context["interface_layer"][plane]`，`interface_z=context["layers_z"][interface_layer]`）；`fsd25d/validate25d.py:1175-1210`（`_check_ports` 起终点 z == interface_z）；`fsd25d/validate25d.py:1160-1165`（`_travel_span` 用 `layers_z[travel_layer]-layers_z[interface_layer]`） | 旧数据 `interface_layer: z1=0, z2=4`、`interface_z_mm: 0.0/0.5`；失败记录也带 `interface_layer=4`（route 573 A5、route 27 B5） | 旧 validator 把 0.5 mm 归因于“层 4”而不是“z2 行高”。**z1 的 0.0 恰好等于旧 layer 0 的 z，因此旧 z1 部分数值看起来“正确”，容易误导成“旧数据只要把 layer 4 改成 1 就能用”**；实际上面层号需 0/4→1，而高度必须来自 CSV row | 接口层恒 `layer_id=1`；`start_z_mm`/`end_z_mm`/`source_port.z_mm`/`target_port.z_mm` 必须等于真实行高（z1:0.0，z2:0.5，`SCHEMA_L3D.md:63-67,91-92,129-130`）；端口身份与行号来自冻结 V2 CSV（`fslw/ports.py:120-170`） |
| **A7** | z1/z2 是“两个独立 2D 问题”，旧 25D 可以直接复用两个 2D PASS 的并集，且合并结果仍按 2D 口径验收 | `fsd25d/config25d.py:26-45`（`SCHEMES` 直接指向两个 2D 基线，`baseline_routed` 752/262）；`fsd25d/router25d.py:106-109`（2D routed 原样搬成 flat 路线）；`r15/run25d_r15.py:33-48,70-82`（R15 下改用 A=943/B=515 的 R15 2D 基线） | 旧 A5 `baseline_routed=943`（= R15 2D A 的 z1 498 + z2 445）、B5 `515`（= 184+331）；旧 R40 轮 `baseline_routed=752`（=R40 2D A）、`262`（R40 2D B）；R15 2D 合并验收 JSON 的 `cross_plane_policy` 明写“plane z1 and z2 are separate 2D problems; cross-plane XY-projected overlaps are NOT conflicts” | **旧 985/723 = 两个独立 2D PASS 之和 + 旧模型 lifted**；新模型要求单一真实 XYZ 世界中的整体验收（`SCHEMA_L3D.md:107-122,124-142`）。两个 2D PASS 各自只覆盖一排的 flat 布局，不能相加成 3D PASS；新模型还引入 L2–L5、transition、多过渡，旧并集完全未覆盖 | 两个 2D 布局只作为 **L1 flat 几何**放进同一个 XYZ 世界重验；跨排 XY 投影重叠是否冲突必须用真实 3D 距离判定（Δz=0.5 mm > 0.08 mm，大概率安全，但结论必须**被验证**而不是沿用“不同 plane 非冲突”的旧豁免语句） |
| **A8** | 旧五层 PASS 可以当作正式验收；没有“层高未确认 → 拒绝正式验收”的概念 | `validate25d.py` 全文（2229 行）**没有任何** `formal_acceptance`/`exploratory`/`confirmed`/`unconfirmed` 字样（本次审计 grep 0 命中）；结论只在 `fsd25d/validate25d.py:1930-1945` 由 counts/min 距离/曲率聚合出 `passed`；`_check_payload` 在 `641-754`、`677-713` 直接硬比 `CFG.stack()` 与 `CFG.INTERFACE_LAYER` | 旧两轮 `validation/*.json` 全部 `passed=true`（R15 A5 `min_3d_distance_mm=0.080295032`、`min_curvature_radius_mm=14.999999963`；B5 `0.08`/`14.999999966`）；R40 轮 A5/B5 `passed=true`（`min_curvature≈40.0`）。这些 PASS 均无 provenance 字段 | 新模型：L2–L5 高度未确认时必须标 `unconfirmed_simulation`，**拒绝正式验收**（`formal_acceptance=false`；几何检查只能报 `exploratory_pass`）（`SCHEMA_L3D.md:10-15,27-28,140-142`）。旧 PASS 既不能迁移，也无法表达这种状态 | 新验证器输出必须含 stack `provenance`；stack 缺高度/不满足 invariant → 明确拒绝（exit nonzero / `formal_acceptance=false`）；探索性结果单独标记 |
| **A9** | 2D 审计按**逻辑层号**分组即可（一层一组） | `fsd25d/validate25d.py:1407-1474`（`_audit_layers`：`by_layer.setdefault(part.layer, ...)`，每组调用 frozen `audit_route_pairs(policy='strict')`）；`fsd25d/world25d.py:145-175`（同样按 layer 建索引） | 旧 A5 逐层 2D 审计：layer 0 = 526 parts / 69072 crossings，layer 4 = 501 parts / 67521 crossings；B5 layer 0 = 480/13724，layer 4 = 451/40864（其余为中间层） | 新模型下 L1 两排同 `layer_id=1` 但物理 z 不同（0/0.5），**必须拆成两个 2D 审计组**；若沿用“按 layer_id 分组”，两排会被塞进同一个 2D index：既错误地对 0.5 mm 垂直相邻的两排执行同层 2D 间距/交叉规则，又丢失“不同物理 z 必须真实 3D”的检查 | 2D strict 审计按 **`(layer_id, physical_z)`** 分组（L1 拆两排；L2–L5 每层一组）；跨组用 3D 距离 |
| **A10** | 旧数据契约 `SCHEMA_25D.md` 有效，可以作为新模型数据契约 | `fsd25d/SCHEMA_25D.md:28`（`interface_layer: {"z1": 0, "z2": n_layers-1}`）、`SCHEMA_25D.md:24-33`（顶层 `layers_z_mm`）、`SCHEMA_25D.md:35-95`（route/parts 字段）、`SCHEMA_25D.md:97-144`（旧验收清单） | 旧 `routes_25d.json` 顶层字段完全按此 schema 生成（`n_layers`/`layers_z_mm`/`interface_layer`/`parts.layer`/`z0_mm` 等） | 契约本身写入了错误模型（尤其 `SCHEMA_25D.md:28` 的 `z2 = n_layers-1`），且与新 L3D schema 字段不兼容 → 旧 JSON/旧 validator/旧契约必须整体标为 legacy，不能“迁就旧字段”实现新验证器 | 以 `SCHEMA_L3D.md` 为唯一新契约；旧契约只保留历史读取用途 |
| **A11** | 旧 JSON 只要“改个 layer 标签”就能迁移：旧 travel layer id 1..3 继续当新 routing layer | `fsd25d/config25d.py:81-86`（`travel_layers()` 返回 `1..n-2`）；数据证据见 A5 | 旧 travel_layer：A5 `{1:32,2:6,3:4}`，B5 `{1:69,2:66,3:73}`；旧 flat layer→z：1→0.125、2→0.25、3→0.375 | 新模型 routing layer id 是 **L2..L5 = 2..5**（L1=1 接口）；旧 id 1..3 既不是新 L2..L4 的物理高度（0.125/0.25/0.375 在新模型无对应），也没有“旧 id 4 = 新 L1”这回事（旧 id 4 是 z2 接口排，新 id 1 才是接口层）。**简单 relabel 会同时破坏 layer id 与 z 两个维度** | 旧 lifted 路线必须按新 stack 重新布线；旧 transition/中间层 flat 数据直接作废（不能改名复用） |
| **A12** | 旧 25D 的两轮结果（R40 820/383、R15 985/723）可以作为新模型的参照上限或“已验证数” | `r15/run25d_r15.py:1-15,65-96`（R15 runner 复用旧 25D，仅替换 baseline root 与半径 profile）；`r15/profile_r15.py:33-39,44-51,77-94`（R15 全局半径 15，含 import-time 绑定） | R40 旧轮：A3 788、A5 820、B3 342、B5 383（旧 validation 全 PASS，min curvature≈40.0）；R15 旧轮：A5 985、B5 723（旧 validation 全 PASS，min curvature≈15.0）。两轮 stack 相同、仅半径不同 | 两轮都在错误 stack 上求解；新模型 L2–L5 高度未确认 → 25D 布通数依赖未确认的仿真输入，只能作 `exploratory`。旧数值既不能当新模型的“已验证上限”，也不能与 2D 数或新 L3D 数直接比较 | 新轮用 `l3d` pipeline 在明确声明的 stack preset 上重跑；结果标 `unconfirmed_simulation`；正式验收被拒绝直到高度确认 |

### 2.2 旧结论 985/723 的失效链条（为什么“旧五层 PASS 不能继承”）

```
旧 A5 = 985 routed = 943 (R15 2D 两排 flat, 直接复用)  + 42 (旧模型 lifted)
旧 B5 = 723 routed = 515 (R15 2D 两排 flat, 直接复用)  + 208 (旧模型 lifted)
                        │                                  │
                        │                                  └─ 高度 0.125/0.25/0.375 mm（L2–L4 虚构）
                        │                                     在新模型中：不存在；新 L2–L5 未确认（示例 1.0–2.5 mm）
                        └─ z2 flat 标在 layer 4 (=旧 L5)；新模型应为 L1 (layer_id=1, z=0.5)
```

1. **模型错误**：z2 接口层被放到 L5；五层高度域 = 0–0.5 mm（A1/A2）。
2. **lifted 部分不可移植**：A 42 / B 208 条 lifted 依赖 0.125/0.25/0.375 的虚构中间高度与“单 travel layer + 恰好 2 次 transition”的结构（A5/A11）。新模型的 L2–L5 高度未确认、允许任意层序/多过渡，因此旧 lifted 路线必须重路由。
3. **验收不可继承**：旧 PASS 由旧 validator 在旧模型口径下产生（A8），没有未确认高度拒绝、没有 L1 两排的 3D 检查、没有多过渡支持，且**字段层面无法读取新 L3D JSON**（A6/A8/A9）。因此“旧五层 PASS”不能迁移为 R9 的 PASS，985/723 不能写进新模型结论。
4. **可迁移的只有 2D flat 几何**：943/515 条 flat 可以在 L1 上复用（见 §4），但必须整体重验；而且它们是 flat-only 布局，“两个 2D PASS 相加”不能得到 3D/新模型 PASS（A7）。

---

## 3. B. 正确的数据模型摘要 + 旧代码逐文件改动清单

### 3.1 正确模型（严格对齐 `SCHEMA_L3D.md`）

引用行号均指 `four_side_1024/l3d/SCHEMA_L3D.md`。

1. **L1 是接口路由层，含两排真实端口高度**：z1 行 z=0.0 mm、z2 行 z=0.5 mm；两排都是 `layer_id=1`（`SCHEMA_L3D.md:6-15,19-26,31,91-92`）。0.5 mm 是 MPO 2×16 的行距/行高差（真实接口事实，见 `fslw/config.py:39-58` 与 `fslw/ports.py:1-14`），**不是**五层堆栈的高度域。
2. **L2–L5 是四个额外路由层，高度未确认**：`physical_z_mm` 是仿真输入，`provenance='unconfirmed_simulation'`；示例探索 stack：`medium_050` = 1.0/1.5/2.0/2.5、`compact_025` = 0.75/1.0/1.25/1.5、`wide_100` = 1.5/2.5/3.5/4.5（`SCHEMA_L3D.md:10-15,27-28,42-53`）。
3. **Stack invariants**（违反即拒绝，`SCHEMA_L3D.md:27-40`）：L1 存在且 `layer_type='interface'`、rows 恰为 z1=0.0/z2=0.5；L2–L5 存在且高度有限；routing 层高度严格有序、在接口行高之外、任意两不同物理平面 `abs(dz) > 0.08 mm`；`allowed_transitions` 对称，任意两层间可达（任意层对可由合法 transition 序列连接）。
4. **逻辑层与物理 z 彻底解耦**：`layer_id` 不是 z 坐标；同一 `layer_id` 可对应不同物理高度（L1 两排），不同 `layer_id` 仍必须做真实 3D 碰撞检查（`SCHEMA_L3D.md:118-120`）。
5. **Route 规则**（`SCHEMA_L3D.md:55-105`）：每条 route 首尾都在 L1 的自身行高（z1:0.0 / z2:0.5）；`parts` 顺序为 flat/transition 交替（`flat,transition,flat,...`）；transition 为 R=15 的两圆弧垂直 S 曲线，`theta=acos(1-abs(dz)/(2R))`、`footprint=2R sinθ`、`length=2Rθ`，可连接**任意**两层且**一条路线允许多次换层**（含非相邻层、back-to-back）；`layer_sequence` 与 `layer_z_sequence` 必须分别独立记录，不能互相推断；纯 L1 路线 `layer_sequence=[1]`、无 transition。
6. **碰撞语义（真实 XYZ）**（`SCHEMA_L3D.md:107-122`）：同物理 z 的 flat–flat 用 frozen strict 2D 规则；**任意不同物理 z 的 part 对**（含 L1 两排彼此、L1 vs L2–L5、任何 transition vs flat/transition）必须真实 3D 中心线距离 ≥0.08，无交叉豁免；同一路线自净空也按真实 3D。
7. **验收语义**（`SCHEMA_L3D.md:124-142`）：独立重建 transition/flat 采样；验证 L1 两排属于同一接口层但物理高度不同、同列两排端口保持 0.5 mm 真实距离、首尾 L1 行高、任意层对/多过渡合法、完整 3D 曲率与净空、transition vs L1 行的真实 3D 距离、“同 logical layer 不同物理高度”的距离；**L2–L5 高度未定义/stack 物理无效时必须拒绝正式验收**（`formal_acceptance=false`；`--allow-exploratory` 下只能报 `exploratory_pass`）。
8. 新实现位置（`SCHEMA_L3D.md:144-147`）：`l3d/layers.py`、`l3d/paths.py`、`l3d/world.py`、`l3d/router.py`、`l3d/run_l3d.py`、`l3d/validate_l3d.py`；输出 `outputs/four_side_1024_v2_l1l5_v01/`，R15/R40 旧输出保持不动。

### 3.2 旧代码必须改的地方（逐文件）

> 说明：本节按“旧实现 → 新模型要求”列出**需要改动**的位置；不代表新实现必须沿用旧代码结构。当前 `l3d/` 新实现不在本审计范围内（本审计只审计旧模型）。

| 文件 | 必须改动 | 原因/对应错误假设 |
|---|---|---|
| `fsd25d/config25d.py` | **`47` `LAYER_STACKS`、`49` `INTERFACE_LAYER` 整体替换**为 `LayerStack`（L1 rows + L2–L5 unconfirmed heights + provenance + allowed_transitions + 物理 invariant 校验）；`71-78` `stack()`/`interface_layer()` 改为返回 LayerStack/恒 1；`81-86` `travel_layers()` 语义改为 L2..L5（`[2,3,4,5]`，且不再“排除 base”）；`88-98` `transition_footprint()` 公式可保留，但需支持**任意** dz（含 L1↔任意层、层间任意对，dz 上限 2R）；`24` 旧输出根仅历史；`26-45` schemes 基线描述保留但需注明“仅 flat L1 复用” | A1/A2/A3/A5/A11 |
| `fsd25d/path3d.py` | `282-340` `build_route3d(` 的 `base_layer/base_z/travel_layer/travel_z` 单一 travel 模型 → 改为 **layer sequence 规划**（任意长度、任意层对，多 transition）；`223-277` `place_transitions` 只支持两段升降 → 需支持多段/多次换层与 back-to-back；`338-340` `flat_full_route3d` 的 layer 参数需为 L1=1 + 行高；`326-335` route 字段改为 `start_z_mm/end_z_mm/layer_sequence/layer_z_sequence/layers_used/source_port/target_port`；`450-471` 写出/摘要按新 schema | A3/A5/A6 |
| `fsd25d/router25d.py` | `90-120` `load()`：`base_layer` 恒为 1，`base_z` 取该 route 的行高（z1:0.0/z2:0.5），不能取 `interface` 层号；`104-105` 同上；`122-129` `_accept` 的 LayerWorld 注册键改为“物理平面”；`161-214` `attempt_route` 的“flat 或单 travel layer”循环 → 改为层序/多 transition 搜索；`359-479` `routes_payload()` 全部按 L3D schema 重写（`interface_layer` 恒 1、route/part 新字段、删除 `travel_layer` 单值语义等） | A1/A3/A5/A6 |
| `fsd25d/world25d.py` | `145-175` `LayerWorld` 以逻辑层号为 key → 改为按 **物理平面 `(layer_id, z)`**（L1 两排两个索引；L2–L5 各一）；`180-189`/`196-240` flat 插入已有 `z` 但不参与 flat–flat 判断 → 增加 **flat–flat 不同物理 z 的真实 3D 距离检查**（L1 两排彼此也要查）；`283-469` transition 相关 3D 检查可保留思路，但必须补“同 layer_id 不同 z”与多 transition 情况；`471-485` `check_route` 去掉“不同层必然安全”的构造性假设；`500-532` self-clearance 3D 可保留 | A3/A4/A9 |
| `fsd25d/validate25d.py` | `641-754` `_check_payload`：不再硬比 `CFG.stack/CFG.INTERFACE_LAYER`（`677-713`），改为读取 payload 的 `LayerStack` 并校验 provenance/invariants；`893-943` `_parse_flat_part`：`layer`→`layer_id`，`z_mm` 与 `(layer_id,z)` 校验（L1 允许两排）；`946-998` `_parse_transition_part`：支持 `from_layer/to_layer/z0/z1/theta_rad` 与任意层对；`1001-1125` `_parse_route`：`interface_layer` 恒 1、`start_z_mm/end_z_mm` 取行高；`1073-1112` 删除“只允许 flat-transition-flat-transition-flat / n_transitions∈{0,2} / travel_layer 单值”限制，改为 layer_sequence 任意长度；`1128-1165` `_travel_span` 改为 `layer_z_sequence` 的 max−min；`1407-1474` `_audit_layers` 分组键改为 `(layer_id, physical z)`；`1480-1561` `_SegmentStore` 增加 `(layer_id, z)` 元数据并纳入 flat–flat cross-z 对；`1580-1661` `_audit_3d_pairs` 删除“不同层必安全”的假设，覆盖所有不同物理 z 对（含 L1 两排）；`1667-1685` 失败记录字段按新 schema；`1713-1721` `_check_layer_gaps` 改为对 LayerStack 的“routing 层两两 abs(dz)>0.08、且在接口行高之外”校验；`1740-1952` 结论增加 `formal_acceptance/exploratory_pass`、provenance 拒绝、`layer_z_sequence` 一致性、多过渡校验；`1966-1981` `_discover_runs` 只认 `scheme{A,B}/layers{3,5}` 旧目录 → 新模型固定 L1–L5，旧目录必须不再被自动接受 | A1/A2/A3/A4/A5/A6/A8/A9 |
| `fsd25d/run25d.py` / `r15/run25d_r15.py` | 旧 runner 的输出根/目录（`fsd25d/run25d.py:63`、`r15/run25d_r15.py:82-96`）与“25d/scheme*/layers*”命名 → 新轮输出 `outputs/four_side_1024_v2_l1l5_v01/`（`SCHEMA_L3D.md:147`）；`r15/run25d_r15.py:1-15,70-82` 可保留“用 R15 2D 基线”的思想，但仅用于 **L1 flat baseline**，且不能再把 25D 结果当交付 | A7/A12 |
| `fsd25d/plots25d.py`、`report_details.py`、`extra_metrics25d.py`、`summarize25d.py` | 这些下游模块消费旧 `routes_25d.json`（旧 `layer`/`travel_layer`/`layers_z_mm` 字段）并据此出图/统计/报告；旧 schema 作废后，它们要么按新 L3D schema 改写，要么整体标 legacy 不再用于新轮交付（本审计未逐行审计其统计口径） | A10（契约）连带 |
| `r15/profile_r15.py` | 半径 profile 本身可继续用（R=15 仍是新模型 transition 的示例半径）；注意其 import-time 绑定语义（`r15/profile_r15.py:8-23,44-51,77-94`）对 `config25d.RADIUS_MM`/`path3d` 默认参数的影响需在新实现中显式化（避免“先 import 后 patch”导致默认参数仍绑定 R=40） | A12 附带风险 |
| `fsd25d/SCHEMA_25D.md` | 标记 legacy/superseded：`28` 的 `interface_layer z2=n_layers-1`、`24-33` 的 `layers_z_mm`、`35-95` 的 route/parts 字段、`97-144` 的验收清单均已被 `l3d/SCHEMA_L3D.md` 取代；不得作为新验收依据 | A10 |
| `fslw/ports.py` | **保留**（它是正确的接口事实来源）：`1-14` 行号→z 映射、`120-170` 逐平面 CSV 身份与 1024 端口占用、`173-234` 结构校验；仅 `230` 的 `cross_plane_rule` 措辞“XY-projected crossings between z1 and z2 are not same-layer conflicts”需要按新模型改写成“两排同属 L1、物理 z 相差 0.5 mm，故 XY 投影交叉不是同层冲突；但仍须真实 3D 距离检查” | A6/A7 |
| `fslw/config.py` | **保留**：`39-58` 明确 2×16 MPO 行距 0.5 mm、`PLANE_Z_MM={1:0.0,2:0.5}`、`Z_TRANSITION='not_implemented'`、制造声明；`11-24` 工艺参数与 R 半径（env 绑定，`15-21`）继续作为唯一工艺常量来源。**不得**再把 `PLANE_Z_MM` 的 0/0.5 当成 L2–L5 堆栈端点（旧 config25d 的错误正是如此） | A2/A6 |

### 3.3 旧模型与新模型最小对照表

| 维度 | 旧 25D（`fsd25d`） | 新 L1–L5（`SCHEMA_L3D.md`） |
|---|---|---|
| 接口层 | z1=L1(z=0)、z2=L5(z=0.5)，两个逻辑层 | L1 一个逻辑层，含两排 z=0.0 / z=0.5 |
| 额外层 | L2–L4 = 0.125/0.25/0.375（虚构、压在 0–0.5 内） | L2–L5 额外层，高度未确认（示例 0.75–4.5） |
| 层高与 z | 层号↔z 一一绑定 | 彻底解耦：`layer_id` 不是 z；同层可两排 |
| transition | 恰好 2 次，单 travel layer | 任意次、任意层对、back-to-back |
| 碰撞 | 同层 2D + transition 3D；不同层 flat–flat 构造性跳过 | 同物理平面 2D（frozen strict）；**所有不同物理 z 对真实 3D**（含 L1 两排） |
| 2D 分组 | 按逻辑层号 | 按 `(layer_id, physical z)` |
| 验收 | 无 provenance / 无正式拒绝 / 单层 PASS | 未确认高度 → `formal_acceptance=false`，只能 `exploratory_pass` |

---

## 4. C. 旧 2D 布局能否复用

### 4.1 事实：R15 两套 2D 布局及其验收状态

| scheme | z1 routed | z2 routed | 合计 | 2D 逐平面验收 | 2D 合并验收 | 半径 |
|---|---:|---:|---:|---|---|---:|
| A（D56/Short-S） | 498 | 445 | **943** | `validation/2d/A/z1.json`、`z2.json` 均 `passed=true`、0 violations | `validation/2d/A/combined.json` `passed=true` | 15.0 mm |
| B（纯正交 90°） | 184 | 331 | **515** | `validation/2d/B/z1.json`、`z2.json` 均 `passed=true`、0 violations | `validation/2d/B/combined.json` `passed=true` | 15.0 mm |

数据来源：`outputs/four_side_1024_v2_r15_v01/validation/2d/{A,B}/…`（sha256 见附录）。2D 合并 JSON 的 `cross_plane_policy` 写的是“plane z1 and z2 are separate 2D problems; cross-plane XY-projected overlaps are NOT conflicts”。

### 4.2 可复用的部分（结论）

**可以复用**：两套 R15 2D 布局中 **routed 路线的 XY flat 几何**（含 CSV 连接身份、端口 XY、D56/正交 90° 图元、R=15 平面弧）。它们在修正模型中只作为 **L1 上的 flat 布局**：

- z1 行的路线全部放在 L1（`layer_id=1`）的 **物理高度 0.0 mm**；
- z2 行的路线全部放在 L1（`layer_id=1`）的 **物理高度 0.5 mm**；
- 两排放进**同一个真实 XYZ 世界**（不再分成两个互不相关的 2D 问题）；
- 复用后必须用新 `validate_l3d` 重新验收（真实 3D 净空、板界、自净空、CSV 身份、L2–L5 可达性等），不能直接引用 2D 结论。

物理判据：两排 flat 的物理 z 相差 0.5 mm > clearance 0.08 mm，因此**两排之间的 XY 投影交叉不是同层冲突**——但这是“用真实 3D 距离判定得到的安全结论”，**必须被新验证器验证**，而不是沿用旧 2D “不同 plane 非冲突”的豁免语句（旧语句的物理前提是“两个不同平面”，新模型是“同一层两个物理高度”）。

### 4.3 不可复用的部分 / 不能继承的结论

1. **旧 25D 的 lifted 路线**（A5 42 条 / B5 208 条；旧 R40 轮 A5 68 / B5 121、3 层 A3 36 / B3 80）以及它们的 transition/中间层 flat 段：高度 0.125/0.25/0.375 与 layer id 1..3 在新模型中不存在 → 必须按新 stack 重新布线。
2. **旧 25D 的布通数（R15 A5 985 / B5 723；R40 A5 820 / B5 383）**：是错误模型下的结果，**不能**作为新模型基线、上限或“已验证数”。
3. **旧五层 PASS**：不能继承（§2.2 四步链条）。
4. **旧 25D 的 flat 子集本身也不能整体继承**：虽然旧 flat 路线（A 943 / B 515）几何上与 2D 布局一致，但旧 JSON 的 `layer=0/4` 标注、`layers_z_mm`、`interface_layer=4` 都是错误的；必须重新生成新 schema 数据（`layer_id=1`、`layer_sequence=[1]`、`start_z_mm/end_z_mm` 等）。
5. **两个独立 2D PASS 相加 ≠ 新模型 PASS**：2D PASS 只覆盖“每排在自己的平面内是合法布局”；新模型还要求 L2–L5 上的布线能力、多过渡、真实 XYZ 净空，以及“L1 两排在同一世界中的 3D 关系”。即使只做 flat-only 的 L1 基线，也要在新验证器下重新确认（跨排 0.5 mm 间距、板界、端口等）。

### 4.4 建议的复用流程（供 Lead 参考）

1. 以 R15 2D 的 943/515 条 routed 路线生成 **L1-only baseline**（z1 行 z=0.0、z2 行 z=0.5，同一 XYZ 世界，`layer_sequence=[1]`，无 transition）。
2. 用新 `validate_l3d` 验证该 baseline（预期：同物理平面 strict 2D 规则来自 frozen `validate_fslw`；跨排用真实 3D 距离，0.5 mm > 0.08；结果应标 `exploratory_pass`，且因 L2–L5 高度未确认而 `formal_acceptance=false`）。
3. 在明确声明的一个 stack preset（如 `medium_050`）上，用新的多过渡/L2–L5 能力布通剩余路线；每条新路线允许 L1↔L2..L5 的任意层序与多次换层。
4. 报告口径：任何 25D/L3D 结果都标 `unconfirmed_simulation`；旧 985/723 只作为历史对照（注明“旧模型、旧 stack、不可继承”）。

---

## 5. D. 旧 `routes_25d.json` 字段级影响清单

### 5.1 顶层字段

| 旧字段（旧 JSON 实际存在） | 旧含义 | 新模型下的处置 |
|---|---|---|
| `schema='four_side_1024_v2_25d_routes_v1'` | 旧契约 | 改为 L3D schema（`four_side_1024_v2_l3d_routes_v1` 等，以新实现为准）；旧值不再有效 |
| `n_layers`（5 或 3） | 旧可变层数 | 新模型固定 L1+L2–L5（共 5 个逻辑层），旧 `3` 层变体在新模型中没有对应 |
| `layers_z_mm` = `[0,0.125,0.25,0.375,0.5]` | “层高数组” | **作废**；新模型用 `layer_stack`（L1 rows + L2–L5 unconfirmed physical_z + provenance + allowed_transitions） |
| `interface_layer={"z1":0,"z2":4}` | z1/z2 各自“接口层号” | **作废语义**：新模型接口层恒 `layer_id=1`；两排由端口行高区分，不再有“z2=4” |
| `scheme`/`scheme_label`/`xy_model` | A/B 方案标识 | 可复用（标识 2D 几何族） |
| `topology`/`csv_sha256`/`process`/`statistics`/`router`/`budget`/`run`/`experiment` | 运行元数据 | 大部分可复用；但 `statistics.per_layer_flat_parts` 的层号含义改变，`statistics.lifted` 等的旧模型口径需重算 |
| `routes` | 1024 条记录 | 记录级字段见 5.2 |

### 5.2 单条路线记录字段

| 旧字段 | 旧语义/取值 | 新模型下的语义/处置 |
|---|---|---|
| `route_id`、`plane`、`pair`、`relation`、`status`、`baseline_2d`、`family`、`params` | CSV 连接身份、2D 来源、族 | **可复用**（身份来自冻结 CSV，与层模型无关） |
| `interface_layer`（0/4） | “接口层号”：z1→0、z2→4 | **语义改变**：新模型恒为 1；旧 0/4 都必须映射为 1（且旧 4 不代表新 L5） |
| `interface_z_mm`（0.0/0.5） | 接口物理高度 | **物理含义保留**，但须绑定到 L1 行高；新 JSON 用 `start_z_mm`/`end_z_mm`/`source_port.z_mm`/`target_port.z_mm`，不再由 interface_layer 反推 |
| `mode`（"flat"/"lifted"） | 二元模式 | 新模型用 `layer_sequence`/`lifted` 表达；`mode` 作为旧模型字段可弃用（新 schema 示例未使用） |
| `travel_layer`（1..3 或 null） | 旧中间层号 | **作废**；新模型无“单一 travel layer”，改为 `layer_sequence[1:-1]`/`layers_used`（id 2..5）；旧 1..3 与任何新层 id 都不对应 |
| `travel_z_mm`（0.125/0.25/0.375 或 null） | 旧中间层高度 | **作废**；新模型由 `layer_z_sequence` 记录每层真实物理高度（L2–L5 未确认，示例 1.0–2.5） |
| `n_transitions`（0/2） | 换层段数 | **语义扩展**：任意非负整数；`len(layer_sequence)=n_transitions+1` |
| `z_span_mm` | `abs(travel_z - interface_z)`（单 travel layer） | **语义改变**：`max(layer_z_sequence)-min(layer_z_sequence)`（多过渡时更大） |
| `xy_length_mm`、`length_mm`、`flat_length_mm`、`transition_length_mm` | 旧 3D 长度（依赖旧 stack） | 字段名可复用，但**数值全部需重算**（旧数值依赖错误高度/旧 transition） |
| `port={p,q,start_tangent,end_tangent}` | 2D 端口位姿 | 2D 部分可复用；新 schema 改为 `source_port`/`target_port`（含 `xy`、`z_mm`、`layer_id`），并增加 route 级 `start_z_mm`/`end_z_mm` |
| `parts` | 旧 5 段结构（flat/transition/flat/transition/flat） | 结构扩展为任意 `flat/transition` 交替；每段字段见 5.3 |
| `reason`（failed：`no_2d_candidate`/`no_lift_candidate`） | 旧失败分类 | 新模型失败分类需重定义（例如“L1 无候选/无合法层序”）；`no_lift_candidate` 的“lift”语义已不存在 |

### 5.3 `parts` 子字段

**flat 段（旧）** → **新**：

| 旧字段 | 新字段/处置 |
|---|---|
| `kind="flat"` | 保留 |
| `layer`（0..4，旧层号） | **改名/改义** `layer_id`：L1=1（两排都是 1）；旧 0/4→1，旧 1/2/3 **作废** |
| `z_mm`（旧 stack 高度） | 保留物理含义：L1 两排 0.0/0.5；其他值必须等于 L2–L5 的未确认高度；旧 0.125/0.25/0.375 作废 |
| `length_mm` | 保留名字，数值重算（几何本身不变时可复用） |
| `primitives` | **可复用**（D56/正交 90° XY 图元与层模型无关；方案 A/B 的 2D 规则不变） |

**transition 段（旧）** → **新**：

| 旧字段 | 新字段/处置 |
|---|---|
| `kind="transition"` | 保留 |
| `start`、`end`、`direction`、`radius_mm`、`footprint_mm`、`length_mm` | 名字/含义基本保留（数值随新高度重算） |
| `z0_mm`、`z1_mm` | 新 schema 为 `z0`/`z1`（物理高度；L1 行高或 L2–L5 高度） |
| `dz_mm` | 保留（=z1−z0；新模型可连接任意层对，dz 可为数百 µm 到数 mm） |
| （无 `from_layer`/`to_layer`） | **新增**：`from_layer`/`to_layer`（逻辑层序号，允许非相邻/多次） |
| （无 `theta_rad`） | **新增**：`theta_rad`（可由 dz/R 重建，schema 要求记录） |
| 旧 transition 只能 L1↔L{1..3} | 新模型：任意两层对（L1↔L2..L5、Li↔Lj），且可一条 route 内多次 |

### 5.4 兼容性矩阵（迁移时逐字段判断）

| 处置 | 字段 |
|---|---|
| **直接复用** | `route_id`、`plane`、`pair`、`relation`、`status`、`baseline_2d`、`family`、`params`、`port.p/q/start_tangent/end_tangent`（2D 部分）、flat 段 `primitives`、`radius_mm`（R15 时 15.0）、`process`/`csv_sha256`/`topology` |
| **物理含义保留但值/绑定改变** | `interface_z_mm`（→ 行高，绑定 L1）、flat 段 `z_mm`（仅 0.0/0.5 可直接用，其余作废）、`dz_mm`/`footprint_mm`/`length_mm`（公式不变，值随新 dz 变）、`start/end/direction`（可复用，需要新 footprint 重新计算终点） |
| **语义改变/重命名** | `layer`→`layer_id`（旧 0/4→1、旧 1..3 作废）、`interface_layer`（恒 1）、`z_span_mm`（多过渡 max−min）、`n_transitions`（任意值）、`parts` 结构（任意段数） |
| **作废/删除** | `layers_z_mm`、`interface_layer={"z1":0,"z2":4}`、`travel_layer`、`travel_z_mm`、`mode`（二元）、旧 `reason` 分类、`n_layers=3` 变体 |
| **新增（新 schema 必需）** | `layer_stack`、`layer_sequence`、`layer_z_sequence`、`layers_used`、`start_z_mm`/`end_z_mm`、`source_port`/`target_port`（含 `xy`/`z_mm`/`layer_id`）、parts 的 `layer_id`/`from_layer`/`to_layer`/`z0`/`z1`/`theta_rad`、stack `provenance` |

### 5.5 代表性记录证据（旧 JSON 原值）

| 记录 | `plane`/`status` | 旧关键字段 | 新模型问题 |
|---|---|---|---|
| A5 `route_id=1` | z1 / flat | `interface_layer=0, interface_z_mm=0.0`；parts `[{flat, layer=0, z_mm=0.0, 1 prim}]` | 层号需 0→1；z=0.0 可保留 |
| A5 `route_id=513` | z2 / flat | `interface_layer=4, interface_z_mm=0.5`；parts `[{flat, layer=4, z_mm=0.5, 7 prims}]` | 旧“L5 接口层”；新模型 layer_id=1、z=0.5（几何可作 L1 z2 行 flat 复用） |
| A5 `route_id=300` | z1 / lifted | `travel_layer=1, travel_z_mm=0.125, n_transitions=2`；parts flat(L0,z0)/trans(0→0.125)/flat(L1,z0.125)/trans(0.125→0)/flat(L0,z0) | 0.125 与 L1 编号作废 → 重路由 |
| A5 `route_id=539` | z2 / lifted | `travel_layer=1, travel_z_mm=0.125, z_span_mm=0.375, n_transitions=2`；parts flat(L4,z0.5)/trans(0.5→0.125)/flat(L1,z0.125)/trans(0.125→0.5)/flat(L4,z0.5) | 旧模型让 z2 “下降”到 0.125；新模型 z2 在 L1(z=0.5)，L2=未确认高度（通常 >0.5）→ 不是同一条曲线 |
| A5 `route_id=573`（failed） | z2 / failed | `reason=no_lift_candidate, interface_layer=4, interface_z_mm=0.5` | 失败原因/接口层号均为旧模型语义 |

（上述记录完整字段与 parts 见 `l3d/OLD_MODEL_FIELDS.json` 的 `old_artefacts_r15.*.samples`。）

---

## 6. 附录

### 6.1 旧 25D 运行矩阵（全部为旧模型；仅历史对照）

| 轮次/输出根 | scheme | 层数 | `layers_z_mm` | `interface_layer` | 2D 基线 routed | 25D routed | lifted / transitions | 旧验证 |
|---|---|---:|---|---|---:|---:|---|---|
| R40 `outputs/four_side_1024_v2_25d_v01` | A | 3 | 0/0.25/0.5 | {z1:0, z2:2} | 752 | **788** | 36 / 72 | `passed=true`（min_3d 0.080390234，min_curv≈40.0） |
| R40 同上 | A | 5 | 0/0.125/0.25/0.375/0.5 | {z1:0, z2:4} | 752 | **820** | 68 / 136 | `passed=true`（min_3d 0.080390234） |
| R40 同上 | B | 3 | 0/0.25/0.5 | {z1:0, z2:2} | 262 | **342** | 80 / 160 | `passed=true`（min_3d 0.092445592） |
| R40 同上 | B | 5 | 0/0.125/0.25/0.375/0.5 | {z1:0, z2:4} | 262 | **383** | 121 / 242 | `passed=true`（min_3d 0.091116569） |
| R15 `outputs/four_side_1024_v2_r15_v01/25d` | A | 5 | 0/0.125/0.25/0.375/0.5 | {z1:0, z2:4} | 943 | **985** | 42 / 84 | `passed=true`（min_3d 0.080295032，min_curv 14.999999963） |
| R15 同上 | B | 5 | 0/0.125/0.25/0.375/0.5 | {z1:0, z2:4} | 515 | **723** | 208 / 416 | `passed=true`（min_3d 0.08，min_curv 14.999999966） |

R15 A5/B5 逐层 flat 段数与 crossing：A5 `layer0=526/69072, layer1=32/424, layer2=6/48, layer3=4/16, layer4=501/67521`；B5 `layer0=480/13724, layer1=69/2684, layer2=66/2881, layer3=73/3663, layer4=451/40864`。旧 validator 的 `stats.min_layer_gap_mm=0.125`——即旧模型的“层间安全”来自这个 0.125 mm 的人为挤压高度。

### 6.2 证据文件 sha256（本审计现场重算；完整清单含更多文件在 `OLD_MODEL_FIELDS.json`）

| 文件 | bytes | sha256 |
|---|---:|---|
| `outputs/four_side_1024_v2_r15_v01/25d/schemeA/layers5/routes_25d.json` | 2 002 144 | `7d1e82fb7742818ecf9cd904d02e1e91b14cc61408253df4dede72e87b382484` |
| `outputs/four_side_1024_v2_r15_v01/25d/schemeB/layers5/routes_25d.json` | 2 109 589 | `3c4be7a0288e4770ac8eec6b98a770686c6d6ddc9b1a42880569d4b3f6524d8f` |
| `outputs/four_side_1024_v2_r15_v01/25d/schemeA/layers5/run_summary.json` | 2 007 | `c425f2fe1e94f975c83a7df7591fa4cdc2d1b3283ce49e9a9e1fe26b4edcd016` |
| `outputs/four_side_1024_v2_r15_v01/25d/schemeB/layers5/run_summary.json` | 2 034 | `89b87fa840e71c07380cf7c5e2578f3372af9b3fdc98e4a0e95b977b6b7d55ce` |
| `outputs/four_side_1024_v2_r15_v01/25d/validation/all_validation.json` | 2 793 | `ff964fac37ac25f09aa53c42d138fba4430f44a2c8b2c6338144827adae8f441` |
| `outputs/four_side_1024_v2_r15_v01/25d/validation/A/layers5.json` | 4 161 | `4e14f1de6e6ea3a3d35742e1f2276f7c36de7be54a7f836aa19be46b1a2946fd` |
| `outputs/four_side_1024_v2_r15_v01/25d/validation/B/layers5.json` | 4 171 | `0d7f9561d091ff5526cf2688001975c5f30e32c1ee66ff140cfdd5e023259e02` |
| `outputs/four_side_1024_v2_r15_v01/validation/2d/A/combined.json` | 2 723 | `c06f15d2dd51e4bfb5537bc6c8b430b0568081d23dbe99a4ff4961ae8351484e` |
| `outputs/four_side_1024_v2_r15_v01/validation/2d/B/combined.json` | 2 723 | `982b8ba77b2e1bbe712e975e784967d16418a89f55330c6790d584305b3b2edb` |

（R15 2D 的 z1/z2 单平面验收 JSON、R40 轮 summary、旧源码文件 sha256 均在 `OLD_MODEL_FIELDS.json` 中。）

### 6.3 复现/复核命令（只读）

```powershell
cd "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D"

# 旧 25D 顶层模型字段
.venv\Scripts\python.exe -c "import json; p='outputs/four_side_1024_v2_r15_v01/25d/schemeA/layers5/routes_25d.json'; d=json.load(open(p,encoding='utf-8')); print(d['layers_z_mm'], d['interface_layer'], d['statistics']['routed'])"

# 旧 flat 段 layer->z 与 transition z 对（见 §5.5 / 证据 JSON）
.venv\Scripts\python.exe -c "import json,collections; d=json.load(open('outputs/four_side_1024_v2_r15_v01/25d/schemeA/layers5/routes_25d.json',encoding='utf-8')); f=collections.Counter(); t=collections.Counter(); [ (f.update([(p['layer'],round(p['z_mm'],9))]) if p['kind']=='flat' else t.update([(round(p['z0_mm'],9),round(p['z1_mm'],9))])) for r in d['routes'] if r['status']=='routed' for p in r['parts'] ]; print('flat',dict(sorted(f.items()))); print('trans',dict(sorted(t.items())))"

# 旧验证结论
.venv\Scripts\python.exe -c "import json; d=json.load(open('outputs/four_side_1024_v2_r15_v01/25d/validation/all_validation.json',encoding='utf-8')); print({k:(v['passed'],v['routed'],v['min_3d_distance_mm'],v['min_curvature_radius_mm']) for k,v in d['runs'].items()})"

# 证据抽取文件
.venv\Scripts\python.exe -c "import json; d=json.load(open('four_side_1024/l3d/OLD_MODEL_FIELDS.json',encoding='utf-8')); print(d['schema'], d['old_model']['layers_z_mm'], d['old_model']['interface_layer']); print(d['reuse_conclusion']['reusable_geometry'])"
```

### 6.4 审计边界与不确定性

- 本审计**没有**重新运行旧 25D 路由器，也没有运行新 L3D 验证器；结论来自对代码的逐行阅读与对已交付 JSON 的统计/对照，属于“代码+产物审计”，不是“重跑复验”。
- 旧产物的 PASS/数字按“旧模型口径”理解；本审计只主张“它们不能迁移/继承”，不主张“旧结果在当时口径下算错”。
- 新模型 L2–L5 高度仍是未确认的仿真输入：本审计给出的新旧高度对照（0.125/0.25/0.375 vs 1.0/1.5/2.0/2.5 等）只是示例 preset，不代表已确认工艺值；任何新 L3D 验收都必须保留 `unconfirmed_simulation` 标记并拒绝正式验收。
- 旧 `r15/profile_r15.py` 的 import-time 半径绑定（`_REBIND_CONSTANTS` 含 `config25d.RADIUS_MM`，但 `path3d` 的默认参数不在其中）存在“先 import 后 apply 则默认半径仍为 R=40”的潜在顺序风险；旧 R15 产物实际使用 R=15（A5 transition 总长度 316.07 mm 与 R=15 公式一致），本审计仅提示该风险，不计入旧模型错误假设表。
- 文件行号以审计时的当前工作区文件为准；若后续有其它 teammate 修改 `fsd25d/`/`fslw/`，请以文件 sha256/修改时间戳为准重新定位。
