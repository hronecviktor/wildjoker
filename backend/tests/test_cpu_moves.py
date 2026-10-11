import random

import pytest

from wildjoker.cpu import EASY, EXPERT, HARD, LEVELS, MEDIUM, find_moves
from wildjoker.cpu.moves import decode, is_split, openings
from wildjoker.engine import Card, Config, Game, cards_from_codes
from wildjoker.engine.cards import full_deck
from wildjoker.solver import solve

from .conftest import codes, make_game


def state(game: Game, pid: str = "a"):
    hand = [c.id for c in game.players[pid].hand]
    piles = [(pile.id, tuple(c.id for c in pile.cards)) for pile in game.table.values()]
    return hand, piles


def moves_for(level, game: Game, joker_weight: float | None = None):
    hand, piles = state(game)
    weight = level.smarts.joker_weight if joker_weight is None else joker_weight
    return find_moves(hand, piles, level.moves, weight).moves


def best(moves):
    return max(moves, key=lambda m: (m.value, -len(m.stage)), default=None)


def apply(game: Game, move, pid: str = "a") -> None:
    """Play a move through the engine, as the room would."""
    before = len(game.players[pid].hand)
    if move.stage:
        game.stage(pid, list(move.stage), now=0.0)
    game.commit(pid, [list(p) for p in move.piles], now=0.0)
    assert len(game.players[pid].hand) == before - move.shed


def table(game: Game) -> list[str]:
    return sorted(codes(pile.cards) for pile in game.table.values())


# -- what each level can find --------------------------------------------------


def test_easy_adds_to_a_pile():
    game = make_game({"a": "8H 9H 2C"}, table=["5H 6H 7H"], opened="a")
    [move] = moves_for(EASY, game)
    assert move.stage == (1,) and move.shed == 2
    apply(game, move)
    assert table(game) == ["5H 6H 7H 8H 9H"]


def test_easy_makes_new_piles_from_the_hand():
    game = make_game({"a": "QS QH QD 4C"}, table=["5H 6H 7H"], opened="a")
    [move] = moves_for(EASY, game)
    assert move.private and move.shed == 3


def test_easy_and_medium_never_split():
    # The 5H only fits by splitting A-10H into A-5H and 5H-10H.
    game = make_game({"a": "5H"}, table=["AH 2H 3H 4H 5H 6H 7H 8H 9H TH"], opened="a")
    assert moves_for(EASY, game) == []
    assert moves_for(MEDIUM, game) == []
    move = best(moves_for(HARD, game))
    assert move.shed == 1
    apply(game, move)
    assert table(game) == ["5H 6H 7H 8H 9H TH", "AH 2H 3H 4H 5H"]


def test_medium_takes_a_card_from_a_pile():
    game = make_game({"a": "6C 7C"}, table=["5S 5H 5D 5C"], opened="a")
    assert moves_for(EASY, game) == []
    move = best(moves_for(MEDIUM, game))
    assert move.shed == 2
    apply(game, move)
    assert table(game) == ["5C 6C 7C", "5S 5H 5D"]


def test_medium_swaps_a_joker():
    game = make_game({"a": "5H 9S 9D"}, table=["4H JK 6H"], opened="a")
    move = best(moves_for(MEDIUM, game))
    assert move.shed == 3
    apply(game, move)
    assert table(game) == ["4H 5H 6H", "9S 9D JK"]


def test_rearranging_two_piles_needs_hard():
    # 7D only fits by taking 7S and 7H off the ends of two runs to make a set.
    game = make_game({"a": "7D 2C"}, table=["4S 5S 6S 7S", "7H 8H 9H TH"], opened="a")
    assert moves_for(EASY, game) == []
    assert moves_for(MEDIUM, game) == []
    for level in (HARD, EXPERT):
        move = best(moves_for(level, game))
        assert move.shed == 1 and len(move.stage) == 2
    apply(game, move)
    assert table(game) == ["4S 5S 6S", "7S 7H 7D", "8H 9H TH"]


def test_hard_is_limited_to_three_piles_expert_is_not():
    # 6D needs a set of 6s taken off the ends of four runs.
    runs = ["3S 4S 5S 6S", "6H 7H 8H 9H", "6C 7C 8C 9C", "3D 4D 5D"]
    game = make_game({"a": "6D 7D 8D KS"}, table=runs, opened="a")
    # 6D 7D 8D alone makes a pile, but 3-8D together sheds the same: fine.
    hard = best(moves_for(HARD, game))
    expert = best(moves_for(EXPERT, game))
    assert hard.shed == expert.shed == 3

    game = make_game({"a": "6D KS"}, table=["3S 4S 5S 6S", "6H 7H 8H 9H", "6C 7C 8C 9C"])
    game.players["a"].opened = True
    hard, expert = best(moves_for(HARD, game)), best(moves_for(EXPERT, game))
    assert hard.shed == expert.shed == 1


def test_untouched_piles_are_not_staged():
    game = make_game({"a": "8H"}, table=["5H 6H 7H", "9S 9D 9C", "2C 3C 4C"], opened="a")
    for level in (MEDIUM, HARD, EXPERT):
        move = best(moves_for(level, game))
        assert move.stage == (1,), level.name


def test_hard_keeps_jokers_back():
    game = make_game({"a": "5H 6H 7H JK 2C 9D"}, opened="a")
    assert best(moves_for(HARD, game)).shed == 3
    assert best(moves_for(MEDIUM, game)).shed == 4
    # ...but uses a joker when it lets real cards out.
    game = make_game({"a": "5H 6H JK 2C 9D"}, opened="a")
    assert best(moves_for(HARD, game)).shed == 3


def test_hard_takes_a_spare_joker():
    game = make_game({"a": "2C 9D KS"}, table=["5H 6H 7H JK"], opened="a")
    move = best(moves_for(HARD, game))
    assert move.shed == -1 and move.value > 0
    assert best(moves_for(MEDIUM, game)) is None


def test_nothing_to_do():
    game = make_game({"a": "2C 9D"}, table=["5H 6H 7H"], opened="a")
    for level in LEVELS.values():
        assert moves_for(level, game) == []


# -- decoding solver output -----------------------------------------------------


def test_decode_ignores_identical_cards_from_another_deck():
    five, six, seven, other_five = cards_from_codes("5H 6H 7H 5H")
    pile = (1, (five.id, six.id, seven.id))
    assert decode([other_five], [pile], [[other_five, six, seven]]) is None


def test_decode_stages_changed_piles_only():
    hand = cards_from_codes("8H 2C")
    a, b = cards_from_codes("5H 6H 7H"), cards_from_codes("9S 9D 9C")
    piles = [(1, tuple(c.id for c in a)), (2, tuple(c.id for c in b))]
    move = decode(hand, piles, [[*a, hand[0]], b])
    assert move.stage == (1,) and move.shed == 1 and move.cards == 1
    assert sorted(move.piles[0]) == sorted(c.id for c in [*a, hand[0]])


def test_decode_counts_cards_taken_into_the_hand():
    hand = cards_from_codes("2C")
    pile = cards_from_codes("5H 6H 7H JK")
    move = decode(hand, [(1, tuple(c.id for c in pile))], [pile[:3]], joker_weight=-0.25)
    assert move.shed == -1 and move.value == pytest.approx(0.25)


def test_is_split():
    game = make_game({"a": "5H"}, table=["AH 2H 3H 4H 5H 6H 7H"], opened="a")
    move = best(moves_for(HARD, game))
    assert is_split(move, state(game)[1])


@pytest.mark.parametrize("seed", range(10))
@pytest.mark.parametrize("level", LEVELS)
def test_moves_are_valid_commits(seed, level):
    """Every move found on a random table goes through the engine as promised."""
    rng = random.Random(seed)
    cards = full_deck(2)
    rng.shuffle(cards)
    game = Game({"a": _player(cards[:8])}, deck=[], config=Config())
    for pile in solve(cards[8:50]).piles:
        game._add_pile(pile)
    for move in moves_for(LEVELS[level], game):
        trial = _copy(game)
        apply(trial, move)


def _player(hand):
    from wildjoker.engine.game import Player

    return Player("a", list(hand), opened=True)


def _copy(game: Game) -> Game:
    import copy

    return copy.deepcopy(game)


# -- opening -----------------------------------------------------------------


def test_openings():
    hand = [c.id for c in cards_from_codes("3S 4S 5S 6S 9H TH JH JK")]
    [longest] = openings(hand, longest=True)
    assert codes(Card(i) for i in longest) == "3S 4S 5S 6S"
    runs = openings(hand, longest=False)
    assert sorted(codes(Card(i) for i in r) for r in runs) == ["3S 4S 5S", "4S 5S 6S", "9H TH JH"]
    assert openings([c.id for c in cards_from_codes("3S 4S JK")], longest=True) == []
