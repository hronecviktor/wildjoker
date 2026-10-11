// The game WebSocket: requests with replies, automatic resume, reconnects
// with backoff, and the latest state. See shared/protocol.md.

import type {
  ErrorMessage,
  EventMessage,
  Reply,
  ServerMessage,
  SignalMessage,
  StateMessage,
  WelcomeMessage,
} from "./protocol";
import { sessions } from "./storage";

export type Status = "idle" | "connecting" | "open" | "reconnecting" | "replaced";

/** A request the server rejected; `code` is one of the protocol error codes. */
export class ServerError extends Error {
  constructor(public code: string) {
    super(code);
  }
}

const PING_INTERVAL = 25_000;
const MAX_BACKOFF = 10_000;
/** Close code the server uses when a newer connection takes the seat. */
const REPLACED = 4000;

interface Pending {
  resolve: (reply: Reply) => void;
  reject: (error: ServerError) => void;
}

function defaultUrl(): string {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}/ws`;
}

export class Connection {
  status = $state<Status>("idle");
  /** The latest state for the room we're in. */
  state = $state.raw<StateMessage | null>(null);
  /** Room code and player id once joined. */
  code = $state<string | null>(null);
  you = $state<string | null>(null);

  onEvent: (event: EventMessage) => void = () => {};
  onSignal: (signal: SignalMessage) => void = () => {};
  /** Called after every welcome, including automatic resumes. */
  onJoined: () => void = () => {};
  /** Called when the socket drops while joined. */
  onDropped: () => void = () => {};
  /** Called when an automatic resume fails (room gone, token rejected). */
  onLost: (code: string, error: string) => void = () => {};

  private ws: WebSocket | null = null;
  private wanted = false;
  private joined = false;
  private nextReq = 1;
  private pending = new Map<number, Pending>();
  private openWaiters: { resolve: () => void; reject: (e: ServerError) => void }[] = [];
  private readyWaiters: (() => void)[] = [];
  private attempt = 0;
  private retryTimer: ReturnType<typeof setTimeout> | undefined;
  private pingTimer: ReturnType<typeof setInterval> | undefined;

  constructor(private url: string = defaultUrl()) {
    if (typeof window !== "undefined") {
      window.addEventListener("online", () => this.reconnectNow());
      document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") this.reconnectNow();
      });
    }
  }

  /** Create a room; resolves once we're its host. */
  async create(name: string): Promise<void> {
    await this.join({ type: "create", name });
  }

  /** Start a tutorial game against the scripted Teacher. */
  async tutorial(name: string, teacher: string): Promise<void> {
    await this.join({ type: "tutorial", name, teacher });
  }

  /** Join a room by its code. */
  async joinRoom(code: string, name: string): Promise<void> {
    await this.join({ type: "join", code, name });
  }

  /** Take back our seat with a stored token. */
  async resume(code: string, token: string): Promise<void> {
    await this.join({ type: "resume", code, token });
  }

  /** Leave the room for good (forgets the resume token). */
  async leave(): Promise<void> {
    const code = this.code;
    try {
      await this.request({ type: "leave" });
    } finally {
      this.forget(code);
    }
  }

  /** Forget the current room without telling the server (kicked, room gone). */
  forget(code: string | null = this.code): void {
    if (code) sessions.forget(code);
    this.wanted = false;
    this.joined = false;
    this.code = this.you = null;
    this.state = null;
    clearTimeout(this.retryTimer);
    this.ws?.close();
    this.ws = null;
    this.status = "idle";
  }

  /** After another tab took the seat: take it back here. */
  takeOver(): void {
    if (this.status === "replaced") {
      this.wanted = true;
      this.open();
    }
  }

  /** Send a game or lobby message and wait for the reply. */
  async request(msg: { type: string; [key: string]: unknown }): Promise<Reply> {
    await this.ready();
    return this.sendRaw(msg);
  }

  /** Send without waiting (voice signalling); replies and errors are ignored. */
  send = (msg: object): void => {
    if (this.joined && this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  };

  // -- internals -----------------------------------------------------------

  private async join(msg: { type: string; [key: string]: unknown }): Promise<void> {
    this.wanted = true;
    await this.opened();
    const reply = (await this.sendRaw(msg)) as WelcomeMessage;
    this.welcome(reply);
  }

  private welcome(reply: WelcomeMessage): void {
    if (reply.code !== this.code) this.state = null;
    this.code = reply.code;
    this.you = reply.you;
    this.joined = true;
    this.attempt = 0;
    sessions.set(reply.code, reply.token);
    this.readyWaiters.splice(0).forEach((f) => f());
    this.onJoined();
  }

  private sendRaw(msg: object): Promise<Reply> {
    const ws = this.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN) return Promise.reject(new ServerError("disconnected"));
    const req = this.nextReq++;
    return new Promise((resolve, reject) => {
      this.pending.set(req, { resolve, reject });
      ws.send(JSON.stringify({ ...msg, req }));
    });
  }

  private opened(): Promise<void> {
    if (this.ws?.readyState === WebSocket.OPEN) return Promise.resolve();
    this.open();
    return new Promise((resolve, reject) => this.openWaiters.push({ resolve, reject }));
  }

  private ready(): Promise<void> {
    if (this.joined && this.ws?.readyState === WebSocket.OPEN) return Promise.resolve();
    if (!this.code) return Promise.reject(new ServerError("not_joined"));
    this.open();
    return new Promise((resolve) => this.readyWaiters.push(resolve));
  }

  private open(): void {
    if (this.ws && this.ws.readyState <= WebSocket.OPEN) return;
    clearTimeout(this.retryTimer);
    this.status = this.attempt > 0 || this.code ? "reconnecting" : "connecting";
    const ws = new WebSocket(this.url);
    this.ws = ws;
    ws.onopen = () => this.handleOpen(ws);
    ws.onmessage = (e) => this.ws === ws && this.handleMessage(JSON.parse(e.data as string));
    ws.onclose = (e) => this.handleClose(ws, e.code);
  }

  private handleOpen(ws: WebSocket): void {
    if (this.ws !== ws) return;
    this.status = "open";
    clearInterval(this.pingTimer);
    this.pingTimer = setInterval(() => this.send({ type: "ping" }), PING_INTERVAL);
    this.openWaiters.splice(0).forEach((w) => w.resolve());
    // Coming back after a drop: take our seat again.
    const token = this.code && sessions.get(this.code);
    if (this.code && !this.joined) {
      const code = this.code;
      if (!token) {
        this.lost(code, "bad_token");
        return;
      }
      this.sendRaw({ type: "resume", code, token })
        .then((reply) => this.welcome(reply as WelcomeMessage))
        .catch((e: ServerError) => {
          if (e.code !== "disconnected") this.lost(code, e.code);
        });
    }
  }

  private lost(code: string, error: string): void {
    this.forget(code);
    this.readyWaiters.splice(0);
    this.onLost(code, error);
  }

  private handleMessage(msg: ServerMessage): void {
    switch (msg.type) {
      case "state":
        // Ignore a state older than the one we have (e.g. after a reconnect race).
        if (this.state && this.state.code === msg.code && msg.version < this.state.version) return;
        this.state = msg;
        break;
      case "welcome":
      case "ok":
      case "error": {
        const pending = msg.req != null ? this.pending.get(msg.req) : undefined;
        if (!pending) return;
        this.pending.delete(msg.req!);
        if (msg.type === "error") pending.reject(new ServerError((msg as ErrorMessage).code));
        else pending.resolve(msg);
        break;
      }
      case "event":
        this.onEvent(msg);
        break;
      case "signal":
        this.onSignal(msg);
        break;
    }
  }

  private handleClose(ws: WebSocket, code: number): void {
    if (this.ws !== ws) return;
    this.ws = null;
    clearInterval(this.pingTimer);
    const wasJoined = this.joined;
    this.joined = false;
    for (const p of this.pending.values()) p.reject(new ServerError("disconnected"));
    this.pending.clear();
    if (wasJoined) this.onDropped();
    if (code === REPLACED) {
      this.status = "replaced";
      this.wanted = false;
      return;
    }
    if (!this.wanted || !this.code) {
      this.openWaiters.splice(0).forEach((w) => w.reject(new ServerError("disconnected")));
      this.status = "idle";
      this.wanted = false;
      return;
    }
    this.status = "reconnecting";
    const delay = Math.min(MAX_BACKOFF, 500 * 2 ** this.attempt) * (0.75 + Math.random() / 2);
    this.attempt++;
    this.retryTimer = setTimeout(() => this.open(), delay);
  }

  private reconnectNow(): void {
    if (this.wanted && this.code && this.status === "reconnecting" && !this.ws) {
      this.attempt = 0;
      this.open();
    }
  }
}
