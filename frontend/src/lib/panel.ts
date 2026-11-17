/** Open and close the gate detail panel from any page that lists gates. */

import { tick } from "svelte";
import { navigate, router, type Route } from "./router.svelte";

/** The control that opened the panel, which gets focus back when no row matches `key`. */
let opener: HTMLElement | null = null;

/**
 * Open a gate's panel. Switching gates while a panel is open replaces its history entry, so
 * closing still goes back once to the page that opened it.
 */
export function openGatePanel(gate: { repo: string | null; name: string }): void {
  const panelOpen = router.route.page === "gate";
  if (!panelOpen) {
    const active = document.activeElement;
    opener = active instanceof HTMLElement && active !== document.body ? active : null;
  }
  navigate({ page: "gate", repo: gate.repo, name: gate.name }, { replace: panelOpen });
}

let closing = false;

/**
 * Close the panel and return to the page it was opened from: back through history when the
 * app opened it, else to `fallback`. Focus goes to the row whose `data-key` is `key` when that
 * page shows it, else to the control that opened the panel when it is still on the page, else
 * to the main region.
 */
export async function closeGatePanel(key: string | null, fallback: Route): Promise<void> {
  // A second close before the first lands would go back one history entry too far.
  if (closing) return;
  closing = true;
  try {
    const changed = new Promise<void>((resolve) => {
      window.addEventListener("hashchange", () => resolve(), { once: true });
    });
    if (router.opener) history.back();
    else navigate(fallback, { replace: true });
    await changed;
    await tick();
    const row = key && document.querySelector<HTMLElement>(`tr[data-key="${CSS.escape(key)}"]`);
    const control = opener?.isConnected ? opener : null;
    (row || control || document.querySelector<HTMLElement>("main"))?.focus();
  } finally {
    closing = false;
    opener = null;
  }
}
