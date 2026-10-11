import pytest

from wildjoker.engine import Config, Game, GameError

from .conftest import codes, make_game


def ids(game: Game, pid: str, wanted: str) -> list[int]:
    """Ids of cards in a player's hand by code, in the order given."""
    hand = list(game.players[pid].hand)
    result = []
    for code in wanted.split():
        card = next(c for c in hand if c.code == code)
        hand.remove(card)
        result.append(card.id)
    return result


def pile_ids(game: Game, pile_id: int, wanted: str) -> list[int]:
    cards = list(game.table[pile_id].cards)
    result = []
    for code in wanted.split():
        card = next(c for c in cards if c.code == code)
        cards.remove(card)
        result.append(card.id)
    return result


def hand(game: Game, pid: str) -> str:
    return " ".join(sorted(c.code for c in game.players[pid].hand))


# -- setup -------------------------------------------------------------------


def test_new_game_deals_hands():
    game = Game.new(["a", "b", "c"], Config(decks=2, hand_size=5), seed=1)
    assert [len(p.hand) for p in game.players.values()] == [5, 5, 5]
    assert len(game.deck) == 108 - 15
    all_cards = [c for p in game.players.values() for c in p.hand] + game.deck
    assert len(set(all_cards)) == 108


def test_same_seed_same_deal():
    a = Game.new(["a", "b"], seed=7)
    b = Game.new(["a", "b"], seed=7)
    assert a.players["a"].hand == b.players["a"].hand


@pytest.mark.parametrize(
    "players,config",
    [
        (["a"], Config()),
        ([str(i) for i in range(9)], Config()),
        (["a", "b"], Config(decks=4)),
        (["a", "b"], Config(decks=0)),
        ([str(i) for i in range(8)], Config(decks=1, hand_size=7)),
    ],
)
def test_bad_config(players, config):
    with pytest.raises(GameError) as error:
        Game.new(players, config)
    assert error.value.code == "bad_config"


def test_duplicate_player_ids_rejected():
    with pytest.raises(GameError):
        Game.new(["a", "a"])


# -- drawing and opening ----------------------------------------------------


def test_draw_takes_top_card():
    game = make_game({"a": "2S", "b": "3S"}, deck="4S 5S")
    assert game.draw("a").code == "5S"
    assert hand(game, "a") == "2S 5S"
    assert len(game.deck) == 1


def test_draw_from_empty_deck():
    game = make_game({"a": "2S", "b": "3S"})
    with pytest.raises(GameError, match="deck_empty"):
        game.draw("a")


def test_open_with_run():
    game = make_game({"a": "4H 2H 3H 9C", "b": "3S"})
    pile = game.open("a", ids(game, "a", "4H 2H 3H"))
    assert codes(pile.cards) == "2H 3H 4H"
    assert hand(game, "a") == "9C"
    assert game.players["a"].opened


@pytest.mark.parametrize(
    "cards,error",
    [
        ("2H 3H", "invalid_opening"),
        ("QS QH QD", "invalid_opening"),
        ("2H JK 4H", "invalid_opening"),
    ],
)
def test_invalid_openings(cards, error):
    game = make_game({"a": cards + " 9C", "b": "3S"})
    with pytest.raises(GameError, match=error):
        game.open("a", ids(game, "a", cards))
    assert not game.table and not game.players["a"].opened


def test_open_only_once():
    game = make_game({"a": "2H 3H 4H 5S 6S 7S 9C", "b": "3S"})
    game.open("a", ids(game, "a", "2H 3H 4H"))
    with pytest.raises(GameError, match="already_opened"):
        game.open("a", ids(game, "a", "5S 6S 7S"))


def test_open_with_cards_not_in_hand():
    game = make_game({"a": "2H 3H 9C", "b": "4H"})
    with pytest.raises(GameError, match="bad_card"):
        game.open("a", ids(game, "a", "2H 3H") + ids(game, "b", "4H"))


def test_cannot_stage_or_commit_before_opening():
    game = make_game({"a": "5H 6H 7H", "b": "3S"}, table=["2C 3C 4C"])
    with pytest.raises(GameError, match="not_opened"):
        game.stage("a", [1], now=0)
    with pytest.raises(GameError, match="not_opened"):
        game.commit("a", [ids(game, "a", "5H 6H 7H")], now=0)


# -- staging -----------------------------------------------------------------


def test_add_card_to_pile():
    game = make_game({"a": "5C 9H", "b": "3S"}, table=["2C 3C 4C"], opened="a")
    game.stage("a", [1], now=0)
    [pile] = game.commit("a", [pile_ids(game, 1, "2C 3C 4C") + ids(game, "a", "5C")], now=1)
    assert codes(pile.cards) == "2C 3C 4C 5C"
    assert hand(game, "a") == "9H"
    assert 1 not in game.table and pile.locked_by is None


def test_new_pile_from_hand_without_staging():
    game = make_game({"a": "QS QH QD 2C", "b": "3S"}, opened="a")
    [pile] = game.commit("a", [ids(game, "a", "QS QH QD")], now=0)
    assert pile.cards and hand(game, "a") == "2C"


def test_take_card_from_pile_into_hand():
    game = make_game({"a": "9H", "b": "3S"}, table=["2C 3C 4C 5C"], opened="a")
    game.stage("a", [1], now=0)
    game.commit("a", [pile_ids(game, 1, "2C 3C 4C")], now=1)
    assert hand(game, "a") == "5C 9H"


def test_swap_joker_for_real_card():
    game = make_game({"a": "5H", "b": "3S"}, table=["4H JK 6H"], opened="a")
    game.stage("a", [1], now=0)
    [pile] = game.commit("a", [pile_ids(game, 1, "4H 6H") + ids(game, "a", "5H")], now=1)
    assert codes(pile.cards) == "4H 5H 6H"
    assert hand(game, "a") == "JK"


def test_split_pile_inserting_card():
    game = make_game({"a": "5H 9C", "b": "3S"}, table=["AH 2H 3H 4H 5H 6H 7H 8H 9H TH"], opened="a")
    game.stage("a", [1], now=0)
    low = pile_ids(game, 1, "AH 2H 3H 4H") + ids(game, "a", "5H")
    high = pile_ids(game, 1, "5H 6H 7H 8H 9H TH")
    a, b = game.commit("a", [low, high], now=1)
    assert codes(a.cards) == "AH 2H 3H 4H 5H"
    assert codes(b.cards) == "5H 6H 7H 8H 9H TH"
    assert hand(game, "a") == "9C"


def test_split_without_adding():
    game = make_game({"a": "9C", "b": "3S"}, table=["AH 2H 3H 4H 5H 6H"], opened="a")
    game.stage("a", [1], now=0)
    game.commit("a", [pile_ids(game, 1, "AH 2H 3H"), pile_ids(game, 1, "4H 5H 6H")], now=1)
    assert len(game.table) == 2


def test_rearrange_several_piles():
    # Take 7S off one run and 7H off another, add 7D from hand: a new set.
    game = make_game({"a": "7D 2C", "b": "3S"}, table=["4S 5S 6S 7S", "7H 8H 9H TH"], opened="a")
    game.stage("a", [1, 2], now=0)
    result = game.commit(
        "a",
        [
            pile_ids(game, 1, "4S 5S 6S"),
            pile_ids(game, 2, "8H 9H TH"),
            pile_ids(game, 1, "7S") + pile_ids(game, 2, "7H") + ids(game, "a", "7D"),
        ],
        now=1,
    )
    assert [codes(p.cards) for p in result] == ["4S 5S 6S", "8H 9H TH", "7S 7H 7D"]
    assert hand(game, "a") == "2C"


def test_merge_piles():
    game = make_game({"a": "9C", "b": "3S"}, table=["AH 2H 3H", "4H 5H 6H"], opened="a")
    game.stage("a", [1, 2], now=0)
    [pile] = game.commit(
        "a", [pile_ids(game, 1, "AH 2H 3H") + pile_ids(game, 2, "4H 5H 6H")], now=1
    )
    assert len(pile.cards) == 6


def test_take_whole_piles_into_hand():
    game = make_game({"a": "9C", "b": "3S"}, table=["AH 2H 3H"], opened="a")
    game.stage("a", [1], now=0)
    assert game.commit("a", [], now=1) == []
    assert hand(game, "a") == "2H 3H 9C AH"
    assert not game.table


def test_invalid_commit_changes_nothing():
    game = make_game({"a": "9C", "b": "3S"}, table=["2C 3C 4C 5C"], opened="a")
    game.stage("a", [1], now=0)
    version = game.version
    with pytest.raises(GameError, match="invalid_pile"):
        game.commit("a", [pile_ids(game, 1, "2C 3C 4C") + ids(game, "a", "9C")], now=1)
    assert game.version == version
    assert game.table[1].locked_by == "a" and hand(game, "a") == "9C"


def test_commit_cannot_use_unstaged_or_foreign_cards():
    game = make_game({"a": "5C", "b": "6C"}, table=["2C 3C 4C", "9S 9H 9D"], opened="a")
    game.stage("a", [1], now=0)
    with pytest.raises(GameError, match="bad_card"):
        game.commit("a", [pile_ids(game, 1, "2C 3C 4C") + ids(game, "b", "6C")], now=1)
    with pytest.raises(GameError, match="bad_card"):
        game.commit("a", [pile_ids(game, 2, "9S 9H 9D")], now=1)
    card = ids(game, "a", "5C")
    with pytest.raises(GameError, match="bad_card"):
        game.commit("a", [pile_ids(game, 1, "2C 3C 4C") + card + card], now=1)


def test_empty_commit_without_staging():
    game = make_game({"a": "9C", "b": "3S"}, opened="a")
    with pytest.raises(GameError, match="empty_move"):
        game.commit("a", [], now=0)


def test_staged_piles_are_locked_for_others():
    game = make_game({"a": "9C", "b": "3S"}, table=["2C 3C 4C"], opened="ab")
    game.stage("a", [1], now=0)
    with pytest.raises(GameError, match="pile_locked"):
        game.stage("b", [1], now=0)
    with pytest.raises(GameError, match="pile_locked"):
        game.stage("a", [1], now=0)


def test_stage_more_piles_keeps_start_time():
    game = make_game({"a": "9C", "b": "3S"}, table=["2C 3C 4C", "9S 9H 9D"], opened="a")
    game.stage("a", [1], now=0)
    game.stage("a", [2], now=10)
    assert game.staging["a"].pile_ids == [1, 2]
    assert game.expire(now=15.5) == ["a"]


def test_stage_unknown_pile():
    game = make_game({"a": "9C", "b": "3S"}, opened="a")
    with pytest.raises(GameError, match="bad_pile"):
        game.stage("a", [42], now=0)


def test_cancel_returns_piles_unchanged():
    game = make_game({"a": "9C", "b": "3S"}, table=["2C 3C 4C"], opened="a")
    game.stage("a", [1], now=0)
    game.cancel("a")
    assert game.table[1].locked_by is None and "a" not in game.staging
    with pytest.raises(GameError, match="not_staging"):
        game.cancel("a")


def test_staging_times_out():
    game = make_game({"a": "5C", "b": "3S"}, table=["2C 3C 4C"], opened="a")
    game.stage("a", [1], now=100)
    assert game.expire(now=115) == []
    assert game.expire(now=115.1) == ["a"]
    assert game.table[1].locked_by is None


def test_late_commit_is_rejected_and_releases():
    game = make_game({"a": "5C", "b": "3S"}, table=["2C 3C 4C"], opened="a")
    game.stage("a", [1], now=0)
    with pytest.raises(GameError, match="staging_expired"):
        game.commit("a", [pile_ids(game, 1, "2C 3C 4C") + ids(game, "a", "5C")], now=16)
    assert game.table[1].locked_by is None and hand(game, "a") == "5C"


def test_version_bumps_on_every_change():
    game = make_game({"a": "5C", "b": "3S"}, table=["2C 3C 4C"], deck="8D", opened="a")
    v = game.version
    game.draw("a")
    game.stage("a", [1], now=0)
    game.cancel("a")
    assert game.version == v + 3


# -- end of the game ---------------------------------------------------------


def test_going_out_with_two_players_ends_the_game():
    game = make_game({"a": "5C", "b": "3S"}, table=["2C 3C 4C"], opened="a")
    game.stage("a", [1], now=0)
    game.commit("a", [pile_ids(game, 1, "2C 3C 4C") + ids(game, "a", "5C")], now=1)
    assert game.places == [["a"], ["b"]]
    assert game.status == "finished"
    with pytest.raises(GameError, match="game_over"):
        game.draw("b")


def test_opening_can_empty_the_hand():
    game = make_game({"a": "2H 3H 4H", "b": "3S", "c": "4S"})
    game.open("a", ids(game, "a", "2H 3H 4H"))
    assert game.places == [["a"]] and game.status == "playing"
    assert game.active == ["b", "c"]


def test_finished_player_cannot_act_and_others_continue():
    game = make_game(
        {"a": "5C", "b": "QS QH QD 2D", "c": "4S"}, table=["2C 3C 4C"], deck="9D", opened="ab"
    )
    game.stage("a", [1], now=0)
    game.commit("a", [pile_ids(game, 1, "2C 3C 4C") + ids(game, "a", "5C")], now=1)
    with pytest.raises(GameError, match="player_out"):
        game.draw("a")
    game.commit("b", [ids(game, "b", "QS QH QD")], now=2)
    assert game.status == "playing"
    assert game.active == ["b", "c"]


def test_last_two_finish_in_order():
    game = make_game({"a": "5C", "b": "6C", "c": "4S"}, table=["2C 3C 4C"], opened="ab")
    game.stage("a", [1], now=0)
    [pile] = game.commit("a", [pile_ids(game, 1, "2C 3C 4C") + ids(game, "a", "5C")], now=1)
    game.stage("b", [pile.id], now=2)
    game.commit("b", [pile_ids(game, pile.id, "2C 3C 4C 5C") + ids(game, "b", "6C")], now=3)
    assert game.places == [["a"], ["b"], ["c"]]
    assert game.status == "finished"


def test_other_players_staging_released_when_game_ends():
    game = make_game({"a": "5C", "b": "3S"}, table=["2C 3C 4C", "9S 9H 9D"], opened="ab")
    game.stage("b", [2], now=0)
    game.stage("a", [1], now=0)
    game.commit("a", [pile_ids(game, 1, "2C 3C 4C") + ids(game, "a", "5C")], now=1)
    assert not game.staging and game.table[2].locked_by is None


def test_draw_vote_needs_empty_deck():
    game = make_game({"a": "5C", "b": "3S"}, deck="9D")
    with pytest.raises(GameError, match="deck_not_empty"):
        game.vote_draw("a")


def test_draw_by_agreement():
    game = make_game({"a": "5C", "b": "3S", "c": "8H"})
    game.vote_draw("a")
    game.vote_draw("b")
    assert game.status == "playing"
    game.vote_draw("c")
    assert game.status == "finished"
    assert game.places == [["a", "b", "c"]]


def test_draw_votes_reset_when_someone_plays():
    game = make_game({"a": "QS QH QD 5C", "b": "3S"}, opened="a")
    game.vote_draw("b")
    game.commit("a", [ids(game, "a", "QS QH QD")], now=0)
    game.vote_draw("a")
    assert game.status == "playing"


def test_stalemate_shares_the_remaining_places():
    game = make_game({"a": "2H 3H 4H", "b": "3S", "c": "4S"})
    game.open("a", ids(game, "a", "2H 3H 4H"))
    game.end_in_stalemate()
    assert game.places == [["a"], ["b", "c"]]
    assert game.status == "finished"
