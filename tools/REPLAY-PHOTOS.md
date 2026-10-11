# Replay the exact input through Python and the browser

Use `tools/replay_photos.py` when a supplied image gives different results from a
previous review. This diagnostic does not train or correct the reader. It creates
a fresh static build from the current checkout, then tests both the original
bytes and the app's actual `TTPhoto.normalize` output (EXIF orientation, longest
side at most 1600, browser canvas JPEG quality **0.94**). Pillow's JPEG quality
settings are not a substitute for this path. The browser leg uses Chromium and
records its version; Safari's JPEG encoder and physical-phone timings can differ.

Install the normal app dependencies plus Playwright and Chromium. Reuse the
`pyodide` directory from a previous `tools/prepare_static.py --download-runtime`
build, or use `--download-runtime` below to fetch the pinned public runtime:

```sh
.venv/bin/python tools/replay_photos.py \
  --runtime /tmp/tritowers-static-final/pyodide \
  --output local/exact-replay.json \
  /absolute/path/to/photo-one.jpg /absolute/path/to/photo-two.jpg
```

A downloaded build's adjacent `web/vendor` HEIC codec is reused when available.
Use `--download-runtime` for a fresh runtime and self-hosted HEIC codec if no cache
exists. `--chromium /path/to/chrome` selects an installed browser instead of
Playwright's Chromium. Only the public static build is served, on localhost;
photos and labels are not placed in its document root. Recognition receives
bytes through the browser bridge, with other network origins blocked.

To enforce the exact files from a review, supply a private manifest instead of
positional paths. Relative image paths resolve beside the manifest. **Every hash
is checked before any image is decoded or recognized.**

```json
{"photos": [
  {"image": "photo-one.jpg", "sha256": "<the complete expected SHA-256>"},
  {"image": "photo-two.jpg", "sha256": "<the complete expected SHA-256>"}
]}
```

```sh
.venv/bin/python tools/replay_photos.py \
  --manifest local/replay-manifest.json \
  --runtime /tmp/tritowers-static-final/pyodide \
  --labels local/labels.json --output local/exact-replay.json
```

Labels are optional and are used **only to score the responses**. They may be a
list or a `{"photos": [...]}` object. Each entry needs `image`, `board` (28 tokens
as a list or space-separated string), and `waste`. Full-deal labels also supply
`stock` in draw order (23 ranks, optionally followed by `*`) or
`stock_with_joker`. The image path must identify the same file as the input path.
Keep the actual photographs, manifests and labels in an ignored local directory.

The JSON report contains original and normalized byte hashes, dimensions,
normalization/startup/read timings, native library versions, browser version,
runtime lockfile versions, and hashes of every public build asset and packaged
source. It reports layout/trust, named/unknown-or-covered/empty counts, aggregate
label accuracy when supplied, and native/worker token parity without exposing
rank values, image contents or input filenames. The API represents both covered
and unread ranks as `?`; these cannot be separated by this diagnostic.

Each case uses a new browser context. Each photo call awaits its own bridge
response, with a two-minute deadline for normalization and each photo call, rather than waiting for a reusable “Read in…” message. Original and
normalized worker calls share that case's warmed worker; native calls share one
Python process. Startup and normalization are measured separately. Browser
original-HEIC recognition can fail because Pyodide lacks the native HEIC plugin;
the normalized-HEIC route is the app's supported path and is reported separately.

Exit status 2 means input/configuration validation failed. Status 1 means a read
failed, a network API request escaped the local bridge, or packaged Python source
changed during the run. A rank mismatch remains visible in the JSON and does not
by itself change the exit code. Successful synthetic or alternative-file runs do
not resolve a report about different exact bytes: reproduce the supplied hashes
before claiming that case is fixed.
