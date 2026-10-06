"""Generate a true bold variant of SimSun by outline emboldening (skia-pathops).

The Chinese bold face in the revision PDF must remain a Song (宋体) face, not
the Hei (黑体) face. SimSun ships regular-only, so this script reads SimSun from
simsun.ttc, expands every glyph outline with the standard pathops stroke+union
emboldening, and writes SimSun-Bold.ttf next to the report scripts.

Usage (project root):
    .venv\\Scripts\\python.exe -B scripts\\build_simsun_bold.py
"""
import sys
from pathlib import Path as FilePath

from fontTools.ttLib import TTCollection
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from pathops import Path as SkiaPath, PathPen, op, PathOp

SOURCE = FilePath('C:/Windows/Fonts/simsun.ttc')
TARGET = FilePath(__file__).resolve().parents[1]/'publication'/'report'/'brief_build'/'SimSun-Bold.ttf'
AMOUNT = 0.03   # emboldening strength in em units, one side per outline


def emboldened_glyph(glyph_set, glyph_name, amount):
    # Decompose composite glyphs into plain outlines first, then replay into
    # the pathops pen (pathops.PathPen is a Cython pen without component support).
    recording = DecomposingRecordingPen(glyph_set)
    glyph_set[glyph_name].draw(recording)
    if not recording.value:
        return None
    original = SkiaPath()
    recording.replay(PathPen(original))
    if not list(original.contours):
        return None
    # pathops cannot compute areas of conic segments (TrueType quads map to
    # CONIC in the pathops pen), so convert every path to quads first.
    original.convertConicsToQuads()
    stroked = SkiaPath()
    stroked.addPath(original)
    stroked.stroke(amount*2, 1, 1, 4)      # round cap, round join, miter 4
    stroked.convertConicsToQuads()
    out = op(original, stroked, PathOp.UNION)
    out.convertConicsToQuads()
    out.simplify(fix_winding=True, keep_starting_points=False)
    pen = TTGlyphPen(glyph_set)
    out.draw(pen)
    return pen.glyph()


def main():
    font = TTCollection(str(SOURCE)).fonts[0]
    family = font['name'].getDebugName(1)
    subfamily = font['name'].getDebugName(2)
    print(f'source face: {family!r} / {subfamily!r}, glyphs={font["maxp"].numGlyphs}')
    glyph_set = font.getGlyphSet()
    glyf = font['glyf']
    updated = 0
    skipped = 0
    failed = []
    for index, glyph_name in enumerate(font.getGlyphOrder()):
        try:
            glyph = emboldened_glyph(glyph_set, glyph_name, AMOUNT)
        except Exception:
            # Degenerate outlines (self-intersections, zero-area contours) can
            # make the boolean op fail; keep the original glyph for those.
            failed.append(glyph_name)
            continue
        if glyph is None:
            skipped += 1
            continue
        glyf[glyph_name] = glyph
        updated += 1
        if index % 4000 == 0:
            print(f'  ..{index} glyphs processed', flush=True)
    print(f'emboldened {updated} glyphs, skipped {skipped} empty, kept original for {len(failed)} failed')
    if failed:
        print('first failed glyphs:', failed[:20])
    # Rename so the family is recognisably the Song bold variant.
    name = font['name']
    for record in list(name.names):
        if record.nameID == 2:
            name.setName('Bold', 2, record.platformID, record.platEncID, record.langID)
        elif record.nameID == 4:
            name.setName('SimSun Bold', 4, record.platformID, record.platEncID, record.langID)
        elif record.nameID == 6:
            name.setName('SimSun-Bold', 6, record.platformID, record.platEncID, record.langID)
        elif record.nameID == 1 and record.platformID == 3:
            name.setName('SimSun', 1, record.platformID, record.platEncID, record.langID)
    font.save(str(TARGET))
    print(f'wrote {TARGET} ({TARGET.stat().st_size} bytes)')


if __name__ == '__main__':
    sys.exit(main())
