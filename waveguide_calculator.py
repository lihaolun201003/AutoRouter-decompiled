"""Waveguide length, crossing and loss statistics.

Python 3.10 port of the legacy ``waveguide_calculator.py``.

``main.Router`` only imports :func:`calc_index` and :func:`draw_chart`; neither
is called by the GUI workflow in the legacy program, so this module is kept
importable and runnable on its own rather than wired into the routing pipeline.

Repairs compared with the decompiled listing:

* ``np.cross(p2 - p1, p1 - p0)`` on 2-D vectors is deprecated in NumPy 2 and
  removed in later releases.  The 2-D cross product is the same determinant the
  module already defines as ``det``, so the expression is written with ``det``.
* ``calc_loss`` indexes the loss table with ``.values[0]``; that stays, but a
  missing angle now raises a readable error instead of ``IndexError`` on an
  empty array.
* ``calc_crossing`` had no return outside the ``DEBUG`` branch (confirmed in
  the recovered bytecode), so ``calc_index`` raised ``TypeError: object of type
  'NoneType' has no len()`` for every route.  The non-debug path now returns an
  empty angle list, which is what the debug path uses for "not analysed".
"""

from __future__ import annotations

import ast
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from numpy.linalg import norm
from scipy.stats import norm as nm

__all__ = ["calc_index", "draw_chart", "det", "is_fall_on", "is_cross"]

min_angle = 90
count = 0


def det(a, b):
    """2-D determinant / cross product."""
    return a[0] * b[1] - a[1] * b[0]


def is_fall_on(p, line):
    """True when ``p`` lies on the axis-aligned bounding box of ``line``."""
    return (
        p[0] >= min(line[0][0], line[1][0])
        and p[0] <= max(line[0][0], line[1][0])
        and p[1] >= min(line[0][1], line[1][1])
        and p[1] <= max(line[0][1], line[1][1])
    )


def is_cross(line1, line2):
    """Intersection of two segments: ``(found, point_or_None)``."""
    xdiff = (line1[0][0] - line1[1][0], line2[0][0] - line2[1][0])
    ydiff = (line1[0][1] - line1[1][1], line2[0][1] - line2[1][1])
    div = det(xdiff, ydiff)
    if div == 0:
        return (False, None)
    d = (det(*line1), det(*line2))
    x = np.round(det(d, xdiff) / div, 3)
    y = np.round(det(d, ydiff) / div, 3)
    return (is_fall_on((x, y), line1) and is_fall_on((x, y), line2), (x, y))


def calc_index(
    data: pd.DataFrame,
    loss: pd.DataFrame,
    line_width: float,
    bend_radius: float,
    height: int = 150,
    width: int = 150,
    file_name: str = "fiberBoard256calc.xlsx",
) -> pd.DataFrame:
    """Add length, crossing and loss columns to a routed waveguide table.

    ``data`` is the workbook written by :func:`wiring_bend_826.plotter_bend`
    (``inflection_x``/``inflection_y``/``center``/``theta`` are stored as text
    and parsed with :func:`ast.literal_eval`), and ``loss`` is a lookup table
    with ``angle`` and ``loss_db`` columns.  The legacy repository does not
    ship a loss table, so this dataset is not available here.
    """
    global count
    global min_angle

    def calc_length(x):
        if x.dx < 2 * bend_radius:
            theta = np.arccos((bend_radius - x.dx * 0.5) / bend_radius)
            bend_length = 2 * bend_radius * theta
            vertical_length = (
                np.abs(x.sy - x.inflection)
                + np.abs(x.ly - x.inflection)
                - 2 * bend_radius * np.sin(theta)
            )
            return bend_length + vertical_length
        bend_length = bend_radius * np.pi
        vertical_length = (
            np.abs(x.sy - x.inflection) + np.abs(x.ly - x.inflection) - 2 * bend_radius
        )
        horizontal_length = x.dx - 2 * bend_radius
        return bend_length + vertical_length + horizontal_length

    def calc_crossing(row):
        global count
        global min_angle

        def is_across_at_bend(p, line1, line2):
            if np.abs(line1[0][0] - line1[1][0]) < 0.1:
                return (
                    int(np.abs(p[0] - line2[0][0]) < bend_radius)
                    + int(np.abs(p[0] - line2[1][0]) < bend_radius) * 2
                    + int(
                        np.abs(p[1] - line1[0][1]) < bend_radius
                        or np.abs(p[1] - line1[1][1]) < bend_radius
                    )
                    * 4
                )
            return (
                -int(np.abs(p[0] - line1[0][0]) < bend_radius)
                - int(np.abs(p[0] - line1[1][0]) < bend_radius) * 2
                - int(
                    np.abs(p[1] - line2[0][1]) < bend_radius
                    or np.abs(p[1] - line2[1][1]) < bend_radius
                )
                * 4
            )

        def line_to_arc(center, line, idx):
            p0 = np.asarray(center)
            p1 = np.asarray(line[0])
            p2 = np.asarray(line[1])
            d = np.abs(det(p2 - p1, p1 - p0) / norm(p2 - p1))
            if d < bend_radius:
                return np.round(np.arccos(d / bend_radius) / np.pi * 180)
            if os.getenv("DEBUG") == "True":
                return idx
            return 0

        def arc_to_arc(center1, center2, line1, line2, idx):
            p1 = np.asarray(center1)
            p2 = np.asarray(center2)
            d = norm(p1 - p2)
            if d < 2 * bend_radius:
                return np.round(
                    np.arccos(1 - d**2 / (2 * bend_radius**2)) / np.pi * 180
                )
            if not (
                center1[0] >= min(line2[0][0], line2[1][0])
                and center1[0] <= max(line2[0][0], line2[1][0])
            ):
                if (
                    not center1[1] >= min(line2[0][1], line2[1][1])
                    or center1[1] <= max(line2[0][1], line2[1][1])
                ):
                    return line_to_arc(center1, line2, idx)
                if not (
                    center2[0] >= min(line1[0][0], line1[1][0])
                    and center2[0] <= max(line1[0][0], line1[1][0])
                ):
                    if (
                        not center2[1] >= min(line1[0][1], line1[1][1])
                        or center2[1] <= max(line1[0][1], line1[1][1])
                    ):
                        return line_to_arc(center2, line1, idx)
                    if os.getenv("DEBUG") == "True":
                        return idx
                return 0

        def f(lines, center1, x, y, center2):
            for i in range(len(x) - 1):
                for j, line1 in enumerate(lines):
                    line2 = ((x[i], y[i]), (x[i + 1], y[i + 1]))
                    if line1 == line2:
                        return None
                    else:
                        ok, p = is_cross(line1, line2)
                    if ok:
                        result = {
                            -1: line_to_arc(center1[0], line2, -1),
                            -2: line_to_arc(center1[1], line2, -2),
                            -3: (
                                line_to_arc(center1[0], line2, -3)
                                if (
                                    np.abs(p[0] - line1[0][0])
                                    < np.abs(p[0] - line1[1][0])
                                )
                                else (line_to_arc(center1[1], line2, -3))
                            ),
                            -4: (
                                line_to_arc(center2[0], line1, -4)
                                if (line2[0][1] == 0) or (line2[0][1] == height)
                                else (line_to_arc(center2[1], line1, 4))
                            ),
                            -5: (
                                arc_to_arc(center1[0], center2[0], line1, line2, -5)
                                if (line2[0][1] == 0) or (line2[0][1] == height)
                                else (
                                    arc_to_arc(
                                        center1[0], center2[1], line1, line2, -5
                                    )
                                )
                            ),
                            -6: (
                                arc_to_arc(center1[1], center2[0], line1, line2, -6)
                                if (line2[0][1] == 0) or (line2[0][1] == height)
                                else (
                                    arc_to_arc(
                                        center1[1], center2[1], line1, line2, -6
                                    )
                                )
                            ),
                            -7: (
                                arc_to_arc(center1[0], center2[0], line1, line2, -7)
                                if (line2[0][1] == 0) or (line2[0][1] == height)
                                else (
                                    arc_to_arc(
                                        center1[0], center2[1], line1, line2, -7
                                    )
                                    if (
                                        np.abs(p[0] - line1[0][0])
                                        < np.abs(p[0] - line1[1][0])
                                    )
                                    else (
                                        arc_to_arc(
                                            center1[1], center2[0], line1, line2, -7
                                        )
                                        if (line2[0][1] == 0)
                                        or (line2[0][1] == height)
                                        else (
                                            arc_to_arc(
                                                center1[1],
                                                center2[1],
                                                line1,
                                                line2,
                                                -7,
                                            )
                                        )
                                    )
                                )
                            ),
                            1: line_to_arc(center2[0], line1, 1),
                            2: line_to_arc(center2[1], line1, 2),
                            3: (
                                line_to_arc(center2[0], line2, 3)
                                if (
                                    np.abs(p[0] - line2[0][0])
                                    < np.abs(p[0] - line2[1][0])
                                )
                                else (line_to_arc(center2[1], line2, 3))
                            ),
                            4: (
                                line_to_arc(center1[0], line2, 4)
                                if (line1[0][1] == 0) or (line1[0][1] == height)
                                else (line_to_arc(center1[1], line2, 4))
                            ),
                            5: (
                                arc_to_arc(center2[0], center1[0], line2, line1, 5)
                                if (line1[0][1] == 0) or (line1[0][1] == height)
                                else (
                                    arc_to_arc(
                                        center2[0], center1[1], line2, line1, 5
                                    )
                                )
                            ),
                            6: (
                                arc_to_arc(center2[1], center1[0], line2, line1, 6)
                                if (line1[0][1] == 0) or (line1[0][1] == height)
                                else (
                                    arc_to_arc(
                                        center2[1], center1[1], line2, line1, 6
                                    )
                                )
                            ),
                            7: (
                                arc_to_arc(center2[0], center1[0], line2, line1, 7)
                                if (line1[0][1] == 0) or (line1[0][1] == height)
                                else (
                                    arc_to_arc(
                                        center2[0], center1[1], line2, line1, 7
                                    )
                                    if (
                                        np.abs(p[0] - line2[0][0])
                                        < np.abs(p[0] - line2[1][0])
                                    )
                                    else (
                                        arc_to_arc(
                                            center2[1], center1[0], line2, line1, 7
                                        )
                                        if (line1[0][1] == 0)
                                        or (line1[0][1] == height)
                                        else (
                                            arc_to_arc(
                                                center2[1],
                                                center1[1],
                                                line2,
                                                line1,
                                                7,
                                            )
                                        )
                                    )
                                )
                            ),
                            0: 90,
                        }[is_across_at_bend(p, line1, line2)]
                        if os.getenv("DEBUG") == "True":
                            print(p, line1, line2, result)
                        return result

        if os.getenv("DEBUG") == "True":
            if row.name != 56:
                return []
            lines = []
            for i in range(len(row.inflection_x) - 1):
                lines.append(
                    (
                        (row.inflection_x[i], row.inflection_y[i]),
                        (row.inflection_x[i + 1], row.inflection_y[i + 1]),
                    )
                )

            points = [
                f(lines, row.center, r[0], r[1], r[2])
                for r in data[["inflection_x", "inflection_y", "center"]].values
            ]
            points = [p for p in points if p != None]
            count += len([p for p in points if p >= 20])
            if 0 in points:
                print(row, points)
            min_angle = min(min(points + [min_angle]), min_angle)
            return points

        # Legacy defect, not a decompiler artifact: the whole body sits behind
        # the DEBUG gate and the function otherwise falls off the end, so
        # calc_index crashed on ``len(None)`` for every route.  An empty angle
        # list is exactly how the DEBUG branch itself spells "no crossing
        # analysis" (``if row.name != 56: return []``).
        return []

    def calc_loss(x):
        r = [2, 3, 4, 5, 6, 8, 10, 15]
        tl = [-16.0, -10.59, -6.08, -2.8, -2.03, -1.39, -0.87, -0.45]
        ll = [6.33, 7.33, 8.33, 9.23, 10.05, 11.53, 12.92, 15.74]
        total_loss = tl[r.index(bend_radius)]
        length = ll[r.index(bend_radius)]
        bend_loss = total_loss / length
        straight_loss = -0.005
        l = 0
        for a in x.angles:
            rows = loss.loc[loss["angle"] == int(a)]["loss_db"].values
            if len(rows) == 0:
                raise KeyError(
                    "loss table has no entry for crossing angle %r" % (int(a),)
                )
            l += rows[0] / 30

        for t in x.theta:
            l += (t[1] - t[0]) * bend_radius * (bend_loss - straight_loss)

        l += x.length * straight_loss
        return l

    data["inflection_x"] = data.apply(lambda x: ast.literal_eval(x.inflection_x), axis=1)
    data["inflection_y"] = data.apply(lambda x: ast.literal_eval(x.inflection_y), axis=1)
    data["center"] = data.apply(lambda x: ast.literal_eval(x.center), axis=1)
    data["theta"] = data.apply(lambda x: ast.literal_eval(x.theta), axis=1)
    data = data.sort_values(by="inflection", ascending=True)
    data["length"] = data.apply(lambda x: np.round(calc_length(x), 4), axis=1)
    wg_density = np.round(np.sum(data["length"]) * line_width / (height * width), 4)
    print("waveguide_density: ", wg_density)
    data["angles"] = data.apply(lambda x: calc_crossing(x), axis=1)
    data["crossing"] = data.apply(lambda x: len(x.angles), axis=1)
    if os.getenv("DEBUG") == "True":
        return data
    data["loss"] = data.apply(lambda x: calc_loss(x), axis=1)
    print("******** Output the data to excel file ********")
    data.to_excel(file_name)
    print("min angle: ", min_angle)
    print("count: ", count)
    return data


def draw_chart(data: pd.DataFrame, filename: str):
    """Histogram and scatter plots of the per-waveguide loss.

    ``filename`` is used both as a suffix and for the normalisation of the
    fitted curve (``int(filename)`` in the legacy source), so it must be a
    numeric string such as ``"256"``.
    """
    plt.clf()
    data["loss"] = data.apply(lambda x: -float(x.loss), axis=1)
    data["length"] = data.apply(lambda x: float(x.length), axis=1)
    data["crossing"] = data.apply(lambda x: float(x.crossing), axis=1)
    n, bins, patches = plt.hist((data["loss"]), bins=64)
    plt.ylabel("Counts", family="Arial", fontsize=16)
    plt.xlabel("Loss (dB)", family="Arial", fontsize=16)
    xmin, xmax = plt.xlim()
    loss_mu, loss_std = nm.fit(data["loss"])
    y = nm.pdf(bins, loss_mu, loss_std) * (xmax - xmin) / 64 * int(filename)
    plt.plot(bins, y, "r--", linewidth=2)
    plt.savefig("loss-count" + filename + ".png")
    data = data.sort_values(by="length", ascending=True)
    fig, ax = plt.subplots()
    data["straight_loss"] = data.apply(lambda x: -0.005 * x.length, axis=1)
    ax.scatter((data["length"]), (data["loss"]), label="loss", color="red", s=6)
    plt.ylabel("Loss (dB)", family="Arial", fontsize=16)
    plt.xlabel("Length (mm)", family="Arial", fontsize=16)
    plt.savefig("loss-length" + filename + ".png")
    data = data.sort_values(by="crossing", ascending=True)
    fig, ax = plt.subplots()
    ax.scatter((data["crossing"]), (data["loss"]), label="loss", color="red", s=6)
    plt.ylabel("Loss (dB)", family="Arial", fontsize=16)
    plt.xlabel("Number of crossings", family="Arial", fontsize=16)
    plt.savefig("loss-crossing" + filename + ".png")
