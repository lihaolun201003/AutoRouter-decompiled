# MANUAL-C4 新连接表：1024 通道 C4 二维/三维布线实验（交付索引）

## 输入
- 两份人工连接 CSV 见 `inputs/`（sha256 记录于 `inputs/input_validation.json`）
- 输入/兼容性校验：True，35/35 项 PASS
- 合成拓扑 `inputs/connectivity_1024.csv`：1024 条连接、256 个 C4 四元组、C4 闭合 {'90deg': 0, '180deg': 0, '270deg': 0}

## 二维（阶段 2）
- 布通：1024/1024，C4 四元组 256/256
- 逐平面：{'z1': 512, 'z2': 512}；按关系：{'opposite': 272, 'same': 256, 'adjacent': 496}
- 总长度：97438.4405 mm；验收：True
- 产物：`phase2_2d/`（routes_1024.json、routes_z{1,2}.json、validation.json、failed_routes.json、plots/、run.log、checkpoint）

## 初始三维交叉抬升（阶段 3）
- 抬升四元组 47，升降 376 次，唯一交叉对 42584 → 25308
- 三维验收：exploratory_only（geometry_pass=True）
- 产物：`phase3_initial_lift/`（routes_l3d.json、lift_plans.json、crossings_before/after.json、summary.json、validation.json、plots/）

## 层高对照（阶段 4）
- A_0.25mm：剩余唯一交叉对 20416，抬升 72 组，升降 576 次，几何 exploratory_only（594.93 s）
- B_0.50mm：剩余唯一交叉对 25308，抬升 47 组，升降 376 次，几何 exploratory_only（399.44 s）
- C_0.75mm：剩余唯一交叉对 20820，抬升 67 组，升降 536 次，几何 exploratory_only（579.56 s）
- D_1.00mm：剩余唯一交叉对 21392，抬升 66 组，升降 528 次，几何 exploratory_only（620.71 s）
- 产物：`phase4_ablation/<A_0.25mm|B_0.50mm|C_0.75mm|D_1.00mm>/` + `ablation_table.json/md` + `ablation_3d_compare.png`

## 动态优化 V2（阶段 5）
- 唯一交叉对 25308 → 23356
- 单一重调度 4、联合重调度 1、失败组救回 8
- 验收：exploratory_only；运行 856.05 s
- 产物：`phase5_dynamic_optimization/`（before/、after/、actions.json、stage_records.json、summary.json、figures/、checkpoint.json）

## 对照表

# 新连接表 vs 旧 V4-C4 对照表

| 指标 | 新 CSV（本轮） | 旧 V4-C4（历史参考） |
|---|---:|---:|
| 二维布通数（条） | 1,024 / 1024 | 1,020 / 1024 |
| 二维 C4 四元组（全部布通） | 256 / 256 | 255 / 256 |
| 初始三维抬升后剩余唯一交叉线路对 | 25,308 | 56,032 |
| A 组 0.25 mm：剩余唯一交叉对 | 20,416 | 47,192 |
| B 组 0.50 mm：剩余唯一交叉对 | 25,308 | 55,484 |
| C 组 0.75 mm：剩余唯一交叉对 | 20,820 | 46,112 |
| D 组 1.00 mm：剩余唯一交叉对 | 21,392 | 45,204 |
| B 组动态优化 V2 最终剩余唯一交叉对 | 23,356 | 49,992 |
| 动态优化 V2：单一/联合重调度/失败组救回 | 4 / 1 / 8 | 13 / 1 / 6 |
| 初始三维抬升：抬升四元组 / 升降次数 | 47 / 376 | 86 / 688 |
| 三维总长变化（mm） | 47.1 | 118.0 |
| 初始三维运行时间（s） | 397.1 | — |

> 新 CSV 为全新人工配对，旧 V4-C4 数字仅作参考，不是预期值
> 交叉数为跨全部物理高度、按唯一 (route_id_a, route_id_b) 去重
> 层高为探索性参数，几何 PASS 不代表制造工艺正式验收

