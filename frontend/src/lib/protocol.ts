// Types for the messages in shared/protocol.md.

export type CpuLevel = "easy" | "medium" | "hard" | "expert";
export const CPU_LEVELS: readonly CpuLevel[] = ["easy", "medium", "hard", "expert"];
export type Phase = "lobby" | "playing" | "finished";
/** Which game a room plays: Wild Joker or Gin (RULES-GIN.md). */
export type GameKind = "wild" | "gin";

export const ERROR_CODES = [
  "bad_message",
  "too_large",
  "not_joined",
  "already_joined",
  "no_room",
  "bad_token",
  "room_full",
  "game_in_progress",
  "not_host",
  "bad_player",
  "bad_config",
  "not_enough_players",
  "no_game",
  "game_over",
  "player_out",
  "unknown_player",
  "deck_empty",
  "deck_not_empty",
  "already_opened",
  "invalid_opening",
  "not_opened",
  "bad_card",
  "bad_pile",
  "pile_locked",
  "not_staging",
  "staging_expired",
  "empty_move",
  "invalid_pile",
  "not_in_voice",
  "humans_playing",
  "not_tutorial",
  "not_your_turn",
  "draw_first",
  "already_drew",
  "round_over",
  "round_not_over",
  "just_picked",
  "must_play",
  "cant_play_card",
  "keep_one",
] as const;
export const EVENT_KINDS = [
  "drew",
  "went_out",
  "staging_expired",
  "stalemate",
  "kicked",
  "took",
  "discarded",
  "one_card",
  "gin",
  "stock_out",
] as const;
export type EventKind = (typeof EVENT_KINDS)[number];

export interface PlayerView {
  id: string;
  name: string;
  cpu: CpuLevel | null;
  connected: boolean;
  voice: boolean;
  muted: boolean;
  cards?: number;
  opened?: boolean;
  place?: number | null;
  /** Gin: the total score so far. */
  score?: number;
}

export interface TablePile {
  id: number;
  cards: number[];
  locked_by: string | null;
}

export interface GameView {
  kind?: undefined;
  version: number;
  deck: number;
  table: TablePile[];
  places: string[][];
  draw_votes: string[];
  staging_timeout: number;
  hand?: number[];
  staging?: { piles: number[]; remaining: number } | null;
}

export interface Meld {
  id: number;
  cards: number[];
  /** Who put down each card (its points are theirs). */
  owners: string[];
}

export interface RoundResult {
  /** Who went out; null when the round ended with the stock used up. */
  gin: string | null;
  table: Record<string, number>;
  hand: Record<string, number>;
  scores: Record<string, number>;
  /** Everyone's cards left at the end. */
  hands: Record<string, number[]>;
}

/** A Gin game, as in shared/protocol.md. */
export interface GinView {
  kind: "gin";
  version: number;
  round: number;
  status: "playing" | "round_over" | "finished";
  deck: number;
  /** Bottom first. */
  discard: number[];
  melds: Meld[];
  dealer: string;
  turn: string | null;
  step: "draw" | "play";
  /** Taken from the discard pile this turn: can't be discarded. */
  picked: number | null;
  /** A deeper discard taken that must still go on the table. */
  must_play: number | null;
  scores: Record<string, number>;
  target: number;
  history: Record<string, number>[];
  result: RoundResult | null;
  winner: string | null;
  places: string[][];
  hand?: number[];
  /** Discards you may take now. */
  takeable?: number[];
}

export interface StateMessage {
  type: "state";
  version: number;
  code: string;
  kind: GameKind;
  phase: Phase;
  host: string | null;
  you: string;
  options: { decks: number; hand_size: number };
  /** CPUs are sped up (only CPUs are still playing). */
  fast_forward: boolean;
  /** A tutorial game against the scripted Teacher. */
  tutorial: boolean;
  players: PlayerView[];
  game: GameView | GinView | null;
}

/** The game, if it is Wild Joker. */
export function wildView(state: StateMessage | null | undefined): GameView | null {
  const game = state?.game;
  return game && game.kind !== "gin" ? game : null;
}

/** The game, if it is Gin. */
export function ginView(state: StateMessage | null | undefined): GinView | null {
  const game = state?.game;
  return game?.kind === "gin" ? game : null;
}

export interface WelcomeMessage {
  type: "welcome";
  req?: number | null;
  code: string;
  you: string;
  token: string;
}

export interface OkMessage {
  type: "ok";
  req?: number | null;
  [key: string]: unknown;
}

export interface ErrorMessage {
  type: "error";
  req?: number | null;
  code: string;
}

export interface EventMessage {
  type: "event";
  kind: EventKind;
  player?: string;
  /** went_out: the player's finishing place (1-based). */
  place?: number;
  /** took: how many cards. */
  count?: number;
}

export interface SignalMessage {
  type: "signal";
  from: string;
  data: unknown;
}

export type ServerMessage =
  | StateMessage
  | WelcomeMessage
  | OkMessage
  | ErrorMessage
  | EventMessage
  | SignalMessage;

export type Reply = WelcomeMessage | OkMessage;
