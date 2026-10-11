<script lang="ts">
  // The end of a game: finishing order, and the host can go back to the lobby.
  import { t } from "../i18n/index.svelte";
  import type { StateMessage } from "../lib/protocol";
  import { act, conn, leaveRoom } from "../lib/session.svelte";
  import LangPicker from "./LangPicker.svelte";
  import VoiceControls from "./VoiceControls.svelte";

  let { room }: { room: StateMessage } = $props();

  const isHost = $derived(room.host === room.you);
  const name = (id: string) => room.players.find((p) => p.id === id)?.name ?? "?";
  const places = $derived(room.game?.places ?? []);
  const medals = ["🥇", "🥈", "🥉"];
  // Numbered like players[].place: players sharing a place (a draw) share the number.
  const numbered = $derived(places.map((ids, i) => ({ place: i + 1, ids })));
</script>

<main class="finished">
  <header class="bar">
    <h1>{t("finished.title")}</h1>
    <span class="spacer"></span>
    <VoiceControls />
    <LangPicker />
  </header>

  <ol class="places" data-testid="places">
    {#each numbered as { place, ids } (place)}
      <li class:me={ids.includes(room.you)}>
        <span class="medal" aria-hidden="true">{medals[place - 1] ?? place + "."}</span>
        <span class="names">
          <span class="sr-only">{t("players.place", { place })}:</span>
          {ids.map(name).join(", ")}
          {#if ids.length > 1}<span class="draw">{t("finished.shared")}</span>{/if}
        </span>
      </li>
    {/each}
  </ol>

  <footer class="actions">
    <button type="button" class="btn" onclick={leaveRoom}>{t("lobby.leave")}</button>
    {#if isHost}
      <button
        type="button"
        class="btn primary big"
        data-testid="back-to-lobby"
        onclick={() => act(() => conn.request({ type: "back_to_lobby" }))}>{t("finished.back_to_lobby")}</button
      >
    {:else}
      <p class="wait">{t("finished.waiting_for_host")}</p>
    {/if}
  </footer>
</main>

<style>
  .finished {
    display: flex;
    flex-direction: column;
    gap: 16px;
    width: 100%;
    max-width: 520px;
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
    font-size: 24px;
  }
  .spacer {
    flex: 1;
  }
  .places {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .places li {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 14px;
    border-radius: 12px;
    background: var(--panel);
    font-size: 18px;
  }
  .places li.me {
    outline: 2px solid var(--accent);
  }
  .medal {
    width: 36px;
    font-size: 26px;
    text-align: center;
  }
  .draw {
    margin-left: 6px;
    color: var(--muted);
    font-size: 14px;
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
  .wait {
    margin: 0;
    color: var(--muted);
  }
</style>
