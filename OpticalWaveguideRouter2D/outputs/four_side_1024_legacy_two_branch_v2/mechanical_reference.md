# Mechanical reference and legacy regression

Reviewed local standards visually after Poppler rendering. No upstream/workspace/module AGENTS.md was found. No legacy source code was modified.

| Quantity | Value | Verified source |
|---|---:|---|
| 16-column pitch | 0.250 mm | IEC 61754-7-3:2019 Figure 2, printed p.8 / PDF p.10; YD/T 1272.5-2019 Figure A.8(b), printed p.65 / PDF p.70 |
| Two-row centre pitch | 0.500 mm | Same figures: each row is 0.250 mm from centre line |
| 16-column end-to-end span | 3.750 mm | Derived from 15 x 0.250 mm, also +/-1.875 mm shown |
| Bare ferrule width D | 6.3-6.5 mm | IEC Figure 9 + Table 6, printed pp.15-16 / PDF pp.17-18; YD/T Figure A.1 + Table A.1, printed pp.54-55 / PDF pp.59-60 |
| Bare ferrule height U | 2.4-2.5 mm | Same tables |
| MPO coupling sleeve width H | 12.19-12.59 mm | Same figures/tables |
| MPO sleeve transverse R | <=7.7 mm | Same figures/tables |

The 9 mm connector centre pitch is provisional. With H aligned along a board edge, adjacent full MPO sleeve envelopes overlap by 3.19-3.59 mm. At pitch 9 mm and symmetric centres 7.5...142.5 mm, the first and last sleeve envelopes stay inside that edge's 0...150 mm span (1.205 mm margin using H=12.59), but they collide with their neighbours. Sixteen full sleeves placed without overlap need at least 195.04 mm (16 x 12.19 mm, zero installation clearance). Their total occupied span at pitch 9 mm is 147.19-147.59 mm, but their envelopes overlap. A bare ferrule envelope has no same-edge overlap at pitch 9 mm; this does not establish a complete mechanical connector design.

The connector face is transverse to the optical axis. Its two rows are not two planar routing layers. Any planar virtual unfolding must be identified as `virtual_unfolded` and keep row/column identities, while preserving the physical face-coordinate table separately. Coupling both physical face rows into one planar layer has not been established. The dimensions here are interface dimensions, not a vendor-specific complete package, mounting bracket or assembly drawing. Corner interactions also require the chosen package depth and mounting arrangement.

Regression command: `.venv/Scripts/python.exe -m pytest tests -v` in OpticalWaveguideRouter2D, with MPLBACKEND=Agg and QT_QPA_PLATFORM=offscreen. Result: **34 passed, 3 warnings in 66.19 s**. See `legacy_tests.log`.

The local IEC file cannot be parsed by pypdf/pdfplumber (truncated EOF/xref), but Poppler pdfinfo/rendering succeeds and the cited pages were visually inspected. YD/T is scanned; its text extraction largely returns watermarks, so geometry values were read visually from complete relevant pages.
