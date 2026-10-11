/** Above this RMS level (0..1) a stream counts as speaking. */
export const SPEAKING_LEVEL = 0.02;
/** How often levels are sampled, in ms. */
export const SAMPLE_INTERVAL = 100;

/**
 * Debounces a level meter into a speaking flag: it turns on after `onAfter`
 * ms above the threshold and off after `offAfter` ms below it, so the
 * indicator neither flickers on clicks nor between words.
 */
export class SpeakingDetector {
  speaking = false;
  private since: number | null = null;

  constructor(
    private threshold = SPEAKING_LEVEL,
    private onAfter = 100,
    private offAfter = 500,
  ) {}

  update(level: number, now: number): boolean {
    const loud = level >= this.threshold;
    if (loud === this.speaking) {
      this.since = null;
    } else {
      this.since ??= now;
      if (now - this.since >= (loud ? this.onAfter : this.offAfter)) {
        this.speaking = loud;
        this.since = null;
      }
    }
    return this.speaking;
  }

  reset(): void {
    this.speaking = false;
    this.since = null;
  }
}
