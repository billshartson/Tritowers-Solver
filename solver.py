"""
======================================================================
                         TRITOWERS SOLVER
======================================================================

A rank-only TriTowers solver.

CARD STRUCTURE
--------------

Standard 52-card deck:

    28 tableau cards
     1 waste card
    23 stock cards
    ----------------
    52 cards total

Suits are completely ignored.

There are four copies of every rank:

    A  2  3  4  5  6  7  8  9  10  J  Q  K


TABLEAU POSITIONS
-----------------

                         [01]       [02]       [03]

                    [04] [05]   [06] [07]   [08] [09]

               [10] [11] [12] [13] [14] [15] [16] [17] [18]

        [19] [20] [21] [22] [23] [24] [25] [26] [27] [28]


The bottom row is positions 19-28.


SOLVER BEHAVIOUR
----------------

1. Ask whether the complete tableau is known.

2. Ask whether the stock order is known.

3. Ask for the waste card.

4. Enter the known cards as quickly as possible.

5. If only the bottom row is known, upper cards are requested
   ONLY when they become exposed.

6. With every card and stock order known, the solver searches
   for a verified winning line first, within a search limit.

7. If no guaranteed route is available, it chooses the route
   with the highest estimated probability of success.

8. Solver moves require NO confirmation.

9. If the stock is unknown, the user only enters the card
   that actually appears when a draw occurs.

======================================================================
"""

import random
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum

# CLI helpers import solver too; script execution must use the same classes.
if __name__ == "__main__":
    sys.modules["solver"] = sys.modules[__name__]


# ======================================================================
# SETTINGS
# ======================================================================

RANKS = (
    "A",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
    "10",
    "J",
    "Q",
    "K",
)

VALUE = {
    rank: index + 1
    for index, rank in enumerate(RANKS)
}

COPIES_PER_RANK = 4

TOTAL_TABLEAU = 28
TOTAL_WASTE = 1
TOTAL_STOCK = 23
TOTAL_CARDS = 52

assert TOTAL_TABLEAU + TOTAL_WASTE + TOTAL_STOCK == TOTAL_CARDS, "deck layout must account for every card"

SIMULATIONS = 1200
MAX_SIMULATION_MOVES = 100

# In TriTowers, A and K are treated as adjacent.
ACE_WRAP = True


class Evidence(Enum):
    """What supports a move recommendation."""

    PROVEN = "proven"
    SAMPLED = "sampled"


@dataclass(frozen=True)
class Recommendation:
    position: int
    success_rate: float
    evidence: Evidence
    simulations: int = 0

    @property
    def is_proven(self):
        return self.evidence is Evidence.PROVEN

    def as_legacy_tuple(self):
        """Temporary adapter for old CLI code; never implies proof from 1.0."""
        return self.position, self.success_rate


# ======================================================================
# TABLEAU STRUCTURE
# ======================================================================

"""
The 28 cards are arranged as:

                         [01]       [02]       [03]

                    [04] [05]   [06] [07]   [08] [09]

               [10] [11] [12] [13] [14] [15] [16] [17] [18]

        [19] [20] [21] [22] [23] [24] [25] [26] [27] [28]


A card is exposed when BOTH cards covering it have been removed.

The three tower tops have two blockers each.

The second row has two blockers each.

The third row has two blockers each.

The bottom row has no blockers.
"""


# ----------------------------------------------------------------------
# BLOCKERS
#
# For each position, this gives the two cards directly beneath it
# which must BOTH be removed before the card is exposed.
# ----------------------------------------------------------------------

BLOCKERS = {

    # --------------------------------------------------------------
    # TOP OF TOWER 1
    # --------------------------------------------------------------

    1: (4, 5),

    # --------------------------------------------------------------
    # TOP OF TOWER 2
    # --------------------------------------------------------------

    2: (6, 7),

    # --------------------------------------------------------------
    # TOP OF TOWER 3
    # --------------------------------------------------------------

    3: (8, 9),

    # --------------------------------------------------------------
    # SECOND ROW - TOWER 1
    # --------------------------------------------------------------

    4: (10, 11),
    5: (11, 12),

    # --------------------------------------------------------------
    # SECOND ROW - TOWER 2
    # --------------------------------------------------------------

    6: (13, 14),
    7: (14, 15),

    # --------------------------------------------------------------
    # SECOND ROW - TOWER 3
    # --------------------------------------------------------------

    8: (16, 17),
    9: (17, 18),

    # --------------------------------------------------------------
    # THIRD ROW
    # --------------------------------------------------------------

    10: (19, 20),
    11: (20, 21),
    12: (21, 22),

    13: (22, 23),
    14: (23, 24),
    15: (24, 25),

    16: (25, 26),
    17: (26, 27),
    18: (27, 28),
}


# ======================================================================
# CARD FUNCTIONS
# ======================================================================

def normalize(card):
    """
    Convert input to a valid rank.
    """

    if not isinstance(card, str):
        raise ValueError("Choose a card rank: A, 2-10, J, Q or K.")
    card = card.strip().upper()

    if card in ("?", "--"):
        return card

    if card not in RANKS:
        raise ValueError(
            f"Invalid card '{card}'. "
            f"Use A, 2-10, J, Q or K."
        )

    return card


JOKER = "*"


def can_play(card, waste):
    """
    Determine whether 'card' can be played on 'waste'.
    """

    # The joker ("*") only ever sits on the waste: it accepts any ranked card, and a ranked
    # card played onto it becomes the new waste. It is never a tableau card.
    if waste == JOKER:
        return card in VALUE
    if card == JOKER:
        return False
    card_value = VALUE[card]
    waste_value = VALUE[waste]

    if abs(card_value - waste_value) == 1:
        return True

    if ACE_WRAP and {card_value, waste_value} == {VALUE["A"], VALUE["K"]}:
        return True

    return False


# ======================================================================
# STATE VALIDATION AND CLI MIGRATION SURFACE
# ======================================================================


def validate_board(board):
    """Return a normalized 28-card board or raise ``ValueError``."""
    if len(board) != TOTAL_TABLEAU:
        raise ValueError(f"Board must contain exactly {TOTAL_TABLEAU} positions.")
    normalized = [normalize(card) for card in board]
    return normalized


def validate_deal(board, waste, stock_known, stock):
    """Normalize and validate the complete known portion of a deal.

    This is the canonical entry point for CLIs and future UIs. Unknown stock is
    represented by a nonnegative count; known stock remains ordered.
    """
    board = validate_board(board)
    cleared = {p for p, card in enumerate(board, 1) if card == "--"}
    if any(not set(BLOCKERS.get(p, ())) <= cleared for p in cleared):
        raise ValueError("A cleared tableau card is still covered by a present card.")
    waste = JOKER if isinstance(waste, str) and waste.strip() == JOKER else normalize(waste)
    if waste not in RANKS and waste != JOKER:
        raise ValueError("Waste must have a known rank.")

    jokers = 1 if waste == JOKER else 0
    if stock_known:
        if not isinstance(stock, (list, tuple)):
            raise ValueError("Known stock must be an ordered sequence.")
        normalized_stock = [
            JOKER if isinstance(card, str) and card.strip() == JOKER else normalize(card)
            for card in stock
        ]
        for index, card in enumerate(normalized_stock):
            if card == JOKER:
                # Provenance: Bill-reported rule (always the last card of the stock). Model only.
                if index != len(normalized_stock) - 1:
                    raise ValueError("The joker can only be the last stock card.")
                jokers += 1
            elif card not in RANKS:
                raise ValueError("Known stock cannot contain unknown or removed cards.")
        if jokers > 1:
            raise ValueError("Only one joker exists.")
        stock = normalized_stock
        if len(stock) - int(bool(stock) and stock[-1] == JOKER) > TOTAL_STOCK:
            raise ValueError(f"Stock cannot contain more than {TOTAL_STOCK} ranked cards.")
    else:
        if isinstance(stock, bool) or not isinstance(stock, int) or stock < 0:
            raise ValueError("Unknown stock must be a nonnegative card count.")
        if stock > TOTAL_STOCK:
            raise ValueError(f"Unknown stock cannot exceed {TOTAL_STOCK} ranked cards.")

    counts = Counter(card for card in board if card in RANKS)
    if waste in RANKS:
        counts[waste] += 1
    if stock_known:
        counts.update(card for card in stock if card in RANKS)
    overfull = {rank: count for rank, count in counts.items() if count > COPIES_PER_RANK}
    if overfull:
        details = ", ".join(f"{rank}={count}" for rank, count in sorted(overfull.items()))
        raise ValueError(f"Impossible deck: {details}")
    if sum(counts.values()) > TOTAL_CARDS:
        raise ValueError("Known cards exceed a standard deck.")
    unknown_slots = board.count("?") + (0 if stock_known else stock)
    unseen_cards = TOTAL_CARDS - sum(counts.values())
    if unknown_slots > unseen_cards:
        raise ValueError("Unknown cards exceed the unseen standard-deck pool.")
    return board, waste, stock_known, stock


# ======================================================================
# GAME STATE
# ======================================================================

class Game:

    def __init__(
        self,
        board,
        waste,
        stock_known,
        stock,
        joker_in_stock=False
    ):

        # joker_in_stock: opt-in, unknown-order stock only. The stock count then
        # INCLUDES the joker, which is always the last stock card (Bill-reported
        # rule, model only). It never enters the ranked pool or seen_counts.
        joker_in_stock = bool(joker_in_stock)
        if joker_in_stock:
            if stock_known:
                raise ValueError("joker_in_stock is for an unknown-order stock; put '*' last in a known stock instead.")
            if isinstance(stock, bool) or not isinstance(stock, int) or stock < 1:
                raise ValueError("A stock holding the joker needs a count of at least 1.")
        board, waste, stock_known, checked_stock = validate_deal(
            board, waste, stock_known, stock - 1 if joker_in_stock else stock
        )
        if waste == JOKER and joker_in_stock:
            raise ValueError("Only one joker exists.")
        stock = checked_stock + 1 if joker_in_stock else checked_stock
        self.board = board
        self.waste = waste
        self.stock_known = stock_known
        self.joker_in_stock = joker_in_stock
        self.stock = list(stock) if stock_known else stock

        # Positions are 1-28.
        self.removed = {
            position
            for position, card in enumerate(self.board, start=1)
            if card == "--"
        }

        # Every observed card remains consumed even after it leaves the
        # tableau or is covered by a later waste card.
        self.seen_counts = Counter(
            card for card in self.board if card in RANKS
        )
        if self.waste in RANKS:
            self.seen_counts[self.waste] += 1
        if self.stock_known:
            self.seen_counts.update(c for c in self.stock if c in RANKS)
        self._validate_seen_counts()

    @property
    def stock_remaining(self):
        """Number of stock cards remaining, independent of stock mode."""
        return len(self.stock) if self.stock_known else self.stock

    @property
    def stock_empty(self):
        """True when no stock card can be drawn, in either stock mode."""
        return not self.stock if self.stock_known else self.stock <= 0

    def state_snapshot(self):
        """Stable read-only-shaped state for CLIs and display adapters."""
        return {
            "board": tuple(self.board),
            "removed": frozenset(self.removed),
            "waste": self.waste,
            "stock_known": self.stock_known,
            "stock": tuple(self.stock) if self.stock_known else self.stock,
            "stock_remaining": self.stock_remaining,
            "joker_in_stock": self.joker_in_stock,
            "remaining": self.remaining(),
        }

    # ------------------------------------------------------------------
    # COPY
    # ------------------------------------------------------------------

    def copy(self):
        # Do not reconstruct through __init__: a played tableau card remains in
        # board for display while also becoming waste, so recounting would count
        # the same physical card twice. Copy the validated state directly.
        new_game = object.__new__(Game)
        new_game.board = self.board.copy()
        new_game.waste = self.waste
        new_game.stock_known = self.stock_known
        new_game.joker_in_stock = self.joker_in_stock
        new_game.stock = self.stock.copy() if self.stock_known else self.stock
        new_game.removed = self.removed.copy()
        new_game.seen_counts = self.seen_counts.copy()
        return new_game

    def _validate_seen_counts(self):
        overfull = {
            rank: count
            for rank, count in self.seen_counts.items()
            if count > COPIES_PER_RANK
        }
        if overfull:
            details = ", ".join(
                f"{rank}={count}" for rank, count in sorted(overfull.items())
            )
            raise ValueError(f"Impossible deck: {details}")

    def observe_rank(self, card):
        """Record one newly observed card, rejecting impossible deals."""
        card = normalize(card)
        if card not in RANKS:
            raise ValueError("An observed card must have a known rank.")
        if self.seen_counts[card] >= COPIES_PER_RANK:
            raise ValueError(f"Impossible deck: more than four {card} cards.")
        self.seen_counts[card] += 1
        return card

    def unknown_counts(self):
        return {
            rank: COPIES_PER_RANK - self.seen_counts[rank]
            for rank in RANKS
        }

    def unknown_card_pool(self):
        return [
            rank
            for rank, count in self.unknown_counts().items()
            for _ in range(count)
        ]

    def sample_unknown_card(self, rng=None):
        pool = self.unknown_card_pool()
        if not pool:
            raise ValueError("No unknown cards remain in the deck.")
        rng = rng or random
        return self.observe_rank(rng.choice(pool))

    def observe_draw(self, card):
        if self.stock_known:
            raise ValueError("Cannot manually observe a known stock.")
        if self.stock_empty:
            raise ValueError("The stock is empty.")
        if self.joker_in_stock:
            if self.stock == 1:
                if not (isinstance(card, str) and card.strip() in (JOKER, "joker", "Joker")):
                    raise ValueError("The last stock card is the joker.")
                self.stock = 0
                self.joker_in_stock = False
                self.waste = JOKER
                return JOKER
            if isinstance(card, str) and card.strip() == JOKER:
                raise ValueError("The joker is only ever the last stock card.")
        elif isinstance(card, str) and card.strip() == JOKER:
            raise ValueError("This game has no joker in the stock.")
        card = self.observe_rank(card)
        self.stock -= 1
        self.waste = card
        return card

    def draw_known(self):
        """Draw the next card of a known stock (index 0) onto the waste and return it."""
        if not self.stock_known:
            raise ValueError("Stock order is not known.")
        if not self.stock:
            raise ValueError("The stock is empty.")
        self.waste = self.stock.pop(0)
        return self.waste

    # ------------------------------------------------------------------
    # TABLEAU REMAINING
    # ------------------------------------------------------------------

    def remaining(self):

        count = 0

        for position in range(1, TOTAL_TABLEAU + 1):

            if position in self.removed:
                continue

            card = self.board[position - 1]

            if card != "--":
                count += 1

        return count

    # ------------------------------------------------------------------
    # EXPOSED CARDS
    # ------------------------------------------------------------------

    def exposed(self):
        """Return all currently exposed tableau positions, in position order."""
        removed = self.removed
        board = self.board
        return [
            position
            for position in range(1, TOTAL_TABLEAU + 1)
            if position not in removed
            and board[position - 1] != "--"
            and BLOCKER_SETS[position] <= removed
        ]

    # ------------------------------------------------------------------
    # LEGAL MOVES
    # ------------------------------------------------------------------

    def legal_moves(self):

        result = []

        for position in self.exposed():

            card = self.board[position - 1]

            # Unknown card cannot be played yet.
            if card == "?":
                continue

            if can_play(
                card,
                self.waste
            ):
                result.append(position)

        return result

    # ------------------------------------------------------------------
    # PLAY
    # ------------------------------------------------------------------

    def play(self, position):
        """Apply one legal tableau move.

        Keeping validation at the state boundary prevents callers, tests, and
        future interfaces from creating impossible games.
        """
        if not isinstance(position, int) or not 1 <= position <= TOTAL_TABLEAU:
            raise ValueError(f"Invalid tableau position: {position!r}")
        if position in self.removed:
            raise ValueError(f"Position {position:02d} has already been removed.")
        if position not in self.exposed():
            raise ValueError(f"Position {position:02d} is not exposed.")
        card = self.board[position - 1]
        if card not in RANKS:
            raise ValueError(f"Position {position:02d} has no known playable card.")
        if not can_play(card, self.waste):
            raise ValueError(f"{card} cannot be played on {self.waste}.")
        self.removed.add(position)
        self.waste = card
        return card


# ======================================================================
# CARD ACCOUNTING
# ======================================================================

def known_counts(game):
    """Return a copy of all ranks observed in this game."""
    return game.seen_counts.copy()


def unknown_counts(game):
    """Compatibility wrapper for callers outside ``Game``."""
    return game.unknown_counts()


def unknown_card_pool(game):
    """Compatibility wrapper for callers outside ``Game``."""
    return game.unknown_card_pool()


def random_unknown_card(game, rng=None):
    """Sample and consume one previously unknown card."""
    return game.sample_unknown_card(rng)


# ======================================================================
# INPUT FUNCTIONS
# ======================================================================

def read_cards(prompt, count):
    """
    Read exactly 'count' cards from one line.

    Example:

        > A 4 7 10 Q 3 ...
    """

    while True:

        try:

            values = (
                input(prompt)
                .strip()
                .upper()
                .split()
            )

            if len(values) != count:

                print(
                    f"Please enter exactly "
                    f"{count} cards."
                )

                continue

            return [
                normalize(card)
                for card in values
            ]

        except ValueError as error:

            print(error)


def read_rank(prompt):

    while True:

        try:

            card = normalize(
                input(prompt)
            )

            if card in ("?", "--"):

                print(
                    "Please enter an actual card rank."
                )

                continue

            return card

        except ValueError as error:

            print(error)


class UndoRequested(Exception):
    """Raised by an in-game prompt when the user types undo."""


def read_rank_undoable(prompt):
    """Like read_rank, but 'undo' or 'u' returns to the previous input prompt."""

    while True:

        raw = input(prompt)

        if raw.strip().lower() in ("undo", "u"):
            raise UndoRequested

        try:
            card = normalize(raw)
        except ValueError as error:
            print(error)
            continue

        if card in ("?", "--"):
            print("Please enter an actual card rank.")
            continue

        return card


CORRECTION_HELP = "fix <pos> <rank> / waste <rank> / stock <count> (unknown stock) / stock <n> <rank>"


def apply_correction(line, board, waste, stock, stock_known):
    """Parse one correction command and return (board, waste, stock).

    Inputs are not modified. Raises ValueError for anything unrecognised or
    out of range.
    """

    board = list(board)
    stock = list(stock) if stock_known else stock
    command = line[0].lower()

    if command == "fix" and len(line) == 3:
        position = int(line[1])
        if not 1 <= position <= TOTAL_TABLEAU:
            raise ValueError(f"position must be 1-{TOTAL_TABLEAU}")
        board[position - 1] = normalize(line[2])
    elif command == "waste" and len(line) == 2:
        waste = normalize(line[1])
    elif command == "stock" and len(line) == 3 and stock_known:
        index = int(line[1])
        if not 1 <= index <= len(stock):
            raise ValueError(f"stock index must be 1-{len(stock)}")
        stock[index - 1] = normalize(line[2])
    elif command == "stock" and len(line) == 2 and not stock_known:
        stock = int(line[1])
    else:
        raise ValueError("unrecognised correction")

    return board, waste, stock


def overfull_report(board, waste, stock_known, stock):
    """Describe every rank entered more than four times, or return []."""

    places = {}

    for position, card in enumerate(board, start=1):
        if card in RANKS:
            places.setdefault(card, []).append(f"position {position:02d}")

    if waste in RANKS:
        places.setdefault(waste, []).append("waste")

    if stock_known:
        for index, card in enumerate(stock, start=1):
            if card in RANKS:
                places.setdefault(card, []).append(f"stock {index}")

    return [
        f"{rank} was entered {len(where)} times (a deck has "
        f"{COPIES_PER_RANK}): " + ", ".join(where)
        for rank, where in places.items()
        if len(where) > COPIES_PER_RANK
    ]


def repair_entry(board, waste, stock_known, stock, read_line=input, emit=print, joker=False):
    """Build the Game, letting the user correct entry mistakes in place.

    Instead of failing and restarting 50-odd ranks, show where the problem
    is and accept the same fix/waste/stock commands used after setup.
    """

    while True:

        problems = overfull_report(board, waste, stock_known, stock)

        if not problems:
            try:
                return Game(board, waste, stock_known, stock, joker_in_stock=joker and not stock_known)
            except ValueError as error:
                problems = [str(error)]

        emit()
        emit("The entered cards cannot be a real deck:")

        for problem in problems:
            emit("  " + problem)

        emit("Correct the mistyped card with: " + CORRECTION_HELP)

        line = read_line("Correction: ").split()

        if not line:
            continue

        try:
            board, waste, stock = apply_correction(
                line, board, waste, stock, stock_known
            )
        except ValueError as error:
            emit(f"Not changed: {error}")


def review_setup(game, read_line=input, emit=print):
    """Let the user fix a mistyped entry before play starts.

    Enter (or end of input) starts the game. Commands:
        fix <position> <rank>   e.g. fix 07 K   (also -- for cleared, ? for unknown)
        waste <rank>
        stock <index> <rank>    known stock only, 1 = next card drawn
        stock <count>           unknown stock only, remaining card count
    Returns the (possibly corrected) game. A rejected correction leaves the
    game unchanged.
    """

    import tritowers_cli

    while True:

        emit()
        emit(tritowers_cli.format_board(game))
        if game.stock_known:
            emit("Stock order: " + " ".join(game.stock))
        else:
            emit("To correct the remaining stock count, enter stock <count>.")

        try:
            line = read_line(
                "Enter to start, or fix <pos> <rank> / waste <rank> / "
                "stock <n> <rank>: "
            ).split()
        except EOFError:
            return game

        if not line:
            return game

        try:
            board, waste, stock = apply_correction(
                line, game.board, game.waste, game.stock, game.stock_known
            )
            game = Game(board, waste, game.stock_known, stock, joker_in_stock=game.joker_in_stock)

        except ValueError as error:
            emit(f"Not changed: {error}")


def checkpoint(history, game, rng):
    """Save the game and sampler immediately before a user input prompt."""

    history.checkpoint(game)
    history._states[-1].rng_state = rng.getstate()


def rewind(history, rng=None):
    """Return the game to the previous input prompt, crossing automatic moves.

    The newest checkpoint is the prompt in progress and is discarded. With
    no earlier input prompt, the current prompt simply restarts.
    """

    current = history.undo()
    target = history.undo() if history.can_undo() else current

    state = getattr(target, "rng_state", None)

    if rng is not None and state is not None:
        rng.setstate(state)

    return target


# ======================================================================
# STARTUP EXPLANATION
# ======================================================================

def explain():

    print()
    print("=" * 72)
    print("                         TRITOWERS SOLVER")
    print("=" * 72)

    print(
        """
CARD INFORMATION
----------------

This solver ignores SUITS completely.

Only the rank/number of each card matters.

There are four copies of every rank:

    A  2  3  4  5  6  7  8  9  10  J  Q  K


THE 52 CARDS
------------

    28 tableau cards
     1 waste card
    23 stock cards
    ----------------
    52 cards total


TABLEAU
-------

The tableau is the group of 28 cards arranged into the
three towers.


WASTE
-----

The waste is the single card currently showing.

A tableau card can be played when its rank is immediately
above or below the waste card.

A and K are treated as adjacent.


STOCK
-----

The stock is the pile of cards that you draw when there
are no playable tableau cards.

There are ALWAYS 23 stock cards at the start.


EXPOSED
-------

A card is exposed when BOTH cards covering it have been
removed.

If you only know the bottom row, you do NOT need to enter
the other tableau cards initially.

The solver will ask for an unknown card when it becomes
exposed.


GUARANTEED ROUTE
----------------

When every remaining tableau card and the stock order are
known, the solver first searches for a verified winning line.
Search limits can leave the result undecided. With hidden
cards, only an immediate tableau clear is labelled guaranteed.


STATISTICAL ROUTE
-----------------

If no guaranteed route can be established, the solver
simulates possible future cards and chooses the move with
the highest estimated chance of success.


DURING PLAY
-----------

You do NOT need to confirm the solver's moves.

When a card becomes exposed, simply enter its rank.

When an unknown stock card is drawn, simply enter the rank
that appeared.

The solver then immediately continues.
"""
    )

    print()
    print("=" * 72)
    print("                         POSITION MAP")
    print("=" * 72)

    print(
        """
                         [01]       [02]       [03]


                    [04] [05]   [06] [07]   [08] [09]


               [10] [11] [12] [13] [14] [15] [16] [17] [18]


        [19] [20] [21] [22] [23] [24] [25] [26] [27] [28]


BOTTOM ROW:

19 20 21 22 23 24 25 26 27 28
"""
    )

    print("=" * 72)
    print()


# ======================================================================
# SETUP
# ======================================================================

def read_stock_count(read_line=None, emit=print, joker=False):
    """Ask how many stock cards remain when entering a game in progress.

    With the joker the machine counter includes it (fresh stock is 24)."""
    read_line = read_line or input
    top = TOTAL_STOCK + (1 if joker else 0)
    while True:
        raw = read_line(
            f"Stock cards remaining (0-{top}): "
        ).strip()
        try:
            count = int(raw)
        except ValueError:
            count = -1
        if 0 <= count <= top:
            return count
        emit(f"Please enter a whole number from 0 to {top}.")


def read_stock_cards(read_line=None, emit=print, joker=False):
    """Read the remaining ordered stock, including an optional fixed joker tail."""
    read_line = read_line or input
    while True:
        try:
            cards = [JOKER if token == JOKER else normalize(token)
                     for token in read_line("> ").split()]
            if joker and JOKER not in cards:
                cards.append(JOKER)
            if any(card not in RANKS and card != JOKER for card in cards):
                raise ValueError("Enter known ranks only; an empty line means no stock remains.")
            if JOKER in cards and (cards[-1] != JOKER or cards.count(JOKER) != 1):
                raise ValueError("The joker must be the last stock card.")
            if len(cards) - int(bool(cards) and cards[-1] == JOKER) > TOTAL_STOCK:
                raise ValueError(f"Enter at most {TOTAL_STOCK} ranked stock cards.")
            return cards
        except ValueError as error:
            emit(str(error))


def setup(skip_tutorial=False, joker=False):

    if not skip_tutorial:
        explain()

    # ------------------------------------------------------------------
    # ASK ALL INFORMATION QUESTIONS BEFORE CARD ENTRY
    # ------------------------------------------------------------------

    print("=" * 72)
    print("                         GAME INFORMATION")
    print("=" * 72)

    print()

    print(
        "Do you know all 28 tableau cards?"
    )

    print(
        "1 = Yes, I know all 28"
    )

    print(
        "2 = No, I only know the bottom row"
    )

    while True:

        tableau_mode = input(
            "\nChoice [1/2]: "
        ).strip()

        if tableau_mode in ("1", "2"):
            break

        print(
            "Please enter 1 or 2."
        )

    print()

    print(
        "Do you know the order of the remaining stock cards?"
    )

    print(
        "1 = Yes, I know the stock order"
    )

    print(
        "2 = No, the stock is unknown"
    )

    while True:

        stock_mode = input(
            "\nChoice [1/2]: "
        ).strip()

        if stock_mode in ("1", "2"):
            break

        print(
            "Please enter 1 or 2."
        )

    # ------------------------------------------------------------------
    # TABLEAU ENTRY
    # ------------------------------------------------------------------

    board = ["?"] * TOTAL_TABLEAU

    print()
    print("=" * 72)
    print("                           CARD ENTRY")
    print("=" * 72)

    if tableau_mode == "1":

        print(
            """
Enter all 28 tableau cards in POSITION ORDER.

Order:

01 02 03 04 05 06 07 08 09 10 ... 26 27 28

Enter all 28 cards on ONE line.

Use -- if a tableau position has already been cleared.
"""
        )

        board = read_cards(
            "> ",
            28
        )

    else:

        print(
            """
Enter ONLY the bottom row.

Positions:

19 20 21 22 23 24 25 26 27 28

Enter all 10 cards on ONE line.
"""
        )

        bottom = read_cards(
            "> ",
            10
        )

        board[18:28] = bottom

    # ------------------------------------------------------------------
    # WASTE
    # ------------------------------------------------------------------

    print()

    waste = read_rank(
        "Current waste card: "
    )

    # ------------------------------------------------------------------
    # STOCK
    # ------------------------------------------------------------------

    if stock_mode == "1":

        print(
            """
Enter the remaining stock cards in DRAW ORDER (up to 23 ranks).

The FIRST card you enter is the NEXT card that
will be drawn.

Enter them on ONE line, or leave it empty if the stock is empty.
"""
        )

        stock = read_stock_cards(joker=joker)

        stock_known = True

    else:

        # A fresh deal has 52 - 28 tableau - 1 waste = 23 stock cards. Cleared
        # tableau cards (--) mean the game is under way, so the count is asked.
        stock = (
            read_stock_count(joker=joker)
            if "--" in board
            else TOTAL_STOCK + (1 if joker else 0)
        )

        stock_known = False

    # ------------------------------------------------------------------
    # VALIDATE DECK (mistakes are corrected in place, not restarted)
    # ------------------------------------------------------------------

    return repair_entry(board, waste, stock_known, stock, joker=joker)


# ======================================================================
# REVEAL UNKNOWN CARDS
# ======================================================================

def reveal_unknowns(game, read_card=read_rank, emit=print, before_prompt=None):

    """
    Ask for every newly exposed unknown tableau card.

    If only the bottom row was entered initially, this is how
    the solver progressively learns the rest of the tableau.
    """

    unknown_positions = [
        position
        for position in game.exposed()
        if game.board[position - 1] == "?"
    ]

    for position in unknown_positions:
        if before_prompt is not None:
            before_prompt()
        while True:
            card = read_card(f"Position {position:02d}: ")
            try:
                card = game.observe_rank(card)
            except ValueError as error:
                emit(str(error) + " Please try again, or type undo.")
                continue
            game.board[position - 1] = card
            break


# ======================================================================
# STOCK DRAW
# ======================================================================

def draw(game, read_card=read_rank, emit=print, before_prompt=None):

    # ------------------------------------------------------------------
    # KNOWN STOCK
    # ------------------------------------------------------------------

    if game.stock_known:

        if game.stock_empty:
            return False

        card = game.stock.pop(0)

        game.waste = card

        emit(f"DRAW -> {card}")

        return True

    # ------------------------------------------------------------------
    # UNKNOWN STOCK
    # ------------------------------------------------------------------

    if game.stock_empty:
        return False

    # A stock holding the joker ends with it: nothing to ask for the last draw.
    if game.joker_in_stock and game.stock_remaining == 1:
        game.observe_draw(JOKER)
        emit("DRAW -> joker (*)")
        return True

    # The user only tells us what card actually appeared.
    if before_prompt is not None:
        before_prompt()
    while True:
        card = read_card("DRAW -> ")
        try:
            game.observe_draw(card)
            break
        except ValueError as error:
            emit(str(error) + " Please try again, or type undo.")

    return True


# ======================================================================
# MOVE HEURISTIC
# ======================================================================

BLOCKER_SETS = {
    position: frozenset(BLOCKERS.get(position, ()))
    for position in range(1, TOTAL_TABLEAU + 1)
}

COVERED_BY = {
    blocker: tuple(sorted(
        covered for covered, blockers in BLOCKERS.items() if blocker in blockers
    ))
    for blocker in range(1, TOTAL_TABLEAU + 1)
}


def _newly_exposed(game, position):
    """Positions that become exposed when ``position`` is removed.

    Only cards that ``position`` was blocking can change, so nothing is copied
    and the rest of the board is not rescanned.
    """
    removed = game.removed
    return [
        covered
        for covered in COVERED_BY[position]
        if covered not in removed
        and game.board[covered - 1] != "--"
        and all(blocker == position or blocker in removed
                for blocker in BLOCKERS[covered])
    ]


def move_score(game, position):
    """Score only consequences caused by this move.

    The former implementation rescored every already exposed card and added a
    sibling-constant "cards removed" term. That made most of the score unrelated
    to the candidate move and produced avoidable ties.

    Evaluated without copying the game: playing ``position`` only adds it to
    ``removed`` and makes its card the waste, so the result is computed from
    those two facts. Scores are identical to the copying implementation.
    """
    board = game.board
    removed = game.removed | {position}
    waste = board[position - 1]
    newly_exposed = _newly_exposed(game, position)

    score = 0
    for exposed_position in newly_exposed:
        card = board[exposed_position - 1]
        if card == "?":
            score += 20
        else:
            score += 10
            if can_play(card, waste):
                score += 8

    # Prefer moves that remove a blocker from still-covered cards. This differs
    # between sibling moves and measures genuine future progress.
    score += sum(
        position in blockers
        for covered, blockers in BLOCKERS.items()
        if covered not in removed
    )
    return score


# ======================================================================
# GUARANTEED MOVE CHECK
# ======================================================================

def guaranteed_moves(game):
    """Return moves that immediately and provably clear the tableau.

    A Monte Carlo success rate, or merely having stock left, is not a proof.
    Broader proof-producing search can be added separately.
    """
    result = []
    for position in game.legal_moves():
        child = game.copy()
        child.play(position)
        if child.remaining() == 0:
            result.append(position)
    return result


# ======================================================================
# SIMULATION
# ======================================================================

def simulate(
    game,
    first_move=None,
    rng=None
):

    """
    Simulate a possible future game.

    Unknown tableau and stock cards are sampled according to
    the known cards and the four-copy rule.
    """

    rng = rng or random
    g = game.copy()

    # --------------------------------------------------------------
    # Apply proposed first move.
    # --------------------------------------------------------------

    if first_move is not None:

        g.play(first_move)

    # --------------------------------------------------------------
    # Simulate.
    # --------------------------------------------------------------

    # Every iteration either removes a tableau card or consumes a stock card.
    max_transitions = g.remaining() + g.stock_remaining
    for _ in range(max_transitions):

        # ----------------------------------------------------------
        # Win.
        # ----------------------------------------------------------

        if g.remaining() == 0:

            return True

        # ----------------------------------------------------------
        # Resolve unknown exposed tableau cards.
        # ----------------------------------------------------------

        for position in g.exposed():

            if g.board[position - 1] == "?":

                g.board[position - 1] = (
                    random_unknown_card(g, rng)
                )

        # ----------------------------------------------------------
        # Play available tableau cards.
        # ----------------------------------------------------------

        moves = g.legal_moves()

        if moves:

            scored = [
                (
                    move_score(
                        g,
                        position
                    ),
                    position
                )
                for position in moves
            ]

            scored.sort(
                reverse=True
            )

            # Consider the strongest few moves rather than
            # making the simulation completely deterministic.
            top = scored[
                :min(3, len(scored))
            ]

            _, position = rng.choice(
                top
            )

            g.play(position)

            continue

        # ----------------------------------------------------------
        # No tableau move: draw.
        # ----------------------------------------------------------

        if g.stock_empty:

            return False

        if g.stock_known:

            g.waste = g.stock.pop(0)

        else:

            if g.joker_in_stock and g.stock == 1:
                g.stock = 0
                g.joker_in_stock = False
                g.waste = JOKER
            else:
                g.stock -= 1
                g.waste = g.sample_unknown_card(rng)

    return (
        g.remaining() == 0
    )


# ======================================================================
# PROBABILITY
# ======================================================================

MIN_BUDGET_SIMULATIONS = 20


def estimate(game, position, simulations=SIMULATIONS, rng=None, deadline=None):
    """Return ``(win_rate, runs)`` for a first move.

    Stops early once ``deadline`` (a ``time.monotonic()`` value) has passed, but
    never before MIN_BUDGET_SIMULATIONS runs so a rate is always meaningful.
    """
    if simulations <= 0:
        raise ValueError("simulations must be positive")
    rng = rng or random
    wins = runs = 0
    while runs < simulations:
        if (
            deadline is not None
            and runs >= MIN_BUDGET_SIMULATIONS
            and time.monotonic() >= deadline
        ):
            break
        wins += bool(simulate(game, first_move=position, rng=rng))
        runs += 1
    return wins / runs, runs


def probability(game, position, simulations=SIMULATIONS, rng=None):
    """Estimate a move's win rate with reproducible injected randomness."""
    return estimate(game, position, simulations, rng)[0]


# ======================================================================
# BEST MOVE
# ======================================================================

def best_move(game, simulations=SIMULATIONS, rng=None, time_budget=None):
    """Return a recommendation whose evidence type cannot be confused.

    A sampled rate of 100% remains sampled evidence, never a proof.

    With ``time_budget``, sample complete rounds across all candidates so they
    receive equal run counts. At least MIN_BUDGET_SIMULATIONS rounds run (unless
    fewer were requested). The deadline is checked between rounds, so this is
    a soft budget. Wall-clock termination is not reproducible even with a
    seeded generator; omit the budget for reproducible fixed-work sampling.
    """
    if time_budget is not None and time_budget <= 0:
        raise ValueError("time_budget must be positive")
    if simulations <= 0:
        raise ValueError("simulations must be positive")
    moves = game.legal_moves()
    if not moves:
        return None

    proven = guaranteed_moves(game)
    if proven:
        position = max(proven, key=lambda candidate: move_score(game, candidate))
        return Recommendation(position, 1.0, Evidence.PROVEN)

    rng = rng or random
    scored = []
    if time_budget is None:
        runs = simulations
        for position in moves:
            scored.append((probability(game, position, simulations, rng),
                           move_score(game, position), position))
    else:
        deadline = time.monotonic() + time_budget
        wins = {position: 0 for position in moves}
        runs = 0
        while runs < simulations:
            if runs >= MIN_BUDGET_SIMULATIONS and time.monotonic() >= deadline:
                break
            for position in moves:
                wins[position] += bool(simulate(game, first_move=position, rng=rng))
            runs += 1
        scored = [(wins[p] / runs, move_score(game, p), p) for p in moves]
    success_rate, _, position = max(scored)
    return Recommendation(
        position,
        success_rate,
        Evidence.SAMPLED,
        runs,
    )


# ======================================================================
# MAIN GAME LOOP
# ======================================================================

# ======================================================================
# EXACT SOLVER FOR A COMPLETE DEAL
# ======================================================================

@dataclass(frozen=True)
class SolveResult:
    """status: solved | unsolvable | unknown | incomplete.

    moves: list of ("play", position) or ("draw",) steps; only set when solved.
    unsolvable means the search was exhaustive under this module's rules; budgets give unknown.
    """
    status: str
    moves: list = field(default_factory=list)
    reason: str = ""
    nodes: int = 0
    seconds: float = 0.0


class _Budget(Exception):
    pass


def solve_complete(game, time_budget=None, max_nodes=5_000_000, max_memo=3_000_000,
                   draw_only_when_stuck=True, require_full_deal=False, require_joker=False):
    """Exact search over a fully known deal: every tableau card, the waste and the ordered stock.

    Does not mutate ``game``. Rules come from can_play, ACE_WRAP and BLOCKERS above.

    Input is a known POSITION, possibly mid-game (some tableau cards removed, a short stock); only the
    4-per-rank and 52-card ceilings are checked. Pass require_full_deal=True for a fresh deal
    (28 tableau + waste + 23 stock = 52, nothing removed; or 24 stock ending in the joker "*"),
    otherwise status "incomplete".

    Joker ("*", Bill-reported rules, not verified against the machine): one extra card, always the
    last stock card, never on the tableau; any ranked card can be played onto it and that card then
    becomes the waste. require_joker=True demands the full 53-card fresh deal (stock of 24 ending
    in "*"). No joker in the stock means exactly the previous 52-card behaviour.
    draw_only_when_stuck=True matches the CLI (a draw only when no tableau card is playable);
    False also allows a voluntary draw. Which one the real machine uses is unverified, and
    "unsolvable" holds only for the chosen setting.
    """
    t0 = time.monotonic()
    done = lambda status, moves=(), reason="", nodes=0: SolveResult(
        status, list(moves), reason, nodes, round(time.monotonic() - t0, 4))
    try:
        stock_known = game.stock_known
        if not stock_known:
            return done("incomplete", reason="unknown_stock")
        if any(c == "?" for p, c in enumerate(game.board, 1) if p not in game.removed):
            return done("incomplete", reason="unknown_cards")
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return done("incomplete", reason=f"invalid_deal: {exc}")
    # Game fields are mutable, so re-validate rather than trust the constructor.
    try:
        removed = set(game.removed)
        # Game.play leaves a played card on the board and also on the waste: count it once.
        board, waste, _, stock = validate_deal(
            ["--" if p in removed else c for p, c in enumerate(game.board, 1)],
            game.waste, True, game.stock)
        if "?" in board:
            return done("incomplete", reason="unknown_cards")
        if any(not isinstance(p, int) or isinstance(p, bool) or not 1 <= p <= TOTAL_TABLEAU for p in removed):
            raise ValueError("removed has invalid positions")
        if any(p not in removed for p, c in enumerate(board, 1) if c == "--"):
            raise ValueError("board has cleared slots not in removed")
        if any(not BLOCKER_SETS[p] <= removed for p in removed):
            raise ValueError("removed card is still covered")
        has_joker = bool(stock) and stock[-1] == JOKER
        if require_full_deal and (removed or waste == JOKER
                                  or len(stock) != TOTAL_STOCK + int(has_joker)):
            return done("incomplete", reason="not_full_deal")
        if require_joker and not (has_joker and not removed and waste != JOKER
                                  and len(stock) == TOTAL_STOCK + 1):
            return done("incomplete", reason="joker_missing")
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return done("incomplete", reason=f"invalid_deal: {exc}")
    n, full = len(stock), (1 << TOTAL_TABLEAU) - 1
    need = [sum(1 << (b - 1) for b in BLOCKER_SETS[p]) for p in range(1, TOTAL_TABLEAU + 1)]
    start = sum(1 << (p - 1) for p in removed)
    deadline = t0 + time_budget if time_budget is not None else None
    memo, nodes, calls, why = {}, [0], [0], [""]
    if deadline is not None and time_budget <= 0:
        return done("unknown", reason="timeout")

    def go(rem, w, i):
        if rem == full:
            return ()
        calls[0] += 1
        if deadline is not None and (calls[0] & 255) == 0 and time.monotonic() > deadline:
            why[0] = "timeout"; raise _Budget
        key = (rem, w, i)
        if key in memo:
            return memo[key]
        nodes[0] += 1
        if nodes[0] > max_nodes:
            why[0] = "node_limit"; raise _Budget
        if len(memo) >= max_memo:
            why[0] = "memory_limit"; raise _Budget
        res = None
        playable = False
        for p in range(TOTAL_TABLEAU):
            if rem >> p & 1 or need[p] & ~rem or not can_play(board[p], w):
                continue
            playable = True
            r = go(rem | 1 << p, board[p], i)
            if r is not None:
                res = (("play", p + 1),) + r
                break
        if res is None and i < n and not (draw_only_when_stuck and playable):
            r = go(rem, stock[i], i + 1)
            if r is not None:
                res = (("draw",),) + r
        memo[key] = res
        return res

    try:
        res = go(start, waste, 0)
    except _Budget:
        return done("unknown", reason=why[0], nodes=nodes[0])
    return done("unsolvable" if res is None else "solved", res or (), nodes=nodes[0])


def main(argv=None):

    import tritowers_cli

    args = tritowers_cli.build_parser().parse_args(argv)
    # Always an explicit generator so undo can restore its state.
    rng = random.Random(args.seed)
    game = review_setup(setup(skip_tutorial=args.skip_tutorial, joker=getattr(args, "joker", False)))

    print()
    print("=" * 72)
    print("                         SOLVER ACTIVE")
    print("=" * 72)

    history = tritowers_cli.UndoHistory()
    exact_plan = None
    before_prompt = lambda: checkpoint(history, game, rng)

    while True:

        # --------------------------------------------------------------
        # Ask for newly exposed unknown cards.
        # --------------------------------------------------------------

        try:
            reveal_unknowns(game, read_card=read_rank_undoable, before_prompt=before_prompt)
        except UndoRequested:
            game = rewind(history, rng)
            exact_plan = None
            print("Undid the last step.")
            continue

        print()
        print(tritowers_cli.format_board(game))

        # --------------------------------------------------------------
        # Check for win.
        # --------------------------------------------------------------

        if game.remaining() == 0:

            print()
            print("=" * 72)
            print("                              WIN!")
            print("=" * 72)

            return

        # A completely known position can be searched exactly. Reuse the
        # verified line so each automatic step does not repeat the search.
        if exact_plan is None and game.stock_known and all(
                card != "?" for p, card in enumerate(game.board, 1) if p not in game.removed):
            result = solve_complete(game, time_budget=args.time_budget, max_nodes=500_000)
            if result.status == "solved":
                exact_plan = list(result.moves)
            elif result.status == "unsolvable":
                print("No winning line exists with these known cards (draw only when stuck).")
                return
            else:
                print("Exact search did not finish; recommendations below are sampled.")
        if exact_plan:
            step = exact_plan.pop(0)
            if step[0] == "draw":
                draw(game)
            else:
                position = step[1]
                print(f"\nPLAY {game.board[position - 1]} @ {position:02d} [PROVEN: verified winning line]")
                game.play(position)
            continue

        # --------------------------------------------------------------
        # Find legal tableau moves.
        # --------------------------------------------------------------

        moves = game.legal_moves()

        # --------------------------------------------------------------
        # No tableau move -> draw.
        # --------------------------------------------------------------

        if not moves:

            if game.stock_empty:

                print()
                print(
                    "No playable tableau cards "
                    "and the stock is empty."
                )

                return

            try:
                draw(game, read_card=read_rank_undoable, before_prompt=before_prompt)
            except UndoRequested:
                game = rewind(history, rng)
                exact_plan = None
                print("Undid the last step.")

            continue

        # --------------------------------------------------------------
        # Find best move.
        # --------------------------------------------------------------

        recommendation = best_move(
            game,
            simulations=args.simulations,
            rng=rng,
            time_budget=args.time_budget,
        )
        position = recommendation.position
        card = game.board[position - 1]

        # --------------------------------------------------------------
        # Guaranteed route.
        # --------------------------------------------------------------

        if recommendation.evidence is Evidence.PROVEN:

            print(
                f"\nPLAY {card} @ "
                f"{position:02d} "
                f"[GUARANTEED]"
            )

        # --------------------------------------------------------------
        # Statistical route.
        # --------------------------------------------------------------

        else:

            print(
                f"\nPLAY {card} @ "
                f"{position:02d} "
                f"[{recommendation.success_rate * 100:.1f}% sampled "
                f"over {recommendation.simulations} runs]"
            )

        # --------------------------------------------------------------
        # Automatically apply move.
        #
        # No confirmation required.
        # --------------------------------------------------------------

        game.play(position)


# ======================================================================
# START
# ======================================================================

if __name__ == "__main__":

    try:

        main()

    except EOFError:

        print(
            "\nInput ended; solver stopped."
        )

    except KeyboardInterrupt:

        print(
            "\nSolver stopped."
        )
