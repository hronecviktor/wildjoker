import { describe, expect, it } from "vitest";
import { cardCode, cardsFromCodes } from "./cards";
import {
  addTaken,
  canCommit,
  commitPayload,
  emptyDraft,
  handCards,
  moveCards,
  reconcile,
  splitPile,
} from "./draft";

const codes = (ids: readonly number[]) => ids.map(cardCode).join(" ");

describe("draft", () => {
  const [h4, h5, h6, h7, s9, joker] = cardsFromCodes("4H 5H 6H 7H 9S JK");

  it("takes a pile and adds a hand card to it", () => {
    let d = addTaken(emptyDraft(), 3, [h4, h5, h6]);
    expect(handCards(d, [h7, s9], [h4, h5, h6])).toEqual([h7, s9]);
    expect(canCommit(d, true)).toBe(true);
    d = moveCards(d, [h7], { kind: "pile", key: d.piles[0].key });
    expect(codes(commitPayload(d)[0])).toBe("4H 5H 6H 7H");
    expect(handCards(d, [h7, s9], [h4, h5, h6])).toEqual([s9]);
  });

  it("swaps a joker into the hand", () => {
    let d = addTaken(emptyDraft(), 1, [h4, joker, h6]);
    d = moveCards(d, [h5], { kind: "pile", key: d.piles[0].key });
    d = moveCards(d, [joker], { kind: "hand" });
    expect(codes(commitPayload(d)[0])).toBe("4H 5H 6H");
    expect(handCards(d, [h5], [h4, joker, h6])).toEqual([joker]);
    expect(canCommit(d, true)).toBe(true);
  });

  it("marks invalid piles and blocks the commit", () => {
    let d = addTaken(emptyDraft(), 1, [h4, h5, h6]);
    d = moveCards(d, [s9], { kind: "pile", key: d.piles[0].key });
    expect(canCommit(d, true)).toBe(false);
    d = moveCards(d, [s9], { kind: "new" });
    expect(d.piles).toHaveLength(2);
    expect(canCommit(d, true)).toBe(false);
  });

  it("splits a pile in display order", () => {
    const run = cardsFromCodes("AH 2H 3H 4H 5H 6H");
    let d = addTaken(emptyDraft(), 1, [...run].reverse());
    d = splitPile(d, d.piles[0].key, 3);
    expect(d.piles.map((p) => codes(p.cards))).toEqual(["AH 2H 3H", "4H 5H 6H"]);
    expect(canCommit(d, true)).toBe(true);
  });

  it("merges piles by moving all cards", () => {
    let d = moveCards(emptyDraft(), [h4, h5], { kind: "new" });
    d = moveCards(d, [h6, h7], { kind: "new" });
    d = moveCards(d, d.piles[1].cards, { kind: "pile", key: d.piles[0].key });
    expect(d.piles).toHaveLength(1);
    expect(codes(commitPayload(d)[0])).toBe("4H 5H 6H 7H");
  });

  it("needs something to commit without staging", () => {
    expect(canCommit(emptyDraft(), false)).toBe(false);
    expect(canCommit(emptyDraft(), true)).toBe(true);
    expect(canCommit(moveCards(emptyDraft(), [h4, h5, h6], { kind: "new" }), false)).toBe(true);
  });

  it("drops expired staged cards but keeps hand piles", () => {
    let d = addTaken(emptyDraft(), 3, [h4, h5, h6]);
    d = moveCards(d, [h7], { kind: "pile", key: d.piles[0].key });
    d = moveCards(d, [s9, joker], { kind: "new" });
    d = reconcile(d, [h7, s9, joker], []);
    expect(d.taken).toEqual([]);
    expect(d.piles.map((p) => codes(p.cards))).toEqual(["7H", "9S JK"]);
  });

  it("adds newly staged piles once", () => {
    let d = reconcile(emptyDraft(), [h7], [{ id: 5, cards: [h4, h5, h6] }]);
    d = reconcile(d, [h7], [{ id: 5, cards: [h4, h5, h6] }]);
    expect(d.piles).toHaveLength(1);
    expect(d.taken).toEqual([5]);
  });
});
