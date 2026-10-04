"""Hidden-joker adapter integration on the real Game/solver APIs."""
from collections import Counter
import random
import pytest
import solver
import solver_ui as ui
import tritowers_cli as cli
def fresh(seed=1):
    deck = [r for r in solver.RANKS for _ in range(4)]
    random.Random(seed).shuffle(deck)
    return deck[:28], deck[28], deck[29:]


def hidden_game():
    board, waste, stock = fresh()
    return solver.Game(['?'] * 18 + board[18:], waste, False, 24, joker_in_stock=True)


def test_opt_in_session_includes_joker_in_counter():
    board, waste, _ = fresh()
    text = ' '.join(['?'] * 18 + board[18:])
    s = ui.new_session(text, waste, 24, joker=True)
    assert s.game.joker_in_stock and s.game.stock_remaining == 24
    with pytest.raises(ValueError): ui.new_session(text, waste, 24)
    for invalid in (25, -1, 24.5, True):
        with pytest.raises(ValueError): ui.new_session(text, waste, invalid, joker=True)


def test_sampled_completion_places_joker_only_at_tail():
    game = hidden_game()
    pool = game.unknown_card_pool()
    assert '*' not in pool
    assert len(pool) == 18 + 24 - 1
    snap = game.state_snapshot()
    for seed in range(80):
        comp = ui._completion(game, pool, list(range(18)), random.Random(seed))
        assert comp.stock_known and not comp.joker_in_stock
        assert len(comp.stock) == 24 and comp.stock[-1] == '*'
        assert comp.stock.count('*') == 1 and '*' not in comp.board
        assert Counter(comp.board + [comp.waste] + comp.stock[:-1]) == Counter({r: 4 for r in solver.RANKS})
        while not comp.stock_empty: comp.draw_known()
        assert comp.waste == '*'
        assert comp.legal_moves()
        pos = comp.legal_moves()[0]
        comp.play(pos)
        assert comp.waste == comp.board[pos - 1]
    assert game.state_snapshot() == snap
    assert pool == game.unknown_card_pool()


def test_estimator_counts_reserved_slot_and_keeps_unknown_samples(monkeypatch):
    game = hidden_game()
    moves = game.legal_moves()
    assert moves
    seen = []
    def fake(comp, **kwargs):
        seen.append(comp)
        assert comp.stock_known and not comp.joker_in_stock
        assert comp.stock[-1] == '*' and len(comp.stock) == 24
        return solver.SolveResult('unknown', [], 'timeout', 0, 0.0)
    monkeypatch.setattr(solver, 'solve_complete', fake)
    stats = ui.estimate_moves(game, moves, samples=2, budget=0, rng=random.Random(2))
    assert stats is not None and len(seen) == 2 * len(moves)
    assert all(s['n'] == 2 and s['unknown'] == 2 and s['won'] == 0 for s in stats.values())
    game.stock -= 1
    assert ui.estimate_moves(game, moves, samples=1) is None


def test_final_joker_adapter_draw_and_undo():
    board, waste, stock = fresh()
    s = ui.new_session(' '.join(board), waste, 24, joker=True)
    for card in stock: ui.do_draw(s, card)
    assert s.game.stock_remaining == 1 and s.game.joker_in_stock
    before = s.game.state_snapshot()
    history_len = len(s.history)
    with pytest.raises(ValueError): ui.do_draw(s, 'A')
    assert s.game.state_snapshot() == before and len(s.history) == history_len
    ui.do_draw(s, '*')
    assert s.game.stock_empty and s.game.waste == '*' and not s.game.joker_in_stock
    assert s.game.legal_moves()
    s.undo()
    assert s.game.state_snapshot() == before


def test_early_joker_rejected_without_state_change():
    game = hidden_game()
    s = ui.Session(game)
    before = game.state_snapshot()
    with pytest.raises(ValueError): ui.do_draw(s, '*')
    assert game.state_snapshot() == before and not s.history


def test_cli_undo_preserves_reserved_joker():
    board, waste, stock = fresh()
    game = solver.Game(board, waste, False, 24, joker_in_stock=True)
    for card in stock: game.observe_draw(card)
    history = cli.UndoHistory()
    history.checkpoint(game)
    game.observe_draw('*')
    restored = history.undo()
    assert restored.joker_in_stock and restored.stock_remaining == 1
    assert restored.waste != '*'
    assert restored.state_snapshot()['joker_in_stock'] is True


def test_session_rejects_nonboolean_mode():
    board, waste, _ = fresh()
    for bad in ('false', 'true', 1, 0, None):
        with pytest.raises(ValueError): ui.new_session(' '.join(board), waste, 23, joker=bad)


def test_final_joker_completion_with_no_unseen_ranks():
    board, waste, stock = fresh()
    game = solver.Game(board, waste, False, 24, joker_in_stock=True)
    for card in stock: game.observe_draw(card)
    assert game.unknown_card_pool() == []
    comp = ui._completion(game, [], [], random.Random(1))
    assert comp.stock == ['*'] and comp.stock_known and not comp.joker_in_stock
    comp.draw_known()
    assert comp.waste == '*' and comp.legal_moves()
    # Unknown/timeout is still an honest result if this exact solver is budget-limited.
    result = solver.solve_complete(comp, time_budget=0.2)
    assert result.status in ('solved', 'unsolvable', 'unknown')


def test_completed_hidden_joker_deal_exact_solver_replay():
    game = hidden_game()
    comp = ui._completion(game, game.unknown_card_pool(), list(range(18)), random.Random(1))
    result = solver.solve_complete(comp, time_budget=2, require_full_deal=True, require_joker=True)
    assert result.status in ('solved', 'unsolvable', 'unknown')
    assert result.status != 'incomplete'
    if result.status == 'solved':
        replay = comp.copy()
        for move in result.moves:
            if move[0] == 'draw': replay.draw_known()
            else: replay.play(move[1])
        assert replay.remaining() == 0


def test_cli_display_includes_reserved_tail_but_not_legacy():
    game = hidden_game()
    assert 'Stock: 24' in cli.format_board(game)
    assert 'includes the joker' in cli.format_board(game)
    game.joker_in_stock = False
    assert 'includes the joker' not in cli.format_board(game)
