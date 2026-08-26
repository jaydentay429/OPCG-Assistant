/**
 * Copy text with a fallback for non-secure contexts: `navigator.clipboard` is
 * unavailable over plain http (e.g. opening the dev server via a LAN IP), and
 * some mobile browsers resolve the promise without actually writing.
 */
export async function copyTextToClipboard(text: string): Promise<boolean> {
  const value = String(text ?? "");
  if (!value) return false;

  // Try the legacy path first when the async API is unavailable, so we never
  // report success for a write that never happened.
  if (typeof navigator !== "undefined" && window.isSecureContext && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch {
      /* fall through to execCommand */
    }
  }

  return legacyCopy(value);
}

function legacyCopy(value: string): boolean {
  if (typeof document === "undefined") return false;
  const el = document.createElement("textarea");
  el.value = value;
  el.setAttribute("readonly", "");
  el.style.position = "fixed";
  el.style.top = "0";
  el.style.left = "0";
  el.style.opacity = "0";
  document.body.appendChild(el);
  try {
    el.focus();
    el.select();
    el.setSelectionRange(0, value.length);
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    document.body.removeChild(el);
  }
}
