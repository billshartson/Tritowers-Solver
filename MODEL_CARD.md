# TriTowers automatic photo reader

This is a calibrated, rule-aware reader for the Cashpot Tri Towers skin, not a newly trained neural model.

- **Alignment:** screen structure, card edges and stock/waste anchors propose transforms. Scene refinement follows observed occupancy. Acceptance independently checks silhouette overlap, face/back patterns, card interiors and unexplained bright card regions. A missed last card can veto an otherwise high global score. Unsupported geometry leaves all slots unknown and flagged.
- **Presence:** the 28-slot tableau obeys the solver's blocking rules. Covered ranks are never inferred. Sparse and absent-stock scenes use the same evidence checks; a starting layout is not forced onto the photo.
- **Ranks:** each visible index is sampled from its own card, with crop integrity checked before matching. Connected edge fragments, missing rank bands and suit-only crops are rejected. Public open-font glyphs, shape/hole checks and in-image agreement supply the runtime reader. Score/margin thresholds were not lowered to make the new geometry pass.
- **Full-deal grids:** a separate geometric reader locates the two 14-card rows and the bottom deck row. Visible ranks map into the 28 tableau positions, waste and 24 stock entries including the joker. Stock order uses the documented right-to-left interpretation, which remains inferred from machine layout rather than observed draws. The user reviews that order and every uncertain rank before exact solving; missing ranks are never filled from deck counts.
- **Output:** ranks, unknowns and empty slots; a photo overlay; review flags; separate registration/crop diagnostics. Suits and the HUD stock counter are not read. A tableau photo keeps stock order unknown; a full-deal grid supplies the visible stock for review. The user confirms/corrects the draft before play-along or exact solving.

The static runtime ships only `data/font_glyphs.npz`, rendered from the existing open-font sources. It has no private-template loader. The optional HTTP `TT_TEMPLATES` setting remains for local research; public packaging contains no private photos, crops, labels or photo-derived templates.

Evaluation uses the available owner-private development captures and generated scenes. It does not establish accuracy on another machine, theme, venue or session. Some readable-looking ranks still abstain. See [PHOTO-VALIDATION.md](PHOTO-VALIDATION.md) for measured scope, reproducible checks and outstanding actual-device/independent-field validation.
