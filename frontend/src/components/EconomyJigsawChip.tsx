interface EconomyJigsawChipProps {
  label: string;
  title: string;
  primaryEconomy: string;
  secondaryEconomy: string;
  suffix?: string;
  primaryColor: string;
  secondaryColor: string;
  primarySoft: string;
  secondarySoft: string;
  testIdPrefix?: string;
}

export function EconomyJigsawChip({
  label,
  title,
  primaryEconomy,
  secondaryEconomy,
  suffix = '',
  primaryColor,
  secondaryColor,
  primarySoft,
  secondarySoft,
  testIdPrefix,
}: EconomyJigsawChipProps) {
  const wrapperTestId = testIdPrefix;
  const leftTestId = testIdPrefix ? `${testIdPrefix}-left` : undefined;
  const dividerTestId = testIdPrefix ? `${testIdPrefix}-divider` : undefined;
  const rightTestId = testIdPrefix ? `${testIdPrefix}-right` : undefined;
  const primaryLabelTestId = testIdPrefix ? `${testIdPrefix}-primary` : undefined;
  const secondaryLabelTestId = testIdPrefix ? `${testIdPrefix}-secondary` : undefined;
  const secondarySuffixTestId = testIdPrefix ? `${testIdPrefix}-suffix` : undefined;

  return (
    <span
      data-testid={wrapperTestId}
      aria-label={label}
      className="relative inline-flex overflow-hidden rounded-chunk border uppercase"
      style={{
        borderColor: 'rgba(148,163,184,0.22)',
        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.05), 0 18px 44px -34px rgba(0,0,0,0.9)',
      }}
      title={title}
    >
      <span
        data-testid={leftTestId}
        className="relative z-[1] inline-flex items-center px-3 py-[7px] pr-8 font-mono text-[10px] font-bold tracking-[0.12em]"
        style={{ background: `linear-gradient(180deg, ${primarySoft}, rgba(15,23,42,0.16))` }}
      >
        <span data-testid={primaryLabelTestId} style={{ color: primaryColor }}>
          {primaryEconomy}
        </span>
      </span>

      <span
        data-testid={rightTestId}
        className="relative z-[1] inline-flex items-center px-3 py-[7px] pl-8 font-mono text-[10px] font-bold tracking-[0.12em]"
        style={{ background: `linear-gradient(180deg, ${secondarySoft}, rgba(15,23,42,0.16))` }}
      >
        <span data-testid={secondaryLabelTestId} style={{ color: secondaryColor }}>
          {secondaryEconomy}
        </span>
        {suffix ? <span data-testid={secondarySuffixTestId} className="ml-2 text-silver">{suffix}</span> : null}
      </span>

      <span
        data-testid={dividerTestId}
        aria-hidden="true"
        className="pointer-events-none absolute inset-y-[-1px] left-1/2 z-[2] w-[14px]"
        style={{
          background: 'linear-gradient(180deg, rgba(226,232,240,0.55), rgba(148,163,184,0.16))',
          transform: 'translateX(-50%) skewX(-18deg)',
          boxShadow: '0 0 0 1px rgba(2,6,23,0.35)',
        }}
      />
    </span>
  );
}
