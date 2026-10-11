<script lang="ts">
  // The lobby: invite link and code, the players filling up live, voice, and
  // the host's controls (options, CPU players, kick, start).
  import { t, tn } from "../i18n/index.svelte";
  import { copyText } from "../lib/clipboard";
  import { CPU_LEVELS, type CpuLevel, type StateMessage } from "../lib/protocol";
  import { act, conn, leaveRoom, voice } from "../lib/session.svelte";
  import { toast } from "../lib/toasts.svelte";
  import LangPicker from "./LangPicker.svelte";
  import VoiceControls from "./VoiceControls.svelte";

  let { room }: { room: StateMessage } = $props();
  const speaking = voice.speaking;

  const isHost = $derived(room.host === room.you);
  const link = $derived(`${location.origin}/j/${room.code}`);
  const canShare = typeof navigator !== "undefined" && "share" in navigator;
  let cpuLevel = $state<CpuLevel>("medium");

  const send = (msg: { type: string; [key: string]: unknown }) => act(() => conn.request(msg));

  async function copy() {
    if (await copyText(link)) toast(t("lobby.copied"));
    else toast(t("lobby.copy_failed"), "error");
  }

  async function share() {
    try {
      await navigator.share({ title: "Wild Joker", text: t("lobby.share_text"), url: link });
    } catch {
      // cancelled
    }
  }

  const setOptions = (decks: number, hand_size: number) => send({ type: "set_options", decks, hand_size });
</script>

<main class="lobby">
  <header class="bar">
    <h1>{t("lobby.title")}</h1>
    <span class="spacer"></span>
    <VoiceControls />
    <LangPicker />
  </header>

  <section class="panel invite">
    <p class="label">{t("lobby.code")}</p>
    <p class="code" data-testid="room-code">{room.code}</p>
    <p class="link-text" data-testid="invite-link">{link}</p>
    <div class="row">
      <button type="button" class="btn" onclick={copy} data-testid="copy-link">📋 {t("lobby.copy")}</button>
      {#if canShare}
        <button type="button" class="btn" onclick={share}>📤 {t("lobby.share")}</button>
      {/if}
    </div>
  </section>

  <section class="panel">
    <h2>{tn("lobby.players", room.players.length)}</h2>
    <ul class="players" data-testid="lobby-players">
      {#each room.players as p (p.id)}
        <li class:speaking={$speaking.has(p.id) && !p.muted}>
          <span class="avatar" aria-hidden="true">{p.cpu ? "🤖" : p.name.slice(0, 1).toUpperCase()}</span>
          <span class="who">
            <span class="name">{p.name}</span>
            <span class="tags">
              {#if p.id === room.host}<span class="tag host">{t("players.host")}</span>{/if}
              {#if p.id === room.you}<span class="tag">{t("players.you")}</span>{/if}
              {#if !p.connected}<span class="tag warn">{t("players.offline")}</span>{/if}
              {#if p.voice}<span class="tag">{p.muted ? "🔇 " + t("voice.muted") : "🎙 " + t("voice.in_voice")}</span>{/if}
            </span>
          </span>
          {#if p.cpu}
            {#if isHost}
              <select
                aria-label={t("lobby.cpu_level_for", { name: p.name })}
                value={p.cpu}
                onchange={(e) => send({ type: "set_cpu_level", player: p.id, level: e.currentTarget.value })}
              >
                {#each CPU_LEVELS as level (level)}<option value={level}>{t(`cpu.${level}`)}</option>{/each}
              </select>
            {:else}
              <span class="tag">{t(`cpu.${p.cpu}`)}</span>
            {/if}
          {/if}
          {#if isHost && p.id !== room.you}
            <button
              type="button"
              class="icon-btn danger"
              aria-label={(p.cpu ? t("lobby.remove") : t("lobby.kick")) + " " + p.name}
              title={p.cpu ? t("lobby.remove") : t("lobby.kick")}
              onclick={() => send({ type: "remove_player", player: p.id })}>✕</button
            >
          {/if}
        </li>
      {/each}
    </ul>
    {#if isHost}
      <div class="row add-cpu">
        <select aria-label={t("lobby.cpu_level")} bind:value={cpuLevel}>
          {#each CPU_LEVELS as level (level)}<option value={level}>{t(`cpu.${level}`)}</option>{/each}
        </select>
        <button
          type="button"
          class="btn"
          disabled={room.players.length >= 8}
          onclick={() => send({ type: "add_cpu", level: cpuLevel })}
          data-testid="add-cpu">🤖 {t("lobby.add_cpu")}</button
        >
      </div>
    {/if}
  </section>

  <section class="panel options">
    <h2>{t("lobby.options")}</h2>
    <div class="option">
      <span id="decks-label">{t("lobby.decks")}</span>
      {#if isHost}
        <div class="seg" role="radiogroup" aria-labelledby="decks-label">
          {#each [1, 2, 3] as n (n)}
            <button
              type="button"
              role="radio"
              aria-checked={room.options.decks === n}
              class:active={room.options.decks === n}
              onclick={() => setOptions(n, room.options.hand_size)}>{n}</button
            >
          {/each}
        </div>
      {:else}
        <strong>{room.options.decks}</strong>
      {/if}
    </div>
    <div class="option">
      <span id="hand-label">{t("lobby.hand_size")}</span>
      {#if isHost}
        <div class="stepper" role="group" aria-labelledby="hand-label">
          <button
            type="button"
            aria-label={t("lobby.fewer")}
            disabled={room.options.hand_size <= 1}
            onclick={() => setOptions(room.options.decks, room.options.hand_size - 1)}>−</button
          >
          <output aria-live="polite">{room.options.hand_size}</output>
          <button
            type="button"
            aria-label={t("lobby.more")}
            disabled={room.options.hand_size >= 15}
            onclick={() => setOptions(room.options.decks, room.options.hand_size + 1)}>+</button
          >
        </div>
      {:else}
        <strong>{room.options.hand_size}</strong>
      {/if}
    </div>
  </section>

  <footer class="actions">
    <button type="button" class="btn" onclick={leaveRoom}>{t("lobby.leave")}</button>
    {#if isHost}
      <button
        type="button"
        class="btn primary big"
        disabled={room.players.length < 2}
        onclick={() => send({ type: "start" })}
        data-testid="start">{t("lobby.start")}</button
      >
    {:else}
      <p class="wait">{t("lobby.waiting_for_host")}</p>
    {/if}
  </footer>
  {#if isHost && room.players.length < 2}
    <p class="hint">{t("lobby.need_players")}</p>
  {/if}
</main>

<style>
  .lobby {
    display: flex;
    flex-direction: column;
    gap: 12px;
    width: 100%;
    max-width: 560px;
    margin: 0 auto;
    padding: 8px 16px 24px;
  }
  .bar {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .bar h1 {
    margin: 0;
    font-size: 22px;
  }
  .spacer {
    flex: 1;
  }
  .panel {
    padding: 14px;
    border-radius: 14px;
    background: var(--panel);
  }
  h2 {
    margin: 0 0 8px;
    font-size: 16px;
  }
  .invite {
    text-align: center;
  }
  .label {
    margin: 0;
    color: var(--muted);
    font-size: 13px;
  }
  .code {
    margin: 2px 0;
    font-size: 44px;
    font-weight: 800;
    letter-spacing: 0.2em;
    font-variant-numeric: tabular-nums;
  }
  .link-text {
    margin: 0 0 10px;
    color: var(--muted);
    font-size: 14px;
    word-break: break-all;
  }
  .row {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 8px;
  }
  .players {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin: 0 0 10px;
    padding: 0;
    list-style: none;
  }
  .players li {
    display: flex;
    align-items: center;
    gap: 10px;
    min-height: 48px;
  }
  .avatar {
    display: grid;
    flex: none;
    place-items: center;
    width: 38px;
    height: 38px;
    border-radius: 50%;
    background: #33415c;
    font-weight: 700;
    transition: box-shadow 0.15s;
  }
  .speaking .avatar {
    box-shadow:
      0 0 0 3px #4ade80,
      0 0 10px #4ade80;
  }
  .who {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-width: 0;
  }
  .name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 600;
  }
  .tags {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .tag {
    padding: 0 6px;
    border-radius: 999px;
    background: rgb(255 255 255 / 0.1);
    color: var(--muted);
    font-size: 12px;
  }
  .tag.host {
    background: #6b4f00;
    color: #ffe08a;
  }
  .tag.warn {
    background: #5c1d22;
    color: #ffd6d9;
  }
  select {
    min-height: 44px;
    padding: 0 8px;
    border: 1px solid rgb(255 255 255 / 0.25);
    border-radius: 8px;
    background: #22304a;
    color: inherit;
    font: inherit;
  }
  .add-cpu {
    justify-content: flex-start;
  }
  .option {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    min-height: 52px;
  }
  .seg,
  .stepper {
    display: flex;
    overflow: hidden;
    border: 1px solid rgb(255 255 255 / 0.25);
    border-radius: 10px;
  }
  .seg button,
  .stepper button {
    min-width: 48px;
    min-height: 44px;
    border: 0;
    background: transparent;
    color: inherit;
    font: inherit;
    font-size: 18px;
    font-weight: 700;
    cursor: pointer;
  }
  .seg button.active {
    background: var(--accent);
    color: #fff;
  }
  .stepper button:disabled {
    opacity: 0.3;
  }
  .stepper output {
    display: grid;
    place-items: center;
    min-width: 40px;
    font-size: 18px;
    font-weight: 700;
  }
  .actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }
  .actions .primary {
    flex: 1;
  }
  .wait,
  .hint {
    margin: 0;
    color: var(--muted);
    text-align: center;
  }
</style>
