---
title: TriTowers Solver
emoji: 🃏
colorFrom: green
colorTo: gray
sdk: gradio
sdk_version: 6.28.0
python_version: "3.10"
app_file: app.py
suggested_hardware: cpu-basic
pinned: false
---
# TriTowers Solver

A rank-only Tri Towers move helper with manual board entry and an optional photo
reader. Enter the 28 tableau positions, waste rank and number of stock cards left,
then start a game. Green cards are playable; yellow question marks need a rank
before a recommendation. Enter the position you played, newly revealed ranks or
the card drawn from stock. Undo restores the previous game state.

The UI accepts an unknown stock count, not a known stock order. UI undo restores
game state only, not sampling history. Sampled win percentages are estimates, not
proofs. A proven recommendation is separately labelled. The stock count is the
engine count; translating a quiz-machine HUD count has not been verified.

## Photo reader limits

Recognition is calibrated on one skin. Always review its draft (the picture shows
what was read) before copying it into the solver. It finds the card layout in
screenshots, loose crops and phone photos, and reads ranks from private same-skin
templates (`TT_TEMPLATES`) or, failing that, a bundled set of open-font glyphs.
Unread or uncertain cards are left as `?` and flagged. Set `TT_FONT_TIER=0` to read
ranks only from private templates. No photos or photo-derived templates are bundled.
Suits and stock counters are not read.

## Runtime

This file must be the Space's root `README.md`. The runtime entrypoint is `app.py`;
root `requirements.txt` pins Gradio 6.28.0 and the image dependencies. The solver
runs on CPU. `suggested_hardware` is a suggestion, not a hardware purchase.

The deployment owner must create or select a **private** Space before uploading.
README metadata does not enforce visibility. This package neither creates a
Space nor uploads anything. See `HF-DEPLOY.md` in the source repository for the
runtime staging and verification checklist.
