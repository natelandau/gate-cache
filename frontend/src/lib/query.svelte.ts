import { filters, freshness } from "./state.svelte";

export interface Query<T> {
  /** The latest result for the current inputs; kept while a live refresh is in flight. */
  readonly data: T | undefined;
  /** The latest failure, cleared by the next success. */
  readonly error: Error | undefined;
  /** True from an input change until its first result or failure arrives. */
  readonly loading: boolean;
}

interface QueryState<T> {
  data: T | undefined;
  error: Error | undefined;
  loading: boolean;
}

/**
 * The state transitions of a query, kept free of runes so they can be tested directly.
 *
 * `inputs` identifies what a load was for. A load for new inputs turns `loading` on; a failed
 * load for new inputs drops the old data, which no longer matches them. A reload for the same
 * inputs (new archive data) leaves the displayed data alone until its result arrives.
 */
export class QueryTracker<T> {
  #currentInputs: string | undefined;
  #dataInputs: string | undefined;

  constructor(readonly state: QueryState<T>) {}

  begin(inputs: string): void {
    if (inputs !== this.#currentInputs) {
      this.#currentInputs = inputs;
      this.state.loading = true;
    }
  }

  succeed(inputs: string, data: T): void {
    this.state.data = data;
    this.state.error = undefined;
    this.state.loading = false;
    this.#dataInputs = inputs;
  }

  fail(inputs: string, error: unknown): void {
    this.state.error = error instanceof Error ? error : new Error(String(error));
    this.state.loading = false;
    if (this.#dataInputs !== inputs) {
      this.state.data = undefined;
      this.#dataInputs = undefined;
    }
  }
}

/**
 * Load data for a page, reload it when the archive changes, and reload it when its inputs
 * change.
 *
 * Call it during component initialization. The inputs are the global filters plus whatever
 * `key` returns, such as the route parameters of a detail page. `load` runs inside an effect,
 * so reactive state it reads also triggers a reload, but only reads made before its first
 * `await` are tracked. Return every input from `key` (or read it before the first `await`).
 *
 * When the inputs change, `loading` turns true so the old data can be dimmed, and if that load
 * fails the old data is dropped. A reload caused only by new archive data keeps the current
 * data on screen, so live updates do not flicker.
 *
 * @param load Fetch the data; abort the request when `signal` aborts.
 * @param key Return the inputs beyond the global filters; any JSON-serializable value.
 */
export function createQuery<T>(
  load: (signal: AbortSignal) => Promise<T>,
  key: () => unknown = () => null,
): Query<T> {
  const state: QueryState<T> = $state({ data: undefined, error: undefined, loading: true });
  const tracker = new QueryTracker(state);

  $effect(() => {
    void freshness.changes;
    const inputs = JSON.stringify([filters.repo, filters.range, key()]);
    tracker.begin(inputs);
    const controller = new AbortController();
    load(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) tracker.succeed(inputs, data);
      },
      (error: unknown) => {
        if (!controller.signal.aborted) tracker.fail(inputs, error);
      },
    );
    return () => controller.abort();
  });

  return state;
}
