"""Gin rooms: the game actions and what each player sees (see ``engine.gin``).

``Room`` hands Gin games over to these functions; seats, the lobby, voice
and reconnects work the same for both games.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..engine import GameError
from ..engine.gin import GinGame
from . import protocol as p

if TYPE_CHECKING:
    from .rooms import Room


def act(room: Room, pid: str, msg: p.Message) -> dict[str, Any] | None:
    """A Gin action from a player; ``Room.act`` checks the room is playing."""
    game: GinGame = room.game
    before = game.round
    reply = None
    match msg:
        case p.Draw():
            card = game.draw(pid)
            if card is None:
                room.broadcast({"type": "event", "kind": "stock_out"})
            else:
                reply = {"card": card.id}
                room.broadcast({"type": "event", "kind": "drew", "player": pid})
        case p.Take(card=card):
            taken = game.take(pid, card)
            reply = {"cards": [c.id for c in taken]}
            room.broadcast({"type": "event", "kind": "took", "player": pid, "count": len(taken)})
        case p.Meld(cards=cards):
            reply = {"pile": game.meld(pid, cards).id}
        case p.LayOff(pile=pile, cards=cards):
            game.lay_off(pid, pile, cards)
        case p.Discard(card=card):
            game.discard(pid, card)
            room.broadcast({"type": "event", "kind": "discarded", "player": pid})
            if before.result is not None:
                room.broadcast({"type": "event", "kind": "gin", "player": pid})
            elif len(before.hands[pid]) == 1:
                # Everyone hears it, so they can get rid of their high cards.
                room.broadcast({"type": "event", "kind": "one_card", "player": pid})
        case p.NextRound():
            if pid != room.host:
                raise GameError("not_host")
            game.next_round()
        case _:
            raise GameError("bad_message")
    if game.status == "finished":
        room.phase = "finished"
    room.changed()
    return reply


def view(room: Room, pid: str | None) -> dict[str, Any]:
    game: GinGame = room.game
    rnd = game.round
    over = game.status != "playing"
    result = rnd.result
    out: dict[str, Any] = {
        "kind": "gin",
        "version": game.version,
        "round": len(game.history) + (0 if over else 1),
        "status": game.status,
        "deck": len(rnd.stock),
        "discard": [c.id for c in rnd.discard],
        # Each card on the table with who put it there (their points).
        "melds": [
            {
                "id": m.id,
                "cards": [c.id for c in m.cards],
                "owners": [m.owners[c.id] for c in m.cards],
            }
            for m in rnd.melds.values()
        ],
        "dealer": rnd.dealer,
        "turn": None if over else rnd.turn,
        "step": rnd.step,
        "picked": rnd.picked,
        "must_play": rnd.must_play,
        "scores": dict(game.scores),
        "target": game.target,
        "history": [r.scores for r in game.history],
        "result": result
        and {
            "gin": result.gin,
            "table": result.table,
            "hand": result.hand,
            "scores": result.scores,
            # Everyone's cards at the end, so the score can be checked.
            "hands": {p_: [c.id for c in h] for p_, h in rnd.hands.items()},
        },
        "winner": game.winner,
        "places": game.places() if game.status == "finished" else [],
    }
    if pid in rnd.hands:
        out["hand"] = [c.id for c in rnd.hands[pid]]
        mine = not over and rnd.turn == pid and rnd.step == "draw"
        # Which discards the player could take now (deeper ones only if
        # they could be played this turn).
        out["takeable"] = [c.id for c in rnd.discard if mine and game.can_take(pid, c.id)]
    return out


def place(game: GinGame, pid: str) -> int | None:
    if game.status != "finished":
        return None
    return next(i + 1 for i, ids in enumerate(game.places()) if pid in ids)
