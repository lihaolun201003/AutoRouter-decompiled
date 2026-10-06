# Step 8.5-A special Z与圆弧路径表示方案审计

## 1. 范围与当前实现
本次只生成架构报告，未修改src/tests、454条Route或track。
已检查models、geometry、router_2d、collision、loss、export、visualize源码。相关测试已有206项回归结果；此次设计审计不声称重新运行测试。
Route.points为list[Point2D]或list[Point3D]。geometry只生成轴对齐骨架；special Z明确未实现。Router已有分配和骨架生成分层。collision只接受轴对齐线段；loss使用明确物理单位的数值参数；export/visualize仍是NotImplementedError占位。
router_2d原有docstring仍有“模型限定Point3D”的过时说明，今后允许改代码时应清理；本次未改。
论文证据使用此前视觉核对的正文第12页（PDF17页）式3-7～3-9、正文第10～11页直段后添弯流程；不将EXE未知实现补成事实。

## 2. Route.points限制
点列表精确表达折线顶点，却不表达相邻点之间应该走直线还是圆弧、圆心、半径、绕向及扫角。仅凭圆弧两个端点不能唯一确定曲线；同端点存在无数圆弧。
有限点样本加“按直线连接”的现有语义只能近似圆弧，不能精确保存固定曲率。即使三个点可在非共线情况下拟合圆，也没有弧段分界、方向及大/小弧约定，不能无损重建完整复合路径。
所谓精确表示指保存解析几何参数，不是宣称浮点运算没有误差。

## 3. 三套候选
|项目|A 点列表采样|B 替换为显式segment路径|C 骨架与精确geometry并存|
|---|---|---|---|
|核心|圆弧离散点接折线|所有路径直接用line/arc段|保留Route，另有SmoothedRoute2D|
|修改范围|模型少，但消费模块必须改|现有Router/测试接口迁移较大|增加独立结果，旧链可保留|
|圆弧精确性|没有，依采样误差|解析参数|解析参数|
|碰撞|现有轴对齐检测仍不能接收斜弦|新增line/arc检测|旧骨架检测与新精确检测分开|
|损耗|长度偏短、弯曲信息丢失|直接读取半径扫角|直接读取半径扫角|
|显示/输出|直接折线但精度依赖采样|边界适配时离散|边界适配时离散|
|结论|适合派生预览，不作最终核心|适合新起项目，当前迁移较重|推荐|

A：可按最大弦高误差epsilon定义采样，单段扫角上限2*acos(1-epsilon/r)，片数ceil(abs(sweep)/上限)，需处理r、epsilon定义域；这只是未来适配策略。采样误差影响长度、切线、交点及相触判断，不能沿用当前碰撞结果。
GDS并非一定要恢复圆弧才能写出：可以按公差输出多边形/折线近似。保留精确源几何的价值是避免从低精度样本反推圆弧，而非假设GDS一定原生保存理想圆弧。

## 4. 推荐最小结构：C采用B的段表示
建议后续在models.py新增三个简单dataclass，不改变现有Route：
- LineSegment2D：start: Point2D，end: Point2D。
- ArcSegment2D：start: Point2D，end: Point2D，center: Point2D，sweep_rad: float。
- SmoothedRoute2D：waveguide_id: int，segments: list[LineSegment2D | ArcSegment2D]。
半径由norm(start-center)唯一得到；不用再存radius、clockwise以免重复状态不一致。sweep_rad的正负同时表示方向：标准x向右/y向上，正逆时针、负顺时针。扫角绝对值是弯曲角。若选择显式radius字段也可，但必须校验与两端半径一致；不推荐两套真值。
初版约定r>0，0<abs(sweep_rad)<=pi；足以覆盖本轮quarter-circle和两个小于90度的special Z圆弧，不支持整圆/多圈。有限值、两端半径相等、旋转start半径向量后到end、段首尾连续都需验证。
结构不含loss、物理plane层级、track分配状态或隐藏单位。合法性验证放geometry函数，保持数据类简单。
以waveguide_id对应已有Route和Waveguide，一份结果集合内ID唯一。不要让SmoothedRoute2D成为可随意脱离骨架版本的长期缓存：骨架/参数改变时显式重新生成。
special Z没有普通四点骨架可被独立圆角化；可以直接由原端点、显式yh和r构造同一种SmoothedRoute2D。不要伪造一个已通过普通Z骨架验证的Route来挂接它。
当前58项根本没有track；数学表示完善不等于已获得yh，不能直接沿用空assignment。

## 5. 对模块与测试的影响
- router_2d：route_waveguide_2d和generate_assigned_routes_2d继续返回原Route骨架。新增精确几何转换是独立调用，不悄悄更换返回类型。special Z未来需要单独授权的支持状态与track政策变更。
- geometry：初期把解析段校验、长度、90度圆角及专用special Z构造放在现有geometry.py，复用Point2D；若变大再拆geometry_2d，不预先搭建类层级。建议接口smooth_orthogonal_route_2d(route,radius,tol)->SmoothedRoute2D；build_special_z_geometry_2d(waveguide_id,start,end,reference_y,radius,tol)->SmoothedRoute2D。本次仅接口建议。
- collision：保留当前轴对齐API语义，新增精确几何入口而非把Arc采样偷偷交给旧函数。line-line须处理任意方向；line-arc为直线/圆交点再过滤线段参数与有向扫角；arc-arc为两圆交点后过滤扫角，另处理同圆弧区间重叠、相切和接点。复用结果表达，但必须重新定义曲线相切与横穿的kind、容差及正常相邻连接豁免。旧cross数47292不等于圆滑后cross数。
- loss：直线L=norm(end-start)，圆弧L=r*abs(sweep_rad)。总长度再显式转length_cm；半径再转radius_mm、角度转degree调用现有bend_loss。几何单位仍不绑定mm。扫角给定真实弯曲量，比从采样点反算可靠。现有L90*r角度比例是候选模型，不新增实验数据。缺crossing loss时不得称完整总损耗。
- visualize：精确弧可用绘图后端弧元或按误差采样，方向和等比例坐标需保留；暂不实现。
- export：JSON可保存解析参数；GDS适配层未来负责宽度轮廓、弦高公差和量化。精确几何不替代制造规则，也不要求现在选定导出库。
- 3D：保留现有Point3D Route；新类型明确2D。将来3D圆弧可独立保存平面基/法向，不能将当前xy有符号扫角直接当任意3D弧，也不能假设XY/XZ/YZ损耗相同。本轮不添加plane字段。
- 测试：保留206项作为骨架回归；新增解析段连续性、半径、切线、长度、镜像/反向、退化与不可行用例。旧“碰撞有效”标签只属于原骨架，不能继承给平滑结果。

## 6. special Z数学证据与关键疑点
【已确认】论文文字描述横向距离不足两个弯曲半径时使用对称弯曲，圆滑后无普通水平直段。式3-7 theta=acos((r-dx/2)/r)，式3-8 xc=(xs+xt)/2，式3-9 yc=yh±r*sin(theta)；论文将这些作为圆心相关坐标描述。
【已确认】当前58项由dx<2r的保守policy拒绝，不代表仅补这三式就能生成合格路径。
【可以数学推导】对r>0、0<dx<2r，theta∈(0,pi/2)，h=r*sin(theta)=sqrt(r*dx-dx²/4)。可以构造与竖直端部相切的对称双弧S连接。
【仍未确认】论文xc是否存在符号/表述省略：若把两个圆心都放在x=(xs+xt)/2、y=yh±h，则两圆心距2h<2r；一般不能得到两不同圆在中心连接处的相切连接，且竖直直段相切要求圆心x距该直段为r。这与直接照抄“两个圆心共享xc”的解释不一致。不能悄悄把式3-8改写后声称完全复现论文/EXE。

### 一个明确带假设的自洽数学构造（非已确认EXE实现）
设端点为S=(xs,ys)、T=(xt,yt)，横向符号e=sign(xt-xs)，纵向行进符号q=sign(yt-ys)。假设两端接竖直直段、两圆弧等半径、在M=((xs+xt)/2,yh)相切连接、整体y单调。
切点A=(xs,yh-q*h)，B=(xt,yh+q*h)；
圆心C1=(xs+e*r,yh-q*h)，C2=(xt-e*r,yh+q*h)。
验证norm(M-C1)=norm(M-C2)=r；C2-M=-(C1-M)，两弧可在M同向相切。
第一弧有向扫角=-e*q*theta，第二弧=+e*q*theta。路径为S→A直线、A→M圆弧、M→B圆弧、B→T直线；零长端直段可省略，无水平直段。
S→A及B→T方向均为q的竖直方向；M处共同单位切向量为(e*sin(theta),q*cos(theta))。
要求q*(yh-ys)>=h以及q*(yt-yh)>=h。否则给定参考y无法容纳，必须返回unsupported/不合法，不自动换track。
其中上下圆心符号由q控制，横向圆心偏移由e控制，扫角由e*q控制；反转路径须交换端点与段顺序并反转扫角，不能只改一个±。
【可以数学推导】dx趋近2r时theta趋近pi/2，双弧连接可退化为普通Z零长水平段；dx=0时theta=0，两弧退化，可能应成为纯竖直直线，但这属于需明确的新工程边界处理，不能未经授权补入special Z。
【仍未确认】EXE实际如何用yh、是否与这里的连接中点一致、上下符号与原始方向的具体约定、track占用范围和等号/退化处理。建议将这一自洽构造标记为新项目二维数学模型，先验证再采用，不宣称修复了前代公式。
因此数学上足以设计一个受限、可测试的双弧构造；尚不足以无条件恢复前代完整special Z实现。

## 7. 普通U/Z圆角化
对非退化90度拐角B，前点A、后点D：
u=(B-A)/norm(B-A)，v=(D-B)/norm(D-B)，要求u·v=0。
入切点P=B-r*u；出切点Q=B+r*v；圆心C=B-r*u+r*v。
从P到Q的扫角为sign(cross(u,v))*pi/2。原端点不改变，用P→Q圆弧替代拐角。
单拐角两侧各需要至少r；整条路径必须累计每段两端的截短量：
- 只有一端圆角的段：长度>=r；
- 两端均为半径r圆角的中间段：长度>=2r；
- 不等半径时长度>=r_left+r_right。
等号可产生零长直段，省略该直段后仍须检查相邻弧连续且切向一致；不允许圆角互相越过。180度折返不是90度圆角，单独拒绝。
圆滑单个90度弯后长度减少2r、增加pi*r/2；两个90度弯的长度改变为-4r+pi*r（仅在两弯合法时）。
当前allocator检查dx>=2r并将track与边界隔开r+w/2，有利于普通两弯条件，但几何模块仍须独立检查，不能把assigned视为所有新几何参数下都可行。
失败建议返回明确几何不可行原因，不减少半径、不挪track、不自动退回锐角。为未来batch单项失败保留结构，别把部分成功描述为完整512。

## 8. 最终推荐与最小模型变化
【推荐Step 8.5后续采用：方案C——保留骨架Route，新增由显式LineSegment2D/ArcSegment2D组成的SmoothedRoute2D。】
无需修改现有Route、Point2D、Port、Layer字段。推荐后续仅向models.py添加上述三个小dataclass；计算与校验放geometry。可以另放geometry数据模块避免models增长，但首版集中三个类型更易理解，无须继承/Protocol/泛型。
waveguide_id是原需求与新旧结果对应键；原454骨架及其验证报告保留。精确几何必须单独验证，58项的track处理须之后明确，不因架构设计自动释放unsupported状态。

## 9. 建议Step 8.5内部顺序（本次只完成A）
1. 8.5-A：本架构审计，确认论文公式疑点与采用的数学约定。
2. 8.5-B：最小line/arc模型、解析校验、长度与普通90度圆角化，保留骨架回归。
3. 8.5-C：special Z受限构造及镜像/反向/退化/不可行测试，明确yh语义；不擅自批量改track。
4. 8.5-D：独立精确line/arc中心线交互检测，重新规定相切/交叉与正常连接，验证平滑路径。
5. 8.5-E：经单独批准衔接unsupported需求的准备/track政策，复跑512精确几何和检测，诚实报告失败。
6. 8.5-F：显式单位下接入已知长度/弯曲损耗并规划显示/导出适配；未知crossing loss仍未实现，不声称完整光学损耗。

本轮只保存本报告，不实现Arc、special Z或上述后续工作。
