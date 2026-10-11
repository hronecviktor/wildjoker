// Everything the voice module needs from the browser, behind one interface so
// the negotiation logic can be tested with fakes in Node.

export interface IceConfig {
  iceServers: RTCIceServer[];
  /** Seconds the TURN credentials stay valid. */
  ttl: number;
}

/** Plays one remote stream. */
export interface AudioSink {
  /** Rejects (NotAllowedError) when the browser wants a user gesture first. */
  play(): Promise<void>;
  remove(): void;
}

/** Measures how loud a stream is. */
export interface LevelMeter {
  /** RMS level of the latest samples, 0..1. */
  level(): number;
  close(): void;
}

export interface VoiceEnv {
  getUserMedia(constraints: MediaStreamConstraints): Promise<MediaStream>;
  createPeerConnection(config: RTCConfiguration): RTCPeerConnection;
  fetchIceConfig(player: string): Promise<IceConfig>;
  createAudioSink(stream: MediaStream): AudioSink;
  createMeter(stream: MediaStream): LevelMeter;
  /** Resume audio output that is waiting for a user gesture. */
  resumeAudio(): Promise<void>;
  /** Calls `callback` once, on the next click, tap or key press. */
  onUserGesture(callback: () => void): void;
  randomId(): string;
}

export const DEFAULT_ICE: IceConfig = {
  iceServers: [{ urls: ["stun:stun.l.google.com:19302"] }],
  ttl: 3600,
};

export function browserEnv(): VoiceEnv {
  let context: AudioContext | null = null;
  const audioContext = () => {
    if (!context && typeof AudioContext !== "undefined") context = new AudioContext();
    return context;
  };

  return {
    getUserMedia(constraints) {
      if (!navigator.mediaDevices?.getUserMedia) {
        const name = window.isSecureContext ? "NotSupportedError" : "SecurityError";
        return Promise.reject(new DOMException("getUserMedia is not available", name));
      }
      // Create the AudioContext while we are still inside the user gesture
      // that started join(), so it is allowed to run.
      audioContext()
        ?.resume()
        .catch(() => {});
      return navigator.mediaDevices.getUserMedia(constraints);
    },

    createPeerConnection: (config) => new RTCPeerConnection(config),

    async fetchIceConfig(player) {
      const response = await fetch(`/ice?player=${encodeURIComponent(player)}`, {
        cache: "no-store",
      });
      if (!response.ok) throw new Error(`/ice: ${response.status}`);
      const body = await response.json();
      return { iceServers: body.ice_servers, ttl: body.ttl };
    },

    createAudioSink(stream) {
      const audio = document.createElement("audio");
      audio.autoplay = true;
      audio.hidden = true;
      audio.dataset.voice = "";
      audio.srcObject = stream;
      document.body.append(audio);
      return {
        play: () => audio.play(),
        remove() {
          audio.srcObject = null;
          audio.remove();
        },
      };
    },

    createMeter(stream) {
      const ctx = audioContext();
      if (!ctx) return { level: () => 0, close() {} };
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      source.connect(analyser); // not connected to the output: measuring only
      const samples = new Float32Array(analyser.fftSize);
      return {
        level() {
          analyser.getFloatTimeDomainData(samples);
          let sum = 0;
          for (const s of samples) sum += s * s;
          return Math.sqrt(sum / samples.length);
        },
        close() {
          source.disconnect();
          analyser.disconnect();
        },
      };
    },

    async resumeAudio() {
      await context?.resume();
    },

    onUserGesture(callback) {
      const events = ["pointerdown", "keydown", "touchend"] as const;
      const handler = () => {
        for (const e of events) window.removeEventListener(e, handler, true);
        callback();
      };
      for (const e of events) window.addEventListener(e, handler, true);
    },

    randomId: () => Math.random().toString(36).slice(2, 10),
  };
}
