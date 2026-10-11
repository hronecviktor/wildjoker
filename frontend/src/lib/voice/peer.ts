// One WebRTC connection to another player, set up with "perfect negotiation"
// (https://w3c.github.io/webrtc-pc/#perfect-negotiation-example): both sides
// may send offers at any time; when two offers cross, the polite side rolls
// its own back and answers, the impolite side ignores the incoming one.

import type { VoiceEnv } from "./env";

/** What travels in `{type: "signal", data}`. */
export interface SignalData {
  /** Id of the sender's connection; a new one means a fresh connection. */
  sid: string;
  /** The receiver's connection this is meant for, once the sender knows it. */
  to?: string;
  description?: RTCSessionDescriptionInit;
  candidate?: RTCIceCandidateInit;
}

export function parseSignal(data: unknown): SignalData | null {
  if (typeof data !== "object" || data === null) return null;
  const d = data as Record<string, unknown>;
  if (typeof d.sid !== "string") return null;
  if (d.to !== undefined && typeof d.to !== "string") return null;
  const description = d.description as RTCSessionDescriptionInit | undefined;
  if (description !== undefined) {
    if (typeof description !== "object" || description === null) return null;
    if (description.type !== "offer" && description.type !== "answer") return null;
  }
  const candidate = d.candidate as RTCIceCandidateInit | undefined;
  if (candidate !== undefined && (typeof candidate !== "object" || candidate === null)) return null;
  if (!description && !candidate) return null;
  return d as unknown as SignalData;
}

export interface PeerEvents {
  signal(data: SignalData): void;
  stream(stream: MediaStream): void;
  /** The connection is beyond repair; replace it with a new one. */
  failed(): void;
}

export const timing = {
  /** How long (ms) a connection may stay failed after an ICE restart before it is replaced. */
  failedTimeout: 10_000,
};

export class Peer {
  readonly sid: string;
  remoteSid: string | null = null;
  readonly pc: RTCPeerConnection;
  stream: MediaStream | null = null;
  closed = false;

  private makingOffer = false;
  private ignoreOffer = false;
  private settingRemoteAnswer = false;
  private queue: Promise<void> = Promise.resolve();
  private failedTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    readonly id: string,
    readonly polite: boolean,
    env: VoiceEnv,
    config: RTCConfiguration,
    local: MediaStream,
    private events: PeerEvents,
  ) {
    this.sid = env.randomId();
    const pc = (this.pc = env.createPeerConnection(config));

    pc.onnegotiationneeded = async () => {
      try {
        this.makingOffer = true;
        await pc.setLocalDescription();
        if (pc.localDescription) this.send({ description: pc.localDescription.toJSON() });
      } catch (e) {
        if (!this.closed) console.warn("voice: offer to", this.id, "failed", e);
      } finally {
        this.makingOffer = false;
      }
    };

    pc.onicecandidate = ({ candidate }) => {
      if (candidate) this.send({ candidate: candidate.toJSON() });
    };

    pc.ontrack = ({ track, streams }) => {
      this.stream = streams[0] ?? new MediaStream([track]);
      this.events.stream(this.stream);
    };

    pc.onconnectionstatechange = () => this.checkConnection();

    for (const track of local.getAudioTracks()) pc.addTrack(track, local);
  }

  /** Handle one signal from the other side; signals are applied in order. */
  handle(data: SignalData): Promise<void> {
    this.queue = this.queue.then(() => this.apply(data)).catch((e) => {
      if (!this.closed) console.warn("voice: signal from", this.id, "failed", e);
    });
    return this.queue;
  }

  setConfiguration(config: RTCConfiguration): void {
    try {
      this.pc.setConfiguration(config);
    } catch (e) {
      console.warn("voice: could not update ICE servers", e);
    }
  }

  close(): void {
    if (this.closed) return;
    this.closed = true;
    if (this.failedTimer) clearTimeout(this.failedTimer);
    this.pc.onnegotiationneeded = this.pc.onicecandidate = null;
    this.pc.ontrack = this.pc.onconnectionstatechange = null;
    this.pc.close();
  }

  private async apply({ sid, description, candidate }: SignalData): Promise<void> {
    if (this.closed) return;
    this.remoteSid ??= sid;
    const pc = this.pc;
    if (description) {
      const readyForOffer =
        !this.makingOffer && (pc.signalingState === "stable" || this.settingRemoteAnswer);
      const collision = description.type === "offer" && !readyForOffer;
      this.ignoreOffer = !this.polite && collision;
      if (this.ignoreOffer) return;
      this.settingRemoteAnswer = description.type === "answer";
      try {
        await pc.setRemoteDescription(description); // rolls our offer back on a collision
      } finally {
        this.settingRemoteAnswer = false;
      }
      if (description.type === "offer") {
        await pc.setLocalDescription();
        if (pc.localDescription) this.send({ description: pc.localDescription.toJSON() });
      }
    } else if (candidate) {
      try {
        await pc.addIceCandidate(candidate);
      } catch (e) {
        if (!this.ignoreOffer) throw e; // candidates for an offer we ignored don't matter
      }
    }
  }

  private send(data: Omit<SignalData, "sid" | "to">): void {
    if (this.closed) return;
    this.events.signal({ sid: this.sid, ...(this.remoteSid ? { to: this.remoteSid } : {}), ...data });
  }

  private checkConnection(): void {
    const state = this.pc.connectionState;
    if (state === "failed") {
      // Networks change (Wi-Fi to mobile data): try new candidates first.
      this.pc.restartIce();
      this.failedTimer ??= setTimeout(() => {
        this.failedTimer = null;
        if (!this.closed && this.pc.connectionState !== "connected") this.events.failed();
      }, timing.failedTimeout);
    } else if (state === "connected" && this.failedTimer) {
      clearTimeout(this.failedTimer);
      this.failedTimer = null;
    }
  }
}
