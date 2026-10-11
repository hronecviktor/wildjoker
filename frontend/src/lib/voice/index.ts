// Placeholder for the voice module (WebRTC), which is being written
// separately with exactly this interface. Until it lands, joining voice and
// muting only update the player list; no audio is sent.

import { writable, type Readable } from "svelte/store";

export interface VoiceController {
  join(): Promise<void>; // asks for the mic, sends voice_join, connects to peers
  leave(): void; // sends voice_leave, closes peers
  setMuted(muted: boolean): void; // mutes the local track, sends voice_mute
  handleSignal(from: string, data: unknown): void; // call for every incoming {type:"signal"}
  updatePeers(players: { id: string; voice: boolean }[], you: string): void; // call on every state
  speaking: Readable<Set<string>>; // player ids currently speaking
}

export function createVoice(send: (msg: object) => void): VoiceController {
  const speaking = writable(new Set<string>());
  return {
    async join() {
      send({ type: "voice_join" });
    },
    leave() {
      send({ type: "voice_leave" });
    },
    setMuted(muted) {
      send({ type: "voice_mute", muted });
    },
    handleSignal() {},
    updatePeers() {},
    speaking,
  };
}
