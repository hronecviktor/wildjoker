"""Stalemate detection: deck empty and nobody can get rid of a card."""

from __future__ import annotations

from ..engine import Game, find_opening
from .solve import solve


def can_shed(game: Game, pid: str, time_limit: float | None = None) -> bool:
    """Whether the player has a move that leaves them with fewer cards."""
    player = game.players[pid]
    if not player.opened:
        return find_opening(player.hand) is not None
    table = [c for pile in game.table.values() for c in pile.cards]
    return solve(table + player.hand, time_limit=time_limit).placed > len(table)


def is_stalemate(game: Game) -> bool:
    if game.status != "playing" or game.deck:
        return False
    return not any(can_shed(game, pid) for pid in game.active)
