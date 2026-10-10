"""Scene model for the calibrated skin: where every card sits in the 1024x768 frame, what the screen should look like for a
given set of present cards, and which set of present cards best explains the observed colours.

Tri Towers rules make the occupancy problem much smaller than 28 independent guesses:
  * a card can only leave the tableau once it is exposed, so if a card is present, every card it covers is present;
  * a present card is face up exactly when it is exposed (none of its blockers is present), otherwise it shows its back.
So the reader only decides which cards are present; face up vs covered follows from the layout. A removed card does not
leave a hole: the lower half of the card behind it shows through, which a per-slot colour test cannot tell apart from a
covered card. Rendering whole hypotheses and comparing them with the photo handles that.
"""
import numpy as np
import cv2

from .layout import CARD_W, STOCK_BOX, WASTE_BOX, _ROWS

FRAME = (1024, 768)
CARD_H = 150
WASTE_W, WASTE_H = WASTE_BOX[2] - WASTE_BOX[0], WASTE_BOX[3] - WASTE_BOX[1]
WASTE_SEARCH = range(-35, 11, 3)          # the waste card's vertical position varies between frames
SLOTS = [f"tableau-{i:02d}" for i in range(1, 29)]
# Same table as solver.BLOCKERS (checked by a test): the two cards in front of each covered position.
BLOCKERS = {1: (4, 5), 2: (6, 7), 3: (8, 9), 4: (10, 11), 5: (11, 12), 6: (13, 14), 7: (14, 15), 8: (16, 17), 9: (17, 18),
            10: (19, 20), 11: (20, 21), 12: (21, 22), 13: (22, 23), 14: (23, 24), 15: (24, 25), 16: (25, 26), 17: (26, 27), 18: (27, 28)}
COVERS = {p: tuple(q for q, bs in BLOCKERS.items() if p in bs) for p in range(1, 29)}
BACKGROUND, FACE, BACK = 0, 1, 2
# Region scored when comparing hypotheses: the towers plus the stock/waste area (HUD and buttons vary between skins).
ROI = (0, 120, 1024, 768)


def card_rects():
    """Full card rectangles (x0, y0, x1, y1) for positions 1-28, in draw order (later cards are in front)."""
    rects, p = {}, 1
    for centres, top, _bottom in _ROWS:
        for cx in centres:
            rects[p] = (cx - CARD_W // 2, top, cx + CARD_W // 2, top + CARD_H); p += 1
    return rects


RECTS = card_rects()


def waste_rect(dy=0):
    x0, y0 = WASTE_BOX[0], WASTE_BOX[1] + dy
    return (x0, y0, x0 + WASTE_W, y0 + WASTE_H)


def _closure(p, graph):
    out, todo = {p}, [p]
    while todo:
        for q in graph.get(todo.pop(), ()):
            if q not in out: out.add(q); todo.append(q)
    return out


IN_FRONT = {p: _closure(p, BLOCKERS) - {p} for p in range(1, 29)}    # every card that must go before p can
BEHIND = {p: _closure(p, COVERS) - {p} for p in range(1, 29)}       # every card p (transitively) covers


def flip(present, p):
    """Nearest valid set with p toggled: removing p removes what is in front of it, adding p adds what it covers."""
    return (present - {p} - IN_FRONT[p]) if p in present else (present | {p} | BEHIND[p])


def exposed(present, p):
    return all(b not in present for b in BLOCKERS.get(p, ()))


def valid(present):
    return all(q in present for p in present for q in COVERS[p])


def render(present, res=0.25, waste_dy=0, roi=ROI):
    """Class map (BACKGROUND / FACE / BACK) of the ROI at `res` pixels per frame unit."""
    x0, y0, x1, y1 = roi
    out = np.zeros((int(round((y1 - y0) * res)), int(round((x1 - x0) * res))), np.uint8)
    def fill(r, cls):
        a, b, c, d = (int(round((r[0] - x0) * res)), int(round((r[1] - y0) * res)), int(round((r[2] - x0) * res)), int(round((r[3] - y0) * res)))
        out[max(b, 0):max(d, 0), max(a, 0):max(c, 0)] = cls
    for p in range(1, 29):
        if p in present: fill(RECTS[p], FACE if exposed(present, p) else BACK)
    fill(waste_rect(waste_dy), FACE)
    return out


def ignore_mask(res=0.25, roi=ROI):
    """Pixels left out of hypothesis scoring: the stock pile (its counter and depth vary)."""
    x0, y0, x1, y1 = roi
    m = np.zeros((int(round((y1 - y0) * res)), int(round((x1 - x0) * res))), bool)
    sx0, sy0, sx1, sy1 = STOCK_BOX
    m[int((sy0 - 12 - y0) * res):int((sy1 + 12 - y0) * res), int((sx0 - 12 - x0) * res):int((sx1 + 12 - x0) * res)] = True
    return m


class Scorer:
    """Agreement between a hypothesis and per-pixel evidence (face, back) warped into the ROI frame."""

    def __init__(self, face, back, res=0.25, roi=ROI):
        self.res, self.roi = res, roi
        bg = np.clip(1.0 - face - back, 0.0, 1.0)
        keep = ~ignore_mask(res, roi)
        self.ev = np.stack([bg * keep, face * keep, back * keep]).astype(np.float32)   # [class, y, x]
        self._cache = {}

    def score(self, present, waste_dy=0):
        key = (frozenset(present), waste_dy)
        if key not in self._cache:
            lab = render(present, self.res, waste_dy, self.roi)
            self._cache[key] = float(np.take_along_axis(self.ev, lab[None].astype(np.intp), 0).sum())
        return self._cache[key]

    def best_waste_dy(self, present):
        return max(WASTE_SEARCH, key=lambda dy: self.score(present, dy))


def infer_presence(scorer, start=None):
    """Greedy search over valid present-sets (only legal single-card toggles), from all-present and from `start`.

    Returns (present set, waste_dy, per-slot margin in evidence pixels per unit card area)."""
    best = None
    seen = set()
    for init in [set(range(1, 29)), set()] + ([set(start)] if start is not None and valid(start) else []):
        key = frozenset(init)
        if key in seen:
            continue
        seen.add(key)
        cur = set(init); dy = scorer.best_waste_dy(cur); s = scorer.score(cur, dy)
        for _ in range(60):
            moves = []
            for p in range(1, 29):
                if p in cur and exposed(cur, p): nxt = cur - {p}                   # remove an exposed card
                elif p not in cur and all(q in cur for q in COVERS[p]): nxt = cur | {p}   # put back a card whose covers are present
                else: continue
                moves.append((scorer.score(nxt, dy), nxt))
            if not moves: break
            ms, nxt = max(moves, key=lambda m: m[0])
            if ms <= s + 1e-6:
                ndy = scorer.best_waste_dy(cur)
                if ndy == dy: break
                dy = ndy; s = scorer.score(cur, dy); continue
            cur, s = nxt, ms
        if best is None or s > best[1]: best = (cur, s, dy)
    cur, s, dy = best
    area = CARD_W * CARD_H * scorer.res * scorer.res
    # Confidence per slot: how much worse the best rule-respecting alternative with this slot flipped explains the
    # image, in units of one card's area. A covered card is as certain as the cards in front of it.
    margins = {p: (s - scorer.score(flip(cur, p), dy)) / area for p in range(1, 29)}
    return cur, dy, margins


def project(H, pts):
    """Apply a 3x3 homography to an (N, 2) array of points."""
    pts = np.asarray(pts, np.float64).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(pts, np.asarray(H, np.float64)).reshape(-1, 2)
