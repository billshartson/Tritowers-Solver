"""Rank reader v2 (prototype, single skin). Aspect-preserving glyphs, waste-card locator, two-tier acceptance.

Why v2: the v1 reader squashed every glyph to 24x32 (a two-glyph "10" was distorted), cropped the waste card
with a fixed box (the real card position moves ~25 px and its index is ~1.25x larger, so glyphs were clipped),
and had no photo template for ranks seen in only one photo. Numbers below are tuned on the same 33 labelled
glyphs from 5 screenshots: a prototype signal, not an accuracy guarantee.

Deployment rule: production always loads EVERY labelled photo as a template (TT_TEMPLATES, private, never committed).
The leave-one-image-out split is an offline measurement of coverage only; it is not a deployment choice.
"""
import os
import numpy as np, cv2
from PIL import Image
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
GH, GW = 32, 40
# Tier 1: photo templates (private, via TT_TEMPLATES). Tier 2: glyphs rendered from an open font.
PHOTO_SCORE, PHOTO_MARGIN = 0.80, 0.10
SYN_SCORE, SYN_MARGIN = 0.45, 0.03
_FONTS = (
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf",
    "/usr/share/fonts/liberation/LiberationSerif-Bold.ttf",
)
_SYN = None

def raw_glyph(patch: Image.Image, scale: float = 1.0):
    """Binary rank glyph (variable size) from a corner patch, or None. scale > 1 for the larger waste card."""
    rgb = np.asarray(patch.convert("RGB")).astype(np.int16)
    g = np.asarray(patch.convert("L")).astype(np.float32)
    ink = (g < 110).astype(np.uint8)
    ink |= ((rgb[..., 1] < 100) & (rgb[..., 0] > 100)).astype(np.uint8)
    if int(ink.sum()) < 15: return None
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink)
    comps = sorted([i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] >= 8], key=lambda i: st[i, cv2.CC_STAT_TOP])
    if not comps: return None
    top = st[comps[0], cv2.CC_STAT_TOP]
    keep = [i for i in comps if st[i, cv2.CC_STAT_TOP] < top + 14 * scale and st[i, cv2.CC_STAT_HEIGHT] > 8]
    if not keep: return None
    m = np.isin(lab, keep).astype(np.float32); ys, xs = np.nonzero(m)
    if not len(xs): return None
    return m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]

def normalize(a):
    """Scale to height GH keeping aspect, centre in a GH x GW frame. None/empty -> zeros."""
    if a is None or a.size == 0: return np.zeros((GH, GW), np.float32)
    h, w = a.shape; nw = max(1, min(GW, int(round(w * GH / h))))
    r = cv2.resize(a.astype(np.float32), (nw, GH), interpolation=cv2.INTER_AREA)
    out = np.zeros((GH, GW), np.float32); x = (GW - nw) // 2; out[:, x:x + nw] = r; return out

def glyph(patch: Image.Image, scale: float = 1.0) -> np.ndarray:
    return normalize(raw_glyph(patch, scale))

def waste_card(rectified: Image.Image, region=(560, 500, 780, 790)):
    """(x, y, w, h) of the light waste card face, or None. The card's vertical position varies between frames."""
    x0, y0, x1, y1 = region
    p = np.asarray(rectified.convert("RGB").crop(region)).astype(np.int16)
    if p.size == 0: return None
    light = ((p.min(axis=2) > 150) & ((p.max(axis=2) - p.min(axis=2)) < 70)).astype(np.uint8)
    light = cv2.morphologyEx(light, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(light)
    if n < 2: return None
    i = max(range(1, n), key=lambda k: st[k, cv2.CC_STAT_AREA])
    if st[i, cv2.CC_STAT_AREA] < 4000: return None
    return (x0 + int(st[i, 0]), y0 + int(st[i, 1]), int(st[i, 2]), int(st[i, 3]))

def waste_corner_box(rectified):
    c = waste_card(rectified)
    if c is None: return None
    return (c[0] + 4, c[1] + 3, c[0] + 70, c[1] + 74)   # waste index is ~1.5x the tableau size

def _ncc(a, b):
    a = a - a.mean(); b = b - b.mean()
    return float((a * b).sum() / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-6))
def _shifts(g):
    out = [g]
    for dx in (-2, -1, 1, 2):
        for dy in (-2, -1, 1, 2): out.append(cv2.warpAffine(g, np.float32([[1, 0, dx], [0, 1, dy]]), (GW, GH)))
    return out

def synthetic_templates():
    global _SYN
    if _SYN is not None: return _SYN
    from PIL import ImageDraw, ImageFont
    path = next((p for p in _FONTS if os.path.exists(p)), None); out = []
    if path:
        font = ImageFont.truetype(path, 64)
        for r in RANKS:
            im = Image.new("L", (220, 120), 0); ImageDraw.Draw(im).text((10, 5), r, font=font, fill=255)
            a = np.array(im) > 128; ys, xs = np.nonzero(a)
            if len(xs): out.append((r, normalize(a[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.float32))))
    _SYN = out; return out

def _rank_scores(g, templates):
    best = {}
    for r, t in templates:
        if t.shape != (GH, GW): continue            # ignore legacy 24x32 templates
        v = max(_ncc(g, x) for x in _shifts(t)); best[r] = max(best.get(r, -1.0), v)
    return sorted(best.items(), key=lambda kv: -kv[1])

def match(g, photo_templates):
    """Returns (rank or None, score, margin, tier). None means abstain. Photo tier first, then font tier."""
    if g is None or g.sum() == 0: return None, 0.0, 0.0, "none"
    po = _rank_scores(g, photo_templates)
    if po:
        m = po[0][1] - (po[1][1] if len(po) > 1 else 0.0)
        if po[0][1] >= PHOTO_SCORE and m >= PHOTO_MARGIN: return po[0][0], po[0][1], m, "photo"
    so = _rank_scores(g, synthetic_templates())
    if so:
        m = so[0][1] - (so[1][1] if len(so) > 1 else 0.0)
        if so[0][1] >= SYN_SCORE and m >= SYN_MARGIN: return so[0][0], so[0][1], m, "font"
        return None, so[0][1], m, "abstain"
    return None, 0.0, 0.0, "abstain"
