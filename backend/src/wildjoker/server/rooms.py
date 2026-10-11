"""Rooms: seats, lobby, running a game and telling everyone about it.

Everything here runs on the event loop. Room methods that change state are
synchronous, so actions from different players are applied one at a time in
arrival order. Outgoing messages go through each connection's ``send``,
which must not block (see ``app.Outbox``).
"""

from __future__ import annotations

import asyncio
import copy
import logging
import secrets
import time
from collections.abc import Callable
from concurrent.futures import Executor
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from ..engine import Config, Game, GameError
from ..engine.game import MAX_PLAYERS, MIN_PLAYERS, STAGING_TIMEOUT
from ..solver import is_stalemate
from . import protocol as p

log = logging.getLogger(__name__)

CODE_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # no I or O
# How much faster CPUs play while a room is fast-forwarded.
FAST_FORWARD = 20.0
CPU_NAMES = ["Ada", "Boris", "Cyril", "Dora", "Emil", "Fiona", "Gustav", "Hana"]


class Connection(Protocol):
    def send(self, message: dict[str, Any]) -> None: ...
    def close(self, code: int = 1000) -> None: ...


@dataclass
class Settings:
    staging_timeout: float = STAGING_TIMEOUT
    # Seconds without a change, once the deck is empty, before looking for a
    # stalemate.
    stalemate_idle: float = 20.0
    # Rooms with nobody connected are removed after this many seconds.
    room_idle: float = 600.0
    clock: Callable[[], float] = time.monotonic
    # Where stalemate searches and CPU move searches run; None means the
    # loop's default executor.
    executor: Executor | None = None
    # Scales how fast CPU players react, think and draw (2.0 = twice as fast).
    cpu_speed: float = 1.0


@dataclass
class Seat:
    id: str
    name: str
    token: str
    cpu: p.CpuLevel | None = None
    conn: Connection | None = None
    voice: bool = False
    muted: bool = False

    @property
    def connected(self) -> bool:
        return self.cpu is not None or self.conn is not None


@dataclass
class Room:
    code: str
    settings: Settings
    seats: dict[str, Seat] = field(default_factory=dict)
    host: str | None = None
    decks: int = 2
    hand_size: int = 5
    phase: Literal["lobby", "playing", "finished"] = "lobby"
    game: Game | None = None
    version: int = 0
    # Only CPUs are still playing and a human asked to speed them up.
    fast_forward: bool = False
    last_activity: float = 0.0
    closed: bool = False
    # Called after every change and on close; CPU players hook in here.
    listeners: list[Callable[[Room], None]] = field(default_factory=list)
    _expiry: asyncio.TimerHandle | None = None
    _stalemate: asyncio.TimerHandle | None = None

    # -- seats -------------------------------------------------------------

    def add_seat(self, name: str, conn: Connection | None, cpu: p.CpuLevel | None = None) -> Seat:
        if self.phase != "lobby":
            raise GameError("game_in_progress")
        if len(self.seats) >= MAX_PLAYERS:
            raise GameError("room_full")
        seat = Seat(secrets.token_hex(4), name, secrets.token_urlsafe(16), cpu=cpu, conn=conn)
        self.seats[seat.id] = seat
        if self.host is None and cpu is None:
            self.host = seat.id
        self.changed()
        return seat

    def connect(self, seat: Seat, conn: Connection) -> None:
        """Attach a new connection to a seat, replacing any previous one."""
        old, seat.conn = seat.conn, conn
        if old is not None:
            old.close(4000)  # replaced by a newer connection
        seat.voice = False
        self.changed()

    def disconnect(self, seat: Seat, conn: Connection) -> None:
        if seat.conn is not conn:
            return
        seat.conn = None
        seat.voice = False
        self.changed()

    def humans(self) -> list[Seat]:
        return [s for s in self.seats.values() if s.cpu is None]

    # -- handling messages -------------------------------------------------

    def handle(self, pid: str, msg: p.Message) -> dict[str, Any] | None:
        """Apply a message from a seated player; returns extra reply data."""
        seat = self.seats[pid]
        now = self.settings.clock()
        self.last_activity = now
        match msg:
            case p.Ping():
                return None
            case p.Leave():
                self._leave(seat)
            case p.SetOptions(decks=decks, hand_size=hand_size):
                self._host_in_lobby(pid)
                Config(decks, hand_size).check(max(len(self.seats), MIN_PLAYERS))
                self.decks, self.hand_size = decks, hand_size
                self.changed()
            case p.AddCpu(level=level):
                self._host_in_lobby(pid)
                self.add_seat(self._cpu_name(), None, cpu=level)
            case p.SetCpuLevel(player=player, level=level):
                self._host_in_lobby(pid)
                target = self.seats.get(player)
                if target is None or target.cpu is None:
                    raise GameError("bad_player")
                target.cpu = level
                self.changed()
            case p.RemovePlayer(player=player):
                self._host_in_lobby(pid)
                target = self.seats.get(player)
                if target is None or player == pid:
                    raise GameError("bad_player")
                self._remove(target)
                if target.conn is not None:
                    target.conn.send({"type": "event", "kind": "kicked"})
                    target.conn.close()
            case p.Start():
                self._host_in_lobby(pid)
                self._start()
            case p.FastForward(on=on):
                if seat.cpu is not None:
                    raise GameError("bad_player")
                if on and not self.only_cpus_left:
                    raise GameError("humans_playing")
                self.fast_forward = on
                self.changed()
            case p.BackToLobby():
                if pid != self.host:
                    raise GameError("not_host")
                if self.phase != "finished":
                    raise GameError("game_in_progress")
                self.phase, self.game = "lobby", None
                self.changed()
            case p.VoiceJoin():
                seat.voice, seat.muted = True, False
                self.changed()
            case p.VoiceLeave():
                seat.voice = False
                self.changed()
            case p.VoiceMute(muted=muted):
                seat.muted = muted
                self.changed()
            case p.Signal(to=to, data=data):
                target = self.seats.get(to)
                if not (seat.voice and target and target.voice and target.conn):
                    raise GameError("not_in_voice")
                target.conn.send({"type": "signal", "from": pid, "data": data})
            case _:
                return self.act(pid, msg, now)
        return None

    def act(self, pid: str, msg: p.Message, now: float | None = None) -> dict[str, Any] | None:
        """A game action, from a human or a CPU player."""
        if self.phase != "playing" or self.game is None:
            raise GameError("no_game")
        now = self.settings.clock() if now is None else now
        game = self.game
        places = len(game.places)
        reply = None
        match msg:
            case p.Draw():
                reply = {"card": game.draw(pid).id}
            case p.Open(cards=cards):
                reply = {"pile": game.open(pid, cards).id}
            case p.Stage(piles=piles):
                game.stage(pid, piles, now)
            case p.Cancel():
                game.cancel(pid)
            case p.Commit(piles=piles):
                try:
                    reply = {"piles": [pile.id for pile in game.commit(pid, piles, now)]}
                except GameError as e:
                    if e.code == "staging_expired":
                        self.changed()
                    raise
            case p.VoteDraw():
                game.vote_draw(pid)
            case _:
                raise GameError("bad_message")
        for place in game.places[places:]:
            for out in place:
                self.broadcast({"type": "event", "kind": "went_out", "player": out})
        if game.status == "finished":
            self.phase = "finished"
        self.changed()
        return reply

    # -- views -------------------------------------------------------------

    def view(self, pid: str | None) -> dict[str, Any]:
        game = self.game
        players = []
        for seat in self.seats.values():
            info: dict[str, Any] = {
                "id": seat.id,
                "name": seat.name,
                "cpu": seat.cpu,
                "connected": seat.connected,
                "voice": seat.voice,
                "muted": seat.muted,
            }
            if game and seat.id in game.players:
                player = game.players[seat.id]
                info["cards"] = len(player.hand)
                info["opened"] = player.opened
                info["place"] = next(
                    (i + 1 for i, place in enumerate(game.places) if seat.id in place), None
                )
            players.append(info)
        result: dict[str, Any] = {
            "type": "state",
            "version": self.version,
            "code": self.code,
            "phase": self.phase,
            "host": self.host,
            "you": pid,
            "options": {"decks": self.decks, "hand_size": self.hand_size},
            "fast_forward": self.fast_forward,
            "players": players,
            "game": None,
        }
        if game:
            now = self.settings.clock()
            result["game"] = {
                "version": game.version,
                "deck": len(game.deck),
                "table": [
                    {
                        "id": pile.id,
                        "cards": [c.id for c in pile.cards],
                        "locked_by": pile.locked_by,
                    }
                    for pile in game.table.values()
                ],
                "places": game.places,
                "draw_votes": sorted(game.draw_votes),
                "staging_timeout": game.config.staging_timeout,
            }
            if pid in game.players:
                result["game"]["hand"] = [c.id for c in game.players[pid].hand]
                staging = game.staging.get(pid)
                result["game"]["staging"] = staging and {
                    "piles": staging.pile_ids,
                    "remaining": max(0.0, game.config.staging_timeout - (now - staging.started)),
                }
        return result

    # -- change notification and timers ------------------------------------

    @property
    def only_cpus_left(self) -> bool:
        """A game is running and everyone still holding cards is a CPU."""
        if self.phase != "playing" or self.game is None:
            return False
        active = self.game.active
        return bool(active) and all(self.seats[pid].cpu is not None for pid in active)

    def changed(self) -> None:
        if self.fast_forward and not self.only_cpus_left:
            self.fast_forward = False  # a human took a seat back, or the game ended
        self.version += 1
        self.last_activity = self.settings.clock()
        for seat in self.seats.values():
            if seat.conn is not None:
                seat.conn.send(self.view(seat.id))
        self._schedule_timers()
        for listener in list(self.listeners):
            listener(self)

    def broadcast(self, message: dict[str, Any]) -> None:
        for seat in self.seats.values():
            if seat.conn is not None:
                seat.conn.send(message)

    def close(self) -> None:
        self.closed = True
        for handle in (self._expiry, self._stalemate):
            if handle:
                handle.cancel()
        for seat in self.seats.values():
            if seat.conn is not None:
                seat.conn.close()
        for listener in list(self.listeners):
            listener(self)

    def _schedule_timers(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # no loop (plain unit tests): timers are driven by hand
        for handle in (self._expiry, self._stalemate):
            if handle:
                handle.cancel()
        self._expiry = self._stalemate = None
        game = self.game
        if self.phase != "playing" or game is None:
            return
        if game.staging:
            first = min(s.started for s in game.staging.values())
            delay = first + game.config.staging_timeout - self.settings.clock()
            self._expiry = loop.call_later(max(0.0, delay) + 0.01, self.expire_staging)
        if not game.deck:
            idle = self.settings.stalemate_idle / (FAST_FORWARD if self.fast_forward else 1.0)
            self._stalemate = loop.call_later(idle, self._check_stalemate)

    def expire_staging(self) -> None:
        if self.game is None or self.phase != "playing":
            return
        expired = self.game.expire(self.settings.clock())
        for pid in expired:
            seat = self.seats[pid]
            if seat.conn is not None:
                seat.conn.send({"type": "event", "kind": "staging_expired"})
        if expired:
            self.changed()
        else:
            self._schedule_timers()

    def _check_stalemate(self) -> None:
        game = self.game
        if game is None or self.phase != "playing":
            return
        version, snapshot = game.version, copy.deepcopy(game)
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(self.settings.executor, is_stalemate, snapshot)

        def done(f: asyncio.Future) -> None:
            if f.cancelled() or f.exception():
                if not f.cancelled():
                    log.error("stalemate check failed", exc_info=f.exception())
                return
            if f.result() and self.game is game and game.version == version:
                game.end_in_stalemate()
                self.phase = "finished"
                self.broadcast({"type": "event", "kind": "stalemate"})
                self.changed()

        future.add_done_callback(done)

    # -- helpers -----------------------------------------------------------

    def _host_in_lobby(self, pid: str) -> None:
        if pid != self.host:
            raise GameError("not_host")
        if self.phase != "lobby":
            raise GameError("game_in_progress")

    def _start(self) -> None:
        if len(self.seats) < MIN_PLAYERS:
            raise GameError("not_enough_players")
        config = Config(self.decks, self.hand_size, self.settings.staging_timeout)
        self.game = Game.new(list(self.seats), config)
        self.phase = "playing"
        self.changed()

    def _leave(self, seat: Seat) -> None:
        """The player leaves; the caller closes their connection."""
        if self.phase == "playing" and self.game and seat.id in self.game.players:
            # A CPU takes over the seat so the game goes on (it has nothing to
            # do if the player had already gone out).
            seat.cpu = "medium"
            seat.conn = None
            seat.voice = False
            if self.host == seat.id:
                self._pick_host(exclude=seat.id)
            self.changed()
        else:
            self._remove(seat)

    def _remove(self, seat: Seat) -> None:
        if self.phase == "playing" and self.game and seat.id in self.game.players:
            raise GameError("game_in_progress")
        del self.seats[seat.id]
        if self.host == seat.id:
            self._pick_host(exclude=seat.id)
        self.changed()

    def _pick_host(self, exclude: str) -> None:
        self.host = next((s.id for s in self.humans() if s.id != exclude), None)

    def _cpu_name(self) -> str:
        taken = {s.name for s in self.seats.values()}
        return next((n for n in CPU_NAMES if n not in taken), f"CPU {len(self.seats) + 1}")


class RoomManager:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.rooms: dict[str, Room] = {}
        # Hook for CPU players: called with every new room.
        self.on_room_created: list[Callable[[Room], None]] = []

    def create(self, name: str) -> tuple[Room, Seat]:
        """A new room with its host seated; attach the host with ``room.connect``."""
        code = self._new_code()
        room = Room(code, self.settings, last_activity=self.settings.clock())
        self.rooms[code] = room
        for hook in self.on_room_created:
            hook(room)
        return room, room.add_seat(name, None)

    def join(self, code: str, name: str) -> tuple[Room, Seat]:
        room = self._get(code)
        return room, room.add_seat(name, None)

    def resume(self, code: str, token: str) -> tuple[Room, Seat]:
        room = self._get(code)
        seat = next(
            (s for s in room.seats.values() if secrets.compare_digest(s.token, token)), None
        )
        if seat is None:
            raise GameError("bad_token")
        if seat.cpu is not None:
            # Taking a seat back from the CPU that stood in.
            seat.cpu = None
            if room.host is None:
                room.host = seat.id
        return room, seat

    def leave_empty(self, room: Room) -> None:
        """Drop a room once no humans are seated."""
        if not room.humans() and self.rooms.get(room.code) is room:
            room.close()
            del self.rooms[room.code]

    def reap(self) -> list[str]:
        """Remove rooms nobody has been connected to for a while."""
        now = self.settings.clock()
        idle = [
            code
            for code, room in self.rooms.items()
            if not any(s.conn for s in room.seats.values())
            and now - room.last_activity > self.settings.room_idle
        ]
        for code in idle:
            self.rooms.pop(code).close()
        return idle

    def _get(self, code: str) -> Room:
        room = self.rooms.get(code)
        if room is None:
            raise GameError("no_room")
        return room

    def _new_code(self) -> str:
        while True:
            code = "".join(secrets.choice(CODE_LETTERS) for _ in range(4))
            if code not in self.rooms:
                return code
