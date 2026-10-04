"""Baseline adapter invariants; proposed unknown-tail tests await agreed Game API."""
from collections import Counter
import random

import solver
import solver_ui as ui


def fresh(seed=1):
    deck = [r for r in solver.RANKS for _ in range(4)]
    random.Random(seed).shuffle(deck)
    return deck[:28], deck[28], deck[29:]


def test_known_joker_completion_preserves_tail_without_duplicate():
    board, waste, stock = fresh()
    board[:18] = ['?'] * 18
    game = solver.Game(board, waste, True, stock + ['*'])
    snap = game.state_snapshot()
    hidden = [i for i, card in enumerate(board) if card == '?']
    for seed in range(40):
        comp = ui._completion(game, game.unknown_card_pool(), hidden, random.Random(seed))
        assert comp.stock == stock + ['*']
        assert '*' not in comp.board
        assert comp.stock.count('*') == 1
        assert Counter(comp.board + [comp.waste] + comp.stock[:-1]) == Counter({r: 4 for r in solver.RANKS})
    assert game.state_snapshot() == snap


def test_legacy_unknown_stock_completion_conserves_normal_deck():
    board, waste, stock = fresh()
    board[:18] = ['?'] * 18
    game = solver.Game(board, waste, False, len(stock))
    hidden = list(range(18))
    snap = game.state_snapshot()
    pool = game.unknown_card_pool()
    for seed in range(40):
        comp = ui._completion(game, pool, hidden, random.Random(seed))
        assert comp.stock_known and len(comp.stock) == 23
        assert '*' not in comp.board + comp.stock
        assert Counter(comp.board + [comp.waste] + comp.stock) == Counter({r: 4 for r in solver.RANKS})
    assert game.state_snapshot() == snap


def test_estimator_rejects_inconsistent_unseen_slot_count():
    board, waste, stock = fresh()
    game = solver.Game(board, waste, False, len(stock) - 1)
    assert ui.estimate_moves(game, game.legal_moves(), samples=1) is None


def test_estimator_receives_known_joker_completions(monkeypatch):
    board, waste, stock = fresh()
    game = solver.Game(board, waste, True, stock + ['*'])
    seen = []
    def fake(comp, **kwargs):
        seen.append(comp)
        assert comp.stock[-1] == '*'
        assert comp.stock.count('*') == 1
        assert kwargs['draw_only_when_stuck']
        return solver.SolveResult('unknown', [], 'timeout', 0, 0.0)
    monkeypatch.setattr(solver, 'solve_complete', fake)
    moves = game.legal_moves()
    assert moves
    stats = ui.estimate_moves(game, moves, samples=1, budget=0)
    assert len(seen) == len(moves)
    assert all(s['unknown'] == 1 and s['won'] == 0 and s['n'] == 1 for s in stats.values())
