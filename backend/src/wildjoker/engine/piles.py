"""Pile validation.

A pile is a multiset of cards; its order on the table is derived. ``arrange``
decides whether the cards form a valid run or set and returns one canonical
ordering, which is what the client displays. Jokers have no fixed value, so
the same pile may be arranged differently after it changes.

Canonical ordering (mirrored by the frontend, checked by
``shared/piles.json``):

- A pile with two or more natural cards of the same rank is a set; otherwise
  it is tried as a run first, then as a set.
- Runs are ordered low to high. An ace counts low when that works, high
  otherwise. Jokers fill gaps first; extra jokers extend the top of the run
  (up to the ace) and then the bottom.
- Sets list the natural cards by suit (S, H, D, C), then the jokers.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from .cards import Card, Suit

MIN_PILE = 3
MAX_RUN = 13
MAX_SET = 4
ACE_HIGH = 14


@dataclass(frozen=True, slots=True)
class Arrangement:
    kind: Literal["run", "set"]
    cards: tuple[Card, ...]
    # Runs: the rank each position stands for (1-14, 14 being a high ace).
    # Sets: the shared rank at every position. None for an all-joker pile.
    values: tuple[int, ...] | None
    # Runs: the suit of the run, None for an all-joker pile.
    suit: Suit | None = None


def arrange(cards: Iterable[Card]) -> Arrangement | None:
    """The canonical arrangement of a valid pile, or None if it is invalid."""
    cards = list(cards)
    naturals = [c for c in cards if not c.is_joker]
    if len(naturals) >= 2 and naturals[0].rank == naturals[1].rank:
        return _as_set(cards)
    return _as_run(cards) or _as_set(cards)


def is_valid_pile(cards: Iterable[Card]) -> bool:
    return arrange(cards) is not None


def is_valid_opening(cards: Iterable[Card]) -> bool:
    """An opening is a run of 3 or more cards without jokers."""
    cards = list(cards)
    if any(c.is_joker for c in cards):
        return False
    result = arrange(cards)
    return result is not None and result.kind == "run"


def _as_run(cards: list[Card]) -> Arrangement | None:
    n = len(cards)
    if not MIN_PILE <= n <= MAX_RUN:
        return None
    naturals = [c for c in cards if not c.is_joker]
    jokers = [c for c in cards if c.is_joker]
    if not naturals:
        return Arrangement("run", tuple(cards), tuple(range(1, n + 1)), None)

    suit = naturals[0].suit
    if any(c.suit != suit for c in naturals):
        return None
    if len({c.rank for c in naturals}) != len(naturals):
        return None

    has_ace = any(c.rank == 1 for c in naturals)
    for ace_value in (1, ACE_HIGH) if has_ace else (1,):
        by_value = {(ace_value if c.rank == 1 else c.rank): c for c in naturals}
        lo, hi = min(by_value), max(by_value)
        if hi - lo + 1 > n:
            continue
        # Extra jokers extend the top first (up to a high ace), then the bottom.
        top = min(ACE_HIGH, lo + n - 1)
        bottom = top - n + 1
        spare = iter(jokers)
        ordered = [by_value[v] if v in by_value else next(spare) for v in range(bottom, top + 1)]
        return Arrangement("run", tuple(ordered), tuple(range(bottom, top + 1)), suit)
    return None


def _as_set(cards: list[Card]) -> Arrangement | None:
    n = len(cards)
    if not MIN_PILE <= n <= MAX_SET:
        return None
    naturals = [c for c in cards if not c.is_joker]
    jokers = [c for c in cards if c.is_joker]
    ranks = {c.rank for c in naturals}
    if len(ranks) > 1:
        return None
    if len({c.suit for c in naturals}) != len(naturals):
        return None
    rank = ranks.pop() if ranks else None
    ordered = sorted(naturals, key=lambda c: c.suit) + jokers
    values = (rank,) * n if rank is not None else None
    return Arrangement("set", tuple(ordered), values)


def find_opening(cards: Iterable[Card]) -> list[Card] | None:
    """The longest joker-free run in ``cards``, or None if there is none."""
    by_suit: dict[Suit, dict[int, Card]] = {}
    for card in cards:
        if not card.is_joker:
            ranks = by_suit.setdefault(card.suit, {})
            ranks[card.rank] = card
            if card.rank == 1:
                ranks[ACE_HIGH] = card
    best: list[Card] = []
    for ranks in by_suit.values():
        run: list[Card] = []
        for value in range(1, ACE_HIGH + 1):
            if value in ranks and len(run) < MAX_RUN:
                run.append(ranks[value])
            else:
                run = [ranks[value]] if value in ranks else []
            if len(run) > len(best):
                best = list(run)
    return best if len(best) >= MIN_PILE else None
