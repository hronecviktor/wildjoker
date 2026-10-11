// Placeholder for the voice module (WebRTC) from the voice branch, with the
// same exports. When merging, take that branch's version of this directory.
// Until then, joining voice and muting only update the player list; no audio
// is sent.

import { writable, type Readable } from "svelte/store";

export type VoiceErrorCode =
  | "permission_denied"
  | "no_device"
  | "device_busy"
  | "insecure_context"
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
  muted?: boolean;
}

export interface VoiceController {
  join(): Promise<void>; // asks for the mic, sends voice_join, connects to peers
  leave(): void; // sends voice_leave, closes peers
  setMuted(muted: boolean): void; // mutes the local track, sends voice_mute; works before join
  handleSignal(from: string, data: unknown): void; // call for every incoming {type:"signal"}
  updatePeers(players: VoicePlayer[], you: string): void; // call on every state
  speaking: Readable<Set<string>>; // player ids currently speaking
  playbackBlocked: Readable<boolean>; // remote audio waits for a click or key press
}

export function createVoice(send: (msg: object) => void): VoiceController {
  const speaking = writable(new Set<string>());
  const playbackBlocked = writable(false);
  let muted = false;
  return {
    async join() {
      send({ type: "voice_join" });
      if (muted) send({ type: "voice_mute", muted });
    },
    leave() {
      send({ type: "voice_leave" });
    },
    setMuted(value) {
      muted = value;
      send({ type: "voice_mute", muted });
    },
    handleSignal() {},
    updatePeers() {},
    speaking,
    playbackBlocked,
  };
}
