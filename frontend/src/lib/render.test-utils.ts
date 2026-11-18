import type { Component } from "svelte";
import { render } from "svelte/server";

/**
 * Render a component on the server, like `render` from "svelte/server", and return its HTML
 * without Svelte's hydration comments, so tests can match markup with plain patterns.
 */
export function html<Props extends Record<string, any>>(component: Component<Props>, options: { props: Props }): string {
  return render(component, options).body.replace(/<!--[^>]*-->/g, "");
}
