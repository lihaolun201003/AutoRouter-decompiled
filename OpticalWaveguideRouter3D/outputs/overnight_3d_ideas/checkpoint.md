# Overnight 3D ideas — checkpoint

Task card: c995c9ec-1103-469f-8e6d-77aad54066e4 (global task library).
Machine state: outputs/overnight_3d_ideas/status.json, task_queue.json, this file.

## How to resume after an interruption

```powershell
cd "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D"
# 1. what is already finished
Get-ChildItem outputs/overnight_3d_ideas/*/*/summary.json | Select-Object FullName
# 2. re-run a single pre-registered group (the runner refuses unregistered groups)
.\.venv\Scripts\python.exe -B scripts\run_overnight_3d.py . outputs\overnight_3d_ideas --round v5 --group V5_STRATIFIED_N720
# 3. launch a whole batch of pre-registered groups in parallel
.\scripts\overnight_launch.ps1 -Round v5 -Groups V5_STRATIFIED_N720,V5_STRATIFIED_R720
# 4. freeze the next round manifest BEFORE running it
.\.venv\Scripts\python.exe -B scripts\freeze_overnight_manifest.py . outputs\overnight_3d_ideas --round v6 --adoption outputs\overnight_3d_ideas\v5\adoption.json
```

## Frozen inputs (verified by scripts/overnight_p0_baseline.py, verdict PASS)

| item | value |
| --- | --- |
| main start | outputs/3d_strategy_v3/512_ablation/D_both_enabled — 42,909 pairs, 3 unresolved, 24 elevated |
| challenge start | outputs/3d_strategy_v4/512_full_layout/N2880 — 30,999 pairs, 3 unresolved, 77 elevated |
| planar reconstruction | outputs/step_8_5_legacy_512_plot_geometry.json + outputs/step_8_5_legacy_512_physical_events.jsonl (SHA256 in P0_baseline.json) |
| config | layers z=0/1/2 mm, clearance 0.1 mm, required radius 5.0 mm, window slack 1e-5 mm |
| engine | src/overnight_engine_3d.py, driven by scripts/run_overnight_3d.py, registry scripts/overnight_registry.py |

## Errata (derived records only; original data untouched)

See outputs/overnight_3d_ideas/P0_baseline.json key "errata" for the three step-17 metadata defects.

## Round status

| round | manifest sha256 | groups | state |
| --- | --- | --- | --- |
| v5 | ee77fdd079c1ab6bc1cd8bb3ebef379dc06fb1f0a10b58d3a5a8f4c19eff8d38 | 16 | running |

## Bugs found and fixed during bring-up (kept as a real record)

1. `eligible.append(...)` passed `victim_id`/`action` twice (once explicitly, once via `**entry`)
   -> TypeError. Fixed to `**entry` only; the winner row must be the full ledger row so
   strategy_rank sees net_collision_reduction.
2. `_full_acceptance` decision cache must key on the neighbour route change counter, not a
   global that was never populated; the counter is now passed in.
3. `ElevationCandidate3D` is a frozen dataclass, so the "other route" of a pool row is stored
   in the row dict, never on the candidate.

## Diagnostics already produced

- outputs/overnight_3d_ideas/P0_baseline.json — both start states independently rescanned, PASS.
- outputs/overnight_3d_ideas/diagnostics_prechecks.json — conflict-graph components: main start has
  4 components, largest 507/512 = 99.0% of nodes. The conflict graph is effectively ONE giant
  component, so component round-robin must not be presented as evidence; idea D uses per-route
  recency instead.
- outputs/overnight_3d_ideas/diagnostics_target_depth.json — generation-only depth scan of the
  priority order (diagnostic, booked separately from every budget).
## 运行期发现（供恢复者参考）

1. `C:\...\.venv\Scripts\python.exe` 在本机是**转发 shim**（cpu≈0、WS≈4.5 MB），真正的解释器是
   `C:\Users\lihao\AppData\Local\Programs\Python\Python310\python.exe`。因此每个 run 会出现**两个**
   python 进程，任务管理器里进程数是运行组数的两倍；这不是重复启动。判断重复运行要看日志里
   `INITIAL_DONE` 出现次数，而不是进程数。
2. 本机 PowerShell 执行策略禁止直接运行 .ps1；`scripts/overnight_launch.ps1` 与 `overnight_run_round.ps1`
   需要 `Set-ExecutionPolicy -Scope Process Bypass`，或按下面的内联 Start-Process 方式启动。
3. 运行器要求组必须在该轮 manifest 中出现；`--force` 重写 manifest 时必须在
   `outputs/overnight_3d_ideas/manifest/round_<轮>_override_record.json` 留下原因与旧 SHA256。

## 已完成的轮

- v5（16 组）全部完成并 PASS。采纳结论：**不采纳 STRATIFIED**（主 R2880：LEGACY 30,999 < STRATIFIED 33,343）。
  证据：outputs/overnight_3d_ideas/v5/adoption.json、comparison.csv、summary_v5.json、
  equiv/v5_legacy_vs_v4.json（六组 IDENTICAL）。
- 中立性检查：outputs/overnight_3d_ideas/neutrality_checks/ 下的 V5_LEGACY_N720_postedit 与 _finalcode
  在步级轨迹、终态近距集合、长度账本上与 v4 N720 逐位一致，用于证明运行期对引擎的字段追加**不改变行为**。
- 中途作废的臂：outputs/overnight_3d_ideas/aborted_arms/v6_stratified_arm_aborted（在 v5 采纳决定把基线
  定为 LEGACY 之前、按临时 manifest 启动的 STRATIFIED 版 v6 E1/E2；已终止，不作为正式结果）。
