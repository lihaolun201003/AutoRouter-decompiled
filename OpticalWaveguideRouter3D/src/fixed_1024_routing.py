"""PROJECT-SPECIFIC 1024 EXTENSION: fixed doubled legacy fixture, existing routing."""
from collections import defaultdict,Counter
from copy import deepcopy
from dataclasses import asdict
from math import isclose
from .models import Point2D,Point3D,Port,Waveguide,Layer
from .router_2d import (TrackPolicyConfig,prepare_waveguides_2d,assign_tracks_2d,
    build_track_grid_2d,generate_assigned_routes_2d)
from .geometry import (smooth_orthogonal_route_2d,build_special_z_smoothed_route_2d,
    validate_smoothed_route_2d)
from .geometry_3d import (LineSegment3D,PlanarArcSegment3D,CosineTransition3D,
    PathWindowTransition3D,Route3D,lift_smoothed_route_to_layer)
from .geometry_3d_diagnostics import analyze_route3d_joins
from .three_layer_assignment_3d import LayerConfiguration

BOARD_WIDTH_MM=300.
BOARD_HEIGHT_MM=200.


def legacy_waveguides_from_seed(seed):
    def port(p):return Port(p['id'],p['pmt_id'],p['local_id'],Point2D(**p['position']))
    return [Waveguide(w['id'],port(w['start_port']),port(w['end_port'])) for w in seed['waveguides']]


def generate_fixed_1024_input(legacy):
    """Two-copy graph lift: destination copy = source copy XOR (legacy route ID % 2).

    Each legacy PMT becomes adjacent copy 0/1 on its original board side; local
    endpoint slot is ascending legacy x, not the legacy snapshot index columns.
    """
    original=deepcopy(legacy)
    if len(legacy)!=512 or {w.id for w in legacy}!=set(range(512)):raise ValueError('FIXED_LEGACY_512_REQUIRED')
    groups=defaultdict(list)
    for w in legacy:
        for p in (w.start_port,w.end_port):groups[p.pmt_id].append(p)
    if len(groups)!=64:raise ValueError('REQUIRE_64_LEGACY_PMTS')
    mapping={};pmts=[];legacy_pmts=[]
    ids={i:rank for rank,i in enumerate(sorted(groups))}
    for side in (0.,150.):
        ordered=sorted((i for i,ps in groups.items() if ps[0].position.y==side),key=lambda i:min(p.position.x for p in groups[i]))
        if len(ordered)!=32:raise ValueError('REQUIRE_32_PMTS_PER_SIDE')
        origin=2. if side==0 else 4.
        for column,i in enumerate(ordered):
            ps=sorted(groups[i],key=lambda p:p.position.x)
            if len(ps)!=16 or any(p.position.y!=side for p in ps):raise ValueError('REQUIRE_16_ENDPOINTS_PER_PMT')
            expected=origin+4.5*column
            if not isclose(ps[0].position.x,expected,abs_tol=1e-8):raise ValueError('LEGACY_PMT_LAYOUT_MISMATCH')
            if any(not isclose(p.position.x,expected+.175*k,abs_tol=1e-8) for k,p in enumerate(ps)):raise ValueError('LEGACY_ENDPOINT_PITCH_MISMATCH')
            legacy_pmts.append(dict(legacy_pmt_id=i,side_y=side,column=column,x_min=ps[0].position.x,x_max=ps[-1].position.x,
                source_count=sum(w.start_port.pmt_id==i for w in legacy),destination_count=sum(w.end_port.pmt_id==i for w in legacy)))
            for copy in (0,1):
                pmt_id=2*ids[i]+copy+1;y=0. if side==0 else BOARD_HEIGHT_MM
                xmin=origin+4.5*(2*column+copy)
                pmts.append(dict(pmt_id=pmt_id,legacy_pmt_id=i,copy=copy,side='bottom' if side==0 else 'top',column=2*column+copy,x_min=xmin,y=y))
                for slot,p in enumerate(ps):mapping[p.id,copy]=dict(pmt_id=pmt_id,endpoint_slot=slot,legacy_port_id=p.id,
                    legacy_pmt_id=i,copy=copy,xyz=[xmin+.175*slot,y,0.])
    records=[]
    for w in sorted(legacy,key=lambda w:w.id):
        for copy in (0,1):
            route_id=2*w.id+copy
            a=deepcopy(mapping[w.start_port.id,copy]);b=deepcopy(mapping[w.end_port.id,copy^(w.id%2)])
            a['endpoint_id']=2*route_id;b['endpoint_id']=2*route_id+1
            records.append(dict(route_id=route_id,legacy_route_id=w.id,source_copy=copy,source=a,destination=b))
    result=dict(dataset='FIXED_1024_FROM_LEGACY_512_DOUBLE_COVER',parameter_status='PROJECT_SPECIFIC_EXPERIMENTAL',
        board=dict(width_mm=BOARD_WIDTH_MM,height_mm=BOARD_HEIGHT_MM),endpoint_pitch_mm=.175,pmt_pitch_mm=4.5,
        connection_rule='id=2*legacy_id+copy; destination_copy=copy XOR (legacy_id mod 2)',
        source_direction_preserved=True,pmts=sorted(pmts,key=lambda p:p['pmt_id']),routes=records,
        legacy_audit=dict(route_count=512,pmt_count=64,endpoints=1024,board_y=[0,150],
            endpoint_x_range=[min(p.position.x for ps in groups.values() for p in ps),max(p.position.x for ps in groups.values() for p in ps)],
            pmt_pitch_mm=4.5,endpoint_pitch_mm=.175,pmts=sorted(legacy_pmts,key=lambda p:p['legacy_pmt_id'])))
    validate_fixed_1024_input(result)
    assert legacy==original
    return result


def validate_fixed_1024_input(data):
    rows=data['routes'];ports=[p for r in rows for p in (r['source'],r['destination'])]
    if len(rows)!=1024 or {r['route_id'] for r in rows}!=set(range(1024)):raise ValueError('EXACTLY_1024_UNIQUE_ROUTES')
    if len({p['endpoint_id'] for p in ports})!=2048 or len({(p['pmt_id'],p['endpoint_slot']) for p in ports})!=2048:raise ValueError('DUPLICATE_ENDPOINT')
    if len({tuple(p['xyz']) for p in ports})!=2048:raise ValueError('DUPLICATE_ENDPOINT_POSITION')
    degrees=Counter(p['pmt_id'] for p in ports)
    if len(degrees)!=128 or set(degrees.values())!={16}:raise ValueError('128_PMTS_X_16_REQUIRED')
    if any(not (0<=p['xyz'][0]<=BOARD_WIDTH_MM and p['xyz'][1] in (0.,BOARD_HEIGHT_MM) and p['xyz'][2]==0) for p in ports):raise ValueError('BOARD_BOUNDS')
    if len({(p['legacy_port_id'],p['copy']) for p in ports})!=2048:raise ValueError('LEGACY_ENDPOINT_COPY_NOT_BIJECTIVE')


def waveguides_from_fixed_input(data):
    validate_fixed_1024_input(data)
    def port(p):return Port(p['endpoint_id'],p['pmt_id'],p['endpoint_slot'],Point2D(*p['xyz'][:2]))
    return [Waveguide(r['route_id'],port(r['source']),port(r['destination'])) for r in data['routes']]


def build_fixed_1024_geometry(data):
    ws=waveguides_from_fixed_input(data);frozen=deepcopy(ws)
    config=TrackPolicyConfig(BOARD_HEIGHT_MM,.05,.125,5.)
    preps=prepare_waveguides_2d(ws,BOARD_HEIGHT_MM,0.)
    assignments=assign_tracks_2d(ws,preps,config)
    unexpected=[asdict(a) for a in assignments if a.status not in ('assigned','unsupported_geometry')]
    if unexpected:raise ValueError(('FIXED_1024_ALLOCATION_FAILED',unexpected))
    skeletons=generate_assigned_routes_2d(ws,preps,assignments,top_y=BOARD_HEIGHT_MM,bottom_y=0.)
    planar={r.waveguide_id:smooth_orthogonal_route_2d(r,5.) for r in skeletons}
    for w,a in zip(ws,assignments):
        if a.status=='unsupported_geometry':planar[w.id]=build_special_z_smoothed_route_2d(w.id,w.start_port.position,w.end_port.position,5.)
    assert len(planar)==1024
    lifted={}
    for w in ws:
        r=planar[w.id];validate_smoothed_route_2d(r)
        assert r.segments[0].start==w.start_port.position and r.segments[-1].end==w.end_port.position
        lifted[w.id]=lift_smoothed_route_to_layer(r,Layer(0,0))
        joins=analyze_route3d_joins(lifted[w.id]);assert joins.all_C0 and joins.all_C1_direction
        from .clearance_3d import _box
        for p in lifted[w.id].primitives:
            bounds=_box(p,0,1)
            assert bounds[0][0]>=-1e-8 and bounds[0][1]<=BOARD_WIDTH_MM+1e-8
            assert bounds[1][0]>=-1e-8 and bounds[1][1]<=BOARD_HEIGHT_MM+1e-8
    assert ws==frozen
    stats=dict(geometry_count=len(planar),route3d_count=len(lifted),track_config=asdict(config),
        track_count=len(build_track_grid_2d(config)),assignment_status_counts=dict(Counter(a.status for a in assignments)),
        route_types=dict(Counter((p.route_type,p.side).__repr__() for p in preps)),
        original_height_track_count=len(build_track_grid_2d(TrackPolicyConfig(150.,.05,.125,5.))),
        baseline_read_only=True,allocator_modified=False)
    return planar,lifted,stats


def fixed_three_layer_config():
    return LayerConfiguration([Layer(0,0.),Layer(1,1.),Layer(2,2.)],.1,5.,'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC')


def run_fixed_1024_assignment(routes,planar,*,progress=None):
    from .sequential_elevation_3d import _run_sequential_elevation
    if len(routes)!=1024:raise ValueError('EXACTLY_1024_ROUTES_REQUIRED')
    from .collision import find_smoothed_route_intersections_2d
    class PlanarCrossingAnchors:
        def get(self,pair):
            return [Point3D(e.point.x,e.point.y,0.) for e in find_smoothed_route_intersections_2d(planar[pair[0]],planar[pair[1]]) if e.kind=='cross' and e.point is not None]
    return _run_sequential_elevation(routes,fixed_three_layer_config(),max_targets=1024,
        progress=progress,saved_crossings=PlanarCrossingAnchors(),expanded_layers=True,fixed_1024=True)


def _encode_path_window(p):
    """Self-describing encoding of a path window; every historical primitive
    keeps its previous 'geometry'=asdict(p) encoding unchanged."""
    return dict(pieces=[dict(type=type(q).__name__,geometry=asdict(q)) for q in p.pieces],
                z_start=p.z_start,z_end=p.z_end)


def serialize_route3d(route):
    return dict(route_id=route.route_id,continuity_tol=route.continuity_tol,
        primitives=[dict(type=type(p).__name__,
                         geometry=(_encode_path_window(p) if type(p) is PathWindowTransition3D
                                   else asdict(p)))
                    for p in route.primitives])


def deserialize_route3d(data):
    def build(item):
        raw=item['geometry'];kind=item['type']
        if kind=='PlanarArcSegment3D':
            p=PlanarArcSegment3D(raw['center_x'],raw['center_y'],raw['z'],raw['radius'],raw['start_angle'],raw['sweep_angle'])
            for key in ('_source_start_xy','_source_end_xy'):
                if raw.get(key) is not None:object.__setattr__(p,key,tuple(raw[key]))
            return p
        if kind=='LineSegment3D':
            return LineSegment3D(Point3D(**raw['start']),Point3D(**raw['end']))
        if kind=='CosineTransition3D':
            return CosineTransition3D(Point3D(**raw['start']),Point3D(**raw['end']))
        if kind=='PathWindowTransition3D':
            encoded=raw.get('pieces')
            if encoded and isinstance(encoded[0],dict) and 'geometry' in encoded[0]:
                pieces=tuple(build(row) for row in encoded)
            else:
                pieces=tuple(PlanarArcSegment3D(q['center_x'],q['center_y'],q['z'],q['radius'],
                                                q['start_angle'],q['sweep_angle'])
                             if q.get('radius') is not None
                             else LineSegment3D(Point3D(**q['start']),Point3D(**q['end']))
                             for q in encoded)
            return PathWindowTransition3D(pieces,raw['z_start'],raw['z_end'])
        raise ValueError('UNKNOWN_PRIMITIVE_TYPE')
    pieces=[build(item) for item in data['primitives']]
    return Route3D(data['route_id'],pieces,data['continuity_tol'])


def _deserialize_route3d_legacy(data):
    pieces=[]
    for item in data['primitives']:
        raw=item['geometry'];kind=item['type']
        if kind=='PlanarArcSegment3D':
            p=PlanarArcSegment3D(raw['center_x'],raw['center_y'],raw['z'],raw['radius'],raw['start_angle'],raw['sweep_angle'])
            for key in ('_source_start_xy','_source_end_xy'):
                if raw.get(key) is not None:object.__setattr__(p,key,tuple(raw[key]))
        elif kind in ('LineSegment3D','CosineTransition3D'):
            ctor=LineSegment3D if kind=='LineSegment3D' else CosineTransition3D
            p=ctor(Point3D(**raw['start']),Point3D(**raw['end']))
        else:raise ValueError('UNKNOWN_PRIMITIVE_TYPE')
        pieces.append(p)
    return Route3D(data['route_id'],pieces,data['continuity_tol'])
