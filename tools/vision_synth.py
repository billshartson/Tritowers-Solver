"""Synthetic Tri Towers screens and phone-style photos with exact labels, for measuring the photo reader.

Nothing here is a real screenshot. Geometry follows tritowers_vision.layout (the calibrated 1024x768 skin) and the look
approximates that skin (parchment band, HUD bar, dark lower band, cream faces, red backs with a cream border), so
results show how the pipeline copes with capture conditions and layouts, not how well it matches the real machine.
For that, use tools/vision_eval.py --labels on real labelled images (optionally with --captures to re-shoot them). Rank glyphs are drawn with a font chosen per "skin"; evaluate with fonts that are NOT in the
reader's template bank, otherwise the font tier is being tested against itself.

    python tools/vision_synth.py OUT_DIR --count 40 --seed 1    # writes PNG/JPEG files plus labels.json
"""
from dataclasses import dataclass, field
from pathlib import Path
import io, json, math, random, sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from tritowers_vision import layout                       # noqa: E402

RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
BLOCKERS = {1: (4, 5), 2: (6, 7), 3: (8, 9), 4: (10, 11), 5: (11, 12), 6: (13, 14), 7: (14, 15), 8: (16, 17), 9: (17, 18),
            10: (19, 20), 11: (20, 21), 12: (21, 22), 13: (22, 23), 14: (23, 24), 15: (24, 25), 16: (25, 26), 17: (26, 27), 18: (27, 28)}
SS = 2                      # render the screen at 2x so photos keep detail when the screen fills the frame
SCREEN = (1024, 768)
CARD_H = 150
WASTE_W, WASTE_H = 120, 180
# Fonts for held-out skins (system fonts on macOS, common Linux fonts as fallbacks). None means Pillow's bundled font.
SKIN_FONTS = (
    "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
    "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Trebuchet MS Bold.ttf",
    "/System/Library/Fonts/Supplemental/Verdana Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf",
    "/System/Library/Fonts/Supplemental/Tahoma Bold.ttf",
    None,
)


def _font(path, size):
    if path:
        try: return ImageFont.truetype(path, size)
        except OSError: pass
    return ImageFont.load_default(size=size)


@dataclass
class Skin:
    font: str | None = None
    face: tuple = (235, 225, 200)
    back: tuple = (170, 40, 60)
    black: tuple = (25, 25, 30)
    red: tuple = (200, 30, 40)
    bg: tuple = (105, 80, 40)    # parchment
    glyph_px: int = 24            # cap height of the tableau rank index, in 1024x768 screen pixels

    @staticmethod
    def random(rng, font=None):
        j = lambda c, d: tuple(int(np.clip(v + rng.randint(-d, d), 0, 255)) for v in c)
        bg = rng.choice([(105, 80, 40), (95, 72, 38), (115, 88, 48)])            # parchment browns
        return Skin(font=font, face=j((235, 225, 200), 8), back=j((170, 40, 60), 12), bg=j(bg, 10),
                    red=j((200, 30, 40), 15), black=j((25, 25, 30), 10), glyph_px=rng.randint(21, 27))


@dataclass
class Deal:
    tableau: list                 # 28 tokens: rank (face up), "?" (covered), "--" (removed)
    waste: str
    waste_dy: int = 0
    stock_count: int = 23
    suits: dict = field(default_factory=dict)

    def tokens(self): return list(self.tableau), self.waste


def random_deal(rng, removed=None):
    """A reachable position: remove `removed` exposed cards one at a time, flip what becomes exposed."""
    deck = [r for r in RANKS for _ in range(4)]; rng.shuffle(deck)
    present = set(range(1, 29))
    k = removed if removed is not None else (0 if rng.random() < .35 else rng.randint(1, 22))
    for _ in range(k):
        exposed = [p for p in present if all(b not in present for b in BLOCKERS.get(p, ()))]
        present.discard(rng.choice(exposed))
    tableau = []
    for p in range(1, 29):
        if p not in present: tableau.append("--")
        elif all(b not in present for b in BLOCKERS.get(p, ())): tableau.append(deck.pop())
        else: tableau.append("?")
    suits = {p: rng.choice("CDHS") for p in range(1, 29)}; suits["waste"] = rng.choice("CDHS")
    return Deal(tableau, deck.pop(), waste_dy=rng.randint(-25, 0), stock_count=rng.randint(0, 23), suits=suits)


def _suit_poly(suit, cx, cy, s):
    """Simple suit pip shapes (enough to give the index a second blob like real cards)."""
    if suit == "D": return "poly", [(cx, cy - s), (cx + .7 * s, cy), (cx, cy + s), (cx - .7 * s, cy)]
    if suit == "H": return "heart", (cx, cy, s)
    if suit == "S": return "spade", (cx, cy, s)
    return "club", (cx, cy, s)


def _draw_suit(d, suit, cx, cy, s, fill):
    kind, a = _suit_poly(suit, cx, cy, s)
    if kind == "poly": d.polygon(a, fill=fill); return
    cx, cy, s = a; r = s * .5
    if kind == "heart":
        d.ellipse((cx - s, cy - s * .8, cx, cy + r * .4), fill=fill); d.ellipse((cx, cy - s * .8, cx + s, cy + r * .4), fill=fill)
        d.polygon([(cx - s, cy - s * .2), (cx + s, cy - s * .2), (cx, cy + s)], fill=fill)
    elif kind == "spade":
        d.polygon([(cx, cy - s), (cx + s, cy + s * .3), (cx - s, cy + s * .3)], fill=fill)
        d.ellipse((cx - s, cy - s * .2, cx, cy + s * .6), fill=fill); d.ellipse((cx, cy - s * .2, cx + s, cy + s * .6), fill=fill)
        d.rectangle((cx - s * .12, cy + s * .2, cx + s * .12, cy + s), fill=fill)
    else:
        for ox, oy in ((0, -.45), (-.45, .15), (.45, .15)): d.ellipse((cx + (ox - .42) * s, cy + (oy - .42) * s, cx + (ox + .42) * s, cy + (oy + .42) * s), fill=fill)
        d.rectangle((cx - s * .12, cy, cx + s * .12, cy + s), fill=fill)


def _text(d, xy, text, font, fill, cap_px):
    """Draw text so its ink box starts at xy and its cap height is about cap_px (fonts differ in metrics)."""
    box = d.textbbox((0, 0), text, font=font)
    d.text((xy[0] - box[0], xy[1] - box[1]), text, font=font, fill=fill)
    return box[2] - box[0], box[3] - box[1]


def _font_for_cap(path, cap_px, cache={}):
    key = (path, cap_px)
    if key not in cache:
        size = cap_px
        for _ in range(4):
            f = _font(path, size); box = f.getbbox("K")
            h = max(1, box[3] - box[1]); size = max(6, int(round(size * cap_px / h)))
        cache[key] = _font(path, size)
    return cache[key]


def _card_face(rank, suit, w, h, skin, scale, rng):
    s = SS * scale
    im = Image.new("RGB", (int(w * SS), int(h * SS)), skin.bg); d = ImageDraw.Draw(im)
    r = int(7 * SS)
    d.rounded_rectangle((0, 0, im.width - 1, im.height - 1), r, fill=skin.face, outline=(120, 120, 120), width=max(1, SS))
    ink = skin.red if suit in "DH" else skin.black
    cap = int(round(skin.glyph_px * s))
    font = _font_for_cap(skin.font, cap)
    x0, y0 = int(6 * s), int(5 * s)
    if rank == "10":                                       # real indexes squeeze "10" into the index column
        tw, th = _text(ImageDraw.Draw(tmp := Image.new("L", (cap * 4, cap * 2), 0)), (0, 0), "10", font, 255, cap)
        glyph = tmp.crop((0, 0, tw, th)).resize((int(tw * .82), th)); im.paste(Image.new("RGB", glyph.size, ink), (x0 - int(s), y0), glyph)
        gw = glyph.width
    else:
        gw, _ = _text(d, (x0, y0), rank, font, ink, cap)
    _draw_suit(d, suit, x0 + max(gw, cap * .7) / 2, y0 + cap + 11 * s, 7 * s, ink)
    cx, cy = im.width / 2, im.height * .55
    if rank in "JQK":                                      # court art: coloured panel lowers the cream share
        d.rectangle((im.width * .22, im.height * .3, im.width * .9, im.height * .9), fill=(205, 170, 70), outline=ink, width=2 * SS)
        d.ellipse((cx - 14 * s, cy - 24 * s, cx + 14 * s, cy + 4 * s), fill=(230, 190, 160), outline=(40, 40, 40))
        d.rectangle((cx - 20 * s, cy + 4 * s, cx + 20 * s, cy + 40 * s), fill=skin.red if rng.random() < .5 else (40, 60, 140))
    else:
        _draw_suit(d, suit, cx + 6 * s, cy, 15 * s, ink)
    return im


def _card_back(w, h, skin):
    im = Image.new("RGB", (int(w * SS), int(h * SS)), skin.bg); d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, im.width - 1, im.height - 1), int(7 * SS), fill=skin.face, outline=(120, 110, 100), width=SS)
    d.rectangle((7 * SS, 7 * SS, im.width - 7 * SS, im.height - 7 * SS), fill=skin.back)
    dark = tuple(int(c * .78) for c in skin.back)
    for k in range(-im.height, im.width, 10 * SS):
        d.line((k, 7 * SS, k + im.height, im.height + 7 * SS), fill=dark, width=SS)
    d.rectangle((7 * SS, 7 * SS, im.width - 7 * SS, im.height - 7 * SS), outline=skin.face, width=2 * SS)
    return im


def _hud(d, skin, rng):
    """HUD bar, bottom-corner panels and a red timer, like the calibrated skin: distractors for alignment."""
    W = SCREEN[0] * SS
    f = _font(None, 22 * SS)
    d.rectangle((0, 0, W, 112 * SS), fill=(150, 105, 60))
    for x0, label in ((55, "CURRENT SCORE"), (400, "CASHPOT"), (740, "SCORE TO BEAT")):
        d.rounded_rectangle((x0 * SS, 4 * SS, (x0 + 225) * SS, 100 * SS), 8 * SS, fill=(25, 45, 70), outline=(230, 230, 220), width=2 * SS)
        d.text(((x0 + 20) * SS, 12 * SS), label, font=f, fill=(240, 240, 240))
        d.text(((x0 + 60) * SS, 50 * SS), str(rng.randint(0, 999999)), font=_font(None, 30 * SS), fill=(255, 255, 255))
    d.rounded_rectangle((0, 690 * SS, 245 * SS, 750 * SS), 6 * SS, fill=(200, 160, 100))
    d.text((25 * SS, 700 * SS), "LONGEST RUN %d" % rng.randint(0, 9), font=f, fill=(120, 20, 20))
    d.ellipse((820 * SS, 640 * SS, 920 * SS, 745 * SS), fill=(170, 30, 30), outline=(200, 170, 80), width=3 * SS)


def _background(skin, rng):
    """Dark screen, textured parchment band between the HUD and a wavy lower edge (as in the calibrated skin)."""
    W, H = SCREEN[0] * SS, SCREEN[1] * SS
    g = np.random.default_rng(rng.randint(0, 2**31))
    a = np.full((H, W, 3), 12, np.float32)
    tex = cv2.resize(g.normal(0, 1, (H // 32, W // 32)).astype(np.float32), (W, H), interpolation=cv2.INTER_CUBIC)
    par = np.array(skin.bg, np.float32)[None, None, :] * (1 + 0.12 * tex[..., None])
    xs = np.arange(W) / SS
    bottom = (620 + 18 * np.sin(xs / 90 + rng.uniform(0, 6))) * SS
    yy = np.arange(H)[:, None]
    band = (yy >= 118 * SS) & (yy < bottom[None, :])
    a[band] = par[band]
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)); d = ImageDraw.Draw(im)
    for _ in range(40):                                        # map ink: thin dark curves
        x, y = rng.uniform(0, W), rng.uniform(130 * SS, 600 * SS)
        pts = [(x + rng.uniform(-60, 60) * SS * k, y + rng.uniform(-30, 30) * SS * k) for k in range(4)]
        d.line(pts, fill=(60, 45, 25), width=SS)
    return im


def render_screen(deal, skin, rng):
    """The game screen at SS x 1024x768, with deal drawn in the calibrated layout."""
    im = _background(skin, rng); d = ImageDraw.Draw(im)
    _hud(d, skin, rng)
    boxes = layout.tableau_boxes()
    for p in range(1, 29):                                   # row order = draw order: lower rows overlap upper rows
        x0, y0, x1, _ = boxes[f"tableau-{p:02d}"]; tok = deal.tableau[p - 1]
        if tok == "--": continue
        card = _card_back(x1 - x0, CARD_H, skin) if tok == "?" else _card_face(tok, deal.suits.get(p, "S"), x1 - x0, CARD_H, skin, 1.0, rng)
        im.paste(card, (x0 * SS, y0 * SS))
    sx0, sy0, _, _ = layout.STOCK_BOX
    if deal.stock_count > 0:
        for k in range(min(3, deal.stock_count)):
            im.paste(_card_back(WASTE_W - 2, WASTE_H - 2, skin), ((sx0 + 2 * k) * SS, (sy0 - 2 * k) * SS))
        cx0, cy0, cx1, cy1 = layout.STOCK_COUNTER_BOX
        d.text(((cx0 + 10) * SS, (cy0 + 10) * SS), str(deal.stock_count + 1), font=_font(None, 26 * SS), fill=(255, 255, 255))
    wx0, wy0 = layout.WASTE_BOX[0], layout.WASTE_BOX[1] + deal.waste_dy
    im.paste(_card_face(deal.waste, deal.suits.get("waste", "S"), WASTE_W, WASTE_H, skin, 1.5, rng), (wx0 * SS, wy0 * SS))
    return im


# ---------------------------------------------------------------------- capture simulation
def _corners_rect(w, h): return np.float32([[0, 0], [w, 0], [w, h], [0, h]])


def _photo_effects(a, rng, strength):
    a = a.astype(np.float32)
    h, w = a.shape[:2]
    if rng.random() < .8 * strength:                        # moire from the LCD pixel grid
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32); th = rng.uniform(0, math.pi); f = rng.uniform(.25, .9)
        a += rng.uniform(2, 9) * strength * np.sin(f * (xx * math.cos(th) + yy * math.sin(th)))[..., None]
    for _ in range(rng.randint(0, 2) if rng.random() < .7 * strength else 0):   # glare from the glass
        mask = np.zeros((h, w), np.float32); cx, cy = rng.uniform(0, w), rng.uniform(0, h)
        cv2.ellipse(mask, (int(cx), int(cy)), (int(rng.uniform(.05, .25) * w), int(rng.uniform(.03, .15) * h)), rng.uniform(0, 180), 0, 360, 1.0, -1)
        mask = cv2.GaussianBlur(mask, (0, 0), w * .03)
        a += mask[..., None] * rng.uniform(40, 130) * strength
    gain = np.array([rng.uniform(.85, 1.15) for _ in range(3)], np.float32) ** strength      # white balance
    a *= gain * rng.uniform(.75, 1.25) ** strength                                          # exposure
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    a *= (1 - .35 * strength * rng.random() * (((xx - w / 2) / w) ** 2 + ((yy - h / 2) / h) ** 2) * 2)[..., None]   # vignette
    a = np.clip(a, 0, 255)
    g = rng.uniform(.75, 1.35) ** strength; a = 255 * (a / 255) ** g
    sigma = rng.uniform(0, 1.6) * strength * max(1, w / 1500)
    if sigma > .3: a = cv2.GaussianBlur(a, (0, 0), sigma)
    if rng.random() < .2 * strength:                        # small hand-shake
        k = rng.randint(3, 9); ker = np.zeros((k, k), np.float32); ker[k // 2] = 1 / k
        ker = cv2.warpAffine(ker, cv2.getRotationMatrix2D((k / 2 - .5, k / 2 - .5), rng.uniform(0, 180), 1), (k, k)); ker /= ker.sum()
        a = cv2.filter2D(a, -1, ker)
    a += np.random.default_rng(rng.randint(0, 2**31)).normal(0, rng.uniform(1, 6) * strength, a.shape)
    return np.clip(a, 0, 255).astype(np.uint8)


def capture(screen, rng, mode):
    """Turn a screen into an input image. Returns (PIL image, 4 screen corners in the output image as [[x, y], ...])."""
    src = np.asarray(screen); sh, sw = src.shape[:2]
    if mode == "screenshot":                                 # exact screen, rescaled
        w = rng.choice([800, 1024, 1280, 1600]); h = int(round(w * sh / sw))
        out = cv2.resize(src, (w, h), interpolation=cv2.INTER_AREA)
        return Image.fromarray(out), (_corners_rect(w, h) - .5).tolist()
    if mode == "crop":                                       # screen plus a loose, slightly rotated hand crop
        w = rng.choice([900, 1200, 1500]); h = int(round(w * .75))
        m = [rng.uniform(-.02, .07) for _ in range(4)]
        quad = np.float32([[m[0] * w, m[1] * h], [w * (1 - m[2]), m[1] * h + rng.uniform(-.01, .01) * h],
                           [w * (1 - m[2]), h * (1 - m[3])], [m[0] * w + rng.uniform(-.01, .01) * w, h * (1 - m[3])]])
        H = cv2.getPerspectiveTransform(_corners_rect(sw, sh), quad)
        out = cv2.warpPerspective(src, H, (w, h), flags=cv2.INTER_AREA, borderValue=(18, 18, 20))
        out = _photo_effects(out, rng, .5)
        return Image.fromarray(out), quad.tolist()
    # "photo": phone photo of the cabinet, landscape or portrait, perspective and photo artefacts
    portrait = rng.random() < .4
    W, Hh = (1500, 2000) if portrait else (2000, 1500)
    fill = rng.uniform(.55, .92) * W
    sw2, sh2 = fill, fill * .75
    cx, cy = W / 2 + rng.uniform(-.08, .08) * W, Hh / 2 + rng.uniform(-.1, .1) * Hh
    quad = np.float32([[cx - sw2 / 2, cy - sh2 / 2], [cx + sw2 / 2, cy - sh2 / 2], [cx + sw2 / 2, cy + sh2 / 2], [cx - sw2 / 2, cy + sh2 / 2]])
    t = rng.uniform(-.12, .12); quad[0, 0] += t * sw2; quad[3, 0] -= t * sw2 * .5            # keystone
    v = rng.uniform(-.1, .1); quad[0, 1] += v * sh2; quad[1, 1] -= v * sh2
    quad += np.float32([[rng.uniform(-.025, .025) * sw2, rng.uniform(-.025, .025) * sh2] for _ in range(4)])
    ang = math.radians(rng.uniform(-10, 10)); R = np.float32([[math.cos(ang), -math.sin(ang)], [math.sin(ang), math.cos(ang)]])
    quad = ((quad - [cx, cy]) @ R.T + [cx, cy]).astype(np.float32)
    # cabinet: dark surround, bezel ring, a lit panel, some texture
    cab = np.full((Hh, W, 3), rng.randint(10, 60), np.uint8)
    cab = (cab.astype(np.int16) + np.random.default_rng(rng.randint(0, 2**31)).integers(-8, 8, cab.shape)).clip(0, 255).astype(np.uint8)
    bez = ((quad - [cx, cy]) * rng.uniform(1.06, 1.18) + [cx, cy]).astype(np.int32)
    cv2.fillConvexPoly(cab, bez, tuple(int(rng.randint(5, 45)) for _ in range(3)))
    if rng.random() < .6:
        top = int(max(0, bez[:, 1].min() - rng.uniform(.05, .2) * Hh))
        cv2.rectangle(cab, (int(bez[:, 0].min()), top), (int(bez[:, 0].max()), int(bez[:, 1].min() - 10)), tuple(rng.randint(80, 220) for _ in range(3)), -1)
    H = cv2.getPerspectiveTransform(_corners_rect(sw, sh), quad)
    warped = cv2.warpPerspective(src, H, (W, Hh), flags=cv2.INTER_AREA)
    mask = cv2.warpPerspective(np.full((sh, sw), 255, np.uint8), H, (W, Hh), flags=cv2.INTER_NEAREST)
    out = np.where(mask[..., None] > 0, warped, cab)
    out = _photo_effects(out, rng, 1.0)
    return Image.fromarray(out), quad.tolist()


def encode(image, rng, mode):
    buf = io.BytesIO()
    if mode == "screenshot" and rng.random() < .5: image.save(buf, format="PNG")
    else: image.save(buf, format="JPEG", quality=rng.randint(55, 92))
    return buf.getvalue()


def sample(rng, mode, skin=None, deal=None):
    skin = skin or Skin.random(rng, rng.choice(SKIN_FONTS))
    deal = deal or random_deal(rng)
    img, quad = capture(render_screen(deal, skin, rng), rng, mode)
    # quad is in 2x-screen units for the source; corners map the 1024x768 screen frame into the output image
    return {"bytes": encode(img, rng, mode), "board": deal.tableau, "waste": deal.waste, "corners": quad, "mode": mode,
            "font": Path(skin.font).stem if skin.font else "pillow-default"}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path); ap.add_argument("--count", type=int, default=30); ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--modes", default="screenshot,crop,photo")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True); rng = random.Random(a.seed); labels = []
    modes = a.modes.split(",")
    for i in range(a.count):
        s = sample(rng, modes[i % len(modes)])
        ext = "png" if s["bytes"][:4] == b"\x89PNG" else "jpg"
        name = f"synth-{i:04d}-{s['mode']}.{ext}"; (a.out / name).write_bytes(s.pop("bytes"))
        labels.append({"image": name, **s})
    (a.out / "labels.json").write_text(json.dumps(labels, indent=1))
    print(f"Wrote {len(labels)} images and labels.json to {a.out}")


if __name__ == "__main__":
    main()
