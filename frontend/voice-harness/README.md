# Voice harness

A standalone page and tests for `frontend/src/lib/voice`, independent of the
real app (it only needs the backend).

```bash
cd frontend/voice-harness
npm install
npm test             # unit tests (Vitest, fake RTCPeerConnection)
npm run check        # TypeScript
npm run build        # the page, into dist/
```

## Trying it by hand

Serve the built page with the backend on one port, so `/ws` and `/ice` are
same-origin:

```bash
cd backend
WILDJOKER_STATIC=../frontend/voice-harness/dist uv run python -m wildjoker.server --port 8103
```

Open http://127.0.0.1:8103 in two browser windows (microphone access needs
`localhost`/`127.0.0.1` or HTTPS), create a room in one, join it with the
code in the other, and press **Join voice** in both. Headphones help.

## Real-browser test

`browser_test.py` drives three Chromium pages with fake microphones that play
a generated speech-like signal (`make_speech_wav.py`), against the backend
above:

```bash
./run_browser_test.sh               # http://127.0.0.1:8103 by default
```

It runs in the `mcr.microsoft.com/playwright/python:v1.58.0-noble` image
with `--network host`, installs the `playwright` Python package once into
`~/envs/wildjoker-voice-pw`, and checks that:

- all three pages connect to each other, two of them joining at once;
- audio flows on every connection (`inbound-rtp` bytes grow);
- every player is detected as speaking;
- a muted player is shown muted everywhere and never as speaking;
- leaving and rejoining voice reconnects;
- after the game socket drops and resumes, the player is back in voice by
  itself and audio flows again.

`./run_browser_test.sh --relay` forces all audio through TURN
(`iceTransportPolicy: "relay"`, the page's `?relay` option) and checks that
every connection uses a relay candidate. It needs a TURN server and the
backend configured for it, e.g. coturn with `deploy/turnserver.conf` on
`127.0.0.1:13478` (with `allow-loopback-peers` and the `127.0.0.0` denial
removed, for local testing only) and the backend started with
`WILDJOKER_TURN_URLS="turn:127.0.0.1:13478?transport=udp"
WILDJOKER_TURN_SECRET=<its static-auth-secret>`.
