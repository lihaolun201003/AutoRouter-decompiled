"""Bend generation, visualisation and GDSII export.

Python 3.10 port of the legacy ``wiring_bend_826.py``.

``plotter_bend`` turns the rectangular polylines produced by
:func:`wiring_rect_826.plotter_rect` into circular arcs: the tangent points
(``bend_x``/``bend_y``), the arc centres (``center``) and the angular spans
(``theta``) are computed from the same ``bend_radius`` the legacy program used,
and the arcs are sampled with ``np.arange(start, stop, delta_arc)``.

Repairs compared with the decompiled listing (confirmed against the original
``.pyc`` in ``_reference/bytecode``):

* ``dir_norm`` returned after the first loop iteration, so only ``a[0]`` was
  ever normalised; the bytecode shows ``return a`` after the loop.
* the theta list comprehension lost its ``and``: the decompiler emitted
  ``... for d in dir if dx < bend_radius * 2``, which leaves ``theta_list``
  empty (and the arc plot raises ``IndexError``) whenever ``dx >= 2R``.  The
  bytecode is ``calc_theta(dx, d) if dx < bend_radius * 2 and dx != 0 else
  theta_map[...]`` with no filter clause, so the list is always as long as the
  direction list.
* ``dir_map``/``theta_map`` hold four quadrant directions, so the ``dx == 0``
  and ``dx >= 2R`` cases fall back to ``theta_map`` instead of ``calc_theta``.
* output paths were string-concatenated (``save_folder + file_name + ".xlsx"``),
  which produced names such as ``resultsfiberBoard256bend.xlsx``.
* geometry stored in the output workbook is converted back to plain Python
  numbers.  NumPy 2 renders ``np.float64(1.5)`` in ``repr`` where NumPy 1
  printed ``1.5``, which made the stored list cells unreadable for
  ``ast.literal_eval`` and therefore for ``waveguide_calculator.calc_index``.
* the module defaults to the non-interactive Agg backend: it only saves
  figures, and ``Router`` builds them from a worker thread.
"""

from __future__ import annotations

import os

import gdspy
import matplotlib

if os.environ.get("MPLBACKEND") is None:
    matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

matplotlib.rcParams["xtick.direction"] = "in"
matplotlib.rcParams["ytick.direction"] = "in"
matplotlib.rcParams["mathtext.rm"] = "Arial"

__all__ = ["plotter_bend", "svg2gds_bend", "data_linewidth_plot"]


def _output_path(folder, name: str):
    from pathlib import Path

    return Path(folder) / name


def plain(value):
    """Replace NumPy scalars with the equivalent Python scalars.

    ``plotter_bend`` stores per-waveguide geometry as list cells in the output
    workbook, and :func:`waveguide_calculator.calc_index` reads them back with
    ``ast.literal_eval``.  NumPy 1 renders ``np.float64(1.5)`` as ``1.5``, but
    NumPy 2 renders the wrapper itself, so a stored cell would read
    ``[np.float64(1.5), ...]`` and ``literal_eval`` would refuse it.  The legacy
    workbook held plain numbers, so convert back to that form.
    """
    if isinstance(value, (list, tuple)):
        return type(value)(plain(item) for item in value)
    if isinstance(value, np.generic):
        return value.item()
    return value


class data_linewidth_plot:
    """Plot a line whose on-screen width matches a data-space width."""

    def __init__(self, x, y, **kwargs):
        self.ax = kwargs.pop("ax", plt.gca())
        self.fig = self.ax.get_figure()
        self.lw_data = kwargs.pop("linewidth", 1)
        self.lw = 1
        self.fig.canvas.draw()
        self.ppd = 72.0 / self.fig.dpi
        self.trans = self.ax.transData.transform
        self.linehandle, = (self.ax.plot)([], [], **kwargs)
        if "label" in kwargs:
            kwargs.pop("label")
        self.line, = (self.ax.plot)(x, y, **kwargs)
        self.line.set_color(self.linehandle.get_color())
        self._resize()
        self.cid = self.fig.canvas.mpl_connect("draw_event", self._resize)

    def _resize(self, event=None):
        lw = ((self.trans((1, self.lw_data)) - self.trans((0, 0))) * self.ppd)[1]
        if lw != self.lw:
            self.line.set_linewidth(lw)
            self.lw = lw
            self._redraw_later()

    def _redraw_later(self):
        self.timer = self.fig.canvas.new_timer(interval=10)
        self.timer.single_shot = True
        self.timer.add_callback(lambda: self.fig.canvas.draw_idle())
        self.timer.start()


def plotter_bend(
    df_rect: pd.DataFrame,
    line_width: float,
    dist: float,
    bend_radius: float = 5.0,
    delta_arc: float = 0.001,
    save_folder: str = "./results/",
    file_name: str = "fiberBoard256bend",
) -> pd.DataFrame:
    """Replace the corners of every routed waveguide with a circular arc."""

    def dir_norm(a: list) -> list:
        for i in range(len(a)):
            if a[i] > 0:
                a[i] = 1
            if a[i] < 0:
                a[i] = -1
        return a

    def dir_list(x):
        dir_list = []
        for i in range(len(x.inflection_x) - 2):
            dir_in = dir_norm(
                [x.inflection_x[i] - x.inflection_x[i + 1], x.inflection_y[i] - x.inflection_y[i + 1]]
            )
            dir_out = dir_norm(
                [x.inflection_x[i + 2] - x.inflection_x[i + 1], x.inflection_y[i + 2] - x.inflection_y[i + 1]]
            )
            dir_list.append(plain(tuple(np.array(dir_in) + np.array(dir_out))))

        return dir_list

    def elements_round_list(a: list) -> list:
        for i in range(len(a)):
            a[i] = round(plain(a[i]), 4)

        return a

    def bend_x_list(x):
        bend_x_list = []
        for i in range(len(x.inflection_x) - 2):
            dir_in = dir_norm(
                [x.inflection_x[i] - x.inflection_x[i + 1], x.inflection_y[i] - x.inflection_y[i + 1]]
            )
            dir_out = dir_norm(
                [x.inflection_x[i + 2] - x.inflection_x[i + 1], x.inflection_y[i + 2] - x.inflection_y[i + 1]]
            )
            if x.dx >= bend_radius * 2:
                bend_x_list = bend_x_list + [
                    x.inflection_x[i + 1] + bend_radius * dir_in[0],
                    x.inflection_x[i + 1] + bend_radius * dir_out[0],
                ]
            else:
                bend_x_list = bend_x_list + [
                    x.inflection_x[i + 1] + x.dx * 0.5 * dir_in[0],
                    x.inflection_x[i + 1] + x.dx * 0.5 * dir_out[0],
                ]

        return elements_round_list(bend_x_list)

    def bend_y_list(x):
        bend_y_list = []
        for i in range(len(x.inflection_x) - 2):
            dir_in = dir_norm(
                [x.inflection_x[i] - x.inflection_x[i + 1], x.inflection_y[i] - x.inflection_y[i + 1]]
            )
            dir_out = dir_norm(
                [x.inflection_x[i + 2] - x.inflection_x[i + 1], x.inflection_y[i + 2] - x.inflection_y[i + 1]]
            )
            if x.dx >= bend_radius * 2:
                bend_y_list = bend_y_list + [
                    x.inflection_y[i + 1] + bend_radius * dir_in[1],
                    x.inflection_y[i + 1] + bend_radius * dir_out[1],
                ]
            else:
                bend_y_list = bend_y_list + [
                    x.inflection_y[i + 1]
                    + bend_radius
                    * np.sin(np.arccos((bend_radius - x.dx * 0.5) / bend_radius))
                    * dir_in[1],
                    x.inflection_y[i + 1]
                    + bend_radius
                    * np.sin(np.arccos((bend_radius - x.dx * 0.5) / bend_radius))
                    * dir_out[1],
                ]

        return elements_round_list(bend_y_list)

    def center_list(x):
        center_list = []
        for i in range(len(x.dir)):
            if x.dx >= bend_radius * 2:
                center_list.append(
                    plain(
                        tuple(
                            np.array([x.inflection_x[i + 1], x.inflection_y[i + 1]])
                            + bend_radius * np.array(x.dir[i])
                        )
                    )
                )
            else:
                center_list.append(
                    plain(
                        tuple(
                            np.array(
                                [
                                    x.bend_x[i * (len(x.bend_x) - 1)] + bend_radius * x.dir[i][0],
                                    x.bend_y[i * (len(x.bend_y) - 1)],
                                ]
                            )
                        )
                    )
                )

        return center_list

    def calc_theta(dx, d):
        theta = np.arccos((bend_radius - dx * 0.5) / bend_radius)
        theta_map_s = [
            (0, theta),
            (np.pi - theta, np.pi),
            (np.pi, np.pi + theta),
            (2 * np.pi - theta, 2 * np.pi),
        ]
        return theta_map_s[dir_map.index(d)]

    dir_map = [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]
    theta_map = [
        (0, np.pi / 2),
        (np.pi / 2, np.pi),
        (np.pi, np.pi / 2 * 3),
        (np.pi / 2 * 3, 2 * np.pi),
    ]
    df = df_rect.copy()
    df["dir"] = df.apply(dir_list, axis=1)
    df["bend_x"] = df.apply(bend_x_list, axis=1)
    df["bend_y"] = df.apply(bend_y_list, axis=1)
    df["center"] = df.apply(center_list, axis=1)
    fig = plt.figure()
    ax = plt.gca()
    ax.set_xlabel("$\\mathrm{x(mm)}$", fontsize=18)
    ax.set_ylabel("$\\mathrm{y(mm)}$", fontsize=18)
    color = ["r", "b", "m", "c"]
    for layer in range(4):
        for i in range(df[df["dz"] == layer].shape[0]):
            tempx = df[df["dz"] == layer]["inflection_x"].tolist()[i]
            tempy = df[df["dz"] == layer]["inflection_y"].tolist()[i]
            bendx = df[df["dz"] == layer]["bend_x"].tolist()[i]
            bendy = df[df["dz"] == layer]["bend_y"].tolist()[i]
            dir_list_col = df[df["dz"] == layer]["dir"].tolist()[i]
            center_list_col = df[df["dz"] == layer]["center"].tolist()[i]
            dx = df[df["dz"] == layer]["dx"].tolist()[i]
            x_list = [tempx[0]] + bendx + [tempx[-1]]
            y_list = [tempy[0]] + bendy + [tempy[-1]]
            theta_list = [
                plain(
                    calc_theta(dx, d)
                    if dx < bend_radius * 2 and dx != 0
                    else theta_map[dir_map.index(d)]
                )
                for d in dir_list_col
            ]
            j = 0
            for k in range(int(len(x_list) / 2)):
                ax.plot(x_list[j : j + 2], y_list[j : j + 2], color=color[layer], linewidth=0.2, alpha=1.0)
                j = j + 2

            for k in range(int(len(center_list_col))):
                arc_x_list = list(
                    center_list_col[k][0]
                    + bend_radius * np.cos(np.arange(theta_list[k][0], theta_list[k][1], delta_arc))
                )
                arc_y_list = list(
                    center_list_col[k][1]
                    + bend_radius * np.sin(np.arange(theta_list[k][0], theta_list[k][1], delta_arc))
                )
                ax.plot(arc_x_list, arc_y_list, color=color[layer], linewidth=0.2, alpha=1.0)

    plt.axis("scaled")
    df["theta"] = df.apply(
        lambda x: [
            plain(
                calc_theta(x.dx, d)
                if x.dx < bend_radius * 2 and x.dx != 0
                else theta_map[dir_map.index(d)]
            )
            for d in x.dir
        ],
        axis=1,
    )
    print("******** Output Routed waveguides to svg file and pdf file ********")
    fig.savefig(_output_path(save_folder, file_name + ".png"), dpi=150, format="png")
    fig.savefig(_output_path(save_folder, file_name + ".pdf"), dpi=3000, format="pdf")
    df.to_excel(_output_path(save_folder, file_name + ".xlsx"))
    return df


def svg2gds_bend(
    df: pd.DataFrame,
    line_width: float = 0.125,
    bend_radius: float = 5,
    gds_filename: str = "fiberBoard896bend.gds",
    save_folder: str = "./results/",
) -> None:
    """Write every routed waveguide to a GDSII flex path with circular bends."""
    gdspy.current_library = gdspy.GdsLibrary()
    cell = gdspy.Cell("wiring896")
    for i in range(df.shape[0]):
        points = []
        for j in range(len(df["inflection_x"][i])):
            points = points + [
                tuple([df["inflection_x"][i][j], df["inflection_y"][i][j]])
            ]

        sp = gdspy.FlexPath(
            points,
            line_width,
            corners="circular bend",
            bend_radius=bend_radius,
            gdsii_path=True,
        )
        cell.add(sp)

    gdspy.write_gds(_output_path(save_folder, gds_filename))
