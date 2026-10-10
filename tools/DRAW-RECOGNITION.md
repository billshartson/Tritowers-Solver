# Guided draw-screen rank prototype

This document describes the older, manually guided research modules (`draw_*`).
The app's automatic all-cards-grid path is now `tritowers_vision/full_deal.py`,
selected by `tritowers_vision/intake.py`. It uses public fonts, supplies an editable
known-deal draft and does not call this private-template prototype. See
[PHOTO-VALIDATION.md](../PHOTO-VALIDATION.md) for current app behavior and measurements.

Source-only object detector, paired glyph extraction and rank proposal matcher for a full draw screen. Callers supply a BGR uint8 image, row guides, expected row counts and a privately curated paired template bank. No photo, guide, glyph or template data is bundled.

This is separate from the existing 28-tableau photo reader. It does not replace that reader, change the UI or provide accepted solver input. Every match returns rank=null, accepted=false and needs_visual_review=true. Blank, constant and nonfinite query views abstain. Count, spacing and endpoint checks reject inconsistent geometry; passing them never makes a rank safe.

25 synthetic tests cover detection, extraction, geometry and draft boundaries. Private research reached 208/208 rank proposals with other-photo templates from 191 visually complete crops on the same four tuning photos. Normalization, geometry and matcher choices were tuned on that set, so this is not independent performance. Manual row guides remain required. Negative tests rejected all 208 individually masked ranks on that same set; this is not a general safety guarantee.

Nothing is deployed. Private images, crops, manifests and evaluation harnesses must stay outside the repository.

## Owned-foreground experimental path

`draw_consensus.consensus(image, row_guides, expected_counts)` checks three
ink thresholds and requires at least two consistent ordered assignments.
Bounded short overlapping fragments can be joined before subset assignment.
Spacing, endpoint, near-tie and disjoint-ownership guards still reject.

`draw_ownership.paired(image, boxes, expected_counts)` supplies hard foreground
and a one-pixel antialias halo of the same owned components to the existing
review-only matcher. Row height and neighbour boundaries define ownership;
fragment-centre recovery requires intact neighbours on both sides. Neither
rank labels nor matching scores choose the crop. Callers must construct their
private template bank with this same paired normalization.

18 additional synthetic tests cover fragment guards, input validation,
foreground ownership, review boundaries and concurrent threshold reads.
Private tuning probes retain 208/208 proposals after tested area-resize and
known-inverse affine resampling. Known inverses diagnose interpolation loss,
not recovery from an unknown camera angle. These remain the same four tuning
photos, not independent validation. Some partial right edges and stray ink
remain visible, so score-only acceptance is still forbidden.

This path is not wired into the UI or solver and nothing is deployed.

### Card-edge components

Foreground ownership drops thin vertical components only when they continue
below the fitted rank band and have little horizontal overlap with the detected
rank box. This is a geometry guard, not a rank-dependent filter. Detached
horizontal strokes, rooted thin strokes, short vertical strokes and wider
components keep the existing rules. Synthetic tests check these boundaries,
soft/hard consistency, blank crops and unchanged neighbouring slots.

This does not prove a crop is complete or identify every card edge. The matcher
still returns review-only candidates, never accepted ranks. Private same-photo
resampling checks are tuning evidence, not independent recognition accuracy.
