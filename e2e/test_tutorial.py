"""The tutorial on a phone, done by tapping only what it points at.

If an instruction doesn't lead to its goal, this gets stuck and fails, so
it checks that the highlighted targets really walk through the game.
"""

import re

from conftest import SCREENSHOTS
from playwright.sync_api import Page, expect

MAX_TAPS = 60


def tap_highlight(page: Page) -> bool:
    """Tap the middle of the first highlighted target; False if there is none."""
    ring = page.locator(".ring").first
    if not ring.count():
        return False
    box = ring.bounding_box()
    page.touchscreen.tap(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    return True


def test_tutorial_by_following_the_highlights(phone):
    page = phone.new_page()
    page.goto("/")
    page.get_by_test_id("tutorial-start").tap()
    coach = page.get_by_test_id("tutorial")
    expect(coach).to_be_visible()
    expect(page.get_by_test_id("draw")).to_be_disabled()  # no drawing until a step asks

    steps, last_hint, hints = [], "", 0
    for _ in range(MAX_TAPS):
        if page.get_by_test_id("tutorial-outro").is_visible():
            break
        step = coach.get_attribute("data-step")
        hint = page.get_by_test_id("tutorial-hint")
        hint = hint.inner_text() if hint.is_visible() else ""
        if not steps or steps[-1] != step:
            steps.append(step)
            hints = 0
            page.screenshot(path=str(SCREENSHOTS / f"tutorial-{len(steps):02d}-{step}.png"))
        if hint and hint != last_hint:
            hints += 1
            page.screenshot(path=str(SCREENSHOTS / f"tutorial-{len(steps):02d}-{step}-{hints}.png"))
        last_hint = hint
        next_button = page.get_by_test_id("tutorial-next")
        if next_button.is_visible():
            expect(next_button).to_be_enabled()
            next_button.tap()
        else:
            assert tap_highlight(page), f"step {step}: nothing to tap"
        page.wait_for_timeout(400)  # let the move land and the rings move
    else:
        page.screenshot(path=str(SCREENSHOTS / "tutorial-stuck.png"))
        raise AssertionError(f"tutorial didn't finish; steps seen: {steps}")

    assert steps == [
        "welcome",
        "screen",
        "draw",
        "open",
        "teacher",
        "draw_again",
        "add",
        "joker",
        "split",
        "locked",
        "take",
    ]
    expect(page.get_by_test_id("tutorial-outro")).to_contain_text("You won")
    page.screenshot(path=str(SCREENSHOTS / "tutorial-99-outro.png"))
    page.get_by_test_id("tutorial-play").tap()
    expect(page.get_by_test_id("tutorial-start")).to_be_visible()
    expect(page).to_have_url(re.compile(r"/$"))


def test_tutorial_skip(phone):
    page = phone.new_page()
    page.goto("/")
    page.get_by_test_id("tutorial-start").tap()
    page.get_by_test_id("tutorial-skip").tap()
    expect(page.get_by_test_id("tutorial-start")).to_be_visible()
