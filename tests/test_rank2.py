import os
import pytest
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from tritowers_vision import rank2 as R2

def _render_patch(txt, size=40, color=(20, 20, 20)):
    font = R2.synthetic_templates() and next((p for p in R2._FONTS if __import__("os").path.exists(p)), None)
    im = Image.new("RGB", (60, 60), (235, 225, 200))
    ImageDraw.Draw(im).text((6, 3), txt, font=ImageFont.truetype(font, size), fill=color)
    return im

def test_normalize_keeps_aspect_and_handles_empty():
    wide = np.ones((30, 37), np.float32); narrow = np.ones((30, 16), np.float32)
    a, b = R2.normalize(wide), R2.normalize(narrow)
    assert a.shape == b.shape == (R2.GH, R2.GW)
    assert (a.sum(axis=0) > 0).sum() > (b.sum(axis=0) > 0).sum()      # wider glyph stays wider
    assert R2.normalize(None).sum() == 0 and R2.glyph(Image.new("RGB", (40, 40), "white")).sum() == 0

def test_font_tier_reads_clean_rendered_ranks_and_waste_scale():
    if not R2.synthetic_templates():
        if os.environ.get("TT_REQUIRE_TEST_FONTS"): pytest.fail("Install fonts-liberation for legacy matcher coverage")
        pytest.skip("Legacy matcher needs an installed Liberation font")
    for r in ("A", "7", "Q", "10", "K"):
        for size, scale in ((40, 1.0), (56, 1.5)):                    # waste index is larger than tableau
            p, sc, mg, tier = R2.match(R2.glyph(_render_patch(r, size), scale), [])
            assert p == r and tier == "font", (r, size, p, sc, mg)

def test_abstains_on_noise_blank_and_legacy_templates():
    rng = np.random.default_rng(0)
    noise = (rng.random((R2.GH, R2.GW)) > 0.5).astype(np.float32)
    assert R2.match(noise, [])[0] is None
    assert R2.match(np.zeros((R2.GH, R2.GW), np.float32), [])[0] is None
    legacy = [("5", np.ones((32, 24), np.float32))]                    # old-shape template must be ignored, not crash
    assert R2.match(noise, legacy)[0] is None

def test_photo_tier_wins_for_exact_template_and_waste_card_locator():
    g = R2.normalize(np.pad(np.ones((20, 10), np.float32), 2))
    other = R2.normalize(np.eye(24, dtype=np.float32))
    p, sc, mg, tier = R2.match(g, [("9", g.copy()), ("4", other)])
    assert (p, tier) == ("9", "photo")
    frame = Image.new("RGB", (1024, 768), (40, 40, 40)); ImageDraw.Draw(frame).rectangle((602, 570, 719, 751), fill=(240, 232, 215))
    x, y, w, h = R2.waste_card(frame); assert abs(x - 602) <= 1 and abs(y - 570) <= 1
    assert R2.waste_card(Image.new("RGB", (1024, 768), (40, 40, 40))) is None
