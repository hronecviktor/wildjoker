<script lang="ts">
  // The player's hand: cards overlap to fit the width and wrap into
  // overlapping rows, keeping at least 44 px of every card tappable.
  import { t, tn } from "../i18n/index.svelte";
  import Card from "./Card.svelte";

  interface Props {
    cards: number[];
    selected: number[];
    borrowed: Set<number>;
    ontoggle: (card: number) => void;
    /** Tapping the empty part of the hand (puts selected pile cards back). */
    onplace?: () => void;
  }
  let { cards, selected, borrowed, ontoggle, onplace }: Props = $props();

  const MIN_STEP = 44;
  const ROW_STEP = 50;
  let width = $state(360);
  let wide = $state(typeof matchMedia !== "undefined" && matchMedia("(min-width: 900px)").matches);
  $effect(() => {
    const mq = matchMedia("(min-width: 900px)");
    const update = () => (wide = mq.matches);
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  });

  const cw = $derived(wide ? 70 : 58);
  const ch = $derived(wide ? 100 : 84);
  const layout = $derived.by(() => {
    const n = cards.length;
    const room = Math.max(0, width - cw - 4);
    const perRowMax = Math.max(1, Math.floor(room / MIN_STEP) + 1);
    const rows = Math.max(1, Math.ceil(n / perRowMax));
    const perRow = Math.ceil(n / rows);
    const step = perRow > 1 ? Math.min(cw + 6, room / (perRow - 1)) : 0;
    const rowWidth = (perRow - 1) * step + cw;
    const offset = Math.max(0, (width - rowWidth) / 2);
    return { rows, perRow, step, offset, height: (rows - 1) * ROW_STEP + ch + 12 };
  });
</script>

<!-- Tapping the background is a shortcut; the "to hand" button does the same. -->
<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_noninteractive_element_interactions -->
<div
  class="hand"
  bind:clientWidth={width}
  style:height="{layout.height}px"
  data-nav-group="hand"
  role="group"
  aria-label={tn("hand.label", cards.length)}
  onclick={(e) => e.target === e.currentTarget && onplace?.()}
>
  {#each cards as card, i (card)}
    {@const row = Math.floor(i / layout.perRow)}
    {@const col = i % layout.perRow}
    <Card
      id={card}
      nav="hand"
      selected={selected.includes(card)}
      borrowed={borrowed.has(card)}
      onclick={() => ontoggle(card)}
      style="position:absolute;left:{layout.offset + col * layout.step}px;top:{12 + row * ROW_STEP}px;z-index:{i +
        1}"
    />
  {:else}
    <p class="empty">{t("hand.empty")}</p>
  {/each}
</div>

<style>
  .hand {
    position: relative;
    width: 100%;
    min-height: 96px;
  }
  .empty {
    margin: 0;
    padding-top: 36px;
    text-align: center;
    color: var(--muted);
  }
</style>
