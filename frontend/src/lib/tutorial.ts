// The tutorial's steps. The server deals a fixed game (see
// backend/src/wildjoker/server/tutorial.py); each step explains something,
// points at what to tap, and finishes when the player has done it (or with
// Next for steps that only explain). Steps are matched against the game
// state, not counted, so doing something early just skips ahead.

import { cardCode } from "./cards";
import * as D from "./draft";

export type TeacherAction = "teacher_opens" | "teacher_borrows";

/** What a step can look at. */
export interface TutorialView {
  /** Card ids in the player's real hand (server state). */
  hand: number[];
  /** Card ids in the hand as shown (with staged cards not in a pile). */
  shownHand: number[];
  table: { id: number; cards: number[]; locked_by: string | null }[];
  opened: boolean;
  /** Piles in the player's move, and the selected cards. */
  draft: D.Draft;
  selected: number[];
  you: string;
}

export interface Step {
  id: string;
  /** i18n key of the text: `tutorial.<id>`. */
  text: string;
  /** Only explains: the player taps Next. */
  next?: boolean;
  /** Next is enabled once this holds (default: at once). */
  ready?: (v: TutorialView) => boolean;
  /** The step is done once this holds. */
  done?: (v: TutorialView) => boolean;
  /** The Teacher's move to ask for when the step starts. */
  teacher?: TeacherAction;
  /** Drawing is only allowed in steps that ask for it. */
  allowDraw?: boolean;
  /** What to point at now, and the short instruction for it (an i18n key
   * plus parameters), shown alone once the player has started the step. */
  guide?: (v: TutorialView) => Guide;
}

export interface Guide {
  targets: string[];
  hint?: { key: string; params?: Record<string, string> };
}

// -- looking things up by card code ---------------------------------------------

const codeOf = (id: number) => cardCode(id);
const has = (ids: number[], code: string) => ids.some((id) => codeOf(id) === code);
const onTable = (v: TutorialView, code: string) => v.table.some((p) => has(p.cards, code));
const drafting = (v: TutorialView) => v.draft.piles.length > 0 || v.draft.taken.length > 0;
const pileWith = (v: TutorialView, code: string) => v.table.find((p) => has(p.cards, code));
const draftPileWith = (v: TutorialView, code: string) => v.draft.piles.find((p) => has(p.cards, code));
const isSelected = (v: TutorialView, code: string) => v.selected.some((id) => codeOf(id) === code);

/** Unselected cards in the shown hand with these codes. */
function handCards(v: TutorialView, codes: string): string[] {
  const ids = [...v.shownHand];
  const result: string[] = [];
  for (const code of codes.split(" ")) {
    const i = ids.findIndex((id) => codeOf(id) === code);
    if (i < 0) continue;
    const [id] = ids.splice(i, 1);
    if (!v.selected.includes(id)) result.push(`.hand [data-card="${id}"]`);
  }
  return result;
}

/** Unselected cards in the player's move with these codes. */
function sheetCards(v: TutorialView, codes: string): string[] {
  const ids = v.draft.piles.flatMap((p) => p.cards);
  return codes
    .split(" ")
    .map((code) => ids.find((id) => codeOf(id) === code && !v.selected.includes(id)))
    .filter((id): id is number => id !== undefined)
    .map((id) => `[data-testid="staging"] [data-card="${id}"]`);
}

const tablePile = (v: TutorialView, code: string) => {
  const pile = pileWith(v, code);
  return pile ? [`[data-pile="${pile.id}"]`] : [];
};

const COMMIT = '[data-testid="commit"]';

// -- the steps ------------------------------------------------------------------

const tap = (cards: string) => ({ key: "tutorial.h.cards", params: { cards } });
const button = (name: string) => ({ key: "tutorial.h.button", params: { button: name } });

export const STEPS: Step[] = [
  { id: "welcome", text: "tutorial.welcome", next: true },
  {
    id: "screen",
    text: "tutorial.screen",
    next: true,
    guide: () => ({ targets: ['[data-testid="players"]', '[data-testid="table"]', ".hand"] }),
  },
  {
    id: "draw",
    text: "tutorial.draw",
    allowDraw: true,
    done: (v) => has(v.hand, "6H") || onTable(v, "6H"),
    guide: () => ({ targets: ['[data-testid="draw"]'], hint: button("draw") }),
  },
  {
    id: "open",
    text: "tutorial.open",
    done: (v) => v.opened,
    guide: (v) => {
      const cards = handCards(v, "4H 5H 6H");
      if (cards.length) return { targets: cards, hint: tap("4♥ 5♥ 6♥") };
      return { targets: ['[data-testid="open"]'], hint: button("open") };
    },
  },
  {
    id: "teacher",
    text: "tutorial.teacher",
    next: true,
    teacher: "teacher_opens",
    ready: (v) => onTable(v, "9S"),
    guide: (v) => ({ targets: [...tablePile(v, "AD"), ...tablePile(v, "9S")] }),
  },
  {
    id: "draw_again",
    text: "tutorial.draw_again",
    allowDraw: true,
    done: (v) => has(v.hand, "7H") || onTable(v, "7H"),
    guide: () => ({ targets: ['[data-testid="draw"]'], hint: button("draw") }),
  },
  {
    id: "add",
    text: "tutorial.add",
    done: (v) => onTable(v, "7H") && !drafting(v),
    guide: (v) => {
      if (draftPileWith(v, "7H")) return { targets: [COMMIT], hint: button("done") };
      if (!isSelected(v, "7H")) return { targets: handCards(v, "7H"), hint: tap("7♥") };
      return { targets: tablePile(v, "4H"), hint: { key: "tutorial.h.hearts" } };
    },
  },
  {
    id: "joker",
    text: "tutorial.joker",
    done: (v) => onTable(v, "JK") && !drafting(v),
    guide: (v) => {
      if (draftPileWith(v, "JK")) return { targets: [COMMIT], hint: button("done") };
      const cards = handCards(v, "QS KS JK");
      if (cards.length) return { targets: cards, hint: { key: "tutorial.h.joker" } };
      return { targets: ['[data-testid="new-pile"]'], hint: button("new_pile") };
    },
  },
  {
    id: "split",
    text: "tutorial.split",
    // Done once the player's own 3♦ (the hand had one) is on the table.
    done: (v) => !has(v.hand, "3D") && !drafting(v),
    guide: (v) => {
      if (!draftPileWith(v, "AD")) return { targets: tablePile(v, "AD"), hint: { key: "tutorial.h.diamonds" } };
      const split = v.draft.piles.some((p) => has(p.cards, "4D") && !has(p.cards, "AD"));
      if (!split) {
        if (isSelected(v, "4D")) return { targets: ['[data-testid="split"]'], hint: button("split") };
        return { targets: sheetCards(v, "4D"), hint: { key: "tutorial.h.in_move", params: { cards: "4♦" } } };
      }
      const high = draftPileWith(v, "4D")!;
      if (has(high.cards, "3D")) return { targets: [COMMIT], hint: button("done") };
      if (!isSelected(v, "3D")) return { targets: handCards(v, "3D"), hint: { key: "tutorial.h.your", params: { cards: "3♦" } } };
      return {
        targets: [`[data-testid="draft-pile"]:has([data-card="${high.cards[0]}"]) [data-testid="place-here"]`],
        hint: { key: "tutorial.h.plus" },
      };
    },
  },
  {
    id: "locked",
    text: "tutorial.locked",
    next: true,
    teacher: "teacher_borrows",
    guide: (v) => ({ targets: tablePile(v, "4H") }),
  },
  {
    id: "take",
    text: "tutorial.take",
    guide: (v) => {
      if (!draftPileWith(v, "9S")) return { targets: tablePile(v, "9S"), hint: { key: "tutorial.h.nines" } };
      const run = v.draft.piles.find((p) => has(p.cards, "8C"));
      if (run && has(run.cards, "TC") && has(run.cards, "9C")) return { targets: [COMMIT], hint: button("done") };
      const picks = [...sheetCards(v, "9C"), ...handCards(v, "8C TC")];
      if (picks.length) return { targets: picks, hint: { key: "tutorial.h.take" } };
      return { targets: ['[data-testid="staging-new-pile"]'], hint: button("new_pile") };
    },
  },
];

/** The first step that isn't done yet, starting from `from`. */
export function currentStep(view: TutorialView, from: number): number {
  let i = from;
  while (i < STEPS.length && STEPS[i].done?.(view)) i++;
  return i;
}
