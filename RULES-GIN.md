# Gin rules

The family's turn-based rummy, played over several rounds to 500 points.
(It is closer to Rummy 500 than to classic Gin Rummy.) This document is the
reference for the engine (`backend/src/wildjoker/engine/gin.py`), the CPU
players and the in-game help. Runs, sets and jokers work as in
[RULES.md](RULES.md).

## Cards

- One 54-card deck, including 2 jokers.
- 2–6 players, 7 cards each.
- The rest of the deck is the face-down **stock**. Its top card is turned up
  to start the **discard pile** (the "community hand"), which is spread out
  so every card in it can be seen.

## Card values

| Card | Points |
|---|---|
| Joker | 25 |
| Ace | 15, or 5 as the low end of a run (A‑2‑3) |
| K, Q, J, 10 | 10 |
| 2–9 | 5 |

## Melds

- **Run:** 3 or more cards of one suit in a row. The ace is low (A‑2‑3) or
  high (Q‑K‑A), never both: runs don't wrap around (K‑A‑2 is not allowed).
- **Set:** 3 or 4 cards of the same rank.
- A **joker** stands in for any card, any number of times. Once on the
  table it stays there: it can't be swapped for the real card.

## A turn

The dealer moves one seat each round; the player after the dealer starts.
On your turn:

1. **Draw** one of:
   - the top card of the stock;
   - the top card of the discard pile, which you can't discard again this
     turn;
   - a deeper card of the discard pile, together with every card above it.
     That card must go on the table this turn, so you can only take it if
     you can play it, and you can't discard it.
2. **Play** (optional), as much as you like:
   - put down new melds from your hand;
   - add cards to any meld on the table, yours or anyone's. The points for
     a card belong to whoever put it down.
3. **Discard** one card onto the discard pile. This ends your turn. You
   always need a card left to discard: you can't put your last card on the
   table.

When a player is down to one card, everyone is told (the "Uno" call), so
they can get rid of their high cards.

When the stock runs out, the discard pile except its top card is shuffled
into a new stock. If the stock runs out again and nobody has put a card on
the table since the last time, the round ends without a winner and is
scored as usual.

## Scoring

A round ends when someone discards their last card (**Gin**). Every player
scores the points of the cards they put on the table, minus the points of
the cards left in their hand. There is no bonus for going out; the winner
simply has nothing left in hand. Scores can go below zero.

After a round in which someone reaches 500 points or more, the player with
the most points wins. If the top score is shared, another round is played.
