"""The tutorial plays out exactly as its steps describe."""

import pytest

from wildjoker.engine import Card
from wildjoker.server import tutorial

from .test_server import connect, http  # noqa: F401 (fixtures)

pytestmark = pytest.mark.timeout(10)


def codes(ids) -> list[str]:
    return [Card(i).code for i in ids]


def pick(ids, wanted: str) -> list[int]:
    """Card ids by code, in the order given."""
    ids, result = list(ids), []
    for code in wanted.split():
        card = next(i for i in ids if Card(i).code == code)
        ids.remove(card)
        result.append(card)
    return result


def pile_with(state, code: str) -> dict:
    return next(p for p in state["game"]["table"] if code in codes(p["cards"]))


def test_tutorial_game(connect, monkeypatch):  # noqa: F811
    monkeypatch.setattr(tutorial, "BORROW_SECONDS", 0.2)
    me = connect()
    me.ok("tutorial", name="Viktor", teacher="Teacher")
    state = me.wait(lambda c: c.state["phase"] == "playing")
    assert state["tutorial"] is True
    teacher = next(p["id"] for p in state["players"] if p["id"] != me.you)
    assert me.player(teacher)["cpu"] == "easy"
    assert sorted(codes(state["game"]["hand"])) == sorted(tutorial.PLAYER_HAND.split())
    assert state["game"]["staging_timeout"] == tutorial.STAGING_TIMEOUT

    # 1. Draw 6H and open with 4H 5H 6H.
    assert Card(me.ok("draw")["card"]).code == "6H"
    hand = me.wait(lambda c: len(c.state["game"]["hand"]) == 9)["game"]["hand"]
    me.ok("open", cards=pick(hand, "4H 5H 6H"))

    # 2. The Teacher opens and puts down the 9s.
    me.ok("tutorial_action", action="teacher_opens")
    state = me.wait(lambda c: len(c.state["game"]["table"]) == 3)
    assert sorted(codes(pile_with(state, "9S")["cards"])) == sorted("9S 9H 9D 9C".split())

    # 3. Draw 7H and add it to the hearts run.
    assert Card(me.ok("draw")["card"]).code == "7H"
    state = me.wait(lambda c: "7H" in codes(c.state["game"]["hand"]))
    run = pile_with(state, "4H")
    me.ok("stage", piles=[run["id"]])
    me.ok("commit", piles=[run["cards"] + pick(state["game"]["hand"], "7H")])

    # 4. A new pile with the joker.
    state = me.wait(lambda c: "7H" not in codes(c.state["game"]["hand"]))
    me.ok("commit", piles=[pick(state["game"]["hand"], "QS KS JK")])

    # 5. Split the Teacher's diamonds to fit 3D: A-3D and 3D-6D.
    state = me.wait(lambda c: "JK" not in codes(c.state["game"]["hand"]))
    diamonds = pile_with(state, "AD")
    me.ok("stage", piles=[diamonds["id"]])
    low = pick(diamonds["cards"], "AD 2D 3D")
    high = pick(diamonds["cards"], "4D 5D 6D") + pick(state["game"]["hand"], "3D")
    me.ok("commit", piles=[low, high])
    state = me.wait(lambda c: "3D" not in codes(c.state["game"]["hand"]))
    assert sorted(codes(state["game"]["hand"])) == ["8C", "TC"]

    # 6. The Teacher briefly holds the hearts run, then gives it back.
    me.ok("tutorial_action", action="teacher_borrows")
    me.wait(lambda c: pile_with(c.state, "4H")["locked_by"] == teacher)
    me.wait(lambda c: pile_with(c.state, "4H")["locked_by"] is None)

    # 7. Take 9C from the set to make 8C 9C 10C: the hand is empty.
    nines = pile_with(me.state, "9S")
    me.ok("stage", piles=[nines["id"]])
    me.ok(
        "commit",
        piles=[
            pick(nines["cards"], "9S 9H 9D"),
            pick(nines["cards"], "9C") + pick(me.state["game"]["hand"], "8C TC"),
        ],
    )
    state = me.wait(lambda c: c.state["phase"] == "finished")
    assert state["game"]["places"] == [[me.you], [teacher]]


def test_tutorial_teacher_never_plays_by_itself(connect):  # noqa: F811
    import time

    me = connect()
    me.ok("tutorial", name="Viktor", teacher="Teacher")
    state = me.wait(lambda c: c.state["phase"] == "playing")
    teacher = next(p["id"] for p in state["players"] if p["id"] != me.you)
    time.sleep(0.5)
    me.ok("ping")
    assert me.player(teacher)["cards"] == len(tutorial.TEACHER_HAND.split())
    assert me.state["game"]["table"] == []


def test_tutorial_actions_only_in_tutorials(connect):  # noqa: F811
    host = connect()
    host.ok("create", name="Host")
    host.ok("add_cpu", level="easy")
    host.ok("start")
    assert host.error("tutorial_action", action="teacher_opens") == "not_tutorial"


def test_tutorial_room_closes_when_the_player_leaves(http, connect):  # noqa: F811
    me = connect()
    me.ok("tutorial", name="Viktor", teacher="Teacher")
    me.wait(lambda c: c.state["phase"] == "playing")
    code = me.code
    me.ok("leave")
    assert code not in http.app.state.manager.rooms
