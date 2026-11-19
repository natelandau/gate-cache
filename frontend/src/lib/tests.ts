import type { ReportProblems } from "./api";
import { formatCount } from "./format";

const PROBLEM_LABELS: [keyof ReportProblems, string][] = [
  ["missing", "missing"],
  ["stale", "stale"],
  ["invalid", "unreadable"],
];

/**
 * Describe the test report problems of a gate's recent runs in one sentence that counts each
 * kind, or return null when no run had one.
 */
export function reportProblemText(problems: ReportProblems): string | null {
  const parts = PROBLEM_LABELS.filter(([key]) => problems[key] > 0).map(
    ([key, label]) => `${formatCount(problems[key])} ${label}`,
  );
  if (!parts.length) return null;
  return `Recent runs had problems with their test reports: ${parts.join(", ")}. The report path may be wrong.`;
}
