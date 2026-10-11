import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { cardCode, cardsFromCodes } from "./cards";
import { arrange, findOpening, isValidOpening, isValidPile } from "./piles";

interface Case {
  name: string;
  cards: string;
  valid: boolean;
  kind?: "run" | "set";
  order?: string;
  opening?: boolean;
}

const path = fileURLToPath(new URL("../../../shared/piles.json", import.meta.url));
const { cases } = JSON.parse(readFileSync(path, "utf8")) as { cases: Case[] };
const codes = (ids: number[]) => ids.map(cardCode).join(" ");

describe("shared pile cases", () => {
  it("has cases", () => expect(cases.length).toBeGreaterThan(10));

  for (const c of cases) {
    it(c.name, () => {
      const cards = cardsFromCodes(c.cards);
      const result = arrange(cards);
      expect(isValidPile(cards)).toBe(c.valid);
      if (!c.valid) {
        expect(result).toBeNull();
        expect(isValidOpening(cards)).toBe(false);
        return;
      }
      expect(result?.kind).toBe(c.kind);
      expect(codes(result!.cards)).toBe(c.order);
      expect(isValidOpening(cards)).toBe(c.opening);
      // Arranging is stable: the canonical order arranges to itself.
      expect(arrange(result!.cards)?.cards).toEqual(result!.cards);
    });
  }
});

describe("arrange values", () => {
  it("gives joker values in runs", () => {
    const result = arrange(cardsFromCodes("4H JK 6H"))!;
    expect(result.values).toEqual([4, 5, 6]);
    expect(result.suit).toBe(1);
  });
  it("gives a high ace 14", () => {
    expect(arrange(cardsFromCodes("KH AH JK"))!.values).toEqual([12, 13, 14]);
  });
  it("gives the set rank", () => {
    expect(arrange(cardsFromCodes("9D JK 9S"))!.values).toEqual([9, 9, 9]);
  });
});

describe("findOpening", () => {
  it("finds the longest run", () => {
    expect(codes(findOpening(cardsFromCodes("2H 3H 4H 9S TS JS QS JK"))!)).toBe("9S TS JS QS");
  });
  it("uses a high ace", () => {
    expect(codes(findOpening(cardsFromCodes("QD KD AD 5C"))!)).toBe("QD KD AD");
  });
  it("ignores jokers", () => {
    expect(findOpening(cardsFromCodes("2H JK 4H 7C"))).toBeNull();
  });
});
