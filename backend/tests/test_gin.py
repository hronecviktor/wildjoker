import random

import pytest

from wildjoker.engine import GameError, cards_from_codes
from wildjoker.engine.gin import GinGame, Meld, Round, can_finish_turn, hand_points, points

from .conftest import codes


def make_gin(
    hands: dict[str, str],
    discard: str = "",
    stock: str = "",
    melds: list[tuple[str, str]] = (),
    turn: str | None = None,
    step: str = "draw",
    scores: dict[str, int] | None = None,
) -> GinGame:
    """A game in its first round with fixed cards (top of stock and discard last).

    ``melds`` lists (owner, codes) for melds already on the table.
    """
    groups = [*hands.values(), discard, stock, *(c for _, c in melds)]
    cards = iter(cards_from_codes(" ".join(groups).split()))
    take = lambda text: [next(cards) for _ in text.split()]  # noqa: E731
    order = list(hands)
    rnd = Round(
        order=order,
        dealer=order[-1],
        hands={pid: take(text) for pid, text in hands.items()},
        discard=take(discard),
        stock=take(stock),
        turn=turn or order[0],
        step=step,
    )
    for owner, text in melds:
        meld_cards = take(text)
        rnd.melds[rnd.next_meld_id] = Meld(
            rnd.next_meld_id, tuple(meld_cards), {c.id: owner for c in meld_cards}
        )
        rnd.next_meld_id += 1
    return GinGame(order, scores or dict.fromkeys(order, 0), rnd, rng=random.Random(1))


def ids(game: GinGame, pid: str, text: str) -> list[int]:
    """Ids of cards in a player's hand by code."""
    hand = list(game.hand(pid))
    out = []
    for code in text.split():
        card = next(c for c in hand if c.code == code)
        hand.remove(card)
        out.append(card.id)
    return out


def discard_id(game: GinGame, code: str) -> int:
    return next(c.id for c in game.round.discard if c.code == code)


def hand(game: GinGame, pid: str) -> str:
    return " ".join(sorted(c.code for c in game.hand(pid)))


def table(game: GinGame) -> list[str]:
    return [codes(m.cards) for m in game.round.melds.values()]


# -- values ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "low", "value"),
    [
        ("JK", False, 25),
        ("AS", False, 15),
        ("AS", True, 5),
        ("KH", False, 10),
        ("TD", False, 10),
        ("9C", False, 5),
        ("2S", False, 5),
    ],
)
def test_points(code, low, value):
    [card] = cards_from_codes(code)
    assert points(card, low) == value


def test_ace_is_low_only_at_the_bottom_of_a_run():
    def meld_points(text):
        cards = cards_from_codes(text)
        return sum(Meld(1, tuple(cards), {}).card_points().values())

    assert meld_points("AS 2S 3S") == 15
    assert meld_points("QS KS AS") == 35
    assert meld_points("AS AH AD") == 45
    assert meld_points("JK 2S 3S") == 35  # the joker is the ace here, but still 25
    assert hand_points(cards_from_codes("AS 2S JK")) == 45


# -- dealing -----------------------------------------------------------------


def test_new_game_deals_seven_each_and_turns_up_a_card():
    game = GinGame.new(["a", "b", "c"], seed=3)
    rnd = game.round
    assert all(len(h) == 7 for h in rnd.hands.values())
    assert len(rnd.discard) == 1
    assert len(rnd.stock) == 54 - 21 - 1
    assert rnd.dealer == "c" and rnd.turn == "a" and rnd.step == "draw"
    every = [c.id for h in rnd.hands.values() for c in h] + [c.id for c in rnd.stock + rnd.discard]
    assert sorted(every) == list(range(54))


@pytest.mark.parametrize("n", [1, 7])
def test_player_count_limits(n):
    with pytest.raises(GameError) as e:
        GinGame.new([str(i) for i in range(n)])
    assert e.value.code == "bad_config"


# -- turns -------------------------------------------------------------------


def test_draw_from_the_stock_then_discard_passes_the_turn():
    game = make_gin({"a": "2S 5H 9C", "b": "3D 4D 8C"}, discard="KD", stock="7S 6S")
    assert game.draw("a").code == "6S"
    with pytest.raises(GameError, match="already_drew"):
        game.draw("a")
    game.discard("a", ids(game, "a", "9C")[0])
    assert hand(game, "a") == "2S 5H 6S"
    assert codes(game.round.discard) == "KD 9C"
    assert game.round.turn == "b" and game.round.step == "draw"


def test_only_the_player_whose_turn_it_is_can_act():
    game = make_gin({"a": "2S 5H 9C", "b": "3D 4D 8C"}, discard="KD", stock="7S")
    with pytest.raises(GameError, match="not_your_turn"):
        game.draw("b")
    with pytest.raises(GameError, match="draw_first"):
        game.discard("a", ids(game, "a", "9C")[0])


def test_the_turn_goes_round_the_table():
    game = make_gin({"a": "2S 5H", "b": "3D 4D", "c": "8C 9C"}, discard="KD", stock="7S 6S 5S")
    for pid in "abc":
        assert game.round.turn == pid
        game.draw(pid)
        game.discard(pid, game.hand(pid)[0].id)
    assert game.round.turn == "a"


def test_the_top_discard_cant_be_thrown_straight_back():
    game = make_gin({"a": "2S 5H 9C", "b": "3D"}, discard="4C KD")
    taken = game.take("a", discard_id(game, "KD"))
    assert codes(taken) == "KD"
    with pytest.raises(GameError, match="just_picked"):
        game.discard("a", ids(game, "a", "KD")[0])
    game.discard("a", ids(game, "a", "9C")[0])
    assert codes(game.round.discard) == "4C 9C"


def test_a_deeper_discard_comes_with_the_cards_above_and_must_be_played():
    game = make_gin({"a": "5H 6H 2C", "b": "3D"}, discard="7H KD 9S")
    taken = game.take("a", discard_id(game, "7H"))
    assert codes(taken) == "7H KD 9S"
    assert game.round.discard == []
    with pytest.raises(GameError, match="must_play"):
        game.discard("a", ids(game, "a", "2C")[0])
    game.meld("a", ids(game, "a", "5H 6H 7H"))
    game.discard("a", ids(game, "a", "KD")[0])
    assert hand(game, "a") == "2C 9S"


def test_a_deeper_discard_that_cant_be_played_cant_be_taken():
    game = make_gin({"a": "5H 2C", "b": "3D"}, discard="7H KD 9S")
    assert not game.can_take("a", discard_id(game, "7H"))
    with pytest.raises(GameError, match="cant_play_card"):
        game.take("a", discard_id(game, "7H"))
    assert game.can_take("a", discard_id(game, "9S"))  # the top card is always free


def test_a_deeper_discard_can_be_added_to_a_meld_on_the_table():
    game = make_gin({"a": "2C 3C", "b": "3D"}, discard="9H KD", melds=[("b", "6H 7H 8H")])
    game.take("a", discard_id(game, "9H"))
    game.lay_off("a", 1, ids(game, "a", "9H"))
    assert table(game) == ["6H 7H 8H 9H"]
    assert game.round.must_play is None


def test_a_deeper_discard_can_need_a_card_from_the_hand_to_reach_a_meld():
    game = make_gin({"a": "8H 2C", "b": "3D"}, discard="9H KD", melds=[("b", "5H 6H 7H")])
    assert game.can_take("a", discard_id(game, "9H"))


def test_plays_that_strand_the_picked_card_are_refused():
    # 7H can go with 5H 6H, but putting 5H in a set of fives would strand it.
    game = make_gin({"a": "5H 6H 5S 5D 2C", "b": "3D"}, discard="7H KD")
    game.take("a", discard_id(game, "7H"))
    with pytest.raises(GameError, match="must_play"):
        game.meld("a", ids(game, "a", "5H 5S 5D"))
    game.meld("a", ids(game, "a", "5H 6H 7H"))
    assert game.round.must_play is None


def test_a_card_must_be_left_to_discard():
    game = make_gin({"a": "5H 6H 7H", "b": "3D"}, discard="KD", stock="8H")
    game.draw("a")
    with pytest.raises(GameError, match="keep_one"):
        game.meld("a", ids(game, "a", "5H 6H 7H 8H"))
    game.meld("a", ids(game, "a", "5H 6H 7H"))
    assert hand(game, "a") == "8H"


def test_the_picked_card_doesnt_count_as_one_left_to_discard():
    game = make_gin({"a": "5H 6H 7H", "b": "3D"}, discard="KD")
    game.take("a", discard_id(game, "KD"))
    with pytest.raises(GameError, match="keep_one"):
        game.meld("a", ids(game, "a", "5H 6H 7H"))


def test_melds_and_lay_offs_remember_who_played_each_card():
    game = make_gin({"a": "4S 5S 6S 9D 2H", "b": "7S 9C"}, discard="2C", stock="TC KC", step="play")
    game.meld("a", ids(game, "a", "5S 4S 6S"))
    game.discard("a", ids(game, "a", "9D")[0])
    game.draw("b")
    game.lay_off("b", 1, ids(game, "b", "7S"))
    meld = game.round.melds[1]
    assert codes(meld.cards) == "4S 5S 6S 7S"
    owner = {c.code: meld.owners[c.id] for c in meld.cards}
    assert owner == {"4S": "a", "5S": "a", "6S": "a", "7S": "b"}


def test_invalid_melds_and_lay_offs_are_refused():
    game = make_gin(
        {"a": "4S 5S 7S 9D KD", "b": "3D"},
        discard="2C",
        melds=[("b", "8H 8C 8D")],
        step="play",
    )
    with pytest.raises(GameError, match="invalid_pile"):
        game.meld("a", ids(game, "a", "4S 5S 7S"))
    with pytest.raises(GameError, match="invalid_pile"):
        game.lay_off("a", 1, ids(game, "a", "9D"))
    with pytest.raises(GameError, match="bad_pile"):
        game.lay_off("a", 9, ids(game, "a", "9D"))


def test_jokers_are_wild_and_stay_on_the_table():
    game = make_gin(
        {"a": "JK 5H KC 2C", "b": "6H"}, discard="2D", melds=[("b", "8C 8D 8S")], step="play"
    )
    game.lay_off("a", 1, ids(game, "a", "JK"))
    assert table(game) == ["8S 8D 8C JK"]
    with pytest.raises(GameError, match="invalid_pile"):
        game.lay_off("a", 1, ids(game, "a", "KC"))  # a set holds 4 at most


def test_an_empty_stock_is_made_from_the_discard_pile():
    game = make_gin({"a": "2S 9C", "b": "3D"}, discard="4C 5C 6C KD")
    card = game.draw("a")
    assert card.code in {"4C", "5C", "6C"}
    assert codes(game.round.discard) == "KD"
    assert len(game.round.stock) == 2


def test_with_nothing_to_draw_the_top_discard_is_still_there():
    game = make_gin({"a": "2S 9C", "b": "3D"}, discard="KD")
    with pytest.raises(GameError, match="deck_empty"):
        game.draw("a")
    game.take("a", discard_id(game, "KD"))


# -- scoring -----------------------------------------------------------------


def test_going_out_scores_the_round():
    game = make_gin(
        {"a": "4S 5S 6S 9D", "b": "AH JK 2C"},
        discard="2D",
        stock="TC",
        melds=[("b", "8C 8D 8S"), ("a", "QH KH AH")],
        step="play",
    )
    game.meld("a", ids(game, "a", "4S 5S 6S"))
    game.discard("a", ids(game, "a", "9D")[0])
    assert game.status == "round_over"
    result = game.round.result
    assert result.gin == "a"
    assert result.table == {"a": 15 + 35, "b": 15}
    assert result.hand == {"a": 0, "b": 15 + 25 + 5}
    assert game.scores == {"a": 50, "b": -30}


def test_scores_add_up_and_the_dealer_moves_on():
    game = make_gin(
        {"a": "4S 5S 6S 9D", "b": "2C 3D"},
        discard="2D",
        stock="TC",
        step="play",
        scores={"a": 100, "b": 40},
    )
    game.meld("a", ids(game, "a", "4S 5S 6S"))
    game.discard("a", ids(game, "a", "9D")[0])
    assert game.scores == {"a": 115, "b": 30}
    with pytest.raises(GameError, match="round_over"):
        game.draw("b")
    game.next_round()
    assert game.status == "playing"
    assert game.round.dealer == "a" and game.round.turn == "b"
    assert all(len(h) == 7 for h in game.round.hands.values())
    assert len(game.history) == 1


def test_reaching_the_target_wins():
    game = make_gin(
        {"a": "4S 5S 6S 9D", "b": "2C"},
        discard="2D",
        stock="TC",
        step="play",
        scores={"a": 490, "b": 480},
    )
    game.meld("a", ids(game, "a", "4S 5S 6S"))
    game.discard("a", ids(game, "a", "9D")[0])
    assert game.status == "finished" and game.winner == "a"
    assert game.places() == [["a"], ["b"]]
    assert game.active == []
    with pytest.raises(GameError, match="round_not_over"):
        game.next_round()


def test_a_shared_top_score_plays_another_round():
    game = make_gin(
        {"a": "4S 5S 6S 9D", "b": "2C"},
        discard="2D",
        stock="TC",
        step="play",
        scores={"a": 495, "b": 515},
    )
    game.meld("a", ids(game, "a", "4S 5S 6S"))
    game.discard("a", ids(game, "a", "9D")[0])
    assert game.scores == {"a": 510, "b": 510}
    assert game.status == "round_over"
    assert game.places() == [["a", "b"]]


def test_the_highest_score_wins_even_if_the_player_going_out_passes_500_too():
    game = make_gin(
        {"a": "4S 5S 6S 9D", "b": "2C"},
        discard="2D",
        stock="TC",
        step="play",
        scores={"a": 490, "b": 600},
    )
    game.meld("a", ids(game, "a", "4S 5S 6S"))
    game.discard("a", ids(game, "a", "9D")[0])
    assert game.status == "finished" and game.winner == "b"


# -- can_finish_turn -----------------------------------------------------------


def test_can_finish_turn():
    h = cards_from_codes("5H 6H 7H 2C")
    assert can_finish_turn(h, [], None, None)
    assert can_finish_turn(h, [], h[2].id, None)  # 5H 6H 7H, keep 2C
    assert not can_finish_turn(h[:3], [], h[2].id, None)  # nothing left after the run
    assert not can_finish_turn(h[:1], [], None, h[0].id)


def test_whole_random_games_finish():
    for seed in range(20):
        rng = random.Random(seed)
        game = GinGame.new(["a", "b", "c"], seed=seed, target=150)
        for _ in range(5000):
            if game.status == "finished":
                break
            if game.status == "round_over":
                game.next_round()
                continue
            pid = game.round.turn
            if rng.random() < 0.3 and game.can_take(pid, game.round.discard[-1].id):
                game.take(pid, game.round.discard[-1].id)
            else:
                try:
                    game.draw(pid)
                except GameError:
                    game.take(pid, game.round.discard[-1].id)
                if game.status != "playing":
                    continue  # the stock ran out again
            _play_greedily(game, pid)
            options = [c for c in game.hand(pid) if c.id != game.round.picked]
            game.discard(pid, rng.choice(options).id)
        assert game.status == "finished", seed
        assert game.winner == max(game.scores, key=game.scores.get)


def _play_greedily(game: GinGame, pid: str) -> None:
    """Put down any 3-card meld and lay off single cards while allowed."""
    from itertools import combinations

    progress = True
    while progress:
        progress = False
        hand_cards = game.hand(pid)
        for trio in combinations(hand_cards, 3):
            try:
                game.meld(pid, [c.id for c in trio])
            except GameError:
                continue
            progress = True
            break
        if progress:
            continue
        for card in game.hand(pid):
            for meld_id in list(game.round.melds):
                try:
                    game.lay_off(pid, meld_id, [card.id])
                except GameError:
                    continue
                progress = True
                break
            if progress:
                break


def test_a_round_nobody_can_finish_ends_when_the_stock_runs_out_again():
    game = make_gin({"a": "2S 9C", "b": "3D 7H"}, discard="4C 5C KD", melds=[("b", "8S 8H 8D")])
    game.draw("a")  # the first refill
    assert game.round.refills == 1
    game.discard("a", ids(game, "a", "2S")[0])
    game.draw("b")
    game.discard("b", ids(game, "b", "3D")[0])
    assert game.draw("a") is None
    assert game.status == "round_over"
    assert game.round.result.gin is None
    assert game.scores["b"] == 15 - 5 - 5


def test_playing_a_card_allows_another_refill():
    game = make_gin({"a": "2S 9C 8C", "b": "3D 7H"}, discard="4C 5C KD", melds=[("b", "8S 8H 8D")])
    game.draw("a")
    game.lay_off("a", 1, ids(game, "a", "8C"))
    game.discard("a", ids(game, "a", "2S")[0])
    game.draw("b")
    game.discard("b", ids(game, "b", "3D")[0])
    assert game.draw("a") is not None
    assert game.round.refills == 2
