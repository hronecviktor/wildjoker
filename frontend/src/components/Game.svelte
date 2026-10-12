<script lang="ts">
  // The game table: players, table piles, the staging sheet, the hand, and
  // keyboard shortcuts.
  import { untrack } from "svelte";
  import { t, tn } from "../i18n/index.svelte";
  import { GameController } from "../lib/game.svelte";
  import * as motion from "../lib/motion";
  import { setSound, soundOn } from "../lib/sounds";
  import { keepAwake } from "../lib/wakelock";
  import { focusGroup, navigate } from "../lib/keynav";
  import { act, conn, leaveRoom, toggleMute } from "../lib/session.svelte";
  import { toast } from "../lib/toasts.svelte";
  import Hand from "./Hand.svelte";
  import LangPicker from "./LangPicker.svelte";
  import PlayerStrip from "./PlayerStrip.svelte";
  import ShortcutHelp from "./ShortcutHelp.svelte";
  import StagingSheet from "./StagingSheet.svelte";
  import TablePile from "./TablePile.svelte";
  import Tutorial from "./Tutorial.svelte";
  import { wildView } from "../lib/protocol";
  import { tableOrder } from "../lib/tableOrder";
  import VoiceControls from "./VoiceControls.svelte";

  const game = new GameController(conn);
  // Before the cards on screen change, note where they are (motion.ts)...
  $effect.pre(() => {
    void conn.state;
    untrack(() => {
      motion.capture();
      game.sync();
    });
  });
  $effect.pre(() => {
    void game.draft;
    void game.sort;
    untrack(() => motion.capture());
  });

  // The screen stays on while the game is open.
  $effect(() => keepAwake());

  let help = $state(false);
  let menu = $state(false);
  let sound = $state(soundOn());

  const room = $derived(conn.state!);
  const view = $derived(wildView(room)!);
  const nameOf = (id: string | null) => (id ? (room.players.find((p) => p.id === id)?.name ?? "?") : null);
  const deckEmpty = $derived(view.deck === 0);
  const voted = $derived(view.draw_votes.includes(room.you));
  const hasSelection = $derived(game.selected.length > 0);

  // The table shrinks its cards (density 0-3) until every pile fits without
  // scrolling; only if even the smallest size doesn't fit does it scroll.
  const MAX_DENSITY = 3;
  const piles = $derived(tableOrder(view.table));
  let tableEl: HTMLElement | undefined = $state();
  let deckEl: HTMLElement | undefined = $state();
  let density = $state(0);

  /** Some pile reaches under the deck in the table's corner. */
  function underDeck(el: HTMLElement): boolean {
    const deck = deckEl?.getBoundingClientRect();
    if (!deck) return false;
    return [...el.querySelectorAll("[data-pile]")].some((pile) => {
      const r = pile.getBoundingClientRect();
      return r.right > deck.left - 4 && r.bottom > deck.top - 4;
    });
  }

  function fitTable() {
    const el = tableEl;
    if (!el) return;
    // Measure by setting the attribute directly (the browser lays out on
    // read), then keep the result in state so the markup agrees.
    let d = 0;
    el.dataset.density = "0";
    while ((el.scrollHeight > el.clientHeight + 1 || underDeck(el)) && d < MAX_DENSITY) {
      el.dataset.density = String(++d);
    }
    density = d;
  }

  $effect(() => {
    void piles; // refit when piles change...
    fitTable();
  });
  $effect(() => {
    if (!tableEl) return;
    const observer = new ResizeObserver(() => fitTable()); // ...or the table's size does
    observer.observe(tableEl);
    return () => observer.disconnect();
  });
  // ...and once they have changed (and the table fits), animate the moves.
  $effect(() => {
    void conn.state;
    void game.draft;
    void game.sort;
    untrack(() => {
      const changes = game.observe();
      motion.play({
        from: (_card, zone) => {
          if (zone === "hand") return motion.deck();
          const pile = zone.startsWith("pile:") ? Number(zone.slice(5)) : null;
          const actor = pile === null ? null : (changes?.piles.get(pile) ?? null);
          return motion.playerIcon(actor);
        },
        to: (_card, spot) => (spot.owner && spot.owner !== room.you ? motion.playerIcon(spot.owner) : null),
        fast: !!room.fast_forward,
      });
    });
  });
  // Everyone still holding cards is a CPU: a human may speed them up.
  const canFastForward = $derived.by(() => {
    if (room.phase !== "playing" || !game.me || game.me.cpu !== null) return false;
    const playing = room.players.filter((p) => p.cards !== undefined && p.place == null);
    return playing.length > 0 && playing.every((p) => p.cpu !== null);
  });

  function toggleFastForward() {
    void act(() => conn.request({ type: "fast_forward", on: !room.fast_forward }));
  }

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
      case "f":
        if (canFastForward) toggleFastForward();
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
    if (confirm(t("game.leave_confirm"))) await leaveRoom();
  }
</script>

<svelte:window {onkeydown} />

<div class="game">
  <header class="bar">
    <span class="code" title={t("lobby.code")}>{room.code}</span>
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
          <button
            type="button"
            class="btn"
            aria-pressed={sound}
            data-testid="sound"
            onclick={() => setSound((sound = !sound))}>{sound ? "🔊 " + t("game.sound_on") : "🔇 " + t("game.sound_off")}</button
          >
          <button type="button" class="btn" onclick={leave}>{t("lobby.leave")}</button>
        </div>
      {/if}
    </div>
  </header>

  <PlayerStrip players={room.players} you={room.you} host={room.host} />

  {#if room.tutorial}<Tutorial {game} {room} />{/if}

  <div class="table-wrap">
  <section class="table" aria-label={t("table.title")} data-testid="table"
    data-density={density}
    bind:this={tableEl}
  >
    {#each piles as pile (pile.id)}
      <TablePile
        {pile}
        lockedBy={nameOf(pile.locked_by)}
        mine={pile.locked_by === room.you}
        fresh={game.freshTable}
        changed={game.changedPiles.has(pile.id)}
        changedBy={game.changedPiles.get(pile.id) ?? null}
        disabled={!game.active || !game.opened}
        onclick={() => game.take(pile)}
      />
    {:else}
      <p class="empty">{t("table.empty")}</p>
    {/each}
  </section>
  <!-- The deck, in the table's corner: tap it to draw. -->
  <button
    type="button"
    class="deck"
    class:empty={deckEmpty}
    data-testid="deck"
    bind:this={deckEl}
    disabled={!game.active || deckEmpty || !game.allowDraw}
    aria-label={tn("game.deck", view.deck) + (game.active ? ". " + t("game.draw") : "")}
    title={t("game.draw") + " (D)"}
    onclick={() => game.draw()}
  >
    <span class="stack" aria-hidden="true"></span>
    <span class="count" data-testid="deck-count">{view.deck}</span>
  </button>
  </div>

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
        disabled={deckEmpty || !game.allowDraw}
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
    {#if !room.tutorial}
      <!-- (The tutorial's coach panel explains instead.) The tip keeps its
           two-line slot even when empty: if it came and went with the
           selection, the table's height would change and its piles jump
           to another card size. -->
      <p class="tip" data-testid="tip">
        {#if !game.opened}
          {hasSelection && !game.canOpen ? t("game.open_hint") : t("game.open_tip")}
        {:else if !game.drafting && !hasSelection && view.table.length > 0}
          {t("game.move_tip")}
        {/if}
      </p>
    {/if}
    <Hand
      cards={game.hand}
      selected={game.selected}
      borrowed={game.fromTable}
      fresh={game.freshHand}
      ontoggle={(c) => game.toggle(c)}
      onplace={() => game.place({ kind: "hand" })}
    />
  {:else if game.me?.place}
    <p class="banner" data-testid="out-banner">{t("game.you_are_out", { place: game.me.place })}</p>
  {:else}
    <p class="banner">{t("game.spectating")}</p>
  {/if}
  {#if canFastForward}
    <div class="ff-bar">
      <span class="ff-hint">{t("game.only_cpus_left")}</span>
      <button
        type="button"
        class="btn"
        class:primary={!room.fast_forward}
        aria-pressed={room.fast_forward}
        aria-keyshortcuts="F"
        data-testid="fast-forward"
        onclick={toggleFastForward}
        >{room.fast_forward ? "▶ " + t("game.normal_speed") : "⏩ " + t("game.fast_forward")}</button
      >
    </div>
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
  .table-wrap {
    position: relative;
    display: flex;
    flex: 1;
    min-height: 80px;
    margin: 0 6px;
  }
  .deck {
    position: absolute;
    right: 8px;
    bottom: 8px;
    z-index: 2;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: 0;
    border: 0;
    background: none;
    color: #fff;
    font: inherit;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
  }
  .deck:disabled {
    cursor: default;
  }
  .deck .stack {
    position: relative;
    width: 40px;
    height: 56px;
    border: 2px solid #fff;
    border-radius: 5px;
    background: repeating-linear-gradient(45deg, #b3263a 0 4px, #8c1c2d 4px 8px);
    /* The cards underneath. */
    box-shadow:
      2px 2px 0 -1px #8c1c2d,
      2px 2px 0 0 #fff,
      4px 4px 0 -1px #8c1c2d,
      4px 4px 0 0 #fff,
      4px 6px 8px rgb(0 0 0 / 0.4);
    transition: transform 0.12s ease;
  }
  .deck:not(:disabled):hover .stack,
  .deck:not(:disabled):active .stack {
    transform: translateY(-3px);
  }
  .deck.empty .stack {
    border-style: dashed;
    border-color: rgb(255 255 255 / 0.5);
    background: rgb(0 0 0 / 0.15);
    box-shadow: none;
  }
  .deck .count {
    min-width: 26px;
    padding: 0 6px;
    border-radius: 999px;
    background: rgb(0 0 0 / 0.45);
    font-size: 12px;
    font-weight: 800;
    line-height: 18px;
    font-variant-numeric: tabular-nums;
    text-align: center;
  }
  .deck:focus-visible {
    outline: 3px solid #39a0ff;
    outline-offset: 2px;
    border-radius: 6px;
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
    box-shadow: inset 0 2px 12px rgb(0 0 0 / 0.35);
  }
  /* Denser tables: smaller pile cards that overlap more, showing the corner. */
  .table[data-density="1"] {
    gap: 6px;
  }
  .table[data-density="1"] :global(.card.pile) {
    --w: 34px;
    --h: 48px;
    --corner: 12px;
  }
  .table[data-density="1"] :global(.pile .cards > *:not(:first-child)) {
    margin-left: -19px;
  }
  .table[data-density="2"],
  .table[data-density="3"] {
    gap: 5px;
    padding: 8px;
  }
  .table[data-density="2"] :global(.pile),
  .table[data-density="3"] :global(.pile) {
    padding: 4px 5px 5px;
  }
  .table[data-density="2"] :global(.card.pile) {
    --w: 30px;
    --h: 40px;
    --corner: 11px;
  }
  .table[data-density="2"] :global(.pile .cards > *:not(:first-child)) {
    margin-left: -17px;
  }
  .table[data-density="3"] :global(.card.pile) {
    --w: 26px;
    --h: 34px;
    --corner: 10px;
  }
  .table[data-density="3"] :global(.pile .cards > *:not(:first-child)) {
    margin-left: -14px;
  }
  .table[data-density="2"] :global(.card.pile .corner),
  .table[data-density="3"] :global(.card.pile .corner) {
    left: 2px;
  }
  .table[data-density="2"] :global(.card.pile .pip),
  .table[data-density="3"] :global(.card.pile .pip) {
    display: none;
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
    --lines: 2;
    flex: none;
    height: calc(var(--lines) * 1.35em);
    margin: 4px 12px 0;
    overflow: hidden;
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: var(--lines);
    line-clamp: var(--lines);
    color: var(--muted);
    font-size: 13px;
    line-height: 1.35;
  }
  .ff-bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: center;
    gap: 8px 12px;
    margin: 0 12px 12px;
  }
  .ff-hint {
    color: var(--muted);
    font-size: 14px;
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
    }
    .table-wrap {
      margin: 0 10px;
    }
    .deck {
      right: 14px;
      bottom: 14px;
    }
    .deck .stack {
      width: 48px;
      height: 68px;
    }
    .sheet-wrap {
      width: min(900px, 100%);
      align-self: center;
    }
  }
</style>
