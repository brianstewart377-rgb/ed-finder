import { useState } from 'react';
import { Plus, X, Search, RotateCcw } from 'lucide-react';
import { RefSystemPicker } from '@/features/search/RefSystemPicker';
import { hasKnownCoords } from '@/lib/format';
import type { AutocompleteHit } from '@/types/api';
import type { ClusterSearchFilters } from './useClusterSearch';

const ECONOMIES = ['Agriculture', 'Refinery', 'Industrial', 'HighTech', 'Military', 'Tourism'] as const;

export interface ClusterSearchFormProps {
  filters:            ClusterSearchFilters;
  onChange:           (patch: Partial<ClusterSearchFilters>) => void;
  onAddRequirement:   () => void;
  onRemoveRequirement: (index: number) => void;
  onUpdateRequirement: (index: number, patch: { economy?: string; min_count?: number }) => void;
  onSubmit:           () => void;
  onReset:            () => void;
  loading?:           boolean;
}

export function ClusterSearchForm({
  filters, onChange, onAddRequirement, onRemoveRequirement,
  onUpdateRequirement, onSubmit, onReset, loading,
}: ClusterSearchFormProps) {
  const [referencePending, setReferencePending] = useState(false);

  const canAdd = filters.requirements.length < 6;

  return (
    <div className="space-y-6 p-5" data-testid="cluster-search-form">
      {/* Reference System */}
      <fieldset className="space-y-2.5">
        <legend className="px-1 font-mono text-[11px] tracking-[0.18em] text-orange uppercase">
          Reference System
        </legend>
        <div className="premium-subpanel space-y-3 p-3">
          <RefSystemPicker
            value={filters.refName}
            onPendingSelectionChange={setReferencePending}
            onPick={(hit: AutocompleteHit) => {
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
          >
            {referencePending
              ? 'Pick a system from autocomplete to update the active reference.'
              : `${filters.refName}: ${filters.refCoords.x.toFixed(2)}, ${filters.refCoords.y.toFixed(2)}, ${filters.refCoords.z.toFixed(2)}`}
          </p>
        </div>
      </fieldset>

      {/* Economy Requirements */}
      <fieldset className="space-y-2.5">
        <legend className="px-1 font-mono text-[11px] tracking-[0.18em] text-orange uppercase">
          Economy Requirements
        </legend>
        <div className="premium-subpanel space-y-2 p-3">
          {filters.requirements.map((req, i) => (
            <div key={i} className="flex items-center gap-2">
              <select
                value={req.economy}
                onChange={(e) => onUpdateRequirement(i, { economy: e.target.value })}
                className="w-36 px-2 py-1 rounded bg-bg3 border border-border font-mono text-xs text-text"
              >
                {ECONOMIES.map((e) => (
                  <option key={e} value={e}>{e}</option>
                ))}
              </select>
              <input
                type="number"
                min={1}
                value={req.min_count}
                onChange={(e) => {
                  const v = parseInt(e.target.value, 10);
                  if (!Number.isNaN(v) && v >= 1) onUpdateRequirement(i, { min_count: v });
                }}
                className="w-16 rounded bg-bg3 border border-border px-2 py-1 font-mono text-xs text-text text-right no-spinner"
              />
              <span className="font-mono text-[10px] text-text-dim">min</span>
              <button
                type="button"
                onClick={() => onRemoveRequirement(i)}
                className="ml-auto p-1 text-text-dim hover:text-red transition-colors"
                title="Remove requirement"
              >
                <X size={14} />
              </button>
            </div>
          ))}

          <button
            type="button"
            onClick={onAddRequirement}
            disabled={!canAdd}
            className={[
              'w-full py-2 rounded border-dashed border font-mono text-[10px] uppercase tracking-wide transition-colors',
              canAdd
                ? 'border-border text-cyan hover:border-cyan/50 hover:text-white cursor-pointer'
                : 'border-border/40 text-text-dim/40 cursor-not-allowed',
            ].join(' ')}
          >
            <Plus size={12} className="inline mr-1" />
            Add economy
          </button>
        </div>
      </fieldset>

      {/* Limit */}
      <fieldset className="space-y-2.5">
        <legend className="px-1 font-mono text-[11px] tracking-[0.18em] text-orange uppercase">
          Results
        </legend>
        <div className="premium-subpanel space-y-3 p-3">
          <div className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1.5">
            <label className="font-mono text-[11px] text-text-dim col-span-2">
              Max regions to return
            </label>
            <input
              type="range"
              min={5} max={200}
              value={filters.limit}
              onChange={(e) => onChange({ limit: Number(e.target.value) })}
              className="accent-orange"
            />
            <input
              type="number"
              min={5} max={200} step={5}
              value={filters.limit}
              onChange={(e) => {
                const v = Number(e.target.value);
                if (!Number.isNaN(v)) onChange({ limit: Math.max(5, Math.min(200, v)) });
              }}
              className="w-20 rounded border border-border bg-bg4/70 px-2 py-1 font-mono text-xs text-orange text-right tabular-nums no-spinner"
            />
          </div>
        </div>
      </fieldset>

      {/* Actions */}
      <div className="flex gap-2 pt-1">
        <button
          type="button"
          disabled={loading || referencePending || filters.requirements.length === 0}
          onClick={onSubmit}
          data-testid="cluster-search-submit"
          className="btn-primary flex-1"
        >
          {loading ? 'Scanning…' : referencePending ? 'Pick reference' : 'Search'}
        </button>
        <button
          type="button"
          onClick={onReset}
          data-testid="cluster-search-reset"
          className="btn-metal"
        >
          <RotateCcw size={14} className="inline mr-1" />
          Reset
        </button>
      </div>
    </div>
  );
}
