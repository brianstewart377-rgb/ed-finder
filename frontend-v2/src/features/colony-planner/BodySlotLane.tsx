import type { ReactNode } from 'react';

export function BodySlotLane({
  laneKey,
  label,
  helper,
  slotStatus,
  disabled = false,
  disabledReason,
  onAdd,
  children,
}: {
  laneKey: 'orbital' | 'surface' | 'flex';
  label: string;
  helper: string;
  slotStatus: string;
  disabled?: boolean;
  disabledReason?: string;
  onAdd: () => void;
  children: ReactNode;
}) {
  const addLabel = laneKey === 'orbital'
    ? 'Add orbital structure'
    : laneKey === 'surface'
      ? 'Add surface structure'
      : 'Add flexible/unknown structure';

  return (
    <section
      data-testid={`slot-lane-${laneKey}`}
      className={[
        'relative overflow-hidden rounded border p-2.5',
        disabled
          ? 'border-gold/35 bg-gold/6'
          : laneKey === 'orbital'
            ? 'border-cyan/35 bg-cyan/5'
            : laneKey === 'surface'
              ? 'border-green/35 bg-green/5'
              : 'border-border/60 bg-bg3/35',
      ].join(' ')}
    >
      <div
        aria-hidden="true"
        className={[
          'pointer-events-none absolute inset-x-0 top-0 h-px',
          disabled
            ? 'bg-gold/50'
            : laneKey === 'orbital'
              ? 'bg-cyan/55'
              : laneKey === 'surface'
                ? 'bg-green/55'
                : 'bg-silver/35',
        ].join(' ')}
      />
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="font-mono text-[11px] uppercase tracking-[0.1em] text-silver">{label}</div>
          <p className="mt-0.5 text-xs leading-relaxed text-silver-dk">{helper}</p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="rounded border border-border/55 bg-bg2/60 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.1em] text-silver-dk">
            {slotStatus}
          </span>
          <button
            type="button"
            onClick={onAdd}
            disabled={disabled}
            data-testid={`slot-lane-add-${laneKey}`}
            className={[
              'rounded border px-2 py-1 font-mono text-[11px] uppercase tracking-[0.1em]',
              disabled
                ? 'cursor-not-allowed border-gold/35 bg-gold/10 text-gold/70'
                : 'border-orange/45 bg-orange/12 text-orange hover:bg-orange/20',
            ].join(' ')}
          >
            {addLabel}
          </button>
        </div>
      </div>

      {disabled && disabledReason && (
        <p className="mt-2 rounded border border-gold/30 bg-gold/10 px-2 py-1 text-xs leading-relaxed text-gold">
          {disabledReason}
        </p>
      )}

      <div className="mt-2">{children}</div>
    </section>
  );
}
