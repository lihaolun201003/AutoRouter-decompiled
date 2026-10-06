# opt2d —— 二维光波导布线优化实验

本目录是**只做二维**的布线优化实验模块，放在 OpticalWaveguideRouter3D 项目内，
但完全独立于三维流程（不修改 `src/` 下任何既有文件，不触碰
`OpticalWaveguideRouter2D` 的代码、数据与输出）。

目标：在**相同端点、板尺寸和几何约束**下降低平均与最坏链路损耗。

## 运行环境

2D 项目的 `waveguide_calculator` 依赖 `scipy`，因此实验统一用 2D 项目的解释器运行：

```powershell
..\OpticalWaveguideRouter2D\.venv\Scripts\python.exe -B scripts\opt2d_run_all.py --channels 256 512
```

常用参数：

| 参数 | 说明 |
| --- | --- |
| `--channels 256 512` | 要跑的板规模 |
| `--output outputs/opt2d` | 输出根目录 |
| `--skip-sensitivity` | 跳过消融（更快） |
| `--refine-rounds N` | 拆线重布最大轮数（默认 3） |
| `--figures-only` | 不重新布线，用已保存结果重画图 |

测试：

```powershell
..\OpticalWaveguideRouter2D\.venv\Scripts\python.exe -m pytest tests\test_opt2d.py -q
```

## 模块

| 文件 | 职责 |
| --- | --- |
| `legacy_bridge.py` | 只读复用 2D 项目（端口排布、原版直角布线、损耗模型） |
| `smoothing.py` | 从端点与轨道坐标重建**原版圆弧几何**（Line/Arc 解析表示） |
| `geometry_audit.py` | 端点、切向连接、半径、板边界核验 |
| `evaluator.py` | 统一评价器：全部交叉事件、去重、逐路损耗、两套统计、违规分类 |
| `frozen.py` | Step 13 冻结端点（逐路固定 A 的起点/终点与连接身份） |
| `freeform.py` | Step 13 自由弯角 S 形路径几何（两弧 + 斜向直线） |
| `intersections.py` | 解析求交封装：一般方向直线的浮点残差余量 |
| `step13.py` | Step 13 编排：固定端点对照、D0、自由弯角、敏感性、接受判据 |
| `spacing.py` | 近并行间距检查与线段最小距离（解析，含弧） |
| `planner.py` | 候选轨道与自适应半径布线器（方案 B/C/D）+ 有界拆线重布 |
| `source.py` | 从原版直角表构造评价输入；生成原版统计所需的弯道表 |
| `experiments.py` | A/B/C/D 编排、消融、逐路 CSV 与汇总 JSON |
| `report.py` | 损耗分布、损耗分解、指标对比、最差路线局部图 |

## 口径（与实验约定一致）

* **几何**：`dx >= 2R` 为标准双 90° 圆角；`0 < dx < 2R` 时原版把两个半径 `R`
  的非完整圆弧在水平中点直接相接（半角 `arccos((R - dx/2)/R)`），本模块逐字复刻
  并用原版 `bend_x/bend_y/center/theta/dir` 逐条核验（偏差 < 5e-5 mm，即原版
  四位小数存储的舍入界）。
* **交叉事件**：全网唯一记录（每对路线只测一次；同一对在同一位置的重复记录合并，
  不同位置全部保留）。逐路损耗中一个事件**分别计入两根波导各一次**，不做除以二。
* **交叉角**：由交点处两条曲线的**真实切线**计算（含不同半径圆弧）。
* **损耗**：`直线长度 × 0.05 dB/cm + Σ弧长 × 对应半径弯曲损耗密度 + Σ交叉角度损耗`；
  半径表与原版 `tl/ll` 表一致；交叉损耗表是论文图 3-12 数字化近似。
* **允许的交叉 / 重合 / 近并行间距不足**分别统计。中心线相交本身不是违规；
  间距阈值 = 线宽 + 标称间隔，是**实验假设**（原版只用 `noCross` 的端口顺序启发式，
  没有显式间距规则）。
* 两套统计都保留：**原版统计**（2D 项目 `calc_index`）与**解析物理统计**（本模块）。

## 方案

| 方案 | 含义 |
| --- | --- |
| A | 原版 R5 几何（`plotter_rect` 实际输出） |
| B | 统一半径 R6 重新布线（几何不合法的轨道自动下移到最近合法轨道）——**参数**对照 |
| C | 候选轨道优化（R5 固定，多候选 + 联合评分 + 有界拆线重布） |
| D | 局部自适应半径（候选 = (轨道, 半径)，半径取 R5/R6） |

## 输出

```text
outputs/opt2d/<channels>/
  A|B|C|D/            per_route.csv、summary.json、crossing_events.csv、spacing_events.csv
  sensitivity/        各消融配置的同样产物
  comparison.csv/.json A/B/C/D 对照表
  sensitivity.json     消融汇总
  figures/            损耗分布、分解、指标对比、最差路线局部图
```

`per_route.csv` 同时含解析物理统计与 `legacy_*` 原版统计列，便于口径对照。


## Step 13（固定端点 + 自由弯角）

```powershell
..\OpticalWaveguideRouter2D\.venv\Scripts\python.exe -B scripts\opt2d_step13.py --channels 256 512
..\OpticalWaveguideRouter2D\.venv\Scripts\python.exe -m pytest tests	est_opt2d_step13.py -q
```

| 方案 | 含义 |
| --- | --- |
| A | 原版几何（端点来源，仅参照） |
| R5U | 固定端点 + U 型 + R5 |
| D0 | 固定端点 + U 型 + 优先 R6、失败回退 R5（单候选、无搜索） |
| D56 | 固定端点 + U 型 + 多候选自适应 R5/R6 |
| F5 / F56 | 跨侧连接改用自由弯角 S 形（R5 / R5+R6 候选） |

关键约定：**端点逐路冻结**（不再交换端口槽位，`allow_port_reorder` 默认关闭）；
快照覆盖完整状态与冻结 pass 边界；间距检查区分"允许的交叉 / 接触 / 重合 / 近并行"；
自由弯角候选必须重算交叉、接触、重合与间距，重合硬拒绝。
报告见 `docs/reports/step_13_opt2d_fixed_endpoints_and_freeform.md`。

## Step 13 补修与复验（真实重合 + 间距口径）

补修起因：旧求交兜底把 256 F56 的一条**真实重合**（路线 #7/#31 的斜线段同在
`x + y = 149.9` 上，重叠 152.007142675 mm）误判为 cross。

| 文件 | 修复 |
| --- | --- |
| `intersections.py` | 直线段稳健分类：夹角正弦（`|sin| <= 1e-8` 判平行）+ 垂距（`max(tol, scale·1e-12)` 判共线）+ 投影区间（重叠 → `overlap`，退化 → `touch`）；非平行分支校验"交点在两条有限线段上"且残差 `<= max(tol, scale·1e-7)`，超限抛错 |
| `spacing.py` | 弧—弧最近距离补齐圆心连线上的**同向**极值候选（`(1,1)`、`(-1,-1)`） |
| `planner.py` | AABB 预筛用间距阈值；间距违规按路线对计数；接受规则改为"平均严格改善 且 最大不恶化"；新增 `radius_overrides`（逐路半径冻结，用于公平对照）与 `small_angle_deg` / `small_angle_penalty_db`（小角交叉限制） |
| `evaluator.py` | 路线级 AABB 预筛与间距口径一致 |
| `tests/test_opt2d_step13_fixes.py` | 新增 19 项回归测试（真实反例、反向/交换/平移、近乎平行、共线分离、端点接触、弧—弧极值、计数单位、预筛阈值、小角交叉限制） |
| `scripts/opt2d_step13_fix.py` | 补修复验：重新评价/重新布线、敏感性 ×1/×2/×5/×10、半径对照、逐路差异、间距惩罚消融 |
| `scripts/opt2d_step13_scan_legacy.py` | 旧产物合法性扫描（重合/接触/间距） |
| `scripts/opt2d_step13_constrained.py` | 受约束自由弯角实验（小角交叉限制 vs 间距惩罚） |

```powershell
# 重新验证与重新布线（新产物 outputs/opt2d_step13_fix）
..\OpticalWaveguideRouter2D\.venv\Scripts\python.exe -B scripts\opt2d_step13_fix.py --channels 256 512
# 旧产物合法性扫描
..\OpticalWaveguideRouter2D\.venv\Scripts\python.exe -B scripts\opt2d_step13_scan_legacy.py
# 受约束自由弯角实验（base / spacing / small / both）
..\OpticalWaveguideRouter2D\.venv\Scripts\python.exe -B scripts\opt2d_step13_constrained.py --channels 256
# 回归测试（新增 19 项）
..\OpticalWaveguideRouter2D\.venv\Scripts\python.exe -m pytest tests\test_opt2d_step13_fixes.py -q
```

报告见 `docs/reports/step_13_opt2d_fix_and_reverification.md`（含勘误、重新布线结果、
×1/×2/×5/×10 敏感性边界与受约束自由弯角实验提案）。
