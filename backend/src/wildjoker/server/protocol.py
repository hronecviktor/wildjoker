"""Messages from the client.

Every client message is a JSON object with a ``type`` and an optional
``req`` id; the server echoes ``req`` in its ``ok`` or ``error`` reply so the
client can match them. Server messages are plain dicts built in ``rooms``:

- ``welcome``: ``{you, token, code}`` after create/join/resume
- ``state``: the full room as this player may see it, after every change
- ``ok`` / ``error``: ``{req, code?}`` replies to a client message
- ``signal``: ``{from, data}`` relayed WebRTC signalling
- ``event``: ``{kind, ...}`` notable moments for toasts (``went_out``,
  ``staging_expired``, ``stalemate``, ``kicked``)
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, TypeAdapter

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
RoomCode = Annotated[
    str,
    BeforeValidator(lambda v: v.strip().upper() if isinstance(v, str) else v),
    StringConstraints(pattern=r"^[A-Z]{4}$"),
]
CardIds = Annotated[list[int], Field(max_length=200)]
CpuLevel = Literal["easy", "medium", "hard", "expert"]


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    req: int | None = None


# -- joining -----------------------------------------------------------------


class Create(Message):
    type: Literal["create"]
    name: Name


class Join(Message):
    type: Literal["join"]
    code: RoomCode
    name: Name


class Resume(Message):
    type: Literal["resume"]
    code: RoomCode
    token: Annotated[str, Field(max_length=64)]


# -- lobby (host only, except leave) -----------------------------------------


class SetOptions(Message):
    type: Literal["set_options"]
    decks: Annotated[int, Field(ge=1, le=3)]
    hand_size: Annotated[int, Field(ge=1, le=15)]


class AddCpu(Message):
    type: Literal["add_cpu"]
    level: CpuLevel


class SetCpuLevel(Message):
    type: Literal["set_cpu_level"]
    player: str
    level: CpuLevel


class RemovePlayer(Message):
    type: Literal["remove_player"]
    player: str


class Start(Message):
    type: Literal["start"]


class BackToLobby(Message):
    type: Literal["back_to_lobby"]


class Leave(Message):
    type: Literal["leave"]


# -- game --------------------------------------------------------------------


class Draw(Message):
    type: Literal["draw"]


class Open(Message):
    type: Literal["open"]
    cards: CardIds


class Stage(Message):
    type: Literal["stage"]
    piles: Annotated[list[int], Field(max_length=100)]


class Cancel(Message):
    type: Literal["cancel"]


class Commit(Message):
    type: Literal["commit"]
    piles: Annotated[list[CardIds], Field(max_length=100)]


class VoteDraw(Message):
    type: Literal["vote_draw"]


class FastForward(Message):
    type: Literal["fast_forward"]
    on: bool


# -- voice -------------------------------------------------------------------


class VoiceJoin(Message):
    type: Literal["voice_join"]


class VoiceLeave(Message):
    type: Literal["voice_leave"]


class VoiceMute(Message):
    type: Literal["voice_mute"]
    muted: bool


class Signal(Message):
    type: Literal["signal"]
    to: str
    data: dict[str, Any]


class Ping(Message):
    type: Literal["ping"]


ClientMessage = Annotated[
    Create
    | Join
    | Resume
    | SetOptions
    | AddCpu
    | SetCpuLevel
    | RemovePlayer
    | Start
    | BackToLobby
    | Leave
    | Draw
    | Open
    | Stage
    | Cancel
    | Commit
    | VoteDraw
    | FastForward
    | VoiceJoin
    | VoiceLeave
    | VoiceMute
    | Signal
    | Ping,
    Field(discriminator="type"),
]

client_message = TypeAdapter(ClientMessage)
