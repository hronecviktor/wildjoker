"""Finding CPU moves: pure functions on what a player may see.

The input is the player's hand and the unlocked table piles, as card ids, so
a search can run in another process. A ``Move`` is exactly what the player
sends: the piles to stage and the piles to commit.

Staging locks piles and makes everyone else wait, so the search prefers
moves that touch few piles: the hand alone, then each pile with the hand,
then (for the higher levels) several piles together. Solving the hand with
all the candidate piles at once gives an upper bound on what any subset of
them can achieve, which skips the subset search on most looks.
"""

from __future__ import annotations

import functools
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from itertools import combinations

from ..engine import Card, arrange
from ..engine.piles import ACE_HIGH, find_opening
from ..solver import JOKER, card_type, solve
from .levels import Moves

TablePile = tuple[int, tuple[int, ...]]  # (pile id, card ids)
EPS = 1e-6
# Stop shrinking a move's staged piles after this many solver calls.
MAX_SHRINK_SOLVES = 8


@dataclass(frozen=True)
class Move:
    stage: tuple[int, ...]  # pile ids to stage
    piles: tuple[tuple[int, ...], ...]  # the piles to commit, as card ids
    shed: int  # how many fewer cards the hand holds afterwards
    value: float  # gain in solver weight (``shed`` with default weights)
    cards: int  # hand cards played plus table cards taken, for thinking time

    @property
    def private(self) -> bool:
        """Only puts new piles down from the hand, touching nothing on the table."""
        return not self.stage


@dataclass
class Search:
    moves: list[Move] = field(default_factory=list)
    solves: int = 0
    seconds: float = 0.0


def _kind(card: Card):
    return JOKER if card.is_joker else card_type(card)


def _weight(card: Card, joker_weight: float) -> float:
    return joker_weight if card.is_joker else 1.0


def decode(
    hand: Sequence[Card],
    piles: Sequence[TablePile],
    solution: Iterable[Iterable[Card]],
    joker_weight: float = 1.0,
) -> Move | None:
    """Turn solver piles over ``hand`` plus ``piles`` into a commit.

    The solver works on card types and may hand back a table pile unchanged
    (or with an identical card from another deck), so solution piles matching
    a table pile's types leave that pile alone. Only the others are staged.
    """
    unmatched: dict[tuple, list[TablePile]] = defaultdict(list)
    for pile in piles:
        key = tuple(sorted(Counter(_kind(Card(i)) for i in pile[1]).items(), key=str))
        unmatched[key].append(pile)
    new_piles = []
    for cards in solution:
        cards = list(cards)
        key = tuple(sorted(Counter(_kind(c) for c in cards).items(), key=str))
        if unmatched.get(key):
            unmatched[key].pop()
        else:
            new_piles.append(cards)
    staged = [pile for group in unmatched.values() for pile in group]
    if not new_piles and not staged:
        return None

    # Real card ids: staged cards first (they stay on the table), then the hand.
    pool: dict[object, list[Card]] = defaultdict(list)
    for card in hand:
        pool[_kind(card)].append(card)
    for _, ids in staged:
        for i in ids:
            pool[_kind(Card(i))].append(Card(i))
    committed = []
    for cards in new_piles:
        committed.append(tuple(pool[_kind(c)].pop().id for c in cards))
    used = {i for pile in committed for i in pile}
    staged_ids = {i for _, ids in staged for i in ids}
    placed = [Card(i) for i in used]
    taken = [Card(i) for i in staged_ids]
    value = sum(_weight(c, joker_weight) for c in placed) - sum(
        _weight(c, joker_weight) for c in taken
    )
    return Move(
        stage=tuple(sorted(pid for pid, _ in staged)),
        piles=tuple(committed),
        shed=len(used) - len(staged_ids),
        value=value,
        cards=len(used - staged_ids) + len(staged_ids - used),
    )


def additions(hand: Sequence[Card], piles: Sequence[TablePile]) -> list[Move]:
    """For each pile, the hand cards that can be added to it one by one."""
    moves = []
    for pid, ids in piles:
        pile = [Card(i) for i in ids]
        rest = list(hand)
        added = True
        while added:
            added = False
            for card in rest:
                if arrange([*pile, card]) is not None:
                    pile.append(card)
                    rest.remove(card)
                    added = True
                    break
        n = len(pile) - len(ids)
        if n:
            moves.append(Move((pid,), (tuple(c.id for c in pile),), n, float(n), n))
    return moves


def is_split(move: Move, piles: Sequence[TablePile]) -> bool:
    """Whether a staged pile ends up spread over several piles of 2+ cards."""
    staged = {pid: ids for pid, ids in piles if pid in move.stage}
    for ids in staged.values():
        kinds = Counter(_kind(Card(i)) for i in ids)
        holders = 0
        for new in move.piles:
            common = kinds & Counter(_kind(Card(i)) for i in new)
            if sum(common.values()) >= 2:
                holders += 1
        if holders > 1:
            return True
    return False


def _related(a: Card, b: Card) -> bool:
    if a.is_joker or b.is_joker:
        return False
    if a.rank == b.rank:
        return True
    if a.suit != b.suit:
        return False
    ranks_a = {a.rank, ACE_HIGH} if a.rank == 1 else {a.rank}
    ranks_b = {b.rank, ACE_HIGH} if b.rank == 1 else {b.rank}
    return min(abs(x - y) for x in ranks_a for y in ranks_b) <= 2


def relevant(hand: Sequence[Card], piles: Sequence[TablePile]) -> list[TablePile]:
    """Piles a hand card could interact with, most promising first."""
    scored = []
    has_real = any(not c.is_joker for c in hand)
    for pile in piles:
        cards = [Card(i) for i in pile[1]]
        score = sum(1 for h in hand if any(_related(h, c) for c in cards))
        if has_real and any(c.is_joker for c in cards):
            score += 1  # a joker that might be swapped out
        if score:
            scored.append((score, pile))
    scored.sort(key=lambda s: -s[0])
    return [pile for _, pile in scored]


class _Solver:
    """Counts and times solver calls for one search, within a time budget."""

    def __init__(self, hand: Sequence[Card], joker_weight: float, moves: Moves):
        self.hand, self.joker_weight = hand, joker_weight
        self.time_limit, self.budget = moves.time_limit, moves.search_time
        self.calls, self.seconds = 0, 0.0

    def __call__(self, piles: Sequence[TablePile]) -> Move | None:
        remaining = self.budget - self.seconds
        if remaining <= 0.01:
            return None
        ids = tuple(sorted([c.id for c in self.hand] + [i for _, pile in piles for i in pile]))
        start = time.perf_counter()
        if remaining >= self.time_limit:
            solution = _solve(ids, self.joker_weight, self.time_limit)
        else:
            solution = _solve.__wrapped__(ids, self.joker_weight, remaining)
        self.seconds += time.perf_counter() - start
        self.calls += 1
        return decode(self.hand, piles, solution, self.joker_weight)


@functools.lru_cache(maxsize=4096)
def _solve(ids: tuple[int, ...], joker_weight: float, time_limit: float) -> list[list[Card]]:
    """``solve``, remembered: the next look usually asks about the same piles again."""
    return solve([Card(i) for i in ids], {JOKER: joker_weight}, time_limit).piles


def _shrink(move: Move, piles: Sequence[TablePile], solver: _Solver) -> Move:
    """Drop staged piles the move's gain doesn't need, one at a time."""
    by_id = dict(piles)
    for pid in list(move.stage)[:MAX_SHRINK_SOLVES]:
        if len(move.stage) <= 1:
            break
        if pid not in move.stage:
            continue
        rest = [(p, by_id[p]) for p in move.stage if p != pid]
        smaller = solver(rest)
        if smaller is not None and smaller.value >= move.value - EPS:
            move = smaller
    return move


def find_moves(
    hand_ids: Sequence[int],
    piles: Sequence[TablePile],
    moves: Moves,
    joker_weight: float,
) -> Search:
    """Useful moves (positive gain) a CPU with these ``moves`` settings can find."""
    hand = [Card(i) for i in hand_ids]
    solver = _Solver(hand, joker_weight, moves)
    found: list[Move] = []

    def keep(move: Move | None) -> None:
        if move is not None and move.value > EPS and move not in found:
            found.append(move)

    keep(solver([]))  # new piles from the hand alone
    if moves.kind == "add":
        found += additions(hand, piles)
        return Search(found, solver.calls, solver.seconds)

    candidates = relevant(hand, piles)
    for pile in candidates[: moves.max_solves]:
        move = solver([pile])
        if move is not None and moves.kind == "take" and is_split(move, piles):
            continue
        keep(move)
    if moves.kind == "take" or not candidates:
        return Search(found, solver.calls, solver.seconds)

    best = max((m.value for m in found), default=0.0)
    # Solving with many piles at once bounds what any subset of them can do,
    # so the slow subset search only runs when it can gain something. Hard
    # bounds with the piles a hand card touches; Expert with the whole table,
    # since piles no hand card touches can still be moved to make room.
    pool = piles if moves.kind == "full" else candidates
    bound = solver(pool)
    if bound is None or bound.value <= best + EPS:
        return Search(found, solver.calls, solver.seconds)
    if len(bound.stage) <= moves.max_piles:
        keep(bound)
        return Search(found, solver.calls, solver.seconds)
    budget = solver.calls + moves.max_solves
    for size in range(2, min(3, moves.max_piles) + 1):
        for group in combinations(candidates, size):
            if solver.calls >= budget:
                break
            keep(solver(list(group)))
    best = max((m.value for m in found), default=0.0)
    if moves.kind == "full" and bound.value > best + EPS:
        keep(_shrink(bound, pool, solver))
    return Search(found, solver.calls, solver.seconds)


def openings(hand_ids: Sequence[int], longest: bool) -> list[list[int]]:
    """Possible opening runs: the longest one, or every 3-card run."""
    hand = [Card(i) for i in hand_ids]
    if longest:
        run = find_opening(hand)
        return [[c.id for c in run]] if run else []
    by_suit: dict[object, dict[int, Card]] = defaultdict(dict)
    for card in hand:
        if not card.is_joker:
            by_suit[card.suit][card.rank] = card
            if card.rank == 1:
                by_suit[card.suit][ACE_HIGH] = card
    runs = []
    for ranks in by_suit.values():
        for low in range(1, ACE_HIGH - 1):
            if all(r in ranks for r in (low, low + 1, low + 2)):
                runs.append([ranks[r].id for r in (low, low + 1, low + 2)])
    return runs
