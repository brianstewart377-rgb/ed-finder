import { useEffect, useId, useRef, useState } from 'react';

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

const CHIP_HEIGHT = 34;
const CHIP_HALF_WIDTH = 168;
const CHIP_TOTAL_WIDTH = CHIP_HALF_WIDTH * 2;

export function EconomyJigsawChip({
  label,
  title,
  primaryEconomy,
  secondaryEconomy,
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
  const gradientId = useId().replace(/:/g, '');
  const leftMeasureRef = useRef<HTMLSpanElement | null>(null);
  const rightMeasureRef = useRef<HTMLSpanElement | null>(null);
  const [compactText, setCompactText] = useState(false);

  useEffect(() => {
    const leftWidth = leftMeasureRef.current?.getBoundingClientRect().width ?? 0;
    const rightWidth = rightMeasureRef.current?.getBoundingClientRect().width ?? 0;
    const nextCompact = leftWidth > CHIP_HALF_WIDTH - 34 || rightWidth > CHIP_HALF_WIDTH - 34;
    setCompactText((current) => (current === nextCompact ? current : nextCompact));
  }, [primaryEconomy, secondaryEconomy]);

  return (
    <span
      data-testid={wrapperTestId}
      aria-label={label}
      className="relative inline-grid grid-cols-2 overflow-hidden rounded-chunk border uppercase align-middle"
      style={{
        width: `${CHIP_TOTAL_WIDTH}px`,
        maxWidth: '100%',
        height: `${CHIP_HEIGHT}px`,
        borderColor: 'rgba(148,163,184,0.24)',
        background: [
          'linear-gradient(180deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0) 24%)',
          'linear-gradient(180deg, rgba(24, 28, 34, 0.9), rgba(12, 15, 20, 0.88))',
        ].join(', '),
        boxShadow: [
          'inset 0 1px 0 rgba(255,255,255,0.05)',
          'inset 0 -1px 0 rgba(0,0,0,0.28)',
          '0 12px 30px -24px rgba(0,0,0,0.9)',
          '0 0 18px -16px rgba(111,229,255,0.22)',
          '0 0 18px -16px rgba(255,122,20,0.2)',
        ].join(', '),
      }}
      title={title}
    >
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{
          background: [
            `radial-gradient(circle at 18% 50%, ${primarySoft} 0%, transparent 58%)`,
            `radial-gradient(circle at 82% 50%, ${secondarySoft} 0%, transparent 58%)`,
          ].join(', '),
          opacity: 0.8,
        }}
      />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-[1px] rounded-[15px]"
        style={{
          border: '1px solid rgba(255,255,255,0.03)',
          background: 'linear-gradient(180deg, rgba(255,255,255,0.045), transparent 34%)',
        }}
      />
      <svg
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 h-full w-full"
        viewBox="0 0 100 34"
        preserveAspectRatio="none"
      >
        <defs>
          <linearGradient id={`${gradientId}-left`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={primaryColor} stopOpacity="0.9" />
            <stop offset="100%" stopColor={primaryColor} stopOpacity="0.68" />
          </linearGradient>
          <linearGradient id={`${gradientId}-right`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={secondaryColor} stopOpacity="0.9" />
            <stop offset="100%" stopColor={secondaryColor} stopOpacity="0.68" />
          </linearGradient>
        </defs>
        <polygon points="0,0 53,0 47,34 0,34" fill={`url(#${gradientId}-left)`} />
        <polygon points="53,0 100,0 100,34 47,34" fill={`url(#${gradientId}-right)`} />
        <line
          x1="53"
          y1="0"
          x2="47"
          y2="34"
          stroke="rgba(10,14,22,0.28)"
          strokeWidth="3.2"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
        <line
          data-testid={dividerTestId}
          x1="53"
          y1="0"
          x2="47"
          y2="34"
          stroke="rgba(255,255,255,0.92)"
          strokeWidth="1.15"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      </svg>

      <span
        data-testid={leftTestId}
        className="relative z-[1] inline-flex h-full min-w-0 items-center justify-center px-4 text-center"
      >
        <span
          ref={leftMeasureRef}
          data-testid={primaryLabelTestId}
          className={[
            'block w-full truncate whitespace-nowrap text-center font-display font-semibold text-white',
            compactText ? 'text-[10px] tracking-[0.005em]' : 'text-[11px] tracking-[0.01em]',
          ].join(' ')}
        >
          {primaryEconomy}
        </span>
      </span>

      <span
        data-testid={rightTestId}
        className="relative z-[1] inline-flex h-full min-w-0 items-center justify-center px-4 text-center"
      >
        <span
          ref={rightMeasureRef}
          className={[
            'inline-flex w-full min-w-0 items-center justify-center whitespace-nowrap text-center font-display font-semibold text-white',
            compactText ? 'text-[10px] tracking-[0.005em]' : 'text-[11px] tracking-[0.01em]',
          ].join(' ')}
        >
          <span data-testid={secondaryLabelTestId} className="block shrink-0 text-center">
            {secondaryEconomy}
          </span>
        </span>
      </span>
    </span>
  );
}
