"""Public synthetic full-deal grids: geometry, ordering and safe abstention.

These drawings contain no machine photos, private coordinates or labels. The
font is an installed openly licensed serif; the deck and rendering are seeded.
"""
from pathlib import Path
import os
import random

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import pytest

from tritowers_vision.full_deal import read_full_deal

RANKS = 'A 2 3 4 5 6 7 8 9 10 J Q K'.split()
FACE = (247, 241, 224)
BACKGROUND = (83, 68, 45)
SIZE = (1600, 1000)
ROW_Y = (120, 380, 640)


def _public_font(size):
    candidates = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf',
        str(Path.home() / 'Library/Fonts/DejaVuSerif-Bold.ttf'),
        '/opt/homebrew/share/fonts/DejaVuSerif-Bold.ttf',
        'DejaVuSerif-Bold.ttf',
        '/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf',
        'LiberationSerif-Bold.ttf',
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    if os.environ.get('TT_REQUIRE_TEST_FONTS'):
        pytest.fail('Install fonts-dejavu-core for full-grid regression coverage')
    pytest.skip('Install an openly licensed DejaVu Serif or Liberation Serif font')


def _rank_image(rank, condensed=False):
    font = _public_font(58)
    box = font.getbbox(rank)
    mask = Image.new('L', (box[2] - box[0], box[3] - box[1]))
    ImageDraw.Draw(mask).text((-box[0], -box[1]), rank, font=font, fill=255)
    # A single index column fits the fan's exposed face. Ten uses the same
    # printed size, so a following card may cover part of it as on a real fan.
    return mask.resize((round(mask.width * 44 / mask.height * (.82 if condensed else 1)), 44), Image.Resampling.LANCZOS)


def _positions(row):
    count = 14 if row < 2 else 25
    left, pitch = (100, 96) if row < 2 else (70, 54)
    return [(left + i * pitch, ROW_Y[row]) for i in range(count)]


def make_grid(seed=3):
    """Return a generated PIL screen and board/waste/stock tokens in draw order."""
    rng = random.Random(seed)
    deck = [rank for rank in RANKS for _ in range(4)]
    rng.shuffle(deck)
    truth = {'board': deck[:28], 'waste': deck[28], 'stock': deck[29:] + ['*']}
    rows = [truth['board'][:14], truth['board'][14:], ['*'] + list(reversed(truth['stock'][:-1])) + [truth['waste']]]
    image = Image.new('RGB', SIZE, BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 50, 1570, 940), fill=(158, 132, 87), outline=(32, 30, 26), width=8)
    for row, ranks in enumerate(rows):
        for i, (rank, (x, y)) in enumerate(zip(ranks, _positions(row))):
            draw.rounded_rectangle((x, y, x + 128, y + 210), radius=8,
                                   fill=FACE, outline=(90, 78, 68), width=2)
            if rank == '*':
                # Distinctive joker art, not an ordinary rank-shaped glyph.
                draw.ellipse((x + 7, y + 14, x + 31, y + 38), fill=(120, 60, 130))
                draw.polygon([(x + 7, y + 50), (x + 31, y + 50), (x + 19, y + 30)], fill=(175, 70, 70))
            else:
                mask = _rank_image(rank, condensed=row == 2)
                ink = (155, 25, 32) if i % 2 else (22, 24, 25)
                image.paste(ink, (x + 8, y + 12), mask)
                draw.polygon([(x + 21, y + 75), (x + 30, y + 87), (x + 21, y + 99), (x + 12, y + 87)], fill=ink)
            draw.ellipse((x + 48, y + 114, x + 87, y + 152), fill=(192, 160, 102))
    return image, truth


def _expected(truth):
    return {**{f'tableau-{i:02d}': rank for i, rank in enumerate(truth['board'], 1)},
            'waste': truth['waste'],
            **{f'stock-{i:02d}': rank for i, rank in enumerate(truth['stock'], 1)}}


def _assert_draft(result, truth, minimum_read=40):
    assert result is not None, 'Generated three-row grid must be located'
    draft = result.draft
    assert draft['photo_kind'] == 'full_deal'
    assert draft['registration']['trusted']
    expected = _expected(truth)
    assert set(draft['cards']) == set(expected)
    known = {slot: card['rank'] for slot, card in draft['cards'].items() if card['rank'] is not None}
    assert len(known) >= minimum_read
    assert not {slot: (rank, expected[slot]) for slot, rank in known.items() if rank != expected[slot]}
    assert len(draft['stock']) == 24 and draft['stock'][-1] == '*'
    assert draft['stock'] == [draft['cards'][f'stock-{i:02d}']['rank'] or '?' for i in range(1, 25)]
    assert set(draft['needs_human_review']) == set(expected) - set(known)
    return draft


@pytest.mark.parametrize('seed', [3, 17])
def test_generated_full_grid_maps_tableau_waste_and_reverse_stock(seed):
    image, truth = make_grid(seed)
    _assert_draft(read_full_deal(image), truth)


@pytest.mark.parametrize('transform', ['scale', 'rotate', 'perspective'])
def test_full_grid_survives_moderate_photo_geometry(transform):
    image, truth = make_grid()
    if transform == 'scale':
        image = image.resize((1200, 750), Image.Resampling.LANCZOS)
    elif transform == 'rotate':
        image = image.rotate(4, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=BACKGROUND)
    else:
        src = np.float32([[0, 0], [1599, 0], [1599, 999], [0, 999]])
        dst = np.float32([[60, 30], [1550, 0], [1590, 975], [10, 940]])
        H = cv2.getPerspectiveTransform(src, dst)
        image = Image.fromarray(cv2.warpPerspective(np.asarray(image), H, SIZE, borderValue=BACKGROUND))
    _assert_draft(read_full_deal(image), truth, minimum_read=35)


def test_masked_internal_rank_retains_slot_and_does_not_shift_neighbours():
    image, truth = make_grid()
    x, y = _positions(0)[6]
    ImageDraw.Draw(image).rectangle((x + 3, y + 5, x + 87, y + 65), fill=FACE)
    draft = _assert_draft(read_full_deal(image), truth)
    assert draft['cards']['tableau-07']['rank'] is None
    assert 'tableau-07' in draft['needs_human_review']


@pytest.mark.parametrize('damage', ['missing_first_rank', 'cropped_left_edge'])
def test_missing_row_endpoint_never_shifts_deal(damage):
    image, truth = make_grid()
    if damage == 'missing_first_rank':
        x, y = _positions(0)[0]
        ImageDraw.Draw(image).rectangle((x + 3, y + 5, x + 87, y + 65), fill=FACE)
    else:
        image = image.crop((165, 0, image.width, image.height))
    result = read_full_deal(image)
    if result is not None:
        draft = _assert_draft(result, truth, minimum_read=0)
        assert draft['cards']['tableau-01']['rank'] is None
        assert not draft['complete']


def test_dense_distractor_text_does_not_become_a_full_deal():
    image = Image.new('RGB', SIZE, FACE)
    draw = ImageDraw.Draw(image)
    font = _public_font(48)
    for row in range(11):
        draw.text((30, 20 + row * 85), 'A7 Q3 10K  42 J9  KQ5  8A2  37J  610', font=font, fill=(20, 20, 25))
    assert read_full_deal(image) is None


def test_overlapped_ten_with_open_zero_is_not_read_as_a_king():
    from tritowers_vision.full_deal import _extract
    mask = _rank_image('10', condensed=True)
    left, top = 80, 60
    center = left + mask.width / 2
    row = {'x': np.array([center, center + 100]), 'y': np.array([82, 82]),
           'h': np.array([44, 44]), 'fit': np.array([0, 82]),
           'objects': {0: np.array([left, top, mask.width, 44])}}
    intact = Image.new('RGB', (240, 180), FACE)
    intact.paste((20, 20, 20), (left, top), mask)
    glyph, _, valid = _extract(np.asarray(intact), row, 0, shear=0)
    assert valid and glyph is not None
    # The next overlapping face conceals the zero's closing stroke. Both
    # remaining tall components are visible, but this is not a printed K.
    cut = mask.width - 13
    damaged = intact.copy()
    ImageDraw.Draw(damaged).rectangle((left + cut, top, 239, top + 44), fill=FACE)
    row['objects'][0] = np.array([left, top, cut, 44])
    glyph, _, valid = _extract(np.asarray(damaged), row, 0, shear=0)
    assert glyph is None and not valid


@pytest.mark.parametrize('diagonal_contrast', [.30, .35])
def test_faded_four_diagonal_is_reviewed_instead_of_named_as_another_rank(diagonal_contrast):
    from tritowers_vision import glyphs
    from tritowers_vision.full_deal import _extract
    mask = _rank_image('4')
    width, height = mask.size
    left, top = 80, 60
    center = left + width / 2
    row = {'x': np.array([center, center + 100]), 'y': np.array([82, 82]),
           'h': np.array([44, 44]), 'fit': np.array([0, 82]),
           'objects': {0: np.array([left, top, width, height])}}
    intact = Image.new('RGB', (240, 180), FACE)
    intact.paste((155, 25, 32), (left, top), mask)
    glyph, _, valid = _extract(np.asarray(intact), row, 0, shear=0)
    assert valid and glyphs.match(glyph)[0] == '4'
    # Glare fades the diagonal left of the four's vertical stem. It is still
    # visible on the card, but treating it as paper leaves a different shape.
    coverage = np.asarray(mask, dtype=float) / 255
    coverage[:round(height * .68), :round(width * .51)] *= diagonal_contrast
    face, ink = np.array(FACE), np.array((155, 25, 32))
    patch = (face + (ink - face) * coverage[..., None]).astype(np.uint8)
    damaged = Image.new('RGB', (240, 180), FACE)
    damaged.paste(Image.fromarray(patch), (left, top))
    glyph, _, valid = _extract(np.asarray(damaged), row, 0, shear=0)
    assert glyph is None and not valid
