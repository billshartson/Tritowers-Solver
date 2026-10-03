# Private pilot dataset contract
Pilot: 30-50 permission-cleared photos. Next: 200-400 stills from 20-30 sessions, ideally >=3 machines and >=2 venues. Hold out >=50 photos from unseen machine/session; split 70/15/15 by whole session with venue/machine/augmentation siblings isolated. Never infer hidden cards. Double-label 10-20%. Target gates (not current results): >=95% screen detection, >=98% occupancy, >=90% visible-card identity, >=80% whole-frame exact extraction; abstention reported separately.

## Prototype labels (current five owner photos)
- Per image: image_sha256, 28 tableau slot states (covered/face_up/empty/unknown), face-up rank (suit not yet labelled), waste rank, HUD stock number as displayed, ui_state. Hidden cards are never labelled.
- Keep HUD stock and engine stock as separate fields; HUD-minus-one is an unverified hypothesis.
- Glyph templates built from these photos stay private (not committed). Evaluate leave-one-image-out only, never on training images; report abstentions separately from errors.
- 33 labelled face-up cards cover all 13 ranks but most only once or twice; more frames needed before any accuracy claim. Current gate (score>=0.6, margin>=0.2) was tuned on the same 33 samples, so treat it as optimistic.

## Labels for the reader tools (v3)
`tools/build_templates.py` and `tools/vision_eval.py --labels` take a `labels.json` next to the images, in the board
notation the solver uses: `[{"image": "IMG_0001.jpg", "board": "28 tokens", "waste": "K"}]`, where each token is a rank
(face up), `?` (covered) or `--` (empty). Keep it with the photos, outside the repository (or under an ignored folder).
- `python tools/vision_eval.py --labels L --captures 4` scores the reader slot by slot (correct / abstain / flagged /
  silent error) on each image and on simulated loose crops and phone photos of it; photo templates are built
  leave-one-image-out. `--synthetic` does the same on generated screens with fonts outside the bundled bank.
- `python tools/build_templates.py L private/templates.json` builds the `TT_TEMPLATES` file from every labelled image.
