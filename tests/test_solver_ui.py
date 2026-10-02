import sys, os
sys.path.insert(0, os.environ.get("TT_SOLVER_DIR", "."))
import pytest
solver = pytest.importorskip("solver")
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
    ui.recommend(ui.new_session(BOARD, "K", 23), 50, 1)
    assert seen["time_budget"] == ui.RECOMMEND_TIME_BUDGET
def test_three_tower_geometry():
    h = ui.render_board(ui.new_session(BOARD, "K", 23))
    import re
    pos = {int(m.group(3)): (int(m.group(1)), int(m.group(2))) for m in re.finditer(r'left:(\d+)px;top:(\d+)px" class="c [^"]*"><small>(\d+)', h)}
    assert len(pos) == 28
    assert pos[2][0] > pos[1][0] and pos[3][0] > pos[2][0]
    assert pos[1][1] == pos[2][1] == pos[3][1] < pos[4][1]
    assert abs(pos[1][0] - (pos[4][0] + pos[5][0]) / 2) <= 1
    assert pos[19][1] == pos[28][1] > pos[10][1]
