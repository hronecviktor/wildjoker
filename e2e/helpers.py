"""Helpers for driving the app: rooms, hands and simple moves."""

import re

from playwright.sync_api import Page, expect

ACE_HIGH = 14


def suit(card: int) -> int | None:
    index = card % 54
    return None if index >= 52 else index // 13


def rank(card: int) -> int | None:
    index = card % 54
    return None if index >= 52 else index % 13 + 1


def create_room(page: Page, name: str) -> str:
    page.goto("/")
    page.get_by_test_id("name").fill(name)
    page.get_by_test_id("create").click()
    code = page.get_by_test_id("room-code")
    expect(code).to_have_text(re.compile(r"^[A-Z]{4}$"))
    return code.inner_text()


def join_by_link(page: Page, link: str, name: str) -> None:
    page.goto(link)
    page.get_by_test_id("name").fill(name)
    page.get_by_test_id("join").click()
    expect(page.get_by_test_id("room-code")).to_be_visible()


def hand(page: Page) -> list[int]:
    """Card ids in the hand, in display order."""
    return [int(c) for c in page.locator(".hand [data-card]").evaluate_all("els => els.map(e => e.dataset.card)")]


def table(page: Page) -> list[list[int]]:
    return page.locator("[data-testid=table] [data-pile]").evaluate_all(
        "piles => piles.map(p => [...p.querySelectorAll('[data-card]')].map(c => +c.dataset.card))"
    )


def find_run(cards: list[int]) -> list[int] | None:
    """A joker-free run of 3 in the hand (as engine.piles.find_opening, shortest is enough)."""
    by_suit: dict[int, dict[int, int]] = {}
    for c in cards:
        if suit(c) is None:
            continue
        ranks = by_suit.setdefault(suit(c), {})
        ranks[rank(c)] = c
        if rank(c) == 1:
            ranks[ACE_HIGH] = c
    for ranks in by_suit.values():
        for low in range(1, ACE_HIGH - 1):
            if all(v in ranks for v in (low, low + 1, low + 2)):
                return [ranks[low], ranks[low + 1], ranks[low + 2]]
    return None


def extends(card: int, pile: list[int]) -> bool:
    """Whether the card can be added to a joker-free run."""
    if suit(card) is None:
        return len(pile) < 13
    if suit(card) != suit(pile[0]) or len(pile) >= 13:
        return False
    values = {rank(c) for c in pile}
    if rank(card) in values:
        return False
    if 1 in values and 13 in values:  # ace high
        values = {ACE_HIGH if v == 1 else v for v in values}
    lo, hi, r = min(values), max(values), rank(card)
    return r == lo - 1 or r == hi + 1 or (r == 1 and hi == 13)


def draw(page: Page) -> None:
    before = len(hand(page))
    page.get_by_test_id("draw").click()
    expect(page.locator(".hand [data-card]")).to_have_count(before + 1)


def draw_until(page: Page, found, limit: int = 90, press: str | None = None):
    """Draw until `found(hand)` returns something truthy, and return it."""
    for _ in range(limit):
        result = found(hand(page))
        if result:
            return result
        before = len(hand(page))
        if press:
            page.keyboard.press(press)
        else:
            page.get_by_test_id("draw").click()
        expect(page.locator(".hand [data-card]")).to_have_count(before + 1)
    raise AssertionError("didn't draw what we needed")


def tap_card(page: Page, card: int) -> None:
    # Cards in the hand overlap; tap the visible top-left corner, like a finger would.
    page.locator(f".hand [data-card='{card}']").click(position={"x": 14, "y": 22})
