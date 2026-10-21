# V3-C4 对称 1024 通道光波导布线实验 — 原始数据清单

输入连接表（未修改）：
`outputs/four_side_1024_v3_c4_connectivity/optical_1024_multitomulti_connectivity_v3_c4_symmetric.csv`
SHA256 `de7e382d3fbf94033eb323ccc64914739e14bde5793191389341896b717f0430`（1024 条 = row1 对边 512 + row2 邻边 512，256 个四元旋转组）

工艺/物理口径（三轮实验相同）：板 150×150 mm；R = 15 mm（平面弯曲与升降 S 弯）；波导宽 0.05 mm；最小边缘间距 0.03 mm；中心线净空 ≥ 0.08 mm；L1 含 z1=0.0 mm 与 z2=0.5 mm 两排；L2–L5 使用修正后探索性层高 medium_050 = 1.0/1.5/2.0/2.5 mm（provenance = unconfirmed_simulation，三维结果只能 exploratory 验收）。

## 最终结果

| 实验 | 成功通道数 | 失败通道数 | 四元组（已布/总） | C4 对称 | 自动验收 |
|---|---:|---:|---|---|---|
| V3_FREE_2D | 948 | 76 | 224/256（仅统计） | 不强制 | PASS |
| V3_C4_2D | 964 | 60 | 241/256 | 严格 C4（端口级） | PASS |
| V3_C4_L3D | 964 | 60 | 241/256 | 严格 C4（端口级） | PASS（3D exploratory；堆叠未确认，formal_acceptance=false） |

- FREE_2D：z1 495/512 + z2 453/512；算法 = R15 D56 + Short-S 候选（v2opt.candext）+ exact D56Index + 顺序提交 + 串行 R&R。
- C4_2D：z1 508/512 + z2 456/512；每四元组只搜索代表连接，其余三条由 90°/180°/270° 旋转生成，四条联合检测、整组原子提交；候选预算 1600（z1）/1600（z2，先 400 快扫后 1600），组级 R&R + 组级重试。
- C4_L3D：从 C4_2D 的 15 个失败组尝试 L2–L5 抬升（代表路径 60/120 候选 × 单层/多层序列 × 3 个过渡放置 variant，四条旋转副本联合 3D 检查后原子提交）。实际抬升成功 0 组：z1 抬升的 S 形过渡必须穿过 z2 所在 z=0.5 平面，与 z2 密集角部布局的真实三维净空冲突；z2 剩余组多为端口距板角 <15 mm 的 R15 不可行组。失败状态已完整记录，未通过降低半径/净空或破坏对称性强行布通。

## 目录

```
four_side_1024_v3_c4_routing/
├─ summary.json / summary.md / validation_all.json / run_all.log   汇总与总验收
├─ free_2d/
│  ├─ z1/{routes.json, failed_routes.json, validation.json, run_summary.json, checkpoint.json, checkpoints/}
│  ├─ z2/{routes.json, failed_routes.json, validation.json, run_summary.json, checkpoint.json, config.json, CHECKPOINT.json}
│  ├─ routes_1024.json        1024 条（含 plane / z / layer_sequence / rotation_group_id）
│  ├─ failed_routes.json      失败线路与失败组
│  └─ validation_combined.json 整板重读验收（identity / 2048 端口覆盖 / 逐平面 strict 审计）
├─ c4_2d/
│  ├─ z1|z2/{routes.json, run_summary.json, validation.json, checkpoint.json, run.log}
│  ├─ routes_1024.json        1024 条 + 256 个 rotation_groups（每组 4 条 route_id + routed/failed）
│  ├─ failed_routes.json / validation_combined.json（含 C4 3D?否 = 2D 旋转几何逐组比对 PASS）
├─ c4_l3d/
│  ├─ routes_l3d.json         1024 条三维记录（routed 含 parts/层间过渡；failed 含原因）
│  ├─ rotation_groups.json    256 组对应关系与状态
│  ├─ failed_routes.json / checkpoint.json / layer_stack.json
│  ├─ run_summary.json / validation.json（C4 3D 对称审计 + l3d.validate_l3d 结果）
└─ _smoke/                    小样本正确性测试（少量四元组/平面）
```

## 数据 schema 要点

- 2D `routes.json`：`four_side_1024_fslw_plane_routes_v1`；每条 routed 记录含完整 D56 `primitives`（line/arc，R=15）、`length_mm`、`bend_count`、`candidate`；failed 含 `reason/evaluated/rejection_counts/blockers`。平面 z 由 `plane`/`z_mm` 给出（z1=0.0，z2=0.5）。
- 3D `routes_l3d.json`：`four_side_1024_v2_l3d_routes_v1`；每条 routed 记录的 `parts` 按路径顺序给出 flat 段（layer_id/z_mm/primitives）与 transition 段（from/to_layer、z0/z1、radius=15、theta/footprint/length、start/end/direction），并含 `layer_sequence`、`length_mm`、`xy_length_mm`、`z_span_mm`、`lifted`。
- checkpoint：2D 为 `four_side_1024_v2opt_checkpoint_v1`（geometry 级，可恢复）；C4_2D 为组级 checkpoint（`four_side_1024_v3c4_group_checkpoint_v1`）；C4_L3D 为 `four_side_1024_v3c4_l3d_checkpoint_v1`（route 列表 + 失败组，l3d 无组内增量保存）。

## 复现命令

```powershell
# 在 OpticalWaveguideRouter2D 目录、已把 R 绑定为 15（runner 内部先 apply profile）
$env:PYTHONPATH = "...\OpticalWaveguideRouter2D"
$py = "...\python.exe"

# 实验 1（每平面；z2 用 easy 顺序，z1 用 x_desc）
& $py -m four_side_1024.v3c4.free2d --plane z1 --order x_desc --budget 1600 --retry-passes 1 --out outputs/.../free_2d/z1
& $py -m four_side_1024.v3c4.free2d --plane z2 --order easy_leg_desc --budget 400 --retry-passes 1 --out outputs/.../free_2d/z2
& $py -m four_side_1024.v3c4.rr --plane z1 --checkpoint <z1 checkpoint> --out outputs/.../free_2d/z1 --budget 1600 --rounds 4

# 实验 2（C4 组级；z1/z2 各自）
& $py -m four_side_1024.v3c4.c4 --plane z1 --order easy --budget 1600 --rr-rounds 2 --retry-passes 3 --out outputs/.../c4_2d/z1
& $py -m four_side_1024.v3c4.c4 --plane z2 --order easy --budget 1600 --rr-rounds 2 --retry-passes 3 --out outputs/.../c4_2d/z2

# 实验 3（L2–L5 组级抬升 + 三维验收，需要 scipy 的 .venv Python）
& $py -m four_side_1024.v3c4.l3d --planes z1,z2 --candidate-budget 120 --multi-budget 24 --flat-retry-budget 2400 --out outputs/.../c4_l3d

# 汇总 + 总验收
& $py -m four_side_1024.v3c4.combine
```

## 验收（自动输出，均为对已保存文件的重读）

- 2D：`v3c4.validate2d` 调用冻结 `fslw.validate_fslw`（`policy='strict'`）逐平面对审计；身份与 V3-C4 CSV 逐条一致；2048 端口恰好各用一次；C4 实验另做端口级旋转几何逐组比对（每组 4 条必须互为 90° 旋转）。
- 3D：`l3d.validate_l3d.validate_payload`（注入 V3-C4 端口身份；仓库独立验证器，不 import 路由器内部实现）检查层栈/端口/曲率/同层 strict 2D/跨平面真 3D 净空/自净空/板界；结果为 0 violations，`exploratory_pass=true`、`formal_acceptance=false`（层高未确认）。
- 总表见 `validation_all.json`；任何一项失败时该文件 `all_pass=false`。
