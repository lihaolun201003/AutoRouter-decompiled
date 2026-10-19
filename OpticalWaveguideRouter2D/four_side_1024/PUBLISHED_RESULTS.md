# 1024 四边单层实验与复现

当前选定算法为原逆向 AutoRouter 的四边适配版，入口 `legacy_adapter.py`。邻边保留固定 L 形／三弯模板；两个跨边分支分别按源边调用；每条路线的 256 次评价上限已取消，仅保留全局时间和评价预算。原 256/512 路由核心未改动。

## 最新实测：two_branch_v2

| 项目 | 结果 |
|---|---:|
| 原始连接 / 端点 / 接头 | 1024 / 2048 / 64 |
| 通过最终几何检查 | 80 / 1024（7.8125%） |
| 实际进入轨道与几何处理 | 667 |
| 当前固定轨道内未找到合法路径 | 586 |
| 处理中因总时间结束而停止 | 1 |
| 因总时间结束而尚未开始 | 357 |
| 同层交叉 / 小于10°交叉 | 1141 / 0 |
| 路由层 / 最小半径 | layer=0 / 5 mm |
| 总程序执行时间 | 602.117 秒 |
| 路由时间 / 总评价预算 | 600 秒 / 900000 次 |
| 实际几何评价次数 | 429559 |

未完成944条不能统一解释为“几何不可能布通”。用尽的是时间预算，未达到总评价次数上限。运行结果受机器速度影响，这里保存的是一次真实运行快照。

![实际通过检查的80条路线](../outputs/four_side_1024_legacy_two_branch_v2/02_routing_all.png)

完整的 [实验报告](../../docs/reports/four_side_1024_legacy_two_branch_v2.md)、[统计JSON](../outputs/four_side_1024_legacy_two_branch_v2/statistics.json)、[失败记录](../outputs/four_side_1024_legacy_two_branch_v2/failed_routes.json)、[SVG](../outputs/four_side_1024_legacy_two_branch_v2/routing_all.svg)、[GDS](../outputs/four_side_1024_legacy_two_branch_v2/routing_all.gds) 与 [独立验收](../outputs/four_side_1024_legacy_two_branch_v2/independent_audit.json) 均已保留。全部GDS路径属于layer=0。

## 输入与物理局限

输入文件为 [`data/optical_1024_multitomulti_connectivity_v1.csv`](../data/optical_1024_multitomulti_connectivity_v1.csv)，内容与用户原文件逐字节相同：

```text
SHA256 0ecce47109f9223e8407928c423ad5d9272186938cc267877a6158936e0e428b
```

row=1/row=2是接头内部两排通道，两者共同参与同层冲突检测。真实端口面采用0.25 mm列距与0.50 mm排距；实验中的二维端点采用明确标注的 `virtual_unfolded` 坐标，未验证真实端口到平面的适配器。9 mm接头中心距为暂定值；完整MPO外壳按标准所述宽度沿板边安装时存在机械重叠。半径5 mm、宽度0.05 mm、边缘间距0.125 mm是初版验证参数，不是新玻璃工艺最终标准。旧聚合物损耗模型仅为估计对照。

## 运行

先按项目主README安装依赖，然后在 `OpticalWaveguideRouter2D` 目录执行：

```shell
# 仅读取、校验并保存1024条输入，不执行布线
python -m four_side_1024.legacy_adapter

# 一次固定参数的布线运行
python -m four_side_1024.legacy_adapter --route --seconds 600 --evaluations 900000 --output outputs/four_side_1024_legacy_two_branch_v2

# 对保存的几何、交叉与GDS执行独立验收
python -m four_side_1024.independent_audit --output outputs/four_side_1024_legacy_two_branch_v2
```

程序优先读取仓库内的CSV；在原开发环境中没有打包CSV时，可回退至原桌面路径，也可用 `--input` 显式指定。发布时仅增加了默认输入的可移植查找，不改变路由算法。实验JSON/log中的绝对路径是原运行记录；各实验的 `source_manifest.json` 是当时源码快照的哈希，不代表当前发布文件必须与历史源码完全相同。

## 历史结果

- `four_side_1024_single_layer_v1`：之前的通用候选搜索对照实验，526条，不是当前选定的原算法入口。
- `four_side_1024_legacy_single_layer_v1`：修改前66条；含已停止运行的标记和更早预算试跑归档。
- `four_side_1024_legacy_input_v1`：当前输入接入与代码测试记录。
- `four_side_1024_legacy_two_branch_v2`：本页所述最新80条结果。

历史实验完整保留以便追溯，不能把不同算法或不同预算版本的数字混用。缓存、虚拟环境和旧256/512私有输入不属于本次发布文件。
