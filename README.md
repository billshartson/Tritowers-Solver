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
