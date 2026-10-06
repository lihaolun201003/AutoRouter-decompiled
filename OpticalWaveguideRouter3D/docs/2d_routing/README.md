# 二维布线资料

此目录专门整理 **256/512 波导二维布线** 的规则、参数状态与文件索引。现有 `src/`、`scripts/`、`tests/` 和 `docs/reports/` 的文件保留在原位置，以维持 Python 导入、实验复现命令及历史检查点中的路径和哈希。1024 是后续三维实验规模，不作为这里的二维研究对象。

## 从这里开始

- [参数、损耗与端口排布](parameters_and_ports.md)：区分已实现的实验设定、前代数据和仍未确定的设计要求。
- [根目录说明](../../README.md)：项目整体状态和运行入口。
- [系统架构](../architecture.md)：二维到三维的数据流。

## 二维代码与测试

| 主题 | 文件 |
| --- | --- |
| 端口、连接与二维路线模型 | [`src/models.py`](../../src/models.py) |
| U/Z 分类、轨道生成与分配 | [`src/router_2d.py`](../../src/router_2d.py) |
| 正交路线、解析 Line/Arc 与 special-Z 平滑 | [`src/geometry.py`](../../src/geometry.py) |
| 二维曲线交叉与物理事件归并 | [`src/collision.py`](../../src/collision.py)、[`src/physical_intersections.py`](../../src/physical_intersections.py) |
| 多波导交叉及归因分析 | [`src/multi_crossing.py`](../../src/multi_crossing.py)、[`src/multi_attribution.py`](../../src/multi_attribution.py) |
| 传播、弯曲及二维已知损耗分析 | [`src/loss.py`](../../src/loss.py)、[`src/loss_analysis.py`](../../src/loss_analysis.py) |
| 相应测试 | [`tests/test_router_2d.py`](../../tests/test_router_2d.py)、[`tests/test_geometry.py`](../../tests/test_geometry.py)、[`tests/test_loss_analysis.py`](../../tests/test_loss_analysis.py) |

## 数据与原始记录

- [`source_data/fiberBoard256.xlsx`](source_data/fiberBoard256.xlsx)：原始 256 PMT 连线表，256 行、两列；SHA-256 `50dadf81426b3a1e56b67ff827809c4a3ab4af92e9b05da411072f850cce9a8b`。
- [`source_data/fiberBoard512.xlsx`](source_data/fiberBoard512.xlsx)：原始 512 PMT 连线表，512 行、两列；SHA-256 `71a19ec1739de75453608d1d9bd0bb2b9ad102140e4af5057c12e60c0accd7ff`。
- [`source_data/fiberBoard0data.xlsx`](source_data/fiberBoard0data.xlsx)：512 条连接对应的端点坐标快照，512 行、11 列；SHA-256 `6901bd1f15388cf15831b57297be9a6a6f51efd661196e282dc5f1bbd6a8770`。
- [256/512 输入验证](../reports/step_8_legacy_input_validation.md)：两种规模的连接表、PMT 和端口数量。
- [256/512 布局审计](../reports/step_8_legacy_layout_audit.md)：512 快照坐标、256 论文参数及未确认项。
- [512 轨道分配](../reports/step_8_legacy_512_track_assignment_v01.md)：宽度、间隔、半径和轨道策略。
- [512 已知损耗分析](../reports/step_8_5_loss_and_angle_v01.md)：传播、弯曲估算与交叉角；交叉损耗未计算。
- [512 端点快照](../reports/step_8_legacy_512_snapshot.md)：64 个 PMT、1024 个端点的坐标验证。

其他二维阶段报告保存在 `docs/reports/step_8_*.md` 和 `docs/reports/step_8_5_*.md`；它们是历史实验记录，本文档不会覆盖其结论。

这三份工作簿是从 `C:\Users\lihao\Desktop\Graduation Project\自动排布` 复制的只读资料副本，原件未修改。该目录顶层的 256/512 工作簿与 `AutoRouter/` 内同名文件的 SHA-256 相同；512 坐标快照来自 `AutoRouter/fiberBoard0data.xlsx`。目录还含 256 布线演示视频，但视频不等于可校验的数值端口坐标表。
