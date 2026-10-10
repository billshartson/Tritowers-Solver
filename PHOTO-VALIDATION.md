# Automatic photo intake and app fixes

A machine-screen photo now produces a 28-slot draft and waste rank in the existing app. A scene acceptance gate checks screen alignment, card silhouettes, face/back evidence and unexplained visible cards before retaining named ranks. Stock/waste anchors are hypotheses, not automatic approval. Sparse boards and the missing-stock fallback are checked against the observed scene. Crop validity is recorded separately from matcher confidence.

The photo overlay and editable board appear together. Uncertain cards are highlighted; one **Confirm board & start** action enters the existing play-along adapter. Covered cards remain `?`, missing cards become `--`, and unknown stock order remains unknown. The stock counter and joker setting remain explicit user inputs. Selecting a new photo or editing the board invalidates older results.

The static build uses public font glyphs only. It warms the Python worker, preloads packages, batches font comparisons and never probes the retired origin. JPEG/PNG/WebP/HEIC intake normalizes orientation and the working size to a 1600px long edge. Browsers without native HEIC decoding use a pinned local worker codec; the static build self-hosts that codec. No photos, crops, private templates or review records are included in either runtime package.

## Measured scope

These are small development checks, not a general recognition accuracy claim. All available machine photos, including the staging prototype's images, were treated as tuning/development data. Reserving individual photos from that same session did not establish independent field validation. The final reader names 71 of 77 visible ranks correctly across the nine tableau photos, abstains on six, and names none incorrectly. This includes 41/44 on the four HEIC photos and 30/33 on the five JPEGs.

- Nine local tableau images: five JPEGs including mid-game and empty-stock states, plus four actual iPhone HEICs. All 28 slot states match the local labels on all nine. No wrong named rank was observed. Per-image results stay in ignored `local/`.
- Four local full-draw-screen HEICs were rejected as unsupported tableau geometry.
- A separate 18-scene generated evaluation (three skins; screenshot, crop and perspective capture; fixed evaluation seed) produced 69.8% correct visible names and 30.2% abstentions, with no wrong named ranks or silent errors. This is synthetic validation, not an independent machine session.
- Public regressions cover single-card and empty scenes, absent stock, a sparse board with an animation banner, rotation/scale, lighting/crop extraction errors, negatives, font-score equivalence and the missed-last-card veto.
- All eight EXIF orientations, 48 MP JPEG normalization, invalid/unsupported input and actual local JPEG/HEIC decoding were exercised. Browser tests cover repeated selections, failed decode, bitmap fallback, stale responses and correction/confirmation.

Desktop Chromium, 390px viewport, CDP 4× CPU-throttling setting, with runtime files served locally: an actual HEIC took 5.59 seconds on the first photo read and 4.72 seconds warm, including software HEIC decoding. A normalized phone JPEG took 1.73 seconds. A separate unthrottled run loaded the local runtime and setup UI in approximately 1.4 seconds. These are diagnostics, not an actual iPhone benchmark, and exclude internet download latency. The final named board—not just geometry—was present in these reads. No `/api/*` network calls occurred.

## Issue coverage

| Issue | Change and validation |
| --- | --- |
| #51 | Integrated automatic no-bank photo draft, bulk confirmation, bounded phone intake, scene/crop acceptance, absent-stock/sparse guards, worker speed/race fixes, real Pyodide CI. Actual iPhone timing and independent field validation remain outstanding. |
| #46 | Existing explicit provenance and approved-bank/query-photo separation retained; new diagnostics separately report crop quality, wrong named ranks, abstentions and lucky matches on contaminated crops. The review lab remains a research tool; proposals are never automatic acceptances. Independent field validation remains outstanding. |
| #22 | Visible starting progress, preserved board, safe retry IDs, cleared retry banners, and no tunnel dependency in the static app. |
| #25, #34 | Invalid reveal/draw input re-prompts without state loss; undo returns to a prior input prompt across automatic plays/draws. |
| #26–#28 | Correct known/unknown-stock cache keys, one bounded background worker, CPU/upload/session admission limits, in-flight reservations and retained mutation IDs. Polls cannot evict applied-action IDs; duplicate actions return current state. |
| #29 | Optional Docker Space package serves the mobile app, API and `/gradio` with explicit dependencies. No Space or origin was started or deployed. |
| #30 | Discovery-based Python/browser CI, explicit fonts/dependencies, all runtime imports, standalone package checks and actual Pyodide browser tests. |
| #31–#32 | Verified exact CLI routes for known deals, honest unsolvable/unknown labels, recovery and stock corrections, physical-state checks, normalized exact search and equal sampling rounds. Seeded work and wall-clock budgets are separate modes. |
| #33 | Rank-only paste validation and escaped rendering, actionable image/Gradio/JSON errors, complete-deal validation for known partial positions, consistent simulation caps, Gradio foresight/known-deal flow, and retry-safe new/solve requests. |

## Automated checks

Final local discovery: 398 non-browser tests passed, plus seven unittest subtests. Two legacy font-specific tests explicitly skipped on macOS; CI installs the fonts and requires them. The private iPhone intake test was enabled locally. Browser validation includes the existing mobile/desktop flow, a 40-second outage, photo races/corrections and actual Pyodide/HEIC decoding.

## Reproduce

```sh
python -m pytest -q -m 'not browser'
python tools/prepare_static.py /tmp/tritowers-site --download-runtime
TT_STATIC_SITE=/tmp/tritowers-site python -m pytest -q -m browser
python tools/vision_eval.py --synthetic --skins 3 --per-mode 2 --readers v3 --regimes none
TT_PRIVATE_PHOTOS=local python -m pytest -q tests/test_image_intake.py
python tools/vision_eval.py --labels local/labels.json --readers v3 --regimes none
```

`vision_eval.py` reports wrong named ranks, rank abstentions, false-present slots, false-empty slots and unresolved geometry separately. Its optional leave-one-photo-out private-template diagnostic is not an independent validation claim. Local labels, performance details and overlays remain outside the public repository.

Before closing the field-validation portions of #46/#51, capture independently labeled sessions under different lighting/perspective and measure cold/warm named-board confirmation on a physical iPhone, including actual Safari HEIC intake and first-visit network loading. No new paid hosting or origin restart is required for this PR.
