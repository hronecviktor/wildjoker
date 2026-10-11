"""CPU-only games on a virtual clock, for tests and tuning.

Games run through a real ``Room`` with real ``CpuPlayer`` tasks, but on an
event loop whose clock jumps straight to the next timer, and with searches
run inline, so a game of many minutes takes a fraction of a second and is
reproducible from its seed.

``python -m wildjoker.cpu.simulate --games 100 easy expert`` prints win
rates and timings.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import selectors
import statistics
import time
from collections import Counter, defaultdict
from collections.abc import Mapping
from concurrent.futures import Executor, Future
from dataclasses import dataclass, field

from ..engine import Config, Game
from ..server.rooms import Room, Settings
from .levels import LEVELS, Level
from .player import CpuPlayers, Stats

# Virtual seconds after which a game counts as stuck.
MAX_GAME_TIME = 6 * 3600.0


class _JumpingSelector(selectors.DefaultSelector):
    """Instead of sleeping until the next timer, moves the loop's clock there."""

    loop: VirtualTimeLoop

    def select(self, timeout=None):
        events = super().select(0)
        if events or timeout == 0:
            return events
        if timeout is None:
            return super().select(None)  # nothing scheduled: wait for real I/O
        self.loop.virtual_time += timeout
        return []


class VirtualTimeLoop(asyncio.SelectorEventLoop):
    def __init__(self):
        selector = _JumpingSelector()
        super().__init__(selector)
        selector.loop = self
        self.virtual_time = 0.0

    def time(self) -> float:
        return self.virtual_time


class InlineExecutor(Executor):
    """Runs submitted work right away, keeping a simulation deterministic."""

    def submit(self, fn, /, *args, **kwargs):
        future: Future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as e:
            future.set_exception(e)
        return future


async def _inline(fn, *args):
    return fn(*args)


@dataclass
class GameResult:
    levels: dict[str, str]  # player id -> level
    places: list[list[str]]
    duration: float  # virtual seconds
    stats: dict[str, Stats] = field(default_factory=dict)  # by player id
    finished: bool = True

    @property
    def stalemate(self) -> bool:
        return len(self.places[-1]) > 1

    @property
    def winners(self) -> list[str]:
        return self.places[0] if self.places else []


async def play(
    levels: list[str],
    decks: int = 2,
    hand_size: int = 5,
    seed: int = 0,
    catalog: Mapping[str, Level] = LEVELS,
) -> GameResult:
    """One game between CPUs of the given levels (names in ``catalog``, in seating order)."""
    loop = asyncio.get_running_loop()
    settings = Settings(clock=loop.time, executor=InlineExecutor())
    room = Room("SIMU", settings, decks=decks, hand_size=hand_size)
    cpus = CpuPlayers(catalog, seed=seed, run_blocking=_inline)
    cpus.watch(room)
    for i, level in enumerate(levels):
        room.add_seat(f"CPU {i + 1}", None, cpu=level)
    ids = list(room.seats)
    rng = random.Random(seed)
    finished = asyncio.Event()
    room.listeners.append(lambda r: r.phase == "finished" and finished.set())
    stats = {}
    room.listeners.append(
        lambda r: stats.update({pid: pl.stats for (_, pid), (pl, _) in cpus.players.items()})
    )
    config = Config(decks, hand_size, settings.staging_timeout)
    room.game = Game.new(ids, config, seed=rng.getrandbits(32))
    room.phase = "playing"
    start = loop.time()
    room.changed()
    try:
        await asyncio.wait_for(finished.wait(), MAX_GAME_TIME)
        done = True
    except TimeoutError:
        done = False
    await cpus.close()
    room.close()
    return GameResult(
        levels=dict(zip(ids, levels, strict=True)),
        places=room.game.places,
        duration=loop.time() - start,
        stats=stats,
        finished=done,
    )


def run(
    levels: list[str],
    decks: int = 2,
    hand_size: int = 5,
    seed: int = 0,
    catalog: Mapping[str, Level] = LEVELS,
) -> GameResult:
    """``play`` on a fresh virtual-time loop."""
    game = play(levels, decks, hand_size, seed, catalog)
    return asyncio.run(game, loop_factory=VirtualTimeLoop)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("levels", nargs="+", choices=sorted(LEVELS))
    parser.add_argument("--games", type=int, default=50)
    parser.add_argument("--decks", type=int, default=2)
    parser.add_argument("--hand", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    wins: Counter = Counter()
    stalemates = 0
    durations = []
    delays, searches, solves = defaultdict(list), defaultdict(list), defaultdict(list)
    start = time.perf_counter()
    for g in range(args.games):
        # Rotate seats so nobody always sits first.
        shift = g % len(args.levels)
        levels = args.levels[shift:] + args.levels[:shift]
        result = run(levels, args.decks, args.hand, seed=args.seed + g)
        assert result.finished, f"game {g} did not finish"
        durations.append(result.duration)
        stalemates += result.stalemate
        for pid in result.winners:
            wins[result.levels[pid]] += 1 / len(result.winners)
        for pid, stats in result.stats.items():
            level = result.levels[pid]
            delays[level] += stats.act_delays
            searches[level] += stats.search_seconds
            solves[level] += stats.solves
    elapsed = time.perf_counter() - start

    print(f"{args.games} games, {args.decks} decks, {args.hand} cards, {elapsed:.1f} s real time")
    print(f"average game {statistics.mean(durations) / 60:.1f} min, {stalemates} drawn")
    print(f"{'level':8} {'wins':>6} {'act s':>6} {'search ms':>10} {'max ms':>7} {'solves':>7}")
    for level in dict.fromkeys(args.levels):
        n = args.levels.count(level)
        share = wins[level] / args.games / n * len(args.levels)  # 1.0 = fair share
        mean = lambda xs: statistics.mean(xs) if xs else 0.0  # noqa: E731
        print(
            f"{level:8} {wins[level] / args.games:6.0%} {mean(delays[level]):6.1f}"
            f" {mean(searches[level]) * 1000:10.1f} {max(searches[level], default=0) * 1000:7.0f}"
            f" {mean(solves[level]):7.1f}   ({share:.2f}x fair share)"
        )


if __name__ == "__main__":
    main()
