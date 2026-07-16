import { forwardRef } from 'react';
import { cn } from '../../lib/cn';

const sizeStyles = {
  sm: 'text-label px-2 py-0.5',
  md: 'text-overline px-2.5 py-1',
} as const;

const variantStyles = {
  default: [
    'bg-bg4 text-silver',
    'border border-silver/20',
    'shadow-inner-soft',
  ],
  silver: [
    'bg-gradient-to-b from-white/6 to-transparent bg-bg4',
    'border border-silver/30',
    'text-silver',
    'shadow-inner-soft',
  ],
  orange: [
    'bg-orange/15 text-orange-lt',
    'border border-orange/40',
    'shadow-inner-soft',
  ],
  green: [
    'bg-green/10 text-green',
    'border border-green/35',
  ],
  gold: [
    'bg-gold/10 text-gold',
    'border border-gold/35',
  ],
  red: [
    'bg-red/10 text-red',
    'border border-red/35',
  ],
  cyan: [
    'bg-cyan/10 text-cyan',
    'border border-cyan/35',
  ],
} as const;

type ChipVariant = keyof typeof variantStyles;
type ChipSize = keyof typeof sizeStyles;

export interface ChipProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: ChipVariant;
  size?: ChipSize;
}

export const Chip = forwardRef<HTMLSpanElement, ChipProps>(
  ({ variant = 'default', size = 'sm', className, ...props }, ref) => {
    return (
      <span
        ref={ref}
        className={cn(
          'inline-flex items-center gap-0.5',
          'rounded-full',
          'font-mono font-semibold tracking-[0.04em]',
          'border',
          variantStyles[variant],
          sizeStyles[size],
          className,
        )}
        {...props}
      />
    );
  },
);

Chip.displayName = 'Chip';
