// Accessible card names ("Queen of hearts", "srdcová dáma").

import { isJoker, rankOf, suitOf } from "../lib/cards";
import { t } from "./index.svelte";

/** What a joker stands for in a pile: a rank (1-14) and, in runs, a suit. */
export interface JokerValue {
  rank: number;
  suit: number | null;
}

function natural(rank: number, suit: number | null): string {
  const r = rank === 14 ? 1 : rank;
  const name = t(`rank.${r}`);
  if (suit === null) return name;
  const gender = t(`rank_gender.${r}`);
  return t("card.label", { rank: name, suit: t(`suit_adj.${suit}.${gender}`) });
}

export function cardLabel(id: number, value?: JokerValue | null): string {
  if (!isJoker(id)) return natural(rankOf(id)!, suitOf(id));
  if (!value) return t("card.joker");
  return t("card.joker_as", { card: natural(value.rank, value.suit) });
}
