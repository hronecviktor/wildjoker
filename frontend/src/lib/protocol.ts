// Types for the messages in shared/protocol.md.

export type CpuLevel = "easy" | "medium" | "hard" | "expert";
export const CPU_LEVELS: readonly CpuLevel[] = ["easy", "medium", "hard", "expert"];
export type Phase = "lobby" | "playing" | "finished";

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
] as const;
export const EVENT_KINDS = ["drew", "went_out", "staging_expired", "stalemate", "kicked"] as const;
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
}

export interface TablePile {
  id: number;
  cards: number[];
  locked_by: string | null;
}

export interface GameView {
  version: number;
  deck: number;
  table: TablePile[];
  places: string[][];
  draw_votes: string[];
  staging_timeout: number;
  hand?: number[];
  staging?: { piles: number[]; remaining: number } | null;
}

export interface StateMessage {
  type: "state";
  version: number;
  code: string;
  phase: Phase;
  host: string | null;
  you: string;
  options: { decks: number; hand_size: number };
  /** CPUs are sped up (only CPUs are still playing). */
  fast_forward: boolean;
  /** A tutorial game against the scripted Teacher. */
  tutorial: boolean;
  players: PlayerView[];
  game: GameView | null;
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
