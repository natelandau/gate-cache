/** Return whether `value` is an own key of `record`, narrowing it to the record's key type. */
export function hasKey<K extends string>(record: Record<K, unknown>, value: string | null): value is K {
  return value !== null && Object.hasOwn(record, value);
}
