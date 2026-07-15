import { useId, useState, type ChangeEvent } from 'react';
import {
  BODY_FILTER_KEYS, BODY_FILTER_LABELS, BODY_SLIDERS, PRESETS, applyPreset,
  type FilterTri, type SearchFilters, type BodySliderKey, type BodyRange, type PresetId,
} from './useSearch';
import { DualSlider } from '@/components/DualSlider';
import { ChevronDown, Sparkles } from 'lucide-react';
import { RefSystemPicker } from './RefSystemPicker';
import { hasKnownCoords } from '@/lib/format';

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
  const [referencePending, setReferencePending] = useState(false);

  return (
    <form
      onSubmit={(e) => { e.preventDefault(); onSubmit(); }}
      className="space-y-6 p-5"
      data-testid="search-form"
    >
      <Section title="Reference System">
        <RefSystemPicker
          value={filters.refName}
          onPendingSelectionChange={setReferencePending}
          onPick={(hit) => {
            if (!hasKnownCoords(hit, hit.id64)) return;
            onChange({
              refName:   hit.name,
              refCoords: { x: hit.x, y: hit.y, z: hit.z },
            });
          }}
        />
        <p
          className={[
            'font-mono text-[10px]',
            referencePending ? 'text-orange-lt' : 'text-text-dim',
          ].join(' ')}
          data-testid="reference-system-status"
        >
          {referencePending
            ? 'Pick a system from autocomplete to update the active reference.'
            : `${filters.refName}: ${filters.refCoords.x.toFixed(2)}, ${filters.refCoords.y.toFixed(2)}, ${filters.refCoords.z.toFixed(2)}`}
        </p>
      </Section>

      <QuickPresets
        onPick={(id) => onChange(applyPreset(filters, id) as Partial<SearchFilters>)}
      />

      <div className="rounded border border-orange/20 bg-orange/6 px-3 py-2 font-mono text-[10px] leading-relaxed text-silver-dk">
        Development score is a Finder-side triage signal. Inspect and Colony Planner remain the authoritative places for evidence-backed planning decisions.
        <div className="mt-2">
          <a
            href="#search-tuning"
            className="inline-flex items-center rounded border border-cyan/30 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-cyan transition-colors hover:border-cyan/50 hover:text-white"
            data-testid="open-search-tuning-link"
          >
            Open Development Tuning
          </a>
        </div>
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
          label="Colony status"
          value={filters.populated}
          onChange={(v) => onChange({ populated: v as SearchFilters['populated'] })}
          options={[
            { value: 'any',         label: 'Any' },
            { value: 'populated',   label: 'Inhabited only' },
            { value: 'uninhabited', label: 'Non-colonised only' },
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
          disabled={loading || referencePending}
          data-testid="search-submit"
          className="btn-primary flex-1"
        >
          {loading ? 'Scanning…' : referencePending ? 'Pick reference' : 'Search'}
        </button>
        <button
          type="button"
          onClick={onReset}
          data-testid="search-reset"
          className="btn-metal"
        >
          Reset
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
    <fieldset className="space-y-2.5">
      <legend className="px-1 font-mono text-[11px] tracking-[0.18em] text-orange uppercase">
        {title}
      </legend>
      <div className="premium-subpanel space-y-3 p-3">{children}</div>
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
          'w-full flex items-center justify-between gap-2 px-3 py-2.5 rounded-chunk-sm',
          'border transition-all duration-200 cursor-pointer',
          open
            ? 'border-orange/55 bg-orange/10 shadow-brand-glow'
            : 'border-border bg-bg3/55 hover:border-orange/45 hover:bg-orange/5',
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
              className="premium-subpanel text-left px-3 py-2.5 transition-all duration-200 group hover:border-orange/55 hover:bg-orange/10 hover:shadow-brand-glow"
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
    <div className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1.5">
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
        className="w-20 rounded border border-border bg-bg4/70 px-2 py-1 font-mono text-xs text-orange text-right tabular-nums no-spinner"
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
