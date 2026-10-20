# R15 光波导布线实验报告（1024 通道四边 V2 双高度 / 五层 2.5D）

- 日期：2026-10-20
- 项目：`OpticalWaveguideRouter2D`
- 本轮唯一几何变更：**所有平面弯曲与三维升降弯曲统一按最小曲率半径 R = 15 mm 设计**
- 数据根目录：`outputs/four_side_1024_v2_r15_v01/`（R40 历史目录保持原样，未覆盖、未混用）
- 参考形状：师兄《密集光路板.pdf》第 1 页（总版图 / 第一层 / 第二层 / 两层互连）
- 详细几何对照见 `four_side_1024/r15/PDF_GEOMETRY.md`；半径硬编码审计见
  `four_side_1024/r15/RADIUS_AUDIT.md`。

---

## 0. 一句话结论

R15 把二维 D56 从 752 提升到 **943/1024**（+191），把二维纯正交 90° 从 262
提升到 **515/1024**（+253，接近翻倍，但仍只有 D56 的 54.6%），五层 2.5D 进一步
达到 **A 985/1024、B 723/1024**。半径缩小到 15 mm 后纯正交方案布通率显著恢复，
但没有恢复到 D56 的水平；五层抬升对纯正交的增益（R15 +208）明显大于对 D56
的增益（R15 +42），因为纯正交的失败池更大（509 vs 81）。

---

## 1. 本轮工艺要求与范围

1. **R15 优先于一切历史参数**：历史代码的 R = 40 mm、PDF 示例中的 R = 6000 µm /
   R = 6137.33 µm 均不作为本轮半径；PDF 只用于几何形状与版图组织方式的参考。
2. 保持 V2 的 1024 条连接、真实双高度接口（z1 = 0.0 mm、z2 = 0.5 mm）、
   150 × 150 mm 板、波导宽度 0.050 mm、边缘间隙 0.030 mm（中心线净空 0.080 mm）、
   交叉策略 strict 等全部已确认约束不变。
3. 五层高度 `z = [0, 0.125, 0.25, 0.375, 0.5] mm` **仍是仿真假设**，不是师兄确认的
   工艺参数；本轮不改变层数、不改端口位置、不改连接关系、不做 Native 3D 联合寻路。
4. 损耗：本轮不引入任何新损耗系数；只统计长度/弧/交叉等几何量，损耗参数按
   “已标定 / 待标定”分类（见 §7），不输出总损耗结论。
5. 历史 R40 全部结果保留在 `outputs/four_side_1024_v2_candidate_rr_v01/`（752）、
   `outputs/four_side_1024_v2_ortho90_v01/`（262）与
   `outputs/four_side_1024_v2_25d_v01/`（A 820 / B 383），本轮不写这些目录。

---

## 2. PDF 几何对照与本轮几何推导

### 2.1 PDF 页内容与形状语义

参考 PDF 只有 1 页，含四个图题：**总版图**、**第一层**、**第二层**、**两层互连**。
页内尺寸标注（渲染页读得）：端口间距 127 µm、bank 间距 250 µm、直段 L = 8000 µm、
横向偏移 2000 µm、90° 弯 R = 6000 µm（两处）、2R = 7746 µm、
第二层平面 S 弯 R = 6137.33 µm、层间升降高度 50 µm / 水平长度 1000 µm。

PDF 的可参考价值在**形状与组织方式**：

| PDF 形状 | 本轮对应几何族 | R15 取值 |
|---|---|---|
| 总版图/第一层的 90° 转弯（R6000 标注） | 四分之一圆弧连接水平/竖直直线；D56 与纯正交均使用 | R = 15 mm（横/纵各占 15 mm），不用 R6000 |
| 总版图/第一层同侧 180° U（2R=7746 标注） | 同侧端口 U 型：纯半圆 / 直线+半圆+直线 / 两段 90° 弧+中间直段 | 最小可行间距 **2R = 30 mm**；纯半圆仅 d = 2R，d > 2R 用 quarter_pair；d < 2R 拒绝、不缩半径 |
| 总版图红色曲线 / “第二层”平面 S 弯（R6137.33） | 对侧端口的反向双弧 S（横向偏移 dx，保持航向） | R = 15 mm；dx < 2R 时 θ = acos(1 − dx/(2R))，纵向推进 2R·sinθ；dx ≥ 2R 退化为两段 90° 弧 + 中间直段 |
| “两层互连”（50 µm 高度 / 1000 µm 长度） | 垂直面内两段同向圆弧的升降 S 曲线 | θ = acos(1 − |Δz|/(2R))，footprint = 2R·sinθ，弧长 = 2R·θ；R = 15 mm 重新计算（表 2） |
| 第一层 / 第二层两张图 | V2 双高度接口模型：z1（row 1）与 z2（row 2，Δz = 0.5 mm），每层独立二维布线 | 层间以升降 S 曲线连接；同层冲突按平面内 strict 检查，跨层 XY 投影重叠不算冲突（冻结 SPEC §2） |

### 2.2 PDF 数值的处理（全部不照抄）

| PDF 数值 | 本轮处理 / 重算值 |
|---|---|
| 127 µm 端口间距 | 不用：本轮用 IEC 61754-7-3:2019 2×16 MPO 的列距 **250 µm**，行距 500 µm 由 0.5 mm 双层高度实现 |
| 250 µm bank 间距 | 与 IEC 列距 0.25 mm 数值一致，作为标准值参考，不是照抄 PDF |
| L = 8000 µm 直段 | 不强制：直段长度由布线器在 150×150 mm 板上按障碍与轨道求解 |
| 2000 µm 横向偏移 | 重新推导：R15 下一个 90° 弯恰好占用 R = 15 mm，2 mm 在 R15 下不可行 |
| R = 6000 µm（90° 弯） | 不用；本轮 R = 15 mm（2.5 倍） |
| 2R = 7746 µm（U/S 行距） | 不用；其隐含 U 半径 3873 µm，本轮同侧 U 最小间距 2R = 30 mm |
| R = 6137.33 µm（第二层平面 S） | 不用；本轮平面 S 一律 R = 15 mm，θ 由实际 dx 反解 |
| 50 µm / 1000 µm（层间升降） | 不用（隐含 R ≈ 5.01 mm）；本轮升降按 R15 公式重算（表 2）；实际 Δz 取 0.125/0.25/0.375/0.5 mm |

### 2.3 R15 升降 S 曲线重新推导（相对 R40 的差异）

半径 R、层间高差 Δz，两段同向圆弧的中心对称 S 曲线：

- 转角：`theta = acos(1 - |dz| / (2R))`
- 水平占用：`footprint = 2R * sin(theta)`
- 弧长：`length = 2R * theta`

| Δz (mm) | R15 θ | R15 footprint (mm) | R15 弧长 (mm) | R40 footprint (mm) | R40 弧长 (mm) |
|---:|---:|---:|---:|---:|---:|
| 0.125 | 5.232° | 2.7358 | 2.7396 | 4.4704 | 4.4735 |
| 0.250 | 7.402° | 3.8649 | 3.8757 | 6.3245 | 6.3376 |
| 0.375 | 9.069° | 4.7286 | 4.7484 | 7.7926 | 7.8233 |
| 0.500 | 10.475° | 5.4544 | 5.4849 | 9.0983 | 9.1531 |

R15 的升降 footprint 约为 R40 的 0.60–0.61，弧长同理；五层堆叠
`[0, 0.125, 0.25, 0.375, 0.5]` 不变，因此 R15 下可用更短的直段容纳升降、
更大的候选集，5 层结果明显改善。

### 2.4 同侧 U 模块（本轮新增，V2 本身不涉及同侧）

`four_side_1024/r15/u_geometry.py` 实现三类合法 U 族并全部通过冻结
`fslw.geom.canonical_validate`（R = 15、板 150、width 0.05、切线连续）：

- `half_circle`：d = 2R = 30 mm 时的一条 180° 半圆；
- `stadium`：直线 + 半圆 + 直线（同 d = 2R）；
- `quarter_pair`：直线 + 90° 弧 + 直线 + 90° 弧 + 直线，d > 2R 时中间直段 = d − 2R。

结论：**最小可行同侧间距 = 2R = 30 mm**，d < 30 mm 一律拒绝而不是缩小半径；
在真实 V2 端口表（每侧每平面 256 端口、32640 个同侧无序对）中，R15 可行
**20 098 对 = 61.6%**，R40 仅 6 706 对 = 20.5%（约 3 倍）。本轮 V2 配对不含同侧，
因此 U 模块只做几何实现与测试，不为测试修改 V2 连接。

---

## 3. R15 实现方式与半径审计

### 3.1 统一进程配置（profile）

`four_side_1024/r15/profile_r15.py` 在任何绑定半径的模块 import 之前调用：

- 把 `fslw.config.RADIUS_MM` 从 40 改为 **15**，`FIXED_RADIUS_40MM = False`；
- 替换 `fslw.config.process_record()`，使所有产物的 process 记录写入
  `min_bend_radius_mm = 15 / radius_mm = 15 / fixed_radius_40mm = false`；
- **import 期绑定模块**（`v2opt.candext.R`、`v2opt.ortho90.R`、
  `fsd25d.config25d.RADIUS_MM`、`fsd25d.path3d` 默认 transition 半径、
  `fsd25d.validate25d.RADIUS_MM/MIN_CURVATURE_MM` 等）必须在 apply 之后 import。

### 3.2 并行 worker 的半径修复（本轮实际发现的缺陷）

第一轮 R15 A/z1 用 R&R 时发现：**R&R 的 multiprocessing worker 在 Windows spawn 下
重新 import 模块，半径回落到 R40**，导致 67/506 条路由混入 R40 短 S 弧。修复分三层：

1. `fslw/config.py` 支持环境变量 `FSLW_PROCESS_RADIUS_MM`（默认缺省仍是 40，
   R40 历史行为不变），子进程 import 时即绑定正确半径；
2. `profile_r15.patch_radius()` 在父进程设置该环境变量，并回填已 import 模块的
   模块级半径常量；
3. R&R / parallel sweep 的任务载荷携带 `process_radius_mm`，worker 入口调用
   `four_side_1024/r15/worker_boot.ensure_profile()` 再生成候选。

修复验证：新起 multiprocessing 子进程测试显示所有子进程均绑定 R = 15；
被污染的首个 A/z1 产物已隔离到
`outputs/four_side_1024_v2_r15_v01/work/incident_r40_worker_contamination/A_z1_before_fix/`
作为审计证据，重跑后的 A/z1（498 条）独立扫描 762 条弧全部 R = 15、0 违规。
这是本轮“避免只改配置却仍按 R40 生成/判断路径”要求的一个具体落实点。

### 3.3 半径相关硬编码/候选限制/验收阈值审计

完整逐文件审计见 `four_side_1024/r15/RADIUS_AUDIT.md`，摘要：

| 类别 | 位置 | 本轮处理 |
|---|---|---|
| import 期绑定 | `v2opt/candext.py` L34 `R = C.RADIUS_MM`；`v2opt/ortho90.py` L38；`fsd25d/config25d.py` L53；`fsd25d/path3d.py` 默认参数；`fsd25d/validate25d.py` L105/107；`v2opt/ortho90_validate.py` L28 | 全部在 profile.apply() 之后 import；worker 走 worker_boot 回填 |
| 硬编码 40 字面量 | `fslw/validate_fslw.py` L65 `RADIUS=40`（但 `build_report(radius=...)` 与 process 记录可覆盖，R15 验收显式传 15）；`fslw/config.py` 默认 40 与环境变量 | R15 验收全部显式 `radius=15`；产物 process 记录 15/False；R40 默认行为不变 |
| 冻结但非本轮验收器 | `d56/validate_d56.py` 冻结 R5（历史 D56 轮），`v3/*` 冻结 R40 | 本轮不用作 R15 验收器；R15 用 `fslw.validate_fslw`（radius=15）+ `fsd25d.validate25d`（R15 profile） |
| 纯文案 | 多个模块 docstring/标题仍写 R>=40 | 仅注释；本轮 R15 图件/报告由 profile 动态取值 |
| 半径无关 | `fslw/geom.py`、`fslw/candidates.py`、`d56/index.py`、U 模块 | 调用时读 config 或显式参数，无需改 |

候选限制/搜索范围方面：R15 没有降低预算或放松阈值，而是**重新生成**候选池与
轨迹坐标（candext / ortho90 的坐标基由 R 动态推导），2D 全部从空布局重新搜索，
没有使用任何 R40 的候选缓存、最优结果或验收参数；5 层实验只使用本轮 R15 的
二维布局作为 baseline。

---

## 4. 二维 R15 实验（A：D56+Short-S；B：纯正交 90°）

### 4.1 实验设置

- A：D56 图元 = 正交直线 + R15 的 90° 圆弧 + R15 短 S（两段反向弧，
  θ = acos(1 − d/(2R))，θ < 90°），允许非 90° 平面弧；
- B：纯正交 = 仅轴对齐直线 + 精确 90°、R15 的圆弧，不含任何非 90° 平面弧；
- 两组都使用 `v2opt.search.sequential_commit`（候选预算 1600）+ 强化 R&R
  （A z1/B z1：4 轮、24 transactions、sizes 1/2/4；A z2/B z2：4 轮、64 transactions、
  sizes 1/2/4/8），固定种子 20261019。
- 顺序策略在 R15 下重新扫描（历史 R40 用的 round-robin / group 顺序不再最优）：
  z2 各跑 csv / group_ensw / group_swesnw / round_robin_N_cw / global_congestion
  等顺序（独立 root），取最好顺序再做 R&R：
  - A z2：round_robin_N_cw **437**（group_swesnw 411、csv 409、global_congestion 387）；
  - B z2：round_robin_N_cw **331**（group_swesnw 313、csv 312、group_ensw 306）；
  - z1 采用 NS→EW、x 降序顺序（历史经验）。
- 全部从空布局重新生成，无 R40 缓存/结果复用。

### 4.2 二维结果

| 方案 | z1 布通 | z2 布通 | 合计 | z1 失败 | z2 失败 | z1 同层交叉 | z2 同层交叉 | z1 最小间距 mm | z2 最小间距 mm |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A（D56+Short-S） | 498 | 445 | **943/1024** | 14 | 67 | 69 072 | 67 110 | 0.0802950 | 0.0832720 |
| B（纯正交 90°） | 184 | 331 | **515/1024** | 328 | 181 | 13 342 | 40 842 | ≥0.08（验收 0 违规） | ≥0.08（验收 0 违规） |

- 2D 独立 strict 验收（`fslw.validate_fslw`，policy=strict，显式 `radius=15`）：
  A z1/z2/combined、B z1/z2/combined 全部 **PASS**，全部弧半径 = 15 mm（0 条非 R15 弧），
  所有 violation 计数为 0，组合 1024 通道分别 **PASS 943** 与 **PASS 515**。
- 最小非交叉中心线距离：A z1 = 0.080295032 mm、A z2 = 0.083271974 mm；
  B z1 = 0.094654426 mm、B z2 = 0.0799999999999983 mm（恰好落在 0.08 mm 边界，
  冻结 strict 口径按 `clearance − 1e-7` 容差判定合法）。B 的 z2 距离余量为 0，
  工艺上属于临界情形，见 §9 限制。
- 失败原因（R15）：A 失败 81 = z1 14 + z2 67（“no legal candidate” 79 + 无候选 2）；
  B 失败 509 = z1 328 + z2 181（“no legal candidate” 431 + 复分析失效 76 + 无候选 2）。
- 关键对比：R40 的纯正交 z1 有 384/512 因 `2R = 80 mm > 相邻对所需横向偏移` 而无候选；
  R15 下 `2R = 30 mm`，邻边 L 族要求从 `qy ≥ 40` 降为 `qy ≥ 15`，
  B z2 从 134 → **331**（+147%）；但对侧小偏移（dx = 8/16/24 mm）在纯正交下仍难：
  一段反向 90° 弧对固定横向位移 2R = 30 mm，无法直接得到 8/16/24，
  组合弧对也受限，因此 B z1 只有 184（R40 128，+56）。
  D56 的短 S 恰好覆盖 dx < 30 mm 的连续位移，A z1 因此保持 498。

### 4.3 几何构成

| 方案 | 弧数 | 90° 弧 | 短 S 弧 | 短 S 平均转角 | 短 S 弧长 mm | 90° 弧长 mm | 总弧长 mm | 总长 mm |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 1 917 | 645 | 1 272 | 50.20° | 16 716.0 | 15 197.5 | 31 913.4 | 149 599.5 |
| B | 1 141 | 1 141 | 0 | — | 0 | 26 884.2 | 26 884.2 | 88 847.4 |

A 的 z1 全部由短 S 组成（762 条非 90° 弧，对侧小偏移），z2 是 645 条 90° 弧 +
510 条短 S；B 全部为 90° 弧。所有弧半径严格 15.000000 mm。

---

## 5. 五层 2.5D R15 实验

### 5.1 设置

- 沿用 `four_side_1024/fsd25d/` 模块；五层 `z = [0, 0.125, 0.25, 0.375, 0.5] mm`
  （仿真假设，未变）；z1 接口层 0、z2 接口层 4；
- 2D baseline 换成**本轮 R15 的二维布局**（A 943、B 515），未使用 R40 缓存；
- R15 升降 S 曲线按 §2.3 重新计算；router 参数与 R40 轮相同（budget 400、
  passes 3、flat-probe 12、R&R 2 轮）以保持可比性；
- 独立 3D 验收 `fsd25d.validate25d`（R15 profile 下 `RADIUS_MM = 15`、
  `MIN_CURVATURE_MM = 14.985`），不依赖 router 几何，独立重建 S 曲线并采样
  0.02 mm 检查曲率、端口高度/切线、板边距、真实 3D 净空（≥ 0.08 mm）与
  同层 strict 冲突。

### 5.2 五层结果

| 方案 | 布通/总数 | 相对 2D 新增 | 抬升路由 | 升降次数 | flat 长 mm | transition 长 mm | 总长 mm | 最小曲率 mm | 最小 3D 净空 mm | 同层交叉 | 验收 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A（Short-S） | **985/1024** | +42 | 42 | 84 | 159 878.2 | 316.1 | 160 194.2 | 14.99999996 | 0.0802950 | 137 081 | **PASS** |
| B（纯正交） | **723/1024** | +208 | 208 | 416 | 134 923.5 | 1 538.7 | 136 462.2 | 14.99999997 | 0.0800000 | 63 816 | **PASS** |

A 的细节：z1 512/512（2D 498 + 抬升 14），z2 473/512（2D 445 + 抬升 28）；
travel layer 分布 {1:32, 2:6, 3:4}；Δz 分布 0.125:36、0.25:12、0.375:36；
所有 transition 半径 15.000000；各层 flat 段数
{0:526, 1:32, 2:6, 3:4, 4:501}；逐层交叉
{0:69 072, 1:424, 2:48, 3:16, 4:67 521}；2D 失败中 2 条无 2D 候选、37 条
升降段无法在净空内放置（21 次 pass 尝试 + 2 轮 R&R 后仍失败）。
B 的细节见 §5.3。

### 5.3 五层失败分析（B）

B 的二维 baseline 515（z1 184 + z2 331），总失败 509 条；其中 78 条在当前二维
布局下没有任何 2D 候选（no-2D-candidate），可尝试抬升 431 条。3 遍 pass 中
pass 1 放置 198 条（431 次尝试），pass 2/3 无新增；2 轮 R&R 另外增加 16 条
（+15、+1）。最终 **723/1024**（z1 332 = 184+148；z2 391 = 331+60），
失败 301 = 78 条无 2D 候选 + 222 条升降段/层间净空无法放置。

B 的 travel layer 分布 {1:69, 2:66, 3:73}，Δz 分布
（0.125 mm:160、0.25 mm:132、0.375 mm:124，共 416 条 transition）；
每层 flat 段 {0:480, 1:69, 2:66, 3:73, 4:451}；各层同层交叉
{0:13 724, 1:2 684, 2:2 881, 3:3 663, 4:40 864}，总计 63 816；
所有 416 条 transition 半径 = 15.000000 mm、θ/footprint/弧长按 R15 公式
独立复核通过；最小 3D 净空 0.0800000 mm（恰在冻结 strict 的
`clearance − 1e-7` 容差内），最小曲率 14.99999997 mm，独立验收 0 违规。
纯正交的五层增益（+208）远大于 D56（+42），因为其二维失败池大得多，
而 R15 升降 footprint 更小、候选更易找到合法放置。

---

## 6. R40 vs R15 对照与结论

### 6.1 用户要求的对照表

| 方案 | R40 历史结果 | R15 新实验 | Δ（R15−R40） | 相对变化 |
|---|---:|---:|---:|---:|
| 二维 D56（Short-S） | 752 | **943** | +191 | +25.4% |
| 二维纯正交 90° | 262 | **515** | +253 | +96.6%（×1.97） |
| 五层 2.5D + Short-S | 820 | **985** | +165 | +20.1% |
| 五层 2.5D + 纯正交 | 383 | **723** | +340 | +88.8% |

说明：R40 列只有冻结的历史布通数（752 = z1 508 + z2 244；262 = z1 128 + z2 134；
5L A 820 / B 383）；R15 全部为本轮从图元重算并独立验收的数据，两轮不混用。

### 6.2 半径 40 → 15 的影响

1. **纯正交方案显著恢复**：262 → 515（×1.97）。主要原因：
   - 90° 弯 footprint 从 40×40 mm 降到 15×15 mm，板内可用轨道/结构坐标大幅增多；
   - 邻边 L/TURN 族条件 `qy ≥ R` 从 40 mm 降到 15 mm，z2 绝大多数邻边连接
     第一次拥有 L 族候选，B z2 从 134 提升到 331（+147%）；
   - 但纯正交对“对侧小横向偏移（8/16/24 mm）”仍缺乏灵活几何：单对反向 90° 弧
     横向位移固定为 2R，不能直接产生 8/16/24 mm，组合也受限，因此 B z1 仅
     128 → 184。这是纯正交方案的结构性短板，不是搜索预算问题。
2. **D56 也明显受益**：752 → 943（+25.4%）。R15 短 S 覆盖 dx < 30 mm 的连续
   横向偏移（θ = 42.8° / 62.2° / 78.5°，对应 dx = 8/16/24 mm），有效替代了 R40
   的“大半径短 S + 大量绕行”；A z1 498、A z2 445。
3. **顺序最优策略随半径改变**：R40 最优 z2 顺序是 group_swesnw 类；R15 下
   round_robin_N_cw 最好（A 437、B 331）。说明半径改变后候选空间/冲突结构变化，
   顺序必须重新扫描，不能沿用 R40 结论。
4. **五层额外收益**：
   - A：820 − 752 = +68（R40）；R15：985 − 943 = **+42**。二维已经更高，
     剩余失败池从 272 缩到 81，可抬升空间变小。
   - B：383 − 262 = +121（R40）；R15：723 − 515 = **+208**。纯正交二维失败池从
     762 缩到 509，但 R15 升降 footprint 更小、五层可抬升的失败路由比例更高，
     因而 5 层对纯正交的增益反而比 R40 更大（+208 vs +121）。
5. **问题回答**：
   - “半径从 40 mm 改为 15 mm 后，纯正交方案是否能够恢复较高布通率？”
     **是，显著恢复（262 → 515，约翻倍），但仍明显低于 D56（943）**；
     R15 修复了邻边连接（z2 134 → 331），但没有修复对侧小偏移的纯正交几何短板。
   - “五层抬升还能带来多少额外收益？”
     A 仅 +42（R40 时 +68），因为 D56 的 2D 失败池已经很小；
     B +208（R40 时 +121），因为纯正交的二维失败池仍有 509 条且 R15 升降段
     更容易找到合法位置——五层抬升对纯正交的边际价值明显更大。
   - 综合最优仍是 **D56 + 五层 2.5D（A 985）**；纯正交即使 R15 + 五层
     （B 723）仍未追上 D56 的二维（943）。

### 6.3 几何/工艺层面的差异

- 90° 弯：R40 占 40×40 mm，R15 占 15×15 mm（面积约 14%），板内可容纳的
  弯/轨道数量大幅增加；
- 同侧 U 最小间距：R40 80 mm → R15 30 mm（同侧可行端口对 20.5% → 61.6%）；
- 升降 S：footprint 从 4.47/6.32/7.79/9.10 mm 降到 2.74/3.86/4.73/5.45 mm
  （Δz = 0.125/0.25/0.375/0.5 mm）；
- 短 S：R15 下 θ 更大（dx = 8/16/24 → 42.8°/62.2°/78.5°），弧更短但转角更急，
  因此 A z1 的短 S 路由更多、更紧凑，也更容易与相邻路由产生交叉。

---

## 7. 统计与损耗口径

### 7.1 统计（全部从 R15 图元重算）

- 二维 A：总长 149 599.5 mm、弧 1 917（90° 645、短 S 1 272）、总弧长 31 913.4 mm；
- 二维 B：总长 88 847.4 mm、弧 1 141（全部 90°）、总弧长 26 884.2 mm；
- 五层 A：flat 159 878.2 mm + transition 316.1 mm = 160 194.2 mm，84 条 transition
  （42 条抬升路由 × 2），θ 总计 603.66°、footprint 总计 315.09 mm；
- 五层 B：flat 134 923.5 mm + transition 1 538.7 mm = 136 462.2 mm，416 条 transition
  （208 条抬升路由 × 2），θ 总计 2 938.74°、footprint 总计 1 534.23 mm；
- 弧半径分布：所有 2D/3D 弧均为 15.000000 mm（非 R15 弧 0 条）；
- 逐波导总长/总弯曲量见 `outputs/four_side_1024_v2_r15_v01/summary/r15_per_waveguide_2d.csv`
  与 `r15_per_waveguide_3d.csv`（每条连接一行，含失败记录与短 S/transition 标记）；
- 同层交叉：二维 A 136 182、B 54 184；五层 A 137 081（逐层见 §5.2）。

完整表格见 `outputs/four_side_1024_v2_r15_v01/summary/r15_statistics.md` 与
`r15_statistics.json`。

### 7.2 损耗参数分类（本轮不输出总损耗结论）

| 参数 | 值/状态 | 是否已标定 | 说明 |
|---|---|---|---|
| 传播损耗 | 0.05 dB/cm，`experimental_convention_not_measured` | 否（实验约定） | 仅用于历史沿用的长度估算口径，不是实测玻璃值 |
| 弯曲损耗 | `unknown_uncalibrated` | 否 | 无 R15 玻璃弯曲损耗函数；R = 15 mm 只是几何约束 |
| 交叉损耗 | `unknown_uncalibrated` | 否 | 单层交叉的光学可行性未确认；交叉数只是几何指标 |
| 层间/升降影响 | `unknown_uncalibrated` | 否 | 两段 3D 升降 S 曲线/层间传播的插损未标定 |

因此本轮**不给出总损耗数字**，只给出长度/弧/交叉/弯曲量等可复算几何量；
待马老师确认损耗模型后再补损耗预算。

---

## 8. 独立验收汇总

| 项目 | 验收器 | 半径 | 结果 |
|---|---|---|---|
| 2D A z1/z2 | `fslw.validate_fslw` policy=strict（显式 radius=15） | 15 mm | PASS（0 违规，all arcs R15） |
| 2D A combined 1024 | `fslw.validate_fslw`（两平面分别 strict） | 15 mm | PASS 943 |
| 2D B z1/z2 | 同上 | 15 mm | PASS（0 违规，all arcs R15） |
| 2D B combined 1024 | 同上 | 15 mm | PASS 515 |
| 5L 2.5D A | `fsd25d.validate25d`（R15 profile，MIN_CURVATURE 14.985） | 15 mm | PASS 985；min 3D 净空 0.080295；min 曲率 14.99999996；0 违规 |
| 5L 2.5D B | 同上 | 15 mm | PASS 723；min 3D 净空 0.080000（冻结容差内）；min 曲率 14.99999997；0 违规 |
| 独立 R15 复核 | `four_side_1024/r15/validate_r15.py`（primitive 级独立扫描 + 冻结验证器 + 3D 复核） | 15 mm | 2D A/B 与 25D A/B 共 8 项全部 PASS；10 046 条弧全部 R15（最大半径偏差 0.0 mm）；500 条 transition 全部 R15；0 违规 |

---

## 9. 限制与未决事项

1. 五层高度 `[0, 0.125, 0.25, 0.375, 0.5] mm` 仍是仿真假设，不是师兄确认的
   工艺参数；本轮结论只在该假设下成立。
2. 本轮只做“先 2D、再局部抬升”的单次抬升 2.5D，不做 Native 3D 联合寻路；
   5 层结果不代表联合 3D 优化能达到的上限。
3. 最小净空余量：A 的 3D 最小净空 0.080295 mm，仅比 0.08 mm 阈值高 0.0004 mm
   （来自已接受的 2D baseline 本身的最小间距）；B 的 2D z2 与 5L 最小净空
   = 0.0800000 mm，恰好落在 0.08 mm 边界（冻结 strict 口径按 `clearance − 1e-7`
   容差接受），工艺容差风险偏高，制造前必须复核；纯正交的 B z1 相对宽松
   （0.094654 mm）。
4. 损耗系数未标定，不输出总损耗；弯曲/交叉/层间影响待确认。
5. R15 是本文几何约束，不是制造能力声明；玻璃厚度、MPO 安装方向、真实折射率
   分布等仍未确认。
6. PDF 示例尺寸仅作形状参考；本轮没有照抄 PDF 的 R6000/R6137.33/1000 µm/50 µm
   参数，全部按 R15 重新推导（见 §2 与 `PDF_GEOMETRY.md`）。
7. 纯正交对侧小偏移（8/16/24 mm）的结构性短板只有改变连接模型（允许同侧 U 或
   非 90° 弧）或增加层数才可能根本解决；本轮不修改 V2 配对。

---

## 10. 复现与文件清单

### 10.1 复现命令（Windows PowerShell，项目根目录）

```powershell
$env:HTTP_PROXY='http://127.0.0.1:10808'; $env:HTTPS_PROXY='http://127.0.0.1:10808'  # 仅上传需要
.\.venv\Scripts\python.exe -m four_side_1024.r15.run2d_r15 --scheme A --plane z1 `
  --order ns_ew_xdesc --budget 1600 --rr-rounds 4 --transactions 24 --sizes 1,2,4 `
  --analysis-budget 1600 --reinsert-budget 1600 --rr-time-limit 1200 --workers 5
# A z2 顺序扫描（4 个顺序各自独立 root）
foreach ($order in 'round_robin_N_cw','group_swesnw','csv','global_congestion') {
  .\.venv\Scripts\python.exe -m four_side_1024.r15.run2d_r15 --scheme A --plane z2 `
    --order $order --budget 1600 --rr-rounds 0 `
    --root "outputs/four_side_1024_v2_r15_v01/sweep2d/A_z2_$order"
}
# 取最好顺序（round_robin_N_cw 437）继续 R&R
.\.venv\Scripts\python.exe -m four_side_1024.r15.run2d_r15 --scheme A --plane z2 `
  --continue-from outputs/four_side_1024_v2_r15_v01/sweep2d/A_z2_round_robin_N_cw/checkpoints/A_z2_round_robin_N_cw.json `
  --rr-rounds 4 --transactions 64 --sizes 1,2,4,8 --analysis-budget 800 `
  --reinsert-budget 800 --rr-time-limit 1800 --workers 8 `
  --targets-per-round 64 --analysis-targets 128
# B z1
.\.venv\Scripts\python.exe -m four_side_1024.r15.run2d_r15 --scheme B --plane z1 `
  --order ns_ew_xdesc --budget 400 --rr-rounds 4 --transactions 24 --sizes 1,2,4 `
  --analysis-budget 400 --reinsert-budget 400 --rr-time-limit 1200 --workers 5
# B z2 顺序扫描 + 最好顺序（round_robin_N_cw 331）继续 R&R（同 A z2 参数）
# 2D 组合与统计/验收
.\.venv\Scripts\python.exe -m four_side_1024.r15.run_r15_pipeline --step finalize2d --labels A
.\.venv\Scripts\python.exe -m four_side_1024.r15.run_r15_pipeline --step finalize2d --labels B
.\.venv\Scripts\python.exe -m four_side_1024.r15.validate_r15 --only 2d
# 五层 2.5D（A/B 各一次，使用本轮 R15 二维布局作 baseline）
.\.venv\Scripts\python.exe -m four_side_1024.r15.run25d_r15 --scheme A --layers 5 `
  --budget 400 --passes 3 --flat-probe 12 --rr-rounds 2
.\.venv\Scripts\python.exe -m four_side_1024.r15.run25d_r15 --scheme B --layers 5 `
  --budget 400 --passes 3 --flat-probe 12 --rr-rounds 2
# 五层独立验收 + 统计 + 图件
.\.venv\Scripts\python.exe -m four_side_1024.r15.validate_r15 --only 25d
.\.venv\Scripts\python.exe -m four_side_1024.r15.stats_r15
.\.venv\Scripts\python.exe -m four_side_1024.r15.plots_r15
```

说明：`profile_r15.apply()` 由各 runner 自动执行，并在父进程设置
`FSLW_PROCESS_RADIUS_MM=15`，使 multiprocessing 子进程与父进程一致（见 §3.2）。
R40 历史轮不设该变量，默认仍为 40，历史数据不受影响。

### 10.2 输出目录

```
outputs/four_side_1024_v2_r15_v01/
├─ planes/V2/A/{z1,z2}/        # R15 二维 D56 平面产物（routes/config/audit/statistics/失败记录/run.log）
├─ planes/V2/B/{z1,z2}/        # R15 二维纯正交 90° 平面产物
├─ combined/V2/{A,B}/          # 1024 组合布局（routes_1024.json + 组合图/GDS）
├─ checkpoints/                # R15 候选真实几何 checkpoint（非 R40 缓存）
├─ sweep2d/                    # 顺序策略对照（各自独立 root）
├─ 25d/scheme{A,B}/layers5/    # R15 五层 2.5D 布局与统计
├─ 25d/validation/             # 五层独立 3D 验收结果
├─ validation/                 # R15 独立复核（2D 平面/组合、25D、汇总）
├─ summary/                    # 统计表、逐波导 CSV、损耗参数分类、R40 vs R15 对照
├─ comparison/                 # 新旧（R40 vs R15）对照图（plots_r15）
├─ figures/                    # R15 几何类型图与 5 层 3D 图
├─ work/                       # 运行日志、事故隔离证据（r40 worker contamination）
├─ final_validation.json       # 2D 组合独立验收汇总（v2opt.finalize，R15 适配）
└─ REPRODUCE_R15.md / report_four_side_1024_v2_r15_v01.md
```

### 10.3 数据来源与不可混用声明

- R40：`outputs/four_side_1024_v2_candidate_rr_v01/`、`outputs/four_side_1024_v2_ortho90_v01/`、
  `outputs/four_side_1024_v2_25d_v01/`；
- R15：本文件所在根 `outputs/four_side_1024_v2_r15_v01/`；
- 两轮数据不共享候选缓存/最优布局/验证参数；本报告 R40 列只用于对照表的历史布通数，
  R15 的长度/弧/交叉全部由 R15 图元重算。

---

## 11. 与师兄 PDF 的对应关系总结

- **形状层面**：90° 四分之一弧、平面反向双弧 S、同侧 180° U、层间升降 S 四种
  基本形状与 PDF 的总版图/第一层/第二层/两层互连一一对应；四边端口 bank →
  直段 → 弯 → 板中布线区 → 对侧/同侧连接的版图组织方式与本轮 V2 拓扑一致。
- **数值层面**：PDF 的 R6000 µm、R6137.33 µm、2R=7746 µm、1000 µm/50 µm 升降对
  均不采用；本轮一律 R = 15 mm 并重新推导所有派生的 θ、footprint、弧长、
  最小间距（同侧 U 30 mm、升降 footprint 表 2、短 S θ = acos(1 − dx/(2R))）。
- **未使用 PDF 的部分**：127 µm 间距（用 IEC 2×16 MPO 的 250 µm 列距）、
  8000 µm 直段、2000 µm 横向偏移（R15 下不可行）等示意性尺寸，均按本项目
  真实板/端口模型重新求解。

---

## 12. 本轮新增/修改代码

新增（`four_side_1024/r15/`）：

- `profile_r15.py` — R15 进程配置（环境变量、import 顺序、模块常量回填）；
- `worker_boot.py` — multiprocessing worker 半径自检；
- `run2d_r15.py` — R15 二维 runner（顺序扫描、R&R、从 checkpoint 继续）；
- `run25d_r15.py` — R15 五层 runner（R15 二维布局作 baseline）；
- `run_r15_pipeline.py` — finalize / 25d / validate / stats / plots 编排；
- `u_geometry.py` + `tests_r15/test_u_geometry.py` — 同侧 U 几何模块与 27 个测试；
- `PDF_GEOMETRY.md`、`RADIUS_AUDIT.md`、`README_R15.md`；
- `validate_r15.py`（独立 R15 验收封装）、`stats_r15.py`（统计）、`plots_r15.py`（图件）。

兼容性修改（不改变 R40 默认行为）：

- `fslw/config.py`：支持 `FSLW_PROCESS_RADIUS_MM` 环境变量（缺省 40），
  `FIXED_RADIUS_40MM` 与 process 记录动态化；
- `v2opt/rr.py` / `v2opt/search.py`：任务载荷携带 process 半径，worker 入口自检；
- `v2opt/finalize.py`：R15 下传入 `build_report(radius=...)`、半径检查动态化、
  禁止在非 R40 轮从冻结 R40 BASE 物化缺失平面；
- `v2opt/ortho90_validate.py`、`v2opt/plots_geomtype.py`、`v2opt/plots_ortho90.py`、
  `fsd25d/plots25d.py`：半径标签/规则文本动态化。

历史 R40 代码与输出目录均未删除或覆盖。
