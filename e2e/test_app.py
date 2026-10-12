"""Installing the site as an app (PWA): manifest, service worker, offline page."""

from playwright.sync_api import Page, expect


def wait_for_worker(page: Page) -> None:
    """Wait until the service worker is active and controls the page."""
    page.evaluate("navigator.serviceWorker.ready")
    page.reload()
    page.wait_for_function("navigator.serviceWorker.controller !== null")


def test_chrome_can_install_it(desktop):
    page = desktop.new_page()
    page.goto("/")
    manifest = page.evaluate(
        "fetch(document.querySelector('link[rel=manifest]').href).then((r) => r.json())"
    )
    assert manifest["name"] == "Wild Joker"
    assert manifest["display"] == "standalone"
    assert {"192x192", "512x512"} <= {icon["sizes"] for icon in manifest["icons"]}
    assert any(icon["purpose"] == "maskable" for icon in manifest["icons"])
    wait_for_worker(page)
    # Chrome's own installability check, the one behind its install prompt.
    cdp = desktop.new_cdp_session(page)
    errors = cdp.send("Page.getInstallabilityErrors")["installabilityErrors"]
    assert errors == []


def test_offline_shows_the_offline_page(phone):
    page = phone.new_page()
    page.goto("/")
    wait_for_worker(page)
    phone.set_offline(True)
    page.reload()
    expect(page.get_by_role("heading", name="No connection")).to_be_visible()
    expect(page.get_by_role("button", name="Try again")).to_be_visible()
    # Back online, it reloads by itself.
    phone.set_offline(False)
    expect(page.get_by_test_id("tutorial-start")).to_be_visible()


def test_iphone_gets_install_steps(phone):
    # The phone context is an iPhone, which has no install prompt.
    page = phone.new_page()
    page.goto("/")
    page.get_by_test_id("install").tap()
    help = page.get_by_test_id("install-help")
    expect(help).to_contain_text("Add to Home Screen")
    help.get_by_role("button", name="Close").tap()
    expect(help).to_be_hidden()
