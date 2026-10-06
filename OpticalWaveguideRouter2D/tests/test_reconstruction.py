"""Acceptance tests for the AutoRouter 2D reconstruction.

These tests run the real pipeline on the real 256/512 workbooks; nothing is
mocked.  The strongest one is :func:`test_create_sim_space_matches_legacy_snapshot`:
``data/fiberBoard0data.xlsx`` is the port-placement snapshot that the original
``AutoRouter.exe`` wrote next to itself, so a row-by-row comparison pins the
port numbering, sorting and index handling to the legacy behaviour.

    .venv\\Scripts\\python.exe -m pytest tests -v
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import problem_graph  # noqa: E402
import wiring_bend_826  # noqa: E402
import wiring_rect_826  # noqa: E402
import waveguide_calculator  # noqa: E402

DATA = ROOT / "data"
PARAMS = {
    256: {"line_width": 0.05, "pitch": 0.25, "bend_radius": 5},
    512: {"line_width": 0.05, "pitch": 0.125, "bend_radius": 5},
}
HEIGHT = 150


def workbook(N: int) -> Path:
    return DATA / f"fiberBoard{N}.xlsx"


@pytest.fixture(scope="session")
def routed(tmp_path_factory):
    """Run create_sim_space -> plotter_rect -> plotter_bend once per board size."""
    from main import Router

    out = {}
    for N, params in PARAMS.items():
        folder = tmp_path_factory.mktemp(f"route{N}")
        router = Router(
            N,
            str(folder),
            str(workbook(N)),
            params["line_width"],
            params["pitch"],
            params["bend_radius"],
            HEIGHT,
            HEIGHT,
        )
        df_bend = router.router(
            N,
            str(folder),
            str(workbook(N)),
            params["line_width"],
            params["pitch"],
            params["bend_radius"],
            HEIGHT,
            HEIGHT,
        )
        out[N] = {"folder": folder, "sim": router.df, "rect": router.df_rect, "bend": df_bend}
    return out


def test_core_modules_import():
    """Level B: every core module imports and keeps the legacy entry points."""
    import app
    import main

    assert callable(main.Router)
    assert callable(problem_graph.create_sim_space)
    assert callable(problem_graph.read_sim_space)
    assert callable(wiring_rect_826.plotter_rect)
    assert callable(wiring_rect_826.svg2dwgscr_rect)
    assert callable(wiring_bend_826.plotter_bend)
    assert callable(wiring_bend_826.svg2gds_bend)
    assert callable(waveguide_calculator.calc_index)
    assert callable(waveguide_calculator.draw_chart)
    assert callable(app.MainWindow)


def test_create_sim_space_matches_legacy_snapshot(tmp_path):
    """The 512 port placement must match the output of the original executable."""
    reference = pd.read_excel(DATA / "fiberBoard0data.xlsx")
    mine = problem_graph.create_sim_space(
        str(workbook(512)), str(tmp_path), 0.05, 0.125, height=HEIGHT, N=512
    )
    columns = ["Port1", "Port2", "index1", "index2", "sy", "ly", "dz", "sx", "lx", "dx"]
    assert len(reference) == len(mine) == 512
    assert reference["Unnamed: 0"].tolist() == mine.index.tolist()
    for column in columns:
        expected = reference[column].to_numpy(dtype=float)
        actual = mine[column].to_numpy(dtype=float)
        assert np.allclose(expected, actual, rtol=0, atol=1e-9), (
            f"column {column} differs from the legacy snapshot, "
            f"max delta {np.abs(expected - actual).max():g}"
        )


@pytest.mark.parametrize("N", [256, 512])
def test_create_sim_space_geometry(N, tmp_path):
    """Level C: port placement produces finite, in-range coordinates."""
    params = PARAMS[N]
    df = problem_graph.create_sim_space(
        str(workbook(N)), str(tmp_path), params["line_width"], params["pitch"], height=HEIGHT, N=N
    )
    assert len(df) == N
    for column in ("sx", "lx", "dx"):
        values = df[column].to_numpy(dtype=float)
        assert np.isfinite(values).all(), f"{column} has NaN/Inf"
        assert values.min() >= 0
    assert df["dx"].min() > 0
    assert set(df["sy"].unique()) | set(df["ly"].unique()) <= {0, HEIGHT}
    assert df["dz"].eq(0).all(), "dz is 0 for every route in the legacy placement"
    assert df["index1"].between(0, 2 * N // 16 - 1).all()
    assert df["index2"].between(0, 2 * N // 16 - 1).all()

    source = pd.read_excel(workbook(N))
    pairs_in = sorted(tuple(sorted(p)) for p in source[["Port1", "Port2"]].to_numpy())
    pairs_out = sorted(tuple(sorted(p)) for p in df[["Port1", "Port2"]].to_numpy())
    assert pairs_in == pairs_out
    assert len(pairs_out) == N


def test_create_sim_space_rejects_unknown_board(tmp_path):
    with pytest.raises(ValueError, match="256 and 512"):
        problem_graph.create_sim_space(str(workbook(256)), str(tmp_path), N=1024)


def test_read_sim_space_roundtrip(routed, tmp_path):
    """read_sim_space reloads the workbook plotter_rect wrote."""
    N = 256
    path = routed[N]["folder"] / f"fiberBoard{N}rect.xlsx"
    reloaded = problem_graph.read_sim_space(str(path))
    assert len(reloaded) == N
    assert set(["Port1", "Port2", "index1", "index2", "sy", "ly", "sx", "lx", "dx", "dz", "ln"]) <= set(
        reloaded.columns
    )


@pytest.mark.parametrize("N", [256, 512])
def test_straight_routing_geometry(routed, N):
    """Level D: four inflection points per route, inside the area, no overlap."""
    df = routed[N]["rect"]
    assert len(df) == N
    lengths = df["inflection_x"].apply(len)
    assert (lengths == 4).all()
    assert (df["inflection_y"].apply(len) == lengths).all()

    for _, row in df.iterrows():
        for value in row["inflection_y"]:
            assert -1e-6 <= float(value) <= HEIGHT + 1e-6
        assert float(row["dx"]) >= 0

    runs: dict[float, list[tuple[float, float]]] = {}
    for _, row in df.iterrows():
        low, high = sorted((float(row["sx"]), float(row["lx"])))
        runs.setdefault(float(row["inflection"]), []).append((low, high))
    for track, intervals in runs.items():
        intervals.sort()
        for (low_a, high_a), (low_b, _) in zip(intervals, intervals[1:]):
            assert low_b >= high_a - 1e-6, f"two routes overlap on track {track}"

    assert df["ln"].between(4, 9).all()


@pytest.mark.parametrize("N", [256, 512])
def test_bend_geometry(routed, N):
    """Level E: arcs have tangent points, centres and angular spans."""
    df = routed[N]["bend"]
    params = PARAMS[N]
    for _, row in df.iterrows():
        assert len(row["dir"]) == 2
        assert len(row["bend_x"]) == 4
        assert len(row["bend_y"]) == 4
        assert len(row["center"]) == len(row["theta"]) == 2
        assert np.isfinite(np.asarray(row["bend_x"], dtype=float)).all()
        assert np.isfinite(np.asarray(row["bend_y"], dtype=float)).all()
        for center in row["center"]:
            assert np.isfinite(np.asarray(center, dtype=float)).all()
        for start, stop in row["theta"]:
            assert 0 <= start < stop <= 2 * np.pi + 1e-9
        # A bend only fits if the two runs are at least the bend diameter apart,
        # otherwise the legacy code falls back to the dx/2 tangent points.
        span = params["bend_radius"] if row["dx"] >= 2 * params["bend_radius"] else row["dx"] * 0.5
        assert span > 0


@pytest.mark.parametrize("N", [256, 512])
def test_end_to_end_outputs(routed, N):
    """Level G: PNG, PDF, XLSX and GDS are all produced and non-empty."""
    folder = routed[N]["folder"]
    prefix = f"fiberBoard{N}bend"
    expected = [
        f"{prefix}.png",
        f"{prefix}.pdf",
        f"{prefix}.xlsx",
        f"{prefix}.gds",
        f"fiberBoard{N}rect.xlsx",
        f"fiberBoard{N}_rect.pdf",
        "fiberBoard0data.xlsx",
    ]
    for name in expected:
        path = folder / name
        assert path.is_file(), f"{name} was not produced"
        assert path.stat().st_size > 0, f"{name} is empty"

    for name in (f"{prefix}.png",):
        from PIL import Image

        with Image.open(folder / name) as image:
            image.load()
            assert image.size[0] > 100 and image.size[1] > 100
            rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
            non_white = float((rgb < 250).any(axis=2).mean())
            assert non_white > 0.001, "PNG looks blank"

    assert (folder / f"{prefix}.pdf").read_bytes()[:5] == b"%PDF-"


@pytest.mark.parametrize("N", [256, 512])
def test_gds_roundtrip(routed, N):
    """Level F: the GDSII file reopens with one path per routed waveguide."""
    import gdspy

    path = routed[N]["folder"] / f"fiberBoard{N}bend.gds"
    library = gdspy.GdsLibrary(infile=str(path))
    assert list(library.cells)
    cell = library.cells[list(library.cells)[0]]
    paths = cell.get_paths()
    assert len(paths) == N
    assert cell.get_bounding_box() is not None
    assert np.isfinite(cell.get_bounding_box()).all()


def test_workbook_stays_literal_eval_readable(routed):
    """The stored polylines must survive the round trip calc_index performs."""
    path = routed[256]["folder"] / "fiberBoard256bend.xlsx"
    df = pd.read_excel(path)
    for column in ("inflection_x", "inflection_y", "center", "theta"):
        values = df[column].apply(ast.literal_eval)
        assert len(values) == 256
        assert all(isinstance(v, (list, tuple)) for v in values)


def test_waveguide_calculator_helpers():
    """Deterministic checks of the independently computable geometry helpers."""
    assert waveguide_calculator.det((1, 0), (0, 1)) == 1
    crossed, point = waveguide_calculator.is_cross(((0, 0), (10, 0)), ((5, -5), (5, 5)))
    assert crossed and point == (5.0, 0.0)
    crossed, _ = waveguide_calculator.is_cross(((0, 0), (10, 0)), ((0, 5), (10, 5)))
    assert not crossed
    assert waveguide_calculator.is_fall_on((5, 0), ((0, 0), (10, 0)))
    assert not waveguide_calculator.is_fall_on((15, 0), ((0, 0), (10, 0)))


def test_calc_index_length_column(routed, tmp_path):
    """calc_index must reload the workbook and compute lengths and crossings.

    The crossing-loss table was an external workbook the legacy repository never
    shipped, so this passes an explicit all-zero table: the geometry, the
    crossing analysis and the length formula are what is under test, not a
    validated loss figure.

    Crossing analysis runs on the normal path, not only under ``DEBUG``.  The
    recovered bytecode gates just the early exit, and the original program run
    under the legacy runtime reports a minimum crossing angle of 14 degrees for
    512 channels, matching thesis section 4.1.
    """
    source = routed[512]["folder"] / "fiberBoard512bend.xlsx"
    data = pd.read_excel(source)
    # calc_index parses inflection_x/inflection_y/center/theta itself, exactly
    # as it would for a workbook produced by the legacy executable.
    zero = pd.DataFrame({"angle": list(range(1, 181)), "loss_db": [0.0] * 180})
    out = waveguide_calculator.calc_index(
        data.copy(),
        zero,
        0.05,
        5.0,
        height=HEIGHT,
        width=HEIGHT,
        file_name=str(tmp_path / "calc.xlsx"),
    )
    assert len(out) == 512
    assert np.isfinite(out["length"].to_numpy(dtype=float)).all()
    assert out["length"].min() > 0
    assert (out["crossing"] > 0).mean() > 0.9, "most 512-channel routes cross others"
    # 86512 is what the original bytecode reports for this workbook under the
    # legacy runtime; the count does not depend on row order.
    assert out["crossing"].sum() == 86512
    assert np.isfinite(out["loss"].to_numpy(dtype=float)).all()
    assert (tmp_path / "calc.xlsx").is_file()


def test_draw_chart_writes_three_plots(routed, tmp_path, monkeypatch):
    """draw_chart consumes the calc_index output and saves its three figures."""
    source = routed[256]["folder"] / "fiberBoard256bend.xlsx"
    data = pd.read_excel(source)
    zero = pd.DataFrame({"angle": list(range(1, 181)), "loss_db": [0.0] * 180})
    out = waveguide_calculator.calc_index(
        data.copy(), zero, 0.05, 5.0, height=HEIGHT, width=HEIGHT,
        file_name=str(tmp_path / "calc.xlsx"),
    )
    monkeypatch.chdir(tmp_path)
    waveguide_calculator.draw_chart(out, "256")
    for name in ("loss-count256.png", "loss-length256.png", "loss-crossing256.png"):
        assert (tmp_path / name).is_file(), f"{name} was not produced"
        assert (tmp_path / name).stat().st_size > 0


def test_bend_geometry_at_dx_equal_diameter(tmp_path):
    """Pin the arc geometry for the boundary case dx == 2R.

    A single corner: (10, 0) -> (10, 50) -> (0, 50).  With R = 5 and dx = 10 the
    two quarter-circle tangent points are at (10, 45) and (5, 50) around centre
    (5, 45), so ``dx < bend_radius * 2`` is false and the theta spans must come
    from ``theta_map`` -- exactly the branch the decompiled listing broke by
    turning the ternary's ``and`` into a list filter (which also made
    ``theta_list`` shorter than ``center_list``).
    """
    from wiring_bend_826 import plotter_bend

    df = pd.DataFrame(
        [
            {
                "inflection_x": [10.0, 10.0, 0.0, 0.0],
                "inflection_y": [0.0, 50.0, 50.0, 150.0],
                "dx": 10.0,
                "sy": 0.0,
                "ly": 150.0,
                "dz": 0,
                "sx": 10.0,
                "lx": 0.0,
                "Port1": 1,
                "Port2": 2,
                "index1": 0,
                "index2": 0,
                "inflection": 50.0,
                "ln": 4,
            }
        ]
    )
    out = plotter_bend(df, 0.05, 0.3, 5.0, 0.001, str(tmp_path), "probe_bend")
    row = out.iloc[0]
    assert row["dir"] == [(-1.0, -1.0), (1.0, 1.0)]
    assert row["bend_x"] == [10.0, 5.0, 5.0, 0.0]
    assert row["bend_y"] == [45.0, 50.0, 50.0, 55.0]
    assert row["center"] == [(5.0, 45.0), (5.0, 55.0)]
    assert row["theta"] == [(0, np.pi / 2), (np.pi, np.pi * 1.5)]
    for name in ("probe_bend.png", "probe_bend.pdf", "probe_bend.xlsx"):
        assert (tmp_path / name).is_file()


def test_bend_geometry_below_diameter(tmp_path):
    """dx < 2R uses the dx/2 tangent points and the arccos angular span."""
    from wiring_bend_826 import plotter_bend

    df = pd.DataFrame(
        [
            {
                "inflection_x": [4.0, 4.0, 0.0, 0.0],
                "inflection_y": [0.0, 50.0, 50.0, 150.0],
                "dx": 4.0,
                "sy": 0.0,
                "ly": 150.0,
                "dz": 0,
                "sx": 4.0,
                "lx": 0.0,
                "Port1": 1,
                "Port2": 2,
                "index1": 0,
                "index2": 0,
                "inflection": 50.0,
                "ln": 4,
            }
        ]
    )
    out = plotter_bend(df, 0.05, 0.3, 5.0, 0.001, str(tmp_path), "probe_narrow")
    row = out.iloc[0]
    # dx/2 = 2 mm tangent offset, arc rise R*sin(arccos((R - dx/2)/R)) = 4 mm.
    assert row["bend_x"] == [4.0, 2.0, 2.0, 0.0]
    assert row["bend_y"] == [46.0, 50.0, 50.0, 54.0]
    # calc_theta: arccos((R - dx/2) / R) = arccos(0.6).
    theta = np.arccos((5.0 - 2.0) / 5.0)
    assert row["theta"] == [(0, theta), (np.pi, np.pi + theta)]


def test_gui_launches_and_routes(tmp_path):
    """The PyQt5 window builds and a real routing run completes through it."""
    from PyQt5.QtCore import QEventLoop, QTimer
    from PyQt5.QtWidgets import QApplication

    import app

    application = QApplication.instance() or QApplication([])
    window = app.MainWindow()
    window.show()
    assert window.windowTitle() == "自动布线程序"
    assert window.styleSheet()

    panel = window.inputPanel
    panel.N.setValue(256)
    panel.wg_pitch.setValue(250)
    panel.input.setText(str(workbook(256)))
    panel.output.setText(str(tmp_path / "gui_out"))
    assert panel.validate() is None
    panel.N.setValue(1024)
    assert panel.validate() is not None
    panel.N.setValue(256)
    panel.input.setText("does_not_exist.xlsx")
    assert panel.validate() is not None
    panel.input.setText(str(workbook(256)))

    outcome = {}
    loop = QEventLoop()
    window.router.finish.connect(lambda f, n: (outcome.setdefault("finish", (f, n)), loop.quit()))
    window.router.error.connect(lambda t: (outcome.setdefault("error", t), loop.quit()))
    QTimer.singleShot(600000, loop.quit)
    panel.start()
    loop.exec_()

    assert "error" not in outcome, outcome.get("error")
    assert outcome.get("finish") == (str(tmp_path / "gui_out"), 256)
    assert (tmp_path / "gui_out" / "fiberBoard256bend.gds").is_file()
    assert window.imageWindow is not None and window.imageWindow.isVisible()
    assert "波导布线完成" in window.logger.toPlainText()
    assert not window.router.isRunning()
    window.close()
    application.processEvents()
