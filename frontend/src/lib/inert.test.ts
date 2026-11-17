import { afterEach, describe, expect, it, vi } from "vitest";
import { inertOutside } from "./inert";

class FakeElement {
  readonly nodeType = 1;
  attributes = new Map<string, string>();
  children: FakeElement[] = [];
  parentElement: FakeElement | null = null;

  constructor(readonly name: string) {}

  append(...kids: FakeElement[]): this {
    for (const kid of kids) {
      kid.parentElement = this;
      this.children.push(kid);
    }
    return this;
  }

  hasAttribute(name: string): boolean {
    return this.attributes.has(name);
  }

  setAttribute(name: string, value: string): void {
    this.attributes.set(name, value);
  }

  removeAttribute(name: string): void {
    this.attributes.delete(name);
  }
}

describe("inertOutside", () => {
  it("makes everything but the element and its ancestors inert, and undoes it", () => {
    const panel = new FakeElement("panel");
    const table = new FakeElement("table");
    const main = new FakeElement("main").append(table, panel);
    const nav = new FakeElement("nav");
    const already = new FakeElement("already");
    already.setAttribute("inert", "");
    const body = new FakeElement("body").append(nav, main, already);

    const restore = inertOutside(panel as unknown as Element, body as unknown as Element);
    expect([table, nav, already].every((e) => e.hasAttribute("inert"))).toBe(true);
    expect([panel, main].some((e) => e.hasAttribute("inert"))).toBe(false);

    restore();
    expect(table.hasAttribute("inert") || nav.hasAttribute("inert")).toBe(false);
    expect(already.hasAttribute("inert")).toBe(true);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("makes siblings added later inert until cleanup", () => {
    const observers: FakeObserver[] = [];
    class FakeObserver {
      targets: FakeElement[] = [];
      disconnected = false;
      constructor(readonly callback: (records: { addedNodes: unknown[] }[]) => void) {
        observers.push(this);
      }
      observe(target: FakeElement): void {
        this.targets.push(target);
      }
      disconnect(): void {
        this.disconnected = true;
      }
    }
    vi.stubGlobal("MutationObserver", FakeObserver);

    const panel = new FakeElement("panel");
    const main = new FakeElement("main").append(panel);
    const body = new FakeElement("body").append(main);
    const restore = inertOutside(panel as unknown as Element, body as unknown as Element);
    const observer = observers[0]!;
    expect(observer.targets).toEqual([main, body]);

    const toast = new FakeElement("toast");
    body.append(toast);
    observer.callback([{ addedNodes: [toast, { nodeType: 3 }] }]);
    expect(toast.hasAttribute("inert")).toBe(true);

    restore();
    expect(observer.disconnected).toBe(true);
    expect(toast.hasAttribute("inert")).toBe(false);
  });
});
