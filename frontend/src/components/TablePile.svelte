<script lang="ts">
  // A pile on the table. Tapping it takes it into your staging area (and adds
  // any selected cards); piles someone else is staging are greyed out.
  import { t } from "../i18n/index.svelte";
  import { cardLabel } from "../i18n/cards";
  import { withValues } from "../lib/jokers";
  import type { TablePile } from "../lib/protocol";
  import Card from "./Card.svelte";

  interface Props {
    pile: TablePile;
    lockedBy: string | null;
    mine: boolean;
    disabled: boolean;
    /** Cards that just arrived on the table (flashed). */
    fresh?: Set<number>;
    /** The pile just changed; ``changedBy`` names who changed it, if known. */
    changed?: boolean;
    changedBy?: string | null;
    onclick: () => void;
  }
  let {
    pile,
    lockedBy,
    mine,
    disabled,
    fresh = new Set(),
    changed = false,
    changedBy = null,
    onclick,
  }: Props = $props();

  const cards = $derived(withValues(pile.cards));
  const label = $derived(
    (lockedBy ? t("table.locked_by", { name: lockedBy }) + ": " : "") +
      cards.map((c) => cardLabel(c.id, c.value)).join(", "),
  );
</script>

<button
  type="button"
  class="pile"
  class:locked={!!lockedBy && !mine}
  class:mine
  class:changed
  data-nav="table"
  data-pile={pile.id}
  aria-label={label}
  aria-disabled={disabled || (!!lockedBy && !mine)}
  {onclick}
>
  <span class="cards">
    {#each cards as c (c.id)}
      <Card id={c.id} value={c.value} size="pile" fresh={fresh.has(c.id)} />
    {/each}
  </span>
  {#if lockedBy && !mine}
    <span class="who">🔒 {lockedBy}</span>
  {:else if mine}
    <span class="who mine">{t("table.in_staging")}</span>
  {/if}
  {#if changed && changedBy && !lockedBy}
    <span class="who changed-by">{changedBy}</span>
  {/if}
</button>

<style>
  .pile {
    position: relative;
    display: inline-flex;
    flex-direction: column;
    align-items: flex-start;
    min-height: 48px;
    padding: 6px 8px 8px;
    border: 1px solid rgb(255 255 255 / 0.12);
    border-radius: 10px;
    background: rgb(0 0 0 / 0.14);
    color: inherit;
    font: inherit;
    cursor: pointer;
  }
  .cards {
    display: flex;
  }
  /* Just changed: the outline pulses green and fades (3 s, see FRESH_MS). */
  .changed {
    animation: changed 3s ease-out forwards;
  }
  @keyframes changed {
    0%,
    60% {
      border-color: #2fe07a;
      box-shadow: 0 0 0 2px #2fe07a, 0 0 18px 2px rgb(47 224 122 / 0.6);
    }
    100% {
      border-color: rgb(255 255 255 / 0.12);
      box-shadow: none;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .changed {
      animation: none;
      border-color: #2fe07a;
    }
  }
  .cards > :global(*:not(:first-child)) {
    margin-left: -20px;
  }
  .pile[aria-disabled="true"] {
    cursor: default;
  }
  .locked .cards {
    opacity: 0.4;
    filter: grayscale(0.8);
  }
  .mine .cards {
    opacity: 0.55;
  }
  .who {
    position: absolute;
    left: 50%;
    top: 50%;
    transform: translate(-50%, -50%);
    padding: 2px 8px;
    border-radius: 999px;
    background: rgb(20 20 30 / 0.85);
    color: #fff;
    font-size: 13px;
    font-weight: 600;
    white-space: nowrap;
  }
  .who.mine {
    background: #2958c9;
  }
  .who.changed-by {
    z-index: 5; /* above flashing cards, which lift */
    top: 0;
    left: 8px;
    transform: translateY(-60%);
    background: #1f9d57;
    font-size: 12px;
    animation: fade-out 3s ease-in forwards;
  }
  @keyframes fade-out {
    0%,
    75% {
      opacity: 1;
    }
    100% {
      opacity: 0;
    }
  }
  .pile:focus-visible {
    outline: 3px solid #39a0ff;
    outline-offset: 2px;
  }
  @media (min-width: 900px) {
    .cards > :global(*:not(:first-child)) {
      margin-left: -22px;
    }
  }
</style>
