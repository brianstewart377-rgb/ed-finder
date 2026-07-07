import { useEffect, useState } from 'react';

/**
 * Debounce a value by `delay` ms.
 *
 * Used by the autocomplete input so we don't fire an API request on every
 * keystroke. The vanilla app does this with a manual `setTimeout` + clear
 * dance in 12 different places; here it's one hook.
 */
export function useDebounced<T>(value: T, delay = 250): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(t);
  }, [value, delay]);

  return debounced;
}
