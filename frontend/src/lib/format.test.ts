import { describe, expect, it } from "vitest";
import { durationTicks, formatAxisDuration, formatBytes, formatCount, formatDuration, formatLongDay, formatPercent, formatRatio, formatRelative, formatShortDay, formatSignedDuration, plural, valueParts } from "./format";

describe("formatSignedDuration", () => {
  it("prefixes a negative duration with a minus sign", () => {
    expect(formatSignedDuration(-90)).toBe("\u22121m 30s");
    expect(formatSignedDuration(90)).toBe("1m 30s");
  });

  it("drops the sign for less than a second below zero", () => {
    expect(formatSignedDuration(-0.7)).toBe("<1s");
    expect(formatSignedDuration(-1)).toBe("\u22121s");
  });
});

describe("formatDuration", () => {
  it("matches the Python format_duration table", () => {
    expect(formatDuration(0.4)).toBe("<1s");
    expect(formatDuration(42)).toBe("42s");
    expect(formatDuration(94)).toBe("1m 34s");
    expect(formatDuration(3720)).toBe("1h 2m");
    expect(formatDuration(null)).toBe("n/a");
  });

  it("handles boundaries", () => {
    expect(formatDuration(0)).toBe("<1s");
    expect(formatDuration(1)).toBe("1s");
    expect(formatDuration(59.9)).toBe("1m 0s");
    expect(formatDuration(1.5)).toBe("2s");
    expect(formatDuration(3629)).toBe("1h 0m");
    expect(formatDuration(3630)).toBe("1h 1m");
    expect(formatDuration(60)).toBe("1m 0s");
    expect(formatDuration(3600)).toBe("1h 0m");
    expect(formatDuration(90000)).toBe("25h 0m");
  });
});

describe("formatPercent", () => {
  it("rounds to a whole percent", () => {
    expect(formatPercent(0.714)).toBe("71%");
    expect(formatPercent(1)).toBe("100%");
    expect(formatPercent(0)).toBe("0%");
    expect(formatPercent(null)).toBe("n/a");
  });
});

describe("formatRelative", () => {
  it("picks the largest whole unit", () => {
    expect(formatRelative(100, 112)).toBe("12s ago");
    expect(formatRelative(0, 180)).toBe("3m ago");
    expect(formatRelative(0, 7200)).toBe("2h ago");
    expect(formatRelative(0, 4 * 86400)).toBe("4d ago");
  });

  it("clamps clock skew to zero", () => {
    expect(formatRelative(200, 100)).toBe("0s ago");
  });
});

describe("formatCount", () => {
  it("groups thousands", () => {
    expect(formatCount(1234567)).toBe("1,234,567");
  });
});

describe("durationTicks", () => {
  it("steps by a readable unit", () => {
    expect(durationTicks(1100)).toEqual([0, 600, 1200]);
    expect(durationTicks(45)).toEqual([0, 15, 30, 45]);
    expect(durationTicks(4 * 3600)).toEqual([0, 7200, 14400]);
  });

  it("returns a single zero tick for an empty axis", () => {
    expect(durationTicks(0)).toEqual([0]);
  });
});

describe("formatAxisDuration", () => {
  it("drops zero trailing units and writes 0 bare", () => {
    expect(formatAxisDuration(0)).toBe("0");
    expect(formatAxisDuration(600)).toBe("10m");
    expect(formatAxisDuration(3600)).toBe("1h");
    expect(formatAxisDuration(90)).toBe("1m 30s");
  });
});

describe("plural", () => {
  it("counts with the singular for one and the plural otherwise", () => {
    expect(plural(1, "failure", "failures")).toBe("1 failure");
    expect(plural(0, "failure", "failures")).toBe("0 failures");
    expect(plural(1200, "run", "runs")).toBe("1,200 runs");
  });
});

describe("formatBytes", () => {
  it("uses binary units, one decimal from MiB up", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1536)).toBe("1.5 KiB");
    expect(formatBytes(52428800)).toBe("50.0 MiB");
    expect(formatBytes(3 * 1024 ** 3)).toBe("3.0 GiB");
  });

  it("matches the duration text for null", () => {
    expect(formatBytes(null)).toBe(formatDuration(null));
  });
});

describe("formatRatio", () => {
  it("renders one decimal with a times sign", () => {
    expect(formatRatio(3.42)).toBe("3.4×");
    expect(formatRatio(1)).toBe("1.0×");
  });

  it("matches the duration text for null", () => {
    expect(formatRatio(null)).toBe(formatDuration(null));
  });
});

describe("day formatters", () => {
  it("name the calendar day without shifting it by the local offset", () => {
    expect(formatShortDay("2026-11-10")).toMatch(/^(Nov 10|10 Nov)$/);
    expect(formatShortDay("2026-01-01")).toContain("1");
  });

  it("add the weekday and year", () => {
    const text = formatLongDay("2026-11-10");
    expect(text).toContain("Tue");
    expect(text).toContain("2026");
    expect(text).toContain("10");
  });
});

describe("valueParts", () => {
  it("splits units from the digits of a duration", () => {
    expect(valueParts("6h 38m")).toEqual([
      { text: "6", unit: false },
      { text: "h", unit: true },
      { text: " ", unit: false },
      { text: "38", unit: false },
      { text: "m", unit: true },
    ]);
  });

  it("treats a percent sign as a unit and leaves a plain count whole", () => {
    expect(valueParts("61%")).toEqual([
      { text: "61", unit: false },
      { text: "%", unit: true },
    ]);
    expect(valueParts("1,705")).toEqual([{ text: "1,705", unit: false }]);
  });

  it("keeps a sign with its number", () => {
    expect(valueParts("−2m")[0]).toEqual({ text: "−2", unit: false });
  });
});
