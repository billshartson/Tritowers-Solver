# TriTowers photo reader (v3)
Not a trained model. A calibrated, rule-aware reader for one skin (the Cashpot Tri Towers screen):

1. **Layout alignment** (`tritowers_vision/register.py`): a homography from the 1024x768 layout frame to the photo,
   found by ECC against a rendering of the expected scene (card silhouettes, parchment band, dark lower band), started
   from the whole frame, the bright screen region and a coarse silhouette search. No exact crop or screen border needed.
   A fit below `MIN_QUALITY` is reported as untrusted and every card is flagged for review.
2. **Presence** (`tritowers_vision/scene.py`): which of the 28 cards are still on the table, chosen among the sets the
   game rules allow (a present card's covered cards are present; a card is face up exactly when exposed).
3. **Ranks** (`tritowers_vision/glyphs.py`): each exposed index is warped from the original pixels, ink is measured
   against the card's own face colour, and the glyph is matched against private same-skin photo templates
   (`TT_TEMPLATES`) and then a bundled bank rendered from five open fonts (`data/font_glyphs.npz`, no font files).
   Enclosed-hole counts separate 3/8 and 5/6. Gates abstain rather than guess; the font tier is switched off for an
   image whose glyphs fit the bundled fonts poorly, and `TT_FONT_TIER=0` turns it off entirely.
4. **Checks**: at most four of a rank; cards whose presence is uncertain are flagged.

Suits and the stock counter are not read. Hidden cards are never inferred. No gameplay screenshots, photos or
photo-derived templates are distributed. Measured on the five private pilot screenshots and simulated re-shoots of them
(crops and phone photos, `tools/vision_eval.py --captures`); that is one skin and 33 face-up cards, so it is a
prototype signal, not a real-cabinet accuracy claim.
