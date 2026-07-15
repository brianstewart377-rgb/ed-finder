import { useState } from 'react';
import { Plus, X, Search, RotateCcw } from 'lucide-react';
import { RefSystemPicker } from '@/features/search/RefSystemPicker';
import { hasKnownCoords } from '@/lib/format';
import { economyColor } from '@/features/colony-planner/economyVisuals';
import type { AutocompleteHit } from '@/types/api';
import type { ClusterSearchFilters, SlotRequirement } from './useClusterSearch';
import { ARCHETYPE_PROFILES, ALL_ECONOMIES } from './useClusterSearch';

export interface ClusterSearchFormProps {
  filters:            ClusterSearchFilters;
  onChange:           (patch: Partial<ClusterSearchFilters>) => void;
  onAddSlot:          () => void;
  onRemoveSlot:       (index: number) => void;
  onUpdateSlot:       (index: number, patch: Partial<SlotRequirement>) => void;
  onSubmit:           () => void;
  onReset:            () => void;
  loading?:           boolean;
}

export function ClusterSearchForm({
  filters, onChange, onAddSlot, onRemoveSlot,
  onUpdateSlot, onSubmit, onReset, loading,
}: ClusterSearchFormProps) {
  const [referencePending, setReferencePending] = useState(false);

  const canAdd = filters.slots.length < 5;

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

      {/* Colony Worlds (slots) */}
      <fieldset className="space-y-2.5">
        <legend className="px-1 font-mono text-[11px] tracking-[0.18em] text-orange uppercase">
          Colony Worlds
        </legend>
        <div className="premium-subpanel space-y-3 p-3">
          {filters.slots.map((slot, i) => (
            <SlotRow
              key={i}
              slot={slot}
              index={i}
              onRemove={() => onRemoveSlot(i)}
              onUpdate={(patch) => onUpdateSlot(i, patch)}
            />
          ))}

          <button
            type="button"
            onClick={onAddSlot}
            disabled={!canAdd}
            className={[
              'w-full py-2 rounded border-dashed border font-mono text-[10px] uppercase tracking-wide transition-colors',
              canAdd
                ? 'border-border text-cyan hover:border-cyan/50 hover:text-white cursor-pointer'
                : 'border-border/40 text-text-dim/40 cursor-not-allowed',
            ].join(' ')}
          >
            <Plus size={12} className="inline mr-1" />
            Add World
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
          disabled={loading || referencePending || filters.slots.length === 0}
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

// ── Slot row sub-component ──────────────────────────────────────────────

function SlotRow({
  slot, index, onRemove, onUpdate,
}: {
  slot:    SlotRequirement;
  index:   number;
  onRemove: () => void;
  onUpdate: (patch: Partial<SlotRequirement>) => void;
}) {
  const isCustom = slot.archetype_key === '__custom__';
  const resolvedEcons = isCustom
    ? slot.economies
    : (ARCHETYPE_PROFILES.find(p => p.archetype_key === slot.archetype_key)?.economies ?? slot.economies);

  const handleArchetypeChange = (value: string) => {
    if (value === '__custom__') {
      onUpdate({ archetype_key: '__custom__', economies: ['Agriculture'], label: 'Agriculture' });
    } else {
      const profile = ARCHETYPE_PROFILES.find(p => p.archetype_key === value);
      if (profile) {
        onUpdate({
          archetype_key: value,
          label: profile.label,
          economies: [],
        });
      }
    }
  };

  const handleCustomEconomy = (slotIndex: number, economy: string) => {
    const current = [...slot.economies];
    current[slotIndex] = economy;
    const label = current.join(' + ');
    onUpdate({ economies: current, label });
  };

  const handleAddSecondEconomy = () => {
    const used = new Set(slot.economies);
    const next = ALL_ECONOMIES.find(e => !used.has(e)) ?? 'Industrial';
    const current = [...slot.economies, next];
    const label = current.join(' + ');
    onUpdate({ economies: current, label });
  };

  return (
    <div className="rounded border border-border/70 bg-bg3/50 p-3 space-y-2.5">
      {/* Archetype / custom dropdown */}
      <div className="flex items-center gap-2">
        <select
          value={slot.archetype_key ?? '__custom__'}
          onChange={(e) => handleArchetypeChange(e.target.value)}
          className="flex-1 px-2 py-1.5 rounded bg-bg3 border border-border font-mono text-xs text-text"
        >
          {ARCHETYPE_PROFILES.map((p) => (
            <option key={p.archetype_key} value={p.archetype_key}>{p.label}</option>
          ))}
          <option value="__custom__">Custom…</option>
        </select>

        <button
          type="button"
          onClick={onRemove}
          className="p-1 text-text-dim hover:text-red transition-colors shrink-0"
          title="Remove world"
        >
          <X size={14} />
        </button>
      </div>

      {/* Resolved economies */}
      {isCustom ? (
        <div className="flex items-center gap-2 flex-wrap">
          {slot.economies.map((econ, ci) => (
            <div key={ci} className="flex items-center gap-1">
              <select
                value={econ}
                onChange={(e) => handleCustomEconomy(ci, e.target.value)}
                className="px-2 py-1 rounded bg-bg3 border border-border font-mono text-xs text-text"
              >
                {ALL_ECONOMIES.map((e) => (
                  <option key={e} value={e}>{e}</option>
                ))}
              </select>
              {ci > 0 && (
                <button
                  type="button"
                  onClick={() => {
                    const current = slot.economies.filter((_, ei) => ei !== ci);
                    const label = current.join(' + ');
                    onUpdate({ economies: current, label });
                  }}
                  className="p-0.5 text-text-dim hover:text-red transition-colors"
                  title="Remove economy"
                >
                  <X size={12} />
                </button>
              )}
            </div>
          ))}
          {slot.economies.length < 2 && (
            <button
              type="button"
              onClick={handleAddSecondEconomy}
              className="px-2 py-1 rounded border-dashed border border-border/60 font-mono text-[10px] text-cyan hover:text-white hover:border-cyan/50 transition-colors"
            >
              <Plus size={10} className="inline mr-0.5" />
              Add economy
            </button>
          )}
        </div>
      ) : (
        <div className="flex items-center gap-1.5 flex-wrap">
          {resolvedEcons.map((econ) => (
            <span
              key={econ}
              className="px-2 py-0.5 rounded-full font-mono text-[10px] border"
              style={{
                color: economyColor(econ),
                borderColor: economyColor(econ),
                backgroundColor: `${economyColor(econ)}18`,
              }}
            >
              {econ}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
