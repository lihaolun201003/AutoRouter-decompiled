"""Configuration of the V2 five-layer (2.5D) experiment.

This round keeps the frozen V2 geometry/process parameters and adds a vertical
stack of routing heights between the two real interface heights z=0 and z=0.5 mm.
The 2.5D model is deliberately simple and auditable:

* every route keeps its 2D XY path from one of the two accepted 2D layouts
  (scheme A = D56 with short-S, scheme B = pure orthogonal 90 deg);
* a route either stays flat at its interface layer or climbs in one smooth
  S-curve to an intermediate "travel" layer, propagates there and descends in a
  second S-curve before reaching its target port;
* the S-curve is two circular arcs of radius R=40 mm in the vertical plane, so
  the complete 3D path is G1-continuous with minimum curvature radius 40 mm;
* clearance is checked in true 3D (>= 0.08 mm centerline distance).
"""
from __future__ import annotations

from pathlib import Path

from ..fslw import config as C

ROOT = Path(__file__).resolve().parents[2]
OUTPUTS = ROOT / 'outputs'
V25D_ROOT = OUTPUTS / 'four_side_1024_v2_25d_v01'

SCHEMES = {
    'A': dict(
        name='A',
        label='A_shortS',
        description='D56 with short-S (baseline V2-BEST 752/1024)',
        baseline_root=OUTPUTS / 'four_side_1024_v2_candidate_rr_v01',
        baseline_algorithm='BEST',
        baseline_routed=752,
        xy_model='d56',
    ),
    'B': dict(
        name='B',
        label='B_ortho90',
        description='pure orthogonal 90 deg (baseline 262/1024)',
        baseline_root=OUTPUTS / 'four_side_1024_v2_ortho90_v01',
        baseline_algorithm='ORTHO90',
        baseline_routed=262,
        xy_model='ortho90',
    ),
}

LAYER_STACKS = {3: (0.0, 0.25, 0.5), 5: (0.0, 0.125, 0.25, 0.375, 0.5)}
PLANES = ('z1', 'z2')
INTERFACE_LAYER = {3: {'z1': 0, 'z2': 2}, 5: {'z1': 0, 'z2': 4}}

BOARD_MM = C.BOARD_MM
HALF_WIDTH_MM = C.WIDTH_MM / 2.0
RADIUS_MM = C.RADIUS_MM
CLEARANCE_MM = C.CLEARANCE_MM
EDGE_GAP_MM = C.EDGE_GAP_MM
WIDTH_MM = C.WIDTH_MM
MIN_CROSS_ANGLE_DEG = C.MIN_CROSS_ANGLE_DEG
SAGITTA_MM = C.SAGITTA_MM
CROSSING_POLICY = 'strict'

# transition margins (mm) along the 2D path
PORT_MARGIN_MM = 1.2          # keep the port stretch flat near the port
SEGMENT_MARGIN_MM = 0.25      # margin inside the straight segment hosting a transition
MIN_TRAVEL_MM = 8.0           # minimum flat run at the travel layer (otherwise not "lifted")
TRANSITION_STEP_MM = 0.05     # sampling step of a transition curve (routing checks)
ROUTE_STEP_MM = 0.20          # sampling step of flat parts (routing clearance checks)
# 3D clearance tolerance (routing decision); the independent validator re-checks
CLEARANCE_3D = CLEARANCE_MM


def stack(n_layers):
    if int(n_layers) not in LAYER_STACKS:
        raise ValueError(f'layers must be one of {sorted(LAYER_STACKS)}')
    return LAYER_STACKS[int(n_layers)]


def interface_layer(n_layers, plane):
    return INTERFACE_LAYER[int(n_layers)][plane]


def travel_layers(n_layers, plane):
    """Layers a route of ``plane`` may use as its flat travel layer."""
    count = int(n_layers)
    base = interface_layer(count, plane)
    return [layer for layer in range(1, count - 1) if layer != base]


def transition_footprint(dz_mm, radius=RADIUS_MM):
    """Horizontal advance of the two-arc S-curve that changes height by ``dz``."""
    dz = abs(float(dz_mm))
    if dz <= 0.0:
        return 0.0
    ratio = 1.0 - dz / (2.0 * radius)
    if ratio <= -1.0:
        raise ValueError('height change too large for the given radius')
    theta = __import__('math').acos(max(-1.0, min(1.0, ratio)))
    return 2.0 * radius * __import__('math').sin(theta)


def run_dir(scheme, n_layers):
    return V25D_ROOT / f'scheme{scheme}' / f'layers{n_layers}'


def baseline_plane_routes(scheme, plane):
    spec = SCHEMES[scheme]
    path = (spec['baseline_root'] / 'planes' / 'V2' / spec['baseline_algorithm']
            / plane / 'routes.json')
    if not path.exists():
        raise FileNotFoundError(path)
    return path
