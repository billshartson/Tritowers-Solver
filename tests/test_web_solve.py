"""Complete-deal endpoint tests with a fake solver (no solver core dependency)."""
import types
import pytest
from fastapi.testclient import TestClient
import web_app, solver

client = TestClient(web_app.app)
# legal endgame: a top-peak 6 remains after every supporting card was cleared
BOARD = ["6"] + ["--"] * 27
def post(**kw):
    body = {"board": " ".join(BOARD), "waste": "5", "stock": [], "stock_count": 0}; body.update(kw)
    return client.post("/api/solve", json=body).json()

def fake(status, moves=(), reason=""):
    return lambda game, time_budget=None, **kw: types.SimpleNamespace(status=status, moves=list(moves), reason=reason, nodes=3, seconds=0.01)

def test_incomplete_deal_is_never_guessed(monkeypatch):
    monkeypatch.setattr(solver, "solve_complete", fake("solved"), raising=False)
    r = post(board=" ".join(["?"] + ["--"] * 27)); assert r["status"] == "incomplete" and "tableau position 1" in r["message"]
    r = post(waste=""); assert r["status"] == "incomplete" and "waste" in r["message"]
    r = post(stock=["A"], stock_count=3); assert r["status"] == "incomplete" and "stock order" in r["message"]

def test_unavailable_without_solver(monkeypatch):
    monkeypatch.delattr(solver, "solve_complete", raising=False)
    assert post()["status"] == "unavailable"

def test_solved_line_is_replayed_and_shown(monkeypatch):
    monkeypatch.setattr(solver, "solve_complete", fake("solved", [("play", 1)]), raising=False)
    r = post(); assert r["status"] == "solved" and r["steps"] == ["Play the 6 (position 1)"]
    assert len(r["frames"]) == 2 and r["frames"][0]["next"] == 1 and r["frames"][1]["remaining"] == 0

def test_bad_line_is_rejected_not_shown(monkeypatch):
    monkeypatch.setattr(solver, "solve_complete", fake("solved", [("play", 20)]), raising=False)
    r = post(); assert r["ok"] is False and "verification" in r["message"] and "steps" not in r
    monkeypatch.setattr(solver, "solve_complete", fake("solved", []), raising=False)
    assert post()["ok"] is False                                   # empty line does not clear the tableau

def test_unsolvable_and_unknown_are_distinct(monkeypatch):
    monkeypatch.setattr(solver, "solve_complete", fake("unsolvable"), raising=False)
    assert "Proven unsolvable" in post()["message"]
    monkeypatch.setattr(solver, "solve_complete", fake("unknown", reason="timeout"), raising=False)
    m = post()["message"]; assert "NOT a proof" in m and "Proven" not in m

def test_background_recommendation_is_ready(monkeypatch):
    import time
    r = client.post("/api/new", json={"board": " ".join(BOARD), "waste": "5", "stock": 23}).json(); sid = r["sid"]
    adv = None
    for _ in range(40):
        s = client.post("/api/act", json={"sid": sid, "op": "state"}).json()
        if s.get("advice"): adv = s["advice"]; break
        time.sleep(0.25)
    assert adv and adv["pos"] == 1, adv
    # asking explicitly returns the same cached result without error
    assert client.post("/api/act", json={"sid": sid, "op": "recommend"}).json()["advice"]["pos"] == 1

def test_policy_labels(monkeypatch):
    # stuck-only unsolvable but voluntary solved -> solved with the voluntary caveat
    def f(game, time_budget=None, draw_only_when_stuck=True, **kw):
        if draw_only_when_stuck: return types.SimpleNamespace(status="unsolvable", moves=[], reason="", nodes=1, seconds=0)
        return types.SimpleNamespace(status="solved", moves=[("play", 1)], reason="", nodes=1, seconds=0)
    monkeypatch.setattr(solver, "solve_complete", f, raising=False)
    r = post(); assert r["status"] == "solved" and r["policy"] == "voluntary" and "draw while a play" in r["message"]
    monkeypatch.setattr(solver, "solve_complete", fake("unsolvable"), raising=False)
    r = post(); assert r["policy"] == "both" and "both draw rules" in r["message"]

def test_real_solver_end_to_end():
    # real solve_complete on a fresh full deal is validated, solved lines are verified by replay
    import random
    rnd = random.Random(3); d = [x for x in solver.RANKS for _ in range(4)]; rnd.shuffle(d)
    r = client.post("/api/solve", json={"board": " ".join(d[:28]), "waste": d[28], "stock": d[29:], "stock_count": 23}).json()
    assert r["ok"] is True and r["status"] in ("solved", "unknown", "unsolvable"), r
    assert r["policy"] in ("stuck", "voluntary", "both"), r
    if r["status"] == "solved": assert r["frames"][-1]["remaining"] == 0 and len(r["steps"]) == len(r["frames"]) - 1


def test_foresight_line_is_labelled_and_separate():
    import random, solver_ui as ui
    rnd = random.Random(5); d = [x for x in solver.RANKS for _ in range(4)]; rnd.shuffle(d)
    vis = ["?" if p <= 18 else d[p - 1] for p in range(1, 29)]
    s = ui.Session(solver.Game(vis, d[28], False, 23))
    text, pos, proven, rate, sims = ui.recommend_detail(s, 200, 1)
    assert "Winnable" not in text and pos
    fs = ui.foresight_line(s, pos, 1)
    assert "perfect foresight" in fs and "not a bound" in fs and "sampled completions" in fs
    # inconsistent card counts: no estimate rather than a made-up one
    bad = ui.Session(solver.Game(vis, d[28], False, 22))
    assert ui.foresight_line(bad, pos, 1) is None


def test_malformed_solve_inputs_never_500():
    for extra in ({"stock_count": "x"}, {"time_budget": "x"}, {"stock": "AAAA"}, {"stock_count": 1.5}, {"stock_count": -1}, {"stock": None}):
        r = client.post("/api/solve", json={"board": " ".join(BOARD), "waste": "5", "stock": [], **extra})
        assert r.status_code == 200 and "ok" in r.json(), (extra, r.status_code)


def _joker_deal(seed):
    import random
    cards = [r for r in web_app.RANKS for _ in range(4)]; random.Random(seed).shuffle(cards)
    return cards[:28], cards[28], cards[29:] + ["*"]

def test_joker_deal_accepts_24_stock_and_verifies_line():
    board, waste, stock = _joker_deal(1)
    r = client.post("/api/solve", json={"board": " ".join(board), "waste": waste, "stock": stock, "stock_count": 24, "time_budget": 4}).json()
    assert r["ok"] is True and r["status"] in ("solved", "unsolvable", "unknown"), r
    if r["status"] == "solved": assert r["frames"][-1]["remaining"] == 0     # line was replayed with the joker in the stock

def test_joker_must_be_last_and_only_one():
    board, waste, stock = _joker_deal(2)
    bad = ["*"] + stock[:-1]
    r = client.post("/api/solve", json={"board": " ".join(board), "waste": waste, "stock": bad, "stock_count": 24}).json()
    assert r["ok"] is False and "joker" in r["message"].lower()
    r = client.post("/api/solve", json={"board": " ".join(board), "waste": waste, "stock": stock, "stock_count": 25}).json()
    assert r["ok"] is False


def test_play_along_joker_session_draws_the_joker_last():
    b = ["?"] * 18 + ["A", "2", "3", "4", "7", "8", "9", "10", "J", "Q"]          # exposed bottom row known, so no reveals are pending
    r = client.post("/api/new", json={"board": " ".join(b), "waste": "5", "stock": 2, "joker": True, "sid": "jk1"}).json()
    assert r["ok"] and r["joker"] is True and r["stock"] == 2
    sid = r["sid"]; assert sid != "jk1"
    r = client.post("/api/act", json={"sid": sid, "op": "draw", "rank": "*"}).json(); assert not r["ok"]      # joker is only the last card
    r = client.post("/api/act", json={"sid": sid, "op": "draw", "rank": "K"}).json(); assert r["ok"] and r["stock"] == 1 and r["waste"] == "K"
    r = client.post("/api/act", json={"sid": sid, "op": "draw"}).json()                                       # last card: no rank needed
    assert r["ok"] and r["waste"] == "*" and r["stock"] == 0 and r["joker"] is False

def test_joker_session_cap_and_legacy_default():
    b = " ".join(["?"] * 28)
    assert not client.post("/api/new", json={"board": b, "waste": "5", "stock": 24}).json()["ok"]            # legacy cap 23
    r = client.post("/api/new", json={"board": b, "waste": "5", "stock": 24, "joker": True}).json(); assert r["ok"] and r["stock"] == 24


def test_exhaustive_voluntary_failure_proves_both_policies(monkeypatch):
    def search(game, draw_only_when_stuck=True, **kwargs):
        return types.SimpleNamespace(status="unknown" if draw_only_when_stuck else "unsolvable",
                                     moves=[], reason="timeout", nodes=2, seconds=0.5)
    monkeypatch.setattr(solver, "solve_complete", search)
    result = post()
    assert result["status"] == "unsolvable" and result["policy"] == "both"
    assert result["nodes"] == 4 and result["seconds"] == 1
