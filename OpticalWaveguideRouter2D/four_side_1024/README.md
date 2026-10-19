# 四边 1024 通道单层二维路由

当前交付范围为**将1024条CSV连接接入原逆向算法的四边适配入口**。`legacy_adapter.py` 默认只读取、校验并保存输入，不执行布线、扫描或优化。原有256/512代码保持不变。具体适配差异见 [LEGACY_ADAPTATION.md](LEGACY_ADAPTATION.md)。

设计条件为 150 × 150 mm 板面、四边各 16 个接头、每接头 2 × 16 个通道、1024 条波导。全部路线固定为 `layer=0`，不使用 z 方向避让。初始弯曲半径 5 mm、波导宽度 0.05 mm、边缘间距 0.125 mm 是本次验证参数，不是新玻璃工艺最终标准。

## 运行

在 PowerShell 中使用项目现有虚拟环境：

```powershell
Set-Location -LiteralPath 'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D'
& '.venv\Scripts\python.exe' -m four_side_1024.legacy_adapter
```

指定 CSV 和独立实验输出目录：

```powershell
& '.venv\Scripts\python.exe' -m four_side_1024.legacy_adapter `
  --input 'C:\Users\lihao\Desktop\optical_1024_multitomulti_connectivity_v1.csv' `
  --output 'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\outputs\four_side_1024_legacy_input_v1'
```

仅生成连接关系检查和第一张连接图：

```powershell
& '.venv\Scripts\python.exe' -m four_side_1024.inputs
```

显式加 `--route` 后才进行布线，仍先校验CSV并生成连接图。当前保留邻边固定L形／三弯模板；取消每条256次评价上限；两个跨边分支按源边方向分别调用，在本CSV中各分配512条。默认仅保留全局600秒、900000次几何评价预算，可分别用 `--seconds`、`--evaluations` 调整。导出和最终几何复核需要额外时间，预算不是整个命令的硬超时。历史66条结果来自修改前版本。

## 依赖与检查

沿用项目虚拟环境中的 NumPy、Matplotlib 和 GDS 导出支持。Shapely 2 为可选加速依赖：可用时用 `STRtree` 做空间查询；缺少可兼容的 Shapely 时，模块退回 NumPy 包围盒筛选。两条路径都用解析直线和圆弧处理最终几何相交、切向和距离判定；后备模式可能较慢。不要为了安装本模块而改写旧版环境的核心依赖。

```powershell
# 独立模块几何检查
& '.venv\Scripts\python.exe' -m unittest four_side_1024.geometry_test -v

# 原有 256/512 回归检查
& '.venv\Scripts\python.exe' -m pytest tests -v
```

## 原始连接身份

直接读取完整输入，保留 CSV 的 `route_id`、源/目标接头、行、列及通道。端点身份为 `接头:行:列`，例如 `N01:1:1`。程序检查全部路线均跨不同边、每个物理端点只使用一次、接头通道完整、对边和邻边关系与文件一致。输入内容以原字节副本和 SHA256 保存；已有输入副本与新输入不同时会拒绝覆盖。

CSV 的 `row=1` 和 `row=2` 指接头内部两排通道。它们共同进入同一个冲突索引；分别显示两组路线的图片只用于观察，不代表两个布线层。路径生成中的辅助几何选择不改变 CSV 配对。

## 物理端口与 `virtual_unfolded`

物理接头面坐标保存在 `physical_face_u_mm`、`physical_face_v_mm`：16 列按 0.250 mm 间距排列，双排中心距为 0.500 mm。依据本地 IEC 61754-7-3:2019 图2，以及 YD/T 1272.5-2019 图A.8(b)。列跨度为 3.750 mm，行、列、通道身份保持完整。

真实接头面横切光轴。将它投影到板面时，两排同列端点投影重合，不能把这两个物理端口直接当成不同的平面边界端点。`physical_projected_xy` 只表示该投影。

当前坐标约定为 N/S 两边列号向全局 x 增大方向排列、E/W 两边列号向全局 y 增大方向排列；行号 1/2 对应面坐标 v 的负/正方向。CSV 连接身份不受这一显示约定影响。实际接头键位、观察方向和装配旋转仍须用器件装配图核实。

本版实际寻路端点使用明确标识的 `virtual_unfolded` 模式：把每个接头的 32 个通道按身份展开成一排独立的 `routing_xy`，中心距为 0.175 mm。它等于验证波导宽度与边缘间距之和；它不是物理接头列距。路线起终点固定在这组计算端点上。物理端口到这组展开端点的耦合器、扇出结构及损耗尚未得到实现或制造验证，因此计算结果不能直接认定为实际 2 × 16 接头器件可制造。

## 接头机械限制

9 mm 接头中心距是暂定参数。标准中的裸插芯宽度 D 为 6.3–6.5 mm、高度 U 为 2.4–2.5 mm；完整 MPO 外框套 H 为 12.19–12.59 mm，另一个正面方向 R 最大为 7.7 mm。来源为 IEC 图9／表6及 YD/T 图A.1／表A.1。

若 H 沿着板边，9 mm 中心距使相邻完整外框套重叠 3.19–3.59 mm。16 个完整外框套零安装净空至少需要 195.04 mm，超过本实验固定的板边长度。裸插芯宽度能够放入该中心距，不等于完整机械连接器能够安装。程序记录外形冲突，并保留 150 mm 板面和暂定中心距；不会自动扩大板面或移动端点。

正面横截面尺寸不能当成接头沿光轴的完整安装深度。图中的板外外形仅为暂定包络示意，不是供应商总装图。安装深度、壳体选型、板角、固定件和展开耦合结构仍需机械设计确认。机械资料的页码、文件哈希及已核对限制可见实验目录中的 `mechanical_reference.md` 和 `mechanical_reference.json`。

## 当前交付与历史实验

当前默认入口仅生成 `legacy_adapter_input.json` 和 `integration_status.json`，并保存原始CSV副本、哈希、2048端点坐标、64接头及完整连接图。状态明确为 `input_connected`、`routing_executed=false`。默认入口不调用 `route_original`；后续寻路须另行显式指定 `--route`，本次按用户要求停止后续运行。

本目录先前的 `router.py` 和通用候选搜索实验保留作为历史记录，不属于当前接入入口。已中止的试跑或历史输出不能作为本次1024接入的布通验收结果。

允许的二维交叉必须真实检测并记录交叉位置和角度。交叉只豁免两条路径的局部交叉区域；其他位置仍检查波导宽度和间距，不因两条路线相交而整对忽略间距。未经允许的重叠、自交、相切和交叉区域重叠会导致候选被拒绝。交叉角、交叉区域工艺与光学可行性仍需独立评价。

输出包含不可变输入信息、配置、物理/计算端点、路线解析几何、成功及失败原因、策略统计、图像、SVG、单层 GDS 和运行日志。全体路由图标注实际成功数量；GDS 几何使用同一布线层。正式实验结论、交叉分布、瓶颈和损耗对照写入实验报告。旧 AutoRouter 损耗模型只作为估计对照，不是新玻璃实测值。

失败表示在指定时间、候选数和候选评价预算内未找到合法候选。有限候选搜索没有覆盖所有可能曲线，不能据此证明该路线在数学上不可能完成；也不能把一部分成功路线当作全体布通。即使计算端点上的路线全部通过几何检查，也需要另行解决物理端口耦合、接头外壳冲突以及同层交叉工艺，才能讨论器件制造。

## D56 优化引擎（`four_side_1024/d56/`，467/1024）

`d56/` 是本轮新增的独立包，**不修改**上面的 legacy 适配器与原 256/512 代码：

| 文件 | 作用 |
|---|---|
| `SPEC.md` | D56 几何契约、JSON schema、双口径验收说明、变更记录 |
| `frames.py` | 6 个有向边对的 canonical 刚体框架 |
| `candidates.py` | D56 候选族（对边 `straight/U/Z`，邻边 `L/Z3`），车道由实际障碍带推导 |
| `index.py` | primitive 级空间哈希 + 解析交点/最小距离的精确单层冲突索引（exact / legacy 两种交叉区口径） |
| `search.py` | 顺序调度（A/B/C/D/E）、候选排序、事务式 Rip-up and Reroute、最终自审计 |
| `run.py` | 实验驱动（策略/预算/checkpoint） |
| `validate_d56.py` | 独立 D56 校验器（不 import `conflicts.py`），authoritative audit |
| `outputs_d56.py` / `plots_d56.py` | 13 个交付产物（PNG/SVG/GDS/JSON）管线 |
| `tests_d56/` | pytest 套件（86 passed） |

结果：**467/1024**（精确交叉区口径；历史口径敏感性 72/1024）。完整报告见
[`docs/reports/four_side_1024_d56_optimized.md`](../../../docs/reports/four_side_1024_d56_optimized.md)，
失败诊断见 [`docs/reports/d56_1024_failure_diagnosis.md`](../../../docs/reports/d56_1024_failure_diagnosis.md)。

```shell
python -m four_side_1024.d56.run --strategy A --groups NW,EN,SW,ES,NS,EW --within x_desc --out outputs/four_side_1024_d56_optimized
python -m four_side_1024.d56.validate_d56 --routes outputs/four_side_1024_d56_optimized/routes.json --compare-exact
python -m four_side_1024.d56.outputs_d56 --run-dir outputs/four_side_1024_d56_optimized --run-status complete
python -m pytest four_side_1024/d56/tests_d56 -q
```

## ABCD 与 FSLW 两轮新实验（2026-10-19 晚）

| 包 | 内容 | 最佳结果 |
|---|---|---|
| `abcd/` | V1/V2 连接拓扑 x A/B/C/D 四种算法在**单层虚拟展开**基线（R = 5 mm、125 um 间距）上的 8 组全量 1024 条实验、C 的轮流设计消融、D 的全局联合候选 + LNS、strict 局部交叉窗口验收 | 462/1024（V1_B）；strict 口径复验使历史 467 -> 465 |
| `fslw/` | **双高度真实 2x16 接口**（row1->z1 对边平面、row2->z2 邻边平面）在飞秒直写参数 **R >= 40 mm（固定 40）**、边缘间距 **30 um** 下的 16 个平面实验 + 8 个 1024 通道组合布局 + 4 配置参数敏感性 | **694/1024（V2_C）**；邻边平面 22.3 %/25.0 % 连接几何上无合法 R=40 路径 |

公共能力：`abcd/SPEC.md`（strict 交叉窗口数学定义、8 组实验矩阵、产物契约）、
`fslw/SPEC.md`（双高度接口模型、R=40 几何、敏感性矩阵、诚实边界声明）、
两套独立几何实现（路由器索引 `d56/index.py` 与独立校验器 `abcd` 复用 validator /
`fslw/validate_fslw.py`），交叉验证 mismatch = 0。

入口：

```shell
# ABCD 轮（虚拟展开单层基线）
python -m four_side_1024.abcd.run --experiment V1_B --policy strict
python -m four_side_1024.abcd.finalize_all

# FSLW 轮（双高度真实 2x16，R>=40 mm，30 um 间距）
python -m four_side_1024.fslw.run --topology V2 --plane z2 --algorithm C
python -m four_side_1024.fslw.validate_fslw --scan-root outputs/four_side_1024_fslw_R40_gap30_abcd/planes
python -m four_side_1024.fslw.plots --root outputs/four_side_1024_fslw_R40_gap30_abcd --all
```

## V3-Huang 同边 U 型/回折轮（2026-10-19）

`v3/` 包实现用户提供的 V3-Huang 1024 通道连接（same 448 / opposite 384 / adjacent 192）
在双高度真实 2×16 接口、R=40 mm 固定、30 µm 间距下的 ABCD 实验：同边规范帧
（四边旋转到 y=0，起向 +y 终向 −y）、同边族 `SAME_U` 与 `SAME_HAIRPIN_A/B`
（短 S + 相邻两段四分之一弧半圆回折）、A/B/C/D 调度（A 对边优先、B 同边优先、
C 四边轮流 batch=16、D 全局联合 + LNS）、独立 strict 校验器 `validate_v3.py`、
Phase-3 几何测试 `feasibility.py` 与类别隔离容量 `same_side_capacity.py`。
全部代码/报告/证据见 `outputs/four_side_1024_v3_huang_R40_gap30_abcd/` 与
`docs/reports/four_side_1024_v3_huang_R40_gap30_abcd.md`。
