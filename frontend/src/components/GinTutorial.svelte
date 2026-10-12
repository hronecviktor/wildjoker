<script lang="ts">
  // The Gin tutorial's coach: explains the current step, rings what to tap
  // next and tells the game which moves the step allows. The steps live in
  // lib/ginTutorial.ts; the round is a real one, dealt by the server with
  // fixed cards, and the Teacher plays when a step asks for its turn.
  import { untrack } from "svelte";
  import { t, tn } from "../i18n/index.svelte";
  import { currentGinStep, GIN_STEPS, type GinStep, type GinTutorialView } from "../lib/ginTutorial";
  import type { GinView, StateMessage } from "../lib/protocol";
  import { conn } from "../lib/session.svelte";
  import { load, save } from "../lib/storage";
  import Coach from "./Coach.svelte";
  import TutorialRings from "./TutorialRings.svelte";

  interface Props {
    room: StateMessage;
    game: GinView;
    selected: number[];
    dig: number | null;
    /** The current step, for the game to check moves against. */
    step?: GinStep;
  }
  let { room, game, selected, dig, step = $bindable() }: Props = $props();

  // Remember the step across reloads of the same tutorial.
  const key = $derived(`tutorial.${room.code}`);
  let index = $state(load<number>(untrack(() => key), 0));
  const asked = new Set<string>();

  const view = $derived<GinTutorialView>({ game, you: room.you, selected, dig });
  const current = $derived(GIN_STEPS[Math.min(index, GIN_STEPS.length - 1)]);
  $effect(() => {
    step = current;
  });
  const ready = $derived(current.ready?.(view) ?? true);
  const guide = $derived(current.guide?.(view) ?? { targets: [] });
  const started = $derived(!!guide.hint && (selected.length > 0 || dig !== null));

  const labels = $derived({
    lay_down: t("gin.lay_down"),
    discard: t("gin.discard"),
    take: dig === null ? "" : tn("gin.take", game.discard.length - game.discard.indexOf(dig)),
  });

  // Skip ahead past steps the player has already done.
  $effect(() => {
    const next = currentGinStep(view, index);
    if (next !== index) index = next;
  });
  $effect(() => save(key, index));
  // Ask for the Teacher's turn once per step that wants it.
  $effect(() => {
    if (current.teacher && !asked.has(current.id)) {
      asked.add(current.id);
      void conn.request({ type: "tutorial_action", action: "teacher_turn" }).catch(() => {});
    }
  });

  function next() {
    index = currentGinStep(view, index + 1);
  }
</script>

<Coach
  step={current.id}
  n={Math.min(index, GIN_STEPS.length - 1) + 1}
  total={GIN_STEPS.length}
  text={t(current.text, labels)}
  hint={guide.hint ? t(guide.hint, { ...labels, ...guide.params }) : null}
  {started}
  next={!!current.next}
  {ready}
  onnext={next}
/>
<TutorialRings targets={guide.targets} />
