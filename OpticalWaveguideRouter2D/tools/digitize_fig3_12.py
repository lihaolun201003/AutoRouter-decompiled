"""Digitise thesis Figure 3-12 into an angle -> insertion-loss table.

The original AutoRouter obtained its crossing loss from an external workbook
(``loss.loc[loss["angle"] == int(a)]["loss_db"]`` in ``calc_loss``) that was
never shipped with the executable.  The only remaining source for that table is
Figure 3-12 of the thesis, "simulated insertion loss of waveguides crossing at
different angles", whose "cross number 30" curve is exactly the quantity
``loss_db`` holds: the extra insertion loss of 30 crossings.

This script renders page 20 of the PDF, extracts the green curve by colour,
maps pixels back to (angle, dB) using the plot grid, and writes::

    data/crossing_loss_from_thesis_fig3_12.csv   angle_deg,loss_db_per_30

Accuracy is limited by the source: the published curve is a noisy simulation
trace whose ripple (~0.1 dB) is far larger than one crossing contribution
(0.05/30 dB), so only the trend is recoverable.  ``loss_model`` therefore
rescales the digitised shape so that its 90 degree value equals the 0.05 dB the
thesis states in words; that anchoring removes the colour-extraction offset.
The table is an approximation and is labelled as such everywhere it is used.

Usage::

    .venv\\Scripts\\python.exe tools/digitize_fig3_12.py
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PDF = Path(r"C:\Users\lihao\Desktop\Graduation Project\黄志杰_毕设论文.pdf")
THESIS_PAGE = 20  # printed page number; the PDF has 5 pages of front matter
OUT_CSV = PROJECT_ROOT / "data" / "crossing_loss_from_thesis_fig3_12.csv"

# Plot-grid calibration, in figure pixels, measured from the rendered figure.
# Vertical grid lines sit every 20 degrees at x = 201.5 .. 805.5 (0 deg at
# x = 125.5 before the first line); horizontal grid lines sit every 0.2 dB at
# y = 51 .. 523 (0 dB at y = 51, -1 dB at y = 523).
X_ZERO, X_PER_DEG = 125.5, (805.5 - 125.5) / 180.0
Y_ZERO, Y_PER_DB = 51.0, 523.0 - 51.0


def extract(pdf: Path, out_png: Path) -> np.ndarray:
    import pymupdf
    from PIL import Image

    doc = pymupdf.open(pdf)
    page = doc[THESIS_PAGE - 1 + 5]
    images = page.get_images(full=True)
    if not images:
        raise SystemExit("figure 3-12 image not found on the thesis page")
    info = doc.extract_image(images[0][0])
    out_png.parent.mkdir(parents=True, exist_ok=True)
    out_png.write_bytes(info["image"])
    return np.asarray(Image.open(out_png).convert("RGB")).astype(int)


def green_curve(pixels: np.ndarray) -> dict[int, float]:
    """Median y of the green trace for every whole degree in 1..180."""
    r, g, b = pixels[..., 0], pixels[..., 1], pixels[..., 2]
    green = (g > 110) & (g - r > 45) & (g - b > 45)
    table: dict[int, float] = {}
    for deg in range(1, 181):
        xc = X_ZERO + deg * X_PER_DEG
        lo, hi = int(round(xc - 2)), int(round(xc + 2))
        ys = np.where(green[:, lo : hi + 1].any(axis=1))[0]
        if len(ys):
            table[deg] = float((np.median(ys) - Y_ZERO) / Y_PER_DB)
    return table


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    ap.add_argument("--png", type=Path, default=PROJECT_ROOT / "scratch" / "thesis" / "fig3_12_raw.png")
    ap.add_argument("--out", type=Path, default=OUT_CSV)
    args = ap.parse_args()

    pixels = extract(args.pdf, args.png)
    table = green_curve(pixels)
    missing = [d for d in range(1, 181) if d not in table]
    # Interior gaps are linearly interpolated; there is at most one.
    for deg in missing:
        lo = max((d for d in table if d < deg), default=None)
        hi = min((d for d in table if d > deg), default=None)
        if lo is None or hi is None:
            table[deg] = table[min(table)] if lo is None else table[max(table)]
        else:
            frac = (deg - lo) / (hi - lo)
            table[deg] = table[lo] + frac * (table[hi] - table[lo])

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["angle_deg", "loss_db_per_30_crossings"])
        for deg in range(1, 181):
            writer.writerow([deg, "%.6f" % table[deg]])
    print("wrote %s (%d rows, %d interpolated)" % (args.out, len(table), len(missing)))
    print("digitised 90 deg value: %.4f dB / 30 crossings (thesis text: 0.05)" % table[90])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
