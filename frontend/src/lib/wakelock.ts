// Keeps the screen on while a game is open, so a phone doesn't go to sleep
// while you think. The browser drops the lock whenever the page is hidden,
// so it's taken again when the page comes back. Without the Wake Lock API
// (older browsers) the screen just sleeps as usual.

type Sentinel = { release(): Promise<void> };

/** Hold the lock until the returned function is called. */
export function keepAwake(): () => void {
  const wakeLock = (navigator as { wakeLock?: { request(type: "screen"): Promise<Sentinel> } }).wakeLock;
  if (!wakeLock) return () => {};
  let lock: Sentinel | null = null;
  let done = false;
  const take = async () => {
    if (done || document.visibilityState !== "visible") return;
    try {
      lock = await wakeLock.request("screen");
      if (done) void lock.release();
    } catch {
      // refused (battery saver) or not allowed here
    }
  };
  const onVisible = () => void take();
  document.addEventListener("visibilitychange", onVisible);
  void take();
  return () => {
    done = true;
    document.removeEventListener("visibilitychange", onVisible);
    void lock?.release().catch(() => {});
  };
}
