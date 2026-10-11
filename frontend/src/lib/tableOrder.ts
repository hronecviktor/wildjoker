// The order piles are shown on the table: sets by rank, then runs by suit and
// lowest card. The server gives every pile a move touched a new id, so in
// arrival order piles would keep jumping around; sorted by what they are,
// each pile stays where you'd look for it.

import { arrange } from "./piles";
import type { TablePile } from "./protocol";

function sortKey(pile: TablePile): number[] {
  const a = arrange(pile.cards);
  if (!a) return [2, 0, 0, pile.id]; // shouldn't happen: the server only keeps valid piles
  if (a.kind === "set") return [0, a.values?.[0] ?? 99, 0, pile.id];
  return [1, a.suit ?? 9, a.values?.[0] ?? 99, pile.id];
}

export function tableOrder(piles: readonly TablePile[]): TablePile[] {
  const keyed = piles.map((pile) => ({ pile, key: sortKey(pile) }));
  keyed.sort((x, y) => {
    for (let i = 0; i < x.key.length; i++) if (x.key[i] !== y.key[i]) return x.key[i] - y.key[i];
    return 0;
  });
  return keyed.map((k) => k.pile);
}
