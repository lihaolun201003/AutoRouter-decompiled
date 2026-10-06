# OpticalWaveguideRouter2D 汇报讲稿（三步版）

按“解码、复现、波导图与论文对比”讲述。损耗数字为论文级估计模型结果，并非物理实验。

## 第 1 页：封面

这次汇报只讲三步。第一步，从旧 AutoRouter.exe 解出程序。第二步，在 Python 3.10 中复现并证明路由结果与原版一致。第三步，展示生成的波导图，把估计损耗与黄志杰论文中的数字对比。

**资料来源：** README.md；migration_report.md

## 第 2 页：三步总览

整项工作按三步展开：先从可执行程序找回代码，再把它迁移到 Python 3.10，并和旧程序逐条比较，最后展示真实生成的波导图，以及论文级损耗模型复现结果。

**资料来源：** README.md；exact_legacy_fidelity_report.md；loss_model_reconstruction_report.md

## 第 3 页：为什么解码

黄志杰论文解释了二维光波导排布的思路，但真正执行的细节在旧 AutoRouter 程序里。原 GitHub 的反编译源码说明仅通过语法检查，尚未验证运行行为。为了建立可靠的二维基线，需要回到 EXE 中确认程序实际怎么运行。

**资料来源：** 原始 GitHub README；migration_report.md

## 第 4 页：解码工具

这里展示的是 PyInstaller Extractor 的项目页面截图。我们用它从 AutoRouter.exe 提取打包内容，得到 Python 字节码，再把字节码还原为可读代码。反编译结果不能直接当作正确源码，所以后面还要用原程序运行行为核对。

**资料来源：** 用户提供截图；migration_report.md

## 第 5 页：解码结果

解码后可以看到四块主要逻辑：端口放置、直角布线、圆弧生成与损耗计算。反编译有时会把缩进和判断还原错，我们对照字节码与原版运行结果修正这些错误。目标是恢复旧程序本来的算法，而不是重新发明一个算法。

**资料来源：** migration_report.md

## 第 6 页：复现流程

复现版用 Python 3.10.11，直接读取项目中的 256 和 512 通道输入表。流程是端口放置、波导布线、圆弧生成，最后输出 GDS、图片和 Excel。这个流程也保留了 GUI 和命令行入口。

**资料来源：** README.md；migration_report.md；两张输入 Excel

## 第 7 页：精确复现证据

我们把原版字节码放回它原来的 Python 3.8 环境实际运行，再与 Python 3.10 复现版逐条对比。512 根波导的端口、布线轨道、弯曲参数和 GDS 路径全部一致。GDS 文件只有自身记录的时间戳不同。

**资料来源：** exact_legacy_fidelity_report.md；exact_fidelity_gate.py

## 第 8 页：历史 PDF 差异

一开始用旧文件夹里的 2020 年 PDF 图比较，只对上 266 根。继续追踪后发现，该图来自另一版 AutoRouter。用本次解码的 EXE 在原 Python 3.8 环境实际运行，复现版 512 根全部一致。因此选原 EXE 的运行结果作为基准。

**资料来源：** debug_first_divergence.md；exact_legacy_fidelity_report.md

## 第 9 页：256 通道波导图

这是复现版使用 fiberBoard256.xlsx 输入后直接生成的 256 通道弯曲波导图。横纵坐标单位为毫米，红色曲线是实际布线路径。这里展示的是程序输出，不是重新画的示意图。

**资料来源：** fiberBoard256bend.png；fiberBoard256.xlsx

## 第 10 页：512 通道波导图

这张是与用户给出的参考图同样样式的项目实际输出。512 根波导在 150 毫米见方的布线区域里完成排布，图中可看出波导密度高于 256 通道。后面损耗对比的 512 R5 场景就基于这组路由结果。

**资料来源：** fiberBoard512bend.png；fiberBoard512.xlsx

## 第 11 页：损耗计算

论文把总损耗分成弯曲、直线和交叉三项。直线损耗的系数是 0.05 dB/cm。弯曲损耗按论文表 3-1 的半径数据计算。交叉损耗所需的原始表没有找到，所以从论文图 3-12 数字化估算；整个损耗模型状态写 PARTIAL。

**资料来源：** 黄志杰论文；loss_model_reconstruction_report.md

## 第 12 页：与论文数值对比

把论文中明确报告的三组场景拿出来，比较平均损耗与最大损耗。256 R5、512 R5、512 R4 的复现值都能四舍五入到论文所印的一位小数。六个比较值中最大相对误差是 1.05%。这支持论文级损耗数值复现，但交叉部分仍是近似。

**资料来源：** 三个 loss summary JSON；loss_model_reconstruction_report.md

## 第 13 页：损耗贡献

这两张图直接来自 results。以 512 通道、5 毫米半径为例，平均弯曲损耗为 4.5587 dB，占总平均损耗的 82.7%；直线占 11.5%，交叉占 5.8%。半径扫描图也显示更小的弯曲半径会显著增加损耗。这里仍是论文模型估计结果。

**资料来源：** fiberBoard512_loss_summary.json；两张 results 损耗图

## 第 14 页：总结与 3D 下一步

现在我们有一个可靠的二维路由基线，也有一套来源明确的论文级损耗评价口径。下一步进入三维路由，处理多层、最小间距和冲突后的重布线，再用布通率、长度、损耗和冲突数量与二维结果对比。交叉损耗的原始表缺失会继续清楚标注。

**资料来源：** README.md；exact_legacy_fidelity_report.md；loss_model_reconstruction_report.md
