"""Draw one saved route with native analytic SVG geometry; do not run routing."""

from __future__ import annotations

import csv
import html
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from src.models import ArcSegment2D, LineSegment2D
from src.opt2d.freeform import FreeformParams, build_freeform_geometry
from src.opt2d.smoothing import RouteSpec, build_route_geometry


def saved_row(scheme: str) -> dict[str, str]:
    path = ROOT / 'outputs' / 'opt2d_step13_fix' / '512' / scheme / 'per_route.csv'
    with path.open(encoding='utf-8-sig', newline='') as stream:
        rows = [r for r in csv.DictReader(stream) if int(r['route_id']) == 287]
    assert len(rows) == 1
    return rows[0]


def rebuild(row: dict[str, str]):
    common = {key: float(row[column]) for key, column in [
        ('sx', 'sx_mm'), ('sy', 'sy_mm'), ('lx', 'lx_mm'), ('ly', 'ly_mm'),
        ('radius', 'radius_mm')
    ]}
    if row['geometry'] == 'freeform':
        return build_freeform_geometry(FreeformParams(
            route_id=287, **common, alpha_deg=float(row['alpha_deg']),
            t0_fraction=float(row['t0_fraction'])
        ))
    return build_route_geometry(RouteSpec(
        route_id=287, **common, track_y=float(row['track_y_mm'])
    ))


def verify(row, segments):
    line_length = sum(math.hypot(s.end.x - s.start.x, s.end.y - s.start.y)
                      for s in segments if isinstance(s, LineSegment2D))
    arc_length = sum(math.hypot(s.start.x - s.center.x, s.start.y - s.center.y)
                     * abs(s.sweep_rad) for s in segments if isinstance(s, ArcSegment2D))
    turn = sum(math.degrees(abs(s.sweep_rad))
               for s in segments if isinstance(s, ArcSegment2D))
    assert math.isclose(line_length, float(row['straight_length_mm']), abs_tol=1e-8)
    assert math.isclose(arc_length, float(row['arc_length_mm']), abs_tol=1e-8)
    assert math.isclose(turn, float(row['bend_total_deg']), abs_tol=1e-8)
    assert math.isclose(segments[0].start.x, float(row['sx_mm']), abs_tol=1e-8)
    assert math.isclose(segments[0].start.y, float(row['sy_mm']), abs_tol=1e-8)
    assert math.isclose(segments[-1].end.x, float(row['lx_mm']), abs_tol=1e-8)
    assert math.isclose(segments[-1].end.y, float(row['ly_mm']), abs_tol=1e-8)


parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1500" height="1030" viewBox="0 0 1500 1030">',
         '<rect width="1500" height="1030" fill="white"/>',
         '<g font-family="Arial, sans-serif" fill="#172330">']


def text(x, y, content, size=25, weight='normal', anchor='start', color='#172330'):
    parts.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" '
                 f'text-anchor="{anchor}" fill="{color}">{html.escape(str(content))}</text>')


text(750, 54, 'Same waveguide #287: original and optimized geometry', 36, 'bold', 'middle')
text(750, 95, 'Fixed endpoints (144.725, 150) to (8.950, 0) mm; board 150 x 150 mm', 24, anchor='middle')

rows = {}
for scheme, title, left, color in [
    ('A', 'A: original route', 120, '#28618C'),
    ('F56', 'F56: freeform route', 840, '#BD552F')
]:
    row = saved_row(scheme)
    rows[scheme] = row
    segments = rebuild(row)
    verify(row, segments)
    top, size = 200.0, 500.0
    scale = size / 150.0

    def xy(point):
        return left + point.x * scale, top + (150.0 - point.y) * scale

    text(left + size / 2, 146, title, 30, 'bold', 'middle', color)
    text(left + size / 2, 180,
         f"Radius {float(row['radius_mm']):.0f} mm | total turn {float(row['bend_total_deg']):.0f} deg",
         24, anchor='middle')
    for value in (0, 50, 100, 150):
        p = value * scale
        parts.append(f'<path d="M {left+p:.4f} {top} V {top+size} '
                     f'M {left} {top+size-p:.4f} H {left+size}" '
                     'stroke="#DFE4E8" stroke-width="1.3" fill="none"/>')
        text(left + p, top + size + 31, str(value), 21, anchor='middle')
        text(left - 19, top + size - p + 7, str(value), 21, anchor='end')
    parts.append(f'<rect x="{left}" y="{top}" width="{size}" height="{size}" '
                 'fill="none" stroke="#74808C" stroke-width="2"/>')
    text(left + size / 2, top + size + 66, 'x (mm)', 24, anchor='middle')
    parts.append(f'<text transform="translate({left-75} {top+size/2}) rotate(-90)" '
                 'font-size="24" text-anchor="middle">y (mm)</text>')

    sx, sy = xy(segments[0].start)
    path = [f'M {sx:.10f} {sy:.10f}']
    for segment in segments:
        ex, ey = xy(segment.end)
        if isinstance(segment, LineSegment2D):
            path.append(f'L {ex:.10f} {ey:.10f}')
        else:
            radius = math.hypot(segment.start.x - segment.center.x,
                                segment.start.y - segment.center.y) * scale
            large = 1 if abs(segment.sweep_rad) > math.pi else 0
            # Cartesian positive sweep becomes negative when the SVG y-axis is reflected.
            sweep = 0 if segment.sweep_rad > 0 else 1
            path.append(f'A {radius:.10f} {radius:.10f} 0 {large} {sweep} {ex:.10f} {ey:.10f}')
    parts.append(f'<path d="{" ".join(path)}" fill="none" stroke="{color}" '
                 'stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>')
    for point in (segments[0].start, segments[-1].end):
        px, py = xy(point)
        parts.append(f'<circle cx="{px:.10f}" cy="{py:.10f}" r="6" '
                     f'fill="{color}" stroke="white" stroke-width="1.5"/>')
    text(left + size - 35, top + 34, 'Start', 21, anchor='end', color=color)
    text(left + 73, top + size - 10, 'End', 21, color=color)
    text(left, 809, f"Total loss: {float(row['total_loss_db']):.4f} dB", 28, 'bold', color=color)
    text(left, 847, f"Length: {float(row['total_length_mm']):.3f} mm", 25)
    text(left, 885, f"Bend loss: {float(row['bend_loss_db']):.4f} dB", 25)
    text(left, 923, f"Crossing loss: {float(row['crossing_loss_db']):.4f} dB ({row['crossing_count']} events)", 25)

for field in ('sx_mm', 'sy_mm', 'lx_mm', 'ly_mm'):
    assert rows['A'][field] == rows['F56'][field], field
text(750, 987, 'Saved route centerlines; computed losses; all other waveguides are omitted.',
     23, anchor='middle', color='#596574')
parts.extend(['</g>', '</svg>'])
out = HERE / 'route_287_comparison.svg'
out.write_text('\n'.join(parts), encoding='utf-8')
print(json.dumps({'svg': str(out), 'verified_route_id': 287,
                  'A_loss_db': float(rows['A']['total_loss_db']),
                  'F56_loss_db': float(rows['F56']['total_loss_db']),
                  'endpoints_equal': True, 'reconstruction_checks': 'passed'}, ensure_ascii=False))
