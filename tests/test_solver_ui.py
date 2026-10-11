import sys, os
sys.path.insert(0, os.environ.get("TT_SOLVER_DIR", "."))
import pytest
import solver
import solver_ui as ui
BOARD = "? "*18 + "2 A 3 7 9 J 5 3 9 3"
def test_flow():
    s = ui.new_session(BOARD, "K", 23)
    assert "Ready" in ui.status(s) or "Draw" in ui.status(s)
    assert "position" in ui.recommend(s, 50, 1).lower()
    ui.do_draw(s, "4"); assert s.game.waste == "4" and s.game.stock_remaining == 22
    ui.do_draw(s, "2")
    s.undo(); assert s.game.waste == "4"
def test_bad_board_len():
    with pytest.raises(ValueError): ui.parse_board("A 2 3")
def test_render_has_28():
    assert ui.render_board(ui.new_session(BOARD, "K", 23)).count('class="c ') == 28

MID = "? "*10 + "-- "*8 + "2 A 3 7 9 J 5 3 9 3"
def test_integer_inputs_rejected():
    for bad in (23.9, "23.5", "", None, True, "abc", float("nan")):
        with pytest.raises(ValueError): ui.new_session(BOARD, "K", bad)
    assert ui.new_session(BOARD, "K", 23.0).game.stock_remaining == 23
    s = ui.new_session(BOARD, "K", 23)
    with pytest.raises(ValueError): ui.do_play(s, 20.9)
    with pytest.raises(ValueError): ui.recommend(s, 50.5, 1)
    with pytest.raises(ValueError): ui.recommend(s, 50, 1.5)
def test_stock_bounds():
    for bad in (-1, 24, 40):
        with pytest.raises(ValueError): ui.new_session(BOARD, "K", bad)
    with pytest.raises(ValueError): ui.new_session(MID, "K", 40)
def test_pending_reveal_gates_draw_and_play():
    s = ui.new_session("? "*28, "K", 5)
    assert ui.pending_reveals(s.game)
    with pytest.raises(ValueError): ui.do_draw(s, "4")
    with pytest.raises(ValueError): ui.recommend(s, 10, 1)
    assert s.game.stock_remaining == 5 and not s.history
def test_terminal_blocks_actions():
    s = ui.new_session("-- "*28, "K", 5)
    assert ui.status(s) == "Tableau cleared."
    with pytest.raises(ValueError): ui.do_draw(s, "4")
    assert s.game.stock_remaining == 5 and not s.history
    with pytest.raises(ValueError): ui.recommend(s, 10, 1)
def test_empty_stock_draw_rejected():
    s = ui.new_session(BOARD, "K", 0)
    with pytest.raises(ValueError): ui.do_draw(s, "4")
def test_recommend_passes_time_budget(monkeypatch):
    seen = {}
    def fake(game, **kw): seen.update(kw); return None
    monkeypatch.setattr(solver, "best_move", fake)
    ui.recommend(ui.new_session(BOARD, "K", 23), 50)
    assert seen["time_budget"] == ui.RECOMMEND_TIME_BUDGET
def test_three_tower_geometry():
    h = ui.render_board(ui.new_session(BOARD, "K", 23))
    import re
    pos = {int(m.group(3)): (float(m.group(1)), float(m.group(2))) for m in re.finditer(r'left:([0-9.]+)%;top:([0-9.]+)%" class="c [^"]*"><small>(\d+)', h)}
    assert len(pos) == 28
    assert pos[2][0] > pos[1][0] and pos[3][0] > pos[2][0]
    assert pos[1][1] == pos[2][1] == pos[3][1] < pos[4][1]
    assert abs(pos[1][0] - (pos[4][0] + pos[5][0]) / 2) <= 1
    assert pos[19][1] == pos[28][1] > pos[10][1]


import random as _random
import pytest
import solver
from solver import Game

FRESH = ["?"] * 28

def game(stock=24, **kw): return Game(list(FRESH), "5", False, stock, joker_in_stock=True, **kw)

def test_default_game_is_unchanged_52_cards():
    g = Game(list(FRESH), "5", False, 23); assert g.joker_in_stock is False and g.stock_remaining == 23
    with pytest.raises(ValueError): g.observe_draw("*")                      # no joker in a legacy game

def test_count_includes_joker_and_pool_stays_ranked():
    g = game(); assert g.stock_remaining == 24 and g.joker_in_stock
    assert "*" not in g.unknown_card_pool() and len(g.unknown_card_pool()) == 51   # 52 ranks minus the waste 5
    assert sum(g.unknown_counts().values()) == 51 and g.state_snapshot()["joker_in_stock"] is True

def test_validation():
    with pytest.raises(ValueError): Game(list(FRESH), "5", True, ["A"], joker_in_stock=True)   # known stock uses '*' directly
    with pytest.raises(ValueError): Game(list(FRESH), "5", False, 0, joker_in_stock=True)
    with pytest.raises(ValueError): Game(list(FRESH), "*", False, 24, joker_in_stock=True)     # only one joker
    with pytest.raises(ValueError): Game(["A"] * 5 + ["?"] * 23, "5", False, 24, joker_in_stock=True)  # five aces

def test_last_draw_is_the_joker_and_only_the_last():
    g = game(2)
    with pytest.raises(ValueError): g.observe_draw("*")                       # not last yet
    g.observe_draw("K"); assert g.stock_remaining == 1 and g.waste == "K"
    with pytest.raises(ValueError): g.observe_draw("Q")                       # last card must be the joker
    assert g.observe_draw("*") == "*" and g.waste == "*" and g.stock_empty and not g.joker_in_stock

def test_copy_carries_flag_and_does_not_alias():
    g = game(); c = g.copy(); c.observe_draw("K"); assert g.stock_remaining == 24 and c.joker_in_stock and g.joker_in_stock

def test_cli_draw_takes_joker_without_asking():
    g = game(1); out = []
    assert solver.draw(g, read_card=lambda p: (_ for _ in ()).throw(AssertionError("must not ask")), emit=out.append) is True
    assert g.waste == "*" and "joker" in out[0]

def test_sampled_rollout_draws_the_joker_last_and_wins_on_it():
    g = Game(["K"] + ["--"] * 27, "5", False, 1, joker_in_stock=True)   # K cannot play on 5; the only draw is the joker, K plays on it
    assert solver.simulate(g, rng=_random.Random(0)) is True

def test_cli_flag_and_setup_count():
    import tritowers_cli
    assert tritowers_cli.build_parser().parse_args(["--joker"]).joker is True
    assert tritowers_cli.build_parser().parse_args([]).joker is False
    assert solver.read_stock_count(read_line=lambda p: "24", joker=True) == 24
    out = []
    assert solver.read_stock_count(read_line=(lambda it: lambda p: next(it))(iter(["24", "23"])), emit=out.append) == 23   # 24 refused without joker
