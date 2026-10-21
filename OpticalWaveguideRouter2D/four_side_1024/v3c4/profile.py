"""Apply the R15 process profile before importing radius-bound routing modules.

Every runnable script in :mod:`four_side_1024.v3c4` must call :func:`apply`
*before* importing ``v2opt.candext`` / ``v2opt.ortho90`` / any ``fsd25d`` /
``l3d`` module (they bind R at import time).
"""
from __future__ import annotations

from ..r15 import profile_r15

APPLIED = False


def apply(verbose: bool = False):
    global APPLIED
    if not APPLIED:
        profile_r15.apply(verbose=verbose)
        APPLIED = True
    return profile_r15


def radius_mm() -> float:
    from ..fslw import config as C
    return float(C.RADIUS_MM)
