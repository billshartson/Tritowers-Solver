# Private Hugging Face Space deployment

The deployment owner handles account access, Space creation, visibility, upload
and any paid hardware decision. This package does none of those things.

## Stage the runtime

From a reviewed checkout, choose a new destination outside the source tree:

```sh
python3 tools/prepare_space.py /tmp/tritowers-space-runtime
```

The staging script refuses existing destinations. It copies this runtime manifest:

- `app.py`: Gradio entrypoint, with per-browser session state.
- `solver_ui.py`, `solver.py`, `tritowers_cli.py`: UI adapter and solver imports.
- `tritowers_vision/`: image extraction and recognition modules, without bytecode.
- `requirements.txt`: pinned runtime dependencies.
- `MODEL_CARD.md`: recognition limitations.
- `README-SPACE.md` renamed to root `README.md`: Hugging Face SDK metadata.

It does not copy the source Git history, tests, annotation app, local environment,
private templates, photos or corpus. No `packages.txt` is needed for the pinned
headless OpenCV wheel. `annotation_app.py` is a separate tool, not this Space.

## Validate before upload

Use Python 3.10 in a clean environment. Root README pins the same Gradio version
as requirements. From the staged runtime:

```sh
python3 -m venv /tmp/tritowers-space-venv
/tmp/tritowers-space-venv/bin/pip install -r requirements.txt
/tmp/tritowers-space-venv/bin/pip check
/tmp/tritowers-space-venv/bin/python -c 'import app; assert app.demo is not None'
/tmp/tritowers-space-venv/bin/python app.py
```

Check the local UI opens, then stop it. Import/startup checks are not hosted build
or browser acceptance. Run the source tests separately in the full checkout.

## Owner deployment checklist

1. Create or select a **private Gradio Space** and verify visibility in its account
   settings. The README cannot enforce privacy.
2. Upload the staged runtime with `README.md` at the root. Do not upload secrets,
   templates or a photo corpus inadvertently.
3. Check the build log, dependency install and runtime startup. Open the actual
   Space and test start, recommendation, play, reveal, draw and undo on desktop
   and mobile. Record the deployed source revision and Space URL.
4. Confirm recommendation latency on the chosen CPU. A solver time budget is a
   soft cap, not a strict hosted response deadline; the UI wiring owner handles
   the recommendation cap.
5. Keep calibrated photo reading unavailable unless separately approved private
   templates are provided. `TT_TEMPLATES` is an optional local template path,
   not an account credential. No calibration data is supplied by this package.

The UI accepts an unknown stock count only. Its undo restores game state, not the
sampler state or recommendation cache. Do not apply the CLI's stronger undo or
known-stock guarantees to the UI.

Official configuration and dependency references:
- https://huggingface.co/docs/hub/spaces-sdks-gradio
- https://huggingface.co/docs/hub/spaces-config-reference
