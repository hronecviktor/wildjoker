<script lang="ts">
  // Between Gin rounds: who went out, everyone's points on the table and in
  // hand, the round's scores and the totals; the host deals the next round.
  import { t } from "../i18n/index.svelte";
  import { cardLabel } from "../i18n/cards";
  import type { GinView, StateMessage } from "../lib/protocol";
  import { act, conn } from "../lib/session.svelte";
  import Card from "./Card.svelte";

  let { room, game }: { room: StateMessage; game: GinView } = $props();

  const result = $derived(game.result!);
  const isHost = $derived(room.host === room.you);
  const name = (id: string) => room.players.find((p) => p.id === id)?.name ?? "?";
  const rows = $derived(
    room.players
      .filter((p) => p.id in game.scores)
      .map((p) => ({
        id: p.id,
        name: p.id === room.you ? `${p.name} (${t("players.you")})` : p.name,
        table: result.table[p.id] ?? 0,
        hand: result.hand[p.id] ?? 0,
        round: result.scores[p.id] ?? 0,
        total: game.scores[p.id] ?? 0,
        left: result.hands[p.id] ?? [],
      }))
      .sort((a, b) => b.total - a.total),
  );
  const top = $derived(Math.max(...Object.values(game.scores)));
  const tie = $derived(top >= game.target && Object.values(game.scores).filter((s) => s === top).length > 1);
  const signed = (n: number) => (n > 0 ? `+${n}` : String(n));

  let dialog: HTMLDialogElement;
  $effect(() => {
    dialog.showModal();
  });
</script>

<dialog
  bind:this={dialog}
  class="round-over"
  aria-labelledby="round-over-title"
  data-testid="round-over"
  oncancel={(e) => e.preventDefault()}
>
  <h2 id="round-over-title">{t("gin.round_over", { n: game.round })}</h2>
  <p class="headline">
    {#if result.gin === null}
      {t("gin.stock_out")}
    {:else if result.gin === room.you}
      🎉 {t("gin.went_out_you")}
    {:else}
      {t("gin.went_out", { name: name(result.gin) })}
    {/if}
  </p>

  <table>
    <thead>
      <tr>
        <th scope="col">{t("gin.col_player")}</th>
        <th scope="col">{t("gin.col_table")}</th>
        <th scope="col">{t("gin.col_hand")}</th>
        <th scope="col">{t("gin.col_round")}</th>
        <th scope="col">{t("gin.col_total")}</th>
      </tr>
    </thead>
    <tbody>
      {#each rows as row (row.id)}
        <tr class:me={row.id === room.you}>
          <th scope="row">
            {row.name}
            {#if row.left.length}
              <span
                class="left"
                role="img"
                aria-label={t("gin.cards_left", { cards: row.left.map((c) => cardLabel(c)).join(", ") })}
              >
                {#each row.left as card (card)}<Card id={card} size="mini" />{/each}
              </span>
            {/if}
          </th>
          <td>{row.table}</td>
          <td>{row.hand ? -row.hand : 0}</td>
          <td class:neg={row.round < 0}>{signed(row.round)}</td>
          <td class="total" data-testid="total">{row.total}</td>
        </tr>
      {/each}
    </tbody>
  </table>

  <p class="note">{tie ? t("gin.tie_again") : t("gin.first_to", { n: game.target })}</p>

  {#if isHost}
    <button
      type="button"
      class="btn primary big"
      data-testid="next-round"
      onclick={() => act(() => conn.request({ type: "next_round" }))}>{t("gin.next_round")}</button
    >
  {:else}
    <p class="wait">{t("gin.waiting_host")}</p>
  {/if}
</dialog>

<style>
  .round-over {
    width: min(520px, calc(100vw - 24px));
    max-height: calc(100dvh - 24px);
    padding: 18px 16px;
    border: 0;
    border-radius: 14px;
    background: #1b2a43;
    color: #fff;
  }
  .round-over::backdrop {
    background: rgb(0 0 0 / 0.55);
  }
  h2 {
    margin: 0;
    font-size: 21px;
  }
  .headline {
    margin: 4px 0 12px;
    font-size: 17px;
    font-weight: 600;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-variant-numeric: tabular-nums;
  }
  th,
  td {
    padding: 8px 4px;
    border-bottom: 1px solid rgb(255 255 255 / 0.1);
    text-align: right;
  }
  thead th {
    color: var(--muted);
    font-size: 12px;
    font-weight: 600;
  }
  th[scope="row"],
  thead th:first-child {
    text-align: left;
  }
  th[scope="row"] {
    font-weight: 600;
  }
  tr.me th[scope="row"] {
    color: #8fb6ff;
  }
  .left {
    display: flex;
    flex-wrap: wrap;
    gap: 2px;
    margin-top: 4px;
  }
  .neg {
    color: #ff9aa5;
  }
  .total {
    font-size: 18px;
    font-weight: 800;
  }
  .note,
  .wait {
    margin: 12px 0;
    color: var(--muted);
  }
  .btn {
    width: 100%;
  }
</style>
