import { forwardRef } from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cn } from '../../lib/cn';

const variantStyles = {
  primary: [
    'bg-orange-grad text-white',
    'border border-orange-lt/90',
    'shadow-brand-glow',
    'hover:brightness-110',
    'active:translate-y-px active:brightness-95',
  ],
  metal: [
    'bg-metal text-silver',
    'border border-silver/30',
    'shadow-brand',
    'hover:border-silver/45 hover:text-white hover:bg-metal-active',
    'active:translate-y-px',
  ],
  ghost: [
    'bg-transparent text-silver-dk',
    'border border-transparent',
    'hover:text-white hover:bg-white/6',
    'active:translate-y-px',
  ],
} as const;

const sizeStyles = {
  sm: 'text-label px-2.5 py-1 gap-1',
  md: 'text-overline px-4 py-1.5 gap-1.5',
  lg: 'text-sm px-6 py-2.5 gap-2',
} as const;

type ButtonVariant = keyof typeof variantStyles;
type ButtonSize = keyof typeof sizeStyles;

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    { variant = 'primary', size = 'md', asChild, className, disabled, ...props },
    ref,
  ) => {
    const Comp = asChild ? Slot : 'button';
    return (
      <Comp
        ref={ref}
        disabled={disabled}
        className={cn(
          // Base
          'inline-flex items-center justify-center',
          'font-display font-bold uppercase tracking-[0.12em]',
          'rounded-chunk-sm',
          'transition-all duration-fast',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/60 focus-visible:ring-offset-2 focus-visible:ring-offset-bg1',
          // Interactive
          'select-none',
          disabled && 'opacity-40 cursor-not-allowed pointer-events-none',
          // Variant + size
          variantStyles[variant],
          sizeStyles[size],
          className,
        )}
        {...props}
      />
    );
  },
);

Button.displayName = 'Button';
