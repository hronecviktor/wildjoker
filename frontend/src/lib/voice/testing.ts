// Fakes for testing the voice module in Node: a fake RTCPeerConnection that
// follows the signalling state machine (including implicit rollback), and a
// fake game server that relays signals with random delays.

import type { AudioSink, LevelMeter, VoiceEnv } from "./env";
import type { VoiceController, VoicePlayer } from "./controller";

const tick = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

function domError(name: string, message = name): Error {
  const e = new Error(message);
  e.name = name;
  return e;
}

export class FakeTrack {
  readonly kind = "audio";
  enabled = true;
  stopped = false;
  stop() {
    this.stopped = true;
  }
}

export class FakeStream {
  constructor(
    readonly id: string,
    readonly tracks: FakeTrack[] = [new FakeTrack()],
  ) {}
  getAudioTracks() {
    return this.tracks;
  }
  getTracks() {
    return this.tracks;
  }
}

interface FakeDescription {
  type: "offer" | "answer";
  sdp: string;
}

function description(type: "offer" | "answer", sdp: string) {
  return { type, sdp, toJSON: () => ({ type, sdp }) };
}

let pcIds = 0;

export class FakePeerConnection {
  readonly id = ++pcIds;
  signalingState: RTCSignalingState = "stable";
  connectionState: RTCPeerConnectionState = "new";
  localDescription: ReturnType<typeof description> | null = null;
  remoteDescription: FakeDescription | null = null;
  senders: FakeTrack[] = [];
  candidates: RTCIceCandidateInit[] = [];
  rollbacks = 0;
  restarts = 0;
  closed = false;
  broken = false;
  onnegotiationneeded: (() => void) | null = null;
  onicecandidate: ((e: { candidate: { toJSON(): RTCIceCandidateInit } | null }) => void) | null =
    null;
  ontrack: ((e: { track: FakeTrack; streams: FakeStream[] }) => void) | null = null;
  onconnectionstatechange: (() => void) | null = null;

  private negotiated = 0; // senders included in a completed negotiation
  private restartPending = false;
  private negotiationQueued = false;
  private gotTrack = false;

  constructor(public config: RTCConfiguration) {}

  addTrack(track: FakeTrack) {
    this.senders.push(track);
    this.queueNegotiation();
  }

  restartIce() {
    this.restartPending = true;
    this.restarts++;
    this.queueNegotiation();
  }

  setConfiguration(config: RTCConfiguration) {
    this.config = config;
  }

  async setLocalDescription(): Promise<void> {
    await tick();
    if (this.closed) throw domError("InvalidStateError", "closed");
    if (this.signalingState === "have-remote-offer") {
      this.localDescription = description("answer", `answer from ${this.id} senders=${this.senders.length}`);
      this.signalingState = "stable";
      this.completed();
    } else {
      this.localDescription = description("offer", `offer from ${this.id} senders=${this.senders.length}`);
      this.signalingState = "have-local-offer";
      this.restartPending = false;
    }
    setTimeout(() => {
      if (!this.closed) this.onicecandidate?.({ candidate: { toJSON: () => ({ candidate: `c${this.id}`, sdpMid: "0" }) } });
    }, 0);
  }

  async setRemoteDescription(desc: RTCSessionDescriptionInit): Promise<void> {
    await tick();
    if (this.closed) throw domError("InvalidStateError", "closed");
    if (desc.type === "offer") {
      if (this.signalingState === "have-local-offer") {
        this.rollbacks++; // implicit rollback
        this.localDescription = null;
        this.signalingState = "stable";
      }
      if (this.signalingState !== "stable") throw domError("InvalidStateError", `offer in ${this.signalingState}`);
      this.remoteDescription = { type: "offer", sdp: desc.sdp! };
      this.signalingState = "have-remote-offer";
    } else {
      if (this.signalingState !== "have-local-offer") {
        throw domError("InvalidStateError", `answer in ${this.signalingState}`);
      }
      this.remoteDescription = { type: "answer", sdp: desc.sdp! };
      this.signalingState = "stable";
      this.completed();
    }
    if (!this.gotTrack && !desc.sdp!.endsWith("senders=0")) {
      this.gotTrack = true;
      const track = new FakeTrack();
      this.ontrack?.({ track, streams: [new FakeStream(`remote-of-${this.id}`, [track])] });
    }
  }

  async addIceCandidate(candidate: RTCIceCandidateInit): Promise<void> {
    await tick();
    if (!this.remoteDescription) throw domError("InvalidStateError", "no remote description");
    this.candidates.push(candidate);
  }

  close() {
    this.closed = true;
    this.signalingState = "closed";
    this.connectionState = "closed";
  }

  /** Simulate the network dropping; with `forGood`, an ICE restart doesn't help. */
  fail(forGood = false) {
    this.broken = forGood;
    this.connectionState = "failed";
    this.onconnectionstatechange?.();
  }

  private completed() {
    this.negotiated = this.senders.length;
    if (this.connectionState !== "connected" && !this.broken) {
      this.connectionState = "connected";
      this.onconnectionstatechange?.();
    }
    this.queueNegotiation();
  }

  private queueNegotiation() {
    if (this.negotiationQueued) return;
    this.negotiationQueued = true;
    setTimeout(() => {
      this.negotiationQueued = false;
      const needed = this.negotiated < this.senders.length || this.restartPending;
      if (!this.closed && needed && this.signalingState === "stable") this.onnegotiationneeded?.();
    }, 0);
  }
}

export interface FakeSink extends AudioSink {
  stream: FakeStream;
  removed: boolean;
  plays: number;
}

export class FakeEnv implements VoiceEnv {
  pcs: FakePeerConnection[] = [];
  sinks: FakeSink[] = [];
  streams: FakeStream[] = [];
  levels = new Map<FakeStream, number>();
  gestureCallbacks: (() => void)[] = [];
  iceRequests: string[] = [];
  mediaError: Error | null = null;
  autoplayAllowed = true;
  ice = { iceServers: [{ urls: ["turn:test"], username: "u", credential: "c" }], ttl: 100 };
  private ids = 0;

  constructor(readonly name: string) {}

  async getUserMedia(): Promise<MediaStream> {
    await tick();
    if (this.mediaError) throw this.mediaError;
    const stream = new FakeStream(`local-${this.name}`);
    this.streams.push(stream);
    return stream as unknown as MediaStream;
  }

  createPeerConnection(config: RTCConfiguration): RTCPeerConnection {
    const pc = new FakePeerConnection(config);
    this.pcs.push(pc);
    return pc as unknown as RTCPeerConnection;
  }

  async fetchIceConfig(player: string) {
    this.iceRequests.push(player);
    return this.ice;
  }

  createAudioSink(stream: MediaStream): AudioSink {
    const sink: FakeSink = {
      stream: stream as unknown as FakeStream,
      removed: false,
      plays: 0,
      play: async () => {
        sink.plays++;
        if (!this.autoplayAllowed) throw domError("NotAllowedError");
      },
      remove: () => {
        sink.removed = true;
      },
    };
    this.sinks.push(sink);
    return sink;
  }

  createMeter(stream: MediaStream): LevelMeter {
    const s = stream as unknown as FakeStream;
    return { level: () => this.levels.get(s) ?? 0, close() {} };
  }

  async resumeAudio() {}

  onUserGesture(callback: () => void) {
    this.gestureCallbacks.push(callback);
  }

  gesture() {
    const callbacks = this.gestureCallbacks.splice(0);
    for (const cb of callbacks) cb();
  }

  randomId() {
    return `${this.name}${++this.ids}`;
  }

  /** Open (not closed) peer connections. */
  open() {
    return this.pcs.filter((pc) => !pc.closed);
  }

  /** Audio sinks still playing. */
  playing() {
    return this.sinks.filter((s) => !s.removed);
  }
}

export interface FakeClient {
  id: string;
  env: FakeEnv;
  voice: VoiceController;
  sent: Record<string, unknown>[];
}

/**
 * The game server's voice part: tracks who is in voice, sends everyone the
 * player list after every change and relays signals, all asynchronously
 * with random delays but in order per connection, like a WebSocket.
 */
export class FakeServer {
  players: (VoicePlayer & { muted: boolean })[] = [];
  clients = new Map<string, FakeClient>();
  /** When false, state updates aren't delivered (to simulate lost messages). */
  deliverStates = true;
  private queues = new Map<string, Promise<void>>();

  constructor(
    private create: (send: (msg: object) => void, env: FakeEnv) => VoiceController,
    private random: () => number = Math.random,
  ) {}

  add(id: string): FakeClient {
    const env = new FakeEnv(id);
    const sent: Record<string, unknown>[] = [];
    const voice = this.create((msg) => {
      sent.push(msg as Record<string, unknown>);
      this.enqueue(`server<-${id}`, () => this.receive(id, msg as Record<string, unknown>));
    }, env);
    const client = { id, env, voice, sent };
    this.clients.set(id, client);
    this.players.push({ id, voice: false, muted: false });
    this.broadcast();
    return client;
  }

  remove(id: string) {
    this.clients.get(id)?.voice.leave();
    this.clients.delete(id);
    this.players = this.players.filter((p) => p.id !== id);
    this.broadcast();
  }

  /** The player's game socket reconnected: the server drops them from voice. */
  reconnect(id: string) {
    const player = this.players.find((p) => p.id === id)!;
    player.voice = false;
    this.broadcast();
  }

  broadcast() {
    if (!this.deliverStates) return;
    for (const client of this.clients.values()) {
      const snapshot = this.players.map((p) => ({ ...p }));
      this.enqueue(`client<-${client.id}`, () => client.voice.updatePeers(snapshot, client.id));
    }
  }

  /** Resolves once every queued message has been delivered and processed. */
  async settle(rounds = 50) {
    for (let i = 0; i < rounds; i++) {
      await Promise.all(this.queues.values());
      await new Promise((resolve) => setTimeout(resolve, 5));
    }
  }

  private receive(from: string, msg: Record<string, unknown>) {
    const player = this.players.find((p) => p.id === from);
    if (!player) return;
    switch (msg.type) {
      case "voice_join":
        player.voice = true;
        player.muted = false;
        this.broadcast();
        break;
      case "voice_leave":
        player.voice = false;
        this.broadcast();
        break;
      case "voice_mute":
        player.muted = msg.muted as boolean;
        this.broadcast();
        break;
      case "signal": {
        const target = this.players.find((p) => p.id === msg.to);
        const client = this.clients.get(msg.to as string);
        if (!player.voice || !target?.voice || !client) return; // not_in_voice
        this.enqueue(`client<-${client.id}`, () => client.voice.handleSignal(from, msg.data));
        break;
      }
    }
  }

  private enqueue(queue: string, fn: () => void) {
    const delay = Math.floor(this.random() * 4);
    const prev = this.queues.get(queue) ?? Promise.resolve();
    this.queues.set(
      queue,
      prev.then(() => new Promise<void>((resolve) => setTimeout(() => (fn(), resolve()), delay))),
    );
  }
}

/** Checks that every pair of clients in voice has one working connection. */
export function meshProblems(server: FakeServer): string[] {
  const problems: string[] = [];
  const inVoice = [...server.clients.values()].filter((c) =>
    server.players.find((p) => p.id === c.id && p.voice),
  );
  for (const client of inVoice) {
    const open = client.env.open();
    if (open.length !== inVoice.length - 1) {
      problems.push(`${client.id}: ${open.length} open connections, expected ${inVoice.length - 1}`);
    }
    for (const pc of open) {
      if (pc.signalingState !== "stable" || pc.connectionState !== "connected" || !pc.remoteDescription) {
        problems.push(`${client.id}: pc ${pc.id} is ${pc.signalingState}/${pc.connectionState}`);
      }
    }
    if (client.env.playing().length !== inVoice.length - 1) {
      problems.push(`${client.id}: plays ${client.env.playing().length} streams`);
    }
  }
  return problems;
}

/** A small seeded random generator, so failures can be reproduced. */
export function seeded(seed: number): () => number {
  return () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    return seed / 0x7fffffff;
  };
}
