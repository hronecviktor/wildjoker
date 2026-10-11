"""Best rearrangement of a set of cards into valid piles.

The question behind CPU moves and stalemate detection: given the cards of
some table piles plus a hand, which valid piles put the most cards (or the
most value) on the table? Cards left over go to the hand.

This is the Rummikub integer program (den Hertog & Hulshof, 2006), extended
with an ace that can be low or high:

- Pile templates: every set (3 or 4 distinct suits of one rank) and every
  run of 3, 4 or 5 consecutive ranks of one suit, ranks 1-14 with 14 being a
  high ace. Longer runs never need their own template because any run of 6+
  splits into runs of 3-5.
- ``x[t]``: how many copies of template t are used.
- ``z[t, s]``: how many of those copies fill slot s with a real card; the
  other ``x[t] - z[t, s]`` copies use a joker there.
- Each real card type and the jokers are limited by how many are available.

After solving, adjacent runs of one suit are merged back so the table isn't
littered with short runs, and real card ids are assigned to the slots.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import combinations

import highspy
import numpy as np

from ..engine.cards import Card, Suit
from ..engine.piles import ACE_HIGH, arrange

CardType = tuple[Suit, int]  # (suit, rank 1-13)
JOKER = "joker"
FEASIBLE = 2  # HiGHS primal_solution_status for a feasible solution


@dataclass(frozen=True, slots=True)
class Template:
    kind: str  # "run" or "set"
    slots: tuple[CardType, ...]  # rank 14 stands for the ace (rank 1)


def _templates() -> list[Template]:
    result = []
    for rank in range(1, 14):
        for size in (3, 4):
            for suits in combinations(Suit, size):
                result.append(Template("set", tuple((s, rank) for s in suits)))
    for suit in Suit:
        for length in (3, 4, 5):
            for low in range(1, ACE_HIGH - length + 2):
                ranks = range(low, low + length)
                result.append(Template("run", tuple((suit, r) for r in ranks)))
    return result


TEMPLATES = _templates()


def card_type(card: Card) -> CardType:
    return (card.suit, card.rank)


def _slot_type(slot: CardType) -> CardType:
    suit, rank = slot
    return (suit, 1 if rank == ACE_HIGH else rank)


@dataclass(frozen=True)
class Solution:
    piles: list[list[Card]]
    # Total weight of the cards placed (the number of cards with default weights).
    value: float

    @property
    def placed(self) -> int:
        return sum(len(p) for p in self.piles)


def solve(
    cards: Iterable[Card],
    weights: Mapping[CardType | str, float] | None = None,
    time_limit: float | None = None,
) -> Solution:
    """The valid piles that place the most weight from ``cards``.

    ``weights`` maps a card type or ``"joker"`` to its value when placed
    (default 1 for every card). A negative or zero weight makes the solver
    happy to keep that card back.
    """
    cards = list(cards)
    weights = weights or {}
    pools: dict[CardType | str, list[Card]] = defaultdict(list)
    for card in cards:
        pools[JOKER if card.is_joker else card_type(card)].append(card)
    jokers = len(pools[JOKER])

    # Templates that can be filled with what we have (at least one real card,
    # unless there are enough jokers to fill it alone).
    usable = []
    for t in TEMPLATES:
        real = sum(1 for s in t.slots if pools.get(_slot_type(s)))
        if real + jokers >= len(t.slots) and (real or jokers >= len(t.slots)):
            usable.append(t)
    if not usable:
        return Solution([], 0.0)

    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    if time_limit is not None:
        h.setOptionValue("time_limit", float(time_limit))
    inf = highspy.kHighsInf
    joker_weight = weights.get(JOKER, 1.0)

    # Columns: x[t] for each usable template, then z[t, s] for each slot.
    x_index = {}
    z_index: dict[tuple[int, int], int] = {}
    lower, upper, cost = [], [], []
    max_copies = len(cards) // 3
    for ti, t in enumerate(usable):
        x_index[ti] = len(cost)
        lower.append(0.0)
        # A template can't be used more often than its scarcest slot allows.
        scarcest = min(len(pools.get(_slot_type(s), ())) + jokers for s in t.slots)
        upper.append(float(min(max_copies, scarcest)))
        # Every slot filled by a joker scores the joker weight; real cards
        # add the difference to their own weight through z.
        cost.append(joker_weight * len(t.slots))
    for ti, t in enumerate(usable):
        for si, slot in enumerate(t.slots):
            available = len(pools.get(_slot_type(slot), ()))
            if not available:
                continue
            z_index[ti, si] = len(cost)
            lower.append(0.0)
            upper.append(float(available))
            cost.append(weights.get(_slot_type(slot), 1.0) - joker_weight)

    n = len(cost)
    h.addVars(n, np.array(lower), np.array(upper))
    h.changeColsIntegrality(
        n, np.arange(n, dtype=np.int32), np.array([highspy.HighsVarType.kInteger] * n)
    )
    h.changeColsCost(n, np.arange(n, dtype=np.int32), np.array(cost))
    h.changeObjectiveSense(highspy.ObjSense.kMaximize)

    def add_row(lo: float, hi: float, entries: list[tuple[int, float]]) -> None:
        idx = np.array([i for i, _ in entries], dtype=np.int32)
        val = np.array([v for _, v in entries])
        h.addRow(lo, hi, len(entries), idx, val)

    # z[t, s] <= x[t]
    for (ti, _), zi in z_index.items():
        add_row(-inf, 0.0, [(zi, 1.0), (x_index[ti], -1.0)])
    # Real cards of each type: sum of z over slots of that type <= available.
    by_type: dict[CardType, list[int]] = defaultdict(list)
    for (ti, si), zi in z_index.items():
        by_type[_slot_type(usable[ti].slots[si])].append(zi)
    for ctype, zs in by_type.items():
        add_row(-inf, float(len(pools[ctype])), [(zi, 1.0) for zi in zs])
    # Jokers: sum over templates of (len * x - sum z) <= jokers available.
    entries: dict[int, float] = defaultdict(float)
    for ti, t in enumerate(usable):
        entries[x_index[ti]] += len(t.slots)
    for zi in z_index.values():
        entries[zi] -= 1.0
    add_row(-inf, float(jokers), list(entries.items()))

    h.run()
    status = h.getModelStatus()
    found = status == highspy.HighsModelStatus.kOptimal or (
        status == highspy.HighsModelStatus.kTimeLimit
        and h.getInfo().primal_solution_status == FEASIBLE
    )
    if not found:
        return Solution([], 0.0)
    values = [round(v) for v in h.getSolution().col_value]

    # Build piles from the solution, assigning real cards and jokers.
    piles = [
        (t, [None] * len(t.slots))
        for ti, t in enumerate(usable)
        for _ in range(values[x_index[ti]])
    ]
    _fill(usable, values, x_index, z_index, pools, piles)
    merged = _merge_runs(piles)
    value = sum(weights.get(JOKER if c.is_joker else card_type(c), 1.0) for p in merged for c in p)
    return Solution(merged, value)


def _fill(usable, values, x_index, z_index, pools, piles) -> None:
    """Put real cards into ``z`` slots and jokers into the rest."""
    pools = {k: list(v) for k, v in pools.items()}
    i = 0
    for ti, t in enumerate(usable):
        copies = values[x_index[ti]]
        for copy in range(copies):
            _, slots = piles[i]
            for si, slot in enumerate(t.slots):
                real = values[z_index[ti, si]] if (ti, si) in z_index else 0
                if copy < real:
                    slots[si] = pools[_slot_type(slot)].pop()
                else:
                    slots[si] = pools[JOKER].pop()
            i += 1


def _merge_runs(piles: list[tuple[Template, list[Card]]]) -> list[list[Card]]:
    """Join runs of one suit that continue each other, keeping piles valid."""
    runs: dict[Suit, list[tuple[int, int, list[Card]]]] = defaultdict(list)
    result = []
    for t, cards in piles:
        if t.kind == "run":
            suit = t.slots[0][0]
            runs[suit].append((t.slots[0][1], t.slots[-1][1], cards))
        else:
            result.append(cards)
    for suit_runs in runs.values():
        suit_runs.sort(key=lambda r: r[0])
        merged: list[tuple[int, int, list[Card]]] = []
        for low, high, cards in suit_runs:
            if merged and merged[-1][1] + 1 == low:
                prev_low, _, prev_cards = merged[-1]
                candidate = prev_cards + cards
                if arrange(candidate) is not None:
                    merged[-1] = (prev_low, high, candidate)
                    continue
            merged.append((low, high, cards))
        result.extend(cards for _, _, cards in merged)
    return result
