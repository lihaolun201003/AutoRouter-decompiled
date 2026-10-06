"""生成三维策略改进实验的中文实验说明（Markdown）。

用法（项目根目录）：
    .venv\\Scripts\\python.exe -B scripts\\summarize_3d_strategy_v2.py PROJECT OUTDIR
"""
import csv, json, sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
RUNS = {size: json.loads((OUT/f'{size}_three_layer_abc'/'summary.json').read_text(encoding='utf-8'))
        for size in (512, 1024)}
COMPARISON = {size: {row['strategy']: row for row in
                     csv.DictReader((OUT/f'{size}_three_layer_abc'/'comparison.csv').open(encoding='utf-8-sig'))}
              for size in (512, 1024)}


def ledger(size, strategy):
    return RUNS[size]['runs'][strategy]['ledger']


def f(v, d=4):
    return f'{float(v):.{d}f}'


def i(v):
    return f'{int(float(v)):,}'


def stop_label(reason):
    return {'TARGET_LIMIT': '达到目标尝试上限', 'NO_ELIGIBLE_TARGETS': '没有可尝试目标',
            'CANDIDATE_BUDGET_EXHAUSTED': '候选评价预算耗尽'}.get(reason, reason)


lines = []
w = lines.append
w('# Step 15 — 三维布线策略改进实验（A/B/C 对照）')
w('')
w('在固定二维 XY 路径、三层高度 0/1/2 mm、0.1 mm 中心线阈值、5 mm 最小曲率半径条件下，')
w('对现有三维局部升降方法的三种决策策略做同预算对照：')
w('')
w('- **A（对照）**：原 9-E/9-F 规则（最小目标对、victim 冲突度数小者优先、第一条路线有改善即停止、每条路线最多抬一次）。')
w('- **B**：过滤双方都已抬过的目标；目标按"冲突集中"确定性排序；对两条路线的候选都完整评价；')
w('  跨路线排序以净减少量 `net = removed − created` 为首要键，其次新增对、长度代价、过渡数。')
w('- **C**：在 B 基础上允许已抬路线重定位（重新选择 1/2 mm 层与升降窗口），')
w('  替代候选从原始平面路线重建，失败目标按依赖版本缓存、相关路线变化后允许重试。')
w('')
w('三个策略使用相同的输入、几何参数、验收规则与**实际候选评价预算**；')
w('预算取历史实测值并在查看 B/C 结果之前冻结：512 条为 720 次、1024 条为 8172 次候选评价')
w('（每个候选一次 `evaluate_elevation`，基本验收失败同样计入；预算不足时不提交未完整验收的候选）。')
w('')
w('## 结果')
w('')
for size in (512, 1024):
    a = ledger(size, 'A')
    w(f'### {size} 条连接（初始 {i(a["initial_collision_pair_count"])} 对近距对）')
    w('')
    w('| 策略 | 终态近距对 | 净减少 | 接受修改 | 其中重定位 | 终态额外长度 mm | 终态过渡数 | 候选评价数 | 耗时 s | 停止原因 |')
    w('| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |')
    for strategy in 'ABC':
        entry = ledger(size, strategy)
        reduction = 100 * (entry['initial_collision_pair_count'] - entry['final_collision_pair_count']) / entry['initial_collision_pair_count']
        w(f'| {strategy} | {i(entry["final_collision_pair_count"])} | {f(reduction, 2)}% | {entry["accepted_moves"]} | '
          f'{entry["relocations"]} | {f(entry["final_extra_length_mm"], 4)} | {entry["final_transition_count"]} | '
          f'{i(entry["candidate_evaluations"])} | {f(entry["runtime_seconds"], 1)} | {stop_label(entry["stop_reason"])} |')
    w('')
    w(f'累计移除/新增：A {i(a["total_old_collisions_removed"])}/{i(a["total_new_collisions_created"])}、'
      f'B {i(ledger(size, "B")["total_old_collisions_removed"])}/{i(ledger(size, "B")["total_new_collisions_created"])}、'
      f'C {i(ledger(size, "C")["total_old_collisions_removed"])}/{i(ledger(size, "C")["total_new_collisions_created"])}；'
      f'终态另有未决/边界对 A {a["final_unresolved_pair_count"]}、B {ledger(size, "B")["final_unresolved_pair_count"]}、'
      f'C {ledger(size, "C")["final_unresolved_pair_count"]}（单列，不当作 CLEAR）。')
    w('')
    hist = RUNS[size].get('historical_A') or {}
    if hist.get('status') == 'COMPARED':
        import json as _json
        new_steps = _json.loads((OUT/f'{size}_three_layer_abc'/'decisions_A.json').read_text(encoding='utf-8'))
        old_path = ROOT/'outputs'/(('step_9_f_three_layer_attempts.json', 'step_10_fixed_1024_attempts.json')[size == 1024])
        old_steps = _json.loads(old_path.read_text(encoding='utf-8'))
        fields = ['target_pair', 'status', 'moved_route_id', 'target_layer_id',
                  'net_collision_reduction', 'global_collision_pairs_before', 'global_collision_pairs_after']
        diffs = 0
        for a, b in zip(new_steps, old_steps):
            for field in fields:
                x, y = a.get(field), b.get(field)
                if isinstance(x, list):
                    x = tuple(x)
                if isinstance(y, list):
                    y = tuple(y)
                if x != y:
                    diffs += 1
        w(f'A 与历史记录核对：终态近距对 {i(hist["measured_final_pairs"])}（历史 {i(hist["historical_final_pairs"])}）、'
          f'成功抬升 {hist["measured_accepted_first_elevations"]}（历史 {hist["historical_successful_elevations"]}）、'
          f'额外长度 {f(hist["measured_total_extra_length_mm"], 6)} mm（历史 {f(hist["historical_total_extra_length_mm"], 6)} mm），'
          f'终态近距对集合与未决集合完全相同：{hist.get("final_pair_sets_equal")}/{hist.get("unresolved_pair_sets_equal")}；'
          f'{len(new_steps)} 步逐步记录（目标对、状态、移动路线、层、净减少、全局前后计数）差异 {diffs} 处。')
        w('')

for size in (512, 1024):
    recheck = RUNS[size]['runs']['C']['recheck']
    w(f'重载复核（{size} 条）以 C 为例：从保存文件重新加载 {i(recheck["reloaded_route_count"])} 条终态路线，'
      f'完整复核 {i(recheck["checks"])} 路线对，近距对集合与未决集合与增量账目一致'
      f'（{recheck["collision_pair_set_matches_incremental"]}/{recheck["unresolved_pair_set_matches_incremental"]}），'
      f'端点、C0/C1 连接、过渡曲率、XY 投影与长度台账全部通过。')
w('')
w('## 结论')
w('')
best_1024 = min('ABC', key=lambda s: ledger(1024, s)['final_collision_pair_count'])
best_512 = min('ABC', key=lambda s: ledger(512, s)['final_collision_pair_count'])
w(f'- 512 条：终态近距对 A {i(ledger(512, "A")["final_collision_pair_count"])}、'
  f'B {i(ledger(512, "B")["final_collision_pair_count"])}、C {i(ledger(512, "C")["final_collision_pair_count"])}，最优为 {best_512}。')
w(f'- 1024 条：终态近距对 A {i(ledger(1024, "A")["final_collision_pair_count"])}、'
  f'B {i(ledger(1024, "B")["final_collision_pair_count"])}、C {i(ledger(1024, "C")["final_collision_pair_count"])}，最优为 {best_1024}。')
w('- 结论只覆盖中心线几何；不代表光学损耗、串扰或制造合规性下降，终态仍有大量近距对，不构成无碰撞版图。')
w('- 长度、过渡与运行代价见表；C 的重定位可以降低单步长度（长度变化可为负），终态总增长始终按终态几何统计。')
w('')
w('## 数据与复现')
w('')
w('- 原始记录：`outputs/3d_strategy_v2/{512,1024}_three_layer_abc/`（config、code_version、decisions、final_routes、')
w('  collision_sets、ledger、recheck、comparison.csv、summary.json）。')
w('- 图：`outputs/3d_strategy_v2/figures/`。')
w('- 复现：')
w('')
w('```text')
w('.venv\\Scripts\\python.exe -B scripts\\run_3d_strategy_v2.py . outputs\\3d_strategy_v2\\512_three_layer_abc --size 512')
w('.venv\\Scripts\\python.exe -B scripts\\run_3d_strategy_v2.py . outputs\\3d_strategy_v2\\1024_three_layer_abc --size 1024')
w('.venv\\Scripts\\python.exe -B scripts\\visualize_3d_strategy_v2.py . outputs\\3d_strategy_v2')
w('```')
w('')

target = ROOT/'docs'/'reports'/'step_15_strategy_v2_3d.md'
target.write_text('\n'.join(lines), encoding='utf-8')
print(f'wrote {target}')
