# Automatic photo intake and app fixes

A machine-screen photo now produces a 28-slot draft and waste rank in the existing app. A scene acceptance gate checks screen alignment, card silhouettes, face/back evidence and unexplained visible cards before retaining named ranks. Stock/waste anchors are hypotheses, not automatic approval. Sparse boards and the missing-stock fallback are checked against the observed scene. Crop validity is recorded separately from matcher confidence.

The same upload also accepts the full-deal grid, using a separate automatic row detector and public-font reader.
The first two 14-card rows map to board positions 1–28. The bottom row supplies the rightmost waste, the remaining
normal cards in right-to-left draw order, and the final joker. The app switches to known-deal mode with editable,
numbered stock entries and a **Confirm deal & solve** action. Unknown stock ranks remain `?` and block exact solving.
Stock direction is inferred from the documented layout and must be checked by the user. Gradio and the static
worker use the same intake and mapping; neither requires private templates or manual row guides.

The photo overlay and editable board appear together. Uncertain cards are highlighted; one **Confirm board & start** action enters the existing play-along adapter. Covered cards remain `?`, missing cards become `--`, and unknown stock order remains unknown. The stock counter and joker setting remain explicit user inputs. Selecting a new photo or editing the board invalidates older results.

The static build uses public font glyphs only. It warms the Python worker, preloads packages, batches font comparisons and never probes the retired origin. JPEG/PNG/WebP/HEIC intake normalizes orientation and the working size to a 1600px long edge. Browsers without native HEIC decoding use a pinned local worker codec; the static build self-hosts that codec. No photos, crops, private templates or review records are included in either runtime package.

## Recognition changes in this update

The development-set misses were inspected crop by crop. Resolution was not the cause: re-reading the originals at
1200, 2000 and 2400px changed little, so the 1600px phone working size is unchanged. The causes and fixes were:

- **Crop ownership.** Halfway-between-centres windows cut the "1" of deck tens and admitted card borders and court
  art. Each card's strip now runs from its own left border to the next card's border; borders are found from the
  median horizontal gradient down the card, and the card tops from the vertical gradient above the ranks. Drawn
  border columns are removed before grouping ink.
- **Cut ranks.** A deck rank that reaches the covering card is read as clipped: every template, font or same-image,
  is cut at the same visible width. Separate tall strokes may only be named 10, and only with both strokes visible;
  a tall stroke left beside a rank (the thin cut arc of a zero) makes the crop ambiguous rather than a J.
- **Faint strokes.** This skin's hairlines (an A's left leg, a four's diagonal) blur below the ink threshold.
  Faint ink connected to the rank within its rows is kept (hysteresis). The previous hole-count veto rejected
  legible 3s, As and 2s whose small counters opened or closed at 32px; it is replaced by a veto when a lower ink
  threshold confidently names a different rank. Hole counts are taken at the extracted resolution.
- **Perspective.** Pitch-to-height ratios along a row restore each glyph's aspect before matching.
- **Typeface.** No open font resembles this skin's curly 3 and 2 or its swash Q (a search of 1,200 TeX Live fonts
  added at most a few reads), so the shipped bank is unchanged. Instead, copies of a rank on one photo are used:
  complete and clipped crops are compared over their common part; a group of identical unread crops is named when
  every close font rival has been read on this photo and looks unlike them; a lone crop likewise when every close
  rival is ruled out. Nothing is filled from deck counts; groups claiming one rank cancel out.
- **Geometry.** A bezel mark beyond two rows' ends no longer moves the screen edges, and compression ringing that
  joins two deck ranks is split again; a recompressed 1600px JPEG of one grid was previously not detected.
- **Tableau registration cost.** Refinement stops after six candidates or at an initial quality below .40 (accepted
  layouts started at .52 or more in all 126 local and generated checks). Rejected photos now take 1.2-1.3 s
  natively instead of 2.5-2.8 s; accepted registrations and all metrics are unchanged.

The follow-up adds crop-integrity checks and a bounded aspect retry:

- Significant discarded edge ink beside a rank makes the crop incomplete. A clipped 9 can no longer lose its loop
  and become a confidently named J. Aligned digit tops and bottoms also catch a clipped zero across a wider gap
  from the first digit of 10. The check measures actual ink within the rank band, so connected card outlines and a
  suit below the rank do not invalidate a complete index.
- A connected component crossing the bottom of the rank band is not a complete index. This catches a Q joined to
  its suit symbol whose truncated shape otherwise resembles 9. The expanded generated-scene audit found this while
  testing the aspect retry; the regression is covered separately from match confidence.
- The entire corner ownership window must project inside the source photograph. Border replication cannot supply
  evidence for a missing half of a rank. This guard applies to reading and private training extraction; eight
  progressive edge-crop probes now abstain while preserving the visible card's face-up state.
- For a valid complete index that remains unread, the reader may retry horizontal scale at ±2% and ±4%. The
  original winner must already have the required margin, remain the winner in all four views, and pass both font
  gates in two adjacent views. The reported score and margin are the weaker supporting values. The image's font
  must fit, and private-template-only mode remains unchanged. This is a bounded new acceptance path, not evidence
  that an arbitrary low-scoring crop is readable. Invalid and clipped indexes cannot enter it.
- Full-grid consensus and exclusion now respect `TT_FONT_TIER=0`. Disabling fonts leaves normal ranks unread;
  the final joker still follows the explicit machine rule.

## Measured scope

These are development-set results on the same captures used for tuning, not independent field accuracy. Counts are
before human correction. The joker's identity comes from the machine rule and is excluded.

| Set | Correct | Unknown | Wrong |
| --- | --- | --- | --- |
| Four full grids, original HEIC (Python decode) | 208/208 | 0 | 0 |
| Same grids, actual browser conversion (Python) | 208/208 | 0 | 0 |
| Same grids, real Pyodide build with browser HEIC decode | 208/208 | 0 | 0 |
| 20 original/derived grid cases (JPEG 1600/1200, 2° rotation, perspective) | 1031/1040 | 9 | 0 |
| Nine tableau photos, originals | 77/77 | 0 | 0 |
| Same, actual browser conversion (Python) | 77/77 | 0 | 0 |
| Same, real Pyodide build with browser HEIC decode | 77/77 | 0 | 0 |
| Four added legacy screenshots, originals and actual browser conversion in both engines | 22/22 | 0 | 0 |

- Previous results on the same inputs: grids 166/208 (original) and 170/208 (browser), tableau 71/77.
- All 53 grid slot states, the stock order and the joker tail are exact on all four originals and browser
  conversions (complete exact deals: 4/4 each). All twenty derived cases are detected; the nine unknowns are in two
  variants of one grid. All 28 slot states are correct on every tableau photo in every path.
- Final replay covers 17 local images and 307 visible normal ranks: all are correct before correction, with exact
  native/worker parity on actual browser-normalized bytes. All layouts are trusted. Normalized IMG_7194 retains
  one conservative presence-review flag at position 28 despite its correct rank. The four added screenshots show
  deals already present in the earlier captures; they are not independent held-out photos.
- The previous Pyodide unknown was one photo's lone curly 2, scoring .749 against the .75 floor. Further inspection
  found different native/browser registration transforms, not just JPEG decoding: native OpenCV 5 uses separate
  template/input masks during refinement, while browser OpenCV 4.11 exposes the older input-mask API. The resulting
  rank crops have different aspect ratios. The bounded aspect retry recovers this rank without lowering either
  font gate; it is a new acceptance path, not a claim that the original low score passed unchanged.
- Eight obscured-rank probes left every obscured rank unknown with no wrong names; unmasked ranks read 50-51 of 51.
  As before, masking one grid's first rank makes it fall back to the tableau path.
- Generated grids (public, 20 seeds): 936/1040 ranks named, 104 unknown, zero wrong even before the deck-count
  rule. This sacrifices two reads versus the previous build's 938 to reject incomplete crops. Seed 12 is not
  detected, as before.
- Expanded synthetic tableau audit: 396 scenes, 2229/3285 ranks correct, 1056 unknown, zero wrong names and zero
  false-present/false-empty slots; 336 card states remain unresolved. The 246 diagnostic/tuning scenes score
  1368/2023; 96 scenes using a separate seed not used to choose fixes score 560/807; 54 additional scenes with
  regular, italic and monospace fonts score 301/455. These generated scenes are not independent field photos.
  On the original 96-scene subset, the previous build named 551/796 with one wrong name; this build names 548/796
  with zero wrong. The stricter crop checks intentionally trade some recall for fewer confident mistakes.
- Bill reproduced the 28-unknown regression on **94423b2**, using four exact JPEGs in
  [his latest review](https://github.com/billshartson/Tritowers-Solver/pull/52#issuecomment-6100697691).
  Three of the four remain untrusted in his actual browser run; two remain untrusted natively. No matching bytes
  have been located using the previously supplied hashes. The four added 1024×768 screenshots have different
  dimensions and hashes. Other conversions passing here do not resolve that report.
  Those exact inputs remain unverified; the development-set results must not be presented as a fix for that report.

The final 17-image replay's warm worker calls took 0.956–2.881 s under concurrent validation load, excluding
normalization and startup. These are diagnostic timings, not an isolated before/after benchmark. The preceding
build's isolated Mac measurements were 3.9–4.6 s end to end for grid HEICs, including about 2.7 s of HEIC decoding.
CDP CPU throttling does not slow the Web Workers that decode and recognise, so neither measurement represents
phone performance. The worker builds the font caches while idle.

## App: waste and stock

Play-along and solution replay show a large face-up waste card and the stock pile beneath the tableau, with the
remaining count. The next stock card is shown face up only when known (a known-deal stock, or the machine joker as
the last card); otherwise the pile stays face down. When the next recommended action is a draw, the stock gets an
outline, a glow (static under reduced motion) and a "Draw next" label; tapping it performs the existing draw, or
advances the replay over that draw, once. The area sits in the page flow directly under the board, so it never
covers the board, controls or the rank keypad; at 390px the board, waste, stock and controls fit on one screen.

Views and replay frames carry an explicit `next_action` (`play` with `pos`, `draw`, `reveal` with `positions`,
`done`, or `none` with a reason) and `stock_next`. A null position no longer has to be interpreted, and `can_draw`
remains permission only. Advice carries the same `action`. HTTP and the browser worker share this code.

## Upstream maintenance

The recent merged changes on `benamoore96/Tritowers-Solver/main` were reviewed and adapted: terminal EOF now exits
with status 1, Ctrl-C with status 130, and successful completion with status 0. Unexpected exceptions retain their
tracebacks. Existing heuristic weights now have descriptive names, with their values and behavior unchanged.
The CLI's joker support, time budgets, validated stock and undo behavior remain intact. Source commits and author
credit are recorded in [ALEX-ATTRIBUTION.md](ALEX-ATTRIBUTION.md).

## Issue coverage

| Issue | Change and validation |
| --- | --- |
| #51 | Integrated automatic no-bank tableau and full-deal-grid drafts, editable ordered stock, bulk confirmation, bounded phone intake, scene/crop acceptance, absent-stock/sparse guards, worker speed/race fixes, real Pyodide CI. Actual iPhone timing and independent field validation remain outstanding. |
| #46 | Existing explicit provenance and approved-bank/query-photo separation retained; new diagnostics separately report crop quality, wrong named ranks, abstentions and lucky matches on contaminated crops. The review lab remains a research tool; proposals are never automatic acceptances. Independent field validation remains outstanding. |
| #22 | Visible starting progress, preserved board, safe retry IDs, cleared retry banners, and no tunnel dependency in the static app. |
| #25, #34 | Invalid reveal/draw input re-prompts without state loss; undo returns to a prior input prompt across automatic plays/draws. |
| #26–#28 | Correct known/unknown-stock cache keys, one bounded background worker, CPU/upload/session admission limits, in-flight reservations and retained mutation IDs. Polls cannot evict applied-action IDs; duplicate actions return current state. |
| #29 | Optional Docker Space package serves the mobile app, API and `/gradio` with explicit dependencies. No Space or origin was started or deployed. |
| #30 | Discovery-based Python/browser CI, explicit fonts/dependencies, all runtime imports, standalone package checks and actual Pyodide browser tests. |
| #31–#32 | Verified exact CLI routes for known deals, honest unsolvable/unknown labels, recovery and stock corrections, physical-state checks, normalized exact search and equal sampling rounds. Seeded work and wall-clock budgets are separate modes. |
| #33 | Rank-only paste validation and escaped rendering, actionable image/Gradio/JSON errors, complete-deal validation for known partial positions, consistent simulation caps, Gradio foresight/known-deal flow, and retry-safe new/solve requests. |

## Automated checks

Local validation: 474 non-browser tests passed, plus nine unittest subtests; two legacy-font tests skip on macOS
(CI installs the fonts) and the private iPhone intake test passes when `TT_PRIVATE_PHOTOS=local` is set. All 29
browser tests passed against a fresh static build; one optional private-template fixture skipped. New public
regressions cover border-cut tens, drawn borders, bezel marks and bridged ranks, faded fours and hairline aces,
same-image consensus and exclusion, full-resolution hole counts, a slightly low tableau index, the refinement cap,
the `next_action` contract in HTTP and the worker, and the stock area at 390px in both builds. The follow-up covers
bounded aspect consensus and ambiguous rivals, complete crop ownership and source support, font-disable behavior,
replay manifest hashes and deadlines, and terminal exit statuses. The built Python archive contains only the 22
allowlisted public source files, each matching the tested checkout.

## Reproduce

```sh
python -m pytest -q -m 'not browser'
python tools/prepare_static.py /tmp/tritowers-site --download-runtime
TT_STATIC_SITE=/tmp/tritowers-site python -m pytest -q -m browser
python tools/vision_eval.py --synthetic --skins 3 --per-mode 2 --readers v3 --regimes none
TT_PRIVATE_PHOTOS=local python -m pytest -q tests/test_image_intake.py
TT_STATIC_SITE=/tmp/tritowers-site TT_FULL_DEAL_LABELS=local/full-deal-labels.json python -m pytest -q tests/test_static_browser.py
python tools/vision_eval.py --labels local/tableau-labels.json --readers v3 --regimes none
python tools/vision_eval.py --labels local/tableau-browser-labels.json --readers v3 --regimes none
python tools/evaluate_full_deal.py --labels local/full-deal-labels.json --variants original,jpeg1600,jpeg1200,rotate2,perspective
python tools/evaluate_full_deal.py --labels local/full-deal-browser-labels.json
```

`vision_eval.py` reports wrong named ranks, rank abstentions, false-present slots, false-empty slots and unresolved geometry separately. Its optional leave-one-photo-out private-template diagnostic is not an independent validation claim. Local labels, performance details and overlays remain outside the public repository.

For a report about exact input bytes, use [tools/REPLAY-PHOTOS.md](tools/REPLAY-PHOTOS.md). The replay command checks
manifest hashes before decoding, builds fresh public sources, and compares original bytes with the actual browser
JPEG normalization through both engines. Each worker response is awaited directly, with a deadline; a stale
"Read in…" message cannot complete a later case. Reports contain source/runtime hashes, aggregate counts and
timings, without image contents or rank values. A raw HEIC sent directly to Pyodide can fail because that runtime
has no HEIF plugin; browser normalization is the supported app path and is measured separately.

Before closing the field-validation portions of #46/#51, capture independently labeled sessions under different lighting/perspective and measure cold/warm named-board confirmation on a physical iPhone, including actual Safari HEIC intake and first-visit network loading. No new paid hosting or origin restart is required for this PR.
