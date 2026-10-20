"""Corrected L1–L5 physical layer model (2026-10-20 R9).

The old 2.5D model identified the two 2x16 MPO port rows with two *different*
routing layers (``z1 -> layer 0 / z=0`` and ``z2 -> layer 4 / z=0.5``) and put the
extra layers between them.  That is physically wrong.  The correct structure is:

* **L1** is the interface routing layer.  BOTH port rows belong to L1:
  - ``z1`` row: physical height 0.0 mm,
  - ``z2`` row: physical height 0.5 mm,
  - each row has 16 columns at 0.25 mm pitch.
* **L2 .. L5** are four additional routing layers.  Their physical heights are
  **not confirmed** by the supervisor; they are configurable simulation inputs and
  carry the ``unconfirmed_simulation`` provenance.  A stack with unconfirmed
  heights must never be reported as a formally accepted process condition.

This module keeps four concepts strictly separate:

1. port *logical routing layer* (always L1 for the interface),
2. port *physical height* (0.0 or 0.5 mm depending on the row),
3. waveguide *current physical height* (``z_mm`` of a flat part / transition end),
4. waveguide *current logical routing layer* (``layer_id`` of a flat part).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

INTERFACE_LAYER_ID = 1
ROUTING_LAYER_IDS = (2, 3, 4, 5)
INTERFACE_ROWS = {'z1': 0.0, 'z2': 0.5}
PLANES = ('z1', 'z2')
PROVENANCE_UNCONFIRMED = 'unconfirmed_simulation'
PROVENANCE_CONFIRMED = 'confirmed'
PROVENANCE_VALUES = (PROVENANCE_UNCONFIRMED, PROVENANCE_CONFIRMED)

#: exploratory L2..L5 height presets (mm).  These are NOT process parameters.
STACK_PRESETS = {
    # 0.5 mm spacing above the top interface row (z2 = 0.5)
    'medium_050': dict(L2=1.0, L3=1.5, L4=2.0, L5=2.5,
                       note='0.5 mm spacing above the top interface row; exploratory'),
    # compact 0.25 mm spacing above z2 (smallest above the frozen 0.08 mm clearance)
    'compact_025': dict(L2=0.75, L3=1.0, L4=1.25, L5=1.5,
                        note='0.25 mm spacing; minimum-clearance exploratory stack'),
    # wide 1.0 mm spacing
    'wide_100': dict(L2=1.5, L3=2.5, L4=3.5, L5=4.5,
                     note='1.0 mm spacing; exploratory'),
}


def _clearance_mm():
    from ..fslw import config as C
    return float(C.CLEARANCE_MM)


@dataclass(frozen=True)
class LayerGeometry:
    layer_id: int
    layer_type: str                       # 'interface' | 'routing'
    physical_z_mm: Optional[float] = None
    interface_rows: Dict[str, float] = field(default_factory=dict)
    allowed_transitions: Tuple[int, ...] = ()

    @property
    def is_interface(self):
        return self.layer_type == 'interface'

    def z_for_row(self, row):
        if not self.is_interface:
            raise TypeError(f'layer {self.layer_id} is not an interface layer')
        if row not in self.interface_rows:
            raise KeyError(f'unknown interface row {row!r}')
        return float(self.interface_rows[row])

    def to_dict(self):
        return dict(layer_id=int(self.layer_id), layer_type=self.layer_type,
                    physical_z_mm=(None if self.physical_z_mm is None
                                   else round(float(self.physical_z_mm), 9)),
                    interface_rows={key: round(float(value), 9)
                                    for key, value in sorted(self.interface_rows.items())},
                    allowed_transitions=[int(value) for value in self.allowed_transitions])


@dataclass
class LayerStack:
    """Ordered L1..L5 layer geometry with explicit provenance/validation."""

    layers: Dict[int, LayerGeometry]
    provenance: str = PROVENANCE_UNCONFIRMED
    note: str = ''

    def validate(self):
        clearance = _clearance_mm()
        if self.provenance not in PROVENANCE_VALUES:
            raise ValueError(f'invalid provenance {self.provenance!r}')
        if set(self.layers) != {INTERFACE_LAYER_ID, *ROUTING_LAYER_IDS}:
            raise ValueError('layer stack must contain exactly layer ids 1..5')
        interface = self.layers[INTERFACE_LAYER_ID]
        if not interface.is_interface:
            raise ValueError('layer 1 must be the interface layer')
        if interface.physical_z_mm is not None:
            raise ValueError('interface layer L1 has rows, not a single physical z')
        if {key: float(value) for key, value in interface.interface_rows.items()} != INTERFACE_ROWS:
            raise ValueError(f'L1 interface rows must be exactly {INTERFACE_ROWS}')
        heights = []
        for layer_id in ROUTING_LAYER_IDS:
            layer = self.layers[layer_id]
            if layer.layer_type != 'routing':
                raise ValueError(f'layer {layer_id} must be a routing layer')
            if layer.physical_z_mm is None:
                raise ValueError(f'layer {layer_id} has no physical height')
            height = float(layer.physical_z_mm)
            if height != height or height in (float('inf'), float('-inf')):
                raise ValueError(f'layer {layer_id} physical height is not finite')
            heights.append((layer_id, height))
        ordered = sorted(heights, key=lambda item: item[1])
        for (id_a, z_a), (id_b, z_b) in zip(ordered, ordered[1:]):
            if z_b - z_a <= clearance:
                raise ValueError(
                    f'physical planes L{id_a}={z_a:g} and L{id_b}={z_b:g} are '
                    f'closer than the {clearance:g} mm clearance')
        # interface rows versus routing layers
        for row, z_row in INTERFACE_ROWS.items():
            for layer_id, z_layer in heights:
                if abs(z_layer - z_row) <= clearance:
                    raise ValueError(
                        f'L{layer_id}={z_layer:g} is closer than clearance to '
                        f'interface row {row}={z_row:g}')
        all_ids = [INTERFACE_LAYER_ID, *ROUTING_LAYER_IDS]
        for layer_id in all_ids:
            allowed = set(int(value) for value in self.layers[layer_id].allowed_transitions)
            if layer_id not in allowed:
                raise ValueError(f'layer {layer_id} must allow a transition to itself')
            if allowed - set(all_ids):
                raise ValueError(f'layer {layer_id} allows unknown layers')
            for other in allowed:
                other_allowed = set(
                    int(value) for value in self.layers[other].allowed_transitions)
                if layer_id not in other_allowed:
                    raise ValueError(f'asymmetric allowed_transitions {layer_id} <-> {other}')
        return self

    # -- convenience -------------------------------------------------------
    @property
    def interface(self):
        return self.layers[INTERFACE_LAYER_ID]

    @property
    def routing_layers(self):
        return [self.layers[layer_id] for layer_id in ROUTING_LAYER_IDS]

    @property
    def formal_acceptance_allowed(self):
        return (self.provenance == PROVENANCE_CONFIRMED
                and all(layer.physical_z_mm is not None
                        for layer in self.routing_layers))

    def z_for_layer(self, layer_id, row=None):
        layer = self.layers[int(layer_id)]
        if layer.is_interface:
            if row is None:
                raise ValueError('interface layer L1 needs a row (z1/z2)')
            return layer.z_for_row(row)
        return float(layer.physical_z_mm)

    def z_sequence_for(self, layer_sequence, row):
        return [self.z_for_layer(layer_id, row=row) for layer_id in layer_sequence]

    def physical_planes(self):
        planes = [(INTERFACE_LAYER_ID, row, value)
                  for row, value in sorted(INTERFACE_ROWS.items())]
        planes += [(layer.layer_id, None, float(layer.physical_z_mm))
                   for layer in self.routing_layers]
        return planes

    def to_dict(self):
        return dict(
            schema='four_side_1024_v2_l3d_layer_stack_v1',
            provenance=self.provenance,
            formal_acceptance_allowed=bool(self.formal_acceptance_allowed),
            note=self.note,
            interface_layer=INTERFACE_LAYER_ID,
            layers={str(layer_id): self.layers[layer_id].to_dict()
                    for layer_id in sorted(self.layers)},
            routing_heights_mm={str(layer_id): round(float(self.layers[layer_id].physical_z_mm), 9)
                                for layer_id in ROUTING_LAYER_IDS},
        )

    def write(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=1, ensure_ascii=False) + '\n',
                        encoding='utf-8')
        return path


def _allowed_transitions():
    ids = [INTERFACE_LAYER_ID, *ROUTING_LAYER_IDS]
    return {layer_id: tuple(ids) for layer_id in ids}


def build_stack(name='medium_050', heights=None, provenance=PROVENANCE_UNCONFIRMED,
                note=None):
    """Build (and validate) a LayerStack from a preset name or explicit heights."""
    if heights is None:
        if name not in STACK_PRESETS:
            raise ValueError(f'unknown stack preset {name!r}')
        preset = STACK_PRESETS[name]
        heights = {layer_id: preset[f'L{layer_id}'] for layer_id in ROUTING_LAYER_IDS}
        note = note or preset['note']
        stack_name = name
    else:
        heights = {int(int(key[1:]) if isinstance(key, str) and key.upper().startswith('L')
                       else int(key)): float(value) for key, value in heights.items()}
        stack_name = name or 'custom'
        note = note or 'explicitly configured exploratory heights'
    allowed = _allowed_transitions()
    layers = {INTERFACE_LAYER_ID: LayerGeometry(
        INTERFACE_LAYER_ID, 'interface', None, dict(INTERFACE_ROWS),
        allowed[INTERFACE_LAYER_ID])}
    for layer_id in ROUTING_LAYER_IDS:
        layers[layer_id] = LayerGeometry(
            layer_id, 'routing', float(heights[layer_id]), {},
            allowed[layer_id])
    stack = LayerStack(layers=layers, provenance=provenance,
                       note=f'{stack_name}: {note}')
    stack.validate()
    stack.name = stack_name  # type: ignore[attr-defined]
    return stack


def load_stack(path_or_payload):
    """Load a previously written layer stack JSON/dict (must still validate)."""
    if isinstance(path_or_payload, dict):
        payload = path_or_payload
        source_name = str(payload.get('schema', 'layer_stack'))
    else:
        payload = json.loads(Path(path_or_payload).read_text(encoding='utf-8'))
        source_name = str(path_or_payload)
    layers = {}
    for key, value in payload['layers'].items():
        layers[int(key)] = LayerGeometry(
            layer_id=int(value['layer_id']),
            layer_type=value['layer_type'],
            physical_z_mm=(None if value.get('physical_z_mm') is None
                           else float(value['physical_z_mm'])),
            interface_rows={name: float(z) for name, z in
                            (value.get('interface_rows') or {}).items()},
            allowed_transitions=tuple(int(v) for v in value.get('allowed_transitions') or ()))
    stack = LayerStack(layers=layers,
                       provenance=payload.get('provenance', PROVENANCE_UNCONFIRMED),
                       note=payload.get('note', ''))
    stack.validate()
    stack.name = payload.get('name', Path(source_name).stem)  # type: ignore[attr-defined]
    return stack


def plan_sequences(stage='single', include_back_to_back=True):
    """Return exploratory layer sequences (logical ids) for the router.

    ``single``: L1 -> Lk -> L1; ``multi``: additionally Li/Lj/Lk combinations.
    """
    sequences = [[INTERFACE_LAYER_ID, layer_id, INTERFACE_LAYER_ID]
                 for layer_id in ROUTING_LAYER_IDS]
    if stage == 'single':
        return sequences
    routing = list(ROUTING_LAYER_IDS)
    pairs = [[INTERFACE_LAYER_ID, a, b, INTERFACE_LAYER_ID]
             for a in routing for b in routing if a != b]
    triples = [
        [1, 2, 3, 1], [1, 3, 2, 1], [1, 2, 4, 1], [1, 4, 2, 1],
        [1, 3, 4, 1], [1, 4, 3, 1], [1, 2, 5, 1], [1, 5, 2, 1],
        [1, 3, 5, 1], [1, 5, 3, 1], [1, 4, 5, 1], [1, 5, 4, 1],
        [1, 2, 3, 5, 1], [1, 5, 3, 2, 1], [1, 2, 4, 5, 1], [1, 5, 4, 2, 1],
    ]
    if stage == 'multi':
        return sequences + pairs + triples
    return sequences
