"""V3-Huang configuration: frozen inputs, topology contract, process parameters.

The process numbers are the FSLW round's convention and are imported from
:mod:`four_side_1024.fslw.config` (this round does not change the process).
The V1/V2 and FSLW packages stay untouched; V3 has its own input module, port
loader, frames and candidate library.
"""
from __future__ import annotations

from pathlib import Path

from ..fslw import config as F

ROOT = Path(__file__).resolve().parents[2]          # OpticalWaveguideRouter2D
PROJECT = ROOT.parent

# ---------------------------------------------------------------- process
BOARD_MM = F.BOARD_MM
WIDTH_MM = F.WIDTH_MM
EDGE_GAP_MM = F.EDGE_GAP_MM
CLEARANCE_MM = F.CLEARANCE_MM
RADIUS_MM = F.RADIUS_MM
FIXED_RADIUS_40MM = F.FIXED_RADIUS_40MM
SAGITTA_MM = F.SAGITTA_MM
MIN_CROSS_ANGLE_DEG = F.MIN_CROSS_ANGLE_DEG
PROPAGATION_LOSS_DB_PER_CM = F.PROPAGATION_LOSS_DB_PER_CM
BEND_LOSS = F.BEND_LOSS
CROSSING_LOSS = F.CROSSING_LOSS
LEGACY_POLYMER_ESTIMATE = F.LEGACY_POLYMER_ESTIMATE
FIBER_COLUMN_PITCH_MM = F.FIBER_COLUMN_PITCH_MM
FIBER_ROW_PITCH_MM = F.FIBER_ROW_PITCH_MM
ROWS = F.ROWS
COLUMNS = F.COLUMNS
CONNECTORS_PER_SIDE = F.CONNECTORS_PER_SIDE
CONNECTOR_PITCH_MM = F.CONNECTOR_PITCH_MM
CONNECTOR_PITCH_STATUS = F.CONNECTOR_PITCH_STATUS
ENVELOPE_WIDTH_MM = F.ENVELOPE_WIDTH_MM
PLANE_Z_MM = F.PLANE_Z_MM
PLANE_NAME = dict(F.PLANE_NAME)
PLANE_ROW = dict(F.PLANE_ROW)
PORT_MODEL = F.PORT_MODEL
Z_TRANSITION = F.Z_TRANSITION
MANUFACTURING_CLAIM = F.MANUFACTURING_CLAIM

# ---------------------------------------------------------------- inputs
INPUT_DIR = ROOT / 'data/v3_huang'
CSV_PATH = INPUT_DIR / 'fiberBoard1024_huang_fiber_pairs.csv'
XLSX_PATH = INPUT_DIR / 'fiberBoard1024_huang_four_side_connectors.xlsx'
PROVENANCE_PATH = INPUT_DIR / 'PROVENANCE.json'
EXPECTED_CSV_SHA256 = '76d91316e0933a64b8c822fd541faa2bda571fdef97e49b64f75b55cf4a6cf23'
EXPECTED_XLSX_SHA256 = '4d285f5667fa922849b3371525944e12feca1dae1bc07c0d5cd40be3b38b32de'

TOPOLOGY = 'V3_Huang'

#: Connection-class contract (CSV is authoritative; these are validation targets).
EXPECTED = dict(
    connections=1024,
    relation_counts={'same': 448, 'opposite': 384, 'adjacent': 192},
    pair_counts={'NN': 112, 'SS': 112, 'EE': 112, 'WW': 112,
                 'NS': 192, 'EW': 192,
                 'NE': 48, 'NW': 48, 'ES': 48, 'SW': 48},
    connectors=64,
    fibers_per_connector=32,
    endpoints=2048,
    planes={'z1': dict(total=512, same=222, opposite=196, adjacent=94),
            'z2': dict(total=512, same=226, opposite=188, adjacent=98)},
)

PLANES = ('z1', 'z2')
ALGORITHMS = ('A', 'B', 'C', 'D')
RELATIONS = ('same', 'opposite', 'adjacent')
SAME_PAIRS = ('NN', 'SS', 'EE', 'WW')
OPPOSITE_PAIRS = ('NS', 'EW')
ADJACENT_PAIRS = ('NE', 'NW', 'ES', 'SW')

# ---------------------------------------------------------------- outputs
OUTPUT_ROOT = ROOT / 'outputs/four_side_1024_v3_huang_R40_gap30_abcd'
REPORT_PATH = PROJECT / 'docs/reports/four_side_1024_v3_huang_R40_gap30_abcd.md'

#: Reused FSLW revision that this round is compared against (descriptive only).
FSLW_BASELINE = dict(
    output_dir='outputs/four_side_1024_fslw_R40_gap30_abcd',
    report='docs/reports/four_side_1024_fslw_R40_gap30_abcd.md',
    note='R>=40 mm, 30 um edge gap, dual-height real 2x16; no same-side connections; '
         'candidate library lacks the V3 same-side U/hairpin/refold families, so routed '
         'counts are not directly comparable without a same-library control run',
)


def process_record(**overrides):
    record = dict(
        round='V3-Huang round 3 (same/opposite/adjacent mixed dual-height topology)',
        board_mm=[BOARD_MM, BOARD_MM],
        waveguide_width_mm=WIDTH_MM,
        min_edge_gap_mm=EDGE_GAP_MM,
        min_centerline_clearance_mm=CLEARANCE_MM,
        min_bend_radius_mm=RADIUS_MM,
        fixed_radius_40mm=FIXED_RADIUS_40MM,
        radius_note='all arcs are exactly R=40 mm (D56 fixed-radius family)',
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
        topology=TOPOLOGY,
        topology_contract=EXPECTED,
        relation_source='CSV column relation (never inferred from the row number)',
        plane_source='CSV source_row/target_row (row 1 -> z1, row 2 -> z2)',
        input_files=dict(csv=str(CSV_PATH), xlsx=str(XLSX_PATH),
                         csv_sha256=EXPECTED_CSV_SHA256,
                         xlsx_sha256=EXPECTED_XLSX_SHA256),
        manufacturing_claim=MANUFACTURING_CLAIM,
        historical_baseline=FSLW_BASELINE,
    )
    record.update(overrides)
    return record
