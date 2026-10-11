# Voice chat module

Full-mesh WebRTC audio between the players in a room (up to 8, so at most 7
connections each). The game WebSocket relays the connection setup; see
`shared/protocol.md` (Voice).

```ts
import { createVoice, VoiceError } from "$lib/voice"; // or a relative path

const voice = createVoice((msg) => socket.send(JSON.stringify(msg)));

// On every message from the server:
if (msg.type === "state") voice.updatePeers(msg.players, msg.you);
if (msg.type === "signal") voice.handleSignal(msg.from, msg.data);

// From a click (the browser asks for the microphone):
try {
  await voice.join();
} catch (e) {
  if (e instanceof VoiceError) showError(t(`voice.error.${e.code}`));
}
voice.setMuted(true);   // M key; can also be set before joining
voice.leave();          // also call it when leaving the room

// In a component: stores from svelte/store.
const { speaking, playbackBlocked } = voice;
// {#if $speaking.has(player.id)} ... {/if}   {#if $playbackBlocked} ... {/if}
```

- `updatePeers` accepts the `players` of a state as they are; it reads `id`,
  `voice` and `muted` (a player muted in the state is never shown as
  speaking). Call it on every state, also before `join()`, so the module
  knows your player id.
- `VoiceError.code` is one of `permission_denied`, `no_device`,
  `device_busy` (mic used by another app), `insecure_context` (not HTTPS),
  `unsupported`, `failed`. A failed `join()` can be retried.
- `playbackBlocked` (an extra store beyond the agreed interface) is `true`
  while the browser blocks audio playback until a user gesture. The module
  retries by itself on the next click or key press anywhere, so the UI only
  needs to show a hint like "tap to hear the others".
- Reconnects of the game socket need nothing special: the server drops the
  player from voice on reconnect, and the module sends `voice_join` (and
  the mute state) again by itself when the next state shows it.
- Remote audio plays through hidden `<audio data-voice>` elements appended to
  `<body>`.
- STUN/TURN servers come from `GET /ice?player=<id>` (fetched on `join()`
  and refreshed before the TURN credentials expire); without it the module
  falls back to public STUN.

## How it works

- `controller.ts`: joining, leaving, muting, which peers to connect to
  (everyone in voice once the server confirms we are in voice too),
  re-joining after a socket reconnect, TURN credential refresh, speaking
  detection and playback.
- `peer.ts`: one `RTCPeerConnection` with the perfect negotiation pattern.
  The player with the smaller id is polite: it waits for the other side's
  first offer (up to 3 s) and sends its audio in the answer, because when
  first offers cross Chromium sometimes never starts ICE on the side that
  rolled back. After that either side may offer (ICE restarts), and
  crossing offers are resolved by the polite side rolling back. Every signal carries the
  sender's connection id (`sid`) and, once known, the receiver's (`to`), so
  signals for a closed connection are dropped and a peer that rejoined gets
  a fresh connection. A failed connection first tries an ICE restart; if it
  stays failed for 10 s, the impolite side replaces it.
- `speaking.ts`: debounced level detection (Web Audio `AnalyserNode`, RMS
  sampled every 100 ms): on after 100 ms above the threshold, off after
  500 ms below.
- `env.ts`: the browser APIs, behind an interface so `testing.ts` can fake
  them.

## Tests

`voice.test.ts` runs the negotiation against a fake `RTCPeerConnection` and a
fake server with random delays (glare, rejoining, reconnects, failures).
`frontend/voice-harness/` has a standalone page and a real-browser test with
Chromium's fake microphones; see its README.
