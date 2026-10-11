// Card ids, as in shared/cards.md: id = deck * 54 + index; index 0-51 are
// suit * 13 + (rank - 1), 52-53 are jokers.

export const CARDS_PER_DECK = 54;
const SUITED_PER_DECK = 52;

export type Suit = 0 | 1 | 2 | 3; // spades, hearts, diamonds, clubs
export const SUITS: readonly Suit[] = [0, 1, 2, 3];
export const SUIT_LETTERS = "SHDC";
export const SUIT_SYMBOLS = ["♠", "♥", "♦", "♣"];
export const SUIT_NAMES = ["spades", "hearts", "diamonds", "clubs"] as const;
const RANK_LETTERS: Record<number, string> = { 1: "A", 10: "T", 11: "J", 12: "Q", 13: "K" };

export const isJoker = (id: number) => id % CARDS_PER_DECK >= SUITED_PER_DECK;
export const suitOf = (id: number): Suit | null =>
  isJoker(id) ? null : (Math.floor((id % CARDS_PER_DECK) / 13) as Suit);
/** 1 (ace) to 13 (king); null for a joker. */
export const rankOf = (id: number): number | null =>
  isJoker(id) ? null : ((id % CARDS_PER_DECK) % 13) + 1;

/** Deck-independent code such as "AH", "TS" or "JK". */
export function cardCode(id: number): string {
  if (isJoker(id)) return "JK";
  const rank = rankOf(id)!;
  return (RANK_LETTERS[rank] ?? String(rank)) + SUIT_LETTERS[suitOf(id)!];
}

/** Rank as printed on a card: A, 2-10, J, Q, K (14 is a high ace). */
export function rankLabel(rank: number): string {
  if (rank === 1 || rank === 14) return "A";
  return { 11: "J", 12: "Q", 13: "K" }[rank] ?? String(rank);
}

/** Cards from codes like "AH 2H JK"; repeated codes come from the next deck. */
export function cardsFromCodes(codes: string): number[] {
  const seen = new Map<string, number>();
  return codes
    .split(/\s+/)
    .filter(Boolean)
    .map((code) => {
      const n = seen.get(code) ?? 0;
      seen.set(code, n + 1);
      if (code === "JK") return Math.floor(n / 2) * CARDS_PER_DECK + SUITED_PER_DECK + (n % 2);
      const rankPart = code.slice(0, -1);
      const suit = SUIT_LETTERS.indexOf(code.slice(-1));
      const letter = Object.entries(RANK_LETTERS).find(([, v]) => v === rankPart);
      const rank = letter ? Number(letter[0]) : Number(rankPart);
      if (suit < 0 || !(rank >= 1 && rank <= 13)) throw new Error(`bad card code ${code}`);
      return n * CARDS_PER_DECK + suit * 13 + rank - 1;
    });
}

export type SortMode = "suit" | "rank";

/** Hand order: by suit then rank, or by rank then suit; jokers last. */
export function sortCards(ids: readonly number[], mode: SortMode): number[] {
  const key = (id: number) => {
    if (isJoker(id)) return [99, 99, id];
    const [s, r] = [suitOf(id)!, rankOf(id)!];
    return mode === "suit" ? [s, r, id] : [r, s, id];
  };
  return [...ids].sort((a, b) => {
    const [ka, kb] = [key(a), key(b)];
    return ka[0] - kb[0] || ka[1] - kb[1] || ka[2] - kb[2];
  });
}
