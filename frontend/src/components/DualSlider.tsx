import { useId, useRef, useEffect, useState } from 'react';

/**
 * Dual-range chunky orange slider (min + max thumb on a shared track).
 *
 * Implementation: two overlapping <input type="range"> elements stacked
 * absolutely. The track between the two thumbs is painted with a
 * background-image gradient computed from the current values.
 *
 * Why not a library? A single-purpose ~100-line component is cheaper to own
 * than a dependency for one screen, and it lets us match the brushed-metal
 * + ED-orange aesthetic exactly without override CSS battles.
 */
export interface DualSliderProps {
  label:    string;
  min:      number;
  max:      number;
  step?:    number;
  value:    { min: number; max: number };
  onChange: (next: { min: number; max: number }) => void;
  /** Accent dot drawn next to the label — usually the body-type colour. */
  color?:   string;
  testid?:  string;
}

export function DualSlider({
  label, min, max, step = 1, value, onChange, color, testid,
}: DualSliderProps) {
  const id = useId();
  // Local state lets the user drag smoothly without re-renders snapping back.
  const [lo, setLo] = useState(value.min);
  const [hi, setHi] = useState(value.max);

  // Keep local in sync if the parent resets us.
  const lastExt = useRef({ min: value.min, max: value.max });
  useEffect(() => {
    if (lastExt.current.min !== value.min || lastExt.current.max !== value.max) {
      lastExt.current = { min: value.min, max: value.max };
      setLo(value.min);
      setHi(value.max);
    }
  }, [value.min, value.max]);

  const span     = max - min || 1;
  const loPct    = ((lo - min) / span) * 100;
  const hiPct    = ((hi - min) / span) * 100;

  const commit = (newLo: number, newHi: number) => {
    lastExt.current = { min: newLo, max: newHi };
    onChange({ min: newLo, max: newHi });
  };

  return (
    <div className="space-y-1" data-testid={testid}>
      <div className="flex items-start justify-between gap-2">
        <label htmlFor={id} className="flex items-start gap-1.5 font-mono text-[10px] tracking-[0.06em] text-silver-dk uppercase leading-tight">
          {color && (
            <span
              className="block w-2 h-2 rounded-full shrink-0 mt-1"
              style={{ background: color, boxShadow: `0 0 6px ${color}aa` }}
            />
          )}
          <span>{label}</span>
        </label>
        <span className="font-mono text-[10px] text-orange-lt tabular-nums shrink-0 mt-0.5 whitespace-nowrap">
          {lo}<span className="text-silver-dk mx-1">—</span>{hi}
        </span>
      </div>

      <div
        className="relative h-6 select-none"
        style={{ '--lo': `${loPct}%`, '--hi': `${hiPct}%` } as React.CSSProperties}
      >
        {/* Inert track */}
        <div
          className="absolute top-1/2 -translate-y-1/2 left-0 right-0 h-1.5 rounded-full"
          style={{
            background: 'linear-gradient(180deg, hsl(216 10% 12%), hsl(218 11% 8%))',
            border: '1px solid hsl(216 10% 22%)',
            boxShadow: 'inset 0 1px 2px rgba(0,0,0,0.6)',
          }}
        />
        {/* Active range fill */}
        <div
          className="absolute top-1/2 -translate-y-1/2 h-1.5 rounded-full pointer-events-none"
          style={{
            left:  `var(--lo)`,
            right: `calc(100% - var(--hi))`,
            background: 'linear-gradient(90deg, #ff7a14, #ffb074)',
            boxShadow: '0 0 8px rgba(255,122,20,0.45)',
          }}
        />
        {/* Min input */}
        <input
          id={id}
          type="range"
          min={min} max={max} step={step}
          value={lo}
          onChange={(e) => {
            const v = Math.min(Number(e.target.value), hi);
            setLo(v);
            commit(v, hi);
          }}
          className="dual-range absolute inset-0 w-full appearance-none bg-transparent"
          style={{ zIndex: lo >= max - step ? 4 : 3 }}
          aria-label={`${label} minimum`}
        />
        {/* Max input */}
        <input
          type="range"
          min={min} max={max} step={step}
          value={hi}
          onChange={(e) => {
            const v = Math.max(Number(e.target.value), lo);
            setHi(v);
            commit(lo, v);
          }}
          className="dual-range absolute inset-0 w-full appearance-none bg-transparent"
          style={{ zIndex: 3 }}
          aria-label={`${label} maximum`}
        />
      </div>
    </div>
  );
}
