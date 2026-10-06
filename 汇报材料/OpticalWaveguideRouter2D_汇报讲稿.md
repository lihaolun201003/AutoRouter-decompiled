# OpticalWaveguideRouter2D 阶段汇报讲稿

> 对应 15 页 PPT。所有损耗均为论文级估计模型结果，不代表物理实验验证。

## 第1页｜封面

本次汇报说明两个成果：旧版 AutoRouter 的 Python 3.10 行为级精确复刻，以及依据黄志杰论文重建的损耗评价模型。复刻版本用于后续 3D Router 的二维基线。

**资料来源：** README.md；黄志杰论文

## 第2页｜背景与动机

旧版 AutoRouter 是论文中的二维路由算法工程实现。为了评价新的三维算法，需要先固定二维参考行为与评价口径。这里的工作重点是复现原始程序真实输出，并能解释每个损耗分量的来历。

**资料来源：** migration_report.md；黄志杰论文

## 第3页｜原始程序的工程问题

原始来源是 Python 3.8 可执行文件及反编译代码。旧 README 明确提示仅通过 syntax check，行为未与原程序核验。主要风险不是语言版本本身，而是反编译后的控制流可能改变算法结果。

**资料来源：** 原始 GitHub README；migration_report.md

## 第4页｜复刻范围与处理链

输入是 256 或 512 通道工作簿中的 Port1、Port2。流程依次完成端口放置、直角布线、圆弧弯曲、GDS 与图像及 Excel 输出，最后计算长度、交叉与估计损耗。工程同时保留 GUI 和 CLI，并增加测试与验证工具。

**资料来源：** README.md；migration_report.md；exact_fidelity_gate.py；analyze_loss.py

## 第5页｜Exact Legacy Fidelity：三层证据

验证不依赖肉眼相似。先从原版字节码判定控制流，再用 Python 3.8.10 和当年依赖执行原版代码对象，然后同 Python 3.10 复刻结果逐阶段比较。512 条路由的端口、轨道、弯曲参数及 GDS 点列和线宽一致。GDS 文件本体只有 8 字节时间戳差异。

**资料来源：** exact_legacy_fidelity_report.md；exact_fidelity_gate.py

## 第6页｜关键反编译错误修复

这些修复的原则是恢复原程序的语义，而不是调整路由策略。比如 find_next 的 return 位置和 noCross 的布尔条件链，都由字节码中的跳转与原版 runtime 对照确认。NumPy 2 的 repr 变化属于输出兼容问题，避免 Excel 回读失败。

**资料来源：** migration_report.md；loss_model_reconstruction_report.md

## 第7页｜2020 PDF 与原 EXE 的版本差异

最初把 2020 年生成的 PDF 当成基准，只得到 266/512 exact。排查首个分歧后，发现它来自另一个 AutoRouter build。通过运行当前 EXE 中提取的原始代码对象，复刻版达到 512/512 exact。因此本项目以原版可执行程序的运行行为作为 ground truth，历史 PDF 仅用于说明版本差异。

**资料来源：** debug_first_divergence.md；exact_legacy_fidelity_report.md

## 第8页｜仓库发布与可复现工程

GitHub 的 c1da72b 提交把反编译原型替换为 Python 3.10 正式工程，v1.0-legacy-exact 标签可作为路由基线。旧代码仍可从 Git 历史追溯。环境和生成结果没有纳入该提交，数据、报告、验证工具与测试已纳入。损耗模型的本地后续工作应与该发布状态区分。

**资料来源：** GitHub commit c1da72b；GitHub tag v1.0-legacy-exact；README.md

## 第9页｜论文 3.3.2 节的损耗模型

论文式 3-19 将每根波导损耗分为对称的两段弯曲、直线传播与所有交叉插入损耗。直波导系数 0.05 dB/cm 来自论文表 2-1。弯曲项从论文表 3-1 与原版内部数据恢复，交叉项因原始表缺失只能采用图 3-12 的近似数字化。

**资料来源：** 黄志杰论文；loss_model_reconstruction_report.md

## 第10页｜弯曲损耗：由原版 tl / ll 恢复

论文表 3-1 的五个半径值可以由原版程序硬编码的 tl 和 ll 两表求出损耗密度，再乘 90 度弧长得到。原版计算使用未四舍五入的密度，故 R=5 时内部值约 2.3826 dB，论文印刷为 2.39 dB。小于 90 度时按照角度线性折算，与原版按弧长累积完全等价。

**资料来源：** 黄志杰论文；loss_model_reconstruction_report.md

## 第11页｜交叉损耗：近似数据与边界

原版 calc_loss 会读取一张 crossing loss 表，但它没有随 EXE 或 PYZ 发布。本项目把论文图 3-12 的 30 次交叉曲线数字化为角度表，再用论文给出的 90 度、30 次交叉约 0.05 dB 进行锚定。这个表只有趋势与论文级近似的意义，不能称为原始模型完整复原，因此状态明确写 PARTIAL。

**资料来源：** loss_model_reconstruction_report.md；crossing_loss_from_thesis_fig3_12.csv；黄志杰论文

## 第12页｜论文关键结果复现

对 256 R5、512 R5 和 512 R4 三个论文明确给数值的场景，复现平均值和最大值均在一位小数印刷精度内。六个比较值中的最大相对误差为 1.05%，来自 256 R5 的最大损耗。这里没有针对目标结果调参，但交叉表仍是数字化近似，故只称论文级损耗结果复现。

**资料来源：** 三个 loss summary JSON；loss_model_reconstruction_report.md

## 第13页｜512 通道 R5：损耗贡献与趋势

这四张图直接来自 results。512 R5 的逐路由平均损耗为 5.5147 dB，其中弯曲占 82.7%，直线占 11.5%，交叉占 5.8%。从损耗分布、与长度和交叉数的关系，以及不同半径扫描可看到弯曲半径是主要因素。这与论文第四章的趋势一致，但图中数值是模型估计而非测量。

**资料来源：** fiberBoard512_loss_summary.json；results 中四张 loss 图

## 第14页｜当前成果的两个版本

两个版本承担不同作用。v1.0 固定原版 2D 算法的路由和 GDS 行为，属于 exact baseline。v1.1 增加论文损耗评价口径，在直线和弯曲部分有明确来源，交叉部分受原表缺失限制，因此标记 PARTIAL。后续 3D 算法可用同一组输入与指标对照。

**资料来源：** README.md；exact_legacy_fidelity_report.md；loss_model_reconstruction_report.md

## 第15页｜下一阶段：OpticalWaveguideRouter3D

下一阶段进入 OpticalWaveguideRouter3D，处理空间坐标、多层、几何约束和冲突后的 rip-up and reroute。先在 512 通道上与二维基线对照，再扩展至 1024 通道。比较指标包括布通率、总长度、平均与最大估计损耗、均衡性、交叉或冲突数量，以及输出几何和可视化。2D 项目保持冻结参考实现。

**资料来源：** README.md；毕设目标
