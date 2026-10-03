"""Plain HTTP front end (no Gradio queue, no SSE). Every action is a JSON POST that the page can safely retry:
the server caches the response per request id, so a retry after a dropped connection never applies an action twice.
Run: python web_app.py   (PORT env, default 7860)."""
import os, threading, time, uuid
from collections import OrderedDict
from pathlib import Path
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
import solver, solver_ui as ui

RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
MAX_SESSIONS = 300
HERE = Path(__file__).resolve().parent
app = FastAPI(title="TriTowers")
_sessions = OrderedDict()   # sid -> {"s": Session, "lock": Lock, "replies": {req_id: reply|Event}, "advice": dict|None}
_glock = threading.Lock()
_TEMPLATES = None

def _templates():
    global _TEMPLATES
    if _TEMPLATES is None:
        path = os.environ.get("TT_TEMPLATES")
        if path and os.path.exists(path):
            from tritowers_vision.rank import load_templates
            _TEMPLATES = load_templates(path)
        else: _TEMPLATES = []
    return _TEMPLATES

def geometry():
    xs = {p: float(p - 19) for p in range(19, 29)}
    for p in sorted(solver.BLOCKERS, reverse=True): xs[p] = sum(xs[b] for b in solver.BLOCKERS[p]) / 2
    ys = {p: next(i for i, row in enumerate(ui.ROWS) if p in row) for p in range(1, 29)}
    XU, YU, W, H = 58, 76, 52, 68
    CW, CH = 9 * XU + W, 3 * YU + H
    return {p: (round(xs[p] * XU / CW * 100, 3), round(ys[p] * YU / CH * 100, 3)) for p in range(1, 29)}, round(CW / CH, 4)
GEO, ASPECT = geometry()

def view(entry, message="", ok=True, extra=None):
    s = entry["s"]; g = s.game; snap = g.state_snapshot(); exposed = set(g.exposed()); legal = set(g.legal_moves()); pend = set(ui.pending_reveals(g))
    advice = entry.get("advice")
    cells = []
    for p in range(1, 29):
        if p in snap["removed"]: kind, card = "gone", ""
        elif snap["board"][p - 1] == "?": kind, card = ("ask" if p in pend else "back"), "?"
        else: kind, card = ("play" if p in legal else "up" if p in exposed else "blocked"), snap["board"][p - 1]
        cells.append({"p": p, "card": card, "kind": kind, "x": GEO[p][0], "y": GEO[p][1]})
    over = g.remaining() == 0
    out = {"ok": ok, "message": message, "cells": cells, "aspect": ASPECT, "waste": snap["waste"], "remaining": snap["remaining"],
           "stock": snap["stock_remaining"], "status": ui.status(s), "pending": sorted(pend), "over": over,
           "can_undo": bool(s.history), "can_draw": (not over) and (not pend) and snap["stock_remaining"] > 0,
           "log": s.log[-12:], "advice": advice, "rev": len(s.log)}
    if extra: out.update(extra)
    return out

def _get(sid):
    with _glock:
        e = _sessions.get(sid)
        if e: _sessions.move_to_end(sid)
        return e

@app.get("/", response_class=HTMLResponse)
def index(): return (HERE / "web" / "index.html").read_text(encoding="utf-8")

@app.get("/api/geo")
def api_geo(): return {"geo": {str(k): v for k, v in GEO.items()}, "aspect": ASPECT}

@app.get("/health")
def health(): return {"ok": True, "templates": len(_templates())}

@app.post("/api/new")
def api_new(body: dict):
    try:
        s = ui.new_session(body.get("board", ""), str(body.get("waste", "")).strip(), body.get("stock", 23))
        if not str(body.get("waste", "")).strip(): raise ValueError("Pick the waste card first.")
    except Exception as e: return {"ok": False, "message": str(e)}
    sid = body.get("sid") or uuid.uuid4().hex
    entry = {"s": s, "lock": threading.Lock(), "replies": {}, "advice": None}
    with _glock:
        _sessions[sid] = entry
        while len(_sessions) > MAX_SESSIONS: _sessions.popitem(last=False)
    _precompute(entry)
    r = view(entry); r["sid"] = sid; return r

def _key(game):
    return repr((list(game.board), game.waste, game.stock_remaining, list(getattr(game, "stock", []) or [])))

_pre_sem = threading.Semaphore(1)   # one background solve at a time per process (2 cores)

def _precompute(entry):
    """Start computing the recommendation for the current state in the background."""
    s = entry["s"]
    try:
        if s.game.remaining() == 0 or ui.pending_reveals(s.game): entry["pre"] = None; return
        game = s.game.copy(); key = _key(game)
    except Exception: entry["pre"] = None; return
    cur = entry.get("pre")
    if cur and cur["key"] == key: return
    pre = {"key": key, "done": threading.Event(), "res": None}; entry["pre"] = pre
    def work():
        try:
            with _pre_sem:
                if entry.get("pre") is not pre: pre["done"].set(); return   # superseded before starting
                tmp = ui.Session(game)
                text, pos, proven, rate, sims = ui.recommend_detail(tmp, 1200, None)
                if pos: text = text.replace(f"Play position {pos:02d}.", f"Play the {game.board[pos - 1]} marked with the blue star.")
                fs = None
                try:
                    if pos: fs = ui.foresight_line(tmp, pos)
                except Exception: fs = None
                pre["res"] = {"text": text, "pos": pos, "proven": proven, "rate": rate, "sims": sims, "foresight": fs}
        except Exception: pre["res"] = None
        finally: pre["done"].set()
    threading.Thread(target=work, daemon=True).start()

def _adopt(entry):
    """If the background result matches the current state, show it as the advice."""
    pre = entry.get("pre")
    if pre and pre["done"].is_set() and pre["res"] and not entry.get("advice"):
        try:
            if pre["key"] == _key(entry["s"].game): entry["advice"] = pre["res"]
        except Exception: pass

def _do(entry, op, body):
    s = entry["s"]; msg = ""
    if op == "play":
        before = s.game.board[ui.to_int(body.get("pos"), "Position", 1, 28) - 1]
        ui.do_play(s, body.get("pos")); entry["advice"] = None; msg = s.log[-1]
    elif op == "reveal": ui.do_reveal(s, body.get("pos"), str(body.get("rank", ""))); entry["advice"] = None; msg = s.log[-1]
    elif op == "draw": ui.do_draw(s, str(body.get("rank", ""))); entry["advice"] = None; msg = s.log[-1]
    elif op == "state": msg = ""
    elif op == "undo": s.undo(); entry["advice"] = None; msg = s.log[-1]
    elif op == "recommend":
        pre = entry.get("pre")
        if pre and pre["key"] == _key(s.game):
            pre["done"].wait(40); _adopt(entry)
            if entry.get("advice"): return ""
        text, pos, proven, rate, sims = ui.recommend_detail(s, body.get("sims", 1200), body.get("seed"))
        if pos: text = text.replace(f"Play position {pos:02d}.", f"Play the {s.game.board[pos - 1]} marked with the blue star.")
        fs = None
        try:
            if pos: fs = ui.foresight_line(s, pos)
        except Exception: fs = None
        entry["advice"] = {"text": text, "pos": pos, "proven": proven, "rate": rate, "sims": sims, "foresight": fs}
    else: raise ValueError("Unknown action.")
    if op in ("play", "reveal", "draw", "undo"): _precompute(entry)
    if op == "state": _adopt(entry)
    return msg

@app.post("/api/act")
def api_act(body: dict):
    entry = _get(body.get("sid", ""))
    if not entry: return {"ok": False, "gone": True, "message": "This game expired on the server. Start again."}
    rid = str(body.get("req_id") or uuid.uuid4().hex)
    with _glock:
        cached = entry["replies"].get(rid)
        if cached is None: entry["replies"][rid] = threading.Event()
        while len(entry["replies"]) > 40: entry["replies"].pop(next(iter(entry["replies"])))
    if isinstance(cached, threading.Event): cached.wait(60); cached = entry["replies"].get(rid)
    if isinstance(cached, dict): return cached
    ev = entry["replies"][rid]
    with entry["lock"]:
        try: msg = _do(entry, body.get("op"), body); reply = view(entry, msg)
        except Exception as e: reply = view(entry, str(e), ok=False)
    entry["replies"][rid] = reply; ev.set()
    return reply

def _replay_frames(game, moves):
    """Replay a returned line on a fresh copy and return (frames, texts). Raises ValueError if any step is illegal."""
    g = game.copy(); frames = []; texts = []
    def frame(g, nxt):
        f = view({"s": ui.Session(g.copy()), "advice": None}); f.pop("log", None); f.pop("advice", None)
        f["next"] = nxt; return f
    for mv in moves:
        nxt = mv[1] if mv[0] == "play" else None
        frames.append(frame(g, nxt))
        if mv[0] == "play":
            card = g.play(int(mv[1])); texts.append(f"Play the {card} (position {int(mv[1])})")
        elif mv[0] == "draw":
            if not g.stock: raise ValueError("Line draws from an empty stock.")
            card = g.stock.pop(0); g.waste = card; texts.append(f"Draw from the stock: {card}")
        else: raise ValueError("Unknown step.")
    frames.append(frame(g, None))
    if g.remaining() != 0: raise ValueError("Line does not clear the tableau.")
    return frames, texts

@app.post("/api/solve")
def api_solve(body: dict):
    """Complete-deal mode: every card known, stock order known. Never guesses missing cards."""
    board = str(body.get("board", "")).replace(",", " ").split(); waste = str(body.get("waste", "")).strip()
    raw_stock = body.get("stock")
    if raw_stock is None: raw_stock = []
    if not isinstance(raw_stock, (list, tuple)): return {"ok": False, "message": "Stock must be a list of cards in draw order."}
    stock = [str(x).strip() for x in raw_stock]
    try:
        stock_count = None if body.get("stock_count") is None else ui.to_int(body.get("stock_count"), "Stock count", 0, 23)
        budget_in = float(body.get("time_budget", 20))
    except Exception as e: return {"ok": False, "message": str(e) if "Stock count" in str(e) else "Time budget must be a number."}
    missing = []
    if len(board) != 28: return {"ok": False, "message": f"Need 28 board entries, got {len(board)}."}
    missing += [f"tableau position {i}" for i, c in enumerate(board, 1) if c == "?"]
    if not waste: missing.append("waste card")
    if stock_count is not None and stock_count != len(stock): missing.append(f"stock order ({len(stock)} of {stock_count} cards entered)")
    if missing:
        return {"ok": True, "status": "incomplete", "message": "The deal is not complete, so I will not guess. Missing: " + ", ".join(missing[:12]) + (" ..." if len(missing) > 12 else "") + ".", "missing": missing}
    try: game = solver.Game(board, waste, True, stock)
    except Exception as e: return {"ok": False, "message": str(e)}
    fn = getattr(solver, "solve_complete", None)
    if fn is None: return {"ok": True, "status": "unavailable", "message": "The exact solver is not installed in this build yet."}
    budget = max(0.5, min(budget_in, 25))
    def run(stuck, share):
        return fn(game.copy(), time_budget=budget * share, require_full_deal=True, draw_only_when_stuck=stuck)
    try:
        res = run(True, 0.5); policy = "stuck"
        if res.status in ("unsolvable", "unknown"):
            res2 = run(False, 0.5)
            if res2.status == "solved": res, policy = res2, "voluntary"
            elif res.status == "unsolvable" and res2.status == "unsolvable": policy = "both"
            elif res.status == "unsolvable": res = res2; policy = "voluntary"   # voluntary undecided: say so below
            elif res2.status == "unsolvable": policy = "both"                    # voluntary unsolvable implies stuck-only unsolvable
    except Exception as e: return {"ok": False, "message": f"Solver error: {e}"}
    out = {"ok": True, "status": res.status, "policy": policy, "nodes": getattr(res, "nodes", None), "seconds": getattr(res, "seconds", None)}
    if res.status == "solved":
        try: frames, texts = _replay_frames(game, list(res.moves))
        except Exception as e: return {"ok": False, "message": f"Solver returned a line that failed verification ({e}). Not shown."}
        note = ("Valid whether or not the machine lets you draw while a play is available." if policy == "stuck" else
                "Only works if the machine lets you draw while a play is available (not verified).")
        out.update(message=f"Solved in {len(texts)} steps (line verified by replay). {note}", steps=texts, frames=frames)
    elif res.status == "unsolvable" and policy == "both": out["message"] = "Proven unsolvable under both draw rules: the search was exhaustive and no winning line exists."
    elif res.status == "unsolvable": out["message"] = "No line wins if you may only draw when no play is available. Whether voluntary draws would help was not decided, so this is NOT a full proof."; out["status"] = "unknown"
    elif res.status == "unknown": out["message"] = f"Could not decide in the time limit ({getattr(res, 'reason', 'timeout')}). This is NOT a proof that it is unsolvable."
    else: out["message"] = "The deal is not valid or complete for the solver: " + str(getattr(res, "reason", ""))
    return out

@app.post("/api/photo")
def api_photo(file: UploadFile = File(...), corners: str = Form("")):
    """Read a photo or screenshot into a draft board. Sync on purpose: the work is CPU-bound, so it runs in the
    thread pool instead of blocking the event loop. Never guesses: unread or uncertain cards come back as '?'."""
    import base64, io
    from tritowers_vision.image import MAX_BYTES, ImageInputError
    from tritowers_vision.reader import board_tokens, read_photo
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES: return {"ok": False, "message": f"Image is too large ({MAX_BYTES // (1024 * 1024)} MB max)."}
    manual = None
    if corners.strip():
        try: nums = [float(x) for x in corners.replace(";", ",").split(",") if x.strip()]
        except ValueError: return {"ok": False, "message": "Corners need 8 numbers."}
        if len(nums) != 8: return {"ok": False, "message": "Corners need 8 numbers."}
        manual = [(nums[i], nums[i + 1]) for i in range(0, 8, 2)]
    try:
        r = read_photo(data, _templates(), manual)
    except (ImageInputError, ValueError) as e:
        return {"ok": False, "message": f"Could not read that image: {e}"}
    d = r.draft; tokens, waste = board_tokens(d)
    review = [s.replace("tableau-", "").lstrip("0") if s != "waste" else "waste" for s in d["needs_human_review"]]
    if not d["registration"]["trusted"]:
        note = "The card layout was not found reliably, so check every card (a straighter photo of the whole screen helps). "
    else:
        note = ("Check: " + ", ".join(review) + ". " if review else "")
    note += "Suit and the stock counter are not read: set the stock yourself. Check the picture before you start."
    view = r.overlay.copy(); view.thumbnail((900, 900))
    buf = io.BytesIO(); view.save(buf, format="JPEG", quality=80)
    return {"ok": True, "board": tokens, "waste": waste, "note": note, "review": review,
            "trusted": d["registration"]["trusted"], "overlay": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "7860")), log_level="warning")
