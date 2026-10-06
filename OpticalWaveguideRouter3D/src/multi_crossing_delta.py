"""Read-only set/severity helpers for fixed-criterion multi-crossing audits."""
from math import degrees
from .loss_analysis import statistics

def canonical_triplet(ids):
    key=tuple(sorted(ids))
    if len(key)!=3 or len(set(key))!=3:raise ValueError("Three distinct IDs required.")
    return key

def triplet_set_diff(control,variant):
    a={canonical_triplet(x) for x in control};b={canonical_triplet(x) for x in variant}
    return dict(stable=sorted(a&b),removed=sorted(a-b),added=sorted(b-a))

def severity(record,spacing=.125):
    sides=sorted(record["side_lengths_mm"])
    return dict(s1=sides[0],s2=sides[1],s3=sides[2],
                second_shortest_margin_mm=spacing-sides[1],short_side_count=record["short_side_count"])

def margin_delta(control,variant,tol=1e-9):
    delta=severity(variant)["second_shortest_margin_mm"]-severity(control)["second_shortest_margin_mm"]
    return dict(delta=delta,change="worsened" if delta>tol else "improved" if delta<-tol else "unchanged")

def check_top_u_invariant(difference,top):
    bad=[t for group in ("added","removed") for t in difference[group] if not set(t)&top]
    if bad:raise ValueError(f"Changed non-top-U triplets: {bad}")
    return True

def summarize_records(records):
    values=[severity(r) for r in records]
    angles=[r["crossing_angles_deg"] for r in records]
    return dict(severity={key:statistics([v[key] for v in values]) for key in ("s1","s2","s3","second_shortest_margin_mm")},
                minimum_angle_per_triplet=statistics([min(a) for a in angles]),
                mean_angle_per_triplet=statistics([sum(a)/3 for a in angles]),
                contains_angle_below_20=sum(min(a)<20 for a in angles))
