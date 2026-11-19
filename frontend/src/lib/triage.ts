/** Helpers for the Triage page: its reasons and which rows a reason filter keeps. */

import type { TriageItem, TriageReason } from "./api";
import { gateKey } from "./gates";
import { hasKey } from "./guards";
import { TRIAGE } from "./terms";

/** Every triage reason, in the order the reason filter lists them. */
export const TRIAGE_REASONS = Object.keys(TRIAGE.reasons) as TriageReason[];

/** Return whether a hash or API value names a triage reason. */
export function isTriageReason(value: string | null): value is TriageReason {
  return hasKey(TRIAGE.reasons, value);
}

/** Return a key unique to one row: a gate appears once per reason. */
export function triageKey(item: TriageItem): string {
  return `${gateKey(item)}\n${item.reason}`;
}
