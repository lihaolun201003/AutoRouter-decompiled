"""Print only the control-flow skeleton of Python 3.8 code objects.

Full instruction listings are noisy; for reconstructing block structure what
matters is where the loops, conditional jumps, returns and calls sit.  This
resolves EXTENDED_ARG prefixes and prints absolute jump targets so the real
nesting is unambiguous.
"""

from __future__ import annotations

import sys
from pathlib import Path

from xdis import load_module
from xdis.opcodes import opcode_38 as O

HAVE_ARGUMENT = O.HAVE_ARGUMENT
JABS = set(O.hasjabs)
JREL = set(O.hasjrel)
OPNAME = O.opname
INTERESTING = set(O.hasjabs) | set(O.hasjrel) | {
    O.RETURN_VALUE, O.CALL_FUNCTION, O.CALL_METHOD, O.CALL_FUNCTION_KW,
    O.CALL_FUNCTION_EX, O.MAKE_FUNCTION, O.BUILD_LIST, O.INPLACE_ADD,
    O.STORE_SUBSCR, O.STORE_FAST, O.POP_TOP,
}
CALLS = {O.CALL_FUNCTION, O.CALL_METHOD, O.CALL_FUNCTION_KW, O.CALL_FUNCTION_EX}


def walk(code, prefix=""):
    yield prefix + code.co_name, code
    for const in code.co_consts:
        if hasattr(const, "co_name"):
            yield from walk(const, prefix + code.co_name + ".")


def line_starts(code):
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


def skeleton(code) -> None:
    raw = code.co_code
    names = code.co_names
    starts = line_starts(code)
    ext = 0
    last_line = None
    for offset in range(0, len(raw), 2):
        op = raw[offset]
        oparg = raw[offset + 1]
        if op >= HAVE_ARGUMENT:
            arg = (ext << 8) | oparg
            if op == O.EXTENDED_ARG:
                ext = arg
                continue
        else:
            arg = 0
        ext = 0
        line = starts[offset]
        if op not in INTERESTING and op < HAVE_ARGUMENT:
            continue
        detail = ""
        if op in JABS:
            detail = f"L{starts.get(arg, -1)}@{arg}"
        elif op in JREL:
            t = offset + 2 + arg
            detail = f"L{starts.get(t, -1)}@{t}"
        elif op in CALLS:
            detail = f"arg={arg}"
        elif op == O.STORE_FAST:
            detail = code.co_varnames[arg] if arg < len(code.co_varnames) else "?"
        if op in CALLS:
            continue
        prefix = "" if line == last_line else f"L{line:<4} "
        last_line = line
        print(f"{offset:5d}  {prefix:<7} {OPNAME[op]:<22} {detail}")
        if op == O.RETURN_VALUE:
            pass


def main() -> int:
    path = Path(sys.argv[1])
    wanted = sys.argv[2:]
    loaded = load_module(str(path))
    for qualname, obj in walk(loaded[3]):
        short = qualname.split(".")[-1]
        if wanted and short not in wanted and qualname != wanted:
            continue
        print("=" * 76)
        print(f"# {qualname}  (line {obj.co_firstlineno}, "
              f"args={obj.co_varnames[:obj.co_argcount]})")
        print("=" * 76)
        skeleton(obj)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
