"""Select the per-plane best verified layout of the round and write the BEST planes.

Selection rule (task 6.5 / task 8):
* z2: the layout with the largest routed count among the *verified* experiment
  checkpoints (E1/E2/E3); ties prefer E3 (expanded candidates + R&R).
* z1: Z1OPT if it strictly improves on the 492-route baseline, otherwise BASE.

The selected layouts are written to ``planes/V2/BEST/{z1,z2}/routes.json`` with the
frozen fslw schema so ``v2opt.finalize`` can independently audit them and build the
combined 1024-channel artefact.
"""
from __future__ import annotations

import json
from pathlib import Path

from .core import (DEFAULT_OUT, LayoutState, load_layout_from_checkpoint)
from . import search as S


def _load_summary(label, plane):
    path = Path(DEFAULT_OUT) / 'experiments' / f'{label}_{plane}_summary.json'
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def _checkpoint_candidates():
    root = Path(DEFAULT_OUT) / 'checkpoints'
    return {path.stem: path for path in root.glob('*.json')}


def select_z2(log=print):
    candidates = []
    for label in ('E1', 'E2', 'E3', 'E3X'):
        summary = _load_summary(label, 'z2')
        if not summary:
            continue
        checkpoint = Path(DEFAULT_OUT) / 'checkpoints' / f'{label}_z2.json'
        if not checkpoint.exists():
            continue
        candidates.append(dict(label=label,
                               routed=summary.get('final_routed', summary.get('routed')),
                               checkpoint=str(checkpoint), summary=str(
                                   Path(DEFAULT_OUT) / 'experiments'
                                   / f'{label}_z2_summary.json')))
    if not candidates:
        raise FileNotFoundError('no E1/E2/E3 z2 summary + checkpoint found')
    # ties prefer the most general arm (E3 > E3X > E2 > E1)
    preference = {'E3': 0, 'E3X': 1, 'E2': 2, 'E1': 3}
    candidates.sort(key=lambda item: (-item['routed'], preference[item['label']]))
    log('z2 candidates: ' + json.dumps(candidates, ensure_ascii=False))
    return candidates[0]


def select_z1(log=print):
    summary = _load_summary('Z1OPT', 'z1')
    checkpoint = Path(DEFAULT_OUT) / 'checkpoints' / 'z1opt_z1.json'
    if summary and checkpoint.exists() and summary['final'] > 492:
        return dict(label='Z1OPT', routed=summary['final'],
                    checkpoint=str(checkpoint), summary=summary)
    base = Path(DEFAULT_OUT) / 'planes' / 'V2' / 'BASE' / 'z1' / 'routes.json'
    return dict(label='BASE', routed=492, checkpoint=None, history=str(base))


def write_best(log=print):
    z1 = select_z1(log=log)
    z2 = select_z2(log=log)
    out_root = Path(DEFAULT_OUT) / 'planes' / 'V2' / 'BEST'
    selections = {}
    chosen = {}
    for plane, selection in (('z1', z1), ('z2', z2)):
        if selection.get('checkpoint'):
            state = load_layout_from_checkpoint('V2', plane, selection['checkpoint'],
                                                log=log)
        else:
            state = LayoutState.from_history('V2', plane, selection['history'], log=log)
        out_dir = out_root / plane
        detail = dict(name=f'BEST_{selection["label"]}', algorithm='BEST',
                      crossing_policy='strict', generator='v2opt',
                      selected_from=selection['label'],
                      routed=len(state.accepted))
        state.write_plane(out_dir, 'BEST', detail, 'selected_best',
                          extra=dict(selection=selection))
        selections[plane] = dict(selection=selection, routed=len(state.accepted),
                                 out_dir=str(out_dir))
        chosen[plane] = len(state.accepted)
        log(f'BEST {plane}: {len(state.accepted)} routed <- {selection["label"]}')
    payload = dict(schema='four_side_1024_v2opt_best_selection_v1',
                   rule='z2: max routed among E1/E2/E3 (tie -> E3); '
                        'z1: Z1OPT if it strictly beats 492 else BASE',
                   z1=selections['z1'], z2=selections['z2'],
                   combined_routed=chosen['z1'] + chosen['z2'],
                   baseline_698=698,
                   delta_vs_698=chosen['z1'] + chosen['z2'] - 698)
    path = Path(DEFAULT_OUT) / 'best_selection.json'
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False),
                    encoding='utf-8')
    log(f'BEST combined: {chosen["z1"]} + {chosen["z2"]} = '
        f'{chosen["z1"] + chosen["z2"]}/1024 (baseline 698, delta '
        f'{chosen["z1"] + chosen["z2"] - 698:+d})')
    return payload


def main(argv=None):
    return write_best()


if __name__ == '__main__':
    raise SystemExit(main())

