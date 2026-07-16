import { cn } from '../../lib/cn';

const sizeStyles = {
  sm: 'text-label min-w-[1.2rem] h-4 px-1',
  md: 'text-overline min-w-[1.4rem] h-5 px-1.5',
} as const;

const variantStyles = {
  orange: 'bg-orange-grad text-white shadow-brand-glow',
  silver: 'bg-silver-grad text-bg1 shadow-brand',
  gold: 'bg-gold text-bg1 shadow-brand',
} as const;

type BadgeVariant = keyof typeof variantStyles;
type BadgeSize = keyof typeof sizeStyles;

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  count: number | string;
  variant?: BadgeVariant;
  size?: BadgeSize;
}

export function Badge({
  count,
  variant = 'orange',
  size = 'sm',
  className,
  ...props
}: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center justify-center',
        'rounded-full',
        'font-mono font-bold tabular-nums leading-none',
        variantStyles[variant],
        sizeStyles[size],
        className,
      )}
      {...props}
    >
      {count}
    </span>
  );
}
