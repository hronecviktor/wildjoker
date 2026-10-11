from wildjoker.engine import Game, cards_from_codes
from wildjoker.engine.game import Player


def make_game(hands: dict[str, str], table: list[str] = (), deck: str = "", opened=()) -> Game:
    """A game with fixed hands, table piles and deck (top of deck last).

    Codes are allocated across everything at once, so a code that appears
    twice gets cards from different decks.
    """
    groups = [*hands.values(), *table, deck]
    cards = iter(cards_from_codes(" ".join(groups).split()))
    take = lambda codes: [next(cards) for _ in codes.split()]  # noqa: E731
    players = {pid: Player(pid, take(codes), opened=pid in opened) for pid, codes in hands.items()}
    game = Game(players=players, deck=[])
    for codes in table:
        game._add_pile(take(codes))
    game.deck = take(deck)
    return game


def codes(cards) -> str:
    return " ".join(c.code for c in cards)
