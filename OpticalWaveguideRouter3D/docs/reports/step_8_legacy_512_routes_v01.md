# Step 8: legacy 512 Route generation V0.1

## Scope
New project A+G1+S1 policy, not full legacy reproduction. Uses existing route_waveguide_2d and existing U/Z generators. No geometry is duplicated. U uses preparation side; Z always uses horizontal orientation and assignment.track_y. Original Waveguide endpoint direction is preserved; algorithmic allocation direction does not alter routes.

## Configuration and inputs
board_height=150, top_y=150, bottom_y=0, width=0.05, spacing=0.125, bend_radius=5, tol=1e-9. Input files:
C:\Users\lihao\Desktop\Graduation Project\自动排布\AutoRouter\fiberBoard512.xlsx
C:\Users\lihao\Desktop\Graduation Project\自动排布\AutoRouter\fiberBoard0data.xlsx

## Actual results
```json
{
  "total": 512,
  "assigned": 454,
  "routes": 454,
  "skipped": {
    "unsupported_geometry": 58
  },
  "categories": {
    "z": 230,
    "bottom_u": 112,
    "top_u": 112
  },
  "errors": {
    "endpoint": 0,
    "non_2d": 0,
    "non_axis": 0,
    "duplicate": 0,
    "redundant": 0,
    "track_mismatch": 0
  }
}
```

## Integrity
All routes have correct unique waveguide IDs and input-order output; endpoints agree with original direction. All points are Point2D. No diagonal segments, consecutive duplicate points, redundant collinear points or horizontal track-coordinate mismatches were found. Point count is not fixed; normalization is supported.
58 unsupported_geometry demands remain skipped; no diagnostic routes or special Z fallback generated.

## Testing
Direct test-function execution: {'models': 15, 'geometry': 45, 'router_2d': 48, 'collision': 34, 'loss': 26, 'io': 28}; total 196 passed. No pytest installation or other new dependencies. Existing collision module tests were run as regression only; no collision validation was performed on generated routes.

## Limits
No cross-route or self-intersection validation, no track reassignment, no arcs or loss evaluation. These are orthogonal skeletons, not proven collision-free or physically rounded waveguides. Next stage remains separate.
