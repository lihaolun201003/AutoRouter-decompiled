"""Raw instruction dump for Python 3.8 code objects.

``xdis.std.dis`` renders jump targets using the running interpreter's
semantics, which is wrong here because the archive holds 3.8 bytecode.  Jump
opcodes changed from absolute byte offsets (3.8) to relative instruction
offsets (3.10), so we decode ``co_code`` by hand and print the numeric oparg
and the resolved 3.8 target.
"""

from __future__ import annotations

import sys
from pathlib import Path

from xdis import load_module
from xdis.opcodes import opcode_38

OPMAP = opcode_38.opmap
HAVE_ARGUMENT = opcode_38.HAVE_ARGUMENT
# In CPython 3.8 `hasjabs` opcodes take an absolute byte offset, while
# `hasjrel` ones take a byte delta measured from the *next* instruction.
JABS = set(opcode_38.hasjabs)
JREL = set(opcode_38.hasjrel)
OPNAME = opcode_38.opname


def walk(code, prefix=""):
    yield prefix + code.co_name, code
    for const in code.co_consts:
        if hasattr(const, "co_name"):
            yield from walk(const, prefix + code.co_name + ".")


def line_starts(code) -> list[int]:
    """Expand co_lnotab into a per-byte-offset line table."""
    table = []
    addr = 0
    line = code.co_firstlineno
    for i in range(0, len(code.co_lnotab), 2):
        delta = code.co_lnotab[i]
        ldelta = code.co_lnotab[i + 1]
        if ldelta >= 128:
            ldelta -= 256
        line += ldelta
        addr += delta
        table.append((addr, line))
    starts = {}
    cur = code.co_firstlineno
    idx = 0
    for offset in range(0, len(code.co_code), 2):
        while idx < len(table) and table[idx][0] <= offset:
            cur = table[idx][1]
            idx += 1
        starts[offset] = cur
    return starts


def dump(code) -> None:
    code_bytes = code.co_code
    consts = code.co_consts
    names = code.co_names
    varnames = code.co_varnames
    # xdis exposes the 3.8 cell/free variable lists swapped, so the deref name
    # space (cellvars then freevars in CPython's localsplus layout) has to be
    # rebuilt from the swapped attributes.
    derefvars = list(code.co_freevars) + list(code.co_cellvars)
    cmp_op = opcode_38.cmp_op
    starts = line_starts(code)
    arg = 0
    ext = 0
    for offset in range(0, len(code_bytes), 2):
        op = code_bytes[offset]
        oparg = code_bytes[offset + 1]
        name = OPNAME[op]
        text = ""
        if op >= HAVE_ARGUMENT:
            arg = (ext << 8) | oparg
            if op == opcode_38.EXTENDED_ARG:
                ext = arg
                print(f"{offset:4d}  L{starts[offset]:<4} {name:<24} {oparg}")
                continue
            ext = 0
            # JABS/JREL operands are the *accumulated* argument: a preceding
            # EXTENDED_ARG contributes the high byte, so using ``oparg`` here
            # would misreport every jump whose target exceeds byte 255.
            if op in JABS:
                text = f"{arg}  -> byte {arg}  (L{starts.get(arg, -1)})"
            elif op in JREL:
                target = offset + 2 + arg
                text = f"{arg}  -> byte {target}  (L{starts.get(target, -1)})"
            elif op == 100:  # LOAD_CONST
                try:
                    text = f"{oparg}  {consts[oparg]!r}"[:110]
                except IndexError:
                    text = str(oparg)
            elif op in (106, 108, 116, 120):  # LOAD_ATTR/METHOD/GLOBAL/NAME
                try:
                    text = f"{oparg}  {names[oparg]}"
                except IndexError:
                    text = str(oparg)
            elif op in (124, 125, 126):  # LOAD_FAST / STORE_FAST / DELETE_FAST
                try:
                    text = f"{oparg}  {varnames[oparg]}"
                except IndexError:
                    text = str(oparg)
            elif op in (135, 136, 137):  # LOAD_CLOSURE / LOAD_DEREF / STORE_DEREF
                try:
                    text = f"{oparg}  {derefvars[oparg]}"
                except IndexError:
                    text = f"{oparg}  <bad deref>"
            elif op == 107:  # COMPARE_OP
                text = f"{oparg}  {cmp_op[oparg] if oparg < len(cmp_op) else oparg}"
            else:
                text = str(oparg)
        print(f"{offset:4d}  L{starts[offset]:<4} {name:<24} {text}")
    print(f"\n[co_code length = {len(code_bytes)} bytes, "
          f"first_line = {code.co_firstlineno}, nlocals = {code.co_nlocals}]")
    print(f"[cellvars={code.co_cellvars} freevars={code.co_freevars}]")


def main() -> int:
    path = Path(sys.argv[1])
    wanted = sys.argv[2:]
    loaded = load_module(str(path))
    module_code = loaded[3]
    hit = False
    for qualname, obj in walk(module_code):
        short = qualname.split(".")[-1]
        if wanted and short not in wanted and qualname != wanted:
            continue
        hit = True
        print("=" * 78)
        print(f"# {qualname}   (defined at line {obj.co_firstlineno}, "
              f"args={obj.co_varnames[:obj.co_argcount]})")
        print("=" * 78)
        dump(obj)
        print()
    if not hit:
        print("available code objects:")
        for qualname, _ in walk(module_code):
            print("  ", qualname)
    return 0


if __name__ == "__main__":
    sys.exit(main())
