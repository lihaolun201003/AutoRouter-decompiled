# Core physics literature index

最后更新：2026-09-14。范围：为 `OpticalWaveguideRouter3D` 的三维聚合物多模波导布线、弯曲、交叉、层间过渡、串扰与损耗建模建立可追溯证据链。

## 使用规则

- `FULL TEXT VERIFIED`：本地保存且已逐页核验全文；只有此等级可支撑正文、图表、公式和实验条件的精确引用。
- `ABSTRACT VERIFIED`：在出版社/机构库核验题名、作者、出版信息与摘要；不能把摘要未给出的参数写成论文结论。
- `SNIPPET-ASSISTED`：除官方摘要外，还使用搜索索引可见的正文片段定位参数；报告中均明确标注，不能等同全文阅读。
- `NOT OBTAINED`：截至本次检索没有取得可合法保存的全文。没有绕过登录、付费墙、机器人验证或出版社访问控制。
- 不同平台的数据不可直接拼接：光刻矩形阶跃型、Mosquito 圆形渐变型、薄膜多层 PolyBoard、PCB 嵌入式波导分别保留平台标签。
- `NOT REPORTED` 表示所核验层级中未报告，不表示原论文全文必然没有。

## 八篇核心论文

| # | 论文与稳定标识 | 出版与作者 | 获取/核验状态 | 本地文件 | 与项目相关的已核实信息 | 不能据此声称 |
|---|---|---|---|---|---|---|
| 1 | *Design and Fabrication of Crossing-Free Waveguide Routing Networks Using a Multi-Layer Polymer-Based Photonic Integration Platform*. DOI: [10.1109/JLT.2023.3320908](https://doi.org/10.1109/JLT.2023.3320908)；[Optica/JLT](https://opg.optica.org/jlt/abstract.cfm?uri=jlt-42-5-1511) | *Journal of Lightwave Technology* 42(5), 1511–1517 (2024). Madeleine Weigel et al. | `ABSTRACT VERIFIED`; `NOT OBTAINED`. 官方页标为开放获取，但本次自动访问 PDF 被站点验证拦截；Fraunhofer 机构库条目也被机器人验证拦截。 | 无 | 四层聚合物堆叠、16×4 无平面交叉网络；相邻层间距 7.2 µm、顶底 21.6 µm；用垂直 1×1 3D MMI 与多层沉积/平坦化。 | 不能把该薄膜光子集成平台的微米级层距直接用于板级 50 µm 多模 Mosquito 波导；未全文核实的损耗细节为 `NOT REPORTED`。 |
| 2 | *Error-Free Three-Dimensional Multimode Crossover Graded-Index Polymer Waveguides for Board-Level Optical Circuitry*. DOI: [10.1109/JLT.2022.3193229](https://doi.org/10.1109/JLT.2022.3193229)；[Optica/JLT](https://opg.optica.org/jlt/abstract.cfm?uri=jlt-40-19-6465) | *Journal of Lightwave Technology* 40(19), 6465–6473 (2022). Md Omar Faruk Rasel, Akira Yamauchi, Takaaki Ishigure. | `ABSTRACT VERIFIED`, `SNIPPET-ASSISTED`; `NOT OBTAINED`. 官方 PDF 请求被访问控制拦截。 | 无 | Mosquito 法、SUNCONNECT 有机-无机混合聚合物、约 50 µm 圆形抛物线 GI 芯；12 通道、6×6、250 µm 节距；两组波导各上下偏移 0.35 mm，交叉处约 0.7 mm 高差，约 30 mm 斜坡；弯曲半径 4 mm、投影交叉角 13°；850 nm 平均插损 1.64 dB（排除两条受灰尘影响通道），串扰低于 −45 dB，26 Gb/s 无误码。 | 这些数值不能证明任意 1 mm 离散层距、任意短过渡或项目中的余弦过渡都满足同样损耗。1.64 dB 也不是纯过渡损耗。 |
| 3 | *Optical loss and crosstalk in multimode photolithographically fabricated polyacrylate polymer waveguide crossings*. DOI: [10.1117/12.2039860](https://doi.org/10.1117/12.2039860)；[UCL 开放仓储](https://discovery.ucl.ac.uk/id/eprint/1434591/) | Proc. SPIE 8988, 898807 (2014). Hadi Baghsiahi, Kai Wang, David R. Selviah. | `FULL TEXT VERIFIED`，7 页。 | `03_crossing_loss_angle_SPIE2014.pdf`；438,666 B；SHA-256 `B61AD97D442CEA2B11837B5C9B4D9FFB92FB6D80D60B3EFECDBA5BE93A97FE02` | FR4 上光刻 Truemode 聚丙烯酸酯阶跃型多模波导，50×50 µm；n_core=1.5560、n_clad=1.5264；853 nm。每种角度串联 6 个交叉并重复测量；约 10° 时每交叉损耗约 0.15 dB，随角度增大下降，90° 附近约 0.02 dB（均为图读近似）；图 5 拟合约为 `1.0779·θ^-0.873 dB/crossing`，θ 以度计。小于约 20° 的简单射线模型明显高估实验损耗，发射模态分布/NA 很重要。 | 论文题名含 crosstalk，但所取得 7 页正文没有给出可用的定量串扰结果，故本报告对该项记 `NOT REPORTED`；图读值不能当高精度标定系数。 |
| 4 | *Fabrication of graded-index core polymer optical waveguides enabling low loss with small bend radius (~1 mm) using high Δ resins*. DOI: [10.1364/OE.582449](https://doi.org/10.1364/OE.582449)；[Optics Express 卷期页](https://opg.optica.org/oe/issue.cfm?issue=4&volume=34) | *Optics Express* 34(4), 6895–6907 (2026). Masahiro Karakawa, Takaaki Ishigure. | `ABSTRACT VERIFIED`; `NOT OBTAINED`. | 无 | Mosquito 法圆形 GI 多模聚合物波导；高 Δ 树脂使半径约 1 mm 的 90° 弯曲损耗低于 0.1 dB。 | 摘要未给出的芯径、折射率、完整测量条件和可制造公差均为 `NOT REPORTED`；不能把 1 mm 当作跨材料通用最小半径。 |
| 5 | *90°-bent graded-index core polymer waveguide for a high-bandwidth-density VCSEL-based optical engine*. DOI: [10.1364/OE.446899](https://doi.org/10.1364/OE.446899)；[Optics Express 卷期页](https://opg.optica.org/oe/issue.cfm?issue=3&volume=30) | *Optics Express* 30(3), 4351–4364 (2022; online 2021-12-30). Naohiro Kohmu, Maho Ishii, Ryosuke Hatai, Takaaki Ishigure. | `ABSTRACT VERIFIED`, `SNIPPET-ASSISTED`; `NOT OBTAINED`. | 无 | Mosquito 法、90° 圆形 GI 多模波导；850 nm 总插损约 2 dB，包含输入/输出耦合、弯曲与传播；高折射率树脂间隙使耦合损耗降低约 5 dB。片段显示器件约 5 mm 长、R≈1 mm，且研究 10/30/50/70 µm 芯径、芯径与 NA 优化。 | 约 2 dB 不能作为纯弯曲损耗；局部耦合结构结果不能直接标定长距离板级路由。 |
| 6 | *Optical printed circuit boards with multimode polymer waveguides and pluggable connectors for high-speed optical interconnects*. DOI: [10.1364/OE.497184](https://doi.org/10.1364/OE.497184)；[Optics Express 卷期页](https://opg.optica.org/oe/issue.cfm?issue=17&volume=31) | *Optics Express* 31(17), 27776–27786 (2023). Ying Shi, Xu Liu, Lin Ma, Marika Immonen, Longxiu Zhu, Zuyuan He. | `ABSTRACT VERIFIED`, `SNIPPET-ASSISTED`; `NOT OBTAINED`. | 无 | 8 电层+1 光层 PCB；10 cm 波导加两个连接器的平均插损 6.42 dB；耦合损耗 0.77 dB/接口；30 Gb/s/通道。片段显示光成像聚合物，n_core≈1.569、n_clad≈1.544、NA≈0.28，材料损耗约 0.05–0.07 dB/cm（850 nm），实测芯约 46×50 µm、节距 250 µm。 | 总插损不可拆成项目所需的弯曲、交叉和过渡独立系数；连接器损耗不能忽略后再复用总值。 |
| 7 | *Investigation on mode dispersion and lamination stability of multimode polymer waveguides for an optical backplane*. DOI: [10.1364/OE.472218](https://doi.org/10.1364/OE.472218)；[Optics Express 卷期页](https://opg.optica.org/oe/issue.cfm?issue=22&volume=30) | *Optics Express* 30(22), 40505–40514 (2022). Xiao Xu, Xu Liu, Marika Immonen, Lin Ma, Zuyuan He. | `ABSTRACT VERIFIED`; `NOT OBTAINED`. | 无 | 50 µm GI 多模光纤中心发射；40 与 70 µm 宽波导比较，后者因更大模态色散产生约 1 dB 代价；高温高压层压前后 80 通道平均插损分别 0.137 与 0.192 dB/cm；25 Gb/s 无误码。 | 摘要不能证明项目中的层间高度、余弦过渡或 1024 通道路由可按相同统计扩展。 |
| 8 | *Design and Fabrication of Three-dimensional Polymer Optical Waveguide-based Fan-in/out Device for Multicore Fibers*. [ECOC 2022 官方记录](https://opg.optica.org/abstract.cfm?uri=ECEOC-2022-We3A.3) | ECOC 2022 Technical Digest, We3A.3. Yuto Yamaguchi, Sho Yakabe, Takaaki Ishigure. | `ABSTRACT VERIFIED`; 官方页标记 `Not Accessible`; `NOT OBTAINED`. | 无 | Mosquito 法制作约 10 mm 长、四芯、三维变化排列的 MCF fan-in/out。 | ECOC 官方记录未显示 DOI，故记 `DOI NOT FOUND/NOT ASSIGNED`。Keio 页面上的 DOI `10.1109/ICSJ55786.2022.10034708` 属于同题名的 ICSJ 2022 版本，不能冒充 ECOC We3A.3 的 DOI。摘要也不足以给出定量过渡损耗。 |

## 补充来源

以下来源用于补足核心论文没有覆盖的弯曲损耗分解、层间距、复杂组件拼接及真实通道规模；均不得替代核心论文身份。

1. I. Papakonstantinou et al., “Transition, radiation and propagation loss in polymer multimode waveguide bends,” *Optics Express* 15(2), 669–679 (2007), DOI [10.1364/OE.15.000669](https://doi.org/10.1364/OE.15.000669). 弯曲损耗分解与发射条件/几何依赖。
2. A. Hashim et al., “Multimode Polymer Waveguide Components for Complex On-Board Optical Topologies,” *JLT* 31, 3962–3969 (2013), DOI [10.1109/JLT.2013.2278382](https://doi.org/10.1109/JLT.2013.2278382). 复杂板上组件、交叉与发射条件。
3. F. Zhang et al., “Optimization of the interlayer distance for low-loss and low-crosstalk double-layer polymer optical waveguides,” *Optics Express* 31(15), 23754–23766 (2023), DOI [10.1364/OE.489977](https://doi.org/10.1364/OE.489977). 20×20 µm 双层平台的 24–24.5 µm 层距与串扰优化。
4. X. Xu et al., “Directly inscribed multimode polymer waveguide and 3D device for high-speed and high-density optical interconnects,” *Optics Express* 27(16), 22419–22431 (2019), DOI [10.1364/OE.27.022419](https://doi.org/10.1364/OE.27.022419). 直接写入圆芯、R=4 mm 弯曲、双层/3D 器件。
5. N. Bamiedakis et al., “Low Loss and Low Crosstalk Multimode Polymer Waveguide Crossings for High-Speed Optical Interconnects,” CLEO 2007, CMG1, [官方摘要](https://opg.optica.org/abstract.cfm?uri=cleo-2007-CMG1). 90° 低损耗交叉概念依据。
6. F. Martinez Abreu et al., “Polymeric Optical Waveguides: An Approach to Different Manufacturing Processes,” *Applied Sciences* 15, 10644 (2025), DOI [10.3390/app151910644](https://doi.org/10.3390/app151910644). 开放综述，用于制造路线分型。本地文件：`S06_polymeric_waveguide_manufacturing_review_2025.pdf`，27 页，5,378,201 B，SHA-256 `E6371F3970D79714C98DB2ABED00AC0B0BF2EE7DA04BD6862D1270290B45C185`，已核验题名、作者、页数与 PDF 文件有效性。
7. IBM Research, [Silicon photonics packaging / polymer waveguide demonstrations](https://research.ibm.com/projects/silicon-photonics-packaging). 用于核对公开系统级通道数量级，不用于器件损耗标定。

## 获取失败与复现说明

- Optica/IEEE 的多个公开着陆页可访问，但 PDF 端点在本次环境返回机器人验证 HTML、HTTP 418 或访问控制页面；这些响应均未保留为 `.pdf`。
- Fraunhofer 机构库对论文 1 显示开放获取，但下载进入 Anubis 验证页；ResearchGate 只出现作者上传/许可片段，未取得可验证文件。
- 对所有失败项均保留 DOI 与官方着陆页，便于人工在机构订阅或作者主页中继续查找。
- 本目录只有文件名以 `.pdf` 结尾且通过 `%PDF-` 文件头和页数检查的文件才计为成功下载；截至本次为 1/8。
