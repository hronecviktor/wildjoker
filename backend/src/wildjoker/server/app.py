"""The web app: one WebSocket endpoint for the game, plus the static frontend."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketDisconnected

from ..engine import GameError
from . import protocol as p
from .ice import IceConfig
from .rooms import Room, RoomManager, Seat, Settings

log = logging.getLogger(__name__)

MAX_MESSAGE = 64 * 1024
OUTBOX_SIZE = 256
REAP_INTERVAL = 60.0
DEFAULT_STATIC = Path(__file__).parents[4] / "frontend" / "dist"


class Outbox:
    """Queues outgoing messages so a slow client never blocks a room."""

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(OUTBOX_SIZE)
        self.closing: int | None = None
        self.task = asyncio.create_task(self._run())

    def send(self, message: dict[str, Any]) -> None:
        if self.closing is not None:
            return
        try:
            self.queue.put_nowait(message)
        except asyncio.QueueFull:
            log.warning("outbox full, closing connection")
            self.close(1008)

    def close(self, code: int = 1000) -> None:
        if self.closing is None:
            self.closing = code
            with contextlib.suppress(asyncio.QueueFull):
                self.queue.put_nowait(None)

    async def _run(self) -> None:
        try:
            while (message := await self.queue.get()) is not None:
                await self.ws.send_text(json.dumps(message, separators=(",", ":")))
            await self.ws.close(self.closing or 1000)
        except Exception:  # the socket went away; the reader notices too
            pass


async def game_socket(ws: WebSocket) -> None:
    manager: RoomManager = ws.app.state.manager
    await ws.accept()
    outbox = Outbox(ws)
    room: Room | None = None
    seat: Seat | None = None
    try:
        while True:
            text = await ws.receive_text()
            req = None
            try:
                if len(text) > MAX_MESSAGE:
                    raise GameError("too_large")
                try:
                    raw = json.loads(text)
                    req = raw.get("req") if isinstance(raw, dict) else None
                    msg = p.client_message.validate_python(raw)
                except (ValueError, ValidationError) as e:
                    raise GameError("bad_message") from e

                if isinstance(msg, (p.Create, p.Tutorial, p.Join, p.Resume)):
                    if seat is not None:
                        raise GameError("already_joined")
                    match msg:
                        case p.Create(name=name):
                            room, seat = manager.create(name)
                        case p.Tutorial(name=name, teacher=teacher):
                            room, seat = manager.create_tutorial(name, teacher)
                        case p.Join(code=code, name=name):
                            room, seat = manager.join(code, name)
                        case p.Resume(code=code, token=token):
                            room, seat = manager.resume(code, token)
                    outbox.send(
                        {
                            "type": "welcome",
                            "req": req,
                            "code": room.code,
                            "you": seat.id,
                            "token": seat.token,
                        }
                    )
                    room.connect(seat, outbox)
                    continue

                if room is None or seat is None:
                    raise GameError("not_joined")
                if seat.id not in room.seats or room.seats[seat.id].conn is not outbox:
                    raise GameError("not_joined")  # removed, or replaced by a newer connection
                reply = room.handle(seat.id, msg)
                outbox.send({"type": "ok", "req": req, **(reply or {})})
                if isinstance(msg, (p.Leave, p.RemovePlayer)):
                    manager.leave_empty(room)
                if isinstance(msg, p.Leave):
                    outbox.close()
                    room = seat = None
            except GameError as e:
                outbox.send({"type": "error", "req": req, "code": e.code})
    except (WebSocketDisconnect, WebSocketDisconnected):
        pass  # the client went away, or we closed the socket ourselves
    finally:
        if room is not None and seat is not None:
            room.disconnect(seat, outbox)
        outbox.close()


async def health(request) -> Response:
    return PlainTextResponse("ok")


async def ice_servers(request) -> Response:
    """STUN/TURN servers for voice chat, for a player who is connected to a room.

    Asking for the player id keeps the TURN relay from being open to anyone
    on the internet: ids are random and only shared within a room.
    """
    manager: RoomManager = request.app.state.manager
    pid = request.query_params.get("player", "")
    if not any(
        (seat := room.seats.get(pid)) and seat.conn is not None for room in manager.rooms.values()
    ):
        return JSONResponse({"error": "not_joined"}, status_code=403)
    config: IceConfig = request.app.state.ice
    return JSONResponse(config.servers(pid), headers={"Cache-Control": "no-store"})


def create_app(
    settings: Settings | None = None,
    static_dir: Path | None = None,
    process_pool: bool = True,
    ice: IceConfig | None = None,
) -> Starlette:
    settings = settings or Settings()
    static_dir = static_dir or Path(os.environ.get("WILDJOKER_STATIC", DEFAULT_STATIC))

    async def index(request) -> Response:
        page = static_dir / "index.html"
        if not page.exists():
            return PlainTextResponse("frontend not built", status_code=404)
        return FileResponse(page)

    routes = [
        Route("/healthz", health),
        Route("/ice", ice_servers),
        WebSocketRoute("/ws", game_socket),
        Route("/", index),
        Route("/j/{code}", index),  # invite links open the app
    ]
    if (static_dir / "assets").is_dir():
        routes.append(Mount("/assets", StaticFiles(directory=static_dir / "assets")))

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        pool = None
        if process_pool and settings.executor is None:
            pool = settings.executor = ProcessPoolExecutor(max_workers=2)

        async def reaper() -> None:
            while True:
                await asyncio.sleep(REAP_INTERVAL)
                for code in app.state.manager.reap():
                    log.info("removed idle room %s", code)

        task = asyncio.create_task(reaper())
        try:
            yield
        finally:
            task.cancel()
            await app.state.cpus.close()
            if pool is not None:
                pool.shutdown(cancel_futures=True)

    app = Starlette(routes=routes, lifespan=lifespan)
    from ..cpu import CpuPlayers  # here: cpu imports the server's protocol

    app.state.manager = RoomManager(settings)
    app.state.ice = ice or IceConfig.from_env()
    app.state.cpus = CpuPlayers()
    app.state.cpus.attach(app.state.manager)
    return app
