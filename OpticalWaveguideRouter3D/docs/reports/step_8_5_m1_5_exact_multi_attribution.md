# Step 8.5-M1.5：Exact Multi Spatial / Segment Attribution Audit

日期：2026-09-11。**M1.5：PASS。** 正式ascending baseline的318个legacy-eligible multi已完成全部954行physical CROSS归因。原有路由、交点集合及算法不变。

## 1. Scope

本轮取消优先恢复论文终止端/危险侧的路线，直接对保存的真实Line/Arc几何做事后审计。没有调用allocator，没有重做Step L descending partial routing，没有K、hierarchy、fragment、hard guard或reroute实现。

新增文件：

- src/multi_attribution.py：只读primitive/物理端点归因、PMT几何关系和事后构型标签。
- scripts/audit_multi_attribution.py：读取已保存正式结果，生成新统计、CSV与SVG。
- scripts/render_multi_attribution.ps1：使用Windows现有System.Drawing生成PNG预览，不安装依赖。
- tests/test_multi_attribution.py：29项新增测试。
- 本报告及outputs/step_8_5_m1_5_*专用输出。

PAPER FACT依据Step M直接核读的本科论文正文14页（PDF物理19页）3.2.1：三条波导两两交点聚集，至少两条三角形边短于间距；局部说明涉及横向段、终止端弯曲及相邻PMT纵向段。本报告的物理归属/构型标签均为**PROJECT-SPECIFIC post-hoc diagnostic**，不冒充论文形式化充分必要定理。

## 2. Baseline与证据链

| 项目 | 本轮使用值 |
|---|---|
| 正式策略 | ascending / exclusive A / guard OFF |
| width / spacing / pitch / radius | 0.05 / 0.125 / 0.175 / 5 mm |
| 解析路径 | 512=454 ordinary+58 special-Z |
| 保存的全局unordered pair验证覆盖 | 130,816 |
| physical CROSS事件 | 55,935 |
| 有CROSS的route pairs | 49,502 |
| legacy-eligible multi | 318 |
| 主集之外boundary triangle | 2，独立保留 |
| outside-single-cross-assumption triangles | 841,477，独立保留 |
| 归因行数 | 954=3×318 |
| 主集涉及的唯一physical route pairs | 798；同一pair可在不同triplet中重复计数 |

直接读取：

- outputs/step_8_5_legacy_512_plot_geometry.json。
- outputs/step_8_5_legacy_512_exact_events.jsonl。
- outputs/step_8_5_legacy_512_physical_events.jsonl。
- outputs/step_8_5_legacy_512_multi_crossings.jsonl及其summary。
- 既有physical/loss summary、top_u_order_ab_summary用于验证输入哈希与ascending control身份。
- 原始fiberBoard512.xlsx、fiberBoard0data.xlsx仅只读加载端点身份与PMT坐标。

Control配置明确为ascending；physical事件SHA256同时匹配既有multi、loss、A/B control记录。已有审计覆盖130,816对，本轮复用，不再重复全pair求交。plot JSON的圆心、半径、起角、sweep只是反序列化为Arc对象，不重新选track或生成路由。

每个保存raw交点均检查属于它所引用的两条保存primitive；全部512 primitive chains与真实端点连接一致。318个triplet逐个调用**现有**classify_multi_crossing确认原分类和三边长度完全一致；三个保存point与对应physical事件坐标逐值相同。没有重新consolidate或改变代表坐标。

## 3. Attribution Method

1. 根据保存route ID关联Waveguide/Port；类别标签沿用当前工程，但不使用算法起终点决定物理左右。
2. 从两真实端点建立无分支primitive chain；根据端点坐标连接逐段追踪，索引只用来记录来源。
3. 用保存raw事件的segment_index与physical CROSS位置关联。
4. 额外检查交点实际属于哪些Line/Arc；若位于join，保留全部成员，不任意选一个。
5. 对主集而言，954行全部具有唯一primitive_a、primitive_b；不存在join归因歧义。
6. 每triplet保存三个cross、重心、bbox、三条边、每route两次primitive参与明细及canonical signature。

CSV定义：

- multi_triplets.csv：一行一个triplet；包含route_categories、pmt_pairs、endpoints、centroid、bounding_box、side_lengths_mm、per_route_crossings、空间标签及paper标签。
- multi_crosses.csv：一行一个triplet内physical cross，包含要求的route、坐标、primitive类型/index/orientation/owner字段，以及完整Arc参数和PMT关系。
- summary.json：总数、类别矩阵、所有512路线参与统计（包括零值）、top20、PMT热点、空间统计和四个case完整明细。

索引为保存segment数组的零基索引。Arc角度以弧度记录，sweep有符号；曲线本身未修改。

## 4. Primitive Classification

Line方向按dx/dy计算，容差1e-9；水平为HORIZONTAL，竖直为VERTICAL，非轴对齐或退化线为OTHER。不依赖文件名或route名称。

Arc记录center、radius、start/end angle、sweep和端点归属。反序列化保留真实圆弧，SVG使用A命令，PNG使用DrawArc，没有用粗折线模拟弯曲。

954个cross的unordered primitive组合：

| 组合 | cross出现次数 | 占954 |
|---|---:|---:|
| Arc×Vertical | 331 | 34.70% |
| Arc×Horizontal | 303 | 31.76% |
| Horizontal×Vertical | 289 | 30.29% |
| Arc×Arc | 31 | 3.25% |
| Horizontal×Horizontal | 0 | 0 |
| Vertical×Vertical | 0 | 0 |
| Other | 0 | 0 |

“出现次数”按3N计数，不是全局去重后的交点数。主集共798个唯一pair，不能拿954直接比较全局55,935个physical CROSS。

## 5. Endpoint Ownership

物理endpoint_1/2保留真实Port身份，仅按坐标标记LEFT、RIGHT、SAME_X及TOP/BOTTOM。x相等不选左右；非明确边界为AMBIGUOUS。

从各物理端点沿唯一链追踪：只经过初始相连Line后首先到达的Arc归属该端点。不会因为segment_index=1就认定左端，也不会因为离某PMT近就猜归属。中间Arc无此连接证据则不归属；单Arc同时可达两端则保持AMBIGUOUS。端点相连纵向Line也沿同一连接证据关联PMT。

全部512路径均能建立链；本轮multi中的Arc均有唯一endpoint owner。测试支持数组重排后连接不变、整链反向以及输入Port顺序反向，物理归属保持一致；存储index变化不伪称索引不变。

**重要限制**：“endpoint-bend-related”指与端点相连的弯曲，不表示交点在欧氏距离上接近PMT边界。连接Line可能很长，本轮没有使用“距端点小于r”等阈值。

## 6. Multi Spatial Distribution

每个triplet有重心、bbox和三边长度。空间标签来自实际参与Arc的owner：

| 左右空间标签 | multi数 |
|---|---:|
| 仅LEFT端Arc | 265 |
| 仅RIGHT端Arc | 23 |
| LEFT/RIGHT混合 | 30 |
| 无endpoint Arc | 0 |

因此有LEFT参与的multi为295，有RIGHT参与为53；二者重叠30，不能相加当总数。无Arc时应标NO_ENDPOINT_ARC，不把“未归属”强行称为几何中部。

散点图每个点代表一个multi重心；真实重心很近时点会覆盖，不人为抖动坐标。

[重心矢量图](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/step_8_5_m1_5_multi_centroids.svg>)
![multi重心分布](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/step_8_5_m1_5_multi_centroids.png>)

显示分组是互斥的优先标签：special_related优先，其次top_U_related、bottom_U_related，最后cross_side_Z。对应96、90、62、70。它不等于各类别所有参与multi的独立计数。

## 7. Segment-Pair Statistics与Topology Signature

每个multi的三个cross按unordered primitive token编码并排序。详细signature的Arc再附物理LEFT/RIGHT与TOP/BOTTOM；不含算法端点方向或route遍历顺序。

简单signature：

| signature | multi数 | 占318 |
|---|---:|---:|
| Arc×H \| Arc×V \| H×V | 287 | 90.25% |
| Arc×Arc \| Arc×V \| Arc×V | 21 | 6.60% |
| Arc×Arc \| Arc×H \| Arc×H | 8 | 2.52% |
| Arc×Arc \| Arc×V \| H×V | 2 | 0.63% |

最常见简单组合并不自动满足PMT邻接，不能直接全部标PAPER_LIKE。

详细signature实际只有9种，全部列出，不为凑top20造条目：

| 排名 | canonical detailed signature | 数量 | 比例 |
|---|---|---:|---:|
| 1 | ARC(LEFT:BOTTOM) x HORIZONTAL \| ARC(LEFT:BOTTOM) x VERTICAL \| HORIZONTAL x VERTICAL | 135 | 42.45% |
| 2 | ARC(LEFT:TOP) x HORIZONTAL \| ARC(LEFT:TOP) x VERTICAL \| HORIZONTAL x VERTICAL | 130 | 40.88% |
| 3 | ARC(RIGHT:BOTTOM) x HORIZONTAL \| ARC(RIGHT:BOTTOM) x VERTICAL \| HORIZONTAL x VERTICAL | 13 | 4.09% |
| 4 | ARC(LEFT:BOTTOM) x ARC(RIGHT:BOTTOM) \| ARC(LEFT:BOTTOM) x VERTICAL \| ARC(RIGHT:BOTTOM) x VERTICAL | 11 | 3.46% |
| 5 | ARC(LEFT:TOP) x ARC(RIGHT:TOP) \| ARC(LEFT:TOP) x VERTICAL \| ARC(RIGHT:TOP) x VERTICAL | 9 | 2.83% |
| 6 | ARC(RIGHT:TOP) x HORIZONTAL \| ARC(RIGHT:TOP) x VERTICAL \| HORIZONTAL x VERTICAL | 9 | 2.83% |
| 7 | ARC(LEFT:BOTTOM) x ARC(RIGHT:BOTTOM) \| ARC(LEFT:BOTTOM) x HORIZONTAL \| ARC(RIGHT:BOTTOM) x HORIZONTAL | 8 | 2.52% |
| 8 | ARC(LEFT:TOP) x ARC(RIGHT:TOP) \| ARC(RIGHT:TOP) x VERTICAL \| HORIZONTAL x VERTICAL | 2 | 0.63% |
| 9 | ARC(RIGHT:BOTTOM) x ARC(RIGHT:TOP) \| ARC(RIGHT:BOTTOM) x VERTICAL \| ARC(RIGHT:TOP) x VERTICAL | 1 | 0.31% |

## 8. Left / Right Statistics

定义严格沿用户要求：

- cross中至少一个primitive为唯一endpoint-connected Arc，称endpoint-bend-related。
- 三个cross中至少一个相关，称endpoint-bend-dominated。这里“dominated”是约定名称，不要求多数cross。

| 每multi相关cross数 | multi数 |
|---|---:|
| 0 | 0 |
| 1 | 0 |
| 2 | 289 |
| 3 | 29 |

**318/318=100% multi涉及endpoint bend。** 665/954个cross涉及Arc；31个Arc×Arc交点各贡献两个Arc owner，因此owner出现次数为696，不能与665混用。

全局Arc-owner出现次数：LEFT=588（84.48%），RIGHT=108（15.52%），SAME_X/AMBIGUOUS=0。

| route类别 | LEFT owner出现次数 | RIGHT owner出现次数 | LEFT占该类owner | LEFT参与multi数 | RIGHT参与multi数 |
|---|---:|---:|---:|---:|---:|
| top-U | 228 | 8 | 96.61% | 114 | 4 |
| bottom-U | 156 | 0 | 100.00% | 78 | 0 |
| top->bottom Z | 128 | 18 | 87.67% | 65 | 8 |
| bottom->top Z | 76 | 82 | 48.10% | 38 | 41 |
| special-Z | 0 | 0 | N/A | 0 | 0 |

描述性判断，无90%阈值：

- top-U：左端明显占主导，但右端不是零；不能建立“仅左端”规则。
- bottom-U：当前样本只观察到左端，不证明所有未来输入均如此。
- top→bottom Z：左端更多，两侧均有。
- bottom→top Z：76/82接近平衡，明显需要双向关注。
- special-Z：当前96个相关multi中，special贡献的是其他primitive，没有special自己的Arc参与主集。不能把零Arc观察解释为special整体安全。

JSON中的BIDIRECTIONAL仅表示左右均观察到，不声称两边数量相近；此处用完整比例补充偏向程度。

## 9. Top / Bottom Statistics

LEFT/RIGHT与TOP/BOTTOM是独立轴：

| route类别 | TOP-LEFT | TOP-RIGHT | BOTTOM-LEFT | BOTTOM-RIGHT |
|---|---:|---:|---:|---:|
| top-U | 228 | 8 | 0 | 0 |
| bottom-U | 0 | 0 | 156 | 0 |
| top→bottom Z | 24 | 16 | 104 | 2 |
| bottom→top Z | 28 | 18 | 48 | 64 |
| special-Z | 0 | 0 | 0 | 0 |

计数仍为Arc-owner出现次数；TOP总322、BOTTOM总374。按unique multi，该类top→bottom Z的BOTTOM有53、TOP有14；bottom→top Z的BOTTOM有37、TOP有23，两侧可能重叠。类别名不能代替真实Arc owner侧别。

## 10. PMT Adjacency Statistics

复用M1的几何政策：top/bottom分组、PMT端点x范围排序、同侧紧邻为邻接；没有调用M1的Dynamic-D计算或建立pending状态。因M1邻接逻辑嵌在诊断函数内，本轮在独立归因模块按同一政策实现只读关系查询，未改M1。

仅对Arc×Vertical：Arc owner确定其PMT；Vertical沿端点连接确定另一PMT。关系相对于Arc owner定义。

| 关系 | Arc×Vertical出现次数 |
|---|---:|
| LEFT geometric neighbor | 32 |
| RIGHT geometric neighbor | 215 |
| NON_ADJACENT | 84 |
| SAME_PMT | 0 |
| AMBIGUOUS | 0 |

其中247/331=74.62%的Arc×Vertical出现为同侧相邻PMT。**84次NON_ADJACENT全部是上下不同侧PMT**，不是同侧跨多个邻居。这是几何关系事实，不是路由错误判断。

按multi去重：

- 有相邻PMT Arc×Vertical关系：227/318=71.38%。
- 有任何可分析Arc×Vertical关系：310/318；相邻比例227/310=73.23%。
- 有NON_ADJACENT关系的multi：84；其中1个同时有相邻关系，两者不是互斥类别。
- 剩余8个没有Arc×Vertical关系，不能据此猜邻接为否。

仅H×Arc或Arc×Arc不能凭横向段反推某个单一PMT；因此“所有endpoint bend multi是否相邻”的充分答案有这个适用范围限制。

## 11. Paper-Like Topology Classification

**PROJECT-SPECIFIC 保守事后标签**，不改变现有multi detector。判定前先用现有函数验证legacy-eligible和至少两边<0.125−1e-9 mm。

满足用户A—E的基础兼容条件：

A. 当前主集multi；
B. 存在同一route在两个不同cross中贡献Vertical Line；
C. 有唯一endpoint-connected Arc参与；
D. Arc×Vertical所关联PMT与论文同侧几何相邻兼容；
E. 原三角形criterion通过。

为避免把仅满足宽泛条件的构图硬称论文原图，另加保守确证：存在唯一邻接见证，signature为H×V、Arc×V、Arc×H，两个Arc出现属于同一条route的同一个物理bend。满足A—E但不满足此唯一构图的保留AMBIGUOUS。这个额外确证条件是本轮明示工程分类，不是论文写过的完整判定器。

| 标签 | 数量 | 比例 |
|---|---:|---:|
| PAPER_LIKE_LOCAL_MULTI | 204 | 64.15% |
| NON_PAPER_LIKE | 91 | 28.62% |
| PAPER_LIKE_AMBIGUOUS | 23 | 7.23% |

NON_PAPER_LIKE中83个没有相邻endpoint bend见证，8个没有两次cross均为Vertical的carrier。标签表示不符合本次明确局部模型，不等于全部论文方法无法影响它。

| 组成 | PAPER_LIKE | NON_PAPER_LIKE | AMBIGUOUS |
|---|---:|---:|---:|
| ordinary-only（222） | 159 | 43 | 20 |
| 含special（96） | 45 | 48 | 3 |

special的45个PAPER_LIKE只说明局部交叉构型可兼容，不说明special自身可参加普通hierarchy/pending；本轮它们的special成员没有Arc出现在这些cross中。

## 12. Non-Paper-Like Multi与独立异常标签

下表标签可相互重叠，也可与PAPER_LIKE_AMBIGUOUS重叠，不能求和当91：

| 诊断项 | multi数 |
|---|---:|
| 没有任何Arc参与 | 0 |
| 含Arc×Arc | 31 |
| 含非邻接PMT Arc×Vertical | 84 |
| 同一route两个不同bend同时参与 | 0 |
| special相关 | 96 |
| 无两次Vertical carrier | 8 |

Arc×Arc不是自动NON_PAPER_LIKE：部分满足宽泛A—E而构图不同，因此落入AMBIGUOUS。special相关也不自动NON_PAPER_LIKE。所有主集triplet都已得到三个互斥主标签之一，没有被静默丢弃。

## 13. Route Hot Spots与PMT Hot Spots

每route的multi_count是unique triplet参与数。角色统计按“该route在某multi是否至少一次涉及此类primitive”计数，各角色可能重叠。所有512路线（包括未参与者）均记录在summary.per_route。

| 排名 | route | 类别 | PMT pair | multi | LEFT bend | RIGHT bend | Horizontal | Vertical |
|---|---:|---|---|---:|---:|---:|---:|---:|
| 1 | 74 | bottom->top Z | 11—26 | 13 | 0 | 3 | 4 | 6 |
| 2 | 485 | top-U | 111—114 | 13 | 7 | 0 | 6 | 0 |
| 3 | 457 | top-U | 101—114 | 12 | 6 | 0 | 6 | 0 |
| 4 | 245 | top->bottom Z | 56—20 | 9 | 0 | 0 | 0 | 9 |
| 5 | 85 | bottom->top Z | 13—1 | 8 | 0 | 0 | 0 | 8 |
| 6 | 102 | top->bottom Z | 14—38 | 8 | 8 | 0 | 0 | 0 |
| 7 | 103 | top->bottom Z | 14—38 | 8 | 8 | 0 | 0 | 0 |
| 8 | 142 | top-U | 19—26 | 8 | 5 | 0 | 3 | 0 |
| 9 | 265 | top-U | 61—114 | 8 | 7 | 0 | 1 | 0 |
| 10 | 437 | bottom->top Z | 98—89 | 8 | 0 | 0 | 8 | 0 |
| 11 | 465 | top-U | 108—111 | 8 | 1 | 0 | 7 | 0 |
| 12 | 87 | special-Z | 13—39 | 7 | 0 | 0 | 0 | 7 |
| 13 | 88 | special-Z | 13—39 | 7 | 0 | 0 | 0 | 7 |
| 14 | 116 | top->bottom Z | 16—56 | 7 | 0 | 0 | 0 | 7 |
| 15 | 125 | top->bottom Z | 17—53 | 7 | 0 | 5 | 2 | 0 |
| 16 | 327 | bottom->top Z | 70—118 | 7 | 0 | 0 | 5 | 2 |
| 17 | 332 | top-U | 71—111 | 7 | 1 | 0 | 6 | 0 |
| 18 | 387 | bottom->top Z | 78—99 | 7 | 6 | 0 | 0 | 1 |
| 19 | 416 | bottom->top Z | 86—114 | 7 | 5 | 0 | 0 | 2 |
| 20 | 436 | bottom->top Z | 98—89 | 7 | 0 | 0 | 7 | 0 |

最高为route74和485，各13个multi；并非一条route支配318个全部问题。route74为混合角色，route485则左bend与水平段参与较多。

PMT热点分开两种口径：

- **参与route的所有端点PMT**：PMT26关联70个multi、86关联59、114关联56、108关联53、111关联51。这不证明交点位于这些PMT附近。
- **实际endpoint-bend owner PMT**：PMT114=34、38=26、78=26、113=23、19=16；更接近局部bend归因。
- **连接PMT pair**：14—38=26、61—86=23、26—49=20、13—39=19、86—114=18。
- **Arc/Vertical几何邻接PMT pair**：26—114=20、49—78=18、19—108=16、20—113=16、16—109=14。数字大小不决定邻接，只是输出canonical身份。

完整top20分别保存在summary对应字段。PMT pair每triplet内去重，跨triplet累计；不据此调整输入连接关系。

## 14. Spatial Hot Spots

重心按25×25 mm固定网格作描述统计，不用于几何判定或allocator。

最密的5格：

| x范围(mm) | y范围(mm) | multi重心数 |
|---|---|---:|
| [50,75) | [125,150) | 42 |
| [50,75) | [0,25) | 37 |
| [0,25) | [100,125) | 33 |
| [25,50) | [125,150) | 31 |
| [100,125) | [100,125) | 26 |

y带计数：[0,25)=78、[25,50)=0、[50,75)=0、[75,100)=35、[100,125)=91、[125,150)=114。当前结果集中在上下布线带及上半部跨侧区域；不能由这个分布反推出新的PMT位置规则。

图形输出：950×950散点PNG与真正矢量SVG；四个case各1200×660 PNG+SVG。已检查轴比例一致、SVG无嵌入image且case含真实A命令。case上下文中的交点文本原本过密，已仅在放大面板标AB/AC/BC，避免文字重叠。

## 15. Case Studies

A/B/C按canonical route IDs次序，AB/AC/BC分别对应三对真实physical CROSS。案例图是同一保存几何的局部视窗，不是重新布线；曲线裁剪仅为展示。

### 15.1 most_common_topology：M0009

Route IDs：3、101、302。类别：3=bottom->top Z；101=special-Z；302=bottom->top Z。PMT pairs：3=1—9；101=14—33；302=68—116。

标签：**NON_PAPER_LIKE**；原因：NO_ADJACENT_ENDPOINT_BEND。重心(123.60315526293537, 87.11666666666667) mm；边长依次为AB点—AC点、AB点—BC点、AC点—BC点：0.08243016945757743、0.05000000000001137、0.06553421119387792 mm。

| pair | physical CROSS (mm) | 第一route primitive | 第二route primitive |
|---|---|---|---|
| 3—101 | (123.625, 87.15) | Arc #1；LEFT/BOTTOM，PMT 1，port 6，端点(121.625, 0) | VERTICAL Line #0；LEFT/TOP，PMT 14，port 202，端点(123.625, 150) |
| 3—302 | (123.55946578880612, 87.1) | Arc #1；LEFT/BOTTOM，PMT 1，port 6，端点(121.625, 0) | HORIZONTAL Line #2；无唯一端点归属（中间段或双端连接） |
| 101—302 | (123.625, 87.1) | VERTICAL Line #0；LEFT/TOP，PMT 14，port 202，端点(123.625, 150) | HORIZONTAL Line #2；无唯一端点归属（中间段或双端连接） |

Arc几何：
- route 3 / segment 1：center=(126.625,83.15)，r=5，start angle=3.141592653589793，end angle=1.5707963267948966，sweep=-1.5707963267948966 rad。

Arc×Vertical PMT关系：Arc route3/PMT1 → Vertical route101/PMT14：NON_ADJACENT

[矢量简图](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/step_8_5_m1_5_case_most_common_topology.svg>)，左侧为12 mm弯曲上下文，右侧为三交点细节；两面板各自保持等比例坐标，未对几何做折线近似。
![M0009 局部几何](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/step_8_5_m1_5_case_most_common_topology.png>)
### 15.2 endpoint_bend：M0001

Route IDs：0、300、345。类别：0=bottom->top Z；300=bottom->top Z；345=bottom->top Z。PMT pairs：0=1—8；300=68—113；345=73—108。

标签：**NON_PAPER_LIKE**；原因：NO_TWO_CROSS_VERTICAL_CARRIER。重心(122.09811024146559, 86.73000377299623) mm；边长依次为AB点—AC点、AB点—BC点、AC点—BC点：0.07563289280257654、0.13170082129686023、0.10455944653360795 mm。

| pair | physical CROSS (mm) | 第一route primitive | 第二route primitive |
|---|---|---|---|
| 0—300 | (122.15736446016119, 86.75) | Arc #1；LEFT/BOTTOM，PMT 1，port 0，端点(121.1, 0) | HORIZONTAL Line #2；无唯一端点归属（中间段或双端连接） |
| 0—345 | (122.1113026253713, 86.69001131898871) | Arc #1；LEFT/BOTTOM，PMT 1，port 0，端点(121.1, 0) | Arc #1；RIGHT/BOTTOM，PMT 73，port 690，端点(124.2, 0) |
| 300—345 | (122.02566363886433, 86.75) | HORIZONTAL Line #2；无唯一端点归属（中间段或双端连接） | Arc #1；RIGHT/BOTTOM，PMT 73，port 690，端点(124.2, 0) |

Arc几何：
- route 0 / segment 1：center=(126.1,83.675)，r=5，start angle=3.141592653589793，end angle=1.5707963267948966，sweep=-1.5707963267948966 rad。
- route 345 / segment 1：center=(119.2,82.625)，r=5，start angle=0，end angle=1.5707963267948966，sweep=1.5707963267948966 rad。

Arc×Vertical PMT关系：N/A，此案例没有Arc×Vertical，因此不能推断PMT邻接。

[矢量简图](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/step_8_5_m1_5_case_endpoint_bend.svg>)，左侧为12 mm弯曲上下文，右侧为三交点细节；两面板各自保持等比例坐标，未对几何做折线近似。
![M0001 局部几何](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/step_8_5_m1_5_case_endpoint_bend.png>)
### 15.3 non_paper_like：M0002

Route IDs：0、300、348。类别：0=bottom->top Z；300=bottom->top Z；348=bottom->top Z。PMT pairs：0=1—8；300=68—113；348=73—117。

标签：**NON_PAPER_LIKE**；原因：NO_TWO_CROSS_VERTICAL_CARRIER。重心(122.12667551730316, 86.73912199812484) mm；边长依次为AB点—AC点、AB点—BC点、AC点—BC点：0.041253645577283136、0.06683024896732093、0.0528678697701958 mm。

| pair | physical CROSS (mm) | 第一route primitive | 第二route primitive |
|---|---|---|---|
| 0—300 | (122.15736446016119, 86.75) | Arc #1；LEFT/BOTTOM，PMT 1，port 0，端点(121.1, 0) | HORIZONTAL Line #2；无唯一端点归属（中间段或双端连接） |
| 0—348 | (122.13212788055439, 86.71736599437449) | Arc #1；LEFT/BOTTOM，PMT 1，port 0，端点(121.1, 0) | Arc #1；RIGHT/BOTTOM，PMT 73，port 696，端点(124.025, 0) |
| 300—348 | (122.09053421119387, 86.75) | HORIZONTAL Line #2；无唯一端点归属（中间段或双端连接） | Arc #1；RIGHT/BOTTOM，PMT 73，port 696，端点(124.025, 0) |

Arc几何：
- route 0 / segment 1：center=(126.1,83.675)，r=5，start angle=3.141592653589793，end angle=1.5707963267948966，sweep=-1.5707963267948966 rad。
- route 348 / segment 1：center=(119.025,82.8)，r=5，start angle=0，end angle=1.5707963267948966，sweep=1.5707963267948966 rad。

Arc×Vertical PMT关系：N/A，此案例没有Arc×Vertical，因此不能推断PMT邻接。

[矢量简图](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/step_8_5_m1_5_case_non_paper_like.svg>)，左侧为12 mm弯曲上下文，右侧为三交点细节；两面板各自保持等比例坐标，未对几何做折线近似。
![M0002 局部几何](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/step_8_5_m1_5_case_non_paper_like.png>)
### 15.4 special_related：M0023

Route IDs：13、182、318。类别：13=special-Z；182=bottom-U；318=bottom-U。PMT pairs：13=2—11；182=38—41；318=70—73。

标签：**PAPER_LIKE_LOCAL_MULTI**；原因：UNIQUE_ADJACENT_HV_AV_AH_MOTIF。重心(93.24625019860189, 21.81907371025245) mm；边长依次为AB点—AC点、AB点—BC点、AC点—BC点：0.017778869242640383、0.06375059580564368、0.06618328079750549 mm。

| pair | physical CROSS (mm) | 第一route primitive | 第二route primitive |
|---|---|---|---|
| 13—182 | (93.225, 21.824999999999996) | VERTICAL Line #3；LEFT/BOTTOM，PMT 11，port 27，端点(93.225, 0) | HORIZONTAL Line #2；无唯一端点归属（中间段或双端连接） |
| 13—318 | (93.225, 21.807221130757355) | VERTICAL Line #3；LEFT/BOTTOM，PMT 11，port 27，端点(93.225, 0) | Arc #1；LEFT/BOTTOM，PMT 70，port 636，端点(89.6, 0) |
| 182—318 | (93.28875059580564, 21.824999999999996) | HORIZONTAL Line #2；无唯一端点归属（中间段或双端连接） | Arc #1；LEFT/BOTTOM，PMT 70，port 636，端点(89.6, 0) |

Arc几何：
- route 318 / segment 1：center=(94.6,17)，r=5，start angle=3.141592653589793，end angle=1.5707963267948966，sweep=-1.5707963267948966 rad。

Arc×Vertical PMT关系：Arc route318/PMT70 → Vertical route13/PMT11：RIGHT_GEOMETRIC_NEIGHBOR

[矢量简图](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/step_8_5_m1_5_case_special_related.svg>)，左侧为12 mm弯曲上下文，右侧为三交点细节；两面板各自保持等比例坐标，未对几何做折线近似。
![M0023 局部几何](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/step_8_5_m1_5_case_special_related.png>)

补充解读：

- M0009属于最常见的详细拓扑，但Arc/Vertical连接上下不同侧PMT，因此NON_PAPER_LIKE；常见signature不能代替邻接证明。
- M0001/M0002含Arc×Arc与水平线，不存在两次均贡献Vertical的carrier，是明确不同于所选论文局部模型的例子。
- M0023含special却局部符合模型；special是route13，实际贡献Vertical。相关bend来自ordinary route318。不能把“special相关”误读为“special弧危险”。

完整CSV/summary还保留每个case所有实体和坐标；上表没有使用距离阈值挑Arc owner。

## 16. Implications for Hierarchy：回答Q1—Q9

**Q1：主要primitive组合？** 单cross以Arc×V最多（331），其次Arc×H（303）、H×V（289）；完整triplet最常见Arc×H/Arc×V/H×V（287）。

**Q2：是否endpoint bend相关？** 是，318/318；这是连接拓扑意义，不是交点距PMT的距离断言。

**Q3：LEFT还是RIGHT？** owner出现588/108，左端更多；unique multi为LEFT-only265、RIGHT-only23、mixed30，不能只看一次Arc×Arc的某一侧。

**Q4：类别是否方向不同？** 是。top-U左偏、bottom-U当前仅左、top→bottom Z左偏但双侧、bottom→top Z近均衡。不存在可直接写进allocator的统一“危险侧”。

**Q5：是否主要邻接PMT？** 在可归因Arc×V中有明显相邻成分：227个multi有同侧邻接；但84个multi含上下不同侧的非邻接关系，8个没有Arc×V可判。

**Q6：多少符合论文局部模型？** 保守确证204（64.15%），另23（7.23%）兼容部分条件但无法唯一确证。

**Q7：多少明显不同？** 91（28.62%）不满足本轮局部模型的必要构型/同侧邻接条件。不能把23个歧义强行归入true或false。

**Q8：hierarchy/Dynamic-D是否值得继续？** 对局部邻接构图仍值得做限定研究，但不宜作为覆盖当前全部exact multi的唯一主要恢复路线。ordinary-only确证子集为159（占所有multi50%）；其余含special或不同构型/未决时序。即使PAPER_LIKE通过，也没有证明K选择、候选时序或布通恢复有效。

**Q9：是否应考虑更通用exact-geometry recovery？** 是，作为下一步设计方向更能容纳跨侧非邻接和Arc×Arc。但本轮没有证明任何recovery策略会成功，也没有实现、试跑或重新启动greedy hard guard。

## 17. Recommended Next Step

建议单独授权 **M1.6：局部Exact-Geometry Recovery方案设计与小样本验收规格**，先只设计，不直接实现reroute：

1. 用邻接普通PAPER_LIKE、上下异侧NON_PAPER_LIKE、Arc×Arc及special-carrier四类已有case定义局部问题。
2. 明确每种方案可能修改的自由度、哪些既有路径必须保护、独立exact验收与no-commit-on-failure要求。
3. 将M1 Dynamic-D仅作为同侧邻接子集的可选诊断，不用它解释全部multi，也不计算整数K。
4. 在用户另行确认实验范围前，不运行512 routing、fragment、hard rejection或reroute。

暂不建议继续以“论文终止端必等于当前算法终止端”作为前置假设；物理归因已显示不同类别和不同端有不同分布。

## 18. Remaining Limitations、Tests与交付检查

- 本轮复用既有全pair验证，不重复130,816对求交；逐个验证全部raw事件的geometry membership，并核对318主集的criterion与坐标，不声称重跑完整intersection pipeline。
- 0.125−tol criterion完全未变，touch、overlap、angle未被加入multi定义。
- 边界2与outside 841,477不混入主集。
- 端点相连Arc是链结构定义，非空间距离标签；没有证明当前左右对应论文终止端。
- NON_PAPER_LIKE/PAPER_LIKE是明确的工程后分类，并非旧源码规则；23个歧义单列。
- 同一个physical pair可能参与多个triplet；954行归因与696次Arc owner统计都有明确重复计数口径。
- special成员没有Arc参与当前主集，不等于special在整个设计中无风险。
- 热点为单一baseline上的描述，不推断全局优化因果或未来布局不变量。

新增29项测试涵盖Line方向、物理左右/上下/SAME_X、几何链Arc owner、数组重排和反向、raw index不匹配、join保留、真实合成H×V/Arc×V/Arc×Arc multi、几何PMT邻接、paper-like/non-paper-like/ambiguous、canonical signature、special双Arc、只读深拷贝与反序列化。

**全套487/487通过：原458项+新增29项，失败0。** 回归约5.13秒，未安装任何依赖。审计初次输出截取引起一次stdout关闭提示，随后改为完整消费输出并重新成功生成本次结果；这没有改变数据或归因判定。

独立文件检查通过：

- triplets.csv=318行；crosses.csv=954行。
- 每个multi三个pair各一个physical CROSS；954行双方primitive均唯一。
- per_route含512项，multi_count总和954。
- primitive组合计数和为954，paper标签计数和为318。
- 三个physical点与保存结果逐值一致；所有初始输入对象未改。
- 5个SVG均解析通过，无嵌入PNG；case含真实圆弧命令。
- 5个PNG尺寸和文件头有效；散点与全部case已目视检查，局部标注修正后再次检查。
- 本轮开始时已有121个src/tests/scripts/outputs/docs文件交付前逐一SHA256检查保持不变；原始Excel哈希保持不变。

主要输出：

- [summary.json](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/step_8_5_m1_5_multi_attribution_summary.json>)
- [triplets.csv](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/step_8_5_m1_5_multi_triplets.csv>)
- [crosses.csv](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/step_8_5_m1_5_multi_crosses.csv>)
- [centroids.svg](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/step_8_5_m1_5_multi_centroids.svg>) / [centroids.png](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/step_8_5_m1_5_multi_centroids.png>)
- 四个case的SVG/PNG见第15节。

**M1.5 PASS仅表示归因审计完整、可重复且未改变正式baseline。本轮停止。**
