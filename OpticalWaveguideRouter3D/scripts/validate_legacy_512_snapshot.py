"""Read-only validation of the specific legacy 512 endpoint snapshot."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from math import isclose
from pathlib import Path

from openpyxl import load_workbook
from src.io import load_legacy_512_snapshot


def validate(fiberboard: Path, snapshot: Path) -> dict:
    before = [sha256(p.read_bytes()).hexdigest() for p in (fiberboard, snapshot)]
    waveguides = load_legacy_512_snapshot(fiberboard, snapshot)
    book = load_workbook(snapshot, read_only=True, data_only=False)
    try:
        rows = list(book.worksheets[0].values)
    finally:
        book.close()
    headers = rows[0]
    col = {key: headers.index(key) for key in ("Port1", "Port2", "sy", "ly")}
    directions = Counter()
    snapshot_sides = Counter()
    for row in rows[1:]:
        if all(v is None for v in row):
            continue
        w = waveguides[int(row[0])]
        directions["same" if row[col["Port1"]] == w.start_port.pmt_id else "reversed"] += 1
        snapshot_sides[f'{row[col["sy"]]}->{row[col["ly"]]}'] += 1
    groups = defaultdict(list)
    restored_sides = Counter()
    for w in waveguides:
        restored_sides[f'{w.start_port.position.y:g}->{w.end_port.position.y:g}'] += 1
        for p in (w.start_port, w.end_port):
            groups[p.pmt_id].append(p.position)
    endpoint_checks = {}
    for pmt, points in sorted(groups.items()):
        xs = sorted(p.x for p in points)
        endpoint_checks[pmt] = {
            "count": len(points), "unique_x": len(set(xs)),
            "y_values": sorted(set(p.y for p in points)),
            "pitch_0175": all(isclose(b-a, 0.175, abs_tol=1e-8, rel_tol=0) for a,b in zip(xs,xs[1:])),
        }
    after = [sha256(p.read_bytes()).hexdigest() for p in (fiberboard, snapshot)]
    assert before == after
    return {
        "waveguides": len(waveguides), "pmt_count": len(groups),
        "direction": dict(directions), "snapshot_sides": dict(snapshot_sides),
        "restored_sides": dict(restored_sides),
        "same_side": sum(w.start_port.position.y == w.end_port.position.y for w in waveguides),
        "opposite_side": sum(w.start_port.position.y != w.end_port.position.y for w in waveguides),
        "all_local_id_none": all(p.local_id is None for w in waveguides for p in (w.start_port,w.end_port)),
        "y_values": sorted({p.y for pts in groups.values() for p in pts}),
        "endpoint_checks": endpoint_checks, "source_sha256_unchanged": before,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fiberboard", type=Path)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.fiberboard, args.snapshot), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
