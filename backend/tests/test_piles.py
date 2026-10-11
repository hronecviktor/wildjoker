import json
from pathlib import Path

import pytest

from wildjoker.engine import arrange, cards_from_codes, is_valid_opening

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
