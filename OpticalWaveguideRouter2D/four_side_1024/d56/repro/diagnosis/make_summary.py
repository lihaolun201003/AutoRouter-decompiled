"""Assemble the machine-readable 8-question diagnosis summary.

Reads every probe output under scratch/diagnosis/data and writes
scratch/diagnosis/summary.json.  Run after the probes:
  .venv/Scripts/python.exe scratch/diagnosis/make_summary.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import d56_diag_common as C

DATA = C.DATA


def load(name, default=None):
    path = DATA / name
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    analysis = load('analysis.json', {})
    direct = load('direct_l_matrix.json', {})
    transforms = load('transforms.json', {})
    template = load('adjacent_template_coverage.json', {})
    rescue = load('adjacent_rescue.json', {})
    capacity = load('capacity.json', {})
    policy = load('policy_search/policyC_full_unlimited.json', {})
    replay = load('replay/full_unlimited.json', {})
    opposite_only = load('replay/order_opposite_only.json', {})
    adjacent_only = load('replay/order_adjacent_only.json', {})
    sc = json.loads((C.BASELINE / 'search_checkpoint.json').read_text(encoding='utf-8'))
    stats = json.loads((C.BASELINE / 'statistics.json').read_text(encoding='utf-8'))

    baseline = analysis.get('baseline', {})
    q1 = analysis.get('q1_order_replay', {})
    q24 = analysis.get('q2_q4_rule_rejection_samples', {})
    q5 = analysis.get('q5_exact_evaluations_baseline_667', {})
    q8_dist = analysis.get('q8_spacing_distances_baseline_667', {})
    q8_sample = analysis.get('q8_spacing_sample_rescue', {})
    cross_group = analysis.get('q7_cross_group_blocking', {})
    full_unlimited = q1.get('full_unlimited', {})
    base_cmp = full_unlimited.get('baseline_comparison') or replay.get('baseline_comparison') or {}

    rescue_scenarios = rescue.get('scenarios', {})
    rescue_best = max(rescue_scenarios.values(), key=lambda x: x['sequential_total']) \
        if rescue_scenarios else {}

    summary = {
        'schema': 'd56_1024_failure_diagnosis_summary_v1',
        'report': 'docs/reports/d56_1024_failure_diagnosis.md',
        'baseline': dict(success=stats['success_count'], failed=stats['failed_count'],
                         attempted=stats['actual_routing_attempted_count'],
                         not_attempted=stats['not_attempted_due_global_budget'],
                         scanned=stats['search']['scanned_tracks'],
                         evaluations=stats['search']['candidate_evaluations'],
                         runtime_seconds=stats['search']['search_runtime_seconds'],
                         by_pair={pair: v['success'] for pair, v in stats['by_pair'].items()}),
        'replay_validation': dict(total_attempted=full_unlimited.get('attempted'),
                                  accepted=full_unlimited.get('accepted'),
                                  compared_routes=base_cmp.get('compared'),
                                  mismatched_routes=len(base_cmp.get('mismatched', [])),
                                  accepted_geometry_mismatch=len(base_cmp.get('accepted_mismatch', [])),
                                  note='586 comparable failed routes reproduce scanned/evaluated/rejection counts/blockers exactly; '
                                       'the 11 mismatches are baseline-not-attempted routes that the budget-free replay accepted'),
        'control_experiments': {
            'deployed_baseline_600s': 80,
            'deployed_unlimited': full_unlimited.get('accepted'),
            'deployed_unlimited_by_pair': full_unlimited.get('by_pair'),
            'corrected_crossing_policy_unlimited': policy.get('summary', {}).get('accepted'),
            'corrected_crossing_policy_by_pair': policy.get('summary', {}).get('by_pair'),
            'adjacent_only_unlimited': adjacent_only.get('summary', {}).get('accepted'),
            'opposite_only_unlimited': opposite_only.get('summary', {}).get('accepted'),
            'opposite_only_by_pair': opposite_only.get('summary', {}).get('by_pair'),
            'independent_sum_adjacent_plus_opposite': 238,
            'interference_loss': 238 - (full_unlimited.get('accepted') or 0),
        },
        'q1_order_replay': dict(
            conclusion='placing adjacent routes first costs the opposite relation 147 routes '
                       '(opposite-alone 182 -> 35 in the joint baseline order)',
            per_pair_table=analysis.get('q1_by_pair_table'),
            blocker_concentration=full_unlimited.get('blocker_concentration'),
            first_blocker_table=full_unlimited.get('first_blocker_table'),
            nearest_blocked_distance_note='q1_route_rows.csv columns nearest_blocked_distance are the '
                                          'closest spacing-rejected candidate distance for that route'),
        'q2_nocross': dict(
            total_rejections=q24.get('total_nocross_rejections'),
            sampled=q24.get('nocross_reject', {}).get('sampled'),
            geometry_constructible_fraction=q24.get('nocross_reject', {}).get('bend_fit_fraction'),
            exact_legal_fraction=q24.get('nocross_reject', {}).get('exact_legal_fraction'),
            estimated_wrong_rejections=q24.get('estimated_wrong_nocross_rejections'),
            conclusion='noCross is analytically conservative but rejects essentially no geometrically legal '
                       'candidate in this dense CSV (0.012% sampled)'),
        'q3_transforms': dict(
            max_position_error=transforms.get('global_invariants', {}).get('max_world_roundtrip_position_error'),
            max_direction_error=transforms.get('global_invariants', {}).get('max_source_inward_mapping_error'),
            determinants=transforms.get('global_invariants', {}).get('determinants'),
            pairs=[{k: p[k] for k in ('source_side', 'target_side', 'kind', 'route_count',
                                      'max_position_error', 'max_direction_error')}
                   for p in transforms.get('pairs', [])],
            conclusion='all six directed side pairs transform exactly (round-trip error < 2e-14 mm, direction error 0)'),
        'q4_legacy_order': dict(
            total_rejections=q24.get('total_order_rejections'),
            sampled=q24.get('order_reject', {}).get('sampled'),
            exact_legal_fraction=q24.get('order_reject', {}).get('exact_legal_fraction'),
            estimated_wrong_rejections=q24.get('estimated_wrong_order_rejections'),
            conclusion='legacy_order_ok triggers on 0.96% of scans and wrongly rejects ~0.3% of its triggers'),
        'q5_redundancy': dict(
            baseline=analysis.get('q5_deployed_statistics'),
            budget_free=analysis.get('q5_exact_evaluations'),
            baseline_667=q5,
            conclusion='98.1% of exact evaluations repeat the same first blocker at the previous track '
                       '(mean 672.7 per route); only ~1.9% test a new obstruction'),
        'q6_adjacent_templates': dict(
            fixed_template_coverage=template.get('summary'),
            direct_L_valid=direct.get('direct_L_geometrically_valid'),
            flexible_template_geometric_coverage=512,
            rescue_best=dict(kept_direct_L=rescue_best.get('kept_direct_L'),
                             reroute_candidates=rescue_best.get('reroute_candidates'),
                             independent_rescued=rescue_best.get('independent_rescued'),
                             sequential_rescued=rescue_best.get('sequential_rescued'),
                             sequential_total=rescue_best.get('sequential_total'),
                             independent_upper_bound=299 + (rescue_best.get('independent_rescued') or 0),
                             needs_more_than_3_bends=(rescue_best.get('reroute_candidates') or 0)
                                                    - (rescue_best.get('independent_rescued') or 0)),
            conclusion='fixed t2=145 template leaves 32 routes with zero geometric alternative and 19% '
                       'track-coverage gap; variable terminal turn recovers all geometric coverage and '
                       'rescues 135-163/209 excluded routes independently (338-354 sequential)'),
        'q7_track_state': dict(
            accepted_routes=80, distinct_track_y=80, shared_tracks=0,
            cross_group_first_blocker=cross_group,
            conclusion='WGyset is not an exclusive global resource (code appends; all accepted routes on distinct '
                       'tracks by geometry). The real gap is that noCross state is per-pair-group while conflicts '
                       'are global (NW: 100% of first blockers are cross-group).'),
        'q8_crossing_zone': dict(
            spacing_rejections=q8_dist.get('n'),
            distance_distribution=q8_dist.get('deficit_bins'),
            share_deficit_le_5um=q8_dist.get('share_deficit_le_5um'),
            share_deficit_le_1um=q8_dist.get('share_deficit_le_1um'),
            mean_deficit_mm=q8_dist.get('mean_deficit'),
            sampled_spacing_rejections=q8_sample.get('sample_size'),
            sampled_corrected_legal=q8_sample.get('corrected_legal'),
            sampled_corrected_legal_fraction=q8_sample.get('corrected_legal_fraction'),
            sampled_outcomes=q8_sample.get('outcomes'),
            exact_vs_deployed_confusion=direct.get('policy_confusion'),
            direct_L_deployed_illegal_pairs=direct.get('policies', {}).get('deployed', {}).get('illegal_pairs'),
            direct_L_corrected_illegal_pairs=direct.get('policies', {}).get('primitive_pair', {}).get('illegal_pairs'),
            direct_L_genuine_conflicts=direct.get('genuine_conflicts_improved', {}).get('by_pair_label_combo'),
            route_level_rescue=dict(deployed_unlimited=full_unlimited.get('accepted'),
                                    corrected=policy.get('summary', {}).get('accepted'),
                                    gain=(policy.get('summary', {}).get('accepted') or 0)
                                         - (full_unlimited.get('accepted') or 0)),
            conclusion='the clearance/sin(angle) exemption window is exact for straight crossings but too short '
                       'for arc crossings (0.8-15 um deficits); 95.3% of sampled spacing rejections become legal '
                       'against their first blocker under an exact window; fixing only this takes 91 -> 417.'),
        'capacity': dict(
            boundary=capacity.get('e1_boundary_port_lanes'),
            band=capacity.get('e2_mandatory_boundary_bands'),
            lane_demand=capacity.get('e3_opposite_lane_demand'),
            accepted_occupancy=capacity.get('e4_accepted_lane_blockage'),
            corners=capacity.get('e5_corner_band_occupancy'),
            conclusion='global lane-length demand is only 40.75% of supply; boundary bands are 100% occupied '
                       'at zero clearance margin (port pitch = clearance = 0.175 mm); capacity is not the wall'),
        'budget': analysis.get('budget'),
        'rescue_summary': {
            'deployed_600s': 80,
            'deployed_unlimited': full_unlimited.get('accepted'),
            'corrected_crossing_only': policy.get('summary', {}).get('accepted'),
            'corrected_plus_adjacent_template_upper_bound': None,
            'remaining_gap_needs': ['richer >=5-bend templates', 'global ordering / rip-up', 'exact crossing policy everywhere'],
        },
        'reproduction_commands': [
            "Set-Location 'C:\\Users\\lihao\\Desktop\\Graduation Project\\OpticalWaveguideRouter2D'",
            "& '.venv\\Scripts\\python.exe' scratch/diagnosis/probe_replay.py --label full_unlimited --validate-baseline --out-dir scratch/diagnosis/data/replay",
            "& '.venv\\Scripts\\python.exe' scratch/diagnosis/probe_transforms.py",
            "& '.venv\\Scripts\\python.exe' scratch/diagnosis/probe_direct_l.py",
            "& '.venv\\Scripts\\python.exe' scratch/diagnosis/probe_policy_search.py --policy primitive_pair --label policyC_full_unlimited --out-dir scratch/diagnosis/data/policy_search",
            "& '.venv\\Scripts\\python.exe' scratch/diagnosis/probe_adjacent_rescue.py",
            "& '.venv\\Scripts\\python.exe' scratch/diagnosis/probe_capacity.py",
            "& '.venv\\Scripts\\python.exe' scratch/diagnosis/analyze_replay.py",
            "& '.venv\\Scripts\\python.exe' scratch/diagnosis/make_summary.py",
        ],
    }
    # derived combined upper bound for adjacent relation
    if rescue_best:
        summary['rescue_summary']['corrected_plus_adjacent_template_upper_bound'] = \
            299 + rescue_best.get('independent_rescued', 0)
    C.save_json(Path(__file__).resolve().parent / 'summary.json', summary)
    print(json.dumps({k: summary[k] for k in
                      ('baseline', 'control_experiments', 'q2_nocross', 'q3_transforms',
                       'q4_legacy_order', 'q6_adjacent_templates', 'q8_crossing_zone')},
                     indent=1)[:6000])


if __name__ == '__main__':
    main()
