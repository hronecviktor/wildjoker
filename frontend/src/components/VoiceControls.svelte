<script lang="ts">
  // Join or leave voice chat, and mute.
  import { t } from "../i18n/index.svelte";
  import { conn, toggleMute, toggleVoice, voicePrefs } from "../lib/session.svelte";

  const me = $derived(conn.state?.players.find((p) => p.id === conn.you));
  const joined = $derived(!!me?.voice);
</script>

<button
  type="button"
  class="icon-btn"
  class:on={joined}
  aria-pressed={joined}
  aria-label={joined ? t("voice.leave") : t("voice.join")}
  title={joined ? t("voice.leave") : t("voice.join")}
  data-testid="voice"
  onclick={toggleVoice}
>
  <span aria-hidden="true">{joined ? "🎧" : "🎙"}</span>
  <span class="label">{joined ? t("voice.leave_short") : t("voice.join_short")}</span>
</button>
{#if joined}
  <button
    type="button"
    class="icon-btn"
    class:warn={voicePrefs.muted}
    aria-pressed={voicePrefs.muted}
    aria-label={voicePrefs.muted ? t("voice.unmute") : t("voice.mute")}
    title={(voicePrefs.muted ? t("voice.unmute") : t("voice.mute")) + " (M)"}
    data-testid="mute"
    onclick={toggleMute}
  >
    <span aria-hidden="true">{voicePrefs.muted ? "🔇" : "🔊"}</span>
  </button>
{/if}
