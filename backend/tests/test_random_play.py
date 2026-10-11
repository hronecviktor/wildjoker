"""Random actions against the engine, checking invariants after each one."""

import random
from collections import Counter

import pytest

from wildjoker.engine import Config, Game, GameError, is_valid_pile


def all_cards(game: Game) -> Counter:
    cards = Counter(game.deck)
    for player in game.players.values():
        cards.update(player.hand)
    for pile in game.table.values():
        cards.update(pile.cards)
    return cards


def find_opening(hand) -> list[int] | None:
    by_suit = {}
    for card in hand:
        if not card.is_joker:
            by_suit.setdefault(card.suit, {})[card.rank] = card
    for ranks in by_suit.values():
        for low in range(1, 12):
            if {low, low + 1, low + 2} <= ranks.keys():
                return [ranks[r].id for r in (low, low + 1, low + 2)]
    return None


def random_commit(game: Game, pid: str, rng: random.Random) -> list[list[int]]:
    """A plausible edit of the staged piles, valid often but not always."""
    staged = game.staging.get(pid)
    piles = [[c.id for c in game.table[i].cards] for i in (staged.pile_ids if staged else [])]
    hand = [c.id for c in game.players[pid].hand]
    edit = rng.random()
    if piles and edit < 0.4:
        rng.choice(piles).append(rng.choice(hand))  # add a hand card
    elif piles and edit < 0.6:
        pile = rng.choice(piles)
        pile.pop(rng.choice([0, -1]))  # take an end card
    elif piles and edit < 0.75 and len(piles) >= 2:
        piles = [piles[0] + piles[1], *piles[2:]]  # merge
    elif edit < 0.85:
        piles.append(rng.sample(hand, min(3, len(hand))))  # new pile from hand
    elif piles:
        pile = rng.choice(piles)
        cut = rng.randint(1, len(pile) - 1)
        piles.remove(pile)
        piles += [pile[:cut], pile[cut:]]  # split
    return piles


def random_action(game: Game, rng: random.Random, now: float) -> None:
    pid = rng.choice(game.active)
    player = game.players[pid]
    action = rng.random()
    if action < 0.25:
        game.draw(pid)
    elif action < 0.4:
        opening = find_opening(player.hand)
        cards = opening or [c.id for c in rng.sample(player.hand, min(3, len(player.hand)))]
        game.open(pid, cards)
    elif action < 0.6:
        free = [p.id for p in game.table.values() if p.locked_by is None]
        game.stage(pid, rng.sample(free, min(len(free), rng.randint(1, 3))), now)
    elif action < 0.9:
        game.commit(pid, random_commit(game, pid, rng), now)
    elif action < 0.95:
        game.cancel(pid)
    else:
        game.expire(now)


@pytest.mark.parametrize("seed", range(30))
def test_random_play_keeps_invariants(seed):
    rng = random.Random(seed)
    game = Game.new(
        ["a", "b", "c"], Config(decks=rng.randint(1, 3), hand_size=rng.randint(3, 6)), seed=seed
    )
    expected = all_cards(game)
    for step in range(2000):
        version = game.version
        try:
            random_action(game, rng, now=step * 0.5)
        except GameError:
            pass
        assert all_cards(game) == expected
        assert all(is_valid_pile(p.cards) for p in game.table.values())
        for pid, staging in game.staging.items():
            assert all(game.table[i].locked_by == pid for i in staging.pile_ids)
        locked = {p.id for p in game.table.values() if p.locked_by}
        assert locked == {i for s in game.staging.values() for i in s.pile_ids}
        assert game.version >= version
        if game.status == "finished":
            assert sorted(p for place in game.places for p in place) == ["a", "b", "c"]
            break
