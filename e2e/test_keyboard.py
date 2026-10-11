"""A game played with the keyboard only, on desktop."""

from playwright.sync_api import expect

from helpers import draw_until, extends, find_run, hand, table


def tab_to(page, test_id: str, limit: int = 40) -> None:
    for _ in range(limit):
        page.keyboard.press("Tab")
        if page.evaluate("document.activeElement?.dataset.testid") == test_id:
            return
    raise AssertionError(f"couldn't tab to {test_id}")


def select_with_arrows(page, cards: list[int]) -> None:
    for card in cards:
        page.keyboard.press("h")
        for _ in range(hand(page).index(card)):
            page.keyboard.press("ArrowRight")
        assert page.evaluate("document.activeElement.dataset.card") == str(card)
        page.keyboard.press("Enter")


def test_keyboard_only_game(desktop, screenshot):
    page = desktop.new_page()
    page.goto("/")
    page.keyboard.type("Keys")  # the name field has focus
    page.keyboard.press("Enter")
    expect(page.get_by_test_id("room-code")).to_be_visible()
    tab_to(page, "add-cpu")
    page.keyboard.press("Enter")
    expect(page.get_by_test_id("lobby-players").locator("li")).to_have_count(2)
    tab_to(page, "start")
    page.keyboard.press("Enter")
    expect(page.locator(".hand [data-card]")).to_have_count(5)

    # D draws.
    page.keyboard.press("d")
    expect(page.locator(".hand [data-card]")).to_have_count(6)

    # ? shows the shortcuts, Esc closes them.
    page.keyboard.press("?")
    expect(page.get_by_test_id("shortcuts")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.get_by_test_id("shortcuts")).to_be_hidden()

    # Select a run with the arrows and Enter, open with O.
    run = draw_until(page, find_run, press="d")
    select_with_arrows(page, run)
    expect(page.locator(".hand [aria-pressed=true]")).to_have_count(3)
    page.keyboard.press("o")
    expect(page.locator("[data-testid=table] [data-pile]")).to_have_count(1)

    # Select a card that fits, T to the table, Enter takes the pile with it, S commits.
    pile = table(page)[0]
    card = draw_until(page, lambda h: next((c for c in h if extends(c, pile)), None), press="d")
    select_with_arrows(page, [card])
    page.keyboard.press("t")
    assert page.evaluate("document.activeElement.dataset.pile") is not None
    page.keyboard.press("Enter")
    sheet = page.get_by_test_id("staging")
    expect(sheet.get_by_test_id("commit")).to_be_enabled()
    page.keyboard.press("s")
    expect(sheet).to_have_count(0)
    assert sorted(table(page)[0]) == sorted(pile + [card])

    # Esc clears a selection, then cancels a move.
    page.keyboard.press("h")
    page.keyboard.press("Enter")
    expect(page.locator(".hand [aria-pressed=true]")).to_have_count(1)
    page.keyboard.press("Escape")
    expect(page.locator(".hand [aria-pressed=true]")).to_have_count(0)
    page.keyboard.press("t")
    page.keyboard.press("Enter")
    expect(sheet).to_be_visible()
    page.keyboard.press("Escape")
    expect(sheet).to_have_count(0)
    screenshot(page, "game-keyboard-desktop")
