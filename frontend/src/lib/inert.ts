const ELEMENT_NODE = 1;

/**
 * Make everything under `root` inert except `element` and its ancestors, so focus and screen
 * readers stay inside a modal sheet. Siblings added while it holds, such as a toast, are made
 * inert too. Returns a function that undoes it; elements that were already inert stay inert.
 */
export function inertOutside(element: Element, root: Element = document.body): () => void {
  const changed: Element[] = [];
  const path = new Set<Element>();
  const parents: Element[] = [];
  const makeInert = (el: Element) => {
    if (!path.has(el) && !el.hasAttribute("inert")) {
      el.setAttribute("inert", "");
      changed.push(el);
    }
  };
  for (let node: Element | null = element; node && node !== root; node = node.parentElement) {
    path.add(node);
    const parent = node.parentElement;
    if (!parent) continue;
    parents.push(parent);
    for (const sibling of Array.from(parent.children)) makeInert(sibling);
  }

  const Observer = globalThis.MutationObserver;
  const observer = Observer
    ? new Observer((records) => {
        for (const record of records) {
          for (const added of Array.from(record.addedNodes)) {
            if (added.nodeType === ELEMENT_NODE) makeInert(added as Element);
          }
        }
      })
    : undefined;
  for (const parent of parents) observer?.observe(parent, { childList: true });

  return () => {
    observer?.disconnect();
    for (const el of changed) el.removeAttribute("inert");
  };
}
