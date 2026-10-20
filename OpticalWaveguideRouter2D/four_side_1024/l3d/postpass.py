"""Stage 4 post-pass: local re-layering of already accepted routes.

The corrected-model router keeps every accepted route's XY geometry.  This pass
takes routes that are still flat on L1 (both the re-used R15 2D baselines and
routes added during the 3D passes), rips them out of the true-XYZ world one at a
time, and re-builds the same XY path over a multi-layer sequence
(e.g. L1→L2→L3→L1, L1→L4→L5→L1).  The re-layered route is committed only when
the independent-style world checks pass; otherwise the original route is
restored.

This demonstrates the required stage-4 capability ("already successful routes
can participate in local re-layering") and produces real multi-transition
example routes for the report/visualisation.  The routed count is unchanged
unless the re-layering also happens to free L1 space (it is not a rip-up of
other routes, so the count stays the same here).

CLI::

    python -m four_side_1024.l3d.postpass --routes outputs/.../routes_l3d.json \
        --targets 24 --max-attempts 80

By default the result is written as a replacement ``routes_l3d.json`` and the
router output is kept as ``routes_l3d_router.json``.
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

from . import common, layers, paths
from .common import PROJECT_ROOT
from .world import World


def _row_z(record):
    return 0.0 if int(record['source_row']) == 1 else 0.5


def _port_meta(record):
    return dict(source_port=record['source_port'],
                target_port=record['target_port'],
                source_row=int(record['source_row']),
                target_row=int(record['target_row']))


def _record_from_route(base_record, route):
    record = {key: base_record[key] for key in
              ('route_id', 'plane', 'source_row', 'target_row', 'source_port',
               'target_port', 'baseline_2d', 'status')}
    record.update(dict(
        start_z_mm=round(float(route['start_z_mm']), 9),
        end_z_mm=round(float(route['end_z_mm']), 9),
        layer_sequence=[int(value) for value in route['layer_sequence']],
        layer_z_sequence=[round(float(value), 9) for value in route['layer_z_sequence']],
        n_transitions=int(route['n_transitions']),
        lifted=bool(route['lifted']),
        layers_used=sorted({int(value) for value in route['layer_sequence']}),
        xy_length_mm=round(float(route['xy_length_mm']), 6),
        length_mm=round(float(route['length_mm']), 6),
        z_span_mm=round(float(route['z_span_mm']), 6),
        mode='relayered',
        family=base_record.get('family'),
        params=base_record.get('params') or {},
        parts=route['parts']))
    return record


def _clean_record(record):
    """Make the route record JSON-safe (round numbers, keep schema fields)."""
    return json.loads(json.dumps(record))


def relayer(payload, stack, targets=24, max_attempts=80, variants=(0, 1, 2),
            max_straights=3, log=print):
    world = World(stack)
    records = [_clean_record(record) for record in payload['routes']]
    routed = [record for record in records if record.get('status') == 'routed']
    for record in routed:
        world.add_route(record)
    # all intermediate-layer sequences need >= 3 transitions for a real
    # multi-layer demonstration (L1 -> Li -> Lj -> ... -> L1)
    sequences = [sequence for sequence in layers.plan_sequences('multi')
                 if len(sequence) >= 4]
    candidates = sorted(
        [record for record in routed if int(record['n_transitions']) == 0
         and float(record['length_mm']) > 60.0],
        key=lambda record: (-float(record['length_mm']), int(record['route_id'])))
    log(f'relayer: {len(candidates)} flat candidate routes, '
        f'{len(sequences)} multi-layer sequences, targets={targets}')
    started = time.perf_counter()
    successes = []
    attempts = 0
    for record in candidates:
        if len(successes) >= targets or attempts >= max_attempts:
            break
        attempts += 1
        route_id = int(record['route_id'])
        original = record
        world.remove_route(route_id)
        base_prims = original['parts'][0]['primitives']
        meta = _port_meta(original)
        replacement = None
        for sequence in sequences:
            z_sequence = stack.z_sequence_for(sequence, row=original['plane'])
            for variant in variants:
                try:
                    built = paths.build_route_l3d(
                        route_id, original['plane'], base_prims, sequence,
                        z_sequence, meta, radius=15.0, variant=int(variant))
                except ValueError:
                    built = None
                if built is None:
                    continue
                new_record = _clean_record(_record_from_route(original, built))
                violations = world.check_route(new_record, check_self=True)
                if violations:
                    continue
                replacement = new_record
                break
            if replacement is not None:
                break
        if replacement is None:
            world.add_route(original)
            continue
        world.add_route(replacement)
        index = records.index(original)
        records[index] = replacement
        successes.append(dict(
            route_id=route_id,
            original_layer_sequence=original['layer_sequence'],
            new_layer_sequence=replacement['layer_sequence'],
            n_transitions=replacement['n_transitions'],
            length_mm=replacement['length_mm']))
        log(f'relayer: route {route_id} -> {"-".join("L%d" % value for value in replacement["layer_sequence"])} '
            f'({replacement["n_transitions"]} transitions)')
    payload['routes'] = records
    summary = dict(
        role='stage4_local_relayering',
        candidate_routes=len(candidates),
        attempts=attempts,
        relayered=len(successes),
        routed_unchanged=True,
        sequences=[int(value) for value in range(2, 6)],
        seconds=round(time.perf_counter() - started, 2),
        relayered_routes=successes)
    payload['relayer'] = summary
    _refresh_statistics(payload)
    return summary


def _refresh_statistics(payload):
    from collections import Counter
    records = [record for record in payload['routes']
               if record.get('status') == 'routed']
    layer_counts = Counter()
    plane_flat_parts = Counter()
    plane_flat_lengths = Counter()
    transition_pairs = Counter()
    transitions_hist = Counter()
    layers_used_hist = Counter()
    layer_sequence_hist = Counter()
    total_length = 0.0
    total_xy = 0.0
    for record in records:
        transitions_hist[str(int(record['n_transitions']))] += 1
        layers_used_hist[','.join(str(v) for v in record['layers_used'])] += 1
        layer_sequence_hist['->'.join(str(v) for v in record['layer_sequence'])] += 1
        total_length += float(record['length_mm'])
        total_xy += float(record['xy_length_mm'])
        for part in record['parts']:
            if part['kind'] == 'flat':
                layer_counts[str(part['layer_id'])] += 1
                key = f'L{part["layer_id"]}@{float(part["z_mm"]):g}'
                plane_flat_parts[key] += 1
                plane_flat_lengths[key] += float(part['length_mm'])
            else:
                transition_pairs[f'{part["from_layer"]}->{part["to_layer"]}'] += 1
    statistics = payload.setdefault('statistics', {})
    statistics.update(dict(
        routed=len(records),
        lifted=sum(1 for record in records if record['lifted']),
        transitions=sum(int(record['n_transitions']) for record in records),
        total_length_mm=round(total_length, 6),
        mean_length_mm=round(total_length / len(records), 6) if records else None,
        total_xy_length_mm=round(total_xy, 6),
        per_layer_flat_parts=dict(layer_counts),
        per_physical_plane_flat_parts=dict(plane_flat_parts),
        per_physical_plane_flat_length_mm={key: round(value, 6)
                                           for key, value in plane_flat_lengths.items()},
        transition_layer_pairs=dict(transition_pairs),
        transitions_histogram=dict(transitions_hist),
        layers_used_histogram=dict(layers_used_hist),
        layer_sequence_histogram=dict(layer_sequence_hist),
        z_span_max_mm=max((float(record['z_span_mm']) for record in records),
                          default=0.0)))
    payload['routed'] = len(records)
    payload['failed'] = sum(1 for record in payload['routes']
                            if record.get('status') != 'routed')
    if payload.get('stage'):
        payload['stage'] = str(payload['stage']) + '+relayer'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--routes', required=True, type=Path)
    parser.add_argument('--targets', type=int, default=24)
    parser.add_argument('--max-attempts', type=int, default=80)
    parser.add_argument('--out', type=Path, default=None)
    parser.add_argument('--keep-router-file', action='store_true', default=True)
    args = parser.parse_args(argv)

    from ..r15 import profile_r15
    profile_r15.apply(verbose=True)
    from ..fslw import config as C

    payload = json.loads(Path(args.routes).read_text(encoding='utf-8'))
    stack = layers.load_stack(payload['layer_stack'])
    log_lines = []

    def log(message):
        line = time.strftime('%H:%M:%S') + ' ' + str(message)
        print(line, flush=True)
        log_lines.append(line)

    log(f'postpass routes={args.routes} stack={stack.name} radius={C.RADIUS_MM}')
    summary = relayer(payload, stack, targets=args.targets,
                      max_attempts=args.max_attempts, log=log)
    routes_path = Path(args.routes)
    if args.out is None:
        backup = routes_path.with_name(routes_path.stem + '_router.json')
        if not backup.exists():
            shutil.copy2(routes_path, backup)
            log(f'kept router output as {backup}')
        out_path = routes_path
    else:
        out_path = Path(args.out)
    common.write_json(out_path, payload)
    summary_path = out_path.with_name('postpass_summary.json')
    common.write_json(summary_path, dict(
        schema='four_side_1024_v2_l3d_postpass_v1',
        input=str(args.routes), output=str(out_path),
        radius_mm=float(C.RADIUS_MM), layer_stack=stack.to_dict(),
        relayer=summary, log=log_lines))
    log(f'written {out_path}')
    print(json.dumps(dict(relayered=summary['relayered'],
                          routed=payload['routed'],
                          transitions=payload['statistics']['transitions']),
                     ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
