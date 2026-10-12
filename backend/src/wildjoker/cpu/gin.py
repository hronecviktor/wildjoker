"""CPU players for Gin.

On its turn a CPU waits its reaction time, then:

1. draws: the top discard if it makes a meld or fits one on the table,
   a deeper discard if that one can be played and doesn't bring too many
   other cards with it (not on Easy), otherwise the stock;
2. puts down the most valuable melds it can make from its hand, then adds
   every card it can to melds on the table (playing cards scores them and
   saves their points in the hand);
3. discards the card it needs least: a high card with no partner in the hand.

Moves are planned on a copy of the game with the engine's own actions, so
the plan never breaks a rule, then played one by one with short pauses so
the others can follow. Like the Wild Joker CPUs it only sees its own hand,
the table and the discard pile.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import logging
import random
from dataclasses import dataclass
from itertools import combinations
from typing import TYPE_CHECKING

from ..engine import Card, GameError, arrange
from ..engine.gin import GinGame, points
from ..server import protocol as p
from .levels import Level

if TYPE_CHECKING:
    from ..server.rooms import Room

log = logging.getLogger(__name__)

# Pause between plays within a turn, at normal speed.
PLAY_PAUSE = 0.9
# Search limit for the best set of melds in a hand.
MAX_NODES = 20_000


@dataclass(frozen=True)
class GinSmarts:
    # Takes deeper discards when it can play them, bringing at most this many
    # cards in all (0: never).
    deep_take: int
    # Chance of overlooking a card it could add to a meld on the table.
    miss_lay_off: float
    # Discards a random spare card instead of the highest one.
    careless_discard: bool


SMARTS = {
    "easy": GinSmarts(deep_take=0, miss_lay_off=0.3, careless_discard=True),
    "medium": GinSmarts(deep_take=3, miss_lay_off=0.1, careless_discard=False),
    "hard": GinSmarts(deep_take=5, miss_lay_off=0.0, careless_discard=False),
    "expert": GinSmarts(deep_take=8, miss_lay_off=0.0, careless_discard=False),
}


# -- planning (pure, on copies of the game) -------------------------------------


@dataclass
class Plan:
    draw: int | None  # a discard to take, or None for the stock
    melds: list[list[int]]
    lay_offs: list[tuple[int, list[int]]]  # (meld id, cards)
    discard: int | None  # None if the round ended (the stock ran out)


def candidate_melds(hand: list[Card]) -> list[tuple[Card, ...]]:
    """Every valid meld that can be made from the hand (jokers fill gaps)."""
    jokers = [c for c in hand if c.is_joker]
    naturals = [c for c in hand if not c.is_joker]
    found: set[frozenset[int]] = set()
    out: list[tuple[Card, ...]] = []

    def add(cards: list[Card]) -> None:
        key = frozenset(c.id for c in cards)
        if key not in found and arrange(cards) is not None:
            found.add(key)
            out.append(tuple(cards))

    by_rank: dict[int, list[Card]] = {}
    for c in naturals:
        by_rank.setdefault(c.rank, []).append(c)
    for same in by_rank.values():
        for size in range(1, len(same) + 1):
            for subset in combinations(same, size):
                for j in range(0, len(jokers) + 1):
                    if 3 <= size + j <= 4:
                        add([*subset, *jokers[:j]])
    by_suit: dict[int, dict[int, Card]] = {}
    for c in naturals:
        ranks = by_suit.setdefault(c.suit, {})
        ranks[c.rank] = c
        if c.rank == 1:
            ranks[14] = c
    for ranks in by_suit.values():
        for low in range(1, 13):
            for high in range(low + 2, min(14, low + 12) + 1):
                cards = [ranks[v] for v in range(low, high + 1) if v in ranks]
                gaps = high - low + 1 - len(cards)
                if cards and gaps <= len(jokers) and len({c.id for c in cards}) == len(cards):
                    add([*cards, *jokers[:gaps]])
    return out


def best_melds(hand: list[Card]) -> list[tuple[Card, ...]]:
    """Disjoint melds from the hand worth the most points."""
    candidates = sorted(candidate_melds(hand), key=lambda m: -sum(points(c) for c in m))
    by_card: dict[int, list[int]] = {}
    for i, meld in enumerate(candidates):
        for c in meld:
            by_card.setdefault(c.id, []).append(i)
    best: tuple[int, list[int]] = (0, [])
    nodes = 0

    def search(used: frozenset[int], chosen: list[int], value: int, start: int) -> None:
        nonlocal best, nodes
        nodes += 1
        if value > best[0]:
            best = (value, list(chosen))
        if nodes > MAX_NODES:
            return
        for i in range(start, len(candidates)):
            meld = candidates[i]
            if any(c.id in used for c in meld):
                continue
            chosen.append(i)
            search(used | {c.id for c in meld}, chosen, value + sum(points(c) for c in meld), i + 1)
            chosen.pop()

    search(frozenset(), [], 0, 0)
    return [candidates[i] for i in best[1]]


def partners(card: Card, hand: list[Card]) -> int:
    """How many cards in the hand could go in a meld with this one."""
    if card.is_joker:
        return 99  # always useful
    count = 0
    for other in hand:
        if other.id == card.id:
            continue
        if other.is_joker or other.rank == card.rank:
            count += 1
        elif other.suit == card.suit:
            # An ace is next to both the 2 and the king.
            high = lambda c: 14 if c.rank == 1 else c.rank  # noqa: E731
            gap = min(abs(other.rank - card.rank), abs(high(other) - high(card)))
            if gap <= 2:
                count += 1
    return count


def choose_discard(hand: list[Card], picked: int | None, careless: bool, rng: random.Random) -> int:
    options = [c for c in hand if c.id != picked]
    if careless:
        spare = [c for c in options if partners(c, hand) == 0] or options
        return rng.choice(spare).id
    return min(options, key=lambda c: (partners(c, hand), -points(c), c.id)).id


def fits_table(card: Card, game: GinGame) -> bool:
    return any(arrange([*m.cards, card]) is not None for m in game.round.melds.values())


def choose_draw(game: GinGame, pid: str, smarts: GinSmarts) -> int | None:
    rnd = game.round
    hand = rnd.hands[pid]
    top = rnd.discard[-1] if rnd.discard else None
    if top is not None:
        with_top = [*hand, top]
        if fits_table(top, game) or any(top in m for m in candidate_melds(with_top)):
            return top.id
    if smarts.deep_take:
        best: tuple[int, int] | None = None
        for depth, card in enumerate(rnd.discard[:-1]):
            taken = rnd.discard[depth:]
            if len(taken) > smarts.deep_take or not game.can_take(pid, card.id):
                continue
            gain = sum(points(c) for m in best_melds([*hand, *taken]) for c in m)
            gain -= sum(points(c) for m in best_melds(hand) for c in m)
            if gain > 0 and (best is None or gain > best[0]):
                best = (gain, card.id)
        if best is not None:
            return best[1]
    if not rnd.stock and len(rnd.discard) <= 1 and top is not None:
        return top.id  # nothing to draw: the top discard is all there is
    return None


def plan_plays(game: GinGame, pid: str, smarts: GinSmarts, rng: random.Random) -> Plan:
    """Plays after drawing, tried out on ``game`` (pass a copy)."""
    plan = Plan(None, [], [], None)
    for meld in best_melds(game.hand(pid)):
        ids = [c.id for c in meld]
        if _try(lambda ids=ids: game.meld(pid, ids)):
            plan.melds.append(ids)
            continue
        # Kept back as the last card to discard: try the meld without one card.
        for card in sorted(meld, key=lambda c: points(c)):
            rest = [c.id for c in meld if c.id != card.id]
            if _try(lambda rest=rest: game.meld(pid, rest)):
                plan.melds.append(rest)
                break
    changed = True
    while changed:
        changed = False
        for card in list(game.hand(pid)):
            if smarts.miss_lay_off and rng.random() < smarts.miss_lay_off:
                continue
            for meld_id in list(game.round.melds):
                if _try(lambda m=meld_id, c=card: game.lay_off(pid, m, [c.id])):
                    plan.lay_offs.append((meld_id, [card.id]))
                    changed = True
                    break
    if game.round.must_play is not None:
        _play_must(game, pid, plan)
    plan.discard = choose_discard(game.hand(pid), game.round.picked, smarts.careless_discard, rng)
    return plan


def _play_must(game: GinGame, pid: str, plan: Plan) -> None:
    """Find any play holding the card that has to go on the table."""
    must = next(c for c in game.hand(pid) if c.id == game.round.must_play)
    others = [c for c in game.hand(pid) if c.id != must.id]
    for meld_id in list(game.round.melds):
        for extra in [None, *others]:
            ids = [must.id] if extra is None else [must.id, extra.id]
            if _try(lambda m=meld_id, ids=ids: game.lay_off(pid, m, ids)):
                plan.lay_offs.append((meld_id, ids))
                return
    for a, b in combinations(others, 2):
        ids = [must.id, a.id, b.id]
        if _try(lambda ids=ids: game.meld(pid, ids)):
            plan.melds.append(ids)
            return


def _try(action) -> bool:
    try:
        action()
    except GameError:
        return False
    return True


# -- the player ------------------------------------------------------------------


class GinCpuPlayer:
    """One CPU seat in a Gin room, as an asyncio task (see ``CpuPlayers``)."""

    def __init__(
        self,
        room: Room,
        pid: str,
        level: Level,
        rng: random.Random | None = None,
        speed: float = 1.0,
        run_blocking=None,
    ):
        self.room, self.pid, self.level = room, pid, level
        self.game: GinGame = room.game
        self.rng = rng or random.Random()
        self.speed = speed
        self.smarts = SMARTS.get(level.name, SMARTS["medium"])
        self._wake = asyncio.Event()
        self._wake.set()

    def notify(self) -> None:
        self._wake.set()

    async def run(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            if not self._my_turn():
                continue
            await self._pause(self.rng.uniform(*self.level.speed.reaction) / 2)
            try:
                await self._turn()
            except GameError:
                # The plan went stale (it shouldn't): end the turn any legal way.
                self._discard_anything()
            self._wake.set()  # look again: the turn may still be ours

    def _my_turn(self) -> bool:
        game = self.room.game
        return (
            game is self.game
            and self.room.phase == "playing"
            and game.status == "playing"
            and game.round.turn == self.pid
        )

    async def _turn(self) -> None:
        game = self.game
        rnd = game.round
        if rnd.step == "draw":
            take = choose_draw(game, self.pid, self.smarts)
            if take is None:
                self._act(p.Draw(type="draw"))
            else:
                self._act(p.Take(type="take", card=take))
            if not self._my_turn():
                return  # the stock ran out and ended the round
            await self._pause(self._think())
        plan = plan_plays(copy.deepcopy(game), self.pid, self.smarts, self.rng)
        for ids in plan.melds:
            self._act(p.Meld(type="meld", cards=ids))
            await self._pause(PLAY_PAUSE)
        for meld_id, ids in plan.lay_offs:
            self._act(p.LayOff(type="lay_off", pile=meld_id, cards=ids))
            await self._pause(PLAY_PAUSE)
        if plan.discard is not None:
            self._act(p.Discard(type="discard", card=plan.discard))

    def _discard_anything(self) -> None:
        if not self._my_turn() or self.game.round.step != "play":
            return
        for card in self.game.hand(self.pid):
            with contextlib.suppress(GameError):
                self._act(p.Discard(type="discard", card=card.id))
                return

    def _act(self, msg: p.Message) -> None:
        try:
            self.room.act(self.pid, msg)
        except GameError as e:
            log.debug("gin cpu %s: %s failed: %s", self.pid, msg.type, e.code)
            raise

    def _think(self) -> float:
        speed = self.level.speed
        return (speed.think_base + speed.think_per_card * 3) * self.rng.uniform(0.8, 1.2)

    async def _pause(self, seconds: float) -> None:
        await asyncio.sleep(seconds / self.speed)
