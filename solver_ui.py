"""Friendly Gradio front end for the rank-only solver. Rules stay in solver.py; this only presents them."""
import random, html
import solver
ROWS = ((1, 2, 3), tuple(range(4, 10)), tuple(range(10, 19)), tuple(range(19, 29)))

class Session:
    def __init__(self, game): self.game, self.history, self.log = game, [], []
    def checkpoint(self): self.history.append(self.game.copy())
    def undo(self):
        if not self.history: raise ValueError("Nothing to undo.")
        self.game = self.history.pop(); self.log.append("Undid last action.")

def to_int(value, name, lo=None, hi=None):
    """Strict integer: rejects fractions, bools, blanks, text. 23.0 is accepted, 23.9 is not."""
    if isinstance(value, bool) or value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{name} must be a whole number.")
    try:
        f = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a whole number.")
    if f != f or f in (float("inf"), float("-inf")) or f != int(f):
        raise ValueError(f"{name} must be a whole number, got {value}.")
    n = int(f)
    if lo is not None and n < lo or hi is not None and n > hi:
        raise ValueError(f"{name} must be between {lo} and {hi}, got {n}.")
    return n

MAX_STOCK = 23
RECOMMEND_TIME_BUDGET = 20.0

def guard_open(session, need_no_reveals=True):
    g = session.game
    if g.remaining() == 0: raise ValueError("Tableau is cleared: the game is over.")
    if need_no_reveals and pending_reveals(g): raise ValueError("Reveal the yellow ? cards first.")

def parse_board(text):
    tokens = [t for t in text.replace(",", " ").split() if t]
    if len(tokens) != 28: raise ValueError(f"Need 28 board entries (positions 1-28), got {len(tokens)}. Use ? for a covered card and -- for an empty slot.")
    return tokens

def new_session(board_text, waste, stock):
    board = parse_board(board_text)
    stock = to_int(stock, "Stock", 0, MAX_STOCK)
    return Session(solver.Game(board, waste, False, stock))

def pending_reveals(game):
    return [p for p in game.exposed() if game.board[p - 1] == "?"]

def render_board(session):
    g = session.game; s = g.state_snapshot(); exposed = set(g.exposed()); legal = set(g.legal_moves()); reveals = set(pending_reveals(g))
    def cell(p):
        card = "" if p in s["removed"] else s["board"][p - 1]
        if p in s["removed"]: cls, label = "gone", ""
        elif card == "?": cls, label = ("ask" if p in reveals else "back"), ("?" if p in reveals else "")
        else: cls, label = ("play" if p in legal else "up" if p in exposed else "blocked"), html.escape(card)
        return f'<div class="c {cls}"><small>{p}</small>{label}</div>'
    W, H, XU, YU = 52, 68, 58, 76
    xs = {p: float(p - 19) for p in range(19, 29)}
    for p in sorted(solver.BLOCKERS, reverse=True): xs[p] = sum(xs[b] for b in solver.BLOCKERS[p]) / 2
    ys = {p: next(i for i, row in enumerate(ROWS) if p in row) for p in range(1, 29)}
    cells = "".join(cell(p).replace('<div class="c ', f'<div style="left:{xs[p]*XU:.0f}px;top:{ys[p]*YU}px" class="c ', 1) for p in range(1, 29))
    rows = f'<div class="towers" style="position:relative;width:{9*XU+W}px;height:{3*YU+H}px;margin:0 auto">{cells}</div>'
    css = ("<style>.c{position:absolute;width:52px;height:68px;border-radius:6px;border:1px solid #888;display:flex;"
           "flex-direction:column;align-items:center;justify-content:center;font:700 20px sans-serif}.c small{position:absolute;top:2px;left:4px;font:10px sans-serif;opacity:.6}"
           ".gone{border-style:dashed;opacity:.25}.back{background:#a33;color:#fff}.ask{background:#fc6;color:#000}.up{background:#f6f1e3;color:#222}.play{background:#cfe9c8;color:#111;border:2px solid #2a7}.blocked{background:#ddd;color:#555}</style>")
    foot = (f'<div style="text-align:center;margin-top:8px">Waste <b>{s["waste"]}</b> &nbsp;|&nbsp; Tableau left <b>{s["remaining"]}</b> &nbsp;|&nbsp; Stock left <b>{s["stock_remaining"]}</b></div>'
            '<div style="text-align:center;font-size:12px;opacity:.7">green = playable now, yellow ? = tell me this card, red = still covered</div>')
    return css + rows + foot

def status(session):
    g = session.game; need = pending_reveals(g)
    if need: return "Reveal needed: " + ", ".join(f"{p:02d}" for p in need)
    if g.remaining() == 0: return "Tableau cleared."
    if not g.legal_moves(): return "No playable card. Draw from the stock." if g.stock_remaining > 0 else "No moves and the stock is empty."
    return "Ready for a recommendation."

def recommend(session, simulations=solver.SIMULATIONS, seed=None):
    guard_open(session)
    sims = to_int(simulations, "Simulations", 1, 100000)
    rng = random.Random(to_int(seed, "Seed")) if seed not in (None, "") else None
    rec = solver.best_move(session.game, simulations=sims, rng=rng, time_budget=RECOMMEND_TIME_BUDGET)
    if rec is None: return "No legal move: draw from the stock." if session.game.stock_remaining else "No legal move and stock empty."
    if rec.is_proven: return f"Play position {rec.position:02d}. Proven: this move is guaranteed by the known cards."
    return f"Play position {rec.position:02d}. Sampled estimate {rec.success_rate:.0%} over {rec.simulations} simulations. This is an estimate, not a proof."

def do_play(session, position):
    position = to_int(position, "Position", 1, 28); guard_open(session)
    session.checkpoint()
    try: card = session.game.play(int(position))
    except Exception: session.history.pop(); raise
    session.log.append(f"Played {int(position):02d} ({card}).")

def do_reveal(session, position, rank):
    position = to_int(position, "Position", 1, 28)
    if position not in pending_reveals(session.game): raise ValueError(f"Position {position:02d} is not waiting for a reveal.")
    session.checkpoint()
    try: card = session.game.observe_rank(rank); session.game.board[position - 1] = card
    except Exception: session.history.pop(); raise
    session.log.append(f"Revealed {position:02d} = {card}.")

def do_draw(session, rank):
    guard_open(session)
    if session.game.stock_empty: raise ValueError("Stock is empty.")
    session.checkpoint()
    try: session.game.observe_draw(rank)
    except Exception: session.history.pop(); raise
    session.log.append(f"Drew {session.game.waste}.")
