import { describe, expect, it } from "vitest";
import { nextTheme, parseTheme, resolveTheme, themeLabel } from "./theme.svelte";

describe("parseTheme", () => {
  it("accepts the three stored choices", () => {
    expect(parseTheme("system")).toBe("system");
    expect(parseTheme("light")).toBe("light");
    expect(parseTheme("dark")).toBe("dark");
  });

  it("falls back to system for anything else", () => {
    expect(parseTheme(null)).toBe("system");
    expect(parseTheme("")).toBe("system");
    expect(parseTheme("Dark")).toBe("system");
    expect(parseTheme("blue")).toBe("system");
  });
});

describe("nextTheme", () => {
  it("cycles system, light, dark, system", () => {
    expect(nextTheme("system")).toBe("light");
    expect(nextTheme("light")).toBe("dark");
    expect(nextTheme("dark")).toBe("system");
  });
});

describe("resolveTheme", () => {
  it("follows the system preference only in system mode", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });
});

describe("themeLabel", () => {
  it("names the current state and the next one", () => {
    expect(themeLabel("system")).toBe("Theme: System. Switch to light.");
    expect(themeLabel("light")).toBe("Theme: Light. Switch to dark.");
    expect(themeLabel("dark")).toBe("Theme: Dark. Switch to system.");
  });
});
