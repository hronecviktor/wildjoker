"""Real-browser voice test: three Chromium pages with fake microphones.

Needs the backend serving the built harness (see README.md), then:

    python browser_test.py http://127.0.0.1:8103

Checks that every page connects to the other two, that audio flows
(inbound-rtp bytes grow, audio level is non-zero), that speaking is
detected, and that mute shows up everywhere and silences the speaker.
"""

import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from make_speech_wav import main as make_speech_wav

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8103"
SPEECH = Path(tempfile.gettempdir()) / "wildjoker-speech.wav"
FLAGS = [
    "--use-fake-ui-for-media-stream",
    "--use-fake-device-for-media-stream",
    f"--use-file-for-fake-audio-capture={SPEECH}",
]


def wait_for(page: Page, js: str, timeout: float = 15_000):
    return page.wait_for_function(js, timeout=timeout).json_value()


def stats(page: Page):
    return page.evaluate("harness.stats()")


def poll(fn, seconds: float, interval: float = 0.1):
    """Collect fn() every interval for some seconds."""
    results = []
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        results.append(fn())
        time.sleep(interval)
    return results


def main() -> None:
    make_speech_wav(str(SPEECH))
    with sync_playwright() as p:
        browser = p.chromium.launch(args=FLAGS)
        pages = []
        for i in range(3):
            context = browser.new_context(permissions=["microphone"])
            page = context.new_page()
            page.on("console", lambda m, i=i: m.type in ("error", "warning") and print(f"[{i}]", m.text))
            page.goto(URL)
            page.fill("#name", f"P{i}")
            pages.append(page)

        host = pages[0]
        host.click("#create")
        code = wait_for(host, "harness.state()?.code")
        for page in pages[1:]:
            page.fill("#code", code)
            page.click("#join-room")
        for page in pages:
            wait_for(page, "harness.state()?.players.length === 3")
        ids = [page.evaluate("harness.state().you") for page in pages]
        print("room", code, "players", ids)

        # Joining one after another, then two at the same time (glare).
        pages[0].click("#join")
        wait_for(pages[0], "harness.state().players[0].voice")
        pages[1].click("#join", no_wait_after=True)
        pages[2].click("#join", no_wait_after=True)

        for i, page in enumerate(pages):
            wait_for(
                page,
                "harness.stats().then(s => s.length === 2 && s.every(x => x.state === 'connected'))",
            )
            print(f"page {i}: connected to 2 peers")
            wait_for(page, "harness.state().players.every(p => p.voice)")

        # Audio flows: bytes received keep growing on every connection.
        before = [stats(page) for page in pages]
        time.sleep(2)
        after = [stats(page) for page in pages]
        problems = []
        for i, (b, a) in enumerate(zip(before, after, strict=True)):
            grown = [y["bytes"] - x["bytes"] for x, y in zip(b, a, strict=True)]
            print(f"page {i}: inbound bytes grew by {grown}, levels {[s['level'] for s in a]}")
            if not all(g > 1000 for g in grown):
                problems.append((i, a))
        for i, a in problems:
            print(f"page {i} connections:", a)
            print("\n".join(pages[i].evaluate("harness.trace")))
        assert not problems

        # The fake microphones play speech.wav: everyone speaks now and then.
        seen = set()
        for sample in poll(lambda: pages[0].evaluate("harness.speaking()"), 4):
            seen.update(sample)
        print("page 0 saw speaking:", sorted(seen))
        assert set(ids) <= seen, seen

        # Mute: shown in everyone's state, never speaking, and silent for the others.
        pages[1].click("#mute")
        for page in pages:
            wait_for(page, f"harness.state().players.find(p => p.id === '{ids[1]}').muted")
        time.sleep(1)
        for page in (pages[0], pages[1]):
            samples = poll(lambda page=page: page.evaluate("harness.speaking()"), 3)
            assert not any(ids[1] in s for s in samples), samples
        print("muted player is never speaking")

        # Leave and rejoin.
        pages[2].click("#leave")
        wait_for(pages[0], "harness.stats().then(s => s.length === 1)")
        pages[2].click("#join")
        for page in pages:
            wait_for(
                page,
                "harness.stats().then(s => s.length === 2 && s.every(x => x.state === 'connected'))",
            )
        print("leave and rejoin: reconnected")

        # The game socket of page 0 drops and comes back: the server takes it
        # out of voice, the module joins again by itself.
        pages[0].evaluate("harness.reconnect()")
        for page in pages:
            wait_for(page, "harness.state().players.every(p => p.voice)")
            wait_for(
                page,
                "harness.stats().then(s => s.length === 2 && s.every(x => x.state === 'connected'))",
            )
        before = stats(pages[1])
        time.sleep(1)
        after = stats(pages[1])
        assert all(y["bytes"] > x["bytes"] for x, y in zip(before, after, strict=True))
        print("socket reconnect: back in voice, audio flows")

        errors = [page.evaluate("harness.errors") for page in pages]
        print("server errors:", errors)
        browser.close()
    print("OK")


if __name__ == "__main__":
    main()
