# Real-machine facts (from Bill's own photos, 3 Oct 2026)

Source: seven photos of a real Tri Towers machine, supplied by Bill Hart (private; the photos and the deals read from them are not in this repo). Facts below were checked on three draw/board pairs and one unpaired draw.

- The machine plays a **53-card set**: 52 normal cards plus **one joker**, which is always the bottom card of the stock.
- Deal order (the "full draw" screen): its first two display rows contain 14 cards each. Read them left to right, top row first, into board positions 1-28. Positions 1-18 become the three covered tower rows (3 + 6 + 9); positions 19-28 become the exposed base row. The third display row is the deck.
- The deck row shows 25 cards: the joker at the left end, then 24 real cards. The rightmost card is the waste card shown face up on the board.
- The stock counter on the board reads 24 at the start. That is the deck row minus the waste card: 23 real cards plus the joker. The current app includes the joker in its stock count, so enter 24 and enable the joker setting for a fresh game.
- On all three pairs, the 10 base-row cards on the board equal draw positions 19-28 in the same left-to-right order, and the waste equals the last deck-row card.
- Draw direction from the waste to the joker (right to left in the deck row) is inferred from the layout, not observed. All four deals are solvable under it.
- Joker rules (Bill, 3 Oct 2026): it is always the last card in the stock, it plays onto any waste card, and any card plays onto it. A card played onto the joker becomes the waste as normal. The game is lost only when the stock is empty and no board card can play. The solver and web app model this; known-deal stock uses `*` as its final card.
