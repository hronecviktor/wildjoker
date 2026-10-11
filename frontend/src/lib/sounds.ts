// Subtle sound effects, made with Web Audio so there are no files to load:
// a soft card flick when anyone draws, and a short chime when someone goes out.
// Browsers only allow audio after the user has interacted with the page, so
// the context starts on the first tap or key press.

import { load, save } from "./storage";

let ctx: AudioContext | null = null;
let enabled = load<boolean>("sound", true);
let lastDraw = 0;

function unlock(): void {
  if (!ctx && typeof AudioContext !== "undefined") ctx = new AudioContext();
  if (ctx?.state === "suspended") void ctx.resume();
}
if (typeof window !== "undefined") {
  for (const type of ["pointerdown", "keydown"]) window.addEventListener(type, unlock, { capture: true });
}

export function soundOn(): boolean {
  return enabled;
}

export function setSound(on: boolean): void {
  enabled = on;
  save("sound", on);
  if (on) unlock();
}

function ready(): AudioContext | null {
  return enabled && ctx?.state === "running" ? ctx : null;
}

/** A soft flick of a card sliding off the deck. */
export function drawSound(): void {
  const ac = ready();
  if (!ac) return;
  // Fast-forwarded CPUs draw many cards a second: one flick is enough.
  if (ac.currentTime - lastDraw < 0.08) return;
  lastDraw = ac.currentTime;
  const t = ac.currentTime;
  const length = 0.12;
  const buffer = ac.createBuffer(1, Math.ceil(ac.sampleRate * length), ac.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
  const noise = ac.createBufferSource();
  noise.buffer = buffer;
  const filter = ac.createBiquadFilter();
  filter.type = "bandpass";
  filter.Q.value = 1.2;
  filter.frequency.setValueAtTime(2400, t);
  filter.frequency.exponentialRampToValueAtTime(900, t + length);
  const gain = ac.createGain();
  gain.gain.setValueAtTime(0.0001, t);
  gain.gain.exponentialRampToValueAtTime(0.18, t + 0.012);
  gain.gain.exponentialRampToValueAtTime(0.0001, t + length);
  noise.connect(filter).connect(gain).connect(ac.destination);
  noise.start(t);
  noise.stop(t + length);
}

/** A short rising chime for someone going out; a little brighter when it's you. */
export function finishSound(you: boolean): void {
  const ac = ready();
  if (!ac) return;
  const notes = you ? [523.25, 659.25, 783.99, 1046.5] : [523.25, 659.25, 783.99];
  const start = ac.currentTime + 0.02;
  notes.forEach((freq, i) => {
    const t = start + i * 0.11;
    const osc = ac.createOscillator();
    osc.type = "triangle";
    osc.frequency.value = freq;
    const gain = ac.createGain();
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(0.16, t + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.6);
    osc.connect(gain).connect(ac.destination);
    osc.start(t);
    osc.stop(t + 0.65);
  });
}
