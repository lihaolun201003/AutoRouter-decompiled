"""Step 9-F: fixed experimental 0/1/2 mm families on the existing 9-E loop."""
from dataclasses import dataclass
from .models import Layer
from .layer_assignment_3d import LayerConfiguration as TwoLayerConfiguration,elevation_candidates


@dataclass(frozen=True)
class LayerConfiguration(TwoLayerConfiguration):
    """Two-layer control or three-layer experiment; no arbitrary layer count."""

    def validate(self):
        if len(self.layers) not in (2,3) or any(type(x) is not Layer for x in self.layers):
            raise ValueError('REQUIRE_TWO_OR_THREE_LAYERS')
        for layer in self.layers:layer.validate()
        if len({x.id for x in self.layers})!=len(self.layers):raise ValueError('DUPLICATE_LAYER_ID')
        if len({x.z for x in self.layers})!=len(self.layers):raise ValueError('DUPLICATE_LAYER_Z')
        TwoLayerConfiguration(self.layers[:2],self.clearance_mm,self.required_radius_mm,
            self.transition_policy,self.parameter_status)
        if [(x.id,x.z) for x in self.layers]!=[(i,float(i)) for i in range(len(self.layers))]:
            raise ValueError('FIXED_EXPERIMENTAL_LAYERS_0_1_2_REQUIRED')


GENERATION_DOMAINS=('LINE_ONLY','PATH_WINDOWS')


def candidate_families(route,target_pair,crossings,config,*,window_slack_mm=0.0,
                       generation_domain='LINE_ONLY',path_window_settings=None,stats_out=None):
    """Enumerate every window in every configured elevated layer, in ID order.

    window_slack_mm is passed through to elevation_candidates; default 0.0
    keeps the historical generation inputs unchanged.

    generation_domain:
      LINE_ONLY     the historical finite straight-window enumeration, byte for
                    byte and in the same order (G0)
      PATH_WINDOWS  exactly the G0 candidates, plus the frozen path-arc-length
                    windows of src/path_window_3d.py (G1). Windows are
                    deduplicated by their PLANAR ARC-LENGTH interval, so a path
                    window that covers exactly the same frozen-path interval as
                    a G0 window is dropped in favour of the G0 one, and every
                    G0 candidate is always retained.

    Always returns (candidates, failures); optional generation accounting is
    written into stats_out so every existing caller keeps its two-value call."""
    if generation_domain not in GENERATION_DOMAINS:
        raise ValueError('UNSUPPORTED_GENERATION_DOMAIN')
    config.validate();candidates=[];failures={}
    stats=dict(generation_domain=generation_domain,line_window_candidates=0,
               path_window_candidates=0,path_window_dedup_removed=0,
               path_window_curvature_rejected=0,path_window_build_rejected=0,
               path_window_cap_truncated=0,path_window_length_does_not_fit=0,
               path_window_no_legal_interval=0,path_window_pairs_before_rejection=0,
               path_window_rejection_reasons={},path_window_settings=None)
    for layer in config.layers[1:]:
        family,failure=elevation_candidates(route,target_pair,crossings,config,target_layer_id=layer.id,
            window_slack_mm=window_slack_mm)
        candidates.extend(family);failures[layer.id]=failure
    stats['line_window_candidates']=len(candidates)
    if generation_domain=='LINE_ONLY':
        if stats_out is not None:
            stats_out.clear();stats_out.update(stats)
        return candidates,failures
    from .path_window_3d import (PATH_WINDOW_CANDIDATE_CAP,PATH_WINDOW_LENGTH_FACTORS,
        PATH_WINDOW_PLACEMENTS,candidate_path_offsets,path_window_candidates,planar_path_model)
    settings=dict(path_window_settings or {})
    placements=tuple(settings.get('placements',PATH_WINDOW_PLACEMENTS))
    factors=tuple(settings.get('length_factors',PATH_WINDOW_LENGTH_FACTORS))
    cap=int(settings.get('cap',PATH_WINDOW_CANDIDATE_CAP))
    stats['path_window_settings']=dict(placements=list(placements),length_factors=list(factors),cap=cap)
    model=planar_path_model(route)
    seen=set()
    for candidate in candidates:
        seen.add((candidate.layer_to,candidate_path_offsets(model,candidate)))
    for layer in config.layers[1:]:
        family,path_stats=path_window_candidates(route,target_pair,crossings,config,
            window_slack_mm=window_slack_mm,placements=placements,length_factors=factors,cap=cap,
            target_layer_id=layer.id)
        stats['path_window_curvature_rejected']+=path_stats['curvature_rejected']
        stats['path_window_build_rejected']+=path_stats['build_rejected']
        stats['path_window_cap_truncated']+=path_stats['cap_truncated']
        stats['path_window_pairs_before_rejection']+=path_stats['pair_count_before_rejection']
        stats['path_window_length_does_not_fit']+=sum(path_stats['length_does_not_fit'].values())
        stats['path_window_no_legal_interval']+=sum(1 for v in path_stats['no_legal_interval'].values() if v)
        for reason,count in path_stats['rejection_reasons'].items():
            stats['path_window_rejection_reasons'][reason]=\
                stats['path_window_rejection_reasons'].get(reason,0)+count
        for candidate in family:
            key=(layer.id,candidate_path_offsets(model,candidate))
            if key in seen:
                stats['path_window_dedup_removed']+=1
                continue
            seen.add(key);candidates.append(candidate)
    stats['path_window_candidates']=len(candidates)-stats['line_window_candidates']
    if stats_out is not None:
        stats_out.clear();stats_out.update(stats)
    return candidates,failures


def layer_candidate_rank(row):
    c=row['candidate']
    return (row['after_collision_count'],len(row['new_collisions_created']),c.extra_length_mm,
            c.elevated_length_mm,c.layer_to,c.rise_window,c.fall_window)


def run_layer_assignment_probe(initial_routes,config,*,max_targets=50,saved_crossings=None,progress=None):
    from .sequential_elevation_3d import _run_sequential_elevation
    if not isinstance(config,LayerConfiguration):raise TypeError('Step 9-F LayerConfiguration required')
    return _run_sequential_elevation(initial_routes,config,max_targets=max_targets,
        saved_crossings=saved_crossings,progress=progress,expanded_layers=True)
