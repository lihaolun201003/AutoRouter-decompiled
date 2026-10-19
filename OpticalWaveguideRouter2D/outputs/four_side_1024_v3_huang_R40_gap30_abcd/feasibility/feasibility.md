# V3 Phase-3 geometry tests and same-side feasibility

process: R=40.0 fixed, width 0.05, edge gap 0.03, clearance 0.08, board 150.0

## Required small-scale tests

| test | result | detail |
|---|---|---|
| 1_single_N_N | PASS |  |
| 1_single_E_E | PASS |  |
| 1_single_S_S | PASS |  |
| 1_single_W_W | PASS |  |
| 2_nested_u_1 | PASS | pair passed=True |
| 2_nested_u_2 | PASS | pair passed=True |
| 2_nested_u_3 | PASS | pair passed=True |
| 3_short_same_side | PASS |  |
| 4_long_same_side | PASS |  |
| 5_same_plus_opposite | PASS | pair passed=True |
| 5_same_plus_adjacent | PASS | pair passed=True |
| 6_four_sides_u | PASS | pair passed=True |
| 7_parallel_spacing | PASS | {"offset_0.05": {"expected": "invalid", "passed": false, "reason": "spacing"}, "nested_10mm": {"expected": "valid", "passed": true, "reason": null}} |
| 8_legal_crossing | PASS | pair passed=True |
| 9_illegal_overlap_rejected | PASS | pair passed=False |
| 10_transaction_rollback | PASS |  |

## Same-side canonical (sx, qx) feasibility grid

- feasible cells: 72/121 (59.5 %)
- legal family count per cell in `same_side_feasibility_grid.png`
