# Step 8: legacy 512 global collision validation V0.1

## Scope and acceptance
This is zero-width two-dimensional orthogonal centerline validation only. Between distinct routes cross is allowed and fully recorded in the returned report; touch and overlap invalidate both routes. All reported self-intersections invalidate their route. Normal adjacent bends are ignored by the existing detector. No exemptions for shared endpoints. No route mutation, reassignment or repair.

Assigned, route_generated and collision_validated are different states. Collision-valid does not mean physically manufacturable: width, spacing, bend envelopes and optical loss remain unchecked.

## Input
512 demands loaded from legacy 512 input and endpoint snapshot; A+G1+S1 configuration H=150, width=0.05, spacing=0.125, radius=5, tol=1e-9. 454 generated routes are checked; 58 unsupported_geometry demands have no Route and are excluded.

## Actual statistics
```json
{
  "route_count": 454,
  "pair_count": 102831,
  "events": {
    "cross": 47292,
    "touch": 0,
    "overlap": 0
  },
  "pairs_with_event": {
    "cross": 41147,
    "touch": 0,
    "overlap": 0
  },
  "self_routes": {
    "cross": 0,
    "touch": 0,
    "overlap": 0
  },
  "self_event_count": 0,
  "invalid_routes": 0,
  "current_policy_valid_routes": 454,
  "batch_valid": true,
  "invalid_by_category": {},
  "pair_category_events": {
    "U-U": {
      "cross": 13442
    },
    "U-Z": {
      "cross": 16920
    },
    "Z-Z": {
      "cross": 16930
    }
  }
}
```

Pair count is computed as N*(N-1)//2. Event counts represent segment-pair events, not unique physical crossing positions. Exact duplicate records are suppressed; different segment indices at the same position remain distinct. Each unordered route pair is tested once.
Current-policy valid count means routes not involved in any invalid event in this batch, not an optimized subset obtained by removing others.

## Invalid examples (at most 10)
```json
[]
```
Overlap point is None because the existing detector reports an overlapping segment relationship, not a single intersection point. All pairwise and self events remain available in BatchCollisionReport; this document intentionally contains only summary and representative examples.

## Tests
{'models': 15, 'geometry': 45, 'router_2d': 48, 'collision': 44, 'loss': 26, 'io': 28}; total 206 passed through direct test-function execution (pytest unavailable). No dependency installation. Input routes compared unchanged before/after real validation.

## Next-stage issues
Any invalid touch/overlap/self events above require a separately authorized future policy or routing change. Cross events are not failures but future crossing-loss data is still missing. This round performs no collision avoidance, special Z, interval reuse, finite-width checks, loss evaluation or rerouting.
