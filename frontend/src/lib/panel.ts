/** Open and close the gate detail panel from any page that lists gates. */

import { tick } from "svelte";
import { navigate, router, type Route } from "./router.svelte";

/**
 * Open a gate's panel. Switching gates while a panel is open replaces its history entry, so
 * closing still goes back once.
 */
export function openGatePanel(gate: { repo: string | null; name: string }, panelOpen: boolean): void {
  navigate({ page: "gate", repo: gate.repo, name: gate.name }, { replace: panelOpen });
}

let closing = false;

/**
 * Close the panel and return to the page it was opened from: back through history when the
 * app opened it, else to `fallback`. Focus goes to the row whose `data-key` is `key` when that
 * page shows it, else to the main region.
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
    (row || document.querySelector<HTMLElement>("main"))?.focus();
  } finally {
    closing = false;
  }
}
