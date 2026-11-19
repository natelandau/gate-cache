/**
 * How the Triage page shows each reason: the badge tone and the evidence block. The words come
 * from `TRIAGE.reasons` in `lib/terms.ts`. A new reason adds one entry there and one here.
 */

import type { Component, ComponentProps } from "svelte";
import type { TriageItem, TriageReason } from "../../lib/api";
import type Badge from "../../lib/components/Badge.svelte";
import FlakyEvidence from "./FlakyEvidence.svelte";
import SpotCheckEvidence from "./SpotCheckEvidence.svelte";

type ReasonView<R extends TriageReason> = {
  tone: ComponentProps<typeof Badge>["tone"];
  evidence: Component<{ item: Extract<TriageItem, { reason: R }> }>;
};

export const REASON_VIEWS: { [R in TriageReason]: ReasonView<R> } = {
  flaky: { tone: "flaky", evidence: FlakyEvidence },
  failed_spot_check: { tone: "danger", evidence: SpotCheckEvidence },
};

/** Return the evidence block of a row, typed for any reason. */
export function evidenceOf(item: TriageItem): Component<{ item: TriageItem }> {
  return REASON_VIEWS[item.reason].evidence as Component<{ item: TriageItem }>;
}
