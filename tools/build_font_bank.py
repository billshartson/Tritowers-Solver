"""Render the bundled font-tier glyph bank (tritowers_vision/data/font_glyphs.npz) from openly licensed fonts.

Only rendered 32x40 glyph bitmaps are stored, never the font files. Download the fonts first, e.g.
  https://github.com/google/fonts/raw/main/ofl/librebaskerville/LibreBaskerville%5Bwght%5D.ttf   (OFL 1.1)
  https://github.com/google/fonts/raw/main/ofl/prata/Prata-Regular.ttf                          (OFL 1.1)
  https://github.com/google/fonts/raw/main/ofl/librebodoni/LibreBodoni%5Bwght%5D.ttf            (OFL 1.1)
  https://github.com/google/fonts/raw/main/ofl/alike/Alike-Regular.ttf                          (OFL 1.1)
  DejaVuSerif-Bold.ttf from https://github.com/dejavu-fonts/dejavu-fonts/releases               (Bitstream Vera licence)
then:
  python tools/build_font_bank.py FONT.ttf [FONT.ttf ...]

These five were chosen because each one, on its own, ranks all 33 labelled face-up glyphs of the pilot screenshots
correctly (the skin uses a Clarendon-like serif with a curly 2 and 3; Liberation Serif reads 3 as 8). That is a choice
made on 33 glyphs from one skin, so treat the font tier as a fallback: same-skin photo templates remain the main path.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from tritowers_vision import glyphs                      # noqa: E402

if __name__ == "__main__":
    fonts = [Path(p) for p in sys.argv[1:]]
    if not fonts or any(not p.exists() for p in fonts): sys.exit(__doc__)
    n = glyphs.build_bank(fonts)
    print(f"Wrote {n} glyphs from {len(fonts)} fonts to {glyphs.BANK}")
