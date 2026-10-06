# 系统架构与实现状态

本文描述当前仓库实际运行的固定 1024 条波导实验，以及保留但尚未实现的通用接口。主要入口是 `scripts/run_fixed_1024_3d.py` 和 `scripts/visualize_fixed_1024_3d.py`，不是根目录的 `main.py`。

## 数据流

```text
data/fixed_1024_legacy_seed.json
  → 继承 512 条历史连接并按固定规则扩展为 1024 条
  → PMT / Port / Waveguide 与 300 × 200 mm 板模型
  → 二维路线准备、轨道分配及 Line/Arc 平滑
  → 所有二维路线提升到 Layer 0，形成 Route3D 初态
  → 三维 clearance 检测与三层局部抬升
  → 保存路线、碰撞集合、统计与全量复核结果
  → 从保存的最终状态只读采样并绘制 Step 11 图
```

固定数据规则、板布局及历史输入来源见 [Step 10 报告](reports/step_10_fixed_1024_3d_routing.md)。早期 512 路线分析与多个三维基础实验的记录保存在 `docs/reports/`，不能把这些阶段的参数和结论自动视为固定 1024 实验的配置。

## 关键模块

| 模块 | 当前职责与状态 |
| --- | --- |
| `models.py` | 二维点、PMT、端口、连接、板、层及二维路线的数据结构 |
| `io.py` | 历史 FiberBoard 输入与快照读取；通用连接读取、配置读取、保存接口仍为占位 |
| `geometry.py`, `router_2d.py` | 二维 U/Z 路线、轨道分配、直线与圆弧平滑；`build_special_z_route` 旧入口仍为占位，实验使用已实现的解析 special-Z 平滑路径 |
| `collision.py`, `physical_intersections.py` | 二维线段/解析曲线相交与物理交叉事件归并 |
| `multi_crossing*.py`, `multi_attribution.py`, `double_cross_audit.py` | 历史二维多波导交叉及归因分析，不是固定 1024 三维抬升的主循环 |
| `geometry_3d.py`, `geometry_3d_diagnostics.py` | 三维 Line、平面 Arc、余弦过渡、Route3D、几何连接与曲率检查 |
| `clearance_3d.py` | 解析/自适应的三维 primitive、路线之间及自身间距检查 |
| `layer_assignment_3d.py` | 单路线抬升候选构造和局部评估 |
| `sequential_elevation_3d.py`, `three_layer_assignment_3d.py` | 顺序处理当前碰撞集合、生成两目标层候选并接受使全局碰撞数下降的抬升 |
| `fixed_1024_routing.py` | 固定输入扩展、二维几何构造、专用三层配置、实验入口封装及 Route3D 序列化 |
| `visualize_3d.py` | 从最终检查点加载路线、显示采样、分层绘图和统计图；不更改路线 |
| `loss.py`, `loss_analysis.py` | 部分传播/弯曲损耗计算与二维损耗分析；可靠的交叉角损耗参数尚未确定，未形成固定 1024 的实测总损耗模型 |
| `router_3d.py`, `optimizer.py`, `metrics.py`, `export.py`, `visualize.py` | 预留的通用路由、优化、指标、导出和旧绘图 API；含 `NotImplementedError`，不能作为当前实验入口 |

## 固定 1024 路由策略

1. 由本地种子生成 128 个 PMT、2048 个唯一端点及恰好 1024 条连接。二维准备阶段先分配轨道，再把正交路线平滑为解析几何；64 条特殊 Z 路线走专用构造。
2. 初态将所有路线放在 z = 0 mm。实验层位是 0、1、2 mm，clearance 为 0.1 mm，过渡曲率半径下限为 5 mm；均为 `EXPERIMENTAL_SYNTHETIC` 参数。
3. 建立当前碰撞对集合。每轮选择目标对，按当前碰撞度考虑移动路线，在有限直线窗口上为两个高层构造一次上升和下降过渡；不切圆弧，不改变端点或 XY 主路径。
4. 候选与其余当前路线进行三维间距检查。只有全局碰撞对数严格下降才接受；被移动路线最多抬升一次。局部更新碰撞集合，最终重新检查全部 523,776 对路线并核对保存后重载的结果。
5. 实验设 1024 次目标尝试上限。保存结果为 175 次成功抬升、138,113 对剩余碰撞与 4 对未决；达到上限不等于已经无可改进候选。

该过程是固定布局的碰撞减少实验，不提供全局最优性、零碰撞或制造可行性保证。结果中的 `PASS` 表示输入、几何、序列化和复核满足本阶段的实验检查，并非产品验收。

## 配置、产物与验证

固定实验的实际参数由 `fixed_1024_routing.fixed_three_layer_config()` 和 `build_fixed_1024_geometry()` 使用；`config/default.yaml` 是早期通用模板，保留未知物理参数为 `null`，其 150 × 150 mm 单层设置并非 Step 10 的配置。

`scripts/run_fixed_1024_3d.py` 生成 `outputs/step_10_fixed_1024_*.json`、步骤 CSV 和测试记录。重要检查点为 `final_route_state.json`、`summary.json`、`collision_sets.json`、`validation.json`。单次完整运行记录约 1173 秒，包含初始及最终全对扫描。`scripts/visualize_fixed_1024_3d.py` 读取已有检查点，输出 13 张图的 PNG/PDF 和 `step_11_visualization_summary.json`；绘图采样不写回几何，也不重新路由或计算碰撞。

测试位于 `tests/`，可从项目根目录运行 `.\.venv\Scripts\python.exe -m pytest -q`。截至当前仓库状态为 705 项通过。实验细节、具体产物与限制分别见 [Step 10 报告](reports/step_10_fixed_1024_3d_routing.md)和 [Step 11 报告](reports/step_11_1024_3d_visualization.md)。
