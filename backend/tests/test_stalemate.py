from wildjoker.solver import can_shed, is_stalemate

from .conftest import make_game


def test_not_stalemate_while_deck_has_cards():
    game = make_game({"a": "9C", "b": "3S"}, deck="8D", opened="ab")
    assert not is_stalemate(game)


def test_stalemate_when_nobody_can_play():
    game = make_game({"a": "9C", "b": "3S"}, table=["5H 6H 7H"], opened="ab")
    assert is_stalemate(game)


def test_unopened_player_with_a_run_can_still_play():
    game = make_game({"a": "9C", "b": "3S 4S 5S 2D"}, opened="a")
    assert can_shed(game, "b")
    assert not is_stalemate(game)


def test_unopened_player_cannot_use_the_table():
    game = make_game({"a": "9C", "b": "8H"}, table=["5H 6H 7H"], opened="a")
    assert not can_shed(game, "b")


def test_shedding_by_rearranging_the_table():
    # 7D only fits by taking 7S and 7H off the ends of two runs to make a set.
    game = make_game({"a": "7D", "b": "2D"}, table=["4S 5S 6S 7S", "7H 8H 9H TH"], opened="ab")
    assert can_shed(game, "a")
    assert not can_shed(game, "b")
