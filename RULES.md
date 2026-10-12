# Wild Joker rules

A family card game: real-time rummy where everyone plays at once and the
table can be rearranged freely. This document is the reference for the game
engine, the CPU players and the tutorial. The app's other game, Gin, has
its own rules in [RULES-GIN.md](RULES-GIN.md).

## Cards

- 1, 2 or 3 standard 54-card decks, chosen when creating the game
  (default 2: 108 cards, including 4 jokers).
- Ranks: A, 2–10, J, Q, K in four suits. With several decks, every card
  exists once per deck.
- The ace can be low (A‑2‑3) or high (Q‑K‑A), never both in one run.

## Setup

- 2–8 players.
- Each player is dealt 5 cards (configurable when creating the game).
- The rest of the deck goes face down on the table as the draw pile.
- Everyone sees how many cards each player holds.

## Piles

Every pile on the table must always be one of:

- **Run:** 3–13 cards of one suit in consecutive rank order. Runs can't wrap
  around (K‑A‑2 is invalid), so the longest possible run is A through K.
- **Set:** 3–4 cards of the same rank, all of different suits (there can't be
  two identical cards).

A **joker** can stand in for any card, in any pile, any number of times. A
pile of three jokers is valid. Jokers count toward a set's maximum of 4. A
joker has no fixed value: it means whatever makes its current pile valid, and
that can change when the pile is rearranged.

## Play

There are no turns. Each player acts whenever they want.

### Before opening

A player who hasn't opened can only:

- **Draw** a card from the deck.
- **Open:** put down a run of 3 or more cards from their hand. The opening
  run can't contain jokers. Opening is a move of its own; nothing else
  happens in the same move.

### After opening

A player who has opened can, at any time:

- **Draw** a card from the deck, as often as they like.
- **Make a move** using their **staging area**:
  1. Take any number of piles off the table into the staging area.
  2. Rearrange freely there:
     - add cards from their hand to piles
     - start new piles from their hand (jokers allowed)
     - take cards from piles into their hand, including jokers (for
       example, swapping the real 5♥ for the joker in 4♥‑🃏‑6♥ and keeping
       the joker)
     - split a pile, with or without adding cards
       (1–10♥ → 1–4♥ and 5–10♥; or with your own 5♥ → A‑2‑3‑4‑5♥ and
       5–10♥)
     - merge piles and move cards between them
  3. Return the result to the table once every staged pile is valid. The
     number of piles returned can differ from the number taken.

  Cards taken from piles can stay in the player's hand. Starting new piles
  from the hand alone works the same way, with nothing taken from the
  table.

  While piles are in someone's staging area they are off the table: nobody
  else can touch them, and the other players see them greyed out with the
  staging player's name. A player can cancel at any time, and after 15
  seconds the staging is cancelled automatically. Cancelling puts the piles
  back on the table unchanged and returns any hand cards to the hand.

Invalid moves can't be made in the online game; there are no penalties.

### Empty deck

When the deck runs out, play continues without drawing.

## End of the game

- A player who has no cards left is out and takes the next finishing place.
  They stay in the game as a spectator.
- The game ends when only one player still has cards; that player finishes
  last.
- Finishing order is the only result. There are no points.
- **Stalemate:** if the deck is empty and no player can get rid of any more
  cards, the game ends in a draw. Players who are still in share the
  remaining places.
  - Players can almost always do *something* (for example take a card from
    a 4-card pile), so a stalemate means no player can make a move that
    leaves them with fewer cards.
  - Once the deck is empty and nobody has played for a while, the server
    searches the possible rearrangements in the background. It declares
    the draw only when it has proved that nobody can get rid of a card.
  - Once the deck is empty, the remaining players can also agree to end the
    game as a draw at any time.

## CPU players

CPU players follow the same rules. They don't draw repeatedly while they
still have a useful move. The deck is open to everyone, so humans may draw
as they please.
