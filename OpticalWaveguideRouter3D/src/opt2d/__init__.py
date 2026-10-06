"""opt2d —— 光学波导二维布线优化实验模块（独立于 3D 流程）。

本包只做二维研究，复用两个既有项目的资产而不修改它们：

* ``OpticalWaveguideRouter2D``（原版 AutoRouter 的精确复现）提供
  端口排布、原版直角布线与损耗模型；
* 本项目的 ``src.models`` / ``src.geometry`` / ``src.collision`` /
  ``src.physical_intersections`` 提供解析 Line/Arc 表示、解析求交与
  路线对事件归并。

模块分工：

``legacy_bridge``   注入 2D 项目路径并调用其原版布线
``smoothing``       从端点与轨道坐标重建原版圆弧几何（Line/Arc 解析表示）
``geometry_audit``  端点、长度、切向连接核验
``evaluator``       统一评价器：全部交叉事件、去重、两套统计、违规分类
``spacing``         近并行间距检查（实验假设阈值）
``planner``         候选轨道与自适应半径布线器（方案 C/D）
``experiments``     A/B/C/D 编排与产物输出
"""

__all__ = [
    "legacy_bridge",
    "smoothing",
    "geometry_audit",
    "evaluator",
    "spacing",
    "planner",
    "experiments",
]
