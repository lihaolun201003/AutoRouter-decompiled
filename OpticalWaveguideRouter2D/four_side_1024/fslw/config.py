"""Process parameters for the femtosecond-laser-written (FSLW) R>=40 mm experiment.

Every other module in :mod:`four_side_1024.fslw` must read the geometry numbers from
here instead of hard-coding them.  The values are the *experiment convention* of this
round (see ``fslw/SPEC.md``): they are not yet confirmed fabrication parameters.
"""
from __future__ import annotations

BOARD_MM = 150.0
WIDTH_MM = 0.050
EDGE_GAP_MM = 0.030
CLEARANCE_MM = WIDTH_MM + EDGE_GAP_MM          # 0.080 mm centreline clearance
RADIUS_MM = 40.0
FIXED_RADIUS_40MM = True                       # every arc is exactly 40.0 mm
SAGITTA_MM = 0.0005
MIN_CROSS_ANGLE_DEG = 5.0
PROPAGATION_LOSS_DB_PER_CM = 0.05

#: Bend loss and crossing loss are NOT known for this glass process.  They are
#: deliberately absent instead of being replaced by the legacy polymer model.
BEND_LOSS = dict(status='unknown_uncalibrated',
                  note='no femtosecond-laser-written glass bend-loss function is known; '
                       'R=40 mm is a geometry constraint only, not a measured loss value')
CROSSING_LOSS = dict(status='unknown_uncalibrated',
                     note='single-layer crossing optical feasibility not confirmed; '
                          'crossing count is a geometric metric only')
LEGACY_POLYMER_ESTIMATE = dict(available=True, status='legacy_estimate',
                               note='the previous polymer bend-loss model may be quoted '
                                    'for comparison only, never as glass truth')

#: Interface model (IEC 61754-7-3:2019 2x16 MPO) used this round.
FIBER_COLUMN_PITCH_MM = 0.250
FIBER_ROW_PITCH_MM = 0.500
ROWS = 2
COLUMNS = 16
CONNECTORS_PER_SIDE = 16
CONNECTOR_PITCH_MM = 9.0
CONNECTOR_PITCH_STATUS = 'provisional; full MPO housing interference at 9 mm pitch unresolved'
ENVELOPE_WIDTH_MM = 12.59

#: Dual-height assumption: row 1 lives at z1, row 2 at z2, 0.5 mm apart.
PLANE_Z_MM = {1: 0.0, 2: 0.5}
PLANE_NAME = {1: 'z1', 2: 'z2'}
PLANE_ROW = {'z1': 1, 'z2': 2}
PORT_MODEL = 'real_2x16_dual_height'
Z_TRANSITION = 'not_implemented'
MANUFACTURING_CLAIM = ('simulation under the two-height interface assumption; '
                       'glass thickness and connector mounting direction are not '
                       'confirmed, no z transition is implemented, not a claim of '
                       'manufacturability')

#: Historical model of the previous round (kept only as an external baseline).
LEGACY_VIRTUAL_MODEL = dict(endpoint_mode='virtual_unfolded',
                            virtual_port_pitch_mm=0.175, radius_mm=5.0,
                            edge_gap_mm=0.125, clearance_mm=0.175,
                            output_dir='outputs/four_side_1024_v1_v2_abcd')

#: Sensitivity matrix (Phase 11): same representative topology+algorithm, four configs.
SENSITIVITY_CONFIGS = (
    dict(name='O_legacy_R5_gap125', radius_mm=5.0, edge_gap_mm=0.125),
    dict(name='G_gap30_R5', radius_mm=5.0, edge_gap_mm=0.030),
    dict(name='R_R40_gap125', radius_mm=40.0, edge_gap_mm=0.125),
    dict(name='N_R40_gap30', radius_mm=40.0, edge_gap_mm=0.030),
)


def clearance(edge_gap_mm=None, width_mm=None):
    width = WIDTH_MM if width_mm is None else float(width_mm)
    gap = EDGE_GAP_MM if edge_gap_mm is None else float(edge_gap_mm)
    return width + gap


def process_record(**overrides):
    """JSON-ready process/config record embedded in every artifact."""
    record = dict(
        board_mm=[BOARD_MM, BOARD_MM],
        waveguide_width_mm=WIDTH_MM,
        min_edge_gap_mm=EDGE_GAP_MM,
        min_centerline_clearance_mm=CLEARANCE_MM,
        min_bend_radius_mm=RADIUS_MM,
        fixed_radius_40mm=FIXED_RADIUS_40MM,
        radius_note='all arcs are exactly R=40 mm (D56 fixed-radius family); '
                    'this is not a search over all R>=40 mm geometries',
        propagation_loss_db_per_cm=PROPAGATION_LOSS_DB_PER_CM,
        bend_loss=BEND_LOSS,
        crossing_loss=CROSSING_LOSS,
        legacy_polymer_estimate=LEGACY_POLYMER_ESTIMATE,
        sagitta_mm=SAGITTA_MM,
        min_cross_angle_deg=MIN_CROSS_ANGLE_DEG,
        interface_standard=dict(name='IEC 61754-7-3:2019 2x16 MPO',
                                fiber_column_pitch_mm=FIBER_COLUMN_PITCH_MM,
                                fiber_row_pitch_mm=FIBER_ROW_PITCH_MM,
                                rows=ROWS, columns=COLUMNS,
                                connectors_per_side=CONNECTORS_PER_SIDE,
                                connector_pitch_mm=CONNECTOR_PITCH_MM,
                                connector_pitch_status=CONNECTOR_PITCH_STATUS),
        port_model=PORT_MODEL,
        plane_z_mm={str(row): z for row, z in PLANE_Z_MM.items()},
        plane_row=PLANE_ROW,
        z_transition=Z_TRANSITION,
        layer=0,
        routing_layers_per_plane=1,
        planes=2,
        manufacturing_claim=MANUFACTURING_CLAIM,
        historical_baseline=LEGACY_VIRTUAL_MODEL,
    )
    record.update(overrides)
    return record
