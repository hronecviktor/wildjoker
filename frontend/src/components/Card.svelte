<script lang="ts">
  // One playing card, drawn with CSS. Suits have their own colour and symbol,
  // so they can be told apart without colour too.
  import { isJoker, rankLabel, rankOf, suitOf, SUIT_SYMBOLS } from "../lib/cards";
  import { cardLabel, type JokerValue } from "../i18n/cards";

  interface Props {
    id: number;
    size?: "hand" | "pile" | "mini";
    selected?: boolean;
    /** What a joker stands for in its pile. */
    value?: JokerValue | null;
    /** Marks a card that came from a table pile. */
    borrowed?: boolean;
    /** A card just drawn: flashes so it's easy to spot in the hand. */
    fresh?: boolean;
    onclick?: (e: MouseEvent) => void;
    nav?: string;
    style?: string;
  }
  let {
    id,
    size = "hand",
    selected = false,
    value = null,
    borrowed = false,
    fresh = false,
    onclick,
    nav,
    style,
  }: Props =
    $props();

  const joker = $derived(isJoker(id));
  const suit = $derived(suitOf(id));
  const rank = $derived(joker ? "" : rankLabel(rankOf(id)!));
  const symbol = $derived(suit === null ? "★" : SUIT_SYMBOLS[suit]);
  const hint = $derived(
    joker && value ? rankLabel(value.rank) + (value.suit === null ? "" : SUIT_SYMBOLS[value.suit]) : "",
  );
  const label = $derived(cardLabel(id, value));
</script>

{#snippet face()}
  <span class="corner">
    {#if joker}
      <span class="sym">★</span><span class="joker-word">JOKER</span>
    {:else}
      <span class="rank">{rank}</span><span class="sym">{symbol}</span>
    {/if}
  </span>
  <span class="pip" aria-hidden="true">{symbol}</span>
  {#if hint}<span class="hint">{hint}</span>{/if}
  {#if selected}<span class="check" aria-hidden="true">✓</span>{/if}
{/snippet}

{#if onclick}
  <button
    type="button"
    class="card {size}"
    class:joker
    class:selected
    class:borrowed
    class:fresh
    data-suit={suit ?? "j"}
    data-nav={nav}
    data-card={id}
    aria-label={label}
    aria-pressed={selected}
    {style}
    {onclick}>{@render face()}</button
  >
{:else}
  <span
    class="card {size}"
    class:joker
    class:borrowed
    class:fresh
    data-suit={suit ?? "j"}
    data-card={id}
    role="img"
    aria-label={label}
    {style}>{@render face()}</span
  >
{/if}

<style>
  .card {
    --w: 58px;
    --h: 84px;
    --corner: 17px;
    position: relative;
    display: inline-block;
    flex: none;
    width: var(--w);
    height: var(--h);
    padding: 0;
    border: 1px solid #b9bcc4;
    border-radius: 7px;
    background: linear-gradient(160deg, #fff 60%, #f1f2f5);
    box-shadow: 0 1px 2px rgb(0 0 0 / 0.35);
    color: var(--suit);
    font: inherit;
    text-align: left;
    cursor: default;
    user-select: none;
    -webkit-tap-highlight-color: transparent;
    transition: transform 0.12s ease, box-shadow 0.12s ease;
  }
  button.card {
    cursor: pointer;
  }
  .pile {
    --w: 42px;
    --h: 60px;
    --corner: 14px;
    border-radius: 5px;
  }
  .mini {
    --w: 30px;
    --h: 42px;
    --corner: 11px;
    border-radius: 4px;
  }
  [data-suit="0"] {
    --suit: #1d2330;
  }
  [data-suit="1"] {
    --suit: #d0202a;
  }
  [data-suit="2"] {
    --suit: #1f5fd6;
  }
  [data-suit="3"] {
    --suit: #13803c;
  }
  .joker {
    --suit: #7b2ff2;
    background: linear-gradient(160deg, #fff 45%, #efe4ff);
    border-color: #a77df5;
  }
  .corner {
    position: absolute;
    top: 3px;
    left: 4px;
    display: flex;
    flex-direction: column;
    align-items: center;
    line-height: 0.95;
    font-size: var(--corner);
    font-weight: 700;
    letter-spacing: -0.03em;
  }
  .sym {
    font-size: 0.95em;
  }
  .joker-word {
    margin-top: 2px;
    writing-mode: vertical-rl;
    text-orientation: upright;
    font-size: 0.5em;
    letter-spacing: -0.12em;
    line-height: 1;
  }
  .pip {
    position: absolute;
    right: 5px;
    bottom: 2px;
    font-size: calc(var(--h) * 0.42);
    line-height: 1;
    opacity: 0.9;
  }
  .mini .pip {
    display: none;
  }
  .joker .pip {
    right: 4px;
    font-size: calc(var(--h) * 0.38);
  }
  .hint {
    position: absolute;
    left: 50%;
    bottom: -2px;
    transform: translate(-50%, 50%);
    padding: 0 3px;
    border-radius: 4px;
    background: #7b2ff2;
    color: #fff;
    font-size: 10px;
    font-weight: 700;
    line-height: 14px;
    white-space: nowrap;
  }
  .selected {
    transform: translateY(-10px);
    border-color: #f5b301;
    box-shadow:
      0 0 0 3px #f5b301,
      0 6px 10px rgb(0 0 0 / 0.35);
  }
  /* A card just drawn: a green glow that pulses, then fades (3 s, see FRESH_MS). */
  .fresh {
    z-index: 3;
    border-color: #2fe07a;
    animation: fresh 3s ease-out forwards;
  }
  .fresh.selected {
    border-color: #f5b301;
  }
  @keyframes fresh {
    0%,
    30%,
    60% {
      transform: translateY(-14px) scale(1.08);
      box-shadow:
        0 0 0 4px #2fe07a,
        0 0 22px 6px rgb(47 224 122 / 0.85);
    }
    15%,
    45%,
    75% {
      transform: translateY(-6px) scale(1);
      box-shadow:
        0 0 0 3px #2fe07a,
        0 0 8px 2px rgb(47 224 122 / 0.5);
    }
    100% {
      transform: none;
      box-shadow: 0 0 0 2px rgb(47 224 122 / 0);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .fresh {
      animation: none;
      box-shadow: 0 0 0 4px #2fe07a;
    }
  }
  .check {
    position: absolute;
    top: -8px;
    right: -6px;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: #f5b301;
    color: #1d2330;
    font-size: 13px;
    line-height: 20px;
    text-align: center;
    font-weight: 800;
  }
  .borrowed::after {
    content: "";
    position: absolute;
    inset: 2px;
    border: 2px dashed #7aa7ff;
    border-radius: 5px;
    pointer-events: none;
  }
  button.card:focus-visible {
    outline: 3px solid #39a0ff;
    outline-offset: 2px;
    z-index: 50 !important;
  }
  @media (min-width: 900px) {
    .card.hand {
      --w: 70px;
      --h: 100px;
      --corner: 20px;
    }
    .pile {
      --w: 48px;
      --h: 68px;
      --corner: 15px;
    }
  }
</style>
