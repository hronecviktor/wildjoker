"""CPU players through the real server, against a human on a WebSocket."""

import pytest
from starlette.testclient import TestClient

from wildjoker.server import Settings, create_app

from .test_server import Client

pytestmark = pytest.mark.timeout(20)


@pytest.fixture
def http(tmp_path):
    settings = Settings(staging_timeout=2.0, stalemate_idle=0.5, cpu_speed=20.0)
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


def test_human_plays_against_a_cpu(http, connect):
    human = connect()
    human.ok("create", name="Viktor")
    human.ok("add_cpu", level="expert")
    human.ok("start")
    state = human.wait(lambda c: c.state["phase"] == "playing")
    cpu = next(pl["id"] for pl in state["players"] if pl["cpu"])

    # The CPU acts on its own: it draws until it can open, then opens.
    human.wait(lambda c: c.player(cpu)["opened"] or c.state["phase"] == "finished")
    assert human.state["game"]["table"] or human.state["phase"] == "finished"

    # Meanwhile the human can still act, and the game carries on until it ends
    # (the human keeps drawing and never plays, so the CPU wins or it's a draw).
    while human.state["phase"] == "playing":
        if human.state["game"]["deck"]:
            human.send("draw")
        else:
            human.send("vote_draw")
        human.wait(lambda c: True)
    places = human.state["game"]["places"]
    assert places[0] == [cpu] or places == [[human.you, cpu]]
    assert http.app.state.cpus.players == {}


def test_cpu_stands_in_for_a_player_who_left(http, connect):
    host, other = connect(), connect()
    host.ok("create", name="Host")
    other.ok("join", code=host.code, name="Hana")
    host.ok("start")
    host.wait(lambda c: c.state["phase"] == "playing")
    gone, code, token = other.you, other.code, other.token
    other.ok("leave")

    host.wait(lambda c: c.player(gone)["cpu"] == "medium")
    start = host.state["game"]["version"]
    # The stand-in plays: it draws (or opens) without anyone asking.
    host.wait(lambda c: c.state["game"]["version"] > start + 2)

    back = connect()
    back.ok("resume", code=code, token=token)
    state = back.wait(lambda c: c.player(gone)["cpu"] is None)
    assert state["you"] == gone
    assert all(pid != gone for _, pid in http.app.state.cpus.players)
