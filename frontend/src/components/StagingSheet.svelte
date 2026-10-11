<script lang="ts">
  // The staging area as a bottom sheet: the piles of the move being built,
  // each marked valid or invalid live, with targets to place selected cards.
  import { t, tn } from "../i18n/index.svelte";
  import { displayOrder, pileValid } from "../lib/draft";
  import type { GameController } from "../lib/game.svelte";
  import { withValues } from "../lib/jokers";
  import Card from "./Card.svelte";

  let { game }: { game: GameController } = $props();

  let now = $state(performance.now());
  $effect(() => {
    if (game.deadline === null) return;
    const timer = setInterval(() => (now = performance.now()), 200);
    return () => clearInterval(timer);
  });
  const remaining = $derived(game.deadline === null ? null : Math.max(0, (game.deadline - now) / 1000));
  const timeout = $derived(game.game?.staging_timeout ?? 15);
  const hasSelection = $derived(game.selected.length > 0);
</script>

<section class="sheet" aria-label={t("staging.title")} data-testid="staging">
  <header>
    <h2>{t("staging.title")}</h2>
    {#if remaining !== null}
      <span
        class="timer"
        class:urgent={remaining < 5}
        style:--frac={remaining / timeout}
        role="timer"
        aria-label={tn("staging.seconds_left", Math.ceil(remaining))}>{Math.ceil(remaining)}</span
      >
    {/if}
    <span class="spacer"></span>
    <button type="button" class="btn" data-nav="staging-actions" onclick={() => game.cancel()}>
      {t("staging.cancel")}
    </button>
    <button
      type="button"
      class="btn primary"
      data-nav="staging-actions"
      data-testid="commit"
      disabled={!game.canCommit || game.busy}
      onclick={() => game.commit()}
    >
      {t("staging.commit")}
    </button>
  </header>

  <div class="piles">
    {#each game.draft.piles as pile, n (pile.key)}
      {@const valid = pileValid(pile)}
      {@const cards = valid ? withValues(pile.cards) : displayOrder(pile.cards).map((id) => ({ id, value: null }))}
      <div class="pile" class:invalid={!valid} data-testid="draft-pile">
        <button
          type="button"
          class="status"
          data-nav="staging"
          aria-label={t(valid ? "staging.pile_valid" : "staging.pile_invalid", { n: n + 1 }) +
            ". " +
            t("staging.select_pile")}
          onclick={() => game.selectPile(pile.key)}
        >
          <span aria-hidden="true">{valid ? "✓" : "✗"}</span>
        </button>
        <div class="cards">
          {#each cards as c (c.id)}
            <Card
              id={c.id}
              value={c.value}
              size="pile"
              nav="staging"
              selected={game.selected.includes(c.id)}
              borrowed={false}
              onclick={() => game.toggle(c.id)}
            />
          {/each}
        </div>
        <button
          type="button"
          class="place"
          data-nav="staging"
          disabled={!hasSelection}
          aria-label={t("staging.place_here_n", { n: n + 1 })}
          onclick={() => game.place({ kind: "pile", key: pile.key })}>＋</button
        >
      </div>
    {:else}
      <p class="hint">{t("staging.empty_hint")}</p>
    {/each}
  </div>

  {#if hasSelection}
    <div class="actions">
      <button type="button" class="btn" data-nav="staging-actions" onclick={() => game.place({ kind: "new" })}>
        {t("staging.new_pile")}
      </button>
      {#if game.selectedInPiles.length}
        <button type="button" class="btn" data-nav="staging-actions" onclick={() => game.place({ kind: "hand" })}>
          {t("staging.to_hand")}
        </button>
      {/if}
      {#if game.splitPoint}
        <button type="button" class="btn" data-nav="staging-actions" onclick={() => game.split()}>
          ✂ {t("staging.split")}
        </button>
      {/if}
    </div>
  {:else if game.draft.piles.some((p) => !pileValid(p))}
    <p class="hint small">{t("staging.fix_piles")}</p>
  {/if}
</section>

<style>
  .sheet {
    display: flex;
    flex-direction: column;
    gap: 6px;
    max-height: 100%;
    padding: 8px 10px 10px;
    border-radius: 16px 16px 0 0;
    background: #1b2a43;
    box-shadow: 0 -6px 18px rgb(0 0 0 / 0.4);
    color: #fff;
  }
  header {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  h2 {
    margin: 0;
    font-size: 16px;
  }
  .spacer {
    flex: 1;
  }
  .timer {
    --frac: 1;
    display: inline-grid;
    place-items: center;
    width: 34px;
    height: 34px;
    border-radius: 50%;
    background:
      radial-gradient(closest-side, #1b2a43 78%, transparent 80%),
      conic-gradient(#4ade80 calc(var(--frac) * 360deg), rgb(255 255 255 / 0.15) 0);
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }
  .timer.urgent {
    background:
      radial-gradient(closest-side, #1b2a43 78%, transparent 80%),
      conic-gradient(#f87171 calc(var(--frac) * 360deg), rgb(255 255 255 / 0.15) 0);
    color: #fca5a5;
  }
  .piles {
    display: flex;
    flex-direction: column;
    gap: 6px;
    overflow-y: auto;
    min-height: 0;
  }
  .pile {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px;
    border: 2px solid #3f9e64;
    border-radius: 10px;
    background: rgb(74 222 128 / 0.08);
  }
  .pile.invalid {
    border-color: #e5484d;
    border-style: dashed;
    background: rgb(229 72 77 / 0.1);
  }
  .status {
    flex: none;
    width: 44px;
    height: 44px;
    border: 0;
    border-radius: 8px;
    background: #3f9e64;
    color: #fff;
    font-size: 20px;
    font-weight: 800;
    cursor: pointer;
  }
  .invalid .status {
    background: #e5484d;
  }
  .cards {
    display: flex;
    flex: 1;
    min-width: 0;
    overflow-x: auto;
    padding: 12px 4px 8px;
  }
  .cards > :global(*:not(:first-child)) {
    margin-left: 2px;
  }
  .place {
    flex: none;
    width: 44px;
    height: 60px;
    border: 2px dashed #8fb3ff;
    border-radius: 8px;
    background: transparent;
    color: #8fb3ff;
    font-size: 24px;
    cursor: pointer;
  }
  .place:disabled {
    opacity: 0.3;
    cursor: default;
  }
  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .hint {
    margin: 4px 0;
    color: #c6d1e6;
    font-size: 14px;
  }
  .hint.small {
    font-size: 13px;
  }
  button:focus-visible {
    outline: 3px solid #39a0ff;
    outline-offset: 2px;
  }
</style>
