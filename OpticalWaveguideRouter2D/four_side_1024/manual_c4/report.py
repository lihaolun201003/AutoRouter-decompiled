"""Final comparison table + delivery summary of the new manual C4 round.

Reads the artefacts written by phases 2-5 (and the historical V4-C4 reference
numbers) and writes:

* ``outputs/manual_c4_new_connectivity/comparison_table.json`` / ``.md``
* ``outputs/manual_c4_new_connectivity/SUMMARY.md`` (delivery index + results)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'outputs/manual_c4_new_connectivity'
HIST = ROOT / 'outputs'


def _read(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def collect():
    data = dict(
        input=_read(OUT / 'inputs/input_validation.json'),
        phase2_summary=_read(OUT / 'phase2_2d/run_summary.json'),
        phase2_validation=_read(OUT / 'phase2_2d/validation.json'),
        phase3_summary=_read(OUT / 'phase3_initial_lift/summary.json'),
        phase3_validation=_read(OUT / 'phase3_initial_lift/validation.json'),
        phase4_table=_read(OUT / 'phase4_ablation/ablation_table.json'),
        phase5_summary=_read(OUT / 'phase5_dynamic_optimization/summary.json'),
        phase5_validation=_read(OUT / 'phase5_dynamic_optimization/after/validation.json'),
        manual_routing=_read(HIST / 'four_side_1024_v4_c4_routing/run_summary.json'),
        manual_lift=_read(HIST / 'four_side_1024_v4_c4_crossing_lift/summary.json'),
        manual_ablation=_read(HIST / 'v4_c4_layer_height_ablation/ablation_table.json'),
        manual_dynamic=_read(HIST / 'v4_c4_dynamic_layer_optimization/summary.json'),
    )
    return data


def _fmt(value, digits=0):
    if value is None:
        return '—'
    if isinstance(value, bool):
        return 'PASS' if value else 'FAIL'
    if isinstance(value, float):
        if digits == 0:
            return f'{value:,.0f}'
        return f'{value:,.{digits}f}'
    if isinstance(value, int):
        return f'{value:,}'
    return str(value)


def build_table(data):
    ablation = data.get('phase4_table') or {}
    new_ab = {row['name']: row for row in ablation.get('results') or []}
    old_ab = {row['name']: row for row in
              (data.get('manual_ablation') or {}).get('results') or []}
    phase3 = data.get('phase3_summary') or {}
    phase5 = data.get('phase5_summary') or {}
    lift = data.get('manual_lift') or {}
    routing = data.get('manual_routing') or {}
    dynamic = data.get('manual_dynamic') or {}
    phase2 = data.get('phase2_summary') or {}

    def ab_row(name, key):
        return (new_ab.get(name) or {}).get(key)

    def old_row(name, key):
        return (old_ab.get(name) or {}).get(key)

    rows = [
        dict(metric='二维布通数（条）',
             new=phase2.get('routed'), old=routing.get('routed'),
             new_text=f"{_fmt(phase2.get('routed'))} / 1024",
             old_text=f"{_fmt(routing.get('routed'))} / 1024"),
        dict(metric='二维 C4 四元组（全部布通）',
             new=phase2.get('routed_groups'), old=255,
             new_text=f"{_fmt(phase2.get('routed_groups'))} / {_fmt(phase2.get('total_groups'))}",
             old_text='255 / 256'),
        dict(metric='初始三维抬升后剩余唯一交叉线路对',
             new=phase3.get('remaining_unique_crossing_pairs'),
             old=lift.get('crossing_pairs_after'),
             new_text=_fmt(phase3.get('remaining_unique_crossing_pairs')),
             old_text=_fmt(lift.get('crossing_pairs_after'))),
        dict(metric='A 组 0.25 mm：剩余唯一交叉对',
             new=ab_row('A_0.25mm', 'remaining_unique_crossing_pairs'),
             old=old_row('A_0.25mm', 'remaining_unique_crossing_pairs'),
             new_text=_fmt(ab_row('A_0.25mm', 'remaining_unique_crossing_pairs')),
             old_text=_fmt(old_row('A_0.25mm', 'remaining_unique_crossing_pairs'))),
        dict(metric='B 组 0.50 mm：剩余唯一交叉对',
             new=ab_row('B_0.50mm', 'remaining_unique_crossing_pairs'),
             old=old_row('B_0.50mm', 'remaining_unique_crossing_pairs'),
             new_text=_fmt(ab_row('B_0.50mm', 'remaining_unique_crossing_pairs')),
             old_text=_fmt(old_row('B_0.50mm', 'remaining_unique_crossing_pairs'))),
        dict(metric='C 组 0.75 mm：剩余唯一交叉对',
             new=ab_row('C_0.75mm', 'remaining_unique_crossing_pairs'),
             old=old_row('C_0.75mm', 'remaining_unique_crossing_pairs'),
             new_text=_fmt(ab_row('C_0.75mm', 'remaining_unique_crossing_pairs')),
             old_text=_fmt(old_row('C_0.75mm', 'remaining_unique_crossing_pairs'))),
        dict(metric='D 组 1.00 mm：剩余唯一交叉对',
             new=ab_row('D_1.00mm', 'remaining_unique_crossing_pairs'),
             old=old_row('D_1.00mm', 'remaining_unique_crossing_pairs'),
             new_text=_fmt(ab_row('D_1.00mm', 'remaining_unique_crossing_pairs')),
             old_text=_fmt(old_row('D_1.00mm', 'remaining_unique_crossing_pairs'))),
        dict(metric='B 组动态优化 V2 最终剩余唯一交叉对',
             new=phase5.get('unique_crossing_pairs_after'),
             old=dynamic.get('unique_crossing_pairs_after'),
             new_text=_fmt(phase5.get('unique_crossing_pairs_after')),
             old_text=_fmt(dynamic.get('unique_crossing_pairs_after'))),
        dict(metric='动态优化 V2：单一/联合重调度/失败组救回',
             new=None, old=None,
             new_text=f"{_fmt(phase5.get('single_group_reschedules'))} / "
                      f"{_fmt(phase5.get('joint_reschedules'))} / "
                      f"{_fmt(phase5.get('recovered_failed_groups'))}",
             old_text=f"{_fmt(dynamic.get('single_group_reschedules'))} / "
                      f"{_fmt(dynamic.get('joint_reschedules'))} / "
                      f"{_fmt(dynamic.get('recovered_failed_groups'))}"),
        dict(metric='初始三维抬升：抬升四元组 / 升降次数',
             new=None, old=None,
             new_text=f"{_fmt(phase3.get('lifted_groups'))} / "
                      f"{_fmt(phase3.get('transitions'))}",
             old_text=f"{_fmt(lift.get('lifted_groups'))} / "
                      f"{_fmt(lift.get('transitions'))}"),
        dict(metric='三维总长变化（mm）',
             new=None, old=None,
             new_text=_fmt(phase3.get('length_delta_mm'), 1),
             old_text=_fmt((lift.get('length_delta_mm')), 1)),
        dict(metric='初始三维运行时间（s）',
             new=None, old=None,
             new_text=_fmt(phase3.get('runtime_seconds'), 1),
             old_text=_fmt(lift.get('runtime_seconds'), 1)),
    ]
    table = dict(schema='manual_c4_comparison_table_v1',
                 topology='MANUAL_C4', reference='V4-C4 (historical)',
                 rows=rows,
                 notes=['新 CSV 为全新人工配对，旧 V4-C4 数字仅作参考，不是预期值',
                        '交叉数为跨全部物理高度、按唯一 (route_id_a, route_id_b) 去重',
                        '层高为探索性参数，几何 PASS 不代表制造工艺正式验收'])
    return table


def comparison_markdown(table):
    lines = ['# 新连接表 vs 旧 V4-C4 对照表', '',
             '| 指标 | 新 CSV（本轮） | 旧 V4-C4（历史参考） |',
             '|---|---:|---:|']
    for row in table['rows']:
        lines.append(f"| {row['metric']} | {row['new_text']} | {row['old_text']} |")
    lines += [''] + [f'> {note}' for note in table['notes']]
    return '\n'.join(lines) + '\n'


def summary_markdown(data, table):
    phase2 = data.get('phase2_summary') or {}
    phase3 = data.get('phase3_summary') or {}
    phase3v = (data.get('phase3_validation') or {})
    phase4 = data.get('phase4_table') or {}
    phase5 = data.get('phase5_summary') or {}
    phase5v = data.get('phase5_validation') or {}
    inp = data.get('input') or {}
    lines = [
        '# MANUAL-C4 新连接表：1024 通道 C4 二维/三维布线实验（交付索引）', '',
        '## 输入',
        f"- 两份人工连接 CSV 见 `inputs/`（sha256 记录于 `inputs/input_validation.json`）",
        f"- 输入/兼容性校验：{inp.get('passed')}，"
        f"{sum(1 for c in inp.get('checks', []) if c.get('passed'))}/"
        f"{len(inp.get('checks', []))} 项 PASS",
        f"- 合成拓扑 `inputs/connectivity_1024.csv`：1024 条连接、256 个 C4 四元组、"
        f"C4 闭合 {inp.get('group_gate', {}).get('rotation_closure')}", '',
        '## 二维（阶段 2）',
        f"- 布通：{phase2.get('routed')}/{phase2.get('total')}，"
        f"C4 四元组 {phase2.get('routed_groups')}/{phase2.get('total_groups')}",
        f"- 逐平面：{phase2.get('routed_by_plane')}；按关系：{phase2.get('routed_by_relation')}",
        f"- 总长度：{phase2.get('total_length_mm')} mm；"
        f"验收：{phase2.get('validation_passed')}",
        '- 产物：`phase2_2d/`（routes_1024.json、routes_z{1,2}.json、validation.json、'
        'failed_routes.json、plots/、run.log、checkpoint）', '',
        '## 初始三维交叉抬升（阶段 3）',
        f"- 抬升四元组 {phase3.get('lifted_groups')}，升降 {phase3.get('transitions')} 次，"
        f"唯一交叉对 {phase3.get('crossing_pairs_before')} → "
        f"{phase3.get('remaining_unique_crossing_pairs')}",
        f"- 三维验收：{(phase3v.get('status') or phase3v.get('validation_status'))}"
        f"（geometry_pass={(phase3v.get('geometry_pass'))}）",
        '- 产物：`phase3_initial_lift/`（routes_l3d.json、lift_plans.json、'
        'crossings_before/after.json、summary.json、validation.json、plots/）', '',
        '## 层高对照（阶段 4）',
    ]
    for row in phase4.get('results') or []:
        lines.append(
            f"- {row['name']}：剩余唯一交叉对 "
            f"{row['remaining_unique_crossing_pairs']}，抬升 {row['lifted_groups']} 组，"
            f"升降 {row['transitions']} 次，几何 {row.get('validation_status')}"
            f"（{row.get('runtime_seconds')} s）")
    lines += [
        '- 产物：`phase4_ablation/<A_0.25mm|B_0.50mm|C_0.75mm|D_1.00mm>/` + '
        '`ablation_table.json/md` + `ablation_3d_compare.png`', '',
        '## 动态优化 V2（阶段 5）',
        f"- 唯一交叉对 {phase5.get('unique_crossing_pairs_before')} → "
        f"{phase5.get('unique_crossing_pairs_after')}",
        f"- 单一重调度 {phase5.get('single_group_reschedules')}、联合重调度 "
        f"{phase5.get('joint_reschedules')}、失败组救回 "
        f"{phase5.get('recovered_failed_groups')}",
        f"- 验收：{phase5.get('validation_status')}；"
        f"运行 {phase5.get('runtime_seconds')} s",
        '- 产物：`phase5_dynamic_optimization/`（before/、after/、actions.json、'
        "stage_records.json、summary.json、figures/、checkpoint.json）", '',
        '## 对照表', '', comparison_markdown(table),
    ]
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=OUT)
    args = parser.parse_args(argv)
    out = Path(args.out)
    data = collect()
    table = build_table(data)
    (out).mkdir(parents=True, exist_ok=True)
    (out / 'comparison_table.json').write_text(
        json.dumps(table, indent=1, ensure_ascii=False), encoding='utf-8')
    (out / 'comparison_table.md').write_text(
        comparison_markdown(table), encoding='utf-8')
    (out / 'SUMMARY.md').write_text(summary_markdown(data, table),
                                    encoding='utf-8')
    print(comparison_markdown(table))
    return table


if __name__ == '__main__':
    main()
