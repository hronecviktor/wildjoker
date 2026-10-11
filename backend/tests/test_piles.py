import json
from pathlib import Path

import pytest

from wildjoker.engine import arrange, cards_from_codes, find_opening, is_valid_opening

from .conftest import codes

CASES = json.loads((Path(__file__).parents[2] / "shared" / "piles.json").read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_shared_pile_case(case):
    cards = cards_from_codes(case["cards"])
    result = arrange(cards)
    if not case["valid"]:
        assert result is None
        assert not is_valid_opening(cards)
        return
    assert result is not None
    assert result.kind == case["kind"]
    assert codes(result.cards) == case["order"]
    assert is_valid_opening(cards) == case["opening"]


def test_arrangement_keeps_the_same_cards():
    cards = cards_from_codes("KS JK JK")
    assert sorted(arrange(cards).cards, key=lambda c: c.id) == sorted(cards, key=lambda c: c.id)


def test_run_values_show_what_jokers_stand_for():
    result = arrange(cards_from_codes("KH AH JK"))
    assert result.values == (12, 13, 14)


@pytest.mark.parametrize(
    "hand,opening",
    [
        ("2H 3H 9C", None),
        ("2H 3H 4H 9C", "2H 3H 4H"),
        ("QD KD AD 2D", "QD KD AD"),
        ("AD 2D 3D 4D QD KD", "AD 2D 3D 4D"),
        ("2H JK 4H", None),
        ("2H 3H 4H 6S 7S 8S 9S", "6S 7S 8S 9S"),
        ("AC 2C 3C 4C 5C 6C 7C 8C 9C TC JC QC KC", "AC 2C 3C 4C 5C 6C 7C 8C 9C TC JC QC KC"),
    ],
)
def test_find_opening(hand, opening):
    found = find_opening(cards_from_codes(hand))
    assert (codes(found) if found else None) == opening
