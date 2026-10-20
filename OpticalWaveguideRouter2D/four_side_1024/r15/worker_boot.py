"""Multiprocessing-worker bootstrap for the R15 round.

Windows spawns new processes for ``multiprocessing.Pool``; a child re-imports
``four_side_1024.v2opt.candext`` / ``.ortho90`` etc. and therefore binds the
*default* radius (R = 40 mm) unless the profile is re-applied in the child.

Every R&R / sweep task payload carries ``process_radius_mm`` (taken from the
parent's frozen ``fslw.config``); the worker entry points call
:func:`ensure_profile` before creating a layout or generating candidates.
For the historical R40 rounds the payload radius is 40 and this is a no-op.
"""
from __future__ import annotations

_ENSURED = set()


def payload_radius(payload):
    if not payload:
        return None
    value = payload.get('process_radius_mm')
    return None if value is None else float(value)


def ensure_profile(radius_mm):
    """Re-apply the parent process radius in a freshly spawned worker."""
    if radius_mm is None:
        return None
    radius = float(radius_mm)
    if radius in _ENSURED:
        return radius
    from . import profile_r15
    profile_r15.patch_radius(radius)
    _ENSURED.add(radius)
    return radius


def ensure_from_payload(payload):
    return ensure_profile(payload_radius(payload))
