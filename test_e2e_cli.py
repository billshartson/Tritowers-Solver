"""End-to-end check: the real solver.py entry point, driven through stdin."""
import os
import random
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tools import heuristic_baseline as hb

HERE = os.path.dirname(os.path.abspath(__file__))


def session_input(seed=3):
    board, waste, stock = hb.deal(random.Random(seed))
    return "\n".join(["1", "1", " ".join(board), waste, " ".join(stock)]) + "\n"


def run(args, text):
    return subprocess.run(
        [sys.executable, os.path.join(HERE, "solver.py"), *args],
        input=text, capture_output=True, text=True, timeout=60,
    )


class EndToEndTests(unittest.TestCase):
    def test_help_exits_without_starting_a_game(self):
        r = run(["--help"], "")
        self.assertEqual(r.returncode, 0)
        self.assertIn("--skip-tutorial", r.stdout)
        self.assertNotIn("CARD ENTRY", r.stdout)

    def test_full_known_game_plays_to_a_win_with_board_shown(self):
        r = run(["--skip-tutorial", "--seed", "1", "--simulations", "60"], session_input())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("CARD INFORMATION", r.stdout)
        self.assertIn("Waste:", r.stdout)
        self.assertIn("PLAY ", r.stdout)
        self.assertIn("WIN!", r.stdout)
        self.assertNotIn("stock is empty", r.stdout)

    def test_same_seed_gives_same_session(self):
        a = run(["--skip-tutorial", "--seed", "7", "--simulations", "40"], session_input(5))
        b = run(["--skip-tutorial", "--seed", "7", "--simulations", "40"], session_input(5))
        self.assertEqual(a.stdout, b.stdout)

    def test_tutorial_shown_by_default(self):
        r = run([], "")
        self.assertIn("CARD INFORMATION", r.stdout)

    def test_eof_mid_entry_stops_cleanly(self):
        r = run(["--skip-tutorial"], "1\n1\n")
        self.assertEqual(r.returncode, 0)
        self.assertIn("Input ended", r.stdout)
        self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
