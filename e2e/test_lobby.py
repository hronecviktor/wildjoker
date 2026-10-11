"""Creating a room and joining it through the invite link on a phone."""

from playwright.sync_api import expect

from helpers import create_room, join_by_link


def test_invite_link_on_phone(desktop, phone, screenshot):
    host = desktop.new_page()
    code = create_room(host, "Viktor")
    link = host.get_by_test_id("invite-link").inner_text()
    assert link.endswith(f"/j/{code}")

    guest = phone.new_page()
    guest.goto(link)
    expect(guest.get_by_text(f"You're invited to game {code}")).to_be_visible()
    join_by_link(guest, link, "Hana")

    # Both see the lobby fill up live.
    for page in (host, guest):
        players = page.get_by_test_id("lobby-players")
        expect(players).to_contain_text("Viktor")
        expect(players).to_contain_text("Hana")
    expect(guest.get_by_test_id("room-code")).to_have_text(code)

    # Host controls: options and a CPU show up for the guest.
    host.get_by_role("radio", name="3").click()
    host.get_by_test_id("add-cpu").click()
    expect(guest.get_by_test_id("lobby-players").locator("li")).to_have_count(3)
    expect(guest.locator(".options")).to_contain_text("3")
    expect(guest.get_by_test_id("start")).to_have_count(0)  # only the host can start

    screenshot(guest, "lobby-phone")
    screenshot(host, "lobby-desktop")

    # Reloading keeps the seat (resume with the stored token).
    guest.reload()
    expect(guest.get_by_test_id("lobby-players").locator("li")).to_have_count(3)
    expect(host.get_by_test_id("lobby-players").locator("li")).to_have_count(3)

    # Kick the guest.
    host.get_by_role("button", name="Kick Hana").click()
    expect(guest.get_by_test_id("create")).to_be_visible()
    expect(host.get_by_test_id("lobby-players").locator("li")).to_have_count(2)


def test_slovak(phone):
    page = phone.new_page()
    page.goto("/")
    page.get_by_label("Language").select_option("sk")
    expect(page.get_by_test_id("create")).to_have_text("Založiť hru")
    page.reload()
    expect(page.get_by_test_id("create")).to_have_text("Založiť hru")
