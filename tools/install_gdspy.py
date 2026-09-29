"""Install gdspy into the current environment without its C++ extension.

``gdspy`` ships ``gdspy/clipper.cpp`` as a mandatory ``ext_modules`` entry, so
``pip install gdspy`` needs a C++ toolchain.  This machine has none, which
would make the whole GDSII export unavailable.

The extension is only used by the *polygon* code paths (``to_polygonset``,
``offset``, ``clip``, ``inside``, and the ``max_points`` splitting of large
polygons).  ``FlexPath(..., corners="circular bend", gdsii_path=True)`` followed
by ``GdsiiLibrary.write_gds`` -- exactly what the legacy router does -- never
touches it.

This script therefore installs the **unmodified official gdspy source** and adds
a pure-Python ``gdspy/clipper.py`` fallback so that
``from gdspy import clipper`` succeeds.  Every function in the fallback raises
``NotImplementedError`` with an explanatory message, so a polygon job fails
loudly instead of silently producing wrong geometry.

Usage::

    python tools/install_gdspy.py               # download gdspy 1.6.13 from PyPI
    python tools/install_gdspy.py <sdist.zip>   # use a local source archive
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

GDSPY_VERSION = "1.6.13"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

FALLBACK_MODULE = '''"""Pure-Python fallback for gdspy's optional C++ ``clipper`` extension.

The upstream extension is built from ``clipper.cpp`` and provides the polygon
boolean/offset operations.  It could not be compiled in the environment where
this project was reconstructed (no C++ toolchain available), so this module
exists purely so that ``from gdspy import clipper`` -- which ``gdspy.path``,
``gdspy.polygon`` and ``gdspy.operation`` all perform at import time -- keeps
working.

Paths created with ``gdsii_path=True`` (what this project uses) are written
straight to GDSII by ``gdspy.path.PathSet.to_gds`` and never call into this
module.  Anything that genuinely needs polygon clipping will raise instead of
returning wrong geometry.
"""

HELP = (
    "gdspy's C++ clipper extension is not available in this environment "
    "(no C++ compiler was found when the package was installed). "
    "Polygon boolean/offset operations are therefore unavailable. "
    "FlexPath with gdsii_path=True and GdsLibrary.write_gds do not need them."
)


def _unavailable(*args, **kwargs):
    raise NotImplementedError(HELP)


clip = _unavailable
offset = _unavailable
inside = _unavailable
_chop = _unavailable


class _ClipperError(RuntimeError):
    """Mirror of the exception type the C++ extension exposes."""


def _self_check() -> None:
    try:
        import numpy  # noqa: F401
    except ImportError:  # pragma: no cover - numpy is a hard dependency
        pass


_self_check()
'''


def _download_sdist(destination: Path) -> Path:
    meta_url = f"https://pypi.org/pypi/gdspy/{GDSPY_VERSION}/json"
    with urllib.request.urlopen(meta_url) as response:
        meta = json.load(response)
    sdist = next(
        (entry for entry in meta["urls"] if entry["packagetype"] == "sdist"), None
    )
    if sdist is None:
        raise RuntimeError(f"no sdist published for gdspy {GDSPY_VERSION}")
    target = destination / sdist["filename"]
    print(f"downloading {sdist['url']}")
    urllib.request.urlretrieve(sdist["url"], target)
    return target


def _prepare(source: Path, workspace: Path, skip_extension: bool) -> Path:
    extract_root = workspace / "src"
    extract_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as archive:
        archive.extractall(extract_root)
    package_root = next(
        path for path in extract_root.iterdir() if (path / "setup.py").is_file()
    )
    (package_root / "gdspy" / "clipper.py").write_text(FALLBACK_MODULE, encoding="utf-8")
    print(f"added pure-Python clipper fallback to {package_root / 'gdspy' / 'clipper.py'}")
    if skip_extension:
        setup = package_root / "setup.py"
        text = setup.read_text(encoding="utf-8")
        marker = "    ext_modules=[\n"
        if marker not in text:
            raise RuntimeError("unexpected gdspy setup.py layout; cannot skip ext_modules")
        # A statement cannot be injected inside setup(...), so make the kwarg
        # value a conditional that resolves to an empty list.
        text = text.replace(marker, "    ext_modules=[] if _SKIP_CLIPPER else [\n", 1)
        text = (
            "# Patched by OpticalWaveguideRouter2D/tools/install_gdspy.py: the machine\n"
            "# has no C++ toolchain, so gdspy.clipper is replaced by a Python fallback.\n"
            "_SKIP_CLIPPER = True\n\n"
        ) + text
        setup.write_text(text, encoding="utf-8")
        print("patched setup.py to skip the clipper extension")
    return package_root


def _has_compiler() -> bool:
    for candidate in ("cl", "g++", "clang++", "c++"):
        if shutil.which(candidate):
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sdist", nargs="?", type=Path, default=None)
    parser.add_argument(
        "--force-pure-python",
        action="store_true",
        help="skip the clipper extension even when a compiler is present",
    )
    args = parser.parse_args()

    compiler = _has_compiler()
    skip_extension = args.force_pure_python or not compiler
    if compiler and not args.force_pure_python:
        print("a C++ compiler was found; the clipper extension will be built")
    else:
        print("no C++ compiler found; installing the pure-Python fallback instead")

    with tempfile.TemporaryDirectory(prefix="gdspy-build-") as tmp:
        workspace = Path(tmp)
        source = args.sdist or _download_sdist(workspace)
        if not source.is_file():
            raise SystemExit(f"source archive not found: {source}")
        package_root = _prepare(source, workspace, skip_extension)
        if skip_extension:
            # Build a wheel from the patched tree, then install it, so that pip
            # records normal metadata and the package can be reinstalled later.
            wheel_dir = workspace / "wheel"
            subprocess.check_call(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "wheel",
                    "--no-deps",
                    "--no-build-isolation",
                    "-w",
                    str(wheel_dir),
                    str(package_root),
                ]
            )
            wheels = sorted(wheel_dir.glob("gdspy-*.whl"))
            if not wheels:
                raise SystemExit("failed to build a gdspy wheel")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--force-reinstall", str(wheels[-1])]
            )
        else:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--no-build-isolation", str(package_root)]
            )
    print("gdspy installation finished")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
