# Phase-2 geometric feasibility at R=40 mm

board 150.0 mm, R = 40.0 mm (fixed), width 0.05 mm, edge gap 0.03 mm, centreline clearance 0.08 mm

## Required family checks

| family test | result | primitives | radii | errors |
|---|---|---:|---|---|
| opposite_straight_N_S | PASS | 1 | [] |  |
| opposite_E_W_U | PASS | 4 | [40.0] |  |
| adjacent_N_E_L | PASS | 3 | [40.0] |  |
| adjacent_E_S_turn_shift | PASS | 4 | [40.0] |  |
| opposite_short_S | PASS | 4 | [40.0] |  |
| adjacent_Z3 | PASS | 7 | [40.0] |  |
| adjacent_Z5 | FAIL | 0 | None | no_geometry |
| adjacent_LEFT_C | FAIL | 0 | None | no_geometry |
| short_S_d5 | PASS | 4 | [40.0] |  |
| short_S_d40 | PASS | 4 | [40.0] |  |
| short_S_d79 | PASS | 4 | [40.0] |  |

## Adjacent canonical (sx, qy) grid

- feasible cells: 62/121 (51.2 %)
- see `adjacent_feasibility_grid.png` and `feasibility.json`

## Route-level candidate availability (real connections)

- V1_z1: 512/512 have >=1 legal candidate; 0 blocked ({})
- V1_z2: 398/512 have >=1 legal candidate; 114 blocked ({'EN': 31, 'ES': 26, 'NW': 28, 'SW': 29})
- V2_z1: 512/512 have >=1 legal candidate; 0 blocked ({})
- V2_z2: 384/512 have >=1 legal candidate; 128 blocked ({'EN': 32, 'ES': 32, 'NW': 32, 'SW': 32})

## A/B/C classification

- A (mathematically impossible at R=40): the adjacent families need a 40 mm quarter turn plus >=2R=80 mm straight runs between double-corner segments; with the canonical port at s_x and the target row q_y the reachable set is the complement of the infeasible regions in the grid above. The final quarter turn into the x=150 edge must be centred at x<=110 and at y = q_y +/- R, which forces q_y >= R (approach from below) or the approach-from-above shape that needs >= 2R of horizontal travel before the descent; that is what blocks the s_x >= 40 / q_y < 40 and s_x >= 120 regions.
- B (template coverage): every gap in the grid was re-tested with the full family set (L, TURN_S, SHIFT_TURN, Z3, Z5, LEFT); adding more families does not fill the mathematically empty regions, but exotic multi-S chains are not enumerated - recorded as residual template risk.
- C (program error): ruled out for the reported families by validate() re-checks and by the independent validator round-trip on emitted geometry.
