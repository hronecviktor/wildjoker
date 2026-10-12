<script lang="ts">
  // A tutorial's coach panel: the step's explanation with Next and Skip, or,
  // once the player has started the step, just the next tap on one line.
  import { t } from "../i18n/index.svelte";
  import { leaveRoom } from "../lib/session.svelte";

  interface Props {
    step: string;
    /** 1-based step number and the number of steps. */
    n: number;
    total: number;
    text: string;
    /** The one-line instruction for the next tap, shown alone when started. */
    hint: string | null;
    started: boolean;
    /** The step only explains: a Next button, enabled when ready. */
    next: boolean;
    ready: boolean;
    onnext: () => void;
  }
  let { step, n, total, text, hint, started, next, ready, onnext }: Props = $props();
</script>

<section class="coach" class:compact={started} aria-live="polite" data-testid="tutorial" data-step={step}>
  {#if started && hint}
    <!-- Started: just the next tap, on one line, to leave room for the move. -->
    <p class="text hint" data-testid="tutorial-hint">{hint}</p>
    <button type="button" class="link" onclick={() => leaveRoom()} data-testid="tutorial-skip">
      {t("tutorial.skip_short")}
    </button>
  {:else}
    <p class="count">{t("tutorial.step", { n, total })}</p>
    <p class="text">{text}</p>
    <div class="buttons">
      <button type="button" class="link" onclick={() => leaveRoom()} data-testid="tutorial-skip">
        {t("tutorial.skip")}
      </button>
      {#if next}
        <button type="button" class="btn primary" disabled={!ready} onclick={onnext} data-testid="tutorial-next">
          {t("tutorial.next")}
        </button>
      {/if}
    </div>
  {/if}
</section>

<style>
  .coach {
    flex: none;
    margin: 0 6px 8px;
    padding: 10px 12px;
    border: 2px solid #f5b301;
    border-radius: 12px;
    background: #23283a;
  }
  .count {
    margin: 0 0 2px;
    color: #f5b301;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .text {
    margin: 0;
    font-size: 15px;
    line-height: 1.4;
  }
  .compact {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 6px 12px;
  }
  .hint {
    flex: 1;
    font-weight: 700;
    font-size: 16px;
  }
  .compact .link {
    flex: none;
    padding: 6px 0;
  }
  .buttons {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-top: 8px;
  }
  .link {
    padding: 8px 0;
    border: 0;
    background: none;
    color: var(--muted);
    font: inherit;
    font-size: 14px;
    text-decoration: underline;
    cursor: pointer;
  }
  .buttons .btn {
    margin-left: auto;
  }
</style>
