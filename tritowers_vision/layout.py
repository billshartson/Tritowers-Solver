"""Calibrated slot layout for the one skin seen so far (1024x768 rectified frame).

Calibrated by eye on five owner-supplied crops of a single visible skin. It is NOT
validated across machines, skins or camera angles.
"""
CARD_W = 98
# (row, centres of card x, visible band top, visible band bottom)
_ROWS = (
    ((211, 515, 817), 145, 225),
    ((161, 261, 461, 561, 761, 861), 225, 305),
    (tuple(111 + 100 * i for i in range(9)), 305, 385),
    (tuple(61 + 100 * i for i in range(10)), 385, 535),
)
def tableau_boxes():
    """28 boxes keyed tableau-01..tableau-28 (visible band of each card)."""
    boxes, n = {}, 1
    for centres, top, bottom in _ROWS:
        for cx in centres:
            boxes[f"tableau-{n:02d}"] = (cx - CARD_W // 2, top, cx + CARD_W // 2, bottom); n += 1
    return boxes
WASTE_BOX = (600, 585, 720, 765)
STOCK_BOX = (402, 572, 520, 750)
STOCK_COUNTER_BOX = (432, 640, 492, 690)
# Rank/suit index glyph in the top-left of a face-up card, as an offset box inside the slot.
CORNER = (2, 2, 40, 62)
# Static scene, same skin and same by-eye calibration as above (used to align sparse boards, which have few cards):
# the parchment map fills the screen width between the HUD bar and a dark band; its lower edge is wavy.
PARCHMENT_BAND = (0, 118, 1024, 618)
# Regions whose content changes between frames or is not parchment: excluded from alignment scoring.
VARIABLE_BOXES = (
    (0, 0, 1024, 116),          # HUD bar (its light frame encloses the score panels, which then look like cards)
    (0, 612, 1024, 658),        # wavy lower edge of the parchment
    (390, 560, 532, 768),       # stock pile and its counter (present or not)
    (800, 575, 940, 768),       # timer bottle
    (0, 670, 270, 768),         # longest-run panel
    (860, 110, 1024, 165),      # EXIT button
)
