"""Reported CLI/engine regressions: #25, #31, #32 and #34."""
from collections import Counter
import random
import re

import pytest

import solver
import solver_ui as ui
import tritowers_cli as cli
from tools import heuristic_baseline as hb


def last_cards(*cards, waste="A", stock=(), known=True):
    return solver.Game(list(cards) + ["--"] * (28 - len(cards)), waste, known,
                       list(stock) if known else stock)


def test_reveal_retries_impossible_rank_without_consuming_it():
    board = ["?"] * 18 + ["?", "Q", "Q", "Q", "Q", "2", "3", "4", "5", "6"]
    game = solver.Game(board, "7", False, 23)
    original = game.state_snapshot()
    ranks, messages, prompts = iter(["Q", "8"]), [], []
    def answer(prompt):
        prompts.append(prompt)
        assert game.state_snapshot() == original
        assert game.seen_counts["Q"] == 4
        return next(ranks)
    solver.reveal_unknowns(game, read_card=answer, emit=messages.append)
    assert prompts == ["Position 19: "] * 2
    assert game.board[18] == "8" and game.seen_counts["8"] == 1
    assert "more than four Q" in messages[0]


def test_draw_retries_impossible_rank_without_consuming_stock():
    game = solver.Game(["Q"] * 4 + ["?"] * 24, "A", False, 2)
    ranks, prompts = iter(["Q", "K"]), []
    def answer(prompt):
        prompts.append(prompt)
        assert game.stock == 2 and game.waste == "A"
        return next(ranks)
    assert solver.draw(game, read_card=answer, emit=lambda _: None)
    assert prompts == ["DRAW -> "] * 2
    assert game.stock == 1 and game.waste == "K" and game.seen_counts["Q"] == 4


def test_undo_crosses_automatic_steps_and_repeated_undo_moves_back(monkeypatch, capsys):
    board, waste, stock = hb.deal(random.Random(3))
    game = solver.Game(["?"] * 18 + board[18:], waste, True, stock)
    monkeypatch.setattr(solver, "setup", lambda **_: game)
    monkeypatch.setattr(solver, "review_setup", lambda game: game)
    asked = []
    def answer(prompt):
        position = int(re.search(r"Position (\d+)", prompt).group(1))
        asked.append(position)
        if len(asked) in (3, 4):
            return "undo"
        return board[position - 1]
    monkeypatch.setattr("builtins.input", answer)
    solver.main(["--skip-tutorial", "--seed", "1", "--simulations", "40"])
    assert asked[:5] == [15, 16, 17, 16, 15]
    assert "WIN!" in capsys.readouterr().out


def test_exact_cli_uses_verified_line_and_never_samples(monkeypatch, capsys):
    board, waste, stock = hb.deal(random.Random(3))
    game = solver.Game(board, waste, True, stock)
    monkeypatch.setattr(solver, "setup", lambda **_: game)
    monkeypatch.setattr(solver, "review_setup", lambda game: game)
    monkeypatch.setattr(solver, "best_move", lambda *a, **k: pytest.fail("known deal was sampled"))
    solver.main(["--seed", "1", "--simulations", "1"])
    text = capsys.readouterr().out
    assert "WIN!" in text and text.count("[PROVEN: verified winning line]") == 28


def test_exact_cli_reports_proven_unsolvable(monkeypatch, capsys):
    game = last_cards("8", waste="A")
    monkeypatch.setattr(solver, "setup", lambda **_: game)
    monkeypatch.setattr(solver, "review_setup", lambda game: game)
    solver.main([])
    assert "No winning line exists" in capsys.readouterr().out


def test_seed_and_wall_time_budget_are_explicitly_incompatible():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["--seed", "3", "--time-budget", ".1"])


@pytest.mark.parametrize("bad", ["nan", "inf", "-inf", "0"])
def test_cli_rejects_nonfinite_time_budgets(bad):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["--time-budget", bad])


def test_timed_candidates_receive_equal_completed_rounds(monkeypatch):
    game = last_cards("2", "K", waste="A", known=False, stock=2)
    runs = Counter()
    def simulation(game, first_move, rng):
        runs[first_move] += 1
        return first_move == 1
    monkeypatch.setattr(solver, "simulate", simulation)
    rec = solver.best_move(game, simulations=500, time_budget=1e-12)
    assert runs == {1: solver.MIN_BUDGET_SIMULATIONS, 2: solver.MIN_BUDGET_SIMULATIONS}
    assert rec.position == 1 and rec.simulations == solver.MIN_BUDGET_SIMULATIONS


def test_midgame_known_stock_accepts_short_empty_and_joker(monkeypatch):
    assert solver.read_stock_cards(lambda _: "A 2 Q") == ["A", "2", "Q"]
    assert solver.read_stock_cards(lambda _: "") == []
    assert solver.read_stock_cards(lambda _: "A 2", joker=True) == ["A", "2", "*"]
    answers = iter(["1", "1", " ".join(["2"] + ["--"] * 27), "A", "K Q"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    game = solver.setup(skip_tutorial=True)
    assert game.stock == ["K", "Q"]


def test_review_stock_count_can_be_corrected_after_clearing_slot():
    game = solver.Game(["?"] * 28, "A", False, 23)
    answers = iter(["fix 19 --", "stock 11", ""])
    changed = solver.review_setup(game, read_line=lambda _: next(answers), emit=lambda *a: None)
    assert changed.stock == 11 and changed.board[18] == "--"
    assert game.stock == 23 and game.board[18] == "?"


def test_overfull_report_excludes_unknown_and_removed_stock_entries():
    assert solver.overfull_report(["?"] * 28, "A", True, ["?"] * 8 + ["--"] * 7) == []


def test_stock_count_limit_also_applies_to_sparse_positions():
    with pytest.raises(ValueError, match="stock.*23"):
        last_cards("2", waste="A", known=False, stock=30)


def test_cleared_card_cannot_still_have_present_blockers():
    board = ["?"] * 28
    board[0] = "--"
    with pytest.raises(ValueError, match="still covered"):
        solver.Game(board, "A", False, 23)


def test_exact_search_uses_normalized_values_without_mutating_input():
    game = last_cards("10", waste="9", stock=["Q"])
    game.waste, game.board[0], game.stock[0] = " 9", " 10 ", " q "
    before = game.state_snapshot()
    result = solver.solve_complete(game)
    assert result.status == "solved" and result.moves == [("play", 1)]
    assert game.state_snapshot() == before


def test_removed_unknown_rank_does_not_block_exact_remaining_position():
    game = last_cards("2", waste="A")
    game.board[1] = "?"  # a removed card's old rank is immaterial
    assert solver.solve_complete(game).status == "solved"


def test_normalized_cleared_slot_must_match_removed_positions():
    game = last_cards("2", waste="A")
    game.board[0] = " -- "
    result = solver.solve_complete(game)
    assert result.status == "incomplete" and "cleared slots not in removed" in result.reason


def test_empty_ui_inputs_report_useful_errors():
    with pytest.raises(ValueError, match="Board must be text"):
        ui.new_session([], "A", 23)
    with pytest.raises(ValueError, match="waste rank"):
        ui.new_session("? " * 28, None, 23)
    session = ui.Session(last_cards("2", waste="A", stock=2, known=False))
    with pytest.raises(ValueError, match="drawn card"):
        ui.do_draw(session, None)
    assert not session.history and session.game.stock == 2


def test_ui_known_midgame_foresight_and_recommendation_are_exact():
    session = ui.Session(last_cards("2", waste="A"))
    text, position, proven, rate, runs = ui.recommend_detail(session)
    assert (position, proven, rate, runs) == (1, True, 1.0, 0)
    assert "verified winning line" in text
    assert "Exact:" in ui.foresight_line(session, 1)


def test_ui_seed_selects_fixed_work_sampling(monkeypatch):
    seen = {}
    def recommend(game, **kw):
        seen.update(kw)
    monkeypatch.setattr(solver, "best_move", recommend)
    ui.recommend_detail(ui.new_session("? " * 18 + "2 A 3 7 9 J 5 3 9 3", "K", 23), 50, seed=1)
    assert seen["time_budget"] is None and seen["simulations"] == 50
