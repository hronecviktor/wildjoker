<script lang="ts">
  // The tutorial's coach panel: explains the current step and rings what to
  // tap next. The steps live in lib/tutorial.ts; the game is a real one,
  // dealt by the server with fixed cards.
  import { untrack } from "svelte";
  import { t } from "../i18n/index.svelte";
  import type { GameController } from "../lib/game.svelte";
  import { wildView, type StateMessage } from "../lib/protocol";
  import { conn } from "../lib/session.svelte";
  import { load, save } from "../lib/storage";
  import { currentStep, STEPS, type TutorialView } from "../lib/tutorial";
  import Coach from "./Coach.svelte";
  import TutorialRings from "./TutorialRings.svelte";

  let { game, room }: { game: GameController; room: StateMessage } = $props();

  // Remember the step across reloads of the same tutorial.
  const key = $derived(`tutorial.${room.code}`);
  let index = $state(load<number>(untrack(() => key), 0));
  const asked = new Set<string>();

  const view = $derived<TutorialView>({
    hand: wildView(room)?.hand ?? [],
    shownHand: game.hand,
    table: wildView(room)?.table ?? [],
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

<Coach
  step={step.id}
  n={Math.min(index, STEPS.length - 1) + 1}
  total={STEPS.length}
  text={t(step.text, labels)}
  hint={guide.hint ? hintText(guide.hint) : null}
  {started}
  next={!!step.next}
  {ready}
  onnext={next}
/>
<TutorialRings {targets} />
