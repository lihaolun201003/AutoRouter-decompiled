"""Assemble the original AutoRouter runtime used by the fidelity gate.

The bundle next to ``AutoRouter.exe`` holds everything the original program was
built from, but not in a runnable layout: the pure-Python packages live inside
``PYZ-00.pyz``, the compiled extensions sit loose at the top level, and there is
no interpreter executable.  This script puts them together behind the official
Python 3.8 embeddable interpreter, entirely inside ``_legacy_runtime/`` — no
installer runs and nothing on the system is touched.

Steps:

1. ``tools/extract_pyz.py`` unpacks ``PYZ-00.pyz`` into ``_legacy_runtime/pyz/``;
2. the official ``python-3.8.10-embed-amd64.zip`` is downloaded and extracted
   into ``_legacy_runtime/py38/``;
3. the bundle's compiled extensions (numpy, pandas, scipy, matplotlib, pytz,
   dateutil, ``kiwisolver.pyd``, ``gdspy/clipper.pyd``, and the shared libraries
   numpy links against) are merged into the same tree, and ``mpl-data`` is moved
   where matplotlib 3.2 expects it;
4. ``python38._pth`` is pointed at the merged tree.

Afterwards ``tools/legacy_runtime_trace.py`` and ``tools/exact_fidelity_gate.py``
can run the original bytecode.

Usage::

    .venv\\Scripts\\python.exe tools\\setup_legacy_runtime.py
"""

from __future__ import annotations

import argparse
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNTIME = PROJECT_ROOT / "_legacy_runtime"
PYZ_TREE = RUNTIME / "pyz"
PY38 = RUNTIME / "py38"
EMBED_URL = "https://www.python.org/ftp/python/3.8.10/python-3.8.10-embed-amd64.zip"
BUNDLE = Path(
    r"C:\Users\lihao\Desktop\Graduation Project\自动排布\AutoRouter"
)
PYZ_SOURCE = Path(
    r"C:\Users\lihao\Desktop\Graduation Project\自动排布\jiema\AutoRouter.exe_extracted\PYZ-00.pyz"
)
# Packages whose compiled parts live in the bundle directory.
COMPILED_PACKAGES = ["numpy", "pandas", "scipy", "matplotlib", "pytz", "dateutil", "gdspy"]
LOOSE_BINARIES = [
    "kiwisolver.cp38-win_amd64.pyd",
]
DLL_GLOBS = ["libopenblas*", "lib_blas_su*", "libbanded5x*", "msvcp140.dll",
             "libcrypto-1_1.dll", "libssl-1_1.dll"]


def step(message):
    print("== %s" % message)


def extract_pyz() -> None:
    step("extracting PYZ-00.pyz -> %s" % PYZ_TREE)
    sys.path.insert(0, str(PROJECT_ROOT / "tools"))
    import extract_pyz as tool

    tool.extract(PYZ_SOURCE, PYZ_TREE)
    # The tool prints one line per module; that is 1440 lines of noise here.
    print("   %d modules" % len(list(PYZ_TREE.rglob("*.pyc"))))


def fetch_embed() -> None:
    if (PY38 / "python.exe").is_file():
        print("== python 3.8 embeddable already present")
        return
    step("downloading %s" % EMBED_URL)
    archive = RUNTIME / "py38embed.zip"
    RUNTIME.mkdir(parents=True, exist_ok=True)
    if not archive.is_file():
        urllib.request.urlretrieve(EMBED_URL, archive)
    with zipfile.ZipFile(archive) as handle:
        handle.extractall(PY38)
    print("   extracted into %s" % PY38)


def merge_compiled() -> None:
    step("merging the bundle's compiled extensions")
    for name in COMPILED_PACKAGES:
        source = BUNDLE / name
        target = PYZ_TREE / name
        if source.is_dir() and target.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
            print("   %s" % name)
    for name in LOOSE_BINARIES:
        source = BUNDLE / name
        if source.is_file():
            module = name.split(".")[0].replace("-", "_")
            shutil.copy2(source, PYZ_TREE / (module + ".pyd"))
            print("   %s -> %s.pyd" % (name, module))
    if (BUNDLE / "gdspy" / "clipper.cp38-win_amd64.pyd").is_file():
        shutil.copy2(BUNDLE / "gdspy" / "clipper.cp38-win_amd64.pyd", PYZ_TREE / "gdspy" / "clipper.pyd")
        print("   gdspy/clipper.pyd")
    # numpy's extensions load OpenBLAS and the MSVC runtime from their directory.
    for pattern in DLL_GLOBS:
        for source in BUNDLE.glob(pattern):
            if source.is_file():
                shutil.copy2(source, PY38 / source.name)
    print("   shared libraries copied next to python.exe")

    # matplotlib 3.2 looks for its data inside the package directory.  The data
    # files are not in the PYZ (they are not code), so they come from the bundle.
    wanted = PYZ_TREE / "matplotlib" / "mpl-data"
    source_data = BUNDLE / "mpl-data"
    if source_data.is_dir():
        shutil.copytree(source_data, wanted, dirs_exist_ok=True)
        print("   mpl-data -> matplotlib/mpl-data (%d entries)"
              % len(list(wanted.iterdir())))
    elif not wanted.is_dir():
        raise SystemExit("mpl-data not found in the bundle: %s" % source_data)


def write_pth() -> None:
    step("pointing python38._pth at the merged tree")
    (PY38 / "python38._pth").write_text(
        "python38.zip\n.\n..\\pyz\n", encoding="ascii"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-download", action="store_true")
    args = parser.parse_args()
    if not PYZ_SOURCE.is_file():
        raise SystemExit("PYZ-00.pyz not found at %s" % PYZ_SOURCE)
    if not BUNDLE.is_dir():
        raise SystemExit("AutoRouter bundle not found at %s" % BUNDLE)

    RUNTIME.mkdir(parents=True, exist_ok=True)
    # Both the router module and a pure-Python package must be present: the
    # bundle directory only supplies compiled extensions, so a tree without
    # numpy/__init__.pyc is incomplete and has to be re-extracted.
    extracted = (PYZ_TREE / "problem_graph.pyc").is_file() and (
        PYZ_TREE / "numpy" / "__init__.pyc"
    ).is_file()
    if not extracted:
        extract_pyz()
    else:
        print("== PYZ tree already extracted")
    if not args.skip_download:
        fetch_embed()
    merge_compiled()
    write_pth()

    step("self-check")
    import subprocess

    result = subprocess.run(
        [str(PY38 / "python.exe"), "-c",
         "import sys, numpy, pandas; print(sys.version.split()[0], numpy.__version__, pandas.__version__)"],
        capture_output=True,
        text=True,
    )
    print("   " + (result.stdout.strip() or result.stderr.strip()))
    return 0 if result.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
