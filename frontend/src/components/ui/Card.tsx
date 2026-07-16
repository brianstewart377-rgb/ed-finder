import { forwardRef } from 'react';
import { cn } from '../../lib/cn';

const variantStyles = {
  default: [
    // Glassmorphic chrome panel — replaces .panel
    'bg-metal',
    'backdrop-blur-xl saturate-[120%]',
    'border border-silver/20',
    'rounded-chunk-lg',
    'shadow-metal',
    // Chrome highlight stripe + inner border via pseudo-elements
    'card-chrome',
  ],
  thin: [
    // Lighter panel — replaces .panel-thin
    'bg-gradient-to-b from-white/5 to-transparent',
    'bg-bg2/88',
    'backdrop-blur-md saturate-[120%]',
    'border border-silver/20',
    'rounded-chunk',
    'shadow-brand',
    'card-chrome-thin',
  ],
  premium: [
    // Raised inner card — replaces .premium-subpanel
    'bg-gradient-to-b from-white/6 to-transparent',
    'bg-bg3/86',
    'border border-silver/20',
    'rounded-chunk',
    'shadow-metal',
    'overflow-hidden',
    'card-chrome-thin',
  ],
  toolbar: [
    // Raised toolbar pill — replaces .premium-toolbar
    'bg-gradient-to-b from-white/6 to-transparent',
    'bg-bg3/86',
    'border border-silver/20',
    'rounded-chunk-sm',
    'shadow-brand',
  ],
} as const;

const paddingStyles = {
  none: '',
  sm: 'p-3',
  md: 'p-5',
  lg: 'p-8',
} as const;

type CardVariant = keyof typeof variantStyles;
type CardPadding = keyof typeof paddingStyles;
type CardElement = 'div' | 'section' | 'aside' | 'article' | 'header' | 'footer';

export interface CardProps extends React.HTMLAttributes<HTMLElement> {
  variant?: CardVariant;
  padding?: CardPadding;
  as?: CardElement;
}

export const Card = forwardRef<HTMLElement, CardProps>(
  (
    { variant = 'default', padding = 'md', as: Comp = 'div', className, ...props },
    ref,
  ) => {
    return (
      <Comp
        ref={ref as React.Ref<HTMLDivElement>}
        className={cn(
          variantStyles[variant],
          paddingStyles[padding],
          className,
        )}
        {...props}
      />
    );
  },
);

Card.displayName = 'Card';
