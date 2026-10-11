import { type Readable, writable } from "svelte/store";
import { browserEnv, DEFAULT_ICE, type AudioSink, type IceConfig, type LevelMeter, type VoiceEnv } from "./env";
import { parseSignal, Peer, type SignalData } from "./peer";
import { SAMPLE_INTERVAL, SpeakingDetector } from "./speaking";

export type VoiceErrorCode =
  /** The user (or a browser policy) refused microphone access. */
  | "permission_denied"
  /** There is no microphone. */
  | "no_device"
  /** The microphone is in use by another app or couldn't be started. */
  | "device_busy"
  /** The page isn't served over HTTPS (or localhost). */
  | "insecure_context"
  /** The browser has no WebRTC or getUserMedia. */
  | "unsupported"
  | "failed";

export class VoiceError extends Error {
  constructor(
    readonly code: VoiceErrorCode,
    options?: { cause?: unknown },
  ) {
    super(`voice: ${code}`, options);
    this.name = "VoiceError";
  }
}

export interface VoicePlayer {
  id: string;
  voice: boolean;
  /** When true, the player is never shown as speaking. */
  muted?: boolean;
}

export interface VoiceController {
  /** Asks for the mic, sends voice_join, connects to peers. Rejects with a VoiceError. */
  join(): Promise<void>;
  /** Sends voice_leave, closes peers. */
  leave(): void;
  /** Mutes the local track, sends voice_mute. Can be set before joining. */
  setMuted(muted: boolean): void;
  /** Called for every incoming {type: "signal"}. */
  handleSignal(from: string, data: unknown): void;
  /** Called on every state. */
  updatePeers(players: VoicePlayer[], you: string): void;
  /** Player ids currently speaking. */
  speaking: Readable<Set<string>>;
  /** True while remote audio can't play until the user clicks or presses a key. */
  playbackBlocked: Readable<boolean>;
}

const CONSTRAINTS: MediaStreamConstraints = {
  audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  video: false,
};

/** Re-send voice_join if the server still hasn't put us in voice after this long. */
const JOIN_RETRY = 3000;

interface Remote {
  peer: Peer;
  sink: AudioSink | null;
  meter: LevelMeter | null;
  detector: SpeakingDetector;
}

export function createVoice(send: (msg: object) => void, env: VoiceEnv = browserEnv()): VoiceController {
  const speaking = writable(new Set<string>());
  const playbackBlocked = writable(false);

  let you: string | null = null;
  let players: VoicePlayer[] = [];
  let muted = false;

  // Joining: `joining` while waiting for the mic, then `local` is set.
  let joining: Promise<void> | null = null;
  let generation = 0;
  let local: MediaStream | null = null;
  let localMeter: LevelMeter | null = null;
  const localDetector = new SpeakingDetector();
  let ice: IceConfig = DEFAULT_ICE;
  let iceTimer: ReturnType<typeof setTimeout> | null = null;
  // When we last sent voice_join that the server hasn't confirmed yet.
  let joinSentAt: number | null = null;
  let sampler: ReturnType<typeof setInterval> | null = null;

  const remotes = new Map<string, Remote>();
  // Connection ids of other players' closed connections, to drop late signals.
  const retired = new Map<string, Set<string>>();
  const blocked = new Set<AudioSink>();

  // -- joining and leaving --------------------------------------------------

  function join(): Promise<void> {
    if (local) return Promise.resolve();
    if (joining) return joining;
    const gen = ++generation;
    const attempt = (async () => {
      let stream: MediaStream;
      try {
        const [media, config] = await Promise.all([env.getUserMedia(CONSTRAINTS), fetchIce()]);
        stream = media;
        ice = config ?? DEFAULT_ICE;
      } catch (e) {
        throw toVoiceError(e);
      }
      if (gen !== generation) {
        // leave() was called while we were waiting for the mic.
        stopTracks(stream);
        return;
      }
      local = stream;
      refreshIceIn(ice === DEFAULT_ICE ? 1 : Math.max(60, ice.ttl * 0.8));
      for (const track of stream.getAudioTracks()) track.enabled = !muted;
      localMeter = env.createMeter(stream);
      sampler = setInterval(sample, SAMPLE_INTERVAL);
      sendJoin();
      reconcile();
    })();
    joining = attempt;
    attempt.then(
      () => joining === attempt && (joining = null),
      () => joining === attempt && (joining = null),
    );
    return attempt;
  }

  function leave(): void {
    generation++;
    joining = null;
    const wasJoined = local !== null;
    for (const id of [...remotes.keys()]) closeRemote(id);
    if (local) stopTracks(local);
    local = null;
    localMeter?.close();
    localMeter = null;
    localDetector.reset();
    if (sampler) clearInterval(sampler);
    sampler = null;
    if (iceTimer) clearTimeout(iceTimer);
    iceTimer = null;
    joinSentAt = null;
    blocked.clear();
    playbackBlocked.set(false);
    publishSpeaking();
    if (wasJoined) send({ type: "voice_leave" });
  }

  function sendJoin(): void {
    joinSentAt = Date.now();
    send({ type: "voice_join" });
    // The server unmutes on voice_join.
    if (muted) send({ type: "voice_mute", muted: true });
  }

  function setMuted(value: boolean): void {
    muted = value;
    if (!local) return;
    for (const track of local.getAudioTracks()) track.enabled = !muted;
    if (muted) localDetector.reset();
    publishSpeaking();
    send({ type: "voice_mute", muted });
  }

  // -- ICE servers --------------------------------------------------------

  async function fetchIce(): Promise<IceConfig | null> {
    if (!you) return null;
    try {
      return await env.fetchIceConfig(you);
    } catch (e) {
      console.warn("voice: no ICE config from the server, using STUN only", e);
      return null;
    }
  }

  /** Fetch new TURN credentials in `seconds`, well before the old ones expire. */
  function refreshIceIn(seconds: number): void {
    if (iceTimer) clearTimeout(iceTimer);
    iceTimer = setTimeout(async () => {
      iceTimer = null;
      const gen = generation;
      const config = await fetchIce();
      if (gen !== generation || iceTimer) return;
      if (config) {
        ice = config;
        for (const { peer } of remotes.values()) peer.setConfiguration({ iceServers: ice.iceServers });
      }
      refreshIceIn(config ? Math.max(60, ice.ttl * 0.8) : 30);
    }, seconds * 1000);
  }

  // -- peers ------------------------------------------------------------------

  function updatePeers(list: VoicePlayer[], me: string): void {
    if (me !== you) {
      // Another seat (or room): nothing carries over.
      for (const id of [...remotes.keys()]) closeRemote(id);
      retired.clear();
      you = me;
      if (local || joining) refreshIceIn(0);
    }
    players = list;
    reconcile();
  }

  function reconcile(): void {
    const self = players.find((p) => p.id === you);
    const inVoice = !!(local && self?.voice);
    if (local && self) {
      if (self.voice) {
        joinSentAt = null;
      } else if (joinSentAt === null || Date.now() - joinSentAt > JOIN_RETRY) {
        // The server dropped us from voice (a reconnect of the game socket)
        // or never got our voice_join: ask again.
        sendJoin();
      }
    }
    const wanted = new Set(inVoice ? players.filter((p) => p.voice && p.id !== you).map((p) => p.id) : []);
    for (const id of [...remotes.keys()]) if (!wanted.has(id)) closeRemote(id);
    for (const id of wanted) if (!remotes.has(id)) openRemote(id);
    publishSpeaking();
  }

  function openRemote(id: string): Remote | null {
    if (!local || !you) return null;
    const remote: Remote = { peer: null!, sink: null, meter: null, detector: new SpeakingDetector() };
    remote.peer = new Peer(id, you < id, env, { iceServers: ice.iceServers }, local, {
      signal: (data) => send({ type: "signal", to: id, data }),
      stream: (stream) => attachStream(remote, stream),
      failed: () => {
        // Only one side replaces the connection; the other follows when it sees the new sid.
        if (!remote.peer.polite && remotes.get(id) === remote) {
          closeRemote(id);
          openRemote(id);
        }
      },
    });
    remotes.set(id, remote);
    return remote;
  }

  function closeRemote(id: string): void {
    const remote = remotes.get(id);
    if (!remote) return;
    remotes.delete(id);
    if (remote.peer.remoteSid) {
      const set = retired.get(id) ?? new Set();
      set.add(remote.peer.remoteSid);
      retired.set(id, set);
    }
    remote.peer.close();
    remote.meter?.close();
    if (remote.sink) {
      blocked.delete(remote.sink);
      remote.sink.remove();
    }
    if (blocked.size === 0) playbackBlocked.set(false);
  }

  function attachStream(remote: Remote, stream: MediaStream): void {
    if (remote.sink) {
      blocked.delete(remote.sink);
      remote.sink.remove();
    }
    remote.meter?.close();
    remote.sink = env.createAudioSink(stream);
    remote.meter = env.createMeter(stream);
    play(remote.sink);
  }

  function play(sink: AudioSink): void {
    sink.play().then(
      () => {
        blocked.delete(sink);
        if (blocked.size === 0) playbackBlocked.set(false);
      },
      (e: unknown) => {
        if ((e as { name?: string })?.name !== "NotAllowedError") return;
        // Autoplay policy: wait for a click or key press, then try again.
        if (blocked.size === 0) env.onUserGesture(retryPlayback);
        blocked.add(sink);
        playbackBlocked.set(true);
      },
    );
  }

  function retryPlayback(): void {
    env.resumeAudio().catch(() => {});
    for (const sink of [...blocked]) {
      blocked.delete(sink);
      play(sink);
    }
  }

  function handleSignal(from: string, raw: unknown): void {
    const data = parseSignal(raw);
    if (!data || !local || from === you) return;
    if (retired.get(from)?.has(data.sid)) return; // from a connection that's gone
    let remote = remotes.get(from);
    if (remote && data.to && data.to !== remote.peer.sid) return; // meant for our old connection
    if (remote?.peer.remoteSid && remote.peer.remoteSid !== data.sid) {
      // They started a new connection (rejoined, or replaced a failed one).
      closeRemote(from);
      remote = undefined;
    }
    if (!remote) {
      if (data.to) return;
      // The server only relays between players in voice, so this is a new
      // peer even if no state has told us yet; the next state corrects it.
      remote = openRemote(from) ?? undefined;
      if (!remote) return;
    }
    remote.peer.handle(data);
  }

  // -- speaking -----------------------------------------------------------------

  function sample(): void {
    const now = Date.now();
    if (localMeter) localDetector.update(muted ? 0 : localMeter.level(), now);
    for (const remote of remotes.values()) {
      if (remote.meter) remote.detector.update(remote.meter.level(), now);
    }
    publishSpeaking();
  }

  function publishSpeaking(): void {
    const next = new Set<string>();
    if (you && local && !muted && localDetector.speaking) next.add(you);
    for (const [id, remote] of remotes) {
      const player = players.find((p) => p.id === id);
      if (remote.detector.speaking && !player?.muted) next.add(id);
    }
    speaking.update((current) => (sameSet(current, next) ? current : next));
  }

  return {
    join,
    leave,
    setMuted,
    handleSignal,
    updatePeers,
    speaking: { subscribe: speaking.subscribe },
    playbackBlocked: { subscribe: playbackBlocked.subscribe },
  };
}

function toVoiceError(e: unknown): VoiceError {
  if (e instanceof VoiceError) return e;
  const name = (e as { name?: string })?.name;
  const code: VoiceErrorCode =
    name === "NotAllowedError" || name === "PermissionDeniedError"
      ? "permission_denied"
      : name === "SecurityError"
        ? "insecure_context"
        : name === "NotFoundError" || name === "OverconstrainedError" || name === "DevicesNotFoundError"
          ? "no_device"
          : name === "NotReadableError" || name === "AbortError" || name === "TrackStartError"
            ? "device_busy"
            : name === "NotSupportedError" || e instanceof TypeError
              ? "unsupported"
              : "failed";
  return new VoiceError(code, { cause: e });
}

function stopTracks(stream: MediaStream): void {
  for (const track of stream.getTracks()) track.stop();
}

function sameSet(a: Set<string>, b: Set<string>): boolean {
  return a.size === b.size && [...a].every((x) => b.has(x));
}

export type { SignalData };
