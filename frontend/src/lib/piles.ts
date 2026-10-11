// Pile validation, mirroring backend/src/wildjoker/engine/piles.py exactly
// (checked against shared/piles.json in piles.test.ts).
//
// - A pile with two or more natural cards of the same rank is a set;
//   otherwise it is tried as a run first, then as a set.
// - Runs are ordered low to high. An ace counts low when that works, high
//   otherwise. Jokers fill gaps first; extra jokers extend the top of the run
//   (up to the ace) and then the bottom.
// - Sets list the natural cards by suit (S, H, D, C), then the jokers.

import { isJoker, rankOf, suitOf, type Suit } from "./cards";

export const MIN_PILE = 3;
export const MAX_RUN = 13;
export const MAX_SET = 4;
const ACE_HIGH = 14;

export interface Arrangement {
  kind: "run" | "set";
  cards: number[];
  /** Runs: the rank each position stands for (1-14); sets: the shared rank. Null for all jokers. */
  values: number[] | null;
  /** Runs: the suit of the run; null for sets and all-joker piles. */
  suit: Suit | null;
}

/** The canonical arrangement of a valid pile, or null if it is invalid. */
export function arrange(cards: readonly number[]): Arrangement | null {
  const naturals = cards.filter((c) => !isJoker(c));
  if (naturals.length >= 2 && rankOf(naturals[0]) === rankOf(naturals[1])) return asSet(cards);
  return asRun(cards) ?? asSet(cards);
}

export const isValidPile = (cards: readonly number[]) => arrange(cards) !== null;

/** An opening is a run of 3 or more cards without jokers. */
export function isValidOpening(cards: readonly number[]): boolean {
  if (cards.some(isJoker)) return false;
  return arrange(cards)?.kind === "run";
}

function range(lo: number, hi: number): number[] {
  return Array.from({ length: hi - lo + 1 }, (_, i) => lo + i);
}

function asRun(cards: readonly number[]): Arrangement | null {
  const n = cards.length;
  if (n < MIN_PILE || n > MAX_RUN) return null;
  const naturals = cards.filter((c) => !isJoker(c));
  const jokers = cards.filter(isJoker);
  if (naturals.length === 0) return { kind: "run", cards: [...cards], values: range(1, n), suit: null };

  const suit = suitOf(naturals[0]);
  if (naturals.some((c) => suitOf(c) !== suit)) return null;
  if (new Set(naturals.map(rankOf)).size !== naturals.length) return null;

  const hasAce = naturals.some((c) => rankOf(c) === 1);
  for (const aceValue of hasAce ? [1, ACE_HIGH] : [1]) {
    const byValue = new Map<number, number>();
    for (const c of naturals) byValue.set(rankOf(c) === 1 ? aceValue : rankOf(c)!, c);
    const lo = Math.min(...byValue.keys());
    const hi = Math.max(...byValue.keys());
    if (hi - lo + 1 > n) continue;
    const top = Math.min(ACE_HIGH, lo + n - 1);
    const bottom = top - n + 1;
    let spare = 0;
    const values = range(bottom, top);
    const ordered = values.map((v) => byValue.get(v) ?? jokers[spare++]);
    return { kind: "run", cards: ordered, values, suit };
  }
  return null;
}

function asSet(cards: readonly number[]): Arrangement | null {
  const n = cards.length;
  if (n < MIN_PILE || n > MAX_SET) return null;
  const naturals = cards.filter((c) => !isJoker(c));
  const jokers = cards.filter(isJoker);
  const ranks = new Set(naturals.map(rankOf));
  if (ranks.size > 1) return null;
  if (new Set(naturals.map(suitOf)).size !== naturals.length) return null;
  const rank = ranks.size ? [...ranks][0]! : null;
  const ordered = [...naturals].sort((a, b) => suitOf(a)! - suitOf(b)!).concat(jokers);
  return { kind: "set", cards: ordered, values: rank === null ? null : Array(n).fill(rank), suit: null };
}

/** The longest joker-free run in `cards`, or null if there is none. */
export function findOpening(cards: readonly number[]): number[] | null {
  const bySuit = new Map<Suit, Map<number, number>>();
  for (const c of cards) {
    if (isJoker(c)) continue;
    const s = suitOf(c)!;
    if (!bySuit.has(s)) bySuit.set(s, new Map());
    const ranks = bySuit.get(s)!;
    ranks.set(rankOf(c)!, c);
    if (rankOf(c) === 1) ranks.set(ACE_HIGH, c);
  }
  let best: number[] = [];
  for (const ranks of bySuit.values()) {
    let run: number[] = [];
    for (let value = 1; value <= ACE_HIGH; value++) {
      const card = ranks.get(value);
      if (card !== undefined && run.length < MAX_RUN) run.push(card);
      else run = card !== undefined ? [card] : [];
      if (run.length > best.length) best = [...run];
    }
  }
  return best.length >= MIN_PILE ? best : null;
}
