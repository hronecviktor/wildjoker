// The game table's local state: selected cards, the draft move, hand sorting,
// and the actions that talk to the server.

import { errorText, t } from "../i18n/index.svelte";
import { sortCards, type SortMode } from "./cards";
import { ServerError, type Connection } from "./connection.svelte";
import * as D from "./draft";
import { arrange, isValidOpening } from "./piles";
import type { TablePile } from "./protocol";
import { load, save } from "./storage";
import { toast } from "./toasts.svelte";

export class GameController {
  draft = $state.raw<D.Draft>(D.emptyDraft());
  selected = $state.raw<number[]>([]);
  sort = $state<SortMode>(load<SortMode>("sort", "suit"));
  /** When the staging area expires, as a performance.now() timestamp. */
  deadline = $state<number | null>(null);
  busy = $state(false);

  constructor(private conn: Connection) {}

  get state() {
    return this.conn.state;
  }
  get game() {
    return this.conn.state?.game ?? null;
  }
  get me() {
    return this.conn.state?.players.find((p) => p.id === this.conn.you) ?? null;
  }
  get opened(): boolean {
    return !!this.me?.opened;
  }
  get active(): boolean {
    return this.state?.phase === "playing" && this.game?.hand !== undefined && !this.me?.place;
  }
  get staging(): boolean {
    return !!this.game?.staging;
  }
  /** My staged table piles, as the server has them. */
  get stagedPiles(): TablePile[] {
    const ids = this.game?.staging?.piles ?? [];
    return (this.game?.table ?? []).filter((p) => ids.includes(p.id));
  }
  /** The hand as shown: real hand plus staged cards not in a draft pile. */
  get hand(): number[] {
    const staged = this.stagedPiles.flatMap((p) => p.cards);
    return sortCards(D.handCards(this.draft, this.game?.hand ?? [], staged), this.sort);
  }
  /** Staged cards currently in the hand (they came from the table). */
  get fromTable(): Set<number> {
    return new Set(this.stagedPiles.flatMap((p) => p.cards));
  }
  get drafting(): boolean {
    return this.staging || this.draft.piles.length > 0;
  }
  get canCommit(): boolean {
    return D.canCommit(this.draft, this.staging);
  }
  get canOpen(): boolean {
    return this.active && !this.opened && isValidOpening(this.selected);
  }
  /** Selected cards that sit in draft piles. */
  get selectedInPiles(): number[] {
    const inPiles = new Set(this.draft.piles.flatMap((p) => p.cards));
    return this.selected.filter((c) => inPiles.has(c));
  }
  /** The split point when exactly one card in a pile is selected (not its first). */
  get splitPoint(): { key: number; index: number } | null {
    if (this.selected.length !== 1) return null;
    for (const p of this.draft.piles) {
      const index = D.displayOrder(p.cards).indexOf(this.selected[0]);
      if (index > 0) return { key: p.key, index };
    }
    return null;
  }

  /** Call on every new state. */
  sync(): void {
    const game = this.game;
    if (!game || !this.active) {
      this.draft = D.emptyDraft();
      this.selected = [];
      this.deadline = null;
      return;
    }
    this.draft = D.reconcile(this.draft, game.hand ?? [], this.stagedPiles);
    const available = new Set([...(game.hand ?? []), ...this.stagedPiles.flatMap((p) => p.cards)]);
    if (this.selected.some((c) => !available.has(c))) this.selected = this.selected.filter((c) => available.has(c));
    this.deadline = game.staging ? performance.now() + game.staging.remaining * 1000 : null;
  }

  setSort(mode: SortMode): void {
    this.sort = mode;
    save("sort", mode);
  }

  toggle(card: number): void {
    this.selected = this.selected.includes(card)
      ? this.selected.filter((c) => c !== card)
      : [...this.selected, card];
  }

  selectPile(key: number): void {
    const pile = this.draft.piles.find((p) => p.key === key);
    if (!pile) return;
    const all = pile.cards.every((c) => this.selected.includes(c));
    this.selected = all ? [] : [...pile.cards];
  }

  clearSelection(): void {
    this.selected = [];
  }

  /** Draws don't take the busy lock, so quick repeated draws all go through. */
  async draw(): Promise<void> {
    if (!this.active) return;
    try {
      await this.conn.request({ type: "draw" });
    } catch (e) {
      if (!(e instanceof ServerError)) throw e;
      toast(errorText(e.code), "error");
    }
  }

  async open(): Promise<void> {
    if (!this.canOpen) {
      if (this.active && !this.opened) toast(t("game.open_hint"));
      return;
    }
    const cards = arrange(this.selected)!.cards;
    await this.run(async () => {
      await this.conn.request({ type: "open", cards });
      this.selected = [];
    });
  }

  /** Take a table pile into the staging area, adding any selected hand cards to it. */
  async take(pile: TablePile): Promise<void> {
    if (!this.active) return;
    if (!this.opened) {
      toast(t("game.open_first"));
      return;
    }
    if (pile.locked_by === this.conn.you) {
      const draftPile = this.draft.piles.find((p) => p.from === pile.id);
      if (draftPile) this.place({ kind: "pile", key: draftPile.key });
      return;
    }
    if (pile.locked_by) {
      toast(errorText("pile_locked"), "error");
      return;
    }
    const moving = this.selected;
    await this.run(async () => {
      await this.conn.request({ type: "stage", piles: [pile.id] });
      this.sync();
      const draftPile = this.draft.piles.find((p) => p.from === pile.id);
      if (draftPile && moving.length) {
        this.draft = D.moveCards(this.draft, moving, { kind: "pile", key: draftPile.key });
        this.selected = [];
      }
    });
  }

  /** Put the selected cards on a target. */
  place(target: D.Target): void {
    if (!this.selected.length) return;
    if (target.kind !== "hand" && !this.opened) {
      toast(t("game.open_first"));
      return;
    }
    this.draft = D.moveCards(this.draft, this.selected, target);
    this.selected = [];
  }

  split(): void {
    const at = this.splitPoint;
    if (!at) return;
    this.draft = D.splitPile(this.draft, at.key, at.index);
    this.selected = [];
  }

  async commit(): Promise<void> {
    if (!this.canCommit) {
      if (this.drafting) toast(t("staging.fix_piles"), "error");
      return;
    }
    const piles = D.commitPayload(this.draft);
    await this.run(async () => {
      await this.conn.request({ type: "commit", piles });
      this.draft = D.emptyDraft();
      this.selected = [];
    });
  }

  async cancel(): Promise<void> {
    const wasStaging = this.staging;
    this.draft = D.emptyDraft();
    this.selected = [];
    if (wasStaging) await this.run(() => this.conn.request({ type: "cancel" }).then(() => {}));
  }

  async voteDraw(): Promise<void> {
    await this.run(() => this.conn.request({ type: "vote_draw" }).then(() => {}));
  }

  private async run(fn: () => Promise<void>): Promise<void> {
    if (this.busy) return;
    this.busy = true;
    try {
      await fn();
    } catch (e) {
      if (!(e instanceof ServerError)) throw e;
      // staging_expired and not_staging also come with a new state; sync() tidies up.
      if (e.code !== "not_staging") toast(errorText(e.code), "error");
      this.sync();
    } finally {
      this.busy = false;
    }
  }
}
