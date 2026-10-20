# 修正后的 L1–L5 五层光波导布线实验报告（2026-10-20 R9）

- 项目：`OpticalWaveguideRouter2D`
- 本轮主题：**先纠正物理模型，再重新开展 1024 通道实验**
- 输出目录：`outputs/four_side_1024_v2_l1l5_v01/`（R15/R40 历史目录全部保留、未覆盖、未混用）
- 关键前置：R15 工艺要求继续生效（所有平面弯曲与三维升降曲线 R = 15 mm；板 150×150 mm、
  宽 0.05 mm、边缘间隙 0.03 mm、中心线净空 0.08 mm、strict 交叉例外不变）；V2 的 1024 条连接、
  端口数量/坐标/切向、连接 CSV 与 SHA256 全部不变
- 配套文档：
  - `four_side_1024/l3d/SCHEMA_L3D.md`（修正后的数据模型与 JSON schema）
  - `four_side_1024/l3d/AUDIT_OLD_25D.md`（旧模型错误假设逐条审计，含 file:line 与数据证据）
  - `four_side_1024/l3d/OLD_MODEL_FIELDS.json`（机器可读证据）
  - `four_side_1024/l3d/PDF_GEOMETRY.md`（PDF 形状对照，R6 不覆盖 R15）
  - `outputs/four_side_1024_v2_l1l5_v01/REPRODUCE_L3D.md`（全部复现命令）

---

## 0. 一句话结论

旧五层模型把 z2 接口排当成 L5、把 0.5 mm 两排高差当成整个五层高度域，
因此旧的 R15 五层 A=985 / B=723 **不是本模型的结果，不能继承**。
修正模型（L1 同时包含 z=0 与 z=0.5 两排接口，L2–L5 为未确认高度的额外布线层）
在相同的 R15/0.08 mm/strict 约束下得到：
修正 L1 基线 **A 943、B 515**；单次/多次升降与局部重分层后
**A 963（+20；旧错误模型 985，差 −22）、B 621（+106；旧错误模型 723，差 −102）**。
由于 L2–L5 高度尚未被师兄确认，**本轮所有五层结果都是探索性几何结果，
独立验收器明确拒绝正式工艺验收（formal_acceptance=false）**。

---

## 1. 旧五层模型的错误假设与影响

逐条审计见 `four_side_1024/l3d/AUDIT_OLD_25D.md`（12 条错误假设，file:line 引用，
所有旧产物 SHA256 现场复验未变）。最重要的错误：

| # | 旧假设 | 位置（节选） | 后果 |
|---|---|---|---|
| 1 | z2 端口 = 第 4 号层（L5）接口层 | `fsd25d/config25d.py` `INTERFACE_LAYER={3:{...},5:{z1:0,z2:4}}`；`router25d.py` `base_layer=interface[plane]` | 旧五层把 z2 排画在最高层；新模型 z2 属于 L1（z=0.5） |
| 2 | 五层高度域 = `[0,0.125,0.25,0.375,0.5]` | `config25d.py: LAYER_STACKS[5]` | 把 2×16 接口两排的 0.5 mm 高差当成整个堆栈高度；真实 L2–L5 高度未确认 |
| 3 | 逻辑层号 ≡ 物理高度 | `world25d.LayerWorld` 按 layer index 建 2D 世界；`validate25d.py` 按层号分组 | 无法表示 L1 两排不同物理高度；新模型 layer_id 与 z 彻底解耦 |
| 4 | 不同层 flat–flat 不做真实 3D 检查（"safe by construction"） | `world25d.py`、`validate25d.py` | 新模型要求所有不同物理 z 对（含 L1 两排）真实 3D ≥0.08 mm |
| 5 | 只允许恰好 2 次 transition + 单一 travel layer | `path3d.build_route3d`；`router25d.attempt_route`；`validate25d` 结构检查 | 新模型允许多次换层/任意层序（L1→L2→L3→L1 等） |
| 6 | 无“未确认高度 → 拒绝正式验收”概念 | `validate25d.py` 全文 | 新模型独立验收器强制 formal_acceptance=false，仅报 exploratory |

**旧 985/723 的构成与不可继承性**：
旧 A5 985 = 943（R15 二维 A 的两排 flat 原样复用）+ 42 lifted；旧 B5 723 = 515 + 208 lifted。
这些 lifted 路线使用的中间高度 0.125/0.25/0.375 mm、旧 layer id 0..4、
旧 `interface_layer={z1:0,z2:4}` 在新模型中都不存在；旧验证器也无法解析新 L3D JSON
（`layer` vs `layer_id`、`z0_mm` vs `z0`、`interface_layer=4` vs 1、缺 `layer_sequence` 等）。
R40 的 820/383（及 3 层 788/342）同样是错误模型的数字，只能作历史对照。

---

## 2. 修正后的端口 / 物理高度 / 逻辑层数据模型

（完整定义见 `four_side_1024/l3d/SCHEMA_L3D.md`）

1. **L1 = 接口所在逻辑布线层**，同时包含两排 2×16 MPO 端口：
   z1 排物理高度 **0.0 mm**，z2 排物理高度 **0.5 mm**（真实高度差 0.5 mm，不是两个逻辑层）；
   每排 16 端口、同排列距 0.25 mm。
2. **L2–L5 = 四个额外布线层**，物理高度未确认，作为可配置仿真参数；
   L2–L5 高度必须互不相同、严格有序、与两排接口高度及彼此间距均 > 0.08 mm，
   否则模型直接拒绝。
3. 四个概念彻底解耦：端口所属逻辑层（恒为 L1）、端口真实物理高度（0/0.5）、
   波导当前物理高度（flat 的 z_mm / transition 的 z0,z1）、波导当前逻辑层（layer_id）。
4. 每条路线从 L1 的真实端口高度出发，可访问任意层序列（多次换层、非相邻层直连），
   最后必须回到 L1 并精确连接目标端口的真实物理高度；不允许改变接口排。
5. 路径表示：`parts = [flat(z, layer_id), transition(from_layer,to_layer,z0,z1,R,θ,footprint), ...]`；
   每条 transition 都是垂直面内两段 R=15 mm 圆弧的 S 曲线
   （θ=acos(1−|Δz|/(2R))，footprint=2R sinθ，弧长=2Rθ，G1 切向连续）。
6. 碰撞语义：同一物理 z 平面用冻结 strict 2D 规则（含合法交叉窗口）；
   不同物理 z 的所有部件对（包括 L1 两排之间、L1 vs L2–L5、任何 transition 对
   flat/transition）用真实 XYZ 最小距离 ≥0.08 mm，不适用交叉豁免；
   `layer_id` 相同不代表 z 相同，`layer_id` 不同也不代表必然不碰撞。

本轮新增的三维冒烟/回归测试（`four_side_1024/l3d/tests_l3d/`）覆盖：
L1 双排端口高度、同列两排端口 0.5 mm 真实距离、任意层序/多次 transition、
无效/未定义层高拒绝、同层不同高、曲率违规、self-clearance 等。

---

## 3. L2–L5 层高参数配置及假设依据

**师兄只确认了“五层组织方式”，未提供 L2–L5 的具体物理高度。**
因此本轮不把任何自选高度写成工艺参数，而是建立显式可配置层栈并做参数化探索：

| 层栈 | L1 接口排 | L2 | L3 | L4 | L5 | 依据/说明 |
|---|---|---:|---:|---:|---:|---|
| `medium_050`（主探索） | z1=0.0 / z2=0.5 | 1.0 | 1.5 | 2.0 | 2.5 | 以 0.5 mm 等间距布置在接口上方，作为首选探索参数 |
| `compact_025`（敏感性） | 同上 | 0.75 | 1.0 | 1.25 | 1.5 | 0.25 mm 间距（略大于 0.08 mm 净空的最小可行紧凑布置） |
| `wide_100`（敏感性） | 同上 | 1.5 | 2.5 | 3.5 | 4.5 | 1.0 mm 间距，检验层距对布通率的敏感性 |

- 所有层栈的 `provenance = 'unconfirmed_simulation'`；不是师兄确认值，也不是制造参数。
- 所有额外层假设位于接口上方（两排 z=0/0.5 之上）；下方布置在物理上也可能，
  但本轮未做设备厚度/折射率分布确认，未模拟。
- 层栈参数写在 `outputs/four_side_1024_v2_l1l5_v01/layer_stacks/<name>.json`，
  每条 route JSON 内嵌 `layer_stack` 记录，可逐条追溯。
- 敏感性结果见 §6：三种层距对 A/B 布通数影响很小（A 962–963、B 611–621），
  说明本轮 3D 提升的瓶颈主要不是层间距，而是“失败路线的 XY 候选/可用直段数量 +
  跨越另一排接口高度时的真实 3D 净空”。

---

## 4. 修正后的布线代码与回归测试

新增包 `four_side_1024/l3d/`（仅新增，不改动旧 `fsd25d`/`r15` 历史代码与数据）：

| 文件 | 作用 |
|---|---|
| `SCHEMA_L3D.md` | 修正后的层/端口/路线/碰撞数据契约 |
| `layers.py` | `LayerGeometry` / `LayerStack` 数据模型与严格校验（双排 L1、L2–L5 高度、间距、可达性、provenance） |
| `paths.py` | 多过渡路径装配：任意层序的 S 曲线放置、仅直段、margins、footprint 完整落在直线段、G1 连续；`build_route_l3d` |
| `world.py` | 真实 XYZ 世界：按物理 z 分组的 strict 2D 世界 + 3D 净空世界（transition vs flat/transition、self-clearance；按物理 z 而非 layer id） |
| `router.py` | 阶段 2/3 路由器：单次升降（比较全部 L2–L5 层选择）、多次换层序列、bounded R&R、失败原因统计 |
| `postpass.py` | 阶段 4：对已成功路线做局部重新分层（L1→L2→L3→L1 / L1→L2→L3→L5→L1 等），routed 数不降 |
| `run_l3d.py` / `baseline.py` | 命令行 runner 与修正 L1 基线 |
| `validate_l3d.py` | 独立 3D 验收器（不 import router/paths/world），从 JSON 参数重建空间曲线 |
| `plots_l3d.py` / `stats_l3d.py` | 可视化与统计 |
| `AUDIT_OLD_25D.md` / `OLD_MODEL_FIELDS.json` | 旧模型错误审计证据 |

回归测试：`python -m pytest four_side_1024/l3d/tests_l3d -q` → **56 passed**
（路径装配 41 + 独立验收 17；两套测试按目录分进程运行，避免 R15/R40 profile 互相污染）。
历史 R15/R40 的测试与数据未受影响。

---

## 5. 阶段 1：修正后的 L1 基线（旧 R15 二维布局的统一 3D 复核）

将已验收的 R15 二维布局按新模型放回同一个真实 XYZ 世界：
z1 平面 498 条路线 = L1 且在 z=0.0；z2 平面 445 条路线 = L1 且在 z=0.5；
两排属于同一逻辑层 L1，但物理平面不同，XY 投影交叉不是冲突（真实间距 0.5 mm）。

| 方案 | z1 排（z=0.0） | z2 排（z=0.5） | L1 基线合计 | 独立验收 |
|---|---:|---:|---:|---|
| A（D56 + Short-S） | 498 | 445 | **943/1024** | exploratory_only PASS（0 违规；min 曲率 14.999999961 mm；min 3D 净空 0.080295 mm） |
| B（纯正交 90°） | 184 | 331 | **515/1024** | exploratory_only PASS（0 违规；min 曲率 14.999999966 mm；min 3D 净空 0.08 mm） |

这就是新模型下的正确基线；旧五层 lifted 结果一条都没有继承。

---

## 6. 阶段 2–4：修正模型的 A/B 布线结果

统一参数：R = 15 mm、净空 0.08 mm、strict 交叉、候选预算 120/路线、multi 候选 60、
passes 3（敏感性 2）、R&R 1 轮（主探索）、随后对已成功路线做最多 24 条局部重新分层
（阶段 4）；A/B 使用完全相同的层栈、约束、预算与独立验收规则。

| 层栈 | 方案 | L1 基线 | 修正后布通 | 新增 | 抬升路线 | 多次换层路线(≥3 transitions) | 总 transitions | 独立验收 |
|---|---|---:|---:|---:|---:|---:|---:|---|
| medium_050（主） | A | 943 | **963** | +20 | 44 | 24 | 117 | exploratory_only PASS |
| medium_050（主） | B | 515 | **621** | +106 | 130 | 31（含 7 条 4 次 transition） | 298 | exploratory_only PASS |
| compact_025 | A | 943 | 962 | +19 | 43 | 24 | 115 | exploratory_only PASS |
| compact_025 | B | 515 | 611 | +96 | 120 | 24 | 268 | exploratory_only PASS |
| wide_100 | A | 943 | 963 | +20 | 44 | 24 | 117 | exploratory_only PASS |
| wide_100 | B | 515 | 611 | +96 | 120 | 24 | 265 | exploratory_only PASS |

说明：
- “新增”为相对 L1 基线；“多次换层路线”指 `n_transitions >= 3` 的真实跨多层路线
  （如 L1→L2→L3→L1、L1→L2→L3→L5→L1、L1→L5→L3→L2→L1 等），
  由阶段 4 的局部重新分层产生且保持 routed 数不变；
- A/Primary 的各逻辑层使用路线数（同一条路线可访问多层）：L1 963、L2 37、L3 24、L4 4、L5 8；
  transition 层对：L1→Lk 44 条、中间层 29 条；B/Primary：L1 621、L2 57、L3 39、L4 41、L5 31，
  transition 层对：L1↔Lk 260 条、中间层 38 条；
- B 的新增 106 条中：99 条为单次升降、7 条由阶段 3 的多次换层直接布通
  （z1 行共 +27、z2 行共 +79）；另有 24 条阶段 4 本地重分层路线只改变层序、
  routed 数不变；B medium 的 ≥3-transition 路线合计 31 条（24 条重分层 + 7 条新增）。
- A 的 24 条多次换层路线均来自阶段 4 本地重分层（阶段 3 未额外布通）。

**三种层栈的敏感性**：A 962–963（±1），B 611–621（主探索 621）。
在本轮失败池中，层高间距不是主要瓶颈；这进一步说明“把高度调近一点”不能恢复旧模型的
高提升率——旧模型的高提升来自错误地把额外层放进 0–0.5 mm 的接口行距内部，
其 transition 极短且从不跨越另一排接口高度。

---

## 7. 独立三维验收

独立验收器 `four_side_1024/l3d/validate_l3d.py` 不 import 路由器；它从 JSON 参数
重建 flat 图元与 S 曲线（θ/footprint/弧长重算），按真实弧长 ≤0.02 mm 采样完整 3D 路径，
按物理 z（绝不用 layer_id 当 z）分组做同层 strict 2D 审计或真实 3D 净空检查。

| 项目 | routed | 抬升 | 多次换层 | 最小曲率 | 最小 3D 净空 | 同层交叉 | 违规 | 状态 |
|---|---:|---:|---:|---:|---:|---|---:|---|
| baseline A | 943 | 0 | 0 | 14.999999961 | 0.080295032 | L1@0.0: 69072；L1@0.5: 67110 | 0 | exploratory_only PASS |
| baseline B | 515 | 0 | 0 | 14.999999966 | 0.08 | L1@0.0: 13342；L1@0.5: 40842 | 0 | exploratory_only PASS |
| A medium final | 963 | 44 | 24 | 14.999999961 | 0.080295032 | L1@0.0: 69072（非交叉最小 0.080295032）；L1@0.5: 62111（0.083271974）；L2@1.0: 221；L3@1.5: 56；L4@2.0: 0；L5@2.5: 6 | 0 | exploratory_only PASS |
| A compact final | 962 | 43 | 24 | 14.999999961 | 0.080295032 | L1@0.0: 69072；L1@0.5: 61494；L2@0.75: 230；L3@1.0: 83；L4@1.25: 0；L5@1.5: 6 | 0 | exploratory_only PASS |
| A wide final | 963 | 44 | 24 | 14.999999961 | 0.080295032 | L1@0.0: 69072；L1@0.5: 63267；L2@1.5: 120；L3@2.5: 82；L4@3.5: 4；L5@4.5: 2 | 0 | exploratory_only PASS |
| B compact final | 611 | 120 | 24 | 14.999999961 | 0.08 | L1@0.0: 13350（0.094654426）；L1@0.5: 38207（0.08）；L2@0.75: 1996；L3@1.0: 206；L4@1.25: 212；L5@1.5: 166 | 0 | exploratory_only PASS |
| B wide final | 611 | 120 | 24 | 14.999999961 | 0.08 | L1@0.0: 13402；L1@0.5: 38324；L2@1.5: 342；L3@2.5: 1579；L4@3.5: 210；L5@4.5: 52 | 0 | exploratory_only PASS |
| B medium final | 621 | 130 | 31（含 7 条 4 次 transition） | 14.999999961 | 0.08 | L1 z1@0.0: 13864；L1 z2@0.5: 39988；L2@1.0: 518；L3@1.5: 296；L4@2.0: 811；L5@2.5: 354 | 0 | exploratory_only PASS |

独立验收器确认的 10 项要求：
1. L1 为接口层，两排端口真实高度 0.0/0.5 mm；
2. 同列两排端口即使 XY 相同，真实 3D 距离恰为 0.5 mm（1024 对全部检查）；
3. 所有路线起终点是正确 L1 端口与行高（端口/CSV 身份核对，0 错误）；
4. L1→L2/L3/L4/L5 过渡合法（R=15、θ/footprint/弧长重建比对、端点与切向连续）；
5. 中间层过渡与多次过渡合法（含 fixture 中 L1→L2→L3→L1 staggered 与 back-to-back，
   以及本轮 final 数据中的 3–4 次 transition 路线）；
6. 完整路径 3D 曲率 ≥14.985 mm（逐点重建采样），平面弧半径严格 15、直线轴对齐；
7. transition 与 L1 两排 flat 的真实 3D 净空 ≥0.08 mm（无跨 z 交叉豁免）；
8. 同逻辑层不同物理高度（L1 两排）按不同物理平面处理；
9. `layer_id` 从不当作 z 使用；无效/未定义层高直接拒绝；
10. L2–L5 高度未确认 → `formal_acceptance=false`、`status=exploratory_only`，
    不给 `--allow-exploratory` 时 exit 3（拒绝正式验收）。

**验收汇总**（2 个修正 L1 基线 + 6 个 scheme/stack 最终布局，全部 8 项
`exploratory_pass=true`、0 违规）见
`outputs/four_side_1024_v2_l1l5_v01/validation/l3d_validation_summary.{json,md}`；
每个条目的完整报告位于其 run 目录的 `validation/routes_l3d.validation.json`。
本轮**没有任何正式工艺验收（formal_acceptance）被授予**。

8 个条目合计：routed **6 189**、failed 2 003、lifted 501、transitions **1 180**；
其中 ≥3-transition 路线 **151 条**（144 条由阶段 4 重分层 + 7 条 B/medium 阶段 3 直接布通），
≥3-layer 路线 151 条；全部 8 个条目最小曲率 **14.999999961 mm**（≥14.985）、
最小 3D 净空 **0.080000 mm**（≥0.08）、最小 transition-vs-flat **0.091540 mm**、
最小 transition-vs-transition **0.081738 mm**；同层交叉合计 749 141（全部为合法
strict-2D 交叉窗口内的交叉，0 违规）。所有 8 个条目的 8 类 violation 计数均为 0。

---

## 8. 与旧 985/723 的差异和原因

| 方案 | 旧（错误模型） | 新（修正模型，主探索 medium_050） | 差 |
|---|---:|---:|---:|
| A（D56 + Short-S） | 985 | **963** | −22 |
| B（纯正交 90°） | 723 | **621** | −102 |
| R15 二维基线 | 943 / 515 | 943 / 515（同，L1 flat 重新验收） | 0 |

差异原因：
1. 旧模型的中间层位于 0–0.5 mm 行距内部，transition 极短（z1 行到 0.125 mm：
   footprint≈2.74 mm；到 0.25 mm：≈3.86 mm），且 z1 行的升降从不跨越 z2 行所在高度；
   因此几乎任意失败路线都能找到一段直段塞入两次短升降。旧 985/723 的高提升率
   本质来自这个不存在的“层间高度域”。
2. 修正模型中 L2–L5 位于接口上方（主探索 1.0/1.5/2.0/2.5 mm），
   transition footprint 7.7–11.9 mm；z1 行的升降必须穿过 z2 行所在的 z=0.5 mm 平面，
   在真实 3D 中与 z2 行路线保持 0.08 mm 净空，约束显著更强。
3. 失败池结构：修正模型 A 可尝试 79 条（2 条无候选），B 可尝试 431 条（78 条无 2D 候选）；
   旧模型 B 可尝试 431 条但 travel 层在接口行距内，放置容易。
4. 修正模型的 3D 结果仍然明显高于二维基线（A 943→963、B 515→621），
   说明五层额外布线层确实能救回一部分被 L1 平面冲突堵死的连接；但提升幅度
   远小于旧错误模型，且随层高参数变化很小。
5. 旧 985/723 以及 R40 820/383 只作为历史记录保留，不再作为可比工艺结果。

---

## 9. 可视化

`outputs/four_side_1024_v2_l1l5_v01/`：
- `figures/l1_interface_two_rows_zoom.png`：L1 双排接口 3D 局部放大（z1 排 0.0 mm、
  z2 排 0.5 mm，同为 L1，0.25 mm 列距/0.5 mm 行距；明确标注 L5 不是接口层）；
- `figures/layer_stack_physical_heights.png`：五层真实物理高度示意（左逻辑层号/右物理 z，
  标注 L2–L5 为探索性未确认高度、正式验收被拒绝）；
- `figures/layer_L1_routing.png` … `layer_L5.png`：逐层布线图（L1 按两排着色；
  L2–L5 显示真实使用到的层与物理高度）；
- `figures/full_1024_layout_3d.png` 与 `full_1024_layout_height_colored.png`：
  完整 1024 通道 3D 布局与按物理高度着色版；
- `figures/example_multilayer_route.png` + `_xz.png`：真实多次换层示例
  （从 final 数据中取 transition 最多的路线，如 L1→L2→L3→L5→L1，标注层序与升降点）；
- `figures/per_layer_counts_and_transitions.png`：每层承载路线数、transition 数直方图、
  层序直方图；
- `comparison/old25d_vs_new_l3d.png`、`a_vs_b_l3d.png`：旧错误模型 vs 修正模型、
  A/B 对比（明确标注旧值不可比）；
- `comparison/plots_manifest.json`：图件清单、数据来源、层栈、半径审计与 caveats。

---

## 10. 输出目录、复现与数据来源

```
outputs/four_side_1024_v2_l1l5_v01/
├─ baseline/scheme{A,B}/                    # 修正 L1 基线（routes_l3d.json + validation）
├─ layer_stacks/{medium_050,compact_025,wide_100}.json   # 探索性层高配置（unconfirmed）
├─ l3d/scheme{A,B}/layers5_<stack>/         # 路由器输出 + routes_l3d.json（含阶段4重分层）
│   ├─ routes_l3d.json                      # 最终交付（relayer 后）
│   ├─ routes_l3d_router.json               # 阶段4前路由器输出（中间证据）
│   ├─ run_summary.json / run.log / postpass_summary.json
│   └─ validation/routes_l3d.validation.json
├─ demo_multi/schemeB/layers5_medium_050/   # 多次换层演示尝试（0 条：候选/直段几何不足，见报告）
├─ figures/ 、 comparison/                  # 可视化
├─ summary/                                 # stats_l3d 统计表
└─ REPRODUCE_L3D.md
```

复现命令见 `REPRODUCE_L3D.md`；所有运行由固定 R15 profile、固定层栈 JSON、
固定 budget/seed（20261019）与固定验收规则驱动。

---

## 11. 限制与未决

1. **L2–L5 的物理高度仍是未确认的仿真参数**；本轮所有五层结果标记为 exploratory，
   不是正式工艺验证，不能作为师兄确认的五层工艺结论。
2. 未探索“L2–L5 位于接口下方/玻璃厚度方向另一侧”的布置；真实玻璃厚度与层间
   折射率/耦合机制未确认。
3. 本模型只做几何布线；损耗系数未标定（传播 0.05 dB/cm 仅为实验约定；
   弯曲/交叉/层间 unknown_uncalibrated），不输出总损耗结论。
4. 阶段 4 的局部重分层只对已成功路线的层序做替换，未做“用重分层腾出的 L1 空间
   再去救回失败路线”的完整联合 R&R；路由器中的 bounded R&R 只使用了 1 轮。
5. 多次换层路线：A 主探索为 24 条（全部由阶段 4 本地重分层产生，routed 数不变）；
   B 主探索为 31 条（24 条重分层 + 7 条由阶段 3 多次换层直接新增布通）。
   直接用多次换层提高布通数的空间存在但较小；更大收益需要更大的候选预算/
   更宽松失败池，或联合优化层序与 XY 路径（本轮未做 Native 3D 联合寻路）。
6. 敏感性层栈只跑了阶段 2（单次升降）baseline；主探索 medium_050 走了完整阶段 2–4。
7. 修正模型 A 的最小 3D 净空 0.080295 mm、B 为 0.08 mm 边界（冻结 strict 的
   clearance−1e-7 容差内），制造前需按真实工艺容差复核。
8. 接口位置、端口坐标/切向、CSV 与 SHA256 全程未改；旧 R15/R40 输出目录只读保留。

---

## 12. 结论

1. 旧五层模型的 z1=L1 / z2=L5 与 0–0.5 mm 高度域假设被完整审计并纠正；
   旧的 985/723 及 R40 五层数字不再作为可比结果。
2. 修正模型把 L1 定义成含两排真实物理高度（0.0/0.5 mm）的接口层，L2–L5 作为
   未确认高度的额外布线层；逻辑层、端口高度、当前物理高度、当前逻辑层四者解耦，
   支持任意层序、多次平滑过渡与真实 XYZ 碰撞判断。
3. 用旧 R15 二维布局作为 L1 基线（A 943、B 515）在统一 3D 环境复核通过；
   修正模型的五层探索结果为主探索 A **963**、B **621**
   （敏感性层栈 A 962–963、B 611），全部通过独立探索性 3D 验收（0 违规）。
4. 修正后的提升幅度显著低于旧错误模型，原因已定位为旧模型把额外层压入接口行距内
   导致 transition 极短且不跨越另一排接口高度；这是物理模型错误，不是算法差异。
5. L2–L5 高度确认前，正式五层工艺验收保持拒绝；下一步应先在真实玻璃厚度/层间
   耦合条件下确认 L2–L5 高度，再进行正式五层实验。
