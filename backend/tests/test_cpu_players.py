import asyncio
import dataclasses
import logging

import pytest

from wildjoker.cpu import EASY, EXPERT, LEVELS, CpuPlayers
from wildjoker.cpu.player import STUCK_REACTIONS
from wildjoker.cpu.simulate import InlineExecutor, VirtualTimeLoop, run
from wildjoker.server import protocol as p
from wildjoker.server.rooms import Room, Seat, Settings

from .conftest import codes, make_game

PATIENT = dataclasses.replace(
    EXPERT, name="patient", smarts=dataclasses.replace(EXPERT.smarts, patience=6.0)
)


def virtual(coro):
    return asyncio.run(coro, loop_factory=VirtualTimeLoop)


async def _inline(fn, *args):
    return fn(*args)


class Table:
    """A room with a human seat "h" (driven by the test) and a CPU seat "c"."""

    def __init__(self, level, hands, table=(), deck="", opened="hc", **settings):
        loop = asyncio.get_running_loop()
        self.loop = loop
        self.settings = Settings(clock=loop.time, executor=InlineExecutor(), **settings)
        self.room = Room("TEST", self.settings)
        self.room.seats = {"h": Seat("h", "Human", "t1"), "c": Seat("c", "CPU", "t2", cpu=level)}
        self.room.host = "h"
        self.cpus = CpuPlayers({**LEVELS, "patient": PATIENT}, seed=1, run_blocking=_inline)
        self.cpus.watch(self.room)
        self.game = make_game(hands, table=table, deck=deck, opened=opened)
        self.room.game = self.game
        self.room.phase = "playing"
        self.start = loop.time()
        self.log = []  # (time, what changed) seen by listeners
        self.room.listeners.append(self._record)
        self.room.changed()

    def _record(self, room):
        self.log.append((self.loop.time(), len(self.game.deck), room.game and room.game.version))

    @property
    def cpu(self):
        entry = self.cpus.players.get(("TEST", "c"))
        return entry[0] if entry else None

    def hand(self, pid="c"):
        return " ".join(sorted(c.code for c in self.game.players[pid].hand))

    def piles(self):
        return sorted(codes(pile.cards) for pile in self.game.table.values())

    async def until(self, predicate, timeout=120.0):
        """Advance virtual time until ``predicate()`` holds."""
        end = self.loop.time() + timeout
        while not predicate():
            assert self.loop.time() < end, "timed out"
            await asyncio.sleep(0.05)

    async def close(self):
        await self.cpus.close()
        self.room.close()


def test_cpu_plays_a_move():
    async def main():
        t = Table("hard", {"h": "KS KD", "c": "8H 9H 2C"}, table=["5H 6H 7H"], deck="3D 4D")
        await t.until(lambda: t.hand() == "2C")
        assert t.piles() == ["5H 6H 7H 8H 9H"]
        assert len(t.game.deck) == 2  # no draw while it had a move
        assert 1.5 < t.loop.time() - t.start < 10  # reaction plus thinking time
        await t.close()

    virtual(main())


def draw_times(t):
    return [time for time, (_, deck, _), (_, prev, _) in _pairs(t.log) if deck < prev]


def test_cpu_draws_at_its_pace_when_stuck():
    async def main():
        deck = "9D 4S KH 7C JD 2H 5S QC 8D 3H 6C TS"
        t = Table("easy", {"h": "KS", "c": "2C"}, deck=deck, opened="")
        await asyncio.sleep(60)
        draws = draw_times(t)
        assert 4 <= len(draws) <= 8
        gaps = [b - a for a, b in zip(draws, draws[1:], strict=False)]
        assert min(gaps) >= 8.0  # Easy draws every 8-12 s at most
        assert sum(t.cpu.stats.errors.values()) == 0
        await t.close()

    virtual(main())


def test_unopened_cpu_catches_up_once_a_human_has_opened():
    async def main():
        deck = " ".join(["9D 4S KH 7C JD 2H 5S QC 8D 3H 6C TS"] * 3)
        t = Table("easy", {"h": "KS", "c": "2C"}, deck=deck, opened="")
        await asyncio.sleep(30)
        before = len(draw_times(t))
        # The human opens: the CPU now draws three times as fast.
        t.game.players["h"].opened = True
        t.room.changed()
        switched = t.loop.time()
        await asyncio.sleep(30)
        after = [time for time in draw_times(t) if time > switched]
        assert len(after) >= 2.5 * before
        gaps = [b - a for a, b in zip(after, after[1:], strict=False)]
        assert min(gaps) >= 8.0 / 3 and max(gaps) <= 12.0 / 3 + 0.5
        assert sum(t.cpu.stats.errors.values()) == 0
        await t.close()

    virtual(main())


def test_opened_cpus_and_other_cpus_opening_dont_hurry():
    async def main():
        # Only a human opening counts; an opened CPU draws at its normal pace.
        deck = "9D 4S KH 7C JD 2H 5S QC 8D 3H 6C TS"
        t = Table("easy", {"h": "KS", "c": "2C 3C 4C 9H"}, deck=deck, opened="hc")
        await asyncio.sleep(60)
        gaps = [b - a for a, b in zip(draw_times(t), draw_times(t)[1:], strict=False)]
        assert gaps and min(gaps) >= 8.0
        await t.close()

    virtual(main())


def _pairs(log):
    for prev, cur in zip(log, log[1:], strict=False):
        yield cur[0], cur, prev


def test_cpu_opens():
    async def main():
        t = Table("medium", {"h": "KS", "c": "3S 4S 5S 6S 9D"}, deck="2D", opened="h")
        await t.until(lambda: t.game.players["c"].opened)
        assert t.piles() == ["3S 4S 5S 6S"]  # the longest run
        await t.close()

    virtual(main())


def test_cpu_plans_again_when_a_pile_gets_locked():
    async def main():
        t = Table("hard", {"h": "KS KD", "c": "8H 9H 2C"}, table=["5H 6H 7H"], deck="3D 4D")
        # The human grabs the pile while the CPU is working out its move.
        await t.until(lambda: t.cpu is not None and t.cpu.stats.search_seconds)
        t.room.act("h", p.Stage(type="stage", piles=[1]))
        await asyncio.sleep(5)
        assert t.hand() == "2C 8H 9H" and len(t.game.deck) == 2  # waits, doesn't draw
        t.room.act("h", p.Commit(type="commit", piles=[[c.id for c in t.game.table[1].cards]]))
        await t.until(lambda: t.hand() == "2C")
        assert sum(t.cpu.stats.errors.values()) == 0
        await t.close()

    virtual(main())


def test_cpu_votes_for_a_draw_when_stuck():
    async def main():
        t = Table("expert", {"h": "KS", "c": "2C"}, table=["5H 6H 7H"])
        await t.until(lambda: "c" in t.game.draw_votes)
        t.room.act("h", p.VoteDraw(type="vote_draw"))
        assert t.room.phase == "finished" and t.game.places == [["h", "c"]]
        await asyncio.sleep(1)
        assert t.cpus.players == {}
        await t.close()

    virtual(main())


def test_stuck_cpu_finds_a_hard_move_late_instead_of_voting():
    async def main():
        # Easy can't see that 7D fits by taking 7S and 7H off two runs.
        runs = ["4S 5S 6S 7S", "7H 8H 9H TH"]
        t = Table("easy", {"h": "KS", "c": "7D 2C"}, table=runs)
        await t.until(lambda: t.hand() == "2C")
        assert t.loop.time() - t.start >= STUCK_REACTIONS * EASY.speed.reaction[1]
        assert "c" not in t.game.draw_votes
        await t.until(lambda: "c" in t.game.draw_votes)  # now it's really stuck
        await t.close()

    virtual(main())


def test_cpu_with_a_move_does_not_vote():
    async def main():
        t = Table("medium", {"h": "KS", "c": "8H 2C"}, table=["5H 6H 7H"])
        await t.until(lambda: t.hand() == "2C")
        await t.until(lambda: "c" in t.game.draw_votes)  # now it is stuck
        await t.close()

    virtual(main())


def test_cpu_stops_when_the_seat_is_taken_back():
    async def main():
        t = Table("easy", {"h": "KS", "c": "2C"}, deck="9D 4S KH 7C JD", opened="h")
        await t.until(lambda: len(t.game.deck) < 5)
        t.room.seats["c"].cpu = None
        t.room.changed()
        deck = len(t.game.deck)
        await asyncio.sleep(60)
        assert len(t.game.deck) == deck and t.cpus.players == {}
        await t.close()

    virtual(main())


def test_cpu_takes_over_a_leaving_player():
    async def main():
        t = Table("easy", {"h": "8H 9H TH", "c": "2C"}, table=["5H 6H 7H"], deck="KD")
        t.room.handle("h", p.Leave(type="leave"))
        assert t.room.seats["h"].cpu == "medium"
        await t.until(lambda: t.game.players["h"].hand == [] or t.room.phase == "finished")
        assert t.game.places[0] == ["h"]
        await t.close()

    virtual(main())


def test_cpus_stop_when_the_room_closes_or_goes_back_to_the_lobby():
    async def main():
        t = Table("hard", {"h": "KS", "c": "2C"}, deck="9D 4S KH 7C JD", opened="h")
        await asyncio.sleep(0.1)
        assert t.cpu is not None
        t.room.close()
        await asyncio.sleep(0.1)
        assert t.cpus.players == {}

        t = Table("hard", {"h": "KS", "c": "2C"}, deck="9D 4S KH 7C JD", opened="h")
        t.room.phase, t.room.game = "lobby", None
        t.room.changed()
        await asyncio.sleep(0.1)
        assert t.cpus.players == {}
        await t.close()

    virtual(main())


def test_patience_holds_back_new_piles_until_racing():
    async def main():
        hand = "9S 9H 9D 2C 4D 6H KC QD"
        t = Table("patient", {"h": "AS 3C 5C 7S 8C TD JS KH", "c": hand}, deck="2S 3S 4S 5S")
        await t.until(lambda: len(t.game.players["c"].hand) < 8)
        patience = PATIENT.smarts.patience
        assert t.loop.time() - t.start >= patience and len(t.game.deck) == 4
        await t.close()

        t = Table("patient", {"h": "AS 3C", "c": hand}, deck="2S 3S 4S 5S")
        await t.until(lambda: len(t.game.players["c"].hand) < 8)
        assert t.loop.time() - t.start < patience / 2  # racing: the human has 2 cards
        await t.close()

    virtual(main())


def test_expert_plays_contested_moves_first():
    async def main():
        # 8H on the run could be taken by someone else; the set of 9s can't.
        hand = "9S 9H 9D 8H 2C 4D KC QD"
        t = Table("expert", {"h": "AS 3C 5C 7S 8C TD JS", "c": hand}, ["5H 6H 7H"], deck="2S")
        await t.until(lambda: len(t.game.players["c"].hand) < 8)
        assert "5H 6H 7H 8H" in t.piles()  # the first move takes the spot
        await t.until(lambda: len(t.game.players["c"].hand) < 5)
        assert t.piles() == ["5H 6H 7H 8H", "9S 9H 9D"]
        await t.close()

    virtual(main())


# -- simulated games ---------------------------------------------------------


def check_game(levels, decks, hand_size=5, seed=0):
    result = run(levels, decks, hand_size, seed)
    assert result.finished
    seated = sorted(pid for place in result.places for pid in place)
    assert seated == sorted(result.levels)
    for stats in result.stats.values():
        assert sum(stats.errors.values()) == 0, stats.errors
    return result


@pytest.mark.parametrize(
    "levels,decks",
    [
        (["easy", "expert"], 2),
        (["medium", "hard"], 1),
    ],
)
def test_simulated_games_finish(levels, decks, caplog):
    with caplog.at_level(logging.ERROR):
        check_game(levels, decks, seed=7)
    assert not caplog.records


ALL = ["easy", "medium", "hard", "expert"]


@pytest.mark.slow
@pytest.mark.parametrize("decks", [1, 2, 3])
@pytest.mark.parametrize("players", [2, 3, 4, 5, 6])
def test_simulated_games_finish_everywhere(players, decks, caplog):
    for seed in range(3):
        levels = [ALL[(seed + i) % 4] for i in range(players)]
        with caplog.at_level(logging.ERROR):
            check_game(levels, decks, seed=seed)
        assert not caplog.records


@pytest.mark.slow
def test_expert_beats_easy():
    games = 40
    wins = 0.0
    for seed in range(games):
        levels = ["easy", "expert"] if seed % 2 else ["expert", "easy"]
        result = check_game(levels, 2, seed=seed)
        winners = result.winners
        wins += sum(result.levels[w] == "expert" for w in winners) / len(winners)
    print(f"expert won {wins / games:.0%} against easy")
    assert wins / games >= 0.8
