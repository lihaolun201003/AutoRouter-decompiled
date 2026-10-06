"""Figures for the v8 continuation: comparisons, trade-offs, timing, diagnostics.

Usage:
  python -B scripts/v8_figures.py PROJECT OUTDIR
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
CMP = OUT / "comparison"
FIG = OUT / "figures"
FIG.mkdir(parents=True, exist_ok=True)


def load(name):
    path = CMP / (name + ".json")
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def save(fig, name):
    for suffix in (".png", ".pdf"):
        fig.savefig(FIG / (name + suffix), dpi=160, bbox_inches="tight")
    plt.close(fig)
    print("figure", name, flush=True)


def fig_p2():
    data = load("p2_g0_vs_g1")
    if not data:
        return
    cells = [c for c in data["cells"] if c["g0"]["status"] == "PRESENT"
             and c["g1"]["status"] == "PRESENT"]
    if not cells:
        return
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for axis, challenge in zip(axes, (False, True)):
        for arm, key, colour in (("G0 line windows", "g0", "#1f77b4"),
                                 ("G1 path windows", "g1", "#d62728")):
            for mode in ("N", "R"):
                rows = sorted([c for c in cells if c["mode"] == mode
                               and bool(c.get("challenge")) == challenge],
                              key=lambda c: c["budget"])
                if not rows:
                    continue
                axis.plot([c["budget"] for c in rows], [c[key]["final_collision_pairs"] for c in rows],
                          marker="o", linestyle="-" if mode == "R" else "--",
                          color=colour, label=arm + " " + mode)
        axis.set_title("challenge start" if challenge else "main start")
        axis.set_xlabel("appended candidate budget")
        axis.set_ylabel("terminal near-distance pairs")
        axis.grid(alpha=.3)
        axis.set_xticks([720, 1440, 2880])
    axes[0].legend(fontsize=7)
    fig.suptitle("v8: same-budget whole-layout result, G0 vs G1")
    save(fig, "v8_p2_g0_vs_g1_pairs")


def fig_p4():
    data = load("p4_length_cap")
    if not data:
        return
    rows = [r for r in data["capped"] if r["status"] == "PRESENT"]
    refs = [r for r in data["uncapped_references"] if r["status"] == "PRESENT"]
    if not rows:
        return
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    markers = {"BASE_E2": "o", "A_FAMILY": "s"}
    colours = {"N": "#1f77b4", "R": "#d62728"}
    for axis, challenge in zip(axes, (False, True)):
        for family in ("BASE_E2", "A_FAMILY"):
            for mode in ("N", "R"):
                subset = sorted([r for r in rows if r["arm"] == family and r["mode"] == mode
                                 and bool(r["challenge"]) == challenge],
                                key=lambda r: r["cap_mm"])
                if subset:
                    axis.plot([r["cap_mm"] for r in subset],
                              [r["final_collision_pairs"] for r in subset],
                              marker=markers[family], color=colours[mode],
                              label="%s %s capped" % (family, mode))
                reference = next((r for r in refs if r["arm"] == family and r["mode"] == mode
                                  and bool(r["challenge"]) == challenge), None)
                if reference:
                    axis.axhline(reference["final_collision_pairs"], color=colours[mode],
                                 linestyle=":", linewidth=1)
        axis.set_title("challenge start" if challenge else "main start")
        axis.set_xlabel("stage length cap (mm)")
        axis.set_ylabel("terminal near-distance pairs")
        axis.grid(alpha=.3)
    axes[0].legend(fontsize=5.5, loc="upper right", ncol=2)
    fig.suptitle("v8 P4: capped runs (solid) vs the uncapped reference of the SAME policy (dotted)",
                 fontsize=10)
    save(fig, "v8_p4_length_cap")


def fig_p4_tradeoff():
    data = load("p4_length_cap")
    if not data:
        return
    rows = [r for r in data["capped"] + data["uncapped_references"] if r["status"] == "PRESENT"]
    if not rows:
        return
    fig, axis = plt.subplots(figsize=(7.2, 5.2))
    for family, marker in (("BASE_E2", "o"), ("A_FAMILY", "s")):
        for mode, colour in (("N", "#1f77b4"), ("R", "#d62728")):
            subset = [r for r in rows if r["arm"] == family and r["mode"] == mode]
            if not subset:
                continue
            # marker area encodes the transition structure count, but it is
            # clamped: the raw count reaches ~200 and would swallow the panel
            sizes = [30 + min(150, 1.2 * (r.get("final_transition_count") or 0)) for r in subset]
            axis.scatter([r["stage_length_delta_mm"] for r in subset],
                         [r["final_collision_pairs"] for r in subset], s=sizes,
                         marker=marker, color=colour, alpha=.75,
                         label="%s %s" % (family, mode))
    axis.set_xlabel("stage length change (mm)")
    axis.set_ylabel("terminal near-distance pairs")
    axis.grid(alpha=.3)
    axis.legend(fontsize=7, loc="upper right", framealpha=.9)
    axis.set_title("P4 trade-off: near pairs vs stage length\n"
                   "(marker area grows with the transition structure count, clamped)")
    save(fig, "v8_p4_tradeoff")


def fig_p3():
    data = load("p3_family_and_target_limit")
    if not data:
        return
    rows = [r for r in data["rows"] if r["status"] == "PRESENT"
            and r["mode"] == "R" and not r.get("challenge")]
    if not rows:
        return
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for axis, limit in zip(axes, (200, 2000)):
        for family, colour in (("BASE_E2", "#1f77b4"), ("A_FAMILY", "#d62728")):
            subset = sorted([r for r in rows if r["arm"] == family
                             and (r.get("max_targets") or 200) == limit],
                            key=lambda r: r["budget"])
            if subset:
                axis.plot([r["budget"] for r in subset],
                          [r["final_collision_pairs"] for r in subset], marker="o",
                          color=colour, label=family)
        axis.set_title("max_targets = %d" % limit)
        axis.set_xlabel("appended candidate budget")
        axis.set_ylabel("terminal near-distance pairs (R)")
        axis.set_xticks([720, 1440, 2880])
        axis.grid(alpha=.3)
    axes[0].legend(fontsize=8)
    fig.suptitle("P3: family diversity vs target-attempt limit (R mode)")
    save(fig, "v8_p3_family_limit")


def fig_p5():
    data = load("p5_serial_timing")
    if not data:
        return
    rows = [r for r in data["rows"] if r["status"] == "PRESENT"]
    if not rows:
        return
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for axis, key, title in ((axes[0], "runtime_seconds", "engine kernel seconds"),
                             (axes[1], "run_seconds_including_recheck",
                              "process seconds incl. IO and recheck")):
        for index, arm in enumerate(("OFF", "ON")):
            values = [r[key] for r in rows if r["arm"] == arm and r[key] is not None]
            if not values:
                continue
            axis.scatter([index] * len(values), values, color="#1f77b4" if arm == "OFF"
                         else "#d62728")
            axis.hlines(sorted(values)[len(values) // 2], index - .2, index + .2, color="black")
        axis.set_xticks([0, 1]); axis.set_xticklabels(["cache OFF", "cache ON"])
        axis.set_title(title)
        axis.grid(alpha=.3)
    save(fig, "v8_p5_serial_timing")


def fig_diagnostics():
    path = OUT / "diagnostics" / "v8_side_diagnostics_summary.json"
    if not path.is_file():
        return
    summary = json.loads(path.read_text(encoding="utf-8"))
    labels = ["v4 frozen set", "G0 line windows", "G1 path windows"]
    keys = ["v4_outcome_counts", "g0_outcome_counts", "g1_outcome_counts"]
    outcomes = sorted({o for key in keys for o in summary[key]})
    fig, axis = plt.subplots(figsize=(9.5, 4.6))
    bottom = [0] * len(labels)
    for outcome in outcomes:
        values = [summary[key].get(outcome, 0) for key in keys]
        axis.bar(labels, values, bottom=bottom, label=outcome)
        bottom = [a + b for a, b in zip(bottom, values)]
    axis.set_ylabel("sides (of 120)")
    axis.set_title("frozen 60-pair / 120-side diagnostic: outcome per generation domain")
    axis.legend(fontsize=6, ncol=2)
    save(fig, "v8_diagnostics_side_outcomes")


def main():
    fig_p2(); fig_p3(); fig_p4(); fig_p4_tradeoff(); fig_p5(); fig_diagnostics()


if __name__ == "__main__":
    main()
