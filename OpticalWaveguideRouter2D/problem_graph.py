"""Input parsing and port placement for the legacy AutoRouter 2D router.

Python 3.10 port of the legacy ``problem_graph.py``.  The
port assignment algorithm is kept as-is; the changes are limited to

* decompilation repairs that were verified against the original bytecode
  recovered from ``AutoRouter.exe`` (see ``_reference/bytecode`` and
  ``docs/migration_report.md``),
* replacing CWD-relative output paths with paths derived from the requested
  save folder.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

__all__ = ["create_sim_space", "read_sim_space", "PortPlacementError"]


class PortPlacementError(RuntimeError):
    """Raised when a connection refers to a port that has already been used.

    The original code silently wrote to the last slot of the port list when
    ``find_next`` failed, which produced silently wrong port x coordinates.
    Failing loudly is the only safe behaviour here.
    """


def _save_folder(folder) -> Path:
    path = Path(folder) if folder not in (None, "") else Path("results")
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_sim_space(
    file_name: str,
    save_folder: str = "./results/",
    line_width: float = 0.05,
    line_dist: float = 0.25,
    channel_num: int = 12,
    height: int = 150,
    N: int = 256,
) -> pd.DataFrame:
    """Place every connection of the input workbook on the fiber board.

    ``Port1``/``Port2`` in the workbook are fiber-board port numbers.  They are
    mapped to ``index1``/``index2`` (position along the board), ``sy``/``ly``
    (side of the board), ``sx``/``lx`` (x coordinate of the waveguide on that
    side) and ``dz`` (routing layer).
    """
    data = pd.read_excel(file_name)
    BeginPointX = 0
    BeginPointY = 0
    BeginPointZ = 0
    if N == 256:
        above_list = [
            29, 26, 21, 20, 24, 17, 10, 16, 18, 19, 2, 13, 12, 14, 9, 8]
        below_list = [
            53, 54, 56, 57, 58, 48, 47, 49, 51, 41, 33, 11, 38, 39, 1, 6]
        above_dist = [6.5] + [9] * (len(above_list) - 1)
        below_dist = [2] + [9] * (len(below_list) - 1)
    elif N == 512:
        above_list = [
            21, 116, 29, 114, 26, 113, 20, 117, 24, 118, 18, 107, 19, 108,
            16, 109, 17, 101, 10, 111, 2, 12, 13, 98, 71, 99, 14, 93, 8, 61,
            9, 66]
        below_list = [
            53, 89, 54, 80, 56, 81, 57, 86, 58, 84, 47, 79, 48, 78, 49, 76,
            51, 77, 41, 70, 11, 62, 38, 74, 39, 72, 1, 73, 33, 68, 6, 69]
        above_dist = [4] + [4.5] * (len(above_list) - 1)
        below_dist = [2] + [4.5] * (len(below_list) - 1)
    else:
        raise ValueError(
            "the legacy port table only defines the 256 and 512 channel "
            f"fiber boards, got N={N!r}"
        )
    above_dist = np.cumsum(above_dist)
    below_dist = np.cumsum(below_dist)

    def find_next(value, l, reverse):
        length = len(l)
        for i in range(length):
            i = length - i - 1 if reverse else i
            if l[i] == value:
                return i
        print("didn't find the value %d, in " % value, l)
        return -1

    def sn_posx(x):
        idx = find_next(x.index2, PORTS[int(x.index1)], False)
        if idx < 0:
            raise PortPlacementError(
                "Port1=%s(index1=%s) has no free slot for Port2=%s(index2=%s)"
                % (x.Port1, x.index1, x.Port2, x.index2)
            )
        PORTS[int(x.index1)][idx] = -1
        base_x = (
            above_dist[above_list.index(x.Port1)]
            if x.Port1 in above_list
            else below_dist[below_list.index(x.Port1)]
        )
        return base_x + idx * (line_dist + line_width)

    def ln_posx(x):
        idx = find_next(x.index1, PORTS[int(x.index2)], x.sy == x.ly)
        if idx < 0:
            raise PortPlacementError(
                "Port2=%s(index2=%s) has no free slot for Port1=%s(index1=%s)"
                % (x.Port2, x.index2, x.Port1, x.index1)
            )
        PORTS[int(x.index2)][idx] = -1
        base_x = (
            above_dist[above_list.index(x.Port2)]
            if x.Port2 in above_list
            else below_dist[below_list.index(x.Port2)]
        )
        return base_x + idx * (line_dist + line_width)

    PORTS = [[] for j in range(len(below_list) + len(above_list))]

    def calc_sn_ln(x):
        PORTS[int(x.index1)].append(x.index2)
        PORTS[int(x.index2)].append(x.index1)

    def coarse_sort(PORTS):
        """Order each port's neighbours left / centre / right.

        The decompiler flattened the two ``if``/``elif`` chains below into
        nested ``if``/``else`` blocks and hoisted the ``PORT error`` print out
        of the ``else`` branch; the bytecode shows the original used ``elif``
        with the print as the final fallback.
        """
        for i, l in enumerate(PORTS):
            left = []
            center = []
            right = []
            if i < len(above_list):
                for it in l:
                    if it < i:
                        left.append(it)
                    elif it > i and it < len(above_list):
                        right.append(it)
                    elif (
                        it >= len(above_list)
                        and it < len(above_list) + len(below_list)
                    ):
                        center.append(it)
                    else:
                        print("Port error")
            else:
                for it in l:
                    if it < len(above_list):
                        center.append(it)
                    elif it < i:
                        left.append(it)
                    elif it > i and it < len(above_list) + len(below_list):
                        right.append(it)
                    else:
                        print("Port error")

            PORTS[i] = (
                np.sort(left)[::-1].tolist()
                + np.sort(center).tolist()
                + np.sort(right)[::-1].tolist()
            )

        return PORTS

    data["Port1"] = pd.to_numeric(data["Port1"])
    data["Port2"] = pd.to_numeric(data["Port2"])
    idx = data["Port1"] > data["Port2"]
    data.loc[idx, ["Port1", "Port2"]] = data.loc[idx, ["Port2", "Port1"]].values
    data["index1"] = data.apply(
        lambda x: (
            above_list.index(x.Port1)
            if x.Port1 in above_list
            else below_list.index(x.Port1) + len(above_list)
        ),
        axis=1,
    )
    data["index2"] = data.apply(
        lambda x: (
            above_list.index(x.Port2)
            if x.Port2 in above_list
            else below_list.index(x.Port2) + len(above_list)
        ),
        axis=1,
    )
    data["sy"] = data.apply(
        lambda x: BeginPointY + height if x.Port1 in above_list else BeginPointY,
        axis=1,
    )
    data["ly"] = data.apply(
        lambda x: BeginPointY + height if x.Port2 in above_list else BeginPointY,
        axis=1,
    )
    data["dz"] = data.apply(lambda x: 0, axis=1)
    data.apply(lambda x: calc_sn_ln(x), axis=1)
    PORTS = coarse_sort(PORTS)
    data["sx"] = data.apply(lambda x: sn_posx(x), axis=1)
    data["lx"] = data.apply(lambda x: ln_posx(x), axis=1)
    data["dx"] = data.apply(lambda x: np.abs(x.sx - x.lx), axis=1)
    idx = data["sx"] < data["lx"]
    data.loc[
        idx, ["Port1", "Port2", "index1", "index2", "sy", "ly", "sx", "lx"]
    ] = data.loc[
        idx, ["Port2", "Port1", "index2", "index1", "ly", "sy", "lx", "sx"]
    ].values
    # Deliberately no reset_index(): plotter_rect() stores the row labels in
    # WGyset.WGs and later uses them to index the concatenated dataframe.
    data = data.sort_values(by="sx", ascending=True)
    data.to_excel(_save_folder(save_folder) / "fiberBoard0data.xlsx")
    return data


def create_sim_space_896_legacy(
    file_name: str = "./fiberBoard896.xls",
    save_folder: str = "./results/",
    line_width: float = 0.125,
    line_dist: float = 0.2,
) -> pd.DataFrame:
    """Superseded 896-channel port placement, kept for reference only.

    The decompiled module contains two ``create_sim_space`` definitions in
    the same module; the second one (``create_sim_space``, the N=256/512
    variant used by ``main.Router``) shadows this one, so this code never runs
    in the original program either.  It is reproduced verbatim so that the
    896-channel layout can still be compared function-by-function with the
    legacy source.  Do not call it.
    """
    data = pd.read_excel(file_name)
    BeginPointX = 0
    BeginPointY = 0
    BeginPointZ = 0
    NumPerOutput = 16
    OutputDist = 0.6
    mt_gap = NumPerOutput * (line_width + line_dist) + OutputDist
    mm_list = [2, 4, 6, 8, 7, 5, 3, 1]
    ll_list = [9, 10, 15, 16, 17, 18, 23, 24]
    sc_list = [1, 2, 3, 4, 5, 6, 7]
    mt_list = [16, 15, 10, 9, 17, 18, 23, 24]

    def ll_mm_ln_posy(x):
        ll_bpy_list = [10.5, 23.8, 64.4, 77.7]
        dy = 0
        dy = dy + ll_bpy_list[ll_list.index(x.L) % 4]
        if x.L in ll_list[:4]:
            dy = dy + mm_list.index(x.M) * mt_gap
            if mm_list.index(x.M) >= 4:
                dy = dy + 0.4
            dy = dy + (NumPerOutput / 2 - x.LN) * (line_width + line_dist)
        else:
            dy = dy + (len(mm_list) - 1 - mm_list.index(x.M)) * mt_gap
            if mm_list.index(x.M) < 4:
                dy = dy + 0.4
            dy = dy + (x.LN - NumPerOutput / 2) * (line_width + line_dist)
        return BeginPointY + dy

    def sc_mt_sn_posx(x):
        sc_bpx_list = [42.8 + i * 6 for i in range(7)]
        dx = 0
        dx = dx + sc_bpx_list[sc_list.index(x.SC)] + mt_list.index(x.MT) % 4 * mt_gap
        if mt_list.index(x.MT) < 4:
            dx = dx + (x.SN - NumPerOutput / 2 + 0.5) * (line_width + line_dist)
        else:
            dx = dx + (NumPerOutput / 2 + 0.5 - x.SN) * (line_width + line_dist)
        return BeginPointX + dx

    df_sc = data["Port1"].str.split("-", expand=True)
    df_sc[0] = pd.to_numeric(df_sc[0].str[2:])
    df_sc[1] = pd.to_numeric(df_sc[1].str[2:])
    df_sc[2] = pd.to_numeric(df_sc[2])
    df_sc.columns = ["SC", "MT", "SN"]
    df_sc["sx"] = df_sc.apply(lambda x: sc_mt_sn_posx(x), axis=1)
    df_sc["sy"] = df_sc.apply(
        lambda x: BeginPointY + 5 if x.MT in mt_list[:4] else BeginPointY + 95,
        axis=1,
    )
    df_l = data["Port2"].str.split("-", expand=True)
    df_l[0] = pd.to_numeric(df_l[0].str[1:])
    df_l[1] = pd.to_numeric(df_l[1].str[1:])
    df_l[2] = pd.to_numeric(df_l[2])
    df_l.columns = ["L", "M", "LN"]
    df_l["lx"] = df_l.apply(
        lambda x: BeginPointX + 0 if x.L in ll_list[:4] else BeginPointX + 130,
        axis=1,
    )
    df_l["ly"] = df_l.apply(lambda x: ll_mm_ln_posy(x), axis=1)
    df = pd.concat([data, df_sc, df_l], axis=1)
    return df


def read_sim_space(SimSpace: str) -> pd.DataFrame:
    """Reload a workbook written by :func:`create_sim_space`."""
    data = pd.read_excel(SimSpace)
    data["Port1"] = data.apply(lambda x: int(x.Port1), axis=1)
    data["Port2"] = data.apply(lambda x: int(x.Port2), axis=1)
    data["index1"] = data.apply(lambda x: int(x.index1), axis=1)
    data["index2"] = data.apply(lambda x: int(x.index2), axis=1)
    data["sy"] = data.apply(lambda x: int(x.sy), axis=1)
    data["ly"] = data.apply(lambda x: int(x.ly), axis=1)
    data["sx"] = data.apply(lambda x: float(x.sx), axis=1)
    data["lx"] = data.apply(lambda x: float(x.lx), axis=1)
    data["dx"] = data.apply(lambda x: float(x.dx), axis=1)
    data["dz"] = data.apply(lambda x: int(x.dz), axis=1)
    data["ln"] = data.apply(lambda x: int(x.ln), axis=1)
    return data
