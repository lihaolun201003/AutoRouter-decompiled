# R9 修正 L1–L5 五层模型产物说明（2026-10-20）

本目录是**修正物理模型后的探索性**五层实验输出，对应
`docs/reports/four_side_1024_v2_l1l5_v01.md` 与 `four_side_1024/l3d/`。

## 1. 模型（本轮最重要修正）

- **L1 是接口所在逻辑布线层，同时包含两排 2×16 MPO 端口**：
  z1 排真实物理高度 **0.0 mm**、z2 排真实物理高度 **0.5 mm**（真实 0.5 mm 高差，
  不是两个逻辑层）；每排 16 端口、同排列距 0.25 mm。
- **L2–L5 是四个额外布线层**，物理高度**尚未被师兄确认**；本轮作为可配置仿真参数
  (`provenance = unconfirmed_simulation`) 探索三种层栈：
  medium 1.0/1.5/2.0/2.5 mm、compact 0.75/1.0/1.25/1.5 mm、wide 1.5/2.5/3.5/4.5 mm。
- 端口逻辑层、端口物理高度、波导当前物理高度、当前逻辑层四者解耦；允许任意层序与
  多次平滑升降，最后回到 L1 真实行高；L1 两排之间、不同物理 z 的所有部件对均按真实
  XYZ 净空 ≥0.08 mm 检查（无跨 z 交叉豁免），`layer_id` 不当作 z 坐标。
- R15 工艺继续生效（平面/3D 弯曲 R=15 mm、宽 0.05、边缘间隙 0.03、净空 0.08、
  板 150×150、strict 交叉）；1024 连接、端口坐标/切向、CSV 与 SHA256 未改。

## 2. 结果（探索性）

| 方案 | 修正 L1 基线（flat） | 主探索 medium_050 | compact_025 | wide_100 | 旧错误模型（不可比） |
|---|---:|---:|---:|---:|---:|
| A（D56 + Short-S） | 943 | **963**（+20） | 962（+19） | 963（+20） | 985 |
| B（纯正交 90°） | 515 | **621**（+106） | 611（+96） | 611（+96） | 723 |

- A/B 主探索分别有 24/31 条 ≥3-transition 多次换层路线（含 L1→L2→L3→L5→L1 等）；
- 8 项独立三维验收（2 基线 + 6 最终布局）全部 `exploratory_only` PASS、0 违规；
  min 曲率 14.999999961 mm、min 真实 3D 净空 0.080000 mm（≥0.08）、
  min transition-vs-flat 0.091540 mm、min transition-vs-transition 0.081738 mm；
- **没有任何正式工艺验收**：L2–L5 高度未确认 → `formal_acceptance=false`、
  `status=exploratory_only`；正式验收必须等真实层高确认后重做。
- 旧 z1=L1/z2=L5 模型下的 R15 985/723、R40 820/383、A3/B3 788/342 全部不可继承，
  仅作历史记录；R15 二维 A 943/B 515 作为修正 L1 flat 基线已重新验收。

## 3. 上传内容（完整探索性输出）

- `baseline/scheme{A,B}/`：修正 L1 基线 `routes_l3d.json` + `run_summary.json` + 独立验收；
- `layer_stacks/`：三种探索性层栈 JSON（含 provenance）；
- `l3d/scheme{A,B}/layers5_<stack>/`：`routes_l3d.json`（最终，含阶段 4 本地重分层）、
  `routes_l3d_router.json`（阶段 4 前路由器输出，中间证据）、`run_summary.json`、
  `run.log`、`postpass_summary.json`、`validation/routes_l3d.validation.json`；
- `demo_multi/`：仅多次换层序列的演示尝试（0 条布通，记录候选/直段几何限制）；
- `figures/`：L1 双排接口 3D 局部图、五层真实物理高度示意图（逻辑层号 vs 物理 z 双轴）、
  逐层布线图 L1–L5、完整 1024 通道 3D 布局与按高度着色图、真实多次换层示例与 XZ 侧视；
- `comparison/`：旧错误模型 vs 修正模型、A/B 对比、plots manifest；
- `summary/`：统计表（含物理平面 vs 逻辑层、层序/transition 直方图、逐 route CSV）、
  R15 2D 与历史旧 5L 对照（明确标注旧值不可比）、损耗参数分类；
- `validation/`：独立三维验收汇总（JSON/MD，含 10 项检查与聚合）；
- `report_four_side_1024_v2_l1l5_v01.md`、`REPRODUCE_L3D.md`。

## 4. 边界/诚信

- L2–L5 高度是**探索性仿真参数**，不是师兄确认的工艺值；不做正式五层工艺结论。
- 未模拟 L2–L5 位于接口下方的布置；未做 Native 3D 联合寻路；阶段 4 只对已成功路线
  做局部重分层，未把腾出的 L1 空间用于联合救回失败路线（bounded R&R 仅 1 轮）。
- 损耗系数未标定（传播 0.05 dB/cm 仅为实验约定；弯曲/交叉/层间 unknown_uncalibrated），
  不输出总损耗结论；不宣称可制造。
- 修正模型 B 的最小 2D/3D 净空为 0.08 mm 边界（冻结 strict 容差内），制造前需复核。

## 5. 复现

`REPRODUCE_L3D.md` 给出修正 L1 基线、三层层栈的阶段 2–4 运行、阶段 4 重分层、
独立验收、统计与图件的完整命令；代码在 `OpticalWaveguideRouter2D/four_side_1024/l3d/`。
