import asyncio
import copy
import random

import pytest

from wildjoker.cpu import CpuPlayers
from wildjoker.cpu.gin import (
    SMARTS,
    best_melds,
    candidate_melds,
    choose_discard,
    choose_draw,
    plan_plays,
)
from wildjoker.cpu.simulate import InlineExecutor, VirtualTimeLoop
from wildjoker.engine import cards_from_codes
from wildjoker.engine.gin import GinGame
from wildjoker.server.rooms import Room, Seat, Settings

from .conftest import codes
from .test_gin import discard_id, make_gin

MEDIUM = SMARTS["medium"]


def melds_text(melds):
    return sorted(codes(m) for m in melds)


def test_candidate_melds_use_jokers_for_gaps():
    found = melds_text(candidate_melds(cards_from_codes("4H 6H JK 9C")))
    assert "4H 6H JK" in found
    assert all("9C" not in m for m in found)


def test_best_melds_take_the_most_points():
    hand = cards_from_codes("QS KS AS AH AD 2C")
    # Q-K-A of spades (35) or three aces (45): not both, they share A♠.
    assert melds_text(best_melds(hand)) == ["AS AH AD"]


def test_the_discard_is_a_high_card_without_partners():
    hand = cards_from_codes("5H 6H KC 2D JK")
    chosen = choose_discard(hand, None, False, random.Random())
    assert codes(c for c in hand if c.id == chosen) == "KC"


def test_a_picked_card_is_never_discarded():
    hand = cards_from_codes("5H 6H KC")
    assert choose_discard(hand, hand[2].id, False, random.Random()) != hand[2].id


def test_takes_the_top_discard_when_it_makes_a_meld():
    game = make_gin({"a": "5H 6H KC", "b": "2D"}, discard="2S 7H", stock="3C")
    assert choose_draw(game, "a", MEDIUM) == discard_id(game, "7H")


def test_takes_the_top_discard_when_it_fits_the_table():
    game = make_gin({"a": "KC 2D", "b": "2D"}, discard="9H", stock="3C", melds=[("b", "6H 7H 8H")])
    assert choose_draw(game, "a", MEDIUM) == discard_id(game, "9H")


def test_draws_from_the_stock_otherwise():
    game = make_gin({"a": "5H 9C KC", "b": "2D"}, discard="2S", stock="3C")
    assert choose_draw(game, "a", MEDIUM) is None


def test_digs_for_a_deeper_discard_it_can_play():
    game = make_gin({"a": "5H 6H 2C", "b": "2D"}, discard="7H 9S", stock="3C")
    assert choose_draw(game, "a", MEDIUM) == discard_id(game, "7H")
    assert choose_draw(game, "a", SMARTS["easy"]) is None


def test_plans_melds_lay_offs_and_a_discard():
    game = make_gin(
        {"a": "4S 5S 6S 9H KC 2D", "b": "2C"},
        discard="3D",
        stock="TC",
        melds=[("b", "6H 7H 8H")],
        step="play",
    )
    plan = plan_plays(copy.deepcopy(game), "a", MEDIUM, random.Random(1))
    assert [codes_of(game, m) for m in plan.melds] == ["4S 5S 6S"]
    assert [(m, codes_of(game, ids)) for m, ids in plan.lay_offs] == [(1, "9H")]
    assert codes_of(game, [plan.discard]) == "KC"


def test_plans_to_go_out_by_keeping_one_card_back():
    game = make_gin({"a": "4S 5S 6S 7S", "b": "2C"}, discard="3D", stock="TC", step="play")
    sandbox = copy.deepcopy(game)
    plan = plan_plays(sandbox, "a", MEDIUM, random.Random(1))
    assert len(plan.melds) == 1 and len(plan.melds[0]) == 3
    sandbox.discard("a", plan.discard)
    assert sandbox.status == "round_over"


def test_plans_the_card_that_must_be_played():
    game = make_gin({"a": "5H 6H 5S 5D 2C", "b": "2D"}, discard="7H KD")
    game.take("a", discard_id(game, "7H"))
    sandbox = copy.deepcopy(game)
    plan = plan_plays(sandbox, "a", MEDIUM, random.Random(1))
    sandbox.discard("a", plan.discard)  # allowed: 7H went on the table


def codes_of(game, ids):
    every = {c.id: c for h in game.round.hands.values() for c in h}
    every |= {c.id: c for c in game.round.discard}
    return " ".join(every[i].code for i in ids)


# -- whole games -----------------------------------------------------------------


async def _inline(fn, *args):
    return fn(*args)


async def play_match(levels, seed, target=300):
    loop = asyncio.get_running_loop()
    settings = Settings(clock=loop.time, executor=InlineExecutor())
    room = Room("GINS", settings, kind="gin")
    room.seats = {
        f"c{i}": Seat(f"c{i}", f"CPU {i}", f"t{i}", cpu=level) for i, level in enumerate(levels)
    }
    cpus = CpuPlayers(seed=seed, run_blocking=_inline)
    cpus.watch(room)
    room.game = GinGame.new(list(room.seats), seed=seed, target=target)
    room.phase = "playing"
    room.changed()
    rounds = 0
    try:
        while room.phase == "playing":
            await asyncio.sleep(1.0)
            assert loop.time() < 24 * 3600, "stuck"
            if room.game.status == "round_over":
                rounds += 1
                room.game.next_round()  # what the host does
                room.changed()
    finally:
        await cpus.close()
        room.close()
    return room.game, rounds


@pytest.mark.parametrize("seed", range(4))
def test_cpus_play_whole_games(seed):
    game, rounds = asyncio.run(
        play_match(["easy", "medium", "expert"], seed), loop_factory=VirtualTimeLoop
    )
    assert game.status == "finished"
    assert game.scores[game.winner] >= 300
    assert rounds >= 1
