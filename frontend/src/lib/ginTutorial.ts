// The Gin tutorial's steps. The server deals one fixed round (see
// backend/src/wildjoker/server/gin_tutorial.py); each step explains
// something, rings what to tap, and finishes when the player has done it.
// Steps are matched against the game state, so a reload picks up where the
// player was. Each step also says which moves it allows, so a tap off the
// script can't lead the round somewhere the steps don't go.

import { cardCode } from "./cards";
import type { GinView } from "./protocol";

/** What a step can look at. */
export interface GinTutorialView {
  game: GinView;
  you: string;
  selected: number[];
  /** The deeper discard picked, waiting for Take. */
  dig: number | null;
}

export type Move = "draw" | "take" | "meld" | "lay_off" | "discard";

export interface GinStep {
  id: string;
  /** i18n key of the text. */
  text: string;
  /** Only explains: the player taps Next once ``ready`` holds. */
  next?: boolean;
  ready?: (v: GinTutorialView) => boolean;
  done?: (v: GinTutorialView) => boolean;
  /** Ask for the Teacher's turn when the step starts. */
  teacher?: boolean;
  /** The moves allowed, each with the cards it may use (by code, all of them). */
  allow?: Partial<Record<Move, string>>;
  guide?: (v: GinTutorialView) => { targets: string[]; hint?: string; params?: Record<string, string> };
}

const code = (id: number) => cardCode(id);
const inHand = (v: GinTutorialView, c: string) => (v.game.hand ?? []).some((id) => code(id) === c);
const onTable = (v: GinTutorialView, c: string) => v.game.melds.some((m) => m.cards.some((id) => code(id) === c));
const myTurn = (v: GinTutorialView) => v.game.status === "playing" && v.game.turn === v.you;
const isSelected = (v: GinTutorialView, c: string) => v.selected.some((id) => code(id) === c);

/** Hand cards by code that aren't selected yet. */
function handCards(v: GinTutorialView, codes: string): string[] {
  return codes
    .split(" ")
    .map((c) => (v.game.hand ?? []).find((id) => code(id) === c && !v.selected.includes(id)))
    .filter((id): id is number => id !== undefined)
    .map((id) => `.hand [data-card="${id}"]`);
}

const allSelected = (v: GinTutorialView, codes: string) => codes.split(" ").every((c) => isSelected(v, c));

function meldOf(v: GinTutorialView, c: string): string[] {
  const meld = v.game.melds.find((m) => m.cards.some((id) => code(id) === c));
  return meld ? [`[data-meld="${meld.id}"]`] : [];
}

function discardCard(v: GinTutorialView, c: string): string[] {
  const id = v.game.discard.find((d) => code(d) === c);
  return id === undefined ? [] : [`[data-testid="discard"] [data-card="${id}"]`];
}

const DECK = '[data-testid="deck"]';
const LAY_DOWN = '[data-testid="lay-down"]';
const DISCARD = '[data-testid="discard-btn"]';
const TAKE = '[data-testid="take"]';

/** Select these cards, then tap ``then``. */
function selectThen(v: GinTutorialView, codes: string, label: string, then: string[], thenHint: string) {
  if (!allSelected(v, codes)) return { targets: handCards(v, codes), hint: "gin_tutorial.h.cards", params: { cards: label } };
  return { targets: then, hint: thenHint };
}

export const GIN_STEPS: GinStep[] = [
  { id: "welcome", text: "gin_tutorial.welcome", next: true },
  {
    id: "screen",
    text: "gin_tutorial.screen",
    next: true,
    guide: () => ({ targets: ['[data-testid="players"]', '[data-testid="discard"]', DECK] }),
  },
  {
    id: "draw",
    text: "gin_tutorial.draw",
    allow: { draw: "" },
    done: (v) => inHand(v, "7H") || onTable(v, "7H"),
    guide: () => ({ targets: [DECK], hint: "gin_tutorial.h.deck" }),
  },
  {
    id: "meld",
    text: "gin_tutorial.meld",
    allow: { meld: "5H 6H 7H" },
    done: (v) => onTable(v, "7H"),
    guide: (v) => selectThen(v, "5H 6H 7H", "5♥ 6♥ 7♥", [LAY_DOWN], "gin_tutorial.h.lay_down"),
  },
  {
    id: "discard",
    text: "gin_tutorial.discard",
    allow: { discard: "KS" },
    done: (v) => !inHand(v, "KS") || !myTurn(v),
    guide: (v) => selectThen(v, "KS", "K♠", [DISCARD], "gin_tutorial.h.discard"),
  },
  {
    id: "teacher",
    text: "gin_tutorial.teacher",
    next: true,
    teacher: true,
    ready: (v) => myTurn(v) && onTable(v, "9S"),
    guide: (v) => ({ targets: [...meldOf(v, "9S"), ...discardCard(v, "4D")] }),
  },
  {
    id: "dig",
    text: "gin_tutorial.dig",
    allow: { take: "8H" },
    done: (v) => inHand(v, "8H") || onTable(v, "8H"),
    guide: (v) => {
      if (v.dig === null) return { targets: discardCard(v, "8H"), hint: "gin_tutorial.h.dig" };
      return { targets: [TAKE], hint: "gin_tutorial.h.take" };
    },
  },
  {
    id: "own",
    text: "gin_tutorial.own",
    allow: { lay_off: "8H" },
    done: (v) => onTable(v, "8H"),
    guide: (v) => selectThen(v, "8H", "8♥", meldOf(v, "5H"), "gin_tutorial.h.hearts"),
  },
  {
    id: "other",
    text: "gin_tutorial.other",
    allow: { lay_off: "9C" },
    done: (v) => onTable(v, "9C"),
    guide: (v) => selectThen(v, "9C", "9♣", meldOf(v, "9S"), "gin_tutorial.h.nines"),
  },
  {
    id: "discard_again",
    text: "gin_tutorial.discard_again",
    allow: { discard: "4D" },
    done: (v) => !inHand(v, "4D") && !inHand(v, "8H"),
    guide: (v) => selectThen(v, "4D", "4♦", [DISCARD], "gin_tutorial.h.discard"),
  },
  {
    id: "teacher_again",
    text: "gin_tutorial.teacher_again",
    next: true,
    teacher: true,
    ready: (v) => myTurn(v),
    guide: (v) => ({ targets: ['[data-testid="players"]', ...discardCard(v, "QD")] }),
  },
  {
    id: "draw_last",
    text: "gin_tutorial.draw_last",
    allow: { draw: "" },
    done: (v) => inHand(v, "TC") || onTable(v, "TC"),
    guide: () => ({ targets: [DECK], hint: "gin_tutorial.h.deck" }),
  },
  {
    id: "joker",
    text: "gin_tutorial.joker",
    allow: { meld: "TC JC QC JK" },
    done: (v) => onTable(v, "JK"),
    guide: (v) => selectThen(v, "TC JC QC JK", "10♣ J♣ Q♣ ★", [LAY_DOWN], "gin_tutorial.h.lay_down"),
  },
  {
    id: "gin",
    text: "gin_tutorial.gin",
    allow: { discard: "KS" },
    guide: (v) => selectThen(v, "KS", "K♠", [DISCARD], "gin_tutorial.h.discard"),
  },
];

/** The first step that isn't done yet, starting from `from`. */
export function currentGinStep(view: GinTutorialView, from: number): number {
  let i = from;
  while (i < GIN_STEPS.length && GIN_STEPS[i].done?.(view)) i++;
  return i;
}

/** Whether a step allows a move with these cards. */
export function allows(step: GinStep, move: Move, cards: number[]): boolean {
  const allowed = step.allow?.[move];
  if (allowed === undefined) return false;
  const wanted = allowed.split(" ").filter(Boolean).sort();
  return JSON.stringify(cards.map(code).sort()) === JSON.stringify(wanted);
}
