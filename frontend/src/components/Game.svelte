<script lang="ts">
  // The game table: players, table piles, the staging sheet, the hand, and
  // keyboard shortcuts.
  import { untrack } from "svelte";
  import { t, tn } from "../i18n/index.svelte";
  import { GameController } from "../lib/game.svelte";
  import { focusGroup, navigate } from "../lib/keynav";
  import { act, conn, toggleMute } from "../lib/session.svelte";
  import { toast } from "../lib/toasts.svelte";
  import Hand from "./Hand.svelte";
  import LangPicker from "./LangPicker.svelte";
  import PlayerStrip from "./PlayerStrip.svelte";
  import ShortcutHelp from "./ShortcutHelp.svelte";
  import StagingSheet from "./StagingSheet.svelte";
  import TablePile from "./TablePile.svelte";
  import VoiceControls from "./VoiceControls.svelte";

  const game = new GameController(conn);
  $effect(() => {
    void conn.state;
    untrack(() => game.sync());
  });

  let help = $state(false);
  let menu = $state(false);

  const room = $derived(conn.state!);
  const view = $derived(room.game!);
  const nameOf = (id: string | null) => (id ? (room.players.find((p) => p.id === id)?.name ?? "?") : null);
  const deckEmpty = $derived(view.deck === 0);
  const voted = $derived(view.draw_votes.includes(room.you));
  const hasSelection = $derived(game.selected.length > 0);

  function takeFocused(): boolean {
    const el = document.activeElement as HTMLElement | null;
    const id = el?.dataset.pile;
    const pile = id !== undefined ? view.table.find((p) => p.id === Number(id)) : undefined;
    if (pile) void game.take(pile);
    return !!pile;
  }

  function onkeydown(e: KeyboardEvent) {
    if (help || e.ctrlKey || e.metaKey || e.altKey) return;
    const target = e.target as HTMLElement;
    if (target.closest("input, select, textarea")) return;
    const key = e.key;
    const arrows: Record<string, "left" | "right" | "up" | "down"> = {
      ArrowLeft: "left",
      ArrowRight: "right",
      ArrowUp: "up",
      ArrowDown: "down",
    };
    if (arrows[key]) {
      e.preventDefault();
      navigate(arrows[key]);
      return;
    }
    switch (key.toLowerCase()) {
      case "escape":
        if (menu) menu = false;
        else if (hasSelection) game.clearSelection();
        else if (game.drafting) void game.cancel();
        break;
      case "d":
        void game.draw();
        break;
      case "s":
        if (game.drafting) void game.commit();
        else if (!takeFocused()) {
          if (hasSelection) game.place({ kind: "new" });
          else toast(t("game.stage_hint"));
        }
        break;
      case "n":
        game.place({ kind: "new" });
        break;
      case "o":
        void game.open();
        break;
      case "h":
        focusGroup("hand");
        break;
      case "t":
        if (!focusGroup("table")) toast(t("table.empty"));
        break;
      case "r":
        game.setSort(game.sort === "suit" ? "rank" : "suit");
        break;
      case "m":
        toggleMute();
        break;
      case "?":
        help = true;
        break;
      default:
        return;
    }
    e.preventDefault();
  }

  async function leave() {
    if (!confirm(t("game.leave_confirm"))) return;
    await act(() => conn.leave());
    history.replaceState(null, "", "/");
  }
</script>

<svelte:window {onkeydown} />

<div class="game">
  <header class="bar">
    <span class="code" title={t("lobby.code")}>{room.code}</span>
    <span class="deck" data-testid="deck-count" aria-label={tn("game.deck", view.deck)}>
      <span class="deck-icon" aria-hidden="true"></span>{view.deck}
    </span>
    <span class="spacer"></span>
    <VoiceControls />
    <button type="button" class="icon-btn" aria-label={t("keys.title")} title={t("keys.title") + " (?)"} onclick={() => (help = true)}
      >?</button
    >
    <div class="menu-wrap">
      <button
        type="button"
        class="icon-btn"
        aria-label={t("app.menu")}
        aria-expanded={menu}
        onclick={() => (menu = !menu)}>☰</button
      >
      {#if menu}
        <div class="menu">
          <LangPicker />
          <button type="button" class="btn" onclick={leave}>{t("lobby.leave")}</button>
        </div>
      {/if}
    </div>
  </header>

  <PlayerStrip players={room.players} you={room.you} host={room.host} />

  <section class="table" aria-label={t("table.title")} data-testid="table">
    {#each view.table as pile (pile.id)}
      <TablePile
        {pile}
        lockedBy={nameOf(pile.locked_by)}
        mine={pile.locked_by === room.you}
        disabled={!game.active || !game.opened}
        onclick={() => game.take(pile)}
      />
    {:else}
      <p class="empty">{t("table.empty")}</p>
    {/each}
  </section>

  {#if game.drafting}
    <div class="sheet-wrap"><StagingSheet {game} /></div>
  {/if}

  {#if game.active}
    <div class="actionbar" role="toolbar" aria-label={t("game.actions")}>
      <button
        type="button"
        class="btn"
        data-nav="actions"
        data-testid="draw"
        disabled={deckEmpty || game.busy}
        onclick={() => game.draw()}
        title={t("game.draw") + " (D)"}
      >
        {t("game.draw")}
      </button>
      {#if !game.opened}
        <button
          type="button"
          class="btn primary"
          data-nav="actions"
          data-testid="open"
          disabled={!game.canOpen || game.busy}
          onclick={() => game.open()}
          title={t("game.open") + " (O)"}>{t("game.open")}</button
        >
      {:else if hasSelection && !game.drafting}
        <button
          type="button"
          class="btn primary"
          data-nav="actions"
          data-testid="new-pile"
          onclick={() => game.place({ kind: "new" })}>{t("staging.new_pile")}</button
        >
      {/if}
      {#if deckEmpty}
        <button
          type="button"
          class="btn"
          data-nav="actions"
          disabled={voted}
          onclick={() => game.voteDraw()}
          title={t("game.vote_draw_hint")}
          >{voted
            ? t("game.voted", { n: view.draw_votes.length })
            : t("game.vote_draw", { n: view.draw_votes.length })}</button
        >
      {/if}
      <span class="spacer"></span>
      <button
        type="button"
        class="btn sort"
        data-nav="actions"
        aria-label={t(game.sort === "suit" ? "game.sorted_suit" : "game.sorted_rank")}
        title={t("keys.sort") + " (R)"}
        onclick={() => game.setSort(game.sort === "suit" ? "rank" : "suit")}
        >{game.sort === "suit" ? "♠♥" : "A23"}</button
      >
    </div>
    {#if !game.opened}
      <p class="tip">{hasSelection && !game.canOpen ? t("game.open_hint") : t("game.open_tip")}</p>
    {:else if !game.drafting && !hasSelection && view.table.length > 0}
      <p class="tip">{t("game.move_tip")}</p>
    {/if}
    <Hand
      cards={game.hand}
      selected={game.selected}
      borrowed={game.fromTable}
      ontoggle={(c) => game.toggle(c)}
      onplace={() => game.place({ kind: "hand" })}
    />
  {:else if game.me?.place}
    <p class="banner" data-testid="out-banner">{t("game.you_are_out", { place: game.me.place })}</p>
  {:else}
    <p class="banner">{t("game.spectating")}</p>
  {/if}
</div>

{#if help}<ShortcutHelp onclose={() => (help = false)} />{/if}

<style>
  .game {
    display: flex;
    flex-direction: column;
    width: 100%;
    max-width: 1200px;
    height: 100dvh;
    margin: 0 auto;
    overflow: hidden;
  }
  .bar {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 10px 0;
  }
  .code {
    padding: 2px 8px;
    border-radius: 6px;
    background: rgb(0 0 0 / 0.25);
    font-weight: 800;
    letter-spacing: 0.12em;
  }
  .deck {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }
  .deck-icon {
    width: 16px;
    height: 22px;
    border: 2px solid #fff;
    border-radius: 3px;
    background: repeating-linear-gradient(45deg, #b3263a 0 3px, #8c1c2d 3px 6px);
    box-shadow: 2px 2px 0 rgb(0 0 0 / 0.3);
  }
  .spacer {
    flex: 1;
  }
  .menu-wrap {
    position: relative;
  }
  .menu {
    position: absolute;
    right: 0;
    top: calc(100% + 4px);
    z-index: 100;
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 10px;
    border-radius: 12px;
    background: #1b2a43;
    box-shadow: 0 6px 18px rgb(0 0 0 / 0.5);
  }
  .table {
    display: flex;
    flex: 1;
    flex-wrap: wrap;
    align-content: flex-start;
    gap: 8px;
    min-height: 80px;
    padding: 10px;
    overflow-y: auto;
    background: radial-gradient(ellipse at center, #1d6b45, #145236 80%);
    border-radius: 14px;
    margin: 0 6px;
    box-shadow: inset 0 2px 12px rgb(0 0 0 / 0.35);
  }
  .empty {
    margin: auto;
    color: rgb(255 255 255 / 0.65);
  }
  .sheet-wrap {
    display: flex;
    flex-direction: column;
    max-height: 46dvh;
    margin: -12px 0 0;
    position: relative;
    z-index: 10;
  }
  .actionbar {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 10px 0;
  }
  .sort {
    min-width: 56px;
    font-weight: 800;
  }
  .tip {
    margin: 4px 12px 0;
    color: var(--muted);
    font-size: 13px;
  }
  .banner {
    margin: 12px;
    padding: 14px;
    border-radius: 12px;
    background: var(--panel);
    text-align: center;
    font-size: 17px;
  }
  .game > :global(.hand) {
    flex: none;
    max-height: 40dvh;
    overflow-y: auto;
    overflow-x: hidden;
    padding-bottom: env(safe-area-inset-bottom);
    margin-bottom: 6px;
  }
  @media (min-width: 900px) {
    .table {
      gap: 12px;
      padding: 16px;
      margin: 0 10px;
    }
    .sheet-wrap {
      width: min(900px, 100%);
      align-self: center;
    }
  }
</style>
