import random, unittest
import solver
from solver import Game, solve_complete

def verify(board, waste, stock, moves):
    """Replay on a fresh Game via the public play/draw_known path."""
    g = Game(board, waste, True, list(stock))
    for m in moves:
        if m[0] == "draw": g.draw_known()
        else: g.play(m[1])
    return g.remaining() == 0

def deals(seed, k):
    rnd = random.Random(seed)
    for _ in range(k):
        d = [r for r in solver.RANKS for _ in range(4)]; rnd.shuffle(d)
        yield d[:28], d[28], d[29:]

UNSOLV = (['5','10','Q','Q','2','5','10','5','5','9','6','7','8','8','3','3','4','10','4','A','6','8','9','A','Q','K','4','J'], 'K',
 ['6','3','2','7','K','J','6','J','9','4','9','A','10','7','2','A','3','Q','J','7','2','K','8'])

class T(unittest.TestCase):
    def test_solved_replays_independently(self):
        n = 0
        for b, w, s in deals(7, 20):
            r = solve_complete(Game(b, w, True, s))
            self.assertIn(r.status, ("solved", "unsolvable"))
            if r.status == "solved":
                n += 1; self.assertTrue(verify(b, w, s, r.moves))
        self.assertGreater(n, 10)
    def test_unsolvable_proven(self):
        self.assertEqual(solve_complete(Game(UNSOLV[0], UNSOLV[1], True, UNSOLV[2])).status, "unsolvable")
    def test_budget_is_unknown_not_unsolvable(self):
        r = solve_complete(Game(UNSOLV[0], UNSOLV[1], True, UNSOLV[2]), max_nodes=5)
        self.assertEqual((r.status, r.reason, r.moves), ("unknown", "node_limit", []))
        r = solve_complete(Game(UNSOLV[0], UNSOLV[1], True, UNSOLV[2]), time_budget=0.0)
        self.assertEqual((r.status, r.reason), ("unknown", "timeout"))
    def test_incomplete_is_unknown(self):
        b, w, s = next(deals(1, 1))
        self.assertEqual(solve_complete(Game(["?"]+b[1:], w, True, s)).status, "incomplete")
        self.assertEqual(solve_complete(Game(b, w, False, 23)).status, "incomplete")
    def test_zero_budget_and_memo_limit(self):
        b, w, s = UNSOLV
        self.assertEqual(solve_complete(Game(b, w, True, s), time_budget=0).reason, "timeout")
        r = solve_complete(Game(b, w, True, s), max_memo=3)
        self.assertEqual((r.status, r.reason), ("unknown", "memory_limit"))
    def test_all_removed_and_list_moves(self):
        r = solve_complete(Game(["--"] * 28, "5", True, []))
        self.assertEqual((r.status, r.moves), ("solved", []))
        b, w, s = next(deals(7, 1)); r = solve_complete(Game(b, w, True, s))
        self.assertIsInstance(r.moves, list)
    def test_observe_draw_rejects_known(self):
        b, w, s = next(deals(2, 1))
        with self.assertRaises(ValueError): Game(b, w, True, s).observe_draw("5")
    def test_mutated_invalid_game_is_incomplete_never_unsolvable(self):
        b, w, s = next(deals(7, 1))
        def fresh(): return Game(b, w, True, s)
        g = fresh(); g.board[:5] = ["K"] * 5
        r = solve_complete(g); self.assertEqual(r.status, "incomplete"); self.assertTrue(r.reason.startswith("invalid_deal"))
        for mark in ("?", "--", "Z"):
            g = fresh(); g.stock[0] = mark
            self.assertEqual(solve_complete(g).status, "incomplete")
        g = fresh(); g.waste = "?"
        self.assertEqual(solve_complete(g).status, "incomplete")
        g = fresh(); g.board[3] = "--"          # cleared but not in removed
        self.assertEqual(solve_complete(g).status, "incomplete")
    def test_waste_none_and_removed_consistency(self):
        b, w, s = next(deals(7, 1))
        g = Game(b, w, True, s); g.waste = None
        self.assertEqual(solve_complete(g).status, "incomplete")
        g = Game(b, w, True, s); g.removed.add(1)          # card still covered
        self.assertEqual(solve_complete(g).status, "incomplete")
        g = Game(b, w, True, s); g.removed.add(99)
        self.assertEqual(solve_complete(g).status, "incomplete")
    def test_midgame_position_and_full_deal_flag(self):
        b, w, s = next(deals(7, 1)); g = Game(b, w, True, s)
        first = solve_complete(g)
        self.assertEqual(first.status, "solved")
        step = next(m for m in first.moves if m[0] == "play")
        # replay up to and including the first play, then solve the remaining position
        h = Game(b, w, True, s)
        for m in first.moves:
            h.draw_known() if m[0] == "draw" else h.play(m[1])
            if m is step: break
        r = solve_complete(h); self.assertEqual(r.status, "solved")
        self.assertEqual(solve_complete(h, require_full_deal=True).reason, "not_full_deal")
        self.assertEqual(solve_complete(g, require_full_deal=True).status, "solved")
    def test_draw_policy_is_explicit(self):
        n_any = n_stuck = 0
        for b, w, s in deals(11, 40):
            a = solve_complete(Game(b, w, True, s), draw_only_when_stuck=False).status
            c = solve_complete(Game(b, w, True, s)).status
            if a == "solved": n_any += 1
            if c == "solved":
                n_stuck += 1; self.assertEqual(a, "solved")   # strict-legal implies permissive-legal
        self.assertGreaterEqual(n_any, n_stuck)
    def test_stuck_only_replay_never_draws_with_playable(self):
        for b, w, s in deals(5, 15):
            r = solve_complete(Game(b, w, True, s)); 
            if r.status != "solved": continue
            g = Game(b, w, True, s)
            for m in r.moves:
                if m[0] == "draw": self.assertEqual(g.legal_moves(), []); g.draw_known()
                else: g.play(m[1])
    def test_every_prefix_position_stays_solved(self):
        for b, w, s in deals(3, 6):
            r = solve_complete(Game(b, w, True, s))
            if r.status != "solved": continue
            h = Game(b, w, True, s)
            for m in r.moves:
                h.draw_known() if m[0] == "draw" else h.play(m[1])
                rest = solve_complete(h)
                self.assertEqual(rest.status, "solved", (m, rest.reason))
    def test_none_and_wrong_type_fields_are_incomplete(self):
        b, w, s = next(deals(7, 1))
        for field, val in (("removed", None), ("board", None), ("stock", None), ("stock", 5), ("removed", 7), ("board", [None] * 28), ("stock_known", None)):
            g = Game(b, w, True, s); setattr(g, field, val)
            r = solve_complete(g)
            self.assertIn(r.status, ("incomplete",), (field, val, r))
    def test_draw_known(self):
        b, w, s = next(deals(2, 1)); g = Game(b, w, True, s)
        self.assertEqual(g.draw_known(), s[0]); self.assertEqual(g.waste, s[0]); self.assertEqual(len(g.stock), 22)
        e = Game(b, w, True, []);
        with self.assertRaises(ValueError): e.draw_known()
    def test_does_not_mutate(self):
        b, w, s = next(deals(3, 1)); g = Game(b, w, True, s); snap = g.state_snapshot()
        solve_complete(g); self.assertEqual(g.state_snapshot(), snap)

class Joker(unittest.TestCase):
    # Joker rules are Bill-reported (relayed), model only; not machine-verified.
    def deal(self, seed=7):
        b, w, s = next(deals(seed, 1)); return b, w, s + ["*"]
    def test_can_play_wild(self):
        self.assertTrue(solver.can_play("7", "*")); self.assertFalse(solver.can_play("*", "7"))
    def test_no_joker_unchanged(self):
        for b, w, s in deals(9, 6):
            self.assertEqual(solve_complete(Game(b, w, True, s)).moves, solve_complete(Game(b, w, True, s), require_full_deal=True).moves)
    def test_joker_validation(self):
        b, w, s = self.deal()
        Game(b, w, True, s)
        with self.assertRaises(ValueError): Game(b, w, True, ["*"] + s[:-1])           # not last
        with self.assertRaises(ValueError): Game(b, w, True, s[:5] + ["*"] + s[5:])     # not last
        with self.assertRaises(ValueError): Game(["*"] + b[1:], w, True, s)            # on board
        with self.assertRaises(ValueError): Game(b, "*", True, s)                      # two jokers
        with self.assertRaises(ValueError): Game(b, w, False, 23).board.__setitem__(0, "*") or Game(["*"] + b[1:], w, False, 23)
    def test_solved_replays_with_joker_and_flags(self):
        n = 0
        for seed in range(1, 8):
            b, w, s = self.deal(seed); g = Game(b, w, True, s)
            r = solve_complete(g, require_full_deal=True, require_joker=True)
            self.assertIn(r.status, ("solved", "unsolvable"))
            if r.status == "solved": n += 1; self.assertTrue(verify(b, w, s, r.moves))
        self.assertGreater(n, 3)
    def test_joker_flags(self):
        b, w, s = next(deals(7, 1))
        self.assertEqual(solve_complete(Game(b, w, True, s), require_joker=True).reason, "joker_missing")
        self.assertEqual(solve_complete(Game(b, w, True, s + ["*"]), require_full_deal=True).status in ("solved", "unsolvable"), True)
        self.assertEqual(solve_complete(Game(b, w, True, s[:-1] + ["*"]), require_full_deal=True).reason, "not_full_deal")
    def test_joker_draw_then_any_card_then_replacement(self):
        # joker drawn: any exposed card can be played onto it, and the played card becomes the waste
        b = ["K"] * 4 + ["Q"] * 4 + ["J"] * 4 + ["10"] * 4 + ["9"] * 4 + ["8"] * 4 + ["7"] * 4
        g = Game(b, "2", True, ["*"]); g.draw_known(); self.assertEqual(g.waste, "*")
        self.assertEqual(len(g.legal_moves()), len(g.exposed()))
        p = g.legal_moves()[0]; g.play(p); self.assertEqual(g.waste, g.board[p - 1])
    def test_joker_is_last_so_stock_empty_continues_play(self):
        # after the joker is drawn the stock is empty but legal board moves must still count
        b, w, s = self.deal(2); g = Game(b, w, True, s)
        while g.stock: g.draw_known()
        self.assertEqual(g.waste, "*"); self.assertEqual(g.stock, [])
        r = solve_complete(g); self.assertNotEqual(r.status, "incomplete")
    def test_mutated_second_joker_is_incomplete(self):
        b, w, s = self.deal(); g = Game(b, w, True, s); g.waste = "*"
        self.assertEqual(solve_complete(g).status, "incomplete")
if __name__ == "__main__": unittest.main()
