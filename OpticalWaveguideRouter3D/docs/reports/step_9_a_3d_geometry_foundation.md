# Step 9-A：3D Geometry Model & Inter-Layer Transition Foundation

日期：2026-09-11。**PASS：三维几何基础完成，没有实现3D routing。**

## 1. Scope

二维阶段按本次指令冻结：ascending、exclusive track、guard OFF；原512条解析路径和318个multi保存结果不变。不继续M1.7、recovery、hierarchy、fragment或全量multi消除。

本Step仅扩展既有Point3D与Layer，新增独立三维primitive、Route3D和只读lifting。三维长度/坐标单位为mm，角度为radian。没有3D collision、layer assignment/optimization、1024 routing、loss优化、GUI、GDS、BPM或新依赖。合成fixture的z位置不是制造参数或建议层间距。

## 2. Existing 3D Model Audit

检查当前src/models.py、src/geometry.py、src/router_2d.py，并搜索src中的3D对象：

| 既有对象 | 原状态 | 本次处理 |
|---|---|---|
| Point3D(x,y,z) | dataclass字段，无finite/距离helper | 原类扩展，无重复定义 |
| Layer(id,z) | 仅保存层身份和物理Z | 保留构造参数，新增验证与layer_id/z_mm只读别名 |
| Route(waveguide_id,points) | 接受2D或3D点列表，非解析primitive容器 | 原样保留，不重新解释为Route3D |
| Board.layers | 保存Layer列表 | 不修改、不选择层 |
| Route3D | 不存在 | 独立新增 |
| visualize.plot_routes_3d | NotImplementedError占位 | 不修改、不实现绘图 |
| geometry.py | 2D Line/Arc、ordinary与special解析构造 | 原样复用 |
| router_2d.py | 正式二维分配/骨架生成 | 完全不修改 |

router_2d早期docstring仍有“模型注解限定Point3D”的历史说明，当前models.Route实际已支持2D/3D union。以实际代码为准，本次未因说明陈旧修改冻结allocator。

既有Point2D、Port、Waveguide、Route、LineSegment2D、ArcSegment2D、SmoothedRoute2D行为不改。models.py唯一增量为3D基础能力和模块说明。

## 3. Point3D

沿用Point3D(x,y,z)，构造调用validate()：拒绝NaN、±inf、bool和非int/float坐标。distance_to(other)使用math.hypot；不可表示的距离明确拒绝。is_close(other,tol=1e-9)使用以mm计的欧氏绝对容差，tol必须有限非负。

dataclass精确相等仍保留，不将==偷偷改成近似比较。原类保留可变性；validate/distance/is_close及新primitive操作会重新校验，不能认为构造检查后任意修改仍天然有效。

## 4. Layer

构造继续为Layer(id=...,z=...)，要求整数id与显式有限z；提供layer_id、z_mm属性。别名不另存一份值，避免不一致。

不提供默认z、不生成层表、不规定相邻层距离，允许调用者输入负或正有限坐标。fixture的1 mm或2.75 mm不代表生产层间距。Layer仅描述物理平面，不是二维hierarchy。

## 5. LineSegment3D

在src/geometry_3d.py独立实现，保存start/end Point3D，构造复制端点，拒绝零长度。

- length()：三维欧氏长度，mm。
- direction()：单位方向三元组。
- point_at(t)：线性插值，0≤t≤1，返回新Point3D。
- tangent_at(t)：d(position)/dt，非单位切向量。

允许一般空间直线，包括纯竖直LineSegment3D；这只是表示能力，不表示允许用竖直线替代受限的CosineTransition。后者有独立有限XY run要求。

## 6. PlanarArcSegment3D

为保留二维Arc，新增固定z解析圆弧，不实现任意方向空间Arc。

字段：center_x、center_y、z、radius、start_angle、sweep_angle。点为(center_x+r cosθ, center_y+r sinθ,z)，θ=start_angle+t·sweep_angle；tangent为(-r·sweep·sinθ,r·sweep·cosθ,0)；length=r·|sweep|。

radius必须正且有限；sweep沿现行2D支持域0<|sweep|≤π，保留正负方向。不加入full-circle或任意3D圆弧。

lifting保留二维圆心、从原start/center得到的radius和原sweep。内部另存原start/end的XY标量快照，使point_at(0/1)精确保留输入端点，不因atan2/cos/sin往返改变末位。中间位置仍为同一个解析圆，不做polyline近似。源Arc先经过现有2D校验，圆参数与端点遵循1e-9 mm几何容差。一般浮点输入不承诺每个中间计算逐bit相同；本次保存样本检查点误差实际为0。

## 7. CosineTransition3D

令Δx=x1−x0、Δy=y1−y0、Δz=z1−z0、Lxy=hypot(Δx,Δy)，t∈[0,1]：

```text
x(t) = x0 + t Δx
y(t) = y0 + t Δy
z(t) = z0 + (Δz/2) [1 − cos(πt)]
r'(t) = (Δx, Δy, (πΔz/2) sin(πt))
```

实现用等价sin²(πt/2)计算z比例，减少t接近0时的消减误差；t=.5明确取比例.5，两端返回原端点副本。tangent_at在t=0/1明确返回z分量0，避免sin(π)浮点尾差。上升/下降均支持，XY沿给定直线前进。

Δz=0抛ValueError("NOT_A_LAYER_TRANSITION")；Lxy=0且Δz≠0抛ValueError("INSUFFICIENT_TRANSITION_RUN")。不补水平长度、不自动转成竖直路径。所有point_at/tangent_at拒绝t越界、NaN、inf及bool。

端部z斜率为零只保证无突然的z方向斜率。与相邻层内primitive获得几何切向连续，还需要**XY切线同向对齐**。不同局部参数速度也不自动等于参数C1连续，本Step不声称曲率连续。

## 8. Paper-Derived vs Project-Specific Rules

本次任务提供的论文公式为cosine S-bend：
f(y)=Δx/2·[1−cos(πy/Δy)]，Reff=(Δy²+Δx²)/(4Δx)；
论文变量指横向中心距与纵向routing length。

**来源边界：PAPER FACT按用户提供的公式摘录归属；本Step没有重新核读论文原页，也没有补造页码或实验参数。** 没有从论文推导最佳层间距。

将原横向位移映射到|Δz|、纵向run映射到Lxy，并扩展任意XY方向，是明确的**PROJECT-SPECIFIC 3D模型**，不冒充论文原3D实现。

## 9. Effective Radius Indicator

Reff_3d=(Lxy²+Δz²)/(4|Δz|)，Δz≠0。

接口effective_radius_indicator()，单位mm。它仅是与提供的S-bend几何对应的工程指标，**不是真实minimum curvature radius，不是制造安全证书或换层接受阈值**。未计算曲率或用指标自动选长度/层距。

手算fixture：(0,0,0)→(10,0,1) mm；Lxy=10，Δz=1，中点(5,0,.5)，**Reff_3d=25.25 mm**。上升/下降同|Δz|得到相同指标；零Δz构造已拒绝，无除零路径。

## 10. Route3D

Route3D(route_id,primitives,continuity_tol=1e-9)与原Route独立。Primitive3D union只包括LineSegment3D、PlanarArcSegment3D、CosineTransition3D，为未来算法提供统一point/tangent/length数据接口，本轮不实现collision或routing。

构造将primitive序列深拷贝为tuple并验证类型、primitive有效性与相邻end/start三维欧氏连续性。超过容差抛DISCONTINUOUS_ROUTE_3D，不自动snap。默认验收是C0连接，不保证切向连续。

支持total_length()、start_point、end_point。空Route3D兼容原空SmoothedRoute2D：长度0、首尾None。总长用math.fsum；多transition时误差需考虑逐段累加，不把每段默认容差称作整个route统一误差上界。

新容器/primitive使用frozen dataclass，但复用Point3D仍可变，不宣称深层对象绝对不可变。防护是输入深拷贝、返回点副本、操作时重新validate；来源二维对象不与输出共享可变Point。

## 11. 2D-to-3D Lifting

lift_smoothed_route_to_layer(SmoothedRoute2D,Layer)先调用现有2D解析校验，再逐段映射：Line→LineSegment3D，Arc→PlanarArcSegment3D。route_id保留waveguide_id，primitive数量/顺序不变，只附加调用者输入的固定z。

直接读取outputs/step_8_5_legacy_512_plot_geometry.json，复用deserialize_plot。固定取各类保存ID最小的3条：ordinary 0/1/2，special-Z 13/14/15；选择不依赖multi或recovery。仅在内存映射到测试平面Layer(901,2.75)，不写入真实layer assignment。

| 类别 | route | Line / Arc | 2D长度(mm) | 3D长度(mm) |
|---|---:|---:|---:|---:|
| ordinary | 0 | 3 / 2 | 156.70796326794897 | 156.70796326794897 |
| ordinary | 1 | 3 / 2 | 156.70796326794897 | 156.70796326794897 |
| ordinary | 2 | 3 / 2 | 165.35796326794895 | 165.35796326794895 |
| special-Z | 13 | 2 / 2 | 150.76069504134688 | 150.76069504134688 |
| special-Z | 14 | 2 / 2 | 150.76069504134688 | 150.76069504134688 |
| special-Z | 15 | 2 / 2 | 150.76069504134688 | 150.76069504134688 |

六样本均通过：类型/数量/顺序一致，首尾XY精确相同，Arc radius/sweep相同，长度逐值相同；每primitive在t=0,.125,.25,.5,.75,.875,1检查XY，最大误差0 mm，z恒2.75。输入深拷贝比较不变，正式geometry文件SHA256读前后相同。

测试采样用于检查解析模型，不是用采样点替代正式geometry；保留圆参数与Line/Arc结构才是lifting表示。

## 12. Numerical Validation

Cosine长度来自速度积分：

```text
length = integral_0^1 sqrt(Lxy² + [(πΔz/2) sin(πt)]²) dt
```

采用标准库adaptive Simpson，默认abs_tol=1e-10 mm、rel_tol=1e-12、max_depth=20。用两半Simpson与整段差值/15估计局部误差，预算随递归平分，返回Richardson修正值。无效容差/深度拒绝；达到深度上限但未收敛抛TRANSITION_LENGTH_NOT_CONVERGED，不返回未验收估计。

这是可测试的数值误差估计，不是所有浮点尺度的形式化误差界。极端尺度可能不收敛或不可表示，明确失败；Δz非常小时“曲线长度大于弦长”的数学差可能低于浮点分辨率，不能要求所有近零fixture都显示正浮点差。

fixture结果：

- midpoint=(5,0,.5)，Reff_3d=25.25 mm。
- adaptive length=**10.061402544253308 mm**。
- chord=sqrt(101)=10.04987562112089 mm，长度严格更大。
- 独立composite midpoint积分n=32768：10.06140254425331 mm。
- 两方法差1.7763568394002505e-15 mm；是该fixture实测差，非全域保证。
- 两端导数均(10,0,0)，z分量精确0。

测试另覆盖|Δz|=.1/1/5/20长度单调增加，.1/1/10/100独立midpoint对照，上下行/XY旋转不变性、确定性、收紧容差、深度不足显式失败。未安装SciPy。

## 13. Tests

**545/545 PASS = 历史506 + 新增39，失败0。** 历史测试保持原样，使用既有venv及现有test_*函数方式，无新依赖。历史微型2D allocator fixtures照常回归，但没有新512布局或3D routing。

新增覆盖Point3D距离/finite/equality/tolerance/修改后重验；Layer旧参数及别名；Line长度/方向/插值/零长；各primitive非法t；cosine端点/中点/任意XY/升降单调性/零斜率/有限差分导数/零Δz/零run/指标；数值长度/弦长/单调性/独立积分/确定性/失败；Arc长度/固定z/顺逆方向/非法值；Route连接/断开/空route/未知类型/副本隔离；ordinary与special lifting、XY/length/圆结构/read-only及非法Layer拒绝。

复现入口（项目根目录）：

```powershell
.\.venv\Scripts\python.exe -B scripts/validate_3d_foundation.py . . outputs
```

第一参数为实现/测试根，第二个为保存二维geometry根，第三个为新审计输出目录；可在隔离副本上验证真实保存几何，无需allocator。输出step_9_a_tests.json及step_9_a_geometry_validation.json。

## 14. Remaining Limitations

- 真实minimum curvature radius尚未推导，Reff不能替代。
- 不决定layer spacing、层数、transition run制造下限或可制造性。
- 不实现curve-curve minimum distance、3D collision/clearance/multi。
- Route3D仅验证位置连续，任意连接不自动保证G1/C1/C2。
- 无任意空间Arc、Bezier、spline；planar arc用于准确承接二维解析几何。
- 无真实loss、trench/TOA-cos/BPM/TE-TM或插损拟合。
- 积分有有限精度/深度限制，数值长度不是制造测量值。
- 六保存样本不是512层分配，也没有消除318 multi。

## 15. Verdict / Files

**Step 9-A PASS。** 在原二维系统上建立独立三维解析表示，保持2D allocator、geometry kernel、输入和既有输出不变。Point3D/Layer在原类兼容扩展，无重复定义。

修改：src/models.py（仅3D类型能力和模块说明）。

新增：

- src/geometry_3d.py。
- tests/test_geometry_3d.py。
- scripts/validate_3d_foundation.py。
- docs/reports/step_9_a_3d_geometry_foundation.md。
- outputs/step_9_a_tests.json。
- outputs/step_9_a_geometry_validation.json。
- outputs/step_9_a_file_integrity.json。

文件完整性只允许原src/models.py发生本次已审查改动；所有其他既有src/tests/scripts/outputs/docs/config/data文件SHA256一致，正式router_2d.py及保存二维geometry包含在其中。

## 16. Recommended Next Step

建议 **Step 9-B：Cosine Transition Curvature & Tangent-Join Validation**。先独立推导真实曲率及minimum curvature radius、明确与Reff指标的差别，再验证给定输入下层内Line/PlanarArc与transition的切向连接条件与数值边界；不预设层间距，不以本Step指标自动决定routing。

本报告仅提出建议。**9-A完成后停止，不自行进入9-B、layer assignment或3D routing。**

