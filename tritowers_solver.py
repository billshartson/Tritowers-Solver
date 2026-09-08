from functools import lru_cache


# ============================================================
# CONFIGURATION
# ============================================================

# Set to True if your version allows:
# K -> A and A -> K
ACE_WRAP = True


# ============================================================
# CARD HANDLING
# ============================================================

RANKS = {
    "A": 1,
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "10": 10,
    "J": 11,
    "Q": 12,
    "K": 13,
}

SUITS = {
    "C": "Clubs",
    "D": "Diamonds",
    "H": "Hearts",
    "S": "Spades",
}


def normalize_card(card):
    """
    Convert a card to a consistent format.

    Examples:
        ac  -> AC
        10h -> 10H
        QS  -> QS
    """

    card = card.strip().upper()

    if card == "--":
        return None

    if len(card) < 2:
        raise ValueError(f"Invalid card: {card}")

    r = card[:-1]
    s = card[-1]

    if r not in RANKS:
        raise ValueError(f"Invalid rank: {r}")

    if s not in SUITS:
        raise ValueError(f"Invalid suit: {s}")

    return r + s


def card_rank(card):
    """Return numerical rank."""

    return RANKS[card[:-1]]


def card_is_playable(card, waste, ace_wrap=True):
    """
    Determine whether card can be played on waste.
    """

    a = card_rank(card)
    b = card_rank(waste)

    # Normal adjacent ranks
    if abs(a - b) == 1:
        return True

    # Optional K <-> A
    if ace_wrap and {a, b} == {1, 13}:
        return True

    return False


# ============================================================
# BOARD GEOMETRY
# ============================================================

"""
Standard 28-card TriPeaks / TriTowers layout:

                    00       01       02

                 03    04  05    06  07    08

              09  10  11  12  13  14  15  16  17

           18  19  20  21  22  23  24  25  26  27


A card is blocked by the cards immediately underneath it.

For example:

        00
       /  \
      03  04

Card 00 becomes available when BOTH 03 and 04
have been removed.
"""

BLOCKERS = {
    # Peaks
    0: (3, 4),
    1: (5, 6),
    2: (7, 8),

    # Six-card row
    3: (9, 10),
    4: (10, 11),

    5: (12, 13),
    6: (13, 14),

    7: (15, 16),
    8: (16, 17),

    # Nine-card row
    9: (18, 19),
    10: (19, 20),
    11: (20, 21),

    12: (21, 22),
    13: (22, 23),
    14: (23, 24),

    15: (24, 25),
    16: (25, 26),
    17: (26, 27),

    # Bottom row 18-27 has no blockers.
}


# ============================================================
# SOLVER
# ============================================================

class TriTowersSolver:

    def __init__(
        self,
        board,
        waste,
        stock,
        ace_wrap=True,
    ):
        """
        board:
            28-card list.
            Use None for cards that have already been removed.

        waste:
            Current waste card.

        stock:
            Remaining stock in draw order.

        ace_wrap:
            Whether K and A are considered adjacent.
        """

        if len(board) != 28:
            raise ValueError(
                "The board must contain exactly 28 positions."
            )

        self.board = tuple(
            normalize_card(c) if c is not None else None
            for c in board
        )

        self.waste = normalize_card(waste)

        self.stock = tuple(
            normalize_card(c)
            for c in stock
        )

        self.ace_wrap = ace_wrap

        # Make sure all cards are valid.
        self._validate_cards()

        self.states_searched = 0

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    def _validate_cards(self):

        cards = []

        for card in self.board:
            if card is not None:
                cards.append(card)

        if self.waste is not None:
            cards.append(self.waste)

        cards.extend(self.stock)

        # A normal deck cannot contain duplicate physical cards.
        duplicates = []

        seen = set()

        for card in cards:
            if card in seen:
                duplicates.append(card)

            seen.add(card)

        if duplicates:
            raise ValueError(
                "Duplicate cards found: "
                + ", ".join(duplicates)
            )

    # --------------------------------------------------------
    # EXPOSED CARDS
    # --------------------------------------------------------

    def exposed_cards(self, removed):
        """
        Return board positions that can currently be played.

        A card is exposed if:
          - it has not already been removed
          - every card blocking it has been removed
        """

        result = []

        for position in range(28):

            if position in removed:
                continue

            card = self.board[position]

            if card is None:
                continue

            blockers = BLOCKERS.get(position, ())

            if all(
                blocker in removed
                for blocker in blockers
            ):
                result.append(position)

        return result

    # --------------------------------------------------------
    # SOLVE
    # --------------------------------------------------------

    def solve(self):
        """
        Find a winning sequence from the current game state.

        Returns:
            List of moves, or None if no solution exists.
        """

        self.states_searched = 0

        # Cards that are already gone.
        removed = frozenset(
            i
            for i, card in enumerate(self.board)
            if card is None
        )

        return self._search(
            removed,
            self.stock,
            self.waste,
        )

    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    @lru_cache(maxsize=None)
    def _search(
        self,
        removed,
        stock,
        waste,
    ):
        self.states_searched += 1

        # ----------------------------------------------------
        # WIN
        # ----------------------------------------------------

        remaining_cards = sum(
            1
            for i, card in enumerate(self.board)
            if card is not None
            and i not in removed
        )

        if remaining_cards == 0:
            return []

        # ----------------------------------------------------
        # FIND PLAYABLE BOARD CARDS
        # ----------------------------------------------------

        available = self.exposed_cards(removed)

        playable_positions = []

        for position in available:

            card = self.board[position]

            if card_is_playable(
                card,
                waste,
                self.ace_wrap,
            ):
                playable_positions.append(position)

        # ----------------------------------------------------
        # TRY BOARD MOVES FIRST
        # ----------------------------------------------------

        # Good heuristic:
        # prefer moves that expose more cards.
        #
        # This doesn't change correctness, only search order.

        def move_score(position):

            new_removed = removed | {position}

            newly_exposed = len(
                self.exposed_cards(new_removed)
            )

            return newly_exposed

        playable_positions.sort(
            key=move_score,
            reverse=True,
        )

        for position in playable_positions:

            card = self.board[position]

            new_removed = removed | {position}

            result = self._search(
                new_removed,
                stock,
                card,
            )

            if result is not None:

                return [
                    {
                        "type": "PLAY",
                        "position": position,
                        "card": card,
                    }
                ] + result

        # ----------------------------------------------------
        # TRY DRAWING
        # ----------------------------------------------------

        if stock:

            next_card = stock[0]
            remaining_stock = stock[1:]

            result = self._search(
                removed,
                remaining_stock,
                next_card,
            )

            if result is not None:

                return [
                    {
                        "type": "DRAW",
                        "card": next_card,
                    }
                ] + result

        # ----------------------------------------------------
        # DEAD END
        # ----------------------------------------------------

        return None


# ============================================================
# DISPLAY BOARD
# ============================================================

def print_board(board, removed=None):

    if removed is None:
        removed = set()

    def get(position):

        if position in removed:
            return "--"

        card = board[position]

        if card is None:
            return "--"

        return card

    print()
    print("                    " +
          f"{get(0):>3}       " +
          f"{get(1):>3}       " +
          f"{get(2):>3}")

    print()
    print("                 " +
          f"{get(3):>3} {get(4):>3}   " +
          f"{get(5):>3} {get(6):>3}   " +
          f"{get(7):>3} {get(8):>3}")

    print()
    print("              " +
          " ".join(
              f"{get(i):>3}"
              for i in range(9, 18)
          ))

    print()
    print("           " +
          " ".join(
              f"{get(i):>3}"
              for i in range(18, 28)
          ))

    print()


# ============================================================
# PRINT SOLUTION
# ============================================================

def print_solution(solution, starting_waste):

    print()
    print("=" * 65)
    print("SOLUTION")
    print("=" * 65)

    print()
    print("Starting waste:", starting_waste)
    print()

    waste = starting_waste

    move_number = 1

    for move in solution:

        if move["type"] == "PLAY":

            position = move["position"]
            card = move["card"]

            print(
                f"{move_number:3}. "
                f"PLAY {card:>3} "
                f"from position {position:02d} "
                f"on {waste}"
            )

            waste = card

        else:

            card = move["card"]

            print(
                f"{move_number:3}. "
                f"DRAW {card:>3}"
            )

            waste = card

        move_number += 1

    print()
    print("=" * 65)
    print(
        f"Total moves: {len(solution)}"
    )
    print("=" * 65)


# ============================================================
# MANUAL INPUT
# ============================================================

def read_card(prompt):

    while True:

        value = input(prompt).strip().upper()

        try:
            return normalize_card(value)

        except ValueError as e:
            print(e)


def read_board():

    print()
    print("=" * 65)
    print("ENTER THE CURRENT BOARD")
    print("=" * 65)

    print(
        """
Enter the 28 positions in this order:

                    00       01       02

                 03    04  05    06  07    08

              09  10  11  12  13  14  15  16  17

           18  19  20  21  22  23  24  25  26  27


Use -- for a card that has already been removed.

Example:

    00 = --
    01 = 7H
    02 = QC

Cards:
    AC = Ace of Clubs
    10D = Ten of Diamonds
    QS = Queen of Spades
"""
    )

    board = []

    for position in range(28):

        while True:

            value = input(
                f"Position {position:02d}: "
            ).strip().upper()

            try:

                if value == "--":
                    board.append(None)
                else:
                    board.append(
                        normalize_card(value)
                    )

                break

            except ValueError as e:
                print(e)

    return board


def read_stock():

    print()
    print("=" * 65)
    print("ENTER THE REMAINING STOCK")
    print("=" * 65)

    print(
        """
Enter the cards in the EXACT order they will be drawn.

Example:

    6H 9C 10S JD 4D 7S

If there are no cards left, just press ENTER.
"""
    )

    while True:

        text = input("Stock: ").strip().upper()

        if not text:
            return []

        values = text.split()

        try:

            return [
                normalize_card(card)
                for card in values
            ]

        except ValueError as e:
            print(e)


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 65)
    print("                 TRITOWERS SOLVER")
    print("=" * 65)

    print(
        """
This solver works with ANY current TriTowers/TriPeaks
game state.

You can enter:
  - a brand-new game
  - a partially played game
  - cards already removed
  - any waste card
  - any remaining stock
"""
    )

    # --------------------------------------------------------
    # Board
    # --------------------------------------------------------

    board = read_board()

    # --------------------------------------------------------
    # Waste
    # --------------------------------------------------------

    print()
    print("=" * 65)
    print("CURRENT WASTE")
    print("=" * 65)

    waste = read_card("Waste card: ")

    # --------------------------------------------------------
    # Stock
    # --------------------------------------------------------

    stock = read_stock()

    # --------------------------------------------------------
    # A/K rule
    # --------------------------------------------------------

    print()
    print("Does your game allow A <-> K?")

    while True:

        answer = input(
            "Allow A/K wrap? [Y/N]: "
        ).strip().upper()

        if answer in ("Y", "YES"):
            ace_wrap = True
            break

        if answer in ("N", "NO"):
            ace_wrap = False
            break

        print("Enter Y or N.")

    # --------------------------------------------------------
    # Display
    # --------------------------------------------------------

    print()
    print("=" * 65)
    print("CURRENT BOARD")
    print("=" * 65)

    removed = {
        i
        for i, card in enumerate(board)
        if card is None
    }

    print_board(board, removed)

    print("Waste:", waste)
    print("Stock:", len(stock), "cards")
    print("A/K wrap:", ace_wrap)

    # --------------------------------------------------------
    # Solve
    # --------------------------------------------------------

    print()
    print("Searching for a solution...")
    print()

    solver = TriTowersSolver(
        board=board,
        waste=waste,
        stock=stock,
        ace_wrap=ace_wrap,
    )

    solution = solver.solve()

    print(
        f"States searched: "
        f"{solver.states_searched:,}"
    )

    # --------------------------------------------------------
    # Result
    # --------------------------------------------------------

    if solution is None:

        print()
        print("=" * 65)
        print("NO SOLUTION FOUND")
        print("=" * 65)

        print(
            """
The current state cannot be solved using the rules entered.

Check:
  - board positions
  - waste card
  - stock order
  - A/K rule
"""
        )

    else:

        print_solution(
            solution,
            waste,
        )


if __name__ == "__main__":
    main()
