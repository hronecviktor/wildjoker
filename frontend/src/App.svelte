<script lang="ts">
  import Finished from "./components/Finished.svelte";
  import Game from "./components/Game.svelte";
  import GinGame from "./components/GinGame.svelte";
  import Lobby from "./components/Lobby.svelte";
  import Start from "./components/Start.svelte";
  import { errorText, t } from "./i18n/index.svelte";
  import { ServerError } from "./lib/connection.svelte";
  import { conn, voice } from "./lib/session.svelte";
  import { sessions } from "./lib/storage";
  import { dismiss, toast, toasts } from "./lib/toasts.svelte";

  const playbackBlocked = voice.playbackBlocked;
  const parseInvite = () => /^\/j\/([A-Za-z]{4})\/?$/.exec(location.pathname)?.[1].toUpperCase() ?? null;

  let invite = $state(parseInvite());
  let resuming = $state(false);

  // Take our seat back after a reload: the room from the invite link, or the last one.
  async function resumeOnLoad() {
    const code = invite ?? sessions.last();
    const token = code && sessions.get(code);
    if (!code || !token) return;
    resuming = true;
    try {
      await conn.resume(code, token);
      history.replaceState(null, "", `/j/${code}`);
      resuming = false;
    } catch (e) {
      if (!(e instanceof ServerError)) throw e;
      if (e.code === "disconnected") {
        // The server is unreachable; keep the token and try again.
        setTimeout(resumeOnLoad, 3000);
        return;
      }
      resuming = false;
      conn.forget(code);
      if (e.code === "no_room" && invite) {
        invite = null;
        history.replaceState(null, "", "/");
        toast(errorText("no_room"), "error", 6000);
      }
    }
  }
  resumeOnLoad();

  // Back on the start screen after leaving or being kicked.
  $effect(() => {
    if (!conn.code) invite = parseInvite();
  });

  $effect(() => {
    const s = conn.state;
    if (s) voice.updatePeers(s.players, s.you);
  });
</script>

{#if conn.code && conn.state}
  {#if conn.state.phase === "lobby"}
    <Lobby room={conn.state} />
  {:else if conn.state.phase === "playing" && conn.state.game?.kind === "gin"}
    <GinGame />
  {:else if conn.state.phase === "playing" && conn.state.game}
    <Game />
  {:else}
    <Finished room={conn.state} />
  {/if}
{:else if resuming || conn.code}
  <p class="loading">{t("app.connecting")}</p>
{:else}
  <Start {invite} />
{/if}

{#if conn.code && conn.status === "reconnecting"}
  <div class="reconnecting" role="status" data-testid="reconnecting">
    <span class="dot" aria-hidden="true"></span>{t("app.reconnecting")}
  </div>
{/if}

{#if conn.status === "replaced"}
  <div class="replaced" role="alertdialog" aria-labelledby="replaced-text">
    <div class="panel">
      <p id="replaced-text">{t("app.replaced")}</p>
      <button type="button" class="btn primary" onclick={() => conn.takeOver()}>{t("app.play_here")}</button>
    </div>
  </div>
{/if}

{#if $playbackBlocked}
  <!-- The voice module resumes audio on the next click or key press anywhere. -->
  <button type="button" class="playback" data-testid="playback-blocked">🔈 {t("voice.tap_to_hear")}</button>
{/if}

<div class="toasts" aria-live="polite">
  {#each toasts as toast (toast.id)}
    <button type="button" class="toast {toast.kind}" onclick={() => dismiss(toast.id)}>{toast.text}</button>
  {/each}
</div>

<style>
  .loading {
    margin: 40vh auto 0;
    color: var(--muted);
    text-align: center;
  }
  .reconnecting {
    position: fixed;
    left: 50%;
    top: 8px;
    z-index: 200;
    display: flex;
    align-items: center;
    gap: 8px;
    transform: translateX(-50%);
    padding: 6px 12px;
    border-radius: 999px;
    background: #6b4f00;
    color: #ffe08a;
    font-size: 14px;
    font-weight: 600;
    box-shadow: 0 2px 8px rgb(0 0 0 / 0.4);
  }
  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: currentColor;
    animation: pulse 1s infinite alternate;
  }
  @keyframes pulse {
    to {
      opacity: 0.2;
    }
  }
  .replaced {
    position: fixed;
    inset: 0;
    z-index: 300;
    display: grid;
    place-items: center;
    padding: 16px;
    background: rgb(0 0 0 / 0.6);
  }
  .replaced .panel {
    max-width: 360px;
    padding: 18px;
    border-radius: 14px;
    background: #1b2a43;
    text-align: center;
  }
  .playback {
    position: fixed;
    left: 50%;
    bottom: 16px;
    z-index: 220;
    transform: translateX(-50%);
    min-height: 44px;
    padding: 0 16px;
    border: 0;
    border-radius: 999px;
    background: #2f6fe4;
    color: #fff;
    font: inherit;
    font-weight: 600;
    box-shadow: 0 4px 14px rgb(0 0 0 / 0.45);
  }
  .toasts {
    position: fixed;
    left: 50%;
    top: 48px;
    z-index: 250;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    width: min(420px, calc(100vw - 32px));
    transform: translateX(-50%);
    pointer-events: none;
  }
  .toast {
    pointer-events: auto;
    padding: 10px 14px;
    border: 0;
    border-radius: 10px;
    background: #22304a;
    color: #fff;
    font: inherit;
    font-size: 15px;
    box-shadow: 0 4px 14px rgb(0 0 0 / 0.45);
  }
  .toast.error {
    background: #8c1c2d;
  }
</style>
