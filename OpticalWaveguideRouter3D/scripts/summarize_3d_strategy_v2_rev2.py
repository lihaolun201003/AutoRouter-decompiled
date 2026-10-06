"""生成修正版实验说明（Markdown）。

用法（项目根目录）：
    .venv\\Scripts\\python.exe -B scripts\\summarize_3d_strategy_v2_rev2.py PROJECT OLDDIR NEWDIR
"""
import json, sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
OLD = Path(sys.argv[2]).resolve()
NEW = Path(sys.argv[3]).resolve()


def jsread(path): return json.loads(Path(path).read_text(encoding='utf-8'))


def i(v): return f'{int(float(v)):,}'


def f(v, d=4): return f'{float(v):.{d}f}'


OLD_SUMMARY = {size: jsread(OLD/f'{size}_three_layer_abc'/'summary.json') for size in (512, 1024)}
FIX = {size: jsread(NEW/f'{size}_c_fixed'/'summary_C_fixed.json') for size in (512, 1024)}
RECOUNT = jsread(NEW/'stats_fix'/'second_victim_recount.json')
DE = jsread(NEW/'512_de_diagnostic'/'summary_DE.json')
DE_ROWS = {row['mode']: row for row in DE['comparison']}
TARGETS = jsread(NEW/'512_de_diagnostic'/'target_list.json')

lines = []
w = lines.append
w('# Step 15 修正版 — 三维布线策略改进实验（缓存修正、C 重跑、D/E 重定位诊断）')
w('')
w('本说明对应《三维布线策略改进实验报告（修正版）》。修正两处代码问题后重跑了 C 的 512 与 1024 主实验，')
w('并补做了一组来自真实终态的 D/E 重定位诊断；A/B 沿用此前已验证的原始记录。')
w('所有指标都是 0.1 mm 中心线近距对数，不代表无碰撞版图、损耗、串扰或制造合规。')
w('')
w('## 一、修正内容')
w('')
w('- **失败缓存**：由"按目标两条路线的版本"改为**全局布局版本**——任何被接受的路线修改都会使旧失败记录失效，')
w('  第三方路线变化后失败目标可以重新评价；布局不变时不会重复尝试。已加回归测试（含第三方变化触发重试的真实场景）。')
w('- **second_victim_success**：改为"实际获选路线对应的 victim 尝试的 priority_index == 1"；')
w('  从旧 decisions 重算（未重跑 A/B）：')
w('')
w('| 规模 | 策略 | 接受修改 | 旧口径（错） | 修正口径 |')
w('| --- | --- | ---: | ---: | ---: |')
for r in RECOUNT['records']:
    if r['strategy'] == 'A': continue
    w(f"| {r['scale']} | {r['strategy']} | {i(r['accepted_moves'])} | {i(r['old_rule_last_attempt'])} | {i(r['corrected_rule_selected_attempt'])} |")
w('')
w('## 二、修正后 C 的重跑结果')
w('')
for size in (512, 1024):
    old = OLD_SUMMARY[size]['runs']['C']['ledger']
    new = FIX[size]['ledger']
    w(f'### {size} 条连接（预算上限 {i(new["candidate_budget"])} 次候选评价）')
    w('')
    w('| 实验 | 终态近距对 | 净减少% | 接受修改 | 重定位 | 候选评价 | 目标尝试 | 停止原因 |')
    w('| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |')
    for label, entry in (('C（原记录）', old), ('C（修正重跑）', new)):
        red = 100*(entry['initial_collision_pair_count']-entry['final_collision_pair_count'])/entry['initial_collision_pair_count']
        w(f"| {label} | {i(entry['final_collision_pair_count'])} | {red:.2f}% | {i(entry['accepted_moves'])} | "
          f"{i(entry['relocations'])} | {i(entry['candidate_evaluations'])} | {i(entry.get('target_attempts', 0))} | {entry['stop_reason']} |")
    w('')
    w(f"修正后：含已抬升路线的目标尝试 {i(new['targets_with_any_elevated_route'])} 次、双方均已抬升 "
      f"{i(new['targets_with_both_elevated_route'])} 次；重定位路线尝试 {i(new['relocation_victim_attempts'])} 次、"
      f"重定位候选评价 {i(new['relocation_candidate_evaluations'])} 次、接受重定位 {i(new['relocations'])} 次。")
    w('')
w('512 条修正后终态为 44274（原记录 43750）：全局版本缓存使失败目标重复尝试增多，')
w('50 次目标尝试上限先于 720 次候选预算用尽（实际评价 666 次），成功接受从 24 次降到 22 次。')
w('这是修正语义的真实代价，未调整规则去凑回原数值。')
w('')
w('## 三、D/E 重定位诊断（512 条，起点为 B 的终态）')
w('')
w(f"起点：{i(DE['start_state']['collisions'])} 对近距对、{i(DE['start_state']['elevated_routes'])} 条已抬升路线；")
w(f"目标清单 {DE['target_count']} 对（双方均已抬升 {len(TARGETS['both_elevated'])} 对、仅一方已抬升 {len(TARGETS['one_elevated'])} 对，")
w('按路线编号元组升序预先选定，完整清单见 target_list.json）。D 只允许首次抬升，E 允许重定位；')
w('两组同起点、同清单、同顺序、同验收规则，候选评价预算上限同为 720 次。')
w('')
w('| 组 | 终态近距对 | 净减少 | 接受修改 | 接受重定位 | 重定位路线尝试 | 重定位候选评价 | 候选评价合计 | 运行时间 s |')
w('| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |')
for mode in ('D', 'E'):
    row = DE_ROWS[mode]
    w(f"| {mode} | {i(row['final_collision_pairs'])} | {i(row['net_reduction'])} | {i(row['accepted_moves'])} | "
      f"{i(row['relocations'])} | {i(row['relocation_victim_attempts'])} | {i(row['relocation_candidate_evaluations'])} | "
      f"{i(row['candidate_evaluations'])} | {f(row['runtime_seconds'], 1)} |")
w('')
w('**结论（负结果）**：E 实际生成并完整评价了 126 个重定位候选（28 次路线尝试），但没有任何一个通过全部验收规则；')
w('D 与 E 的终态完全相同（42112 对）。失败原因：70 个候选自检歧义（SELF_AMBIGUOUS_CLEARANCE）、')
w('63 个目标近距对未清除（TARGET_NOT_CLEARED）、28 个全局近距对数未严格下降（NO_STRICT_GLOBAL_DECREASE）；')
w('另有 3 个目标没有生成任何候选。因此这是"候选全部失败"，不是"没有触发重定位"。')
w('由于没有接受任何重定位，本报告不评价重定位的长度代价（D/E 的长度账目完全相同）。')
w('E 相比 D 多消耗 126 次候选评价与约 51% 的运行时间而没有收益。')
w('')
w('## 四、未得到验证的问题')
w('')
w('- 重定位在别的起点、目标或更宽松预算下是否有收益，本轮没有正面证据（也没有负面证据之外的信息）。')
w('- B 同时改动了目标选择、双方候选比较与跨路线排序三项规则，本轮结果只支持"该规则组合"的收益，')
w('  不能证明每一项改动的独立贡献。')
w('- 运行时间是单次实测，不能外推为效率结论；相同候选次数不等于相同耗时（1024 的复核与评价成本更高）。')
w('- 两套固定输入上 B 的终态低于 A；C 与 B 在两规模上并列，不能写成"最优为 B"。')
w('')
w('## 五、数据与复现')
w('')
w('- 修正后 C：`outputs/3d_strategy_v2_rev2/{512,1024}_c_fixed/`；D/E：`outputs/3d_strategy_v2_rev2/512_de_diagnostic/`；')
w('  统计重算：`outputs/3d_strategy_v2_rev2/stats_fix/second_victim_recount.json`；图：`outputs/3d_strategy_v2_rev2/figures/`。')
w('- 原实验数据与上一版报告保留在 `outputs/3d_strategy_v2/` 与 `publication/report/`（未覆盖）。')
w('')
w('```text')
w('.venv\\Scripts\\python.exe -B scripts\\run_3d_strategy_v2_rev2.py . outputs\\3d_strategy_v2_rev2\\512_c_fixed --task c_fixed --size 512')
w('.venv\\Scripts\\python.exe -B scripts\\run_3d_strategy_v2_rev2.py . outputs\\3d_strategy_v2_rev2\\1024_c_fixed --task c_fixed --size 1024')
w('.venv\\Scripts\\python.exe -B scripts\\run_3d_strategy_v2_rev2.py . outputs\\3d_strategy_v2_rev2\\512_de_diagnostic --task de --size 512')
w('.venv\\Scripts\\python.exe -B scripts\\recount_second_victim_v2.py . outputs\\3d_strategy_v2_rev2\\stats_fix')
w('.venv\\Scripts\\python.exe -B scripts\\visualize_3d_strategy_v2_rev2.py . outputs\\3d_strategy_v2 outputs\\3d_strategy_v2_rev2')
w('```')
w('')

target = ROOT/'docs'/'reports'/'step_15_rev2_strategy_v2.md'
target.write_text('\n'.join(lines), encoding='utf-8')
print(f'wrote {target}')
