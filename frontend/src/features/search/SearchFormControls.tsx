import { useId } from 'react';
import { Check, ChevronRight, X } from 'lucide-react';
import { PRESETS, type PresetId } from './useSearch';
import type { FilterSectionId } from './searchFormConfig';

export function FilterWorkspaceHeader({
  section,
  items,
  onClose,
}: {
  section: FilterSectionId;
  items: { id: FilterSectionId; label: string }[];
  onClose: () => void;
}) {
  const item = items.find((candidate) => candidate.id === section);
  return (
    <header className="finder-filter-workspace__header">
      <h2 id="finder-filter-workspace-title">{item?.label ?? section}</h2>
      <button type="button" onClick={onClose} aria-label="Close filter workspace">
        <X size={19} aria-hidden />
      </button>
    </header>
  );
}

export function WorkspaceSection({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="finder-workspace-section">
      <div className="finder-workspace-section__intro">
        {eyebrow ? <span>{eyebrow}</span> : null}
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
      {children}
    </div>
  );
}

export function QuickPresets({ onPick }: { onPick: (id: PresetId) => void }) {
  return (
    <div className="finder-preset-grid" data-testid="quick-presets">
      {PRESETS.map((preset, index) => (
        <button
          key={preset.id}
          type="button"
          data-testid={`preset-${preset.id}`}
          onClick={() => onPick(preset.id)}
          className="finder-preset"
        >
          <span className="finder-preset__number">{String(index + 1).padStart(2, '0')}</span>
          <span className="finder-preset__icon" aria-hidden>{preset.icon}</span>
          <strong>{preset.label}</strong>
          <small>{preset.hint}</small>
          <ChevronRight size={15} aria-hidden />
        </button>
      ))}
    </div>
  );
}

export function RangeRow({
  label,
  description,
  unit,
  min,
  max,
  step = 1,
  value,
  onChange,
}: {
  label: string;
  description?: string;
  unit?: string;
  min: number;
  max: number;
  step?: number;
  value: number;
  onChange: (value: number) => void;
}) {
  const id = useId();
  const descriptionId = description ? `${id}-description` : undefined;
  return (
    <div className="finder-range-control">
      <label htmlFor={id}>{label}</label>
      <div className="finder-range-control__value">
        <input
          type="number"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(event) => {
            const next = Number(event.target.value);
            if (!Number.isNaN(next)) onChange(Math.max(min, Math.min(max, next)));
          }}
          aria-label={`${label} value`}
          aria-describedby={descriptionId}
        />
        {unit && <span>{unit}</span>}
      </div>
      {description ? (
        <p id={descriptionId} className="finder-range-control__description">
          {description}
        </p>
      ) : null}
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        aria-describedby={descriptionId}
      />
      <div className="finder-range-control__limits" aria-hidden>
        <span>{min}</span>
        <span>{max}</span>
      </div>
    </div>
  );
}

export function CheckboxRow({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  const id = useId();
  return (
    <label htmlFor={id} className="finder-checkbox-control">
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span aria-hidden>{checked ? <Check size={15} /> : null}</span>
      <strong>{label}</strong>
    </label>
  );
}
