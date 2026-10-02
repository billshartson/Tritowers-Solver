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
4. Ctrl-D ends the session cleanly.

## Test

    python3 -m unittest -v test_solver.py test_cli.py test_perf_equiv.py test_setup_stock.py test_time_budget.py test_heuristic_baseline.py test_e2e_cli.py

`test_e2e_cli.py` drives the real `solver.py` through stdin. `python tools/heuristic_baseline.py --deals 10000 --seed 11` compares the move heuristic with simple policies.

Not done yet: undo is implemented in `tritowers_cli.UndoHistory` but not wired into the prompts.
