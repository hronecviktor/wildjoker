"""Messages from the client.

Every client message is a JSON object with a ``type`` and an optional
``req`` id; the server echoes ``req`` in its ``ok`` or ``error`` reply so the
client can match them. Server messages are plain dicts built in ``rooms``:

- ``welcome``: ``{you, token, code}`` after create/join/resume
- ``state``: the full room as this player may see it, after every change
- ``ok`` / ``error``: ``{req, code?}`` replies to a client message
- ``signal``: ``{from, data}`` relayed WebRTC signalling
- ``event``: ``{kind, ...}`` notable moments for toasts, sounds and
  animations (``drew``, ``went_out``, ``staging_expired``, ``stalemate``,
  ``kicked``; in Gin also ``took``, ``discarded``, ``one_card``, ``gin``
  and ``stock_out``)
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
GameKind = Literal["wild", "gin"]


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    req: int | None = None


# -- joining -----------------------------------------------------------------


class Create(Message):
    type: Literal["create"]
    name: Name
    game: GameKind = "wild"


class Join(Message):
    type: Literal["join"]
    code: RoomCode
    name: Name


class Tutorial(Message):
    """A private tutorial game against a scripted Teacher (see ``tutorial``)."""

    type: Literal["tutorial"]
    name: Name
    teacher: Name


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


class Take(Message):
    """Gin: take a card from the discard pile, with every card above it."""

    type: Literal["take"]
    card: int


class Meld(Message):
    """Gin: put a new meld on the table from your hand."""

    type: Literal["meld"]
    cards: CardIds


class LayOff(Message):
    """Gin: add cards from your hand to a meld on the table."""

    type: Literal["lay_off"]
    pile: int
    cards: CardIds


class Discard(Message):
    """Gin: discard a card, ending your turn."""

    type: Literal["discard"]
    card: int


class NextRound(Message):
    """Gin, host only: deal the next round after the scores were shown."""

    type: Literal["next_round"]


class VoteDraw(Message):
    type: Literal["vote_draw"]


class TutorialAction(Message):
    type: Literal["tutorial_action"]
    action: Literal["teacher_opens", "teacher_borrows"]


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
    | Tutorial
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
    | Take
    | Meld
    | LayOff
    | Discard
    | NextRound
    | FastForward
    | TutorialAction
    | VoiceJoin
    | VoiceLeave
    | VoiceMute
    | Signal
    | Ping,
    Field(discriminator="type"),
]

client_message = TypeAdapter(ClientMessage)
