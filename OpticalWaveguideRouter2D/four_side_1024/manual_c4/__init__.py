"""Manual C4 adapter package: new human connectivity -> 2D/3D routing experiments.

All deliverables of the new round live under
``outputs/manual_c4_new_connectivity/``.  Existing historical packages are reused
unchanged (:mod:`four_side_1024.v2opt`, :mod:`four_side_1024.d56`,
:mod:`four_side_1024.fslw`, :mod:`four_side_1024.r15`, :mod:`four_side_1024.v3c4`);
this package only adds the new connectivity loader, state/router adapter for the
same-side U turns and the acceptance wrappers.
"""

__all__ = ['connectivity', 'state', 'router', 'audit2d', 'run2d']
