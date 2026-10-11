// The local half of a move (RULES.md "After opening"): piles taken off the
// table plus new piles, rearranged on the client until they are all valid,
// then sent as one `commit`. The server never sees a half-finished draft.
//
// A draft only lists the cards in its piles. The hand shown to the player is
// their real hand plus staged cards that aren't in any pile.

import { arrange } from "./piles";

export interface DraftPile {
  /** Stable key for rendering and targeting. */
  key: number;
  cards: number[];
  /** The table pile it was taken from, if any. */
  from?: number;
}

export interface Draft {
  piles: DraftPile[];
  /** Table pile ids already brought into the draft. */
  taken: number[];
  nextKey: number;
}

export type Target = { kind: "pile"; key: number } | { kind: "hand" } | { kind: "new" };

export const emptyDraft = (): Draft => ({ piles: [], taken: [], nextKey: 1 });

export const isEmpty = (d: Draft) => d.piles.length === 0 && d.taken.length === 0;

/** Cards to show in the hand: the real hand plus staged cards not in a pile. */
export function handCards(d: Draft, hand: readonly number[], staged: readonly number[]): number[] {
  const inPiles = new Set(d.piles.flatMap((p) => p.cards));
  return [...hand, ...staged].filter((c) => !inPiles.has(c));
}

/** Move cards (from the hand or any pile) to a target; empty piles disappear. */
export function moveCards(d: Draft, cards: readonly number[], target: Target): Draft {
  const moving = new Set(cards);
  let nextKey = d.nextKey;
  let piles = d.piles.map((p) => ({ ...p, cards: p.cards.filter((c) => !moving.has(c)) }));
  if (target.kind === "pile") {
    piles = piles.map((p) => (p.key === target.key ? { ...p, cards: [...p.cards, ...cards] } : p));
  } else if (target.kind === "new" && cards.length) {
    piles.push({ key: nextKey++, cards: [...cards] });
  }
  return { ...d, piles: piles.filter((p) => p.cards.length > 0), nextKey };
}

/** Split a pile before position `index` of its displayed order. */
export function splitPile(d: Draft, key: number, index: number): Draft {
  const pile = d.piles.find((p) => p.key === key);
  if (!pile) return d;
  const shown = displayOrder(pile.cards);
  if (index <= 0 || index >= shown.length) return d;
  const piles = d.piles.flatMap((p) =>
    p.key === key
      ? [
          { ...p, cards: shown.slice(0, index) },
          { key: d.nextKey, cards: shown.slice(index) },
        ]
      : [p],
  );
  return { ...d, piles, nextKey: d.nextKey + 1 };
}

/** Bring a newly staged table pile into the draft (once per pile). */
export function addTaken(d: Draft, pileId: number, cards: readonly number[]): Draft {
  if (d.taken.includes(pileId)) return d;
  return {
    piles: [...d.piles, { key: d.nextKey, cards: [...cards], from: pileId }],
    taken: [...d.taken, pileId],
    nextKey: d.nextKey + 1,
  };
}

/**
 * Bring the draft in line with a new server state: add newly staged piles,
 * forget piles no longer staged (cancelled or expired) and drop cards the
 * player no longer has.
 */
export function reconcile(
  d: Draft,
  hand: readonly number[],
  staged: readonly { id: number; cards: readonly number[] }[],
): Draft {
  const stagedIds = new Set(staged.map((p) => p.id));
  let next: Draft = { ...d, taken: d.taken.filter((id) => stagedIds.has(id)) };
  const available = new Set([...hand, ...staged.flatMap((p) => p.cards)]);
  const piles = next.piles
    .map((p) => ({ ...p, cards: p.cards.filter((c) => available.has(c)) }))
    .filter((p) => p.cards.length > 0);
  next = { ...next, piles };
  for (const p of staged) next = addTaken(next, p.id, p.cards);
  return next;
}

/** Valid piles in canonical order; invalid ones as the player built them. */
export function displayOrder(cards: readonly number[]): number[] {
  return arrange(cards)?.cards ?? [...cards];
}

export const pileValid = (p: DraftPile) => arrange(p.cards) !== null;

/** Whether the draft can be committed: every pile valid and something to do. */
export function canCommit(d: Draft, staging: boolean): boolean {
  return (staging || d.piles.length > 0) && d.piles.every(pileValid);
}

export const commitPayload = (d: Draft) => d.piles.map((p) => displayOrder(p.cards));
