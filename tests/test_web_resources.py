"""Concurrency, admission and transport regressions; no slow solver or private photos."""
from concurrent.futures import ThreadPoolExecutor
from collections import OrderedDict
import io
import threading
import time

import pytest
from fastapi.testclient import TestClient
import web_app
import web_shared
import solver_ui

BOARD = " ".join(["6"] + ["--"] * 27)
UNKNOWN = " ".join(["?"] * 28)
client = TestClient(web_app.app)
REAL_PRECOMPUTE = web_app._precompute


@pytest.fixture(autouse=True)
def isolated_sessions(monkeypatch):
    with web_app._glock:
        for entry in web_app._sessions.values(): entry["active"] = False
        web_app._sessions.clear()
        web_app._requests.clear()
    with web_app._pre_condition: web_app._pre_jobs.clear()
    monkeypatch.setattr(web_app, "_precompute", lambda entry: None)
    yield


def new(**extra):
    return client.post("/api/new", json={"board": BOARD, "waste": "5", "stock": 3, **extra}).json()


def test_new_retries_reuse_generated_session_and_never_overwrite():
    first = new(req_id="new-1", sid="chosen")
    retry = new(req_id="new-1", sid="chosen")
    second = new(req_id="new-2", sid=first["sid"])
    assert first == retry
    assert first["sid"] != "chosen" and second["sid"] != first["sid"]
    assert len(web_app._sessions) == 2
    assert web_app._sessions[first["sid"]]["s"].game.stock_remaining == 3


@pytest.mark.parametrize("extra,message", [
    ({"board": []}, "Board must be text"), ({"waste": None}, "Waste must be text"),
    ({"waste": ""}, "Pick the waste"), ({"joker": "false"}, "Joker mode"),
    ({"req_id": []}, "Request ID"), ({"req_id": "x" * 129}, "Request ID"),
])
def test_new_input_errors_are_actionable(extra, message):
    result = new(**extra)
    assert result["ok"] is False and message in result["message"]


def test_nonstring_session_id_never_raises():
    response = client.post("/api/act", json={"sid": [], "op": "draw"})
    assert response.status_code == 200 and response.json()["gone"]


def test_inflight_retry_does_not_wait_or_apply_twice(monkeypatch):
    sid = new()["sid"]
    started, release = threading.Event(), threading.Event()
    original = web_app._do
    calls = []
    def slow(entry, op, body):
        calls.append(op); started.set()
        assert release.wait(5)
        return original(entry, op, body)
    monkeypatch.setattr(web_app, "_do", slow)
    body = {"sid": sid, "op": "draw", "rank": "9", "req_id": "draw-once"}
    with ThreadPoolExecutor(max_workers=2) as executor:
        future = executor.submit(lambda: client.post("/api/act", json=body).json())
        assert started.wait(2)
        before = time.monotonic()
        duplicate = client.post("/api/act", json=body).json()
        assert duplicate["pending"] and time.monotonic() - before < 1
        release.set()
        finished = future.result(3)
    assert finished["stock"] == 2 and calls == ["draw"]
    assert client.post("/api/act", json=body).json() == finished


def test_completed_cache_pressure_preserves_inflight_event():
    event = threading.Event()
    cache = OrderedDict([("inflight", event)])
    for i in range(100): cache[str(i)] = {"ok": True}
    web_app._trim(cache, 4)
    assert len(cache) == 4 and cache["inflight"] is event
    reservation, result = web_app._claim(cache, "inflight", 4)
    assert reservation is None and result["pending"]


def test_active_session_admission_does_not_evict_existing_games(monkeypatch):
    monkeypatch.setattr(web_app, "MAX_SESSIONS_PER_CLIENT", 2)
    first, second = new(), new()
    denied = new()
    assert not denied["ok"] and "Too many active games" in denied["message"]
    assert set(web_app._sessions) == {first["sid"], second["sid"]}
    entry = web_app._sessions[first["sid"]]
    entry["touched"] = time.monotonic() - web_app.SESSION_TTL - 1
    replacement = new()
    assert replacement["ok"] and not entry["active"]
    assert second["sid"] in web_app._sessions


def test_client_limit_does_not_block_a_different_client(monkeypatch):
    monkeypatch.setattr(web_app, "MAX_SESSIONS_PER_CLIENT", 1)
    assert new()["ok"]
    assert not new()["ok"]
    other = TestClient(web_app.app, client=("other-client", 12345))
    result = other.post("/api/new", json={"board": BOARD, "waste": "5", "stock": 0}).json()
    assert result["ok"]


def test_busy_solver_keeps_health_and_actions_responsive():
    sid = new()["sid"]
    web_app._cpu_slots.acquire(); web_app._cpu_slots.acquire()
    try:
        response = client.post("/api/solve", json={"board": BOARD, "waste": "5", "stock": []}).json()
        assert response["busy"]
        assert client.get("/health").json() == {"ok": True}
        response = client.post("/api/act", json={"sid": sid, "op": "state"}).json()
        assert response["ok"]
    finally:
        web_app._cpu_slots.release(); web_app._cpu_slots.release()


def test_locked_session_returns_busy_without_consuming_request():
    sid = new()["sid"]; entry = web_app._sessions[sid]
    body = {"sid": sid, "op": "draw", "rank": "9", "req_id": "blocked"}
    with entry["lock"]:
        assert client.post("/api/act", json=body).json()["busy"]
    assert "blocked" not in entry["replies"]
    result = client.post("/api/act", json=body).json()
    assert result["ok"] and result["stock"] == 2


def test_exact_solve_retries_do_not_repeat_work(monkeypatch):
    calls = []
    def solve(body): calls.append(body); return {"ok": True, "status": "unsolvable"}
    monkeypatch.setattr(web_app, "solve_deal", solve)
    body = {"board": BOARD, "waste": "5", "stock": [], "req_id": "solve-once"}
    assert client.post("/api/solve", json=body).json() == client.post("/api/solve", json=body).json()
    assert len(calls) == 1


def test_recommend_simulations_are_capped(monkeypatch):
    calls = []
    def advice(game, simulations=1200, seed=None):
        calls.append(simulations)
        return {"text": "example", "pos": 1, "proven": True, "rate": 1, "sims": simulations, "foresight": None}
    monkeypatch.setattr(web_app, "_advice", advice)
    sid = new()["sid"]
    response = client.post("/api/act", json={"sid": sid, "op": "recommend", "sims": 100000}).json()
    assert response["ok"] and calls == [2000]


def test_background_key_includes_stock_mode_removed_and_joker():
    game = solver_ui.new_session(BOARD, "5", 23).game
    before = web_app._key(game)
    game.stock = 22
    assert web_app._key(game) != before
    game.stock = 23; game.removed.add(1)
    assert web_app._key(game) != before


def test_photo_reads_only_bounded_input_and_does_not_leak_exception(monkeypatch):
    from starlette.datastructures import UploadFile
    from tritowers_vision.image import MAX_BYTES
    reads = []
    class Source:
        def read(self, amount): reads.append(amount); return b"invalid"
    result = web_app.api_photo(UploadFile(filename="bad.jpg", file=Source()), corners="")
    assert not result["ok"] and reads == [MAX_BYTES + 1]
    from tritowers_vision import intake
    monkeypatch.setattr(intake, "read_photo", lambda *args: (_ for _ in ()).throw(RuntimeError("secret-path")))
    result = web_shared.photo_response(b"x")
    assert not result["ok"] and "secret-path" not in result["message"]


def test_large_request_rejected_before_parsing():
    response = client.post("/api/new", content=b"x" * 17000, headers={"Content-Type": "application/json"})
    assert response.status_code == 413


def test_real_endgame_solves_without_full_23_card_stock():
    result = web_shared.solve_deal({"board": BOARD, "waste": "5", "stock": [], "stock_count": 0})
    assert result["ok"] and result["status"] == "solved"
    assert result["frames"][-1]["remaining"] == 0


def test_background_queue_is_latest_only_and_skips_expired_sessions(monkeypatch):
    original_precompute = REAL_PRECOMPUTE
    started, release = threading.Event(), threading.Event()
    calls = []
    def advice(game):
        calls.append(game.stock_remaining)
        if len(calls) == 1:
            started.set(); assert release.wait(5)
        return {"text": "ready", "pos": 1}
    monkeypatch.setattr(web_app, "_advice", advice)
    entries = [web_app._sessions[new()["sid"]] for _ in range(3)]
    original_precompute(entries[0]); assert started.wait(3)
    worker = web_app._pre_worker
    for count in (12, 11, 10):
        entries[1]["s"].game.stock = count
        original_precompute(entries[1])
    original_precompute(entries[2]); entries[2]["active"] = False
    with web_app._pre_condition: assert len(web_app._pre_jobs) == 2
    assert web_app._pre_worker is worker
    release.set()
    assert entries[1]["pre"]["done"].wait(3)
    assert entries[2]["pre"]["done"].wait(3)
    assert calls == [3, 10]
    web_app._adopt(entries[1])
    assert entries[1]["advice"]["text"] == "ready"


def test_chunked_request_is_bounded_without_content_length():
    def chunks():
        yield b'{"board":"'
        yield b'x' * 17000
        yield b'"}'
    response = client.post("/api/new", content=chunks(), headers={"Content-Type": "application/json"})
    assert response.status_code == 413 and response.json()["ok"] is False


def test_mutation_retry_survives_reply_eviction_and_polling():
    sid = new()["sid"]
    body = {"sid": sid, "op": "draw", "rank": "9", "req_id": "important-draw"}
    assert client.post("/api/act", json=body).json()["stock"] == 2
    entry = web_app._sessions[sid]
    entry["replies"].clear()  # completed reply evicted; the successful action ID survives
    for _ in range(3):
        assert client.post("/api/act", json={"sid": sid, "op": "state"}).json()["ok"]
    assert not entry["replies"]
    retry = client.post("/api/act", json=body).json()
    assert retry["ok"] and retry["stock"] == 2
    assert len(entry["s"].history) == 1


def test_action_limit_bounds_history_without_forgetting_applied_requests(monkeypatch):
    monkeypatch.setattr(web_app, "MAX_SESSION_ACTIONS", 1)
    sid = new()["sid"]
    first = {"sid": sid, "op": "draw", "rank": "9", "req_id": "first"}
    result = client.post("/api/act", json=first).json()
    assert result["ok"]
    blocked = client.post("/api/act", json={**first, "req_id": "second"}).json()
    assert not blocked["ok"] and "action limit" in blocked["message"]
    assert client.post("/api/act", json=first).json() == result
    assert len(web_app._sessions[sid]["s"].history) == 1


def test_retried_old_action_returns_current_board_without_reapplying():
    sid = new()["sid"]
    first = {"sid": sid, "op": "draw", "rank": "9", "req_id": "draw-one"}
    assert client.post("/api/act", json=first).json()["stock"] == 2
    assert client.post("/api/act", json={**first, "rank": "8", "req_id": "draw-two"}).json()["stock"] == 1
    retry = client.post("/api/act", json=first).json()
    assert retry["stock"] == 1 and retry["waste"] == "8"
    assert len(web_app._sessions[sid]["s"].history) == 2


def test_unknown_board_new_retry_caches_pending_reveals_and_creates_once(monkeypatch):
    calls = []
    monkeypatch.setattr(web_app, "_precompute", lambda entry: calls.append(entry["sid"]))
    first = new(board=UNKNOWN, stock=23, req_id="unknown-new")
    assert first["pending"] == list(range(19, 29))
    assert web_app._requests[("testclient", "new", "unknown-new")] == first
    second = new(board=UNKNOWN, stock=23, req_id="unknown-new")
    assert second == first and len(web_app._sessions) == 1
    assert calls == [first["sid"]]


def test_partial_reveal_is_cached_despite_remaining_pending_cards():
    sid = new(board=UNKNOWN, stock=23)["sid"]
    body = {"sid": sid, "op": "reveal", "pos": 19, "rank": "A", "req_id": "reveal-first"}
    first = client.post("/api/act", json=body).json()
    assert first["ok"] and first["pending"] == list(range(20, 29))
    entry = web_app._sessions[sid]
    assert entry["replies"]["reveal-first"] == first
    assert client.post("/api/act", json=body).json() == first
    assert len(entry["s"].history) == 1
    assert entry["s"].game.board[18:20] == ["A", "?"]


def test_new_retry_resumes_current_board_after_reply_cache_eviction():
    first = new(req_id="resume-new")
    drawn = client.post("/api/act", json={"sid": first["sid"], "op": "draw", "rank": "9", "req_id": "draw"}).json()
    assert drawn["stock"] == 2
    with web_app._glock: web_app._requests.clear()
    retry = new(req_id="resume-new")
    assert retry["sid"] == first["sid"] and retry["stock"] == 2 and retry["waste"] == "9"
    assert len(web_app._sessions) == 1


def test_expired_new_reply_does_not_return_a_missing_game():
    first = new(req_id="expired-new")
    entry = web_app._sessions[first["sid"]]
    entry["touched"] = time.monotonic() - web_app.SESSION_TTL - 1
    replacement = new(req_id="expired-new")
    assert replacement["ok"] and replacement["sid"] != first["sid"]
    assert first["sid"] not in web_app._sessions and replacement["sid"] in web_app._sessions
    assert not entry["active"]


def test_retry_of_failed_action_keeps_current_state_in_error_reply():
    sid = new()["sid"]
    invalid = {"sid": sid, "op": "draw", "rank": "not-a-rank", "req_id": "failed-draw"}
    first = client.post("/api/act", json=invalid).json()
    assert not first["ok"]
    assert client.post("/api/act", json={**invalid, "rank": "9", "req_id": "good-draw"}).json()["stock"] == 2
    retry = client.post("/api/act", json=invalid).json()
    assert not retry["ok"] and retry["message"] == first["message"]
    assert retry["stock"] == 2 and retry["waste"] == "9"
