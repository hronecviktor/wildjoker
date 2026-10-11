<script lang="ts">
  import { t } from "../i18n/index.svelte";

  let { onclose }: { onclose: () => void } = $props();
  let dialog: HTMLDialogElement;
  $effect(() => {
    dialog.showModal();
  });

  const keys: [string, string][] = [
    ["← → ↑ ↓", "keys.arrows"],
    ["Enter", "keys.enter"],
    ["Esc", "keys.esc"],
    ["D", "keys.draw"],
    ["S", "keys.stage"],
    ["N", "keys.new_pile"],
    ["O", "keys.open"],
    ["H", "keys.hand"],
    ["T", "keys.table"],
    ["R", "keys.sort"],
    ["M", "keys.mute"],
    ["?", "keys.help"],
  ];
</script>

<dialog bind:this={dialog} class="help" aria-labelledby="help-title" onclose={onclose} data-testid="shortcuts">
  <h2 id="help-title">{t("keys.title")}</h2>
  <dl>
    {#each keys as [key, text] (key)}
      <dt><kbd>{key}</kbd></dt>
      <dd>{t(text)}</dd>
    {/each}
  </dl>
  <form method="dialog">
    <button class="btn primary">{t("app.close")}</button>
  </form>
</dialog>

<style>
  .help {
    max-width: min(440px, calc(100vw - 32px));
    padding: 18px 20px;
    border: 0;
    border-radius: 14px;
    background: #1b2a43;
    color: #fff;
  }
  .help::backdrop {
    background: rgb(0 0 0 / 0.55);
  }
  h2 {
    margin: 0 0 10px;
    font-size: 18px;
  }
  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 6px 14px;
    margin: 0 0 14px;
  }
  dt {
    text-align: right;
  }
  dd {
    margin: 0;
  }
  kbd {
    display: inline-block;
    min-width: 24px;
    padding: 1px 6px;
    border: 1px solid #5a6b8c;
    border-bottom-width: 2px;
    border-radius: 5px;
    background: #22304a;
    font: 600 13px/20px ui-monospace, monospace;
    text-align: center;
  }
  form {
    text-align: right;
  }
</style>
