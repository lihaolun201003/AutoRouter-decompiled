"""Loss model of the legacy AutoRouter, reconstructed from the thesis.

Model (thesis section 3.3.2, equation 3-19)::

    Lt = Lb * 2 + L0 * ls + sum(Lc)

with ``Lb`` the loss of one bend (``Lb = L90 * theta / 90`` for a bend of
``theta`` degrees, equation 3-18), ``L0 = 0.05 dB/cm`` the straight-waveguide
loss (thesis table 2-1) and ``Lc`` the extra insertion loss of one crossing.

The reconstruction follows the *original implementation* inside
``waveguide_calculator.calc_loss`` byte-for-byte.  Two details of that code are
easy to get wrong and are preserved here:

* the tables ``tl``/``ll`` hold the raw laboratory measurement as a *total loss*
  over a *reference length*; the model uses their ratio
  ``bend_loss = tl[i] / ll[i]`` as a per-millimetre figure, both negative
  because the legacy program accumulated transmission, not loss.  Multiply the
  ratio by ``R*pi/2`` and the thesis bend table 3-1 falls out exactly:
  ``2.8/9.23 * 5*pi/2 = 2.383 dB`` against a published 2.39 dB.
* ``calc_loss`` walks ``x.theta`` (radian intervals) and adds
  ``(t1 - t0) * R * (bend_loss - straight_loss)``, then adds
  ``length * straight_loss`` for the *whole* path.  Expanding that gives
  ``arc_length * bend_density + straight_length * L0`` -- algebraically the
  thesis equation, because ``L90 * theta/90`` equals ``arc_length * density``.
  No arc length is counted twice.

Crossings are summed without de-duplication, which is what the original code
does: ``calc_crossing`` visits every waveguide against every other waveguide, so
each physical crossing contributes twice.  The thesis says the duplicates
"need to be removed when compiling statistics", but its reported 5.3/5.5/9.8 dB
are reproduced by the un-deduplicated sum, so the shipped code is what the
published numbers came from.

The crossing loss table itself was an external workbook that was never shipped;
see ``load_crossing_table`` for what is used instead.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from math import pi
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CROSSING_TABLE = PROJECT_ROOT / "data" / "crossing_loss_from_thesis_fig3_12.csv"

# Thesis table 2-1: straight-waveguide loss, 0.05 dB/cm.
PROPAGATION_LOSS_DB_PER_CM = 0.05
PROPAGATION_LOSS_DB_PER_MM = PROPAGATION_LOSS_DB_PER_CM / 10.0

# The tables compiled into the original ``calc_loss``.  ``tl`` is the measured
# total loss and ``ll`` the reference length it was measured over; the list
# position indexes the bend radius.  Radii 2..6 are the ones the thesis quotes
# in table 3-1.
BEND_TABLE_RADII_MM = (2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 15.0)
BEND_TABLE_TOTAL_LOSS_DB = (-16.0, -10.59, -6.08, -2.8, -2.03, -1.39, -0.87, -0.45)
BEND_TABLE_REFERENCE_LENGTH_MM = (6.33, 7.33, 8.33, 9.23, 10.05, 11.53, 12.92, 15.74)

#: Thesis table 3-1, for reference and for the unit tests.  Every entry equals
#: ``bend_loss_density * R * pi / 2`` to within the published rounding.
THESIS_BEND_LOSS_90_DB = {2.0: 7.94, 3.0: 6.81, 4.0: 4.59, 5.0: 2.39, 6.0: 1.90}

#: The thesis states that at 90 degrees, 30 crossings cost about 0.05 dB.
THESIS_CROSSING_ANCHOR_DB = 0.05
THESIS_CROSSING_ANCHOR_ANGLE_DEG = 90
THESIS_CROSSING_ANCHOR_COUNT = 30


class LossModelError(ValueError):
    """Raised for inputs the reconstructed model cannot evaluate."""


def bend_loss_density_db_per_mm(radius_mm: float) -> float:
    """Bend propagation loss per millimetre of arc, as a positive dB/mm value.

    ``tl / ll`` is negative in the original source (it stores transmission);
    the sign is flipped here so every loss in this module is a positive number.
    """
    try:
        index = BEND_TABLE_RADII_MM.index(float(radius_mm))
    except ValueError:
        raise LossModelError(
            "no bend loss measurement for radius %r mm; the original table has %s"
            % (radius_mm, list(BEND_TABLE_RADII_MM))
        ) from None
    return -BEND_TABLE_TOTAL_LOSS_DB[index] / BEND_TABLE_REFERENCE_LENGTH_MM[index]


def bend_loss_90_db(radius_mm: float) -> float:
    """Loss of a 90 degree bend: ``density * R * pi/2`` (thesis table 3-1)."""
    return bend_loss_density_db_per_mm(radius_mm) * radius_mm * pi / 2.0


def bend_loss_db(radius_mm: float, angle_deg: float) -> float:
    """Loss of a bend of ``angle_deg`` degrees: ``L90 * theta / 90`` (eq. 3-18)."""
    if angle_deg < 0:
        raise LossModelError("bend angle must not be negative")
    return bend_loss_90_db(radius_mm) * angle_deg / 90.0


def bend_loss_from_arc_db(radius_mm: float, arc_length_mm: float) -> float:
    """Loss of an arc of ``arc_length_mm``; equals :func:`bend_loss_db`.

    ``arc = R * theta_rad`` and ``L90 = R*pi/2 * density``, so
    ``arc * density`` and ``L90 * theta_deg/90`` are the same quantity.  The
    original program uses the first form; this function exposes it directly.
    """
    if arc_length_mm < 0:
        raise LossModelError("arc length must not be negative")
    return bend_loss_density_db_per_mm(radius_mm) * arc_length_mm


def straight_loss_db(length_mm: float) -> float:
    """``L0 * ls`` for a straight section measured in millimetres."""
    if length_mm < 0:
        raise LossModelError("straight length must not be negative")
    return length_mm * PROPAGATION_LOSS_DB_PER_MM


def load_crossing_table(path: Path | str | None = None) -> dict[int, float]:
    """Return ``{angle_deg: loss_db_of_30_crossings}``.

    **The original table does not exist.**  ``calc_loss`` read it from a
    workbook passed in by the caller; no such workbook was packaged with
    ``AutoRouter.exe``, appears anywhere on the original media, or is referenced
    by the decompiled sources.  What is used instead is a digitisation of the
    thesis' own Figure 3-12 (cross number 30 curve), rescaled so that its 90
    degree value matches the 0.05 dB/30 figure the thesis states in words
    (section 3.3.2).

    That anchoring matters: pixels are calibrated to about 0.01 dB, while the
    published curve's ripple is around 0.1 dB, so the absolute level of a raw
    digitisation is not trustworthy.  The shape is; the thesis' stated anchor
    pins the level.  This is an approximation digitised from thesis Figure
    3-12, not the original simulation data.
    """
    source = Path(path) if path is not None else DEFAULT_CROSSING_TABLE
    raw: dict[int, float] = {}
    with source.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            raw[int(row["angle_deg"])] = float(row["loss_db_per_30_crossings"])
    if not raw:
        raise LossModelError("crossing loss table %s is empty" % source)
    anchor = raw.get(THESIS_CROSSING_ANCHOR_ANGLE_DEG)
    if not anchor:
        raise LossModelError(
            "crossing loss table %s has no %d degree anchor"
            % (source, THESIS_CROSSING_ANCHOR_ANGLE_DEG)
        )
    scale = THESIS_CROSSING_ANCHOR_DB / anchor
    return {angle: value * scale for angle, value in raw.items()}


def crossing_loss_db(
    angle_deg: float, table: dict[int, float] | None = None
) -> float:
    """Extra insertion loss of a single crossing, in dB.

    The stored table is the loss of ``THESIS_CROSSING_ANCHOR_COUNT`` crossings,
    which is why the original code divides by 30.  Non-integer angles are
    truncated towards zero exactly as ``int(a)`` did in the original; an angle
    outside the table is an error rather than a silently substituted value.
    """
    lookup = table if table is not None else load_crossing_table()
    key = int(angle_deg)
    if key not in lookup:
        raise LossModelError(
            "crossing loss table has no entry for angle %r" % (angle_deg,)
        )
    return lookup[key] / THESIS_CROSSING_ANCHOR_COUNT


def crossing_table_dataframe(table: dict[int, float] | None = None):
    """The table as a DataFrame with the legacy ``angle`` / ``loss_db`` columns."""
    import pandas as pd

    lookup = table if table is not None else load_crossing_table()
    return pd.DataFrame(
        {"angle": sorted(lookup), "loss_db": [lookup[a] for a in sorted(lookup)]}
    )


@dataclass
class RouteLoss:
    """Per-waveguide loss breakdown."""

    route_id: int
    port1: int
    port2: int
    bend_radius_mm: float

    straight_length_mm: float
    bend_arc_length_mm: float
    total_length_mm: float

    bend_angles_deg: list[float] = field(default_factory=list)
    crossing_angles_deg: list[float] = field(default_factory=list)

    straight_loss_db: float = 0.0
    bend_loss_db: float = 0.0
    crossing_loss_db: float = 0.0
    total_loss_db: float = 0.0

    @property
    def bend_count(self) -> int:
        return len(self.bend_angles_deg)

    @property
    def crossing_count(self) -> int:
        """Crossings as the legacy loss sum counts them (duplicates included)."""
        return len(self.crossing_angles_deg)

    def breakdown(self) -> dict[str, float]:
        return {
            "straight_loss_db": self.straight_loss_db,
            "bend_loss_db": self.bend_loss_db,
            "crossing_loss_db": self.crossing_loss_db,
            "total_loss_db": self.total_loss_db,
        }


def route_loss_from_geometry(
    route_id: int,
    port1: int,
    port2: int,
    bend_radius_mm: float,
    total_length_mm: float,
    theta_intervals,
    crossing_angles,
    table: dict[int, float] | None = None,
) -> RouteLoss:
    """Evaluate the thesis loss model for one routed waveguide.

    ``theta_intervals`` are the radian ``(start, end)`` pairs stored by
    ``plotter_bend``; ``crossing_angles`` are the integer degrees stored by
    ``calc_crossing``.  The three loss components are computed in the original
    order ("crossings, then arcs, then the whole path at the straight rate") so
    the total matches the legacy accumulation.
    """
    lookup = table if table is not None else load_crossing_table()

    crossing_total = 0.0
    angles_deg: list[float] = []
    for angle in crossing_angles:
        crossing_total += crossing_loss_db(angle, lookup)
        angles_deg.append(float(angle))

    arc_mm = 0.0
    bends_deg: list[float] = []
    for start, end in theta_intervals:
        span_rad = float(end) - float(start)
        arc_mm += span_rad * bend_radius_mm
        bends_deg.append(span_rad * 180.0 / pi)

    # Same accumulation order as the legacy calc_loss.
    acc = crossing_total
    density = bend_loss_density_db_per_mm(bend_radius_mm)
    acc += arc_mm * density
    straight_mm = float(total_length_mm) - arc_mm
    acc += straight_mm * PROPAGATION_LOSS_DB_PER_MM

    return RouteLoss(
        route_id=route_id,
        port1=port1,
        port2=port2,
        bend_radius_mm=bend_radius_mm,
        straight_length_mm=straight_mm,
        bend_arc_length_mm=arc_mm,
        total_length_mm=float(total_length_mm),
        bend_angles_deg=bends_deg,
        crossing_angles_deg=angles_deg,
        straight_loss_db=straight_mm * PROPAGATION_LOSS_DB_PER_MM,
        bend_loss_db=arc_mm * density,
        crossing_loss_db=crossing_total,
        total_loss_db=acc,
    )


def summarise(losses) -> dict[str, float]:
    """Mean/max/min/std of the total and of each component, in dB."""
    import statistics

    routes = list(losses)
    if not routes:
        raise LossModelError("no routes to summarise")

    def stats(values):
        return {
            "mean": statistics.fmean(values),
            "max": max(values),
            "min": min(values),
            "std": statistics.pstdev(values),
        }

    out: dict[str, float] = {}
    for name, values in (
        ("loss_db", [r.total_loss_db for r in routes]),
        ("straight_loss_db", [r.straight_loss_db for r in routes]),
        ("bend_loss_db", [r.bend_loss_db for r in routes]),
        ("crossing_loss_db", [r.crossing_loss_db for r in routes]),
        ("straight_length_mm", [r.straight_length_mm for r in routes]),
        ("bend_arc_length_mm", [r.bend_arc_length_mm for r in routes]),
        ("total_length_mm", [r.total_length_mm for r in routes]),
        ("crossing_count", [float(r.crossing_count) for r in routes]),
    ):
        for key, value in stats(values).items():
            out["%s_%s" % (name, key)] = float(value)
    return out
