# Client–server protocol

One WebSocket per browser tab at `/ws`. All messages are JSON objects with a
`type`. Card ids are described in [cards.md](cards.md); pile rules in
[../RULES.md](../RULES.md). A room plays one of two games: Wild Joker
(`"kind": "wild"`, the default) or Gin (`"kind": "gin"`, see
[../RULES-GIN.md](../RULES-GIN.md) and [Gin](#gin) below). The source of truth is
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
| `{"type": "create", "name": "Viktor", "game": "wild"}` | New room; you are the host. `game` is `wild` (default) or `gin`, fixed for the room. |
| `{"type": "tutorial", "name": "Viktor", "teacher": "Teacher", "game": "wild"}` | A private tutorial game against a scripted Teacher (`teacher` is its display name), already started with fixed hands; see `backend/src/wildjoker/server/tutorial.py` (Wild Joker, moves have 60 s) and `gin_tutorial.py` (`"game": "gin"`: one round, played to 1 point). The Teacher only moves when asked with `tutorial_action`. |
| `{"type": "join", "code": "ABCD", "name": "Hana"}` | Code is case-insensitive. Only in the lobby, at most 8 seats (Gin: 6). |
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
| `{"type": "set_options", "decks": 2, "hand_size": 5}` | 1–3 decks, 1–15 cards; rejected (`bad_config`) if the seated players couldn't be dealt. Gin has no options (`bad_config`). |
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
| `{"type": "tutorial_action", "action": "teacher_opens"}` | | Tutorial rooms only, by the player: the Teacher's scripted moves. `teacher_opens`: opens with A♦–6♦ and puts down four 9s. `teacher_borrows`: holds the player's hearts run for 4 s, then puts it back. In the Gin tutorial, `teacher_turn` plays the Teacher's next scripted turn (draw, meld, discard, a step every 0.9 s) if it's its turn. Error `not_tutorial` elsewhere. |
| `{"type": "fast_forward", "on": true}` | | Humans only, once everyone still holding cards is a CPU: CPUs play 20× faster (`on: false` back to normal). Switches itself off when a human plays again or the game ends. Error `humans_playing` otherwise. |

The client builds the move locally (the server never sees a half-finished
staging area) and should only commit piles it has validated with the shared
pile rules (`shared/piles.json`). The server checks everything again.

## Gin

Gin rooms replace the game actions above with turns. Only the player whose
turn it is (`game.turn`) can act, first drawing (`game.step` is `draw`),
then playing and discarding (`play`). Errors: `not_your_turn`,
`draw_first`, `already_drew`, `round_over` (between rounds).

| Message | Reply data | Notes |
|---|---|---|
| `{"type": "draw"}` | `card` | Top card of the stock. An empty stock is first rebuilt from the discard pile; if that happens a second time with no card played since, the round ends instead (no `card` in the reply, event `stock_out`). `deck_empty` if there's nothing to rebuild it from. |
| `{"type": "take", "card": id}` | `cards`: taken, bottom first | A card from the discard pile with every card above it. A deeper card must be playable this turn (`cant_play_card`); `game.takeable` lists what you may take. |
| `{"type": "meld", "cards": [ids]}` | `pile`: new meld id | A run or set from your hand. |
| `{"type": "lay_off", "pile": id, "cards": [ids]}` | | Add cards from your hand to any meld. |
| `{"type": "discard", "card": id}` | | Ends the turn. `just_picked` for the card taken from the discard pile this turn; `must_play` while a deeper card taken is still in your hand. |
| `{"type": "next_round"}` | | Host only, after a round (`game.status` is `round_over`). `round_not_over` otherwise. |

Plays that would leave the turn unable to end are refused: `keep_one` if no
card would be left to discard, `must_play` if a deeper card taken from the
discard pile could no longer be played.

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
    {"urls": ["turn:zolik.0s.is:3478?transport=udp", "..."],
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
  kinds `drew` (`player`; sent to everyone before the state with the new
  card), `went_out` (`player`, `place`: 1-based; only for players who ran
  out of cards, sent before the state that records it), `staging_expired`
  (only to the player concerned), `stalemate`, `kicked`. Gin adds `took`
  (`player`, `count`), `discarded` (`player`), `one_card` (`player`: down
  to one card), `gin` (`player` went out, sent before the state with the
  scores) and `stock_out` (the round ended with the stock used up).

## State

Sent as `{"type": "state", ...}` after every change, tailored to each player:

```json
{
  "type": "state",
  "version": 42,
  "code": "ABCD",
  "kind": "wild | gin",
  "phase": "lobby | playing | finished",
  "host": "<player id or null>",
  "you": "<your player id>",
  "options": {"decks": 2, "hand_size": 5},
  "fast_forward": false,
  "tutorial": false,
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

In a Gin room, `players[]` has `cards`, `score` (the total so far) and
`place` (once the game is over) instead of `opened`, and `game` is:

```json
{
  "kind": "gin",
  "version": 17,
  "round": 2,
  "status": "playing | round_over | finished",
  "deck": 30,
  "discard": [4, 61, 23],
  "melds": [{"id": 1, "cards": [13, 14, 15, 16], "owners": ["<id>", "<id>", "<id>", "<other id>"]}],
  "dealer": "<id>",
  "turn": "<id or null between rounds>",
  "step": "draw | play",
  "picked": 23,
  "must_play": null,
  "scores": {"<id>": 120},
  "target": 500,
  "history": [{"<id>": 60, "<other id>": -15}],
  "result": {"gin": "<id or null>", "table": {}, "hand": {}, "scores": {}, "hands": {}},
  "winner": null,
  "places": [],
  "hand": [5, 9, 40],
  "takeable": [23]
}
```

- `discard` is bottom first; `melds[].owners` names who put down each card.
- `picked` is the card taken from the discard pile this turn (it can't be
  discarded); `must_play` is set while a deeper card taken must still go on
  the table.
- `result` is set between rounds and at the end: points on the table, in
  hand, the round's scores and everyone's cards left. `history` holds each
  finished round's scores.
- `winner` and `places` (grouped by score) are set when the game is over.
- `hand` and `takeable` only for players in the game; `takeable` is empty
  unless it's your turn to draw.

## Error codes

`bad_message`, `too_large`, `not_joined`, `already_joined`, `no_room`,
`bad_token`, `room_full`, `game_in_progress`, `not_host`, `bad_player`,
`bad_config`, `not_enough_players`, `no_game`, `game_over`, `player_out`,
`unknown_player`, `deck_empty`, `deck_not_empty`, `already_opened`,
`invalid_opening`, `not_opened`, `bad_card`, `bad_pile`, `pile_locked`,
`not_staging`, `staging_expired`, `empty_move`, `invalid_pile`,
`not_in_voice`, `humans_playing`, `not_tutorial`, `not_your_turn`,
`draw_first`, `already_drew`, `round_over`, `round_not_over`,
`just_picked`, `must_play`, `cant_play_card`, `keep_one`.
