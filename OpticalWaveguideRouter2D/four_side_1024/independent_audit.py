"""Independent saved-artifact verification, not the routing conflict checker.

Run after export: python -m four_side_1024.independent_audit
Uses geometry.intersections (separate from conflicts.py), own length/pose
calculations, raw GDS binary records, and an independent sampled-segment simple
curve test. Shapely is an additional check when available, never a dependency.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import struct
import time

import numpy as np

from .geometry import intersections, bounds, sample
from .inputs import DEFAULT_OUTPUT, save_json


def _real8(data):
    if data == bytes(8):
        return 0.
    sign = -1. if data[0]&0x80 else 1.
    return sign*int.from_bytes(data[1:],'big')/(1<<56)*16.**((data[0]&127)-64)


def _read_gds(path):
    """Read actual UNITS/PATH/LAYER/DATATYPE/WIDTH/XY bytes independently."""
    data = Path(path).read_bytes()
    offset=0; units=None; paths=[]; current=None; polygon_count=0
    while offset<len(data):
        length,kind,dtype=struct.unpack('>HBB',data[offset:offset+4])
        if length<4 or offset+length>len(data):
            raise ValueError('Malformed GDS record')
        payload=data[offset+4:offset+length]
        if kind==3:
            units=(_real8(payload[:8]),_real8(payload[8:]))
        elif kind==8:
            polygon_count+=1
        elif kind==9:
            current={}
        elif current is not None:
            if kind==13:
                current['layer']=struct.unpack('>h',payload)[0]
            elif kind==14:
                current['datatype']=struct.unpack('>h',payload)[0]
            elif kind==15:
                current['width_db']=struct.unpack('>i',payload)[0]
            elif kind==16:
                current['xy_db']=np.frombuffer(payload,dtype='>i4').astype(float).reshape((-1,2))
            elif kind==17:
                paths.append(current); current=None
        offset+=length
    if units is None:
        raise ValueError('GDS missing UNITS')
    user_per_db,db_m=units
    for path in paths:
        path['xy_mm']=path['xy_db']*db_m*1000
        path['width_mm']=abs(path['width_db'])*db_m*1000
    return dict(unit_m=db_m/user_per_db,precision_m=db_m,paths=paths,
                polygon_count=polygon_count,sha256=hashlib.sha256(data).hexdigest())


def _tangent(primitive,point=None,end=False):
    if primitive['kind']=='line':
        vector=np.subtract(primitive['p1'],primitive['p0'])
        return vector/np.linalg.norm(vector)
    if point is None:
        a=primitive['start_angle']+(primitive['sweep'] if end else 0.)
    else:
        a=math.atan2(point[1]-primitive['center'][1],point[0]-primitive['center'][0])
    sign=1 if primitive['sweep']>0 else -1
    return sign*np.array([-math.sin(a),math.cos(a)])


def _bbox_overlap(a,b,tol=1e-8):
    return a[0]<=b[2]+tol and b[0]<=a[2]+tol and a[1]<=b[3]+tol and b[1]<=a[3]+tol


def _polyline_simple(points):
    """Vectorized independent finite-segment intersections, all nonneighbors."""
    points=np.asarray(points)
    points=points[np.r_[True,np.linalg.norm(np.diff(points,axis=0),axis=1)>1e-10]]
    a=points[:-1]; u=points[1:]-a
    if len(a)<3:
        return True
    i,j=np.triu_indices(len(a),k=2)
    v=u[j]; uu=u[i]; w=a[j]-a[i]
    den=uu[:,0]*v[:,1]-uu[:,1]*v[:,0]
    scale=np.linalg.norm(uu,axis=1)*np.linalg.norm(v,axis=1)
    nonparallel=np.abs(den)>1e-12*np.maximum(scale,1e-20)
    if np.any(nonparallel):
        crosswv=w[:,0]*v[:,1]-w[:,1]*v[:,0]
        crosswu=w[:,0]*uu[:,1]-w[:,1]*uu[:,0]
        t=crosswv[nonparallel]/den[nonparallel]
        q=crosswu[nonparallel]/den[nonparallel]
        if np.any((t>=-1e-10)&(t<=1+1e-10)&(q>=-1e-10)&(q<=1+1e-10)):
            return False
    parallel=~nonparallel
    if np.any(parallel):
        us=uu[parallel]; ws=w[parallel]; vs=v[parallel]
        norms=np.linalg.norm(us,axis=1)
        collinear=np.abs(ws[:,0]*us[:,1]-ws[:,1]*us[:,0])<=1e-10*norms
        if np.any(collinear):
            us,ws,vs=us[collinear],ws[collinear],vs[collinear]
            norm2=np.sum(us*us,axis=1)
            t0=np.sum(ws*us,axis=1)/norm2
            t1=np.sum((ws+vs)*us,axis=1)/norm2
            lo=np.maximum(0,np.minimum(t0,t1)); hi=np.minimum(1,np.maximum(t0,t1))
            if np.any(hi>=lo-1e-10):
                return False
    return True


def main(output=DEFAULT_OUTPUT):
    start=time.perf_counter(); output=Path(output)
    cfg=json.loads((output/'config.json').read_text(encoding='utf-8'))
    geometries=json.loads((output/'routes_geometry.json').read_text(encoding='utf-8'))
    records=sorted(geometries['routes'],key=lambda r:r['route_id'])
    endpoint_data=json.loads((output/'endpoints.json').read_text(encoding='utf-8'))
    endpoints=({e['endpoint_id']:e for e in endpoint_data} if isinstance(endpoint_data,list) else endpoint_data)
    routes=json.loads((output/'routes.json').read_text(encoding='utf-8'))
    lookup={r['route_id']:r for r in routes}
    stats=json.loads((output/'statistics.json').read_text(encoding='utf-8'))
    source_bytes=(output/'input_connectivity.csv').read_bytes()
    source=list(csv.DictReader(source_bytes.decode('utf-8-sig').splitlines()))
    errors=[]; max_endpoint=0.; max_tangent=0.; max_length=0.; lengths=[]; boxes={}
    self_intersections=0; self_overlaps=0; min_radius=math.inf; dense_simple_failures=[]
    try:
        from shapely.geometry import LineString
        shapely_available=True
    except ImportError:
        LineString=None; shapely_available=False
    shapely_simple_failures=[]
    if len(source)!=1024 or len(routes)!=1024:
        errors.append('input_or_record_count_not_1024')
    if len({r['route_id'] for r in routes})!=1024:
        errors.append('route_identities_not_unique')
    if {r['route_id'] for r in routes if r['status']=='success'}!={r['route_id'] for r in records}:
        errors.append('route_status_geometry_mismatch')
    original={int(r['route_id']):r for r in source}
    for r in routes:
        for key,value in original[r['route_id']].items():
            if str(r[key])!=value:
                errors.append(f'csv_identity_changed:{r["route_id"]}:{key}')
    for rec in records:
        rid=rec['route_id']; ps=rec['primitives']; relation=lookup[rid]
        src=endpoints[relation['source_endpoint']]; dst=endpoints[relation['target_endpoint']]
        if rec.get('layer')!=0:
            errors.append(f'nonzero_route_layer:{rid}')
        endpoint=max(math.dist(ps[0]['p0'],src['routing_xy']),math.dist(ps[-1]['p1'],dst['routing_xy']))
        tangent=max(np.linalg.norm(_tangent(ps[0])-np.array(src['inward'])),
                    np.linalg.norm(_tangent(ps[-1],end=True)+np.array(dst['inward'])))
        max_endpoint=max(max_endpoint,endpoint); max_tangent=max(max_tangent,float(tangent))
        if endpoint>1e-7 or tangent>1e-7:
            errors.append(f'endpoint_or_direction:{rid}')
        exact=sum(math.dist(p['p0'],p['p1']) if p['kind']=='line' else p['radius']*abs(p['sweep']) for p in ps)
        lengths.append(exact); max_length=max(max_length,abs(exact-rec['length_mm']))
        boxes[rid]=[bounds(p) for p in ps]
        for i,p in enumerate(ps):
            if p.get('layer',0)!=0 or abs(p.get('z',0))>1e-10:
                errors.append(f'nonplanar_primitive:{rid}:{i}')
            if p['kind']=='arc':
                min_radius=min(min_radius,p['radius'])
                if p['radius']<cfg['min_radius_mm']-1e-8:
                    errors.append(f'radius:{rid}:{i}')
                for key,a in [('p0',p['start_angle']),('p1',p['start_angle']+p['sweep'])]:
                    reconstructed=np.array(p['center'])+p['radius']*np.array([math.cos(a),math.sin(a)])
                    if np.linalg.norm(reconstructed-p[key])>1e-7:
                        errors.append(f'arc_endpoint:{rid}:{i}:{key}')
            b=bounds(p,cfg['width_mm'])
            if min(b[0],b[1])<-1e-8 or max(b[2],b[3])>150+1e-8:
                errors.append(f'board_bounds:{rid}:{i}')
            if i:
                if math.dist(ps[i-1]['p1'],p['p0'])>1e-7 or np.linalg.norm(_tangent(ps[i-1],end=True)-_tangent(p))>1e-7:
                    errors.append(f'join:{rid}:{i}')
            for j in range(i+1,len(ps)):
                if not _bbox_overlap(boxes[rid][i],boxes[rid][j]):
                    continue
                points,overlap=intersections(p,ps[j]); self_overlaps+=int(overlap)
                self_intersections+=sum(j!=i+1 or math.dist(point,p['p1'])>1e-7 for point in points)
        dense=sample(ps,cfg['sagitta_mm']/10)
        if not _polyline_simple(dense):
            dense_simple_failures.append(rid)
        if shapely_available and not LineString(dense).is_simple:
            shapely_simple_failures.append(rid)
    independent_crossings={}; pair_overlaps=[]; contacts=[]
    for ai,a in enumerate(records):
        arid=a['route_id']
        for b in records[ai+1:]:
            brid=b['route_id']; points=[]; overlap=False
            for i,p in enumerate(a['primitives']):
                for j,q in enumerate(b['primitives']):
                    if not _bbox_overlap(boxes[arid][i],boxes[brid][j]):
                        continue
                    crossings,common=intersections(p,q); overlap|=common
                    for point in crossings:
                        if any(math.dist(point,c['point'])<1e-6 for c in points):
                            continue
                        u,v=_tangent(p,point),_tangent(q,point)
                        angle=math.degrees(math.atan2(abs(u[0]*v[1]-u[1]*v[0]),abs(float(np.dot(u,v)))))
                        points.append(dict(point=list(map(float,point)),angle=angle))
                        if angle<1e-6:
                            contacts.append([arid,brid])
            if points:
                independent_crossings[(arid,brid)]=points
            if overlap:
                pair_overlaps.append([arid,brid])
    with (output/'crossings.csv').open(encoding='utf-8-sig',newline='') as f:
        exported=list(csv.DictReader(f))
    mismatched=[]; max_crossing_position=0.; max_crossing_angle=0.; matched=set()
    for c in exported:
        pair=tuple(sorted((int(c['route_a']),int(c['route_b']))))
        options=independent_crossings.get(pair,[])
        if not options:
            mismatched.append(dict(pair=pair,reason='exported_crossing_missing')); continue
        point=(float(c['x_mm']),float(c['y_mm']))
        best=min(range(len(options)),key=lambda i:math.dist(point,options[i]['point']))
        match=options[best]; error=math.dist(point,match['point']); angle=abs(float(c['angle_deg'])-match['angle'])
        max_crossing_position=max(max_crossing_position,error); max_crossing_angle=max(max_crossing_angle,angle)
        if (pair,best) in matched:
            mismatched.append(dict(pair=pair,reason='duplicate_crossing_record'))
        matched.add((pair,best))
        if error>1e-5 or angle>1e-5:
            mismatched.append(dict(pair=pair,reason='crossing_position_or_angle',position_error_mm=error,angle_error_deg=angle))
    independent_count=sum(map(len,independent_crossings.values()))
    if independent_count!=len(exported) or len(matched)!=independent_count:
        errors.append('independent_crossing_count_mismatch')
    if mismatched:
        errors.append('independent_crossing_details_mismatch')
    gds=_read_gds(output/'routing_all.gds'); gds_errors=[]; max_gds_endpoint=0.; max_gds_width=0.; gds_simple_failures=[]
    if abs(gds['unit_m']-1e-3)>1e-15 or abs(gds['precision_m']-1e-9)>1e-20:
        gds_errors.append('units_or_precision')
    if len(gds['paths'])!=len(records) or gds['polygon_count']:
        gds_errors.append('path_count_or_unexpected_polygon')
    for rec,p in zip(records,gds['paths']):
        if p['layer']!=0 or p['datatype']!=0:
            gds_errors.append(f'layer_or_datatype:{rec["route_id"]}')
        width_error=abs(p['width_mm']-cfg['width_mm']); max_gds_width=max(max_gds_width,width_error)
        endpoint=max(math.dist(p['xy_mm'][0],rec['primitives'][0]['p0']),math.dist(p['xy_mm'][-1],rec['primitives'][-1]['p1']))
        max_gds_endpoint=max(max_gds_endpoint,endpoint)
        if endpoint>1e-6 or width_error>1e-8:
            gds_errors.append(f'endpoint_or_width:{rec["route_id"]}')
        if not _polyline_simple(p['xy_mm']):
            gds_simple_failures.append(rec['route_id'])
    if self_intersections or self_overlaps or pair_overlaps or contacts or dense_simple_failures or shapely_simple_failures:
        errors.append('illegal_geometry_found')
    if abs(sum(lengths)-stats['total_length_mm'])>1e-6 or len(records)!=stats['success_count'] or independent_count!=stats['crossing_count']:
        errors.append('statistics_mismatch')
    if gds_errors or gds_simple_failures:
        errors.append('gds_verification_failed')
    # Recompute the documented old-polymer arithmetic without calling its
    # implementation. Input angles remain the exported audited angles because
    # the legacy lookup deliberately truncates integer degrees.
    loss_records=json.loads((output/'legacy_loss_per_route.json').read_text(encoding='utf-8'))
    table_path=Path(__file__).resolve().parents[1]/'data/crossing_loss_from_thesis_fig3_12.csv'
    with table_path.open(encoding='utf-8',newline='') as f:
        raw_table={int(v['angle_deg']):float(v['loss_db_per_30_crossings']) for v in csv.DictReader(f)}
    table={k:v*(.05/raw_table[90])/30 for k,v in raw_table.items()}
    density={2.:16/6.33,3.:10.59/7.33,4.:6.08/8.33,5.:2.8/9.23,
             6.:2.03/10.05,8.:1.39/11.53,10.:.87/12.92,15.:.45/15.74}
    loss_by_route={r['route_id']:dict(propagation_db=0.,bend_db=0.,crossing_db=0.,unmodeled_crossings=0) for r in records}
    for rec in records:
        own=loss_by_route[rec['route_id']]
        for p in rec['primitives']:
            if p['kind']=='line':
                own['propagation_db']+=math.dist(p['p0'],p['p1'])*.005
            else:
                own['bend_db']+=abs(p['sweep'])*p['radius']*density[p['radius']]
    for c in exported:
        angle=int(float(c['angle_deg']))
        for rid in (int(c['route_a']),int(c['route_b'])):
            if angle in table:
                loss_by_route[rid]['crossing_db']+=table[angle]
            else:
                loss_by_route[rid]['unmodeled_crossings']+=1
    max_loss_error=0.; loss_errors=[]; own_known=[]
    for rid,own in loss_by_route.items():
        recorded=loss_records[str(rid)]
        known=own['propagation_db']+own['bend_db']+own['crossing_db']; own_known.append(known)
        for key in ('propagation_db','bend_db','crossing_db'):
            max_loss_error=max(max_loss_error,abs(own[key]-recorded[key]))
        max_loss_error=max(max_loss_error,abs(known-recorded['known_components_db']))
        if own['unmodeled_crossings']!=recorded['unmodeled_crossings'] or (own['unmodeled_crossings'] and recorded['estimated_total_db'] is not None):
            loss_errors.append(rid)
    mean_known=sum(own_known)/len(own_known) if own_known else 0.
    if max_loss_error>1e-9 or abs(mean_known-stats['legacy_loss_estimate']['mean_known_components_db'])>1e-9 or loss_errors:
        errors.append('legacy_loss_arithmetic_mismatch')
    result=dict(passed=not errors,errors=errors,route_count=len(records),input_connection_count=len(source),
        methods=['independent geometry.intersections','independent exact primitive length and pose',
                 'analytic stroke bounds','dense NumPy nonadjacent segment self intersections',
                 'raw binary GDS UNITS/PATH/LAYER/DATATYPE/WIDTH/XY parser',
                 'independent documented legacy-polymer arithmetic'],
        shapely_available=shapely_available,shapely_additional_simple_failures=shapely_simple_failures,
        source_sha256=hashlib.sha256(source_bytes).hexdigest(),
        max_endpoint_error_mm=max_endpoint,max_direction_vector_error=max_tangent,
        max_length_record_error_mm=max_length,independent_total_length_mm=sum(lengths),min_radius_mm=min_radius,
        self_intersections=self_intersections,self_overlaps=self_overlaps,pair_overlaps=pair_overlaps,
        tangent_contacts=contacts,dense_polyline_self_simple_failures=dense_simple_failures,
        crossing_count=independent_count,exported_crossing_count=len(exported),
        max_crossing_position_error_mm=max_crossing_position,max_crossing_angle_error_deg=max_crossing_angle,
        crossing_mismatches=mismatched,
        legacy_loss=dict(max_component_error_db=max_loss_error,mismatched_routes=loss_errors,
                         independent_mean_known_components_db=mean_known,
                         model='old polymer model only, not glass measurements'),
        gds=dict(passed=not(gds_errors or gds_simple_failures),errors=gds_errors,paths=len(gds['paths']),
            layers=sorted({p['layer'] for p in gds['paths']}),unit_m=gds['unit_m'],precision_m=gds['precision_m'],
            width_mm=cfg['width_mm'],max_width_error_mm=max_gds_width,max_endpoint_error_mm=max_gds_endpoint,
            polyline_self_simple_failures=gds_simple_failures,sha256=gds['sha256']),
        limitations='Independent audit verifies centers/angles/poses/lengths/simple curves and GDS, not optical fabrication. Local inter-route spacing is separately verified by the main exact conflict audit.',
        runtime_seconds=time.perf_counter()-start)
    save_json(output/'independent_audit.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    args=parser.parse_args()
    raise SystemExit(0 if main(args.output)['passed'] else 1)
