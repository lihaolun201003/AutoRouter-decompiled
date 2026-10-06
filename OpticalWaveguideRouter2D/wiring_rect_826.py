"""Straight-waveguide routing and crossing avoidance.

Python 3.10 port of the legacy ``wiring_rect_826.py``.

The routing algorithm is unchanged: for each of the four layers the track list
``WGysets[layer]`` is scanned for the first free track that satisfies
``noCross``, and the resulting inflections are re-ordered by port so that
waveguides leaving the same fiber-board port stay in the same relative order.

Repaired compared with the decompiled listing (all confirmed against the
original ``.pyc`` dumped in ``_reference/bytecode``):

* ``it = [iter(...)]`` / ``df["inflection"] = ...`` were emitted *inside* the
  ``for row`` loop; the bytecode puts them after the ``for layer`` loop, which
  is the only placement that can work (``list_inflection`` must hold all four
  layers before the per-layer iterators are built).
* ``wiring_rect_below2above`` ended with ``return df3`` inside the innermost
  loop; the bytecode runs to the end of the function.
* the two re-ordering loops lost their ``if A and B: ... else: break`` shape.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import matplotlib

# This module only ever *saves* figures.  Router runs the pipeline in a QThread,
# and building figures on an interactive backend from a worker thread makes
# matplotlib warn ("Starting a Matplotlib GUI outside of the main thread will
# likely fail") and can build Qt canvases off the GUI thread.  Default to the
# non-interactive backend; an explicit MPLBACKEND still wins.
if os.environ.get("MPLBACKEND") is None:
    matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

interface_length = 5

__all__ = [
    "WGyset",
    "MT",
    "MTset",
    "plotter_rect",
    "svg2dwgscr_rect",
    "interface_length",
]


@dataclass
class WGyset:
    WGs: List[int] = field(default_factory=list)
    rEnd: List[int] = field(default_factory=list)
    lEnd: List[int] = field(default_factory=list)
    y: float = interface_length


@dataclass
class MT:
    x: List[float] = field(default_factory=list)
    y: List[float] = field(default_factory=list)


@dataclass
class MTset:
    MTabove: List[MT] = field(default_factory=list)
    MTbelow: List[MT] = field(default_factory=list)


def _output_path(folder, name: str) -> Path:
    """Join an output name onto the save folder.

    The legacy source concatenated the strings directly, which produced paths
    such as ``resultsfiberBoard256rect.xlsx`` whenever the folder did not end
    with a separator.  Names are unchanged, only the join is fixed.
    """
    return Path(folder) / name


def plotter_rect(
    df: pd.DataFrame,
    line_width: float,
    dist: float,
    save_folder: str = "./results/",
    height: int = 150,
    N: int = 256,
    r: float = 5,
) -> pd.DataFrame:
    """Route every connection to a straight waveguide and return the geometry."""
    yy = [
        np.round(i * 0.001, 3)
        for i in range(
            interface_length * 1000,
            (height - interface_length) * 1000,
            int(dist * 1000),
        )
    ]
    WGysets = [[WGyset(y=y, rEnd=[-1], lEnd=[100]) for y in yy] for layer in range(4)]

    def ln_calc(lx, ly):
        if N == 256:
            offset = 6.5 if ly == height else 2
            return max(int(np.round((lx - offset) % 9, 3) / dist) - 6, 4)
        if N == 512:
            offset = 4 if ly == height else 2
            return max(int(np.round((lx - offset) % 4.5, 3) / dist) - 6, 4)
        raise ValueError(f"ln_calc is only defined for N in (256, 512), got N={N!r}")

    def sn_calc(idx2, y, isBelow=True):
        if idx2 >= len(nodes.MTabove):
            return 8
        if isBelow:
            for i, it in enumerate(nodes.MTbelow[idx2].y):
                if it >= y + r:
                    return i
                if it >= y:
                    return -i
        else:
            for i, it in enumerate(nodes.MTabove[idx2].y):
                if it <= y - r:
                    return i
                if it <= y:
                    return -i
        return 8

    def noCross(lEnd, rEnd, i, WGyset, _type="below", lx=0, ly=0, boundary=0):
        """True when track ``i`` can host the connection without crossing.

        The decompiler folded the second test of the ``below`` and ``above``
        sweeps into the first one, turning two sibling ``if`` statements into
        nested ones.  The bytecode jumps every failed condition of either test
        to the same continuation, i.e. they are flat ``and`` chains that both
        run on every iteration.  The nesting changed which track the router
        picked (209 of the 512 routes in the real board).
        """
        if _type == "below":
            for j in range(1, max(ln_calc(lx, ly) - sn_calc(lEnd + 1, WGyset[i].y), 4)):
                if (
                    i >= j
                    and WGyset[i - j].WGs
                    and WGyset[i - j].rEnd[-1] < rEnd
                    and WGyset[i - j].lEnd[-1] < lEnd
                ):
                    return False
                if (
                    i >= j
                    and len(WGyset[i - j].rEnd) > 2
                    and WGyset[i - j].rEnd[-2] < lEnd
                ):
                    return False

            for j in range(1, 8):
                if (
                    i + j < len(WGyset)
                    and WGyset[i + j].WGs
                    and WGyset[i + j].rEnd[-1] > lEnd
                ):
                    return False

        elif _type == "above2below":
            for j in range(1, max(ln_calc(lx, ly) - sn_calc(lEnd + 1, WGyset[i].y), 3)):
                if i >= j and WGyset[i - j].WGs and WGyset[i - j].lEnd[-1] < lEnd:
                    return False

            for j in range(1, 6):
                if (
                    i + j < len(WGyset)
                    and WGyset[i + j].WGs
                    and WGyset[i + j].rEnd[-1] > lEnd
                ):
                    return False

        elif _type == "above":
            for j in range(1, max(ln_calc(lx, ly) - sn_calc(lEnd + 1, WGyset[i].y, False), 4)):
                if (
                    i + j < len(WGyset)
                    and WGyset[i + j].WGs
                    and WGyset[i + j].rEnd[-1] != rEnd
                ):
                    return False
                if (
                    i + j < len(WGyset)
                    and len(WGyset[i + j].rEnd) > 1
                    and WGyset[i + j].rEnd[-2] > lEnd
                ):
                    return False

            for j in range(1, 8):
                if i >= j and WGyset[i - j].WGs and WGyset[i - j].rEnd[-1] > lEnd:
                    return False

        elif _type == "below2above":
            for j in range(1, 6):
                if i >= j and WGyset[i - j].WGs and WGyset[i - j].rEnd[-1] > lEnd:
                    return False

            for j in range(1, max(ln_calc(lx, ly) - sn_calc(lEnd + 1, WGyset[i].y, False), 3)):
                if (
                    i + j < len(WGyset)
                    and WGyset[i + j].WGs
                    and WGyset[i + j].rEnd[-1] > rEnd
                ):
                    return False

        return True

    def _reorder_by_port(values, index, inflections, prefer_greater, swap_direction):
        """Sort ``values`` so that tracks of one port stay ordered.

        ``values`` is a list of per-layer lists; ``index`` are the port indices
        of the same rows and ``inflections`` their assigned track coordinate.
        Two rows sharing a port must keep a monotonic track order, otherwise
        their waveguides would cross right at the port fan-out.
        """
        temp = values[swap_direction].copy()
        i = 0
        while i < len(inflections):
            for j in reversed(range(i)):
                if index[i] == index[j] and (
                    inflections[i] > inflections[j]
                    if prefer_greater
                    else inflections[i] < inflections[j]
                ):
                    values[swap_direction][i], values[swap_direction][j] = (
                        values[swap_direction][j],
                        values[swap_direction][i],
                    )
                    inflections[i], inflections[j] = inflections[j], inflections[i]
                    i = j
                else:
                    break
            i += 1
        values[swap_direction] = [
            temp[values[swap_direction].index(temp[i])]
            for i in range(len(values[swap_direction]))
        ]

    def wiring_rect_below(dist, df):
        def f_inflection_x(x):
            return list([round(x.sx, 4), round(x.sx, 4), round(x.lx, 4), round(x.lx, 4)])

        def f_inflection_y(x):
            return list([round(x.sy, 4), round(x.inflection, 4), round(x.inflection, 4), round(x.ly, 4)])

        df2 = df.copy()
        df2 = df2[(df2["sy"] == 0) & (df2["ly"] == 0)]
        df2 = df2.sort_values(by="sx", ascending=True)
        list_inflection = []
        for layer in range(4):
            i = 0
            indexes = set()
            list_inflection += [[]]
            for row in df2[df2["dz"] == layer].iterrows():
                idx1, idx2 = int(row[1]["index1"] - N / 16), int(row[1]["index2"] - N / 16)
                if idx1 not in indexes:
                    indexes.add(idx1)
                for i, w in enumerate(WGysets[layer]):
                    if idx2 >= w.rEnd[-1]:
                        if noCross(
                            idx2,
                            idx1,
                            i,
                            lx=(row[1]["lx"]),
                            ly=(row[1]["ly"]),
                            WGyset=(WGysets[layer]),
                        ):
                            w.WGs.append(row[0])
                            w.rEnd.append(idx1)
                            w.lEnd.append(idx2)
                            nodes.MTbelow[idx1].y[nodes.MTbelow[idx1].x.index(row[1]["sx"])] = w.y
                            nodes.MTbelow[idx2].y[nodes.MTbelow[idx2].x.index(row[1]["lx"])] = w.y
                            list_inflection[layer] += [w.y]
                            break

        it = [iter(list_inflection[i]) for i in range(4)]
        df2["inflection"] = df2.apply(lambda x: next(it[int(x.dz)]), axis=1)

        sx = []
        for layer in range(4):
            list_inflection = df2[df2["dz"] == layer]["inflection"].tolist()
            index1 = df2[df2["dz"] == layer]["index1"].tolist()
            sx += [df2[df2["dz"] == layer]["sx"].tolist()]
            _reorder_by_port(sx, index1, list_inflection, prefer_greater=False, swap_direction=layer)

        it = [iter(sx[i]) for i in range(4)]
        df2["sx"] = df2.apply(lambda x: next(it[int(x.dz)]), axis=1)

        df2 = df2.sort_values(by="lx", ascending=True)
        lx = []
        for layer in range(4):
            list_inflection = df2[df2["dz"] == layer]["inflection"].tolist()
            index2 = df2[df2["dz"] == layer]["index2"].tolist()
            lx += [df2[df2["dz"] == layer]["lx"].tolist()]
            _reorder_by_port(lx, index2, list_inflection, prefer_greater=True, swap_direction=layer)

        it = [iter(lx[i]) for i in range(4)]
        df2["lx"] = df2.apply(lambda x: next(it[int(x.dz)]), axis=1)
        df2["dx"] = df2.apply(lambda x: np.abs(x.sx - x.lx), axis=1)
        df2["inflection_x"] = df2.apply(lambda x: f_inflection_x(x), axis=1)
        df2["inflection_y"] = df2.apply(lambda x: f_inflection_y(x), axis=1)
        return df2

    def wiring_rect_above(dist, df):
        def f_inflection_x(x):
            if x.dx == 0:
                return list([x.sx, x.lx])
            return list([round(x.sx, 4), round(x.sx, 4), round(x.lx, 4), round(x.lx, 4)])

        def f_inflection_y(x):
            if x.dx == 0:
                return list([x.sy, x.ly])
            return list([round(x.sy, 4), round(x.inflection, 4), round(x.inflection, 4), round(x.ly, 4)])

        df4 = df.copy()
        df4 = df4[(df4["sy"] != 0) & (df4["ly"] != 0)]
        df4 = df4.sort_values(by="sx", ascending=True)
        list_inflection = []
        for layer in range(4):
            i = 0
            indexes = set()
            list_inflection += [[]]
            for row in df4[df4["dz"] == layer].iterrows():
                idx1, idx2 = int(row[1]["index1"]), int(row[1]["index2"])
                if idx1 not in indexes:
                    indexes.add(idx1)
                for i, w in reversed(list(enumerate(WGysets[layer]))):
                    if idx2 >= w.rEnd[-1]:
                        if noCross(
                            idx2,
                            idx1,
                            i,
                            lx=(row[1]["lx"]),
                            ly=(row[1]["ly"]),
                            WGyset=(WGysets[layer]),
                            _type="above",
                        ):
                            w.WGs.append(row[0])
                            w.rEnd.append(idx1)
                            w.lEnd.append(idx2)
                            nodes.MTabove[idx1].y[nodes.MTabove[idx1].x.index(row[1]["sx"])] = w.y
                            nodes.MTabove[idx2].y[nodes.MTabove[idx2].x.index(row[1]["lx"])] = w.y
                            list_inflection[layer] += [w.y]
                            break

        it = [iter(list_inflection[i]) for i in range(4)]
        df4["inflection"] = df4.apply(lambda x: next(it[int(x.dz)], height - 1), axis=1)

        sx = []
        for layer in range(4):
            list_inflection = df4[df4["dz"] == layer]["inflection"].tolist()
            index1 = df4[df4["dz"] == layer]["index1"].tolist()
            sx += [df4[df4["dz"] == layer]["sx"].tolist()]
            _reorder_by_port(sx, index1, list_inflection, prefer_greater=True, swap_direction=layer)

        it = [iter(sx[i]) for i in range(4)]
        df4["sx"] = df4.apply(lambda x: next(it[int(x.dz)]), axis=1)

        df4 = df4.sort_values(by="lx", ascending=True)
        lx = []
        for layer in range(4):
            list_inflection = df4[df4["dz"] == layer]["inflection"].tolist()
            index2 = df4[df4["dz"] == layer]["index2"].tolist()
            lx += [df4[df4["dz"] == layer]["lx"].tolist()]
            _reorder_by_port(lx, index2, list_inflection, prefer_greater=False, swap_direction=layer)

        it = [iter(lx[i]) for i in range(4)]
        df4["lx"] = df4.apply(lambda x: next(it[int(x.dz)]), axis=1)
        df4["dx"] = df4.apply(lambda x: np.abs(x.sx - x.lx), axis=1)
        df4["inflection_x"] = df4.apply(lambda x: f_inflection_x(x), axis=1)
        df4["inflection_y"] = df4.apply(lambda x: f_inflection_y(x), axis=1)
        return df4

    def wiring_rect_below2above(dist, df, df4):
        def f_inflection_x(x):
            if x.dx == 0:
                return list([x.sx, x.lx])
            return list([round(x.sx, 4), round(x.sx, 4), round(x.lx, 4), round(x.lx, 4)])

        def f_inflection_y(x):
            if x.dx == 0:
                return list([x.sy, x.ly])
            return list([round(x.sy, 4), round(x.inflection, 4), round(x.inflection, 4), round(x.ly, 4)])

        df3 = df.copy()
        df3 = df3[(df3["sy"] == 0) & (df3["ly"] != 0)]
        df3 = df3.sort_values(by="sx", ascending=False)
        above_line = min(df4["inflection"])
        list_inflection = []
        for layer in range(4):
            i = 0
            indexes = set()
            list_inflection += [[]]
            for row in df3[df3["dz"] == layer].iterrows():
                idx1, idx2 = int(row[1]["index1"] - N / 16), int(row[1]["index2"])
                if idx1 not in indexes:
                    indexes.add(idx1)
                    gap = 1
                for i, w in reversed(list(enumerate(WGysets[layer]))):
                    if w.y >= above_line:
                        pass
                    elif idx2 >= w.rEnd[-1]:
                        if idx1 != w.rEnd[-1]:
                            if noCross(
                                idx2,
                                idx1,
                                i,
                                lx=(row[1]["sx"]),
                                ly=(row[1]["sy"]),
                                WGyset=(WGysets[layer]),
                                _type="below2above",
                            ):
                                w.WGs.append(row[0])
                                w.rEnd.append(idx1)
                                w.lEnd.append(idx2)
                                nodes.MTbelow[idx1].y[nodes.MTbelow[idx1].x.index(row[1]["sx"])] = w.y
                                nodes.MTabove[idx2].y[nodes.MTabove[idx2].x.index(row[1]["lx"])] = w.y
                                list_inflection[layer] += [w.y]
                                break

        it = [iter(list_inflection[i]) for i in range(4)]
        df3["inflection"] = df3.apply(lambda x: next(it[int(x.dz)]), axis=1)
        df3["inflection_x"] = df3.apply(lambda x: f_inflection_x(x), axis=1)
        df3["inflection_y"] = df3.apply(lambda x: f_inflection_y(x), axis=1)
        return df3

    def wiring_rect_above2below(dist, df, df2, df3):
        def f_inflection_x(x):
            if x.dx == 0:
                return list([x.sx, x.lx])
            return list([round(x.sx, 4), round(x.sx, 4), round(x.lx, 4), round(x.lx, 4)])

        def f_inflection_y(x):
            if x.dx == 0:
                return list([x.sy, x.ly])
            return list([round(x.sy, 4), round(x.inflection, 4), round(x.inflection, 4), round(x.ly, 4)])

        df5 = df.copy()
        df5 = df5[(df5["sy"] != 0) & (df5["ly"] == 0)]
        df5 = df5.sort_values(by="sx", ascending=False)
        b2a_line = min(df3["inflection"])
        below_line = max(df2["inflection"])
        boundary = yy.index(below_line)
        list_inflection = []
        for layer in range(4):
            i = 0
            indexes = set()
            list_inflection += [[]]
            for row in df5[df5["dz"] == layer].iterrows():
                idx1, idx2 = int(row[1]["index1"]), int(row[1]["index2"] - N / 16)
                if idx1 not in indexes:
                    indexes.add(idx1)
                for i, w in enumerate(WGysets[layer]):
                    if w.y < below_line:
                        pass
                    elif idx2 > w.rEnd[-1]:
                        if noCross(
                            idx2,
                            idx1,
                            i,
                            lx=(row[1]["lx"]),
                            ly=(row[1]["ly"]),
                            WGyset=(WGysets[layer]),
                            _type="above2below",
                        ):
                            w.WGs.append(row[0])
                            w.rEnd.append(idx1)
                            w.lEnd.append(idx2)
                            nodes.MTabove[idx1].y[nodes.MTabove[idx1].x.index(row[1]["sx"])] = w.y
                            nodes.MTbelow[idx2].y[nodes.MTbelow[idx2].x.index(row[1]["lx"])] = w.y
                            list_inflection[layer] += [w.y]
                            break

        it = [iter(list_inflection[i]) for i in range(4)]
        df5["inflection"] = df5.apply(lambda x: next(it[int(x.dz)], height + 10), axis=1)
        df5 = df5.sort_values(by="sx", ascending=True)
        sx = []
        for layer in range(4):
            list_inflection = df5[df5["dz"] == layer]["inflection"].tolist()
            index1 = df5[df5["dz"] == layer]["index1"].tolist()
            sx += [df5[df5["dz"] == layer]["sx"].tolist()]
            _reorder_by_port(sx, index1, list_inflection, prefer_greater=True, swap_direction=layer)

        # The original computed ``it = [iter(sx[i]) ...]`` here and never used
        # it, so the re-ordered ``sx`` is deliberately not written back; kept
        # for behavioural fidelity.
        it = [iter(sx[i]) for i in range(4)]

        df5["dx"] = df5.apply(lambda x: np.abs(x.sx - x.lx), axis=1)
        df5["inflection_x"] = df5.apply(lambda x: f_inflection_x(x), axis=1)
        df5["inflection_y"] = df5.apply(lambda x: f_inflection_y(x), axis=1)
        return df5

    def add_port(it, nodes, l):
        if it.index1 >= l:
            nodes.MTbelow[int(it.index1 - l)].x.append(it.sx)
        else:
            nodes.MTabove[int(it.index1)].x.append(it.sx)
        if it.index2 >= l:
            nodes.MTbelow[int(it.index2 - l)].x.append(it.lx)
        else:
            nodes.MTabove[int(it.index2)].x.append(it.lx)

    def init_MT_set(df, N=512):
        nodes = MTset(MTabove=[], MTbelow=[])
        for i in range(int(N / 16)):
            nodes.MTabove.append(MT(x=[], y=([0] * 16)))
            nodes.MTbelow.append(MT(x=[], y=([height] * 16)))

        df.apply(lambda x: add_port(x, nodes, int(N / 16)), axis=1)
        for mt in nodes.MTabove + nodes.MTbelow:
            mt.x.sort()

        return nodes

    nodes = init_MT_set(df, N)
    df2 = wiring_rect_below(dist, df)
    df4 = wiring_rect_above(dist, df)
    df3 = wiring_rect_below2above(dist, df, df4)
    df5 = wiring_rect_above2below(dist, df, df2, df3)
    df = pd.concat([df2, df4, df3, df5], axis=0)
    df["ln"] = df.apply(lambda x: ln_calc(x.lx, x.ly), axis=1)

    # The polylines are stored as list cells that
    # waveguide_calculator.calc_index reads back with ast.literal_eval.  NumPy 2
    # renders np.float64 as "np.float64(1.5)" in repr (NumPy 1 printed "1.5"),
    # which literal_eval rejects, so keep the legacy plain-number form.
    df["inflection_x"] = df["inflection_x"].apply(lambda values: [float(v) for v in values])
    df["inflection_y"] = df["inflection_y"].apply(lambda values: [float(v) for v in values])

    fig = plt.figure()
    ax = plt.gca()
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    for i in range(df.shape[0]):
        x_list = df["inflection_x"].tolist()[i]
        y_list = df["inflection_y"].tolist()[i]
        ax.plot(x_list, y_list, color="g", linewidth=line_width, alpha=0.8)

    fig.savefig(
        _output_path(save_folder, "fiberBoard" + str(N) + "_rect.pdf"),
        dpi=3000,
        format="pdf",
    )
    df.to_excel(_output_path(save_folder, "fiberBoard" + str(N) + "rect.xlsx"))
    return df


def svg2dwgscr_rect(
    data_res: pd.DataFrame,
    scr_filename: str = "fiberBoard896rect.scr",
    save_folder: str = "./results/",
) -> None:
    """Write the routed polylines as an AutoCAD ``.scr`` script."""
    with open(_output_path(save_folder, scr_filename), "w") as f:
        for i in range(data_res.shape[0]):
            f.write(
                "line {},{} {},{} {},{} {},{} {},{}  \n".format(
                    data_res["inflection_x"][i][0],
                    data_res["inflection_y"][i][0],
                    data_res["inflection_x"][i][1],
                    data_res["inflection_y"][i][1],
                    data_res["inflection_x"][i][2],
                    data_res["inflection_y"][i][2],
                    data_res["inflection_x"][i][3],
                    data_res["inflection_y"][i][3],
                    data_res["inflection_x"][i][4],
                    data_res["inflection_y"][i][4],
                )
            )
