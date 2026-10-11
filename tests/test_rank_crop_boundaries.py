"""A partial rank cannot become a confident name by dropping border ink.

These generated strokes model a disconnected, cropped loop beside a complete
looking stem. No machine image, crop, font or private coordinates are used.
"""
import cv2
import numpy as np
import pytest
from PIL import Image

from tritowers_vision import glyphs, reader, scene
from tritowers_vision.register import Registration


def stem_patch():
    patch = np.full((189, 120, 3), 238, np.uint8)
    cv2.line(patch, (45, 30), (45, 100), (20, 20, 20), 8)
    cv2.ellipse(patch, (30, 96), (15, 13), 0, 0, 160, (20, 20, 20), 8)
    return patch


@pytest.mark.parametrize("mirror", [False, True])
def test_edge_connected_half_of_rank_cannot_leave_a_complete_stem(mirror):
    clean = stem_patch()
    partial = clean.copy()
    # A damaged index can have a detached loop that runs outside the crop.
    # Ignoring this substantial neighbouring piece makes its stem look whole.
    cv2.ellipse(partial, (4, 54), (20, 22), 0, 0, 360, (20, 20, 20), 8)
    if mirror:
        clean, partial = clean[:, ::-1].copy(), partial[:, ::-1].copy()
    found, detail = glyphs.extract(clean)
    assert found is not None and detail["valid"]
    found, detail = glyphs.extract(partial)
    assert found is None and not detail["valid"]


def test_narrow_border_and_distant_ink_do_not_invalidate_complete_rank():
    clean = stem_patch()
    expected, detail = glyphs.extract(clean)
    assert detail["valid"]
    # Thin card edges and pips in another vertical band are not missing rank
    # pieces. Keeping these separate prevents rejecting otherwise whole ranks.
    clean[25:100, :3] = 20
    cv2.ellipse(clean, (4, 151), (20, 16), 0, 0, 360, (20, 20, 20), 8)
    found, detail = glyphs.extract(clean)
    assert detail["valid"]
    np.testing.assert_array_equal(found, expected)


def test_connected_card_outline_is_measured_in_rank_band_not_whole_box():
    patch = np.full((189, 204, 3), 238, np.uint8)
    patch[:, 45:165] = stem_patch()
    expected, detail = glyphs.extract(patch)
    assert detail["valid"]
    # One connected frame has a bbox containing the whole rank, although
    # none of its ink is near the rank. Its bbox must not veto a valid crop.
    cv2.rectangle(patch, (0, 0), (203, 188), (20, 20, 20), 14)
    found, detail = glyphs.extract(patch)
    assert detail["valid"]
    np.testing.assert_array_equal(found, expected)


def test_bottom_connected_pip_below_rank_is_not_a_missing_rank_piece():
    patch = stem_patch()
    expected, detail = glyphs.extract(patch)
    assert detail["valid"]
    # A suit can start a few pixels below the tail and continue off the
    # patch. Its ink is entirely below the rank and does not truncate it.
    cv2.rectangle(patch, (15, 119), (49, 188), (20, 20, 20), -1)
    found, detail = glyphs.extract(patch)
    assert detail["valid"]
    np.testing.assert_array_equal(found, expected)


def test_index_merged_with_suit_cannot_be_cut_into_a_different_glyph():
    patch = stem_patch()
    assert glyphs.extract(patch)[1]["valid"]
    # Blur can join a suit to the bottom of the index. A fixed-height band
    # must not manufacture a complete glyph by cutting that component short.
    cv2.line(patch, (45, 100), (45, 159), (20, 20, 20), 8)
    found, detail = glyphs.extract(patch)
    assert found is None and not detail["valid"]


def test_edge_cut_second_digit_invalidates_first_across_character_gap():
    patch = stem_patch()
    assert glyphs.extract(patch)[1]["valid"]
    # A clipped zero can sit farther from the first digit than disconnected
    # strokes do. Aligned cap heights show both pieces belong to the index.
    cv2.ellipse(patch, (130, 68), (61, 39), 0, 0, 360, (20, 20, 20), 8)
    found, detail = glyphs.extract(patch)
    assert found is None and not detail["valid"]


def test_wider_digit_gap_does_not_capture_a_nearby_tall_card_border():
    patch = np.full((189, 140, 3), 238, np.uint8)
    patch[:, 20:] = stem_patch()
    expected, detail = glyphs.extract(patch)
    assert detail["valid"]
    patch[:, :16] = 20
    found, detail = glyphs.extract(patch)
    assert detail["valid"]
    np.testing.assert_array_equal(found, expected)


def _source_corner():
    source = np.full((240, 230, 3), 238, np.uint8)
    patch = np.full((189, 171, 3), 238, np.uint8)
    patch[:, :120] = stem_patch()
    source[15:204, 15:186] = patch
    return source, np.diag([3.0, 3.0, 1.0])


@pytest.mark.parametrize("side", ["left", "top", "right", "bottom"])
def test_source_must_contain_whole_corner_even_if_surviving_glyph_looks_complete(side):
    source, H = _source_corner()
    found, detail = glyphs.extract_at(source, H, (10, 10))
    assert found is not None and detail["valid"]
    if side == "left":
        source = source[:, 20:]
        H[0, 2] -= 20
    elif side == "top":
        source = source[20:]
        H[1, 2] -= 20
    elif side == "right":
        source = source[:, :180]
    else:
        source = source[:200]
    # Border replication can still leave an apparently complete component.
    assert glyphs.extract(glyphs.corner_patch(source, H, (10, 10)))[1]["valid"]
    found, detail = glyphs.extract_at(source, H, (10, 10))
    assert found is None and detail == {"valid": False, "reason": "corner_outside_image"}


def test_source_boundary_guard_applies_to_reads_and_private_training(monkeypatch):
    source, H = _source_corner()
    x, y = scene.RECTS[19][:2]
    H[0, 2], H[1, 2] = 30 - 3 * x, 30 - 3 * y
    registration = Registration(H, 1.0, "generated", present={19})
    monkeypatch.setattr(reader, "register", lambda *args, **kwargs: registration)
    board = ["?"] * 28
    board[18] = "J"
    assert len(reader.labelled_glyphs(Image.fromarray(source), board, "")) == 1
    assert reader.read_photo(Image.fromarray(source)).draft["cards"]["tableau-19"]["crop"]["valid"]
    cropped = Image.fromarray(source[:, 20:])
    registration.H[0, 2] -= 20
    assert reader.labelled_glyphs(cropped, board, "") == []
    card = reader.read_photo(cropped).draft["cards"]["tableau-19"]
    assert card["state"] == "face_up" and card["rank"] is None
    assert card["crop"] == {"valid": False, "reason": "corner_outside_image"}
