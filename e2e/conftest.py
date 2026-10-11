"""Fixtures for the browser tests: one Chromium, desktop and phone contexts."""

import os
from pathlib import Path

import pytest
from playwright.sync_api import Browser, BrowserContext, sync_playwright

BASE_URL = os.environ.get("WILDJOKER_URL", "http://127.0.0.1:8101")
SCREENSHOTS = Path(os.environ.get("WILDJOKER_SCREENSHOTS", Path(__file__).parents[1] / "screenshots"))
PHONE = "iPhone SE (3rd gen)"  # 375 x 667


@pytest.fixture(scope="session")
def pw():
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(pw) -> Browser:
    browser = pw.chromium.launch()
    yield browser
    browser.close()


ERRORS: list[str] = []


def _context(browser: Browser, **kwargs) -> BrowserContext:
    context = browser.new_context(base_url=BASE_URL, locale="en-US", **kwargs)
    context.set_default_timeout(10_000)

    def watch(page):
        page.on("pageerror", lambda e: ERRORS.append(f"{page.url}: {e}"))
        page.on("console", lambda m: m.type == "error" and ERRORS.append(f"{page.url}: {m.text}"))

    context.on("page", watch)
    return context


@pytest.fixture(autouse=True)
def no_page_errors():
    """Fail a test when the app throws or logs an error."""
    ERRORS.clear()
    yield
    assert ERRORS == []


@pytest.fixture
def desktop(browser):
    context = _context(browser, viewport={"width": 1280, "height": 800})
    yield context
    context.close()


@pytest.fixture
def phone(browser, pw):
    device = {k: v for k, v in pw.devices[PHONE].items() if k != "default_browser_type"}
    context = _context(browser, **device)
    yield context
    context.close()


@pytest.fixture
def make_context(browser, pw):
    """Contexts by kind ('desktop' or 'phone'), closed after the test."""
    made = []

    def make(kind: str) -> BrowserContext:
        if kind == "phone":
            device = {k: v for k, v in pw.devices[PHONE].items() if k != "default_browser_type"}
            context = _context(browser, **device)
        else:
            context = _context(browser, viewport={"width": 1280, "height": 800})
        made.append(context)
        return context

    yield make
    for context in made:
        context.close()


@pytest.fixture(scope="session")
def screenshot():
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)

    def take(page, name: str) -> None:
        page.screenshot(path=SCREENSHOTS / f"{name}.png")

    return take
