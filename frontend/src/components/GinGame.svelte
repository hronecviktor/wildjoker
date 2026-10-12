<script lang="ts">
  // A Gin game (RULES-GIN.md): players with whose turn it is and the scores,
  // the melds on the table, the discard pile and the deck, and the hand.
  // On your turn you draw (tap the deck, or a card of the discard pile), lay
  // down or add to melds with the cards you select, and discard one card.
  import { untrack } from "svelte";
  import { t, tn } from "../i18n/index.svelte";
  import { cardLabel } from "../i18n/cards";
  import { allows, type GinStep, type Move } from "../lib/ginTutorial";
  import { sortCards, type SortMode } from "../lib/cards";
  import { withValues } from "../lib/jokers";
  import * as motion from "../lib/motion";
  import { arrange } from "../lib/piles";
  import { ginView, type Meld } from "../lib/protocol";
  import { act, conn, leaveRoom, toggleMute } from "../lib/session.svelte";
  import { setSound, soundOn, turnSound } from "../lib/sounds";
  import { load, save } from "../lib/storage";
  import { toast } from "../lib/toasts.svelte";
  import { keepAwake } from "../lib/wakelock";
  import Card from "./Card.svelte";
  import GinRoundOver from "./GinRoundOver.svelte";
  import GinRules from "./GinRules.svelte";
  import GinTutorial from "./GinTutorial.svelte";
  import Hand from "./Hand.svelte";
  import LangPicker from "./LangPicker.svelte";
  import PlayerStrip from "./PlayerStrip.svelte";
  import VoiceControls from "./VoiceControls.svelte";

  /** How long a card just drawn stays highlighted (as in Card's animation). */
  const FRESH_MS = 3000;

  const room = $derived(conn.state!);
  const view = $derived(ginView(room)!);
  const nameOf = (id: string | null) => (id ? (room.players.find((p) => p.id === id)?.name ?? "?") : "");

  let selected = $state<number[]>([]);
  let sort = $state<SortMode>(load<SortMode>("sort", "suit"));
  /** A deeper discard tapped once: tapping "Take" confirms. */
  let dig = $state<number | null>(null);
  let busy = $state(false);
  let menu = $state(false);
  let rules = $state(false);
  let sound = $state(soundOn());
  let fresh = $state.raw<Set<number>>(new Set());
  /** In the tutorial, the step being played: only its moves are allowed. */
  let tutorialStep = $state<GinStep | undefined>();

  function allowed(move: Move, cards: number[]): boolean {
    if (!room.tutorial || !tutorialStep || allows(tutorialStep, move, cards)) return true;
    toast(t("gin_tutorial.follow"));
    return false;
  }

  const playing = $derived(view.status === "playing");
  const myTurn = $derived(playing && view.turn === room.you);
  const drawing = $derived(myTurn && view.step === "draw");
  const acting = $derived(myTurn && view.step === "play");
  const hand = $derived(sortCards(view.hand ?? [], sort));
  const top = $derived(view.discard.at(-1) ?? null);
  const takeable = $derived(new Set(view.takeable ?? []));
  const selection = $derived(arrange(selected));
  const canLayDown = $derived(acting && selection !== null);
  const canDiscard = $derived(
    acting && selected.length === 1 && selected[0] !== view.picked && view.must_play === null,
  );
  /** Melds the selected cards could be added to. */
  const fits = $derived(
    new Set(
      acting && selected.length
        ? view.melds.filter((m) => arrange([...m.cards, ...selected]) !== null).map((m) => m.id)
        : [],
    ),
  );
  const digCards = $derived(dig === null ? [] : view.discard.slice(view.discard.indexOf(dig)));

  const status = $derived.by(() => {
    if (!playing) return "";
    if (!myTurn) return t("gin.waiting", { name: nameOf(view.turn) });
    if (drawing) return t("gin.your_turn_draw");
    if (view.must_play !== null) return t("gin.must_play", { card: cardLabel(view.must_play) });
    if (fits.size && !canLayDown) return t("gin.add_hint");
    return t("gin.your_turn_play");
  });

  // The screen stays on while the game is open.
  $effect(() => keepAwake());

  // Keep the selection to cards still in the hand, and forget a half-made
  // dig once it's no longer our turn to draw.
  $effect(() => {
    const inHand = new Set(view.hand ?? []);
    untrack(() => {
      if (selected.some((c) => !inHand.has(c))) selected = selected.filter((c) => inHand.has(c));
      if (dig !== null && (!drawing || !takeable.has(dig))) dig = null;
    });
  });

  // Cards move (motion.ts): note where they are before an update...
  $effect.pre(() => {
    void conn.state;
    void sort;
    untrack(() => motion.capture());
  });
  // ...and after it, fly them from where they came from: a new card in the
  // hand from the deck, a card new to the table or the discard pile from
  // the icon of whoever played it, a discard someone took to their icon.
  let last: { turn: string | null; deck: number; hand: number[]; round: number } | null = null;
  $effect(() => {
    void conn.state;
    void sort;
    untrack(() => {
      const v = ginView(conn.state);
      if (!v) return;
      const before = last;
      const actor = before?.turn ?? null;
      const refilled = !!before && v.deck > before.deck;
      motion.play({
        from: (_card, zone) => (zone === "hand" ? motion.deck() : motion.playerIcon(actor)),
        to: (_card, spot) =>
          spot.zone === "discard" ? (refilled || !actor ? motion.deck() : motion.playerIcon(actor)) : null,
        fast: false,
      });
      // A card just drawn or taken glows for a moment.
      if (before && before.round === v.round && v.hand) {
        const had = new Set(before.hand);
        const added = v.hand.filter((c) => !had.has(c));
        if (added.length) {
          fresh = new Set([...fresh, ...added]);
          setTimeout(() => (fresh = new Set([...fresh].filter((c) => !added.includes(c)))), FRESH_MS);
        }
      }
      if (v.status === "playing" && v.turn === room.you && before?.turn !== room.you) turnSound();
      last = { turn: v.status === "playing" ? v.turn : null, deck: v.deck, hand: v.hand ?? [], round: v.round };
    });
  });

  async function send(msg: { type: string; [key: string]: unknown }): Promise<boolean> {
    if (busy) return false;
    busy = true;
    try {
      return (await act(() => conn.request(msg))) !== undefined;
    } finally {
      busy = false;
    }
  }

  function toggle(card: number) {
    selected = selected.includes(card) ? selected.filter((c) => c !== card) : [...selected, card];
  }

  function draw() {
    if (!drawing) {
      if (playing && !myTurn) toast(t("error.not_your_turn"));
      return;
    }
    if (!allowed("draw", [])) return;
    dig = null;
    void send({ type: "draw" });
  }

  function tapDiscard(card: number) {
    if (!drawing) {
      if (playing && !myTurn) toast(t("error.not_your_turn"));
      return;
    }
    if (card === top) {
      if (!allowed("take", [card])) return;
      dig = null;
      void send({ type: "take", card });
    } else if (!takeable.has(card)) {
      toast(t("gin.cant_take"));
    } else {
      dig = dig === card ? null : card;
    }
  }

  async function takeDig() {
    if (dig === null || !allowed("take", [dig])) return;
    const card = dig;
    if (await send({ type: "take", card })) dig = null;
  }

  async function layDown() {
    if (!canLayDown) {
      if (acting) toast(t("gin.select_hint"));
      return;
    }
    if (!allowed("meld", selection!.cards)) return;
    if (await send({ type: "meld", cards: selection!.cards })) selected = [];
  }

  async function tapMeld(meld: Meld) {
    if (!acting) return;
    if (!selected.length) {
      toast(t("gin.select_hint"));
      return;
    }
    if (!fits.has(meld.id)) {
      toast(t("error.invalid_pile"), "error");
      return;
    }
    if (!allowed("lay_off", selected)) return;
    if (await send({ type: "lay_off", pile: meld.id, cards: selected })) selected = [];
  }

  async function discard() {
    if (!canDiscard) {
      if (acting) toast(t("gin.select_hint"));
      return;
    }
    if (!allowed("discard", selected)) return;
    if (await send({ type: "discard", card: selected[0] })) selected = [];
  }

  function setSort(mode: SortMode) {
    sort = mode;
    save("sort", mode);
  }

  /** The names of who put down a meld's cards, first the one with most. */
  function owners(meld: Meld): string {
    const counts = new Map<string, number>();
    for (const o of meld.owners) counts.set(o, (counts.get(o) ?? 0) + 1);
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([id]) => (id === room.you ? t("table.you") : nameOf(id)))
      .join(", ");
  }

  function meldLabel(meld: Meld): string {
    const cards = withValues(meld.cards)
      .map((c) => cardLabel(c.id, c.value))
      .join(", ");
    return t("gin.meld", { cards }) + "; " + t("gin.put_down_by", { names: owners(meld) });
  }

  // Keep the newest discard in view.
  let discardEl: HTMLElement | undefined = $state();
  $effect(() => {
    void view.discard.length;
    discardEl?.scrollTo({ left: discardEl.scrollWidth });
  });

  function onkeydown(e: KeyboardEvent) {
    if (rules || e.ctrlKey || e.metaKey || e.altKey) return;
    if ((e.target as HTMLElement).closest("input, select, textarea")) return;
    switch (e.key.toLowerCase()) {
      case "escape":
        if (menu) menu = false;
        else if (dig !== null) dig = null;
        else selected = [];
        break;
      case "d":
        draw();
        break;
      case "l":
        void layDown();
        break;
      case "x":
        void discard();
        break;
      case "r":
        setSort(sort === "suit" ? "rank" : "suit");
        break;
      case "m":
        toggleMute();
        break;
      case "?":
        rules = true;
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
    <span class="round" data-testid="round"
      >{t("gin.round", { n: view.round })}{room.tutorial ? "" : " · " + t("gin.to", { n: view.target })}</span
    >
    <span class="spacer"></span>
    <VoiceControls />
    <button type="button" class="icon-btn" aria-label={t("gin.rules_title")} title={t("gin.rules_title") + " (?)"}
      onclick={() => (rules = true)}>?</button
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

  <PlayerStrip players={room.players} you={room.you} host={room.host} turn={view.turn} />

  {#if room.tutorial}
    <GinTutorial {room} game={view} {selected} {dig} bind:step={tutorialStep} />
  {/if}

  <div class="table-wrap">
    <section class="table" aria-label={t("gin.melds")} data-testid="table">
      {#each view.melds as meld (meld.id)}
        {@const ownerOf = new Map(meld.cards.map((c, i) => [c, meld.owners[i]]))}
        {@const mixed = new Set(meld.owners).size > 1}
        <button
          type="button"
          class="meld"
          class:fits={fits.has(meld.id)}
          data-zone="meld:{meld.id}"
          data-meld={meld.id}
          aria-label={meldLabel(meld)}
          aria-disabled={!acting}
          onclick={() => tapMeld(meld)}
        >
          <span class="cards">
            {#each withValues(meld.cards) as c (c.id)}
              <span class="slot">
                <Card id={c.id} value={c.value} size="pile" />
                {#if mixed}
                  {@const owner = ownerOf.get(c.id) ?? ""}
                  <span class="owner" class:mine={owner === room.you} aria-hidden="true"
                    >{nameOf(owner).slice(0, 1).toUpperCase()}</span
                  >
                {/if}
              </span>
            {/each}
          </span>
        </button>
      {:else}
        <p class="empty">{t("gin.no_melds")}</p>
      {/each}
    </section>

    <div class="piles">
      <div
        class="discard"
        class:drawing
        role="group"
        aria-label={t("gin.discard_pile")}
        data-zone="discard"
        data-testid="discard"
        bind:this={discardEl}
      >
        {#each view.discard as card, i (card)}
          <span
            class="slot"
            class:top={i === view.discard.length - 1}
            class:dim={drawing && !takeable.has(card)}
            class:dug={digCards.includes(card)}
          >
            <Card id={card} size="pile" selected={dig === card} onclick={() => tapDiscard(card)} />
          </span>
        {/each}
      </div>
      <button
        type="button"
        class="deck"
        class:empty={view.deck === 0}
        data-testid="deck"
        disabled={!drawing}
        aria-label={tn("game.deck", view.deck) + (drawing ? ". " + t("game.draw") : "")}
        title={t("game.draw") + " (D)"}
        onclick={draw}
      >
        <span class="stack" aria-hidden="true"></span>
        <span class="count" data-testid="deck-count">{view.deck}</span>
      </button>
    </div>
  </div>

  {#if !room.tutorial}
    <!-- (In the tutorial the coach panel explains instead, leaving the table more room.) -->
    <p class="status" class:mine={myTurn} data-testid="status" aria-live="polite">{status}</p>
  {/if}

  {#if dig !== null}
    <div class="actionbar" role="toolbar" aria-label={t("game.actions")}>
      <p class="dig-hint">{t("gin.dig_hint", { card: cardLabel(dig) })}</p>
      <button type="button" class="btn" onclick={() => (dig = null)}>{t("staging.cancel")}</button>
      <button type="button" class="btn primary" data-testid="take" disabled={busy} onclick={takeDig}
        >{tn("gin.take", digCards.length)}</button
      >
    </div>
  {:else}
    <div class="actionbar" role="toolbar" aria-label={t("game.actions")}>
      <button
        type="button"
        class="btn primary"
        data-testid="lay-down"
        disabled={!canLayDown || busy}
        title={t("gin.lay_down") + " (L)"}
        onclick={layDown}>{t("gin.lay_down")}</button
      >
      <button
        type="button"
        class="btn"
        data-testid="discard-btn"
        disabled={!canDiscard || busy}
        title={t("gin.discard") + " (X)"}
        onclick={discard}>{t("gin.discard")}</button
      >
      <span class="spacer"></span>
      <button
        type="button"
        class="btn sort"
        aria-label={t(sort === "suit" ? "game.sorted_suit" : "game.sorted_rank")}
        title={t("keys.sort") + " (R)"}
        onclick={() => setSort(sort === "suit" ? "rank" : "suit")}>{sort === "suit" ? "♠♥" : "A23"}</button
      >
    </div>
  {/if}

  <Hand
    cards={hand}
    {selected}
    borrowed={new Set(view.must_play === null ? [] : [view.must_play])}
    {fresh}
    ontoggle={toggle}
  />
</div>

{#if view.status === "round_over"}<GinRoundOver {room} game={view} />{/if}
{#if rules}<GinRules onclose={() => (rules = false)} />{/if}

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
  .round {
    overflow: hidden;
    color: var(--muted);
    font-size: 14px;
    white-space: nowrap;
    text-overflow: ellipsis;
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
  .table-wrap {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-height: 120px;
    margin: 0 6px;
    overflow: hidden;
    border-radius: 14px;
    background: radial-gradient(ellipse at center, #1d6b45, #145236 80%);
    box-shadow: inset 0 2px 12px rgb(0 0 0 / 0.35);
  }
  .table {
    display: flex;
    flex: 1;
    flex-wrap: wrap;
    align-content: flex-start;
    gap: 8px;
    min-height: 0;
    padding: 10px;
    overflow-y: auto;
  }
  .empty {
    margin: auto;
    color: rgb(255 255 255 / 0.65);
  }
  .meld {
    display: inline-flex;
    padding: 6px 8px 8px;
    border: 1px solid rgb(255 255 255 / 0.12);
    border-radius: 10px;
    background: rgb(0 0 0 / 0.14);
    color: inherit;
    font: inherit;
    cursor: pointer;
  }
  .meld[aria-disabled="true"] {
    cursor: default;
  }
  .meld.fits {
    border-color: #2fe07a;
    box-shadow: 0 0 0 2px #2fe07a;
  }
  .meld:focus-visible {
    outline: 3px solid #39a0ff;
    outline-offset: 2px;
  }
  .cards {
    display: flex;
  }
  .slot {
    position: relative;
    display: inline-flex;
  }
  .cards > .slot:not(:first-child) {
    margin-left: -20px;
  }
  .owner {
    position: absolute;
    left: 2px;
    bottom: -6px;
    z-index: 3;
    min-width: 16px;
    height: 16px;
    padding: 0 3px;
    border-radius: 999px;
    background: #33415c;
    color: #fff;
    font-size: 10px;
    font-weight: 800;
    line-height: 16px;
    text-align: center;
  }
  .owner.mine {
    background: #2958c9;
  }
  .piles {
    display: flex;
    flex: none;
    align-items: flex-end;
    gap: 10px;
    padding: 6px 8px 8px;
    border-top: 1px solid rgb(0 0 0 / 0.18);
    background: rgb(0 0 0 / 0.12);
  }
  .discard {
    display: flex;
    flex: 1;
    min-width: 0;
    /* Room for a selected card's lift and check mark. */
    padding: 14px 6px 2px;
    overflow-x: auto;
    scrollbar-width: thin;
  }
  /* Fanned wide enough that each card shows its corner and is easy to tap;
     the row scrolls when the pile grows long. */
  .discard .slot:not(:first-child) {
    margin-left: -14px;
  }
  .discard .slot.top {
    margin-right: 4px;
  }
  .discard.drawing .slot:not(.dim) :global(.card) {
    box-shadow: 0 0 0 2px #f5b301;
  }
  .discard .slot.dim {
    opacity: 0.55;
  }
  .discard .slot.dug :global(.card) {
    transform: translateY(-8px);
  }
  .deck {
    display: flex;
    flex: none;
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
    width: 42px;
    height: 60px;
    border: 2px solid #fff;
    border-radius: 5px;
    background: repeating-linear-gradient(45deg, #b3263a 0 4px, #8c1c2d 4px 8px);
    box-shadow:
      2px 2px 0 -1px #8c1c2d,
      2px 2px 0 0 #fff,
      4px 4px 0 -1px #8c1c2d,
      4px 4px 0 0 #fff,
      4px 6px 8px rgb(0 0 0 / 0.4);
    transition: transform 0.12s ease;
  }
  .deck:not(:disabled) .stack {
    box-shadow:
      0 0 0 3px #f5b301,
      2px 2px 0 -1px #8c1c2d,
      4px 6px 8px rgb(0 0 0 / 0.4);
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
  /* Two lines always, so the table doesn't change size as the text does. */
  .status {
    --lines: 2;
    flex: none;
    height: calc(var(--lines) * 1.35em);
    margin: 6px 12px 0;
    overflow: hidden;
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: var(--lines);
    line-clamp: var(--lines);
    color: var(--muted);
    font-size: 14px;
    line-height: 1.35;
  }
  .status.mine {
    color: #ffd75e;
    font-weight: 600;
  }
  .actionbar {
    display: flex;
    flex: none;
    align-items: center;
    gap: 6px;
    min-height: 52px;
    padding: 4px 10px 0;
  }
  .dig-hint {
    flex: 1;
    margin: 0;
    color: var(--muted);
    font-size: 13px;
    line-height: 1.3;
  }
  .sort {
    min-width: 56px;
    font-weight: 800;
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
    .deck .stack {
      width: 48px;
      height: 68px;
    }
    .discard .slot:not(:first-child) {
      margin-left: -16px;
    }
  }
</style>
