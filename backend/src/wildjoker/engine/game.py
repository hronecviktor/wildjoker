"""Game state and the actions players take.

The engine is synchronous and does no I/O. Callers pass the current time to
the actions that depend on it, so tests control the clock. Every successful
action bumps ``version``; failed actions raise ``GameError`` and change
nothing.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Literal

from .cards import CARDS_PER_DECK, Card, shuffled_deck
from .piles import arrange, is_valid_opening

MIN_PLAYERS = 2
MAX_PLAYERS = 8
STAGING_TIMEOUT = 15.0


class GameError(Exception):
    """A rejected action. ``code`` is stable and translated by the client."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class Config:
    decks: int = 2
    hand_size: int = 5
    staging_timeout: float = STAGING_TIMEOUT

    def check(self, players: int) -> None:
        if not 1 <= self.decks <= 3:
            raise GameError("bad_config", "decks must be 1-3")
        if not 1 <= self.hand_size <= 15:
            raise GameError("bad_config", "hand size must be 1-15")
        if not MIN_PLAYERS <= players <= MAX_PLAYERS:
            raise GameError("bad_config", f"{MIN_PLAYERS}-{MAX_PLAYERS} players")
        if players * self.hand_size > self.decks * CARDS_PER_DECK:
            raise GameError("bad_config", "not enough cards to deal")


@dataclass
class Pile:
    id: int
    cards: tuple[Card, ...]  # canonical order, see piles.arrange
    locked_by: str | None = None


@dataclass
class Staging:
    pile_ids: list[int]
    started: float


@dataclass
class Player:
    id: str
    hand: list[Card]
    opened: bool = False


@dataclass
class Game:
    players: dict[str, Player]
    deck: list[Card]
    config: Config = field(default_factory=Config)
    table: dict[int, Pile] = field(default_factory=dict)
    staging: dict[str, Staging] = field(default_factory=dict)
    # Finishing places in order; a stalemate puts the remaining players in one
    # shared place.
    places: list[list[str]] = field(default_factory=list)
    status: Literal["playing", "finished"] = "playing"
    draw_votes: set[str] = field(default_factory=set)
    version: int = 0
    _next_pile_id: int = 1

    @classmethod
    def new(cls, player_ids: list[str], config: Config | None = None, seed: int | None = None):
        config = config or Config()
        config.check(len(player_ids))
        if len(set(player_ids)) != len(player_ids):
            raise GameError("bad_config", "duplicate player id")
        deck = shuffled_deck(config.decks, random.Random(seed))
        players = {}
        for pid in player_ids:
            hand, deck = deck[: config.hand_size], deck[config.hand_size :]
            players[pid] = Player(pid, hand)
        return cls(players=players, deck=deck, config=config)

    # -- queries -----------------------------------------------------------

    @property
    def active(self) -> list[str]:
        """Players still holding cards, in seating order."""
        out = {pid for place in self.places for pid in place}
        return [pid for pid in self.players if pid not in out]

    def card_counts(self) -> dict[str, int]:
        return {pid: len(p.hand) for pid, p in self.players.items()}

    # -- actions -----------------------------------------------------------

    def draw(self, pid: str) -> Card:
        self._check_active(pid)
        if not self.deck:
            raise GameError("deck_empty")
        card = self.deck.pop()
        self.players[pid].hand.append(card)
        self._changed()
        return card

    def open(self, pid: str, card_ids: list[int]) -> Pile:
        player = self._check_active(pid)
        if player.opened:
            raise GameError("already_opened")
        cards = self._take_from_hand(player, card_ids, remove=False)
        if not is_valid_opening(cards):
            raise GameError("invalid_opening")
        self._take_from_hand(player, card_ids, remove=True)
        player.opened = True
        pile = self._add_pile(cards)
        self._after_hand_change(pid)
        self._changed()
        return pile

    def stage(self, pid: str, pile_ids: list[int], now: float) -> None:
        """Take piles off the table into the player's staging area."""
        player = self._check_active(pid)
        if not player.opened:
            raise GameError("not_opened")
        if len(set(pile_ids)) != len(pile_ids):
            raise GameError("bad_pile")
        for pile_id in pile_ids:
            pile = self.table.get(pile_id)
            if pile is None:
                raise GameError("bad_pile")
            if pile.locked_by is not None:
                raise GameError("pile_locked")
        staging = self.staging.setdefault(pid, Staging([], now))
        for pile_id in pile_ids:
            self.table[pile_id].locked_by = pid
            staging.pile_ids.append(pile_id)
        self._changed()

    def cancel(self, pid: str) -> None:
        if pid not in self.staging:
            raise GameError("not_staging")
        self._release(pid)
        self._changed()

    def commit(self, pid: str, piles: list[list[int]], now: float) -> list[Pile]:
        """Replace the staged piles with ``piles``.

        ``piles`` lists card ids and may use any card from the staged piles
        or the player's hand. Staged cards left out go to the hand. Without a
        staging area this just puts new piles down from the hand.
        """
        player = self._check_active(pid)
        if not player.opened:
            raise GameError("not_opened")
        staging = self.staging.get(pid)
        if staging and now - staging.started > self.config.staging_timeout:
            self._release(pid)
            self._changed()
            raise GameError("staging_expired")
        staged_ids = staging.pile_ids if staging else []
        if not staged_ids and not piles:
            raise GameError("empty_move")

        available = {c.id: c for c in player.hand}
        for pile_id in staged_ids:
            available.update((c.id, c) for c in self.table[pile_id].cards)
        used = [card_id for pile in piles for card_id in pile]
        if len(set(used)) != len(used) or not set(used) <= available.keys():
            raise GameError("bad_card")
        arranged = [arrange(available[i] for i in pile) for pile in piles]
        if any(a is None for a in arranged):
            raise GameError("invalid_pile")

        used_set = set(used)
        leftovers = [c for i in staged_ids for c in self.table[i].cards if c.id not in used_set]
        player.hand = [c for c in player.hand if c.id not in used_set] + leftovers
        for pile_id in staged_ids:
            del self.table[pile_id]
        self.staging.pop(pid, None)
        new_piles = [self._add_pile(a.cards) for a in arranged]
        self.draw_votes.clear()
        self._after_hand_change(pid)
        self._changed()
        return new_piles

    def expire(self, now: float) -> list[str]:
        """Cancel staging areas older than the timeout; returns their players."""
        expired = [
            pid for pid, s in self.staging.items() if now - s.started > self.config.staging_timeout
        ]
        for pid in expired:
            self._release(pid)
        if expired:
            self._changed()
        return expired

    def vote_draw(self, pid: str) -> None:
        """Agree to end the game as a draw; possible once the deck is empty."""
        self._check_active(pid)
        if self.deck:
            raise GameError("deck_not_empty")
        self.draw_votes.add(pid)
        if set(self.active) <= self.draw_votes:
            self.end_in_stalemate()
        else:
            self._changed()

    def end_in_stalemate(self) -> None:
        for pid in list(self.staging):
            self._release(pid)
        self.places.append(self.active)
        self.status = "finished"
        self._changed()

    # -- helpers -----------------------------------------------------------

    def _check_active(self, pid: str) -> Player:
        if self.status != "playing":
            raise GameError("game_over")
        if pid not in self.players:
            raise GameError("unknown_player")
        if pid not in self.active:
            raise GameError("player_out")
        return self.players[pid]

    def _take_from_hand(self, player: Player, card_ids: list[int], remove: bool) -> list[Card]:
        by_id = {c.id: c for c in player.hand}
        if len(set(card_ids)) != len(card_ids) or not set(card_ids) <= by_id.keys():
            raise GameError("bad_card")
        if remove:
            player.hand = [c for c in player.hand if c.id not in set(card_ids)]
        return [by_id[i] for i in card_ids]

    def _add_pile(self, cards) -> Pile:
        arranged = arrange(cards)
        assert arranged is not None
        pile = Pile(self._next_pile_id, arranged.cards)
        self._next_pile_id += 1
        self.table[pile.id] = pile
        return pile

    def _release(self, pid: str) -> None:
        staging = self.staging.pop(pid)
        for pile_id in staging.pile_ids:
            self.table[pile_id].locked_by = None

    def _after_hand_change(self, pid: str) -> None:
        if self.players[pid].hand:
            return
        self.places.append([pid])
        self.draw_votes.discard(pid)
        if len(self.active) <= 1:
            if self.active:
                self.places.append(self.active)
            self.status = "finished"
            for other in list(self.staging):
                self._release(other)

    def _changed(self) -> None:
        self.version += 1
