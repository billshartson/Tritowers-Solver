"""End-to-end check: the real solver.py entry point, driven through stdin."""
import os
import random
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tools import heuristic_baseline as hb

HERE = os.path.dirname(os.path.abspath(__file__))


def solver_ranks():
    import solver
    return solver.RANKS


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
        self.assertIn("[PROVEN: verified winning line]", r.stdout)

    def test_same_seed_gives_same_session(self):
        a = run(["--skip-tutorial", "--seed", "7", "--simulations", "40"], session_input(5))
        b = run(["--skip-tutorial", "--seed", "7", "--simulations", "40"], session_input(5))
        self.assertEqual(a.stdout, b.stdout)

    def drive(self, setup_cards, board, review_lines=(), undo_at=None, seed=1, draws=None, undo_draw_at=None):
        """Interactive session: answer review/Position prompts from the true board."""
        import re
        import threading
        p = subprocess.Popen(
            [sys.executable, os.path.join(HERE, "solver.py"), "--skip-tutorial",
             "--seed", str(seed), "--simulations", "40"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=0)
        killer = threading.Timer(60, p.kill)
        killer.start()
        review = list(review_lines)
        asked, out, undone = [], "", False
        draw_i, draw_undone = 0, False
        try:
            p.stdin.write(setup_cards)
            while True:
                ch = p.stdout.read(1)
                if ch == "":
                    break
                out += ch
                if out.endswith("stock <n> <rank>: "):
                    p.stdin.write((review.pop(0) if review else "") + "\n")
                    out += "\n"
                    continue
                if draws is not None and out.endswith("DRAW -> "):
                    if undo_draw_at and draw_i + 1 == undo_draw_at and not draw_undone:
                        draw_undone = True
                        draw_i -= 1  # undo returns to the previous draw prompt
                        p.stdin.write("undo\n")
                    else:
                        p.stdin.write(draws[draw_i] + "\n")
                        draw_i += 1
                    out += "\n"
                    continue
                m = re.search(r"Position (\d\d): $", out)
                if not m:
                    continue
                asked.append(int(m.group(1)))
                if undo_at and len(asked) == undo_at and not undone:
                    undone = True
                    p.stdin.write("undo\n")
                else:
                    p.stdin.write(board[int(m.group(1)) - 1] + "\n")
                out += "\n"
        finally:
            killer.cancel()
            p.stdin.close()
            p.wait(timeout=30)
            p.stdout.close()
        return p.returncode, out, asked

    def bottom_row_setup(self, seed, bottom_override=None):
        board, waste, stock = hb.deal(random.Random(seed))
        bottom = list(board[18:28])
        if bottom_override:
            bottom[bottom_override[0]] = bottom_override[1]
        text = "\n".join(["2", "1", " ".join(bottom), waste, " ".join(stock)]) + "\n"
        return board, text

    def test_undo_mid_game_rewinds_and_game_still_wins(self):
        board, text = self.bottom_row_setup(3)
        rc, out, asked = self.drive(text, board, undo_at=3)
        self.assertEqual(rc, 0)
        self.assertIn("Undid the last step.", out)
        self.assertIn("WIN!", out)
        self.assertIn(asked[3], asked[:3])  # rewound: an answered position is asked again

    def test_undo_leaves_the_rest_of_the_session_unchanged(self):
        # Undo restores the sampler state too, so undoing and re-answering
        # reproduces the session with no undo.
        board, text = self.bottom_row_setup(3)
        _, plain, _ = self.drive(text, board)
        _, undone, _ = self.drive(text, board, undo_at=3)
        lines = lambda s: [l for l in s.splitlines() if l.startswith(("PLAY ", "DRAW", "Undid"))]
        after = lines(undone)
        after = after[after.index("Undid the last step.") + 1:]
        self.assertTrue(after)
        # everything after the undo replays exactly the tail of the plain session
        self.assertEqual(lines(plain)[-len(after):], after)

    def test_setup_typo_is_fixed_before_play_and_game_wins(self):
        # Mistype the first bottom-row card (position 19), then correct it.
        board, _ = self.bottom_row_setup(3)
        wrong = "2" if board[18] != "2" else "3"
        board_, text = self.bottom_row_setup(3, bottom_override=(0, wrong))
        fix = f"fix 19 {board[18]}"
        rc, out, _ = self.drive(text, board, review_lines=[fix, ""])
        self.assertEqual(rc, 0, out[-400:])
        self.assertIn(f"19:{wrong:>2}", out)      # the typo was visible
        self.assertIn(f"19:{board[18]:>2}", out)  # then corrected
        self.assertIn("WIN!", out)

    def test_rejected_setup_correction_changes_nothing(self):
        board, text = self.bottom_row_setup(3)
        rc, out, _ = self.drive(text, board, review_lines=["fix 99 K", "fix 19 Z", ""])
        self.assertEqual(rc, 0)
        self.assertIn("Not changed", out)
        self.assertIn("WIN!", out)

    def test_full_entry_typo_is_repaired_in_place_and_game_wins(self):
        board, waste, stock = hb.deal(random.Random(3))
        other = next(r for r in solver_ranks() if r != board[0])
        typo = [other] + board[1:]
        text = "\n".join([
            "1", "1", " ".join(typo), waste, " ".join(stock),
            "fix 99 K",          # rejected
            f"fix 1 {board[0]}",  # the real correction
            "",                   # start
        ]) + "\n"
        r = run(["--skip-tutorial", "--seed", "1", "--simulations", "60"], text)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("cannot be a real deck", r.stdout)
        self.assertIn("position 01", r.stdout)       # says where the problem is
        self.assertIn("Not changed", r.stdout)        # bad fix rejected
        self.assertNotIn("ERROR", r.stdout)           # no restart
        self.assertIn("WIN!", r.stdout)

    def test_unknown_stock_draws_and_undo_replays_identically(self):
        board, waste, stock = hb.deal(random.Random(3))
        text = "\n".join(["1", "2", " ".join(board), waste]) + "\n"
        _, plain, _ = self.drive(text, board, draws=stock)
        rc, undone, _ = self.drive(text, board, draws=stock, undo_draw_at=2)
        self.assertEqual(rc, 0)
        self.assertIn("Undid the last step.", undone)
        lines = lambda s: [l for l in s.splitlines() if l.startswith(("PLAY ", "Undid"))]
        after = lines(undone)
        after = after[after.index("Undid the last step.") + 1:]
        self.assertTrue(after)
        self.assertEqual(lines(plain)[-len(after):], after)

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
