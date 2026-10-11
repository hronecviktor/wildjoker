// What changed between two game states, so the UI can flash it: cards that
// arrived in the hand, cards that arrived in table piles, and which piles
// changed (and who changed them, when that can be told).

import type { TablePile } from "./protocol";

export interface Snapshot {
  table: TablePile[];
  hand: number[] | undefined;
  /** Card counts by player id. */
  counts: Record<string, number>;
}

export interface Changes {
  /** Cards new in the hand. */
  hand: Set<number>;
  /** Cards that arrived in a table pile (from a hand or another pile). */
  table: Set<number>;
  /** Changed piles by new pile id, with the player id who changed them, if known. */
  piles: Map<number, string | null>;
}

export function diff(before: Snapshot, after: Snapshot): Changes {
  const changes: Changes = { hand: new Set(), table: new Set(), piles: new Map() };

  if (before.hand && after.hand) {
    const had = new Set(before.hand);
    for (const card of after.hand) if (!had.has(card)) changes.hand.add(card);
  }

  // The engine gives every pile a move touched a new id, so piles with a
  // known id are unchanged (locking doesn't change the cards).
  const oldIds = new Set(before.table.map((p) => p.id));
  const fresh = after.table.filter((p) => !oldIds.has(p.id));
  if (!fresh.length) return changes;

  const actor = soleShedder(before.counts, after.counts);
  for (const pile of fresh) {
    // Compare with the old pile it shares most cards with: anything else in
    // it was added (from a hand, or moved from another pile). A pile that
    // shares no more than half its cards with any old pile is new as a whole.
    let best: TablePile | null = null;
    let bestOverlap = 0;
    for (const old of before.table) {
      const overlap = old.cards.filter((c) => pile.cards.includes(c)).length;
      if (overlap > bestOverlap) [best, bestOverlap] = [old, overlap];
    }
    const base = bestOverlap * 2 > pile.cards.length ? best : null;
    for (const card of pile.cards) if (!base?.cards.includes(card)) changes.table.add(card);
    changes.piles.set(pile.id, best?.locked_by ?? actor);
  }
  return changes;
}

/** The one player whose card count went down, if exactly one did. */
function soleShedder(before: Record<string, number>, after: Record<string, number>): string | null {
  const shed = Object.keys(after).filter((id) => id in before && after[id] < before[id]);
  return shed.length === 1 ? shed[0] : null;
}
