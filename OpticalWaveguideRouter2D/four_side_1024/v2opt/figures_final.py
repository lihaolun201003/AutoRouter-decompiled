"""Final figures of the V2 optimisation round (reuses the frozen fslw plotting stack).

For the delivered plane layouts (BASE / E1 / E2 / E3 / Z1OPT / BEST) this renders the
same per-plane figure set as the previous round (full-board routing, detail, crossing
heatmap, radius check, congestion zoom), so the optimised layouts are directly
comparable with the historical ones.  It also renders a success/failure map of the
best z2 plane.

Run after ``v2opt.finalize`` has produced audit_strict.json / statistics.json.
"""
from __future__ import annotations

import json
from pathlib import Path

from .core import DEFAULT_OUT

LABELS = ('BASE', 'E1', 'E2', 'E3', 'Z1OPT', 'BEST')


def render_plane_figures(label, plane, log=print):
    from ..fslw import metrics as fslw_metrics
    from ..fslw import plots as fslw_plots
    run_dir = Path(DEFAULT_OUT) / 'planes' / 'V2' / label / plane
    if not (run_dir / 'routes.json').exists():
        log(f'{label}/{plane}: no routes.json, skipped')
        return None
    statistics = fslw_metrics.build_plane_statistics(run_dir, quiet=True) \
        if not (run_dir / 'statistics.json').exists() else \
        json.loads((run_dir / 'statistics.json').read_text(encoding='utf-8'))
    result = fslw_plots.render_plane(
        run_dir, statistics, with_detail=True, with_heatmap=True,
        with_radius=True, with_congestion=True, with_svg_gds=False, verbose=False)
    log(f'{label}/{plane}: plane figures -> {result if isinstance(result, str) else "ok"}')
    return result


def main(log=print):
    manifest = {}
    for label in LABELS:
        for plane in ('z1', 'z2'):
            run_dir = Path(DEFAULT_OUT) / 'planes' / 'V2' / label / plane
            if not run_dir.exists():
                continue
            try:
                render_plane_figures(label, plane, log=log)
                manifest[f'{label}/{plane}'] = str(run_dir)
            except Exception as exc:  # noqa: BLE001 - figure failure must not hide data
                log(f'{label}/{plane}: figure failed {type(exc).__name__}: {exc}')
    path = Path(DEFAULT_OUT) / 'comparison' / 'figures_manifest.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=1, ensure_ascii=False),
                    encoding='utf-8')
    return manifest


if __name__ == '__main__':
    main()
