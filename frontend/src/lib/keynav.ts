// Arrow-key focus movement between cards and piles. Focusable items carry
// `data-nav="<group>"`: left/right moves within the group in DOM order,
// up/down moves to the nearest item above or below on screen.

export type Direction = "left" | "right" | "up" | "down";

function items(): HTMLElement[] {
  return [...document.querySelectorAll<HTMLElement>("[data-nav]")].filter(
    (el) => !(el as HTMLButtonElement).disabled && el.getClientRects().length > 0,
  );
}

const center = (el: HTMLElement) => {
  const r = el.getBoundingClientRect();
  return { x: r.left + r.width / 2, y: r.top + r.height / 2, top: r.top };
};

export function focusGroup(group: string): boolean {
  const first = items().find((el) => el.dataset.nav === group);
  first?.focus();
  return !!first;
}

export function navigate(dir: Direction): void {
  const all = items();
  const current = document.activeElement as HTMLElement | null;
  if (!current || !all.includes(current)) {
    (all.find((el) => el.dataset.nav === "hand") ?? all[0])?.focus();
    return;
  }
  if (dir === "left" || dir === "right") {
    const group = all.filter((el) => el.dataset.nav === current.dataset.nav);
    const i = group.indexOf(current) + (dir === "right" ? 1 : -1);
    group[Math.max(0, Math.min(group.length - 1, i))]?.focus();
    return;
  }
  const from = center(current);
  let best: HTMLElement | null = null;
  let bestScore = Infinity;
  for (const el of all) {
    if (el === current) continue;
    const c = center(el);
    // Compare tops so overlapping rows of cards count as rows.
    const dy = dir === "up" ? from.top - c.top : c.top - from.top;
    if (dy < 8) continue;
    const score = dy * 2 + Math.abs(c.x - from.x);
    if (score < bestScore) [best, bestScore] = [el, score];
  }
  best?.focus();
  best?.scrollIntoView({ block: "nearest", inline: "nearest" });
}
