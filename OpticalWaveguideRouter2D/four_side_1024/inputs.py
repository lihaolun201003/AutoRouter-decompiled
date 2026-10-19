"""Immutable connectivity identities and explicit physical/virtual port mapping."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

SIDES = 'NSEW'
INWARD = {'N': (0., -1.), 'S': (0., 1.), 'E': (-1., 0.), 'W': (1., 0.)}
PACKAGED_INPUT = Path(__file__).resolve().parents[1] / 'data/optical_1024_multitomulti_connectivity_v1.csv'
ORIGINAL_INPUT = Path(r'C:\Users\lihao\Desktop\optical_1024_multitomulti_connectivity_v1.csv')
DEFAULT_INPUT = PACKAGED_INPUT if PACKAGED_INPUT.exists() else ORIGINAL_INPUT
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / 'outputs/four_side_1024_single_layer_v1'


def config():
    return dict(board_mm=[150., 150.], layer=0, routing_layers=1,
                min_radius_mm=5., width_mm=.05, edge_gap_mm=.125,
                connector_pitch_mm=9., connector_pitch_status='provisional',
                connector_envelope_width_mm=12.59, connector_face_R_max_mm=7.7,
                provisional_visual_depth_mm=3.,
                ferrule_width_mm=6.5, ferrule_height_mm=2.5,
                envelope_status='IEC Fig9/Table6 full MPO sleeve H, H aligned with board edge; depth visualization provisional',
                physical_column_pitch_mm=.25, physical_row_pitch_mm=.5,
                physical_pitch_status='IEC 61754-7-3:2019 Fig2 and YD/T 1272.5-2019 FigA.8(b)',
                endpoint_mode='virtual_unfolded', virtual_pitch_mm=.175,
                initial_validation_parameters_not_final_glass_process=True,
                crossing_small_angle_deg=10., sagitta_mm=.0005,
                candidates_per_route=24, candidate_evaluation_budget=122880,
                search_seconds=600., strategies=['csv', 'longest', 'congested', 'opposite_first'],
                ripup_routes=20, crossing_region_policy='local clearance / sin(angle), both routes; no whole-pair exemption')


def board_xy(side, along, inset=0.):
    return {'N': [along, 150.-inset], 'S': [along, inset],
            'E': [150.-inset, along], 'W': [inset, along]}[side]


def load(path=DEFAULT_INPUT, cfg=None):
    cfg = cfg or config()
    raw = Path(path).read_bytes()
    rows = list(csv.DictReader(raw.decode('utf-8-sig').splitlines()))
    assert len(rows) == 1024, f'Expected 1024 connections, got {len(rows)}'
    assert sorted(int(r['route_id']) for r in rows) == list(range(1, 1025))
    endpoints, connectors = {}, []
    for side in SIDES:
        for c in range(1, 17):
            name = f'{side}{c:02d}'
            center = 7.5 + (c-1)*cfg['connector_pitch_mm']
            connectors.append(dict(connector=name, side=side, center_xy=board_xy(side, center),
                                   along_center_mm=center, channels=32,
                                   envelope_width_mm=cfg['connector_envelope_width_mm']))
            for row in (1, 2):
                for col in range(1, 17):
                    ch = (row-1)*16+col
                    key = f'{name}:{row}:{col}'
                    u = (col-8.5)*cfg['physical_column_pitch_mm']
                    v = (row-1.5)*cfg['physical_row_pitch_mm']
                    along = center+(ch-16.5)*cfg['virtual_pitch_mm']
                    endpoints[key] = dict(endpoint_id=key, connector=name, side=side, row=row,
                        column=col, channel=ch, physical_face_u_mm=u, physical_face_v_mm=v,
                        physical_projected_xy=board_xy(side, center+u),
                        routing_xy=board_xy(side, along), inward=list(INWARD[side]),
                        layer=0, mode='virtual_unfolded')
    usage = Counter()
    relations = Counter()
    for r in rows:
        r['route_id'] = int(r['route_id'])
        for role in ('source', 'target'):
            for field in ('row', 'column', 'channel'):
                r[f'{role}_{field}'] = int(r[f'{role}_{field}'])
            key = f"{r[role+'_connector']}:{r[role+'_row']}:{r[role+'_column']}"
            assert key in endpoints, key
            e = endpoints[key]
            assert e['side'] == r[role+'_side'] and e['channel'] == r[role+'_channel']
            r[role+'_endpoint'] = key
            usage[key] += 1
        s, t = r['source_side'], r['target_side']
        assert s != t
        pair = ''.join(sorted((s, t)))
        relation = 'opposite' if pair in ('NS', 'EW') else 'adjacent'
        assert r['relation'] == relation
        assert r['source_row'] == r['target_row'] == (1 if relation == 'opposite' else 2)
        r['pair'] = pair
        relations[relation] += 1
    assert set(usage) == set(endpoints) and set(usage.values()) == {1}
    assert relations == {'opposite': 512, 'adjacent': 512}
    assert len(set(tuple(e['routing_xy']) for e in endpoints.values())) == 2048
    # Provisional envelope lies outside the board, mating face on its boundary.
    # Same-side widths and along-edge bounds are checked; installed housings are not certified.
    envelope_conflicts = []
    for c in connectors:
        lo = c['along_center_mm']-c['envelope_width_mm']/2
        hi = c['along_center_mm']+c['envelope_width_mm']/2
        if lo < 0 or hi > 150:
            envelope_conflicts.append(c['connector']+':boundary')
    if cfg['connector_envelope_width_mm'] > cfg['connector_pitch_mm']:
        for side in SIDES:
            for i in range(1,16):
                envelope_conflicts.append(dict(first=f'{side}{i:02d}', second=f'{side}{i+1:02d}',
                    overlap_mm=cfg['connector_envelope_width_mm']-cfg['connector_pitch_mm']))
    validation = dict(passed=True, connections=len(rows), unique_physical_identities=len(usage),
        endpoints_used_once=True, connectors=64, channels_per_connector=32,
        opposite=512, adjacent=512, csv_sha256=hashlib.sha256(raw).hexdigest(),
        all_different_sides=True, csv_pairing_unchanged=True,
        virtual_coordinate_count=2048, physical_projection_unique_coordinates=1024,
        physical_projection_limitation='Two physical rows project to coincident board-plane ports; virtual unfolding is an idealized adapter, not a manufactured fanout.',
        provisional_envelope_conflicts=envelope_conflicts)
    return rows, endpoints, connectors, validation


def save_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')


def phase1(path=DEFAULT_INPUT, output=DEFAULT_OUTPUT, cfg=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.patches import Rectangle
    cfg = cfg or config()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    routes, endpoints, connectors, validation = load(path, cfg)
    copy = output / 'input_connectivity.csv'
    if copy.exists():
        assert copy.read_bytes() == Path(path).read_bytes(), 'Existing immutable input differs'
    else:
        copy.write_bytes(Path(path).read_bytes())
        copy.chmod(0o444)
    save_json(output/'config.json', cfg)
    save_json(output/'connectivity_validation.json', validation)
    save_json(output/'endpoints.json', list(endpoints.values()))
    save_json(output/'connectors.json', connectors)
    with (output/'endpoints.csv').open('w', newline='', encoding='utf-8') as f:
        fields = ['endpoint_id', 'connector', 'side', 'row', 'column', 'channel',
                  'physical_face_u_mm', 'physical_face_v_mm', 'physical_projected_xy',
                  'routing_xy', 'layer', 'mode']
        w = csv.DictWriter(f, fields, extrasaction='ignore'); w.writeheader(); w.writerows(endpoints.values())
    fig, ax = plt.subplots(figsize=(11, 11))
    colors = {'NS':'#3366bb', 'EW':'#b84040', 'EN':'#e3a323', 'ES':'#00a0a0', 'SW':'#a545b0', 'NW':'#60a735'}
    segments = [[endpoints[r['source_endpoint']]['routing_xy'], endpoints[r['target_endpoint']]['routing_xy']] for r in routes]
    ax.add_collection(LineCollection(segments, colors=[colors[r['pair']] for r in routes], linewidths=.35, alpha=.45))
    ax.add_patch(Rectangle((0, 0), 150, 150, fill=False, linewidth=1.5))
    for c in connectors:
        x, y = c['center_xy']; side = c['side']; width = c['envelope_width_mm']
        if side in 'NS':
            ax.add_patch(Rectangle((x-width/2, y if side=='N' else -3), width, 3, facecolor='#bbbbbb', edgecolor='black', linewidth=.3))
            ax.text(x, y+(4 if side=='N' else -5), c['connector'], ha='center', fontsize=5)
        else:
            ax.add_patch(Rectangle((x if side=='E' else -3, y-width/2), 3, width, facecolor='#bbbbbb', edgecolor='black', linewidth=.3))
            ax.text(x+(5 if side=='E' else -5), y, c['connector'], ha='center', fontsize=5)
    ax.set(xlim=(-9,159), ylim=(-9,159), aspect='equal', xlabel='x (mm)', ylabel='y (mm)',
           title='1024 original CSV connections | 64 connectors | 2048 port identities\nvirtual_unfolded | 150 x 150 mm | routing layer = 0')
    fig.tight_layout(); fig.savefig(output/'01_connectivity.png', dpi=200); plt.close(fig)
    return routes, endpoints, connectors, validation


if __name__ == '__main__':
    _, _, _, result = phase1()
    print(json.dumps(result, indent=2))
