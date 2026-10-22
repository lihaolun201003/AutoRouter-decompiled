"""L2-L5 layer-spacing ablation for the V4-C4 crossing-avoidance 3D lift.

Four independent runs (A 0.25 mm / B 0.50 mm / C 0.75 mm / D 1.00 mm layer
spacing) start from the same un-lifted V4 1020-route baseline and use the same
search budget / termination rule.  Only the layer stack heights are changed.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

CONFIGS = [
    dict(name='A_0.25mm', heights=[0.75, 1.00, 1.25, 1.50]),
    dict(name='B_0.50mm', heights=[1.00, 1.50, 2.00, 2.50]),
    dict(name='C_0.75mm', heights=[1.25, 2.00, 2.75, 3.50]),
    dict(name='D_1.00mm', heights=[1.50, 2.50, 3.50, 4.50]),
]
ROOT_NAME = 'outputs/v4_c4_layer_height_ablation'


def repo_root():
    return Path(__file__).resolve().parents[2]


def _write_json(path, payload, indent=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=indent),
                    encoding='utf-8')
    return path


def _read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


# ---------------------------------------------------------------------------
# smoke tests (small number of C4 groups per configuration)
# ---------------------------------------------------------------------------
def run_smoke(root, cache_path, groups=2, v4_root=None, log=print):
    from . import lift_cross_run
    results = {}
    for config in CONFIGS:
        smoke_dir = Path(root) / config['name'] / 'smoke'
        log(f'[ablation] smoke {config["name"]} heights={config["heights"]}')
        result = lift_cross_run.run(
            out_dir=smoke_dir, v4_root=v4_root, heights=config['heights'],
            crossing_cache=str(cache_path), smoke_groups=groups,
            time_limit=600.0, plots=False, log=log)
        validation = result.get('validation') or {}
        results[config['name']] = dict(
            layer_heights_mm=config['heights'],
            lifted_groups=len(result['lifter'].lifted) // 4,
            validation_status=validation.get('status'),
            validation_pass=validation.get('exploratory_pass'),
            validation_counts=validation.get('counts'))
        log(f'[ablation] smoke {config["name"]}: groups='
            f'{results[config["name"]]["lifted_groups"]} '
            f'validation={validation.get("status")}')
    _write_json(Path(root) / 'smoke_results.json', results, indent=1)
    return results


# ---------------------------------------------------------------------------
# full four runs (parallel, identical budget)
# ---------------------------------------------------------------------------
def run_full(root, cache_path, max_groups=150, time_limit=3000.0, v4_root=None,
             log=print):
    root = Path(root)
    env = dict(__import__('os').environ)
    env['PYTHONPATH'] = str(repo_root())
    processes = []
    for config in CONFIGS:
        out_dir = root / config['name']
        out_dir.mkdir(parents=True, exist_ok=True)
        command = [sys.executable, '-X', 'utf8', '-m',
                   'four_side_1024.v3c4.lift_cross_run',
                   '--out', str(out_dir),
                   '--layer-heights',
                   ','.join(str(value) for value in config['heights']),
                   '--crossing-cache', str(cache_path),
                   '--max-groups', str(max_groups),
                   '--time-limit', str(time_limit)]
        if v4_root is not None:
            command += ['--v4-root', str(v4_root)]
        log_file = open(out_dir / 'process.log', 'a', encoding='utf-8')
        process = subprocess.Popen(command, stdout=log_file, stderr=subprocess.STDOUT,
                                   env=env)
        processes.append(dict(config=config, process=process, log=log_file))
        log(f'[ablation] started {config["name"]} pid={process.pid}')
    for item in processes:
        item['process'].wait()
        item['log'].close()
        log(f'[ablation] finished {item["config"]["name"]} '
            f'exit={item["process"].returncode}')
    return processes


# ---------------------------------------------------------------------------
# post-processing: comparison table + combined 3D figure
# ---------------------------------------------------------------------------
def build_comparison(root, label='V4-C4', log=print):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from ..l3d import layers as LL
    from .lift_cross_run import (LAYER_PALETTE, Z_AXIS_LIMIT_MM,
                                 _part_samples, z_style_map)

    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    root = Path(root)
    rows = []
    payloads = {}
    for config in CONFIGS:
        cfg_dir = root / config['name']
        summary = _read_json(cfg_dir / 'summary.json')
        validation = _read_json(cfg_dir / 'validation.json')
        paths = _read_json(cfg_dir / 'crossings_after.json')
        payload = _read_json(cfg_dir / 'routes_l3d.json')
        payloads[config['name']] = (payload, config['heights'])
        stats = validation.get('stats') or {}
        rows.append(dict(
            name=config['name'],
            layer_heights_mm=config['heights'],
            routed=summary['routed_after'],
            remaining_unique_crossing_pairs=summary[
                'remaining_unique_crossing_pairs'],
            crossing_reduction_ratio=summary['crossing_reduction_ratio'],
            crossing_pairs_before=summary['crossing_pairs_before'],
            crossing_points_by_height=summary.get('crossing_points_by_height'),
            new_high_layer_crossing_pairs=summary.get(
                'new_high_layer_crossing_pairs_unique'),
            lifted_groups=summary['lifted_groups'],
            transitions=summary['transitions'],
            length_delta_mm=summary['length_delta_mm'],
            length_total_after_mm=summary['length_total_after_mm'],
            min_3d_clearance_mm=summary.get('min_3d_clearance_mm'),
            runtime_seconds=summary['runtime_seconds'],
            termination=summary.get('termination'),
            validation_status=validation.get('status'),
            geometry_pass=bool(validation.get('exploratory_pass')),
            validation_counts=validation.get('counts'),
            reverted_groups=summary.get('reverted_groups',
                                        len(summary.get('reverted_group_ids') or [])),
        ))
    table = dict(schema='v4_c4_layer_height_ablation_table_v1',
                 topology_label=label,
                 configs=CONFIGS, results=rows,
                 notes=[f'all four runs start from the same un-lifted {label} '
                        '1024-channel baseline',
                        'crossing statistics use unique (route_id_a, route_id_b) '
                        'pairs deduplicated across all physical heights',
                        'L2-L5 heights are exploratory process assumptions; '
                        'geometry PASS is not a formal manufacturing acceptance'])
    _write_json(root / 'ablation_table.json', table, indent=1)
    lines = [f'# {label} L2–L5 层间距对照实验（交叉规避式三维抬升）', '',
             '| 指标 | 0.25 mm (A) | 0.50 mm (B) | 0.75 mm (C) | 1.00 mm (D) |',
             '|---|---:|---:|---:|---:|']
    keys = [('布通数', 'routed'), ('剩余唯一交叉线路对',
                                   'remaining_unique_crossing_pairs'),
            ('交叉减少比例', 'crossing_reduction_ratio'),
            ('抬升四元组数量', 'lifted_groups'),
            ('实际升降次数', 'transitions'),
            ('总三维路线长度增量 (mm)', 'length_delta_mm'),
            ('最小三维净空 (mm)', 'min_3d_clearance_mm'),
            ('运行时间 (s)', 'runtime_seconds'),
            ('终止原因', 'termination'),
            ('几何验收', 'geometry_pass')]
    for metric_label, key in keys:
        values = []
        for row in rows:
            value = row.get(key)
            if key == 'crossing_reduction_ratio' and value is not None:
                values.append(f'{100.0 * float(value):.2f}%')
            elif key == 'geometry_pass':
                values.append('PASS' if value else 'FAIL')
            elif isinstance(value, float):
                values.append(f'{value:.3f}')
            else:
                values.append(str(value))
        lines.append('| ' + metric_label + ' | ' + ' | '.join(values) + ' |')
    lines += ['', f'每组从同一 {label} 未抬升 1024 条基线独立开始，预算相同 '
                  '（max_groups=150, time_limit=3000 s）。',
              'L2–L5 层高为探索性工艺假设，几何 PASS 不等同于正式制造验收。']
    (root / 'ablation_table.md').write_text('\n'.join(lines) + '\n',
                                            encoding='utf-8')
    log(f'[ablation] table written {root / "ablation_table.md"}')
    print('\n'.join(lines))

    # combined 3D comparison, identical axis range / colour mapping
    fig = plt.figure(figsize=(17, 15))
    for index, config in enumerate(CONFIGS):
        ax = fig.add_subplot(2, 2, index + 1, projection='3d')
        payload, heights = payloads[config['name']]
        stack = LL.build_stack('ablation_custom',
                               heights={2: heights[0], 3: heights[1],
                                        4: heights[2], 5: heights[3]})
        style = z_style_map(stack)
        for record in payload['routes']:
            if record.get('status') != 'routed':
                continue
            for part in record['parts']:
                points = _part_samples(part)
                if len(points) == 0:
                    continue
                if part['kind'] == 'flat':
                    color = style.get(round(float(part['z_mm']), 6),
                                      ('#444444', ''))[0]
                else:
                    color = '#7a7a7a'
                ax.plot(points[:, 0], points[:, 1], points[:, 2],
                        color=color, linewidth=0.45, alpha=0.7)
        ax.set_xlim(0, 150)
        ax.set_ylim(0, 150)
        ax.set_zlim(-0.1, Z_AXIS_LIMIT_MM)
        ax.set_xlabel('x')
        ax.set_ylabel('y')
        ax.set_zlabel('z (mm)')
        ax.view_init(elev=26, azim=-58)
        row = rows[index]
        ax.set_title(f'{config["name"]}  L2-L5 = {heights}\n'
                     f'groups={row["lifted_groups"]}, unique pairs='
                     f'{row["remaining_unique_crossing_pairs"]}, '
                     f'valid={row["validation_status"]}', fontsize=9)
    handles = []
    from matplotlib.lines import Line2D
    handles.append(Line2D([0], [0], color='#1f6fd6', lw=2, label='L1 row1 z=0'))
    handles.append(Line2D([0], [0], color='#e07b1a', lw=2, label='L1 row2 z=0.5'))
    for layer_id, color in LAYER_PALETTE.items():
        handles.append(Line2D([0], [0], color=color, lw=2, label=f'L{layer_id}'))
    handles.append(Line2D([0], [0], color='#7a7a7a', lw=2, label='S transition'))
    fig.legend(handles=handles, loc='upper right', fontsize=9)
    fig.suptitle(f'{label} 层间距对照：四组实际三维布线图（统一坐标范围与颜色映射）',
                 fontsize=14)
    png = root / 'ablation_3d_compare.png'
    fig.savefig(png, dpi=200, bbox_inches='tight')
    fig.savefig(png.with_suffix('.svg'), bbox_inches='tight')
    plt.close(fig)
    log(f'[ablation] combined 3D figure {png}')
    return table


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=None)
    parser.add_argument('--v4-root', type=Path, default=None,
                        help='routing root providing routes_1024.json '
                             '(default: historical V4-C4 routing root)')
    parser.add_argument('--label', default='V4-C4')
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--full', action='store_true')
    parser.add_argument('--postprocess', action='store_true')
    parser.add_argument('--smoke-groups', type=int, default=2)
    parser.add_argument('--max-groups', type=int, default=150)
    parser.add_argument('--time-limit', type=float, default=3000.0)
    args = parser.parse_args(argv)
    root = Path(args.root or (repo_root() / ROOT_NAME))
    root.mkdir(parents=True, exist_ok=True)
    cache_path = root / 'baseline_crossings.json'
    log_handle = open(root / 'ablation_run.log', 'a', encoding='utf-8')

    def log(message):
        line = time.strftime('%H:%M:%S') + ' ' + str(message)
        print(line, flush=True)
        log_handle.write(line + '\n')
        log_handle.flush()

    if not cache_path.exists():
        from . import lift_cross_run
        log('[ablation] building shared un-lifted crossing cache ...')
        lift_cross_run.run(out_dir=root / '_cache_builder',
                           v4_root=args.v4_root,
                           crossing_cache=str(cache_path),
                           heights=None, max_groups=0, time_limit=1.0,
                           plots=False, log=log)
    if args.smoke:
        run_smoke(root, cache_path, groups=args.smoke_groups,
                  v4_root=args.v4_root, log=log)
    if args.full:
        run_full(root, cache_path, max_groups=args.max_groups,
                 time_limit=args.time_limit, v4_root=args.v4_root, log=log)
        build_comparison(root, label=args.label, log=log)
    if args.postprocess:
        build_comparison(root, label=args.label, log=log)
    log_handle.close()


if __name__ == '__main__':
    main()
