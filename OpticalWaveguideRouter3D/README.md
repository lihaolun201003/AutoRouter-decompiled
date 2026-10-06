# OpticalWaveguideRouter3D

本科毕业设计项目：面向固定 1024 条连接的三维光波导自动布线实验。项目从二维解析几何出发，在三层中尝试局部抬升以减少波导间碰撞，并保存可重载的路线与可视化结果。

## 当前成果

- 固定输入由 `data/fixed_1024_legacy_seed.json` 中的 512 条历史连接按确定性规则扩展而来：1024 条波导、128 个 PMT、2048 个唯一端点，实验板尺寸为 300 × 200 mm。
- 二维阶段生成 1024 条解析路线；三维阶段使用 z = 0/1/2 mm 三层、0.1 mm clearance 与 5 mm 最小过渡曲率半径。这些参数是实验设定，并非制造标准。
- 保存的 Step 10 结果中，175 条路线完成一次抬升，碰撞对从 204,291 降至 138,113（减少 32.394%）。1024 次目标尝试达到预设上限；最终另有 4 对未决。结果不能视为无碰撞版图。
- Step 11 从保存的最终路线只读生成 13 张图（各有 PNG/PDF），包括三维总览、分层、XY/XZ 投影、局部抬升示例和统计图。
- 当前测试集为 705 项；本地使用 Python 3.10.11 的 `.venv` 运行通过。

详细方法、统计口径与限制见 [Step 10 路由报告](docs/reports/step_10_fixed_1024_3d_routing.md)和 [Step 11 可视化报告](docs/reports/step_11_1024_3d_visualization.md)。

## 快速使用

在项目根目录运行。现有开发环境是 `.venv`；新环境可使用 Python 3.10 创建虚拟环境并安装 `requirements.txt`。依赖文件尚未锁定版本，重新安装时应记录实际版本。

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

从已有 Step 10 检查点重新生成图片（读取 `outputs/step_10_fixed_1024_final_route_state.json`，写入 `outputs/figures/`）：

```powershell
.\.venv\Scripts\python.exe -B scripts\visualize_fixed_1024_3d.py . outputs
```

完整重跑固定 1024 路由会重新生成实验输出，并执行全量碰撞复核；已有单次记录约 19.5 分钟。建议指定新的输出目录，以便保留现有检查点：

```powershell
.\.venv\Scripts\python.exe -B scripts\run_fixed_1024_3d.py . outputs_reproduction
```

该脚本也支持在项目根目录只运行其内置测试：

```powershell
.\.venv\Scripts\python.exe -B scripts\run_fixed_1024_3d.py . outputs_reproduction --tests-only
```

`main.py` 和 `scripts/run_example.py` 目前只打印提示，不会启动路由。固定 1024 实验参数由 `src/fixed_1024_routing.py` 中的专用配置给出；`config/default.yaml` 仍是通用占位模板，不能直接用于复现该实验。

## 目录与关键产物

| 路径 | 内容 |
| --- | --- |
| `src/` | 数据模型、二维几何与布线、三维几何、clearance、分层实验、统计及绘图代码；职责与状态见 [架构文档](docs/architecture.md) |
| `scripts/` | 实验、验证、审计和可视化入口 |
| `tests/` | 单元和回归测试 |
| `data/fixed_1024_legacy_seed.json` | 固定 1024 输入的本地来源种子 |
| `outputs/step_10_fixed_1024_summary.json` | 路由指标与停止原因 |
| `outputs/step_10_fixed_1024_final_route_state.json` | 1024 条可重建的最终三维路线 |
| `outputs/step_10_fixed_1024_validation.json` | 重载与 523,776 对路线全量复核记录 |
| `outputs/figures/` | Step 11 图像与 PDF |
| `docs/reports/` | 各阶段实验报告及适用范围 |
| `docs/2d_routing/` | 二维布线文件索引、参数状态与端口排布说明 |
| `references/` | 文献索引与已取得的本地资料 |
| `thesis/` | 论文格式模板和写作说明；尚无论文正文 |

## 当前边界

项目完成了固定数据集上的二维路线构造、局部三层抬升、碰撞统计和结果展示。通用 `Router3D.route`、通用导入导出、优化器、指标接口与旧 `visualize.py` 接口仍为占位；没有 GUI 或 GDS 输出。现有长度统计不等于经实测标定的光学损耗，论文和制造可行性仍需进一步论证。
