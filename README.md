# Wild Joker

A real-time multiplayer card game for the browser: rummy with no turns,
where everyone plays at once and the table can be rearranged freely.

- [RULES.md](RULES.md): the rules
- [DESIGN.md](DESIGN.md): architecture and plans
- [shared/protocol.md](shared/protocol.md): client–server messages

## Backend

Python 3.13 with [uv](https://docs.astral.sh/uv/).

```bash
cd backend
uv sync
uv run pytest                      # tests
uv run ruff check . && uv run ruff format --check .
uv run python -m wildjoker.server  # http://127.0.0.1:8000, WebSocket at /ws
```

The server serves the built frontend from `frontend/dist` (or
`$WILDJOKER_STATIC`).

## Frontend

Svelte 5 + TypeScript + Vite, in `frontend/`. Node 20.19 or newer.

```bash
cd frontend
npm ci
npm run dev     # http://127.0.0.1:5181, proxies /ws to a backend on :8101
npm test        # Vitest: pile rules (shared/piles.json), the draft move, translations
npm run check   # svelte-check
npm run build   # frontend/dist, served by the backend
```

`npm run dev` expects a backend on port 8101
(`uv run python -m wildjoker.server --port 8101`); set
`WILDJOKER_BACKEND` to use another one. All UI text is in
`src/i18n/en.json` and `src/i18n/sk.json`; a test fails when the two
files don't have the same keys.

## Browser tests

Python Playwright tests in `e2e/`, run in the Playwright Docker image
(no local browsers needed):

```bash
e2e/run.sh                        # all tests
e2e/run.sh -k keyboard -x         # pytest arguments pass through
```

The script builds the frontend if `frontend/dist` is missing, starts a
backend on `$PORT` (default 8101) unless one is already running, installs
`playwright` and `pytest` for the container once into `$E2E_DEPS`
(default `~/envs/wildjoker-e2e`), and runs pytest in
`mcr.microsoft.com/playwright/python:v1.58.0-noble` with host networking.
Screenshots of the lobby and the game at phone (375 × 667) and desktop
sizes are written to `screenshots/`. Tests fail on any JavaScript error
in the page.
