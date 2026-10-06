# 3D Waveguide Literature and Physics Audit v0.1

日期：2026-09-14  
项目：`C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D`  
审计范围：文献证据、三维几何模型、碰撞定义、层间过渡曲线、参数来源与首版光损耗模型。  
变更边界：本次仅新增本文档及 `references/core_physics/README.md`，未修改源代码、配置、既有报告或数据。

> 证据等级：`FULL TEXT VERIFIED` 表示已取得并逐页核验全文；`ABSTRACT VERIFIED` 表示只核验官方摘要和元数据；`SNIPPET-ASSISTED` 表示另外参考搜索索引可见正文片段。摘要或片段未给出的量一律记为 `NOT REPORTED`。不同制造平台的数据不直接拼成同一组设计规则。

## Executive Summary

1. 八篇指定核心论文全部完成身份核验；合法下载并完整阅读 1 篇，另 7 篇只达到官方摘要或摘要加索引片段级别。失败原因主要是出版社 PDF 端点的访问控制/机器人验证，不是论文身份不明。论文 8 的 ECOC 记录没有可核实 DOI；同题名 ICSJ 论文的 DOI 不能移植给 ECOC 版本。[1–8]
2. 文献足以否定项目当前“所有中心线小于 0.1 mm 的相交/近接都等价于制造违规”的解释。单层合法交叉、投影交叉、近并行贴近、重合、真实三维包络违规具有不同物理含义，必须分型。[3,9–12]
3. 当前 `204291 → 138113` 只表示项目自定义中心线近距对计数下降 32.39%，不是“制造违规减少 32.39%”，也不是“光学风险减少 32.39%”。终态仍有 138,113 对，说明这个标量更像密集网络的几何负载指标，而不是可验收的违规数量。
4. `CosineTransition3D` 的位置和切向连续，理论曲率公式及由此得到的 `Lxy ≥ π√(R|Δz|/2)` 是正确的；但它与直线在端点只有 C1 连续，曲率从 0 突跳到最大值，因此不是 C2/曲率连续过渡。有限最小曲率半径只证明几何可定义，不证明低损耗、低模态扰动或可制造。[9]
5. 八篇核心论文没有一篇直接验证“项目的离散 0/1/2 mm 三层 + 余弦高度律 + 5 mm 最小曲率半径 + 0.1 mm clearance + 1024 路”组合。最接近的 Mosquito 3D crossover 使用约 0.7 mm 局部高差、约 30 mm 斜坡和 4 mm 弯曲半径；微米级多层光刻论文则属于不同平台。[1,2]
6. 现有证据足够建立首版“损耗台账/符号模型”：传播、弯曲、交叉、层间过渡分别计项，并保留耦合/连接器项；但不足以建立可信的数值预测模型。缺失量包括选定材料与折射率分布、波长和发射模态、每厘米传播损耗、弯曲损耗函数、角度相关交叉损耗、3D 过渡的模态转换/辐射损耗以及聚簇和重复交叉效应。[2–7,9]
7. 最需要优先重审的不是 300×200 mm 板尺寸，而是 `clearance_3d = 0.1 mm` 的物理定义：它目前把中心线距离、芯区尺寸、包层/工艺安全边界和光学串扰边界压成一个数，直接决定“碰撞”数量及层分配行为，但没有对应选定制造平台的测量依据。
8. 工程上建议先选择平台，再标定规则：若走光刻 PCB 矩形 SI 路线，应以有限横截面、最小边缘间距、角度相关交叉损耗和层压稳定性为主；若走 Mosquito 圆形 GI 路线，应以可写入的三维轨迹、坡长/高差、曲率变化和模态保持为主。两套证据不能在未校准时共用一个 clearance 或损耗系数。[2–7,9–12]

## Core Papers

### 核心文献矩阵

| # | 核心论文 | 平台标签 | 证据等级 | 可用于本项目的结论 | 关键边界 |
|---|---|---|---|---|---|
| 1 | Weigel et al., JLT 2024[1] | 多层薄膜聚合物光子集成、垂直 3D MMI | `ABSTRACT VERIFIED`; PDF `NOT OBTAINED` | 证明“通过多层绕开平面交叉”可在特定平台实现；四层、相邻层距 7.2 µm | 不是 50 µm 板级多模 Mosquito 平台；层距不可直接迁移 |
| 2 | Rasel et al., JLT 2022[2] | Mosquito 圆形 GI、板级 3D crossover | `ABSTRACT VERIFIED`, `SNIPPET-ASSISTED`; PDF `NOT OBTAINED` | 约 50 µm 芯、250 µm pitch、4 mm bend、0.7 mm 局部高差、13° 投影交叉可以实现低串扰/无误码 | 30 mm 坡长与整体器件条件很关键；1.64 dB 是总插损而非纯过渡损耗 |
| 3 | Baghsiahi et al., SPIE 2014[3] | FR4、光刻矩形 SI 聚丙烯酸酯 MM | `FULL TEXT VERIFIED` | 同层交叉的单位损耗强烈依赖角度；10° 图读约 0.15 dB/crossing，90° 图读约 0.02 dB/crossing | 图读近似；定量串扰在所得正文中 `NOT REPORTED`; 不适用于 GI 圆芯的无校准外推 |
| 4 | Karakawa & Ishigure, OE 2026[4] | Mosquito 圆形 GI、高 Δ 树脂 | `ABSTRACT VERIFIED`; PDF `NOT OBTAINED` | 特定高 Δ 材料可在约 1 mm 半径 90° 弯处实现 <0.1 dB bend loss | 不能推出一般材料的 1 mm 规则；完整材料与测量条件 `NOT REPORTED` |
| 5 | Kohmu et al., OE 2022[5] | VCSEL 光引擎、Mosquito GI、局部 90° 弯 | `ABSTRACT VERIFIED`, `SNIPPET-ASSISTED`; PDF `NOT OBTAINED` | 850 nm 下，芯径、NA、弯曲与耦合间隙共同决定性能；约 2 dB 是器件总插损 | 不能把总插损当作 R=1 mm 的单位 bend loss |
| 6 | Shi et al., OE 2023[6] | 光成像矩形 MM PCB + 可插拔连接器 | `ABSTRACT VERIFIED`, `SNIPPET-ASSISTED`; PDF `NOT OBTAINED` | 10 cm+两连接器平均插损 6.42 dB，0.77 dB/interface；真实链路必须计入耦合/连接器 | 不能只用长度、弯曲、交叉、过渡四项解释系统总损耗 |
| 7 | Xu et al., OE 2022[7] | 层压光背板、矩形 MM | `ABSTRACT VERIFIED`; PDF `NOT OBTAINED` | 芯宽改变模态色散；层压使平均损耗从 0.137 增至 0.192 dB/cm | 说明制造后处理不可忽略，不提供项目 3D 过渡系数 |
| 8 | Yamaguchi et al., ECOC 2022[8] | Mosquito 3D fan-in/out | `ABSTRACT VERIFIED`; PDF `NOT OBTAINED` | 约 10 mm 长四芯三维变换器表明短程 3D 排列变化可制造 | 官方摘要没有定量损耗和轨迹细节；ECOC DOI `NOT FOUND/NOT ASSIGNED` |

### 逐篇物理审计

#### 1. Crossing-free multilayer routing

论文 1 的价值是给出一种真正避免同层交叉的架构，而不是给出项目当前板级参数的标定。官方摘要报告 16×4 网络、四个堆叠聚合物层、相邻层 7.2 µm、顶底 21.6 µm，并用垂直 1×1 3D MMI 连接。[1] 这说明“层”必须连同层间耦合器、沉积和平坦化工艺定义，不能只是几何坐标中的 z 值。项目采用 0、1、2 mm 三个离散高度、50 µm 量级波导时，两者尺度相差两个数量级以上；将其称为同一种 multilayer platform 会造成证据错配。

#### 2. Board-level 3D multimode crossover

论文 2 是八篇中与项目局部“抬升避让”概念最接近的一篇。官方摘要确认其为 Mosquito 法、圆形 GI 多模聚合物波导、12 通道 6×6 crossover；可检索正文片段进一步给出 250 µm pitch、上下两组各偏移约 0.35 mm、交叉处总高差约 0.7 mm、约 30 mm 的斜坡段、4 mm 弯曲半径和 13° 投影角。[2] 报告的平均插损 1.64 dB、串扰 <−45 dB 和 26 Gb/s 无误码是整个试样、发射/接收和制造条件下的结果，不是一个可以乘以“过渡次数”的常数。

对项目最重要的启示是：跨层的可制造性由 `Δz、坡长、曲率、芯形、GI 分布、写入工艺、发射模态` 共同决定。只检查最小曲率半径不足以复现实验。项目中每次升降若采用 1 mm 高差且只按 5 mm 半径下限确定短过渡，其坡度和曲率变化历史都不同于论文 2。

#### 3. Angle-dependent crossing loss

论文 3 已全文核验。试样为 FR4 上光刻聚丙烯酸酯矩形 SI 多模波导，芯 50×50 µm，`n_core=1.5560`、`n_clad=1.5264`，853 nm；每种角度串联六个交叉，通过重复测量估计每交叉损耗。[3] 图 5 显示单位交叉损耗随角度增大显著下降，幂律拟合约为：

`L_cross(θ) ≈ 1.0779 · θ^-0.873 dB/crossing`，其中 θ 以度计。[3]

该式只能视为该试样和发射条件的经验拟合。图读约 10° 为 0.15 dB/crossing，90° 约 0.02 dB/crossing。射线模型在小于约 20° 时预测超过 1 dB，但实验明显更低；作者讨论的关键原因包括实际发射模态/角分布，最佳匹配的等效 NA 约 0.05，而不是简单用输入 50/125 µm SI MMF 的额定 NA 0.22。[3] 因此，单层交叉应是带角度和平台标签的光学事件，不能统一判为几何硬冲突。

论文题名同时写 optical loss and crosstalk，但所取得七页正文未给出可提取的定量串扰结果；本审计记作 `NOT REPORTED`，不以题名推断数据。

#### 4–5. Small-radius GI bends

论文 4 的官方摘要显示，高 Δ 树脂配合 Mosquito GI 圆芯，使 R≈1 mm 的 90° 弯曲损耗低于 0.1 dB。[4] 这表明 `R_min=5 mm` 未必物理上过激，但同时证明半径阈值高度依赖材料 Δ 和 GI 轮廓。论文 5 的约 2 dB 是 850 nm 器件总插损，含耦合、传播和弯曲；使用高折射率树脂间隙可使耦合损耗降低约 5 dB。[5] 两者共同说明：一个很小的 bend loss 并不等于整个 3D transition loss 很小，接口和模态匹配可以主导预算。

#### 6–7. PCB link and lamination evidence

论文 6 的 10 cm 波导加两个连接器平均 6.42 dB、耦合 0.77 dB/interface，为系统损耗项提供现实校验。[6] 若首版只写 `L_total=L_prop+L_bend+L_cross+L_transition`，其物理命名应说明这是“路由内部损耗”，不是端到端链路损耗；端到端至少还需 `L_in+L_out+L_connector`。

论文 7 在层压前后对 80 通道测得平均 0.137 与 0.192 dB/cm，并观察 70 µm 宽波导较 40 µm 宽波导约 1 dB 模态色散代价。[7] 它提示制造流程会改变损耗，宽度也同时影响空间设计与带宽。项目把 width 只当几何线宽，会漏掉模态和加工层压后果。

#### 8. 3D fan-in/out

论文 8 的官方 ECOC 记录仅确认 Mosquito 法、约 10 mm 长、四芯三维排列变化的 fan-in/out。[8] 官方页标记不可访问，摘要没有定量过渡损耗。本次发现同题名 ICSJ 2022 记录带 DOI `10.1109/ICSJ55786.2022.10034708`，但它是不同会议版本，故没有把该 DOI 赋给 ECOC We3A.3。这是本次检索中一个必须保留的元数据边界。

## Supplementary Papers

1. Papakonstantinou et al. 将多模聚合物弯曲损耗分成 transition、radiation 和 propagation，并用 BPM 与实验比较。50/75/100 µm 矩形芯、Δn≈0.0296、850 nm 条件下，最低总 bend loss 的具体半径与芯宽有关；例如 50 µm 方芯在约 13.5 mm 半径得到约 0.74 dB，而 75 µm、R=5 mm 时初始约 8° 主要由 transition loss 主导，之后 radiation loss 增长。[9] 因而“半径大于阈值”不是完整损耗模型。
2. Hashim et al. 研究板上复杂多模波导组件，报告 50×100 µm 平台的 90° crossing 最坏约 0.1 dB/crossing，并强调发射条件对串联组件响应的影响。[10] 它与论文 3 的数值不完全一致，正好说明不能把跨实验系数当通用常数。
3. Zhang et al. 在 20×20 µm 双层光刻平台中优化层距：粗糙度 <80 nm 时约 24 µm 可使 crosstalk <−30 dB；实作约 24.5 µm，850/1310 nm 传播损耗分别 <0.25/<0.40 dB/cm，串扰低于 −52/−60 dB。[11] 这是“层距必须由横截面、粗糙度和串扰联合标定”的证据，不是项目 1 mm 层距的直接设计值。
4. Xu et al. 的直接写入圆芯平台报告 43–44 µm 量级长波导、62.5 µm pitch 下串扰低于 −34 dB、R=4 mm bend loss <0.08 dB/mm，并展示双层及 3D 器件。[12] 它为 4–5 mm 半径的可行性提供旁证，但仍需匹配材料、芯形与发射条件。
5. Bamiedakis et al. 的 CLEO 摘要报告特定多模聚合物 90° crossing 的 excess loss 约 0.006 dB/crossing、crosstalk 可低至 −30 dB。[13] 它证明合法交叉可以很低损耗，也显示不同试样间数值跨度较大。
6. Martinez Abreu et al. 的开放综述用于区分光刻、直接写入/Mosquito、打印等制造路线，提醒几何规则必须挂靠工艺。[14]
7. IBM 公开项目列举 12、32 和 192 通道量级的聚合物波导系统实例；本次没有找到与项目 1024 路固定拓扑相匹配的真实系统证据。[15] 这不是“不可能”的证明，而是“当前未找到依据”。

## Physics Findings

### 1. 路由中心线不是物理波导

项目碰撞核对路由中心线的最小三维距离，阈值为 0.1 mm。真实波导至少包含芯区、包层、制造偏差和光场尾部。令两路中心线最小距离为 `d_cc`，芯区等效半宽为 `a_i、a_j`，制造余量为 `m_fab`，光学串扰余量为 `m_xtalk`，则应分别检查：

- 芯区几何不重叠：`d_cc ≥ a_i + a_j`；
- 工艺安全：`d_cc ≥ a_i + a_j + m_fab`；
- 光学隔离：`d_cc ≥ d_xtalk(material, profile, λ, modes, parallel_length)`。

三者一般不相等。当前单一 `clearance_3d` 没有说明是中心线间距、边缘间距、工艺包络还是光学隔离，因此同一个计数不能被解释成制造违规数或串扰事件数。

### 2. 同层交叉是光学事件，不天然是制造违规

论文 3、10、13 均证明光刻多模聚合物波导可以制造同层交叉，且损耗随角度、平台与发射条件变化。[3,10,13] 因此，若选定平台允许 crossing，则单次交叉应进入 `L_cross(θ, platform, launch)`，同时计入 crossing 统计；只有当角度低于平台合格下限、发生长距离重合、局部密度超过工艺规则，或系统损耗/串扰预算超限时，才升级为硬约束。

### 3. 小角度、重合与近并行必须分开

二维折线的严格横穿通常在一点相交；共线重合在一段区间相交；近并行路由可能不相交但持续强耦合。三者的风险次序不能由最小中心线距离单独决定。尤其是近并行，`d_min` 相同而平行长度不同，串扰会显著不同；必须至少记录 `parallel_length` 与相对角度。

### 4. 投影交叉不等于三维接触

两条波导的 xy 投影可交叉但 z 分离充分。此时它不是同层 crossing loss，也不是芯区几何碰撞，而是层间耦合/串扰事件；其物理量取决于垂直芯间距、层间材料、重叠长度和模式。论文 1、2、11 展示了三种完全不同的层间机制与尺度。[1,2,11]

### 5. CosineTransition3D 的曲率推导

项目过渡可写为：

`x(t)=x0+Δx·t, y(t)=y0+Δy·t, z(t)=z0+Δz(1−cos πt)/2, t∈[0,1]`。

设平面投影长度 `Lxy=√(Δx²+Δy²)`，以平面弧长 `s=Lxy·t` 参数化，则：

`z'(s)=πΔz/(2Lxy)·sin(πs/Lxy)`，

`z''(s)=π²Δz/(2Lxy²)·cos(πs/Lxy)`。

平面-高度曲线的曲率为：

`κ(s)=|z''(s)|/[1+z'(s)²]^(3/2)`。

最大曲率在两端点，`κ_max=π²|Δz|/(2Lxy²)`，故：

`R_min=1/κ_max=2Lxy²/(π²|Δz|)`，

`Lxy ≥ π√(R_req|Δz|/2)`。

代码中的这一解析关系正确。对于 `R_req=5 mm、|Δz|=1 mm`，最短平面长度约 4.967 mm；对于 2 mm 高差约 7.025 mm。问题在于端点外接直线的曲率为 0，而余弦段端点曲率为 `κ_max`：位置连续、切线水平，因此是 C1；曲率不连续，因此不是 C2/渐变曲率连接。对多模波导，曲率突变会激发模式重分配和 transition loss，论文 9 明确表明这可在弯曲初段主导。[9]

### 6. 验证余弦过渡需要什么仿真

板级 50 µm 多模波导不适合对整条几十至几百毫米路由直接做全波 3D FDTD，计算尺度过大。推荐的证据链是：

1. 用实际 `n(x,y,z,λ)` 求截面本征模与模式功率分布；
2. 对局部升降段使用标量/全矢量 BPM 或有限元传播，扫描 `Δz、Lxy、R_min、曲率变化、芯径、GI/SI、波长、发射模态`；
3. 输出总透射、辐射损耗、各导模耦合矩阵和近场分布；
4. 在最紧半径、最大高差和曲率突变局部用 3D FDTD/FEM 做有限尺寸交叉验证；
5. 以实际制造试样做 cutback/参考直线对照，分离耦合、传播、弯曲和 transition loss。

在完成上述至少第 1–2、5 步前，`R_min≥5 mm` 只能称为几何筛选条件，不能称为“低损耗保证”。

## Collision Taxonomy

| 类型 | 判定所需几何量 | 建议分类 | 损耗/串扰处理 | 统计字段 |
|---|---|---|---|---|
| 合法单次同层横穿 | 拓扑相交点、角度 θ、交叉邻域无重合 | 默认非硬碰撞；平台禁止时才硬约束 | `L_cross(θ, platform, launch)`；串扰用平台模型 | `n_cross`, 角度直方图 |
| 小角度交叉 | θ 小于合格角阈值但仍点交 | 软惩罚；低于制造/预算下限时硬约束 | 角度相关损耗和串扰快速增加；避免用常数 | `n_cross_small_angle`, `θ_min` |
| 共线/近共线重合 | 相交集合为线段或距离低于阈值且切向相同 | 硬约束 | 不视为多个 crossing；需重新布线 | `overlap_length` |
| 近并行长距离贴近 | `d_min`、相对角、近距持续长度 | 工艺间距不足时硬约束；否则串扰软约束 | `XT(d, L_parallel, modes)` | `parallel_close_length` |
| 有限横截面/包层间距不足 | 中心线距离减去两路包络半径 | 硬约束 | 即使中心线不交也可能不可制造 | `min_edge_clearance` |
| 多波导聚簇交叉 | 一个局部邻域内 crossing 数、最近事件间距 | 未经验证的密集聚簇为硬约束；其余软惩罚 | 不能简单假设独立相加，应做局部仿真/试验 | `cluster_order`, `event_spacing` |
| 同一路由对重复交叉 | 同一 pair 的相交事件数和间距 | 通常软惩罚；预算超限时硬约束 | 首版可暂加和并标不确定度，后续考虑模态记忆 | `repeated_pair_crossings` |
| 层间投影交叉 | xy 投影相交、实际 z 分离 | 非同层 crossing；层间距离不足时硬约束 | 层间耦合/串扰模型，而非同层 crossing loss | `projected_crossings`, `vertical_gap` |
| 真实三维包络交叠 | 两条三维芯/包层实体相交 | 硬约束 | 无需损耗模型即可判失败 | `true_3d_violations` |
| 过渡段自交/触碰器件 | 曲线-自身、曲线-障碍物/端口包络 | 硬约束 | 另计 transition/bend loss | `transition_violations` |

推荐将当前单一 collision count 拆成三层：

- `hard_violation_count`：真实三维包络交叠、重合、工艺间距不足、障碍物碰撞；目标必须为 0。
- `optical_event_ledger`：合法 crossing、bend、transition、层间近耦合；不要求为 0，但必须满足损耗/串扰预算。
- `geometric_density_metrics`：近距 pair、投影交叉、聚簇密度；用于优化和对比，不宣称为违规。

因此现有 `204291 → 138113` 应重命名为类似 `centerline_close_pair_count(<0.1 mm)`。降幅 `(204291−138113)/204291=32.39%` 只证明该项目指标减少。它没有区分 138,113 个终态 pair 中哪些为合法交叉、近接、重合或真正 3D 侵入，不能转写成制造合规率。

## Transition Model Audit

### 几何正确性

- 端点位置正确：`z(0)=z0, z(1)=z1`。
- 端点坡度为零：`z'(0)=z'(1)=0`，若前后直线与平面投影方向一致，则连接为 C1。
- 最小曲率半径解析式正确，代码据此计算所需投影长度。
- 曲率最大值位于端点，连接到零曲率直线时发生曲率跳变；曲线不是 C2。
- 若平面路径在升降段端点同时转向，仍须检查三维合成曲率和扭率，不能只用高度剖面的公式。

### 物理充分性

`CosineTransition3D` 是合理的第一版几何候选，但没有直接文献验证。论文 2 验证的是特定 Mosquito 3D crossover 几何；论文 8 只在摘要层面证明短 3D 排列变化；论文 9 证明 transition loss 与曲率变化/发射模态有关。[2,8,9] 因此当前模型的恰当表述是：

> “满足项目定义的解析最小曲率半径并具有零端点坡度的候选过渡曲线。”

不应表述为：

> “满足制造约束且低损耗的物理过渡。”

### 可改进曲线

如果目标是消除直线—曲线的曲率跳变，可考虑 quintic smoothstep 高度律 `h(t)=10t³−15t⁴+6t⁵`，其一、二阶导在两端均为零，能实现高度函数的 C2 接续；也可使用 Euler/clothoid、minimum-jerk 或受曲率/曲率变化率约束的样条。选择不能只看解析优美，还需用 BPM 与制造能力比较插损、峰值曲率、占板长度和对邻线的侵占。

### 需要新增的单元测试/验证量（建议，未改代码）

- 数值曲率与解析 `κ(s)` 的误差；
- 端点位置、切向和曲率连续性；
- 三维弧长与额外长度；
- 最大坡度 `π|Δz|/(2Lxy)`；
- 与所有有限包络、器件区和板边界的 swept-volume clearance；
- 不同采样密度下最小距离稳定性；
- BPM 得到的传输矩阵/损耗与曲率、坡长的响应面。

## Parameter Audit

| 项目参数 | 当前值/状态 | 文献证据 | 审计判定 | 建议 |
|---|---|---|---|---|
| 波导宽度 | 0.05 mm | 论文 3 为 50×50 µm；论文 2 约 50 µm 圆芯；论文 6 实测约 46×50 µm。[2,3,6] | `PARTIALLY SUPPORTED`，但平台相关 | 明确是矩形 width、圆芯 diameter 还是碰撞包络；同时指定高度/包层 |
| 路由间距 | 0.125 mm | 文献有 62.5 µm 与 250 µm pitch 等不同值。[2,6,12] | `PROJECT-SPECIFIC / AMBIGUOUS` | 明确 center pitch 或 edge gap；由串扰和工艺标定 |
| 最小弯曲半径 | 5 mm | 特定平台有 R≈1 mm、4 mm、5–13.5 mm 等结果。[2,4,5,9,12] | `CONSERVATIVE ASSUMPTION`, 非通用验证 | 选定材料/芯形后建立 `L_bend(R, angle, launch)`；不要只有阈值 |
| 离散层高 | 0/1/2 mm | 论文 2 局部约 0.7 mm 高差；论文 1 为 7.2 µm 相邻层；论文 11 约 24.5 µm。[1,2,11] | `UNVERIFIED / PLATFORM-MIXED` | 若 Mosquito 路线，用连续可写轨迹与包层厚度定义；若光刻多层，重建设计栈 |
| 3D clearance | 0.1 mm | 没有与当前材料、横截面和发射条件匹配的直接依据 | `UNSUPPORTED CRITICAL PARAMETER` | 拆成芯区几何、工艺包络、光学串扰三个阈值；这是最高优先级 |
| 板尺寸 | 300×200 mm | 论文 6 示例约 150×150 mm；真实系统尺寸依应用而定。[6,15] | `SYNTHETIC DESIGN CHOICE` | 保留为实验场景，但不得称真实设备规格 |
| 层数 | 3 | 文献有 2 层、4 层及局部 3D 轨迹。[1,11,12] | `SYNTHETIC / ARCHITECTURE-SPECIFIC` | 通过制造栈、耦合器/写入可达性和收益曲线决定 |
| PMT 数 | 128 | 当前数据由既有 64/512 场景扩增；未找到对应真实系统 | `NO REAL-SYSTEM BASIS FOUND` | 把它标为 scalability stress test，不写成探测器硬件需求 |
| 路由数 | 1024 | 当前固定问题由 512 路复制构造；公开示例远低于此规模。[15] | `SYNTHETIC` | 分开报告算法规模与真实系统规模；增加多规模曲线 |
| 连通关系 | 固定、复制生成 | 没有传感器/探测器接口规范或真实 netlist | `SYNTHETIC` | 获取端口、扇入扇出、允许交叉与损耗预算后再冻结 |
| 损耗参数 | 配置中为空/未标定 | 各论文数值平台差异大 | `NOT IMPLEMENTED / NOT CALIBRATED` | 先建立证据带标签的数据表，再做模型 |

最需要重审的是 `clearance_3d=0.1 mm`，因为它既是当前碰撞计数的判据，也是层分配优化的驱动力。若该值或含义错误，`204291、138113、175 次 elevation、350 个 transition` 的工程解释都会变化。相比之下，板尺寸即使是合成值，主要影响可扩展性场景，不会直接把合法交叉误判成硬违规。

## Optical Loss Model

### 首版推荐结构

路由内部损耗可先写成事件台账：

`L_route = α_prop(λ, material, profile, process)·ℓ + Σ_i L_bend(R_i, φ_i, profile, launch) + Σ_j L_cross(θ_j, cluster_j, launch) + Σ_k L_transition(Δz_k, Lxy_k, κ_k(s), profile, launch)`。

端到端链路再加：

`L_link = L_in + L_route + L_out + Σ L_connector + L_process_margin`。

同时必须独立报告串扰预算；dB 插损不能代表串扰：

`XT_route = F(crossings, parallel_close_sections, interlayer_overlaps, modes, coherence)`。

### 现阶段可以实现的部分

- 从几何提取总长度、弯曲事件、交叉角、层间过渡的 `Δz/Lxy/κ(s)`、近并行长度与层间投影交叉。
- 将论文 3 的角度拟合仅作为 `photolithographic_polyacrylate_SI_50x50um_853nm` 示例模型，并附大不确定度，不作为项目默认物理真值。[3]
- 把传播、弯曲、交叉、过渡列成 `NOT CALIBRATED` 的独立项，允许场景分析和敏感性分析。
- 对每个系数记录 source、platform、wavelength、core geometry、index profile、launch condition 与 evidence level。

### 现阶段不能可信完成的部分

- 不能用论文 4 的 `<0.1 dB at R≈1 mm` 与论文 3 的 crossing 拟合、论文 6 的传播/连接器数据直接拼成一个“聚合物波导”通用模型；三者芯形、折射率分布、工艺和测试链路不同。[3,4,6]
- 不能假定每个 crossing 独立同分布。重复交叉与聚簇会改变模态分布，后续事件的损耗可能依赖此前事件。[3,9,10]
- 不能把每次升降固定赋一个常数。过渡损耗应依赖高差、坡长、曲率历史、模式与发射条件；当前余弦曲线没有实验/BPM 标定。[2,8,9]
- 不能省略耦合和连接器后仍称端到端 loss budget；论文 5、6 显示这些项可占显著比例。[5,6]

### 缺失系数与最低实验集

1. 选定平台的 cutback `α_prop`，至少在目标波长、层压前后和代表性芯尺寸下测量。
2. `L_bend(R, φ)`：直线参考、多个半径/角度、明确发射条件；同时测近场/模式变化。
3. `L_cross(θ)` 与 crossing crosstalk：覆盖项目角度分布，含单次、重复、聚簇。
4. `L_transition(Δz,Lxy)`：至少对 0.5/1/2 mm 高差与若干坡长，比较余弦、quintic 或实际可写轨迹。
5. `XT_parallel(d,L)` 与 `XT_interlayer(dz,overlap)`：把 clearance 从经验数改为满足串扰预算的响应面。
6. 输入/输出与连接器损耗分布，以及制造批次、公差和温度/层压后的 margin。

结论：足够建立首版结构化损耗台账和敏感性模型；不足以建立可用于设计验收的定量损耗预测。报告数值时必须给出平台标签和置信等级，不能只给单一总 dB。

## Real-System Relevance

当前固定问题的关键事实是：128 个 PMT、1024 routes、2048 endpoints、300×200 mm 板和固定连通关系来自合成扩增/算法压力测试，而不是已识别的探测器背板或商业光互连 netlist。公开聚合物波导示例证明几十到数百通道具有现实相关性，但本次未找到与“128 PMT、每 PMT 8 路、固定 1024 路”对应的系统论文或接口规范。[6,7,15]

因此建议把结论分为两层：

- 算法层：在该固定合成实例中，三维局部抬升将自定义近距 pair 指标从 204,291 降到 138,113；175 次 elevation、350 个 transition，代价约 87.4 mm 额外长度和约 1172.7 s 运行时间。
- 物理层：尚不能据此宣称 32.39% 制造违规消除、1024 路可制造，或损耗满足真实系统预算。需要真实端口尺寸、允许交叉规则、材料/波长、目标 BER/串扰和端到端 loss budget。

算法本质是“二维初始解 + 碰撞引导的贪心局部 elevation”，不是 A*、Dijkstra 或全局最优三维路由。报告应避免使用“全局最优”“无碰撞”或“物理验证完成”等措辞。只剩 4 个 `unresolved` elevation 候选也不代表只剩 4 个硬碰撞，因为终态近距 pair 仍为 138,113，两个量定义不同。

真实系统对接至少需要以下输入：PMT/ASIC/光引擎端口布局与 keep-out；连接器和耦合方向；板栈、材料、波长与制造工艺；每链路速率和功率预算；允许的 insertion loss、crosstalk、BER；热/机械层压条件；可接受的测试和返修策略。

## Recommendations

1. 冻结制造平台选择。在“光刻矩形 SI PCB”和“Mosquito 圆形 GI 连续 3D”之间选定主路线；其后所有规则附 platform ID。
2. 重构 collision schema。先实现 `hard_violation / optical_event / density_metric` 三分法，再讨论算法优劣；保留现有计数但更名，避免历史结果丢失。
3. 将 `clearance_3d` 拆为 `core_envelope_clearance、fabrication_margin、optical_isolation_rule`，明确中心线或边缘定义；从 2D/3D swept envelope 计算硬违规。
4. 交叉事件保留角度。对允许同层交叉的平台，用角度相关损耗和串扰预算；对近共线重合、过小角、聚簇另设规则。
5. 升级 transition 几何。把当前余弦曲线作为 baseline；加入端点二阶导为零的 quintic 或曲率受限样条，比较占板长度、最大坡度、曲率/曲率变化率和碰撞侵占。
6. 开展局部 BPM 标定，不对全板做盲目 FDTD。先对最差的 1/2 mm 高差、最短坡长和密集邻线情形求模式传输矩阵；再用小范围全波/FEM与试样验证。
7. 建立 loss evidence table。每一系数必须包含数值、单位、波长、芯形、GI/SI、材料、制造、发射、测量方法、证据等级和适用范围；没有就写 `NOT CALIBRATED`。
8. 增加规模与真实度分层。将 1024-route 实例标为 synthetic stress test，同时加入来自真实接口的较小 netlist；分别报告运行时间、硬违规、光学事件和估计损耗。
9. 把验收口径改为：`hard_violation_count=0`；每链路损耗/串扰在预算内；制造曲率/坡度/包络合格；算法指标只作次级比较。
10. 后续全文获取优先级：论文 2（最接近 3D crossover）> 论文 4/5（小半径和 VCSEL 耦合）> 论文 6/7（系统与层压）> 论文 1/8（架构/三维器件）。应通过机构订阅、作者公开稿或图书馆文献传递合法补全。

## Gaps and Risks

| 风险 | 严重度 | 当前证据 | 后果 | 缓解 |
|---|---|---|---|---|
| collision 语义混合 | 严重 | 代码与结果明确；文献反证合法 crossing | 优化目标错误，违规降幅被夸大 | 三分法与有限包络 |
| 余弦过渡仅 C1，未做光学验证 | 严重 | 数学推导 + bend transition 文献 | 模态转换/辐射损耗未知 | quintic baseline + BPM + 试样 |
| clearance 0.1 mm 无平台依据 | 严重 | 无匹配来源 | 所有碰撞和分层统计敏感 | 拆分并实验/仿真标定 |
| 跨平台拼接系数 | 高 | 核心论文平台差异显著 | 得到形式完整但物理错误的总损耗 | platform-tagged coefficients |
| 1024 路与真实系统脱节 | 高 | 项目为复制生成；未找到匹配系统 | 可扩展性结论无法落地 | 获取真实 netlist/预算 |
| 7/8 核心全文未取得 | 中到高 | 官方摘要可核验，PDF受限 | 参数、误差条、图表细节不完整 | 机构订阅/作者稿；继续标注证据等级 |
| crossing 独立加和假设 | 中 | 多模事件存在模态记忆 | 密集重复交叉误差累积 | 组件链 BPM/实验 |
| 忽略连接器和耦合 | 高（系统预算） | 论文 5、6 | 端到端损耗被低估 | 分离 route/link loss |
| 层数与层距只作为抽象 z | 高 | 文献显示层连接机制各异 | 可能不可制造或无法耦合 | 完整板栈/写入流程定义 |
| 采样型最小距离漏检 | 中 | 曲线离散化固有风险 | 细小交叠未被计数 | 解析/自适应距离和扫掠体 |

## Sources

[1] M. Weigel et al., “Design and Fabrication of Crossing-Free Waveguide Routing Networks Using a Multi-Layer Polymer-Based Photonic Integration Platform,” *Journal of Lightwave Technology*, 42(5), 1511–1517 (2024). DOI: [10.1109/JLT.2023.3320908](https://doi.org/10.1109/JLT.2023.3320908); [official abstract](https://opg.optica.org/jlt/abstract.cfm?uri=jlt-42-5-1511).

[2] M. O. F. Rasel, A. Yamauchi, and T. Ishigure, “Error-Free Three-Dimensional Multimode Crossover Graded-Index Polymer Waveguides for Board-Level Optical Circuitry,” *Journal of Lightwave Technology*, 40(19), 6465–6473 (2022). DOI: [10.1109/JLT.2022.3193229](https://doi.org/10.1109/JLT.2022.3193229); [official abstract](https://opg.optica.org/jlt/abstract.cfm?uri=jlt-40-19-6465).

[3] H. Baghsiahi, K. Wang, and D. R. Selviah, “Optical loss and crosstalk in multimode photolithographically fabricated polyacrylate polymer waveguide crossings,” *Proc. SPIE* 8988, 898807 (2014). DOI: [10.1117/12.2039860](https://doi.org/10.1117/12.2039860); [UCL open repository](https://discovery.ucl.ac.uk/id/eprint/1434591/). `FULL TEXT VERIFIED`.

[4] M. Karakawa and T. Ishigure, “Fabrication of graded-index core polymer optical waveguides enabling low loss with small bend radius (~1 mm) using high Δ resins,” *Optics Express*, 34(4), 6895–6907 (2026). DOI: [10.1364/OE.582449](https://doi.org/10.1364/OE.582449); [official issue](https://opg.optica.org/oe/issue.cfm?issue=4&volume=34).

[5] N. Kohmu, M. Ishii, R. Hatai, and T. Ishigure, “90°-bent graded-index core polymer waveguide for a high-bandwidth-density VCSEL-based optical engine,” *Optics Express*, 30(3), 4351–4364 (2022). DOI: [10.1364/OE.446899](https://doi.org/10.1364/OE.446899); [official issue](https://opg.optica.org/oe/issue.cfm?issue=3&volume=30).

[6] Y. Shi, X. Liu, L. Ma, M. Immonen, L. Zhu, and Z. He, “Optical printed circuit boards with multimode polymer waveguides and pluggable connectors for high-speed optical interconnects,” *Optics Express*, 31(17), 27776–27786 (2023). DOI: [10.1364/OE.497184](https://doi.org/10.1364/OE.497184); [official issue](https://opg.optica.org/oe/issue.cfm?issue=17&volume=31).

[7] X. Xu, X. Liu, M. Immonen, L. Ma, and Z. He, “Investigation on mode dispersion and lamination stability of multimode polymer waveguides for an optical backplane,” *Optics Express*, 30(22), 40505–40514 (2022). DOI: [10.1364/OE.472218](https://doi.org/10.1364/OE.472218); [official issue](https://opg.optica.org/oe/issue.cfm?issue=22&volume=30).

[8] Y. Yamaguchi, S. Yakabe, and T. Ishigure, “Design and Fabrication of Three-dimensional Polymer Optical Waveguide-based Fan-in/out Device for Multicore Fibers,” ECOC 2022, We3A.3. [Official record](https://opg.optica.org/abstract.cfm?uri=ECEOC-2022-We3A.3). DOI: `NOT FOUND/NOT ASSIGNED` for this ECOC record.

[9] I. Papakonstantinou et al., “Transition, radiation and propagation loss in polymer multimode waveguide bends,” *Optics Express*, 15(2), 669–679 (2007). DOI: [10.1364/OE.15.000669](https://doi.org/10.1364/OE.15.000669).

[10] A. Hashim et al., “Multimode Polymer Waveguide Components for Complex On-Board Optical Topologies,” *Journal of Lightwave Technology*, 31, 3962–3969 (2013). DOI: [10.1109/JLT.2013.2278382](https://doi.org/10.1109/JLT.2013.2278382); [official abstract](https://opg.optica.org/jlt/abstract.cfm?uri=jlt-31-24-3962).

[11] F. Zhang et al., “Optimization of the interlayer distance for low-loss and low-crosstalk double-layer polymer optical waveguides,” *Optics Express*, 31(15), 23754–23766 (2023). DOI: [10.1364/OE.489977](https://doi.org/10.1364/OE.489977).

[12] X. Xu et al., “Directly inscribed multimode polymer waveguide and 3D device for high-speed and high-density optical interconnects,” *Optics Express*, 27(16), 22419–22431 (2019). DOI: [10.1364/OE.27.022419](https://doi.org/10.1364/OE.27.022419).

[13] N. Bamiedakis et al., “Low Loss and Low Crosstalk Multimode Polymer Waveguide Crossings for High-Speed Optical Interconnects,” CLEO 2007, CMG1. [Official abstract](https://opg.optica.org/abstract.cfm?uri=cleo-2007-CMG1).

[14] F. Martinez Abreu, J. J. Imas, A. Ozcariz, C. Elosua, J. M. Corres, and I. R. Matias, “Polymeric Optical Waveguides: An Approach to Different Manufacturing Processes,” *Applied Sciences*, 15, 10644 (2025). DOI: [10.3390/app151910644](https://doi.org/10.3390/app151910644); [open article](https://www.mdpi.com/2076-3417/15/19/10644). Local open-access PDF verified, 27 pages.

[15] IBM Research, “Silicon photonics packaging,” public project page. [Source](https://research.ibm.com/projects/silicon-photonics-packaging), accessed 2026-09-14.

### Local project evidence audited

- `src/geometry_3d.py`: `CosineTransition3D` 参数化、曲率公式和最小过渡长度。
- `src/layer_assignment_3d.py`: 基于碰撞的贪心局部 elevation、层选择与过渡插入。
- `src/collision.py`: 中心线/折线最小距离及阈值语义。
- 项目配置：0/1/2 mm 层、0.1 mm clearance、5 mm 最小弯曲半径、未标定 loss 字段。
- Step 10 固定问题输出：1024 routes、2048 endpoints、`204291→138113`、175 elevations、350 transitions、4 unresolved、额外长度约 87.4066 mm、运行时间约 1172.659 s。
