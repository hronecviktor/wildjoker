<script lang="ts">
  // How to install on an iPhone or iPad, which has no install prompt.
  import { t } from "../i18n/index.svelte";

  let { onclose }: { onclose: () => void } = $props();
  let dialog: HTMLDialogElement;
  $effect(() => {
    dialog.showModal();
  });
</script>

<dialog bind:this={dialog} class="install" aria-labelledby="install-title" {onclose} data-testid="install-help">
  <h2 id="install-title">{t("install.ios_title")}</h2>
  <ol>
    <li>
      {t("install.ios_share")}
      <!-- The iOS share symbol: a box with an arrow pointing up. -->
      <svg class="share" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 3v12M7.5 7.5 12 3l4.5 4.5" />
        <path d="M8 10H6a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-9a1 1 0 0 0-1-1h-2" />
      </svg>
    </li>
    <li>{t("install.ios_add")}</li>
    <li>{t("install.ios_done")}</li>
  </ol>
  <form method="dialog">
    <button class="btn primary">{t("app.close")}</button>
  </form>
</dialog>

<style>
  .install {
    max-width: min(400px, calc(100vw - 32px));
    padding: 18px 20px;
    border: 0;
    border-radius: 14px;
    background: #1b2a43;
    color: #fff;
  }
  .install::backdrop {
    background: rgb(0 0 0 / 0.55);
  }
  h2 {
    margin: 0 0 12px;
    font-size: 19px;
  }
  ol {
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin: 0 0 16px;
    padding-left: 22px;
    line-height: 1.4;
  }
  .share {
    width: 22px;
    height: 22px;
    margin-left: 2px;
    vertical-align: -5px;
    fill: none;
    stroke: #4d9bff;
    stroke-width: 2;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
  form {
    display: flex;
    justify-content: flex-end;
  }
</style>
