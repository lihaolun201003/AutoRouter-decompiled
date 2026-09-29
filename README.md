# OpticalWaveguideRouter2D

**OpticalWaveguideRouter2D** is a Python 3.10.11 reconstruction of the legacy
**AutoRouter** program for 2D optical waveguide routing — the *Legacy AutoRouter
Reference Implementation*.

It was reconstructed from the original AutoRouter Python 3.8 executable and
validated directly against its original runtime behaviour: the original
bytecode was recovered from the packaged executable, re-run under the
interpreter and libraries it was built with, and compared with this
implementation stage by stage. Every one of the 512 routed waveguides, every
bend parameter and every GDSII path matches.

This repository is kept as a behavioural reference. New 3D routing algorithms
are not developed here.

---

## Features

- 256-channel and 512-channel 2D optical waveguide routing
- legacy port placement, port numbering and channel ordering
- 2D rectilinear (Manhattan) routing, with the legacy four layer slots (`dz`)
- crossing avoidance (`noCross` / `sn_calc` / `ln_calc`)
- circular bend reconstruction: tangent points, arc centres, angular spans
- PNG / PDF visualisation (layout plate and straight-routing plate)
- Excel intermediate and output data
- GDSII output through `gdspy.FlexPath(..., corners="circular bend")`
- PyQt5 GUI with a background routing thread, parameter validation and a log pane
- command line interface for both board sizes

---

## Legacy fidelity

### Environment

| | Interpreter | NumPy | pandas |
| --- | --- | --- | --- |
| original AutoRouter runtime | Python 3.8.10 | 1.18.5 | 1.0.4 |
| this reconstruction | Python 3.10.11 | 2.2.6 | 2.3.3 |

The original runtime is not shipped here (it is large and binary);
`tools/setup_legacy_runtime.py` rebuilds it locally from the PyInstaller bundle
that ships with `AutoRouter.exe`.

### Verified equivalence

The original `problem_graph`, `wiring_rect_826` and `wiring_bend_826` code
objects were executed unmodified under Python 3.8.10 / NumPy 1.18.5 /
pandas 1.0.4, and their output was diffed against this reconstruction:

```text
create_sim_space   512/512 exact       port table, index labels, sx/sy/lx/ly/dx/dz
plotter_rect       512/512 exact       every route on the identical inflection track
plotter_bend       512/512 exact       inflection_x/y, dir, bend_x, bend_y, center, theta
GDS geometry       512/512 paths exact identical point arrays and widths
```

Per routing pass:

```text
below -> below   112/112
above -> above   112/112
below -> above   115/115
above -> below   173/173
```

The GDSII files are identical except for the creation timestamps that GDSII
itself embeds (`BGNLIB` / `BGNSTR`, 8 bytes). In other words this is an **exact
behavioural and routing-geometry reconstruction of the analysed AutoRouter
executable**; it is not a claim of byte-for-byte identity with the compiled
executable.

The full evidence chain, including the hypotheses tested and rejected, is in
[docs/exact_legacy_fidelity_report.md](docs/exact_legacy_fidelity_report.md) and
[docs/debug_first_divergence.md](docs/debug_first_divergence.md).

### Note on the historical `fiberBoard512_rect.pdf`

A figure dated 2020 ships alongside the executable and was used as the reference
at first. It turned out to come from a **different AutoRouter build** and
disagrees with the executable that was decompiled: on `below -> below` it places
62 of 112 routes one track higher, which then shifts all 173 `above -> below`
routes. The ground truth is therefore the original executable's runtime
behaviour, not that figure. The figure is kept in `docs/` as
`legacy_2020_fiberBoard512_rect.pdf` so that the distinction stays visible.

---

## Install (Windows, Python 3.10.11)

```powershell
py -3.10 -m venv .venv

.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# gdspy publishes no Windows wheel and compiles a C++ extension, so it is
# installed by a dedicated script that also works without a C++ toolchain.
.\.venv\Scripts\python.exe tools\install_gdspy.py
```

`tools\install_gdspy.py` installs the unmodified official gdspy 1.6.13 source
and adds a pure-Python `gdspy/clipper.py` fallback for the optional C++
extension that this project never reaches — paths are written with
`gdsii_path=True`, which does not use polygon clipping. See
[docs/migration_report.md](docs/migration_report.md) section 3.1.

Activating the environment is not required; call the interpreter in `.venv`
directly as shown above.

---

## Run

### GUI

```powershell
.\.venv\Scripts\python.exe app.py
```

### 256-channel routing

```powershell
.\.venv\Scripts\python.exe main.py --channels 256
```

### 512-channel routing

```powershell
.\.venv\Scripts\python.exe main.py --channels 512
```

### Explicit paths and parameters

```powershell
.\.venv\Scripts\python.exe main.py --input data\fiberBoard512.xlsx --channels 512 --output results
.\.venv\Scripts\python.exe main.py --help
```

With no `--input` the workbook is resolved from `data\fiberBoard<N>.xlsx`, so
both board sizes run out of the box after a clone. Parameters are in
millimetres: `--input --output --channels --line-width --pitch --bend-radius
--width --height`. `--pitch` is the edge-to-edge waveguide gap and defaults to
0.125 mm for 512 channels and 0.25 mm for 256 channels, the values in the
verified 2D parameter table.

A run writes `fiberBoard<N>bend.png/.pdf/.xlsx/.gds`, `fiberBoard<N>rect.xlsx`,
`fiberBoard<N>_rect.pdf` and `fiberBoard0data.xlsx` into the output folder, which
is created if it does not exist.

---

## Verification

```powershell
# real-data acceptance tests (no mocks)
.\.venv\Scripts\python.exe -m pytest tests -q

# end-to-end output audit: GDSII re-read, PNG measurement, track audit
.\.venv\Scripts\python.exe tools\verify_reconstruction.py 256 --output results
.\.venv\Scripts\python.exe tools\verify_reconstruction.py 512 --output results

# debug map for visual inspection
.\.venv\Scripts\python.exe tools\render_debug_map.py 512 --output results
```

The exact-fidelity gate compares against the original program and needs the
legacy runtime, which is rebuilt from the local `AutoRouter.exe` bundle:

```powershell
.\.venv\Scripts\python.exe tools\setup_legacy_runtime.py

_legacy_runtime\py38\python.exe tools\legacy_runtime_trace.py `
    --out scratch\legacy_full.json --channels 512 --full

.\.venv\Scripts\python.exe tools\exact_fidelity_gate.py
```

The gate exits non-zero when the reference is missing or when the frozen passes
(`above -> above`, `below -> above`) regress.

---

## Layout

```text
app.py                      PyQt5 GUI
main.py                     Router (QThread) pipeline and CLI
problem_graph.py            input parsing and port placement
wiring_rect_826.py          straight routing, crossing avoidance, four layers
wiring_bend_826.py          circular bends, visualisation, GDSII export
waveguide_calculator.py     length / crossing / loss statistics
requirements.txt            runtime dependencies
data/                       real 256 and 512 workbooks, legacy port snapshot
resource/  style/           GUI icon and stylesheet from the original bundle
results/                    run output (generated)
tests/                      real-data acceptance tests
tools/                      installation, verification, fidelity and bytecode utilities
docs/                       migration report, fidelity report, divergence analysis
```

### Tools

| Tool | Purpose |
| --- | --- |
| `install_gdspy.py` | install gdspy, with or without a C++ toolchain |
| `setup_legacy_runtime.py` | rebuild the original Python 3.8 runtime from the bundle |
| `extract_pyz.py` | unpack `PYZ-00.pyz` into importable `.pyc` modules |
| `raw_dis.py`, `skeleton_dis.py` | version-correct Python 3.8 bytecode disassembly |
| `legacy_runtime_trace.py` | run the original bytecode and trace its internal state |
| `reconstruction_trace.py` | the same trace taken from this implementation |
| `exact_fidelity_gate.py` | the fidelity gate (routing, bends, GDSII, frozen passes) |
| `verify_reconstruction.py` | output audit (GDSII re-read, PNG, track overlap) |
| `render_debug_map.py` | per-route debug map for visual inspection |
| `compare_with_legacy_pdf.py` | compare a run against the legacy outputs |

---

## Scope and known limitations

- Only 256 and 512 channels are supported. The legacy port table defines no other
  fiber board, and `create_sim_space` rejects any other channel count.
- `dz` is 0 for every connection, exactly as in the original. The four-layer
  machinery is present in all four routing passes and in the four-colour figure,
  but only layer 0 ever holds geometry. Nothing was invented here.
- `waveguide_calculator.calc_index` runs on the real workbooks, but no
  crossing-angle loss table or index table ships with the repository, so those
  numbers cannot be validated and were not fabricated.
- The decompiled module defined `create_sim_space` twice; the superseded
  896-channel version is kept as `create_sim_space_896_legacy()` for reference
  and is not reachable from the pipeline.
- A few legacy behaviours are preserved deliberately: an unused `it = [...]` in
  `wiring_rect_above2below`, the `int(filename)` in `draw_chart`, the
  never-called `Viewer()` in `app.py`, and the deprecated module-level
  `gdspy.write_gds`. They are listed in
  [docs/migration_report.md](docs/migration_report.md) section 6.4.

## Licence

No licence file is included. The routing code is a reconstruction of the legacy
AutoRouter program. `gdspy`, `matplotlib`, `numpy`, `pandas`, `scipy`,
`openpyxl` and `PyQt5` remain under their own licences.
