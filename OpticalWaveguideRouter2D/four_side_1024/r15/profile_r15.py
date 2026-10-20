"""R15 process profile (2026-10-20 round).

The 2026-10-20 process requirement is **minimum curvature radius R = 15 mm for
every planar bend and every 3D elevation change**.  It supersedes the historical
R = 40 mm experiment convention and the PDF example radii (R = 6000 um /
R = 6137.33 um); the PDF is used for shape reference only.

Import-time radius binders
--------------------------
Several modules bind the radius at import time and therefore need the profile
applied **before** they are imported:

* ``four_side_1024.fslw.config``                  (``RADIUS_MM``, ``process_record``)
* ``four_side_1024.v2opt.candext`` / ``.ortho90`` (``R = C.RADIUS_MM``)
* ``four_side_1024.fsd25d.config25d`` / ``.path3d`` (``RADIUS_MM`` and default
  transition-radius arguments)
* ``four_side_1024.fsd25d.validate25d``          (``RADIUS_MM`` from fslw config)

Multiprocessing workers (R&R blocker analysis / transactions) are spawned as new
processes and re-import those modules, so they must call
:func:`four_side_1024.r15.worker_boot.ensure_profile` with the process radius
carried in the task payload.  ``patch_radius`` handles both the config patch and
the rebinding of already-imported module constants.

Nothing here changes the default R = 40 mm behaviour: importing this module has
no side effect until :func:`apply` / :func:`patch_radius` is called.
"""
from __future__ import annotations

import os
import sys

RADIUS_MM = 15.0
PROFILE_NAME = 'R15_min_radius_15mm'
PROFILE_NOTE = ('2026-10-20 process requirement: every planar bend and every 3D '
                'elevation S-curve uses the fixed radius R = 15 mm; this round '
                'supersedes the historical R = 40 mm convention and the PDF '
                'example radii R = 6000/6137.33 um (the PDF is a shape reference).')
R15_ROOT = 'outputs/four_side_1024_v2_r15_v01'

_APPLIED = False
_ORIGINAL_PROCESS_RECORD = None

#: modules whose module-level radius constant is bound at import time
_REBIND_CONSTANTS = {
    'four_side_1024.v2opt.candext': ('R',),
    'four_side_1024.v2opt.ortho90': ('R',),
    'four_side_1024.fslw.feasibility': ('R',),
    'four_side_1024.v2opt.ortho90_validate': ('RADIUS',),
    'four_side_1024.fsd25d.config25d': ('RADIUS_MM',),
}


def _install_process_record(radius):
    from ..fslw import config as C
    global _ORIGINAL_PROCESS_RECORD
    if _ORIGINAL_PROCESS_RECORD is None:
        _ORIGINAL_PROCESS_RECORD = C.process_record

    def process_record(**overrides):
        record = _ORIGINAL_PROCESS_RECORD(**overrides)
        record.update(dict(
            min_bend_radius_mm=float(radius),
            radius_mm=float(radius),
            fixed_radius_40mm=abs(float(radius) - 40.0) <= 1e-12,
            radius_note=(f'all arcs are exactly R={float(radius):g} mm '
                         f'({PROFILE_NAME} fixed-radius family; 2026-10-20 '
                         'process requirement)'),
            process_profile=PROFILE_NAME,
            process_profile_note=PROFILE_NOTE,
        ))
        return record

    C.process_record = process_record


def patch_radius(radius_mm):
    """Patch ``fslw.config`` and every already-imported radius binder."""
    radius = float(radius_mm)
    # children spawned by multiprocessing inherit the environment; fslw.config
    # reads this variable at import time so workers bind the same radius
    os.environ['FSLW_PROCESS_RADIUS_MM'] = f'{radius:g}'
    from ..fslw import config as C
    C.RADIUS_MM = radius
    C.FIXED_RADIUS_40MM = abs(radius - 40.0) <= 1e-12
    _install_process_record(radius)
    for module_name, attributes in _REBIND_CONSTANTS.items():
        module = sys.modules.get(module_name)
        if module is None:
            continue
        for attribute in attributes:
            if hasattr(module, attribute):
                setattr(module, attribute, radius)
    return radius


def apply(verbose=False):
    """Apply the R15 (R = 15 mm) process profile (idempotent)."""
    global _APPLIED
    from ..fslw import config as C
    previous = float(C.RADIUS_MM)
    patch_radius(RADIUS_MM)
    _APPLIED = True
    if verbose:
        print(f'[r15] process profile applied: RADIUS_MM {previous:g} -> '
              f'{C.RADIUS_MM:g} mm; process_record patched; already-imported '
              f'radius constants rebound')
    return True


def assert_applied():
    from ..fslw import config as C
    if abs(float(C.RADIUS_MM) - RADIUS_MM) > 1e-12:
        raise RuntimeError('r15 profile not applied before importing the router '
                           f'(RADIUS_MM={C.RADIUS_MM})')
    return True


def check_imported_modules():
    """Return the radius each import-time binder actually uses."""
    report = {}
    from ..fslw import config as C
    report['fslw.config.RADIUS_MM'] = float(C.RADIUS_MM)
    report['fslw.config.process_record.radius'] = float(
        C.process_record().get('min_bend_radius_mm'))
    for module_name, attributes in _REBIND_CONSTANTS.items():
        module = sys.modules.get(module_name)
        if module is None:
            continue
        for attribute in attributes:
            if hasattr(module, attribute):
                report[f'{module_name}.{attribute}'] = float(getattr(module, attribute))
    try:
        from ..fsd25d import config25d as CFG
        report['fsd25d.transition_footprint_0.125'] = float(
            CFG.transition_footprint(0.125))
    except Exception as exc:  # noqa: BLE001
        report['fsd25d.transition_footprint_0.125'] = f'unavailable: {exc}'
    try:
        from ..v2opt import finalize
        report['v2opt.finalize.fslw_radius'] = float(finalize.fslw_config.RADIUS_MM)
    except Exception as exc:  # noqa: BLE001
        report['v2opt.finalize.fslw_radius'] = f'unavailable: {exc}'
    return report


if __name__ == '__main__':
    apply(verbose=True)
    import json
    print(json.dumps(check_imported_modules(), indent=1, ensure_ascii=False))
