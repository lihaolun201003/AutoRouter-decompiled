# Exact legacy fidelity report — AutoRouter 2D on Python 3.10.11

## Summary

The Python 3.10 reconstruction is **bit-identical to the original AutoRouter**
on the 512-channel board, all the way from the input workbook to the GDSII
file. This was established by running the original program itself: the
`wiring_rect_826` / `wiring_bend_826` / `problem_graph` code objects recovered
from `AutoRouter.exe`'s `PYZ-00.pyz` were executed under the exact interpreter
and libraries they were compiled against, and its outputs were diffed against
the reconstruction's.

| Stage | Comparison | Result |
| --- | --- | --- |
| `create_sim_space` | original snapshot `fiberBoard0data.xlsx` (2020) | 512/512 rows, identical index labels, max column delta **0** |
| `plotter_rect` | original code run under Python 3.8.10 / NumPy 1.18.5 / pandas 1.0.4 | **512/512 routes on the identical inflection track**, first mismatch: none |
| `plotter_bend` | same | `inflection_x`, `inflection_y`, `dir`, `bend_x`, `bend_y`, `center`, `theta` all **512/512 identical**; `sx`, `lx`, `dx`, `inflection`, `ln` max delta **0** |
| `svg2gds_bend` | same | 512/512 paths with **identical point arrays and widths**; file size identical; only the 8 timestamp bytes of `BGNLIB`/`BGNSTR` differ |

Per-pass breakdown against the original code run:

```
below->below  total=112  exact=112  +1=0  -1=0  other=0
above->above  total=112  exact=112  +1=0  -1=0  other=0
below->above  total=115  exact=115  +1=0  -1=0  other=0
above->below  total=173  exact=173  +1=0  -1=0  other=0
overall       total=512  exact=512  +1=0  -1=0  other=0
```

Gate command:

```powershell
.\.venv\Scripts\python.exe tools\exact_fidelity_gate.py      # exit 0, "FROZEN GROUPS: OK"
```

## Root cause: the reference figure, not the reconstruction

Before this investigation the reconstruction was compared against
`AutoRouter\fiberBoard512_rect.pdf`, a figure dated 2020 that ships next to the
executable, and it agreed on only 266/512 routes (235 off by exactly one
track).  That gap was **not** a defect in the reconstruction. The 2020 figure
was produced by a **different build** of AutoRouter than the one that was
decompiled, and it contradicts the decompiled program's own behaviour:

| Pass | 2020 figure vs current reconstruction |
| --- | --- |
| `above->above` | 112/112 exact |
| `below->above` | 115/115 exact |
| `below->below` | 39 exact, 62 off by +1 track, 11 by more |
| `above->below` | 0 exact, **all 173 off by exactly +1 track** |

The two passes that agree are the two that resolve their crossing test with
`sn_calc(..., isBelow=False)`, i.e. against `nodes.MTabove`; the two that differ
are the ones that read `nodes.MTbelow` (`below->below` directly, and
`above->below` indirectly through `below_line = max(df2["inflection"])`, which
shifts every one of its 173 tracks by the same amount). In other words the 2020
build's behaviour differs **only** inside the `MTbelow`-based branch of
`noCross`, and the `above->below` block is a pure consequence of that single
divergence. That is consistent with the whole gap having one cause, as
suspected.

Because the reconstruction matches the decompiled program exactly, no code
change was made and none is warranted: the only way to match the 2020 figure
would be to guess at an earlier algorithm, which would break fidelity with the
executable that is actually being reproduced.

## Bytecode evidence collected along the way

The investigation needed the original program's intermediate state, which came
from three sources, strongest first.

### 1. Running the original bytecode under the original runtime

`_legacy_runtime/` assembles:

* **interpreter**: the official Python 3.8 embeddable package
  (`python-3.8.10-embed-amd64.zip`, extracted into the project, no installer and
  no system change);
* **pure-Python packages**: extracted from `PYZ-00.pyz` with
  `tools/extract_pyz.py`; the extractor had to be fixed to place a package's
  code object in `pkg/__init__.pyc` rather than `pkg.pyc`, because PyInstaller
  names a package after itself and flags it with `ispkg`;
* **compiled extensions**: `numpy/core/*.cp38-win_amd64.pyd`,
  `pandas`, `scipy`, `matplotlib` and `kiwisolver` taken from the bundle
  directory, plus `gdspy/clipper.cp38-win_amd64.pyd` (the real C++ clipper);
* `matplotlib/mpl-data` moved next to the `matplotlib` package.

Result: the original modules import and run, reporting
`Python 3.8.10 / numpy 1.18.5 / pandas 1.0.4` — the very versions the exe was
built against.

`tools/legacy_runtime_trace.py` runs the whole `Router` pipeline with that
stack and records internal state through `sys.settrace`, without editing the
original bytecode:

* every accepted `below -> below` route: dataframe label, `idx1`/`idx2`,
  `sx`/`lx`, chosen `w.y` and its track index, `w.rEnd`, `w.lEnd`, `w.WGs`;
* the full `nodes.MTbelow` array after every accepted route;
* every `noCross` call with its arguments and result.

`tools/reconstruction_trace.py` records the identical structure from the
reconstruction. `sys.settrace` is used because the decision logic is nested
inside `plotter_rect` and cannot be monkey-patched from outside; the two
tracers key on the accept line of `wiring_rect_below`
(legacy source line 126 `list_inflection[layer] += [w.y]`, reconstruction line
277) which is where the chosen track becomes observable.

### 2. State diff — identical, route for route

```
routes: legacy=112  mine=112
processing-order labels identical: True
ports / idx1 / idx2 identical:      True
sx / lx max difference:             0 / 0
routes with a different track:      0 / 112
nodes.MTbelow snapshots max delta:  0
```

So the input state, the row order, the candidate scan and the resulting
`MTbelow` bookkeeping are all reproduced exactly.

### 3. What the bytecode already pinned down

Every condition the earlier analysis had to reconstruct from disassembly was
re-confirmed while building the runtime: `noCross`'s two flat `and` chains per
sweep (the decompiler had nested them), its four loop bounds
(`max(ln_calc - sn_calc, 4)` / `range(1, 8)` for `below`, `…, 3)` /
`range(1, 6)` for `above2below`, `…, False), 4)` / `range(1, 8)` for `above`,
`range(1, 6)` / `…, False), 3)` for `below2above`), the ascending scan for
`below` and the descending scan for `above`, the `w.y >= above_line` and
`w.y < below_line` guards, `sn_calc`'s `MTbelow`/`MTabove` selection and its
`>=` comparisons, `init_MT_set` (`MTabove.y = [0] * 16`,
`MTbelow.y = [height] * 16`) and `add_port`'s `int(index - N / 16)` routing.

## Hypotheses tested and rejected

Each of these was checked against the original program's behaviour rather than
reasoned about:

| Hypothesis | Test | Result |
| --- | --- | --- |
| Row order / tie-breaking in `sort_values` differs | processing-order label sequences from both tracers | identical |
| Float representation or `list.index` picks a different slot | slot indices and resulting `nodes.MTbelow` arrays | identical (max delta 0) |
| pandas ≥ 2 calls an `apply(lambda …, axis=1)` twice on the first row | instrumented counter on both pandas 1.0.4 and 2.3.3 | never called twice |
| `dataclass` field order / shared mutable defaults differ between 3.8 and 3.10 | `WGyset`/`MT`/`MTset` layouts confirmed from bytecode; object state compared through the tracers | identical |
| NumPy 2 `repr` change masks a real geometry difference | `flat()`/`plain()` conversions compared column by column against the original | numerically identical; only the workbook text form was affected (already repaired) |
| `sn_calc` uses `>` instead of `>=` | variant run under both interpreters | no effect; track values never fall exactly on a tolerance boundary |
| The 2020 build predates the `sn_calc` term in the `noCross` loop bound | controlled variant with the term removed, compared to the 2020 figure | 43/512 exact — far worse, hypothesis rejected |

## Regression status

Nothing in the routing, bend or GDS code was changed for this hotfix; the only
edits are the new tools (`tools/legacy_runtime_trace.py`,
`tools/reconstruction_trace.py`, `tools/exact_fidelity_gate.py`) and the
`pkg/__init__.pyc` fix in `tools/extract_pyz.py`. The frozen groups therefore
hold by construction, and the gate re-verifies them on every run:

```
create_sim_space          exact (max column delta 0)
above->above              112/112
below->above              115/115
below->below              112/112
above->below              173/173
overall                   512/512
bend columns              all identical
GDSII                     512/512 identical paths, 8 timestamp bytes differ
```

`python -m pytest tests -q` → 21 passed; `tools/verify_reconstruction.py 256`
and `512` → 36/36 each; `compileall` and the six core imports are clean; the
GUI starts and routes; the CLI runs both boards.

## Reproducing it

```powershell
# original runtime (once): extract the PYZ, unpack the official 3.8 embeddable
.\.venv\Scripts\python.exe tools\extract_pyz.py `
    "C:\Users\lihao\Desktop\Graduation Project\自动排布\jiema\AutoRouter.exe_extracted\PYZ-00.pyz" `
    _legacy_runtime\pyz
# then merge the bundle's compiled extensions into _legacy_runtime\pyz
# (numpy, pandas, scipy, matplotlib, pytz, dateutil, mpl-data, gdspy/clipper.pyd)

# ground truth: the original program, traced
_legacy_runtime\py38\python.exe tools\legacy_runtime_trace.py `
    --out scratch\legacy_full.json --channels 512 --full
# the reconstruction, traced the same way
.\.venv\Scripts\python.exe tools\reconstruction_trace.py --out scratch\mine.json --channels 512
# the gate
.\.venv\Scripts\python.exe tools\exact_fidelity_gate.py
```

## Files added for this hotfix

| File | Purpose |
| --- | --- |
| `tools/legacy_runtime_trace.py` | run the original bytecode under the original runtime; trace routes, `noCross`, `MTbelow` |
| `tools/reconstruction_trace.py` | the same trace from the reconstruction, for a route-by-route state diff |
| `tools/exact_fidelity_gate.py` | the fidelity gate: snapshot, per-pass track counts, bend columns, GDSII, frozen groups |
| `docs/debug_first_divergence.md` | the state evidence behind the conclusion above |
| `tools/setup_legacy_runtime.py` | rebuilds `_legacy_runtime/` from the bundle (PYZ extraction, Python 3.8 embeddable, compiled extensions, `mpl-data`) |
| `docs/legacy_2020_fiberBoard512_rect.pdf` | the 2020 figure kept for reference; note the `2020` in the name — it is **not** the authoritative reference |
