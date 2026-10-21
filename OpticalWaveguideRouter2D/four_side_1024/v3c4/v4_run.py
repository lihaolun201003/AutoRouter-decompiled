"""Runner / artefact writer / plotting for the V4-C4 same-side routing round.

Usage::

    python -m four_side_1024.v3c4.v4_run                # full V4 experiment
    python -m four_side_1024.v3c4.v4_run --skip-z1-recovery --no-plots

The runner inserts the 56 same-side U connections into the accepted V3 964
layout, optionally tries to recover the remaining opposite group 53, re-audits
the saved layout with the frozen authoritative 2D checker, the C4 rotation audit
and the V4 connectivity identity, and writes all required figures / JSON files.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

from .profile import apply as apply_profile

OUT_ROOT_NAME = 'outputs/four_side_1024_v4_c4_routing'
RELATION_COLORS = {'opposite': '#1f6fd6', 'adjacent': '#e07b1a', 'same': '#c92a2a'}
RELATION_LABELS = {'opposite': '对边 (row1)', 'adjacent': '邻边 (row2)',
                   'same': '同边 U 形 (row2)'}


def _write_json(path, payload, indent=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=indent),
                    encoding='utf-8')
    return path


def _read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------
def validate_layout(router, payloads, combined, log=print):
    from . import validate2d
    from . import v4_connectivity as C

    errors = []
    plane_reports = {}
    for plane in ('z1', 'z2'):
        report = validate2d.audit_plane(payloads[plane], plane,
                                        label=f'V4_{plane}', log=log)
        plane_reports[plane] = report
        if not report['passed']:
            errors.append(f'{plane}_plane_audit')
    c4_report = validate2d.audit_c4_groups(combined['routes'], router.groups,
                                           router.route_group, log=log)
    if not c4_report['passed']:
        errors.append('c4_rotation_audit')
    coverage = validate2d.audit_full_coverage(combined['routes'], log=log)
    if not coverage['passed']:
        errors.append('coverage')
    identity_errors = []
    records = {int(record['route_id']): record
               for record in combined['routes']}
    for rid, connection in router.connection_by_id.items():
        record = records.get(rid)
        if record is None:
            identity_errors.append(f'{rid}:missing')
            continue
        if record['source_endpoint'] != connection['source_endpoint'] or \
                record['target_endpoint'] != connection['target_endpoint']:
            identity_errors.append(f'{rid}:endpoint')
        if record['relation'] != connection['relation']:
            identity_errors.append(f'{rid}:relation')
    if identity_errors:
        errors.append('identity')
    identity = dict(schema='four_side_1024_v4_c4_identity_v1',
                    records=len(records), connections=len(router.connection_by_id),
                    errors=identity_errors[:20], error_count=len(identity_errors),
                    passed=not identity_errors)
    log(f'[v4] identity: records={len(records)} errors={len(identity_errors)} '
        f'-> {"PASS" if identity["passed"] else "FAIL"}')
    connectivity_path = router.out_dir / 'validation_connectivity.json'
    connectivity = _read_json(connectivity_path) if connectivity_path.exists() else None
    passed = bool(not errors and connectivity and connectivity.get('passed'))
    report = dict(
        schema='four_side_1024_v4_c4_validation_v1',
        stage='v4_final',
        routed=sum(1 for record in combined['routes']
                   if record['status'] == 'routed'),
        failed=sum(1 for record in combined['routes']
                   if record['status'] != 'routed'),
        connectivity=connectivity, planes=plane_reports, c4_symmetry=c4_report,
        coverage=coverage, identity=identity,
        strict_policy='fslw.validate_fslw strict',
        errors=errors,
        passed=passed)
    log(f'[v4] integrated validation -> {"PASS" if passed else "FAIL"}')
    return report


# ---------------------------------------------------------------------------
# figures
# ---------------------------------------------------------------------------
def _sample(primitive, step_deg=6.0):
    from .plots_opt import sample_primitive
    return sample_primitive(primitive, step_deg=step_deg)


def _draw_route(ax, record, color, linewidth=0.6, alpha=0.85, zorder=3):
    for primitive in record.get('primitives') or []:
        points = _sample(primitive)
        ax.plot(points[:, 0], points[:, 1], color=color, linewidth=linewidth,
                alpha=alpha, zorder=zorder, solid_capstyle='round')


def _decorate(ax):
    from .plots_opt import draw_board
    draw_board(ax)


def plot_figures(router, combined, failed_entries, plots_dir, log=print):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.patches import Rectangle

    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    plots_dir = Path(plots_dir)
    plots_dir.mkdir(parents=True, exist_ok=True)
    records = combined['routes']
    routed = [record for record in records if record['status'] == 'routed']
    routed_by_relation = Counter(record['relation'] for record in routed)
    routed_by_plane = Counter(record['plane'] for record in routed)
    total = len(routed)

    def save(fig, name):
        png = plots_dir / name
        fig.savefig(png, dpi=220, bbox_inches='tight')
        fig.savefig(png.with_suffix('.svg'), bbox_inches='tight')
        plt.close(fig)
        log(f'[v4] figure {png.relative_to(router.out_dir)}')

    # 1. whole-board overview
    fig, ax = plt.subplots(figsize=(11.5, 11.5))
    _decorate(ax)
    for record in routed:
        _draw_route(ax, record, RELATION_COLORS[record['relation']],
                    linewidth=0.55, alpha=0.75)
    for entry in failed_entries:
        x1, y1 = entry['source_xy']
        x2, y2 = entry['target_xy']
        ax.plot([x1, x2], [y1, y2], color='#7048e8', linewidth=1.0,
                linestyle=(0, (3, 2)), zorder=6)
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 - 5, f"G{entry['group_id']}",
                fontsize=5, color='#7048e8', ha='center', zorder=7)
    for relation, color in RELATION_COLORS.items():
        ax.plot([], [], color=color, linewidth=2,
                label=f"{RELATION_LABELS[relation]}  "
                      f"{routed_by_relation.get(relation, 0)}/512")
    ax.legend(loc='upper right', fontsize=8, framealpha=0.95)
    ax.set_title('V4-C4 整板 1024 通道二维俯视布线图\n'
                 f'成功通道数 routed = {total} / 1024    '
                 f'（对边 {routed_by_relation.get("opposite", 0)}/512，'
                 f'邻边 {routed_by_relation.get("adjacent", 0)}/456，'
                 f'同边 U 形 {routed_by_relation.get("same", 0)}/56）',
                 fontsize=12)
    save(fig, '01_overview_1024.png')

    # 2. row1 opposite
    fig, ax = plt.subplots(figsize=(11.5, 11.5))
    _decorate(ax)
    for record in routed:
        if record['relation'] != 'opposite':
            continue
        _draw_route(ax, record, RELATION_COLORS['opposite'], linewidth=0.6)
    ax.set_title('V4-C4 row1 对边布线图（z = 0 mm）\n'
                 f'成功通道数 routed = {routed_by_relation.get("opposite", 0)} / 512',
                 fontsize=12)
    save(fig, '02_row1_opposite.png')

    # 3. row2 adjacent + same
    fig, ax = plt.subplots(figsize=(11.5, 11.5))
    _decorate(ax)
    for record in routed:
        if record['plane'] != 'z2':
            continue
        _draw_route(ax, record, RELATION_COLORS[record['relation']],
                    linewidth=0.65 if record['relation'] == 'same' else 0.5,
                    alpha=0.9 if record['relation'] == 'same' else 0.6)
    ax.plot([], [], color=RELATION_COLORS['adjacent'], linewidth=2,
            label=f"邻边 {routed_by_relation.get('adjacent', 0)}/456")
    ax.plot([], [], color=RELATION_COLORS['same'], linewidth=2,
            label=f"同边 U 形 {routed_by_relation.get('same', 0)}/56")
    ax.legend(loc='upper right', fontsize=9)
    ax.set_title('V4-C4 row2 邻边与同边布线图（z = 0.5 mm）\n'
                 f'成功通道数 routed = {routed_by_plane.get("z2", 0)} / 512',
                 fontsize=12)
    save(fig, '03_row2_adjacent_same.png')

    # 4. same-side U zoom (canonical per-side view: x = along-edge, y = depth)
    def side_project(points, side):
        x, y = points[:, 0], points[:, 1]
        if side == 'N':
            return np.stack([x, 150.0 - y], axis=1)
        if side == 'S':
            return np.stack([150.0 - x, y], axis=1)
        if side == 'E':
            return np.stack([y, 150.0 - x], axis=1)
        return np.stack([y, x], axis=1)

    def draw_projected(ax, record, side, color, linewidth=1.5, alpha=0.95):
        for primitive in record.get('primitives') or []:
            points = side_project(_sample(primitive), side)
            ax.plot(points[:, 0], points[:, 1], color=color,
                    linewidth=linewidth, alpha=alpha, solid_capstyle='round')

    fig = plt.figure(figsize=(17, 11.5))
    grid = fig.add_gridspec(2, 3, width_ratios=(1.7, 1.7, 2.0),
                            height_ratios=(1.0, 1.0))
    axes_map = {'N': fig.add_subplot(grid[0, 0]), 'S': fig.add_subplot(grid[0, 1]),
                'E': fig.add_subplot(grid[1, 0]), 'W': fig.add_subplot(grid[1, 1])}
    for side, ax in axes_map.items():
        for record in routed:
            if record['plane'] == 'z2' and record['relation'] != 'same':
                draw_projected(ax, record, side, '#dcdcdc', linewidth=0.35,
                               alpha=0.5)
        for record in routed:
            if record['relation'] == 'same' and record['source_side'] == side:
                draw_projected(ax, record, side, RELATION_COLORS['same'],
                               linewidth=1.6)
        ax.axhline(0.0, color='#555555', linewidth=1.0)
        for index in range(1, 17):
            center = 7.5 + (index - 1) * 9.0
            ax.plot([center], [0.0], marker='|', markersize=7, color='#555555')
            ax.text(center, -3.2, f'{side}{index:02d}', ha='center', va='top',
                    fontsize=4.5, rotation=90 if side in 'EW' else 0)
        ax.set_xlim(-4, 154)
        ax.set_ylim(-8, 84)
        count = sum(1 for record in routed
                    if record['relation'] == 'same' and record['source_side'] == side)
        ax.set_title(f'{side} 边同边 U 形：{count} 条（R15）', fontsize=10)
        ax.set_xlabel('沿边坐标 (mm)', fontsize=8)
        ax.set_ylabel('进入板内深度 (mm)', fontsize=8)
        ax.tick_params(labelsize=7)
        ax.text(0.015, 0.93,
                f'本边 {count} 条同边连接\n红色 = 同边 U 形\n浅灰 = 邻边布线（背景）',
                transform=ax.transAxes, fontsize=7.5, va='top',
                bbox=dict(boxstyle='round,pad=0.25', fc='white', alpha=0.9))
    # right column: single U close-up (one concrete same-side group, N member)
    ax_zoom = fig.add_subplot(grid[:, 2])
    for record in routed:
        if record['relation'] == 'same' and record['source_side'] == 'N':
            draw_projected(ax_zoom, record, 'N', RELATION_COLORS['same'],
                           linewidth=2.0)
    ax_zoom.axhline(0.0, color='#555555', linewidth=1.2)
    ax_zoom.set_xlim(0, 150)
    ax_zoom.set_ylim(-4, 84)
    ax_zoom.set_xlabel('沿边坐标 (mm)', fontsize=8)
    ax_zoom.set_ylabel('进入板内深度 (mm)', fontsize=8)
    ax_zoom.tick_params(labelsize=7)
    ax_zoom.set_title('N 边 14 条同边 U 形叠放放大\n（R=15 mm quarter-pair：'
                      '直线 + 90° 圆弧 + 中间直线 + 90° 圆弧 + 直线）', fontsize=9)
    ax_zoom.text(0.03, 0.97,
                 '端口处直线沿内法向进入板内；\n两次 90° 圆弧（R15）转向 180°；\n'
                 '中间直线长度 = 端口间距 - 2R。\n不同组用不同深度嵌套，\n'
                 '全部与邻边布线做严格 D56 联合检测后原子提交。',
                 transform=ax_zoom.transAxes, fontsize=7.5, va='top',
                 bbox=dict(boxstyle='round,pad=0.3', fc='white', alpha=0.92))
    fig.suptitle('V4-C4 同边 U 形连接局部放大图（共 '
                 f'{routed_by_relation.get("same", 0)} 条 = 14 组 × 4 边旋转；R15）',
                 fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    save(fig, '04_same_side_u_zoom.png')

    # 5. two physical heights 3D
    fig = plt.figure(figsize=(13, 12))
    ax = fig.add_subplot(111, projection='3d')
    for record in routed:
        z = 0.0 if record['plane'] == 'z1' else 0.5
        color = RELATION_COLORS[record['relation']]
        for primitive in record.get('primitives') or []:
            points = _sample(primitive, step_deg=10.0)
            ax.plot(points[:, 0], points[:, 1], np.full(len(points), z),
                    color=color, linewidth=0.45, alpha=0.65)
    ax.set_xlim(0, 150)
    ax.set_ylim(0, 150)
    ax.set_zlim(-0.1, 0.8)
    ax.set_xlabel('x (mm)')
    ax.set_ylabel('y (mm)')
    ax.set_zlabel('z (mm)')
    ax.view_init(elev=28, azim=-60)
    for relation, color in RELATION_COLORS.items():
        ax.plot([], [], [], color=color, linewidth=2,
                label=f'{RELATION_LABELS[relation]} {routed_by_relation.get(relation, 0)}')
    ax.plot([], [], [], color='black', linewidth=2, label='row1: z = 0 mm')
    ax.plot([], [], [], color='black', linewidth=2, linestyle=':',
            label='row2: z = 0.5 mm')
    ax.legend(loc='upper left', fontsize=8)
    ax.set_title('V4-C4 两排物理高度三维布线图\n'
                 f'row1 z = 0 mm（{routed_by_plane.get("z1", 0)} 条） / '
                 f'row2 z = 0.5 mm（{routed_by_plane.get("z2", 0)} 条）\n'
                 f'成功通道数 routed = {total} / 1024（本轮无 L2–L5 抬升）',
                 fontsize=11)
    save(fig, '05_3d_two_rows.png')
    return dict(plots_dir=str(plots_dir),
                files=sorted(str(path.relative_to(router.out_dir))
                             for path in plots_dir.glob('*')))


# ---------------------------------------------------------------------------
# main pipeline
# ---------------------------------------------------------------------------
def run(out_dir=None, routing_root=None, z1_recovery_seconds=600.0,
        skip_z1_recovery=False, plots=True, log=print):
    apply_profile()
    from .v4_route import V4Router
    from . import v4_connectivity as C

    started = time.perf_counter()
    router = V4Router(routing_root=routing_root, out_dir=out_dir, log=log)
    out_dir = router.out_dir
    v4_csv = out_dir / 'optical_1024_multitomulti_connectivity_v4_c4_symmetric.csv'
    if not v4_csv.exists():
        raise FileNotFoundError(f'run v4_connectivity first: {v4_csv}')
    router.v4_csv_sha256 = C.sha256_file(v4_csv)
    validation_connectivity = _read_json(out_dir / 'validation_connectivity.json')
    log(f'[v4] V4 CSV sha256={router.v4_csv_sha256} '
        f'connectivity={"PASS" if validation_connectivity.get("passed") else "FAIL"}')

    same_started = time.perf_counter()
    inserted, insert_info = router.insert_same_groups(log=log)
    same_seconds = time.perf_counter() - same_started

    z1_recovery = None
    if not skip_z1_recovery:
        log('[v4] attempting bounded recovery of remaining opposite group 53 ...')
        z1_recovery = router.recover_opposite_group(
            time_limit=z1_recovery_seconds, log=log)
        log(f'[v4] z1 group 53 recovery: {z1_recovery.get("status")}')

    z1_state = router.states['z1']
    z2_state = router.states['z2']
    routed_z1 = len(z1_state.accepted)
    routed_z2 = len(z2_state.accepted)
    algorithm_detail = dict(
        name='V4_C4', algorithm='C4_2D', geometry_mode='d56',
        radius_mm=15.0, width_mm=0.05, edge_gap_mm=0.03, clearance_mm=0.08,
        board_mm=150.0, crossing_policy='exact',
        same_side_u_family='r15.u_geometry quarter_pair (straight + 90deg arc + '
                           'middle straight + 90deg arc + straight)',
        same_side_u_bulge_mm=sorted({info.get('params', {}).get('bulge_mm')
                                     for info in insert_info
                                     if info.get('status') == 'inserted'}),
        strategy='keep V3 964 routes; insert 14 same-side C4 groups atomically; '
                 'group-level rip-up only if needed',
        forced_symmetry=True)
    payloads, combined = router.build_all(algorithm_detail)
    validation = validate_layout(router, payloads, combined, log=log)

    # ---- save route data -------------------------------------------------
    _write_json(out_dir / 'routes_z1.json', payloads['z1'])
    _write_json(out_dir / 'routes_z2.json', payloads['z2'])
    _write_json(out_dir / 'routes_1024.json', combined)
    failed_records = [record for record in combined['routes']
                      if record['status'] != 'routed']
    failed_groups = [group for group in router.groups
                     if not all(record['status'] == 'routed'
                                for record in combined['routes']
                                if int(record['route_id']) in group['route_ids'])]
    _write_json(out_dir / 'failed_routes.json',
                dict(schema='four_side_1024_v4_c4_failed_routes_v1',
                     routed=combined['routed'], failed=combined['failed'],
                     failed_routes=failed_records,
                     failed_groups=failed_groups), indent=1)

    # ---- checkpoint / summary -------------------------------------------
    checkpoint = dict(
        schema='four_side_1024_v4_c4_checkpoint_v1',
        stage='v4_final', routed=combined['routed'], total=1024,
        routed_by_plane=dict(z1=routed_z1, z2=routed_z2),
        routed_by_relation=dict(Counter(
            record['relation'] for record in combined['routes']
            if record['status'] == 'routed')),
        same_side_inserted_groups=inserted,
        same_side_insert_info=insert_info,
        z1_group53_recovery=z1_recovery,
        v4_csv=str(v4_csv), v4_csv_sha256=router.v4_csv_sha256,
        v3_csv=router.v3_csv, v3_csv_sha256=router.v3_csv_sha256,
        timestamp=time.strftime('%Y-%m-%dT%H:%M:%S'))
    _write_json(out_dir / 'checkpoint.json', checkpoint, indent=1)
    summary = dict(
        schema='four_side_1024_v4_c4_run_summary_v1',
        routed=combined['routed'], total=1024,
        delta_vs_v3_964=combined['routed'] - 964,
        routed_by_plane=dict(z1=routed_z1, z2=routed_z2),
        routed_by_relation=dict(Counter(
            record['relation'] for record in combined['routes']
            if record['status'] == 'routed')),
        total_by_relation=dict(opposite=512, adjacent=456, same=56),
        same_side=dict(total=56, routed=sum(
            1 for record in combined['routes']
            if record['relation'] == 'same' and record['status'] == 'routed'),
            groups=14, inserted_groups=inserted),
        params=algorithm_detail,
        runtime_seconds=dict(
            same_side_insert=round(same_seconds, 2),
            z1_recovery=round((z1_recovery or {}).get('seconds', 0.0), 2),
            total=round(time.perf_counter() - started, 2)),
        same_side_insert_info=insert_info,
        z1_group53_recovery=z1_recovery,
        validation_passed=validation['passed'],
        timestamp=time.strftime('%Y-%m-%dT%H:%M:%S'))
    _write_json(out_dir / 'run_summary.json', summary, indent=1)
    _write_json(out_dir / 'validation.json', validation, indent=1)

    # ---- figures ---------------------------------------------------------
    from . import inputs as V3
    failed_entries = []
    by_id = {int(route['route_id']): route for route in V3.load_all_routes()[0]}
    for group in failed_groups:
        route = by_id[int(group['route_ids'][0])]
        failed_entries.append(dict(
            group_id=group['group_id'], kind=group['kind'],
            plane=group['plane'],
            source_xy=V3.port_xy(route['source_endpoint']),
            target_xy=V3.port_xy(route['target_endpoint']),
            route_ids=group['route_ids']))
    figure_info = {}
    if plots:
        figure_info = plot_figures(router, combined, failed_entries,
                                   out_dir / 'plots', log=log)
        summary['figures'] = figure_info
        _write_json(out_dir / 'run_summary.json', summary, indent=1)
    log(f'[v4] DONE routed={combined["routed"]}/1024 '
        f'(delta {combined["routed"] - 964}) same-side={summary["same_side"]["routed"]}/56 '
        f'validation={"PASS" if validation["passed"] else "FAIL"} '
        f'in {time.perf_counter() - started:.1f}s')
    return dict(summary=summary, validation=validation, router=router,
                payloads=payloads, combined=combined)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=None)
    parser.add_argument('--routing-root', type=Path, default=None)
    parser.add_argument('--z1-recovery-seconds', type=float, default=600.0)
    parser.add_argument('--skip-z1-recovery', action='store_true')
    parser.add_argument('--no-plots', action='store_true')
    args = parser.parse_args(argv)
    repo = Path(__file__).resolve().parents[2]
    out_dir = Path(args.out or (repo / OUT_ROOT_NAME))
    out_dir.mkdir(parents=True, exist_ok=True)
    log_handle = open(out_dir / 'run.log', 'a', encoding='utf-8')

    def log(message):
        line = time.strftime('%H:%M:%S') + ' ' + str(message)
        print(line, flush=True)
        log_handle.write(line + '\n')
        log_handle.flush()

    result = run(out_dir=out_dir, routing_root=args.routing_root,
                 z1_recovery_seconds=args.z1_recovery_seconds,
                 skip_z1_recovery=args.skip_z1_recovery,
                 plots=not args.no_plots, log=log)
    log_handle.close()
    summary = result['summary']
    print(json.dumps({key: summary[key] for key in
                      ('routed', 'delta_vs_v3_964', 'routed_by_relation',
                       'same_side', 'validation_passed')}, ensure_ascii=False))
    return result


if __name__ == '__main__':
    main()
