import base64
import hashlib
import hmac

import pytest
from starlette.testclient import TestClient

from wildjoker.server import Settings, create_app
from wildjoker.server.ice import DEFAULT_STUN, IceConfig, turn_credentials

from .test_server import Client

pytestmark = pytest.mark.timeout(10)

TURN = IceConfig(
    stun_urls=("stun:turn.example:3478",),
    turn_urls=("turn:turn.example:3478?transport=udp", "turns:turn.example:5349?transport=tcp"),
    turn_secret="s3cret",
    ttl=3600,
    clock=lambda: 1_700_000_000.5,
)


def test_turn_credentials_follow_coturn_rest_scheme():
    username, credential = turn_credentials("s3cret", "1a2b3c4d", 1_700_003_600)
    assert username == "1700003600:1a2b3c4d"
    expected = hmac.new(b"s3cret", b"1700003600:1a2b3c4d", hashlib.sha1).digest()
    assert base64.b64decode(credential) == expected


def test_servers_with_turn():
    assert TURN.servers("p1") == {
        "ice_servers": [
            {"urls": ["stun:turn.example:3478"]},
            {
                "urls": list(TURN.turn_urls),
                "username": "1700003600:p1",
                "credential": turn_credentials("s3cret", "p1", 1_700_003_600)[1],
            },
        ],
        "ttl": 3600,
    }


def test_turn_needs_urls_and_secret():
    assert IceConfig(turn_urls=("turn:x",)).servers("p")["ice_servers"] == [
        {"urls": list(DEFAULT_STUN)}
    ]
    assert len(IceConfig(turn_secret="s").servers("p")["ice_servers"]) == 1


def test_config_from_env():
    assert IceConfig.from_env({}) == IceConfig(clock=IceConfig.clock)
    config = IceConfig.from_env(
        {
            "WILDJOKER_STUN_URLS": "",
            "WILDJOKER_TURN_URLS": " turn:a:3478 , turns:a:5349?transport=tcp,",
            "WILDJOKER_TURN_SECRET": "x",
            "WILDJOKER_TURN_TTL": "60",
        }
    )
    assert config.stun_urls == ()
    assert config.turn_urls == ("turn:a:3478", "turns:a:5349?transport=tcp")
    assert config.turn_enabled and config.ttl == 60
    assert [s["urls"] for s in config.servers("p")["ice_servers"]] == [list(config.turn_urls)]


@pytest.fixture
def http(tmp_path):
    app = create_app(Settings(), static_dir=tmp_path, process_pool=False, ice=TURN)
    with TestClient(app) as client:
        yield client


def test_endpoint_only_for_connected_players(http):
    assert http.get("/ice").status_code == 403
    assert http.get("/ice", params={"player": "nobody"}).status_code == 403

    client = Client(http)
    client.ok("create", name="Viktor")
    reply = http.get("/ice", params={"player": client.you})
    assert reply.status_code == 200
    assert reply.headers["cache-control"] == "no-store"
    assert reply.json() == TURN.servers(client.you)

    client.close()
    assert http.get("/ice", params={"player": client.you}).status_code == 403
