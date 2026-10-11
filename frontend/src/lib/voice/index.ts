// Voice chat: full-mesh WebRTC audio between the players in a room, with the
// game WebSocket relaying the connection setup. See README.md.

export { createVoice, VoiceError } from "./controller";
export type { VoiceController, VoiceErrorCode, VoicePlayer } from "./controller";
