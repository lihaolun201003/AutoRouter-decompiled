# Step 8.5-B: exact ordinary line/arc smoothing

Independent LineSegment2D, ArcSegment2D and SmoothedRoute2D models were added; existing Route remains the skeleton. Radius is derived from arc start/center; positive sweep is counterclockwise. Empty analytic routes are valid; a single-point skeleton is rejected. Duplicates and reversals are rejected, collinear redundancy normalized on a copy. Segment trimming requirements are checked before geometry creation. Shortages within tol are treated as numerical equality, not a physical radius reduction.

## Legacy 512 smoke validation
Radius=5.0 (mm for this explicitly configured legacy experiment only). Geometry functions remain unit-neutral.
```json
{
  "input_routes": 454,
  "success": 454,
  "short_segment": 0,
  "reversal": 0,
  "other_error": 0,
  "lines": 1362,
  "arcs": 908,
  "quarter_arcs": 908,
  "endpoint_errors": 0,
  "continuity_errors": 0
}
```

## Tests
{'models': 18, 'geometry': 55, 'router_2d': 48, 'collision': 44, 'loss': 26, 'io': 28}; total 219 passed through direct test-function execution. No test dependencies installed. Coverage includes signed arcs, radius/rotation consistency, line/arc lengths, tangent continuity, zero-length omission, short segments, reversals and non-mutation.

## Limits
58 unsupported special Z connections remain untouched and have no smoothed geometry. No tracks changed. No exact curve collision validation, finite-width verification or optical loss calculation has been performed. The previous skeleton collision result does not transfer to these arcs.
