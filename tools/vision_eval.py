"""Measure photo readers on labelled images: what the user would get in the draft board, slot by slot.

Two data sources:
  --labels DIR/labels.json   real (private) or saved synthetic images. Each entry: {"image": "file.jpg",
                             "board": "28 tokens, rank / ? covered / -- empty", "waste": "Q"}. Photo templates are
                             built leave-one-image-out from the other labelled images (never from the image scored).
  --synthetic                generated in memory by tools/vision_synth.py: several skins (one font each, none of them
                             in the reader's bundled template bank), a few template images per skin, then test images
                             as screenshots, loose crops and phone photos.

Outcome per slot (28 tableau + waste), comparing the draft token with the truth:
  correct | abstain (a face-up card left as '?', the user is asked) | flagged (wrong but listed for review)
  | silent (wrong and NOT flagged: the dangerous case).
A board is "exact" with every slot correct and "safe" with no silent errors.

    python tools/vision_eval.py --synthetic --skins 8 --per-mode 4 --readers v2,v3
    python tools/vision_eval.py --labels private/labels.json --readers v3
"""
from collections import defaultdict
from pathlib import Path
import argparse, json, random, sys, time

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "tools"):
    if str(p) not in sys.path: sys.path.insert(0, str(p))

RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
SLOTS = [f"tableau-{i:02d}" for i in range(1, 29)] + ["waste"]


# ---------------------------------------------------------------------- readers
def _v2_rectified(data):
    from tritowers_vision.image import extract_screen
    ex = extract_screen(data, None)
    if ex.rectified is None:                                  # same full-frame fallback as app.py / web_app.py
        w, h = ex.normalized.size; ex = extract_screen(data, [(0, 0), (w, 0), (w, h), (0, h)])
    return ex.rectified


def read_v2(data, templates):
    from tritowers_vision.calibrated import read
    return read(_v2_rectified(data), templates)


def glyphs_v2(data, board, waste):
    from tritowers_vision import rank2
    from tritowers_vision.layout import tableau_boxes
    from tritowers_vision.rank import corner_box
    rect = _v2_rectified(data); boxes = tableau_boxes(); out = []
    for i, tok in enumerate(board, 1):
        if tok in RANKS:
            g = rank2.glyph(rect.crop(corner_box(boxes[f"tableau-{i:02d}"])), 1.0)
            if g.sum(): out.append((tok, g))
    box = rank2.waste_corner_box(rect)
    if box is not None and waste in RANKS:
        g = rank2.glyph(rect.crop(box), 1.5)
        if g.sum(): out.append((waste, g))
    return out


def read_v3(data, templates):
    from tritowers_vision.reader import read_photo
    return read_photo(data, templates).draft


def glyphs_v3(data, board, waste):
    from tritowers_vision.reader import labelled_glyphs
    return labelled_glyphs(data, board, waste)


READERS = {"v2": (read_v2, glyphs_v2), "v3": (read_v3, glyphs_v3)}


# ---------------------------------------------------------------------- scoring
def draft_tokens(draft):
    """The tokens the app would put in the board box: rank, '?' (covered/unknown/unread), '--' (empty)."""
    out = {}
    for slot in SLOTS:
        c = draft["cards"].get(slot, {"state": "unknown", "rank": None})
        if slot == "waste": out[slot] = c.get("rank") or "?"
        else: out[slot] = "--" if c["state"] == "empty" else (c.get("rank") or "?")
    return out


def score(draft, board, waste):
    tok = draft_tokens(draft); flagged = set(draft.get("needs_human_review") or [])
    truth = dict(zip(SLOTS, list(board) + [waste]))
    res = {}
    for slot in SLOTS:
        t, p = truth[slot], tok[slot]
        if p == t: res[slot] = "correct"
        elif t in RANKS and p == "?": res[slot] = "abstain"
        elif slot in flagged: res[slot] = "flagged"
        else: res[slot] = "silent"
    return res, truth


def summarise(rows):
    """rows: list of (slot_results, truth, seconds)."""
    n = len(rows); c = defaultdict(int); rk = defaultdict(int); exact = safe = 0; secs = 0.0
    for res, truth, s in rows:
        secs += s
        for slot, r in res.items():
            c[r] += 1
            if truth[slot] in RANKS: rk[r] += 1
        exact += all(r == "correct" for r in res.values()); safe += not any(r == "silent" for r in res.values())
    total = sum(c.values()) or 1; rtotal = sum(rk.values()) or 1
    return {"images": n, "slot_correct": c["correct"] / total, "slot_abstain": c["abstain"] / total,
            "slot_flagged": c["flagged"] / total, "silent_per_image": c["silent"] / max(n, 1),
            "rank_correct": rk["correct"] / rtotal, "rank_abstain": rk["abstain"] / rtotal,
            "rank_wrong": (rk["flagged"] + rk["silent"]) / rtotal, "exact": exact / max(n, 1), "safe": safe / max(n, 1),
            "sec": secs / max(n, 1)}


def run_one(reader, data, templates, board, waste):
    t0 = time.perf_counter()
    try: draft = READERS[reader][0](data, templates)
    except Exception as e:                                      # a crash leaves every slot unread: counts as abstain/silent
        draft = {"cards": {}, "needs_human_review": [], "error": repr(e)}
    return (*score(draft, board, waste), time.perf_counter() - t0)


# ---------------------------------------------------------------------- data sources
def synthetic_sets(skins, per_mode, k_train, seed, modes):
    import vision_synth as V
    fonts = [f for f in V.SKIN_FONTS if f is None or Path(f).exists()]
    for i in range(skins):
        rng = random.Random(seed * 1000 + i)
        skin = V.Skin.random(rng, fonts[i % len(fonts)])
        train = [V.sample(rng, rng.choice(["screenshot", "crop"]), skin) for _ in range(k_train)]
        test = [V.sample(rng, m, skin) for m in modes for _ in range(per_mode)]
        yield skin, train, test


def load_labels(path):
    path = Path(path); items = []
    # board may be a string of 28 tokens or a list; "stock_hud" and other fields are ignored here
    for e in json.loads(path.read_text()):
        board = e["board"].split() if isinstance(e["board"], str) else list(e["board"])
        if len(board) != 28: raise SystemExit(f"{e['image']}: board needs 28 tokens, got {len(board)}")
        items.append({"bytes": (path.parent / e["image"]).read_bytes(), "board": board, "waste": e["waste"],
                      "mode": e.get("mode", "real"), "image": e["image"]})
    return items


def table(results):
    keys = ["images", "slot_correct", "slot_abstain", "silent_per_image", "rank_correct", "rank_abstain", "rank_wrong", "exact", "safe", "sec"]
    head = f"{'reader':6} {'templates':9} {'mode':10} " + " ".join(f"{k:>15}" for k in keys)
    lines = [head, "-" * len(head)]
    for (reader, regime, mode), s in sorted(results.items()):
        vals = " ".join(f"{s[k]:>15.3f}" if isinstance(s[k], float) else f"{s[k]:>15}" for k in keys)
        lines.append(f"{reader:6} {regime:9} {mode:10} {vals}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels"); ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--readers", default="v2,v3"); ap.add_argument("--skins", type=int, default=8)
    ap.add_argument("--per-mode", type=int, default=4); ap.add_argument("--train", type=int, default=4)
    ap.add_argument("--seed", type=int, default=7); ap.add_argument("--modes", default="screenshot,crop,photo")
    ap.add_argument("--regimes", default="none,photo", help="none = no photo templates, photo = templates from labelled images")
    ap.add_argument("--old-font", help="font file for v2's font tier (it only looks in Linux font paths)")
    ap.add_argument("--captures", type=int, default=0, help="with --labels: also score K simulated crops and K phone photos of each image")
    ap.add_argument("--json", help="write per-group summaries here"); ap.add_argument("--failures", type=int, default=0)
    a = ap.parse_args(argv)
    readers = a.readers.split(","); regimes = a.regimes.split(",")
    if a.old_font:
        from tritowers_vision import rank2
        rank2._FONTS = (a.old_font,) + tuple(rank2._FONTS); rank2._SYN = None
    rows = defaultdict(list); fails = []
    if a.synthetic:
        for skin, train, test in synthetic_sets(a.skins, a.per_mode, a.train, a.seed, a.modes.split(",")):
            for reader in readers:
                tmpl = {"none": [], "photo": [g for s in train for g in READERS[reader][1](s["bytes"], s["board"], s["waste"])]}
                for regime in regimes:
                    for s in test:
                        res, truth, sec = run_one(reader, s["bytes"], tmpl[regime], s["board"], s["waste"])
                        for key in ((reader, regime, s["mode"]), (reader, regime, "ALL")): rows[key].append((res, truth, sec))
                        if any(r == "silent" for r in res.values()):
                            fails.append((reader, regime, s["mode"], s["font"], {k: (truth[k], r) for k, r in res.items() if r == "silent"}))
    if a.labels:
        items = load_labels(a.labels)
        variants = [[(it["mode"], it["bytes"])] for it in items]
        if a.captures:                                         # the labelled screens re-shot as loose crops and phone photos
            import vision_synth as V
            from PIL import Image
            import io
            for i, it in enumerate(items):
                screen = Image.open(io.BytesIO(it["bytes"])).convert("RGB")
                for k in range(a.captures):
                    for mode in ("crop", "photo"):
                        rng = random.Random(a.seed * 7919 + i * 101 + k * 7 + len(mode))
                        img, _ = V.capture(screen, rng, mode)
                        variants[i].append((mode, V.encode(img, rng, mode)))
        for reader in readers:
            glyphs = [READERS[reader][1](it["bytes"], it["board"], it["waste"]) for it in items]   # templates come from clean screens
            for regime in regimes:
                for i, it in enumerate(items):
                    tmpl = [] if regime == "none" else [g for j, gs in enumerate(glyphs) if j != i for g in gs]
                    for v, (mode, data) in enumerate(variants[i]):
                        res, truth, sec = run_one(reader, data, tmpl, it["board"], it["waste"])
                        for key in ((reader, regime, mode), (reader, regime, "ALL")): rows[key].append((res, truth, sec))
                        if any(r == "silent" for r in res.values()):
                            fails.append((reader, regime, f"{it['image']}#{v}", mode, {k: (truth[k], r) for k, r in res.items() if r == "silent"}))
    if not rows: ap.error("give --synthetic and/or --labels")
    results = {k: summarise(v) for k, v in rows.items()}
    print(table(results))
    for f in fails[:a.failures]: print("silent:", *f)
    if a.json: Path(a.json).write_text(json.dumps({"|".join(k): v for k, v in results.items()}, indent=1))
    return results


if __name__ == "__main__":
    main()
