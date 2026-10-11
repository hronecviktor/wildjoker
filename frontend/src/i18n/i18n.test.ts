import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { ERROR_CODES, EVENT_KINDS } from "../lib/protocol";
import en from "./en.json";
import sk from "./sk.json";

const files = { en, sk } as Record<string, Record<string, string>>;

describe("translations", () => {
  it("have the same keys in every language", () => {
    const enKeys = Object.keys(en).sort();
    for (const [lang, table] of Object.entries(files)) {
      const keys = Object.keys(table).sort();
      expect(keys.filter((k) => !enKeys.includes(k)), `extra keys in ${lang}.json`).toEqual([]);
      expect(enKeys.filter((k) => !keys.includes(k)), `missing keys in ${lang}.json`).toEqual([]);
    }
  });

  it("have no empty strings and the same placeholders", () => {
    for (const [key, text] of Object.entries(en as Record<string, string>)) {
      const vars = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
      for (const [lang, table] of Object.entries(files)) {
        expect(table[key], `${lang}:${key}`).toBeTruthy();
        expect(vars(table[key] ?? ""), `${lang}:${key}`).toEqual(vars(text));
      }
    }
  });

  it("cover every protocol error code and event", () => {
    for (const code of ERROR_CODES) expect(en, code).toHaveProperty([`error.${code}`]);
    for (const kind of EVENT_KINDS) expect(en, kind).toHaveProperty([`event.${kind}`]);
  });

  it("cover every voice error code", () => {
    const codes = ["permission_denied", "no_device", "device_busy", "insecure_context", "unsupported", "failed"];
    for (const code of codes) expect(en, code).toHaveProperty([`voice.error.${code}`]);
  });

  it("cover every error code listed in shared/protocol.md", () => {
    const doc = readFileSync(fileURLToPath(new URL("../../../shared/protocol.md", import.meta.url)), "utf8");
    const section = doc.split("## Error codes")[1] ?? "";
    const codes = [...section.matchAll(/`([a-z_]+)`/g)].map((m) => m[1]);
    expect(codes.length).toBeGreaterThan(20);
    for (const code of codes) expect(en, code).toHaveProperty([`error.${code}`]);
  });

  it("are used: every literal t() key exists", () => {
    const root = fileURLToPath(new URL("..", import.meta.url));
    const sources: string[] = [];
    const walk = (dir: string) => {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const path = `${dir}/${entry.name}`;
        if (entry.isDirectory()) walk(path);
        else if (/\.(svelte|ts)$/.test(entry.name) && !entry.name.endsWith(".test.ts")) sources.push(path);
      }
    };
    walk(root);
    const missing: string[] = [];
    for (const path of sources) {
      const text = readFileSync(path, "utf8");
      for (const m of text.matchAll(/\bt\("([a-z_.]+)"/g)) if (!(m[1] in en)) missing.push(`${path}: ${m[1]}`);
      for (const m of text.matchAll(/\btn\("([a-z_.]+)"/g))
        for (const form of ["one", "few", "other"])
          if (!(`${m[1]}_${form}` in en)) missing.push(`${path}: ${m[1]}_${form}`);
    }
    expect(missing).toEqual([]);
  });
});
