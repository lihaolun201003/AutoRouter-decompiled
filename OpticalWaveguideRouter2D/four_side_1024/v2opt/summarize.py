"""Build the cross-experiment comparison tables of the V2 optimisation round.

Reads only artefacts written by the experiments (plane routes.json / checkpoints /
summaries) and produces:

* ``outputs/four_side_1024_v2_candidate_rr_v01/comparison/experiment_comparison.json``
* ``outputs/four_side_1024_v2_candidate_rr_v01/comparison/experiment_comparison.md``
* ``outputs/four_side_1024_v2_candidate_rr_v01/comparison/figure_*.png``
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .core import DEFAULT_OUT, load_layout_from_checkpoint

OUT = Path(DEFAULT_OUT)
COMPARISON = OUT / 'comparison'
HISTORICAL = {
    'V1_A': 575, 'V1_B': 553, 'V1_C': 543, 'V1_D': 527,
    'V2_A': 681, 'V2_B': 677, 'V2_C': 694, 'V2_D': 638,
}
LABELS = ('BASE', 'E1', 'E2', 'E3', 'E3X', 'Z1OPT', 'BEST')


def _load_json(path):
    path = Path(path)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def _plane_records(label, plane):
    path = OUT / 'planes' / 'V2' / label / plane / 'routes.json'
    payload = _load_json(path)
    if payload is None:
        return None
    routed = {record['route_id']: record for record in payload['routes']
              if record['status'] == 'routed'}
    failed = [record for record in payload['routes'] if record['status'] != 'routed']
    return dict(payload=payload, routed=routed, failed=failed,
                by_pair=_by_pair(payload, routed),
                failure_reasons=dict(Counter(record.get('reason') or 'unknown'
                                             for record in failed)))


def _by_pair(payload, routed):
    result = {}
    for record in payload['routes']:
        pair = record['pair']
        entry = result.setdefault(pair, dict(total=0, routed=0))
        entry['total'] += 1
        if record['status'] == 'routed':
            entry['routed'] += 1
    return result


def _base_sets():
    base = {}
    for plane in ('z1', 'z2'):
        data = _plane_records('BASE', plane)
        base[plane] = set(data['routed']) if data else set()
    return base


def collect(log=print):
    base = _base_sets()
    result = dict(schema='four_side_1024_v2opt_comparison_v1',
                  historical_abcd={key: int(value) for key, value in HISTORICAL.items()},
                  baseline=dict(v2_c=694, recombined_698=True),
                  planes={}, experiments={})
    for label in LABELS:
        entry = {}
        for plane in ('z1', 'z2'):
            data = _plane_records(label, plane)
            if data is None:
                continue
            new_ids = sorted(set(data['routed']) - base[plane])
            entry[plane] = dict(routed=len(data['routed']),
                                failed=len(data['failed']),
                                by_pair=data['by_pair'],
                                failure_reasons=data['failure_reasons'],
                                new_route_ids=new_ids,
                                new_route_count=len(new_ids),
                                total=len(data['payload']['routes']))
        if 'z1' in entry and 'z2' in entry:
            entry['combined_routed'] = entry['z1']['routed'] + entry['z2']['routed']
            entry['combined_rate'] = entry['combined_routed'] / 1024.0
        result['planes'][label] = entry
    # experiment summaries (E1/E2/E3/Z1OPT)
    for label in ('E1', 'E2', 'E3'):
        summary = _load_json(OUT / 'experiments' / f'{label}_z2_summary.json')
        if summary:
            result['experiments'][label] = dict(
                budget=summary.get('budget'),
                initial=summary.get('initial_routed') or summary.get('route_summary'),
                final=summary.get('final_routed'),
                gain=summary.get('gain'),
                seconds=summary.get('seconds'),
                history=summary.get('history'),
                sizes=summary.get('sizes'),
                use_expanded=summary.get('use_expanded'))
    for label, plane in (('Z1OPT', 'z1'), ('E1', 'z2'), ('E2', 'z2'), ('E3', 'z2')):
        summary = _load_json(OUT / 'experiments' / f'{label}_{plane}_summary.json')
        if summary:
            result['experiments'][label] = result['experiments'].get(label) or {}
            result['experiments'][label].update(summary)
    sweep = _load_json(OUT / 'candidates_budget' / 'sweep_summary.json')
    if sweep:
        result['candidate_budget_sweep'] = sweep
    rr_analysis = _load_json(OUT / 'experiments' / 'rr_analysis.json')
    if rr_analysis:
        result['rr_analysis'] = rr_analysis
    reachability = _load_json(OUT / 'reachability' / 'summary.json')
    if reachability:
        result['reachability'] = reachability
    result['best_selection'] = _load_json(OUT / 'best_selection.json')
    return result


def render_figures(result, log=print):
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    COMPARISON.mkdir(parents=True, exist_ok=True)
    figures = {}

    # --- 1. overall score ladder -------------------------------------------
    labels = ['V2_B', 'V2_A', 'V2_C(原最佳)', '698组合基线']
    values = [HISTORICAL['V2_B'], HISTORICAL['V2_A'], HISTORICAL['V2_C'], 698]
    for label in ('E1', 'E2', 'E3', 'BEST'):
        entry = result['planes'].get(label)
        if entry and 'combined_routed' in entry:
            labels.append(label)
            values.append(entry['combined_routed'])
    fig, axis = plt.subplots(figsize=(9, 4.2), dpi=160)
    colors = ['#8899aa'] * 4 + ['#2e7d32', '#1565c0', '#6a1b9a', '#c62828'][:len(labels) - 4]
    bars = axis.bar(labels, values, color=colors)
    axis.axhline(698, color='#999999', linestyle='--', linewidth=1)
    axis.set_ylabel('routed / 1024')
    axis.set_title('V2 双高度 1024 通道：历史、基线与本轮最优（独立验收后）')
    axis.set_ylim(600, 800)
    for bar, value in zip(bars, values):
        axis.text(bar.get_x() + bar.get_width() / 2, value + 1, str(value),
                  ha='center', fontsize=9)
    axis.tick_params(axis='x', labelrotation=15)
    fig.tight_layout()
    path = COMPARISON / 'figure_score_ladder.png'
    fig.savefig(path)
    plt.close(fig)
    figures['score_ladder'] = str(path)

    # --- 2. candidate budget sweep ----------------------------------------
    sweep = result.get('candidate_budget_sweep') or []
    if sweep:
        budgets = [item['budget'] for item in sweep]
        found = [item['found'] for item in sweep]
        fig, axis1 = plt.subplots(figsize=(7.5, 4), dpi=160)
        axis1.plot(budgets, found, marker='o', color='#1565c0')
        axis1.set_xlabel('per-route candidate evaluation budget')
        axis1.set_ylabel('previously failed routes directly placeable')
        axis1.set_title('z2: expanded candidates, frozen 206-route layout (independent tests)')
        for x, y in zip(budgets, found):
            axis1.annotate(str(y), (x, y), textcoords='offset points',
                           xytext=(0, 6), ha='center')
        axis1.set_xscale('log', base=2)
        fig.tight_layout()
        path = COMPARISON / 'figure_candidate_budget.png'
        fig.savefig(path)
        plt.close(fig)
        figures['candidate_budget'] = str(path)

    # --- 3. R&R rounds -----------------------------------------------------
    for label in ('E2', 'E3'):
        entry = result['experiments'].get(label) or {}
        history = entry.get('history') or []
        if not history:
            continue
        fig, axis = plt.subplots(figsize=(7.5, 4), dpi=160)
        rounds = [item['round'] for item in history]
        routed = [item['routed'] for item in history]
        gains = [item['gain'] for item in history]
        axis.plot(rounds, routed, marker='o', color='#2e7d32')
        axis.set_xlabel('R&R round')
        axis.set_ylabel('routed / 512 (z2)')
        axis.set_title(f'{label}: strengthened rip-up & reroute convergence')
        for x, y, g in zip(rounds, routed, gains):
            axis.annotate(f'+{g}', (x, y), textcoords='offset points',
                          xytext=(0, 6), ha='center')
        fig.tight_layout()
        path = COMPARISON / f'figure_rr_rounds_{label}.png'
        fig.savefig(path)
        plt.close(fig)
        figures[f'rr_rounds_{label}'] = str(path)
    return figures


def render_markdown(result):
    lines = ['# V2 优化轮结果对比（自动生成）', '']
    lines.append('## 1. 历史与基线')
    lines.append('')
    lines.append('| 组合 | 布通 | 说明 |')
    lines.append('|---|---:|---|')
    for key in ('V1_A', 'V1_B', 'V1_C', 'V1_D', 'V2_A', 'V2_B', 'V2_C', 'V2_D'):
        lines.append(f'| {key} | {HISTORICAL[key]}/1024 | 上一轮历史 |')
    lines.append('| V2 组合基线 (z1=D 492 + z2=C 206) | **698/1024** | 本轮正式验收基线 |')
    lines.append('')
    lines.append('## 2. 本轮各实验（独立验收口径）')
    lines.append('')
    lines.append('| 标签 | z1 | z2 | 合计 | 新增（相对 698） | z2 新增 route id |')
    lines.append('|---|---:|---:|---:|---:|---|')
    base_combined = 698
    for label in LABELS:
        entry = result['planes'].get(label)
        if not entry or 'combined_routed' not in entry:
            continue
        z1 = entry['z1']['routed']
        z2 = entry['z2']['routed']
        new_ids = entry['z2']['new_route_ids']
        lines.append(f'| {label} | {z1} | {z2} | **{entry["combined_routed"]}** | '
                     f'{entry["combined_routed"] - base_combined:+d} | '
                     f'{", ".join(str(v) for v in new_ids) if new_ids else "-"} |')
    lines.append('')
    sweep = result.get('candidate_budget_sweep') or []
    if sweep:
        lines.append('## 3. 候选预算对照（z2，206 条已布路线冻结，逐条独立插入测试）')
        lines.append('')
        lines.append('| 每路线评价预算 | 可直接插入条数 | 评价次数合计 | 耗时 s |')
        lines.append('|---:|---:|---:|---:|')
        for item in sweep:
            lines.append(f'| {item["budget"]} | {item["found"]} | {item["evaluated"]} | '
                         f'{item["seconds"]:.1f} |')
        lines.append('')
    for label in ('E1', 'E2', 'E3', 'Z1OPT'):
        entry = result['experiments'].get(label) or {}
        history = entry.get('history') or []
        if not history and not entry.get('final'):
            continue
        lines.append(f'## {label}')
        lines.append('')
        if entry.get('initial') is not None:
            lines.append(f'- 初始 routed: {entry.get("initial")}')
        if entry.get('final') is not None:
            lines.append(f'- 最终 routed: {entry.get("final")}（gain '
                         f'{entry.get("gain"):+d}）')
        if entry.get('seconds'):
            lines.append(f'- 耗时: {entry["seconds"]:.1f} s')
        for item in history:
            lines.append(f'  - round {item["round"]}: transactions={item["transactions"]} '
                         f'improving={item["improving_results"]} '
                         f'committed={item["committed"]} gain={item["gain"]} '
                         f'routed={item["routed"]}')
        lines.append('')
    return '\n'.join(lines)


def main(log=print):
    COMPARISON.mkdir(parents=True, exist_ok=True)
    result = collect(log=log)
    result['figures'] = render_figures(result, log=log)
    (COMPARISON / 'experiment_comparison.json').write_text(
        json.dumps(result, indent=1, ensure_ascii=False), encoding='utf-8')
    markdown = render_markdown(result)
    (COMPARISON / 'experiment_comparison.md').write_text(markdown, encoding='utf-8')
    log(markdown)
    return result


if __name__ == '__main__':
    main()
