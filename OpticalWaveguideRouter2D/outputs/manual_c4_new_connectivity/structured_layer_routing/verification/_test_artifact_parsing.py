"""Throw-away local test of the verifier's assignment-artefact parsing.

Builds stage4-style u_layer_assignment.json / opposite_assignment.json from the
*current* A payload in verification/_test_artifacts/A and runs the verifier's
artefact checkers on them.  Not part of the acceptance; delete after use.
"""
import importlib.util
import json
import sys
from pathlib import Path

VERIFY = Path(__file__).resolve().parent
SCRIPT = VERIFY / 'verify_structured_layer_routing.py'
spec = importlib.util.spec_from_file_location('v', SCRIPT)
v = importlib.util.module_from_spec(spec)
sys.modules['v'] = v
spec.loader.exec_module(v)

A = v.A_DIR
payload = json.loads((A / 'routes_1024.json').read_text(encoding='utf-8'))
summary = json.loads((A / 'summary.json').read_text(encoding='utf-8'))
records = {int(r['route_id']): r for r in payload['routes']}
conn_payload, connection = v.load_connectivity()
port_model = v.load_port_model()
_, expected_groups = v.expected_manifest_for(connection, False)
report = v.Report('A')
facts = v.check_rule_layers(report, records, connection, expected_groups, summary)
u_details = v.check_u_geometry(report, records, port_model, connection)
facts['u_details'] = u_details
class_map = {}
for gid in connection['opposite_groups']:
    rids = [int(rid) for rid in connection['groups'][gid]['route_ids']]
    classes, _info = v.classify_route(records[rids[0]])
    class_map[gid] = ('opposite_L2' if 'opposite_L2' in classes
                      else 'flat_interface')
facts['opposite_class_map'] = class_map
facts['opposite_route_ids'] = {gid: [int(rid) for rid in
                                     connection['groups'][gid]['route_ids']]
                               for gid in connection['opposite_groups']}

TEST = VERIFY / '_test_artifacts' / 'A'
TEST.mkdir(parents=True, exist_ok=True)


def rise_fall_info(route):
    parts = route.get('parts') or []
    transitions = [p for p in parts if p['kind'] == 'transition']
    flats = [p for p in parts if p['kind'] == 'flat']
    info = {}
    if transitions:
        up = transitions[0]
        down = transitions[-1]
        info['rise_start_xy'] = [round(float(x), 6) for x in up['start']]
        info['rise_end_xy'] = [round(float(x), 6) for x in up['end']]
        info['rise_start_mm'] = round(float(flats[0]['length_mm']), 6)
        info['rise_z_mm'] = [float(up['z0']), float(up['z1'])]
        if len(transitions) > 1:
            info['fall_start_xy'] = [round(float(x), 6) for x in down['start']]
            info['fall_end_xy'] = [round(float(x), 6) for x in down['end']]
            info['fall_start_mm'] = round(sum(float(p['length_mm'])
                                              for p in parts[:3]), 6)
            info['fall_z_mm'] = [float(down['z0']), float(down['z1'])]
    return info


def flat_z(rid):
    return [round(float(p['z_mm']), 6) for p in records[rid]['parts']
            if p['kind'] == 'flat']


# ---- opposite
opp_rows = []
for gid in connection['opposite_groups']:
    rids = [int(rid) for rid in connection['groups'][gid]['route_ids']]
    if class_map[gid] == 'opposite_L2':
        rep = records[rids[0]]
        flats = [p for p in rep['parts'] if p['kind'] == 'flat']
        opp_rows.append(dict(
            group_id=gid, status='L2', actual='L2', target_layer=2,
            target_z_mm=1.0, a_in=float(flats[0]['length_mm']),
            a_out=float(flats[-1]['length_mm']), route_ids=rids,
            rise_fall={str(rid): rise_fall_info(records[rid]) for rid in rids},
            reason=None))
    else:
        opp_rows.append(dict(
            group_id=gid, status='flat_interface_exception',
            actual='interface_flat', target_layer=2, target_z_mm=1.0,
            a_in=None, a_out=None, route_ids=rids, rise_fall={},
            reason=(summary.get('opposite_exceptions') or {}).get(str(gid))
            or 'kept_flat_interface'))
l2 = sum(1 for row in opp_rows if row['status'] == 'L2')
opp_doc = dict(schema='structured_layer_opposite_assignment_v1', group='A',
               total_groups=len(opp_rows), total_routes=272, l2_groups=l2,
               l2_routes=4 * l2, exception_groups=len(opp_rows) - l2,
               exception_routes=4 * (len(opp_rows) - l2),
               exception_reasons={row['group_id']: row['reason']
                                  for row in opp_rows
                                  if row['status'] != 'L2'},
               groups=opp_rows)
(TEST / 'opposite_assignment.json').write_text(
    json.dumps(opp_doc, ensure_ascii=False, indent=1), encoding='utf-8')

# ---- U
u_rows = []
reached = 0
for gid in v.TARGET_U_GROUPS:
    target_layer, target_z = v.TARGET_U_LAYER[gid]
    rids = [int(rid) for rid in connection['groups'][gid]['route_ids']]
    rep = records[rids[0]]
    flats = [p for p in rep['parts'] if p['kind'] == 'flat']
    high = [p for p in flats if int(p['layer_id']) != 1]
    arcs = [p for p in high[0]['primitives'] if p['kind'] == 'arc']
    depth = v.depth_of(rep.get('source_side'), arcs[0]['p0'])
    if u_details[gid]['ok']:
        reached += 1
        u_rows.append(dict(
            group_id=gid, bundle='test', status='target_layer_reached',
            target_layer=target_layer, target_z_mm=target_z,
            actual_layer=target_layer, actual_z_mm=target_z,
            a_in=float(flats[0]['length_mm']),
            a_out=float(flats[-1]['length_mm']),
            high_arc_depth=round(float(depth), 6), route_ids=rids,
            rise_fall={str(rid): rise_fall_info(records[rid]) for rid in rids},
            failure=None))
    else:
        u_rows.append(dict(group_id=gid, bundle='test', status='failed',
                           target_layer=target_layer, target_z_mm=target_z,
                           actual_layer=None, actual_z_mm=None, a_in=None,
                           a_out=None, high_arc_depth=None, route_ids=rids,
                           rise_fall={}, failure='not assembled'))
u_doc = dict(schema='structured_layer_u_assignment_v1', group='A',
             total_groups=len(u_rows), total_routes=256,
             target_reached_groups=reached,
             failed_groups=len(u_rows) - reached, failures={},
             groups=u_rows)
(TEST / 'u_layer_assignment.json').write_text(
    json.dumps(u_doc, ensure_ascii=False, indent=1), encoding='utf-8')

# ---- run the verifier checkers
v.check_u_assignment(report, 'A', TEST, records, u_details, summary)
v.check_opposite_assignment(report, 'A', TEST, records, facts)
for check in report.checks[-2:]:
    print(check['name'], 'PASS' if check['passed'] else 'FAIL')
    print(json.dumps(check.get('detail'), ensure_ascii=False)[:800])
