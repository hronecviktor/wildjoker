# Wild Joker design

How the game in [RULES.md](RULES.md) is built. The interactive tutorial
("teach me how to play") is planned for later and is out of scope here, but
the design leaves room for it.

## Requirements

- Online multiplayer for 2–8 players in the browser, with a lobby and voice
  chat.
- CPU opponents at several difficulty levels.
- Responsive and fully usable on a phone; fully playable with the keyboard
  on desktop.
- English and Slovak.
- Python backend.

## Architecture

```
browser (Svelte SPA) ──WebSocket──▶ Python server (game state, CPU players)
        │                                     │
        └──── WebRTC audio, peer to peer ─────┘ (server only relays signalling)
```

- **The server is the authority.** It holds every room's state, validates
  every action and sends each player only what they may see: their own hand,
  the table, other players' card counts and who is staging which piles.
- **One process, state in memory.** Rooms live in memory in a single
  asyncio process. This is enough for family use; a server restart ends
  running games. Persistence can be added later if needed.
- **No accounts.** Players pick a name. A token stored in the browser lets
  a player reconnect to their seat after a dropped connection.

## Lobby

- Creating a game opens its lobby and gives the host an **invite link**
  (`wildjoker.0s.is/j/ABCD`) with copy and share buttons (the phone's
  share menu where available). The 4-letter code is shown as well.
- Opening the link asks for a name and drops the player straight into the
  lobby.
- Everyone in the lobby sees it fill up live: players joining and leaving,
  and who is connected to voice.
- The host sets the game options (number of decks, cards per player),
  adds or removes CPU players and their difficulty, and starts the game
  once there are at least 2 players.
- Voice chat already works in the lobby and carries on into the game.

## Backend (Python)

- Python 3.13, managed with `uv`.
- **Starlette + uvicorn**: one WebSocket endpoint for the game, plus static
  files and a health check. Messages are JSON, validated with **pydantic**.
- Modules:
  - `engine/`: pure game logic with no I/O, fully unit-tested: cards,
    pile validation (runs, sets, jokers), dealing, the staging area, the
    15-second timeout, finishing order and the end of the game.
  - `solver/`: finds the best rearrangement of a set of piles plus a hand
    (see below). Used by CPU players and stalemate detection.
  - `cpu/`: CPU players as asyncio tasks that act through the same
    actions as humans.
  - `rooms/`: lobby, rooms, seats, reconnects, and message routing.
- CPU search runs in a process pool so it never blocks the event loop.

### Messages

Clients send actions, such as `draw`, `open`, `stage_take`,
`stage_update` and `stage_commit`. The server answers with errors or state
updates. Every update carries a version number, so a client can detect
missed messages and request a full state. Each room has a single ordered
action queue, so two players can never grab the same pile.

## The solver

The core question for both CPU players and stalemate detection is: given
some piles and a hand, what valid rearrangement puts the most cards from the
hand onto the table?

This is a known problem from Rummikub, which can be written as an integer
linear program (den Hertog & Hulshof, 2006) and solved quickly with an ILP
solver (**HiGHS** via `highspy`, no license needed). With jokers counting as
wildcards and up to 3 decks the model stays small (at most 162 cards), so a
solve takes milliseconds to tens of milliseconds.

The solver can be limited to a subset of the piles, which matters because
staging locks the piles involved: a good move touches as few piles as
possible.

## CPU players

A CPU player keeps checking whether it has a move, acts on it, and otherwise
draws. Difficulty is a combination of three separate dimensions:

| | Easy | Medium | Hard | Expert |
|---|---|---|---|---|
| **Reaction speed:** delay before it notices a new table or a new card | 6–10 s | 3–6 s | 1.5–3 s | 0.5–1.5 s |
| **Move complexity:** what kinds of moves it can find | add to a pile, new pile from hand | + take cards from piles, swap jokers | + split piles, rearrange 2–3 piles | full solver across any number of piles |
| **Smartness:** how it plays | plays anything it finds | plays the move that sheds most cards | + keeps jokers for later, opens early | + waits to play cards others can't use, watches who is close to going out |

- Each level also takes time to "work out" a move, proportional to how
  complicated it is, so an Expert CPU is fast but not instant.
- Easy and Medium sometimes miss moves they could have made.
- CPUs don't draw repeatedly while they still have a useful move.
- The settings are kept separate in code, so mixed or custom levels are
  easy to add later.

## Frontend

- **Svelte 5 + TypeScript + Vite**, built as a static single-page app and
  served by the Python server.
- Pile validation is written in TypeScript as well, so the staging area can
  show instantly which piles are valid. Both implementations run the same
  shared JSON test cases, so they can't drift apart; the server is still the
  authority.

### Phone

- Designed for a portrait phone first: the table scrolls in the middle, the
  hand sits at the bottom, and the staging area opens as a sheet over the
  table.
- **Tap to select, tap to place** as the main interaction, because dragging
  small cards on a phone is fiddly. Dragging also works where it's
  comfortable.
- Large touch targets, cards that overlap in the hand to fit, and no hover
  effects that are needed to play.
- Tested on real phone screen sizes with Playwright device profiles, and
  checked by you on your own phone.

### Keyboard

- Arrow keys move between cards and piles; Enter selects and places, Esc
  cancels.
- Single-key shortcuts: **D** draw, **S** start or commit staging, **Esc**
  cancel staging, **H** jump to hand, **T** jump to table, **M** mute or
  unmute, **?** list all shortcuts.
- A visible focus outline everywhere. Screen-reader labels for cards come
  at no extra cost from the same work.

### Languages

- English and Slovak, switchable at any time and remembered per browser,
  with the browser's language as the default.
- All text lives in translation files (`en.json`, `sk.json`); a test fails
  when a key is missing from either.

## Voice chat

- WebRTC audio, peer to peer between all players in a room (at most 7
  connections each, fine for audio). The game WebSocket relays the
  connection setup.
- Available from the moment a player enters the lobby.
- Joining voice is opt-in (the browser asks for the microphone). Once
  joined, the microphone is open, with a mute button and a speaking
  indicator next to each player.
- Players on mobile networks often need a **TURN relay server** to connect.
  **coturn** runs next to the game server; you install it, following steps
  I'll write when we get there.

## Hosting

- Served from the same server as bbl3d.0s.is, behind Caddy, for example at
  `wildjoker.0s.is` (Caddy handles TLS and WebSocket upgrade).
- The game runs as a single Docker container; coturn runs alongside it,
  installed by you.

## Repository layout

```
backend/     Python server: engine, solver, cpu, rooms, tests
frontend/    Svelte app, translations, tests
shared/      JSON test cases for pile validation, used by both sides
e2e/         Playwright tests: phone and desktop, keyboard-only game
```

## Build order

1. **Engine:** cards, pile validation, staging, end of game, with the
   shared test cases.
2. **Solver**, plus stalemate detection.
3. **Server:** rooms, lobby, WebSocket protocol, reconnects.
4. **Frontend:** lobby and table, phone layout and keyboard controls,
   English and Slovak.
5. **CPU players:** the four difficulty levels.
6. **Voice chat**, plus TURN.
7. **Deployment** to wildjoker.0s.is.

Each step ends with tests and something you can try. After step 4 you can
play against other people in the browser, and after step 5 against CPUs.
