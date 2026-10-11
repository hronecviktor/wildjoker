// Copying text. The Clipboard API only exists on secure pages (https or
// localhost); on a plain-http LAN address, fall back to the old
// select-and-copy command, which still works there.

export async function copyText(text: string): Promise<boolean> {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // permission denied or not focused: try the fallback
    }
  }
  return legacyCopy(text);
}

function legacyCopy(text: string): boolean {
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  // Off-screen but focusable; a font size of 16px stops iOS from zooming.
  area.style.cssText = "position:fixed;top:0;left:-9999px;opacity:0;font-size:16px";
  document.body.append(area);
  const focused = document.activeElement as HTMLElement | null;
  area.select();
  area.setSelectionRange(0, text.length);
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  area.remove();
  focused?.focus();
  return ok;
}
