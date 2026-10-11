"""Starting a game, drawing, opening and committing a move."""

import re

import pytest
from playwright.sync_api import expect

from helpers import create_room, draw, draw_until, extends, find_run, hand, join_by_link, table, tap_card


def test_start_and_draw(desktop, phone):
    host = desktop.new_page()
    create_room(host, "Viktor")
    link = host.get_by_test_id("invite-link").inner_text()
    guest = phone.new_page()
    join_by_link(guest, link, "Hana")

    host.get_by_test_id("start").click()
    for page in (host, guest):
        expect(page.get_by_test_id("table")).to_be_visible()
        expect(page.locator(".hand [data-card]")).to_have_count(5)

    deck = int(guest.get_by_test_id("deck-count").inner_text())
    draw(guest)
    expect(guest.get_by_test_id("deck-count")).to_have_text(str(deck - 1))
    expect(host.get_by_test_id("deck-count")).to_have_text(str(deck - 1))
    # The host sees the guest's card count go up.
    hana = host.get_by_test_id("player").filter(has_text="Hana")
    expect(hana.get_by_test_id("card-count")).to_have_text("6")


@pytest.mark.parametrize("kind", ["phone", "desktop"])
def test_open_and_add_to_pile(make_context, screenshot, kind):
    page = make_context(kind).new_page()
    create_room(page, "Viktor")
    page.get_by_test_id("add-cpu").click()
    page.get_by_test_id("start").click()
    expect(page.locator(".hand [data-card]")).to_have_count(5)

    # Open with a run of three.
    run = draw_until(page, find_run)
    expect(page.get_by_test_id("open")).to_be_disabled()
    for card in run:
        tap_card(page, card)
    page.get_by_test_id("open").click()
    expect(page.locator("[data-testid=table] [data-pile]")).to_have_count(1)
    assert sorted(table(page)[0]) == sorted(run)
    expect(page.get_by_test_id("open")).to_have_count(0)

    # Add a card to the run: select it, tap the pile, commit.
    pile = table(page)[0]
    card = draw_until(page, lambda h: next((c for c in h if extends(c, pile)), None))
    size = len(hand(page))
    tap_card(page, card)
    page.locator("[data-testid=table] [data-pile]").first.click()
    sheet = page.get_by_test_id("staging")
    expect(sheet).to_be_visible()
    expect(sheet.get_by_test_id("draft-pile")).to_have_count(1)
    expect(sheet.locator("[role=timer]")).to_be_visible()
    expect(sheet.get_by_test_id("commit")).to_be_enabled()
    screenshot(page, f"game-staging-{kind}")
    sheet.get_by_test_id("commit").click()

    expect(sheet).to_have_count(0)
    expect(page.locator(".hand [data-card]")).to_have_count(size - 1)
    assert sorted(table(page)[0]) == sorted(pile + [card])
    screenshot(page, f"game-{kind}")


def test_invalid_pile_blocks_commit_and_cancel_returns_cards(desktop):
    page = desktop.new_page()
    create_room(page, "Viktor")
    page.get_by_test_id("add-cpu").click()
    page.get_by_test_id("start").click()
    run = draw_until(page, find_run)
    for card in run:
        tap_card(page, card)
    page.get_by_test_id("open").click()
    expect(page.locator("[data-testid=table] [data-pile]")).to_have_count(1)

    # Take the pile without adding anything, then put a random card on it.
    pile = table(page)[0]
    other = next(c for c in hand(page) if not extends(c, pile))
    tap_card(page, other)
    page.locator("[data-testid=table] [data-pile]").first.click()
    sheet = page.get_by_test_id("staging")
    expect(sheet.get_by_test_id("draft-pile")).to_have_class(re.compile(r"\binvalid\b"))
    expect(sheet.get_by_test_id("commit")).to_be_disabled()
    size = len(hand(page))

    sheet.get_by_role("button", name="Cancel").click()
    expect(sheet).to_have_count(0)
    expect(page.locator(".hand [data-card]")).to_have_count(size + 1)
    assert sorted(table(page)[0]) == sorted(pile)
