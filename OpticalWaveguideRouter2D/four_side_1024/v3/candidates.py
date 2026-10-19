"""V3 candidate dispatch: same-side families are new, opposite/adjacent are reused.

The opposite-side and adjacent-side generators are exactly the FSLW round's
(``fslw.candidates.opposite_candidates`` / ``adjacent_candidates``) because their
canonical frames are unchanged.  Same-side routes (canonical ``p=(sx,0)`` ->
``q=(qx,0)``, inward +y -> outward -y) use the new families from
:mod:`four_side_1024.v3.geom_same`; they are ranked with the same cheap line-oracle
used by the other families and legalised later by the exact strict index only.
"""
from __future__ import annotations

from ..fslw import candidates as FSLW_CANDIDATES
from ..fslw.candidates import FrameOracleSet, LineOracle, clearance_tracks  # noqa: F401
from . import geom_same

SAME_CANDIDATE_LIMIT = 40
SAME_CANDIDATE_LIMIT_DEEP = 220


def same_candidates(frame, oracle, cfg, deep=False):
    """Ranked same-side candidates (U / hairpin-A / hairpin-B)."""
    specs = []
    family_rank = {name: index for index, name in enumerate(geom_same.SAME_FAMILIES)}
    for family, params in geom_same.family_options(frame.p, frame.q, deep=deep):
        primitives = geom_same.build_family(family, frame.p, frame.q, **params)
        if primitives is None:
            continue
        top_height = max(max(primitive['p0'][1], primitive['p1'][1])
                         for primitive in primitives)
        cap = cfg.get('same_side_depth_cap')
        if cap is not None and top_height > float(cap) + 1e-9:
            continue
        score = 0.0
        if oracle is not None:
            for primitive in primitives:
                if primitive['kind'] != 'line':
                    continue
                p0, p1 = primitive['p0'], primitive['p1']
                if abs(p0[1] - p1[1]) < 1e-9:
                    score += oracle.h_parallel(p0[1], min(p0[0], p1[0]),
                                               max(p0[0], p1[0]))
                else:
                    score += oracle.v_parallel(p0[0], min(p0[1], p1[1]),
                                               max(p0[1], p1[1]))
        specs.append(((round(top_height, 3), score, family_rank[family]),
                      family, params, primitives))
    # shallowest track first: with narrow-connection-first ordering this produces the
    # nested outer-deeper / inner-shallower arch structure without double crossings.
    specs.sort(key=lambda item: item[0])
    limit = int(cfg.get('same_candidates_deep' if deep else 'same_candidates',
                        SAME_CANDIDATE_LIMIT_DEEP if deep else SAME_CANDIDATE_LIMIT))
    for _score, family, params, primitives in specs[:limit]:
        yield dict(family=family, params=params, primitives=primitives)


def candidates(frame, oracle, cfg, deep=False):
    """Yield V3 candidates for one route (dispatch on the canonical frame kind)."""
    if frame.kind == 'same':
        yield from same_candidates(frame, oracle, cfg, deep=deep)
    else:
        yield from FSLW_CANDIDATES.candidates(frame, oracle, cfg, deep=deep)
