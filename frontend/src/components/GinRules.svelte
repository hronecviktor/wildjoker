<script lang="ts">
  // The rules of Gin in short (RULES-GIN.md), from the start page, the
  // lobby and the game.
  import { t } from "../i18n/index.svelte";

  let { onclose }: { onclose: () => void } = $props();
  let dialog: HTMLDialogElement;
  $effect(() => {
    dialog.showModal();
  });
</script>

<dialog bind:this={dialog} class="rules" aria-labelledby="gin-rules-title" {onclose} data-testid="gin-rules">
  <h2 id="gin-rules-title">{t("gin.rules_title")}</h2>
  <div class="body">
    <p>{t("gin.rules_goal")}</p>
    <p>{t("gin.rules_melds")}</p>
    <p>{t("gin.rules_turn")}</p>
    <ol>
      <li>{t("gin.rules_draw")}</li>
      <li>{t("gin.rules_play")}</li>
      <li>{t("gin.rules_discard")}</li>
    </ol>
    <p>{t("gin.rules_end")}</p>
    <p>{t("gin.rules_values")}</p>
    <p>{t("gin.rules_stock")}</p>
  </div>
  <form method="dialog">
    <button class="btn primary">{t("app.close")}</button>
  </form>
</dialog>

<style>
  .rules {
    display: flex;
    flex-direction: column;
    max-width: min(480px, calc(100vw - 32px));
    max-height: calc(100dvh - 32px);
    padding: 18px 20px;
    border: 0;
    border-radius: 14px;
    background: #1b2a43;
    color: #fff;
  }
  .rules:not([open]) {
    display: none;
  }
  .rules::backdrop {
    background: rgb(0 0 0 / 0.55);
  }
  h2 {
    margin: 0 0 10px;
    font-size: 20px;
  }
  .body {
    overflow-y: auto;
    line-height: 1.45;
  }
  p {
    margin: 0 0 10px;
  }
  ol {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin: 0 0 10px;
    padding-left: 22px;
  }
  form {
    display: flex;
    justify-content: flex-end;
    margin-top: 8px;
  }
</style>
