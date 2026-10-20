# V2 双高度二维布线优化轮（v2_candidate_rr_v01）方法说明

本文件说明本轮新增的搜索与拆线重布机制。**物理模型、连接关系、几何 primitive、
验收口径全部沿用上一轮**（`four_side_1024/fslw/SPEC.md`、`four_side_1024/d56/SPEC.md`）：

| 项目 | 值（不变） |
|---|---|
| 板面 | 150 × 150 mm，每平面 `layer=0` 二维 |
| 波导宽度 | 0.050 mm |
| 最小边缘间距 | 0.030 mm |
| 中心线净空 | 0.080 mm（exact strict 口径） |
| 弯曲半径 | 固定 R = 40.0 mm（不搜索其他 R） |
| 路径 primitive | 正交直线 + R=40 90° 圆弧 + `theta=acos(1-d/(2R))` 两弧短 S |
| 端点/端口 | 真实 2×16 双高度接口（z1 = row1 对边，z2 = row2 邻边），端口位置与切向固定 |
| 连接关系 | V2 CSV，SHA256 = `49dd9e89...3915e`，本轮零改动 |
| 验收 | `four_side_1024.fslw.validate_fslw --policy strict`（独立于路由器实现） |

本轮**新增/修改的只有搜索与调度**：候选队列如何产生、按什么顺序评价、评价多少条、
以及允许哪些已布路线被临时拆除再重布。任何候选的合法性仍由冻结的
`four_side_1024/d56/index.py` 精确 strict 索引判定；最终布局由冻结的独立校验器重审。

---

## 1. 基线：历史结果重组（698/1024）

上一轮两个平面是独立二维问题，因此可以逐平面取最优：

| 平面 | 来源（历史 `routes.json`） | routed |
|---|---|---:|
| z1（对边，z=0.0 mm） | `planes/V2/D/z1/routes.json`（算法 D） | 492/512 |
| z2（邻边，z=0.5 mm） | `planes/V2/C/z2/routes.json`（算法 C） | 206/512 |
| **V2 组合基线** | 两平面独立、XY 投影交叉不计同层冲突 | **698/1024** |

`v2opt/core.py:LayoutState.from_history` 从历史 `routes.json` 的 **真实 primitive 链**
重建几何（不是只读路线编号）：每条路线 `prepare()` 后装入精确索引和 6 个 canonical
frame oracle；随后 `verify()` 用全新索引做 leave-one-out 自检，并把 9 个身份字段与
V2 CSV 逐条比对。z1 = 492/492、z2 = 206/206 全部有效、身份 0 mismatch（详见
`outputs/four_side_1024_v2_candidate_rr_v01/baseline_acceptance.json`）。

## 2. 扩大单路线候选搜索（任务一）

### 2.1 为什么不能只调大预算

上一轮 z2 的 178 条 `no_legal_candidate` 中 175 条恰好停在 200 次评价，但历史生成器
对邻边路线最多只能产出约 200~240 条不同候选（深层 Z3 24×24 采样 + 浅层/深层截断），
因此 200→400→800→1600 单纯加预算没有任何意义。本轮的候选队列必须先在**数量与多样性**
上扩展，预算才有意义。

### 2.2 扩展方式（仍然只用同一 primitive 集）

`four_side_1024/v2opt/candext.py`：

1. **采样池**：每个候选族使用的轨道/转弯坐标不再来自固定 24 点粗网格，而是来自
   *当前已布几何* 推导的 clearance tracks（`d56.candidates.clearance_tracks`，
   贴着已有波导 0.080 mm 生成的候选轨道）+ 结构坐标（R、150-R、q.y、q.y±R 等），
   并按板边半宽 0.025 mm 裁剪（保证描边不越界）。池上限 600/轴。
2. **候选族**：
   - 冻结族（沿用 `fslw.geom` 的构造函数）：`L`、`TURN_S`、`SHIFT_TURN`、`Z3`、`LEFT`、`Z5`；
   - 新增族 `DOWN_LOOP`：左转-上-右-下-再从左下方向以 +x 切向进入 q 的长 staircase
     （可带一个短 S 高度修正），用于覆盖"从上方接近 q"的形状；
   - 所有族仍只输出三种 primitive，所有候选都在 canonical frame 内用
     `fslw.geom.canonical_validate` 预检（端点/切向/半径/板界/自交）。
3. **预算语义**：`candidate_budget_per_route` = 本路线最多**评价**（调用精确索引）的
   不同候选数。队列是一次性完整排序后按序 yield，四种预算 200/400/800/1600 评价的
   是**同一个排序队列的前缀**，因此预算对比是可比的。
4. **排序**：cheap oracle 打分（与已布直线的平行占用 + 横向穿越数；只做排序，不判合法），
   再按族 round-robin 交错，避免单一族占满预算；同分时用确定性 per-route 抖动。
5. **去重**：按 primitive 链的四舍五入签名去重（同几何只评价一次，不同几何不会误删）。
6. **缓存**：spec 列表按路线缓存；每次尝试只重新打分/构建，不重复枚举。

对边（z1）平面沿用冻结的 U/S/Z 生成器，但放宽深层轨道数与 Z 候选上限
（`OPPOSITE_DEEP=1200` 等），候选预算语义相同。

### 2.3 候选预算对照（任务 5.1/5.4）

保持 z2 基线 206 条成功路线**不变**，把 306 条失败路线逐条放回当前布局中独立测试
（`v2opt/search.py:parallel_sweep`，按路线并行，不提交、不互相影响），预算
200/400/800/1600 各跑一遍；记录每条路线找到的候选族/参数、评价数、失败原因、blockers。
这是"候选预算 → 能否直接插入"的干净对照。

## 3. 强化拆线重布（任务二）

`four_side_1024/v2opt/rr.py`：

1. **重新计算阻挡关系**：R&R 开始前对失败路线重新尝试（不在旧 `blockers` 统计上
   继续使用过期数据），得到当前布局下的真实 blockers。
2. **拆线对象选择**：统计每条已布路线阻挡多少条失败路线、被引用次数（blocker impact），
   失败路线的 blocker 集按 impact 加权抽样；对同一失败路线生成多个拆线组候选。
3. **拆线规模**：k ∈ {1, 2, 4, 8, 12}（任务要求 2/4/8/12，k=1 作为对照）。
4. **重布顺序**：ripped_first / target_first / reversed / random / congestion_desc /
   congestion_asc 六种顺序（固定种子抽样）。
5. **并行事务评估**：每轮把候选事务分发到多个 worker 进程，各自在 base 布局的
   **快照副本**上执行"拆线→布目标→重布被拆路线"，返回净收益与完整 primitive 链；
   worker 不做任何合法性最终决定。
6. **提交前重验**：协调进程按净收益排序，对每个事务在当前实时布局上**逐条重新**用
   精确索引验证 placement；任何一条不合法或 routed 数不增加 → 完整回滚（恢复被拆几何），
   只有严格增加才提交。即 **best-so-far 永不下降**。
7. **预算与迭代上限**：每轮限制事务数、每事务评价上限（默认 12000）、事务墙钟上限
   （默认 90 s）、总时间上限、最大轮数；每轮结束写 checkpoint（真实 primitive 链），
   中断可用 `load_layout_from_checkpoint` 恢复。
8. **拆线规模收益**：summary 中记录每轮 transactions/committed/gain 及每个事务的
   size；按 size 聚合即可得到 k → 新增布通数。

## 4. 消融实验设计（任务三）

三组都以经过独立验收的 698 组合基线为初始解，物理约束相同，只改变两个因素：

| 实验 | 候选搜索 | R&R |
|---|---|---|
| E1 | 扩大（1600 评价/路线 + 扩展候选队列） | 不做强化 R&R（只做一次贪心顺序插入） |
| E2 | 原预算（200 评价/路线 + 历史生成器） | 强化 R&R |
| E3 | 扩大（同 E1） | 强化 R&R |

- 每组都先 z2（重点），z2 有结论后再对 z1 的 20 条失败路线做同样处理（Z1OPT）。
- E1 的逐路线"能否插入"数据来自第 2.3 的并行 sweep；E1 的正式布局来自一次
  1600 预算的顺序贪心提交（`v2opt/pipeline.py e1`）。
- E2/E3 用同一 R&R 实现与相同随机种子；E2 的候选/预算参数为历史值（200、历史生成器），
  保证"原预算"不是把扩展队列截断到 200。

## 5. 产物与复现

```
outputs/four_side_1024_v2_candidate_rr_v01/
  planes/V2/{BASE,E1,E2,E3,Z1OPT,BEST}/{z1,z2}/   # routes.json + 独立审计 + 统计
  combined/V2/{...}/                              # routes_1024.json + 双高度图/GDS
  candidates_budget/                              # 任务 5.1/5.4 数据与图
  experiments/                                    # E1/E2/E3 摘要与图
  reachability/                                   # 128 条角部路线覆盖/可达性探针
  checkpoints/                                    # 真实几何 checkpoint
  work/                                           # 完整运行日志（含 seed/命令）
  baseline_acceptance.json / final_validation.json
```

复现命令见 `outputs/four_side_1024_v2_candidate_rr_v01/REPRODUCE.md`。
