"""The Gin tutorial: one short round against a scripted Teacher.

The player learns by doing (the client shows the steps, see
``frontend/src/lib/ginTutorial.ts``, and asks for the Teacher's turns with
``tutorial_action``):

1. draw 7♥ from the deck, lay down 5♥ 6♥ 7♥, discard K♠
2. the Teacher draws, lays down 9♠ 9♥ 9♦ and discards 4♦
3. take 8♥ from the bottom of the discard pile (with K♠ and 4♦ above it),
   add it to the hearts run, add 9♣ to the Teacher's nines, discard 4♦
4. the Teacher draws and discards Q♦
5. draw 10♣, lay down 10♣ J♣ Q♣ and the joker, discard K♠: Gin

The game is played to 1 point, so that one round ends it and the end screen
shows the scores. The Teacher never plays on its own.
"""

from __future__ import annotations

import random
from collections.abc import Callable

from ..engine import cards_from_codes
from ..engine.cards import full_deck
from ..engine.gin import GinGame, Round
from . import protocol as p

PLAYER_HAND = "5H 6H 9C KS QC JC JK"
TEACHER_HAND = "9S 9H 9D 4D 2D 3S AC"
DISCARD = "8H"
# Drawn in this order: the player, the Teacher, the Teacher, the player.
STOCK_TOP = "7H 5S QD TC"
# The Teacher's turns: what it lays down, and what it discards.
TEACHER_TURNS = [("9S 9H 9D", "4D"), ("", "QD")]
TARGET = 1
# Pause between the Teacher's draw, meld and discard.
STEP_SECONDS = 0.9


def new_game(player: str, teacher: str) -> GinGame:
    groups = [PLAYER_HAND, TEACHER_HAND, DISCARD, STOCK_TOP]
    cards = iter(cards_from_codes(" ".join(groups)))
    take = lambda codes: [next(cards) for _ in codes.split()]  # noqa: E731
    player_hand, teacher_hand, discard, top = (take(g) for g in groups)
    used = {c.id for c in [*player_hand, *teacher_hand, *discard, *top]}
    rest = [c for c in full_deck(1) if c.id not in used]
    random.Random(1).shuffle(rest)
    rnd = Round(
        order=[player, teacher],
        dealer=teacher,
        hands={player: player_hand, teacher: teacher_hand},
        stock=rest + top[::-1],  # the end of the list is the top
        discard=discard,
        turn=player,
    )
    return GinGame([player, teacher], {player: 0, teacher: 0}, rnd, target=TARGET)


def teacher_turn(game: GinGame, teacher: str) -> list[Callable[[], p.Message]]:
    """The Teacher's next turn, as the messages to send one by one (each made
    when it's sent, from the hand at that time); [] if it isn't its turn."""
    rnd = game.round
    if game.status != "playing" or rnd.turn != teacher or rnd.step != "draw":
        return []
    played = any(c.code == "9S" for m in rnd.melds.values() for c in m.cards)
    meld, discard = TEACHER_TURNS[1 if played else 0]
    hand = lambda: game.hand(teacher)  # noqa: E731
    steps: list[Callable[[], p.Message]] = [lambda: p.Draw(type="draw")]
    if meld:
        steps.append(lambda: p.Meld(type="meld", cards=_ids(hand(), meld)))
    steps.append(lambda: p.Discard(type="discard", card=_ids(hand(), discard)[0]))
    return steps


def _ids(hand, codes: str) -> list[int]:
    hand = list(hand)
    result = []
    for code in codes.split():
        card = next(c for c in hand if c.code == code)
        hand.remove(card)
        result.append(card.id)
    return result
