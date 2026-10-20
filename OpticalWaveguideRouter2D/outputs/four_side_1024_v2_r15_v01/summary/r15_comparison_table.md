# R40 vs R15 对照表（自动生成）

- 生成时间（UTC）：2026-10-20T08:58:33Z
- 说明：R40 numbers are the frozen historical routed counts only; every length/geometry/loss column in this R15 report is computed from R15 artefacts. The two rounds are never mixed outside this comparison.

## 1. 布通数对照

| 配置 | R40 布通 | R15 布通 | Δ (R15−R40) | R15 失败 | R15 总长 mm | R15 同层交叉 | R15 最小半径/曲率 mm |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2D D56 (Short-S), A | 752 | 943 | +191 | 81 | 149,599.532 | 136,182 | 15.000000000 |
| 2D pure orthogonal 90°, B | 262 | 515 | +253 | 509 | 88,847.389 | 54,184 | 15.000000000 |
| 5L 2.5D + Short-S, A | 820 | 985 | +165 | 39 | 160,194.232 | 137,081 | 14.999999963 |
| 5L 2.5D + pure orthogonal, B | 383 | 723 | +340 | 301 | 136,462.234 | 63,816 | 14.999999966 |

## 2. 说明

- R40 列只有冻结的历史布通数（2D D56 = 752、2D 纯正交 = 262、5L 2.5D+Short-S = 820、5L 2.5D+纯正交 = 383），不包含任何 R40 几何/长度/损耗数值；R15 列全部由本轮 R15 产物重算。
- R15 工艺要求：所有平面弯曲与 3D 升降曲线固定 R = 15 mm；2D 行“最小半径/曲率”来自图元半径，5L 行来自独立 3D 验收的最小曲率半径。
- 2D R15 布通取自 `combined/V2/{A,B}/routes_1024.json`（若缺失则回退为两平面之和）。
- 5L 2.5D R15 布通取自 `25d/scheme{A,B}/layers5/routes_25d.json`；其升降曲线半径为 R = 15 mm。
- 因此本表只用于回答“在 R15 工艺约束下布通数相对 R40 基线变化多少”，不能把两轮的长度/损耗/交叉数直接相除。

