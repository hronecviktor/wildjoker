// The app's single connection and voice controller, wired together.

import { errorText, t } from "../i18n/index.svelte";
import { Connection, ServerError } from "./connection.svelte";
import { load, save } from "./storage";
import { toast } from "./toasts.svelte";
import { createVoice, VoiceError } from "./voice";

export const conn = new Connection();
export const voice = createVoice(conn.send);

/** Whether the player is in voice and muted. The voice module itself rejoins after a reconnect. */
export const voicePrefs = $state({ wanted: false, muted: load("muted", false) });

conn.onSignal = (s) => voice.handleSignal(s.from, s.data);

conn.onEvent = (e) => {
  const name = (id?: string) => conn.state?.players.find((p) => p.id === id)?.name ?? "?";
  switch (e.kind) {
    case "went_out": {
      const place = conn.state?.players.find((p) => p.id === e.player)?.place;
      const you = e.player === conn.you;
      toast(you ? t("event.went_out_you") : t("event.went_out", { name: name(e.player), place: place ?? "" }));
      break;
    }
    case "kicked":
      stopVoice();
      conn.forget();
      history.replaceState(null, "", "/");
      toast(t("event.kicked"), "error", 6000);
      break;
    default:
      toast(t(`event.${e.kind}`));
  }
};

conn.onLost = (_code, error) => {
  stopVoice();
  history.replaceState(null, "", "/");
  toast(errorText(error), "error", 6000);
};

export async function joinVoice(): Promise<void> {
  voicePrefs.wanted = true;
  try {
    voice.setMuted(voicePrefs.muted); // kept by the module through the join
    await voice.join();
  } catch (e) {
    voicePrefs.wanted = false;
    const code = e instanceof VoiceError ? e.code : "failed";
    toast(t(`voice.error.${code}`), "error", 6000);
  }
}

/** Leave voice when leaving the room (left, kicked, room gone). */
function stopVoice(): void {
  if (voicePrefs.wanted || inVoice()) voice.leave();
  voicePrefs.wanted = false;
}

/** Leave the room for good, and voice with it. */
export async function leaveRoom(): Promise<void> {
  stopVoice();
  await act(() => conn.leave());
  history.replaceState(null, "", "/");
}

export function leaveVoice(): void {
  voicePrefs.wanted = false;
  voice.leave();
}

export function toggleVoice(): void {
  if (inVoice()) leaveVoice();
  else void joinVoice();
}

export function toggleMute(): void {
  if (!inVoice()) return;
  voicePrefs.muted = !voicePrefs.muted;
  save("muted", voicePrefs.muted);
  voice.setMuted(voicePrefs.muted);
}

export function inVoice(): boolean {
  return !!conn.state?.players.find((p) => p.id === conn.you)?.voice;
}

/** Run a request, showing a translated toast for server errors. */
export async function act<T>(fn: () => Promise<T>): Promise<T | undefined> {
  try {
    return await fn();
  } catch (e) {
    if (e instanceof ServerError) toast(errorText(e.code), "error");
    else throw e;
  }
}
