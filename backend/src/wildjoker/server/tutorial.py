"""The tutorial: a fixed, quick game against a scripted Teacher.

The player learns by doing, in this order (the client shows the steps and
asks the server for the Teacher's moves with ``tutorial_action``):

1. draw (6♥), and open with 4♥ 5♥ 6♥
2. the Teacher opens with A♦-6♦ and puts down a set of four 9s
3. draw (7♥) and add it to the hearts run
4. a new pile with a joker: Q♠ K♠ 🃏
5. split the Teacher's A♦-6♦ to fit their own 3♦: A♦2♦3♦ and 3♦4♦5♦6♦
6. the Teacher briefly holds the hearts run, showing a locked pile
7. take 9♣ from the set to make 8♣ 9♣ 10♣, which empties the hand

The Teacher never plays on its own, so the game can't go another way.
"""

from __future__ import annotations

import random

from ..engine import Config, Game, GameError, cards_from_codes
from ..engine.cards import full_deck
from ..engine.game import Player

PLAYER_HAND = "4H 5H QS KS JK 8C TC 3D"
TEACHER_HAND = "AD 2D 3D 4D 5D 6D 9S 9H 9D 9C KD"
# Drawn in this order.
DECK_TOP = "6H 7H"
TEACHER_OPENING = "AD 2D 3D 4D 5D 6D"
TEACHER_SET = "9S 9H 9D 9C"
# Moves have more time than the real 15 seconds while learning.
STAGING_TIMEOUT = 60.0
# How long the Teacher holds the player's run to show a locked pile.
BORROW_SECONDS = 4.0
DECKS = 2


def new_game(player: str, teacher: str) -> Game:
    """The tutorial deal: fixed hands, the deck's top cards in order."""
    cards = iter(cards_from_codes(" ".join([PLAYER_HAND, TEACHER_HAND, DECK_TOP])))
    take = lambda codes: [next(cards) for _ in codes.split()]  # noqa: E731
    player_hand, teacher_hand, top = take(PLAYER_HAND), take(TEACHER_HAND), take(DECK_TOP)
    used = {c.id for c in [*player_hand, *teacher_hand, *top]}
    rest = [c for c in full_deck(DECKS) if c.id not in used]
    random.Random(1).shuffle(rest)
    return Game(
        players={player: Player(player, player_hand), teacher: Player(teacher, teacher_hand)},
        deck=rest + top[::-1],  # the end of the list is the top
        config=Config(DECKS, len(player_hand), STAGING_TIMEOUT),
    )


def teacher_opens(game: Game, teacher: str) -> None:
    if game.players[teacher].opened:
        return
    game.open(teacher, _ids(game.players[teacher].hand, TEACHER_OPENING))
    game.commit(teacher, [_ids(game.players[teacher].hand, TEACHER_SET)], now=0.0)


def teacher_borrows(game: Game, teacher: str, now: float) -> bool:
    """Stage the player's hearts run, if it's free; True if it did."""
    for pile in game.table.values():
        if pile.locked_by is None and any(c.code == "4H" for c in pile.cards):
            try:
                game.stage(teacher, [pile.id], now)
            except GameError:
                return False
            return True
    return False


def teacher_returns(game: Game, teacher: str) -> None:
    if teacher in game.staging:
        game.cancel(teacher)


def _ids(hand, codes: str) -> list[int]:
    hand = list(hand)
    result = []
    for code in codes.split():
        card = next(c for c in hand if c.code == code)
        hand.remove(card)
        result.append(card.id)
    return result
