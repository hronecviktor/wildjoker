import { describe, expect, it } from "vitest";
import { cardCode } from "./cards";
import type { TablePile } from "./protocol";
import { tableOrder } from "./tableOrder";

// Card ids: suit * 13 + rank - 1 (spades, hearts, diamonds, clubs); 52 is a joker.
const card = (rank: number, suit: number) => suit * 13 + rank - 1;
const pile = (id: number, cards: number[]): TablePile => ({ id, cards, locked_by: null });
const show = (piles: TablePile[]) => piles.map((p) => p.cards.map(cardCode).join(" "));

describe("tableOrder", () => {
  it("puts sets first by rank, then runs by suit and lowest card", () => {
    const piles = [
      pile(1, [card(5, 3), card(6, 3), card(7, 3)]), // clubs run
      pile(2, [card(9, 1), card(10, 1), card(11, 1)]), // hearts 9-J
      pile(3, [card(12, 0), card(12, 1), card(12, 2)]), // queens
      pile(4, [card(2, 1), card(3, 1), card(4, 1)]), // hearts 2-4
      pile(5, [card(4, 0), card(4, 2), card(4, 3)]), // fours
    ];
    expect(tableOrder(piles).map((p) => p.id)).toEqual([5, 3, 4, 2, 1]);
  });

  it("keeps a pile's place when it changes and gets a new id", () => {
    const before = [pile(1, [card(2, 1), card(3, 1), card(4, 1)]), pile(2, [card(7, 0), card(8, 0), card(9, 0)])];
    const after = [pile(2, [card(7, 0), card(8, 0), card(9, 0)]), pile(3, [card(2, 1), card(3, 1), card(4, 1), card(5, 1)])];
    expect(show(tableOrder(before))[0]).toBe("7S 8S 9S");
    expect(show(tableOrder(after))[0]).toBe("7S 8S 9S");
  });

  it("orders a run starting with a joker by the rank the joker stands for", () => {
    const piles = [pile(1, [card(5, 1), card(6, 1), card(7, 1)]), pile(2, [52, card(3, 1), card(4, 1)])];
    expect(tableOrder(piles).map((p) => p.id)).toEqual([2, 1]);
  });
});
