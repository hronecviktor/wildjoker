import { describe, expect, it } from "vitest";
import { diff, type Snapshot } from "./changes";
import type { TablePile } from "./protocol";

const pile = (id: number, cards: number[], locked_by: string | null = null): TablePile => ({
  id,
  cards,
  locked_by,
});

const snap = (table: TablePile[], hand?: number[], counts: Record<string, number> = {}): Snapshot => ({
  table,
  hand,
  counts,
});

describe("diff", () => {
  it("finds a drawn card", () => {
    const c = diff(snap([], [1, 2]), snap([], [1, 2, 7]));
    expect([...c.hand]).toEqual([7]);
    expect(c.table.size).toBe(0);
  });

  it("ignores a missing hand (first state, or spectating)", () => {
    expect(diff(snap([]), snap([], [1, 2])).hand.size).toBe(0);
  });

  it("finds a card added to a staged pile and who added it", () => {
    const before = snap([pile(1, [10, 11, 12], "cpu")], undefined, { cpu: 4, me: 5 });
    const after = snap([pile(2, [10, 11, 12, 13])], undefined, { cpu: 3, me: 5 });
    const c = diff(before, after);
    expect([...c.table]).toEqual([13]);
    expect([...c.piles]).toEqual([[2, "cpu"]]);
  });

  it("finds a new pile put down from a hand without staging", () => {
    const before = snap([pile(1, [10, 11, 12])], undefined, { a: 5, b: 5 });
    const after = snap([pile(1, [10, 11, 12]), pile(2, [30, 31, 32])], undefined, { a: 2, b: 5 });
    const c = diff(before, after);
    expect([...c.table]).toEqual([30, 31, 32]);
    expect([...c.piles]).toEqual([[2, "a"]]);
  });

  it("marks cards moved between piles", () => {
    // 13 moves from pile 1 to a new set built with pile 2's end card and a hand card.
    const before = snap([pile(1, [10, 11, 12, 13], "a"), pile(2, [40, 41, 42, 43], "a")]);
    const after = snap([pile(3, [10, 11, 12]), pile(4, [41, 42, 43]), pile(5, [13, 40, 99])]);
    const c = diff(before, after);
    expect([...c.table].sort()).toEqual([13, 40, 99].sort());
    expect(c.piles.size).toBe(3);
    expect(c.piles.get(5)).toBe("a");
  });

  it("marks a split pile as changed without flashing its cards", () => {
    const before = snap([pile(1, [1, 2, 3, 4, 5, 6], "a")]);
    const after = snap([pile(2, [1, 2, 3]), pile(3, [4, 5, 6])]);
    const c = diff(before, after);
    expect([...c.piles.keys()]).toEqual([2, 3]);
    // The second half shares fewer cards with the old pile but all came from it.
    expect(c.table.size).toBe(0);
  });

  it("ignores locking and unlocking", () => {
    const c = diff(snap([pile(1, [1, 2, 3])]), snap([pile(1, [1, 2, 3], "a")]));
    expect(c.piles.size).toBe(0);
    expect(c.table.size).toBe(0);
  });

  it("doesn't guess the player when several card counts dropped", () => {
    const before = snap([], undefined, { a: 5, b: 5 });
    const after = snap([pile(2, [30, 31, 32])], undefined, { a: 2, b: 4 });
    expect(diff(before, after).piles.get(2)).toBeNull();
  });
});
