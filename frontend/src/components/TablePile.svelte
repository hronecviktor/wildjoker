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
    onclick: () => void;
  }
  let { pile, lockedBy, mine, disabled, onclick }: Props = $props();

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
  data-nav="table"
  data-pile={pile.id}
  aria-label={label}
  aria-disabled={disabled || (!!lockedBy && !mine)}
  {onclick}
>
  <span class="cards">
    {#each cards as c (c.id)}
      <Card id={c.id} value={c.value} size="pile" />
    {/each}
  </span>
  {#if lockedBy && !mine}
    <span class="who">🔒 {lockedBy}</span>
  {:else if mine}
    <span class="who mine">{t("table.in_staging")}</span>
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
