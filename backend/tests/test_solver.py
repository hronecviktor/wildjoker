import random
from itertools import combinations

import pytest

from wildjoker.engine import Card, cards_from_codes, is_valid_pile
from wildjoker.solver import JOKER, solve


def brute_force(cards: list[Card]) -> int:
    """Most cards that can be placed in valid piles, by exhaustive search."""
    if len(cards) < 3:
        return 0
    first, rest = cards[0], cards[1:]
    best = brute_force(rest)  # first card stays in hand
    for size in range(2, len(rest) + 1):
        for others in combinations(range(len(rest)), size):
            pile = [first] + [rest[i] for i in others]
            if is_valid_pile(pile):
                remaining = [c for i, c in enumerate(rest) if i not in others]
                best = max(best, len(pile) + brute_force(remaining))
    return best


def check(solution, cards):
    used = [c for p in solution.piles for c in p]
    assert len(used) == len(set(used))
    assert set(used) <= set(cards)
    assert all(is_valid_pile(p) for p in solution.piles)


@pytest.mark.parametrize(
    "hand,placed",
    [
        ("", 0),
        ("2H 3H", 0),
        ("2H 3H 4H", 3),
        ("2H 3H 4H 9C", 3),
        ("QS QH QD QC", 4),
        ("QS QH QD QC QS", 4),
        ("AH 2H 3H 4H 5H 6H 7H 8H 9H TH JH QH KH", 13),
        ("QS KS AS 2S 3S", 3),  # Q-K-A and A-2-3 would need two aces
        ("QS KS AS 2S 3S AS", 6),
        ("JK JK JK", 3),
        ("5H JK 9C", 0),
        ("5H 7H JK", 3),
        ("5H 5S 5D 6H 7H", 3),  # 5H can be in the run or the set, not both
        ("5H 5S 5D 6H 7H 5H", 6),
    ],
)
def test_known_hands(hand, placed):
    cards = cards_from_codes(hand)
    solution = solve(cards)
    check(solution, cards)
    assert solution.placed == placed


def test_long_runs_are_merged():
    cards = cards_from_codes("AH 2H 3H 4H 5H 6H 7H 8H 9H TH")
    [pile] = solve(cards).piles
    assert len(pile) == 10


def test_weights_keep_jokers_back():
    cards = cards_from_codes("5H 6H JK 9S 9D")
    assert solve(cards).placed == 3
    assert solve(cards, weights={JOKER: -3}).placed == 0


@pytest.mark.parametrize("seed", range(150))
def test_matches_brute_force(seed):
    rng = random.Random(seed)
    # Draw from a narrow slice of two decks so piles are likely.
    low = rng.randint(1, 10)
    codes = [
        f"{'A23456789TJQK'[r - 1]}{s}"
        for r in range(low, low + 4)
        for s in rng.sample("SHDC", 2)
        for _ in range(2)
    ] + ["JK"] * 2
    cards = cards_from_codes(rng.sample(codes, rng.randint(5, 9)))
    solution = solve(cards)
    check(solution, cards)
    assert solution.placed == brute_force(cards)
