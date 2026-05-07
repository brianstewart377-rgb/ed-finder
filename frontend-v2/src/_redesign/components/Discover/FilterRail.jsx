// FilterRail — section-panel layout matching the user's reference images.
// Body sliders arranged in 2-up grid; section panels with collapsible headers;
// chunky orange dual-range sliders.
import React from 'react';
import {
  Compass, RefreshCw, Sparkles, RotateCcw, Crosshair, Star,
  Globe2, Telescope, Zap, Sliders,
} from 'lucide-react';
import { Panel, PanelHeader, SectionPanel, HudButton, ToggleSwitch } from '../UI/Hud';

const PRESETS = [
  { id: 'farm',    label: 'Farm Colony',    hint: 'Agriculture · Terraformable · ELW' },
  { id: 'tourist', label: 'Tourism Hub',    hint: 'Tourism · Neutron · ELW' },
  { id: 'mining',  label: 'Mining Outpost', hint: 'Refinery · Extraction · Pristine' },
  { id: 'tech',    label: 'High Tech',      hint: 'High Tech · Industrial · Hi-pop' },
];

const BODY_SLIDERS = [
  { key: 'landable', label: 'Landable Bodies',    color: '#94a3b8', max: 60 },
  { key: 'walkable', label: 'Walkable Bodies',    color: '#38bdf8', max: 60 },
  { key: 'blackHole',label: 'Black Holes',        color: '#e2e8f0', max: 5  },
  { key: 'neutron',  label: 'Neutron Stars',      color: '#cbd5e1', max: 5  },
  { key: 'whiteDwarf',label:'White Dwarves',      color: '#dbeafe', max: 3  },
  { key: 'otherStar',label: 'Other Stars',        color: '#bef264', max: 30 },
  { key: 'elw',      label: 'Earth-like Worlds',  color: '#4ade80', max: 10 },
  { key: 'ww',       label: 'Water Worlds',       color: '#60a5fa', max: 20 },
  { key: 'ammonia',  label: 'Ammonia Worlds',     color: '#fb923c', max: 10 },
  { key: 'gasGiant', label: 'Gas Giants',         color: '#fbbf24', max: 30 },
  { key: 'hmc',      label: 'High Metal Content', color: '#a78bfa', max: 30 },
  { key: 'metalRich',label: 'Metal Rich Bodies',  color: '#f87171', max: 10 },
  { key: 'rockyIce', label: 'Rocky Ice Worlds',   color: '#7dd3fc', max: 25 },
  { key: 'rocky',    label: 'Rocky Bodies',       color: '#94a3b8', max: 50 },
  { key: 'icy',      label: 'Icy Bodies',         color: '#e0e7ff', max: 60 },
  { key: 'rings',    label: 'Rings',              color: '#bef264', max: 30 },
  { key: 'geo',      label: 'Bodies w/ Geologicals', color: '#d97706', max: 30 },
  { key: 'bio',      label: 'Bodies w/ Organics',  color: '#22c55e', max: 25 },
];

const ECONOMIES = ['Any', 'Agriculture', 'Refinery', 'Industrial', 'High Tech', 'Military', 'Tourism', 'Extraction'];

export function FilterRail({
  preset, onPreset,
  refSystem,
  distance, onDistance,
  resultsPerPage, onResultsPerPage,
  minRating, onMinRating,
  bodySliders, onBodySlider,
  economy, onEconomy,
  galaxyWide, onGalaxyWide,
  sortBy, onSortBy,
  toggles, onToggle,
  onSearch, onReset,
  loading,
}) {
  return (
    <Panel className="h-full overflow-hidden flex flex-col">
      <PanelHeader
        icon={<Compass size={14} strokeWidth={1.6} />}
        title="FINDER · FILTERS"
        sub="186M systems · live EDDN deltas"
        right={
          <div className="flex items-center gap-1.5">
            <HudButton size="sm" icon={RotateCcw} onClick={onReset}>RESET</HudButton>
            <HudButton size="sm" icon={RefreshCw} onClick={onSearch} active>
              {loading ? 'SCAN…' : 'SCAN'}
            </HudButton>
          </div>
        }
      />

      <div className="flex-1 overflow-y-auto p-3.5 space-y-3.5">
        {/* ── Reference system ── */}
        <SectionPanel
          icon={<Crosshair size={13} strokeWidth={1.8} />}
          title="REFERENCE SYSTEM"
        >
          <div className="space-y-3">
            <div className="readout px-3 py-2.5 flex items-center justify-between">
              <span className="font-display text-[12px] tracking-[0.1em] text-[var(--ed-orange-lt)]">
                {refSystem.name}
              </span>
              <span className="font-mono text-[10px] text-[var(--steel-400)] tabular-nums">
                {refSystem.x}, {refSystem.y}, {refSystem.z}
              </span>
            </div>
            <label className="flex items-center justify-between cursor-pointer group">
              <span className="font-display text-[10px] tracking-[0.16em] text-[var(--steel-300)]">
                GALAXY-WIDE SEARCH
              </span>
              <ToggleSwitch checked={galaxyWide} onChange={onGalaxyWide} />
            </label>
          </div>
        </SectionPanel>

        {/* ── Search radius (single sliders) ── */}
        <SectionPanel
          icon={<Telescope size={13} strokeWidth={1.8} />}
          title="SEARCH RADIUS"
        >
          <div className="space-y-3">
            <SingleSlider
              label="MAX DISTANCE (LY)"
              min={0} max={1000} step={1}
              value={distance.max}
              onChange={(v) => onDistance({ ...distance, max: Math.max(v, distance.min) })}
            />
            <SingleSlider
              label="MIN DISTANCE (LY)"
              min={0} max={1000} step={1}
              value={distance.min}
              onChange={(v) => onDistance({ ...distance, min: Math.min(v, distance.max) })}
            />
            <SingleSlider
              label="RESULTS PER PAGE"
              min={10} max={200} step={10}
              value={resultsPerPage}
              onChange={onResultsPerPage}
            />
            <button className="flex items-center gap-2 text-[10px] font-mono text-[var(--steel-400)] hover:text-[var(--ed-orange-lt)]">
              <Zap size={10} strokeWidth={2} />
              Jump Range Calculator
            </button>
          </div>
        </SectionPanel>

        {/* ── Quick presets ── */}
        <SectionPanel
          icon={<Sparkles size={13} strokeWidth={1.8} />}
          title="QUICK PRESETS"
        >
          <div className="grid grid-cols-2 gap-2">
            {PRESETS.map((p) => (
              <button
                key={p.id}
                onClick={() => onPreset(p.id)}
                className={[
                  'text-left px-3 py-2.5 rounded-[10px] border transition-all',
                  preset === p.id
                    ? 'border-[hsla(22,100%,50%,0.55)] bg-[hsla(22,100%,50%,0.12)] shadow-[0_0_14px_hsla(22,100%,50%,0.2)]'
                    : 'border-[hsla(232,22%,55%,0.28)] bg-[hsla(232,18%,18%,0.45)] hover:border-[hsla(232,30%,70%,0.4)] hover:bg-[hsla(232,18%,24%,0.5)]',
                ].join(' ')}
              >
                <div className={[
                  'font-display text-[10px] tracking-[0.1em] mb-0.5',
                  preset === p.id ? 'text-[var(--ed-orange-lt)] text-glow-orange' : 'text-[var(--steel-200)]',
                ].join(' ')}>
                  {p.label}
                </div>
                <div className="font-mono text-[9px] text-[var(--steel-400)] leading-tight">
                  {p.hint}
                </div>
              </button>
            ))}
          </div>
        </SectionPanel>

        {/* ── Economy / rating / sort ── */}
        <SectionPanel
          icon={<Star size={13} strokeWidth={1.8} />}
          title="ECONOMY · RATING"
        >
          <div className="grid grid-cols-2 gap-3">
            <SelectRow label="Primary economy" value={economy} onChange={onEconomy} options={ECONOMIES} />
            <SelectRow label="Sort by" value={sortBy} onChange={onSortBy} options={['Rating ↓', 'Distance ↑', 'Population ↓']} />
            <div className="col-span-2">
              <SingleSlider label={`MIN RATING · ${minRating}`} min={0} max={100} step={1} value={minRating} onChange={onMinRating} />
            </div>
          </div>
        </SectionPanel>

        {/* ── BODY TYPE FILTERS — 2-up grid of dual-range sliders ── */}
        <SectionPanel
          icon={<Globe2 size={13} strokeWidth={1.8} />}
          title="BODY TYPE FILTERS"
        >
          <div className="grid grid-cols-2 gap-x-5 gap-y-3.5">
            {BODY_SLIDERS.map((b) => {
              const v = bodySliders[b.key] || { min: 0, max: b.max };
              return (
                <DualSlider
                  key={b.key}
                  label={b.label}
                  color={b.color}
                  min={0} max={b.max}
                  value={v}
                  onChange={(nv) => onBodySlider(b.key, nv)}
                />
              );
            })}
          </div>
        </SectionPanel>

        {/* ── FEATURE FILTERS — toggle list ── */}
        <SectionPanel
          icon={<Sliders size={13} strokeWidth={1.8} />}
          title="FEATURE FILTERS"
        >
          <div className="-my-1.5">
            <ToggleRow label="Uncolonised Only"        checked={toggles.hideCol}   onChange={(c) => onToggle('hideCol', c)} />
            <ToggleRow label="Has Biological Signals"  checked={toggles.bio}       onChange={(c) => onToggle('bio', c)} />
            <ToggleRow label="Has Geological Signals"  checked={toggles.geo}       onChange={(c) => onToggle('geo', c)} />
            <ToggleRow label="Has Rings"               checked={toggles.rings}     onChange={(c) => onToggle('rings', c)} />
            <ToggleRow label="Has Terraformable Bodies"checked={toggles.terra}     onChange={(c) => onToggle('terra', c)} />
            <ToggleRow label="Has Volcanism"           checked={toggles.volcanism} onChange={(c) => onToggle('volcanism', c)} />
            <ToggleRow label="Not Tidally Locked"      checked={toggles.notTidal}  onChange={(c) => onToggle('notTidal', c)} />
            <ToggleRow label="Population = 0 Only"     checked={toggles.popZero}   onChange={(c) => onToggle('popZero', c)} />
            <ToggleRow label="Exclude Black Holes"     checked={toggles.noBH}      onChange={(c) => onToggle('noBH', c)} />
          </div>
        </SectionPanel>
      </div>
    </Panel>
  );
}

// ── Subcomponents ────────────────────────────────────────────

function SingleSlider({ label, min, max, step = 1, value, onChange }) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <label className="font-display text-[10px] tracking-[0.16em] text-[var(--steel-300)]">{label}</label>
        <span className="font-mono text-[12px] text-[var(--ed-orange-lt)] text-glow-orange tabular-nums">{value}</span>
      </div>
      <input
        type="range"
        className="slider-single"
        min={min} max={max} step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ '--val': `${pct}%` }}
      />
    </div>
  );
}

function DualSlider({ label, color, min, max, value, onChange }) {
  const pctMin = ((value.min - min) / (max - min)) * 100;
  const pctMax = ((value.max - min) / (max - min)) * 100;
  const displayMax = value.max === max ? `${max}` : value.max;
  return (
    <div className="space-y-1.5">
      <div className="flex items-start gap-2">
        <span
          className="w-2 h-2 rounded-full flex-shrink-0 mt-1.5"
          style={{ background: color, boxShadow: `0 0 8px ${color}99` }}
        />
        <span className="font-display text-[10px] tracking-[0.08em] text-[var(--steel-200)] leading-tight flex-1">
          {label}
        </span>
        <span className="font-mono text-[10px] text-[var(--ed-orange-lt)] tabular-nums whitespace-nowrap mt-0.5">
          {value.min} — {displayMax}
        </span>
      </div>
      <div className="dual-track">
        <div className="track-bg" />
        <div
          className="track-fill"
          style={{ left: `${pctMin}%`, right: `${100 - pctMax}%` }}
        />
        <input
          type="range" min={min} max={max} value={value.min}
          onChange={(e) => {
            const v = Number(e.target.value);
            onChange({ ...value, min: Math.min(v, value.max) });
          }}
          aria-label={`${label} minimum`}
        />
        <input
          type="range" min={min} max={max} value={value.max}
          onChange={(e) => {
            const v = Number(e.target.value);
            onChange({ ...value, max: Math.max(v, value.min) });
          }}
          aria-label={`${label} maximum`}
        />
      </div>
    </div>
  );
}

function SelectRow({ label, value, onChange, options }) {
  return (
    <div className="space-y-1">
      <label className="font-display text-[10px] tracking-[0.14em] text-[var(--steel-300)]">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-[hsla(232,30%,8%,0.85)] border border-[hsla(232,22%,50%,0.4)] rounded-[8px] px-2.5 py-1.5 font-mono text-[11px] text-[var(--steel-100)] hover:border-[hsla(232,30%,70%,0.5)] focus:border-[var(--ed-orange-dk)] outline-none cursor-pointer"
      >
        {options.map((o) => <option key={o} value={o} className="bg-[hsl(232,18%,14%)]">{o}</option>)}
      </select>
    </div>
  );
}

function ToggleRow({ label, checked, onChange }) {
  return (
    <label className="flex items-center justify-between py-2 cursor-pointer group border-b border-[hsla(232,22%,55%,0.12)] last:border-b-0">
      <span className="font-display text-[10px] tracking-[0.12em] text-[var(--steel-200)] group-hover:text-[var(--steel-100)]">
        {label}
      </span>
      <ToggleSwitch checked={checked} onChange={onChange} />
    </label>
  );
}
