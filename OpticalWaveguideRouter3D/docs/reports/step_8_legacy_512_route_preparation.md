# Step 8: legacy 512 routing preparation V0.1

## Inputs and boundaries
C:\Users\lihao\Desktop\Graduation Project\自动排布\AutoRouter\fiberBoard512.xlsx
C:\Users\lihao\Desktop\Graduation Project\自动排布\AutoRouter\fiberBoard0data.xlsx

Loaded with load_legacy_512_snapshot, preserving original input direction. Explicit boundaries: top_y=150, bottom_y=0, tol=1e-9.

## Actual classification
Total: 512

```json
{
  "z": 288,
  "bottom_u": 112,
  "top_u": 112
}
{
  "0->150": 144,
  "150->0": 144
}
```

Invalid endpoints: 0 (all records passed classification). Results match 112 top_u, 112 bottom_u, 288 z; original-direction Z counts are 144 each.

## Interface and limitations
RoutePreparation stores only waveguide_id, route_type and side. prepare_waveguide_2d classifies a single waveguide; prepare_waveguides_2d preserves list order and IDs. No input mutation. Point2D is required; unknown/off-boundary/nonfinite positions are rejected. Boundaries must be finite, top_y > bottom_y, tolerance nonnegative and tolerance bands disjoint.

No track, orientation, middle coordinate or Route is generated. Opposite-side connections remain z without ordinary/special-Z subdivision. Future work still requires explicitly defined routing specifications and track policies. No geometry, special Z, collision or loss is invoked by preparation.

## Tests
{"models": 15, "geometry": 45, "router_2d": 27, "collision": 34, "loss": 26, "io": 28}
Total: 175 passed by direct test-function execution. Tests include invalid inputs, tolerance, order preservation, no mutation and mocked geometry entry points proving no geometry calls. No dependencies installed.
