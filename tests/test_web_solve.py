"""Complete-deal endpoint tests with a fake solver (no solver core dependency)."""
import types
import pytest
pytest.importorskip("fastapi"); pytest.importorskip("httpx")
from fastapi.testclient import TestClient
import web_app, solver

client = TestClient(web_app.app)
# one playable card: waste 5, a 6 on the bottom row, everything else empty
BOARD = ["--"] * 18 + ["6"] + ["--"] * 9
def post(**kw):
    body = {"board": " ".join(BOARD), "waste": "5", "stock": [], "stock_count": 0}; body.update(kw)
    return client.post("/api/solve", json=body).json()

def fake(status, moves=(), reason=""):
    return lambda game, time_budget=None: types.SimpleNamespace(status=status, moves=list(moves), reason=reason, nodes=3, seconds=0.01)

def test_incomplete_deal_is_never_guessed(monkeypatch):
    monkeypatch.setattr(solver, "solve_complete", fake("solved"), raising=False)
    r = post(board=" ".join(["?"] + ["--"] * 27)); assert r["status"] == "incomplete" and "tableau position 1" in r["message"]
    r = post(waste=""); assert r["status"] == "incomplete" and "waste" in r["message"]
    r = post(stock=["A"], stock_count=3); assert r["status"] == "incomplete" and "stock order" in r["message"]

def test_unavailable_without_solver(monkeypatch):
    monkeypatch.delattr(solver, "solve_complete", raising=False)
    assert post()["status"] == "unavailable"

def test_solved_line_is_replayed_and_shown(monkeypatch):
    monkeypatch.setattr(solver, "solve_complete", fake("solved", [("play", 19)]), raising=False)
    r = post(); assert r["status"] == "solved" and r["steps"] == ["Play the 6 (position 19)"]
    assert len(r["frames"]) == 2 and r["frames"][0]["next"] == 19 and r["frames"][1]["remaining"] == 0

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
    r = client.post("/api/new", json={"board": " ".join(BOARD), "waste": "5", "stock": 0}).json(); sid = r["sid"]
    adv = None
    for _ in range(40):
        s = client.post("/api/act", json={"sid": sid, "op": "state"}).json()
        if s.get("advice"): adv = s["advice"]; break
        time.sleep(0.25)
    assert adv and adv["pos"] == 19, adv
    # asking explicitly returns the same cached result without error
    assert client.post("/api/act", json={"sid": sid, "op": "recommend"}).json()["advice"]["pos"] == 19
