// What each joker in a pile stands for, for the small hint on the card.

import type { JokerValue } from "../i18n/cards";
import { isJoker } from "./cards";
import { arrange } from "./piles";

/** Cards in display order, each with its joker value (null for naturals or unknown). */
export function withValues(cards: readonly number[]): { id: number; value: JokerValue | null }[] {
  const a = arrange(cards);
  if (!a) return cards.map((id) => ({ id, value: null }));
  return a.cards.map((id, i) => ({
    id,
    value: isJoker(id) && a.values ? { rank: a.values[i], suit: a.suit } : null,
  }));
}
