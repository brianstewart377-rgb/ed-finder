import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { AutocompleteHit } from '@/types/api';
import { useDebounced } from '@/hooks/useDebounced';

/**
 * Debounced system-name autocomplete.
 *
 * Behaviour matches the vanilla app's `_autocompleteRef()` minus its
 * 6 layers of side effects:
 *   • Returns empty results when input < 2 chars.
 *   • Debounces 200 ms after typing stops.
 *   • Cancels stale in-flight requests so the displayed list always
 *     matches the latest query.
 */
export function useAutocomplete(query: string, limit = 8) {
  const debouncedQ = useDebounced(query, 200);
  const [hits, setHits]       = useState<AutocompleteHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr]         = useState<string | null>(null);

  useEffect(() => {
    if (debouncedQ.trim().length < 2) {
      setHits([]);
      setLoading(false);
      setErr(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setErr(null);
    api.autocomplete(debouncedQ.trim(), limit)
      .then((res) => {
        if (cancelled) return;
        setHits(res.results);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setErr(e instanceof Error ? e.message : String(e));
        setHits([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [debouncedQ, limit]);

  return { hits, loading, err };
}
