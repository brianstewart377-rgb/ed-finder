import { forwardRef } from 'react';
import { Slot } from '@radix-ui/react-slot';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import { cn } from '../../lib/cn';

const sizeStyles = {
  sm: 'h-7 w-7 rounded-md [&_svg]:size-3.5',
  md: 'h-9 w-9 rounded-lg [&_svg]:size-4.5',
  lg: 'h-11 w-11 rounded-chunk-sm [&_svg]:size-5.5',
} as const;

const variantStyles = {
  ghost: [
    'text-silver-dk',
    'hover:text-white hover:bg-white/8',
    'active:bg-white/12',
  ],
  metal: [
    'text-silver',
    'bg-bg4 border border-silver/20',
    'shadow-inner-soft',
    'hover:text-white hover:border-silver/40 hover:bg-bg5',
    'active:bg-bg4',
  ],
} as const;

type IconButtonSize = keyof typeof sizeStyles;
type IconButtonVariant = keyof typeof variantStyles;

export interface IconButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** Lucide icon component or any ReactNode */
  icon: React.ReactNode;
  /** Required — used as aria-label and visually-hidden text for screen readers */
  label: string;
  size?: IconButtonSize;
  variant?: IconButtonVariant;
  active?: boolean;
  asChild?: boolean;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  (
    {
      icon,
      label,
      size = 'md',
      variant = 'ghost',
      active,
      asChild,
      className,
      ...props
    },
    ref,
  ) => {
    const Comp = asChild ? Slot : 'button';
    return (
      <Comp
        ref={ref}
        aria-label={label}
        className={cn(
          'inline-flex items-center justify-center',
          'transition-colors duration-fast',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange/60 focus-visible:ring-offset-1 focus-visible:ring-offset-bg1',
          'disabled:opacity-30 disabled:cursor-not-allowed',
          sizeStyles[size],
          variantStyles[variant],
          active && 'text-orange bg-orange/10 border-orange/40',
          className,
        )}
        {...props}
      >
        {icon}
        <VisuallyHidden>{label}</VisuallyHidden>
      </Comp>
    );
  },
);

IconButton.displayName = 'IconButton';
