"""Gin: picking the game on the start page, the tutorial, and turns between
two phones."""

import re

from conftest import SCREENSHOTS
from helpers import hand, join_by_link, tap_card
from playwright.sync_api import Page, expect
from test_tutorial import MAX_TAPS, tap_highlight


def create_gin_room(page: Page, name: str) -> str:
    page.goto("/")
    page.get_by_test_id("game-gin").click()
    page.get_by_test_id("name").fill(name)
    page.get_by_test_id("create").click()
    code = page.get_by_test_id("room-code")
    expect(code).to_have_text(re.compile(r"^[A-Z]{4}$"))
    return code.inner_text()


def discard_pile(page: Page) -> list[int]:
    return [
        int(c)
        for c in page.locator("[data-testid=discard] [data-card]").evaluate_all(
            "els => els.map(e => e.dataset.card)"
        )
    ]


def test_the_start_page_switches_between_the_games(phone):
    page = phone.new_page()
    page.goto("/")
    expect(page.get_by_role("heading", level=1)).to_contain_text("Wild Joker")
    page.get_by_test_id("game-gin").click()
    expect(page.get_by_role("heading", level=1)).to_contain_text("Gin")
    expect(page.get_by_test_id("game-gin")).to_have_attribute("aria-checked", "true")
    # The choice is remembered.
    page.reload()
    expect(page.get_by_test_id("game-gin")).to_have_attribute("aria-checked", "true")
    page.get_by_test_id("game-wild").click()
    expect(page.get_by_role("heading", level=1)).to_contain_text("Wild Joker")


def test_two_players_take_turns(make_context, screenshot):
    host = make_context("phone").new_page()
    guest = make_context("phone").new_page()
    code = create_gin_room(host, "Viktor")
    expect(host.get_by_test_id("gin-info")).to_be_visible()
    join_by_link(guest, f"/j/{code}", "Babka")
    host.get_by_test_id("start").click()

    # The host starts: draws from the deck, and discards a card.
    expect(host.get_by_test_id("status")).to_contain_text("Your turn")
    expect(guest.get_by_test_id("status")).to_have_text("Viktor's turn")
    expect(host.locator(".hand [data-card]")).to_have_count(7)
    expect(guest.get_by_test_id("deck")).to_be_disabled()
    host.get_by_test_id("deck").click()
    expect(host.locator(".hand [data-card]")).to_have_count(8)
    screenshot(host, "gin-phone")
    thrown = hand(host)[0]
    tap_card(host, thrown)
    host.get_by_test_id("discard-btn").click()
    expect(host.locator(".hand [data-card]")).to_have_count(7)

    # The guest sees it on the discard pile, takes it, and can't throw it back.
    expect(guest.get_by_test_id("status")).to_contain_text("Your turn")
    expect(guest.locator(f"[data-testid=discard] [data-card='{thrown}']")).to_be_visible()
    assert discard_pile(guest)[-1] == thrown
    guest.locator(f"[data-testid=discard] [data-card='{thrown}']").click()
    expect(guest.locator(f".hand [data-card='{thrown}']")).to_be_visible()
    tap_card(guest, thrown)
    expect(guest.get_by_test_id("discard-btn")).to_be_disabled()
    tap_card(guest, thrown)
    other = next(c for c in hand(guest) if c != thrown)
    tap_card(guest, other)
    guest.get_by_test_id("discard-btn").click()

    # Back to the host, who now sees the guest's discard on top.
    expect(host.get_by_test_id("status")).to_contain_text("Your turn")
    expect(host.locator(f"[data-testid=discard] [data-card='{other}']")).to_be_visible()
    assert discard_pile(host)[-1] == other
    # Scores show in the player strip; the round number in the header.
    expect(host.get_by_test_id("score")).to_have_count(2)
    expect(host.get_by_test_id("round")).to_contain_text("Round 1")


def test_gin_tutorial_by_following_the_highlights(phone):
    page = phone.new_page()
    page.goto("/")
    page.get_by_test_id("game-gin").tap()
    page.get_by_test_id("tutorial-start").tap()
    coach = page.get_by_test_id("tutorial")
    expect(coach).to_be_visible()
    # Off-script moves are refused: the top discard can't be taken at the start.
    page.locator("[data-testid=discard] [data-card]").last.tap()
    expect(page.locator(".toast").last).to_contain_text("Follow the step")

    steps = []
    for _ in range(MAX_TAPS):
        if page.get_by_test_id("tutorial-outro").is_visible():
            break
        step = coach.get_attribute("data-step")
        if not steps or steps[-1] != step:
            steps.append(step)
            page.screenshot(path=str(SCREENSHOTS / f"gin-tutorial-{len(steps):02d}-{step}.png"))
        next_button = page.get_by_test_id("tutorial-next")
        if next_button.is_visible():
            expect(next_button).to_be_enabled()
            next_button.tap()
        else:
            assert tap_highlight(page), f"step {step}: nothing to tap"
        page.wait_for_timeout(400)  # let the move land and the rings move
    else:
        page.screenshot(path=str(SCREENSHOTS / "gin-tutorial-stuck.png"))
        raise AssertionError(f"tutorial didn't finish; steps seen: {steps}")

    assert steps == [
        "welcome",
        "screen",
        "draw",
        "meld",
        "discard",
        "teacher",
        "dig",
        "own",
        "other",
        "discard_again",
        "teacher_again",
        "draw_last",
        "joker",
        "gin",
    ]
    expect(page.get_by_test_id("tutorial-outro")).to_contain_text("80 points")
    expect(page.get_by_test_id("final-score").first).to_have_text("80 points")
    page.screenshot(path=str(SCREENSHOTS / "gin-tutorial-99-outro.png"))
    page.get_by_test_id("tutorial-play").tap()
    expect(page.get_by_test_id("tutorial-start")).to_be_visible()
