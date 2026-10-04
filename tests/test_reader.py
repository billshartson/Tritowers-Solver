"""Photo reader v3 on synthetic screens: no private images are used.

Ranks are drawn with Pillow's bundled font, which is not in the reader's font bank, so these tests read ranks through
same-skin templates cut from another synthetic screen (the deployment path) and otherwise only allow abstentions."""
import importlib.util
import io
import random
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location("vision_synth", ROOT / "tools/vision_synth.py")
V = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(V)

import solver                                                      # noqa: E402
from tritowers_vision import glyphs, reader, scene                 # noqa: E402

RANKS = set(V.RANKS)


def _png(image):
    buf = io.BytesIO(); image.save(buf, format="PNG"); return buf.getvalue()


def _shot(seed, removed=0, skin=None, mode=None):
    rng = random.Random(seed)
    skin = skin or V.Skin.random(rng, None)
    deal = V.random_deal(rng, removed)
    screen = V.render_screen(deal, skin, rng)
    if mode is None: data = _png(screen.resize(V.SCREEN))
    else: img, _ = V.capture(screen, rng, mode); data = V.encode(img, rng, mode)
    return data, deal, skin


def _check(draft, deal):
    """States must be exact; a rank may be missing (abstain) but never wrong. Returns the number of ranks read."""
    tokens, waste = reader.board_tokens(draft); read = 0
    for p, (got, want) in enumerate(zip(tokens, deal.tableau), 1):
        if want in RANKS: assert got in (want, "?"), (p, got, want); read += got == want
        else: assert got == want, (p, got, want)
    assert waste in (deal.waste, ""), (waste, deal.waste)
    return read + (waste == deal.waste)


def test_blockers_match_solver():
    assert scene.BLOCKERS == solver.BLOCKERS


def test_flip_keeps_the_rules():
    rng = random.Random(3)
    for _ in range(200):
        tokens = V.random_deal(rng).tableau
        present = {p for p, t in enumerate(tokens, 1) if t != "--"}
        assert scene.valid(present)
        for p in range(1, 29): assert scene.valid(scene.flip(present, p))


def test_screenshot_states_are_exact_and_ranks_never_wrong():
    data, deal, _ = _shot(11)
    r = reader.read_photo(data)
    assert r.draft["registration"]["trusted"]
    _check(r.draft, deal)


def test_same_skin_templates_read_the_ranks():
    a, deal_a, skin = _shot(21)
    b, deal_b, _ = _shot(22, skin=skin)
    c, deal_c, _ = _shot(23, removed=6, skin=skin)
    templates = reader.labelled_glyphs(a, deal_a.tableau, deal_a.waste) + reader.labelled_glyphs(b, deal_b.tableau, deal_b.waste)
    known = {r for r, _ in templates}
    r = reader.read_photo(c, templates)
    assert _check(r.draft, deal_c) >= sum(t in known for t in deal_c.tableau + [deal_c.waste]) - 1


def test_phone_photo_of_a_mid_game_board():
    data, deal, _ = _shot(5, removed=9, mode="photo")
    r = reader.read_photo(data)
    assert r.draft["registration"]["trusted"]
    _check(r.draft, deal)
    assert r.overlay.size[0] <= 1280 and r.rectified.size == (1024, 768)


def test_noise_is_not_trusted_and_everything_is_flagged():
    noise = Image.fromarray(np.random.default_rng(0).integers(0, 255, (600, 800, 3), dtype=np.uint8))
    d = reader.read_photo(_png(noise)).draft
    assert not d["registration"]["trusted"] and not d["complete"]
    assert len(d["needs_human_review"]) == 29


def test_font_bank_is_bundled_and_can_be_switched_off(monkeypatch):
    bank = glyphs.font_bank()
    assert glyphs.BANK.exists() and {r for r, _ in bank} == RANKS
    eight = next(g for r, g in bank if r == "8")
    assert glyphs.holes(eight) == 2 and glyphs.match(eight)[0] == "8"
    monkeypatch.setenv("TT_FONT_TIER", "0")
    assert glyphs.match(eight)[0] is None
    assert glyphs.match(eight, [("8", eight)])[3] == "photo"


def test_web_photo_endpoint_returns_a_checkable_draft():
    pytest.importorskip("fastapi"); pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    import web_app
    data, deal, _ = _shot(11)
    client = TestClient(web_app.app)
    r = client.post("/api/photo", files={"file": ("s.png", data, "image/png")}, data={"corners": ""}).json()
    assert r["ok"] and len(r["board"]) == 28 and r["overlay"].startswith("data:image/jpeg;base64,")
    _check({"cards": {**{f"tableau-{i:02d}": {"state": "empty" if t == "--" else "x", "rank": None if t in ("?", "--") else t}
                         for i, t in enumerate(r["board"], 1)}, "waste": {"rank": r["waste"] or None}}}, deal)
    too_big = client.post("/api/photo", files={"file": ("s.png", b"0" * (61 * 1024 * 1024), "image/png")}, data={"corners": ""}).json()
    assert not too_big["ok"] and "too large" in too_big["message"]
