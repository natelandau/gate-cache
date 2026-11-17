import { describe, expect, it } from "vitest";
import { QueryTracker } from "./query.svelte";

function tracker() {
  return new QueryTracker<string>({ data: undefined, error: undefined, loading: true });
}

describe("QueryTracker", () => {
  it("keeps data undimmed through a reload for the same inputs", () => {
    const t = tracker();
    t.begin("a");
    t.succeed("a", "first");
    t.begin("a");
    expect(t.state).toMatchObject({ data: "first", loading: false });
    t.succeed("a", "second");
    expect(t.state.data).toBe("second");
  });

  it("dims on new inputs and drops the old data when their load fails", () => {
    const t = tracker();
    t.begin("gate A");
    t.succeed("gate A", "A");
    t.begin("gate B");
    expect(t.state).toMatchObject({ data: "A", loading: true });
    t.fail("gate B", new Error("boom"));
    expect(t.state.data).toBeUndefined();
    expect(t.state.error?.message).toBe("boom");
    expect(t.state.loading).toBe(false);
  });

  it("keeps the data when a reload for the same inputs fails", () => {
    const t = tracker();
    t.begin("a");
    t.succeed("a", "first");
    t.begin("a");
    t.fail("a", "blip");
    expect(t.state).toMatchObject({ data: "first", loading: false });
    expect(t.state.error?.message).toBe("blip");
  });

  it("clears the error on the next success", () => {
    const t = tracker();
    t.begin("a");
    t.fail("a", new Error("x"));
    t.succeed("a", "ok");
    expect(t.state.error).toBeUndefined();
  });
});
