"""CPU players: one asyncio task per CPU seat, acting through ``Room.act``.

There are no turns. A CPU wakes up when the room changes (or when a timer it
set runs out), waits its reaction time, looks at what it may see (its own
hand and the table, through ``Room.view``), searches for a move off the
event loop, "thinks" for a while and then acts with the same messages a
human sends. If the table changed meanwhile and the move is no longer
possible, it looks again after its reaction time, so it never hammers the
room.

``CpuPlayers`` starts and stops these tasks as seats change hands and games
start and end.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..engine import Card, GameError
from ..server import protocol as p
from ..server.rooms import FAST_FORWARD
from .gin import GinCpuPlayer
from .levels import EXPERT, LEVELS, Level, Moves
from .moves import Move, Search, find_moves, openings

if TYPE_CHECKING:
    from ..server.rooms import Room, RoomManager

log = logging.getLogger(__name__)

FULL_SEARCH = EXPERT.moves

RunBlocking = Callable[..., Awaitable[Any]]
# Hands this small don't hold anything back.
CLOSE_TO_OUT = 5
# Racing CPUs react and think this much faster.
RACE_FACTOR = 0.5
# Once the deck is empty, a CPU whose own search finds nothing searches the
# whole table before voting for a draw. If that finds a move, it plays it
# after this many of its (slowest) reaction times: it took a while to spot.
STUCK_REACTIONS = 3
# Longest single sleep inside a pause, so a speed change applies quickly.
PAUSE_SLICE = 0.5
# A CPU that hasn't opened reacts and draws this many times faster once a
# human has opened, so it doesn't leave the human playing alone for long.
CATCH_UP_FACTOR = 3.0


@dataclass
class Stats:
    """What a CPU did, for tuning and reports."""

    actions: Counter = field(default_factory=Counter)
    # Seconds from noticing the change that led to an action to taking it.
    act_delays: list[float] = field(default_factory=list)
    # Wall-clock seconds and solver calls per search.
    search_seconds: list[float] = field(default_factory=list)
    solves: list[int] = field(default_factory=list)
    errors: Counter = field(default_factory=Counter)


class CpuPlayer:
    def __init__(
        self,
        room: Room,
        pid: str,
        level: Level,
        rng: random.Random | None = None,
        speed: float = 1.0,
        run_blocking: RunBlocking | None = None,
    ):
        self.room, self.pid, self.level = room, pid, level
        self.game = room.game
        self.rng = rng or random.Random()
        self._speed = speed
        self.run_blocking = run_blocking or self._in_executor
        self.stats = Stats()
        self._wake = asyncio.Event()
        self._wake.set()  # look at the table as soon as the task starts
        self._deadline: float | None = None  # look again then, even without a change
        self._last_draw: float | None = None
        self._draw_gap = 0.0  # this draw's interval, before speed-ups
        self._staging = False
        self._racing = False
        self._hurry = False  # not opened while a human has: catching up
        self._stuck_since: float | None = None
        self._first_seen: dict[tuple, float] = {}  # private moves held back
        self._cache: dict[tuple, Search] = {}

    @property
    def speed(self) -> float:
        """This CPU's speed, including the room's fast-forward."""
        return self._speed * (FAST_FORWARD if self.room.fast_forward else 1.0)

    def notify(self) -> None:
        """The room changed."""
        self._wake.set()

    async def run(self) -> None:
        try:
            while True:
                changed = await self._wait()
                noticed = self._now()
                if changed:
                    # Noticing a change takes the reaction time; a deadline
                    # the CPU set itself (e.g. its next draw) doesn't.
                    await self._pause(self._reaction())
                try:
                    await self._look(noticed)
                except GameError:
                    self._look_again()  # the room moved on meanwhile
        finally:
            self._cancel_staging()

    # -- one look at the table ---------------------------------------------

    async def _look(self, noticed: float) -> None:
        room = self.room
        if room.phase != "playing" or room.game is not self.game:
            return
        view = room.view(self.pid)
        game = view["game"]
        me = next(pl for pl in view["players"] if pl["id"] == self.pid)
        if me["place"] is not None:
            return
        if game["staging"]:
            # Left over from an interrupted move: put it back and look again.
            self._staging = True
            self._cancel_staging()
            self._look_again()
            return
        hand, deck = game["hand"], game["deck"]
        opponents = [
            pl["cards"] for pl in view["players"] if pl["id"] != self.pid and pl["place"] is None
        ]
        race_below = self.level.smarts.race_below
        self._racing = bool(race_below and opponents and min(opponents) <= race_below)

        self._hurry = not me["opened"] and any(
            pl["cpu"] is None and pl["opened"] for pl in view["players"]
        )
        if not me["opened"]:
            runs = openings(hand, self.level.smarts.open_longest)
            seen = [run for run in runs if not self._missed()]
            if seen:
                run = seen[0] if self.level.smarts.open_longest else self.rng.choice(seen)
                await self._pause(self._think_time(len(run), 0))
                if set(run) <= set(self._hand()):
                    self._act(p.Open(type="open", cards=run), "open", noticed)
                return
            if len(seen) < len(runs):
                self._look_again()
            else:
                self._idle(deck, can_shed=bool(runs), voted=self.pid in game["draw_votes"])
            return

        piles = tuple(
            (pile["id"], tuple(pile["cards"])) for pile in game["table"] if not pile["locked_by"]
        )
        search = await self._search(hand, piles, self._joker_weight(hand, deck))
        moves = search.moves
        if not deck:
            # Shuffling the table without shedding would keep an empty-deck
            # game going forever.
            moves = [m for m in moves if m.shed > 0]
        seen = [m for m in moves if not self._missed()]
        move, held = self._choose(seen, len(hand), deck)
        if move is not None:
            await self._play(move, noticed)
        elif len(seen) < len(moves):
            self._look_again()
        elif held:
            pass  # a held move sets its own deadline
        elif await self._blocked(hand, game["table"], deck):
            pass  # wait for the pile it wants instead of drawing
        elif not deck and await self._stuck(hand, piles, noticed):
            pass  # it plays a move it was slow to spot instead of voting
        else:
            can_shed = any(m.shed > 0 for m in moves)
            self._idle(deck, can_shed=can_shed, voted=self.pid in game["draw_votes"])

    async def _stuck(self, hand: list[int], piles: tuple, noticed: float) -> bool:
        """With the deck empty, whether the full search finds a shedding move.

        The move is played once the CPU has been stuck for a while; until
        then it waits (and doesn't vote for a draw).
        """
        if self.level.moves.kind == "full":
            return False  # its own search was the full one
        search = await self._search(hand, piles, 1.0, FULL_SEARCH)
        moves = [m for m in search.moves if m.shed > 0]
        if not moves:
            return False
        now = self._now()
        if self._stuck_since is None:
            self._stuck_since = now
        due = self._stuck_since + STUCK_REACTIONS * self.level.speed.reaction[1] / self.speed
        if now < due:
            self._deadline = due
        else:
            self._stuck_since = None
            await self._play(max(moves, key=lambda m: (m.shed, -len(m.stage))), noticed)
        return True

    async def _blocked(self, hand: list[int], table: list[dict], deck: int) -> bool:
        """Whether a pile someone else is staging would give it a move."""
        if not any(pile["locked_by"] for pile in table):
            return False
        piles = tuple((pile["id"], tuple(pile["cards"])) for pile in table)
        search = await self._search(hand, piles, self._joker_weight(hand, deck))
        return any(m.shed > 0 or deck for m in search.moves)

    def _choose(self, moves: list[Move], hand_size: int, deck: int) -> tuple[Move | None, bool]:
        """The move to play, and whether a move is being held back."""
        if not moves:
            return None, False
        going_out = [m for m in moves if m.shed == hand_size]
        if going_out:
            return going_out[0], False
        smarts = self.level.smarts
        held = False
        if smarts.patience and deck and not self._racing and hand_size > CLOSE_TO_OUT:
            now = self._now()
            current = {m.piles for m in moves if m.private}
            self._first_seen = {k: t for k, t in self._first_seen.items() if k in current}
            ready = []
            for m in moves:
                if not m.private:
                    ready.append(m)
                elif now - self._first_seen.setdefault(m.piles, now) >= smarts.patience:
                    ready.append(m)
                else:
                    held = True
                    due = self._first_seen[m.piles] + smarts.patience
                    self._deadline = due if self._deadline is None else min(self._deadline, due)
            moves = ready
        if not moves:
            return None, held
        if smarts.contested_first and not self._racing:
            # Spots on the table can be taken by someone else; the hand can wait.
            moves = [m for m in moves if not m.private] or moves
        if smarts.pick == "any":
            return self.rng.choice(moves), held
        return max(moves, key=lambda m: (m.value, -len(m.stage), -m.cards)), held

    def _joker_weight(self, hand: list[int], deck: int) -> float:
        real = sum(1 for i in hand if not Card(i).is_joker)
        if not deck or self._racing or real < 3:
            return 1.0  # nothing to save jokers for
        return self.level.smarts.joker_weight

    async def _search(
        self, hand: list[int], piles: tuple, joker_weight: float, moves: Moves | None = None
    ) -> Search:
        moves = moves or self.level.moves
        key = (tuple(hand), piles, joker_weight, moves)
        if key in self._cache:
            return self._cache[key]
        search = await self.run_blocking(find_moves, hand, piles, moves, joker_weight)
        self.stats.search_seconds.append(search.seconds)
        self.stats.solves.append(search.solves)
        if len(self._cache) >= 4:
            self._cache.clear()
        self._cache[key] = search
        return search

    # -- acting ------------------------------------------------------------

    async def _play(self, move: Move, noticed: float) -> None:
        await self._pause(self._think_time(move.cards, len(move.stage)))
        if not self._still_possible(move):
            self._look_again()
            return
        try:
            if move.stage:
                self._act(p.Stage(type="stage", piles=list(move.stage)), None, None)
                self._staging = True
                timeout = self.room.game.config.staging_timeout
                await self._pause(min(self.level.speed.stage_pause / self.speed, timeout / 4))
            commit = p.Commit(type="commit", piles=[list(pile) for pile in move.piles])
            self._act(commit, "commit", noticed)
        except GameError:
            self._look_again()
        finally:
            self._cancel_staging()

    def _still_possible(self, move: Move) -> bool:
        game = self.room.game
        if game is None or game is not self.game or self.room.phase != "playing":
            return False
        staged = set()
        for pile_id in move.stage:
            pile = game.table.get(pile_id)
            if pile is None or pile.locked_by is not None:
                return False
            staged |= {c.id for c in pile.cards}
        needed = {i for pile in move.piles for i in pile} - staged
        return needed <= set(self._hand())

    def _idle(self, deck: int, can_shed: bool, voted: bool) -> None:
        """Nothing to play: draw at the level's pace, or vote for a draw.

        Catching up (see ``CATCH_UP_FACTOR``) also shortens the wait for a
        draw that is already due.
        """
        if deck:
            now = self._now()
            gap = self._draw_gap / self.speed / (CATCH_UP_FACTOR if self._hurry else 1.0)
            due = now if self._last_draw is None else self._last_draw + gap
            if now >= due:
                self._act(p.Draw(type="draw"), "draw", None)
                self._last_draw = now
                self._draw_gap = self.rng.uniform(*self.level.speed.draw_interval)
            else:
                self._deadline = due
        elif not can_shed and not voted:
            self._act(p.VoteDraw(type="vote_draw"), "vote_draw", None)

    def _act(self, msg: p.Message, name: str | None, noticed: float | None) -> None:
        try:
            self.room.act(self.pid, msg)
        except GameError as e:
            self.stats.errors[e.code] += 1
            log.debug("cpu %s: %s failed: %s", self.pid, msg.type, e.code)
            raise
        if name:
            self.stats.actions[name] += 1
        if noticed is not None:
            self.stats.act_delays.append(self._now() - noticed)
        if isinstance(msg, p.Commit):
            self._staging = False

    def _cancel_staging(self) -> None:
        if not self._staging:
            return
        self._staging = False
        game = self.room.game
        if game is not None and self.pid in game.staging:
            with contextlib.suppress(GameError):
                self.room.act(self.pid, p.Cancel(type="cancel"))

    # -- time --------------------------------------------------------------

    async def _wait(self) -> bool:
        """Wait for a change or the CPU's own deadline; True if it was a change."""
        changed = True
        if not self._wake.is_set():
            timeout = None if self._deadline is None else max(0.0, self._deadline - self._now())
            try:
                await asyncio.wait_for(self._wake.wait(), timeout)
            except TimeoutError:
                changed = False
        self._wake.clear()
        self._deadline = None
        return changed

    def _look_again(self) -> None:
        """Look again after the reaction time even if nothing changes."""
        self._wake.set()

    def _reaction(self) -> float:
        delay = self.rng.uniform(*self.level.speed.reaction) / self.speed
        if self._hurry:
            delay /= CATCH_UP_FACTOR
        return delay * RACE_FACTOR if self._racing else delay

    def _think_time(self, cards: int, piles: int) -> float:
        speed = self.level.speed
        base = speed.think_base + speed.think_per_card * cards + speed.think_per_pile * piles
        delay = base * self.rng.uniform(0.8, 1.2) / self.speed
        return delay * RACE_FACTOR if self._racing else delay

    def _missed(self) -> bool:
        return self.rng.random() < self.level.moves.miss

    def _now(self) -> float:
        return self.room.settings.clock()

    async def _pause(self, seconds: float) -> None:
        """Sleep ``seconds`` at the current speed, in slices, so that switching
        fast-forward on or off takes effect during a long pause."""
        work = seconds * self.speed  # the pause at speed 1
        while work > 1e-9:
            step = min(work / self.speed, PAUSE_SLICE)
            await asyncio.sleep(step)
            work -= step * self.speed

    def _hand(self) -> list[int]:
        game = self.room.game
        return [c.id for c in game.players[self.pid].hand] if game else []

    async def _in_executor(self, fn, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.room.settings.executor, fn, *args)


class CpuPlayers:
    """Runs a ``CpuPlayer`` for every CPU seat still holding cards in a running game.

    Attach it to a ``RoomManager``; it watches every room through
    ``Room.listeners``. A CPU stops when its seat goes back to a human, when
    it goes out, when the game ends and when the room closes.
    """

    def __init__(
        self,
        levels: Mapping[str, Level] = LEVELS,
        seed: int | None = None,
        run_blocking: RunBlocking | None = None,
    ):
        self.levels = levels
        self.rng = random.Random(seed)
        self.run_blocking = run_blocking
        self.players: dict[tuple[str, str], tuple[CpuPlayer | GinCpuPlayer, asyncio.Task]] = {}

    def attach(self, manager: RoomManager) -> None:
        manager.on_room_created.append(self.watch)

    def watch(self, room: Room) -> None:
        room.listeners.append(self.update)
        self.update(room)

    def update(self, room: Room) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # plain unit tests drive rooms without a loop
        game = room.game
        wanted: dict[str, str] = {}
        # The tutorial's Teacher is scripted, not a CPU player.
        if room.phase == "playing" and game is not None and not room.closed and not room.tutorial:
            active = set(game.active)
            wanted = {s.id: s.cpu for s in room.seats.values() if s.cpu and s.id in active}
        for key, (player, task) in list(self.players.items()):
            code, pid = key
            if code != room.code or player.room is not room:
                continue
            if task.done() or wanted.get(pid) != player.level.name or player.game is not game:
                task.cancel()
                del self.players[key]
        for pid, level in wanted.items():
            if (room.code, pid) not in self.players:
                self._start(room, pid, self.levels[level])
        for (code, _), (player, _) in self.players.items():
            if code == room.code:
                player.notify()

    def _start(self, room: Room, pid: str, level: Level) -> None:
        rng = random.Random(self.rng.getrandbits(64))
        cls = GinCpuPlayer if room.kind == "gin" else CpuPlayer
        player = cls(room, pid, level, rng, room.settings.cpu_speed, self.run_blocking)
        task = asyncio.create_task(player.run(), name=f"cpu {room.code} {pid}")
        task.add_done_callback(_log_crash)
        self.players[room.code, pid] = (player, task)

    async def close(self) -> None:
        tasks = [task for _, task in self.players.values()]
        self.players.clear()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def _log_crash(task: asyncio.Task) -> None:
    if not task.cancelled() and task.exception() is not None:
        log.error("cpu player crashed", exc_info=task.exception())
