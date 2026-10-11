import { get } from "svelte/store";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createVoice, VoiceError } from "./index";
import { parseSignal, timing } from "./peer";
import { SpeakingDetector } from "./speaking";
import { FakeEnv, FakeServer, meshProblems, seeded } from "./testing";

const newServer = (seed = 1) => new FakeServer((send, env) => createVoice(send, env), seeded(seed));

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("mesh", () => {
  it("connects players who join one after another", async () => {
    const server = newServer();
    const [a, b, c] = ["a", "b", "c"].map((id) => server.add(id));
    await server.settle(2);
    for (const client of [a, b, c]) {
      await client.voice.join();
      await server.settle();
      expect(meshProblems(server)).toEqual([]);
    }
    expect(a.env.open()).toHaveLength(2);
    expect(a.env.iceRequests).toEqual(["a"]);
    expect(a.env.pcs[0].config.iceServers).toEqual(a.env.ice.iceServers);
  });

  it.each([1, 2, 3, 4, 5, 6, 7, 8])("survives everyone joining at once (seed %i)", async (seed) => {
    const server = newServer(seed);
    const clients = ["a", "b", "c", "d", "e"].map((id) => server.add(id));
    await server.settle(2);
    await Promise.all(clients.map((c) => c.voice.join()));
    await server.settle();
    expect(meshProblems(server)).toEqual([]);
    // Offers crossed and were resolved by rolling back.
    expect(clients.flatMap((c) => c.env.pcs).some((pc) => pc.rollbacks > 0)).toBe(true);
  });

  it("handles leaving and rejoining", async () => {
    const server = newServer();
    const [a, b, c] = ["a", "b", "c"].map((id) => server.add(id));
    await server.settle(2);
    await Promise.all([a, b, c].map((x) => x.voice.join()));
    await server.settle();

    b.voice.leave();
    await server.settle();
    expect(b.env.open()).toHaveLength(0);
    expect(b.env.streams[0].tracks[0].stopped).toBe(true);
    expect(b.sent.at(-1)).toEqual({ type: "voice_leave" });
    expect(meshProblems(server)).toEqual([]);
    expect(a.env.open()).toHaveLength(1);

    await b.voice.join();
    await server.settle();
    expect(meshProblems(server)).toEqual([]);
  });

  it("rejoins voice after the game socket reconnects", async () => {
    const server = newServer();
    const [a, b] = ["a", "b"].map((id) => server.add(id));
    await server.settle(2);
    await Promise.all([a, b].map((x) => x.voice.join()));
    await server.settle();
    const before = a.env.pcs[0];

    vi.spyOn(Date, "now").mockReturnValue(Date.now() + 10_000); // well past the retry delay
    server.reconnect("a");
    await server.settle();
    expect(a.sent.filter((m) => m.type === "voice_join")).toHaveLength(2);
    expect(before.closed).toBe(true);
    expect(meshProblems(server)).toEqual([]);
  });

  it("does not resend voice_join while waiting for the server", async () => {
    const server = newServer();
    const a = server.add("a");
    await server.settle(2);
    await a.voice.join();
    // A state from before our voice_join arrived.
    a.voice.updatePeers([{ id: "a", voice: false }], "a");
    a.voice.updatePeers([{ id: "a", voice: false }], "a");
    expect(a.sent.filter((m) => m.type === "voice_join")).toHaveLength(1);
  });

  it("ignores repeated identical states", async () => {
    const server = newServer();
    const [a, b] = ["a", "b"].map((id) => server.add(id));
    await server.settle(2);
    await Promise.all([a, b].map((x) => x.voice.join()));
    await server.settle();
    const players = server.players.map((p) => ({ ...p }));
    for (let i = 0; i < 20; i++) a.voice.updatePeers(players, "a");
    await server.settle(5);
    expect(a.env.pcs).toHaveLength(1);
    expect(meshProblems(server)).toEqual([]);
  });

  it("replaces the connection when the other side starts a new one", async () => {
    const server = newServer();
    const [a, b] = ["a", "b"].map((id) => server.add(id));
    await server.settle(2);
    await Promise.all([a, b].map((x) => x.voice.join()));
    await server.settle();

    // b leaves and rejoins, but a never sees the states in between.
    server.deliverStates = false;
    b.voice.leave();
    await server.settle(5);
    server.players.find((p) => p.id === "b")!.voice = true;
    server.deliverStates = true;
    server.broadcast();
    await b.voice.join();
    await server.settle();
    expect(a.env.pcs.filter((pc) => pc.closed)).toHaveLength(1);
    expect(meshProblems(server)).toEqual([]);
  });

  it("drops signals that are not for the current connection", async () => {
    const server = newServer();
    const [a, b] = ["a", "b"].map((id) => server.add(id));
    await server.settle(2);
    await Promise.all([a, b].map((x) => x.voice.join()));
    await server.settle();
    const pcs = a.env.pcs.length;
    a.voice.handleSignal("b", { sid: "b-old", to: "a-other", description: { type: "offer", sdp: "x" } });
    a.voice.handleSignal("b", { nonsense: true });
    a.voice.handleSignal("b", "garbage");
    await server.settle(5);
    expect(a.env.pcs).toHaveLength(pcs);
    expect(meshProblems(server)).toEqual([]);
  });

  it("recovers with an ICE restart", async () => {
    const server = newServer();
    const [a, b] = ["a", "b"].map((id) => server.add(id));
    await server.settle(2);
    await Promise.all([a, b].map((x) => x.voice.join()));
    await server.settle();
    const pc = a.env.pcs[0];
    pc.fail();
    await server.settle();
    expect(pc.restarts).toBe(1);
    expect(pc.closed).toBe(false);
    expect(meshProblems(server)).toEqual([]);
  });

  it("restarts ICE, then replaces a connection that stays failed", async () => {
    vi.spyOn(timing, "failedTimeout", "get").mockReturnValue(20);
    const server = newServer();
    const [a, b] = ["a", "b"].map((id) => server.add(id));
    await server.settle(2);
    await Promise.all([a, b].map((x) => x.voice.join()));
    await server.settle();
    // a < b, so b is the impolite side that replaces connections.
    const pc = b.env.pcs[0];
    pc.fail(true);
    expect(pc.restarts).toBe(1);
    await new Promise((resolve) => setTimeout(resolve, 30));
    await server.settle();
    expect(pc.closed).toBe(true);
    expect(a.env.pcs.filter((x) => x.closed)).toHaveLength(1);
    expect(meshProblems(server)).toEqual([]);
  });

  it("closes everything when the player moves to another seat", async () => {
    const server = newServer();
    const [a, b] = ["a", "b"].map((id) => server.add(id));
    await server.settle(2);
    await Promise.all([a, b].map((x) => x.voice.join()));
    await server.settle();
    a.voice.updatePeers([{ id: "z", voice: false }], "z");
    expect(a.env.open()).toHaveLength(0);
    expect(a.env.playing()).toHaveLength(0);
  });
});

describe("joining", () => {
  const solo = () => {
    const env = new FakeEnv("a");
    const sent: Record<string, unknown>[] = [];
    const voice = createVoice((m) => sent.push(m as Record<string, unknown>), env);
    voice.updatePeers([{ id: "a", voice: false }], "a");
    return { env, sent, voice };
  };

  it.each([
    ["NotAllowedError", "permission_denied"],
    ["NotFoundError", "no_device"],
    ["NotReadableError", "device_busy"],
    ["SecurityError", "insecure_context"],
    ["NotSupportedError", "unsupported"],
    ["Weird", "failed"],
  ])("maps %s to %s", async (name, code) => {
    const { env, sent, voice } = solo();
    env.mediaError = Object.assign(new Error(name), { name });
    const error = await voice.join().catch((e) => e);
    expect(error).toBeInstanceOf(VoiceError);
    expect(error.code).toBe(code);
    expect(sent).toEqual([]);
    // Can try again.
    env.mediaError = null;
    await voice.join();
    expect(sent).toEqual([{ type: "voice_join" }]);
  });

  it("joining twice asks for the mic once", async () => {
    const { env, sent, voice } = solo();
    await Promise.all([voice.join(), voice.join()]);
    await voice.join();
    expect(env.streams).toHaveLength(1);
    expect(sent).toEqual([{ type: "voice_join" }]);
  });

  it("leaving while waiting for the mic releases it", async () => {
    const { env, sent, voice } = solo();
    const joining = voice.join();
    voice.leave();
    await joining;
    expect(env.streams[0].tracks[0].stopped).toBe(true);
    expect(sent).toEqual([]);
  });

  it("works without ICE config from the server", async () => {
    const { env, voice } = solo();
    env.fetchIceConfig = () => Promise.reject(new Error("offline"));
    vi.spyOn(console, "warn").mockImplementation(() => {});
    await voice.join();
    voice.updatePeers(
      [
        { id: "a", voice: true },
        { id: "b", voice: true },
      ],
      "a",
    );
    expect(env.pcs[0].config.iceServers?.[0].urls).toEqual(["stun:stun.l.google.com:19302"]);
  });

  it("refreshes TURN credentials before they expire", async () => {
    vi.useFakeTimers();
    const { env, voice } = solo();
    const joined = voice.join();
    await vi.advanceTimersByTimeAsync(1);
    await joined;
    voice.updatePeers(
      [
        { id: "a", voice: true },
        { id: "b", voice: true },
      ],
      "a",
    );
    env.ice = { iceServers: [{ urls: ["turn:new"], username: "u2", credential: "c2" }], ttl: 100 };
    await vi.advanceTimersByTimeAsync(80_000);
    expect(env.iceRequests).toEqual(["a", "a"]);
    expect(env.pcs[0].config.iceServers).toEqual(env.ice.iceServers);
    voice.leave();
  });
});

describe("mute and speaking", () => {
  it("mutes the track and tells the server", async () => {
    const server = newServer();
    const a = server.add("a");
    await server.settle(2);
    await a.voice.join();
    a.voice.setMuted(true);
    expect(a.env.streams[0].tracks[0].enabled).toBe(false);
    expect(a.sent.at(-1)).toEqual({ type: "voice_mute", muted: true });
    a.voice.setMuted(false);
    expect(a.env.streams[0].tracks[0].enabled).toBe(true);
  });

  it("keeps a mute chosen before joining", async () => {
    const server = newServer();
    const a = server.add("a");
    await server.settle(2);
    a.voice.setMuted(true);
    expect(a.sent).toEqual([]);
    await a.voice.join();
    expect(a.env.streams[0].tracks[0].enabled).toBe(false);
    expect(a.sent).toEqual([{ type: "voice_join" }, { type: "voice_mute", muted: true }]);
    await server.settle();
    expect(server.players[0]).toMatchObject({ voice: true, muted: true });
  });

  it("reports who is speaking, never a muted player", async () => {
    const server = newServer();
    const [a, b] = ["a", "b"].map((id) => server.add(id));
    await server.settle(2);
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] });
    await Promise.all([a, b].map((x) => x.voice.join()));
    await server.settle();

    const local = a.env.streams[0];
    const remote = a.env.playing()[0].stream;
    a.env.levels.set(local, 0.2);
    a.env.levels.set(remote, 0.2);
    vi.advanceTimersByTime(300);
    expect(get(a.voice.speaking)).toEqual(new Set(["a", "b"]));

    a.voice.setMuted(true);
    expect(get(a.voice.speaking)).toEqual(new Set(["b"]));
    vi.advanceTimersByTime(300);
    expect(get(a.voice.speaking)).toEqual(new Set(["b"]));

    // b muted, as seen in the state.
    a.voice.updatePeers(
      [
        { id: "a", voice: true, muted: true },
        { id: "b", voice: true, muted: true },
      ],
      "a",
    );
    expect(get(a.voice.speaking)).toEqual(new Set());

    a.voice.updatePeers(
      [
        { id: "a", voice: true, muted: true },
        { id: "b", voice: true, muted: false },
      ],
      "a",
    );
    a.env.levels.set(remote, 0);
    vi.advanceTimersByTime(1000);
    expect(get(a.voice.speaking)).toEqual(new Set());
    a.voice.leave();
  });

  it("detector debounces", () => {
    const d = new SpeakingDetector(0.1, 100, 500);
    expect(d.update(0.5, 0)).toBe(false);
    expect(d.update(0.5, 100)).toBe(true);
    expect(d.update(0, 200)).toBe(true);
    expect(d.update(0.5, 300)).toBe(true); // a short pause doesn't count
    expect(d.update(0, 400)).toBe(true);
    expect(d.update(0, 899)).toBe(true);
    expect(d.update(0, 900)).toBe(false);
    expect(d.update(0.5, 1000)).toBe(false); // a click doesn't count
    expect(d.update(0, 1050)).toBe(false);
  });
});

describe("playback", () => {
  it("waits for a user gesture when autoplay is blocked", async () => {
    const server = newServer();
    const [a, b] = ["a", "b"].map((id) => server.add(id));
    a.env.autoplayAllowed = false;
    await server.settle(2);
    await Promise.all([a, b].map((x) => x.voice.join()));
    await server.settle();
    expect(get(a.voice.playbackBlocked)).toBe(true);
    expect(get(b.voice.playbackBlocked)).toBe(false);

    a.env.autoplayAllowed = true;
    a.env.gesture();
    await server.settle(2);
    expect(get(a.voice.playbackBlocked)).toBe(false);
    expect(a.env.playing()[0].plays).toBe(2);
  });
});

describe("parseSignal", () => {
  it("accepts descriptions and candidates", () => {
    expect(parseSignal({ sid: "x", description: { type: "offer", sdp: "v=0" } })).toBeTruthy();
    expect(parseSignal({ sid: "x", to: "y", candidate: { candidate: "c" } })).toBeTruthy();
  });

  it.each([null, "x", {}, { sid: 1, candidate: {} }, { sid: "x" }, { sid: "x", to: 3, candidate: {} }, { sid: "x", description: { type: "rollback" } }])(
    "rejects %j",
    (data) => expect(parseSignal(data)).toBeNull(),
  );
});
