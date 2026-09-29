"""Extract the PyInstaller PYZ archive that ships inside AutoRouter.exe.

The archive header is ``PYZ\\0`` + the embedded CPython magic + a big-endian
offset to a marshalled table of contents.  Each entry is ``(ispkg, pos, len)``
and its payload is a zlib-wrapped marshalled code object.

Run this with Python 3.10: the marshal stream produced by 3.8 uses format
version 4, which 3.10 still reads, so we can recover the original bytecode
without a 3.8 interpreter.
"""

from __future__ import annotations

import argparse
import marshal
import struct
import sys
import zlib
from pathlib import Path


class PYZEntry:
    __slots__ = ("name", "ispkg", "pos", "length")

    def __init__(self, name: str, ispkg: bool, pos: int, length: int) -> None:
        self.name = name
        self.ispkg = ispkg
        self.pos = pos
        self.length = length


def read_toc(handle) -> tuple[bytes, list[PYZEntry]]:
    magic = handle.read(4)
    if magic != b"PYZ\0":
        raise ValueError(f"not a PYZ archive (magic={magic!r})")
    pymagic = handle.read(4)
    (toc_position,) = struct.unpack("!i", handle.read(4))
    handle.seek(toc_position)
    raw = marshal.load(handle)
    if isinstance(raw, dict):
        raw = list(raw.items())
    entries = []
    for name, (ispkg, pos, length) in raw:
        if isinstance(name, bytes):
            name = name.decode("utf-8")
        entries.append(PYZEntry(name, bool(ispkg), pos, length))
    return pymagic, entries


def extract(pyz_path: Path, out_dir: Path, only: set[str] | None = None) -> list[Path]:
    """Write real ``.pyc`` files.

    PYZ payloads are bare marshalled code objects, so we re-attach the 16 byte
    header the interpreter expects (magic + flags + mtime + size).  Without it
    neither ``marshal.loads`` nor xdis can recognise the file.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    with pyz_path.open("rb") as handle:
        pymagic, entries = read_toc(handle)
        header = pymagic + struct.pack("<III", 0, 0, 0)
        for entry in entries:
            if only and entry.name not in only:
                continue
            handle.seek(entry.pos)
            blob = handle.read(entry.length)
            data = zlib.decompress(blob)
            code = marshal.loads(data)
            # PyInstaller names a package after the package itself and flags it
            # with ispkg; the code object is that package's __init__, so it has
            # to land in a directory to be importable as a package.
            relative = entry.name.replace(".", "/")
            if entry.ispkg:
                relative += "/__init__"
            target = out_dir / (relative + ".pyc")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(header + data)
            written.append(target)
            print(f"  {entry.name:<40} -> {target}  ({len(data)} bytes, {len(code.co_names)} names)")
    return written


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pyz", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--only", nargs="*", default=None)
    args = parser.parse_args()
    only = set(args.only) if args.only else None
    written = extract(args.pyz, args.out, only)
    print(f"extracted {len(written)} module(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
