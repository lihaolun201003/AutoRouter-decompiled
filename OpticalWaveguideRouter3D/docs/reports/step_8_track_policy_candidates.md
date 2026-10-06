# Step 8 二维 baseline track policy 候选（待人工选择）

本文件只设计候选，不是已批准政策，不实施allocator、Route或任何优化。所有新增的边界、排序、复用、碰撞接受规则均为新项目工程约定候选，不声称恢复前代EXE。参考 step_8_legacy_track_assignment_audit.md、现有preparation及collision接口。

## 1. 可继承证据与候选参数
legacy 512实验：区域150×150 mm，宽w=0.05 mm，边缘间隔s=0.125 mm，pitch p=w+s=0.175 mm，实验半径r=5 mm。r必须参数化，5不是永久物理常数。
已确认论文类别次序：top U→bottom U→top-to-bottom Z→bottom-to-top Z；top U及两类Z按y下降扫描，bottom U按y上升。论文按内部起点x升序，但当前Excel方向不等于其内部方向。
当前Point2D/Route是无单位模型；本候选仅在显式声明snapshot坐标按mm解释的配置下使用上述数值，不进行隐式单位转换。

建议候选配置量：W,H,w,s,r,tol；可额外指定边界余量c（以下完整候选取c=r）、区间膨胀m（B/C以下取r+w/2）。均需用户确认。要求有限数，W,H,w,p>0，s,r,tol>=0，tol远小于p；边界以底0、顶H描述，可平移到显式bottom_y/top_y。

## 2. 两种坐标约定及明确网格公式

### G1：直接中心线网格（方案A、B）
h=w/2，L=c+h，U=H-c-h。
若L>U，无可用track。
N=floor((U-L)/p)+1，i=0,...,N-1。
track_y(i)=L+i*p，track origin=L，Route直接使用这个中心线y。
仅下界紧贴允许区，顶端可能保留不足一个pitch的额外余量；这是有意选定的候选锚定方式，不强行上下对称。
有效条件为L<=y<=U，等号允许；数学边界保留h，意味着预留中心线到物理上下边界至少c+h。
默认示例H=150,c=5,h=0.025：L=5.025,U=144.975，N=800，末track=144.85。不是857，也不追求匹配821。
上述margin只限制横向track，不要求边界上的输入Port本身离边界c+h，否则真实端点会全部非法。

### G2：条带底边网格，映射至中心线（方案C）
逻辑条带底边b(k)=k*p，k从0开始；条带为[b(k),b(k)+p]。
明确选择中心线y(k)=b(k)+p/2。注意这是新工程映射，不是论文已确认中心线偏移；不可混用w/2或直接b(k)。
仅保留完整条带k=0,...,floor(H/p)-1，再要求L<=y(k)<=U。
k_min=max(0,ceil((L-p/2)/p))；
k_max=min(floor(H/p)-1,floor((U-p/2)/p))。
若k_min>k_max则无track。公开track index仍从0开始：i=0,...,k_max-k_min，k=k_min+i，
track_y(i)=(k_min+i)*p+p/2。
示例k_min=29,k_max=827，共799条；首中心线5.1625，末144.8125，首有效条带底边5.075。
保留物理网格k和分配序号i的区别，不能将i*p当中心线坐标。
G2更像论文条带离散概念，但中心线偏移和完整末条带处理仍是新约定，不能称legacy-compatible。

### 取整与浮点共同候选
数学上采用上面的floor/ceil。实现时可将商在tol/p内接近整数的情况归整，再校验生成坐标在[L-tol,U+tol]；超过容差的track拒绝。tol是数值容差，不是额外物理间距。
G1更适合现有中心线模型：少一层映射且易测；G2适合将来需要保存条带区域的方案，但增加解释和边界测试负担。

## 3. 三套共用的方向、排序与扫描约定

为避免Excel行方向偶然影响分配，定义不修改Waveguide的algorithmic endpoint视图：
- U：左端为algorithmic start，右端为end；x相同以(pmt_id,port.id)升序决定，两端仍在原侧。
- Z：以两端(pmt_id,port.id)字典序较小者为algorithmic start，而不是直接取Excel start，也不是统一改成top start。该确定性选择保留两种Z方向且不依赖Excel方向；是纯工程规范，不赋予PMT ID几何意义。
- Z的top-to-bottom或bottom-to-top组按该algorithmic start所在侧决定。不能期待新分组数仍为原Excel144/144；正式实现时应报告两种计数。也不能冒称恢复了前代173/115。
- 分类顺序为top U、bottom U、algorithmic top-to-bottom Z、algorithmic bottom-to-top Z。
- 组内排序key=(algorithmic_start.x,algorithmic_end.x,algorithmic_start.pmt_id,algorithmic_end.pmt_id,waveguide.id)。最后ID唯一，保证多重边稳定。
- track扫描：top U、两类Z为N-1,...,0；bottom U为0,...,N-1。
- 不重新编号、不修改原始start/end；未来输出Route必须恢复原始端点方向。
- 三套均使用上述首次满足谓词的候选（first-fit）；明确这是我们选择的候选政策，不是从论文完整恢复。
- 三套均不加入类别结束后的整片区域永久封锁，仅依据具体占用记录；这是有意简化，偏离论文分区优化，必须在实验报告声明。

同PMT自连接、重合端点、重复Waveguide ID、非有限坐标、位置不在指定上下边界应预检失败，不通过不明确的规范化掩盖问题。x需在[h,W-h]内；对于y处于0/H的Port，其边界位置是合法接入面，不套用track的c+h限制。

## 4. special Z与普通两弯容纳范围
候选S1（A推荐搭配，B/C也可选）：若Z的dx=abs(xs-xe)<2r（考虑仅数值tol），返回unsupported_geometry，且不占用track。等于2r允许，允许未来规范化零长度中间直段；这是候选边界约定，不是复现EXE。
候选S2：仍允许分配一个诊断性track，但状态必须是assigned_unsupported_geometry，不允许生成可宣称普通两弯可行的Route，不计入成功路由数。诊断track单独记录，不进入可用路由occupancy，避免挤占支持的连接；该模式只是评估位置，不保证所有诊断track互相兼容。
S1失败更清晰、最少假设；S2可完整展示512需求的准备情况，但状态/统计更复杂。两种均不实现special Z。
对U也不能假装半径条件自动满足：若未来假设两个90°弯位于公共横段，dx>=2r同样是保守预检。可取失败unsupported_u_bend_span。若用户选择纯直角中心线实验，可去除此项，但必须标记“不保证圆滑可实现”，不能一面宣称r可行一面只检查Z。
本文件推荐比较A/B/C时统一用S1及上述U跨度预检，以便公平比较；这是待批准候选，不承诺512全部可布。

## 5. 方案A：独占track基线
使用G1；方向、排序、扫描同第3节。
occupancy：每个track为None或单个waveguide_id。
candidate acceptance：
1. 通过输入、跨度及几何支持预检；
2. i在有效范围，track满足边界；
3. occupancy[i]为空。
选择扫描序第一个满足者，成功后设置该track唯一owner。不同类别不可共享已占用track。
不做区间复用、K检查或弯曲相互作用推断。边界r余量不是所有曲线间clearance保证。
失败：预检给明确reason；无空track为no_available_track。
之后统一构造直角骨架并做全局collision验证（未来步骤，本次不执行），碰撞失败不暗中换track。
优点：最少策略、最易测试和解释；独占track仅避免同一y横段共享，不保证无touch/overlap或圆弧安全。
缺点：复用率低；相对于高密度优化较浪费。示例800个track大于512需求，所以不能把当前实例可能失败简单归因于track总量不足；跨度不支持、后验碰撞仍可能失败。更小区域、更大余量或更高数量时才会出现容量不足。

## 6. 方案B：同track区间复用
使用G1；方向、排序、扫描与A完全相同。
每根候选的原始水平投影I=[min(xs,xe),max(xs,xe)]，保守膨胀J=[I_left-m,I_right+m]，候选m=r+h。
occupancy[i]保存(waveguide_id,J)列表，端点方向不影响J。
不裁剪J到板边：J只是保守排斥足迹，可延伸出板外，不代表实际生成了板外路径；物理合法性由端点/track边界及后续几何验证单独判断。
candidate acceptance：
1. A的输入、跨度、边界条件；
2. 对该track的每个已有J'，要求J_right < J'_left-tol 或 J'_right < J_left-tol。
即膨胀闭区间接触也拒绝；不会把“不重叠”混成“允许相触”。
满足则first-fit插入；无候选为no_compatible_interval。
不检查邻track，m是可解释的保守工程代理，绝不是完整弯曲或多波导交叉证明。
最终统一collision验证所有Route；零宽检测不能验证w/s或圆弧，因此成功仅指中心线验证通过。
优点：易在A之上扩展，能利用远离的碎片；缺点：r膨胀可能过保守，跨track/竖段问题仍会后验失败。无测试前不能承诺利用率一定更优。

## 7. 方案C：条带映射与有限邻域复用（建议暂缓）
使用G2；同第3节顺序。occupancy仍为每track的(id,J)列表，另记录已接受端点和候选中心线骨架供未来谓词检查。
K=ceil((2r+w+s)/p)，r=5示例K=59。这是新项目保守邻域候选，不使用前代根号K公式，也不冒称层级约束复现。
candidate acceptance：
1. B的预检及同track膨胀区间不相接；
2. 对所有已有track j且0<abs(j-i)<=K，保守要求J与其全部J'不相接；
3. 未来构造候选直角骨架后，与全部已接受骨架进行collision谓词检查：拒绝touch/overlap和自身非相邻接触/重叠/交叉，允许两条不同Route的内部正交cross并记录。
前后检查包括数值上i两侧的全部已占用邻域，与处理时间先后无关；未处理需求不占据未来槽位。
K窗口只提供启发式保守过滤，不能证明窗口外长竖段安全，因此第3项仍检查全部已接受Route；这也增加实现成本。
无候选分别记录interval_blocked、neighbor_blocked或collision_blocked（可累计各拒绝数量）；不重排之前结果。
缺点：更多新假设、不同网格带来对比混杂、容易过度封锁并降低布通率；其优势仅是把更强几何检查提前，而非保证最优。属于明确的新策略，不建议为了“像前代”优先实施。

## 8. collision验证与成功语义
当前collision.py基于零宽直角中心线，cross、touch、overlap是几何关系，不是光学损耗或有限宽安全结论。
候选共同验收政策：
- 两根不同Route的内部正交cross允许但记录数量与位置；不计算crossing loss。
- touch及overlap拒绝；若未来允许共享物理端口，须单独明确例外，本方案不默认豁免。
- 非相邻自身cross/touch/overlap和相邻折返overlap拒绝；正常相邻拐点忽略。
A/B先完成候选track分配，再统一生成骨架并全量验证；C在每次候选阶段提前验证，最终仍全量复核。
A/B碰撞失败只返回validation_failed和相关ID，不自动避障、重路由或把失败当成功。track_assigned与route_validated必须区分。
尤其宽度、spacing、圆弧弯曲范围仍不在现有collision能力内，不能在报告写“通过完整物理clearance验证”。

## 9. 失败返回与确定性（共用候选）
未来结果建议保留原Waveguide.id、成功/失败状态、明确reason以及可选候选track；失败不造坐标。
按固定顺序尽力处理所有需求，失败项不占occupancy、不修改已成功项，返回partial结果及failed_ids；不静默丢失连接。输入配置非法则整批在分配前拒绝；需求自身非法单项失败。
后验collision阶段若A/B失败，保留诊断分配但将全批状态标为validation_failed；不宣称获得完整512布线。
无随机数，不用hash排序。正式实现需测试边界等号、浮点取整、正反向输入不变性、同x多重边、空pool、unsupported跨度、区间相触以及失败计数。
本次未设计或实现上述返回对象代码。

## 10. 比较
|项目|方案A|方案B|方案C|
|---|---|---|---|
|复杂度|低|中低|高|
|track利用率|每条最多一根|可复用，受m影响|可复用但K可能过度保守|
|前代相似度|简化整条占用思想|碎片思想，缺前代多交叉规则|邻域思想相似，公式仍是新定义|
|未确认/新约定数量|最少|增加m和复用谓词|增加K、邻域与提前几何检查|
|collision依赖|最终全局验收|最终全局验收|候选全局检查加最终复核|
|坐标模式|G1中心线|G1中心线|G2条带底边映射|
|special Z|推荐S1拒绝|推荐S1，S2可选诊断|推荐S1|
|失败可解释性|最高|较高|多种过滤相互作用|
|适合V0.1|推荐|可作下一比较实验|建议暂缓|
|未来3D|无层语义耦合|无层语义耦合|K仅二维邻track，绝非物理Z层|

## 11. 推荐意见（仅建议，等待人工选择）
【推荐用于第一个可运行512 baseline的方案】：A+G1+S1。
理由：最少未经验证的物理假设，最容易测试、复现及解释失败，为以后加入B提供清晰对照，不将二维条带当物理Z层。不承诺全部512得到物理可制造路由；“可运行”应指能够处理全部需求并诚实返回成功/失败。
最终仍需确认：方案与坐标模式、r/c/h边界、origin和取整、algorithmic start规范、排序平局、类别共享/屏蔽、first-fit、S1/S2及U跨度策略、m/K（如适用）、碰撞验收和部分失败策略。
本报告没有替用户选择最终方案，没有修改src/tests或实施下一阶段。
