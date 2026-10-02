"""Tests for Game.stock_empty (#19): one answer for both stock modes."""
import random
import unittest

import solver
from tools import heuristic_baseline as hb


def make_game(known, stock):
    board, waste, full_stock = hb.deal(random.Random(3))
    if known:
        return solver.Game(board, waste, True, stock)
    return solver.Game(board, waste, False, stock)


class StockEmptyTests(unittest.TestCase):
    def test_known_stock(self):
        full = hb.deal(random.Random(3))[2]
        self.assertFalse(make_game(True, full).stock_empty)
        game = make_game(True, full)
        game.stock.clear()
        self.assertTrue(game.stock_empty)

    def test_unknown_stock_counts(self):
        self.assertFalse(make_game(False, 23).stock_empty)
        self.assertFalse(make_game(False, 1).stock_empty)
        self.assertTrue(make_game(False, 0).stock_empty)

    def test_matches_old_four_line_condition(self):
        full = hb.deal(random.Random(3))[2]
        for known, stock in ((True, list(full)), (True, []), (False, 5), (False, 0)):
            game = make_game(known, stock)
            old = (game.stock_known and not game.stock) or (
                not game.stock_known and game.stock <= 0
            )
            self.assertEqual(game.stock_empty, old)

    def test_observe_draw_refuses_empty_unknown_stock(self):
        game = make_game(False, 0)
        with self.assertRaises(ValueError):
            game.observe_draw("A")

    def test_count_never_goes_negative(self):
        game = make_game(False, 1)
        game.observe_draw(next(c for c in solver.RANKS if game.seen_counts[c] < 4))
        self.assertEqual(game.stock_remaining, 0)
        self.assertTrue(game.stock_empty)
        with self.assertRaises(ValueError):
            game.observe_draw("A")
        self.assertEqual(game.stock_remaining, 0)

    def test_draw_returns_false_when_empty(self):
        self.assertFalse(solver.draw(make_game(False, 0), read_card=lambda _: "A", emit=lambda *_: None))
        self.assertFalse(solver.draw(make_game(True, []), emit=lambda *_: None))


if __name__ == "__main__":
    unittest.main()
