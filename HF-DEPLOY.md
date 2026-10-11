# Private Hugging Face Space deployment

The deployment owner handles account access, Space creation, visibility, upload
and any paid hardware decision. This package does none of those things.

## Stage the runtime

From a reviewed checkout, choose a new destination outside the source tree:

```sh
python3 tools/prepare_space.py /tmp/tritowers-space-runtime
```

The staging script refuses existing destinations. It copies this runtime manifest:

- `Dockerfile` and `app.py`: shared FastAPI/Gradio entrypoint on port 7860.
- `web_app.py`, `web_shared.py`, `web/`: mobile UI, HTTP API and shared response logic.
- `solver_ui.py`, `solver.py`, `tritowers_cli.py`: UI adapter and solver imports.
- `tritowers_vision/`: image extraction and recognition modules, without bytecode,
  including the bundled open-font glyph bank `data/font_glyphs.npz`.
- `requirements.txt`: pinned runtime dependencies.
- `MODEL_CARD.md`: recognition limitations.
- `README-SPACE.md` renamed to root `README.md`: Hugging Face SDK metadata.

It does not copy the source Git history, tests, annotation app, local environment,
private templates, photos or corpus. No `packages.txt` is needed for the pinned
headless OpenCV wheel. `annotation_app.py` is a separate tool, not this Space.

## Validate before upload

Use Python 3.12 in a clean environment. Docker and requirements pin the runtime. From the staged runtime:

```sh
python3 -m venv /tmp/tritowers-space-venv
/tmp/tritowers-space-venv/bin/pip install -r requirements.txt
/tmp/tritowers-space-venv/bin/pip check
/tmp/tritowers-space-venv/bin/python -c 'import app; assert app.demo is not None; assert app.app is not None'
/tmp/tritowers-space-venv/bin/python app.py
```

Check `/`, `/health`, `/api/geo` and `/gradio/` locally, then stop it. Import/startup checks are not hosted build
or browser acceptance. Run the source tests separately in the full checkout.

## Owner deployment checklist

1. Create or select a **private Docker Space** and verify visibility in its account
   settings. The README cannot enforce privacy.
2. Upload the staged runtime with `README.md` at the root. Do not upload secrets,
   templates or a photo corpus inadvertently.
3. Check the build log, dependency install and runtime startup. Open the actual
   Space and test start, recommendation, play, reveal, draw and undo on desktop
   and mobile. Record the deployed source revision and Space URL.
4. Confirm recommendation latency on the chosen CPU. A solver time budget is a
   soft cap, not a strict hosted response deadline; the UI wiring owner handles
   the recommendation cap.
5. Decide how ranks may be read from photos. By default the reader uses private
   templates when `TT_TEMPLATES` points at them, and otherwise the bundled
   open-font glyphs (`tritowers_vision/data/font_glyphs.npz`, rendered bitmaps
   only). Set `TT_FONT_TIER=0` to keep rank reading unavailable without approved
   private templates (the previous behaviour). `TT_TEMPLATES` is an optional local
   template path, not an account credential; build it with
   `tools/build_templates.py` and never upload it with the runtime.

The play-along UI accepts an unknown stock count. Known-deal mode accepts a
remaining known board and stock order, including games already in progress. Its undo restores game state, not the
sampler state or recommendation cache. Do not apply the CLI's stronger undo or
known-stock guarantees to the UI.

## Local server limits

The HTTP app generates session IDs and retains active games for one hour of
inactivity. It admits at most 20 games per client address and 300 per process;
reaching a cap refuses new games instead of evicting another player's game.
One background worker keeps only the latest queued state per game. Two shared
compute slots bound recommendations and exact solves; a separate slot bounds
photo decoding. Requests that cannot run immediately return `busy` or `pending`
with `retry_after`, allowing the client to retry the same request ID.

State polling does not evict action replies. Applied action IDs remain recorded
for the session's lifetime even when full replies are discarded, and a 512-action
cap bounds each game's history. Recommendations use at most 2000 simulations;
known-deal searches share a maximum 10-second budget. Upload bodies are bounded
while streamed, as well as before image decode. These are process-local bounds,
not shared state across several uvicorn workers: use one worker for this runtime.

Official configuration and dependency references:
- https://huggingface.co/docs/hub/spaces-sdks-docker
- https://huggingface.co/docs/hub/spaces-config-reference
