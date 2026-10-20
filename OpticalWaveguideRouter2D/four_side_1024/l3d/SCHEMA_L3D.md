# Corrected L1–L5 physical layer model and L3D data schema (2026-10-20 R9)

This round corrects the five-layer physical model. **The old 2.5D model is wrong** and is
kept only as history:

- OLD (wrong): `z1 plane = layer index 0 (z=0)`, `z2 plane = layer index 4 (z=0.5)`,
  and layers 1..3 are extra layers *between* 0 and 0.5 mm.  That treats the 0.5 mm
  interface row height difference as the whole five-layer stack and puts the two port
  rows on L1 and L5.
- NEW (this round): **L1 is the interface routing layer and contains BOTH port rows**
  (z1 row at physical z = 0.0 mm, z2 row at physical z = 0.5 mm, 0.5 mm real height
  difference).  L2–L5 are four additional routing layers whose physical heights are
  **not confirmed by the supervisor**.  They are parameterised simulation inputs and
  must be labelled `unconfirmed_simulation`; formal process acceptance is refused
  while they are unconfirmed.

## 1. Layer data model

```python
class LayerGeometry:
    layer_id: int                     # 1..5 (logical routing layer identity)
    layer_type: str                   # 'interface' (L1) or 'routing' (L2..L5)
    physical_z_mm: float | None       # routing layer: one physical height
    interface_rows: dict[str, float]  # L1 only: {'z1': 0.0, 'z2': 0.5}
    allowed_transitions: tuple[int, ...]
```
`LayerStack`: ordered mapping `layer_id -> LayerGeometry`, plus
`provenance: 'unconfirmed_simulation' | 'confirmed'`, `provenance_note`, and the
validated stack invariants:

1. L1 exists, `layer_type='interface'`, rows exactly `z1=0.0`, `z2=0.5`.
2. L2..L5 exist and have finite physical heights.
3. All routing-layer heights are strictly ordered, outside the interface row heights,
   and every pair of distinct physical planes is at least `CLEARANCE_MM` apart
   (`min |dz| > 0.08`).  A stack violating this is rejected.
4. `allowed_transitions` is symmetric; every routing layer is reachable from L1 and
   from every other routing layer, i.e. any pair of layers may be connected by a legal
   transition sequence.
5. L1 routes may only leave/enter at their true row height (`z1 -> 0.0`,
   `z2 -> 0.5`); no route may change its interface row.

Example exploratory stacks (all `unconfirmed_simulation`; only parameters, never a
process claim):

| stack name | L2 | L3 | L4 | L5 | note |
|---|---:|---:|---:|---:|---|
| `medium_050` (primary) | 1.0 | 1.5 | 2.0 | 2.5 | 0.5 mm spacing above the top interface row |
| `compact_025` | 0.75 | 1.0 | 1.25 | 1.5 | 0.25 mm spacing (minimum above clearance) |
| `wide_100` | 1.5 | 2.5 | 3.5 | 4.5 | 1.0 mm spacing |

All extra layers are assumed to be above the interface rows for this exploratory
round; a below-interface arrangement is possible in principle but was not simulated.
The heights are **not** supervisor-confirmed process values.

## 2. Route description (JSON, one route)

```json
{
  "route_id": 123,
  "plane": "z1",                     // source CSV row: z1 -> z=0.0, z2 -> z=0.5
  "source_row": 1,
  "target_row": 1,
  "source_port": {"xy": [x, y], "z_mm": 0.0, "layer_id": 1},
  "target_port": {"xy": [x, y], "z_mm": 0.0, "layer_id": 1},
  "start_z_mm": 0.0,
  "end_z_mm": 0.0,
  "layer_sequence": [1, 2, 3, 1],    // logical layers visited, first/last always 1
  "layer_z_sequence": [0.0, 1.0, 1.5, 0.0],
  "n_transitions": 3,
  "lifted": true,
  "layers_used": [1, 2, 3],
  "xy_length_mm": 240.5,
  "length_mm": 248.3,
  "z_span_mm": 1.5,
  "parts": [
    {"kind": "flat", "layer_id": 1, "z_mm": 0.0, "length_mm": 5.2,
     "primitives": [{"kind": "line", "p0": [x0, y0], "p1": [x1, y1]}, ...]},
    {"kind": "transition", "from_layer": 1, "to_layer": 2,
     "z0": 0.0, "z1": 1.0, "dz_mm": 1.0, "radius_mm": 15.0,
     "theta_rad": 0.2570, "footprint_mm": 7.629,
     "start": [x, y], "direction": [dx, dy], "end": [x2, y2],
     "length_mm": 7.71},
    {"kind": "flat", "layer_id": 2, "z_mm": 1.0, ...},
    ...
  ]
}
```

Rules:

- **Every route starts and ends on L1 at its own row height** (`source_port.z_mm` /
  `target_port.z_mm`; z1 = 0.0, z2 = 0.5).  Flat parts on L1 use those same heights.
- `parts` are ordered along the route; each transition joins the previous flat's end
  to the next flat's start, with identical endpoints and horizontal tangents.
- A `flat` part is a sub-chain of the (unchanged) 2D XY primitive geometry at one
  constant physical z; its `layer_id` is the logical layer it belongs to.
- A `transition` is the two-arc vertical S-curve: `theta = acos(1 - |dz|/(2R))`,
  `footprint = 2R sin(theta)`, `length = 2R theta`, horizontal projection along the
  local straight XY direction, `radius_mm = 15.0`.  It may connect **any** pair of
  distinct layers (L1↔Lk, Li↔Lj).
- Multiple transitions per route are allowed (e.g. L1→L2→L3→L1), including direct
  transitions between non-adjacent layers and transitions placed back-to-back.
- `layer_sequence` records only logical layer identities; `layer_z_sequence` records
  the real physical heights actually used.  Neither may be inferred from the other.
- A route that stays on L1 has no transitions and `layer_sequence == [1]`.

## 3. Collision semantics (true XYZ)

- Two flat parts on the **same physical z plane** are checked with the frozen strict
  2D rules (D56 index: clearance 0.08, legal crossings allowed only inside the strict
  crossing windows of the frozen policy).
- Every pair of parts with **different physical z** (including L1's two rows versus
  each other, L1 vs L2..L5, and any transition versus any flat/transition) must keep
  a true 3D centre-line distance >= 0.08 mm.  No crossing exemption applies there.
- Because layer heights are chosen > 0.08 mm apart, flat/flat cross-plane distance is
  at least the layer gap; but the validator still checks the real XYZ distance for all
  hard parts.
- `layer_id` is NOT a z coordinate: two parts with the same `layer_id` can have
  different physical heights (L1's two rows), and two parts with different `layer_id`
  must still be checked for true 3D collisions.
- Self-clearance of one route (path returns within 0.08 mm of itself) is checked in
  true 3D as well.

## 4. Independent validator acceptance semantics

`validate_l3d.py` rebuilds every transition and flat sample from the JSON **parameters**
(never trusting router flags), then checks:

1. z1/z2 both belong to L1 but have real port heights 0 / 0.5 mm.
2. Two same-column ports on the two rows keep 0.5 mm real distance even with equal XY.
3. Every route start/end is a correct L1 port with correct row height.
4. Transitions L1→L2/L3/L4/L5 are legal (R=15, tangent-continuous, endpoints).
5. Transitions between intermediate layers are legal, multiple transitions allowed.
6. Full path 3D curvature (sampled, min circumradius >= 15*(1-1e-3)), 3D clearance,
   endpoint/tangent continuity.
7. Transition segment versus L1 row routes: true 3D distance.
8. Two routes with the same logical layer but different physical height: distance.
9. `layer_id` equality/inequality never substitutes a z coordinate; invalid stacks /
   missing heights cause an explicit refusal (formal acceptance not allowed).
10. If L2–L5 heights are undefined or the stack is not physically valid, the validator
    refuses **formal acceptance** (exit nonzero / `formal_acceptance=false`); geometry
    checks may still be reported as `exploratory_pass` under `--allow-exploratory`.

The corrected model is in `l3d/layers.py`; paths are built in `l3d/paths.py`; the
routing world is in `l3d/world.py`; routing is in `l3d/router.py`; the experimental
runner is `l3d/run_l3d.py`; the independent validator is `l3d/validate_l3d.py`.
Outputs go to `outputs/four_side_1024_v2_l1l5_v01/` (R15/R40 outputs untouched).
