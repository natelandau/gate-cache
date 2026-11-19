import { describe, expect, it } from "vitest";
import { isTriageReason } from "./triage";

describe("isTriageReason", () => {
  it.each([
    ["flaky", true],
    ["failed_spot_check", true],
    ["fail", false],
    ["toString", false],
    [null, false],
  ])("%s is %s", (value, expected) => {
    expect(isTriageReason(value)).toBe(expected);
  });
});
