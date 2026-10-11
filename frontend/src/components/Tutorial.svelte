<script lang="ts">
  // The tutorial's coach panel: explains the current step and rings what to
  // tap next. The steps live in lib/tutorial.ts; the game is a real one,
  // dealt by the server with fixed cards.
  import { untrack } from "svelte";
  import { t } from "../i18n/index.svelte";
  import type { GameController } from "../lib/game.svelte";
  import type { StateMessage } from "../lib/protocol";
  import { conn, leaveRoom } from "../lib/session.svelte";
  import { load, save } from "../lib/storage";
  import { currentStep, STEPS, type TutorialView } from "../lib/tutorial";

  let { game, room }: { game: GameController; room: StateMessage } = $props();

  // Remember the step across reloads of the same tutorial.
  const key = $derived(`tutorial.${room.code}`);
  let index = $state(load<number>(untrack(() => key), 0));
  const asked = new Set<string>();

  const view = $derived<TutorialView>({
    hand: room.game?.hand ?? [],
    shownHand: game.hand,
    table: room.game?.table ?? [],
    opened: !!game.me?.opened,
    draft: game.draft,
    selected: game.selected,
    you: room.you,
  });
  const step = $derived(STEPS[Math.min(index, STEPS.length - 1)]);
  const ready = $derived(step.ready?.(view) ?? true);
  const guide = $derived(step.guide?.(view) ?? { targets: [] });
  const targets = $derived(guide.targets);
  // Once the player has started the step, only the next tap is shown, so the
  // panel stays small next to the move sheet and the hand.
  const started = $derived(!!guide.hint && (game.drafting || game.selected.length > 0));

  // Skip ahead past steps the player has already done.
  $effect(() => {
    const next = currentStep(view, index);
    if (next !== index) index = next;
  });
  $effect(() => save(key, index));
  // Ask for the Teacher's move once, when its step starts.
  $effect(() => {
    const action = step.teacher;
    if (action && !asked.has(action)) {
      asked.add(action);
      void conn.request({ type: "tutorial_action", action }).catch(() => {});
    }
  });
  $effect(() => {
    game.allowDraw = !!step.allowDraw;
    return () => (game.allowDraw = true);
  });

  function next() {
    index = currentStep(view, index + 1);
  }

  // Rings around the targets, following them as the layout changes.
  let rings = $state<{ x: number; y: number; w: number; h: number }[]>([]);
  $effect(() => {
    const selectors = targets;
    let frame = 0;
    let last = "";
    const measure = () => {
      const found = selectors.flatMap((sel) => [...document.querySelectorAll(sel)]);
      const next = found.map((el) => {
        const r = el.getBoundingClientRect();
        return { x: r.left, y: r.top, w: r.width, h: r.height };
      });
      const json = JSON.stringify(next);
      if (json !== last) [last, rings] = [json, next];
      frame = requestAnimationFrame(measure);
    };
    measure();
    return () => cancelAnimationFrame(frame);
  });

  /** A one-line instruction; a ``button`` parameter names one of ``labels``. */
  function hintText(hint: { key: string; params?: Record<string, string> }): string {
    const params: Record<string, string> = { ...hint.params };
    if (params.button) params.button = labels[params.button as keyof typeof labels];
    return t(hint.key, params);
  }

  const labels = $derived({
    draw: t("game.draw"),
    open: t("game.open"),
    new_pile: t("staging.new_pile"),
    done: t("staging.commit"),
    split: t("staging.split"),
  });
</script>

<section class="coach" class:compact={started} aria-live="polite" data-testid="tutorial" data-step={step.id}>
  {#if started && guide.hint}
    <!-- Started: just the next tap, on one line, to leave room for the move. -->
    <p class="text hint" data-testid="tutorial-hint">{hintText(guide.hint)}</p>
    <button type="button" class="link" onclick={() => leaveRoom()} data-testid="tutorial-skip">
      {t("tutorial.skip_short")}
    </button>
  {:else}
    <p class="count">{t("tutorial.step", { n: Math.min(index, STEPS.length - 1) + 1, total: STEPS.length })}</p>
    <p class="text">{t(step.text, labels)}</p>
    <div class="buttons">
      <button type="button" class="link" onclick={() => leaveRoom()} data-testid="tutorial-skip">
        {t("tutorial.skip")}
      </button>
      {#if step.next}
        <button type="button" class="btn primary" disabled={!ready} onclick={next} data-testid="tutorial-next">
          {t("tutorial.next")}
        </button>
      {/if}
    </div>
  {/if}
</section>

{#each rings as r, i (i)}
  <div
    class="ring"
    aria-hidden="true"
    style:left="{r.x - 4}px"
    style:top="{r.y - 4}px"
    style:width="{r.w + 8}px"
    style:height="{r.h + 8}px"
  ></div>
{/each}

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
  .ring {
    position: fixed;
    z-index: 60;
    border: 3px solid #f5b301;
    border-radius: 12px;
    pointer-events: none;
    animation: ring 1.2s ease-in-out infinite;
  }
  @keyframes ring {
    0%,
    100% {
      box-shadow: 0 0 0 0 rgb(245 179 1 / 0.7);
    }
    50% {
      box-shadow: 0 0 0 8px rgb(245 179 1 / 0);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .ring {
      animation: none;
    }
  }
</style>
