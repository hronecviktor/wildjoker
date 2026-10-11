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
uv run pytest                      # tests (uv run pytest -m slow: long CPU simulations)
uv run ruff check . && uv run ruff format --check .
uv run python -m wildjoker.server  # http://127.0.0.1:8000, WebSocket at /ws
uv run python -m wildjoker.cpu.simulate --games 50 easy expert  # CPU win rates
```

The server serves the built frontend from `frontend/dist` (or
`$WILDJOKER_STATIC`).
