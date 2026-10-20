# Historical AutoRouter decompilation

The recovered source is maintained in one canonical location:
[OpticalWaveguideRouter2D/_reference](../../../OpticalWaveguideRouter2D/_reference/).
That directory retains `app.py`, `main.py`, `problem_graph.py`,
`waveguide_calculator.py`, `wiring_bend_826.py`, and `wiring_rect_826.py`.

The source was recovered from the Python 3.8 bytecode packaged in `AutoRouter.exe`
using [pyinstxtractor](https://github.com/extremecoders-re/pyinstxtractor) and
decompyle3. The original executable is retained at
[自动排布/AutoRouter/AutoRouter.exe](../../AutoRouter/AutoRouter.exe).
Bundled dependencies and private input data are not included.

On 2026-10-20 the byte-for-byte duplicate source files and `jiema/AutoRouter.exe`
copy were removed. This README preserves the old directory as a navigation entry.
The original decompilation caveats are preserved in the canonical directory's
README; runnable reconstructed code and validation reports are in
[OpticalWaveguideRouter2D](../../../OpticalWaveguideRouter2D/).
