"""Public-font checks for bounded uncertainty in index aspect after registration."""
import cv2
import numpy as np
import pytest

from tritowers_vision import glyphs


def _public(rank):
    return next(g.copy() for r, g in glyphs.font_bank() if r == rank)


def _compressed_two():
    # A publicly rendered index near the recognition boundary after horizontal
    # compression. The retry has only a further +/-4% width to work with.
    return cv2.warpAffine(_public('2'), np.float32([[.70, 0, (glyphs.GW-1)*.15], [0, 1, 0]]),
                          (glyphs.GW, glyphs.GH), flags=cv2.INTER_LINEAR)


def test_bounded_width_consensus_recovers_a_distorted_public_index():
    query = _compressed_two()
    scores = dict(glyphs._ranked(query, glyphs.font_bank()))
    assert glyphs.match(query, font_scores=scores)[0] is None
    result = glyphs.aspect_match(query, scores)
    assert result[0] == '2'
    assert result[1] >= glyphs.FONT_SCORE and result[2] >= glyphs.FONT_MARGIN
    assert result[3] == 'font_aspect_consensus'
    # The reported evidence is weaker than the most favourable trial: one
    # especially convenient distortion must not determine confidence.
    expanded = cv2.warpAffine(query, np.float32([[1.04, 0, -(glyphs.GW-1)*.02], [0, 1, 0]]),
                             (glyphs.GW, glyphs.GH), flags=cv2.INTER_LINEAR)
    assert result[1] < dict(glyphs._ranked(expanded, glyphs.font_bank()))['2']


@pytest.mark.parametrize('first,second,weight', [('2', 'J', .4), ('5', '3', .5), ('6', '9', .4), ('A', '4', .4)])
def test_ambiguous_public_shapes_cannot_gain_a_name_by_stretching(first, second, weight):
    query = weight * _public(first) + (1-weight) * _public(second)
    ranking = glyphs._ranked(query, glyphs.font_bank())
    assert ranking[0][1] - ranking[1][1] < glyphs.FONT_MARGIN
    assert glyphs.aspect_match(query, dict(ranking)) is None


def test_retry_requires_other_evidence_that_the_photos_font_fits():
    query = _compressed_two()
    alone, fit = glyphs.read_ranks({'target': query})
    assert fit < glyphs.FONT_FIT and alone['target'][0] is None
    with_anchors = {'target': query, **{r: _public(r) for r in ('A', '5', '8', 'K')}}
    reads, fit = glyphs.read_ranks(with_anchors)
    assert fit >= glyphs.FONT_FIT
    assert reads['target'][0] == '2' and reads['target'][3] == 'font_aspect_consensus'


def test_retry_respects_disabled_fonts_and_explicit_private_templates(monkeypatch):
    query = _compressed_two()
    found = {'target': query, **{r: _public(r) for r in ('A', '5', '8', 'K')}}
    monkeypatch.setenv('TT_FONT_TIER', '0')
    assert glyphs.read_ranks(found)[0]['target'][0] is None
    monkeypatch.setenv('TT_FONT_TIER', '1')
    assert glyphs.read_ranks(found, [('A', _public('A'))])[0]['target'][0] is None


def test_retry_does_not_cut_off_a_stroke_at_the_normalized_frame_edge():
    query = _compressed_two()
    # A stray connected stroke at the frame's edge cannot be discarded by
    # the widening retry even if the main shape still favours the same rank.
    query[10:25, 0] = 1
    assert glyphs.aspect_match(query, {'2': .74, 'J': .55}) is None


def test_retry_rejects_a_patch_without_visible_ink():
    faded = np.full((glyphs.GH, glyphs.GW), .01, np.float32)
    assert glyphs.aspect_match(faded, {'2': .74, 'J': .55}) is None
