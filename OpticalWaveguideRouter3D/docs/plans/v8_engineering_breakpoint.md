# v8 工程断点：保持 XY 的路径弧长窗口（本轮未实现完成）

状态：**未实现、未运行、未验收**。本文件只记录设计约束与恢复入口，不包含任何 v8 结果。
写入时间：本轮通宵执行期间（v5 正式实验进行中）。

## 为什么停在断点

通宵窗口的优先级为 v5 → v6 → v7 → A/B/F → C/D → E/G → H → v8。在 v5/v6/v7 与八项单项消融
尚未全部跑完并复核之前，v8 需要同步扩展几何表示、真曲率、保守近距判定、序列化与重载，
不能在窗口内完成验收。按任务文件要求，这里保留明确断点，而不是声称 v8 已完成或用一个
小预算探针冒充一整轮。

## 现有实现的实际约束（读代码得到，不是推测）

1. `src/geometry_3d.py: CosineTransition3D` 的 XY 是**直线插值**：
   `point_at` 用 `(1-t)*start + t*end` 得到 XY，只有 z 走 `sin^2(pi t/2)`。
   因此升降窗口的 XY 轨迹不跟随冻结平面路径。
2. `src/layer_assignment_3d.py: build_elevation_candidate` 明确要求
   `isinstance(route.primitives[i], LineSegment3D)`（升窗）与 `LineSegment3D`（降窗），
   并在 `i == j and v >= x` 时判定窗口重叠；弧段完全不能切分。
3. `elevation_candidates` 的窗口枚举同样只遍历 `LineSegment3D`，
   过渡长度由 `minimum_xy_run_for_radius` 按**直线**公式给出，
   弧段上该公式不适用（v8 prompt 第 5 条明确禁止直接套用）。
4. `CosineTransition3D.minimum_curvature_radius = 2*Lxy^2/(pi^2*|dz|)` 是二维余弦模型的真曲率半径；
   一旦 XY 变成弧线，必须改用三维曲率 `||r′×r″|| / ||r′||³`，并给出可靠上界或收敛认证。
5. `strategy_v2_3d.xy_projection_preserved` 用采样做双向 XY 比对，
   `clearance_3d` 的保守距离界、`elevation_structure` 的“恰好 0 或 2 个过渡”判定、
   `fixed_1024_routing.serialize_route3d/deserialize_route3d` 的原语分支，
   都必须同时支持新原语，否则不得按 CLEAR 接受。

## 需要一起改的链接（缺一不可）

- 新原语：路径参数的余弦升降段，沿冻结平面路径弧长 s 定义 (x(s), y(s), z(s))，
  支持切分 `PlanarArcSegment3D` 与跨相邻 primitive，内部切分保留共同相位，
  不能把每个小片重启为一次完整余弦升降。
- `point_at` / `tangent_at` / `length()`（自适应 Simpson 的 speed 函数要含弧长曲率）、
  真三维曲率与收敛状态、`minimum_curvature_radius` 的替代证明。
- `xy_projection_preserved`、保守近距判定（空间包围/弦误差界）、自近距、未决语义。
- `RouteView.prepare`、`pair_status`、`elevation_structure`（逻辑升降计数不因片段数增加而叠加）、
  `serialize_route3d` / `deserialize_route3d` 与旧文件兼容、可视化。
- 生成器：新增枚举密度、窗口长度集合、边界 margin、总候选上限与去重规则，
  全部在正式评价前冻结，并记录截断。

## 恢复入口（可直接执行）

```powershell
cd "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D"
# 现状：v8 的生成域开关尚不存在，G1 需要先落地上面的支持链
# 1. 先做第一阶段几何支持链与针对性验证（不进入主试验）：
.\.venv\Scripts\python.exe -B scripts\validate_3d_foundation.py
.\.venv\Scripts\python.exe -B scripts\validate_cosine_curvature.py
# 2. 支持链通过后，在 scripts/overnight_registry.py 增加两个生成域 spec：
#    G0 LEGACY_LINE_ONLY（默认行为，必须与现有候选逐一相同）
#    G1 PATH_WINDOWS（保留全部旧候选并新增跨弧窗口）
#    然后在 StrategySpec 增加 generation_domain 字段并纳入 generation_settings() 缓存键。
# 3. 冻结 v8 manifest 后再跑：
.\.venv\Scripts\python.exe -B scripts\freeze_overnight_manifest.py . outputs\overnight_3d_ideas --round v8
.\.\scripts\overnight_launch.ps1 -Round v8 -Groups <G0/G1 x N/R x 720/1440/2880>
```

## 已知必须先回答的旧无窗侧问题

v4 审计给出 33/120 个目标侧在现行规则下无合法窗口（单方已抬升 13/20、双方已抬升 12/20、
双方未抬升各 4/40）。这 33 侧是 v8 的候选诊断对象，但它们只作为**固定诊断集**，
不得用来挑选性能目标。v8 是否让其中任何一侧获得合法候选，本轮**没有测量**。
