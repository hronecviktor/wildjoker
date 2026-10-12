"""Gin rooms over the WebSocket (the rules themselves are in test_gin)."""

import pytest

from .test_gin import discard_id, ids, make_gin
from .test_server import connect, http, room_of, run  # noqa: F401 (fixtures)

pytestmark = pytest.mark.timeout(10)


def gin_lobby(connect, n=2):  # noqa: F811
    host = connect()
    host.ok("create", name="Host", game="gin")
    others = []
    for i in range(1, n):
        other = connect()
        other.ok("join", code=host.code, name=f"P{i}")
        others.append(other)
    host.wait(lambda c: len(c.state["players"]) == n)
    return host, *others


def rigged(http, connect, hands, **kw):  # noqa: F811
    """A started Gin room whose game is replaced with fixed cards.

    ``hands`` is keyed "host", "p1", ...; returns the clients and the game.
    """
    clients = gin_lobby(connect, len(hands))
    host = clients[0]
    host.ok("start")
    room = room_of(http, host)
    pids = [c.you for c in clients]

    def setup():
        game = make_gin(dict(zip(pids, hands.values(), strict=True)), **kw)
        room.game = game
        room.changed()
        return game, room.version

    game, version = run(http, setup)
    for c in clients:
        c.wait(lambda c: c.state["version"] >= version)
    return clients, game


def test_a_gin_room(connect):  # noqa: F811
    host, guest = gin_lobby(connect)
    assert host.state["kind"] == "gin"
    assert host.error("set_options", decks=2, hand_size=5) == "bad_config"
    host.ok("start")
    state = guest.wait(lambda c: c.state["phase"] == "playing")
    game = state["game"]
    assert game["kind"] == "gin" and game["round"] == 1 and game["status"] == "playing"
    assert len(game["hand"]) == 7 and len(game["discard"]) == 1
    assert game["deck"] == 54 - 14 - 1
    assert game["turn"] == host.you and game["step"] == "draw"
    assert {p["id"]: p["cards"] for p in state["players"]} == {host.you: 7, guest.you: 7}
    assert all(p["score"] == 0 for p in state["players"])
    assert game["takeable"] == []  # not the guest's turn
    assert host.state["game"]["takeable"] == game["discard"]


def test_wild_joker_rooms_are_the_default(connect):  # noqa: F811
    host = connect()
    host.ok("create", name="Host")
    assert host.wait(lambda c: c.state)["kind"] == "wild"


def test_gin_rooms_seat_six(connect):  # noqa: F811
    host = connect()
    host.ok("create", name="Host", game="gin")
    for _ in range(5):
        host.ok("add_cpu", level="medium")
    assert host.error("add_cpu", level="medium") == "room_full"


def test_a_turn_over_the_wire(http, connect):  # noqa: F811
    (host, guest), game = rigged(
        http, connect, {"host": "4S 5S 6S 9D 2H", "p1": "7S 9C KC"}, discard="2C", stock="TC"
    )
    assert guest.error("draw") == "not_your_turn"
    assert host.ok("draw")["card"] == next(c.id for c in game.hand(host.you) if c.code == "TC")
    pile = host.ok("meld", cards=ids(game, host.you, "4S 5S 6S"))["pile"]
    host.ok("discard", card=ids(game, host.you, "9D")[0])
    state = guest.wait(lambda c: c.state["game"]["turn"] == guest.you)
    assert state["game"]["melds"] == [
        {
            "id": pile,
            "cards": ids_on_table(game, pile),
            "owners": [host.you] * 3,
        }
    ]
    assert guest.state["game"]["discard"] == [discard_id(game, "2C"), discard_id(game, "9D")]
    kinds = [e["kind"] for e in guest.events]
    assert kinds == ["drew", "discarded"]
    guest.ok("take", card=discard_id(game, "9D"))
    assert guest.error("discard", card=ids(game, guest.you, "9D")[0]) == "just_picked"
    guest.ok("lay_off", pile=pile, cards=ids(game, guest.you, "7S"))
    owners = guest.wait(lambda c: len(c.state["game"]["melds"][0]["owners"]) == 4)
    assert owners["game"]["melds"][0]["owners"] == [host.you] * 3 + [guest.you]


def ids_on_table(game, pile):
    return [c.id for c in game.round.melds[pile].cards]


def test_one_card_left_and_going_out(http, connect):  # noqa: F811
    (host, guest), game = rigged(
        http,
        connect,
        {"host": "4S 5S 6S 9D KH", "p1": "2C 3D"},
        discard="2D",
        stock="7S TC",
        step="play",
    )
    pile = host.ok("meld", cards=ids(game, host.you, "4S 5S 6S"))["pile"]
    host.ok("discard", card=ids(game, host.you, "9D")[0])
    guest.wait(lambda c: any(e["kind"] == "one_card" for e in c.events))
    assert [e for e in guest.events if e["kind"] == "one_card"] == [
        {"type": "event", "kind": "one_card", "player": host.you}
    ]
    guest.ok("draw")
    guest.ok("discard", card=ids(game, guest.you, "3D")[0])
    host.ok("draw")
    host.ok("lay_off", pile=pile, cards=ids(game, host.you, "7S"))
    host.ok("discard", card=ids(game, host.you, "KH")[0])
    state = guest.wait(lambda c: c.state["game"]["status"] == "round_over")
    assert any(e["kind"] == "gin" and e["player"] == host.you for e in guest.events)
    result = state["game"]["result"]
    assert result["gin"] == host.you
    assert result["scores"] == {host.you: 20, guest.you: -15}
    assert sorted(result["hands"][guest.you]) == sorted(ids(game, guest.you, "2C TC"))
    assert state["game"]["turn"] is None
    assert {p["id"]: p["score"] for p in state["players"]} == {host.you: 20, guest.you: -15}
    assert guest.error("next_round") == "not_host"
    host.ok("next_round")
    state = guest.wait(lambda c: c.state["game"]["status"] == "playing")
    assert state["game"]["round"] == 2 and state["game"]["turn"] == guest.you
    assert state["game"]["history"] == [{host.you: 20, guest.you: -15}]


def test_the_game_ends_at_500(http, connect):  # noqa: F811
    (host, guest), game = rigged(
        http,
        connect,
        {"host": "4S 5S 6S 9D", "p1": "2C"},
        discard="2D",
        stock="TC",
        step="play",
        scores=None,
    )
    run(http, lambda: game.scores.update({host.you: 495}))
    host.ok("meld", cards=ids(game, host.you, "4S 5S 6S"))
    host.ok("discard", card=ids(game, host.you, "9D")[0])
    state = guest.wait(lambda c: c.state["phase"] == "finished")
    assert state["game"]["winner"] == host.you
    assert state["game"]["places"] == [[host.you], [guest.you]]
    assert {p["id"]: p["place"] for p in state["players"]} == {host.you: 1, guest.you: 2}
    host.ok("back_to_lobby")
    assert guest.wait(lambda c: c.state["phase"] == "lobby")["kind"] == "gin"


def test_the_stock_running_out_again_ends_the_round(http, connect):  # noqa: F811
    (host, guest), game = rigged(
        http, connect, {"host": "2S 9C", "p1": "3D 7H"}, discard="4C 5C KD"
    )
    host.ok("draw")
    host.ok("discard", card=ids(game, host.you, "2S")[0])
    guest.ok("draw")
    guest.ok("discard", card=ids(game, guest.you, "3D")[0])
    assert "card" not in host.ok("draw")
    state = guest.wait(lambda c: c.state["game"]["status"] == "round_over")
    assert state["game"]["result"]["gin"] is None
    assert any(e["kind"] == "stock_out" for e in guest.events)


def test_leaving_a_gin_game_hands_the_seat_to_a_cpu(connect):  # noqa: F811
    host, guest = gin_lobby(connect)
    host.ok("start")
    guest.wait(lambda c: c.state["phase"] == "playing")
    guest.ok("leave")
    state = host.wait(lambda c: c.player(guest.you)["cpu"] == "medium")
    assert state["phase"] == "playing"
