# Migration report — AutoRouter legacy 2D router → OpticalWaveguideRouter2D (Python 3.10.11)

Scope: reproduce the legacy **AutoRouter** 2D optical waveguide router on
Python 3.10.11 as a standalone project, using
the decompiled AutoRouter sources as the algorithmic baseline, and verify it against the
original executable and its real outputs.

---

## 1. Reference

### 1.1 Decompiled repository

The decompiled sources this project was reconstructed from — Python source
recovered from the Python 3.8 bytecode in `AutoRouter.exe` with
`pyinstxtractor` + `decompyle3` 3.9.3:

| File | Role |
| --- | --- |
| `app.py` | PyQt5 window: routing area, waveguide width/pitch/radius, channel count, input workbook, output folder, start button, log pane, result dialog |
| `main.py` | `Router(QThread)` pipeline: `create_sim_space → plotter_rect → plotter_bend → svg2gds_bend` |
| `problem_graph.py` | Excel input, `Port1`/`Port2`, 256/512 port tables, `above_list`/`below_list`, `index1`/`index2`, `sx`/`sy`/`lx`/`ly`/`dx`/`dz` |
| `wiring_rect_826.py` | tracks (`WGysets`), `MT`/`MTset`, `noCross`, `sn_calc`, `ln_calc`, the four routing passes, `plotter_rect`, `svg2dwgscr_rect` |
| `wiring_bend_826.py` | `plotter_bend` (bend tangent points, centres, theta) and `svg2gds_bend` (`gdspy.FlexPath`) |
| `waveguide_calculator.py` | `calc_index`, `calc_loss`, `draw_chart` |

### 1.2 The original executable (not just the source)

`C:\Users\lihao\Desktop\Graduation Project\自动排布\AutoRouter\` contains the
real `AutoRouter.exe` (19 Jun 2020) with its PyInstaller bundle:
`PYZ-00.pyz`, `base_library/`, `python38.dll`, the bundled `pandas`/`numpy`/
`matplotlib`/`gdspy`, plus the GUI resources and two genuine outputs:

- `resource/search.png`, `style/app.qss` — the original GUI icon and stylesheet
  (copied into this project unchanged)
- `fiberBoard0data.xlsx` — **the port placement the original wrote during a real
  run**
- `fiberBoard512_rect.pdf` — **the straight-routing figure the original wrote
  during the same run**

`jiema/AutoRouter.exe_extracted/` holds the extraction of the same exe. Both
`fiberBoard0data.xlsx` and `fiberBoard512_rect.pdf` are used as golden files in
this project. `AutoRouter.zip` in the same folder was not needed.

**Recovering the original bytecode** made the difference for this migration:
`tools/extract_pyz.py` pulls the unmarshalled code objects out of `PYZ-00.pyz`,
and `tools/raw_dis.py` / `tools/skeleton_dis.py` disassemble Python 3.8
bytecode with `xdis`. Wherever the decompiled listing looked wrong, the
bytecode settled it. Every repair in section 4 below is backed by an
instruction-level reading, and each one names the opcodes involved.

One trap worth recording: `xdis` renders 3.8 jump targets using 3.10 semantics,
and it exposes `co_cellvars`/`co_freevars` swapped, so `tools/raw_dis.py`
decodes `co_code` directly, resolves `EXTENDED_ARG` prefixes, treats `hasjabs`
as absolute byte offsets and `hasjrel` as deltas from the next instruction, and
rebuilds the deref namespace as `freevars + cellvars` (the order CPython uses
in `localsplus`).

---

## 2. Local 2D routing data

`OpticalWaveguideRouter3D\docs\2d_routing` (read-only) contains:

| File | Rows × cols | Use here |
| --- | --- | --- |
| `source_data/fiberBoard256.xlsx` | 256 × 2 (`Port1`, `Port2`) | real 256 input, copied to `data/` |
| `source_data/fiberBoard512.xlsx` | 512 × 2 | real 512 input, copied to `data/` |
| `source_data/fiberBoard0data.xlsx` | 512 × 11 | the original executable's own port-placement snapshot → golden file `data/fiberBoard0data.xlsx` |
| `README.md` | — | file index; states the 512 snapshot is the verified coordinate source and that no 256 snapshot exists |
| `parameters_and_ports.md` | — | verified parameters: 256 → 50 µm waveguide, 250 µm gap; 512 → 50 µm waveguide, 125 µm gap, 5 mm radius; 512 port formulas `(2 + 4.5c + 0.175j, 0)` below and `(4 + 4.5c + 0.175j, 150)` above |

Also used: `自动排布\fiberBoard256.xlsx` and `fiberBoard512.xlsx` have the same
SHA-256 as the copies above, so the inputs and the snapshot provably come from
the same run.

The SHA-256 in `README.md` for `fiberBoard0data.xlsx`
(`6901bd1f…f51efd66…`) turned out to be 63 characters long — a typo in that
document. The real digest of both the `source_data` copy and the
`AutoRouter\fiberBoard0data.xlsx` original is
`6901bd1f15388cf15831b57297be9a6a6f51ef1d661196e282dc5f1bbd6a8770`. The 256 and
512 digests match as documented.

No loss table, no index table and no 256 coordinate snapshot exist locally, so
those parts of `waveguide_calculator` are exercised with a clearly-labelled
placeholder table only (section 5).

---

## 3. Python 3.10 migration

| Item | Change |
| --- | --- |
| Interpreter | Python 3.10.11 in a project-local `.venv`; no Python 3.8 compatibility code kept |
| `numpy` | 2.2.6 — see the `np.float64` repr repair in section 4 |
| `pandas` | 2.3.3; `data.loc[(idx, cols)] = …` was rewritten as the equivalent `data.loc[idx, cols] = …` form, and `np.cross` on 2-D vectors was replaced by the module's own `det` |
| `matplotlib` | 3.10.9; both plotting modules default to the non-interactive **Agg** backend unless `MPLBACKEND` is set, because `Router` builds figures inside a `QThread` (matplotlib warns "Starting a Matplotlib GUI outside of the main thread will likely fail" otherwise). Outputs are identical |
| `gdspy` | 1.6.13, still the GDS backend (see 3.1) |
| `PyQt5` | 5.15.11, kept as PyQt5 (not migrated to PyQt6) |
| Paths | `./results`, `./resource/…`, `./style/…` replaced by paths derived from `Path(__file__).resolve().parent`; output names are joined with `Path`, never string concatenation. Works from any working directory, with spaces and non-ASCII in the path |
| Dependencies | `requirements.txt`; the environment installs on Python 3.10.11 from scratch |

### 3.1 gdspy and its C++ extension

`gdspy` 1.6.13 declares `gdspy/clipper.cpp` as a mandatory `ext_modules` entry
and PyPI publishes no Windows wheel, so `pip install gdspy` needs a C++
toolchain. No compiler exists on this machine (`cl`, `gcc`, `clang`, `tcc` all
absent), so the extension cannot be built.

Resolution: `tools/install_gdspy.py` installs the **unmodified official gdspy
sdist** and adds a small pure-Python `gdspy/clipper.py` so that
`from gdspy import clipper` — which `gdspy.path`, `gdspy.polygon` and
`gdspy.operation` perform at import time — succeeds. `gdspy` remains the GDS
backend; no other library replaces it, and no routing geometry changes.

The fallback is never reached on this code path, which was verified rather than
assumed: `FlexPath(..., corners="circular bend", gdsii_path=True)` followed by
`GdsLibrary.write_gds` takes the `gdsii_path` branch of `PathSet.to_gds`, which
does not call `to_polygonset`. Every `clipper` reference in gdspy 1.6.13
(`path.py` 558/567/889/898/2139/2148, `polygon.py` 358/367, `operation.py`
136/200/259/299) sits in polygon-conversion or `max_points`-splitting code, and
the reconstruction produced 256 and 512 GDSII paths with no exception
(section 5). Should a polygon job ever need it, the fallback raises
`NotImplementedError` with an explanatory message instead of returning wrong
geometry.

---

## 4. Decompiled-code repairs

Format: file — function — old problem — why it is a decompilation artefact —
fix — how it was verified.

### 4.1 `problem_graph.py` — `create_sim_space.find_next`

- **Old code**

  ```python
  for i in range(length):
      i = length - i - 1 if reverse else i
      if l[i] == value:
          return i
      print("didn't find the value %d, in " % value, l)
      return -1
  ```

- **Why**: `print`/`return -1` were rendered inside the loop, so the function
  would fall out of the first non-matching iteration. The bytecode shows
  `FOR_ITER` (offset 16, target byte 62) leaving the loop and landing on the
  `print`, i.e. those statements come *after* the loop; `POP_JUMP_IF_FALSE`
  (offset 50, target 16) is the loop-continue for the `if`.
- **Fix**: dedented both statements out of the loop; `find_next` now really
  searches the whole list.
- **Verified**: `tests/test_reconstruction.py::test_create_sim_space_matches_legacy_snapshot`
  (the port placement is bit-identical to the original snapshot) plus the
  direct check of the port-slot consumption in both real workbooks.

### 4.2 `problem_graph.py` — `create_sim_space.coarse_sort`

- **Old code**: nested `if`/`else` with `print("Port error")` hoisted out of the
  `else`, and `PORTS[i] = …` placed inside the loop body.
- **Why**: the bytecode jumps every failed condition of one neighbour test to
  the *next* test, and each accepted branch ends with `JUMP_ABSOLUTE` back to
  `FOR_ITER` — the signature of an `if`/`elif`/`elif`/`else` chain with the
  `print` as the final fallback. Bytecode line numbers confirm the two chains
  are lines 132-140 and 143-151.
- **Fix**: restored the `elif` chains and moved `PORTS[i] = np.sort(left)[::-1]
  .tolist() + np.sort(center).tolist() + np.sort(right)[::-1].tolist()` to after
  the branch, where the bytecode places it (line 152, after the `JUMP_FORWARD`
  that skips the `else` block).
- **Verified**: as 4.1 — a wrong neighbour order or a mis-sorted port list
  changes `sx`/`lx`, which the snapshot comparison would catch.

### 4.3 `wiring_rect_826.py` — the four routing passes, block placement

- **Old code**: `it = [iter(list_inflection[i]) for i in range(4)]` and
  `df["inflection"] = df.apply(lambda x: next(it[int(x.dz)]), axis=1)` appeared
  *inside* the `for row` loop, and in `wiring_rect_below2above` the
  `return df3` sat inside the innermost loop.
- **Why**: `list_inflection` only grows to four entries as the `for layer` loop
  runs, so indexing `list_inflection[1]` during layer 0 would raise
  `IndexError`, and the decompiled form cannot execute at all. The bytecode puts
  the block right after the outer loop: the `for layer` `FOR_ITER` (byte 80,
  `EXTENDED_ARG 1` then oparg 84, target byte 422) exits exactly onto the
  `MAKE_FUNCTION` of the line-129 list comprehension.
- **Fix**: moved `it`/`df["inflection"]`/the `f_inflection_*` assignments after
  the `for layer` loop in `wiring_rect_below`, `wiring_rect_above` and
  `wiring_rect_above2below`; `wiring_rect_below2above` now runs to the end of
  the function. The `f_inflection_x`/`f_inflection_y` bodies (including which
  ones have the `dx == 0` two-point branch) are unchanged.
- **Verified**: all four passes now execute and produce four-point polylines for
  all 256/512 routes; the block placement is additionally confirmed by the two
  passes that now reproduce the legacy figure exactly (section 6).

### 4.4 `wiring_rect_826.py` — `noCross`, sibling `if` statements

- **Old code**: the second test of the `below` and `above` sweeps was nested
  *inside* the first one.
- **Why**: in the bytecode both tests push every failed condition to the same
  target — `POP_JUMP_IF_FALSE` at offsets 62/76/98/120 all go to byte 128 for
  `below`, and offsets 542/558/582/606/630/654 all go to byte 522 for `above` —
  so they are two flat `and` chains that both run on every loop iteration, not a
  nested pair. Each test has exactly one `return False` block (bytes 122-126 and
  180-184); the nested reading would have needed a separate one for each level.
- **Fix**: rewrote `noCross` with flat `and` chains in all four branches, and
  verified every loop bound and constant at the same time:
  `range(1, max(ln_calc(lx, ly) - sn_calc(lEnd + 1, WGyset[i].y), 4))` and
  `range(1, 8)` for `below`; `…, 3)` and `range(1, 6)` for `above2below`;
  `…, False), 4)` and `range(1, 8)` for `above`; `range(1, 6)` and `…, False), 3)`
  for `below2above` — matching the decompiled text exactly.
- **Verified**: this repair is what makes the routing match the original. Before
  it, `above→above` and `below→above` disagreed with the legacy figure on many
  routes; after it both reproduce **every** route's inflection track
  (section 6).

### 4.5 `wiring_bend_826.py` — `plotter_bend.dir_norm`

- **Old code**: `return a` inside the loop, so only `a[0]` was ever normalised.
- **Why**: the `FOR_ITER` (offset 12) exits onto byte 60 = `LOAD_FAST a;
  RETURN_VALUE`, i.e. the `return` is after the loop; inside the body the
  `if a[i] > 0` / `if a[i] < 0` branches end with `JUMP_ABSOLUTE` to the loop
  start.
- **Fix**: dedented `return a` out of the loop.
- **Verified**: all four quadrant direction tuples
  `(-1,-1) (1,-1) (1,1) (-1,1)` appear in the real runs, and
  `tests/…::test_bend_geometry` pins the tangent-point/theta values for a known
  corner. With the broken version every direction would have been `(1,1)`-like
  and `dir_map.index()` would have failed on most routes.

### 4.6 `wiring_bend_826.py` — the theta comprehension lost its `and`

- **Old code**

  ```python
  [calc_theta(dx, d) if dx != 0 else theta_map[dir_map.index(d)]
   for d in dir_list if dx < bend_radius * 2]
  ```

- **Why**: the list comprehension code object (line 196) has no filter: it runs
  `dx < bend_radius * 2` and then `dx != 0` as a short-circuit chain
  (`POP_JUMP_IF_FALSE` at offsets 18 and 26 both to byte 38), with
  `calc_theta(dx, d)` in the `then` slot. So the condition belongs to the
  ternary, and the list is always as long as `dir_list`.
- **Fix**: `calc_theta(dx, d) if dx < bend_radius * 2 and dx != 0 else
  theta_map[dir_map.index(d)]`, with no filter clause — in both the drawing loop
  and the `df["theta"]` column (whose inner list comprehension at line 211 has
  the same shape).
- **Verified**: the decompiled form leaves `theta_list` empty whenever
  `dx >= 2R` while `center_list` still holds two entries, so `theta_list[k]`
  raises `IndexError` — the legacy figure could not have been produced that way.
  `tests/…::test_bend_geometry_at_dx_equal_diameter` and
  `…::test_bend_geometry_below_diameter` pin both branches, and the real runs
  produce `len(theta) == len(center) == 2` for all 768 routes.

### 4.7 `wiring_bend_826.py` — NumPy 2 scalar representation in the workbook

- **Old code**: the per-waveguide geometry was written with the NumPy scalars
  still in place.
- **Why**: this is a Python-3.10-era API difference rather than a decompiler
  artefact. NumPy 1 renders `np.float64(1.5)` as `1.5`; NumPy 2 renders the
  wrapper, so a stored list cell reads `[np.float64(138.8), …]` and
  `ast.literal_eval` — which `waveguide_calculator.calc_index` uses to read the
  workbook back — rejects it with *malformed node or string*.
- **Fix**: `wiring_bend_826.plain()` converts NumPy scalars to Python scalars for
  `dir`, `bend_x`, `bend_y`, `center` and `theta`; `wiring_rect_826.plotter_rect`
  does the same for `inflection_x`/`inflection_y`. Values are numerically
  identical (`.item()`), so the geometry is unchanged and the workbook returns
  to the legacy plain-number text.
- **Verified**: `tests/…::test_workbook_stays_literal_eval_readable` and the
  `literal_eval` checks in `tools/verify_reconstruction.py` (4 columns × 2 board
  sizes), plus `calc_index` successfully reading a real 512 workbook.

### 4.8 `waveguide_calculator.py` — `calc_crossing` had no return

- **Old code**: the whole body sat behind `if os.getenv("DEBUG") == "True":`, and
  the function then fell off the end.
- **Why**: the bytecode ends at offset 280 with `RETURN_VALUE` inside the DEBUG
  block (line 147); there is no trailing `return`. This is an original defect,
  not a decompiler artefact — but it makes `calc_index` raise
  `TypeError: object of type 'NoneType' has no len()` on `len(x.angles)` for
  every route, which is consistent with the legacy GUI never calling
  `calc_index`.
- **Fix**: the non-debug path returns `[]`, which is exactly how the debug path
  itself spells "not analysed" (`if row.name != 56: return []`). The debug path
  is untouched.
- **Verified**: `tests/…::test_calc_index_length_column` and
  `…::test_draw_chart_writes_three_plots` run `calc_index` and `draw_chart` on a
  real 512/256 workbook.

### 4.9 `waveguide_calculator.py` — 2-D cross product

- **Old code**: `np.cross(p2 - p1, p1 - p0)`.
- **Why**: NumPy 2 deprecates the 2-D cross product (removed in later releases).
  The 2-D cross product is the determinant the module already defines as `det`.
- **Fix**: `det(p2 - p1, p1 - p0)`, mathematically identical.
- **Verified**: `tests/…::test_waveguide_calculator_helpers` checks `det`,
  `is_cross` and `is_fall_on` on known geometry.

### 4.10 `app.py` — GUI defects

- **`ButtonLineEdit.resizeEvent`** passed `(self.rect().bottom() - … ) / 2` (a
  `float`) to `QToolButton.move`; PyQt5 on Python 3.10 raises `TypeError`. Fixed
  with `int(...)`. Verified by constructing the window
  (`tests/…::test_gui_launches_and_routes`).
- **Resource paths** `./resource/search.png` and `./style/app.qss` were opened
  relative to the working directory and would crash the window if missing. Now
  resolved from the project directory with fallbacks (a `...` text button, a
  built-in stylesheet). Verified by launching the GUI from a different working
  directory.
- **Result dialog** built `SaveFolder + "/" + name`; now uses `Path` and reports
  a missing image instead of showing an empty label.
- **Silent thread death**: routing exceptions killed the worker with no visible
  error. `Router.error` was added, `run()` wraps the pipeline in `try`, and the
  GUI logs the traceback and shows a message box.
- **Spin boxes started at zero** as decompiled (a zero routing area cannot
  route), so all six fields now start at the documented 512-channel values, and
  `InputPanel.validate()` checks the channel count, the input file, the output
  folder and the positivity of area/width/pitch/radius before starting.
- **`Viewer()`** is a function containing nested `__init__`/`initUI` definitions
  and is never called in the original either; it is kept as an inert
  placeholder rather than inventing behaviour for it.

### 4.11 Path handling — the missing separator (requested repair)

`plotter_rect` wrote `save_folder + "fiberBoard" + str(N) + "rect.xlsx"` and
`plotter_bend` wrote `save_folder + file_name + ".xlsx"` (no separator, while
its PNG/PDF used `+ "/" +`), and `create_sim_space` wrote `"./fiberBoard0data.xlsx"`
relative to the working directory. With a GUI-chosen folder the legacy program
therefore produced names such as `resultsfiberBoard256bend.xlsx`. All output
paths now go through `Path(folder) / name`; the file names themselves are
unchanged. `fiberBoard0data.xlsx` is written into the requested output folder
instead of the working directory. Verified by running from three different
working directories.

---

## 5. End-to-end results

Both boards were run through the full pipeline
(`create_sim_space → plotter_rect → plotter_bend → svg2gds_bend`) on the real
workbooks. Command:

```powershell
.\.venv\Scripts\python.exe main.py --input data\fiberBoard<N>.xlsx --channels <N> --output results
```

### 256 channels

```
input     = data/fiberBoard256.xlsx        (SHA-256 50dadf81426b3a1e56b67ff827809c4a3ab4af92e9b05da411072f850cce9a8b)
params    = line_width 0.05 mm, pitch 0.25 mm, bend_radius 5 mm, area 150x150 mm
routes    = 256 (122 distinct port pairs, all present in the input)
lines     = 467 candidate tracks of 0.3 mm pitch, 243 used, 10 shared without overlap
output PNG= results/fiberBoard256bend.png        81 709 B  960x720, 20.3% non-white
output PDF= results/fiberBoard256bend.pdf        72 748 B
output XLSX= results/fiberBoard256bend.xlsx      37 073 B  (256 rows)
intermediate= results/fiberBoard256rect.xlsx, results/fiberBoard256_rect.pdf, results/fiberBoard0data.xlsx
output GDS= results/fiberBoard256bend.gds        67 188 B
runtime   = 3.08 s
status    = PASS (36/36 checks in tools/verify_reconstruction.py)
```

### 512 channels

```
input     = data/fiberBoard512.xlsx        (SHA-256 71a19ec1739de75453608d1d9bd0bb2b9ad102140e4af5057c12e60c0accd7ff)
params    = line_width 0.05 mm, pitch 0.125 mm, bend_radius 5 mm, area 150x150 mm
routes    = 512 (244 distinct port pairs, all present in the input)
lines     = 800 candidate tracks of 0.175 mm pitch, 475 used, 25 shared without overlap
output PNG= results/fiberBoard512bend.png       126 415 B  960x720, non-blank
output PDF= results/fiberBoard512bend.pdf       138 154 B
output XLSX= results/fiberBoard512bend.xlsx      71 571 B  (512 rows)
intermediate= results/fiberBoard512rect.xlsx, results/fiberBoard512_rect.pdf, results/fiberBoard0data.xlsx
output GDS= results/fiberBoard512bend.gds       134 260 B
runtime   = 4.65 s
status    = PASS (36/36 checks in tools/verify_reconstruction.py)
```

### GDSII re-read verification

The produced GDSII files were reopened with `gdspy.GdsLibrary(infile=…)`:

| File | Cells | Paths | Polygons | Bounding box |
| --- | --- | --- | --- | --- |
| `fiberBoard256bend.gds` | `wiring896` | 256 | 256 | `[[1.473, -0.0016], [146.527, 150.0]]` |
| `fiberBoard512bend.gds` | `wiring896` | 512 | 512 | `[[1.975, -0.0016], [149.152, 150.0]]` |

One `FlexPath`/`GdsPath` per routed waveguide, all inside the routing area, and
the flex paths keep `width = 0.05`, `bend_radius = 5`,
`corners = "circular bend"`.

### Acceptance checks (`tools/verify_reconstruction.py`, 36 per board)

Passing for both board sizes: PNG exists / is at least 100×100 / is not blank /
has more than 50 distinct colours; PDF exists / has a `%PDF-` header / is larger
than 2 KB; the workbook has one row per route; the GDS exists / is non-empty /
has one cell / has one path per route / has a finite bounding box; and for the
routing table: `inflection_x`, `inflection_y`, `center` and `theta` parse with
`ast.literal_eval`, `sx`/`lx`/`dx`/`inflection`/`ln` are finite, the inflection
arrays are four long and equal-length, no two routes overlap on the same track,
the number of distinct tracks is plausible, every inflection lies inside the
routing area, and the routed port pairs equal the input workbook's.

### Other levels

- **Level A** — `python -m compileall` over the six modules, `tests` and `tools`: clean.
- **Level B** — `import problem_graph`, `wiring_rect_826`, `wiring_bend_826`,
  `waveguide_calculator`, `main`, `app`: all succeed on Python 3.10.11.
- **Level C** — port placement: no NaN/Inf, `sx ∈ [6.5, 146.0]`, `lx ∈ [2.0, 141.5]`,
  `sy`/`ly` ∈ {0, 150}, `index1`/`index2` in range, `dx > 0`, `dz == 0` everywhere
  (see section 6.4).
- **Level D** — straight routing: 4 inflections per route, all inside the area,
  no overlapping runs per track.
- **Level E** — bends: 2 tangent pairs, 2 centres, 2 theta spans per route, all
  finite, `0 ≤ start < stop ≤ 2π`.
- **Level F / G** — GDS above; end-to-end above.

### Tests

`python -m pytest tests -q` → **21 passed**. The suite runs the real pipeline on
the real workbooks; there are no mocks of `create_sim_space`, `plotter_rect`,
`plotter_bend` or `gdspy`.

### `waveguide_calculator` on real data

`calc_index` runs on a real 512 workbook and produces finite per-route lengths
(propagation + bend). **not available**: a crossing-angle loss table and an
index table. The test that exercises `calc_index` therefore passes an explicitly
labelled placeholder loss table containing a single 90° entry; it proves the
workbook round trip, the length formula and the lookup path, and is **not** a
validated loss figure.

---

## 6. Comparison with the original executable

### 6.1 Resolved: the routing is exact against the original program

The one-track difference described in earlier revisions of this report was
**not** a defect in the reconstruction.  It was traced to the reference figure:
`AutoRouteriberBoard512_rect.pdf` (2020) was produced by a *different build*
of AutoRouter than the executable that was decompiled.

The resolution came from running the original program itself.  `_legacy_runtime/`
assembles the official Python 3.8.10 embeddable interpreter with the pure-Python
packages extracted from `PYZ-00.pyz` and the bundle's own compiled extensions
(NumPy 1.18.5, pandas 1.0.4, matplotlib, scipy, gdspy with its real C++
clipper), so the original `problem_graph` / `wiring_rect_826` /
`wiring_bend_826` code objects run as they were built.  Its outputs were then
diffed against the reconstruction, and `sys.settrace` was used to compare
internal state route by route without editing the original bytecode.

| Stage | Result |
| --- | --- |
| `create_sim_space` vs the 2020 snapshot | 512/512 rows, identical index labels, max column delta **0** |
| `plotter_rect` vs the original code run | **512/512 routes on the identical track** (112/112, 112/112, 115/115, 173/173 per pass), first mismatch: none |
| `plotter_bend` vs the original code run | `inflection_x/y`, `dir`, `bend_x`, `bend_y`, `center`, `theta` all 512/512 identical; `sx`, `lx`, `dx`, `inflection`, `ln` max delta 0 |
| `svg2gds_bend` vs the original code run | 512/512 paths with identical point arrays and widths; identical file size; only the 8 `BGNLIB`/`BGNSTR` timestamp bytes differ |
| `wiring_rect_below` internal state | identical `nodes.MTbelow` after every one of the 112 routes (max delta 0) |

The 2020 figure agrees with the original program on `above→above` (112/112) and
`below→above` (115/115) but differs on `below→below` (62 of 112 one track
higher) and, as a pure consequence of `below_line = max(df2["inflection"])`, on
all of `above→below`.  Both differing passes are exactly the ones that resolve
their crossing test against `nodes.MTbelow`, which localises the older build's
difference to that single term.

No code change was made for this: matching the 2020 figure would mean guessing
at an earlier algorithm and would break fidelity with the executable this
project reproduces.  Full evidence, including the hypotheses tested and
rejected, is in
[exact_legacy_fidelity_report.md](exact_legacy_fidelity_report.md) and
[debug_first_divergence.md](debug_first_divergence.md); the gate that keeps it
true is `tools/exact_fidelity_gate.py`.

### 6.2 Behaviour that cannot be compared at all

- **No 256 reference figure or snapshot exists** locally (the local documents
  state this explicitly), so the 256 routing can only be checked by the
  invariants above, not against the original. The 256 port table itself is shared
  with the decompiled source, and the 512 snapshot validates the same code path.
- **Unrouted connections**: neither board produced any. With `dz == 0`
  everywhere, a track is always found inside `[5, 145] mm`, and the checks confirm
  every route has four finite inflections. The legacy program has no "unrouted"
  marker, so this situation cannot be represented and was not invented.
- **Loss / index numbers**: no loss table, no index table, no coupling data
  (section 5). The propagation coefficient (0.05 dB/cm) and the 90° bend table
  inside `calc_loss` are the legacy constants, unchanged.

### 6.3 Layer (`dz`) behaviour, kept as found

`create_sim_space` assigns `dz = 0` to every connection, and no other module
writes `dz` (checked instruction by instruction in `wiring_rect_826.pyc`). The
four-layer machinery — `WGysets[layer]`, the four `for layer in range(4)` loops
per pass and the four-colour figure — is therefore present but only layer 0 ever
holds geometry, exactly as in the legacy program. It was not deleted, and no
layer assignment was invented.

### 6.4 Smaller things carried over deliberately

- `create_sim_space` in the reference module defines the function twice; the
  second definition (256/512) shadows the first (896 channels, `Port1` strings
  like `SC-MT-SN`). The dead first definition is kept as
  `create_sim_space_896_legacy()` with a docstring saying it is unreachable and
  superseded — behaviour is identical, and the 896 layout stays available for
  comparison. Supporting it is not attempted: `create_sim_space` now raises a
  `ValueError` mentioning "256 and 512" for any other channel count instead of
  failing later with a `NameError`.
- `wiring_rect_above2below` computes `it = [iter(sx[i]) for i in range(4)]` and
  never uses it, so its re-ordered `sx` is deliberately not written back. Kept.
- `draw_chart` still scales the fitted curve with `int(filename)`, so `filename`
  must be a numeric string such as `"256"`; unchanged.
- `svg2dwgscr_rect` is ported although the pipeline never calls it; it now writes
  through `Path` into the save folder.
- `data.to_excel(...)` for `fiberBoard0data.xlsx` intentionally does **not**
  reset the index, matching the original snapshot's index column.
- `pd.concat` order is `[df2, df4, df3, df5]` and rows keep their original
  labels — the `WGs` bookkeeping depends on that.
- `Router` keeps its original name, constructor signature, `logger` and `finish`
  signals; `error` and the intermediate `df`/`df_rect`/`df_bend` attributes are
  additions. `run()` is wrapped in `try`, so an exception is reported instead of
  killing the thread.
- `gdspy.write_gds` (the deprecated module-level call the legacy program used)
  is kept instead of `GdsLibrary.write_gds`; it emits a `DeprecationWarning`
  under gdspy 1.6.13, which is harmless and stable, since 1.6.13 is gdspy's last
  release. Routing geometry is unaffected.
- The `-0.0` value `sn_calc` can return for slot 0 (`return -i` with `i == 0`)
  is preserved: `-0 == 0`, so it behaves as slot 0 either way.

### 6.5 One documentation error found in the source material

`docs/2d_routing/README.md` records a 63-character SHA-256 for
`fiberBoard0data.xlsx` (a typo, see section 2). The file itself is genuine and
matches the copy shipped inside `AutoRouter/`.

---

## 7. Reproducing this report

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe tools\install_gdspy.py
.\.venv\Scripts\python.exe main.py --input data\fiberBoard256.xlsx --channels 256 --output results
.\.venv\Scripts\python.exe main.py --input data\fiberBoard512.xlsx --channels 512 --output results
.\.venv\Scripts\python.exe tools\render_debug_map.py 256 --output results
.\.venv\Scripts\python.exe tools\render_debug_map.py 512 --output results
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe tools\verify_reconstruction.py 256 --output results
.\.venv\Scripts\python.exe tools\verify_reconstruction.py 512 --output results
.\.venv\Scripts\python.exe tools\compare_with_legacy_pdf.py 512 --output results
```

For the bytecode work, clone the reference repository next to this project and
point the tools at the exe:

```powershell
# the decompiled sources are the commit before the reconstruction in this
# repository; check it out to cross-check function by function
git worktree add _reference <decompiled-commit>
.\.venv\Scripts\python.exe tools\extract_pyz.py `
    "C:\Users\lihao\Desktop\Graduation Project\自动排布\jiema\AutoRouter.exe_extracted\PYZ-00.pyz" `
    _reference\bytecode --only problem_graph wiring_rect_826 wiring_bend_826 waveguide_calculator
.\.venv\Scripts\python.exe tools\raw_dis.py _reference\bytecode\wiring_rect_826.pyc noCross sn_calc ln_calc
```

`OpticalWaveguideRouter3D` was not modified: only
`docs/2d_routing` was read from it.
