# Step 8: legacy 512 track assignment V0.1

## Policy declaration
This is the new project A+G1+S1 engineering policy, not full legacy AutoRouter reproduction. No Route was generated; no geometry or collision validation was called. No special Z, interval reuse, K constraints or permanent category region locks.

## Configuration and grid
board_height=150, top_y=150, bottom_y=0, width=0.05, spacing=0.125, bend_radius=5, tol=1e-9. Units follow the legacy snapshot mm interpretation; model remains unit-neutral. Radius is explicitly configured, not a permanent constant.
Half width=0.025; pitch=0.175; lower=5.025; upper=144.975; floor((upper-lower)/pitch)+1=800. Indices 0..799; last centerline=144.85. Near-integer quotients are repaired only within numerical precision and configured tolerance.

## Ordering and ownership
Process top U, bottom U, algorithmic top-to-bottom Z, algorithmic bottom-to-top Z. U uses the left endpoint, with (pmt_id,port.id) tie-break within tol. Z uses lexicographically smaller (pmt_id,port.id). Original Waveguide direction is not mutated. Group sort key=(start.x,end.x,start.pmt_id,end.pmt_id,waveguide.id).
Top U and both Z groups scan descending; bottom U scans ascending. First empty track is taken exclusively. Failures consume no track, results return in original input order.

## Actual results
```json
{
  "grid_count": 800,
  "lower_y": 5.025,
  "upper_y": 144.975,
  "last_track_y": 144.85,
  "status": {
    "assigned": 454,
    "unsupported_geometry": 58
  },
  "groups": {
    "bottom_to_top_z": {
      "total": 144,
      "assigned": 122,
      "unsupported_geometry": 22
    },
    "bottom_u": {
      "total": 112,
      "assigned": 112
    },
    "top_to_bottom_z": {
      "total": 144,
      "unsupported_geometry": 36,
      "assigned": 108
    },
    "top_u": {
      "total": 112,
      "assigned": 112
    }
  },
  "max_used_index": 799,
  "occupied_tracks": 454
}
```

## Failures and interpretation
U with dx < 2r-tol returns unsupported_u_bend_span; Z returns unsupported_geometry. Equality passes. no_available_track means the exclusive pool was exhausted. These are assignment outcomes, not proof of physical route feasibility.
All 512 demands receive an outcome. Input reversal gives the same ID-to-assignment mapping; original objects are unchanged; occupied indices are unique. Algorithmic category counts are distinct from prior Excel-direction statistics.

857/821 from the legacy thesis use different strip/boundary/usage conventions; this centerline policy intentionally produces 800 and does not force agreement.

## Tests
188 test functions passed: models 15, geometry 45, router_2d 40, collision 34, loss 26, io 28. Executed directly with existing Python (pytest unavailable), no dependency installation.

No subsequent Route generation stage was performed.
