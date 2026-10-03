# Tritowers Solver

Recommends the next move in the Tri Towers pub-quiz-machine card game. Only card ranks matter, suits are ignored.

## Run

    python3 solver.py                 # with the startup tutorial
    python3 solver.py --skip-tutorial
    python3 solver.py --seed 1 --simulations 300 --time-budget 5

Options: `--seed` seeds the sampling, so the same entries and seed give the same output (tested for one scripted game; not a guarantee across Python versions), `--simulations` sets runs per candidate move (default 1200), `--time-budget` is a soft cap in seconds on sampling per recommendation: it is shared between candidates and each still gets at least 20 runs, so it can be exceeded, `--skip-tutorial` hides the intro. Python 3.10+, no dependencies.

## Play

1. Say whether you know all 28 tableau cards and whether you know the stock order.
2. Enter ranks (`A 2 ... 10 J Q K`), use `--` for already-cleared positions.
3. The solver prints the board each turn, then `PLAY <card> @ <position>` with `[GUARANTEED]` or the sampled win rate and run count. Enter any newly exposed or drawn card when asked.
4. After setup the board is shown once more. Press Enter to start, or correct a mistyped entry first: `fix 07 K` (position, rank; `--` cleared, `?` unknown), `waste Q`, or `stock 5 9` (known stock only, 1 = next card drawn). A correction that breaks the deck rules is rejected and nothing changes.
5. Type `undo` (or `u`) at a card prompt to go back one step: it returns to the start of the previous step (or restarts the current one if it is the first), and you re-enter from there. The sampler state is restored too, so after undo the session replays as if the step had not happened (same seed, same entries). Undo does not apply during setup, use the correction step above.
6. Ctrl-D ends the session cleanly.

## Test

    python3 -m unittest -v test_solver.py test_cli.py test_perf_equiv.py test_setup_stock.py test_time_budget.py test_heuristic_baseline.py test_e2e_cli.py test_stock_empty.py

`test_e2e_cli.py` drives the real `solver.py` through stdin. `python tools/heuristic_baseline.py --deals 10000 --seed 11` compares the move heuristic with simple policies.

If setup cards cannot be a real deck (a rank entered more than four times), the solver says where, for example `K was entered 5 times: position 01, position 07 ...`, and asks for a correction with the same `fix` / `waste` / `stock` commands instead of making you start over. Ctrl-D still ends the session.

## Photo reader

`app.py` (Gradio, "Photo to board" tab) and `web_app.py` (`/api/photo`, the "Read from a photo" button) turn a
screenshot or phone photo of the machine screen into a draft board. The reader (`tritowers_vision/reader.py`) finds
the card layout in the image (no exact crop or screen border needed), decides which cards are still on the table using
the game rules, reads the rank of every exposed card and the waste card, and returns a picture showing what it read.
Anything it is not sure of stays `?` and is listed for checking; it never guesses hidden cards, suits or the stock.
It is calibrated on one skin (see `MODEL_CARD.md`).

- `TT_TEMPLATES=path/templates.json`: private same-skin glyph templates (read first). Build them from labelled images
  with `python tools/build_templates.py labels.json templates.json`; never commit them.
- Without templates, ranks come from a bundled bank of open-font glyphs (`tritowers_vision/data/font_glyphs.npz`,
  rebuilt with `tools/build_font_bank.py`). `TT_FONT_TIER=0` turns that off.
- Measure changes with `python tools/vision_eval.py --labels labels.json --captures 4` (real labelled images, plus
  simulated loose crops and phone photos of them) or `--synthetic` (generated screens, `tools/vision_synth.py`).
  The labels format is in `DATASET.md`.

Tests: `python -m pip install -r requirements.txt pytest httpx`, then
`python -m pytest -q tests/test_reader.py tests/test_vision.py tests/test_calibrated.py tests/test_rank2.py`.
