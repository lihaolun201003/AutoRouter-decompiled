"""Tunable knobs of the V2 candidate-expansion / rip-up-reroute round.

Only *search* knobs live here.  The physical process parameters (board, width,
edge gap, clearance, radius, sagitta, crossing policy) are imported from the
frozen :mod:`four_side_1024.fslw.config` and never redefined in this package.
"""
from __future__ import annotations

#: Deterministic base seed of every experiment (the CLI can override it).
SEED = 20261019

# ---------------------------------------------------------------------------
# candidate pools / queue sizes (search only)
# ---------------------------------------------------------------------------
#: maximum number of clearance-track coordinates kept per axis for the move
#: family pools (the pools are derived from currently placed geometry).
POOL_LIMIT = 600
#: coordinates per axis used for the 2-parameter Z3/LEFT families.
Z3_POOL = 72
#: coordinates per axis used for the 4-parameter Z5 family.
Z5_POOL = 10
#: coordinates per axis used for the 5-parameter DOWN_LOOP family.
LOOP_POOL = 7
#: hard cap on the number of DOWN_LOOP specs per route.
LOOP_MAX_SPECS = 4000
#: hard cap on the number of specs produced per route (before scoring).
MAX_SPECS = 40000

#: opposite-side (z1) family sizes: dense tracks, many Z candidates
OPPOSITE_SHALLOW = 64
OPPOSITE_DEEP = 1200
OPPOSITE_Z_CANDIDATES = 1200
OPPOSITE_Z_TRACK_SAMPLES = 40

# ---------------------------------------------------------------------------
# ranking weights (ranking only - never affects legality)
# ---------------------------------------------------------------------------
SCORE_PARALLEL = 1.0
SCORE_CROSS = 0.35

#: remove exact duplicate primitive chains from the candidate queue
DEDUPE = True

#: number of candidates drawn from a per-family bucket before re-interleaving
FAMILY_BATCH = 200

# ---------------------------------------------------------------------------
# attempt budgets (candidate evaluations per route, as in the experiment table)
# ---------------------------------------------------------------------------
#: budget ladder of the candidate-search experiment (task 5.1)
BUDGET_LADDER = (200, 400, 800, 1600)
