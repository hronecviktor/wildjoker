// Translations: English and Slovak, remembered per browser, defaulting to
// the browser's language. All UI text lives in en.json and sk.json.

import { load, save } from "../lib/storage";
import en from "./en.json";
import sk from "./sk.json";

export const LANGS = { en, sk } as const;
export type Lang = keyof typeof LANGS;
export const LANG_NAMES: Record<Lang, string> = { en: "English", sk: "Slovenčina" };
type Params = Record<string, string | number>;

function initial(): Lang {
  const stored = load<string | null>("lang", null);
  if (stored && stored in LANGS) return stored as Lang;
  const browser = typeof navigator !== "undefined" ? navigator.languages ?? [navigator.language] : [];
  for (const l of browser) {
    const base = l.slice(0, 2).toLowerCase();
    if (base in LANGS) return base as Lang;
    if (base === "cs") return "sk"; // Czech speakers read Slovak more easily than English
  }
  return "en";
}

const current = $state({ lang: initial() });
if (typeof document !== "undefined") document.documentElement.lang = current.lang;

export const i18n = {
  get lang(): Lang {
    return current.lang;
  },
  set lang(lang: Lang) {
    current.lang = lang;
    save("lang", lang);
    document.documentElement.lang = lang;
  },
};

/** The text for `key`, with `{name}` placeholders filled from `params`. */
export function t(key: string, params?: Params): string {
  const table = LANGS[current.lang] as Record<string, string>;
  let text = table[key] ?? (en as Record<string, string>)[key] ?? key;
  if (params) text = text.replace(/\{(\w+)\}/g, (m, name) => (name in params ? String(params[name]) : m));
  return text;
}

/** Plural forms: `key_one`, `key_few` (Slovak 2-4) and `key_other`; `{n}` is the count. */
export function tn(key: string, n: number, params?: Params): string {
  const form = n === 1 ? "one" : current.lang === "sk" && n >= 2 && n <= 4 ? "few" : "other";
  return t(`${key}_${form}`, { n, ...params });
}

/** Whether a translation exists (e.g. for error codes from the server). */
export const has = (key: string) => key in (LANGS[current.lang] as Record<string, string>);

/** Translated message for a protocol error code. */
export const errorText = (code: string) => (has(`error.${code}`) ? t(`error.${code}`) : t("error.unknown", { code }));
