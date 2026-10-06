"""只读复核前代输入；从项目根目录运行 python -m scripts.validate_legacy_inputs 文件...。"""

import argparse
from collections import Counter
import json
from pathlib import Path

from src.io import load_legacy_fiberboard


def summarize(path: str | Path) -> dict:
    """调用唯一解析接口并统计无向 pair；保留模型中的原始方向。"""
    waveguides = load_legacy_fiberboard(path)
    pairs = Counter(tuple(sorted((w.start_port.pmt_id, w.end_port.pmt_id))) for w in waveguides)
    degree = Counter(p for w in waveguides for p in (w.start_port.pmt_id, w.end_port.pmt_id))
    duplicates = [(pair, count) for pair, count in sorted(pairs.items()) if count > 1]
    return {
        "file": str(path), "valid_rows": len(waveguides), "waveguides": len(waveguides),
        "pmt_count": len(degree), "pmt_min": min(degree, default=None),
        "pmt_max": max(degree, default=None),
        "self_connections": sum(w.start_port.pmt_id == w.end_port.pmt_id for w in waveguides),
        "duplicate_undirected_pairs": len(duplicates),
        "extra_pair_rows": sum(count - 1 for _, count in duplicates),
        "duplicate_examples": duplicates[:8],
        "endpoint_counts": dict(sorted(degree.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    for path in args.paths:
        print(json.dumps(summarize(path), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
