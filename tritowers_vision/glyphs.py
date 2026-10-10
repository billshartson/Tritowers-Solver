"""Rank index glyphs read straight from the original image through the layout homography.

Compared with rank2 (fixed crops of the 1024x768 rectified frame, fixed grey-level ink threshold): the index corner is
warped once from the full-resolution photo, ink is measured against the card's own face colour (so exposure, colour
casts and red or black ink all work the same), and blobs touching the patch edge (neighbouring cards, backs behind,
parchment) are dropped. Glyphs are normalised exactly like rank2 (32 x 40, aspect kept), so templates stay compatible.

Matching: private same-skin photo templates first, then a bundled bank rendered from open fonts; enclosed-hole counts
penalise impossible ranks; every gate abstains rather than guesses (thresholds measured on the five pilot screenshots
and simulated re-shoots of them, tools/vision_eval.py).
"""
from pathlib import Path
import os
import numpy as np
import cv2

from . import rank2
from .rank2 import GH, GW, RANKS, normalize

PX = 3                                   # output pixels per layout unit for the corner patch
GLYPH_H = 37                             # rank band height for a tableau index, layout units (real ranks are 32-35)
TABLEAU_CORNER = (-5, -5, 52, 58)        # patch around a tableau card's top-left corner, layout units (Q tails run low)
WASTE_CORNER = (-6, -6, 62, 78)          # the waste index is larger
BANK = Path(__file__).with_name("data") / "font_glyphs.npz"
# Acceptance gates: (best score, margin over the best other rank) for each tier.
PHOTO_SCORE, PHOTO_MARGIN = 0.85, rank2.PHOTO_MARGIN   # 0.85: no wrong accepts when a rank has no template (leave-one-out)
FONT_SCORE, FONT_MARGIN = 0.75, 0.10    # no wrong accepts on 465 real and re-shot pilot glyphs, nor on held-out synthetic fonts
FONT_FIT = 0.75                          # below this image-level fit the font tier names nothing (see font_fit)
_BANK = None


def corner_patch(image_rgb, H, card_xy, box=TABLEAU_CORNER):
    """RGB patch of the index corner of the card whose top-left layout point is card_xy. H: layout -> image pixels."""
    x0, y0 = card_xy[0] + box[0], card_xy[1] + box[1]
    w, h = box[2] - box[0], box[3] - box[1]
    pts = np.float64([[x0, y0], [x0 + w, y0], [x0, y0 + h]])
    img_pts = cv2.perspectiveTransform(pts.reshape(-1, 1, 2), H).reshape(-1, 2)
    s = max(np.linalg.norm(img_pts[1] - img_pts[0]) / w, np.linalg.norm(img_pts[2] - img_pts[0]) / h)
    hi = max(PX, int(np.ceil(s)))                 # sample at least at the image's own resolution, then average down
    T = np.array([[1 / hi, 0, x0], [0, 1 / hi, y0], [0, 0, 1]], np.float64)
    patch = cv2.warpPerspective(image_rgb, H @ T, (w * hi, h * hi), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                                borderMode=cv2.BORDER_REPLICATE)
    if hi != PX: patch = cv2.resize(patch, (w * PX, h * PX), interpolation=cv2.INTER_AREA)
    return patch


def ink_mask(patch):
    """Pixels that differ from the card face colour (rank, pip, anything that is not the face)."""
    a = patch.astype(np.float32)
    v = a.max(axis=2); chroma = (v - a.min(axis=2)) / (v + 1)
    face_px = (v >= np.percentile(v, 60)) & (chroma < 0.35)
    face = np.median(a[face_px], axis=0) if face_px.sum() > 20 else np.percentile(a.reshape(-1, 3), 90, axis=0)
    d = cv2.GaussianBlur(np.sqrt(((a - face) ** 2).sum(axis=2)), (0, 0), 0.8)    # calms moire and JPEG noise
    d8 = np.clip(d, 0, 255).astype(np.uint8)
    otsu, _ = cv2.threshold(d8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    thr = max(45.0, min(float(otsu), 0.45 * float(np.linalg.norm(face))))
    return (d > thr).astype(np.uint8)


def raw_glyph(patch, scale=1.0, *, with_box=False):
    """Binary rank glyph (variable size) or None. scale: index size relative to a tableau card.

    The rank occupies a band from its top down to the first clear gap (the space above the suit pip; smaller indexes
    on other skins put the pip well inside a fixed band), at most GLYPH_H; every blob starting inside the band belongs
    to it (blur and moire can split a stroke), and the band's bottom edge cuts off a pip that has merged into it."""
    ink = ink_mask(patch)
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    H, W = ink.shape
    unit = PX * scale
    cands = []
    for i in range(1, n):
        x, y, w, h, area = st[i]
        if area < 4 * unit * unit: continue                                          # specks
        if x <= 0 or y <= 0 or x + w >= W or y + h >= H: continue                   # touches the patch edge
        if h > 50 * unit or w > 36 * unit: continue                                 # pips, art, card edges
        cands.append(i)
    tops = [st[i, cv2.CC_STAT_TOP] for i in cands if st[i, cv2.CC_STAT_HEIGHT] >= 15 * unit]
    if not tops: return None
    top = min(tops); bottom = top + int(GLYPH_H * unit)
    first = min((i for i in cands if st[i, cv2.CC_STAT_TOP] == top), key=lambda i: st[i, cv2.CC_STAT_LEFT])
    left = st[first, cv2.CC_STAT_LEFT]
    column = [i for i in cands if top <= st[i, cv2.CC_STAT_TOP] < bottom
              and st[i, cv2.CC_STAT_LEFT] < left + 30 * unit
              and (st[i, cv2.CC_STAT_LEFT] >= left - 3 * unit
                   or (st[i, cv2.CC_STAT_HEIGHT] >= .65 * st[first, cv2.CC_STAT_HEIGHT]
                       and st[i, cv2.CC_STAT_WIDTH] >= 3 * unit))]
    rows = np.isin(lab, column)[top:bottom].any(axis=1)
    gap = max(2, int(round(2 * unit)))
    for y in range(int(0.45 * GLYPH_H * unit), len(rows) - gap):     # first empty run past a plausible glyph height
        if not rows[y:y + gap].any(): bottom = top + y; break
    keep = [i for i in column if st[i, cv2.CC_STAT_TOP] < bottom - min(4 * unit, 0.2 * (bottom - top))]
    m = np.isin(lab, keep)[top:bottom].astype(np.float32); ys, xs = np.nonzero(m)
    if not len(xs): return None
    raw = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    box = (int(xs.min()), int(top + ys.min()), int(xs.max() + 1), int(top + ys.max() + 1))
    return (raw, box) if with_box else raw


def glyph(patch, scale=1.0):
    return normalize(raw_glyph(patch, scale))



def extract(patch, scale=1.0):
    """A glyph and separate crop-validity evidence, before any rank matching.

    Reject blank/partial crops and suit pips exposed by losing the rank to a
    connected card edge. A high match score cannot override ownership checks.
    """
    result = raw_glyph(patch, scale, with_box=True)
    if result is None:
        return None, {"valid": False, "reason": "no_complete_index"}
    raw, (x0, y0, x1, y1) = result
    unit = PX * scale
    height = (y1 - y0) / unit
    valid = bool(15 <= height <= 40 and 3 <= x0 / unit <= 30 and 3 <= y0 / unit <= 23
                 and x1 < patch.shape[1] - 2 and y1 < patch.shape[0] - 2)
    detail = {"valid": valid, "reason": "index_inside_card" if valid else "partial_or_displaced_index",
              "box": [x0, y0, x1, y1]}
    return (normalize(raw) if valid else None), detail

def _render_bank(fonts):
    from PIL import Image, ImageDraw, ImageFont
    out = []
    for path in fonts:
        try: font = ImageFont.truetype(str(path), 72)
        except OSError: continue
        try: font.set_variation_by_name("Bold")
        except Exception: pass
        for r in RANKS:
            for squeeze in ((1.0, 0.8) if r == "10" else (1.0,)):
                im = Image.new("L", (260, 140), 0); ImageDraw.Draw(im).text((10, 10), r, font=font, fill=255)
                a = np.array(im) > 128; ys, xs = np.nonzero(a)
                if not len(xs): continue
                g = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.float32)
                if squeeze != 1.0: g = cv2.resize(g, (max(1, int(g.shape[1] * squeeze)), g.shape[0]), interpolation=cv2.INTER_AREA)
                out.append((r, normalize(g)))
    return out


def font_bank():
    """Bundled open-font glyphs (data/font_glyphs.npz), else rank2's runtime font templates."""
    global _BANK
    if _BANK is None:
        if BANK.exists():
            z = np.load(BANK, allow_pickle=False)
            _BANK = [(str(r), g.astype(np.float32) / 255.0) for r, g in zip(z["ranks"], z["glyphs"])]
        else:
            _BANK = list(rank2.synthetic_templates())
    return _BANK


# Enclosed holes per rank index (8 has two, A 4 6 9 Q 10 one, the rest none; this skin and the bank draw a closed 4). Counting
# holes separates the curly 3 from 8 and 5 from 6, which shape correlation alone only just tells apart.
HOLES = {"A": {1}, "2": {0}, "3": {0}, "4": {1}, "5": {0}, "6": {1}, "7": {0}, "8": {2}, "9": {1}, "10": {1}, "J": {0}, "Q": {1}, "K": {0}}
HOLE_PENALTY = 0.12


def holes(g, thr=0.5):
    """Number of enclosed background regions in a normalised glyph (specks under 3 px ignored)."""
    inv = np.pad((g <= thr).astype(np.uint8), 1, constant_values=1)
    n, _, st, _ = cv2.connectedComponentsWithStats(inv, connectivity=4)
    return sum(1 for i in range(2, n) if st[i, cv2.CC_STAT_AREA] >= 3)


# Only the immutable, public font bank is cached. Private inputs and in-image
# examples live for one read, so switching photos cannot contaminate later reads.
_FONT_MATRIX = None


def _prepare(templates):
    ranks, rows = [], []
    for rank, template in templates:
        if template.shape != (GH, GW):
            continue
        blurred = cv2.GaussianBlur(template, (0, 0), 0.8)
        for shifted in rank2._shifts(blurred):
            centered = shifted.ravel() - shifted.mean()
            rows.append(centered)
            ranks.append(rank)
    if not rows:
        return [], np.empty((0, GH * GW), np.float32), np.empty(0, np.float32)
    matrix = np.asarray(rows, np.float32)
    return ranks, matrix, np.linalg.norm(matrix, axis=1)


def _prepared(templates):
    global _FONT_MATRIX
    if templates is font_bank():
        if _FONT_MATRIX is None:
            _FONT_MATRIX = _prepare(templates)
        return _FONT_MATRIX
    return _prepare(templates)


def _ranked(g, templates):
    ranks, matrix, norms = _prepared(templates)
    if not ranks:
        return []
    blurred = cv2.GaussianBlur(g, (0, 0), 0.8)
    query = blurred.ravel() - blurred.mean()
    # einsum avoids a multithreaded BLAS launch for these small, frequent dots.
    scores = np.einsum("ij,j->i", matrix, query, dtype=np.float64) / (norms * np.linalg.norm(query) + 1e-6)
    h, best = holes(g), {}
    for rank, score in zip(ranks, scores):
        value = float(score) - (HOLE_PENALTY if h not in HOLES.get(rank, {h}) else 0)
        best[rank] = max(best.get(rank, -1.0), value)
    return sorted(best.items(), key=lambda kv: -kv[1])


def font_tier_enabled():
    """TT_FONT_TIER=0 turns the bundled font tier off, so only private photo templates can name a rank."""
    return os.environ.get("TT_FONT_TIER", "1").strip() != "0"


def match(g, photo_templates=(), *, font_scores=None):
    """(rank or None, score, margin, tier). Photo templates (same skin) first, then the bundled font bank.

    The photo tier's margin is taken against all 13 ranks: a rank with no photo template competes through its font
    score, so a glyph whose true rank has no template cannot win just because its rivals are missing."""
    if g is None or g.sum() == 0: return None, 0.0, 0.0, "none"
    font = dict(_ranked(g, font_bank())) if font_scores is None else font_scores
    photo = dict(_ranked(g, photo_templates)) if len(photo_templates) else {}
    best = (0.0, 0.0)
    if photo:
        top = max(photo, key=photo.get)
        rivals = [photo.get(r, font.get(r, -1.0)) for r in RANKS if r != top]
        m = photo[top] - max(rivals)
        if photo[top] >= PHOTO_SCORE and m >= PHOTO_MARGIN: return top, photo[top], m, "photo"
        best = (photo[top], m)
    if font and font_tier_enabled():
        order = sorted(font.items(), key=lambda kv: -kv[1]); m = order[0][1] - order[1][1]
        if order[0][1] >= FONT_SCORE and m >= FONT_MARGIN: return order[0][0], order[0][1], m, "font"
        best = (order[0][1], m)
    return None, best[0], best[1], "abstain"


def font_fit(found):
    """Median best font-bank score over the glyphs of one image: about 0.86 on the calibrated skin, far lower when the
    skin's index font is unlike every bundled font (then no rank should be named from fonts)."""
    tops = [_ranked(g, font_bank())[0][1] for g in found if g is not None and g.sum()]
    return float(np.median(tops)) if tops else 0.0


def read_ranks(found, templates=()):
    """Rank every glyph of one image: {key: (rank or None, score, margin, tier)}.

    1. match() each glyph; font-tier reads are dropped when the image's font fit is below FONT_FIT.
    2. Confident reads become same-skin templates for the glyphs that abstained (a board repeats ranks, and copies of
       a rank on one screen are near-identical); only the photo-tier gate can accept them."""
    templates = list(templates)
    font_scores = {k: dict(_ranked(g, font_bank())) if g is not None and g.sum() else {} for k, g in found.items()}
    tops = [max(scores.values()) for scores in font_scores.values() if scores]
    fit = float(np.median(tops)) if tops else 0.0
    out = {}
    for k, g in found.items():
        r = match(g, templates, font_scores=font_scores[k])
        if r[3] == "font" and fit < FONT_FIT: r = (None, r[1], r[2], "font_unfit")
        out[k] = r
    local = [(r[0], found[k]) for k, r in out.items() if r[0]]
    for k, g in found.items():
        if out[k][0] is None and local:
            r = match(g, templates + local, font_scores=font_scores[k])
            if r[3] == "photo": out[k] = (r[0], r[1], r[2], "same_image")
    return out, fit


def build_bank(fonts, out=BANK):
    """Render the bundled font bank. Used by tools/build_font_bank.py; fonts must be openly licensed."""
    bank = _render_bank(fonts)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, ranks=np.array([r for r, _ in bank]), glyphs=np.round(np.stack([g for _, g in bank]) * 255).astype(np.uint8))
    return len(bank)
