# Strict crossing-policy re-audit of the historical D56 result (467 routes)

Input: `outputs/four_side_1024_d56_optimized/routes.json` (467 routed / 1024 records), audited by the independent authoritative validator `four_side_1024/d56/validate_d56.py` (`policy='strict'`, no router code imported).

- routes.json SHA256: `ce96833a41f21f0515008c179f0c4cc50ca53ba069dc4cb85c0d27ce0a94a5c1`
- route geometry unchanged by this audit: **True** (SHA256 and mtime identical before/after; the `exact`-policy audit reproduces the historical `independent_audit.json` bit for bit)

## 1. Three-policy verdict on the same 467 routes

| policy | route pairs audited | invalid route pairs | violating routes | strict-legal routes | crossings | pair-audit time |
|---|---|---|---|---|---|---|
| `exact` | 467 | 0 | 0 | 467 | 57029 | 2.83 s |
| `legacy` | 467 | 8919 | 467 | 0 | 46382 | 6.43 s |
| `strict` | 467 | 1 | 2 | 465 | 57027 | 8.07 s |

Violation kinds: exact — none; legacy — spacing=8919; strict — crossing_window_overlap=1.

**Strict verdict: 465 / 467 routes pass. Exactly one route pair is illegal, so 2 routes (460, 989) are involved in the single defect.**

## 2. Every strict violation

| route pair | kind | distance (mm) | x (mm) | y (mm) |
|---|---|---|---|---|
| (460, 989) | `crossing_window_overlap` | 0.000000000 | 37.842888 | 110.995091 |

## 3. Why (460, 989) fails under strict
Route 460's two short-S arcs (A1, A2) both cross route 989's quarter arc B1, at **19.673°** and **16.810°**, only **1.727 mm** apart along route 460. Between the two crossings the two routes never leave the clearance band: their separation only rises to **0.147 mm** (limit 0.175 mm), i.e. a continuous **2.766 mm** sub-clearance run, and the exact minimal windows of the two crossings therefore contain each other: they overlap by 2.766 mm along route 460 (identical intervals) and by 0.345 mm along route 989. Just outside the merged window the separation is 0.176456 / 0.175847 mm, i.e. above the 0.1749999 mm violation limit — the window itself is minimal and correct; the violation is the non-separability of two genuine crossings, not an over-sized window.

The historical `exact` policy exempted the whole intersected primitive pairs (A1-B1 and A2-B1) and therefore accepted this pair; the strict policy exposes the real physical defect (a 2.77 mm run closer than 0.175 mm). Both routes are involved in the one pair — the count is **1 illegal pair / 2 illegal routes**, not two independent defects. Legacy (historical `clearance/sin` windows) also flags this pair, see `pair_verdicts_460_989` in the JSON.

## 4. Cross-window statistics: the exemption is local

- crossing windows (one per grouped crossing point): **57029**
- half-window max: **2.339801 mm**; mean: 0.198699 mm
- total window length per crossing (A-left+A-right+B-left+B-right) mean: **0.794796 mm**
- max single-side window length: 3.619729 mm; the 4.0 mm cap (`crossing_window_excessive`) is never hit (0 excessive pairs)

Half-window length distribution (each crossing contributes its 4 side halves):

| half-window (mm) | count | share |
|---|---|---|
| 0-0.17 | 0 | 0.00% |
| 0.17-0.25 | 209107 | 91.67% |
| 0.25-0.5 | 15736 | 6.90% |
| 0.5-1 | 2228 | 0.98% |
| 1-2 | 1043 | 0.46% |
| 2-4.001 | 2 | 0.001% |

Crossing angle vs solved window half (mean / max per angle bin):

| crossing angle (deg) | crossings | mean half (mm) | max half (mm) |
|---|---|---|---|
| 5-10 | 9 | 1.321161 | 1.825831 |
| 10-20 | 581 | 0.896046 | 2.339801 |
| 20-30 | 1208 | 0.436722 | 0.601756 |
| 30-45 | 3129 | 0.295158 | 0.377257 |
| 45-60 | 3086 | 0.222981 | 0.258066 |
| 60-75 | 1881 | 0.192354 | 0.206391 |
| 75-90 | 47135 | 0.176049 | 0.183184 |

Interpretation: 91.7% of side halves are 0.17-0.25 mm (orthogonal line-line crossings, analytic half = 0.176 mm) and the mean half-window is 0.1987 mm, i.e. ~0.13% of the mean routed path length (149.56 mm). The window grows only for genuinely shallow crossings (5-20°: 1.3 mm mean half), which is exactly the local near-region of the real geometry; the 4.0 mm exclusion cap is never triggered.

## 5. Route geometry unchanged
- SHA256 before/after: `ce96833a41f21f0515008c179f0c4cc50ca53ba069dc4cb85c0d27ce0a94a5c1` / `ce96833a41f21f0515008c179f0c4cc50ca53ba069dc4cb85c0d27ce0a94a5c1` → unchanged=True
- file size 1145885 bytes, mtime 2026-10-19T07:52:11.806654+00:00 (unchanged=True)
- `exact`-policy audit reproduces the historical `independent_audit.json`: routed 467 vs 467, crossings 57029 vs 57029, angle histogram equal=True, spacing/overlap/touch violations 0/0/0 (historical 0/0/0)

## 6. Reproduce

```powershell
.venv\Scripts\python.exe -m four_side_1024.d56.validate_d56 --run-dir outputs\four_side_1024_d56_optimized --policy strict
.venv\Scripts\python.exe -m four_side_1024.d56.validate_d56 --run-dir outputs\four_side_1024_d56_optimized --policy exact
.venv\Scripts\python.exe -m four_side_1024.d56.validate_d56 --run-dir outputs\four_side_1024_d56_optimized --policy legacy
.venv\Scripts\python.exe -m four_side_1024.abcd.crosscheck_strict
```

Machine-readable companion: `strict_reaudit_467.json` (this audit), `crosscheck_strict_467.json` (router-index vs validator per-route-pair crosscheck, mismatch=0).
