# Step 9-B：Cosine Transition True Curvature & Tangent-Join Validation

日期：2026-09-11。**PASS。** 本Step仅完成当前cosine模型的真实曲率、显式半径反算和只读切向连接诊断。完成后停止。

## 1. Scope

正式二维baseline保持ascending + exclusive track + guard OFF，既有512 analytic routes与318 multi保存结果冻结。不返回M1.7，不做二维recovery、hierarchy或fragment。

不选择layer spacing、layer assignment、制造半径阈值，不做3D collision/clearance/multi、1024 routing、loss fitting、TOA-cos trench、BPM、GUI或GDS，不安装依赖。

## 2. Current 3D Model

已核读当前src/geometry_3d.py、9-A正式报告与保存验证输出。9-A包含Point3D、Layer、LineSegment3D、PlanarArcSegment3D、CosineTransition3D、Route3D及解析lifting；历史545项测试。

本次仅向CosineTransition3D增加4个曲率查询方法；新建src/geometry_3d_diagnostics.py放置纯数学反算和显式join诊断。既有point_at、tangent_at、length、effective_radius_indicator及Route3D默认构造/连续性语义不变。

对修改前后语法树核对：从新版移除4个新增方法后，与原geometry_3d.py的AST完全一致。证据见outputs/step_9_b_model_preservation.json。这包含所有既有类、字段、方法、lifting及Reff接口，不仅比较采样点。

## 3. Analytical Curvature Derivation

**PROJECT-SPECIFIC TRUE CURVATURE OF CURRENT COSINE MODEL。** 以下是从当前工程定义推导，不是论文直接给出的3D曲率公式。

设L=Lxy>0，h=Δz≠0，e=(Δx/L,Δy/L,0)为单位XY chord方向。令水平投影弧长s=Lt，0≤s≤L。注意s是水平弧长，不是整条空间曲线的弧长。

r(s)=(x0,y0,z0)+s e+[z(s)−z0](0,0,1)，因此曲线始终位于e与Z方向张成的固定竖直平面内。

```text
z(s) = z0 + h/2 · [1 − cos(πs/L)]
z'(s) = πh/(2L) · sin(πs/L)
z''(s) = π²h/(2L²) · cos(πs/L)

r'(s) = (e_x, e_y, z'(s))
r''(s) = (0, 0, z''(s))
|r' × r''| = |z''|, because e_x²+e_y²=1
|r'|³ = [1+z'²]^(3/2)

κ(s) = |z''(s)| / [1+z'(s)²]^(3/2)
     = [π²|h|/(2L²)] |cos(πs/L)|
       / {1+[πh/(2L)]² sin²(πs/L)}^(3/2)
```

κ单位1/mm；用t查询时只需将πs/L换成πt，不能额外再除一次L。

代码curvature_at(t)使用解析公式，不调用采样或有限差分。数值上以hypot(1,slope)计算分母基数，连续除三次以避免直接立方带来的不必要溢出。关于t=.5反射计算有助于对称性；没有修改9-A的任何几何求值。

## 4. Maximum Curvature

令A=π²|h|/(2L²)>0，B=π|h|/(2L)>0。对所有s∈[0,L]：

1. |cos(πs/L)|≤1；
2. [1+B²sin²(πs/L)]^(3/2)≥1；
3. 所以κ(s)≤A。
4. s=0和s=L时sin=0且|cos|=1，两个不等式同时取等，故两端均达到A。
5. 对严格内部s∈(0,L)，|cos|<1，κ<A，因此只有两个端点达到最大值。

由此解析证明：

**κ_max=π²|Δz|/(2Lxy²)，最大值位置s=0、Lxy。**

端点值也等于从曲线内部逼近的单侧极限。采样最大值测试只是回归证据，不代替上述证明。

## 5. Minimum Radius

定义局部R(s)=1/κ(s)（κ>0）；曲率为0时R=+∞。当前模型的最小曲率半径：

**R_min=1/κ_max=2Lxy²/(π²|Δz|)。**

新增接口明确分离：

| 接口 | 含义 | 单位 |
|---|---|---|
| curvature_at(t) | 当前位置真实曲率κ | 1/mm |
| radius_of_curvature_at(t) | 局部曲率半径R | mm |
| max_curvature() | 全transition最大曲率κ_max | 1/mm |
| minimum_curvature_radius() | 全transition最小半径R_min | mm |

t=.5为唯一内部零曲率点，API精确返回curvature_at(.5)=0.0、radius_of_curvature_at(.5)=math.inf，不返回人为巨大有限数。JSON审计文件用字符串"Infinity"表示无穷，避免非标准JSON Infinity；Python API返回真正浮点无穷。

t越界、NaN、inf、bool沿用明确拒绝语义。Δz=0、Lxy=0沿9-A构造规则拒绝。可变Point被非法修改后重新validate。非零曲率在极端尺度下不可有限表示或下溢为0时明确拒绝，不把数值下溢谎报为真实零曲率。

## 6. Reff vs True Radius

既有effective_radius_indicator保留：

Reff_3d=(L²+h²)/(4|h|)，仍为paper-inspired engineering indicator。

新R_min是本工程cosine模型的真实解析曲率结果；两者不可混用。进一步比较：

**Reff_3d/R_min=(π²/8)[1+(h/L)²] > 1**（π²/8>1）。

因此对本模型合法输入，Reff总大于R_min；不能使用Reff代替真实半径判断曲率要求。

fixture start=(0,0,0)，end=(10,0,1)：

| 指标 | 数值 |
|---|---:|
| Lxy / Δz | 10 / 1 mm |
| κ_max=π²/200 | 0.049348022005446794 1/mm |
| R_min=200/π² | 20.264236728467555 mm |
| Reff_3d | 25.25 mm |
| Reff/R_min | 1.2460375556375314 |

这些是几何数值，不是损耗或制造可行性结论。论文cosine S-bend及曲率变化/mode mismatch背景按本次用户提供的说明归属；本轮未重新核读论文原页、未补造引用页码。3D z映射、以上R_min以及下述C1/C2解释均为PROJECT-SPECIFIC derivation。

## 7. Numerical Verification

独立验证只调用point_at，使用三维五点有限差分得到r_t'、r_t''，再计算|r_t'×r_t''|/|r_t'|³。不调用解析tangent_at、curvature_at或max_curvature求数值参考。

内部点使用中心模板；端点使用区间内单侧模板，绝不越出t∈[0,1]。右端反向参数的方向符号不影响曲率模。步长h_t=.001，另记录.0005对照；步长无量纲，不是几何容差。

| t | 解析κ (1/mm) | 独立数值κ (1/mm) | 绝对误差 |
|---:|---:|---:|---:|
| 0 | .049348022005446794 | .049348022011802654 | 6.356e-12 |
| .1 | .04676737356269076 | .046767373562814504 | 1.237e-13 |
| .25 | .03425840056569086 | .03425840056489707 | 7.938e-13 |
| .5 | 0 | 8.027732847833864e-13 | 8.028e-13 |
| .75 | .03425840056569086 | .03425840056846183 | 2.771e-12 |
| .9 | .04676737356269077 | .04676737356445018 | 1.759e-12 |
| 1 | .049348022005446794 | .04934802200795968 | 2.513e-12 |

fixture最大误差6.3558602825253274e-12 1/mm。单元测试还对下降Δz和旋转/平移XY的曲线逐个检查这7个t，采用明确绝对容差2e-7 1/mm，全部通过。该容差是测试验收，不控制正式曲率值。

减半步长不保证误差处处更小：二阶差分会放大浮点舍入，t=1时半步长结果差约6.63e-11，仍远低于测试容差。不把有限差分误差宣传成解析实现误差界或制造精度。

## 8. Tangent Join Definition

独立validate_tangent_join_3d(A,B)先校验支持的primitive及端点，再验证三维端点距离≤position_tol。默认position_tol=1e-9 mm。

位置连续时，取vA=A.tangent_at(1)、vB=B.tangent_at(0)，归一化得到uA、uB。计算dot与angle=atan2(|uA×uB|,uA·uB)。相对acos，atan2可更稳定区分非常小的角度。dot限制在[-1,1]仅修复浮点尾差，不能用abs(dot)把反向当同向。

默认angle_tol=1e-9 rad，angle≤angle_tol才通过。输入角容差必须0≤tol<π/2，位置容差必须有限非负；这些是显式数值检查参数，不是制造规则。无效容差抛ValueError，不误标为primitive错误。

JoinValidation3D包含position_continuous、tangent_continuous、dot_product、angle_rad、status，另有position_gap_mm、direction_status和detail：

| status | 含义 |
|---|---|
| C0_C1_PASS | 位置连续且单位切向同向，direction_status=C1_DIRECTION_CONTINUOUS |
| POSITION_DISCONTINUOUS | 端点距离超容差；不继续计算方向，dot/angle为None |
| TANGENT_DIRECTION_MISMATCH | C0通过但切向角超容差，包括反向π |
| ZERO_TANGENT | C0通过，但有限切向量范数为0，无法归一化 |
| INVALID_PRIMITIVE | 不支持类型、无效几何或非法切向量 |

正常9-A primitive已排除零长度/非法transition，因此ZERO_TANGENT是防御路径。测试用有效line配故意损坏的切向provider覆盖，不将零长line作为合法几何放行。非有限切向量返回INVALID_PRIMITIVE。

## 9. Line-Transition Join

cosine端点解析r_t'=(Δx,Δy,0)，归一化为(e_x,e_y,0)，两端同向；上升/下降不改变这个端点XY方向。

固定transition(0,0,0)→(10,0,1)，所有下表incoming线都终止于(0,0,0)：

| Line start | C0 | dot | angle | 结果 |
|---|---|---:|---:|---|
| (-2,0,0) | PASS | 1 | 0 | C0_C1_PASS |
| (0,-2,0) | PASS | 0 | π/2 | TANGENT_DIRECTION_MISMATCH |
| (2,0,0) | PASS | -1 | π | TANGENT_DIRECTION_MISMATCH |

另外测试Line→Transition→Line两个join均通过，并验证一般XY chord(6,8)的两端导数均(6,8,0)。不是只有x轴特例有效。

## 10. Arc-Transition Join

PlanarArc的signed sweep决定有向切线，不能只依据圆心或共点判定：

| Arc参数（z=0,r=1） | 接点 | 末端切向 | C0 / 方向结果 |
|---|---|---|---|
| center=(0,1), start=-π, sweep=π/2 | 约(0,0,0) | +X | PASS / PASS |
| center=(-1,0), start=-π/2, sweep=π/2 | (0,0,0) | +Y | PASS / FAIL |

第一例三角函数造成约6.123e-17 mm端点差、约6.123e-17 rad夹角，在明确容差内通过。第二例端点相同但夹角π/2。两例都可按原Route3D C0语义构造；高等级检查才区分切向。没有改变圆弧或吸附端点。

## 11. Route3D Join Audit

新增只读analyze_route3d_joins(route)，返回RouteJoinAnalysis3D：route_id、按顺序排列的joins、all_C0、all_C1_direction。joins[i]对应primitive i→i+1。默认沿用route.continuity_tol，角容差可显式提供。

不改变Route3D.__post_init__或validate，不把切向检查隐式插入构造。既有C0通过但C1失败的route仍允许表示，并得到明确诊断。

因9-A端点类型保留可变性，route构造后若被外部改坏，helper逐join报告不连续，不提前调用route.validate把诊断变成异常。空route或单primitive无join时两个all按空集真返回；这是join汇总约定，不是整条route所有primitive有效性的认证。

真实结果包含同向line、垂直line、反向line、同向arc、不匹配arc五个构型；前者和同向arc的all_C0/all_C1_direction均True，其余为True/False。正常/损坏路径诊断均无输入写入，深拷贝比较通过。不扫描512个route、不做layer assignment。

## 12. C1 vs Curvature Continuity

本项目C1_DIRECTION_CONTINUOUS专指**单位切向同向（几何G1）**。它不验证本地参数t的导数大小一致。例如2 mm incoming line导数(2,0,0)，10 mm水平run的transition端部导数(10,0,0)，归一化方向一致但原参数导数不同，不能称同一参数化下严格C1。

即使调整参数速度使一阶连接一致，straight line曲率为0，而cosine端点曲率为κ_max>0，因此Line→Cosine的曲率从0跳到κ_max，**不具备曲率连续性，也不应声称C2连接**。

Arc→Transition即使方向连续，也不自动曲率连续：不仅要比较曲率大小，还涉及曲率向量方向，planar arc和竖直平面transition的弯曲方向一般不同。本Step不实现C2诊断或改曲线来消除跳变。

z slope=0绝不等于“完全平滑无损”。论文所述曲率变化/mode mismatch仅作为用户提供的物理背景；本Step不计算真实mode mismatch loss，不拟合损耗。

## 13. Required XY Run Inversion

调用者显式给定R_required>0，固定|Δz|>0：

R_min≥R_required
⇔ 2Lxy²/(π²|Δz|)≥R_required
⇔ **Lxy≥π sqrt(R_required·|Δz|/2)**。

minimum_xy_run_for_radius(delta_z,required_radius)返回边界值，无默认半径。Δz=0明确NOT_A_LAYER_TRANSITION；非正required_radius、NaN、inf、bool拒绝；符号仅通过|Δz|处理。未内置5 mm、2.5 mm或任何layer_pitch。

fixture R_required=200/π² mm、Δz=1 mm，返回Lxy=10.0 mm。多个显式radius和正负Δz测试回代R_min等于required_radius（浮点容差内），增加run则R_min更大。helper只返回数学量，不修改geometry、不自动建transition、不声称满足制造规范。

## 14. Tests

**579/579 PASS = 历史545 + 新增34，失败0。** 旧测试文件全部未修改，标准库和既有venv，无新依赖。

覆盖端点/中点/对称/Δz正负/XY旋转曲率、手算R_min、Reff保留且不同、局部半径倒数/无穷、采样最大值回归、三类曲线point-only数值交叉验证、非法t/可变输入重验、反算手算/回代/显式参数/非法值、Line同向/垂直/反向、Arc同向/不匹配、位置不连续、ZERO_TANGENT、非法primitive/切向量、容差和小角度边界、全route join、只读、空join约定、构造后损坏的route、G1与参数C1区别。

另核对9-A全部既有AST不变（新增4个方法除外）。旧9-A lifting回归复查仍保持六保存样本结构、XY和长度，输出仅在工作验证目录，没有覆盖正式9-A结果。

复现（项目根目录）：

```powershell
.\.venv\Scripts\python.exe -B scripts/validate_cosine_curvature.py . outputs
```

输出step_9_b_tests.json及step_9_b_curvature_join_validation.json。数值参考位于新增测试模块，仅验证工具使用；正式curvature接口不依赖测试或数值差分。

## 15. Limitations

- 结果严格针对当前固定cosine几何，不推广为任意S-bend/3D spline公式。
- Reff保留为paper-inspired指标，不替代R_min或制造标准。
- 数值有限差分是交叉验证，不是生产曲率计算，不证明任意尺度的浮点误差上界。
- 不解决曲率跳变或物理mode mismatch，不声称无损。
- 只验证单位切向方向；不自动重参数化，不提供C2保证。
- 不决定layer spacing、半径门槛、run空间可放置性、collision或layer assignment。
- 无层优化、3D multi、1024 routing；正式二维baseline没有变化。

## 16. Verdict / Deliverables

**Step 9-B PASS。** 真实曲率完成解析证明与实现；独立数值交叉验证通过；显式Line/Arc/Transition切向与route级诊断完成；9-A几何和默认C0语义保持。

修改：src/geometry_3d.py，仅新增四个cosine曲率方法。

新增：

- src/geometry_3d_diagnostics.py。
- tests/test_geometry_3d_curvature.py。
- scripts/validate_cosine_curvature.py。
- docs/reports/step_9_b_cosine_curvature_tangent_validation.md。
- outputs/step_9_b_tests.json。
- outputs/step_9_b_curvature_join_validation.json。
- outputs/step_9_b_model_preservation.json。
- outputs/step_9_b_file_integrity.json。

文件检查仅允许原geometry_3d.py发生本次扩展；models.py、router_2d.py、所有既有二维实现/测试/报告/保存输出不变，哈希清单见file_integrity。

## 17. Recommended Next Step

建议 **Step 9-C：3D几何距离与碰撞判据设计**，先明确primitive对的数学距离接口、数值容差及验收证据，再界定后续实现范围。制造clearance等参数应由调用者明确提供，不能由当前层间模型或二维radius自动推定。

本Step不实现上述内容。**9-B完成后停止，不自行进入9-C或任何layer assignment/routing。**
