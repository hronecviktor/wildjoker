<script lang="ts">
  // Everyone at the table: card counts, opened status, places, voice.
  import { t, tn } from "../i18n/index.svelte";
  import type { PlayerView } from "../lib/protocol";
  import { voice } from "../lib/session.svelte";

  let { players, you, host }: { players: PlayerView[]; you: string | null; host: string | null } = $props();
  const speaking = voice.speaking;

  function describe(p: PlayerView): string {
    const parts = [p.name];
    if (p.id === you) parts.push(t("players.you"));
    if (p.cpu) parts.push(t(`cpu.${p.cpu}`));
    if (p.place) parts.push(t("players.place", { place: p.place }));
    else if (p.cards !== undefined) parts.push(tn("players.cards", p.cards));
    if (p.opened === false) parts.push(t("players.not_opened"));
    if (!p.connected) parts.push(t("players.offline"));
    if (p.voice) parts.push(p.muted ? t("voice.muted") : t("voice.in_voice"));
    if ($speaking.has(p.id)) parts.push(t("voice.speaking"));
    return parts.join(", ");
  }
</script>

<ul class="strip" aria-label={t("players.title")}>
  {#each players as p (p.id)}
    <li
      class="player"
      class:me={p.id === you}
      class:offline={!p.connected}
      class:speaking={$speaking.has(p.id) && !p.muted}
      class:out={!!p.place}
      aria-label={describe(p)}
      data-testid="player"
    >
      <span class="avatar" aria-hidden="true">
        {p.cpu ? "🤖" : p.name.slice(0, 1).toUpperCase()}
        {#if p.place}
          <span class="badge place">{p.place}</span>
        {:else if p.cards !== undefined}
          <span class="badge" data-testid="card-count">{p.cards}</span>
        {/if}
      </span>
      <span class="name" aria-hidden="true">
        {#if p.id === host}<span title={t("players.host")}>👑</span>{/if}{p.name}
      </span>
      <span class="icons" aria-hidden="true">
        {#if p.opened}<span class="opened" title={t("players.opened")}>✓</span>{/if}
        {#if p.voice}<span>{p.muted ? "🔇" : "🎙"}</span>{/if}
        {#if !p.connected}<span>⚠</span>{/if}
      </span>
    </li>
  {/each}
</ul>

<style>
  .strip {
    display: flex;
    gap: 6px;
    margin: 0;
    padding: 6px 10px;
    list-style: none;
    overflow-x: auto;
    scrollbar-width: none;
  }
  .player {
    display: flex;
    flex-direction: column;
    align-items: center;
    flex: none;
    min-width: 58px;
    max-width: 84px;
    font-size: 12px;
  }
  .avatar {
    position: relative;
    display: grid;
    place-items: center;
    width: 38px;
    height: 38px;
    border-radius: 50%;
    background: #33415c;
    color: #fff;
    font-size: 17px;
    font-weight: 700;
    box-shadow: 0 0 0 2px transparent;
    transition: box-shadow 0.15s;
  }
  .me .avatar {
    background: #2958c9;
  }
  .speaking .avatar {
    box-shadow:
      0 0 0 3px #4ade80,
      0 0 10px #4ade80;
  }
  .offline .avatar,
  .out .avatar {
    opacity: 0.5;
  }
  .badge {
    position: absolute;
    right: -8px;
    bottom: -4px;
    min-width: 22px;
    height: 20px;
    padding: 0 5px;
    border-radius: 999px;
    background: #fff;
    color: #1d2330;
    font-size: 12px;
    line-height: 20px;
    text-align: center;
    font-weight: 800;
    box-shadow: 0 1px 2px rgb(0 0 0 / 0.4);
  }
  .badge.place {
    background: #f5b301;
  }
  .name {
    max-width: 100%;
    margin-top: 3px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .icons {
    display: flex;
    gap: 3px;
    min-height: 15px;
    font-size: 11px;
    line-height: 15px;
  }
  .opened {
    color: #4ade80;
    font-weight: 800;
  }
</style>
