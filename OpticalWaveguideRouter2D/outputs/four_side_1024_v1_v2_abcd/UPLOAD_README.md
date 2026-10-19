# 公开仓库说明：V1/V2 x ABCD 虚拟展开单层基线（2026-10-19）

本目录对应 `docs/reports/four_side_1024_v1_v2_abcd.md`，是**修改 2x16 接口模型之前**的
单层虚拟展开（`virtual_unfolded`，32 端口以 0.175 mm 展开在同一平面）算法压力测试基线：
R = 5 mm、边缘间距 125 um、中心线净空 175 um，V1/V2 两个连接拓扑 x A/B/C/D 四种算法，
共 8 组全量 1024 条实验 + 8 个 C 消融设计 + D 的等预算/扩展预算臂。

## 已上传

| 内容 | 说明 |
|---|---|
| `connectivity/` | V1/V2 连接关系校验、对称性分析、差异表与连接图（全部） |
| `comparison/` | 全部对比资产：all_metrics、ABCD 四联图、V1/V2 同算法对比、指标柱状图、C 消融、D 预算对比、strict 审计汇总 |
| `V1_A/ ... V2_D/` | 8 组主实验的 `routes.json`（1024 条身份，含失败记录）、`statistics.json`、`config.json`、三口径 `audit_*.json`、`run.log` |
| `sweeps/ extended/ equal_budget/` | 辅助实验的统计/配置/审计/日志 |

## 因体积未上传（可完整重建）

- 每个运行目录的 `routing_all.png` / `routing_detail.png` / `routing_all.svg` /
  `routing_all.gds` / `CHECKPOINT.json` / `failed_routes.json`（失败记录已含在
  `routes.json` 中）。
- 重新生成命令（在 `OpticalWaveguideRouter2D/` 下）：

```shell
python -m four_side_1024.abcd.finalize_all --skip-audits --skip-metrics
```

`routes.json` 是自包含的权威几何记录（每条成功路线含全部解析图元），
`statistics.json`/`audit_*.json` 给出对应验收数字；GDS 层集恒为 `[0]`（单层）。
