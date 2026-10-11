"""Cards and decks.

Every card in a game has a unique integer id: ``deck * 54 + index``, where
index 0-51 are the suited cards (suit-major, ace first) and 52-53 the two
jokers. The id alone identifies the card, so the client can decode it the
same way (see ``shared/cards.md``).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import IntEnum

CARDS_PER_DECK = 54
SUITED_PER_DECK = 52


class Suit(IntEnum):
    SPADES = 0
    HEARTS = 1
    DIAMONDS = 2
    CLUBS = 3

    @property
    def letter(self) -> str:
        return "SHDC"[self]


RANK_LETTERS = {1: "A", 10: "T", 11: "J", 12: "Q", 13: "K"}


@dataclass(frozen=True, slots=True)
class Card:
    id: int

    @property
    def deck(self) -> int:
        return self.id // CARDS_PER_DECK

    @property
    def index(self) -> int:
        return self.id % CARDS_PER_DECK

    @property
    def is_joker(self) -> bool:
        return self.index >= SUITED_PER_DECK

    @property
    def suit(self) -> Suit | None:
        return None if self.is_joker else Suit(self.index // 13)

    @property
    def rank(self) -> int | None:
        """1 (ace) to 13 (king); None for a joker."""
        return None if self.is_joker else self.index % 13 + 1

    @property
    def code(self) -> str:
        """Deck-independent name such as ``"AH"``, ``"TS"`` or ``"JK"``."""
        if self.is_joker:
            return "JK"
        return f"{RANK_LETTERS.get(self.rank, str(self.rank))}{self.suit.letter}"

    def __repr__(self) -> str:
        return f"Card({self.code}#{self.deck})"


def card_from_code(code: str, deck: int = 0, joker: int = 0) -> Card:
    """Build a card from its code; ``joker`` picks which of a deck's two jokers."""
    if code == "JK":
        return Card(deck * CARDS_PER_DECK + SUITED_PER_DECK + joker)
    rank_part, suit_letter = code[:-1], code[-1]
    letters = {v: k for k, v in RANK_LETTERS.items()}
    rank = letters[rank_part] if rank_part in letters else int(rank_part)
    suit = Suit("SHDC".index(suit_letter))
    return Card(deck * CARDS_PER_DECK + suit * 13 + rank - 1)


def cards_from_codes(codes: str | list[str]) -> list[Card]:
    """Cards from codes like ``"AH 2H JK"``; repeated codes come from the next deck."""
    if isinstance(codes, str):
        codes = codes.split()
    seen: dict[str, int] = {}
    cards = []
    for code in codes:
        n = seen.get(code, 0)
        seen[code] = n + 1
        if code == "JK":
            cards.append(card_from_code(code, deck=n // 2, joker=n % 2))
        else:
            cards.append(card_from_code(code, deck=n))
    return cards


def full_deck(decks: int) -> list[Card]:
    return [Card(i) for i in range(decks * CARDS_PER_DECK)]


def shuffled_deck(decks: int, rng: random.Random) -> list[Card]:
    cards = full_deck(decks)
    rng.shuffle(cards)
    return cards
