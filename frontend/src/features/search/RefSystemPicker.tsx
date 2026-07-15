import { useEffect, useRef, useState } from 'react';
import { useAutocomplete } from './useAutocomplete';
import type { AutocompleteHit } from '@/types/api';
import { formatCoords, hasKnownCoords } from '@/lib/format';

/**
 * Reference-system picker — text input + autocomplete dropdown.
 *
 * Extracted from SearchForm.tsx so it can be reused by ClusterSearchForm
 * without duplicating the autocomplete wiring.
 */
export function RefSystemPicker({
  value, onPick, onPendingSelectionChange,
}: {
  value: string;
  onPick: (hit: AutocompleteHit) => void;
  onPendingSelectionChange?: (pending: boolean) => void;
}) {
  const [text, setText]   = useState(value);
  const [open, setOpen]   = useState(false);
  const blurT              = useRef<number | null>(null);
  const { hits, loading }  = useAutocomplete(text);
  const isPendingSelection =
    text.trim().length > 0 &&
    text.trim().toLocaleLowerCase() !== value.trim().toLocaleLowerCase();

  // Sync local text → parent value when parent resets/changes externally
  // (e.g. Reset button, or a future "Show on map" deep-link landing here).
  // Without this, the input keeps showing the user's last query after reset.
  useEffect(() => {
    setText(value);
  }, [value]);

  useEffect(() => {
    onPendingSelectionChange?.(isPendingSelection);
  }, [isPendingSelection, onPendingSelectionChange]);

  const selectHit = (hit: AutocompleteHit) => {
    if (!hasKnownCoords(hit, hit.id64)) return;
    if (blurT.current) window.clearTimeout(blurT.current);
    setText(hit.name);
    setOpen(false);
    onPick(hit);
  };

  // The form's `value` (parent state) only updates when a hit is picked.
  // Local `text` is the in-progress query. If the user wipes the input
  // we keep showing the parent's resolved name in the placeholder.
  return (
    <div className="relative">
      <input
        type="text"
        value={text}
        placeholder={value || 'Type a system name…'}
        onChange={(e) => { setText(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key !== 'Enter') return;
          if (!isPendingSelection) return;
          e.preventDefault();
          const firstKnownHit = hits.find((hit) => hasKnownCoords(hit, hit.id64));
          if (firstKnownHit) selectHit(firstKnownHit);
        }}
        onBlur={() => {
          // Defer hiding so onClick on a list item fires first.
          blurT.current = window.setTimeout(() => {
            setOpen(false);
            if (text.trim().length === 0) setText(value);
          }, 120);
        }}
        data-testid="ref-system-input"
        className="w-full px-3 py-2 rounded bg-bg4 border border-border font-mono text-sm text-text placeholder:text-text-dim/50 focus:border-orange-dk focus:outline-none"
      />
      {open && text.trim().length >= 2 && (
        <ul
          role="listbox"
          className="absolute z-10 mt-1 w-full max-h-60 overflow-auto rounded border border-border bg-bg3 shadow-lg font-mono text-xs"
        >
          {loading && (
            <li className="px-3 py-2 text-text-dim italic">Searching…</li>
          )}
          {!loading && hits.length === 0 && (
            <li className="px-3 py-2 text-text-dim italic">No matches</li>
          )}
          {hits.map((h) => {
            const hasCoords = hasKnownCoords(h, h.id64);
            return (
              <li
                key={h.id64}
                role="option"
                aria-selected={false}
                aria-disabled={!hasCoords}
                title={hasCoords ? undefined : 'Reference system coordinates are unknown'}
                data-testid={`ref-system-option-${h.id64}`}
                onMouseDown={(e) => e.preventDefault()}   // keep input focused
                onClick={() => { selectHit(h); }}
                className={[
                  'flex items-center gap-3 px-3 py-1.5 hover:bg-bg4',
                  hasCoords ? 'cursor-pointer' : 'cursor-not-allowed opacity-60',
                ].join(' ')}
              >
                <span className="text-orange flex-1 truncate">{h.name}</span>
                <span className="text-text-dim text-[10px] tabular-nums">
                  {hasCoords ? formatCoords(h, h.id64) : 'Unknown'}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
