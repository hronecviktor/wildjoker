// Small wrappers around localStorage, which can be missing or throw (private
// windows, blocked storage); the app works without it, just without resume.

const PREFIX = "wildjoker.";

export function load<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(PREFIX + key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export function save(key: string, value: unknown): void {
  try {
    if (value === undefined || value === null) localStorage.removeItem(PREFIX + key);
    else localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // storage unavailable
  }
}

/** Resume tokens, one per room code. */
export const sessions = {
  get(code: string): string | undefined {
    return load<Record<string, string>>("sessions", {})[code.toUpperCase()];
  },
  set(code: string, token: string): void {
    const all = load<Record<string, string>>("sessions", {});
    all[code.toUpperCase()] = token;
    save("sessions", all);
    save("last", code.toUpperCase());
  },
  forget(code: string): void {
    const all = load<Record<string, string>>("sessions", {});
    delete all[code.toUpperCase()];
    save("sessions", all);
    if (load<string | null>("last", null) === code.toUpperCase()) save("last", null);
  },
  last(): string | null {
    return load<string | null>("last", null);
  },
};
