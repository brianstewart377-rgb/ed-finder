import { useEffect, useId, useRef, useState, type ChangeEvent } from 'react';
import {
  BODY_FILTER_KEYS, BODY_FILTER_LABELS, BODY_SLIDERS, PRESETS, applyPreset,
  type FilterTri, type SearchFilters, type BodySliderKey, type BodyRange, type PresetId,
} from './useSearch';
import { useAutocomplete } from './useAutocomplete';
import type { AutocompleteHit } from '@/types/api';
import { DualSlider } from '@/components/DualSlider';
import { ChevronDown, Sparkles } from 'lucide-react';
import { formatCoords, hasKnownCoords } from '@/lib/format';

/**
 * Search form. Stateless w.r.t. results — emits filter changes through
 * `onChange` and triggers searches via `onSubmit` / `onReset`. The parent
 * owns the results list (see useSearch hook).
 *
 * UX choices vs the vanilla app:
 *   • Sliders + numeric input side-by-side so power users can type a value.
 *   • Reference system picker lives at the top — that's what users adjust
 *     most often.
 *   • Single inline form rather than the vanilla's collapsible panels —
 *     for the POC we prioritise discoverability over screen real-estate.
 */
export interface SearchFormProps {
  filters:   SearchFilters;
  onChange:  (patch: Partial<SearchFilters>) => void;
  onSubmit:  () => void;
  onReset:   () => void;
  loading?:  boolean;
}

export function SearchForm({ filters, onChange, onSubmit, onReset, loading }: SearchFormProps) {
  return (
    <form
      onSubmit={(e) => { e.preventDefault(); onSubmit(); }}
      className="space-y-5 p-5"
      data-testid="search-form"
    >
      <Section title="Reference System">
        <RefSystemPicker
          value={filters.refName}
          onPick={(hit) => {
            if (!hasKnownCoords(hit, hit.id64)) return;
            onChange({
              refName:   hit.name,
              refCoords: { x: hit.x, y: hit.y, z: hit.z },
            });
          }}
        />
        <p className="font-mono text-[10px] text-text-dim">
          {filters.refCoords.x.toFixed(2)}, {filters.refCoords.y.toFixed(2)}, {filters.refCoords.z.toFixed(2)}
        </p>
      </Section>

      <QuickPresets
        onPick={(id) => onChange(applyPreset(filters, id) as Partial<SearchFilters>)}
      />

      <div className="mb-2 text-right text-xs text-dim">
        <a
          href="/v2/development.html"
          target="_blank"
          rel="noopener"
          data-testid="development-help-link"
          className="text-orange hover:underline"
        >
          Development model notes &rarr;
        </a>
      </div>
      <Section title="Search Radius">
        <RangeRow
          label="Min distance (LY)"
          min={0} max={2000}
          value={filters.minDistance}
          onChange={(v) => onChange({ minDistance: Math.min(v, filters.maxDistance) })}
        />
        <RangeRow
          label="Max distance (LY)"
          min={0} max={2000}
          value={filters.maxDistance}
          onChange={(v) => onChange({ maxDistance: Math.max(v, filters.minDistance) })}
        />
        <RangeRow
          label="Results per page"
          min={5} max={500} step={5}
          value={filters.size}
          onChange={(v) => onChange({ size: v })}
        />
        <CheckboxRow
          label="Galaxy-wide (ignore distance)"
          checked={filters.galaxyWide}
          onChange={(c) => onChange({ galaxyWide: c })}
        />
      </Section>

      <Section title="Filters">
        <SelectRow
          label="Population"
          value={filters.populated}
          onChange={(v) => onChange({ populated: v as SearchFilters['populated'] })}
          options={[
            { value: 'any',         label: 'Any' },
            { value: 'populated',   label: 'Populated only' },
            { value: 'uninhabited', label: 'Uninhabited only' },
          ]}
        />
        <SelectRow
          label="Primary economy"
          value={filters.economy}
          onChange={(v) => onChange({ economy: v })}
          options={ECONOMY_OPTIONS}
        />
        <RangeRow
          label="Min development score"
          min={0} max={100}
          value={filters.minDevelopmentScore}
          onChange={(v) => onChange({ minDevelopmentScore: v })}
        />
      </Section>

      <Section title="Body types — quick filter">
        <p className="font-mono text-[10px] text-text-dim leading-relaxed">
          Click once to require, twice to exclude, again to clear.
        </p>
        <div className="flex flex-wrap gap-1.5">
          {BODY_FILTER_KEYS.map((k) => (
            <BodyFilterPill
              key={k}
              label={BODY_FILTER_LABELS[k]}
              state={filters.bodyFilters[k]}
              onCycle={() => onChange({
                bodyFilters: { ...filters.bodyFilters, [k]: cycleTri(filters.bodyFilters[k]) },
              })}
              testid={`body-filter-${k}`}
            />
          ))}
        </div>
      </Section>

      <Section title="Body type filters">
        <p className="font-mono text-[10px] text-text-dim leading-relaxed mb-1">
          Per-body min/max counts. Drag both thumbs to narrow the range.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-5 gap-y-3 pt-1">
          {BODY_SLIDERS.map((b) => {
            const r = filters.bodyRanges[b.key as BodySliderKey] ?? { min: 0, max: b.max };
            return (
              <DualSlider
                key={b.key}
                label={b.label}
                color={b.color}
                min={0}
                max={b.max}
                value={r}
                onChange={(nv: BodyRange) => onChange({
                  bodyRanges: { ...filters.bodyRanges, [b.key]: nv },
                })}
                testid={`body-slider-${b.key}`}
              />
            );
          })}
        </div>
      </Section>

      <Section title="Sort">
        <SelectRow
          label="Order by"
          value={filters.sortBy}
          onChange={(v) => onChange({ sortBy: v as SearchFilters['sortBy'] })}
          options={[
            { value: 'development', label: 'Development first' },
            { value: 'distance',    label: 'Distance nearest' },
            { value: 'population',  label: 'Population highest' },
          ]}
        />
      </Section>

      <div className="flex gap-2 pt-1">
        <button
          type="submit"
          disabled={loading}
          data-testid="search-submit"
          className="btn-primary flex-1"
        >
          {loading ? 'SCANNING…' : '🔍 SEARCH'}
        </button>
        <button
          type="button"
          onClick={onReset}
          data-testid="search-reset"
          className="btn-metal"
        >
          ✕ Reset
        </button>
      </div>
    </form>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Internal building blocks. Inline because they're trivial and only used
// here. Promote to `components/` when a second feature reuses one.
// ─────────────────────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <fieldset className="space-y-2">
      <legend className="font-mono text-[11px] tracking-wider text-orange uppercase">
        {title}
      </legend>
      <div className="space-y-2">{children}</div>
    </fieldset>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Quick presets — collapsed by default. Pick one to overwrite filters with
// an opinionated starting point (e.g. "Tourism Hub", "Mining / Refinery").
// ─────────────────────────────────────────────────────────────────────────

function QuickPresets({ onPick }: { onPick: (id: PresetId) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <fieldset className="space-y-2" data-testid="quick-presets">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        data-testid="quick-presets-toggle"
        className={[
          'w-full flex items-center justify-between gap-2 px-3 py-2 rounded-chunk-sm',
          'border transition-all duration-200 cursor-pointer',
          open
            ? 'border-orange/55 bg-orange/10 shadow-brand-glow'
            : 'border-border bg-bg3/40 hover:border-orange/45 hover:bg-orange/5',
        ].join(' ')}
      >
        <span className="flex items-center gap-2 font-mono text-[11px] tracking-[0.14em] uppercase">
          <Sparkles size={13} className="text-orange-lt" />
          <span className={open ? 'text-orange-lt' : 'text-orange'}>Quick Presets</span>
          <span className="text-silver-dk text-[10px] font-normal normal-case tracking-normal">
            {open ? '— pick a profile' : '— click to expand'}
          </span>
        </span>
        <ChevronDown
          size={14}
          className={['text-silver-dk transition-transform duration-200', open && 'rotate-180 text-orange-lt'].filter(Boolean).join(' ')}
        />
      </button>

      {open && (
        <div className="grid grid-cols-2 gap-2 pt-1 animate-fade-up">
          {PRESETS.map((p) => (
            <button
              key={p.id}
              type="button"
              data-testid={`preset-${p.id}`}
              onClick={() => onPick(p.id)}
              className="text-left px-3 py-2.5 rounded-chunk-sm border border-border bg-bg3/40 hover:border-orange/55 hover:bg-orange/10 hover:shadow-brand-glow transition-all duration-200 group"
            >
              <div className="flex items-center gap-1.5 font-mono text-[11px] tracking-[0.08em] text-silver group-hover:text-orange-lt mb-0.5">
                <span className="text-base leading-none">{p.icon}</span>
                <span className="truncate">{p.label}</span>
              </div>
              <div className="font-mono text-[9px] text-silver-dk leading-snug line-clamp-2">
                {p.hint}
              </div>
            </button>
          ))}
        </div>
      )}
    </fieldset>
  );
}

function RangeRow({
  label, min, max, step = 1, value, onChange,
}: {
  label: string; min: number; max: number; step?: number;
  value: number; onChange: (v: number) => void;
}) {
  const id = useId();
  return (
    <div className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1">
      <label htmlFor={id} className="font-mono text-[11px] text-text-dim col-span-2">
        {label}
      </label>
      <input
        id={id}
        type="range"
        min={min} max={max} step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="accent-orange"
      />
      <input
        type="number"
        min={min} max={max} step={step}
        value={value}
        onChange={(e) => {
          const v = Number(e.target.value);
          if (!Number.isNaN(v)) onChange(Math.max(min, Math.min(max, v)));
        }}
        className="w-20 px-2 py-0.5 rounded bg-bg4 border border-border font-mono text-xs text-orange text-right tabular-nums no-spinner"
      />
    </div>
  );
}

function SelectRow<T extends string>({
  label, value, onChange, options,
}: {
  label: string; value: T; onChange: (v: T) => void;
  options: { value: T; label: string }[];
}) {
  const id = useId();
  return (
    <div className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1">
      <label htmlFor={id} className="font-mono text-[11px] text-text-dim col-span-2">
        {label}
      </label>
      <span />
      <select
        id={id}
        value={value}
        onChange={(e: ChangeEvent<HTMLSelectElement>) => onChange(e.target.value as T)}
        className="w-44 px-2 py-1 rounded bg-bg4 border border-border font-mono text-xs text-text"
      >
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}

function CheckboxRow({
  label, checked, onChange,
}: { label: string; checked: boolean; onChange: (c: boolean) => void }) {
  const id = useId();
  return (
    <label htmlFor={id} className="flex items-center gap-2 font-mono text-[11px] text-text-dim cursor-pointer">
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="accent-orange"
      />
      {label}
    </label>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Reference-system picker — text input + autocomplete dropdown.
// ─────────────────────────────────────────────────────────────────────────

function RefSystemPicker({
  value, onPick,
}: { value: string; onPick: (hit: AutocompleteHit) => void }) {
  const [text, setText]   = useState(value);
  const [open, setOpen]   = useState(false);
  const blurT              = useRef<number | null>(null);
  const { hits, loading }  = useAutocomplete(text);

  // Sync local text → parent value when parent resets/changes externally
  // (e.g. Reset button, or a future "Show on map" deep-link landing here).
  // Without this, the input keeps showing the user's last query after reset.
  useEffect(() => {
    setText(value);
  }, [value]);

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
        onBlur={() => {
          // Defer hiding so onClick on a list item fires first.
          blurT.current = window.setTimeout(() => setOpen(false), 120);
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
                onClick={() => {
                  if (!hasCoords) return;
                  if (blurT.current) window.clearTimeout(blurT.current);
                  setText(h.name);
                  setOpen(false);
                  onPick(h);
                }}
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

const ECONOMY_OPTIONS: { value: string; label: string }[] = [
  { value: 'any',         label: 'Any' },
  { value: 'Agriculture', label: 'Agriculture' },
  { value: 'Refinery',    label: 'Refinery' },
  { value: 'Industrial',  label: 'Industrial' },
  // Wire value MUST match the PostgreSQL `economy_type` enum literal
  // (`HighTech`, no space) — see sql/001_schema.sql + apps/api/src/
  // search_economies.py::ECONOMY_ENUM_LITERALS. Label is human-friendly.
  { value: 'HighTech',    label: 'High Tech' },
  { value: 'Military',    label: 'Military' },
  { value: 'Tourism',     label: 'Tourism' },
  { value: 'Extraction',  label: 'Extraction' },
];

// ─────────────────────────────────────────────────────────────────────────
// Body-type filter pill — tri-state button.
// ─────────────────────────────────────────────────────────────────────────

function cycleTri(s: FilterTri): FilterTri {
  if (s === 'off')      return 'required';
  if (s === 'required') return 'excluded';
  return 'off';
}

function BodyFilterPill({
  label, state, onCycle, testid,
}: {
  label:   string;
  state:   FilterTri;
  onCycle: () => void;
  testid:  string;
}) {
  const cls =
    state === 'required'
      ? 'bg-green/20 text-green border-green/50'
      : state === 'excluded'
      ? 'bg-red/20 text-red border-red/50 line-through'
      : 'bg-bg4 text-text-dim border-border hover:text-text';

  const symbol =
    state === 'required' ? '✓ ' :
    state === 'excluded' ? '✕ ' : '';

  return (
    <button
      type="button"
      onClick={onCycle}
      data-testid={testid}
      data-state={state}
      title={`${label}: ${state}`}
      className={[
        'px-2 py-1 rounded-full border font-mono text-[11px] transition-colors',
        cls,
      ].join(' ')}
    >
      {symbol}{label}
    </button>
  );
}
