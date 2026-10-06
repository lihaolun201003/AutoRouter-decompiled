"""Tests for the reconstructed loss model.

The unit tests pin the thesis numbers (table 3-1, equation 3-18/3-19), and the
last test runs the whole 512-channel pipeline and checks the headline
reproduction.  Nothing here is mocked: the workbooks are the real ones under
``results/``.

    .venv\\Scripts\\python.exe -m pytest tests/test_loss_model.py -v
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

os.environ.setdefault("MPLBACKEND", "Agg")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import loss_model  # noqa: E402
import waveguide_calculator  # noqa: E402

RESULTS = ROOT / "results"


# --------------------------------------------------------------------------
# Thesis equations
# --------------------------------------------------------------------------


def test_straight_loss_100mm_is_half_db():
    """Thesis table 2-1: L0 = 0.05 dB/cm, so a 100 mm straight run loses 0.5 dB."""
    assert loss_model.PROPAGATION_LOSS_DB_PER_CM == 0.05
    assert loss_model.straight_loss_db(100.0) == pytest.approx(0.5)
    assert loss_model.straight_loss_db(10.0) == pytest.approx(0.05)


def test_bend_loss_90deg_r5():
    """Thesis table 3-1 lists 2.39 dB at R = 5 mm; the table is rounded."""
    exact = loss_model.bend_loss_90_db(5.0)
    assert exact == pytest.approx(2.39, abs=0.01)
    assert loss_model.bend_loss_db(5.0, 90.0) == pytest.approx(exact)


def test_bend_loss_45deg_is_half_of_90deg():
    """Equation 3-18: Lb = L90 * theta / 90, so 45 degrees is half."""
    assert loss_model.bend_loss_db(5.0, 45.0) == pytest.approx(2.39 / 2, abs=0.005)
    assert loss_model.bend_loss_db(5.0, 45.0) == pytest.approx(
        loss_model.bend_loss_90_db(5.0) / 2
    )


def test_two_90deg_bends_r5():
    """Equation 3-19 puts two bends on a typical route: 2 * Lb."""
    pair = 2 * loss_model.bend_loss_db(5.0, 90.0)
    assert pair == pytest.approx(4.78, abs=0.02)


def test_thesis_bend_table_3_1_is_reproduced():
    """Every published table row comes out of the recovered density ratio."""
    for radius, published in loss_model.THESIS_BEND_LOSS_90_DB.items():
        assert loss_model.bend_loss_90_db(radius) == pytest.approx(
            published, abs=0.01
        )


def test_arc_length_form_equals_angle_form():
    """``arc * density`` and ``L90 * theta/90`` are the same quantity.

    The original program integrates over radian intervals; the thesis writes the
    per-angle form.  They must agree, or the reconstruction would double count
    arc length in one of them.
    """
    for radius in loss_model.BEND_TABLE_RADII_MM:
        arc = radius * math.pi / 2
        assert loss_model.bend_loss_from_arc_db(radius, arc) == pytest.approx(
            loss_model.bend_loss_db(radius, 90.0)
        )


def test_unknown_radius_and_angle_are_errors_not_guesses():
    with pytest.raises(loss_model.LossModelError):
        loss_model.bend_loss_90_db(7.0)
    with pytest.raises(loss_model.LossModelError):
        loss_model.crossing_loss_db(0.0, {90: 0.05})
    with pytest.raises(loss_model.LossModelError):
        loss_model.crossing_loss_db(90.0, {})


def test_crossing_table_is_anchored_to_the_thesis_stated_value():
    """The digitised curve's shape is kept, its level is pinned by the text.

    The thesis says 30 crossings at 90 degrees cost about 0.05 dB, and the
    original code divides the stored value by 30.
    """
    table = loss_model.load_crossing_table()
    assert loss_model.crossing_loss_db(90.0, table) == pytest.approx(0.05 / 30)
    assert loss_model.crossing_loss_db(90.0, table) * 30 == pytest.approx(0.05)


def test_crossing_loss_is_larger_at_shallow_angles():
    """Figure 3-12 only falls away near 0 and 180 degrees.

    This is the one qualitative claim the digitised table is allowed to carry
    into the model, so it is asserted rather than assumed.
    """
    table = loss_model.load_crossing_table()
    assert table[20] > table[90]
    assert table[160] > table[90]


# --------------------------------------------------------------------------
# Legacy plumbing
# --------------------------------------------------------------------------


def test_calc_loss_sign_and_legacy_accumulation_order():
    """``calc_loss`` keeps the legacy negative sign; the loss is its negation.

    Built by hand from one straight run and one 90 degree arc pair so the test
    does not depend on any routed workbook.
    """
    radius = 5.0
    length = 100.0 + radius * math.pi  # straight part + two quarter arcs
    row = pd.Series(
        {
            "length": length,
            "theta": [(0.0, math.pi / 2), (math.pi / 2, math.pi)],
            "angles": [],
            "Port1": 1,
            "Port2": 2,
        }
    )
    table = loss_model.load_crossing_table()
    value = -waveguide_calculator.legacy_signed_loss(
        row["length"], row["theta"], row["angles"], radius, table
    )

    expected = loss_model.bend_loss_90_db(radius) * 2 + loss_model.straight_loss_db(
        100.0
    )
    assert value == pytest.approx(expected)


def test_a_crossing_adds_loss_in_both_code_paths():
    """Crossings must increase the total, and the two paths must agree.

    The original ``calc_loss`` added the stored ``loss_db`` value unchanged, so
    the stored column had to be negative -- the same "negative means loss"
    convention as ``tl`` and the ``-0.005`` straight coefficient.  A positive
    table would have made crossings *reduce* the total, worth 0.64 dB of mean
    loss on the 512-channel board and enough to miss the thesis' 5.5 dB.
    """
    radius = 5.0
    theta = [(0.0, math.pi / 2), (math.pi / 2, math.pi)]
    table = loss_model.load_crossing_table()
    length = 200.0 + radius * math.pi

    without = -waveguide_calculator.legacy_signed_loss(
        length, theta, [], radius, table
    )
    with_crossing = -waveguide_calculator.legacy_signed_loss(
        length, theta, [90, 90], radius, table
    )
    assert with_crossing > without
    assert with_crossing - without == pytest.approx(2 * 0.05 / 30)

    by_model = loss_model.route_loss_from_geometry(
        route_id=0,
        port1=1,
        port2=2,
        bend_radius_mm=radius,
        total_length_mm=length,
        theta_intervals=theta,
        crossing_angles=[90, 90],
        table=table,
    )
    assert by_model.total_loss_db == pytest.approx(with_crossing)


def test_calc_index_returns_one_angle_list_per_route():
    """The non-debug path returns ``points`` instead of falling off the end.

    decompyle3 moved the whole body of ``calc_crossing`` inside the DEBUG gate,
    which turned it into a function that returned ``None`` and made
    ``calc_index`` raise ``TypeError`` on ``len(None)`` for every route.  The
    recovered bytecode shows only the early exit is gated.
    """
    source = Path(waveguide_calculator.__file__).read_text(encoding="utf-8")
    marker = "if os.getenv(\"DEBUG\") == \"True\":\n            if row.name != 56:\n                return []"
    assert marker in source, "calc_crossing's DEBUG gate no longer covers only the early exit"
    assert "return points" in source


# --------------------------------------------------------------------------
# Thesis reproduction
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def routed_512():
    return pd.read_excel(RESULTS / "fiberBoard512bend.xlsx")


def test_512_summary_reproduces_the_thesis(routed_512):
    """512 channels, R = 5 mm: thesis reports 5.5 dB mean and 6.6 dB maximum."""
    table = loss_model.load_crossing_table()
    result = waveguide_calculator.calc_index(
        routed_512.copy(), table, 0.05, 5.0, file_name=None
    )
    losses = [
        loss_model.route_loss_from_geometry(
            route_id=int(row.name),
            port1=int(row["Port1"]),
            port2=int(row["Port2"]),
            bend_radius_mm=5.0,
            total_length_mm=float(row["length"]),
            theta_intervals=row["theta"],
            crossing_angles=row["angles"],
            table=table,
        )
        for _, row in result.iterrows()
    ]
    stats = loss_model.summarise(losses)

    assert len(losses) == 512
    assert stats["loss_db_mean"] == pytest.approx(5.5, abs=0.1)
    assert stats["loss_db_max"] == pytest.approx(6.6, abs=0.15)

    # Bend loss dominates, straight loss is second, crossings contribute least:
    # the ordering the thesis conclusion states.
    assert stats["bend_loss_db_mean"] > stats["straight_loss_db_mean"]
    assert stats["straight_loss_db_mean"] > stats["crossing_loss_db_mean"]
    assert stats["bend_loss_db_mean"] / stats["loss_db_mean"] > 0.75

    # The published summary file must agree with a fresh computation.
    stored = json.loads(
        (RESULTS / "fiberBoard512_loss_summary.json").read_text(encoding="utf-8")
    )
    assert stored["mean_loss_db"] == pytest.approx(stats["loss_db_mean"])
    assert stored["max_loss_db"] == pytest.approx(stats["loss_db_max"])
