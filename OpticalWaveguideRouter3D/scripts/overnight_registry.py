"""Frozen pre-registration of every formal overnight configuration.

Nothing here is chosen after seeing a result: the four rounds and the eight
mechanisms were fixed in docs/plans/*.md and this file only turns them into
executable group definitions. Each round group list is written to
outputs/overnight_3d_ideas/manifest/round_<name>.json together with a SHA256
before that round first formal run; the runner refuses a group that is not in
the frozen manifest.

Baselines are NOT re-run when a verified identical run already exists:
 - v5 LEGACY scheduling, N/R, 720/1440/2880 == the six reviewed step-17 v4
   groups. That reuse is accepted only after scripts/run_overnight_3d.py
   reproduces a v4 group from the same start state with the same spec
   (see outputs/overnight_3d_ideas/equiv/).
 - each later round control is the previously ACCEPTED configuration, chosen by
   the pre-declared rule in the roadmap, stored in adoption.json.
"""
MAIN_START = "outputs/3d_strategy_v3/512_ablation/D_both_enabled"
CHALLENGE_START = "outputs/3d_strategy_v4/512_full_layout/N2880"
MAIN_BUDGETS = (720, 1440, 2880)
CHALLENGE_BUDGET = 2880
MODES = ("N", "R")
SIZE = 512
CLEARANCE_MM = 0.1
REQUIRED_RADIUS_MM = 5.0
WINDOW_SLACK_MM = 1e-5

ADOPTION_RULE = ("correctness and recheck PASS first; then the fixed MAIN R2880 terminal "
                  "near-distance pair count (fewer adopts); tie -> smaller stage length "
                  "delta; tie -> fewer actual evaluations; tie -> keep the old config")

IDEA_TITLES = {
    "A": "candidate family diversity round-robin vs unified-score top-K",
    "B": "reserved relocation evaluation slots vs joint top-K",
    "C": "target waiting age vs original degree ordering",
    "D": "route coverage scheduling inside the state layers vs existing traversal",
    "E": "multi-target witness anchor vs single-target anchor",
    "F": "exact geometry dedup vs original candidate sequence",
    "G": "candidate-neighbour decision cache (identical results required)",
    "H": "RETURN to frozen plane as an extra action vs plain R",
}
IDEA_ORDER = ("A", "B", "F", "C", "D", "E", "G", "H")


def _spec(name, **kwargs):
    from src.overnight_engine_3d import StrategySpec
    return StrategySpec(name, **kwargs)


def v5_specs():
    """v5: two target schedulers, everything else frozen at the v4 values."""
    return {
        "LEGACY": _spec("V5_LEGACY", target_policy="LEGACY", max_targets=200,
                        window_slack_mm=WINDOW_SLACK_MM),
        "STRATIFIED": _spec("V5_STRATIFIED", target_policy="STRATIFIED", max_targets=200,
                            window_slack_mm=WINDOW_SLACK_MM),
    }


def v6_specs(target_policy):
    """v6: three candidate evaluation policies on the adopted target scheduler."""
    return {
        "E0_EXHAUSTIVE": _spec("V6_E0", target_policy=target_policy,
                               evaluation_policy="E0_EXHAUSTIVE", max_targets=200,
                               window_slack_mm=WINDOW_SLACK_MM),
        "E1_ORDERED_EXHAUSTIVE": _spec("V6_E1", target_policy=target_policy,
                                       evaluation_policy="E1_ORDERED_EXHAUSTIVE", max_targets=200,
                                       window_slack_mm=WINDOW_SLACK_MM),
        "E2_ORDERED_K16": _spec("V6_E2", target_policy=target_policy,
                                evaluation_policy="E2_ORDERED_K16", k_per_target=16,
                                max_targets=200, window_slack_mm=WINDOW_SLACK_MM),
    }


def v7_specs(target_policy, eval_policy, k_per_target):
    """v7: target-attempt limit and coverage traversal, with generation, cheap
    ordering, per-target quota, winner ranking and acceptance all unchanged."""
    common = dict(target_policy=target_policy, evaluation_policy=eval_policy,
                  k_per_target=k_per_target, window_slack_mm=WINDOW_SLACK_MM)
    return {
        "T0_BASE_200": _spec("V7_T0", max_targets=200, **common),
        "T1_BASE_2000": _spec("V7_T1", max_targets=2000, **common),
        "T2_COVERAGE_2000": _spec("V7_T2", max_targets=2000, traversal_policy="COVERAGE",
                                  route_coverage=True, cache_structural_skips=True, **common),
    }


def idea_spec(target_policy, eval_policy, k_per_target):
    """The frozen single-factor ablation set for the eight extra mechanisms.

    Every entry changes exactly ONE declared factor relative to the control
    that is named in its own "control" field: the previously accepted
    configuration for C, D, E, F, G, H, and the v6 E2 configuration for A and B
    (whose hypotheses are about how the fixed K quota is spent)."""
    base = dict(target_policy=target_policy, evaluation_policy=eval_policy,
                k_per_target=k_per_target, max_targets=200, window_slack_mm=WINDOW_SLACK_MM)
    k2 = 16
    e2 = dict(target_policy=target_policy, evaluation_policy="E2_ORDERED_K16",
              k_per_target=k2, max_targets=200, window_slack_mm=WINDOW_SLACK_MM)
    specs = {"BASE": (_spec("IDEA_BASE", **base), "BASE")}
    specs["A"] = (_spec("IDEA_A_FAMILY", family_round_robin=True, **e2), "E2")
    specs["B"] = (_spec("IDEA_B", relocation_side_reserve=k2 // 2, **e2), "E2")
    specs["C"] = (_spec("IDEA_C", waiting_age=True, **base), "BASE")
    # Route coverage is applied INSIDE the UU/UE/EE state layers, so it needs the
    # state-layered scheduler. If that scheduler was not the adopted baseline, D
    # is compared with the v5 STRATIFIED control instead of mixing two factors.
    d_target = "STRATIFIED"
    d_base = dict(base, target_policy=d_target)
    specs["D"] = (_spec("IDEA_D", route_coverage=True, traversal_policy="COVERAGE",
                        cache_structural_skips=True, **d_base),
                  "BASE" if target_policy == "STRATIFIED" else "v5_stratified")
    specs["E"] = (_spec("IDEA_E", multi_anchor=True, **base), "BASE")
    specs["F"] = (_spec("IDEA_F", exact_dedup=True, **base), "BASE")
    specs["G"] = (_spec("IDEA_G", decision_cache=True, **base), "BASE")
    specs["H"] = (_spec("IDEA_H", return_action=True, **base), "BASE")
    return specs


def round_groups(round_name, adoption=None, with_challenge=None):
    """Return [(group_name, spec, mode, budget, start_kind, control)].

    with_challenge defaults to True for v5/v6/v7 (their prompts require a fixed
    challenge set from the v4 N2880 terminal state) and to False for the extra
    single-factor mechanisms, whose declared matrix in the overnight prompt is
    baseline/single-factor x N/R x the three main budgets."""
    adoption = adoption or {}
    target_policy = adoption.get("target_policy", "LEGACY")
    eval_policy = adoption.get("evaluation_policy", "E0_EXHAUSTIVE")
    k_per_target = adoption.get("k_per_target", 16)
    if round_name == "dctrl":
        # Supplementary single-factor control for idea D. Idea D applies the route
        # coverage traversal INSIDE the UU/UE/EE state layers, so its control must
        # be the state-layered scheduler with the accepted evaluation policy and
        # NO coverage rule; otherwise two factors change at once.
        raw = [(_spec("IDEA_D_CONTROL", target_policy="STRATIFIED", evaluation_policy=eval_policy,
                      k_per_target=k_per_target, max_targets=200, window_slack_mm=WINDOW_SLACK_MM),
                "LEGACY_E2_BASE")]
    elif round_name == "v5":
        raw = [(spec, "BASE") for spec in v5_specs().values()]
    elif round_name == "v6":
        raw = [(spec, "v5") for spec in v6_specs(target_policy).values()]
    elif round_name == "v7":
        raw = [(spec, "v6") for spec in v7_specs(target_policy, eval_policy, k_per_target).values()]
    elif round_name == "ideas":
        raw = list(idea_spec(target_policy, eval_policy, k_per_target).values())
    elif round_name == "pe":
        return pe_round_groups()
    elif round_name in ("v8", "v8_neutrality", "p3", "p4", "p5"):
        # v8-continuation rounds: the adapter below carries its own frozen
        # matrix (including the challenge cells), so nothing is derived here.
        return v8_round_groups(round_name)
    else:
        raise SystemExit("unknown round " + round_name)
    if with_challenge is None:
        with_challenge = round_name in ("v5", "v6", "v7", "dctrl")
    groups = []
    for spec, control in raw:
        for mode in MODES:
            for budget in MAIN_BUDGETS:
                groups.append((spec.name + "_" + mode + str(budget), spec, mode, budget,
                               "main", control))
            if with_challenge:
                groups.append((spec.name + "_" + mode + "C" + str(CHALLENGE_BUDGET), spec, mode,
                               CHALLENGE_BUDGET, "challenge", control))
    return groups


def group_index(round_name, adoption=None, with_challenge=None):
    return {row[0]: dict(name=row[0], spec=row[1], mode=row[2], budget=row[3], start=row[4],
                         control=row[5])
            for row in round_groups(round_name, adoption, with_challenge)}


# ---------------------------------------------------------------------------
# v8 continuation (this session): the SAME adopted policy, one declared factor
# ---------------------------------------------------------------------------
# Adopted by v5/v6/v7: LEGACY target scheduling, E2_ORDERED_K16 evaluation, the
# retained 200 target-attempt limit, k=16 and the 1e-5 mm window slack. Every v8
# arm below changes exactly ONE declared factor on top of that base.
ADOPTED_TARGET_POLICY = "LEGACY"
ADOPTED_EVALUATION_POLICY = "E2_ORDERED_K16"
ADOPTED_K_PER_TARGET = 16
ADOPTED_MAX_TARGETS = 200
V8_MAX_TARGETS = 2000
V8_CAPS_MM = (24.0, 40.0, 60.0)

# Frozen path-window enumeration (declared BEFORE the first formal v8 run).
PATH_WINDOW_SETTINGS = dict(placements=(0.0, 0.5, 1.0),
                            length_factors=(1.0, 1.5, 2.0, 3.0),
                            cap=4096)
GENERATION_DOMAIN_LINE = "LINE_ONLY"
GENERATION_DOMAIN_PATH = "PATH_WINDOWS"
PATH_WINDOW_NOTE = ("G1 = every G0 candidate PLUS the frozen path-arc-length windows; "
                    "dedup is by planar arc-length interval, so no window is lost and no "
                    "duplicate is created")


def adopted(**kwargs):
    """The adopted v5/v6/v7 policy, with the declared v8 factor(s) on top."""
    base_kwargs = dict(target_policy=ADOPTED_TARGET_POLICY,
                       evaluation_policy=ADOPTED_EVALUATION_POLICY,
                       k_per_target=ADOPTED_K_PER_TARGET, max_targets=ADOPTED_MAX_TARGETS,
                       window_slack_mm=WINDOW_SLACK_MM)
    base_kwargs.update(kwargs)
    return base_kwargs


def v8_specs():
    """P2: G0 (the historical line-only generation domain) and G1 (path windows).

    G0 is the CONTROL and must reproduce the already verified v7 T0/V6 E2 groups
    bit for bit; G1 changes only generation_domain plus its frozen settings."""
    return {
        "G0_LINE_ONLY": _spec("V8_G0", generation_domain=GENERATION_DOMAIN_LINE, **adopted()),
        "G1_PATH_WINDOWS": _spec("V8_G1", generation_domain=GENERATION_DOMAIN_PATH,
                                 path_window_settings=PATH_WINDOW_SETTINGS, **adopted()),
    }


def v8_neutrality_specs():
    """G0 re-run under the frozen v8 code: proves the new code path is neutral."""
    return {"G0_NEUTRALITY": _spec("V8_G0_NEUTRALITY", generation_domain=GENERATION_DOMAIN_LINE,
                                   **adopted())}


def p3_specs():
    """P3: candidate-FAMILY diversity x target-attempt limit, nothing else.

    BASE_E2 is the adopted E2 policy; A_FAMILY adds only the family round-robin.
    max_targets 200/2000 is the single-factor limit axis."""
    return {
        "BASE_E2_T200": _spec("P3_BASE_E2_T200", **adopted(max_targets=200)),
        "BASE_E2_T2000": _spec("P3_BASE_E2_T2000", **adopted(max_targets=2000)),
        "A_FAMILY_T200": _spec("P3_A_FAMILY_T200", family_round_robin=True,
                               **adopted(max_targets=200)),
        "A_FAMILY_T2000": _spec("P3_A_FAMILY_T2000", family_round_robin=True,
                                **adopted(max_targets=2000)),
    }


def p4_specs():
    """P4: the SAME E2 / A policies with a stage length cap, max_targets 2000.

    The cap is a signed constraint on the whole-layout stage length
    (current total length <= start total length + cap); a relocation that
    shortens the layout therefore earns headroom."""
    specs = {}
    for cap in V8_CAPS_MM:
        tag = str(int(cap))
        specs["BASE_E2_CAP" + tag] = _spec("P4_BASE_E2_CAP" + tag,
                                           **adopted(max_targets=2000, stage_length_cap_mm=cap))
        specs["A_FAMILY_CAP" + tag] = _spec("P4_A_FAMILY_CAP" + tag, family_round_robin=True,
                                            **adopted(max_targets=2000, stage_length_cap_mm=cap))
    return specs


def p5_specs():
    """P5: the controlled serial timing pair (cache OFF / cache ON)."""
    return {
        "CACHE_OFF": _spec("P5_CACHE_OFF", decision_cache=False, **adopted()),
        "CACHE_ON": _spec("P5_CACHE_ON", decision_cache=True, **adopted()),
    }



def pe_specs():
    """EXTRA queue 1: idea E (multi-anchor witness) x target-attempt limit.

    E is kept exactly as it was defined and verified in the ideas round
    (multi_anchor=True on the adopted BASE policy, evaluation E2_ORDERED_K16);
    the ONLY thing that changes here is max_targets 200 vs 2000, so the
    question 'was E's early stop at 668 evaluations caused by the target limit
    or by the mechanism itself' has a single-factor answer."""
    return {
        "E_T200": _spec("PE_E_T200", multi_anchor=True, **adopted(max_targets=200)),
        "E_T2000": _spec("PE_E_T2000", multi_anchor=True, **adopted(max_targets=2000)),
    }


def pe_round_groups():
    raw = [(spec, "IDEAS_ROUND_E_ARM") for spec in pe_specs().values()]
    groups = []
    for spec, control in raw:
        for mode in MODES:
            for budget in MAIN_BUDGETS:
                groups.append((spec.name + "_" + mode + str(budget), spec, mode, budget,
                               "main", control))
            groups.append((spec.name + "_" + mode + "C" + str(CHALLENGE_BUDGET), spec, mode,
                           CHALLENGE_BUDGET, "challenge", control))
    return groups


def v8_round_groups(round_name):
    """Group list of one v8-continuation round: spec x mode x budget (+challenge).

    P4 is fixed at the 2880 budget by its own prompt (12 main + 12 challenge
    cells only), so it does not inherit the 720/1440 main budgets."""
    budgets = None
    p5_only_r1440 = False
    if round_name == "v8":
        raw = [(spec, "ADOPTED_V7_T0_V6_E2") for spec in v8_specs().values()]
        with_challenge = True
    elif round_name == "v8_neutrality":
        # The neutrality re-run must cover BOTH fixed start states: the main
        # start (v3 D_both_enabled) and the challenge start (v4 N2880).
        raw = [(spec, "ADOPTED_V7_T0_V6_E2") for spec in v8_neutrality_specs().values()]
        with_challenge = True
    elif round_name == "p3":
        raw = [(spec, "P3_FAMILY_AND_LIMIT_MATRIX") for spec in p3_specs().values()]
        with_challenge = True
    elif round_name == "p4":
        raw = [(spec, "P4_LENGTH_CAP_MATRIX") for spec in p4_specs().values()]
        with_challenge = True
        budgets = (2880,)
    elif round_name == "p5":
        # The controlled serial timing comparison is declared at the MAIN start
        # and R1440 only; every other cell would be an unrun pre-registration.
        raw = [(spec, "P5_SERIAL_TIMING_PAIR") for spec in p5_specs().values()]
        with_challenge = False
        p5_only_r1440 = True
    else:
        raise SystemExit("unknown v8 round " + round_name)
    budgets = budgets if round_name == "p4" else MAIN_BUDGETS
    groups = []
    for spec, control in raw:
        for mode in MODES:
            for budget in budgets:
                groups.append((spec.name + "_" + mode + str(budget), spec, mode, budget,
                               "main", control))
            if with_challenge:
                groups.append((spec.name + "_" + mode + "C" + str(CHALLENGE_BUDGET), spec, mode,
                               CHALLENGE_BUDGET, "challenge", control))
    if round_name == "p5":
        # The controlled serial timing comparison is declared at the MAIN start
        # and R1440 only (both cache settings, three tag-suffixed repeats each);
        # any other cell would be an unrun pre-registration in a frozen manifest.
        return [row for row in groups if row[2] == "R" and row[3] == 1440]
    return groups
