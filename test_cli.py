import argparse
import unittest

import solver
from tools import heuristic_baseline as hb
import tritowers_cli as cli


class CliTests(unittest.TestCase):
    def test_parser_exposes_seed_budget_and_tutorial_switch(self):
        args = cli.build_parser().parse_args(["--seed", "4", "--simulations", "25", "--skip-tutorial"])
        self.assertEqual((args.seed, args.simulations, args.skip_tutorial), (4, 25, True))

    def test_parser_rejects_nonpositive_simulation_budget(self):
        with self.assertRaises(SystemExit):
            cli.build_parser().parse_args(["--simulations", "0"])

    def test_board_display_uses_snapshot_and_counts(self):
        board = ["?"] * solver.TOTAL_TABLEAU
        board[18] = "2"
        game = solver.Game(board, "A", False, 3)
        text = cli.format_board(game)
        self.assertIn("19: 2", text)
        self.assertIn("Waste: A", text)
        self.assertIn("Tableau: 28", text)
        self.assertIn("Stock: 3", text)

    def test_undo_returns_independent_prior_state(self):
        board = ["--"] * solver.TOTAL_TABLEAU
        board[0] = "2"
        game = solver.Game(board, "A", False, 0)
        history = cli.UndoHistory()
        history.checkpoint(game)
        game.play(1)
        restored = history.undo()
        self.assertEqual(restored.waste, "A")
        self.assertNotIn(1, restored.removed)

    def test_eof_is_clean_stop(self):
        def eof(_):
            raise EOFError
        with self.assertRaises(SystemExit):
            cli.read_rank_or_command("> ", input_fn=eof)

    def test_commands_are_distinct_from_card_ranks(self):
        self.assertEqual(cli.read_rank_or_command("> ", input_fn=lambda _: "undo"), "UNDO")
        self.assertEqual(cli.read_rank_or_command("> ", input_fn=lambda _: "q"), "Q")
        self.assertEqual(cli.read_rank_or_command("> ", input_fn=lambda _: "a"), "A")


class UndoWiringTests(unittest.TestCase):
    def test_rewind_goes_to_start_of_previous_step(self):
        h = cli.UndoHistory()
        g1, g2 = solver.Game.__new__(solver.Game), solver.Game.__new__(solver.Game)
        h._states = [g1, g2]  # g2 = start of the step in progress
        self.assertIs(solver.rewind(h), g1)

    def test_rewind_with_no_earlier_step_restarts_current(self):
        h = cli.UndoHistory()
        g = solver.Game.__new__(solver.Game)
        h._states = [g]
        self.assertIs(solver.rewind(h), g)

    def test_rewind_restores_sampler_state(self):
        import random
        rng = random.Random(5)
        board, waste, stock = hb.deal(random.Random(3))
        game = solver.Game(board, waste, True, stock)
        h = cli.UndoHistory()
        h.checkpoint(game)
        h._states[-1].rng_state = rng.getstate()
        expected = rng.random()
        rng.random(); rng.random()
        solver.rewind(h, rng)
        self.assertEqual(rng.random(), expected)

    def test_review_setup_corrects_and_rejects(self):
        import random
        board, waste, stock = hb.deal(random.Random(3))
        partial = ["?"] * 18 + board[18:]  # bottom row only: a typo is not caught by the deck check
        game = solver.Game(partial, waste, True, stock)
        wrong = "2" if board[18] != "2" else "3"
        answers = iter([f"fix 19 {wrong}", "fix 99 K", "fix 19 Z", "bogus", f"fix 19 {board[18]}", ""])
        out = []
        fixed = solver.review_setup(game, read_line=lambda p: next(answers),
                                    emit=lambda *a: out.append(" ".join(map(str, a))))
        self.assertEqual(fixed.board[18], board[18])
        self.assertEqual(sum("Not changed" in o for o in out), 3)
        self.assertTrue(any(f"19:{wrong:>2}" in o for o in out))  # typo shown before the fix
        self.assertEqual(game.board[18], board[18])  # original object untouched

    def test_review_setup_rejects_a_fix_that_breaks_the_deck(self):
        import random
        board, waste, stock = hb.deal(random.Random(3))
        game = solver.Game(board, waste, True, stock)
        other = next(r for r in solver.RANKS if r != board[0])
        answers = iter([f"fix 1 {other}", ""])
        out = []
        fixed = solver.review_setup(game, read_line=lambda p: next(answers),
                                    emit=lambda *a: out.append(" ".join(map(str, a))))
        self.assertIs(fixed, game)
        self.assertTrue(any("Not changed" in o for o in out))

    def test_review_setup_enter_and_eof_start_the_game(self):
        import random
        board, waste, stock = hb.deal(random.Random(3))
        game = solver.Game(board, waste, True, stock)
        self.assertIs(solver.review_setup(game, read_line=lambda p: "", emit=lambda *a: None), game)
        def eof(p):
            raise EOFError
        self.assertIs(solver.review_setup(game, read_line=eof, emit=lambda *a: None), game)

    def test_overfull_report_names_every_place(self):
        board = ["K"] * 5 + ["?"] * 23
        report = solver.overfull_report(board, "2", True, ["3"])
        self.assertEqual(len(report), 1)
        self.assertIn("K was entered 5 times", report[0])
        self.assertIn("position 05", report[0])
        self.assertEqual(solver.overfull_report(["K"] * 4 + ["?"] * 24, "2", False, 23), [])

    def test_repair_entry_corrects_in_place_and_rejects_bad_fix(self):
        import random
        board, waste, stock = hb.deal(random.Random(3))
        other = next(r for r in solver.RANKS if r != board[0])
        typo = [other] + board[1:]
        answers = iter(["", "fix 99 K", f"fix 1 {board[0]}"])
        out = []
        game = solver.repair_entry(typo, waste, True, stock,
                                   read_line=lambda p: next(answers),
                                   emit=lambda *a: out.append(" ".join(map(str, a))))
        self.assertEqual(game.board[0], board[0])
        self.assertTrue(any("Not changed" in o for o in out))
        self.assertTrue(any("cannot be a real deck" in o for o in out))
        self.assertEqual(typo[0], other)  # caller's list untouched

    def test_undoable_reader_raises_on_undo_and_returns_ranks(self):
        import builtins
        answers = iter(["u", "q", "UNDO", "10"])
        real = builtins.input
        builtins.input = lambda prompt="": next(answers)
        try:
            with self.assertRaises(solver.UndoRequested):
                solver.read_rank_undoable("x: ")
            self.assertEqual(solver.read_rank_undoable("x: "), "Q")
            with self.assertRaises(solver.UndoRequested):
                solver.read_rank_undoable("x: ")
            self.assertEqual(solver.read_rank_undoable("x: "), "10")
        finally:
            builtins.input = real


if __name__ == "__main__":
    unittest.main()
