"""Gin: the family's turn-based rummy, played over rounds to 500 points.

See RULES-GIN.md. One 54-card deck, 7 cards each. On their turn a player
draws (from the stock, or from the discard pile: the top card, or a deeper
card together with every card above it), lays down melds or adds to any meld
on the table, and ends the turn by discarding. A round ends when someone
discards their last card, or when the stock runs out a second time with no
card put on the table since the first; everyone scores the cards they put
on the table minus the cards left in their hand. The game ends after a round in which
someone has 500 points or more, unless the top score is shared.

Melds use the same runs and sets as Wild Joker (``piles.arrange``), but
nothing on the table is ever rearranged: cards are only added. Every card on
the table remembers who put it there, because its points are theirs.

Like ``game``, the engine is synchronous and does no I/O; every successful
action bumps ``version`` and failed actions raise ``GameError`` and change
nothing.
"""

from __future__ import annotations

import random
from collections.abc import Iterable
from dataclasses import dataclass, field
from itertools import combinations
from typing import Literal

from .cards import Card, shuffled_deck
from .game import GameError
from .piles import arrange

MIN_PLAYERS = 2
MAX_PLAYERS = 6
HAND_SIZE = 7
TARGET = 500

JOKER_POINTS = 25
ACE_POINTS = 15
LOW_ACE_POINTS = 5
FACE_POINTS = 10  # 10, J, Q, K
PIP_POINTS = 5  # 2-9


def points(card: Card, low_ace: bool = False) -> int:
    """A card's value. An ace is worth less as the low end of a run (A-2-3)."""
    if card.is_joker:
        return JOKER_POINTS
    if card.rank == 1:
        return LOW_ACE_POINTS if low_ace else ACE_POINTS
    return FACE_POINTS if card.rank >= 10 else PIP_POINTS


def hand_points(cards: Iterable[Card]) -> int:
    return sum(points(c) for c in cards)


@dataclass
class Meld:
    id: int
    cards: tuple[Card, ...]  # canonical order, see piles.arrange
    owners: dict[int, str]  # card id -> who put it down

    def card_points(self) -> dict[int, int]:
        """Each card's points where it lies: a low ace in a run is worth less."""
        arranged = arrange(self.cards)
        assert arranged is not None
        low = set()
        if arranged.kind == "run" and arranged.values:
            low = {c.id for c, v in zip(arranged.cards, arranged.values, strict=True) if v == 1}
        return {c.id: points(c, c.id in low) for c in self.cards}


@dataclass
class RoundResult:
    """How one round was scored. ``gin`` is who went out (None: the round
    ended with the stock used up, see ``Round.refills``)."""

    gin: str | None
    table: dict[str, int]
    hand: dict[str, int]

    @property
    def scores(self) -> dict[str, int]:
        return {pid: self.table[pid] - self.hand[pid] for pid in self.table}


@dataclass
class Round:
    order: list[str]  # seating order
    dealer: str
    hands: dict[str, list[Card]]
    stock: list[Card]  # top is last
    discard: list[Card]  # bottom first, top last
    turn: str
    step: Literal["draw", "play"] = "draw"
    melds: dict[int, Meld] = field(default_factory=dict)
    # The card taken from the discard pile this turn, which can't be
    # discarded again; a deeper card also has to go on the table this turn.
    picked: int | None = None
    must_play: int | None = None
    result: RoundResult | None = None
    next_meld_id: int = 1
    # Times the stock was made again from the discard pile, and whether a card
    # went on the table since: with nothing played, a second refill would go
    # round for ever, so the round ends instead.
    refills: int = 0
    played_since_refill: bool = False

    @classmethod
    def deal(cls, order: list[str], dealer: str, rng: random.Random) -> Round:
        deck = shuffled_deck(1, rng)
        hands = {}
        for pid in order:
            hands[pid], deck = deck[:HAND_SIZE], deck[HAND_SIZE:]
        discard = [deck.pop()]
        first = order[(order.index(dealer) + 1) % len(order)]
        return cls(order, dealer, hands, deck, discard, first)


@dataclass
class GinGame:
    players: list[str]  # seating order
    scores: dict[str, int]
    round: Round
    history: list[RoundResult] = field(default_factory=list)
    status: Literal["playing", "round_over", "finished"] = "playing"
    winner: str | None = None
    target: int = TARGET
    version: int = 0
    rng: random.Random = field(default_factory=random.Random, repr=False)

    kind = "gin"

    @classmethod
    def new(cls, player_ids: list[str], seed: int | None = None, target: int = TARGET) -> GinGame:
        if not MIN_PLAYERS <= len(player_ids) <= MAX_PLAYERS:
            raise GameError("bad_config", f"{MIN_PLAYERS}-{MAX_PLAYERS} players")
        if len(set(player_ids)) != len(player_ids):
            raise GameError("bad_config", "duplicate player id")
        rng = random.Random(seed)
        # The first dealer sits last, so the first player to act sits first.
        first = Round.deal(player_ids, player_ids[-1], rng)
        scores = dict.fromkeys(player_ids, 0)
        return cls(list(player_ids), scores, first, target=target, rng=rng)

    # -- queries -----------------------------------------------------------

    @property
    def active(self) -> list[str]:
        """Everyone takes part until the game is over."""
        return [] if self.status == "finished" else list(self.players)

    def hand(self, pid: str) -> list[Card]:
        return self.round.hands[pid]

    def card_counts(self) -> dict[str, int]:
        return {pid: len(h) for pid, h in self.round.hands.items()}

    def places(self) -> list[list[str]]:
        """Players grouped by total score, best first."""
        by_score: dict[int, list[str]] = {}
        for pid in self.players:
            by_score.setdefault(self.scores[pid], []).append(pid)
        return [by_score[s] for s in sorted(by_score, reverse=True)]

    def can_take(self, pid: str, card_id: int) -> bool:
        """Whether the player could take this card from the discard pile now."""
        try:
            self._check_turn(pid, "draw")
            self._take_plan(pid, card_id)
        except GameError:
            return False
        return True

    # -- actions -----------------------------------------------------------

    def draw(self, pid: str) -> Card | None:
        """Draw the top card of the stock; None if that ended the round."""
        rnd = self._check_turn(pid, "draw")
        if not rnd.stock and len(rnd.discard) > 1:
            if rnd.refills and not rnd.played_since_refill:
                self._end_round(gin=None)
                self._changed()
                return None
            # The discard pile, except its top card, becomes the new stock.
            rnd.stock, rnd.discard = rnd.discard[:-1], rnd.discard[-1:]
            self.rng.shuffle(rnd.stock)
            rnd.refills += 1
            rnd.played_since_refill = False
        if not rnd.stock:
            raise GameError("deck_empty")
        card = rnd.stock.pop()
        rnd.hands[pid].append(card)
        rnd.step = "play"
        self._changed()
        return card

    def take(self, pid: str, card_id: int) -> list[Card]:
        """Take a card from the discard pile, with every card above it."""
        rnd = self._check_turn(pid, "draw")
        depth = self._take_plan(pid, card_id)
        taken = rnd.discard[depth:]
        del rnd.discard[depth:]
        rnd.hands[pid].extend(taken)
        rnd.picked = card_id
        rnd.must_play = card_id if len(taken) > 1 else None
        rnd.step = "play"
        self._changed()
        return taken

    def meld(self, pid: str, card_ids: list[int]) -> Meld:
        """Put a new meld on the table from the hand."""
        rnd = self._check_turn(pid, "play")
        cards = self._from_hand(pid, card_ids)
        arranged = arrange(cards)
        if arranged is None:
            raise GameError("invalid_pile")
        meld = Meld(rnd.next_meld_id, arranged.cards, dict.fromkeys(card_ids, pid))
        self._check_can_finish(pid, card_ids, [*rnd.melds.values(), meld])
        self._remove_from_hand(pid, card_ids)
        rnd.next_meld_id += 1
        rnd.melds[meld.id] = meld
        self._played(pid)
        return meld

    def lay_off(self, pid: str, meld_id: int, card_ids: list[int]) -> Meld:
        """Add cards from the hand to any meld on the table."""
        rnd = self._check_turn(pid, "play")
        meld = rnd.melds.get(meld_id)
        if meld is None:
            raise GameError("bad_pile")
        cards = self._from_hand(pid, card_ids)
        arranged = arrange([*meld.cards, *cards])
        if arranged is None:
            raise GameError("invalid_pile")
        grown = Meld(meld.id, arranged.cards, {})
        others = [m for m in rnd.melds.values() if m.id != meld_id]
        self._check_can_finish(pid, card_ids, [*others, grown])
        self._remove_from_hand(pid, card_ids)
        meld.cards = arranged.cards
        meld.owners.update(dict.fromkeys(card_ids, pid))
        self._played(pid)
        return meld

    def discard(self, pid: str, card_id: int) -> None:
        """Discard a card, ending the turn; the last card ends the round."""
        rnd = self._check_turn(pid, "play")
        [card] = self._from_hand(pid, [card_id])
        if card_id == rnd.picked:
            raise GameError("just_picked")
        if rnd.must_play is not None:
            raise GameError("must_play")
        self._remove_from_hand(pid, [card_id])
        rnd.discard.append(card)
        rnd.picked = None
        if not rnd.hands[pid]:
            self._end_round(gin=pid)
        else:
            rnd.turn = rnd.order[(rnd.order.index(pid) + 1) % len(rnd.order)]
            rnd.step = "draw"
        self._changed()

    def next_round(self) -> None:
        if self.status != "round_over":
            raise GameError("round_not_over")
        order = self.players
        dealer = order[(order.index(self.round.dealer) + 1) % len(order)]
        self.round = Round.deal(order, dealer, self.rng)
        self.status = "playing"
        self._changed()

    # -- helpers -----------------------------------------------------------

    def _check_turn(self, pid: str, step: str) -> Round:
        if self.status == "finished":
            raise GameError("game_over")
        if self.status != "playing":
            raise GameError("round_over")
        if pid not in self.scores:
            raise GameError("unknown_player")
        rnd = self.round
        if rnd.turn != pid:
            raise GameError("not_your_turn")
        if rnd.step != step:
            raise GameError("draw_first" if step == "play" else "already_drew")
        return rnd

    def _take_plan(self, pid: str, card_id: int) -> int:
        """Where the card is in the discard pile, if the player may take it."""
        rnd = self.round
        depth = next((i for i, c in enumerate(rnd.discard) if c.id == card_id), None)
        if depth is None:
            raise GameError("bad_card")
        if depth < len(rnd.discard) - 1:
            # A deeper card has to go on the table this turn: only if it can.
            hand = rnd.hands[pid] + rnd.discard[depth:]
            if not can_finish_turn(hand, rnd.melds.values(), card_id, card_id):
                raise GameError("cant_play_card")
        return depth

    def _from_hand(self, pid: str, card_ids: list[int]) -> list[Card]:
        by_id = {c.id: c for c in self.round.hands[pid]}
        if not card_ids or len(set(card_ids)) != len(card_ids) or not set(card_ids) <= by_id.keys():
            raise GameError("bad_card")
        return [by_id[i] for i in card_ids]

    def _remove_from_hand(self, pid: str, card_ids: list[int]) -> None:
        gone = set(card_ids)
        self.round.hands[pid] = [c for c in self.round.hands[pid] if c.id not in gone]

    def _check_can_finish(self, pid: str, card_ids: list[int], melds: list[Meld]) -> None:
        """After putting these cards down (``melds`` is the table then), the
        turn must still be able to end: a card left to discard, and a deeper
        card picked from the discard pile still playable."""
        rnd = self.round
        gone = set(card_ids)
        rest = [c for c in rnd.hands[pid] if c.id not in gone]
        must = rnd.must_play if rnd.must_play not in gone else None
        if not can_finish_turn(rest, melds, must, rnd.picked):
            raise GameError("must_play" if must is not None else "keep_one")

    def _played(self, pid: str) -> None:
        rnd = self.round
        rnd.played_since_refill = True
        held = {c.id for c in rnd.hands[pid]}
        if rnd.must_play is not None and rnd.must_play not in held:
            rnd.must_play = None
        self._changed()

    def _end_round(self, gin: str | None) -> None:
        rnd = self.round
        table = dict.fromkeys(self.players, 0)
        for meld in rnd.melds.values():
            for card_id, value in meld.card_points().items():
                table[meld.owners[card_id]] += value
        hand = {pid: hand_points(rnd.hands[pid]) for pid in self.players}
        result = RoundResult(gin, table, hand)
        rnd.result = result
        self.history.append(result)
        for pid, score in result.scores.items():
            self.scores[pid] += score
        best = max(self.scores.values())
        leaders = [pid for pid in self.players if self.scores[pid] == best]
        if best >= self.target and len(leaders) == 1:
            self.status, self.winner = "finished", leaders[0]
        else:
            self.status = "round_over"

    def _changed(self) -> None:
        self.version += 1


def can_finish_turn(
    hand: list[Card], melds: Iterable[Meld], must_play: int | None, picked: int | None
) -> bool:
    """Whether a turn with this hand can still end with a discard.

    ``must_play`` has to go on the table first, with or without other cards
    from the hand, and a card other than ``picked`` must be left to discard.
    It is enough to look at the smallest plays: any valid meld holding the
    card contains a 3-card meld holding it, and adding it to a meld on the
    table needs at most one other card (more would make a meld of their own).
    """
    by_id = {c.id: c for c in hand}
    if must_play is None:
        return any(c.id != picked for c in hand)
    card = by_id.get(must_play)
    if card is None:
        return False
    others = [c for c in hand if c.id != must_play]

    def leaves_discard(used: set[int]) -> bool:
        return any(c.id not in used and c.id != picked for c in others)

    for meld in melds:
        if arrange([*meld.cards, card]) is not None and leaves_discard(set()):
            return True
        for extra in others:
            if arrange([*meld.cards, card, extra]) is not None and leaves_discard({extra.id}):
                return True
    for a, b in combinations(others, 2):
        if arrange([card, a, b]) is not None and leaves_discard({a.id, b.id}):
            return True
    return False
