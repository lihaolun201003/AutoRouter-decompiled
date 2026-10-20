# R15 实验轮（2026-10-20）目录、数据契约与工具约定

**工艺要求**：所有平面弯曲和三维升降弯曲统一按最小曲率半径 **R = 15 mm** 设计；
该要求优先于历史代码的 R = 40 mm 与 PDF 示例中的 R = 6000 µm / R = 6137.33 µm
（PDF 只作几何形状参考）。本轮保留 R40 全部历史结果，不覆盖、不混用。

## 1. 进程配置（必须最早应用）

`four_side_1024/r15/profile_r15.py`：

- 在任何绑定半径的模块 import 之前调用 `profile_r15.apply()`；
- 它把 `fslw.config.RADIUS_MM` 改为 15、`FIXED_RADIUS_40MM=False`，并替换
  `fslw.config.process_record()` 使输出的 config/process 记录半径正确；
- `v2opt.candext.R`、`v2opt.ortho90.R`、`fsd25d.config25d.RADIUS_MM`、
  `fsd25d.path3d` 的默认 transition 半径都在 import 时绑定，因此必须在 apply 之后导入；
- R40 默认行为不变（不调用 apply 时仍是 40 mm）。

## 2. 输出根目录

```
outputs/four_side_1024_v2_r15_v01/
├─ planes/V2/A/{z1,z2}/      # R15 二维 D56（保留 Short-S）
├─ planes/V2/B/{z1,z2}/      # R15 二维纯正交 90°
├─ combined/V2/{A,B}/        # 1024 组合（v2opt.finalize 生成）
├─ checkpoints/              # R15 真实几何 checkpoint
├─ sweep2d/                  # 顺序策略对照（各自独立 root）
├─ 25d/scheme{A,B}/layers5/  # R15 五层 2.5D（fsd25d.run25d 写出）
├─ 25d/validation/           # 五层独立 3D 验收（fsd25d.validate25d 写出）
├─ validation/               # 二维 strict 验收（v2opt.finalize 写出，附 R15 适配）
├─ summary/                  # R15 统计、损耗参数清单、对照表
├─ comparison/               # 新旧（R40 vs R15）对照图
└─ report_four_side_1024_v2_r15_v01.md
```

## 3. 数据格式

- **二维平面**：与历史 FSLW 轮完全相同的 `routes.json` schema
  （`four_side_1024_fslw_plane_routes_v1`，1024 条记录 = 每平面 512 身份），
  但 process/config 中 radius = 15、`fixed_radius_40mm=false`；
  路线图元：D56（直线 + 90° 弧 + 非 90° 短 S）或纯正交（仅轴对齐直线 + 精确 90° 弧），
  所有弧半径 = 15 mm。
- **五层 2.5D**：`SCHEMA_25D.md` 的 `routes_25d.json v1`，但
  transition 的 `radius_mm = 15`、`theta/footprint/length` 按 R = 15 重新计算；
  layer 高度仍为 `[0, 0.125, 0.25, 0.375, 0.5]` mm（仿真假设）。

## 4. 本轮新增工具（四个独立模块）

| 模块 | 用途 |
|---|---|
| `r15/u_geometry.py` | 同侧端口 180° U 型几何模块（含直线/其他圆弧组合、可达性判断、测试），对应 PDF 总版图/第一层的 U 形与 S 形参考 |
| `r15/validate_r15.py` | 独立 R15 验收封装：二维 strict（`fslw.validate_fslw.build_report(radius=15)`，逐平面/组合）+ 三维（`fsd25d.validate25d` 以 R15 profile 运行）；输出 `validation/` JSON |
| `r15/stats_r15.py` | R15 统计：二维/三维长度、弧数量/半径/转角/弧长、S 弯、升降弯曲、同层交叉、逐波导总长与总弯曲；损耗参数分「已标定/待标定」 |
| `r15/plots_r15.py` | 对照图：R40 vs R15 二维布局；R15 二维几何类型着色；R15 五层三维/分层图 |

## 5. 损耗口径

本轮**不引入新损耗系数**。已有参数只有传播损耗 `PROPAGATION_LOSS_DB_PER_CM = 0.05`
（实验约定，非实测标定）；弯曲损耗、交叉损耗、层间影响一律标注
`unknown_uncalibrated` / 待马老师确认，不输出总损耗结论。可复用
`fslw/metrics.py` 的长度/交叉统计框架，但必须区分已标定与未标定项。
