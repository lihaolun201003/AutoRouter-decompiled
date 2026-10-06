# Step 8.5-D：精确 Line/Arc Collision V0.1

## 范围与文件

本次新增零宽二维中心线解析相交能力。“精确”指解析求交、不采用采样折线近似；计算仍使用 Python 双精度浮点与绝对容差，不是任意精度数学证明。

修改：
- `src/collision.py`
- `tests/test_collision.py`

新增本报告。未修改 geometry、models、Router、allocator、IO、loss 或 special-Z placement policy；没有安装依赖。

## 新增接口

- `point_on_arc_2d(point, arc, tol=1e-9)`：检查半径与带方向的有限 sweep。
- `find_segment_intersections_2d(a, b, tol=1e-9)`：统一接收 LineSegment2D / ArcSegment2D，返回 `list[SegmentIntersection]`。
- `find_smoothed_route_intersections_2d(a, b, tol=1e-9)`：逐 segment pair 返回所有事件。
- `find_smoothed_route_self_intersections_2d(route, tol=1e-9)`：检查每个无序段对。
- `CurveRouteIntersection`：保存两个 route ID、两段索引、类型、kind 与 point。

旧 axis-aligned skeleton API 和批量 skeleton 验证政策保持不变。新接口报告几何关系，不决定交叉是否应允许，不实施修复或全局有效性政策。

## 分类与返回语义

| 关系 | 表达 |
| --- | --- |
| none | 空事件列表 `[]` |
| cross | 双方内部的横穿；一个离散点对应一个事件 |
| touch | 切触或任一端点接触；包含容差内接触 |
| overlap | 共同轨迹长度大于容差；`point=None` |

同一段对可能返回两个不同的点，甚至分别为 touch 和 cross。重合圆弧不使用任意点代表其公共轨迹。当前 overlap 不返回公共轨迹的端点或参数区间。

每个段对内部去重点；不同段对即使共享同一坐标仍分别保留事件，便于定位。事件数量不等同于全局去重后的物理交叉点数量。

## Line-Line

通用有限二维直线段解析相交，允许斜向线段。以单位方向向量计算交点参数，检查有限长度范围；平行共线时比较投影区间。

测试覆盖横穿、端点接触、平行分离、共线接触/分离/重合、反向端点顺序以及近乎平行的相交和分离。非零小角度不会仅因小于用户长度容差而被当作平行。

零长度解析线段明确拒绝，与已有 SmoothedRoute2D 的有效性约束一致；旧 skeleton API 的退化点段行为不变。

## Line-Arc

先求线与 supporting circle 的候选点，再分别检查有限线段参数和实际 arc sweep。切线只生成一个候选点。

测试覆盖两交点、切触、分离、圆相交但 sweep 排除、切点在线段外、圆弧端点、直线端点、CW/CCW、quarter arc、两个交点类别不同以及近切线两点仍可分辨的情况。交换 Line/Arc 参数顺序可得到相同结果。

## Arc-Arc

支持外离、外切、内切、两交点、包含、同心不等半径、同圆重合及同圆端点接触。

同圆情况将 sweep 变为有方向无关的 CCW 区间，并用加减 2π 的区间比较处理回绕。非零公共弧返回 overlap；互补半圆仅共享两端点时返回两个 touch。

不同 supporting circles 的解析候选点必须同时满足两条 arc 的有限 sweep。测试覆盖 supporting circles 相交而 arcs 不相交、部分/完全/反向重合、回绕及参数交换。

## Sweep membership 与数值处理

- sweep 正值 CCW、负值 CW，沿用 `0 < abs(sweep) <= pi`。
- atan2 差值按方向取模 2π；支持跨 0、2π、±π。
- 半径和端点使用默认 1e-9 的非负绝对长度容差；角容差由 tol/r 转换，单位不绑定 mm。
- 重合区间长度超过 tol 才记 overlap；容差内端点关系记 touch。
- 近切触在长度容差内按切触处理，因此属于容差分类，不能作为精确拓扑判定的证明。
- 线圆根使用因式分解形式；圆圆计算先缩放，避免直接对大半径平方；只在切触容差允许的情况下合并根。
- 非法容差、无效圆弧、零长度线、非有限输入或检测到不可可靠计算的数值状态会抛出受控异常。
- 不人为放大容差，不使用采样求交。极端尺度、病态条件下的完备鲁棒性仍不作保证。

## Route 与 self-intersection

route-pair 保留 route ID、segment index/type 以及每个交点。进入计算前验证输入段和路径连续性，空 route 合法；输入不被修改。

self 检查仅忽略相邻段共同端点处的正常 touch，保留：
- 非相邻 touch；
- 真正 cross；
- 相邻折返 overlap；
- 相邻圆弧除共同端点外的第二交点。

封闭路径的首尾段目前没有额外特殊邻接政策；非连续索引的首尾接触仍会报告。

## 验证结果

使用既有项目 Python 3.10 环境，通过 runpy 加载测试文件并直接调用全部 test functions。没有安装 pytest 或其他依赖。

| 模块 | 通过 / 总数 |
| --- | --- |
| models | 18 / 18 |
| geometry | 63 / 63 |
| router_2d | 48 / 48 |
| collision | 98 / 98 |
| loss | 26 / 26 |
| io | 28 / 28 |
| 总计 | **281 / 281** |

原有 227 个测试全部通过，新增 **54** 个解析测试全部通过；最终测试运行捕获警告数 **0**。

### 小规模 smoke validation

全部为合成几何，没有运行真实 512 全局验证：
- 普通双弯圆角路径自交结果为空，正常 Line/Arc 接点被正确跳过。
- special-Z：端点 (0,0) → (4,20)，radius=5，构造后自交结果为空。
- 该 special-Z 与 y=3 的有限横线检测得到一个 cross。
- 非 quarter special-Z 圆弧的中间点通过 sweep membership。
- Line/Arc route pair 保留两个 cross，Arc/Arc route pair 也保留两个 cross。

## 局限与下一步边界

1. 仅零宽中心线，不代表物理波导外包络；没有 finite width、clearance 或 spacing 检查。
2. 没有损耗、优化、track reassignment 或 rerouting。
3. overlap 只报告关系，不输出重合弧/线的详细参数区间。
4. 当前只支持现有模型允许的不超过半圆的单段 sweep。
5. 未运行 454 ordinary + 58 special-Z 的真实 512 全局精确验证；不能声称“512 全局无碰撞布通”。
6. 58 条 special-Z 的 allocator unsupported_geometry 状态没有改变。
7. Git 命令在当前终端不可用，未取得 git diff/status；本次写入仅针对上述两个代码/测试文件及本报告。
8. Step 8.5-E 留待下一次指令，本次停止于 8.5-D。
