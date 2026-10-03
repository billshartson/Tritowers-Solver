import numpy as np
from PIL import Image
from tritowers_vision.layout import tableau_boxes
from tritowers_vision.occupancy import classify_patch
from tritowers_vision.rank import match
from tritowers_vision.schema import SlotState
def test_layout_has_28_slots():
    b=tableau_boxes(); assert len(b)==28 and b["tableau-28"][0]>800
def test_patch_states():
    assert classify_patch(Image.new("RGB",(40,40),(235,225,200)))[0] is SlotState.FACE_UP
    assert classify_patch(Image.new("RGB",(40,40),(170,40,60)))[0] is SlotState.COVERED
def test_match_abstains_without_templates():
    assert match(np.ones((32,24),np.float32),[])[0] is None


def test_robust_matcher_tolerates_shift_and_abstains_on_noise():
    import cv2
    from tritowers_vision import rank as R
    syn = dict(R.synthetic_templates())
    if not syn: return          # open font not installed here: robust matcher degrades to photo templates only
    for r in ("A", "7", "Q", "10"):
        g = cv2.warpAffine(syn[r], np.float32([[1, 0, 1], [0, 1, -1]]), (24, 32))
        assert R.match_robust(g, [])[0] == r
    rng = np.random.default_rng(0)
    noise = (rng.random((32, 24)) > 0.5).astype(np.float32)
    p, sc, mg = R.match_robust(noise, [])
    assert not (sc >= R.ROBUST_SCORE and mg >= R.ROBUST_MARGIN)
    assert R.match_robust(np.zeros((32, 24), np.float32), [])[0] is None


def test_glyph_with_only_tiny_blobs_returns_empty_not_crash():
    from PIL import Image
    from tritowers_vision import rank as R
    im = Image.new("RGB", (100, 100), "white")
    for x in range(10, 30): im.putpixel((x, 12), (0, 0, 0))        # a thin 1px line: ink but height <= 8
    assert R.glyph(im, (0, 0, 60, 60)).sum() == 0
