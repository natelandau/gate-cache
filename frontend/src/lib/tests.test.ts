import { describe, expect, it } from "vitest";
import { reportProblemText } from "./tests";

describe("reportProblemText", () => {
  it("is null when no recent run had a report problem", () => {
    expect(reportProblemText({ missing: 0, stale: 0, invalid: 0 })).toBeNull();
  });

  it.each([
    [{ missing: 2, stale: 0, invalid: 0 }, ["2 missing"], ["stale", "unreadable"]],
    [{ missing: 0, stale: 1, invalid: 3 }, ["1 stale", "3 unreadable"], ["missing"]],
  ])("names only the problems that occurred", (problems, named, absent) => {
    const text = reportProblemText(problems) ?? "";
    for (const part of named) expect(text).toContain(part);
    for (const part of absent) expect(text).not.toContain(part);
  });
});
