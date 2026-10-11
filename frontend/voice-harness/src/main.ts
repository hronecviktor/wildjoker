// A bare page to try the voice module without the real app: create or join
// a room, then join voice. Exposes `window.harness` for the browser test.

import { get } from "svelte/store";
import { createVoice, VoiceError } from "../../src/lib/voice";
import { browserEnv } from "../../src/lib/voice/env";

interface Player {
  id: string;
  name: string;
  voice: boolean;
  muted: boolean;
}

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const pcs: RTCPeerConnection[] = [];
const env = browserEnv();
const realCreate = env.createPeerConnection;
// ?relay forces audio through the TURN server, to test it.
const relayOnly = new URLSearchParams(location.search).has("relay");
env.createPeerConnection = (config) => {
  const pc = realCreate(relayOnly ? { ...config, iceTransportPolicy: "relay" } : config);
  pcs.push(pc);
  return pc;
};

const meters: { level(): number }[] = [];
const realMeter = env.createMeter;
env.createMeter = (stream) => {
  const meter = realMeter(stream);
  meters.push(meter);
  return meter;
};

let ws: WebSocket;
let opened: Promise<unknown>;
let session: { code: string; token: string } | null = null;
const trace: string[] = [];
const t0 = performance.now();
const describe = (m: any, data: any) =>
  `${Math.round(performance.now() - t0)} ${m} ${data?.sid ?? ""}${data?.to ? ">" + data.to : ""} ${data?.description?.type ?? (data?.candidate ? "cand" : "")}`;
const send = (msg: object) => {
  const m = msg as any;
  trace.push(describe(m.type === "signal" ? `send ${m.to}` : m.type, m.data));
  if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
};
const voice = createVoice(send, env);
let state: { you: string; code: string; players: Player[] } | null = null;
let muted = false;
const errors: string[] = [];

function onMessage(event: MessageEvent) {
  const msg = JSON.parse(event.data);
  if (msg.type === "welcome") {
    session = { code: msg.code, token: msg.token };
  } else if (msg.type === "state") {
    trace.push(`${Math.round(performance.now() - t0)} state ${msg.players.map((p: Player) => p.id + (p.voice ? "+" : "-")).join(" ")}`);
    state = msg;
    voice.updatePeers(msg.players, msg.you);
    render();
  } else if (msg.type === "signal") {
    trace.push(describe(`recv ${msg.from}`, msg.data));
    voice.handleSignal(msg.from, msg.data);
  } else if (msg.type === "error") {
    errors.push(msg.code);
  }
}

function connect() {
  ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  ws.onmessage = onMessage;
  opened = new Promise((resolve) => ws.addEventListener("open", resolve));
}
connect();

/** Drop the game socket and resume the seat on a new one, like a flaky network. */
async function reconnect() {
  ws.close();
  connect();
  await opened;
  if (session) send({ type: "resume", ...session });
}

function render() {
  if (!state) return;
  $("room").textContent = state.code;
  const speaking = get(voice.speaking);
  $("players").replaceChildren(
    ...state.players.map((p) => {
      const li = document.createElement("li");
      li.dataset.id = p.id;
      li.className = speaking.has(p.id) ? "speaking" : "";
      li.textContent = `${p.name}${p.id === state!.you ? " (you)" : ""}: ${p.voice ? "in voice" : "–"}${p.muted ? ", muted" : ""}${speaking.has(p.id) ? ", speaking" : ""}`;
      return li;
    }),
  );
}
voice.speaking.subscribe(render);
voice.playbackBlocked.subscribe((blocked) => ($("blocked").hidden = !blocked));

$("create").onclick = async () => {
  await opened;
  send({ type: "create", name: $<HTMLInputElement>("name").value });
};
$("join-room").onclick = async () => {
  await opened;
  send({ type: "join", code: $<HTMLInputElement>("code").value, name: $<HTMLInputElement>("name").value });
};
$("join").onclick = async () => {
  $("error").textContent = "";
  try {
    await voice.join();
  } catch (e) {
    $("error").textContent = e instanceof VoiceError ? e.code : String(e);
  }
};
$("leave").onclick = () => voice.leave();
$("mute").onclick = () => {
  muted = !muted;
  voice.setMuted(muted);
  $("mute").textContent = muted ? "Unmute" : "Mute";
};

/** Audio bytes and level received per open connection. */
async function stats() {
  const result = [];
  for (const pc of pcs) {
    if (pc.connectionState === "closed") continue;
    let bytes = 0;
    let sent = 0;
    let level = 0;
    let candidate = "";
    const report = await pc.getStats();
    report.forEach((s) => {
      if (s.type === "transport" && s.selectedCandidatePairId) {
        const pair = report.get(s.selectedCandidatePairId);
        candidate = report.get(pair?.localCandidateId)?.candidateType ?? "";
      } else if (s.type === "inbound-rtp" && s.kind === "audio") {
        bytes += s.bytesReceived ?? 0;
        level = Math.max(level, s.audioLevel ?? 0);
      } else if (s.type === "outbound-rtp" && s.kind === "audio") {
        sent += s.bytesSent ?? 0;
      }
    });
    const transceivers = pc
      .getTransceivers()
      .map((t) => `${t.mid}:${t.direction}/${t.currentDirection}:${t.sender.track ? "track" : "none"}`);
    const ufrag = (d: RTCSessionDescription | null) => d?.sdp.match(/a=ice-ufrag:(\S+)/)?.[1];
    result.push({
      state: pc.connectionState,
      bytes,
      sent,
      level,
      candidate,
      transceivers,
      ice: `${ufrag(pc.localDescription)}->${ufrag(pc.remoteDescription)}`,
      signaling: pc.signalingState,
    });
  }
  return result;
}

Object.assign(window, {
  harness: {
    voice,
    stats,
    reconnect,
    errors,
    trace,
    state: () => state,
    speaking: () => [...get(voice.speaking)],
    levels: () => meters.map((m) => m.level()),
  },
});
