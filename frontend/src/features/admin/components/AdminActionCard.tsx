export function ActionCard({
  title,
  blurb,
  confirmText,
  disabled,
  busy,
  onClick,
  testid,
}: {
  title: string;
  blurb: string;
  confirmText: string;
  disabled: boolean;
  busy: boolean;
  onClick: () => Promise<void>;
  testid: string;
}) {
  return (
    <div className="panel-thin p-4 space-y-2 flex flex-col">
      <div className="font-display text-orange text-xs tracking-[0.14em]">{title}</div>
      <p className="text-[11px] text-silver-dk leading-snug flex-1">{blurb}</p>
      <button
        type="button"
        disabled={disabled}
        onClick={() => { if (confirm(confirmText)) void onClick(); }}
        data-testid={testid}
        className={disabled ? 'btn-metal opacity-50 cursor-not-allowed text-[11px] py-1.5' : 'btn-primary text-[11px] py-1.5'}
      >
        {busy ? '⟳ Working…' : 'Run'}
      </button>
    </div>
  );
}
