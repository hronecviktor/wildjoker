import itertools
import time

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from wildjoker.engine import Config
from wildjoker.server import Settings, create_app

from .conftest import make_game

pytestmark = pytest.mark.timeout(10)


class Client:
    """A test player on a WebSocket, keeping the latest state it was sent."""

    _req = itertools.count(1)

    def __init__(self, http: TestClient):
        self._cm = http.websocket_connect("/ws")
        self.ws = self._cm.__enter__()
        self.state = None
        self.events = []
        self.signals = []
        self.you = self.token = self.code = None

    def close(self):
        self._cm.__exit__(None, None, None)

    def _receive(self):
        msg = self.ws.receive_json()
        match msg["type"]:
            case "state":
                self.state = msg
            case "event":
                self.events.append(msg)
            case "signal":
                self.signals.append(msg)
            case "welcome":
                self.you, self.token, self.code = msg["you"], msg["token"], msg["code"]
        return msg

    def send(self, type, **fields):
        """Send a message and return the server's reply to it."""
        req = next(self._req)
        self.ws.send_json({"type": type, "req": req, **fields})
        while True:
            msg = self._receive()
            if msg.get("req") == req and msg["type"] in ("ok", "error", "welcome"):
                return msg

    def ok(self, type, **fields):
        reply = self.send(type, **fields)
        assert reply["type"] in ("ok", "welcome"), reply
        return reply

    def error(self, type, **fields):
        reply = self.send(type, **fields)
        assert reply["type"] == "error", reply
        return reply["code"]

    def wait(self, predicate):
        """Read messages until there is a state and ``predicate(self)`` holds."""
        while self.state is None or not predicate(self):
            self._receive()
        return self.state

    def player(self, pid):
        return next(p for p in self.state["players"] if p["id"] == pid)


@pytest.fixture
def http(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>Wild Joker</title>")
    settings = Settings(staging_timeout=0.3, stalemate_idle=0.2)
    with TestClient(create_app(settings, static_dir=tmp_path, process_pool=False)) as client:
        yield client


@pytest.fixture
def connect(http):
    clients = []

    def make():
        client = Client(http)
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.close()


def lobby(connect, n=2):
    """A room with n humans; the first is the host."""
    host = connect()
    host.ok("create", name="Host")
    others = []
    for i in range(1, n):
        other = connect()
        other.ok("join", code=host.code, name=f"P{i}")
        others.append(other)
    host.wait(lambda c: len(c.state["players"]) == n)
    return host, *others


def started(connect, n=2):
    clients = lobby(connect, n)
    clients[0].ok("start")
    for c in clients:
        c.wait(lambda c: c.state["phase"] == "playing")
    return clients


def run(http, fn):
    """Run ``fn`` on the server's event loop (to set up game state)."""
    return http.portal.call(_async(fn))


def _async(fn):
    async def wrapper():
        return fn()

    return wrapper


def room_of(http, client):
    return http.app.state.manager.rooms[client.code]


# -- http ----------------------------------------------------------------------


def test_health_and_invite_page(http):
    assert http.get("/healthz").text == "ok"
    assert "Wild Joker" in http.get("/j/ABCD").text
    assert "Wild Joker" in http.get("/").text


# -- lobby ---------------------------------------------------------------------


def test_create_room(connect):
    host = connect()
    welcome = host.ok("create", name="  Viktor ")
    assert len(welcome["code"]) == 4 and welcome["token"]
    state = host.wait(lambda c: c.state)
    assert state["phase"] == "lobby" and state["host"] == host.you == state["you"]
    assert state["players"][0]["name"] == "Viktor" and state["players"][0]["connected"]


def test_lobby_fills_up_for_everyone(connect):
    host, a, b = lobby(connect, 3)
    for c in (host, a, b):
        c.wait(lambda c: len(c.state["players"]) == 3)
    assert [p["name"] for p in a.state["players"]] == ["Host", "P1", "P2"]


def test_join_with_lowercase_code(connect):
    host = connect()
    host.ok("create", name="Host")
    assert connect().ok("join", code=f" {host.code.lower()} ", name="x")["code"] == host.code


def test_join_errors(connect):
    host = connect()
    host.ok("create", name="Host")
    assert connect().error("join", code="ZZZZ", name="x") == "no_room"
    assert connect().error("join", code=host.code, name="") == "bad_message"
    assert host.error("join", code=host.code, name="again") == "already_joined"
    assert connect().error("draw") == "not_joined"


def test_room_full(connect):
    host = connect()
    host.ok("create", name="Host")
    for _ in range(7):
        host.ok("add_cpu", level="easy")
    assert connect().error("join", code=host.code, name="late") == "room_full"


def test_bad_messages(connect):
    host = connect()
    host.ws.send_text("not json")
    assert host.ws.receive_json() == {"type": "error", "req": None, "code": "bad_message"}
    assert host.error("fly") == "bad_message"
    host.ok("create", name="Host")
    assert host.error("set_options", decks=4, hand_size=5) == "bad_message"


def test_host_only_actions(connect):
    host, other = lobby(connect)
    assert other.error("start") == "not_host"
    assert other.error("add_cpu", level="easy") == "not_host"
    assert other.error("set_options", decks=1, hand_size=3) == "not_host"
    host.ok("set_options", decks=3, hand_size=7)
    other.wait(lambda c: c.state["options"] == {"decks": 3, "hand_size": 7})


def test_cpu_players_in_lobby(connect):
    host = connect()
    host.ok("create", name="Host")
    host.ok("add_cpu", level="hard")
    host.wait(lambda c: len(c.state["players"]) == 2)
    cpu = host.state["players"][1]
    assert cpu["cpu"] == "hard" and cpu["connected"]
    host.ok("set_cpu_level", player=cpu["id"], level="easy")
    host.wait(lambda c: c.state["players"][1]["cpu"] == "easy")
    host.ok("remove_player", player=cpu["id"])
    host.wait(lambda c: len(c.state["players"]) == 1)


def test_kick_player(connect):
    host, other = lobby(connect)
    host.ok("remove_player", player=other.you)
    other.wait(lambda c: any(e["kind"] == "kicked" for e in c.events))
    host.wait(lambda c: len(c.state["players"]) == 1)


def test_host_leaving_passes_host_on(connect):
    host, a = lobby(connect)
    host.ok("leave")
    a.wait(lambda c: len(c.state["players"]) == 1 and c.state["host"] == a.you)


def test_last_human_leaving_closes_room(http, connect):
    host = connect()
    host.ok("create", name="Host")
    host.ok("add_cpu", level="easy")
    code = host.code
    host.ok("leave")
    time.sleep(0.05)
    assert code not in http.app.state.manager.rooms


def test_start_needs_two_players(connect):
    host = connect()
    host.ok("create", name="Host")
    assert host.error("start") == "not_enough_players"


def test_start_checks_card_supply(connect):
    host, _ = lobby(connect)
    host.ok("set_options", decks=1, hand_size=7)  # fine for 2 players...
    for _ in range(6):
        host.ok("add_cpu", level="easy")
    assert host.error("start") == "bad_config"  # ...but 8 x 7 > 54
    assert host.error("set_options", decks=1, hand_size=7) == "bad_config"


def test_cannot_join_running_game(connect):
    host, _ = started(connect)
    assert connect().error("join", code=host.code, name="late") == "game_in_progress"


# -- game ----------------------------------------------------------------------


def test_start_deals_private_hands(connect):
    host, other = started(connect)
    game = host.state["game"]
    assert len(game["hand"]) == 5 and game["deck"] == 108 - 10
    assert host.player(other.you)["cards"] == 5
    assert set(game["hand"]).isdisjoint(other.state["game"]["hand"])
    assert "hand" not in str(host.player(other.you))


def test_draw_updates_counts(connect):
    host, other = started(connect)
    reply = host.ok("draw")
    assert reply["card"] in host.wait(lambda c: len(c.state["game"]["hand"]) == 6)["game"]["hand"]
    other.wait(lambda c: c.player(host.you)["cards"] == 6)


def test_game_errors_come_back_with_codes(connect):
    host, _ = started(connect)
    assert host.error("stage", piles=[1]) == "not_opened"
    assert host.error("open", cards=host.state["game"]["hand"][:2]) == "invalid_opening"
    assert host.error("vote_draw") == "deck_not_empty"


def test_full_game_flow(http, connect):
    host, other = started(connect)
    room = room_of(http, host)
    game = make_game({host.you: "2H 3H 4H 5H", other.you: "9C 9D"}, table=["9S 9H 9D"], deck="KD")

    def install():
        room.game = game
        room.changed()

    run(http, install)
    hand = host.wait(lambda c: len(c.state["game"]["hand"]) == 4)["game"]["hand"]
    by_code = {c.code: c.id for c in game.players[host.you].hand}
    host.ok("open", cards=[by_code["2H"], by_code["3H"], by_code["4H"]])
    pile = host.wait(lambda c: len(c.state["game"]["table"]) == 2)["game"]["table"][1]
    host.ok("stage", piles=[pile["id"]])
    other.wait(lambda c: any(p["locked_by"] == host.you for p in c.state["game"]["table"]))
    assert host.state["game"]["staging"]["piles"] == [pile["id"]]
    host.ok("commit", piles=[pile["cards"] + [by_code["5H"]]])
    assert len(hand) == 4
    for c in (host, other):
        c.wait(lambda c: c.state["phase"] == "finished")
    assert host.state["game"]["places"] == [[host.you], [other.you]]
    assert host.player(host.you)["place"] == 1
    assert any(e["kind"] == "went_out" for e in other.events)
    host.ok("back_to_lobby")
    other.wait(lambda c: c.state["phase"] == "lobby" and c.state["game"] is None)


def test_staging_expires(http, connect):
    host, other = started(connect)
    room = room_of(http, host)

    def install():
        room.game = make_game(
            {host.you: "9C", other.you: "8D"}, table=["2C 3C 4C"], deck="KD", opened=[host.you]
        )
        room.game.config = Config(staging_timeout=0.3)
        room.changed()

    run(http, install)
    host.wait(lambda c: len(c.state["game"]["table"]) == 1)
    host.ok("stage", piles=[1])
    host.wait(lambda c: any(e["kind"] == "staging_expired" for e in c.events))
    state = host.wait(lambda c: c.state["game"]["table"][0]["locked_by"] is None)
    assert state["game"]["staging"] is None


def test_stalemate_detected(http, connect):
    host, other = started(connect)
    room = room_of(http, host)

    def install():
        room.game = make_game(
            {host.you: "9C", other.you: "2D"}, table=["5H 6H 7H"], opened=[host.you, other.you]
        )
        room.changed()

    run(http, install)
    host.wait(lambda c: c.state["phase"] == "finished")
    assert host.state["game"]["places"] == [[host.you, other.you]]
    assert any(e["kind"] == "stalemate" for e in host.events)


def test_draw_by_votes(http, connect):
    host, other = started(connect)
    room = room_of(http, host)

    def install():
        # Deck empty but host can still play, so no automatic stalemate.
        room.game = make_game({host.you: "2C 3C 4C 9H", other.you: "8D"})
        room.changed()

    run(http, install)
    host.wait(lambda c: c.state["game"]["deck"] == 0)
    host.ok("vote_draw")
    other.wait(lambda c: c.state["game"]["draw_votes"] == [host.you])
    other.ok("vote_draw")
    host.wait(lambda c: c.state["phase"] == "finished")


# -- reconnecting and leaving ------------------------------------------------------


def test_resume_after_disconnect(connect):
    host, other = started(connect)
    hand = other.state["game"]["hand"]
    other.close()
    host.wait(lambda c: not c.player(other.you)["connected"])
    again = connect()
    again.ok("resume", code=other.code, token=other.token)
    assert again.wait(lambda c: c.state)["game"]["hand"] == hand
    assert again.you == other.you
    host.wait(lambda c: c.player(other.you)["connected"])


def test_resume_with_bad_token(connect):
    host = connect()
    host.ok("create", name="Host")
    assert connect().error("resume", code=host.code, token="nope") == "bad_token"


def test_second_connection_replaces_first(connect):
    host, other = lobby(connect)
    again = connect()
    again.ok("resume", code=other.code, token=other.token)
    again.wait(lambda c: c.state)
    with pytest.raises(WebSocketDisconnect) as closed:
        while True:
            other._receive()
    assert closed.value.code == 4000


def test_leaving_mid_game_hands_seat_to_cpu(connect):
    host, other = started(connect)
    other.ok("leave")
    host.wait(lambda c: c.player(other.you)["cpu"] == "medium")
    assert host.player(other.you)["cards"] == 5


def test_reclaiming_seat_from_cpu(connect):
    host, other = started(connect)
    token, code, you = other.token, other.code, other.you
    host.ok("leave")
    other.wait(lambda c: c.player(host.you)["cpu"] == "medium" and c.state["host"] == you)
    back = connect()
    back.ok("resume", code=code, token=host.token)
    state = back.wait(lambda c: c.state)
    assert state["you"] == host.you and back.player(host.you)["cpu"] is None
    assert token  # the other player's seat is untouched


# -- voice -----------------------------------------------------------------------


def test_voice_signalling(connect):
    host, other = lobby(connect)
    assert host.error("signal", to=other.you, data={"sdp": "x"}) == "not_in_voice"
    host.ok("voice_join")
    other.ok("voice_join")
    host.wait(lambda c: c.player(other.you)["voice"])
    host.ok("signal", to=other.you, data={"sdp": "offer"})
    other.wait(lambda c: c.signals)
    assert other.signals == [{"type": "signal", "from": host.you, "data": {"sdp": "offer"}}]
    other.ok("voice_mute", muted=True)
    host.wait(lambda c: c.player(other.you)["muted"])
    other.ok("voice_leave")
    host.wait(lambda c: not c.player(other.you)["voice"])


# -- fast forward ------------------------------------------------------------------


def only_cpus_left(http, host):
    """Host has gone out; one CPU and one human-less seat play on."""
    room = room_of(http, host)
    cpu = next(s.id for s in room.seats.values() if s.cpu)

    def install():
        room.game = make_game({host.you: "", cpu: "9C 2D"}, deck="KD QS JH", opened=[cpu])
        room.game.places = [[host.you]]
        room.changed()

    run(http, install)
    host.wait(lambda c: c.player(host.you)["place"] == 1)
    return room


def test_fast_forward_only_when_only_cpus_are_left(http, connect):
    host = connect()
    host.ok("create", name="Host")
    host.ok("add_cpu", level="easy")
    host.ok("start")
    host.wait(lambda c: c.state["phase"] == "playing")
    assert host.error("fast_forward", on=True) == "humans_playing"
    assert host.state["fast_forward"] is False
    room = only_cpus_left(http, host)
    host.ok("fast_forward", on=True)
    host.wait(lambda c: c.state["fast_forward"])
    assert room.fast_forward
    host.ok("fast_forward", on=False)
    host.wait(lambda c: not c.state["fast_forward"])


def test_fast_forward_switches_off_when_a_human_is_back(http, connect):
    host, other = started(connect)
    room = room_of(http, host)
    token, code = other.token, other.code
    other.ok("leave")  # a CPU takes over other's seat
    host.wait(lambda c: c.player(other.you)["cpu"] == "medium")
    assert host.error("fast_forward", on=True) == "humans_playing"  # host still plays

    def host_out():
        room.game.players[host.you].hand = []
        room.game.places = [[host.you]]
        room.changed()

    run(http, host_out)
    host.ok("fast_forward", on=True)
    host.wait(lambda c: c.state["fast_forward"])
    back = connect()
    back.ok("resume", code=code, token=token)  # a human is playing again
    host.wait(lambda c: not c.state["fast_forward"])
