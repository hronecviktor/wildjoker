# Client–server protocol

One WebSocket per browser tab at `/ws`. All messages are JSON objects with a
`type`. Card ids are described in [cards.md](cards.md); pile rules in
[../RULES.md](../RULES.md). The source of truth is
`backend/src/wildjoker/server/protocol.py` (client messages) and
`backend/src/wildjoker/server/rooms.py` (`Room.view`, the state).

## Requests and replies

Every client message may carry a numeric `req`. The server answers each
message with exactly one reply carrying the same `req`:

- `{"type": "ok", "req": 7, ...}`: done. Some actions add data (below).
- `{"type": "error", "req": 7, "code": "pile_locked"}`: rejected; nothing
  changed. Codes are stable and translated by the client (list below).
- `{"type": "welcome", ...}` instead of `ok` for `create`, `join` and
  `resume`.

State changes are not in the reply: they arrive as `state` messages, to
every player, after every change (including other players' actions).

## Joining

| Client message | Notes |
|---|---|
| `{"type": "create", "name": "Viktor"}` | New room; you are the host. |
| `{"type": "join", "code": "ABCD", "name": "Hana"}` | Code is case-insensitive. Only in the lobby, at most 8 seats. |
| `{"type": "resume", "code": "ABCD", "token": "..."}` | Take your seat back after a reload or dropped connection. Also takes a seat back from the CPU that stood in after you left. |

Reply: `{"type": "welcome", "code": "ABCD", "you": "<player id>", "token": "<secret>"}`.
Store `code` and `token` (e.g. in `localStorage`) to resume later. Names are
1–20 characters. A newer connection to the same seat closes the older one
with WebSocket close code 4000.

Invite links have the form `/j/ABCD`; the server serves the app there.

## Lobby

Host only, in the lobby:

| Message | Notes |
|---|---|
| `{"type": "set_options", "decks": 2, "hand_size": 5}` | 1–3 decks, 1–15 cards; rejected (`bad_config`) if the seated players couldn't be dealt. |
| `{"type": "add_cpu", "level": "medium"}` | `easy`, `medium`, `hard` or `expert`. |
| `{"type": "set_cpu_level", "player": "<id>", "level": "hard"}` | |
| `{"type": "remove_player", "player": "<id>"}` | Removes a CPU or kicks a human (they get event `kicked`). |
| `{"type": "start"}` | Needs 2+ seats. |
| `{"type": "back_to_lobby"}` | After a game has finished; same seats, new game possible. |

Anyone: `{"type": "leave"}`. In the lobby the seat is removed (the host role
passes to the next human). During a game a CPU (`medium`) takes over the
seat; you can `resume` it later with your token. The server closes the
connection after replying.

## Game actions

| Message | Reply data | Notes |
|---|---|---|
| `{"type": "draw"}` | `card`: the card drawn | Any time, as often as you like, until the deck is empty. |
| `{"type": "open", "cards": [ids]}` | `pile`: new pile id | Joker-free run of 3+ from your hand; once per game. |
| `{"type": "stage", "piles": [pile ids]}` | | Take piles off the table into your staging area (locks them). Can be repeated to take more; the 15 s clock starts at the first. |
| `{"type": "cancel"}` | | Put staged piles back unchanged. |
| `{"type": "commit", "piles": [[ids], ...]}` | `piles`: new pile ids | The final piles. May use any card from your staged piles and your hand. Staged cards you leave out go to your hand. Works without staging to put new piles down from your hand. An empty list with staged piles takes them all into your hand. |
| `{"type": "vote_draw"}` | | Once the deck is empty: agree to end as a draw. Votes reset when anyone commits. |

The client builds the move locally (the server never sees a half-finished
staging area) and should only commit piles it has validated with the shared
pile rules (`shared/piles.json`). The server checks everything again.

## Voice

| Message | Notes |
|---|---|
| `{"type": "voice_join"}` / `{"type": "voice_leave"}` | Shown to everyone in `players[].voice`. Disconnecting leaves voice. |
| `{"type": "voice_mute", "muted": true}` | `players[].muted`. |
| `{"type": "signal", "to": "<id>", "data": {...}}` | Relayed as `{"type": "signal", "from": "<id>", "data": {...}}`. Both players must be in voice. `data` is opaque (SDP offer/answer, ICE candidates). |

Connections are set up with WebRTC "perfect negotiation" (see
`frontend/src/lib/voice/`): whenever two players are both in voice, both
sides create a connection. The player with the larger id sends the first
offer (the other one only offers itself if none comes within 3 s); later
offers may come from either side, and on a collision the player with the
smaller id is *polite* and rolls its own offer back. The `data` the
voice module sends is `{"sid": "<session id>", "description": {...}}` or
`{"sid": "...", "candidate": {...}}`; `sid` is new each time a player joins
voice, so a peer that rejoined is recognised and gets a fresh connection.

### ICE servers (HTTP)

`GET /ice?player=<your player id>` returns the STUN/TURN servers for
`RTCPeerConnection`, with short-lived TURN credentials (coturn's
`use-auth-secret` scheme: username `<expiry>:<player id>`, password
`base64(HMAC-SHA1(secret, username))`):

```json
{
  "ice_servers": [
    {"urls": ["stun:stun.l.google.com:19302"]},
    {"urls": ["turn:wildjoker.0s.is:3478?transport=udp", "..."],
     "username": "1760000000:1a2b3c4d", "credential": "..."}
  ],
  "ttl": 43200
}
```

`403` unless the player id belongs to a seat with an open connection. The
TURN entry is only present when the server has `WILDJOKER_TURN_URLS` and
`WILDJOKER_TURN_SECRET` set (see `deploy/README.md`); `ttl` is in seconds,
the client fetches new credentials before they expire.

## Other

- `{"type": "ping"}`: replies `ok`; use as a keep-alive.
- Events, for toasts and sounds: `{"type": "event", "kind": ...}` with
  kinds `went_out` (`player`), `staging_expired` (only to the player
  concerned), `stalemate`, `kicked`.

## State

Sent as `{"type": "state", ...}` after every change, tailored to each player:

```json
{
  "type": "state",
  "version": 42,
  "code": "ABCD",
  "phase": "lobby | playing | finished",
  "host": "<player id or null>",
  "you": "<your player id>",
  "options": {"decks": 2, "hand_size": 5},
  "players": [
    {
      "id": "1a2b3c4d", "name": "Viktor", "cpu": null,
      "connected": true, "voice": true, "muted": false,
      "cards": 5, "opened": false, "place": null
    }
  ],
  "game": {
    "version": 17,
    "deck": 93,
    "table": [{"id": 3, "cards": [13, 14, 15], "locked_by": null}],
    "places": [["<id>"], ["<id>", "<id>"]],
    "draw_votes": [],
    "staging_timeout": 15.0,
    "hand": [4, 61, 108],
    "staging": {"piles": [3], "remaining": 11.2}
  }
}
```

- `players[].cpu` is the CPU level, or `null` for a human. CPUs are always
  `connected`.
- `cards`, `opened` and `place` are present once a game exists. `place` is
  1-based; players sharing a place (a stalemate) have the same number.
- `game` is `null` in the lobby. `hand` and `staging` are only present for
  players seated in the game; `staging` is `null` when you aren't staging.
- Table piles come in canonical order (see `shared/piles.json`), so the
  client can display them as they are.
- `version` increases with every state; ignore a state older than the one
  you have.

## Error codes

`bad_message`, `too_large`, `not_joined`, `already_joined`, `no_room`,
`bad_token`, `room_full`, `game_in_progress`, `not_host`, `bad_player`,
`bad_config`, `not_enough_players`, `no_game`, `game_over`, `player_out`,
`unknown_player`, `deck_empty`, `deck_not_empty`, `already_opened`,
`invalid_opening`, `not_opened`, `bad_card`, `bad_pile`, `pile_locked`,
`not_staging`, `staging_expired`, `empty_move`, `invalid_pile`,
`not_in_voice`.
