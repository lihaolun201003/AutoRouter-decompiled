# R15 轮产物说明（2026-10-20，全部弯曲 R = 15 mm）

本目录对应 `docs/reports/four_side_1024_v2_r15_v01.md`（仓库根 `docs/`）。

- **本轮工艺要求**：所有平面弯曲与 3D 升降弯曲统一按最小曲率半径 **R = 15 mm**
  设计；该要求优先于历史代码的 R = 40 mm 与参考 PDF 示例中的 R = 6000 / 6137.33 µm
  （PDF 只作几何形状参考）。R40 历史结果在仓库其他目录原样保留，本目录数据
  **全部**按 R = 15 mm 重新生成与验收，不与 R40 混用。
- **模型**：V2 真实 2x16 双高度接口（z1 = 0.0 mm、z2 = 0.5 mm），1024 条连接；
  二维两组几何：A = D56（轴对齐直线 + R15 精确 90° 弧 + R15 短 S），
  B = 纯正交（轴对齐直线 + 精确 90° R15 弧，禁止非 90° 平面弧）；
  五层 2.5D 高度 z = [0, 0.125, 0.25, 0.375, 0.5] mm（仿真假设，未确认），
  每段抬升 = 接口层平坦 -> 两段 R15 弧升降 S -> 中间层平坦 -> 两段 R15 弧下降
  -> 接口层平坦；只做单次升降，不含 Native 3D 联合寻路。
- **结果**：

| 方案 | R40 历史 | R15 本轮 | Δ | 验收 |
|---|---:|---:|---:|---|
| 二维 D56（Short-S） | 752 | **943**（z1 498 + z2 445） | +191 | PASS |
| 二维纯正交 90° | 262 | **515**（z1 184 + z2 331） | +253 | PASS |
| 五层 2.5D + Short-S | 820 | **985**（抬升 42，transition 84） | +165 | PASS |
| 五层 2.5D + 纯正交 | 383 | **723**（抬升 208，transition 416） | +340 | PASS |

- **独立验收**：8 项全部 PASS（2D A/B 的 z1、z2、组合 1024；25D A/B）。
  10,046 条弧全部严格 R = 15.000000 mm（最大半径偏差 0.0 mm）、500 条 transition
  全部 R15、所有违规计数 0；最小曲率 A 14.99999996 mm / B 14.99999997 mm；
  最小 3D 净空 A 0.080295 mm，B 0.080000 mm（恰在冻结 strict 的 clearance-1e-7
  容差内，属于制造前需复核的临界情形）。
- **上传内容**：
  - `planes/V2/{A,B}/{z1,z2}/`：权威二维 routes.json、audit_strict.json、
    statistics.json、config.json、failed_routes.json、run_summary.json、run.log、
    CHECKPOINT.json；
  - `combined/V2/{A,B}/`：组合 1024 routes_1024.json、statistics.json、
    planes_summary.json、layer_2d.png；
  - `25d/scheme{A,B}/layers5/`：五层 routes_25d.json、run_summary.json、run.log，
    以及 `25d/validation/` 独立三维验收；
  - `validation/`：独立 R15 复核（2D 平面/组合、25D、汇总）；
  - `summary/`：统计表、逐波导 CSV、R40 vs R15 对照表、损耗参数分类；
  - `comparison/`：R40 vs R15 二维对照图、五层 3D 视图 A/B、柱状对比、plots manifest；
  - `checkpoints/`、`sweep2d/`、`work/`：R15 候选真实几何 checkpoint、顺序策略对照、
    运行日志与首轮 R&R worker 半径污染隔离证据（事故已修复并重跑，证据保留供审计）；
  - 根目录 `REPRODUCE_R15.md`、报告副本、`final_validation.json`。
- **省略的可再生文件**（未上传，均可用上传的权威 JSON + 复现命令重建）：
  - `planes/*/*/routing_all.gds|.svg`（逐平面大图/掩模导出）；
  - `combined/V2/*/overlay_3d.png`、`layer_2d.svg`、`routing_1024_two_height.gds`；
  - `figures/`（几何类型图与五层逐层图，共约 34 MB；键图已在 `comparison/` 中）；
  - `comparison/r40_vs_r15_schemeA.png`、`schemeB.png`（`r40_vs_r15_2d.png` 的子集）；
  - `sweep2d/*/checkpoints/`（顺序扫描的中间 checkpoint）。
- **边界/诚信**：五层高度是仿真假设，不是师兄确认的工艺参数；B 的最小净空在 0.08 mm
  边界；不宣称可制造；弯曲/交叉/层间损耗未标定（仅传播 0.05 dB/cm 为实验约定），
  不输出总损耗结论。
- **复现**：`REPRODUCE_R15.md` 给出全部 2D/5D 运行、组合验收、统计与图件命令；
  R15 代码在仓库 `OpticalWaveguideRouter2D/four_side_1024/r15/`。
