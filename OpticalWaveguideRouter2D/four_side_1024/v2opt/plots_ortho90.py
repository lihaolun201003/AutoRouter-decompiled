"""Old-vs-new layout comparison figures for the pure orthogonal 90-degree experiment.

Every figure is geometry-type coloured: straight axis segments are blue
(``#1565c0``), arcs are red (``#c62828``).  The old V2-BEST panels contain short-S
arcs (with per-arc sweep < 90 deg); the new panels contain only exact 90-degree
quarter arcs.  Route shapes are plotted exactly as stored in ``routes.json`` - the
drawing never modifies geometry, connectors, board scale or axes.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..d56.plots_d56 import DPI, _board_frame, draw_connectors, pyplot
from ..fslw import plots as fslw_plots
from . import plots_geomtype

ROOT = Path(__file__).resolve().parents[2]
BEST_OUT = ROOT / 'outputs/four_side_1024_v2_candidate_rr_v01'
ORTHO90_OUT = ROOT / 'outputs/four_side_1024_v2_ortho90_v01'
LINE_COLOR = plots_geomtype.LINE_COLOR
ARC_COLOR = plots_geomtype.ARC_COLOR
DISPLAY_SAGITTA_MM = plots_geomtype.DISPLAY_SAGITTA_MM


def _load_panel(run_dir):
    data = fslw_plots.load_plane(Path(run_dir))
    routed = data['routed']
    line_segments, arc_segments, _line_len, _arc_len = \
        plots_geomtype._kind_segments(routed)
    return dict(data=data, routed=routed,
                line_segments=line_segments, arc_segments=arc_segments)


def _draw_panel(ax, panel, title, subtitle, linewidth=0.4, show_legend=True):
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D
    if panel['line_segments']:
        ax.add_collection(LineCollection(
            panel['line_segments'], colors=[LINE_COLOR],
            linewidths=linewidth, alpha=0.85, zorder=3))
    if panel['arc_segments']:
        ax.add_collection(LineCollection(
            panel['arc_segments'], colors=[ARC_COLOR],
            linewidths=linewidth, alpha=0.85, zorder=4))
    _board_frame(ax)
    draw_connectors(ax, panel['data']['connectors'])
    if show_legend:
        handles = [
            Line2D([0], [0], color=LINE_COLOR, linewidth=1.4,
                   label=f"line: {len(panel['line_segments'])}"),
            Line2D([0], [0], color=ARC_COLOR, linewidth=1.4,
                   label=f"arc: {len(panel['arc_segments'])}"),
        ]
        ax.legend(handles=handles, loc='upper left', fontsize=7.0, framealpha=0.85)
    ax.set_title(title + '\n' + subtitle, fontsize=9.5)


def render_compare_plane(plane, output_path):
    """Old V2-BEST vs new ORTHO90, same geometry-type colouring, side by side."""
    plt = pyplot()
    old_dir = BEST_OUT / 'planes' / 'V2' / 'BEST' / plane
    new_dir = ORTHO90_OUT / 'planes' / 'V2' / 'ORTHO90' / plane
    old = _load_panel(old_dir)
    new = _load_panel(new_dir)
    old_routed = len(old['routed'])
    new_routed = len(new['routed'])
    fig, axes = plt.subplots(1, 2, figsize=(20.0, 10.6))
    _draw_panel(
        axes[0], old,
        f'V2-BEST (contains short-S non-90 arcs) | plane {plane} | '
        f'{old_routed}/512 routed',
        'geometry-type colour: line = blue, arc = red (arcs include short-S)')
    _draw_panel(
        axes[1], new,
        f'pure orthogonal 90-deg layout (this experiment) | plane {plane} | '
        f'{new_routed}/512 routed',
        'only axis-aligned lines + exact R=40 mm 90-deg quarter arcs (no short-S)')
    fig.suptitle(
        f'V2 plane {plane}: V2-BEST vs pure orthogonal 90-deg routing  '
        f'({old_routed}/512 -> {new_routed}/512)', fontsize=13, y=0.995)
    fig.tight_layout(rect=(0.0, 0.03, 1.0, 0.92))
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    info = dict(file=str(output_path), plane=plane,
                old_routed=old_routed, new_routed=new_routed,
                old_arcs=len(old['arc_segments']),
                new_arcs=len(new['arc_segments']),
                old_lines=len(old['line_segments']),
                new_lines=len(new['line_segments']),
                line_color=LINE_COLOR, arc_color=ARC_COLOR)
    return info


def render_compare_all(output_path):
    """2 x 2 comparison: rows z1/z2, columns old BEST / new ORTHO90."""
    plt = pyplot()
    planes = ('z1', 'z2')
    panels = {}
    for plane in planes:
        panels[(plane, 'old')] = _load_panel(
            BEST_OUT / 'planes' / 'V2' / 'BEST' / plane)
        panels[(plane, 'new')] = _load_panel(
            ORTHO90_OUT / 'planes' / 'V2' / 'ORTHO90' / plane)
    fig, axes = plt.subplots(2, 2, figsize=(20.0, 20.6))
    for row, plane in enumerate(planes):
        old = panels[(plane, 'old')]
        new = panels[(plane, 'new')]
        _draw_panel(
            axes[row][0], old,
            f'V2-BEST plane {plane} | {len(old["routed"])}/512',
            'original D56 layout (contains non-90 short-S arcs)')
        _draw_panel(
            axes[row][1], new,
            f'ORTHO90 plane {plane} | {len(new["routed"])}/512',
            'pure orthogonal: only exact 90-deg quarter arcs')
    fig.suptitle('V2 dual-height 1024 layout: V2-BEST (752/1024) vs pure 90-deg routing',
                 fontsize=15, y=0.997)
    fig.tight_layout(rect=(0.0, 0.02, 1.0, 0.955))
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=DPI)
    plt.close(fig)
    return dict(file=str(output_path))


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ORTHO90_OUT)
    args = parser.parse_args(argv)
    out = Path(args.out)
    comparison = out / 'comparison'
    comparison.mkdir(parents=True, exist_ok=True)
    manifest = {}
    # frozen per-plane figure set (routing_all / detail / heatmap / radius /
    # congestion), same style as the V2-BEST plane figures
    from ..fslw import metrics as fslw_metrics
    from ..fslw import plots as fslw_plots
    for plane in ('z1', 'z2'):
        run_dir = out / 'planes' / 'V2' / 'ORTHO90' / plane
        if not (run_dir / 'routes.json').exists():
            continue
        statistics_path = run_dir / 'statistics.json'
        statistics = (json.loads(statistics_path.read_text(encoding='utf-8'))
                      if statistics_path.exists()
                      else fslw_metrics.build_plane_statistics(run_dir, quiet=True))
        try:
            fslw_plots.render_plane(
                run_dir, statistics, with_detail=True, with_heatmap=True,
                with_radius=True, with_congestion=True, with_svg_gds=True,
                verbose=False)
            manifest[f'frozen_plane_figures_{plane}'] = str(run_dir)
            print(f'{plane}: frozen plane figure set rendered')
        except Exception as exc:  # noqa: BLE001 - figures must not hide data
            print(f'{plane}: frozen plane figures failed: {type(exc).__name__}: {exc}')
    # per-plane geometry-type figures inside the delivered plane directories
    for plane in ('z1', 'z2'):
        new_dir = out / 'planes' / 'V2' / 'ORTHO90' / plane
        if (new_dir / 'routes.json').exists():
            info = plots_geomtype.render_geomtype_plane(
                new_dir, new_dir / 'routing_geomtype.png',
                meta_path=out / 'work' / 'plots_geomtype'
                / f'ORTHO90_{plane}_meta.json')
            manifest[f'geomtype_{plane}'] = info
            print(f'{plane}: routing_geomtype.png written ({info["routed_count"]} routed)')
    for plane in ('z1', 'z2'):
        path = comparison / f'compare_{plane}.png'
        manifest[f'compare_{plane}'] = render_compare_plane(plane, path)
        print(f'{plane}: comparison -> {path}')
    all_path = comparison / 'compare_all.png'
    manifest['compare_all'] = render_compare_all(all_path)
    print(f'combined comparison -> {all_path}')
    (comparison / 'compare_manifest.json').write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False), encoding='utf-8')
    return manifest


if __name__ == '__main__':
    main()
