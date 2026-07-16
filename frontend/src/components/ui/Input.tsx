import { forwardRef } from 'react';
import { cn } from '../../lib/cn';

const sizeStyles = {
  sm: 'text-label px-2.5 py-1.5',
  md: 'text-overline px-3.5 py-2',
  lg: 'text-sm px-4 py-2.5',
} as const;

type InputSize = keyof typeof sizeStyles;

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
  inputSize?: InputSize;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, hint, inputSize = 'md', className, id, ...props }, ref) => {
    const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined);

    return (
      <div className="space-y-1">
        {label && (
          <label
            htmlFor={inputId}
            className="block font-mono text-label uppercase tracking-[0.12em] text-silver-dk"
          >
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          aria-invalid={!!error}
          aria-describedby={error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined}
          className={cn(
            'w-full',
            'bg-gradient-to-b from-bg3 to-bg2',
            'border border-border',
            'rounded-chunk-sm',
            'text-text font-ui placeholder:text-silver-2',
            'shadow-inner-soft',
            'transition-colors duration-fast',
            'focus:outline-none focus:border-orange/65 focus:ring-2 focus:ring-orange/20',
            'disabled:opacity-40 disabled:cursor-not-allowed',
            error && 'border-red/50 focus:border-red/65 focus:ring-red/20',
            sizeStyles[inputSize],
            props.type === 'number' && 'no-spinner',
            className,
          )}
          {...props}
        />
        {error && (
          <p id={`${inputId}-error`} className="text-label text-red" role="alert">
            {error}
          </p>
        )}
        {hint && !error && (
          <p id={`${inputId}-hint`} className="text-caption text-silver-2">
            {hint}
          </p>
        )}
      </div>
    );
  },
);

Input.displayName = 'Input';
