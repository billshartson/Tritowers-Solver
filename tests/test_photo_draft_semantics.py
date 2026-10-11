"""A corrected photo draft (covered cards unknown, missing slots empty) must keep play-along
semantics: no hidden cards or stock order inferred, joker stays the last stock card."""
import pytest

import solver
import web_core as core


@pytest.fixture(autouse=True)
def fresh():
    core._sessions.clear(); core._replies.clear()
    yield
    core._sessions.clear(); core._replies.clear()


def draft_board():
    board = ["?"] * 18 + ["9", "3", "4", "5", "6", "7", "8", "9", "10", "J"]
    board[27] = "--"  # a bottom-row slot the photo reader found empty
    return board


def test_draft_with_empty_slot_and_joker_is_not_a_full_deal():
    board = " ".join(draft_board())
    result = core.api_solve({"board": board, "waste": "A", "stock_count": 24})
    assert result["status"] == "incomplete"
    s = core.api_new({"board": board, "waste": "A", "stock": 24, "joker": True})
    game = core._sessions[s["sid"]]["s"].game
    assert not game.stock_known and game.joker_in_stock
    assert game.board[:18] == ["?"] * 18 and game.board[27] == "--"


def test_empty_slot_under_a_covered_card_is_rejected():
    board = draft_board(); board[0] = "--"
    s = core.api_new({"board": " ".join(board), "waste": "A", "stock": 24, "joker": True})
    assert s["ok"] is False and "covered" in s["message"]


def test_stock_order_is_never_inferred_and_joker_comes_last():
    board = " ".join(["?"] * 18 + ["9", "3", "4", "5", "6", "7", "8", "9", "10", "J"])
    sid = core.api_new({"board": board, "waste": "A", "stock": 3, "joker": True})["sid"]
    game = core._sessions[sid]["s"].game

    def draw(rank=""):
        return core.api_act({"sid": sid, "op": "draw", "rank": rank})

    # No legal tableau play is forced here; drawing needs a rank until the joker is last.
    assert not draw()["ok"]
    assert draw("4")["ok"] and game.stock_remaining == 2
    assert draw("5")["ok"] and game.stock_remaining == 1
    last = draw()  # last stock card is the joker, no rank asked
    assert last["ok"] and game.stock_remaining == 0
    assert game.waste == "*" or "*" in str(last.get("waste"))
