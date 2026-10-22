"""Per-layer true-3D figures of the **z2 (row 2)** waveguides after Manual-C4 dynamic V2.

Visualisation only: the routing result is read from
``outputs/manual_c4_new_connectivity/phase5_dynamic_optimization/after/routes_l3d.json``
and nothing is re-routed or modified.

Layer usage rule (constraint 3/4 of the task):

* only the original ``plane == 'z2'`` connections (512 of them) are considered;
  all z1 (row 1) routes are hidden;
* a route is shown in a layer figure **iff it has at least one flat (horizontal
  propagation) part on that very layer** - a route that merely passes through the
  height inside a transition S curve is *not* counted as using the layer;
* every selected route is drawn as its complete true 3D path (all flat parts of
  other layers + all R=15 rise/fall transitions), so the figure is not a sketch.

All five figures share identical axes limits, view angle and box scale.  Outputs:
``L1_z2_3d``, ``L2_3d``, ``L3_3d``, ``L4_3d``, ``L5_3d`` (PNG + SVG) and
``layer_counts.json`` under
``outputs/manual_c4_new_connectivity/z2_layer_visualization/``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from ..v3c4.profile import apply as apply_profile  # radius binder, no side effect on import

ROOT = Path(__file__).resolve().parents[2]
AFTER_DIR = ROOT / 'outputs/manual_c4_new_connectivity/phase5_dynamic_optimization/after'
OUT_DIR = ROOT / 'outputs/manual_c4_new_connectivity/z2_layer_visualization'

XLIM = (-5.0, 155.0)
YLIM = (-5.0, 155.0)
ZLIM = (-0.1, 2.7)
VIEW = dict(elev=26, azim=-58)
BOX_ASPECT = (1.0, 1.0, 0.62)
FIGSIZE = (13.2, 11.2)
DPI = 230
BOARD = 150.0

#: highlight colour of the layer that the figure is about
HIGHLIGHT = {1: '#e07b1a', 2: '#2f9e44', 3: '#7048e8', 4: '#e03131', 5: '#0c8599'}
#: muted colours of the other flat heights
MUTED = {0.0: '#1f6fd6', 0.5: '#e07b1a', 1.0: '#2f9e44', 1.5: '#7048e8',
         2.0: '#e03131', 2.5: '#0c8599'}
TRANSITION = '#8c8c8c'


def _read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def layer_specs(stack_payload):
    """Five figure specs: L1-z2 (0.5 mm) + L2..L5 from the saved layer stack."""
    specs = [dict(key='L1_z2', title='L1-z2', layer_id=1, z_mm=0.5,
                  note='接口层第二排 / row2（初始高度）')]
    for layer_id in (2, 3, 4, 5):
        z = round(float(stack_payload['layers'][str(layer_id)]['physical_z_mm']), 6)
        specs.append(dict(key=f'L{layer_id}', title=f'L{layer_id}',
                          layer_id=layer_id, z_mm=z, note=f'布线层 L{layer_id}'))
    return specs


def z2_routed(payload):
    """The 512 routed z2 (row 2) routes; z1 routes are excluded here."""
    routes = [record for record in payload['routes']
              if record.get('status') == 'routed' and record.get('plane') == 'z2']
    if len(routes) != 512:
        raise ValueError(f'expected 512 routed z2 routes, got {len(routes)}')
    return routes


def _uses_layer(record, spec):
    """True iff a *flat* part (horizontal propagation) lies on this layer."""
    layer_id = int(spec['layer_id'])
    z_wanted = float(spec['z_mm'])
    for part in record['parts']:
        if part.get('kind') != 'flat':
            continue
        if int(part.get('layer_id')) != layer_id:
            continue
        if abs(float(part.get('z_mm')) - z_wanted) > 1e-9:
            continue
        return True
    return False


def select_routes(routes, spec):
    return [record for record in routes if _uses_layer(record, spec)]


def _part_samples(part):
    from ..v3c4.lift_cross_run import _part_samples as sample
    return sample(part)


def _draw_reference(ax, z_mm, color='#e07b1a'):
    """Faint board outline + the current layer plane (visual reference only)."""
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    corners = [(0, 0), (BOARD, 0), (BOARD, BOARD), (0, BOARD)]
    for height, line_color, linestyle, width in ((0.0, '#c9c9c9', ':', 0.6),
                                                 (0.5, '#d8d8d8', '--', 0.5)):
        xs = [corner[0] for corner in corners] + [0]
        ys = [corner[1] for corner in corners] + [0]
        ax.plot(xs, ys, [height] * 5, color=line_color, linewidth=width,
                linestyle=linestyle, zorder=1)
    plane = Poly3DCollection([[(0, 0, z_mm), (BOARD, 0, z_mm),
                               (BOARD, BOARD, z_mm), (0, BOARD, z_mm)]],
                             facecolor=color, alpha=0.045,
                             edgecolor='#999999', linewidth=0.4, zorder=0)
    ax.add_collection3d(plane)


def _draw_route(ax, record, spec):
    """Complete true 3D route; the current-layer flat parts are highlighted."""
    highlight = HIGHLIGHT[int(spec['layer_id'])]
    z_wanted = float(spec['z_mm'])
    layer_id = int(spec['layer_id'])
    for part in record['parts']:
        points = _part_samples(part)
        if len(points) == 0:
            continue
        if part.get('kind') == 'flat':
            z = round(float(part.get('z_mm')), 6)
            is_current = (int(part.get('layer_id')) == layer_id
                          and abs(z - z_wanted) <= 1e-9)
            if is_current:
                ax.plot(points[:, 0], points[:, 1], points[:, 2],
                        color=highlight, linewidth=0.9, alpha=0.92,
                        solid_capstyle='round', zorder=5)
            else:
                color = MUTED.get(z, '#4d4d4d')
                ax.plot(points[:, 0], points[:, 1], points[:, 2],
                        color=color, linewidth=0.52, alpha=0.42,
                        solid_capstyle='round', zorder=3)
        else:
            ax.plot(points[:, 0], points[:, 1], points[:, 2],
                    color=TRANSITION, linewidth=0.62, alpha=0.62,
                    solid_capstyle='round', zorder=4)


def _decorate(ax, spec, count):
    from matplotlib.lines import Line2D

    ax.set_xlim(*XLIM)
    ax.set_ylim(*YLIM)
    ax.set_zlim(*ZLIM)
    ax.set_xlabel('x (mm)', labelpad=8)
    ax.set_ylabel('y (mm)', labelpad=8)
    ax.set_zlabel('z (mm)', labelpad=8)
    ax.set_xticks([0, 25, 50, 75, 100, 125, 150])
    ax.set_yticks([0, 25, 50, 75, 100, 125, 150])
    ax.set_zticks([0.0, 0.5, 1.0, 1.5, 2.0, 2.5])
    ax.view_init(**VIEW)
    ax.set_box_aspect(BOX_ASPECT)
    ax.grid(True)
    ax.set_title(
        f'z2（row2）波导 — {spec["title"]} 单层三维布线图\n'
        f'层：{spec["title"]}（{spec["note"]}）　物理高度：z = {spec["z_mm"]:g} mm　'
        f'使用该层水平传播的波导：{count} 条\n'
        '（每条显示完整 XYZ 路线，含上升/下降段和其他高度的部分；z1/row1 已隐藏）',
        fontsize=11.5, pad=14)
    handles = [Line2D([0], [0], color=HIGHLIGHT[int(spec['layer_id'])], lw=2.4,
                      label=f'{spec["title"]} 上水平传播（本图主体）'),
               Line2D([0], [0], color='#9a9a9a', lw=1.4, alpha=0.8,
                      label='其他高度的水平段（按层淡化着色）'),
               Line2D([0], [0], color=TRANSITION, lw=1.6,
                      label='升降过渡 S 曲线（R=15 mm，只在直线段）')]
    ax.legend(handles=handles, loc='upper right', fontsize=8.5,
              framealpha=0.85)


def _save(fig, png_path):
    """Fixed canvas (no tight bbox) so all five figures have identical framing."""
    png_path = Path(png_path)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png_path, dpi=DPI, facecolor='white')
    fig.savefig(png_path.with_suffix('.svg'), facecolor='white')
    return png_path


def plot_all(after_dir=None, out_dir=None, log=print):
    apply_profile()
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False

    after_dir = Path(after_dir or AFTER_DIR)
    out_dir = Path(out_dir or OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    routes_payload = _read_json(after_dir / 'routes_l3d.json')
    stack_payload = _read_json(after_dir / 'layer_stack.json')
    routes = z2_routed(routes_payload)
    specs = layer_specs(stack_payload)

    manifest = dict(
        schema='manual_c4_z2_layer_visualization_v1',
        stage='z2_only_per_layer_3d',
        source=dict(
            routes_l3d=str(after_dir / 'routes_l3d.json'),
            routes_l3d_sha256=_sha256(after_dir / 'routes_l3d.json'),
            layer_stack=str(after_dir / 'layer_stack.json'),
            layer_stack_sha256=_sha256(after_dir / 'layer_stack.json')),
        scope='z2 (row2) only; z1 (row1) routes are hidden',
        definition='a route counts for a layer iff at least one FLAT part lies '
                   'on that layer (transitions passing through the height do '
                   'not count); each selected route is drawn as its complete '
                   '3D path',
        axes=dict(xlim=XLIM, ylim=YLIM, zlim=ZLIM, view=VIEW,
                  box_aspect=BOX_ASPECT, figsize=FIGSIZE, dpi=DPI),
        z2_routed_total=len(routes),
        layers={},
        generated_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
    )
    for spec in specs:
        selected = select_routes(routes, spec)
        route_ids = sorted(int(record['route_id']) for record in selected)
        fig = plt.figure(figsize=FIGSIZE)
        ax = fig.add_subplot(111, projection='3d')
        fig.subplots_adjust(left=0.01, right=0.99, bottom=0.045, top=0.885)
        _draw_reference(ax, spec['z_mm'], HIGHLIGHT[int(spec['layer_id'])])
        for record in selected:
            _draw_route(ax, record, spec)
        if not selected:
            ax.text2D(0.5, 0.5, '该层没有波导', transform=ax.transAxes,
                      ha='center', va='center', fontsize=20, color='#888888')
        _decorate(ax, spec, len(selected))
        fig.text(0.5, 0.015,
                 '数据来源：manual_c4_new_connectivity/phase5_dynamic_optimization/'
                 'after/routes_l3d.json（1024/1024 布通；仅渲染其中 z2 的 512 条，'
                 '不重新布线、不修改任何路线）',
                 ha='center', va='center', fontsize=8, color='#666666')
        png = _save(fig, out_dir / f'{spec["key"]}_3d.png')
        plt.close(fig)
        manifest['layers'][spec['key']] = dict(
            layer_id=int(spec['layer_id']), z_mm=float(spec['z_mm']),
            title=spec['title'], note=spec['note'],
            count=len(selected), route_ids=route_ids, png=str(png),
            svg=str(png.with_suffix('.svg')))
        log(f'[z2-layer] {spec["key"]} z={spec["z_mm"]:g} mm: '
            f'{len(selected)} routes -> {png.name}')
    counts = {key: value['count'] for key, value in manifest['layers'].items()}
    manifest['counts'] = counts
    (out_dir / 'layer_counts.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')
    log(f'[z2-layer] counts: {counts}')
    log(f'[z2-layer] written {out_dir}')
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--after-dir', type=Path, default=None)
    parser.add_argument('--out', type=Path, default=None)
    args = parser.parse_args(argv)
    manifest = plot_all(after_dir=args.after_dir, out_dir=args.out,
                        log=lambda message: print(message, flush=True))
    print(json.dumps(manifest['counts'], ensure_ascii=False))
    return manifest


if __name__ == '__main__':
    main()
