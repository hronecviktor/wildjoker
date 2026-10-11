// Cards that move, animated. Before each update of the table the game takes a
// snapshot of where every card is on screen; after the update it compares:
//
// - a card still in the same place (the hand, a draft pile, a table pile)
//   slides from its old position to its new one;
// - a card that moved somewhere else flies there, as a copy drawn above
//   everything (so the hand's or the table's edges don't clip it);
// - a card that wasn't on screen comes from where the game says it came
//   from: the deck for a card drawn into your hand, a player's icon for a
//   card they put down from their hand;
// - a card that left the screen goes to the icon of the player who took it.
//
// Cards say where they are with ``data-card`` inside an element with
// ``data-zone`` (``data-zone="skip"`` hides a copy, such as your own staged
// piles, which show on the table and in the move sheet). A table pile being
// staged by someone names them in ``data-owner``.

export interface Spot {
  el: HTMLElement;
  rect: DOMRect;
  zone: string;
  /** Who is staging the pile the card was in. */
  owner: string | null;
}

export interface Sources {
  /** Where a card new to the screen, now in ``zone``, came from. */
  from(card: number, zone: string): Element | null;
  /** Where a card that left the screen went. */
  to(card: number, spot: Spot): Element | null;
  /** Fast-forwarded games move quicker. */
  fast: boolean;
}

const FLY_MS = 480;
const SLIDE_MS = 240;
const EASE = "cubic-bezier(0.25, 0.8, 0.3, 1)";
/** No more flights at once than this; the rest just appear. */
const MAX_FLIGHTS = 40;
/** A snapshot older than this missed its update and is stale. */
const STALE_MS = 250;

let pending: { spots: Map<number, Spot>; at: number } | null = null;
let layer: HTMLElement | null = null;

function quiet(): boolean {
  return (
    typeof document === "undefined" ||
    document.hidden ||
    matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/** Where every card is now. */
export function snapshot(): Map<number, Spot> {
  const spots = new Map<number, Spot>();
  for (const el of document.querySelectorAll<HTMLElement>("[data-zone] [data-card]")) {
    if (el.closest(".flying")) continue;
    const zoneEl = el.closest<HTMLElement>("[data-zone]")!;
    const zone = zoneEl.dataset.zone!;
    if (zone === "skip") continue;
    spots.set(Number(el.dataset.card), {
      el,
      rect: el.getBoundingClientRect(),
      zone,
      owner: zoneEl.dataset.owner || null,
    });
  }
  return spots;
}

/** Call just before the DOM updates; the first call before an update wins. */
export function capture(): void {
  const now = performance.now();
  if (pending && now - pending.at < STALE_MS) return;
  pending = quiet() ? null : { spots: snapshot(), at: now };
}

/** Call just after the DOM updated: animate what moved since ``capture()``. */
export function play(sources: Sources): void {
  const before = pending;
  pending = null;
  if (!before || quiet() || performance.now() - before.at > STALE_MS) return;
  const after = snapshot();
  const speed = sources.fast ? 0.45 : 1;
  // Several new cards from the same place (a deal, a whole set put down)
  // leave one after the other.
  const queued = new Map<Element, number>();

  for (const [card, spot] of after) {
    const prev = before.spots.get(card);
    if (prev && prev.zone === spot.zone) {
      slide(spot.el, prev.rect, spot.rect, SLIDE_MS * speed);
      continue;
    }
    let from = prev?.rect;
    let delay = 0;
    if (!from) {
      const source = sources.from(card, spot.zone);
      if (!source) continue;
      from = source.getBoundingClientRect();
      const n = queued.get(source) ?? 0;
      queued.set(source, n + 1);
      delay = Math.min(n, 12) * 60 * speed;
    }
    fly(spot.el, from, spot.rect, { duration: FLY_MS * speed, delay, hide: spot.el });
  }

  for (const [card, spot] of before.spots) {
    if (after.has(card)) continue;
    const target = sources.to(card, spot);
    if (target) fly(spot.el, spot.rect, target.getBoundingClientRect(), { duration: FLY_MS * speed, fade: true });
  }
}

/** A face-down card from the deck to a player's icon (someone else drew). */
export function drawTo(player: string, fast = false): void {
  if (quiet()) return;
  const deck = document.querySelector('[data-testid="deck"] .stack');
  const icon = playerIcon(player);
  if (!deck || !icon) return;
  const back = document.createElement("span");
  back.className = "card-back";
  const from = deck.getBoundingClientRect();
  fly(back, from, icon.getBoundingClientRect(), { duration: FLY_MS * (fast ? 0.45 : 1), fade: true, size: from });
}

export function playerIcon(player: string | null): Element | null {
  return player ? document.querySelector(`[data-player="${CSS.escape(player)}"] .avatar`) : null;
}

export function deck(): Element | null {
  return document.querySelector('[data-testid="deck"] .stack');
}

/** Move an element from where it was to where it is, in place. */
function slide(el: HTMLElement, from: DOMRect, to: DOMRect, duration: number): void {
  const dx = from.left - to.left;
  const dy = from.top - to.top;
  if (Math.abs(dx) < 2 && Math.abs(dy) < 2) return;
  el.animate([{ transform: `translate(${dx}px, ${dy}px)` }, { transform: "translate(0, 0)" }], {
    duration,
    easing: EASE,
    composite: "add", // on top of a selected or fresh card's own lift
  });
}

interface FlyOptions {
  duration: number;
  delay?: number;
  /** The real card, kept invisible until its copy lands. */
  hide?: HTMLElement;
  /** Shrink and fade into the target (a player's icon). */
  fade?: boolean;
  /** The copy's size; by default the size of where it lands, or it leaves. */
  size?: DOMRect;
}

/** A copy of ``el`` flies from one rectangle to another, above the page. */
function fly(el: HTMLElement, from: DOMRect, to: DOMRect, opts: FlyOptions): void {
  const host = flightLayer();
  if (host.childElementCount >= MAX_FLIGHTS) return;
  // The copy has the size of the card at the end it shows best: where it
  // lands, or where it leaves from when it disappears into an icon.
  const box = opts.size ?? (opts.fade ? from : to);
  const copy = el.cloneNode(true) as HTMLElement;
  copy.classList.remove("selected", "fresh");
  copy.removeAttribute("data-card");
  copy.removeAttribute("id");
  copy.setAttribute("aria-hidden", "true");
  const corner = opts.hide ? getComputedStyle(opts.hide).getPropertyValue("--corner") : "";
  copy.style.cssText = [
    "position:absolute",
    "left:0",
    "top:0",
    "margin:0",
    `width:${box.width}px`,
    `height:${box.height}px`,
    `--w:${box.width}px`,
    `--h:${box.height}px`,
    `--corner:${corner || Math.max(10, Math.round(box.height * 0.21)) + "px"}`,
    "transform-origin:0 0",
    "will-change:transform",
  ].join(";");
  host.append(copy);

  const at = (r: DOMRect, shrink = 1) => {
    const scale = Math.min(r.width / box.width, r.height / box.height) * shrink;
    // Centre the copy on the rectangle.
    const x = r.left + (r.width - box.width * scale) / 2;
    const y = r.top + (r.height - box.height * scale) / 2;
    return `translate(${x}px, ${y}px) scale(${scale})`;
  };
  const start = opts.fade ? `translate(${from.left}px, ${from.top}px)` : at(from);
  const end = opts.fade ? at(to, 0.8) : `translate(${to.left}px, ${to.top}px)`;
  const lift = `0 ${opts.fade ? 4 : 10}px 18px rgb(0 0 0 / 0.45)`;
  const flight = copy.animate(
    [
      { transform: start, opacity: 1, boxShadow: "0 1px 2px rgb(0 0 0 / 0.35)" },
      { opacity: 1, boxShadow: lift, offset: 0.5 },
      { transform: end, opacity: opts.fade ? 0.2 : 1, boxShadow: "0 1px 2px rgb(0 0 0 / 0.35)" },
    ],
    { duration: opts.duration, delay: opts.delay ?? 0, easing: EASE, fill: "backwards" },
  );
  const hidden = opts.hide?.animate([{ opacity: 0 }, { opacity: 0 }], {
    duration: opts.duration + (opts.delay ?? 0),
  });
  const done = () => {
    copy.remove();
    hidden?.cancel();
  };
  flight.onfinish = done;
  flight.oncancel = done;
}

function flightLayer(): HTMLElement {
  if (!layer || !layer.isConnected) {
    layer = document.createElement("div");
    layer.className = "flying";
    layer.setAttribute("aria-hidden", "true");
    document.body.append(layer);
  }
  return layer;
}
