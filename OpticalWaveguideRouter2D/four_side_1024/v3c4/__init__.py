"""V3-C4 connectivity adapter for the existing four_side_1024 routing engines.

This package is *not* a new router: it feeds the accepted V3-C4 CSV
(``outputs/four_side_1024_v3_c4_connectivity/``) into the frozen
``fslw`` / ``d56`` / ``v2opt`` machinery and adds the group-level (C4) commit
layer on top.

The process profile (R = 15 mm) must be applied before importing any module that
binds the radius at import time; runnable entry points call
:func:`four_side_1024.v3c4.profile.apply` first.
"""
