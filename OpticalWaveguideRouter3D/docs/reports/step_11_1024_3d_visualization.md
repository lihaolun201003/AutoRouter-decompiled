# Step 11 — 1024-Channel 3D Visualization

## 1. Scope
**PASS**。仅从 Step 10 最终状态重建并绘图；未运行 routing、assignment 或 523,776 pair 扫描。未修改任何 Route3D、层分配或 collision 结果。

## 2. Input Checkpoint
1024 Route3D；Layer 0/1/2 路线状态为 849/72/103；175 条抬层路线、350 个 transition，全部匹配。最终状态 SHA256：`3ec2cbeea000d742689d8765788fe81eb54837aef6d667cb71430af7fe28fbe8`。可视化前后所有 Step 10 正式输出及报告哈希一致，明细见 summary。

## 3. Visualization Method
`src/visualize_3d.py` 与 `scripts/visualize_fixed_1024_3d.py` 提供只读绘图入口，保留原 2D 绘图。白底、Layer 0 灰实线、Layer 1 蓝实线、Layer 2 橙虚线、transition 紫点线；整体低层细线半透明，局部加粗。所有 13 张图均为 300 dpi PNG 和 PDF。

## 4. Primitive Sampling
Line 两端点；Arc 按扫角以 pi/64 为步长确定点数，限制 12～65；Cosine 49 点，直接调用真实解析 point_at。总计 89534 个显示采样点。采样不写回 geometry、不重算 collision 或正式长度。

## 5. Full 1024 Overview
整体包含全部 1024 路线、300×200 mm 板框、上下边端点、三层。真实比例版本保留 300:200:2 轴比例，Z 很薄是实际尺度；展示版本放大 Z。

## 6. Layer Views
三个独立图只纳入真实 z=0/1/2 的平面 primitive，排除 transition；不会将整条抬层路线误算到高层。平面段计数：{'0': 4555, '1': 360, '2': 491}。路线状态柱状图与平面段计数含义不同。

## 7. XY Projection
显示全部路线 XY 投影、板框、2048 端点及 128 个 PMT 简化线段，无全量文字标签。

## 8. Elevation Examples
固定规则：在每层具有两个完整 transition 的路线中，选择高层平面总长度最短者，相同则 route_id 最小。因此 Layer 1 为 **153**，Layer 2 为 **152**。选择不改变 routing，也不按碰撞收益筛选。局部图隔离目标路线，保留完整 rise/high/fall，低层相邻直线仅显示最多 10 mm 尾段；图标题明确裁剪，数据未裁剪。

## 9. Z Exaggeration
仅显示数组 z×20，并将轴刻度标回真实 0/1/2 mm；标题明确 visual exaggeration。真实比例图同时保留。侧视图使用真实坐标值但纵横显示比例不同，标题注明。XZ 为全体投影，局部侧图沿 transition 水平方向投影，可能发生 U 形两侧重叠，结合 3D 局部图阅读。

## 10. Statistics Figures
路线状态柱图 849/72/103；collision 柱图读取并核对 Step 10 保存值 204291/138113，减少 66178（32.394%）；未重新计算碰撞。

## 11. Generated Files
13 张图，26 个 PNG/PDF 文件：
- `outputs/figures/step_11_1024_3d_overview.png`
- `outputs/figures/step_11_1024_3d_overview.pdf`
- `outputs/figures/step_11_1024_3d_overview_z20.png`
- `outputs/figures/step_11_1024_3d_overview_z20.pdf`
- `outputs/figures/step_11_layer_0.png`
- `outputs/figures/step_11_layer_0.pdf`
- `outputs/figures/step_11_layer_1.png`
- `outputs/figures/step_11_layer_1.pdf`
- `outputs/figures/step_11_layer_2.png`
- `outputs/figures/step_11_layer_2.pdf`
- `outputs/figures/step_11_1024_xy_projection.png`
- `outputs/figures/step_11_1024_xy_projection.pdf`
- `outputs/figures/step_11_layer1_elevation_example.png`
- `outputs/figures/step_11_layer1_elevation_example.pdf`
- `outputs/figures/step_11_layer1_elevation_side.png`
- `outputs/figures/step_11_layer1_elevation_side.pdf`
- `outputs/figures/step_11_layer2_elevation_example.png`
- `outputs/figures/step_11_layer2_elevation_example.pdf`
- `outputs/figures/step_11_layer2_elevation_side.png`
- `outputs/figures/step_11_layer2_elevation_side.pdf`
- `outputs/figures/step_11_1024_xz_side.png`
- `outputs/figures/step_11_1024_xz_side.pdf`
- `outputs/figures/step_11_layer_usage_bar.png`
- `outputs/figures/step_11_layer_usage_bar.pdf`
- `outputs/figures/step_11_collision_reduction_bar.png`
- `outputs/figures/step_11_collision_reduction_bar.pdf`

可复现命令（项目根目录）：`.venv\Scripts\python.exe -B scripts\visualize_fixed_1024_3d.py . outputs`。
requirements.txt 已声明 numpy/matplotlib，但未指定版本。经用户明确授权，仅安装二者及必要依赖：NumPy **2.2.6**、Matplotlib **3.10.9**，Python 3.10.11；安装日志保存为 `outputs/step_11_dependency_install.log`。未安装 GUI、CAD、3D 引擎或其他非必要库。

## 12. Tests
**705/705 PASS = 历史 696 + 新增 9**。覆盖加载、三类采样端点、真实层分类、确定示例选择、仅显示放大、文件签名/非空与只读 SHA256。全部 PNG 已目视检查，紧凑案例另行检查；PDF 与 PNG 从同一 Figure 导出。图生成耗时 6.622 秒，不包含安装和测试。

## 13. Limitations
图为可视化，不是无碰撞或制造可行证明。最终仍有 138113 collision pairs 和 4 对未决，层参数保持实验含义。整体拥挤处透明线可能遮叠，采用独立层图和局部图辅助阅读。放大版本不表示真实高度比例。

## 14. Verdict
**Step 11：PASS**。本报告、summary、测试日志和 26 个图文件组成 checkpoint。未修改 Step 10；没有安装额外引擎、运行优化或产生新正式 geometry。

## 15. Recommended Next Step
建议下一步做固定 1024 成果的复现说明与答辩演示材料整理，复用保存数据和本批图；是否进入该 Step 由用户决定。本次到此停止，未进入 GUI、GDS 或论文正文写作。
