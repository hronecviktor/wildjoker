"""The Gin tutorial plays out exactly as its steps describe."""

import pytest

from wildjoker.server import gin_tutorial

from .test_server import connect, http  # noqa: F401 (fixtures)
from .test_tutorial import codes, pick

pytestmark = pytest.mark.timeout(10)


def meld_with(state, code: str) -> dict:
    return next(m for m in state["game"]["melds"] if code in codes(m["cards"]))


def test_gin_tutorial_game(connect, monkeypatch):  # noqa: F811
    monkeypatch.setattr(gin_tutorial, "STEP_SECONDS", 0.01)
    me = connect()
    me.ok("tutorial", name="Viktor", teacher="Teacher", game="gin")
    state = me.wait(lambda c: c.state["phase"] == "playing")
    assert state["tutorial"] is True and state["kind"] == "gin"
    teacher = next(p["id"] for p in state["players"] if p["id"] != me.you)
    game = state["game"]
    assert sorted(codes(game["hand"])) == sorted(gin_tutorial.PLAYER_HAND.split())
    assert codes(game["discard"]) == ["8H"]
    assert game["turn"] == me.you and game["target"] == gin_tutorial.TARGET

    # The Teacher only moves on its turn.
    me.ok("tutorial_action", action="teacher_turn")
    me.ok("draw")
    assert "7H" in codes(me.wait(lambda c: len(c.state["game"]["hand"]) == 8)["game"]["hand"])
    me.ok("meld", cards=pick(me.state["game"]["hand"], "5H 6H 7H"))
    me.ok("discard", card=pick(me.state["game"]["hand"], "KS")[0])

    me.ok("tutorial_action", action="teacher_turn")
    me.ok("tutorial_action", action="teacher_turn")  # asking twice changes nothing
    state = me.wait(lambda c: c.state["game"]["turn"] == me.you)
    assert codes(meld_with(state, "9S")["cards"]) == ["9S", "9H", "9D"]
    assert codes(state["game"]["discard"]) == ["8H", "KS", "4D"]
    # K♠ can't be played, so it can't be taken; 8♥ can (it fits the hearts).
    assert codes(state["game"]["takeable"]) == ["8H", "4D"]
    assert {e["kind"] for e in me.events} >= {"drew", "discarded"}

    me.ok("take", card=pick(state["game"]["discard"], "8H")[0])
    hand = me.wait(lambda c: c.state["game"]["step"] == "play")["game"]["hand"]
    me.ok("lay_off", pile=meld_with(me.state, "5H")["id"], cards=pick(hand, "8H"))
    me.ok("lay_off", pile=meld_with(me.state, "9S")["id"], cards=pick(hand, "9C"))
    me.ok("discard", card=pick(hand, "4D")[0])

    me.ok("tutorial_action", action="teacher_turn")
    state = me.wait(lambda c: c.state["game"]["turn"] == me.you)
    assert codes(state["game"]["discard"])[-1] == "QD"

    me.ok("draw")
    hand = me.wait(lambda c: c.state["game"]["step"] == "play")["game"]["hand"]
    me.ok("meld", cards=pick(hand, "TC JC QC JK"))
    me.ok("discard", card=pick(hand, "KS")[0])
    state = me.wait(lambda c: c.state["phase"] == "finished")
    assert state["game"]["winner"] == me.you
    assert state["game"]["scores"] == {me.you: 80, teacher: 15 - 30}
    assert any(e["kind"] == "gin" for e in me.events)


def test_the_gin_teacher_never_plays_by_itself(connect):  # noqa: F811
    import time

    me = connect()
    me.ok("tutorial", name="Viktor", teacher="Teacher", game="gin")
    me.wait(lambda c: c.state["phase"] == "playing")
    me.ok("draw")
    me.ok("discard", card=pick(me.state["game"]["hand"], "KS")[0])
    time.sleep(0.5)
    me.ok("ping")
    assert me.state["game"]["turn"] != me.you
    assert len(me.state["game"]["discard"]) == 2
