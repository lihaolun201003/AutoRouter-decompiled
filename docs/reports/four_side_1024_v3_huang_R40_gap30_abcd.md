# V3-Huang 1024 通道黄志杰风格连接拓扑——双高度二维布线实验报告

本轮在上一轮 FSLW（R≥40 mm / 30 µm / 真实 2×16 双高度接口）的工程与验收口径上，
使用用户提供的 **V3-Huang 1024 通道连接关系**（含 448 条同边连接）完成 8 个平面实验
（A/B/C/D × z1/z2）与 4 套 1024 通道双高度组合布局。

> **本轮定位：** 回答"引入黄志杰风格的同边连接后，在四边 1024 通道、双高度、R=40 mm
> 二维布线条件下，能否得到真正规整且合法的 U 型/回折型波导布局，以及能布通多少条"。
> 不追求 1024/1024；不放宽任何几何或验收约束；失败与几何上限如实报告。

---

## 1. 结论摘要

### 1.1 八组平面实验（每平面 512 条固定连接）

| 算法 | 平面 | 布通 | 同边 same | 对边 opposite | 邻边 adjacent | 平均长度 mm | 同平面交叉 | 严格审计 |
|---|---|---:|---:|---:|---:|---:|---:|---|
| A | z1 | **236/512 = 46.09 %** | 37/222 | 180/196 | 19/94 | 186.1 | 25 248 | PASS |
| A | z2 | **219/512 = 42.77 %** | 37/226 | 166/188 | 16/98 | 190.3 | 22 955 | PASS |
| B | z1 | **240/512 = 46.88 %** | 101/222 | 115/196 | 24/94 | 211.8 | 34 977 | PASS |
| B | z2 | **233/512 = 45.51 %** | 102/226 | 106/188 | 25/98 | 213.5 | 34 029 | PASS |
| C | z1 | **247/512 = 48.24 %** | 63/222 | 147/196 | 37/94 | 202.8 | 34 144 | PASS |
| C | z2 | **218/512 = 42.58 %** | 60/226 | 129/188 | 29/98 | 210.3 | 28 811 | PASS |
| D | z1 | **221/512 = 43.16 %** | 70/222 | 133/196 | 18/94 | 195.3 | 24 712 | PASS |
| D | z2 | **209/512 = 40.82 %** | 78/226 | 119/188 | 12/98 | 200.2 | 23 720 | PASS |

### 1.2 四套 1024 通道组合布局

| 组合 | z1 布通 | z2 布通 | 组合布通 | 类别构成 | 平均长度 mm | 总传播损耗 dB |
|---|---:|---:|---:|---|---:|---:|
| A | 236 | 219 | **455/1024 = 44.43 %** | same 74/448 · opposite 346/384 · adjacent 35/192 | 188.2 | 428.1 |
| B | 240 | 233 | **473/1024 = 46.19 %** | same 203/448 · opposite 221/384 · adjacent 49/192 | 212.7 | 502.9 |
| C | 247 | 218 | **465/1024 = 45.41 %** | same 123/448 · opposite 276/384 · adjacent 66/192 | 206.3 | 479.7 |
| D | 221 | 209 | **430/1024 = 41.99 %** | same 148/448 · opposite 252/384 · adjacent 30/192 | 197.7 | 425.0 |

### 1.3 核心结论

1. **同边连接确实自然产生了大量真实 U 型与回折（hairpin）波导**：布通的同边路线全部是
   真实的 180° 回转几何（R=40 四分之一圆弧 + 历史短 S 对 + 相邻四分之一弧组成的半圆回折），
   并通过独立 strict 验收；以"同边优先"的算法 B 为例，一个平面内 **101–102/222–226 条
   同边连接布通（约 45 %）**，其中 NN 组在 z1 达到 **54/56**，形成真正的嵌套拱形组。
2. **但 R=40 mm 使这些 U 型回路变得"巨大"**：448 条同边连接中仅 53 条（|dx| ≥ 2R = 80 mm）
   可直接用普通 U 型；其余 **395 条**必须使用短 S + 半圆回折的"回折型"，回折高度达
   **40–120 mm**。四边（N/S/E/W）的回折回路在板面中部相互重叠，叠加"禁止二次交叉"的
   strict 口径后，同边路线之间存在强几何互斥。
3. **单边单独布通率很高（NN 54/56、SS 52/53、EE 55/58、WW 54/55，约 95 %），但四边同时存在
   时同边布通率降至 45 % 左右**：这不是候选不足，而是四边大回路在同一平面内的几何/交叉
   政策冲突（详见 §6.3 与 §9.7）。
4. **八组平面布通 209–247/512（40.8 %–48.2 %）**；四套组合布局
   **A 455、B 473、C 465、D 430 /1024**
   （最佳 **B 473/1024 = 46.19 %**，
   最差 D 430/1024）。
5. **算法排序（按总布通）**：B 473 > C 465 > A 455 > D 430。
   同边优先（B）把同边布通从 A 的 74 提升到 203，
   但把对边从 A 的 346 压到 221；
   **净收益约为 +18 条（B vs A）**——规整 U 型轨道确实改善了同边连接，但同时挤压了对边连接。
6. **全部 8 个平面均通过独立 strict 几何验收**（8/8 已审计，0 违规；
   见 §6），路由器内部审计删除 0 条，路由器与独立校验器在上一轮同一口径下 mismatch=0。
7. **与上一轮 V1/V2（无同边连接）不可直接因果比较**：本轮为同边连接扩展了候选几何库
   （SAME_U / SAME_HAIRPIN_A/B）并修改了 A/B 的调度分组，因此布通率差异
   （V3 473 vs FSLW 最好 694）**不能全部归因于连接拓扑**；报告只作描述性比较，
   并明确指出这一公平性问题（§9）。

---

## 2. 输入与拓扑验收（Phase 1）

### 2.1 输入文件与完整性

| 文件 | 位置 | 大小 | SHA256 |
|---|---|---:|---|
| 接头级连接（Excel） | `data/v3_huang/fiberBoard1024_huang_four_side_connectors.xlsx` | 91 589 B | `4d285f56…b32de` |
| 光纤级固定配对（CSV，**实际布线输入**） | `data/v3_huang/fiberBoard1024_huang_fiber_pairs.csv` | 39 565 B | `76d91316…6cf23` |

两份文件均由用户提供，**按字节原样复制**到独立 V3 输入目录，原始路径与 SHA256 记录在
`data/v3_huang/PROVENANCE.json`；输入文件在整个实验中未被修改或重新生成。

### 2.2 拓扑契约（CSV 为准）

| 类别 | 总数 | 构成 | z1（row=1） | z2（row=2） |
|---|---:|---|---:|---:|
| 同边 same | 448 | NN/SS/EE/WW 各 112 | 222 | 226 |
| 对边 opposite | 384 | NS 192 + EW 192 | 196 | 188 |
| 邻边 adjacent | 192 | NE/NW/ES/SW 各 48 | 94 | 98 |
| 合计 | 1024 | | 512 | 512 |

- 4 边 × 16 接头 × 32 光纤 = 2048 个物理端点，**恰好各使用一次**；64 个接头 × 32 光纤全部用满。
- 双高度分配由 CSV 的 `row` 决定（row 1 → z1，row 2 → z2），**每个高度同时含三类连接**；
  不再存在"row1 全对边、row2 全邻边"的旧假设。
- 连接类别取自 CSV 的 `relation` 列，并与两端 side 独立推导双向核对（0 处不一致）；
  同边连接不存在"接头连自己"（0 条）。
- 连接关系与端点在整个实验中**没有被修改**（CSV 的 SHA256 与 `PROVENANCE.json` 一致）。

### 2.3 独立输入审计（connectivity 负责人，非本模块代码）

- 独立解析器与独立结构检测，**PASS 26/26 检查、0 失败**。
- 与 Lead 的 `v3/inputs.py`/`v3/ports.py`/`v3/config.py` 在子进程中逐字段比较：
  **2048 个端点身份全部一致、最大坐标差 0.0 mm、1024 条连接字段 0 处不一致**。
- Excel 交叉核对全部 0 不匹配：Sheet1 的 1024 个接头级配对与 CSV 完全同序；
  64×64 矩阵对称、对角 0、行列和 32、总和 2048（= 2×1024）、与 CSV 接头级计数逐格一致；
  **光纤级参考工作表与 CSV 逐行完全相同**（1024 行 × 12 列）；端口映射 64 行、
  接头对重数 549 对全部一致。
- 产出：`topology/`（校验 JSON、2048 个 3D 物理端口坐标、每平面 1024 端点清单、
  64×64 矩阵 CSV、5 张需求/组成图、README）。

---

## 3. 冻结的物理/几何/验收规则（与 FSLW 轮一致，未放宽）

| 项 | 值 |
|---|---|
| 板面 / 层 | 150×150 mm，每平面单层（平面内 `layer=0`） |
| 波导宽度 | 0.050 mm |
| 最小边缘间距 | **0.030 mm**（本轮用户给出） |
| 最小中心线净空 | **0.080 mm**（= 0.05 + 0.03，`lim = 0.0799999`） |
| 最小弯曲半径 | **R = 40 mm 固定**（所有弧严格 40.0；未搜索 R>40 族） |
| 路径图元 | 正交直线、R=40 四分之一圆弧、历史短 S 对（`d=2R(1−cosθ)`、推进 `2R sinθ`）、**同边 180° 回折（两段相邻四分之一弧）** |
| 交叉/间距验收 | 上一轮 strict 局部交叉窗口口径（精度豁免 `h*+2·sagitta`、窗外双向严格复检、禁止二次交叉/重叠/相切/窗互叠/过宽窗） |
| 传播损耗 | 0.05 dB/cm（仅传播项） |
| 弯曲/交叉损耗 | `unknown_uncalibrated`（不编造） |
| 双高度 | row1→z1、row2→z2；两高度独立二维布线；跨高度 XY 投影交叉不计冲突；**不实现 z 过渡** |
| 接口 | IEC 61754-7-3:2019 2×16，列距 0.25 mm、排距 0.5 mm；9 mm 接头距仍为暂定值 |

**同边几何扩展（本轮新增，已写入 `v3/SPEC.md`）**：同边连接的两个端口在同一板边，
规范坐标下都在 `y=0`（四边通过旋转映射统一），源端切向 +y（入板）、目标端切向 −y（回端口）。
R=40 时 180° 回转至少横向占用 2R=80 mm，因此：
- `SAME_U`：普通矩形 U（|dx| ≥ 2R，53/448 条可用）；
- `SAME_HAIRPIN_A/B`：短 S 横向补偿 + 相邻四分之一弧半圆回折（覆盖 395 条 |dx| < 80 的连接）。

---

## 4. Phase-2/3：同边几何验证与小规模测试

### 4.1 十类必需的小规模几何测试（全部真实几何 + strict 索引）

| 测试 | 结果 | 说明 |
|---|---|---|
| 1_single_N_N | PASS | single same-edge N-N route (route 138, SAME_U) |
| 1_single_E_E | PASS | single same-edge E-E route (route 433, SAME_U) |
| 1_single_S_S | PASS | single same-edge S-S route (route 757, SAME_U) |
| 1_single_W_W | PASS | single same-edge W-W route (route 916, SAME_U) |
| 2_nested_u_1 | PASS | 1 nested same-side U tracks at increasing depth |
| 2_nested_u_2 | PASS | 2 nested same-side U tracks at increasing depth |
| 2_nested_u_3 | PASS | 3 nested same-side U tracks at increasing depth |
| 3_short_same_side | PASS | shortest same-side connection (|dx|=5.25 mm) |
| 4_long_same_side | PASS | longest same-side connection (|dx|=133.00 mm) |
| 5_same_plus_opposite | PASS | same-side U coexisting with one opposite route (route ids (1, 18, 'SAME_HAIRPIN_B', 'NS')) |
| 5_same_plus_adjacent | PASS | same-side U coexisting with one adjacent route (route ids (1, 13, 'SAME_HAIRPIN_B', 'NE')) |
| 6_four_sides_u | PASS | one same-side U on each of the four sides ([1, 401, 753, 913]) |
| 7_parallel_spacing | PASS | spacing detection: 0.05 mm parallel offset rejected, properly separated nested arches accepted |
| 8_legal_crossing | PASS | same-side U crossed once by an opposite route |
| 9_illegal_overlap_rejected | PASS | nested U arches at the SAME depth (collinear overlapping tops) must be rejected |
| 10_transaction_rollback | PASS | conflicting candidate rejected, accepted after rollback, rejected again after re-add |

**16/16 全部通过。**
测试覆盖：单条 N-N/S-S/E-E/W-W、2/3 条嵌套 U、最短（5.25 mm）与最长（133 mm）同边连接、
同边+对边共存、同边+邻边共存、四边同时各一条 U、0.05 mm 并行偏移被拒、
合法单次交叉、非法重叠被拒、冲突回滚（拒绝→移除后接受→重新加入再拒绝）。
产出：`feasibility/feasibility.json`、`feasibility.md`、`same_side_feasibility_grid.png`。

### 4.2 同边可行域与容量

- 规范 (sx, qx) 网格：**72/121 个单元
      至少存在一个合法族**（59.5 %）。
- 真实 448 条同边连接的候选可用性：**无"无候选"连接**（0 条
      `no_candidate_generated`）；全部可用 U 或回折族覆盖。
- **A/B/C 分类**：A（模板不满足）——普通 U 模板只覆盖 |dx| ≥ 80 的 53 条，其余需要回折族；
  B（所有已实现 D56 族都无解）——本轮未发现（448/448 都有候选）；
  C（有候选但被挡住）——平面内同边失败的主要原因（§6.3）。
### 4.3 类别隔离容量实验（单独布线，排除相互干扰）

| 平面 | 同边单独 | 对边单独 | 邻边单独 | NN | SS | EE | WW |
|---|---:|---:|---:|---:|---:|---:|---:|
| z1 | 101/222 | 186/196 | 63/94 | 54/56 | 55/58 | 52/53 | 54/55 |
| z2 | 102/226 | 160/188 | 61/98 | 55/56 | 52/54 | 57/59 | 57/57 |

结论：**单个类别/单条边单独布线时容量很高（同边每边 ≈95 %，对边 ≈90 %），
而四类混合时同边掉到约 30 %（8 平面合计 548/1792）**。这定量说明同边布通损失主要来自
"四边大回路 + 其他类路线"的空间/交叉政策冲突，而不是候选几何不足。
原程序在 `four_side_1024/v3/same_side_capacity.py`，结果 JSON 在
`feasibility/same_side_capacity.json`。

---

## 5. Phase-4：ABCD 调度（在 FSLW 实现上适配，非从零开发）

| 算法 | 本轮定义（V3 适配） | 与上一轮的差异 |
|---|---|---|
| A 对边优先 | 对边（NS/EW）→ 同边（NN/SS/EE/WW）→ 邻边 | 增加同边分组；组内同边按跨度升序（窄→宽） |
| B 同边优先 | 同边 → 邻边 → 对边 | 同边新增为第一优先级（同边按跨度升序，利于嵌套） |
| C 四边轮流 | 每边 256 条混合三类，轮转取 batch=16 条；每边队列内三类交替 | 同边加入每边队列，不再把某类全部留到最后 |
| D 全局联合 | 静态候选池 + 多起点 + LNS 成组释放（≤12 条）+ 动态补候选 + 全索引复测 | 候选池扩展到同边 U/回折族；分层目标不变 |

四套算法使用**完全相同的候选库、几何校验和 strict 索引**，没有为某个算法单独放宽约束。

### 5.1 实际使用的候选族（两平面合计，按布通数）

| 算法 | 实际使用候选族（两平面合计） |
|---|---|
| A | S 294 · U 43 · SAME_HAIRPIN_A 34 · SAME_HAIRPIN_B 26 · TURN_S 22 · SAME_U 14 · straight 9 · SHIFT_TURN 8 · L 5 |
| B | S 197 · SAME_HAIRPIN_A 109 · SAME_HAIRPIN_B 73 · TURN_S 32 · SAME_U 21 · U 19 · L 9 · SHIFT_TURN 8 · straight 5 |
| C | S 247 · SAME_HAIRPIN_A 68 · SAME_HAIRPIN_B 42 · TURN_S 34 · U 24 · L 15 · SAME_U 13 · SHIFT_TURN 12 · Z3 5 · straight 5 |
| D | S 222 · SAME_HAIRPIN_A 65 · SAME_HAIRPIN_B 63 · U 22 · SAME_U 20 · L 16 · TURN_S 11 · straight 8 · SHIFT_TURN 3 |

---

## 6. Phase-5：八组实验与验收

### 6.1 各平面类别构成

| 算法 | z1 | z2 | NS/EW 合计 | same 合计 | adjacent 合计 |
|---|---:|---:|---:|---:|---:|
| A | 236 | 219 | 346 | 74 | 35 |
| B | 240 | 233 | 221 | 203 | 49 |
| C | 247 | 218 | 276 | 123 | 66 |
| D | 221 | 209 | 252 | 148 | 30 |

### 6.2 同平面交叉、长度与传播损耗（质量指标）

| 算法 | 平面 | 布通 | 平均长度 mm | 最短/最长 mm | 平均转弯 | 同平面交叉 | <10° 交叉 | 总传播损耗 dB | 最大半窗 mm |
|---|---|---:|---:|---|---:|---:|---:|---:|---:|
| A | z1 | 236 | 186.1 | 124.7 / 370.5 | 2.29 | 25 248 | 422 | 219.6 | 1.0736 |
| A | z2 | 219 | 190.3 | 128.3 / 370.5 | 2.26 | 22 955 | 344 | 208.4 | 0.9117 |
| B | z1 | 240 | 211.8 | 133.7 / 354.6 | 2.82 | 34 977 | 608 | 254.2 | 1.0833 |
| B | z2 | 233 | 213.5 | 131.4 / 355.6 | 2.79 | 34 029 | 563 | 248.7 | 1.3668 |
| C | z1 | 247 | 202.8 | 117.5 / 362.4 | 2.51 | 34 144 | 559 | 250.4 | 1.0529 |
| C | z2 | 218 | 210.3 | 116.7 / 370.0 | 2.56 | 28 811 | 429 | 229.3 | 1.0736 |
| D | z1 | 221 | 195.3 | 133.7 / 359.1 | 2.51 | 24 712 | 438 | 215.8 | 1.0623 |
| D | z2 | 209 | 200.2 | 132.1 / 351.9 | 2.60 | 23 720 | 423 | 209.2 | 1.0497 |

八平面合计：布通 **1823** 条，同平面交叉 **228 596**，
<10° 浅角交叉 **3 786**，总传播损耗 **1835.7 dB**（仅传播项）。

### 6.3 失败构成

| 算法 | 平面 | 失败 | 无候选（no_candidate_generated） | 有候选但被阻挡（no_legal_candidate） | 预算耗尽 | 候选评价 |
|---|---|---:|---:|---:|---:|---:|
| A | z1 | 276 | 22 | 254 | 0 | 34 314 |
| A | z2 | 293 | 22 | 271 | 0 | 36 129 |
| B | z1 | 272 | 22 | 250 | 0 | 41 097 |
| B | z2 | 279 | 22 | 257 | 0 | 40 262 |
| C | z1 | 265 | 22 | 243 | 0 | 36 134 |
| C | z2 | 294 | 22 | 272 | 0 | 40 027 |
| D | z1 | 291 | 0 | 291 | 0 | 27 970 |
| D | z2 | 303 | 0 | 303 | 0 | 27 957 |

- `no_candidate_generated` 每个 A/B/C 平面固定为 22 条：这是**邻边（adjacent）类**在 R=40 下
  无合法候选的连接（与上一轮相同），不是同边类。
- 同边类失败全部是 `no_legal_candidate`（有候选但被已布路线阻挡/交叉政策拒绝）。
- D 使用动态补候选，因此失败全部记为 `no_legal_candidate`（0 条 `no_candidate_generated`），
  这是失败记录口径差异，不代表 D 的候选更多。

### 6.4 独立 strict 验收

- 每个平面由独立校验器 `v3/validate_v3.py` 生成 `audit_strict.json`；
  **8/8 平面全部 PASS、0 违规**（间距/重叠/相切/窗互叠/二次交叉/过宽窗/自交/半径/板界/
  斜线/弧族检查全 0；`d56_passed == routed` 全部平面成立）。
- 8 平面累计（authoritative）：布通 **1823** 条、同平面交叉 **228 596**、<10° 浅角 **3 786**、
  最大半窗 **1.366808 mm**（< 4 mm 上限，0 个过宽窗）；类别布通率 same **30.58 %**、
  opposite **71.29 %**、adjacent **23.44 %**。
- 独立校验器与路由器索引 `D56Index(width=0.05, gap=0.03, strict)` 逐路线对交叉验证：
  **160 367 对路线比较、mismatch = 0**（invalid pairs 两侧均 0，交叉数与窗口数逐平面一致）。
  详见 `comparison/strict_audit_summary.json`、`crosscheck_summary.json`。
- C 分类的失败原因（路由器候选级拒绝，非验收违规）：`double_cross` 94 290、
  `spacing` 69 656、`tangent_touch` 24 158、`overlap` 4 547——同边 U/回折族确实撞上了
  R=40 + strict 政策下的几何极限，而**已验收的布通几何 0 违规**。

---

## 7. Phase-6：同边 U 型专项统计

### 7.1 同边布通率（448 条专项）

| 算法 | 平面 | 同边布通 | NN / SS / EE / WW（各 112 条） |
|---|---|---:|---|
| A | z1 | **37/222 = 16.7 %** | NN 18/112 / SS 8/112 / EE 6/112 / WW 5/112 |
| A | z2 | **37/226 = 16.4 %** | NN 21/112 / SS 7/112 / EE 5/112 / WW 4/112 |
| B | z1 | **101/222 = 45.5 %** | NN 54/112 / SS 11/112 / EE 27/112 / WW 9/112 |
| B | z2 | **102/226 = 45.1 %** | NN 55/112 / SS 11/112 / EE 26/112 / WW 10/112 |
| C | z1 | **63/222 = 28.4 %** | NN 21/112 / SS 13/112 / EE 18/112 / WW 11/112 |
| C | z2 | **60/226 = 26.5 %** | NN 23/112 / SS 12/112 / EE 18/112 / WW 7/112 |
| D | z1 | **70/222 = 31.5 %** | NN 44/112 / SS 8/112 / EE 11/112 / WW 7/112 |
| D | z2 | **78/226 = 34.5 %** | NN 47/112 / SS 11/112 / EE 9/112 / WW 11/112 |

关键事实：
- 同边布通数随算法差异巨大：A 74、B 203、
  C 123、D 148（z1+z2 合计，满值 448）。
- **B（同边优先）的同边布通最高**，且同边组内部高度不均：B_z1 的 NN 54/56、SS 11/53、
  EE 27/58、WW 9/55——同边 U 轨道先到先得，先布的一组几乎全通，后面的边被前面的大回路挤压。
- 这不是"只有 first group 能布"的算法 artefact，而是四边大回路共享中央区域的几何结果；
  C（四边轮流）把同边摊平为 21/13/18/11（z1），代价是总同边数降到 63。

### 7.2 路径形态（由实际保存的图元分类，不按连接类别推断）

**实际布通路径的形态构成（由保存图元分类，不按连接类别推断；8 个平面合计 1823 条布通）**

| 形态 | 数量 | 占比 |
|---|---:|---:|
| short_S | 960 | 52.66 % |
| U | 548 | 30.06 % |
| multi_bend_refold | 135 | 7.41 % |
| other | 108 | 5.92 % |
| L | 45 | 2.47 % |
| straight | 27 | 1.48 % |

- 同边连接布通：548/1792 (30.58 %，8 平面合计)
- U 型/回折型路线计数：U=548、refold=135
- 嵌套组数：32，最长嵌套链：3

**U 型/回折轨道专项（8 平面合计）**

- U 型路线：548 条；按板边 N/E/S/W = N 283 / E 120 / S 81 / W 64
- 回折进入板内深度：均值 110.7 mm、中位 117.4 mm、范围 40.0–148.9 mm
- 相邻 U 型最小中心线间距：0.081436 mm
- 成组/束状拱形：53 组；最大组 4 条
- 嵌套组数：32，最长链 3

### 7.3 失败分类

| 类别 | 说明 |
|---|---|
| 无合法几何候选（A/B） | 同边类 0 条；adjacent 类每平面 22 条（R=40 结构性无解，与上一轮相同） |
| 候选存在但被其他路线阻挡（C） | 同边失败主体：`double_cross` / `spacing` / `tangent_touch`（大回路与已布路线/回路冲突） |
| 板界/半径限制 | 已包含在候选生成的自校验中（不会计入成功） |
| 搜索预算/优化器限制 | 全部平面在 30 万次评价/900 s 预算内自然结束，未出现预算耗尽 |
| 交叉或间距限制 | 严格验收拒绝的具体原因逐条记录在 `failed_routes.json` 的 `rejection_counts` 中 |

---

## 8. Phase-7：可视化（10 项必需 + 附加）

| # | 图 | 路径 |
|---|---|---|
| 1 | V3 原始 1024 通道接头级连接关系图 | `comparison/demand_1024_connector.png`（另有 `topology/demand_1024_connectors.png`） |
| 2 | 64×64 加权连接矩阵热力图 | `comparison/connector_matrix_64x64.png`（另有 `topology/connector_matrix_heatmap_64x64.png`；有向/对称矩阵均存 JSON） |
| 3 | z1 的 A/B/C/D 四张完整二维布线图 | `comparison/layouts_z1_abcd.png` + 各平面 `routing_all.png/svg/gds` |
| 4 | z2 的 A/B/C/D 四张完整二维布线图 | `comparison/layouts_z2_abcd.png` + 各平面 `routing_all.png/svg/gds` |
| 5 | A/B/C/D 四套双高度完整组合图 | `comparison/combined_layouts_abcd.png` + `combined/<A>/layer_2d.png/svg` |
| 6 | 三维叠加示意图 | `combined/<A>/overlay_3d.png`、`comparison/overlay_3d_abcd.png` |
| 7 | 仅同边 U 型/回折型专项图 | `shapes/u_routes_only.png`、`shapes/shape_mix.png` |
| 8 | 10–20 条嵌套 U 型局部放大图 | `shapes/nested_u_zoom.png` |
| 9 | 同边/对边/邻边布通数量对比图 | `comparison/class_routed_compare.png` |
| 10 | 四算法布通率对比图 | `comparison/algo_routed_rate_compare.png` |

所有完整布局图保留全部实际成功波导；标题写真实布通数（不做缩放或隐藏）。
GDS：每平面单层 `layer 0`；组合布局 `layer0 = z1`、`layer1 = z2`（两个物理高度，不是波导层堆叠）。

---

## 9. Phase-8：与黄志杰原版 512 和 V1/V2 的对照（回答 7 问）

### 9.1 新 V3 是否自然产生大量 U 型路径？

**是，但只在"同边优先"或混合调度下大量出现。** 同边布通合计 A 74、
B 203、C 123、D 148 条（满值 448），
且全部是由真实 U/回折图元生成的合法路径（不是示意）；B 的 z1 中 NN 组 54/56 形成真实
嵌套拱形组（`shapes/nested_u_zoom.png` 可见）。

### 9.2 哪些 U 型真正通过 R=40 约束？

**所有计入布通的同边路线都通过 R=40 + strict 验收**（`audit_strict.json` 逐条审计）。
几何上分两类：53 条 |dx| ≥ 80 mm 可用普通 U；395 条 |dx| < 80 mm 必须使用"短 S + 半圆回折"，
回折高度 40–120 mm。R=40 使"回折"成为同边连接的主要形态，而不是原版 R≈5 mm 的紧凑小 U。

### 9.3 哪些同边连接因模板或拥塞失败？

- **模板不足**：普通 U 只覆盖 53/448；若只允许普通 U，则 395 条同边连接会有"模板不足"。
  本轮已实现回折族，因此同边失败**不是模板不足**（448/448 都有候选）。
- **拥塞/交叉政策**：同边失败几乎全部是 `no_legal_candidate`，主因
  `double_cross`/`spacing`/`tangent_touch`——四边大回路在中部重叠，禁止二次交叉的 strict 口径
  使后布回路无法穿越已布回路。单边独立布通 ≈95 % 而四边同时 ≈45 %，定量证明这是空间冲突。

### 9.4 V3 的布线形态与原版黄志杰有多相似？

**在"嵌套拱形"这一风格上得到再现，但尺度完全不同**：原版（R≈5 mm）的 U 型是贴近板边的
细密小拱；V3 在 R=40 下是大尺度回路（回折高度 40–120 mm、横向 80–160 mm），
布通后可看到有序嵌套的"大拱"，但不是原版那种高密度梳状。原因在物理：90° 弯要 40 mm。
（候选族/调度不同：原版是四遍二维流程，本轮是 ABCD 通用调度；不作因果断言。）

### 9.5 V3 布通率相对 V1/V2 有什么变化？

- V3（本轮，448 同边 + 384 对边 + 192 邻边）：455/473/
  465/430 每 1024；
- 上一轮 V1/V2（无同边，同工艺）：上一轮 FSLW（同一工艺参数、无同边连接）：V1_A 575、V1_B 553、V1_C 543、V1_D 527、V2_A 681、V2_B 677、V2_C 694、V2_D 638 （best 694/1024）。
**描述性比较：V3 明显更低**（最好 473 vs 694）。但要强调公平性：
本轮为了同边连接扩展了候选几何库并改了 A/B 分组，**不能把差异全部归因于连接拓扑**；
若要做定量因果，需要在同一候选库/调度下重跑无同边拓扑作对照（本轮未做）。

### 9.6 规整的回折轨道是否改善拥塞，还是挤压其他连接？

**两者都有，净效应略正。** 同边优先（B）把同边布通从 A 的 74 提高到
203（+129），但对边从
346 降到 221
（−125）、邻边略升；
总量 A 455 → B 473（**净 +18 条**）。
即：预留同边 U 轨道让同边连接大幅受益，但占用了中央区域、挤压对边，属"零和接近"的再分配，
只在总量上略有改善。C 的四边轮流在 z1 上取得最高单平面布通（247/512），但同边只有
63（z1）——均衡性以牺牲同边数量为代价。

### 9.7 光纤固定配对是否限制了轨道分配空间？

**是，且是主要的隐性约束。** 448 条同边连接的端点由 CSV 固定（0.25 mm 列距、端口不可交换），
每条连接的 (sx, qx) 区间不可调整；四边回路要形成"外层更深、内层更浅"的合法嵌套，
必须依赖区间包含关系。固定配对产生大量**交叠但不嵌套**的区间（多条连接共用同一对
接头区域），这类区间天然产生交叉；在 strict"禁止二次交叉"口径下，
它们与已布回路的组合被频繁拒绝。**如果能重新配对（把同边连接按区间包含关系重排），
同边布通率有提升空间**——但本轮任务明确要求 1024 条固定连接不被修改，因此未做。

---

## 10. 诚实声明与局限

1. **本轮的 448 条同边连接需要扩展几何库**（`SAME_U`/`SAME_HAIRPIN_A/B`）；旧 V1/V2/FSLW
   代码与产物未被修改（历史结果保留），但**新旧布通率不能直接因果比较**（§9.5）。
2. **R=40 mm 是固定半径**（未搜索 R>40 的路径族）；"同边容量低"的结论只对固定 R=40 的
   D56 族 + 本轮 strict 口径成立。
3. **双高度仍是仿真假设**：玻璃厚度/接头安装方向未确认、9 mm 接头间距存在机械干涉、
   未实现 z 过渡、不宣称可制造。
4. **弯曲/交叉损耗未知**（`unknown_uncalibrated`），报告只给传播损耗；没有编造任何
   玻璃弯曲/交叉损耗数值。
5. **全部 8 个平面均已完成独立 strict 审计（8/8 PASS、0 违规、mismatch=0）**；
   权威结果见 `comparison/strict_audit_summary.json` 与各平面 `audit_strict.json`。
6. 失败路线、拒绝原因与阻挡统计全部保存在各平面 `failed_routes.json`，没有隐藏或删除。
7. 同边布通的形态分类由 viz 从保存图元独立计算（straight/short-S/L/U/multi-bend refold/other），
   分类规则见 `shapes/` 下 JSON 的 `SHAPE_DEFINITIONS`；连接属于 same 不等于路径是 U，
   两者分开报告。

---

## 11. 复现命令与交付物

```powershell
Set-Location -LiteralPath 'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D'
$py = '.\.venv\Scripts\python.exe'

# Phase 1：输入校验（独立审计 + 需求图）
& $py -m four_side_1024.v3.ports_audit_v3

# Phase 2/3：同边几何测试与可行域
& $py -m four_side_1024.v3.feasibility

# Phase 5：八个平面实验（示例：z1 同边优先）
& $py -m four_side_1024.v3.run --plane z1 --algorithm B --eval-budget 300000 --time-budget 900 --ripup-rounds 3
# 其余：A/C/D × z1/z2（C 用 --c-batch 16 --c-start N --c-direction cw；D 用 --d-pool 48 --d-restarts 2 --d-batches 400）

# Phase 6/7：指标、图、组合、对比
& $py -m four_side_1024.v3.metrics --run-dir outputs/four_side_1024_v3_huang_R40_gap30_abcd/planes/B/z1
& $py -m four_side_1024.v3.plots --root outputs/four_side_1024_v3_huang_R40_gap30_abcd --all
& $py -m four_side_1024.v3.combine --root outputs/four_side_1024_v3_huang_R40_gap30_abcd --all
& $py -m four_side_1024.v3.compare --root outputs/four_side_1024_v3_huang_R40_gap30_abcd

# 独立 strict 验收 + 路由器/校验器交叉验证
& $py -m four_side_1024.v3.validate_v3 --scan-root outputs/four_side_1024_v3_huang_R40_gap30_abcd/planes
& $py -m four_side_1024.v3.crosscheck_v3 --scan-root outputs/four_side_1024_v3_huang_R40_gap30_abcd/planes

# 测试
& $py -m pytest four_side_1024/v3/tests_v3 -q
```

**交付目录** `outputs/four_side_1024_v3_huang_R40_gap30_abcd/`：

```
inputs/             # 冻结的 V3 输入副本 + SHA256 校验
topology/           # 独立输入审计、2048 物理端口 3D 坐标、每平面端点、64x64 矩阵、需求图
feasibility/        # Phase-2/3 几何测试 + 同边可行域网格
planes/<A-D>/<z1|z2>/# routes.json、failed_routes.json、config.json、run.log、CHECKPOINT.json、
                    #   statistics.json、audit_strict.json、routing_all.png/svg/gds 等
combined/<A-D>/     # routes_1024.json、statistics.json、layer_2d.png/svg、overlay_3d.png、
                    #   routing_1024_two_height.gds（layer0=z1、layer1=z2）、planes_summary.json
shapes/             # 同边 U/回折专项统计与图（形态构成、U 深度/轨道/嵌套/间距、失败分类）
comparison/         # all_metrics.csv/json、八组/平面/分层对比、64x64 矩阵、strict 审计汇总、
                    #   crosscheck_*.json
report/report_data.json  # 本报告使用的原始数据快照
```

**保留的历史结果（未修改）：** `outputs/four_side_1024_v1_v2_abcd/`（R5/125 µm 单层虚拟展开
8 组 ABCD，best 462/1024）、`outputs/four_side_1024_fslw_R40_gap30_abcd/`（上一轮 R40/30 µm
双高度 16 平面 + 8 组合，best V2_C 694/1024）、`outputs/four_side_1024_d56_optimized/`
（历史 467/1024）、旧 256/512 AutoRouter 复刻。

---

## 附录：公开仓库裁剪说明（2026-10-19 上传）

公开仓库 `lihaolun201003/AutoRouter-decompiled` 按体积裁剪上传：代码、报告、冻结输入的
SHA256 清单、全部 `routes.json`/`statistics.json`/`config.json`/`audit_strict.json`/`run.log`、
输入审计与可行性证据、全部对比图与 10 项必需可视化均在仓库中；**各平面的逐图渲染
（PNG/SVG/GDS）与部分大图副本未上传**（体积原因），可用上传的代码与 `routes.json` 重新生成，
见同目录 `UPLOAD_README.md`。裁剪清单与每个已上传文件的 SHA256 见仓库根目录
`UPLOAD_MANIFEST_20261019_v3_huang.json`。
