# Rank-template curation prototype

Source-only portability slice for TT issue #46. No photos, extracted glyphs, templates, reviewed sample metadata, tokens or generated review pages belong in this directory or in GitHub.

- `tritowers_vision/curation.py`: hash-bound review validation and approved training bank selection.
- `tritowers_vision/curation_review.py`: every query remains `needs_visual_review`; template approval is not query acceptance. Its `diagnostics` function reports manually reviewed localisation categories separately from rank proposals on all, clean and visually bad crops. Correct proposals from bad crops have their own count; omitted queries are rejected.
- `review-template.html`: self-contained review UI source with no sample data.
- `build_private_review.py`: combine an owner-private payload with embedded PNGs into a LOCAL ONLY reviewer.
- `tests/test_curation.py`: synthetic arrays and synthetic photo identifiers only.

Run `python3 -m pytest -q tests/test_curation.py` with NumPy installed. Production selection loads approved samples from every labelled photo. Only explicit offline LOGO mode excludes a query photo. No automatic score gate is implemented.

The UI can edit, export and import reviews. Imports reject stale crop hashes, changed labels, duplicate/missing samples and inconsistent reasons/decisions before applying changes. Generated output contains private photo crops: never commit, upload or host it. Exported manifests have no images but still contain private sample metadata: keep those private too.

The synthetic regression suite covers stale provenance, all reject reasons, production inclusion, whole-photo holdout exclusion, and lucky correct proposals from wrong-neighbour crops. A leave-one-photo-out split is an offline diagnostic; tuning on the same photos still prevents an independent-validation claim.

The prior 106 to 126/208 result was rank-only, manually curated, tuned on the same four photos, prototype signal only. It is not independent held-out validation or production performance. A score/margin-only gate was unsafe.

Not yet integrated into the repository reader or deploy pipeline. The private builder that supplies crop payloads remains outside this source-only slice.
