# Phase 2 (2D) independent verification

- verdict: **PASS**
- generated: 2026-10-22T23:24:52 (runtime 6.61 s)
- failed checks: none

## Key numbers

- connections: 1024 (route_id 1..1024), physical ports used once: 2048/2048
- C4 quartets: 256 (z1 128, z2 128); kinds {'opposite': 68, 'same': 64, 'adjacent': 124}; rotation closure errors 0
- 2D routed: z1 512/512, z2 512/512, failed 0
- strict fslw pair audit: z1 29376 crossing pairs (30608 points), z2 13208 pairs (14992 points), violations 0
- unique crossing pairs: z1 29376 + z2 13208 = 42584
- min non-crossing centerline: z1 0.252049 mm, z2 0.154291 mm
- total 2D length: 97438.4405 mm
- C4 geometry: 256 groups x 3 phases exact 90 deg rotations (768 checks, forward 691, reversed 77)

## Checks

- PASS `input_files_present`
- PASS `port_model`
- PASS `connectivity_table_ids`
- PASS `manual_csv_matches_connectivity`
- PASS `port_coverage_2048_once`
- PASS `c4_orbit_structure`
- PASS `c4_groups_match_manifest`
- PASS `rotation_closure_90_180_270`
- PASS `routes_1024_identity`
- PASS `pair_metadata_consistent`
- PASS `routes_1024_header`
- PASS `failed_routes_empty`
- PASS `per_plane_matches_combined`
- PASS `fslw_strict_2d_audit`
- PASS `producer_reported_crossings_match`
- PASS `c4_geometric_rotation_256x3`
- PASS `crossing_statistics_consistent`
- PASS `relation_counts_expected`
- PASS `total_length_matches`
