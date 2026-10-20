# V2 纯正交 90° 圆弧布线实验（four_side_1024_v2_ortho90_v01）复现说明

工程根：`C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D`
Python：`.venv\Scripts\python.exe`

本实验只改一个几何约束：**只允许水平/竖直直线段 + 半径 40 mm、转角恰好 90° 的四分之一圆弧，
禁止 Short-S 的 θ<90° 圆弧组合**；V2 连接、双高度接口、R40、0.03 mm 边缘间距、全部 strict 约束
与独立验收均沿用上一轮。全部实验从零重新布线（不沿用 V2-BEST 的 752 条路径，因为它含非 90° 弧）。

## 1. 纯 90° 双平面布线（z2 主顺序 + z1）

```bat
rem z2: V2-C round-robin 顺序 + R&R（第一轮基线，供顺序对照）
.venv\Scripts\python.exe -m four_side_1024.v2opt.pipeline ortho90 --budget 1600 --rounds 4 --transactions 64 --sizes 1,2,4,8 --workers 8 --analysis-budget 1600 --reinsert-budget 1600 --rr-time-limit 2400 --targets-per-round 48 --analysis-targets 96 --min-rounds 2 --zero-rounds 2
```

## 2. z2 顺序策略对照（可比预算，每策略一次全新顺序插入）

```bat
.venv\Scripts\python.exe -m four_side_1024.v2opt.order_sweep_ortho90 --plane z2 --order csv --budget 1600
.venv\Scripts\python.exe -m four_side_1024.v2opt.order_sweep_ortho90 --plane z2 --order group_ensw --budget 1600
.venv\Scripts\python.exe -m four_side_1024.v2opt.order_sweep_ortho90 --plane z2 --order round_robin_E_ccw --budget 1600
.venv\Scripts\python.exe -m four_side_1024.v2opt.order_sweep_ortho90 --plane z2 --order global_congestion --budget 1600
```

（可加 `csv_desc` / `group_swesnw` / `global_length` / `round_robin_N_cw`；本报告采用其中 5 种。）

## 3. 最佳顺序 + 重新插入/R&R 循环（最终布局）

实测顺序对照后最佳为 `group_swesnw`（SW→ES→NW→EN，x 降序，顺序插入 134/512）。
在其 checkpoint 上运行两轮"剩余失败路线重新插入 + 强化 R&R"：

```bat
.venv\Scripts\python.exe -m four_side_1024.v2opt.pipeline ortho90rr --plane z2 --from-checkpoint outputs/four_side_1024_v2_ortho90_v01/checkpoints/order_group_swesnw_z2.json --budget 1600 --cycles 2 --rounds 4 --transactions 128 --targets-per-round 64 --analysis-targets 128 --sizes 1,2,4,8 --analysis-budget 1600 --reinsert-budget 1600 --rr-time-limit 2400 --min-rounds 2 --zero-rounds 2 --seed-offset 777 --reinsert-order shuffle
```

实测顺序对照共 8 种（`experiments/order_sweep/`）：
round-robin N cw（90，来自主 pipeline 顺序插入）< round-robin E ccw（84）< CSV（113）<
全局拥塞（114）< CSV 逆序（117）< 全局长度（123）< 分组 EN→ES→SW→NW（124）<
**分组 SW→ES→NW→EN（134，最佳）**。第一轮 round-robin N cw 的完整产物
（顺序插入 90 + R&R 后 93）保存在 `experiments/ORTHO90_combined_summary_roundrobin_firstpass.json`。

## 4. 候选覆盖与 z1 几何可达性证据

```bat
rem 空板候选覆盖（每路线是否有合法纯 90° 候选，layout-independent）
.venv\Scripts\python.exe -m four_side_1024.v2opt.coverage_ortho90 z1 6
.venv\Scripts\python.exe -m four_side_1024.v2opt.coverage_ortho90 z2 6

rem z1 小偏移（dx=±8/16/24mm）纯 90° 路径的精确 LP 可达性证据
.venv\Scripts\python.exe -m four_side_1024.v2opt.z1_pure90_infeasibility --max-turns 14
```

## 5. 独立 strict 验收 + 每弧 90° 审计

```bat
.venv\Scripts\python.exe -m four_side_1024.v2opt.finalize --root outputs/four_side_1024_v2_ortho90_v01 --labels ORTHO90
.venv\Scripts\python.exe -m four_side_1024.v2opt.ortho90_validate
```

- `finalize`：对两个平面运行冻结的 `fslw.validate_fslw`（strict，expected_route_count=512），
  生成 `audit_strict.json` / `statistics.json` / `combined/V2/ORTHO90/`（1024 组合、双高度 GDS/图）。
- `ortho90_validate`：额外交付 `geometry_audit.json`——逐 primitive 检查
  "line 必须轴对齐、arc 必须 R=40 且 |sweep|=90°"，并统计 V2-BEST 参考布局的弧转角分布
  （量化非 90° Short-S 弧的使用量）与相对 BEST 丢失/新增的路线。

## 6. 新旧布局对照图（几何类型着色：直线蓝、弧红）

```bat
.venv\Scripts\python.exe -m four_side_1024.v2opt.plots_ortho90
```

生成：
- `planes/V2/ORTHO90/{z1,z2}/routing_geomtype.png`（新布局，line=蓝 / arc=红）；
- `comparison/compare_z1.png`、`comparison/compare_z2.png`（左旧 V2-BEST、右新纯 90°）；
- `comparison/compare_all.png`（2×2：z1/z2 × 旧/新）。

## 7. 目录

```
outputs/four_side_1024_v2_ortho90_v01/
├─ planes/V2/ORTHO90/{z1,z2}/   # routes.json + config/CHECKPOINT + 独立 audit_strict/statistics + 图
├─ combined/V2/ORTHO90/         # 1024 组合 routes_1024.json + 双高度图/GDS + 统计
├─ experiments/                 # 顺序对照、覆盖、LP 可达性、汇总 JSON
├─ checkpoints/                 # 各顺序与最终的几何 checkpoint
├─ comparison/                  # 新旧对照图
├─ work/                        # 运行日志（含命令/seed/配置）
├─ geometry_audit.json          # 每弧 90° 额外审计 + 与 BEST 对比
├─ final_validation.json        # 独立 strict 验收汇总（fslw.validate_fslw）
└─ REPRODUCE.md
```
