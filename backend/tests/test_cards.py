import random

from wildjoker.engine import Card, Suit, card_from_code, cards_from_codes
from wildjoker.engine.cards import full_deck, shuffled_deck


def test_card_ids_decode():
    assert Card(0).code == "AS"
    assert Card(13).code == "AH" and Card(13).suit == Suit.HEARTS
    assert Card(51).code == "KC" and Card(51).rank == 13
    assert Card(52).is_joker and Card(53).code == "JK"
    assert Card(54).code == "AS" and Card(54).deck == 1


def test_codes_round_trip():
    for card in full_deck(3):
        if not card.is_joker:
            assert card_from_code(card.code, deck=card.deck) == card


def test_repeated_codes_use_next_deck():
    a, b, j1, j2, j3 = cards_from_codes("5H 5H JK JK JK")
    assert a != b and a.code == b.code == "5H"
    assert len({j1, j2, j3}) == 3


def test_deck_sizes():
    for decks in (1, 2, 3):
        cards = shuffled_deck(decks, random.Random(1))
        assert len(cards) == len(set(cards)) == 54 * decks
        assert sum(c.is_joker for c in cards) == 2 * decks
