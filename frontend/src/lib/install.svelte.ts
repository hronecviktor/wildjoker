// Installing the site as an app. Chrome and Edge (Android, desktop) offer a
// prompt the page can open from a button; iOS has none, so there the button
// shows how to add the site to the home screen by hand. Imported at startup
// so the browser's early beforeinstallprompt isn't missed.

interface InstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

const standaloneQuery = typeof matchMedia !== "undefined" ? matchMedia("(display-mode: standalone)") : null;

export const install = $state({
  /** Running as an installed app. */
  standalone: isStandalone(),
  /** The browser's install prompt, when it offers one. */
  prompt: null as InstallPromptEvent | null,
  /** iPhone or iPad, where installing is done from the share menu. */
  ios: isIos(),
});

function isStandalone(): boolean {
  if (typeof navigator === "undefined") return false;
  return !!standaloneQuery?.matches || (navigator as { standalone?: boolean }).standalone === true;
}

function isIos(): boolean {
  if (typeof navigator === "undefined") return false;
  // iPadOS reports itself as a Mac, but Macs have no touch screen.
  return /iPhone|iPad|iPod/.test(navigator.userAgent) || (/Macintosh/.test(navigator.userAgent) && navigator.maxTouchPoints > 1);
}

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault(); // keep it for our button instead of the browser's mini bar
    install.prompt = e as InstallPromptEvent;
  });
  window.addEventListener("appinstalled", () => {
    install.prompt = null;
  });
  standaloneQuery?.addEventListener("change", () => (install.standalone = isStandalone()));
}

/** Whether to offer installing at all. */
export function canInstall(): boolean {
  return !install.standalone && (install.prompt !== null || install.ios);
}

/** Open the browser's install prompt; false if there is none (iOS). */
export async function promptInstall(): Promise<boolean> {
  const prompt = install.prompt;
  if (!prompt) return false;
  install.prompt = null; // each prompt can only be shown once
  await prompt.prompt();
  await prompt.userChoice.catch(() => null);
  return true;
}
